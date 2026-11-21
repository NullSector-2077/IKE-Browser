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


COVER = r'''
def steps(ike, qapp, out):
    import json
    from PyQt6.QtCore import QUrl
    win = ike.windows[0]
    yield 1000
    v = win.current_view()
    v.load(QUrl("http://127.0.0.1:%d/cover"))
    yield 2500
    got = {}
    v.page().runJavaScript("JSON.stringify(window.__cover || null)", 0, lambda r: got.setdefault("r", r))
    while "r" not in got:
        yield 20
    out["r"] = json.loads(got["r"])
'''


@pytest.fixture
def cover_site():
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            # an inline script of the page, at the very start: the cover is there
            body = (b"<!doctype html><html><head><script>"
                    b"var s = [].slice.call(document.querySelectorAll('style')).filter(function (e) {"
                    b" return e.textContent.indexOf('html{background') === 0; })[0];"
                    b"window.__cover = { where: s ? s.parentNode.nodeName : 'none', text: s ? s.textContent : '' };"
                    b"</script><title>p</title></head><body><p>a white page</body></html>")
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


def test_the_dark_cover_does_not_restyle_the_page(run_ike, cover_site):
    """Dark Reader's cover against the white flash was a colour on <html>
    and the first child of <html>: taking it away restyled the whole page
    (about a third of Dark Reader's cost on Speedometer's Lit pages). Now it
    is an image, in <head>: the colour of <html> stays the page's own."""
    out = run_ike(COVER % cover_site, settings={"dark_mode": "on", "dark_engine": "reader",
                                                "https_only": False}, timeout=60)
    r = out["r"]
    assert r and r["where"] == "HEAD", r
    assert "background-image" in r["text"] and "background:" not in r["text"] \
        and "background-color" not in r["text"], r                # no colour of <html> to take away
