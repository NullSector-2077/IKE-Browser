#!/usr/bin/env python3
"""The builders' re-anchoring rule (WP11 of the maintenance; no AI here).

One component is not copied but built with I.K.E.'s own change: uBlock
Origin's scriptlets (tools/build-ubo-scriptlets.mjs: the library it imports).
When a new upstream version moves that library, tools/check-components.py
reports "builder refused" and the component stays at the version in use. Since
2026-11-22 an AI may, on the isolated branch ``automation/builder/<id>`` only,
re-anchor it. This is the rule its change must follow, checked by
tools/check-autofix-patch.py (--builder ID) and again by tools/automerge.py:

- uBlock Origin: only the path of the library the builder imports may change
  (a file under the checkout, ending in .js, no ".."); every other line
  identical. Upstream code is never changed: it is only read.

Dark Reader was the second one until 1.1.29 (its engine with I.K.E.'s speed
patches); its engine left I.K.E., and its lists (tools/build-darkreader-lists.py)
have no patches to re-anchor: a lists build that refuses waits for a person.

    builder-anchor.py check --id ID --old FILE --new FILE
"""

import argparse
import re
import sys
from pathlib import Path

BUILDERS = {"ubo-scriptlets": "tools/build-ubo-scriptlets.mjs"}
UBO_IMPORT = re.compile(r"^const mod = await import\(pathToFileURL\(process\.cwd\(\) \+ '(/src/[A-Za-z0-9_./-]+\.js)'"
                        r"\)\.href\);$")


def ubo_problem(old_src, new_src):
    """"" when new_src changes only the path of the library the builder imports."""
    a, b = old_src.split("\n"), new_src.split("\n")
    if len(a) != len(b):
        return "lines added or removed (only the import path may change)"
    diff = [(x, y) for x, y in zip(a, b) if x != y]
    if not diff:
        return "nothing changed"
    for x, y in diff:
        mx, my = UBO_IMPORT.match(x), UBO_IMPORT.match(y)
        if not (mx and my):
            return "a line other than the library's import path changed: %s" % y.strip()[:100]
        if ".." in my.group(1) or "//" in my.group(1):
            return "the import path leaves the checkout: %s" % my.group(1)[:100]
    return ""


def problem(cid, old_src, new_src):
    """Why a change of the builder of cid is more than a re-anchoring, or ""."""
    if cid == "ubo-scriptlets":
        return ubo_problem(old_src or "", new_src or "")
    return "no builder of I.K.E.'s for %s" % (cid or "?")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("--id", required=True, choices=sorted(BUILDERS))
    c.add_argument("--old", required=True)
    c.add_argument("--new", required=True)
    a = ap.parse_args(argv)
    why = problem(a.id, Path(a.old).read_text("utf-8"), Path(a.new).read_text("utf-8"))
    print(why or "a re-anchoring only: accepted")
    return 1 if why else 0


if __name__ == "__main__":
    sys.exit(main())
