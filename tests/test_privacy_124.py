"""The privacy package of 1.1.24: bounce tracking, the protected time zone,
quiet permission prompts, the password breach check, the web engine's
advisory ("Update the system") and the battery saver."""

import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from conftest import ROOT

sys.path.insert(0, str(ROOT))

NO_PROXY_ENV = {"http_proxy": "", "https_proxy": "", "HTTP_PROXY": "", "HTTPS_PROXY": "", "all_proxy": "",
                "ALL_PROXY": "", "no_proxy": "*", "NO_PROXY": "*"}

JS = r'''
import json
def js(view, code, world=0):
    box = {}
    page = view.page() if hasattr(view, "page") else view
    page.runJavaScript(code, world, lambda r: box.setdefault("r", r))
    for _ in range(300):
        if "r" in box:
            break
        yield 20
    return box.get("r")

def load(view, url):
    from PyQt6.QtCore import QUrl
    done = {}
    def finished(ok):
        done.setdefault("ok", ok)
    view.page().loadFinished.connect(finished)
    view.load(QUrl(url) if isinstance(url, str) else url)
    for _ in range(400):
        if "ok" in done:
            break
        yield 20
    view.page().loadFinished.disconnect(finished)
    yield 300
    return done.get("ok")

def until(test, ms=8000):
    for _ in range(ms // 50):
        if test():
            return True
        yield 50
    return False
'''


def serve(handler_cls):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def resolver_env(hosts):
    rules = ", ".join("MAP %s 127.0.0.1" % h for h in hosts)
    return dict(NO_PROXY_ENV, QTWEBENGINE_CHROMIUM_FLAGS='--no-sandbox "--host-resolver-rules=%s"' % rules)


# --- 1. bounce tracking -------------------------------------------------------

def test_a_hop_is_a_redirect_away_from_another_site_without_the_users_act():
    from PyQt6.QtCore import QUrl
    from PyQt6.QtWebEngineCore import QWebEnginePage

    from ike import bounce
    R = QWebEnginePage.NavigationType.NavigationTypeRedirect
    L = QWebEnginePage.NavigationType.NavigationTypeLinkClicked
    u = QUrl
    assert bounce.hop(u("https://t.tracker.test/x?to=d"), u("https://dest.test/"), R, False) == "tracker.test"
    assert bounce.hop(u("https://t.tracker.test/x"), u("https://dest.test/"), L, False) is None      # a link
    assert bounce.hop(u("https://t.tracker.test/x"), u("https://dest.test/"), R, True) is None       # the user acted
    assert bounce.hop(u("https://example.test/"), u("https://www.example.test/"), R, False) is None  # one site
    assert bounce.hop(u("http://example.test/"), u("https://example.test/"), R, False) is None       # http -> https
    assert bounce.hop(None, u("https://dest.test/"), R, False) is None
    assert bounce.hop(u("file:///tmp/a.html"), u("https://dest.test/"), R, False) is None


def test_the_sites_used_are_kept_45_days_and_the_list_stays_small():
    from ike import bounce
    now = 100 * 86400.0
    day = bounce.today(now)
    used = {"old.test": day - 46, "recent.test": day - 45, "today.test": day, "bad.test": "x"}
    bounce.prune(used, now)
    assert used == {"recent.test": day - 45, "today.test": day}
    many = {"s%d.test" % i: day - (i % 40) for i in range(50)}
    bounce.prune(many, now, most=10)
    assert len(many) == 10 and min(many.values()) >= day - 39 + 30 - 1


def test_sign_in_payment_and_allowed_sites_are_never_cleaned(tmp_path):
    from ike import bounce
    from ike.config import Config
    cfg = Config(tmp_path / "settings.json")
    for site in ("google.com", "microsoftonline.com", "apple.com", "paypal.com", "stripe.com"):
        assert bounce.protected_site(cfg, site), site
    assert not bounce.protected_site(cfg, "tracker.test")
    cfg.set_site_level("tracker.test", "off")
    assert bounce.protected_site(cfg, "tracker.test")
    cfg.set_site_opt("other.test", "cookies", "allow")
    assert bounce.protected_site(cfg, "other.test", {"t.other.test"})


BOUNCE_HOSTS = ("start.test", "t.tracker.test", "js.tracker2.test", "used.test", "dest.test", "kept.test")


@pytest.fixture
def bounce_sites():
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            host = self.headers.get("Host", "").split(":")[0]
            port = self.server.server_address[1]
            dest = "http://dest.test:%d/" % port
            if host == "start.test":
                links = "".join('<a id="%s" href="http://%s:%d/go">%s</a>' % (h.split(".")[-2], h, port, h)
                                for h in ("t.tracker.test", "js.tracker2.test", "used.test", "kept.test"))
                self._send(200, "<!doctype html><title>start</title>" + links)
            elif host == "kept.test" and self.path == "/page":
                self._send(200, "<!doctype html><title>kept</title>kept", cookie="k=1; Max-Age=86400; Path=/")
            elif host in ("t.tracker.test", "used.test", "kept.test"):
                # the server's redirect, with a cookie that would follow the user
                self.send_response(302)
                self.send_header("Set-Cookie", "uid=%s-1234; Max-Age=86400; Path=/" % host.split(".")[0])
                self.send_header("Location", dest)
                self.send_header("Content-Length", "0")
                self.end_headers()
            elif host == "js.tracker2.test":
                # the page's own redirect, with a cookie and local storage
                self._send(200, "<!doctype html><title>hop</title><script>document.cookie='uid=js-1234; "
                                "max-age=86400; path=/'; localStorage.setItem('uid', 'js-1234');"
                                "location.replace(%s);</script>" % json.dumps(dest),
                           cookie=None)
            else:
                self._send(200, "<!doctype html><title>dest</title>destination", cookie="seen=1; Max-Age=86400; Path=/")

        def _send(self, code, body, cookie=None):
            data = body.encode()
            self.send_response(code)
            self.send_header("Content-Type", "text/html")
            if cookie:
                self.send_header("Set-Cookie", cookie)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):
            pass
    srv = serve(H)
    yield srv.server_address[1]
    srv.shutdown()


def test_bounce_trackers_lose_their_data_and_the_others_keep_it(run_ike, bounce_sites):
    from ike import bounce
    port = bounce_sites
    out = run_ike(JS + r'''
PORT = %d

def steps(ike, qapp, out):
    from PyQt6.QtCore import QUrl
    from PyQt6.QtWebEngineCore import QWebEnginePage
    from ike import bounce
    bounce.DELAY_MS = 120000         # the clean-up is started below, when everything is noted
    win = ike.windows[0]
    view = win.current_view()
    profile = view.page().profile()
    start = "http://start.test:%%d/" %% PORT
    # a tab of kept.test stays open: never cleaned (opened by I.K.E. as if typed:
    # the site counts as used too, which is forgotten here to see the open tab alone)
    win.add_tab(QUrl("http://kept.test:%%d/page" %% PORT), background=True)
    yield 1500
    ike.config["bounce_used"].pop("kept.test", None)
    ike.bounce._last = None
    for name in ("tracker", "tracker2", "used", "kept"):
        yield from load(view, start)
        done = {}
        view.page().loadFinished.connect(lambda ok, done=done: done.setdefault("ok", ok))
        yield from js(view, "document.getElementById(%%s).click(); 1" %% json.dumps(name))
        yield from until(lambda: "dest" in view.url().host() and "ok" in done)
        yield 400
    out["recorded"] = sorted(e["site"] for e in ike.bounce.pending.values())
    out["cookies_before"] = {s: len(ike.shields.site_cookies(profile, s))
                             for s in ("tracker.test", "tracker2.test", "used.test", "kept.test", "dest.test")}
    out["timer"] = ike.bounce._timer is not None and ike.bounce._timer.isActive()
    ike.bounce.purge()
    yield from until(lambda: ike.bounce._cleaner is None
                     and not ike.bounce._cleaning, 10000)
    yield 1500
    out["purged"] = sorted(ike.bounce.purged)
    out["cookies_after"] = {s: len(ike.shields.site_cookies(profile, s))
                            for s in ("tracker.test", "tracker2.test", "used.test", "kept.test", "dest.test")}
    # the page's own storage of the client-side hop, read from a page at its address
    page = QWebEnginePage(profile)
    loaded = {}
    page.loadFinished.connect(lambda ok: loaded.setdefault("ok", ok))
    page.setHtml("<title>x</title>", QUrl("http://js.tracker2.test:%%d/" %% PORT))
    yield from until(lambda: "ok" in loaded)
    out["storage"] = yield from js(page, "localStorage.getItem('uid')")
    out["used"] = sorted(ike.config["bounce_used"])
''' % port, env=resolver_env(BOUNCE_HOSTS), timeout=180,
                  settings={"https_only": False, "bounce_used": {"used.test": bounce.today()},
                            "bounce_seeded": True})
    # every redirect away from another site without a click was noted
    assert out["recorded"] == ["kept.test", "tracker.test", "tracker2.test", "used.test"], out
    assert out["timer"] is True                              # the clean-up waits its time
    before, after = out["cookies_before"], out["cookies_after"]
    assert before["tracker.test"] and before["tracker2.test"] and before["used.test"] and before["dest.test"], before
    # only the two trackers were cleaned: used.test was used, kept.test is open in a tab
    assert out["purged"] == ["tracker.test", "tracker2.test"], out
    assert after["tracker.test"] == 0 and after["tracker2.test"] == 0, after
    assert after["used.test"] == before["used.test"] and after["dest.test"] == before["dest.test"], after
    assert after["kept.test"] == before["kept.test"], after
    assert out["storage"] is None, out                       # the hop's local storage went too


def test_bounce_protection_off_records_and_cleans_nothing(run_ike, bounce_sites):
    port = bounce_sites
    out = run_ike(JS + r'''
PORT = %d

def steps(ike, qapp, out):
    from ike import bounce
    bounce.DELAY_MS = 300
    view = ike.windows[0].current_view()
    yield from load(view, "http://start.test:%%d/" %% PORT)
    yield from js(view, "document.getElementById('tracker').click(); 1")
    yield from until(lambda: "dest" in view.url().host())
    yield 1500
    out["pending"] = len(ike.bounce.pending)
    out["purged"] = list(ike.bounce.purged)
    out["cookies"] = len(ike.shields.site_cookies(view.page().profile(), "tracker.test"))
''' % port, env=resolver_env(BOUNCE_HOSTS), timeout=120,
                  settings={"https_only": False, "bounce_protect": False})
    assert out["pending"] == 0 and out["purged"] == [] and out["cookies"] == 1, out


# --- 2. the protected time zone ----------------------------------------------

TZ_STEPS = JS + r'''
PORT = %d

def steps(ike, qapp, out):
    import time
    view = ike.windows[0].current_view()
    yield from load(view, "http://127.0.0.1:%%d/page" %% PORT)
    yield from until(lambda: view.title().startswith("["), 10000)
    out["page"] = json.loads(view.title())
    out["python_offset"] = time.localtime(1700000000).tm_gmtoff
    out["newtab_zone"] = "Asia/Tokyo" in ike.shields.newtab_html()
    from ike import timezone
    out["active"] = timezone.active()
'''

TZ_PAGE = br"""<!doctype html><title>tz</title><script>
var me = [new Date(0).getTimezoneOffset(), Intl.DateTimeFormat().resolvedOptions().timeZone,
          new Date(2020, 0, 1).toString().indexOf('GMT+0000') > 0, new Date(0).toLocaleString('en-US'),
          new Date(0).getHours()];
var f = document.createElement('iframe');
f.srcdoc = '<script>parent.frameSays([new Date(0).getTimezoneOffset(), Intl.DateTimeFormat().resolvedOptions().timeZone]);<\/script>';
var frame = null, inline = null, file = null;
window.frameSays = function (v) { frame = v; done(); };
function done() { if (frame && inline && file) document.title = JSON.stringify({me: me, frame: frame, inline: inline, file: file}); }
var src = 'postMessage([new Date(0).getTimezoneOffset(), Intl.DateTimeFormat().resolvedOptions().timeZone])';
var w1 = new Worker(URL.createObjectURL(new Blob([src])));
w1.onmessage = function (e) { inline = e.data; done(); };
var w2 = new Worker('/w.js');
w2.onmessage = function (e) { file = e.data; done(); };
document.documentElement.appendChild(f);
</script>"""


@pytest.fixture
def tz_site():
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/w.js":
                body, kind = (b"postMessage([new Date(0).getTimezoneOffset(), "
                              b"Intl.DateTimeFormat().resolvedOptions().timeZone])"), "text/javascript"
            else:
                body, kind = TZ_PAGE, "text/html"
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = serve(H)
    yield srv.server_address[1]
    srv.shutdown()


@pytest.mark.parametrize("level", ["balanced", "maximum"])
def test_the_protected_time_zone_is_utc_everywhere_and_ike_keeps_its_own(run_ike, tz_site, level):
    """The page, a frame, an inline worker and a worker from a file all see UTC;
    I.K.E.'s own time and its new tab clock stay in the user's zone. At Maximum
    the fingerprinting protection's dates (en-US) agree with it."""
    out = run_ike(TZ_STEPS % tz_site, env=dict(NO_PROXY_ENV, TZ="Asia/Tokyo"), timeout=120,
                  settings={"protect_timezone": True, "https_only": False, "shield_level": level})
    page = out["page"]
    assert page["me"] == [0, "UTC", True, "1/1/1970, 12:00:00 AM", 0], page
    for where in ("frame", "inline", "file"):
        assert page[where] == [0, "UTC"], (where, page)
    assert out["active"] is True
    assert out["python_offset"] == 9 * 3600, out          # menus and history: the user's own time
    assert out["newtab_zone"] is True                      # the new tab clock: the user's own zone


def test_without_the_option_pages_see_the_real_zone(run_ike, tz_site):
    out = run_ike(TZ_STEPS % tz_site, env=dict(NO_PROXY_ENV, TZ="Asia/Tokyo"), timeout=120,
                  settings={"https_only": False})
    page = out["page"]
    assert page["me"][:2] == [-540, "Asia/Tokyo"] and page["me"][3:] == ["1/1/1970, 9:00:00 AM", 9], page
    assert page["file"] == [-540, "Asia/Tokyo"] and page["inline"] == [-540, "Asia/Tokyo"], page
    assert out["active"] is False and out["newtab_zone"] is False


def test_time_zone_apply_and_restore(tmp_path):
    from ike import timezone
    zoneinfo = tmp_path / "usr/share/zoneinfo/Europe"
    zoneinfo.mkdir(parents=True)
    (zoneinfo / "Rome").write_bytes(b"TZif")
    link = tmp_path / "localtime"
    link.symlink_to(zoneinfo / "Rome")
    assert timezone.real_zone({}, localtime=str(link)) == "Europe/Rome"
    assert timezone.real_zone({"TZ": "America/New_York"}) == "America/New_York"
    assert timezone.real_zone({"TZ": "x; rm -rf /"}) == ""            # only plain zone names
    env = {}
    assert timezone.apply({"protect_timezone": False}, env) is False and env == {}
    try:
        assert timezone.apply({"protect_timezone": True}, env) is True and env["TZ"] == "UTC"
        assert timezone.active()
    finally:
        assert timezone.restore(env) is True
    # back in the user's zone, and still set: the engine never follows the system's files
    assert env["TZ"] == ":/etc/localtime"
    env = {"TZ": "Asia/Tokyo"}
    timezone.apply({"protect_timezone": True}, env)
    timezone.restore(env)
    assert env == {"TZ": "Asia/Tokyo"}
    timezone._saved.clear()


# --- 3. quiet permission prompts --------------------------------------------------

@pytest.fixture
def ask_site():
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            body = (b"<!doctype html><title>ask</title><script>window.asked = [];"
                    b"function ask() { Notification.requestPermission().then(function (r) { asked.push(r); }); }"
                    b"</script>")
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = serve(H)
    yield "http://127.0.0.1:%d" % srv.server_address[1]
    srv.shutdown()


def test_quiet_prompts_a_sign_instead_of_a_window(run_ike, ask_site):
    out = run_ike(JS + r'''
BASE = %r

def steps(ike, qapp, out):
    import time
    from PyQt6.QtCore import QUrl
    from PyQt6.QtWebEngineCore import QWebEnginePermission as P
    from ike import quietperms, webview
    windows = []
    webview.WebPage.ask_permission = lambda self, o, t: windows.append(o) or False
    win = ike.windows[0]
    view = win.current_view()
    page = view.page()
    origin = QUrl(BASE)
    state = lambda: page.profile().queryPermission(origin, P.PermissionType.Notifications).state()
    yield from load(view, BASE + "/ask")
    # 1. asked with no click on the page: refused at once, not remembered, the sign shown
    yield from js(view, "ask(); 1")
    yield from until(lambda: len(quietperms.waiting(page)) == 1, 4000)
    yield 500
    out["no_click"] = [(yield from js(view, "asked")), state() == P.State.Ask,
                       win.urlbar.perm_act.isVisible()]
    quietperms.drop(page)
    out["dropped"] = win.urlbar.perm_act.isVisible()
    # 2. asked four times right after a click: one question, answered for all
    yield from load(view, BASE + "/ask?click")
    page._ike_input = time.monotonic()
    for _ in range(4):
        yield from js(view, "ask(); 1")
        yield 100
    yield 500
    out["held"] = [len(quietperms.waiting(page)), (yield from js(view, "asked")), win.urlbar.perm_act.isVisible(),
                   win.urlbar.perm_act.toolTip()]
    quietperms.answer(page, True)
    yield 600
    out["allowed"] = [(yield from js(view, "asked")), state() == P.State.Granted,
                      win.urlbar.perm_act.isVisible()]
    # 3. a tab in the background: its sign only when it is shown
    page.profile().queryPermission(origin, P.PermissionType.Notifications).reset()
    front = view
    back = win.add_tab(QUrl(BASE + "/ask?back"), background=True)
    yield from until(lambda: back.url().toString().endswith("back") and not getattr(back, "loading", False))
    yield 800
    back.page()._ike_input = time.monotonic()
    yield from js(back, "ask(); 1")
    yield 600
    out["background"] = [len(quietperms.waiting(back.page())), win.urlbar.perm_act.isVisible(),
                         win.current_view() is front]
    win.set_current(back)
    yield 400
    out["shown"] = win.urlbar.perm_act.isVisible()
    menu = quietperms.menu(win)
    out["menu"] = [a.text() for a in menu.actions()]
    menu.close()
    quietperms.answer(back.page(), False)
    yield 600
    out["blocked"] = [(yield from js(back, "asked")), state() == P.State.Denied]
    out["windows"] = windows
''' % ask_site, env={"IKE_TEST_PERMS": ""}, timeout=150)
    answers, not_kept, sign = out["no_click"]
    assert answers == ["denied"] and not_kept and sign, out["no_click"]
    assert out["dropped"] is False
    n, answers, sign, tip = out["held"]
    assert n == 1 and answers == [] and sign and "127.0.0.1" in tip, out["held"]
    answers, granted, sign = out["allowed"]
    assert answers == ["granted"] * 4 and granted and not sign, out["allowed"]
    assert out["background"] == [1, False, True], out["background"]
    assert out["shown"] is True
    assert "Allow" in out["menu"] and "Block" in out["menu"] and "Not now" in out["menu"], out["menu"]
    assert out["blocked"][0] == ["denied"] and out["blocked"][1], out["blocked"]
    assert out["windows"] == [], out["windows"]            # never a window over the page


def test_the_window_comes_back_with_the_option_off(run_ike, ask_site):
    out = run_ike(JS + r'''
BASE = %r

def steps(ike, qapp, out):
    from ike import webview
    asked = []
    webview.WebPage.ask_permission = lambda self, o, t: asked.append(o) or True
    view = ike.windows[0].current_view()
    yield from load(view, BASE + "/ask")
    yield from js(view, "ask(); 1")
    yield 1200
    out["asked"] = asked
    out["answers"] = yield from js(view, "asked")
''' % ask_site, env={"IKE_TEST_PERMS": ""}, timeout=120, settings={"quiet_permissions": False})
    assert out["asked"] == ["127.0.0.1"] and out["answers"] == ["granted"], out


# --- 4. the password breach check ----------------------------------------------

def test_only_five_characters_of_the_fingerprint_leave_the_computer():
    from ike import breach
    prefix, suffix = breach.split("password")
    assert prefix + suffix == "5BAA61E4C9B93F3F0682250B6CF8331B7EE68FD8"
    req = breach.request(prefix)
    assert req.full_url == "https://api.pwnedpasswords.com/range/5BAA6"
    assert req.get_header("Add-padding") == "true"
    assert suffix not in req.full_url and "password" not in json.dumps(dict(req.header_items()))
    for bad in ("5BAA", "5BAA61", "5baa6", "../x1"):
        with pytest.raises(ValueError):
            breach.request(bad)
    answer = ("0018A45C4D1DEF81644B54AB7F969B88D65:1\r\n"
              "1E4C9B93F3F0682250B6CF8331B7EE68FD8:9659365\r\n"
              "FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF:0\r\n")
    assert breach.count_in(answer, suffix) == 9659365
    assert breach.count_in(answer, "FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF") == 0     # padding
    assert breach.count_in(answer, "0" * 35) == 0


def test_the_breach_lookup_asks_the_range_and_compares_here(monkeypatch):
    from ike import breach
    seen = []

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append((self.path, self.headers.get("Add-Padding"), self.headers.get("Cookie")))
            body = (b"1E4C9B93F3F0682250B6CF8331B7EE68FD8:42\r\n"
                    b"0000000000000000000000000000000000A:0\r\n")
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = serve(H)
    for k, v in NO_PROXY_ENV.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(breach, "URL", "http://127.0.0.1:%d/range/" % srv.server_address[1])
    try:
        prefix, suffix = breach.split("password")
        got = []
        job = breach._Lookup(prefix, suffix)
        job.found.connect(lambda s, n: got.append((s, n)))
        job.run()
    finally:
        srv.shutdown()
    assert seen == [("/range/5BAA6", "true", None)], seen
    assert got == [(suffix, 42)]


def test_the_breach_check_is_off_by_default(tmp_path):
    from ike import breach
    from ike.config import DEFAULTS, Config

    class App:
        config = Config(tmp_path / "settings.json")
    assert DEFAULTS["pw_breach_check"] is False
    check = breach.BreachCheck(None)
    check.app = App()
    assert check.check("password", "example.test") is False and not check._busy


# --- 5. "Update the system": the web engine's advisory --------------------------------

def test_the_advisory_names_versions_and_applies_only_to_older_engines(tmp_path):
    from ike import advisory
    from ike.config import Config
    assert advisory.clean(None) is None and advisory.clean({"id": "X"}) is None
    assert advisory.clean({"id": "CVE-2026-1", "qtwebengine": "6.12; rm"}) is None
    assert advisory.clean({"id": "<b>", "qtwebengine": "6.12.1"}) is None
    adv = {"id": "CVE-2026-1", "qtwebengine": "6.12.1", "chromium_security": "158.0.7444.59", "x": 1}
    assert advisory.clean(adv) == {"id": "CVE-2026-1", "qtwebengine": "6.12.1",
                                   "chromium_security": "158.0.7444.59"}
    old = {"qtwebengine": "6.12.0", "chromium_security": "157.0.7400.1"}
    assert advisory.applies(adv, old)
    assert not advisory.applies(adv, {"qtwebengine": "6.12.1", "chromium_security": "157.0.7400.1"})
    assert not advisory.applies(adv, {"qtwebengine": "6.12.0", "chromium_security": "158.0.7444.59"})
    assert not advisory.applies({"id": "A", "qtwebengine": "6.12"}, {"qtwebengine": "6.12.0"})
    assert not advisory.applies(adv, {})                     # nothing to compare: no notice
    cfg = Config(tmp_path / "settings.json")
    assert cfg["engine_advisory"] == {} and advisory.notice(cfg, old) == ""
    advisory.remember(cfg, adv)
    text = advisory.notice(cfg, old)
    assert "6.12.0" in text and "CVE-2026-1" in text and "sudo pacman -Syu" in text
    advisory.remember(cfg, None)                             # the next update information names none
    assert cfg["engine_advisory"] == {} and advisory.notice(cfg, old) == ""


def test_the_release_tool_signs_the_advisory_only_when_it_is_written(tmp_path):
    pytest.importorskip("cryptography")
    import base64

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from test_updater import PASS, load_tool, make_update_json
    key = Ed25519PrivateKey.generate()
    path = tmp_path / "keys" / "k.key"
    path.parent.mkdir()
    path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                       serialization.BestAvailableEncryption(PASS.encode())))
    pub = base64.b64encode(key.public_key().public_bytes(serialization.Encoding.Raw,
                                                         serialization.PublicFormat.Raw)).decode()
    tool = load_tool()
    upd = make_update_json(tmp_path, pub)
    _, plain = tool.make(path, tmp_path / "a", ["stable"], passphrase=PASS, update_file=upd,
                         advisory_file=tmp_path / "none.json")
    assert "engine_advisory" not in plain
    adv = tmp_path / "engine-advisory.json"
    adv.write_text(json.dumps({"id": "CVE-2026-1", "qtwebengine": "6.12.1"}))
    out, signed = tool.make(path, tmp_path / "b", ["stable"], passphrase=PASS, update_file=upd, advisory_file=adv)
    assert signed["engine_advisory"] == {"id": "CVE-2026-1", "qtwebengine": "6.12.1"}
    assert json.loads((out / "stable.json").read_bytes())["engine_advisory"] == signed["engine_advisory"]
    adv.write_text(json.dumps({"id": "CVE-2026-1", "qtwebengine": "latest"}))
    with pytest.raises(SystemExit):
        tool.make(path, tmp_path / "c", ["stable"], passphrase=PASS, update_file=upd, advisory_file=adv)


ADVISORY_CHECK = r'''
def steps(ike, qapp, out):
    import time
    told = []
    ike._notify = lambda text: told.append(text)
    result = []
    ike.updater.finished.connect(lambda kind, data: result.append(kind))
    ike.updater.run(install=False)
    t = time.time()
    while not result and time.time() - t < 60:
        yield 200
    yield 300
    out["kind"] = result[0] if result else "timeout"
    out["stored"] = ike.config["engine_advisory"]
    out["told"] = told
'''


def test_the_advisory_comes_with_the_verified_daily_check(run_ike, tmp_path):
    pytest.importorskip("cryptography")
    import base64

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from test_updater import Releases, update_env

    import ike
    key = Ed25519PrivateKey.generate()
    pub = base64.b64encode(key.public_key().public_bytes(serialization.Encoding.Raw,
                                                         serialization.PublicFormat.Raw)).decode()
    releases = Releases()
    try:
        adv = {"id": "CVE-2026-1", "qtwebengine": "999.0.0"}
        releases.publish(key, ike.__version__, min_system="0", extra={"engine_advisory": adv})
        out = run_ike(ADVISORY_CHECK, env=update_env(tmp_path, releases, pub), timeout=120)
        assert out["kind"] == "current" and out["stored"] == adv, out
        assert len(out["told"]) == 1 and "sudo pacman -Syu" in out["told"][0], out["told"]
        # a manifest whose signature does not match: nothing is taken from it
        releases.publish(key, ike.__version__, min_system="0", extra={"engine_advisory": adv}, bad_sig=True)
        out = run_ike(ADVISORY_CHECK, env=update_env(tmp_path, releases, pub), timeout=120,
                      settings={"engine_advisory": {}})
        assert out["kind"] == "error" and out["stored"] == {}, out
        assert not [t for t in out["told"] if "pacman" in t], out["told"]  # only the failed check is told
    finally:
        releases.close()


# --- 6. the battery saver ------------------------------------------------------------

def test_the_battery_saver_works_only_when_chosen_and_on_battery(tmp_path):
    from ike import battery, effects
    from ike.config import Config

    class App:
        config = Config(tmp_path / "settings.json")
        windows = []
    app = App()
    assert app.config["battery_saver"] is False
    b = battery.Battery(None)
    b.app = app
    try:
        b.set_on_battery(True)
        assert battery.saving() is False and effects.on(app.config)       # not chosen: nothing changes
        app.config["battery_saver"] = True
        b._update()                      # (start() would also ask UPower: not here)
        assert battery.saving() is True and not effects.on(app.config)
        b.set_on_battery(False)
        assert battery.saving() is False and effects.on(app.config)
    finally:
        battery._state["saving"] = False


@pytest.fixture
def upower(tmp_path):
    import shutil
    if not shutil.which("dbus-daemon"):
        pytest.skip("dbus-daemon not installed")
    pytest.importorskip("jeepney")
    daemon = subprocess.Popen(["dbus-daemon", "--session", "--nofork", "--print-address=1"],
                              stdout=subprocess.PIPE, text=True)
    address = daemon.stdout.readline().strip()
    log = tmp_path / "upower.log"
    standin = subprocess.Popen([sys.executable, str(Path(__file__).parent / "upower_standin.py"), str(log), "on"],
                               env=dict(os.environ, DBUS_SESSION_BUS_ADDRESS=address))
    for _ in range(100):
        if log.exists():
            break
        time.sleep(0.05)
    try:
        yield address, log
    finally:
        standin.kill()
        daemon.kill()
        standin.wait()
        daemon.wait()


def test_the_battery_saver_follows_upower_without_polling(run_ike, upower):
    address, log = upower
    out = run_ike(JS + r'''
LOG = %r

def steps(ike, qapp, out):
    import time
    from PyQt6.QtCore import QUrl
    from ike import battery, effects
    win = ike.windows[0]
    yield from until(lambda: ike.battery.on_battery, 5000)
    out["start"] = [ike.battery.connected, ike.battery.on_battery, battery.saving(), effects.on(ike.config)]
    # a tab in the background, left alone for two minutes: it pauses
    back = win.add_tab(QUrl("about:blank"), background=True)
    yield 800
    back.last_active = time.time() - 120
    out["rested"] = ike.battery.rest()
    out["frozen"] = bool(getattr(back, "frozen", False))
    open(LOG + ".cmd", "w").write("off")
    yield from until(lambda: not ike.battery.on_battery, 5000)
    out["plugged"] = [ike.battery.on_battery, battery.saving(), effects.on(ike.config),
                      bool(getattr(back, "frozen", False))]
''' % str(log), env={"DBUS_SYSTEM_BUS_ADDRESS": address}, timeout=120,
                  settings={"battery_saver": True, "ui_effects": True})
    assert out["start"] == [True, True, True, False], out["start"]
    assert out["rested"] == 1 and out["frozen"], out
    assert out["plugged"] == [False, False, True, False], out["plugged"]
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    # asked once at the start, then only told: no polling
    assert [c["member"] for c in calls if c.get("event") == "call"].count("Get") == 1, calls


def test_without_the_saver_nothing_connects_to_the_bus(run_ike, upower):
    address, log = upower
    out = run_ike(r'''
def steps(ike, qapp, out):
    yield 1500
    out["connected"] = ike.battery.connected
''', env={"DBUS_SYSTEM_BUS_ADDRESS": address}, timeout=90)
    assert out["connected"] is False
    assert not [line for line in log.read_text().splitlines() if '"call"' in line]
