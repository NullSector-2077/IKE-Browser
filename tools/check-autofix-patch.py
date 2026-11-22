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
  repository (tools/autofix-context.py), at least one of them must change.

- never the files that come from others or are generated (1.1.16): Dark
  Reader, uBlock Origin's scriptlets, the icon sets, the ad blocker's Cargo
  files and lock, the third-party notice. Inside ike-adblock/ only I.K.E.'s own
  wrapper (src/, and vendor/adblock/__init__.py) may change, and only with
  --allow-adblock; the engine itself (adblock-rust) is a crate, never in here.

    check-autofix-patch.py --repo DIR --patch FILE [--allow-adblock]
                           [--related FILE] [--report FILE.md] [--check-only]

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
}
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


def allowed_path(path, allow_adblock):
    """The reason a path may not be changed, or '' when it may."""
    if path.startswith("/") or ".." in Path(path).parts or path.startswith(".git/") or path == ".git":
        return "outside the repository"
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


def check(repo, patch_text, allow_adblock=False):
    """The list of reasons the patch is refused (empty: accepted)."""
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
                why = allowed_path(old, allow_adblock) or allowed_path(new, allow_adblock)
                reasons.append("%s => %s: %s" % (old, new, why) if why else "renamed file: %s => %s" % (old, new))
    if not files and not reasons:
        return []
    for path in sorted(files):
        why = allowed_path(path, allow_adblock)
        if why:
            reasons.append("%s: %s" % (path, why))
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
    return reasons + weakened_tests(patch_text) + emptied_parameters(repo, patch_text)


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
                yield path or "", "@@", ""


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
          "empties the parameters of a test", "behaves differently under the tests")


def safety_refusal(reasons):
    return any(any(mark in r for mark in SAFETY) for r in reasons)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--repo", default=".")
    ap.add_argument("--patch", required=True)
    ap.add_argument("--allow-adblock", action="store_true")
    ap.add_argument("--report", help="write the outcome here (Markdown)")
    ap.add_argument("--related", help="files involved in the failure, one per line")
    ap.add_argument("--check-only", action="store_true", help="check, do not apply")
    a = ap.parse_args(argv)
    # bytes, then text: reading as text would turn a lone carriage return into a
    # new line and hide it from the checks (git sees it as part of the line)
    patch_text = Path(a.patch).read_bytes().decode("utf-8", errors="replace")
    if not patch_text.strip():
        print("empty patch")
        if a.report:
            Path(a.report).write_text("The agent changed nothing.\n", "utf-8")
        return 2
    reasons = check(a.repo, patch_text, a.allow_adblock)
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
