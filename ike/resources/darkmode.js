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
  if (reg[topHost]) { whenShown(reg[topHost]); return; }
  window.__ikeDarkGo = function (host) {
    if (host === topHost && reg[host]) { window.__ikeDarkGo = null; whenShown(reg[host]); }
  };

  // A frame that is not shown (display:none, or a frame of a pixel or two, as
  // the frames of trackers and advertisers are) has nothing to make dark:
  // Dark Reader starts there only when the frame gets a size. The browser
  // tells a frame its new size before it draws it, so a frame shown later is
  // dark from its first picture, as before. This saves Dark Reader's whole
  // start (about 30 ms of the page's processor time) in each hidden frame.
  function shown() {
    return window.top === window || (innerWidth > 2 && innerHeight > 2);
  }
  function whenShown(site) {
    if (shown()) { go(site); return; }
    addEventListener('resize', function onResize() {
      if (!shown()) return;
      removeEventListener('resize', onResize);
      go(site);
    });
  }

  function go(site) {
  // the colours: the site's own when it has them (1.1.25, the dark mode panel), else every site's
  var CFG = {theme: site.theme || __IKE_DR_THEME__, common: __IKE_DR_COMMON__, fix: site.fix,
             detect: site.detect, hints: site.hints, topHost: topHost};
  var styles = strictPolicyStyles();
  var DR;
  try {
    var module = { exports: {} }, exports = module.exports;
    (function () {
__IKE_DR_LIB__
    }).call(window);
    DR = module.exports;
  } catch (e) { return; }
  if (!DR || typeof DR.enable !== 'function') return;

  // --- styles under a strict Content-Security-Policy (1.1.26) ---
  // A page whose policy allows style sheets from its own site only ("default-src
  // 'self'", "style-src 'self'": archlinux.org, for one) blocks every <style>
  // element added to it, Dark Reader's too: the page stayed light. A <style>
  // made in this isolated world whose sheet the policy refused is given to the
  // page as a constructed style sheet instead (adoptedStyleSheets, which the
  // policy does not cover, as the CSSOM), with the same text and rules, in the
  // order of the <style> elements, after the page's own sheets. Only the
  // <style> elements made here (by Dark Reader or by this script) are copied:
  // the page's own inline styles stay blocked, its policy is not touched. On a
  // page without such a policy nothing changes: every <style> has its sheet.
  // Dark Reader's code is not changed: the copy works on the DOM it uses, so
  // it survives its updates. Dark Reader does not see the copies among the
  // page's constructed sheets (it would darken them again).
  function strictPolicyStyles() {
    var none = { sheets: function () { return []; } };
    var docDesc = Object.getOwnPropertyDescriptor(Document.prototype, 'adoptedStyleSheets');
    var textDesc = Object.getOwnPropertyDescriptor(Node.prototype, 'textContent');
    if (!docDesc || !docDesc.get || !docDesc.set || !textDesc || typeof CSSStyleSheet !== 'function') return none;
    var srDesc = window.ShadowRoot && Object.getOwnPropertyDescriptor(ShadowRoot.prototype, 'adoptedStyleSheets');
    var kinds = [window.HTMLStyleElement, window.SVGStyleElement].filter(function (k) {
      return k && Object.getOwnPropertyDescriptor(k.prototype, 'sheet');
    });
    var sheetGet = kinds.map(function (k) { return Object.getOwnPropertyDescriptor(k.prototype, 'sheet').get; });
    var own = new WeakSet();          // the <style> elements made in this world
    var mirrors = new Map();          // <style> -> {sheet, text}
    var copies = new WeakSet();       // every copy ever made
    var placed = new Map();           // root (document or shadow root) -> its copies, in order
    var due = false;
    var watcher = new MutationObserver(function () { refresh(); });

    function adoptedDesc(root) { return root instanceof Document ? docDesc : srDesc; }
    function kindOf(el) {
      for (var i = 0; i < kinds.length; i++) if (el instanceof kinds[i]) return i;
      return -1;
    }
    function nativeSheet(el, k) { try { return sheetGet[k].call(el); } catch (e) { return null; } }
    function refused(el) {
      var k = kindOf(el);
      return k >= 0 && own.has(el) && el.isConnected && nativeSheet(el, k) === null &&
        (!el.type || /^\s*text\/css\s*$/i.test(el.type));
    }
    function setText(m, text) {
      m.text = text;
      try { m.sheet.replaceSync(text); } catch (e) {}
    }
    function mirror(el) {
      var m = mirrors.get(el);
      if (!m) {
        var sheet;
        try { sheet = new CSSStyleSheet({ media: el.media || '' }); } catch (e) { sheet = new CSSStyleSheet(); }
        m = { sheet: sheet, text: null };
        mirrors.set(el, m);
        copies.add(sheet);
        watcher.observe(el, { childList: true, characterData: true, subtree: true });
      }
      if (el.parentNode) watcher.observe(el.parentNode, { childList: true });
      var text = textDesc.get.call(el);
      if (text !== m.text) setText(m, text);
      schedule();
      return m;
    }
    function check(node) {
      if (!node || node.nodeType !== 1 && node.nodeType !== 11) return;
      if (kindOf(node) >= 0) { if (refused(node)) mirror(node); return; }
      if (!node.firstElementChild) return;
      var found = node.querySelectorAll('style');
      for (var i = 0; i < found.length; i++) if (refused(found[i])) mirror(found[i]);
    }
    function schedule() {
      if (due) return;
      due = true;
      Promise.resolve().then(place);
    }
    function refresh() {
      mirrors.forEach(function (m, el) {
        var text = textDesc.get.call(el);
        if (text !== m.text) setText(m, text);
      });
      schedule();
    }
    // the copies of each root, in the order of their <style> elements, after the page's own sheets
    function place() {
      due = false;
      var byRoot = new Map();
      mirrors.forEach(function (m, el) {
        if (!el.isConnected) { mirrors.delete(el); return; }
        var root = el.getRootNode();
        if (!adoptedDesc(root)) return;
        if (!byRoot.has(root)) byRoot.set(root, []);
        byRoot.get(root).push(el);
      });
      placed.forEach(function (_s, root) { if (!byRoot.has(root)) byRoot.set(root, []); });
      byRoot.forEach(function (els, root) {
        els.sort(function (a, b) {
          return a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1;
        });
        var ours = els.map(function (el) { return mirrors.get(el).sheet; });
        var desc = adoptedDesc(root);
        var now = Array.prototype.slice.call(desc.get.call(root));
        var want = now.filter(function (s) { return !copies.has(s); }).concat(ours);
        if (want.length !== now.length || want.some(function (s, i) { return s !== now[i]; })) {
          try { desc.set.call(root, want); } catch (e) {}
        }
        if (ours.length) {
          if (!placed.has(root)) {
            // the page set its own constructed sheets (Dark Reader's proxy tells): ours go back after them
            try { root.addEventListener('__darkreader__adoptedStyleSheetsChange', schedule); } catch (e) {}
          }
          placed.set(root, ours);
        } else {
          placed.delete(root);
          try { root.removeEventListener('__darkreader__adoptedStyleSheetsChange', schedule); } catch (e) {}
        }
      });
    }

    // the <style> elements made here
    var create = Document.prototype.createElement, createNS = Document.prototype.createElementNS;
    Document.prototype.createElement = function () {
      var el = create.apply(this, arguments);
      if (kindOf(el) >= 0) own.add(el);
      return el;
    };
    Document.prototype.createElementNS = function () {
      var el = createNS.apply(this, arguments);
      if (kindOf(el) >= 0) own.add(el);
      return el;
    };
    // their sheet: the copy when the policy refused it
    kinds.forEach(function (k, i) {
      Object.defineProperty(k.prototype, 'sheet', {
        configurable: true, enumerable: true,
        get: function () {
          var s = nativeSheet(this, i);
          if (s || !refused(this)) return s;
          return mirror(this).sheet;
        }
      });
      // a new text makes a new sheet, as for a <style> of the page
      Object.defineProperty(k.prototype, 'textContent', {
        configurable: true, enumerable: true,
        get: function () { return textDesc.get.call(this); },
        set: function (v) {
          textDesc.set.call(this, v);
          var m = mirrors.get(this);
          if (m) setText(m, textDesc.get.call(this));
          else if (refused(this)) mirror(this);
        }
      });
    });
    // a <style> put into the page, or taken out of it, by this world
    function after(proto, name, nodes) {
      var f = proto && proto[name];
      if (typeof f !== 'function') return;
      proto[name] = function () {
        var r = f.apply(this, arguments);
        if (nodes) for (var i = 0; i < arguments.length; i++) check(arguments[i]);
        if (mirrors.size) schedule();
        return r;
      };
    }
    after(Node.prototype, 'insertBefore', true);
    after(Node.prototype, 'appendChild', true);
    after(Node.prototype, 'replaceChild', true);
    after(Node.prototype, 'removeChild', false);
    ['append', 'prepend', 'before', 'after', 'replaceWith'].forEach(function (n) {
      after(Element.prototype, n, true);
    });
    after(Element.prototype, 'remove', false);
    after(window.DocumentFragment && DocumentFragment.prototype, 'append', true);
    after(window.DocumentFragment && DocumentFragment.prototype, 'prepend', true);
    // Dark Reader looks at the page's constructed sheets: the copies are not among them
    [[Document.prototype, docDesc], [window.ShadowRoot && ShadowRoot.prototype, srDesc]].forEach(function (pd) {
      var proto = pd[0], desc = pd[1];
      if (!proto || !desc || !desc.get || !desc.set) return;
      Object.defineProperty(proto, 'adoptedStyleSheets', {
        configurable: true, enumerable: desc.enumerable,
        get: function () {
          var list = desc.get.call(this);
          if (!placed.has(this)) return list;
          return Array.prototype.filter.call(list, function (s) { return !copies.has(s); });
        },
        set: function (v) {
          var ours = placed.get(this);
          if (!ours || !v) { desc.set.call(this, v); return; }
          desc.set.call(this, Array.prototype.filter.call(v, function (s) { return !copies.has(s); }).concat(ours));
        }
      });
    });
    return { sheets: function () {
      var all = [];
      placed.forEach(function (s) { all = all.concat(s); });
      return all;
    } };
  }

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
    // as an image, not a colour: when the colour of <html> changes the browser
    // styles the whole page again, and taking the cover away would cost that
    early.textContent = 'html{background-image:linear-gradient(#181a1b,#181a1b)!important;' +
      'background-repeat:repeat!important;background-size:auto!important;background-position:0 0!important;' +
      'background-attachment:scroll!important;background-origin:padding-box!important;' +
      'background-clip:border-box!important;background-blend-mode:normal!important}';
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
    // and the copies of Dark Reader's styles under a strict policy
    sheets = sheets.concat(styles.sheets());
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
    var obs = new MutationObserver(function () {
      if (canCheck()) { stop(); runCheck(callback); }
    });
    function onReady() {
      if (document.readyState === 'complete') { stop(); runCheck(callback); }
    }
    function stop() { obs.disconnect(); document.removeEventListener('readystatechange', onReady); }
    obs.observe(document.documentElement, { childList: true });
    if (document.readyState !== 'complete') document.addEventListener('readystatechange', onReady);
  }

  function start() {
    // the cover goes into <head>, first: taken away from there, only <head>
    // can be styled again (as the first child of <html>, with <head> and
    // <body> after it, a page with "~" rules was styled again as a whole)
    if (early && document.head && early.parentNode !== document.head) {
      try { document.head.insertBefore(early, document.head.firstChild); } catch (e) {}
    }
    try { DR.enable(drTheme(CFG.theme), fix); running = true; } catch (e) {}
    hideBars(running && CFG.theme.scrollbarColor === 'hidden');
    if (early) {
      var s = early;
      early = null;
      setTimeout(function () { try { s.remove(); } catch (e) {} }, 400);
    }
    // a site with a dark theme of its own is left as it is (only the top frame,
    // or a frame the hints name, as in the extension)
    if (CFG.detect && (window.top === window || (CFG.hints || []).some(function (h) { return h.iframe; }))) {
      detect(function (dark) {
        if (dark) { running = false; hideBars(false); try { DR.disable(); } catch (e) {} }
      });
    }
  }

  // --- the colours of the dark mode panel (1.1.25) ---
  // "hidden" scroll bars are I.K.E.'s: Dark Reader leaves them alone, a style hides them
  var running = false, bars = null;
  function drTheme(t) {
    var o = {};
    for (var k in t) { if (Object.prototype.hasOwnProperty.call(t, k)) o[k] = t[k]; }
    if (o.scrollbarColor === 'hidden') o.scrollbarColor = '';
    return o;
  }
  function hideBars(on) {
    if (!on) {
      if (bars) { try { bars.remove(); } catch (e) {} bars = null; }
      return;
    }
    if (bars && bars.isConnected) return;
    var root = document.head || document.documentElement;
    if (!root) return;
    bars = document.createElement('style');
    bars.className = 'darkreader darkreader--ike-bars';
    bars.textContent = '*{scrollbar-width:none!important}';
    root.appendChild(bars);
  }
  // Called by the browser in this isolated world when the colours change (the page
  // cannot reach it): the page takes them at once, without being loaded again. The
  // colours were checked by the browser; a page that is not dark stays as it is.
  window.__ikeDarkTheme = function (theme) {
    if (!theme || typeof theme !== 'object') return false;
    CFG.theme = theme;
    if (!running) return false;
    try { DR.enable(drTheme(theme), fix); } catch (e) { return false; }
    hideBars(theme.scrollbarColor === 'hidden');
    return true;
  };
  if (document.head) { start(); return; }
  cover();
  new MutationObserver(function (_m, obs) {
    cover();
    if (document.head) { obs.disconnect(); start(); }
  }).observe(document, { childList: true, subtree: true });
  }
})();
