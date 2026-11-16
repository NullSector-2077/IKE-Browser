#!/usr/bin/env python3
"""Draw I.K.E.'s lettering as vector paths and rebuild the icon files.

    python3 tools/make-brand.py "/path/to/Orbitron[wght].ttf"

The lettering of the logo ("I.K.E") and of the full name ("INTERNET KONTROL
EXPERIENCE") is set in Orbitron (SIL Open Font License 1.1, see
licenses/LICENSE.orbitron) and written into the SVG files as plain paths: nothing
of the font is installed or shipped, and the logo looks the same on every
system. Run this only to change the lettering; it rewrites

    ike/resources/ike.svg         the logo (shield with the "I.K.E" plate)
    data/icons/ike-browser.svg    the same file, for the desktop
    data/icons/*.png, ike/resources/icons/*.png   the logo at each icon size
    ike/resources/wordmark.svg    the full name, in the colour of the text around it

Needs fontTools and PyQt6 (QtSvg) on the computer that runs it, not at run
time. The font file is the variable Orbitron of
https://github.com/google/fonts/tree/main/ofl/orbitron (version 2.001).
"""

import hashlib
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FONT_SHA256 = "f42db2dd16e642258e35782916eceb1dcdbea06fb958d77ad71dc5963587e8fd"

LOGO_TEXT = "I.K.E"
LOGO_WEIGHT = 800
LOGO_TRACKING = 40            # font units (1000 per em) added between glyphs
PLATE = (56.0, 96.0, 144.0, 60.0)   # x, y, width, height of the plate in ike.svg
LOGO_CAP_HEIGHT = 30.0        # height of the capitals, in the 256-unit drawing
LOGO_MAX_WIDTH = 118.0        # the lettering never comes closer to the plate's border

NAME_TEXT = "INTERNET KONTROL EXPERIENCE"
NAME_WEIGHT = 500
NAME_TRACKING = 150
NAME_SPACE = 520              # width of the space between the words
NAME_CAP_HEIGHT = 100.0       # the wordmark's own units; it is scaled where it is used

PNG_SIZES = {"data/icons": (48, 64, 128, 256, 512), "ike/resources/icons": (48, 64, 128, 256)}
LETTERING_ID = "lettering"


def _num(v):
    text = "%.2f" % v
    text = text.rstrip("0").rstrip(".") if "." in text else text
    return "0" if text in ("-0", "") else text


class _Path:
    """Collects a glyph outline as SVG path commands, moved and scaled."""

    def __init__(self):
        self.out = []
        self.scale = 1.0
        self.dx = self.dy = 0.0
        self.box = [1e9, 1e9, -1e9, -1e9]

    def _pt(self, p):
        x, y = self.dx + p[0] * self.scale, self.dy - p[1] * self.scale
        b = self.box
        b[0], b[1], b[2], b[3] = min(b[0], x), min(b[1], y), max(b[2], x), max(b[3], y)
        return "%s %s" % (_num(x), _num(y))

    def moveTo(self, p):
        self.out.append("M" + self._pt(p))

    def lineTo(self, p):
        self.out.append("L" + self._pt(p))

    def qCurveTo(self, *points):
        from fontTools.pens.basePen import decomposeQuadraticSegment
        for control, end in decomposeQuadraticSegment(points):
            self.out.append("Q%s %s" % (self._pt(control), self._pt(end)))

    def curveTo(self, *points):
        self.out.append("C" + " ".join(self._pt(p) for p in points))

    def closePath(self):
        self.out.append("Z")

    def endPath(self):
        pass

    def addComponent(self, name, transform):
        raise ValueError("composite glyph %r: decompose the font first" % name)


def _font(path, weight):
    from fontTools.ttLib import TTFont
    from fontTools.varLib import instancer
    font = TTFont(path)
    if "fvar" in font:
        font = instancer.instantiateVariableFont(font, {"wght": weight})
    return font


def lettering(font_path, text, weight, tracking, cap_height, space=None):
    """(path data, width, height) of `text`: the capitals `cap_height` tall,
    the top left corner of the lettering at 0, 0."""
    from fontTools.pens.recordingPen import DecomposingRecordingPen
    font = _font(font_path, weight)
    glyphs, cmap, hmtx = font.getGlyphSet(), font.getBestCmap(), font["hmtx"]
    scale = cap_height / font["OS/2"].sCapHeight
    pen = _Path()
    pen.scale, pen.dy = scale, cap_height
    x = 0.0
    last = len(text) - 1
    for i, ch in enumerate(text):
        if ch == " ":
            x += (space if space is not None else hmtx[cmap[ord(" ")]][0]) + tracking
            continue
        name = cmap[ord(ch)]
        advance, lsb = hmtx[name]
        if i == 0:
            x -= lsb                              # start at the ink, not at the side bearing
        pen.dx = x * scale
        rec = DecomposingRecordingPen(glyphs)
        glyphs[name].draw(rec)
        rec.replay(pen)
        x += advance + (tracking if i != last else 0)
    left, top, right, bottom = pen.box
    return " ".join(pen.out), left, top, right, bottom


def _shift(d, dx, dy, scale=1.0):
    def repl(m):
        return "%s %s" % (_num(float(m.group(1)) * scale + dx), _num(float(m.group(2)) * scale + dy))
    return re.sub(r"(-?\d+(?:\.\d+)?) (-?\d+(?:\.\d+)?)", repl, d)


def logo_path(font_path):
    d, left, top, right, bottom = lettering(font_path, LOGO_TEXT, LOGO_WEIGHT, LOGO_TRACKING,
                                            LOGO_CAP_HEIGHT)
    width, height = right - left, bottom - top
    scale = min(1.0, LOGO_MAX_WIDTH / width)
    px, py, pw, ph = PLATE
    dx = px + (pw - width * scale) / 2 - left * scale
    dy = py + (ph - height * scale) / 2 - top * scale
    return _shift(d, dx, dy, scale)


def write_logo(font_path):
    target = ROOT / "ike/resources/ike.svg"
    svg = target.read_text("utf-8")
    new = '<path id="%s" fill="#eafcff" d="%s"/>' % (LETTERING_ID, logo_path(font_path))
    # the lettering is the last path of the drawing
    svg, n = re.subn(r'<path (?:id="%s" )?fill="#eafcff"[^>]*/>' % LETTERING_ID, lambda m: new, svg)
    if n != 1:
        raise SystemExit("the lettering path was not found in %s" % target)
    if "<title>" not in svg:
        svg = svg.replace(">\n", ">\n  <title>I.K.E</title>\n", 1)
    target.write_text(svg, "utf-8")
    (ROOT / "data/icons/ike-browser.svg").write_text(svg, "utf-8")
    return svg


def write_wordmark(font_path):
    d, left, top, right, bottom = lettering(font_path, NAME_TEXT, NAME_WEIGHT, NAME_TRACKING,
                                            NAME_CAP_HEIGHT, NAME_SPACE)
    d = _shift(d, -left, -top)
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %s %s" role="img" '
           'aria-label="Internet Kontrol Experience" fill="currentColor">'
           '<title>Internet Kontrol Experience</title><path d="%s"/></svg>\n'
           % (_num(right - left), _num(bottom - top), d))
    (ROOT / "ike/resources/wordmark.svg").write_text(svg, "utf-8")


def render_png(svg_bytes, size):
    """The drawing as a size x size picture (QImage)."""
    from PyQt6.QtCore import QByteArray, QRectF
    from PyQt6.QtGui import QImage, QPainter
    from PyQt6.QtSvg import QSvgRenderer
    renderer = QSvgRenderer(QByteArray(svg_bytes))
    if not renderer.isValid():
        raise SystemExit("the logo is not a valid SVG file")
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    return image


def write_pngs(svg):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtGui import QGuiApplication
    app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
    for folder, sizes in PNG_SIZES.items():
        for size in sizes:
            target = ROOT / folder / ("ike-browser-%d.png" % size)
            if not render_png(svg.encode("utf-8"), size).save(str(target), "PNG"):
                raise SystemExit("could not write %s" % target)
    del app


def main(argv):
    if len(argv) != 2:
        raise SystemExit(__doc__)
    font_path = argv[1]
    digest = hashlib.sha256(Path(font_path).read_bytes()).hexdigest()
    if digest != FONT_SHA256:
        print("warning: this is not the Orbitron file the lettering was drawn from "
              "(sha256 %s); check the result by eye" % digest, file=sys.stderr)
    svg = write_logo(font_path)
    write_wordmark(font_path)
    write_pngs(svg)
    print("logo, wordmark and icons rewritten")


if __name__ == "__main__":
    main(sys.argv)
