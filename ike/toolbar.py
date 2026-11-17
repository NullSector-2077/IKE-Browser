"""The navigation toolbar: which buttons it shows, on which side of the address
bar and in which order, and moving them with the mouse.

    Back Forward Home Reload | left zone ~ Shield address bar ~ right zone | window buttons

Back, Forward, Home, Reload and the separator after them are fixed, and so is
the shield, right before the address bar (1.1.9, the owner's choice). The other buttons
live in one of two zones and can be moved inside a zone or to the other one,
after a long press or at once in "Customise toolbar" mode.

ToolbarLayout is the single description of the arrangement (plain data, saved
in the settings as "toolbar_order", "toolbar_left" and "toolbar_hidden").
ToolbarMover turns mouse events on the buttons into a move. While a button is
dragged the toolbar itself is not touched: a marker shows where the button
would land and the move is applied once, on release. (QToolBar builds a new
button whenever an action is inserted, so rearranging it during the drag
destroyed the very button that was receiving the mouse events.)

When the window is too narrow for all the buttons, the last ones are taken
out of the toolbar and listed under a "»" button (spill() says which), so the
address bar, the menu and the window buttons always stay in view.
"""

from PyQt6.QtCore import QEvent, QObject, QPoint, QRect, QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QPainter, QPalette, QPen, QPixmap
from PyQt6.QtWidgets import QApplication, QLabel, QToolButton, QWidget

FIXED = ("back", "forward", "home", "reload")     # always at the start, in this order
_METRICS_EVENTS = tuple(e for e in (QEvent.Type.StyleChange, QEvent.Type.FontChange,
                                    getattr(QEvent.Type, "DevicePixelRatioChange", None)) if e is not None)
PINNED = ("menu",)                       # movable, but never hidden
LEFT, RIGHT = "left", "right"


def _keys(value):
    """A list of strings from a settings value, whatever was stored there."""
    if not isinstance(value, (list, tuple)):
        return []
    return [v for v in value if isinstance(v, str)]


class ToolbarLayout:
    """Where each movable button is: two ordered zones and the hidden keys.

    Every known key is in exactly one zone, hidden or not, so a button comes
    back where it was when it is shown again."""

    def __init__(self, keys, order=(), left=(), hidden=()):
        self.keys = tuple(keys)
        known = set(self.keys)
        seen, clean = set(), []
        for key in _keys(order):
            if key in known and key not in seen:
                seen.add(key)
                clean.append(key)
        for key in self.keys:                   # buttons the stored order does not know yet
            if key not in seen:
                seen.add(key)
                if clean and clean[-1] == "menu" and key != "menu":
                    clean.insert(len(clean) - 1, key)
                else:
                    clean.append(key)
        on_left = set(_keys(left))
        self.left = [k for k in clean if k in on_left]
        self.right = [k for k in clean if k not in on_left]
        self.hidden = {k for k in _keys(hidden) if k not in PINNED}

    @classmethod
    def from_config(cls, config, keys):
        return cls(keys, config.get("toolbar_order"), config.get("toolbar_left"),
                   config.get("toolbar_hidden"))

    def store(self, config):
        """Write the arrangement into the settings (the hidden keys are not changed here)."""
        config["toolbar_order"] = self.left + self.right
        config["toolbar_left"] = list(self.left)

    def zone(self, name):
        return self.left if name == LEFT else self.right

    def shown(self, name):
        return [k for k in self.zone(name) if k not in self.hidden]

    def zone_of(self, key):
        return LEFT if key in self.left else RIGHT

    def slot_of(self, key):
        """(zone, index among the shown buttons of the zone without key itself)."""
        name = self.zone_of(key)
        zone = self.zone(name)
        return name, sum(1 for k in zone[:zone.index(key)] if k not in self.hidden)

    def move(self, key, name, index):
        """Put key in a zone, before the shown button that is now at index
        there (counted without key itself); past the last one, at the end.
        True if the arrangement changed."""
        if key not in self.keys or name not in (LEFT, RIGHT):
            return False
        before = (list(self.left), list(self.right))
        for zone in (self.left, self.right):
            if key in zone:
                zone.remove(key)
        zone = self.zone(name)
        shown = [k for k in zone if k not in self.hidden]
        index = max(0, min(int(index), len(shown)))
        if index < len(shown):
            zone.insert(zone.index(shown[index]), key)
        elif shown:
            zone.insert(zone.index(shown[-1]) + 1, key)
        else:
            zone.append(key)
        return (self.left, self.right) != before


def default_layout(keys, defaults, items):
    """The arrangement of a new installation: the order and sides of the
    default settings, and the buttons that start hidden."""
    return ToolbarLayout(keys, defaults["toolbar_order"], defaults["toolbar_left"],
                         [key for key, hide in items if hide])


def spill(widths, room, keep=PINNED):
    """Keys of the buttons that do not fit in room pixels.

    widths: [(key, width)] of the buttons to show, left zone then right zone.
    The last buttons go first; the pinned ones always stay."""
    total = sum(w for _key, w in widths)
    out = []
    for key, width in reversed(widths):
        if total <= room:
            break
        if key in keep:
            continue
        out.append(key)
        total -= width
    return out


class _Overlay(QWidget):
    """Drawn over the toolbar while it is customised: an outline around each
    button that can be moved, and the marker of the place a dragged button
    would take. Hidden (and never painted) the rest of the time."""

    def __init__(self, toolbar):
        super().__init__(toolbar)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.outlines = []          # QRect, toolbar coordinates
        self.marker = None          # x of the drop marker, or None
        self.hide()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = self.palette()
        if self.outlines:
            colour = QColor(pal.color(QPalette.ColorRole.WindowText))
            colour.setAlphaF(0.45)
            pen = QPen(colour, 1, Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            for r in self.outlines:
                p.drawRoundedRect(QRectF(r).adjusted(0.5, 0.5, -0.5, -0.5), 4, 4)
        if self.marker is not None:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(pal.color(QPalette.ColorRole.Highlight))
            p.drawRoundedRect(QRectF(self.marker - 1.5, 3, 3, max(6, self.height() - 6)), 1.5, 1.5)
        p.end()


class ToolbarMover(QObject):
    """Moves the buttons of one window's toolbar with the mouse."""

    LONG_PRESS_MS = 800
    CANCEL_MARGIN = 48          # released this far above or below the toolbar: nothing moves

    def __init__(self, window):
        super().__init__(window)
        self.win = window
        self.nav = window.nav
        self.customising = False
        self.overlay = _Overlay(self.nav)
        self.nav.installEventFilter(self)
        self._buttons = {}          # key -> button, as last attached
        self._key = self._button = self._ghost = None
        self._armed = self._dragging = False
        self._press = QPoint()
        self._slot = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(self.LONG_PRESS_MS)
        self._timer.timeout.connect(self._long_pressed)

    # -- buttons -------------------------------------------------------
    def attach(self, key, button):
        """Called each time the toolbar has (re)built the button of key."""
        if not isinstance(button, QToolButton):
            return
        self._buttons[key] = button
        if button.property("ikeToolbarKey") != key:
            button.setProperty("ikeToolbarKey", key)
            button.setCursor(Qt.CursorShape.OpenHandCursor)
            button.installEventFilter(self)
            button.destroyed.connect(lambda _o=None, k=key, b=button: self._gone(k, b))

    def _gone(self, key, button):
        if self._buttons.get(key) is button:
            del self._buttons[key]
        if self._button is button:
            self._button = None
            self._finish()

    def button(self, key):
        return self._buttons.get(key)

    def _movable(self):
        """[(key, button)] of the buttons now shown, left to right."""
        layout, spilled = self.win.toolbar_layout, self.win.toolbar_spilled
        found = []
        for key in layout.shown(LEFT) + layout.shown(RIGHT):
            b = self._buttons.get(key)
            if b is not None and key not in spilled and b.isVisible():
                found.append((key, b))
        return found

    # -- customise mode ------------------------------------------------
    def set_customising(self, on):
        on = bool(on)
        if on == self.customising:
            return
        self._finish()
        self.customising = on
        self.refresh()

    def refresh(self):
        """Outlines and overlay after the toolbar or its mode changed."""
        ov = self.overlay
        ov.outlines = ([QRect(b.mapTo(self.nav, QPoint(0, 0)), b.size()) for _k, b in self._movable()]
                       if self.customising else [])
        if self.customising or self._dragging:
            ov.setGeometry(self.nav.rect())
            ov.show()
            ov.raise_()
            ov.update()
        else:
            ov.hide()

    # -- events --------------------------------------------------------
    def eventFilter(self, obj, event):
        kind = event.type()
        if obj is self.nav:
            if kind in (QEvent.Type.Resize, QEvent.Type.LayoutRequest) and self.overlay.isVisible():
                QTimer.singleShot(0, self.refresh)
            elif kind in _METRICS_EVENTS:
                # another style, font or screen scale: the buttons have another size
                QTimer.singleShot(0, self.win.toolbar_metrics_changed)
            return False
        key = obj.property("ikeToolbarKey")
        if not key:
            return False
        left = Qt.MouseButton.LeftButton
        if kind == QEvent.Type.MouseButtonPress and event.button() == left:
            self._finish()
            self._key, self._button = key, obj
            self._press = event.globalPosition().toPoint()
            if self.customising:
                self._armed = True
                return True                     # no click, no menu: the button is being arranged
            self._timer.start()
            return False
        if kind == QEvent.Type.MouseButtonDblClick and self.customising:
            return True
        if obj is not self._button:
            return False
        if kind == QEvent.Type.MouseMove and event.buttons() & left:
            if not self._armed:
                return False
            pos = event.globalPosition().toPoint()
            if not self._dragging:
                if (pos - self._press).manhattanLength() < QApplication.startDragDistance():
                    return True
                self._start_drag()
            self._drag_to(pos)
            return True
        if kind == QEvent.Type.MouseButtonRelease and event.button() == left:
            self._timer.stop()
            armed, dragging = self._armed, self._dragging
            if dragging:
                self._drop(event.globalPosition().toPoint())
            else:
                self._finish()
            return armed                        # an armed press never becomes a click
        return False

    def _long_pressed(self):
        b = self._button
        if b is None or not (QApplication.mouseButtons() & Qt.MouseButton.LeftButton or b.isDown()):
            return
        self._armed = True
        b.setDown(False)                        # releasing will not click
        b.setCursor(Qt.CursorShape.ClosedHandCursor)
        self.win.toolbar_hint(True)

    # -- dragging ------------------------------------------------------
    def _start_drag(self):
        b = self._button
        self._dragging = True
        b.setCursor(Qt.CursorShape.ClosedHandCursor)
        shot = b.grab()
        faded = QPixmap(shot.size())
        faded.setDevicePixelRatio(shot.devicePixelRatio())
        faded.fill(Qt.GlobalColor.transparent)
        p = QPainter(faded)
        p.setOpacity(0.75)
        p.drawPixmap(0, 0, shot)
        p.end()
        ghost = self._ghost = QLabel(self.nav)
        ghost.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        ghost.setPixmap(faded)
        ghost.resize(b.size())
        ghost.show()
        self.refresh()

    def slot_at(self, global_pos):
        """(zone, index, marker x) for a drop at this point, or None when it
        is too far from the toolbar (the drop is then cancelled)."""
        nav, layout = self.nav, self.win.toolbar_layout
        p = nav.mapFromGlobal(global_pos)
        if not -self.CANCEL_MARGIN <= p.y() <= nav.height() + self.CANCEL_MARGIN:
            return None
        ub = self.win.urlbar
        zone = LEFT if p.x() < ub.mapTo(nav, ub.rect().center()).x() else RIGHT
        rects, spilled = [], self.win.toolbar_spilled
        for key in layout.shown(zone):
            b = self._buttons.get(key)
            if key != self._key and key not in spilled and b is not None and b.isVisible():
                rects.append(QRect(b.mapTo(nav, QPoint(0, 0)), b.size()))
        index = sum(1 for r in rects if p.x() > r.center().x())
        own = self._button
        if own is not None and (zone, index) == layout.slot_of(self._key):
            x = own.mapTo(nav, QPoint(0, 0)).x() - 1           # where it already is
        elif index < len(rects):
            x = rects[index].left() - 1
        elif rects:
            x = rects[-1].right() + 2
        else:
            x = self.win.toolbar_zone_start(zone)
        return zone, index, x

    def _drag_to(self, global_pos):
        slot = self._slot = self.slot_at(global_pos)
        ghost, nav = self._ghost, self.nav
        if ghost is not None and self._button is not None:
            x = nav.mapFromGlobal(global_pos).x() - ghost.width() // 2
            x = max(0, min(x, nav.width() - ghost.width()))
            ghost.move(x, self._button.mapTo(nav, QPoint(0, 0)).y())
            ghost.raise_()
        marker = slot[2] if slot else None
        if marker != self.overlay.marker:
            self.overlay.marker = marker
            self.overlay.update()

    def _drop(self, global_pos):
        key, slot = self._key, self.slot_at(global_pos)
        self._finish()
        if key is None or slot is None:
            return
        if self.win.toolbar_layout.move(key, slot[0], slot[1]):
            self.win.toolbar_layout_changed()

    def _finish(self):
        """End a press or a drag and remove what it showed."""
        self._timer.stop()
        was_armed = self._armed
        b = self._button
        self._key = self._button = self._slot = None
        self._armed = self._dragging = False
        if self._ghost is not None:
            self._ghost.hide()
            self._ghost.deleteLater()
            self._ghost = None
        self.overlay.marker = None
        if b is not None:
            try:
                if was_armed:
                    b.setDown(False)            # (an ordinary click is left to the button itself)
                b.setCursor(Qt.CursorShape.OpenHandCursor)
            except RuntimeError:                # the toolbar rebuilt the button meanwhile
                pass
        if was_armed:
            self.win.toolbar_hint(False)
        self.refresh()
