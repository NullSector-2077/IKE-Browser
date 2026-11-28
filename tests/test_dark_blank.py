"""No white while dark mode is on for every site (1.1.19, the owner's request):
an empty page (a window a site opens, before its address loads) is dark, from
the first moment and after a page; with dark mode off it stays white."""

import http.server
import threading

import pytest


@pytest.fixture
def site():
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = b"<title>p</title><p>a page with a white background"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
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
def steps(ike, qapp, out):
    from PyQt6.QtCore import QUrl
    win = ike.windows[0]
    yield 1000
    def colour(v):
        img = v.grab().toImage()
        return img.pixelColor(img.width() // 2, img.height() // 2).lightness()
    v = win.add_tab(QUrl("about:blank"))
    yield 1200
    out["new"] = colour(v)
    v.load(QUrl("http://127.0.0.1:%d/"))
    yield 1500
    out["page"] = colour(v)
    v.load(QUrl("about:blank"))
    yield 1200
    out["after"] = colour(v)
'''


def test_an_empty_page_is_dark_in_dark_mode(run_ike, site):
    out = run_ike(STEPS % site, settings={"dark_mode": "on", "https_only": False}, timeout=60)
    assert out["new"] < 60 and out["page"] < 60 and out["after"] < 60, out


def test_an_empty_page_stays_white_without_dark_mode(run_ike, site):
    out = run_ike(STEPS % site, settings={"dark_mode": "off", "https_only": False}, timeout=60)
    assert out["new"] > 200 and out["page"] > 200 and out["after"] > 200, out
