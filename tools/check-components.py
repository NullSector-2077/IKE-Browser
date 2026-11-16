#!/usr/bin/env python3
"""Daily check of the components I.K.E. bundles against their newest releases.

    python3 tools/check-components.py [--json FILE] [--markdown FILE] [--apply] [--ubo-src DIR]

Components and where the version in use is written:

- adblock-rust, the AdBlock engine library: ``ike-adblock/Cargo.toml``
  (newest on crates.io);
- uBlock Origin scriptlets: ``ike/resources/ubo-scriptlets.json`` (rebuilt from
  uBlock Origin's newest sources with tools/build-ubo-scriptlets.mjs; only a
  change in the scriptlets themselves counts, not a new commit);
- Qt WebEngine and PyQt6 of the AppImage: ``tools/appimage-requirements.txt``
  (the newest set pip would install for the AppImage's Python);
- the standalone Python of the AppImage and of the Windows build:
  ``tools/build-appimage.sh`` and ``tools/build-windows.ps1``
  (python-build-standalone; a new Python patch release counts, a rebuild of
  the same Python does not). The Windows build uses the same Qt / PyQt6
  versions (``tools/appimage-requirements.txt``).

Packages of the AppImage other than Qt (cryptography, certifi, ...) and new
builds of the same Python are reported as "also newer": they do not call for
a release on their own, and are taken along by the next one.

With --apply the files above are rewritten with the newest versions (and
``cargo update`` is run for a new engine); adapting I.K.E.'s code, building
and testing are handled by the daily GitHub Actions maintenance workflow.
Needs git, and for the scriptlets Node.js; uses only crates.io, PyPI and
github.com (no API token).
"""

import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CRATES_INDEX = "https://index.crates.io/ad/bl/adblock"
UBO_GIT = "https://github.com/gorhill/uBlock"
PBS_GIT = "https://github.com/astral-sh/python-build-standalone"
PBS_DOWNLOAD = PBS_GIT + "/releases/download"
# the Qt packages: a new version of any of them calls for a new AppImage
QT_PACKAGES = ("pyqt6", "pyqt6-qt6", "pyqt6-webengine", "pyqt6-webengine-qt6")
# packages the AppImage asks for; the rest are their dependencies
APPIMAGE_TOP = ("PyQt6", "PyQt6-WebEngine", "cryptography", "certifi", "jeepney")


def fetch(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": "ike-browser-component-check"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def vkey(version):
    """Sort key for release versions such as 0.13.5, 6.140.0, 2026.10.18."""
    return tuple(int(n) for n in re.findall(r"\d+", version))


def is_stable(version):
    return re.fullmatch(r"[0-9]+(\.[0-9]+)*(\.post[0-9]+)?", version) is not None


def norm(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw).stdout


# --- adblock-rust -----------------------------------------------------------

def current_adblock(root):
    text = (root / "ike-adblock" / "Cargo.toml").read_text("utf-8")
    return re.search(r'^adblock = \{ version = "=([^"]+)"', text, re.M).group(1)


def latest_adblock():
    versions = []
    for line in fetch(CRATES_INDEX).decode("utf-8").splitlines():
        if line.strip():
            entry = json.loads(line)
            if not entry.get("yanked") and is_stable(entry["vers"]):
                versions.append(entry["vers"])
    return max(versions, key=vkey)


def check_adblock(root):
    cur, new = current_adblock(root), latest_adblock()
    newer = vkey(new) > vkey(cur)
    return {"current": cur, "latest": new, "update": newer,
            "note": "system part: raise __min_system__ and adapt ike-adblock/src/lib.rs if the API changed"
            if newer else ""}


def apply_adblock(root, info):
    v = info["latest"]
    cargo = root / "ike-adblock" / "Cargo.toml"
    cargo.write_text(re.sub(r'^(adblock = \{ version = "=)[^"]+"', r'\g<1>' + v + '"',
                            cargo.read_text("utf-8"), flags=re.M), "utf-8")
    lib = root / "ike-adblock" / "src" / "lib.rs"
    lib.write_text(re.sub(r'(const ENGINE_VERSION: &str = ")[^"]+"', r'\g<1>' + v + '"',
                          lib.read_text("utf-8")), "utf-8")
    if shutil.which("cargo"):
        run(["cargo", "update", "-p", "adblock", "--precise", v,
             "--manifest-path", str(cargo)])
    else:
        print("!! cargo not found: run `cargo update -p adblock --precise %s` in ike-adblock/" % v)


# --- uBlock Origin scriptlets ------------------------------------------------

def scriptlets_hash(data):
    return hashlib.sha256(json.dumps(data["scriptlets"], sort_keys=True).encode("utf-8")).hexdigest()


def build_scriptlets(root, work, ubo_src=None):
    src = work / "src"
    if ubo_src:
        os.symlink(Path(ubo_src).resolve(), src)
    else:
        run(["git", "clone", "--quiet", "--depth", "1", UBO_GIT, str(src)])
    run(["node", str(root / "tools" / "build-ubo-scriptlets.mjs")], cwd=work)
    return work / "ubo-scriptlets.json"


def check_scriptlets(root, work, ubo_src=None):
    cur = json.loads((root / "ike" / "resources" / "ubo-scriptlets.json").read_text("utf-8"))
    built = build_scriptlets(root, work, ubo_src)
    new = json.loads(built.read_text("utf-8"))
    changed = scriptlets_hash(cur) != scriptlets_hash(new)
    names_cur, names_new = set(cur["scriptlets"]), set(new["scriptlets"])
    note = ""
    if changed:
        modified = sum(1 for n in names_cur & names_new if cur["scriptlets"][n] != new["scriptlets"][n])
        note = "%d changed, %d new, %d removed" % (modified, len(names_new - names_cur), len(names_cur - names_new))
    return {"current": "%s (%s)" % (cur["commit"][:10], cur["date"]),
            "latest": "%s (%s)" % (new["commit"][:10], new["date"]),
            "update": changed, "note": note, "_file": str(built)}


def apply_scriptlets(root, info):
    shutil.copyfile(info["_file"], root / "ike" / "resources" / "ubo-scriptlets.json")


# --- Qt WebEngine / PyQt6 of the AppImage ------------------------------------

def read_pins(root):
    pins = {}
    for line in (root / "tools" / "appimage-requirements.txt").read_text("utf-8").splitlines():
        line = line.split("#")[0].strip()
        if line:
            name, version = line.split("==")
            pins[norm(name)] = (name.strip(), version.strip())
    return pins


def appimage_python(root):
    text = (root / "tools" / "build-appimage.sh").read_text("utf-8")
    return re.search(r"^PBS_PYTHON=(\S+)", text, re.M).group(1)


def resolve_appimage(root):
    """Resolve the newest package set pip installs for the AppImage Python."""
    minor = ".".join(appimage_python(root).split(".")[:2])
    plats = []
    for glibc in range(34, 4, -1):            # the AppImage needs glibc 2.34
        plats += ["--platform", "manylinux_2_%d_x86_64" % glibc]
    plats += ["--platform", "manylinux2014_x86_64", "--platform", "manylinux2010_x86_64",
              "--platform", "manylinux1_x86_64"]
    abi = "cp" + minor.replace(".", "")
    with tempfile.TemporaryDirectory() as tmp:
        report = Path(tmp) / "report.json"
        run([sys.executable, "-m", "pip", "install", "--dry-run", "--ignore-installed", "--quiet",
             "--disable-pip-version-check", "--report", str(report), "--only-binary=:all:",
             "--python-version", minor, "--implementation", "cp",
             "--abi", abi, "--abi", "abi3", "--abi", "none", *plats, *APPIMAGE_TOP],
            env=dict(os.environ, PYTHONNOUSERSITE="1"))
        data = json.loads(report.read_text("utf-8"))
    return {norm(i["metadata"]["name"]): (i["metadata"]["name"], i["metadata"]["version"])
            for i in data["install"]}


def check_appimage_packages(root):
    pins, new = read_pins(root), resolve_appimage(root)
    qt = [n for n in QT_PACKAGES if n in new and (n not in pins or new[n][1] != pins[n][1])]
    other = [n for n in new if n not in QT_PACKAGES and (n not in pins or new[n][1] != pins[n][1])]
    gone = [n for n in pins if n not in new]

    def show(names):
        return ", ".join("%s %s -> %s" % (new[n][0], pins[n][1] if n in pins else "-", new[n][1])
                         for n in names)

    def label(s):
        return "Qt %s, WebEngine wheel %s" % (s.get("pyqt6-qt6", ("", "?"))[1],
                                              s.get("pyqt6-webengine-qt6", ("", "?"))[1])

    return {"current": label(pins), "latest": label(new),
            "update": bool(qt), "note": show(qt),
            "also": "; ".join(x for x in (show(other), ("no longer needed: " + ", ".join(gone)) if gone else "")
                              if x),
            "_set": new}


def apply_appimage_packages(root, info):
    pins, new = read_pins(root), info["_set"]
    path = root / "tools" / "appimage-requirements.txt"
    header = [line for line in path.read_text("utf-8").splitlines() if line.startswith("#")]
    order = list(pins) + sorted(n for n in new if n not in pins)
    lines = ["%s==%s" % (pins[n][0] if n in pins else new[n][0], new[n][1]) for n in order if n in new]
    path.write_text("\n".join(header + lines) + "\n", "utf-8")


# --- standalone Python of the AppImage ----------------------------------------

def current_pbs(root):
    text = (root / "tools" / "build-appimage.sh").read_text("utf-8")
    get = lambda key: re.search(r"^%s=(\S+)" % key, text, re.M).group(1)  # noqa: E731
    return get("PBS_TAG"), get("PBS_PYTHON")


def latest_pbs(minor):
    tags = []
    for line in run(["git", "ls-remote", "--tags", "--refs", PBS_GIT]).splitlines():
        tag = line.rsplit("/", 1)[-1]
        if re.fullmatch(r"\d{8}", tag):
            tags.append(tag)
    tag = max(tags)
    sums = fetch("%s/%s/SHA256SUMS" % (PBS_DOWNLOAD, tag)).decode("utf-8")
    found = {}
    for target in ("x86_64-unknown-linux-gnu", "x86_64-pc-windows-msvc"):
        pat = re.compile(r"^([0-9a-f]{64})\s+cpython-(%s\.\d+)\+%s-%s-install_only\.tar\.gz$"
                         % (re.escape(minor), tag, target))
        for line in sums.splitlines():
            m = pat.match(line.strip())
            if m:
                found[target] = (m.group(2), m.group(1))
    linux, windows = found.get("x86_64-unknown-linux-gnu"), found.get("x86_64-pc-windows-msvc")
    if not linux or not windows or linux[0] != windows[0]:
        raise RuntimeError("no Python %s build for x86_64 Linux and Windows in release %s" % (minor, tag))
    return tag, linux[0], linux[1], windows[1]


def check_pbs(root):
    tag, python = current_pbs(root)
    minor = ".".join(python.split(".")[:2])
    new_tag, new_python, sha, win_sha = latest_pbs(minor)
    newer_python = vkey(new_python) > vkey(python)
    return {"current": "Python %s (build %s)" % (python, tag),
            "latest": "Python %s (build %s)" % (new_python, new_tag),
            "update": newer_python, "note": "",
            "also": "newer build %s of Python %s" % (new_tag, new_python)
            if not newer_python and new_tag > tag else "",
            "_new": (new_tag, new_python, sha, win_sha), "_newer": new_tag > tag}


def apply_pbs(root, info):
    if not info["_newer"]:
        return
    tag, python, sha, win_sha = info["_new"]
    path = root / "tools" / "build-appimage.sh"
    text = path.read_text("utf-8")
    for key, value in (("PBS_TAG", tag), ("PBS_PYTHON", python), ("PBS_SHA256", sha)):
        text = re.sub(r"^%s=\S+" % key, "%s=%s" % (key, value), text, flags=re.M)
    path.write_text(text, "utf-8")
    path = root / "tools" / "build-windows.ps1"
    text = path.read_text("utf-8")
    for key, value in (("PBS_TAG", tag), ("PBS_PYTHON", python), ("PBS_SHA256", win_sha)):
        text = re.sub(r'^\$%s = "[^"]*"' % key, '$%s = "%s"' % (key, value), text, flags=re.M)
    path.write_text(text, "utf-8")


# --- report -----------------------------------------------------------------

def check_all(root, ubo_src=None, work=None):
    work = Path(work or tempfile.mkdtemp(prefix="ike-check-"))
    work.mkdir(parents=True, exist_ok=True)
    checks = [
        ("adblock-rust (AdBlock engine)", check_adblock, apply_adblock, ()),
        ("uBlock Origin scriptlets", check_scriptlets, apply_scriptlets, (work, ubo_src)),
        ("Qt WebEngine / PyQt6 (AppImage)", check_appimage_packages, apply_appimage_packages, ()),
        ("Python (AppImage, Windows)", check_pbs, apply_pbs, ()),
    ]
    results = []
    for name, check, apply, args in checks:
        try:
            info = check(root, *args)
            info.setdefault("also", "")
            info["error"] = ""
        except Exception as e:   # one failing source must not hide the others
            info = {"current": "", "latest": "", "update": False, "note": "", "also": "",
                    "error": "%s: %s" % (type(e).__name__, (getattr(e, "stderr", "") or str(e)).strip()[:300])}
        info["name"] = name
        info["_apply"] = apply
        results.append(info)
    return results


def public(results):
    return [{k: v for k, v in r.items() if not k.startswith("_")} for r in results]


def to_markdown(results):
    n = sum(r["update"] for r in results)
    out = []
    if n:
        out.append("Nuove versioni trovate: GitHub Actions prepara un candidato da testare e sottoporre al proprietario.\n")
    out.append("New versions of bundled components: **%d**. Checked %s UTC by "
               "`tools/check-components.py`.\n" % (n, datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M")))
    out.append("| Component | In use | Newest | New | Notes |\n|---|---|---|---|---|")
    for r in results:
        notes = "; ".join(x for x in (r["note"], ("also newer: " + r["also"]) if r["also"] else "",
                                      ("**check failed**: " + r["error"]) if r["error"] else "") if x)
        out.append("| %s | %s | %s | %s | %s |" % (r["name"], r["current"], r["latest"],
                                                  "**yes**" if r["update"] else "no", notes.replace("|", "\\|")))
    return "\n".join(out) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--json", help="write the result as JSON to this file")
    ap.add_argument("--markdown", help="write the result as a Markdown table to this file")
    ap.add_argument("--apply", action="store_true",
                    help="rewrite the version files with every newer version found")
    ap.add_argument("--ubo-src", help="use this uBlock Origin checkout instead of cloning it")
    ap.add_argument("--root", default=str(ROOT), help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    root = Path(args.root)
    results = check_all(root, args.ubo_src)
    for r in results:
        state = "ERROR " + r["error"] if r["error"] else ("NEW" if r["update"] else "ok")
        print("%-34s %-6s %s -> %s %s" % (r["name"], state.split(" ")[0], r["current"], r["latest"],
                                         r["note"] or r["also"] or (r["error"] if r["error"] else "")))
    updates = sum(r["update"] for r in results)
    errors = sum(bool(r["error"]) for r in results)
    print("updates: %d, errors: %d" % (updates, errors))
    if args.json:
        Path(args.json).write_text(json.dumps({"updates": updates, "errors": errors,
                                               "components": public(results)}, indent=1) + "\n", "utf-8")
    if args.markdown:
        Path(args.markdown).write_text(to_markdown(results), "utf-8")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write("updates=%d\nerrors=%d\n" % (updates, errors))
    if args.apply:
        if errors:
            print("not applying any updates: at least one component source could not be checked")
            return 1
        if updates:
            for r in results:
                if r["update"] or r["also"]:
                    r["_apply"](root, r)
                    print("applied:", r["name"])
        else:
            print("no actionable component updates; informational rebuilds are deferred")
    return 0


if __name__ == "__main__":
    sys.exit(main())
