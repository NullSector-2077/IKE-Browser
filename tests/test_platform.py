"""Operating-system details (ike/osinfo.py, ike/drm.py)."""

import io
import json
import os
import struct
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from conftest import ROOT

from ike import drm, osinfo


def test_folders(monkeypatch):
    for v in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME"):
        monkeypatch.delenv(v, raising=False)
    home = Path.home()
    assert osinfo.app_dir("config") == home / ".config" / "ike-browser"
    assert osinfo.app_dir("data") == home / ".local/share" / "ike-browser"
    assert osinfo.app_dir("cache") == home / ".cache" / "ike-browser"


def test_folders_follow_xdg(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    assert osinfo.app_dir("data") == tmp_path / "xdg" / "ike-browser"


def test_update_folder_agrees(tmp_path):
    """ike_boot.py (a system part, which cannot import ike/) and the updater
    must use the same folder for updates."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("XDG_")}
    code = ("import sys; sys.path.insert(0, %r); import ike_boot, ike.updater; "
            "print(ike_boot.UPDATES == ike.updater.UPDATES, ike_boot.UPDATES)" % str(ROOT))
    env["QT_QPA_PLATFORM"] = "offscreen"
    res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, cwd=str(tmp_path))
    assert res.stdout.startswith("True"), res.stdout + res.stderr


def test_identity():
    ident = osinfo.identity()
    assert osinfo.chrome_user_agent(140) == (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36")
    assert (ident["platform"], ident["platform_version"]) == ("Linux", "6.0.0")


# ---- Widevine module checks -------------------------------------------------

def pe(machine=0x8664, size=4096):
    """A Windows library: never accepted."""
    data = bytearray(size)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, 0x80)
    data[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<HHIIIHH", data, 0x84, machine, 1, 0, 0, 0, 0xF0, 0x2022)
    return bytes(data)


def elf(machine=62):
    data = bytearray(4096)
    data[:4] = b"\x7fELF"
    data[4], data[5] = 2, 1
    struct.pack_into("<HH", data, 16, 3, machine)
    return bytes(data)


def test_widevine_library_checks():
    drm.check_library(elf())
    for bad in (pe(), elf(machine=183), b"\x7fELF" + b"\0" * 100, b"not a library" * 10):
        with pytest.raises(drm.DrmError):
            drm.check_library(bad)


def test_widevine_archive(tmp_path, monkeypatch):
    """A Linux archive installs; one with another kind of library, or with
    names that try to leave the folder, does not write outside it."""
    monkeypatch.setattr(drm, "OWN_DIR", tmp_path / "WidevineCdm")
    lib, other = elf(), pe()

    def archive(name, data, extra=()):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("manifest.json", json.dumps({"version": "4.10.9999.0", "arch": "x64"}))
            z.writestr(name, data)
            for n, d in extra:
                z.writestr(n, d)
        return buf.getvalue()

    assert drm.install_from_zip(archive("_platform_specific/x/" + drm.LIB_NAME, lib)) == "4.10.9999.0"
    assert (tmp_path / "WidevineCdm" / "_platform_specific" / drm.PLATFORM_DIR / drm.LIB_NAME).is_file()
    with pytest.raises(drm.DrmError):
        drm.install_from_zip(archive(drm.LIB_NAME, other))
    drm.install_from_zip(archive("../../" + drm.LIB_NAME, lib, [("../../evil.txt", b"x")]))
    assert not (tmp_path / "evil.txt").exists() and not (tmp_path.parent / "evil.txt").exists()
    assert sorted(p.name for p in (tmp_path / "WidevineCdm").rglob("*") if p.is_file()) == sorted([
        drm.LIB_NAME, "manifest.json"])


# ---- in the browser -----------------------------------------------------------

def test_look_and_settings(run_ike, tmp_path):
    """The window and Settings. With IKE_TEST_SHOTS=<folder> they are saved
    as pictures, to check them by eye."""
    shots = os.environ.get("IKE_TEST_SHOTS", "")
    out = run_ike("""
        import os
        SHOTS = %r

        def save(widget, name):
            if SHOTS:
                widget.grab().save(os.path.join(SHOTS, "look-%%s.png" %% name))

        def steps(ike, qapp, out):
            win = ike.windows[0]
            win.resize(1000, 700)
            yield 800
            save(win, "window")
            out["title"] = win.windowTitle()
            dlg = ike.show_settings(win)
            yield 400
            for i, name in enumerate(dlg.PAGES):
                dlg.nav.setCurrentRow(i)
                yield 150
                save(dlg, "settings-" + name)
            out["desktop_switches"] = sorted(dlg.di)
            dlg.close()
            yield 200
    """ % shots, settings={"language": "it"})
    assert out["title"]
    assert out["desktop_switches"] == ["di_downloads", "di_kdeconnect", "di_krunner", "di_media"]
