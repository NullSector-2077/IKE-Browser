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


def _fields(buf):
    """The fields of a protocol buffer message: [(number, bytes)] for the
    length-delimited ones (all that a CRX header holds); others skipped."""
    out, i = [], 0

    def varint():
        nonlocal i
        value = shift = 0
        while True:
            if i >= len(buf) or shift > 63:
                raise ValueError("damaged extension package header")
            b = buf[i]
            i += 1
            value |= (b & 0x7F) << shift
            shift += 7
            if not b & 0x80:
                return value
    while i < len(buf):
        key = varint()
        kind = key & 7
        if kind == 2:
            n = varint()
            if i + n > len(buf):
                raise ValueError("damaged extension package header")
            out.append((key >> 3, buf[i:i + n]))
            i += n
        elif kind == 0:
            varint()
        elif kind == 1:
            i += 8
        elif kind == 5:
            i += 4
        else:
            raise ValueError("damaged extension package header")
    return out


def crx_id_of(public_key):
    """The extension id that belongs to a signing key (DER): the first 16
    bytes of its SHA-256, written with the letters a-p."""
    import hashlib
    return "".join("abcdefghijklmnop"[int(c, 16)] for c in hashlib.sha256(public_key).hexdigest()[:32])


def verify_crx(ext_id, data):
    """A store package must be a CRX3 signed by the key of the extension asked
    for: its id names it, and the signature covers the whole archive (review
    of 1.1.19, L8; until then only the connection's TLS vouched for it).
    Raises ValueError otherwise."""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
    if len(data) < 12 or data[:4] != b"Cr24" or struct.unpack("<I", data[4:8])[0] != 3:
        raise ValueError("not a signed (CRX3) extension package")
    size = struct.unpack("<I", data[8:12])[0]
    header, archive = data[12:12 + size], data[12 + size:]
    if len(header) != size:
        raise ValueError("damaged extension package")
    fields = _fields(header)
    signed = [v for n, v in fields if n == 10000]
    if len(signed) != 1:
        raise ValueError("the extension package is not signed")
    crx_id = [v for n, v in _fields(signed[0]) if n == 1]
    if len(crx_id) != 1 or len(crx_id[0]) != 16:
        raise ValueError("the extension package is not signed")
    named = "".join("abcdefghijklmnop"[c >> 4] + "abcdefghijklmnop"[c & 15] for c in crx_id[0])
    if named != ext_id:
        raise ValueError("the package is of another extension")
    message = b"CRX3 SignedData\x00" + struct.pack("<I", len(signed[0])) + signed[0] + archive
    for number, proof in fields:
        if number not in (2, 3):
            continue
        parts = dict(_fields(proof))
        key, sig = parts.get(1, b""), parts.get(2, b"")
        if crx_id_of(key) != ext_id:
            continue                      # the store's own key, or another
        try:
            pub = serialization.load_der_public_key(key)
            if number == 2 and isinstance(pub, rsa.RSAPublicKey):
                pub.verify(sig, message, padding.PKCS1v15(), hashes.SHA256())
                return True
            if number == 3 and isinstance(pub, ec.EllipticCurvePublicKey):
                pub.verify(sig, message, ec.ECDSA(hashes.SHA256()))
                return True
        except (InvalidSignature, ValueError):
            pass
    raise ValueError("the extension package's signature is not valid")


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
        try:
            verify_crx(ext_id, data)
        except ValueError as exc:
            self.finished.emit(False, T("This is not a valid extension: %s") % exc)
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
