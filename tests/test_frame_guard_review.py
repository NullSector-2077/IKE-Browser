"""The independent review's attack pages for the 1.1.18 frame guard (1.1.18).

An independent review (another model, on headless I.K.E.) found ways to reach
an unprotected frame that the first version of the lighter frame guard left
open; each is played here at Balanced and Strict and must give the page's own
protected values:

- a frame removed, then a new one added (the count of frames is the same) and
  read at once through window[i], by name, or by a javascript: address;
- the same after the frames were emptied with textContent;
- a frame passed off as text (its own nodeType), a table's caption, a new
  body, a node put after the doctype;
- a document opened again (document.open) whose parser writes a frame read by
  the next script after a slow script;
- a page faking readyState and DOMContentLoaded to switch the parser's watch
  off, then a frame written in its HTML and read by the next script.

Kept apart as known, not claimed: a frame written by document.write and read
by a script inside the very same write (the parser runs that script before
anything else can run; the same in 1.1.17).
"""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

COMMON = r"""
function hash(s) { var h = 2166136261; for (var i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return (h >>> 0).toString(16); }
function sig(win) {
  try {
    var doc = win.document, c = doc.createElement('canvas'); c.width = 200; c.height = 40;
    var x = c.getContext('2d');
    x.textBaseline = 'top'; x.font = '16px sans-serif'; x.fillStyle = '#f60'; x.fillRect(5, 5, 100, 20);
    x.fillStyle = '#069'; x.fillText('I.K.E. frames', 2, 10);
    var gl = doc.createElement('canvas').getContext('webgl'), d = gl && gl.getExtension('WEBGL_debug_renderer_info');
    return [hash(c.toDataURL()), win.navigator.hardwareConcurrency, d ? gl.getParameter(d.UNMASKED_RENDERER_WEBGL) : null].join('|');
  } catch (e) { return 'error ' + e; }
}
function last() { return window[window.length - 1]; }
function wait(ms) { return new Promise(function (ok) { setTimeout(ok, ms); }); }
"""

PAGE = r"""<!doctype html><title>frames</title><body><div id=box></div><script>
""" + COMMON + r"""
function box() { return document.getElementById('box'); }
async function both(R, name) { var w = last(); R[name + '.sync'] = sig(w); await wait(80); R[name + '.async'] = sig(last()); }
window.run = async function () {
  var R = {top: sig(window)};
  try {
  box().appendChild(document.createElement('iframe')); await both(R, 'control');
  var a = document.createElement('iframe'); box().appendChild(a); a.remove();
  await wait(80);
  box().appendChild(document.createElement('iframe')); await both(R, 'remove_then_add');
  var holder = document.createElement('div'); box().appendChild(holder);
  holder.appendChild(document.createElement('iframe')); holder.textContent = '';
  await wait(80);
  holder.appendChild(document.createElement('iframe')); await both(R, 'textcontent_then_add');
  box().replaceChildren(); await wait(50);
  var f = document.createElement('iframe'); Object.defineProperty(f, 'nodeType', {value: 3});
  box().appendChild(f); await both(R, 'nodetype_spoof');
  box().replaceChildren(); await wait(50);
  var table = document.createElement('table'); box().appendChild(table);
  var cap = document.createElement('caption'); cap.appendChild(document.createElement('iframe'));
  table.caption = cap; await both(R, 'table_caption');
  box().replaceChildren(); await wait(50);
  var nb = document.createElement('body'); nb.appendChild(document.createElement('iframe'));
  document.body = nb; await both(R, 'body_setter');
  document.documentElement.remove(); await wait(50);
  document.doctype.after(document.createElement('iframe')); await both(R, 'doctype_after');
  } catch (e) { R.error = String(e && e.stack || e); }
  window.result = JSON.stringify(R);
};
</script>frames</body>"""

TIMING = r"""<!doctype html><title>t</title><body><div id=box></div><script>
""" + COMMON + r"""
window.addEventListener('message', function (e) { if (e.data && e.data.js) window.JSURL = e.data.js; });
window.run = async function () {
  var R = {top: sig(window)}, box = document.getElementById('box');
  var a = document.createElement('iframe'); box.appendChild(a); R.first_use = sig(a.contentWindow); box.removeChild(a);
  await wait(200);
  var b = document.createElement('iframe'); b.name = 'probe'; box.appendChild(b);
  R.t_sync = sig(window.frames[0]);
  await Promise.resolve(); R.t_microtask = sig(window.frames[0]);
  box.removeChild(b); await wait(200);
  for (var ms of [0, 5, 40]) {
    var c = document.createElement('iframe'); box.appendChild(c); await wait(ms);
    R['t_after_' + ms + 'ms'] = sig(window.frames[0]); box.removeChild(c); await wait(100);
  }
  var d = document.createElement('iframe'); d.name = 'probe2'; box.appendChild(d);
  R.named_access = sig(window.probe2); box.removeChild(d); await wait(100);
  var j = document.createElement('iframe');
  var src = "function hash(s) { var h = 2166136261; for (var i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return (h >>> 0).toString(16); }";
  j.src = "javascript:" + encodeURIComponent(src + sig.toString() + ";void parent.postMessage({js: sig(window)}, '*')");
  box.appendChild(j); await wait(400);
  R.javascript_url = window.JSURL || 'did not run';
  window.result = JSON.stringify(R);
};
</script>x</body>"""

REOPEN = r"""<!doctype html><title>reopen</title><body><script>
""" + COMMON + r"""
window.run = function () {
  window.TOP = sig(window);
  document.open();
  document.write('<!doctype html><body><script src="/slow.js"><\/script><iframe></iframe><script>window.RAW = sig(window[0]);<\/script>');
  document.close();
  setTimeout(function () { window.result = JSON.stringify({top: window.TOP, 'reopen_parser.sync': window.RAW, 'reopen_parser.async': sig(window[0])}); }, 1500);
};
</script>x</body>"""

SPOOF = r"""<!doctype html><title>spoof</title><head><script>
""" + COMMON + r"""
Object.defineProperty(document, 'readyState', {get: function () { return 'complete'; }, configurable: true});
document.dispatchEvent(new Event('DOMContentLoaded'));
delete document.readyState;
</script></head><body><script src="/slow.js"></script><iframe></iframe><script>
window.RAW = sig(window[0]);
window.run = function () { window.result = JSON.stringify({top: sig(window), 'readystate_spoof.sync': window.RAW, 'readystate_spoof.async': sig(window[0])}); };
</script>x</body>"""

PAGES = {"/timing": TIMING, "/": PAGE, "/reopen": REOPEN, "/spoof": SPOOF}


@pytest.fixture
def site():
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            path = self.path.split("?")[0]
            ctype = "text/html; charset=utf-8"
            if path == "/slow.js":
                time.sleep(0.4)
                body, ctype = b"window.SLOW = 1;", "text/javascript"
            else:
                body = PAGES.get(path, PAGE).encode()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield "http://127.0.0.1:%d" % srv.server_address[1]
    srv.shutdown()


STEPS = r'''
import json
from PyQt6.QtCore import QUrl

def steps(ike, qapp, out):
    v = ike.windows[0].current_view()
    for path in PATHS:
        done = {}
        v.page().loadFinished.connect(lambda ok, done=done: done.setdefault("ok", ok))
        v.load(QUrl(SITE + path))
        while "ok" not in done:
            yield 20
        yield 400
        v.page().runJavaScript("run()")
        for _ in range(240):
            res = {}
            v.page().runJavaScript("window.result || ''", 0, lambda r, res=res: res.setdefault("r", r))
            while "r" not in res:
                yield 20
            if res["r"]:
                out[path] = json.loads(res["r"])
                break
            yield 50
'''

FLAGS = "--no-sandbox --enable-unsafe-swiftshader --use-angle=swiftshader --ignore-gpu-blocklist"


@pytest.mark.parametrize("level", ["balanced", "strict"])
def test_the_reviews_attacks_find_no_unprotected_frame(run_ike, site, level):
    out = run_ike("SITE = %r\nPATHS = %r\n" % (site, list(PAGES)) + STEPS, settings={"shield_level": level},
                  env={"QTWEBENGINE_CHROMIUM_FLAGS": FLAGS}, timeout=180)
    real = run_ike("SITE = %r\nPATHS = ['/timing']\n" % site + STEPS, settings={"shield_level": "off"},
                   env={"QTWEBENGINE_CHROMIUM_FLAGS": FLAGS}, timeout=120)["/timing"]["top"]
    bad = {}
    for path in PAGES:
        r = out.get(path)
        assert r, ("the page did not finish", path)
        assert "error" not in r, (path, r)
        top = r["top"]
        assert top != real, ("the page itself is not protected", path)
        bad.update({path + " " + k: v for k, v in r.items() if k != "top" and v != top})
    assert not bad, json.dumps(bad, indent=1)
