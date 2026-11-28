#!/usr/bin/env python3
"""Inventory of every external component I.K.E. uses (WP2 of the maintenance plan).

    python3 tools/inventory.py [--json FILE] [--markdown FILE] [--offline]
                               [--components report.json] [--lists lists.json]
                               [--arch-tested arch-tested.json] [--advisories FILE]

Read-only: nothing in the repository is changed. Every component is found in
the repository itself, so a dependency added later appears with no change
here:

- PKGBUILD: depends, makedepends, optdepends, and the commands of build();
- the Python modules imported by ike/ and ike_boot.py (AST), each mapped to
  the Arch package that provides it (Arch's rule: module ``foo`` is
  ``python-foo``, with the exceptions of MODULE_PACKAGES); the PyQt6 modules
  and the Qt packages they need;
- every crate of ike-adblock/Cargo.lock, direct or transitive;
- the Node.js modules imported by tools/*.mjs;
- the PyPI packages the workflows install (pip ``-r FILE`` and single
  packages), the tools installed with ``cargo install``, the Rust, Python and
  Node.js versions, runner images and apt packages of the workflows;
- every ``uses:`` of a GitHub Action, with the commit it is pinned to;
- the integrated resources: Dark Reader's lists, uBlock Origin's scriptlets, the
  filter lists of ike/config.py DEFAULT_LISTS, the vendored AdBlock engine;
- the programs ike/ starts (subprocess, QProcess; xdg-open through Qt's
  QDesktopServices, which ike/ no longer calls since 1.1.24), each mapped to
  its Arch package; the desktop's own openers (DESKTOP_TOOLS), started only
  when the desktop has them, are listed as the desktop's, not as
  dependencies.

A module, program or build command that no declared Arch package covers is a
finding "used but not declared".

Each record has: name, kind, type, origin (where in the repository it was
found), distribution, installed (pinned) version, available version (read from
archlinux.org's JSON API, crates.io's index, PyPI, npm, GitHub's git tags;
``--offline`` reads none), update mode, the tests an update needs
(tools/test-categories.py), compatibility, vulnerabilities, last check and
result. A value that is not known or could not be read is "unknown" or "not
checked", never guessed. Vulnerabilities come only from checks that ran: the
crates from RustSec through cargo-deny in security.yml (given with
--advisories); since WP7 the PyPI, npm and GitHub Actions components from the
OSV database and the Arch packages from Arch's security tracker
(tools/vulnerabilities.py; a source that does not answer leaves its
components "not checked", never "none known"). With --offline none is asked.

Hosts asked (no token): archlinux.org, index.crates.io, pypi.org,
registry.npmjs.org, github.com (git ls-remote), api.osv.dev (POST of names and
versions), security.archlinux.org.
"""

import argparse
import ast
import concurrent.futures
import datetime
import importlib.util
import json
import os
import re
import shlex
import subprocess
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = 1
UNKNOWN = "unknown"
NOT_CHECKED = "not checked"

CRATES_SPARSE = "https://index.crates.io/%s"
PYPI_JSON = "https://pypi.org/pypi/%s/json"
NPM_LATEST = "https://registry.npmjs.org/%s/latest"
GITHUB = "https://github.com/%s"
NETWORK_FAILURES = 3          # a host that failed this many times is not asked again in this run
WORKERS = 8

# Arch's rule for Python modules is python-<name>; the exceptions
MODULE_PACKAGES = {
    "PyQt6": "python-pyqt6", "PyQt6-WebEngine": "python-pyqt6-webengine", "yaml": "python-yaml",
    "PIL": "python-pillow", "dbus": "python-dbus", "gi": "python-gobject", "Crypto": "python-pycryptodome",
    "bs4": "python-beautifulsoup4", "dateutil": "python-dateutil", "OpenSSL": "python-pyopenssl",
    "google": "python-protobuf", "magic": "python-magic", "serial": "python-pyserial", "sip": "python-pyqt6-sip",
}
# the PyQt6 module -> the Arch packages it needs at run time
QT_MODULE_PACKAGES = {
    "QtWebEngineCore": ("python-pyqt6-webengine", "qt6-webengine"),
    "QtWebEngineWidgets": ("python-pyqt6-webengine", "qt6-webengine"),
    "QtWebEngineQuick": ("python-pyqt6-webengine", "qt6-webengine"),
    "QtWebChannel": ("python-pyqt6", "qt6-webchannel"),
    "QtSvg": ("python-pyqt6", "qt6-svg"), "QtSvgWidgets": ("python-pyqt6", "qt6-svg"),
    "QtMultimedia": ("python-pyqt6", "qt6-multimedia"), "QtMultimediaWidgets": ("python-pyqt6", "qt6-multimedia"),
    "QtPdf": ("python-pyqt6-webengine", "qt6-webengine"), "QtPdfWidgets": ("python-pyqt6-webengine", "qt6-webengine"),
    "QtQml": ("python-pyqt6", "qt6-declarative"), "QtQuick": ("python-pyqt6", "qt6-declarative"),
    "QtSerialPort": ("python-pyqt6", "qt6-serialport"), "QtPositioning": ("python-pyqt6", "qt6-positioning"),
    "QtSpeech": ("python-pyqt6", "qt6-speech"), "QtCharts": ("python-pyqt6-charts", "qt6-charts"),
}
# in qt6-base, which python-pyqt6 brings
QT_BASE_MODULES = ("QtCore", "QtGui", "QtWidgets", "QtNetwork", "QtPrintSupport", "QtDBus", "QtSql", "QtXml",
                   "QtOpenGL", "QtOpenGLWidgets", "QtTest", "QtConcurrent", "sip")
# a package brought by another declared one (its own depends in Arch)
TRANSITIVE = {"qt6-base": "python-pyqt6"}
# programs ike/ starts -> the Arch package that has them
TOOL_PACKAGES = {
    "notify-send": "libnotify", "xdg-settings": "xdg-utils", "xdg-open": "xdg-utils", "xdg-mime": "xdg-utils",
    "xdg-email": "xdg-utils", "kde-open": "kde-cli-tools", "kioclient": "kde-cli-tools", "gsettings": "glib2",
    "gio": "glib2", "exo-open": "exo",
    "git": "git", "ffmpeg": "ffmpeg", "pacman": "pacman", "python3": "python", "python": "python",
}
# programs of the user's desktop that ike/ starts only when they are there (ike/handoff.py: the
# opener of KDE, of the GLib desktops, of Xfce when no desktop portal answers): not dependencies
DESKTOP_TOOLS = ("kioclient", "gio", "exo-open")
# the build() commands of the PKGBUILD -> their Arch package
BUILD_PACKAGES = {"cargo": "rust", "rustc": "rust", "gcc": "gcc", "cc": "gcc", "clang": "clang", "make": "make",
                  "node": "nodejs", "npm": "npm", "python3": "python", "python": "python"}
# always there with makepkg (base, base-devel)
BASE_COMMANDS = {"cd", "install", "cp", "find", "rm", "mkdir", "ln", "sed", "chmod", "local", "printf", "echo",
                 "for", "do", "done", "if", "then", "fi", "test", "tar", "sh", "bash", "return", "export", "true"}

# how each kind of component is updated
UPDATE_MODES = {
    "arch-package": "system: users get it with pacman -Syu; the daily check starts arch.yml to verify it",
    "arch-optional": "system: users get it with pacman -Syu; optional, installed by the user",
    "arch-build": "system: the owner's makepkg uses the installed one",
    "python-module": "through its Arch package (pacman -Syu)",
    "pyqt-module": "through its Arch packages (pacman -Syu)",
    "crate": "candidate: tools/check-components.py --apply (cargo update) on automation/daily-maintenance",
    "adblock-engine": "candidate: tools/check-components.py --apply on automation/daily-maintenance",
    "vendored": "rebuilt from ike-adblock/ (crates) in every build and in the signed self-update",
    "pypi-test": "candidate: tools/check-components.py --apply (tools/test-requirements.txt)",
    "pypi-ci": "follows tools/test-requirements.txt",
    "npm": "imported by a tool (tools/*.mjs) when it runs: no lockfile pins it",
    "node": "workflow file (setup-node): a proposal for a person",
    "integrated": "candidate: tools/check-components.py --apply (rebuilt by I.K.E.'s builder)",
    "filter-list": "runtime: each browser downloads it (ike/blocker.py); checked daily in the bundled engine",
    "github-action": "workflow file: Dependabot's monthly proposal, merged by a person",
    "ci-tool": "workflow file: a proposal for a person (version pinned in the workflow)",
    "ci-runtime": "workflow file: a proposal for a person",
    "ci-package": "the runner's apt archive (unpinned)",
    "runtime-tool": "system: its Arch package (pacman -Syu)",
    "build-tool": "system: its Arch package (makedepends)",
}


def _components_tool():
    """tools/check-components.py, beside this file: its fetch, Arch and Cargo.lock helpers."""
    spec = importlib.util.spec_from_file_location("check_components", Path(__file__).resolve().parent /
                                                  "check-components.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _manifest_tool():
    spec = importlib.util.spec_from_file_location("component_manifest", Path(__file__).resolve().parent /
                                                  "component-manifest.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --- the inventory guard (2026-11-22): nothing from upstream without an update path ---------------

# I.K.E.'s own files under ike/resources/, written for I.K.E. and kept by its own commits (page
# scripts, pages, the look-alike table, its pictures). Everything else there must be declared: an
# entry of components.json, or one of the kinds below.
OWN_RESOURCES = (
    "ike/resources/consent.js", "ike/resources/darkmode.js", "ike/resources/fingerprint.js",
    "ike/resources/mediahook.js", "ike/resources/passwords.js", "ike/resources/reader.js",
    "ike/resources/userscript.js", "ike/resources/videoads.js", "ike/resources/videorelay.js",
    "ike/resources/newtab.html", "ike/resources/lookalike.json", "ike/resources/ike.svg",
    "ike/resources/wordmark.svg", "ike/resources/newtab-background.webp", "ike/resources/newtab-preview.png",
    # 1.1.24: the new tab page's greeting, and its table of holiday dates (checked by hand on
    # 2026-11-23; its yearly refresh by AUTOMAT is planned with the other ageing data)
    "ike/resources/greeting.js", "ike/resources/holidays.json",
)
# folders of I.K.E.'s own resources: its language packs, the icon sets (Lucide, Phosphor) and the
# Orbitron font (ike/resources/fonts/, 1.1.30): fixed copies with their licences in licenses/, chosen
# by the owner, not followed upstream: docs/THIRD-PARTY.md
OWN_RESOURCE_DIRS = ("ike/resources/lang/", "ike/resources/icons/", "ike/resources/fonts/")
# folders under those that hold a component followed upstream (1.1.24: KDE's Breeze icons, built by
# tools/build-breeze-icons.py): every file there must be declared in components.json
FOLLOWED_DIRS = ("ike/resources/icons/sets/breeze/",)
# what another auto-discovered kind covers: the vendored engine is rebuilt from ike-adblock/ (crates)
COVERED_DIRS = ("vendor/adblock/",)
EXTERNAL_DIRS = re.compile(r"(^|/)(vendor|vendored|third_party|third-party|thirdparty|node_modules|external|deps)/")
UPSTREAM_HEADER = re.compile(
    r"@license\b|@preserve\b|SPDX-License-Identifier|\bMIT License\b|Permission is hereby granted"
    r"|GNU (?:Lesser |Affero )?General Public License|Apache License|Mozilla Public License|BSD \d-Clause"
    r"|\(c\) \d{4}|Copyright (?:\(c\) )?\d{4}", re.I)
CODE_SUFFIXES = (".js", ".mjs", ".css", ".json", ".wasm", ".html")
MINIFIED_LINE = 2000


def looks_external(root, path):
    """Why a file of the repository looks like it comes from upstream, or "" (read, never run)."""
    if EXTERNAL_DIRS.search(path):
        return "it is in a folder of vendored code"
    if path.startswith(FOLLOWED_DIRS):
        return "it is in the folder of a component followed upstream (FOLLOWED_DIRS)"
    if path.startswith("ike/resources/") and path not in OWN_RESOURCES and not path.startswith(OWN_RESOURCE_DIRS):
        return "it is under ike/resources/ and not one of I.K.E.'s own resources (OWN_RESOURCES)"
    if not path.startswith("ike/") or not path.endswith(CODE_SUFFIXES):
        return ""
    if re.search(r"\.min\.(js|css)$", path):
        return "a minified file"
    try:
        text = (Path(root) / path).read_text("utf-8", "replace")
    except OSError:
        return ""
    if path.endswith((".js", ".mjs", ".css")):
        if UPSTREAM_HEADER.search(text[:3000]) and path not in OWN_RESOURCES:
            return "it starts with an upstream licence header"
        if any(len(line) > MINIFIED_LINE for line in text.split("\n")) and path not in OWN_RESOURCES:
            return "minified code (a line of more than %d characters)" % MINIFIED_LINE
    return ""


def tracked_files(root):
    out = subprocess.run(["git", "-C", str(root), "ls-files", "-z"], capture_output=True, text=True, check=False)
    if out.returncode == 0 and out.stdout:
        return [n for n in out.stdout.split("\0") if n]
    return sorted(str(p.relative_to(root)) for p in Path(root).rglob("*")
                  if p.is_file() and ".git" not in p.parts and "__pycache__" not in p.parts)


def entry_hint(root, path):
    """The entry of components.json to add for an undeclared file: what the test's message shows."""
    import hashlib
    try:
        digest = hashlib.sha256((Path(root) / path).read_bytes()).hexdigest()
    except OSError:
        digest = "<sha256 of the file>"
    cid = re.sub(r"[^a-z0-9]+", "-", Path(path).stem.lower()).strip("-")[:40] or "component"
    return json.dumps({cid: {
        "name": "<what it is>", "upstream": {"git": "https://github.com/<owner>/<repository>", "tag": "v*"},
        "files": [path], "version": "<the version in use>",
        "download": [{"url": "https://raw.githubusercontent.com/<owner>/<repository>/{tag}/<path upstream>",
                      "file": path, "sha256": digest}],
        "licence": "licenses/<its licence file>",
        "tests": list(_manifest_tool().DEFAULT_TESTS)}}, indent=1)


def undeclared_files(root=ROOT, files=None):
    """[(file, why it looks external, the entry to add)]: files from upstream that no entry of the
    component manifest and no auto-discovered kind covers. Empty in a healthy repository."""
    mf = _manifest_tool()
    declared = {f for e in mf.components(root).values() for f in e["files"]}
    out = []
    for path in (files if files is not None else tracked_files(root)):
        if path in declared or path.startswith(COVERED_DIRS):
            continue
        why = looks_external(root, path)
        if why:
            out.append((path, why, entry_hint(root, path)))
    return out


# kinds whose update comes through a candidate of its own (tools/update-candidates.py candidate_for)
CANDIDATE_KINDS = ("adblock-engine", "crate", "integrated", "npm", "pypi-test", "github-action")


def update_path(rec):
    """How this record is updated: its candidate ("candidate automation/update/<id>"), or its update
    mode when its kind is not updated through a candidate (the system's packages, the lists the
    browser downloads, what follows another record); "" when it has none (the guard then fails)."""
    mode = str(rec.get("update_mode") or "")
    if not mode or mode == UNKNOWN:
        return ""
    if rec.get("kind") in CANDIDATE_KINDS:
        uc_spec = importlib.util.spec_from_file_location("update_candidates", Path(__file__).resolve().parent /
                                                         "update-candidates.py")
        uc = importlib.util.module_from_spec(uc_spec)
        uc_spec.loader.exec_module(uc)
        cid = uc.candidate_for(rec)
        if cid:
            return "candidate automation/update/%s" % cid
        if rec.get("kind") == "crate":
            return "with the crate that brings it (a candidate of adblock, pyo3 or the crates)"
        return ""
    return mode


def guard_problems(root=ROOT, inv=None, files=None):
    """What the inventory guard refuses (a list of messages; empty: every external component is
    catalogued and has an update path)."""
    out = []
    try:
        _manifest_tool().read(root)
    except ValueError as e:
        out.append(str(e))
    for path, why, hint in undeclared_files(root, files):
        out.append("%s looks like a file from upstream (%s) and no entry of components.json declares it. Add this "
                   "entry to \"components\" in components.json, with its real upstream, version and licence "
                   "(the sha256 is the file's own):\n%s" % (path, why, hint))
    for rec in (inv or {}).get("components", []):
        if not update_path(rec):
            out.append("%s (%s) has no update path: its update mode is %r and no candidate carries it "
                       "(tools/inventory.py UPDATE_MODES, tools/update-candidates.py candidate_for, or an entry "
                       "of components.json)" % (rec.get("id"), rec.get("kind"), rec.get("update_mode")))
    return out


def _vulnerabilities_tool():
    spec = importlib.util.spec_from_file_location("vulnerabilities", Path(__file__).resolve().parent /
                                                  "vulnerabilities.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _tests_tool():
    spec = importlib.util.spec_from_file_location("test_categories", Path(__file__).resolve().parent /
                                                  "test-categories.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def record(name, kind, type_, origin, distribution, installed, **kw):
    rec = {"id": "%s:%s" % (kind, name), "name": name, "kind": kind, "type": type_,
           "origin": sorted(set(origin)) if isinstance(origin, (list, set, tuple)) else [origin],
           "distribution": distribution, "installed": installed or UNKNOWN, "available": NOT_CHECKED,
           "available_source": "", "update_mode": UPDATE_MODES.get(kind, UNKNOWN), "tests_needed": [],
           "compatibility": UNKNOWN, "vulnerabilities": NOT_CHECKED, "last_check": "", "result": NOT_CHECKED,
           "notes": []}
    rec.update(kw)
    return rec


def rel(root, path):
    try:
        return str(Path(path).resolve().relative_to(Path(root).resolve()))
    except ValueError:
        return str(path)


# --- PKGBUILD ------------------------------------------------------------------

def _bash_array(text, key):
    """The words of every `key=(...)` array of a PKGBUILD: quoted strings or bare words, comments
    dropped; a ")" inside quotes does not end the array."""
    out = []
    for m in re.finditer(r"^%s=\(" % re.escape(key), text, re.M):
        i, word, quote, have = m.end(), "", "", False
        while i < len(text):
            ch = text[i]
            if quote:
                if ch == quote:
                    quote = ""
                else:
                    word += ch
            elif ch in "'\"":
                quote, have = ch, True
            elif ch == "#" and not have:
                while i < len(text) and text[i] != "\n":
                    i += 1
                continue
            elif ch.isspace() or ch == ")":
                if have:
                    out.append(word)
                word, have = "", False
                if ch == ")":
                    break
            else:
                word, have = word + ch, True
            i += 1
    return out


def parse_pkgbuild(text):
    """{"depends": [names], "makedepends": [...], "optdepends": [(name, why)], "checkdepends": [...],
    "build_commands": [command names of build()], "pkgver"}"""
    out = {"depends": [], "makedepends": [], "optdepends": [], "checkdepends": [], "build_commands": [],
           "pkgver": ""}
    for key in ("depends", "makedepends", "optdepends", "checkdepends"):
        for word in _bash_array(text, key):
            if key == "optdepends":
                name, _, why = word.partition(":")
                out[key].append((re.split(r"[<>=]", name.strip())[0], why.strip()))
            else:
                out[key].append(re.split(r"[<>=]", word.strip())[0])
    ver = re.search(r"^pkgver=([^\s#]+)", text, re.M)
    out["pkgver"] = ver.group(1).strip("'\"") if ver else ""
    body = re.search(r"^build\(\)\s*\{(.*?)^\}", text, re.M | re.S)
    if body:
        commands = []
        for line in body.group(1).replace("\\\n", " ").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                words = shlex.split(line, comments=True)
            except ValueError:
                words = line.split()
            words = [w for w in words if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", w)]
            if words and re.fullmatch(r"[A-Za-z][\w.+-]*", words[0]) and words[0] not in commands:
                commands.append(words[0])
        out["build_commands"] = commands
    return out


# --- Python imports of ike/ and ike_boot.py -------------------------------------

def _stdlib():
    names = set(getattr(sys, "stdlib_module_names", ()))
    if not names:          # Python < 3.10: the modules this interpreter has built in or in its library
        names = set(sys.builtin_module_names)
        lib = Path(os.__file__).parent
        names |= {p.stem for p in lib.glob("*.py")} | {p.name for p in lib.iterdir() if p.is_dir()}
    return names


def _optional(node, parents):
    """True when the import sits in a try: whose handlers catch ImportError (or anything)."""
    child = node
    for p in parents:
        if isinstance(p, ast.Try) and child in p.body:
            for h in p.handlers:
                names = []
                for t in ([h.type] if not isinstance(h.type, ast.Tuple) else h.type.elts) if h.type else []:
                    names.append(getattr(t, "id", getattr(t, "attr", "")))
                if h.type is None or set(names) & {"ImportError", "ModuleNotFoundError", "Exception",
                                                   "BaseException"}:
                    return True
        child = p
    return False


def python_files(root):
    root = Path(root)
    files = sorted((root / "ike").rglob("*.py")) if (root / "ike").is_dir() else []
    if (root / "ike_boot.py").is_file():
        files.append(root / "ike_boot.py")
    return [f for f in files if "__pycache__" not in f.parts]


def scan_python(root):
    """({top module: {"files": [...], "optional": bool, "names": [full module names]}},
    [(program, file:line, how)] started by the code, [syntax errors])."""
    imports, tools, errors = {}, [], []
    for f in python_files(root):
        where = rel(root, f)
        try:
            tree = ast.parse(f.read_text("utf-8"), str(f))
        except (SyntaxError, ValueError, OSError) as e:
            errors.append("%s: %s" % (where, e))
            continue
        parents = {}
        for node in ast.walk(tree):
            for child in ast.iter_child_nodes(node):
                parents[child] = node

        def chain(n):
            out = []
            while n in parents:
                n = parents[n]
                out.append(n)
            return out

        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module] + ["%s.%s" % (node.module, a.name) for a in node.names
                                         if node.module == "PyQt6"]
            for full in names:
                top = full.split(".")[0]
                entry = imports.setdefault(top, {"files": set(), "optional": True, "names": set()})
                entry["files"].add(where)
                entry["names"].add(full)
                entry["optional"] = entry["optional"] and _optional(node, chain(node))
            if isinstance(node, ast.Call):
                prog = _started_program(node)
                if prog:
                    tools.append((prog[0], "%s:%d" % (where, node.lineno), prog[1]))
    for entry in imports.values():
        entry["files"] = sorted(entry["files"])
        entry["names"] = sorted(entry["names"])
    return imports, tools, errors


_SUBPROCESS = {"run", "Popen", "call", "check_call", "check_output"}
_OS_EXEC = {"execv", "execvp", "execvpe", "execl", "execlp", "spawnlp", "spawnvp"}


def _started_program(call):
    """(program, how) when this call starts a program named by a literal, else None."""
    func = call.func
    attr = getattr(func, "attr", getattr(func, "id", ""))
    owner = getattr(getattr(func, "value", None), "id", "") or getattr(getattr(func, "value", None), "attr", "")
    if attr == "openUrl" and owner == "QDesktopServices":
        return ("xdg-open", "Qt's QDesktopServices.openUrl")
    if not call.args:
        return None
    first = call.args[0]
    literal = isinstance(first, ast.Constant) and isinstance(first.value, str) and first.value.strip()
    if (owner == "subprocess" and attr in _SUBPROCESS) or (owner == "os" and attr in _OS_EXEC):
        if isinstance(first, (ast.List, ast.Tuple)) and first.elts and isinstance(first.elts[0], ast.Constant) \
                and isinstance(first.elts[0].value, str):
            return (first.elts[0].value, "%s.%s" % (owner, attr))
        if literal:
            return (first.value.split()[0], "%s.%s" % (owner, attr))
    # QProcess.startDetached("prog", [...]) / QProcess.execute(...), or a QProcess object's start("prog")
    if attr in ("startDetached", "execute") and owner == "QProcess" and literal:
        return (first.value.split()[0], "QProcess.%s" % attr)
    if attr == "start" and literal and len(call.args) == 2:
        return (first.value.split()[0], "QProcess.start")
    return None


def module_package(module):
    """The Arch package of a Python module, by Arch's naming rule."""
    if module in MODULE_PACKAGES:
        return MODULE_PACKAGES[module]
    return "python-" + re.sub(r"[_.]+", "-", module).lower()


def qt_packages(name):
    """The Arch packages a PyQt6 module needs, or None when the module is not known here."""
    mod = name.split(".", 1)[1] if "." in name else name
    if mod in QT_MODULE_PACKAGES:
        return QT_MODULE_PACKAGES[mod]
    if mod in QT_BASE_MODULES:
        return ("python-pyqt6", "qt6-base")
    return None


# --- Cargo ---------------------------------------------------------------------

def parse_cargo_lock(text):
    """[{"name", "version", "source", "dependencies"}] of a Cargo.lock."""
    out = []
    for block in text.replace("\r\n", "\n").split("[[package]]")[1:]:
        name = re.search(r'^name = "([^"]+)"', block, re.M)
        version = re.search(r'^version = "([^"]+)"', block, re.M)
        source = re.search(r'^source = "([^"]+)"', block, re.M)
        deps = re.search(r"^dependencies = \[(.*?)\]", block, re.M | re.S)
        if name and version:
            out.append({"name": name.group(1), "version": version.group(1),
                        "source": source.group(1) if source else "",
                        "dependencies": [d.split()[0] for d in re.findall(r'"([^"]+)"', deps.group(1))]
                        if deps else []})
    return out


def cargo_requirements(text):
    """{crate: requirement} of the [dependencies] of a Cargo.toml."""
    out = {}
    section = re.search(r"^\[dependencies\]\n(.*?)(?=^\[|\Z)", text, re.M | re.S)
    for line in (section.group(1) if section else "").splitlines():
        m = re.match(r'^([A-Za-z0-9_-]+)\s*=\s*(?:"([^"]+)"|\{[^}]*?version\s*=\s*"([^"]+)")', line.strip())
        if m:
            out[m.group(1)] = m.group(2) or m.group(3)
    return out


# --- workflows ---------------------------------------------------------------------

USES = re.compile(r"^\s*-?\s*uses:\s*([^\s#]+)\s*(?:#\s*(\S+))?", re.M)


def workflow_files(root):
    gh = Path(root) / ".github"
    files = sorted(gh.glob("workflows/*.yml")) + sorted(gh.glob("workflows/*.yaml"))
    files += sorted(gh.glob("actions/**/action.yml")) + sorted(gh.glob("actions/**/action.yaml"))
    return files


def _run_blocks(text):
    """The shell lines of a workflow, continuation lines joined."""
    return text.replace("\\\n", " ").splitlines()


def scan_workflows(root):
    """Everything the workflows use: actions, pip, cargo install, rustup, setup-python/node, images, apt."""
    found = {"actions": {}, "pip_files": {}, "pip": {}, "cargo_install": {}, "rustup": {}, "python": {},
             "node": {}, "runners": {}, "containers": {}, "apt": {}}
    for f in workflow_files(root):
        where = rel(root, f)
        text = f.read_text("utf-8", "replace")
        for m in USES.finditer(text):
            ref = m.group(1).strip("'\"")
            if ref.startswith("./"):
                continue                                   # the repository's own action: read above
            if ref.startswith("docker://"):
                found["containers"].setdefault(ref[9:], set()).add(where)
                continue
            action, _, pin = ref.partition("@")
            key = (action, pin)
            entry = found["actions"].setdefault(key, {"files": set(), "comment": m.group(2) or ""})
            entry["files"].add(where)
        for line in _run_blocks(text):
            s = line.strip()
            if re.search(r"\bpip3?\s+install\b|-m\s+pip\s+install\b", s):
                words = s.split("pip install", 1)[-1].split()
                i = 0
                while i < len(words):
                    w = words[i].strip("'\"")
                    if w in ("-r", "--requirement") and i + 1 < len(words):
                        found["pip_files"].setdefault(words[i + 1].strip("'\""), set()).add(where)
                        i += 2
                        continue
                    if w.startswith("-") or w in ("|", "&&", ";", ">", "2>&1") or w.startswith((">", "$(")):
                        if w in ("|", "&&", ";"):
                            break
                        i += 1
                        continue
                    name = re.sub(r"^\$\{\w+:-", "", w).rstrip("}")
                    m2 = re.match(r"^([A-Za-z][A-Za-z0-9._-]*)(?:==([\w.]+))?", name)
                    if m2:
                        found["pip"].setdefault(m2.group(1), {"files": set(), "version": m2.group(2) or ""})
                        found["pip"][m2.group(1)]["files"].add(where)
                    i += 1
            for m2 in re.finditer(r"cargo install\s+(?:--\S+\s+)*([A-Za-z0-9_-]+)@([\w.]+)", s):
                found["cargo_install"].setdefault((m2.group(1), m2.group(2)), set()).add(where)
            m2 = re.search(r"rustup toolchain install\s+([\w.-]+)", s)
            if m2:
                found["rustup"].setdefault(m2.group(1), set()).add(where)
            m2 = re.match(r"^python-version:\s*['\"]?([\w.]+)", s)
            if m2:
                found["python"].setdefault(m2.group(1), set()).add(where)
            m2 = re.match(r"^node-version:\s*['\"]?([\w.]+)", s)
            if m2:
                found["node"].setdefault(m2.group(1), set()).add(where)
            m2 = re.match(r"^runs-on:\s*['\"]?([\w.-]+)", s)
            if m2:
                found["runners"].setdefault(m2.group(1), set()).add(where)
            m2 = re.match(r"^(?:container|image):\s*['\"]?([\w./-]+:[\w.-]+)['\"]?$", s)
            if m2:
                found["containers"].setdefault(m2.group(1), set()).add(where)
            m2 = re.search(r"apt-get install\s+(.*)", s)
            if m2:
                for w in m2.group(1).split():
                    if w in ("|", "&&", ";", ">") or w.startswith((">", "/")):
                        break
                    if not w.startswith("-") and re.fullmatch(r"[a-z0-9][a-z0-9.+-]+", w):
                        found["apt"].setdefault(w, set()).add(where)
    return found


def read_pins(path):
    pins = []
    try:
        lines = Path(path).read_text("utf-8").splitlines()
    except OSError:
        return pins
    for line in lines:
        line = line.split("#")[0].strip()
        if "==" in line:
            name, version = line.split("==", 1)
            pins.append((name.strip(), version.strip()))
        elif line and not line.startswith("-"):
            pins.append((re.split(r"[<>=~!\s;]", line)[0], ""))
    return pins


# --- Node.js tools -----------------------------------------------------------------

def scan_mjs(root):
    """({npm package: [files]}, [files using Node.js built-ins])."""
    npm, builtin = {}, []
    for f in sorted((Path(root) / "tools").glob("*.mjs")):
        text = f.read_text("utf-8", "replace")
        specs = re.findall(r"""(?:\bfrom\s+|\bimport\s*\(\s*|\brequire\s*\(\s*|^\s*import\s+)['"]([^'"]+)['"]""",
                           text, re.M)
        for spec in specs:
            if spec.startswith("node:"):
                if rel(root, f) not in builtin:
                    builtin.append(rel(root, f))
            elif not spec.startswith((".", "/")):
                name = "/".join(spec.split("/")[:2]) if spec.startswith("@") else spec.split("/")[0]
                npm.setdefault(name, []).append(rel(root, f))
    return npm, builtin


# --- the filter lists -----------------------------------------------------------------

def default_lists(root):
    """DEFAULT_LISTS of ike/config.py, read without running it."""
    path = Path(root) / "ike" / "config.py"
    try:
        tree = ast.parse(path.read_text("utf-8"))
    except (OSError, SyntaxError):
        return []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "DEFAULT_LISTS" for t in node.targets):
            try:
                value = ast.literal_eval(node.value)
            except ValueError:
                return []
            return [e for e in value if isinstance(e, dict) and e.get("url")]
    return []


def followed_arch_packages(root):
    """ARCH_PACKAGES of tools/check-components.py, read without running it."""
    try:
        tree = ast.parse((Path(root) / "tools" / "check-components.py").read_text("utf-8"))
    except (OSError, SyntaxError):
        return []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "ARCH_PACKAGES" for t in node.targets):
            try:
                return [str(n) for n in ast.literal_eval(node.value)]
            except ValueError:
                return []
    return []


# --- discovery -----------------------------------------------------------------------

def discover(root, arch_tested=None):
    """Every component found in the repository (no network). (records, findings, notes)."""
    root = Path(root)
    records, findings, notes = {}, [], []

    def add(rec):
        old = records.get(rec["id"])
        if old:
            old["origin"] = sorted(set(old["origin"]) | set(rec["origin"]))
            return old
        records[rec["id"]] = rec
        return rec

    tested = ((arch_tested or {}).get("tested") or {}).get("packages", {}) if isinstance(arch_tested, dict) else {}
    pkg = {"depends": [], "makedepends": [], "optdepends": [], "checkdepends": [], "build_commands": []}
    if (root / "PKGBUILD").is_file():
        pkg = parse_pkgbuild((root / "PKGBUILD").read_text("utf-8"))
    declared = {n: "depends" for n in pkg["depends"]}
    for n in pkg["makedepends"]:
        declared.setdefault(n, "makedepends")
    for n, _ in pkg["optdepends"]:
        declared.setdefault(n, "optdepends")

    def arch_installed(name):
        if tested.get(name):
            return tested[name]
        return "not pinned (rolling: pacman -Syu)"

    for name in pkg["depends"]:
        add(record(name, "arch-package", "runtime", "PKGBUILD depends", "Arch Linux (pacman)", arch_installed(name)))
    for name in pkg["makedepends"]:
        add(record(name, "arch-build", "build", "PKGBUILD makedepends", "Arch Linux (pacman)",
                   arch_installed(name)))
    for name, why in pkg["optdepends"]:
        add(record(name, "arch-optional", "optional", "PKGBUILD optdepends", "Arch Linux (pacman)",
                   arch_installed(name), notes=[why] if why else []))
    for name in pkg["checkdepends"]:
        add(record(name, "arch-build", "test", "PKGBUILD checkdepends", "Arch Linux (pacman)", arch_installed(name)))

    # the Arch packages the daily check follows (tools/check-components.py ARCH_PACKAGES) that the
    # PKGBUILD does not name: what arch.yml installs and records for I.K.E.'s features
    for name in followed_arch_packages(root):
        if name not in declared:
            add(record(name, "arch-package", "tested", "tools/check-components.py ARCH_PACKAGES",
                       "Arch Linux (pacman)", arch_installed(name),
                       notes=["followed by the daily check; not a PKGBUILD dependency"]))

    def covered(package):
        """How a needed Arch package is declared: depends / optdepends / makedepends / via X / ''."""
        if package in declared:
            return declared[package]
        via = TRANSITIVE.get(package)
        if via and declared.get(via) == "depends":
            return "via " + via
        return ""

    # build() commands
    for cmd in pkg["build_commands"]:
        if cmd in BASE_COMMANDS:
            continue
        package = BUILD_PACKAGES.get(cmd, "")
        rec = add(record(cmd, "build-tool", "build", "PKGBUILD build()", "Arch Linux (pacman)",
                         arch_installed(package) if package else UNKNOWN, provided_by=package or UNKNOWN))
        if not package:
            findings.append({"finding": "unknown provider", "component": rec["id"],
                             "detail": "build() runs `%s`: its Arch package is not known (BUILD_PACKAGES)" % cmd})
        elif not covered(package):
            findings.append({"finding": "used but not declared", "component": rec["id"],
                             "detail": "build() runs `%s` (package %s), not in makedepends or depends"
                                       % (cmd, package)})
    if (root / "PKGBUILD").is_file():
        add(record("makepkg", "build-tool", "build", "PKGBUILD", "Arch Linux (pacman, base-devel)",
                   "not pinned (rolling: pacman -Syu)", provided_by="pacman"))

    # Python imports
    imports, tools, errors = scan_python(root)
    notes += ["not read (syntax error): %s" % e for e in errors]
    stdlib = _stdlib()
    for top, info in sorted(imports.items()):
        if top in stdlib or top == "__future__":
            continue
        if top == "ike" or (root / "ike" / (top + ".py")).is_file() or (root / (top + ".py")).is_file():
            continue                                                   # I.K.E.'s own
        if (root / "vendor" / top).is_dir():
            ver = ""
            toml = root / "ike-adblock" / "Cargo.toml"
            if toml.is_file():
                req = cargo_requirements(toml.read_text("utf-8"))
                ver = "adblock-rust %s" % req.get("adblock", "?").lstrip("=") if "adblock" in req else ""
            add(record(top, "vendored", "runtime", ["vendor/%s" % top] + info["files"],
                       "built from ike-adblock/ (Rust, crates.io) with the package", ver or UNKNOWN,
                       notes=["imported by: %s" % ", ".join(info["files"][:6])]))
            continue
        package = module_package(top)
        how = covered(package)
        rec = add(record(top, "python-module", "optional" if info["optional"] else "runtime", info["files"],
                         "Arch Linux (pacman), package %s" % package, "through %s" % package,
                         provided_by=package, declared=how or "no"))
        if not how:
            findings.append({"finding": "used but not declared", "component": rec["id"],
                             "detail": "`import %s` in %s: package %s is not in the PKGBUILD%s"
                                       % (top, ", ".join(info["files"][:4]), package,
                                          " (the import is optional)" if info["optional"] else "")})
        elif how == "makedepends" or (how == "optdepends" and not info["optional"]):
            findings.append({"finding": "declared too weakly", "component": rec["id"],
                             "detail": "`import %s` is needed at run time, but %s is only in %s"
                                       % (top, package, how)})
        if top == "PyQt6":
            for full in info["names"]:
                if full == "PyQt6":
                    continue
                needs = qt_packages(full)
                qrec = add(record(full, "pyqt-module", "runtime", info["files"], "Arch Linux (pacman)",
                                  "through %s" % " + ".join(needs) if needs else UNKNOWN,
                                  provided_by=list(needs) if needs else UNKNOWN))
                if needs is None:
                    findings.append({"finding": "unknown provider", "component": qrec["id"],
                                     "detail": "%s: its Arch package is not known (QT_MODULE_PACKAGES)" % full})
                    continue
                missing = [p for p in needs if not covered(p)]
                qrec["declared"] = "yes" if not missing else "no"
                if missing:
                    findings.append({"finding": "used but not declared", "component": qrec["id"],
                                     "detail": "%s needs %s, not in the PKGBUILD depends"
                                               % (full, ", ".join(missing))})

    # programs ike/ starts
    for prog, where, how in tools:
        name = Path(prog).name
        package = TOOL_PACKAGES.get(name, "")
        rec = add(record(name, "runtime-tool", "runtime", where, "Arch Linux (pacman), package %s"
                         % (package or UNKNOWN), "through %s" % package if package else UNKNOWN,
                         provided_by=package or UNKNOWN, notes=["started by %s" % how]))
        if not package:
            findings.append({"finding": "unknown provider", "component": rec["id"],
                             "detail": "ike/ starts `%s` (%s): its Arch package is not known (TOOL_PACKAGES)"
                                       % (name, where)})
        elif name in DESKTOP_TOOLS and not covered(package):
            rec["declared"] = "the desktop's own (started only when installed)"
            rec["notes"].append("the desktop's own program: used only when the desktop has it")
        elif not covered(package):
            findings.append({"finding": "used but not declared", "component": rec["id"],
                             "detail": "ike/ starts `%s` (%s, %s): package %s is not in depends or optdepends"
                                       % (name, where, how, package)})
        else:
            rec["declared"] = covered(package)

    # Cargo.lock
    lock = root / "ike-adblock" / "Cargo.lock"
    if lock.is_file():
        crates = parse_cargo_lock(lock.read_text("utf-8"))
        roots = [c for c in crates if not c["source"]]
        direct = {d for c in roots for d in c["dependencies"]}
        reqs = cargo_requirements((root / "ike-adblock" / "Cargo.toml").read_text("utf-8")) \
            if (root / "ike-adblock" / "Cargo.toml").is_file() else {}
        seen = {}
        for c in crates:
            seen[c["name"]] = seen.get(c["name"], 0) + 1
        for c in crates:
            if not c["source"]:
                continue                                                    # ike-adblock itself
            kind = "adblock-engine" if c["name"] in ("adblock", "pyo3") else "crate"
            dist = "crates.io" if "crates.io-index" in c["source"] else c["source"].split("+")[0]
            rec = record(c["name"], kind, "direct" if c["name"] in direct else "transitive",
                         "ike-adblock/Cargo.lock", dist, c["version"])
            if seen[c["name"]] > 1:                 # two versions of one crate: one record each
                rec["id"] = "%s:%s@%s" % (kind, c["name"], c["version"])
            rec = add(rec)
            if c["name"] in reqs:
                rec["requirement"] = reqs[c["name"]]
        for name in sorted(set(reqs) - {c["name"] for c in crates}):
            findings.append({"finding": "not locked", "component": "crate:" + name,
                             "detail": "%s is in ike-adblock/Cargo.toml but not in Cargo.lock" % name})

    # tools/*.mjs
    npm, builtin = scan_mjs(root)
    for name, files in sorted(npm.items()):
        add(record(name, "npm", "build", files, "npm", UNKNOWN,
                   notes=["imported by a tool; no lockfile pins it"]))

    # workflows
    wf = scan_workflows(root)
    node_versions = sorted(wf["node"].items())
    if builtin or node_versions:
        add(record("Node.js", "node", "build", builtin + [f for _, fs in node_versions for f in fs],
                   "actions/setup-node", ", ".join(v for v, _ in node_versions) or UNKNOWN,
                   notes=["major version only: setup-node takes its newest release"] if node_versions else []))
    for (action, pin), info in sorted(wf["actions"].items()):
        pinned = bool(re.fullmatch(r"[0-9a-f]{40}", pin))
        rec = add(record("%s@%s" % (action, pin[:12]) if not pinned else action, "github-action", "ci",
                         info["files"], "GitHub Actions (github.com/%s)" % "/".join(action.split("/")[:2]),
                         "%s (%s)" % (info["comment"] or "?", pin) if pinned else pin or UNKNOWN,
                         pin=pin, release=info["comment"], pinned_sha=pinned))
        if not pinned:
            findings.append({"finding": "not pinned", "component": rec["id"],
                             "detail": "uses: %s@%s is not pinned to a commit" % (action, pin)})
    for path, files in sorted(wf["pip_files"].items()):
        for name, version in read_pins(root / path):
            add(record(name, "pypi-test", "test", [path] + sorted(files), "PyPI", version or "unpinned"))
    for name, info in sorted(wf["pip"].items()):
        rid = "pypi-test:" + name
        if rid in records:
            records[rid]["origin"] = sorted(set(records[rid]["origin"]) | info["files"])
            continue
        add(record(name, "pypi-ci", "ci", info["files"], "PyPI", info["version"] or "unpinned"))
    for (name, version), files in sorted(wf["cargo_install"].items()):
        add(record(name, "ci-tool", "ci", files, "crates.io (cargo install)", version))
    for channel, files in sorted(wf["rustup"].items()):
        add(record("Rust toolchain (CI)", "ci-runtime", "ci", files, "rustup", channel,
                   notes=["the %s channel: not pinned" % channel] if not re.match(r"^\d", channel) else []))
    for version, files in sorted(wf["python"].items()):
        add(record("Python %s (CI)" % version, "ci-runtime", "ci", files, "actions/setup-python", version))
    for image, files in sorted(wf["runners"].items()):
        add(record(image, "ci-runtime", "ci", files, "GitHub-hosted runner image", image))
    for image, files in sorted(wf["containers"].items()):
        add(record(image, "ci-runtime", "ci", files, "container image", image.split(":")[-1] if ":" in image
                   else UNKNOWN))
    for name, files in sorted(wf["apt"].items()):
        add(record(name, "ci-package", "ci", files, "Ubuntu apt (runner)", "the runner's archive (unpinned)"))

    # integrated resources
    res = root / "ike" / "resources"
    try:
        dr = json.loads((res / "darkreader-data.json").read_text("utf-8"))
        # 1.1.29: Dark Reader's engine left I.K.E.; its lists stay (data, no code: no advisory database)
        add(record("Dark Reader", "integrated", "runtime", "ike/resources/darkreader-data.json",
                   "git (https://github.com/darkreader/darkreader, default branch: its lists), rebuilt by "
                   "tools/build-darkreader-lists.py", "%s, lists %s (%s)" % (dr.get("version", "?"),
                                                                           str(dr.get("lists_commit", ""))[:10],
                                                                           dr.get("lists_date", "?")),
                   commit=dr.get("lists_commit", ""), git="https://github.com/darkreader/darkreader",
                   candidate="darkreader"))
    except (OSError, ValueError):
        pass
    try:
        ubo = json.loads((res / "ubo-scriptlets.json").read_text("utf-8"))
        add(record("uBlock Origin scriptlets", "integrated", "runtime", "ike/resources/ubo-scriptlets.json",
                   "git (%s, default branch), rebuilt by tools/build-ubo-scriptlets.mjs"
                   % ubo.get("source", "github.com/gorhill/uBlock"),
                   "%s (%s)" % (str(ubo.get("commit", ""))[:10], ubo.get("date", "?")),
                   commit=ubo.get("commit", ""), git=ubo.get("source", ""), candidate="ubo-scriptlets"))
    except (OSError, ValueError):
        pass
    # an entry of the manifest built by another builder of I.K.E.'s (1.1.24: KDE's Breeze icons): the
    # version in use is in the record its builder writes (the entry's .json file), its own candidate
    for cid, entry in sorted(_manifest_tool().components(root).items()):
        if not entry.get("build") or cid in ("darkreader", "ubo-scriptlets"):
            continue
        made = next((f for f in entry["files"] if f.endswith(".json")), "")
        try:
            info = json.loads((root / made).read_text("utf-8")) if made else {}
        except (OSError, ValueError):
            continue
        add(record(entry["name"], "integrated", "runtime", [made, "components.json"],
                   "components.json: %s, rebuilt by %s" % (
                       ", ".join("%s %s" % kv for kv in sorted(entry["upstream"].items())), entry["build"]),
                   "%s (%s)" % (info.get("version", "?"), str(info.get("commit", ""))[:10]),
                   candidate=cid, upstream_tag=info.get("tag", ""),
                   update_mode="candidate: automation/update/%s (components.json; tools/check-components.py "
                               "--only %s --apply, rebuilt by %s)" % (cid, cid, entry["build"])))
    # every other entry of the component manifest (components.json): a plain download, its own candidate
    for cid, entry in sorted(_manifest_tool().components(root).items()):
        if entry.get("download"):
            add(record(entry["name"], "integrated", "runtime", list(entry["files"]) + ["components.json"],
                       "components.json: %s" % ", ".join("%s %s" % kv for kv in sorted(entry["upstream"].items())),
                       entry.get("version", ""), candidate=cid,
                       update_mode="candidate: automation/update/%s (components.json; tools/check-components.py "
                                   "--only %s --apply, a download checked by its sha256)" % (cid, cid)))
    for entry in default_lists(root):
        add(record(entry.get("name") or entry["url"], "filter-list", "runtime", "ike/config.py DEFAULT_LISTS",
                   "HTTPS: %s" % urllib.parse.urlsplit(entry["url"]).hostname,
                   "not pinned (each browser downloads it)", url=entry["url"],
                   enabled=bool(entry.get("enabled", True))))
    return records, findings, notes


# --- available versions -------------------------------------------------------------------

class Net:
    """GET with a per-host failure limit: a host that does not answer is not asked again."""

    def __init__(self, get=None, ls_remote=None, offline=False, post=None):
        self.cc = None
        self._get = get
        self._post = post
        self._ls_remote = ls_remote
        self.offline = offline
        self.failures = {}
        self.hosts = {}

    def _fetch(self, url, timeout=30):
        if self._get:
            return self._get(url)
        if self.cc is None:
            self.cc = _components_tool()
        return self.cc.fetch(url, timeout=timeout)

    def get(self, url):
        host = urllib.parse.urlsplit(url).hostname or url
        if self.offline:
            raise LookupError("offline")
        if self.failures.get(host, 0) >= NETWORK_FAILURES:
            raise OSError("%s did not answer earlier in this run" % host)
        try:
            data = self._fetch(url)
            self.hosts.setdefault(host, "ok")
            return data
        except OSError as e:
            self.failures[host] = self.failures.get(host, 0) + 1
            self.hosts[host] = "unreachable: %s" % str(e)[:160]
            raise

    def json(self, url):
        return json.loads(self.get(url).decode("utf-8"))

    def post(self, url, payload):
        """POST of JSON (the OSV database's batch query), with the same per-host limit."""
        host = urllib.parse.urlsplit(url).hostname or url
        if self.offline:
            raise LookupError("offline")
        if self.failures.get(host, 0) >= NETWORK_FAILURES:
            raise OSError("%s did not answer earlier in this run" % host)
        try:
            if self._post is None and self._get is not None:
                # stand-ins for GET (the tests) and none for POST: never the real network
                raise OSError("no stand-in for POST %s" % url)
            data = self._post(url, payload) if self._post else _vulnerabilities_tool().post_json(url, payload)
            self.hosts.setdefault(host, "ok")
            return data
        except OSError as e:
            self.failures[host] = self.failures.get(host, 0) + 1
            self.hosts[host] = "unreachable: %s" % str(e)[:160]
            raise

    def ls_remote(self, url, *refs):
        """{ref: sha} of a git repository (git ls-remote), GitHub's tags with no API token."""
        host = urllib.parse.urlsplit(url).hostname or url
        if self.offline:
            raise LookupError("offline")
        if self.failures.get(host, 0) >= NETWORK_FAILURES:
            raise OSError("%s did not answer earlier in this run" % host)
        try:
            if self._ls_remote:
                out = self._ls_remote(url, *refs)
            else:
                done = subprocess.run(["git", "ls-remote", url, *refs], capture_output=True, text=True,
                                      timeout=60, check=False, env=dict(os.environ, GIT_TERMINAL_PROMPT="0"))
                if done.returncode:
                    raise OSError("git ls-remote %s: %s" % (url, done.stderr.strip()[:160]))
                out = done.stdout
            self.hosts.setdefault(host, "ok")
        except (OSError, subprocess.SubprocessError) as e:
            self.failures[host] = self.failures.get(host, 0) + 1
            self.hosts[host] = "unreachable: %s" % str(e)[:160]
            raise OSError(str(e)) from e
        refs_out = {}
        for line in out.splitlines():
            parts = line.split()
            if len(parts) == 2:
                refs_out[parts[1]] = parts[0]
        return refs_out


def vkey(version):
    return tuple(int(n) for n in re.findall(r"\d+", version or ""))


def _commit(version):
    """A commit hash (a component followed on a branch, 1.1.29): its digits say nothing about
    which is newer, so any other commit than the one in use is an update."""
    return re.fullmatch(r"[0-9a-f]{40}", str(version or "")) is not None


def stable(version):
    return re.fullmatch(r"v?[0-9]+(\.[0-9]+)*(\.post[0-9]+)?", version or "") is not None


def crate_index_path(name):
    n = name.lower()
    if len(n) <= 2:
        return "%d/%s" % (len(n), n)
    if len(n) == 3:
        return "3/%s/%s" % (n[0], n)
    return "%s/%s/%s" % (n[:2], n[2:4], n)


def compatible(old, new):
    """Cargo's semver compatibility (same major, or same minor for 0.x, same patch for 0.0.x)."""
    a, b = vkey(old), vkey(new)
    if not a or not b:
        return False
    if a[0] != 0:
        return a[0] == b[0]
    if len(a) > 1 and a[1] != 0:
        return len(b) > 1 and b[0] == 0 and a[1] == b[1]
    return a[:3] == b[:3]


def newest(versions):
    good = [v for v in versions if stable(v)]
    return max(good, key=vkey) if good else ""


def _crate_versions(net, name):
    versions = []
    for line in net.get(CRATES_SPARSE % crate_index_path(name)).decode("utf-8").splitlines():
        if line.strip():
            entry = json.loads(line)
            if not entry.get("yanked"):
                versions.append(entry["vers"])
    return versions


def _compare(rec, latest, source):
    rec["available"], rec["available_source"] = latest or UNKNOWN, source
    inst = rec["installed"]
    if not latest:
        rec["result"] = "unknown"
    elif not vkey(inst):
        rec["result"] = "ok"
        rec["compatibility"] = "installed version not pinned"
    elif (latest != inst) if (_commit(latest) or _commit(inst)) else vkey(latest) > vkey(inst):
        rec["result"] = "update available"
        if rec["compatibility"] == UNKNOWN:
            rec["compatibility"] = "newer version: to verify"
    else:
        rec["result"] = "ok"
        if rec["compatibility"] == UNKNOWN:
            rec["compatibility"] = "newest"


def _lookup(rec, net, arch_get, components, lists):
    """Fill the available version of one record (in a worker thread); never raises."""
    kind = rec["kind"]
    try:
        if kind in ("arch-package", "arch-optional", "arch-build", "build-tool", "runtime-tool", "python-module"):
            package = rec.get("provided_by") if kind in ("build-tool", "runtime-tool", "python-module") \
                else rec["name"]
            if not package or package == UNKNOWN:
                return
            latest = arch_get(package)
            rec["available"], rec["available_source"] = latest, "archlinux.org (core, extra)"
            inst = rec["installed"]
            if kind in ("arch-package", "arch-optional", "arch-build") and vkey(inst):
                rec["result"] = "changed since last tested" if inst != latest else "ok"
                rec["compatibility"] = ("changed since the last green arch.yml run on main: to verify"
                                        if inst != latest else "tested by the last green arch.yml run on main")
            else:
                rec["result"] = "ok"
                rec["compatibility"] = ("not tested by arch.yml (not installed there)"
                                        if kind == "arch-optional" else "not recorded by arch.yml")
        elif kind == "pyqt-module":
            return                                          # follows its packages (filled after)
        elif kind in ("crate", "adblock-engine", "ci-tool"):
            versions = _crate_versions(net, rec["name"])
            latest = newest(versions)
            _compare(rec, latest, "crates.io index")
            if rec["result"] == "update available" and kind != "ci-tool":
                same = newest([v for v in versions if compatible(rec["installed"], v)])
                rec["newest_compatible"] = same or UNKNOWN
                req = rec.get("requirement", "")
                if req.startswith("="):
                    rec["compatibility"] = "pinned exactly (%s): a new version is followed by check-components" % req
                elif same and vkey(same) >= vkey(latest):
                    rec["compatibility"] = "semver-compatible update (cargo update)"
                else:
                    rec["compatibility"] = "major update: needs a requirement change in the crate that uses it"
        elif kind in ("pypi-test", "pypi-ci"):
            data = net.json(PYPI_JSON % urllib.parse.quote(rec["name"]))
            _compare(rec, data.get("info", {}).get("version", ""), "pypi.org")
        elif kind == "npm":
            data = net.json(NPM_LATEST % urllib.parse.quote(rec["name"], safe="@"))
            _compare(rec, data.get("version", ""), "registry.npmjs.org")
        elif kind == "github-action":
            repo = "/".join(rec["name"].split("/")[:2])
            tags = net.ls_remote(GITHUB % repo, "refs/tags/v*")
            names = {t[len("refs/tags/"):].removesuffix("^{}"): sha for t, sha in tags.items()}
            latest = newest(names)
            rec["available"], rec["available_source"] = latest or UNKNOWN, "github.com tags (git ls-remote)"
            if latest:
                peeled = tags.get("refs/tags/%s^{}" % latest) or tags.get("refs/tags/%s" % latest, "")
                rec["available_sha"] = peeled
                current = rec.get("release") or ""
                if rec.get("pin") and peeled and rec["pin"] == peeled:
                    rec["result"], rec["compatibility"] = "ok", "pinned to the newest release"
                elif vkey(current) and vkey(latest) > vkey(current):
                    rec["result"] = "update available"
                    rec["compatibility"] = ("same major release" if vkey(latest)[0] == vkey(current)[0]
                                            else "new major release: read its notes")
                elif vkey(current):
                    rec["result"], rec["compatibility"] = "ok", "pinned to the newest release (by its comment)"
                else:
                    rec["result"] = "unknown"
            else:
                rec["result"] = "unknown"
        elif kind == "integrated":
            comp = _component_result(components, rec["name"])
            if comp:
                rec["available"] = comp.get("latest") or UNKNOWN
                rec["available_source"] = "tools/check-components.py (the builder's own check)"
                rec["result"] = ("builder refused" if comp.get("refused") else "unreachable" if comp.get("error")
                                 else "update available" if comp.get("update") else "ok")
                rec["compatibility"] = ("I.K.E.'s builder refused the new version: a person adapts it"
                                        if comp.get("refused") else "the builder accepts it" if comp.get("update")
                                        else rec["compatibility"])
                if comp.get("error"):
                    rec["available"] = "unknown (%s)" % comp["error"][:120]
            elif rec.get("git"):
                head = net.ls_remote(rec["git"], "HEAD").get("HEAD", "")
                rec["available"] = head[:10] if head else UNKNOWN
                rec["available_source"] = "git ls-remote (default branch)"
                rec["result"] = "ok" if head and head == rec.get("commit") else (
                    "new upstream commit" if head else "unknown")
                rec["compatibility"] = "an update only if the rebuilt files differ (tools/check-components.py)"
        elif kind == "filter-list":
            row = next((r for r in (lists or {}).get("lists", []) if r.get("url") == rec.get("url")), None)
            if row:
                rec["available"] = "downloaded today" if row.get("state") != "unreachable" else UNKNOWN
                rec["available_source"] = "tools/check-components.py --filter-lists"
                rec["result"] = row.get("state", UNKNOWN)
                if "network" in row:
                    rec["compatibility"] = "%d network / %d cosmetic rules read; %d unsupported, %d errors" % (
                        row["network"], row["cosmetic"], row.get("unsupported", 0), row.get("errors", 0))
    except LookupError as e:
        if str(e) == "offline":
            return
        rec["available"], rec["result"] = "unknown (%s)" % str(e)[:120], "unknown"
    except Exception as e:      # the network, a site, an answer laid out differently: never guessed
        rec["available"] = "unknown (source unreachable: %s)" % ("%s: %s" % (type(e).__name__, e))[:160]
        rec["result"] = "unreachable"


def _component_result(components, name):
    names = {"Dark Reader": "Dark Reader", "uBlock Origin scriptlets": "uBlock Origin scriptlets"}
    want = names.get(name, name)
    for c in (components or {}).get("components", []):
        if str(c.get("name", "")).startswith(want):
            return c
    return None


def lookup_versions(records, net, components=None, lists=None, arch_get=None):
    """Fill available versions (in parallel); every record gets its last check time."""
    stamp = now()
    cache = {}

    def arch(name):
        """The version in Arch's core/extra (check-components' arch_version), once per package."""
        if name not in cache:
            if net.offline:
                raise LookupError("offline")
            if arch_get:
                cache[name] = arch_get(name)
            else:
                if net.cc is None:
                    net.cc = _components_tool()
                cache[name] = net.cc.arch_version(name, get=lambda u, timeout=30: net.get(u))
        return cache[name]

    with concurrent.futures.ThreadPoolExecutor(max_workers=1 if net.offline else WORKERS) as pool:
        list(pool.map(lambda r: _lookup(r, net, arch, components, lists), list(records.values())))
    for rec in records.values():
        rec["last_check"] = stamp
    # a PyQt6 module follows its Arch packages
    for rec in records.values():
        if rec["kind"] == "pyqt-module" and isinstance(rec.get("provided_by"), list) and not net.offline:
            srcs = [records.get("arch-package:" + p) for p in rec["provided_by"]]
            rec["available"] = "; ".join("%s %s" % (p, s["available"] if s else NOT_CHECKED)
                                         for p, s in zip(rec["provided_by"], srcs))
            rec["available_source"] = "its Arch packages"
            if all(s and s["result"] not in ("unreachable", "unknown", NOT_CHECKED) for s in srcs):
                rec["result"] = "ok"
                rec["compatibility"] = "follows its Arch packages (arch.yml)"
    return records


def apply_advisories(records, advisories):
    """Vulnerabilities from a check already run: RustSec through cargo-deny (security.yml).
    advisories: {"state": "clean" | "found" | "unknown", "url", "date", "crates": [names],
    "advisories": [tools/security-fix.py's findings: id, crate, version, title, fix, url]}."""
    if not isinstance(advisories, dict):
        return records
    state, url = advisories.get("state"), advisories.get("url") or "?"
    crates = set(advisories.get("crates") or [])
    found = [f for f in advisories.get("advisories") or [] if isinstance(f, dict) and f.get("crate")]
    crates |= {f["crate"] for f in found}
    for rec in records.values():
        if rec["kind"] not in ("crate", "adblock-engine", "vendored"):
            continue
        if state == "clean":
            rec["vulnerabilities"] = "none known (RustSec via cargo-deny, %s)" % url
        elif state == "found":
            if not crates or rec["name"] in crates:
                rec["vulnerabilities"] = "RustSec advisory reported (cargo-deny, %s)" % url
                rec["result"] = "vulnerable" if rec["name"] in crates else rec["result"]
                mine = [f for f in found if f["crate"] == rec["name"] and
                        (not f.get("version") or f["version"] == rec["installed"])]
                if mine:
                    seen = set()
                    rec["advisories"] = [{"id": f["id"], "source": "RustSec (cargo-deny)",
                                          "summary": (f.get("title") or f.get("kind") or "")[:200], "aliases": [],
                                          "fixed": [f["fix"]] if f.get("fix") else [], "url": f.get("url") or url,
                                          "package": "%s %s (crates.io)" % (f["crate"], f.get("version", ""))}
                                         for f in mine if not (f["id"] in seen or seen.add(f["id"]))]
                    rec["vulnerabilities"] = "%d known (RustSec via cargo-deny, %s): %s" % (
                        len(rec["advisories"]), url, ", ".join(a["id"] for a in rec["advisories"]))
            else:
                rec["vulnerabilities"] = "none named for this crate (cargo-deny reported others: %s)" % url
        else:
            rec["vulnerabilities"] = "%s (cargo-deny's last result could not be read)" % NOT_CHECKED
    return records


def fill_tests(records):
    tc = _tests_tool()
    for rec in records.values():
        rec["tests_needed"] = tc.required_for([rec["kind"]])
    return records


def inventory(root=ROOT, offline=False, net=None, components=None, lists=None, arch_tested=None,
              advisories=None, arch_get=None):
    """The whole inventory as a dict (see the module's docstring)."""
    records, findings, notes = discover(root, arch_tested)
    fill_tests(records)
    net = net or Net(offline=offline)
    lookup_versions(records, net, components, lists, arch_get)
    apply_advisories(records, advisories)
    # WP7: OSV (PyPI, npm, GitHub Actions) and Arch's security tracker; offline: none asked
    vuln_sources = {} if net.offline else _vulnerabilities_tool().check(records, post=net.post, get=net.get)
    for f in findings:
        rec = records.get(f["component"])
        if rec is not None:
            rec["result"] = "finding: %s" % f["finding"]
            rec["notes"] = rec.get("notes", []) + [f["detail"]]
    counts = {}
    for rec in records.values():
        counts[rec["kind"]] = counts.get(rec["kind"], 0) + 1
    commit = ""
    try:
        commit = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True,
                                check=False).stdout.strip()
    except OSError:
        pass
    return {"schema": SCHEMA, "generated": now(), "commit": commit, "offline": bool(net.offline),
            "counts": dict(sorted(counts.items())), "total": len(records),
            "components": sorted(records.values(), key=lambda r: (r["kind"], r["name"].lower())),
            "findings": findings, "notes": notes, "sources": dict(sorted(net.hosts.items())),
            "vulnerability_sources": vuln_sources,
            "advisories_state": (advisories or {}).get("state", "unknown") if isinstance(advisories, dict)
            else "unknown"}


# --- report ------------------------------------------------------------------------------

def _md(text):
    return str(text).replace("|", "\\|").replace("\n", " ")


def updates_of(inv):
    return [r for r in inv["components"] if r["result"] in ("update available", "changed since last tested",
                                                             "builder refused", "vulnerable")]


def to_markdown(inv, full=True):
    out = ["### Inventory of the external components", "",
           "%d components found in the repository (commit `%s`), checked %s UTC by `tools/inventory.py`%s." % (
               inv["total"], (inv.get("commit") or "?")[:10], inv["generated"][:16].replace("T", " "),
               " (offline: no available versions read)" if inv.get("offline") else ""), "",
           "| Kind | Components |", "|---|---|"]
    out += ["| %s | %d |" % (k, n) for k, n in inv["counts"].items()]
    out += ["", "#### Findings", ""]
    if inv["findings"]:
        out += ["- **%s**: `%s`: %s" % (f["finding"], f["component"], _md(f["detail"])) for f in inv["findings"]]
    else:
        out.append("None: every module, program and build command is covered by a declared package.")
    ups = updates_of(inv)
    out += ["", "#### Newer versions or changes to verify", ""]
    if ups:
        out += ["| Component | Kind | In use | Available | Compatibility | Update mode |", "|---|---|---|---|---|---|"]
        out += ["| %s | %s | %s | %s | %s | %s |" % (_md(r["name"]), r["kind"], _md(r["installed"]),
                                                     _md(r["available"]), _md(r["compatibility"]),
                                                     _md(r["update_mode"])) for r in ups]
    else:
        out.append("None.")
    out += ["", "#### Known vulnerabilities", ""]
    vulnerable = [r for r in inv["components"] if r.get("advisories")]
    if vulnerable:
        out += ["| Component | Kind | Advisory | Fixed in | Source |", "|---|---|---|---|---|"]
        out += ["| %s | %s | [%s](%s) %s | %s | %s |" % (
            _md(r["name"]), r["kind"], a["id"], a.get("url", ""), _md(a.get("summary", ""))[:120],
            _md(", ".join(a.get("fixed") or [])) or "**no fix upstream**", a.get("source", ""))
            for r in vulnerable for a in r["advisories"]]
    else:
        out.append("None known by the sources that answered.")
    states = dict(inv.get("vulnerability_sources") or {})
    if states:
        out += ["", "Vulnerability sources: " + "; ".join("%s %s" % (h, s) for h, s in sorted(states.items()))]
        down = [h for h, s in states.items() if s != "ok"]
        if down:
            out.append("Their components are **not checked** today (never \"none known\"): %s." % ", ".join(down))
    elif inv.get("offline"):
        out.append("Vulnerability sources: not asked (offline): every component but the crates is not checked.")
    unreachable = [r for r in inv["components"] if r["result"] == "unreachable"]
    if unreachable:
        out += ["", "Not checked today (source unreachable): %s." % ", ".join(r["name"] for r in unreachable[:30])]
    if inv.get("sources"):
        out += ["", "Sources: " + "; ".join("%s %s" % (h, s) for h, s in inv["sources"].items())]
    if full:
        out += ["", "<details><summary>Every component</summary>", "",
                "| Component | Kind | Type | In use | Available | Result | Vulnerabilities | Tests needed |",
                "|---|---|---|---|---|---|---|---|"]
        out += ["| %s | %s | %s | %s | %s | %s | %s | %s |" % (
            _md(r["name"]), r["kind"], r["type"], _md(r["installed"]), _md(r["available"]), _md(r["result"]),
            _md(r["vulnerabilities"]), ", ".join(r["tests_needed"])) for r in inv["components"]]
        out += ["", "</details>"]
    return "\n".join(out) + "\n"


def _read_json(path):
    if not path:
        return None
    try:
        return json.loads(Path(path).read_text("utf-8"))
    except (OSError, ValueError):
        return None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--json", help="write the inventory as JSON")
    ap.add_argument("--markdown", help="write the summary as Markdown")
    ap.add_argument("--offline", action="store_true", help="read the repository only, no available versions")
    ap.add_argument("--components", help="tools/check-components.py --json report (the builders' own check)")
    ap.add_argument("--lists", help="tools/check-components.py --filter-lists report")
    ap.add_argument("--arch-tested", help="tools/check-components.py --save-arch-tested file")
    ap.add_argument("--advisories", help="cargo-deny's last result: {state, url, date, crates}")
    ap.add_argument("--root", default=str(ROOT), help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    inv = inventory(Path(args.root), offline=args.offline, components=_read_json(args.components),
                    lists=_read_json(args.lists), arch_tested=_read_json(args.arch_tested),
                    advisories=_read_json(args.advisories))
    if args.json:
        Path(args.json).write_text(json.dumps(inv, indent=1) + "\n", "utf-8")
    text = to_markdown(inv)
    if args.markdown:
        Path(args.markdown).write_text(text, "utf-8")
    print(to_markdown(inv, full=False), end="")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write("components=%d\nfindings=%d\nupdates=%d\n" % (inv["total"], len(inv["findings"]),
                                                                  len(updates_of(inv))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
