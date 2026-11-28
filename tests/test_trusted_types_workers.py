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
- a worker from a file at Maximum still never runs without the protection
  (refused, as before); at Kontrol the site's own file runs (1.1.31, the
  owner's decision after the web compatibility campaign,
  tests/test_site_workers.py).

SIMULATION: a local server; 127.0.0.1 and localhost are two sites. The
"allowlist" page copies the policy of Cloudflare's frame and adds a default
policy that counts what reaches it and turns it into an address no worker can
start from, as Turnstile's own does (with the code of 1.1.30 the page's
workers end with "error" here, as Turnstile's did).
"""

import http.server
import json
import threading
import time

import pytest

LEVELS = ["balanced", "strict", "maximum"]

COMMON = r"""
// the refusals of policies the page can learn of: as events from now on, and
// the ones before its first script through a ReportingObserver's buffer
var V = [];
document.addEventListener('securitypolicyviolation', function (e) {
  V.push(e.violatedDirective + ':' + e.sample);
});
function earlier() {
  var out = [];
  try {
    new ReportingObserver(function () {}, { buffered: true, types: ['csp-violation'] }).takeRecords().forEach(function (r) {
      out.push(r.body.effectiveDirective + ':' + r.body.sample);
    });
  } catch (e) { out.push('no observer: ' + e); }
  return out;
}
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
  return { a: a, b: b, file: f, tripped: window.tripped, violations: V, earlier: earlier() };
};
</script></body>"""

OPEN = r"""<!doctype html><title>tt</title><body><script>
""" + COMMON + r"""
var mine = trustedTypes.createPolicy('site', { createScriptURL: function (u) { return u; } });
window.__run = async function () {
  var w = await start(function () { return new Worker(mine.createScriptURL(blobUrl())); });
  var out = { worker: w, page: 'pic:' + draw(new OffscreenCanvas(96, 40)), violations: V.slice() };
  // the page's own Trusted Types error, through a function the protection
  // replaced (innerHTML), and an event the page makes itself: both are the
  // page's, and it gets them
  try { document.createElement('div').innerHTML = '<b>x</b>'; } catch (e) {}
  document.dispatchEvent(new SecurityPolicyViolationEvent('securitypolicyviolation', {
    documentURI: location.href, violatedDirective: 'trusted-types', effectiveDirective: 'trusted-types',
    originalPolicy: 'x', disposition: 'enforce', statusCode: 200, sourceFile: 'userscript', sample: 'made-here' }));
  await new Promise(function (ok) { setTimeout(ok, 500); });
  out.own = V.slice(out.violations.length);
  return out;
};
</script></body>"""

# Ways a page's script could try to have a worker without the protection (the
# independent review of this change): Trusted Types names without requiring
# them (in a header, or in a <meta> a script adds), a <meta> that requires them
# with a pass-through default policy of the page's, and an exhausted stack
# while the protection makes its policy. The protection's policy is made as the
# document starts, so none of them refuses it.
NAMES = r"""<!doctype html><title>tt</title><body><script>
""" + COMMON + r"""
var mine = trustedTypes.createPolicy('site', { createScriptURL: function (u) { return u; } });
window.__run = async function () {
  var w = await start(function () { return new Worker(mine.createScriptURL(blobUrl())); });
  return { worker: w, page: 'pic:' + draw(new OffscreenCanvas(96, 40)), violations: V };
};
</script></body>"""

TRICKS = r"""<!doctype html><title>tt</title><body><script>
""" + COMMON + r"""
var mine = trustedTypes.createPolicy('site', { createScriptURL: function (u) { return u; } });
window.__run = async function () {
  var page = 'pic:' + draw(new OffscreenCanvas(96, 40)), out = { page: page };
  // the stack used up, then a worker at every depth on the way back
  var made = null, u = mine.createScriptURL(blobUrl());
  function deep() { try { deep(); } catch (e) {} if (!made) { try { made = new Worker(u); } catch (e) {} } }
  deep();
  out.deep = made ? await start(function () { return made; }) : 'none';
  out.after = await start(function () { return new Worker(mine.createScriptURL(blobUrl())); });
  // a <meta> that requires Trusted Types and allows only the page's names
  var m = document.createElement('meta');
  m.httpEquiv = 'Content-Security-Policy';
  m.content = "require-trusted-types-for 'script'; trusted-types site default";
  document.head.appendChild(m);
  trustedTypes.createPolicy('default', { createScriptURL: function (u) { return u; } });
  out.meta = await start(function () { return new Worker(mine.createScriptURL(blobUrl())); });
  out.metaPlain = await start(function () { return new Worker(blobUrl()); });
  out.violations = V;
  out.earlier = earlier();
  return out;
};
</script></body>"""

# Frames that take the policy of the document that made them (the second
# round of the independent review): a <meta> a script added in the page is
# their policy too, so it can refuse the protection's policy there. Their
# workers must keep the protection or not start, never start without it; and
# the page never sees the protection's refusals.
CHILD = r"""<!doctype html><title>tt</title><body><script>
""" + COMMON + r"""
window.WORKER = WORKER; window.start = start;
function meta(text) {
  var m = document.createElement('meta');
  m.httpEquiv = 'Content-Security-Policy';
  m.content = text;
  document.head.appendChild(m);
}
function inFrame(f) {
  var cw = f.contentWindow, seen = [];
  cw.document.addEventListener('securitypolicyviolation', function (e) {
    seen.push(e.effectiveDirective + ':' + e.sourceFile);
  });
  var pol = cw.trustedTypes.createPolicy('site', { createScriptURL: function (u) { return u; } });
  try { cw.trustedTypes.createPolicy('default', { createScriptURL: function (u) { return u; } }); } catch (e) {}
  return start(function () {
    return new cw.Worker(pol.createScriptURL(cw.URL.createObjectURL(new cw.Blob([WORKER], { type: 'text/javascript' }))));
  }).then(function (r) { return { worker: r, seen: seen }; });
}
window.__run = async function () {
  var out = { page: 'pic:' + draw(new OffscreenCanvas(96, 40)) };
  // a frame of the page's own site given a policy by the page (<iframe csp>),
  // not by its server
  out.cspAttr = await new Promise(function (ok) {
    var c = document.createElement('iframe');
    c.setAttribute('csp', "trusted-types site default");
    c.onload = function () { inFrame(c).then(ok, function (e) { ok({ worker: 'throw ' + e, seen: [] }); }); };
    c.src = '/plain.html';
    document.body.appendChild(c);
    setTimeout(function () { ok({ worker: 'no answer', seen: [] }); }, 8000);
  });
  // a data: worker whose address has a character beyond Latin-1
  out.dataWide = await start(function () {
    return new Worker('data:text/javascript;base64,' + btoa(WORKER) + '#\u65e5');
  });
  // a <meta> that allows only the page's names (and a default policy), then
  // an empty frame and a srcdoc frame that take it
  meta("trusted-types site default");
  var f = document.createElement('iframe');
  document.body.appendChild(f);
  out.blank = await inFrame(f);
  out.srcdoc = await new Promise(function (ok) {
    window.fromSrcdoc = ok;
    var g = document.createElement('iframe');
    g.srcdoc = '<script>var pol = trustedTypes.createPolicy("site", { createScriptURL: function (u) { return u; } });' +
      'try { trustedTypes.createPolicy("default", { createScriptURL: function (u) { return u; } }); } catch (e) {}' +
      'parent.start(function () { return new Worker(pol.createScriptURL(URL.createObjectURL(' +
      'new Blob([parent.WORKER], { type: "text/javascript" })))); }).then(parent.fromSrcdoc);<\/script>';
    document.body.appendChild(g);
    setTimeout(function () { ok('no answer'); }, 6000);
  });
  // the same with Trusted Types required and no default policy
  meta("require-trusted-types-for 'script'; trusted-types site");
  var h = document.createElement('iframe');
  document.body.appendChild(h);
  out.required = await inFrame(h);
  return out;
};
</script></body>"""

FILE_WORKER = b"postMessage({pic: ''});"

PAGES = {
    "/allow.html": (ALLOWLIST.encode(), "text/html; charset=utf-8",
                    "require-trusted-types-for 'script'; trusted-types site default; worker-src 'self' blob:; "
                    "report-uri /csp-report"),
    "/open.html": (OPEN.encode(), "text/html; charset=utf-8", "require-trusted-types-for 'script'"),
    "/names.html": (NAMES.encode(), "text/html; charset=utf-8", "trusted-types site"),
    "/tricks.html": (TRICKS.encode(), "text/html; charset=utf-8", None),
    "/child.html": (CHILD.encode(), "text/html; charset=utf-8", None),
    "/plain.html": (b"<!doctype html><title>plain</title><body>plain</body>", "text/html; charset=utf-8", None),
    "/w.js": (FILE_WORKER, "text/javascript", None),
}


REPORTS = []                # what the pages' report-uri received


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

        def do_POST(self):
            body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            if self.path == "/csp-report":
                REPORTS.append(json.loads(body or b"null"))
            self.send_response(204)
            self.end_headers()

        def log_message(self, *a):
            pass
    REPORTS.clear()
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


def run(run_ike, port, level, pages=None):
    pages = pages or [("allow1", "http://127.0.0.1:%d/allow.html"), ("allow2", "http://127.0.0.1:%d/allow.html"),
                      ("open1", "http://127.0.0.1:%d/open.html"), ("open2", "http://localhost:%d/open.html")]
    script = "PAGES = %r\n" % [(k, u % port) for k, u in pages] + STEPS
    out = run_ike(script, settings={"shield_level": level}, timeout=200)
    return {k: json.loads(out[k]) for k, _ in pages}


def policy_names(r):
    """The names of the refused Trusted Types policies a page can learn of."""
    seen = r["violations"] + r.get("earlier", [])
    assert not any(v.startswith("no observer") for v in seen), seen
    return [v.split(":", 1)[1] for v in seen if v.startswith("trusted-types:")]


@pytest.mark.parametrize("level", LEVELS)
def test_workers_start_where_the_page_refuses_the_protections_policy(run_ike, site, level):
    got = run(run_ike, site, level)
    for key in ("allow1", "allow2"):
        r = got[key]
        # the page's blob workers run (Turnstile's did not until 1.1.31)
        assert r["a"].startswith("pic:") and r["b"].startswith("pic:"), (level, r)
        # nothing of I.K.E.'s reached the page's own default policy
        assert r["tripped"] == 0, (level, r)
        # at most one refusal the page can see (made as the document starts,
        # it usually comes before the page's first script listens)
        assert len(policy_names(r)) <= 1, (level, r)
        # a worker from a file: Balanced and Kontrol (1.1.31) start it as the
        # page asked; Maximum never runs it without the protection (refused)
        assert r["file"] == ("error" if level == "maximum" else "data"), (level, r)
    # what the site's server is told (report-uri): one refusal in each of the
    # two documents, not one for every worker, and another name in each: not
    # the site's seed ('p' + seed was the same in both)
    def names():
        return [r["csp-report"]["script-sample"] for r in REPORTS
                if r["csp-report"]["violated-directive"] == "trusted-types"]
    for _ in range(50):                 # the engine sends its reports a moment later
        if len(names()) >= 2:
            break
        time.sleep(0.1)
    time.sleep(0.3)
    names = names()
    assert len(names) == 2 and names[0] != names[1], (level, names)


@pytest.mark.parametrize("level", LEVELS)
def test_workers_keep_the_protection_where_the_policy_is_allowed(run_ike, site, level):
    got = run(run_ike, site, level)
    a, b = got["open1"], got["open2"]
    for r in (a, b):
        # no refusal, and the worker the page made trusted by its own policy
        # draws as the page does (the same noise: the protection runs in it)
        assert policy_names(r) == [], (level, r)
        # the page's own violations reach it, and its own events
        assert "trusted-types:made-here" in r["own"], (level, r)
        assert [v for v in r["own"] if v.startswith("require-trusted-types-for:")], (level, r)
        assert r["worker"].startswith("pic:") and r["worker"] == r["page"], (level, r)
    # another picture on another site: the noise is the site's own
    assert a["worker"] != b["worker"], (level, a, b)


@pytest.mark.parametrize("level", LEVELS)
def test_a_pages_script_cannot_refuse_the_protection(run_ike, site, level):
    got = run(run_ike, site, level, [("names", "http://127.0.0.1:%d/names.html"),
                                     ("tricks", "http://127.0.0.1:%d/tricks.html")])
    n, t = got["names"], got["tricks"]
    # Trusted Types names in the header, not required: the protection's policy
    # is refused, the bare address is taken, and the worker keeps the protection
    assert n["worker"].startswith("pic:") and n["worker"] == n["page"], (level, n)
    # a worker after the stack was used up, and one made after a <meta> a
    # script added (with a pass-through default policy): the same noise as the
    # page, and no refusal of the protection's policy
    for key in ("after", "meta", "metaPlain"):
        assert t[key].startswith("pic:") and t[key] == t["page"], (level, key, t)
    assert t["deep"] in ("none", t["page"]), (level, t)
    assert policy_names(t) == [], (level, t)


@pytest.mark.parametrize("level", LEVELS)
def test_frames_that_take_a_scripts_policy_never_run_a_worker_without_the_protection(run_ike, site, level):
    t = run(run_ike, site, level, [("child", "http://127.0.0.1:%d/child.html")])["child"]
    # the engine's own picture: the page's with the shield off
    real = run(run_ike, site, "off", [("child", "http://127.0.0.1:%d/child.html")])["child"]["page"]
    assert t["page"] != real, (level, t, real)
    # protected (the page's noise), or not started: never the engine's own picture
    safe = (t["page"], "error", "timeout")
    # a data: worker has a seed of its own: another noise, never none
    assert t["dataWide"].startswith("pic:") and t["dataWide"] != real, (level, t, real)
    for key in ("cspAttr", "blank", "required"):
        assert t[key]["worker"] in safe or t[key]["worker"].startswith("throw"), (level, key, t)
        # the page does not see the protection's own refusals
        assert not [v for v in t[key]["seen"] if v.endswith(":userscript")], (level, key, t)
    assert t["srcdoc"] in safe or str(t["srcdoc"]).startswith("throw"), (level, t)
