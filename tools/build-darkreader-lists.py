#!/usr/bin/env python3
"""Build the copy of Dark Reader's lists I.K.E. comes with (MIT, https://darkreader.org).

    python3 tools/build-darkreader-lists.py --src DIR [--commit SHA] [--date YYYY-MM-DD] [--out DIR]

--src   a checkout of Dark Reader's repository (https://github.com/darkreader/darkreader)

Writes only ike/resources/darkreader-data.json: the lists of Dark Reader's
extension, read from the checkout's src/config:

- the fixes for single sites   (dynamic-theme-fixes.config)
- the sites already dark       (dark-sites.config)
- the hints that recognise a site's own dark theme (detector-hints.config)

with "version" (Dark Reader's version, from the checkout's package.json),
"lists_commit" and "lists_date". ike/darkfixes.py reads them; ike/window.py
shows the version and the date in About. Dark Reader's engine left I.K.E. in
1.1.29 (the I.K.E. Dark Engine and Chromium's own dark mode remain); only its
lists stay, and the browser itself fetches them once a day (ike/darklists.py):
this copy is what a new profile, or one that could not fetch them, uses.

The lists are read and checked with the browser's own functions
(ike/darklists.py: parse, data_problems, check), so the builder and the browser
can never read them differently. The rules:

1. The lists are data for Dark Reader: CSS put in a style element, selectors
   and flags. Anything that looks like a script STOPS the build
   (DATA_SCRIPT_MARKS of ike/darklists.py).
2. The site fixes start with the common fix (url "*"), or the build STOPS.
3. A list much shorter than the copy I.K.E. has (--bundled, by default the
   repository's own copy) is taken for a broken checkout: the build STOPS.

A build that stops writes nothing: the copy in use stays as it is, and the
daily report says why ("builder refused").
"""

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "ike" / "resources"
NAME = "darkreader-data.json"
VERSION = re.compile(r"^\d+(\.\d+){1,3}$")


def darklists(root=ROOT):
    """ike/darklists.py of this checkout, as a module (it imports nothing heavy: json, re, time, urllib)."""
    spec = importlib.util.spec_from_file_location("ike_darklists", Path(root) / "ike" / "darklists.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def version_of(src):
    """Dark Reader's version, from the checkout's package.json."""
    try:
        version = json.loads((Path(src) / "package.json").read_text("utf-8")).get("version", "")
    except (OSError, ValueError, AttributeError):
        raise SystemExit("package.json of the checkout cannot be read") from None
    if not isinstance(version, str) or not VERSION.match(version):
        raise SystemExit("package.json of the checkout gives no version")
    return version


def build(src, commit="", date="", bundled=None):
    """The lists as I.K.E. ships them, or SystemExit with the reason (nothing is written then)."""
    dl = darklists()
    cfg = Path(src) / "src" / "config"
    texts = {}
    for part, name in dl.FILES.items():
        try:
            texts[part] = (cfg / name).read_text("utf-8")
        except (OSError, UnicodeDecodeError) as e:
            raise SystemExit("%s cannot be read: %s" % (name, e)) from None
    lists = dl.parse(texts)
    problems = dl.data_problems(lists)
    if problems:
        raise SystemExit("the lists hold what could be a script: %s" % "; ".join(problems[:5]))
    why = dl.check(lists, bundled)
    if why:
        raise SystemExit(why)
    return {"version": version_of(src), "lists_commit": commit, "lists_date": date,
            "fixes": lists["fixes"], "dark_sites": lists["dark_sites"], "detector_hints": lists["detector_hints"]}


def dump(data):
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--src", required=True, help="a checkout of Dark Reader's repository")
    ap.add_argument("--commit", default="")
    ap.add_argument("--date", default="")
    ap.add_argument("--out", default=str(RES))
    ap.add_argument("--bundled", default=str(RES / NAME),
                    help="the copy in use, against which a much shorter list is refused")
    a = ap.parse_args(argv)
    try:
        bundled = json.loads(Path(a.bundled).read_text("utf-8")) if a.bundled else None
    except (OSError, ValueError):
        bundled = None
    data = build(a.src, a.commit, a.date, bundled)
    (Path(a.out) / NAME).write_text(dump(data), "utf-8")
    print("Dark Reader %s lists: %d site fixes, %d dark sites, %d detector hints"
          % (data["version"], len(data["fixes"]), len(data["dark_sites"]), len(data["detector_hints"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
