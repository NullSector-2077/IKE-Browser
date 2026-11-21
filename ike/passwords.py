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

# scrypt for new vaults and for old ones at their next unlock (1.1.17: N was
# 2^15). About a third of a second, once, when the vault is opened; each
# guess of a stolen file costs a thief the same, and 128 MB of memory.
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2 ** 17, 8, 1
LEGACY = (2 ** 15, 8, 1)        # every vault file written from 1.0.0 to 1.1.16 names exactly these
# The only scrypt profiles a vault file may name: the one of today and the
# legacy one (opened, then sealed again with today's). Anything else is
# refused before scrypt runs: scrypt needs about 128 * N * r bytes and p times
# the work, so a doctored file naming, say, N = 2^20, r = 16, p = 4 (2 GiB,
# four rounds) must not even be tried.
PROFILES = frozenset({(SCRYPT_N, SCRYPT_R, SCRYPT_P), LEGACY})


def _params(blob):
    """{"n", "r", "p"} of a vault file, or None unless the file names one of
    PROFILES exactly: whole numbers written as such (no text, no fractions,
    no true/false), all three present."""
    try:
        values = tuple(blob[k] for k in ("n", "r", "p"))
    except (KeyError, TypeError):
        return None
    if not all(type(v) is int for v in values) or values not in PROFILES:
        return None
    return dict(zip(("n", "r", "p"), values))


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
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


CLIPBOARD_SECONDS = 45


def copy_secret(text):
    """Put a password on the clipboard: marked so that the desktop's clipboard
    history (Klipper and others that follow the same hint) does not keep it,
    and taken off again after a while if it is still there."""
    from PyQt6.QtCore import QMimeData
    clipboard = QGuiApplication.clipboard()
    data = QMimeData()
    data.setText(text)
    data.setData("x-kde-passwordManagerHint", b"secret")
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
        self._params = None      # scrypt parameters of self._key

    def exists(self):
        return self.path.exists()

    @property
    def unlocked(self):
        return self.entries is not None

    def _derive(self, master, salt, params=None):
        from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
        k = params or {"n": SCRYPT_N, "r": SCRYPT_R, "p": SCRYPT_P}
        return Scrypt(salt=salt, length=32, n=k["n"], r=k["r"], p=k["p"]).derive(
            master.encode("utf-8"))

    def create(self, master):
        self._salt = os.urandom(16)
        self._key = self._derive(master, self._salt)
        self._params = {"n": SCRYPT_N, "r": SCRYPT_R, "p": SCRYPT_P}
        self.entries = []
        self.save()

    def unlock(self, master):
        from cryptography.exceptions import InvalidTag
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        try:
            blob = json.loads(self.path.read_text("utf-8"))
            params = _params(blob)
            if params is None:
                return False
            salt = base64.b64decode(blob["salt"])
            key = self._derive(master, salt, params)
            nonce, data = base64.b64decode(blob["nonce"]), base64.b64decode(blob["data"])
        except (ValueError, KeyError, OSError, AttributeError):
            return False
        try:
            plain = AESGCM(key).decrypt(nonce, data, _AAD)
        except InvalidTag:
            return False
        self.entries = json.loads(plain.decode("utf-8"))
        self._key, self._salt, self._params = key, salt, params
        if (params["n"], params["r"], params["p"]) != (SCRYPT_N, SCRYPT_R, SCRYPT_P):
            # sealed again with today's parameters; if that cannot be written
            # the file stays exactly as it was and opens as before
            old = (self._key, self._salt, self._params)
            try:
                self._salt = os.urandom(16)
                self._key = self._derive(master, self._salt)
                self._params = {"n": SCRYPT_N, "r": SCRYPT_R, "p": SCRYPT_P}
                self.save()
            except OSError:
                self._key, self._salt, self._params = old
        return True

    def lock(self):
        self.entries = None
        self._key = None

    def verify(self, master):
        """True if `master` is the master password of the open vault (no file
        is read: the key is derived again and compared in constant time)."""
        import hmac
        if self._key is None or self._salt is None:
            return False
        try:
            return hmac.compare_digest(self._derive(master, self._salt, self._params), self._key)
        except (TypeError, ValueError):
            return False

    def change_master(self, master):
        self._salt = os.urandom(16)
        self._key = self._derive(master, self._salt)
        self._params = {"n": SCRYPT_N, "r": SCRYPT_R, "p": SCRYPT_P}
        self.save()

    def save(self):
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        nonce = os.urandom(12)
        data = AESGCM(self._key).encrypt(nonce, json.dumps(self.entries).encode("utf-8"),
                                         _AAD)
        k = self._params or {"n": SCRYPT_N, "r": SCRYPT_R, "p": SCRYPT_P}
        blob = {"v": 1, "kdf": "scrypt", "n": k["n"], "r": k["r"], "p": k["p"],
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


def insecure_page(url):
    """True for a page reached without encryption from another computer
    (plain http, not this computer or the home network)."""
    from .userscripts import is_local_name
    return url.scheme() == "http" and not is_local_name(url.host())


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

    @pyqtSlot(float, float, float, float, str)
    def offerFill(self, x, y, w, h, typed):
        """The user clicked into a login form: I.K.E. offers its saved logins
        in a menu of its own. The page never receives a password it was not
        given by the user's choice."""
        self.manager.offer_fill(self.page, x, y, w, h, typed)

    @pyqtSlot(str, str)
    def captured(self, username, password):
        self.manager.captured(self.page, username, password)

    cssFetched = pyqtSignal(str, bool, str)

    @pyqtSlot(str, str)
    def fetchCss(self, ident, url):
        """Dark mode: fetch a style sheet of another site that the page cannot read.

        Only style sheets, only over http(s), without cookies, at most 3 MB.
        Never from this computer or the home network (a router, a printer, a
        program listening here) unless the page itself comes from there: the
        restyled sheet ends up in the page, which could otherwise read what
        those devices serve. Every redirect is checked the same way, and never
        from https to http.
        """
        from PyQt6.QtCore import QUrl

        from .userscripts import is_local_name, outside_home
        target = QUrl(url)
        if (target.scheme() not in ("http", "https") or not getattr(self.page, "_dark_on", False)
                or not self._css_allowed(target)):
            self.cssFetched.emit(ident, False, "")
            return
        if is_local_name(self.page.url().host()):
            self._get_css(ident, target, check=None)      # a page of the home network itself
            return
        outside_home(target.host(), lambda ok: self._get_css(ident, target, check=outside_home)
                     if ok else self._css_answer(ident, False, ""), "dark mode",
                     self.manager.app.network)

    def _css_allowed(self, target):
        """As the engine would load it for the page (review of 1.1.19, M4):
        never in clear for a page sent encrypted (mixed content), and never
        what the filter lists block for this page."""
        page_url = self.page.url()
        if page_url.scheme() == "https" and target.scheme() != "https":
            return False
        sh = self.manager.app.shields
        cfg = sh.config
        if ((cfg["comp_adblock"] or cfg["comp_consent"])
                and cfg.site_opt(page_url.host().lower(), "ads") is not False):
            action, _ = sh.blocker.request_action(target.toString(), page_url.toString(), "stylesheet")
            if action != "allow":
                return False
        return True

    def _css_answer(self, ident, ok, text):
        try:
            self.cssFetched.emit(ident, ok, text)
        except RuntimeError:
            pass                          # the page is gone

    def _get_css(self, ident, target, check, hops=0):
        from PyQt6.QtNetwork import QNetworkRequest

        from . import doh
        app = self.manager.app
        req = QNetworkRequest(target)
        req.setRawHeader(b"Accept", b"text/css,*/*;q=0.1")
        # the browser's own User-Agent: Qt's default named this fetch as I.K.E.'s
        req.setRawHeader(b"User-Agent", app.shields.user_agent().encode("ascii", "replace"))
        req.setAttribute(QNetworkRequest.Attribute.CookieLoadControlAttribute,
                         QNetworkRequest.LoadControl.Manual)
        req.setAttribute(QNetworkRequest.Attribute.CookieSaveControlAttribute,
                         QNetworkRequest.LoadControl.Manual)
        req.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,
                         QNetworkRequest.RedirectPolicy.UserVerifiedRedirectPolicy)
        req.setTransferTimeout(12000)
        doh.get(app.network, req, lambda reply: self._css_reply(reply, ident, target, check, hops))

    def _css_reply(self, reply, ident, target, check, hops):
        from PyQt6.QtNetwork import QNetworkReply, QNetworkRequest

        from . import doh
        app = self.manager.app
        if reply is None:                         # no address from encrypted DNS
            self._css_answer(ident, False, "")
            return
        refused = []
        address = reply.url().host()        # Qt changes reply.url() to the redirect's
        pinned = address != target.host()

        def redirected(where):
            where = reply.url().resolved(where) if where.isRelative() else where
            if pinned and where.host() == address:
                where = doh.unpin(where, target.host())
            if where.scheme() not in ("http", "https") or (
                    reply.url().scheme() == "https" and where.scheme() != "https") or not self._css_allowed(where):
                refused.append(1)
                reply.abort()
                return
            if pinned:
                # followed as a new request, its name asked of the provider of
                # encrypted DNS (Qt would look it up in clear); marked first:
                # abort() ends the reply at once, and its end must not answer
                follow.append(1)
                refused.append(1)
                reply.abort()
                if hops >= 10:
                    return

                def again(ok):
                    if ok:
                        self._get_css(ident, where, check, hops + 1)
                    else:
                        self._css_answer(ident, False, "")
                if check is None:
                    again(True)
                else:
                    check(where.host(), again, "dark mode", app.network)
                return
            if check is None:
                reply.redirectAllowed.emit()
                return

            def checked(ok):
                if refused or not reply.isRunning():
                    return
                if ok:
                    reply.redirectAllowed.emit()
                else:
                    refused.append(1)
                    reply.abort()
            check(where.host(), checked, "dark mode", app.network)
        follow = []
        reply.redirected.connect(redirected)

        def done():
            if follow:
                reply.deleteLater()
                return
            ok, text = False, ""
            ctype = str(reply.header(QNetworkRequest.KnownHeaders.ContentTypeHeader) or "").lower()
            if (not refused and reply.error() == QNetworkReply.NetworkError.NoError
                    and "css" in ctype):
                data = bytes(reply.read(3 * 1024 * 1024 + 1))
                if len(data) <= 3 * 1024 * 1024:
                    ok, text = True, data.decode("utf-8", "replace")
            reply.deleteLater()
            self._css_answer(ident, ok, text)
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
        self._confirmed = -1e9           # when the master password was last typed (time.monotonic)
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

    def offer_fill(self, page, x, y, w, h, typed=""):
        """A small menu under the field: "Fill in: <user>" for each saved login
        of the page's origin (a user name already typed narrows it), and "Not
        now", after which the page is not asked about again until it changes.
        Nothing when the vault is locked or has no login for the site."""
        from PyQt6.QtCore import QPoint
        from PyQt6.QtWidgets import QMenu
        win = getattr(page, "window_ref", None)
        if (insecure_page(page.url()) and win is not None
                and getattr(page, "_ike_warned", None) != page.url().toString()):
            # once per page, saved login or not: typing a password here is risky
            page._ike_warned = page.url().toString()
            win.toast(T("This page is not secure: others on the network can read "
                        "what you type here."), 7000)
        if not self.vault.unlocked or getattr(page, "_ike_fill_menu", None) is not None:
            return
        origin = self._origin(page)
        if not origin or getattr(page, "_ike_fill_declined", None) == page.url().toString():
            return
        found = self.vault.find(origin)
        if typed:
            found = [e for e in found if e["username"] == typed]
        view = win.view_of(page) if win is not None else None
        if not found or view is None:
            return
        menu = QMenu(view)
        if insecure_page(page.url()):
            warn = menu.addAction(T("This page is not secure: others on the network can read "
                                    "what you type here."))
            warn.setEnabled(False)
            menu.addSeparator()
        for e in found[:12]:
            a = menu.addAction(T("Fill in: %s") % (e["username"] or T("(no user name)")))
            a.triggered.connect(lambda _c=False, e=e: self._chosen(page, origin, e))
        menu.addSeparator()
        menu.addAction(T("Not now")).triggered.connect(
            lambda: setattr(page, "_ike_fill_declined", page.url().toString()))
        page._ike_fill_menu = menu
        menu.aboutToHide.connect(lambda: setattr(page, "_ike_fill_menu", None))
        menu.aboutToHide.connect(menu.deleteLater)
        zoom = page.zoomFactor() or 1.0
        menu.popup(view.mapToGlobal(QPoint(int(x * zoom), int((y + h) * zoom) + 2)))

    def _chosen(self, page, origin, entry):
        bridge = getattr(page, "_ike_bridge", None)
        if bridge is None or self._origin(page) != origin or not self.vault.unlocked:
            return                        # the page went elsewhere meanwhile
        bridge.fillRequested.emit(json.dumps({"u": entry["username"], "p": entry["password"]}))

    def captured(self, page, username, password):
        if not self.available:
            return
        cfg = self.app.config
        win = getattr(page, "window_ref", None)
        origin = self._origin(page)
        if (not password or not origin or not cfg["passwords_offer_save"]
                or not cfg.get("ext_passwords", True)
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
            self._confirmed = time.monotonic()
            return True
        for _ in range(3):
            pw, ok = QInputDialog.getText(parent, T("Unlock passwords"), T("Master password:"),
                                          QLineEdit.EchoMode.Password)
            if not ok:
                return False
            if self.vault.unlock(pw):
                self._confirmed = time.monotonic()
                return True
            QMessageBox.warning(parent, "I.K.E.", T("Wrong master password."))
        return False

    # showing, copying or exporting saved passwords in the Passwords window
    # asks for the master password again, unless it was typed in the last few
    # minutes: whoever sits at an unattended computer with the vault open
    # cannot read them all (1.1.17). Filling a login into a site is unchanged.
    CONFIRM_SECONDS = 300

    def confirm_owner(self, parent=None):
        if not self.vault.unlocked:
            return self.ensure_unlocked(parent)
        if time.monotonic() - self._confirmed < self.CONFIRM_SECONDS:
            return True
        pw, ok = QInputDialog.getText(parent, T("Show passwords"), T(
            "Type the master password to see, copy or export saved passwords:"),
            QLineEdit.EchoMode.Password)
        if not ok:
            return False
        if self.vault.verify(pw):
            self._confirmed = time.monotonic()
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
        self.manager = app.passwords
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
        if e is None or not self.manager.confirm_owner(self):
            return                           # the edit window shows the password
        r = self._ask(e)
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
        if e and self.manager.confirm_owner(self):
            copy_secret(e["password"])

    def _toggle(self):
        if not self.shown and not self.manager.confirm_owner(self):
            return
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
        if not self.manager.confirm_owner(self):
            return
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
        self.manager._confirmed = -1e9
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
