"""Self-update: signatures, release files, and a full update through a local
server that answers like GitHub Releases (redirects included)."""

import base64
import hashlib
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from conftest import ROOT

sys.path.insert(0, str(ROOT))

cryptography = pytest.importorskip("cryptography")
from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402

PASS = "test passphrase"
# these tests drive the update of a copy started from source; a real AppImage
# is tested by test_real_appimage_updates_itself instead
from_source = pytest.mark.skipif(bool(os.environ.get("ICE_TEST_APPIMAGE") or os.environ.get("ICE_TEST_EXE")),
                                 reason="started from source only (an AppImage would update itself)")
linux_only = pytest.mark.skipif(sys.platform == "win32", reason="AppImages exist on Linux only")


def load_tool():
    spec = importlib.util.spec_from_file_location("make_release", ROOT / "tools" / "make-release.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def updater(tmp_path, monkeypatch):
    from ice import updater as u
    monkeypatch.setattr(u, "UPDATES", tmp_path / "updates")
    monkeypatch.setattr(u, "STATE", tmp_path / "updates" / "state.json")
    return u


@pytest.fixture
def keypair(tmp_path):
    """An encrypted PEM key outside the repository and its base64 public key."""
    key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.BestAvailableEncryption(PASS.encode()))
    path = tmp_path / "keys" / "ice-update.key"
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
    assert updater.plain_name("ice-1.4.1.tar.gz")
    assert updater.plain_name("IKE-Browser-1.4.1-x86_64.AppImage")
    for bad in ("", None, "../ice.tar.gz", "/etc/passwd", "a/b.tar.gz",
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


def test_system_version(updater):
    import ice
    assert updater.system_version() == ice.__version__
    assert len(updater.vtuple(ice.__min_system__)) == 3


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

    import ice
    assert manifest["version"] == ice.__version__
    assert manifest["min_system"] == ice.__min_system__
    payload = (out1 / manifest["payload"]).read_bytes()
    assert payload == (out2 / manifest["payload"]).read_bytes()          # reproducible
    assert hashlib.sha256(payload).hexdigest() == manifest["sha256"]
    for ch in ("stable", "beta"):
        raw = (out1 / (ch + ".json")).read_bytes()
        assert json.loads(raw) == manifest
        assert updater.verify_signature(pub, raw, (out1 / (ch + ".json.sig")).read_text().strip())
    with tarfile.open(fileobj=io.BytesIO(payload)) as tar:
        names = tar.getnames()
    assert all(n == "ike" or n.startswith("ike/") for n in names)
    assert "ike/__init__.py" in names and "ike/resources/lang/it.json" in names
    assert not [n for n in names if "__pycache__" in n or n.endswith(".pyc")]
    updater.safe_extract(payload, tmp_path / "x")            # the updater accepts it


def test_release_tool_refuses_wrong_or_misplaced_key(keypair, tmp_path):
    tool = load_tool()
    _, key_path, pub = keypair
    other = Ed25519PrivateKey.generate().public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    upd = make_update_json(tmp_path, base64.b64encode(other).decode())
    with pytest.raises(SystemExit, match="does not match"):
        tool.make(key_path, tmp_path / "r", ["stable"], passphrase=PASS, update_file=upd)
    with pytest.raises(SystemExit, match="inside the repository"):
        tool.make(ROOT / "ice-update.key", tmp_path / "r", ["stable"], passphrase=PASS,
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

    def publish(self, key, version, min_system="1.4.0", broken=False, bad_sig=False,
                appimage=None, appimage_sha=None):
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
        m = {"version": version, "payload": "ice-%s.tar.gz" % version,
             "sha256": hashlib.sha256(payload).hexdigest(), "min_system": min_system}
        name = "IKE-Browser-%s-x86_64.AppImage" % version
        if appimage is not None:
            m["appimage"] = {"file": name, "size": len(appimage),
                             "sha256": appimage_sha or hashlib.sha256(appimage).hexdigest()}
        manifest = json.dumps(m).encode()
        sig = key.sign(manifest + (b"x" if bad_sig else b""))
        self.files = {"stable.json": manifest, "stable.json.sig": base64.b64encode(sig),
                      "ice-%s.tar.gz" % version: payload}
        if appimage is not None:
            self.files[name] = appimage

    def close(self):
        self.server.shutdown()


@pytest.fixture
def releases():
    r = Releases()
    yield r
    r.close()


CHECK = """
    def steps(ice, qapp, out):
        import json, os, time
        from ice import updater
        result = []
        ice.updater.finished.connect(lambda kind, data: result.append((kind, data)))
        out["configured"] = ice.updater.configured()
        out["started"] = ice.updater.run(install=True)
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
    def steps(ice, qapp, out):
        from ice import updater
        yield 1500
        out["running"] = __import__("ike").__version__
        out["app_dir"] = __import__("os").environ.get("IKE_APP_DIR")
        updater.confirm_healthy()
        out["state"] = updater.load_state()
"""


def update_env(tmp_path, releases, pub):
    cfg = tmp_path / "test-update.json"
    cfg.write_text(json.dumps({"url": releases.url, "pubkey": pub}))
    return {"ICE_TEST_UPDATE_CONFIG": str(cfg), "NO_PROXY": "127.0.0.1,localhost",
            "no_proxy": "127.0.0.1,localhost"}


@from_source
def test_full_update_through_github_like_releases(run_ice, releases, keypair, tmp_path):
    key, _, pub = keypair
    env = update_env(tmp_path, releases, pub)
    releases.publish(key, "99.0.0", min_system="0")
    out = run_ice(CHECK, env=env, timeout=240)
    assert out["configured"] and out["started"]
    assert out["kind"] == "installed", out["data"]
    assert out["state"]["current"] == "99.0.0" and out["state"]["status"] == "pending"
    assert out["versions"] == ["99.0.0"]
    assert any(h.startswith("/assets/ice-99.0.0") for h in releases.hits)    # redirects followed

    # next start: the verified update is used, then confirmed healthy
    out = run_ice(RUNNING, env=env, keep_profile=True)
    assert out["running"] == "99.0.0"
    assert Path(out["app_dir"]).parts[-2:] == ("versions", "99.0.0")
    assert out["state"]["status"] == "ok"

    # the same release again: nothing to do
    out = run_ice(CHECK, env=env, keep_profile=True, timeout=120)
    assert out["kind"] == "current"


@from_source
def test_bad_signature_is_refused(run_ice, releases, keypair, tmp_path):
    key, _, pub = keypair
    releases.publish(key, "99.0.0", min_system="0", bad_sig=True)
    out = run_ice(CHECK, env=update_env(tmp_path, releases, pub), timeout=120)
    assert out["kind"] == "error" and "signature" in out["data"]
    assert out["versions"] == []
    assert not any(h.startswith("/assets/ice-") for h in releases.hits)      # payload never fetched


@from_source
def test_update_failing_self_test_is_not_installed(run_ice, releases, keypair, tmp_path):
    key, _, pub = keypair
    releases.publish(key, "99.0.0", min_system="0", broken=True)
    out = run_ice(CHECK, env=update_env(tmp_path, releases, pub), timeout=240)
    assert out["kind"] == "error" and "self-test" in out["data"]
    assert out["versions"] == [] and not out["state"].get("current")


@from_source
def test_update_needing_new_package_is_only_announced(run_ice, releases, keypair, tmp_path):
    key, _, pub = keypair
    releases.publish(key, "99.0.0", min_system="99.0.0")
    out = run_ice(CHECK, env=update_env(tmp_path, releases, pub), timeout=120)
    assert out["kind"] == "system"
    assert out["versions"] == []
    assert not any(h.startswith("/assets/ice-") for h in releases.hits)
    assert out["state"].get("system_notice") == "99.0.0"       # told once, not every day


@from_source
def test_rollback_of_update_that_does_not_start(run_ice, tmp_path):
    """An installed update that crashes at start-up: the next start goes back."""
    data = tmp_path / "home" / ".local/share/ike-browser/updates"
    vdir = data / "versions" / "99.0.0"
    shutil.copytree(ROOT / "ike", vdir / "ike", ignore=shutil.ignore_patterns("__pycache__"))
    init = vdir / "ike" / "__init__.py"
    init.write_text(re.sub(r'__version__ = "[^"]+"', '__version__ = "99.0.0"', init.read_text()))
    (vdir / "ike" / "app.py").write_text("raise RuntimeError('crash at start')\n")
    (data / "state.json").write_text(json.dumps({"current": "99.0.0", "status": "pending", "attempts": 0}))
    out = run_ice(RUNNING)
    import ice
    assert out["running"] == ice.__version__
    state = json.loads((data / "state.json").read_text())
    assert "99.0.0" in state["bad"] and not state["current"]


# --- AppImage: the whole file is replaced ------------------------------------

def fake_appimage(version):
    """A stand-in AppImage that only answers the self-test."""
    return ('#!/bin/sh\n[ "$1" = --selftest ] && echo "IKE-SELFTEST-OK %s"\n' % version).encode()


def appimage_env(tmp_path, releases, pub):
    apps = tmp_path / "Applications"
    apps.mkdir(exist_ok=True)
    current = apps / "IKE-Browser.AppImage"
    current.write_bytes(fake_appimage("1.0.0"))
    current.chmod(0o755)
    env = update_env(tmp_path, releases, pub)
    env.update({"APPIMAGE": str(current), "ICE_PACKAGE": "appimage"})
    return env, current


@from_source
@linux_only
def test_appimage_replaced(run_ice, releases, keypair, tmp_path):
    key, _, pub = keypair
    env, current = appimage_env(tmp_path, releases, pub)
    old = current.read_bytes()
    new = fake_appimage("99.0.0")
    releases.publish(key, "99.0.0", min_system="99.0.0", appimage=new)
    out = run_ice(CHECK, env=env, timeout=240)
    assert out["kind"] == "installed", out["data"]
    assert current.read_bytes() == new and os.access(current, os.X_OK)
    assert (current.parent / (current.name + ".previous")).read_bytes() == old
    assert sorted(p.name for p in current.parent.iterdir()) == [current.name, current.name + ".previous"]
    assert out["state"]["appimage"]["version"] == "99.0.0"
    assert out["versions"] == []                    # no separate ike/ copy for AppImages
    assert not any(h.startswith("/assets/ice-") for h in releases.hits)


@from_source
@linux_only
@pytest.mark.parametrize("case", ["hash", "selftest", "missing"])
def test_appimage_not_replaced(run_ice, releases, keypair, tmp_path, case):
    key, _, pub = keypair
    env, current = appimage_env(tmp_path, releases, pub)
    old = current.read_bytes()
    if case == "hash":
        releases.publish(key, "99.0.0", appimage=fake_appimage("99.0.0"), appimage_sha="0" * 64)
    elif case == "selftest":
        releases.publish(key, "99.0.0", appimage=fake_appimage("98.0.0"))
    else:
        releases.publish(key, "99.0.0")
    out = run_ice(CHECK, env=env, timeout=240)
    assert out["kind"] == {"hash": "error", "selftest": "error", "missing": "system"}[case], out["data"]
    if case != "missing":
        assert case.replace("selftest", "self-test") in out["data"]
    assert current.read_bytes() == old
    assert [p.name for p in current.parent.iterdir()] == [current.name]


def _selftest_version(appimage):
    res = subprocess.run([str(appimage), "--selftest"], capture_output=True, text=True, timeout=180,
                         env=dict(os.environ, QT_QPA_PLATFORM="offscreen"))
    return re.search(r"IKE-SELFTEST-OK (\S+)", res.stdout).group(1)


@pytest.mark.skipif(not (os.environ.get("ICE_TEST_APPIMAGE") and os.environ.get("ICE_TEST_APPIMAGE_NEW")),
                    reason="needs two real AppImages: ICE_TEST_APPIMAGE and a newer ICE_TEST_APPIMAGE_NEW")
def test_real_appimage_updates_itself(run_ice, releases, keypair, tmp_path, monkeypatch):
    """A real AppImage downloads a real newer AppImage, checks it, swaps, restarts into it."""
    key, _, pub = keypair
    current = tmp_path / "Applications" / "IKE-Browser.AppImage"
    current.parent.mkdir()
    shutil.copy2(Path(os.environ["ICE_TEST_APPIMAGE"]).resolve(), current)
    new = Path(os.environ["ICE_TEST_APPIMAGE_NEW"]).read_bytes()
    old_version = _selftest_version(current)
    new_version = _selftest_version(os.environ["ICE_TEST_APPIMAGE_NEW"])
    releases.publish(key, new_version, appimage=new)
    monkeypatch.setenv("ICE_TEST_APPIMAGE", str(current))
    env = update_env(tmp_path, releases, pub)
    out = run_ice(CHECK, env=env, timeout=400)
    assert out["running"] == old_version
    assert out["kind"] == "installed", out["data"]
    assert current.read_bytes() == new
    out = run_ice(RUNNING, env=env, keep_profile=True, timeout=120)
    assert out["running"] == new_version
