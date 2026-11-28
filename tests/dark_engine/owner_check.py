"""The big-site check of the I.K.E. Dark Engine experiment, for the owner's own
computer (the sites below cannot be reached from the machines that built the
engine). Started by owner-check.sh; not part of the automatic tests.

Each site is opened three times, in a private profile that keeps nothing (no
cookies, no history, no login, nothing of the user's own I.K.E. profile): as it
is ("off"), with Dark Reader as I.K.E. ships it ("dr") and with the Dark Engine
("proto"). Only plain page loads: nothing is typed or sent, and nothing is
clicked unless --click names a button (a site's age or cookie question).

Saved in the folder given (default ~/ike-dark-check-<date>):
  shots/<site>__<mode>.png and .json   the screenshots and what the page held
  sheets/<site>.png                    the three side by side
  metrics.txt / metrics.json           per site and mode: PASS/FAIL (text below
                                       3:1, invisible icons, light areas), and
                                       the colour difference from Dark Reader
  times.txt                            page load times per mode (ms)
  diagnose.txt                         the light areas the Dark Engine left, and where
                                       their colour comes from (to send to Claude)
  run.log                              the renderer's own log
"""

import argparse
import datetime
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODES = ("off", "dr", "proto")

SITES = {
    # reference and documentation
    "wikipedia": "https://en.wikipedia.org/wiki/Arch_Linux",
    "wikipedia-it": "https://it.wikipedia.org/wiki/Arch_Linux",
    "archwiki": "https://wiki.archlinux.org/title/Installation_guide",
    "mdn": "https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/color",
    "python-docs": "https://docs.python.org/3/library/re.html",
    "rust-docs": "https://doc.rust-lang.org/book/ch01-00-getting-started.html",
    "w3schools": "https://www.w3schools.com/css/css_colors.asp",
    "gnu": "https://www.gnu.org/software/bash/manual/bash.html",
    # code and communities
    "github": "https://github.com/NullSector-2077/IKE-Browser",
    "gitlab": "https://gitlab.com/gitlab-org/gitlab",
    "stackoverflow": "https://stackoverflow.com/questions/11227809",
    "hackernews": "https://news.ycombinator.com/",
    "reddit": "https://www.reddit.com/r/archlinux/",
    "lwn": "https://lwn.net/",
    "kernel-org": "https://www.kernel.org/",
    # news and magazines
    "bbc-news": "https://www.bbc.com/news",
    "repubblica": "https://www.repubblica.it/",
    "corriere": "https://www.corriere.it/",
    "ansa": "https://www.ansa.it/",
    "ilpost": "https://www.ilpost.it/",
    "reuters": "https://www.reuters.com/",
    # shops, services, search
    "ebay-it": "https://www.ebay.it/",
    "booking": "https://www.booking.com/",
    "duckduckgo": "https://duckduckgo.com/?q=arch+linux",
    "startpage": "https://www.startpage.com/",
    "openstreetmap": "https://www.openstreetmap.org/",
    "weather": "https://www.ilmeteo.it/",
    # video and media
    "youtube": "https://www.youtube.com/watch?v=jNQXAC9IVRw",
    "vimeo": "https://vimeo.com/",
    # sites that are dark by their own design (to be left as they are)
    "steam": "https://store.steampowered.com/",
    "twitch": "https://www.twitch.tv/",
    "discord": "https://discord.com/",
}
EXPECTED_CONTENT = {}


def _in_unreadable(urls, names):
    """The sheets the page cannot read, fetched here (no cookies): where they
    define the variables of the light areas (definitions and @property)."""
    import re
    import urllib.request
    lines = []
    if not names:
        return lines
    for u in urls:
        if not u.startswith(("http://", "https://")):
            continue
        try:
            req = urllib.request.Request(u.split("#")[0], headers={"User-Agent": "Mozilla/5.0"})
            text = urllib.request.urlopen(req, timeout=20).read(4 * 1024 * 1024).decode("utf-8", "replace")
        except Exception as e:                      # noqa: BLE001 - a report, never a failure
            lines.append("   (could not fetch %s: %s)" % (u[:100], e))
            continue
        for n in sorted(names):
            hits = [m.start() for m in re.finditer(r"(@property\s+)?" + re.escape(n) + r"\s*[:{]", text)][:4]
            for h in hits:
                s = text.rfind("}", 0, h) + 1
                lines.append("   in unreadable sheet %s: %s" % (u[:70], " ".join(text[max(s, h - 160):h + 120].split())))
    return lines


def _sources(urls, classes):
    """Where the unreadable sheets (fetched here, no cookies) style these classes:
    the rules as written, so that a value built of variables can be followed."""
    import re
    import urllib.request
    lines, texts = [], {}
    for u in urls:
        if not u.startswith(("http://", "https://")):
            continue
        try:
            req = urllib.request.Request(u.split("#")[0], headers={"User-Agent": "Mozilla/5.0"})
            texts[u] = urllib.request.urlopen(req, timeout=20).read(4 * 1024 * 1024).decode("utf-8", "replace")
        except Exception:                           # noqa: BLE001 - a report, never a failure
            continue
    names = set()
    for c in sorted(classes):
        n = 0
        for u, text in texts.items():
            for m in re.finditer(r"\." + re.escape(c) + r"(?![\w-])", text):
                s, e = text.rfind("}", 0, m.start()) + 1, text.find("}", m.end())
                rule = " ".join(text[s:e + 1].split())
                if "background" not in rule and "--" not in rule:
                    continue
                lines.append("   source of .%s in %s: %s" % (c, u.rsplit("/", 1)[-1][:50], rule[:400]))
                names.update(re.findall(r"var\(\s*(--[\w-]+)", rule))
                n += 1
                if n >= 4:
                    break
            if n >= 4:
                break
    for v in sorted(names)[:8]:
        n = 0
        for u, text in texts.items():
            for m in re.finditer(re.escape(v) + r"\s*:", text):
                s = text.rfind("{", 0, m.start())
                sel_start = text.rfind("}", 0, s) + 1
                e = text.find(";", m.end())
                lines.append("   %s defined in %s: %s { %s }" % (v, u.rsplit("/", 1)[-1][:50],
                             " ".join(text[sel_start:s].split())[:120], " ".join(text[m.start():e].split())[:160]))
                n += 1
                if n >= 4:
                    break
            if n >= 4:
                break
    return lines


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out", nargs="?", default=str(Path.home() / ("ike-dark-check-" + datetime.date.today().isoformat())))
    ap.add_argument("--sites", default="", help="names, separated by commas (default: all): " + ",".join(SITES))
    ap.add_argument("--settle", type=int, default=4000, help="ms to wait after each load")
    ap.add_argument("--url", action="append", default=[],
                    help="any other address to check (repeatable); kept on this computer only")
    ap.add_argument("--click", default="",
                    help="click first a button or link with this text (an age or cookie question), e.g. \"I'm Over 18\"")
    ap.add_argument("--modes", default="",
                    help="the renders to compare (default off,proto); with DE_JS_<mode>=file a mode runs another "
                         "copy of the engine, e.g. --modes off,proto128,proto with DE_JS_proto128=an older darkengine.js")
    a = ap.parse_args()
    out = Path(a.out).expanduser()
    shots = out / "shots"
    shots.mkdir(parents=True, exist_ok=True)
    names = a.sites.split(",") if a.sites else ([] if a.url else list(SITES))
    unknown = sorted(set(names) - SITES.keys())
    if unknown:
        ap.error("unknown sites: " + ", ".join(unknown))
    sites = dict(SITES)
    for i, u in enumerate(a.url, 1):
        if not u.startswith(("https://", "http://")):
            u = "https://" + u
        name = "site%d-%s" % (i, (urllib.parse.urlsplit(u).hostname or "page").replace(".", "-"))
        sites[name] = u
        names.append(name)
    with tempfile.TemporaryDirectory() as tmp:
        # render.py's live mode reads the address of each page from a manifest
        for n in names:
            (Path(tmp) / n).mkdir()
            u = sites[n]
            (Path(tmp) / n / "manifest.json").write_text(json.dumps(
                {"url": u, "entry": "index", "site": urllib.parse.urlsplit(u).hostname,
                 "expected_content": EXPECTED_CONTENT.get(n)}))
        env = dict(os.environ, QT_QPA_PLATFORM=os.environ.get("QT_QPA_PLATFORM", "offscreen"), DE_DIAG="1", DE_CLICK=a.click, DE_SCROLL="1")
        # Dark Reader left I.K.E. in 1.1.30: it is compared only when a checkout of 1.1.28
        # is given (DE_DR_ROOT, tests/dark_engine/drcompare.py)
        global MODES
        if not ((HERE.parents[1] / "ike" / "darkpages.py").is_file() or os.environ.get("DE_DR_ROOT")):
            MODES = ("off", "proto")
        if a.modes:
            MODES = tuple(m for m in a.modes.split(",") if m)
        print("Opening %d sites, %d times each (%s): a few minutes..." % (len(names), len(MODES), ", ".join(MODES)),
              flush=True)
        started = time.time_ns()
        with open(out / "run.log", "w") as log:
            render = subprocess.run(
                [sys.executable, str(HERE / "render.py"), str(shots), "--snaps", tmp, "--live",
                 "--pages", ",".join(names), "--modes", ",".join(MODES), "--settle", str(a.settle)],
                env=env, stdout=log, stderr=subprocess.STDOUT)
        if "forced dark mode of the computer" in (out / "run.log").read_text(errors="replace"):
            print("Note: this computer forces a dark mode on Chromium programs (QTWEBENGINE_CHROMIUM_FLAGS);"
                  " it is left out here, as I.K.E. does.", flush=True)
        if render.returncode:
            print(f"Some renders failed. See {out / 'run.log'} and {shots / 'results.json'}.", file=sys.stderr)
            def current(path):
                return path.is_file() and path.stat().st_mtime_ns >= started
            names = [name for name in names if all(current(shots / f"{name}__{mode}.{ext}")
                     for mode in MODES for ext in ("json", "png"))]
            if not names:
                return 1
    with open(out / "metrics.txt", "w") as f:
        subprocess.run([sys.executable, str(HERE / "metrics.py"), str(shots), "--modes", ",".join(MODES),
                        "--json", str(out / "metrics.json"), "--sheets", str(out / "sheets"),
                        "--pages", ",".join(names)],
                       stdout=f, stderr=subprocess.STDOUT, check=True)
    lines = ["| site | off dcl/load | dr dcl/load | proto dcl/load |"]
    for n in names:
        cells = []
        for m in MODES:
            p = shots / ("%s__%s.json" % (n, m))
            if not p.is_file():
                raise RuntimeError("Missing renderer result: %s" % p)
            d = json.loads(p.read_text())
            cells.append("%s/%s" % (d.get("dcl", "-"), d.get("load", "-")))
        lines.append("| %s | %s |" % (n, " | ".join(cells)))
    (out / "times.txt").write_text("\n".join(lines) + "\n")
    # the light areas left by the Dark Engine and where their colour comes from (diagnose.txt)
    diag = []
    for n, m in [(n, m) for n in names for m in MODES if m.startswith("proto")]:
        p = shots / ("%s__%s.diag.json" % (n, m))
        try:
            d = json.loads(p.read_text())
        except (OSError, ValueError):
            continue
        if not d:
            continue
        wanted = set()
        diag.append("== %s%s: %d sheets (%d the page cannot read), %d frames"
                    % (n, "" if m == "proto" else " (" + m + ")", d.get("sheets", 0), len(d.get("unreadable", [])),
                       d.get("frames", 0)))
        for u in d.get("unreadable", []):
            diag.append("   unreadable sheet: %s" % u)
        for e in d.get("light", []):
            diag.append("   %s at %s background %s%s%s" % (e["el"], e["rect"], e["bg"],
                        " frame " + e["frame"] if e.get("frame") else "", " (shadow host)" if e.get("shadowHost") else ""))
            for r in e.get("rules", []):
                diag.append("      rule: %s" % r)
            for v in e.get("vars", []):
                diag.append("      variable %s = %s" % (v["name"], v["value"] or "(empty)"))
                for w in v.get("where", []) + v.get("property", []):
                    diag.append("         %s" % w)
                for a in v.get("ancestors", []):
                    diag.append("         inside %s" % a)
                wanted.add(v["name"])
            if e.get("inline"):
                diag.append("      inline style: %s" % e["inline"])
        for e in d.get("lowcontrast", []):
            u = e["under"]
            diag.append("   light text on a light %s: %r %s at %s colour %s, under it %s: %s%s" % (
                u["kind"], e["text"], e["el"], e["rect"], e["color"], u["layer"], u["value"],
                ("  [style: %s]" % u["inline"]) if u.get("inline") else ""))
            for r in u.get("rules", []):
                diag.append("      rule: %s" % r)
            diag.append("      layers: %s" % " > ".join(e.get("path", [])))
        for e in d.get("onpicture", []):
            diag.append("   light text on a picture: %r %s at %s colour %s, over %s: %s"
                        % (e["text"], e["el"], e["rect"], e["color"], e["under"], e["picture"]))
        diag.extend(_in_unreadable(d.get("unreadable", []), wanted))
    (out / "diagnose.txt").write_text("\n".join(diag) + "\n")
    print((out / "metrics.txt").read_text())
    print("\n".join(lines))
    print("\nEverything is in", out)
    return render.returncode


if __name__ == "__main__":
    sys.exit(main())
