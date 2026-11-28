"""The sites' own workers at Kontrol and Maximum (1.1.31, the owner's decision
after the web compatibility campaign of 2026-11-28,
docs/review/web-compat-2026-11.md).

WhatsApp and Telegram did not work at Kontrol and Maximum: their service
workers, shared workers and dedicated workers from their own files were
refused, and their policy (worker-src without blob:) refused the protected
copy of a dedicated worker too, a moment after the Worker object was made,
so the fallback never ran.

- Kontrol: the site's own workers run (service worker, shared worker, a
  dedicated worker whose protected copy the policy refuses: the site's file
  inside the same object, the messages posted before the switch delivered,
  no error and no report of the refused copy for the page); a worker made
  from the page's own text keeps the protection; they are counted.
- Maximum: refused as before, counted; the bar above the page says so and
  "Allow them on this site" lets that site's own workers run, the other
  sites' stay refused; "Undo the repair" takes it back.
- "Repair this site" finds the workers, not the whole fingerprinting
  protection, when only the workers break the page.

SIMULATION: a local server with a WhatsApp-like page (a policy without
blob: workers), a service worker and a shared worker; 127.0.0.1 and
localhost are two sites.
"""

import http.server
import json
import threading

import pytest

PAGE = r"""<!doctype html><title>w</title><body><script>
var R = {violations: [], pageErrors: 0};
document.addEventListener('securitypolicyviolation', function (e) { R.violations.push(e.blockedURI); });
function dedicated() {
  return new Promise(function (ok) {
    var got = [], w;
    try { w = new Worker('/dw.js'); } catch (e) { ok('throw ' + e.name); return; }
    w.onmessage = function (e) { got.push(e.data); if (got.length === 2) ok(got); };
    w.onerror = function () { R.pageErrors++; ok('error'); };
    w.postMessage('one');                   // posted at once, before the worker said anything
    setTimeout(function () { w.postMessage('two'); }, 50);
    setTimeout(function () { ok(got.length ? got : 'timeout'); }, 6000);
  });
}
(async function () {
  R.first = await dedicated();
  R.second = await dedicated();             // the document already knows its policy
  R.blob = await new Promise(function (ok) {
    var u = URL.createObjectURL(new Blob(['postMessage(navigator.hardwareConcurrency)'], {type: 'text/javascript'}));
    try { var w = new Worker(u); w.onmessage = function (e) { ok('cores ' + e.data); }; w.onerror = function () { ok('error'); }; }
    catch (e) { ok('throw ' + e.name); }
    setTimeout(function () { ok('timeout'); }, 4000);
  });
  R.shared = await new Promise(function (ok) {
    try { var s = new SharedWorker('/shw.js'); s.port.onmessage = function (e) { ok(e.data); };
          s.onerror = function () { ok('error'); }; s.port.start(); s.port.postMessage('hi'); }
    catch (e) { ok('throw ' + e.name); }
    setTimeout(function () { ok('timeout'); }, 6000);
  });
  try {
    var reg = await navigator.serviceWorker.register('/sw.js');
    await navigator.serviceWorker.ready;
    R.sw = await new Promise(function (ok) {
      navigator.serviceWorker.onmessage = function (e) { ok(e.data); };
      (reg.active || reg.waiting || reg.installing).postMessage('hi');
      setTimeout(function () { ok('timeout'); }, 6000);
    });
  } catch (e) { R.sw = 'refused ' + e.name; }
  window.result = JSON.stringify(R);
})();
</script></body>"""

FILES = {
    "/dw.js": "onmessage = function (e) { postMessage('echo ' + e.data); };",
    "/shw.js": "onconnect = function (e) { var p = e.ports[0]; p.onmessage = function (m) { p.postMessage('shared ' + m.data); }; };",
    "/sw.js": "self.addEventListener('install', function () { self.skipWaiting(); });"
              "self.addEventListener('activate', function (e) { e.waitUntil(clients.claim()); });"
              "self.addEventListener('message', function (e) { e.source.postMessage('sw ' + e.data); });",
}


@pytest.fixture
def site():
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            path = self.path.split("?")[0]
            body = (FILES.get(path) or PAGE).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/javascript" if path.endswith(".js") else "text/html")
            # WhatsApp's and Telegram's kind of policy: workers only from the site's own files
            self.send_header("Content-Security-Policy", "worker-src 'self'")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1]
    srv.shutdown()


LOAD = r'''
import json
from PyQt6.QtCore import QUrl

def load(view, url, key, out, tries=300):
    done = {}
    view.page().loadFinished.connect(lambda ok, d=done: d.setdefault("ok", ok))
    view.load(QUrl(url))
    while "ok" not in done:
        yield 20
    for _ in range(tries):
        res = {}
        view.page().runJavaScript("window.result || ''", 0, lambda r, res=res: res.__setitem__("r", r))
        while "r" not in res:
            yield 20
        if res["r"]:
            out[key] = json.loads(res["r"])
            return
        yield 100
'''

STEPS = LOAD + r'''
def steps(ike, qapp, out):
    win = ike.windows[0]
    view = win.current_view()
    for i, host in enumerate(%s):
        yield from load(view, "http://%%s:%d/page%%d" %% (host, i), host, out)
        yield 300
        out[host + "_stats"] = ike.shields.site_stats(host)
        out[host + "_bar"] = win.workers_bar.isVisible()
'''


def run(run_ike, port, level, hosts=("127.0.0.1",), opts=None):
    settings = {"shield_level": level, "https_only": False}
    if opts:
        settings["site_opts"] = opts
    return run_ike(STEPS % (json.dumps(list(hosts)), port), settings=settings, timeout=150)


def test_kontrol_runs_the_sites_own_workers(run_ike, site):
    out = run(run_ike, site, "strict")
    r = out["127.0.0.1"]
    # the protected copy refused by the policy: the site's own file, in the same object,
    # with the message posted at once delivered, no error and no report for the page
    assert r["first"] == ["echo one", "echo two"], r
    assert r["second"] == ["echo one", "echo two"], r
    assert r["pageErrors"] == 0 and r["violations"] == [], r
    assert r["shared"] == "shared hi", r
    assert r["sw"] == "sw hi", r
    # a worker made from the page's own text: refused by this policy as by any browser
    assert r["blob"] in ("error", "timeout"), r
    stats = out["127.0.0.1_stats"]
    assert stats["workers"] == 0 and stats["workers_open"] >= 3, stats      # counted, not refused
    assert out["127.0.0.1_bar"] is False


def test_maximum_refuses_them_and_says_so(run_ike, site):
    out = run(run_ike, site, "maximum")
    r = out["127.0.0.1"]
    assert r["first"] == "error" and r["second"] == "error", r
    assert r["shared"] == "error", r
    assert r["sw"].startswith("refused"), r
    stats = out["127.0.0.1_stats"]
    assert stats["workers"] >= 2, stats          # the shared and the service worker (the dedicated ones: the policy)
    assert out["127.0.0.1_bar"] is True                  # the bar above the page says why


def test_maximum_allows_them_for_one_site_only(run_ike, site):
    out = run(run_ike, site, "maximum", hosts=("127.0.0.1", "localhost"),
              opts={"127.0.0.1": {"workers": False, "repaired": ["workers"]}})
    allowed, other = out["127.0.0.1"], out["localhost"]
    assert allowed["first"] == ["echo one", "echo two"] and allowed["shared"] == "shared hi", allowed
    assert allowed["sw"] == "sw hi", allowed
    assert other["first"] == "error" and other["sw"].startswith("refused"), other
    assert out["127.0.0.1_bar"] is False and out["localhost_bar"] is True


ALLOW = LOAD + r'''
def steps(ike, qapp, out):
    from ike import repair
    win = ike.windows[0]
    view = win.current_view()
    yield from load(view, "http://127.0.0.1:%d/page", "before", out)
    yield 300
    out["bar"] = win.workers_bar.isVisible()
    win.workers_bar.ok.click()                            # "Allow them on this site"
    yield 300
    out["opts"] = dict(ike.config["site_opts"].get("127.0.0.1") or {})     # a copy: undone below
    out["repaired"] = repair.repaired(ike.config, "127.0.0.1")
    yield from load(view, "http://127.0.0.1:%d/again", "after", out)
    repair.undo(ike.config, "127.0.0.1")
    out["undone"] = ike.config["site_opts"].get("127.0.0.1")
'''


def test_allow_button_and_undo(run_ike, site):
    out = run_ike(ALLOW % (site, site), settings={"shield_level": "maximum", "https_only": False}, timeout=150)
    assert out["bar"] is True
    assert out["opts"].get("workers") is False and out["repaired"] == ["workers"], out
    assert out["after"]["first"] == ["echo one", "echo two"], out["after"]
    assert out["undone"] is None, out


REPAIR = r'''
def steps(ike, qapp, out):
    from ike import repair
    cfg = ike.config
    host = "web.example.com"
    rep = repair.Repair(ike, None, host)
    rep._reload = lambda: None               # no page: the answers below stand for it
    out["candidates"] = list(rep.candidates)
    rep.start()
    for _ in range(20):
        if rep.state != "ask":
            break
        # the page works unless its workers are refused: the rule acts only while
        # both the workers and the fingerprinting protection are on
        on = lambda k: k in repair.active(cfg, host)
        rep.answer(not (on("workers") and on("fp")))
    out["state"] = rep.state
    out["culprits"] = rep.culprits
    yield 10
'''


@pytest.mark.parametrize("level", ["maximum"])
def test_repair_finds_the_workers_not_the_fingerprinting(run_ike, level):
    out = run_ike(REPAIR, settings={"shield_level": level}, timeout=60)
    assert "workers" in out["candidates"] and out["candidates"].index("workers") == \
        out["candidates"].index("fp") + 1, out
    assert out["state"] == "found" and out["culprits"] == ["workers"], out


def test_kontrol_and_lower_levels_offer_no_worker_repair(run_ike):
    out = run_ike(r'''
def steps(ike, qapp, out):
    from ike import repair
    for lv in ("balanced", "strict", "maximum"):
        ike.config["shield_level"] = lv
        out[lv] = "workers" in repair.active(ike.config, "web.example.com")
    yield 10
''', timeout=60)
    assert (out["balanced"], out["strict"], out["maximum"]) == (False, False, True), out
