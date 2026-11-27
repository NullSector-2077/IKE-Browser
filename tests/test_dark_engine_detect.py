"""The I.K.E. Dark Engine leaves alone a page that is dark already, also when the
page does not say so (no color-scheme, no data-theme, not in Dark Reader's
lists), and darkens a light page that only has dark parts. Real engine, local
pages."""

import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from test_security import JS

TEXT = "<p id='t'>" + "Some text of the page. " * 30 + "</p>"
DARK_CSS = ("body{background:#121212;color:#ddd;margin:0;min-height:100vh}main{padding:20px}"
            ".card{background:#1e1e1e;color:#eee;padding:12px;margin:8px 0}a{color:#8ab4f8}")
PAGES = {
    # dark by its own style sheet, nothing declared
    "/dark-plain": ("<!doctype html><title>dark</title><style>%s</style><main><div class='card'>Card</div>%s"
                    "<a href='#'>link</a></main>" % (DARK_CSS, TEXT), "text/html"),
    # the same, its style sheet arriving late (the page is judged once it is there)
    "/dark-late": ("<!doctype html><title>dark late</title><link rel='stylesheet' href='/slow-dark.css'>"
                   "<main><div class='card'>Card</div>%s</main>" % TEXT, "text/html"),
    "/slow-dark.css": (DARK_CSS, "text/css"),
    # a light page with a dark header: darkened
    "/light-header": ("<!doctype html><title>light</title><style>body{background:#fff;color:#222;margin:0}"
                      "header{background:#222;color:#fff;height:90px}</style><header>Site</header><main>%s</main>"
                      % TEXT, "text/html"),
    # a dark page frame with large white content cards: darkened (the reader sees white)
    "/dark-light-cards": ("<!doctype html><title>cards</title><style>body{background:#111;color:#eee;margin:0}"
                          ".sheet{background:#fff;color:#222;margin:30px;min-height:90vh}</style>"
                          "<div class='sheet'>%s</div>" % TEXT, "text/html"),
    # dark text on a dark background is not a dark theme (a broken page is not left as it is)
    "/plain-light": ("<!doctype html><title>plain</title><style>body{background:#fafafa;color:#333}</style>%s"
                     % TEXT, "text/html"),
}


@pytest.fixture
def site():
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            path = self.path.split("?")[0]
            body, ctype = PAGES.get(path, (None, None))
            if body is None:
                self.send_error(404)
                return
            if path == "/slow-dark.css":
                time.sleep(0.6)
            data = body.encode()
            self.send_response(200)
            self.send_header("Content-Type", ctype + "; charset=utf-8")
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
READ = """JSON.stringify({
  body: getComputedStyle(document.body).backgroundColor,
  text: getComputedStyle(document.getElementById('t')).color,
  mapped: !!document.querySelector('style.ike-de') || document.adoptedStyleSheets.length > 0})"""

def steps(ike, qapp, out):
    view = ike.windows[0].current_view()
    yield 500
    for name in ("dark-plain", "dark-late", "light-header", "dark-light-cards", "plain-light"):
        yield from load(view, SITE + "/" + name)
        yield 2500
        out[name] = json.loads((yield from js(view, READ)))
'''


def test_a_page_dark_already_is_left_alone(run_ike, site):
    out = run_ike(STEPS.replace("__SITE__", site), settings={
        "dark_mode": "on", "dark_engine": "reader", "dark_engine_experiment": True}, timeout=150)
    for name in ("dark-plain", "dark-late"):
        p = out[name]
        assert p["body"] == "rgb(18, 18, 18)" and p["text"] == "rgb(221, 221, 221)", (name, p)
        assert p["mapped"] is False, (name, p)
    for name in ("light-header", "dark-light-cards", "plain-light"):
        p = out[name]
        assert p["mapped"] is True, (name, p)
    # the light parts were made dark, their text light
    assert out["light-header"]["body"] != "rgb(255, 255, 255)", out["light-header"]
    assert out["plain-light"]["body"] != "rgb(250, 250, 250)", out["plain-light"]
