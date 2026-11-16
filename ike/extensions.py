"""Installing Chrome extensions (Manifest V3) from the Chrome Web Store.

The store page cannot install into I.K.E. by itself (its button talks to a
Chrome-only API), so I.K.E. downloads the extension package (.crx) from the
store's public download address, unpacks it and hands it to the engine.
Enabling an extension uses the engine call that crashed in our tests with
Qt 6.11; it goes through IkeApp.enable_extension, which survives a crash.
"""

import io
import json
import re
import shutil
import struct
import zipfile

from PyQt6.QtCore import QObject, QUrl, pyqtSignal
from PyQt6.QtNetwork import QNetworkReply, QNetworkRequest

from .config import DATA_DIR
from .i18n import T

STORE_HOME = "https://chromewebstore.google.com/"
_ID = re.compile(r"^https://(?:chromewebstore\.google\.com|chrome\.google\.com/webstore)/"
                 r"detail/(?:[^/]+/)?([a-p]{32})(?:[/?#]|$)")
MAX_CRX = 150 * 1024 * 1024


def store_id(url):
    """Extension id if url is a Chrome Web Store detail page, else None."""
    m = _ID.match(url or "")
    return m.group(1) if m else None


def crx_to_zip(data):
    """Strip the CRX header and return the ZIP archive inside."""
    if data[:2] == b"PK":
        return data
    if data[:4] != b"Cr24":
        raise ValueError("not a Chrome extension package")
    version = struct.unpack("<I", data[4:8])[0]
    if version == 3:
        header = struct.unpack("<I", data[8:12])[0]
        start = 12 + header
    elif version == 2:
        key, sig = struct.unpack("<II", data[8:16])
        start = 16 + key + sig
    else:
        raise ValueError("unknown CRX version %d" % version)
    if data[start:start + 2] != b"PK":
        raise ValueError("damaged extension package")
    return data[start:]


def unpack(ext_id, data):
    """Unpack a CRX/ZIP into the data folder; returns (folder, manifest)."""
    target = DATA_DIR / "extensions-src" / ext_id
    shutil.rmtree(target, ignore_errors=True)
    target.mkdir(parents=True)
    with zipfile.ZipFile(io.BytesIO(crx_to_zip(data))) as z:
        total = 0
        for info in z.infolist():
            name = info.filename
            if name.startswith("/") or ".." in name.split("/") or "\\" in name:
                raise ValueError("unsafe path in extension: %s" % name)
            total += info.file_size
            if total > 400 * 1024 * 1024:
                raise ValueError("extension is too large")
        z.extractall(target)
    manifest = json.loads((target / "manifest.json").read_text("utf-8-sig"))
    return target, manifest


class StoreInstaller(QObject):
    """Downloads and installs one extension at a time."""

    finished = pyqtSignal(bool, str)      # ok, message

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self._reply = None
        self._wired = False

    def busy(self):
        return self._reply is not None

    def crx_url(self, ext_id):
        from PyQt6.QtWebEngineCore import qWebEngineChromiumVersion
        return (self.app.config["crx_url"].replace("{id}", ext_id)
                .replace("{version}", qWebEngineChromiumVersion()))

    def install(self, ext_id):
        if self._reply is not None:
            return
        req = QNetworkRequest(QUrl(self.crx_url(ext_id)))
        req.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,
                         QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy)
        req.setRawHeader(b"User-Agent", self.app.shields.user_agent().encode())
        self._reply = self.app.network.get(req)
        self._reply.finished.connect(lambda r=self._reply, i=ext_id: self._downloaded(r, i))

    def _downloaded(self, reply, ext_id):
        self._reply = None
        ok = reply.error() == QNetworkReply.NetworkError.NoError
        data = bytes(reply.readAll()) if ok else b""
        err = reply.errorString()
        reply.deleteLater()
        if not ok or not data:
            self.finished.emit(False, T("Could not download the extension: %s") % err)
            return
        if len(data) > MAX_CRX:
            self.finished.emit(False, T("Could not download the extension: %s") % "too large")
            return
        self.install_data(ext_id, data)

    def install_data(self, ext_id, data):
        try:
            folder, manifest = unpack(ext_id, data)
        except Exception as exc:
            self.finished.emit(False, T("This is not a valid extension: %s") % exc)
            return
        name = manifest.get("name", ext_id)
        if name.startswith("__MSG_"):
            name = self._localized(folder, manifest, name) or ext_id
        if manifest.get("manifest_version") != 3:
            shutil.rmtree(folder, ignore_errors=True)
            self.finished.emit(False, T(
                "“%s” uses Manifest V%s. The engine only runs Manifest V3 extensions.")
                % (name, manifest.get("manifest_version")))
            return
        mgr = self.app.extension_manager()
        if mgr is None:
            self.finished.emit(False, T("This engine version has no extension support."))
            return
        if not self._wired:
            mgr.installFinished.connect(self._installed)
            self._wired = True
        self._pending = name
        mgr.installExtension(str(folder))

    @staticmethod
    def _localized(folder, manifest, name):
        key = name[6:].rstrip("_")
        for loc in (manifest.get("default_locale", "en"), "en"):
            try:
                msgs = json.loads((folder / "_locales" / loc / "messages.json").read_text("utf-8-sig"))
                for k, v in msgs.items():
                    if k.lower() == key.lower():
                        return v.get("message")
            except Exception:
                continue
        return None

    def _installed(self, info):
        name = getattr(self, "_pending", None) or info.name()
        self._pending = None
        if info.error():
            self.finished.emit(False, T("The engine refused the extension: %s") % info.error())
            return
        if not info.isEnabled() and not getattr(self, "skip_enable", False):
            # may crash the engine on some Qt versions; a marker is written first
            self.app.enable_extension(self.app.extension_manager(), info)
        self.finished.emit(True, T("Extension installed: %s") % name)
