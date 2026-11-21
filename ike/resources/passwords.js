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
  function fill(login, force, p) {
    p = p || pwField(false);
    if (!p || (p.value && !force)) return false;
    var u = userFor(p);
    if (u && (force || !u.value)) setValue(u, login.u);
    setValue(p, login.p);
    return true;
  }
  // The channel is this helper's alone (review of 1.1.19, L6): once it is
  // made, the transport's receiver is locked, so a second channel in this
  // world (a list scriptlet, Dark Reader, by a bug) cannot take the answers,
  // and the other helpers get only the calls they use, never the logins
  // (fillRequested) or "captured". (The engine finds the transport by its
  // name to deliver messages: it stays where it is.)
  var transport = qt.webChannelTransport;
  new QWebChannel(transport, function (channel) {
    var ike = channel.objects.ike;
    if (!ike) return;
    var shared = {
      fetchCss: function (id, url) { ike.fetchCss(String(id), String(url)); },
      cssFetched: Object.freeze({connect: function (f) { ike.cssFetched.connect(f); }}),
      adClick: function (x, y) { ike.adClick(+x, +y); },
      adClickEmbedded: function (x, y) { ike.adClickEmbedded(+x, +y); }
    };
    Object.defineProperty(window, '__ikeBridge', {value: Object.freeze(shared)});
    // A saved login is offered when the user clicks (or tabs) into the
    // password field or its user name field: I.K.E. shows its own small menu
    // ("Fill in: name" / "Not now") and only the login the user picks comes
    // to the page. Nothing is filled by itself when the page loads: a script
    // of the page (an advert, a comment) could otherwise make a tiny form and
    // read the password. Only real input counts (isTrusted): a page cannot
    // click or tab for the user, and it never sees the menu.
    var target = null;
    function onUser(e) {
      var t = e.target;
      if (!e.isTrusted || !t || t.tagName !== 'INPUT' || !visible(t) || t.value) return;
      if (e.type === 'keyup' && e.key !== 'Tab') return;
      var p = (t.getAttribute('type') || '').toLowerCase() === 'password' ? t : null;
      if (!p) {
        var form = t.form || document;
        var all = form.querySelectorAll('input[type="password"]');
        for (var i = 0; i < all.length && !p; i++) {
          if (visible(all[i]) && userFor(all[i]) === t) p = all[i];
        }
      }
      if (!p || p.value) return;
      target = p;
      var u = userFor(p);
      var r = t.getBoundingClientRect();
      ike.offerFill(r.left, r.top, r.width, r.height, (u && u.value) || '');
    }
    document.addEventListener('pointerdown', onUser, true);
    document.addEventListener('keyup', onUser, true);
    function capture() {
      var p = pwField(true);
      if (!p) return;
      var u = userFor(p);
      ike.captured(u ? u.value : '', p.value);
    }
    ike.fillRequested.connect(function (json) {
      // the field the user clicked, if it is still on the page
      var p = target && target.isConnected ? target : null;
      target = null;
      try { fill(JSON.parse(json), true, p); } catch (e) {}
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
  });
  ['onmessage', 'send'].forEach(function (k) {
    try {
      Object.defineProperty(transport, k, {value: transport[k], writable: false, configurable: false});
    } catch (e) {}
  });
  // and the names the engine and other code find it by: a replaced transport
  // object (or "qt") would otherwise receive the answers (review 4, N6)
  try {
    Object.defineProperty(qt, 'webChannelTransport', {value: transport, writable: false, configurable: false});
  } catch (e) {}
  try {
    Object.defineProperty(window, 'qt', {value: qt, writable: false, configurable: false});
  } catch (e) {}
})();
