"""The protected time zone (1.1.24, opt-in, off by default).

With it on, every page sees the time zone UTC: dates, ``getTimezoneOffset()``,
``Intl.DateTimeFormat().resolvedOptions().timeZone``, frames and every kind of
worker (those a site starts from a file of its own too) all agree, because it
is the engine itself that runs in UTC. A script that rewrote the date
functions of each page could be caught by the details it gets wrong (parsing,
the names of the zones, the workers it cannot reach) and would slow every
page down; this costs nothing while pages run.

How: the engine's page processes take the time zone from the environment of
the process that starts them, once, when the engine starts. I.K.E. sets
``TZ=UTC`` just before the engine starts and gives itself its own time back
right after (its menus, history and downloads keep the user's local time).
Back on I.K.E.'s side ``TZ`` stays set (to the user's own zone): the engine
then never watches the system's time-zone files, so a change of the
computer's zone while I.K.E. runs cannot reach the pages either. A change of
the setting applies at the next start.

I.K.E.'s own new tab page shows the clock in the user's real zone
(``real_zone()``, passed to the page as a name).
"""

import os
import time
from pathlib import Path

ZONE = "UTC"
# the user's own TZ while the engine starts with ZONE: None = not changed
_saved = {}


def apply(config, environ=None):
    """Before the engine starts: the pages' time zone as chosen. Returns True
    when it was set to ZONE."""
    environ = os.environ if environ is None else environ
    if not config.get("protect_timezone"):
        return False
    _saved["tz"] = environ.get("TZ")
    _saved["zone"] = real_zone(environ)
    environ["TZ"] = ZONE
    _tzset(environ)
    return True


def restore(environ=None):
    """After the engine has started: I.K.E. itself in the user's own zone again.
    TZ keeps a value (":/etc/localtime", the system's own zone, when there was
    none), so the engine does not follow the system's files for its pages."""
    environ = os.environ if environ is None else environ
    if "tz" not in _saved:
        return False
    old = _saved.pop("tz")
    environ["TZ"] = old if old else ":/etc/localtime"
    _tzset(environ)
    return True


def active():
    """Do the pages of this session see ZONE?"""
    return "zone" in _saved


def _tzset(environ):
    if environ is os.environ and hasattr(time, "tzset"):
        time.tzset()


def real_zone(environ=None, localtime="/etc/localtime"):
    """The user's own zone as an IANA name ("Europe/Rome"), or "" when it
    cannot be told. Remembered once the engine runs in ZONE."""
    environ = os.environ if environ is None else environ
    if "zone" in _saved:
        return _saved["zone"]
    tz = (environ.get("TZ") or "").strip()
    if tz.startswith(":"):
        tz = tz[1:]
    if tz and tz != ZONE and not tz.startswith("/"):
        return tz if _plain(tz) else ""
    path = Path(tz) if tz.startswith("/") else Path(localtime)
    try:
        target = str(path.resolve())
    except OSError:
        return ""
    marker = "/zoneinfo/"
    if marker in target:
        name = target.split(marker, 1)[1]
        for prefix in ("posix/", "right/"):
            if name.startswith(prefix):
                name = name[len(prefix):]
        return name if _plain(name) else ""
    try:
        name = Path("/etc/timezone").read_text("utf-8").strip()     # older systems
    except OSError:
        return ""
    return name if _plain(name) else ""


def _plain(name):
    """An IANA zone name such as "America/Argentina/Buenos_Aires", nothing else
    (it goes into I.K.E.'s own new tab page)."""
    import re
    return bool(re.fullmatch(r"[A-Za-z][A-Za-z0-9_+\-]*(/[A-Za-z0-9_+\-]+){0,2}", name or ""))
