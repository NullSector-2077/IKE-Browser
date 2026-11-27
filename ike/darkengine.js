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
  // Installed for the whole profile, it does nothing on its own: a small script
  // per dark site (darkengine.py) registers that site's fix in
  // window.__ikeDECfg, and only a frame whose top site is registered is made
  // dark (as resources/darkmode.js does for Dark Reader).
  var reg = window.__ikeDECfg || (window.__ikeDECfg = {});
  var topHost = '';
  try {
    if (window.top === window) topHost = location.hostname || location.protocol;
    else if (location.ancestorOrigins && location.ancestorOrigins.length) {
      var topUrl = new URL(location.ancestorOrigins[location.ancestorOrigins.length - 1]);
      topHost = topUrl.hostname || topUrl.protocol;
    }
  } catch (e) {}
  if (!topHost) return;
  if (reg[topHost]) { engine(reg[topHost]); return; }
  window.__ikeDEGo = function (host) {
    if (host === topHost && reg[host]) { window.__ikeDEGo = null; engine(reg[host]); }
  };

  function engine(siteFix) {
  // a frame of another site gets the common fix only, as in Dark Reader
  var sameSite = false;
  try { sameSite = window.top === window || (location.hostname || location.protocol) === topHost; } catch (e) {}
  var fix = (sameSite && siteFix) || __IKE_DE_COMMON__;

  function matchesPattern(value, pattern, substring) {
    if (pattern[0] === '^') return value.startsWith(pattern.slice(1));
    if (pattern.endsWith('$')) return value.endsWith(pattern.slice(0, -1));
    return substring ? value.includes(pattern) : value === pattern;
  }
  function skipRuleImage(selector) {
    var ignored = fix.ignoreImage;
    if (!ignored.length) return false;
    var selectors = selector.split(/,\s*/);
    return ignored.some(function (p) {
      return p === '*' || selectors.some(function (s) { return matchesPattern(s, p, false); });
    });
  }
  function skipElementImage(el) {
    return fix.ignoreImage.some(function (s) {
      try { return el.matches(s); } catch (e) { return false; }
    });
  }

  // --- colours ---------------------------------------------------------------
  var BG = [200, 0.06, 0.1], FG = [36, 0.098, 0.9];       // hsl poles: #181a1b, #e8e6e3
  var ctx = null;
  var cache = new Map();
  var RGB = /^rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*(?:,\s*([\d.]+)\s*)?\)$/i, HEX = /^#([0-9a-f]{6}|[0-9a-f]{3})$/i;
  function parse(v) {                       // -> [r, g, b, a] or null
    var c = cache.get(v);
    if (c !== undefined) return c;
    c = null;
    var f = RGB.exec(v), h;
    if (f) c = [Math.min(255, +f[1]), Math.min(255, +f[2]), Math.min(255, +f[3]), f[4] === undefined ? 1 : Math.min(1, +f[4])];
    else if ((h = HEX.exec(v))) {
      h = h[1];
      if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
      c = [parseInt(h.substr(0, 2), 16), parseInt(h.substr(2, 2), 16), parseInt(h.substr(4, 2), 16), 1];
    } else if (!/^(inherit|initial|unset|revert|transparent)/i.test(v) &&
               !/\b(?:currentcolor\b|var\(|light-dark\()/i.test(v)) {
      if (!ctx) ctx = new OffscreenCanvas(1, 1).getContext('2d', { willReadFrequently: true });
      ctx.fillStyle = '#010203';
      ctx.fillStyle = v;
      var s = ctx.fillStyle;
      if (s !== '#010203' || /^#010203$/i.test(v)) {
        if (s[0] === '#') c = [parseInt(s.substr(1, 2), 16), parseInt(s.substr(3, 2), 16), parseInt(s.substr(5, 2), 16), 1];
        else if ((f = RGB.exec(s))) c = [+f[1], +f[2], +f[3], f[4] === undefined ? 1 : +f[4]];
        else {
          // Chromium can keep wide-gamut and perceptual CSS syntax in fillStyle.
          // Read the converted sRGB pixel instead of interpreting its components as RGB.
          ctx.clearRect(0, 0, 1, 1);
          ctx.fillRect(0, 0, 1, 1);
          var pixel = ctx.getImageData(0, 0, 1, 1).data;
          c = [pixel[0], pixel[1], pixel[2], pixel[3] / 255];
        }
      }
    }
    if (cache.size > 8000) cache.clear();
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
    // Low-opacity light strokes and washes already act as highlights over
    // dark surfaces. Darkening the RGB channels would erase them.
    if (kind !== 'fg' && a < 0.2 && l >= 0.6) return css(h, s, l, a);
    // Dark translucent controls and scrims already dim their backdrop.
    if (kind === 'bg' && a < 1 && l <= 0.25) return css(h, s, l, a);
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
  // the mappings of a value, kept by kind and text (pages repeat a few colours thousands of times)
  var mapped = { bg: new Map(), fg: new Map(), border: new Map() };
  var listMapped = { bg: new Map(), fg: new Map(), border: new Map() };
  function mapValue(v, kind) {
    var m = mapped[kind], r = m.get(v);
    if (r !== undefined) return r;
    var c = parse(v);
    r = c ? mapColor(c, kind) : null;
    if (m.size > 4000) m.clear();
    m.set(v, r);
    return r;
  }
  function mapColors(v, kind) {
    var m = listMapped[kind], r = m.get(v);
    if (r !== undefined) return r;
    r = v.replace(COLRE, function (x) { var c = parse(x); return c ? mapColor(c, kind) : x; });
    if (m.size > 4000) m.clear();
    m.set(v, r);
    return r;
  }
  function rgbTriple(c) {                   // "hsla(...)" -> "r, g, b" for a variable used inside rgba()
    if (!ctx) ctx = new OffscreenCanvas(1, 1).getContext('2d', { willReadFrequently: true });
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
  var pictureLimit = 256, pictureCharLimit = 4 * 1024 * 1024;
  var pictureChars = 0, pendingPictures = 0, pictureTrim = 0;
  var work = null;
  function trimPicturesLater() {
    if (pendingPictures || pictureTrim || (pics.size <= pictureLimit && pictureChars <= pictureCharLimit)) return;
    pictureTrim = setTimeout(function () {
      pictureTrim = 0;
      // Give declarations waiting for the next frame their completed layers.
      // The frame will request a trim again after it consumes them.
      if (pendingPictures || frame) return;
      for (var entry of pics) {
        if (pics.size <= pictureLimit && pictureChars <= pictureCharLimit) break;
        pics.delete(entry[0]);
        if (entry[1].data) pictureChars -= entry[1].data.length;
      }
      stats.pictureCacheEntries = pics.size;
      stats.pictureCacheChars = pictureChars;
    }, 0);
  }
  function picture(url, done) {
    var p = pics.get(url);
    if (p) {
      if (p.state === 'wait') {
        if (done) p.waiting.push(done);
      } else {
        pics.delete(url);
        pics.set(url, p);
      }
      return p;
    }
    p = { state: 'wait', data: null, waiting: done ? [done] : [] };
    pics.set(url, p);
    pendingPictures++;
    stats.pictureCacheEntries = pics.size;
    var img = new Image();
    img.crossOrigin = 'anonymous';          // no cross-origin credentials; non-CORS pictures stay as they are
    var end = function (data) {
      if (p.state !== 'wait') return;
      p.state = data ? 'dark' : 'keep';
      p.data = data;
      pendingPictures--;
      if (data) pictureChars += data.length;
      stats.pictureCacheChars = pictureChars;
      var w = p.waiting;
      p.waiting = [];
      for (var i = 0; i < w.length; i++) w[i]();
      trimPicturesLater();
    };
    img.onerror = function () { end(null); };
    img.onload = function () {
      try {
        var w = img.naturalWidth || 64, h = img.naturalHeight || 64;
        if (!work) work = new OffscreenCanvas(32, 32).getContext('2d', { willReadFrequently: true });
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
  function mapImage(v, base, again, skipPicture) {
    if (v.indexOf('url(') < 0) {
      return { value: v.indexOf('gradient') >= 0 ? mapColors(v, 'bg') : null, pending: false };
    }
    var changed = v.indexOf('gradient') >= 0, pending = false;
    var out = v.replace(/url\(\s*(["']?)([^"')]+)\1\s*\)/g, function (m, q, u) {
      if (/^data:image\/svg|^data:/.test(u) && u.length > 4000) return m;
      var abs;
      try { abs = new URL(u, base || document.baseURI).href; } catch (e) { return m; }
      if (skipPicture) return 'url("' + abs + '")';
      // One pending layer is enough to trigger the next pass for this value.
      var p = picture(abs, pending ? null : again);
      if (p.state === 'wait') pending = true;
      if (p.state === 'dark') { changed = true; return 'url("' + p.data + '")'; }
      return 'url("' + abs + '")';
    });
    return { pending: pending, value: changed ? out.replace(
      /(linear|radial|conic|repeating-linear|repeating-radial)-gradient\((?:[^()]|\([^()]*\))*\)/g,
      function (g) { return mapColors(g, 'bg'); }) : null };
  }

  var imageSources = new WeakMap();
  function background(st, value, mine, base, again, skipPicture) {
    var ours = mine && mine['background-image'] === value;
    var source = ours ? imageSources.get(st) : value;
    if (!source || source === 'none' || source.indexOf('var(') >= 0) {
      imageSources.delete(st);
      return null;
    }
    var mapped = mapImage(source, base, again, skipPicture);
    // Retain the author value only while asynchronous layers can still change
    // our output. A new value written by the page takes precedence.
    if (mine && mapped.pending) imageSources.set(st, source);
    else imageSources.delete(st);
    return mapped.value !== value ? mapped.value : null;
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
  // is written again with its variables per use. -> [[name, value, priority], ...]
  // keep: also the values that do not change (an override sheet keeps the
  // page's cascade order with them); mine: the values written into this
  // declaration before (never mapped twice)
  function items(st, base, again, keep, mine, selector) {
    var out = [], shorts = false, v;
    function add(n, val) { out.push([n, val, st.getPropertyPriority(n)]); }
    function addText(t, priority) {
      if (!t) return;
      t.split(';').forEach(function (pair) {
        var c = pair.indexOf(':');
        if (c > 0) out.push([pair.slice(0, c), pair.slice(c + 1), priority]);
      });
    }
    for (var j = 0; j < st.length; j++) {
      var n = st[j], k = KIND[n];
      if (n.charCodeAt(0) === 45 && n.charCodeAt(1) === 45) {
        v = st.getPropertyValue(n);
        if (!mine || mine[n] !== v) addText(defineVar(n, v), st.getPropertyPriority(n));
        continue;
      }
      if (k) {
        v = st.getPropertyValue(n);
        if (!v) { shorts = true; continue; }
        if (mine && mine[n] === v) continue;
        if (v.indexOf('var(') >= 0) { add(n, useVars(v, k)); continue; }
        var m = keepLight(n, v, st) ? null : mapValue(v, k);
        // other values are kept in an override sheet so that the cascade order stays
        // the page's, except the keywords that cannot lose a colour
        if (m) add(n, m);
        else if (keep && !KEYWORD.test(v)) add(n, v);
      } else if (n === 'background-image') {
        v = st.getPropertyValue(n);
        if (!v) { shorts = true; continue; }
        var nb = background(st, v, mine, base, again, skipRuleImage(selector));
        if (nb) add(n, nb);
      } else if (n === 'box-shadow' || n === 'text-shadow') {
        v = st.getPropertyValue(n);
        if (mine && mine[n] === v) continue;
        if (v && v !== 'none') {
          if (v.indexOf('var(') < 0) add(n, mapColors(v, 'bg'));
          else if (keep) add(n, v);
        }
      }
    }
    if (shorts) {
      for (var i = 0; i < SHORT.length; i++) {
        var sn = SHORT[i][0];
        v = st.getPropertyValue(sn);
        if (v && v.indexOf('var(') >= 0 && (!mine || mine[sn] !== v)) add(sn, useVars(v, SHORT[i][1]));
      }
    }
    if (!mine || (mine.color === undefined && mine['background-color'] === undefined)) guard(st, out);
    return out;
  }
  function decl(st, base, again, selector) {
    var l = items(st, base, again, true, null, selector), t = '';
    for (var i = 0; i < l.length; i++) t += l[i][0] + ':' + l[i][1] + (l[i][2] ? ' !important' : '') + ';';
    return t;
  }
  // a rule that gives both a text and a background colour (buttons, tabs, badges):
  // the text keeps at least 4.5:1 against that background once both are mapped
  function lum(c) {
    var f = function (v) { v /= 255; return v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]);
  }
  function contrast(fg, bg, bgLuminance) {
    var fgLuminance = lum(fg[3] === 1 ? fg : [
      fg[0] * fg[3] + bg[0] * (1 - fg[3]),
      fg[1] * fg[3] + bg[1] * (1 - fg[3]),
      fg[2] * fg[3] + bg[2] * (1 - fg[3])
    ]);
    return (Math.max(bgLuminance, fgLuminance) + 0.05) / (Math.min(bgLuminance, fgLuminance) + 0.05);
  }
  function guard(st, out) {
    var fv = st.getPropertyValue('color'), bv = st.getPropertyValue('background-color');
    var fc = fv && parse(fv), bc = bv && parse(bv);
    if (!fc || !bc || bc[3] < 0.5 || onPicture(st)) return;
    var fm = parse(mapColor(fc, 'fg')), bm = parse(mapColor(bc, 'bg'));
    if (!fm || !bm) return;
    var lb = lum(bm);
    if (contrast(fm, bm, lb) >= 4.5) return;
    var alpha = fm[3];
    var onWhite = contrast([255, 255, 255, alpha], bm, lb);
    var onBlack = contrast([0, 0, 0, alpha], bm, lb);
    // An intentionally faint color may never reach the target at its opacity.
    if (Math.max(onWhite, onBlack) < 4.5) return;
    var hsl = toHsl(fm[0], fm[1], fm[2]), up = onWhite >= onBlack, l = hsl[2];
    for (var i = 0; i < 20; i++) {
      l = up ? Math.min(1, l + 0.04) : Math.max(0, l - 0.04);
      var c = parse(css(hsl[0], hsl[1], l, alpha));
      if (contrast(c, bm, lb) >= 4.5) break;
    }
    out.push(['color', css(hsl[0], hsl[1], l, fm[3]), st.getPropertyPriority('color')]);
  }
  // the page's own rules, changed where they are (sheets the page can read: its
  // own site's, its <style> elements, the sheets it builds in script): no copy of
  // any selector, the cascade exactly the page's, nothing for the engine to match
  // twice. A rule is done once; the values written are remembered per rule.
  var ruleWrote = new WeakMap();
  function inRule(r, base) {
    var mine = ruleWrote.get(r);
    if (!mine) { mine = {}; ruleWrote.set(r, mine); }
    var again = function () { quiet(function () { inRule(r, base); }); };
    var l = items(r.style, base, again, false, mine, r.selectorText);
    if (!l.length) return;
    var st = r.style;
    for (var i = 0; i < l.length; i++) {
      try { st.setProperty(l[i][0], l[i][1], l[i][2]); } catch (e) {}
      mine[l[i][0]] = st.getPropertyValue(l[i][0]);
    }
    stats.rules++;
  }
  function inPlace(list, base, from) {
    for (var i = from || 0; i < list.length; i++) {
      var r = list[i];
      if (r.style && r.selectorText !== undefined) {
        if (!ruleWrote.has(r)) inRule(r, base);
        if (r.cssRules && r.cssRules.length) inPlace(r.cssRules, base, 0);
      } else if (r.cssRules) {
        inPlace(r.cssRules, base, 0);
      } else if (r.styleSheet) {                     // @import
        try { inPlace(r.styleSheet.cssRules, r.styleSheet.href || base, 0); } catch (e) {}
      }
    }
  }
  function rules(list, out, base, again) {
    for (var i = 0; i < list.length; i++) {
      var r = list[i];
      if (r.style && r.selectorText !== undefined) {
        var d = decl(r.style, base, again, r.selectorText);
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
  // Owner nodes are scanned for changes. Constructed sheets are looked up only
  // while adopted, so their records must not keep replaced sheets alive.
  var recs = new Map(), adoptedRecords = new WeakMap(), generatedStyles = new WeakSet();
  var stats = { sheets: 0, fetched: 0, rules: 0, ms: 0, pictureCacheEntries: 0, pictureCacheChars: 0,
    shadowRoots: 0 };
  function own(el) { return generatedStyles.has(el); }
  function makeStyle() {
    var style = document.createElement('style');
    style.className = 'ike-de';
    generatedStyles.add(style);
    return style;
  }
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
    var sh = node.sheet, href = node.href || '', rec = recs.get(node);
    if (!node.isConnected || !sh ||
        (sh.href && fix.ignoreSheet.some(function (p) { return matchesPattern(sh.href, p, true); }))) {
      if (rec) { detachOverride(rec); recs.delete(node); }
      return;
    }
    if (rec && (rec.sh !== sh || rec.href !== href)) {
      detachOverride(rec);
      // While a replacement link is loading Chrome can still expose the old sheet.
      if (rec.sh === sh) return;
      rec = null;
    }
    if (!rec) {
      rec = { n: -1, sh: sh, href: href };
      recs.set(node, rec);
      stats.sheets++;
    }
    var list;
    try { list = sh.cssRules; } catch (e) {
      // a sheet of another site: an override sheet made from its text
      if (!rec.el && !rec.sheet) {
        if (csp) rec.sheet = new CSSStyleSheet();
        else rec.el = makeStyle();
      }
      if (!rec.cs) { other(node, rec); return; }
      if (rec.n === -1) write(rec, rec.cs.cssRules, rec.base);
      put(node, rec);
      return;
    }
    grow(rec, list, sh.href || document.baseURI);
  }
  // rules added at the end (CSS-in-JS): only those; any other change: every rule not done yet
  function grow(rec, list, base) {
    var n = list.length;
    if (rec.n === n && (!n || list[n - 1] === rec.last)) return;
    var from = rec.n > 0 && n > rec.n && list[rec.n - 1] === rec.last ? rec.n : 0;
    inPlace(list, base, from);
    rec.n = n;
    rec.last = n ? list[n - 1] : null;
  }
  function put(node, rec) {
    var root = node.getRootNode();
    var media = rec.sh.media.mediaText;
    if (rec.el) {
      if (rec.el.media !== media) rec.el.media = media;
      if (node.nextSibling !== rec.el) node.parentNode.insertBefore(rec.el, node.nextSibling);
      if (rec.el.sheet) rec.el.sheet.disabled = rec.sh.disabled;
    } else {
      if (rec.root && rec.root !== root) detachOverride(rec);
      rec.sheet.media.mediaText = media;
      rec.sheet.disabled = rec.sh.disabled;
      adopt(root, rec.sheet);
      rec.root = root;
    }
  }
  function detachOverride(rec) {
    if (rec.el) rec.el.remove();
    if (rec.root) {
      rec.root.adoptedStyleSheets = rec.root.adoptedStyleSheets.filter(function (sheet) {
        return sheet !== rec.sheet;
      });
      rec.root = null;
    }
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
      if (off || !node.isConnected || recs.get(node) !== rec || node.href !== url ||
          node.sheet !== rec.sh) return;
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
  // sheets built in script (adoptedStyleSheets): changed in place too (one
  // sheet shared by many shadow roots is done once)
  function adopted(root) {
    var list = root.adoptedStyleSheets;
    if (!list || !list.length) return;
    for (var i = 0; i < list.length; i++) {
      var s = list[i];
      if (s.__ikeDE) continue;
      var rec = adoptedRecords.get(s);
      if (!rec) { rec = { n: -1, last: null }; adoptedRecords.set(s, rec); stats.sheets++; }
      grow(rec, s.cssRules, document.baseURI);
    }
  }
  // rules added through insertRule leave no trace in the document: the sheets
  // already known are looked at again (one length per sheet) with every batch
  // (shadow roots' adopted sheets only on the timers: components adopt theirs
  // before they are seen, and a page can hold thousands of roots)
  function grown(all) {
    recs.forEach(function (rec, owner) {
      var sh = owner.sheet, l;
      if (!owner.isConnected || sh !== rec.sh || (owner.href || '') !== rec.href || rec.cs) {
        sheetOf(owner);
        return;
      }
      if (rec.fetching) return;
      try { l = sh.cssRules; } catch (e) { return; }
      if (l.length !== rec.n || (l.length && l[l.length - 1] !== rec.last)) sheetOf(owner);
    });
    adopted(document);
    if (all) roots.forEach(function (r) { if (r.host.isConnected) adopted(r); });
  }
  var trackedLinks = new WeakSet();
  function trackLink(node) {
    if (trackedLinks.has(node) || !node.relList || !node.relList.contains('stylesheet')) return;
    trackedLinks.add(node);
    node.addEventListener('load', function () { quiet(sheetOf.bind(null, this)); });
  }

  // --- inline styles and colour attributes -----------------------------------
  // what was last seen of each element (its style and bgcolor attributes once
  // we had written), and the values we wrote per property: a change of the page
  // that touches no colour costs one string comparison and one test, and a value
  // we wrote is never mapped twice (a light text would drift darker each time)
  var applied = new WeakMap(), wrote = new WeakMap();
  var presentationSheets = new WeakMap();
  function svgPresentation(el) {
    if (!el.isConnected) return;
    var root = el.getRootNode();
    ['fill', 'stroke'].forEach(function (p) {
      var value = el.getAttribute(p);
      var color = value && mapValue(value, 'fg');
      if (!color) return;
      var record = presentationSheets.get(root);
      if (!record) {
        var sheet = root === document && (baseSheet || baseEl.sheet);
        if (!sheet) {
          var style = makeStyle();
          root.insertBefore(style, root.firstChild);
          sheet = style.sheet;
          if (!sheet) {
            style.remove();
            sheet = new CSSStyleSheet();
            adopt(root, sheet);
          }
        }
        record = { sheet: sheet, keys: new Set() };
        presentationSheets.set(root, record);
      }
      var key = p + ':' + value;
      if (!record.keys.has(key)) {
        var selector = '[' + p + '="' + CSS.escape(value) + '"]';
        var rule = ':where(svg' + selector + ',svg ' + selector + '){' + p + ':' + color + '}';
        // Keep presentation attributes at zero specificity, below author rules.
        record.sheet.insertRule(rule, record.sheet.cssRules.length);
        record.keys.add(key);
      }
    });
  }
  function seen(el) { return (el.getAttribute('style') || '') + '\u0001' + (el.getAttribute('bgcolor') || ''); }
  function inline(el) {
    var now = seen(el);
    if (fix.ignoreInline && fix.ignoreInline.length && el.matches(fix.ignoreInline)) { applied.set(el, now); return; }
    if (el.namespaceURI === SVGNS) svgPresentation(el);
    if (applied.get(el) === now) return;
    var st = el.style, attr = el.getAttribute('style');
    var done = wrote.get(el);
    if (!done) { done = {}; wrote.set(el, done); }
    var set = function (n, v, prio) {
      st.setProperty(n, v, prio || '');
      done[n] = st.getPropertyValue(n);
    };
    if (attr && PRE.test(attr)) {
      var again = function () { applied.delete(el); quiet(function () { inline(el); }); };
      var names = [], shorts = false;
      for (var i = 0; i < st.length; i++) names.push(st[i]);
      for (var q = 0; q < names.length; q++) {
        var n = names[q], k = KIND[n], v = st.getPropertyValue(n);
        if (v && done[n] === v && n !== 'background-image') continue;
        if (k) {
          if (!v) { shorts = true; continue; }
          if (keepLight(n, v, st)) continue;
          var m = v.indexOf('var(') >= 0 ? useVars(v, k) : mapValue(v, k);
          if (m && m !== v) set(n, m, st.getPropertyPriority(n));
        } else if (n === 'background-image') {
          if (!v) { shorts = true; continue; }
          var nb = background(st, v, done, document.baseURI, again, skipElementImage(el));
          if (nb) set(n, nb);
        } else if ((n === 'box-shadow' || n === 'text-shadow') && v && v !== 'none' && v.indexOf('var(') < 0) {
          set(n, mapColors(v, 'bg'));
        } else if (n.charCodeAt(0) === 45 && n.charCodeAt(1) === 45 && n.indexOf('--ike-') !== 0) {
          var d = defineVar(n, v);
          var priority = st.getPropertyPriority(n);
          if (d) d.split(';').forEach(function (pair) {
            var c = pair.indexOf(':');
            if (c > 0) set(pair.slice(0, c), pair.slice(c + 1), priority);
          });
        }
      }
      if (shorts) {
        for (var k2 = 0; k2 < SHORT.length; k2++) {
          var sn = SHORT[k2][0], sv = st.getPropertyValue(sn);
          if (sv && sv.indexOf('var(') >= 0 && done[sn] !== sv) { var nv = useVars(sv, SHORT[k2][1]); if (nv !== sv) set(sn, nv); }
        }
      }
    }
    var a = el.getAttribute('bgcolor');
    if (a) { var c = parse(a); if (c) set('background-color', mapColor(c, 'bg')); }
    if (el.localName === 'font' && el.getAttribute('color')) {
      var fc = parse(el.getAttribute('color'));
      if (fc) set('color', mapColor(fc, 'fg'));
    }
    applied.set(el, seen(el));
  }

  // --- pictures: recheck only when the element loads a different source ------
  var probe = null, imageSource = new WeakMap(), imageListeners = new WeakSet();
  function lookAt(img) {
    var src = img.currentSrc;
    if (!img.complete || !img.naturalWidth || !src || imageSource.get(img) === src) return;
    imageSource.set(img, src);
    img.classList.remove('ike-de-lift');
    if (skipElementImage(img) || img.naturalWidth * img.naturalHeight > 512 * 512 || /\.jpe?g($|\?)/i.test(src)) return;
    var d;
    try {
      if (!probe) probe = new OffscreenCanvas(24, 24).getContext('2d', { willReadFrequently: true });
      probe.clearRect(0, 0, 24, 24);
      probe.drawImage(img, 0, 0, 24, 24);
      d = probe.getImageData(0, 0, 24, 24).data;   // a picture of another site cannot be read here
    } catch (e) {
      // Clearing pixels does not restore origin cleanliness after a foreign image.
      probe = null;
      return;
    }
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
  var shadowRootsMayBeDetached = false;
  function pruneShadowRoots() {
    if (!shadowRootsMayBeDetached) return;
    shadowRootsMayBeDetached = false;
    var previous = roots.size;
    roots.forEach(function (root) { if (!root.host.isConnected) roots.delete(root); });
    if (roots.size === previous) return;
    stats.shadowRoots = roots.size;
    // An observer can only disconnect all targets. The surrounding quiet()
    // call has already delivered pending author records.
    mo.disconnect();
    mo.observe(document, OBS);
    roots.forEach(function (root) { mo.observe(root, OBS); });
  }
  function shadow(el) {
    var sr = el.shadowRoot;
    if (!sr) { hosts.add(el); return; }
    hosts.delete(el);
    if (roots.has(sr)) return;
    roots.add(sr);
    stats.shadowRoots = roots.size;
    mo.observe(sr, OBS);
    adopted(sr);
    tree(sr);
  }
  var SEL = '[style],[bgcolor],font[color],svg[fill],svg[stroke],svg [fill],svg [stroke]';
  var SVGNS = 'http://www.w3.org/2000/svg';
  function needsInline(e) {
    return e.hasAttribute('style') || (e.namespaceURI === SVGNS ? e.hasAttribute('fill') || e.hasAttribute('stroke')
      : e.hasAttribute('bgcolor') || (e.tagName === 'FONT' && e.hasAttribute('color')));
  }
  function visit(e) {
    if (e.localName === 'style') sheetOf(e);
    else if (e.localName === 'link') { trackLink(e); sheetOf(e); }
    else if (e.tagName === 'IMG') look(e);
    else if (e.localName.indexOf('-') > 0) shadow(e);
  }
  function tree(root) {
    var l, i;
    if (root.nodeType === 1) {
      if (needsInline(root)) inline(root);
      visit(root);
      if (!root.firstElementChild) return;              // most added nodes: nothing below
    }
    l = root.querySelectorAll(SEL);
    for (i = 0; i < l.length; i++) inline(l[i]);
    l = root.querySelectorAll('*');
    for (i = 0; i < l.length; i++) visit(l[i]);
  }
  function look(img) {
    if (!imageListeners.has(img)) {
      imageListeners.add(img);
      img.addEventListener('load', function () { lookAt(this); });
    }
    lookAt(img);
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
      (window === window.top ? 'html{background-color:#181a1b!important}' : '') +
      ':where(html,body){color:#e8e6e3;border-color:#736b5e}' +
      ':where(input,textarea,select,button){color:#e8e6e3}';
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
    var s = makeStyle();
    s.textContent = t;
    return s;
  }

  // --- a page that is dark already is left alone --------------------------------
  function darkPalette() {
    var theme = (document.documentElement.getAttribute('data-theme') || '').toLowerCase();
    if (theme !== 'dark' && (theme !== 'system' || !matchMedia('(prefers-color-scheme: dark)').matches)) {
      return false;
    }
    // Verify a declared palette against the author's canvas colors. Our
    // temporary cover and default foreground would otherwise bias the result.
    var sheet = baseSheet || (baseEl && baseEl.sheet);
    if (sheet) sheet.disabled = true;
    try {
      var root = getComputedStyle(document.documentElement);
      var body = document.body ? getComputedStyle(document.body) : root;
      var background = parse(body.backgroundColor);
      if (!background || background[3] < 0.95) background = parse(root.backgroundColor);
      var foreground = parse(body.color);
      if (!background || background[3] < 0.95 || !foreground) return false;
      var luminance = lum(background);
      return luminance < 0.18 && lum(foreground) > luminance && contrast(foreground, background, luminance) >= 4.5;
    } finally {
      if (sheet) sheet.disabled = false;
    }
  }
  function isDarkAlready() {
    if (siteFix.chosen) return false;
    var m = document.querySelector('meta[name="color-scheme"]');
    if (m && /^\s*(?:only\s+dark|dark(?:\s+only)?)\s*$/i.test(m.content)) return true;
    var hint = fix.hint;
    if (!hint) return window === window.top && darkPalette();
    if (hint.noDarkTheme || (window !== window.top && !hint.iframe)) return false;
    if (hint.systemTheme && matchMedia('(prefers-color-scheme: dark)').matches) return true;
    if (!hint.target || !hint.match || !hint.match.length) return false;
    try {
      var target = document.querySelector(hint.target);
      if (!target || !target.matches(hint.match.join(','))) return false;
      // Some sites advertise both palettes with data-theme="light dark".
      // A substring hint alone cannot distinguish the palette being shown.
      var themes = (target.getAttribute('data-theme') || '').toLowerCase().split(/\s+/);
      if (themes.includes('light') && themes.includes('dark')) {
        return matchMedia('(prefers-color-scheme: dark)').matches;
      }
      return true;
    } catch (e) { return false; }
  }

  // --- start, then only what is added ----------------------------------------
  var baseEl = null, coverSheet = null, coverRule = null;
  var off = false, pending = [], queued = false, wait = null;
  var OBS = { childList: true, subtree: true, attributes: true,
    attributeFilter: ['style', 'bgcolor', 'fill', 'stroke', 'href', 'rel', 'media', 'disabled'] };
  function stop() {
    off = true;
    queue = [];
    coverSheet = coverRule = null;
    if (wait) wait.disconnect();
    mo.disconnect();
    if (baseEl) baseEl.remove();
    if (baseSheet) {
      document.adoptedStyleSheets = document.adoptedStyleSheets.filter(function (sheet) {
        return sheet !== baseSheet;
      });
    }
  }
  function waitForLightTheme() {
    stop();
    var preference = matchMedia('(prefers-color-scheme: dark)');
    var observer = new MutationObserver(check);

    function watch() {
      observer.disconnect();
      var root = document.documentElement;
      var meta = document.querySelector('meta[name="color-scheme"]');
      observer.observe(document, { childList: true });
      if (root) observer.observe(root, { childList: true, attributes: true, attributeFilter: ['data-theme'] });
      if (document.head) observer.observe(document.head, { childList: true });
      if (meta) observer.observe(meta, { attributes: true, attributeFilter: ['content', 'name'] });
      if (!fix.hint || !fix.hint.target) return;
      var target;
      try { target = document.querySelector(fix.hint.target); } catch (e) { return; }
      if (target) {
        observer.observe(target, { attributes: true, childList: target === root || target === document.head });
        for (var parent = target.parentElement; parent && parent !== root && parent !== document.head;
             parent = parent.parentElement) {
          observer.observe(parent, { childList: true });
        }
      }
    }

    function check() {
      if (!document.documentElement || isDarkAlready()) { watch(); return; }
      observer.disconnect();
      preference.removeEventListener('change', check);
      // No author declarations were changed while the site used its theme.
      baseEl = baseSheet = null;
      csp = off = false;
      ready();
    }

    preference.addEventListener('change', check);
    watch();
  }
  // the sheets' lengths, the hosts still without a shadow root and the
  // pictures that came back are looked at once a frame (before it is drawn),
  // not with every batch of changes
  var frame = 0;
  function schedule() {
    if (frame || off) return;
    frame = requestAnimationFrame(function () {
      frame = 0;
      if (off) return;
      inFrame = true;
      setTimeout(function () { inFrame = false; }, 0);   // the next task comes after the frame is drawn
      quiet(function () {
        hosts.forEach(function (h) { if (!h.isConnected) hosts.delete(h); else if (h.shadowRoot) shadow(h); });
        pruneShadowRoots();
        if (ready.done) grown();
      });
      trimPicturesLater();
    });
  }
  // work done outside the observer: the page's changes still waiting are
  // handled first, the records of our own writes are dropped after
  function quiet(fn) {
    if (off) return;
    var t0 = performance.now();
    var waiting = mo.takeRecords();
    if (queue.length) { waiting = queue.concat(waiting); queue = []; }
    if (waiting.length) handle(waiting);
    fn();
    mo.takeRecords();
    stats.ms += performance.now() - t0;
  }
  var touched = new Set();
  function handle(list) {
    for (var i = 0; i < list.length; i++) {
      var m = list[i], t = m.target;
      if (!t.isConnected) continue;
      if (m.type === 'attributes') {
        if (t.localName === 'link') { trackLink(t); sheetOf(t); }
        else if (!own(t) && needsInline(t)) touched.add(t);
        continue;
      }
      {
        for (var k = 0; !shadowRootsMayBeDetached && roots.size && k < m.removedNodes.length; k++) {
          if (m.removedNodes[k].nodeType === 1 && !own(m.removedNodes[k])) shadowRootsMayBeDetached = true;
        }
        for (var j = 0; j < m.addedNodes.length; j++) {
          var n = m.addedNodes[j];
          if (n.nodeType !== 1 || !n.isConnected || own(n)) continue;
          tree(n);
        }
      }
      if (t && t.localName === 'style' && !own(t)) sheetOf(t);
    }
    if (touched.size) {
      touched.forEach(function (el) { if (el.isConnected) inline(el); });
      touched.clear();
    }
    schedule();
  }
  // The page's changes wait for the next frame and are handled then, before it
  // is drawn: a node added and taken away again in between costs nothing, and
  // many small changes are handled together. Changes made by the page's own
  // frame callbacks after ours (inFrame) are handled at once.
  var queue = [], inFrame = false;
  var mo = new MutationObserver(function (ms) {
    if (off) return;
    if (inFrame) {
      var t0 = performance.now();
      handle(ms);
      mo.takeRecords();                  // what we wrote ourselves (inline styles, our sheets)
      stats.ms += performance.now() - t0;
      return;
    }
    for (var i = 0; i < ms.length; i++) queue.push(ms[i]);
    if (queue.length > 20000) quiet(function () {});
    else schedule();
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
    // The body can paint while a parser-blocking resource is pending.
    // Cover its canvas background until the author declarations are mapped.
    if (window === window.top) {
      coverSheet = baseSheet || baseEl.sheet;
      coverRule = coverSheet.cssRules[coverSheet.insertRule(
        ':root:root > body{background-color:#181a1b!important}', 0)];
    }
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
    if (isDarkAlready()) { waitForLightTheme(); return; }
    ready.done = true;
    // Wait for the page's color-scheme metadata before rewriting author styles.
    mo.observe(document, OBS);
    var t0 = performance.now();
    // first in <head>: the page's own rules come after the defaults
    if (!csp && baseEl && baseEl.parentNode !== document.head && document.head) document.head.insertBefore(baseEl, document.head.firstChild);
    mo.takeRecords();
    queue = [];                          // the whole page is looked at now
    adopted(document);
    tree(document.documentElement);
    if (coverSheet && coverSheet.cssRules[0] === coverRule) coverSheet.deleteRule(0);
    coverSheet = coverRule = null;
    mo.takeRecords();
    stats.ms += performance.now() - t0;
    // CSS-in-JS and components that start late: looked at again a few times
    [500, 1500, 4000].forEach(function (t) { setTimeout(function () { quiet(function () { hosts.forEach(function (h) { if (h.shadowRoot) shadow(h); }); grown(true); }); }, t); });
  }
  if (document.readyState !== 'loading' && document.body) ready();
  else document.addEventListener('DOMContentLoaded', ready, { once: true });
  window.addEventListener('load', function () { quiet(function () { grown(true); }); }, { once: true });
  window.__ikeDEStats = stats;           // isolated world only: for tests/dark_engine
  }
})();
