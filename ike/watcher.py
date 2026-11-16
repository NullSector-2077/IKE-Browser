"""Page watcher: "tell me when this page changes".

The user picks a page, or one part of it (a price, a headline), from the
right-click menu, and how often to check: every 15 minutes, hour, 6 hours or
day. While I.K.E. is open, each due page is loaded in the background, one at
a time, in a private profile with the usual protections (no cookies of the
user, nothing counted in the shield, nothing in the history). The visible text
of the page or of the part is compared with the previous check; when it
differs, a desktop notification says so and the page is marked as changed in
Tools → Watched pages.

Only the pages the user chose are checked; nothing runs when there are none.
Stored in settings.json (``page_watches``): address, CSS selector of the part,
name, interval, times and a short excerpt of the last text.
"""

import hashlib
import json
import time

from PyQt6.QtCore import QObject, Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineScript
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from .i18n import T

INTERVALS = ((15, "Every 15 minutes"), (60, "Every hour"), (360, "Every 6 hours"),
             (1440, "Once a day"))
TICK_MS = 60 * 1000
SETTLE_MS = 3000            # time given to scripts that fill the page after it loads
TIMEOUT_MS = 45 * 1000
EXCERPT = 300
_WORLD = QWebEngineScript.ScriptWorldId.ApplicationWorld
# stored as codes, shown translated
ERRORS = {"load": "Could not load the page", "missing": "The part was not found", "timeout": "No answer"}

_TEXT_JS = r"""(function (sel) {
  var e = sel ? document.querySelector(sel) : document.body;
  if (!e) return null;
  var t = e.innerText;
  if (!t || !t.trim()) t = e.textContent || '';
  return t.replace(/\s+/g, ' ').trim().slice(0, 50000);
})(%s)"""

# CSS selector of the element at a point (CSS pixels): an id when it is unique,
# otherwise the tag path with :nth-of-type from the nearest such id or <body>.
_PICK_JS = r"""(function (x, y) {
  var e = document.elementFromPoint(x, y);
  if (!e || e === document.documentElement) return null;
  if (e === document.body) return {sel: '', text: ''};
  function esc(s) { return window.CSS && CSS.escape ? CSS.escape(s) : s; }
  var parts = [], n = e;
  while (n && n.nodeType === 1 && n !== document.body && n !== document.documentElement) {
    if (n.id && document.querySelectorAll('#' + esc(n.id)).length === 1) {
      parts.unshift('#' + esc(n.id)); break;
    }
    var i = 1, s = n;
    while ((s = s.previousElementSibling)) if (s.tagName === n.tagName) i++;
    parts.unshift(n.tagName.toLowerCase() + ':nth-of-type(' + i + ')');
    n = n.parentElement;
  }
  if (parts.length && parts[0].charAt(0) !== '#') parts.unshift('body');
  var t = (e.innerText || e.textContent || '').replace(/\s+/g, ' ').trim();
  return {sel: parts.join(' > '), text: t.slice(0, 300)};
})(%d, %d)"""


def _digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class Watcher(QObject):
    """Checks the watched pages that are due, one at a time."""

    changed = pyqtSignal()          # list or state of a watch changed (for the window)

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self._profile = None
        self._page = None
        self._current = None
        self.timer = QTimer(self)
        self.timer.setInterval(TICK_MS)
        self.timer.timeout.connect(self.check_due)
        self._deadline = QTimer(self)
        self._deadline.setSingleShot(True)
        self._deadline.setInterval(TIMEOUT_MS)
        self._deadline.timeout.connect(lambda: self._done(None, "timeout"))
        self.settings_changed()

    @property
    def watches(self):
        return self.app.config["page_watches"]

    def active(self):
        return bool(self.app.config["page_watch_on"]) and bool(self.watches)

    def settings_changed(self):
        if self.active():
            if not self.timer.isActive():
                self.timer.start()
                QTimer.singleShot(5000, self.check_due)
        else:
            self.timer.stop()

    # --- the list --------------------------------------------------------
    def add(self, url, selector, name, interval, text):
        w = {"url": url, "selector": selector or "", "name": name or url,
             "interval": int(interval), "added": int(time.time()), "last_check": int(time.time()),
             "last_change": 0, "hash": _digest(text or ""), "excerpt": (text or "")[:EXCERPT],
             "changed": False, "status": "ok"}
        self.watches.append(w)
        self._save()
        self.settings_changed()
        return w

    def remove(self, w):
        if w in self.watches:
            self.watches.remove(w)
            self._save()
        self.settings_changed()

    def seen(self, w):
        if w.get("changed"):
            w["changed"] = False
            self._save()

    def _save(self):
        self.app.config.save()
        self.changed.emit()

    # --- checking ----------------------------------------------------------
    def due(self, now=None):
        now = now or time.time()
        return [w for w in self.watches
                if now - w.get("last_check", 0) >= int(w.get("interval", 60)) * 60]

    def check_due(self):
        if self._current is not None or not self.active():
            return
        due = self.due()
        if due:
            self.check(min(due, key=lambda w: w.get("last_check", 0)))

    def check(self, w):
        """Load the page in the background and compare its text."""
        if self._current is not None:
            return False
        if self._profile is None:
            self._profile = self.app.shields.make_profile(private=True, parent=self, quiet=True)
        self._current = w
        self._page = QWebEnginePage(self._profile, self)
        self._page.setAudioMuted(True)
        self._page.loadFinished.connect(self._loaded)
        self._deadline.start()
        self._page.load(QUrl(w["url"]))
        return True

    def _loaded(self, ok):
        if self._current is None:
            return
        if not ok:
            self._done(None, "load")
            return
        page = self._page
        sel = self._current.get("selector") or ""
        QTimer.singleShot(SETTLE_MS, lambda: page.runJavaScript(
            _TEXT_JS % json.dumps(sel), _WORLD,
            lambda text: self._done(text, None if text is not None else "missing")
            if page is self._page else None))

    def _done(self, text, error):
        w, page = self._current, self._page
        if w is None:
            return
        self._deadline.stop()
        self._current = self._page = None
        if page is not None:
            page.loadFinished.disconnect()
            page.deleteLater()
        if self._profile is not None:       # every check starts clean
            self._profile.cookieStore().deleteAllCookies()
            self._profile.clearHttpCache()
        w["last_check"] = int(time.time())
        if error or text is None:
            w["status"] = error or "missing"
        else:
            w["status"] = "ok"
            h = _digest(text)
            if h != w.get("hash"):
                w["hash"] = h
                w["excerpt"] = text[:EXCERPT]
                w["last_change"] = w["last_check"]
                w["changed"] = True
                self.app._desktop_notify(T("“%s” has changed.") % w.get("name", w["url"]))
        self._save()
        QTimer.singleShot(0, self.check_due)        # the next one that is due, if any


def pick_and_watch(view, pos, part):
    """From the right-click menu: watch this page, or the part under the pointer."""
    win = view.window_ref
    app = win.app
    url = view.url().toString()
    if not part:
        view.page().runJavaScript(_TEXT_JS % '""', _WORLD,
                                  lambda text: _ask(win, url, "", text or "", view.title()))
        return
    zoom = view.zoomFactor() or 1.0
    js = _PICK_JS % (int(pos.x() / zoom), int(pos.y() / zoom))

    def got(res):
        if not res or res.get("sel") is None:
            app._notify(T("Nothing to watch there."))
            return
        if not res["sel"]:
            pick_and_watch(view, pos, False)
            return
        _ask(win, url, res["sel"], res.get("text") or "", view.title())
    view.page().runJavaScript(js, _WORLD, got)


def _ask(win, url, selector, text, title):
    dlg = WatchAddDialog(win, url, selector, text, title)
    win.app._dialogs["watch-add"] = dlg
    dlg.show()


class WatchAddDialog(QDialog):
    def __init__(self, win, url, selector, text, title):
        super().__init__(win)
        self.app = win.app
        self.url, self.selector, self.text = url, selector, text
        self.setWindowTitle(T("Notify me when this changes"))
        lay = QVBoxLayout(self)
        f = QFormLayout()
        self.name = QLineEdit(title or url, self)
        f.addRow(T("Name"), self.name)
        what = QLabel(self)
        what.setWordWrap(True)
        what.setTextFormat(Qt.TextFormat.PlainText)
        short = text if len(text) <= 160 else text[:159] + "…"
        what.setText(T("The whole page") if not selector else (short or T("(no text yet)")))
        f.addRow(T("Watch"), what)
        self.interval = QComboBox(self)
        for minutes, label in INTERVALS:
            self.interval.addItem(T(label), minutes)
        self.interval.setCurrentIndex(1)
        f.addRow(T("Check"), self.interval)
        lay.addLayout(f)
        note = QLabel(T("Checked only while I.K.E. is open, in the background, like a private window "
                        "(without your cookies). You get a notification when the text changes."), self)
        note.setWordWrap(True)
        lay.addWidget(note)
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
                               self)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        lay.addWidget(box)
        self.resize(460, self.sizeHint().height())

    def accept(self):
        self.app.watcher.add(self.url, self.selector, self.name.text().strip(),
                             self.interval.currentData(), self.text)
        self.app._notify(T("Watching “%s”.") % (self.name.text().strip() or self.url))
        super().accept()


class WatchesDialog(QDialog):
    """Tools → Watched pages."""

    COLS = ("Name", "Watch", "Check", "Last change", "State")

    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self.w = app.watcher
        self.setWindowTitle(T("Watched pages"))
        self.resize(760, 420)
        lay = QVBoxLayout(self)
        self.on = QCheckBox(T("Check the watched pages while I.K.E. is open"), self)
        self.on.setChecked(bool(app.config["page_watch_on"]))
        self.on.toggled.connect(self._toggle)
        lay.addWidget(self.on)
        self.table = QTableWidget(0, len(self.COLS), self)
        self.table.setHorizontalHeaderLabels([T(c) for c in self.COLS])
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for c in (2, 3, 4):
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        self.table.doubleClicked.connect(lambda *_: self._open())
        lay.addWidget(self.table, 1)
        self.empty = QLabel(T("No pages are watched. Right-click a page, or a part of it such as a "
                              "price, and choose “Notify me when this page changes…” or “Notify me "
                              "when this part changes…”."), self)
        self.empty.setWordWrap(True)
        lay.addWidget(self.empty)
        row = QHBoxLayout()
        self.open_btn = QPushButton(T("Open"), self)
        self.check_btn = QPushButton(T("Check now"), self)
        self.remove_btn = QPushButton(T("Remove"), self)
        self.interval = QComboBox(self)
        for minutes, label in INTERVALS:
            self.interval.addItem(T(label), minutes)
        for wdg in (self.open_btn, self.check_btn, self.remove_btn):
            row.addWidget(wdg)
        row.addStretch(1)
        row.addWidget(self.interval)
        lay.addLayout(row)
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        box.rejected.connect(self.close)
        lay.addWidget(box)
        self.open_btn.clicked.connect(self._open)
        self.check_btn.clicked.connect(self._check)
        self.remove_btn.clicked.connect(self._remove)
        self.interval.activated.connect(self._interval)
        self.table.currentCellChanged.connect(lambda *_: self._selected())
        self.w.changed.connect(self.refresh)
        self.refresh()

    def _toggle(self, on):
        self.app.config["page_watch_on"] = bool(on)
        self.app.config.save()
        self.w.settings_changed()

    def _sel(self):
        r = self.table.currentRow()
        ws = self.w.watches
        return ws[r] if 0 <= r < len(ws) else None

    def _selected(self):
        w = self._sel()
        for b in (self.open_btn, self.check_btn, self.remove_btn, self.interval):
            b.setEnabled(w is not None)
        if w is not None:
            i = self.interval.findData(int(w.get("interval", 60)))
            self.interval.setCurrentIndex(max(0, i))

    def refresh(self):
        r0 = self.table.currentRow()
        ws = self.w.watches
        self.table.setRowCount(len(ws))
        labels = dict(INTERVALS)
        for r, w in enumerate(ws):
            when = (time.strftime("%Y-%m-%d %H:%M", time.localtime(w["last_change"]))
                    if w.get("last_change") else "—")
            status = w.get("status", "ok")
            if self.w._current is w:
                status = T("Checking…")
            elif status == "ok":
                status = T("Changed") if w.get("changed") else T("No change")
            else:
                status = T(ERRORS.get(status, ERRORS["load"]))
            vals = (w.get("name") or w["url"],
                    T("The whole page") if not w.get("selector") else (w.get("excerpt") or "")[:80],
                    T(labels.get(int(w.get("interval", 60)), "Every hour")), when, status)
            for c, val in enumerate(vals):
                it = self.table.item(r, c)
                if it is None:
                    it = QTableWidgetItem()
                    self.table.setItem(r, c, it)
                it.setText(val)
                f = it.font()
                f.setBold(bool(w.get("changed")))
                it.setFont(f)
            self.table.item(r, 0).setToolTip(w["url"])
            self.table.item(r, 1).setToolTip(w.get("excerpt") or "")
        self.empty.setVisible(not ws)
        if ws:
            self.table.setCurrentCell(min(max(r0, 0), len(ws) - 1), 0)
        self._selected()

    def _open(self):
        w = self._sel()
        if w is None:
            return
        win = self.app.active_window() or self.app.new_window(open_default=False)
        win.add_tab(w["url"])
        self.w.seen(w)

    def _check(self):
        w = self._sel()
        if w is not None and self.w.check(w):
            self.refresh()

    def _remove(self):
        w = self._sel()
        if w is not None:
            self.w.remove(w)

    def _interval(self, _i):
        w = self._sel()
        if w is not None:
            w["interval"] = int(self.interval.currentData())
            self.w._save()

    def closeEvent(self, event):
        try:
            self.w.changed.disconnect(self.refresh)
        except TypeError:
            pass
        super().closeEvent(event)
