// I.K.E. Dark Engine (EXPERIMENT, off by default; loaded by ike/darkengine.py). I.K.E.'s own
// dark mode for pages: one pass over the page's style sheets and inline styles,
// one generated override style sheet per source sheet, then only the nodes and
// sheets added later, in batches. No re-analysis of the whole page.
// The colour curves were measured on Dark Reader's output (black-box swatch
// pages, tests/dark_engine/), its per-site fixes come from its lists (MIT,
// resources/darkreader-data.json); no Dark Reader code is used.
// Runs in an isolated world at document creation. Placeholders: __IKE_DE_COMMON__.
(function () {
  'use strict';
  if (window.__ikeDE) return;
  window.__ikeDE = true;
  var cfgs = window.__ikeDECfg || {};
  var fix = cfgs[location.hostname] || __IKE_DE_COMMON__;

  // --- colours ---------------------------------------------------------------
  var BG = [200, 0.06, 0.1], FG = [36, 0.098, 0.9];       // hsl poles: #181a1b, #e8e6e3
  var ctx = new OffscreenCanvas(1, 1).getContext('2d');
  var cache = new Map();
  function parse(v) {                       // -> [r, g, b, a] or null
    var c = cache.get(v);
    if (c !== undefined) return c;
    c = null;
    if (!/^(var|inherit|initial|unset|revert|currentcolor|transparent)/i.test(v) && v.indexOf('var(') < 0) {
      ctx.fillStyle = '#010203';
      ctx.fillStyle = v;
      var s = ctx.fillStyle;
      if (s !== '#010203' || /^#010203$/i.test(v)) {
        if (s[0] === '#') c = [parseInt(s.substr(1, 2), 16), parseInt(s.substr(3, 2), 16), parseInt(s.substr(5, 2), 16), 1];
        else { var m = s.match(/[\d.]+/g); c = m ? [+m[0], +m[1], +m[2], +m[3]] : null; }
      }
    }
    cache.set(v, c);
    return c;
  }
  function toHsl(r, g, b) {
    r /= 255; g /= 255; b /= 255;
    var mx = Math.max(r, g, b), mn = Math.min(r, g, b), l = (mx + mn) / 2, h = 0, s = 0, d = mx - mn;
    if (d) {
      s = l > 0.5 ? d / (2 - mx - mn) : d / (mx + mn);
      h = mx === r ? (g - b) / d + (g < b ? 6 : 0) : mx === g ? (b - r) / d + 2 : (r - g) / d + 4;
      h *= 60;
    }
    return [h, s, l];
  }
  function css(h, s, l, a) {
    return 'hsla(' + h.toFixed(1) + ',' + (s * 100).toFixed(1) + '%,' + (l * 100).toFixed(1) + '%,' + a + ')';
  }
  // kind: 'bg' | 'fg' | 'border'
  function mapColor(c, kind) {
    var hsl = toHsl(c[0], c[1], c[2]), h = hsl[0], s = hsl[1], l = hsl[2], a = c[3];
    var blue = h >= 195 && h <= 260;
    if (kind === 'bg') {
      var yellow = Math.abs(h - 60) < 15 && s > 0.12;
      if (l <= 0.5) l = l * (yellow ? 0.6 + 0.4 * (0.5 - l) / 0.3 : 0.8);
      else l = 0.1 + (1 - l) * (yellow ? 0.4 : 0.6);
      if (s > 0.12 && hsl[2] >= 0.5 && h > 90 && h < 150) h -= 15 * (1 - Math.abs(h - 120) / 30);
      if (s <= 0.12 || (blue && hsl[2] >= 0.5 && s * (1 - hsl[2]) < 0.15)) { h = BG[0]; s = BG[1]; }
      return css(h, s, l, a);
    }
    if (kind === 'fg') {
      var lo = hsl[2] <= 0.5;
      l = lo ? 0.9 - (blue && s > 0.12 ? 0.6 : 0.7) * l : 0.9 - 0.7 * (1 - l);
      if (blue && s > 0.12) h = h <= 210 ? h - 3 : Math.min(222, 207 + (h - 210) * 0.37);
      if (s <= 0.12 || (hsl[2] < 0.25 && s < 0.6)) { h = FG[0]; s = FG[1]; }
      return css(h, s, l, a);
    }
    var light = l >= 0.5;
    l = 0.2 + (1 - l) * 0.3;
    if (s <= 0.12) { h = light ? BG[0] : FG[0]; s = light ? BG[1] : FG[1]; }
    return css(h, s, l, a);
  }
  var PROPS = [['background-color', 'bg'], ['color', 'fg'], ['border-top-color', 'border'],
    ['border-right-color', 'border'], ['border-bottom-color', 'border'], ['border-left-color', 'border'],
    ['outline-color', 'border'], ['fill', 'fg'], ['stroke', 'fg'], ['text-decoration-color', 'fg'],
    ['column-rule-color', 'border'], ['caret-color', 'fg']];
  var COLRE = /#[0-9a-f]{3,8}\b|rgba?\([^)]*\)|hsla?\([^)]*\)|\b(white|black|whitesmoke|gainsboro|silver|gray|grey|lightgr[ae]y)\b/gi;
  function mapValue(v, kind) {
    var c = parse(v);
    if (c) return mapColor(c, kind);
    return null;
  }
  function mapGradient(v) {
    return v.replace(COLRE, function (m) { var c = parse(m); return c ? mapColor(c, 'bg') : m; });
  }

  // --- custom properties: the kind is guessed from where the variable is used --
  var varKind = new Map();
  function noteVars(val, kind) {
    var re = /var\(\s*(--[\w-]+)/g, m;
    while ((m = re.exec(val))) if (!varKind.has(m[1])) varKind.set(m[1], kind);
  }

  // --- one style declaration -> the override text ------------------------------
  function onPicture(st) { return st.getPropertyValue('background-image').indexOf('url(') >= 0; }
  // light text drawn on a picture keeps its own colour (Dark Reader dims it: less contrast on photos)
  function keepLight(p, v, st) {
    if (p !== 'color' || !onPicture(st)) return false;
    var c = parse(v);
    return !!c && toHsl(c[0], c[1], c[2])[2] >= 0.5;
  }
  function decl(st) {
    var out = '';
    for (var i = 0; i < PROPS.length; i++) {
      var p = PROPS[i][0], v = st.getPropertyValue(p);
      if (!v) continue;
      var imp = st.getPropertyPriority(p) ? ' !important' : '';
      if (v.indexOf('var(') >= 0) { noteVars(v, PROPS[i][1]); out += p + ':' + v + imp + ';'; continue; }
      var m = keepLight(p, v, st) ? null : mapValue(v, PROPS[i][1]);
      out += p + ':' + (m || v) + imp + ';';          // unmapped values kept: the cascade order stays the page's
    }
    var bi = st.getPropertyValue('background-image');
    if (bi && bi.indexOf('gradient') >= 0 && bi.indexOf('url(') < 0) out += 'background-image:' + mapGradient(bi) + ';';
    for (var j = 0; j < st.length; j++) {
      var n = st[j];
      if (n.charCodeAt(0) === 45 && n.charCodeAt(1) === 45) {
        var cv = st.getPropertyValue(n).trim(), cc = parse(cv);
        if (cc) out += n + ':' + mapColor(cc, varKind.get(n) || 'bg') + ';';
        else if (cv.indexOf('gradient') >= 0) out += n + ':' + mapGradient(cv) + ';';
      }
    }
    return out;
  }
  function rules(list, out) {
    for (var i = 0; i < list.length; i++) {
      var r = list[i];
      if (r.style && r.selectorText) {
        var d = decl(r.style);
        if (d) out.push(r.selectorText + '{' + d + '}');
        if (r.cssRules && r.cssRules.length) { var sub = []; rules(r.cssRules, sub); if (sub.length) out.push(r.selectorText + '{' + sub.join('') + '}'); }
      } else if (r.cssRules) {
        var inner = [];
        rules(r.cssRules, inner);
        if (!inner.length) continue;
        if (r.media) out.push('@media ' + r.media.mediaText + '{' + inner.join('\n') + '}');
        else if (r.conditionText !== undefined && r.constructor.name === 'CSSSupportsRule') out.push('@supports ' + r.conditionText + '{' + inner.join('\n') + '}');
        else if (r.constructor.name === 'CSSLayerBlockRule') out.push('@layer ' + r.name + '{' + inner.join('\n') + '}');
        else out.push(inner.join('\n'));
      } else if (r.styleSheet) {                     // @import
        try { rules(r.styleSheet.cssRules, out); } catch (e) {}
      }
    }
  }

  // --- style sheets: one override <style> right after each source -------------
  var done = new WeakMap();                         // owner node -> {n: rules seen, el: override}
  function own(el) { return el.classList && el.classList.contains('ike-de'); }
  function sheetOf(node) {
    if (own(node)) return;
    var sh = node.sheet;
    if (!sh) return;
    var list;
    try { list = sh.cssRules; } catch (e) { return; }  // cross-origin: not readable from here (see the report)
    var st = done.get(node);
    if (st && st.n === list.length) return;
    var out = [];
    rules(list, out);
    if (!st) {
      st = { n: 0, el: document.createElement('style') };
      st.el.className = 'ike-de';
      done.set(node, st);
    }
    st.n = list.length;
    st.el.textContent = out.join('\n');
    if (node.nextSibling !== st.el) node.parentNode.insertBefore(st.el, node.nextSibling);
  }
  function scanSheets() {
    var n = document.querySelectorAll('style:not(.ike-de),link[rel~="stylesheet"]');
    for (var i = 0; i < n.length; i++) sheetOf(n[i]);
  }

  // --- inline styles and colour attributes -----------------------------------
  var applied = new WeakMap();                       // element -> serialized style we wrote
  function inline(el) {
    if (fix.ignoreInline && fix.ignoreInline.length && el.matches(fix.ignoreInline)) return;
    var st = el.style;
    if (st && st.length && applied.get(el) !== st.cssText) {
      for (var i = 0; i < PROPS.length; i++) {
        var p = PROPS[i][0], v = st.getPropertyValue(p);
        if (!v || v.indexOf('var(') >= 0 || keepLight(p, v, st)) continue;
        var m = mapValue(v, PROPS[i][1]);
        if (m) st.setProperty(p, m, st.getPropertyPriority(p));
      }
      var bi = st.getPropertyValue('background-image');
      if (bi && bi.indexOf('gradient') >= 0) st.setProperty('background-image', mapGradient(bi));
    }
    var a = el.getAttribute('bgcolor');
    if (a) { var c = parse(a); if (c) el.style.setProperty('background-color', mapColor(c, 'bg')); }
    if (el.namespaceURI === 'http://www.w3.org/2000/svg') {
      ['fill', 'stroke'].forEach(function (p) {
        var v = el.getAttribute(p), c = v && parse(v);
        if (c && !el.style.getPropertyValue(p)) el.style.setProperty(p, mapColor(c, 'fg'));
      });
    } else if (el.tagName === 'FONT' && el.getAttribute('color')) {
      var fc = parse(el.getAttribute('color'));
      if (fc) el.style.setProperty('color', mapColor(fc, 'fg'));
    }
    applied.set(el, el.style.cssText);
  }
  // --- pictures: only small ones with transparency, once each, when loaded ------
  var probe = new OffscreenCanvas(24, 24).getContext('2d', { willReadFrequently: true });
  function lookAt(img) {
    if (img.__ikeDE || !img.complete || !img.naturalWidth) return;
    img.__ikeDE = true;
    if (img.naturalWidth * img.naturalHeight > 512 * 512 || /\.jpe?g($|\?)/i.test(img.currentSrc)) return;
    var d;
    try {
      probe.clearRect(0, 0, 24, 24);
      probe.drawImage(img, 0, 0, 24, 24);
      d = probe.getImageData(0, 0, 24, 24).data;   // a picture of another site cannot be read here
    } catch (e) { return; }
    var clear = 0, n = 0, lum = 0;
    for (var i = 0; i < d.length; i += 4) {
      if (d[i + 3] < 30) { clear++; continue; }
      n++;
      lum += (0.2126 * d[i] + 0.7152 * d[i + 1] + 0.0722 * d[i + 2]) / 255;
    }
    if (clear > 0.2 * 576 && n && lum / n < 0.3) img.classList.add('ike-de-lift');
  }
  function images(root) {
    var l = root.tagName === 'IMG' ? [root] : root.getElementsByTagName('img');
    for (var i = 0; i < l.length; i++) {
      if (l[i].complete) lookAt(l[i]);
      else l[i].addEventListener('load', function () { lookAt(this); }, { once: true });
    }
  }

  var SEL = '[style],[bgcolor],font[color],svg [fill],svg [stroke]';
  function inlineTree(root) {
    if (root.nodeType !== 1) return;
    images(root);
    if (root.matches(SEL)) inline(root);
    var l = root.querySelectorAll(SEL);
    for (var i = 0; i < l.length; i++) inline(l[i]);
  }

  // --- the base sheet and the site's fix (Dark Reader's list) -----------------
  function base() {
    var t = ':root{color-scheme:dark!important}' +
      'html{background-color:#181a1b!important}html,body{color:#e8e6e3;border-color:#736b5e}' +
      'a{color:#3391ff}input,textarea,select,button{color:#e8e6e3}' +
      '::placeholder{color:#b2aba1}';
    var inv = (fix.invert || []).join(',');
    if (inv) t += inv + '{filter:invert(100%) hue-rotate(180deg)!important}';
    if (fix.css) {
      t += fix.css.replace(/var\(--darkreader-neutral-background\)/g, '#181a1b')
        .replace(/var\(--darkreader-neutral-text\)/g, '#e8e6e3')
        .replace(/var\(--darkreader-selection-background\)/g, '#004daf')
        .replace(/var\(--darkreader-selection-text\)/g, '#e8e6e3')
        .replace(/([\w-]+)\s*:\s*\$\{([^}]+)\}/g, function (m, prop, col) {
          var c = parse(col.trim());
          var kind = /background|shadow/.test(prop) ? 'bg' : /border|outline/.test(prop) ? 'border' : 'fg';
          return prop + ':' + (c ? mapColor(c, kind) : col);
        });
    }
    // placeholders: Dark Reader's common fix halves their opacity, below 3:1 on dark fields
    t += '::placeholder{opacity:1!important;color:#8f8a83}';
    t += '.ike-de-lift{filter:invert(100%) hue-rotate(180deg)!important}';
    var s = document.createElement('style');
    s.className = 'ike-de';
    s.textContent = t;
    return s;
  }

  // --- a page that is dark already is left alone --------------------------------
  function isDarkAlready() {
    var m = document.querySelector('meta[name="color-scheme"]');
    if (m && /^\s*dark\s*$/i.test(m.content)) return true;
    var b = document.body, c;
    var sheets = document.querySelectorAll('style.ike-de');
    for (var i = 0; i < sheets.length; i++) sheets[i].disabled = true;
    try {
      c = parse(getComputedStyle(b || document.documentElement).backgroundColor);
      if (!c || c[3] === 0) c = parse(getComputedStyle(document.documentElement).backgroundColor);
    } finally { for (var j = 0; j < sheets.length; j++) sheets[j].disabled = false; }
    return !!(c && c[3] > 0 && toHsl(c[0], c[1], c[2])[2] < 0.3);
  }

  // --- start, then only what is added ----------------------------------------
  var baseEl = null, off = false, pending = [];
  function stop() {
    off = true;
    if (wait) wait.disconnect();
    mo.disconnect();
    document.querySelectorAll('style.ike-de').forEach(function (e) { e.remove(); });
  }
  function flush() {
    var list = pending;
    pending = [];
    for (var i = 0; i < list.length; i++) {
      var m = list[i];
      if (m.type === 'attributes') { if (!own(m.target)) inline(m.target); continue; }
      for (var j = 0; j < m.addedNodes.length; j++) {
        var n = m.addedNodes[j];
        if (n.nodeType !== 1 || own(n)) continue;
        if (n.tagName === 'STYLE') sheetOf(n);
        else if (n.tagName === 'LINK') n.addEventListener('load', function () { sheetOf(this); });
        else inlineTree(n);
      }
      if (m.target && m.target.tagName === 'STYLE' && !own(m.target)) sheetOf(m.target);
    }
  }
  var mo = new MutationObserver(function (ms) {
    if (off) return;
    if (!pending.length) Promise.resolve().then(flush);
    for (var i = 0; i < ms.length; i++) pending.push(ms[i]);
  });
  function start() {
    if (baseEl || off) return true;
    var root = document.documentElement;
    if (!root) return false;
    baseEl = base();
    (document.head || root).appendChild(baseEl);
    mo.observe(document, { childList: true, subtree: true, attributes: true, attributeFilter: ['style', 'bgcolor'] });
    return true;
  }
  var wait = null;
  if (!start()) {
    wait = new MutationObserver(function () { if (start()) wait.disconnect(); });
    wait.observe(document, { childList: true });
  }
  function ready() {
    if (off) return;
    if (wait) wait.disconnect();
    start();
    if (isDarkAlready()) { stop(); return; }
    if (baseEl && baseEl.parentNode !== document.head && document.head) document.head.appendChild(baseEl);
    scanSheets();
    inlineTree(document.documentElement);
  }
  if (document.readyState !== 'loading' && document.body) ready();
  else document.addEventListener('DOMContentLoaded', ready, { once: true });
  // sheets that grow through insertRule are not seen by the observer: checked at load
  window.addEventListener('load', function () { if (!off) scanSheets(); }, { once: true });
})();
