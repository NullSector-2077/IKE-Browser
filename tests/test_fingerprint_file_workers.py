"""Workers a site starts from files of its own (experiment, not in 1.1.18).

`new Worker("/w.js")` runs a script Qt WebEngine cannot add anything to, so
until now it saw the real values (graphics card, cores). fingerprint.js now
starts such a worker from a blob address holding the protection, which then
loads the site's script from its real address. This test checks both halves:

- protection: classic and module workers from files, a worker such a worker
  starts from a relative address, and a script served with a wrong type, all
  report the same graphics card and cores as the page;
- nothing else changes for the site: every functional result (location,
  relative importScripts / fetch / XMLHttpRequest / Request / import, messages,
  the error events of a missing script, a syntax error, an exception, a
  SharedWorker still shared) is exactly the one the same page gets with the
  shield off.

And where it must not apply: a page with a content security policy (the blob
address would be refused or reported) keeps its workers as before, with no
policy violation; a SharedWorker is left alone (a blob address would split
it); a worker started before I.K.E. has seen the page's headers (while the
page loads) is left alone.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

GL_PROBE = r"""
function probe() {
  var out = [];
  ['webgl', 'webgl2'].forEach(function (kind) {
    try {
      var gl = new OffscreenCanvas(4, 4).getContext(kind);
      if (!gl) { out.push('no ' + kind); return; }
      var exts = gl.getSupportedExtensions() || [];
      var d = gl.getExtension('WEBGL_debug_renderer_info');
      out.push([d ? gl.getParameter(d.UNMASKED_VENDOR_WEBGL) : null,
                d ? gl.getParameter(d.UNMASKED_RENDERER_WEBGL) : null,
                exts.indexOf('WEBGL_debug_renderer_info') >= 0 || !!d]);
    } catch (e) { out.push('error ' + e); }
  });
  out.push(navigator.hardwareConcurrency);
  return out;
}
"""

FILES = {
    "/w/helper.js": ("self.HELPER = 'helper from /w/';", "text/javascript"),
    "/helper.js": ("self.HELPER = 'WRONG: helper from /';", "text/javascript"),
    "/w/data.txt": ("data from /w/", "text/plain"),
    "/data.txt": ("WRONG: data from /", "text/plain"),
    "/w/dep.js": ("export var DEP = 'dep from /w/';", "text/javascript"),
    "/w/classic.js": (GL_PROBE + r"""
importScripts('helper.js');
var F = { loc: location.href, str: String(location), path: location.pathname, helper: self.HELPER,
          isLoc: location instanceof WorkerLocation, req: new Request('data.txt').url,
          isReq: new Request('data.txt') instanceof Request, name: self.name,
          natives: [fetch, importScripts, XMLHttpRequest.prototype.open, Request, WebSocket, EventSource,
                    Object.getOwnPropertyDescriptor(WorkerLocation.prototype, 'href').get,
                    WorkerLocation.prototype.toString, Worker].map(function (f) {
                      return [Function.prototype.toString.call(f), f.name, f.length]; }) };
F.entries = performance.getEntriesByType('resource').map(function (e) { return e.name; });
F.all = performance.getEntries().length;
var seen = [];
new PerformanceObserver(function (l) {
  l.getEntries().forEach(function (e) { seen.push(e.name); });
}).observe({ type: 'resource', buffered: true });
var D = { stack: String(new Error('x').stack) };
var x = new XMLHttpRequest();
x.open('GET', 'data.txt', false);
x.send();
F.xhr = x.responseText;
onmessage = function (e) { postMessage({ echo: e.data }); };
fetch('data.txt').then(function (r) { return r.text(); }).then(function (t) {
  F.fetch = t;
  return new Promise(function (ok) {
    var n = new Worker('nested.js');
    n.onmessage = function (e) { ok(e.data); };
    n.onerror = function () { ok('nested error'); };
    setTimeout(function () { ok('nested timeout'); }, 4000);
  });
}).then(function (nested) {
  F.nested = nested.F;
  D.seen = seen.slice().sort();
  postMessage({ F: F, P: probe(), nestedP: nested.P, D: D });
}, function (e) { postMessage({ F: 'error ' + e }); });
""", "text/javascript"),
    "/w/nested.js": (GL_PROBE + r"""
importScripts('helper.js');
postMessage({ F: [location.href, self.HELPER], P: probe() });
""", "text/javascript"),
    "/w/module.js": (GL_PROBE + r"""
import { DEP } from './dep.js';
var F = { loc: location.href, meta: import.meta.url, dep: DEP,
          entries: performance.getEntriesByType('resource').map(function (e) { return e.name; }) };
var D = { stack: String(new Error('x').stack) };
F.fetch = await (await fetch('data.txt')).text();
F.dyn = (await import('./dep.js')).DEP;
onmessage = function (e) { postMessage({ echo: e.data }); };
postMessage({ F: F, P: probe(), D: D });
""", "text/javascript"),
    "/w/plain.txt": (GL_PROBE + "var a = 1;\npostMessage({ F: ['plain', location.pathname], P: probe() });",
                     "text/plain"),
    "/w/syntax.js": ("var a = 1;\npostMessage(", "text/javascript"),
    "/w/throw.js": ("var a = 1;\n  null.x;", "text/javascript"),
    "/w/shared.js": ("var n = 0; onconnect = function (e) { e.ports[0].postMessage([++n, location.pathname]); };",
                     "text/javascript"),
}

PAGE = r"""<!doctype html><html><head><title>file workers</title>%(meta)s</head><body>
<script>
""" + GL_PROBE + r"""
var viol = [];
document.addEventListener('securitypolicyviolation', function (e) { viol.push([e.violatedDirective, e.blockedURI]); });
var origin = location.origin;
function strip(s) { return typeof s === 'string' ? s.split(origin).join('') : s; }
function talk(make, ping, now) {
  return new Promise(function (ok) {
    var log = [], t = setTimeout(function () { log.push('timeout'); ok(log); }, 6000);
    try {
      var w = make();
      if (now) w.postMessage('now');
      w.onmessage = function (e) {
        log.push(['message', e.data]);
        if (ping && !(e.data && e.data.echo === 'ping')) { if (log.length === 1) w.postMessage('ping'); return; }
        clearTimeout(t); ok(log);
      };
      w.onerror = function (e) {
        log.push(['error', e.constructor.name, e.message || '', strip(e.filename), e.lineno, e.colno,
                  e.cancelable]);
        clearTimeout(t); setTimeout(function () { ok(log); }, 200);
      };
    } catch (e) { clearTimeout(t); ok(['throw ' + e]); }
  });
}
// a worker started while the page loads, before I.K.E. has seen its headers
var early = talk(function () { return new Worker('/w/classic.js'); }, false);
window.go = async function () {
  var R = { page: probe() };
  R.early = await early;
  await fetch('/log?reset');
  R.classic = await talk(function () { return new Worker('/w/classic.js?go'); }, true, true);
  R.requests = (await (await fetch('/log')).json()).filter(function (x) {
    return x[0].indexOf('?go') >= 0 || String(x[1]).indexOf('?go') >= 0; }).map(function (x) { return x.map(strip); });
  R.classic_named = await talk(function () { return new Worker('/w/classic.js', { name: 'n1', type: 'classic' }); }, false);
  R.module = await talk(function () { return new Worker('/w/module.js', { type: 'module' }); }, true, true);
  R.plain = await talk(function () { return new Worker('/w/plain.txt'); }, false);
  R.missing = await talk(function () { return new Worker('/w/missing.js'); }, false);
  R.missing_module = await talk(function () { return new Worker('/w/missing.js', { type: 'module' }); }, false);
  R.syntax = await talk(function () { return new Worker('/w/syntax.js'); }, false);
  R.throws = await talk(function () { return new Worker('/w/throw.js'); }, false);
  R.shared = await new Promise(function (ok) {
    var a = new SharedWorker('/w/shared.js', 's'), b = new SharedWorker('/w/shared.js', 's'), got = [];
    function f(e) { got.push(e.data); if (got.length === 2) ok(got); }
    a.port.onmessage = f; b.port.onmessage = f;
    setTimeout(function () { ok(got); }, 4000);
  });
  var w = new Worker('/w/helper.js');
  R.looks = [w instanceof Worker, w.constructor === Worker, Object.getPrototypeOf(w) === Worker.prototype,
             Function.prototype.toString.call(Worker), Worker.name, Worker.length];
  w.terminate();
  R.viol = viol;
  R.entries = performance.getEntriesByType('resource').map(function (e) { return strip(e.name); }).sort();
  window.R = JSON.stringify(R);
};
</script></body></html>"""


@pytest.fixture
def site():
    files = {k: (v[0].encode(), v[1]) for k, v in FILES.items()}
    log = []

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            path = self.path.split("?")[0]
            headers = {}
            if path == "/log":
                if self.path.endswith("reset"):
                    del log[:]
                body, kind = json.dumps(log).encode(), "application/json"
            elif path in files:
                log.append([self.path, self.headers.get("Referer"), self.headers.get("Sec-Fetch-Dest")])
                body, kind = files[path]
            elif path.startswith("/w/") or path == "/favicon.ico":
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            else:
                kind = "text/html; charset=utf-8"
                meta = ""
                if path == "/csp":
                    headers["Content-Security-Policy"] = "worker-src 'self'"
                elif path == "/csp-report-only":
                    headers["Content-Security-Policy-Report-Only"] = "default-src 'self' 'unsafe-inline'"
                elif path == "/csp-neutral":
                    headers["Content-Security-Policy"] = "frame-ancestors 'self'; upgrade-insecure-requests"
                elif path == "/meta-csp":
                    meta = "<meta http-equiv=\"Content-Security-Policy\" content=\"worker-src 'self'\">"
                body = (PAGE % {"meta": meta}).encode()
            self.send_response(200)
            self.send_header("Content-Type", kind)
            for k, v in headers.items():
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield "http://127.0.0.1:%d" % srv.server_address[1]
    srv.shutdown()


STEPS = r'''
import json
from PyQt6.QtCore import QUrl

def steps(ike, qapp, out):
    for path in PATHS:
        v = ike.windows[0].current_view()
        done = {}
        v.page().loadFinished.connect(lambda ok, done=done: done.setdefault("ok", ok))
        v.load(QUrl(SITE + path))
        while "ok" not in done:
            yield 20
        yield 400                       # I.K.E. has looked at the page's headers
        v.page().runJavaScript("window.go()", 0)
        for _ in range(1200):
            res = {}
            v.page().runJavaScript("window.R || ''", 0, lambda r, res=res: res.setdefault("r", r))
            while "r" not in res:
                yield 20
            if res["r"]:
                out[path] = json.loads(res["r"])
                break
            yield 50
'''

FLAGS = "--no-sandbox --enable-unsafe-swiftshader --use-angle=swiftshader --ignore-gpu-blocklist"
PAGES = ["/page", "/csp", "/csp-report-only", "/csp-neutral", "/meta-csp"]


def run(run_ike, site, level, paths=PAGES):
    out = run_ike("SITE = %r\nPATHS = %r\n" % (site, paths) + STEPS, settings={"shield_level": level},
                  env={"QTWEBENGINE_CHROMIUM_FLAGS": FLAGS}, timeout=240)
    missing = [p for p in paths if p not in out]
    assert not missing, ("no result", missing, out.get("_stderr", "")[-2000:])
    return {p: out[p] for p in paths}


WORKERS = ("early", "classic", "classic_named", "module", "plain", "missing", "missing_module",
           "syntax", "throws")


def functional(r):
    """What a worker does for the site, without the values the protection changes."""
    out = {}
    for k in WORKERS + ("shared",):
        def clean(x):
            if isinstance(x, dict):
                return {a: clean(b) for a, b in x.items() if a not in ("P", "nestedP", "D")}
            if isinstance(x, list):
                return [clean(b) for b in x]
            return x
        out[k] = clean(r[k])
    return out


def report(r, k):
    """The message of worker k that carries its values."""
    found = [m[1] for m in r[k] if m[0] == "message" and isinstance(m[1], dict) and "P" in m[1]]
    assert found, (k, r[k])
    return found[0]


def card(r, k):
    """[webgl, webgl2, cores] reported by worker k."""
    return report(r, k)["P"]


@pytest.mark.parametrize("level", ["balanced", "strict"])
def test_file_workers_protected_and_unchanged(run_ike, site, level):
    off = run(run_ike, site, "off")
    on = run(run_ike, site, level)
    real = off["/page"]["page"]
    page = on["/page"]["page"]
    assert real != page, ("the page itself is not protected?", real, page)

    for path in PAGES:
        # 1. nothing changes for the site: every functional result is the one
        #    the same page gets with the shield off
        assert functional(on[path]) == functional(off[path]), path
        assert on[path]["looks"] == off[path]["looks"], path
        assert on[path]["viol"] == off[path]["viol"], path
    o = off["/page"]
    # (sanity: the page really exercises what it claims, shield off)
    assert report(o, "classic")["F"]["helper"] == "helper from /w/", o["classic"]
    assert report(o, "classic")["F"]["fetch"] == "data from /w/" == report(o, "classic")["F"]["xhr"]
    assert ["message", {"echo": "now"}] in o["classic"], o["classic"]
    for k in ("classic", "module"):
        assert ["message", {"echo": "ping"}] in o[k], o[k]
    assert report(o, "module")["F"]["dyn"] == "dep from /w/", o["module"]
    assert o["missing"][0][:2] == ["error", "Event"], o["missing"]
    assert o["syntax"][0][2] == "Uncaught SyntaxError: Unexpected end of input", o["syntax"]
    assert report(o, "plain")["F"] == ["plain", "/w/plain.txt"], o["plain"]
    assert [x[0] for x in o["shared"]] == [1, 2], o["shared"]
    assert o["looks"][:3] == [True, True, True] and "[native code]" in o["looks"][3], o["looks"]
    assert off["/csp"]["viol"] == [] and off["/meta-csp"]["viol"] == []

    # 2. protection: the workers from files of the page without a policy
    #    (and with only a policy that does not concern workers) report the
    #    page's own protected values
    for path in ("/page", "/csp-neutral"):
        r = on[path]
        for k in ("classic", "classic_named", "module", "plain"):
            assert card(r, k) == r["page"], (path, k, card(r, k), r["page"])
            assert card(r, k) != real, (path, k)
        assert report(r, "classic")["nestedP"] == r["page"], (path, r["classic"])

    # 3. left as before (real values): a page with a policy that concerns
    #    workers, enforced, report-only or in a <meta> tag, and a worker
    #    started while the page loads
    for path in ("/csp", "/csp-report-only", "/meta-csp"):
        assert card(on[path], "classic") == real, path
    assert card(on["/page"], "early") == real

    # 4. measured, known differences a site could see (see CHANGELOG):
    # - the page's resource timing: a classic worker's script is fetched by
    #   the worker (importScripts), so it is no longer among the page's
    #   entries; a module worker's scripts still are (a failed one is too);
    # - the same in a worker, for a classic worker it starts from a file;
    # - a stack trace taken in a classic worker's top-level code ends with
    #   one more line, the blob that loaded it (modules: the same as before).
    from collections import Counter
    page_off, page_on = Counter(off["/page"]["entries"]), Counter(on["/page"]["entries"])
    assert page_off - page_on == Counter({"/w/classic.js?go": 1, "/w/classic.js": 1, "/w/plain.txt": 1, "/w/syntax.js": 1,
                                          "/w/throw.js": 1}), (page_off, page_on)
    assert page_on - page_off == Counter({"/w/missing.js": 1}), (page_off, page_on)
    seen_off, seen_on = report(off["/page"], "classic")["D"]["seen"], report(on["/page"], "classic")["D"]["seen"]
    assert [u for u in seen_off if u not in seen_on] == [site + "/w/nested.js"], (seen_off, seen_on)
    stack_off, stack_on = (report(x["/page"], "classic")["D"]["stack"].splitlines() for x in (off, on))
    assert stack_on[:-1] == stack_off and stack_on[-1].strip().startswith("at blob:"), (stack_off, stack_on)
    assert report(on["/page"], "module")["D"] == report(off["/page"], "module")["D"]
    # - what the site's server sees: the script is asked for by importScripts
    #   (Sec-Fetch-Dest "script", not "worker") and, as everything the worker
    #   asks for, with no Referer header (a blob address is never sent)
    req_off, req_on = off["/page"]["requests"], on["/page"]["requests"]
    assert req_off[0] == ["/w/classic.js?go", "/page", "worker"], req_off
    assert any(r[1] == "/w/classic.js?go" for r in req_off), req_off
    assert req_on == [["/w/classic.js?go", None, "script"]], req_on
