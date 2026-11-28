"""The cases the independent review of 1.1.32 found in the diagnosis, the
octagon's colours and the sites' own workers (each was reproduced in the
real browser before it was fixed; the fixes are in ike/incompat.py,
ike/window.py, ike/securebar.py, ike/shields.py, ike/shieldpanel.py,
ike/interference.py and ike/resources/fingerprint.js):

- red never comes from a console message: a frame of another site printing
  the engine's words about the home network does not make the octagon red;
- the green never plays on a page of a warning the user went through (a page
  of the lists opened anyway);
- the green does not play where a protection is off by inheritance (a parent
  domain's exception) or cookies are allowed;
- a kept repair is verified by the probe, and the finding ends by itself;
- the effects turned off while a finding shows: no timer; back on: it runs;
- a web component page and a sign-in form are not "empty";
- where the user blocked the site's own workers, a service worker started
  before is not taken back by register(), in the second page either;
- "Allow them again" on a subdomain of a blocked parent works.
"""

import http.server
import threading

import pytest

PAGE = b"<!doctype html><title>p</title><body><p>" + b"Some text. " * 60 + b"</p></body>"
FRAMED = (b"<!doctype html><title>f</title><body><p>" + b"Text. " * 60 + b"</p>"
          b"<iframe src='http://localhost:%d/lanframe'></iframe></body>")
LANFRAME = b"<!doctype html><script>console.log('address space more-private Permission was denied');</script>"
COMPONENT = (b"<!doctype html><title>c</title><body><my-app></my-app><script>"
             b"customElements.define('my-app', class extends HTMLElement { connectedCallback() {"
             b" this.attachShadow({mode: 'open'}).innerHTML = '<p>' + 'Content of the app. '.repeat(40) + '</p>'; } });"
             b"</script></body>")
SIGNIN = (b"<!doctype html><title>s</title><body><form><input placeholder='Email'>"
          b"<input type='password' placeholder='Password'><button>Go</button></form></body>")
SW_PAGE = (b"<!doctype html><title>w</title><body><script>"
           b"navigator.serviceWorker.register('/sw.js').then(function () { return navigator.serviceWorker.ready; })"
           b".then(function () { window.result = 'ok ' + !!navigator.serviceWorker.controller; },"
           b" function (e) { window.result = 'refused ' + e.name + ' ' + !!navigator.serviceWorker.controller; });"
           b"</script></body>")
SW = b"self.addEventListener('install', function () { self.skipWaiting(); });" \
     b"self.addEventListener('activate', function (e) { e.waitUntil(self.clients.claim()); });" \
     b"self.addEventListener('fetch', function () {});"


@pytest.fixture
def site():
    port = {}

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            path = self.path.split("?")[0]
            body = {"/framed": FRAMED % port["p"], "/lanframe": LANFRAME, "/component": COMPONENT,
                    "/signin": SIGNIN, "/swpage": SW_PAGE, "/sw.js": SW}.get(path, PAGE)
            self.send_response(200)
            self.send_header("Content-Type", "text/javascript" if path.endswith(".js") else "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    port["p"] = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield port["p"]
    srv.shutdown()


LOAD = r'''
import json
from PyQt6.QtCore import QUrl

def load(view, url):
    done = {}
    view.page().loadFinished.connect(lambda ok, d=done: d.setdefault("ok", ok))
    view.load(QUrl(url))
    while "ok" not in done:
        yield 20
    return done["ok"]

def result(view, out, key, tries=100):
    for _ in range(tries):
        res = {}
        view.page().runJavaScript("window.result || ''", 0, lambda r, res=res: res.__setitem__("r", r))
        while "r" not in res:
            yield 20
        if res["r"]:
            out[key] = res["r"]
            return
        yield 100
'''

COLOURS = LOAD + r'''
def steps(ike, qapp, out):
    from ike import incompat as I
    win = ike.windows[0]
    anim = win.shield_btn.interference
    view = win.current_view()
    base = "http://127.0.0.1:%d"
    # a frame of another site prints the engine's words: no red
    yield from load(view, base + "/framed")
    yield 1500
    out["frame_console"] = [win.interference_state()[0], bool(getattr(view, "secure_notice", None))]
    # a page of the lists opened anyway: no green
    view._ike_confirmed_site = None
    view._ike_confirmed_at = -1e9
    ike.shields.pages_allowed.add("127.0.0.1")
    n = anim.confirms
    yield from load(view, base + "/page?pa")
    yield 900
    out["green_pages_allowed"] = anim.confirms - n
    ike.shields.pages_allowed.discard("127.0.0.1")
    # a parent's exception, cookies allowed: no green
    for key, opts in (("parent", {"0.1": {"ads": False}}), ("cookies", {"127.0.0.1": {"cookies": "allow"}})):
        ike.config["site_opts"].clear()
        ike.config["site_opts"].update(opts)
        view._ike_confirmed_site = None
        view._ike_confirmed_at = -1e9
        n = anim.confirms
        yield from load(view, base + "/page?" + key)
        yield 900
        out["green_" + key] = anim.confirms - n
    ike.config["site_opts"].clear()
    # a kept repair, verified by the probe: the finding ends by itself
    ike.config["shield_level"] = "strict"
    ike.config.set_site_opt("127.0.0.1", "workers", True)
    yield from load(view, base + "/page?v1")
    view._ike_diag["quiet"] = set()
    ike.diagnosis._set(view, I.Finding("workers", "127.0.0.1", ("workers",), I.SiteWorkers.CAUSE, I.ATTENTION))
    out["before_verify"] = win.interference_state()[0]
    ike.config.set_site_opt("127.0.0.1", "workers", False)      # the repair kept
    yield from load(view, base + "/page?v2")
    for _ in range(100):
        if ike.diagnosis.finding(view) is None:
            break
        yield 100
    out["verified"] = [ike.diagnosis.finding(view) is None, ike.diagnosis.ended(view)]
    # effects off while a finding shows: no timer; back on: it runs
    ike.diagnosis._settled.clear()
    view._ike_diag["quiet"] = set()
    ike.diagnosis._set(view, I.Finding("workers", "127.0.0.1", ("workers",), I.SiteWorkers.CAUSE, I.SERIOUS))
    yield 200
    ike.config["ui_effects"] = False
    yield 300
    out["effects_off_timer"] = anim._timer.isActive()
    ike.config["ui_effects"] = True
    win.sync_interference()
    yield 200
    out["effects_on_timer"] = anim._timer.isActive()
'''


def test_colours_and_the_green(run_ike, site):
    out = run_ike(COLOURS % site, settings={"shield_level": "balanced", "https_only": False}, timeout=200)
    assert out["frame_console"][0] is None, out
    assert out["green_pages_allowed"] == 0, out
    assert out["green_parent"] == 0 and out["green_cookies"] == 0, out
    assert out["before_verify"] == "attention" and out["verified"] == [True, "resolved"], out
    assert out["effects_off_timer"] is False and out["effects_on_timer"] is True, out


PROBE = LOAD + r'''
def steps(ike, qapp, out):
    from PyQt6.QtWebEngineCore import QWebEngineScript
    from ike.incompat import PROBE_JS
    view = ike.windows[0].current_view()
    for key in ("component", "signin"):
        yield from load(view, "http://127.0.0.1:%d/" + key)
        yield 500
        res = {}
        view.page().runJavaScript(PROBE_JS, QWebEngineScript.ScriptWorldId.ApplicationWorld,
                                  lambda r, res=res: res.__setitem__("r", r))
        while "r" not in res:
            yield 20
        out[key] = json.loads(res["r"])
'''


def test_the_probe_reads_components_and_forms(run_ike, site):
    out = run_ike(PROBE % site, settings={"shield_level": "strict"}, timeout=120)
    assert out["component"]["blank"] is False and out["component"]["text"] >= 30, out
    assert out["signin"]["blank"] is False and out["signin"]["controls"] >= 3, out


SERVICE = LOAD + r'''
def steps(ike, qapp, out):
    from PyQt6.QtCore import QUrl
    win = ike.windows[0]
    a = win.current_view()
    yield from load(a, "http://127.0.0.1:%d/swpage")
    yield from result(a, out, "kontrol")
    # the user blocks the site's workers; the first tab keeps the old worker
    ike.config.set_site_opt("127.0.0.1", "workers", True)
    ike.shields.apply_settings()
    b = win.add_tab(QUrl("about:blank"))
    yield 300
    for i in range(3):                     # three pages in a row: never taken back
        yield from load(b, "http://127.0.0.1:%d/swpage?" + str(i))
        yield from result(b, out, "blocked" + str(i))
'''


def test_a_blocked_service_worker_is_never_taken_back(run_ike, site):
    out = run_ike(SERVICE % (site, site), settings={"shield_level": "strict", "https_only": False}, timeout=200)
    assert out["kontrol"].startswith("ok"), out
    for i in range(3):
        assert out["blocked%d" % i].startswith("refused TypeError"), out


SUBDOMAIN = LOAD + r'''
def steps(ike, qapp, out):
    win = ike.windows[0]
    view = win.current_view()
    p = win.shield_panel
    ike.config.set_site_opt("localhost", "workers", True)          # the block on the parent
    yield from load(view, "http://sub.localhost:%d/swpage")
    yield from result(view, out, "blocked")
    win.shield_menu.aboutToShow.emit()
    out["button"] = p.workers_btn.text()
    p.workers_btn.click()                                           # "Allow them again"
    out["after"] = [ike.config.site_opt("sub.localhost", "workers"), ike.config.site_opt("localhost", "workers")]
'''


def test_allow_again_on_a_subdomain_of_a_blocked_parent(run_ike, site):
    out = run_ike(SUBDOMAIN % site, settings={"shield_level": "strict", "https_only": False}, timeout=120)
    assert out["blocked"].startswith("refused"), out
    assert out["button"] == "Allow them again", out
    # this site allowed, the parent's block left as it was
    assert out["after"] == [False, True], out
