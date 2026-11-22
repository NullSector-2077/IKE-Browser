#!/usr/bin/env python3
"""The merge of the automation's own fully verified pull requests (no AI here).

Called by .github/workflows/automerge.yml when a check of a pull request ends
(or by a dispatch from the automation's own Tests, Security and Arch Linux
runs), from main's own copy of this file: a pull request cannot change the
rules it is judged by, and no agent merges its own work.

**The verified merge** (2026-11-22, the owner's decision: "the workflow merges
by itself when everything is green and verified, then the signing notice").
Only the automation's own pull requests, and only when FULLY VERIFIED:

- the daily maintenance candidate (automation/daily-maintenance: the update's
  own "maintenance:" commit and the automatic fix's commits), an AutoFix fix
  (automation/autofix-main: every commit one the fix wrote itself) or an
  isolated update (automation/update/...: "security: ... (cargo update, no
  AI)" commits and the automatic fix's), in this repository, into main;
- every check of its last commit ended and passed, and "tests", "sandbox",
  "rust-advisories" (Security) and "Arch Linux" are among them;
- every category tools/test-categories.py requires for the kinds of the
  components it changes (merge_required) passed on that commit: nothing "not
  verified", the licences included (the "Licences" step: cargo-deny and the
  licence files), and no skipped test that no other check of the commit runs
  (unexpected_skips);
- no test file changed or removed, no protected file (the guard's
  FORBIDDEN_FILES) and no workflow; the update's commits change only what an
  update may change (UPDATE_COMMITS, as daily-maintenance.yml checks), the
  version files only by the version; the automatic fix's files follow the
  1.1.19 rules below;
- no open security finding: the issue "Sandbox tests failed on main", the
  "Rust advisories" (unless this commit's own RustSec check passed: it is free
  of them), or a security entry of the maintenance ledger not passed;
- main's version is not published yet, or the pull request raises it (or it
  ships nothing, as a candidate of the test packages). Since 2026-11-22 (the
  owner's decision: everything automatic and verified converges into main,
  then one notice to sign) several merges by themselves go into the same
  unpublished version: a pull request whose raise is main's unpublished
  version, or that raises nothing because main is raised already, merges; a
  second raise on top (1.1.24 while 1.1.23 is not published) waits for a
  person (version_rule; M9's "one merge per unsigned version" is dropped for
  the automation's own pull requests).

**The refresh** (the same decision). A fully verified candidate that is
behind main (or conflicts with it) is not merged as it is: main is merged
into its branch (git merge-tree, no AI), CHANGELOG.md resolved as one
"## <version>" heading with the union of the bullet lines, the version files
as main's when main's version is the candidate's own, any other conflict left
for a person (and the ledger); the commit "refresh: main <sha> into <branch>
(tools/automerge.py, no AI)" is pushed to the automation's branch with the
workflow's token (never to main), and Tests, Security and Arch Linux start on
it again; when they pass it is judged again and merged. The merge accepts
such a commit only when it is exactly that: two parents, the second one in
main, and the tree this file computes again from them (refresh_problem).
After every merge the other open pull requests of the automation are judged
again (a dispatch of automerge.yml for each), so they converge one after
another; release-ready.yml says once per version that it is ready to sign.

Then it is merged with the workflow's token at exactly that commit, and the
tests, the security tests and the Arch tests of main start; when they pass,
release-ready.yml tells the owner a version is ready to sign (tests.yml and
security.yml, job merge-ready). Signing and publishing stay with the owner.

A fix of ChatGPT (chatgpt/..., no "trial", no maintenance commit) that would
have merged in 1.1.19 is only marked ready: it waits for the owner's order
(CLAUDE.md), and so does every pull request of a person. A fix of the
automatic fix (and every file it touches on a candidate) must also change only
existing Python modules of the interface under ike/ (and docs/), with no added
line that reaches the environment, the network, the system or the test run,
no module that decides the user's safety (PERSON_FILES), and the version
files exactly as the automation raises the version (hunks read by their
counts).

Anything short of fully verified waits: one comment names the owner (edited,
never repeated, when the reason changes) and the ledger shows it as
needs-person, or blocked for a security finding (tools/maintenance-ledger.py
reads the comment's verdict mark).

The full chain (2026-11-22, the last block): one candidate per component on
automation/update/<id> (tools/update-candidates.py: its own "update: <id> ...
(no AI)" commit may change only its id's files, the licences and the version),
the workflows' pins on automation/update/ci-<name> (tools/ci-pins.py: every
changed workflow line one pin of that name, the same action, a commit that
`git ls-remote` shows is the release tag beside it, the tool's own commit; any
other workflow change waits for a person), the PKGBUILD's dependencies on
automation/update/pkgbuild (tools/pkgbuild-sync.py's rule), a builder's
re-anchoring on automation/builder/<id> (the automatic fix's change of the
builder only as tools/builder-anchor.py allows) and, on a candidate of the
engine (adblock, pyo3, a major crate), the automatic fix's change of I.K.E.'s
wrapper (ike-adblock/src/*.rs, vendor/adblock/__init__.py, ike/blocker.py)
with no unsafe code, process, file, network or environment access added
(wrapper_problem). A fix for Arch's testing packages
(automation/update/arch-testing-<date>) needs "Arch Linux (testing)" too.

    automerge.py --repo OWNER/NAME --sha HEAD_SHA [--dry-run]
"""

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OWN_JOBS = {"merge", "merge-ready", "hand-over", "sandbox-issue", "advisories-issue", "report", "tell"}
BAD_CONCLUSIONS = {"failure", "cancelled", "timed_out", "startup_failure", "stale"}
# what the automatic fix writes (autofix.yml); anything else on its branch
# (a trial, by any spelling) is never merged
AUTOFIX_COMMIT = re.compile(r"^autofix: attempt \d+ after a failure of ")
TRIAL = re.compile(r"trial", re.I)
VERSION = re.compile(r"\d+\.\d+\.\d+(?:-\d+)?")
VERSION_LINES = {
    "ike/__init__.py": re.compile(r'^__version__ = "\d+\.\d+\.\d+"$'),
    "PKGBUILD": re.compile(r"^pkg(ver|rel)=[0-9.]+$"),
    # the two lines tools/prepare-maintenance.py writes
    "README.md": re.compile(r"^\*\*Version \d+\.\d+\.\d+\*\* - see \[CHANGELOG\.md\]\(CHANGELOG\.md\)\.$"
                            r"|^[^`]*ike-browser-\d+\.\d+\.\d+-\d+-x86_64\.pkg\.tar\.zst[^`]*$"),
}
NEVER_PREFIXES = (".github/", "tests/", "tools/", "ike-adblock/", "vendor/", "ike/resources/")
NEVER_FILES = {"PKGBUILD.in", "ike/blocker.py", "ike/scriptlets.py"}
# modules where one line decides the user's safety: always read by a person
# (review 2 of 1.1.19, C1; the update channel, the vault, the network checks)
PERSON_FILES = {"ike/__main__.py", "ike/app.py", "ike/config.py", "ike/osinfo.py", "ike/passwords.py",
                "ike/userscripts.py", "ike/extensions.py", "ike/webview.py", "ike/shields.py", "ike/doh.py",
                "ike/updater.py", "ike/sitedata.py", "ike/drm.py", "ike/chromever.py", "ike_boot.py"}
# added lines that can change where updates come from, reach the network or the
# system, or tell a test run from a real one: a person reads them (C1, H4)
PERSON_LINES = re.compile(
    r"\bos\.environ\b|\benviron\b|\bputenv\b|\bgetenv\b|IKE_\w+|update\.json|\bpubkey\b|\bsys\.modules\b"
    r"|__import__|\bimportlib\b|\bsubprocess\b|\bsocket\b|\burllib\b|\bhttps?\b|://|\bexec\s*\(|\beval\s*\("
    r"|\bcompile\s*\(|\bbase64\b|\batexit\b|\bRUNNER_|\bGITHUB_|\bCI\b|\bpytest\b|\bunittest\b"
    r"|\bsys\._getframe\b|\binspect\b|\bgc\.get_|\bsetattr\s*\(|\bglobals\s*\(|\bopen\s*\(|\bos\.system\b"
    r"|\bctypes\b|\bpickle\b|\bmarshal\b|\bsignal\b|\bthreading\b|QProcess|QNetwork|runJavaScript"
    r"|setUrlRequestInterceptor|setFeaturePermission|QWebEngineScript")


# What a change to a Python module may not add without a person (review 4 of
# 1.1.19, N1: a list of words did not see an alias, a name built from parts,
# a new address or a test told by the command line). Judged on the syntax
# trees of the file before and after the change: anything of these kinds
# that the new file has more of than the old one keeps it for a person.
RISKY_CALLS = {"getattr", "setattr", "delattr", "vars", "globals", "locals", "eval", "exec", "compile",
               "__import__", "open", "input", "breakpoint", "type", "super"}
RISKY_METHODS = {"system", "popen", "spawn", "run", "call", "check_output", "Popen", "exec_module",
                 "import_module", "load_source", "platformName", "setUrlRequestInterceptor", "runJavaScript",
                 "setFeaturePermission", "setHttpUserAgent", "setDnsMode", "get", "post", "urlopen",
                 "setRawHeader", "insert", "setProxy", "write_text", "write_bytes", "unlink", "rmtree"}
RISKY_ATTRS = {"environ", "argv", "modules", "path", "executable", "stdin", "stdout", "stderr", "settrace",
               "setprofile", "_getframe", "f_back", "__dict__", "__class__", "__globals__", "__code__",
               "__builtins__", "__subclasses__", "__bases__", "__mro__", "f_globals", "f_locals"}
RISKY_NAMES = {"os", "sys", "subprocess", "socket", "urllib", "http", "importlib", "builtins", "ctypes",
               "pickle", "marshal", "base64", "atexit", "inspect", "gc", "threading", "signal", "shutil",
               "QProcess", "QNetworkAccessManager", "QNetworkRequest", "QWebEngineScript", "QLibrary"}
RISKY_WORDS = ("://", "environ", "ike_", "pytest", "github_", "runner_", "offscreen", "update.json", "pubkey",
               "conftest", "argv", "sandbox", "--")


def risky_features(source):
    """A Counter of the risky things in a Python source, or None when it does not parse."""
    import ast
    import collections
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return None
    out = collections.Counter()
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mod = getattr(node, "module", None) or ""
            for a in node.names:
                out["import %s.%s as %s" % (mod, a.name, a.asname)] += 1
                imported.add(a.asname or a.name.split(".")[0])
        elif isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name) and f.id in RISKY_CALLS:
                out["call %s()" % f.id] += 1
            elif isinstance(f, ast.Attribute) and f.attr in RISKY_METHODS:
                out["call .%s()" % f.attr] += 1
        elif isinstance(node, ast.Attribute):
            if node.attr in RISKY_ATTRS:
                out["attribute .%s" % node.attr] += 1
        elif isinstance(node, ast.Name):
            if node.id in RISKY_NAMES:
                out["name %s" % node.id] += 1
        elif isinstance(node, ast.Constant) and isinstance(node.value, (str, bytes)):
            text = node.value.decode("latin-1") if isinstance(node.value, bytes) else node.value
            low = text.lower()
            for w in RISKY_WORDS:
                if w in low:
                    out["text with %r" % w] += 1
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            out["global or nonlocal"] += 1
        elif isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for t in targets:
                for sub in ast.walk(t):
                    if isinstance(sub, ast.Attribute):
                        base = sub.value
                        while isinstance(base, ast.Attribute):
                            base = base.value
                        if not (isinstance(base, ast.Name) and base.id in ("self", "cls")):
                            out["assignment to %s" % ast.unparse(sub)[:60]] += 1
    for name in imported:
        out["module name in use: %s" % name] += 0       # imports are counted above
    return out


def tree_problem(name, old, new):
    """"" when the new source adds nothing risky to the old one (both whole files)."""
    a, b = risky_features(old or ""), risky_features(new or "")
    if a is None or b is None:
        return "%s: the file does not parse" % name
    more = b - a
    if more:
        return "%s: %s (a person reads it)" % (name, sorted(more)[0])
    return ""


DOC_LINK = re.compile(r"https?://(?!github\.com/NullSector-2077/IKE-Browser[/)\s])")


def _guard():
    spec = importlib.util.spec_from_file_location("guard", ROOT / "tools" / "check-autofix-patch.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def hunks(patch):
    """[(new_start, removed lines, added lines)] of a file's patch as GitHub
    gives it, read by the counts of each hunk header (a content line "++x"
    is content, not a header: review 2 of 1.1.19, M3). None if unreadable."""
    out, old_left, new_left = [], 0, 0
    for line in (patch or "").split("\n"):
        if old_left > 0 or new_left > 0:
            sign, text = line[:1] or " ", line[1:]
            if sign == "\\":
                continue
            if sign == " ":
                old_left, new_left = old_left - 1, new_left - 1
            elif sign == "-":
                old_left -= 1
                out[-1][1].append(text)
            elif sign == "+":
                new_left -= 1
                out[-1][2].append(text)
            else:
                return None
            continue
        if not line:
            continue
        m = _HUNK.match(line)
        if not m:
            return None
        old_left = int(m.group(2) or 1)
        new_left = int(m.group(4) or 1)
        out.append((int(m.group(3)), [], []))
    if old_left > 0 or new_left > 0:
        return None
    return out


def changed_lines(patch):
    """The added and removed lines of a patch, without the +/- (hunk-accurate)."""
    parts = hunks(patch) or []
    return [line for _, removed, added in parts for line in removed + added]


def version_problem(name, patch, repo):
    """"" when the change only moves the version, as the automatic fix does."""
    parts = hunks(patch)
    if parts is None:
        return "%s: change not readable" % name
    removed = [x for _, r, _a in parts for x in r]
    added = [x for _, _r, a in parts for x in a]
    if name == "CHANGELOG.md":
        # only new entries: a version heading, list items, blank lines, linking
        # nowhere but this repository; nothing removed. (They are added to the
        # top section, or appended to it when its version is not out yet:
        # tools/prepare-maintenance.py; the notes of a release come only from
        # its own section.)
        links = re.findall(r"https?://[^\s)>\]]+", "\n".join(added))
        shape = re.compile(r"^(## \d+\.\d+\.\d+|- .*|  .*|)$")
        if [x for x in removed if x.strip()] or any(not shape.match(x) for x in added) or "`" in "".join(added) \
                or any(not u.startswith("https://github.com/%s/" % repo) for u in links):
            return "%s: more than new entries" % name
        return ""
    rule = VERSION_LINES[name]
    if any(not rule.search(x) for x in removed + added if x.strip()):
        return "%s: more than the version" % name
    if sorted(VERSION.sub("V", x) for x in removed) != sorted(VERSION.sub("V", x) for x in added):
        return "%s: more than the version" % name
    # the version moves by one step at most (1.1.20 -> 1.1.21), never a jump (N1)
    for old, new in zip(sorted(removed), sorted(added)):
        a = re.search(r"(\d+)\.(\d+)\.(\d+)", old)
        b = re.search(r"(\d+)\.(\d+)\.(\d+)", new)
        if a and b:
            x, y = tuple(map(int, a.groups())), tuple(map(int, b.groups()))
            if y != x and y != (x[0], x[1], x[2] + 1):
                return "%s: the version jumps (%s -> %s)" % (name, a.group(0), b.group(0))
    return ""


def file_problem(f, guard_allowed, repo=""):
    """Why this changed file keeps the pull request for a person, or ""."""
    name = f.get("filename", "")
    if f.get("status") in ("removed", "renamed", "copied") or f.get("previous_filename"):
        return "%s: removed or renamed" % name
    if f.get("status") == "added":
        return "%s: a new file" % name
    if f.get("patch") is None:
        return "%s: change not readable" % name
    if name == "CHANGELOG.md" or name in VERSION_LINES:
        return version_problem(name, f["patch"], repo)
    if name.startswith(NEVER_PREFIXES) or name in NEVER_FILES:
        return "%s: tests, workflows, tools, page scripts or the ad blocker" % name
    why = guard_allowed(name)
    if why:
        return "%s: %s" % (name, why)
    if not name.startswith(("ike/", "docs/")) or not name.endswith((".py", ".md")):
        return "%s: outside ike/ and docs/" % name
    if name in PERSON_FILES:
        return "%s: a module a person reads before it changes" % name
    parts = hunks(f["patch"])
    if parts is None:
        return "%s: change not readable" % name
    if name.endswith(".py"):
        for _start, _removed, added in parts:
            for line in added:
                if PERSON_LINES.search(line):
                    return "%s: a line a person must read (%s)" % (name, line.strip()[:80])
        if "old_source" not in f or "new_source" not in f:
            return "%s: the whole file could not be read" % name
        why = tree_problem(name, f["old_source"], f["new_source"])
        if why:
            return why
    if name.endswith(".md"):
        # the owner pastes commands from the documents: no new link outside
        # the repository, no code (N1)
        for _start, _removed, added in parts:
            for line in added:
                if DOC_LINK.search(line) or "`" in line or line.startswith(("    ", "\t")):
                    return "%s: a link or code a person must read (%s)" % (name, line.strip()[:80])
    return ""


# --- the verified merge (2026-11-22) ------------------------------------------------

CANDIDATE = "automation/daily-maintenance"
FIX_MAIN = "automation/autofix-main"
UPDATE_PREFIX = "automation/update/"
BUILDER_PREFIX = "automation/builder/"
ARCH_TESTING_PREFIX = UPDATE_PREFIX + "arch-testing-"
ARCH_TESTING_CHECK = "Arch Linux (testing)"
# the owner's words: "tests, sandbox, Security, Arch Linux"
VERIFIED_CHECKS = ("tests", "sandbox", "rust-advisories", "Arch Linux")
# what an update may change (the same list as daily-maintenance.yml's check of the candidate)
UPDATE_FILES = ("ike-adblock/Cargo.toml", "ike-adblock/Cargo.lock", "ike-adblock/src/lib.rs",
                "ike/resources/ubo-scriptlets.json", "ike/resources/darkreader", "tools/test-requirements.txt",
                "docs/THIRD-PARTY.md", "licenses/")
VERSION_FILES = ("ike/__init__.py", "PKGBUILD", "README.md", "CHANGELOG.md")
# the commits the automation itself writes on its own branches: (first line, branches (a name, or a
# prefix ending in "-"), what it may change, whether the version files may move)
UPDATE_COMMITS = (
    (re.compile(r"^maintenance: "), (CANDIDATE,), UPDATE_FILES, True),
    # since the full chain (item 5) a security update raises the version too when main's is published
    (re.compile(r"^security: .+ \(cargo update, no AI\)$"), (UPDATE_PREFIX + "security-",),
     ("ike-adblock/Cargo.lock", "docs/THIRD-PARTY.md", "licenses/"), True),
)
# I.K.E.'s wrapper of the engine, which the automatic fix may adapt on a candidate of the engine
WRAPPER_FILES = ("vendor/adblock/__init__.py", "ike/blocker.py")
WRAPPER_RS = re.compile(r"^ike-adblock/src/[A-Za-z0-9_/]+\.rs$")
# what an added line of Rust in the wrapper may not bring without a person
RUST_RISKY = re.compile(r"\bunsafe\b|std::(process|net|fs|env|os|ffi|ptr|mem::transmute)|\bCommand\b"
                        r"|include_(bytes|str)!|\benv!|option_env!|\basm!|global_asm!|\bextern\b|#\s*\[\s*link"
                        r"|#\s*\[\s*no_mangle|\blibc\b|\bTcp|\bUdp|\bFile::|\bOpenOptions\b|https?://|\bprintln!")
TEST_FILE = re.compile(r"(^|/)(tests?/|conftest\.py$|test_[^/]*\.py$|[^/]*_test\.py$)")
NOT_SHIPPED = ("tools/", "tests/", "docs/", ".github/")
SECURITY_WHY = "an open security finding"
VERDICT = "<!-- automerge-verdict: %s %s -->"     # read back by tools/maintenance-ledger.py


def verified_branch(ref):
    """A branch of the automation whose fully verified pull request merges by itself."""
    return ref in (CANDIDATE, FIX_MAIN) or (ref.startswith(UPDATE_PREFIX) and len(ref) > len(UPDATE_PREFIX)) or \
        (ref.startswith(BUILDER_PREFIX) and bool(_candidates().id_of_branch(ref)))


def _candidates():
    return _tool("update-candidates")


def candidate_id(ref):
    """The full chain's candidate id of the branch (tools/update-candidates.py), or ""."""
    return _candidates().id_of_branch(ref) if ref.startswith((UPDATE_PREFIX, BUILDER_PREFIX)) else ""


def wrapper_problem(f):
    """Why the automatic fix's change of I.K.E.'s wrapper keeps the pull request for a person, or "".
    Rust: no added unsafe code, process, file, network, environment or foreign code; Python: the
    1.1.19 rules of lines and syntax trees (nothing risky the old file did not have)."""
    name = f.get("filename", "")
    if f.get("status") != "modified" or f.get("patch") is None:
        return "%s: not a plain change of the wrapper" % name
    parts = hunks(f["patch"])
    if parts is None:
        return "%s: change not readable" % name
    for _start, _removed, added in parts:
        for line in added:
            if name.endswith(".rs") and RUST_RISKY.search(line):
                return "%s: a line a person must read (%s)" % (name, line.strip()[:80])
            if name.endswith(".py") and PERSON_LINES.search(line):
                return "%s: a line a person must read (%s)" % (name, line.strip()[:80])
    if name.endswith(".py"):
        if "old_source" not in f or "new_source" not in f:
            return "%s: the whole file could not be read" % name
        return tree_problem(name, f["old_source"], f["new_source"])
    return ""


def is_wrapper(name):
    return name in WRAPPER_FILES or bool(WRAPPER_RS.match(name))


def _tool(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), ROOT / "tools" / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def lock_moves(patch, names=("adblock", "pyo3")):
    """True when a Cargo.lock patch moves one of these crates (or cannot be read: fail closed)."""
    if patch is None:
        return True
    current = ""
    for line in patch.split("\n"):
        text = line[1:] if line[:1] in ("+", "-", " ") else line
        if text.startswith("[[package]]"):
            current = ""
        m = re.match(r'^name = "([^"]+)"$', text)
        if m:
            current = m.group(1)
        elif line[:1] in ("+", "-") and text.startswith("version = ") and current in names:
            return True
    return False


def kinds_of(files, ref=""):
    """The kinds of components (tools/inventory.py) a pull request changes, read from its files (and,
    for a candidate of the full chain, the kinds its id updates)."""
    kinds = set()
    cid = candidate_id(ref)
    if cid:
        kinds.update(_candidates().spec(cid).get("kinds") or ())
    for f in files:
        name = f.get("filename", "")
        if name in VERSION_FILES or name.startswith("licenses/") or name == "docs/THIRD-PARTY.md":
            continue
        if name.startswith(".github/"):
            kinds.add("github-action")
            continue
        if name == "ike-adblock/Cargo.toml" or name.startswith(("ike-adblock/src/", "vendor/adblock/")):
            kinds.add("adblock-engine")
        elif name == "ike-adblock/Cargo.lock":
            kinds.add("crate")
            if lock_moves(f.get("patch")):
                kinds.add("adblock-engine")
        elif name == "tools/test-requirements.txt":
            kinds.add("pypi-test")
        else:
            kinds.add("integrated")
    return sorted(kinds) or ["integrated"]


def verification_problems(evidence, kinds):
    """What keeps the commit from being fully verified (a list; empty: fully verified).

    evidence: {"runs": {"tests.yml", "arch.yml", "security.yml": run or None} (as
    tools/maintenance-ledger.py's run_info reads them), "skips": the skipped tests of its Tests run,
    or None when they could not be read}."""
    tc = _tool("test-categories")
    runs = evidence.get("runs") or {}
    skips = evidence.get("skips")
    rows = tc.verify(tc.merge_required(kinds), tc.results_from_runs(runs), skips)
    out = ["%s %s (%s)" % (r["category"], r["state"], r["detail"]) for r in rows if r["state"] != "passed"]
    for s in tc.unexpected_skips(skips):
        out.append("a required test was skipped: %s (%s)" % (s.get("test", "?"), (s.get("reason") or "")[:120]))
    return out


def open_findings(issues, ledger, advisories_passed):
    """The security findings still open (a list of reasons).

    issues: the bot's open issues, each with its "labels"; ledger: tools/maintenance-ledger.py's
    ledger (None: no ledger issue; "unreadable": one that could not be read); advisories_passed: this
    commit's own RustSec check (cargo-deny on its Cargo.lock) passed."""
    out = []
    for issue in issues or ():
        labels = {(x.get("name") if isinstance(x, dict) else x) for x in issue.get("labels") or ()}
        if "sandbox-failed" in labels:
            out.append("the sandbox tests failed on main (issue #%s)" % issue.get("number"))
        elif "rust-advisories" in labels and not advisories_passed:
            out.append("RustSec advisories (issue #%s)" % issue.get("number"))
    if ledger == "unreadable":
        out.append("the maintenance ledger could not be read")
    elif isinstance(ledger, dict):
        for key, e in sorted((ledger.get("entries") or {}).items()):
            if not e.get("security") or e.get("state") == "passed":
                continue
            if e.get("source_host") == "cargo-deny" and advisories_passed:
                continue                     # this commit's own cargo-deny says it is free of it
            out.append("%s (%s in the maintenance ledger)" % (key, e.get("state")))
    return out


def _on(ref, branches):
    return any(ref == b or (b.endswith("-") and ref.startswith(b)) for b in branches)


def chain_commit_problem(ref, first, files):
    """None when the commit is not one of the full chain's own tools; else why it keeps the pull
    request for a person, or "" (an update, a CI pin, the PKGBUILD's dependencies)."""
    uc = _candidates()
    cid = candidate_id(ref)
    if uc.UPDATE_COMMIT.match(first):
        return uc.commit_problem(cid, first, files) if cid else "an update commit on another branch"
    m = _tool("ci-pins").COMMIT.match(first)
    if m:
        if cid != m.group(1) or not ref.startswith(UPDATE_PREFIX):
            return "a CI pin's commit on another branch than its own (%s)" % first[:60]
        bad = [n for n in files if n and not n.startswith((".github/workflows/", ".github/actions/"))]
        return "%s: the CI pin's commit may change only the workflows" % bad[0] if bad else ""
    if _tool("pkgbuild-sync").COMMIT.match(first):
        if cid != "pkgbuild":
            return "a PKGBUILD commit on another branch than automation/update/pkgbuild"
        bad = [n for n in files if n and n not in VERSION_FILES]
        return "%s: the PKGBUILD's commit may change only the PKGBUILD and the version" % bad[0] if bad else ""
    return None


def commit_problem(ref, commits):
    """Why the commits of the candidate or of an update keep it for a person, or ""."""
    if not commits:
        return "no commits"
    for c in commits:
        msg = (c.get("commit") or {}).get("message") or ""
        first = msg.split("\n", 1)[0]
        if TRIAL.search(first):
            return "a trial"
        if AUTOFIX_COMMIT.match(msg):
            continue
        if c.get("files") is None:
            return "the files of a commit could not be read (%s)" % first[:60]
        why = chain_commit_problem(ref, first, c["files"])
        if why is not None:
            if why:
                return why
            continue
        rule = [u for u in UPDATE_COMMITS if u[0].match(first) and _on(ref, u[1])]
        if not rule:
            return "a commit the automation did not write (%s)" % first[:60]
        if c.get("files") is None:
            return "the files of a commit could not be read (%s)" % first[:60]
        _rx, _branches, allowed, version = rule[0]
        for name in c["files"]:
            if not (version and name in VERSION_FILES) and not name.startswith(allowed):
                return "%s: the update's commit may not change it" % name
    return ""


def origins(commits):
    """{file: {"update", "autofix"}}: which of the branch's commits changed each file."""
    out = {}
    for c in commits:
        msg = (c.get("commit") or {}).get("message") or ""
        kind = "autofix" if AUTOFIX_COMMIT.match(msg) else "update"
        for name in c.get("files") or ():
            out.setdefault(name, set()).add(kind)
    return out


def verified_file_problem(f, by, guard_allowed, repo, ref="", tags=None):
    """Why a file of the candidate or of an update keeps it for a person, or ""."""
    name = f.get("filename", "")
    cid = candidate_id(ref)
    if not by:
        return "%s: no commit of the branch accounts for it" % name
    if by == {"update"}:
        if f.get("status") in ("renamed", "copied") or f.get("previous_filename"):
            return "%s: renamed" % name
        if f.get("status") == "removed" and not name.startswith("licenses/"):
            return "%s: removed" % name
        if name == "PKGBUILD" and cid == "pkgbuild":
            # tools/pkgbuild-sync.py's rule: depends, optdepends and the version only
            if "old_source" not in f or "new_source" not in f:
                return "%s: the whole file could not be read" % name
            why = _tool("pkgbuild-sync").problem(f["old_source"], f["new_source"])
            return "%s: %s" % (name, why) if why else ""
        if name in VERSION_FILES:
            if f.get("patch") is None:
                return "%s: change not readable" % name
            return version_problem(name, f["patch"], repo)
        if name.startswith(".github/") and cid.startswith("ci-"):
            # tools/ci-pins.py's own edit: one pin per line, a release of the same action (git ls-remote)
            if f.get("status") != "modified" or "old_source" not in f or "new_source" not in f:
                return "%s: the whole workflow could not be read" % name
            ci = _tool("ci-pins")
            why = ci.verify_change(cid, f["old_source"], f["new_source"], **({"tags": tags} if tags else {}))
            return "%s: %s" % (name, why) if why else ""
        own = _candidates().spec(cid)["files"] if cid and _candidates().spec(cid) else ()
        if not name.startswith(UPDATE_FILES + own):
            return "%s: not a file an update changes" % name
        return ""
    if by == {"autofix"}:
        builder = _tool("builder-anchor").BUILDERS.get(cid) if ref.startswith(BUILDER_PREFIX) else None
        if builder and name == builder:
            # WP11: only a re-anchoring of I.K.E.'s existing patches
            if f.get("status") != "modified" or "old_source" not in f or "new_source" not in f:
                return "%s: the whole builder could not be read" % name
            why = _tool("builder-anchor").problem(cid, f["old_source"], f["new_source"])
            return "%s: more than a re-anchoring (%s)" % (name, why) if why else ""
        if is_wrapper(name) and _candidates().wrapper_allowed(ref):
            return wrapper_problem(f)            # item 2: the wrapper adapted to a new engine
        return file_problem(f, guard_allowed, repo)     # the 1.1.19 rules of a fix of the automatic fix
    if by == {"update", "autofix"} and is_wrapper(name) and _candidates().wrapper_allowed(ref):
        # item 2: the engine's own file the update moved (ENGINE_VERSION in lib.rs) adapted by the fix
        return wrapper_problem(f)
    return "%s: changed by the update and by the automatic fix" % name


# --- the refresh of a verified candidate behind main (2026-11-22) ---------------------------------

REFRESH = re.compile(r"^refresh: main ([0-9a-f]{40}) into (automation/[A-Za-z0-9._/-]{1,120}) "
                     r"\(tools/automerge\.py, no AI\)$")
BOT_NAME, BOT_MAIL = "github-actions[bot]", "41898282+github-actions[bot]@users.noreply.github.com"


def _first(c):
    return ((c.get("commit") or {}).get("message") or "").split("\n", 1)[0]


def version_in(text):
    m = re.search(r'^__version__ = "(\d+\.\d+\.\d+)"$', text or "", re.M)
    return m.group(1) if m else ""


def _git(cwd, *args, data=None, env=None, check=True):
    """git in cwd (bytes in and out); RuntimeError when it fails and check is set."""
    out = subprocess.run(["git", *args], cwd=cwd, capture_output=True, input=data, env=env)
    if check and out.returncode:
        raise RuntimeError("git %s: %s" % (" ".join(args[:2]), out.stderr.decode("utf-8", "replace").strip()[:300]))
    return out


def _out(cwd, *args, **kw):
    return _git(cwd, *args, **kw).stdout.decode("utf-8").strip()


def _show(cwd, rev, path):
    """The file at a commit (text), or None when it is not there."""
    out = _git(cwd, "show", "%s:%s" % (rev, path), check=False)
    return out.stdout.decode("utf-8") if out.returncode == 0 else None


def changelog_union(base, ours, theirs, version):
    """(text, why): main's CHANGELOG.md (theirs) with the candidate's new bullet lines (ours against
    base) added at the end of its "## version" section, as tools/prepare-maintenance.py adds to an
    unpublished version: one heading, the union of the bullet lines, no duplicates, main's first.
    ("", why) when the candidate changes more than new bullet lines of that version, or main's first
    section is not that version."""
    import difflib
    old, new = base.split("\n"), ours.split("\n")
    added = []
    for tag, _i1, _i2, j1, j2 in difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        if tag != "insert":
            return "", "CHANGELOG.md: the candidate changes more than new lines"
        added += new[j1:j2]
    heading = "## %s" % version
    bullets = []
    for line in added:
        if line.startswith("- "):
            if line not in bullets:
                bullets.append(line)
        elif line.strip() and line != heading:
            return "", "CHANGELOG.md: the candidate adds more than bullet lines of %s (%s)" % (version, line[:60])
    top = "# Changelog\n"
    if not theirs.startswith(top) or theirs.split("\n").count(heading) != 1:
        return "", "CHANGELOG.md: main's has no single %s section" % heading
    rest = theirs[len(top):].lstrip("\n")
    if not rest.startswith(heading + "\n"):
        return "", "CHANGELOG.md: main's first section is not %s" % version
    tail = rest[len(heading) + 1:]
    following = re.search(r"^## ", tail, re.M)
    end = following.start() if following else len(tail)
    section = tail[:end].rstrip()
    more = [x for x in bullets if x not in section.split("\n")]
    if not more:
        return theirs, ""
    return top + "\n" + heading + "\n" + section + "\n" + "\n".join(more) + "\n\n" + tail[end:].lstrip("\n"), ""


def refreshed_tree(ours, theirs, cwd=ROOT):
    """(tree, why): main (theirs) merged into the candidate (ours) by git, CHANGELOG.md resolved by
    changelog_union when both changed it, a conflicting version file taken from main when main's
    version is the candidate's own; ("", why) for any other conflict (a person resolves it)."""
    out = _git(cwd, "merge-tree", "--write-tree", "--name-only", "--no-messages", "-z", ours, theirs, check=False)
    if out.returncode not in (0, 1):
        return "", "main could not be merged in: %s" % out.stderr.decode("utf-8", "replace").strip()[:200]
    parts = out.stdout.decode("utf-8").split("\0")
    tree, conflicted = parts[0].strip(), sorted({p for p in parts[1:] if p})
    base = _out(cwd, "merge-base", ours, theirs)
    mine, mains = version_in(_show(cwd, ours, "ike/__init__.py")), version_in(_show(cwd, theirs, "ike/__init__.py"))
    blobs, texts = {}, {}
    logs = [_show(cwd, c, "CHANGELOG.md") for c in (base, ours, theirs)]
    if None not in logs and logs[1] != logs[0] and logs[2] != logs[0] and logs[1] != logs[2]:
        # both added to it: always the union (a clean text merge could keep two headings of one version)
        if mine != mains:
            return "", "CHANGELOG.md: the candidate's version %s is not main's %s" % (mine or "-", mains or "-")
        text, why = changelog_union(*logs, mains)
        if why:
            return "", why
        texts["CHANGELOG.md"] = text
    for name in conflicted:
        if name in texts:
            continue
        if name in VERSION_LINES and mine and mine == mains:
            blob = _git(cwd, "rev-parse", "-q", "--verify", "%s:%s" % (theirs, name), check=False)
            if blob.returncode == 0:
                blobs[name] = blob.stdout.decode().strip()
                continue
        return "", "%s: a conflict with main that a person resolves" % name
    if not blobs and not texts:
        return tree, ""
    with tempfile.TemporaryDirectory() as tmp:
        env = dict(os.environ, GIT_INDEX_FILE=str(Path(tmp) / "index"))
        _git(cwd, "read-tree", tree, env=env)
        for name, text in sorted(texts.items()):
            blobs[name] = _out(cwd, "hash-object", "-w", "--stdin", data=text.encode("utf-8"))
        for name, blob in sorted(blobs.items()):
            _git(cwd, "update-index", "--add", "--cacheinfo", "100644,%s,%s" % (blob, name), env=env)
        return _out(cwd, "write-tree", env=env), ""


def make_refresh(ref, head, main_sha, cwd=ROOT):
    """(commit, why): the refresh commit of the candidate's head with main merged in (not pushed)."""
    tree, why = refreshed_tree(head, main_sha, cwd)
    if why:
        return "", why
    message = ("refresh: main %s into %s (tools/automerge.py, no AI)\n\nThe verified candidate was behind main: "
               "main merged in, CHANGELOG.md and the version files resolved as decided; its tests run again.\n"
               % (main_sha, ref))
    env = dict(os.environ, GIT_AUTHOR_NAME=BOT_NAME, GIT_AUTHOR_EMAIL=BOT_MAIL, GIT_COMMITTER_NAME=BOT_NAME,
               GIT_COMMITTER_EMAIL=BOT_MAIL)
    return _out(cwd, "commit-tree", tree, "-p", head, "-p", main_sha, data=message.encode("utf-8"), env=env), ""


def refresh_problem(sha, ref, cwd=ROOT, main_ref="origin/main"):
    """"" when the commit is exactly the refresh of this branch: its own message, two parents (the
    branch's commit, then a commit of main it names), and the tree refreshed_tree computes again from
    them; else why it is not (a disguised one: more changes, one parent, a main that is not main's)."""
    try:
        m = REFRESH.match(_out(cwd, "log", "-1", "--format=%s", sha))
        if not m or m.group(2) != ref:
            return "not the refresh commit of %s" % ref
        parents = _out(cwd, "rev-list", "--parents", "-n", "1", sha).split()[1:]
        if len(parents) != 2:
            return "not a merge of the branch and main"
        if parents[1] != m.group(1):
            return "its second parent is not the main it names"
        if _git(cwd, "merge-base", "--is-ancestor", parents[1], main_ref, check=False).returncode:
            return "the main it names is not in main"
        tree, why = refreshed_tree(parents[0], parents[1], cwd)
        if why:
            return why
        if tree != _out(cwd, "rev-parse", "%s^{tree}" % sha):
            return "more than main merged in with the CHANGELOG and version resolutions"
        return ""
    except (RuntimeError, ValueError) as e:
        return "the refresh commit could not be read (%s)" % str(e)[:120]


def target_version(files):
    """The version the pull request sets in ike/__init__.py, or "" when it does not move it."""
    for f in files:
        if f.get("filename") == "ike/__init__.py":
            for _start, _removed, added in hunks(f.get("patch")) or ():
                for line in added:
                    if version_in(line):
                        return version_in(line)
    return ""


def next_version(version):
    major, minor, patch = version.split(".")
    return "%s.%s.%d" % (major, minor, int(patch) + 1)


def version_rule(files, main_version, published):
    """Why the pull request's version does not fit main's, or "" (2026-11-22, the owner's decision:
    several verified merges go into the same unpublished version, never a second raise on top).

    main's version published: a pull request that ships raises it to the next one; not published: a
    raise, if any, is to main's own version (a candidate made before main was raised), and nothing
    more. The CHANGELOG headings it adds name that same version."""
    if not re.fullmatch(r"\d+\.\d+\.\d+", main_version or ""):
        return "main's version could not be read"
    target = target_version(files)
    if published and target and target != next_version(main_version):
        return "main's version %s is published already: the version must be raised to %s, not %s" % (
            main_version, next_version(main_version), target)
    if not published and target and target != main_version:
        return ("a second version raise: main's %s is not published yet and the pull request sets %s; "
                "it goes into %s, signed first (M9)" % (main_version, target, main_version))
    version = target or ("" if published else main_version)
    for f in files:
        if f.get("filename") == "CHANGELOG.md":
            for _start, _removed, added in hunks(f.get("patch")) or ():
                for line in added:
                    if line.startswith("## ") and line != "## %s" % version:
                        return "CHANGELOG.md: a heading of another version (%s; main's is %s)" % (
                            line[3:40], main_version)
    return ""


def decide(repo, pr, commits, files, checks, guard_allowed, published=False, unread=False, evidence=None,
           findings=(), protected=None, tags=None, main_version=None):
    """("merge", "") for a fully verified pull request of the automation, ("ready", "") for a green
    and harmless one of ChatGPT (it waits for the owner's order), ("wait", why) while its checks run,
    or ("person", why). main_version: main's version (version_rule); None only where a test of other
    rules leaves it out. A refresh commit counts only with its "refresh" verdict "" (refresh_problem)."""
    head = pr.get("head") or {}
    ref = head.get("ref", "")
    if pr.get("state") != "open" or (pr.get("base") or {}).get("ref") != "main":
        return "person", "not an open pull request into main"
    if (head.get("repo") or {}).get("full_name") != repo:
        return "person", "not a branch of this repository"
    chatgpt = ref.startswith("chatgpt/")
    if not verified_branch(ref) and not chatgpt:
        return "person", "not a pull request of the automation or of ChatGPT"
    if not chatgpt:
        # the refresh: main merged into the branch, checked again from git; the rest judges the others
        refreshes = [c for c in commits if REFRESH.match(_first(c))]
        for c in refreshes:
            if c.get("refresh") != "":
                return "person", "a refresh commit that is not main merged in as decided: %s" % (
                    c.get("refresh") or "not checked")
        commits = [c for c in commits if c not in refreshes]
    messages = [((c.get("commit") or {}).get("message") or "") for c in commits]
    if not messages:
        return "person", "no commits"
    if ref == FIX_MAIN and not all(AUTOFIX_COMMIT.match(m) for m in messages):
        return "person", "a commit the automatic fix did not write (a trial?)"
    if any(TRIAL.search(m.split("\n", 1)[0]) for m in messages) or \
            (ref != CANDIDATE and any(m.startswith("maintenance:") for m in messages)):
        return "person", "a trial or a maintenance candidate"
    if not files or len(files) >= 100:
        return "person", "no files, or too many to read"
    if protected is None:
        protected = _guard().FORBIDDEN_FILES
    cid = candidate_id(ref)
    own = (_candidates().spec(cid) or {}).get("files", ()) if cid else ()
    # the CI pins' candidate: its workflow edits are judged below, line by line (tools/ci-pins.py)
    ci_branch = cid.startswith("ci-") and ref.startswith(UPDATE_PREFIX) and all(
        _tool("ci-pins").COMMIT.match(m.split("\n", 1)[0]) for m in messages)
    # no test file changed or removed, no protected file, no workflow (the owner's rule)
    for f in files:
        for n in (f.get("filename", ""), f.get("previous_filename") or ""):
            if n and TEST_FILE.search(n):
                return "person", "%s: a test file changed or removed" % n
            if n.startswith(".github/") and not ci_branch:
                return "person", "%s: a workflow" % n
            if n in protected and n not in VERSION_FILES and not (ref == CANDIDATE and n.startswith(UPDATE_FILES)) \
                    and not (own and n.startswith(own)):
                return "person", "%s: a protected file" % n
    if chatgpt or ref == FIX_MAIN:
        for f in files:
            why = file_problem(f, guard_allowed, repo)
            if why:
                return "person", why
        if published and not any(f.get("filename") == "ike/__init__.py" for f in files):
            # the fix would never reach users: the version must be raised (M5)
            return "person", "main's version is published already: the version must be raised"
    else:
        why = commit_problem(ref, commits)
        if why:
            return "person", why
        by = origins(commits)
        for f in files:
            why = verified_file_problem(f, by.get(f.get("filename", "")), guard_allowed, repo, ref, tags)
            if why:
                return "person", why
        names = [f.get("filename", "") for f in files]
        if published and "ike/__init__.py" not in names and any(not n.startswith(NOT_SHIPPED) for n in names):
            return "person", "main's version is published already: the version must be raised"
    if chatgpt and unread:
        # ChatGPT's fix waits for the owner's order anyway; it is not offered on an unsigned version (M9)
        return "person", "main already holds a merge by itself not yet signed: that version is signed first (M9)"
    if not chatgpt and main_version is not None:
        # since 2026-11-22 several verified merges share one unpublished version (M9 dropped for them)
        why = version_rule(files, main_version, published)
        if why:
            return "person", why
    names = {}
    for c in checks:
        if c.get("name") in OWN_JOBS or (c.get("name") or "").split(" / ")[-1] in OWN_JOBS:
            continue                             # the automation's own reporting jobs (N7), also when called
        if c.get("status") != "completed":
            return "wait", "a check is still running: %s" % c.get("name")
        if c.get("conclusion") in BAD_CONCLUSIONS:
            return "person", "the check %s did not pass" % c.get("name")
        names[c.get("name")] = c.get("conclusion")
    need = ["tests", "sandbox", "guard"] if chatgpt else list(VERIFIED_CHECKS)
    if ref.startswith(ARCH_TESTING_PREFIX):
        # WP10 (b): a fix for Arch's testing packages merges only when it passes on stable and testing
        testing = [n for n in names if n.startswith(ARCH_TESTING_CHECK)]
        if not testing:
            return "wait", "the check %s has not run on this commit yet" % ARCH_TESTING_CHECK
        need += testing
    for n in need:
        if n not in names:
            return "wait", "the check %s has not run on this commit yet" % n
        if names[n] != "success":
            return "person", "the check %s did not pass (%s)" % (n, names[n])
    if chatgpt:
        return "ready", ""
    if evidence is None:
        return "wait", NO_EVIDENCE
    problems = verification_problems(evidence, kinds_of(files, ref))
    if problems:
        return "person", "not fully verified: %s" % "; ".join(problems[:6])
    if findings:
        return "person", "%s: %s" % (SECURITY_WHY, "; ".join(list(findings)[:6]))
    return "merge", ""


def gh(*args, data=None):
    out = subprocess.run(["gh", *args], capture_output=True, text=True, input=data)
    if out.returncode:
        raise RuntimeError("gh %s: %s" % (" ".join(args[:3]), out.stderr.strip()[:300]))
    return out.stdout


def api(path):
    return json.loads(gh("api", path))


def version_of_main():
    m = re.search(r'^__version__ = "([^"]+)"', (ROOT / "ike" / "__init__.py").read_text("utf-8"), re.M)
    return m.group(1) if m else ""


def file_at(repo, path, ref):
    import base64
    data = api("repos/%s/contents/%s?ref=%s" % (repo, path, ref))
    return base64.b64decode(data["content"]).decode("utf-8")


def released(repo, tag):
    try:
        gh("release", "view", tag, "--repo", repo, "--json", "tagName")
        return True
    except RuntimeError:
        return False


def unread_merge(repo):
    """main holds a fix merged by itself since the last published release."""
    try:
        tag = json.loads(gh("release", "view", "--repo", repo, "--json", "tagName"))["tagName"]
        commits = api("repos/%s/compare/%s...main" % (repo, tag)).get("commits", [])
    except (RuntimeError, KeyError, ValueError):
        return True                      # not known: a person decides
    return any("(merged by itself" in ((c.get("commit") or {}).get("message") or "") for c in commits)


MARK = "<!-- automerge: left for a person -->"
BOT = "github-actions[bot]"
NO_EVIDENCE = "the results of its checks could not be read"


def person_text(n, why, owner, sha):
    security = why.startswith(SECURITY_WHY)
    return ("%s\n@%s: questa pull request **non** entra in `main` da sola: %s.\n\n"
            "Prima di unirla va letta: chiedi a Claude di revisionare la pull request #%d.\n%s"
            % (MARK, owner, why, n, VERDICT % (sha or "-", "security" if security else "person")))


def tell_person(repo, n, why, owner, sha=""):
    """One comment per pull request, naming the owner (a mail with GitHub's
    notification settings of docs/MAINTENANCE.md); a later reason is written
    into that same comment, never in a new one (no second mail)."""
    body = person_text(n, why, owner, sha)
    said = json.loads(gh("api", "repos/%s/issues/%d/comments?per_page=100" % (repo, n), "--jq",
                         '[.[] | select(.user.login == "%s") | {id, body}]' % BOT) or "[]")
    mine = [c for c in said if MARK in (c.get("body") or "")]
    if mine:
        if mine[0].get("body") != body:
            gh("api", "-X", "PATCH", "repos/%s/issues/comments/%s" % (repo, mine[0]["id"]), "-f", "body=" + body)
        return
    gh("pr", "comment", str(n), "--repo", repo, "--body", body)


READY_MARK = "<!-- ike-automerge-ready -->"


def tell_ready(repo, n, owner):
    """One comment per pull request: green and harmless, waiting for the
    owner's order (ChatGPT's fixes never merge by themselves, 2026-11-22)."""
    said = gh("api", "repos/%s/issues/%d/comments?per_page=100" % (repo, n), "--jq",
              '[.[] | select(.user.login == "github-actions[bot]") | .body] | join("\\n")')
    if READY_MARK in said:
        return
    gh("pr", "comment", str(n), "--repo", repo, "--body",
       "%s\n@%s: tutti i controlli sono verdi e la correzione non tocca test né file protetti. "
       "**Non** entra in `main` da sola: si unisce solo su tuo ordine (a Claude o a ChatGPT)." % (READY_MARK, owner))


def commit_files(repo, commits):
    """Each commit with the names of the files it changed ("files"; None when they cannot be read)."""
    for c in commits:
        try:
            data = api("repos/%s/commits/%s" % (repo, c["sha"]))
            names = []
            for f in data.get("files") or []:
                names += [x for x in (f.get("filename"), f.get("previous_filename")) if x]
            c["files"] = names
        except (RuntimeError, ValueError, KeyError):
            c["files"] = None
    return commits


def gather_evidence(repo, sha):
    """The runs of Tests, Arch Linux and Security on this commit, with their jobs and steps, and the
    skipped tests of its Tests run (tools/maintenance-ledger.py, GET calls only), or None."""
    led = _tool("maintenance-ledger")
    try:
        runs = {wf: led.run_info(repo, wf, led.gh_api, sha=sha) for wf in ("tests.yml", "arch.yml", "security.yml")}
    except (RuntimeError, ValueError, KeyError) as e:
        print("the runs of the commit could not be read: %s" % str(e)[:200])
        return None
    tests = runs.get("tests.yml")
    skips = led.run_skips(repo, tests["id"], led.gh_api) if tests and tests.get("status") == "completed" else None
    return {"runs": runs, "skips": skips}


def gather_findings(repo, advisories_passed):
    """The open security findings (open_findings) from the bot's issues and the maintenance ledger."""
    led = _tool("maintenance-ledger")
    issues = []
    try:
        for label in ("sandbox-failed", "rust-advisories"):
            for i in api("repos/%s/issues?state=open&labels=%s&per_page=20" % (repo, label)):
                if "pull_request" not in i and (i.get("user") or {}).get("login") == BOT:
                    issues.append(i)
    except (RuntimeError, ValueError) as e:
        return ["the security issues could not be read (%s)" % str(e)[:100]]
    try:
        number, ledger = led.read_ledger(repo, led.gh_api)
        if number and ledger is None:
            ledger = "unreadable"
    except (RuntimeError, ValueError):
        ledger = "unreadable"
    return open_findings(issues, ledger, advisories_passed)


def ensure_arch(repo, ref, sha, workflow="arch.yml"):
    """Arch Linux must run on the commit (the owner's rule): started here when no run of arch.yml
    has this commit (the daily candidate starts it itself; a fix's branch may not have)."""
    try:
        if api("repos/%s/actions/workflows/%s/runs?head_sha=%s&per_page=1" % (repo, workflow, sha)).get(
                "total_count"):
            return False
        gh("workflow", "run", workflow, "--repo", repo, "--ref", ref)
        print("%s started on %s: it had not run on %s" % (workflow, ref, sha[:10]))
        return True
    except (RuntimeError, ValueError) as e:
        print("::warning::arch.yml could not be started on %s: %s" % (ref, str(e)[:200]))
        return False


def fetch_commit(sha, cwd=ROOT):
    """main and the pull request's commit from the public repository (no credentials), for the refresh."""
    try:
        _git(cwd, "fetch", "--no-tags", "-q", "origin", "+refs/heads/main:refs/remotes/origin/main", sha)
        return True
    except RuntimeError as e:
        print("::warning::the commits could not be fetched: %s" % str(e)[:200])
        return False


def behind_main(repo, sha):
    """main has commits the pull request's commit does not (GET only); False when it cannot be read
    (the merge is then tried as before: GitHub refuses one that conflicts)."""
    try:
        return int(api("repos/%s/compare/main...%s" % (repo, sha)).get("behind_by") or 0) > 0
    except (RuntimeError, ValueError, TypeError) as e:
        print("::warning::whether it is behind main could not be read: %s" % str(e)[:200])
        return False


def refresh_branch(repo, ref, sha, cwd=ROOT):
    """(commit, why): main merged into the verified candidate's branch (make_refresh), checked as the
    merge will check it, pushed with the workflow's token to that branch only (a fast-forward, never
    main), then Tests, Security and Arch Linux started on it (the token's push starts no workflow)."""
    import base64
    if not verified_branch(ref) or not ref.startswith("automation/"):
        return "", "not a branch of the automation"
    if not fetch_commit(sha, cwd):
        return "", "the commits could not be fetched"
    main_sha = _out(cwd, "rev-parse", "origin/main^{commit}")
    commit, why = make_refresh(ref, sha, main_sha, cwd)
    if why:
        return "", why
    why = refresh_problem(commit, ref, cwd)
    if why:
        return "", "the refresh is not what the merge accepts (%s)" % why
    auth = base64.b64encode(("x-access-token:%s" % os.environ.get("GH_TOKEN", "")).encode()).decode()
    try:
        _git(cwd, "-c", "http.https://github.com/.extraheader=AUTHORIZATION: basic " + auth, "push", "-q", "origin",
             "%s:refs/heads/%s" % (commit, ref))
    except RuntimeError as e:
        return "", "the refresh could not be pushed (%s)" % str(e).replace(auth, "***")[:200]
    for workflow in ("tests.yml", "security.yml", "arch.yml"):
        try:
            gh("workflow", "run", workflow, "--repo", repo, "--ref", ref)
        except RuntimeError as e:
            print("::warning::%s could not be started on %s: %s" % (workflow, ref, str(e)[:200]))
    return commit, ""


def redispatch_others(repo, n):
    """After a merge: every other open pull request of the automation is judged again (its last
    commit), so the verified ones are refreshed and merged one after another without anyone."""
    try:
        prs = api("repos/%s/pulls?state=open&per_page=100" % repo)
    except (RuntimeError, ValueError) as e:
        print("::warning::the other pull requests could not be read: %s" % str(e)[:200])
        return []
    asked = []
    for p in prs or ():
        head = p.get("head") or {}
        sha = head.get("sha") or ""
        if p.get("number") == n or (head.get("repo") or {}).get("full_name") != repo \
                or not verified_branch(head.get("ref", "")) or not re.fullmatch(r"[0-9a-f]{40}", sha):
            continue
        try:
            gh("workflow", "run", "automerge.yml", "--repo", repo, "--ref", "main", "-f", "sha=" + sha)
            asked.append(p.get("number"))
        except RuntimeError as e:
            print("::warning::#%s could not be judged again: %s" % (p.get("number"), str(e)[:200]))
    return asked


def merge_token(files):
    """The token of the merge: the workflow's own, or for a pull request that changes the workflows (the
    CI pins' candidate, already verified line by line) the repository secret IKE_WORKFLOW_TOKEN when the
    owner set it (GitHub refuses workflow changes to the workflow's token)."""
    import os
    if any((f.get("filename") or "").startswith(".github/") for f in files or ()):
        return os.environ.get("IKE_WORKFLOW_TOKEN") or None
    return None


def merge_it(repo, pr, sha):
    """The merge, with the workflow's token, at exactly this commit; then main's own checks."""
    import os
    n = pr["number"]
    if pr.get("draft"):
        gh("pr", "ready", str(n), "--repo", repo)
    try:
        files = api("repos/%s/pulls/%d/files?per_page=100" % (repo, n))
    except (RuntimeError, ValueError):
        files = []
    token = merge_token(files)
    old = os.environ.get("GH_TOKEN")
    if token:
        os.environ["GH_TOKEN"] = token
    try:
        gh("api", "-X", "PUT", "repos/%s/pulls/%d/merge" % (repo, n), "-f", "merge_method=merge", "-f", "sha=" + sha,
           "-f", "commit_title=Merge pull request #%d: %s (merged by itself: fully verified)"
           % (n, pr.get("title", "")[:120]))
    finally:
        if token and old is not None:
            os.environ["GH_TOKEN"] = old
    gh("pr", "comment", str(n), "--repo", repo, "--body",
       "Unita in `main` da sola: verificata in tutto (test, sandbox, Security, Arch Linux, licenze, nessun test "
       "cambiato o saltato, nessun file protetto, nessun avviso di sicurezza aperto; tools/automerge.py). "
       "Ora ripartono i test di `main`: quando passano arriva l'avviso per firmare la versione.")
    # a merge made with the workflow's token starts no workflow by itself: main's tests, security
    # tests and Arch tests start here; tests.yml and security.yml then ask release-ready.yml
    for workflow in ("tests.yml", "security.yml", "arch.yml"):
        gh("workflow", "run", workflow, "--repo", repo, "--ref", "main")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--repo", required=True)
    ap.add_argument("--sha", required=True)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    if not re.fullmatch(r"[0-9a-f]{40}", a.sha):
        print("not a commit: %s" % a.sha[:60])
        return 0
    # the pull request of this repository, on an allowed branch, whose last
    # commit this is (a stranger's pull request on the same commit is not it: L5)
    prs = [p for p in api("repos/%s/pulls?state=open&per_page=100" % a.repo)
           if (p.get("head") or {}).get("sha") == a.sha
           and ((p.get("head") or {}).get("repo") or {}).get("full_name") == a.repo
           and (verified_branch((p.get("head") or {}).get("ref", ""))
                or (p.get("head") or {}).get("ref", "").startswith("chatgpt/"))]
    if not prs:
        print("no pull request of the automation or of ChatGPT has this commit as its last one")
        return 0
    pr = prs[0]
    n, ref = pr["number"], pr["head"]["ref"]
    verified = verified_branch(ref)
    commits = api("repos/%s/pulls/%d/commits?per_page=100" % (a.repo, n))
    if verified and ref != FIX_MAIN:
        commit_files(a.repo, commits)
    files = api("repos/%s/pulls/%d/files?per_page=100" % (a.repo, n))
    base = (pr.get("base") or {}).get("sha", "")
    for f in files:                       # the whole files, before and after (N1)
        whole = f.get("filename", "").endswith((".py", ".rs")) or f.get("filename", "") == "PKGBUILD" or \
            f.get("filename", "").startswith((".github/", "tools/build-"))
        if whole and f.get("status") == "modified":
            try:
                f["old_source"] = file_at(a.repo, f["filename"], base)
                f["new_source"] = file_at(a.repo, f["filename"], a.sha)
            except (RuntimeError, ValueError, KeyError):
                pass
    guard = _guard()
    main_version = version_of_main()
    published = released(a.repo, "v" + main_version)
    # a refresh commit is judged from git: fetched, and computed again from its parents
    refreshes = [c for c in commits if REFRESH.match(_first(c))] if verified else []
    if refreshes:
        fetched = fetch_commit(a.sha)
        for c in refreshes:
            c["refresh"] = refresh_problem(c.get("sha", ""), ref) if fetched else "the commits could not be fetched"
    if verified and not a.dry_run:
        ensure_arch(a.repo, ref, a.sha)
        if ref.startswith(ARCH_TESTING_PREFIX):
            ensure_arch(a.repo, ref, a.sha, workflow="arch-testing.yml")
    # a check still running (another workflow's last job): read again for a
    # while, so that the deciding run does not end on "wait" for good (N7)
    for _round in range(16):
        checks = api("repos/%s/commits/%s/check-runs?per_page=100" % (a.repo, a.sha)).get("check_runs", [])
        args = (a.repo, pr, commits, files, checks, lambda name: guard.allowed_path(name, False))
        unread = unread_merge(a.repo) if not verified else False      # M9: ChatGPT's fix only (2026-11-22)
        kind, why = decide(*args, published=published, unread=unread, protected=guard.FORBIDDEN_FILES,
                           main_version=main_version)
        if kind == "wait" and why == NO_EVIDENCE:
            # every check passed: what they verified, and the open security findings
            passed = any(c.get("name") == "rust-advisories" and c.get("conclusion") == "success" for c in checks)
            kind, why = decide(*args, published=published, unread=unread, protected=guard.FORBIDDEN_FILES,
                               evidence=gather_evidence(a.repo, a.sha), findings=gather_findings(a.repo, passed),
                               main_version=main_version)
        # Arch Linux takes an hour: its own merge-ready job asks again when it ends
        if kind != "wait" or a.dry_run or "Arch Linux" in why:
            break
        time.sleep(30)
    print("#%d (%s): %s" % (n, ref, {"merge": "fully verified: merge", "ready": "ready for the owner's order",
                                     "wait": "waiting: ", "person": "left for a person: "}[kind] + why))
    if a.dry_run or kind == "wait":
        return 0
    if kind == "person":
        tell_person(a.repo, n, why, a.repo.split("/")[0], a.sha)
        return 0
    if kind == "ready":
        # ChatGPT's fix: never merged by itself (CLAUDE.md), it waits for the owner's order
        if pr.get("draft"):
            gh("pr", "ready", str(n), "--repo", a.repo)
        tell_ready(a.repo, n, a.repo.split("/")[0])
        print("#%d ready: every check green; it waits for the owner's order" % n)
        return 0
    if not verified:                      # never reached: decide() merges only the automation's own
        return 0
    if behind_main(a.repo, a.sha):
        # verified, but on an older main: main merged in (the refresh), then its tests again
        commit, why = refresh_branch(a.repo, ref, a.sha)
        if why:
            print("#%d (%s): left for a person: %s" % (n, ref, why))
            tell_person(a.repo, n, "it is verified but behind main, and the refresh stopped: %s" % why,
                        a.repo.split("/")[0], a.sha)
            return 0
        gh("pr", "comment", str(n), "--repo", a.repo, "--body",
           "Verificata, ma indietro rispetto a `main`: `main` è stato unito nel ramo (%s, nessuna AI; CHANGELOG e "
           "versione risolti come deciso). Ripartono test, Security e Arch Linux; quando passano entra in `main` da "
           "sola." % commit[:10])
        print("#%d refreshed with main (%s): its tests run again, then it is judged again" % (n, commit[:10]))
        return 0
    merge_it(a.repo, pr, a.sha)
    print("merged #%d; the tests of main started (then the signing notice)" % n)
    asked = redispatch_others(a.repo, n)
    if asked:
        print("judged again: %s" % ", ".join("#%s" % x for x in asked))
    return 0


if __name__ == "__main__":
    sys.exit(main())
