"""Program self-update: daily check, signature and hash verification, staged
install in the user's data folder, confirmation of a healthy start.

Nothing under /usr and no system package is touched: the engine (Qt) stays
under the control of the package manager. The bootstrap (ike_boot.py) decides
at start-up which verified copy to run and rolls back a copy that fails.
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

from . import __version__, background
from .config import RES_DIR
from .osinfo import app_dir

UPDATES = app_dir("data") / "updates"
STATE = UPDATES / "state.json"
MAX_PAYLOAD = 20 * 1024 * 1024


def vtuple(v):
    return tuple(int(x) for x in re.findall(r"\d+", v or "0")[:4])


def system_dir():
    return Path(os.environ.get("IKE_SYSTEM_DIR") or Path(__file__).resolve().parent.parent)


def boot_command():
    """Command that starts I.K.E. again (used for self-tests and profiles)."""
    boot = system_dir() / "ike_boot.py"
    if boot.exists():
        return [sys.executable, str(boot)]
    return [sys.executable, "-m", "ike"]


def system_version():
    """Version of the copy installed by the package manager."""
    try:
        text = (system_dir() / "ike" / "__init__.py").read_text("utf-8")
        return re.search(r'__version__\s*=\s*"([^"]+)"', text).group(1)
    except Exception:
        return __version__


def plain_name(name):
    """A file name of the release, never a path or another address."""
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]*", name or "")) and ".." not in name



def source():
    """{'url': ..., 'pubkey': ...} or {} when no update channel is configured."""
    paths = [system_dir() / "update.json", RES_DIR / "update.json"]
    if os.environ.get("IKE_TEST_HOOK") and os.environ.get("IKE_TEST_UPDATE_CONFIG"):
        paths = [Path(os.environ["IKE_TEST_UPDATE_CONFIG"])]      # automatic tests only
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
        state = json.loads(STATE.read_text("utf-8"))
    except Exception:
        return {}
    if not isinstance(state, dict):
        return {}
    if not isinstance(state.get("bad", []), list):
        state["bad"] = []
    return state


def save_state(state):
    UPDATES.mkdir(parents=True, exist_ok=True)
    # its own temporary name: two profiles of I.K.E. may write at the same time (1.1.17)
    tmp = STATE.with_name("state.%d.tmp" % os.getpid())
    tmp.write_text(json.dumps(state), "utf-8")
    tmp.replace(STATE)


def bucket():
    """This installation's fixed place (0-99) in a staged release."""
    state = load_state()
    b = state.get("bucket")
    if not isinstance(b, int) or isinstance(b, bool) or not 0 <= b < 100:
        import secrets
        state["bucket"] = b = secrets.randbelow(100)
        try:
            save_state(state)
        except OSError:
            pass
    return b


def _num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def manifest_stale(manifest, now=None, running=None, seen=None):
    """A verified manifest that must not be trusted at all (checked before
    the version): expired; without an expiry while this copy is 1.1.18 or
    later (only releases before 1.1.18 lacked it: a replayed old manifest
    would keep the user where he is, silently); or issued before one already
    seen (a replay that would undo a "halt"). Adversarial review of 1.1.18."""
    now = time.time() if now is None else now
    exp = manifest.get("expires")
    if exp is None:
        if vtuple(running or __version__) >= (1, 1, 18):
            return "expired"
    elif not _num(exp) or now < exp:
        return "expired"
    issued = manifest.get("issued")
    if _num(seen) and (not _num(issued) or issued < seen):
        return "stale"
    return None


def manifest_problem(manifest, now=None, manual=False, place=None):
    """Why this verified manifest must not be installed now, or None (1.1.18,
    security audit F5): expired (a copy kept back after its time), stopped
    by the owner ("halt"), or this installation's turn in a staged release
    has not come yet (a check asked for by the user does not wait). Manifests
    of earlier releases have none of these fields and are taken as before.
    A wrong clock never blocks for good: a turn that starts in the future by
    more than a day counts as come."""
    now = time.time() if now is None else now
    if manifest.get("halt") is True:
        return "halted"
    exp = manifest.get("expires")
    if exp is not None:
        if not isinstance(exp, (int, float)) or isinstance(exp, bool) or now > exp:
            return "expired"
    if manual:
        return None
    r = manifest.get("rollout")
    if isinstance(r, dict):
        start, hours = r.get("start"), r.get("hours")
        if (isinstance(start, (int, float)) and isinstance(hours, (int, float)) and hours > 0
                and not isinstance(start, bool) and start - 86400 <= now):
            share = (now - start) / (hours * 3600.0) * 100
            if (bucket() if place is None else place) >= share:
                return "waiting"
    return None


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
    """Verify, unpack, self-test and register a downloaded version.

    One installation at a time: two profiles of I.K.E. open together share
    this folder, and one must not remove what the other is unpacking (1.1.17)."""
    import fcntl
    UPDATES.mkdir(parents=True, exist_ok=True)
    with open(UPDATES / ".lock", "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise ValueError("another I.K.E. is installing an update") from None
        return _stage(manifest, payload)


def _stage(manifest, payload):
    version = manifest["version"]
    if not re.fullmatch(r"\d+(\.\d+){1,3}", str(version)):
        raise ValueError("the update manifest names an invalid version")
    if hashlib.sha256(payload).hexdigest() != manifest["sha256"]:
        raise ValueError("hash mismatch")
    versions = UPDATES / "versions"
    staging = versions / (version + ".staging")
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    try:
        safe_extract(payload, staging)
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
        env.pop("IKE_TEST_HOOK", None)
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
    if state.get("status") == "pending" and state.get("current") == __version__:
        state.update({"status": "ok", "attempts": 0})
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

    def __init__(self, src, channel, install, parent=None, manual=False):
        super().__init__(parent)
        self.src, self.channel, self.install, self.manual = src, channel, install, manual

    def run(self):
        try:
            base = self.src["url"].rstrip("/")
            raw = _fetch("%s/%s.json" % (base, self.channel), 256 * 1024)
            sig = _fetch("%s/%s.json.sig" % (base, self.channel), 4096).decode().strip()
            if not verify_signature(self.src["pubkey"], raw, sig):
                raise ValueError("the update manifest has an invalid signature")
            manifest = json.loads(raw.decode("utf-8"))
            state = load_state()
            stale = manifest_stale(manifest, seen=state.get("issued"))
            if stale:
                raise ValueError("the update information is out of date (%s manifest); nothing was "
                                 "installed, the next check tries again" % stale)
            if _num(manifest.get("issued")) and manifest["issued"] > (state.get("issued") or 0):
                state["issued"] = manifest["issued"]
                save_state(state)
            staged = load_state().get("current")
            newest = max(__version__, staged or "0", key=vtuple)
            if (vtuple(manifest["version"]) <= vtuple(newest)
                    or manifest["version"] in load_state().get("bad", [])):
                self.result.emit("current", manifest)
                return
            if not plain_name(manifest.get("payload")):
                raise ValueError("the update manifest names an invalid file")
            problem = manifest_problem(manifest, manual=self.manual)
            if problem in ("halted", "waiting"):
                # stopped by the owner, or not this installation's turn yet
                self.result.emit("current", {"version": newest})
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

    def run(self, install, manual=False):
        src = source()
        if not src or self._worker is not None:
            return False
        channel = self.config["update_channel"]
        if channel not in ("stable", "beta"):     # part of the address: never whatever the settings hold
            channel = "stable"
        self._worker = _Worker(src, channel, install, self, manual=manual)
        self._worker.result.connect(self._done)
        background.start(self._worker)
        return True

    def _done(self, kind, data):
        self._worker = None
        self.config["last_app_check"] = int(time.time())
        self.config.save()
        self.finished.emit(kind, data)
