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
- tests may be fixed but not weakened: no test file removed, no skip or xfail
  added, no assertion removed without one added;
- no binary files, links or paths outside the repository; no keys or tokens;
- a small patch: at most MAX_FILES files and MAX_LINES changed lines.

    check-autofix-patch.py --repo DIR --patch FILE [--allow-adblock]
                           [--report FILE.md]

The patch is applied to the index and work tree of DIR only when every rule
passes; the exit status is 0 then, 1 when the patch is refused (the reasons go
to standard output and to --report), 2 when the patch is empty.
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

MAX_FILES = 15
MAX_LINES = 500

ALLOWED_PREFIXES = ("ike/", "tests/", "tools/", "docs/")
ADBLOCK_PATHS = ("ike-adblock/", "ike/blocker.py", "ike/scriptlets.py",
                 "ike/resources/ubo-scriptlets.json")
FORBIDDEN_FILES = {
    "ike/__init__.py",            # version and minimum system: set by the release tools
    "ike/updater.py",             # signature and hash checks of the self-update
    "tests/conftest.py", "tests/harness.py",   # the test harness itself
    "tools/make-release.py", "tools/publish.py", "tools/prepare-maintenance.py",
    "tools/check-autofix-patch.py", "tools/autofix-plan.py",
}
FORBIDDEN_SUFFIXES = (".key", ".pem", ".so", ".dll", ".exe", ".zst", ".tar", ".gz", ".zip")
WEAKENING = re.compile(r"\b(skip|skipif|xfail|importorskip)\b")
SECRET = re.compile(r"AIza[0-9A-Za-z_\-]{30,}|\bgh[pousr]_[0-9A-Za-z]{20,}|github_pat_[0-9A-Za-z_]{20,}"
                    r"|-----BEGIN [A-Z ]*PRIVATE" r" KEY-----")   # split: not a key marker itself


def git(repo, *args, stdin=None):
    return subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false",
                           "-C", str(repo), *args], input=stdin, capture_output=True,
                          text=True, check=False)


def allowed_path(path, allow_adblock):
    """The reason a path may not be changed, or '' when it may."""
    if path.startswith("/") or ".." in Path(path).parts or path.startswith(".git/") or path == ".git":
        return "outside the repository"
    if path in FORBIDDEN_FILES:
        return "protected file"
    if path.endswith(FORBIDDEN_SUFFIXES):
        return "binary, archive or key file"
    if any(path == p or path.startswith(p) for p in ADBLOCK_PATHS):
        return "" if allow_adblock else "ad blocker (only with an engine update)"
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
                reasons.append("renamed file: %s" % path)
                continue
            if added == "-":
                reasons.append("binary file: %s" % path)
                continue
            files[path] = (int(added), int(removed))
            lines += int(added) + int(removed)
        elif row.startswith(("create mode 120000", "mode change")) or " 120000 " in row:
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

    # the content of the changes
    current, asserts = None, {}
    for line in patch_text.splitlines():
        if line.startswith("+++ "):
            current = line[4:].removeprefix("b/")
            continue
        if line.startswith("--- ") or current is None:
            continue
        if line.startswith("+"):
            if SECRET.search(line):
                reasons.append("%s: a key or token in the added lines" % current)
            if current.startswith("tests/"):
                if WEAKENING.search(line):
                    reasons.append("%s: adds a skip or xfail: %s" % (current, line[1:].strip()[:120]))
                if line[1:].lstrip().startswith("assert"):
                    asserts[current] = asserts.get(current, 0) + 1
        elif line.startswith("-") and current.startswith("tests/") and line[1:].lstrip().startswith("assert"):
            asserts[current] = asserts.get(current, 0) - 1
    for path, balance in sorted(asserts.items()):
        if balance < 0:
            reasons.append("%s: %d assertion(s) removed" % (path, -balance))
    return reasons


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--repo", default=".")
    ap.add_argument("--patch", required=True)
    ap.add_argument("--allow-adblock", action="store_true")
    ap.add_argument("--report", help="write the outcome here (Markdown)")
    a = ap.parse_args(argv)
    patch_text = Path(a.patch).read_text("utf-8", errors="replace")
    if not patch_text.strip():
        print("empty patch")
        if a.report:
            Path(a.report).write_text("The agent changed nothing.\n", "utf-8")
        return 2
    reasons = check(a.repo, patch_text, a.allow_adblock)
    if not reasons:
        files = git(a.repo, "apply", "--numstat", "-", stdin=patch_text).stdout.splitlines()
        if not files:
            reasons = ["the patch changes nothing"]
    if not reasons:
        applied = git(a.repo, "apply", "--index", "-", stdin=patch_text)
        if applied.returncode:
            reasons = ["the patch does not apply: " + applied.stderr.strip()[:300]]
    if reasons:
        text = "Patch refused by the automatic checks:\n\n" + "".join("- %s\n" % r for r in reasons)
        print(text)
        if a.report:
            Path(a.report).write_text(text, "utf-8")
        return 1
    names = [row.split("\t")[-1] for row in files]
    text = "Patch accepted by the automatic checks (%d files):\n\n%s" % (
        len(names), "".join("- `%s`\n" % n for n in names))
    print(text)
    if a.report:
        Path(a.report).write_text(text, "utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
