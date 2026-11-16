"""What differs between Linux and Windows: folders, the identity presented to
websites, desktop notifications.

On Linux everything is exactly as before 1.6.0. On Windows I.K.E. keeps its
settings in %APPDATA%\\ike-browser and its data and cache in
%LOCALAPPDATA%\\ike-browser, and presents itself to websites as an ordinary
Chrome for Windows: claiming Linux on a Windows computer would make it stand
out (fonts, graphics and timings tell the real system).

The XDG_* variables are honoured on Windows too when they are set (the
automatic tests use them to give each run an empty profile).
"""

import os
import sys
from pathlib import Path

WINDOWS = sys.platform == "win32"
APP_ID = "ike-browser"

_XDG = {"config": ("XDG_CONFIG_HOME", ".config"),
        "data": ("XDG_DATA_HOME", ".local/share"),
        "cache": ("XDG_CACHE_HOME", ".cache")}


def app_dir(kind, windows=None):
    """I.K.E.'s own folder of a kind: "config", "data" or "cache"."""
    var, default = _XDG[kind]
    if os.environ.get(var):
        return Path(os.environ[var]) / APP_ID
    if WINDOWS if windows is None else windows:
        roaming = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        if kind == "config":
            return Path(roaming) / APP_ID
        if kind == "cache":
            return Path(local) / APP_ID / "cache"
        return Path(local) / APP_ID
    return Path.home() / default / APP_ID


# ---- identity presented to websites ----------------------------------------
# Common values of the system I.K.E. runs on, never the computer's own ones.

def identity(windows=None):
    """Strings that name the operating system in requests and scripts."""
    if WINDOWS if windows is None else windows:
        return {
            "os": "windows",
            "ua_os": "Windows NT 10.0; Win64; x64",
            "platform": "Windows",
            # Windows 11 24H2 / 25H2, the most common version today
            "platform_version": "19.0.0",
            "firefox_ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:140.0) "
                          "Gecko/20100101 Firefox/140.0",
            "firefox_app_version": "5.0 (Windows)",
            "firefox_oscpu": "Windows NT 10.0; Win64; x64",
            "chrome_versions": "win64",
        }
    return {
        "os": "linux",
        "ua_os": "X11; Linux x86_64",
        "platform": "Linux",
        "platform_version": "6.0.0",
        "firefox_ua": "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0",
        "firefox_app_version": "5.0 (X11)",
        "firefox_oscpu": "Linux x86_64",
        "chrome_versions": "linux",
    }


def chrome_user_agent(major, windows=None):
    return ("Mozilla/5.0 (%s) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/%s.0.0.0 Safari/537.36" % (identity(windows)["ua_os"], major))


# ---- desktop notifications ---------------------------------------------------
_tray = None


def notify(title, text):
    """A desktop notification: notify-send on Linux, a Windows notification
    (through Qt's system tray icon, shown only while needed) on Windows."""
    if not WINDOWS:
        import subprocess
        try:
            subprocess.Popen(["notify-send", "-a", "I.K.E.", "-i", "ike-browser", title, text])
        except OSError:
            pass
        return
    global _tray
    try:
        from PyQt6.QtCore import QTimer
        from PyQt6.QtWidgets import QApplication, QSystemTrayIcon
        app = QApplication.instance()
        if app is None or not QSystemTrayIcon.isSystemTrayAvailable():
            return
        if _tray is None:
            _tray = QSystemTrayIcon(app.windowIcon(), app)
            _tray.setToolTip("I.K.E.")
            _tray._hide = QTimer(app, singleShot=True, interval=20000)
            _tray._hide.timeout.connect(_tray.hide)

            def raise_window():
                w = app.activeWindow() or next((t for t in app.topLevelWidgets()
                                                if t.isVisible() and t.isWindow()), None)
                if w is not None:
                    if w.isMinimized():
                        w.showNormal()
                    w.raise_()
                    w.activateWindow()
            _tray.messageClicked.connect(raise_window)
        _tray.show()
        _tray.showMessage(title, text, app.windowIcon(), 8000)
        _tray._hide.start()
    except Exception:
        pass
