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


OPAQUE = r'''
PORT = %d

def steps(ike, qapp, out):
    from PyQt6.QtCore import QUrl
    v = ike.windows[0].current_view()
    yield 1000
    L = "http://127.0.0.1:%%d" %% PORT
    h = "<title>public</title>"
    h += ("<iframe sandbox='allow-scripts' srcdoc=\"<img src='" + L + "/sbx-img'><script>fetch('" + L +
          "/sbx-fetch',{method:'POST',mode:'no-cors',body:'x'})</script>\"></iframe>")
    h += "<iframe src=\"data:text/html,<img src='" + L + "/data-img'>\"></iframe>"
    h += ("<iframe sandbox='allow-forms allow-scripts' srcdoc=\"<form method=post action='" + L +
          "/sbx-form'><input name=a value=1></form><script>document.forms[0].submit()</script>\"></iframe>")
    h += ("<iframe sandbox='allow-scripts allow-popups' srcdoc=\"<a id=a target=_blank href='" + L +
          "/sbx-popup'>x</a><script>document.getElementById('a').click()</script>\"></iframe>")
    v.setHtml(h, QUrl("http://news.example.test/"))
    yield 3500
'''


def test_frames_with_no_origin_of_their_own(run_ike, lan):
    """Adversarial review of 1.1.18: a sandboxed frame or a data: frame has
    no origin, so its requests came with no initiator and passed as the
    user's own: a picture, a POST from fetch and a form reached the router.
    They are judged by the page they are in now; a popup they open by a link
    too."""
    port, seen = lan
    run_ike(OPAQUE % port, settings={"https_only": False}, timeout=90)
    reached = [x for x in seen if x.split(" ", 1)[1].startswith(("/sbx", "/data"))]
    assert reached == [], seen


def test_names_local_by_their_form():
    from ike.userscripts import is_local_name
    for h in ("router", "printer.", "fritz.box", "nas.fritz.box", "router.lan", "nas.home.arpa",
              "svc.internal", "intranet.corp", "cafe", "localhost", "a.local", "192.168.1.1", "[::1]"):
        assert is_local_name(h), h
    for h in ("", "example.com", "cafe.example", "2001:db8::1", "8.8.8.8", "134744072", "fritz.box.example"):
        assert not is_local_name(h), h


POPUP = r'''
PORT = %d

def steps(ike, qapp, out):
    from PyQt6.QtCore import QCoreApplication, QEvent, QPointF, Qt, QUrl
    from PyQt6.QtGui import QMouseEvent
    win = ike.windows[0]
    v = win.current_view()
    yield 1000
    L = "http://127.0.0.1:%%d" %% PORT
    v.setHtml("<title>public</title><style>body{margin:0}</style>"
              "<iframe style='position:fixed;left:0;top:0;width:400px;height:300px;border:0' "
              "sandbox='allow-scripts allow-popups' srcdoc=\"<style>body{margin:0}</style><a target=_blank "
              "style='display:block;width:400px;height:300px' href='" + L + "/sbx-click'>x</a>\"></iframe>",
              QUrl("http://news.example.test/"))
    yield 2500
    before = sum(len(list(w.all_views())) for w in ike.windows)
    t = v.focusProxy() or v
    for et, b in ((QEvent.Type.MouseButtonPress, Qt.MouseButton.LeftButton),
                  (QEvent.Type.MouseButtonRelease, Qt.MouseButton.NoButton)):
        QCoreApplication.sendEvent(t, QMouseEvent(et, QPointF(100, 100), QPointF(100, 100),
                                                  Qt.MouseButton.LeftButton, b, Qt.KeyboardModifier.NoModifier))
    yield 3000
    out["opened"] = sum(len(list(w.all_views())) for w in ike.windows) - before
'''


def test_a_popup_of_a_frame_with_no_origin_opened_by_a_real_click(run_ike, lan):
    """The popup case above is opened by a script, which the engine's popup
    blocker stops before I.K.E. sees it: that case proved nothing. Here a
    real click opens the popup (a new tab) and its address of the home
    network is still stopped: the link of a page with no origin of its own
    is the public page's (1.1.18), not the user's (found in 1.1.19: dropping
    links from that rule went unnoticed)."""
    port, seen = lan
    out = run_ike(POPUP % port, settings={"https_only": False}, timeout=90)
    assert out["opened"] >= 1, out                     # the popup did open: the case is really tried
    assert not [x for x in seen if "/sbx-click" in x], seen


RULE = r'''
def steps(ike, qapp, out):
    from PyQt6.QtCore import QByteArray, QUrl
    from PyQt6.QtWebEngineCore import QWebEngineUrlRequestInfo as RI
    T, NT = RI.ResourceType, RI.NavigationType
    yield 500

    class Info:
        """A main-frame request with no initiator, as from a page with no
        origin of its own (a sandboxed frame's popup) or from the user."""
        def __init__(self, nav):
            self.nav, self.blocked = nav, False
        def requestUrl(self): return QUrl("http://192.168.1.1/admin")
        def firstPartyUrl(self): return QUrl("http://192.168.1.1/admin")
        def initiator(self): return QUrl()
        def resourceType(self): return T.ResourceTypeMainFrame
        def navigationType(self): return self.nav
        def requestMethod(self): return QByteArray(b"POST")
        def block(self, b): self.blocked = b
        def redirect(self, u): pass
        def setHttpHeader(self, k, v): pass
    out["blocked"] = {}
    for name in ("NavigationTypeLink", "NavigationTypeFormSubmitted", "NavigationTypeTyped",
                 "NavigationTypeReload", "NavigationTypeBackForward"):
        info = Info(getattr(NT, name))
        ike.shields.interceptor.interceptRequest(info)
        out["blocked"][name] = info.blocked
'''


def test_with_no_initiator_links_and_forms_are_a_pages(run_ike):
    """With no initiator, a link or a form is a page's (a page with no origin
    of its own: its popup, a form that popup sends) and is stopped on its way
    home; what the user types, reloads or goes back to is the user's."""
    out = run_ike(RULE, timeout=60)
    assert out["blocked"] == {"NavigationTypeLink": True, "NavigationTypeFormSubmitted": True,
                              "NavigationTypeTyped": False, "NavigationTypeReload": False,
                              "NavigationTypeBackForward": False}, out["blocked"]
