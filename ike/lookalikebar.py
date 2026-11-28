"""The warning above a page whose address imitates a famous site (1.1.14).

Nothing is blocked: the page stays usable. "This site is fine" remembers the
site (Settings keep the list in "lookalike_ok"); the close button hides the
warning for this page only. See lookalike.py for how a look-alike is found.
"""

from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QStyle, QToolButton, QWidget

from . import lookalike
from .i18n import T


def check_view(config, view):
    """Find out (once per address) whether the page of `view` imitates a famous site."""
    url = view.url()
    host = url.host().lower()
    if url.scheme() not in ("http", "https") or not config["lookalike_warn"]:
        view.lookalike = None
        return
    if getattr(view, "lookalike_host", None) == host:
        return
    view.lookalike_host = host
    view.lookalike_closed = False
    try:
        view.lookalike = lookalike.check(host, allowed=set(config["lookalike_ok"] or []))
    except Exception:
        view.lookalike = None          # never in the way of browsing


class LookalikeBar(QWidget):
    def __init__(self, window):
        super().__init__(window)
        self.win = window
        self.view = None
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 4, 6, 4)
        self.text = QLabel(self)
        self.text.setWordWrap(True)
        self.ok = QPushButton(T("This site is fine"), self)
        close = QToolButton(self)
        close.setAutoRaise(True)
        close.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_TitleBarCloseButton))
        close.setToolTip(T("Hide this warning"))
        lay.addWidget(self.text, 1)
        lay.addWidget(self.ok)
        lay.addWidget(close)
        self.ok.clicked.connect(self._fine)
        close.clicked.connect(self._close)
        self.setAutoFillBackground(True)
        self.hide()

    def show_for(self, view):
        self._show_for(view)
        sync = getattr(self.win, "sync_interference", None)
        if sync is not None:
            sync()                     # the shield's red follows the warning (1.1.32)

    def _show_for(self, view):
        """Show or hide the warning for the page now in front."""
        self.view = view
        brand = getattr(view, "lookalike", None) if view is not None else None
        if not brand or getattr(view, "lookalike_closed", False):
            self.hide()
            return
        host = view.url().host().lower()
        self.text.setText("⚠ " + T("Careful: %s looks like %s, but it is not %s. "
                                   "Do not enter passwords or card details if you are not sure.")
                          % (host, brand, brand))
        if not self.isVisible():
            from . import polish
            polish.fade_child(self, self.win.app.config)
        self.show()

    def _fine(self):
        v = self.view
        if v is None:
            return
        cfg = self.win.app.config
        site = lookalike.registrable(v.url().host().lower())
        ok = list(cfg["lookalike_ok"] or [])
        if site and site not in ok:
            ok.append(site)
            cfg["lookalike_ok"] = ok
            cfg.save()
        v.lookalike = None
        self.hide()
        self.win.sync_interference()

    def _close(self):
        if self.view is not None:
            self.view.lookalike_closed = True
        self.hide()
