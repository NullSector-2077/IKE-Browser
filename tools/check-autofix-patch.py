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
  (tests/data/, tests/settings-keys.json);
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
    "tools/autofix-context.py", "tools/autofix-reserve.py",
    # 1.1.18: the owner's rule, YouTube's ad blocking never changes by itself
    "ike/resources/videoads.js", "ike/resources/videorelay.js", "ike/resources/mediahook.js",
    # 1.1.18: the test packages, the weekly health check, the notices of others
    "tools/test-requirements.txt", "tools/automation-health.py", "tools/third-party.py",
}
FORBIDDEN_PREFIXES = (".github/", "tests/data/")      # the workflows; the tests' reference data
FORBIDDEN_PATTERNS = ("tools/build-*.py", "tools/build-*.mjs")   # builders of what comes from others
FORBIDDEN_SUFFIXES = (".key", ".pem", ".so", ".dll", ".exe", ".zst", ".tar", ".gz", ".zip")
WEAKENING = re.compile(r"\b(skip|skipif|xfail|importorskip|SkipTest|skipTest)\b")
# an assertion that can never fail (1.1.18)
TRIVIAL_ASSERT = re.compile(r"^\s*assert\s*\(?\s*(True|1|not\s+(False|None|0))\s*\)?\s*(,.*)?(#.*)?$")
TEST_DEF = re.compile(r"^\s*(?:async\s+)?def\s+(test_\w*)\s*\(")
# tests removed or stopped by code (1.1.18): `del test_x`, delattr, globals(),
# skip reached through getattr, an exit of the whole run
TEST_TAMPERING = re.compile(r"^\s*del\b[^=]*\btest_|\bdelattr\s*\(|\bglobals\s*\(\s*\)|\bvars\s*\(\s*\)"
                            r"|\bgetattr\s*\(\s*(pytest|unittest)\b|\b(os\._exit|pytest\.exit)\s*\(")
# what decides which tests run, at any depth (1.1.18)
TEST_CONFIG = {"conftest.py", "pytest.ini", "tox.ini", "setup.cfg", "pyproject.toml", "ruff.toml", ".ruff.toml"}
SECRET = re.compile(r"AIza[0-9A-Za-z_\-]{30,}|\bgh[pousr]_[0-9A-Za-z]{20,}|github_pat_[0-9A-Za-z_]{20,}"
                    r"|\bgsk_[0-9A-Za-z]{20,}"                 # Groq
                    r"|\bsk-[0-9A-Za-z_\-]{20,}"               # OpenRouter (sk-or-v1-...), OpenAI and alike
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
        elif row.startswith("delete mode") and row.split()[-1].startswith("tests/"):
            reasons.append("test file removed: %s" % row.split()[-1])
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
            if path.startswith("tests/") and not re.fullmatch(r"test_\w+\.py", Path(path).name):
                reasons.append("%s: new file in tests/ that is not a test module (protected file)" % path)

    # the content of the changes
    asserts = {}
    for current, sign, code in patch_lines(patch_text):
        if sign == "+":
            if SECRET.search(code):
                reasons.append("%s: a key or token in the added lines" % current)
            if current.startswith("tests/"):
                if WEAKENING.search(code):
                    reasons.append("%s: adds a skip or xfail: %s" % (current, code.strip()[:120]))
                if TEST_TAMPERING.search(_code(code)):
                    reasons.append("%s: removes or stops tests by code: %s" % (current, code.strip()[:120]))
                if code.lstrip().startswith("assert"):
                    asserts[current] = asserts.get(current, 0) + 1
        elif sign == "-" and current.startswith("tests/") and code.lstrip().startswith("assert"):
            asserts[current] = asserts.get(current, 0) - 1
    for path, balance in sorted(asserts.items()):
        if balance < 0:
            reasons.append("%s: %d assertion(s) removed" % (path, -balance))
    return reasons + weakened_tests(patch_text)


_HUNK = re.compile(r"^@@ -\d+(?:,(\d+))? \+\d+(?:,(\d+))? @@")


def _header_path(text):
    text = text.split("\t", 1)[0].strip()
    if text.startswith('"') and text.endswith('"'):
        text = text[1:-1]
    return text


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


def weakened_tests(patch_text):
    """Tests weakened other than by a removed assertion (1.1.18): a test function
    removed or renamed, an assertion that cannot fail, a `return` added at the
    top of a test body (before its first statement)."""
    reasons, removed, added = [], {}, set()
    state, quote = None, ""
    for current, sign, code in patch_lines(patch_text):
        if sign == "@@":
            state = None                      # a hunk may start anywhere: no assumption
            continue
        if not current.startswith("tests/"):
            continue
        found = TEST_DEF.match(code)
        if sign == "-":
            if found:
                removed.setdefault(found.group(1), current)
            continue
        if sign == "+" and found:
            added.add(found.group(1))
        if sign == "+" and (TRIVIAL_ASSERT.match(code) or _same_sides(code)):
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
    return reasons


# A refusal for one of these is not a matter of a better fix: another assistant
# is not asked (exit status 3) and the owner looks.
SAFETY = ("outside the repository", "protected file", "third-party or generated", "binary",
          "ad blocker", "not I.K.E.'s code", "key or token", "link or file mode", "skip or xfail",
          "assertion(s) removed", "test file removed", "test file renamed", "test removed or renamed",
          "assertion that cannot fail", "early return at the top of a test", "removes or stops tests by code")


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
    patch_text = Path(a.patch).read_text("utf-8", errors="replace")
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
