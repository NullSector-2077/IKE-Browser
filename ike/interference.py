"""I.K.E. Interference: the shield's octagon says that something is wrong with
the site in view (1.1.32, the owner's design and colours).

One painter, three styles (STYLES), never three animations:

- "attention", golden yellow (#FACC15): a protection most likely stops some
  feature of the site, which stays usable. Two slow pulses (a 5 s cycle),
  soft trails, a contained glow, a very light inner pulse.
- "serious", neon orange (#FF9100): a protection most likely stops something
  essential (an empty page, a player that cannot play, an app waiting on a
  refused worker). Two pulses with a nearly golden core (a 2.8 s cycle),
  fading trails, a clearer glow, a short wave of energy along the contour
  and an inner pulse where they meet.
- "danger", crimson (#FF254F): a real security risk that I.K.E.'s own safety
  warnings found (a lookalike site, a page on the malware and phishing
  lists, a missing secure connection, an attack on the home network, a
  certificate the engine refused). Brighter pulses with well marked trails
  (a 2 s cycle). It follows the warning's own life and never suggests
  "Repair this site": a safety warning is not an incompatibility.

The two pulses run along the octagon's rim in opposite directions and meet
at the top and at the bottom, twice a cycle; then they go on without a seam.
No flashing, no strobe: every change of light is a smooth curve. The octagon
keeps its shape, size, place, level colour, letter and behaviour; the effect
is drawn over its rim with its own geometry (shieldpanel.octagon) and never
over the letter. A change of style (yellow to orange, orange to red) blends
the two in 0.6 s; the end, when the site works again, fades out in 0.4 s.

Cost: nothing while nothing is shown (no timer). With a style, about 24
pictures a second of the button alone, and only while the button is shown
(another tab without a finding, a hidden or minimised window: no timer; the
phase is kept). With the interface's effects off, or reduced motion asked by
the desktop, a still rim in the style's colour, drawn once.
"""

import math
import time

from PyQt6.QtCore import QEvent, QObject, QPointF, QRectF, Qt, QTimer, QVariantAnimation, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen, QRadialGradient

FRAME_MS = 42                    # about 24 pictures a second
SEGMENTS = 12                    # pieces of each trail
MEET_WIDTH = 0.07                # of a cycle, around each meeting
BLEND_MS = 600                   # from one style to another
FADE_MS = 400                    # the end

ATTENTION, SERIOUS, DANGER, CONFIRM = "attention", "serious", "danger", "confirm"
# the green confirmation (1.1.32, the owner's fourth colour): played once, then gone
CONFIRM_RUN_S = 1.3              # the two pulses from the top to their meeting at the bottom
CONFIRM_FADE_S = 0.5             # then the octagon fades back to itself: 1.8 s in all
CONFIRM_IN_S = 0.15

# Qt's enumerations looked up once (each lookup costs a call at every picture)
_SOLID, _ROUND_CAP, _ROUND_JOIN = Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin
_NO_PEN, _NO_BRUSH = Qt.PenStyle.NoPen, Qt.BrushStyle.NoBrush
_ANTIALIAS = QPainter.RenderHint.Antialiasing


class Style:
    """The numbers of one style; blend() mixes two of them."""

    FIELDS = ("cycle", "glow", "glow_alpha", "trail", "trail_alpha", "rim", "meet", "inner", "wave", "head")

    def __init__(self, colour, core, **kw):
        self.colour = QColor(colour)
        self.core = QColor(core)
        for f in self.FIELDS:
            setattr(self, f, float(kw[f]))

    def blend(self, other, t):
        if t <= 0:
            return self
        if t >= 1:
            return other
        out = Style.__new__(Style)

        def mix(a, b):
            return QColor.fromRgbF(a.redF() + (b.redF() - a.redF()) * t,
                                   a.greenF() + (b.greenF() - a.greenF()) * t,
                                   a.blueF() + (b.blueF() - a.blueF()) * t)
        out.colour = mix(self.colour, other.colour)
        out.core = mix(self.core, other.core)
        for f in self.FIELDS:
            a, b = getattr(self, f), getattr(other, f)
            setattr(out, f, a + (b - a) * t)
        return out


#                cycle s, glow radius / alpha (of the rim's width), trail length / alpha,
#                faint rim, its brightening at a meeting, inner pulse, energy wave, head size
STYLES = {
    ATTENTION: Style("#FACC15", "#FFF3B0", cycle=5.0, glow=1.6, glow_alpha=0.35, trail=0.24,
                     trail_alpha=0.55, rim=0.0, meet=0.22, inner=0.08, wave=0.0, head=0.48),
    SERIOUS: Style("#FF9100", "#FFD56A", cycle=2.8, glow=2.1, glow_alpha=0.55, trail=0.30,
                   trail_alpha=0.80, rim=0.0, meet=0.45, inner=0.20, wave=0.50, head=0.55),
    DANGER: Style("#FF254F", "#FFD3DC", cycle=2.0, glow=2.2, glow_alpha=0.65, trail=0.34,
                  trail_alpha=0.95, rim=0.08, meet=0.35, inner=0.10, wave=0.0, head=0.60),
    # once, never as a state: its cycle is the time of one run (top to bottom is half a cycle)
    CONFIRM: Style("#00E676", "#C8FFE3", cycle=2 * CONFIRM_RUN_S, glow=1.8, glow_alpha=0.45, trail=0.26,
                   trail_alpha=0.70, rim=0.0, meet=0.35, inner=0.12, wave=0.40, head=0.50),
}


def _bump(t):
    """1 at a meeting (t = 0 or 0.5), 0 away from it, smooth (no edge, no flash)."""
    d = min(t % 0.5, 0.5 - (t % 0.5))
    if d >= MEET_WIDTH:
        return 0.0
    return 0.5 * (1 + math.cos(math.pi * d / MEET_WIDTH))


class Interference(QObject):
    """The animation's state for one shield button."""

    confirm_ended = pyqtSignal()     # the green confirmation finished or was cut short

    def __init__(self, button, config):
        super().__init__(button)
        self.button = button
        self.config = config
        self.state = None            # ATTENTION, SERIOUS, DANGER or None
        self.style = None            # the Style drawn now (blended while changing)
        self._from = None
        self._blend = 1.0
        self.strength = 0.0          # 1 while shown, falls to 0 at the end
        self.phase = 0.0             # 0..1 of a cycle, kept while suspended
        self._last = None
        self._timer = QTimer(self)
        self._timer.setInterval(FRAME_MS)
        self._timer.timeout.connect(self._tick)
        self._anim = None            # the blend or the fade
        self._path_key = None
        self._path = None
        self._pens = (None, None)    # (key, trail pens) for the style and strength drawn
        self.frames = 0              # pictures drawn (the tests measure the cost)
        self._confirm_at = None      # when the green confirmation started (monotonic), or None
        self.confirms = 0            # how many were played (the tests count them)
        button.installEventFilter(self)
        self._watched = None
        self._watch_window()

    def _watch_window(self):
        win = self.button.window()
        if win is not None and win is not self.button and win is not self._watched:
            if self._watched is not None:
                self._watched.removeEventFilter(self)
            win.installEventFilter(self)
            self._watched = win

    # --- state ------------------------------------------------------------
    def moving(self):
        from . import polish
        return polish.moving(self.config, "shield_interference")

    def set_state(self, state, fade=False):
        """state: ATTENTION, SERIOUS, DANGER or None. fade: the end is the site
        working again here (not another tab or another site)."""
        if state == self.state:
            return
        old, self.state = self.state, state
        self._stop_anim()
        if state is not None and self._confirm_at is not None:
            self._end_confirm(cut=True)       # something more important: at once, no blend
        if state is not None:
            target = STYLES[state]
            if old is not None and self.style is not None and self.moving() and self._shown():
                self._from = self.style            # blend from what is drawn now
                self._blend = 0.0
                self._animate(0.0, 1.0, BLEND_MS, self._blended, None)
            else:
                self._from, self._blend = None, 1.0
            self.style = target if self._from is None else self._from
            self.strength = 1.0
            self._run()
        elif fade and self.style is not None and self.moving() and self._shown():
            self._animate(1.0, 0.0, FADE_MS, self._faded, self._fade_done)
        else:
            self._fade_done()
        self.button.update()

    # --- the green confirmation (one run, no state) ---------------------------
    def confirm(self):
        """Play the green confirmation once: the pulses run from the top to
        their meeting at the bottom, a short wave, then the octagon fades back
        to itself (1.8 s). Never over a state (red, orange, yellow), never
        twice at once (a new page while it plays: it simply goes on), never
        with the effects off or the button out of sight. True if it started."""
        if self.state is not None or self._anim is not None or not self.moving() or not self._shown():
            return False
        if self._confirm_at is not None:
            return False
        self._confirm_at = time.monotonic()
        self.style = STYLES[CONFIRM]
        self.phase = 0.0
        self.strength = 0.0
        self.confirms += 1
        self._run()
        self._update()
        return True

    def cancel_confirm(self):
        """Another tab in front, a page that failed: the confirmation stops at once."""
        if self._confirm_at is not None:
            self._end_confirm(cut=True)

    def confirming(self):
        return self._confirm_at is not None

    def _end_confirm(self, cut=False):
        self._confirm_at = None
        if self.state is None:
            self.style = None
            self.strength = 0.0
            if self._anim is None:
                self._stop()
        self._update()
        self.confirm_ended.emit()

    def _confirm_step(self, now):
        t = now - self._confirm_at
        if t >= CONFIRM_RUN_S + CONFIRM_FADE_S or not self.moving():
            self._end_confirm()
            return
        # on past their meeting while fading, as the wave opens (no stop, no edge)
        self.phase = 0.5 * t / CONFIRM_RUN_S
        if t < CONFIRM_IN_S:
            self.strength = t / CONFIRM_IN_S
        elif t < CONFIRM_RUN_S:
            self.strength = 1.0
        else:
            x = (t - CONFIRM_RUN_S) / CONFIRM_FADE_S
            self.strength = 0.5 * (1 + math.cos(math.pi * x))      # a soft end, no edge

    def _animate(self, a, b, ms, step, done):
        anim = self._anim = QVariantAnimation(self)
        anim.setDuration(ms)
        anim.setStartValue(a)
        anim.setEndValue(b)
        anim.valueChanged.connect(step)
        if done is not None:
            anim.finished.connect(done)
        anim.start()
        self._run()

    def _stop_anim(self):
        if self._anim is not None:
            self._anim.stop()
            self._anim.deleteLater()
            self._anim = None

    def _blended(self, v):
        self._blend = float(v)
        target = STYLES.get(self.state)
        if target is not None and self._from is not None:
            self.style = self._from.blend(target, self._blend)
            if self._blend >= 1:
                self._from = None
        self.button.update()

    def _faded(self, v):
        self.strength = float(v)
        self._update()

    def _fade_done(self):
        self._stop_anim()
        self.strength = 0.0
        self.style = None
        self._from = None
        self._stop()
        self.button.update()

    def _running(self):
        return self.state is not None or self._anim is not None or self._confirm_at is not None

    def _run(self):
        if not self._running():
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
        if t in (QEvent.Type.Show, QEvent.Type.Hide, QEvent.Type.WindowStateChange, QEvent.Type.ParentChange):
            if t == QEvent.Type.ParentChange:
                self._watch_window()
            QTimer.singleShot(0, self._run if self._running() else self._stop)
        return False

    def _tick(self):
        if not self._shown():
            if self._confirm_at is not None:
                self._end_confirm(cut=True)   # out of sight: a confirmation is not kept for later
                return
            self._stop()              # suspended: the phase stays where it was
            return
        now = time.monotonic()
        if self._confirm_at is not None and self.state is None:
            self._last = now
            self._confirm_step(now)
            self._update()
            return
        if self._last is not None and self.style is not None:
            self.phase = (self.phase + (now - self._last) / max(0.5, self.style.cycle)) % 1.0
        self._last = now
        self._update()

    def _update(self):
        """Only the octagon and its glow are painted again (not the count beside it)."""
        b = self.button
        r = b.icon_rect() if hasattr(b, "icon_rect") else None
        if r is None:
            b.update()
            return
        # everything the painter can reach: the glow of a head on the rim
        from .shieldpanel import TOOLBAR_SHIELD_GROW, octagon
        poly, side, stroke = octagon(r, TOOLBAR_SHIELD_GROW)
        glow = stroke * (max(st.glow for st in STYLES.values()) + 0.6)
        m = max(1.0, glow - (r.width() - side) / 2 - stroke / 2 + 1)
        b.update(r.adjusted(-m, -m, m, m).toAlignedRect())

    # --- painting -----------------------------------------------------------
    def _rim(self, polygon):
        key = tuple((round(p.x(), 2), round(p.y(), 2)) for p in polygon)
        if key != self._path_key:
            path = QPainterPath()
            # from the middle of the top edge, round the octagon, back to it
            path.moveTo((polygon[0] + polygon[1]) / 2)
            for i in list(range(1, len(polygon))) + [0]:
                path.lineTo(polygon[i])
            path.closeSubpath()
            self._path_key, self._path = key, path
        return self._path

    @staticmethod
    def _alpha(colour, a):
        c = QColor(colour)
        c.setAlphaF(max(0.0, min(1.0, a)))
        return c

    def paint(self, p, polygon, stroke):
        """Over the octagon (polygon, its rim's width): the pulses, or the still rim."""
        s, k = self.style, self.strength
        if s is None or k <= 0 or polygon is None or len(polygon) < 3:
            return
        self.frames += 1
        p.save()
        p.setRenderHint(_ANTIALIAS)
        round_pen = (_SOLID, _ROUND_CAP, _ROUND_JOIN)
        if not self.moving():
            # effects off: a still rim over the octagon's own
            p.setPen(QPen(self._alpha(s.colour, 0.9 * k), stroke * 1.05, *round_pen))
            p.setBrush(_NO_BRUSH)
            p.drawPolygon(polygon)
            p.restore()
            return
        path = self._rim(polygon)
        t = self.phase
        bump = _bump(t)
        if self._confirm_at is not None and self.state is None and t < 0.25:
            bump = 0.0                # the green starts quietly: its one meeting is at the bottom
        centre = polygon.boundingRect().center()
        # the rim keeps the level's own colour; it lights up only where the
        # pulses meet (the red keeps a very faint tint all the time)
        a = k * (s.rim + s.meet * bump)
        if a > 0.01:
            p.setPen(QPen(self._alpha(s.colour, a), stroke * 0.95, *round_pen))
            p.setBrush(_NO_BRUSH)
            p.drawPolygon(polygon)
        if bump > 0 and s.inner > 0:
            # the inside of the rim pulses; the middle, with the letter, untouched
            g = QRadialGradient(centre, polygon.boundingRect().width() / 2)
            g.setColorAt(0.0, self._alpha(s.colour, 0))
            g.setColorAt(0.62, self._alpha(s.colour, 0))
            g.setColorAt(1.0, self._alpha(s.colour, k * s.inner * bump))
            p.setPen(_NO_PEN)
            p.setBrush(g)
            p.drawPolygon(polygon)
        if bump > 0 and s.wave > 0:
            # the wave of energy: the contour opening a little, fading as it goes
            grow = 1.0 + 0.16 * (1 - bump)
            p.setBrush(_NO_BRUSH)
            p.setPen(QPen(self._alpha(s.colour, k * s.wave * bump), max(0.8, stroke * 0.45)))
            p.save()
            p.translate(centre)
            p.scale(grow, grow)
            p.translate(-centre)
            p.drawPolygon(polygon)
            p.restore()
        # the two pulses, from the top: one clockwise, one the other way
        for direction in (1, -1):
            self._pulse(p, path, (t * direction) % 1.0, direction, stroke, k, bump, s)
        p.restore()

    def _trail_pens(self, s, k, stroke):
        """The trail's pens, fainter and thinner behind the head: made once
        per style, strength and size, not at every picture."""
        key = (id(s), round(k, 3), round(stroke, 3))
        if self._pens[0] != key:
            n = SEGMENTS if stroke < 3 else SEGMENTS * 2       # a smooth trail on a big octagon too
            pens = []
            for i in range(1, n + 1):
                fade = 1.0 - i / (n + 1)
                pens.append(QPen(self._alpha(s.colour, k * s.trail_alpha * fade * fade), stroke * (0.55 + 0.75 * fade),
                                 _SOLID, _ROUND_CAP))
            self._pens = (key, pens)
        return self._pens[1]

    def _pulse(self, p, path, head, direction, stroke, k, bump, s):
        # the trail: short pieces behind the head, fainter and thinner
        prev = path.pointAtPercent(head)
        pens = self._trail_pens(s, k, stroke)
        n = len(pens)
        for i in range(1, n + 1):
            pt = path.pointAtPercent((head - direction * s.trail * i / n) % 1.0)
            p.setPen(pens[i - 1])
            p.drawLine(prev, pt)
            prev = pt
        pos = path.pointAtPercent(head)
        # the glow, then the bright core
        r = stroke * (s.glow + 0.6 * bump)
        g = QRadialGradient(pos, r)
        g.setColorAt(0.0, self._alpha(s.colour, k * (s.glow_alpha + 0.2 * bump)))
        g.setColorAt(1.0, self._alpha(s.colour, 0))
        p.setPen(_NO_PEN)
        p.setBrush(g)
        p.drawEllipse(QRectF(pos.x() - r, pos.y() - r, 2 * r, 2 * r))
        p.setBrush(self._alpha(s.core, k * 0.95))
        h = stroke * s.head
        p.drawEllipse(QPointF(pos), h, h)
