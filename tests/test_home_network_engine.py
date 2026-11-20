"""The engine's own home-network protection, with I.K.E.'s per-site "Allow"
(1.1.19, the owner's decision; the way Chrome, Brave and Firefox do it).

Qt WebEngine 6.12 has Chromium's Local Network Access, off and without a
per-site permission (Qt answers "denied"). I.K.E. turns it on: a public page
cannot reach this computer or the home network even through a public name
that points there (the check is on the real address, at connection time, so
DNS rebinding too). When it stops something, I.K.E. finds which host (its own
lookup, never the page's word) and shows the usual "Allow for this site" bar;
the choice is kept and given to the engine at the next start (one restart the
first time a device is allowed), and I.K.E.'s own check keeps every other site
away from that device's address.

SIMULATION: --host-resolver-rules makes pub.example.test and cdn.example.test
resolve to 127.0.0.1 inside the engine; the page is served with
Content-Security-Policy treat-as-public-address (a public page); I.K.E.'s own
lookup is answered the same way.
"""

import http.server
import sys
import threading

import pytest
from conftest import APP

sys.path.insert(0, str(APP))
from ike import app as ike_app  # noqa: E402
from ike.shields import endpoint  # noqa: E402


@pytest.fixture
def home():
    seen = []

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append(self.headers.get("Host", "").split(":")[0] + " " + self.path)
            if self.path.startswith("/pub"):
                p = self.server.server_address[1]
                body = ("<title>pub</title><img src='http://cdn.example.test:%d/dns.png'>"
                        "<script>fetch('http://cdn.example.test:%d/fetch', {mode: 'no-cors'})"
                        ".catch(function () {});</script>" % (p, p)).encode()
                self.send_response(200)
                self.send_header("Content-Security-Policy", "treat-as-public-address")
                self.send_header("Content-Type", "text/html")
            else:
                body = b"ok"
                self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1], seen
    srv.shutdown()


STEPS = r'''
PORT = %d
CLICK = %r

def steps(ike, qapp, out):
    from PyQt6.QtCore import QUrl
    from PyQt6.QtNetwork import QHostAddress, QHostInfo
    def lookup(name, callback):              # I.K.E.'s own lookup: the same answer as the engine's
        info = QHostInfo()
        info.setHostName(name)
        if name.endswith("example.test"):
            info.setAddresses([QHostAddress("127.0.0.1")])
        callback(info)
    QHostInfo.lookupHost = staticmethod(lookup)
    restarts = []
    ike.restart = lambda: restarts.append(1)
    win = ike.windows[0]
    v = win.current_view()
    yield 800
    v.load(QUrl("http://pub.example.test:%%d/pub" %% PORT))
    yield 4000
    out["bar"] = [win.secure_bar.isVisible(), win.secure_bar.text.text()]
    n = getattr(v, "secure_notice", None) or {}
    out["targets"] = n.get("targets")
    out["flags"] = __import__("os").environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
    if CLICK:
        win.secure_bar.go.click()
        yield 800
        out["restarts"] = len(restarts)
        out["lan_sites"] = ike.config["lan_sites"]
'''

FLAGS = '--no-sandbox "--host-resolver-rules=MAP pub.example.test 127.0.0.1, MAP cdn.example.test 127.0.0.1"'
ENV = {"QTWEBENGINE_CHROMIUM_FLAGS": FLAGS, "http_proxy": "", "https_proxy": "", "HTTP_PROXY": "",
       "HTTPS_PROXY": "", "all_proxy": "", "ALL_PROXY": "", "no_proxy": "*", "NO_PROXY": "*"}


def test_a_public_name_that_points_home_is_stopped_and_can_be_allowed(run_ike, home):
    port, seen = home
    out = run_ike(STEPS % (port, True), settings={"https_only": False}, env=ENV, timeout=90)
    assert "LocalNetworkAccessChecks:LocalNetworkAccessChecksWarn/false" in out["flags"], out["flags"]
    assert "pub.example.test /pub" in seen, seen                          # the public page itself loaded
    assert not [x for x in seen if x.endswith(("/dns.png", "/fetch"))], seen    # nothing reached home
    assert out["bar"][0] is True and "example.test tried to open" in out["bar"][1], out
    want = {"cdn.example.test:%d" % port, "127.0.0.1:%d" % port}
    assert want <= set(out["targets"] or []), out["targets"]
    assert out["restarts"] == 1, out                                      # the engine learns it at start
    assert want <= set(out["lan_sites"].get("example.test", [])), out["lan_sites"]
    # the next start: the engine lets this device through for that site
    seen.clear()
    out = run_ike(STEPS % (port, False), settings={"https_only": False}, env=ENV, keep_profile=True,
                  timeout=90)
    assert "--ip-address-space-overrides=127.0.0.1:%d=public" % port in out["flags"], out["flags"]
    assert [x for x in seen if x.endswith("/dns.png")], seen


def test_only_addresses_reach_the_engine():
    cfg = {"lan_sites": {"a.test": ["127.0.0.1:631", "fritz.box:80", "[::1]:8080", "x y:1", "bad"],
                         "b.test": "not a list"}}
    assert ike_app.lan_overrides(cfg) == ["127.0.0.1:631=public", "[::1]:8080=public"]
    assert endpoint("http://Router.LAN./x") == "router.lan:80"
    assert endpoint("https://[::1]/") == "[::1]:443" and endpoint("ws://10.0.0.2:81/") == "10.0.0.2:81"


def test_inherited_overrides_and_a_disabled_protection_are_dropped():
    out, named = ike_app._engine_safety(["--ip-address-space-overrides=10.0.0.1:80=public",
                                         "--disable-features=LocalNetworkAccessChecks"], env={}, allowed=False)
    assert out == [] and len(named) == 2, (out, named)
