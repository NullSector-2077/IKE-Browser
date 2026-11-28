#!/usr/bin/env python3
"""Daily check of the components I.K.E. bundles against their newest releases.

    python3 tools/check-components.py [--json FILE] [--markdown FILE] [--apply] [--ubo-src DIR]

Components and where the version in use is written:

- adblock-rust, the AdBlock engine library: ``ike-adblock/Cargo.toml``
  (newest on crates.io);
- uBlock Origin scriptlets: ``ike/resources/ubo-scriptlets.json`` (rebuilt from
  uBlock Origin's newest sources with tools/build-ubo-scriptlets.mjs; only a
  change in the scriptlets themselves counts, not a new commit);
- Dark Reader's lists (fixes for single sites, sites that are dark already,
  hints of a site's own dark theme): ``ike/resources/darkreader-data.json``
  (rebuilt with tools/build-darkreader-lists.py from the newest commit of Dark
  Reader's repository). Its engine left I.K.E. in 1.1.30. The browser fetches
  the lists itself once a day (ike/darklists.py), so a change of them is a
  weekly candidate only (tools/update-candidates.py, WEEKLY);
- KDE's Breeze icons, the shipped icon set "breeze" (1.1.24):
  ``ike/resources/icons/sets/breeze/`` (rebuilt with tools/build-breeze-icons.py
  from the newest release tag of breeze-icons, only the icons I.K.E. uses;
  only a change of those icons counts, not a new tag);
- every other entry of components.json (the component manifest);
- Qt WebEngine and PyQt6 of the automatic tests: ``tools/test-requirements.txt``
  (the newest set pip would install). The browser itself runs on Arch Linux's
  own qt6-webengine, updated by pacman: its current version is shown in the
  report so the tests can follow it.

Test packages other than Qt (cryptography, certifi, ...) are reported as
"also newer": they do not call for a release on their own, and are taken
along by the next one.

With --arch FILE, also Arch Linux's own packages that I.K.E. runs on and is
built with (qt6-webengine, qt6-base, python, python-pyqt6, ..., rust; see
ARCH_PACKAGES): their versions in Arch's official repositories (core, extra)
against the versions the last green "Arch Linux" run on main really tested
(arch.yml records them in its artifact "arch-versions"; --save-arch-tested
reads it back with GET calls of GitHub's API, nothing is written). A change
means "compatibility to verify": the daily check starts arch.yml on main. It
is never an update to apply, never a release, and never counted in
"updates" or "errors"; an Arch source that cannot be reached is "source
unreachable", never a change. --record-arch FILE is what arch.yml runs to
record the versions it tests.

With --apply the files above are rewritten with the newest versions (and
``cargo update`` is run for a new engine); adapting I.K.E.'s code, building
and testing are handled by the daily GitHub Actions maintenance workflow.

Two kinds of trouble are kept apart (1.1.20, the owner's decision):

- "source unreachable": an upstream source could not be read (the network,
  the site, git, a download's hash). Infrastructure: --apply applies nothing and
  exits 1, the next daily run tries again;
- "builder refused": I.K.E.'s builder of a customised component
  (tools/build-ubo-scriptlets.mjs, tools/build-darkreader-lists.py,
  tools/build-breeze-icons.py) does not accept the new upstream version (the
  library is laid out differently, the lists hold what could be a script). A
  component incompatibility for a person, never the automatic fix's: that
  component stays at the version in use, with I.K.E.'s changes, and the report
  says which step refused, the versions, the upstream lines it concerns and
  the builder's log; the other components are
  still applied (security updates of the crates included) and tested.

With --filter-lists FILE, only the filter lists I.K.E. turns on by default
(ike/config.py DEFAULT_LISTS) are downloaded as I.K.E. downloads them, loaded
into the bundled AdBlock engine (vendor/adblock, built from ike-adblock/) and
read for the scriptlets they use: rules the engine cannot read, and
scriptlet names the bundled uBlock Origin library does not know (I.K.E. drops
those rules silently), are component findings, never a failure of the code;
a list that cannot be downloaded is "unreachable".
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
import time
import urllib.parse
import urllib.request
import zipfile
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CRATES_INDEX = "https://index.crates.io/ad/bl/adblock"
PYO3_INDEX = "https://index.crates.io/py/o3/pyo3"
UBO_GIT = "https://github.com/gorhill/uBlock"
DARKREADER_GIT = "https://github.com/darkreader/darkreader"
ARCH_SEARCH = "https://archlinux.org/packages/search/json/?name=%s"
ARCH_PACKAGE = ARCH_SEARCH % "qt6-webengine"
# Arch Linux's own packages I.K.E. runs on (PKGBUILD depends) and is built with
# (rust, which brings cargo): a new version of any of them reaches users with
# `pacman -Syu`, outside I.K.E.'s releases, so arch.yml tests it first
ARCH_PACKAGES = ("qt6-webengine", "qt6-base", "qt6-webchannel", "qt6-svg", "python-pyqt6",
                 "python-pyqt6-webengine", "python", "python-cryptography", "python-jeepney",
                 "publicsuffix-list", "rust",
                 # 1.1.21-1.1.22: the font allowlist (ike/fontallow.py) reads fontconfig and these fonts
                 "fontconfig", "noto-fonts", "ttf-dejavu",
                 # the widget styles, KDE's theme and the icon test
                 "breeze", "oxygen", "kvantum", "plasma-integration", "breeze-icons",
                 # video
                 "ffmpeg")
ARCH_REPOS = ("core", "extra")             # the official repositories (not the -testing ones)
ARCH_WORKFLOW = "arch.yml"
ARCH_ARTIFACT = "arch-versions"            # the artifact arch.yml keeps, holding ARCH_FILE
ARCH_FILE = "arch-versions.json"
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


class SourceUnreachable(Exception):
    """An upstream source could not be read (the network, the site, git):
    infrastructure, the next run tries again."""


class BuilderRefused(Exception):
    """I.K.E.'s builder of a customised component refused the new upstream
    version: a component incompatibility for a person (1.1.20). `report` holds
    component, current, latest, step, reason, context (the upstream lines
    around the anchor) and log."""

    def __init__(self, report):
        super().__init__(report.get("reason", "the builder refused the new version"))
        self.report = report


def fetch_source(url, timeout=60):
    """fetch(), with a failure to read the source as SourceUnreachable."""
    try:
        return fetch(url, timeout=timeout)
    except OSError as e:          # URLError, HTTPError, timeouts, refused connections
        raise SourceUnreachable("%s: %s" % (url, e)) from e


def clone(url, dest):
    """git clone --depth 1, with a failure as SourceUnreachable."""
    try:
        run(["git", "clone", "--quiet", "--depth", "1", url, str(dest)])
    except (subprocess.CalledProcessError, OSError) as e:
        raise SourceUnreachable("git clone %s: %s" % (url, (getattr(e, "stderr", "") or str(e)).strip()[:300])) from e


def tail(text, lines=60, size=6000):
    """The end of a builder's log."""
    text = (text or "").strip()
    return "\n".join(text.splitlines()[-lines:])[-size:]


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
            "_requirement": req, "_candidates": crate_candidates(root, old, new if req == cur_req else None,
                                                                 cur_req, req)}


# --- one candidate per component (WP5, 2026-11-22) ------------------------------
# The daily maintenance makes one isolated candidate per component, or per
# small coherent group, on automation/update/<id> (tools/update-candidates.py):
# its own tests, Arch run, automatic fix, ledger entry and verified merge.
# The engine's crates give three kinds: "crates" (every semver-compatible
# update, cargo update with the requirements as they are), "pyo3" (a new pyo3
# release line: the requirement is raised) and "crate-major-<name>" (a new major
# version of another direct dependency of ike-adblock: its requirement in
# Cargo.toml is raised, then cargo update; a major version of a crate that only
# adblock brings waits for a new adblock, which is its own candidate). A new
# crate still passes deny.toml's licence and source checks (tests.yml,
# "Licences"). The test packages give three groups: Qt's wheels, the test tools
# (pytest, ruff) and the other libraries.

TEST_TOOLS = ("pytest", "ruff", "pluggy", "iniconfig", "packaging", "pygments", "colorama", "exceptiongroup",
              "tomli")


def test_group(name):
    """The candidate of a test package: test-qt, test-tools or test-libs."""
    name = norm(name)
    if name in QT_PACKAGES or name.startswith("pyqt6"):
        return "test-qt"
    return "test-tools" if name in TEST_TOOLS else "test-libs"


def crate_index_url(name):
    """The sparse index file of a crate on crates.io."""
    n = name.lower()
    path = ("1/%s" % n if len(n) == 1 else "2/%s" % n if len(n) == 2 else "3/%s/%s" % (n[0], n) if len(n) == 3
            else "%s/%s/%s" % (n[:2], n[2:4], n))
    return "https://index.crates.io/" + path


def latest_crate(name):
    """The newest stable, not yanked version of a crate on crates.io (raises when unreachable)."""
    versions = []
    for line in fetch_source(crate_index_url(name)).decode("utf-8").splitlines():
        if line.strip():
            entry = json.loads(line)
            if not entry.get("yanked") and is_stable(entry["vers"]):
                versions.append(entry["vers"])
    return max(versions, key=vkey) if versions else ""


def direct_requirements(root):
    """{crate: requirement} of ike-adblock/Cargo.toml's [dependencies]."""
    text = (root / "ike-adblock" / "Cargo.toml").read_text("utf-8")
    deps = re.search(r"^\[dependencies\]\n(.*?)(?=^\[|\Z)", text, re.M | re.S)
    out = {}
    for line in (deps.group(1) if deps else "").splitlines():
        m = re.match(r'^([A-Za-z0-9_-]+)\s*=\s*(?:"([^"]+)"|\{[^}]*?version\s*=\s*"([^"]+)")', line.strip())
        if m:
            out[m.group(1)] = m.group(2) or m.group(3)
    return out


def crate_candidates(root, old, compatible, cur_req, req):
    """The candidates of the engine's crates: [{"id", "from", "to", "note", "requirement"?}]."""
    out = []
    if compatible is None:
        try:
            compatible = lock_packages(updated_lock(root, cur_req))
        except Exception as e:        # cargo or the index: the combined result above still stands
            compatible = {}
            print("!! the semver-compatible crates could not be read apart: %s" % str(e)[:200])
    changed = sorted(n for n in compatible if n in old and compatible[n] != old[n])
    added = sorted(n for n in compatible if n not in old)
    gone = sorted(n for n in old if compatible and n not in compatible)
    if changed or added or gone:
        parts = ["%s %s -> %s" % (n, old[n], compatible[n]) for n in changed]
        parts += ["new: " + ", ".join(added)] if added else []
        parts += ["no longer needed: " + ", ".join(gone)] if gone else []
        out.append({"id": "crates", "from": "%d crates" % len(old), "to": "%d crates" % len(compatible),
                    "note": "; ".join(parts)[:900]})
    if req != cur_req:
        out.append({"id": "pyo3", "from": cur_req, "to": req, "requirement": req, "crate": "pyo3",
                    "note": "pyo3 %s -> %s: a new release line (adapt ike-adblock/src/lib.rs if its API changed)"
                    % (cur_req, req)})
    for name, creq in sorted(direct_requirements(root).items()):
        if name in ("adblock", "pyo3") or creq.startswith("="):
            continue
        try:
            newest = latest_crate(name)
        except Exception as e:        # unreachable today: no major candidate, said in the note
            out.append({"id": "crate-major-%s" % name, "from": creq, "to": "", "error": str(e)[:200]})
            continue
        line = pyo3_requirement(creq, newest) if newest else creq
        if line != creq:
            out.append({"id": "crate-major-%s" % name, "from": creq, "to": line, "requirement": line,
                        "crate": name, "note": "%s %s -> %s: a new major version (the requirement in Cargo.toml "
                        "is raised; I.K.E.'s wrapper may need to adapt)" % (name, creq, line)})
    return out


def apply_compatible_crates(root, info):
    """cargo update with the requirements as they are (adblock stays at its exact version)."""
    manifest = root / "ike-adblock" / "Cargo.toml"
    if not shutil.which("cargo"):
        print("!! cargo not found: run `cargo update` in ike-adblock/")
        return
    run(["cargo", "update", "--manifest-path", str(manifest)])


def apply_requirement(root, crate, requirement):
    """A new major version of a direct dependency: its requirement in Cargo.toml raised, then
    cargo update of that crate (all of them when cargo cannot move it alone)."""
    manifest = root / "ike-adblock" / "Cargo.toml"
    text = manifest.read_text("utf-8")
    new, n = re.subn(r'^(%s = (?:\{ version = )?")[^"]+"' % re.escape(crate), r"\g<1>" + requirement + '"', text,
                     count=1, flags=re.M)
    if n != 1:
        raise ValueError("%s: its requirement is not in ike-adblock/Cargo.toml" % crate)
    manifest.write_text(new, "utf-8")
    if not shutil.which("cargo"):
        print("!! cargo not found: run `cargo update -p %s` in ike-adblock/" % crate)
        return
    try:
        run(["cargo", "update", "-p", crate, "--manifest-path", str(manifest)])
    except subprocess.CalledProcessError:
        run(["cargo", "update", "--manifest-path", str(manifest)])


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


UBO_LIBRARY = "src/js/resources/scriptlets.js"      # what tools/build-ubo-scriptlets.mjs imports


def ubo_refused(root, src, reason, log=""):
    """BuilderRefused for uBlock Origin's scriptlets, with what the new
    checkout has where the builder looks (UBO_LIBRARY and its exports)."""
    cur = json.loads((root / "ike" / "resources" / "ubo-scriptlets.json").read_text("utf-8"))
    try:
        commit = run(["git", "-C", str(src), "log", "-1", "--format=%H %cs"]).split()
    except Exception:
        commit = ["?", ""]
    lib = src / UBO_LIBRARY
    if lib.is_file():
        text = lib.read_text("utf-8", "replace")
        exports = [line.strip()[:160] for line in text.splitlines() if line.lstrip().startswith("export ")]
        context = "%s (%d lines); its exports:\n%s" % (UBO_LIBRARY, text.count("\n") + 1,
                                                       "\n".join("    " + e for e in exports[:20]) or "    (none)")
    else:
        near = sorted(p.name for p in lib.parent.glob("*.js"))[:30] if lib.parent.is_dir() else []
        context = "%s is not in the new version; %s" % (
            UBO_LIBRARY, ("next to it: " + ", ".join(near)) if near else "its folder is not there either")
    return BuilderRefused({
        "component": "uBlock Origin scriptlets",
        "current": "%s (%s)" % (cur["commit"][:10], cur["date"]),
        "latest": "%s (%s)" % (commit[0][:10], commit[1] if len(commit) > 1 else ""),
        "step": "tools/build-ubo-scriptlets.mjs (uBlock Origin's builtinScriptlets read with Node.js)",
        "reason": reason, "context": context, "log": tail(log)})


def build_scriptlets(root, work, ubo_src=None):
    src = work / "src"
    if ubo_src:
        os.symlink(Path(ubo_src).resolve(), src)
    else:
        clone(UBO_GIT, src)
    try:
        done = subprocess.run(["node", str(root / "tools" / "build-ubo-scriptlets.mjs")], cwd=work,
                              capture_output=True, text=True, check=False)
    except OSError as e:          # no Node.js on this machine: not uBlock Origin's change
        raise RuntimeError("Node.js could not be started: %s" % e) from e
    if done.returncode != 0:
        lines = [x for x in done.stderr.splitlines() if x.strip()]
        why = next((x.strip() for x in lines if re.match(r"^\w*Error\b|^Error \[", x.strip())),
                   lines[-1].strip() if lines else "exit %d" % done.returncode)
        raise ubo_refused(root, src, "the builder stopped: %s" % why[:300], done.stdout + done.stderr)
    built = work / "ubo-scriptlets.json"
    try:
        data = json.loads(built.read_text("utf-8"))
    except (OSError, ValueError) as e:
        raise ubo_refused(root, src, "the builder wrote no readable library (%s)" % e, done.stdout + done.stderr)
    entries = data.get("scriptlets") or {}
    missing = sorted({d for e in entries.values() for d in e.get("deps", ()) if d not in entries})
    if not entries or not any(n.endswith(".js") for n in entries):
        raise ubo_refused(root, src, "the builder found no scriptlets in the new version", done.stdout + done.stderr)
    if missing:
        raise ubo_refused(root, src, "scriptlets of the new version depend on entries it does not have: %s"
                          % ", ".join(missing[:10]), done.stdout + done.stderr)
    return built


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


# --- Dark Reader's lists (its engine left I.K.E. in 1.1.30) --------------------

def darkreader_lists_hash(data):
    lists = {k: data[k] for k in ("fixes", "dark_sites", "detector_hints")}
    return hashlib.sha256(json.dumps(lists, sort_keys=True).encode("utf-8")).hexdigest()


def darkreader_refused(root, src, reason, log):
    """BuilderRefused for Dark Reader's lists: the step that refused and, for the site fixes, the
    first lines of the new list."""
    try:
        cur = json.loads((root / "ike" / "resources" / "darkreader-data.json").read_text("utf-8"))
        current = "%s, lists %s" % (cur["version"], cur.get("lists_commit", "")[:10])
    except (OSError, ValueError, KeyError):
        current = "?"
    lists, context = "", ""
    try:
        lists = run(["git", "-C", str(src), "log", "-1", "--format=%h"]).strip()
    except Exception:
        pass
    step = "tools/build-darkreader-lists.py"
    if "could be a script" in (log or ""):
        step = "tools/build-darkreader-lists.py, the lists' content (DATA_SCRIPT_MARKS of ike/darklists.py)"
    elif "common fix" in (log or ""):
        step = "tools/build-darkreader-lists.py, the site fixes list (dynamic-theme-fixes.config)"
        fixes = Path(src) / "src" / "config" / "dynamic-theme-fixes.config"
        if fixes.is_file():
            context = "\n".join(fixes.read_text("utf-8", "replace").splitlines()[:15])
    elif "entries where I.K.E. came with" in (log or ""):
        step = "tools/build-darkreader-lists.py, a list much shorter than the copy in use (MIN_SHARE)"
    return BuilderRefused({"component": "Dark Reader (lists)", "current": current,
                           "latest": "lists %s" % (lists or "?"), "step": step, "reason": reason,
                           "context": context, "log": tail(log)})


def build_darkreader(root, work, dr_src=None):
    """Dark Reader's newest lists (its repository on GitHub), built as I.K.E. ships them."""
    out = work / "darkreader-out"
    out.mkdir(parents=True, exist_ok=True)
    src = work / "darkreader-src"
    if dr_src:
        src = Path(dr_src)
    elif not src.exists():
        clone(DARKREADER_GIT, src)
    commit = run(["git", "-C", str(src), "log", "-1", "--format=%H"]).strip()
    date = run(["git", "-C", str(src), "log", "-1", "--format=%cs"]).strip()
    done = subprocess.run([sys.executable, str(root / "tools" / "build-darkreader-lists.py"), "--src", str(src),
                           "--commit", commit, "--date", date, "--out", str(out),
                           "--bundled", str(root / "ike" / "resources" / "darkreader-data.json")],
                          capture_output=True, text=True, check=False)
    if done.returncode != 0:
        log = done.stdout + done.stderr
        lines = [x.strip() for x in done.stderr.splitlines() if x.strip()]
        raise darkreader_refused(root, src, "the builder stopped: %s"
                                 % (lines[-1] if lines else "exit %d" % done.returncode)[:300], log)
    return out


def check_darkreader(root, work, dr_src=None):
    """1.1.30: Dark Reader's engine is gone, its lists are the whole component. The browser fetches
    them itself once a day, without GitHub's automation (ike/darklists.py, 1.1.27, the owner's decision: no
    new version for simple lists), so a change of the lists makes NO candidate: it is only noted. The copy
    I.K.E. comes with is the first start's fallback; the builder still checks every day that the lists
    parse and hold nothing that looks like a script (a refusal is reported)."""
    cur = json.loads((root / "ike" / "resources" / "darkreader-data.json").read_text("utf-8"))
    out = build_darkreader(root, work, dr_src)
    new = json.loads((out / "darkreader-data.json").read_text("utf-8"))
    lists = darkreader_lists_hash(cur) != darkreader_lists_hash(new)
    version = vkey(new["version"]) > vkey(cur["version"])
    note = ", ".join(x for x, on in (("lists changed", lists), ("Dark Reader %s" % new["version"], version)) if on)
    return {"current": "%s, lists %s (%s)" % (cur["version"], cur.get("lists_commit", "")[:10], cur.get("lists_date", "")),
            "latest": "%s, lists %s (%s)" % (new["version"], new["lists_commit"][:10], new["lists_date"]),
            "update": False, "note": (note + " (the browser fetches them itself)") if note else "",
            "_dir": str(out)}


def apply_darkreader(root, info):
    shutil.copyfile(Path(info["_dir"]) / "darkreader-data.json", root / "ike" / "resources" / "darkreader-data.json")


# --- KDE's Breeze icons (the shipped icon set "breeze", 1.1.24) ------------------

BREEZE_ID = "breeze-icons"
BREEZE_GIT = "https://github.com/KDE/breeze-icons"
BREEZE_RECORD = "ike/resources/icons/sets/breeze/breeze-icons.json"


def breeze_tool(root):
    """tools/build-breeze-icons.py as a module (build, write, Refused)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("build_breeze_icons", Path(root) / "tools" / "build-breeze-icons.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def breeze_refused(cur, latest, reason, step="tools/build-breeze-icons.py"):
    return BuilderRefused({"component": "Breeze icons (KDE)", "current": cur, "latest": latest, "step": step,
                           "reason": reason, "context": "", "log": ""})


def check_breeze_icons(root, work, src=None, tags=None):
    """The newest release tag of breeze-icons, built as I.K.E. ships it. Only a change of the icons
    themselves (or of Breeze's licence notice) counts, not a new tag; an icon the set has that the
    new release no longer gives is a refusal (the set stays at the version in use)."""
    root, work = Path(root), Path(work)
    mf = _manifest()
    tool = breeze_tool(root)
    cur = json.loads((root / BREEZE_RECORD).read_text("utf-8"))
    current = "%s (%s)" % (cur["version"], cur["commit"][:10])
    entry = mf.components(root).get(BREEZE_ID) or {"upstream": {"git": BREEZE_GIT, "tag": "v*"}}
    if src:
        checkout = Path(src)
        tag = run(["git", "-C", str(checkout), "describe", "--tags", "--exact-match"]).strip()
        version = tag.lstrip("v")
    else:
        try:
            version, tag = mf.latest(entry, tags=tags or mf.git_tags)
        except (OSError, subprocess.SubprocessError) as e:
            raise SourceUnreachable("breeze-icons tags: %s" % e) from e
        if vkey(version) <= vkey(cur["version"]):
            return {"current": current, "latest": version, "update": False, "note": ""}
        checkout = work / "breeze-icons-src"
        if not checkout.exists():
            try:
                run(["git", "clone", "--quiet", "--depth", "1", "--branch", tag, entry["upstream"]["git"],
                     str(checkout)])
            except (subprocess.CalledProcessError, OSError) as e:
                raise SourceUnreachable("git clone %s %s: %s" % (entry["upstream"]["git"], tag, (
                    getattr(e, "stderr", "") or str(e)).strip()[:300])) from e
    try:
        files = tool.build(checkout, root, tag=tag)
    except tool.Refused as e:
        raise breeze_refused(current, version, str(e)) from None
    new = json.loads(files[BREEZE_RECORD])
    latest = "%s (%s)" % (new["version"], new["commit"][:10])
    lost = sorted(set(cur["icons"]) - set(new["icons"]))
    if lost:
        raise breeze_refused(current, latest,
                             "icons the set has are not in the new release (renamed or removed upstream): %s; a "
                             "Breeze name for each goes into ALIASES" % ", ".join(lost[:12]),
                             "tools/build-breeze-icons.py, the icons' names (ALIASES)")
    old_icons = {p.name: p.read_text("utf-8") for p in (root / BREEZE_RECORD).parent.glob("*.svg")}
    new_icons = {Path(rel).name: text for rel, text in files.items() if rel.endswith(".svg")}
    changed = sorted(n for n in new_icons if n in old_icons and new_icons[n] != old_icons[n])
    added = sorted(n for n in new_icons if n not in old_icons)
    removed = sorted(n for n in old_icons if n not in new_icons)
    licence = root / tool.LICENCE
    notice = files[tool.LICENCE].split("\n--- %s ---\n" % tool.COPYING, 1)[-1]
    licence_changed = not licence.is_file() or notice not in licence.read_text("utf-8")
    note = ", ".join(x for x in ("%d changed, %d new, %d removed" % (len(changed), len(added), len(removed))
                                 if changed or added or removed else "",
                                 "licence notice changed" if licence_changed else "") if x)
    return {"current": current, "latest": latest, "update": bool(changed or added or removed or licence_changed),
            "note": note, "_files": files}


def apply_breeze_icons(root, info):
    breeze_tool(root).write(info["_files"], root)


# components of the manifest built by a builder of I.K.E.'s (not a plain download), besides Dark
# Reader and uBlock Origin's scriptlets: their check runs when components.json declares them
MANIFEST_BUILDS = {BREEZE_ID: (check_breeze_icons, apply_breeze_icons)}


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
    groups = {}
    for n in [*qt, *other, *gone]:
        groups.setdefault(test_group(n), []).append(n)
    cands = [{"id": g, "from": ", ".join("%s %s" % (pins[n][0], pins[n][1]) for n in names if n in pins)[:300],
              "to": ", ".join("%s %s" % (new[n][0], new[n][1]) for n in names if n in new)[:300],
              "note": show([n for n in names if n in new]) or ("no longer needed: " + ", ".join(names))}
             for g, names in sorted(groups.items())]
    return {"current": label(pins), "latest": label(new),
            "update": bool(qt), "note": note,
            "also": "; ".join(x for x in (show(other), ("no longer needed: " + ", ".join(gone)) if gone else "")
                              if x),
            "_set": new, "_candidates": cands}


def apply_test_packages(root, info):
    pins, new = read_pins(root), info["_set"]
    path = root / "tools" / "test-requirements.txt"
    header = [line for line in path.read_text("utf-8").splitlines() if line.startswith("#")]
    order = list(pins) + sorted(n for n in new if n not in pins)
    lines = ["%s==%s" % (pins[n][0] if n in pins else new[n][0], new[n][1]) for n in order if n in new]
    path.write_text("\n".join(header + lines) + "\n", "utf-8")


def apply_test_group(root, info, group):
    """Only the pins of one group (test_group) move; the others stay as they are."""
    pins, new = read_pins(root), info["_set"]
    path = root / "tools" / "test-requirements.txt"
    header = [line for line in path.read_text("utf-8").splitlines() if line.startswith("#")]
    out = []
    for n in list(pins) + sorted(n for n in new if n not in pins):
        if test_group(n) != group:
            if n in pins:
                out.append("%s==%s" % pins[n])
        elif n in new:
            out.append("%s==%s" % (pins[n][0] if n in pins else new[n][0], new[n][1]))
    path.write_text("\n".join(header + out) + "\n", "utf-8")


# --- Arch Linux's own packages (the system I.K.E. runs on) ---------------------
# The "Tests" workflow runs on Ubuntu with PyPI's Qt and Python 3.13; users run
# Arch's Python, Qt, PyQt and Qt WebEngine, which pacman updates at any time.
# arch.yml tests I.K.E. on them and records what it tested (--record-arch);
# the daily check compares Arch's repositories with the set of the last green
# run on main and, when it changed, starts arch.yml on main (daily-check.yml).
# Nothing here is applied or released: a failure goes to the automatic fix
# (tools/autofix-plan.py, "Arch Linux").

ARCH_NETWORK_FAILURES = 3      # Arch's site did not answer this many times: the rest is not asked


def arch_full_version(entry):
    """epoch:pkgver-pkgrel, as `pacman -Q` writes it ("6.140.0-1", "1:1.91.0-1")."""
    version = "%s-%s" % (entry["pkgver"], entry["pkgrel"])
    return "%s:%s" % (entry["epoch"], version) if entry.get("epoch") else version


def arch_version(name, get=None):
    """The version of an Arch package in the official repositories (core,
    extra; never a -testing one). Raises when Arch's site cannot be read or
    does not list the package there."""
    data = json.loads((get or fetch)(ARCH_SEARCH % urllib.parse.quote(name), timeout=30).decode("utf-8"))
    for entry in data.get("results", []):
        if entry.get("pkgname") == name and entry.get("repo") in ARCH_REPOS:
            return arch_full_version(entry)
    raise LookupError("not in Arch's %s repositories" % " or ".join(ARCH_REPOS))


def arch_current(get=None):
    """({package: version in Arch now}, {package: why it could not be read})."""
    versions, unreachable, down = {}, {}, 0
    for name in ARCH_PACKAGES:
        if down >= ARCH_NETWORK_FAILURES:
            unreachable[name] = "not asked: Arch's site did not answer"
            continue
        try:
            versions[name] = arch_version(name, get)
        except Exception as e:      # the network, Arch's site, an answer it no longer gives
            down += isinstance(e, OSError)
            unreachable[name] = "%s: %s" % (type(e).__name__, str(e).strip()[:200])
    return versions, unreachable


def gh_api(path, raw=False):
    """A GET of GitHub's API through gh (GH_TOKEN of the workflow)."""
    out = subprocess.run(["gh", "api", path], capture_output=True, check=False)
    if out.returncode:
        raise RuntimeError("gh api %s: %s" % (path, out.stderr.decode("utf-8", "replace").strip()[:300]))
    return out.stdout if raw else json.loads(out.stdout)


def arch_record_of_run(repo, run_id, api=None):
    """The versions an arch.yml run recorded (its artifact ARCH_ARTIFACT), or None."""
    api = api or gh_api
    found = api("repos/%s/actions/runs/%s/artifacts?name=%s" % (repo, run_id, ARCH_ARTIFACT))
    for art in found.get("artifacts", []):
        if art.get("name") != ARCH_ARTIFACT or art.get("expired"):
            continue
        data = api("repos/%s/actions/artifacts/%s/zip" % (repo, art["id"]), raw=True)
        try:
            with zipfile.ZipFile(BytesIO(data)) as z:
                if z.getinfo(ARCH_FILE).file_size > 1_000_000:
                    continue
                record = json.loads(z.read(ARCH_FILE).decode("utf-8"))
        except (zipfile.BadZipFile, KeyError, ValueError):
            continue
        if isinstance(record, dict) and isinstance(record.get("packages"), dict):
            return record
    return None


def last_tested_arch(repo, api=None, branch="main", runs=5):
    """The versions the last green arch.yml run on main recorded, with that run
    under "run" ({"id", "url", "sha", "date"}); None when no recent green run
    kept them (runs older than the recording, or artifacts expired)."""
    api = api or gh_api
    data = api("repos/%s/actions/workflows/%s/runs?branch=%s&status=success&per_page=%d"
               % (repo, ARCH_WORKFLOW, branch, runs))
    for run in data.get("workflow_runs", [])[:runs]:
        if run.get("conclusion") != "success" or run.get("head_branch") != branch:
            continue
        record = arch_record_of_run(repo, run["id"], api)
        if record:
            record["run"] = {"id": run["id"], "url": run.get("html_url", ""), "sha": run.get("head_sha", ""),
                             "date": run.get("run_started_at") or run.get("created_at", "")}
            return record
    return None


def save_arch_tested(path, repo, api=None):
    """Write {"tested": <last_tested_arch>} to path; GitHub's errors are kept
    in "error", never raised (the check then starts arch.yml to record anew)."""
    try:
        out = {"tested": last_tested_arch(repo, api)}
    except Exception as e:
        out = {"tested": None, "error": "%s: %s" % (type(e).__name__, str(e).strip()[:300])}
    Path(path).write_text(json.dumps(out, indent=1) + "\n", "utf-8")
    return out


def arch_changes(old, new, skip_not_installed=False):
    """[(package, old version, new version)] for the packages of `new` whose
    version differs from `old` ("" = not recorded or not installed).

    skip_not_installed (the daily check): a package `old` holds as "" was
    recorded as not installed by that run (arch.yml does not install it yet):
    it was not tested, and Arch's version of it is no change to verify, or
    every daily check would start arch.yml again for it. A package `old` does
    not hold at all (newly followed) is still a change: one run records it."""
    names = [n for n in ARCH_PACKAGES if n in new] + sorted(n for n in new if n not in ARCH_PACKAGES)
    return [(n, old.get(n, ""), new[n]) for n in names
            if old.get(n, "") != new[n] and not (skip_not_installed and n in old and old[n] == "")]


# --- the full dependency closure (WP10, 2026-11-22) -----------------------------
# Not only the packages I.K.E. names: everything pacman installs for them
# (Mesa, ffmpeg, NSS, ICU, the fonts, the libraries of Qt...). arch.yml
# records the closure it really tested (`pacman -Qi`, followed recursively
# through "Depends On" and "Provides"), and the daily check compares it with
# Arch's repository databases (core, extra; one download each, not one
# question per package): any package of the closure in another version starts
# arch.yml on main.

ARCH_DB = "https://geo.mirror.pkgbuild.com/%s/os/x86_64/%s.db"
ARCH_TESTING_REPOS = ("core-testing", "extra-testing")
ARCH_DB_MAX = 64 * 1024 * 1024


def parse_repo_db(data, dates=False):
    """{package: epoch:pkgver-pkgrel} of a pacman repository database (a tar, gzip, xz or zstd); with dates,
    {package: (version, build time in seconds since 1970 or 0)}."""
    import io
    import tarfile
    raw = data
    if raw[:4] == b"\x28\xb5\x2f\xfd":                     # zstd: Python's tarfile reads it from 3.14 only
        if shutil.which("zstd"):
            raw = subprocess.run(["zstd", "-dc"], input=data, capture_output=True, check=True).stdout
        else:
            raise ValueError("a zstd database and no zstd to read it")
    out = {}
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:*") as tar:
        for member in tar:
            if not member.isfile() or not member.name.endswith("/desc") or member.size > 1_000_000:
                continue
            text = tar.extractfile(member).read().decode("utf-8", "replace")
            fields = dict(re.findall(r"%([A-Z0-9]+)%\n([^\n]*)", text))
            if fields.get("NAME") and fields.get("VERSION"):
                if dates:
                    built = fields.get("BUILDDATE", "")
                    out[fields["NAME"]] = (fields["VERSION"], int(built) if built.isdigit() else 0)
                else:
                    out[fields["NAME"]] = fields["VERSION"]
    return out


# AUTOMAT block 2 (2026-11-27): Arch's [testing] every day, not only on Wednesdays. A package of the closure
# I.K.E. was tested with that entered [core-testing] or [extra-testing] in the last ARCH_TESTING_HOURS starts
# arch-testing.yml (daily-check.yml, job start-arch-testing): the break is found before Arch moves it to the
# users. The build time of the package is the database's own (%BUILDDATE%): no state is kept.
ARCH_TESTING_HOURS = 30


def arch_testing_news(tested, get=None, now=None, hours=ARCH_TESTING_HOURS):
    """([(package, version in testing)], {repo: error}): the packages of the tested closure (and the packages
    I.K.E. names) built into Arch's testing repositories in the last `hours`."""
    names = set(((tested or {}).get("closure") or {})) | set(((tested or {}).get("packages") or {}))
    now = now or time.time()
    news, errors = [], {}
    for repo in ARCH_TESTING_REPOS:
        try:
            data = (get or fetch)(ARCH_DB % (repo, repo), timeout=120)
            if len(data) > ARCH_DB_MAX:
                raise ValueError("too big")
            for name, (version, built) in parse_repo_db(data, dates=True).items():
                if name in names and built and now - built <= hours * 3600:
                    news.append((name, version))
        except Exception as e:        # the mirror, the network: never a change
            errors[repo] = "%s: %s" % (type(e).__name__, str(e).strip()[:200])
    return sorted(set(news)), errors


def arch_repo_versions(repos=ARCH_REPOS, get=None):
    """({package: version} of Arch's repositories now, {repo: why it could not be read})."""
    versions, errors = {}, {}
    for repo in repos:
        try:
            data = (get or fetch)(ARCH_DB % (repo, repo), timeout=120)
            if len(data) > ARCH_DB_MAX:
                raise ValueError("too big")
            versions.update(parse_repo_db(data))
        except Exception as e:        # the mirror, the network: source unreachable, never a change
            errors[repo] = "%s: %s" % (type(e).__name__, str(e).strip()[:200])
    return versions, errors


def parse_pacman_qi(text):
    """{name: {"version", "depends", "provides"}} of `pacman -Qi` (every installed package)."""
    out = {}
    for block in re.split(r"\n\s*\n", text or ""):
        fields, key = {}, None
        for line in block.splitlines():
            m = re.match(r"^([A-Z][A-Za-z ]+?)\s+:\s?(.*)$", line)
            if m:
                key = m.group(1).strip()
                fields[key] = m.group(2).strip()
            elif key and line.startswith(" "):
                fields[key] += " " + line.strip()
        name = fields.get("Name")
        if not name:
            continue

        def names(value):
            if not value or value == "None":
                return []
            return [re.split(r"[<>=:]", w, maxsplit=1)[0] for w in value.split()]
        out[name] = {"version": fields.get("Version", ""), "depends": names(fields.get("Depends On")),
                     "provides": names(fields.get("Provides"))}
    return out


def dependency_closure(roots, installed):
    """{package: version} of every installed package the roots need, recursively (a dependency
    named by something a package provides is that package)."""
    provider = {}
    for name, info in installed.items():
        for p in info["provides"]:
            provider.setdefault(p, name)
    out, todo = {}, list(roots)
    while todo:
        want = todo.pop()
        name = want if want in installed else provider.get(want)
        if not name or name in out:
            continue
        out[name] = installed[name]["version"]
        todo.extend(installed[name]["depends"])
    return dict(sorted(out.items()))


def closure_roots(root=ROOT):
    """The packages the closure starts from: ARCH_PACKAGES and the PKGBUILD's depends, makedepends
    and optdepends (an optional one counts when it is installed)."""
    names = list(ARCH_PACKAGES)
    try:
        text = (Path(root) / "PKGBUILD").read_text("utf-8")
    except OSError:
        return names
    for key in ("depends", "makedepends", "optdepends"):
        m = re.search(r"^%s=\(" % key, text, re.M)
        words, quote, word = [], "", ""
        for ch in text[m.end():] if m else "":
            if quote:
                quote, word = ("", word) if ch == quote else (quote, word + ch)
            elif ch in "'\"":
                quote = ch
            elif ch.isspace() or ch == ")":
                if word:
                    words.append(word)
                word = ""
                if ch == ")":
                    break
            else:
                word += ch
        for w in words:
            name = re.split(r"[<>=:]", w.strip(), maxsplit=1)[0].strip()
            if name and not name.startswith("#") and name not in names:
                names.append(name)
    return names


def closure_changes(tested, current):
    """[(package, tested, now)] of the recorded closure whose version in Arch differs (a package Arch
    no longer has is not a change: its dependants changed, and they are listed)."""
    return [(n, v, current[n]) for n, v in sorted((tested or {}).items()) if n in current and current[n] != v]


def check_arch(saved, get=None, db=None):
    """Arch's repositories against the set saved by --save-arch-tested.

    state: "changed" (a package moved: compatibility to verify), "untested"
    (no green run on main recorded a set: verify), "unreachable" (Arch's site
    could not be read for some package and nothing else changed: no news, never
    an update), "same". db: ({package: version} of Arch's repository databases,
    {repo: error}) to compare the recorded closure too (WP10); None: not compared."""
    tested = saved.get("tested") if isinstance(saved, dict) else None
    current, unreachable = arch_current(get)
    changed = arch_changes((tested or {}).get("packages", {}), current, skip_not_installed=True) if tested else []
    closure, closure_errors = [], {}
    if db is not None:
        versions, closure_errors = db
        closure = closure_changes((tested or {}).get("closure") or {}, versions) if tested else []
    if not tested:
        state = "untested"
    elif changed or closure:
        state = "changed"
    elif unreachable or closure_errors:
        state = "unreachable"
    else:
        state = "same"
    return {"state": state, "current": current, "unreachable": unreachable, "tested": tested,
            "changed": changed, "closure_changed": closure, "closure_errors": closure_errors,
            "closure_size": len((tested or {}).get("closure") or {}),
            "read_error": (saved or {}).get("error", "") if isinstance(saved, dict) else ""}


def arch_public(info):
    tested = info["tested"] or {}
    return {"state": info["state"], "current": info["current"], "unreachable": info["unreachable"],
            "testing_news": [{"package": n, "testing": v} for n, v in info.get("testing_news", [])],
            "changed": [{"package": n, "tested": o, "now": v} for n, o, v in info["changed"]],
            "closure_changed": [{"package": n, "tested": o, "now": v} for n, o, v in info.get("closure_changed", [])],
            "closure_size": info.get("closure_size", 0), "closure_errors": info.get("closure_errors", {}),
            "tested": {k: tested.get(k) for k in ("packages", "python", "qt", "pyqt", "chromium", "commit", "run")
                       if k in tested},
            "read_error": info["read_error"]}


def _v(text):
    return (text or "-").replace("|", "\\|")


def arch_markdown(info):
    """The Arch section of the report: what Arch has now, what was really
    tested on main, and what that means."""
    tested = info["tested"] or {}
    run = tested.get("run") or {}
    head = {
        "changed": "**Arch changed: compatibility to verify.** The \"Arch Linux\" tests (arch.yml) start on "
                   "`main` with Arch's new packages; a failure there goes to the automatic fix. Not a release by "
                   "itself.",
        "untested": "**No green \"Arch Linux\" run on `main` has recorded the versions it tested yet**: the "
                    "\"Arch Linux\" tests start on `main` to record them.",
        "unreachable": "**Arch's site could not be read for some packages (source unreachable)**; the others are "
                       "the versions already tested. Nothing to verify today.",
        "same": "Arch's packages are the versions the last green \"Arch Linux\" run on `main` tested.",
    }[info["state"]]
    out = ["", "### Arch Linux's own packages", "", head, ""]
    if info.get("testing_news"):
        out += ["**Arch [testing] has new versions of packages I.K.E. was tested with** (built in the last %d hours): "
                "%s. \"Arch Linux (testing)\" starts on `main` to try them before they reach the users."
                % (ARCH_TESTING_HOURS, ", ".join("%s %s" % (n, _v(v)) for n, v in info["testing_news"][:20])), ""]
    if run:
        out.append("Really tested: run [%s](%s) on commit `%s` (%s): Python %s, Qt %s, PyQt %s, Chromium %s "
                   "(as I.K.E. reports it)." % (run.get("id", "?"), run.get("url", ""), str(run.get("sha", ""))[:10],
                                                str(run.get("date", ""))[:16].replace("T", " "),
                                                tested.get("python", "?"), tested.get("qt", "?"),
                                                tested.get("pyqt", "?"), tested.get("chromium", "?")))
        out.append("")
    if info["read_error"]:
        out += ["The tested versions could not be read from GitHub: %s" % _v(info["read_error"]), ""]
    old = tested.get("packages", {})
    moved = {c[0] for c in info["changed"]}
    out.append("| Package | In Arch now | Last tested on main | Changed |\n|---|---|---|---|")
    for name in ARCH_PACKAGES:
        now = info["current"].get(name)
        if now is None:
            now, flag = "source unreachable", "?"
        else:
            flag = "**yes**" if name in moved else ("no" if info["tested"] else "?")
        tested_as = old.get(name, "")
        if info["tested"] and name in old and tested_as == "":
            tested_as, flag = "not installed by arch.yml: **not verified**", "-"
        out.append("| %s | %s | %s | %s |" % (name, _v(now), _v(tested_as), flag))
    why = sorted(set(info["unreachable"].values()))
    if why:
        out += ["", "Source unreachable: " + "; ".join(_v(w) for w in why[:3])]
    closure = info.get("closure_changed") or []
    if info.get("closure_size") or closure:
        out += ["", "**The whole dependency closure** (%d packages arch.yml installed and recorded, Mesa, ffmpeg, "
                "NSS, ICU and the fonts included): %s" % (
                    info.get("closure_size", 0), "%d in another version in Arch now" % len(closure) if closure
                    else "every one the version tested")]
        if closure:
            out += ["", "| Package | Tested | In Arch now |", "|---|---|---|"]
            out += ["| %s | %s | %s |" % (n, _v(o), _v(v)) for n, o, v in closure[:60]]
            if len(closure) > 60:
                out.append("| ... | %d more | |" % (len(closure) - 60))
    elif info["tested"]:
        out += ["", "The run tested on main recorded no dependency closure yet: the next arch.yml run records it."]
    if info.get("closure_errors"):
        out += ["", "Arch's repository databases not read (source unreachable): " +
                "; ".join("%s: %s" % (r, _v(w)) for r, w in sorted(info["closure_errors"].items()))]
    return "\n".join(out) + "\n"


ARCH_PROBE = r"""
import json, platform
out = {"python": platform.python_version()}
try:
    from PyQt6.QtCore import PYQT_VERSION_STR, QT_VERSION_STR
    out["qt"], out["pyqt"] = QT_VERSION_STR, PYQT_VERSION_STR
    from PyQt6.QtWebEngineCore import qWebEngineChromiumVersion
    out["chromium"] = qWebEngineChromiumVersion()
except Exception as e:
    out["error"] = "%s: %s" % (type(e).__name__, e)
try:
    from ike.chromever import engine_full      # what I.K.E. presents to sites (1.1.14)
    out["chromium"] = engine_full()
except Exception as e:
    out.setdefault("error", "%s: %s" % (type(e).__name__, e))
print(json.dumps(out))
"""


def record_arch(path, root=ROOT, query=None, probe=None, qi=None):
    """What this Arch system really has (arch.yml, after installing Arch's
    packages): `pacman -Q` of ARCH_PACKAGES, and Python, Qt, PyQt and the
    engine's Chromium as I.K.E. reports them. Writes the JSON to path and
    returns the Markdown for the run's summary; never fails the run (what
    cannot be read is recorded empty)."""
    def pacman():
        done = subprocess.run(["pacman", "-Q", *ARCH_PACKAGES], capture_output=True, text=True, check=False)
        return done.stdout

    def python():
        done = subprocess.run([sys.executable, "-c", ARCH_PROBE], capture_output=True, text=True, check=False,
                              cwd=str(root), timeout=300)
        return done.stdout.strip().splitlines()[-1] if done.stdout.strip() else "{}"
    installed = {}
    try:
        for line in (query or pacman)().splitlines():
            parts = line.split()
            if len(parts) == 2:
                installed[parts[0]] = parts[1]
    except Exception:
        pass
    try:
        facts = json.loads((probe or python)())
    except Exception as e:
        facts = {"error": "%s: %s" % (type(e).__name__, e)}
    record = {"schema": 1, "packages": {n: installed.get(n, "") for n in ARCH_PACKAGES}}

    def pacman_qi():
        return subprocess.run(["pacman", "-Qi"], capture_output=True, text=True, check=False).stdout
    try:
        # WP10: the whole closure the run installed, recursively (pacman -Qi of every package)
        record["closure"] = dependency_closure(closure_roots(root), parse_pacman_qi((qi or pacman_qi)()))
    except Exception as e:
        record["closure"] = {}
        record["closure_error"] = "%s: %s" % (type(e).__name__, str(e)[:200])
    for key in ("python", "qt", "pyqt", "chromium", "error"):
        if facts.get(key):
            record[key] = str(facts[key])[:300]
    record.update(commit=os.environ.get("GITHUB_SHA", ""), run=os.environ.get("GITHUB_RUN_ID", ""),
                  date=datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(record, indent=1) + "\n", "utf-8")
    lines = ["### The versions this run tests", "",
             "Python %s, Qt %s, PyQt %s, Chromium %s (as I.K.E. reports it)." % (
                 record.get("python", "?"), record.get("qt", "?"), record.get("pyqt", "?"),
                 record.get("chromium", "?")), "",
             "| Package | Version |", "|---|---|"]
    lines += ["| %s | %s |" % (n, v or "not installed") for n, v in record["packages"].items()]
    lines += ["", "The whole dependency closure: %d packages (recorded in the artifact)." % len(record["closure"])]
    if record.get("error"):
        lines += ["", "Not read: " + _v(record["error"])]
    return "\n".join(lines) + "\n"


# --- the filter lists I.K.E. turns on by default (1.1.20) ---------------------
# They change every day on users' computers, outside I.K.E.'s releases, while
# the AdBlock engine and uBlock Origin's scriptlets come with I.K.E. The
# check downloads them as I.K.E. does, loads them into the bundled engine and
# reads the scriptlets they use. A rule the engine cannot read, or a scriptlet
# name the bundled library does not know (ike/scriptlets.py drops such a rule
# without a word), is a finding about the components for a person: never a
# failure of the code. A list that cannot be downloaded is "unreachable".

LIST_MAX_BYTES = 32 * 1024 * 1024        # as MAX_LIST_BYTES of ike/blocker.py
LIST_INCLUDES = 24                       # "!#include" sub-lists followed, as ike/blocker.py
LIST_INCLUDE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,80}\.txt")
# the share of a list's rules the engine may leave unread (rules for other
# blockers, HTML filters...) before it is a finding: well above what the
# default lists give today (docs/MAINTENANCE.md), so only a real change of
# syntax or of the engine shows
LIST_UNREAD_SHARE = 0.25
LIST_EXAMPLES = 8
# every rule the engine does not read (at most this many per list), for the
# classification of the findings (tools/filter-lists.py, WP8)
LIST_UNREAD_KEEP = 4000
# Scriptlet names the default lists use that are not uBlock Origin's
# builtinScriptlets but its own resources (web_accessible_resources, also
# usable with +js): tools/build-ubo-scriptlets.mjs takes only the
# builtinScriptlets, so I.K.E. drops these rules. Seen on 2026-11-21 when this
# check was written; shown every day as a note, not as a new finding. Whether
# to bundle them is a person's decision. Any other unknown name is a finding.
KNOWN_UNRUN_SCRIPTLETS = ("noeval", "nofab", "popads-dummy", "popads.net", "fingerprint2")


def ike_modules(root):
    """ike.config and ike.scriptlets of this checkout (neither needs Qt). Loaded on their own
    when another copy of I.K.E. is already imported (a test that ran before in the same
    process), which is put back afterwards: the check always reads the copy it was given."""
    root = Path(root).resolve()

    def mine(mod):
        return Path(mod.__file__).resolve().parent.parent == root

    def ike_names():
        return [k for k in sys.modules if k == "ike" or k.startswith("ike.")]

    other = {k: sys.modules[k] for k in ike_names()}
    if other and mine(other.get("ike") or next(iter(other.values()))):
        other = {}
    for k in other:
        del sys.modules[k]
    if str(root) in sys.path:
        sys.path.remove(str(root))
    sys.path.insert(0, str(root))
    try:
        import importlib
        config = importlib.import_module("ike.config")
        scriptlets = importlib.import_module("ike.scriptlets")
    finally:
        if other:
            for k in ike_names():
                del sys.modules[k]
            sys.modules.update(other)
    if not mine(config):
        raise RuntimeError("another copy of I.K.E. is imported: %s" % config.__file__)
    return config, scriptlets


def engine_module(root):
    """The AdBlock engine of this checkout (vendor/adblock, built from
    ike-adblock/) and its parse_report, or (None, None, why)."""
    vendor = str(Path(root).resolve() / "vendor")
    sys.path.insert(0, vendor)
    try:
        import adblock
    except Exception as e:
        return None, None, "%s: %s" % (type(e).__name__, e)
    finally:
        sys.path.remove(vendor)
    native = sys.modules.get("adblock.ike_adblock")
    return adblock, getattr(native, "parse_report", None), ""


def scriptlet_library(scr, path=None):
    """The uBlock Origin scriptlet library as ike/scriptlets.py reads it (that
    of the checkout, or the file at path)."""
    lib = scr.Library()
    if path:
        old = scr.LIB_FILE
        scr.LIB_FILE = Path(path)
        try:
            lib._load()
        finally:
            scr.LIB_FILE = old
    return lib


def download_list(url, get=None):
    """A filter list as ike/blocker.py downloads it: HTTPS only, at most
    LIST_MAX_BYTES, not empty or binary, with the "!#include" sub-lists next to
    it, one level deep. (text, [sub-lists that could not be downloaded]);
    raises SourceUnreachable (or OSError) when the list itself cannot be read,
    ValueError when it is not a usable list."""
    get = get or (lambda u: fetch_source(u, timeout=60))
    if not url.startswith("https://"):
        raise ValueError("filter lists must use HTTPS")
    data = get(url)
    if len(data) > LIST_MAX_BYTES:
        raise ValueError("the list is larger than %d MB" % (LIST_MAX_BYTES >> 20))
    if len(data) < 20 or b"\x00" in data[:4096]:
        raise ValueError("an empty or binary list")
    names = []
    for raw in data.split(b"\n"):
        if raw.startswith(b"!#include "):
            name = raw[10:].strip().decode("ascii", "ignore")
            if LIST_INCLUDE_NAME.fullmatch(name) and name not in names:
                names.append(name)
    parts, missing = [data], []
    base = url.rsplit("/", 1)[0] + "/"
    for name in names[:LIST_INCLUDES]:
        try:
            sub = get(base + name)
        except (SourceUnreachable, OSError):
            missing.append(name)            # as I.K.E.: skipped
            continue
        if 20 <= len(sub) <= LIST_MAX_BYTES and b"\x00" not in sub[:4096]:
            parts.append(b"! --- included: " + name.encode() + b"\n" + sub)
        if sum(len(x) for x in parts) > LIST_MAX_BYTES:
            parts.pop()
            break
    return b"\n".join(parts).decode("utf-8", "replace"), missing


def list_scriptlets(text, lib, scr, trusted):
    """The "domain##+js(name, ...)" rules of a list as ike/scriptlets.py reads
    them: {"rules": run by I.K.E., "generic": without a domain (not run by
    I.K.E.), "untrusted": scriptlets uBlock Origin keeps to trusted lists,
    "unknown": {name: [count, first rule]} not in the library}."""
    out = {"rules": 0, "generic": 0, "untrusted": 0, "unknown": {}}
    for line in scr.preprocess(text).splitlines():
        if "+js(" not in line:
            continue
        m = scr._RULE.match(line.strip())
        if not m or m.group(2):             # an exception switches scriptlets off: nothing to run
            continue
        args = scr.split_args(m.group(3))
        if not args or not args[0]:
            continue
        if not m.group(1).strip():
            out["generic"] += 1
            continue
        name = lib.resolve(args[0])
        if name is None:
            seen = out["unknown"].setdefault(args[0], [0, line.strip()[:200]])
            seen[0] += 1
        elif lib.entry(name).get("trust") and not trusted:
            out["untrusted"] += 1
        else:
            out["rules"] += 1
    return out


def check_filter_lists(root=ROOT, get=None, library=None, lists=None):
    """The default filter lists in the bundled engine and scriptlets (see above)."""
    config, scr = ike_modules(root)
    lib = scriptlet_library(scr, library)
    lists = [e for e in (lists if lists is not None else config.DEFAULT_LISTS) if e.get("enabled", True)]
    mod, parse_report, engine_error = engine_module(root)
    blocker = None
    try:                    # ike/blocker.py needs Qt; without it the trusted sources are those of 1.1.20
        from ike import blocker
    except Exception:
        pass

    def trusted(url):
        if blocker is not None:
            return blocker._trusted_scriptlet_source(url)
        parts = urllib.parse.urlsplit(url)
        return parts.scheme == "https" and ((parts.hostname or "") == "ublockorigin.github.io" or (
            parts.hostname == "raw.githubusercontent.com" and parts.path.startswith("/uBlockOrigin/")))

    out = {"lists": [], "unknown_scriptlets": {}, "findings": [], "notes": [],
           "engine": {"backend": getattr(mod, "BACKEND", "") if mod else "", "error": engine_error,
                      "built": False, "parse_report": bool(parse_report)},
           "library": lib.lib_version()}
    texts = []
    for entry in lists:
        row = {"name": entry["name"], "url": entry["url"], "group": entry.get("group", ""), "state": "ok",
               "error": "", "includes_missing": [], "trusted": bool(trusted(entry["url"]))}
        out["lists"].append(row)
        try:
            text, row["includes_missing"] = download_list(entry["url"], get)
        except (SourceUnreachable, OSError) as e:
            row.update(state="unreachable", error="%s: %s" % (type(e).__name__, str(e)[:200]))
            continue
        except ValueError as e:
            row.update(state="unusable", error=str(e)[:200])
            out["findings"].append("%s: not a usable list (%s)" % (entry["name"], e))
            continue
        text = scr.preprocess(text)
        texts.append((entry["name"], text))
        if parse_report:
            try:
                rep = parse_report(text, False, LIST_UNREAD_KEEP)
                row.update({k: rep[k] for k in ("lines", "comments", "network", "cosmetic", "unsupported",
                                                "errors")}, examples=[list(x) for x in rep["examples"][:LIST_EXAMPLES]],
                           unread=[list(x) for x in rep["examples"]])
                rules = rep["network"] + rep["cosmetic"] + rep["unsupported"] + rep["errors"]
                share = (rep["unsupported"] + rep["errors"]) / rules if rules else 0.0
                row["unread_share"] = round(share, 4)
                if share > LIST_UNREAD_SHARE:
                    out["findings"].append("%s: the engine cannot read %.0f%% of its rules (%d unsupported, %d "
                                           "with errors)" % (entry["name"], share * 100, rep["unsupported"],
                                                             rep["errors"]))
            except Exception as e:
                row["error"] = "parse report: %s: %s" % (type(e).__name__, str(e)[:200])
                out["findings"].append("%s: the engine failed while reading it (%s)" % (entry["name"], row["error"]))
        if row["group"] == "consent":
            row["scriptlets"] = None          # I.K.E. runs no scriptlets of the cookie lists (ike/blocker.py)
            continue
        found = list_scriptlets(text, lib, scr, trusted(entry["url"]))
        row["scriptlets"] = {k: found[k] for k in ("rules", "generic", "untrusted")}
        row["scriptlets"]["unknown"] = sum(n for n, _ in found["unknown"].values())
        for name, (count, example) in found["unknown"].items():
            seen = out["unknown_scriptlets"].setdefault(name, {"count": 0, "lists": [], "example": example})
            seen["count"] += count
            seen["lists"].append(entry["name"])
    for name, seen in sorted(out["unknown_scriptlets"].items()):
        known = re.sub(r"\.js$", "", name) in KNOWN_UNRUN_SCRIPTLETS
        seen["known"] = known
        text = ("scriptlet `%s` (%d rules in %s) is not in the bundled uBlock Origin library %s: I.K.E. drops these "
                "rules" % (name, seen["count"], ", ".join(seen["lists"]), out["library"]))
        if known:
            out["notes"].append(text + " (one of uBlock Origin's own resources, known: KNOWN_UNRUN_SCRIPTLETS)")
        else:
            out["findings"].append(text + " (list/scriptlet drift)")
    if mod is None:
        out["findings"].append("the bundled AdBlock engine could not be loaded: %s" % engine_error)
    elif texts:
        if not parse_report:
            out["notes"].append("this engine has no parse_report (built before 1.1.20): rules not counted")
        fs = mod.FilterSet()
        for name, text in texts:
            try:
                fs.add_filter_list(text)
            except Exception as e:
                out["findings"].append("%s: the engine refused the list (%s: %s)" % (name, type(e).__name__, e))
        try:
            started = time.monotonic()
            engine = mod.Engine(fs)
            out["engine"]["build_s"] = round(time.monotonic() - started, 2)
            answer = engine.check_network_urls("https://example.com/", "https://example.com/", "document")
            if getattr(answer, "error", None):
                raise RuntimeError(answer.error)
            out["engine"]["built"] = True
        except Exception as e:
            out["engine"]["error"] = "%s: %s" % (type(e).__name__, str(e)[:300])
            out["findings"].append("the engine could not be built from the lists: %s" % out["engine"]["error"])
    unreachable = sum(r["state"] == "unreachable" for r in out["lists"])
    out["unreachable"] = unreachable
    out["state"] = ("findings" if out["findings"] else
                    "unreachable" if unreachable == len(out["lists"]) and out["lists"] else "ok")
    return out


def lists_markdown(info):
    """The section of the report about the filter lists."""
    head = {
        "ok": "The default filter lists load into the bundled engine, and every scriptlet they use is in the "
              "bundled uBlock Origin library.",
        "findings": "**Findings about the components** (for a person, not a failure of I.K.E.'s code; the "
                    "automatic fix is not asked):",
        "unreachable": "**No list could be downloaded (source unreachable)**: nothing was checked today.",
    }[info["state"]]
    eng = info["engine"]
    out = ["", "### The default filter lists in the bundled engine", "", head, ""]
    out += ["- %s" % _v(f) for f in info["findings"]]
    out += ["- note: %s" % _v(n) for n in info["notes"]]
    if info["findings"] or info["notes"]:
        out.append("")
    some = [r for r in info["lists"] if r["state"] != "unreachable"]
    if info["unreachable"] and some:
        out += ["Some lists could not be downloaded today (source unreachable): %s." % ", ".join(
            r["name"] for r in info["lists"] if r["state"] == "unreachable"), ""]
    out.append("Engine: %s; built from the lists: %s%s. Scriptlet library: uBlock Origin %s." % (
        _v(eng.get("backend") or "not loaded"), "yes" if eng.get("built") else "**no**",
        (" in %.1f s" % eng["build_s"]) if eng.get("build_s") is not None else "", _v(info["library"])))
    out += ["", "| List | State | Network / cosmetic rules | Unsupported | Parse errors | Scriptlet rules "
            "(run / unknown) |", "|---|---|---|---|---|---|"]
    for r in info["lists"]:
        sc = r.get("scriptlets")
        scr = "not read (cookie list)" if sc is None and r["state"] == "ok" else (
            "%d / %s" % (sc["rules"], ("**%d**" % sc["unknown"]) if sc["unknown"] else "0") if sc else "-")
        if "network" in r:
            rules, uns, err = "%d / %d" % (r["network"], r["cosmetic"]), str(r["unsupported"]), str(r["errors"])
        else:
            rules = uns = err = "-"
        state = r["state"] if not r["error"] else "%s (%s)" % (r["state"], r["error"])
        out.append("| %s | %s | %s | %s | %s | %s |" % (r["name"], _v(state), rules, uns, err, scr))
    examples = [(r["name"], e) for r in info["lists"] for e in r.get("examples", [])[:3]]
    if examples:
        out += ["", "<details><summary>Rules the engine does not read (examples)</summary>", "", "```text"]
        out += ["%s: %s: %s (%s)" % (n, kind, line.replace("```", "` ` `"), why) for n, (kind, line, why) in examples]
        out += ["```", "", "</details>"]
    return "\n".join(out) + "\n"


def write_lists_report(info, json_path=None, markdown_path=None):
    if json_path:
        Path(json_path).write_text(json.dumps(info, indent=1) + "\n", "utf-8")
    if markdown_path:
        Path(markdown_path).write_text(lists_markdown(info), "utf-8")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write("lists=%s\nlists_findings=%d\nlists_unreachable=%d\n"
                    % (info["state"], len(info["findings"]), info["unreachable"]))


# --- report -----------------------------------------------------------------

# the check each candidate comes from (WP5): its family
FAMILIES = ("adblock", "crates", "ubo-scriptlets", "darkreader", "test-packages")


def _manifest():
    """tools/component-manifest.py, beside this file: the entries of components.json."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("component_manifest", Path(__file__).resolve().parent /
                                                  "component-manifest.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def manifest_checks(root, get=None, tags=None, work=None):
    """One check per plain-download entry of the component manifest (components.json): any entry
    added there is checked, applied and made a candidate like the others, with no change here. And
    one per entry built by a builder of MANIFEST_BUILDS (1.1.24: KDE's Breeze icons)."""
    mf = _manifest()
    kw = dict({"get": get} if get else {}, **({"tags": tags} if tags else {}))
    out = [(e["name"], (lambda r, cid=cid: mf.check_entry(r, cid, **kw)), mf.apply_entry, (), cid)
           for cid, e in sorted(mf.components(root).items()) if e.get("download")]
    for cid, e in sorted(mf.components(root).items()):
        if cid in MANIFEST_BUILDS and e.get("build"):
            check, apply = MANIFEST_BUILDS[cid]
            folder = Path(work or tempfile.mkdtemp(prefix="ike-check-")) / cid
            folder.mkdir(parents=True, exist_ok=True)
            out.append((e["name"], (lambda r, check=check, folder=folder: check(r, folder, tags=tags)), apply,
                        (), cid))
    return out


def family_of(cid, root=ROOT):
    """The check (FAMILIES, or the manifest's own id) a candidate id comes from, or "" for an unknown id."""
    if cid in ("adblock", "ubo-scriptlets", "darkreader"):
        return cid
    if cid and (_manifest().components(root).get(cid) or {}).get("download"):
        return cid
    if cid in MANIFEST_BUILDS and (_manifest().components(root).get(cid) or {}).get("build"):
        return cid
    if cid in ("crates", "pyo3") or re.fullmatch(r"crate-major-[A-Za-z0-9_-]+", cid or ""):
        return "crates"
    if cid in ("test-qt", "test-tools", "test-libs"):
        return "test-packages"
    return ""


def candidates_of(results):
    """One record per candidate of today's results (WP5): {"id", "component", "from", "to", "note"},
    with "refused" (a builder refused the new version: kept, for the builder's path) or "error" (its
    source could not be read today: nothing to make)."""
    out = []
    for r in results:
        fam = r.get("id", "")
        base = {"component": r.get("name", "")}
        if r.get("error"):
            out.append(dict(base, id=fam, error=r["error"][:300], **{"from": r.get("current", ""), "to": ""}))
            continue
        if r.get("refused"):
            out.append(dict(base, id=fam, refused=True, step=r["refused"].get("step", ""),
                            **{"from": r.get("current", ""), "to": r.get("latest", "")}))
            continue
        if fam in ("crates", "test-packages"):
            out += [dict(base, **c) for c in r.get("_candidates") or ()]
        elif r.get("update"):
            out.append(dict(base, id=fam, note=r.get("note", ""), **{"from": r.get("current", ""),
                                                                      "to": r.get("latest", "")}))
    return out


def apply_candidate(root, results, cid):
    """Apply only this candidate (WP5). Returns its record, or raises when today's results do not have it."""
    cand = next((c for c in candidates_of(results) if c["id"] == cid), None)
    if cand is None:
        raise LookupError("no update of %s today" % cid)
    if cand.get("error") or cand.get("refused") or not cand.get("to"):
        raise LookupError("%s: %s" % (cid, cand.get("error") or ("refused by its builder" if cand.get("refused")
                                                                  else "nothing newer")))
    fam = family_of(cid, root)
    info = next(r for r in results if r.get("id") == fam)
    if cid == "crates":
        apply_compatible_crates(root, info)
    elif cid == "pyo3" or cid.startswith("crate-major-"):
        apply_requirement(root, cand["crate"], cand["requirement"])
    elif fam == "test-packages":
        apply_test_group(root, info, cid)
    else:
        info["_apply"](root, info)
    return cand


def check_all(root, ubo_src=None, work=None, dr_src=None, only=None, get=None, tags=None):
    """Every check (or only the family of the candidate `only`), each result with its "id" (FAMILIES)."""
    work = Path(work or tempfile.mkdtemp(prefix="ike-check-"))
    work.mkdir(parents=True, exist_ok=True)
    checks = [
        ("adblock-rust (AdBlock engine)", check_adblock, apply_adblock, (), "adblock"),
        ("Rust crates of the AdBlock engine", check_crates, apply_crates, (), "crates"),
        ("uBlock Origin scriptlets", check_scriptlets, apply_scriptlets, (work, ubo_src), "ubo-scriptlets"),
        ("Dark Reader (lists)", check_darkreader, apply_darkreader, (work, dr_src), "darkreader"),
        ("Qt WebEngine / PyQt6 (tests)", check_test_packages, apply_test_packages, (), "test-packages"),
    ]
    checks += manifest_checks(root, get, tags, work)
    if only:
        checks = [c for c in checks if c[4] == family_of(only, root)]
    results = []
    for name, check, apply, args, fam in checks:
        try:
            info = check(root, *args)
            info.setdefault("also", "")
            info["error"] = ""
        except BuilderRefused as e:
            # 1.1.20: the component stays at the version in use; the others go on
            info = {"current": e.report.get("current", ""), "latest": e.report.get("latest", ""), "update": False,
                    "note": "", "also": "", "error": "", "refused": dict(e.report, component=name)}
        except Exception as e:   # one failing source must not hide the others
            kind = "source unreachable: " if isinstance(e, (SourceUnreachable, OSError)) else ""
            info = {"current": "", "latest": "", "update": False, "note": "", "also": "",
                    "error": "%s%s: %s" % (kind, type(e).__name__,
                                           (getattr(e, "stderr", "") or str(e)).strip()[:300])}
        info.setdefault("refused", None)
        info["name"] = name
        info["id"] = fam
        info["_apply"] = apply
        results.append(info)
    return results


def public(results):
    return [{k: v for k, v in r.items() if not k.startswith("_")} for r in results]


def refused_markdown(results):
    """The component incompatibility section: one block per refused builder."""
    refused = [r["refused"] for r in results if r.get("refused")]
    if not refused:
        return ""
    out = ["", "### Component incompatibility: a builder refused the new upstream version", "",
           "Not a failure of GitHub or of the network, and not a matter for the automatic fix (the builders, "
           "`tools/build-*`, and the components' files are a person's). The component below **stays at the version "
           "in use, with I.K.E.'s changes**; every other component is still updated and tested. A person adapts "
           "the builder to the new upstream version (for uBlock Origin: the library's path in "
           "`tools/build-ubo-scriptlets.mjs`); the next daily run then takes it.", ""]
    for rep in refused:
        out.append("**%s**: %s → %s. Refused at: %s." % (rep["component"], _v(rep.get("current")),
                                                        _v(rep.get("latest")), rep.get("step", "?")))
        out += ["", "Reason: %s" % rep.get("reason", "?"), ""]
        for title, key in (("The new upstream version around the anchor", "context"), ("The builder's log", "log")):
            if rep.get(key):
                out += ["<details><summary>%s</summary>" % title, "", "```text",
                        rep[key].replace("```", "` ` `"), "```", "", "</details>", ""]
    return "\n".join(out) + "\n"


def to_markdown(results):
    n = sum(r["update"] for r in results)
    out = []
    if any(r.get("refused") for r in results):
        out.append("Un componente non accetta più le modifiche di I.K.E.: resta alla versione in uso, serve una "
                   "persona (dettagli sotto).\n")
    if n:
        out.append("Nuove versioni trovate: GitHub Actions prepara un candidato da testare e sottoporre al proprietario.\n")
    out.append("New versions of bundled components: **%d**. Checked %s UTC by "
               "`tools/check-components.py`.\n" % (n, datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M")))
    out.append("| Component | In use | Newest | New | Notes |\n|---|---|---|---|---|")
    for r in results:
        refused = r.get("refused")
        notes = "; ".join(x for x in (r["note"], ("also newer: " + r["also"]) if r["also"] else "",
                                      ("**check failed**: " + r["error"]) if r["error"] else "",
                                      ("**builder refused** (%s): kept at the version in use, see below"
                                       % refused.get("step", "?")) if refused else "") if x)
        new = "**refused**" if refused else ("**yes**" if r["update"] else "no")
        out.append("| %s | %s | %s | %s | %s |" % (r["name"], r["current"], r["latest"], new,
                                                  notes.replace("|", "\\|")))
    return "\n".join(out) + "\n" + refused_markdown(results)


def refresh_licences(root):
    """The licence files follow every component applied (tools/third-party.py:
    docs/THIRD-PARTY.md, licenses/RUST-CRATES.txt, licenses/NOTICE.ubo-scriptlets),
    run once after all of them. Until the trials of 2026-11-22 only the
    engine's and the crates' updates ran it, before uBlock Origin's scriptlets
    were copied: the candidate's NOTICE.ubo-scriptlets kept the old commit
    and its tests failed at "Licences" (candidate 97df120, issue #97)."""
    tool = root / "tools" / "third-party.py"
    if not tool.is_file():
        return
    done = subprocess.run([sys.executable, str(tool)], capture_output=True, text=True)
    print(done.stdout, end="")
    if done.returncode != 0:
        print("!! the licence files were not updated: run tools/third-party.py (%s)"
              % (done.stderr.strip()[-300:] or "exit %d" % done.returncode))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--json", help="write the result as JSON to this file")
    ap.add_argument("--markdown", help="write the result as a Markdown table to this file")
    ap.add_argument("--apply", action="store_true",
                    help="rewrite the version files with every newer version found")
    ap.add_argument("--ubo-src", help="use this uBlock Origin checkout instead of cloning it")
    ap.add_argument("--darkreader-src", help="use this Dark Reader checkout instead of cloning it")
    ap.add_argument("--arch", metavar="FILE",
                    help="also compare Arch Linux's packages with the tested set in FILE (--save-arch-tested)")
    ap.add_argument("--save-arch-tested", metavar="FILE",
                    help="only write the versions the last green arch.yml run on main tested (GitHub API, GET)")
    ap.add_argument("--record-arch", metavar="FILE",
                    help="only record the versions of this Arch system (arch.yml); prints the run's summary")
    ap.add_argument("--filter-lists", metavar="FILE",
                    help="only check the default filter lists in the bundled engine; JSON to FILE "
                         "(--markdown: its section)")
    ap.add_argument("--only", metavar="ID",
                    help="only this candidate (WP5: adblock, crates, pyo3, crate-major-<crate>, ubo-scriptlets, "
                         "darkreader, breeze-icons, test-qt, test-tools, test-libs, or another entry of "
                         "components.json): checked and, with --apply, applied alone")
    ap.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""), help="OWNER/NAME on GitHub")
    ap.add_argument("--root", default=str(ROOT), help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    root = Path(args.root)
    if args.record_arch:
        print(record_arch(args.record_arch, root), end="")
        return 0
    if args.filter_lists:
        info = check_filter_lists(root)
        write_lists_report(info, args.filter_lists, args.markdown)
        print(lists_markdown(info), end="")
        return 0
    if args.save_arch_tested:
        saved = save_arch_tested(args.save_arch_tested, args.repo)
        run = (saved["tested"] or {}).get("run") or {}
        print("last green Arch run on main with its versions: %s" % (run.get("url") or saved.get("error") or "none"))
        return 0
    arch = None
    if args.arch:
        try:
            saved = json.loads(Path(args.arch).read_text("utf-8"))
        except (OSError, ValueError) as e:
            saved = {"tested": None, "error": "%s: %s" % (type(e).__name__, e)}
        arch = check_arch(saved, db=arch_repo_versions())
        arch["testing_news"], arch["testing_errors"] = arch_testing_news(arch.get("tested"))
    if args.only and not family_of(args.only, root):
        print("::error::not a candidate: %s" % args.only[:80])
        return 2
    results = check_all(root, args.ubo_src, dr_src=args.darkreader_src, only=args.only)
    for r in results:
        state = "ERROR " + r["error"] if r["error"] else (
            "REFUSED" if r.get("refused") else ("NEW" if r["update"] else "ok"))
        print("%-34s %-6s %s -> %s %s" % (r["name"], state.split(" ")[0], r["current"], r["latest"],
                                         r["note"] or r["also"] or (r["error"] if r["error"] else "")))
    if arch:
        print("%-34s %-6s %s" % ("Arch Linux's own packages", arch["state"],
                                 "; ".join("%s %s -> %s" % (n, o or "-", v)
                                           for n, o, v in arch["changed"] + arch["closure_changed"][:20])
                                 or ", ".join(sorted(arch["unreachable"]))))
    updates = sum(r["update"] for r in results)
    errors = sum(bool(r["error"]) for r in results)
    refused = sum(bool(r.get("refused")) for r in results)
    print("updates: %d, errors: %d, refused: %d" % (updates, errors, refused))
    for r in results:
        if r.get("refused"):
            rep = r["refused"]
            print("::warning::component incompatibility: %s %s -> %s refused at %s: %s (kept at the version in use)"
                  % (r["name"], rep.get("current"), rep.get("latest"), rep.get("step"), rep.get("reason")))
    if args.json:
        data = {"updates": updates, "errors": errors, "refused": refused, "components": public(results),
                "candidates": candidates_of(results)}
        if arch:
            data["arch"] = arch_public(arch)
        Path(args.json).write_text(json.dumps(data, indent=1) + "\n", "utf-8")
    if args.markdown:
        Path(args.markdown).write_text(to_markdown(results) + (arch_markdown(arch) if arch else ""), "utf-8")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write("updates=%d\nerrors=%d\nrefused=%d\n" % (updates, errors, refused))
            if arch:
                f.write("arch=%s\n" % arch["state"])
                f.write("arch_testing=%s\n" % ("new" if arch.get("testing_news") else "none"))
    if args.apply and args.only:
        # WP5: one candidate alone; its own source unreachable stops it (the next run tries again)
        if errors:
            print("::error::not applying %s: its source could not be reached or checked" % args.only)
            return 1
        try:
            cand = apply_candidate(root, results, args.only)
        except LookupError as e:
            print("nothing applied: %s" % e)
            return 0
        print("applied: %s %s -> %s" % (cand["id"], cand.get("from", ""), cand.get("to", "")))
        refresh_licences(root)
        return 0
    if args.apply:
        if errors:
            # infrastructure (a source unreachable): fail closed, the next daily run tries again
            print("::error::not applying any updates: a component source could not be reached or checked "
                  "(source unreachable, not a builder that refused)")
            return 1
        if updates:
            for r in results:
                if (r["update"] or r["also"]) and not r.get("refused"):
                    r["_apply"](root, r)
                    print("applied:", r["name"])
            refresh_licences(root)
        else:
            print("no actionable component updates; informational rebuilds are deferred")
    return 0


if __name__ == "__main__":
    sys.exit(main())
