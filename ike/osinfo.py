"""Operating-system details: I.K.E.'s folders, the identity presented to
websites, desktop notifications.

Folders follow the XDG base directories (~/.config, ~/.local/share, ~/.cache);
the XDG_* variables, when set, are honoured (the automatic tests use them to
give each run an empty profile).
"""

import os
import re
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


# Flatpak writes this file into every sandbox it starts, and sets FLATPAK_ID.
FLATPAK_INFO = "/.flatpak-info"


def in_flatpak():
    """True inside a Flatpak sandbox: the program folder is read-only there and
    new versions come from Flatpak (Flathub), never from I.K.E.'s own updater."""
    return os.path.exists(FLATPAK_INFO) or bool(os.environ.get("FLATPAK_ID"))


def desktop_id():
    """Name of I.K.E.'s desktop entry and icon on the desktop: inside a Flatpak
    the application ID (Flatpak exports those files under that name), and
    "ike-browser" everywhere else."""
    fid = os.environ.get("FLATPAK_ID", "")
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*(\.[A-Za-z0-9_-]+)+", fid):
        return fid
    return APP_ID


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
    """A desktop notification through notify-send.

    Title and text can come from a web page: "--" keeps them from being read
    as options of notify-send, and the text is escaped because notification
    services show it as markup (links and pictures included)."""
    import html
    try:
        subprocess.Popen(["notify-send", "-a", "I.K.E.", "-i", desktop_id(), "--",
                          str(title)[:200] or " ", html.escape(str(text)[:2000], quote=False)])
    except (OSError, ValueError):
        pass


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
