"""Hostile frames (1.1.18 review): every way a page can make or reach a new
window of its own and use it at once, before the browser has run anything in
it. Each frame must give the same canvas noise, number of cores and graphics
card as the page itself (never the real ones), at Balanced and at Strict.

The frame guard of fingerprint.js protects a new same-site frame when the
page puts it in the document (hooked DOM methods; while the page is built, a
watch of the parser) and when the page first reaches its window. This test
plays the ways that are not the usual appendChild: srcdoc, outerHTML,
replaceWith / before / after / prepend / append, replaceChild, insertBefore,
insertAdjacentElement, <object>, document.write into a frame, DOMParser with
importNode / adoptNode, Element.setHTMLUnsafe with a declarative shadow root,
cloneNode of a subtree, moveBefore, a frame's document opened again, a frame
sent to a new about:blank, frames inside a frame made with the frame's own
methods, and the innerHTML of the body.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

PAGE = r"""<!doctype html><title>frames</title><body><div id=box></div><script>
function hash(s) { var h = 2166136261; for (var i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return (h >>> 0).toString(16); }
function sig(win) {
  try {
    var doc = win.document, c = doc.createElement('canvas'); c.width = 200; c.height = 40;
    var x = c.getContext('2d');
    x.textBaseline = 'top'; x.font = '16px sans-serif'; x.fillStyle = '#f60'; x.fillRect(5, 5, 100, 20);
    x.fillStyle = '#069'; x.fillText('I.K.E. frames', 2, 10);
    var gl = doc.createElement('canvas').getContext('webgl'), d = gl && gl.getExtension('WEBGL_debug_renderer_info');
    return [hash(c.toDataURL()), win.navigator.hardwareConcurrency, d ? gl.getParameter(d.UNMASKED_RENDERER_WEBGL) : null];
  } catch (e) { return 'error ' + e; }
}
function last() { return window[window.length - 1]; }
function box() { return document.getElementById('box'); }
function slot() { var p = document.createElement('p'); box().appendChild(p); return p; }
function loaded(el) { return new Promise(function (ok) { el.addEventListener('load', function () { ok(); }, {once: true}); }); }
window.run = async function () {
  var R = {top: sig(window)};
  // srcdoc: its first (empty) window at once, then its own document
  var s = document.createElement('iframe'); s.srcdoc = '<p>srcdoc</p>';
  var sl = loaded(s); box().appendChild(s);
  R.srcdoc_now = sig(s.contentWindow);
  await sl; R.srcdoc_loaded = sig(s.contentWindow);
  var p = slot(); p.outerHTML = '<iframe></iframe>'; R.outerhtml = sig(last());
  slot().replaceWith(document.createElement('iframe')); R.replacewith = sig(last());
  slot().before(document.createElement('iframe')); R.before = sig(last());
  slot().after(document.createElement('iframe')); R.after = sig(last());
  var q = slot(); q.prepend(document.createElement('iframe')); R.prepend = sig(q.querySelector('iframe').contentWindow);
  var q2 = slot(); q2.append(document.createElement('iframe')); R.append = sig(q2.querySelector('iframe').contentWindow);
  var q3 = slot(), old = q3.appendChild(document.createElement('span'));
  q3.replaceChild(document.createElement('iframe'), old); R.replacechild = sig(q3.querySelector('iframe').contentWindow);
  var q4 = slot(); q4.insertBefore(document.createElement('iframe'), null); R.insertbefore = sig(q4.querySelector('iframe').contentWindow);
  var q5 = slot(); q5.insertAdjacentElement('afterbegin', document.createElement('iframe'));
  R.adjacentelement = sig(q5.querySelector('iframe').contentWindow);
  // an <object> showing a page of the site
  var o = document.createElement('object'); o.type = 'text/html'; o.data = '/frame';
  var ol = loaded(o); box().appendChild(o); await ol;
  R.object = o.contentWindow ? sig(o.contentWindow) : 'no window';
  // a frame written into another frame's document
  var w = document.createElement('iframe'); box().appendChild(w);
  w.contentDocument.open(); w.contentDocument.write('<iframe id=inner></iframe>'); w.contentDocument.close();
  R.written_outer = sig(w.contentWindow);
  R.written_inner = sig(w.contentDocument.getElementById('inner').contentWindow);
  // frames inside a frame, made with the frame's own methods
  var fd = w.contentDocument, own = fd.createElement('iframe'); fd.body.appendChild(own);
  R.frame_own_methods = sig(own.contentWindow);
  // parsed elsewhere, brought in
  var parsed = new DOMParser().parseFromString('<iframe></iframe>', 'text/html').querySelector('iframe');
  slot().appendChild(document.importNode(parsed, true)); R.domparser_import = sig(last());
  var parsed2 = new DOMParser().parseFromString('<iframe></iframe>', 'text/html').querySelector('iframe');
  slot().appendChild(document.adoptNode(parsed2)); R.domparser_adopt = sig(last());
  // a declarative shadow root
  if (Element.prototype.setHTMLUnsafe) {
    var h = slot(); h.setHTMLUnsafe('<div><template shadowrootmode="open"><iframe></iframe></template></div>');
    var sr = h.firstChild.shadowRoot;
    R.declarative_shadow = sr ? sig(sr.querySelector('iframe').contentWindow) : 'no shadow root';
  } else R.declarative_shadow = R.top;
  // a subtree cloned with its frame
  var t = document.createElement('div'); t.innerHTML = '<span><iframe></iframe></span>';
  slot().appendChild(t.cloneNode(true)); R.clone = sig(last());
  // moveBefore (keeps a frame's window): moved frames stay as they were
  if (Element.prototype.moveBefore) {
    var m = document.createElement('iframe'); box().appendChild(m);
    var dest = slot(); dest.moveBefore(m, null); R.movebefore = sig(m.contentWindow);
  } else R.movebefore = R.top;
  // a frame's document opened again, and a frame sent to a new empty page
  var r1 = document.createElement('iframe'); box().appendChild(r1);
  r1.contentDocument.open(); r1.contentDocument.close(); R.reopened = sig(r1.contentWindow);
  var r2 = document.createElement('iframe'); box().appendChild(r2);
  var rl = loaded(r2); r2.contentWindow.location.replace('about:blank'); await rl;
  R.renavigated = sig(r2.contentWindow);
  // the body's innerHTML written again with a frame in it
  document.body.insertAdjacentHTML('beforeend', '<div id=tail></div>');
  document.getElementById('tail').innerHTML += '<iframe></iframe>'; R.innerhtml_plus = sig(last());
  window.result = JSON.stringify(R);
};
</script>frames</body>"""


@pytest.fixture
def site():
    page = PAGE.encode()

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            body = b"<!doctype html><p>frame</p>" if self.path.startswith("/frame") else page
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield "http://127.0.0.1:%d/" % srv.server_address[1]
    srv.shutdown()


STEPS = r'''
import json
from PyQt6.QtCore import QUrl

def steps(ike, qapp, out):
    v = ike.windows[0].current_view()
    done = {}
    v.page().loadFinished.connect(lambda ok: done.setdefault("ok", ok))
    v.load(QUrl(URL))
    while "ok" not in done:
        yield 20
    yield 300
    v.page().runJavaScript("run()")
    for _ in range(300):
        res = {}
        v.page().runJavaScript("window.result || ''", 0, lambda r, res=res: res.setdefault("r", r))
        while "r" not in res:
            yield 20
        if res["r"]:
            out["r"] = json.loads(res["r"])
            return
        yield 50
'''

FLAGS = "--no-sandbox --enable-unsafe-swiftshader --use-angle=swiftshader --ignore-gpu-blocklist"


@pytest.mark.parametrize("level", ["balanced", "strict"])
def test_every_way_to_a_new_frame_is_protected(run_ike, site, level):
    real = run_ike("URL = %r\n" % site + STEPS, settings={"shield_level": "off"},
                   env={"QTWEBENGINE_CHROMIUM_FLAGS": FLAGS}, timeout=120)["r"]["top"]
    r = run_ike("URL = %r\n" % site + STEPS, settings={"shield_level": level},
                env={"QTWEBENGINE_CHROMIUM_FLAGS": FLAGS}, timeout=120).get("r")
    assert r, "the page did not finish"
    top = r["top"]
    assert top[0] != real[0], "the canvas is not protected at all"
    assert top[2] != real[2], "the real graphics card reached the page"
    wrong = {k: v for k, v in r.items() if v != top}
    assert not wrong, ("frames that do not answer as the page does", top, json.dumps(wrong))
