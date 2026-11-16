"""Import from other browsers, local backup / restore, permission manager.

Other browsers' profiles are never opened in place: the databases are copied
to a temporary folder first and read from there, so nothing is modified.
"""

import json
import shutil
import sqlite3
import tempfile
import time
import zipfile
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from .config import CONFIG_DIR, DATA_DIR
from .i18n import T
from .osinfo import WINDOWS

CHROMIUM_DIRS = {
    "Chromium": ".config/chromium", "Google Chrome": ".config/google-chrome",
    "Brave": ".config/BraveSoftware/Brave-Browser", "Vivaldi": ".config/vivaldi",
    "Microsoft Edge": ".config/microsoft-edge", "Opera": ".config/opera",
}
FIREFOX_DIRS = {
    "Firefox": ".mozilla/firefox", "LibreWolf": ".librewolf", "Zen": ".zen",
    "Floorp": ".floorp", "Waterfox": ".waterfox",
}
if WINDOWS:
    # the same browsers' folders on Windows (relative to the user's folder)
    CHROMIUM_DIRS = {
        "Chromium": "AppData/Local/Chromium/User Data",
        "Google Chrome": "AppData/Local/Google/Chrome/User Data",
        "Brave": "AppData/Local/BraveSoftware/Brave-Browser/User Data",
        "Vivaldi": "AppData/Local/Vivaldi/User Data",
        "Microsoft Edge": "AppData/Local/Microsoft/Edge/User Data",
        "Opera": "AppData/Roaming/Opera Software",
    }
    FIREFOX_DIRS = {
        "Firefox": "AppData/Roaming/Mozilla/Firefox/Profiles",
        "LibreWolf": "AppData/Roaming/librewolf/Profiles", "Zen": "AppData/Roaming/zen/Profiles",
        "Floorp": "AppData/Roaming/Floorp/Profiles", "Waterfox": "AppData/Roaming/Waterfox/Profiles",
    }


def find_sources(home=None):
    """[(label, kind, profile_dir)] for every browser profile found."""
    home = Path(home or Path.home())
    out = []
    for name, rel in FIREFOX_DIRS.items():
        base = home / rel
        if base.is_dir():
            for places in sorted(base.glob("*/places.sqlite")):
                out.append(("%s — %s" % (name, places.parent.name), "firefox", places.parent))
    for name, rel in CHROMIUM_DIRS.items():
        base = home / rel
        if base.is_dir():
            for prof in sorted(base.iterdir()):
                if (prof / "Bookmarks").is_file() or (prof / "History").is_file():
                    out.append(("%s — %s" % (name, prof.name), "chromium", prof))
    return out


def _copy_db(path):
    """Copy an SQLite database (with its WAL) and open the copy read-only."""
    tmp = Path(tempfile.mkdtemp(prefix="ice-import-"))
    for suffix in ("", "-wal"):
        src = Path(str(path) + suffix)
        if src.exists():
            shutil.copy2(src, tmp / (path.name + suffix))
    return tmp, sqlite3.connect("file:%s?mode=ro" % (tmp / path.name), uri=True)


def import_firefox(profile, storage, bookmarks=True, history=True):
    counts = {"bookmarks": 0, "history": 0}
    places = Path(profile) / "places.sqlite"
    if not places.exists():
        return counts
    tmp, db = _copy_db(places)
    try:
        if bookmarks:
            for url, title in db.execute(
                    "SELECT p.url, COALESCE(b.title, p.title) FROM moz_bookmarks b "
                    "JOIN moz_places p ON p.id = b.fk WHERE b.type = 1"):
                if url and url.startswith(("http://", "https://")):
                    storage.add_bookmark(url, title or url)
                    counts["bookmarks"] += 1
        if history:
            rows = db.execute(
                "SELECT url, title, last_visit_date, visit_count FROM moz_places "
                "WHERE visit_count > 0 AND last_visit_date IS NOT NULL "
                "ORDER BY last_visit_date DESC LIMIT 20000").fetchall()
            counts["history"] = storage.import_history(
                (u, t, int(d / 1000000), c) for u, t, d, c in rows
                if u and u.startswith(("http://", "https://")))
    finally:
        db.close()
        shutil.rmtree(tmp, ignore_errors=True)
    return counts


def _walk_chromium(node, out):
    if node.get("type") == "url" and node.get("url", "").startswith(("http://", "https://")):
        out.append((node["url"], node.get("name") or node["url"]))
    for child in node.get("children", []) or []:
        _walk_chromium(child, out)


def import_chromium(profile, storage, bookmarks=True, history=True):
    counts = {"bookmarks": 0, "history": 0}
    profile = Path(profile)
    if bookmarks and (profile / "Bookmarks").is_file():
        data = json.loads((profile / "Bookmarks").read_text("utf-8", "replace"))
        found = []
        for root in (data.get("roots") or {}).values():
            if isinstance(root, dict):
                _walk_chromium(root, found)
        for url, title in found:
            storage.add_bookmark(url, title)
        counts["bookmarks"] = len(found)
    if history and (profile / "History").is_file():
        tmp, db = _copy_db(profile / "History")
        try:
            rows = db.execute("SELECT url, title, last_visit_time, visit_count FROM urls "
                              "WHERE visit_count > 0 ORDER BY last_visit_time DESC "
                              "LIMIT 20000").fetchall()
            # Chromium time: microseconds since 1601-01-01
            counts["history"] = storage.import_history(
                (u, t, int(d / 1000000 - 11644473600), c) for u, t, d, c in rows
                if u and u.startswith(("http://", "https://")))
        finally:
            db.close()
            shutil.rmtree(tmp, ignore_errors=True)
    return counts


class ImportDialog(QDialog):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self.setWindowTitle(T("Import from another browser"))
        self.resize(520, 260)
        lay = QVBoxLayout(self)
        self.sources = find_sources()
        self.combo = QComboBox()
        for label, _kind, _path in self.sources:
            self.combo.addItem(label)
        lay.addWidget(QLabel(T("Browser profile found on this computer:")))
        lay.addWidget(self.combo)
        self.bm = QCheckBox(T("Bookmarks"))
        self.hi = QCheckBox(T("History"))
        self.bm.setChecked(True)
        self.hi.setChecked(True)
        lay.addWidget(self.bm)
        lay.addWidget(self.hi)
        go = QPushButton(T("Import"))
        go.clicked.connect(self._run)
        go.setEnabled(bool(self.sources))
        if not self.sources:
            lay.addWidget(QLabel(T("No other browser profile was found.")))
        lay.addWidget(go)
        note = QLabel(T("The other browser is not modified: its data is copied and read. "
                        "Saved passwords cannot be read from other browsers directly; export "
                        "them to a CSV file there and use the button below."))
        note.setWordWrap(True)
        lay.addWidget(note)
        row = QHBoxLayout()
        pw = QPushButton(T("Import passwords from CSV…"))
        html = QPushButton(T("Import bookmarks from HTML…"))
        pw.clicked.connect(self._passwords)
        html.clicked.connect(self._html)
        row.addWidget(pw)
        row.addWidget(html)
        lay.addLayout(row)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _run(self):
        _label, kind, path = self.sources[self.combo.currentIndex()]
        fn = import_firefox if kind == "firefox" else import_chromium
        try:
            c = fn(path, self.app.storage, self.bm.isChecked(), self.hi.isChecked())
        except Exception as exc:
            QMessageBox.warning(self, "I.K.E.", T("Import failed: %s") % exc)
            return
        self.app.refresh_windows()
        QMessageBox.information(self, "I.K.E.", T("Imported %d bookmarks and %d history entries.")
                                % (c["bookmarks"], c["history"]))

    def _passwords(self):
        pm = self.app.passwords
        if not pm.ensure_unlocked(self):
            return
        path, _f = QFileDialog.getOpenFileName(self, T("Import passwords"), "", "CSV (*.csv)")
        if path:
            with open(path, encoding="utf-8-sig", errors="replace") as fh:
                n = pm.vault.import_csv(fh.read())
            QMessageBox.information(self, "I.K.E.", T("%d logins imported.") % n)

    def _html(self):
        path, _f = QFileDialog.getOpenFileName(self, T("Import bookmarks"), "",
                                               "HTML (*.html *.htm)")
        if path:
            n = self.app.storage.import_bookmarks_html(Path(path).read_text("utf-8", "replace"))
            self.app.refresh_windows()
            QMessageBox.information(self, "I.K.E.", T("%d bookmarks imported.") % n)


# --- backup -------------------------------------------------------------
BACKUP_FILES = (("settings.json", CONFIG_DIR), ("ice.sqlite", DATA_DIR), ("vault.bin", DATA_DIR))


def make_backup(target, storage=None):
    if storage is not None:
        storage.db.commit()
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("ice-backup.json", json.dumps({"format": 1, "created": int(time.time())}))
        for name, folder in BACKUP_FILES:
            p = folder / name
            if p.exists():
                z.write(p, name)
    return target


def restore_backup(source):
    """Returns the list of restored files. Takes effect at the next start."""
    restored = []
    with zipfile.ZipFile(source) as z:
        names = set(z.namelist())
        if "ice-backup.json" not in names:
            raise ValueError("not an I.K.E. backup")
        for name, folder in BACKUP_FILES:
            if name in names:
                folder.mkdir(parents=True, exist_ok=True)
                tmp = folder / (name + ".restore")
                tmp.write_bytes(z.read(name))
                tmp.replace(folder / name)
                restored.append(name)
    return restored


# --- permissions --------------------------------------------------------
class PermissionsDialog(QDialog):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self.setWindowTitle(T("Site permissions") + " — I.K.E.")
        self.resize(680, 440)
        lay = QVBoxLayout(self)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([T("Site"), T("Permission"), T("Status")])
        self.tree.setRootIsDecorated(False)
        self.tree.setColumnWidth(0, 300)
        self.tree.setColumnWidth(1, 200)
        self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        lay.addWidget(self.tree, 1)
        row = QHBoxLayout()
        one = QPushButton(T("Reset selected"))
        allb = QPushButton(T("Reset all"))
        one.clicked.connect(lambda: self._reset(False))
        allb.clicked.connect(lambda: self._reset(True))
        row.addWidget(one)
        row.addWidget(allb)
        row.addStretch(1)
        lay.addLayout(row)
        lay.addWidget(QLabel(T("A reset permission is asked again the next time the site needs it. "
                               "Kinds that must always be refused are set in Settings → Privacy.")))
        self.perms = []
        self.fill()

    def fill(self):
        from PyQt6.QtWebEngineCore import QWebEnginePermission as P
        self.tree.clear()
        self.perms = []
        for profile in self.app.all_profiles():
            try:
                found = profile.listAllPermissions()
            except Exception:
                found = []
            for perm in found:
                if perm.state() == P.State.Ask:
                    continue
                name = perm.permissionType().name
                state = T("Allowed") if perm.state() == P.State.Granted else T("Blocked")
                it = QTreeWidgetItem(self.tree, [perm.origin().toString(), name, state])
                it.setData(0, Qt.ItemDataRole.UserRole, len(self.perms))
                self.perms.append(perm)

    def _reset(self, everything):
        items = ([self.tree.topLevelItem(i) for i in range(self.tree.topLevelItemCount())]
                 if everything else self.tree.selectedItems())
        for it in items:
            self.perms[it.data(0, Qt.ItemDataRole.UserRole)].reset()
        self.fill()
