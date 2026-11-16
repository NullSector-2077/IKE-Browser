"""Password manager: the origin a login is saved for and filled on.

origin_of() rules (scheme, host case, default and explicit ports, IPv6), and in
the real browser: a saved login is offered and filled only on its exact origin
(not on another port, another scheme or a subdomain), and after a redirect the
origin of the page at fill time counts. Site names are mapped to a local
server with Chromium's host resolver rules.
"""

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from ice.passwords import origin_of

FORM = (b"<!doctype html><title>login</title><form><input name=user id=u>"
        b"<input type=password name=pw id=p><button>go</button></form>")


def test_origin_rules():
    assert origin_of("https://Site.Example/login?x=1") == "https://site.example"
    assert origin_of("https://site.example:443/") == "https://site.example"
    assert origin_of("http://site.example:80/") == "http://site.example"
    # the default port of the scheme only (before 1.5.2 both 80 and 443 were dropped for both)
    assert origin_of("http://site.example:443/") == "http://site.example:443"
    assert origin_of("https://site.example:80/") == "https://site.example:80"
    assert origin_of("https://site.example:8443/") == "https://site.example:8443"
    assert origin_of("HTTPS://site.example") == "https://site.example"
    assert origin_of("site.example") == "https://site.example"           # CSV import without a scheme
    assert origin_of("http://a.site.example/") != origin_of("http://site.example/")
    assert origin_of("http://[::1]:8080/") == "http://[::1]:8080"
    assert origin_of("http://site.example:99999/") == ""
    assert origin_of("http://site.example:port/") == ""
    assert origin_of("ftp://site.example/") == "" and origin_of("javascript:alert(1)") == ""
    # entries saved by older versions for ordinary addresses keep the same key
    for url in ("https://site.example/", "http://site.example/", "https://site.example:8443/a"):
        assert origin_of(url) == origin_of(origin_of(url))


@pytest.fixture
def site():
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.startswith("/redirect?"):
                self.send_response(302)
                self.send_header("Location", self.path.split("?", 1)[1])
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(FORM)))
            self.end_headers()
            self.wfile.write(FORM)

        def log_message(self, *a):
            pass
    servers = [ThreadingHTTPServer(("127.0.0.1", 0), H) for _ in range(2)]
    for s in servers:
        threading.Thread(target=s.serve_forever, daemon=True).start()
    yield [s.server_address[1] for s in servers]
    for s in servers:
        s.shutdown()


STEPS = r'''
import json
from PyQt6.QtCore import QUrl

def steps(ice, qapp, out):
    pm = ice.passwords
    pm.vault.create("test master")
    for origin, user in SAVED:
        pm.vault.put(origin, user, "pw-" + user)
    v = ice.windows[0].current_view()
    for url in PAGES:
        done = {}
        v.page().loadFinished.connect(lambda ok, done=done: done.setdefault("ok", ok))
        v.load(QUrl(url))
        while "ok" not in done:
            yield 20
        yield 400
        filled = pm.fill(v)
        yield 400
        res = {}
        v.page().runJavaScript("document.getElementById('u').value + '/' + document.getElementById('p').value",
                               0, lambda r, res=res: res.setdefault("r", r))
        while "r" not in res:
            yield 20
        out.setdefault("pages", []).append({"url": v.url().toString(), "origin": pm._origin(v.page()),
                                            "offered": json.loads(pm.logins_json(v.page())),
                                            "filled": filled, "fields": res["r"]})
'''


def test_fill_only_on_exact_origin(run_ice, site):
    port, port2 = site
    saved = [("http://localhost:%d" % port, "main"), ("http://a.localhost:%d" % port, "sub"),
             ("http://localhost:%d" % port2, "otherport"), ("https://localhost:%d" % port, "secure")]
    pages = ["http://LocalHost:%d/login" % port,                 # host case does not matter
             "http://b.localhost:%d/login" % port,               # another subdomain: nothing
             "http://localhost:%d/login" % port2,                # another port: its own login
             "http://c.localhost:%d/redirect?http://a.localhost:%d/login" % (port, port)]
    head = "SAVED = %r\nPAGES = %r\n" % (saved, pages)
    # the local server speaks plain HTTP: no automatic upgrade to HTTPS
    out = run_ice(head + STEPS, settings={"https_only": False}, timeout=120)
    main, other_sub, other_port, redirected = out["pages"]
    assert main["origin"] == "http://localhost:%d" % port
    assert [e["u"] for e in main["offered"]] == ["main"] and main["fields"] == "main/pw-main"
    assert other_sub["offered"] == [] and not other_sub["filled"] and other_sub["fields"] == "/"
    assert [e["u"] for e in other_port["offered"]] == ["otherport"]
    assert other_port["fields"] == "otherport/pw-otherport"
    # the page's origin at fill time: the redirect's target, not the address typed
    assert redirected["url"].startswith("http://a.localhost:%d" % port)
    assert [e["u"] for e in redirected["offered"]] == ["sub"] and redirected["fields"] == "sub/pw-sub"
