"""The address bar: suggestions, completion and its own context menu."""

import json
import re

from PyQt6.QtCore import QCoreApplication, QEvent, QStringListModel, Qt, QTimer, QUrl
from PyQt6.QtGui import QAction, QColor, QInputMethodEvent, QPalette, QTextCharFormat, QTextFormat
from PyQt6.QtNetwork import QNetworkReply, QNetworkRequest
from PyQt6.QtWidgets import QCompleter, QLineEdit, QStyle

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
        self.cyber = None            # the Cyber theme's look (see cyber.py), or None
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
        text_c, base = pal.color(QPalette.ColorRole.Text), pal.color(QPalette.ColorRole.Base)
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

    def paintEvent(self, event):
        if self.cyber is not None:
            from . import cyber
            cyber.paint_field(self, self.cyber, self.hasFocus())    # the frame; the text is Qt's
        super().paintEvent(event)

    def set_cyber(self, look):
        """Give the field the Cyber theme's cut frame, or (None) the desktop's own."""
        from PyQt6.QtGui import QPalette
        if (look is None) == (self.cyber is None) and look is None:
            return
        self.cyber = look
        self.setFrame(look is None)
        pal = QPalette()                                  # the inherited colours
        if look is not None:
            pal = QPalette(self.palette())
            for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive, QPalette.ColorGroup.Disabled):
                pal.setColor(group, QPalette.ColorRole.Base, Qt.GlobalColor.transparent)
        self.setPalette(pal)
        self.setTextMargins(6 if look is not None else 0, 0, 6 if look is not None else 0, 0)
        self.update()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.PaletteChange:
            self.highlight_domain()

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
