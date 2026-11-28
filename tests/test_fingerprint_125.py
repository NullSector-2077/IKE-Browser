"""The fingerprinting fixes of 1.1.25 (a run of the real browser against
browserleaks.com and CreepJS, the owner's decisions of 2026-11-24):

- every place a site can ask (the page, frames, dedicated, shared and service
  workers, the request headers) gives the same brand list in the same order,
  the same Chrome version and no kernel version: service and shared workers get
  the engine's own client hints, never the profile's, and gave "Chromium" only,
  the engine's full version and the real kernel (6.18.44) where the page said
  "Google Chrome", 140.0.0.0 and 6.0.0;
- Strict and Maximum start no service worker and no shared worker from a
  site's own file (their script is refused in the engine), and a service
  worker registered before at a lower level is unregistered;
- Strict and Maximum: Chrome's own five PDF plugins (the two invented ones had
  no type: "missing mimetype"); the network in JavaScript and in the client
  hints is one common set; the languages are the first one and its base, as
  the header says them;
- Strict and Maximum: one WebGL identity for every user (one card name,
  a fixed list of extensions, a fixed floor of limits, never above the real);
- Strict and Maximum: no canvas noise where a fingerprinting script looks for
  it (a canvas of solid rectangles, flat areas), the noise of the edges
  elsewhere, the same pixel for a pixel read alone or with the whole picture.

SIMULATION: a local server (127.0.0.1, a secure context) with the pages and
the workers' files; software WebGL for the WebGL checks.
"""

import http.server
import json
import re
import threading

import pytest

PDF_PLUGINS = ["PDF Viewer", "Chrome PDF Viewer", "Chromium PDF Viewer", "Microsoft Edge PDF Viewer",
               "WebKit built-in PDF"]
GL_FLAGS = "--no-sandbox --enable-unsafe-swiftshader --use-angle=swiftshader --ignore-gpu-blocklist"

# ---- identity in every place --------------------------------------------------------------------
WORKER = r"""
async function info() {
  var n = self.navigator, o = {langs: Array.from(n.languages || []), lang: n.language};
  try {
    o.brands = JSON.stringify(n.userAgentData.brands);
    var h = await n.userAgentData.getHighEntropyValues(['platformVersion', 'fullVersionList', 'uaFullVersion']);
    o.full = h.uaFullVersion; o.list = JSON.stringify(h.fullVersionList); o.pv = h.platformVersion;
  } catch (e) { o.err = String(e); }
  try { var c = n.connection; o.net = c ? [c.effectiveType, c.rtt, c.downlink, c.saveData] : null; } catch (e) {}
  return o;
}
"""

PAGE = r"""<!doctype html><title>w</title><body><script>
var WSRC = %s;
async function worker(make) {
  return new Promise(function (ok) {
    try { make(ok); } catch (e) { ok('error ' + e); }
    setTimeout(function () { ok('timeout'); }, 8000);
  });
}
(async function () {
  var R = {};
  R.page = await info();
  R.page.plugins = Array.from(navigator.plugins).map(function (p) {
    return [p.name, p.filename, p.description, p.length, p.length ? p[0].type : null]; });
  R.page.mimes = Array.from(navigator.mimeTypes).map(function (m) { return m.type; });
  try {
    var reg = await navigator.serviceWorker.register('/sw.js');
    R.reg = 'ok';
    R.sw = await worker(function (ok) {
      navigator.serviceWorker.onmessage = function (e) { ok(e.data); };
      var w = reg.installing || reg.waiting || reg.active;
      var go = function () { (reg.active || w).postMessage('hi'); };
      if (reg.active) go(); else w.addEventListener('statechange', function () { if (w.state === 'activated') go(); });
    });
  } catch (e) { R.reg = e.name + ': ' + e.message; }
  try { R.regs = (await navigator.serviceWorker.getRegistrations()).length; } catch (e) { R.regs = 'error ' + e.name; }
  R.file_shared = await worker(function (ok) {
    var s = new SharedWorker('/shw.js'); s.port.onmessage = function (e) { ok(e.data); }; s.port.start();
    s.onerror = function () { ok('error'); }; });
  R.blob_shared = await worker(function (ok) {
    var u = URL.createObjectURL(new Blob([WSRC + "onconnect = function (e) { var p = e.ports[0]; info().then(function (o) { p.postMessage(o); }); };"], {type: 'text/javascript'}));
    var s = new SharedWorker(u); s.port.onmessage = function (e) { ok(e.data); }; s.port.start();
    s.onerror = function () { ok('error'); }; });
  R.file_worker = await worker(function (ok) {
    var s = new Worker('/dw.js'); s.onmessage = function (e) { ok(e.data); }; s.onerror = function () { ok('error'); }; });
  var f = document.createElement('iframe'); f.src = '/frame'; document.body.appendChild(f);
  await new Promise(function (ok) { f.onload = ok; });
  R.frame = await f.contentWindow.info();
  await fetch('/after?' + Math.random());
  window.result = JSON.stringify(R);
})();
""" + WORKER + r"""
</script></body>"""

FILES = {
    "/sw.js": WORKER + "self.addEventListener('install', function () { self.skipWaiting(); });"
                       "self.addEventListener('activate', function (e) { e.waitUntil(clients.claim()); });"
                       "self.addEventListener('message', function (e) { info().then(function (o) { e.source.postMessage(o); }); });",
    "/shw.js": WORKER + "onconnect = function (e) { var p = e.ports[0]; info().then(function (o) { p.postMessage(o); }); };",
    "/dw.js": WORKER + "info().then(function (o) { postMessage(o); });",
    "/frame": "<!doctype html><script>" + WORKER + "</script>",
    "/plain": "<!doctype html><title>plain</title><p>plain",
}


@pytest.fixture
def site():
    seen = []

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            path = self.path.split("?")[0]
            seen.append((path, {k.lower(): v for k, v in self.headers.items() if k.lower().startswith(
                ("sec-ch-ua", "rtt", "downlink", "ect", "accept-language"))}))
            if path in FILES:
                body = FILES[path].encode()
                kind = "text/javascript" if path.endswith(".js") else "text/html"
            else:
                body, kind = (PAGE % json.dumps(WORKER)).encode(), "text/html"
            self.send_response(200)
            self.send_header("Accept-CH", "Sec-CH-UA-Full-Version, Sec-CH-UA-Full-Version-List, "
                             "Sec-CH-UA-Platform-Version, RTT, Downlink, ECT")
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1], seen
    srv.shutdown()


LOAD = r'''
import json
from PyQt6.QtCore import QUrl

def load(view, url, key, out, wait="window.result || ''", tries=400):
    done = {}
    view.page().loadFinished.connect(lambda ok, d=done: d.setdefault("ok", ok))
    view.load(QUrl(url))
    while "ok" not in done:
        yield 20
    for _ in range(tries):
        res = {}
        view.page().runJavaScript(wait, 0, lambda r, res=res: res.__setitem__("r", r))
        while "r" not in res:
            yield 20
        if res["r"]:
            out[key] = res["r"]
            return
        yield 100
'''

STEPS = LOAD + r'''
def steps(ike, qapp, out):
    view = ike.windows[0].current_view()
    for i in range(2):          # the second load carries the client hints the site asked for
        yield from load(view, "http://127.0.0.1:%d/page" + str(i), "r" + str(i), out)
'''


def _header_list(text):
    """[(brand, version)] of a Sec-CH-UA header."""
    return re.findall(r'"([^"]*)";v="([^"]*)"', text or "")


@pytest.mark.parametrize("level", ["compatibility", "balanced", "strict", "maximum"])
def test_every_place_gives_the_same_identity(run_ike, site, level):
    port, seen = site
    settings = {"shield_level": level, "accept_language": "de-DE,de,en-US,en"}
    out = run_ike(STEPS % port, settings=settings, timeout=180)
    r = json.loads(out["r1"])
    page = r["page"]
    strict = level in ("strict", "maximum")
    places = {"page": page, "frame": r["frame"], "blob_shared": r["blob_shared"], "file_worker": r["file_worker"]}
    if strict:
        # no service worker, no shared worker from a file: their scripts are refused
        assert r["reg"].startswith("TypeError: Failed to register a ServiceWorker"), r["reg"]
        assert r["regs"] == 0 and "sw" not in r, r
        assert r["file_shared"] == "error", r["file_shared"]
        assert not [p for p, h in seen if p in ("/sw.js", "/shw.js")], seen
    else:
        assert r["reg"] == "ok" and r["regs"] == 1, r
        places["service_worker"], places["file_shared"] = r["sw"], r["file_shared"]
    bad = {k: v for k, v in places.items() if not isinstance(v, dict) or "err" in v}
    assert not bad, bad
    # the same brands, in the same order, the same versions, no kernel version, everywhere
    for name, v in places.items():
        assert (v["brands"], v["list"], v["full"], v["pv"]) == (page["brands"], page["list"], page["full"], ""), \
            (level, name, v, page)
    brands = json.loads(page["brands"])
    # the engine's own order at every level (review round 2: Qt sorted a list it was given at Strict)
    assert [b["brand"] for b in brands] == ["Not=A?Brand", "Chromium"], brands
    assert "Google Chrome" not in page["brands"]
    major = page["full"].split(".")[0]
    if strict:
        assert page["full"] == major + ".0.0.0", page
    assert [b["version"] for b in json.loads(page["list"]) if b["brand"] == "Chromium"] == [page["full"]], page
    # the headers say the same
    asked = [h for p, h in seen if "sec-ch-ua-full-version-list" in h]
    assert asked, seen
    for h in asked:
        assert _header_list(h["sec-ch-ua"]) == [(b["brand"], b["version"]) for b in brands], (h, brands)
        assert _header_list(h["sec-ch-ua-full-version-list"]) == [
            (b["brand"], b["version"]) for b in json.loads(page["list"])], (h, page)
        assert h["sec-ch-ua-full-version"] == '"%s"' % page["full"], h
        assert h["sec-ch-ua-platform-version"] == '""', h
    nets = [(h.get("rtt"), h.get("downlink"), h.get("ect")) for p, h in seen if "rtt" in h]
    assert nets, seen
    if strict:
        # one common network, in JavaScript (page, frame, inline workers) and in the headers
        for name in ("page", "frame", "blob_shared"):
            assert places[name]["net"] == ["4g", 50, 10, False], (name, places[name])
        assert set(nets) == {("50", "10", "4g")}, nets
        # Chrome's own five PDF viewers with their two types, nothing invented (1.1.29:
        # in an order of the site's own, for Cover Your Tracks, tests/test_cover_your_tracks.py)
        assert sorted(p[0] for p in page["plugins"]) == sorted(PDF_PLUGINS), page["plugins"]
        assert all(p[1:] == ["internal-pdf-viewer", "Portable Document Format", 2, "application/pdf"]
                   for p in page["plugins"]), page["plugins"]
        assert page["mimes"] == ["application/pdf", "text/pdf"], page
    else:
        # unchanged: Balanced keeps its two invented plugins, Compatibility the engine's list
        assert len(page["plugins"]) == (7 if level == "balanced" else 5), page["plugins"]
    if level == "strict":
        # the first language and its base, as the header says them, in workers from a file too
        assert page["langs"] == ["de-DE", "de"] and page["lang"] == "de-DE", page
        assert r["file_worker"]["langs"] == ["de-DE", "de"], r["file_worker"]
        langs = {h["accept-language"] for p, h in seen if "accept-language" in h}
        assert langs == {"de-DE,de;q=0.9"}, langs
    if level == "maximum":
        assert page["langs"] == ["en-US", "en"], page                # unchanged


STEPS_OLD_WORKER = LOAD + r'''
def steps(ike, qapp, out):
    view = ike.windows[0].current_view()
    yield from load(view, "http://127.0.0.1:%d/plain", "loaded", out, wait="document.title")
    yield 3000              # the protection unregisters an older service worker on its own
    out["regs"] = None
    res = {}
    view.page().runJavaScript("navigator.serviceWorker.getRegistrations().then(function (r) {"
                              " window.__regs = r.length; }); 1", 0, lambda r: None)
    for _ in range(100):
        view.page().runJavaScript("window.__regs === undefined ? '' : String(window.__regs)", 0,
                                  lambda r, res=res: res.__setitem__("r", r))
        while "r" not in res:
            yield 20
        if res["r"]:
            out["regs"] = int(res.pop("r"))
            return
        res.clear()
        yield 50
'''


def test_strict_unregisters_an_older_service_worker(run_ike, site):
    """A service worker registered at Balanced would still start with the
    engine's own values at Strict: it is unregistered there."""
    port, seen = site
    out = run_ike(STEPS % port, settings={"shield_level": "balanced"}, timeout=180)
    assert json.loads(out["r1"])["regs"] == 1
    out = run_ike(STEPS_OLD_WORKER % port, settings={"shield_level": "balanced"}, keep_profile=True, timeout=120)
    assert out["regs"] == 1, out                          # kept at Balanced
    out = run_ike(STEPS_OLD_WORKER % port, settings={"shield_level": "strict"}, keep_profile=True, timeout=120)
    assert out["regs"] == 0, out


# ---- WebGL ---------------------------------------------------------------------------------------
GL_PROBE = r"""
function glProbe(make) {
  var gl = make();
  if (!gl) return 'no webgl';
  var R = {};
  // the card's name before the extension is enabled: the engine's own INVALID_ENUM and null
  R.before = [gl.getParameter(0x9246), gl.getError()];
  var d = gl.getExtension('WEBGL_debug_renderer_info');
  R.card = d ? [gl.getParameter(d.UNMASKED_VENDOR_WEBGL), gl.getParameter(d.UNMASKED_RENDERER_WEBGL)] : null;
  R.exts = gl.getSupportedExtensions();
  R.hidden = [!!gl.getExtension('EXT_clip_control'), !!gl.getExtension('ext_CLIP_control')];
  gl.getError(); gl.getParameter(0x935D); R.hiddenEnum = gl.getError();       // CLIP_ORIGIN_EXT, never enabled
  var P = {};
  [0x0D33, 0x851C, 0x84E8, 0x8869, 0x8DFB, 0x8DFD, 0x8DFC, 0x8B4C, 0x8872, 0x8B4D, 0x0D50, 0x8073, 0x88FF, 0x8D57,
   0x8A2F, 0x8A30, 0x8A2B, 0x8A2D, 0x8A2E, 0x8B4A, 0x8B49, 0x8A31, 0x8A33, 0x9122, 0x9125, 0x8B4B, 0x8C8A, 0x8C8B,
   0x8C80, 0x8904, 0x8905, 0x84FD, 0x8D6B, 0x8A34, 0x0D3A, 0x846E, 0x846D, 0x80E8, 0x80E9].forEach(function (p) {
    var v = gl.getParameter(p); gl.getError();
    P[p] = v && typeof v === 'object' ? [Object.prototype.toString.call(v), Array.from(v)] : v;
  });
  R.params = P;
  R.objectName = Array.from(gl.getParameter({ valueOf: function () { return 0x846E; } }) || []);
  // a plain colour read back (review round 2: the noise changed some)
  gl.clearColor(0.2, 0.4, 0.6, 1); gl.clear(gl.COLOR_BUFFER_BIT);
  var px = new Uint8Array(4 * 4 * 4); gl.readPixels(0, 0, 4, 4, gl.RGBA, gl.UNSIGNED_BYTE, px);
  R.flat = Array.from(px).join() === Array(16).fill('51,102,153,255').join();
  if (gl.getInternalformatParameter) R.samples = Array.from(gl.getInternalformatParameter(gl.RENDERBUFFER, gl.RGBA8, gl.SAMPLES) || []);
  return R;
}
"""

GL_PAGE = r"""<!doctype html><title>gl</title><body><script>
""" + GL_PROBE + r"""
(async function () {
  var R = {};
  R.webgl = glProbe(function () { return document.createElement('canvas').getContext('webgl'); });
  R.webgl2 = glProbe(function () { return document.createElement('canvas').getContext('webgl2'); });
  var f = document.createElement('iframe'); document.body.appendChild(f);
  R.frame = glProbe(function () { return f.contentDocument.createElement('canvas').getContext('webgl'); });
  var src = %s + "postMessage([glProbe(function () { return new OffscreenCanvas(4, 4).getContext('webgl'); })," +
    "glProbe(function () { return new OffscreenCanvas(4, 4).getContext('webgl2'); })]);";
  R.worker = await new Promise(function (ok) {
    var w = new Worker(URL.createObjectURL(new Blob([src], {type: 'text/javascript'})));
    w.onmessage = function (e) { ok(e.data); }; setTimeout(function () { ok('timeout'); }, 8000); });
  window.result = JSON.stringify(R);
})();
</script></body>""" % json.dumps(GL_PROBE)

# the floor of the limits at Strict (fingerprint.js GLX.lim): [kind, a, b]
FLOOR = {0x0D33: [0, 16384], 0x851C: [0, 16384], 0x84E8: [0, 16384], 0x0D3A: [2, 16384, 16384], 0x8869: [0, 16],
         0x8DFB: [0, 1024], 0x8DFD: [0, 1024], 0x8DFC: [0, 15], 0x8B4C: [0, 16], 0x8872: [0, 16], 0x8B4D: [0, 32],
         0x0D50: [0, 4], 0x846E: [3, 1, 1], 0x846D: [3, 1, 255], 0x8073: [0, 2048], 0x88FF: [0, 2048],
         0x8D57: [0, 4], 0x8A2F: [0, 24], 0x8A30: [0, 16384], 0x8A2B: [0, 12], 0x8A2D: [0, 12], 0x8A2E: [0, 24],
         0x8B4A: [0, 4096], 0x8B49: [0, 4096], 0x8A31: [0, 53248], 0x8A33: [0, 53248], 0x9122: [0, 64],
         0x9125: [0, 60], 0x8B4B: [0, 60], 0x8C8A: [0, 64], 0x8C8B: [0, 4], 0x8C80: [0, 4], 0x8904: [1, -8],
         0x8905: [0, 7], 0x84FD: [0, 2], 0x8D6B: [0, 16777215], 0x8A34: [1, 256], 0x80E8: [0, 3000], 0x80E9: [0, 3000]}
ALLOWED = {"angle_instanced_arrays", "ext_blend_minmax", "ext_color_buffer_float", "ext_color_buffer_half_float",
           "ext_frag_depth", "ext_srgb", "ext_texture_compression_rgtc", "ext_texture_filter_anisotropic",
           "khr_parallel_shader_compile", "oes_element_index_uint", "oes_fbo_render_mipmap", "oes_standard_derivatives",
           "oes_texture_float", "oes_texture_float_linear", "oes_texture_half_float", "oes_texture_half_float_linear",
           "oes_vertex_array_object", "webgl_color_buffer_float", "webgl_compressed_texture_s3tc",
           "webgl_depth_texture", "webgl_draw_buffers", "webgl_lose_context", "webgl_multi_draw"}


def _floor(kind, real, a, b=None):
    if real is None:
        return None
    if kind == 0:
        return min(real, a)
    if kind == 1:
        return max(real, a)
    tag, vals = real
    if kind == 2:
        return [tag, [min(vals[0], a), min(vals[1], b)]]
    return [tag, [vals[0], min(vals[1], b)]]


GL_STEPS = LOAD + r'''
def steps(ike, qapp, out):
    view = ike.windows[0].current_view()
    yield from load(view, "http://127.0.0.1:%d/gl", "r", out)
'''


@pytest.fixture
def gl_site():
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = GL_PAGE.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1]
    srv.shutdown()


def test_strict_webgl_is_one_identity(run_ike, gl_site):
    real = json.loads(run_ike(GL_STEPS % gl_site, settings={"shield_level": "off"},
                              env={"QTWEBENGINE_CHROMIUM_FLAGS": GL_FLAGS}, timeout=120)["r"])
    assert isinstance(real["webgl"], dict), real
    for level in ("strict", "maximum"):
        got = json.loads(run_ike(GL_STEPS % gl_site, settings={"shield_level": level},
                                 env={"QTWEBENGINE_CHROMIUM_FLAGS": GL_FLAGS}, timeout=120)["r"])
        places = {"webgl": got["webgl"], "webgl2": got["webgl2"], "frame": got["frame"],
                  "worker": got["worker"][0], "worker2": got["worker"][1]}
        reals = {"webgl": real["webgl"], "webgl2": real["webgl2"], "frame": real["frame"],
                 "worker": real["worker"][0], "worker2": real["worker"][1]}
        for name, g in places.items():
            r = reals[name]
            # no card name: the extension is not offered, the engine's own answer without it
            # (Chrome's: INVALID_ENUM and null)
            assert g["before"] == r["before"] == [None, 0x0500], (name, g["before"], r["before"])
            assert g["card"] is None and r["card"] is not None, (name, g["card"])
            assert "WEBGL_debug_renderer_info" not in g["exts"] and "WEBGL_debug_shaders" not in g["exts"], name
            assert g["flat"] is True and r["flat"] is True, name
            # the fixed list of extensions, never one the real context lacks, in the engine's order
            assert g["exts"] == [e for e in r["exts"] if e.lower() in ALLOWED], (name, g["exts"], r["exts"])
            assert g["hidden"] == [False, False] and r["hidden"] == [True, True], (name, g["hidden"], r["hidden"])
            assert g["hiddenEnum"] == 0x0500, (name, g["hiddenEnum"])
            # the floor of the limits, never above the real one
            for p, (kind, *ab) in FLOOR.items():
                assert g["params"][str(p)] == _floor(kind, r["params"][str(p)], *ab), \
                    (name, hex(p), g["params"][str(p)], r["params"][str(p)])
            assert g["objectName"] == [1, 1], (name, g["objectName"])     # a name given as an object is read once
            if "samples" in g:
                assert g["samples"] == [s for s in r["samples"] if s <= 4] and g["samples"], (name, g, r)
        assert places["webgl"]["exts"] == places["frame"]["exts"] == places["worker"]["exts"]
        assert places["webgl2"]["exts"] == places["worker2"]["exts"]
        assert places["webgl"]["params"] == places["frame"]["params"] == places["worker"]["params"]


# ---- canvas --------------------------------------------------------------------------------------
CANVAS_PAGE = r"""<!doctype html><title>canvas</title><body><script>
function hash(a) { var h = 2166136261; for (var i = 0; i < a.length; i++) { h ^= a[i]; h = Math.imul(h, 16777619); } return (h >>> 0).toString(16); }
function shash(s) { var h = 2166136261; for (var i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return (h >>> 0).toString(16); }
function text(doc) {
  var c = doc.createElement('canvas'); c.width = 200; c.height = 40;
  var x = c.getContext('2d'); x.fillStyle = '#fff'; x.fillRect(0, 0, 200, 40);
  x.fillStyle = '#123456'; x.fillRect(140, 0, 60, 40);              // a flat area in a canvas with text
  x.fillStyle = '#d02'; x.font = '18px sans-serif'; x.fillText('I.K.E. Wg', 2, 26);
  return c;
}
(function () {
  var R = {};
  // CreepJS's check: random colours, one pixel each, read back one by one
  // (the same "random" colours in every run, so the picture can be compared)
  var c1 = document.createElement('canvas'), c2 = document.createElement('canvas'); c1.width = c1.height = c2.width = c2.height = 8;
  var x1 = c1.getContext('2d', {willReadFrequently: true}), x2 = c2.getContext('2d', {willReadFrequently: true}), diffs = 0;
  var seq = 12345, rnd = function () { seq = (Math.imul(seq, 1103515245) + 12345) >>> 0; return (seq >>> 16) & 255; };
  for (var x = 0; x < 8; x++) for (var y = 0; y < 8; y++) {
    var col = [rnd(), rnd(), rnd()];
    x1.fillStyle = 'rgba(' + col.join(', ') + ', 255)'; x1.fillRect(x, y, 1, 1);
    var d = x1.getImageData(x, y, 1, 1).data;
    x2.fillStyle = 'rgba(' + [d[0], d[1], d[2]].join(', ') + ', 255)'; x2.fillRect(x, y, 1, 1);
    var e = x2.getImageData(x, y, 1, 1).data;
    if (d[0] !== col[0] || d[1] !== col[1] || d[2] !== col[2] || e[0] !== d[0] || e[1] !== d[1] || e[2] !== d[2]) diffs++;
  }
  R.pixelMods = diffs;
  R.flatUrl = shash(c1.toDataURL());
  // a canvas with text: noise (two sessions differ), stable, the same in a frame of the site
  var t = text(document), tx = t.getContext('2d');
  R.textUrl = shash(t.toDataURL()); R.textAgain = shash(t.toDataURL());
  var full = tx.getImageData(0, 0, 200, 40).data;
  R.textData = hash(full);
  // the flat area of that canvas reads back exactly
  var flat = tx.getImageData(142, 2, 56, 36).data, wrong = 0;
  for (var i = 0; i < flat.length; i += 4) if (flat[i] !== 0x12 || flat[i + 1] !== 0x34 || flat[i + 2] !== 0x56 || flat[i + 3] !== 255) wrong++;
  R.flatWrong = wrong;
  // a pixel read alone is the pixel of the whole picture (no way around the noise in small reads)
  var alone = [];
  for (var yy = 10; yy < 30; yy++) for (var xx = 0; xx < 60; xx++) {
    var p = tx.getImageData(xx, yy, 1, 1).data; alone.push(p[0], p[1], p[2], p[3]); }
  var part = [];
  for (yy = 10; yy < 30; yy++) for (xx = 0; xx < 60; xx++) { var k = (yy * 200 + xx) * 4; part.push(full[k], full[k + 1], full[k + 2], full[k + 3]); }
  R.aloneSame = hash(alone) === hash(part);
  R.part = hash(part);
  var f = document.createElement('iframe'); document.body.appendChild(f);
  R.frameText = shash(text(f.contentDocument).toDataURL());
  R.frameData = hash(text(f.contentDocument).getContext('2d').getImageData(0, 0, 200, 40).data);
  // the same text drawn in 4 x 4 pieces: no small canvas is left without the noise (review
  // round 2, LOW-11: pieces that small could be put together into any picture)
  var tiles = [];
  for (var ty = 0; ty < 16; ty += 4) for (var tq = 0; tq < 64; tq += 4) {
    var tc = document.createElement('canvas'); tc.width = tc.height = 4; var tt = tc.getContext('2d');
    tt.fillStyle = '#fff'; tt.fillRect(0, 0, 4, 4); tt.fillStyle = '#d02'; tt.font = '14px sans-serif';
    tt.fillText('Wg Wg Wg', -tq, 12 - ty); tiles.push(hash(tt.getImageData(0, 0, 4, 4).data)); }
  R.tiles = shash(tiles.join());
  tx.clearRect(0, 0, 200, 40);
  R.cleared = Math.max.apply(null, Array.from(tx.getImageData(0, 0, 8, 8).data));
  window.result = JSON.stringify(R);
})();
</script></body>"""

CANVAS_STEPS = LOAD + r'''
def steps(ike, qapp, out):
    view = ike.windows[0].current_view()
    yield from load(view, "http://127.0.0.1:%d/canvas", "r", out)
'''


@pytest.fixture
def canvas_site():
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = CANVAS_PAGE.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1]
    srv.shutdown()


def test_strict_canvas_noise_only_on_edges(run_ike, canvas_site):
    off = json.loads(run_ike(CANVAS_STEPS % canvas_site, settings={"shield_level": "off"}, timeout=90)["r"])
    runs = [json.loads(run_ike(CANVAS_STEPS % canvas_site, settings={"shield_level": "strict"}, timeout=90)["r"])
            for _ in range(2)]
    for r in runs:
        assert r["pixelMods"] == 0, r                       # CreepJS: "pixel data modified" no more
        assert r["flatUrl"] == off["flatUrl"] and r["flatWrong"] == 0, (r, off)     # exactly as drawn
        assert r["aloneSame"] is True, r
        # 1.1.29: every export is the site's own picture, in a frame of the site
        # too (1.1.27 to 1.1.28 varied it at every export); the pixels read too
        assert len({r["textUrl"], r["textAgain"], r["frameText"]}) == 1, r
        assert r["textData"] == r["frameData"], r
        assert r["cleared"] == 0, r
    a, b = runs
    # the noise is there: text differs from the real picture, and between sessions
    assert a["textUrl"] != off["textUrl"] and a["textData"] != off["textData"] and a["part"] != off["part"], (a, off)
    assert a["textUrl"] != b["textUrl"] and a["textData"] != b["textData"], (a, b)
    assert a["tiles"] != off["tiles"] and b["tiles"] != off["tiles"], (a, b, off)
    assert off["pixelMods"] == 0 and off["aloneSame"] is True
