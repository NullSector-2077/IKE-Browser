"""The tab bars: the horizontal one, the vertical list, how a vertical row is
drawn and its close and audio buttons. The small touches they share (the
gliding mark of the current tab, titles that fade out) are in polish.py."""


from PyQt6.QtCore import QEasingCurve, QEvent, QRect, QRectF, QSize, Qt, QVariantAnimation, pyqtSignal
from PyQt6.QtGui import QIcon, QPainter
from PyQt6.QtWidgets import QListWidget, QStyle, QStyledItemDelegate, QTabBar

from . import polish
from .closebutton import CloseButtonStyle

AUDIO_ROLE = Qt.ItemDataRole.UserRole + 5       # "" | "on" | "muted"
TITLE_CHARS = 27         # a horizontal tab is about this many characters wide at most


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
        self.currentChanged.connect(self.mark.current_changed)

    def _mark_target(self):
        i = self.currentIndex()
        if i < 0:
            return None
        r = self.tabRect(i)
        inset = min(10, r.width() // 5)
        return QRectF(r.left() + inset, r.bottom() - 2.5, r.width() - 2 * inset, 2.5)

    def set_title(self, index, text):
        """The tab's title, held to TITLE_CHARS characters: a longer one is cut
        there, and its end fades out (polish.TabLabelStyle) instead of "…"."""
        cut = len(text) > TITLE_CHARS + 1
        self.setTabData(index, "cut" if cut else None)
        self.setTabText(index, text[:TITLE_CHARS] if cut else text)

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        self.mark.paint(p)
        p.end()


class VTabList(QListWidget):
    """The vertical tabs: a bar on the left edge of the current row that glides
    to the next one."""

    def __init__(self, parent, config=None):
        super().__init__(parent)
        self.config = config
        self.mark = polish.MarkGlide(self.viewport(), config, self._mark_target)
        self.currentRowChanged.connect(self.mark.current_changed)

    def _mark_target(self):
        item = self.currentItem()
        if item is None:
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

    def _hit(self, pos):
        """(row, area) under pos; area is "close", "audio" or "" (the title)."""
        index = self.view.indexAt(pos)
        if not index.isValid():
            return (-1, "")
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

    def sizeHint(self, option, index):
        # a narrow hint: rows are as wide as the panel, never as wide as the title
        s = super().sizeHint(option, index)
        return QSize(60, max(s.height(), 32))
