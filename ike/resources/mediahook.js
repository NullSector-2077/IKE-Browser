// I.K.E. media commands for the desktop (Plasma's media controls, the media
// keys). Runs in the page's main world before any page script, in every frame,
// only when "Media controls" is on (Settings -> General), and changes a frame
// only on the media sites of the setting "media_sites" (1.1.12): elsewhere the
// page is left exactly as the engine made it, so anti-abuse checks (Google's
// sign-in and AI Studio, banks, payments) find nothing changed.
//
// A site that offers "next" and "previous" declares them with
// navigator.mediaSession.setActionHandler(). The call works exactly as before;
// I.K.E. also keeps the two handlers, so the desktop can use them. The replaced
// function looks native (as in fingerprint.js). I.K.E.'s own isolated world
// asks and triggers through events whose name carries a per-profile secret, so
// a page can neither see nor send them. __IKE_MEDIA_TOKEN__ is replaced at
// injection time.
(function () {
  'use strict';
  var TOKEN = '__IKE_MEDIA_TOKEN__';
  var SITES = __IKE_MEDIA_SITES__;
  var here = String(location.hostname || '').toLowerCase();
  var listed = SITES.some(function (s) {
    return here === s || here.slice(-(s.length + 1)) === '.' + s;
  });
  if (!listed) return;
  var MS = window.MediaSession && window.MediaSession.prototype;
  if (!MS || typeof MS.setActionHandler !== 'function') return;
  var origToString = Function.prototype.toString;
  var natives = new WeakMap();
  var handlers = Object.create(null);

  var orig = MS.setActionHandler;
  var replaced = ({ setActionHandler(action, handler) {
    var r = orig.apply(this, arguments);         // fails exactly as the original
    if (action === 'nexttrack' || action === 'previoustrack') {
      handlers[action] = typeof handler === 'function' ? handler : null;
    }
    return r;
  } }).setActionHandler;
  try { Object.defineProperty(replaced, 'length', { value: orig.length, configurable: true }); } catch (e) {}
  natives.set(replaced, origToString.call(orig));
  var d = Object.getOwnPropertyDescriptor(MS, 'setActionHandler');
  d.value = replaced;
  try { Object.defineProperty(MS, 'setActionHandler', d); } catch (e) { return; }

  var toStr = ({ toString() {
    var s = natives.get(this);
    return s !== undefined ? s : origToString.call(this);
  } }).toString;
  try { Object.defineProperty(toStr, 'length', { value: origToString.length, configurable: true }); } catch (e) {}
  natives.set(toStr, origToString.call(origToString));
  var t = Object.getOwnPropertyDescriptor(Function.prototype, 'toString');
  t.value = toStr;
  try { Object.defineProperty(Function.prototype, 'toString', t); } catch (e) {}

  var add = EventTarget.prototype.addEventListener;
  var send = EventTarget.prototype.dispatchEvent;
  var Ev = window.CustomEvent;
  add.call(window, 'ike-media-' + TOKEN, function (e) {
    var cmd = e.detail;
    if (cmd === 'query') {
      var a = (handlers.nexttrack ? 'n' : '') + (handlers.previoustrack ? 'p' : '');
      send.call(window, new Ev('ike-media-answer-' + TOKEN, { detail: a }));
      return;
    }
    var h = (cmd === 'nexttrack' || cmd === 'previoustrack') && handlers[cmd];
    if (h) {
      try { h.call(navigator.mediaSession, { action: cmd }); } catch (err) {}
    }
  });
})();
