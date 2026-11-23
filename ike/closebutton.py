"""Close buttons drawn like the Plasma window close button
(vertical tabs and the browser's own window close button)."""

import os

from PyQt6.QtCore import QPointF, QSize, Qt
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QToolButton


def _kde_config(name):
    """Minimal reader for a KDE config file: {group: {key: value}}."""
    out, group = {}, ""
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    try:
        with open(os.path.join(base, name), encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if line.startswith("[") and line.endswith("]"):
                    group = line[1:-1]
                elif "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    out.setdefault(group, {})[k.strip()] = v.strip()
    except OSError:
        pass
    return out


class CloseButtonStyle:
    """Draws a close button like the one on the windows of the Plasma theme.

    Breeze (the default decoration): a disc in the text colour with the cross
    cut out, red while the mouse is on it - or the bare cross if the user
    turned the disc off in the Breeze settings. Aurorae themes: the theme's own
    close button image.
    """

    SIZE = 18

    def __init__(self):
        deco = _kde_config("kwinrc").get("org.kde.kdecoration2", {})
        self.outline = (_kde_config("breezerc").get("Common", {})
                        .get("OutlineCloseButton", "true").lower() != "false")
        neg = _kde_config("kdeglobals").get("Colors:Window", {}).get("ForegroundNegative", "")
        try:
            r, g, b = (int(x) for x in neg.split(",")[:3])
            self.negative = QColor(r, g, b)
        except ValueError:
            self.negative = QColor(218, 68, 83)
        self.svg = None
        theme = deco.get("theme", "")
        if theme.startswith("__aurorae__svg__"):
            self._load_aurorae(theme[len("__aurorae__svg__"):])

    def _load_aurorae(self, name):
        try:
            from PyQt6.QtSvg import QSvgRenderer
        except ImportError:
            return
        data = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
        for root in (data, "/usr/share", "/usr/local/share"):
            for ext in ("svg", "svgz"):
                path = os.path.join(root, "aurorae", "themes", name, "close." + ext)
                if os.path.exists(path):
                    renderer = QSvgRenderer(path)
                    if renderer.isValid():
                        self.svg = renderer
                        return

    def paint(self, painter, zone, palette, hovered, pressed, level=None):
        """level: how far the hover has come in, 0-1, while it glides in or
        out (effects.Glide); None = fully on or off, as hovered says."""
        from PyQt6.QtCore import QRectF
        from PyQt6.QtGui import QPalette, QPen

        from .effects import blend
        s = float(self.SIZE)
        box = QRectF(zone.center().x() - s / 2 + 0.5, zone.center().y() - s / 2 + 0.5, s, s)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.svg is not None:
            for element in (("pressed-center",) if pressed else ()) + \
                    (("hover-center",) if hovered else ()) + ("active-center",):
                if self.svg.elementExists(element):
                    self.svg.render(painter, element, box)
                    painter.restore()
                    return
        fg = palette.color(QPalette.ColorRole.Text)
        bg = palette.color(QPalette.ColorRole.Base)
        if level is None or pressed:
            level = 1.0 if (hovered or pressed) else 0.0
        red = self.negative.lighter(125) if pressed else self.negative
        if level <= 0.0:
            disc, cross = (fg, bg) if self.outline else (None, fg)
        elif level >= 1.0:
            disc, cross = red, bg
        elif self.outline:
            disc, cross = blend(fg, red, level), bg
        else:
            disc = QColor(red)
            disc.setAlphaF(level)
            cross = blend(fg, bg, level)
        if disc is not None:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(disc)
            painter.drawEllipse(box)
        pen = QPen(cross, 1.3)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        u = s / 18.0
        x, y = box.left(), box.top()
        painter.drawLine(QPointF(x + 5.5 * u, y + 5.5 * u), QPointF(x + 12.5 * u, y + 12.5 * u))
        painter.drawLine(QPointF(x + 12.5 * u, y + 5.5 * u), QPointF(x + 5.5 * u, y + 12.5 * u))
        painter.restore()


class WindowCloseButton(QToolButton):
    """The browser's own close button (window without the system title bar),
    drawn like the close button of the vertical tabs: red circle on hover."""

    def __init__(self, parent=None, size=None):
        super().__init__(parent)
        self.setProperty("ike_own_hover", True)      # its own red circle (polish.HoverGlides leaves it)
        self.style_ = CloseButtonStyle()
        if size:
            self.style_.SIZE = size          # the disc's diameter
        self.setAutoRaise(True)
        self.setMouseTracking(True)
        self._hovered = False
        from .effects import Glide
        app = getattr(parent, "app", None)
        self._glide = Glide(self, getattr(app, "config", None), self.update)

    def sizeHint(self):
        h = max(super().sizeHint().height(), self.style_.SIZE + 8)
        return QSize(h, h)

    def enterEvent(self, event):
        self._hovered = True
        self._glide.to(1)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self._glide.to(0)
        super().leaveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        self.style_.paint(painter, self.rect(), self.palette(),
                          self._hovered and self.isEnabled(), self.isDown(),
                          self._glide.value if self._glide.moving and self.isEnabled() else None)
        from . import polish
        if polish.keyboard_focus(self):          # reached with Tab: Breeze's ring (1.1.23)
            from PyQt6.QtCore import QRectF
            s = self.style_.SIZE + 4.0
            c = QRectF(self.rect()).center()
            polish.focus_ring(painter, QRectF(c.x() - s / 2, c.y() - s / 2, s, s), self.palette())
        painter.end()
