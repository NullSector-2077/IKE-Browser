#!/usr/bin/env python3
"""Prepare the code an automatic fix starts from (no AI here).

Reads the failure description (.autofix/failure.md, written by
tools/autofix-plan.py) and finds the places of the repository it names:
Python tracebacks ('File ".../ike/weather.py", line 12'), pytest and ruff
locations ("ike/weather.py:12:5:", "tests/test_x.py:88"). For each place it
writes the code around it, with line numbers, to .autofix/context.md, and the
list of the files involved to .autofix/related.txt:

- the agent (Antigravity) gets the code in its instructions and does not spend
  requests looking for it (tools/autofix-agent.py);
- the reserve assistants, which cannot open files at all, work from it
  (tools/autofix-reserve.py);
- the checks accept a fix only if it touches one of the related files
  (tools/check-autofix-patch.py --related).

A test file that failed also brings in the I.K.E. modules it names ("from ike
import lookalike", "ike.shields"), as the cause is often there.

    autofix-context.py --repo DIR [--failure FILE] [--out-dir DIR]
"""

import argparse
import re
import sys
from pathlib import Path

ROOTS = ("ike/", "tests/", "tools/", "docs/", "ike-adblock/src/", "vendor/adblock/")
AROUND = 30                 # lines before and after a place
MAX_PLACES = 8
MAX_LINES = 700             # all excerpts together
MAX_RELATED = 12
MAX_EXAMPLES = 3            # other places that use a missing name (1.1.16)
EXAMPLE_AROUND = 4
_MISSING = re.compile(r"has no attribute '(\w+)'|name '(\w+)' is not defined|cannot import name '(\w+)'")

_PLACE = re.compile(
    r'File "(?:[^"]*/)?((?:ike|tests|tools|docs|vendor/adblock)/[\w./-]+\.py)", line (\d+)'    # traceback
    r"|(?<![\w/.-])((?:ike|tests|tools|docs)/[\w./-]+\.(?:py|js|json|md|txt)):(\d+)"   # pytest, ruff
    # cargo ("--> src/lib.rs:12:5", from inside ike-adblock/): I.K.E.'s own wrapper.
    # The engine's files (~/.cargo/registry/...adblock-0.13.6/src/...) are never matched:
    # an upstream problem is for the maintenance, not for a fix in here.
    r"|(?:-->|at) (?:ike-adblock/)?(src/[\w/-]+\.rs):(\d+)")
_MODULE = re.compile(r"\bfrom ike(?:\.(\w+))? import ([\w, ]+)|\bike[./](\w+)\b")


def places(text, repo):
    """[(file, line)] named by the failure, existing in the repository, in order."""
    out = []
    for m in _PLACE.finditer(text):
        if m.group(5):
            path, line = "ike-adblock/" + m.group(5), m.group(6)
        else:
            path, line = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
        if path.startswith("./"):
            path = path[2:]
        if ".." in Path(path).parts or not path.startswith(ROOTS):
            continue
        if (repo / path).is_file() and (path, int(line)) not in out:
            out.append((path, int(line)))
    return out


def modules_named(test_text, repo):
    """I.K.E. modules a test file names: ike/<name>.py files that exist."""
    found = []
    for m in _MODULE.finditer(test_text):
        names = []
        if m.group(1):
            names.append(m.group(1))
        if m.group(2) and not m.group(1):
            names += [n.strip() for n in m.group(2).split(",")]
        if m.group(3):
            names.append(m.group(3))
        for n in names:
            p = "ike/%s.py" % n
            if n and (repo / p).is_file() and p not in found:
                found.append(p)
    return found


def excerpt(repo, path, line):
    lines = (repo / path).read_text("utf-8", errors="replace").splitlines()
    start, end = max(1, line - AROUND), min(len(lines), line + AROUND)
    body = "\n".join("%5d  %s" % (n, lines[n - 1]) for n in range(start, end + 1))
    return start, end, body


def examples(repo, failure, found):
    """Where the names an error says are missing are used elsewhere in the code.
    2026-11-19: after a (simulated) PyQt change a reserve did not know the right
    form of an enum, while ike/dialogs.py used it correctly a few lines away
    from where it is defined. Only I.K.E.'s own code, a few lines each."""
    names = []
    for m in _MISSING.finditer(failure):
        n = next(g for g in m.groups() if g)
        if n not in names and len(n) > 3:
            names.append(n)
    if not names:
        return ""
    failing = {path for path, _line in found}     # the failing files may hold the same mistake elsewhere
    parts = []
    for name in names[:3]:
        word = re.compile(r"\b%s\b" % re.escape(name))
        for path in sorted(str(p.relative_to(repo)) for p in (repo / "ike").rglob("*.py")):
            if len(parts) >= MAX_EXAMPLES:
                break
            if path in failing:
                continue
            lines = (repo / path).read_text("utf-8", errors="replace").splitlines()
            for i, text in enumerate(lines, 1):
                if not word.search(text):
                    continue
                start, end = max(1, i - EXAMPLE_AROUND), min(len(lines), i + EXAMPLE_AROUND)
                body = "\n".join("%5d  %s" % (n, lines[n - 1]) for n in range(start, end + 1))
                parts.append("### `%s` uses `%s` (line %d)\n\n```text\n%s\n```\n" % (path, name, i, body))
                break
    if not parts:
        return ""
    return ("\n# The same names elsewhere in I.K.E.\n\nThe error says a name is missing; here it is "
            "used in code that works. Compare the form.\n\n" + "\n".join(parts))


def build(repo, failure):
    found = places(failure, repo)
    related = []
    for path, _line in found:
        if path not in related:
            related.append(path)
    for path in list(related):
        if path.startswith("tests/"):
            for mod in modules_named((repo / path).read_text("utf-8", errors="replace"), repo):
                if mod not in related:
                    related.append(mod)
    related = related[:MAX_RELATED]
    parts, used = [], 0
    for path, line in found[:MAX_PLACES]:
        start, end, body = excerpt(repo, path, line)
        if used + (end - start + 1) > MAX_LINES:
            break
        used += end - start + 1
        parts.append("### `%s`, lines %d-%d (the failure points at line %d)\n\n```text\n%s\n```\n"
                     % (path, start, end, line, body))
    if not parts:
        text = ("# Code at the failure\n\nThe failure names no line of the repository: "
                "read the logs above to find the cause.\n")
    else:
        text = ("# Code at the failure\n\nPrepared by GitHub from the places the failure names "
                "(line numbers on the left; they are not part of the files).\n\n" + "\n".join(parts))
    text += examples(repo, failure, found)
    if related:
        text += "\nFiles involved: %s\n" % ", ".join("`%s`" % p for p in related)
    return text, related


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--repo", default=".")
    ap.add_argument("--failure", help="default: REPO/.autofix/failure.md")
    ap.add_argument("--out-dir", help="default: REPO/.autofix")
    a = ap.parse_args(argv)
    repo = Path(a.repo).resolve()
    failure_file = Path(a.failure) if a.failure else repo / ".autofix" / "failure.md"
    out = Path(a.out_dir) if a.out_dir else repo / ".autofix"
    try:
        failure = failure_file.read_text("utf-8", errors="replace")
    except OSError:
        failure = ""
    text, related = build(repo, failure)
    out.mkdir(parents=True, exist_ok=True)
    (out / "context.md").write_text(text, "utf-8")
    (out / "related.txt").write_text("".join(p + "\n" for p in related), "utf-8")
    print("Places found: %d; files involved: %s" % (text.count("### `"), ", ".join(related) or "none"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
