"""The big-site check of the I.K.E. Dark Engine experiment, for the owner's own
computer (the sites below cannot be reached from the machines that built the
engine). Started by owner-check.sh; not part of the automatic tests.

Each site is opened three times, in a private profile that keeps nothing (no
cookies, no history, no login, nothing of the user's own I.K.E. profile): as it
is ("off"), with Dark Reader as I.K.E. ships it ("dr") and with the Dark Engine
("proto"). Only plain page loads: nothing is clicked, typed or sent.

Saved in the folder given (default ~/ike-dark-check-<date>):
  shots/<site>__<mode>.png and .json   the screenshots and what the page held
  sheets/<site>.png                    the three side by side
  metrics.txt / metrics.json           per site and mode: PASS/FAIL (text below
                                       3:1, invisible icons, light areas), and
                                       the colour difference from Dark Reader
  times.txt                            page load times per mode (ms)
  run.log                              the renderer's own log
"""

import argparse
import datetime
import json
import os
import subprocess
import sys
import tempfile
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent

SITES = {
    "wikipedia": "https://en.wikipedia.org/wiki/Arch_Linux",
    "wikipedia-it": "https://it.wikipedia.org/wiki/Arch_Linux",
    "github": "https://github.com/NullSector-2077/IKE-Browser",
    "youtube": "https://www.youtube.com/watch?v=jNQXAC9IVRw",
    "mdn": "https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/color",
    "hackernews": "https://news.ycombinator.com/",
    "python-docs": "https://docs.python.org/3/library/re.html",
    "archwiki": "https://wiki.archlinux.org/title/Installation_guide",
    "stackoverflow": "https://stackoverflow.com/questions/11227809",
    "reddit": "https://www.reddit.com/r/archlinux/",
    "bbc-news": "https://www.bbc.com/news",
    "guardian": "https://www.theguardian.com/international",
    "repubblica": "https://www.repubblica.it/",
    "corriere": "https://www.corriere.it/",
    "ansa": "https://www.ansa.it/",
    "duckduckgo": "https://duckduckgo.com/?q=arch+linux",
}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out", nargs="?", default=str(Path.home() / ("ike-dark-check-" + datetime.date.today().isoformat())))
    ap.add_argument("--sites", default="", help="names, separated by commas (default: all): " + ",".join(SITES))
    ap.add_argument("--settle", type=int, default=4000, help="ms to wait after each load")
    a = ap.parse_args()
    out = Path(a.out).expanduser()
    shots = out / "shots"
    shots.mkdir(parents=True, exist_ok=True)
    names = [n for n in (a.sites.split(",") if a.sites else SITES) if n in SITES]
    with tempfile.TemporaryDirectory() as tmp:
        # render.py's live mode reads the address of each page from a manifest
        for n in names:
            (Path(tmp) / n).mkdir()
            u = SITES[n]
            (Path(tmp) / n / "manifest.json").write_text(json.dumps(
                {"url": u, "entry": "index", "site": urllib.parse.urlsplit(u).hostname}))
        env = dict(os.environ, QT_QPA_PLATFORM=os.environ.get("QT_QPA_PLATFORM", "offscreen"))
        print("Opening %d sites, 3 times each (off, Dark Reader, Dark Engine): a few minutes..." % len(names),
              flush=True)
        with open(out / "run.log", "w") as log:
            subprocess.run([sys.executable, str(HERE / "render.py"), str(shots), "--snaps", tmp, "--live",
                            "--pages", ",".join(names), "--modes", "off,dr,proto", "--settle", str(a.settle)],
                           env=env, stdout=log, stderr=subprocess.STDOUT, check=False)
    with open(out / "metrics.txt", "w") as f:
        subprocess.run([sys.executable, str(HERE / "metrics.py"), str(shots), "--modes", "off,dr,proto",
                        "--json", str(out / "metrics.json"), "--sheets", str(out / "sheets")],
                       stdout=f, stderr=subprocess.STDOUT, check=False)
    lines = ["| site | off dcl/load | dr dcl/load | proto dcl/load |"]
    for n in names:
        cells = []
        for m in ("off", "dr", "proto"):
            p = shots / ("%s__%s.json" % (n, m))
            d = json.loads(p.read_text()) if p.exists() else {}
            cells.append("%s/%s" % (d.get("dcl", "-"), d.get("load", "-")))
        lines.append("| %s | %s |" % (n, " | ".join(cells)))
    (out / "times.txt").write_text("\n".join(lines) + "\n")
    print((out / "metrics.txt").read_text())
    print("\n".join(lines))
    print("\nEverything is in", out)


if __name__ == "__main__":
    main()
