"""User scripts: common script patterns keep working, and a page cannot use
the scripts' bridge to I.K.E. (forged messages, a replaced console.info, the
answers of GM_xmlhttpRequest), grants and @connect are enforced, and local or
private addresses are reached only when @connect names them, also through
redirects and name resolution.

The scripts run on pages of a local server. Other sites ("*.example.test")
are reached through the same server acting as an HTTP proxy, set on I.K.E.'s
own network manager; IKE_TEST_RESOLVE makes a name resolve to a private
address without a DNS server.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

import pytest

PAGE = b"""<!doctype html><html><head><title>us</title>
<script>
window.pageValue = 'from-page';
window.seenAtStart = window.early;
</script></head><body><p id="p">text</p></body></html>"""

# a page that replaces console.info before an idle script runs, and tries to
# take over the answer callbacks of the scripts in its world
EVIL = b"""<!doctype html><html><head><title>evil</title>
<script>
window.stolen = [];
window.realStringify = JSON.stringify;
console.info = function (m) { window.stolen.push(String(m)); };
JSON.stringify = function () { window.stolen.push('stringify'); return '{}'; };
window.hijack = [];
Object.getOwnPropertyNames(window).forEach(function (k) {
  if (k.indexOf('__ike_us_') === 0) {
    try { window[k] = function () { window.hijack.push(k); }; } catch (e) {}
    try { Object.defineProperty(window, k, { value: function () { window.hijack.push(k); } }); } catch (e) {}
  }
});
</script></head><body>evil</body></html>"""


class Server(ThreadingHTTPServer):
    daemon_threads = True


def make_server():
    seen = []

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            parts = urlsplit(self.path)
            host = parts.hostname or self.headers.get("Host", "").split(":")[0]
            path = parts.path if parts.scheme else self.path.split("?")[0]
            query = parts.query if parts.scheme else (self.path.split("?", 1) + [""])[1]
            seen.append([host, path])
            if path == "/page":
                body, ctype = PAGE, "text/html"
            elif path == "/evil":
                body, ctype = EVIL, "text/html"
            elif path == "/redirect":
                self.send_response(302)
                self.send_header("Location", query)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            else:
                body, ctype = json.dumps({"host": host, "path": path}).encode(), "application/json"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = Server(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, seen


@pytest.fixture
def server():
    srv, seen = make_server()
    srv2, seen2 = make_server()          # another origin on this computer
    yield srv.server_address[1], seen, srv2.server_address[1], seen2
    srv.shutdown()
    srv2.shutdown()


def script(name, grants=(), connect=(), run_at=None, body="", match="http://127.0.0.1/*"):
    head = ["// ==UserScript==", "// @name %s" % name, "// @namespace test", "// @match %s" % match]
    head += ["// @grant %s" % g for g in grants]
    head += ["// @connect %s" % c for c in connect]
    if run_at:
        head.append("// @run-at %s" % run_at)
    head.append("// ==/UserScript==")
    return "\n".join(head) + "\n" + body + "\n"


# runs inside the browser: installs SCRIPTS, loads PAGES, records RESULT_JS of each
STEPS = r'''
import json
from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtNetwork import QNetworkProxy

def steps(ike, qapp, out):
    from ike.userscripts import gather, script_id, parse_meta
    ike.network.setProxy(QNetworkProxy(QNetworkProxy.ProxyType.HttpProxy, "127.0.0.1", PORT))
    QGuiApplication.clipboard().setText("untouched")
    sids = {}
    for text in SCRIPTS:
        sids[parse_meta(text)["name"]] = ike.userscripts.store(gather(text))
    out["sids"] = sids
    us = ike.userscripts
    if hasattr(us, "tokens"):
        out["tokens"] = {n: us.tokens.get(s) for n, s in sids.items()}
    else:                            # 1.5.1 and older: one token for every script
        out["tokens"] = {n: us.token.split(":")[1] for n in sids}
    yield 300
    v = ike.windows[0].current_view()
    for i, page in enumerate(PAGES):
        done = {}
        v.page().loadFinished.connect(lambda ok, done=done: done.setdefault("ok", ok))
        v.load(QUrl(page))
        while "ok" not in done:
            yield 20
        yield WAIT
        for js in PAGE_JS.get(str(i), []):
            js = js.replace("__TOKENS__", json.dumps(out["tokens"])).replace("__SIDS__", json.dumps(sids))
            v.page().runJavaScript(js, 0)
            yield 300
        res = {}
        v.page().runJavaScript(RESULT_JS, 0, lambda r, res=res: res.setdefault("r", r))
        while "r" not in res:
            yield 20
        out.setdefault("pages", []).append(json.loads(res["r"]))
    out["clipboard"] = QGuiApplication.clipboard().text()
    out["tabs"] = [w.url().toString() for w in ike.windows[0].views]
'''

RESULT_JS = """(window.realStringify || JSON.stringify)((function () {
  var o = {}, a = document.documentElement.attributes;
  for (var i = 0; i < a.length; i++) if (a[i].name.indexOf('data-') === 0) o[a[i].name.slice(5)] = a[i].value;
  o.pageVar = window.fromScript === undefined ? null : window.fromScript;
  o.seenAtStart = window.seenAtStart === undefined ? null : window.seenAtStart;
  o.stolen = window.stolen || null;
  o.hijack = window.hijack || null;
  return o;
})())"""


def run_scripts(run_ike, port, scripts, pages, page_js=None, wait=1500, env=None):
    head = "SCRIPTS = %r\nPAGES = %r\nPAGE_JS = %r\nRESULT_JS = %r\nPORT = %d\nWAIT = %d\n" % (
        scripts, pages, page_js or {}, RESULT_JS, port, wait)
    return run_ike(head + STEPS, env=env, timeout=120)


def mark(key, value):
    return "document.documentElement.setAttribute('data-%s', %s);" % (key, value)


# --- common patterns ---------------------------------------------------------

def test_common_patterns(run_ike, server):
    port, seen, port2, seen2 = server
    scripts = [
        script("none", ["none"], body="window.fromScript = 'none:' + window.pageValue + ':' + typeof GM_setValue + ':' + GM_info.script.name;"),
        script("start", ["none"], run_at="document-start",
               body="window.early = 'early';"),
        script("values", ["GM_getValue", "GM_setValue", "GM_addStyle"], run_at="document-end",
               body="var n = GM_getValue('n', 0) + 1; GM_setValue('n', n); GM_addStyle('#p{color:red}');"
                    + mark("values", "n") + mark("styled", "getComputedStyle(document.getElementById('p')).color")),
        script("xhr", ["GM_xmlhttpRequest"], connect=["127.0.0.1"],
               body="GM_xmlhttpRequest({url: 'http://127.0.0.1:%d/data', onload: function (r) {%s}, "
                    "onerror: function (e) {%s}});" % (port2, mark("xhr", "JSON.parse(r.responseText).path"),
                                                       mark("xhr", "'error'"))),
        script("gm4", ["GM.getValue", "GM.setValue", "GM.xmlHttpRequest"], connect=["127.0.0.1"],
               body="GM.setValue('a', 5).then(function () { return GM.getValue('a'); }).then(function (v) {"
                    + mark("gm4value", "v") + "return GM.xmlHttpRequest({url: 'http://127.0.0.1:%d/gm4'});"
                    "}).then(function (r) {%s});" % (port2, mark("gm4xhr", "JSON.parse(r.responseText).path"))),
        script("unsafe", ["unsafeWindow", "GM_getValue"],
               body=mark("unsafe", "unsafeWindow.pageValue + ':' + typeof GM_getValue")),
        script("sameorigin", ["GM_xmlhttpRequest"],
               body="GM_xmlhttpRequest({url: '/same', onload: function (r) {%s}});"
                    % mark("same", "JSON.parse(r.responseText).path")),
    ]
    base = "http://127.0.0.1:%d/page" % port
    # stored values reach new pages when they are saved (1.5 s after the change)
    out = run_scripts(run_ike, port, scripts, [base, base + "?2"], wait=2500)
    first, second = out["pages"]
    assert first["pageVar"] == "none:from-page:undefined:none"      # page world, no GM functions
    assert first["seenAtStart"] == "early"                            # document-start before the page
    assert first["values"] == "1" and second["values"] == "2"         # values kept between loads
    assert first["styled"] == "rgb(255, 0, 0)"
    assert first["xhr"] == "/data" and first["gm4xhr"] == "/gm4" and first["gm4value"] == "5"
    assert first["unsafe"] == "from-page:function"
    assert first["same"] == "/same"


def test_grants(run_ike, server):
    port = server[0]
    probe = ("['GM_getValue','GM_setValue','GM_deleteValue','GM_listValues','GM_addStyle','GM_addElement',"
             "'GM_xmlhttpRequest','GM_setClipboard','GM_openInTab','GM_notification','GM_download',"
             "'GM_getResourceText','GM_getResourceURL','GM_registerMenuCommand','GM_log']"
             ".filter(function (n) { return typeof eval(n) === 'function'; }).join(',') + '|' + "
             "Object.keys(GM).sort().join(',') + '|' + typeof GM_info")
    scripts = [
        script("nogrant", body=mark("nogrant", probe)),
        script("nonegrant", ["none"], body=mark("nonegrant", probe)),
        script("onlyget", ["GM_getValue"], body=mark("onlyget", probe)),
        script("clipboard", ["GM_setClipboard", "GM.openInTab"], body=mark("clipboard", probe)),
        script("all", ["GM_getValue", "GM_setValue", "GM_deleteValue", "GM_listValues", "GM_addStyle",
                       "GM_addElement", "GM_xmlhttpRequest", "GM_setClipboard", "GM_openInTab",
                       "GM_notification", "GM_download", "GM_getResourceText", "GM_getResourceURL",
                       "GM_registerMenuCommand", "GM_log"], body=mark("all", probe)),
    ]
    out = run_scripts(run_ike, port, scripts, ["http://127.0.0.1:%d/page" % port])
    p = out["pages"][0]
    assert p["nogrant"] == "|info|object"
    assert p["nonegrant"] == "|info|object"
    assert p["onlyget"] == "GM_getValue|getValue,info|object"
    # GM_x and GM.x are the same function: granting one gives both
    assert p["clipboard"] == "GM_setClipboard,GM_openInTab|info,openInTab,setClipboard|object"
    assert p["all"].split("|")[0].count(",") == 14
    # only scripts granted something that needs I.K.E. get a token
    assert out["tokens"]["nogrant"] is None and out["tokens"]["onlyget"] is None
    assert out["tokens"]["clipboard"] and out["tokens"]["clipboard"] != out["tokens"]["all"]


# --- a page attacking the bridge ---------------------------------------------

def test_forged_messages(run_ike, server):
    """Messages written by the page: no token, a wrong token, another script's
    token, an operation the script was not granted."""
    port, seen, port2, _seen2 = server
    scripts = [
        script("clip", ["GM_setClipboard"], body=""),
        script("getonly", ["GM_getValue", "GM_xmlhttpRequest"], body=""),
    ]
    forged = """(function () {
      var T = __TOKENS__, S = __SIDS__, P = '\\u0001ike-gm:';
      function m(tok, id, op, d) { console.info(P + tok + ':' + JSON.stringify({id: id, op: op, d: d})); }
      m('', S.clip, 'clip', {text: 'no token'});
      m('0123456789abcdef0123456789abcdef', S.clip, 'clip', {text: 'wrong token'});
      m(T.getonly, S.clip, 'clip', {text: 'other script token'});
      m(T.getonly, S.getonly, 'clip', {text: 'not granted'});
      m(T.getonly, S.getonly, 'tab', {url: 'http://127.0.0.1:%d/tab'});
      m(T.clip, S.clip, 'xhr', {rid: '1', url: 'http://127.0.0.1:%d/forged'});
      console.info(P + T.clip);
      console.info(P + T.clip + ':not json');
    })();""" % (port2, port2)
    out = run_scripts(run_ike, port, scripts, ["http://127.0.0.1:%d/page" % port], {"0": [forged]})
    assert out["clipboard"] == "untouched"
    assert ["127.0.0.1", "/forged"] not in seen + _seen2
    assert ["127.0.0.1", "/tab"] not in _seen2
    assert not any(u.endswith("/tab") for u in out["tabs"])


def test_page_replaces_console_before_idle_script(run_ike, server):
    """The page replaces console.info and JSON.stringify and tries to take over
    the answer callback before a script in its world (unsafeWindow) starts at
    document-idle: the script still works and nothing reaches the page."""
    port, seen, port2, _seen2 = server
    scripts = [script("idle", ["unsafeWindow", "GM_setClipboard", "GM_xmlhttpRequest"],
                      connect=["127.0.0.1"], match="http://127.0.0.1/evil",
                      body="GM_setClipboard('from script');"
                           "GM_xmlhttpRequest({url: 'http://127.0.0.1:%d/idle', onload: function (r) {%s}});"
                           % (port2, mark("idle", "JSON.parse(r.responseText).path")))]
    out = run_scripts(run_ike, port, scripts, ["http://127.0.0.1:%d/evil" % port])
    p = out["pages"][0]
    assert out["clipboard"] == "from script"
    assert p["idle"] == "/idle"
    assert not any("ike-gm" in s for s in p["stolen"]), p["stolen"]
    assert p["hijack"] == []


# --- @connect and local addresses --------------------------------------------

def _xhr_script(name, url, connect=(), grants=("GM_xmlhttpRequest",)):
    return script(name, grants, connect=connect,
                  body="GM_xmlhttpRequest({url: %s, onload: function (r) {%s}, onerror: function (e) {%s}});"
                       % (json.dumps(url), mark(name, "'ok:' + r.status + ':' + JSON.parse(r.responseText).host"),
                          mark(name, "'refused'")))


def test_connect(run_ike, server):
    port, seen, port2, seen2 = server
    scripts = [
        # public sites (through the stand-in proxy)
        _xhr_script("noconnect", "http://api.example.test/a"),
        _xhr_script("listed", "http://api.example.test/b", ["example.test"]),
        _xhr_script("sub", "http://deep.api.example.test/c", ["api.example.test"]),
        _xhr_script("notlisted", "http://other.example.test/d", ["api.example.test"]),
        _xhr_script("star", "http://star.example.test/e", ["*"]),
        # this computer and private networks
        _xhr_script("local", "http://127.0.0.1:%d/f" % port2),
        _xhr_script("localstar", "http://127.0.0.1:%d/g" % port2, ["*"]),
        _xhr_script("localnamed", "http://127.0.0.1:%d/h" % port2, ["127.0.0.1"]),
        _xhr_script("localself", "http://127.0.0.1:%d/i" % port2, ["self"]),
        _xhr_script("localhost", "http://localhost:%d/j" % port2),
        _xhr_script("decimal", "http://2130706433:%d/k" % port2),
        _xhr_script("mapped", "http://[::ffff:127.0.0.1]:%d/l" % port2),
        _xhr_script("lan", "http://192.168.1.1/m"),
        _xhr_script("resolves", "http://private.example.test/n"),
        _xhr_script("resolvesnamed", "http://private.example.test/o", ["private.example.test"]),
        _xhr_script("file", "file:///etc/passwd"),
    ]
    out = run_scripts(run_ike, port, scripts, ["http://127.0.0.1:%d/page" % port],
                      env={"IKE_TEST_RESOLVE": "private.example.test=10.1.2.3"}, wait=2500)
    p = out["pages"][0]
    assert p["noconnect"] == "ok:200:api.example.test"
    assert p["listed"] == "ok:200:api.example.test"
    assert p["sub"] == "ok:200:deep.api.example.test"
    assert p["notlisted"] == "refused"
    assert p["star"] == "ok:200:star.example.test"
    assert p["local"] == "refused" and p["localstar"] == "refused"
    assert p["localnamed"] == "ok:200:127.0.0.1" and p["localself"] == "ok:200:127.0.0.1"
    assert p["localhost"] == "refused" and p["decimal"] == "refused" and p["mapped"] == "refused"
    assert p["lan"] == "refused" and p["resolves"] == "refused" and p["file"] == "refused"
    # a resolved private name is allowed when @connect names it (the request then
    # goes through the stand-in proxy, which answers for every name)
    assert p["resolvesnamed"] == "ok:200:private.example.test"
    reached = {path for _h, path in seen + seen2}
    for path in "dfgjklmn":
        assert "/" + path not in reached


def test_redirect_to_private_address(run_ike, server):
    port, seen, port2, seen2 = server
    secret = "http://127.0.0.1:%d/secret" % port2
    scripts = [
        _xhr_script("tolocal", "http://api.example.test/redirect?" + secret),
        _xhr_script("tolocalnamed", "http://api.example.test/redirect?" + secret, ["api.example.test", "127.0.0.1"]),
        _xhr_script("toresolved", "http://api.example.test/redirect?http://private.example.test/hidden"),
        _xhr_script("topublic", "http://api.example.test/redirect?http://www.example.test/fine"),
        _xhr_script("tounlisted", "http://api.example.test/redirect?http://evil.example.test/x", ["api.example.test"]),
    ]
    out = run_scripts(run_ike, port, scripts, ["http://127.0.0.1:%d/page" % port],
                      env={"IKE_TEST_RESOLVE": "private.example.test=10.1.2.3"}, wait=2500)
    p = out["pages"][0]
    assert p["tolocal"] == "refused" and p["toresolved"] == "refused" and p["tounlisted"] == "refused"
    assert p["tolocalnamed"] == "ok:200:127.0.0.1"
    assert p["topublic"] == "ok:200:www.example.test"
    reached = [path for _h, path in seen + seen2]
    assert reached.count("/secret") == 1                   # only by the script that names it
    assert "/hidden" not in reached and "/x" not in reached


def test_install_dialog_lists_connect():
    from ike.userscripts import UserScripts, parse_meta
    meta = parse_meta(script("d", ["GM_xmlhttpRequest"], connect=["api.example.test", "self"]))
    text = UserScripts.describe(None, meta)
    assert "api.example.test, self" in text and "GM_xmlhttpRequest" in text


def test_address_rules():
    from ike.userscripts import connect_rule, granted, is_local_address, is_local_name
    for a in ("127.0.0.1", "10.2.3.4", "172.16.0.1", "172.31.255.255", "192.168.0.1", "169.254.1.1",
              "0.0.0.0", "100.64.0.1", "::1", "::", "fc00::1", "fd12::1", "fe80::1", "::ffff:192.168.1.1",
              "::127.0.0.1"):
        assert is_local_address(a), a
    for a in ("8.8.8.8", "172.32.0.1", "2001:4860::8888", "1.1.1.1", "::ffff:8.8.8.8"):
        assert not is_local_address(a), a
    for h in ("localhost", "LocalHost.", "a.localhost", "printer.local", "2130706433", "0x7f.1", "[::1]"):
        assert is_local_name(h), h
    assert not is_local_name("example.com") and not is_local_name("local.example.com")
    assert connect_rule([], "site.test", "api.test") == (True, False)
    assert connect_rule(["*"], "site.test", "api.test") == (True, False)
    assert connect_rule(["self"], "Site.test", "site.test") == (True, True)
    assert connect_rule(["self"], "site.test", "sub.site.test") == (True, True)
    assert connect_rule(["api.test"], "site.test", "x.api.test") == (True, True)
    assert connect_rule(["api.test"], "site.test", "badapi.test") == (False, False)
    assert connect_rule(["*.api.test"], "site.test", "api.test") == (True, True)
    assert granted(["GM_xmlhttpRequest", "GM.xmlHttpRequest", "GM.getResourceUrl", "none",
                    "unsafeWindow", "GM_"]) == ["getresourceurl", "xmlhttprequest"]


def test_connect_of_scripts_installed_before(tmp_path, monkeypatch):
    """Scripts installed by 1.5.1 have no "connect" entry: it is read from their code."""
    import ike.userscripts as us
    monkeypatch.setattr(us, "DIR", tmp_path)
    (tmp_path / "abc.user.js").write_text(script("old", ["GM_xmlhttpRequest"], connect=["api.test"]), "utf-8")
    obj = us.UserScripts.__new__(us.UserScripts)
    obj.scripts = {"abc": {"name": "old", "grant": ["GM_xmlhttpRequest"]}}
    assert obj._connect("abc") == ["api.test"]
