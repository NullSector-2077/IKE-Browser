// I.K.E. dark mode for pages: runs Dark Reader's own engine (resources/darkreader.js,
// MIT licence, https://darkreader.org) in the isolated world of every frame of a
// page that should be dark, as the Dark Reader extension does: with the fix of its
// list for the site, its style-sheet proxy in the page's own world
// (resources/darkreader-proxy.js) and its detector of a site's own dark theme.
//
// The script is installed for the whole profile (a script given to one page at
// the moment it navigates can miss the new page when the engine starts it in
// another process). It does nothing on its own: a small script per dark site
// (webview.py) registers that site's settings in window.__ikeDarkCfg, and only a
// page whose top site is registered is made dark. The engine is loaded only then.
// Placeholders (filled in by darkpages.py): the theme, the common fix and the library.
(function () {
  'use strict';
  if (window.__ikeDark) return;
  window.__ikeDark = true;
  var reg = window.__ikeDarkCfg || (window.__ikeDarkCfg = {});
  var topHost = '';
  try {
    if (window.top === window) {
      topHost = location.hostname || location.protocol;          // "file:" for a page on the disk
    } else if (location.ancestorOrigins && location.ancestorOrigins.length) {
      var top = new URL(location.ancestorOrigins[location.ancestorOrigins.length - 1]);
      topHost = top.hostname || top.protocol;
    }
  } catch (e) {}
  if (!topHost) return;
  if (reg[topHost]) { go(reg[topHost]); return; }
  window.__ikeDarkGo = function (host) {
    if (host === topHost && reg[host]) { window.__ikeDarkGo = null; go(reg[host]); }
  };

  function go(site) {
  var CFG = {theme: __IKE_DR_THEME__, common: __IKE_DR_COMMON__, fix: site.fix, detect: site.detect,
             hints: site.hints, topHost: topHost};
  var DR;
  try {
    var module = { exports: {} }, exports = module.exports;
    (function () {
__IKE_DR_LIB__
    }).call(window);
    DR = module.exports;
  } catch (e) { return; }
  if (!DR || typeof DR.enable !== 'function') return;

  // Style sheets of other sites cannot be read by a page; the browser fetches
  // them instead (top frame only, style sheets only).
  var pending = {}, seq = 0, hooked = false;
  function bridgeReady() {
    // the bridge is set up a moment after the page starts loading
    return new Promise(function (resolve, reject) {
      var tries = 0;
      (function look() {
        var b = window.__ikeBridge;
        if (b && typeof b.fetchCss === 'function' && b.cssFetched) { resolve(b); return; }
        if (window.top !== window || ++tries > 60) { reject(new Error('no bridge')); return; }
        setTimeout(look, 100);
      })();
    });
  }
  function viaBrowser(url) {
    return bridgeReady().then(function (bridge) {
      return new Promise(function (resolve, reject) {
        if (!hooked) {
          hooked = true;
          bridge.cssFetched.connect(function (id, ok, text) {
            var p = pending[id];
            if (!p) return;
            delete pending[id];
            if (ok) p[0](new Response(text, { status: 200, headers: { 'content-type': 'text/css' } }));
            else p[1](new Error('fetch failed'));
          });
        }
        var id = String(++seq);
        pending[id] = [resolve, reject];
        bridge.fetchCss(id, String(url));
        setTimeout(function () {
          if (pending[id]) { delete pending[id]; reject(new Error('timeout')); }
        }, 15000);
      });
    });
  }
  try {
    DR.setFetchMethod(function (url) {
      return window.fetch(url).then(function (r) {
        if (!r.ok) throw new Error('status');
        return r;
      }).catch(function () { return viaBrowser(url); });
    });
  } catch (e) {}

  // Until the engine is running, a plain dark background hides the white flash.
  var early = null;
  function cover() {
    if (early || !document.documentElement) return;
    early = document.createElement('style');
    early.textContent = 'html{background:#181a1b!important}';
    document.documentElement.appendChild(early);
  }
  // The fix of Dark Reader's list for this site (with the common fix), as the
  // extension picks it: a frame of another site gets the common fix only.
  var sameSite = false;
  try { sameSite = window.top === window || (location.hostname || location.protocol) === CFG.topHost; } catch (e) {}
  var fix = (sameSite ? CFG.fix : CFG.common) || null;

  // --- the extension's detector of a site's own dark theme (src/inject/detector.ts) ---
  function parseColor(text) {
    var m = /^rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)(?:\s*[,/]\s*([\d.]+%?))?\s*\)$/.exec(text || '');
    if (!m) return text === 'transparent' ? { r: 0, g: 0, b: 0, a: 0 } : null;
    var a = m[4] === undefined ? 1 : (m[4].slice(-1) === '%' ? parseFloat(m[4]) / 100 : parseFloat(m[4]));
    return { r: +m[1], g: +m[2], b: +m[3], a: a };
  }
  function lightness(c) { return (0.2126 * c.r + 0.7152 * c.g + 0.0722 * c.b) / 255; }
  function hasBuiltInDarkTheme() {
    var rootStyle = getComputedStyle(document.documentElement);
    if (rootStyle.filter.indexOf('invert(1)') >= 0 || rootStyle.colorScheme === 'dark') return true;
    var CELL = 256, ROWS = 4, w = innerWidth, h = innerHeight;
    var stepX = Math.floor(w / Math.min(ROWS, Math.ceil(w / CELL)));
    var stepY = Math.floor(h / Math.min(ROWS, Math.ceil(h / CELL)));
    var seen = new Set();
    for (var y = Math.floor(stepY / 2); y < h; y += stepY) {
      for (var x = Math.floor(stepX / 2); x < w; x += stepX) {
        var el = document.elementFromPoint(x, y);
        if (!el || seen.has(el) || el.tagName.toLowerCase() === 'img') continue;
        seen.add(el);
        var st = el === document.documentElement ? rootStyle : getComputedStyle(el);
        var bg = parseColor(st.backgroundColor);
        if (!bg) return false;
        if (bg.r === 24 && bg.g === 26 && bg.b === 27) return false;
        if (bg.a === 1) {
          if (lightness(bg) > 0.6) return false;
        } else {
          var tc = parseColor(st.color);
          if (!tc || lightness(tc) < 0.4) return false;
        }
      }
    }
    var rootColor = parseColor(rootStyle.backgroundColor);
    if (!rootColor) return false;
    var bodyColor = document.body ? parseColor(getComputedStyle(document.body).backgroundColor) : { r: 0, g: 0, b: 0, a: 0 };
    if (!bodyColor) return false;
    if (rootColor.a === 0 && bodyColor.a === 0) {
      var rt = parseColor(rootStyle.color);
      if (rt) return lightness(rt) > 0.5;
    }
    var rootL = (1 - rootColor.a) + rootColor.a * lightness(rootColor);
    return (1 - bodyColor.a) * rootL + bodyColor.a * lightness(bodyColor) < 0.5;
  }
  function runCheck(callback) {
    var meta = document.querySelector('meta[name="color-scheme"]');
    if (meta) {
      var content = (meta.content || '').toLowerCase();
      if (content === 'dark' || content === 'only dark') { callback(true); return; }
      if (content === 'light' || content === 'only light') { callback(false); return; }
    }
    var root = document.documentElement;
    if (root.classList.contains('dark') || (document.body && document.body.classList.contains('dark')) ||
        (root.dataset.theme || '').toLowerCase() === 'dark') { callback(true); return; }
    var sheets = Array.prototype.filter.call(document.styleSheets, function (s) {
      return s.ownerNode && s.ownerNode.classList && s.ownerNode.classList.contains('darkreader');
    });
    if (Array.isArray(document.adoptedStyleSheets)) {
      document.adoptedStyleSheets.forEach(function (s) {
        try {
          var r = s.cssRules && s.cssRules[0];
          if (r && r.selectorText && r.selectorText.indexOf('#__darkreader') === 0) sheets.push(s);
        } catch (e) {}
      });
    }
    sheets.forEach(function (s) { s.disabled = true; });
    var dark = false;
    try { dark = hasBuiltInDarkTheme(); } catch (e) {}
    sheets.forEach(function (s) { s.disabled = false; });
    callback(dark);
  }
  function hasSomeStyle() {
    if (document.querySelector('meta[name="color-scheme"]')) return true;
    if (document.documentElement.style.backgroundColor || (document.body && document.body.style.backgroundColor)) return true;
    for (var i = 0; i < document.styleSheets.length; i++) {
      var o = document.styleSheets[i].ownerNode;
      if (o && !(o.classList && o.classList.contains('darkreader'))) return true;
    }
    return false;
  }
  function canCheck() {
    var b = document.body;
    if (!(b && b.scrollHeight >= 32 && b.clientHeight >= 32 && b.childElementCount > 0 && hasSomeStyle())) return false;
    for (var i = 0; i < b.children.length; i++) {
      var t = b.children[i].tagName;
      if (t !== 'SCRIPT' && t !== 'STYLE' && t !== 'LINK') return true;
    }
    return false;
  }
  function detectUsingHint(hint, success) {
    var selector = (hint.match || []).join(', ');
    var matchObs = null;
    function check(target) {
      try { if (selector && target.matches(selector)) { if (matchObs) matchObs.disconnect(); success(); return true; } } catch (e) {}
      return false;
    }
    function watch(target) {
      if (check(target)) return;
      matchObs = new MutationObserver(function () { check(target); });
      matchObs.observe(target, { attributes: true });
    }
    var target = hint.target ? document.querySelector(hint.target) : null;
    if (target) { watch(target); return; }
    if (!hint.target) return;
    var targetObs = new MutationObserver(function () {
      var t = document.querySelector(hint.target);
      if (t) { targetObs.disconnect(); watch(t); }
    });
    targetObs.observe(document.documentElement, { childList: true, subtree: true });
  }
  function detect(callback) {
    var hints = CFG.hints || [];
    if (hints.length) {
      var hint = hints[0];
      if (hint.noDarkTheme) { callback(false); return; }
      if (hint.systemTheme && matchMedia('(prefers-color-scheme: dark)').matches) { callback(true); return; }
      detectUsingHint(hint, function () { callback(true); });
      return;
    }
    if (canCheck()) { runCheck(callback); return; }
    function look() {
      if (canCheck()) { stop(); runCheck(callback); }
    }
    var obs = new MutationObserver(look);
    function onReady() {
      if (document.readyState === 'complete') { stop(); runCheck(callback); }
    }
    function stop() { lookAgain = null; obs.disconnect(); document.removeEventListener('readystatechange', onReady); }
    lookAgain = look;
    obs.observe(document.documentElement, { childList: true });
    if (document.readyState !== 'complete') document.addEventListener('readystatechange', onReady);
  }

  // the detector's look at the page, while it waits (see uncover)
  var lookAgain = null;
  // The plain background goes 0.4 s after the engine started. Taking an element
  // out of <html> next to <head> and <body> makes the browser style the whole
  // page again when the page has rules such as "* + *" or "x ~ y > *" (it
  // cannot tell which of the elements after it are affected): 6,000 elements
  // on a large page. So the background waits inside <head>, as its first style
  // (the first of the page, as it was before <head>: the same rule wins), and
  // is taken out of there, where nothing after it is drawn.
  function uncover(s) {
    try {
      if (s.parentNode === document.documentElement && document.head) {
        document.head.insertBefore(s, document.head.firstChild);
      }
    } catch (e) {}
    setTimeout(function () {
      var there = !!s.parentNode;
      try { s.remove(); } catch (e) {}
      // the detector looked at the page whenever <html> lost or got a child,
      // so also when the background went: it still does
      if (there) Promise.resolve().then(function () { if (lookAgain) lookAgain(); });
    }, 400);
  }
  function start() {
    try { DR.enable(CFG.theme, fix); } catch (e) {}
    if (early) {
      var s = early;
      early = null;
      uncover(s);
    }
    // a site with a dark theme of its own is left as it is (only the top frame,
    // or a frame the hints name, as in the extension)
    if (CFG.detect && (window.top === window || (CFG.hints || []).some(function (h) { return h.iframe; }))) {
      detect(function (dark) {
        if (dark) { try { DR.disable(); } catch (e) {} }
      });
    }
  }
  if (document.head) { start(); return; }
  cover();
  new MutationObserver(function (_m, obs) {
    cover();
    if (document.head) { obs.disconnect(); start(); }
  }).observe(document, { childList: true, subtree: true });
  }
})();
