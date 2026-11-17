"""The everyday tools of 1.1.4, with real clicks, keys and wheel turns: zoom
kept for each site, videos and sounds that may not start by themselves (for
all sites, or one, from the site panel), the site information panel under the
lock, mouse gestures (off unless chosen; a right click alone still opens the
menu), the command bar (F2) and I.K.E.'s pages for sites that cannot be
reached. All on this computer."""

import io
import struct
import threading
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from test_security import JS


def _wav():
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(struct.pack("<h", 0) * 4000)
    return buf.getvalue()


WAV = _wav()
PLAY = ("<!doctype html><title>wait</title><body><p style='height:900px'>sound</p><script>"
        "var a = new Audio('/s.wav'); a.play().then(function () { document.title = 'played'; })"
        ".catch(function (e) { document.title = e.name; });</script></body>")


@pytest.fixture
def site():
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            path = self.path.split("?")[0]
            if path == "/s.wav":
                body, kind = WAV, "audio/wav"
            elif path == "/play":
                body, kind = PLAY.encode(), "text/html"
            else:
                name = path.strip("/") or "home"
                body = ("<!doctype html><title>%s</title><body style='height:2000px'><h1>%s</h1>"
                        "<p>text</p></body>" % (name, name)).encode()
                kind = "text/html"
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1]
    srv.shutdown()


COMMON = JS + r'''
from PyQt6.QtCore import QPoint, QPointF, Qt, QUrl
from PyQt6.QtGui import QWheelEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QToolButton

PORT = __PORT__
A = "http://127.0.0.1:%d" % PORT          # two sites on this computer
B = "http://localhost:%d" % PORT

def proxy(view):
    return view.focusProxy() or view

def wheel(view, up=True, ctrl=True):
    w = proxy(view)
    pos = QPointF(w.width() / 2, w.height() / 2)
    ev = QWheelEvent(pos, QPointF(w.mapToGlobal(pos.toPoint())), QPoint(0, 0), QPoint(0, 120 if up else -120),
                     Qt.MouseButton.NoButton,
                     Qt.KeyboardModifier.ControlModifier if ctrl else Qt.KeyboardModifier.NoModifier,
                     Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(w, ev)

def action_button(urlbar, act):
    found = [b for b in urlbar.findChildren(QToolButton) if b.defaultAction() is act]
    return found[0] if found else None
'''

ZOOM = COMMON + r'''
def steps(ike, qapp, out):
    win = ike.windows[0]
    win.resize(1200, 800)
    win.show()
    view = win.current_view()
    yield from load(view, A + "/one")
    yield 500
    wheel(view)                                  # Ctrl + wheel: one step
    yield 200
    out["a_zoom"] = round(view.zoomFactor(), 2)
    out["saved"] = dict(ike.config["site_zoom"])
    out["sign"] = win.urlbar.zoom_act.isVisible()
    yield from load(view, B + "/two")            # another site: its own (usual) zoom
    yield 500
    out["b_zoom"] = round(view.zoomFactor(), 2)
    yield from load(view, A + "/three")          # back to the first site: its zoom again
    yield 500
    out["a_again"] = round(view.zoomFactor(), 2)
    wheel(view, ctrl=False)                      # a plain wheel turn only scrolls
    yield 200
    out["plain"] = round(view.zoomFactor(), 2)
    # the lock opens the site panel: a real click on it
    btn = action_button(win.urlbar, win.urlbar.lock)
    QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
    yield 400
    panel = win.site_info
    out["panel"] = [win.site_info_menu.isVisible(), panel.host.text(), panel.zoom.text(),
                    panel.zoom_reset.isVisible(), panel.conn.text(), panel.autoplay.isChecked(),
                    panel.cookies.isVisible()]
    QTest.mouseClick(panel.zoom_reset, Qt.MouseButton.LeftButton)     # "Actual size" in the panel
    yield 300
    out["reset"] = [round(view.zoomFactor(), 2), dict(ike.config["site_zoom"]), win.urlbar.zoom_act.isVisible()]
    win.site_info_menu.hide()
'''


def test_zoom_kept_per_site_and_the_site_panel(run_ike, site):
    out = run_ike(ZOOM.replace("__PORT__", str(site)), timeout=150)
    assert out["a_zoom"] == 1.1 and out["saved"] == {"127.0.0.1": 1.1} and out["sign"] is True
    assert out["b_zoom"] == 1.0 and out["a_again"] == 1.1 and out["plain"] == 1.1
    shown, host, zoom, reset, conn, autoplay, cookies = out["panel"]
    assert shown and host == "127.0.0.1" and "110" in zoom and reset is True
    assert conn == "Connection is not encrypted" and autoplay is True and cookies is True
    assert out["reset"] == [1.0, {}, False]


AUTOPLAY = COMMON + r'''
def title_of(view):
    for _ in range(40):
        if view.title() not in ("wait", ""):
            break
        yield 100
    return view.title()

def steps(ike, qapp, out):
    win = ike.windows[0]
    win.show()
    view = win.current_view()
    yield from load(view, A + "/play")
    out["blocked"] = yield from title_of(view)
    # the site panel: this site may play by itself (a real click on the box)
    QTest.mouseClick(action_button(win.urlbar, win.urlbar.lock), Qt.MouseButton.LeftButton)
    yield 400
    box = win.site_info.autoplay
    out["box_before"] = box.isChecked()
    QTest.mouseClick(box, Qt.MouseButton.LeftButton, pos=QPoint(8, box.height() // 2))
    yield 300
    win.site_info_menu.hide()
    out["opt"] = ike.config.site_opt("127.0.0.1", "autoplay")
    yield 1500                                   # the page loads again by itself
    out["allowed_here"] = yield from title_of(view)
    yield from load(view, B + "/play")           # another site: still blocked
    out["other_site"] = yield from title_of(view)
'''


def test_videos_and_sounds_do_not_start_by_themselves_when_chosen(run_ike, site):
    out = run_ike(AUTOPLAY.replace("__PORT__", str(site)), settings={"autoplay_block": True}, timeout=150)
    assert out["blocked"] == "NotAllowedError"
    assert out["box_before"] is False and out["opt"] is True
    assert out["allowed_here"] != "NotAllowedError"
    assert out["other_site"] == "NotAllowedError"


def test_autoplay_free_by_default(run_ike, site):
    out = run_ike(AUTOPLAY.replace("__PORT__", str(site)).replace(
        'out["blocked"] = yield from title_of(view)', 'out["blocked"] = yield from title_of(view)\n    return'),
        timeout=120)
    assert out["blocked"] != "NotAllowedError"


GESTURES = COMMON + r'''
def drag(view, moves):
    w = proxy(view)
    start = QPoint(w.width() // 2, w.height() // 2)
    QTest.mousePress(w, Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier, start)
    pos = QPoint(start)
    for dx, dy in moves:
        for _ in range(5):
            pos = QPoint(pos.x() + dx // 5, pos.y() + dy // 5)
            ev = __import__("PyQt6.QtGui", fromlist=["QMouseEvent"]).QMouseEvent(
                __import__("PyQt6.QtCore", fromlist=["QEvent"]).QEvent.Type.MouseMove, QPointF(pos),
                QPointF(w.mapToGlobal(pos)), Qt.MouseButton.NoButton, Qt.MouseButton.RightButton,
                Qt.KeyboardModifier.NoModifier)
            QApplication.sendEvent(w, ev)
    QTest.mouseRelease(w, Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier, pos)

def steps(ike, qapp, out):
    win = ike.windows[0]
    win.resize(1200, 800)
    win.show()
    view = win.current_view()
    yield from load(view, A + "/first")
    yield from load(view, A + "/second")
    yield 400
    drag(view, [(-150, 0)])                      # ← back
    yield 1200
    out["back"] = view.url().path()
    drag(view, [(150, 0)])                       # → forward
    yield 1200
    out["forward"] = view.url().path()
    # a right click alone: the page's menu, as always
    w = proxy(view)
    QTest.mouseClick(w, Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier, QPoint(200, 200))
    yield 800
    menu = getattr(view, "_ctx_menu", None)
    out["menu"] = bool(menu is not None and menu.isVisible())
    if menu is not None:
        menu.hide()
    yield 200
    n = len(win.views)
    extra = win.add_tab(A + "/third")
    yield 1000
    drag(extra, [(0, 150), (150, 0)])            # ↓→ close the tab
    yield 800
    out["closed"] = [len(win.views) == n, extra not in win.views]
'''


def test_mouse_gestures(run_ike, site):
    out = run_ike(GESTURES.replace("__PORT__", str(site)), settings={"mouse_gestures": True}, timeout=150)
    assert out["back"] == "/first" and out["forward"] == "/second"
    assert out["menu"] is True
    assert out["closed"] == [True, True]


def test_gestures_off_by_default(run_ike, site):
    out = run_ike(GESTURES.replace("__PORT__", str(site)).replace(
        '    out["back"] = view.url().path()', '    out["back"] = view.url().path()\n    return'), timeout=120)
    assert out["back"] == "/second"            # nothing happens: the setting is off


BAR = COMMON + r'''
def steps(ike, qapp, out):
    from ike.palette import CommandBar
    win = ike.windows[0]
    win.resize(1200, 800)
    win.show()
    win.activateWindow()
    first = win.current_view()
    yield from load(first, A + "/alpha-page")
    second = win.add_tab(A + "/beta-page")
    yield 1200
    ike.storage.add_bookmark(A + "/gamma", "Gamma bookmark")
    found = {}

    def look():
        bars = [w for w in qapp.topLevelWidgets() if isinstance(w, CommandBar) and w.isVisible()]
        if not bars:
            return
        bar = bars[0]
        found["shown"] = True
        QTest.keyClicks(bar.edit, "alpha")
        found["rows"] = [bar.list.item(i).text().split("\n")[0] for i in range(bar.list.count())]
        QTest.keyClick(bar.edit, Qt.Key.Key_Return)     # to the open tab
    from PyQt6.QtCore import QTimer
    QTimer.singleShot(500, look)
    QTest.keyClick(proxy(second), Qt.Key.Key_F2)
    yield 1200
    out["bar"] = found
    out["current"] = win.current_view() is first

    def look2():
        bars = [w for w in qapp.topLevelWidgets() if isinstance(w, CommandBar) and w.isVisible()]
        if bars:
            QTest.keyClicks(bars[0].edit, "gamma")
            found["rows2"] = [bars[0].list.item(i).text().split("\n")[0] for i in range(bars[0].list.count())]
            QTest.keyClick(bars[0].edit, Qt.Key.Key_Escape)
    QTimer.singleShot(500, look2)
    QTest.keyClick(proxy(win.current_view()), Qt.Key.Key_F2)
    yield 1200
    out["rows2"] = found.get("rows2")
    # commands of the menus are there too
    bar = CommandBar(win)
    out["commands"] = sum(1 for e in bar._entries if e[0] == "Command")
    out["settings"] = sorted(e[1] for e in bar._entries if e[0] == "Settings")
    bar.deleteLater()
'''


def test_command_bar(run_ike, site):
    out = run_ike(BAR.replace("__PORT__", str(site)), timeout=150)
    bar = out["bar"]
    assert bar.get("shown") is True
    assert bar["rows"] and "alpha-page" in bar["rows"][0]
    assert out["current"] is True
    assert out["rows2"] and "Gamma bookmark" in out["rows2"][0]
    assert out["commands"] > 30
    assert "General" in out["settings"] and "Privacy and protection" in out["settings"]


ERRORS = COMMON + r'''
def steps(ike, qapp, out):
    win = ike.windows[0]
    view = win.current_view()
    yield from load(view, "http://127.0.0.1:9/nothing")
    yield 1500
    out["refused"] = json.loads((yield from js(view, "JSON.stringify({t: document.title, "
        "go: (document.querySelector('a.go') || {}).href, url: location.href})")))
    out["address"] = view.url().toString()
    out["urlbar"] = win.urlbar.text()
'''


def test_pages_for_sites_that_cannot_be_reached(run_ike):
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()                                                       # nobody listens there now
    out = run_ike(ERRORS.replace("__PORT__", "0").replace("127.0.0.1:9", "127.0.0.1:%d" % port), timeout=120)
    target = "http://127.0.0.1:%d/nothing" % port
    assert out["refused"]["t"] == "Connection refused", out["refused"]
    assert out["refused"]["go"] == target
    assert out["address"] == target                                 # the address stays the site's
    assert out["urlbar"] == target
