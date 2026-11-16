"""I.K.E. inside a Flatpak (packaging/flatpak/README.md).

Flatpak exports the desktop entry and the icon under the application ID, so
every name I.K.E. gives the desktop (the window's desktop file, the media
controls, notifications, Plasma's download view, KRunner) is that ID inside a
Flatpak and "ike-browser" everywhere else. The default-browser button does not
call xdg-settings there: it would only change the sandbox's own copy.

The Flatpak is simulated with FLATPAK_ID; the Flatpak workflow also runs this
file inside the real sandbox, where the cases "outside a Flatpak" are
skipped."""

import json
import os
import sys

import pytest
from conftest import IN_FLATPAK_SANDBOX

APP_ID = "io.github.nullsector_2077.IKE-Browser"
outside_only = pytest.mark.skipif(IN_FLATPAK_SANDBOX, reason="runs inside a real Flatpak sandbox")


def test_desktop_id(monkeypatch, tmp_path):
    from ike import osinfo
    monkeypatch.setattr(osinfo, "FLATPAK_INFO", str(tmp_path / "missing"))
    monkeypatch.delenv("FLATPAK_ID", raising=False)
    assert osinfo.desktop_id() == "ike-browser" and not osinfo.in_flatpak()
    monkeypatch.setenv("FLATPAK_ID", APP_ID)
    assert osinfo.desktop_id() == APP_ID and osinfo.in_flatpak()
    # never a path or anything else a desktop service would read as more than a name
    for bad in ("../../x", "a/b.c", "nodots", "-x.y", "x.y z", "x.y\n"):
        monkeypatch.setenv("FLATPAK_ID", bad)
        assert osinfo.desktop_id() == "ike-browser", bad


def test_notification_icon_in_flatpak(tmp_path, monkeypatch):
    from ike import osinfo
    log = tmp_path / "argv.json"
    fake = tmp_path / "notify-send"
    fake.write_text("#!%s\nimport json, sys\njson.dump(sys.argv[1:], open(%r, 'w'))\n" % (sys.executable, str(log)))
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", "%s:%s" % (tmp_path, os.environ["PATH"]))
    monkeypatch.setenv("FLATPAK_ID", APP_ID)
    osinfo.notify("Title", "Text")
    import time
    for _ in range(100):
        if log.exists() and log.stat().st_size:
            break
        time.sleep(0.05)
    assert json.loads(log.read_text()) == ["-a", "I.K.E.", "-i", APP_ID, "--", "Title", "Text"]


DEFAULT_BROWSER = r'''
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QPushButton

def steps(ike, qapp, out):
    from ike.dialogs import SettingsDialog
    out["desktop_file"] = qapp.desktopFileName()
    win = ike.windows[0]
    dlg = SettingsDialog(ike, win)
    dlg.show()
    yield 400
    btn = [b for b in dlg.findChildren(QPushButton) if "default browser" in b.text()][0]
    for row in range(dlg.nav.count()):          # the settings page that holds the button
        dlg.nav.setCurrentRow(row)
        yield 50
        if btn.isVisible():
            break
    out["visible"] = btn.isVisible()
    seen = []

    def close_box():
        box = QApplication.activeModalWidget()
        if box is not None and box is not dlg:
            seen.append(box.text())
            box.close()
        else:
            QTimer.singleShot(100, close_box)
    QTimer.singleShot(300, close_box)
    QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
    yield 500
    out["message"] = seen
    dlg.close()
'''


def _fake_xdg_settings(tmp_path):
    log = tmp_path / "xdg-settings.json"
    fake = tmp_path / "bin" / "xdg-settings"
    fake.parent.mkdir()
    fake.write_text("#!%s\nimport json, sys\njson.dump(sys.argv[1:], open(%r, 'w'))\n" % (sys.executable, str(log)))
    fake.chmod(0o755)
    return log, "%s:%s" % (fake.parent, os.environ["PATH"])


def test_default_browser_button_in_flatpak(run_ike, tmp_path):
    log, path = _fake_xdg_settings(tmp_path)
    out = run_ike(DEFAULT_BROWSER, env={"PATH": path, "FLATPAK_ID": APP_ID}, timeout=120)
    assert out["desktop_file"] == APP_ID
    assert out["visible"]
    assert not log.exists()                     # the sandbox's own copy is left alone
    assert len(out["message"]) == 1 and "System Settings" in out["message"][0]


@outside_only
def test_default_browser_button_outside_flatpak(run_ike, tmp_path):
    """Unchanged outside a Flatpak: xdg-settings with ike-browser.desktop."""
    log, path = _fake_xdg_settings(tmp_path)
    out = run_ike(DEFAULT_BROWSER, env={"PATH": path, "FLATPAK_ID": ""}, timeout=120)
    assert out["desktop_file"] == "ike-browser"
    assert json.loads(log.read_text()) == ["set", "default-web-browser", "ike-browser.desktop"]
    assert out["message"] == ["I.K.E. is now the default browser."]


# --- a restart (Settings → Restart) and another profile ----------------------
# Inside a Flatpak every process of the sandbox ends with the program that
# started it: the new copy has to be started through Flatpak's portal
# (flatpak-spawn), in a sandbox of its own, and waits for a lock instead of a
# process number. The stand-in flatpak-spawn records how it was called and
# then starts the command itself, as the portal would.

FAKE_SPAWN = r'''#!%(python)s
import fcntl, json, os, sys
args = sys.argv[1:]
env = dict(os.environ)
passed = []
while args and args[0].startswith("--env="):
    k, _, v = args.pop(0)[len("--env="):].partition("=")
    env[k] = v
    passed.append(k)
lock = os.path.join(env["XDG_CACHE_HOME"], "ike-browser", "restart.lock")
try:
    with open(lock, "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    free = True
except OSError:
    free = False
json.dump({"env": passed, "cmd": args, "lock_free": free}, open(%(log)r, "w"))
if os.environ.get("FAKE_SPAWN_RUN") == "1":
    os.execve(args[0], args, env)
'''

RESTART = r'''
import json, os

def steps(ike, qapp, out):
    marker = os.path.join(os.environ["HOME"], "restarted-once")
    if os.path.exists(marker):              # the new copy
        first = json.load(open(marker))["pid"]
        try:
            alive = "\nState:\tZ" not in open("/proc/%d/status" % first).read()
        except OSError:
            alive = False
        views = ike.windows[0].views
        out["second"] = {"pid": os.getpid(), "first_alive": alive,
                         "urls": [getattr(v, "pending_url", None) or v.url().toString() for v in views]}
        yield 200
        return
    win = ike.windows[0]
    win.add_tab("data:text/html,<title>kept</title>kept")
    yield 1500
    json.dump({"pid": os.getpid()}, open(marker, "w"))
    out["first"] = os.getpid()
    json.dump(out, open(os.environ["IKE_TEST_OUT"], "w"))
    ike.restart()
    yield 10000
'''


def _spawn_stand_in(tmp_path):
    log = tmp_path / "spawn.json"
    fake = tmp_path / "bin" / "flatpak-spawn"
    fake.parent.mkdir(exist_ok=True)
    fake.write_text(FAKE_SPAWN % {"python": sys.executable, "log": str(log)})
    fake.chmod(0o755)
    return log, "%s:%s" % (fake.parent, os.environ["PATH"])


def _second_start(tmp_path, timeout=90):
    import time
    out_file = tmp_path / "out.json"
    end = time.time() + timeout
    while time.time() < end:
        try:
            data = json.loads(out_file.read_text("utf-8"))
            if "second" in data:
                return data["second"]
        except (OSError, ValueError):
            pass
        time.sleep(0.5)
    raise AssertionError("the browser did not start again")


def test_restart_in_flatpak_goes_through_the_portal(run_ike, tmp_path):
    log, path = _spawn_stand_in(tmp_path)
    run_ike(RESTART, env={"PATH": path, "FLATPAK_ID": APP_ID, "FAKE_SPAWN_RUN": "1"}, timeout=120)
    second = _second_start(tmp_path)
    first = json.loads((tmp_path / "home" / "restarted-once").read_text())["pid"]
    spawn = json.loads(log.read_text())
    assert spawn["env"] == ["IKE_WAIT_LOCK"] and spawn["cmd"][-1].endswith("ike_boot.py")
    assert spawn["lock_free"] is False               # held by the closing copy
    assert second["pid"] != first and second["first_alive"] is False
    assert any("kept" in u for u in second["urls"])  # the tabs came back


@outside_only
def test_restart_outside_flatpak_unchanged(run_ike, tmp_path):
    log, path = _spawn_stand_in(tmp_path)
    run_ike(RESTART, env={"PATH": path, "FLATPAK_ID": ""}, timeout=120)
    second = _second_start(tmp_path)
    first = json.loads((tmp_path / "home" / "restarted-once").read_text())["pid"]
    assert not log.exists()                          # started directly, as before
    assert second["pid"] != first and second["first_alive"] is False
    assert any("kept" in u for u in second["urls"])


def test_other_profile_in_flatpak_gets_its_own_sandbox(tmp_path, monkeypatch):
    from ike import app
    log, path = _spawn_stand_in(tmp_path)
    monkeypatch.setenv("PATH", path)
    monkeypatch.setenv("FLATPAK_ID", APP_ID)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    (tmp_path / "cache" / "ike-browser").mkdir(parents=True)
    app.start_detached(["/bin/true", "--profile", "work"], dict(os.environ, IKE_PROFILE="work", SECRET="x"),
                       keep=("IKE_PROFILE",), stdin=None)
    import time
    for _ in range(100):
        if log.exists() and log.stat().st_size:
            break
        time.sleep(0.05)
    spawn = json.loads(log.read_text())
    assert spawn["env"] == ["IKE_PROFILE"] and spawn["cmd"] == ["/bin/true", "--profile", "work"]
