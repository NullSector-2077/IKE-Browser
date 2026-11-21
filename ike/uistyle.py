"""Room around texts, and menus that scroll (1.1.21).

The desktop's own style (Breeze on Plasma, Fusion elsewhere) draws every
widget; this thin layer over it only asks for a little more room where a
text would otherwise come close to the frame of its button, and lets any
menu taller than the screen scroll instead of running past its edge. Nothing
is drawn differently. tests/test_text_fit.py checks the result in every
language.
"""

from PyQt6.QtCore import QSize
from PyQt6.QtWidgets import QProxyStyle, QStyle, QStyleFactory

# the least room between a text and the frame of its button, on each side
TEXT_ROOM = 8

_style = None            # the style in use (kept here: Qt owns it, Python must not free it)


class IkeStyle(QProxyStyle):
    """The desktop's style, with room around button texts and scrolling menus."""

    def styleHint(self, hint, opt=None, widget=None, ret=None):
        if hint == QStyle.StyleHint.SH_Menu_Scrollable:
            return 1             # a menu taller than the screen scrolls (arrows at both ends)
        return super().styleHint(hint, opt, widget, ret)

    def sizeFromContents(self, kind, opt, size, widget=None):
        s = super().sizeFromContents(kind, opt, size, widget)
        CT = QStyle.ContentsType
        if kind == CT.CT_PushButton and opt is not None and getattr(opt, "text", ""):
            frame = self.pixelMetric(QStyle.PixelMetric.PM_DefaultFrameWidth, opt, widget)
            least = size.width() + 2 * (frame + TEXT_ROOM)
            if s.width() < least:
                s = QSize(least, s.height())
        elif kind == CT.CT_ToolButton and opt is not None and getattr(opt, "text", "") \
                and getattr(opt, "toolButtonStyle", None) is not None:
            from PyQt6.QtCore import Qt
            if opt.toolButtonStyle != Qt.ToolButtonStyle.ToolButtonIconOnly:
                least = size.width() + 2 * (TEXT_ROOM // 2 + 2)
                if s.width() < least:
                    s = QSize(least, s.height())
        return s


def install(qapp):
    """Put the layer over the application's style (once, before the windows open)."""
    global _style
    if isinstance(qapp.style(), IkeStyle):
        return qapp.style()
    base = QStyleFactory.create(qapp.style().name())
    if base is None:
        return None
    _style = IkeStyle(base)
    qapp.setStyle(_style)
    return _style


def screen_area(widget=None):
    """The free area of the screen a window is (or will be) on."""
    from PyQt6.QtGui import QGuiApplication
    screen = None
    while widget is not None and screen is None:
        screen = widget.screen() if widget.isWindow() or widget.parentWidget() is None else None
        widget = widget.parentWidget()
    screen = screen or QGuiApplication.primaryScreen()
    return screen.availableGeometry()


def fit_window(window, width=0, height=0, margin=40):
    """Give a window the size it asks for (at least width x height, and tall
    enough for its wrapped texts at that width), never more than the free
    area of its screen: what does not fit scrolls (1.1.21)."""
    area = screen_area(window.parentWidget() or window)
    room_w, room_h = max(240, area.width() - margin), max(180, area.height() - margin)
    lay = window.layout()
    want = lay.totalSizeHint() if lay is not None else window.sizeHint()
    w = min(max(width, want.width(), window.minimumSizeHint().width()), room_w)
    h = want.height()
    if lay is not None and lay.hasHeightForWidth():
        h = max(h, lay.totalHeightForWidth(w))
    h = min(max(height, h), room_h)
    window.resize(w, h)
    return w, h
