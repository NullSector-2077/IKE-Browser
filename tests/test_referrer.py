"""Referrer trimming (1.1.18, independent review).

At Balanced and above a cross-site request's Referer is cut to the origin of
the page. Until 1.1.18 the shield added a Referer even where the page's
referrer policy sends none (no-referrer, same-origin): the engine then
cancelled the request, so pictures and scripts of other sites failed on those
pages with the shield on and loaded with it off. Now only a Referer the
request carries is cut, to its own origin.
"""
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PNG = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082")
POLICIES = ("", "no-referrer", "same-origin", "unsafe-url")

STEPS = r'''
from PyQt6.QtCore import QUrl

def steps(ike, qapp, out):
    v = ike.windows[0].current_view()
    yield 500
    for pol in POLICIES:
        done = {}
        v.page().loadFinished.connect(lambda ok, done=done: done.setdefault("ok", ok))
        v.load(QUrl(BASE + "/page/full/path?" + pol))
        while "ok" not in done:
            yield 20
        yield 800
    out["done"] = True
'''


def test_cross_site_requests_keep_the_pages_referrer_policy(run_ike):
    seen = {}

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.startswith("/page"):
                pol = self.path.split("?", 1)[1] if "?" in self.path else ""
                meta = '<meta name="referrer" content="%s">' % pol if pol else ""
                body = ('<!doctype html>%s<img src="http://localhost:%d/img.png?%s">'
                        % (meta, self.server.server_address[1], pol)).encode()
                kind = "text/html"
            else:
                seen[self.path.split("?", 1)[1]] = self.headers.get("Referer")
                body, kind = PNG, "image/png"
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:%d" % srv.server_address[1]
    try:
        out = run_ike("BASE = %r\nPOLICIES = %r\n" % (base, POLICIES) + STEPS,
                      settings={"shield_level": "balanced", "trim_referrer": True})
    finally:
        srv.shutdown()
    assert out.get("done"), out
    origin = base + "/"
    # every picture arrived (none cancelled), with no more than the page's own policy allows
    assert set(seen) == set(POLICIES), seen
    assert seen[""] == origin, seen                      # the engine's default: the origin
    assert seen["no-referrer"] is None and seen["same-origin"] is None, seen
    assert seen["unsafe-url"] == origin, seen            # the full address cut to the origin


# --- two more request rules of the independent review (1.1.18) --------------------
FAKE = r'''
from PyQt6.QtCore import QUrl
from PyQt6.QtWebEngineCore import QWebEngineUrlRequestInfo as I

class Fake:
    """What the request interceptor reads of a request, without a network."""
    def __init__(self, url, rtype, first="", initiator=""):
        self.url, self.rtype = QUrl(url), rtype
        self.first, self.init = QUrl(first), QUrl(initiator)
        self.redirected = self.blocked = None
        self.headers = {}
    def requestUrl(self): return self.url
    def resourceType(self): return self.rtype
    def firstPartyUrl(self): return self.first
    def initiator(self): return self.init
    def requestMethod(self): return b"GET"
    def httpHeaders(self): return {}
    def redirect(self, u): self.redirected = u.toString()
    def block(self, b): self.blocked = b
    def setHttpHeader(self, k, v): self.headers[bytes(k)] = bytes(v)

def steps(ike, qapp, out):
    yield 300
    ike.config["custom_filters"] = "||tracker.example^"
    ike.blocker.load()
    yield 300
    while ike.blocker.building:
        yield 50
    icp = ike.shields.interceptor
    # an http address of a sensitive service is still made secure
    f = Fake("http://myaccount.google.com/", I.ResourceType.ResourceTypeMainFrame)
    icp.interceptRequest(f)
    out["upgrade"] = f.redirected
    # a tracker's own request from a page of the tracker's site goes the free way...
    g = Fake("https://www.tracker.example/pixel.gif", I.ResourceType.ResourceTypeImage,
             first="https://tracker.example/frame")
    icp.interceptRequest(g)
    out["page"] = g.blocked
    # ...but not one of its service worker, which has no page (no first party)
    h = Fake("https://www.tracker.example/pixel.gif", I.ResourceType.ResourceTypeImage,
             initiator="https://tracker.example")
    icp.interceptRequest(h)
    out["worker"] = h.blocked
'''


def test_sensitive_services_upgraded_and_no_free_way_without_a_page(run_ike):
    out = run_ike(FAKE, settings={"shield_level": "balanced", "https_only": True})
    assert out["upgrade"] == "https://myaccount.google.com/", out
    assert out["page"] is None, out                  # Balanced: a site's own request, the free way
    assert out["worker"] is True, out                # no page known: checked against the lists
