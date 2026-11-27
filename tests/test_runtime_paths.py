"""The quicker ways of 1.1.23 in fingerprint.js give pages exactly what the
longer ways gave (Speedometer study of 1.1.23).

1. The frame guard does not search the HTML written through innerHTML /
   outerHTML when the window has no frame, and does not look at a moved node
   when the window had none before the call. Every way a frame can then come
   in (written HTML, a subtree with a frame inside, a frame added after one
   was taken away without the guard seeing it, a node moved while the page
   has frames) must still give a frame that answers as the page does.
   Frames are read through window[i], never through contentWindow.
2. At the global level Maximum the engine already speaks en-US, so a call
   that asks for no language is handed on as it is. Whatever a page asks
   (nothing, an empty list, a language the engine does not have), dates,
   numbers, sorting and the Intl objects must answer exactly as with
   'en-US' written by the page, which is what the protection gave before;
   the same when only one site is at Maximum and the engine speaks the
   system's language.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

FRAMES = r"""<!doctype html><title>paths</title><body><div id=box></div><script>
function hash(s) { var h = 2166136261; for (var i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return (h >>> 0).toString(16); }
function sig(win) {
  try {
    var doc = win.document, c = doc.createElement('canvas'); c.width = 200; c.height = 40;
    var x = c.getContext('2d');
    x.textBaseline = 'top'; x.font = '16px sans-serif'; x.fillStyle = '#f60'; x.fillRect(5, 5, 100, 20);
    x.fillStyle = '#069'; x.fillText('I.K.E. paths', 2, 10);
    return [/* the pixels read (1.1.27: every export varies) */ hash(x.getImageData(0, 0, 200, 40).data.join()), win.navigator.hardwareConcurrency];
  } catch (e) { return 'error ' + e; }
}
function box() { return document.getElementById('box'); }
function list(n) { var h = ''; for (var i = 0; i < n; i++) h += '<li><span>item ' + i + '</span><button></button></li>'; return h; }
window.run = function (which) {
  var R = {top: sig(window)}, b = box();
  if (which === 'inner') {
    // big lists written again and again, then a frame in the same way
    for (var i = 0; i < 20; i++) b.innerHTML = '<ul>' + list(50) + '</ul>';
    b.innerHTML = '<ul>' + list(5) + '</ul><iframe></iframe>';
    R.frame = sig(window[0]);
  } else if (which === 'outer') {
    var p = document.createElement('p'); b.appendChild(p);
    p.outerHTML = '<section><iframe></iframe></section>';
    R.frame = sig(window[0]);
  } else if (which === 'adjacent') {
    b.insertAdjacentHTML('beforeend', '<div><iframe></iframe></div>');
    R.frame = sig(window[0]);
  } else if (which === 'subtree') {
    // a subtree built outside the page, with a frame deep inside
    var d = document.createElement('div'); d.innerHTML = '<ul><li><p><iframe></iframe></p></li></ul>';
    for (var j = 0; j < 30; j++) b.appendChild(document.createElement('li')).appendChild(document.createElement('b'));
    b.appendChild(d);
    R.frame = sig(window[0]);
  } else if (which === 'moved_in_page') {
    // nodes of the page moved around while there is no frame, then a frame
    var a = b.appendChild(document.createElement('div')), c = b.appendChild(document.createElement('div'));
    a.appendChild(document.createElement('span'));
    for (var k = 0; k < 20; k++) { c.appendChild(a); b.insertBefore(a, c); }
    c.appendChild(document.createElement('iframe'));
    R.frame = sig(window[0]);
  } else if (which === 'removed_then_added') {
    // a frame taken away without the guard (removeChild is not hooked),
    // a node moved while the window has none, then frames come back
    var f = b.appendChild(document.createElement('iframe'));
    R.first = sig(window[0]);
    b.removeChild(f);
    var m = b.appendChild(document.createElement('div')); m.appendChild(document.createElement('i'));
    b.appendChild(m);
    b.appendChild(document.createElement('iframe'));
    R.second = sig(window[0]);
    b.removeChild(b.lastChild);
    b.innerHTML = '<p>text</p>';
    b.innerHTML = '<iframe></iframe>';
    R.third = sig(window[0]);
  } else if (which === 'moved_with_frames') {
    // the window has a frame: a subtree with another frame, already in the
    // page, is moved (its frame gets a new window)
    b.appendChild(document.createElement('iframe'));
    var holder = b.appendChild(document.createElement('div'));
    holder.appendChild(document.createElement('span')).appendChild(document.createElement('iframe'));
    var dest = b.appendChild(document.createElement('section'));
    dest.appendChild(holder);
    R.first = sig(window[0]);
    R.moved = sig(window[1]);
    dest.insertBefore(holder, null);
    R.moved_again = sig(window[window.length - 1]);
  } else if (which === 'shadow') {
    var host = b.appendChild(document.createElement('div')), sr = host.attachShadow({mode: 'open'});
    sr.innerHTML = '<iframe></iframe>';
    R.frame = sig(sr.querySelector('iframe').contentWindow);
    b.innerHTML += '<iframe></iframe>';
    R.after_shadow = sig(window[window.length - 1]);
  }
  return JSON.stringify(R);
};
</script></body>"""

CASES = ["inner", "outer", "adjacent", "subtree", "moved_in_page", "removed_then_added", "moved_with_frames",
         "shadow"]

LANGS = r"""<!doctype html><title>langs</title><script>
window.run = function () {
  var R = {}, d = new Date(Date.UTC(2026, 10, 22, 21, 5, 7)), n = 1234567.891, utc = {timeZone: 'UTC'};
  // a: the language part of the call: nothing at all, undefined written, an
  // empty list, languages the engine does not have; 'en-US' written is the
  // answer the protection gave before for all of them
  function same(name, f) {
    var asks = [[], [undefined], [[]], [['tlh']], [['zz-ZZ']]], got = [], want;
    for (var i = 0; i < asks.length; i++) { try { got.push(f(asks[i])); } catch (e) { got.push('error ' + e.name); } }
    try { want = f(['en-US']); } catch (e) { want = 'error ' + e.name; }
    R[name] = {want: want, got: got};
  }
  function withOpts(a, o) { return (a.length ? a : [undefined]).concat([o]); }
  same('date', function (a) { return d.toLocaleString.apply(d, withOpts(a, utc)); });
  same('date_only', function (a) { return d.toLocaleDateString.apply(d, withOpts(a, utc)); });
  same('time', function (a) { return d.toLocaleTimeString.apply(d, withOpts(a, {timeZone: 'UTC', hour12: false})); });
  same('number', function (a) { return n.toLocaleString.apply(n, a); });
  same('number_opts', function (a) { return n.toLocaleString.apply(n, withOpts(a, {style: 'currency', currency: 'EUR'})); });
  same('bigint', function (a) { var b = 12345678901234567890n; return b.toLocaleString.apply(b, a); });
  same('compare', function (a) {
    var words = ['b', 'a', 'C', 'ä', 'A', 'z', 'é', 'e', '10', '9'];
    return words.slice().sort(function (x, y) { return x.localeCompare.apply(x, [y].concat(a)); }).join(',');
  });
  same('compare_opts', function (a) {
    return ['a', 'A', 'á'].map(function (x) { return 'a'.localeCompare.apply('a', [x].concat(withOpts(a, {sensitivity: 'base'}))); }).join(',');
  });
  same('upper', function (a) { var t = 'iı straße'; return t.toLocaleUpperCase.apply(t, a); });
  same('lower', function (a) { var t = 'Iİ SS'; return t.toLocaleLowerCase.apply(t, a); });
  ['DateTimeFormat', 'NumberFormat', 'Collator', 'PluralRules', 'RelativeTimeFormat', 'ListFormat',
   'Segmenter', 'DurationFormat'].forEach(function (k) {
    if (!Intl[k]) return;
    same('new ' + k, function (a) { return JSON.stringify(Reflect.construct(Intl[k], a).resolvedOptions()); });
  });
  same('call DateTimeFormat', function (a) { return Intl.DateTimeFormat.apply(null, withOpts(a, utc)).format(d); });
  same('NumberFormat format', function (a) { return Reflect.construct(Intl.NumberFormat, withOpts(a, {maximumFractionDigits: 1})).format(n); });
  same('PluralRules select', function (a) {
    var p = Reflect.construct(Intl.PluralRules, withOpts(a, {type: 'ordinal'}));
    return [0, 1, 2, 3].map(function (x) { return p.select(x); }).join(',');
  });
  same('DisplayNames', function (a) { return Reflect.construct(Intl.DisplayNames, withOpts(a, {type: 'language'})).of('de'); });
  R.nav = navigator.language;
  return JSON.stringify(R);
};
</script>langs"""


@pytest.fixture
def site():
    pages = {"/frames": FRAMES.encode(), "/langs": LANGS.encode()}

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            body = pages.get(self.path.split("?")[0], b"<!doctype html><p>frame</p>")
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
    for name, url, call in RUNS:
        done = {}
        v.page().loadFinished.connect(lambda ok, done=done: done.setdefault("ok", ok))
        v.load(QUrl(url))
        while "ok" not in done:
            yield 20
        yield 200
        res = {}
        v.page().runJavaScript(call, 0, lambda r, res=res: res.setdefault("r", r))
        while "r" not in res:
            yield 20
        out[name] = json.loads(res["r"]) if res["r"] else None
'''

FLAGS = "--no-sandbox --enable-unsafe-swiftshader --use-angle=swiftshader --ignore-gpu-blocklist"


@pytest.mark.parametrize("level", ["balanced", "strict"])
def test_frames_are_protected_on_the_quick_paths(run_ike, site, level):
    runs = [(c, "%s/frames?%s" % (site, c), "run(%r)" % c) for c in CASES]
    real = run_ike("RUNS = %r\n" % runs[:1] + STEPS, settings={"shield_level": "off"},
                   env={"QTWEBENGINE_CHROMIUM_FLAGS": FLAGS}, timeout=120)["inner"]["top"]
    out = run_ike("RUNS = %r\n" % runs + STEPS, settings={"shield_level": level},
                  env={"QTWEBENGINE_CHROMIUM_FLAGS": FLAGS}, timeout=180)
    for case in CASES:
        r = out.get(case)
        assert r, ("the page did not answer", case)
        top = r["top"]
        assert top[0] != real[0], ("the canvas is not protected at all", case)
        wrong = {k: v for k, v in r.items() if v != top}
        assert not wrong, ("frames that do not answer as the page does", case, top, json.dumps(wrong))


def _langs_same(r):
    assert r, "the page did not answer"
    assert r["nav"] == "en-US"
    wrong = {k: v for k, v in r.items() if k != "nav" and any(g != v["want"] for g in v["got"])}
    assert not wrong, ("answers that differ from en-US", json.dumps(wrong, ensure_ascii=False))
    # the answers are en-US ones, not the system's
    assert r["number"]["want"] == "1,234,567.891"
    assert json.loads(r["new Collator"]["want"])["locale"] == "en-US"
    assert r["DisplayNames"]["want"] == "German"


def test_maximum_answers_en_us_whatever_the_page_asks(run_ike, site):
    # the global level Maximum: the engine itself runs in en-US
    runs = [("langs", site + "/langs", "run()")]
    out = run_ike("RUNS = %r\n" % runs + STEPS, settings={"shield_level": "maximum"}, timeout=120)
    _langs_same(out["langs"])


def test_one_site_at_maximum_answers_en_us_too(run_ike, site):
    # only this site at Maximum: the engine keeps the system's language, the
    # rewrite does the work (the system's language here is not en-US)
    runs = [("langs", site + "/langs", "run()")]
    out = run_ike("RUNS = %r\n" % runs + STEPS,
                  settings={"shield_level": "balanced", "site_levels": {"127.0.0.1": "maximum"}},
                  env={"LANG": "de_DE.UTF-8", "LANGUAGE": "de"}, timeout=120)
    _langs_same(out["langs"])
