"""Cover Your Tracks says "randomized fingerprint" (1.1.30, the owner).

Its code (EFF's cover-your-tracks, static/fetch_whorls.js and
static/fetch_first_party_isolated_whorls.js) measures five values on two
first parties (coveryourtracks.eff.org and firstpartysimulator.org): the
audio fingerprint, the canvas picture, the WebGL picture, the plugins and the
number of cores. Each one that differs between the two sites counts (a
canvas or WebGL value is first made "randomized" when two reads in the same
page differ, and "randomized" on both sites is equal: it does not count);
four or more and the summary says "your browser has a randomized
fingerprint", whatever the other values.

I.K.E. at every level of protection: the audio, the canvas and the WebGL
pictures are the site's own (the same at every read of a site, another on
every other site), the plugins differ (two invented entries at Balanced, the
engine's own in an order of the site's own at Strict and Maximum) and the
cores are 4 or 8 per site where the computer has 8: at least four of five.

SIMULATION: two local sites (127.0.0.1 and localhost) run the same page,
which measures the five values as fingerprintjs2 does and compares them as
Cover Your Tracks does.
"""

import http.server
import json
import threading

import pytest

GL_FLAGS = "--no-sandbox --enable-unsafe-swiftshader --use-angle=swiftshader --ignore-gpu-blocklist"

PAGE = rb"""<!doctype html><title>cyt</title><body><script>
function hash(s) { var h = 2166136261; for (var i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return (h >>> 0).toString(16); }
function canvasValue() {
  var c = document.createElement('canvas'); c.width = 2000; c.height = 200; c.style.display = 'inline';
  var x = c.getContext('2d');
  x.rect(0, 0, 10, 10); x.rect(2, 2, 6, 6);
  x.textBaseline = 'alphabetic'; x.fillStyle = '#f60'; x.fillRect(125, 1, 62, 20);
  x.fillStyle = '#069'; x.font = '11pt no-real-font-123'; x.fillText('Cwm fjordbank glyphs vext quiz, ' + String.fromCodePoint(0x1F603), 2, 15);
  x.fillStyle = 'rgba(102, 204, 0, 0.2)'; x.font = '18pt Arial'; x.fillText('Cwm fjordbank glyphs vext quiz, ' + String.fromCodePoint(0x1F603), 4, 45);
  x.globalCompositeOperation = 'multiply';
  [['#f2f', 40, 40], ['#2ff', 80, 40], ['#ff2', 60, 80]].forEach(function (a) {
    x.fillStyle = a[0]; x.beginPath(); x.arc(a[1], a[2], 40, 0, Math.PI * 2, true); x.closePath(); x.fill(); });
  return hash(c.toDataURL());
}
function webglValue() {
  var c = document.createElement('canvas'), gl = c.getContext('webgl');
  if (!gl) return 'no webgl';
  var vb = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, vb);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-.2, -.9, 0, .4, -.26, 0, 0, .732134444, 0]), gl.STATIC_DRAW);
  var p = gl.createProgram(), v = gl.createShader(gl.VERTEX_SHADER), f = gl.createShader(gl.FRAGMENT_SHADER);
  gl.shaderSource(v, 'attribute vec2 attrVertex;varying vec2 varyinTexCoordinate;uniform vec2 uniformOffset;void main(){varyinTexCoordinate=attrVertex+uniformOffset;gl_Position=vec4(attrVertex,0,1);}');
  gl.compileShader(v);
  gl.shaderSource(f, 'precision mediump float;varying vec2 varyinTexCoordinate;void main() {gl_FragColor=vec4(varyinTexCoordinate,0,1);}');
  gl.compileShader(f); gl.attachShader(p, v); gl.attachShader(p, f); gl.linkProgram(p); gl.useProgram(p);
  p.vertexPosAttrib = gl.getAttribLocation(p, 'attrVertex'); p.offsetUniform = gl.getUniformLocation(p, 'uniformOffset');
  gl.enableVertexAttribArray(p.vertexPosArray); gl.vertexAttribPointer(p.vertexPosAttrib, 3, gl.FLOAT, false, 0, 0);
  gl.uniform2f(p.offsetUniform, 1, 1); gl.drawArrays(gl.TRIANGLE_STRIP, 0, 3);
  return hash(gl.canvas.toDataURL());
}
function audioValue() {
  return new Promise(function (ok) {
    var C = window.OfflineAudioContext || window.webkitOfflineAudioContext;
    if (!C) return ok('undetermined');
    var ctx = new C(1, 44100, 44100), o = ctx.createOscillator();
    o.type = 'triangle'; o.frequency.setValueAtTime(10000, ctx.currentTime);
    var k = ctx.createDynamicsCompressor();
    [['threshold', -50], ['knee', 40], ['ratio', 12], ['reduction', -20], ['attack', 0], ['release', .25]].forEach(function (a) {
      if (k[a[0]] !== undefined && typeof k[a[0]].setValueAtTime === 'function') k[a[0]].setValueAtTime(a[1], ctx.currentTime); });
    o.connect(k); k.connect(ctx.destination); o.start(0); ctx.startRendering();
    ctx.oncomplete = function (e) {
      var d = e.renderedBuffer.getChannelData(0), s = 0;
      for (var i = 4500; i < 5000; i++) s += Math.abs(d[i]);
      ok(s.toString());
    };
  });
}
function pluginsValue() {
  var out = [];
  for (var i = 0; i < navigator.plugins.length; i++) {
    var p = navigator.plugins[i], types = [];
    for (var j = 0; j < p.length; j++) types.push(p[j].type + '~' + p[j].suffixes);
    out.push(p.name + '::' + p.description + '::' + types.join(','));
  }
  return out.join(';');
}
function twice(f) { var a = f(), b = f(); return a !== b ? 'randomized' : a; }
(async function () {
  var a1 = await audioValue(), a2 = await audioValue();
  window.result = JSON.stringify({
    audio: a1 !== a2 ? 'randomized' : a1, canvas: twice(canvasValue), webgl: twice(webglValue),
    plugins: pluginsValue(), cores: navigator.hardwareConcurrency});
})();
</script></body>"""


@pytest.fixture
def site():
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(PAGE)))
            self.end_headers()
            self.wfile.write(PAGE)

        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1]
    srv.shutdown()


STEPS = r'''
from PyQt6.QtCore import QUrl

def measure(view, url):
    done = {}
    view.page().loadFinished.connect(lambda ok, d=done: d.setdefault("ok", ok))
    view.load(QUrl(url))
    while "ok" not in done:
        yield 20
    for _ in range(300):
        res = {}
        view.page().runJavaScript("window.result || ''", 0, lambda r, res=res: res.setdefault("r", r))
        while "r" not in res:
            yield 20
        if res["r"]:
            return res["r"]
        yield 100
    return ""

def steps(ike, qapp, out):
    view = ike.windows[0].current_view()
    out["first"] = yield from measure(view, "http://127.0.0.1:%d/")
    out["second"] = yield from measure(view, "http://localhost:%d/")
'''


def counted(results, fpi):
    """Cover Your Tracks' count (static/fetch_whorls.js): results are the
    values on its own site, fpi those of the other first party."""
    n = 0
    for key in ("audio", "canvas", "webgl", "plugins"):
        if fpi[key] != results[key] and fpi[key] != "undetermined":
            n += 1
    if fpi["cores"] != results["cores"]:
        n += 1
    return n


@pytest.mark.parametrize("level", ["balanced", "strict", "maximum"])
def test_cover_your_tracks_sees_a_randomized_fingerprint(run_ike, site, level):
    out = run_ike(STEPS % (site, site), settings={"shield_level": level},
                  env={"QTWEBENGINE_CHROMIUM_FLAGS": GL_FLAGS}, timeout=180)
    a, b = json.loads(out["first"]), json.loads(out["second"])
    # the canvas and WebGL pictures: the site's own, the same at both reads of a site
    assert "randomized" not in (a["canvas"], a["webgl"], b["canvas"], b["webgl"]), (a, b)
    assert a["webgl"] != "no webgl", a
    n = counted(a, b)
    assert n >= 4, (level, n, a, b)                    # "your browser has a randomized fingerprint"
    # what differs between the two sites
    assert a["audio"] != b["audio"] and a["canvas"] != b["canvas"] and a["webgl"] != b["webgl"], (a, b)
    assert a["plugins"] != b["plugins"], (a["plugins"], b["plugins"])
    if level != "balanced":
        # the engine's own five entries, nothing invented, in another order
        assert sorted(a["plugins"].split(";")) == sorted(b["plugins"].split(";")), (a, b)
        assert a["plugins"].count("::") == 2 * 5, a["plugins"]


def test_nothing_is_randomized_with_the_shield_off(run_ike, site):
    out = run_ike(STEPS % (site, site), settings={"shield_level": "off"},
                  env={"QTWEBENGINE_CHROMIUM_FLAGS": GL_FLAGS}, timeout=180)
    a, b = json.loads(out["first"]), json.loads(out["second"])
    assert counted(a, b) == 0, (a, b)
