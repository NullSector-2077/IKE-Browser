"""Files, folders and links handed to the desktop without xdg-utils (1.1.24, ike/handoff.py).

- No code path starts xdg-open or xdg-settings any more (the code, the inventory, the
  package, and a run with stand-ins of those programs on the PATH).
- The desktop portal (org.freedesktop.portal.OpenURI) gets a file descriptor of the very
  file (OpenFile), shows a file in its folder (OpenDirectory) and takes links (OpenURI),
  on a private test bus with a stand-in portal (tests/portal_standin.py); with no portal,
  the desktop's own opener when it is installed (kioclient, gio, exo-open), else a message.
- The default browser is written in mimeapps.list as the XDG specification says,
  atomically, every other entry kept.
- The handoffs of the menus and of the downloads window ("Open with Okular", "Open image
  in Gwenview", "Show in folder", Ark, "Add to calendar", the page's code in Kate) are
  shown only when the desktop has an app for that type, and hand over only a file of
  that type.

Offline: local servers, a private bus, stand-in programs and apps.
"""

import ast
import http.server
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from conftest import APP, ROOT

sys.path.insert(0, str(APP))
from ike import handoff  # noqa: E402

XDG_UTILS = ("xdg-open", "xdg-settings", "xdg-mime", "xdg-email", "xdg-desktop-menu", "xdg-icon-resource",
             "xdg-screensaver", "xdg-desktop-icon")


# --- no xdg-utils anywhere ------------------------------------------------------------------------

def _code_files():
    return sorted((ROOT / "ike").glob("*.py")) + [ROOT / "ike_boot.py"]


def test_no_code_path_starts_xdg_open_or_xdg_settings():
    """Neither a program of xdg-utils nor Qt's QDesktopServices (which starts xdg-open)
    is used by I.K.E.'s code; the inventory, which reads the programs from the code,
    finds none, and the package and the Arch check no longer have xdg-utils."""
    for f in _code_files():
        tree = ast.parse(f.read_text("utf-8"))
        docs = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)) and \
                    node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant):
                docs.add(id(node.body[0].value))
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                assert node.id != "QDesktopServices", "%s:%d" % (f.name, node.lineno)
            if isinstance(node, ast.alias):
                assert node.name != "QDesktopServices", f.name
            if isinstance(node, ast.Attribute):
                assert node.attr != "QDesktopServices", "%s:%d" % (f.name, node.lineno)
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs:
                for prog in XDG_UTILS:
                    assert not node.value.strip().startswith(prog), "%s:%d %r" % (f.name, node.lineno, node.value)
    sys.path.insert(0, str(ROOT / "tools"))
    import importlib.util
    spec = importlib.util.spec_from_file_location("inventory_handoff", ROOT / "tools" / "inventory.py")
    inv_tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(inv_tool)
    inv = inv_tool.inventory(ROOT, offline=True)
    ids = {r["id"] for r in inv["components"]}
    assert not [i for i in ids if "xdg-utils" in i or any(i.endswith(":" + p) for p in XDG_UTILS)], ids
    assert "xdg-utils" not in (ROOT / "PKGBUILD").read_text("utf-8")
    assert "xdg-utils" not in (ROOT / ".github" / "workflows" / "arch.yml").read_text("utf-8")


def _stand_ins(folder, names):
    """Programs on a PATH of their own that only write down how they were started."""
    folder.mkdir(parents=True, exist_ok=True)
    log = folder / "started.log"
    for name in names:
        p = folder / name
        p.write_text("#!/bin/sh\nprintf '%%s\\n' \"%s $*\" >> '%s'\n" % (name, log))
        p.chmod(0o755)
    return log


def _lines(log, want=1, seconds=5):
    end = time.time() + seconds
    while time.time() < end:
        if log.exists() and len(log.read_text().splitlines()) >= want:
            break
        time.sleep(0.05)
    return log.read_text().splitlines() if log.exists() else []


@pytest.mark.parametrize("desktop,first", [("KDE", "kioclient exec"), ("GNOME", "gio open"),
                                           ("XFCE", "exo-open"), ("", "gio open")])
def test_without_a_portal_the_desktops_own_opener_never_xdg_open(tmp_path, desktop, first):
    """No portal on the bus: the desktop's own opener, its own first; xdg-open never,
    even when it is the only program there; with no opener at all, a message."""
    bin_dir = tmp_path / "bin"
    log = _stand_ins(bin_dir, XDG_UTILS + ("kioclient", "gio", "exo-open"))
    env = {"PATH": str(bin_dir), "XDG_CURRENT_DESKTOP": desktop, "HOME": str(tmp_path)}
    target = tmp_path / "file.txt"
    target.write_text("x")
    told = []
    h = handoff.Handoff(bus_factory=lambda: None, opener=lambda t: handoff.start_opener(t, env))
    h.nothing = lambda target, parent=None: told.append(str(target))
    h.open_file(target)
    assert _lines(log) == ["%s %s" % (first, target)], _lines(log)
    assert told == []
    # only xdg-utils' programs on the PATH: nothing is started, the user is told
    for name in ("kioclient", "gio", "exo-open"):
        (bin_dir / name).unlink()
    log.unlink()
    h.open_file(target)
    h.open_uri("magnet:?xt=urn:btih:abc")
    time.sleep(0.3)
    assert not log.exists(), log.read_text()
    assert told == [str(target), "magnet:?xt=urn:btih:abc"]
    # an option is never passed as the target
    assert handoff.start_opener("--help", env) == ""


def test_the_default_browser_is_set_without_xdg_settings(tmp_path):
    """Settings -> "Make I.K.E. the default browser" writes mimeapps.list itself: a
    stand-in xdg-settings on the PATH is never started."""
    bin_dir = tmp_path / "bin"
    log = _stand_ins(bin_dir, XDG_UTILS)
    env = {"PATH": str(bin_dir), "HOME": str(tmp_path), "XDG_CONFIG_HOME": str(tmp_path / "cfg")}
    old = dict(os.environ)
    os.environ.update(env)
    try:
        written = handoff.set_default_browser(environ=env)
    finally:
        os.environ.clear()
        os.environ.update(old)
    assert written == [tmp_path / "cfg" / "mimeapps.list"]
    groups = handoff.parse_groups(written[0].read_text())
    assert groups == {"Default Applications": {t: "ike-browser.desktop;" for t in handoff.BROWSER_TYPES}}
    time.sleep(0.2)
    assert not log.exists()


# --- mimeapps.list -------------------------------------------------------------------------------------

USER_LIST = """\
# my own notes
[Added Associations]
text/html=firefox.desktop;org.kde.kate.desktop;

[Default Applications]
x-scheme-handler/http=firefox.desktop;chromium.desktop;
application/pdf=org.kde.okular.desktop;
text/html=firefox.desktop

[Removed Associations]
image/png=gimp.desktop;
"""


def test_mimeapps_list_keeps_every_other_entry():
    new = handoff.set_defaults(USER_LIST, dict.fromkeys(handoff.BROWSER_TYPES, "ike-browser.desktop"))
    g = handoff.parse_groups(new)
    d = g["Default Applications"]
    assert d["x-scheme-handler/http"] == "ike-browser.desktop;firefox.desktop;chromium.desktop;"
    assert d["text/html"] == "ike-browser.desktop;firefox.desktop;"
    assert d["x-scheme-handler/https"] == "ike-browser.desktop;"
    assert d["application/pdf"] == "org.kde.okular.desktop;"
    assert g["Added Associations"] == {"text/html": "firefox.desktop;org.kde.kate.desktop;"}
    assert g["Removed Associations"] == {"image/png": "gimp.desktop;"}
    assert new.startswith("# my own notes\n[Added Associations]\n")
    # https goes inside its group, before the blank line that ends it
    lines = new.splitlines()
    i = lines.index("x-scheme-handler/https=ike-browser.desktop;")
    assert lines[i - 1] == "text/html=ike-browser.desktop;firefox.desktop;" and lines[i + 1] == ""
    # written again: nothing changes (I.K.E. once, first)
    assert handoff.set_defaults(new, dict.fromkeys(handoff.BROWSER_TYPES, "ike-browser.desktop")) == new
    # an empty file, a file without the group, a file with no final newline, Windows line ends
    assert handoff.parse_groups(handoff.set_defaults("", {"text/html": "a.desktop"})) == {
        "Default Applications": {"text/html": "a.desktop;"}}
    odd = handoff.set_defaults("[Added Associations]\nx/y=b.desktop;", {"text/html": "a.desktop"})
    assert odd == "[Added Associations]\nx/y=b.desktop;\n\n[Default Applications]\ntext/html=a.desktop;\n"
    crlf = handoff.set_defaults("[Default Applications]\r\ntext/html=b.desktop;\r\n", {"text/html": "a.desktop"})
    assert crlf == "[Default Applications]\r\ntext/html=a.desktop;b.desktop;\r\n"
    # only_existing: a desktop's own list gets only the types it already names
    assert handoff.set_defaults("[Default Applications]\nx/y=b.desktop;\n", {"text/html": "a.desktop"},
                                only_existing=True) == "[Default Applications]\nx/y=b.desktop;\n"


def test_the_default_browser_is_written_atomically_and_completely(tmp_path, monkeypatch):
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    real = tmp_path / "dotfiles" / "mimeapps.list"
    real.parent.mkdir()
    real.write_text(USER_LIST)
    real.chmod(0o640)
    (cfg / "mimeapps.list").symlink_to(real)                # dotfiles kept elsewhere: the link stays
    (cfg / "kde-mimeapps.list").write_text("[Default Applications]\nx-scheme-handler/https=firefox.desktop;\n"
                                           "image/png=org.kde.gwenview.desktop;\n")
    (cfg / "gnome-mimeapps.list").write_text("[Default Applications]\nimage/png=eog.desktop;\n")
    (cfg / "kdeglobals").write_text("[General]\nBrowserApplication=firefox.desktop\nColorScheme=BreezeDark\n\n"
                                    "[KDE]\nBrowserApplication=other\n")
    # only this test's folders: the computer's own apps and lists (a Firefox installed on the
    # runner, /etc/xdg) are never read
    env = {"HOME": str(tmp_path), "XDG_CONFIG_HOME": str(cfg), "XDG_CURRENT_DESKTOP": "KDE:GNOME",
           "XDG_DATA_HOME": str(tmp_path / "data"), "XDG_DATA_DIRS": str(tmp_path / "usr"),
           "XDG_CONFIG_DIRS": str(tmp_path / "etc"), "PATH": os.environ["PATH"]}
    make_app(tmp_path / "usr" / "applications", "ike-browser.desktop", "I.K.E.", list(handoff.BROWSER_TYPES))
    make_app(tmp_path / "usr" / "applications", "firefox.desktop", "Firefox", list(handoff.BROWSER_TYPES))
    # a write that fails half way leaves the old file whole
    real_replace = os.replace

    def broken(*a):
        raise OSError("disk full")
    monkeypatch.setattr(os, "replace", broken)
    with pytest.raises(OSError):
        handoff.set_default_browser(environ=env)
    assert real.read_text() == USER_LIST
    assert [p.name for p in cfg.iterdir() if p.name.startswith(".")] == []          # no temporary file left
    monkeypatch.setattr(os, "replace", real_replace)
    written = handoff.set_default_browser(environ=env)
    assert [p.name for p in written] == ["mimeapps.list", "kde-mimeapps.list", "kdeglobals"]
    assert (cfg / "mimeapps.list").is_symlink() and oct(real.stat().st_mode & 0o777) == "0o640"
    d = handoff.parse_groups(real.read_text())["Default Applications"]
    assert all(d[t].startswith("ike-browser.desktop;") for t in handoff.BROWSER_TYPES)
    kde = handoff.parse_groups((cfg / "kde-mimeapps.list").read_text())["Default Applications"]
    assert kde == {"x-scheme-handler/https": "ike-browser.desktop;firefox.desktop;",
                   "image/png": "org.kde.gwenview.desktop;"}
    assert (cfg / "gnome-mimeapps.list").read_text() == "[Default Applications]\nimage/png=eog.desktop;\n"
    assert (cfg / "kdeglobals").read_text() == ("[General]\nBrowserApplication=ike-browser.desktop\n"
                                                "ColorScheme=BreezeDark\n\n[KDE]\nBrowserApplication=other\n")
    # the browser the desktop now finds for web links is I.K.E., first in the list; a handoff
    # never offers I.K.E. itself, so the one offered is the next installed browser
    d = handoff.parse_groups((cfg / "kde-mimeapps.list").read_text())["Default Applications"]
    assert handoff.ids(d["x-scheme-handler/https"])[0] == "ike-browser.desktop"
    assert handoff.default_app("x-scheme-handler/https", env).id == "firefox.desktop"
    (tmp_path / "usr" / "applications" / "firefox.desktop").unlink()
    assert handoff.default_app("x-scheme-handler/http", env) is None


# --- which app the desktop has for a type ----------------------------------------------------------------

def make_app(folder, desktop_id, name, types, exec_line="true %f", extra=""):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / desktop_id).write_text("[Desktop Entry]\nType=Application\nName=%s\nName[it]=%s (it)\nExec=%s\n"
                                     "MimeType=%s\n%s" % (name, name, exec_line, ";".join(types) + ";", extra))


def test_the_desktops_app_for_a_type(tmp_path):
    home, system = tmp_path / "home", tmp_path / "usr"
    apps = system / "applications"
    env = {"HOME": str(home), "XDG_CONFIG_HOME": str(home / "cfg"), "XDG_DATA_HOME": str(home / "data"),
           "XDG_DATA_DIRS": str(system), "XDG_CONFIG_DIRS": str(tmp_path / "etc"), "PATH": os.environ["PATH"],
           "XDG_CURRENT_DESKTOP": "KDE"}
    make_app(apps, "org.kde.okular.desktop", "Okular", ["application/pdf"])
    make_app(apps, "evince.desktop", "Document Viewer", ["application/pdf"])
    make_app(apps, "gone.desktop", "Gone", ["application/pdf"], exec_line="no-such-program-ike %f")
    make_app(apps, "hidden.desktop", "Hidden", ["text/calendar"], extra="Hidden=true\n")
    make_app(apps, "tryexec.desktop", "Try", ["text/calendar"], extra="TryExec=no-such-program-ike\n")
    make_app(apps, "ike-browser.desktop", "I.K.E.", ["application/pdf", "text/html"])
    make_app(apps / "kde", "kate.desktop", "Kate", ["text/plain"])           # kde-kate.desktop
    assert handoff.default_app("text/calendar", env) is None                   # hidden, or cannot start
    assert handoff.default_app("text/html", env) is None                       # I.K.E. itself never counts
    # no list: the apps that declare the type, in name order
    assert handoff.default_app("application/pdf", env).name == "Document Viewer"
    # the system's default, then the user's own (stronger), then a desktop's own list (stronger still)
    (tmp_path / "etc").mkdir()
    (tmp_path / "etc" / "mimeapps.list").write_text("[Default Applications]\napplication/pdf=gone.desktop;"
                                                    "org.kde.okular.desktop;\n")
    assert handoff.default_app("application/pdf", env).id == "org.kde.okular.desktop"   # gone is not installed
    (home / "cfg").mkdir(parents=True)
    (home / "cfg" / "mimeapps.list").write_text("[Default Applications]\napplication/pdf=evince.desktop;\n")
    assert handoff.default_app("application/pdf", env).id == "evince.desktop"
    (home / "cfg" / "kde-mimeapps.list").write_text("[Default Applications]\napplication/pdf=org.kde.okular.desktop\n")
    found = handoff.default_app("application/pdf", env, "it_IT")
    assert (found.id, found.name) == ("org.kde.okular.desktop", "Okular (it)")
    # a removed association is not offered; an added one is
    (home / "cfg" / "kde-mimeapps.list").unlink()
    (home / "cfg" / "mimeapps.list").write_text("[Removed Associations]\ntext/plain=kde-kate.desktop;\n")
    assert handoff.default_app("text/plain", env) is None
    (home / "cfg" / "mimeapps.list").write_text("[Added Associations]\nimage/png=org.kde.okular.desktop;\n")
    assert handoff.default_app("image/png", env).name == "Okular"
    assert handoff.default_app("text/plain", env).id == "kde-kate.desktop"
    # mimeinfo.cache, when the folder has one, says which apps declare a type
    (apps / "mimeinfo.cache").write_text("[MIME Cache]\napplication/pdf=org.kde.okular.desktop;\n"
                                         "text/plain=kde-kate.desktop;\n")
    (home / "cfg" / "mimeapps.list").unlink()
    (tmp_path / "etc" / "mimeapps.list").unlink()
    assert handoff.default_app("application/pdf", env).id == "org.kde.okular.desktop"
    # a type's parents count (a Python script is text: Kate)
    assert handoff.app_for("text/x-python", env).name.startswith("Kate")


def test_kinds_and_names():
    from PyQt6.QtCore import QMimeDatabase
    db = QMimeDatabase()
    kind = {n: handoff.kind_of(db.mimeTypeForName(n)) for n in (
        "application/zip", "application/x-compressed-tar", "application/x-7z-compressed", "text/calendar",
        "application/pdf", "image/png", "image/svg+xml", "text/plain", "application/x-desktop")}
    assert kind == {"application/zip": "archive", "application/x-compressed-tar": "archive",
                    "application/x-7z-compressed": "archive", "text/calendar": "calendar", "application/pdf": "pdf",
                    "image/png": "image", "image/svg+xml": "image", "text/plain": "", "application/x-desktop": ""}
    assert handoff.image_type("photo.JPG") == "image/jpeg" and handoff.image_type("show.php?id=3") == "image/png"
    assert handoff.safe_name("../../.bashrc") == "_.._.bashrc" and handoff.safe_name("", "image") == "image"
    assert "/" not in handoff.safe_name("a/b\\c") and len(handoff.safe_name("x" * 500)) <= 120


# --- the portal, on a private bus -------------------------------------------------------------------------

DRIVER = r"""
import json, os, sys, time
sys.path.insert(0, os.environ["IKE_ROOT"])
from PyQt6.QtCore import QCoreApplication, QEventLoop
from ike import handoff

app = QCoreApplication([])
fallback = []
h = handoff.Handoff(opener=lambda target: fallback.append(target) or "stand-in")
h.nothing = lambda target, parent=None: fallback.append("nothing:" + str(target))
f, d = sys.argv[1], sys.argv[2]
h.open_file(f)
h.show_in_folder(f)
h.open_file(d)
h.open_uri("mailto:arc@example.it?subject=Ciao")
end = time.time() + 5
while time.time() < end:
    app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
    time.sleep(0.01)
print(json.dumps({"fallback": fallback, "connected": bool(h._bus and h._bus.connected)}))
"""


@pytest.fixture
def portal_bus(tmp_path):
    if not shutil.which("dbus-daemon"):
        pytest.skip("dbus-daemon not installed")
    pytest.importorskip("jeepney")
    started = []

    def start(mode=None):
        daemon = subprocess.Popen(["dbus-daemon", "--session", "--nofork", "--print-address=1"],
                                  stdout=subprocess.PIPE, text=True)
        started.append(daemon)
        address = daemon.stdout.readline().strip()
        log = tmp_path / ("portal-%d.log" % len(started))
        env = dict(os.environ, DBUS_SESSION_BUS_ADDRESS=address)
        if mode != "none":
            portal = subprocess.Popen([sys.executable, str(Path(__file__).parent / "portal_standin.py"), str(log)]
                                      + ([mode] if mode else []), env=env)
            started.append(portal)
            for _ in range(100):
                if log.exists():
                    break
                time.sleep(0.05)
        return address, log
    yield start
    for p in started:
        p.kill()
        p.wait()


def _drive(address, tmp_path):
    f = tmp_path / "dir with space" / "report é.pdf"
    f.parent.mkdir()
    f.write_bytes(b"%PDF-1.4\n")
    env = dict(os.environ, DBUS_SESSION_BUS_ADDRESS=address, IKE_ROOT=str(ROOT), QT_QPA_PLATFORM="offscreen")
    done = subprocess.run([sys.executable, "-c", DRIVER, str(f), str(f.parent)], env=env, capture_output=True,
                          text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    return f, json.loads(done.stdout.strip().splitlines()[-1])


def _calls(log):
    return [json.loads(line) for line in log.read_text().splitlines()[1:]] if log.exists() else []


def test_the_portal_gets_the_file_itself(portal_bus, tmp_path):
    """OpenFile and OpenDirectory get a descriptor of the very file (the portal reads its
    path from it), OpenURI the link; nothing falls back to another program."""
    address, log = portal_bus()
    f, out = _drive(address, tmp_path)
    calls = _calls(log)
    assert all(c["event"] == "call" for c in calls)
    assert [(c["member"], c.get("path") or c.get("uri")) for c in calls] == [
        ("OpenFile", str(f)), ("OpenDirectory", str(f)), ("OpenFile", str(f.parent)),
        ("OpenURI", "mailto:arc@example.it?subject=Ciao")], calls
    assert all(c["parent"] == "" and c["options"]["handle_token"].startswith("ike") for c in calls)
    assert len({c["options"]["handle_token"] for c in calls}) == 4
    assert out == {"fallback": [], "connected": True}


def test_an_older_portal_and_no_portal(portal_bus, tmp_path):
    """A portal without OpenDirectory opens the folder itself; with no portal on the bus
    every request goes to the desktop's own opener (never xdg-open)."""
    address, log = portal_bus("old")
    f, out = _drive(address, tmp_path)
    every = _calls(log)
    calls = sorted((c["member"], c.get("path") or c.get("uri")) for c in every if c["event"] == "call")
    assert calls == sorted([("OpenFile", str(f)), ("OpenFile", str(f.parent)), ("OpenFile", str(f.parent)),
                            ("OpenURI", "mailto:arc@example.it?subject=Ciao")]), calls
    assert [c["member"] for c in every if c["event"] == "refused"] == ["OpenDirectory"]
    assert out["fallback"] == []
    address, log = portal_bus("none")
    (tmp_path / "dir with space" / "report é.pdf").unlink()
    (tmp_path / "dir with space").rmdir()
    f, out = _drive(address, tmp_path)
    assert sorted(out["fallback"]) == sorted([str(f), str(f.parent), str(f.parent),
                                              "mailto:arc@example.it?subject=Ciao"]), out


def test_no_session_bus_at_all(tmp_path, monkeypatch):
    """No bus (a bare window manager, the tests): straight to the opener, nothing waits."""
    monkeypatch.setenv("DBUS_SESSION_BUS_ADDRESS", "")
    got = []
    h = handoff.Handoff(opener=lambda t: got.append(t) or "x")
    f = tmp_path / "a.zip"
    f.write_bytes(b"PK")
    h.open_file(f)
    h.show_in_folder(f)
    h.open_uri("magnet:?xt=1")
    assert got == [str(f), str(tmp_path), "magnet:?xt=1"]
    # a file that is not there: the opener is asked (it says so), never a crash
    h.open_file(tmp_path / "missing.zip")
    assert got[-1] == str(tmp_path / "missing.zip")


# --- the menus and the downloads window, in the browser --------------------------------------------------

PNG = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082")
ICS = b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nSUMMARY:Test\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"


@pytest.fixture
def files_site():
    files = {"/pic.png": (PNG, "image/png"), "/fake.png": (b"[Desktop Entry]\nExec=rm -rf ~\n", "image/png"),
             "/event.ics": (ICS, "text/calendar"), "/doc.pdf": (b"%PDF-1.4\n%%EOF\n", "application/pdf"),
             "/pack.zip": (b"PK\x05\x06" + b"\0" * 18, "application/zip")}

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body, kind = files.get(self.path, (b"<!doctype html><title>page</title><p>hello", "text/html"))
            self.send_response(200)
            self.send_header("Content-Type", kind)
            if self.path in ("/event.ics", "/pack.zip"):
                self.send_header("Content-Disposition", "attachment; filename=%s" % self.path[1:])
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield "http://127.0.0.1:%d" % srv.server_address[1]
    srv.shutdown()


MENUS = r'''
import json, os
from pathlib import Path
SITE, APPS = %r, %r

class Req:
    """What the engine says about a right click (the parts the menu reads)."""
    def __init__(self, link="", media="", mtype="MediaTypeNone"):
        from PyQt6.QtCore import QUrl
        from PyQt6.QtWebEngineCore import QWebEngineContextMenuRequest as R
        self._link, self._media, self._type = QUrl(link), QUrl(media), getattr(R.MediaType, mtype)
    def linkUrl(self): return self._link
    def mediaUrl(self): return self._media
    def mediaType(self): return self._type
    def selectedText(self): return ""
    def isContentEditable(self): return False
    def editFlags(self):
        from PyQt6.QtWebEngineCore import QWebEngineContextMenuRequest as R
        return R.EditFlag(0)
    def mediaFlags(self):
        from PyQt6.QtWebEngineCore import QWebEngineContextMenuRequest as R
        return R.MediaFlag(0)
    def misspelledWord(self): return ""
    def spellCheckerSuggestions(self): return []
    def linkText(self): return ""
    def position(self):
        from PyQt6.QtCore import QPoint
        return QPoint(5, 5)

def texts(menu):
    return [a.text() for a in menu.actions() if a.text()]

def steps(ike, qapp, out):
    from PyQt6.QtCore import QUrl
    from ike import contextmenu, handoff
    from ike.dialogs import DownloadsDialog
    # the desktop's apps: only those of this test (the computer's own are not looked at)
    handoff.data_dirs = lambda environ=None: [Path(APPS)]
    handoff.config_dirs = lambda environ=None: [Path(APPS) / "etc"]
    handoff.FOUND_SECONDS = 0
    opened, folders = [], []
    ike.handoff.open_file = lambda path, parent=None: opened.append(str(path))
    ike.handoff.show_in_folder = lambda path, parent=None: folders.append(str(path))
    win = ike.windows[0]
    view = win.current_view()
    view.setHtml("<p>page", QUrl(SITE + "/page.html"))
    yield 800
    menus = {}
    menus["page"] = texts(contextmenu.build(view, None))
    menus["image"] = texts(contextmenu.build(view, Req(media=SITE + "/pic.png", mtype="MediaTypeImage")))
    menus["ics"] = texts(contextmenu.build(view, Req(link=SITE + "/event.ics")))
    menus["plugin"] = texts(contextmenu.build(view, Req(media=SITE + "/doc.pdf", mtype="MediaTypePlugin")))
    view.setHtml("<p>pdf", QUrl(SITE + "/doc.pdf"))
    yield 600
    menus["pdf"] = texts(contextmenu.build(view, None))
    out["menus"] = menus
    # what the entries do
    menu = contextmenu.build(view, Req(media=SITE + "/pic.png", mtype="MediaTypeImage"))
    for a in menu.actions():
        if a.text().startswith("Open image in "):
            a.trigger()
    ike.hand_off(QUrl(SITE + "/fake.png"), "image", view.page())       # says image, holds a .desktop file
    ike.hand_off(QUrl(SITE + "/doc.pdf"), "pdf", view.page())
    menu = contextmenu.build(view, None)
    for a in menu.actions():
        if a.text().startswith("Open the page source in "):
            a.trigger()
    # up to 30 s (2026-11-27: after heavy tests of the same shard a CI runner needed
    # more than 6 s for the three downloads); it goes on as soon as all three are open
    for _ in range(300):
        yield 100
        if len(opened) >= 3:
            break
    yield 500
    out["opened"] = [[Path(p).name, Path(p).read_bytes()[:12].hex(), oct(Path(p).parent.stat().st_mode & 0o777)]
                     for p in opened]
    out["handoff_dir"] = sorted(p.name for p in handoff.temp_dir().iterdir())
    out["downloads_listed"] = len(ike.downloads)
    # the downloads window: an archive (Ark), a calendar file
    for name in ("pack.zip", "event.ics"):
        view.page().download(QUrl(SITE + "/" + name))
        yield 1200
    dlg = DownloadsDialog(ike, win)
    dlg.show()
    rows = {}
    for i in range(dlg.tree.topLevelItemCount()):
        dlg.tree.setCurrentItem(dlg.tree.topLevelItem(i))
        yield 100
        rows[dlg.tree.topLevelItem(i).text(0)] = [dlg.app_button.isVisible() and dlg.app_button.text(),
                                                  dlg.folder_button.isVisible()]
        if dlg.app_button.isVisible():
            dlg.app_button.click()
    dlg.folder_button.click()
    out["rows"] = rows
    out["after_buttons"] = [Path(p).name for p in opened[3:]]
    out["folders"] = [Path(p).name for p in folders]
    dlg.close()
'''


def _apps(folder, with_apps):
    folder.mkdir(parents=True, exist_ok=True)
    if not with_apps:
        return
    apps = folder / "applications"
    make_app(apps, "org.kde.okular.desktop", "Okular", ["application/pdf"])
    make_app(apps, "org.kde.gwenview.desktop", "Gwenview", ["image/png", "image/jpeg"])
    make_app(apps, "org.kde.kate.desktop", "Kate", ["text/plain"])
    make_app(apps, "org.kde.ark.desktop", "Ark", ["application/zip", "application/x-tar"])
    make_app(apps, "org.kde.merkuro.calendar.desktop", "Merkuro Calendar", ["text/calendar"])
    make_app(apps, "org.kde.dolphin.desktop", "Dolphin", ["inode/directory"])


def test_handoffs_are_shown_only_when_the_desktop_has_the_app(run_ike, files_site, tmp_path):
    apps = tmp_path / "apps"
    _apps(apps, True)
    out = run_ike(MENUS % (files_site, str(apps)), timeout=150,
                  settings={"download_dir": str(tmp_path / "dl"), "ask_download_location": False})
    m = out["menus"]
    assert "Open the page source in Kate" in m["page"] and "Page source" in m["page"]
    assert m["page"].index("Open the page source in Kate") == m["page"].index("Page source") + 1
    assert "Open image in Gwenview" in m["image"]
    assert "Add to calendar" in m["ics"]
    assert "Open with Okular" in m["plugin"] and "Open with Okular" in m["pdf"]
    assert not any(t.startswith("Open with") for t in m["page"] + m["image"] + m["ics"])
    # the image and the PDF fetched by the engine into a private folder, the page's code
    # written there; the "image" that holds a desktop file is never handed over
    names = sorted(o[0].split("-", 2)[2] for o in out["opened"])
    assert names == ["127.0.0.1-source.txt", "doc.pdf", "pic.png"], (
        out["opened"], out.get("handoff_dir"), out.get("downloads_listed"), (out.get("_stderr") or "")[-4000:])
    by_name = {o[0].split("-", 2)[2]: o for o in out["opened"]}
    assert by_name["pic.png"][1].startswith("89504e47") and by_name["doc.pdf"][1].startswith("255044462d")
    assert all(o[2] == "0o700" for o in out["opened"])
    assert not [n for n in out["handoff_dir"] if "fake" in n], out["handoff_dir"]
    assert out["downloads_listed"] == 0                         # a handoff is not the user's download
    assert out["rows"] == {"pack.zip": ["Open with Ark", True], "event.ics": ["Add to calendar", True]}, out["rows"]
    assert sorted(out["after_buttons"]) == ["event.ics", "pack.zip"]
    assert out["folders"] in (["pack.zip"], ["event.ics"])


def test_no_app_no_handoff(run_ike, files_site, tmp_path):
    apps = tmp_path / "apps"
    _apps(apps, False)
    out = run_ike(MENUS % (files_site, str(apps)), timeout=150,
                  settings={"download_dir": str(tmp_path / "dl"), "ask_download_location": False})
    m = out["menus"]
    every = m["page"] + m["image"] + m["ics"] + m["plugin"] + m["pdf"]
    for text in ("Open the page source in", "Open image in", "Add to calendar", "Open with"):
        assert not [t for t in every if t.startswith(text) and t != "Open image in new tab"], (text, m)
    assert "Page source" in m["page"] and "Save image as…" in m["image"]           # the rest as before
    assert out["rows"] == {"pack.zip": [False, False], "event.ics": [False, False]}, out["rows"]
    # (asked by I.K.E. itself, a PDF is still handed over: the menus are what hide the entries)
    assert [o[0].split("-", 2)[2] for o in out["opened"]] == ["doc.pdf"], out["opened"]
