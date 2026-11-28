"""The sites' own workers at Kontrol and Maximum (1.1.32, the owner's decision
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
- Maximum: the same (the owner's decision of 2026-11-28: "i siti devono
  funzionare, almeno quelli fidati"), with a quiet line in the shield and
  "Block them on this site"; refused on a page of a safety warning (a page
  of the lists opened anyway) and where the user blocked them: there the
  shield's octagon turns orange when the app waits on them and stays empty,
  "Repair this site" turns off the probable cause first (the user's block,
  for that site only: the other sites keep theirs), the octagon goes back to
  normal once the user says the page works, and "Undo the repair" brings the
  block back; never on a page of a safety warning.
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


# The independent review of 1.1.32: what the queue of a worker that waits for
# its hello must keep exact, a policy that only reports, a frame of another
# site, a module worker first. The canvas hash tells a protected worker (the
# page's noise) from one with the engine's own values.
HASH = r"""
function hash2d(make) {
  var c = make(120, 30), x = c.getContext('2d');
  x.textBaseline = 'top'; x.font = '14px Arial'; x.fillStyle = '#f60'; x.fillRect(5, 1, 60, 20);
  x.fillStyle = '#069'; x.fillText('I.K.E. fp test', 2, 10);
  var px = x.getImageData(0, 0, 120, 30).data, h = 0;
  for (var i = 0; i < px.length; i++) h = (h * 31 + px[i]) | 0;
  return h;
}
"""
QUEUE = r"""<!doctype html><title>q</title><body><script>
var R = {pageErrors: 0};
(async function () {
  // data changed after posting, a buffer transferred, an object that cannot be cloned
  R.copy = await new Promise(function (ok) {
    var w = new Worker('/qw.js'), a = [1], ab = new ArrayBuffer(8);
    w.onmessage = function (e) { ok({got: e.data, detachedAtOnce: R.detached}); };
    w.onerror = function () { R.pageErrors++; ok('error'); };
    w.postMessage({a: a, n: ab.byteLength}, [ab]);
    R.detached = ab.byteLength;
    a[0] = 2;
    try { w.postMessage(function () {}); R.cloneError = 'none'; } catch (e) { R.cloneError = e.name; }
    setTimeout(function () { ok('timeout'); }, 6000);
  });
  // terminated before the switch: the page hears nothing
  await new Promise(function (ok) {
    var w = new Worker('/qw.js');
    w.onerror = function () { R.pageErrors++; };
    w.terminate();
    setTimeout(ok, 1500);
  });
  window.result = JSON.stringify(R);
})();
</script></body>"""
RO = r"""<!doctype html><title>ro</title><body><script>""" + HASH + r"""
var R = {page: hash2d(function (w, h) { var c = document.createElement('canvas'); c.width = w; c.height = h; return c; })};
function one() {
  return new Promise(function (ok) {
    var w = new Worker('/hw.js'); w.onmessage = function (e) { ok(e.data); }; w.onerror = function () { ok('error'); };
    setTimeout(function () { ok('timeout'); }, 6000);
  });
}
(async function () { R.first = await one(); R.second = await one(); R.third = await one(); window.result = JSON.stringify(R); })();
</script></body>"""
MOD = r"""<!doctype html><title>m</title><body><script>
var R = {};
(async function () {
  R.module = await new Promise(function (ok) {
    var w = new Worker('/mw.js', {type: 'module'}); w.onmessage = function (e) { ok(e.data); }; w.onerror = function () { ok('error'); };
    w.postMessage('hi');
    setTimeout(function () { ok('timeout'); }, 6000);
  });
  window.result = JSON.stringify(R);
})();
</script></body>"""
TOP = r"""<!doctype html><title>top</title><body><script>
var R = {};
window.addEventListener('message', function (e) { R.frame = e.data; window.result = JSON.stringify(R); });
var f = document.createElement('iframe'); f.src = 'http://localhost:' + location.port + '/inner.html'; document.body.appendChild(f);
</script></body>"""
INNER = r"""<!doctype html><title>inner</title><script>
var done = function (v) { parent.postMessage(v, '*'); };
try { var s = new SharedWorker('/shw.js'); s.port.onmessage = function (e) { done(e.data); };
      s.onerror = function () { done('error'); }; s.port.start(); s.port.postMessage('hi'); }
catch (e) { done('throw ' + e.name); }
setTimeout(function () { done('timeout'); }, 6000);
</script>"""
FILES.update({
    "/qw.js": "onmessage = function (e) { postMessage(e.data); };",
    "/hw.js": HASH + "postMessage(hash2d(function (w, h) { return new OffscreenCanvas(w, h); }));",
    "/mw.js": "self.onmessage = function (e) { self.postMessage('module ' + e.data); };",
    "/queue": QUEUE, "/ro": RO, "/mod": MOD, "/top": TOP, "/inner.html": INNER,
})
# the policy each page sends (WhatsApp's and Telegram's kind: workers only from the site's own files)
POLICY = {"/ro": ("Content-Security-Policy-Report-Only", "worker-src 'self'"), "/top": None, "/inner.html": None}


@pytest.fixture
def site():
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            path = self.path.split("?")[0]
            body = (FILES.get(path) or PAGE).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/javascript" if path.endswith(".js") else "text/html")
            policy = POLICY.get(path, ("Content-Security-Policy", "worker-src 'self'"))
            if policy:
                self.send_header(*policy)
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

# the diagnosis looks at the page a few seconds after its load (incompat.py)
SETTLE = r'''
def settle(win, out, key, wait=7000):
    for _ in range(wait // 100):
        if win.interference_state()[0]:
            break
        yield 100
    out[key + "_state"] = win.interference_state()[0]
'''

STEPS = LOAD + SETTLE + r'''
def steps(ike, qapp, out):
    win = ike.windows[0]
    view = win.current_view()
    for i, host in enumerate(%s):
        yield from load(view, "http://%%s:%d/page%%d" %% (host, i), host, out)
        yield from settle(win, out, host)
        out[host + "_stats"] = ike.shields.site_stats(host)
'''


# a page of the protection lists the user opened anyway (securebar.py "Continue anyway")
DANGER = '''
    ike.shields.pages_allowed.add("127.0.0.1")
    ike.shields.apply_settings()
'''


def run(run_ike, port, level, hosts=("127.0.0.1",), opts=None, before=""):
    settings = {"shield_level": level, "https_only": False}
    if opts:
        settings["site_opts"] = opts
    script = STEPS % (json.dumps(list(hosts)), port)
    if before:
        script = script.replace("def steps(ike, qapp, out):\n", "def steps(ike, qapp, out):\n" + before.lstrip("\n"), 1)
    return run_ike(script, settings=settings, timeout=150)


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
    assert out["127.0.0.1_state"] is None                 # nothing broken: the octagon as it is


def test_maximum_runs_them_too(run_ike, site):
    out = run(run_ike, site, "maximum")
    r = out["127.0.0.1"]
    assert r["first"] == ["echo one", "echo two"] and r["shared"] == "shared hi" and r["sw"] == "sw hi", r
    stats = out["127.0.0.1_stats"]
    assert stats["workers"] == 0 and stats["workers_open"] >= 3, stats
    assert out["127.0.0.1_state"] is None


@pytest.mark.parametrize("why", ["blocked", "danger"])
def test_maximum_refuses_them_where_blocked_or_dangerous(run_ike, site, why):
    if why == "blocked":
        out = run(run_ike, site, "maximum", opts={"127.0.0.1": {"workers": True}})
    else:
        out = run(run_ike, site, "maximum", before=DANGER)
    r = out["127.0.0.1"]
    assert r["first"] == "error" and r["second"] == "error", r
    assert r["shared"] == "error", r
    assert r["sw"].startswith("refused"), r
    stats = out["127.0.0.1_stats"]
    # the shared worker (the service worker is answered before its file is
    # asked for, as the engine would answer; the dedicated ones: the policy)
    assert stats["workers"] >= 1, stats
    # the octagon: orange where the user's block breaks the app (with the
    # repair of that block); on a page of the lists opened anyway nothing to
    # repair (the warning was the user's to go through)
    assert out["127.0.0.1_state"] == ("serious" if why == "blocked" else None), out


def test_a_block_is_for_one_site_only(run_ike, site):
    out = run(run_ike, site, "maximum", hosts=("127.0.0.1", "localhost"),
              opts={"localhost": {"workers": True}})
    allowed, other = out["127.0.0.1"], out["localhost"]
    assert allowed["first"] == ["echo one", "echo two"] and allowed["shared"] == "shared hi", allowed
    assert allowed["sw"] == "sw hi", allowed
    assert other["first"] == "error" and other["sw"].startswith("refused"), other
    assert out["127.0.0.1_state"] is None and out["localhost_state"] == "serious", out


ALLOW = LOAD + SETTLE + r'''
def steps(ike, qapp, out):
    from ike import repair
    win = ike.windows[0]
    view = win.current_view()
    yield from load(view, "http://127.0.0.1:%d/page", "before", out)
    yield from settle(win, out, "before")
    f = ike.diagnosis.finding(view)
    out["keys"] = list(f.keys) if f else None
    win.shield_menu.aboutToShow.emit()                     # the panel, as it opens
    p = win.shield_panel
    out["panel"] = {"note": p.diag_note.text(), "ok": p.diag_ok.isVisibleTo(p),
                    "repair_default": p.repair_btn.isDefault()}
    out["anim"] = win.shield_btn.interference.state
    win.repair_site()                                      # "Repair this site": the probable cause first
    rep = win.repair_bar.repair
    out["phase"] = rep.phase
    out["during"] = win.interference_state()[0]            # stays on while the repair asks
    out["kept_during"] = repair.repaired(ike.config, "127.0.0.1")   # a trial, not kept yet
    yield 1500
    win.repair_bar.yes.click()                             # the page works
    yield 300
    out["after_state"] = win.interference_state()[0]
    out["ended"] = ike.diagnosis.ended(view)
    out["opts"] = dict(ike.config["site_opts"].get("127.0.0.1") or {})     # a copy: undone below
    out["repaired"] = repair.repaired(ike.config, "127.0.0.1")
    yield from load(view, "http://127.0.0.1:%d/again", "after", out)
    repair.undo(ike.config, "127.0.0.1")
    out["undone"] = ike.config["site_opts"].get("127.0.0.1")
'''


def test_repair_puts_the_cause_first_and_undo(run_ike, site):
    out = run_ike(ALLOW % (site, site), settings={"shield_level": "maximum", "https_only": False,
                                                 "site_opts": {"127.0.0.1": {"workers": True}}}, timeout=150)
    assert out["before_state"] == "serious" and out["keys"] == ["workers"], out
    assert out["anim"] == "serious", out
    assert "background programs" in out["panel"]["note"], out               # the probable cause, in words
    assert out["panel"]["ok"] is True and out["panel"]["repair_default"] is True, out
    assert out["phase"] == "suggested" and out["during"] == "serious", out
    assert out["kept_during"] == [], out                   # nothing kept before the user's answer
    assert out["after_state"] is None and out["ended"] == "resolved", out
    assert out["opts"].get("workers") is False and out["repaired"] == ["workers"], out
    assert out["after"]["first"] == ["echo one", "echo two"], out["after"]
    assert out["undone"] == {"workers": True}, out        # the user's block is back


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
    out = run_ike(REPAIR, settings={"shield_level": level,
                                    "site_opts": {"web.example.com": {"workers": True}}}, timeout=60)
    assert "workers" in out["candidates"] and out["candidates"].index("workers") == \
        out["candidates"].index("fp") + 1, out
    assert out["state"] == "found" and out["culprits"] == ["workers"], out


def test_only_a_users_block_is_offered_to_the_repair(run_ike):
    out = run_ike(r'''
def steps(ike, qapp, out):
    from ike import repair
    for blocked in (False, True):
        if blocked:
            ike.config.set_site_opt("web.example.com", "workers", True)
        for lv in ("balanced", "strict", "maximum"):
            ike.config["shield_level"] = lv
            out[lv + str(blocked)] = "workers" in repair.active(ike.config, "web.example.com")
    yield 10
''', timeout=60)
    # only the user's own block is a protection the repair can turn off
    assert [out[k] for k in ("balancedFalse", "strictFalse", "maximumFalse")] == [False, False, False], out
    assert [out[k] for k in ("balancedTrue", "strictTrue", "maximumTrue")] == [False, True, True], out


PAGES = LOAD + r"""
def steps(ike, qapp, out):
    view = ike.windows[0].current_view()
    for key, url in %s:
        yield from load(view, url, key, out)
        yield 300
        out[key + "_stats"] = ike.shields.site_stats("127.0.0.1")
"""


def pages(run_ike, port, level, keys):
    urls = [(k, "http://127.0.0.1:%d/%s" % (port, k)) for k in keys]
    return run_ike(PAGES % json.dumps(urls), settings={"shield_level": level, "https_only": False}, timeout=150)


def test_the_queue_keeps_the_engines_semantics(run_ike, site):
    """Kontrol: a message posted before the switch is cloned at once (a change
    made after posting does not reach the worker, a transferred buffer is
    detached at once, an object that cannot be cloned throws at once), and a
    worker terminated before the switch reports nothing (the review)."""
    r = pages(run_ike, site, "strict", ["queue"])["queue"]
    assert r["copy"]["got"]["a"] == [1] and r["copy"]["got"]["n"] == 8, r
    assert r["copy"]["detachedAtOnce"] == 0, r
    assert r["cloneError"] == "DataCloneError", r
    assert r["pageErrors"] == 0, r


def test_a_report_only_policy_keeps_the_protection(run_ike, site):
    """A policy that only reports refuses nothing: every file worker keeps the
    protection (the page's canvas noise), the first one and the next ones."""
    r = pages(run_ike, site, "strict", ["ro"])["ro"]
    assert r["first"] == r["second"] == r["third"] == r["page"], r


def test_a_module_worker_first(run_ike, site):
    r = pages(run_ike, site, "strict", ["mod"])["mod"]
    assert r["module"] == "module hi", r


@pytest.mark.parametrize("level", ["strict", "maximum"])
def test_a_frame_of_another_site_gets_no_free_worker(run_ike, site, level):
    """Kontrol lets only the visited site's own workers run: a frame of another
    site (localhost inside 127.0.0.1) does not get its shared worker, which
    is neither counted for the site nor offered to it."""
    out = pages(run_ike, site, level, ["top"])
    assert out["top"]["frame"] in ("error", "timeout"), out["top"]
    st = out["top_stats"]
    assert st["workers_open"] == 0 and st["workers"] == 0, st


TRANSITION = LOAD + r'''
def steps(ike, qapp, out):
    from PyQt6.QtCore import QUrl
    win = ike.windows[0]
    a = win.current_view()
    yield from load(a, "http://127.0.0.1:%d/page", "kontrol", out)     # its shared worker keeps running
    # the user blocks the site's workers (the shield's own way), the first tab stays open
    ike.config.set_site_opt("127.0.0.1", "workers", True)
    ike.shields.apply_settings()
    b = win.add_tab(QUrl("about:blank"))
    yield 500
    yield from load(b, "http://127.0.0.1:%d/page", "maximum", out)
    out["stats"] = ike.shields.site_stats("127.0.0.1")
    # register() answers in the engine's own words (as when the file is refused)
    res = {}
    b.page().runJavaScript(
        "navigator.serviceWorker.register('/sw.js', {scope: '/x/'}).then(function () { window.r2 = 'ok'; },"
        " function (e) { window.r2 = JSON.stringify([e.name, e.message, e instanceof TypeError]); });", 0)
    for _ in range(50):
        b.page().runJavaScript("window.r2 || ''", 0, lambda r, res=res: res.__setitem__("r", r))
        yield 100
        if res.get("r"):
            break
    out["message"] = json.loads(res["r"]) if res.get("r", "").startswith("[") else res.get("r")
'''


def test_a_block_meanwhile_gives_no_running_worker(run_ike, site):
    """3.2 of the owner's brief: a shared worker started before keeps running
    while a tab of its site is open; a page of that site where they now stay
    out (the user's block, a safety warning) must not join it (the engine
    would connect without asking for its file, so the request check would
    never see it), nor take back its service worker."""
    out = run_ike(TRANSITION % (site, site), settings={"shield_level": "strict", "https_only": False}, timeout=150)
    assert out["kontrol"]["shared"] == "shared hi", out["kontrol"]
    assert out["maximum"]["shared"] == "error", out["maximum"]
    assert out["maximum"]["first"] == "error" and out["maximum"]["sw"].startswith("refused"), out["maximum"]
    origin = "http://127.0.0.1:%d" % site
    assert out["message"] == ["TypeError", "Failed to register a ServiceWorker for scope ('%s/x/') with script "
                              "('%s/sw.js'): An unknown error occurred when fetching the script." % (origin, origin),
                              True], out["message"]


QUIET = LOAD + r'''
def steps(ike, qapp, out):
    win = ike.windows[0]
    view = win.current_view()
    p = win.shield_panel
    yield from load(view, "http://127.0.0.1:%d/page", "ran", out)
    win.shield_menu.aboutToShow.emit()
    out["line"] = [p.workers_line.isVisibleTo(p), p.workers_line.text(), p.workers_btn.text()]
    out["octagon"] = [win.shield_btn.interference.state, win.interference_state()[0]]
    p.workers_btn.click()                                  # "Block them on this site"
    out["blocked_opt"] = ike.config.site_opt("127.0.0.1", "workers")
    yield from load(view, "http://127.0.0.1:%d/page?b", "blocked", out)
    win.shield_menu.aboutToShow.emit()
    out["line_blocked"] = [p.workers_line.isVisibleTo(p), p.workers_line.text(), p.workers_btn.text()]
    p.workers_btn.click()                                  # "Allow them again"
    out["allowed_opt"] = ike.config.site_opt("127.0.0.1", "workers")
    yield from load(view, "http://127.0.0.1:%d/page?a", "again", out)
    # a page of a safety warning: no line, nothing to choose (they stay out)
    ike.shields.pages_allowed.add("127.0.0.1")
    ike.shields.apply_settings()
    yield from load(view, "http://127.0.0.1:%d/page?d", "danger", out)
    win.shield_menu.aboutToShow.emit()
    out["line_danger"] = p.workers_line.isVisibleTo(p)
'''


def test_the_quiet_line_in_the_shield(run_ike, site):
    out = run_ike(QUIET % ((site,) * 4), settings={"shield_level": "maximum", "https_only": False}, timeout=200)
    assert out["ran"]["shared"] == "shared hi", out["ran"]
    assert out["line"][0] is True and "background programs" in out["line"][1], out
    assert out["line"][2] == "Block them on this site", out
    assert out["octagon"] == [None, None], out           # the octagon does not light up for it
    assert out["blocked_opt"] is True, out
    assert out["blocked"]["shared"] == "error" and out["blocked"]["sw"].startswith("refused"), out["blocked"]
    assert out["line_blocked"][0] is True and "blocked" in out["line_blocked"][1], out
    assert out["line_blocked"][2] == "Allow them again", out
    assert out["allowed_opt"] is None and out["again"]["shared"] == "shared hi", out
    assert out["danger"]["shared"] == "error" and out["line_danger"] is False, out
