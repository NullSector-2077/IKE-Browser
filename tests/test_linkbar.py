"""No link preview bar: hovering links must show nothing at the bottom of the
window and must not move or resize the page; the status bar still works for
its own messages (zoom), and links still open."""

import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

SHOTS = os.environ.get("IKE_TEST_SHOTS", "")
PIXEL = (b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,"
         b"\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;")


def _page():
    cells = []
    for i in range(60):
        cells.append('<a class="t" href="/item/%d"><img src="/thumb.gif" width="96" height="54" alt=""></a>' % i)
    links = " ".join('<a class="l" href="/page/%d">link number %d with a long address</a>' % (i, i)
                     for i in range(120))
    return ("<!doctype html><title>links</title><style>body{margin:0;font:14px sans-serif}"
            ".grid{display:grid;grid-template-columns:repeat(10,100px);gap:4px}"
            ".t{display:block;height:54px;background:#888}.l{display:inline-block;margin:2px 6px}"
            "#mark{position:fixed;left:0;bottom:0;width:10px;height:10px;background:red}</style>"
            "<div class=grid>%s</div><p>%s</p><div id=mark></div>"
            "<script>window.sizes=[];addEventListener('resize',function(){sizes.push(innerHeight)});</script>"
            % ("".join(cells), links)).encode()


@pytest.fixture
def site():
    page = _page()

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/thumb.gif":
                body, kind = PIXEL, "image/gif"
            elif self.path == "/":
                body, kind = page, "text/html"
            else:
                body, kind = ("<!doctype html><title>target %s</title>ok" % self.path).encode(), "text/html"
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1]
    srv.shutdown()


STEPS = r'''
import os
from PyQt6.QtCore import QCoreApplication, QEvent, QPointF, Qt, QUrl
from PyQt6.QtGui import QMouseEvent

PORT = %d

def move(v, x, y):
    t = v.focusProxy() or v
    QCoreApplication.sendEvent(t, QMouseEvent(QEvent.Type.MouseMove, QPointF(x, y), t.mapToGlobal(QPointF(x, y)),
                                              Qt.MouseButton.NoButton, Qt.MouseButton.NoButton,
                                              Qt.KeyboardModifier.NoModifier))

def click(v, x, y):
    t = v.focusProxy() or v
    for et, b in ((QEvent.Type.MouseButtonPress, Qt.MouseButton.LeftButton),
                  (QEvent.Type.MouseButtonRelease, Qt.MouseButton.NoButton)):
        QCoreApplication.sendEvent(t, QMouseEvent(et, QPointF(x, y), t.mapToGlobal(QPointF(x, y)),
                                                  Qt.MouseButton.LeftButton, b, Qt.KeyboardModifier.NoModifier))

def snapshot(win, v):
    bar = win.statusBar()
    return [bar.isVisible(), bar.currentMessage(), v.width(), v.height(), v.mapTo(win, v.rect().topLeft()).x(),
            v.mapTo(win, v.rect().topLeft()).y(), win.width(), win.height(), win.stack.height()]

def steps(ike, qapp, out):
    win = ike.windows[0]
    win.resize(1200, 800)
    v = win.current_view()
    done = {}
    v.page().loadFinished.connect(lambda ok: done.setdefault("ok", ok))
    v.load(QUrl("http://127.0.0.1:%%d/" %% PORT))
    while "ok" not in done:
        yield 20
    yield 500
    v.page().runJavaScript("sizes.length = 0")
    yield 100
    hovered = []
    v.page().linkHovered.connect(hovered.append)      # what the engine reports, to prove the hovering is real
    out["connected"] = "_hovered" in dir(win)
    # without the menu bar (1.1.9) the test's pointer starts on the Back button: its tip goes
    # into the (hidden) status bar. That is not a link: start from an empty message.
    win.statusBar().clearMessage()
    yield 100
    start = snapshot(win, v)
    out["start"] = start
    seen = []
    # across the thumbnails, then across the text links
    for y in (20, 80, 140, 200, 420, 440, 470, 500):
        for x in range(10, 1000, 45):
            move(v, x, y)
            yield 12
            now = snapshot(win, v)
            if now != start and now not in seen:
                seen.append(now)
    move(v, 1100, 700)
    yield 200
    out["hovered"] = len(set(u for u in hovered if u))
    out["kinds"] = sorted(set(u.split("/")[3] for u in hovered if u))
    out["changes"] = seen
    out["end"] = snapshot(win, v)
    res = {}
    v.page().runJavaScript("JSON.stringify([sizes, innerHeight, document.getElementById('mark').getBoundingClientRect().bottom])",
                           lambda r: res.setdefault("r", r))
    while "r" not in res:
        yield 20
    out["page"] = res["r"]
    if os.environ.get("IKE_TEST_SHOTS"):
        move(v, 55, 80)
        yield 300
        win.grab().save(os.path.join(os.environ["IKE_TEST_SHOTS"], "hover-no-linkbar.png"))
    # the zoom is told in a pill over the page (1.1.7)
    win.zoom(1)
    yield 150
    out["zoom"] = [win.toast_pill.isVisible(), win.toast_pill.text]
    yield 1900
    out["zoom_gone"] = [win.toast_pill.isVisible(), win.statusBar().isVisible()]
    win.zoom(0)
    yield 1900
    # links still open
    click(v, 55, 30)
    for _ in range(100):
        if "/item/" in v.url().toString():
            break
        yield 30
    yield 200
    out["opened"] = [v.url().path(), v.title()]
'''


def test_hovering_links_shows_no_bar_and_moves_nothing(run_ike, site):
    out = run_ike(STEPS % site, timeout=150, env={"IKE_TEST_SHOTS": SHOTS})
    assert out["connected"] is False
    # the mouse really crossed many links of both kinds
    assert out["hovered"] >= 15 and out["kinds"] == ["item", "page"], (out["hovered"], out["kinds"])
    assert out["start"][0] is False and out["start"][1] == ""
    assert out["changes"] == [], out["changes"]
    assert out["end"] == out["start"]
    import json
    sizes, inner, mark = json.loads(out["page"])
    assert sizes == [] and abs(mark - inner) < 0.5, out["page"]
    assert out["zoom"][0] is True and out["zoom"][1].startswith("Zoom")
    assert out["zoom_gone"] == [False, False]
    assert out["opened"][0].startswith("/item/") and out["opened"][1].startswith("target")
