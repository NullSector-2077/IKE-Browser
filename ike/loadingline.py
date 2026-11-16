"""A refined, lightweight loading accent over the page content."""

from PyQt6.QtCore import QEvent, QRect, Qt, QTimer
from PyQt6.QtGui import QColor, QPainter, QPalette
from PyQt6.QtWidgets import QApplication, QWidget


class LoadingLine(QWidget):
    HEIGHT = 6
    INSET = 1

    def __init__(self, anchor):
        """anchor: the widget whose top edge the line follows (same parent)."""
        super().__init__(anchor.parentWidget())
        self.anchor = anchor
        self.value = 0.0
        self.config = None           # set by the window: the line then advances smoothly (effects.py)
        self._anim = None
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self._hide = QTimer(self)
        self._hide.setSingleShot(True)
        self._hide.setInterval(320)
        self._hide.timeout.connect(self.hide)
        anchor.installEventFilter(self)
        self.hide()

    def set_state(self, loading, percent=0):
        if loading:
            self._hide.stop()
            target = max(0.05, min(1.0, percent / 100.0))
            # forward only while it is in view; a new page starts from the beginning
            self._go(target, smooth=self.isVisible() and target > self.value)
            self._place()
            self.show()
            self.raise_()
        elif self.isVisible():
            self._go(1.0, smooth=True)
            self._hide.start()
        self.update()

    def _go(self, target, smooth):
        from . import effects
        if self._anim is not None:
            self._anim.stop()
        if not smooth or self.config is None or not effects.on(self.config):
            self.value = target
            return
        if self._anim is None:
            from PyQt6.QtCore import QEasingCurve, QVariantAnimation
            self._anim = QVariantAnimation(self)
            self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            self._anim.setDuration(effects.LINE_MS)
            self._anim.valueChanged.connect(self._advance)
        self._anim.setStartValue(float(self.value))
        self._anim.setEndValue(float(target))
        self._anim.start()

    def _advance(self, value):
        self.value = float(value)
        self.update()

    def _place(self):
        g = self.anchor.geometry()
        self.setGeometry(QRect(g.x(), g.y(), g.width(), self.HEIGHT))

    def eventFilter(self, obj, event):
        if obj is self.anchor and event.type() in (QEvent.Type.Resize, QEvent.Type.Move):
            self._place()
        return False

    def paintEvent(self, event):
        width = self.width()
        if width <= 0:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        accent = QApplication.palette().color(QPalette.ColorRole.Highlight)
        accent = QColor(accent)
        end = max(self.INSET + 2, min(width - self.INSET - 2,
                                      self.INSET + (width - 2 * self.INSET) * self.value))
        # A subtle track keeps the indicator legible without drawing attention.
        track = QColor(accent)
        track.setAlpha(28)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(self.INSET, 1, max(0, width - 2 * self.INSET),
                          self.HEIGHT - 2, 2, 2)
        p.setBrush(accent)
        progress_width = max(0, int(round(end - self.INSET)))
        p.drawRoundedRect(self.INSET, 1, progress_width,
                          self.HEIGHT - 2, 2, 2)
        # The small leading bead gives the progress edge a polished finish.
        glow = QColor(accent)
        glow.setAlpha(75)
        p.setBrush(glow)
        p.drawEllipse(int(end - 3), 0, 6, 6)
        p.setBrush(QColor(accent))
        p.drawEllipse(int(end - 1.5), 1, 3, 3)
        p.end()
