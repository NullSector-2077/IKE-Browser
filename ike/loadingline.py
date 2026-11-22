"""A refined, lightweight loading accent over the page content.

1.1.23: a flat bar on a faint track with rounded ends, as Breeze's progress
bar (no glow, no "bead"), drawn from two pictures made once per width and
colour; it shows only for a load that takes a while (SHOW_AFTER) and never
for I.K.E.'s own pages, which load at once. While it shows, every frame of
the page under it repaints it: a picture costs much less than shapes."""

from PyQt6.QtCore import QEvent, QPointF, QRect, QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QPainter, QPalette, QPixmap
from PyQt6.QtWidgets import QApplication, QWidget


class LoadingLine(QWidget):
    HEIGHT = 6
    INSET = 1
    SHOW_AFTER = 150             # ms: a page loaded sooner shows no line

    def __init__(self, anchor):
        """anchor: the widget whose top edge the line follows (same parent)."""
        super().__init__(anchor.parentWidget())
        self.anchor = anchor
        self.value = 0.0
        self.config = None           # set by the window: the line then advances smoothly (effects.py)
        self.quiet = None            # set by the window: True for a page that shows no line (ike:)
        self._anim = None
        self._loading = False
        self._pics = (None, None)    # (key, (track, bar))
        self.painted = 0             # (for the tests)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self._hide = QTimer(self)
        self._hide.setSingleShot(True)
        self._hide.setInterval(320)
        self._hide.timeout.connect(self.hide)
        self._due = QTimer(self)
        self._due.setSingleShot(True)
        self._due.setInterval(self.SHOW_AFTER)
        self._due.timeout.connect(self._appear)
        anchor.installEventFilter(self)
        self.hide()

    def _quiet(self):
        try:
            return bool(self.quiet and self.quiet())
        except RuntimeError:
            return False

    def set_state(self, loading, percent=0, since=None):
        """since: when the load began (time.monotonic()), when it is known; a
        load going on for a while (a tab shown again) shows the line at once."""
        self._loading = loading
        if loading:
            self._hide.stop()
            target = max(0.05, min(1.0, percent / 100.0))
            if self._quiet():
                self._due.stop()
                self.hide()
                return
            if not self.isVisible():
                # it appears only for a load that takes a while, where it has got to
                self.value = target
                if self._anim is not None:
                    self._anim.stop()
                import time
                if since is not None and (time.monotonic() - since) * 1000 >= self.SHOW_AFTER:
                    self._due.stop()
                    self._appear()
                elif not self._due.isActive():
                    self._due.start()
                return
            # forward only while it is in view
            self._go(target, smooth=target > self.value)
        else:
            self._due.stop()
            if self.isVisible():
                self._go(1.0, smooth=True)
                self._hide.start()
        self.update()

    def _appear(self):
        if not self._loading or self._quiet():
            return
        self._place()
        self.show()
        self.raise_()

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

    def hideEvent(self, event):
        self._pics = (None, None)    # nothing kept while it is not shown
        super().hideEvent(event)

    def _place(self):
        g = self.anchor.geometry()
        self.setGeometry(QRect(g.x(), g.y(), g.width(), self.HEIGHT))

    def eventFilter(self, obj, event):
        if obj is self.anchor and event.type() in (QEvent.Type.Resize, QEvent.Type.Move):
            self._place()
        return False

    def _pictures(self, accent):
        """The track and the whole bar, at the line's width, drawn once."""
        dpr = self.devicePixelRatioF() or 1.0
        width = self.width()
        key = (width, accent.rgba(), dpr)
        if self._pics[0] == key:
            return self._pics[1]
        from .polish import RADIUS
        out = []
        for alpha in (28, 255):
            pm = QPixmap(max(1, round(width * dpr)), max(1, round(self.HEIGHT * dpr)))
            pm.setDevicePixelRatio(dpr)
            pm.fill(Qt.GlobalColor.transparent)
            p = QPainter(pm)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            c = QColor(accent)
            c.setAlpha(alpha)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(c)
            r = QRectF(self.INSET, 1, max(0, width - 2 * self.INSET), self.HEIGHT - 2)
            radius = min(RADIUS / 2, r.height() / 2)
            p.drawRoundedRect(r, radius, radius)
            p.end()
            out.append(pm)
        self._pics = (key, tuple(out))
        return self._pics[1]

    def paintEvent(self, event):
        width = self.width()
        if width <= 0:
            return
        self.painted += 1
        accent = QColor(QApplication.palette().color(QPalette.ColorRole.Highlight))
        track, bar = self._pictures(accent)
        p = QPainter(self)
        # the faint track, then the bar up to where the page has got:
        # its start, and the rounded end of the whole bar moved to its end
        p.drawPixmap(0, 0, track)
        end = max(self.INSET + 4, min(width - self.INSET,
                                      round(self.INSET + (width - 2 * self.INSET) * self.value)))
        cap = min(6, end)
        dpr = bar.devicePixelRatio() or 1.0
        h = round(self.HEIGHT * dpr)
        # copied pixel for pixel (no scaling: the quick way)
        p.drawPixmap(QPointF(0, 0), bar, QRectF(0, 0, round((end - cap) * dpr), h))
        p.drawPixmap(QPointF(end - cap, 0), bar,
                     QRectF(bar.width() - round((cap + self.INSET) * dpr), 0, round(cap * dpr), h))
        p.end()
