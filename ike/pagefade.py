"""Pages that change softly (1.1.31, the owner: "pages come in abruptly: can it be smoother without
losing speed?"). When a tab goes to another page, or loads its page again (dark mode turned on or off
for it reloads it), the old page's picture stays over the tab until the new page has drawn its first
content, then fades away in a fifth of a second (a quarter or so for the dark mode's change of colours):
the new page comes in under it instead of jumping in.

Nothing waits for it: the new page loads and draws as fast as ever, the picture only lies over it, and
lets the mouse through. The engine itself keeps showing the old page until the new one has something to
show (Chromium's "paint holding"), so for that moment the picture shows just what the screen showed.
When the new page has drawn is asked of the page itself, in I.K.E.'s own world (the page cannot see it):
a new document (another performance.timeOrigin) and its first-contentful-paint; a page that never tells
(a PDF, an image) ends the picture when it has loaded, and at the latest after HOLD_MS.

Only with the interface's effects (effects.on: not with reduced motion asked nor with the battery saver
at work) and the touch "page_fade" of polish.PARTS, only in a tab that is shown, and never for a tab's
first page.
"""

import time

from PyQt6.QtCore import QEasingCurve, QObject, QPropertyAnimation, Qt, QTimer, QUrl
from PyQt6.QtWebEngineCore import QWebEngineScript
from PyQt6.QtWidgets import QGraphicsOpacityEffect, QLabel

from . import polish

FADE_MS = 190                 # another page
DARK_FADE_MS = 280            # the same page again (dark mode on or off)
ASK_MS = 16                   # how often the page is asked whether it has drawn (only while it changes)
HOLD_MS = 900                 # the longest the old picture stays after the new page took its place
GIVE_UP_MS = 2500             # a page that takes longer to come: no picture, and nothing asked any more
ASK = "[performance.timeOrigin, performance.getEntriesByName('first-contentful-paint').length > 0]"
WORLD = QWebEngineScript.ScriptWorldId.ApplicationWorld


def _plain(url):
    u = QUrl(url)
    u.setFragment(None)
    return u.toString()


class PageFade(QObject):
    """The fade of one tab (a child of its view)."""

    def __init__(self, view, config):
        super().__init__(view)
        self.view = view
        self.config = config
        self.shot = None          # the old page's picture, taken when the new page was asked for
        self.origin = None        # the old document's timeOrigin
        self.started = 0.0
        self.committed = 0.0
        self.same = False         # the same address again (a reload)
        self.cover = None
        self.anim = None
        self.timer = QTimer(self)
        self.timer.setInterval(ASK_MS)
        self.timer.timeout.connect(self._ask)
        page = view.page()
        page.loadStarted.connect(self._started)
        page.loadFinished.connect(self._finished)

    # --- the old page, before the new one -------------------------------
    def _wanted(self):
        v = self.view
        url = v.url()
        return (polish.moving(self.config, "page_fade") and v.isVisible() and v.width() > 0 and v.height() > 0
                and not url.isEmpty() and url.toString() != "about:blank"
                and not getattr(v, "sleeping", False))

    def _started(self):
        self._drop()
        if not self._wanted():
            return
        try:
            self.shot = self.view.grab()
        except RuntimeError:
            return
        if self.shot.isNull():
            self.shot = None
            return
        self.origin, self.committed = None, 0.0
        self.started = time.monotonic()
        self.from_url = _plain(self.view.url())
        self.view.page().runJavaScript(ASK, WORLD, self._first_answer)

    def _first_answer(self, r):
        if self.shot is None:
            return
        self.origin = r[0] if isinstance(r, list) and r else None
        self.timer.start()

    # --- the new page ----------------------------------------------------
    def _ask(self):
        if self.shot is None:
            self.timer.stop()
            return
        now = time.monotonic()
        if not self.view.isVisible():
            self._drop()                             # a tab out of sight is not asked (nor woken)
            return
        if not self.committed and now - self.started > GIVE_UP_MS / 1000:
            self._drop()
            return
        if self.committed and now - self.committed > HOLD_MS / 1000:
            self._fade()
            return
        try:
            self.view.page().runJavaScript(ASK, WORLD, self._answer)
        except RuntimeError:
            self._drop()

    def _answer(self, r):
        if self.shot is None or not isinstance(r, list) or len(r) < 2:
            return
        if not self.committed:
            if r[0] == self.origin:
                return                               # still the old page
            if r[1]:
                # the new page has drawn already (a very quick one): the old picture is not put
                # back over it (it would jump back for a moment); it simply stays as it came
                self._drop()
                return
            self._commit()
        if r[1] and self.cover is not None and self.anim is None:
            self._fade()

    def _commit(self):
        """The new page took the old one's place: the old picture lies over it."""
        self.committed = time.monotonic()
        self.same = _plain(self.view.url()) == self.from_url
        if not self.view.isVisible():
            self._drop()
            return
        c = QLabel(self.view)
        c.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        c.setObjectName("ike_page_fade")
        c.setScaledContents(True)
        c.setPixmap(self.shot)
        c.setGeometry(self.view.rect())
        c.show()
        c.raise_()
        self.cover = c

    def _finished(self, _ok):
        if self.shot is None:
            return
        if self.cover is None:
            self._drop()                             # the new page never needed the picture
            return
        if self.anim is None:
            self._fade()

    def _fade(self):
        self.timer.stop()
        c = self.cover
        if c is None:
            self._drop()
            return
        if self.anim is not None:
            return
        effect = QGraphicsOpacityEffect(c)
        effect.setOpacity(1.0)
        c.setGraphicsEffect(effect)
        a = QPropertyAnimation(effect, b"opacity", self)
        a.setDuration(DARK_FADE_MS if self.same else FADE_MS)
        a.setStartValue(1.0)
        a.setEndValue(0.0)
        a.setEasingCurve(QEasingCurve.Type.OutCubic)
        a.finished.connect(self._drop)
        self.anim = a
        a.start()

    def _drop(self):
        self.timer.stop()
        if self.anim is not None:
            self.anim.stop()
            self.anim = None
        if self.cover is not None:
            try:
                self.cover.hide()
                self.cover.deleteLater()
            except RuntimeError:
                pass
            self.cover = None
        self.shot = None
        self.committed = 0.0

    def resized(self):
        """The tab changed size: the old picture no longer fits it."""
        if self.cover is not None:
            self._drop()


def attach(view, config):
    view.ike_page_fade = PageFade(view, config)
    return view.ike_page_fade
