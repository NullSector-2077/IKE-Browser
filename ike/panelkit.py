"""Small parts shared by the panels of the toolbar's buttons (1.1.25): the dark
mode's (darkpanel.py), the zoom's (zoompanel.py) and the downloads'
(downloadpanel.py). Each panel opens under its button, in a popup made the
first time it opens (window.BrowserWindow._panel_popup); these are the pieces
they have in common, so they look and line up alike:

- the title row: the button's icon, drawn from the panel's left edge, and the
  title in bold;
- a dimmed line of help, a little smaller;
- a link-like button (I.K.E.'s own windows and folders only, never an
  address outside I.K.E.);
- a label that shortens a long text in its middle (a file's name).
"""

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSizePolicy

MARGINS = (14, 12, 14, 12)       # the shield panel's
WIDTH = 320 + 28                 # as wide as the shield's panel


def trim_left(pm):
    """The picture without the empty columns on its left: its drawing starts on
    the panel's left edge, as the texts under it do."""
    img = pm.toImage()
    for x in range(img.width()):
        if any(img.pixelColor(x, y).alpha() > 40 for y in range(img.height())):
            return pm.copy(x, 0, img.width() - x, img.height()) if x else pm
    return pm


def title_row(parent, ic, text, size=18):
    """(layout, icon label, title label): the panel's first row (ic: a QIcon, asked
    for with icons.themed where the panel is made, so tools/build-breeze-icons.py
    finds its names)."""
    row = QHBoxLayout()
    row.setSpacing(8)
    pic = QLabel(parent)
    pic.setPixmap(trim_left(ic.pixmap(size, size)))
    title = QLabel(text, parent)
    f = title.font()
    f.setBold(True)
    title.setFont(f)
    row.addWidget(pic)
    row.addWidget(title, 1)
    return row, pic, title


def dim(label, factor=0.9):
    """A line of help: a little smaller, in the palette's dimmed text colour."""
    f = label.font()
    if f.pointSizeF() > 0 and factor != 1.0:
        f.setPointSizeF(f.pointSizeF() * factor)
        label.setFont(f)
    pal = label.palette()
    col = QColor(pal.color(QPalette.ColorRole.WindowText))
    col.setAlphaF(0.66)
    pal.setColor(QPalette.ColorRole.WindowText, col)
    label.setPalette(pal)
    return label


def link_button(parent, ic, text):
    """A flat button drawn as a link, its icon (a QIcon) on the panel's left edge."""
    b = QPushButton(ic, text, parent)
    b.setFlat(True)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setIconSize(QSize(16, 16))
    b.setStyleSheet("QPushButton { text-align: left; color: palette(link); border: none;"
                    " padding: 4px 8px 4px 0px; }"
                    "QPushButton:hover { text-decoration: underline; }"
                    "QPushButton:focus { text-decoration: underline; }")
    return b


class ElideLabel(QLabel):
    """A label whose text, when it does not fit, is shortened in its middle (the
    start and the end of a file's name stay); the whole text is its tooltip."""

    def __init__(self, text="", parent=None, mode=Qt.TextElideMode.ElideMiddle):
        super().__init__(parent)
        self.mode = mode
        self.full = ""
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(10)
        self.set_full(text)

    def set_full(self, text):
        if text != self.full:
            self.full = text or ""
            self._elide()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._elide()

    def _elide(self):
        shown = self.fontMetrics().elidedText(self.full, self.mode, max(10, self.width()))
        if shown != self.text():
            self.setText(shown)
        self.setToolTip(self.full if shown != self.full else "")

    def sizeHint(self):
        s = super().sizeHint()
        return QSize(min(s.width(), self.fontMetrics().horizontalAdvance(self.full) + 2), s.height())


def negative():
    """The colour scheme's colour for something gone wrong (Breeze's red where the
    desktop sets none)."""
    from .closebutton import _kde_config
    scheme = _kde_config("kdeglobals").get("Colors:Window", {})
    try:
        r, g, b = (int(x) for x in scheme.get("ForegroundNegative", "").split(",")[:3])
        return QColor(r, g, b)
    except ValueError:
        return QColor("#da4453")
