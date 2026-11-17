"""Vertical tabs: how a row is drawn and its close and audio buttons."""


from PyQt6.QtCore import QEvent, QRect, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QStyle, QStyledItemDelegate

from .closebutton import CloseButtonStyle

AUDIO_ROLE = Qt.ItemDataRole.UserRole + 5       # "" | "on" | "muted"


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
        self.style_ = CloseButtonStyle()
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

    def paint(self, painter, option, index):
        from PyQt6.QtWidgets import QApplication, QStyleOptionViewItem
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        widget = opt.widget
        style = widget.style() if widget is not None else QApplication.style()
        audio = index.data(AUDIO_ROLE) or ""
        # the title stops before the button areas
        limit = self._right() - self.ZONE - (self.AUDIO if audio else 0)
        text_rect = style.subElementRect(QStyle.SubElement.SE_ItemViewItemText, opt, widget)
        room = max(0, min(text_rect.right(), limit) - text_rect.left() - 4)
        opt.text = opt.fontMetrics.elidedText(opt.text, Qt.TextElideMode.ElideRight, room)
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, widget)
        row = index.row()
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        if audio:
            from .icons import themed
            zone = self._audio_zone(option.rect)
            ic = themed("audio-volume-muted" if audio == "muted" else "audio-volume-high")
            mode = QIcon.Mode.Selected if selected else QIcon.Mode.Normal
            painter.save()
            if self._hover != (row, "audio"):
                painter.setOpacity(0.75)
            ic.paint(painter, QRect(zone.center().x() - 8, zone.center().y() - 8, 16, 16),
                     Qt.AlignmentFlag.AlignCenter, mode)
            painter.restore()
        hovered = self._hover == (row, "close")
        pressed = self._pressed == (row, "close")
        if hovered or pressed or selected or option.state & QStyle.StateFlag.State_MouseOver:
            self.style_.paint(painter, self._zone(option.rect), option.palette, hovered, pressed,
                              self._glide.value if hovered and self._glide.moving else None)

    def sizeHint(self, option, index):
        # a narrow hint: rows are as wide as the panel, never as wide as the title
        s = super().sizeHint(option, index)
        return QSize(60, max(s.height(), 32))
