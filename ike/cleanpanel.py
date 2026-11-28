"""The panel of the toolbar's broom, "Clear this site's data" (1.1.30, the
owner's choice).

It opens under the button, as the zoom's and the downloads' panels do
(window.show_clean_panel), and shows what the site in the tab keeps on this
computer before anything goes: its cookies, the data it stored (local
storage, databases, service workers), its cache, the cookies of the other
sites its pages loaded that the user never opened (its trackers and
services: window.tracker_sites) and the permissions it was given. Each one
has a switch; "Clear" deletes what is on (everything but the permissions at
first) and loads the page again, and the panel says what went. Its last
switch cleans the site by itself when its last tab is closed (shields.py,
autoclean). Everything is counted in I.K.E.'s own script world: the page sees
nothing of it. Nothing runs while the panel is closed.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from . import panelkit
from .i18n import T
from .uistyle import Switch


def _icon(names):
    from .icons import themed
    return themed(names)


class Pill(QLabel):
    """A count in a small rounded pill, in the theme's colours ("…" while it is
    being counted)."""

    def __init__(self, parent):
        super().__init__("…", parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumWidth(34)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        f = self.font()
        f.setBold(True)
        self.setFont(f)
        self.restyle(False)

    def restyle(self, strong):
        pal = self.palette()
        back = QColor(pal.color(QPalette.ColorRole.Highlight) if strong else pal.color(QPalette.ColorRole.Mid))
        back.setAlphaF(0.30 if strong else 0.35)
        self.setStyleSheet("QLabel { background: rgba(%d, %d, %d, %d); border-radius: 9px; padding: 1px 8px; }"
                           % (back.red(), back.green(), back.blue(), back.alpha()))

    def show_count(self, n):
        self.setText("…" if n is None else str(n))
        self.restyle(bool(n))


class CleanPanel(QWidget):
    """Popup of the toolbar's broom."""

    KINDS = ("cookies", "storage", "cache", "trackers", "permissions")

    def __init__(self, window):
        super().__init__(window)
        self.win = window
        self.view = None
        self.site = ""
        self._busy = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(*panelkit.MARGINS)
        lay.setSpacing(8)

        # 1. the title and the site
        head, self.head_icon, self.title = panelkit.title_row(
            self, _icon(("edit-clear-history", "edit-clear-all-symbolic", "edit-clear-all", "edit-clear")),
            T("Clear this site's data"))
        self.host = panelkit.dim(QLabel(self), 1.0)
        self.host.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        head.addWidget(self.host)
        lay.addLayout(head)
        self.intro = panelkit.dim(QLabel(T("What this site keeps on this computer. Choose what to delete."), self))
        self.intro.setWordWrap(True)
        lay.addWidget(self.intro)

        # 2. what it keeps, each with its switch and its count
        texts = {"cookies": T("Cookies and sign-ins"), "storage": T("Data stored by the site"),
                 "cache": T("Cache"), "trackers": T("Cookies of this page's trackers"),
                 "permissions": T("Permissions given to the site")}
        self.switches, self.pills = {}, {}
        for kind in self.KINDS:
            row = QHBoxLayout()
            row.setSpacing(8)
            sw = Switch(texts[kind], self)
            sw.setChecked(kind != "permissions")
            pill = Pill(self)
            row.addWidget(sw, 1)
            row.addWidget(pill)
            lay.addLayout(row)
            self.switches[kind], self.pills[kind] = sw, pill
        self.tracker_names = panelkit.dim(QLabel(self), 0.85)
        self.tracker_names.setWordWrap(True)
        lay.addWidget(self.tracker_names)

        # 3. Clear, and what went
        self.clear = QPushButton(_icon(("edit-clear-history", "edit-clear-all-symbolic", "edit-clear-all",
                                        "edit-clear")), T("Clear"), self)
        self.clear.setDefault(True)
        self.clear.setMinimumHeight(32)
        self.clear.clicked.connect(self._clear)
        lay.addWidget(self.clear)
        self.done = QLabel(self)
        self.done.setWordWrap(True)
        self.done.hide()
        lay.addWidget(self.done)

        sep = QFrame(self)
        sep.setFrameShape(QFrame.Shape.HLine)
        lay.addWidget(sep)

        # 4. clean by itself
        self.auto = Switch(T("Clean it when I close its last tab"), self)
        self.auto.clicked.connect(self._auto_changed)
        lay.addWidget(self.auto)
        self.auto_hint = panelkit.dim(QLabel(T("Its cookies go at once, what it stored before its next page "
                                               "opens. You are signed out of it each time."), self))
        self.auto_hint.setWordWrap(True)
        lay.addWidget(self.auto_hint)
        self.setFixedWidth(panelkit.WIDTH)

    # --- what the panel shows ------------------------------------------------
    def refresh(self):
        """The site of the tab, and what it keeps (counted again each time it opens)."""
        from .shields import site_of
        self._busy = True
        v = self.win.current_view()
        web = v is not None and v.url().scheme() in ("http", "https") and bool(v.url().host())
        self.view = v if web else None
        self.site = site_of(v.url().host().lower()) if web else ""
        self.host.setText(self.site)
        self.done.hide()
        self.clear.setEnabled(web)
        self.clear.setText(T("Clear"))
        for kind in self.KINDS:
            self.switches[kind].setEnabled(web)
            self.pills[kind].show_count(None if web else 0)
        self.tracker_names.setText("" if web else T("This page keeps no site data."))
        self.auto.setEnabled(web and not self.win.private)
        self.auto.setChecked(web and self.site in self.win.app.config["autoclean_sites"])
        self._busy = False
        if web:
            site = self.site
            self.win.site_contents(v, site, lambda found, s=site: self._counted(s, found))

    def _counted(self, site, found):
        if site != self.site:
            return                      # the panel was opened again for another site meanwhile
        p = self.pills
        p["cookies"].show_count(found["cookies"])
        p["storage"].show_count(found["storage"])
        p["cache"].show_count(found["cache"])
        p["trackers"].show_count(found["tracker_cookies"])
        p["permissions"].show_count(len(found["permissions"]))
        names = found["trackers"]
        if names:
            shown = ", ".join(names[:4]) + (" …" if len(names) > 4 else "")
            self.tracker_names.setText(T("Other sites on this page: %s") % shown)
        else:
            self.tracker_names.setText("")

    # --- what the user does --------------------------------------------------
    def _clear(self):
        if self.view is None:
            return
        what = tuple(k for k in self.KINDS if self.switches[k].isChecked())
        if not what:
            return
        self.clear.setEnabled(False)
        self.clear.setText(T("Clearing…"))
        site = self.site
        self.win.clean_site(self.view, site, what, lambda r, s=site: self._cleaned(s, r))

    def _cleaned(self, site, r):
        if site != self.site:
            return
        self.clear.setText(T("Clear"))
        self.clear.setEnabled(True)
        self.done.setText("✓ " + T("Deleted: %d cookies, %d stored data, %d in the cache, %d trackers' cookies.")
                          % (r["cookies"], r["storage"], r["cache"], r["trackers"]))
        pal = self.done.palette()
        pal.setColor(QPalette.ColorRole.WindowText, QColor("#27ae60"))      # Breeze's positive green
        self.done.setPalette(pal)
        self.done.show()
        for kind, n in (("cookies", 0), ("storage", 0), ("cache", 0), ("trackers", 0)):
            if self.switches[kind].isChecked():
                self.pills[kind].show_count(n)
        if self.switches["permissions"].isChecked():
            self.pills["permissions"].show_count(0)
        self.win.fit_panel("clean", place=False)

    def _auto_changed(self, on):
        if self._busy or not self.site:
            return
        cfg = self.win.app.config
        sites = [x for x in cfg["autoclean_sites"] if x != self.site]
        if on:
            sites.append(self.site)
        cfg["autoclean_sites"] = sites
        cfg.save()
