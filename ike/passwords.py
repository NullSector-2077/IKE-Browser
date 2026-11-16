"""Encrypted password vault, autofill bridge, generator and passkey prompts.

The vault is one file encrypted with AES-256-GCM; the key is derived from the
master password with scrypt. Nothing is readable on disk without the master
password, including the list of sites.
"""

import base64
import csv
import io
import json
import os
import secrets
import string
import sys
import time

from PyQt6.QtCore import QFile, QIODevice, QObject, Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from .config import DATA_DIR, RES_DIR
from .i18n import T

SCRYPT_N, SCRYPT_R, SCRYPT_P = 2 ** 15, 8, 1
_AAD = b"ike-vault-1"               # associated data sealed with every vault file
WORLD = 1  # QWebEngineScript.ApplicationWorld


def crypto_available():
    try:
        import cryptography  # noqa: F401
        return True
    except Exception:
        return False


def generate_password(length=20, upper=True, digits=True, symbols=True):
    pools = [string.ascii_lowercase]
    if upper:
        pools.append(string.ascii_uppercase)
    if digits:
        pools.append(string.digits)
    if symbols:
        pools.append("!@#$%^&*()-_=+[]{};:,.?")
    length = max(length, len(pools))
    while True:
        pw = "".join(secrets.choice("".join(pools)) for _ in range(length))
        if all(any(c in pool for c in pw) for pool in pools):
            return pw


def _b64(b):
    return base64.b64encode(b).decode()


def write_private(path, text):
    """Write a file that only its owner can read, from the first moment (it
    never exists, even briefly, with the usual permissions)."""
    path = str(path)
    try:
        os.unlink(path)                  # an older file may have other permissions
    except OSError:
        pass
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


CLIPBOARD_SECONDS = 45
# Windows' own way to say the same: clipboard formats that keep the text out
# of the clipboard history (Win+V) and of the clipboard synchronised between
# the user's devices. Qt creates a format of exactly this name from the MIME
# type below.
WINDOWS_MIME = 'application/x-qt-windows-mime;value="%s"'
WINDOWS_CLIPBOARD_HINTS = (("ExcludeClipboardContentFromMonitorProcessing", b"\0\0\0\0"),
                           ("CanIncludeInClipboardHistory", b"\0\0\0\0"),
                           ("CanUploadToCloudClipboard", b"\0\0\0\0"))


def copy_secret(text):
    """Put a password on the clipboard: marked so that the desktop's clipboard
    history (Klipper and others that follow the same hint) does not keep it,
    and taken off again after a while if it is still there."""
    from PyQt6.QtCore import QMimeData
    clipboard = QGuiApplication.clipboard()
    data = QMimeData()
    data.setText(text)
    data.setData("x-kde-passwordManagerHint", b"secret")
    if sys.platform == "win32":
        for name, value in WINDOWS_CLIPBOARD_HINTS:
            data.setData(WINDOWS_MIME % name, value)
    clipboard.setMimeData(data)

    def clear():
        if clipboard.text() == text:
            clipboard.clear()
    QTimer.singleShot(CLIPBOARD_SECONDS * 1000, clear)


class Vault:
    def __init__(self, path=None):
        self.path = path or DATA_DIR / "vault.bin"
        self.entries = None      # None while locked
        self._key = None
        self._salt = None

    def exists(self):
        return self.path.exists()

    @property
    def unlocked(self):
        return self.entries is not None

    def _derive(self, master, salt):
        from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
        return Scrypt(salt=salt, length=32, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P).derive(
            master.encode("utf-8"))

    def create(self, master):
        self._salt = os.urandom(16)
        self._key = self._derive(master, self._salt)
        self.entries = []
        self.save()

    def unlock(self, master):
        from cryptography.exceptions import InvalidTag
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        try:
            blob = json.loads(self.path.read_text("utf-8"))
            salt = base64.b64decode(blob["salt"])
            key = self._derive(master, salt)
            nonce, data = base64.b64decode(blob["nonce"]), base64.b64decode(blob["data"])
        except (ValueError, KeyError, OSError):
            return False
        try:
            plain = AESGCM(key).decrypt(nonce, data, _AAD)
        except InvalidTag:
            return False
        self.entries = json.loads(plain.decode("utf-8"))
        self._key, self._salt = key, salt
        return True

    def lock(self):
        self.entries = None
        self._key = None

    def change_master(self, master):
        self._salt = os.urandom(16)
        self._key = self._derive(master, self._salt)
        self.save()

    def save(self):
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        nonce = os.urandom(12)
        data = AESGCM(self._key).encrypt(nonce, json.dumps(self.entries).encode("utf-8"),
                                         _AAD)
        blob = {"v": 1, "kdf": "scrypt", "n": SCRYPT_N, "r": SCRYPT_R, "p": SCRYPT_P,
                "cipher": "aes-256-gcm", "salt": _b64(self._salt), "nonce": _b64(nonce),
                "data": _b64(data)}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        write_private(tmp, json.dumps(blob))
        tmp.replace(self.path)

    # --- entries -----------------------------------------------------
    def find(self, origin):
        return [e for e in self.entries or [] if e["origin"] == origin]

    def put(self, origin, username, password):
        for e in self.entries:
            if e["origin"] == origin and e["username"] == username:
                if e["password"] == password:
                    return False
                e["password"] = password
                e["changed"] = int(time.time())
                self.save()
                return True
        self.entries.append({"origin": origin, "username": username, "password": password,
                             "changed": int(time.time())})
        self.save()
        return True

    def remove(self, entry):
        if entry in self.entries:
            self.entries.remove(entry)
            self.save()

    def import_csv(self, text):
        n = 0
        reader = csv.DictReader(io.StringIO(text))
        for row in reader:
            row = {(k or "").strip().lower(): (v or "") for k, v in row.items()}
            url = row.get("url") or row.get("origin") or row.get("login_uri") or row.get("website")
            user = row.get("username") or row.get("login_username") or row.get("user") or ""
            pw = row.get("password") or row.get("login_password")
            if not url or not pw:
                continue
            origin = origin_of(url)
            if origin and self.put(origin, user, pw):
                n += 1
        return n

    def export_csv(self):
        out = io.StringIO()
        w = csv.writer(out)
        w.writerow(["url", "username", "password"])
        for e in self.entries:
            w.writerow([e["origin"], e["username"], e["password"]])
        return out.getvalue()


def origin_of(url):
    """scheme://host[:port] of an address, the key of saved logins ("" if none).

    The port is left out only when it is the scheme's own default (80 for
    http, 443 for https): http://site:443 and https://site:80 stay distinct."""
    from urllib.parse import urlsplit
    if "://" not in url:
        url = "https://" + url
    try:
        p = urlsplit(url)
        scheme, host, port = p.scheme.lower(), p.hostname, p.port
    except ValueError:                   # a port that is not a number or out of range
        return ""
    if scheme not in ("http", "https") or not host:
        return ""
    if ":" in host:                      # IPv6
        host = "[%s]" % host
    default = 80 if scheme == "http" else 443
    return "%s://%s%s" % (scheme, host.lower(), (":%d" % port) if port and port != default else "")


class PageBridge(QObject):
    """Object exposed to the isolated-world script of one page."""

    fillRequested = pyqtSignal(str)

    def __init__(self, manager, page):
        super().__init__(page)
        self.manager = manager
        self.page = page

    @pyqtSlot(result=str)
    def logins(self):
        return self.manager.logins_json(self.page)

    @pyqtSlot(str, str)
    def captured(self, username, password):
        self.manager.captured(self.page, username, password)

    cssFetched = pyqtSignal(str, bool, str)

    @pyqtSlot(str, str)
    def fetchCss(self, ident, url):
        """Dark mode: fetch a style sheet of another site that the page cannot read.

        Only style sheets, only over http(s), without cookies, at most 3 MB.
        """
        from PyQt6.QtCore import QUrl
        from PyQt6.QtNetwork import QNetworkReply, QNetworkRequest
        target = QUrl(url)
        app = self.manager.app
        if target.scheme() not in ("http", "https") or not getattr(self.page, "_dark_on", False):
            self.cssFetched.emit(ident, False, "")
            return
        req = QNetworkRequest(target)
        req.setRawHeader(b"Accept", b"text/css,*/*;q=0.1")
        req.setAttribute(QNetworkRequest.Attribute.CookieLoadControlAttribute,
                         QNetworkRequest.LoadControl.Manual)
        req.setAttribute(QNetworkRequest.Attribute.CookieSaveControlAttribute,
                         QNetworkRequest.LoadControl.Manual)
        req.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,
                         QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy)
        req.setTransferTimeout(12000)
        reply = app.network.get(req)

        def done():
            ok, text = False, ""
            ctype = str(reply.header(QNetworkRequest.KnownHeaders.ContentTypeHeader) or "").lower()
            if reply.error() == QNetworkReply.NetworkError.NoError and "css" in ctype:
                data = bytes(reply.readAll())
                if len(data) <= 3 * 1024 * 1024:
                    ok, text = True, data.decode("utf-8", "replace")
            reply.deleteLater()
            try:
                self.cssFetched.emit(ident, ok, text)
            except RuntimeError:
                pass                      # the page is gone
        reply.finished.connect(done)

    @pyqtSlot(float, float)
    def adClick(self, x, y):
        """Video-ad fallback for a top-level YouTube page."""
        try:
            self.page.trusted_click(x, y)
        except Exception:
            pass

    @pyqtSlot(float, float)
    def adClickEmbedded(self, x, y):
        """Validated relay request from a cross-origin YouTube iframe."""
        try:
            self.page.trusted_click(x, y, allow_embedded=True)
        except Exception:
            pass


class PasswordManager(QObject):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.vault = Vault()
        self.available = crypto_available()
        self._last = None
        self._script = None

    # --- page integration --------------------------------------------
    def script_source(self):
        if self._script is None:
            f = QFile(":/qtwebchannel/qwebchannel.js")
            lib = ""
            if f.open(QIODevice.OpenModeFlag.ReadOnly):
                lib = bytes(f.readAll()).decode("utf-8")
                f.close()
            self._script = lib + "\n" + (RES_DIR / "passwords.js").read_text("utf-8") if lib else ""
        return self._script

    def attach(self, page):
        from PyQt6.QtWebChannel import QWebChannel
        channel = QWebChannel(page)
        bridge = PageBridge(self, page)
        channel.registerObject("ike", bridge)
        page.setWebChannel(channel, WORLD)
        page._ike_bridge = bridge

    def _origin(self, page):
        return origin_of(page.url().toString())

    def logins_json(self, page):
        if not self.vault.unlocked:
            return "[]"
        return json.dumps([{"u": e["username"], "p": e["password"]}
                           for e in self.vault.find(self._origin(page))])

    def captured(self, page, username, password):
        if not self.available:
            return
        cfg = self.app.config
        win = getattr(page, "window_ref", None)
        origin = self._origin(page)
        if (not password or not origin or not cfg["passwords_offer_save"]
                or (win is not None and win.private)
                or origin in cfg.get("passwords_never", [])):
            return
        key = (origin, username, password)
        if key == self._last:
            return
        self._last = key
        if self.vault.unlocked and any(e["username"] == username and e["password"] == password
                                       for e in self.vault.find(origin)):
            return
        QTimer.singleShot(400, lambda: self._offer(win, origin, username, password))

    def _offer(self, win, origin, username, password):
        box = QMessageBox(win)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle(T("Save password"))
        box.setText(T("Save the password for %s on %s?") % (username or T("(no user name)"), origin))
        save = box.addButton(T("Save"), QMessageBox.ButtonRole.AcceptRole)
        never = box.addButton(T("Never for this site"), QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(T("Not now"), QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is never:
            self.app.config.data.setdefault("passwords_never", []).append(origin)
            self.app.config.save()
        elif box.clickedButton() is save and self.ensure_unlocked(win):
            self.vault.put(origin, username, password)

    def fill(self, view, interactive=False):
        page = view.page()
        bridge = getattr(page, "_ike_bridge", None)
        if bridge is None:
            return False
        if not self.vault.unlocked and not (interactive and self.ensure_unlocked(view.window())):
            return False
        found = self.vault.find(self._origin(page))
        if not found:
            if interactive:
                self.app._notify(T("No saved login for this site."))
            return False
        entry = found[0]
        if len(found) > 1 and interactive:
            names = [e["username"] or T("(no user name)") for e in found]
            name, ok = QInputDialog.getItem(view.window(), T("Fill login"), T("Account:"),
                                            names, 0, False)
            if not ok:
                return False
            entry = found[names.index(name)]
        bridge.fillRequested.emit(json.dumps({"u": entry["username"], "p": entry["password"]}))
        return True

    # --- unlocking ---------------------------------------------------
    def ensure_unlocked(self, parent=None):
        if not self.available:
            QMessageBox.warning(parent, "I.K.E.", T(
                "The password vault needs the python-cryptography package."))
            return False
        if self.vault.unlocked:
            return True
        if not self.vault.exists():
            pw, ok = QInputDialog.getText(parent, T("Create password vault"), T(
                "Choose a master password. It encrypts all saved passwords and cannot be "
                "recovered if you forget it."), QLineEdit.EchoMode.Password)
            if not ok or len(pw) < 8:
                if ok:
                    QMessageBox.warning(parent, "I.K.E.", T(
                        "The master password must have at least 8 characters."))
                return False
            pw2, ok = QInputDialog.getText(parent, T("Create password vault"),
                                           T("Repeat the master password:"),
                                           QLineEdit.EchoMode.Password)
            if not ok or pw2 != pw:
                if ok:
                    QMessageBox.warning(parent, "I.K.E.", T("The passwords do not match."))
                return False
            self.vault.create(pw)
            return True
        for _ in range(3):
            pw, ok = QInputDialog.getText(parent, T("Unlock passwords"), T("Master password:"),
                                          QLineEdit.EchoMode.Password)
            if not ok:
                return False
            if self.vault.unlock(pw):
                return True
            QMessageBox.warning(parent, "I.K.E.", T("Wrong master password."))
        return False


class GeneratorDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(T("Password generator"))
        lay = QVBoxLayout(self)
        self.out = QLineEdit()
        self.out.setReadOnly(True)
        f = self.out.font()
        f.setFamily("monospace")
        self.out.setFont(f)
        self.out.setMinimumWidth(360)
        lay.addWidget(self.out)
        form = QFormLayout()
        self.length = QSpinBox()
        self.length.setRange(8, 64)
        self.length.setValue(20)
        self.upper = QCheckBox(T("Capital letters"))
        self.digits = QCheckBox(T("Digits"))
        self.symbols = QCheckBox(T("Symbols"))
        for c in (self.upper, self.digits, self.symbols):
            c.setChecked(True)
            c.toggled.connect(self.regen)
        self.length.valueChanged.connect(self.regen)
        form.addRow(T("Length"), self.length)
        for c in (self.upper, self.digits, self.symbols):
            form.addRow("", c)
        lay.addLayout(form)
        row = QHBoxLayout()
        again = QPushButton(T("Generate another"))
        copy = QPushButton(T("Copy"))
        again.clicked.connect(self.regen)
        copy.clicked.connect(lambda: copy_secret(self.out.text()))
        row.addWidget(again)
        row.addWidget(copy)
        lay.addLayout(row)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(self.reject)
        bb.accepted.connect(self.accept)
        lay.addWidget(bb)
        self.regen()

    def regen(self, *_):
        self.out.setText(generate_password(self.length.value(), self.upper.isChecked(),
                                           self.digits.isChecked(), self.symbols.isChecked()))


class PasswordsDialog(QDialog):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self.vault = app.passwords.vault
        self.shown = False
        self.setWindowTitle(T("Passwords") + " — I.K.E.")
        self.resize(760, 480)
        lay = QVBoxLayout(self)
        self.search = QLineEdit()
        self.search.setPlaceholderText(T("Search"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.fill)
        lay.addWidget(self.search)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([T("Site"), T("User name"), T("Password")])
        self.tree.setRootIsDecorated(False)
        self.tree.setColumnWidth(0, 300)
        self.tree.setColumnWidth(1, 220)
        lay.addWidget(self.tree, 1)
        row = QHBoxLayout()
        for label, slot in ((T("Add…"), self._add), (T("Edit…"), self._edit),
                            (T("Remove selected"), self._remove),
                            (T("Copy password"), self._copy),
                            (T("Show / hide"), self._toggle),
                            (T("Generator…"), lambda: GeneratorDialog(self).exec())):
            b = QPushButton(label)
            b.clicked.connect(slot)
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        row2 = QHBoxLayout()
        for label, slot in ((T("Import CSV…"), self._import), (T("Export CSV…"), self._export),
                            (T("Change master password…"), self._change),
                            (T("Lock"), self._lock)):
            b = QPushButton(label)
            b.clicked.connect(slot)
            row2.addWidget(b)
        row2.addStretch(1)
        lay.addLayout(row2)
        self.offer = QCheckBox(T("Offer to save passwords when I sign in"))
        self.offer.setChecked(bool(app.config["passwords_offer_save"]))
        self.offer.toggled.connect(self._offer_changed)
        lay.addWidget(self.offer)
        lay.addWidget(QLabel(T("The vault is encrypted with AES-256; the key comes from your "
                               "master password (scrypt). Without it the data cannot be read.")))
        self.fill()

    def _offer_changed(self, on):
        self.app.config["passwords_offer_save"] = on
        self.app.config.save()

    def _entries(self):
        q = self.search.text().lower()
        return [e for e in (self.vault.entries or [])
                if q in e["origin"].lower() or q in e["username"].lower()]

    def fill(self, *_):
        self.tree.clear()
        for e in self._entries():
            it = QTreeWidgetItem(self.tree, [e["origin"], e["username"],
                                             e["password"] if self.shown else "••••••••"])
            it.setData(0, Qt.ItemDataRole.UserRole, id(e))

    def _current(self):
        it = self.tree.currentItem()
        if not it:
            return None
        for e in self.vault.entries:
            if id(e) == it.data(0, Qt.ItemDataRole.UserRole):
                return e
        return None

    def _ask(self, entry=None):
        d = QDialog(self)
        d.setWindowTitle(T("Login"))
        f = QFormLayout(d)
        site = QLineEdit(entry["origin"] if entry else "https://")
        user = QLineEdit(entry["username"] if entry else "")
        pw = QLineEdit(entry["password"] if entry else generate_password())
        f.addRow(T("Site"), site)
        f.addRow(T("User name"), user)
        f.addRow(T("Password"), pw)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                              | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        f.addRow(bb)
        if d.exec() and origin_of(site.text().strip()) and pw.text():
            return origin_of(site.text().strip()), user.text(), pw.text()
        return None

    def _add(self):
        r = self._ask()
        if r:
            self.vault.put(*r)
            self.fill()

    def _edit(self):
        e = self._current()
        r = self._ask(e) if e else None
        if r:
            e["origin"], e["username"], e["password"] = r
            self.vault.save()
            self.fill()

    def _remove(self):
        e = self._current()
        if e:
            self.vault.remove(e)
            self.fill()

    def _copy(self):
        e = self._current()
        if e:
            copy_secret(e["password"])

    def _toggle(self):
        self.shown = not self.shown
        self.fill()

    def _import(self):
        path, _f = QFileDialog.getOpenFileName(self, T("Import passwords"), "", "CSV (*.csv)")
        if path:
            with open(path, encoding="utf-8-sig", errors="replace") as fh:
                n = self.vault.import_csv(fh.read())
            self.fill()
            QMessageBox.information(self, "I.K.E.", T("%d logins imported.") % n)

    def _export(self):
        if QMessageBox.warning(self, "I.K.E.", T(
                "The exported file is NOT encrypted: anyone who opens it can read your "
                "passwords. Continue?"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) != QMessageBox.StandardButton.Yes:
            return
        path, _f = QFileDialog.getSaveFileName(self, T("Export passwords"), "ike-passwords.csv",
                                               "CSV (*.csv)")
        if path:
            try:
                write_private(path, self.vault.export_csv())
            except OSError as exc:
                QMessageBox.warning(self, "I.K.E.", str(exc))

    def _change(self):
        pw, ok = QInputDialog.getText(self, T("Change master password"), T("New master password:"),
                                      QLineEdit.EchoMode.Password)
        if not ok:
            return
        pw2, ok = QInputDialog.getText(self, T("Change master password"),
                                       T("Repeat the master password:"),
                                       QLineEdit.EchoMode.Password)
        if ok and pw == pw2 and len(pw) >= 8:
            self.vault.change_master(pw)
        elif ok:
            QMessageBox.warning(self, "I.K.E.", T(
                "The master password must have at least 8 characters."))

    def _lock(self):
        self.vault.lock()
        self.close()


def handle_webauthn(page, request):
    """Prompts for security keys / passkeys (FIDO2 over USB or NFC)."""
    from PyQt6.QtWebEngineCore import QWebEngineWebAuthUxRequest as R
    win = getattr(page, "window_ref", None)
    S = R.WebAuthUxState
    state = {"box": None}

    def close_box():
        if state["box"] is not None:
            state["box"].done(0)
            state["box"] = None

    def changed(st):
        close_box()
        if st == S.SelectAccount:
            names = list(request.userNames())
            name, ok = QInputDialog.getItem(win, T("Passkey"), T("Account:"), names, 0, False)
            if ok and name:
                request.setSelectedAccount(name)
            else:
                request.cancel()
        elif st == S.CollectPin:
            pin, ok = QInputDialog.getText(win, T("Passkey"), T("PIN of the security key:"),
                                           QLineEdit.EchoMode.Password)
            if ok and pin:
                request.setPin(pin)
            else:
                request.cancel()
        elif st == S.FinishTokenCollection:
            box = QMessageBox(win)
            box.setWindowTitle(T("Passkey"))
            box.setText(T("Touch your security key to continue (%s).") % request.relyingPartyId())
            box.setStandardButtons(QMessageBox.StandardButton.Cancel)
            box.rejected.connect(request.cancel)
            box.setModal(False)
            box.show()
            state["box"] = box
        elif st == S.RequestFailed:
            QMessageBox.warning(win, T("Passkey"), T("The passkey request failed."))
            request.cancel()

    request.stateChanged.connect(changed)
    changed(request.state())
