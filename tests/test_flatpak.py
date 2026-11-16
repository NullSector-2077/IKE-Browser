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
