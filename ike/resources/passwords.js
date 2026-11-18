// I.K.E. page helper (isolated world, top frame only): logins, and the bridge
// used by the video-ad fallback. Talks to the browser
// through QWebChannel; page scripts cannot see this code or the channel.
(function () {
  'use strict';
  if (window.top !== window || typeof QWebChannel === 'undefined' ||
      typeof qt === 'undefined' || !qt.webChannelTransport) return;
  function visible(el) {
    var r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  }
  function pwField(needValue) {
    var all = document.querySelectorAll('input[type="password"]');
    for (var i = 0; i < all.length; i++) {
      if (visible(all[i]) && (!needValue || all[i].value)) return all[i];
    }
    return null;
  }
  function userFor(p) {
    var scope = p.form || document;
    var inputs = scope.querySelectorAll('input');
    var best = null;
    for (var i = 0; i < inputs.length; i++) {
      var el = inputs[i];
      if (el === p) break;
      var t = (el.getAttribute('type') || 'text').toLowerCase();
      if ((t === 'text' || t === 'email' || t === 'tel') && visible(el)) best = el;
    }
    return best;
  }
  function setValue(el, value) {
    if (!el) return;
    var proto = Object.getPrototypeOf(el);
    var d = Object.getOwnPropertyDescriptor(proto, 'value');
    if (d && d.set) d.set.call(el, value); else el.value = value;
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
  }
  function fill(login, force) {
    var p = pwField(false);
    if (!p || (p.value && !force)) return false;
    var u = userFor(p);
    if (u && (force || !u.value)) setValue(u, login.u);
    setValue(p, login.p);
    return true;
  }
  new QWebChannel(qt.webChannelTransport, function (channel) {
    var ike = channel.objects.ike;
    if (!ike) return;
    window.__ikeBridge = ike;      // shared with the other isolated-world helpers
    var filled = false;
    function tryFill() {
      if (filled || !pwField(false)) return;
      ike.logins(function (json) {
        var list = [];
        try { list = JSON.parse(json || '[]'); } catch (e) {}
        if (list.length && fill(list[0], false)) filled = true;
      });
    }
    function capture() {
      var p = pwField(true);
      if (!p) return;
      var u = userFor(p);
      ike.captured(u ? u.value : '', p.value);
    }
    ike.fillRequested.connect(function (json) {
      try { fill(JSON.parse(json), true); } catch (e) {}
    });
    document.addEventListener('submit', capture, true);
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && e.target && e.target.tagName === 'INPUT') capture();
    }, true);
    document.addEventListener('click', function (e) {
      var t = e.target && e.target.closest ?
        e.target.closest('button, input[type="submit"], [role="button"]') : null;
      if (t) capture();
    }, true);
    tryFill();
    // a login form that appears later (sites built while they run); once a
    // login is filled in, the page's changes are no longer watched (1.1.13):
    // on a busy page every change would otherwise be recorded for nothing
    var pending = false;
    var watcher = new MutationObserver(function () {
      if (filled) { watcher.disconnect(); return; }
      if (pending) return;
      pending = true;
      setTimeout(function () {
        pending = false;
        tryFill();
        if (filled) watcher.disconnect();
      }, 600);
    });
    watcher.observe(document.documentElement, { childList: true, subtree: true });
  });
})();
