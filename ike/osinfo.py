"""Operating-system details: I.K.E.'s folders, the identity presented to
websites, desktop notifications.

Folders follow the XDG base directories (~/.config, ~/.local/share, ~/.cache);
the XDG_* variables, when set, are honoured (the automatic tests use them to
give each run an empty profile). On Windows, where those variables are
normally not set, the folders are the user's own application-data folders:
settings in the "ike-browser" folder of %APPDATA%, everything else in the
"ike-browser" folder of %LOCALAPPDATA% (sub-folders "data" and "cache").
"""

import ntpath
import os
import subprocess
import sys
from pathlib import Path

APP_ID = "ike-browser"
WINDOWS = sys.platform == "win32"

_XDG = {"config": ("XDG_CONFIG_HOME", ".config"),
        "data": ("XDG_DATA_HOME", ".local/share"),
        "cache": ("XDG_CACHE_HOME", ".cache")}
# Windows: (variable, the folder it names in a user's profile, sub-folder)
_WIN = {"config": ("APPDATA", "AppData/Roaming", ""),
        "data": ("LOCALAPPDATA", "AppData/Local", "data"),
        "cache": ("LOCALAPPDATA", "AppData/Local", "cache")}


def windows_dir(kind, environ=None, home=None):
    """The folder of a kind on Windows (ike_boot.py computes "data" the same
    way: tests/test_platform.py compares them)."""
    environ = os.environ if environ is None else environ
    var, default, sub = _WIN[kind]
    base = environ.get(var) or ""
    # a relative value would depend on the folder the program was started from
    absolute = os.path.isabs(base) or ntpath.isabs(base)
    root = Path(base) if absolute else Path(home or Path.home()) / default
    return root / APP_ID / sub if sub else root / APP_ID


def app_dir(kind):
    """I.K.E.'s own folder of a kind: "config", "data" or "cache"."""
    var, default = _XDG[kind]
    if os.environ.get(var):
        return Path(os.environ[var]) / APP_ID
    if WINDOWS:
        return windows_dir(kind)
    return Path.home() / default / APP_ID


# ---- identity presented to websites ----------------------------------------
# Common values of a computer with this operating system, never the
# computer's own ones: what Chrome itself says there.

_LINUX = {
    "os": "linux",
    "ua_os": "X11; Linux x86_64",
    "platform": "Linux",
    "platform_version": "6.0.0",
    "navigator_platform": "Linux x86_64",
    "firefox_ua": "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0",
    "firefox_app_version": "5.0 (X11)",
    "firefox_oscpu": "Linux x86_64",
    "chrome_versions": "linux",
}
# Chrome on Windows names "Windows NT 10.0" on Windows 10 and on Windows 11
# alike; the two differ only in the platform version of the client hints.
_WINDOWS = {
    "os": "windows",
    "ua_os": "Windows NT 10.0; Win64; x64",
    "platform": "Windows",
    "platform_version": "19.0.0",
    "navigator_platform": "Win32",
    "firefox_ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:140.0) Gecko/20100101 Firefox/140.0",
    "firefox_app_version": "5.0 (Windows)",
    "firefox_oscpu": "Windows NT 10.0; Win64; x64",
    "chrome_versions": "win64",
}
# First build of Windows 11; Chrome reports platform version 10.0.0 below it.
_WINDOWS_11_BUILD = 22000


def windows_platform_version(build):
    """What Chrome's client hints name as the platform version: one value for
    Windows 10 and one for Windows 11 (the one of its current releases),
    whatever the exact build of this computer is."""
    return "19.0.0" if build >= _WINDOWS_11_BUILD else "10.0.0"


def identity(platform=None, windows_build=None):
    """Strings that name the operating system in requests and scripts.

    The arguments are for the automatic tests; a normal call describes the
    system I.K.E. runs on."""
    if (platform or sys.platform) != "win32":
        return dict(_LINUX)
    ident = dict(_WINDOWS)
    if windows_build is None:
        try:
            windows_build = sys.getwindowsversion().build
        except AttributeError:
            windows_build = _WINDOWS_11_BUILD
    ident["platform_version"] = windows_platform_version(windows_build)
    return ident


def chrome_user_agent(major):
    return ("Mozilla/5.0 (%s) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/%s.0.0.0 Safari/537.36" % (identity()["ua_os"], major))


# ---- desktop notifications ---------------------------------------------------

def notify(title, text):
    """A desktop notification: through notify-send, on Windows through Qt
    (the notification area).

    Title and text can come from a web page: "--" keeps them from being read
    as options of notify-send, and the text is escaped because notification
    services show it as markup (links and pictures included)."""
    if WINDOWS:
        return notify_tray(title, text)
    import html
    try:
        subprocess.Popen(["notify-send", "-a", "I.K.E.", "-i", "ike-browser", "--",
                          str(title)[:200] or " ", html.escape(str(text)[:2000], quote=False)])
    except (OSError, ValueError):
        pass


_tray = {}
TRAY_TITLE_MAX, TRAY_TEXT_MAX = 63, 255      # what Windows shows of a notification


def tray_texts(title, text):
    """Title and text as Windows can show them: plain text (Windows shows no
    markup there, so nothing is escaped), without control characters, cut to
    the lengths of its notification."""
    def plain(value, limit):
        value = "".join(ch if ch.isprintable() else " " for ch in str(value))
        return " ".join(value.split())[:limit]
    return plain(title, TRAY_TITLE_MAX) or "I.K.E.", plain(text, TRAY_TEXT_MAX)


def notify_tray(title, text):
    """A notification through Qt's QSystemTrayIcon: I.K.E.'s icon appears in
    the notification area while the message is shown and leaves afterwards.
    Returns False when there is nothing to show it with (no application
    object, no notification area)."""
    try:
        from PyQt6.QtCore import QTimer
        from PyQt6.QtWidgets import QApplication, QSystemTrayIcon
        app = QApplication.instance()
        if app is None or not QSystemTrayIcon.isSystemTrayAvailable() \
                or not QSystemTrayIcon.supportsMessages():
            return False
        if "icon" not in _tray:
            _tray["icon"] = QSystemTrayIcon(app.windowIcon(), app)
            _tray["icon"].setToolTip("I.K.E.")
            _tray["hide"] = QTimer(app)
            _tray["hide"].setSingleShot(True)
            _tray["hide"].setInterval(20000)
            _tray["hide"].timeout.connect(_tray["icon"].hide)
        title, text = tray_texts(title, text)
        _tray["icon"].show()
        _tray["icon"].showMessage(title, text, app.windowIcon(), 10000)
        _tray["hide"].start()
        return True
    except (ImportError, RuntimeError):
        return False


# ---- automatic tests ---------------------------------------------------------

def test_switch(name):
    """Value of a switch of the automatic tests (IKE_TEST_...), or "".

    The switches that turn a protection off (accept any certificate, answer
    permission requests without asking) only count in a test session, which
    is one started with a test script (IKE_TEST_HOOK); set alone in the
    environment of a normal start they do nothing."""
    if not os.environ.get("IKE_TEST_HOOK"):
        return ""
    return os.environ.get(name, "")
