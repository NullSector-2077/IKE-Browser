// I.K.E. Dark Engine (EXPERIMENT, off by default; loaded by ike/darkengine.py). I.K.E.'s own
// dark mode for pages: one pass over the page's style sheets and inline styles,
// one generated override style sheet per source sheet, then only the nodes and
// sheets added later, in batches. No re-analysis of the whole page.
// Also: style sheets of other sites (fetched as I.K.E. fetches them for Dark
// Reader, resources/darkmode.js), rules added by script (insertRule, adopted
// sheets: the known sheets' lengths are compared with each batch), open shadow
// roots, CSS variables (one mapping per use: background, text, border), shadows,
// light background pictures (made dark; photos kept).
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
      if (s <= 0.12 || (h >= 200 && h <= 260 && hsl[2] >= 0.5 && s * (1 - hsl[2]) < 0.15)) { h = BG[0]; s = BG[1]; }
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
    // a faint dark line (rgba(0,0,0,.2)) would vanish on a dark page: it keeps standing out
    if (!light && a < 0.5) a = +(0.45 + a * 0.6).toFixed(2);
    if (s <= 0.12) { h = light ? BG[0] : FG[0]; s = light ? BG[1] : FG[1]; }
    return css(h, s, l, a);
  }
  var PROPS = [['background-color', 'bg'], ['color', 'fg'], ['border-top-color', 'border'],
    ['border-right-color', 'border'], ['border-bottom-color', 'border'], ['border-left-color', 'border'],
    ['outline-color', 'border'], ['fill', 'fg'], ['stroke', 'fg'], ['text-decoration-color', 'fg'],
    ['column-rule-color', 'border'], ['caret-color', 'fg'], ['-webkit-text-fill-color', 'fg']];
  // shorthands whose longhands read empty while they hold a var()
  var SHORT = [['background', 'bg'], ['border', 'border'], ['border-top', 'border'], ['border-right', 'border'],
    ['border-bottom', 'border'], ['border-left', 'border'], ['border-color', 'border'], ['outline', 'border'],
    ['border-block', 'border'], ['border-inline', 'border'], ['border-block-end', 'border'],
    ['border-block-start', 'border'], ['border-inline-start', 'border'], ['border-inline-end', 'border']];
  var COLRE = /#[0-9a-f]{3,8}\b|rgba?\([^)]*\)|hsla?\([^)]*\)|\b(white|black|whitesmoke|gainsboro|silver|gray|grey|lightgr[ae]y|ivory|snow|beige)\b/gi;
  var COLTEST = new RegExp(COLRE.source, 'i');
  var PRE = /color|background|border|outline|shadow|fill|stroke|--|caret/;
  var TRIPLE = /^\s*(\d{1,3})\s*[, ]\s*(\d{1,3})\s*[, ]\s*(\d{1,3})\s*$/;
  function mapValue(v, kind) {
    var c = parse(v);
    return c ? mapColor(c, kind) : null;
  }
  function mapColors(v, kind) {
    return v.replace(COLRE, function (m) { var c = parse(m); return c ? mapColor(c, kind) : m; });
  }
  function rgbTriple(c) {                   // "hsla(...)" -> "r, g, b" for a variable used inside rgba()
    ctx.fillStyle = c;
    var s = ctx.fillStyle;
    if (s[0] === '#') return parseInt(s.substr(1, 2), 16) + ', ' + parseInt(s.substr(3, 2), 16) + ', ' + parseInt(s.substr(5, 2), 16);
    var m = s.match(/[\d.]+/g);
    return m[0] + ', ' + m[1] + ', ' + m[2];
  }

  // --- custom properties: one definition per use (background, text, border) ---
  // --x keeps the background mapping; --ike-fg-x and --ike-bd-x hold the text
  // and border mappings, and a use in a text or border property is rewritten
  // to them (with --x as the fallback for a variable defined where we cannot read).
  var VK = { fg: 'fg', border: 'bd' };
  function useVars(v, kind) {
    if (v.indexOf('var(') < 0) return mapColors(v, kind);
    var k = VK[kind], out = '', i = 0;
    for (;;) {
      var j = v.indexOf('var(', i);
      if (j < 0) { out += mapColors(v.slice(i), kind); break; }
      out += mapColors(v.slice(i, j), kind);
      var depth = 0, e = j + 3;
      for (; e < v.length; e++) { if (v[e] === '(') depth++; else if (v[e] === ')' && !--depth) break; }
      var inner = v.slice(j + 4, e), c = inner.indexOf(','), name = (c < 0 ? inner : inner.slice(0, c)).trim();
      var fb = c < 0 ? '' : ',' + useVars(inner.slice(c + 1), kind);
      if (!k || name.indexOf('--ike-') === 0) out += 'var(' + name + fb + ')';
      else out += 'var(--ike-' + k + '-' + name.slice(2) + ',var(' + name + fb + '))';
      i = e + 1;
    }
    return out;
  }
  function defineVar(n, v) {              // -> declarations text, '' when not a colour
    v = v.trim();
    if (!v || n.indexOf('--ike-') === 0) return '';
    var c = parse(v), name = n.slice(2);
    if (c) return n + ':' + mapColor(c, 'bg') + ';--ike-fg-' + name + ':' + mapColor(c, 'fg') + ';--ike-bd-' + name + ':' + mapColor(c, 'border') + ';';
    var t = v.match(TRIPLE);
    if (t) {
      var cc = [+t[1], +t[2], +t[3], 1];
      return n + ':' + rgbTriple(mapColor(cc, 'bg')) + ';--ike-fg-' + name + ':' + rgbTriple(mapColor(cc, 'fg')) +
        ';--ike-bd-' + name + ':' + rgbTriple(mapColor(cc, 'border')) + ';';
    }
    if (v.indexOf('var(') >= 0 && !/[;{}]/.test(v)) return '--ike-fg-' + name + ':' + useVars(v, 'fg') + ';--ike-bd-' + name + ':' + useVars(v, 'border') + ';';
    if (v.indexOf('gradient') >= 0) return n + ':' + mapColors(v, 'bg') + ';';
    if (COLTEST.test(v) && (/shadow|-bg|background/i.test(n) || /px/.test(v))) return n + ':' + mapColors(v, 'bg') + ';';
    return '';
  }

  // --- background pictures: light ones are made dark, photos kept -----------------
  var pics = new Map();                     // absolute url -> {state, data, waiting: [fn]}
  var work = new OffscreenCanvas(32, 32).getContext('2d', { willReadFrequently: true });
  function picture(url, done) {
    var p = pics.get(url);
    if (p) { if (p.state === 'wait') p.waiting.push(done); return p; }
    p = { state: 'wait', data: null, waiting: [done] };
    pics.set(url, p);
    var img = new Image();
    img.crossOrigin = 'anonymous';          // read without cookies; a picture that does not allow it stays as it is
    var end = function (data) {
      p.state = data ? 'dark' : 'keep';
      p.data = data;
      var w = p.waiting;
      p.waiting = [];
      if (data) for (var i = 0; i < w.length; i++) w[i]();
    };
    img.onerror = function () { end(null); };
    img.onload = function () {
      try {
        var w = img.naturalWidth || 64, h = img.naturalHeight || 64;
        work.clearRect(0, 0, 32, 32);
        work.drawImage(img, 0, 0, 32, 32);
        var d = work.getImageData(0, 0, 32, 32).data, clear = 0, n = 0, sum = 0, sq = 0;
        for (var i = 0; i < d.length; i += 4) {
          if (d[i + 3] < 30) { clear++; continue; }
          var y = (0.2126 * d[i] + 0.7152 * d[i + 1] + 0.0722 * d[i + 2]) / 255;
          n++; sum += y; sq += y * y;
        }
        if (!n) { end(null); return; }
        var avg = sum / n, sd = Math.sqrt(Math.max(0, sq / n - avg * avg)), small = w <= 256 && h <= 256;
        var darkIcon = clear > 100 && avg < 0.3 && small;              // dark drawing on transparency
        var lightPanel = clear < 50 && avg > 0.75 && (small || sd < 0.08); // light texture or plain light area
        if (!(darkIcon || lightPanel) || w > 1024 || h > 1024) { end(null); return; }
        var cv = new OffscreenCanvas(w, h), c2 = cv.getContext('2d');
        c2.filter = 'invert(100%) hue-rotate(180deg)';
        c2.drawImage(img, 0, 0, w, h);
        cv.convertToBlob().then(function (b) {
          var r = new FileReader();
          r.onload = function () { end(r.result); };
          r.onerror = function () { end(null); };
          r.readAsDataURL(b);
        }, function () { end(null); });
      } catch (e) { end(null); }             // a picture of another site without permission
    };
    img.src = url;
    return p;
  }
  // background-image value -> new value, or null when nothing changes
  function mapImage(v, base, again) {
    if (v.indexOf('url(') < 0) return v.indexOf('gradient') >= 0 ? mapColors(v, 'bg') : null;
    var changed = v.indexOf('gradient') >= 0;
    var out = v.replace(/url\(\s*(["']?)([^"')]+)\1\s*\)/g, function (m, q, u) {
      if (/^data:image\/svg|^data:/.test(u) && u.length > 4000) return m;
      var abs;
      try { abs = new URL(u, base || document.baseURI).href; } catch (e) { return m; }
      var p = picture(abs, again);
      if (p.state === 'dark') { changed = true; return 'url("' + p.data + '")'; }
      return 'url("' + abs + '")';
    });
    if (!changed) return null;
    return out.replace(/(linear|radial|conic|repeating-linear|repeating-radial)-gradient\((?:[^()]|\([^()]*\))*\)/g,
      function (g) { return mapColors(g, 'bg'); });
  }

  // --- one style declaration -> the override text ------------------------------
  function onPicture(st) { return st.getPropertyValue('background-image').indexOf('url(') >= 0; }
  // light text drawn on a picture keeps its own colour (Dark Reader dims it: less contrast on photos)
  function keepLight(p, v, st) {
    if (p !== 'color' || !onPicture(st)) return false;
    var c = parse(v);
    return !!c && toHsl(c[0], c[1], c[2])[2] >= 0.5;
  }
  var KIND = {}, KEYWORD = /^(transparent|inherit|currentcolor|initial|unset|none|revert)$/i;
  PROPS.forEach(function (p) { KIND[p[0]] = p[1]; });
  function imp(st, n) { return st.getPropertyPriority(n) ? ' !important' : ''; }
  // one pass over the properties the declaration holds (longhands): a colour
  // property is mapped, a shorthand holding a var() (its longhands read empty)
  // is written again with its variables per use
  function decl(st, base, again) {
    if (!PRE.test(st.cssText)) return '';
    var out = '', shorts = false, v;
    for (var j = 0; j < st.length; j++) {
      var n = st[j], k = KIND[n];
      if (n.charCodeAt(0) === 45 && n.charCodeAt(1) === 45) { out += defineVar(n, st.getPropertyValue(n)); continue; }
      if (k) {
        v = st.getPropertyValue(n);
        if (!v) { shorts = true; continue; }
        if (v.indexOf('var(') >= 0) { out += n + ':' + useVars(v, k) + imp(st, n) + ';'; continue; }
        var m = keepLight(n, v, st) ? null : mapValue(v, k);
        // other values are kept so that the cascade order stays the page's, except
        // the keywords that cannot lose a colour (fewer rules: less work for the engine)
        if (m || !KEYWORD.test(v)) out += n + ':' + (m || v) + imp(st, n) + ';';
      } else if (n === 'background-image') {
        v = st.getPropertyValue(n);
        if (!v) { shorts = true; continue; }
        if (v !== 'none' && v.indexOf('var(') < 0) {
          var nb = mapImage(v, base, again);
          if (nb) out += n + ':' + nb + imp(st, n) + ';';
        }
      } else if (n === 'box-shadow' || n === 'text-shadow') {
        v = st.getPropertyValue(n);
        if (v && v !== 'none') out += n + ':' + (v.indexOf('var(') >= 0 ? v : mapColors(v, 'bg')) + imp(st, n) + ';';
      }
    }
    if (shorts) {
      for (var i = 0; i < SHORT.length; i++) {
        v = st.getPropertyValue(SHORT[i][0]);
        if (v && v.indexOf('var(') >= 0) out += SHORT[i][0] + ':' + useVars(v, SHORT[i][1]) + imp(st, SHORT[i][0]) + ';';
      }
    }
    return guard(st, out);
  }
  // a rule that gives both a text and a background colour (buttons, tabs, badges):
  // the text keeps at least 4.5:1 against that background once both are mapped
  function lum(c) {
    var f = function (v) { v /= 255; return v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]);
  }
  function guard(st, out) {
    var fv = st.getPropertyValue('color'), bv = st.getPropertyValue('background-color');
    var fc = fv && parse(fv), bc = bv && parse(bv);
    if (!fc || !bc || bc[3] < 0.5 || keepLight('color', fv, st)) return out;
    var fm = parse(mapColor(fc, 'fg')), bm = parse(mapColor(bc, 'bg'));
    var lb = lum(bm), lf = lum(fm);
    if ((Math.max(lb, lf) + 0.05) / (Math.min(lb, lf) + 0.05) >= 4.5) return out;
    var hsl = toHsl(fm[0], fm[1], fm[2]), up = lb < 0.18, l = hsl[2];
    for (var i = 0; i < 20; i++) {
      l = up ? Math.min(1, l + 0.04) : Math.max(0, l - 0.04);
      var c = parse(css(hsl[0], hsl[1], l, fm[3])), lc = lum(c);
      if ((Math.max(lb, lc) + 0.05) / (Math.min(lb, lc) + 0.05) >= 4.5) break;
    }
    var imp = st.getPropertyPriority('color') ? ' !important' : '';
    return out + 'color:' + css(hsl[0], hsl[1], l, fm[3]) + imp + ';';
  }
  function rules(list, out, base, again) {
    for (var i = 0; i < list.length; i++) {
      var r = list[i];
      if (r.style && r.selectorText !== undefined) {
        var d = decl(r.style, base, again);
        var sub = [];
        if (r.cssRules && r.cssRules.length) rules(r.cssRules, sub, base, again);
        if (d || sub.length) out.push(r.selectorText + '{' + d + sub.join('') + '}');
      } else if (r.cssRules) {
        var inner = [];
        rules(r.cssRules, inner, base, again);
        if (!inner.length) continue;
        var cn = r.constructor.name;
        if (r.media) out.push('@media ' + r.media.mediaText + '{' + inner.join('\n') + '}');
        else if (cn === 'CSSSupportsRule') out.push('@supports ' + r.conditionText + '{' + inner.join('\n') + '}');
        else if (cn === 'CSSContainerRule') out.push('@container ' + r.conditionText + '{' + inner.join('\n') + '}');
        else if (cn === 'CSSLayerBlockRule') out.push('@layer ' + r.name + '{' + inner.join('\n') + '}');
        else if (cn === 'CSSScopeRule') out.push('@scope (' + r.start + ')' + (r.end ? ' to (' + r.end + ')' : '') + '{' + inner.join('\n') + '}');
        else out.push(inner.join('\n'));
      } else if (r.styleSheet) {                     // @import
        try { rules(r.styleSheet.cssRules, out, r.styleSheet.href || base, again); } catch (e) {}
      }
    }
  }

  // --- style sheets: one override sheet right after each source ----------------
  // records: owner node (a <style>/<link>) or an adopted sheet -> {n, el|sheet, last}
  var recs = new Map(), stats = { sheets: 0, fetched: 0, rules: 0, ms: 0 };
  function own(el) { return el.classList && el.classList.contains('ike-de'); }
  function write(rec, list, base) {
    var t0 = performance.now(), n = list.length, out = [];
    var again = function () { rec.n = -1; schedule(); };
    // a sheet that only grew at its end (CSS-in-JS): only the new rules
    var target = rec.el ? rec.el.sheet : rec.sheet;
    if (target && rec.n > 0 && n > rec.n && list[rec.n - 1] === rec.last) {
      var tail = [];
      for (var i = rec.n; i < n; i++) tail.push(list[i]);
      rules(tail, out, base, again);
      for (var j = 0; j < out.length; j++) {
        try { target.insertRule(out[j], target.cssRules.length); } catch (e) {}
      }
    } else {
      rules(list, out, base, again);
      if (rec.el) rec.el.textContent = out.join('\n');
      else rec.sheet.replaceSync(out.join('\n'));
    }
    rec.n = n;
    rec.last = n ? list[n - 1] : null;
    stats.rules += out.length;
    stats.ms += performance.now() - t0;
  }
  function sheetOf(node) {
    if (own(node)) return;
    var sh = node.sheet;
    if (!sh) return;
    var rec = recs.get(node);
    if (!rec) {
      rec = { n: -1, node: node };
      if (csp) { rec.sheet = new CSSStyleSheet(); adopt(node.getRootNode(), rec.sheet); }
      else { rec.el = document.createElement('style'); rec.el.className = 'ike-de'; }
      recs.set(node, rec);
      stats.sheets++;
    }
    var list;
    try { list = sh.cssRules; } catch (e) {
      if (!rec.cs) { other(node, rec); return; }
      if (rec.n === -1) write(rec, rec.cs.cssRules, rec.base);
      put(node, rec);
      return;
    }
    if (rec.n !== list.length || (list.length && list[list.length - 1] !== rec.last)) write(rec, list, sh.href || document.baseURI);
    put(node, rec);
  }
  function put(node, rec) {
    if (rec.el) { if (node.nextSibling !== rec.el && node.parentNode) node.parentNode.insertBefore(rec.el, node.nextSibling); }
    else adopt(node.getRootNode(), rec.sheet);
  }
  // a style sheet of another site: its text comes as Dark Reader's own does in
  // I.K.E. (resources/darkmode.js): a plain fetch without cookies, else the
  // browser's own fetch (passwords.py PageBridge.fetchCss: the same address the
  // page loaded, style sheets only, checked by the filter lists)
  var bridgeWait = null, asks = {}, seq = 0;
  function bridge() {
    if (!bridgeWait) bridgeWait = new Promise(function (ok, no) {
      var tries = 0;
      (function look() {
        var b = window.__ikeBridge;
        if (b && typeof b.fetchCss === 'function' && b.cssFetched) {
          b.cssFetched.connect(function (id, good, text) {
            var a = asks[id];
            if (!a) return;
            delete asks[id];
            if (good) a[0](text); else a[1](new Error('no'));
          });
          ok(b);
          return;
        }
        if (++tries > 60) { no(new Error('no bridge')); return; }
        setTimeout(look, 100);
      })();
    });
    return bridgeWait;
  }
  function viaBrowser(url) {
    return bridge().then(function (b) {
      return new Promise(function (ok, no) {
        var id = 'de' + (++seq);
        asks[id] = [ok, no];
        b.fetchCss(id, url);
        setTimeout(function () { if (asks[id]) { delete asks[id]; no(new Error('timeout')); } }, 15000);
      });
    });
  }
  function other(node, rec) {
    if (rec.fetching || !node.href) return;
    rec.fetching = true;
    var url = node.href;
    fetch(url, { credentials: 'omit' }).then(function (r) {
      if (!r.ok) throw new Error('status');
      return r.text();
    }).catch(function () { return viaBrowser(url); }).then(function (text) {
      if (off) return;
      var cs = new CSSStyleSheet();
      cs.replaceSync(text.replace(/@import[^;]+;/g, ''));
      rec.n = -1;
      rec.cs = cs;
      rec.base = url;
      stats.fetched++;
      write(rec, cs.cssRules, url);
      put(node, rec);
    }, function () {});
  }
  // sheets built in script (adoptedStyleSheets): an override sheet adopted right after each
  function adopted(root) {
    var list = root.adoptedStyleSheets;
    if (!list || !list.length) return;
    var want = [], change = false;
    for (var i = 0; i < list.length; i++) {
      var s = list[i];
      if (s.__ikeDE) { if (!s.__pair) want.push(s); continue; }
      want.push(s);
      var rec = recs.get(s);
      if (!rec) { rec = { n: -1, sheet: new CSSStyleSheet() }; rec.sheet.__ikeDE = rec.sheet.__pair = true; recs.set(s, rec); stats.sheets++; }
      if (rec.n !== s.cssRules.length) write(rec, s.cssRules, document.baseURI);
      want.push(rec.sheet);
      if (list[i + 1] !== rec.sheet) change = true;
    }
    if (change || want.length !== list.length) root.adoptedStyleSheets = want;
  }
  // rules added through insertRule leave no trace in the document: the sheets
  // already known are looked at again (one length per sheet) with every batch
  // (shadow roots' adopted sheets only on the timers: components adopt theirs
  // before they are seen, and a page can hold thousands of roots)
  function grown(all) {
    recs.forEach(function (rec, owner) {
      if (rec.node) {
        if (!rec.node.isConnected) { recs.delete(owner); return; }
        if (rec.cs) { if (rec.n === -1) sheetOf(rec.node); return; }
        var sh = rec.node.sheet, l;
        if (!sh || rec.fetching) return;
        try { l = sh.cssRules; } catch (e) { return; }
        if (l.length !== rec.n || (l.length && l[l.length - 1] !== rec.last)) sheetOf(rec.node);
      }
    });
    adopted(document);
    if (all) roots.forEach(function (r) { if (!r.host.isConnected) roots.delete(r); else adopted(r); });
  }
  function scanSheets(root) {
    var n = root.querySelectorAll('style:not(.ike-de),link[rel~="stylesheet"]');
    for (var i = 0; i < n.length; i++) {
      if (n[i].tagName === 'LINK' && !n[i].sheet) n[i].addEventListener('load', function () { sheetOf(this); }, { once: true });
      else sheetOf(n[i]);
    }
    adopted(root);
  }

  // --- inline styles and colour attributes -----------------------------------
  var applied = new WeakMap();                       // element -> serialized style we wrote
  function inline(el) {
    if (fix.ignoreInline && fix.ignoreInline.length && el.matches(fix.ignoreInline)) return;
    var st = el.style, text = st ? st.cssText : '';
    if (text && applied.get(el) !== text && PRE.test(text)) {
      var again = function () { applied.delete(el); inline(el); };
      var names = [], shorts = false;
      for (var i = 0; i < st.length; i++) names.push(st[i]);
      names.forEach(function (n) {
        var k = KIND[n], v = st.getPropertyValue(n);
        if (k) {
          if (!v) { shorts = true; return; }
          if (keepLight(n, v, st)) return;
          var m = v.indexOf('var(') >= 0 ? useVars(v, k) : mapValue(v, k);
          if (m && m !== v) st.setProperty(n, m, st.getPropertyPriority(n));
        } else if (n === 'background-image') {
          if (!v) { shorts = true; return; }
          if (v !== 'none' && v.indexOf('var(') < 0) { var nb = mapImage(v, document.baseURI, again); if (nb) st.setProperty(n, nb); }
        } else if ((n === 'box-shadow' || n === 'text-shadow') && v && v !== 'none' && v.indexOf('var(') < 0) {
          st.setProperty(n, mapColors(v, 'bg'));
        }
      });
      if (shorts) {
        for (var k2 = 0; k2 < SHORT.length; k2++) {
          var sv = st.getPropertyValue(SHORT[k2][0]);
          if (sv && sv.indexOf('var(') >= 0) { var nv = useVars(sv, SHORT[k2][1]); if (nv !== sv) st.setProperty(SHORT[k2][0], nv); }
        }
      }
      var defs = [];
      for (var j = 0; j < st.length; j++) if (st[j].indexOf('--') === 0 && st[j].indexOf('--ike-') !== 0) defs.push(st[j]);
      defs.forEach(function (n) {
        var d = defineVar(n, st.getPropertyValue(n));
        d.split(';').forEach(function (pair) {
          var c = pair.indexOf(':');
          if (c > 0) st.setProperty(pair.slice(0, c), pair.slice(c + 1));
        });
      });
    }
    var a = el.getAttribute('bgcolor');
    if (a) { var c = parse(a); if (c) el.style.setProperty('background-color', mapColor(c, 'bg')); }
    if (el.namespaceURI === 'http://www.w3.org/2000/svg') {
      ['fill', 'stroke'].forEach(function (p) {
        var v = el.getAttribute(p), cc = v && parse(v);
        if (cc && !el.style.getPropertyValue(p)) el.style.setProperty(p, mapColor(cc, 'fg'));
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

  // --- shadow roots (open ones) are treated as small documents -------------------
  var roots = new Set(), hosts = new Set();
  function shadow(el) {
    var sr = el.shadowRoot;
    if (!sr) { hosts.add(el); return; }
    hosts.delete(el);
    if (roots.has(sr)) return;
    roots.add(sr);
    mo.observe(sr, OBS);
    scanSheets(sr);
    tree(sr);
  }
  var SEL = '[style],[bgcolor],font[color],svg [fill],svg [stroke]';
  var SVGNS = 'http://www.w3.org/2000/svg';
  function needsInline(e) {
    return e.hasAttribute('style') || (e.namespaceURI === SVGNS ? e.hasAttribute('fill') || e.hasAttribute('stroke')
      : e.hasAttribute('bgcolor') || (e.tagName === 'FONT' && e.hasAttribute('color')));
  }
  function tree(root) {
    var l, i, e;
    if (root.nodeType === 1) {
      if (needsInline(root)) inline(root);
      if (root.tagName === 'IMG') look(root);
      if (root.localName.indexOf('-') > 0) shadow(root);
      if (!root.firstElementChild) return;              // most added nodes: nothing below
    }
    l = root.querySelectorAll(SEL);
    for (i = 0; i < l.length; i++) inline(l[i]);
    l = root.querySelectorAll('*');
    for (i = 0; i < l.length; i++) {
      e = l[i];
      if (e.tagName === 'IMG') look(e);
      else if (e.localName.indexOf('-') > 0) shadow(e);
    }
  }
  function look(img) {
    if (img.complete) lookAt(img);
    else img.addEventListener('load', function () { lookAt(this); }, { once: true });
  }

  // --- the base sheet and the site's fix (Dark Reader's list) -----------------
  var csp = false, baseSheet = null;
  function adopt(root, sheet) {
    sheet.__ikeDE = true;
    var l = root.adoptedStyleSheets;
    if (l.indexOf(sheet) < 0) root.adoptedStyleSheets = l.concat([sheet]);
  }
  function base() {
    var t = ':root{color-scheme:dark!important}' +
      'html{background-color:#181a1b!important}:where(html,body){color:#e8e6e3;border-color:#736b5e}' +
      ':where(a){color:#3391ff}:where(input,textarea,select,button){color:#e8e6e3}';
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
    t += '::placeholder{opacity:1!important;color:#a8a39b}';
    // the engine's own dark controls draw a disabled button's text at about 2:1
    t += ':where(button,input,select,textarea):disabled{color:#b5b0a8}';
    // the engine's own dark button face is mid-grey: a page's grey button text on it is unreadable
    t += ':where(button,select,input[type=button],input[type=submit],input[type=reset]){background-color:#2b2e30}';
    t += '.ike-de-lift{filter:invert(100%) hue-rotate(180deg)!important}';
    var s = document.createElement('style');
    s.className = 'ike-de';
    s.textContent = t;
    return s;
  }

  // --- a page that is dark already is left alone --------------------------------
  // (only a page that says so: a dark page that does not is mapped like any
  // other, its dark colours stay dark and its light parts become dark too)
  function isDarkAlready() {
    var m = document.querySelector('meta[name="color-scheme"]');
    return !!(m && /^\s*dark\s*$/i.test(m.content));
  }

  // --- start, then only what is added ----------------------------------------
  var baseEl = null, off = false, pending = [], queued = false, wait = null;
  var OBS = { childList: true, subtree: true, attributes: true, attributeFilter: ['style', 'bgcolor'] };
  function stop() {
    off = true;
    if (wait) wait.disconnect();
    mo.disconnect();
    document.querySelectorAll('style.ike-de').forEach(function (e) { e.remove(); });
    if (document.adoptedStyleSheets.some(function (x) { return x.__ikeDE; })) {
      document.adoptedStyleSheets = document.adoptedStyleSheets.filter(function (x) { return !x.__ikeDE; });
    }
  }
  function schedule() {
    if (queued || off) return;
    queued = true;
    Promise.resolve().then(flush);
  }
  function flush() {
    queued = false;
    if (off) return;
    var t0 = performance.now();
    var list = pending;
    pending = [];
    for (var i = 0; i < list.length; i++) {
      var m = list[i];
      if (m.type === 'attributes') { if (!own(m.target)) inline(m.target); continue; }
      for (var j = 0; j < m.addedNodes.length; j++) {
        var n = m.addedNodes[j];
        if (n.nodeType !== 1 || own(n)) continue;
        if (n.tagName === 'STYLE') sheetOf(n);
        else if (n.tagName === 'LINK') n.addEventListener('load', function () { sheetOf(this); }, { once: true });
        else tree(n);
      }
      if (m.target && m.target.tagName === 'STYLE' && !own(m.target)) sheetOf(m.target);
    }
    hosts.forEach(function (h) { if (!h.isConnected) hosts.delete(h); else if (h.shadowRoot) shadow(h); });
    if (ready.done) grown();
    stats.ms += performance.now() - t0;
  }
  var mo = new MutationObserver(function (ms) {
    if (off) return;
    for (var i = 0; i < ms.length; i++) pending.push(ms[i]);
    schedule();
  });
  function start() {
    if (baseEl || off) return true;
    var root = document.documentElement;
    if (!root) return false;
    baseEl = base();
    (document.head || root).insertBefore(baseEl, (document.head || root).firstChild);
    if (!baseEl.sheet) {                          // refused by the page's policy
      csp = true;
      baseSheet = new CSSStyleSheet();
      baseSheet.replaceSync(baseEl.textContent);
      baseEl.remove();
      adopt(document, baseSheet);
    }
    mo.observe(document, OBS);
    return true;
  }
  if (!start()) {
    wait = new MutationObserver(function () { if (start()) wait.disconnect(); });
    wait.observe(document, { childList: true });
  }
  function ready() {
    if (off || ready.done) return;
    if (wait) wait.disconnect();
    start();
    if (isDarkAlready()) { stop(); return; }
    ready.done = true;
    var t0 = performance.now();
    // first in <head>: the page's own rules come after the defaults
    if (!csp && baseEl && baseEl.parentNode !== document.head && document.head) document.head.insertBefore(baseEl, document.head.firstChild);
    scanSheets(document);
    tree(document.documentElement);
    stats.ms += performance.now() - t0;
    // CSS-in-JS and components that start late: looked at again a few times
    [500, 1500, 4000].forEach(function (t) { setTimeout(function () { if (!off) { hosts.forEach(function (h) { if (h.shadowRoot) shadow(h); }); grown(true); } }, t); });
  }
  if (document.readyState !== 'loading' && document.body) ready();
  else document.addEventListener('DOMContentLoaded', ready, { once: true });
  window.addEventListener('load', function () { if (!off) grown(true); }, { once: true });
  window.__ikeDEStats = stats;           // isolated world only: for tests/dark_engine
})();
