"""The Chrome version I.K.E. presents to websites.

The engine inside Qt is always some versions behind the Chrome people actually
run, and an old version number is rare enough to stand out. I.K.E. therefore
presents the current stable version: it asks Google's public version list once
a day (no personal data is sent) and, when that cannot be reached, estimates
the version from the calendar. Nothing here needs the user's attention.
"""

import json
import time
import urllib.request
from datetime import date

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWebEngineCore import qWebEngineChromiumVersion

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


def current(config, today=None):
    """The major version to present: the checked one, or else the estimate."""
    stored = config["chrome_major"]
    floor = estimate(today)
    if plausible(stored, today):
        return max(stored, floor)
    return floor


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
            req = urllib.request.Request(URL, headers={"User-Agent": "I.K.E. version check"})
            with urllib.request.urlopen(req, timeout=20) as r:
                if r.geturl().split("/")[2] == URL.split("/")[2]:        # no redirect elsewhere
                    major = parse(r.read(2 * 1024 * 1024))
        except Exception:
            major = None
        self.done.emit(major)
