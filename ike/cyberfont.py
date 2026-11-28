"""The shield's numbers and the new tab page's figures in the logo's typeface (1.1.30).

The owner: the numbers beside the octagon "as cyber as possible, in the colour of the logo's K,
discreet", and the new tab page's figures and their words in the same letters. The typeface is
Orbitron, the one the logo's lettering was drawn with (SIL Open Font License 1.1,
licenses/LICENSE.orbitron; the file is Google Fonts' ``ofl/orbitron/Orbitron[wght].ttf``,
version 2.001, unchanged, in ike/resources/fonts/).

It is never installed in the font database: the fingerprinting protection lists the families
installed for Qt (fontcheck.py), and a page must not find a font I.K.E. brought. The shield draws
it from the file (QRawFont, outlines only), and the new tab page loads it as a web font of its own.

The colour is the logo's K: its light blue on a dark background, its darkest blue on a light one,
made readable (3:1, as WCAG asks of large figures) when the theme's colours need it.
"""

import base64
import functools

FONT_FILE = "fonts/orbitron.ttf"
K_LIGHT = "#65C2EF"            # the light blue of the logo's K (on dark backgrounds)
K_DARK = "#299BD4"             # the darkest blue of the logo's K (on light backgrounds)


def _path():
    from .config import RES_DIR
    return RES_DIR / FONT_FILE


@functools.lru_cache(maxsize=1)
def font_bytes():
    try:
        return _path().read_bytes()
    except OSError:
        return b""


@functools.lru_cache(maxsize=1)
def data_url():
    """The font as a data: address for a page's @font-face ("" when it is missing)."""
    data = font_bytes()
    return "data:font/ttf;base64," + base64.b64encode(data).decode("ascii") if data else ""


def k_colour(background, foreground=None, ratio=3.0):
    """The logo's K on this background, readable at `ratio`."""
    from PyQt6.QtGui import QColor
    c = QColor(K_DARK if background.lightnessF() > 0.5 else K_LIGHT)
    if foreground is not None:
        from .uistyle import readable
        c = readable(c, background, foreground, ratio)
    return c


@functools.lru_cache(maxsize=16)
def _raw(pixel_size):
    from PyQt6.QtCore import QByteArray
    from PyQt6.QtGui import QFont, QRawFont
    data = font_bytes()
    if not data:
        return None
    raw = QRawFont(QByteArray(data), float(pixel_size), QFont.HintingPreference.PreferNoHinting)
    return raw if raw.isValid() else None


def usable(text, pixel_size):
    """Can the typeface draw every character of `text`?"""
    raw = _raw(pixel_size)
    return bool(text) and raw is not None and all(raw.supportsCharacter(ch) for ch in text)


def width(text, pixel_size):
    raw = _raw(pixel_size)
    if raw is None:
        return 0.0
    glyphs = raw.glyphIndexesForString(text)
    return sum(p.x() for p in raw.advancesForGlyphIndexes(glyphs))


def outline(text, pixel_size):
    """(path, width, cap height) of `text` on a baseline at y = 0, or None."""
    from PyQt6.QtGui import QPainterPath
    raw = _raw(pixel_size)
    if raw is None:
        return None
    glyphs = raw.glyphIndexesForString(text)
    path, x = QPainterPath(), 0.0
    for glyph, adv in zip(glyphs, raw.advancesForGlyphIndexes(glyphs)):
        g = raw.pathForGlyph(glyph)
        g.translate(x, 0)
        path.addPath(g)
        x += adv.x()
    return path, x, raw.capHeight()


def paint(p, left, centre_y, text, pixel_size, colour):
    """Draw `text` from `left`, its capitals centred on `centre_y`; the width drawn (0: not drawn)."""
    out = outline(text, pixel_size)
    if out is None:
        return 0.0
    path, w, cap = out
    dev = p.device()
    dpr = dev.devicePixelRatioF() if dev is not None else 1.0
    # the baseline on a whole device pixel: the figures stay sharp
    base = round((centre_y + cap / 2) * dpr) / dpr
    path.translate(round(left * dpr) / dpr, base)
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QPainter
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.fillPath(path, colour)
    p.restore()
    return w
