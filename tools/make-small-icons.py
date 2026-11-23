#!/usr/bin/env python3
"""Draw I.K.E.'s application icon for the small sizes, one drawing per size.

    python3 tools/make-small-icons.py

At 16 to 64 pixels the scalable logo (data/icons/ike-browser.svg) shrinks its
"I.K.E" plate to a few blurred pixels. Each small size is therefore drawn on its
own pixel grid: the same shield, colours and plate, with the lettering larger
and bolder, every stem, bar and border on whole pixels, and the circuit lines
dropped where they would compete with the letters (below 48 px); up to 24 px
the plate runs across the shield, as its sides would touch the letters. The letters
keep the logo's own construction (Orbitron 800: square stems one fifth of the
capital height, the K with its middle bar), set by hand pixel by pixel; at
16 px the two dots are dropped, as there is no room for "I.K.E" with a pixel
between the letters.

It writes, for every size N in SIZES,

    data/icons/small/ike-browser-N.svg   the drawing (N x N, no text, no font)
    data/icons/ike-browser-N.png         the drawing as a picture, for the desktop
    ike/resources/icons/ike-browser-N.png   the same picture, for the window icon

The large sizes (128 px and up) and the scalable logo are not touched: they come
from tools/make-brand.py. Needs PyQt6 (QtSvg) on the computer that runs it.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SIZES = (16, 22, 24, 32, 48, 64)
SVG_DIR = "data/icons/small"
PNG_DIRS = ("data/icons", "ike/resources/icons")

EDGE_STOPS = (("0", "#7df3ff"), ("0.5", "#19c3e6"), ("1", "#2f6bff"))
BODY_STOPS = (("0", "#12324a"), ("1", "#07131f"))
PLATE_FILL = "#07131f"
PLATE_BORDER_OPACITY = "0.7"      # the logo's thin plate border looks this bright at its own size
LINE = "#19c3e6"
DOT = "#7df3ff"
LETTER = "#eafcff"

# --- the letters, pixel by pixel ("#" is lit) --------------------------------
# cap 5, stroke 1: the logo's proportions at one pixel per stroke
GLYPHS_5 = {
    "I": ["#"] * 5,
    ".": [".", ".", ".", ".", "#"],
    "K": ["#..#",
          "#.#.",
          "##..",
          "#.#.",
          "#..#"],
    "E": ["###",
          "#..",
          "###",
          "#..",
          "###"],
}
# cap 7, stroke 1: for 32 px
GLYPHS_7S = {
    "I": ["#"] * 7,
    ".": ["."] * 6 + ["#"],
    "K": ["#...#",
          "#..#.",
          "#.#..",
          "##...",
          "#.#..",
          "#..#.",
          "#...#"],
    "E": ["####",
          "#...",
          "#...",
          "###.",
          "#...",
          "#...",
          "####"],
}
# cap 7, stems 2: for 48 px
GLYPHS_7 = {
    "I": ["##"] * 7,
    ".": ["..", "..", "..", "..", "..", "##", "##"],
    "K": ["##...##",
          "##..##.",
          "##.##..",
          "####...",
          "##.##..",
          "##..##.",
          "##...##"],
    "E": ["#####",
          "##...",
          "##...",
          "####.",
          "##...",
          "##...",
          "#####"],
}
# cap 10, stroke 2: the logo's proportions at two pixels per stroke
GLYPHS_10 = {
    "I": ["##"] * 10,
    ".": [".."] * 8 + ["##"] * 2,
    "K": ["##....##",
          "##...##.",
          "##..##..",
          "##.##...",
          "#####...",
          "#####...",
          "##.##...",
          "##..##..",
          "##...##.",
          "##....##"],
    "E": ["########",
          "########",
          "##......",
          "##......",
          "#######.",
          "#######.",
          "##......",
          "##......",
          "########",
          "########"],
}

# --- one drawing per size ----------------------------------------------------
# shield: centre x, apex y, shoulder drop, half width, end of the straight sides,
#         bottom y, edge width (sides), edge at the apex, edge at the bottom
# plate: ("box", x, y, width, height (the border included), border, corner radius)
#        or ("band", y, height, border): a plate across the whole shield
# text: glyph set, the letters with the pixels between them, left x, top y
SPECS = {
    16: dict(shield=(8, 0, 2, 7, 7, 16, 1, 1, 1), plate=("band", 3, 9, 1),
             glyphs=GLYPHS_5, text=["I", 1, "K", 1, "E"], at=(3, 5), circuits=False),
    22: dict(shield=(11, 0, 3, 9, 10, 22, 1, 1, 1), plate=("band", 6, 9, 1),
             glyphs=GLYPHS_5, text=["I", 1, ".", 1, "K", 1, ".", 1, "E"], at=(4, 8), circuits=False),
    24: dict(shield=(12, 0, 3, 10, 11, 24, 1, 1, 1), plate=("band", 7, 9, 1),
             glyphs=GLYPHS_5, text=["I", 1, ".", 1, "K", 1, ".", 1, "E"], at=(5, 9), circuits=False),
    32: dict(shield=(16, 0, 4, 13, 16, 32, 2, 2, 2), plate=("box", 6, 9, 20, 11, 1, 0),
             glyphs=GLYPHS_7S, text=["I", 1, ".", 1, "K", 1, ".", 1, "E"], at=(8, 11), circuits=False),
    48: dict(shield=(24, 2, 5, 19, 21, 47, 2, 2, 2), plate=("box", 9, 17, 30, 13, 1, 1),
             glyphs=GLYPHS_7, text=["I", 1, ".", 1, "K", 1, ".", 1, "E"], at=(13, 20), circuits=True),
    64: dict(shield=(32, 2, 9, 24, 28, 63, 3, 3, 4), plate=("box", 13, 22, 38, 18, 1, 2),
             glyphs=GLYPHS_10, text=["I", 2, ".", 2, "K", 2, ".", 2, "E"], at=(17, 26), circuits=True),
}


def _num(v):
    text = "%.3f" % v
    text = text.rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


def shield_path(cx, top, drop, half, y2, bottom):
    """The logo's shield outline: apex, shoulders, straight sides, curved bottom
    (the curve of ike-browser.svg, scaled)."""
    h = bottom - y2
    c1y, c2y, c2x = y2 + 0.484 * h, y2 + 0.836 * h, 0.582 * half
    n = _num
    return ("M%s %s L%s %s V%s C%s %s %s %s %s %s C%s %s %s %s %s %s V%s Z" % (
        n(cx), n(top), n(cx + half), n(top + drop), n(y2),
        n(cx + half), n(c1y), n(cx + c2x), n(c2y), n(cx), n(bottom),
        n(cx - c2x), n(c2y), n(cx - half), n(c1y), n(cx - half), n(y2), n(top + drop)))


def lettering(glyphs, text, at):
    """The letters as one path of whole-pixel rectangles (one per lit run)."""
    rows = len(glyphs["I"])
    x0, y0 = at
    runs = []
    x = x0
    for item in text:
        if isinstance(item, int):
            x += item
            continue
        glyph = glyphs[item]
        assert len(glyph) == rows, item
        for r, line in enumerate(glyph):
            c = 0
            while c < len(line):
                if line[c] == "#":
                    start = c
                    while c < len(line) and line[c] == "#":
                        c += 1
                    runs.append((x + start, y0 + r, c - start))
                else:
                    c += 1
        x += len(glyph[0])
    # join runs of the same columns on consecutive rows into one rectangle
    rects = []
    for rx, ry, w in sorted(runs, key=lambda t: (t[0], t[2], t[1])):
        if rects and rects[-1][0] == rx and rects[-1][2] == w and rects[-1][1] + rects[-1][3] == ry:
            rects[-1][3] += 1
        else:
            rects.append([rx, ry, w, 1])
    rects.sort(key=lambda t: (t[1], t[0]))
    return " ".join("M%d %dh%dv%dh-%dZ" % (rx, ry, w, h, w) for rx, ry, w, h in rects)


def circuits(size, body_top, body_bottom, plate_bottom):
    """The logo's circuit lines and their dots, for 48 and 64 px: the side lines
    1 px wide on pixel centres, their diagonals at 45 degrees, the right half the
    mirror of the left; the lines on the centre 2 px wide (the shield's centre
    falls between two pixels) and fainter; the dots 2 x 2 px on whole pixels."""
    k = size / 256.0

    def px(v):
        return int(v * k + 0.5)

    def side_line(x, y, steps):
        """Pixel columns and rows of a line from (x, y), by (dx, dy) steps in
        the logo's units; returns its points as pixel cells."""
        c, r = int(x * k), int(y * k)
        cells = [(c, r)]
        for dx, dy in steps:
            n = px(max(abs(dx), abs(dy)))
            c += n * (dx > 0) - n * (dx < 0)
            r += n * (dy > 0) - n * (dy < 0)
            cells.append((c, r))
        return cells

    left = [side_line(42, 78, [(32, 0), (14, -14), (32, 0)]),
            side_line(52, 168, [(32, 0), (14, 14), (0, 22)])]
    lines = []
    for cells in left:
        for mirror in (False, True):
            pts = [((size - 1 - c) if mirror else c, r) for c, r in cells]
            lines.append('<path d="M%s"/>' % " L".join("%s %s" % (_num(c + 0.5), _num(r + 0.5)) for c, r in pts))
    (c1, r1), (c2, r2) = left[0][-1], left[1][-1]
    dots = [(c1 - 1, r1), (size - 1 - c1, r1),          # the pair under the top one
            (c2, r2), (size - 2 - c2, r2)]              # the ends of the lower lines
    mid = size // 2 - 1
    high = min(px(52) - 1, r1 - 3)                       # the two dots on the centre
    low = max(px(176) - 1, plate_bottom + 1)
    dots += [(mid, high), (mid, low)]
    centre = ['<path d="M%d %dh2v%dh-2Z"/>' % (mid, body_top + 1, high - body_top - 1),
              '<path d="M%d %dh2v%dh-2Z"/>' % (mid, low + 2, body_bottom - 3 - low - 2)]
    rects = ['<rect x="%d" y="%d" width="2" height="2"/>' % (c, r) for c, r in dots]
    return lines, centre, rects


def drawing(size):
    spec = SPECS[size]
    cx, top, drop, half, y2, bottom, edge, edge_top, edge_bottom = spec["shield"]
    outer = shield_path(cx, top, drop, half, y2, bottom)
    inner_half = half - edge
    inner = shield_path(cx, top + edge_top, drop * inner_half / half, inner_half, y2, bottom - edge_bottom)
    letters = lettering(spec["glyphs"], spec["text"], spec["at"])
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="%d" height="%d">' % (
            size, size, size, size),
        '  <title>I.K.E</title>',
        '  <defs>',
        '    <linearGradient id="body" x1="0" y1="0" x2="0" y2="1">',
    ]
    parts += ['      <stop offset="%s" stop-color="%s"/>' % s for s in BODY_STOPS]
    parts += ['    </linearGradient>', '    <linearGradient id="edge" x1="0" y1="0" x2="1" y2="1">']
    parts += ['      <stop offset="%s" stop-color="%s"/>' % s for s in EDGE_STOPS]
    parts += ['    </linearGradient>',
              '  </defs>',
              '  <path d="%s" fill="url(#edge)"/>' % outer,
              '  <path d="%s" fill="url(#body)"/>' % inner]
    if spec["circuits"]:
        plate = spec["plate"]
        lines, centre, dots = circuits(size, top + edge_top, bottom - edge_bottom, plate[2] + plate[4])
        parts.append('  <g fill="none" stroke="%s" stroke-width="1" stroke-linecap="square" opacity="0.55">'
                     % LINE)
        parts += ["    " + line for line in lines]
        parts.append('  </g>')
        parts.append('  <g fill="%s" opacity="0.4">' % LINE)
        parts += ["    " + line for line in centre]
        parts.append('  </g>')
        parts.append('  <g fill="%s">' % DOT)
        parts += ["    " + d for d in dots]
        parts.append('  </g>')
    plate = spec["plate"]
    if plate and plate[0] == "box":
        _, x, y, w, h, border, radius = plate
        parts.append('  <rect x="%d" y="%d" width="%d" height="%d" rx="%s" fill="%s" opacity="%s"/>' % (
            x, y, w, h, _num(radius), LINE, PLATE_BORDER_OPACITY))
        parts.append('  <rect x="%d" y="%d" width="%d" height="%d" rx="%s" fill="%s"/>' % (
            x + border, y + border, w - 2 * border, h - 2 * border, _num(max(0, radius - border)),
            PLATE_FILL))
    elif plate:
        # no room for the plate's sides: it runs across the shield, from edge to
        # edge, and the edge is drawn again over its ends
        _, y, h, border = plate
        x, w = cx - inner_half, 2 * inner_half
        parts.append('  <rect x="%s" y="%d" width="%s" height="%d" fill="%s"/>' % (
            _num(x), y, _num(w), h, PLATE_FILL))
        parts.append('  <path d="M%s %dh%sv%dh-%sZ M%s %dh%sv%dh-%sZ" fill="%s" opacity="%s"/>' % (
            _num(x), y, _num(w), border, _num(w), _num(x), y + h - border, _num(w), border, _num(w),
            LINE, PLATE_BORDER_OPACITY))
        parts.append('  <path d="%s %s" fill="url(#edge)" fill-rule="evenodd"/>' % (outer, inner))
    parts.append('  <path id="lettering" fill="%s" d="%s"/>' % (LETTER, letters))
    parts.append('</svg>')
    return "\n".join(parts) + "\n"


def render_png(svg_bytes, size):
    from PyQt6.QtCore import QByteArray, QRectF
    from PyQt6.QtGui import QImage, QPainter
    from PyQt6.QtSvg import QSvgRenderer
    renderer = QSvgRenderer(QByteArray(svg_bytes))
    if not renderer.isValid():
        raise SystemExit("the drawing for %d px is not a valid SVG file" % size)
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    return image


def main(argv):
    root = Path(argv[1]) if len(argv) > 1 else ROOT
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtGui import QGuiApplication
    app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
    (root / SVG_DIR).mkdir(parents=True, exist_ok=True)
    for size in SIZES:
        svg = drawing(size)
        (root / SVG_DIR / ("ike-browser-%d.svg" % size)).write_text(svg, "utf-8")
        image = render_png(svg.encode("utf-8"), size)
        for folder in PNG_DIRS:
            (root / folder).mkdir(parents=True, exist_ok=True)
            target = root / folder / ("ike-browser-%d.png" % size)
            if not image.save(str(target), "PNG"):
                raise SystemExit("could not write %s" % target)
    del app
    print("small icons written: %s" % ", ".join("%d px" % s for s in SIZES))


if __name__ == "__main__":
    main(sys.argv)
