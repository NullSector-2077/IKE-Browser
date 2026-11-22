#!/usr/bin/env python3
"""The builders' re-anchoring rule (WP11 of the maintenance; no AI here).

Two components are not copied but built with I.K.E.'s own changes:
Dark Reader (tools/build-darkreader.py: PATCHES, each (name, anchor, replacement),
the anchor found exactly once in Dark Reader's engine) and uBlock Origin's
scriptlets (tools/build-ubo-scriptlets.mjs: the library it imports). When a new
upstream version moves an anchor, tools/check-components.py reports "builder
refused" and the component stays at the version in use. Since 2026-11-22 an AI
may, on the isolated branch ``automation/builder/<id>`` only, re-anchor
I.K.E.'s EXISTING patches. This is the rule its change must follow, checked by
tools/check-autofix-patch.py (--builder ID) and again by tools/automerge.py:

- Dark Reader: the same patches, by name and in the same order (no new patch,
  none removed: the owner's decision of 2026-11-21 keeps only measured
  patches); each replacement text byte-identical; only anchor texts may change;
  everything outside PATCHES byte-identical (no code of the builder changed).
  That the new anchors are found exactly once in the new upstream is proved by
  the builder itself (it refuses otherwise) when the update is applied on the
  branch, and tests/test_darkreader.py proves the result: the shipped engine
  is the npm engine with the changes (byte identity) and carries only the
  measured families;
- uBlock Origin: only the path of the library the builder imports may change
  (a file under the checkout, ending in .js, no ".."); every other line
  identical. Upstream code is never changed: it is only read.

    builder-anchor.py check --id ID --old FILE --new FILE
"""

import argparse
import ast
import re
import sys
from pathlib import Path

BUILDERS = {"darkreader": "tools/build-darkreader.py", "ubo-scriptlets": "tools/build-ubo-scriptlets.mjs"}
UBO_IMPORT = re.compile(r"^const mod = await import\(pathToFileURL\(process\.cwd\(\) \+ '(/src/[A-Za-z0-9_./-]+\.js)'"
                        r"\)\.href\);$")


def _patches(source):
    """(PATCHES as a list of (name, anchor, replacement), first line, last line) or raises ValueError."""
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "PATCHES" for t in node.targets):
            value = ast.literal_eval(node.value)
            if not isinstance(value, list) or not all(
                    isinstance(p, tuple) and len(p) == 3 and all(isinstance(x, str) for x in p) for p in value):
                raise ValueError("PATCHES is not a list of (name, anchor, replacement)")
            return value, node.lineno, node.end_lineno
    raise ValueError("no PATCHES in the builder")


def darkreader_problem(old_src, new_src):
    """"" when new_src only re-anchors old_src's PATCHES (the rule above)."""
    try:
        old, a1, a2 = _patches(old_src)
        new, b1, b2 = _patches(new_src)
    except (SyntaxError, ValueError) as e:
        return "the builder's PATCHES cannot be read: %s" % str(e)[:120]
    if [p[0] for p in old] != [p[0] for p in new]:
        return "the patches are not the same ones in the same order (a patch added, removed or renamed)"
    for (name, anchor_a, repl_a), (_n, anchor_b, repl_b) in zip(old, new):
        if repl_a != repl_b:
            return "patch %r: its replacement text changed (only the anchor may be re-anchored)" % name
        if not anchor_b.strip():
            return "patch %r: an empty anchor" % name
    if all(a[1] == b[1] for a, b in zip(old, new)):
        return "no anchor was changed"
    rest_a = old_src.splitlines()[:a1 - 1] + old_src.splitlines()[a2:]
    rest_b = new_src.splitlines()[:b1 - 1] + new_src.splitlines()[b2:]
    if rest_a != rest_b or old_src.endswith("\n") != new_src.endswith("\n"):
        return "the builder changed outside PATCHES (only anchors may change)"
    return ""


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
    if cid == "darkreader":
        return darkreader_problem(old_src or "", new_src or "")
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
