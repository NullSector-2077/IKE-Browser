"""Program self-update: daily check, signature and hash verification, staged
install in the user's data folder, confirmation of a healthy start.

Nothing under /usr and no system package is touched: the engine (Qt) stays
under the control of the package manager. The bootstrap (ike_boot.py) decides
at start-up which verified copy to run and rolls back a copy that fails.
The AppImage and the Windows installation replace the whole program instead
(web engine included): the AppImage file, or a new app/<version> folder next
to the one in use on Windows.
"""

import base64
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request
from pathlib import Path

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from . import __version__
from .config import RES_DIR
from .osinfo import app_dir

UPDATES = app_dir("data") / "updates"
STATE = UPDATES / "state.json"
MAX_PAYLOAD = 20 * 1024 * 1024
MAX_APPIMAGE = 800 * 1024 * 1024
MAX_WINDOWS = 800 * 1024 * 1024            # the update archive (about 170 MB)
MAX_WINDOWS_UNPACKED = 2 * 1024 * 1024 * 1024
MAX_WINDOWS_FILES = 40000
# names Windows gives a special meaning, whatever the extension
_RESERVED = {"CON", "PRN", "AUX", "NUL", *("COM%d" % i for i in range(10)), *("LPT%d" % i for i in range(10))}


def vtuple(v):
    return tuple(int(x) for x in re.findall(r"\d+", v or "0")[:4])


def system_dir():
    return Path(os.environ.get("IKE_SYSTEM_DIR") or Path(__file__).resolve().parent.parent)


def boot_command():
    """Command that starts I.K.E. again (used for self-tests and profiles)."""
    if os.environ.get("APPIMAGE") and os.path.exists(os.environ["APPIMAGE"]):
        return [os.environ["APPIMAGE"]]
    if os.environ.get("ICE_LAUNCHER") and os.path.isfile(os.environ["ICE_LAUNCHER"]):
        return [os.environ["ICE_LAUNCHER"]]           # Windows: ike-browser.exe
    if getattr(sys, "frozen", False):
        return [sys.executable]
    boot = system_dir() / "ike_boot.py"
    if boot.exists():
        return [sys.executable, str(boot)]
    return [sys.executable, "-m", "ike"]


def system_version():
    """Version of the copy installed by the package manager (or the AppImage)."""
    try:
        text = (system_dir() / "ike" / "__init__.py").read_text("utf-8")
        return re.search(r'__version__\s*=\s*"([^"]+)"', text).group(1)
    except Exception:
        return __version__


def plain_name(name):
    """A file name of the release, never a path or another address."""
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]*", name or "")) and ".." not in name


def appimage_path():
    """The AppImage file this copy runs from, or None."""
    p = os.environ.get("APPIMAGE")
    if os.environ.get("ICE_PACKAGE") == "appimage" and p and os.path.isfile(p):
        return Path(p)
    return None


def replace_appimage(current, url, info, version):
    """Download a new AppImage next to the running one, check it, swap them.

    The new file must match the size and SHA-256 of the signed manifest and
    pass its own self-test; the old file is kept as <name>.previous. The
    running copy keeps working until it is closed.
    """
    folder = current.parent
    if not (os.access(folder, os.W_OK) and os.access(current, os.W_OK)):
        raise ValueError("no permission to replace %s" % current)
    new = folder / ("." + current.name + ".new")
    h, size = hashlib.sha256(), 0
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "IKE-Browser-Updater"})
        with urllib.request.urlopen(req, timeout=60) as r, open(new, "wb") as f:
            while True:
                block = r.read(1 << 20)
                if not block:
                    break
                size += len(block)
                if size > MAX_APPIMAGE:
                    raise ValueError("download too large")
                h.update(block)
                f.write(block)
        if h.hexdigest() != info["sha256"] or (info.get("size") and size != info["size"]):
            raise ValueError("hash mismatch")
        os.chmod(new, 0o755)
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
        for k in ("ICE_TEST_HOOK", "APPIMAGE", "APPDIR", "ARGV0", "OWD"):
            env.pop(k, None)
        res = subprocess.run([str(new), "--selftest"], capture_output=True, text=True,
                             timeout=180, env=env)
        if "IKE-SELFTEST-OK %s" % version not in res.stdout:
            raise ValueError("self-test failed: %s" % (res.stderr.strip()[-300:] or res.stdout[-200:]))
        backup = folder / (current.name + ".previous")
        os.replace(current, backup)
        try:
            os.replace(new, current)
        except OSError:
            os.replace(backup, current)
            raise
    finally:
        if new.exists():
            new.unlink()
    state = load_state()
    state["appimage"] = {"version": version, "file": str(current), "previous": str(backup),
                         "installed": int(time.time())}
    save_state(state)


def windows_install():
    """The per-user Windows installation this copy runs from, or None.

    Its folder holds the launcher, the file "current" (the version folder in
    use) and app/<version>/ folders (docs/UPDATES.md)."""
    d = os.environ.get("ICE_INSTALL_DIR")
    if os.environ.get("ICE_PACKAGE") == "windows" and d and os.path.isfile(os.path.join(d, "current")) \
            and os.path.isdir(os.path.join(d, "app")):
        return Path(d)
    return None


def safe_zip_name(name):
    """A file of the update archive: a relative path inside its folder, with
    no way out of it and nothing Windows would read differently."""
    name = name[:-1] if name.endswith("/") else name
    if not name or "\\" in name or ":" in name or name.startswith("/") or "\0" in name:
        return False
    for part in name.split("/"):
        if part in ("", ".", "..") or part != part.rstrip(". ") or any(ord(c) < 32 for c in part):
            return False
        if part.split(".")[0].upper() in _RESERVED:
            return False
    return True


def _write_text(path, text):
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, "utf-8")
    os.replace(tmp, path)


def _hidden_run(cmd, **kw):
    if sys.platform == "win32":
        kw["creationflags"] = 0x08000000           # CREATE_NO_WINDOW
    return subprocess.run(cmd, **kw)


def unpack_windows(archive, target, version):
    """Check and unpack an update archive into target (which must not exist)."""
    import stat
    import zipfile
    try:
        z = zipfile.ZipFile(archive)
    except zipfile.BadZipFile:
        raise ValueError("the update is not a valid archive")
    with z:
        infos = z.infolist()
        if len(infos) > MAX_WINDOWS_FILES:
            raise ValueError("unexpected update archive: too many files")
        if sum(i.file_size for i in infos) > MAX_WINDOWS_UNPACKED:
            raise ValueError("unexpected update archive: too large once unpacked")
        seen = set()
        for i in infos:
            kind = stat.S_IFMT(i.external_attr >> 16)
            if not safe_zip_name(i.filename) or kind not in (0, stat.S_IFREG, stat.S_IFDIR):
                raise ValueError("unexpected entry in update: %s" % i.filename[:120])
            key = i.filename.rstrip("/").lower()         # Windows names ignore case
            if key in seen:
                raise ValueError("unexpected entry in update: %s" % i.filename[:120])
            seen.add(key)
        target.mkdir(parents=True)
        root = target.resolve()
        total = 0
        for i in infos:
            dest = (target / i.filename).resolve()
            if dest != root and root not in dest.parents:
                raise ValueError("unexpected entry in update: %s" % i.filename[:120])
            if i.is_dir():
                dest.mkdir(parents=True, exist_ok=True)
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            with z.open(i) as src, open(dest, "wb") as out:
                while True:
                    block = src.read(1 << 20)
                    if not block:
                        break
                    total += len(block)
                    if total > MAX_WINDOWS_UNPACKED:      # sizes in the archive can lie
                        raise ValueError("unexpected update archive: too large once unpacked")
                    out.write(block)
    for need in ("python/python3.dll", "python/python.exe", "ike_boot.py", "ike/__init__.py"):
        if not (target / need).is_file():
            raise ValueError("the update is incomplete: %s is missing" % need)
    text = (target / "ike" / "__init__.py").read_text("utf-8", "replace")
    found = re.search(r'__version__\s*=\s*"([^"]+)"', text)
    if not found or found.group(1) != version:
        raise ValueError("the update holds another version")


def replace_windows(root, url, info, version):
    """Download the new version's folder, check it, start it once, and make
    the launcher use it from the next start. Nothing in use is touched: the new
    version goes into its own folder, the current one stays as "previous"."""
    if not plain_name(version):
        raise ValueError("invalid version")
    apps = root / "app"
    if not os.access(apps, os.W_OK):
        raise ValueError("no permission to write to %s" % apps)
    download = apps / (".%s.download" % version)
    staging = apps / (".%s.staging" % version)
    h, size = hashlib.sha256(), 0
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "IKE-Browser-Updater"})
        with urllib.request.urlopen(req, timeout=60) as r, open(download, "wb") as f:
            while True:
                block = r.read(1 << 20)
                if not block:
                    break
                size += len(block)
                if size > MAX_WINDOWS:
                    raise ValueError("download too large")
                h.update(block)
                f.write(block)
        if h.hexdigest() != info["sha256"] or (info.get("size") and size != info["size"]):
            raise ValueError("hash mismatch")
        shutil.rmtree(staging, ignore_errors=True)
        unpack_windows(download, staging, version)
        download.unlink()
        env = {k: v for k, v in os.environ.items() if not k.startswith(("PYTHON", "ICE_TEST_HOOK"))}
        env.update(QT_QPA_PLATFORM="offscreen", PYTHONNOUSERSITE="1")
        python = str(staging / "python" / "python.exe")
        if os.environ.get("ICE_TEST_HOOK") and os.environ.get("ICE_TEST_WIN_PYTHON"):
            python = os.environ["ICE_TEST_WIN_PYTHON"]          # automatic tests only
        res = _hidden_run([python, "-s", str(staging / "ike_boot.py"), "--selftest"],
                          capture_output=True, text=True, timeout=180, env=env, cwd=str(staging))
        if "IKE-SELFTEST-OK %s" % version not in res.stdout:
            raise ValueError("self-test failed: %s" % (res.stderr.strip()[-300:] or res.stdout[-200:]))
        final = apps / version
        shutil.rmtree(final, ignore_errors=True)
        staging.replace(final)
    finally:
        for p in (download, staging):
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            elif p.exists():
                p.unlink()
    current = root / "current"
    old = current.read_text("utf-8").strip()
    if old and old != version and plain_name(old) and (apps / old).is_dir():
        _write_text(root / "previous", old)
    else:
        old = ""
    _write_text(current, version)
    running = Path(os.environ.get("IKE_SYSTEM_DIR") or system_dir()).resolve()
    for d in apps.iterdir():                 # keep the new one, the previous one and the one running
        if d.is_dir() and d.name not in (version, old) and d.resolve() != running:
            shutil.rmtree(d, ignore_errors=True)
    _set_installed_version(version)
    state = load_state()
    state["windows"] = {"version": version, "previous": old, "status": "pending", "attempts": 0,
                        "installed": int(time.time())}
    save_state(state)


def _set_installed_version(version):
    """The version shown in Windows' list of installed apps."""
    try:
        import winreg
        key = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\{5E0C1F7A-8C2B-4D7E-9B61-2A9F4C3D1E07}_is1"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, "DisplayVersion", 0, winreg.REG_SZ, version)
            winreg.SetValueEx(k, "DisplayName", 0, winreg.REG_SZ, "I.K.E.")
    except (ImportError, OSError):
        pass


def source():
    """{'url': ..., 'pubkey': ...} or {} when no update channel is configured."""
    paths = [system_dir() / "update.json", RES_DIR / "update.json"]
    if os.environ.get("ICE_TEST_HOOK") and os.environ.get("ICE_TEST_UPDATE_CONFIG"):
        paths = [Path(os.environ["ICE_TEST_UPDATE_CONFIG"])]      # automatic tests only
    for p in paths:
        try:
            d = json.loads(p.read_text("utf-8"))
            if d.get("url") and d.get("pubkey"):
                return d
        except Exception:
            continue
    return {}


def load_state():
    try:
        return json.loads(STATE.read_text("utf-8"))
    except Exception:
        return {}


def save_state(state):
    UPDATES.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state), "utf-8")
    tmp.replace(STATE)


def verify_signature(pubkey_b64, data, sig_b64):
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    try:
        key = Ed25519PublicKey.from_public_bytes(base64.b64decode(pubkey_b64))
        key.verify(base64.b64decode(sig_b64), data)
        return True
    except (InvalidSignature, ValueError):
        return False


def _fetch(url, limit):
    req = urllib.request.Request(url, headers={"User-Agent": "IKE-Browser-Updater"})
    with urllib.request.urlopen(req, timeout=40) as r:
        data = r.read(limit + 1)
    if len(data) > limit:
        raise ValueError("download too large")
    return data


def safe_extract(payload, target):
    """Extract a .tar.gz that may only contain regular files under ike/."""
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as tar:
        for m in tar.getmembers():
            parts = Path(m.name).parts
            if (not parts or parts[0] != "ike" or ".." in parts or m.name.startswith("/")
                    or not (m.isfile() or m.isdir())):
                raise ValueError("unexpected entry in update: %s" % m.name)
        for m in tar.getmembers():
            dest = target / m.name
            if m.isdir():
                dest.mkdir(parents=True, exist_ok=True)
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                with tar.extractfile(m) as src, open(dest, "wb") as out:
                    shutil.copyfileobj(src, out)


def stage(manifest, payload):
    """Verify, unpack, self-test and register a downloaded version."""
    version = manifest["version"]
    if hashlib.sha256(payload).hexdigest() != manifest["sha256"]:
        raise ValueError("hash mismatch")
    versions = UPDATES / "versions"
    staging = versions / (version + ".staging")
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    try:
        safe_extract(payload, staging)
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
        env.pop("ICE_TEST_HOOK", None)
        res = subprocess.run(boot_command() + ["--selftest-import", str(staging)],
                             capture_output=True, text=True, timeout=120, env=env)
        if "IKE-SELFTEST-OK %s" % version not in res.stdout:
            raise ValueError("self-test failed: %s" % (res.stderr.strip()[-300:] or res.stdout[-200:]))
        final = versions / version
        shutil.rmtree(final, ignore_errors=True)
        staging.replace(final)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    state = load_state()
    previous = state.get("current") if state.get("status") == "ok" else state.get("previous")
    state.update({"current": version, "previous": previous, "status": "pending",
                  "attempts": 0, "installed": int(time.time())})
    state.pop("rolled_back", None)
    save_state(state)
    keep = {version, previous}
    for d in versions.iterdir():           # keep one backup, drop older copies
        if d.is_dir() and d.name not in keep:
            shutil.rmtree(d, ignore_errors=True)
    return version


def confirm_healthy():
    """Called after the program has been running fine for a while."""
    state = load_state()
    changed = False
    if state.get("status") == "pending" and state.get("current") == __version__:
        state.update({"status": "ok", "attempts": 0})
        changed = True
    win = state.get("windows") or {}
    if win.get("status") == "pending" and win.get("version") == __version__:
        win.update({"status": "ok", "attempts": 0})
        changed = True
    if changed:
        save_state(state)


def take_rollback_notice():
    state = load_state()
    bad = state.pop("rolled_back", None)
    if bad:
        reason = state.pop("rollback_reason", "")
        save_state(state)
        return bad, reason
    return None


class _Worker(QThread):
    result = pyqtSignal(str, object)     # kind, data

    def __init__(self, src, channel, install, parent=None):
        super().__init__(parent)
        self.src, self.channel, self.install = src, channel, install

    def run(self):
        try:
            base = self.src["url"].rstrip("/")
            raw = _fetch("%s/%s.json" % (base, self.channel), 256 * 1024)
            sig = _fetch("%s/%s.json.sig" % (base, self.channel), 4096).decode().strip()
            if not verify_signature(self.src["pubkey"], raw, sig):
                raise ValueError("the update manifest has an invalid signature")
            manifest = json.loads(raw.decode("utf-8"))
            staged = load_state().get("current")
            newest = max(__version__, staged or "0", key=vtuple)
            if (vtuple(manifest["version"]) <= vtuple(newest)
                    or manifest["version"] in load_state().get("bad", [])):
                self.result.emit("current", manifest)
                return
            if not plain_name(manifest.get("payload")):
                raise ValueError("the update manifest names an invalid file")
            win = windows_install()
            if win:
                # the whole program folder is replaced, so the web engine is updated too
                info = manifest.get("windows") or {}
                if not (plain_name(info.get("file")) and re.fullmatch(r"[0-9a-f]{64}", info.get("sha256", ""))):
                    self.result.emit("system", manifest)
                elif not self.install:
                    self.result.emit("available", manifest)
                else:
                    replace_windows(win, "%s/%s" % (base, info["file"]), info, manifest["version"])
                    self.result.emit("installed", manifest)
                return
            app = appimage_path()
            if app:
                # the whole AppImage is replaced, so the web engine is updated too
                info = manifest.get("appimage") or {}
                if not (plain_name(info.get("file")) and re.fullmatch(r"[0-9a-f]{64}", info.get("sha256", ""))):
                    self.result.emit("system", manifest)
                elif not self.install:
                    self.result.emit("available", manifest)
                else:
                    replace_appimage(app, "%s/%s" % (base, info["file"]), info, manifest["version"])
                    self.result.emit("installed", manifest)
                return
            need = manifest.get("min_system")
            if need and vtuple(need) > vtuple(system_version()):
                # needs a newer system part: only a new package can provide it
                self.result.emit("system", manifest)
                return
            if not self.install:
                self.result.emit("available", manifest)
                return
            payload = _fetch("%s/%s" % (base, manifest["payload"]), MAX_PAYLOAD)
            stage(manifest, payload)
            self.result.emit("installed", manifest)
        except Exception as exc:
            self.result.emit("error", str(exc))


class Updater(QObject):
    finished = pyqtSignal(str, object)

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self._worker = None

    def configured(self):
        return bool(source())

    def busy(self):
        return self._worker is not None

    def run(self, install):
        src = source()
        if not src or self._worker is not None:
            return False
        self._worker = _Worker(src, self.config["update_channel"], install, self)
        self._worker.result.connect(self._done)
        self._worker.start()
        return True

    def _done(self, kind, data):
        self._worker = None
        self.config["last_app_check"] = int(time.time())
        self.config.save()
        self.finished.emit(kind, data)
