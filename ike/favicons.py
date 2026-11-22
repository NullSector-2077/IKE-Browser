"""Site icons, stored per host so bookmarks can show them."""

import hashlib
import time
from urllib.parse import urlsplit

from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, QObject, QUrl, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtNetwork import QNetworkReply, QNetworkRequest

from .config import DATA_DIR
from .storage import Deferred, checkpoint, connect


def host_of(url):
    try:
        return (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""



def icon_format(data):
    """PNG or ICO, told by their first bytes, or None. Any other format is not
    decoded: this runs in the browser itself, outside the engine's sandbox,
    where Qt would try every image plugin installed (SVG, and on Plasma many
    more) on bytes from a site never visited (review of 1.1.19, L7)."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "PNG"
    if data[:4] == b"\x00\x00\x01\x00":
        return "ICO"
    return None

class Favicons(QObject, Deferred):
    changed = pyqtSignal()          # a new icon is available

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.db = connect(DATA_DIR / "favicons.sqlite")
        self.db.execute("CREATE TABLE IF NOT EXISTS icons("
                        "host TEXT PRIMARY KEY, png BLOB, ts INTEGER)")
        self.db.commit()
        self._cache = {}
        self._tried = set()
        self._stored = {}               # host -> hash of the PNG written last (review of 1.1.20, L6)

    def icon(self, url):
        """QIcon for the site of url, or a null icon when none is known."""
        host = host_of(url)
        if not host:
            return QIcon()
        if host not in self._cache:
            row = self.db.execute("SELECT png FROM icons WHERE host=?", (host,)).fetchone()
            pm = QPixmap()
            if row and row[0]:
                pm.loadFromData(row[0], "PNG")
            self._cache[host] = QIcon(pm) if not pm.isNull() else QIcon()
        return self._cache[host]

    def store(self, url, icon):
        host = host_of(url)
        if not host or icon.isNull():
            return
        pm = icon.pixmap(32, 32)
        if pm.isNull():
            return
        data = QByteArray()
        buf = QBuffer(data)
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        pm.save(buf, "PNG")
        buf.close()
        png = bytes(data)
        mark = hashlib.blake2b(png, digest_size=16).digest()    # not the picture: memory (review 4, N12)
        if self._stored.get(host) == mark:
            return                        # the same picture again (a site redrawing its icon)
        self._stored[host] = mark
        self.db.execute("INSERT INTO icons(host,png,ts) VALUES(?,?,?) ON CONFLICT(host) "
                        "DO UPDATE SET png=excluded.png, ts=excluded.ts",
                        (host, png, int(time.time())))
        self.commit_soon()
        known = host in self._cache and not self._cache[host].isNull()
        self._cache[host] = QIcon(pm)
        if not known:
            self.changed.emit()

    def fetch(self, url):
        """Ask the site for /favicon.ico once per session (bookmarks not visited yet)."""
        host = host_of(url)
        if not host or host in self._tried or not self.icon(url).isNull():
            return
        self._tried.add(host)
        scheme = urlsplit(url).scheme if urlsplit(url).scheme in ("http", "https") else "https"
        req = QNetworkRequest(QUrl("%s://%s/favicon.ico" % (scheme, urlsplit(url).netloc)))
        req.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,
                         QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy)
        req.setRawHeader(b"User-Agent", self.app.shields.user_agent().encode())
        from . import doh
        if doh.active():                          # a redirect would be looked up in clear by Qt
            req.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,
                             QNetworkRequest.RedirectPolicy.ManualRedirectPolicy)
        doh.get(self.app.network, req, lambda reply: self._got(url, reply))

    def _got(self, url, reply):
        if reply is None:
            return                                # no address from encrypted DNS

        def done():
            ok = reply.error() == QNetworkReply.NetworkError.NoError
            data = bytes(reply.readAll()) if ok else b""
            reply.deleteLater()
            pm = QPixmap()
            kind = icon_format(data)
            if kind and len(data) < 512 * 1024 and pm.loadFromData(data, kind):
                self.store(url, QIcon(pm))
        reply.finished.connect(done)

    def clear(self):
        self.db.execute("DELETE FROM icons")
        checkpoint(self.db)
        self._cache.clear()
