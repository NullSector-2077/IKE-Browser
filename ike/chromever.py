"""The Chrome version I.K.E. presents to websites, and how old its engine is.

I.K.E. presents the version of its own engine (1.1.14). Until 1.1.13 it
presented the current stable Chrome while the engine inside Qt is some versions
behind: a site can test which features the engine really has, so the claim was
easy to catch, and anti-abuse checks treat a browser that says one version and
behaves like another as suspicious. The real version is consistent everywhere
(header, client hints, JavaScript) and follows the engine when Arch updates it.

The current stable Chrome is still learned once a day from Google's public
version list (no personal data is sent; estimated from the calendar when that
cannot be reached), only to show in Help -> About how far behind the engine is.
"""

import json
import time
import urllib.request
from datetime import date

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWebEngineCore import qWebEngineChromiumVersion

from . import osinfo
from .osinfo import identity

URL = ("https://versionhistory.googleapis.com/v1/chrome/platforms/%s/channels/stable/versions"
       % identity()["chrome_versions"])
CHECK_INTERVAL = 20 * 3600
# A stable release that is known for certain, to estimate from.
ANCHOR_MAJOR, ANCHOR_DAY = 157, date(2026, 11, 3)
# Chrome has never released faster than this, nor slower than that.
FASTEST_DAYS, SLOWEST_DAYS = 13, 28


def engine_major():
    try:
        return int(qWebEngineChromiumVersion().split(".")[0])
    except (ValueError, IndexError):
        return ANCHOR_MAJOR


def engine_full():
    """The engine's full version ("140.0.7339.207"), or major.0.0.0."""
    v = (qWebEngineChromiumVersion() or "").strip()
    parts = v.split(".")
    if len(parts) == 4 and all(p.isdigit() for p in parts):
        return v
    return "%d.0.0.0" % engine_major()


def security_major():
    """The Chrome version up to which the engine has its security fixes.

    Qt WebEngine is built on an older Chromium and gets the security fixes of
    newer ones backported: those, not the Chromium version, say whether the
    engine is still protected. Falls back to the Chromium version."""
    try:
        from PyQt6.QtWebEngineCore import qWebEngineChromiumSecurityPatchVersion
        return int(qWebEngineChromiumSecurityPatchVersion().split(".")[0])
    except (ImportError, ValueError, IndexError, AttributeError):
        return engine_major()


# Chrome ships a new version about every four weeks, and Qt WebEngine brings
# the security fixes of the newest ones into its own releases
# (qWebEngineChromiumSecurityPatchVersion: Qt 6.12.0 came with those of
# Chrome 157, the current one then). Qt's patch releases come every six to
# nine weeks, so an up-to-date Arch system is often two versions behind for a
# while (Qt 6.8.0, 8 October 2024, had the fixes of Chrome 129; Chrome 131 came
# on 12 November, Qt 6.8.1 on 2 December): at two the notice would come with
# nothing the user can do. Three versions behind means the system has missed
# a Qt update: the user is told (1.1.18, security audit F4 and the adversarial
# review; it was 5).
OUTDATED_AFTER = 3


def security_behind(config, today=None):
    """How many Chrome versions the engine's security fixes are behind."""
    return max(0, latest(config, today) - security_major())


def _since_anchor(today=None):
    return max(0, ((today or date.today()) - ANCHOR_DAY).days)


def estimate(today=None):
    """A version that certainly exists by now (it may lag, it is never ahead)."""
    return max(engine_major(), ANCHOR_MAJOR + _since_anchor(today) // SLOWEST_DAYS)


def plausible(major, today=None):
    """Is this a version Chrome can have reached by now?"""
    ceiling = ANCHOR_MAJOR + _since_anchor(today) // FASTEST_DAYS + 2
    return isinstance(major, int) and not isinstance(major, bool) \
        and engine_major() <= major <= max(ceiling, engine_major())


def current(config=None, today=None):
    """The major version presented to sites: the engine's own (1.1.14)."""
    return engine_major()


def latest(config, today=None):
    """The current stable Chrome: the checked one, or else the estimate."""
    stored = config["chrome_major"]
    floor = estimate(today)
    if plausible(stored, today):
        return max(stored, floor)
    return floor


def latest_checked(config, today=None):
    """True when latest() comes from Google's version list, False when it is
    only the estimate from the calendar (the list could not be reached)."""
    stored = config["chrome_major"]
    return plausible(stored, today) and stored >= estimate(today)


def parse(data):
    """Highest stable major version in the service's answer (None if unreadable)."""
    try:
        obj = json.loads(data.decode("utf-8") if isinstance(data, bytes) else data)
        best = None
        for entry in obj.get("versions", [])[:200]:
            head = str(entry.get("version", "")).split(".")[0]
            if head.isdigit() and len(head) <= 4:
                best = max(best or 0, int(head))
        return best
    except (ValueError, AttributeError, TypeError):
        return None


def due(config):
    return time.time() - (config["chrome_checked"] or 0) > CHECK_INTERVAL


class Checker(QThread):
    done = pyqtSignal(object)        # int major, or None

    def run(self):
        major = None
        try:
            req = urllib.request.Request(URL, headers={"User-Agent": osinfo.browser_user_agent()})
            with urllib.request.urlopen(req, timeout=20) as r:
                if r.geturl().split("/")[2] == URL.split("/")[2]:        # no redirect elsewhere
                    major = parse(r.read(2 * 1024 * 1024))
        except Exception:
            major = None
        self.done.emit(major)
