"""The command bar (F2): type a few letters and go to a command of the menus,
an open tab, a bookmark, a page of the history or a page of the Settings.

F2, as in Vivaldi, and not Ctrl+K: many sites (GitHub, Slack, Discord,
Notion...) use Ctrl+K themselves, and a shortcut of the window would take it
from them.
"""

from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout

from .i18n import T

MAX_ROWS = 40


def _plain(text):
    return text.replace("&&", "\0").replace("&", "").replace("\0", "&").replace("…", "").strip()


def menu_commands(window):
    """[(label, path, shortcut, action)] of the window's menus, submenus included."""
    out = []

    def walk(menu, path):
        for act in menu.actions():
            if act.isSeparator() or not act.isVisible():
                continue
            sub = act.menu()
            label = _plain(act.text())
            if sub is not None:
                walk(sub, path + [label])
            elif label and act.isEnabled():
                out.append((label, " › ".join(path), act.shortcut().toString(), act))
    for act in window.menuBar().actions():
        if act.menu() is not None:
            walk(act.menu(), [_plain(act.text())])
    return out


class CommandBar(QDialog):
    def __init__(self, window):
        super().__init__(window, Qt.WindowType.Popup)
        self.win = window
        self.setWindowTitle(T("Command bar"))
        self.resize(min(640, max(420, window.width() - 80)), 440)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        self.edit = QLineEdit(self)
        self.edit.setPlaceholderText(T("Type a command, a tab, a bookmark or a setting"))
        self.edit.setClearButtonEnabled(True)
        self.list = QListWidget(self)
        self.list.setUniformItemSizes(True)
        self.hint = QLabel(T("↑ ↓ to choose, Enter to go, Esc to close"), self)
        self.hint.setEnabled(False)
        lay.addWidget(self.edit)
        lay.addWidget(self.list, 1)
        lay.addWidget(self.hint)
        self._entries = self._collect()
        self.edit.textChanged.connect(self._filter)
        self.edit.returnPressed.connect(self._go)
        self.list.itemActivated.connect(lambda _i: self._go())
        self.list.itemClicked.connect(lambda _i: self._go())
        self.edit.installEventFilter(self)
        self._filter("")

    def _collect(self):
        win = self.win
        app = win.app
        out = []                 # (kind, label, detail, icon, run)
        for label, path, keys, act in menu_commands(win):
            if act is getattr(win, "act_command_bar", None):
                continue
            out.append((T("Command"), label, path + ("   " + keys if keys else ""), act.icon(),
                        lambda a=act: a.trigger()))
        for w in app.windows:
            if getattr(w, "popup", False):
                continue
            for v in w.views:
                title = v.title() or getattr(v, "saved_title", "") or T("New tab")
                url = v.url().toDisplayString() or (getattr(v, "pending_url", "") or "")
                ic = v.last_icon if not v.last_icon.isNull() else QIcon()
                out.append((T("Open tab"), title, url, ic, lambda w=w, v=v: self._show_tab(w, v)))
        try:
            marks = list(app.storage.bookmarks())
        except Exception:
            marks = []
        for url, title, _folder in marks:
            out.append((T("Bookmark"), title or url, url, None, lambda u=url: win.navigate(u)))
        from .dialogs import SettingsDialog
        names = {"general": T("General"), "appearance": T("Appearance"), "newtab": T("New tab page"),
                 "search": T("Search"), "privacy": T("Privacy and protection"),
                 "components": T("Components and extensions"), "userscripts": T("User scripts"),
                 "downloads": T("Downloads")}
        for key in SettingsDialog.PAGES:
            if key in names:
                out.append((T("Settings"), names[key], "", None, lambda k=key: win.open_settings(k)))
        return out

    def _show_tab(self, w, v):
        if v in w.views:
            w.set_current(v)
            w.raise_()
            w.activateWindow()

    def eventFilter(self, obj, event):
        if obj is self.edit and event.type() == QEvent.Type.KeyPress and self.list.count() \
                and event.key() in (Qt.Key.Key_Down, Qt.Key.Key_Up):
            step = 1 if event.key() == Qt.Key.Key_Down else -1
            self.list.setCurrentRow((self.list.currentRow() + step) % self.list.count())
            return True
        return super().eventFilter(obj, event)

    def _filter(self, text):
        words = text.lower().split()
        rows = [e for e in self._entries
                if all(w in (e[1] + " " + e[2] + " " + e[0]).lower() for w in words)]
        if len(text.strip()) >= 2 and not self.win.private:
            try:
                seen = {e[2] for e in rows}
                for url, title in self.win.app.storage.suggest(text.strip())[:8]:
                    if url not in seen:
                        rows.append((T("History"), title or url, url, None,
                                     lambda u=url: self.win.navigate(u)))
            except Exception:
                pass
        self.list.clear()
        for kind, label, detail, ic, run in rows[:MAX_ROWS]:
            item = QListWidgetItem(ic or QIcon(), "%s   ·   %s%s" % (label, kind, ("\n" + detail) if detail else ""))
            item.setData(Qt.ItemDataRole.UserRole, run)
            self.list.addItem(item)
        if self.list.count():
            self.list.setCurrentRow(0)

    def _go(self):
        item = self.list.currentItem()
        if item is None:
            return
        run = item.data(Qt.ItemDataRole.UserRole)
        self.accept()
        run()


def open_bar(window):
    bar = CommandBar(window)
    g = window.geometry()
    bar.move(window.mapToGlobal(window.rect().topLeft()).x() + (g.width() - bar.width()) // 2,
             window.mapToGlobal(window.rect().topLeft()).y() + 70)
    from . import effects
    effects.fade_in(bar, window.app.config)
    bar.edit.setFocus()
    bar.exec()
    return bar
