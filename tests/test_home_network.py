"""Home network protection for every kind of request (1.1.18, security audit F2).

Until 1.1.18 only pages and frames of a public site were stopped from opening
an address of this computer or of the home network; the engine stopped none
of the rest. A public page reached a local service with a POST from fetch, a
picture, a script, a beacon and a WebSocket. Now each of them is stopped and
the window says that a part of the page was stopped (with "Allow for this
site"); a page of the home network still loads its own parts. Names that are
local by their form (router, fritz.box, *.lan, *.home.arpa) count as local.
"""

import http.server
import threading

import pytest


@pytest.fixture
def lan():
    seen = []

    class H(http.server.BaseHTTPRequestHandler):
        def _any(self):
            seen.append(self.command + " " + self.path)
            if "/redirect?to=" in self.path:            # as a public site (reached as a proxy) that redirects home
                self.send_response(302)
                self.send_header("Location", self.path.split("to=", 1)[1])
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            body = b"<title>home</title><img src='/own.png'>" if self.path == "/page" else b"ok"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        do_GET = do_POST = _any

        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1], seen
    srv.shutdown()


STEPS = r'''
PORT = %d

def steps(ike, qapp, out):
    from PyQt6.QtCore import QUrl
    win = ike.windows[0]
    v = win.current_view()
    yield 1000
    L = "http://127.0.0.1:%%d" %% PORT
    v.setHtml("<title>public</title><img src='" + L + "/img.png'><script src='" + L + "/x.js'></script>"
              "<script>fetch('" + L + "/fetch', {method: 'POST', mode: 'no-cors', body: 'a=1'}).catch(function () {});"
              "navigator.sendBeacon('" + L + "/beacon', 'b');"
              "try { new WebSocket('ws://127.0.0.1:%%d/ws'); } catch (e) {}</script>" %% PORT,
              QUrl("https://news.example.test/"))
    yield 3000
    out["bar"] = [win.secure_bar.isVisible(), win.secure_bar.text.text()]
    home = win.add_tab(QUrl(L + "/page"))                 # a page of the home network: its own parts load
    yield 2500
    out["home"] = home.title()
'''


def test_a_public_page_reaches_no_local_service_with_any_request(run_ike, lan):
    port, seen = lan
    out = run_ike(STEPS % port, settings={"https_only": False}, timeout=90)
    public = [s for s in seen if s.split(" ")[1] in ("/img.png", "/x.js", "/fetch", "/beacon", "/ws")]
    assert public == [], seen                                  # nothing of the public page got there
    assert out["bar"][0] is True and "example.test" in out["bar"][1], out
    assert out["home"] == "home" and "GET /own.png" in seen, (out, seen)


ODD = r'''
PORT = %d

def steps(ike, qapp, out):
    from PyQt6.QtCore import QUrl
    v = ike.windows[0].current_view()
    yield 1000
    P = PORT
    html = "<title>public</title>"
    for i, host in enumerate(("0x7f.0.0.1", "2130706433", "0177.0.0.1", "127.1", "[::ffff:127.0.0.1]", "[::1]")):
        html += "<img src='http://%%s:%%d/odd%%d.png'>" %% (host, P, i)
    html += "<img src='http://cdn.example.test/redirect?to=http://127.0.0.1:%%d/hop.png'>" %% P
    v.setHtml(html, QUrl("http://news.example.test/"))
    yield 3500
'''


def test_other_ways_of_writing_the_address_and_redirects(run_ike, lan):
    """Old and alternative forms of a local address (hexadecimal, a single
    number, octal, short, IPv4 inside IPv6, ::1), and a public site that
    redirects to the home network: none gets there. The public site is the
    test server reached as an HTTP proxy, so the first hop is really made."""
    port, seen = lan
    proxy = "http://127.0.0.1:%d" % port
    run_ike(ODD % port, settings={"https_only": False}, timeout=90,
            env={"http_proxy": proxy, "HTTP_PROXY": proxy, "no_proxy": "", "NO_PROXY": ""})
    assert any("/redirect?to=" in s for s in seen), seen          # the public hop was made
    reached = [s for s in seen if s.split(" ", 1)[1].startswith(("/odd", "/hop.png"))]   # direct requests
    assert reached == [], seen


def test_names_local_by_their_form():
    from ike.userscripts import is_local_name
    for h in ("router", "printer.", "fritz.box", "nas.fritz.box", "router.lan", "nas.home.arpa",
              "svc.internal", "intranet.corp", "cafe", "localhost", "a.local", "192.168.1.1", "[::1]"):
        assert is_local_name(h), h
    for h in ("", "example.com", "cafe.example", "2001:db8::1", "8.8.8.8", "134744072", "fritz.box.example"):
        assert not is_local_name(h), h
