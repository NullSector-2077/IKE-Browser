"""The graphics card a site is told about, in every place a page can ask
(1.1.18): WebGL 1 and 2, OffscreenCanvas in the page and in workers, frames of
every kind (from an address, srcdoc, empty frames used at once, nested), and
workers of every kind (blob of any type and size, data, module, from an
address, shared, started by a worker, from a blob address made in a worker). At
Balanced every place names the same common model for the site; at Strict and
Maximum too, one of the cards most common in Steam's survey (1.1.29, the
owner's choice; until 1.1.28 no place named a model). Software WebGL (SwiftShader) stands in for a graphics
card in the tests; its name must never reach a page.

Known limit: a worker started from an address of the site
(`new Worker("/w.js")`, shared or service workers) runs a script the browser
cannot add anything to (Qt WebEngine injects scripts into pages, not
workers, and its request hooks cannot change a response), so it sees the
real values. Those places are measured and kept apart below.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from conftest import steam_card

# what one place reports: [vendor, renderer, extension offered, cores]
GL_PROBE = r"""
function glInfo(make) {
  try {
    var gl = make();
    if (!gl) return 'no webgl';
    var exts = gl.getSupportedExtensions() || [];
    var has = exts.indexOf('WEBGL_debug_renderer_info') >= 0;
    var d = gl.getExtension('WEBGL_debug_renderer_info');
    return [d ? gl.getParameter(d.UNMASKED_VENDOR_WEBGL) : null,
            d ? gl.getParameter(d.UNMASKED_RENDERER_WEBGL) : null,
            has || !!d, (typeof navigator !== 'undefined') ? navigator.hardwareConcurrency : null];
  } catch (e) { return 'error ' + e; }
}
"""

WORKER_JS = GL_PROBE + r"""
function report() {
  return [glInfo(function () { return new OffscreenCanvas(4, 4).getContext('webgl'); }),
          glInfo(function () { return new OffscreenCanvas(4, 4).getContext('webgl2'); })];
}
if (typeof onconnect !== 'undefined' || self.constructor.name === 'SharedWorkerGlobalScope') {
  onconnect = function (e) { e.ports[0].postMessage(report()); };
} else postMessage(report());
"""

PAGE = r"""<!doctype html><html><head><title>gpu</title></head><body>
<script>
""" + GL_PROBE + r"""
var WORKER_JS = %s;
function canvasGL(doc, kind) { return doc.createElement('canvas').getContext(kind); }
function fromWorker(make) {
  return new Promise(function (ok) {
    var t = setTimeout(function () { ok('timeout'); }, 4000);
    try {
      var w = make();
      var port = w.port || w;
      port.onmessage = function (e) { clearTimeout(t); ok(e.data); };
      w.onerror = function (e) { clearTimeout(t); ok('worker error'); };
      if (w.port) w.port.start();
    } catch (e) { clearTimeout(t); ok('error ' + e); }
  });
}
function frameLoaded(f) { return new Promise(function (ok) { f.onload = function () { ok(); }; }); }
(async function () {
  var R = {};
  R.page_webgl = glInfo(function () { return canvasGL(document, 'webgl'); });
  R.page_webgl2 = glInfo(function () { return canvasGL(document, 'webgl2'); });
  R.page_offscreen = glInfo(function () { return new OffscreenCanvas(4, 4).getContext('webgl'); });
  // an empty frame, used at once, before anything could have run in it
  var f0 = document.createElement('iframe');
  document.body.appendChild(f0);
  R.empty_frame_now = glInfo(function () { return canvasGL(f0.contentDocument, 'webgl'); });
  R.empty_frame_offscreen = glInfo(function () { return new f0.contentWindow.OffscreenCanvas(4, 4).getContext('webgl'); });
  // nested empty frames
  var f1 = f0.contentDocument.createElement('iframe');
  f0.contentDocument.body.appendChild(f1);
  R.nested_frame_now = glInfo(function () { return canvasGL(f1.contentDocument, 'webgl2'); });
  // srcdoc and a frame from an address of the same site
  var f2 = document.createElement('iframe');
  f2.srcdoc = '<p>srcdoc</p>';
  var l2 = frameLoaded(f2); document.body.appendChild(f2); await l2;
  R.srcdoc_frame = glInfo(function () { return canvasGL(f2.contentDocument, 'webgl'); });
  var f3 = document.createElement('iframe');
  f3.src = '/frame';
  var l3 = frameLoaded(f3); document.body.appendChild(f3); await l3;
  R.address_frame = glInfo(function () { return canvasGL(f3.contentDocument, 'webgl'); });
  // a frame written by the HTML parser
  document.body.insertAdjacentHTML('beforeend', '<iframe id="parsed"></iframe>');
  R.parsed_frame = glInfo(function () { return canvasGL(document.getElementById('parsed').contentDocument, 'webgl'); });
  // workers of every kind
  var blob = URL.createObjectURL(new Blob([WORKER_JS], { type: 'text/javascript' }));
  R.blob_worker = await fromWorker(function () { return new Worker(blob); });
  R.module_worker = await fromWorker(function () { return new Worker(blob, { type: 'module' }); });
  R.data_worker = await fromWorker(function () {
    return new Worker('data:text/javascript,' + encodeURIComponent(WORKER_JS)); });
  R.address_worker = await fromWorker(function () { return new Worker('/worker.js'); });
  R.address_shared_worker = await fromWorker(function () { return new SharedWorker('/worker.js'); });
  R.blob_shared_worker = await fromWorker(function () { return new SharedWorker(blob); });
  // (1.1.18, independent review) a blob of any type and size, a worker
  // started by a worker, and a blob address made in a worker
  R.octet_worker = await fromWorker(function () {
    return new Worker(URL.createObjectURL(new Blob([WORKER_JS], { type: 'application/octet-stream' }))); });
  R.big_worker = await fromWorker(function () {
    return new Worker(URL.createObjectURL(new Blob([WORKER_JS, '/*' + 'x'.repeat(9000000) + '*/'],
                                                   { type: 'text/javascript' }))); });
  R.nested_worker = await fromWorker(function () {
    var outer = 'var u = URL.createObjectURL(new Blob([' + JSON.stringify(WORKER_JS) + '], {type: "text/javascript"}));' +
                'var w = new Worker(u); w.onmessage = function (e) { postMessage(e.data); };';
    return new Worker(URL.createObjectURL(new Blob([outer], { type: 'text/javascript' }))); });
  R.minted_worker = await new Promise(function (ok) {
    var maker = new Worker(URL.createObjectURL(new Blob(['postMessage(URL.createObjectURL(new Blob([' +
      JSON.stringify(WORKER_JS) + '], {type: "text/javascript"})))'], { type: 'text/javascript' })));
    maker.onmessage = function (e) { fromWorker(function () { return new Worker(e.data); }).then(ok); };
    setTimeout(function () { ok('timeout'); }, 5000);
  });
  R.frame_blob_worker = await fromWorker(function () {
    var W = f0.contentWindow.Worker, U = f0.contentWindow.URL, B = f0.contentWindow.Blob;
    return new W(U.createObjectURL(new B([WORKER_JS], { type: 'text/javascript' }))); });
  try {
    if (navigator.gpu) {
      var ad = await Promise.race([navigator.gpu.requestAdapter(), new Promise(function (ok) { setTimeout(ok, 1500); })]);
      R.webgpu = ad && ad.info ? [ad.info.vendor, ad.info.architecture, ad.info.device, ad.info.description] : 'no adapter';
    } else R.webgpu = 'none';
  } catch (e) { R.webgpu = 'error ' + e; }
  window.gpuResult = JSON.stringify(R);
})();
</script></body></html>""" % json.dumps(WORKER_JS)


@pytest.fixture
def site():
    page, worker = PAGE.encode(), WORKER_JS.encode()

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.startswith("/worker.js"):
                body, kind = worker, "text/javascript"
            elif self.path.startswith("/frame"):
                body, kind = b"<!doctype html><p>frame</p>", "text/html"
            else:
                body, kind = page, "text/html; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield "http://127.0.0.1:%d/gpu" % srv.server_address[1]
    srv.shutdown()


STEPS = r'''
import json
from PyQt6.QtCore import QUrl

def steps(ike, qapp, out):
    v = ike.windows[0].current_view()
    done = {}
    v.page().loadFinished.connect(lambda ok, done=done: done.setdefault("ok", ok))
    v.load(QUrl(URL))
    while "ok" not in done:
        yield 20
    for _ in range(400):
        res = {}
        v.page().runJavaScript("window.gpuResult || ''", 0, lambda r, res=res: res.setdefault("r", r))
        while "r" not in res:
            yield 20
        if res["r"]:
            out["r"] = json.loads(res["r"])
            return
        yield 50
'''

FLAGS = "--no-sandbox --enable-unsafe-swiftshader --use-angle=swiftshader --ignore-gpu-blocklist"


UNREACHABLE = ("address_worker", "address_shared_worker")      # see the known limit above


def places(r):
    """Every [vendor, renderer, offered, cores] reported, by place."""
    out = {}
    for k, v in r.items():
        if k == "webgpu" or k in UNREACHABLE:
            continue
        if isinstance(v, list) and v and isinstance(v[0], list):        # a worker: webgl, webgl2
            out[k + ".webgl"], out[k + ".webgl2"] = v[0], v[1]
        else:
            out[k] = v
    return out


@pytest.mark.parametrize("level", ["balanced", "strict", "maximum"])
def test_the_same_card_everywhere(run_ike, site, level):
    out = run_ike("URL = %r\n" % site + STEPS, settings={"shield_level": level},
                  env={"QTWEBENGINE_CHROMIUM_FLAGS": FLAGS}, timeout=120)
    r = out.get("r")
    assert r, out
    seen = places(r)
    bad = {k: v for k, v in seen.items() if not isinstance(v, list)}
    assert not bad, ("a place could not be measured", bad)
    # the real renderer of this computer (SwiftShader, llvmpipe...), read with the shield off
    real = run_ike("URL = %r\n" % site + STEPS, settings={"shield_level": "off"},
                   env={"QTWEBENGINE_CHROMIUM_FLAGS": FLAGS}, timeout=120)["r"]["page_webgl"][1]
    assert real and real not in json.dumps(seen), ("the real renderer reached the page", real)
    names = {(v[0], v[1]) for v in seen.values()}
    assert len(names) == 1, ("not the same card everywhere", seen)
    vendor, renderer = names.pop()
    assert vendor.startswith("Google Inc. (") and renderer.startswith("ANGLE ("), (vendor, renderer)
    assert all(v[2] for v in seen.values()), seen
    if level != "balanced":
        assert vendor == "Google Inc. (NVIDIA Corporation)" and steam_card(renderer), (vendor, renderer)
    cores = {v[3] for v in seen.values()}
    assert len(cores) == 1, ("not the same number of cores everywhere", seen)


# A real graphics card is emulated in the page before the protection runs:
# the model a site is told about must be one of the same maker (its limits
# and extensions tell the maker anyway; another maker's name would be a
# contradiction a script can see).
REAL_CARD = r"""
(function () {
  var V = %r, R = %r;
  [self.WebGLRenderingContext, self.WebGL2RenderingContext].forEach(function (GL) {
    if (!GL) return;
    var orig = GL.prototype.getParameter;
    GL.prototype.getParameter = function (p) {
      var r = orig.apply(this, arguments);
      if (p === 37445 && typeof r === 'string') return V;
      if (p === 37446 && typeof r === 'string') return R;
      return r;
    };
  });
})();
"""

EMULATE = r"""
from PyQt6.QtWebEngineCore import QWebEngineScript

def emulate(ike, source):
    for p in ike.shields.profiles:
        s = QWebEngineScript()
        s.setName("test-real-card")
        s.setSourceCode(source)
        s.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        s.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        s.setRunsOnSubFrames(True)
        for old in p.scripts().find("content"):
            p.scripts().remove(old)
        p.scripts().insert(s)
    ike.shields.apply_settings()             # the protection again, after the emulation
"""


@pytest.mark.parametrize("vendor,renderer,maker", [
    ("Google Inc. (NVIDIA Corporation)",
     "ANGLE (NVIDIA Corporation, NVIDIA GeForce RTX 4070 SUPER/PCIe/SSE2, OpenGL 4.5.0)", "NVIDIA"),
    ("Google Inc. (Intel)", "ANGLE (Intel, Mesa Intel(R) Arc(tm) A770 Graphics (DG2), OpenGL 4.6)", "Intel"),
])
def test_the_model_named_is_of_the_real_cards_maker(run_ike, site, vendor, renderer, maker):
    script = ("URL = %r\nREAL = %r\n" % (site, REAL_CARD % (vendor, renderer)) + EMULATE
              + STEPS.replace("    v = ike.windows[0].current_view()",
                              "    emulate(ike, REAL)\n    yield 300\n    v = ike.windows[0].current_view()"))
    out = run_ike(script, settings={"shield_level": "balanced"},
                  env={"QTWEBENGINE_CHROMIUM_FLAGS": FLAGS}, timeout=120)
    r = out.get("r")
    assert r, out
    # the emulation reaches the page itself only: frames get their protection
    # from the page before any script of theirs (the emulation included) runs
    page = {k: v for k, v in places(r).items() if k.startswith("page_")}
    names = {(v[0], v[1]) for v in page.values()}
    assert len(names) == 1, page
    got_vendor, got_renderer = names.pop()
    assert got_renderer != renderer, "the real model reached the page"
    assert maker in got_vendor and maker in got_renderer, (got_vendor, got_renderer)
