"""Battery saver (1.1.24, opt-in, off by default; Settings -> System).

While the computer runs on battery and the user turned the saver on:

- tabs in the background that have been left alone for BACKGROUND_S seconds
  and play no sound are frozen (their timers and scripts stop; the engine's
  own throttling of hidden tabs goes further); they wake when shown, or when
  the computer is plugged in again;
- the interface's extra animations stop (as with Settings -> Appearance ->
  effects off), and the small pictures of the tabs for the preview cards are
  not taken (the cards show the last one, or none).

Whether the computer is on battery comes from UPower over the system bus
(QtDBus, part of PyQt6: nothing to install). It is asked once, then UPower's
own signal says when it changes: nothing is polled. Without UPower or a
system bus the saver simply never starts. With the saver off nothing
connects to the bus at all.
"""

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

try:
    from PyQt6.QtDBus import QDBusConnection, QDBusMessage
    AVAILABLE = True
except ImportError:                     # PyQt6 built without QtDBus
    QDBusMessage = object
    AVAILABLE = False

SERVICE = "org.freedesktop.UPower"
PATH = "/org/freedesktop/UPower"
IFACE = "org.freedesktop.UPower"
PROPS = "org.freedesktop.DBus.Properties"
BACKGROUND_S = 60

_state = {"saving": False}


def saving():
    """Is the battery saver working now (on battery, and chosen)?"""
    return _state["saving"]


def _plain(value):
    """A D-Bus variant as a Python value."""
    variant = getattr(value, "variant", None)
    return variant() if callable(variant) else value


class Battery(QObject):
    changed = pyqtSignal(bool)          # saving() changed

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.on_battery = False
        self.connected = False
        self._bus = None

    def wanted(self):
        return bool(self.app.config.get("battery_saver"))

    def start(self):
        """Follow UPower when the saver is chosen (again after a change of the setting)."""
        if self.wanted() and not self.connected:
            self._connect()
        self._update()

    def _connect(self):
        if not AVAILABLE:
            return False
        bus = QDBusConnection.systemBus()
        if not bus.isConnected():
            return False
        self._bus = bus
        self.connected = bus.connect(SERVICE, PATH, PROPS, "PropertiesChanged", self._props)
        ask = QDBusMessage.createMethodCall(SERVICE, PATH, PROPS, "Get")
        ask.setArguments([IFACE, "OnBattery"])
        bus.callWithCallback(ask, self._got, self._failed)
        return self.connected

    @pyqtSlot(QDBusMessage)
    def _got(self, msg):
        args = msg.arguments()
        if args:
            self.on_battery = bool(_plain(args[0]))
            self._update()

    @pyqtSlot(QDBusMessage)
    def _failed(self, _msg):
        pass                            # no UPower: never on battery

    @pyqtSlot(QDBusMessage)
    def _props(self, msg):
        args = msg.arguments()
        if len(args) < 2 or args[0] != IFACE:
            return
        changed = args[1] if isinstance(args[1], dict) else {}
        if "OnBattery" in changed:
            self.on_battery = bool(_plain(changed["OnBattery"]))
            self._update()

    def set_on_battery(self, on):
        """What UPower says (also for the tests)."""
        self.on_battery = bool(on)
        self._update()

    def _update(self):
        now = self.wanted() and self.on_battery
        if now == _state["saving"]:
            return
        _state["saving"] = now
        self.changed.emit(now)
        if now:
            self.rest()
        else:
            self.wake_all()

    # --- background tabs ------------------------------------------------------
    def rest(self, now=None):
        """Freeze the background tabs left alone for BACKGROUND_S seconds (no sound)."""
        if not saving():
            return 0
        import time

        from PyQt6.QtWebEngineCore import QWebEnginePage
        now = time.time() if now is None else now
        n = 0
        for w in list(getattr(self.app, "windows", [])):
            shown = {w.current_view(), getattr(w, "split", None)} if w.isVisible() and not w.isMinimized() \
                else set()
            for v in w.all_views():
                if (v in shown or getattr(v, "sleeping", False) or getattr(v, "frozen", False)
                        or getattr(v, "pending_url", None) or getattr(v, "loading", False)
                        or now - getattr(v, "last_active", now) < BACKGROUND_S):
                    continue
                page = v.page()
                try:
                    if (page.recentlyAudible()
                            or page.recommendedState() == QWebEnginePage.LifecycleState.Active):
                        continue        # sound, a capture, its devices: left running
                except RuntimeError:
                    continue
                if self.app.resources.freeze(v):
                    v.battery_frozen = True
                    n += 1
        return n

    def wake_all(self):
        """Plugged in again (or the saver turned off): the tabs it froze run again."""
        n = 0
        for w in list(getattr(self.app, "windows", [])):
            for v in w.all_views():
                if getattr(v, "battery_frozen", False):
                    v.battery_frozen = False
                    self.app.resources.wake(v)
                    n += 1
        return n
