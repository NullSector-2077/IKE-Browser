"""The address bar: suggestions, completion and its own context menu."""

import json
import re

from PyQt6.QtCore import QCoreApplication, QEvent, QStringListModel, Qt, QTimer, QUrl
from PyQt6.QtGui import QAction, QColor, QInputMethodEvent, QPalette, QResizeEvent, QTextCharFormat, QTextFormat
from PyQt6.QtNetwork import QNetworkReply, QNetworkRequest
from PyQt6.QtWidgets import QCompleter, QLabel, QLineEdit, QStyle

from . import effects, polish
from .i18n import T
from .icons import themed as icon

_URLISH = re.compile(r"^([a-z][a-z0-9+.-]*:|localhost(:\d+)?(/|$)|[^\s/]+\.[^\s/.]{2,}([/:?#]|$)|\d+\.\d+\.\d+\.\d+)", re.I)


_LOOPBACK4 = re.compile(r"127\.\d{1,3}\.\d{1,3}\.\d{1,3}$")


def is_not_secure(url):
    """True for a page over plain http. Not for this computer's own addresses
    (localhost, 127.x.x.x, ::1: nothing leaves the machine), nor file:, about:,
    ike: and the other schemes: only http is "not secure"."""
    if url.scheme() != "http":
        return False
    host = url.host().lower().rstrip(".")
    return not (host == "localhost" or host.endswith(".localhost") or host == "::1" or _LOOPBACK4.match(host))


class UrlBar(QLineEdit):
    """Address bar with history and search suggestions."""

    def contextMenuEvent(self, event):
        from PyQt6.QtGui import QGuiApplication

        from .shields import strip_tracking
        m = self.createStandardContextMenu()
        first = m.actions()[0] if m.actions() else None
        clip = QGuiApplication.clipboard().text().strip()
        go = QAction(icon(("go-jump-locationbar", "go-jump-symbolic")), T("Paste and go"), m)
        go.setEnabled(bool(clip))
        go.triggered.connect(lambda: (self.setText(clip), self.win.navigate(clip, typed=True)))
        v = self.win.current_view()
        url = v.url().toString() if v and v.url().scheme() in ("http", "https") else ""
        clean = QAction(icon("edit-copy"), T("Copy clean link"), m)
        clean.setToolTip(T("Copy the address without tracking parameters"))
        clean.setEnabled(bool(url))
        clean.triggered.connect(
            lambda: (QGuiApplication.clipboard().setText(strip_tracking(url) or url),
                     self.win.osd(T("Link copied"), "edit-copy")))
        m.insertAction(first, go)
        m.insertAction(first, clean)
        m.insertSeparator(first)
        m.exec(event.globalPos())
        m.deleteLater()

    def __init__(self, window):
        super().__init__(window)
        self.win = window
        self.setClearButtonEnabled(True)
        self.setMinimumHeight(30)
        self._model = QStringListModel(self)
        self._completer = QCompleter(self._model, self)
        self._completer.setCompletionMode(QCompleter.CompletionMode.UnfilteredPopupCompletion)
        self._completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._completer.setMaxVisibleItems(12)
        # the list made here, as QCompleter makes its own, so that its panel
        # can be rounded (polish.round_list_popup, 1.1.23)
        from PyQt6.QtWidgets import QAbstractItemView, QListView
        rows = QListView()
        rows.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        rows.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        rows.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        rows.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._rows_view = rows                      # kept: the completer takes it, Python holds it too
        self._completer.setPopup(rows)
        self.setCompleter(self._completer)
        self._completer.activated[str].connect(self._picked)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(140)
        self._timer.timeout.connect(self._suggest)
        self.textEdited.connect(lambda _t: self._timer.start())
        self._reply = None
        self._local = []
        self._end = None               # the shield, at the far right inside the field (1.1.10)
        self._end_room = 0
        self._start = None             # the search engine, right after the lock (1.1.10)
        self._start_room = 0
        self._shifted = {}
        # "Not secure", small and muted, right after the lock and the engine, for plain http pages
        # (window.sync_urlbar); Breeze's negative text colour
        self._badge = QLabel(T("Not secure"), self)
        self._badge.setStyleSheet("QLabel { color: #da4453; font-size: 11px; padding: 0 3px; background: transparent; }")
        self._badge.setCursor(Qt.CursorShape.ArrowCursor)
        self._badge.hide()
        self.lock = self.addAction(icon(("globe", "web-browser-symbolic"), QStyle.StandardPixmap.SP_FileIcon),
                                   QLineEdit.ActionPosition.LeadingPosition)
        # "Translate page" in the address bar, as other browsers have it (1.1.6; the star of the
        # bookmarks went to the toolbar)
        self.translate_act = self.addAction(icon(("translate", "crow-translate-tray", "preferences-desktop-locale")),
                                            QLineEdit.ActionPosition.TrailingPosition)
        self.translate_act.setToolTip(T("Translate page"))
        self.translate_act.triggered.connect(window.translate_page)
        self.translate_act.setVisible(False)
        # shown only while the page is not at its usual zoom (window._zoom_sign); a click resets it
        self.zoom_act = self.addAction(icon("zoom-in", QStyle.StandardPixmap.SP_ArrowUp),
                                       QLineEdit.ActionPosition.TrailingPosition)
        self.zoom_act.setVisible(False)
        self.zoom_act.triggered.connect(lambda: window.zoom(0))
        # a site's question about a permission, answered with a click (quietperms.py, 1.1.24)
        self.perm_act = self.addAction(icon("dialog-question", QStyle.StandardPixmap.SP_MessageBoxQuestion),
                                       QLineEdit.ActionPosition.TrailingPosition)
        self.perm_act.setVisible(False)
        from . import quietperms
        self.perm_act.triggered.connect(lambda: quietperms.menu(window))
        self._pill = None
        if polish.part("url_pill"):
            # rounded, with an edge that lights up softly while the field is used (polish.py)
            self.setFrame(False)
            self.setContentsMargins(6, 0, 6, 0)
            self._clear_base()
            self._pill = effects.Glide(self, window.app.config, self.update, ms=150)
        if polish.part("url_popup"):
            self._rows = polish.SuggestionDelegate(self._completer.popup(), self._icon_for)
            self._completer.popup().setItemDelegate(self._rows)
            self._completer.popup().installEventFilter(self)
        # one radius and a light shadow, as the other popups (1.1.23)
        polish.round_list_popup(self._completer.popup())
        self.textChanged.connect(lambda _t: None if self.hasFocus() else self.highlight_domain())

    # --- the shield inside the field, at its right end (1.1.10) ---------------
    END_MARGIN = 6

    def set_end_widget(self, widget):
        """Put widget at the right end inside the field. Qt's own buttons on
        the right (clear, translate, zoom) move left of it, and the text stops
        before them."""
        self._end = widget
        widget.setParent(self)
        widget.setCursor(Qt.CursorShape.ArrowCursor)
        widget.show()
        self.place_end()

    def _icon_buttons(self):
        return [w for w in self.children()
                if w.isWidgetType() and w.metaObject().className() == "QLineEditIconButton"]

    def place_end(self):
        w = self._end
        if w is None:
            return
        h = max(16, min(w.sizeHint().height(), self.height() - 4))
        width = w.sizeHint().width()
        # the end of the field: the left one in a right-to-left language (1.1.20)
        x = self.END_MARGIN if self.isRightToLeft() else self.width() - self.END_MARGIN - width
        w.setGeometry(x, (self.height() - h) // 2, width, h)
        room = width + self.END_MARGIN
        if room != self._end_room:
            self._end_room = room
            self._margins()
            self._shifted.clear()
            # Qt puts its buttons back at the right edge, then they are moved left of the shield
            QCoreApplication.sendEvent(self, QResizeEvent(self.size(), self.size()))
        for b in self._icon_buttons():
            b.removeEventFilter(self)
            b.installEventFilter(self)
            self._shift(b)
        w.raise_()

    def _margins(self):
        start, end = self._start_room, max(0, self._end_room - 2)
        if self.isRightToLeft():
            start, end = end, start          # the margins are left and right, not start and end
        self.setTextMargins(start, 0, end, 0)

    def set_start_widget(self, widget):
        """Put widget right after the lock; the text starts after it."""
        self._start = widget
        widget.setParent(self)
        widget.setCursor(Qt.CursorShape.ArrowCursor)
        widget.show()
        self.place_start()

    def place_start(self):
        w = self._start
        if w is None:
            return
        lock = [b for b in self._icon_buttons() if b.defaultAction() is self.lock and not b.isHidden()]
        h = max(16, min(w.sizeHint().height(), self.height() - 4))
        width = w.sizeHint().width()
        if self.isRightToLeft():
            x = lock[0].geometry().left() - width - 1 if lock else self.width() - 4 - width
        else:
            x = lock[0].geometry().right() + 1 if lock else 4
        w.setGeometry(x, (self.height() - h) // 2, width, h)
        room = width + 2
        badge = self._badge
        if not badge.isHidden():
            bw, bh = badge.sizeHint().width(), min(badge.sizeHint().height(), self.height() - 4)
            bx = x - bw if self.isRightToLeft() else x + width
            badge.setGeometry(bx, (self.height() - bh) // 2, bw, bh)
            badge.raise_()
            room += bw
        if room != self._start_room:
            self._start_room = room
            self._margins()
        for b in lock:
            b.removeEventFilter(self)
            b.installEventFilter(self)
        w.raise_()

    def set_not_secure(self, flag):
        """Show or hide the "Not secure" label (plain http pages)."""
        if flag == (not self._badge.isHidden()):
            return
        self._badge.setVisible(flag)
        self.place_start()

    def _shift(self, b):
        """Move one of Qt's buttons on the right left of the shield, once
        for each place Qt gives it (the lock, on the left, stays)."""
        if (self._end is None or b.defaultAction() is self.lock
                or b.geometry() == self._shifted.get(b)):
            return
        to = b.geometry().translated(self._end_room if self.isRightToLeft() else -self._end_room, 0)
        self._shifted[b] = to            # first: moving it sends another Move
        b.move(to.topLeft())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._end is not None:
            self.place_end()
        if self._start is not None:
            self.place_start()

    # --- the site's domain in normal text, the rest of the address dimmed ---
    def domain_span(self, text=None):
        """(start, length) of the host name in the text, or None."""
        text = self.text() if text is None else text
        m = re.match(r"^([a-z][a-z0-9+.-]*)://(?:[^/?#@]*@)?(\[[^\]]*\]|[^/?#:]+)", text, re.I)
        if not m or m.group(1).lower() not in ("http", "https", "ftp", "ws", "wss"):
            return None
        return m.start(2), len(m.group(2))

    def _set_formats(self, formats):
        pos = self.cursorPosition()
        # QTextFormat(): the line edit reads the value as a QTextFormat only
        attrs = [QInputMethodEvent.Attribute(QInputMethodEvent.AttributeType.TextFormat,
                                             start - pos, length, QTextFormat(fmt))
                 for start, length, fmt in formats]
        QCoreApplication.sendEvent(self, QInputMethodEvent("", attrs))

    def highlight_domain(self):
        span = self.domain_span()
        if span is None or self.hasFocus():
            self._set_formats([])
            return
        pal = self.palette()
        # the field's own Base is see-through when it is rounded (polish.py): the one around it is used
        text_c, base = pal.color(QPalette.ColorRole.Text), polish.field_palette(self).color(QPalette.ColorRole.Base)
        dim = QColor(int(text_c.red() * 0.5 + base.red() * 0.5),
                     int(text_c.green() * 0.5 + base.green() * 0.5),
                     int(text_c.blue() * 0.5 + base.blue() * 0.5))
        fmt = QTextCharFormat()
        fmt.setForeground(dim)
        start, length = span
        end = start + length
        formats = [(0, start, fmt)]
        if end < len(self.text()):
            formats.append((end, len(self.text()) - end, fmt))
        self._set_formats(formats)

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.highlight_domain()
        if self._pill is not None:
            self._pill.to(0)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.PaletteChange:
            if self._pill is not None:
                self._clear_base()
            self.highlight_domain()

    # --- the rounded field (polish.py) ------------------------------------
    def _clear_base(self):
        """The field's own background is painted by paint_pill: Qt's is see-through."""
        pal = self.palette()
        if pal.color(QPalette.ColorRole.Base).alpha() == 0:
            return
        for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive, QPalette.ColorGroup.Disabled):
            pal.setColor(group, QPalette.ColorRole.Base, Qt.GlobalColor.transparent)
        self.setPalette(pal)

    def paintEvent(self, event):
        if self._pill is not None:
            polish.paint_pill(self, self._pill.value)
        super().paintEvent(event)
        edge = getattr(self, "site_edge", None)
        if edge is not None:
            # the site's colour as a thin outline over the field's own frame (sitetint.py)
            from PyQt6.QtCore import QRectF
            from PyQt6.QtGui import QPainter, QPen
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setPen(QPen(edge, 1.6))
            r = QRectF(self.rect()).adjusted(0.8, 0.8, -0.8, -0.8)
            # 1.1.23: the one corner radius (polish.RADIUS, was 3)
            radius = r.height() / 2 if self._pill is not None else min(polish.RADIUS, r.height() / 2)
            p.drawRoundedRect(r, radius, radius)
            p.end()

    # --- the suggestions -----------------------------------------------------
    def _icon_for(self, text):
        """The site's icon for an address, a magnifier for a search."""
        if _URLISH.match(text):
            return self.win.site_icon(text if "://" in text else "https://" + text)
        if polish.part("engine_icon"):
            # a search: the search engine's own icon, when it is known (its site was opened once)
            try:
                engine = self.win.app.config.engine()
                ic = self.win.app.favicons.icon(engine["url"].replace("{q}", ""))
                if not ic.isNull():
                    return ic
            except (KeyError, TypeError, AttributeError):
                pass
        return icon("edit-find", QStyle.StandardPixmap.SP_FileDialogContentsView)

    def eventFilter(self, obj, event):
        if (event.type() == QEvent.Type.Move and obj.parent() is self
                and obj.metaObject().className() == "QLineEditIconButton"):
            if obj.defaultAction() is self.lock:
                self.place_start()       # the engine follows the lock
            else:
                self._shift(obj)
            return False
        if event.type() == QEvent.Type.Show and obj is self._completer.popup():
            effects.fade_in(obj, self.win.app.config)
        elif event.type() == QEvent.Type.Hide and obj is self._completer.popup():
            self._rows.clear()
        return False

    def _picked(self, text):
        self.setText(text)
        self.win.navigate(text, typed=True)

    def _suggest(self):
        text = self.text().strip()
        if len(text) < 2:
            self._model.setStringList([])
            return
        app = self.win.app
        self._local = [] if self.win.private else [u for u, _t in app.storage.suggest(text)]
        self._model.setStringList(self._local)
        if self._local:
            self._completer.complete()
        if self._reply is not None:
            self._reply.abort()
            self._reply = None
        engine = app.config.engine()
        if (not app.config["search_suggestions"] or not engine.get("suggest")
                or _URLISH.match(text)):
            return
        url = QUrl(engine["suggest"].replace("{q}", bytes(QUrl.toPercentEncoding(text)).decode()))
        req = QNetworkRequest(url)
        req.setRawHeader(b"User-Agent", app.shields.user_agent().encode())
        self._reply = app.network.get(req)
        self._reply.finished.connect(lambda r=self._reply, t=text: self._got(r, t))

    def _got(self, reply, asked):
        if reply is self._reply:
            self._reply = None
        ok = reply.error() == QNetworkReply.NetworkError.NoError
        data = bytes(reply.readAll()) if ok else b""
        reply.deleteLater()
        if not ok or self.text().strip() != asked or not self.hasFocus():
            return
        out = []
        try:
            js = json.loads(data.decode("utf-8", "replace"))
            if isinstance(js, list) and len(js) > 1 and isinstance(js[1], list):
                items = js[1]
            elif isinstance(js, dict):
                items = js.get("data", {}).get("items", [])
            else:
                items = js if isinstance(js, list) else []
            for it in items:
                if isinstance(it, str):
                    out.append(it)
                elif isinstance(it, dict):
                    v = it.get("phrase") or it.get("value") or it.get("q")
                    if v:
                        out.append(str(v))
                elif isinstance(it, list) and it and isinstance(it[0], str):
                    out.append(it[0])
        except (ValueError, AttributeError):
            return
        merged = self._local[:4] + [s for s in out[:8] if s not in self._local]
        if merged:
            self._model.setStringList(merged)
            self._completer.complete()

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self._set_formats([])               # while editing, the whole address in normal text
        if self._pill is not None:
            self._pill.to(1)
        if event.reason() in (Qt.FocusReason.MouseFocusReason,
                              Qt.FocusReason.ShortcutFocusReason,
                              Qt.FocusReason.TabFocusReason):
            QTimer.singleShot(0, self.selectAll)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.win.sync_urlbar()
            v = self.win.current_view()
            if v:
                v.setFocus()
            return
        super().keyPressEvent(event)
