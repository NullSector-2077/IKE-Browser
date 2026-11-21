"""The small extra effects of the interface: short fades, gliding hover of the
buttons I.K.E. draws itself, the smooth advance of the loading line and the
turning mark on a tab that is loading.

They are light on purpose (no blur, no shadows, nothing that keeps running
while the interface is still) and all of them are off when the user turns
"Interface effects" off in Settings or the desktop asks for reduced motion.
Without them everything works the same, changing at once.
"""

import os
import time

from PyQt6.QtCore import QEasingCurve, QObject, QPropertyAnimation, QRectF, Qt, QVariantAnimation
from PyQt6.QtGui import QColor, QIcon, QPainter, QPalette, QPen, QPixmap

FADE_MS = 120
HOVER_MS = 110
LINE_MS = 160
SPIN_MS = 90                  # one step of the loading mark
SPIN_STEP = 30                # degrees per step
_checked = {"at": -1e9, "reduced": False}


def _opacity_setter(widget, fixed=None):
    """A slot that sets widget's opacity: to the signal's value, or to fixed."""
    if fixed is None:
        def on_value(value):
            widget.setWindowOpacity(float(value))
        return on_value

    def on_end():
        widget.setWindowOpacity(fixed)
    return on_end


def _ini_value(path, key):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                name, sep, value = line.partition("=")
                if sep and name.strip() == key:
                    return value.strip()
    except OSError:
        pass
    return None


def _desktop_reduced():
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    # Plasma: System Settings → Animation speed set to "Instant"
    factor = _ini_value(os.path.join(base, "kdeglobals"), "AnimationDurationFactor")
    if factor is not None:
        try:
            return float(factor) <= 0
        except ValueError:
            pass
    # GTK desktops (and what Plasma writes for GTK programs)
    for folder in ("gtk-4.0", "gtk-3.0"):
        value = _ini_value(os.path.join(base, folder, "settings.ini"), "gtk-enable-animations")
        if value is not None:
            return value.lower() in ("0", "false")
    return False


def reduced_motion():
    """True when the desktop is set to show no animations (looked up again
    every few seconds, so a change is followed without a restart)."""
    forced = os.environ.get("IKE_REDUCED_MOTION")
    if forced in ("0", "1"):
        return forced == "1"
    now = time.monotonic()
    if now - _checked["at"] > 5.0:
        _checked["at"], _checked["reduced"] = now, _desktop_reduced()
    return _checked["reduced"]


def on(config):
    """Are the extra effects to be shown now?"""
    try:
        wanted = bool(config["ui_effects"])
    except (KeyError, TypeError):
        wanted = True
    return wanted and not reduced_motion()


def fade_in(widget, config, ms=FADE_MS):
    """Let a menu or panel appear with a short fade. Call it when the popup is
    about to show. Where the desktop cannot change a window's opacity nothing
    happens, and the popup appears as before."""
    anim = getattr(widget, "_ike_fade", None)
    if not on(config):
        if anim is not None:
            anim.stop()
            widget.setWindowOpacity(1.0)
        return
    if anim is None:
        anim = widget._ike_fade = QVariantAnimation(widget)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        # closures, not lambdas with default arguments: with Python 3.14 and
        # PyQt 6.12 (Arch) a slot's default argument was taken for one the
        # signal must give ("missing 1 required positional argument: 'w'")
        anim.valueChanged.connect(_opacity_setter(widget))
        anim.finished.connect(_opacity_setter(widget, 1.0))
    anim.stop()
    anim.setDuration(ms)
    widget.setWindowOpacity(0.0)
    anim.start()


def cross_fade(widgets, config, ms=200):
    """Call just before the look of widgets changes: a picture of each as it is
    now is laid over it and fades away, so a new theme comes in softly. Used
    for the bars of a window, never for the page (its picture may be empty)."""
    from PyQt6.QtWidgets import QGraphicsOpacityEffect, QLabel
    if not on(config):
        return 0
    n = 0
    for w in widgets:
        if w is None or not w.isVisible() or w.width() < 2 or w.height() < 2:
            continue
        shot = QLabel(w)
        shot.setObjectName("ike_theme_fade")
        shot.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        shot.setPixmap(w.grab())
        shot.setGeometry(w.rect())
        effect = QGraphicsOpacityEffect(shot)
        shot.setGraphicsEffect(effect)
        anim = QPropertyAnimation(effect, b"opacity", shot)
        anim.setDuration(ms)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.finished.connect(shot.deleteLater)
        shot.show()
        shot.raise_()
        anim.start()
        n += 1
    return n


def fading(menu, config):
    """Make a QMenu fade in each time it opens."""
    menu.aboutToShow.connect(lambda m=menu: fade_in(m, config))
    menu.aboutToHide.connect(lambda m=menu: _settle(m))
    return menu


def _settle(widget):
    anim = getattr(widget, "_ike_fade", None)
    if anim is not None:
        anim.stop()
    widget.setWindowOpacity(1.0)


class Glide(QObject):
    """A level between 0 and 1 that glides to its target, for the hover of a
    button drawn by I.K.E.: changed() is called at each step to repaint."""

    def __init__(self, parent, config, changed, ms=HOVER_MS):
        super().__init__(parent)
        self.config, self.changed, self.ms = config, changed, ms
        self.value = 0.0
        self._anim = None

    @property
    def moving(self):
        return self._anim is not None and self._anim.state() == QVariantAnimation.State.Running

    def to(self, target):
        target = 1.0 if target else 0.0
        if not on(self.config):
            if self._anim is not None:
                self._anim.stop()
            self.value = target
            self.changed()
            return
        if self._anim is None:
            self._anim = QVariantAnimation(self)
            self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            self._anim.valueChanged.connect(self._step)
        self._anim.stop()
        self._anim.setDuration(max(1, round(self.ms * abs(target - self.value))))
        self._anim.setStartValue(float(self.value))
        self._anim.setEndValue(target)
        self._anim.start()

    def jump(self, target):
        if self._anim is not None:
            self._anim.stop()
        self.value = 1.0 if target else 0.0

    def _step(self, v):
        self.value = float(v)
        self.changed()


def blend(a, b, t):
    """The colour t of the way from a to b (alpha included)."""
    a, b = QColor(a), QColor(b)
    t = max(0.0, min(1.0, t))
    return QColor(round(a.red() + (b.red() - a.red()) * t), round(a.green() + (b.green() - a.green()) * t),
                  round(a.blue() + (b.blue() - a.blue()) * t), round(a.alpha() + (b.alpha() - a.alpha()) * t))


def loading_icon(base, angle, palette):
    """A tab icon with the small mark of a page that is loading: an open ring
    in the accent colour over the icon's upper left corner, turned by angle."""
    pm = QPixmap(32, 32)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    base.paint(p, 0, 0, 32, 32)
    # the corner is cleared, so the mark reads on any tab colour
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(0, 0, 0))
    p.drawEllipse(QRectF(-1, -1, 19, 19))
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
    pen = QPen(palette.color(QPalette.ColorRole.Highlight), 3.2)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawArc(QRectF(2.5, 2.5, 12, 12), int(-angle * 16), 270 * 16)
    p.end()
    pm.setDevicePixelRatio(2)
    return QIcon(pm)
