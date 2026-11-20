"""Secrets a page must never read (1.1.18, security audit, finding F3).

- The media commands (mediahook.js, plasma.py) talk through events whose name
  carries a secret. It was the first 96 bits of the fingerprinting key, and a
  page on a media site read it: through a getter put on
  CustomEvent.prototype.detail during the 1-second poll, and through
  window.event inside its own "next" handler. Now the secret is a random value
  of its own, the listener uses only functions taken before the page's
  scripts, and the page's handler runs after the event. "Next" and the poll
  still work.
- The worker prelude (with the site's seed) was given to the page's own Blob:
  a page that replaced Blob read it. Now it never reaches a page function.
"""

import json

MEDIA_PAGE = r"""<title>yt</title><video id=v></video><script>
window.leaks = []; window.nexts = 0;
var d = Object.getOwnPropertyDescriptor(CustomEvent.prototype, 'detail');
Object.defineProperty(CustomEvent.prototype, 'detail', {configurable: true, get: function () {
  if (String(this.type).indexOf('ike-') === 0) leaks.push('detail-getter:' + this.type);
  return d.get.call(this); }});
var call = Function.prototype.call;
Function.prototype.call = function (self) {
  try { if (self && self.type && String(self.type).indexOf('ike-') === 0) leaks.push('call:' + self.type); } catch (e) {}
  return call.apply(this, arguments); };
var send = EventTarget.prototype.dispatchEvent;
EventTarget.prototype.dispatchEvent = function (e) {
  try { if (String(e.type).indexOf('ike-') === 0) leaks.push('dispatch:' + e.type); } catch (x) {}
  return send.apply(this, arguments); };
navigator.mediaSession.setActionHandler('nexttrack', function () {
  window.nexts++;
  if (window.event) leaks.push('window.event:' + window.event.type); });
</script>"""

BLOB_PAGE = r"""<title>p</title><script>
window.seen = [];
var RB = Blob;
window.Blob = function (parts, opts) {
  try { parts.forEach(function (p) { if (typeof p === 'string' && p.indexOf('seed') >= 0) seen.push('blob'); }); } catch (e) {}
  return new RB(parts, opts); };
Blob.prototype = RB.prototype;
var concat = Array.prototype.concat;
Array.prototype.concat = function () {
  try { if (String(this[0]).indexOf('blob:') === 0 || String(this[0]).indexOf('data:') === 0) seen.push('concat:' + this[0]); } catch (e) {}
  return concat.apply(this, arguments); };
var construct = Reflect.construct;
Reflect.construct = function (t, a) {
  try { if (a && String(a[0]).indexOf('seed') >= 0) seen.push('construct'); } catch (e) {}
  return construct.apply(Reflect, arguments); };
var u = URL.createObjectURL(new RB(['postMessage(navigator.hardwareConcurrency)'], {type: 'text/javascript'}));
var w = new Worker(u); w.onmessage = function (e) { window.cores = e.data; };
var dw = new Worker('data:text/javascript,postMessage(navigator.hardwareConcurrency)');
dw.onmessage = function (e) { window.dcores = e.data; };
</script>"""

STEPS = r'''
import json
from PyQt6.QtCore import QUrl

def js(page, code, world=0):
    res = {}
    page.runJavaScript(code, world, lambda r: res.setdefault("r", r))
    while "r" not in res:
        yield 20
    return res["r"]

def steps(ike, qapp, out):
    from ike import plasma
    v = ike.windows[0].current_view()
    page = v.page()
    v.setHtml(%(media)r, QUrl("https://www.youtube.com/watch?v=x"))
    yield 2500
    tok = ike.shields.media_token(page.profile())
    key = ike.shields.profile_keys[id(page.profile())]
    out["token_from_key"] = key[:12] in tok
    # exactly what plasma.py runs from I.K.E.'s isolated world: the poll, then "next"
    out["poll"] = yield from js(page, plasma._MEDIA_JS.replace("__TOKEN__", tok), plasma._WORLD_ID)
    yield from js(page, plasma._ACTION_JS %% (tok, json.dumps("nexttrack")), plasma._WORLD_ID)
    yield 500
    out["media"] = json.loads((yield from js(page, "JSON.stringify([window.leaks, window.nexts])")))
    v.setHtml(%(blob)r, QUrl("https://site-one.example/"))
    yield 2500
    out["blob"] = json.loads((yield from js(page, "JSON.stringify([window.seen, window.cores, window.dcores])")))
    out["cores"] = (yield from js(page, "navigator.hardwareConcurrency"))
'''


def test_pages_cannot_read_the_media_secret_or_the_worker_prelude(run_ike):
    out = run_ike(STEPS % {"media": MEDIA_PAGE, "blob": BLOB_PAGE},
                  settings={"shield_level": "balanced"}, timeout=120)
    assert out["token_from_key"] is False, out            # not derived from the fingerprinting key
    leaks, nexts = out["media"]
    assert leaks == [], leaks                              # no getter, call, dispatch or window.event saw it
    assert nexts == 1, out["media"]                        # "next" from the desktop still works
    assert out["poll"]["next"] is True, out["poll"]        # and the poll still sees the page's "next"
    seen, cores, dcores = out["blob"]
    assert seen == [], seen                                # the prelude reached no page function
    assert cores == out["cores"] and dcores == out["cores"], out   # workers still get the protected value
