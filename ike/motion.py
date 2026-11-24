"""Touches of 1.1.24 that look at the whole application: tooltips that fade
in and out, and the keys of the toolbar buttons shown while Ctrl or Alt is
held for a second.

One event filter on the application looks at a handful of event kinds and
lets every event through; nothing runs while the interface is still (no
timer, no animation), and both follow "Interface effects" and the desktop's
reduced motion (polish.moving), like the other touches."""

from PyQt6.QtCore import QEasingCurve, QEvent, QObject, QPoint, QRect, Qt, QTimer, QVariantAnimation
from PyQt6.QtGui import QGuiApplication, QKeySequence, QPainter, QPalette
from PyQt6.QtWidgets import QApplication, QToolButton, QWidget

from . import effects, polish

TIP_IN_MS = 90
TIP_OUT_MS = 110
HOLD_MS = 1000               # Ctrl or Alt held this long: the keys of the buttons show

_WATCHED = frozenset((QEvent.Type.Show, QEvent.Type.Close, QEvent.Type.KeyPress, QEvent.Type.KeyRelease,
                      QEvent.Type.ShortcutOverride,
                      QEvent.Type.MouseButtonPress, QEvent.Type.ApplicationStateChange,
                      QEvent.Type.WindowDeactivate))
_MODIFIERS = {Qt.Key.Key_Control: Qt.KeyboardModifier.ControlModifier,
              Qt.Key.Key_Alt: Qt.KeyboardModifier.AltModifier}


def opacity_works():
    """Can a window here fade? (Wayland gives a program no window opacity:
    there the desktop's own effects fade popups and tooltips.)"""
    return QGuiApplication.platformName() not in ("wayland", "wayland-egl")


class AppTouches(QObject):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.config = app.config
        self._hold = QTimer(self)
        self._hold.setSingleShot(True)
        self._hold.setInterval(HOLD_MS)
        self._hold.timeout.connect(self._show_hints)
        self._held = None            # (window, modifier) while Ctrl or Alt is held
        self.hints = []              # the labels shown now
        self.ghosts = 0              # tooltips faded out (for the tests)
        app.qapp.installEventFilter(self)

    def eventFilter(self, obj, event):
        t = event.type()
        if t not in _WATCHED:
            return False
        if t == QEvent.Type.Show:
            if obj.isWidgetType() and obj.inherits("QTipLabel"):
                self._tip_in(obj)
        elif t == QEvent.Type.Close:
            if obj.isWidgetType() and obj.inherits("QTipLabel") and obj.isVisible():
                self._tip_out(obj)
        elif t == QEvent.Type.KeyPress:
            mod = _MODIFIERS.get(event.key())
            # no other modifier held (Qt adds or leaves out the key's own one
            # depending on the platform)
            if mod is not None and not event.modifiers() & ~(mod | Qt.KeyboardModifier.KeypadModifier):
                if not event.isAutoRepeat() and self._held is None:
                    self._start_hold(mod)
            else:
                self.end_hints()             # a shortcut is being typed: no labels over it
        elif t == QEvent.Type.ShortcutOverride:
            if event.key() not in _MODIFIERS:     # a shortcut: its key press never comes here
                self.end_hints()
        elif t == QEvent.Type.KeyRelease:
            if event.key() in _MODIFIERS and not event.isAutoRepeat():
                self.end_hints()
        else:
            if self._held is not None or self.hints:
                self.end_hints()
        return False

    # --- tooltips (1.1.24) -------------------------------------------------------
    def _tip_in(self, tip):
        if polish.moving(self.config, "tooltip_fade") and opacity_works():
            effects.fade_in(tip, self.config, TIP_IN_MS)

    def _tip_out(self, tip):
        """The tooltip closes: a picture of it, in its place, fades away (the
        tooltip itself is deleted at once by Qt)."""
        if not polish.moving(self.config, "tooltip_fade") or not opacity_works():
            return None
        ghost = TipGhost(tip)
        self.ghosts += 1
        return ghost

    # --- the keys of the toolbar buttons (1.1.24) ----------------------------------
    def _window(self):
        from .window import BrowserWindow
        w = QApplication.activeWindow()
        return w if isinstance(w, BrowserWindow) else None

    def _start_hold(self, mod):
        win = self._window()
        if win is None or not polish.part("key_hints"):
            return
        self._held = (win, mod)
        self._hold.start()

    def _show_hints(self):
        if self._held is None:
            return
        win, mod = self._held
        try:
            if not win.isActiveWindow() or not win.nav.isVisible():
                return
        except RuntimeError:              # the window is gone
            self._held = None
            return
        self.hints = show_hints(win, mod)

    def end_hints(self):
        self._hold.stop()
        self._held = None
        for h in self.hints:
            try:
                h.hide()
                h.deleteLater()
            except RuntimeError:
                pass
        self.hints = []


class TipGhost(QWidget):
    """A closed tooltip's picture fading out where it was."""

    def __init__(self, tip):
        super().__init__(None, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setObjectName("ike_tip_ghost")
        polish.keep(self)
        self.picture = tip.grab()
        self.setGeometry(tip.geometry())
        self.setWindowOpacity(tip.windowOpacity())
        self.anim = QVariantAnimation(self)
        self.anim.setDuration(TIP_OUT_MS)
        self.anim.setStartValue(float(tip.windowOpacity()))
        self.anim.setEndValue(0.0)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.anim.valueChanged.connect(lambda v: self.setWindowOpacity(float(v)))
        self.anim.finished.connect(self.close)
        self.show()
        self.anim.start()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.drawPixmap(0, 0, self.picture)
        p.end()


# the toolbar buttons whose own action has no key: the key of the same
# command in the menus
TWINS = {"act_tb_bookmark": "act_bookmark", "act_tb_shot": "act_shot", "act_tb_private": "act_new_private"}


def hint_text(win, button, mod):
    """The key of button's command that uses mod (Ctrl or Alt), as the
    desktop writes it; "" when it has none."""
    act = button.defaultAction()
    if act is None:
        return ""
    keys = list(act.shortcuts())
    if not keys:
        for name, twin in TWINS.items():
            if getattr(win, name, None) is act and getattr(win, twin, None) is not None:
                keys = list(getattr(win, twin).shortcuts())
    want = mod
    for k in keys:
        if k.isEmpty():
            continue
        combo = k[0]
        mods = combo.keyboardModifiers()
        if mods & want and not mods & ~want & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier):
            return k.toString(QKeySequence.SequenceFormat.NativeText)
    return ""


class KeyHint(QWidget):
    """A small label of a key under a toolbar button, in the tooltip's colours."""

    PAD = 5

    def __init__(self, win, text):
        super().__init__(win)
        self.setObjectName("ike_key_hint")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.text = text
        f = self.font()
        if f.pointSizeF() > 0:
            f.setPointSizeF(f.pointSizeF() * 0.85)
        self.setFont(f)
        fm = self.fontMetrics()
        self.resize(fm.horizontalAdvance(text) + 2 * self.PAD + 2, fm.height() + 4)

    def paintEvent(self, _event):
        from PyQt6.QtCore import QRectF
        pal = self.palette()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(polish.separator(pal))
        p.setBrush(pal.color(QPalette.ColorRole.ToolTipBase))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), polish.RADIUS / 2 + 1,
                          polish.RADIUS / 2 + 1)
        p.setPen(pal.color(QPalette.ColorRole.ToolTipText))
        p.drawText(self.rect(), int(Qt.AlignmentFlag.AlignCenter), self.text)
        p.end()


def show_hints(win, mod):
    """One KeyHint under each visible toolbar button that has a key with mod;
    the labels stay inside the window and never overlap one another (a
    label wider than its button puts the next one a row lower)."""
    out = []
    taken = []
    for b in win.nav.findChildren(QToolButton):
        if not b.isVisible() or b.parentWidget() is not win.nav:
            continue
        text = hint_text(win, b, mod)
        if not text:
            continue
        h = KeyHint(win, text)
        centre = b.mapTo(win, QPoint(b.width() // 2, b.height()))
        x = max(2, min(win.width() - h.width() - 2, centre.x() - h.width() // 2))
        y = centre.y() - h.height() // 2
        r = QRect(x, y, h.width(), h.height())
        for _row in range(3):            # a label wider than its button: the next one goes a row lower
            if not any(r.intersects(o) for o in taken):
                break
            r.translate(0, h.height() + 2)
        else:
            h.deleteLater()
            continue
        y = r.y()
        taken.append(r)
        h.move(x, y)
        h.show()
        h.raise_()
        polish.fade_child(h, win.app.config, 110)
        out.append(h)
    return out
