"""The values a site can read, in every place it can read them (the 1.1.32 audit).

Not part of the automatic tests: an audit tool, to compare the levels after a
change of the fingerprinting protection. One page measures the same values in
the page, a frame of the same site, a srcdoc frame, an empty frame the page
fills, a blob, a data: and a file worker, a worker started by a worker, a
shared worker (blob and file) and a service worker, and prints them side by
side for every level, with what differs from the page.

    python3 -m pytest -s -q tests/fp_audit.py              # all levels
    FP_AUDIT_LEVELS=off,balanced python3 -m pytest -s -q tests/fp_audit.py
    FP_AUDIT_OUT=/tmp/audit.json ...                        # all values as JSON
"""

import http.server
import json
import os
import threading

import pytest

GL_FLAGS = "--no-sandbox --enable-unsafe-swiftshader --use-angle=swiftshader --ignore-gpu-blocklist"

PROBE = r"""
function hash(d) { var h = 2166136261; for (var i = 0; i < d.length; i++) { h ^= d[i]; h = Math.imul(h, 16777619); } return (h >>> 0).toString(16); }
async function probe() {
  var r = {};
  var N = self.navigator;
  r.cores = N.hardwareConcurrency; r.mem = N.deviceMemory;
  r.langs = (N.languages || []).join(','); r.lang = N.language;
  var ro = Intl.DateTimeFormat().resolvedOptions();
  r.tz = ro.timeZone; r.locale = ro.locale; r.tzo = new Date(2026, 0, 1).getTimezoneOffset();
  r.ua = N.userAgent; r.platform = N.platform;
  if (N.userAgentData) {
    r.brands = JSON.stringify(N.userAgentData.brands);
    try {
      var he = await N.userAgentData.getHighEntropyValues(['platformVersion', 'uaFullVersion', 'fullVersionList', 'architecture', 'bitness', 'model']);
      r.he = JSON.stringify([he.platformVersion, he.uaFullVersion, he.architecture, he.bitness, he.model, JSON.stringify(he.fullVersionList)]);
    } catch (e) { r.he = 'err ' + e; }
  } else r.brands = 'none';
  try {
    var oc = new OffscreenCanvas(96, 40), x = oc.getContext('2d'), gr = x.createLinearGradient(0, 0, 96, 40);
    gr.addColorStop(0, '#f60'); gr.addColorStop(1, '#069'); x.fillStyle = gr; x.fillRect(0, 0, 96, 40);
    x.fillStyle = 'rgba(102,204,0,0.7)'; x.font = '14px sans-serif'; x.fillText('Cwm fjord', 4, 24);
    r.canvas = hash(x.getImageData(0, 0, 96, 40).data);
    r.measure = x.measureText('Cwm fjordbank glyphs').width;
  } catch (e) { r.canvas = 'err ' + e; }
  try {
    var g = new OffscreenCanvas(64, 64).getContext('webgl');
    if (g) {
      var ext = g.getExtension('WEBGL_debug_renderer_info');
      r.glVendor = ext ? g.getParameter(ext.UNMASKED_VENDOR_WEBGL) : 'no extension';
      r.glRenderer = ext ? g.getParameter(ext.UNMASKED_RENDERER_WEBGL) : 'no extension';
      r.glExts = (g.getSupportedExtensions() || []).length;
      r.glMax = [g.getParameter(g.MAX_TEXTURE_SIZE), g.getParameter(g.MAX_VERTEX_UNIFORM_VECTORS)].join(',');
      g.clearColor(0.2, 0.4, 0.6, 1); g.clear(g.COLOR_BUFFER_BIT);
      var px = new Uint8Array(64 * 64 * 4); g.readPixels(0, 0, 64, 64, g.RGBA, g.UNSIGNED_BYTE, px);
      r.glPixels = hash(px);
    } else r.glVendor = 'no webgl';
  } catch (e) { r.glVendor = 'err ' + e; }
  if (N.gpu) {
    try {
      var a = await Promise.race([N.gpu.requestAdapter(), new Promise(function (ok) { setTimeout(function () { ok('timeout'); }, 2000); })]);
      r.webgpu = a === 'timeout' ? a : a ? JSON.stringify([a.info && a.info.vendor, a.info && a.info.architecture]) : 'null';
    } catch (e) { r.webgpu = 'err'; }
  } else r.webgpu = 'none';
  try {
    r.fontLocal = await new FontFace('probe', 'local("DejaVu Sans")').load().then(function () { return 'found'; }, function () { return 'not found'; });
  } catch (e) { r.fontLocal = 'err'; }
  return r;
}
"""

WORKER = PROBE + "probe().then(function (r) { postMessage(r); });"
SHARED = PROBE + "onconnect = function (e) { var p = e.ports[0]; probe().then(function (r) { p.postMessage(r); }); };"
SERVICE = PROBE + """
self.addEventListener('install', function (e) { self.skipWaiting(); });
self.addEventListener('activate', function (e) { e.waitUntil(clients.claim()); });
self.addEventListener('message', function (e) { probe().then(function (r) { e.source.postMessage(r); }); });
"""

PAGE = r"""<!doctype html><title>audit</title><body><script>
""" + PROBE + r"""
var WORKER = """ + json.dumps(WORKER) + r""", SHARED = """ + json.dumps(SHARED) + r""";
function wait(p, ms) { return Promise.race([p, new Promise(function (ok) { setTimeout(function () { ok('timeout'); }, ms || 6000); })]); }
function fromWorker(make) {
  return wait(new Promise(function (ok) {
    var w; try { w = make(); } catch (e) { return ok('throw ' + e.name); }
    w.onmessage = function (e) { ok(e.data); }; w.onerror = function () { ok('error'); };
  }));
}
function fromShared(make) {
  return wait(new Promise(function (ok) {
    var s; try { s = make(); } catch (e) { return ok('throw ' + e.name); }
    s.port.onmessage = function (e) { ok(e.data); }; s.onerror = function () { ok('error'); }; s.port.start();
  }));
}
function blob(text) { return URL.createObjectURL(new Blob([text], { type: 'text/javascript' })); }
window.__run = async function () {
  var out = {};
  out.page = await probe();
  out.frame = await wait(new Promise(function (ok) {
    window.addEventListener('message', function h(e) { if (e.data && e.data.from === 'frame') { removeEventListener('message', h); ok(e.data.r); } });
    var f = document.createElement('iframe'); f.src = '/frame.html'; document.body.appendChild(f);
  }));
  out.srcdoc = await wait(new Promise(function (ok) {
    window.fromSrcdoc = ok;
    var f = document.createElement('iframe');
    f.srcdoc = '<script>' + PROBE_TEXT + 'probe().then(function (r) { parent.fromSrcdoc(r); });<\/script>';
    document.body.appendChild(f);
  }));
  var e = document.createElement('iframe'); document.body.appendChild(e);
  out.emptyFrame = await wait(new e.contentWindow.Function(PROBE_TEXT + 'return probe();')());
  out.blobWorker = await fromWorker(function () { return new Worker(blob(WORKER)); });
  out.dataWorker = await fromWorker(function () { return new Worker('data:text/javascript,' + encodeURIComponent(WORKER)); });
  out.fileWorker = await fromWorker(function () { return new Worker('/w.js'); });
  out.nestedWorker = await fromWorker(function () {
    return new Worker(blob('var n = new Worker(URL.createObjectURL(new Blob([' + JSON.stringify(WORKER) +
      ']))); n.onmessage = function (e) { postMessage(e.data); }; n.onerror = function () { postMessage("error"); };'));
  });
  out.sharedBlob = self.SharedWorker ? await fromShared(function () { return new SharedWorker(blob(SHARED)); }) : 'none';
  out.sharedFile = self.SharedWorker ? await fromShared(function () { return new SharedWorker('/sh.js'); }) : 'none';
  out.serviceWorker = await wait(new Promise(function (ok) {
    if (!navigator.serviceWorker) return ok('none');
    navigator.serviceWorker.register('/sw.js').then(function () { return navigator.serviceWorker.ready; }).then(function (reg) {
      navigator.serviceWorker.addEventListener('message', function (e) { ok(e.data); });
      reg.active.postMessage('probe');
    }, function (err) { ok('refused ' + err.name); });
  }), 8000);
  // audio, in the page only
  try {
    var C = new OfflineAudioContext(1, 5000, 44100), o = C.createOscillator(); o.type = 'triangle'; o.frequency.value = 10000;
    o.connect(C.destination); o.start(0);
    var buf = await C.startRendering(), d = buf.getChannelData(0), s = 0;
    for (var i = 4000; i < 5000; i++) s += Math.abs(d[i]);
    out.page.audio = String(s);
  } catch (x) { out.page.audio = 'err'; }
  return out;
};
var PROBE_TEXT = """ + json.dumps(PROBE) + r""";
</script></body>"""

FRAME = "<!doctype html><script>" + PROBE + \
    "probe().then(function (r) { parent.postMessage({from: 'frame', r: r}, '*'); });</script>"

FILES = {"/p.html": (PAGE, "text/html"), "/frame.html": (FRAME, "text/html"), "/w.js": (WORKER, "text/javascript"),
         "/sh.js": (SHARED, "text/javascript"), "/sw.js": (SERVICE, "text/javascript")}


@pytest.fixture
def site():
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            f = FILES.get(self.path.split("?")[0])
            if not f:
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            body = f[0].encode()
            self.send_response(200)
            self.send_header("Content-Type", f[1] + "; charset=utf-8")
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


def measure(run_ike, port, level):
    from test_trusted_types_workers import STEPS
    out = run_ike("PAGES = %r\n" % [("audit", "http://localhost:%d/p.html" % port)] + STEPS,
                  settings={"shield_level": level}, env={"QTWEBENGINE_CHROMIUM_FLAGS": GL_FLAGS}, timeout=300,
                  internal_errors=True)
    return json.loads(out["audit"])


LEVELS = os.environ.get("FP_AUDIT_LEVELS", "off,compatibility,balanced,strict,maximum").split(",")


@pytest.mark.parametrize("level", LEVELS)
def test_audit(run_ike, site, level):
    got = measure(run_ike, site, level)
    page = got["page"]
    print("\n===== %s =====" % level)
    for k in sorted(page):
        print("  page.%-11s %s" % (k, str(page[k])[:110]))
    for ctx, vals in got.items():
        if ctx == "page":
            continue
        if not isinstance(vals, dict):
            print("  %-14s %s" % (ctx, vals))
            continue
        diff = {k: vals.get(k) for k in page if k != "audio" and vals.get(k) != page.get(k)}
        print("  %-14s %s" % (ctx, "same as page" if not diff else
                                 "; ".join("%s=%s" % (k, str(v)[:70]) for k, v in diff.items())))
    if os.environ.get("FP_AUDIT_OUT"):
        path = os.environ["FP_AUDIT_OUT"]
        data = json.load(open(path)) if os.path.exists(path) else {}
        data[level] = got
        json.dump(data, open(path, "w"), indent=1)
