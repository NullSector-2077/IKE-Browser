#!/usr/bin/env python3
"""The Chromium features I.K.E. turns on or off still exist in the engine (AUTOMAT block 2; no AI here).

I.K.E. passes Chromium feature names to Qt WebEngine (ike/app.py: the home-network protection LNA_FEATURES,
PRIVACY_FEATURES, the video decoding VIDEO_ON). Chromium ignores a name it does not know, silently: a renamed or
removed feature turns a protection off with no error and no failing test (docs/automat/SCENARIOS.md, S02). Once a
week (health.yml) this tool asks, for each name:

- **Chromium's development branch**: GitHub's code search in the chromium/chromium mirror finds the file that
  declares it (`BASE_FEATURE(..., "Name", ...)`). Not found: the feature is going away, months before Qt WebEngine
  takes that Chromium (an early warning);
- **the Chromium the users have now** (the version the last green "Arch Linux" run on main recorded, as I.K.E.
  reports it): that file at that version's tag on chromium.googlesource.com, Chromium's own source. Not there:
  the feature is already gone for the users.

What cannot be read is "not verified", never "present". The result goes into the weekly "Automation health"
issue (tools/automation-health.py). The names are read from ike/app.py's own source (its constants), so a new
feature is never forgotten here.

    engine-features.py --chromium VERSION --out FILE [--repo-root DIR]
"""

import argparse
import ast
import base64
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONSTANTS = ("LNA_FEATURES", "PRIVACY_FEATURES", "VIDEO_ON")
SOURCE = "https://chromium.googlesource.com/chromium/src/+/refs/tags/%s/%s?format=TEXT"
NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]{2,80}$")
VERSION = re.compile(r"^\d{2,4}\.\d+\.\d+\.\d+$")


def feature_names(app_source):
    """The feature names of ike/app.py's constants (CONSTANTS), without parameters ("Name:param/x", "Name<trial")."""
    out = []
    for node in ast.parse(app_source).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in CONSTANTS for t in node.targets):
            if isinstance(node.value, (ast.Tuple, ast.List)):
                for elt in node.value.elts:
                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                        name = re.split(r"[:<]", elt.value, maxsplit=1)[0]
                        if NAME.match(name) and name not in out:
                            out.append(name)
    return out


def declares(text, name):
    """True when the text declares the feature (BASE_FEATURE with the name as its string)."""
    return re.search(r'BASE_FEATURE\s*\([^;]{0,200}?"%s"' % re.escape(name), text or "", re.S) is not None


def gh_search(query):
    """GitHub's code search (the workflow's token): [paths]."""
    out = subprocess.run(["gh", "api", "-X", "GET", "search/code", "-f", "q=" + query, "--jq", "[.items[].path]"],
                         capture_output=True, text=True, check=False)
    if out.returncode:
        raise RuntimeError(out.stderr.strip()[:200])
    return json.loads(out.stdout or "[]")


def source_at(version, path, opener=urllib.request.urlopen):
    """The text of one file of Chromium at a version's tag (chromium.googlesource.com), or None when absent."""
    url = SOURCE % (urllib.parse.quote(version), urllib.parse.quote(path))
    try:
        with opener(urllib.request.Request(url, headers={"User-Agent": "ike-engine-features"}), timeout=60) as r:
            return base64.b64decode(r.read(8_000_000)).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise RuntimeError("HTTP %d" % e.code)
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise RuntimeError(type(e).__name__)


MAX_FILES = 6
SEARCH_PAUSE = 7                # GitHub's code search: 10 questions a minute


def check(names, chromium, search=gh_search, source=source_at, pause=None):
    """[{"name", "main", "now", "file"}]: "present", "absent" or "not verified" on Chromium's development branch
    (main) and at the users' version (now)."""
    import time
    pause = pause or (lambda seconds=SEARCH_PAUSE: time.sleep(seconds))
    rows = []
    for name in names:
        row = {"name": name, "main": "not verified", "now": "not verified", "file": ""}
        paths = None
        for attempt in range(2):            # once more after a minute: GitHub's limits of code search
            try:
                paths = [p for p in search('"%s" repo:chromium/chromium' % name) if p.endswith((".cc", ".h", ".mm"))]
                break
            except Exception as e:
                row["why"] = str(e).replace("\n", " ")[:160]
                if attempt == 0:
                    pause(60)
        if paths is None:
            rows.append(row)
            pause()
            continue
        row.pop("why", None)
        row["main"] = "present" if paths else "absent"
        if paths and VERSION.match(chromium or ""):
            # the declaring file is a .cc (a header only names the feature): those first. "absent" only when every
            # file read at the users' version lacks the declaration (2026-11-27: a header read first said absent)
            ordered = sorted(paths, key=lambda p: (not p.endswith(".cc"), p))[:MAX_FILES]
            read = 0
            for path in ordered:
                try:
                    text = source(chromium, path)
                except Exception:
                    continue
                if text is None:
                    continue
                read += 1
                if declares(text, name):
                    row["now"], row["file"] = "present", path
                    break
            if row["now"] != "present" and read == len(ordered):
                row["now"] = "absent"
        rows.append(row)
        pause()
    return rows


def problems(rows, chromium):
    """Lines for the weekly issue: a feature gone now, or going away on Chromium's development branch."""
    out = []
    for r in rows:
        if r["now"] == "absent":
            out.append("The Chromium feature `%s` that I.K.E. sets is no longer declared in Chromium %s (the users' "
                       "engine): it is silently ignored now. Claude updates ike/app.py." % (r["name"], chromium))
        elif r["main"] == "absent":
            out.append("The Chromium feature `%s` that I.K.E. sets is no longer in Chromium's development branch: "
                       "it will stop working with a coming Qt WebEngine. Claude finds its successor." % r["name"])
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--chromium", default="")
    ap.add_argument("--out", required=True)
    ap.add_argument("--repo-root", default=str(ROOT))
    a = ap.parse_args(argv)
    names = feature_names((Path(a.repo_root) / "ike" / "app.py").read_text("utf-8"))
    rows = check(names, a.chromium.strip())
    info = {"chromium": a.chromium.strip(), "features": rows, "problems": problems(rows, a.chromium.strip())}
    Path(a.out).write_text(json.dumps(info, indent=1) + "\n", "utf-8")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    lines = ["### Chromium features I.K.E. sets (tools/engine-features.py)", "",
             "| Feature | Chromium's development branch | Users' Chromium %s |" % (a.chromium or "?"), "|---|---|---|"]
    lines += ["| `%s` | %s | %s |" % (r["name"], r["main"], r["now"] + (" (%s)" % r["why"] if r.get("why") else ""))
              for r in rows]
    print("\n".join(lines))
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
