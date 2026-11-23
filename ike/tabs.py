"""The tab bars: the horizontal one, the vertical list, how a vertical row is
drawn and its close and audio buttons. The small touches they share (the
gliding mark of the current tab, titles that fade out) are in polish.py."""

import functools

from PyQt6.QtCore import QEasingCurve, QEvent, QObject, QRect, QRectF, QSize, Qt, QVariantAnimation, pyqtSignal
from PyQt6.QtGui import QIcon, QPainter
from PyQt6.QtWidgets import QApplication, QListWidget, QStyle, QStyledItemDelegate, QTabBar

from . import polish
from .closebutton import CloseButtonStyle

AUDIO_ROLE = Qt.ItemDataRole.UserRole + 5       # "" | "on" | "muted"
TITLE_CHARS = 27         # a horizontal tab is about this many characters wide at most
TAB_MIME = "application/x-ike-tab"   # a tab being dragged out of its window (1.1.24)


class TabBar(QTabBar):
    """The horizontal tabs: the desktop's style, a line under the current tab
    that glides to the next one, long titles that fade out at the end."""

    def __init__(self, parent, config=None):
        super().__init__(parent)
        self.config = config
        self.label_style = polish.TabLabelStyle()
        self.setStyle(self.label_style)
        self.setElideMode(Qt.TextElideMode.ElideNone)   # the title is cut by fading (polish.py)
        self.mark = polish.MarkGlide(self, config, self._mark_target)
        self.mark.top = True             # Breeze's line along the top of the tab (1.1.24)
        self.own_mark = True             # False: the style's own fixed mark (the tests compare the two)
        self.currentChanged.connect(self.mark.current_changed)
        # 1.1.24: a tab dragged away from the bar (tear_off(index) opens it
        # in a new window); while the current tab is dragged its mark moves
        # with it (polish.TabLabelStyle draws it into the dragged picture)
        self.tear_off = None
        self._press = None               # (index, point) of a left press on a tab
        self.dragging = False
        self._glows = {}                 # close button: its glow (1.1.24)
        # 1.1.23: the hover comes and goes softly (Breeze's colour), and a new
        # tab's title fades in; each only while it moves, nothing at rest
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self._hover = -1
        self._levels = {}            # tab: animation of its hover colour coming or going
        self._enter = None           # (tab, animation) of a new tab coming in
        self.restoring = None        # callable: True while a session comes back (no fades then)

    # --- the hover and the new tab (1.1.23) ----------------------------------
    HOVER_IN = 110
    HOVER_OUT = 120

    @property
    def hovering(self):
        """A tab is under the mouse, or its hover colour is still fading: only
        then are the tabs drawn with I.K.E.'s own hover (polish.TabLabelStyle);
        otherwise the desktop's style draws them as before, at no extra cost."""
        return self._hover >= 0 or bool(self._levels)

    def hover_level(self, index):
        """How much of the hover colour tab index shows, 0-1."""
        anim = self._levels.get(index)
        if anim is not None and anim.state() == QVariantAnimation.State.Running:
            return float(anim.currentValue())
        return 1.0 if index == self._hover else 0.0

    def enter_level(self, index):
        """How far a new tab's title has come in, 0-1 (1: there)."""
        if self._enter is None or self._enter[0] != index:
            return 1.0
        anim = self._enter[1]
        return float(anim.currentValue()) if anim.state() == QVariantAnimation.State.Running else 1.0

    def _animate(self, store, index, start, end, ms, name):
        old = store.pop(index, None)
        if old is not None:
            old.stop()
        if not polish.moving(self.config, name) or not self.isVisible():
            self._repaint_tab(index)
            return None
        anim = QVariantAnimation(self)
        anim.setDuration(ms)
        anim.setStartValue(float(start))
        anim.setEndValue(float(end))
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.valueChanged.connect(lambda _v, i=index: self._repaint_tab(i))

        def done(i=index, a=anim):
            if store.get(i) is a:
                del store[i]
            if self._enter is not None and self._enter[1] is a:
                self._enter = None
            a.deleteLater()
            self._repaint_tab(i)
        anim.finished.connect(done)
        store[index] = anim
        anim.start()
        return anim

    def _repaint_tab(self, index):
        if 0 <= index < self.count():
            self.update(self.tabRect(index))

    def _hover_to(self, index):
        if index == self._hover:
            return
        old, self._hover = self._hover, index
        if old >= 0:
            self._animate(self._levels, old, self._level_now(old, 1.0), 0.0, self.HOVER_OUT, "tab_hover")
        if index >= 0:
            self._animate(self._levels, index, self._level_now(index, 0.0), 1.0, self.HOVER_IN, "tab_hover")

    def _level_now(self, index, default):
        anim = self._levels.get(index)
        if anim is not None and anim.state() == QVariantAnimation.State.Running:
            return float(anim.currentValue())
        return default

    def _forget(self):
        """Tabs added, removed or moved: no fade goes on with an old place."""
        for anim in self._levels.values():
            anim.stop()
        self._levels.clear()
        self._hover = -1
        if self._enter is not None:
            self._enter[1].stop()
            self._enter = None

    def event(self, event):
        t = event.type()
        if t in (QEvent.Type.HoverMove, QEvent.Type.HoverEnter):
            self._hover_to(self.tabAt(event.position().toPoint()))
        elif t == QEvent.Type.HoverLeave:
            self._hover_to(-1)
        return super().event(event)

    def tabInserted(self, index):
        super().tabInserted(index)
        self._forget()
        self._glow(index)
        restoring = self.restoring is not None and self.restoring()
        if self.count() > 1 and not restoring:
            anim = self._animate({}, index, 0.0, 1.0, polish.ENTER_MS, "tab_enter")
            if anim is not None:
                self._enter = (index, anim)

    def tabRemoved(self, index):
        super().tabRemoved(index)
        self._forget()

    def tabLayoutChange(self):
        super().tabLayoutChange()
        if self._enter is not None:          # the tab's place moved while it came in
            self._repaint_tab(self._enter[0])

    def _mark_target(self):
        """Breeze's mark of the current tab (1.1.24, the owner's choice): its
        accent line along the top edge, the tab's whole width, following the
        rounded top corners (polish.top_line_path); it glides from tab to
        tab. The line under the tab (1.1.3-1.1.23) is gone: with Breeze's own
        fixed line there were two."""
        i = self.currentIndex()
        if i < 0 or not self.own_mark or self.dragging:
            return None
        return polish.top_line_rect(self.tabRect(i))

    def set_title(self, index, text):
        """The tab's title, held to TITLE_CHARS characters: a longer one is cut
        there, and its end fades out (polish.TabLabelStyle) instead of "…"."""
        cut = len(text) > TITLE_CHARS + 1
        self.setTabData(index, "cut" if cut else None)
        self.setTabText(index, text[:TITLE_CHARS] if cut else text)

    # --- the close button's red glow (1.1.24) ---------------------------------
    GLOW_MS = 120

    def _glow(self, index):
        """The close button of tab index glows in Breeze's red under the
        mouse (polish.TabLabelStyle draws it), coming in over GLOW_MS."""
        from PyQt6.QtWidgets import QTabBar
        for side in (QTabBar.ButtonPosition.RightSide, QTabBar.ButtonPosition.LeftSide):
            b = self.tabButton(index, side)
            if b is None or b in self._glows:
                continue
            # kept here as well as by the button: a Qt child held only by Qt
            # loses its Python side (its event filter) to Python's collector
            g = self._glows[b] = _CloseGlow(b, self.config)
            b.destroyed.connect(functools.partial(self._glows.pop, b, None))
            b.installEventFilter(g)
            # the button is drawn by the tab bar's style (a widget's own style
            # does not reach its children by itself)
            b.setStyle(self.label_style)

    # --- dragging a tab, and tearing it off (1.1.24) ---------------------------
    TEAR_PX = 40             # how far above or below the bar the mouse goes before the tab comes off

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            i = self.tabAt(event.position().toPoint())
            self._press = (i, event.position().toPoint()) if i >= 0 else None
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        press = self._press
        if press is not None and event.buttons() & Qt.MouseButton.LeftButton:
            pos = event.position().toPoint()
            if not self.dragging and (pos - press[1]).manhattanLength() >= QApplication.startDragDistance():
                self.dragging = True
                self.update()
            if self.away(pos) and self.tear_off is not None and polish.part("tab_tear_off"):
                self._press = None
                self._end_drag(press[1])
                self.tear_off(press[0])
                return
        super().mouseMoveEvent(event)

    def away(self, pos):
        """Is pos (in the bar) far enough above or below it for the tab to come off?"""
        return pos.y() < -self.TEAR_PX or pos.y() > self.height() + self.TEAR_PX

    def _end_drag(self, at):
        """The bar's own move of the tab ends where it began (a release there)."""
        from PyQt6.QtCore import QPointF
        from PyQt6.QtGui import QMouseEvent
        p = QPointF(at)
        super().mouseReleaseEvent(QMouseEvent(QEvent.Type.MouseButtonRelease, p, self.mapToGlobal(p),
                                              Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton,
                                              Qt.KeyboardModifier.NoModifier))
        self._dropped()

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            self._press = None
            self._dropped()

    def _dropped(self):
        if self.dragging:
            self.dragging = False
            self.update()

    # a torn-off tab dropped back on a tab bar: on its own, it stays; on
    # another window's, it moves there (take_tab(key))
    take_tab = None

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(TAB_MIME):
            event.setDropAction(Qt.DropAction.MoveAction)
            event.accept()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(TAB_MIME):
            event.setDropAction(Qt.DropAction.MoveAction)
            event.accept()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasFormat(TAB_MIME):
            event.setDropAction(Qt.DropAction.MoveAction)
            event.accept()
            if self.take_tab is not None:
                self.take_tab(bytes(event.mimeData().data(TAB_MIME)).decode("ascii", "replace"))
            return
        super().dropEvent(event)

    def paintEvent(self, event):
        # the part being painted: the tabs outside it are not drawn again
        # (polish.TabLabelStyle; 1.1.23: the loading mark of one tab redrew
        # every tab, eleven times a second)
        area = event.rect()
        # a whole repaint draws every tab: nothing to look up for each
        self.painting = None if area.contains(self.rect()) else area
        try:
            super().paintEvent(event)
        finally:
            self.painting = None
        p = QPainter(self)
        self.mark.paint(p)
        p.end()


class _CloseGlow(QObject):
    """The glow of one close button: a child of the button, so it lives and
    dies with it; the level is kept as the button's property "ike_glow"."""

    def __init__(self, button, config):
        super().__init__(button)
        self.setObjectName("ike_close_glow")
        self.button = button
        from .effects import Glide
        self.glide = Glide(self, config, self._level, ms=TabBar.GLOW_MS)

    def _level(self):
        self.button.setProperty("ike_glow", self.glide.value)
        self.button.update()

    def eventFilter(self, obj, event):
        t = event.type()
        if t == QEvent.Type.Enter and obj.isEnabled():
            self.glide.to(1)
        elif t in (QEvent.Type.Leave, QEvent.Type.Hide):
            self.glide.to(0)
        return False


class VTabList(QListWidget):
    """The vertical tabs: a bar on the left edge of the current row that glides
    to the next one. 1.1.24: while a row is dragged the others slide aside
    to open its place (Qt's own list shows only a line where it would go),
    and a row dropped outside the list opens in a new window (tear_off)."""

    SLIDE_MS = 160

    def __init__(self, parent, config=None):
        super().__init__(parent)
        self.config = config
        self.mark = polish.MarkGlide(self.viewport(), config, self._mark_target)
        self.currentRowChanged.connect(self.mark.current_changed)
        self.tear_off = None             # callable(row): the row dropped outside the list
        self.picture = None              # callable(row) -> QPixmap: what follows the mouse
        self.key = None                  # callable(row) -> str: the tab, for another window's tab bar
        self.drag_row = -1               # the row being dragged (-1: none)
        self.gap = -1                    # where it would go: an insertion row
        self._offsets = {}               # row: how far it is moved now (px)
        self._from, self._to = {}, {}
        self._slide = None

    def _mark_target(self):
        item = self.currentItem()
        if item is None or self.drag_row >= 0:
            return None
        r = self.visualItemRect(item)
        if r.isEmpty():
            return None
        inset = min(8, r.height() // 4)
        return QRectF(r.left() + 2, r.top() + inset, 3, r.height() - 2 * inset)

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self.viewport())
        self.mark.paint(p)
        p.end()

    # --- rows sliding aside while one is dragged (1.1.24) ---------------------
    def offset(self, row):
        """How far row is drawn from its place now (px; the delegate moves it)."""
        return self._offsets.get(row, 0.0)

    def sliding(self):
        return self.drag_row >= 0 and polish.part("tab_slide")

    def startDrag(self, actions):
        row = self.currentRow()
        indexes = self.selectedIndexes()
        if row < 0 or not indexes:
            return
        from PyQt6.QtCore import QPoint
        from PyQt6.QtGui import QDrag
        drag = QDrag(self)
        mime = self.model().mimeData(indexes)
        if self.key is not None:
            mime.setData(TAB_MIME, self.key(row).encode("ascii"))
        drag.setMimeData(mime)
        pm = self.picture(row) if self.picture is not None else None
        if pm is None or pm.isNull():
            rect = self.visualItemRect(self.item(row))
            pm = self.viewport().grab(rect)
        drag.setPixmap(pm)
        dpr = pm.devicePixelRatio() or 1.0
        drag.setHotSpot(QPoint(round(pm.width() / dpr / 2), min(12, round(pm.height() / dpr / 2))))
        self.drag_row, self.gap = row, row
        shown = self.showDropIndicator()
        if self.sliding():
            self.setDropIndicatorShown(False)
        self.viewport().update()
        try:
            result = run_drag(drag, Qt.DropAction.MoveAction)
        finally:
            self.setDropIndicatorShown(shown)
            self._end_slide()
        if result == Qt.DropAction.IgnoreAction and self.tear_off is not None and polish.part("tab_tear_off") \
                and not cancelled():
            self.tear_off(row)

    def _end_slide(self):
        if self._slide is not None:
            self._slide.stop()
        self.drag_row, self.gap = -1, -1
        self._offsets, self._from, self._to = {}, {}, {}
        self.viewport().update()

    def _gap_at(self, y):
        """The insertion row for the mouse at y: the visible rows as they
        stand without the dragged one, the gap where the mouse is."""
        rows = [r for r in range(self.count()) if not self.item(r).isHidden()]
        for r in rows:
            rect = self.visualItemRect(self.item(r))
            if y < rect.center().y():
                return r
        return rows[-1] + 1 if rows else 0

    def _targets(self, gap):
        h = self.visualItemRect(self.item(self.drag_row)).height()
        out = {}
        for r in range(self.count()):
            if r == self.drag_row or self.item(r).isHidden():
                continue
            if self.drag_row < r < gap:
                out[r] = -h
            elif gap <= r < self.drag_row:
                out[r] = h
        return out

    def slide_to(self, gap):
        """Open the dragged row's place at insertion row gap: the rows
        between its old place and the new one glide up or down."""
        if self.drag_row < 0 or gap == self.gap:
            return
        self.gap = gap
        target = self._targets(gap)
        if not polish.moving(self.config, "tab_slide") or not self.isVisible():
            self._offsets = dict(target)
            self.viewport().update()
            return
        self._from, self._to = dict(self._offsets), target
        if self._slide is None:
            self._slide = QVariantAnimation(self)
            self._slide.setStartValue(0.0)
            self._slide.setEndValue(1.0)
            self._slide.setEasingCurve(QEasingCurve.Type.OutCubic)
            self._slide.valueChanged.connect(self._slide_step)
        self._slide.stop()
        self._slide.setDuration(self.SLIDE_MS)
        self._slide.start()

    def _slide_step(self, v):
        t = float(v)
        rows = set(self._from) | set(self._to)
        self._offsets = {r: self._from.get(r, 0.0) + (self._to.get(r, 0.0) - self._from.get(r, 0.0)) * t
                         for r in rows}
        self.viewport().update()

    def dragMoveEvent(self, event):
        super().dragMoveEvent(event)
        if self.drag_row >= 0 and event.source() is self:
            self.slide_to(self._gap_at(event.position().toPoint().y()))
            if self.sliding():
                event.accept()

    def dropEvent(self, event):
        if self.drag_row >= 0 and event.source() is self and self.sliding():
            self.drop_at(event.position().toPoint().y())
            event.setDropAction(Qt.DropAction.CopyAction)   # nothing for the drag to remove
            event.accept()
            return
        super().dropEvent(event)

    def drop_at(self, y):
        """The dragged row goes where its place was opened, as the user saw it."""
        from PyQt6.QtCore import QModelIndex
        gap = self._gap_at(y)
        row = self.drag_row
        self._end_slide()
        if row >= 0 and gap not in (row, row + 1):
            self.model().moveRows(QModelIndex(), row, 1, QModelIndex(), gap)


# The drag of a tab (1.1.24): QDrag.exec, a function the tests replace (a
# drag waits for the mouse, which an offscreen test has none of)
_cancel = {"esc": False}


def run_drag(drag, actions):
    from PyQt6.QtCore import QObject as _Q

    class _Esc(_Q):
        def eventFilter(self, _obj, event):
            if event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
                _cancel["esc"] = True
            return False
    _cancel["esc"] = False
    watch = _Esc()
    app = QApplication.instance()
    app.installEventFilter(watch)
    try:
        return drag.exec(actions)
    finally:
        app.removeEventFilter(watch)


def cancelled():
    """Was the last drag given up with Esc? (then the tab stays)"""
    return _cancel["esc"]


class VTabDelegate(QStyledItemDelegate):
    """Vertical tab row: title on the left; on the right, in areas of their own,
    the speaker (only while the tab makes sound) and the close button.

    Both areas are fixed to the right edge of the panel, whatever its width and
    however long the title is, and span the whole height of the row. A press
    there never selects or drags the tab.
    """

    close_requested = pyqtSignal(int)
    mute_requested = pyqtSignal(int)
    ZONE = 32            # width of the close area
    AUDIO = 26           # width of the speaker area

    def __init__(self, view, config=None):
        super().__init__(view)
        self.view = view
        self.config = config
        self.style_ = CloseButtonStyle()
        self.audio_phase = None      # where the pulse of the speaker is (polish.pulse), None = still
        self._row_hover = -1         # the row under the mouse
        self._levels = {}            # row: animation of its hover colour coming or going
        self._enter = {}             # row: animation of a new row coming in
        view.model().rowsInserted.connect(self._rows_inserted)
        from .effects import Glide
        self._glide = Glide(self, config, lambda: self._repaint(self._hover[0]))
        self._hover = (-1, "")       # (row, "close" | "audio")
        self._pressed = (-1, "")
        view.viewport().setMouseTracking(True)
        view.viewport().installEventFilter(self)

    def _right(self):
        return self.view.viewport().width()

    def _zone(self, rect):
        return QRect(self._right() - self.ZONE, rect.top(), self.ZONE, rect.height())

    def _audio_zone(self, rect):
        return QRect(self._right() - self.ZONE - self.AUDIO, rect.top(), self.AUDIO, rect.height())

    def icons_only(self):
        """Only the tabs' icons in a narrow panel (1.1.16): no title, no buttons;
        the title shows in a tooltip, closing is by the middle button or the menu."""
        return bool(self.config is not None and self.config["vtabs_icons_only"])

    def _hit(self, pos):
        """(row, area) under pos; area is "close", "audio" or "" (the title)."""
        index = self.view.indexAt(pos)
        if not index.isValid():
            return (-1, "")
        if self.icons_only():
            return (index.row(), "")
        rect = self.view.visualRect(index)
        if self._zone(rect).contains(pos):
            return (index.row(), "close")
        if index.data(AUDIO_ROLE) and self._audio_zone(rect).contains(pos):
            return (index.row(), "audio")
        return (index.row(), "")

    def _repaint(self, *rows):
        for row in rows:
            if row >= 0:
                item = self.view.item(row)
                if item is not None:
                    self.view.viewport().update(self.view.visualItemRect(item))

    def eventFilter(self, obj, event):
        t = event.type()
        if t == QEvent.Type.MouseMove:
            self._hover_row(self.view.indexAt(event.position().toPoint()).row())
            hit = self._hit(event.position().toPoint())
            hit = hit if hit[1] else (-1, "")
            if hit != self._hover:
                old, self._hover = self._hover, hit
                self._repaint(old[0], hit[0])
                if hit[1] == "close":           # the red comes in gently, and leaves at once
                    self._glide.jump(0)
                    self._glide.to(1)
            return self._pressed[0] >= 0       # no drag while a button is held
        if t in (QEvent.Type.Leave, QEvent.Type.HoverLeave):
            self._hover_row(-1)
            if self._hover[0] >= 0:
                old, self._hover = self._hover, (-1, "")
                self._repaint(old[0])
            return False
        if t in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonDblClick):
            if event.button() != Qt.MouseButton.LeftButton:
                return False
            hit = self._hit(event.position().toPoint())
            if not hit[1]:
                return False
            self._pressed = hit
            self._repaint(hit[0])
            return True
        if t == QEvent.Type.MouseButtonRelease and self._pressed[0] >= 0:
            if event.button() != Qt.MouseButton.LeftButton:
                return False
            hit, self._pressed = self._pressed, (-1, "")
            self._repaint(hit[0])
            if self._hit(event.position().toPoint()) == hit:
                if hit[1] == "close":
                    self._hover = (-1, "")
                    self.close_requested.emit(hit[0])
                else:
                    self.mute_requested.emit(hit[0])
            return True
        return False

    # --- the soft touches of a row (polish.py) ---------------------------
    def _animate(self, store, row, start, end, ms, name):
        """Run store[row] from start to end; the row is repainted at each step."""
        old = store.pop(row, None)
        if old is not None:
            old.stop()
        if not polish.moving(self.config, name) or not self.view.viewport().isVisible():
            self._repaint(row)
            return
        anim = QVariantAnimation(self)
        anim.setDuration(ms)
        anim.setStartValue(float(start))
        anim.setEndValue(float(end))
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.valueChanged.connect(lambda _v, r=row: self._repaint(r))

        def done(r=row, a=anim):
            if store.get(r) is a:
                del store[r]
            self._repaint(r)
        anim.finished.connect(done)
        store[row] = anim
        anim.start()

    @staticmethod
    def _value(store, row):
        anim = store.get(row)
        if anim is None or anim.state() != QVariantAnimation.State.Running:
            return None
        return float(anim.currentValue())

    def _hover_row(self, row):
        if row == self._row_hover:
            return
        old, self._row_hover = self._row_hover, row
        if old >= 0:
            now = self._value(self._levels, old)
            self._animate(self._levels, old, 1.0 if now is None else now, 0.0, 160, "row_hover")
        if row >= 0:
            now = self._value(self._levels, row)
            self._animate(self._levels, row, 0.0 if now is None else now, 1.0, 110, "row_hover")

    def _rows_inserted(self, _parent, first, last):
        if first == last:                # one new tab; a whole session coming back is shown at once
            self._animate(self._enter, first, 0.0, 1.0, polish.ENTER_MS, "row_enter")

    def paint(self, painter, option, index):
        from PyQt6.QtWidgets import QApplication, QStyleOptionViewItem
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        widget = opt.widget
        style = widget.style() if widget is not None else QApplication.style()
        audio = index.data(AUDIO_ROLE) or ""
        row = index.row()
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        enter = self._value(self._enter, row)
        painter.save()
        if getattr(self.view, "drag_row", -1) >= 0 and polish.part("tab_slide"):
            if row == self.view.drag_row:           # its place is the gap the others open
                painter.restore()
                return
            painter.translate(0, round(self.view.offset(row)))
        if enter is not None:            # a new row: comes in from a little to the left, fading in
            painter.setOpacity(painter.opacity() * enter)
            painter.translate(round((enter - 1) * 12), 0)
        level = self._value(self._levels, row)
        if level is not None and not selected:
            # the hover colour of the desktop's style, at the strength the fade has reached
            hov = QStyleOptionViewItem(opt)
            hov.state |= QStyle.StateFlag.State_MouseOver
            painter.save()
            painter.setOpacity(painter.opacity() * level)
            style.drawPrimitive(QStyle.PrimitiveElement.PE_PanelItemViewItem, hov, painter, widget)
            painter.restore()
            opt.state &= ~QStyle.StateFlag.State_MouseOver
        if self.icons_only():
            self._paint_icon_only(painter, opt, style, widget, audio, selected)
            painter.restore()
            return
        # the title stops before the button areas; a long one fades out there
        limit = self._right() - self.ZONE - (self.AUDIO if audio else 0)
        text_rect = style.subElementRect(QStyle.SubElement.SE_ItemViewItemText, opt, widget)
        room = max(0, min(text_rect.right(), limit) - text_rect.left() - 4)
        text = opt.text
        own_text = polish.part("title_fade") and opt.fontMetrics.horizontalAdvance(text) > room
        opt.text = "" if own_text else opt.fontMetrics.elidedText(text, Qt.TextElideMode.ElideRight, room)
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, widget)
        if own_text:
            from PyQt6.QtGui import QPalette
            group = QPalette.ColorGroup.Normal if opt.state & QStyle.StateFlag.State_Active \
                else QPalette.ColorGroup.Inactive
            if not opt.state & QStyle.StateFlag.State_Enabled:
                group = QPalette.ColorGroup.Disabled
            role = QPalette.ColorRole.HighlightedText if selected else QPalette.ColorRole.Text
            polish.draw_faded_text(painter, QRect(text_rect.left(), text_rect.top(), room, text_rect.height()),
                                   text, opt.palette.color(group, role), opt.font, opt.displayAlignment)
        if audio:
            from .icons import themed
            zone = self._audio_zone(option.rect)
            ic = themed("audio-volume-muted" if audio == "muted" else "audio-volume-high")
            mode = QIcon.Mode.Selected if selected else QIcon.Mode.Normal
            painter.save()
            if self._hover == (row, "audio"):
                pass
            elif audio == "on" and self.audio_phase is not None and polish.part("audio_pulse"):
                painter.setOpacity(painter.opacity() * polish.pulse(self.audio_phase))
            else:
                painter.setOpacity(painter.opacity() * 0.75)
            ic.paint(painter, QRect(zone.center().x() - 8, zone.center().y() - 8, 16, 16),
                     Qt.AlignmentFlag.AlignCenter, mode)
            painter.restore()
        hovered = self._hover == (row, "close")
        pressed = self._pressed == (row, "close")
        if hovered or pressed or selected or option.state & QStyle.StateFlag.State_MouseOver:
            self.style_.paint(painter, self._zone(option.rect), option.palette, hovered, pressed,
                              self._glide.value if hovered and self._glide.moving else None)
        painter.restore()

    def _paint_icon_only(self, painter, opt, style, widget, audio, selected):
        """The row's background and selection as the desktop draws them, the icon
        in the middle, a small speaker in the corner while the tab makes sound."""
        icon_ = QIcon(opt.icon)
        opt.text = ""
        opt.icon = QIcon()
        from PyQt6.QtWidgets import QStyleOptionViewItem
        opt.features &= ~QStyleOptionViewItem.ViewItemFeature.HasDecoration
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, widget)
        r = opt.rect
        side = 20
        mode = QIcon.Mode.Selected if selected else QIcon.Mode.Normal
        icon_.paint(painter, QRect(r.center().x() - side // 2 + 1, r.center().y() - side // 2, side, side),
                    Qt.AlignmentFlag.AlignCenter, mode)
        if audio:
            from .icons import themed
            ic = themed("audio-volume-muted" if audio == "muted" else "audio-volume-high")
            ic.paint(painter, QRect(r.right() - 13, r.top() + 2, 11, 11), Qt.AlignmentFlag.AlignCenter, mode)

    def helpEvent(self, event, view, option, index):
        if self.icons_only() and event.type() == QEvent.Type.ToolTip and index.isValid():
            from PyQt6.QtWidgets import QToolTip
            QToolTip.showText(event.globalPos(), index.data(Qt.ItemDataRole.DisplayRole) or "", view)
            return True
        return super().helpEvent(event, view, option, index)

    def sizeHint(self, option, index):
        # a narrow hint: rows are as wide as the panel, never as wide as the title
        s = super().sizeHint(option, index)
        return QSize(60, max(s.height(), 32))
