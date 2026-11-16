"""Desktop integration through D-Bus (plasma.py), on a private test bus.

The desktop side is played by tests/dbus_standins.py (Plasma's job view server,
KDE Connect with one phone, the screen saver) and by ``gdbus`` calls made from
inside the browser, the way Plasma's media widget and KRunner call I.K.E.
"""

import http.server
import math
import struct
import threading
import time
import wave
from io import BytesIO

import pytest


def _tone():
    buf = BytesIO()
    w = wave.open(buf, "wb")
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(16000)
    w.writeframes(b"".join(struct.pack("<h", int(6000 * math.sin(2 * math.pi * 440 * i / 16000)))
                           for i in range(16000 * 4)))
    w.close()
    return buf.getvalue()


# (from a blob, so the test server need not answer range requests for seeking)
SONG = (b"<!doctype html><title>Song page</title><audio id=a loop></audio><script>"
        b"navigator.mediaSession.metadata=new MediaMetadata({title:'Ice Tone',artist:'Tester',album:'Tests',"
        b"artwork:[{src:'http://127.0.0.1/cover.png'}]});var a=document.getElementById('a');"
        b"fetch('/tone.wav').then(r=>r.blob()).then(b=>{a.src=URL.createObjectURL(b);a.play()})</script>")
SIZE = 200 * 1024


@pytest.fixture
def site():
    tone = _tone()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/file.bin":
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Disposition", "attachment; filename=file.bin")
                self.send_header("Content-Length", str(SIZE))
                self.end_headers()
                try:
                    for _ in range(40):
                        self.wfile.write(b"x" * (SIZE // 40))
                        self.wfile.flush()
                        time.sleep(0.1)
                except OSError:
                    pass
                return
            pages = {"/song": (SONG, "text/html"), "/tone.wav": (tone, "audio/wav"),
                     "/zebra": (b"<title>Zebra crossing guide</title>zebra", "text/html"),
                     "/other": (b"<title>Other page</title>x", "text/html")}
            body, kind = pages.get(self.path, (b"<title>x</title>", "text/html"))
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield "http://127.0.0.1:%d" % httpd.server_address[1]
    httpd.shutdown()


# gdbus from inside the browser, without blocking its event loop
GDBUS = """
from PyQt6.QtCore import QProcess

def gdbus(res, *args):
    p = QProcess()
    p.start("gdbus", ["call", "--session", *args])
    for _ in range(60):
        yield 100
        if p.state() == QProcess.ProcessState.NotRunning:
            break
    res.append(bytes(p.readAllStandardOutput()).decode() + bytes(p.readAllStandardError()).decode())

def js(view, code, res):
    view.page().runJavaScript(code, 1, lambda v: res.append(v))
"""


def test_media_controls(run_ice, site, desktop_bus):
    address, _log, _f = desktop_bus
    out = run_ice(GDBUS + """
def steps(ice, qapp, out):
    yield 300
    win = ice.windows[0]
    view = win.add_tab(%r)
    yield 3500
    d = ice.desktop
    name = d.mpris_name
    out["registered"] = d._mpris_on and name in d.bus.names
    P = ["-d", name, "-o", "/org/mpris/MediaPlayer2"]
    r = []
    yield from gdbus(r, *P, "-m", "org.freedesktop.DBus.Properties.GetAll", "org.mpris.MediaPlayer2")
    yield from gdbus(r, *P, "-m", "org.freedesktop.DBus.Properties.GetAll", "org.mpris.MediaPlayer2.Player")
    yield from gdbus(r, *P, "-m", "org.mpris.MediaPlayer2.Player.Pause")
    yield 600
    js(view, "document.getElementById('a').paused", r)
    yield from gdbus(r, *P, "-m", "org.freedesktop.DBus.Properties.Get", "org.mpris.MediaPlayer2.Player",
                     "PlaybackStatus")
    yield from gdbus(r, *P, "-m", "org.mpris.MediaPlayer2.Player.PlayPause")
    yield 600
    js(view, "document.getElementById('a').paused", r)
    track = "/org/ike/track/%%d" %% d._track
    yield from gdbus(r, *P, "-m", "org.mpris.MediaPlayer2.Player.SetPosition", track, "2500000")
    yield 400
    js(view, "document.getElementById('a').currentTime", r)
    yield from gdbus(r, *P, "-m", "org.freedesktop.DBus.Introspectable.Introspect")
    out["calls"] = r
    win.close_tab(view)
    yield 1500
    q = []
    yield from gdbus(q, "-d", "org.freedesktop.DBus", "-o", "/org/freedesktop/DBus",
                     "-m", "org.freedesktop.DBus.NameHasOwner", name)
    out["after_close"] = q[0]
""" % (site + "/song"), env={"DBUS_SESSION_BUS_ADDRESS": address})
    c = out["calls"]
    assert out["registered"]
    assert "'Identity': <'I.K.E.'>" in c[0] and "'DesktopEntry': <'ike-browser'>" in c[0]
    assert "'PlaybackStatus': <'Playing'>" in c[1]
    assert "'xesam:title': <'Ice Tone'>" in c[1] and "'xesam:artist': <['Tester']>" in c[1]
    assert "'xesam:album': <'Tests'>" in c[1] and "mpris:length" in c[1] and "int64" in c[1]
    assert "'mpris:artUrl': <'http://127.0.0.1/cover.png'>" in c[1]
    assert c[3] is True and "Paused" in c[4]
    assert c[6] is False
    assert 2.3 < c[8] < 3.5
    assert "org.mpris.MediaPlayer2.Player" in c[9]
    assert "false" in out["after_close"]


def test_media_switched_off_and_private(run_ice, site, desktop_bus):
    address, _log, _f = desktop_bus
    out = run_ice("""
        def steps(ice, qapp, out):
            yield 300
            win = ice.windows[0]
            win.add_tab(%r)
            yield 3000
            out["off"] = ice.desktop._mpris_on
            ice.config["di_media"] = True
            p = ice.new_window(private=True, urls=[%r])
            yield 3000
            out["private"] = ice.desktop._mpris_on
    """ % (site + "/song", site + "/song"), settings={"di_media": False},
        env={"DBUS_SESSION_BUS_ADDRESS": address})
    assert out["off"] is False and out["private"] is False


def test_krunner(run_ice, site, desktop_bus, tmp_path):
    address, _log, _f = desktop_bus
    out = run_ice(GDBUS + """
import os

def steps(ice, qapp, out):
    yield 300
    win = ice.windows[0]
    zebra = win.add_tab(%r)
    other = win.add_tab(%r)
    ice.storage.add_bookmark("https://zebra.example/stripes", "Zebra stripes explained")
    yield 1500
    d = ice.desktop
    out["owned"] = d.runner_name in d.bus.names
    f = os.path.join(os.environ["XDG_DATA_HOME"], "krunner", "dbusplugins", "ike-browser.desktop")
    out["desktop_file"] = open(f).read()
    R = ["-d", d.runner_name, "-o", "/runner"]
    r = []
    yield from gdbus(r, *R, "-m", "org.kde.krunner1.Match", "zebra")
    yield from gdbus(r, *R, "-m", "org.kde.krunner1.Match", "ze")
    yield from gdbus(r, *R, "-m", "org.kde.krunner1.Actions")
    out["calls"] = r
    out["current_before"] = win.current_view() is other
    yield from gdbus(r, *R, "-m", "org.kde.krunner1.Run", "tab:0:%%d" %% id(zebra), "")
    yield 300
    out["current_after"] = win.current_view() is zebra
    n = len(win.views)
    yield from gdbus(r, *R, "-m", "org.kde.krunner1.Run", "bm:https://zebra.example/stripes", "")
    yield 300
    out["bookmark_opened"] = len(win.views) == n + 1
    ice.config["di_krunner"] = False
    ice.desktop.settings_changed()
    yield 300
    out["file_after_off"] = os.path.exists(f)
    out["owned_after_off"] = d.runner_name in d.bus.names
""" % (site + "/zebra", site + "/other"), env={"DBUS_SESSION_BUS_ADDRESS": address})
    m, short, actions = out["calls"][:3]
    assert out["owned"]
    assert "X-Plasma-DBusRunner-Service=org.kde.ice_browser.krunner.*" in out["desktop_file"]
    assert "X-Plasma-DBusRunner-Path=/runner" in out["desktop_file"]
    assert "'Zebra crossing guide'" in m and "'Zebra stripes explained'" in m and "Other page" not in m
    assert "'subtext': <'https://zebra.example/stripes'>" in m
    assert short.strip() == "(@a(sssida{sv}) [],)"
    assert actions.strip() == "(@a(sss) [],)"
    assert out["current_before"] and out["current_after"] and out["bookmark_opened"]
    assert out["file_after_off"] is False and out["owned_after_off"] is False


def test_downloads_in_notifications(run_ice, site, desktop_bus, tmp_path):
    address, log, logfile = desktop_bus
    out = run_ice("""
        from PyQt6.QtCore import QUrl

        def steps(ice, qapp, out):
            yield 400
            win = ice.windows[0]
            win.current_view().page().download(QUrl(%r))
            for _ in range(60):
                yield 200
                if ice.downloads and ice.downloads[0].isFinished():
                    break
            yield 500
            win.current_view().page().download(QUrl(%r))
            yield 1500
            open(%r, "w").write("cancel")       # the user presses "cancel" in Plasma
            for _ in range(30):
                yield 200
                if ice.downloads[0].isFinished():
                    break
            yield 500
            out["second_state"] = ice.downloads[0].state().name
    """ % (site + "/file.bin", site + "/file.bin", str(logfile) + ".cmd"),
        settings={"download_dir": str(tmp_path / "dl"), "ask_download_location": False},
        env={"DBUS_SESSION_BUS_ADDRESS": address}, timeout=120)
    calls = [c for c in log() if c.get("event") == "call"]
    views = [c for c in calls if c["member"] == "requestView"]
    assert len(views) == 2
    assert views[0]["body"][0] == "ike-browser" and views[0]["body"][1] == 1
    assert views[0]["body"][2]["title"] == "Downloading"
    first = "/org/kde/notificationmanager/jobs/JobView_1"
    updates = [c["body"][0] for c in calls if c["member"] == "update" and c["path"] == first]
    percents = [u["percent"] for u in updates if "percent" in u]
    assert percents and percents[-1] == 100 and any(0 < p < 100 for p in percents)
    assert updates[-1]["processedBytes"] == SIZE and updates[-1]["totalBytes"] == SIZE
    assert updates[-1]["descriptionValue2"].endswith("file.bin")
    assert any("speed" in u for u in updates)
    ends = {c["path"]: c["body"] for c in calls if c["member"] == "terminate"}
    assert ends[first][0] == 0
    assert out["second_state"] == "DownloadCancelled"
    assert ends["/org/kde/notificationmanager/jobs/JobView_2"][0] == 1


def test_send_to_phone(run_ice, site, desktop_bus):
    address, log, _f = desktop_bus
    out = run_ice("""
        def steps(ice, qapp, out):
            yield 300
            win = ice.windows[0]
            view = win.add_tab(%r)
            yield 1500
            out["devices"] = ice.desktop.devices
            from PyQt6.QtWidgets import QMenu
            m = QMenu()
            ice.desktop.add_send_menu(m, view.url().toString())
            sub = [a for a in m.actions() if a.menu()]
            out["menu"] = [sub[0].text()] + [a.text() for a in sub[0].menu().actions()] if sub else []
            sub[0].menu().actions()[0].trigger()
            yield 800
            from ice import contextmenu
            menu = contextmenu.build(view, None)
            out["page_menu"] = any(a.text() == "Send to device" for a in menu.actions())
            ice.config["di_kdeconnect"] = False
            ice.desktop.settings_changed()
            m2 = QMenu()
            ice.desktop.add_send_menu(m2, view.url().toString())
            out["menu_off"] = len(m2.actions())
    """ % (site + "/zebra"), env={"DBUS_SESSION_BUS_ADDRESS": address})
    assert out["devices"] == {"abc123": "Pixel"}
    assert out["menu"] == ["Send to device", "Pixel"]
    assert out["page_menu"]
    shares = [c for c in log() if c.get("member") == "shareUrl"]
    assert shares and shares[0]["path"] == "/modules/kdeconnect/devices/abc123/share"
    assert shares[0]["body"] == [site + "/zebra"]
    assert out["menu_off"] == 0


def test_screen_stays_on_through_the_engine(run_ice, site, desktop_bus, tmp_path):
    """Qt WebEngine asks the desktop to keep the screen on while a video plays."""
    import shutil
    import subprocess
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not installed")
    clip = tmp_path / "clip.webm"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=160x120:rate=10",
                    "-f", "lavfi", "-i", "sine=frequency=440", "-t", "6", "-c:v", "libvpx", "-b:v", "100k",
                    "-c:a", "libopus", "-shortest", str(clip)], check=True)
    address, log, _f = desktop_bus
    data = clip.read_bytes()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body, kind = ((b"<title>clip</title><video src='/c.webm' autoplay loop></video>", "text/html")
                          if self.path == "/" else (data, "video/webm"))
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    run_ice("""
        def steps(ice, qapp, out):
            yield 300
            ice.windows[0].add_tab(%r)
            yield 4000
    """ % ("http://127.0.0.1:%d/" % httpd.server_address[1]), env={"DBUS_SESSION_BUS_ADDRESS": address})
    httpd.shutdown()
    members = [c["member"] for c in log() if c.get("event") == "call"]
    assert "Inhibit" in members


def test_without_desktop_bus(run_ice, site):
    out = run_ice("""
        import os

        def steps(ice, qapp, out):
            yield 300
            ice.windows[0].add_tab(%r)
            yield 2500
            out["bus"] = ice.desktop.bus is None
            out["file"] = os.path.exists(os.path.join(os.environ["XDG_DATA_HOME"], "krunner"))
    """ % (site + "/song"))
    assert out["bus"] and out["file"] is False
