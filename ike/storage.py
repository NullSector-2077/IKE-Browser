"""History and bookmarks (SQLite)."""

import sqlite3
import time

from .config import DATA_DIR


class Storage:
    def __init__(self, path=None):
        self.db = sqlite3.connect(str(path or DATA_DIR / "ike.sqlite"))
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS history(
                url TEXT PRIMARY KEY, title TEXT, last INTEGER, visits INTEGER);
            CREATE TABLE IF NOT EXISTS bookmarks(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT UNIQUE, title TEXT, folder TEXT DEFAULT '', added INTEGER);
            """
        )
        self.db.commit()

    # --- history -----------------------------------------------------
    def add_visit(self, url, title):
        if not url or url.startswith(("ike:", "about:", "data:", "view-source:")):
            return
        self.db.execute(
            "INSERT INTO history(url,title,last,visits) VALUES(?,?,?,1) "
            "ON CONFLICT(url) DO UPDATE SET title=excluded.title, "
            "last=excluded.last, visits=visits+1",
            (url, title or url, int(time.time())),
        )
        self.db.commit()

    def set_title(self, url, title):
        self.db.execute("UPDATE history SET title=? WHERE url=?", (title, url))
        self.db.commit()

    def history(self, query="", limit=500):
        like = "%" + query.replace("%", "") + "%"
        return self.db.execute(
            "SELECT url,title,last FROM history WHERE url LIKE ? OR title LIKE ? "
            "ORDER BY last DESC LIMIT ?", (like, like, limit)).fetchall()

    def suggest(self, text, limit=6):
        like = "%" + text.replace("%", "") + "%"
        return self.db.execute(
            "SELECT url,title FROM ("
            " SELECT url,title,1000000 AS w FROM bookmarks WHERE url LIKE ? OR title LIKE ?"
            " UNION ALL"
            " SELECT url,title,visits AS w FROM history WHERE url LIKE ? OR title LIKE ?"
            ") GROUP BY url ORDER BY MAX(w) DESC LIMIT ?",
            (like, like, like, like, limit)).fetchall()

    def import_history(self, rows):
        """rows: (url, title, unix_time, visits). Existing entries are kept."""
        n = 0
        for url, title, last, visits in rows:
            cur = self.db.execute(
                "INSERT OR IGNORE INTO history(url,title,last,visits) VALUES(?,?,?,?)",
                (url, title or url, int(last), int(visits or 1)))
            n += cur.rowcount
        self.db.commit()
        return n

    def delete_history(self, url):
        self.db.execute("DELETE FROM history WHERE url=?", (url,))
        self.db.commit()

    def clear_history(self):
        self.db.execute("DELETE FROM history")
        self.db.commit()

    # --- bookmarks ---------------------------------------------------
    def add_bookmark(self, url, title, folder=""):
        self.db.execute(
            "INSERT INTO bookmarks(url,title,folder,added) VALUES(?,?,?,?) "
            "ON CONFLICT(url) DO UPDATE SET title=excluded.title, folder=excluded.folder",
            (url, title or url, folder, int(time.time())))
        self.db.commit()

    def remove_bookmark(self, url):
        self.db.execute("DELETE FROM bookmarks WHERE url=?", (url,))
        self.db.commit()

    def is_bookmarked(self, url):
        return self.db.execute(
            "SELECT 1 FROM bookmarks WHERE url=?", (url,)).fetchone() is not None

    def bookmarks(self):
        return self.db.execute(
            "SELECT url,title,folder FROM bookmarks ORDER BY folder, id").fetchall()

    def export_bookmarks_html(self):
        out = ["<!DOCTYPE NETSCAPE-Bookmark-file-1>",
               '<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">',
               "<TITLE>Bookmarks</TITLE><H1>Bookmarks</H1><DL><p>"]
        for url, title, _folder in self.bookmarks():
            t = (title or url).replace("&", "&amp;").replace("<", "&lt;")
            out.append('<DT><A HREF="%s">%s</A>' % (url.replace('"', "%22"), t))
        out.append("</DL><p>")
        return "\n".join(out)

    def import_bookmarks_html(self, text):
        import re
        n = 0
        for m in re.finditer(r'<A[^>]*HREF="([^"]+)"[^>]*>(.*?)</A>', text, re.I | re.S):
            self.add_bookmark(m.group(1), re.sub(r"<[^>]+>", "", m.group(2)).strip())
            n += 1
        return n
