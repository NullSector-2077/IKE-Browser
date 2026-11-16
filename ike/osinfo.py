"""Operating-system details: I.K.E.'s folders, the identity presented to
websites, desktop notifications.

Folders follow the XDG base directories (~/.config, ~/.local/share, ~/.cache);
the XDG_* variables, when set, are honoured (the automatic tests use them to
give each run an empty profile).
"""

import os
import subprocess
from pathlib import Path

APP_ID = "ike-browser"

_XDG = {"config": ("XDG_CONFIG_HOME", ".config"),
        "data": ("XDG_DATA_HOME", ".local/share"),
        "cache": ("XDG_CACHE_HOME", ".cache")}


def app_dir(kind):
    """I.K.E.'s own folder of a kind: "config", "data" or "cache"."""
    var, default = _XDG[kind]
    if os.environ.get(var):
        return Path(os.environ[var]) / APP_ID
    return Path.home() / default / APP_ID


# ---- identity presented to websites ----------------------------------------
# Common values of a Linux computer, never the computer's own ones.

def identity():
    """Strings that name the operating system in requests and scripts."""
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


def chrome_user_agent(major):
    return ("Mozilla/5.0 (%s) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/%s.0.0.0 Safari/537.36" % (identity()["ua_os"], major))


# ---- desktop notifications ---------------------------------------------------

def notify(title, text):
    """A desktop notification through notify-send."""
    try:
        subprocess.Popen(["notify-send", "-a", "I.K.E.", "-i", "ike-browser", title, text])
    except OSError:
        pass
