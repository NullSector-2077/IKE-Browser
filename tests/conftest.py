"""Start the real browser without a display and run checks inside it.

Each call of ``run_ike`` starts I.K.E. from this repository with an empty
profile in a temporary folder, ``QT_QPA_PLATFORM=offscreen`` and no network
updates, runs the given ``steps`` script inside it (see tests/harness.py) and
returns what the script recorded.
"""

import hashlib
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
# the copy of I.K.E. to start: this repository, or an installed one
# (IKE_TEST_APP=/usr/lib/ike-browser python3 -m pytest)
APP = Path(os.environ.get("IKE_TEST_APP") or ROOT)
HARNESS = Path(__file__).resolve().parent / "harness.py"
# a tiny filter list stored in place of EasyList, so nothing is downloaded
TEST_LIST_URL = "https://easylist.to/easylist/easylist.txt"
TEST_LIST = "||ads.example.test^\n/banner-ad.$image\n##.ike-test-ad\n"

# no list, version or update downloads while testing
QUIET_SETTINGS = {
    "lists_version": 3,
    "last_lists_update": 4102444800,
    "last_fast_update": 4102444800,
    "chrome_checked": 4102444800,
    "app_updates": "off",
    "auto_update": False,
}


def _engine_available():
    try:
        sys.path.insert(0, str(APP / "vendor"))
        import adblock  # noqa: F401
        return True
    except Exception:
        return False
    finally:
        sys.path.remove(str(APP / "vendor"))


def write_profile(cfg, data_dir, settings=None, keep=False):
    """Quiet settings and the tiny filter list (no downloads while testing)."""
    cfg.mkdir(parents=True, exist_ok=True)
    data = dict(QUIET_SETTINGS)
    if keep and (cfg / "settings.json").exists():
        data = json.loads((cfg / "settings.json").read_text("utf-8"))
    data.update(settings or {})
    (cfg / "settings.json").write_text(json.dumps(data), "utf-8")
    lists = data_dir / "lists"
    lists.mkdir(parents=True, exist_ok=True)
    name = hashlib.sha1(TEST_LIST_URL.encode()).hexdigest()[:16] + ".txt"
    (lists / name).write_text(TEST_LIST, "utf-8")


@pytest.fixture
def run_ike(tmp_path):
    def run(script, settings=None, env=None, timeout=90, args=(), keep_profile=False, command=None,
            wait_results=0, prepare=True, internal_errors=False):
        """keep_profile=True: start again with the profile of the previous run.
        internal_errors=True: the test expects errors inside the browser
        (otherwise one such error fails the test, though the browser goes on).
        command: the program to start instead of this copy of I.K.E.;
        wait_results: seconds to wait for the results after the program ended
        (when it hands over to another process)."""
        home = tmp_path / "home"
        if prepare:         # prepare=False: the profile is left as the test made it
            write_profile(home / ".config" / "ike-browser", home / ".local/share" / "ike-browser",
                          settings, keep_profile)
        script_file = tmp_path / "steps.py"
        script_file.write_text(textwrap.dedent(script), "utf-8")
        out_file = tmp_path / "out.json"
        e = {k: v for k, v in os.environ.items()
             if not k.startswith(("XDG_", "IKE_", "LANG", "LC_"))}
        e.update({
            "HOME": str(home),
            "XDG_CONFIG_HOME": str(home / ".config"),
            "XDG_DATA_HOME": str(home / ".local/share"),
            "XDG_CACHE_HOME": str(home / ".cache"),
            "XDG_RUNTIME_DIR": str(tmp_path / "run"),
            "QT_QPA_PLATFORM": "offscreen",
            "QTWEBENGINE_CHROMIUM_FLAGS": "--no-sandbox",
            "QTWEBENGINE_DISABLE_SANDBOX": "1",
            "LANG": "C.UTF-8",
            "IKE_NO_SINGLE": "1",
            "IKE_TEST_NOASK": "1",
            "IKE_TEST_HOOK": str(HARNESS),
            "IKE_TEST_SCRIPT": str(script_file),
            "IKE_TEST_OUT": str(out_file),
        })
        (tmp_path / "run").mkdir(mode=0o700, exist_ok=True)
        # no desktop bus unless a test brings its own (see desktop_bus below)
        e["DBUS_SESSION_BUS_ADDRESS"] = ""
        e.update(env or {})
        cmd = [sys.executable, str(APP / "ike_boot.py")]
        e.setdefault("PYTHONUTF8", "1")
        if command:
            cmd = list(command)
        if out_file.exists():
            out_file.unlink()
        proc = subprocess.run([*cmd, *args],
                              cwd=str(tmp_path), env=e, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout)
        if wait_results and not out_file.exists():
            import time
            end = time.time() + wait_results
            while time.time() < end and not out_file.exists():
                time.sleep(0.5)
            time.sleep(1)
        if not out_file.exists():
            err = proc.stderr
            if len(err) > 8000:                  # the start too: a fatal check is often early
                err = err[:3000] + "\n[...]\n" + err[-5000:]
            raise AssertionError("the browser ended without results (exit %s)\n%s"
                                 % (proc.returncode, err))
        out = json.loads(out_file.read_text("utf-8"))
        out["_exit"] = proc.returncode
        out["_stderr"] = proc.stderr
        assert "error" not in out, out["error"]
        if not internal_errors:
            assert not out.get("_internal_errors"), "\n".join(out["_internal_errors"])
        return out
    return run


@pytest.fixture
def desktop_bus(tmp_path):
    """A private D-Bus session bus with stand-ins for Plasma's services.

    Yields (address, log): ``log()`` returns the calls the stand-ins received."""
    import shutil
    import time
    if not shutil.which("dbus-daemon"):
        pytest.skip("dbus-daemon not installed")
    pytest.importorskip("jeepney")
    daemon = subprocess.Popen(["dbus-daemon", "--session", "--nofork", "--print-address=1"],
                              stdout=subprocess.PIPE, text=True)
    address = daemon.stdout.readline().strip()
    logfile = tmp_path / "standins.log"
    env = dict(os.environ, DBUS_SESSION_BUS_ADDRESS=address)
    standins = subprocess.Popen([sys.executable, str(Path(__file__).parent / "dbus_standins.py"),
                                 str(logfile)], env=env)

    def log():
        if not logfile.exists():
            return []
        return [json.loads(line) for line in logfile.read_text("utf-8").splitlines() if line.strip()]

    for _ in range(100):
        if log():
            break
        time.sleep(0.05)
    try:
        yield address, log, logfile
    finally:
        standins.kill()
        daemon.kill()
        standins.wait()
        daemon.wait()


needs_engine = pytest.mark.skipif(not _engine_available(),
                                  reason="I.K.E. AdBlock engine not built (see docs/BUILDING.md)")


# Switches that give WebGL without a graphics card, in order of preference:
# Mesa's software GL through ANGLE (what a desktop without a GPU driver uses),
# then the engine's own SwiftShader (left out by some distributions, such as
# Debian). Compositing stays in software: with it on the GPU, distribution
# builds of Qt WebEngine (Ubuntu 26.04, Fedora 43) ended with SIGTRAP in two
# runs out of four in a container; with it in software, four out of four
# passed with either kind of WebGL (measured on GitHub Actions, 2026-11-16).
SOFTWARE_WEBGL = (
    "--use-angle=gl --ignore-gpu-blocklist --disable-gpu-compositing",
    "--enable-unsafe-swiftshader --use-angle=swiftshader --ignore-gpu-blocklist --disable-gpu-compositing",
    "--use-angle=swiftshader-webgl --ignore-gpu-blocklist --disable-gpu-compositing",
    # Debian 13's engine (Chromium 122, no SwiftShader) gives WebGL only with
    # compositing on the GPU; it was steady there (several full runs)
    "--use-angle=gl --ignore-gpu-blocklist",
)
_WEBGL_PROBE = r"""
import sys
from PyQt6.QtCore import QCoreApplication, Qt, QTimer, QUrl
QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
from PyQt6.QtWidgets import QApplication
from PyQt6.QtWebEngineWidgets import QWebEngineView
app = QApplication(sys.argv[:1])
v = QWebEngineView()
v.resize(200, 200)
v.show()
def done(r):
    print("WEBGL=%s" % r)
    app.quit()
v.loadFinished.connect(lambda ok: v.page().runJavaScript(
    "!!document.createElement('canvas').getContext('webgl')", done))
v.setHtml("<p>x</p>")
QTimer.singleShot(30000, app.quit)
app.exec()
"""
_webgl_flags = []


def software_webgl_flags():
    """The first set of SOFTWARE_WEBGL with which this engine gives WebGL, or
    None. Asked once per test session, in a separate process each time."""
    if os.environ.get("IKE_TEST_WEBGL_FLAGS"):         # chosen by hand (diagnostics)
        return os.environ["IKE_TEST_WEBGL_FLAGS"]
    if _webgl_flags:
        return _webgl_flags[0]
    found = None
    for flags in SOFTWARE_WEBGL:
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen",
                   QTWEBENGINE_CHROMIUM_FLAGS="--no-sandbox " + flags)
        try:
            r = subprocess.run([sys.executable, "-c", _WEBGL_PROBE], env=env, capture_output=True,
                               text=True, timeout=60)
        except subprocess.TimeoutExpired:
            continue
        if "WEBGL=True" in r.stdout:
            found = flags
            break
    _webgl_flags.append(found)
    return found
