"""Copies of ike/darkengine.js for busy-check.sh (one part changed each), written
into the folder given: nopic.js (no analysis of background pictures),
nolook.js (no look at whether the page is dark already), log.js (every picture
analysed is written to the console with its size and how long it took),
nosvg.js (SVG pictures left as they are), nofrag.js (pictures named with a #part,
as sprites are, left as they are). Exits 1 if the engine changed so that a copy
cannot be made."""

import sys
from pathlib import Path

JS = Path(__file__).resolve().parents[2] / "ike" / "darkengine.js"
KEEP = "return { state: 'keep', data: null, waiting: [] };"
PIC = "  function picture(url, done) {\n"
DRAW = "        work.drawImage(img, 0, 0, 32, 32);\n"
BIG = "        c2.drawImage(img, 0, 0, w, h);\n"
LOOK = "  function looksDarkNow() {\n"


def make(src, pairs):
    for old, new in pairs:
        if src.count(old) != 1:
            raise SystemExit("the engine changed: %r not found once" % old.strip())
        src = src.replace(old, new)
    return src


def main(out):
    out = Path(out)
    src = JS.read_text("utf-8")
    log = ("        console.log('[ike-de] draw ' + w + 'x' + h + ' ' + String(url).slice(0, 160));\n"
           "        var tD = performance.now();\n")
    done = "        console.log('[ike-de] drawn in ' + Math.round(performance.now() - tD) + ' ms');\n"
    files = {
        "nopic.js": [(PIC, PIC + "    " + KEEP + "\n")],
        "nolook.js": [(LOOK, LOOK + "    return false;\n")],
        "log.js": [(PIC, PIC + "    console.log('[ike-de] asked ' + String(url).slice(0, 160));\n"
                         "    var lc = window.__ikeDELogCount || (window.__ikeDELogCount = {});\n"
                         "    lc[url] = (lc[url] || 0) + 1;\n"
                         "    if (lc[url] === 300 || lc[url] === 3000) console.log('[ike-de] stack ' + lc[url] + ' ' + "
                         "String(url).slice(0, 100) + ' :: ' + String(new Error().stack).split('\\n').slice(1, 14).join(' <- '));\n"),
                   (DRAW, log + DRAW + done), (BIG, log + BIG + done)],
        "nosvg.js": [(PIC, PIC + "    if (/^data:image\\/svg|\\.svg(?:[?#]|$)/i.test(url)) " + KEEP + "\n")],
        "nofrag.js": [(PIC, PIC + "    if (String(url).indexOf('#') >= 0) " + KEEP + "\n")],
    }
    for name, pairs in files.items():
        (out / name).write_text(make(src, pairs), "utf-8")


if __name__ == "__main__":
    main(sys.argv[1])
