"""Touchpad gestures on the page (1.1.24): a horizontal swipe goes back or
forward, the page sliding away; a pinch zooms, with the zoom shown in the
small on-screen box (window.osd).

They come as Qt's native gestures (QNativeGestureEvent): on Wayland from the
compositor's pointer gestures (a pinch with two fingers; a swipe as the
compositor sends it, with three or more fingers where the compositor keeps
two-finger strokes for scrolling), on X11 from libinput through Qt where it
gives them. The page's own scrolling is never touched. Nothing runs between
gestures; with "Interface effects" off or reduced motion the page changes
without sliding."""

from PyQt6.QtCore import QEasingCurve, QPoint, QRect, Qt, QVariantAnimation
from PyQt6.QtGui import QPainter
from PyQt6.QtWidgets import QWidget

from . import polish

SWIPE_PX = 110               # how far the fingers move sideways for back or forward
SLIDE_MS = 240
ZOOM_MIN, ZOOM_MAX = 0.25, 5.0

G = Qt.NativeGestureType


def _state(view):
    st = view.__dict__.get("_ike_gesture")
    if st is None:
        st = view.__dict__["_ike_gesture"] = {"dx": 0.0, "pinch": False}
    return st


def handle(view, event):
    """A native gesture on view's page; True when I.K.E. used it."""
    if not polish.part("gestures"):
        return False
    kind = event.gestureType()
    st = _state(view)
    win = view.window_ref
    if kind == G.BeginNativeGesture:
        st["dx"], st["pinch"] = 0.0, False
        return False
    if kind == G.ZoomNativeGesture:
        pinch(view, float(event.value()))
        st["pinch"] = True
        return True
    if kind == G.PanNativeGesture:
        st["dx"] += float(event.delta().x())
        return True
    if kind == G.SwipeNativeGesture:
        angle = float(event.value()) % 360
        if angle < 45 or angle > 315:
            return swipe(view, back=True)
        if 135 < angle < 225:
            return swipe(view, back=False)
        return False
    if kind == G.EndNativeGesture:
        if st["pinch"]:
            st["pinch"] = False
            win._remember_zoom(view)
            return True
        dx, st["dx"] = st["dx"], 0.0
        if abs(dx) >= SWIPE_PX:
            return swipe(view, back=dx > 0)
    return False


def pinch(view, delta):
    """Zoom by a pinch: delta is the change of scale Qt reports (0.02 = 2 %)."""
    win = view.window_ref
    f = max(ZOOM_MIN, min(ZOOM_MAX, view.zoomFactor() * (1.0 + delta)))
    if abs(f - view.zoomFactor()) < 1e-4:
        return
    view.setZoomFactor(f)
    if view is win.current_view():
        win._zoom_sign()
    win.zoom_osd(view)


def swipe(view, back):
    """Back (fingers to the right) or forward: the page slides away the way
    the fingers went, while the other page comes."""
    h = view.history()
    if not (h.canGoBack() if back else h.canGoForward()):
        return False
    win = view.window_ref
    if polish.moving(win.app.config, "gestures"):
        PageSlide(view, 1 if back else -1)
    view.back() if back else view.forward()
    return True


class PageSlide(QWidget):
    """A picture of the page as it was, sliding out sideways over the page."""

    def __init__(self, view, direction, ms=SLIDE_MS):
        holder = view.parentWidget()
        super().__init__(holder)
        self.setObjectName("ike_page_slide")
        polish.keep(self)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.picture = view.grab()
        self.place = QRect(view.geometry())
        self.direction = direction
        self.setGeometry(self.place)
        self.t = 0.0
        self.anim = QVariantAnimation(self)
        self.anim.setDuration(ms)
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(1.0)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.anim.valueChanged.connect(self._step)
        self.anim.finished.connect(self.deleteLater)
        self.show()
        self.raise_()
        self.anim.start()

    def _step(self, v):
        self.t = float(v)
        self.update()

    def shift(self):
        return round(self.direction * self.t * self.width())

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setOpacity(1.0 - 0.6 * self.t)
        p.drawPixmap(QPoint(self.shift(), 0), self.picture)
        p.end()
