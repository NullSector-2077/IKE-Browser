"""The panel of the toolbar's Downloads button (1.1.25).

It opens under the button (and with Ctrl+J), as the dark mode's panel does
(window.show_downloads_panel): one row for each download of the list
(downloadlist.py), the newest first. A row shows the kind of file (the icon
theme's), its name shortened in the middle, and one line of state: the bytes,
the speed and the time left with a slim bar while it runs; paused; the size,
the site and the time once done; why it failed; why I.K.E.'s checks stopped
it. Its actions are small buttons shown while the mouse is over the row (or
the row has the keyboard's focus): pause and cancel, resume, open the file,
show it in its folder, try again, remove it from the list; a right click gives
them all, with the desktop's app for an archive or a calendar file and
"Copy link address". "Download anyway…" of a stopped download asks the same
question as before, "Cancel" already chosen.

At its foot: the downloads window (every download of this session), the
downloads folder and "Clear the list" (the downloads that ended leave the
list, the files stay). Nothing goes outside I.K.E.: the files and folders are
handed to the desktop's apps (handoff.py). A private window shows its own
downloads only.
"""

from PyQt6.QtCore import QEvent, QPointF, QRectF, QSize, Qt, QTimer
from PyQt6.QtGui import QColor, QGuiApplication, QIcon, QPainter, QPalette, QPen, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QSizePolicy,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import downloadlist, panelkit
from .i18n import T

WIDTH = 400 + 28            # the owner's preview: about 400 pixels of rows
ROW_PAD = 8                 # the rows' hover background reaches this far into the panel's margin
TICK_MS = 500               # while it is open and files arrive: the rows are read again


def _icon(names):
    from .icons import themed
    return themed(names)


_file_icons = {}


def file_icon(name):
    """The icon of the file's kind, from the icon theme (as the downloads window's)."""
    from PyQt6.QtCore import QMimeDatabase
    mime = QMimeDatabase().mimeTypeForFile(name or "", QMimeDatabase.MatchMode.MatchExtension)
    key = mime.name()
    if key not in _file_icons:
        ic = QIcon.fromTheme(mime.iconName())
        if ic.isNull():
            ic = QIcon.fromTheme(mime.genericIconName())
        if ic.isNull():
            ic = QApplication.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)
        _file_icons[key] = ic
    return _file_icons[key]


def stopped_icon(icon, size=32):
    """The file's icon with a small red mark at its corner: stopped by I.K.E."""
    ratio = 2
    pm = QPixmap(size * ratio, size * ratio)
    pm.setDevicePixelRatio(ratio)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    icon.paint(p, 0, 0, size, size)
    r = QRectF(size - 13, size - 13, 13, 13)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QGuiApplication.palette().color(QPalette.ColorRole.Window))
    p.drawEllipse(r.adjusted(-1, -1, 1, 1))
    p.setBrush(panelkit.negative())
    p.drawEllipse(r)
    p.setPen(QPen(QColor("white"), 1.8, cap=Qt.PenCapStyle.RoundCap))
    c = r.center()
    p.drawLine(QPointF(c.x() - 3.5, c.y()), QPointF(c.x() + 3.5, c.y()))
    p.end()
    return pm


class SlimBar(QWidget):
    """The slim line of a download going on: the accent colour, faded while paused."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.fraction, self.paused = 0.0, False
        self.setFixedHeight(4)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def show_state(self, fraction, paused):
        fraction = 0.0 if fraction is None else fraction
        if (fraction, paused) != (self.fraction, self.paused):
            self.fraction, self.paused = fraction, paused
            self.update()

    def paintEvent(self, _e):
        from . import polish
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = self.palette()
        r = QRectF(self.rect())
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(polish.separator(pal))
        p.drawRoundedRect(r, 2, 2)
        if self.paused:
            fill = QColor(pal.color(QPalette.ColorRole.WindowText))
            fill.setAlphaF(0.45)
        else:
            fill = pal.color(QPalette.ColorRole.Highlight)
        p.setBrush(fill)
        if self.fraction > 0:
            p.drawRoundedRect(QRectF(r.left(), r.top(), max(4.0, r.width() * self.fraction), r.height()), 2, 2)
        p.end()


# the actions of a row, in the order of their buttons
ACTIONS = ("pause", "resume", "cancel", "open", "folder", "retry", "remove")
SHOWN = {"running": ("pause", "cancel"), "paused": ("resume", "cancel"), "done": ("open", "folder", "remove"),
         "failed": ("retry", "remove"), "cancelled": ("retry", "remove"), "stopped": ("remove",)}


def action_icon(key):
    """The icon of a row's action (literal names, for tools/build-breeze-icons.py)."""
    if key == "pause":
        return _icon(("media-playback-pause",))
    if key == "resume":
        return _icon(("media-playback-start",))
    if key == "cancel":
        return _icon(("process-stop",))
    if key == "open":
        return _icon(("document-open",))
    if key == "folder":
        return _icon(("folder-open", "document-open-folder", "document-open"))
    if key == "retry":
        return _icon(("view-refresh",))
    return _icon(("edit-delete-remove", "list-remove", "window-close"))


def action_text(key):
    return {"pause": T("Pause"), "resume": T("Resume"), "cancel": T("Cancel download"), "open": T("Open file"),
            "folder": T("Show in folder"), "retry": T("Retry"), "remove": T("Remove from list")}[key]


class DownloadRow(QWidget):
    """One download of the list."""

    def __init__(self, panel, entry):
        super().__init__(panel)
        self.panel, self.entry = panel, entry
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setMouseTracking(True)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(ROW_PAD, 6, ROW_PAD, 6)
        lay.setSpacing(10)
        self.pic = QLabel(self)
        self.pic.setFixedSize(32, 32)
        lay.addWidget(self.pic, 0, Qt.AlignmentFlag.AlignVCenter)
        mid = QVBoxLayout()
        mid.setSpacing(2)
        self.name = panelkit.ElideLabel("", self)
        mid.addWidget(self.name)
        line = QHBoxLayout()
        line.setSpacing(4)
        self.mark = QLabel(self)
        self.mark.setFixedSize(14, 14)
        line.addWidget(self.mark, 0, Qt.AlignmentFlag.AlignVCenter)
        self.status = panelkit.ElideLabel("", self, Qt.TextElideMode.ElideRight)
        panelkit.dim(self.status)
        self._status_palette = self.status.palette()
        line.addWidget(self.status, 1)
        mid.addLayout(line)
        self.bar = SlimBar(self)
        mid.addSpacing(2)
        mid.addWidget(self.bar)
        self.anyway = panelkit.link_button(self, QIcon(), T("Download anyway") + "…")
        self.anyway.setStyleSheet(self.anyway.styleSheet().replace("padding: 4px 8px 4px 0px", "padding: 0px"))
        self.anyway.setToolTip(T("If you download it anyway, it is at your own risk."))
        self.anyway.clicked.connect(lambda: panel.download_anyway(self.entry))
        mid.addWidget(self.anyway, 0, Qt.AlignmentFlag.AlignLeft)
        lay.addLayout(mid, 1)
        self.buttons = {}
        for key in ACTIONS:
            b = QToolButton(self)
            b.setIcon(action_icon(key))
            b.setIconSize(QSize(16, 16))
            b.setAutoRaise(True)
            b.setFixedSize(28, 28)
            b.setToolTip(action_text(key))
            b.setAccessibleName(action_text(key))
            b.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            b.clicked.connect(lambda _c=False, k=key: panel.act(self.entry, k))
            b.installEventFilter(self)
            b.hide()
            self.buttons[key] = b
            lay.addWidget(b, 0, Qt.AlignmentFlag.AlignVCenter)
        self.anyway.installEventFilter(self)
        self.show_entry()

    # --- what it shows -----------------------------------------------------
    def show_entry(self):
        e = self.entry
        self.name.set_full(e.name or e.url)
        self.setAccessibleName(e.name)
        icon = file_icon(e.name)
        self.pic.setPixmap(stopped_icon(icon) if e.state == "stopped" else icon.pixmap(32, 32))
        self.status.set_full(downloadlist.status(e))
        self.setAccessibleDescription(self.status.full)
        bad = e.state in ("failed", "stopped")
        pal = QPalette(self._status_palette)
        if bad:
            pal.setColor(QPalette.ColorRole.WindowText, panelkit.negative())
        self.status.setPalette(pal)
        if e.state == "done" and e.known:
            self.mark.setPixmap(_icon(("security-high",)).pixmap(14, 14))
            self.mark.show()
        else:
            self.mark.hide()
        self.bar.setVisible(e.live)
        self.bar.show_state(e.fraction(), e.state == "paused")
        self.sync_actions()

    def active(self):
        """The mouse is over the row, or the keyboard is on it or on one of its buttons."""
        f = QApplication.focusWidget()
        return self.underMouse() or (f is not None and (f is self or self.isAncestorOf(f)))

    def sync_actions(self):
        on = self.active()
        keys = SHOWN.get(self.entry.state, ())
        for key, b in self.buttons.items():
            # "Retry" of a download that failed is always there (the owner's preview)
            b.setVisible(key in keys and (on or (key == "retry" and self.entry.state == "failed"))
                         and (key != "retry" or self.panel.can_retry(self.entry)))
        link = self.entry.state == "stopped" and on
        if link != (not self.anyway.isHidden()):
            self.anyway.setVisible(link)
            # the row is a line taller or shorter: the popup follows (its foot stays in view)
            QTimer.singleShot(0, self.panel.refit)
        self.update()

    # --- events --------------------------------------------------------------
    def event(self, e):
        if e.type() in (QEvent.Type.HoverEnter, QEvent.Type.HoverLeave, QEvent.Type.FocusIn,
                        QEvent.Type.FocusOut):
            QTimer.singleShot(0, self._later_sync)
        return super().event(e)

    def _later_sync(self):
        try:
            self.sync_actions()
        except RuntimeError:
            pass

    def eventFilter(self, obj, e):
        if e.type() in (QEvent.Type.FocusIn, QEvent.Type.FocusOut):
            QTimer.singleShot(0, self._later_sync)
        return False

    def paintEvent(self, _e):
        if not self.active():
            return
        from . import polish
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QColor(self.palette().color(QPalette.ColorRole.Highlight))
        c.setAlphaF(0.16)
        p.setPen(QPen(self.palette().color(QPalette.ColorRole.Highlight), 1) if self.hasFocus()
                 else Qt.PenStyle.NoPen)
        p.setBrush(c)
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), polish.RADIUS, polish.RADIUS)
        p.end()

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.entry.state == "done":
            self.panel.act(self.entry, "open")

    def keyPressEvent(self, e):
        k = e.key()
        if k in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            first = {"running": "pause", "paused": "resume", "done": "open", "failed": "retry",
                     "cancelled": "retry"}.get(self.entry.state)
            if first:
                self.panel.act(self.entry, first)
            return
        if k == Qt.Key.Key_Delete and not self.entry.live:
            self.panel.act(self.entry, "remove")
            return
        if k == Qt.Key.Key_Menu or (k == Qt.Key.Key_F10 and e.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            self.panel.row_menu(self, self.mapToGlobal(self.rect().center()))
            return
        super().keyPressEvent(e)

    def contextMenuEvent(self, e):
        self.panel.row_menu(self, e.globalPos())


class DownloadsPanel(QWidget):
    """Popup of the toolbar's Downloads button."""

    def __init__(self, window):
        super().__init__(window)
        self.win = window
        self.rows = []
        top, right, bottom = panelkit.MARGINS[1], panelkit.MARGINS[2], panelkit.MARGINS[3]
        outer = QVBoxLayout(self)
        outer.setContentsMargins(panelkit.MARGINS[0] - ROW_PAD, top, right - ROW_PAD, bottom - 2)
        outer.setSpacing(6)

        def inset(layout):
            """The parts that are not rows: on the panel's own edges."""
            box = QWidget(self)
            layout.setContentsMargins(ROW_PAD, 0, ROW_PAD, 0)
            box.setLayout(layout)
            outer.addWidget(box)
            return box

        head, self.head_icon, self.title = panelkit.title_row(self, _icon(("download", "folder-download-symbolic")),
                                                              T("Downloads"))
        self.summary = panelkit.dim(QLabel(self), 1.0)
        self.summary.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        head.addWidget(self.summary)
        self.head = inset(head)

        self.list_box = QWidget(self)
        self.list_lay = QVBoxLayout(self.list_box)
        self.list_lay.setContentsMargins(0, 0, 0, 0)
        self.list_lay.setSpacing(2)
        outer.addWidget(self.list_box)

        empty = QVBoxLayout()
        empty.setSpacing(4)
        self.empty_icon = QLabel(self)
        self.empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_title = QLabel(T("No downloads yet"), self)
        f = self.empty_title.font()
        if f.pointSizeF() > 0:
            f.setPointSizeF(f.pointSizeF() * 1.1)
        self.empty_title.setFont(f)
        self.empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_text = panelkit.dim(QLabel(T("The files you download appear here, with their state."), self))
        self.empty_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_text.setWordWrap(True)
        empty.addSpacing(10)
        for w in (self.empty_icon, self.empty_title, self.empty_text):
            empty.addWidget(w)
        empty.addSpacing(10)
        self.empty = inset(empty)

        sep = QFrame(self)
        sep.setFrameShape(QFrame.Shape.HLine)
        sep_box = QHBoxLayout()
        sep_box.addWidget(sep)
        inset(sep_box)

        foot = QVBoxLayout()
        foot.setSpacing(0)
        self.show_all = panelkit.link_button(self, _icon(("view-list-details", "view-list-text", "download")),
                                             T("Show all downloads"))
        self.open_folder = panelkit.link_button(self, _icon(("folder-download", "folder-download-symbolic", "document-open")),
                                                T("Open the downloads folder"))
        self.clear = panelkit.link_button(self, _icon(("edit-clear-history", "edit-clear-all")), T("Clear the list"))
        self.clear.setToolTip(T("The downloads that ended leave the list; those in progress stay. "
                                "The files stay on the disk."))
        for b in (self.show_all, self.open_folder, self.clear):
            foot.addWidget(b, 0, Qt.AlignmentFlag.AlignLeft)
        inset(foot)
        self.setFixedWidth(WIDTH)

        self.show_all.clicked.connect(self._show_all)
        self.open_folder.clicked.connect(self._open_folder)
        self.clear.clicked.connect(self._clear)
        self.timer = QTimer(self)
        self.timer.setInterval(TICK_MS)
        self.timer.timeout.connect(self.update_rows)
        self.log.changed.connect(self._log_changed)

    # --- what the panel shows ------------------------------------------------
    @property
    def log(self):
        return self.win.app.download_log

    def entries(self):
        return self.log.shown(self.win.private)

    def refresh(self):
        """The list as it is now (each time the panel opens, and when it changes)."""
        entries = self.entries()
        if [r.entry for r in self.rows] != entries:
            focused = QApplication.focusWidget()
            keep = focused.entry if isinstance(focused, DownloadRow) else None
            for r in self.rows:
                r.hide()
                r.deleteLater()
            self.rows = []
            for e in entries:
                row = DownloadRow(self, e)
                self.list_lay.addWidget(row)
                self.rows.append(row)
                if e is keep:
                    row.setFocus(Qt.FocusReason.OtherFocusReason)
        else:
            for r in self.rows:
                r.show_entry()
        self.list_box.setVisible(bool(entries))
        self.empty.setVisible(not entries)
        if not entries:
            pm = _icon(("download", "folder-download-symbolic")).pixmap(48, 48)
            faded = QPixmap(pm.size())
            faded.setDevicePixelRatio(pm.devicePixelRatio())
            faded.fill(Qt.GlobalColor.transparent)
            p = QPainter(faded)
            p.setOpacity(0.35)
            p.drawPixmap(0, 0, pm)
            p.end()
            self.empty_icon.setPixmap(faded)
        self.clear.setVisible(any(not e.live for e in entries))
        self._summary()
        if any(e.live for e in entries) and self.isVisible():
            self.timer.start()

    def _summary(self):
        running = [e for e in self.entries() if e.state == "running"]
        text = ""
        if running:
            text = T("%d in progress") % len(running)
            speed = sum(e.speed or 0 for e in running)
            if speed:
                text += " · %s/s" % downloadlist.size_text(speed)
        self.summary.setText(text)
        self.summary.setVisible(bool(text))

    def update_rows(self):
        """While files arrive: the bytes, the speed, the time left."""
        if not self.isVisible():
            self.timer.stop()
            return
        self.log.tick()
        for r in self.rows:
            if r.entry.live or r.entry.state != getattr(r, "_shown_state", None):
                r.show_entry()
                r._shown_state = r.entry.state
        self._summary()
        if not any(r.entry.live for r in self.rows):
            self.timer.stop()

    def _log_changed(self):
        if self.isVisible():
            before = len(self.rows)
            self.refresh()
            if len(self.rows) != before:
                QTimer.singleShot(0, self.refit)

    def showEvent(self, e):
        super().showEvent(e)
        if any(r.entry.live for r in self.rows):
            self.timer.start()

    def refit(self):
        """The popup as tall as the panel now is (a row grew or shrank)."""
        try:
            if self.isVisible():
                self.win.fit_panel("downloads")
        except RuntimeError:
            pass

    def closed(self):
        self.timer.stop()

    # --- what a row does -----------------------------------------------------
    def can_retry(self, entry):
        from PyQt6.QtCore import QUrl
        return QUrl(entry.url).scheme() in ("http", "https", "ftp", "file")

    def _page(self):
        v = self.win.current_view()
        return v.page() if v is not None else None

    def _close(self):
        menu, _panel = self.win.panel_of("downloads")
        if menu is not None:
            menu.hide()

    def act(self, entry, key):
        app = self.win.app
        item = entry.item
        if key in ("pause", "resume", "cancel"):
            if item is None:
                return
            try:
                {"pause": item.pause, "resume": item.resume, "cancel": item.cancel}[key]()
            except RuntimeError:
                return
            entry.sync(app.download_path)
            self.log.changed.emit()
            self.refresh()
            return
        if key == "remove":
            self.log.remove(entry)
            if item is not None and item in app.downloads and not entry.live:
                app.downloads.remove(item)
            return
        if key == "retry":
            if app.retry_download(entry, self._page()):
                self.refresh()
            return
        from pathlib import Path
        path = Path(entry.path) if entry.path else None
        if key == "open" and path is not None and path.exists():
            self._close()
            app.handoff.open_file(path, self.win)
        elif key == "folder" and path is not None:
            self._close()
            if path.is_file():
                app.handoff.show_in_folder(path, self.win)
            else:
                app.handoff.open_file(path.parent if path.parent.exists() else app.download_dir(), self.win)

    def download_anyway(self, entry):
        """The same question as when it was stopped, "Cancel" already chosen."""
        self._close()
        app = self.win.app
        if entry.anyway is not None and entry.risk:
            app._ask_download_risk(entry.risk, entry.anyway)
        else:                       # stopped in an earlier session: through the checks again
            app.retry_download(entry, self._page())

    def row_menu(self, row, pos):
        """Every action of a download, on a right click (or the Menu key)."""
        from . import effects, handoff
        e = row.entry
        m = effects.fading(QMenu(self), self.win.app.config)
        m.setToolTipsVisible(True)
        for key in SHOWN.get(e.state, ()):
            if key == "retry" and not self.can_retry(e):
                continue
            m.addAction(action_icon(key), action_text(key)).triggered.connect(
                lambda _c=False, k=key: self.act(e, k))
        if e.state == "stopped":
            m.addAction(T("Download anyway") + "…").triggered.connect(lambda: self.download_anyway(e))
        from pathlib import Path
        path = Path(e.path) if e.path else None
        if e.state == "done" and path is not None and path.is_file():
            kind = handoff.kind_of(handoff.file_type(path))
            if kind in ("archive", "calendar"):
                found = handoff.app_for(handoff.file_type(path).name())
                if found is not None:
                    text = T("Add to calendar") if kind == "calendar" else T("Open with %s") % found.name
                    m.addAction(text).triggered.connect(
                        lambda: (self._close(), self.win.app.handoff.open_file(path, self.win)))
        if e.url:
            m.addSeparator()
            m.addAction(_icon(("edit-copy",)), T("Copy link address")).triggered.connect(
                lambda: QGuiApplication.clipboard().setText(e.url))
        if "remove" not in SHOWN.get(e.state, ()) and not e.live:
            m.addAction(action_icon("remove"), action_text("remove")).triggered.connect(
                lambda: self.act(e, "remove"))
        self._menu = m
        m.popup(pos)
        return m

    # --- the foot of the panel -----------------------------------------------
    def _show_all(self):
        self._close()
        self.win.app.show_downloads()

    def _open_folder(self):
        self._close()
        folder = self.win.app.download_dir()
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        self.win.app.handoff.open_file(folder, self.win)

    def _clear(self):
        self.win.app.clear_download_list(self.win.private)
        self.refresh()
        QTimer.singleShot(0, self.refit)
