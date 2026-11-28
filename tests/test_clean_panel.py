"""1.1.30 (the owner): the broom's panel (cleanpanel.py).

It shows what the site keeps before anything goes, deletes what the user
leaves on (the cookies of the page's trackers too, never those of a site the
user opened himself), and cleans a site by itself when its last tab is
closed: its cookies at once, what it stored before its next page can read it.
"""

import http.server
import threading

import pytest

PAGE = (b"<!doctype html><title>shop</title><p>shop<img src='http://localhost:%d/pixel'>"
        b"<script>window.seen = [localStorage.length, document.cookie];"
        b"document.cookie='a=1';localStorage.setItem('x','1');window.ready = true;</script>")


@pytest.fixture
def shop():
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.startswith("/pixel"):
                body, kind = b"GIF89a", "image/gif"
                self.send_response(200)
                self.send_header("Set-Cookie", "trk=1; Path=/")
            else:
                body, kind = PAGE % self.server.server_address[1], "text/html"
                self.send_response(200)
                self.send_header("Set-Cookie", "session=abc; Path=/")
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1]
    srv.shutdown()


STEPS = r'''
import json
from PyQt6.QtCore import QUrl

URL = "http://127.0.0.1:%d/"

def load(view):
    done = {}
    view.page().loadFinished.connect(lambda ok, d=done: d.setdefault("ok", ok))
    view.load(QUrl(URL))
    while "ok" not in done:
        yield 20
    yield 600

def js(view, code):
    res = {}
    view.page().runJavaScript(code, 0, lambda r, res=res: res.__setitem__("r", r))
    while "r" not in res:
        yield 20
    return res["r"]

def steps(ike, qapp, out):
    win = ike.windows[0]
    view = win.current_view()
    yield from load(view)
    # the panel: what the site keeps
    win.show_clean_panel()
    yield 1200
    menu, panel = win.panel_of("clean")
    out["host"] = panel.host.text()
    out["counted"] = {k: p.text() for k, p in panel.pills.items()}
    out["defaults"] = {k: s.isChecked() for k, s in panel.switches.items()}
    out["names"] = panel.tracker_names.text()
    # clear what is on
    panel._clear()
    for _ in range(80):
        yield 100
        if panel.done.isVisible():
            break
    out["done"] = panel.done.text()
    menu.hide()
    yield 1500
    out["after"] = yield from js(view, "[localStorage.length, document.cookie.indexOf('session') >= 0]")
    # automatic cleaning: on, then the site's last tab closed (another tab stays open)
    yield from load(view)
    win.show_clean_panel()
    yield 600
    panel.auto.setChecked(True)
    panel._auto_changed(True)
    menu.hide()
    out["auto_sites"] = list(ike.config["autoclean_sites"])
    win.add_tab(QUrl("about:blank"))
    yield 300
    win.close_tab(view)
    yield 800
    out["pending"] = list(ike.config["autoclean_pending"])
    store = ike.shields.site_cookies(win.current_view().page().profile(), "127.0.0.1", ever=True)
    out["cookies_left"] = len(store)
    # the next page of the site finds nothing of what it stored, and the site is done
    v2 = win.current_view()
    yield from load(v2)
    out["seen_next"] = yield from js(v2, "window.seen")
    out["pending_after"] = list(ike.config["autoclean_pending"])
'''


def test_the_broom_panel(run_ike, shop):
    out = run_ike(STEPS % shop, settings={"shield_level": "compatibility", "block_third_party_cookies": False},
                  timeout=180)
    assert out["host"] == "127.0.0.1", out
    c = out["counted"]
    assert c["cookies"] == "2" and c["storage"] == "1" and c["permissions"] == "0", c
    assert out["defaults"] == {"cookies": True, "storage": True, "cache": True, "trackers": True,
                               "permissions": False}, out["defaults"]
    assert out["names"].endswith("localhost"), out["names"]          # the other site of the page
    assert out["done"].startswith("✓ ") and "2" in out["done"], out["done"]
    assert out["after"] == [1, True], out["after"]                     # the page loaded again, then set its own
    assert out["auto_sites"] == ["127.0.0.1"]
    assert out["pending"] == ["127.0.0.1"] and out["cookies_left"] == 0, out
    # what it stored was gone before its own script read it; its cookies too
    # (the server sets "session" again with the page itself; the page's own "a" was gone)
    assert out["seen_next"][0] == 0 and "a=1" not in out["seen_next"][1], out["seen_next"]
    assert out["pending_after"] == [], out["pending_after"]
