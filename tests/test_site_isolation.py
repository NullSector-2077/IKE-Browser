"""Every site in its own process (1.1.18, security audit F1; owner's decision).

Qt WebEngine leaves Chromium's Site Isolation off: a frame of another site
shared its page's process (chrome://process-internals said "Site Isolation
mode: Disabled", no out-of-process frame), so one bug in the engine let a
page read the other site. I.K.E. now asks for --site-per-process, as Chrome
and Brave always do; a user who added --disable-site-isolation-trials himself
is followed.
"""

import http.server
import re
import threading

import pytest


@pytest.fixture
def two_sites():
    servers = []

    def serve(host, body):
        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                b = body.replace(b"PORT", str(servers[0].server_address[1]).encode()) if servers else body
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)

            def log_message(self, *a):
                pass
        srv = http.server.ThreadingHTTPServer((host, 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        return srv
    servers.append(serve("127.0.0.2", b"<title>B</title><p>site b</p>"))
    top = serve("127.0.0.1", b"<title>A</title><iframe id=f src='http://127.0.0.2:PORT/'></iframe>")
    servers.append(top)
    yield top.server_address[1]
    for s in servers:
        s.shutdown()


STEPS = r'''
import json
from PyQt6.QtCore import QUrl

def js(view, code):
    got = {}
    view.page().runJavaScript(code, 0, lambda r: got.setdefault("r", r))
    while "r" not in got:
        yield 20
    return got["r"]

CLICK = """(function (n) { var el = [].find.call(document.querySelectorAll('*'), function (e) {
  return e.children.length == 0 && e.textContent.trim() == n; }); if (el) { el.click(); return true; } return false; })(%%s)"""

def steps(ike, qapp, out):
    win = ike.windows[0]
    v = win.current_view()
    v.load(QUrl("http://127.0.0.1:%d/"))
    yield 4000
    out["title"] = v.title()
    pi = win.add_tab(QUrl("chrome://process-internals"))
    yield 3000
    for name, key in (("Site Isolation", "general"), ("Frame Trees", "frames")):
        yield from js(pi, CLICK %% json.dumps(name))
        yield 2500
        out[key] = (yield from js(pi, "document.body.innerText")) or ""
'''


def _mode(general):
    line = [x for x in general.splitlines() if "Site Isolation mode" in x]
    return line[0] if line else general[-400:]


def test_each_site_gets_its_own_process(run_ike, two_sites):
    out = run_ike(STEPS % two_sites, timeout=90)
    assert out["title"] == "A", out["title"]
    assert "Site Per Process" in _mode(out["general"]), _mode(out["general"])
    oopif = re.search(r"OOPIF Count:?\s+(\d+)", out["frames"])
    assert oopif and int(oopif.group(1)) >= 1, out["frames"][-1500:]     # the other site's frame: its own process


def test_a_user_who_turned_it_off_is_followed(run_ike, two_sites):
    out = run_ike(STEPS % two_sites, timeout=90,
                  env={"QTWEBENGINE_CHROMIUM_FLAGS": "--no-sandbox --disable-site-isolation-trials"})
    assert "Site Per Process" not in _mode(out["general"]), _mode(out["general"])
