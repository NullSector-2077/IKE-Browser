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
    monkeypatch.setattr(osinfo, "WINDOWS", False)          # the folders of Linux, wherever the test runs
    home = Path.home()
    assert osinfo.app_dir("config") == home / ".config" / "ike-browser"
    assert osinfo.app_dir("data") == home / ".local/share" / "ike-browser"
    assert osinfo.app_dir("cache") == home / ".cache" / "ike-browser"


def test_folders_follow_xdg(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    assert osinfo.app_dir("data") == tmp_path / "xdg" / "ike-browser"
    monkeypatch.setattr(osinfo, "WINDOWS", True)           # the variables win on Windows too
    assert osinfo.app_dir("data") == tmp_path / "xdg" / "ike-browser"


def test_folders_on_windows(monkeypatch, tmp_path):
    """Windows: settings under %APPDATA%, data and cache under %LOCALAPPDATA%,
    each kind in a folder of its own; without the variables, or with values
    that are not full paths, the usual folders of the user's profile."""
    for v in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setattr(osinfo, "WINDOWS", True)
    roaming, local = tmp_path / "Roaming", tmp_path / "Local"
    monkeypatch.setenv("APPDATA", str(roaming))
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    dirs = {kind: osinfo.app_dir(kind) for kind in ("config", "data", "cache")}
    assert dirs == {"config": roaming / "ike-browser", "data": local / "ike-browser" / "data",
                    "cache": local / "ike-browser" / "cache"}
    # no folder inside another one: clearing the cache can never touch the data
    for a in dirs.values():
        for b in dirs.values():
            assert a == b or a not in b.parents
    home = tmp_path / "home"
    for bad in ({}, {"APPDATA": "", "LOCALAPPDATA": ""}, {"APPDATA": "relative", "LOCALAPPDATA": "..\\up"}):
        assert osinfo.windows_dir("config", bad, home) == home / "AppData/Roaming" / "ike-browser"
        assert osinfo.windows_dir("data", bad, home) == home / "AppData/Local" / "ike-browser" / "data"
        assert osinfo.windows_dir("cache", bad, home) == home / "AppData/Local" / "ike-browser" / "cache"
    # a Windows path is taken as it is, wherever this test runs
    assert str(osinfo.windows_dir("config", {"APPDATA": "C:\\Users\\u\\AppData\\Roaming"}, home)).startswith(
        "C:\\Users\\u\\AppData\\Roaming")
    # extra profiles get their own sub-tree there too
    code = ("import os, sys; sys.path.insert(0, %r); from ike import osinfo; osinfo.WINDOWS = True; "
            "from ike import config; print(config.CONFIG_DIR); print(config.DATA_DIR); print(config.CACHE_DIR)"
            % str(ROOT))
    env = {k: v for k, v in os.environ.items() if not k.startswith("XDG_")}
    env.update(APPDATA=str(roaming), LOCALAPPDATA=str(local), IKE_PROFILE="work")
    res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, cwd=str(tmp_path))
    assert res.stdout.split() == [str(roaming / "ike-browser" / "profiles" / "work"),
                                  str(local / "ike-browser" / "data" / "profiles" / "work"),
                                  str(local / "ike-browser" / "cache" / "profiles" / "work")], res.stdout + res.stderr


def test_update_folder_agrees(tmp_path):
    """ike_boot.py (a system part, which cannot import ike/) and the updater
    must use the same folder for updates."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("XDG_")}
    code = ("import sys; sys.path.insert(0, %r); import ike_boot, ike.updater; "
            "print(ike_boot.UPDATES == ike.updater.UPDATES, ike_boot.UPDATES)" % str(ROOT))
    env["QT_QPA_PLATFORM"] = "offscreen"
    res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, cwd=str(tmp_path))
    assert res.stdout.startswith("True"), res.stdout + res.stderr


@pytest.mark.parametrize("variables", [
    {"LOCALAPPDATA": "{tmp}/Local"}, {"LOCALAPPDATA": ""}, {"LOCALAPPDATA": "relative"},
    {"LOCALAPPDATA": "{tmp}/Local", "XDG_DATA_HOME": "{tmp}/xdg"}])
def test_update_folder_agrees_on_windows(tmp_path, variables):
    """The same on Windows (the system is only named: the two files are
    plain path arithmetic), with and without the variables."""
    env = {k: v for k, v in os.environ.items()
           if not k.startswith("XDG_") and k not in ("APPDATA", "LOCALAPPDATA")}
    env.update({k: v.replace("{tmp}", str(tmp_path)) for k, v in variables.items()})
    code = ("import sys; sys.path.insert(0, %r); import ike_boot; "
            "from ike import osinfo; osinfo.WINDOWS = True; sys.platform = 'win32'; "
            "print(ike_boot.data_dir() == osinfo.app_dir('data'), ike_boot.data_dir(), osinfo.app_dir('data'))"
            % str(ROOT))
    res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, cwd=str(tmp_path))
    assert res.stdout.startswith("True"), res.stdout + res.stderr
    assert "ike-browser" in res.stdout


def test_identity():
    linux = osinfo.identity("linux")
    assert (linux["platform"], linux["platform_version"]) == ("Linux", "6.0.0")
    assert (linux["os"], linux["ua_os"], linux["navigator_platform"], linux["chrome_versions"]) == (
        "linux", "X11; Linux x86_64", "Linux x86_64", "linux")
    here = osinfo.identity()
    assert here == (osinfo.identity("win32") if sys.platform == "win32" else linux)
    assert osinfo.chrome_user_agent(140) == (
        "Mozilla/5.0 (%s) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36" % here["ua_os"])
    if sys.platform != "win32":
        assert osinfo.chrome_user_agent(140) == (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/140.0.0.0 Safari/537.36")


def test_identity_on_windows(monkeypatch):
    """Windows: Chrome on Windows in every value a site can read, none of them
    naming Linux; Windows 10 and Windows 11 differ only where Chrome's do."""
    eleven = osinfo.identity("win32", windows_build=26100)
    assert eleven == {
        "os": "windows", "ua_os": "Windows NT 10.0; Win64; x64", "platform": "Windows",
        "platform_version": "19.0.0", "navigator_platform": "Win32",
        "firefox_ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:140.0) Gecko/20100101 Firefox/140.0",
        "firefox_app_version": "5.0 (Windows)", "firefox_oscpu": "Windows NT 10.0; Win64; x64",
        "chrome_versions": "win64"}
    ten = osinfo.identity("win32", windows_build=19045)
    assert ten["platform_version"] == "10.0.0"
    assert {k: v for k, v in ten.items() if k != "platform_version"} == {
        k: v for k, v in eleven.items() if k != "platform_version"}
    assert osinfo.identity("win32", windows_build=22000)["platform_version"] == "19.0.0"
    assert osinfo.identity("win32", windows_build=21999)["platform_version"] == "10.0.0"
    for ident in (ten, eleven):
        assert set(ident) == set(osinfo.identity("linux"))            # the same keys as on Linux
        assert not any("linux" in str(v).lower() or "x11" in str(v).lower() for v in ident.values())
    # the two systems share nothing a site could tell them apart by, except the names themselves
    assert osinfo.identity("linux") != eleven
    # the user agent, and the list Chrome's version is taken from
    monkeypatch.setattr(osinfo, "identity", lambda *a, **k: eleven)
    assert osinfo.chrome_user_agent(157) == (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/157.0.0.0 Safari/537.36")
    code = ("import sys; sys.path.insert(0, %r); from ike import osinfo; real = osinfo.identity; "
            "osinfo.identity = lambda *a, **k: real('win32', 26100); "
            "from ike import chromever; print(chromever.URL)" % str(ROOT))
    res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         env=dict(os.environ, QT_QPA_PLATFORM="offscreen"))
    assert res.stdout.strip() == ("https://versionhistory.googleapis.com/v1/chrome/platforms/win64/"
                                  "channels/stable/versions"), res.stdout + res.stderr


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


def pe_dll(machine=0x8664, flags=0x2022, magic=0x20B, sections=2, optional=240, pe_at=0x80,
           raw=((0x400, 0x200), (0x600, 0x200)), size=0x800):
    """A 64-bit Windows DLL as far as its headers go: two sections that end
    exactly where the file ends, so that any cut makes it incomplete."""
    data = bytearray(size)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, pe_at)
    if pe_at + 24 + 2 <= size:
        data[pe_at:pe_at + 4] = b"PE\0\0"
        struct.pack_into("<HHIIIHH", data, pe_at + 4, machine, sections, 0, 0, 0, optional, flags)
        struct.pack_into("<H", data, pe_at + 24, magic)
        table = pe_at + 24 + optional
        for i, (at, length) in enumerate(raw):
            if table + 40 * (i + 1) <= size:
                data[table + 40 * i:table + 40 * i + 8] = (b".text\0\0\0", b".rdata\0\0")[i % 2]
                struct.pack_into("<II", data, table + 40 * i + 16, length, at)
    return bytes(data)


def _linux(monkeypatch):
    """The module of Linux, wherever the test runs."""
    monkeypatch.setattr(drm, "WINDOWS", False)
    monkeypatch.setattr(drm, "LIB_NAME", "libwidevinecdm.so")
    monkeypatch.setattr(drm, "PLATFORM_DIR", "linux_x64")
    monkeypatch.setattr(drm, "EXTRA_FILES", ())


def _windows(monkeypatch):
    monkeypatch.setattr(drm, "WINDOWS", True)
    monkeypatch.setattr(drm, "LIB_NAME", "widevinecdm.dll")
    monkeypatch.setattr(drm, "PLATFORM_DIR", "win_x64")
    monkeypatch.setattr(drm, "EXTRA_FILES", ("widevinecdm.dll.sig",))


def test_widevine_library_checks(monkeypatch):
    _linux(monkeypatch)
    drm.check_library(elf())
    for bad in (pe(), pe_dll(), elf(machine=183), b"\x7fELF" + b"\0" * 100, b"not a library" * 10):
        with pytest.raises(drm.DrmError):
            drm.check_library(bad)
        with pytest.raises(drm.DrmError):
            drm.check_library(bad, windows=False)


def test_widevine_library_checks_on_windows(monkeypatch):
    """Windows: only a whole 64-bit x86-64 DLL. Another machine, a program
    that is not a library, a 32-bit file, a Linux library, headers that point
    outside the file and files cut at any length are refused - always with
    the module's own error, whatever the bytes are."""
    _windows(monkeypatch)
    good = pe_dll()
    drm.check_library(good)
    drm.check_pe(good)
    drm.check_library(good + b"\0" * 4096, windows=True)        # data after the last section (a signature) is fine
    bad = {
        "linux library": elf(),
        "headers only, without what they describe": pe(),
        "32-bit x86": pe_dll(machine=0x14C),
        "ARM64": pe_dll(machine=0xAA64),
        "a program, not a library": pe_dll(flags=0x0022),
        "not executable": pe_dll(flags=0x2000),
        "32-bit optional header": pe_dll(magic=0x10B),
        "ROM image": pe_dll(magic=0x107),
        "no sections": pe_dll(sections=0, raw=()),
        "65535 sections": pe_dll(sections=0xFFFF),
        "97 sections": pe_dll(sections=97),
        "optional header shorter than the format allows": pe_dll(optional=16),
        "optional header longer than the file": pe_dll(optional=0xFFFF),
        "header offset far outside the file": pe_dll(pe_at=0xFFFFFFF0),
        "header offset at the very end": pe_dll(pe_at=0x800 - 8),
        "header offset inside the DOS header": pe_dll(pe_at=4),
        "header offset zero": pe_dll(pe_at=0),
        "section after the end of the file": pe_dll(raw=((0x400, 0x200), (0x600, 0x201))),
        "section starting outside the file": pe_dll(raw=((0x400, 0x200), (0x10000, 0x200))),
        "section whose size overflows 32 bits": pe_dll(raw=((0x400, 0x200), (0x600, 0xFFFFFFFF))),
        "section whose offset overflows 32 bits": pe_dll(raw=((0x400, 0x200), (0xFFFFFFFF, 0x200))),
        "section lying over the headers": pe_dll(raw=((0x400, 0x200), (0x10, 0x200))),
        "no DOS signature": b"ZM" + good[2:],
        "no PE signature": good[:0x80] + b"PE\0\1" + good[0x84:],
        "text": b"MZ this is not a program at all" * 40,
        "only the signature": b"MZ",
        "empty": b"",
    }
    for what, data in bad.items():
        with pytest.raises(drm.DrmError):
            drm.check_library(data)
            pytest.fail("accepted: " + what)
    # cut at every length: a download that stopped half-way is never kept
    for cut in range(len(good)):
        with pytest.raises(drm.DrmError):
            drm.check_pe(good[:cut])
            pytest.fail("accepted when cut to %d bytes" % cut)
    # changed bytes: accepted or refused, but never another kind of error
    import random
    rnd = random.Random(1234)
    accepted = 0
    for _ in range(4000):
        data = bytearray(good)
        for _n in range(rnd.randint(1, 6)):
            data[rnd.randrange(0x200)] = rnd.randrange(256)
        if rnd.random() < 0.2:
            struct.pack_into("<I", data, 0x3C, rnd.choice((0, 0x3C, 0x40, 0x7E0, 0x7FF, 0x800, 0xFFFF, 0xFFFFFFFF)))
        try:
            drm.check_pe(bytes(data))
            accepted += 1
        except drm.DrmError:
            pass
    assert 0 < accepted < 4000
    # too large
    monkeypatch.setattr(drm, "MAX_LIB", len(good) - 1)
    with pytest.raises(drm.DrmError):
        drm.check_pe(good)
    # and on Linux a Windows library stays what it was: not accepted
    with pytest.raises(drm.DrmError):
        drm.check_library(good, windows=False)


def _archive(name, data, extra=()):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("manifest.json", json.dumps({"version": "4.10.9999.0", "arch": "x64"}))
        z.writestr(name, data)
        for n, d in extra:
            z.writestr(n, d)
    return buf.getvalue()


def test_widevine_archive(tmp_path, monkeypatch):
    """A Linux archive installs; one with another kind of library, or with
    names that try to leave the folder, does not write outside it."""
    _linux(monkeypatch)
    monkeypatch.setattr(drm, "OWN_DIR", tmp_path / "WidevineCdm")
    lib, other = elf(), pe()
    archive = _archive

    assert drm.install_from_zip(archive("_platform_specific/x/" + drm.LIB_NAME, lib)) == "4.10.9999.0"
    assert (tmp_path / "WidevineCdm" / "_platform_specific" / drm.PLATFORM_DIR / drm.LIB_NAME).is_file()
    with pytest.raises(drm.DrmError):
        drm.install_from_zip(archive(drm.LIB_NAME, other))
    drm.install_from_zip(archive("../../" + drm.LIB_NAME, lib, [("../../evil.txt", b"x")]))
    assert not (tmp_path / "evil.txt").exists() and not (tmp_path.parent / "evil.txt").exists()
    assert sorted(p.name for p in (tmp_path / "WidevineCdm").rglob("*") if p.is_file()) == sorted([
        drm.LIB_NAME, "manifest.json"])


def test_widevine_archive_on_windows(tmp_path, monkeypatch):
    """Windows: Google's archive for Windows installs (the DLL and its
    signature file); a Linux library under the DLL's name, a damaged DLL and
    names that try to leave the folder do not get in, and what was installed
    before stays in place."""
    _windows(monkeypatch)
    own = tmp_path / "WidevineCdm"
    monkeypatch.setattr(drm, "OWN_DIR", own)
    dll = pe_dll()
    assert drm.install_from_zip(_archive("widevinecdm.dll", dll, [
        ("widevinecdm.dll.sig", b"signature"), ("widevinecdm.dll.lib", b"not wanted"),
        ("LICENSE.txt", b"licence"), ("..\\..\\evil.dll", dll), ("../../evil.txt", b"x"),
        ("C:/Windows/evil.dll", dll)])) == "4.10.9999.0"
    folder = own / "_platform_specific" / "win_x64"
    assert (folder / "widevinecdm.dll").read_bytes() == dll
    assert (folder / "widevinecdm.dll.sig").read_bytes() == b"signature"
    assert sorted(p.name for p in own.rglob("*") if p.is_file()) == [
        "LICENSE.txt", "manifest.json", "widevinecdm.dll", "widevinecdm.dll.sig"]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["WidevineCdm"]
    assert not (tmp_path.parent / "evil.txt").exists() and not (tmp_path.parent / "evil.dll").exists()
    for what, data in (("a Linux library", elf()), ("cut", dll[:-1]), ("32-bit", pe_dll(machine=0x14C)),
                       ("a program", pe_dll(flags=0x0022)), ("text", b"MZ" + b"x" * 500)):
        with pytest.raises(drm.DrmError):
            drm.install_from_zip(_archive("widevinecdm.dll", data))
            pytest.fail("installed: " + what)
        assert (folder / "widevinecdm.dll").read_bytes() == dll          # the copy in use is untouched
        assert sorted(p.name for p in tmp_path.iterdir()) == ["WidevineCdm"]
    with pytest.raises(drm.DrmError):                                    # the Linux module's name is not looked for
        drm.install_from_zip(_archive("libwidevinecdm.so", elf()))


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
