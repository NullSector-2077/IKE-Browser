"""The password vault locks itself (Unreleased; Passwords window).

The vault opened with the master password stays open while it is used. It
locks itself, and asks for the master password at its next use:

- after `pw_lock_minutes` minutes in which I.K.E. was not used (no key
  pressed, no click, no wheel turn, no touch in any of its windows; 0 = never,
  the behaviour of 1.1.30 and earlier);
- when the desktop locks the screen or the screen saver starts
  (`ActiveChanged(true)` of org.freedesktop.ScreenSaver, KDE Plasma's and
  others', or of org.gnome.ScreenSaver, on the session bus), and when the
  computer goes to sleep (`PrepareForSleep(true)` of systemd-logind on the
  system bus), if `pw_lock_screen` is on (the default).

Nothing runs while the vault is locked: the watch of the input and the
one-minute check start when it opens and stop when it locks. The input is
only timed (which key or where is never looked at). A message on the bus can
only lock the vault, never open it, so whoever sends one gains nothing.
Without QtDBus or a bus, only the time limit applies.
"""

import time

from PyQt6.QtCore import QEvent, QObject, QTimer, pyqtSlot

try:
    from PyQt6.QtDBus import QDBusConnection, QDBusMessage
    DBUS = True
except ImportError:                     # PyQt6 built without QtDBus
    QDBusMessage = object
    DBUS = False

CHOICES = (0, 5, 15, 30, 60)            # minutes offered in the Passwords window (0 = never)
DEFAULT_MINUTES = 15
CHECK_MS = 60_000

_INPUT = frozenset((QEvent.Type.KeyPress, QEvent.Type.MouseButtonPress, QEvent.Type.Wheel,
                    QEvent.Type.TouchBegin, QEvent.Type.TabletPress))

# (bus, path, interface, signal): each says "the screen is locked / asleep" with a true argument
_SESSION_SIGNALS = (
    ("/ScreenSaver", "org.freedesktop.ScreenSaver", "ActiveChanged"),
    ("/org/freedesktop/ScreenSaver", "org.freedesktop.ScreenSaver", "ActiveChanged"),
    ("/org/gnome/ScreenSaver", "org.gnome.ScreenSaver", "ActiveChanged"),
)
_SYSTEM_SIGNALS = (
    ("/org/freedesktop/login1", "org.freedesktop.login1.Manager", "PrepareForSleep"),
)


def minutes_of(cfg):
    """The chosen time limit in minutes (0 = never); anything odd is the default."""
    try:
        m = int(cfg.get("pw_lock_minutes", DEFAULT_MINUTES))
    except (TypeError, ValueError):
        return DEFAULT_MINUTES
    return m if m in CHOICES else DEFAULT_MINUTES


class VaultLock(QObject):
    """Watches the open vault of `manager` (passwords.PasswordManager)."""

    def __init__(self, manager, app):
        super().__init__(manager)
        self.manager = manager
        self.app = app
        self.last_input = time.monotonic()
        self._watching = False
        self._timer = QTimer(self)
        self._timer.setInterval(CHECK_MS)
        self._timer.timeout.connect(self.check)
        self._bus_done = False
        self.bus_links = 0               # how many of the signals above are followed (tests, About)

    # --- the vault opened and closed --------------------------------------
    def opened(self):
        """The vault was opened (or created): start watching."""
        self.last_input = time.monotonic()
        self._listen_bus()
        if minutes_of(self.app.config) and not self._watching:
            from PyQt6.QtWidgets import QApplication
            QApplication.instance().installEventFilter(self)
            self._watching = True
            self._timer.start()

    def closed(self):
        """The vault was locked: stop watching (nothing runs while it is locked)."""
        if self._watching:
            from PyQt6.QtWidgets import QApplication
            QApplication.instance().removeEventFilter(self)
            self._watching = False
        self._timer.stop()

    def changed(self):
        """The time limit was changed in the Passwords window."""
        if self.manager.vault.unlocked:
            self.closed()
            self.opened()

    # --- the time limit ------------------------------------------------------
    def eventFilter(self, _obj, event):
        if event.type() in _INPUT:
            self.last_input = time.monotonic()
        return False

    def check(self, now=None):
        """Lock when I.K.E. was not used for the chosen minutes; True when it locked."""
        minutes = minutes_of(self.app.config)
        if not minutes or not self.manager.vault.unlocked:
            if not self.manager.vault.unlocked:
                self.closed()
            return False
        now = time.monotonic() if now is None else now
        if now - self.last_input >= minutes * 60:
            self.manager.lock_vault("idle")
            return True
        return False

    # --- the screen locked, the computer asleep --------------------------------
    def _listen_bus(self):
        if self._bus_done or not DBUS:
            return
        self._bus_done = True
        for bus, signals in ((QDBusConnection.sessionBus(), _SESSION_SIGNALS),
                             (QDBusConnection.systemBus(), _SYSTEM_SIGNALS)):
            if not bus.isConnected():
                continue
            for path, iface, name in signals:
                # any sender: a message can only lock the vault
                if bus.connect("", path, iface, name, self._signal):
                    self.bus_links += 1

    @pyqtSlot(QDBusMessage)
    def _signal(self, msg):
        args = msg.arguments()
        if args and args[0] is True:
            self.screen_locked()

    def screen_locked(self):
        """The desktop locked the screen or the computer goes to sleep."""
        if self.app.config.get("pw_lock_screen", True) and self.manager.vault.unlocked:
            self.manager.lock_vault("screen")
