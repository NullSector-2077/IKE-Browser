"""Exported pictures of a canvas: the site's own (1.1.30, the owner's decision).

Cover Your Tracks counts a canvas or a WebGL picture as "randomized" when it
differs between two sites (tests/test_cover_your_tracks.py); a picture that
varied at every export (1.1.27 to 1.1.28) read "randomized" on both of its
sites, which it takes for the same value, so it never counted. Now an export
(toDataURL, toBlob, convertToBlob, in pages and workers) is the picture with
the site's noise, every time:

- every export of the same drawing is the same, at Balanced and at Strict:
  what getImageData gives (the site's noise, never the real picture) with a
  little noise of its own at the edges of the drawing, from a key of the
  site's (as much as the variation of 1.1.27 to 1.1.29: "Nothing gets worse"
  measures it), so it is the same at every export on a site;
- the noise touches the lowest bit only;
- flat colours are never changed: a canvas of solid rectangles exports the
  same picture every time at Strict (1.1.25's exact canvases);
- with the shield off nothing changes.

SIMULATION: a local page draws and reads its own canvases.
"""

import http.server
import json
import threading

import pytest

PAGE = rb"""<!doctype html><title>exports</title><body><script>
function draw(c) {
  var x = c.getContext('2d');
  // opaque everywhere: a partly transparent pixel does not survive a picture
  // file unchanged (premultiplied colours), noise or not
  x.fillStyle = '#fff'; x.fillRect(0, 0, 300, 50);
  x.textBaseline = 'top'; x.font = '18px sans-serif'; x.fillStyle = '#f60'; x.fillRect(10, 5, 120, 30);
  x.fillStyle = '#069'; x.fillText('Cwm fjordbank glyphs vext quiz', 2, 12);
  x.strokeStyle = 'rgba(102,204,0,0.7)'; x.beginPath(); x.arc(250, 25, 18, 0, Math.PI * 2); x.stroke();
}
function decode(url) {
  return new Promise(function (ok) {
    var im = new Image();
    im.onload = function () {
      var c = document.createElement('canvas'); c.width = 300; c.height = 50;
      var x = c.getContext('2d'); x.drawImage(im, 0, 0);
      ok(Array.from(x.getImageData(0, 0, 300, 50).data));
    };
    im.src = url;
  });
}
window.run = async function () {
  var c = document.createElement('canvas'); c.width = 300; c.height = 50; draw(c);
  var r = {};
  var urls = []; for (var i = 0; i < 15; i++) urls.push(c.toDataURL());
  r.twoDiffer = urls[0] !== urls[1];
  r.distinct = new Set(urls).size;
  var x = c.getContext('2d');
  var g1 = Array.from(x.getImageData(0, 0, 300, 50).data), g2 = Array.from(x.getImageData(0, 0, 300, 50).data);
  r.readsSame = g1.join() === g2.join();
  // the majority of the exports, pixel byte by pixel byte
  var dec = []; for (var k = 0; k < urls.length; k++) dec.push(await decode(urls[k]));
  var major = [];
  for (var b = 0; b < g1.length; b++) {
    var count = {}, best = null;
    for (var k = 0; k < dec.length; k++) { var v = dec[k][b]; count[v] = (count[v] || 0) + 1;
      if (best === null || count[v] > count[best]) best = v; }
    major.push(+best);
  }
  r.majorityIsNoised = major.join() === g1.join();
  r.exportIsNoised = dec[0].join() === g1.join();
  // how much an export differs from the site's picture: lowest bits only
  var worst = 0;
  for (var b = 0; b < g1.length; b++) worst = Math.max(worst, Math.abs(dec[0][b] - g1[b]));
  r.worst = worst;
  // solid rectangles only
  var p = document.createElement('canvas'); p.width = 60; p.height = 30;
  var px = p.getContext('2d'); px.fillStyle = '#3a7'; px.fillRect(0, 0, 60, 30); px.fillStyle = '#c21';
  px.fillRect(10, 10, 20, 10);
  r.plainSame = p.toDataURL() === p.toDataURL();
  // a blob export varies too
  var blobs = await Promise.all([0, 1].map(function () {
    return new Promise(function (ok) { c.toBlob(function (bl) { bl.arrayBuffer().then(function (a) {
      ok(Array.from(new Uint8Array(a)).join()); }); }); });
  }));
  r.blobsDiffer = blobs[0] !== blobs[1];
  // in a worker: two convertToBlob of one drawing
  var src = "var c = new OffscreenCanvas(300, 50), x = c.getContext('2d'); x.fillStyle = '#fff'; " +
    "x.fillRect(0, 0, 300, 50); x.fillStyle = '#069'; x.font = '18px sans-serif'; x.fillText('Cwm fjordbank', 2, 30); " +
    "Promise.all([c.convertToBlob(), c.convertToBlob()]).then(function (b) { return Promise.all(b.map(function (q) { " +
    "return q.arrayBuffer(); })); }).then(function (a) { postMessage(Array.from(new Uint8Array(a[0])).join() !== " +
    "Array.from(new Uint8Array(a[1])).join()); });";
  r.workerDiffer = await new Promise(function (ok) {
    var wk = new Worker(URL.createObjectURL(new Blob([src], {type: 'text/javascript'})));
    wk.onmessage = function (e) { ok(e.data); };
  });
  window.result = JSON.stringify(r);
};
run();
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

def steps(ike, qapp, out):
    view = ike.windows[0].current_view()
    done = {}
    view.page().loadFinished.connect(lambda ok: done.setdefault("ok", ok))
    view.load(QUrl("http://127.0.0.1:%d/"))
    while "ok" not in done:
        yield 20
    for _ in range(300):
        res = {}
        view.page().runJavaScript("window.result || ''", 0, lambda r: res.setdefault("r", r))
        while "r" not in res:
            yield 20
        if res["r"]:
            out["r"] = res["r"]
            break
        yield 100
'''


@pytest.mark.parametrize("level", ["balanced", "strict"])
def test_every_export_is_the_sites_own_picture(run_ike, site, level):
    out = run_ike(STEPS % site, settings={"shield_level": level}, timeout=120)
    assert "error" not in out, out.get("error")
    r = json.loads(out["r"])
    assert not r["twoDiffer"] and r["distinct"] == 1, r        # the same picture at every export
    assert not r["blobsDiffer"] and not r["workerDiffer"], r
    assert r["readsSame"], r                                   # getImageData: the same at every read
    assert not r["exportIsNoised"], r                          # the export's own noise on top of it
    assert r["worst"] <= 1, r                                  # the lowest bit only
    if level == "strict":
        assert r["plainSame"], r                               # solid rectangles stay exact (1.1.25)


def test_nothing_changes_with_the_shield_off(run_ike, site):
    out = run_ike(STEPS % site, settings={"shield_level": "off"}, timeout=120)
    r = json.loads(out["r"])
    assert not r["twoDiffer"] and r["distinct"] == 1 and r["plainSame"] and r["worst"] == 0, r
    assert not r["blobsDiffer"] and not r["workerDiffer"], r
