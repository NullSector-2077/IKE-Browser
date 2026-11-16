"""The look of the "I.K.E. Cyber" theme in the browser's own windows: tabs with
cut corners, slanted sides or brackets, thin luminous lines, a field for the
address with a cut frame.

Only what Qt already offers is used: shapes are painted with QPainter, the
glow is a few wider, fainter strokes under a line (no blur, nothing behind the
window). With any other theme, and with "Follow the system", nothing of this
runs: the desktop's style draws everything as before.
"""

from PyQt6.QtCore import QEasingCurve, QEvent, QPointF, QRect, QRectF, Qt, QVariantAnimation
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen, QPolygonF
from PyQt6.QtWidgets import QProxyStyle, QStyle, QWidget

SHAPES = ("smusso", "lama", "mirino")
SLANT = 12                    # how far the sides of a "lama" tab lean
GLIDE_MS = 160


class Look:
    """What the Cyber theme needs to paint, read once from the settings."""

    def __init__(self, config, theme):
        data = getattr(config, "data", {})
        self.accent = QColor(theme["accent"])
        self.text = QColor(theme["text"])
        self.tabs = QColor(theme["tabs"])
        self.toolbar = QColor(theme["toolbar"])
        self.background = QColor(theme["background"])
        shape = data.get("cyber_shape")
        self.shape = shape if shape in SHAPES else "smusso"
        self.glow = bool(data.get("cyber_glow", True))
        self.cut = 10 if data.get("cyber_corners", True) else 0
        self.config = config

    def mix(self, a, b, t):
        return QColor(round(a.red() + (b.red() - a.red()) * t), round(a.green() + (b.green() - a.green()) * t),
                      round(a.blue() + (b.blue() - a.blue()) * t))

    def fill(self, selected, hover):
        """The colour of a tab's own surface."""
        return self.mix(self.tabs, self.text, 0.13 if selected else 0.08 if hover else 0.035)

    @property
    def line(self):
        return self.mix(self.tabs, self.text, 0.16)


def look(config):
    """The Look when the Cyber theme is in use, else None."""
    from . import themes
    theme = themes.current(config)
    return Look(config, theme) if themes.is_cyber(theme) else None


# --- shapes -----------------------------------------------------------------
def cut_path(rect, cut, corners="tl br"):
    """A rectangle with some corners cut at 45 degrees ("tl", "tr", "br", "bl")."""
    r = QRectF(rect)
    c = max(0.0, min(float(cut), r.width() / 2, r.height() / 2))
    path = QPainterPath()
    pts = []
    for name, (x, y), (dx, dy) in (("tl", (r.left(), r.top()), ((0, 1), (1, 0))),
                                   ("tr", (r.right(), r.top()), ((-1, 0), (0, 1))),
                                   ("br", (r.right(), r.bottom()), ((0, -1), (-1, 0))),
                                   ("bl", (r.left(), r.bottom()), ((1, 0), (0, -1)))):
        if c and name in corners:
            pts.append(QPointF(x + dx[0] * c, y + dx[1] * c))
            pts.append(QPointF(x + dy[0] * c, y + dy[1] * c))
        else:
            pts.append(QPointF(x, y))
    path.addPolygon(QPolygonF(pts))
    path.closeSubpath()
    return path


def tab_path(rect, shape, cut):
    """The outline of a horizontal tab."""
    r = QRectF(rect)
    if shape == "lama":
        s = min(float(SLANT), r.width() / 3)
        path = QPainterPath()
        path.addPolygon(QPolygonF([QPointF(r.left() + s, r.top()), QPointF(r.right(), r.top()),
                                   QPointF(r.right() - s, r.bottom()), QPointF(r.left(), r.bottom())]))
        path.closeSubpath()
        return path
    if shape == "mirino":
        path = QPainterPath()
        path.addRect(r)
        return path
    return cut_path(r, cut, "tl")


def row_path(rect, shape, cut):
    """The outline of a row of the vertical tabs."""
    r = QRectF(rect)
    if shape == "lama":
        s = min(float(SLANT), r.width() / 4)
        path = QPainterPath()
        path.addPolygon(QPolygonF([QPointF(r.left(), r.top()), QPointF(r.right(), r.top()),
                                   QPointF(r.right() - s, r.bottom()), QPointF(r.left(), r.bottom())]))
        path.closeSubpath()
        return path
    if shape == "mirino":
        path = QPainterPath()
        path.addRect(r)
        return path
    return cut_path(r, cut * 0.8, "tl br")


def glow_line(p, a, b, colour, glow=True, width=2.0):
    """A luminous line: fainter, wider strokes under the line itself."""
    colour = QColor(colour)
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    if glow:
        for extra, alpha in ((6.0, 34), (3.0, 70)):
            halo = QColor(colour)
            halo.setAlpha(alpha)
            pen = QPen(halo, width + extra)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawLine(QPointF(a), QPointF(b))
    pen = QPen(colour, width)
    pen.setCapStyle(Qt.PenCapStyle.FlatCap)
    p.setPen(pen)
    p.drawLine(QPointF(a), QPointF(b))
    p.restore()


def brackets(p, rect, colour, glow=True):
    """Two square brackets around rect, like the corners of a viewfinder."""
    r = QRectF(rect).adjusted(3, 5, -3, -5)
    arm = 6.0
    for x, d in ((r.left(), 1), (r.right(), -1)):
        for a, b in (((x + d * arm, r.top()), (x, r.top())), ((x, r.top()), (x, r.bottom())),
                     ((x, r.bottom()), (x + d * arm, r.bottom()))):
            glow_line(p, QPointF(*a), QPointF(*b), colour, glow)


def mark(p, rect, lk, vertical=False):
    """The sign of the current tab: a line above it (smusso), below it (lama)
    or two brackets (mirino); for the vertical tabs the line is at the left."""
    r = QRectF(rect)
    if lk.shape == "mirino":
        brackets(p, r, lk.accent, lk.glow)
    elif vertical and lk.shape == "smusso":
        c = lk.cut * 0.8
        glow_line(p, QPointF(r.left() + 1, r.top() + c), QPointF(r.left() + 1, r.bottom()), lk.accent, lk.glow, 3.0)
        if c:
            glow_line(p, QPointF(r.left() + 1, r.top() + c), QPointF(r.left() + c, r.top() + 1), lk.accent, lk.glow)
    elif lk.shape == "lama":
        s = min(float(SLANT), r.width() / (4 if vertical else 3))
        glow_line(p, QPointF(r.left() + (0 if vertical else 2), r.bottom() - 1),
                  QPointF(r.right() - s, r.bottom() - 1), lk.accent, lk.glow)
    else:
        c = float(lk.cut)
        glow_line(p, QPointF(r.left() + c, r.top() + 1), QPointF(r.right(), r.top() + 1), lk.accent, lk.glow)
        if c:
            glow_line(p, QPointF(r.left() + 1, r.top() + c), QPointF(r.left() + c, r.top() + 1), lk.accent, lk.glow)


# --- horizontal tabs: a style of our own for the tab bar ----------------------
class TabStyle(QProxyStyle):
    """Draws the tabs of a QTabBar in the Cyber shapes. Text, icon, close
    button, dragging and scrolling stay those of the desktop's style."""

    def __init__(self, lk, group_colour=None):
        super().__init__()
        self.lk = lk
        self.group_colour = group_colour or (lambda index: None)
        self.gliding = False              # while the mark glides, MarkGlide paints it

    def drawControl(self, element, opt, p, widget=None):
        if element == QStyle.ControlElement.CE_TabBarTabShape:
            self._tab(opt, p)
            return
        super().drawControl(element, opt, p, widget)

    def drawPrimitive(self, element, opt, p, widget=None):
        if element == QStyle.PrimitiveElement.PE_FrameTabBarBase:
            p.save()
            p.setPen(QPen(self.lk.line, 1))
            y = opt.rect.bottom()
            p.drawLine(opt.rect.left(), y, opt.rect.right(), y)
            p.restore()
            return
        super().drawPrimitive(element, opt, p, widget)

    def pixelMetric(self, metric, opt=None, widget=None):
        M = QStyle.PixelMetric
        if metric == M.PM_TabBarTabOverlap:
            return SLANT - 2 if self.lk.shape == "lama" else 0
        if metric in (M.PM_TabBarBaseOverlap, M.PM_TabBarTabShiftVertical, M.PM_TabBarTabShiftHorizontal):
            return 0
        if metric == M.PM_TabBarTabHSpace:
            return super().pixelMetric(metric, opt, widget) + (2 * SLANT if self.lk.shape == "lama" else 8)
        return super().pixelMetric(metric, opt, widget)

    def tab_rect(self, rect, selected):
        """Where the shape of a tab is painted inside the tab's own area."""
        r = QRect(rect)
        if self.lk.shape != "lama":
            r.adjust(1, 0, -1, 0)
        r.setTop(r.top() + (1 if selected else 4))
        return r

    def _tab(self, opt, p):
        lk = self.lk
        S = QStyle.StateFlag
        selected = bool(opt.state & S.State_Selected)
        hover = bool(opt.state & S.State_MouseOver)
        r = self.tab_rect(opt.rect, selected)
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        if lk.shape != "mirino" or selected or hover:
            p.setBrush(lk.fill(selected, hover))
            p.drawPath(tab_path(r, lk.shape, lk.cut))
        index = getattr(opt, "tabIndex", -1)
        group = self.group_colour(index) if index >= 0 else None
        if group:                                    # the colour of the tab's group on its leading edge
            g = QColor(group)
            if lk.shape == "smusso" and lk.cut:
                glow_line(p, QPointF(r.left() + 1, r.top() + lk.cut), QPointF(r.left() + lk.cut, r.top() + 1),
                          g, lk.glow)
            else:
                glow_line(p, QPointF(r.left() + (SLANT if lk.shape == "lama" else 2), r.bottom() - 1),
                          QPointF(r.left() + (SLANT if lk.shape == "lama" else 2) + 14, r.bottom() - 1), g, lk.glow)
        if selected and not self.gliding:
            mark(p, r, lk)
        p.restore()


class MarkGlide(QWidget):
    """The sign of the current tab while it moves from the old tab to the new
    one: a child widget over the tabs that paints only during the glide."""

    def __init__(self, host, lk, rect_of_current, vertical=False, on_state=None):
        super().__init__(host)
        self.lk, self.rect_of_current, self.vertical = lk, rect_of_current, vertical
        self.on_state = on_state or (lambda gliding: None)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self._from = self._to = None
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(GLIDE_MS)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.valueChanged.connect(lambda _v: self.update())
        self._anim.finished.connect(self._done)
        self._last = None
        self.hide()
        host.installEventFilter(self)

    def eventFilter(self, obj, event):
        if obj is self.parent() and event.type() == QEvent.Type.Resize:
            self.setGeometry(self.parent().rect())
        return False

    def remember(self):
        """Note where the mark is now (called when nothing is moving)."""
        r = self.rect_of_current()
        self._last = QRectF(r) if r is not None and r.isValid() else None

    def current_changed(self):
        """The current tab changed: glide from where the mark was."""
        from . import effects
        new = self.rect_of_current()
        old, self._last = self._last, (QRectF(new) if new is not None and new.isValid() else None)
        if old is None or self._last is None or old == self._last or not effects.on(self.lk.config) \
                or not self.parent().isVisible():
            return
        self._from, self._to = old, QRectF(self._last)
        self.setGeometry(self.parent().rect())
        self.on_state(True)
        self.show()
        self.raise_()
        self._anim.stop()
        self._anim.start()

    def _done(self):
        self.hide()
        self.on_state(False)

    def stop(self):
        if self._anim.state() == QVariantAnimation.State.Running:
            self._anim.stop()
            self._done()

    def paintEvent(self, _event):
        if self._from is None or self._to is None:
            return
        t = float(self._anim.currentValue() or 0.0)
        a, b = self._from, self._to
        r = QRectF(a.left() + (b.left() - a.left()) * t, a.top() + (b.top() - a.top()) * t,
                   a.width() + (b.width() - a.width()) * t, a.height() + (b.height() - a.height()) * t)
        p = QPainter(self)
        mark(p, r, self.lk, self.vertical)
        p.end()


# --- vertical tabs: called by the delegate of the list ------------------------
def row_rect(rect):
    return QRect(rect).adjusted(4, 2, -4, -2)


def paint_row(p, rect, lk, selected, hover, group=None, with_mark=True):
    """The surface of a row of the vertical tabs (the delegate adds icon and title)."""
    r = row_rect(rect)
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    if lk.shape != "mirino" or selected or hover:
        p.setBrush(lk.fill(selected, hover))
        p.drawPath(row_path(r, lk.shape, lk.cut))
    if group:
        glow_line(p, QPointF(r.right() - 16, r.top() + 2), QPointF(r.right() - 4, r.top() + 2), QColor(group), lk.glow)
    if selected and with_mark:
        mark(p, r, lk, vertical=True)
    p.restore()


# --- the address field --------------------------------------------------------
def paint_field(widget, lk, focus):
    """The frame of the address field: cut corners, an accent line when it has
    the keyboard. Called from the field's own paintEvent, before its text."""
    p = QPainter(widget)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    r = QRectF(widget.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
    path = cut_path(r, lk.cut * 0.8, "tl br")
    p.fillPath(path, lk.mix(lk.toolbar, lk.background, 0.75))
    if focus and lk.glow:
        for extra, alpha in ((4.0, 40), (2.0, 80)):
            halo = QColor(lk.accent)
            halo.setAlpha(alpha)
            p.setPen(QPen(halo, 1.0 + extra))
            p.drawPath(path)
    p.setPen(QPen(lk.accent if focus else lk.mix(lk.toolbar, lk.text, 0.22), 1.0))
    p.drawPath(path)
    p.end()


# --- style sheets for the parts that need no shape ------------------------------
def _rgba(colour, alpha):
    c = QColor(colour)
    return "rgba(%d,%d,%d,%d)" % (c.red(), c.green(), c.blue(), alpha)


def toolbar_qss(lk):
    """Toolbar buttons: square, with a corner that lights up under the mouse.
    (A style sheet on the toolbar also reaches the address field inside it, which
    would then be painted over our frame: it is told to stay clear.)"""
    lit = _rgba(lk.accent, 150 if lk.glow else 90)
    return (
        "QToolBar{background:%s;border:0;spacing:2px}"
        "QToolBar QLineEdit{background:transparent;border:0}"
        "QToolBar QToolButton{background:transparent;border:0;border-radius:0;padding:4px}"
        "QToolBar QToolButton:hover{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,"
        "stop:0 %s,stop:0.22 %s,stop:0.23 %s,stop:1 %s)}"
        "QToolBar QToolButton:pressed,QToolBar QToolButton:checked{background:%s}"
        "QToolBar QToolButton[popupMode=\"1\"]{padding-right:16px}"
        "QToolBar QToolButton::menu-button{border:0;width:14px}"
        "QToolBar QToolButton::menu-indicator{subcontrol-position:right center;right:2px}" % (
            lk.toolbar.name(), lit, lit, _rgba(lk.text, 22), _rgba(lk.text, 22), _rgba(lk.accent, 60)))


def menu_qss(lk):
    """Menus: square, a thin frame, luminous separators."""
    return (
        "QMenu{background:%s;color:%s;border:1px solid %s;padding:4px 0}"
        "QMenu::item{padding:5px 26px 5px 22px;border-left:2px solid transparent}"
        "QMenu::item:selected{background:%s;border-left:2px solid %s}"
        "QMenu::item:disabled{color:%s}"
        "QMenu::separator{height:1px;margin:4px 10px;background:%s}"
        "QMenu::icon{padding-left:6px}" % (
            lk.mix(lk.toolbar, lk.background, 0.35).name(), lk.text.name(), lk.mix(lk.toolbar, lk.text, 0.25).name(),
            _rgba(lk.accent, 46), lk.accent.name(), lk.mix(lk.text, lk.toolbar, 0.55).name(), _rgba(lk.accent, 110)))


# --- putting the look on a window, and taking it off ----------------------------
def apply(win):
    """Give a browser window the Cyber look, or remove it (any other theme)."""
    from PyQt6.QtWidgets import QMenu
    lk = look(win.app.config)
    old = getattr(win, "_cyber", None)
    if old is None and lk is None:
        return
    delegate = win.vtabs.itemDelegate()
    if old is not None:                       # take the previous look off (it may come back changed)
        for glide in old["glides"]:
            glide.stop()
            glide.setParent(None)
            glide.deleteLater()
        win.tabbar.setStyle(None)
        win.nav.setStyleSheet("")
        for menu in old["menus"]:
            try:
                menu.setStyleSheet("")
            except RuntimeError:              # the menu is gone
                pass
        win._cyber = None
    delegate.look = lk
    delegate.gliding = False
    win.urlbar.set_cyber(lk)
    if lk is None:
        win.vtabs.doItemsLayout()
        win.tabbar.update()
        return

    def group_colour(index):
        if 0 <= index < len(win.views):
            g = win.groups.get(win.views[index].group) if win.views[index].group else None
            return g["color"] if g else None
        return None

    style = TabStyle(lk, group_colour)
    win.tabbar.setStyle(style)
    delegate.group_of = group_colour

    def tab_rect():
        i = win.tabbar.currentIndex()
        return style.tab_rect(win.tabbar.tabRect(i), True) if i >= 0 else None

    def row():
        item = win.vtabs.currentItem()
        return row_rect(win.vtabs.visualItemRect(item)) if item is not None else None

    def h_state(gliding):
        style.gliding = gliding
        win.tabbar.update()

    def v_state(gliding):
        delegate.gliding = gliding
        win.vtabs.viewport().update()

    glide_h = MarkGlide(win.tabbar, lk, tab_rect, on_state=h_state)
    glide_v = MarkGlide(win.vtabs.viewport(), lk, row, vertical=True, on_state=v_state)
    win.tabbar.currentChanged.connect(glide_h.current_changed)
    win.vtabs.currentRowChanged.connect(glide_v.current_changed)
    glide_h.remember()
    glide_v.remember()
    win.nav.setStyleSheet(toolbar_qss(lk))
    qss = menu_qss(lk)
    menus = [m for m in win.findChildren(QMenu)]
    for menu in menus:
        menu.setStyleSheet(qss)
    win._cyber = {"style": style, "glides": (glide_h, glide_v), "menus": menus, "look": lk}
    win.vtabs.doItemsLayout()
    win.tabbar.update()


def style_menu(menu, config):
    """A menu about to open: the Cyber frame, or none."""
    lk = look(config)
    want = menu_qss(lk) if lk is not None else ""
    if menu.styleSheet() != want:
        menu.setStyleSheet(want)
