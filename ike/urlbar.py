"""The address bar: suggestions, completion and its own context menu."""

import json
import re

from PyQt6.QtCore import QCoreApplication, QEvent, QStringListModel, Qt, QTimer, QUrl
from PyQt6.QtGui import QAction, QColor, QInputMethodEvent, QPalette, QTextCharFormat, QTextFormat
from PyQt6.QtNetwork import QNetworkReply, QNetworkRequest
from PyQt6.QtWidgets import QCompleter, QLineEdit, QStyle

from . import effects, polish
from .i18n import T
from .icons import themed as icon

_URLISH = re.compile(r"^([a-z][a-z0-9+.-]*:|localhost(:\d+)?(/|$)|[^\s/]+\.[^\s/.]{2,}([/:?#]|$)|\d+\.\d+\.\d+\.\d+)", re.I)


class UrlBar(QLineEdit):
    """Address bar with history and search suggestions."""

    def contextMenuEvent(self, event):
        from PyQt6.QtGui import QGuiApplication

        from .shields import strip_tracking
        m = self.createStandardContextMenu()
        first = m.actions()[0] if m.actions() else None
        clip = QGuiApplication.clipboard().text().strip()
        go = QAction(icon("go-jump-locationbar"), T("Paste and go"), m)
        go.setEnabled(bool(clip))
        go.triggered.connect(lambda: (self.setText(clip), self.win.navigate(clip)))
        v = self.win.current_view()
        url = v.url().toString() if v and v.url().scheme() in ("http", "https") else ""
        clean = QAction(icon("edit-copy"), T("Copy clean link"), m)
        clean.setToolTip(T("Copy the address without tracking parameters"))
        clean.setEnabled(bool(url))
        clean.triggered.connect(
            lambda: QGuiApplication.clipboard().setText(strip_tracking(url) or url))
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
        self.setCompleter(self._completer)
        self._completer.activated[str].connect(self._picked)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(140)
        self._timer.timeout.connect(self._suggest)
        self.textEdited.connect(lambda _t: self._timer.start())
        self._reply = None
        self._local = []
        self.lock = self.addAction(icon("globe", QStyle.StandardPixmap.SP_FileIcon),
                                   QLineEdit.ActionPosition.LeadingPosition)
        self.star = self.addAction(icon("bookmark-new", QStyle.StandardPixmap.SP_DialogApplyButton),
                                   QLineEdit.ActionPosition.TrailingPosition)
        self.star.setToolTip(T("Bookmark this page"))
        self.star.triggered.connect(window.toggle_bookmark)
        # shown only while the page is not at its usual zoom (window._zoom_sign); a click resets it
        self.zoom_act = self.addAction(icon("zoom-in", QStyle.StandardPixmap.SP_ArrowUp),
                                       QLineEdit.ActionPosition.TrailingPosition)
        self.zoom_act.setVisible(False)
        self.zoom_act.triggered.connect(lambda: window.zoom(0))
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
        self.textChanged.connect(lambda _t: None if self.hasFocus() else self.highlight_domain())

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
        if event.type() == QEvent.Type.Show and obj is self._completer.popup():
            effects.fade_in(obj, self.win.app.config)
        elif event.type() == QEvent.Type.Hide and obj is self._completer.popup():
            self._rows.clear()
        return False

    def _picked(self, text):
        self.setText(text)
        self.win.navigate(text)

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
