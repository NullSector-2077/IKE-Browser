"""The bar above a page that I.K.E. stopped for the user's safety (1.1.17).

Two cases, each with a way through that only the user can take:

- "nohttps": the page was asked for over plain http, I.K.E. tried the secure
  address first (https_only) and it did not answer. Until 1.1.17 the browser
  went back to http by itself, without a word: someone on the same network
  can make the secure address fail on purpose to read and change the page.
  Now the page stops, the bar says why, and "Continue without protection"
  opens the http address for this session.
- "lan" (home network protection): a page of a public site tried to open an
  address of this computer or of the home network (a form sent to the
  router). "Allow for this site" opens that address for this session. For a
  part of a page (a frame, an image, a script) the bar only says what was
  stopped: the engine's own protection stops it in any case (1.1.19).
- "blocked": the whole page is on the filter lists (a site that spreads
  malware, or one only made of ads or tracking). "Continue anyway" opens it
  for this session; the lists still filter what it loads.

A web page cannot reach the buttons: they are part of the window, not of the
page, and the pass they give lasts until I.K.E. closes.
"""

from PyQt6.QtCore import QUrl
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QStyle, QToolButton, QWidget

from .i18n import T


def set_notice(view, kind, url, site=""):
    """Mark `view` as stopped (kind "nohttps", "blocked" or "lan") for `url`;
    `site`: the public site that tried to open it ("lan")."""
    view.secure_notice = {"kind": kind, "url": QUrl(url).toString(), "closed": False, "site": site}


def notice_of(view):
    n = getattr(view, "secure_notice", None) if view is not None else None
    if not n or n.get("closed"):
        return None
    # the notice belongs to the address it was given for (or the error page shown for it)
    if view.url().toString() not in (n["url"], "") and view.url().host().lower() != QUrl(n["url"]).host().lower():
        return None
    return n


class SecureBar(QWidget):
    def __init__(self, window):
        super().__init__(window)
        self.win = window
        self.view = None
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 4, 6, 4)
        self.text = QLabel(self)
        self.text.setWordWrap(True)
        self.go = QPushButton(self)
        self.back = QPushButton(T("Go back"), self)
        close = QToolButton(self)
        close.setAutoRaise(True)
        close.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_TitleBarCloseButton))
        close.setToolTip(T("Hide this warning"))
        lay.addWidget(self.text, 1)
        lay.addWidget(self.back)
        lay.addWidget(self.go)
        lay.addWidget(close)
        self.go.clicked.connect(self._continue)
        self.back.clicked.connect(self._back)
        close.clicked.connect(self._close)
        self.setAutoFillBackground(True)
        self.hide()

    def show_for(self, view):
        self.view = view
        n = notice_of(view)
        if n is None:
            self.hide()
            return
        host = QUrl(n["url"]).host()
        # a part of a page: the engine's own protection stops it whatever the
        # window allows (1.1.19), so the bar only says what happened
        self.go.setVisible(not (n["kind"] == "lan" and n.get("frame")))
        if n["kind"] == "nohttps":
            self.text.setText("⚠ " + T("%s has no secure connection (https), or someone on the network "
                                       "is blocking it. Without it, others on the network can read and "
                                       "change this page.") % host)
            self.go.setText(T("Continue without protection"))
        elif n["kind"] == "lan":
            target = T("a part of this page") if n.get("frame") else host
            self.text.setText("⚠ " + T("%s tried to open %s, an address of this computer or of your home "
                                       "network (a router, a printer, a local program). Sites can use this "
                                       "to change their settings.") % (n.get("site") or "?", target))
            self.go.setText(T("Allow for this site"))
        else:
            self.text.setText("⛔ " + T("I.K.E. stopped %s: it is on the protection lists (sites that "
                                       "spread malware, or made only of ads and tracking).") % host)
            self.go.setText(T("Continue anyway"))
        self.back.setVisible(view.history().canGoBack())
        if not self.isVisible():
            from . import polish
            polish.fade_child(self, self.win.app.config)
        self.show()

    def _continue(self):
        v = self.view
        n = notice_of(v)
        if n is None:
            return
        url = QUrl(n["url"])
        sh = self.win.app.shields
        host = url.host().lower()
        if n["kind"] == "nohttps":
            sh.http_allowed.add(host)
            url.setScheme("http")
        elif n["kind"] == "lan":
            if n.get("site"):
                sh.lan_allowed.add(n["site"])      # this site only, until I.K.E. closes
        else:
            sh.pages_allowed.add(host)
        v.secure_notice = None
        self.hide()
        v.load(url)

    def _back(self):
        v = self.view
        if v is not None:
            v.secure_notice = None
            v.back()
        self.hide()

    def _close(self):
        n = getattr(self.view, "secure_notice", None)
        if n:
            n["closed"] = True
        self.hide()
