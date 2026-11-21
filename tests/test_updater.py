"""Self-update: signatures, release files, and a full update through a local
server that answers like GitHub Releases (redirects included)."""

import base64
import hashlib
import importlib.util
import io
import json
import re
import shutil
import subprocess
import sys
import tarfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from conftest import ROOT

sys.path.insert(0, str(ROOT))

cryptography = pytest.importorskip("cryptography")
from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402

PASS = "test passphrase"


def load_tool():
    spec = importlib.util.spec_from_file_location("make_release", ROOT / "tools" / "make-release.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def updater(tmp_path, monkeypatch):
    from ike import updater as u
    monkeypatch.setattr(u, "UPDATES", tmp_path / "updates")
    monkeypatch.setattr(u, "STATE", tmp_path / "updates" / "state.json")
    return u


@pytest.fixture
def keypair(tmp_path):
    """An encrypted PEM key outside the repository and its base64 public key."""
    key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.BestAvailableEncryption(PASS.encode()))
    path = tmp_path / "keys" / "ike-update.key"
    path.parent.mkdir()
    path.write_bytes(pem)
    pub = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return key, path, base64.b64encode(pub).decode()


def tar_gz(files):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            if data is None:                   # a symbolic link
                info.type = tarfile.SYMTYPE
                info.linkname = "/etc/passwd"
                tar.addfile(info)
            else:
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


# --- pieces ---------------------------------------------------------------

def test_signature(updater, keypair):
    key, _, pub = keypair
    data = b'{"version": "9.9.9"}'
    sig = base64.b64encode(key.sign(data)).decode()
    assert updater.verify_signature(pub, data, sig)
    assert not updater.verify_signature(pub, data + b" ", sig)
    other = base64.b64encode(Ed25519PrivateKey.generate().public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode()
    assert not updater.verify_signature(other, data, sig)
    assert not updater.verify_signature(pub, data, "not base64!")


def test_release_file_names(updater):
    assert updater.plain_name("ike-1.0.1.tar.gz")
    assert updater.plain_name("ike-browser-1.0.1-1-x86_64.pkg.tar.zst")
    for bad in ("", None, "../ike.tar.gz", "/etc/passwd", "a/b.tar.gz",
                "https://evil.example/x.tar.gz", "..", ".hidden"):
        assert not updater.plain_name(bad), bad


@pytest.mark.parametrize("files", [
    {"ike/../../evil.py": b"x"},
    {"/tmp/evil.py": b"x"},
    {"other/evil.py": b"x"},
    {"ike/link": None},
])
def test_unsafe_archives_rejected(updater, tmp_path, files):
    with pytest.raises(ValueError):
        updater.safe_extract(tar_gz(files), tmp_path / "out")
    assert not (tmp_path / "evil.py").exists()


def test_hash_mismatch_rejected(updater):
    payload = tar_gz({"ike/__init__.py": b'__version__ = "9.9.9"\n'})
    with pytest.raises(ValueError, match="hash"):
        updater.stage({"version": "9.9.9", "sha256": "0" * 64}, payload)
    assert not (updater.UPDATES / "versions" / "9.9.9").exists()


@pytest.mark.parametrize("version", ["../../escape", "1.0.0/../../x", "", "1", "1.0.0-beta", None])
def test_invalid_version_rejected(updater, version):
    """Even a correctly signed manifest cannot name a folder outside the updates."""
    import hashlib
    payload = tar_gz({"ike/__init__.py": b'__version__ = "9.9.9"\n'})
    with pytest.raises(ValueError, match="invalid version"):
        updater.stage({"version": version, "sha256": hashlib.sha256(payload).hexdigest()}, payload)
    assert not any(updater.UPDATES.parent.rglob("*.staging"))


def test_system_version(updater):
    import ike
    assert updater.system_version() == ike.__version__
    assert len(updater.vtuple(ike.__min_system__)) == 3


# --- release tool -----------------------------------------------------------

def make_update_json(tmp_path, pub):
    p = tmp_path / "update.json"
    p.write_text(json.dumps({"url": "https://example.test/download", "pubkey": pub}))
    return p


def test_release_files_signed_and_reproducible(updater, keypair, tmp_path):
    tool = load_tool()
    _, key_path, pub = keypair
    upd = make_update_json(tmp_path, pub)
    out1, manifest = tool.make(key_path, tmp_path / "r1", ["stable", "beta"], passphrase=PASS, update_file=upd)
    out2, _ = tool.make(key_path, tmp_path / "r2", ["stable"], passphrase=PASS, update_file=upd)

    import ike
    assert manifest["version"] == ike.__version__
    assert manifest["min_system"] == ike.__min_system__
    payload = (out1 / manifest["payload"]).read_bytes()
    assert payload == (out2 / manifest["payload"]).read_bytes()          # reproducible
    assert hashlib.sha256(payload).hexdigest() == manifest["sha256"]
    for ch in ("stable", "beta"):
        raw = (out1 / (ch + ".json")).read_bytes()
        assert json.loads(raw) == dict(manifest, channel=ch)       # bound to its channel (1.1.20)
        assert updater.verify_signature(pub, raw, (out1 / (ch + ".json.sig")).read_text().strip())
    with tarfile.open(fileobj=io.BytesIO(payload)) as tar:
        names = tar.getnames()
    assert all(n == "ike" or n.startswith("ike/") for n in names)
    assert "ike/__init__.py" in names and "ike/resources/lang/it.json" in names
    assert not [n for n in names if "__pycache__" in n or n.endswith(".pyc")]
    updater.safe_extract(payload, tmp_path / "x")            # the updater accepts it


def test_release_carries_the_adblock_engine(updater, keypair, tmp_path):
    """1.1.12: the engine built for the release travels in the signed update
    (ike/_engine/adblock), so a new engine reaches users without a package."""
    tool = load_tool()
    _, key_path, pub = keypair
    upd = make_update_json(tmp_path, pub)
    engine = tmp_path / "vendor" / "adblock"
    engine.mkdir(parents=True)
    for name, data in (("__init__.py", b"MODERN = True\n"), ("adblock.pyi", b""), ("py.typed", b""),
                       ("ike_adblock.abi3.so", b"\x7fELF engine")):
        (engine / name).write_bytes(data)
    out1, manifest = tool.make(key_path, tmp_path / "r1", ["stable"], passphrase=PASS, update_file=upd,
                               engine=engine)
    out2, _ = tool.make(key_path, tmp_path / "r2", ["stable"], passphrase=PASS, update_file=upd,
                        engine=engine)
    payload = (out1 / manifest["payload"]).read_bytes()
    assert payload == (out2 / manifest["payload"]).read_bytes()          # still reproducible
    with tarfile.open(fileobj=io.BytesIO(payload)) as tar:
        names = tar.getnames()
        so = tar.extractfile("ike/_engine/adblock/ike_adblock.abi3.so").read()
    assert so == b"\x7fELF engine"
    assert {"ike/_engine/adblock/__init__.py", "ike/_engine/adblock/py.typed"} <= set(names)
    updater.safe_extract(payload, tmp_path / "x")            # the updater accepts it
    assert (tmp_path / "x" / "ike" / "_engine" / "adblock" / "ike_adblock.abi3.so").is_file()
    # an engine folder without the module is refused, nothing is written
    (engine / "ike_adblock.abi3.so").unlink()
    with pytest.raises(SystemExit, match="lacks"):
        tool.make(key_path, tmp_path / "r3", ["stable"], passphrase=PASS, update_file=upd, engine=engine)
    assert not (tmp_path / "r3").exists()


def test_release_tool_refuses_wrong_or_misplaced_key(keypair, tmp_path):
    tool = load_tool()
    _, key_path, pub = keypair
    other = Ed25519PrivateKey.generate().public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    upd = make_update_json(tmp_path, base64.b64encode(other).decode())
    with pytest.raises(SystemExit, match="does not match"):
        tool.make(key_path, tmp_path / "r", ["stable"], passphrase=PASS, update_file=upd)
    with pytest.raises(SystemExit, match="inside the repository"):
        tool.make(ROOT / "ike-update.key", tmp_path / "r", ["stable"], passphrase=PASS,
                  update_file=make_update_json(tmp_path, pub))


def test_no_private_key_in_repository():
    try:
        names = subprocess.run(["git", "ls-files", "-co", "--exclude-standard"], cwd=ROOT,
                               capture_output=True, text=True, check=True).stdout.split()
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("not a git checkout")
    marker = b"PRIVATE" + b" KEY-----"
    for name in names:
        p = ROOT / name
        if p.is_file():
            assert marker not in p.read_bytes(), name


def test_shipped_update_channel():
    d = json.loads((ROOT / "data" / "update.json").read_text())
    if d.get("url"):
        assert d["url"].startswith("https://github.com/NullSector-2077/IKE-Browser/releases/")
        assert len(base64.b64decode(d["pubkey"])) == 32


# --- full update in the real browser ---------------------------------------

class Releases:
    """Serves /releases/latest/download/<file> with GitHub's two redirects."""

    def __init__(self):
        self.files = {}
        self.hits = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                outer.hits.append(self.path)
                m = re.fullmatch(r"/releases/latest/download/([^/]+)", self.path)
                if m:
                    self.send_response(302)
                    self.send_header("Location", "/releases/download/v-test/" + m.group(1))
                    self.end_headers()
                    return
                m = re.fullmatch(r"/releases/download/v-test/([^/]+)", self.path)
                if m and m.group(1) in outer.files:
                    self.send_response(302)
                    self.send_header("Location", "/assets/" + m.group(1))
                    self.end_headers()
                    return
                m = re.fullmatch(r"/assets/([^/]+)", self.path)
                if m and m.group(1) in outer.files:
                    data = outer.files[m.group(1)]
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return
                self.send_response(404)
                self.end_headers()

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = "http://127.0.0.1:%d/releases/latest/download" % self.server.server_port

    def publish(self, key, version, min_system="1.0.0", broken=False, bad_sig=False, extra=None):
        """Put a release of this repository's ike/ renamed as `version`."""
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            for p in sorted((ROOT / "ike").rglob("*")):
                if "__pycache__" in p.parts or p.is_dir():
                    continue
                data = p.read_bytes()
                name = p.relative_to(ROOT).as_posix()
                if name == "ike/__init__.py":
                    data = re.sub(rb'__version__ = "[^"]+"', b'__version__ = "%s"' % version.encode(), data)
                if broken and name == "ike/window.py":
                    data += b"\nraise RuntimeError('broken test update')\n"
                info = tarfile.TarInfo(name)
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
        payload = buf.getvalue()
        m = {"version": version, "payload": "ike-%s.tar.gz" % version,
             "sha256": hashlib.sha256(payload).hexdigest(), "min_system": min_system}
        # 1.1.18: valid for a day, as make-release.py writes them (expiry, staged release, halt)
        now = int(time.time())
        m.update({"issued": now, "expires": now + 86400})
        m.update(extra or {})
        for k in [k for k, v in m.items() if v is None]:
            del m[k]                            # extra={"expires": None}: a manifest from before 1.1.18
        manifest = json.dumps(m).encode()
        sig = key.sign(manifest + (b"x" if bad_sig else b""))
        self.files = {"stable.json": manifest, "stable.json.sig": base64.b64encode(sig),
                      "ike-%s.tar.gz" % version: payload}

    def close(self):
        self.server.shutdown()


@pytest.fixture
def releases():
    r = Releases()
    yield r
    r.close()


CHECK = """
    def steps(ike, qapp, out):
        import json, os, time
        from ike import updater
        result = []
        ike.updater.finished.connect(lambda kind, data: result.append((kind, data)))
        out["configured"] = ike.updater.configured()
        out["started"] = ike.updater.run(install=True)
        t = time.time()
        while not result and time.time() - t < 150:
            yield 200
        out["kind"], out["data"] = result[0] if result else ("timeout", None)
        out["state"] = updater.load_state()
        vdir = updater.UPDATES / "versions"
        out["versions"] = sorted(os.listdir(vdir)) if vdir.exists() else []
        out["running"] = __import__("ike").__version__
"""

RUNNING = """
    def steps(ike, qapp, out):
        from ike import updater
        yield 1500
        out["running"] = __import__("ike").__version__
        out["app_dir"] = __import__("os").environ.get("IKE_APP_DIR")
        updater.confirm_healthy()
        out["state"] = updater.load_state()
"""


def update_env(tmp_path, releases, pub):
    cfg = tmp_path / "test-update.json"
    cfg.write_text(json.dumps({"url": releases.url, "pubkey": pub}))
    return {"IKE_TEST_UPDATE_CONFIG": str(cfg), "NO_PROXY": "127.0.0.1,localhost",
            "no_proxy": "127.0.0.1,localhost"}


def test_full_update_through_github_like_releases(run_ike, releases, keypair, tmp_path):
    key, _, pub = keypair
    env = update_env(tmp_path, releases, pub)
    releases.publish(key, "99.0.0", min_system="0")
    out = run_ike(CHECK, env=env, timeout=240)
    assert out["configured"] and out["started"]
    assert out["kind"] == "installed", out["data"]
    assert out["state"]["current"] == "99.0.0" and out["state"]["status"] == "pending"
    assert out["versions"] == ["99.0.0"]
    assert any(h.startswith("/assets/ike-99.0.0") for h in releases.hits)    # redirects followed

    # next start: the verified update is used, then confirmed healthy
    out = run_ike(RUNNING, env=env, keep_profile=True)
    assert out["running"] == "99.0.0"
    assert Path(out["app_dir"]).parts[-2:] == ("versions", "99.0.0")
    assert out["state"]["status"] == "ok"

    # the same release again: nothing to do
    out = run_ike(CHECK, env=env, keep_profile=True, timeout=120)
    assert out["kind"] == "current"


def test_bad_signature_is_refused(run_ike, releases, keypair, tmp_path):
    key, _, pub = keypair
    releases.publish(key, "99.0.0", min_system="0", bad_sig=True)
    out = run_ike(CHECK, env=update_env(tmp_path, releases, pub), timeout=120)
    assert out["kind"] == "error" and "signature" in out["data"]
    assert out["versions"] == []
    assert not any(h.startswith("/assets/ike-") for h in releases.hits)      # payload never fetched


def test_update_failing_self_test_is_not_installed(run_ike, releases, keypair, tmp_path):
    key, _, pub = keypair
    releases.publish(key, "99.0.0", min_system="0", broken=True)
    out = run_ike(CHECK, env=update_env(tmp_path, releases, pub), timeout=240)
    assert out["kind"] == "error" and "self-test" in out["data"]
    assert out["versions"] == [] and not out["state"].get("current")


def test_update_needing_new_package_is_only_announced(run_ike, releases, keypair, tmp_path):
    key, _, pub = keypair
    releases.publish(key, "99.0.0", min_system="99.0.0")
    out = run_ike(CHECK, env=update_env(tmp_path, releases, pub), timeout=120)
    assert out["kind"] == "system"
    assert out["versions"] == []
    assert not any(h.startswith("/assets/ike-") for h in releases.hits)
    assert out["state"].get("system_notice") == "99.0.0"       # told once, not every day


def test_rollback_of_update_that_does_not_start(run_ike, tmp_path):
    """An installed update that crashes at start-up: the next start goes back."""
    data = tmp_path / "home" / ".local/share/ike-browser/updates"
    vdir = data / "versions" / "99.0.0"
    shutil.copytree(ROOT / "ike", vdir / "ike", ignore=shutil.ignore_patterns("__pycache__"))
    init = vdir / "ike" / "__init__.py"
    init.write_text(re.sub(r'__version__ = "[^"]+"', '__version__ = "99.0.0"', init.read_text()))
    (vdir / "ike" / "app.py").write_text("raise RuntimeError('crash at start')\n")
    (data / "state.json").write_text(json.dumps({"current": "99.0.0", "status": "pending", "attempts": 0}))
    out = run_ike(RUNNING)
    import ike
    assert out["running"] == ike.__version__
    state = json.loads((data / "state.json").read_text())
    assert "99.0.0" in state["bad"] and not state["current"]


# --- 1.1.13: updates install by themselves for everyone ------------------------

def test_automatic_updates_by_default_and_old_ask_moved_once(tmp_path):
    """The owner's rule: users only browse. A new profile installs updates by
    itself; the old default "ask" becomes "auto" once; "off" stays the user's
    choice, and so does "ask" chosen again afterwards."""
    from ike.config import Config
    assert Config(tmp_path / "new.json")["app_updates"] == "auto"
    old = tmp_path / "old.json"
    old.write_text(json.dumps({"app_updates": "ask"}))
    cfg = Config(old)
    assert cfg["app_updates"] == "auto"
    cfg["app_updates"] = "ask"                       # chosen again by the user, then saved
    cfg.save()
    assert Config(old)["app_updates"] == "ask"
    off = tmp_path / "off.json"
    off.write_text(json.dumps({"app_updates": "off"}))
    assert Config(off)["app_updates"] == "off"


UPDATE_STEPS = r'''
from PyQt6.QtCore import Qt
def steps(ike, qapp, out):
    out["migrated"] = ike.config["app_updates"]
    # the daily check installs without asking
    calls = []
    ike.updater.configured = lambda: True
    ike.updater.run = lambda install: calls.append(install) or True
    ike.config["last_app_check"] = 0
    ike.check_updates()
    out["install"] = list(calls)
    # Settings: "Install automatically" is the first choice and the current one;
    # the user can still turn updates off
    dlg = ike.show_settings(ike.windows[0], "general")
    yield 300
    out["items"] = [dlg.upd.itemData(i) for i in range(dlg.upd.count())]
    out["current"] = dlg.upd.currentData()
    dlg.upd.setFocus()
    dlg.upd.setCurrentIndex(dlg.upd.findData("off"))
    yield 100
    dlg.apply()
    dlg.close()
    out["saved"] = ike.config["app_updates"]
    calls.clear()
    ike.config["last_app_check"] = 0
    ike.check_updates()
    out["after_off"] = list(calls)
'''


def test_updates_install_by_themselves_in_the_browser(run_ike):
    out = run_ike(UPDATE_STEPS, settings={"app_updates": "ask", "app_updates_1113": False})
    assert out["migrated"] == "auto"
    assert out["install"] == [True]
    assert out["items"][0] == "auto" and out["current"] == "auto"
    assert out["saved"] == "off" and out["after_off"] == []


def test_one_installation_at_a_time(updater):
    """Two profiles of I.K.E. share the updates folder: while one installs,
    the other's attempt is refused and touches nothing (1.1.17)."""
    import fcntl
    payload = tar_gz({"ike/__init__.py": b'__version__ = "9.9.9"\n'})
    updater.UPDATES.mkdir(parents=True, exist_ok=True)
    with open(updater.UPDATES / ".lock", "w") as other:
        fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(ValueError, match="another I.K.E."):
            updater.stage({"version": "9.9.9", "sha256": hashlib.sha256(payload).hexdigest()}, payload)
    assert not any(updater.UPDATES.rglob("*.staging"))
    with pytest.raises(ValueError, match="hash"):          # free again: checks go on as before
        updater.stage({"version": "9.9.9", "sha256": "0" * 64}, payload)
