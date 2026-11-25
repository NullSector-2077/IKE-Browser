"""The I.K.E. Dark Engine experiment (ike/darkengine.py) behind its hidden
setting: off by default (Dark Reader as before); on, it takes Dark Reader's
place at the levels Off to Balanced, and at Strict and Maximum only
Chromium's own dark mode darkens the page (no script)."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from test_security import JS

PAGE = ("<!doctype html><html><head><title>light</title><style>body{background:#fff;color:#111}"
        ".box{background:#f4f4f4;color:#222;height:80px}</style></head><body><main><h1>Light</h1>"
        "<div id='a' class='box'>Text in a box</div><p>Text.</p></main></body></html>")


@pytest.fixture
def site():
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            data = PAGE.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):
            pass
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield "http://127.0.0.1:%d" % srv.server_address[1]
    srv.shutdown()


STEPS = JS + r'''
SITE = "__SITE__"

def jsw(view, code):
    box = {}
    view.page().runJavaScript(code, 1, lambda r: box.setdefault("r", r))
    for _ in range(200):
        if "r" in box:
            break
        yield 20
    return box.get("r")

def steps(ike, qapp, out):
    from PyQt6.QtWebEngineCore import QWebEngineSettings
    view = ike.windows[0].current_view()
    yield 500
    yield from load(view, SITE + "/page")
    yield 2500
    out["page"] = json.loads((yield from js(view, """JSON.stringify({
      dr: document.querySelectorAll('style.darkreader').length,
      body: getComputedStyle(document.body).backgroundColor,
      box: getComputedStyle(document.getElementById('a')).backgroundColor})""")))
    out["engine"] = (yield from jsw(view, "JSON.stringify(window.__ikeDEStats || null)"))
    out["native"] = view.page().settings().testAttribute(QWebEngineSettings.WebAttribute.ForceDarkMode)
    out["scripts"] = sorted({s.name().split(":")[0] for s in view.page().profile().scripts().toList()
                             if s.name().startswith("ike-dark")})
'''


def lightness(css):
    import re
    m = re.match(r"rgba?\((\d+), (\d+), (\d+)", css or "")
    r, g, b = (int(x) for x in m.groups())
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255


def run(run_ike, site, **settings):
    base = {"dark_mode": "on", "dark_engine": "reader"}
    base.update(settings)
    return run_ike(STEPS.replace("__SITE__", site), settings=base, timeout=150)


def test_off_by_default_dark_reader_as_before(run_ike, site):
    out = run(run_ike, site)
    assert out["page"]["dr"] > 0 and out["engine"] == "null" and out["native"] is False, out
    assert "ike-dark-engine-x" not in out["scripts"], out


@pytest.mark.parametrize("level", ["off", "compatibility", "balanced"])
def test_on_it_replaces_dark_reader(run_ike, site, level):
    out = run(run_ike, site, dark_engine_experiment=True, shield_level=level)
    p = out["page"]
    assert p["dr"] == 0 and out["native"] is False, out
    assert json.loads(out["engine"])["sheets"] >= 1, out
    assert lightness(p["body"]) < 0.3 and lightness(p["box"]) < 0.3, out
    assert "ike-dark-engine" not in out["scripts"] and "ike-dark-proxy" not in out["scripts"], out


@pytest.mark.parametrize("level", ["strict", "maximum"])
def test_never_at_strict_and_maximum(run_ike, site, level):
    out = run(run_ike, site, dark_engine_experiment=True, shield_level=level)
    assert out["page"]["dr"] == 0 and out["engine"] == "null", out
    assert out["native"] is True, out
    assert not [s for s in out["scripts"] if s.startswith("ike-dark-engine")], out
