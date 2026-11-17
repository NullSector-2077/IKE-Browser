"""The Downloads toolbar icon with a progress ring around it.

While files are downloading, a ring in the accent colour fills clockwise from
the top as the bytes arrive (a short turning arc when the size is unknown).
When everything is done the ring is green, with a tick in place of the arrow
(it comes in with a small pop, polish.py), until the downloads list is opened.
The icon is drawn when it is shown, so it follows theme changes at once.
"""

import time

from PyQt6.QtCore import QPointF, QRect, QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QGuiApplication, QIcon, QIconEngine, QPainter, QPalette, QPen, QPixmap, QPolygonF

DONE_COLOUR = "#27ae60"          # Breeze "positive" green


class RingIconEngine(QIconEngine):
    def __init__(self, base, fraction=None, done=False, phase=0.0, pop=None, bob=None):
        super().__init__()
        self.base = base
        self.bob = bob                      # 0..1: where the arrow is in its gentle move; None: still
        self.pop = pop                      # 0..1 while the tick comes in; None: in place
        self.fraction = fraction            # 0..1, or None when the size is unknown
        self.done = done
        self.phase = phase                  # 0..1, start of the turning arc

    def clone(self):
        return RingIconEngine(self.base, self.fraction, self.done, self.phase, self.pop, self.bob)

    def paint(self, painter, rect, mode, state):
        side = min(rect.width(), rect.height())
        if side <= 0:
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen_w = max(1.5, side / 11.0)
        ring = QRectF(rect.x() + (rect.width() - side) / 2 + pen_w / 2,
                      rect.y() + (rect.height() - side) / 2 + pen_w / 2,
                      side - pen_w, side - pen_w)
        # the arrow, a little smaller, inside the ring
        inner = int(side * 0.62)
        c = QPointF(rect.center())
        from . import polish
        tick = self.done and polish.part("download_pop")
        pop = 1.0 if self.pop is None else self.pop
        if not tick or pop < 1.0:
            painter.save()
            if tick:
                painter.setOpacity(painter.opacity() * max(0.0, 1.0 - pop))
            if self.bob is not None and not self.done:
                import math
                painter.translate(0, side * 0.07 * math.sin(2 * math.pi * self.bob))
            self.base.paint(painter, QRect(int(c.x() - inner / 2 + 0.5), int(c.y() - inner / 2 + 0.5),
                                           inner, inner), Qt.AlignmentFlag.AlignCenter, mode, state)
            painter.restore()
        if tick and pop > 0:
            # the tick, a little smaller than the ring, grown by the pop
            k = inner * 0.5 * max(0.0, pop)
            pen = QPen(QColor(DONE_COLOUR), max(1.6, side / 9.0))
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.save()
            painter.setOpacity(painter.opacity() * min(1.0, max(0.0, pop)))
            painter.setPen(pen)
            painter.drawPolyline(QPolygonF([QPointF(c.x() - k * 0.85, c.y() + k * 0.05),
                                            QPointF(c.x() - k * 0.25, c.y() + k * 0.6),
                                            QPointF(c.x() + k * 0.9, c.y() - k * 0.6)]))
            painter.restore()
        pal = QGuiApplication.palette()
        if self.done:
            pen = QPen(QColor(DONE_COLOUR), pen_w)
            painter.setPen(pen)
            painter.drawEllipse(ring)
        else:
            track = QColor(pal.color(QPalette.ColorRole.WindowText))
            track.setAlphaF(0.22)
            painter.setPen(QPen(track, pen_w))
            painter.drawEllipse(ring)
            pen = QPen(pal.color(QPalette.ColorRole.Highlight), pen_w)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            if self.fraction is None:
                start, span = 90 - 360 * self.phase, -90       # turning quarter
            else:
                start, span = 90, -360 * max(0.02, min(1.0, self.fraction))
            painter.drawArc(ring, int(start * 16), int(span * 16))
        painter.restore()

    def pixmap(self, size, mode, state):
        pm = QPixmap(size)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        self.paint(p, QRect(0, 0, size.width(), size.height()), mode, state)
        p.end()
        return pm

    def actualSize(self, size, mode, state):
        return QSize(size)


def ring_icon(base, fraction=None, done=False, pop=None, bob=None):
    """base with a progress ring; fraction None = size unknown; pop 0..1 while
    the tick of a finished download comes in; bob 0..1 moves the arrow gently."""
    phase = (time.monotonic() % 1.2) / 1.2
    return QIcon(RingIconEngine(base, fraction, done, phase, pop, bob))
