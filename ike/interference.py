"""I.K.E. Interference: the shield's octagon says that a protection may stop
the site in view from working (1.1.32, the owner's design).

Two red neon pulses run along the octagon's rim in opposite directions, each
with a bright head, a soft glow and a trail that fades behind it; where they
meet (at the top, then at the bottom, every 1.4 s of a 2.8 s cycle) the rim
brightens for a moment, a thin wave of energy runs along the contour and the
inside of the rim pulses faintly. Then they go on, without a seam. It reads
as a circuit reporting interference, not as a danger: no flashing, no
strobe, a modest glow, nothing over the level's letter; the octagon keeps
its shape, size, place, colours, letter and behaviour.

Cost: nothing while there is no finding (no timer). With one, 24 pictures a
second of the button alone (about two dozen short antialiased strokes), and
only while the button is shown: a hidden or minimised window, another tab
without a finding, stop it; the phase is kept. With the interface's effects
off (or reduced motion asked by the desktop), a still red rim instead. When
the user confirms the site works, the red fades out in 0.4 s.

Painted by ShieldButton (shieldpanel.py) over its own octagon, with the
octagon's own geometry (shieldpanel.octagon).
"""

import math
import time

from PyQt6.QtCore import QEvent, QObject, QPointF, QRectF, Qt, QTimer, QVariantAnimation
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen, QRadialGradient

RED = QColor("#FF2A52")          # the owner's #FF254F / #FF153E, a touch lighter for dark themes too
HOT = QColor("#FFD3DC")          # the white-hot head
CYCLE_S = 2.8                    # the two pulses meet every half cycle (1.4 s)
FRAME_MS = 42                    # 24 pictures a second
TRAIL = 0.30                     # of the rim behind each head
SEGMENTS = 12                    # pieces of each trail
MEET_WIDTH = 0.07                # of a cycle, around each meeting: the flash
FADE_MS = 400


def _bump(t):
    """1 at a meeting (t = 0 or 0.5), 0 away from it, smooth."""
    d = min(t % 0.5, 0.5 - (t % 0.5))
    if d >= MEET_WIDTH:
        return 0.0
    x = d / MEET_WIDTH
    return 0.5 * (1 + math.cos(math.pi * x))


class Interference(QObject):
    """The animation's state for one shield button."""

    def __init__(self, button, config):
        super().__init__(button)
        self.button = button
        self.config = config
        self.active = False
        self.strength = 0.0          # 1 while active, falls to 0 when the finding is resolved
        self.phase = 0.0             # 0..1 of a cycle, kept while suspended
        self._last = None
        self._timer = QTimer(self)
        self._timer.setInterval(FRAME_MS)
        self._timer.timeout.connect(self._tick)
        self._fade = None
        self._path_key = None
        self._path = None
        self.frames = 0              # pictures drawn (the tests measure the cost)
        button.installEventFilter(self)
        win = button.window()
        if win is not None and win is not button:
            win.installEventFilter(self)

    # --- state ------------------------------------------------------------
    def moving(self):
        from . import polish
        return polish.moving(self.config, "shield_interference")

    def set_active(self, on, fade=False):
        """on: a finding for the site in view. fade: the user resolved it here."""
        if on:
            if self._fade is not None:
                self._fade.stop()
                self._fade = None
            self.active = True
            self.strength = 1.0
            self._run()
        elif self.active:
            self.active = False
            if fade and self.moving() and self.button.isVisible():
                a = self._fade = QVariantAnimation(self)
                a.setDuration(FADE_MS)
                a.setStartValue(1.0)
                a.setEndValue(0.0)
                a.valueChanged.connect(self._faded)
                a.finished.connect(self._fade_done)
                a.start()
            else:
                self.strength = 0.0
                self._stop()
        self.button.update()

    def _faded(self, v):
        self.strength = float(v)
        self.button.update()

    def _fade_done(self):
        self._fade = None
        self.strength = 0.0
        self._stop()
        self.button.update()

    def _run(self):
        if not (self.active or self._fade is not None):
            return
        if not self.moving() or not self._shown():
            self._stop()
            return
        if not self._timer.isActive():
            self._last = time.monotonic()
            self._timer.start()

    def _stop(self):
        self._timer.stop()
        self._last = None

    def _shown(self):
        b = self.button
        win = b.window()
        return b.isVisible() and win is not None and not win.isMinimized()

    def eventFilter(self, obj, event):
        t = event.type()
        if t in (QEvent.Type.Show, QEvent.Type.Hide, QEvent.Type.WindowStateChange):
            QTimer.singleShot(0, self._run if self.active else self._stop)
        return False

    def _tick(self):
        if not self._shown():
            self._stop()              # suspended: the phase stays where it was
            return
        now = time.monotonic()
        if self._last is not None:
            self.phase = (self.phase + (now - self._last) / CYCLE_S) % 1.0
        self._last = now
        self.button.update()

    # --- painting -----------------------------------------------------------
    def _rim(self, polygon):
        key = tuple((round(p.x(), 2), round(p.y(), 2)) for p in polygon)
        if key != self._path_key:
            path = QPainterPath()
            # from the middle of the top edge, round the octagon, back to it
            top = (polygon[0] + polygon[1]) / 2
            path.moveTo(top)
            for i in list(range(1, len(polygon))) + [0]:
                path.lineTo(polygon[i])
            path.lineTo(top)
            self._path_key, self._path = key, path
        return self._path

    def paint(self, p, polygon, stroke):
        """Over the octagon (polygon, its rim's width): the pulses, or the still rim."""
        k = self.strength
        if k <= 0 or polygon is None or len(polygon) < 3:
            return
        self.frames += 1
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.moving():
            # effects off: a still red rim over the octagon's own
            c = QColor(RED)
            c.setAlphaF(0.9 * k)
            p.setPen(QPen(c, stroke * 1.05, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                          Qt.PenJoinStyle.RoundJoin))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPolygon(polygon)
            p.restore()
            return
        path = self._rim(polygon)
        t = self.phase
        bump = _bump(t)
        centre = polygon.boundingRect().center()
        # a faint rim all the time, brighter at a meeting
        rim = QColor(RED)
        rim.setAlphaF(k * (0.28 + 0.45 * bump))
        p.setPen(QPen(rim, stroke * 0.95, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPolygon(polygon)
        if bump > 0:
            # the inside of the rim pulses (the letter in the middle untouched)
            r = polygon.boundingRect().width() / 2
            g = QRadialGradient(centre, r)
            inner = QColor(RED)
            inner.setAlphaF(0)
            g.setColorAt(0.0, inner)
            g.setColorAt(0.62, inner)
            edge = QColor(RED)
            edge.setAlphaF(k * 0.22 * bump)
            g.setColorAt(1.0, edge)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(g)
            p.drawPolygon(polygon)
            # the wave of energy: the contour, a little larger, fading as it opens
            grow = 1.0 + 0.16 * (1 - bump)
            wave = QColor(RED)
            wave.setAlphaF(k * 0.55 * bump)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(wave, max(0.8, stroke * 0.45)))
            p.save()
            p.translate(centre)
            p.scale(grow, grow)
            p.translate(-centre)
            p.drawPolygon(polygon)
            p.restore()
        # the two pulses: one clockwise, one the other way, from the top
        for direction in (1, -1):
            head = (t * direction) % 1.0
            self._pulse(p, path, head, direction, stroke, k, bump)
        p.restore()

    def _pulse(self, p, path, head, direction, stroke, k, bump):
        # the trail: short pieces behind the head, fainter and thinner
        prev = path.pointAtPercent(head)
        for i in range(1, SEGMENTS + 1):
            at = (head - direction * TRAIL * i / SEGMENTS) % 1.0
            pt = path.pointAtPercent(at)
            fade = 1.0 - i / (SEGMENTS + 1)
            c = QColor(RED)
            c.setAlphaF(k * 0.85 * fade * fade)
            p.setPen(QPen(c, stroke * (0.55 + 0.75 * fade), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawLine(prev, pt)
            prev = pt
        pos = path.pointAtPercent(head)
        # the glow, then the bright head
        glow_r = stroke * (2.1 + 0.8 * bump)
        g = QRadialGradient(pos, glow_r)
        c0 = QColor(RED)
        c0.setAlphaF(k * (0.55 + 0.25 * bump))
        c1 = QColor(RED)
        c1.setAlphaF(0)
        g.setColorAt(0.0, c0)
        g.setColorAt(1.0, c1)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.drawEllipse(QRectF(pos.x() - glow_r, pos.y() - glow_r, 2 * glow_r, 2 * glow_r))
        hot = QColor(HOT)
        hot.setAlphaF(k * 0.95)
        p.setBrush(hot)
        r = stroke * 0.55
        p.drawEllipse(QPointF(pos), r, r)
