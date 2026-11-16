"""The Downloads toolbar icon with a progress ring around it.

While files are downloading, a ring in the accent colour fills clockwise from
the top as the bytes arrive (a short turning arc when the size is unknown).
When everything is done the ring is green until the downloads list is opened.
The icon is drawn when it is shown, so it follows theme changes at once.
"""

import time

from PyQt6.QtCore import QPointF, QRect, QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QGuiApplication, QIcon, QIconEngine, QPainter, QPalette, QPen, QPixmap

DONE_COLOUR = "#27ae60"          # Breeze "positive" green


class RingIconEngine(QIconEngine):
    def __init__(self, base, fraction=None, done=False, phase=0.0):
        super().__init__()
        self.base = base
        self.fraction = fraction            # 0..1, or None when the size is unknown
        self.done = done
        self.phase = phase                  # 0..1, start of the turning arc

    def clone(self):
        return RingIconEngine(self.base, self.fraction, self.done, self.phase)

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
        self.base.paint(painter, QRect(int(c.x() - inner / 2 + 0.5), int(c.y() - inner / 2 + 0.5),
                                       inner, inner), Qt.AlignmentFlag.AlignCenter, mode, state)
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


def ring_icon(base, fraction=None, done=False):
    """base with a progress ring; fraction None = size unknown."""
    phase = (time.monotonic() % 1.2) / 1.2
    return QIcon(RingIconEngine(base, fraction, done, phase))
