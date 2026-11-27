"""Operating-system details: I.K.E.'s folders, the identity presented to
websites, desktop notifications.

Folders follow the XDG base directories (~/.config, ~/.local/share, ~/.cache);
the XDG_* variables, when set, are honoured (the automatic tests use them to
give each run an empty profile).
"""

import os
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

# The Firefox presented to Google's sites (1.1.27): a current release, estimated
# from the calendar (nothing is fetched). Until 1.1.26 it was a fixed Firefox
# 140, more than a year old by then, and Google's sign-in refused it as an
# out-of-date browser ("this browser may not be secure"). A release known for
# certain, and the longest a Firefox release has taken since: the estimate can
# fall a version behind, never ahead of a release that does not exist yet.
FIREFOX_ANCHOR, FIREFOX_ANCHOR_DAY = 161, (2026, 11, 24)
FIREFOX_SLOWEST_DAYS = 28


def firefox_major(today=None):
    """The current Firefox release (161, ...), estimated from the calendar."""
    from datetime import date
    today = today or date.today()
    days = (today - date(*FIREFOX_ANCHOR_DAY)).days
    return FIREFOX_ANCHOR + max(0, days) // FIREFOX_SLOWEST_DAYS


def firefox_user_agent(major=None):
    major = major or firefox_major()
    return "Mozilla/5.0 (X11; Linux x86_64; rv:%d.0) Gecko/20100101 Firefox/%d.0" % (major, major)


def identity():
    """Strings that name the operating system in requests and scripts."""
    return {
        "os": "linux",
        "ua_os": "X11; Linux x86_64",
        "platform": "Linux",
        # empty, as the engine itself reduces it (1.1.25: ReduceUserAgentData-
        # LinuxPlatformVersion, app.PRIVACY_FEATURES): service and shared
        # workers get the engine's value, never the profile's, and gave the
        # real kernel version ("6.18.44") where the page said "6.0.0"
        "platform_version": "",
        "firefox_ua": firefox_user_agent(),
        "firefox_app_version": "5.0 (X11)",
        "firefox_oscpu": "Linux x86_64",
        "chrome_versions": "linux",
    }


def browser_user_agent():
    """The User-Agent of the pages, for every request of I.K.E. itself (filter
    lists, updates, version check): a label of its own told each server it
    was I.K.E. (review of 1.1.19, L3)."""
    from . import chromever
    return chrome_user_agent(chromever.engine_major())


def chrome_user_agent(major):
    return ("Mozilla/5.0 (%s) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/%s.0.0.0 Safari/537.36" % (identity()["ua_os"], major))


# ---- desktop notifications ---------------------------------------------------

def notify(title, text):
    """A desktop notification: a call to org.freedesktop.Notifications.Notify
    on the session bus (QtDBus), with no program started.

    Title and text can come from a web page; they travel as D-Bus strings,
    never as program options, and the text is escaped because notification
    services show it as markup (links and pictures included). The call is
    not waited for; with no session bus or no service nothing happens."""
    import html
    try:
        from PyQt6.QtCore import QMetaType
        from PyQt6.QtDBus import QDBusArgument, QDBusConnection, QDBusMessage
        bus = QDBusConnection.sessionBus()
        if not bus.isConnected():
            return
        msg = QDBusMessage.createMethodCall("org.freedesktop.Notifications", "/org/freedesktop/Notifications",
                                            "org.freedesktop.Notifications", "Notify")
        # Notify(s app_name, u replaces_id, s app_icon, s summary, s body, as actions, a{sv} hints,
        # i expire_timeout): the types are set explicitly, a bare Python int or list would be sent as i and av
        def typed(value, kind):
            arg = QDBusArgument()
            arg.add(value, kind.value)
            return arg
        hints = QDBusArgument()                  # a{sv}, empty
        hints.beginMap(QMetaType.Type.QString.value, QMetaType.fromName(b"QDBusVariant").id())
        hints.endMap()
        msg.setArguments(["I.K.E.", typed(0, QMetaType.Type.UInt), APP_ID, str(title)[:200].replace("\0", "") or " ",
                          html.escape(str(text)[:2000].replace("\0", ""), quote=False),
                          typed([], QMetaType.Type.QStringList), hints, -1])
        bus.asyncCall(msg)
    except Exception:
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
