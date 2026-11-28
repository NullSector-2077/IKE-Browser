"""The bar above a page whose own background workers the level refused (1.1.32).

At Maximum a site's own service workers, shared workers and workers from its
files are refused (shields.py, _WORKER_SCRIPTS): messaging sites such as
WhatsApp and Telegram need them and stay empty or wait forever. Nothing is
turned on by itself: the bar says why the page may not work, and "Allow them
on this site" lets that site's own workers run (site_opts "workers": False,
kept with the repairs, so the shield's "Undo the repair" takes it back). The
rest of the protection stays as it is. The close button hides the bar for
this page only. At Kontrol the site's own workers run (the shield counts
them), so the bar never shows there.
"""

from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QStyle, QToolButton, QWidget

from .i18n import T


def refused_here(app, view):
    """Did the level refuse workers of the page in `view`, and could the user allow them?"""
    if view is None:
        return False
    url = view.url()
    host = url.host().lower()
    if url.scheme() not in ("http", "https") or not host:
        return False
    if not app.shields.site_stats(host).get("workers"):
        return False
    from . import repair
    return "workers" in repair.active(app.config, host)


def allow(app, host):
    """Let the site's own workers run on `host` (remembered with its repairs)."""
    from . import repair
    cfg = app.config
    repair.set_off(cfg, host, "workers", True)
    o = cfg["site_opts"].setdefault(host, {})
    o["repaired"] = sorted(set(o.get("repaired", [])) | {"workers"})
    cfg.save()
    app.shields.apply_settings()
    app.refresh_windows()


class WorkersBar(QWidget):
    def __init__(self, window):
        super().__init__(window)
        self.win = window
        self.view = None
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 4, 6, 4)
        self.text = QLabel(T("This level blocks the site's own background workers: "
                             "the site may not work."), self)
        self.text.setWordWrap(True)
        self.ok = QPushButton(T("Allow them on this site"), self)
        close = QToolButton(self)
        close.setAutoRaise(True)
        close.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_TitleBarCloseButton))
        close.setToolTip(T("Hide this warning"))
        lay.addWidget(self.text, 1)
        lay.addWidget(self.ok)
        lay.addWidget(close)
        self.ok.clicked.connect(self._allow)
        close.clicked.connect(self._close)
        self.setAutoFillBackground(True)
        self.hide()

    def show_for(self, view):
        """Show or hide the bar for the page now in front."""
        self.view = view
        if not refused_here(self.win.app, view) or getattr(view, "workers_bar_closed", None) == view.url():
            self.hide()
            return
        if not self.isVisible():
            from . import polish
            polish.fade_child(self, self.win.app.config)
        self.show()

    def _allow(self):
        v = self.view
        if v is None:
            return
        host = v.url().host().lower()
        if not host:
            return
        allow(self.win.app, host)
        self.hide()
        from PyQt6.QtWebEngineCore import QWebEnginePage
        v.page().triggerAction(QWebEnginePage.WebAction.ReloadAndBypassCache)

    def _close(self):
        if self.view is not None:
            self.view.workers_bar_closed = self.view.url()
        self.hide()
