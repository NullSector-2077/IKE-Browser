"""The site information panel: opened with the lock in the address bar.

For the site in the current tab: whether the connection is encrypted, the
permissions it was given, its cookies, the protection level, its zoom and
whether its videos and sounds may start by themselves. Everything here is
also somewhere else (shield, Page menu, Settings): this is the one place
that shows it all for one site.
"""

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QGridLayout, QLabel, QPushButton, QStyle, QVBoxLayout, QWidget

from .config import LEVEL_NAMES
from .i18n import T
from .icons import themed as icon
from .uistyle import Switch


class SiteInfoPanel(QWidget):
    def __init__(self, window):
        super().__init__(window)
        self.win = window
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(8)
        self.host = QLabel(self)
        f = self.host.font()
        f.setBold(True)
        f.setPointSizeF(f.pointSizeF() * 1.1)
        self.host.setFont(f)
        self.host.setTextFormat(Qt.TextFormat.PlainText)
        self.site_icon = QLabel(self)                # the site's icon beside its name (polish.py)
        from PyQt6.QtWidgets import QHBoxLayout
        head = QHBoxLayout()
        head.setSpacing(8)
        head.addWidget(self.site_icon)
        head.addWidget(self.host, 1)
        lay.addLayout(head)
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)
        self.conn_icon, self.conn = QLabel(self), QLabel(self)
        self.perms, self.cookies, self.level, self.zoom = (QLabel(self) for _ in range(4))
        for w in (self.conn, self.perms, self.cookies, self.level, self.zoom):
            w.setTextFormat(Qt.TextFormat.PlainText)
            w.setWordWrap(True)
        self.perms_reset = QPushButton(T("Reset this site's permissions"), self)
        self.perms_reset.clicked.connect(self._reset_perms)
        self.clear = QPushButton(T("Clear this site's data"), self)
        self.clear.clicked.connect(self._clear)
        self.zoom_reset = QPushButton(T("Actual size"), self)
        self.zoom_reset.clicked.connect(self._zoom_reset)
        grid.addWidget(self.conn_icon, 0, 0)
        grid.addWidget(self.conn, 0, 1, 1, 2)
        grid.addWidget(self.perms, 1, 1)
        grid.addWidget(self.perms_reset, 1, 2)
        grid.addWidget(self.cookies, 2, 1)
        grid.addWidget(self.clear, 2, 2)
        grid.addWidget(self.level, 3, 1, 1, 2)
        grid.addWidget(self.zoom, 4, 1)
        grid.addWidget(self.zoom_reset, 4, 2)
        grid.setColumnStretch(1, 1)
        lay.addLayout(grid)
        self.autoplay = Switch(T("Videos and sounds may start by themselves on this site"), self)
        self.autoplay.clicked.connect(self._autoplay)
        lay.addWidget(self.autoplay)
        self.setMinimumWidth(380)

    def refresh(self):
        win = self.win
        v = win.current_view()
        url = v.url() if v else None
        host = url.host().lower() if url else ""
        web = bool(url) and url.scheme() in ("http", "https") and bool(host)
        self.host.setText(host or (url.toString() if url else ""))
        from . import polish
        if polish.part("panel_icons") and web:
            self.site_icon.setPixmap(win.site_icon(url.toString()).pixmap(20, 20))
        self.site_icon.setVisible(polish.part("panel_icons") and web)
        SP = QStyle.StandardPixmap
        if url is not None and url.scheme() == "https":
            ic = icon(("object-locked", "channel-secure-symbolic"), SP.SP_DialogYesButton)
            text = T("Secure connection (HTTPS)")
        elif url is not None and url.scheme() == "http":
            ic, text = icon("security-low", SP.SP_MessageBoxWarning), T("Connection is not encrypted")
        else:
            ic, text = icon(("globe", "web-browser-symbolic"), SP.SP_FileIcon), ""
        self.conn_icon.setPixmap(ic.pixmap(20, 20))
        self.conn.setText(text)
        perms = win.site_permissions() if web else []
        self.perms.setText(T("Permissions: %s") % (", ".join(perms) if perms else T("none granted")))
        self.perms_reset.setVisible(bool(perms))
        n = 0
        if web:
            from .shields import site_of
            n = len(win.app.shields.site_cookies(v.page().profile(), site_of(host)))
        self.cookies.setText(T("Cookies: %d") % n)
        cfg = win.app.config
        lv = cfg.level_for(host) if web else cfg["shield_level"]
        self.level.setText("%s: %s" % (T("Protection level"), T(LEVEL_NAMES[lv])))
        factor = v.zoomFactor() if v else cfg["default_zoom"]
        self.zoom.setText(T("Zoom: %d%%") % round(factor * 100))
        self.zoom_reset.setVisible(abs(factor - cfg["default_zoom"]) > 0.005)
        self.autoplay.setChecked(web and not win.app.shields.autoplay_blocked(host))
        for w in (self.perms, self.cookies, self.clear, self.level, self.autoplay):
            w.setVisible(web)
        QTimer.singleShot(0, self._fit)

    def _fit(self):
        self.adjustSize()
        menu = self.parentWidget()
        if menu is not None and menu.isVisible():
            menu.adjustSize()

    def _reset_perms(self):
        self.win.site_permissions(reset=True)
        self.refresh()

    def _clear(self):
        self.win.site_info_menu.hide()
        self.win.clear_site_data()

    def _zoom_reset(self):
        self.win.zoom(0)
        self.refresh()

    def _autoplay(self, allowed):
        """This site's own choice; the same as Settings means no choice of its own."""
        win = self.win
        v = win.current_view()
        if not v:
            return
        host = v.url().host().lower()
        cfg = win.app.config
        cfg.set_site_opt(host, "autoplay", None if allowed == (not cfg["autoplay_block"]) else bool(allowed))
        cfg.save()
        v.reload()                   # the choice counts from the page's next load
