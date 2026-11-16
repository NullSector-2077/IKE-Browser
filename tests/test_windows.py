"""I.K.E. on Windows.

The first part runs on every system: the choices the Windows port makes
(names, commands, texts, the files of the installer) are plain logic that can
be checked anywhere. The second part asks Windows itself and is marked
``windows_only``: it runs in the Windows workflow.
"""

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest
from conftest import APP, ROOT, SANDBOX_OFF, WINDOWS

from ike import app, osinfo, passwords, updater, winapi

WIN = ROOT / "packaging" / "windows"
SID = "S-1-5-21-1004336348-1177238915-682003330-1001"


# ----------------------------------------------------------------------
# on every system
# ----------------------------------------------------------------------
def test_instance_name():
    """The pipe of the single instance: one per user and profile, and never
    a name that could be read as a path."""
    name = winapi.instance_name("ike-browser", SID, "default")
    assert name == "ike-browser-%s-default" % SID
    assert winapi.instance_name("ike-browser", SID, "work") != name
    assert winapi.instance_name("ike-browser", SID.replace("1001", "1002"), "default") != name
    for profile in ("..\\..\\pipe\\other", "a/b", "x\\y", "c:d", "nul\0", "spa ce", "tab\t", "é", "*?<>|\"", "."):
        made = winapi.instance_name("ike-browser", SID, profile)
        assert re.fullmatch(r"[A-Za-z0-9_-]+", made), made
        assert made.startswith("ike-browser-%s-" % SID)
    # nothing left of a name: still a name, and not somebody else's
    assert winapi.instance_name("ike-browser", "", "") == "ike-browser-user-default"
    assert winapi.instance_name("ike-browser", SID, "\\\\") == name
    long = winapi.instance_name("ike-browser", SID, "p" * 5000)
    assert len(long) <= 200 and len("\\\\.\\pipe\\" + long) < 256


def test_instance_address_on_windows(monkeypatch):
    """Windows: one address, the pipe named after the user; whose pipe it is
    is asked after connecting, and "not known" always means "not ours"."""
    monkeypatch.setattr(winapi, "user_sid", lambda: SID, raising=False)
    addresses = app.instance_addresses("win32")
    assert addresses == [("ike-browser-%s-%s" % (SID, app.PROFILE), True)]
    assert "/" not in addresses[0][0] and "\\" not in addresses[0][0] and not addresses[0][0].endswith(".sock")

    class Sock:
        def __init__(self, handle):
            self.handle = handle

        def socketDescriptor(self):
            if isinstance(self.handle, Exception):
                raise self.handle
            return self.handle

    seen = []
    for answer, ours in ((True, True), (False, False), (None, False), ("yes", False), (1, False)):
        monkeypatch.setattr(winapi, "owned_by_user", lambda h, answer=answer: seen.append(h) or answer,
                            raising=False)
        assert app.pipe_is_ours(Sock(1234), "win32") is ours
    assert seen == [1234] * 5
    monkeypatch.setattr(winapi, "owned_by_user", lambda h: True, raising=False)
    for broken in (RuntimeError("gone"), OSError("closed"), "not a number", None):
        assert app.pipe_is_ours(Sock(broken), "win32") is False

    def fails(handle):
        raise OSError("no access")
    monkeypatch.setattr(winapi, "owned_by_user", fails, raising=False)
    assert app.pipe_is_ours(Sock(1234), "win32") is False
    # on Linux the owner was checked before connecting (instance_addresses): nothing more to ask
    assert app.pipe_is_ours(Sock(RuntimeError("not asked")), "linux") is True


def test_launcher_command(monkeypatch, tmp_path):
    """Starting I.K.E. again (restart, another profile, the updater's
    self-test): from the installed launcher it is the launcher alone - it
    runs ike_boot.py itself; with a plain Python it is Python and the script."""
    assert updater.LAUNCHER == "ike-browser.exe"
    assert updater.runs_in_launcher("win32", r"C:\Users\u\AppData\Local\Programs\I.K.E\ike-browser.exe")
    assert updater.runs_in_launcher("win32", r"D:\x\IKE-Browser.EXE")
    assert updater.runs_in_launcher("win32", "C:/x/ike-browser.exe")
    assert not updater.runs_in_launcher("win32", r"C:\Python313\python.exe")
    assert not updater.runs_in_launcher("win32", r"C:\x\ike-browser.exe\python.exe")
    assert not updater.runs_in_launcher("win32", r"C:\x\not-ike-browser.exe")
    assert not updater.runs_in_launcher("win32", "")
    assert not updater.runs_in_launcher("linux", "/usr/bin/ike-browser.exe")
    (tmp_path / "ike_boot.py").write_text("")
    monkeypatch.setenv("IKE_SYSTEM_DIR", str(tmp_path))
    monkeypatch.setattr(updater, "runs_in_launcher", lambda *a: True)
    assert updater.boot_command() == [sys.executable]
    monkeypatch.setattr(updater, "runs_in_launcher", lambda *a: False)
    assert updater.boot_command() == [sys.executable, str(tmp_path / "ike_boot.py")]


def test_staged_update_is_renamed_again_when_windows_holds_it(tmp_path):
    """A virus scanner still reading the new files makes the rename fail for
    a moment on Windows: it is tried again, and gives up with the error."""
    class Folder:
        def __init__(self, failures):
            self.failures, self.calls = failures, 0

        def replace(self, target):
            self.calls += 1
            if self.calls <= self.failures:
                raise PermissionError(13, "Access is denied")
            self.done = target

    final = tmp_path / "1.2.3"
    ok = Folder(3)
    updater._move_into_place(ok, final, tries=10, wait=0)
    assert ok.calls == 4 and ok.done == final
    never = Folder(99)
    with pytest.raises(PermissionError):
        updater._move_into_place(never, final, tries=5, wait=0)
    assert never.calls == 5
    once = Folder(1)
    with pytest.raises(PermissionError):
        updater._move_into_place(once, final, tries=1, wait=0)          # Linux: one try, as before
    other = Folder(0)
    other.replace = lambda target: (_ for _ in ()).throw(FileNotFoundError("gone"))
    with pytest.raises(FileNotFoundError):                               # another error is not waited for
        updater._move_into_place(other, final, tries=5, wait=0)
    # and the real thing
    staging = tmp_path / "1.2.3.staging"
    (staging / "ike").mkdir(parents=True)
    (staging / "ike" / "__init__.py").write_text('__version__ = "1.2.3"\n')
    updater._move_into_place(staging, final)
    assert (final / "ike" / "__init__.py").is_file() and not staging.exists()


def test_notification_text_on_windows():
    """Windows shows a notification's text as it is: no markup to escape, but
    nothing a page wrote may break the lines or exceed what Windows shows."""
    title, text = osinfo.tray_texts("Site", '<a href="https://evil.example/">click</a> & <img src=x>')
    assert (title, text) == ("Site", '<a href="https://evil.example/">click</a> & <img src=x>')
    title, text = osinfo.tray_texts("--icon=C:\\Windows\\x.ico", "-u critical")
    assert (title, text) == ("--icon=C:\\Windows\\x.ico", "-u critical")         # only ever a text
    title, text = osinfo.tray_texts("a\r\nb\0c\x1b[31m", "line 1\nline 2\ttab\x07\u202e")
    assert title == "a b c [31m" and text == "line 1 line 2 tab"
    title, text = osinfo.tray_texts("x" * 5000, "y" * 50000)
    assert len(title) == osinfo.TRAY_TITLE_MAX == 63 and len(text) == osinfo.TRAY_TEXT_MAX == 255
    assert osinfo.tray_texts("", "") == ("I.K.E.", "") and osinfo.tray_texts("  \n ", None) == ("I.K.E.", "None")
    assert osinfo.tray_texts(7, 8.5) == ("7", "8.5")
    # without an application object there is nothing to show it with: no error
    code = ("import sys; sys.path.insert(0, %r); from ike import osinfo; "
            "print(osinfo.notify_tray('t', 'x'))" % str(ROOT))
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                          env=dict(os.environ, QT_QPA_PLATFORM="offscreen"))
    assert done.stdout.strip() == "False", done.stdout + done.stderr


def test_clipboard_marks_for_windows():
    """The three clipboard formats by which Windows keeps a copied password
    out of its clipboard history and its cloud clipboard."""
    names = [name for name, _value in passwords.WINDOWS_CLIPBOARD_HINTS]
    assert names == ["ExcludeClipboardContentFromMonitorProcessing", "CanIncludeInClipboardHistory",
                     "CanUploadToCloudClipboard"]
    assert all(value == b"\0\0\0\0" for _name, value in passwords.WINDOWS_CLIPBOARD_HINTS)     # DWORD 0: "no"
    assert passwords.WINDOWS_MIME % "X" == 'application/x-qt-windows-mime;value="X"'


def test_resources_units():
    """CPU time on Windows comes in 100-nanosecond steps."""
    assert winapi.TICKS_PER_SECOND == 10_000_000
    from ike import resources
    assert resources._TICKS == (winapi.TICKS_PER_SECOND if WINDOWS else os.sysconf("SC_CLK_TCK"))


def test_windows_requirements_are_pinned_with_hashes():
    """Every package of the installer: one exact version, one SHA-256; only
    the libraries I.K.E. is allowed to use, and no D-Bus library."""
    text = (WIN / "requirements.txt").read_text("utf-8")
    lines = [line for line in text.replace("\\\n", " ").splitlines() if line.strip() and not line.startswith("#")]
    found = {}
    for line in lines:
        m = re.fullmatch(r"([A-Za-z0-9_.-]+)==([0-9][0-9A-Za-z.]*)\s+--hash=sha256:([0-9a-f]{64})", line.strip())
        assert m, "not pinned with one hash: " + line
        assert m.group(1) not in found
        found[m.group(1)] = m.group(2)
    assert set(found) == {"PyQt6", "PyQt6-Qt6", "PyQt6-sip", "PyQt6-WebEngine", "PyQt6-WebEngine-Qt6",
                          "cryptography", "cffi", "pycparser"}
    assert "jeepney" not in text.replace("No jeepney", "").lower()
    # PyQt and Qt go together
    assert found["PyQt6"].split(".")[:2] == found["PyQt6-Qt6"].split(".")[:2]
    assert found["PyQt6-WebEngine"].split(".")[:2] == found["PyQt6-WebEngine-Qt6"].split(".")[:2]


def _build():
    import importlib.util
    spec = importlib.util.spec_from_file_location("ike_windows_build", WIN / "build.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_windows_build_script(tmp_path):
    """The build: Python pinned by hash, the codec libraries of Qt Multimedia
    taken out and refused if still there, archives that cannot write outside
    their folder, an engine replacement that can only replace."""
    import zipfile
    build = _build()
    assert re.fullmatch(r"3\.13\.\d+", build.PYTHON_VERSION)
    assert re.fullmatch(r"[0-9a-f]{64}", build.PYTHON_SHA256)
    assert build.PYTHON_URL == ("https://www.python.org/ftp/python/%s/python-%s-embed-amd64.zip"
                                % (build.PYTHON_VERSION, build.PYTHON_VERSION))
    assert build.version() == __import__("ike").__version__
    assert build.pth_text("313") == "python313.zip\n.\nLib\\site-packages\n"      # no "import site", nothing else

    # pruning
    site = tmp_path / "site-packages"
    keep = ["PyQt6/Qt6/bin/Qt6WebEngineCore.dll", "PyQt6/Qt6/bin/Qt6Core.dll", "PyQt6/QtWebEngineCore.pyd",
            "PyQt6/Qt6/resources/qtwebengine_resources.pak", "PyQt6/Qt6/resources/icudtl.dat",
            "PyQt6/Qt6/bin/QtWebEngineProcess.exe", "PyQt6/Qt6/plugins/platforms/qwindows.dll"]
    drop = ["PyQt6/Qt6/bin/avcodec-63.dll", "PyQt6/Qt6/bin/avformat-63.dll", "PyQt6/Qt6/bin/avutil-61.dll",
            "PyQt6/Qt6/bin/swresample-7.dll", "PyQt6/Qt6/bin/swscale-10.dll", "PyQt6/Qt6/bin/Qt6Multimedia.dll",
            "PyQt6/Qt6/bin/Qt6MultimediaWidgets.dll", "PyQt6/Qt6/plugins/multimedia/ffmpegmediaplugin.dll",
            "PyQt6/Qt6/plugins/multimedia/windowsmediaplugin.dll", "PyQt6/QtMultimedia.pyd",
            "PyQt6/Qt6/resources/qtwebengine_resources.debug.pak", "PyQt6/Qt6/resources/v8_context_snapshot.debug.bin"]
    for name in keep + drop:
        (site / name).parent.mkdir(parents=True, exist_ok=True)
        (site / name).write_bytes(b"x")
    removed = build.prune(site)
    assert sorted(removed) == sorted(n.lower() for n in drop)
    assert sorted(p.relative_to(site).as_posix() for p in site.rglob("*") if p.is_file()) == sorted(keep)
    assert not (site / "PyQt6/Qt6/plugins/multimedia").exists()

    # what must never be in the folder that gets installed
    app_dir = tmp_path / "app"
    for name in build.REQUIRED:
        (app_dir / name).parent.mkdir(parents=True, exist_ok=True)
        (app_dir / name).write_bytes(b"x")
    build.check_tree(app_dir)
    for bad in ("python/Lib/site-packages/PyQt6/Qt6/bin/avcodec-63.dll", "python/x/FFmpegMediaPlugin.DLL",
                "python/openh264-2.4.1-win64.dll", "ike/signing.key", "release.pem", "python/widevinecdm.dll"):
        (app_dir / bad).parent.mkdir(parents=True, exist_ok=True)
        (app_dir / bad).write_bytes(b"x")
        with pytest.raises(SystemExit):
            build.check_tree(app_dir)
        (app_dir / bad).unlink()
    (app_dir / "ike_boot.py").unlink()
    with pytest.raises(SystemExit):
        build.check_tree(app_dir)

    # an archive with a name that leaves its folder is not unpacked
    evil = tmp_path / "evil.zip"
    with zipfile.ZipFile(evil, "w") as z:
        z.writestr("python313.dll", b"x")
        z.writestr("../outside.dll", b"x")
    with pytest.raises(SystemExit):
        build.safe_unzip(evil, tmp_path / "unzipped")
    assert not (tmp_path / "outside.dll").exists() and not (tmp_path / "unzipped" / "python313.dll").exists()

    # a wrong Python download is refused and thrown away
    work = tmp_path / "work"
    work.mkdir()
    fake = work / ("python-%s-embed-amd64.zip" % build.PYTHON_VERSION)
    fake.write_bytes(b"not the file python.org published")
    with pytest.raises(SystemExit):
        build.fetch_python(work)
    assert not fake.exists()

    # an engine built elsewhere replaces files of the same name, and adds none
    engine = tmp_path / "engine"
    (engine / "PyQt6/Qt6/bin").mkdir(parents=True)
    (engine / "PyQt6/Qt6/bin/Qt6WebEngineCore.dll").write_bytes(b"own build")
    done = build.replace_engine(site, engine)
    assert [d["file"] for d in done] == ["PyQt6/Qt6/bin/Qt6WebEngineCore.dll"]
    assert (site / "PyQt6/Qt6/bin/Qt6WebEngineCore.dll").read_bytes() == b"own build"
    (engine / "PyQt6/Qt6/bin/extra-codec.dll").write_bytes(b"x")
    with pytest.raises(SystemExit):
        build.replace_engine(site, engine)
    assert not (site / "PyQt6/Qt6/bin/extra-codec.dll").exists()
    with pytest.raises(SystemExit):
        build.replace_engine(site, tmp_path / "empty-engine")


def test_windows_installer_script():
    """The installer: for one user, without administrator rights, nothing
    outside the user's profile and registry branch, an uninstaller that
    leaves the user's data alone."""
    text = (WIN / "ike-browser.iss").read_text("utf-8-sig")
    lines = [line.strip() for line in text.splitlines() if line.strip() and not line.strip().startswith(";")]
    setup = dict(line.split("=", 1) for line in lines if re.match(r"[A-Za-z]+=", line))
    assert setup["PrivilegesRequired"] == "lowest"
    assert "PrivilegesRequiredOverridesAllowed" not in setup          # no way to ask for administrator rights
    assert setup["DefaultDirName"] == r"{localappdata}\Programs\I.K.E"
    assert not setup["DefaultDirName"].endswith(".")                  # Windows drops a final dot
    assert setup["AppMutex"] == winapi.RUNNING_MUTEX
    assert setup["AppId"].lstrip("{").rstrip("}") in (WIN / "check-install.py").read_text("utf-8")
    assert '#define AppUserModelID "%s"' % winapi.APP_USER_MODEL_ID in text
    for line in lines:
        low = line.lower()
        assert "hklm" not in low and "hkcr" not in low and "hku;" not in low, line
        assert "{commonpf" not in low and "{autopf" not in low and "{sys}" not in low and "{win}" not in low, line
        assert "{common" not in low, line                             # no all-users folders
        if low.startswith("root:"):
            assert low.startswith("root: hkcu;"), line
    registry = [line for line in lines if line.lower().startswith("root:")]
    assert registry and all("Tasks: registerbrowser" in line for line in registry)
    assert all("uninsdelete" in line for line in registry if "Subkey: \"Software\\RegisteredApplications\"" in line)
    # the user's data folders are never named: nothing in the installer can delete them
    section = text[text.index("[UninstallDelete]"):]
    assert "{userappdata}" not in text and "{localappdata}\\ike-browser" not in text.lower()
    for line in section.splitlines():
        if line.startswith("Type:"):
            assert 'Name: "{app}' in line, line
    assert "runascurrentuser" not in text.lower() and "runasoriginaluser" not in text.lower()
    assert "--no-sandbox" not in text and "DISABLE_SANDBOX" not in text


def test_windows_launcher_source():
    """The launcher: a windowed program that loads only the Python next to
    it, and passes the arguments on unchanged."""
    src = (WIN / "launcher" / "ike-browser.c").read_text("utf-8")
    assert "wWinMain" in src and 'SetDllDirectoryW(L"")' in src
    assert "LOAD_WITH_ALTERED_SEARCH_PATH" in src and '"Py_Main"' in src
    for forbidden in ("getenv", "_wgetenv", "GetEnvironmentVariable", "RegOpenKey", "system(", "ShellExecute",
                      "CreateProcess", "no-sandbox", "LoadLibraryW(", "LoadLibraryA("):
        assert forbidden not in src, forbidden
    manifest = (WIN / "launcher" / "ike-browser.exe.manifest").read_text("utf-8")
    assert 'level="asInvoker"' in manifest and "requireAdministrator" not in manifest
    assert "{8e0f7a12-bfb3-4fe8-b9a5-48fd50a15a9a}" in manifest           # Windows 10 and 11
    rc = (WIN / "launcher" / "ike-browser.rc.in").read_text("utf-8")
    assert '1 ICON "ike-browser.ico"' in rc and "@VERSION@" in rc and "@VERSION_COMMAS@" in rc


def test_windows_workflow():
    """The Windows workflow can only read the repository, publishes nothing,
    uses no secret and never switches the engine's sandbox off."""
    text = (ROOT / ".github/workflows/windows.yml").read_text("utf-8")
    assert "\npermissions:\n  contents: read\n" in text
    assert text.count("permissions:") == 1
    assert "runs-on: windows-latest" in text
    assert "pull_request:\n    branches: [main]" in text and "workflow_dispatch:" in text
    assert re.search(r"push:\n\s+branches: \[main, windows/port\]", text)
    code = "\n".join(line for line in text.splitlines() if not line.strip().startswith("#"))
    for forbidden in ("secrets.", "gh release", "softprops", "contents: write", "id-token", "pull_request_target",
                      "make-release", "signtool", "--no-sandbox", "QTWEBENGINE_DISABLE_SANDBOX",
                      "IKE_TEST_NO_SANDBOX", "continue-on-error", "|| true", "--deselect", "-k "):
        assert forbidden not in code, forbidden
    assert "name: ike-browser-windows-installer" in text and "retention-days: 30" in text
    assert "--require-hashes" in text and "packaging/windows/requirements.txt" in text
    assert "/VERYSILENT" in text and "/CURRENTUSER" in text and "--uninstalled" in text
    assert text.count("if: always()") >= 2                                 # logs are kept when a step fails
    assert "persist-credentials: false" in text


def test_no_new_library_is_imported():
    """The port adds no Python library: the Windows parts use ctypes and Qt."""
    allowed = {"PyQt6", "cryptography", "jeepney", "ike", "adblock"}
    std = set(sys.stdlib_module_names)
    import ast
    for path in sorted((ROOT / "ike").glob("*.py")) + [ROOT / "ike_boot.py"]:
        for node in ast.walk(ast.parse(path.read_text("utf-8"))):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                names = [node.module]
            else:
                continue
            for name in names:
                top = name.split(".")[0]
                assert top in std or top in allowed, "%s imports %s" % (path.name, name)
    text = (ROOT / "ike" / "winapi.py").read_text("utf-8")
    assert "import ctypes" in text and "subprocess" not in text and "os.system" not in text


# ----------------------------------------------------------------------
# on Windows only
# ----------------------------------------------------------------------
ASKS_WINDOWS = pytest.mark.windows_only("asks Windows itself (ctypes calls into kernel32, advapi32, user32)")


@ASKS_WINDOWS
def test_windows_answers():
    sid = winapi.user_sid()
    assert re.fullmatch(r"S-1-5-[0-9-]+", sid), sid
    assert sid in winapi.own_sids()
    me = os.getpid()
    memory = winapi.process_memory(me)
    assert memory and memory > 5 * 1024 * 1024
    before = winapi.process_cpu_ticks(me)
    end = time.time() + 0.4
    while time.time() < end:
        sum(range(2000))
    after = winapi.process_cpu_ticks(me)
    assert before is not None and after > before
    assert 0.05 < (after - before) / winapi.TICKS_PER_SECOND < 5
    for gone in (0, -1, 4_000_000_000, "x", None):
        assert winapi.process_memory(gone) is None and winapi.process_cpu_ticks(gone) is None
    assert winapi.animations_wanted() in (True, False)
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(1.5)"])
    start = time.time()
    winapi.wait_for_exit(child.pid, 20)
    waited = time.time() - start
    assert child.poll() is not None and 0.5 < waited < 15, waited
    start = time.time()
    winapi.wait_for_exit(child.pid, 20)                   # already gone: at once
    winapi.wait_for_exit(4_000_000_000, 20)
    assert time.time() - start < 2
    # this very process is not waited for longer than asked
    start = time.time()
    winapi.wait_for_exit(me, 0.3)
    assert 0.2 < time.time() - start < 3
    assert osinfo.identity()["platform_version"] in ("10.0.0", "19.0.0")
    assert osinfo.app_dir("data").parent.name == "ike-browser" or os.environ.get("XDG_DATA_HOME")


@ASKS_WINDOWS
def test_a_pipe_of_this_user_is_recognised(tmp_path):
    """owned_by_user on a real named pipe made by this user (through Qt, as
    the browser makes it): ours. A handle that is no pipe of ours: not."""
    code = r'''
import sys
sys.path.insert(0, %r)
from PyQt6.QtCore import QCoreApplication, QTimer
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from ike import app as ikeapp, winapi
qapp = QCoreApplication(sys.argv)
name = winapi.instance_name("ike-test", winapi.user_sid(), "p%%d" %% __import__("os").getpid())
server = QLocalServer()
server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
assert server.listen(name), server.errorString()
sock = QLocalSocket()
sock.connectToServer(name)
assert sock.waitForConnected(3000), sock.errorString()
handle = int(sock.socketDescriptor())
print("OWNER", winapi.owner_of(handle), sorted(winapi.own_sids()))
print("OURS", winapi.owned_by_user(handle), ikeapp.pipe_is_ours(sock))
print("NONE", winapi.owned_by_user(0), winapi.owned_by_user(-1), winapi.owner_of(0) == "")
sock.abort()
server.close()
''' % str(ROOT)
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120,
                          env=dict(os.environ, QT_QPA_PLATFORM="offscreen"))
    assert "OURS True True" in done.stdout, done.stdout + done.stderr
    assert "NONE False False True" in done.stdout, done.stdout + done.stderr


@ASKS_WINDOWS
def test_instance_pipe_on_windows(run_ike):
    """The real thing on Windows: the first start listens on the pipe named
    after the user, a second start hands its address over and ends, rubbish
    written to the pipe is ignored."""
    out = run_ike(r'''
import json, os, subprocess, sys
from ike import app as ikeapp, winapi

def steps(ike, qapp, out):
    yield 600
    (name, _checked), = ikeapp.instance_addresses()
    out["name"] = name
    out["sid"] = winapi.user_sid()
    path = "\\\\.\\pipe\\" + name
    out["listening"] = os.path.exists(path)
    for rubbish in (b"[]", b"\xff\x00garbage", b'{"urls": 7}', b"null", b'{"urls": ["' + b"x" * 30000 + b'"]}'):
        try:
            with open(path, "r+b", buffering=0) as pipe:
                pipe.write(rubbish)
        except OSError as e:
            out.setdefault("write_errors", []).append(str(e))
        yield 200
    win = ike.windows[0]
    out["tabs_before"] = len(win.views)
    env = dict(os.environ)
    env.pop("IKE_TEST_HOOK", None)
    second = subprocess.run(json.loads(os.environ["IKE_SECOND"]) + ["data:text/html,<title>handed over</title>x"],
                            env=env, capture_output=True, timeout=90)
    out["second_exit"] = second.returncode
    out["second_err"] = second.stderr.decode("utf-8", "replace")[-800:]
    yield 2000
    out["tabs_after"] = [v.title() for v in win.views]
''', env={"IKE_NO_SINGLE": "", "IKE_SECOND": json.dumps(_start_command())}, timeout=180)
    assert out["name"] == "ike-browser-%s-default" % out["sid"] and out["sid"].startswith("S-1-5-")
    assert out["listening"], out
    assert out["second_exit"] == 0, out["second_err"]
    assert out["tabs_before"] == 1
    assert out["tabs_after"][-1] == "handed over" and len(out["tabs_after"]) == 2, out


def _start_command():
    if os.environ.get("IKE_TEST_COMMAND"):
        return [os.environ["IKE_TEST_COMMAND"]]
    return [sys.executable, str(APP / "ike_boot.py")]


_SQUATTER = r'''
import ctypes, sys, time
from ctypes import wintypes
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
adv = ctypes.WinDLL("advapi32", use_last_error=True)
name, owner_sid, ready, log = sys.argv[1:5]

def fail(what):
    open(ready, "w").write("FAILED %s (error %d)" % (what, ctypes.get_last_error()))
    sys.exit(0)

# the privilege that lets an administrator name another owner
class LUID(ctypes.Structure):
    _fields_ = [("low", wintypes.DWORD), ("high", wintypes.LONG)]
class TP(ctypes.Structure):
    _fields_ = [("count", wintypes.DWORD), ("luid", LUID), ("attributes", wintypes.DWORD)]
token = wintypes.HANDLE()
k32.GetCurrentProcess.restype = wintypes.HANDLE
adv.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
if not adv.OpenProcessToken(k32.GetCurrentProcess(), 0x0020 | 0x0008, ctypes.byref(token)):
    fail("OpenProcessToken")
for privilege in ("SeRestorePrivilege", "SeTakeOwnershipPrivilege"):
    tp = TP(1, LUID(), 2)
    adv.LookupPrivilegeValueW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.POINTER(LUID)]
    if not adv.LookupPrivilegeValueW(None, privilege, ctypes.byref(tp.luid)):
        fail("LookupPrivilegeValue")
    adv.AdjustTokenPrivileges.argtypes = [wintypes.HANDLE, wintypes.BOOL, ctypes.POINTER(TP), wintypes.DWORD,
                                          ctypes.c_void_p, ctypes.c_void_p]
    ctypes.set_last_error(0)
    if not adv.AdjustTokenPrivileges(token, False, ctypes.byref(tp), 0, None, None) or ctypes.get_last_error():
        fail("no " + privilege)

k32.CreateNamedPipeW.restype = wintypes.HANDLE
k32.CreateNamedPipeW.argtypes = [wintypes.LPCWSTR] + [wintypes.DWORD] * 6 + [ctypes.c_void_p]
PIPE_ACCESS_DUPLEX, WRITE_OWNER, WRITE_DAC = 3, 0x00080000, 0x00040000
pipe = k32.CreateNamedPipeW("\\\\.\\pipe\\" + name, PIPE_ACCESS_DUPLEX | WRITE_OWNER | WRITE_DAC, 0, 4, 65536, 65536,
                            0, None)
if not pipe or pipe == wintypes.HANDLE(-1).value:
    fail("CreateNamedPipe")
sid = ctypes.c_void_p()
adv.ConvertStringSidToSidW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p)]
if not adv.ConvertStringSidToSidW(owner_sid, ctypes.byref(sid)):
    fail("ConvertStringSidToSid")
adv.SetSecurityInfo.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.DWORD, ctypes.c_void_p, ctypes.c_void_p,
                                ctypes.c_void_p, ctypes.c_void_p]
adv.SetSecurityInfo.restype = wintypes.DWORD
# owner: somebody else; access: everybody (a null list), so the visitor can connect
error = adv.SetSecurityInfo(pipe, 6, 0x1 | 0x4, sid, None, None, None)
if error:
    ctypes.set_last_error(error)
    fail("SetSecurityInfo")
open(ready, "w").write("READY")

k32.ConnectNamedPipe.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
k32.PeekNamedPipe.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p,
                              ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
k32.DisconnectNamedPipe.argtypes = [wintypes.HANDLE]
k32.ReadFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
                         ctypes.c_void_p]
visits, received = 0, b""
end = time.time() + float(sys.argv[5])
import threading
def serve():
    global visits, received
    while True:
        k32.ConnectNamedPipe(pipe, None)             # waits for a visitor
        visits += 1
        for _ in range(30):                          # give it three seconds to say something
            waiting = wintypes.DWORD(0)
            if not k32.PeekNamedPipe(pipe, None, 0, None, ctypes.byref(waiting), None):
                break
            if waiting.value:
                buf = ctypes.create_string_buffer(waiting.value)
                got = wintypes.DWORD(0)
                k32.ReadFile(pipe, buf, waiting.value, ctypes.byref(got), None)
                received += buf.raw[:got.value]
            time.sleep(0.1)
        k32.DisconnectNamedPipe(pipe)
        open(log, "w").write(repr((visits, received)))
threading.Thread(target=serve, daemon=True).start()
while time.time() < end:
    time.sleep(0.2)
    open(log, "w").write(repr((visits, received)))
'''


@ASKS_WINDOWS
def test_a_pipe_of_somebody_else_is_told_nothing(run_ike, tmp_path):
    """Attack: another account creates, before I.K.E. starts, the pipe a
    second start of this user would look for. I.K.E. connects, sees that the
    pipe belongs to somebody else, sends nothing and starts as the first
    instance instead. (The stand-in is made by this user with the owner set
    to the system account, which only an administrator can do: the test is
    skipped, and says so, where the runner is no administrator.)"""
    sid = winapi.user_sid()
    name = winapi.instance_name("ike-browser", sid, "default")
    ready, log = tmp_path / "ready.txt", tmp_path / "squatter.log"
    script = tmp_path / "squatter.py"
    script.write_text(_SQUATTER, "utf-8")
    squatter = subprocess.Popen([sys.executable, str(script), name, "S-1-5-18", str(ready), str(log), "150"])
    try:
        for _ in range(100):
            if ready.exists() and ready.read_text():
                break
            time.sleep(0.1)
        state = ready.read_text() if ready.exists() else "FAILED to start"
        if state != "READY":
            pytest.skip("cannot stand in for another account on this computer: " + state)
        secret = "https://private.example/?token=SECRET-ADDRESS"
        out = run_ike(r'''
from ike import app as ikeapp
def steps(ike, qapp, out):
    yield 1500
    out["tabs"] = [v.url().toString() for v in ike.windows[0].views]
    out["sandbox_off"] = ikeapp.sandbox_off()
''', env={"IKE_NO_SINGLE": ""}, args=[secret], timeout=120)
        # it did not hand the address over: it opened it itself
        assert any("SECRET-ADDRESS" in t for t in out["tabs"]), out
        time.sleep(4)
        visits, received = eval(log.read_text(), {"__builtins__": {}})
        assert visits >= 1, "the stand-in was never visited: the test proved nothing"
        assert received == b"", received
    finally:
        squatter.kill()
        squatter.wait()


@ASKS_WINDOWS
def test_the_sandbox_is_on(run_ike):
    """Windows: I.K.E. never switches the engine's sandbox off, and the
    process that runs a page really is confined: Windows gives it a lower
    integrity level than the browser's own."""
    if SANDBOX_OFF:
        pytest.skip("this run switched the sandbox off (IKE_TEST_NO_SANDBOX=1)")
    out = run_ike(r'''
import ctypes, os
from ctypes import wintypes
from PyQt6.QtCore import QUrl
from ike import app as ikeapp

def integrity(pid):
    """The integrity level of a process (0x1000 low, 0x2000 medium, 0x3000 high; 0 untrusted)."""
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    adv = ctypes.WinDLL("advapi32", use_last_error=True)
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    process = k32.OpenProcess(0x1000, False, pid)
    if not process:
        return "OpenProcess failed: %d" % ctypes.get_last_error()
    token = wintypes.HANDLE()
    adv.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
    if not adv.OpenProcessToken(process, 0x0008, ctypes.byref(token)):
        return "OpenProcessToken failed: %d" % ctypes.get_last_error()
    size = wintypes.DWORD(0)
    adv.GetTokenInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
                                        ctypes.POINTER(wintypes.DWORD)]
    adv.GetTokenInformation(token, 25, None, 0, ctypes.byref(size))
    buf = ctypes.create_string_buffer(size.value)
    if not adv.GetTokenInformation(token, 25, buf, size, ctypes.byref(size)):
        return "GetTokenInformation failed: %d" % ctypes.get_last_error()
    sid = ctypes.cast(buf, ctypes.POINTER(ctypes.c_void_p))[0]
    adv.GetSidSubAuthorityCount.restype = ctypes.POINTER(ctypes.c_ubyte)
    adv.GetSidSubAuthorityCount.argtypes = [ctypes.c_void_p]
    adv.GetSidSubAuthority.restype = ctypes.POINTER(wintypes.DWORD)
    adv.GetSidSubAuthority.argtypes = [ctypes.c_void_p, wintypes.DWORD]
    count = adv.GetSidSubAuthorityCount(sid)[0]
    return int(adv.GetSidSubAuthority(sid, count - 1)[0])

def steps(ike, qapp, out):
    view = ike.windows[0].current_view()
    view.load(QUrl("data:text/html,<title>sandboxed</title>page"))
    for _ in range(100):
        yield 100
        if view.title() == "sandboxed":
            break
    out["title"] = view.title()
    out["sandbox_off"] = ikeapp.sandbox_off()
    out["flags"] = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
    out["disable"] = os.environ.get("QTWEBENGINE_DISABLE_SANDBOX", "")
    pid = int(view.page().renderProcessPid())
    out["renderer"] = pid
    out["own"] = integrity(os.getpid())
    out["page"] = integrity(pid)
''', timeout=120)
    assert out["title"] == "sandboxed"
    assert out["sandbox_off"] is False and "--no-sandbox" not in out["flags"] and out["disable"] in ("", "0")
    assert out["renderer"] > 0
    assert isinstance(out["own"], int) and out["own"] >= 0x2000, out
    if not isinstance(out["page"], int):
        pytest.skip("Windows did not show the page process's integrity level (%s); the switches say the "
                    "sandbox is on" % out["page"])
    assert out["page"] < out["own"] and out["page"] < 0x2000, out


@ASKS_WINDOWS
def test_notification_and_clipboard_in_the_browser(run_ike):
    """In the real browser on Windows: a notification is shown through Qt (or
    there is no notification area - never an error), and a copied password
    carries Windows' marks against the clipboard history."""
    out = run_ike(r'''
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QSystemTrayIcon
from ike import osinfo, passwords

def steps(ike, qapp, out):
    yield 400
    out["tray"] = bool(QSystemTrayIcon.isSystemTrayAvailable() and QSystemTrayIcon.supportsMessages())
    out["shown"] = osinfo.notify("I.K.E.", "<b>test</b> & more")
    yield 300
    out["again"] = osinfo.notify("x" * 500, "y\n" * 5000)
    ike._desktop_notify("update notice")
    yield 300
    passwords.copy_secret("hunter2-secret")
    yield 200
    data = QGuiApplication.clipboard().mimeData()
    out["text"] = data.text()
    out["marks"] = [bool(data.hasFormat(passwords.WINDOWS_MIME % name))
                    for name, _v in passwords.WINDOWS_CLIPBOARD_HINTS]
    out["values"] = [bytes(data.data(passwords.WINDOWS_MIME % name)).hex()
                     for name, _v in passwords.WINDOWS_CLIPBOARD_HINTS]
''', timeout=120)
    assert out["shown"] == out["tray"] and out["again"] == out["tray"], out
    assert out["text"] == "hunter2-secret"
    assert out["marks"] == [True, True, True], out
    assert out["values"] == ["00000000"] * 3, out


@ASKS_WINDOWS
def test_windows_folders_in_the_browser(tmp_path):
    """Without the XDG variables the real browser keeps its settings under
    %APPDATA% and everything else under %LOCALAPPDATA% - and nothing in the
    user's home folder itself."""
    home = tmp_path / "home"
    roaming, local = home / "AppData" / "Roaming", home / "AppData" / "Local"
    for folder in (roaming, local):
        folder.mkdir(parents=True)
    from conftest import HARNESS, QUIET_SETTINGS, engine_flags
    (roaming / "ike-browser").mkdir()
    (roaming / "ike-browser" / "settings.json").write_text(json.dumps(QUIET_SETTINGS), "utf-8")
    script = tmp_path / "steps.py"
    script.write_text('''
from ike import config, updater
def steps(ike, qapp, out):
    yield 1500
    out["config"], out["data"], out["cache"] = str(config.CONFIG_DIR), str(config.DATA_DIR), str(config.CACHE_DIR)
    out["updates"] = str(updater.UPDATES)
    out["settings"] = str(ike.config.path)
    ike.config.save()
''', "utf-8")
    result = tmp_path / "out.json"
    env = {k: v for k, v in os.environ.items() if not k.startswith(("XDG_", "IKE_", "QTWEBENGINE_"))}
    env.update(USERPROFILE=str(home), APPDATA=str(roaming), LOCALAPPDATA=str(local), QT_QPA_PLATFORM="offscreen",
               QTWEBENGINE_CHROMIUM_FLAGS=engine_flags(), IKE_NO_SINGLE="1", IKE_TEST_NOASK="1",
               IKE_TEST_HOOK=str(HARNESS), IKE_TEST_SCRIPT=str(script), IKE_TEST_OUT=str(result), PYTHONUTF8="1")
    if SANDBOX_OFF:
        env["QTWEBENGINE_DISABLE_SANDBOX"] = "1"
    done = subprocess.run(_start_command(), env=env, capture_output=True, text=True, timeout=120, cwd=str(tmp_path))
    assert result.exists(), done.stderr[-3000:]
    out = json.loads(result.read_text("utf-8"))
    assert "error" not in out, out.get("error")
    assert Path(out["config"]) == roaming / "ike-browser"
    assert Path(out["data"]) == local / "ike-browser" / "data"
    assert Path(out["cache"]) == local / "ike-browser" / "cache"
    assert Path(out["updates"]) == local / "ike-browser" / "data" / "updates"
    assert Path(out["settings"]) == roaming / "ike-browser" / "settings.json"
    assert (local / "ike-browser" / "data" / "profile").is_dir()            # the engine's profile
    assert (local / "ike-browser" / "data" / "ike.sqlite").is_file()
    assert sorted(p.name for p in home.iterdir()) == ["AppData"]            # nothing else in the home folder
    assert sorted(p.name for p in roaming.iterdir()) == ["ike-browser"]
