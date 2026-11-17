"""Fingerprinting protection and list scriptlets together.

The same page of the same site is measured three times in one session: twice
without scriptlets (the values must be stable within a session), then with a
set of uBlock Origin scriptlets that wrap the functions pages use most
(timers, fetch, XHR, JSON, events, eval, animation frames, constants). What
sites see — canvas, WebGL, audio, navigator, screen, Client Hints, media
devices, WebGPU, workers, frames, and functions that must look native — must
not change because of the scriptlets. With IKE_TEST_FP_OUT=<file> the
measured values are also written there (before/after comparisons).
"""

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from conftest import engine_flags, needs_engine

from ike.osinfo import identity

PROBE = r"""<!doctype html><html><head><title>fp</title></head><body>
<script>
(async function () {
  var R = {};
  function hash(s) { var h = 2166136261; for (var i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return (h >>> 0).toString(16); }
  function canvasHash(doc) {
    var c = doc.createElement('canvas'); c.width = 220; c.height = 40;
    var x = c.getContext('2d');
    x.textBaseline = 'top'; x.font = '16px sans-serif'; x.fillStyle = '#f60'; x.fillRect(5, 5, 100, 20);
    x.fillStyle = '#069'; x.fillText('I.K.E. fingerprint ☺', 2, 10);
    x.strokeStyle = 'rgba(102,204,0,0.7)'; x.arc(160, 20, 15, 0, Math.PI * 2); x.stroke();
    return hash(c.toDataURL()) + ':' + hash(Array.from(x.getImageData(0, 0, 220, 40).data.slice(0, 4000)).join(','));
  }
  try { R.canvas = canvasHash(document); } catch (e) { R.canvas = 'error ' + e; }
  try {
    var gl = document.createElement('canvas').getContext('webgl');
    var dbg = gl && gl.getExtension('WEBGL_debug_renderer_info');
    R.webgl = gl ? [gl.getParameter(gl.VENDOR), gl.getParameter(gl.RENDERER),
      dbg ? gl.getParameter(dbg.UNMASKED_VENDOR_WEBGL) : null, dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : null,
      gl.getParameter(gl.MAX_TEXTURE_SIZE), (gl.getSupportedExtensions() || []).join(',')] : null;
  } catch (e) { R.webgl = 'error ' + e; }
  try {
    var ac = new OfflineAudioContext(1, 5000, 44100), o = ac.createOscillator(), comp = ac.createDynamicsCompressor();
    o.type = 'triangle'; o.frequency.value = 10000; o.connect(comp); comp.connect(ac.destination); o.start(0);
    var buf = await ac.startRendering(), d = buf.getChannelData(0), sum = 0;
    for (var i = 4500; i < 5000; i++) sum += Math.abs(d[i]);
    R.audio = sum.toFixed(10);
  } catch (e) { R.audio = 'error ' + e; }
  var n = navigator;
  R.navigator = [n.userAgent, n.appVersion, n.platform, n.vendor, n.hardwareConcurrency, n.deviceMemory,
    (n.languages || []).join(','), n.plugins.length, Array.from(n.plugins).map(function (p) { return p.name; }).join(','),
    n.mimeTypes.length, n.webdriver, n.maxTouchPoints, n.pdfViewerEnabled, n.doNotTrack, n.globalPrivacyControl];
  R.screen = [screen.width, screen.height, screen.availWidth, screen.availHeight, screen.colorDepth, screen.pixelDepth,
    devicePixelRatio];
  try {
    var ua = n.userAgentData;
    R.hints = ua ? [JSON.stringify(ua.brands), ua.mobile, ua.platform, JSON.stringify(await ua.getHighEntropyValues(
      ['architecture', 'bitness', 'model', 'platformVersion', 'fullVersionList', 'uaFullVersion', 'wow64']))] : null;
  } catch (e) { R.hints = 'error ' + e; }
  try {
    var devs = await n.mediaDevices.enumerateDevices();
    R.media = devs.map(function (d) { return d.kind + ':' + d.deviceId + ':' + d.label; }).join('|');
  } catch (e) { R.media = 'error ' + e; }
  try {
    if (n.gpu) {
      var ad = await Promise.race([n.gpu.requestAdapter(), new Promise(function (ok) { setTimeout(ok, 1500); })]);
      R.webgpu = ad ? [ad.info ? [ad.info.vendor, ad.info.architecture, ad.info.device, ad.info.description].join('/') : '',
        Array.from(ad.features || []).sort().join(',')] : 'no adapter';
    } else R.webgpu = 'none';
  } catch (e) { R.webgpu = 'error ' + e; }
  try {
    R.worker = await new Promise(function (ok) {
      var src = "var c=null;try{var oc=new OffscreenCanvas(60,20),x=oc.getContext('2d');x.fillText('ike',2,10);" +
        "c=Array.from(x.getImageData(0,0,60,20).data).join(',').length}catch(e){c='e'}" +
        "postMessage([navigator.userAgent,navigator.platform,navigator.hardwareConcurrency,navigator.deviceMemory," +
        "(navigator.languages||[]).join(','),c])";
      var w = new Worker(URL.createObjectURL(new Blob([src], { type: 'text/javascript' })));
      w.onmessage = function (e) { ok(e.data); };
      w.onerror = function () { ok('worker error'); };
      setTimeout(function () { ok('worker timeout'); }, 3000);
    });
  } catch (e) { R.worker = 'error ' + e; }
  try {
    var f = document.createElement('iframe'); document.body.appendChild(f);
    var fw = f.contentWindow;
    R.frame = [fw.navigator.hardwareConcurrency, fw.navigator.userAgent, fw.navigator.plugins.length,
      fw.screen.width, canvasHash(fw.document)];
  } catch (e) { R.frame = 'error ' + e; }
  var natives = {
    toDataURL: HTMLCanvasElement.prototype.toDataURL, getImageData: CanvasRenderingContext2D.prototype.getImageData,
    getParameter: WebGLRenderingContext.prototype.getParameter, getChannelData: AudioBuffer.prototype.getChannelData,
    hardwareConcurrency: Object.getOwnPropertyDescriptor(Navigator.prototype, 'hardwareConcurrency').get,
    toString: Function.prototype.toString, setTimeout: window.setTimeout, setInterval: window.setInterval,
    fetch: window.fetch, xhrOpen: XMLHttpRequest.prototype.open, addEventListener: EventTarget.prototype.addEventListener,
    jsonParse: JSON.parse, requestAnimationFrame: window.requestAnimationFrame, eval: window.eval,
    enumerateDevices: MediaDevices.prototype.enumerateDevices
  };
  R.natives = {};
  Object.keys(natives).forEach(function (k) {
    var f = natives[k], s = '';
    try { s = Function.prototype.toString.call(f); } catch (e) { s = 'error'; }
    R.natives[k] = [/\{\s*\[native code\]\s*\}\s*$/.test(s), f && f.name, f && f.length];
  });
  R.scriptlets = window.ikeFpTestConstant === 1;
  window.fpResult = JSON.stringify(R);
})();
</script></body></html>"""

SCRIPTLETS = "\n".join("127.0.0.1##+js(%s)" % r for r in (
    "set-constant, ikeFpTestConstant, 1",
    "no-setTimeout-if, ikeNeverMatches",
    "no-setInterval-if, ikeNeverMatches",
    "prevent-fetch, icenever.example",
    "prevent-xhr, icenever.example",
    "json-prune, ikeNeverKey",
    "addEventListener-defuser, ikeNeverEvent",
    "no-requestAnimationFrame-if, ikeNeverMatches",
    "noeval-if, ikeNeverMatches",
    "abort-on-property-read, ikeNeverProperty",
    "remove-attr, data-ike-never",
))


@pytest.fixture
def site():
    body = PROBE.encode()

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield "http://127.0.0.1:%d/fp" % srv.server_address[1]
    srv.shutdown()


STEPS = r'''
import json
from PyQt6.QtCore import QUrl

def measure(v, url, out, key):
    done = {}
    v.page().loadFinished.connect(lambda ok, done=done: done.setdefault("ok", ok))
    v.load(QUrl(url))
    while "ok" not in done:
        yield 20
    for _ in range(300):
        res = {}
        v.page().runJavaScript("window.fpResult || ''", 0, lambda r, res=res: res.setdefault("r", r))
        while "r" not in res:
            yield 20
        if res["r"]:
            out[key] = json.loads(res["r"])
            return
        yield 50
    out[key] = None

def steps(ike, qapp, out):
    v = ike.windows[0].current_view()
    yield from measure(v, URL, out, "plain")
    yield from measure(v, URL + "?again", out, "plain_again")
    ike.config["custom_filters"] = SCRIPTLETS
    ike.blocker.load()                     # rebuilds the engine and the scriptlet index
    yield 300
    out["rules"] = ike.blocker.scriptlets.scripts_for("127.0.0.1")
    yield from measure(v, URL + "?scriptlets", out, "scriptlets")
'''


@needs_engine
@pytest.mark.parametrize("level", ["balanced", "maximum"])
def test_scriptlets_do_not_change_fingerprint(run_ike, site, level):
    # software WebGL, so the WebGL values are measured too
    webgl = os.environ.get("IKE_TEST_WEBGL_FLAGS", "").split() or [
        "--enable-unsafe-swiftshader", "--use-angle=swiftshader", "--ignore-gpu-blocklist"]
    if os.name == "nt" and not os.environ.get("IKE_TEST_WEBGL_FLAGS"):
        # Windows runners have no graphics card: there the engine's Direct3D
        # compositing loses its context after a page or two ("Already being
        # accessed for read", "Failed to make current") and WebGL goes with it,
        # whatever renders WebGL (SwiftShader, WARP or the default). Compositing
        # in software keeps WebGL working: tried on the runner with each of
        # those, every try without this switch failed and none with it did.
        # A switch of this test only, never of the browser.
        webgl.append("--disable-gpu-compositing")
    flags = engine_flags(*webgl)
    out = run_ike("URL = %r\nSCRIPTLETS = %r\n" % (site, SCRIPTLETS) + STEPS,
                  settings={"shield_level": level}, env={"QTWEBENGINE_CHROMIUM_FLAGS": flags}, timeout=120)
    print("engine messages:\n" + out["_stderr"][-6000:])      # shown when the test fails
    plain, again, with_scriptlets = out["plain"], out["plain_again"], out["scriptlets"]
    if os.environ.get("IKE_TEST_FP_OUT"):
        with open(os.environ["IKE_TEST_FP_OUT"] + "." + level + ".json", "w", encoding="utf-8") as f:
            json.dump({"plain": plain, "scriptlets": with_scriptlets}, f, indent=1, sort_keys=True)
    assert plain and again and with_scriptlets
    assert out["rules"]["MAIN"], "the scriptlets were not installed"
    assert not plain["scriptlets"] and with_scriptlets["scriptlets"]   # they really ran
    assert plain["webgl"], ("WebGL not available", out["_stderr"][-2500:])
    for key in ("canvas", "webgl", "audio", "navigator", "screen", "hints", "media", "webgpu",
                "worker", "frame"):
        assert not str(plain[key]).startswith("error"), (key, plain[key])
        assert plain[key] == again[key], ("not stable within a session", key, plain[key], again[key],
                                          out["_stderr"][-2500:] if key == "webgl" else "")
        assert with_scriptlets[key] == plain[key], ("changed by the scriptlets", key, plain[key],
                                                    with_scriptlets[key])
    for name, (native, fname, length) in plain["natives"].items():
        assert native, ("does not look native without scriptlets", name)
        assert with_scriptlets["natives"][name] == [native, fname, length], ("changed by the scriptlets", name)
    # the protection is really on: the graphics card is not the real one
    assert "SwiftShader" not in json.dumps(plain["webgl"])
    # the system named to sites is the one I.K.E. runs on (Linux, or Windows),
    # the same in the request header, in scripts, in Client Hints and workers
    ident = identity()
    windows = ident["os"] == "windows"
    assert ident["os"] == ("windows" if os.name == "nt" else "linux")
    nav = plain["navigator"]
    assert ident["ua_os"] in nav[0], nav[0]
    assert ("Windows NT 10.0; Win64; x64" in nav[0]) == windows and ("X11; Linux x86_64" in nav[0]) != windows
    assert nav[2] == ident["navigator_platform"] == ("Win32" if windows else "Linux x86_64"), nav[2]
    assert plain["hints"][2] == ident["platform"] == ("Windows" if windows else "Linux")
    assert json.loads(plain["hints"][3])["platformVersion"] == ident["platform_version"]
    assert plain["worker"][0] == nav[0] and plain["frame"][1] == nav[0]
    assert plain["worker"][1] == nav[2], plain["worker"]
    if level == "balanced":                 # Maximum hides the graphics card's name
        # a card as Chrome names it on this system: through Direct3D on
        # Windows, through Mesa or OpenGL on Linux - never the other one
        assert ("Direct3D11" in plain["webgl"][3]) == windows, plain["webgl"]
        assert ("OpenGL" in plain["webgl"][3]) != windows, plain["webgl"]
