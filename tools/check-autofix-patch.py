#!/usr/bin/env python3
"""Check and apply a patch written by the automatic-fix agent (no AI here).

The agent of .github/workflows/autofix.yml works without any credential and
hands over only a patch. Before anything is committed, this script decides
whether the patch stays inside what an automatic fix may change:

- only I.K.E.'s own code, its tests, its tools and its documents;
- never the workflows, the signing and update channel, the package recipe,
  the version, the licences, the bundled binaries, the system parts or the
  tools that publish and check;
- the ad blocker (engine and its Python side) only on a maintenance candidate
  that updates the engine (--allow-adblock);
- tests may be fixed but not weakened: no test file removed or renamed, no
  skip or xfail added, no assertion removed without one added, and (1.1.18) no
  test function removed or renamed, no assertion that cannot fail, no early
  `return` at the top of a test, no change of the tests' reference data
  (tests/data/, tests/settings-keys.json); final review: no rename or copy of
  any file (git's summary, both names), no empty parameter list, no
  AssertionError caught, no assertion moved into a block, no return in a
  test's body, no decorator on a test but a mark or a patch, file names read
  as git reads them;
- never YouTube's ad blocking (ike/resources/videoads.js, videorelay.js,
  mediahook.js), the test packages, the builders of what comes from others
  (tools/build-*), the weekly health check or the workflows (1.1.18);
- no binary files, links or paths outside the repository; no keys or tokens;
- a small patch: at most MAX_FILES files and MAX_LINES changed lines;
- a pertinent patch (--related, 1.1.15): when the failure names files of the
  repository (tools/autofix-context.py), at least one of them must change;
- never the engine's protections (WP6, 2026-11-22): no added or removed line of
  I.K.E.'s code that names the sandbox and isolation switches, the lists that
  hold them (UNSAFE_SWITCHES, UNSAFE_FEATURES, UNSAFE_ENV, NOTICE_SWITCHES,
  LNA_FEATURES, PRIVACY_FEATURES, read from ike/app.py itself), ENGINE_SAFETY
  or the functions that decide them, and never ike-adblock/deny.toml (an
  exception to a RustSec advisory is a person's, with its reason);
- a fix of a security finding (--security, on automation/update/security-*)
  also never touches the security tests (SECURITY_TESTS: the files
  security.yml runs, and the other tests of the engine's protections), names
  a protection in any file (tests and tools too), or names a RustSec
  advisory: a security finding never makes an AI change a protection.

- never the files that come from others or are generated (1.1.16): Dark
  Reader, uBlock Origin's scriptlets, the icon sets, the ad blocker's Cargo
  files and lock, the third-party notice. Inside ike-adblock/ only I.K.E.'s own
  wrapper (src/, and vendor/adblock/__init__.py) may change, and only with
  --allow-adblock; the engine itself (adblock-rust) is a crate, never in here.

- with --lists (WP8, the AI analysis of the filter lists' findings, on
  automation/update/lists-<date>): only I.K.E.'s adapter (ike/scriptlets.py,
  ike/blocker.py, ike-adblock/src/*.rs) may change; never the lists, the
  bundled uBlock Origin resources, the tests or their data, nor YouTube's ad
  blocking (a changed line or a hunk about YouTube, Scriptlets.host_scripts or
  the video scripts), and no change that removes more than it adds or removes
  a line that keeps a protection (trust, exceptions, ghide...). Patterns, not
  proof: tests/test_lists_recorded.py and the whole suite decide.

- with --builder ID (WP11, the builders' re-anchoring on automation/builder/<id>):
  only that builder (tools/build-darkreader.py, tools/build-ubo-scriptlets.mjs)
  may change, and only as tools/builder-anchor.py allows: the same patches in
  the same order, the same replacement texts, only anchors re-found in the new
  upstream (Dark Reader), or only the path of the library it imports (uBlock
  Origin); nothing else of the builder, no upstream code.

- with --auto (2026-11-22, the full automation: a fix of the automation may reach main by itself):
  the static guard of tools/fix-guard.py too. Never a tier B file (the workflows, the tests, the tools,
  the sandbox and start, the signing and update channel, the package, what comes from others,
  YouTube's ad blocking); a protected file (the ad-blocking adapter, the modules that decide the
  user's safety, I.K.E.'s page scripts) only with statements added, nothing removed or changed, no
  new way out of old code, nothing new that reaches the network, the system or files; the component
  manifest only with a new entry of a plain download. ChatGPT's guard does not use it (its pull
  requests wait for the owner's order).

    check-autofix-patch.py --repo DIR --patch FILE [--allow-adblock] [--security] [--lists] [--builder ID]
                           [--related FILE] [--report FILE.md] [--check-only] [--auto]

The patch is applied to the index and work tree of DIR only when every rule
passes; the exit status is 0 then, 1 when the patch is refused (the reasons go
to standard output and to --report), 2 when the patch is empty, 3 when it is
refused for a reason of safety (a forbidden file, a key, a weakened test...):
then no other assistant is asked, the owner looks. --check-only checks without
applying: the patch must apply to the tree or already be in it (`git apply
--check`, or `--check -R`, 1.1.18); the fix job uses it to hand a refused fix
to the next assistant with the reason.

git runs here without system or global configuration, hooks, fsmonitor,
attributes file or submodules (SAFE_GIT): the fix job runs it on a tree an AI
wrote. Lines printed to the log are one line each, with no "::" that could
start a workflow command.
"""

import argparse
import ast
import fnmatch
import os
import re
import subprocess
import sys
from pathlib import Path

MAX_FILES = 5
MAX_LINES = 150

ALLOWED_PREFIXES = ("ike/", "tests/", "tools/", "docs/")
ADBLOCK_PATHS = ("ike-adblock/src/", "vendor/adblock/__init__.py", "ike/blocker.py", "ike/scriptlets.py")
# from others or generated: never by an automatic fix (their own update tools make them)
THIRD_PARTY = ("ike-adblock/Cargo.toml", "ike-adblock/Cargo.lock", "ike/resources/ubo-scriptlets.json",
               "ike/resources/darkreader", "ike/resources/icons/", "docs/THIRD-PARTY.md")
FORBIDDEN_FILES = {
    "ike/__init__.py",            # version and minimum system: set by the release tools
    "ike/updater.py",             # signature and hash checks of the self-update
    "tests/conftest.py", "tests/harness.py",   # the test harness itself
    "tests/settings-keys.json",   # what the settings tests compare against (1.1.18)
    "tools/make-release.py", "tools/publish.py", "tools/prepare-maintenance.py",
    "tools/check-autofix-patch.py", "tools/autofix-plan.py", "tools/autofix-agent.py",
    "tools/autofix-context.py", "tools/autofix-reserve.py", "tools/autofix-selftest.py",
    # 1.1.18: the owner's rule, YouTube's ad blocking never changes by itself
    "ike/resources/videoads.js", "ike/resources/videorelay.js", "ike/resources/mediahook.js",
    # 1.1.18: the test packages, the weekly health check, the notices of others
    "tools/test-requirements.txt", "tools/automation-health.py", "tools/third-party.py",
    # 1.1.19: the rules of the merge by itself
    "tools/automerge.py",
    # 2026-11-22 (the owner's decisions): the automatic maintenance's detector, inventory,
    # ledger, test categories and candidate report; an agent never changes what judges it
    "tools/check-components.py", "tools/inventory.py", "tools/maintenance-ledger.py",
    "tools/test-categories.py", "tools/maintenance-report.py",
    # WP6/WP7: the security findings' tools (the deterministic update, the vulnerability sources)
    "tools/security-fix.py", "tools/vulnerabilities.py",
    # WP8, WP9: the filter lists' classes, the AI work's queue and cap, the
    # providers' registry and their weekly check (an agent never chooses its own
    # providers or limits), and the test that proves the lists' new support
    "tools/filter-lists.py", "tools/ai-work.py", "tools/ai-providers.py", "tools/provider-check.py",
    "tests/test_lists_recorded.py",
    # the last block of the full chain (2026-11-22): one candidate per component, the
    # workflows' pins (a deterministic tool, never an AI), the builders' re-anchoring rule,
    # the PKGBUILD's dependencies and the proofs of the whole chain
    "tools/update-candidates.py", "tools/ci-pins.py", "tools/builder-anchor.py", "tools/pkgbuild-sync.py",
    "tests/test_full_chain.py",
    # full automation (2026-11-22): the static guard, the AI reviewers, the component manifest's tool, the
    # signing notice and their proofs; the rules the AIs are judged by are never an AI's
    "tools/fix-guard.py", "tools/ai-review.py", "tools/component-manifest.py", "tools/release-notice.py",
    "tools/no-regression.py", "tests/test_full_auto.py", "tests/test_inventory_guard.py",
}
# the component manifest: with --auto an AI may add a missing entry (tools/fix-guard.py, rule 7)
MANIFEST = "components.json"
# WP11 (--builder ID): the builders' re-anchoring on automation/builder/<id>, only that builder
BUILDERS = {"darkreader": "tools/build-darkreader.py", "ubo-scriptlets": "tools/build-ubo-scriptlets.mjs"}
# WP8 (--lists): what the AI analysis of the filter lists may change, I.K.E.'s
# adapter only
LISTS_ALLOWED = ("ike/scriptlets.py", "ike/blocker.py")
LISTS_ALLOWED_PREFIX = "ike-adblock/src/"
# YouTube's ad blocking, in the adapter's code (the owner's rule, CLAUDE.md)
YOUTUBE_CODE = re.compile(r"youtube|youtu\.be|ytimg|googlevideo|host_scripts|videoads|videorelay|mediahook"
                          r"|video", re.I)
# a removed line that keeps a protection of the adapter
PROTECTION_CODE = re.compile(r"trust|ghide|generichide|BUILTIN_RULES|negated|exception|MAX_LIST_BYTES"
                             r"|_ENV\b|preprocess|https://")
# WP6 (2026-11-22): an exception to a RustSec advisory is written by a person, with its
# reason (tools/security-fix.py check-ignores); never by an automatic fix, whatever the mode
DENY_CONFIG = "ike-adblock/deny.toml"
# the tests of the engine's protections: security.yml runs the first nine with the
# sandbox on (a test checks the two lists agree). A fix of a security finding
# (--security) never changes them.
SECURITY_TESTS = {
    "tests/test_sandbox.py", "tests/test_site_isolation.py", "tests/test_home_network.py",
    "tests/test_media_secret.py", "tests/test_engine_switches.py", "tests/test_userscript_bridge.py",
    "tests/test_frame_guard.py", "tests/test_frame_guard_review.py", "tests/test_referrer.py",
    "tests/test_security.py", "tests/test_home_network_engine.py", "tests/test_update_safety.py",
}
# The engine's protections (ike/app.py): the lists of switches, features and variables that
# take a protection away or keep it on, what a run did with them, and the functions that
# decide. Their strings are read from ike/app.py of the tree being checked (protection_terms);
# FALLBACK_TERMS also when it cannot be read.
ENGINE_FILE = "ike/app.py"
PROTECTION_LISTS = ("UNSAFE_SWITCHES", "NOTICE_SWITCHES", "UNSAFE_FEATURES", "UNSAFE_ENV", "LNA_FEATURES",
                    "PRIVACY_FEATURES")
PROTECTION_NAMES = PROTECTION_LISTS + (
    "ENGINE_SAFETY", "_engine_safety", "unsafe_allowed", "refuse_root", "ROOT_MESSAGE", "sandbox_off",
    "site_isolated", "engine_safety_lines", "IKE_ALLOW_UNSAFE_ENGINE", "QTWEBENGINE_DISABLE_SANDBOX",
    "IKE_TEST_SANDBOX", "--site-per-process")
FALLBACK_TERMS = ("--no-sandbox", "--disable-setuid-sandbox", "--disable-seccomp-filter-sandbox",
                  "--disable-namespace-sandbox", "--disable-gpu-sandbox", "--disable-site-isolation-trials",
                  "--disable-web-security", "--single-process", "--no-zygote", "isolateorigins",
                  "site-per-process")
# where the protections live: in these files every fix is refused a line that names them
PROTECTED_CODE = ("ike/", "ike_boot.py", "launcher/")
RUSTSEC = re.compile(r"\bRUSTSEC-\d{4}-\d{4}\b", re.I)
FORBIDDEN_PREFIXES = (".github/", "tests/data/")      # the workflows; the tests' reference data
FORBIDDEN_PATTERNS = ("tools/build-*.py", "tools/build-*.mjs")   # builders of what comes from others
FORBIDDEN_SUFFIXES = (".key", ".pem", ".so", ".dll", ".exe", ".zst", ".tar", ".gz", ".zip")
# a skip or an expected failure, in code (the bare word "skip" in a comment is fine)
WEAKENING = re.compile(r"\bpytest\s*\.\s*(skip|xfail|importorskip)\b|\bmark\s*\.\s*(skip|skipif|xfail)\b"
                       r"|\bunittest\s*\.\s*skip|\b(skipif|xfail|importorskip|SkipTest|skipTest|skipIf|skipUnless"
                       r"|expectedFailure)\b|\.\s*skip\b|\bskip\s*\(")
# an assertion that can never fail (1.1.18), when the line does not parse alone
TRIVIAL_ASSERT = re.compile(r"^\s*assert\s*\(?\s*(True|1|not\s+(False|None|0))\s*\)?\s*(,.*)?(#.*)?$")
TEST_DEF = re.compile(r"^\s*(?:async\s+)?def\s+(test_\w*)\s*\(")
TEST_CLASS = re.compile(r"^\s*class\s+(Test\w*)\b")
# tests removed, replaced or stopped by code (1.1.18, two reviews): `del test_x`
# anywhere on the line, a test name assigned, delattr (but monkeypatch's),
# globals()/vars(), getattr on pytest/unittest or with a name built from pieces,
# pytest's internals, an exec or exit of the whole run, statements chained with
# `;` around a deletion, an emptied parameter list ([:0]), code that never runs
# (`if False:`), a one-line `if ...: return`. Searched in the whole raw line,
# comments and strings included.
TEST_TAMPERING = re.compile(
    r"\bdel\b[^=\n]*\btest_"
    r"|(?:^|[;,(])\s*\*?test_\w+\s*(?:,[^=\n]*)?(?::[^=\n]*)?[-+*/%|&^@]?=(?!=)"
    r"|(?<!monkeypatch\.)\bdelattr\s*\(|\bglobals\s*\(\s*\)|\bvars\s*\(\s*\)"
    r"|\bgetattr\s*\(\s*(pytest|unittest)\b|@\s*getattr\b|\bgetattr\s*\([^)\n]*['\"]\s*\+?\s*['\"]"
    r"|\b_pytest\b|\bruntest\b|\boutcomes\b|\bSkipped\b"
    r"|\bos\s*\.\s*exec|\bexec[lv]p?e?\s*\(|\b_exit\b|\bpytest\s*\.\s*exit\b"
    r"|;.*\b(del|pop|globals|vars|delattr|setattr)\b|\b(del|pop|globals|vars|delattr|setattr)\b.*;"
    r"|\[\s*(?:0\s*)?:\s*0\s*\]"
    r"|^\s*(?:el)?if\s*\(?\s*(?:False|0|None|not\s+True)\s*\)?\s*:|^\s*while\s+(?:False|0)\s*:"
    r"|^\s*if\b.*:\s*return\b"
    # 1.1.18, third review: an empty parameter list given in place, a module
    # that tells pytest not to collect it, pytest hooks or plugins in a test
    # module, an assertion error caught and dropped, a test removed through the
    # module itself, pytest's or the harness's own functions replaced
    r"|\bparametrize\s*\(\s*(?:\"[^\"]*\"|'[^']*'|\([^)]*\)|\[[^\]]*\])\s*,\s*"
    r"(?:\[\s*\]|\(\s*\)|\{\s*\}|(?:list|tuple|set|dict)\s*\(\s*\))\s*[,)]"
    r"|\bargvalues\s*=\s*(?:\[\s*\]|\(\s*\))"
    r"|\b__test__\b|\bpytest_plugins\b|\bdef\s+pytest_\w+|^\s*pytest_\w+\s*="
    r"|\bexcept\b[^:\n]*\bAssertionError\b|\bsuppress\s*\([^)\n]*\b(?:AssertionError|Exception|BaseException)\b"
    r"|\bsys\s*\.\s*modules\s*\[\s*__name__\s*\]|__dict__\s*(?:\.\s*(?:pop|popitem|clear|update|setdefault)\b"
    r"|\[[^\]\n]*\]\s*=(?!=))|\bsetattr\s*\([^)\n]*['\"]test_"
    r"|\bsetattr\s*\(\s*['\"]?(?:pytest|unittest|harness|conftest|builtins)\b"
    r"|(?<![\w.])(?:pytest|unittest|harness|conftest|builtins)\s*(?:\.\s*\w+\s*)+[-+*/%|&^@]?=(?!=)"
    # audit of #65: a skip imported under another name, attributes set through
    # type.__setattr__, pytest under another name or its own item classes, and
    # output written at exit to fool the count of tests ("No tests lost")
    r"|\bimport\b[^#\n]*\b(?:skip|xfail|importorskip|exit|fail)\b|\b__(?:set|del)attr__\b"
    r"|\bimport\s+_?pytest\s+as\b|\b_?pytest\s*\.\s*(?:Function|Item|Collector|Session|Module|Class|Package)\b"
    r"|\batexit\b|\bos\s*\.\s*write\s*\(\s*[12]\b")
# I.K.E.'s own code that behaves differently under the tests, or rebinds the
# protected updater from elsewhere (audit of #65): refused in added lines of ike/
PRODUCT_TAMPERING = re.compile(
    r"\b_?pytest\b|PYTEST_\w+|\bunittest\b|\bconftest\b"
    r"|\bupdater\s*\.\s*\w+\s*[-+*/%|&^@]?=(?!=)|\bsetattr\s*\(\s*updater\b"
    # ways to find the test run or the runner without naming pytest (review 2
    # of 1.1.19, H4): the module table, dynamic imports, the CI's variables,
    # code at exit, the caller's frames
    r"|\bsys\s*\.\s*modules\b|__import__|\bimportlib\b|\bGITHUB_\w+|\bRUNNER_\w+|\bIKE_TEST_\w+"
    r"|\batexit\b|\bsys\s*\.\s*_getframe\b|\binspect\s*\.|\bgc\s*\.\s*get_\w+|[\"']CI[\"']")
# what decides which tests run, at any depth (1.1.18)
TEST_CONFIG = {"conftest.py", "pytest.ini", "tox.ini", "setup.cfg", "pyproject.toml", "ruff.toml", ".ruff.toml",
               ".gitattributes"}       # audit of #65: linguist-generated hides a file from review
SECRET = re.compile(r"AIza[0-9A-Za-z_\-]{30,}|\bgh[pousr]_[0-9A-Za-z]{20,}|github_pat_[0-9A-Za-z_]{20,}"
                    r"|\bgsk_[0-9A-Za-z]{20,}"                 # Groq
                    r"|\bsk-[0-9A-Za-z_\-]{20,}"               # OpenRouter (sk-or-v1-...), OpenAI and alike
                    r"|\b[0-9a-f]{32}\.[0-9A-Za-z]{16}\b"      # Z.AI (an id and a secret, 1.1.19)
                    r"|-----BEGIN [A-Z ]*PRIVATE" r" KEY-----")   # split: not a key marker itself

# git run on a tree an AI wrote (1.1.18): no system or global configuration, no
# attributes file, no hooks, no fsmonitor, no submodules, and no external diff
# or text conversion (diff passes --no-ext-diff --no-textconv). The
# repository's own .git/config stays: the workflow keeps it out of the agent's
# reach and restores it before each use.
SAFE_GIT_ENV = {"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_ATTR_NOSYSTEM": "1",
                "GIT_TERMINAL_PROMPT": "0"}
SAFE_GIT = ["git", "-c", "safe.directory=*", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false",
            "-c", "core.attributesFile=/dev/null", "-c", "submodule.recurse=false",
            "-c", "diff.ignoreSubmodules=all"]


def safe_git_env():
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(SAFE_GIT_ENV)
    return env


def git(repo, *args, stdin=None):
    return subprocess.run([*SAFE_GIT, "-C", str(repo), *args], input=stdin, capture_output=True,
                          text=True, check=False, env=safe_git_env())


def for_log(text, limit=400):
    """One line, safe to print in the job's log: no "::" that could start a
    GitHub workflow command (the reasons quote lines of the patch)."""
    text = re.sub(r"[\x00-\x1f\x7f\x85  ]+", " ", str(text))
    return re.sub(r":(?=:)", ": ", text)[:limit]


def allowed_path(path, allow_adblock, security=False):
    """The reason a path may not be changed, or '' when it may. security: a fix of a
    security finding (WP6), which never changes the security tests."""
    if path.startswith("/") or ".." in Path(path).parts or path.startswith(".git/") or path == ".git":
        return "outside the repository"
    if path == DENY_CONFIG:
        return "protected file (an exception to a RustSec advisory is a person's, with its reason: %s)" % path
    if security and path in SECURITY_TESTS:
        return "protected file (a security test: a fix of a security finding never changes it)"
    if path in FORBIDDEN_FILES or path.startswith(FORBIDDEN_PREFIXES) or \
            any(fnmatch.fnmatchcase(path, p) for p in FORBIDDEN_PATTERNS):
        return "protected file"
    name = Path(path).name
    if name in TEST_CONFIG or (path.startswith("tests/") and name == "__init__.py"):
        return "protected file (what decides which tests run)"
    if any(path == p or path.startswith(p) for p in THIRD_PARTY):
        return "third-party or generated file (its own update tool makes it)"
    if path.endswith(FORBIDDEN_SUFFIXES):
        return "binary, archive or key file"
    if any(path == p or path.startswith(p) for p in ADBLOCK_PATHS):
        return "" if allow_adblock else "ad blocker (only with an engine update)"
    if path.startswith("ike-adblock/") or path.startswith("vendor/"):
        return "the ad blocker's package (only I.K.E.'s wrapper may change)"
    if not path.startswith(ALLOWED_PREFIXES):
        return "not I.K.E.'s code, tests, tools or documents"
    return ""


def protection_terms(repo):
    """The names and strings of the engine's protections: PROTECTION_NAMES, FALLBACK_TERMS and
    every string of ike/app.py's PROTECTION_LISTS in the tree being checked (read with Python's
    parser, never run), so a switch added to those lists later is protected with no change here."""
    terms = set(PROTECTION_NAMES) | set(FALLBACK_TERMS)
    path = Path(repo) / ENGINE_FILE
    try:
        tree = ast.parse(path.read_text("utf-8")) if path.is_file() and not path.is_symlink() else None
    except (OSError, SyntaxError, ValueError):
        tree = None
    for node in (tree.body if tree else []):
        targets = node.targets if isinstance(node, ast.Assign) else \
            [node.target] if isinstance(node, ast.AnnAssign) else []
        if not any(isinstance(t, ast.Name) and t.id in PROTECTION_LISTS for t in targets):
            continue
        for sub in ast.walk(node.value):
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str) and len(sub.value) >= 4:
                # "LocalNetworkAccessChecks:LocalNetworkAccessChecksWarn/false": the feature's name
                terms.add(re.split(r"[:<=]", sub.value, maxsplit=1)[0])
    return terms


def protection_pattern(terms):
    """One pattern for all the terms: each as a whole word, in any case."""
    alts = sorted({t for t in terms if t}, key=len, reverse=True)
    return re.compile(r"(?<![\w-])(?:%s)(?![\w-])" % "|".join(re.escape(t) for t in alts), re.I)


def touched_protections(repo, patch_text, security=False):
    """Lines added or removed that name an engine protection: in I.K.E.'s code (PROTECTED_CODE)
    for every fix; in every file for a fix of a security finding, which is also refused an added
    line naming a RustSec advisory (an exception is a person's, never an AI's)."""
    pattern, reasons = protection_pattern(protection_terms(repo)), []
    for current, sign, code in patch_lines(patch_text):
        if sign not in ("+", "-"):
            continue
        if security or current.startswith(PROTECTED_CODE):
            m = pattern.search(code)
            if m:
                reasons.append("%s: touches the engine's protections (sandbox, site isolation, ENGINE_SAFETY: "
                               "%s): %s" % (current, m.group(0), code.strip()[:120]))
                continue
        if security and sign == "+" and RUSTSEC.search(code):
            reasons.append("%s: names a RustSec advisory (an exception is a person's, in %s, with its reason): %s"
                           % (current, DENY_CONFIG, code.strip()[:120]))
    return reasons


# the adapter's functions that are YouTube's ad blocking (the video sites' scripts)
YOUTUBE_FUNCS = {"ike/scriptlets.py": ("host_scripts",)}


def _ranges(repo, path):
    """[(first, last)] lines of the YouTube functions of path in the tree."""
    names = YOUTUBE_FUNCS.get(path)
    if not names:
        return []
    try:
        tree = ast.parse((Path(repo) / path).read_text("utf-8"))
    except (OSError, SyntaxError, ValueError):
        return [(1, 10 ** 9)]                  # cannot tell: the whole file counts
    return [(n.lineno, n.end_lineno or n.lineno) for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in names]


def lists_reasons(files, patch_text, repo="."):
    """--lists (WP8): only the adapter, never YouTube, never less protection."""
    reasons = []
    ranges = {path: _ranges(repo, path) for path in files}
    for path in sorted(files):
        if path not in LISTS_ALLOWED and not (path.startswith(LISTS_ALLOWED_PREFIX) and path.endswith(".rs")):
            reasons.append("%s: the filter lists' analysis may change only I.K.E.'s adapter (protected file)" % path)
    removed, added = {}, {}
    for current, sign, code in patch_lines(patch_text):
        if sign == "@@":
            m = _HUNK.match(code)
            first = int(re.match(r"^@@ -(\d+)", code).group(1)) if m else 0
            last = first + (int(m.group(1)) if m and m.group(1) is not None else 1) - 1
            context = code[m.end():] if m else code
            if YOUTUBE_CODE.search(context) or any(a <= last and first <= b for a, b in ranges.get(current, ())):
                reasons.append("%s: a change in YouTube's ad blocking (protected file): %s"
                               % (current, code[:120]))
        elif sign in ("+", "-"):
            if YOUTUBE_CODE.search(code):
                reasons.append("%s: a change in YouTube's ad blocking (protected file): %s"
                               % (current, code.strip()[:120]))
            side = added if sign == "+" else removed
            side.setdefault(current, []).append(code.strip())
    for path, lines in sorted(removed.items()):
        kept = set(added.get(path, []))
        if len([x for x in lines if x]) > len([x for x in added.get(path, []) if x]):
            reasons.append("%s: removes more than it adds: blocking may weaken (weakens blocking)" % path)
        for line in lines:
            if line and line not in kept and PROTECTION_CODE.search(line):
                reasons.append("%s: removes a line that keeps a protection (weakens blocking): %s"
                               % (path, line[:120]))
    return reasons


def _anchor_tool():
    import importlib.util
    spec = importlib.util.spec_from_file_location("ike_builder_anchor", Path(__file__).resolve().parent /
                                                  "builder-anchor.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def builder_reasons(repo, patch_text, builder, files):
    """--builder (WP11): only the builder of that component, and only a re-anchoring of its existing
    patches (tools/builder-anchor.py): the old file is the commit's, the new one the patch applied to
    it in a folder of its own."""
    import tempfile
    path = BUILDERS.get(builder)
    if not path:
        return ["--builder %s: not a builder of I.K.E.'s (protected file)" % builder]
    reasons = ["%s: the builder's re-anchoring may change only %s (protected file)" % (f, path)
               for f in sorted(files) if f != path]
    if reasons or path not in files:
        return reasons or ["the patch does not change %s" % path]
    shown = git(repo, "show", "HEAD:" + path)
    if shown.returncode:
        return ["%s: the builder at the commit could not be read" % path]
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / path
        target.parent.mkdir(parents=True)
        target.write_text(shown.stdout, "utf-8")
        done = git(tmp, "apply", "-", stdin=patch_text)
        if done.returncode:
            return ["%s: the patch does not apply to the builder: %s" % (path, done.stderr.strip()[:200])]
        new = target.read_text("utf-8")
    why = _anchor_tool().problem(builder, shown.stdout, new)
    return ["%s: more than a re-anchoring of I.K.E.'s existing patches (protected file): %s" % (path, why)] \
        if why else []


def _fix_guard():
    import importlib.util
    spec = importlib.util.spec_from_file_location("ike_fix_guard", Path(__file__).resolve().parent / "fix-guard.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _at_commit(repo, path):
    """The bytes of a file at the commit being fixed, or None."""
    shown = subprocess.run([*SAFE_GIT, "-C", str(repo), "show", "HEAD:" + path], capture_output=True,
                           check=False, env=safe_git_env())
    return shown.stdout if shown.returncode == 0 else None


def auto_reasons(repo, patch_text, files, allow_adblock=False, lists=False, builder=""):
    """--auto (2026-11-22): the static guard of a fix that may reach main by itself (tools/fix-guard.py):
    tier B never, a protected file only with statements added, nothing new that reaches out. The old
    files are the commit's, the new ones the patch applied to them in a folder of its own."""
    import hashlib
    import tempfile
    fg = _fix_guard()
    with tempfile.TemporaryDirectory() as tmp:
        old = {}
        for path in files:
            data = _at_commit(repo, path)
            old[path] = data.decode("utf-8", "replace") if data is not None else None
            if data is not None:
                target = Path(tmp) / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
        done = git(tmp, "apply", "-", stdin=patch_text)
        if done.returncode:
            return ["the patch does not apply to the files of the commit: %s" % done.stderr.strip()[:200]]
        changes = []
        for path in sorted(files):
            target = Path(tmp) / path
            new = target.read_text("utf-8", "replace") if target.is_file() and not target.is_symlink() else None
            changes.append({"filename": path, "old_source": old[path], "new_source": new,
                            "status": "modified" if old[path] is not None and new is not None else "added"})

        def sha_of(path):
            target = Path(tmp) / path
            if target.is_file() and not target.is_symlink():
                return hashlib.sha256(target.read_bytes()).hexdigest()
            data = _at_commit(repo, path)
            return hashlib.sha256(data).hexdigest() if data is not None else ""
        exempt = (BUILDERS[builder],) if builder in BUILDERS else ()
        return ["static guard: " + r for r in fg.check(changes, engine_candidate=allow_adblock and not lists,
                                                       exempt=exempt, max_files=MAX_FILES, max_lines=MAX_LINES,
                                                       sha_of=sha_of)]


def check(repo, patch_text, allow_adblock=False, security=False, lists=False, builder="", auto=False):
    """The list of reasons the patch is refused (empty: accepted). lists: the
    AI analysis of the filter lists (WP8), the adapter only. builder: the
    builders' re-anchoring (WP11), that builder's PATCHES anchors only. auto: a fix
    of the automation, which may reach main by itself: the static guard too."""
    allow_adblock = allow_adblock or lists
    reasons = []
    stat = git(repo, "apply", "--numstat", "--summary", "-", stdin=patch_text)
    if stat.returncode:
        return ["the patch does not apply: " + stat.stderr.strip()[:300]]
    files, lines = {}, 0
    for row in stat.stdout.splitlines():
        row = row.strip()
        m = re.match(r"^(\d+|-)\t(\d+|-)\t(.+)$", row)
        if m:
            added, removed, path = m.groups()
            path = unquote(path)
            if "=>" in path:
                reasons.append(("test file renamed: %s" if "tests/" in path else "renamed file: %s") % path)
                continue
            if added == "-":
                reasons.append("binary file: %s" % path)
                continue
            files[path] = (int(added), int(removed))
            lines += int(added) + int(removed)
        elif row.startswith(("create mode 120000", "create mode 160000", "mode change")) or \
                " 120000 " in row or " 160000 " in row:          # links, repositories inside (gitlinks)
            reasons.append("link or file mode change: %s" % row)
        elif row.startswith("delete mode") and unquote(row.split(" ", 3)[-1]).startswith("tests/"):
            reasons.append("test file removed: %s" % unquote(row.split(" ", 3)[-1]))
        elif row.startswith(("rename ", "copy ")):
            # 1.1.18, third review: `git apply --numstat` lists only the new name
            # of a renamed file, so renaming tests/harness.py, a workflow or a
            # test module to docs/ removed it unseen. Git's summary names both.
            old, new = renamed_paths(row)
            if old.startswith("tests/") or new.startswith("tests/"):
                reasons.append("test file renamed or copied: %s => %s" % (old, new))
            else:
                why = allowed_path(old, allow_adblock, security) or allowed_path(new, allow_adblock, security)
                reasons.append("%s => %s: %s" % (old, new, why) if why else "renamed file: %s => %s" % (old, new))
    if not files and not reasons:
        return []
    if builder:
        # WP11: the one builder, by its own rule; nothing else (its protected status stays for every
        # other run)
        reasons += builder_reasons(repo, patch_text, builder, files)
    for path in sorted(files):
        if builder and path == BUILDERS.get(builder):
            continue
        if auto and path == MANIFEST and not lists:
            continue                         # judged by the static guard (only a new entry, a plain download)
        why = allowed_path(path, allow_adblock, security)
        if why:
            reasons.append("%s: %s" % (path, why))
    if auto:
        reasons += auto_reasons(repo, patch_text, files, allow_adblock, lists, builder)
    if lists:
        reasons += lists_reasons(files, patch_text, repo)
    if len(files) > MAX_FILES:
        reasons.append("too many files: %d (at most %d)" % (len(files), MAX_FILES))
    if lines > MAX_LINES:
        reasons.append("too many changed lines: %d (at most %d)" % (lines, MAX_LINES))

    # 1.1.18: a new file in tests/ that is not a test module (a helper, a
    # conftest.py, a plugin...) could change what pytest collects
    for row in stat.stdout.splitlines():
        row = row.strip()
        if row.startswith("create mode "):
            path = row.split(" ", 3)[-1]
            if path.startswith("tests/") and not re.fullmatch(r"tests/test_\w+\.py", path):
                reasons.append("%s: new file in tests/ that is not a test module (protected file)" % path)

    # a carriage return alone ends a line for Python but not for git or these
    # checks: "# note\rdel test_x" would hide the second line (second review)
    if re.search(r"\r(?!\n)", patch_text):
        reasons.append("a carriage return inside a line (CR line endings hide lines from the checks)")

    # 1.1.18, third review: the checks below read the file names of the patch
    # themselves ("+++ b/..."); git must read the same ones. A quoted, escaped
    # name ("\164ests/...") was tests/ for git but not for the checks.
    listed = numstat_paths(stat.stdout)
    for path in sorted({p for p, sign, _ in patch_lines(patch_text) if sign == "@@"} - listed):
        reasons.append("%s: the patch names a file in a way git reads differently" % (path or "?"))

    # the content of the changes
    asserts = {}
    for current, sign, code in patch_lines(patch_text):
        if sign == "+":
            if SECRET.search(code):
                reasons.append("%s: a key or token in the added lines" % current)
            if current.startswith("ike/") and PRODUCT_TAMPERING.search(code):
                reasons.append("%s: code that behaves differently under the tests or rebinds the updater: %s"
                               % (current, code.strip()[:120]))
            if current.startswith("tests/"):
                if WEAKENING.search(code):
                    reasons.append("%s: adds a skip or xfail: %s" % (current, code.strip()[:120]))
                if TEST_TAMPERING.search(code):
                    reasons.append("%s: removes or stops tests by code: %s" % (current, code.strip()[:120]))
                if code.lstrip().startswith("assert"):
                    asserts[current] = asserts.get(current, 0) + 1
        elif sign == "-" and current.startswith("tests/") and code.lstrip().startswith("assert"):
            asserts[current] = asserts.get(current, 0) - 1
    for path, balance in sorted(asserts.items()):
        if balance < 0:
            reasons.append("%s: %d assertion(s) removed" % (path, -balance))
    return (reasons + weakened_tests(patch_text) + emptied_parameters(repo, patch_text) +
            touched_protections(repo, patch_text, security))


_HUNK = re.compile(r"^@@ -\d+(?:,(\d+))? \+\d+(?:,(\d+))? @@")


_ESCAPES = {"a": 7, "b": 8, "f": 12, "n": 10, "r": 13, "t": 9, "v": 11, "\\": 92, '"': 34}


def unquote(text):
    """A file name as git writes it: plain, or quoted with C escapes (\\t, \\",
    \\164 in octal...). Git reads "\\164ests/x" as tests/x, and so must the
    checks (1.1.18, third review)."""
    if not (len(text) >= 2 and text.startswith('"') and text.endswith('"')):
        return text
    out, body, i = bytearray(), text[1:-1], 0
    while i < len(body):
        c = body[i]
        if c == "\\" and i + 1 < len(body):
            nxt = body[i + 1]
            if nxt in "01234567":
                digits = re.match(r"[0-7]{1,3}", body[i + 1:]).group(0)
                out.append(int(digits, 8) & 0xFF)
                i += 1 + len(digits)
                continue
            out.append(_ESCAPES.get(nxt, ord(nxt) if ord(nxt) < 128 else 63))
            i += 2
            continue
        out += c.encode("utf-8")
        i += 1
    return out.decode("utf-8", "replace")


def _header_path(text):
    return unquote(text.split("\t", 1)[0].strip())


def renamed_paths(row):
    """[old, new] of a "rename a/{x => y}/b (90%)" or "copy ..." line of
    `git apply --summary`."""
    body = re.sub(r"\s*\(\d+%\)\s*$", "", row.strip().split(" ", 1)[1].strip())
    m = re.match(r"^(.*)\{(.*) => (.*)\}(.*)$", body)
    if m:
        pre, a, b, post = m.groups()
        old, new = pre + a + post, pre + b + post
    else:
        old, _, new = body.partition(" => ")
    return [re.sub(r"/{2,}", "/", unquote(x.strip())) for x in (old, new)]


def numstat_paths(stat_out):
    """Every file name in `git apply --numstat --summary`: changed, created,
    removed, and both names of a rename or copy."""
    out = set()
    for row in stat_out.splitlines():
        m = re.match(r"^(?:\d+|-)\t(?:\d+|-)\t(.+)$", row.strip())
        if m:
            out.add(unquote(m.group(1)))
            continue
        row = row.strip()
        if row.startswith(("rename ", "copy ")):
            out.update(renamed_paths(row))
        elif row.startswith(("create mode ", "delete mode ", "mode change ")):
            out.add(unquote(row.split(" ", 3)[-1]))
    return out


def patch_lines(patch_text):
    """(path, sign, text) of each line inside the hunks of a patch, and
    (path, "@@", "") at the start of each hunk.

    Read as git apply reads it (1.1.18): a hunk holds exactly the number of
    lines its "@@ -a,b +c,d @@" header says, so a line of content that looks
    like a header ("+++ x", from an added "++ x") is content. Until 1.1.18 such
    a line was taken for the next file and blinded every check of the rest of
    it. Lines are split on "\\n" only, as git does."""
    path, old_path, old_left, new_left = None, None, 0, 0
    for line in patch_text.split("\n"):
        if old_left > 0 or new_left > 0:
            sign = line[:1] or " "
            if sign == "\\":                 # "\ No newline at end of file"
                continue
            if sign == " ":
                old_left, new_left = old_left - 1, new_left - 1
            elif sign == "-":
                old_left -= 1
            elif sign == "+":
                new_left -= 1
            else:                             # not a hunk line: the hunk is over
                old_left = new_left = 0
                continue
            yield path or "", sign, line[1:]
            continue
        if line.startswith("diff --git "):
            path = old_path = None
        elif line.startswith("--- "):
            old_path = _header_path(line[4:]).removeprefix("a/")
        elif line.startswith("+++ "):
            new = _header_path(line[4:])
            path = old_path if new == "/dev/null" else new.removeprefix("b/")
        elif line.startswith("@@"):
            m = _HUNK.match(line)
            if m:
                old_left = int(m.group(1)) if m.group(1) is not None else 1
                new_left = int(m.group(2)) if m.group(2) is not None else 1
                yield path or "", "@@", line           # the whole header: its lines and its context


def _code(line):
    return line.split("#", 1)[0].rstrip()


def _same_sides(code):
    """An assertion comparing a thing with itself: `assert x == x`."""
    m = re.match(r"^\s*assert\s+\(?\s*([^,#]+?)\s*(==|is|<=|>=)\s*([^,#]+?)\s*\)?\s*(,.*)?(#.*)?$", code)
    return bool(m) and m.group(1) == m.group(3)


def _always_true(node):
    """An expression that is true whatever the code does: a true constant, a
    non-empty tuple (`assert (cond, 'msg')`), `... or True`, `x == x`."""
    if isinstance(node, ast.Constant):
        return bool(node.value)
    if isinstance(node, (ast.Tuple, ast.List, ast.Set, ast.Dict)):
        return bool(getattr(node, "elts", None) or getattr(node, "keys", None))
    if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or):
        return any(_always_true(v) for v in node.values)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not) and isinstance(node.operand, ast.Constant):
        return not node.operand.value
    if isinstance(node, ast.Compare) and len(node.ops) == 1 and \
            isinstance(node.ops[0], (ast.Eq, ast.Is, ast.LtE, ast.GtE)):
        return ast.dump(node.left) == ast.dump(node.comparators[0])
    return False


def never_fails(code):
    """An added `assert` that can never fail (1.1.18, two reviews). Read with
    Python's own parser when the line is a whole statement, by pattern when not."""
    if not re.match(r"^\s*assert\b", code):
        return False
    try:
        tree = ast.parse(code.strip())
    except (SyntaxError, ValueError):
        return bool(TRIVIAL_ASSERT.match(code)) or _same_sides(code) or \
            bool(re.search(r"\bor\s+(True|1)\b", code)) or bool(re.match(r"^\s*assert\s*\(.*,.*\)\s*(#.*)?$", code))
    stmt = tree.body[0] if tree.body else None
    return isinstance(stmt, ast.Assert) and _always_true(stmt.test)


def _indent(code):
    return len(code) - len(code.lstrip(" \t"))


# decorators that keep a test a test: pytest's marks (a skip or xfail among them
# is refused by WEAKENING) and mock's patches. Any other one added on a test may
# replace it (a fixture, a property, a skipif kept in a name: @needs_engine).
KEEPS_A_TEST = re.compile(r"^\s*@\s*(?:pytest\s*\.\s*)?mark\s*\.|^\s*@\s*(?:unittest\s*\.\s*)?(?:mock\s*\.\s*)?patch\b")


def weakened_tests(patch_text):
    """Tests weakened other than by a removed assertion (1.1.18): a test function
    removed or renamed, an assertion that cannot fail, a `return` added at the
    top of a test body (before its first statement); since the third review
    also a `return` anywhere in the body of a test (not in a nested block), an
    assertion moved into a block (`if`, `try`, `with`, a loop: re-indented
    deeper), and a decorator added on a test other than a mark or a patch."""
    reasons, removed, added = [], {}, set()
    state, quote = None, ""
    test = None                               # (indentation of its def, of its body) in the new file
    decorators = []                           # the decorator lines just above, (sign, code)
    moved = {}                                # (file, assertion) -> ([removed indents], [added indents])
    for current, sign, code in patch_lines(patch_text):
        if sign == "@@":
            state, test, decorators = None, None, []      # a hunk may start anywhere: no assumption
            continue
        if not current.startswith("tests/"):
            continue
        found = TEST_DEF.match(code)
        if code.strip().startswith("assert"):
            sides = moved.setdefault((current, code.strip()), ([], []))
            if sign in ("-", "+"):
                sides[sign == "+"].append(_indent(code))
        if sign == "-":
            if found:
                removed.setdefault(found.group(1), current)
            continue
        stripped = code.strip()
        # the body of the test this line is in (the new file: context and added lines)
        if stripped and not stripped.startswith("#"):
            if found or TEST_CLASS.match(code):
                for d_sign, d_code in decorators:
                    if d_sign == "+" and not KEEPS_A_TEST.match(d_code):
                        reasons.append("%s: adds a decorator that may replace a test: %s"
                                       % (current, d_code.strip()[:120]))
            decorators = decorators + [(sign, code)] if stripped.startswith("@") else []
            if found:
                test = [_indent(code), None]
            elif test and _indent(code) <= test[0] and not stripped.startswith(("@", ")", "]", "}")):
                test = None
            elif test and test[1] is None:
                test[1] = _indent(code)
            if test and test[1] is not None and sign == "+" and _indent(code) == test[1] \
                    and re.match(r"^return\b", stripped) and state != "body":
                reasons.append("%s: adds a return in the body of a test (the lines after it never run): %s"
                               % (current, stripped[:120]))
        if sign == "+" and found:
            added.add(found.group(1))
        if sign == "+" and never_fails(code):
            reasons.append("%s: adds an assertion that cannot fail: %s" % (current, code.strip()[:120]))
        # where we are in a test: its signature, the start of its body, its docstring
        stripped = code.strip()
        if found:
            state = "body" if _code(code).endswith(":") else "signature"
        elif state == "signature":
            if _code(code).endswith(":"):
                state = "body"
        elif state == "doc":
            if quote in stripped:
                state = "body"
        elif state == "body":
            if not stripped or stripped.startswith("#"):
                continue
            opening = re.match(r"^[rRbBuU]?(\"\"\"|''')", stripped)
            if opening:
                quote = opening.group(1)
                if stripped.count(quote) < 2:
                    state = "doc"
                continue
            if sign == "+" and re.match(r"^return\b", stripped):
                reasons.append("%s: adds an early return at the top of a test: %s" % (current, stripped[:120]))
            state = None
    for name, path in sorted(removed.items()):
        if name not in added:
            reasons.append("%s: test removed or renamed: %s" % (path, name))
    # an assertion removed and added again deeper: now under an `if`, a `try`
    # whose except drops it, a `with` or a loop that may never run
    for (path, text), (gone, back) in sorted(moved.items()):
        if gone and back and max(back) > min(gone):
            reasons.append("%s: an assertion moved into a block (if, try, with, loop): %s" % (path, text[:120]))
    return reasons


def emptied_parameters(repo, patch_text):
    """A list a test is parametrized with, emptied where it is defined
    (`REAL = []` for `@pytest.mark.parametrize('n', REAL)`): pytest then runs
    no case of it (third review of 1.1.18)."""
    reasons, names = [], {}
    for current, sign, code in patch_lines(patch_text):
        m = re.match(r"^(\w+)\s*(?::[^=]*)?=\s*(?:\[\s*\]|\(\s*\)|\{\s*\}|(?:list|tuple|set|dict)\s*\(\s*\))\s*(?:#.*)?$",
                     code)
        if sign == "+" and current.startswith("tests/") and m:
            names.setdefault(current, set()).add(m.group(1))
    for path, found in sorted(names.items()):
        try:
            before = (Path(repo) / path).read_text("utf-8", "replace") if not (Path(repo) / path).is_symlink() else ""
        except OSError:
            before = ""
        added = "\n".join(code for p, sign, code in patch_lines(patch_text) if p == path and sign == "+")
        for name in sorted(found):
            if re.search(r"\bparametrize\s*\([^)]*\b%s\b" % re.escape(name), before + "\n" + added):
                reasons.append("%s: empties the parameters of a test: %s" % (path, name))
    return reasons


# A refusal for one of these is not a matter of a better fix: another assistant
# is not asked (exit status 3) and the owner looks.
SAFETY = ("outside the repository", "protected file", "third-party or generated", "binary",
          "ad blocker", "not I.K.E.'s code", "key or token", "link or file mode", "skip or xfail",
          "assertion(s) removed", "test file removed", "test file renamed", "test removed or renamed",
          "assertion that cannot fail", "early return at the top of a test", "removes or stops tests by code",
          "carriage return inside a line", "test file renamed or copied", "reads differently",
          "return in the body of a test", "assertion moved into a block", "decorator that may replace a test",
          "empties the parameters of a test", "behaves differently under the tests",
          "touches the engine's protections", "names a RustSec advisory", "weakens blocking",
          "more than a re-anchoring")


def safety_refusal(reasons):
    return any(any(mark in r for mark in SAFETY) for r in reasons)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--repo", default=".")
    ap.add_argument("--patch", required=True)
    ap.add_argument("--allow-adblock", action="store_true")
    ap.add_argument("--security", action="store_true",
                    help="a fix of a security finding (automation/update/security-*): the stricter rules")
    ap.add_argument("--lists", action="store_true", help="the filter lists' AI analysis: the adapter only (WP8)")
    ap.add_argument("--builder", default="", choices=["", *sorted(BUILDERS)],
                    help="the builders' re-anchoring (WP11): that builder's existing patches only")
    ap.add_argument("--report", help="write the outcome here (Markdown)")
    ap.add_argument("--related", help="files involved in the failure, one per line")
    ap.add_argument("--check-only", action="store_true", help="check, do not apply")
    ap.add_argument("--auto", action="store_true",
                    help="a fix of the automation (it may reach main by itself): the static guard too "
                         "(tools/fix-guard.py: no tier B file, no test, protected files only added to)")
    a = ap.parse_args(argv)
    # bytes, then text: reading as text would turn a lone carriage return into a
    # new line and hide it from the checks (git sees it as part of the line)
    patch_text = Path(a.patch).read_bytes().decode("utf-8", errors="replace")
    if not patch_text.strip():
        print("empty patch")
        if a.report:
            Path(a.report).write_text("The agent changed nothing.\n", "utf-8")
        return 2
    reasons = check(a.repo, patch_text, a.allow_adblock, a.security, a.lists, a.builder, a.auto)
    related = []
    if a.related:
        try:
            related = [x.strip() for x in Path(a.related).read_text("utf-8").splitlines() if x.strip()]
        except OSError:
            related = []
    if related and not reasons:
        changed = re.findall(r"^diff --git a/(\S+) b/", patch_text, re.M)
        if not set(changed) & set(related):
            reasons.append("the patch changes none of the files involved in the failure (%s)"
                           % ", ".join(related[:6]))
    if not reasons:
        files = git(a.repo, "apply", "--numstat", "-", stdin=patch_text).stdout.splitlines()
        if not files:
            reasons = ["the patch changes nothing"]
    if not reasons and a.check_only:
        # 1.1.18: it must apply to the tree, or already be in it (the fix job
        # checks the changes it finds in the work tree)
        ahead = git(a.repo, "apply", "--check", "-", stdin=patch_text)
        if ahead.returncode and git(a.repo, "apply", "--check", "-R", "-", stdin=patch_text).returncode:
            reasons = ["the patch does not apply: " + ahead.stderr.strip()[:300]]
    if not reasons and not a.check_only:
        applied = git(a.repo, "apply", "--index", "-", stdin=patch_text)
        if applied.returncode:
            reasons = ["the patch does not apply: " + applied.stderr.strip()[:300]]
    if reasons:
        text = "Patch refused by the automatic checks:\n\n" + "".join("- %s\n" % r for r in reasons)
        print("\n".join(for_log(line) for line in text.splitlines()))
        if a.report:
            Path(a.report).write_text(text, "utf-8")
        return 3 if safety_refusal(reasons) else 1
    names = [row.split("\t")[-1] for row in files]
    text = "Patch accepted by the automatic checks (%d files):\n\n%s" % (
        len(names), "".join("- `%s`\n" % n for n in names))
    print("\n".join(for_log(line) for line in text.splitlines()))
    if a.report:
        Path(a.report).write_text(text, "utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
