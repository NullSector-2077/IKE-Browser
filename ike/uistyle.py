"""Room around texts, menus that scroll, and switches (1.1.21).

The desktop's own style (Breeze on Plasma, Fusion elsewhere) draws every
widget; this thin layer over it only asks for a little more room where a
text would otherwise come close to the frame of its button, lets any menu
taller than the screen scroll instead of running past its edge, and draws a
small switch, like those of the "I.K.E. extensions" page, for a menu entry
that is turned on and off (a choice among several keeps its dot).
tests/test_text_fit.py checks the result in every language.

Every on / off option of the interface is a Switch (a check box drawn as a
sliding switch by SwitchStyle); the entries of a list that are turned on and
off are drawn the same way by SwitchDelegate (tests/test_switches.py).
"""

from PyQt6.QtCore import QEvent, QPointF, QRect, QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPalette, QPen
from PyQt6.QtWidgets import (
    QCheckBox,
    QMenu,
    QProxyStyle,
    QStyle,
    QStyledItemDelegate,
    QStyleFactory,
    QStyleOptionMenuItem,
    QStyleOptionViewItem,
    QWidget,
)

# the least room between a text and the frame of its button, on each side
TEXT_ROOM = 8

_style = None            # the style in use (kept here: Qt owns it, Python must not free it)
_switch_style = None     # the style of the switches (one for all of them, kept here)


# ----------------------------------------------------------------------
# switches
# ----------------------------------------------------------------------
def switch_size(fm, small=False):
    """(width, height) of a switch beside a text of the font fm: as tall as
    a line and a little more (small: in a list entry; menus: menu_switch_size)."""
    h = max(16, fm.height() + 2) if small else max(18, fm.height() + 4)
    return round(h * 1.9), h


def menu_switch_size(fm):
    """(width, height) of the small switch of a menu entry."""
    h = max(10, round(fm.height() * 0.62))
    return round(h * 1.8), h


def paint_switch(p, rect, on, palette, enabled=True, focus=False, rtl=False, selected=False):
    """A sliding switch in rect: the knob at the end (the right, or the left
    from right to left) when on. focus: a ring around it (the keyboard is on
    it); selected: on a highlighted menu entry (its colours turned round)."""
    R = QPalette.ColorRole
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    if not enabled:
        p.setOpacity(p.opacity() * 0.45)
    outer = QRectF(rect).adjusted(0.5, 0.5, -0.5, -0.5)
    r = outer.adjusted(1.5, 1.5, -1.5, -1.5) if rect.height() >= 14 else outer
    h = r.height()
    if selected:
        track = palette.color(R.HighlightedText) if on else palette.color(R.Mid)
        knob = palette.color(R.Highlight) if on else palette.color(R.Base)
        line = palette.color(R.HighlightedText)
    else:
        track = palette.color(R.Highlight) if on else palette.color(R.Mid)
        knob = palette.color(R.HighlightedText) if on else palette.color(R.Base)
        line = palette.color(R.Mid)
    if focus:
        p.setPen(QPen(palette.color(R.Highlight), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(outer, outer.height() / 2, outer.height() / 2)
    p.setPen(QPen(line, 1))
    p.setBrush(track)
    p.drawRoundedRect(r, h / 2, h / 2)
    end = on != rtl
    side = max(2.0, h - (4 if h >= 12 else 2.5))
    k = QRectF(0, 0, side, side)
    k.moveCenter(QPointF(r.right() - h / 2 if end else r.left() + h / 2, r.center().y()))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(knob)
    p.drawEllipse(k)
    p.restore()


class SwitchStyle(QProxyStyle):
    """The desktop's style for the switches: the box of a check box (or of a
    list entry, SwitchDelegate) drawn and measured as a sliding switch. Its
    text, its focus frame, right to left and the disabled look stay the
    style's own, so a Switch lays out its text as a check box does."""

    def pixelMetric(self, metric, opt=None, widget=None):
        PM = QStyle.PixelMetric
        if metric in (PM.PM_IndicatorWidth, PM.PM_IndicatorHeight):
            fm = widget.fontMetrics() if widget is not None else opt.fontMetrics if opt is not None else None
            if fm is not None:
                w, h = switch_size(fm, small=not isinstance(widget, QCheckBox))
                return w if metric == PM.PM_IndicatorWidth else h
        return super().pixelMetric(metric, opt, widget)

    def drawPrimitive(self, element, opt, p, widget=None):
        PE, S = QStyle.PrimitiveElement, QStyle.StateFlag
        if element in (PE.PE_IndicatorCheckBox, PE.PE_IndicatorItemViewItemCheck):
            paint_switch(p, opt.rect, bool(opt.state & S.State_On), opt.palette,
                         enabled=bool(opt.state & S.State_Enabled),
                         focus=element == PE.PE_IndicatorCheckBox and bool(opt.state & S.State_HasFocus),
                         rtl=opt.direction == Qt.LayoutDirection.RightToLeft)
            return
        if element == PE.PE_FrameFocusRect and isinstance(widget, QCheckBox) and not widget.text():
            return               # a switch without its own text: the ring around it shows the focus
        super().drawPrimitive(element, opt, p, widget)


def switch_style():
    """The one SwitchStyle of the application (made the first time)."""
    global _switch_style
    if _switch_style is None:
        _switch_style = SwitchStyle()
    return _switch_style


class Switch(QCheckBox):
    """An on / off switch: a check box drawn as a sliding switch, like those
    of the "I.K.E. extensions" page (1.1.20), with its text after it (1.1.21:
    every check box of the interface). Same signals and states as a check box."""

    def __init__(self, text="", parent=None):
        if isinstance(text, QWidget):
            text, parent = "", text
        super().__init__(text, parent)
        self.setStyle(switch_style())
        self.setCursor(Qt.CursorShape.PointingHandCursor)


class SwitchDelegate(QStyledItemDelegate):
    """The entries of a list that are turned on and off: a switch in place
    of the tick. A click on the switch or Space turns it, as on the tick."""

    def _option(self, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        return opt

    def paint(self, painter, option, index):
        opt = self._option(option, index)
        switch_style().drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)

    def sizeHint(self, option, index):
        opt = self._option(option, index)
        return switch_style().sizeFromContents(QStyle.ContentsType.CT_ItemViewItem, opt, QSize(), opt.widget)

    def switch_rect(self, view, index):
        """Where the switch of the entry at index is drawn, in view's viewport."""
        opt = QStyleOptionViewItem()
        view.initViewItemOption(opt)
        opt.rect = view.visualRect(index)
        opt = self._option(opt, index)
        return switch_style().subElementRect(QStyle.SubElement.SE_ItemViewItemCheckIndicator, opt, view)

    def editorEvent(self, event, model, option, index):
        mouse = (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease, QEvent.Type.MouseButtonDblClick)
        flags = model.flags(index)
        if (event.type() not in mouse or index.data(Qt.ItemDataRole.CheckStateRole) is None
                or not flags & Qt.ItemFlag.ItemIsUserCheckable or not flags & Qt.ItemFlag.ItemIsEnabled):
            return super().editorEvent(event, model, option, index)     # Space and Select: the tick's own way
        opt = self._option(option, index)
        box = switch_style().subElementRect(QStyle.SubElement.SE_ItemViewItemCheckIndicator, opt, opt.widget)
        if event.button() != Qt.MouseButton.LeftButton or not box.contains(event.position().toPoint()):
            return False
        if event.type() != QEvent.Type.MouseButtonRelease:
            return True          # the press and a double click: the release turns it
        state = Qt.CheckState(index.data(Qt.ItemDataRole.CheckStateRole))
        turned = Qt.CheckState.Unchecked if state == Qt.CheckState.Checked else Qt.CheckState.Checked
        return model.setData(index, turned, Qt.ItemDataRole.CheckStateRole)


# ----------------------------------------------------------------------
# menus: a small switch for an entry turned on and off
# ----------------------------------------------------------------------
def _toggle(action):
    """An entry turned on and off (not one choice of an exclusive group)."""
    g = action.actionGroup()
    return action.isCheckable() and not (g is not None and g.isExclusive())


def _menu_has_switches(menu):
    return any(_toggle(a) and a.isVisible() for a in menu.actions())


class IkeStyle(QProxyStyle):
    """The desktop's style, with room around button texts, scrolling menus
    and a small switch in the menu entries turned on and off."""

    def _switch_room(self, opt, menu):
        """The room added before the entries of menu for their switches (0:
        the switch goes in the column of the tick: Fusion, and no icons)."""
        if not isinstance(menu, QMenu) or not opt.menuHasCheckableItems or not _menu_has_switches(menu):
            return 0
        if opt.maxIconWidth <= 0 and self.baseStyle().name().lower() == "fusion":
            return 0
        return menu_switch_size(opt.fontMetrics)[0] + 6

    def drawControl(self, element, opt, p, widget=None):
        if element == QStyle.ControlElement.CE_MenuItem and isinstance(widget, QMenu) \
                and isinstance(opt, QStyleOptionMenuItem) and opt.menuHasCheckableItems:
            T = QStyleOptionMenuItem.MenuItemType
            if opt.menuItemType in (T.Normal, T.DefaultItem, T.SubMenu):
                room = self._switch_room(opt, widget)
                if room or opt.checkType == QStyleOptionMenuItem.CheckType.NonExclusive:
                    self._menu_item(opt, p, widget, room)
                    return
        super().drawControl(element, opt, p, widget)

    def _menu_item(self, opt, p, menu, room):
        CE, S = QStyle.ControlElement.CE_MenuItem, QStyle.StateFlag
        item = QStyleOptionMenuItem(opt)
        toggle = item.checkType == QStyleOptionMenuItem.CheckType.NonExclusive
        on = bool(item.checked)
        if toggle:                         # no tick: the switch below
            item.checkType = QStyleOptionMenuItem.CheckType.NotCheckable
            item.checked = False
        rtl = opt.direction == Qt.LayoutDirection.RightToLeft
        r = opt.rect
        sw, sh = menu_switch_size(opt.fontMetrics)
        selected = bool(opt.state & S.State_Selected) and bool(opt.state & S.State_Enabled)
        if room:
            if opt.state & S.State_Selected:
                # the highlight across the whole entry, then the entry beside the switch on it
                bg = QStyleOptionMenuItem(item)
                bg.text = ""
                bg.icon = QIcon()
                bg.menuItemType = QStyleOptionMenuItem.MenuItemType.Normal
                super().drawControl(CE, bg, p, menu)
                pal = QPalette(item.palette)
                pal.setBrush(QPalette.ColorRole.Highlight, QColor(0, 0, 0, 0))
                item.palette = pal
            item.rect = r.adjusted(0, 0, -room, 0) if rtl else r.adjusted(room, 0, 0, 0)
            super().drawControl(CE, item, p, menu)
            box = QRect(r.left() + 5, 0, sw, sh)
        else:
            super().drawControl(CE, item, p, menu)
            # Fusion's column of the tick: 4 px in, as wide as the widest icon, 21 px at least
            col = max(round(r.height() * 0.79), opt.maxIconWidth,
                      round(21 * (menu.logicalDpiX() / 96.0)))
            box = QRect(r.left() + 4 + max(0, (col - sw) // 2), 0, sw, sh)
        box.moveTop(r.top() + (r.height() - sh) // 2)
        if toggle:
            box = QStyle.visualRect(opt.direction, r, box)
            paint_switch(p, box, on, opt.palette, enabled=bool(opt.state & S.State_Enabled),
                         rtl=rtl, selected=selected)

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
        elif kind == CT.CT_MenuItem and isinstance(widget, QMenu) and isinstance(opt, QStyleOptionMenuItem) \
                and opt.menuItemType != QStyleOptionMenuItem.MenuItemType.Separator:
            room = self._switch_room(opt, widget)
            if room:
                s = QSize(s.width() + room, s.height())
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
