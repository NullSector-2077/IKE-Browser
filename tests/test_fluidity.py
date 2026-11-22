"""Speed and fluidity of 1.1.23 (docs/review/tests-and-performance.md,
"1.1.23, speed and fluidity"): the interface does the same with less work.

- The new tab page's clock writes its text only when it changes and wakes
  up at the next minute, not every second.
- The picture of a tab for its preview card is taken when the mouse comes
  to the tabs, or once a page has loaded, not at every change of tab.
- The loading mark of a tab repaints that tab only, from pictures drawn once.
- History and site icons: SQLite in WAL mode, synchronous=NORMAL; a backup
  still has the last visits, and clearing leaves nothing in the -wal file.
"""

import sqlite3
import sys
import zipfile

from conftest import APP

sys.path.insert(0, str(APP))


# --- history and icons: WAL ---------------------------------------------------

def test_history_and_icons_in_wal_mode(tmp_path, monkeypatch):
    from ike import favicons, importer, storage
    s = storage.Storage(tmp_path / "ike.sqlite")
    assert s.db.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert s.db.execute("PRAGMA synchronous").fetchone()[0] == 1          # NORMAL
    monkeypatch.setattr(favicons, "DATA_DIR", tmp_path)
    icons = favicons.Favicons(None)
    assert icons.db.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert icons.db.execute("PRAGMA synchronous").fetchone()[0] == 1
    # the last visit is in the -wal file only, and still reaches a backup
    s.add_visit("https://example.org/last", "Last")
    s.flush()
    assert (tmp_path / "ike.sqlite-wal").stat().st_size > 0
    monkeypatch.setattr(importer, "DATA_DIR", tmp_path)
    monkeypatch.setattr(importer, "BACKUP_FILES", (("ike.sqlite", tmp_path),))
    target = tmp_path / "backup.zip"
    importer.make_backup(target, s)
    out = tmp_path / "unpacked"
    with zipfile.ZipFile(target) as z:
        z.extract("ike.sqlite", out)
    copy = sqlite3.connect(str(out / "ike.sqlite"))
    assert copy.execute("SELECT title FROM history WHERE url=?", ("https://example.org/last",)).fetchone() == ("Last",)
    copy.close()
    # cleared: nothing of it left in the -wal file
    s.add_visit("https://example.org/secret-page", "Secret")
    s.flush()
    s.clear_history()
    wal = tmp_path / "ike.sqlite-wal"
    assert not wal.exists() or wal.stat().st_size == 0
    assert s.history() == []
    s.db.close()
    # a restore never meets the -wal file of the database it replaces
    (tmp_path / "ike.sqlite-wal").write_bytes(b"left by a crash")
    (tmp_path / "ike.sqlite-shm").write_bytes(b"left by a crash")
    assert importer.restore_backup(target) == ["ike.sqlite"]
    assert not (tmp_path / "ike.sqlite-wal").exists() and not (tmp_path / "ike.sqlite-shm").exists()
    again = storage.Storage(tmp_path / "ike.sqlite")
    assert [u for u, _t, _l in again.history()] == ["https://example.org/last"]
    again.db.close()
