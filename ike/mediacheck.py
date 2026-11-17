"""Which video and audio formats the engine can play, asked of the engine itself.

I.K.E. ships no codec of its own: what plays depends on how the engine on this
system was built (on Linux, the distribution's Qt WebEngine). Help → About shows
the answer, so a video that does not play can be told apart from a fault in
I.K.E.

The question is asked once per session, when it is first needed, in a blank
page of a private (off-the-record) profile that is thrown away at once: no web
page is involved and nothing is written to disk. The answer is what the engine
declares (``canPlayType`` and Media Source support), not a decoded video.
"""

import glob
import json
import os

from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineScript

# (name shown, MIME type with codec) — the formats video sites actually offer
FORMATS = (
    ("H.264", 'video/mp4; codecs="avc1.42E01E"'),
    ("AAC", 'audio/mp4; codecs="mp4a.40.2"'),
    ("HEVC", 'video/mp4; codecs="hvc1.1.6.L93.B0"'),
    ("VP9", 'video/webm; codecs="vp9"'),
    ("AV1", 'video/webm; codecs="av01.0.05M.08"'),
    ("Opus", 'audio/webm; codecs="opus"'),
    ("MP3", "audio/mpeg"),
)

TIMEOUT_MS = 15000

_PROBE_JS = """(function (types) {
  var v = document.createElement("video"), out = {};
  types.forEach(function (t) {
    var p = v.canPlayType(t), m = false;
    try { m = !!(window.MediaSource && MediaSource.isTypeSupported(t)); } catch (e) {}
    out[t] = (p === "probably" || p === "maybe" || m);
  });
  return JSON.stringify(out);
})(%s)"""

_result = None          # {name: bool} once known, for the rest of the session


def known():
    """The answer of this session, or None when it was not asked yet."""
    return dict(_result) if _result is not None else None


def parse(text):
    """{name: bool} from the probe's JSON; formats missing or not true count
    as not playable. Anything that is not the expected answer gives {}."""
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {name: data.get(mime) is True for name, mime in FORMATS}


class Probe(QObject):
    """Asks the engine once; ``done`` gives {name: bool}, or {} when the
    engine did not answer. The page and its profile are deleted afterwards."""

    done = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._finished = False
        self._profile = QWebEngineProfile(self)           # off the record: no files
        self._page = QWebEnginePage(self._profile, self)
        self._page.loadFinished.connect(self._loaded)
        self._timer = QTimer(self, singleShot=True, interval=TIMEOUT_MS)
        self._timer.timeout.connect(lambda: self._finish({}))

    def start(self):
        self._timer.start()
        self._page.setHtml("<!doctype html><title>I.K.E.</title>")

    def _loaded(self, ok):
        if self._finished:
            return
        if not ok:
            self._finish({})
            return
        js = _PROBE_JS % json.dumps([mime for _name, mime in FORMATS])
        self._page.runJavaScript(js, QWebEngineScript.ScriptWorldId.ApplicationWorld,
                                 lambda text: self._finish(parse(text)))

    def _finish(self, result):
        global _result
        if self._finished:
            return
        self._finished = True
        self._timer.stop()
        if result:
            _result = dict(result)
        self.done.emit(dict(result))
        # the page goes before its profile (Qt warns otherwise)
        page, self._page = self._page, None
        QTimer.singleShot(0, page.deleteLater)
        QTimer.singleShot(0, self.deleteLater)


def ask(parent, callback):
    """Calls callback({name: bool}) — at once when the answer is known,
    otherwise when the engine has answered ({} if it did not)."""
    if _result is not None:
        callback(dict(_result))
        return None
    probe = Probe(parent)
    probe.done.connect(callback)
    probe.start()
    return probe


def split(result):
    """(playable names, not playable names), in the order of FORMATS."""
    yes = [name for name, _mime in FORMATS if result.get(name)]
    no = [name for name, _mime in FORMATS if not result.get(name)]
    return yes, no


# Inside the Flatpak, H.264 is decoded by the run time's FFmpeg only when
# Freedesktop's codec extension is installed (packaging/flatpak/README.md,
# "Codecs"). Its branch follows the Freedesktop base of the KDE run time in
# the manifest: KDE 6.11 is built on Freedesktop 25.08.
CODECS_EXTRA_REF = "org.freedesktop.Platform.codecs-extra//25.08-extra"
CODECS_EXTRA_INSTALL = "flatpak install flathub " + CODECS_EXTRA_REF
# Flatpak writes this file for an installed extension that adds a library
# folder (add-ld-path); Freedesktop's own FFmpeg test detects the extension
# the same way (freedesktop-sdk, tests/ffmpeg-test.py)
_CODECS_EXTRA_CONF = "run/flatpak/ld.so.conf.d/runtime-*-org.freedesktop.Platform.codecs-extra.conf"


def codecs_extra_missing(root="/"):
    """True only inside a Flatpak whose run time's codec extension is not
    installed; outside a Flatpak always False."""
    from . import osinfo
    if not osinfo.in_flatpak():
        return False
    return not glob.glob(os.path.join(root, _CODECS_EXTRA_CONF))
