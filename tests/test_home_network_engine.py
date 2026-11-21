"""The engine's own home-network protection (Chromium's Local Network Access,
turned on by I.K.E. in 1.1.19): a public page cannot reach this computer or
the home network, also through a public name that points there (DNS
rebinding), because the engine checks the real address when it connects.

There are no per-site exceptions. The engine has only one way to let a device
through, an address:port given at start for every site at once: tried on
2026-11-20, an "exception" for one site let any other public site reach the
same device through its own name. So I.K.E. does not use it, and drops it
when inherited.

SIMULATION (no real internet, no real home network):
- "the internet": a server on 127.0.0.1 declared public for the engine
  (--ip-address-space-overrides, kept here with IKE_ALLOW_UNSAFE_ENGINE=1);
  www.public.test and www.other.test are two public sites on it;
- "the home network": another server on 127.0.0.1 (another port), reached by
  its address and by rebind.test, a public-looking name that points to it;
- WebRTC: a UDP socket of the home network used as the page's STUN server.
"""

import http.server
import socket
import sys
import threading

import pytest
from conftest import APP

sys.path.insert(0, str(APP))
from ike import app as ike_app  # noqa: E402

NO_PROXY = {"http_proxy": "", "https_proxy": "", "HTTP_PROXY": "", "HTTPS_PROXY": "", "all_proxy": "",
            "ALL_PROXY": "", "no_proxy": "*", "NO_PROXY": "*"}


def _server(seen, tag, family=socket.AF_INET, host="127.0.0.1", page=None, redirect=None):
    class H(http.server.BaseHTTPRequestHandler):
        def _any(self):
            seen.append((tag, self.command, self.path))
            if page and self.path.startswith("/page"):
                body = page(self.path).encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
            elif self.path.startswith("/redirect") and redirect:
                body = b""
                self.send_response(302)
                self.send_header("Location", redirect[0])
            else:
                body = b"<title>home</title>ok"
                self.send_response(200)
                self.send_header("Content-Type", "text/javascript" if self.path.endswith(".js") else "text/html")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        do_GET = do_POST = _any

        def log_message(self, *a):
            pass

    class S(http.server.ThreadingHTTPServer):
        address_family = family
    srv = S((host, 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def _parts(base, tag):
    """Every way a page can ask for an address, each with its own path."""
    b = base + tag
    ws = "ws" + base[4:] + tag
    return ("<img src='{b}-img'><script src='{b}-script.js'></script><iframe src='{b}-frame'></iframe>"
            "<link rel=stylesheet href='{b}-css'>"
            "<script>fetch('{b}-fetch', {{mode: 'no-cors'}}).catch(function () {{}});"
            "var x = new XMLHttpRequest(); x.open('GET', '{b}-xhr'); x.send();"
            "new Worker(URL.createObjectURL(new Blob([\"fetch('{b}-worker').catch(function () {{}})\"])));"
            "navigator.sendBeacon('{b}-beacon', 'x');"
            "try {{ new WebSocket('{ws}-ws'); }} catch (e) {{}}</script>").format(b=b, ws=ws)


@pytest.fixture
def nets():
    seen = []
    home = _server(seen, "home")
    P = home.server_address[1]
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp.bind(("127.0.0.1", 0))

    def listen():
        while True:
            try:
                udp.recvfrom(2048)
            except OSError:
                return
            seen.append(("home", "UDP", "/webrtc"))
    threading.Thread(target=listen, daemon=True).start()

    def page(path):
        who = path.split("-", 1)[1].split("?")[0]          # /page-a, /page-b
        return ("<title>%s</title>" % who + _parts("http://127.0.0.1:%d/%s-ip" % (P, who), "")
                + _parts("http://rebind.test:%d/%s-dns" % (P, who), "")
                + "<img src='/redirect'>"
                "<script>var pc = new RTCPeerConnection({iceServers: [{urls: 'stun:127.0.0.1:%d'}]});"
                "pc.createDataChannel('x'); pc.createOffer().then(function (o) "
                "{ return pc.setLocalDescription(o); });</script>" % udp.getsockname()[1])
    redirect = ["http://rebind.test:%d/after-redirect" % P]
    inet = _server(seen, "inet", page=page, redirect=redirect)
    yield P, inet.server_address[1], seen
    home.shutdown()
    inet.shutdown()
    udp.close()


def _env(public_port, extra=""):
    rules = "MAP www.public.test 127.0.0.1, MAP www.other.test 127.0.0.1, MAP rebind.test 127.0.0.1" + extra
    return dict(NO_PROXY, IKE_ALLOW_UNSAFE_ENGINE="1",
                QTWEBENGINE_CHROMIUM_FLAGS='--no-sandbox "--host-resolver-rules=%s" '
                '--ip-address-space-overrides=127.0.0.1:%d=public' % (rules, public_port))


STEPS = r'''
P, Q = %d, %d

def steps(ike, qapp, out):
    from PyQt6.QtCore import QUrl
    win = ike.windows[0]
    v = win.current_view()
    # site A got "Allow for this site" from the window (a page of it opened
    # the router): the engine must still keep every other site away, and
    # A's own pages too (nothing per-site reaches the engine)
    ike.shields.lan_allowed.add("public.test")
    yield 800
    v.load(QUrl("http://www.other.test:%%d/page-b" %% Q))
    yield 4500
    out["bar_b"] = [win.secure_bar.isVisible(), win.secure_bar.text.text(), win.secure_bar.go.isVisible()]
    v.load(QUrl("http://www.public.test:%%d/page-a" %% Q))
    yield 4500
    out["flags"] = __import__("os").environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
    # leaving the page for the home network: a link or script, a form
    for how, js in (("nav-ip", "location.href = 'http://127.0.0.1:%%d/b-nav-ip'" %% P),
                    ("nav-dns", "location.href = 'http://rebind.test:%%d/b-nav-dns'" %% P),
                    ("form-dns", "var f = document.createElement('form'); f.method = 'POST';"
                                 "f.action = 'http://rebind.test:%%d/b-form-dns';"
                                 "document.body.appendChild(f); f.submit();" %% P)):
        v.load(QUrl("http://www.other.test:%%d/page-b?" %% Q + how))
        yield 2500
        v.page().runJavaScript(js)
        yield 2000
    v.load(QUrl("http://rebind.test:%%d/typed" %% P))            # the user's own address
    yield 2500
    out["typed"] = v.title()
'''


def test_no_public_site_reaches_home_whatever_it_uses(run_ike, nets):
    P, Q, seen = nets
    out = run_ike(STEPS % (P, Q), settings={"https_only": False}, env=_env(Q), timeout=120)
    for feature in ike_app.LNA_FEATURES:
        assert feature in out["flags"], out["flags"]
    assert ("inet", "GET", "/page-a") in seen and ("inet", "GET", "/page-b") in seen, seen
    home = {path for tag, _, path in seen if tag == "home" and path not in ("/favicon.ico", "/typed")}
    # Chromium 140 checks WebSockets only for a warning, and I.K.E. sees their
    # name, not their address: a WebSocket by a public name that points home
    # is the one way left (docs/SECURITY.md). By a literal address, I.K.E.
    # stops it, except for the site the user allowed.
    gap = {"/b-dns-ws", "/a-dns-ws", "/a-ip-ws"}
    assert home <= gap, sorted(home)
    assert "/b-ip-ws" not in home, sorted(home)
    assert ("home", "GET", "/typed") in seen and out["typed"] == "home", out
    # the window says what was stopped, with no button: nothing to allow
    assert out["bar_b"][0] is True and "other.test" in out["bar_b"][1], out["bar_b"]
    assert out["bar_b"][2] is False, out["bar_b"]


IPV6_STEPS = r'''
P, Q = %d, %d

def steps(ike, qapp, out):
    from PyQt6.QtCore import QUrl
    v = ike.windows[0].current_view()
    yield 800
    v.setHtml("<title>x</title>", QUrl("http://www.public.test:%%d/page-v6" %% Q))
    yield 500
    v.load(QUrl("http://www.public.test:%%d/page-v6" %% Q))
    yield 4500
'''


def _ipv6():
    try:
        with socket.socket(socket.AF_INET6) as s:
            s.bind(("::1", 0))
        return True
    except OSError:
        return False


@pytest.mark.skipif(not _ipv6(), reason="no IPv6 loopback on this machine")
def test_ipv6_devices_too(run_ike):
    seen = []
    home = _server(seen, "home6", family=socket.AF_INET6, host="::1")
    P = home.server_address[1]
    page = (lambda path: "<title>v6</title>" + _parts("http://[::1]:%d/ip" % P, "")
            + _parts("http://rebind6.test:%d/dns" % P, ""))
    inet = _server(seen, "inet", page=page)
    Q = inet.server_address[1]
    try:
        run_ike(IPV6_STEPS % (P, Q), settings={"https_only": False},
                env=_env(Q, ", MAP rebind6.test [::1]"), timeout=90)
    finally:
        home.shutdown()
        inet.shutdown()
    assert ("inet", "GET", "/page-v6") in seen, seen
    reached = {p for t, _, p in seen if t == "home6" and p != "/favicon.ico"}
    assert reached <= {"/dns-ws"}, sorted(reached)


def test_overrides_and_a_disabled_protection_are_dropped():
    out, named = ike_app._engine_safety(["--ip-address-space-overrides=10.0.0.1:80=public",
                                         "--disable-features=LocalNetworkAccessChecks,LocalNetworkAccessForNavigations"],
                                        env={}, allowed=False)
    assert out == [] and len(named) == 3, (out, named)          # each one named


def test_an_inherited_warn_only_does_not_win(monkeypatch, tmp_path):
    monkeypatch.setattr(ike_app, "CONFIG_DIR", tmp_path)
    monkeypatch.setenv("QTWEBENGINE_CHROMIUM_FLAGS",
                       "--enable-features=Foo,LocalNetworkAccessChecks:LocalNetworkAccessChecksWarn/true")
    monkeypatch.setenv("IKE_ALLOW_UNSAFE_ENGINE", "1")
    from ike.config import Config
    ike_app._chromium_flags(Config(tmp_path / "settings.json"))
    flags = ike_app.split_flags(__import__("os").environ["QTWEBENGINE_CHROMIUM_FLAGS"])
    on = [f for f in flags if f.startswith("--enable-features=")]
    assert len(on) == 1, flags
    feats = on[0].split("=", 1)[1].split(",")
    assert "Foo" in feats and "LocalNetworkAccessChecks:LocalNetworkAccessChecksWarn/true" not in feats, feats
    assert all(f in feats for f in ike_app.LNA_FEATURES), feats
