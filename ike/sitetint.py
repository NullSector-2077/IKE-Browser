"""Site colour (1.1.14, 1.1.16): the edge of the address bar takes the site's colour.

The colour is the one the site declares for browsers (<meta name="theme-color">),
read in I.K.E.'s own isolated script world after the page has loaded, so the
page never sees it; when a site declares none, the main colour of its icon is
used. Greys, whites and blacks give none. Only a thin outline around the
address field is drawn in it (1.1.16: the owner found the tinted toolbar of
1.1.14 too much); the rest of the window keeps its theme. It comes and goes
with a short fade when the interface effects are on, and goes away on pages
without a colour, on I.K.E.'s own pages and when the option is off (Settings ->
Appearance). Nothing runs while the option is off.
"""

import re

from PyQt6.QtCore import QObject, QVariantAnimation
from PyQt6.QtGui import QColor

MIN_SATURATION = 50               # below this a colour is a grey: no tint
FADE_MS = 260

_JS = ("(function(){var m=document.querySelector('meta[name=\"theme-color\"]');"
       "return m?String(m.getAttribute('content')||''):'';})()")
_RGB = re.compile(r"rgba?\(\s*(\d{1,3})[\s,]+(\d{1,3})[\s,]+(\d{1,3})")


def parse(text):
    """A CSS colour as sites write it in theme-color, or None."""
    text = (text or "").strip()[:64]
    if not text:
        return None
    m = _RGB.match(text)
    if m:
        c = QColor(*(min(255, int(v)) for v in m.groups()))
    else:
        c = QColor.fromString(text)
    return c if c.isValid() else None


def usable(color):
    """A colour with something of a colour in it (not grey, white or black)."""
    if color is None or not color.isValid():
        return None
    h, s, v, _a = color.getHsv()
    if s < MIN_SATURATION or v < 40:
        return None
    return color


def icon_colour(icon):
    """The main colour of a site icon: the average of its coloured pixels."""
    if icon is None or icon.isNull():
        return None
    img = icon.pixmap(16, 16).toImage()
    if img.isNull():
        return None
    r = g = b = n = 0
    for y in range(img.height()):
        for x in range(img.width()):
            c = img.pixelColor(x, y)
            if c.alpha() < 128:
                continue
            _h, s, v, _a = c.getHsv()
            if s < 80 or v < 50:
                continue
            r, g, b, n = r + c.red(), g + c.green(), b + c.blue(), n + 1
    if n < 12:                                       # mostly grey or transparent
        return None
    return QColor(r // n, g // n, b // n)


class SiteTint(QObject):
    """Draws the site's colour around the window's address bar."""

    def __init__(self, window):
        super().__init__(window)
        self.win = window
        self.shown = None                # the colour of the edge now (None: no colour)
        self._anim = None

    def _on(self):
        try:
            return bool(self.win.app.config["site_tint"])
        except (KeyError, TypeError):
            return False

    def page_loaded(self, view):
        """Read the colour the page declares (in the isolated world)."""
        if not self._on() or view.url().scheme() not in ("http", "https"):
            view.site_colour = None
            self.update(view)
            return
        def got(value, v=view):
            try:
                colour = usable(parse(value if isinstance(value, str) else ""))
                if colour is None:
                    colour = usable(icon_colour(getattr(v, "last_icon", None)))
                v.site_colour = colour
                if v is self.win.current_view():
                    self.update(v)
            except RuntimeError:          # the tab was closed meanwhile
                pass
        view.page().runJavaScript(_JS, 1, got)      # 1: I.K.E.'s isolated world (ApplicationWorld)

    def icon_changed(self, view):
        """A late icon helps a page that declares no colour."""
        if self._on() and getattr(view, "site_colour", None) is None \
                and view.url().scheme() in ("http", "https") and not getattr(view, "loading", False):
            view.site_colour = usable(icon_colour(getattr(view, "last_icon", None)))
            if view is self.win.current_view():
                self.update(view)

    def update(self, view):
        """Give the address bar's edge the colour of the page in front (or take it away)."""
        bar = getattr(self.win, "urlbar", None)
        if bar is None:
            return
        colour = getattr(view, "site_colour", None) if (view is not None and self._on()) else None
        if colour is not None and view.url().scheme() not in ("http", "https"):
            colour = None
        target = QColor(colour) if colour is not None else None
        if target == self.shown:
            return
        start = QColor(self.shown) if self.shown is not None else None
        self.shown = target
        if self._anim is not None:
            self._anim.stop()
            self._anim = None
        from . import effects
        if not effects.on(self.win.app.config) or (start is None and target is None):
            self._paint(target)
            return
        # fade in from transparent, out to transparent, or from one colour to the next
        if start is None:
            start = QColor(target)
            start.setAlpha(0)
        end = target
        if end is None:
            end = QColor(start)
            end.setAlpha(0)
        anim = self._anim = QVariantAnimation(self)
        anim.setStartValue(start)
        anim.setEndValue(end)
        anim.setDuration(FADE_MS)
        anim.valueChanged.connect(self._paint)
        anim.finished.connect(lambda t=target: self._paint(t))
        anim.start()

    def _paint(self, colour):
        bar = self.win.urlbar
        bar.site_edge = QColor(colour) if colour is not None and colour.alpha() > 0 else None
        bar.update()
