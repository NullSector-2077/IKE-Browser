"""Workers on pages that use Trusted Types (1.1.31: Cloudflare's Turnstile).

Cloudflare's challenge frame allows only its own Trusted Types policies by
name (`trusted-types <name> default; require-trusted-types-for 'script';
worker-src blob:`) and starts its workers from blob addresses wrapped by its
policy. I.K.E. adds its protection to a worker by starting it from a new blob
address (the protection, then the site's script), made trusted by a policy of
its own. The page refuses that policy; until 1.1.31 the bare address went on,
the page's own default policy turned it into an address worker-src refuses,
and the worker never started: Turnstile failed at Balanced, Kontrol and
Maximum and worked at Compatibility (verified on turnstile.pages.dev, see
CHANGELOG.md). The refused policy's name was also 'p' + the site's seed, which
the page reads in the refusal's report (securitypolicyviolation, `sample`).

Now:
- where the page refuses the protection's policy, the worker starts with the
  page's own TrustedScriptURL, as the page asked: it runs, and the page's own
  default policy never sees an address of I.K.E.'s;
- the policy is asked for once in a realm, under a random name (another one
  in every document, never the seed);
- where the page's Trusted Types allow the policy, the worker keeps the
  protection (the same noise as the page, another on every site);
- a worker from a file at Kontrol and Maximum still never runs without the
  protection (refused, as before).

SIMULATION: a local server; 127.0.0.1 and localhost are two sites. The
"allowlist" page copies the policy of Cloudflare's frame and adds a default
policy that counts what reaches it and turns it into an address no worker can
start from, as Turnstile's own does (with the code of 1.1.30 the page's
workers end with "error" here, as Turnstile's did).
"""

import http.server
import json
import threading

import pytest

LEVELS = ["balanced", "strict", "maximum"]

COMMON = r"""
var V = [];
document.addEventListener('securitypolicyviolation', function (e) {
  V.push(e.violatedDirective + ':' + e.sample);
});
function hash(d) {
  var h = 2166136261;
  for (var i = 0; i < d.length; i++) { h ^= d[i]; h = Math.imul(h, 16777619); }
  return (h >>> 0).toString(16);
}
function draw(c) {
  var x = c.getContext('2d'), g = x.createLinearGradient(0, 0, 96, 40);
  g.addColorStop(0, '#f60'); g.addColorStop(1, '#069');
  x.fillStyle = g; x.fillRect(0, 0, 96, 40);
  x.fillStyle = 'rgba(102, 204, 0, 0.7)'; x.font = '14px sans-serif'; x.fillText('Cwm fjord', 4, 24);
  return hash(x.getImageData(0, 0, 96, 40).data);
}
var WORKER = 'var hash = ' + hash.toString() + ';\nvar draw = ' + draw.toString() + ';\n' +
  'postMessage({pic: draw(new OffscreenCanvas(96, 40))});';
function start(make) {
  return new Promise(function (ok) {
    var w;
    try { w = make(); } catch (e) { return ok('throw ' + e.name); }
    var t = setTimeout(function () { ok('timeout'); }, 4000);
    w.onmessage = function (e) { clearTimeout(t); ok(e.data.pic ? 'pic:' + e.data.pic : 'data'); };
    w.onerror = function () { clearTimeout(t); ok('error'); };
  });
}
function blobUrl() { return URL.createObjectURL(new Blob([WORKER], { type: 'text/javascript' })); }
"""

ALLOWLIST = r"""<!doctype html><title>tt</title><body><script>
""" + COMMON + r"""
window.tripped = 0;
var mine = trustedTypes.createPolicy('site', { createScriptURL: function (u) { return u; } });
trustedTypes.createPolicy('default', { createScriptURL: function (u) {
  window.tripped++;
  return '/refused.js';
} });
window.__run = async function () {
  var a = await start(function () { return new Worker(mine.createScriptURL(blobUrl())); });
  var b = await start(function () { return new Worker(mine.createScriptURL(blobUrl())); });
  var f = await start(function () { return new Worker(mine.createScriptURL('/w.js')); });
  await new Promise(function (ok) { setTimeout(ok, 300); });
  return { a: a, b: b, file: f, tripped: window.tripped, violations: V };
};
</script></body>"""

OPEN = r"""<!doctype html><title>tt</title><body><script>
""" + COMMON + r"""
var mine = trustedTypes.createPolicy('site', { createScriptURL: function (u) { return u; } });
window.__run = async function () {
  var w = await start(function () { return new Worker(mine.createScriptURL(blobUrl())); });
  return { worker: w, page: 'pic:' + draw(new OffscreenCanvas(96, 40)), violations: V };
};
</script></body>"""

FILE_WORKER = b"postMessage({pic: ''});"

PAGES = {
    "/allow.html": (ALLOWLIST.encode(), "text/html; charset=utf-8",
                    "require-trusted-types-for 'script'; trusted-types site default; worker-src 'self' blob:"),
    "/open.html": (OPEN.encode(), "text/html; charset=utf-8", "require-trusted-types-for 'script'"),
    "/w.js": (FILE_WORKER, "text/javascript", None),
}


@pytest.fixture
def site():
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            page = PAGES.get(self.path.split("?")[0])
            if page is None:
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            body, kind, csp = page
            self.send_response(200)
            self.send_header("Content-Type", kind)
            if csp:
                self.send_header("Content-Security-Policy", csp)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1]
    srv.shutdown()


STEPS = r'''
from PyQt6.QtCore import QUrl

def steps(ike, qapp, out):
    view = ike.windows[0].current_view()
    for key, url in PAGES:
        done = {}
        view.page().loadFinished.connect(lambda ok, d=done: d.setdefault("ok", ok))
        view.load(QUrl(url))
        while "ok" not in done:
            yield 20
        yield 200
        view.page().runJavaScript("window.result = null; window.__run().then(function (r) { window.result = "
                                  "JSON.stringify(r); }, function (e) { window.result = JSON.stringify('ERR ' + e); }); 1",
                                  0, lambda r: None)
        for _ in range(300):
            res = {}
            view.page().runJavaScript("window.result || ''", 0, lambda r, res=res: res.__setitem__("r", r))
            while "r" not in res:
                yield 20
            if res["r"]:
                out[key] = res["r"]
                break
            yield 50
'''


def run(run_ike, port, level):
    pages = [("allow1", "http://127.0.0.1:%d/allow.html"), ("allow2", "http://127.0.0.1:%d/allow.html"),
             ("open1", "http://127.0.0.1:%d/open.html"), ("open2", "http://localhost:%d/open.html")]
    script = "PAGES = %r\n" % [(k, u % port) for k, u in pages] + STEPS
    out = run_ike(script, settings={"shield_level": level}, timeout=200)
    return {k: json.loads(out[k]) for k, _ in pages}


def policy_names(r):
    return [v.split(":", 1)[1] for v in r["violations"] if v.startswith("trusted-types:")]


@pytest.mark.parametrize("level", LEVELS)
def test_workers_start_where_the_page_refuses_the_protections_policy(run_ike, site, level):
    got = run(run_ike, site, level)
    for key in ("allow1", "allow2"):
        r = got[key]
        # the page's blob workers run (Turnstile's did not until 1.1.31)
        assert r["a"].startswith("pic:") and r["b"].startswith("pic:"), (level, r)
        # nothing of I.K.E.'s reached the page's own default policy
        assert r["tripped"] == 0, (level, r)
        # one refusal in a document, not one for every worker
        assert len(policy_names(r)) == 1, (level, r)
        # a worker from a file: Balanced starts it as the page asked; Kontrol
        # and Maximum never run it without the protection (refused, as before)
        assert r["file"] == ("data" if level == "balanced" else "error"), (level, r)
    # the refused policy's name is not the site's seed: another one in every
    # document of the same site in the same session ('p' + seed was the same)
    n1, n2 = policy_names(got["allow1"])[0], policy_names(got["allow2"])[0]
    assert n1 != n2, (n1, n2)


@pytest.mark.parametrize("level", LEVELS)
def test_workers_keep_the_protection_where_the_policy_is_allowed(run_ike, site, level):
    got = run(run_ike, site, level)
    a, b = got["open1"], got["open2"]
    for r in (a, b):
        # no refusal, and the worker the page made trusted by its own policy
        # draws as the page does (the same noise: the protection runs in it)
        assert policy_names(r) == [], (level, r)
        assert r["worker"].startswith("pic:") and r["worker"] == r["page"], (level, r)
    # another picture on another site: the noise is the site's own
    assert a["worker"] != b["worker"], (level, a, b)
