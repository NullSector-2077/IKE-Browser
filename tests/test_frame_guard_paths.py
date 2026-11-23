"""The frame guard's quicker ways of 1.1.24, played as attacks.

The guard (fingerprint.js) no longer looks at an insertion into a node
outside any document, no longer counts the frames before a call when it saw
none at its last look, nor before a call that swaps nodes (it looks after
it anyway). Each way a page can then bring a frame into the page is played
here, at Balanced and Strict, and the new frame is read AT ONCE, in the same
task, through each way to its window, each on a frame of its own (the first
look at a frame is the one that counts):

- ways in: a tree built outside the page with the frame inside, then put in
  with appendChild, insertBefore, append (a fragment), prepend, before,
  after, replaceWith, replaceChild, replaceChildren, insertAdjacentElement,
  Range.insertNode; HTML written with insertAdjacentHTML, innerHTML (in the
  page, and outside it then put in), outerHTML, setHTMLUnsafe, a template's
  content, DOMParser; a cloned tree; a frame moved around outside the page
  first; a srcdoc frame;
- ways to the window: window[i], frames[i], frames[name], window[name],
  document.getElementById(...).contentWindow and .contentDocument;
- frames inside frames: built outside the frame's page then put in, put in
  with the parent's own appendChild, written with document.write;
- a frame swapped for another (the number of frames stays the same) with
  replaceChild, replaceWith, replaceChildren, setHTMLUnsafe, outerHTML,
  innerHTML; a frame taken out of the page and put back;
- the page lying to the guard: a Node.prototype.isConnected that says
  "outside", the same as an own property of the target, a
  firstElementChild that says "no children", a localName that says "div";
- frames in a shadow root (not in window[i]: read through contentWindow and
  contentDocument), with the host in the page or put in later;
- an <object> frame the guard may not have counted yet, then a new frame
  and the object moved.

Between cases every frame is taken away, one time with replaceChildren (the
guard sees it) and the next with removeChild (it does not), so both of the
guard's ways are played.

Every frame here loads a page of the site, so until it has loaded its
window holds the first, empty document: an empty frame (no src) fires its
load event at once, inside the insertion, and the guard's listener of that
event protects it whatever the insertion did; such frames would not show a
gap in the insertion paths.

Kept apart as known, not claimed (the same in 1.1.23, found while writing
these tests): page code that runs inside the very call that puts the frame
in, before the call returns and so before the guard looks: a script put in
together with the frame (a fragment from createContextualFragment), or a
custom element's connectedCallback put in with it. Like a script inside the
same document.write (tests/test_frame_guard_review.py).
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

PAGE = r"""<!doctype html><title>paths</title><body><div id=box></div><script>
function hash(s) { var h = 2166136261; for (var i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return (h >>> 0).toString(16); }
function sig(win) {
  try {
    var doc = win.document, c = doc.createElement('canvas'); c.width = 200; c.height = 40;
    var x = c.getContext('2d');
    x.textBaseline = 'top'; x.font = '16px sans-serif'; x.fillStyle = '#f60'; x.fillRect(5, 5, 100, 20);
    x.fillStyle = '#069'; x.fillText('I.K.E. paths', 2, 10);
    return [hash(c.toDataURL()), win.navigator.hardwareConcurrency];
  } catch (e) { return 'error ' + e; }
}
function box() { return document.getElementById('box'); }
var N = 0, CLEAN = 0;
function names() { N++; return {name: 'n' + N, id: 'i' + N}; }
// Each frame loads a page of the site: until it has loaded, its window holds
// the first, empty document, which the engine runs nothing in, and no load
// event comes at once (an empty frame's load event, heard by the guard, would
// protect it by itself). The empty outer frames of the nested cases keep
// their first document.
function frameEl(doc, k) {
  var f = (doc || document).createElement('iframe'); f.name = k.name; f.id = k.id;
  if (!k.empty) f.src = '/frame?' + k.name;
  return f;
}
function html(k) { return '<span><iframe name="' + k.name + '" id="' + k.id + '" src="/frame?' + k.name + '"></iframe></span>'; }
function outer() { var k = names(); k.empty = true; return frameEl(null, k); }
// a tree built outside the page, the frame deep inside
function tree(f) { var d = document.createElement('div'), s = document.createElement('section'); d.appendChild(s); s.appendChild(f); return d; }
function slot() { var p = document.createElement('p'); box().appendChild(p); return p; }
function clean() {
  var b = box();
  if (CLEAN++ % 2) b.replaceChildren();
  else while (b.firstChild) b.removeChild(b.firstChild);
}
function loaded(el) {
  return new Promise(function (ok) { el.addEventListener('load', function () { ok(); }, {once: true}); setTimeout(ok, 3000); });
}
var WAYS = {
  appendChild: function (k) { box().appendChild(tree(frameEl(null, k))); },
  insertBefore: function (k) { var s = slot(); box().insertBefore(tree(frameEl(null, k)), s); },
  append_fragment: function (k) { var fr = document.createDocumentFragment(); fr.append(tree(frameEl(null, k))); box().append(fr); },
  prepend: function (k) { slot().prepend(tree(frameEl(null, k))); },
  before: function (k) { slot().before(tree(frameEl(null, k))); },
  after: function (k) { slot().after(tree(frameEl(null, k))); },
  replaceWith: function (k) { slot().replaceWith(tree(frameEl(null, k))); },
  replaceChild: function (k) { var s = slot(); box().replaceChild(tree(frameEl(null, k)), s); },
  replaceChildren: function (k) { slot().replaceChildren(tree(frameEl(null, k))); },
  insertAdjacentElement: function (k) { slot().insertAdjacentElement('afterend', tree(frameEl(null, k))); },
  insertNode: function (k) { var r = document.createRange(); r.selectNodeContents(slot()); r.insertNode(tree(frameEl(null, k))); },
  insertAdjacentHTML: function (k) { slot().insertAdjacentHTML('beforeend', html(k)); },
  innerHTML: function (k) { slot().innerHTML = html(k); },
  innerHTML_outside: function (k) { var d = document.createElement('div'); d.innerHTML = html(k); box().appendChild(d); },
  outerHTML: function (k) { slot().outerHTML = '<div>' + html(k) + '</div>'; },
  setHTMLUnsafe: function (k) { slot().setHTMLUnsafe(html(k)); },
  template: function (k) { var t = document.createElement('template'); t.innerHTML = html(k); box().appendChild(document.importNode(t.content, true)); },
  template_append: function (k) { var t = document.createElement('template'); t.content.appendChild(tree(frameEl(null, k))); box().appendChild(t.content); },
  domparser: function (k) { var n = new DOMParser().parseFromString('<div>' + html(k) + '</div>', 'text/html').body.firstChild; box().appendChild(document.adoptNode(n)); },
  clone: function (k) { box().appendChild(tree(frameEl(null, k)).cloneNode(true)); },
  moved_outside: function (k) {
    // the frame moved around outside the page (each call is skipped) first
    var d = document.createElement('div'), a = document.createElement('span'), f = frameEl(null, k);
    d.appendChild(a); a.before(document.createElement('b')); a.replaceWith(f);
    f.after(document.createElement('i')); f.insertAdjacentElement('beforebegin', document.createElement('u'));
    var e = document.createElement('div'); e.append(d); e.prepend(document.createElement('hr'));
    box().appendChild(e);
  },
  srcdoc: function (k) { var f = frameEl(null, k); f.srcdoc = '<p>srcdoc</p>'; box().appendChild(tree(f)); }
};
var PATHS = {
  index: function (k) { return window[0]; },
  frames_index: function (k) { return window.frames[0]; },
  frames_name: function (k) { return frames[k.name]; },
  window_name: function (k) { return window[k.name]; },
  by_id: function (k) { return document.getElementById(k.id).contentWindow; },
  content_document: function (k) { return document.getElementById(k.id).contentDocument.defaultView; }
};
function play(R, label, make) {
  clean();
  try { R[label] = make(); } catch (e) { R[label] = 'error ' + e; }
}
window.run = async function (which) {
  var R = {top: sig(window)};
  try {
  if (which === 'ways') {
    Object.keys(WAYS).forEach(function (w) {
      Object.keys(PATHS).forEach(function (p) {
        play(R, w + ' ' + p, function () {
          var k = names(); WAYS[w](k);
          return sig(PATHS[p](k));       // at once, in the same task
        });
      });
    });
  } else if (which === 'nested') {
    play(R, 'nested built outside', function () {
      box().appendChild(outer());
      var cd = window[0].document, d = cd.createElement('div');
      d.appendChild(frameEl(cd, names())); cd.body.appendChild(d);
      return sig(window[0][0]);
    });
    play(R, 'nested with the parent\'s appendChild', function () {
      box().appendChild(outer());
      var cd = window[0].document;
      Node.prototype.appendChild.call(cd.body, tree(frameEl(cd, names())));
      return sig(window[0][0]);
    });
    play(R, 'nested outside, with the parent\'s methods', function () {
      box().appendChild(outer());
      var cd = window[0].document, d = cd.createElement('div');
      Node.prototype.appendChild.call(d, frameEl(cd, names()));
      Element.prototype.append.call(cd.body, d);
      return sig(window[0][0]);
    });
    play(R, 'nested written', function () {
      box().appendChild(outer());
      var cd = window[0].document;
      cd.open(); cd.write('<div>' + html(names()) + '</div>'); cd.close();
      return sig(window[0][0]);
    });
    play(R, 'nested through frames[name]', function () {
      var o = outer(), k = {name: o.name}; box().appendChild(o);
      var inner = names(), cd = frames[k.name].document;
      cd.body.appendChild(tree(frameEl(cd, inner)));
      return sig(frames[k.name][inner.name]);
    });
  } else if (which === 'swaps') {
    var SWAPS = {
      replaceChild: function (old, k) { box().replaceChild(frameEl(null, k), old); },
      replaceWith: function (old, k) { old.replaceWith(frameEl(null, k)); },
      replaceChildren: function (old, k) { box().replaceChildren(frameEl(null, k)); },
      setHTMLUnsafe: function (old, k) { box().setHTMLUnsafe(html(k)); },
      outerHTML: function (old, k) { old.outerHTML = html(k); },
      innerHTML: function (old, k) { box().innerHTML = html(k); },
      out_and_back: function (old, k) { var d = document.createElement('div'); d.appendChild(old); box().appendChild(d); }
    };
    Object.keys(SWAPS).forEach(function (s) {
      play(R, 'swap ' + s, function () {
        var old = frameEl(null, names()); box().appendChild(old);
        var first = sig(window[0]);
        if (first + '' !== R.top + '') return ['first look', first];
        SWAPS[s](old, names());
        return sig(window[0]);
      });
    });
  } else if (which === 'lies') {
    play(R, 'isConnected on the prototype', function () {
      var d = Object.getOwnPropertyDescriptor(Node.prototype, 'isConnected');
      Object.defineProperty(Node.prototype, 'isConnected', {get: function () { return false; }, configurable: true});
      try { box().appendChild(tree(frameEl(null, names()))); return sig(window[0]); }
      finally { Object.defineProperty(Node.prototype, 'isConnected', d); }
    });
    play(R, 'isConnected of the target', function () {
      var b = box();
      Object.defineProperty(b, 'isConnected', {value: false, configurable: true});
      try { b.appendChild(frameEl(null, names())); return sig(window[0]); }
      finally { delete b.isConnected; }
    });
    play(R, 'firstElementChild on the prototype', function () {
      var d = Object.getOwnPropertyDescriptor(Element.prototype, 'firstElementChild');
      Object.defineProperty(Element.prototype, 'firstElementChild', {get: function () { return null; }, configurable: true});
      try { box().appendChild(tree(frameEl(null, names()))); return sig(window[0]); }
      finally { Object.defineProperty(Element.prototype, 'firstElementChild', d); }
    });
    play(R, 'localName on the prototype', function () {
      var d = Object.getOwnPropertyDescriptor(Element.prototype, 'localName');
      Object.defineProperty(Element.prototype, 'localName', {get: function () { return 'div'; }, configurable: true});
      try { box().appendChild(frameEl(null, names())); return sig(window[0]); }
      finally { Object.defineProperty(Element.prototype, 'localName', d); }
    });
    play(R, 'length of the window', function () {
      window.length = 0;
      try { box().appendChild(tree(frameEl(null, names()))); return sig(window[0]); }
      finally { delete window.length; }
    });
  } else if (which === 'shadow') {
    play(R, 'shadow in the page contentWindow', function () {
      var host = box().appendChild(document.createElement('div')), sr = host.attachShadow({mode: 'open'});
      var f = frameEl(null, names()); sr.appendChild(tree(f));
      return sig(f.contentWindow);
    });
    play(R, 'shadow in the page contentDocument', function () {
      var host = box().appendChild(document.createElement('div')), sr = host.attachShadow({mode: 'open'});
      var f = frameEl(null, names()); sr.appendChild(f);
      return sig(f.contentDocument.defaultView);
    });
    play(R, 'shadow host put in later contentWindow', function () {
      var host = document.createElement('div'), sr = host.attachShadow({mode: 'open'});
      var f = frameEl(null, names()); sr.appendChild(tree(f)); box().appendChild(host);
      return window.length ? ['in window[i]', sig(window[0])] : sig(f.contentWindow);
    });
    play(R, 'shadow host put in later contentDocument', function () {
      var host = document.createElement('div'), sr = host.attachShadow({mode: 'open'});
      sr.innerHTML = html(names()); box().appendChild(host);
      return window.length ? ['in window[i]', sig(window[0])] : sig(sr.querySelector('iframe').contentDocument.defaultView);
    });
  } else if (which === 'object') {
    clean();
    var o = document.createElement('object'); o.type = 'text/html'; o.data = '/frame';
    var ol = loaded(o); box().appendChild(o); await ol;
    R.object = sig(window[0]);
    var k = names(); box().appendChild(tree(frameEl(null, k)));
    R['frame after the object'] = sig(frames[k.name]);
    var k2 = names(); box().appendChild(frameEl(null, k2));
    R['second frame by index'] = sig(window[window.length - 1]);
    var holder = document.createElement('div'); box().appendChild(holder);
    var ol2 = loaded(o); holder.appendChild(o);
    for (var i = 0; i < window.length; i++) R['after the move ' + i] = sig(window[i]);
    await ol2;
    for (var j = 0; j < window.length; j++) R['after the move, loaded ' + j] = sig(window[j]);
  }
  } catch (e) { R.error = String(e && e.stack || e); }
  window.result = JSON.stringify(R);
};
</script>paths</body>"""

CASES = ["ways", "nested", "swaps", "lies", "shadow", "object"]


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
    yield "http://127.0.0.1:%d" % srv.server_address[1]
    srv.shutdown()


STEPS = r'''
import json
from PyQt6.QtCore import QUrl

def steps(ike, qapp, out):
    v = ike.windows[0].current_view()
    for case in CASES:
        done = {}
        v.page().loadFinished.connect(lambda ok, done=done: done.setdefault("ok", ok))
        v.load(QUrl(SITE + "/?" + case))
        while "ok" not in done:
            yield 20
        yield 200
        v.page().runJavaScript("run(%r)" % case)
        for _ in range(400):
            res = {}
            v.page().runJavaScript("window.result || ''", 0, lambda r, res=res: res.setdefault("r", r))
            while "r" not in res:
                yield 20
            if res["r"]:
                out[case] = json.loads(res["r"])
                break
            yield 50
'''


@pytest.mark.parametrize("level", ["balanced", "strict"])
def test_every_quick_path_still_protects_the_frame(run_ike, site, level):
    real = run_ike("SITE = %r\nCASES = ['lies']\n" % site + STEPS,
                   settings={"shield_level": "off"}, timeout=120)["lies"]["top"]
    out = run_ike("SITE = %r\nCASES = %r\n" % (site, CASES) + STEPS,
                  settings={"shield_level": level}, timeout=240)
    bad = {}
    for case in CASES:
        r = out.get(case)
        assert r, ("the page did not finish", case)
        assert "error" not in r, (case, r["error"])
        top = r["top"]
        assert top[0] != real[0], ("the canvas is not protected at all", case)
        assert len(r) > 1, ("nothing was played", case)
        bad.update({case + ": " + k: v for k, v in r.items() if k != "top" and v != top})
    assert not bad, json.dumps(bad, indent=1)
    # every way in was played through every way to the window
    assert len([k for k in out["ways"] if k != "top"]) == 22 * 6
