"""Full screen and mouse lock: both stay automatic (games, videos), with a
notice naming the site, Esc ending both, and nothing for a tab that is not
the one in view. Real clicks and keys are sent to the page, so the engine's
own rules (user activation) apply as on a desktop.
"""

import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

SHOTS = os.environ.get("IKE_TEST_SHOTS", "")   # folder for screenshots, optional

PAGE = b"""<!doctype html><html><body style="margin:0">
<div id="d" style="width:600px;height:400px;background:#ccc"></div>
<video id="v" width="320" height="180" style="background:#000"></video>
<script>
window.log = [];
document.addEventListener('pointerlockchange', function () { log.push('lock:' + !!document.pointerLockElement); });
document.addEventListener('pointerlockerror', function () { log.push('lockerror'); });
document.addEventListener('fullscreenchange', function () { log.push('fs:' + !!document.fullscreenElement); });
window.want = 'lock';
d.addEventListener('click', function () {
  if (want === 'fs' || want === 'both') document.documentElement.requestFullscreen().catch(function () { log.push('fserror'); });
  if (want === 'video') v.requestFullscreen().catch(function () { log.push('fserror'); });
  if (want === 'lock' || want === 'both') { var p = d.requestPointerLock(); if (p && p.catch) p.catch(function () {}); }
});
</script></body></html>"""


@pytest.fixture
def site():
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(PAGE)))
            self.end_headers()
            self.wfile.write(PAGE)

        def log_message(self, *a):
            pass
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1]
    srv.shutdown()


HELPERS = r'''
import json
from PyQt6.QtCore import QCoreApplication, QEvent, QPointF, Qt, QUrl
from PyQt6.QtGui import QKeyEvent, QMouseEvent

def click(v, x=50, y=50):
    t = v.focusProxy() or v
    for et, b in ((QEvent.Type.MouseButtonPress, Qt.MouseButton.LeftButton),
                  (QEvent.Type.MouseButtonRelease, Qt.MouseButton.NoButton)):
        QCoreApplication.sendEvent(t, QMouseEvent(et, QPointF(x, y), QPointF(x, y), Qt.MouseButton.LeftButton,
                                                  b, Qt.KeyboardModifier.NoModifier))

def escape(v):
    # like a real key press: the window's shortcuts first, then the page
    t = v.focusProxy() or v
    from PyQt6.QtTest import QTest
    QTest.keyClick(t, Qt.Key.Key_Escape)

def load(v, url):
    done = {}
    v.page().loadFinished.connect(lambda ok, done=done: done.setdefault("ok", ok))
    v.load(QUrl(url))
    while "ok" not in done:
        yield 20
    yield 300

def state(v, out, key):
    res = {}
    v.page().runJavaScript("JSON.stringify({log: log, fs: !!document.fullscreenElement, "
                           "fsel: document.fullscreenElement ? document.fullscreenElement.id || 'html' : null, "
                           "lock: !!document.pointerLockElement})", 0, lambda r: res.setdefault("r", r))
    while "r" not in res:
        yield 20
    w = v.window()
    notice = getattr(w, "_notice", None)
    d = json.loads(res["r"])
    d["window_fs"] = bool(w._fullscreen_page)
    d["notice"] = notice.text() if notice is not None and notice.isVisible() else None
    if notice is not None and notice.isVisible():
        g = notice.geometry()
        d["notice_inside"] = w.rect().contains(g)
        import os
        if os.environ.get("IKE_TEST_SHOTS"):
            w.grab().save(os.path.join(os.environ["IKE_TEST_SHOTS"], "notike-%s.png" % key))
    out[key] = d
'''


def test_fullscreen_and_mouse_lock(run_ice, site):
    url = "http://127.0.0.1:%d/" % site
    origin = "http://127.0.0.1:%d" % site
    steps = HELPERS + r'''
def steps(ice, qapp, out):
    w = ike.windows[0]
    v = w.current_view()
    yield from load(v, URL)
    v.setFocus()
    yield 300
    # mouse lock alone: granted, notice with the origin, Esc frees the pointer
    click(v)
    yield 600
    yield from state(v, out, "locked")
    escape(v)
    yield 500
    yield from state(v, out, "unlocked")
    # full screen: granted, notice, Esc leaves it
    v.page().runJavaScript("want = 'fs'", 0)
    yield 200
    click(v)
    yield 900
    yield from state(v, out, "fullscreen")
    escape(v)
    yield 900
    yield from state(v, out, "fs_exited")
    # both at once (a game): one Esc ends both
    v.page().runJavaScript("want = 'both'", 0)
    yield 200
    click(v)
    yield 900
    yield from state(v, out, "both")
    escape(v)
    yield 900
    yield from state(v, out, "both_exited")
    # a video in full screen still works; the notice goes away by itself
    v.page().runJavaScript("want = 'video'", 0)
    yield 200
    click(v)
    yield 900
    yield from state(v, out, "video")
    yield 4500
    yield from state(v, out, "video_later")
    escape(v)
    yield 900
    yield from state(v, out, "video_exited")
'''.replace("URL", repr(url))
    out = run_ice(steps, timeout=120, env={"IKE_TEST_SHOTS": SHOTS})
    assert out["locked"]["lock"] and not out["locked"]["window_fs"]
    assert out["locked"]["notice"] == "%s controls the mouse pointer — press Esc to show the cursor" % origin
    assert out["locked"]["notice_inside"]
    assert not out["unlocked"]["lock"] and out["unlocked"]["notice"] is None
    assert out["fullscreen"]["fs"] and out["fullscreen"]["window_fs"]
    assert out["fullscreen"]["notice"] == "%s is full screen — press Esc to exit" % origin
    assert not out["fs_exited"]["fs"] and not out["fs_exited"]["window_fs"]
    assert out["fs_exited"]["notice"] is None
    assert out["both"]["fs"] and out["both"]["lock"] and out["both"]["window_fs"]
    assert not out["both_exited"]["fs"] and not out["both_exited"]["lock"]
    assert not out["both_exited"]["window_fs"]
    assert out["video"]["fsel"] == "v" and out["video"]["window_fs"] and out["video"]["notice"]
    assert out["video_later"]["fs"] and out["video_later"]["notice"] is None
    assert not out["video_exited"]["fs"] and not out["video_exited"]["window_fs"]


def test_background_tab_refused(run_ice, site):
    """A tab that was clicked (so it may ask) but is no longer in view."""
    url = "http://127.0.0.1:%d/" % site
    steps = HELPERS + r'''
def steps(ice, qapp, out):
    w = ike.windows[0]
    a = w.current_view()
    yield from load(a, URL)
    a.page().runJavaScript("want = 'none'", 0)
    a.setFocus()
    yield 200
    click(a)                              # user activation for tab A
    yield 300
    b = w.add_tab(QUrl(URL))
    w.set_current(b)
    yield 800
    out["a_visible"] = a.page().visible_tab()
    a.page().runJavaScript("document.documentElement.requestFullscreen().catch(function () { log.push('fserror'); });"
                           "var p = document.getElementById('d').requestPointerLock();"
                           "if (p && p.catch) p.catch(function () { log.push('lockerror'); });", 0)
    yield 1000
    yield from state(a, out, "a")
    out["window_fs"] = w._fullscreen_page
    # the tab in view still can
    b.setFocus()
    yield 200
    click(b)
    yield 600
    yield from state(b, out, "b")
'''.replace("URL", repr(url))
    out = run_ice(steps, timeout=120)
    assert out["a_visible"] is False
    assert not out["a"]["fs"] and not out["a"]["lock"] and not out["window_fs"]
    assert out["a"]["notice"] is None
    assert out["b"]["lock"]
