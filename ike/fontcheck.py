"""Which of the masked font names a page could find on this computer (1.1.17).

At Strict and Maximum the fingerprint protection (fingerprint.js, maskFonts)
hides the computer's fonts from pages: for every name of its list (714 names)
it adds a blank font face, so a page measuring text in that font sees nothing
special. Doing it for all 714 names costs about 20 ms in every frame of every
page. A name the engine cannot find on this computer already looks absent, so
only the names it can find need a mask: the protection is the same (measured:
no name can be found either way), the cost much smaller.

The engine itself is asked, with the very test the fingerprinting scripts use
(the width of a text in the font against the default fonts), in a hidden page
of a separate profile with none of I.K.E.'s scripts, once after the start and
again only when the installed fonts change (their list is remembered with the
answer). Until there is an answer, or if the test fails, the whole list is used.
"""

import hashlib
import json
import re

from PyQt6.QtCore import QObject, QTimer, QUrl

from .config import CACHE_DIR, RES_DIR

_CACHE = CACHE_DIR / "fonts-findable.json"
_found = None            # list of names, once known for the fonts installed now
_key = None

DETECT = r"""(function (names) {
  var s = 'mmmmmmmmmmlli1WQ@#%%&ABCxyz', out = [];
  var box = document.createElement('div'); document.body.appendChild(box);
  function w(f) {
    var e = document.createElement('span');
    e.style.cssText = 'font-size:72px;position:absolute;white-space:nowrap;font-family:' + f;
    e.textContent = s; box.appendChild(e);
    var r = e.offsetWidth + 'x' + e.offsetHeight; box.removeChild(e); return r;
  }
  var base = {}; ['monospace', 'serif', 'sans-serif'].forEach(function (b) { base[b] = w(b); });
  names.forEach(function (n) {
    ['monospace', 'serif', 'sans-serif'].some(function (b) {
      if (w("'" + n.replace(/'/g, '') + "'," + b) !== base[b]) { out.push(n); return true; }
      return false;
    });
  });
  return out;
})(%s)"""


def masked_names():
    """The list of fingerprint.js (one source of truth)."""
    text = (RES_DIR / "fingerprint.js").read_text("utf-8")
    m = re.search(r"var MASKED_FONTS = (\[.*?\]);", text, re.S)
    return json.loads(m.group(1)) if m else []


# the families every system answers to: never masked (fingerprint.js). Also
# "Monospace", the engine's own family for monospace (shields.CHROME_FONTS):
# fontconfig's name for it, which Qt lists among the installed families. A
# worker draws monospace through that name, so its mask made a worker's
# monospace another font, and a worker found other fonts than its page
# (review of 1.1.25, round 3).
KEPT = {"arial", "helvetica", "times", "times new roman", "courier", "courier new", "monospace"}


def candidates(families=None):
    """The names to test: the list of fingerprint.js and every family
    installed here (fingerprinting audit, H-D: a font outside the list, such
    as IPAGothic, was found by measuring text in it)."""
    if families is None:
        from PyQt6.QtGui import QFontDatabase
        families = QFontDatabase.families()
    names = list(masked_names())
    seen = {n.lower() for n in names}
    for f in installed(families):
        if f.lower() not in seen:
            seen.add(f.lower())
            names.append(f)
    return names


def installed(families=None):
    """Every family installed here, Qt's " [foundry]" removed, but never the
    six every system answers to."""
    if families is None:
        from PyQt6.QtGui import QFontDatabase
        families = QFontDatabase.families()
    out, seen = [], set(KEPT)
    for f in families:
        f = re.sub(r"\s*\[[^\]]*\]$", "", str(f)).strip()
        if f and f.lower() not in seen:
            seen.add(f.lower())
            out.append(f)
    return out


def fonts_key():
    """Changes when the fonts installed on this computer change."""
    from PyQt6.QtGui import QFontDatabase
    names = sorted(QFontDatabase.families())
    h = hashlib.sha1("\n".join(names).encode("utf-8"))
    h.update(hashlib.sha1(json.dumps(masked_names()).encode()).digest())
    h.update(b"installed families always")       # answers of 1.1.19 and before: asked again
    h.update(b"monospace kept")                   # answers of 1.1.24 and before: asked again
    return h.hexdigest()


def findable():
    """The masked names a page can find here, or None (not known: mask all)."""
    global _found, _key
    if _key is None:
        try:
            _key = fonts_key()
            data = json.loads(_CACHE.read_text("utf-8"))
            if data.get("key") == _key and isinstance(data.get("fonts"), list):
                _found = [str(n) for n in data["fonts"]]
        except (OSError, ValueError, AttributeError):
            pass
    return _found


class Checker(QObject):
    """Runs the test once, in the background, when the answer is not known."""

    def __init__(self, shields, parent=None):
        super().__init__(parent)
        self.shields = shields
        self._page = None
        self._profile = None

    def start(self, delay_ms=15000):
        if findable() is None:
            QTimer.singleShot(delay_ms, self._run)

    def _run(self):
        from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
        if findable() is not None or self._page is not None:
            return
        self._profile = QWebEngineProfile(self)          # off the record, no scripts of I.K.E.
        self._page = QWebEnginePage(self._profile, self)
        self._page.loadFinished.connect(self._loaded)
        self._page.setHtml("<!doctype html><body></body>", QUrl("about:blank"))

    def _loaded(self, ok):
        if not ok or self._page is None:
            self._end(None)
            return
        self._page.runJavaScript(DETECT % json.dumps(candidates()), 0, self._end)

    def _end(self, found):
        global _found
        page, self._page = self._page, None
        if page is not None:
            page.deleteLater()
        if not isinstance(found, list):
            return                              # the whole list stays in use
        # every family installed here is masked too, whatever the measure said:
        # a font whose letters a script font shares measured the same once in
        # a while, and was left findable (seen on a computer with 900 fonts)
        seen, _found = set(), []
        for n in [str(x) for x in found] + installed():
            if n.lower() not in seen:
                seen.add(n.lower())
                _found.append(n)
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            _CACHE.write_text(json.dumps({"key": _key or fonts_key(), "fonts": _found}), "utf-8")
        except OSError:
            pass
        self.shields.apply_settings()           # new pages get the shorter list
