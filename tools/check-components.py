#!/usr/bin/env python3
"""Daily check of the components I.K.E. bundles against their newest releases.

    python3 tools/check-components.py [--json FILE] [--markdown FILE] [--apply] [--ubo-src DIR]

Components and where the version in use is written:

- adblock-rust, the AdBlock engine library: ``ike-adblock/Cargo.toml``
  (newest on crates.io);
- uBlock Origin scriptlets: ``ike/resources/ubo-scriptlets.json`` (rebuilt from
  uBlock Origin's newest sources with tools/build-ubo-scriptlets.mjs; only a
  change in the scriptlets themselves counts, not a new commit);
- Dark Reader, the engine of the page dark mode and the lists of its extension
  (fixes for single sites, sites that are dark already, hints of a site's own
  dark theme): ``ike/resources/darkreader*.{js,json}`` (rebuilt with
  tools/build-darkreader.py from the newest "darkreader" package on npm and
  the newest lists in Dark Reader's repository; only a new engine or changed
  lists count);
- Qt WebEngine and PyQt6 of the automatic tests: ``tools/test-requirements.txt``
  (the newest set pip would install). The browser itself runs on Arch Linux's
  own qt6-webengine, updated by pacman: its current version is shown in the
  report so the tests can follow it.

Test packages other than Qt (cryptography, certifi, ...) are reported as
"also newer": they do not call for a release on their own, and are taken
along by the next one.

With --apply the files above are rewritten with the newest versions (and
``cargo update`` is run for a new engine); adapting I.K.E.'s code, building
and testing are handled by the daily GitHub Actions maintenance workflow.
Needs git, and for the scriptlets Node.js; uses only crates.io, PyPI,
registry.npmjs.org and github.com (no API token).
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
PYO3_INDEX = "https://index.crates.io/py/o3/pyo3"
UBO_GIT = "https://github.com/gorhill/uBlock"
DARKREADER_GIT = "https://github.com/darkreader/darkreader"
DARKREADER_NPM = "https://registry.npmjs.org/darkreader/latest"
ARCH_PACKAGE = "https://archlinux.org/packages/search/json/?name=qt6-webengine"
# the Qt packages: a new version of any of them calls for a test run on it
QT_PACKAGES = ("pyqt6", "pyqt6-qt6", "pyqt6-webengine", "pyqt6-webengine-qt6")
# packages the tests ask for; the rest are their dependencies
# pytest and ruff too (1.1.19): unpinned, a new release could turn main red with
# no change of I.K.E. (a new lint rule) and start an automatic fix for nothing
TEST_TOP = ("PyQt6", "PyQt6-WebEngine", "cryptography", "certifi", "jeepney", "pytest", "ruff")


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
            "note": "engine: travels in the signed self-update; adapt ike-adblock/src/lib.rs if the API changed"
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
        # the credits follow the engine (docs/THIRD-PARTY.md, 1.1.14); never a
        # reason to stop the update: the tests catch a list left behind
        tool = root / "tools" / "third-party.py"
        if tool.is_file():
            done = subprocess.run([sys.executable, str(tool)], capture_output=True, text=True)
            if done.returncode != 0:
                print("!! docs/THIRD-PARTY.md not updated: run tools/third-party.py")
    else:
        print("!! cargo not found: run `cargo update -p adblock --precise %s` in ike-adblock/" % v)


# --- the other crates of the AdBlock engine (1.1.19) ---------------------------
# pyo3 (the bridge to Python: a new Python on Arch may need a newer one),
# serde_json and every crate they and adblock bring were never updated: only
# adblock itself was followed, and a vulnerable crate only opened an issue
# (security.yml). Now the newest compatible versions are written into
# Cargo.lock (adblock stays at its exact version, followed above), and a new
# pyo3 release line raises the requirement; the tests (cargo test, cargo-deny,
# the whole suite) decide, and the automatic fix may adapt I.K.E.'s wrapper.

def lock_packages(text):
    """{name: version} of a Cargo.lock (the first version of a name)."""
    out = {}
    for block in text.split("[[package]]")[1:]:
        name = re.search(r'^name = "([^"]+)"', block, re.M)
        version = re.search(r'^version = "([^"]+)"', block, re.M)
        if name and version:
            out.setdefault(name.group(1), version.group(1))
    return out


def current_pyo3(root):
    text = (root / "ike-adblock" / "Cargo.toml").read_text("utf-8")
    return re.search(r'^pyo3 = \{ version = "([^"]+)"', text, re.M).group(1)


def latest_pyo3():
    versions = []
    for line in fetch(PYO3_INDEX).decode("utf-8").splitlines():
        if line.strip():
            entry = json.loads(line)
            if not entry.get("yanked") and is_stable(entry["vers"]):
                versions.append(entry["vers"])
    return max(versions, key=vkey)


def pyo3_requirement(current, latest):
    """The requirement for the latest release line ("0.31" for 0.31.2; "1"
    from 1.0), or the current one when that line is not newer."""
    parts = latest.split(".")
    line = ".".join(parts[:2]) if parts[0] == "0" else parts[0]
    return line if vkey(line + ".0") > vkey(current + ".0") else current


def _with_pyo3(text, requirement):
    return re.sub(r'^(pyo3 = \{ version = ")[^"]+"', r"\g<1>" + requirement + '"', text, flags=re.M)


def updated_lock(root, requirement):
    """The Cargo.lock cargo writes with the newest compatible crates (and this
    pyo3 requirement), made in a copy: the repository is not touched."""
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "ike-adblock"
        shutil.copytree(root / "ike-adblock", copy, ignore=shutil.ignore_patterns("target"))
        manifest = copy / "Cargo.toml"
        manifest.write_text(_with_pyo3(manifest.read_text("utf-8"), requirement), "utf-8")
        run(["cargo", "update", "--manifest-path", str(manifest)])
        return (copy / "Cargo.lock").read_text("utf-8")


def check_crates(root):
    cur_req = current_pyo3(root)
    req = pyo3_requirement(cur_req, latest_pyo3())
    old = lock_packages((root / "ike-adblock" / "Cargo.lock").read_text("utf-8"))
    new = lock_packages(updated_lock(root, req))
    changed = sorted(n for n in new if n in old and new[n] != old[n])
    added = sorted(n for n in new if n not in old)
    gone = sorted(n for n in old if n not in new)
    parts = ["%s %s -> %s" % (n, old[n], new[n]) for n in changed]
    parts += ["new: " + ", ".join(added)] if added else []
    parts += ["no longer needed: " + ", ".join(gone)] if gone else []
    note = "; ".join(parts)
    if req != cur_req:
        note = "pyo3 %s -> %s (adapt ike-adblock/src/lib.rs if its API changed); %s" % (cur_req, req, note)
    return {"current": "pyo3 %s, %d crates" % (old.get("pyo3", cur_req), len(old)),
            "latest": "pyo3 %s, %d crates" % (new.get("pyo3", req), len(new)),
            "update": bool(changed or added or gone or req != cur_req), "note": note[:900],
            "_requirement": req}


def apply_crates(root, info):
    manifest = root / "ike-adblock" / "Cargo.toml"
    manifest.write_text(_with_pyo3(manifest.read_text("utf-8"), info["_requirement"]), "utf-8")
    if not shutil.which("cargo"):
        print("!! cargo not found: run `cargo update` in ike-adblock/")
        return
    run(["cargo", "update", "--manifest-path", str(manifest)])
    tool = root / "tools" / "third-party.py"
    if tool.is_file():          # the credits follow the crates (docs/THIRD-PARTY.md)
        done = subprocess.run([sys.executable, str(tool)], capture_output=True, text=True)
        if done.returncode != 0:
            print("!! docs/THIRD-PARTY.md not updated: run tools/third-party.py")


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


# --- Dark Reader ---------------------------------------------------------------

def darkreader_lists_hash(data):
    lists = {k: data[k] for k in ("fixes", "dark_sites", "detector_hints")}
    return hashlib.sha256(json.dumps(lists, sort_keys=True).encode("utf-8")).hexdigest()


def npm_tarball(meta):
    """The package's tarball, from npm's own registry and with the hash npm
    published for it (review 2 of 1.1.19, L1: neither was checked)."""
    import base64
    url = meta["dist"]["tarball"]
    if not url.startswith("https://registry.npmjs.org/"):
        raise ValueError("the tarball is not on npm's registry: %s" % url[:120])
    integrity = meta["dist"].get("integrity", "")
    if not integrity.startswith("sha512-"):
        raise ValueError("npm gives no sha512 for the tarball")
    data = fetch(url)
    if base64.b64encode(hashlib.sha512(data).digest()).decode() != integrity[7:]:
        raise ValueError("the tarball does not match the hash npm published")
    return data


def build_darkreader(root, work, dr_src=None):
    """Dark Reader's newest engine (npm) and lists (GitHub), built as I.K.E. uses them."""
    import tarfile
    out = work / "darkreader-out"
    out.mkdir(parents=True, exist_ok=True)
    meta = json.loads(fetch(DARKREADER_NPM))
    tgz = work / "darkreader.tgz"
    tgz.write_bytes(npm_tarball(meta))
    with tarfile.open(tgz) as tar:
        member = tar.getmember("package/darkreader.js")
        (work / "darkreader.js").write_bytes(tar.extractfile(member).read())
    src = work / "darkreader-src"
    if dr_src:
        src = Path(dr_src)
    elif not src.exists():
        run(["git", "clone", "--quiet", "--depth", "1", DARKREADER_GIT, str(src)])
    commit = run(["git", "-C", str(src), "log", "-1", "--format=%H"]).strip()
    date = run(["git", "-C", str(src), "log", "-1", "--format=%cs"]).strip()
    run([sys.executable, str(root / "tools" / "build-darkreader.py"), "--lib", str(work / "darkreader.js"),
         "--config", str(src / "src" / "config"), "--commit", commit, "--date", date, "--out", str(out)])
    return out


def check_darkreader(root, work, dr_src=None):
    cur = json.loads((root / "ike" / "resources" / "darkreader-data.json").read_text("utf-8"))
    out = build_darkreader(root, work, dr_src)
    new = json.loads((out / "darkreader-data.json").read_text("utf-8"))
    engine = vkey(new["version"]) > vkey(cur["version"])
    lists = darkreader_lists_hash(cur) != darkreader_lists_hash(new)
    note = ", ".join(x for x, on in (("new engine", engine), ("lists changed", lists)) if on)
    return {"current": "%s, lists %s (%s)" % (cur["version"], cur.get("lists_commit", "")[:10], cur.get("lists_date", "")),
            "latest": "%s, lists %s (%s)" % (new["version"], new["lists_commit"][:10], new["lists_date"]),
            "update": engine or lists, "note": note, "_dir": str(out)}


def apply_darkreader(root, info):
    for name in ("darkreader.js", "darkreader-proxy.js", "darkreader-data.json"):
        shutil.copyfile(Path(info["_dir"]) / name, root / "ike" / "resources" / name)


# --- Qt WebEngine / PyQt6 of the automatic tests -----------------------------

def read_pins(root):
    pins = {}
    for line in (root / "tools" / "test-requirements.txt").read_text("utf-8").splitlines():
        line = line.split("#")[0].strip()
        if line:
            name, version = line.split("==")
            pins[norm(name)] = (name.strip(), version.strip())
    return pins


def resolve_test_packages():
    """Resolve the newest package set pip installs for this Python."""
    with tempfile.TemporaryDirectory() as tmp:
        report = Path(tmp) / "report.json"
        run([sys.executable, "-m", "pip", "install", "--dry-run", "--ignore-installed", "--quiet",
             "--disable-pip-version-check", "--report", str(report), "--only-binary=:all:",
             *TEST_TOP], env=dict(os.environ, PYTHONNOUSERSITE="1"))
        data = json.loads(report.read_text("utf-8"))
    return {norm(i["metadata"]["name"]): (i["metadata"]["name"], i["metadata"]["version"])
            for i in data["install"]}


def arch_webengine():
    """Version of Arch Linux's qt6-webengine package, or "" if unknown."""
    try:
        data = json.loads(fetch(ARCH_PACKAGE, timeout=30).decode("utf-8"))
        return next(r["pkgver"] for r in data["results"] if r["pkgname"] == "qt6-webengine")
    except Exception:
        return ""


def check_test_packages(root):
    pins, new = read_pins(root), resolve_test_packages()
    qt = [n for n in QT_PACKAGES if n in new and (n not in pins or new[n][1] != pins[n][1])]
    other = [n for n in new if n not in QT_PACKAGES and (n not in pins or new[n][1] != pins[n][1])]
    gone = [n for n in pins if n not in new]

    def show(names):
        return ", ".join("%s %s -> %s" % (new[n][0], pins[n][1] if n in pins else "-", new[n][1])
                         for n in names)

    def label(s):
        return "Qt %s, WebEngine wheel %s" % (s.get("pyqt6-qt6", ("", "?"))[1],
                                              s.get("pyqt6-webengine-qt6", ("", "?"))[1])

    arch = arch_webengine()
    note = show(qt)
    if arch:
        note = "; ".join(x for x in (note, "Arch Linux qt6-webengine %s" % arch) if x)
    return {"current": label(pins), "latest": label(new),
            "update": bool(qt), "note": note,
            "also": "; ".join(x for x in (show(other), ("no longer needed: " + ", ".join(gone)) if gone else "")
                              if x),
            "_set": new}


def apply_test_packages(root, info):
    pins, new = read_pins(root), info["_set"]
    path = root / "tools" / "test-requirements.txt"
    header = [line for line in path.read_text("utf-8").splitlines() if line.startswith("#")]
    order = list(pins) + sorted(n for n in new if n not in pins)
    lines = ["%s==%s" % (pins[n][0] if n in pins else new[n][0], new[n][1]) for n in order if n in new]
    path.write_text("\n".join(header + lines) + "\n", "utf-8")


# --- report -----------------------------------------------------------------

def check_all(root, ubo_src=None, work=None, dr_src=None):
    work = Path(work or tempfile.mkdtemp(prefix="ike-check-"))
    work.mkdir(parents=True, exist_ok=True)
    checks = [
        ("adblock-rust (AdBlock engine)", check_adblock, apply_adblock, ()),
        ("Rust crates of the AdBlock engine", check_crates, apply_crates, ()),
        ("uBlock Origin scriptlets", check_scriptlets, apply_scriptlets, (work, ubo_src)),
        ("Dark Reader (engine and lists)", check_darkreader, apply_darkreader, (work, dr_src)),
        ("Qt WebEngine / PyQt6 (tests)", check_test_packages, apply_test_packages, ()),
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
    ap.add_argument("--darkreader-src", help="use this Dark Reader checkout instead of cloning it")
    ap.add_argument("--root", default=str(ROOT), help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    root = Path(args.root)
    results = check_all(root, args.ubo_src, dr_src=args.darkreader_src)
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
