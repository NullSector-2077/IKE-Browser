#!/usr/bin/env python3
"""Generate the offline sources of the Flatpak build (packaging/flatpak/generated/).

    python3 tools/flatpak-sources.py [--tools DIR]

Flathub builds without network, so every crate and every Python package the
build needs is listed with its address and SHA-256. This script writes those
lists with the official generators of flatpak-builder-tools
(https://github.com/flatpak/flatpak-builder-tools), checked out at a fixed
commit (or the copy given with --tools):

- cargo-sources.json: the crates of the I.K.E. AdBlock engine, from
  ike-adblock/Cargo.lock (flatpak-cargo-generator);
- python3-build-deps.json: setuptools-rust and maturin, needed only to build
  cryptography and removed from the finished Flatpak, plus
  cargo-sources-maturin.json for maturin's own crates;
- python3-runtime-deps.json: jeepney and cryptography (with cffi, pycparser),
  all from their source archives (flatpak-pip-generator), plus
  cargo-sources-cryptography.json for cryptography's Rust part.

Run it again after a change of ike-adblock/Cargo.lock or of the versions
pinned below, and commit the result. Needs git, network access to GitHub,
PyPI and crates.io, and in the Python that runs it: aiohttp, tomlkit,
requirements-parser, packaging (for example in a virtual environment:
python3 -m venv /tmp/fpvenv && /tmp/fpvenv/bin/pip install aiohttp tomlkit
requirements-parser packaging, then /tmp/fpvenv/bin/python
tools/flatpak-sources.py). Python 3.13, as in the KDE 6.11 run time, gives
the same environment markers as the build.
"""

import argparse
import hashlib
import io
import json
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "packaging" / "flatpak" / "generated"
TOOLS_REPO = "https://github.com/flatpak/flatpak-builder-tools"
TOOLS_COMMIT = "9d86d336a39b9af38b86f114b6ce5820fe260f91"

# what the Flatpak needs beyond the run time and the PyQt base application
# (docs: packaging/flatpak/README.md); the same Python libraries as the PKGBUILD
RUNTIME = ["jeepney==0.9.0", "cryptography==50.0.2"]
BUILD_ONLY = ["setuptools-rust==1.13.0", "maturin==1.16.0"]
# modules whose source archive contains a Rust workspace to vendor
RUST = {"python3-maturin": "maturin", "python3-cryptography": "cryptography"}


def run(cmd, **kw):
    print("+", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run(cmd, check=True, **kw)


def tools_dir(given, tmp):
    if given:
        return Path(given)
    d = Path(tmp) / "flatpak-builder-tools"
    run(["git", "init", "-q", str(d)])
    run(["git", "-C", str(d), "fetch", "-q", "--depth", "1", TOOLS_REPO, TOOLS_COMMIT])
    run(["git", "-C", str(d), "checkout", "-q", "FETCH_HEAD"])
    return d


def cargo_sources(tools, lock, out):
    run([sys.executable, str(tools / "cargo" / "flatpak-cargo-generator.py"), str(lock), "-o", str(out)])


def pip_modules(tools, packages, name, build_only, cwd):
    cmd = [sys.executable, str(tools / "pip" / "flatpak-pip-generator.py"), "--output", name]
    if build_only:
        cmd.append("--build-only")
    for p in packages:          # source archives only, for every package and dependency
        cmd += ["--artifact-policy", p.split("==")[0] + "=sdist"]
    for dep in ("cffi", "pycparser", "semantic-version", "setuptools"):
        cmd += ["--artifact-policy", dep + "=sdist"]
    run(cmd + packages, cwd=cwd)
    return json.loads((Path(cwd) / (name + ".json")).read_text("utf-8"))


def cargo_lock_of(module, crate, tmp):
    """Cargo.lock from the module's source archive, checked against its SHA-256."""
    src = next(s for s in module["sources"] if s["url"].rsplit("/", 1)[-1].startswith(crate + "-"))
    with urllib.request.urlopen(src["url"], timeout=120) as r:
        data = r.read()
    if hashlib.sha256(data).hexdigest() != src["sha256"]:
        raise SystemExit("SHA-256 mismatch for %s" % src["url"])
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        member = next(m for m in tar.getmembers()
                      if m.isfile() and m.name.count("/") == 1 and m.name.endswith("/Cargo.lock"))
        lock = Path(tmp) / ("%s-Cargo.lock" % crate)
        lock.write_bytes(tar.extractfile(member).read())
    return lock


def split_cffi(group):
    """cryptography is compiled against cffi, so cffi (with pycparser) must be
    installed before: a module of its own. One pip run builds every package
    of the module before it installs any."""
    for i, module in enumerate(group["modules"]):
        if module["name"] != "python3-cryptography":
            continue
        mine = [s for s in module["sources"]
                if s["url"].rsplit("/", 1)[-1].startswith(("cffi-", "pycparser-"))]
        module["sources"] = [s for s in module["sources"] if s not in mine]
        cffi = dict(module, name="python3-cffi", sources=mine, **{"build-commands": [
            module["build-commands"][0].replace('"%s"' % RUNTIME[1], '"cffi"')]})
        group["modules"].insert(i, cffi)
        return


def add_rust(module, tools, tmp):
    """Vendored crates and an offline cargo for a module that compiles Rust."""
    crate = RUST[module["name"]]
    name = "cargo-sources-%s.json" % crate
    cargo_sources(tools, cargo_lock_of(module, crate, tmp), OUT / name)
    module["build-options"] = {"env": {"CARGO_HOME": "/run/build/%s/cargo" % module["name"],
                                       "CARGO_NET_OFFLINE": "true"}}
    module["sources"].append(name)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--tools", help="a checkout of flatpak-builder-tools (default: fetch the pinned commit)")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        tools = tools_dir(args.tools, tmp)
        cargo_sources(tools, ROOT / "ike-adblock" / "Cargo.lock", OUT / "cargo-sources.json")

        build = pip_modules(tools, BUILD_ONLY, "python3-build-deps", True, tmp)
        # setuptools-rust builds maturin: it has to come first
        build["modules"].sort(key=lambda m: m["name"] != "python3-setuptools-rust")
        runtime = pip_modules(tools, RUNTIME, "python3-runtime-deps", False, tmp)
        split_cffi(runtime)
        for group in (build, runtime):
            for module in group["modules"]:
                if module["name"] in RUST:
                    add_rust(module, tools, tmp)
        for group in (build, runtime):
            (OUT / (group["name"] + ".json")).write_text(json.dumps(group, indent=4) + "\n", "utf-8")
    print("written to", OUT)


if __name__ == "__main__":
    main()
