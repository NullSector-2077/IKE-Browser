// I.K.E. Dark Engine (the page dark mode since 1.1.30; loaded by ike/darkengine.py). I.K.E.'s own
// dark mode for pages: one pass over the page's style sheets and inline styles,
// one generated override style sheet per source sheet, then only the nodes and
// sheets added later, in batches. No re-analysis of the whole page.
// Also: style sheets of other sites (fetched through I.K.E.'s page bridge),
// rules added by script (insertRule, adopted
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
  // dark.
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

  // The document's own methods and properties, taken from their prototypes when
  // the script starts: a page's named elements (<img name="querySelector">,
  // <form name="head">) override document properties of the same name in every
  // world, and must not be able to stop or mislead the engine.
  var DP = Document.prototype, SRP = window.ShadowRoot && ShadowRoot.prototype;
  function nativeOf(proto, name) {
    var d = Object.getOwnPropertyDescriptor(proto, name);
    return d && (d.get || d.value);
  }
  var _head = nativeOf(DP, 'head'), _body = nativeOf(DP, 'body'), _root = nativeOf(DP, 'documentElement');
  var _qs = DP.querySelector, _qsa = DP.querySelectorAll, _efp = DP.elementFromPoint;
  var _ready = nativeOf(DP, 'readyState'), _base = nativeOf(Node.prototype, 'baseURI'), _create = DP.createElement;
  var _listen = EventTarget.prototype.addEventListener, _design = nativeOf(DP, 'designMode');
  var _adoptDoc = Object.getOwnPropertyDescriptor(DP, 'adoptedStyleSheets');
  var _adoptSr = SRP && Object.getOwnPropertyDescriptor(SRP, 'adoptedStyleSheets');
  function dHead() { return _head.call(document); }
  function dBody() { return _body.call(document); }
  function dRoot() { return _root.call(document); }
  function dq(sel) { return _qs.call(document, sel); }
  function dqa(sel) { return _qsa.call(document, sel); }
  function dBase() { return _base.call(document); }
  function adoptedOf(root) {
    var d = root === document ? _adoptDoc : _adoptSr;
    return d ? d.get.call(root) : [];
  }
  function setAdopted(root, list) {
    var d = root === document ? _adoptDoc : _adoptSr;
    if (d) d.set.call(root, list);
  }
  function engine(siteFix) {
  // a frame of another site gets the common fix only, as in Dark Reader
  var sameSite = false;
  try { sameSite = window.top === window || (location.hostname || location.protocol) === topHost; } catch (e) {}
  var fix = (sameSite && siteFix) || __IKE_DE_COMMON__;
  function readable(sel) {
    if (!sel) return '';
    try { _qs.call(document, sel); return sel; } catch (e) {}
    return sel.split(',').filter(function (one) {
      try { _qs.call(document, one); return true; } catch (e) { return false; }
    }).join(',');
  }
  var ignoreInline = readable(fix.ignoreInline);

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
  // --- the look chosen in the Dark Engine's panel (darkengine.py LOOK) ----------
  // style: the hues of the dark background and of the light text; depth: how dark
  // the backgrounds are; text: how bright the text is; pictures: how much photos
  // and videos are dimmed (0: as they are); detect: sites dark already left alone
  var STYLES = {
    // dark: how dark the style's background is against the others (depth scales it)
    graphite: { bg: [200, 0.06], fg: [36, 0.098], link: [212, 1, 0.6], sel: [214, 1, 0.34], dark: 1 },
    midnight: { bg: [225, 0.12], fg: [220, 0.12], link: [210, 1, 0.66], sel: [222, 0.9, 0.36], dark: 0.6 },
    warm: { bg: [30, 0.14], fg: [38, 0.32], link: [32, 0.85, 0.62], sel: [28, 0.7, 0.32], dark: 1.05 },
    nordic: { bg: [220, 0.17], fg: [218, 0.27], link: [193, 0.43, 0.67], sel: [213, 0.32, 0.4], dark: 1.5 }
  };
  var LOOK = { style: 'graphite', depth: 50, text: 50, pictures: 0, detect: true };
  var K_BG = 1, K_FG = 1, LINK = '#3391ff', SELECTION = '#004daf', BGHEX = '#181a1b', FGHEX = '#e8e6e3', LB = 0.1, LF = 0.9;
  function hex(h, s, l) {
    var q = l < 0.5 ? l * (1 + s) : l + s - l * s, p = 2 * l - q;
    function ch(t) {
      t = ((t % 360) + 360) % 360 / 360;
      var v = t < 1 / 6 ? p + (q - p) * 6 * t : t < 1 / 2 ? q : t < 2 / 3 ? p + (q - p) * (2 / 3 - t) * 6 : p;
      return ('0' + Math.round(Math.max(0, Math.min(1, v)) * 255).toString(16)).slice(-2);
    }
    return '#' + ch(h + 120) + ch(h) + ch(h - 120);
  }
  function setLook(look) {
    look = look || {};
    var st = STYLES[look.style] ? look.style : 'graphite', num = function (v, d, lo, hi) {
      v = +v;
      return isFinite(v) ? Math.max(lo, Math.min(hi, v)) : d;
    };
    LOOK = { style: st, depth: num(look.depth, 50, 0, 100), text: num(look.text, 50, 0, 100),
      pictures: num(look.pictures, 0, 0, 60), detect: look.detect !== false };
    var S = STYLES[st];
    BG = [S.bg[0], S.bg[1], 0.1]; FG = [S.fg[0], S.fg[1], 0.9];
    // depth 0..100: the background pole from 17 % to 4 % lightness (50: 10 %, as Dark Reader)
    var lb = (LOOK.depth <= 50 ? 0.17 - LOOK.depth / 50 * 0.07 : 0.1 - (LOOK.depth - 50) / 50 * 0.06) * S.dark;
    // text 0..100: the text pole from 78 % to 98 % (50: 90 %)
    var lf = LOOK.text <= 50 ? 0.78 + LOOK.text / 50 * 0.12 : 0.9 + (LOOK.text - 50) / 50 * 0.08;
    K_BG = lb / 0.1; K_FG = lf / 0.9; LB = lb; LF = lf;
    BGHEX = hex(BG[0], BG[1], lb); FGHEX = hex(FG[0], FG[1], lf);
    LINK = hex(S.link[0], S.link[1], S.link[2]); SELECTION = hex(S.sel[0], S.sel[1], S.sel[2]);
    // the colours mapped with the previous look (not there yet at the start)
    if (cache) cache.clear();
    if (mapped) { mapped.bg.clear(); mapped.fg.clear(); mapped.border.clear(); }
    if (listMapped) { listMapped.bg.clear(); listMapped.fg.clear(); listMapped.border.clear(); }
  }
  setLook(siteFix && siteFix.look);
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
  // relative luminance of an hsl colour (h in degrees, s and l from 0 to 1)
  function hslLum(h, s, l) {
    var q = l < 0.5 ? l * (1 + s) : l + s - l * s, p = 2 * l - q;
    function ch(t) {
      t = ((t % 360) + 360) % 360 / 360;
      var v = t < 1 / 6 ? p + (q - p) * 6 * t : t < 1 / 2 ? q : t < 2 / 3 ? p + (q - p) * (2 / 3 - t) * 6 : p;
      return v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
    }
    return 0.2126 * ch(h + 120) + 0.7152 * ch(h) + 0.0722 * ch(h - 120);
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
      // a bright colour (orange, green, cyan) stays too light at that lightness for
      // the light text drawn on it (Hacker News' bar: 2.1:1 with Dark Reader):
      // darker until light text reads on it
      l = Math.min(1, l * K_BG);
      if (a >= 0.5 && s > 0.3) while (l > 0.05 && hslLum(h, s, l) > 0.1) l -= 0.02;
      return css(h, s, l, a);
    }
    if (kind === 'fg') {
      var lo = hsl[2] <= 0.5;
      l = lo ? 0.9 - (blue && s > 0.12 ? 0.6 : 0.7) * l : 0.9 - 0.7 * (1 - l);
      if (blue && s > 0.12) h = h <= 210 ? h - 3 : Math.min(222, 207 + (h - 210) * 0.37);
      if (s <= 0.12 || (hsl[2] < 0.25 && s < 0.6)) { h = FG[0]; s = FG[1]; }
      return css(h, s, Math.min(1, l * K_FG), a);
    }
    var light = l >= 0.5;
    l = 0.2 + (1 - l) * 0.3;
    // a faint dark line (rgba(0,0,0,.2)) would vanish on a dark page: it keeps standing out
    if (!light && a < 0.5) a = +(0.45 + a * 0.6).toFixed(2);
    if (s <= 0.12) { h = light ? BG[0] : FG[0]; s = light ? BG[1] : FG[1]; }
    return css(h, s, Math.min(1, l * (0.5 + K_BG / 2)), a);
  }
  var PROPS = [['background-color', 'bg'], ['color', 'fg'], ['border-top-color', 'border'],
    ['border-right-color', 'border'], ['border-bottom-color', 'border'], ['border-left-color', 'border'],
    ['outline-color', 'border'], ['fill', 'fg'], ['stroke', 'fg'], ['text-decoration-color', 'fg'],
    ['column-rule-color', 'border'], ['caret-color', 'fg'], ['-webkit-text-fill-color', 'fg'],
    ['border-block-start-color', 'border'], ['border-block-end-color', 'border'],
    ['border-inline-start-color', 'border'], ['border-inline-end-color', 'border'],
    ['-webkit-text-stroke-color', 'fg'], ['text-emphasis-color', 'fg'], ['stop-color', 'bg'], ['flood-color', 'bg']];
  // shorthands whose longhands read empty while they hold a var()
  var SHORT = [['background', 'bg'], ['border', 'border'], ['border-top', 'border'], ['border-right', 'border'],
    ['border-bottom', 'border'], ['border-left', 'border'], ['border-color', 'border'], ['outline', 'border'],
    ['border-block', 'border'], ['border-inline', 'border'], ['border-block-end', 'border'],
    ['border-block-start', 'border'], ['border-inline-start', 'border'], ['border-inline-end', 'border']];
  // the CSS colour names: in lists, gradients, shadows and fallbacks (never inside
  // a custom property's name, a file name or a function name)
  var NAMES = ('aliceblue antiquewhite aqua aquamarine azure beige bisque black blanchedalmond blue blueviolet ' +
    'brown burlywood cadetblue chartreuse chocolate coral cornflowerblue cornsilk crimson cyan darkblue darkcyan ' +
    'darkgoldenrod darkgray darkgreen darkgrey darkkhaki darkmagenta darkolivegreen darkorange darkorchid darkred ' +
    'darksalmon darkseagreen darkslateblue darkslategray darkslategrey darkturquoise darkviolet deeppink ' +
    'deepskyblue dimgray dimgrey dodgerblue firebrick floralwhite forestgreen fuchsia gainsboro ghostwhite gold ' +
    'goldenrod gray green greenyellow grey honeydew hotpink indianred indigo ivory khaki lavender lavenderblush ' +
    'lawngreen lemonchiffon lightblue lightcoral lightcyan lightgoldenrodyellow lightgray lightgreen lightgrey ' +
    'lightpink lightsalmon lightseagreen lightskyblue lightslategray lightslategrey lightsteelblue lightyellow lime ' +
    'limegreen linen magenta maroon mediumaquamarine mediumblue mediumorchid mediumpurple mediumseagreen ' +
    'mediumslateblue mediumspringgreen mediumturquoise mediumvioletred midnightblue mintcream mistyrose moccasin ' +
    'navajowhite navy oldlace olive olivedrab orange orangered orchid palegoldenrod palegreen paleturquoise ' +
    'palevioletred papayawhip peachpuff peru pink plum powderblue purple rebeccapurple red rosybrown royalblue ' +
    'saddlebrown salmon sandybrown seagreen seashell sienna silver skyblue slateblue slategray slategrey snow ' +
    'springgreen steelblue tan teal thistle tomato turquoise violet wheat white whitesmoke yellow yellowgreen').split(' ');
  var COLRE = new RegExp('#[0-9a-f]{3,8}\\b|rgba?\\([^)]*\\)|hsla?\\([^)]*\\)|(?:ok)?l(?:ab|ch)\\([^)]*\\)|hwb\\([^)]*\\)|(?<![\\w\\-./#])(?:' +
    NAMES.join('|') + ')(?![\\w\\-.(])', 'gi');
  var COLTEST = new RegExp(COLRE.source, 'i');
  var PRE = /color|background|border|outline|shadow|fill|stroke|--|caret/;
  var TRIPLE = /^\s*(\d{1,3})\s*[, ]\s*(\d{1,3})\s*[, ]\s*(\d{1,3})\s*$/;
  var HSL_TRIPLE = /^\s*(-?[\d.]+)(?:deg)?\s+([\d.]+)%\s+([\d.]+)%\s*$/;
  var COLOR_NAME = /colou?r|bg|background|foreground|text|border|fill|stroke|rgb|accent|primary|secondary|surface|muted|ring|shadow|link/i;
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
  // "hsla(...)" -> "r, g, b" (or "r g b": sep) for a variable used inside rgb()
  function rgbTriple(c, sep) {
    if (!ctx) ctx = new OffscreenCanvas(1, 1).getContext('2d', { willReadFrequently: true });
    ctx.fillStyle = c;
    var s = ctx.fillStyle, m;
    if (s[0] === '#') m = [parseInt(s.substr(1, 2), 16), parseInt(s.substr(3, 2), 16), parseInt(s.substr(5, 2), 16)];
    else m = s.match(/[\d.]+/g);
    return m[0] + (sep || ', ') + m[1] + (sep || ', ') + m[2];
  }
  // "hsla(h,s%,l%,a)" as written by css() -> "h s% l%" for a variable used inside hsl()
  function hslTriple(c) {
    var m = /hsla\(([\d.]+),([\d.]+)%,([\d.]+)%/.exec(c);
    return m ? m[1] + ' ' + m[2] + '% ' + m[3] + '%' : null;
  }
  // a colour whose alpha is a variable (Tailwind: rgb(255 255 255 / var(--tw-bg-opacity))):
  // its channels mapped, the alpha kept as written
  var ALPHA_VAR = /\b(rgba?|hsla?)\(\s*([^()\/,]+?(?:\s*,\s*[^()\/,]+?){0,2})\s*(?:\/|,)\s*(var\((?:[^()]|\([^()]*\))*\))\s*\)/gi;
  function alphaVars(v, kind) {
    return v.replace(ALPHA_VAR, function (m, fn, chans, alpha) {
      var c = parse(fn.replace(/a$/i, '') + '(' + chans + ')');
      if (!c) return m;
      return 'rgb(' + rgbTriple(mapColor([c[0], c[1], c[2], 1], kind), ' ') + ' / ' + alpha + ')';
    });
  }

  // --- custom properties: one definition per use (background, text, border) ---
  // --x keeps the background mapping; --ike-fg-x and --ike-bd-x hold the text
  // and border mappings, and a use in a text or border property is rewritten
  // to them (with --x as the fallback for a variable defined where we cannot read).
  var VK = { fg: 'fg', border: 'bd' };
  function useVars(v, kind) {
    if (v.indexOf('var(') < 0) return mapColors(v, kind);
    if (/(rgb|hsl)a?\(/i.test(v)) {
      var a = alphaVars(v, kind);
      if (a !== v) { v = a; if (v.indexOf('var(') < 0) return v; }
    }
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
    // channels of a colour (59 130 246, used as rgb(var(--c) / .5)); not 1 1 1 or 0 0 0
    // of a scale or a translation, unless the name says colour
    if (t && (+t[1] > 1 || +t[2] > 1 || +t[3] > 1 || COLOR_NAME.test(name))) {
      var cc = [+t[1], +t[2], +t[3], 1], sep = v.indexOf(',') >= 0 ? ', ' : ' ';
      return n + ':' + rgbTriple(mapColor(cc, 'bg'), sep) + ';--ike-fg-' + name + ':' + rgbTriple(mapColor(cc, 'fg'), sep) +
        ';--ike-bd-' + name + ':' + rgbTriple(mapColor(cc, 'border'), sep) + ';';
    }
    // hue, saturation and lightness (shadcn/ui: --background: 0 0% 100%, used as hsl(var(--background)))
    var hl = v.match(HSL_TRIPLE);
    if (hl) {
      var hc = parse('hsl(' + hl[1] + ',' + hl[2] + '%,' + hl[3] + '%)');
      if (hc) {
        var hb = hslTriple(mapColor([hc[0], hc[1], hc[2], 1], 'bg')), hf = hslTriple(mapColor([hc[0], hc[1], hc[2], 1], 'fg')),
          hd = hslTriple(mapColor([hc[0], hc[1], hc[2], 1], 'border'));
        if (hb && hf && hd) return n + ':' + hb + ';--ike-fg-' + name + ':' + hf + ';--ike-bd-' + name + ':' + hd + ';';
      }
    }
    // another variable, with a colour to use when that one is not defined
    // (--background-color: var(--theme-bg, #fff), a shop's widgets): the fallback
    // is mapped in all three, else an undefined theme leaves the light colour
    if (v.indexOf('var(') >= 0 && !/[;{}]/.test(v)) {
      var vb = useVars(v, 'bg');
      return (vb !== v ? n + ':' + vb + ';' : '') + '--ike-fg-' + name + ':' + useVars(v, 'fg') + ';--ike-bd-' + name + ':' + useVars(v, 'border') + ';';
    }
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
      // over the size in characters only the pictures that hold some are let go;
      // a picture left as it is keeps its verdict (kept), so that the page's next
      // pass does not load it again (a page with a few large darkened pictures and
      // many small icons made room, asked for the icons again, made room again...)
      for (var entry of pics) {
        var overCount = pics.size > pictureLimit, overChars = pictureChars > pictureCharLimit;
        if (!overCount && !overChars) break;
        if (!overCount && !entry[1].data) continue;
        if (entry[1].state === 'keep') remember(entry[0]);
        pics.delete(entry[0]);
        if (entry[1].data) pictureChars -= entry[1].data.length;
      }
      stats.pictureCacheEntries = pics.size;
      stats.pictureCacheChars = pictureChars;
    }, 0);
  }
  var kept = new Set(), KEPT = { state: 'keep', data: null, waiting: [] };
  function remember(url) {
    if (kept.size >= 20000) kept.clear();
    kept.add(url);
  }
  function picture(url, done) {
    var p = pics.get(url);
    if (!p && kept.has(url)) return KEPT;
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
    stats.pictures++;
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
        var darkIcon = clear > 256 && avg < 0.3 && sd < 0.15 && small; // a flat dark drawing on transparency
        var lightPanel = clear < 50 && avg > 0.75 && (small || sd < 0.08); // light texture or plain light area
        // a large light backdrop (text is drawn on it): Dark Reader hides it, here
        // it is made dark and keeps its details: a drawing inverted, a photo dimmed
        var drawing = /^data:image\/svg|\.svg(?:[?#]|$)/i.test(url);
        var lightBackdrop = !small && clear < 50 && avg > 0.7 && !/\.(gif|apng)(?:[?#]|$)/i.test(url);
        if (!(darkIcon || lightPanel || lightBackdrop) || w > 2048 || h > 2048) { end(null); return; }
        var cv = new OffscreenCanvas(w, h), c2 = cv.getContext('2d');
        c2.filter = lightBackdrop && !lightPanel && !drawing ? 'brightness(40%)' : 'invert(100%) hue-rotate(180deg)';
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
  var URL_RE = /url\(\s*(?:"((?:[^"\\]|\\.)*)"|'((?:[^'\\]|\\.)*)'|([^"')\s]+))\s*\)/g;
  function mapImage(v, base, again, skipPicture, gradKind) {
    gradKind = gradKind || 'bg';
    if (v.indexOf('url(') < 0) {
      return { value: v.indexOf('gradient') >= 0 ? mapColors(v, gradKind) : null, pending: false };
    }
    var changed = v.indexOf('gradient') >= 0, pending = false;
    var out = v.replace(URL_RE, function (m, dq, sq, bare) {
      var u = (dq !== undefined ? dq : sq !== undefined ? sq : bare).replace(/\\(.)/g, '$1');
      if (/^data:image\/svg|^data:/.test(u) && u.length > 4000) return m;
      var abs;
      try { abs = new URL(u, base || dBase()).href; } catch (e) { return m; }
      if (skipPicture) return 'url("' + abs.replace(/["\\]/g, '\\$&') + '")';
      // One pending layer is enough to trigger the next pass for this value.
      var p = picture(abs, pending ? null : again);
      if (p.state === 'wait') pending = true;
      if (p.state === 'dark') { changed = true; return 'url("' + p.data + '")'; }
      return 'url("' + abs.replace(/["\\]/g, '\\$&') + '")';
    });
    return { pending: pending, value: changed ? out.replace(
      /(linear|radial|conic|repeating-linear|repeating-radial)-gradient\((?:[^()]|\([^()]*\))*\)/g,
      function (g) { return mapColors(g, gradKind); }) : null };
  }

  var imageSources = new WeakMap();
  function clipsText(st) {
    return st.getPropertyValue('background-clip') === 'text' || st.getPropertyValue('-webkit-background-clip') === 'text';
  }
  // the gradients of a value, each mapped with its variables per use (the rest,
  // pictures and the variables between the layers, left as written)
  function mapGradients(v, kind) {
    var out = '', i = 0;
    for (;;) {
      var j = v.indexOf('gradient(', i);
      if (j < 0) return out + v.slice(i);
      var depth = 0, e = j + 8;
      for (; e < v.length; e++) { if (v[e] === '(') depth++; else if (v[e] === ')' && !--depth) break; }
      out += v.slice(i, j) + useVars(v.slice(j, e + 1), kind);
      i = e + 1;
    }
  }
  function background(st, value, mine, base, again, skipPicture) {
    var ours = mine && mine['background-image'] === value;
    var source = ours ? imageSources.get(st) : value;
    if (source && source.indexOf('var(') >= 0 && source.indexOf('gradient(') >= 0) {
      // a gradient next to a variable (linear-gradient(#fff, #fff), var(--picture)):
      // its colours are mapped, the variable left to its own definition
      imageSources.delete(st);
      var g = mapGradients(source, clipsText(st) ? 'fg' : 'bg');
      return g !== value ? g : null;
    }
    if (!source || source === 'none' || source.indexOf('var(') >= 0) {
      imageSources.delete(st);
      return null;
    }
    var mapped = mapImage(source, base, again, skipPicture, clipsText(st) ? 'fg' : 'bg');
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
        if (!mine || mine[n] !== v) {
          if (v.indexOf('url(') >= 0) {
            var pic = mapImage(v.trim(), base, again);
            if (pic.value) out.push([n, pic.value, st.getPropertyPriority(n)]);
          } else addText(defineVar(n, v), st.getPropertyPriority(n));
        }
        continue;
      }
      if (k) {
        v = st.getPropertyValue(n);
        if (!v) { shorts = true; continue; }
        if (mine && mine[n] === v) continue;
        if (v.indexOf('var(') >= 0) {
          var uv = useVars(v, k);
          if (uv !== v || keep) add(n, uv);                 // nothing to write when nothing changes
          continue;
        }
        var m = keepLight(n, v, st) ? null : mapValue(v, k);
        // other values are kept in an override sheet so that the cascade order stays
        // the page's, except the keywords that cannot lose a colour
        if (m) add(n, m);
        else if (keep && !KEYWORD.test(v)) add(n, v);
      } else if (n === 'background-image') {
        v = st.getPropertyValue(n);
        if (!v) { shorts = true; continue; }
        var nb = background(st, v, mine, base, again,
          fix.ignoreImage.length ? skipRuleImage(typeof selector === 'function' ? selector() : selector) : false);
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
        if (v && v.indexOf('var(') >= 0 && (!mine || mine[sn] !== v)) {
          var us = useVars(v, SHORT[i][1]);
          if (us !== v || keep) add(sn, us);
        }
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
    if (off) return;
    var mine = ruleWrote.get(r);
    if (!mine) { mine = {}; ruleWrote.set(r, mine); }
    var again = function () { if (calm(r)) quiet(function () { inRule(r, base); }); };
    var l = items(r.style, base, again, false, mine, function () { return r.selectorText || ''; });
    if (!l.length) return;
    var st = r.style;
    for (var i = 0; i < l.length; i++) {
      try { mine[l[i][0]] = writeProp(r, st, l[i][0], l[i][1], l[i][2]); } catch (e) {}
    }
    stats.rules++;
  }
  // a registered custom property (@property) gives its initial value where
  // nothing sets it: a page's light default would stay light (a band of a
  // shop's home page drawn with background: var(--background-color), the
  // colour only in @property's initial-value). Its mapped value is set with no
  // specificity at the root (inherited) or on every element (not inherited), so
  // any value the page sets itself, mapped where it is, still wins.
  var registeredDone = new WeakMap();
  function isPropertyRule(r) { return typeof r.inherits === 'boolean' && 'initialValue' in r && typeof r.name === 'string'; }
  function registered(r) {
    var sheet = baseSheet || (baseEl && baseEl.sheet);
    if (!sheet || !r.initialValue || r.name.indexOf('--') !== 0) return;
    var done = registeredDone.get(sheet);
    if (!done) registeredDone.set(sheet, done = new Set());
    if (done.has(r.name)) return;
    done.add(r.name);
    var d = defineVar(r.name, r.initialValue);
    if (d) try { sheet.insertRule((r.inherits ? ':where(:root)' : ':where(*)') + '{' + d + '}', sheet.cssRules.length); } catch (e) {}
  }
  function inPlace(list, base, from) {
    for (var i = from || 0; i < list.length; i++) {
      var r = list[i];
      if (r.style) {                                  // style, keyframe and nested declaration rules
        if (!ruleWrote.has(r)) inRule(r, base);
        if (r.cssRules && r.cssRules.length) inPlace(r.cssRules, base, 0);
      } else if (r.cssRules) {
        inPlace(r.cssRules, base, 0);
      } else if (r.styleSheet) {                     // @import
        try { inPlace(r.styleSheet.cssRules, r.styleSheet.href || base, 0); } catch (e) {}
      } else if (isPropertyRule(r)) {
        registered(r);
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
      } else if (isPropertyRule(r)) {
        registered(r);
      }
    }
  }

  // --- style sheets: one override sheet right after each source ----------------
  // Owner nodes are scanned for changes. Constructed sheets are looked up only
  // while adopted, so their records must not keep replaced sheets alive.
  var recs = new Map(), adoptedRecords = new WeakMap(), generatedStyles = new WeakSet();
  var stats = { sheets: 0, fetched: 0, rules: 0, ms: 0, batches: 0, looks: 0, looksMs: 0, pictures: 0,
    pictureCacheEntries: 0, pictureCacheChars: 0,
    shadowRoots: 0 };
  function own(el) { return generatedStyles.has(el); }
  // The first value of every property written into the page's own rules and
  // inline styles, so that it can be given back (a page that asks later not to be
  // darkened, a site that switches to its own dark theme): declaration ->
  // {owner, props: name -> [original value, its priority, value written last]}.
  // Declarations whose owner left the page are dropped when the map has grown.
  var undoMap = new Map(), pruneAt = 4000;
  function writeProp(owner, st, n, v, prio) {
    var rec = undoMap.get(st);
    if (!rec) {
      rec = { owner: owner, props: new Map() };
      undoMap.set(st, rec);
      if (undoMap.size > pruneAt) pruneUndo();
    }
    var p = rec.props.get(n), cur;
    if (!p) {
      cur = st.getPropertyValue(n);
      rec.props.set(n, p = [cur, cur ? prio || '' : '', null]);   // written with the original's priority
    } else if ((cur = st.getPropertyValue(n)) !== p[2]) {
      p[0] = cur;                               // the page wrote it since: that is the original now
      p[1] = cur ? prio || '' : '';
    }
    st.setProperty(n, v, prio || '');
    return (p[2] = st.getPropertyValue(n));
  }
  function gone(owner) {
    if (owner.nodeType === 1) return !owner.isConnected;
    var sheet = owner.parentStyleSheet;
    while (sheet && sheet.ownerRule) sheet = sheet.ownerRule.parentStyleSheet;
    return !sheet || (sheet.ownerNode ? !sheet.ownerNode.isConnected : false);
  }
  function pruneUndo() {
    undoMap.forEach(function (rec, st) { if (gone(rec.owner)) undoMap.delete(st); });
    pruneAt = Math.max(4000, undoMap.size * 2);
  }
  function undo() {
    undoMap.forEach(function (rec, st) {
      rec.props.forEach(function (p, n) {
        try {
          if (st.getPropertyValue(n) !== p[2]) return;         // the page has changed it since
          if (p[0]) st.setProperty(n, p[0], p[1]);
          else st.removeProperty(n);
        } catch (e) {}
      });
    });
    undoMap = new Map();
    // what was done is forgotten: a later start maps everything again
    ruleWrote = new WeakMap(); applied = new WeakMap(); wrote = new WeakMap();
    presentationSheets = new WeakMap(); editRules = {};
    recs.forEach(function (rec) { rec.n = -1; rec.last = null; });
    [document].concat(Array.from(roots)).forEach(function (root) {
      try {
        root.querySelectorAll('style.ike-de').forEach(function (el) { if (own(el)) el.remove(); });
        if (adoptedOf(root).some(function (x) { return x.__ikeDE; })) {
          setAdopted(root, adoptedOf(root).filter(function (x) { return !x.__ikeDE; }));
        }
      } catch (e) {}
    });
    dqa('.ike-de-lift').forEach(function (el) { el.classList.remove('ike-de-lift'); });
    dqa('.ike-de-halo').forEach(function (el) { el.classList.remove('ike-de-halo'); });
    haloDone = new WeakSet();
  }
  // --- text laid over a photo --------------------------------------------------
  // Photos are kept as they are, the text of the page is made light: a caption a
  // designer drew dark over a light photo (a shop's banner, a card) became light
  // on light. Text drawn over a large picture of the page gets a dark halo.
  var haloDone = new WeakSet(), haloTimer = 0;
  function halosLater() {
    if (haloTimer || off) return;
    haloTimer = setTimeout(function () { haloTimer = 0; if (ready.done) quiet(halos); }, 300);
  }
  // only the pictures near the window (the rest when the page is scrolled to
  // them), everything read first and the marks written once at the end, so
  // that the page is laid out once
  function halos() {
    if (off || !ready.done) return;
    var imgs = dqa('img'), far = innerHeight, marks = [];
    for (var i = 0; i < imgs.length; i++) {
      var img = imgs[i];
      if (haloDone.has(img) || !img.complete || !img.naturalWidth || img.naturalWidth < 100) continue;
      var r = img.getBoundingClientRect();
      if (r.bottom < -far || r.top > innerHeight + far) continue;
      haloDone.add(img);
      if (r.width < 120 || r.height < 80) continue;
      var box = img.parentElement;
      for (var up = 0; box && up < 4; up++, box = box.parentElement) {
        var br = box.getBoundingClientRect();
        if (br.width * br.height > r.width * r.height * 2.5) break;
        textsOver(box, img, r, marks);
      }
    }
    for (var m = 0; m < marks.length; m++) marks[m].classList.add('ike-de-halo');
  }
  addEventListener('scroll', halosLater, { passive: true, capture: true });
  function textsOver(box, img, r, marks) {
    var els = box.querySelectorAll('*'), k = 0;
    for (var j = 0; j < els.length && k < 60; j++) {
      var e = els[j];
      if (e === img || e.contains(img) || e.classList.contains('ike-de-halo')) continue;
      var words = false;
      for (var c = e.firstChild; c; c = c.nextSibling) if (c.nodeType === 3 && c.data.trim()) { words = true; break; }
      if (!words) continue;
      k++;
      var tr = e.getBoundingClientRect();
      var ox = Math.min(tr.right, r.right) - Math.max(tr.left, r.left), oy = Math.min(tr.bottom, r.bottom) - Math.max(tr.top, r.top);
      if (!tr.width || ox <= 0 || oy <= 0 || ox * oy < 0.5 * tr.width * tr.height) continue;
      var tc = parse(getComputedStyle(e).color);
      if (tc && lum(tc) >= 0.3 && marks.indexOf(e) < 0) marks.push(e);
    }
  }
  function makeStyle() {
    var style = _create.call(document, 'style');
    style.className = 'ike-de';
    generatedStyles.add(style);
    return style;
  }
  // a safety net: a sheet or a rule written again because a picture came back is
  // written again at most 40 times in 10 s (a page that keeps asking for the same
  // pictures cannot keep the engine busy; the next change of the page writes it)
  var calmCounts = new WeakMap();
  function calm(key) {
    var now = performance.now(), c = calmCounts.get(key);
    if (!c || now - c[0] > 10000) calmCounts.set(key, c = [now, 0]);
    return ++c[1] <= 40;
  }
  function write(rec, list, base) {
    var t0 = performance.now(), n = list.length, out = [];
    var again = function () { if (calm(rec)) { rec.n = -1; schedule(); } };
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
    grow(rec, list, sh.href || dBase());
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
      setAdopted(rec.root, adoptedOf(rec.root).filter(function (sheet) {
        return sheet !== rec.sheet;
      }));
      rec.root = null;
    }
  }
  // a style sheet of another site: its text comes by a plain fetch without cookies, else the
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
    var list = adoptedOf(root);
    if (!list || !list.length) return;
    for (var i = 0; i < list.length; i++) {
      var s = list[i];
      if (s.__ikeDE) continue;
      var rec = adoptedRecords.get(s);
      if (!rec) { rec = { n: -1, last: null }; adoptedRecords.set(s, rec); stats.sheets++; }
      grow(rec, s.cssRules, dBase());
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
      if (!value) return;
      // a large filled rectangle is the background of a chart or a drawing: mapped
      // as a background (its labels as text), written on the element itself
      if (p === 'fill' && largeShape(el)) {
        var bg = value.indexOf('var(') >= 0 ? useVars(value, 'bg') : mapValue(value, 'bg');
        var c0 = parse(getComputedStyle(el).fill), c1 = parse(value);
        if (bg && c0 && c1 && c0[0] === c1[0] && c0[1] === c1[1] && c0[2] === c1[2]) {
          var dn = wrote.get(el) || {};
          wrote.set(el, dn);
          dn.fill = writeProp(el, el.style, 'fill', bg, '');
        }
        return;
      }
      var color = value.indexOf('var(') >= 0 ? useVars(value, 'fg') : mapValue(value, 'fg');
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
      // a page that animates its colours would add rules without end: past a few
      // hundred colours the element gets its colour itself
      if (!record.keys.has(key) && record.keys.size >= 400) {
        var dk = wrote.get(el) || {};
        wrote.set(el, dk);
        dk[p] = writeProp(el, el.style, p, color, '');
        return;
      }
      if (!record.keys.has(key)) {
        var selector = '[' + p + '="' + CSS.escape(value) + '"]';
        var rule = ':where(svg' + selector + ',svg ' + selector + '){' + p + ':' + color + '}';
        // Keep presentation attributes at zero specificity, below author rules.
        record.sheet.insertRule(rule, record.sheet.cssRules.length);
        record.keys.add(key);
      }
    });
  }
  function largeShape(el) {
    if (el.localName !== 'rect') return false;
    var w = el.getAttribute('width') || '', h = el.getAttribute('height') || '';
    if (/%$/.test(w) || /%$/.test(h)) return true;
    return parseFloat(w) >= 120 && parseFloat(h) >= 40;
  }
  var editRules = {};
  function editRule(n) {
    if (editRules[n]) return;
    var sheet = baseSheet || (baseEl && baseEl.sheet);
    if (!sheet) return;
    try {
      sheet.insertRule('[style*="--ike-i-' + n + ':"]{' + n + ':var(--ike-i-' + n + ')!important}', sheet.cssRules.length);
      editRules[n] = true;
    } catch (e) {}
  }
  function seen(el) { return (el.getAttribute('style') || '') + '\u0001' + (el.getAttribute('bgcolor') || ''); }
  function inline(el) {
    if (off) return;
    var now = seen(el);
    if (ignoreInline && el.matches(ignoreInline)) { applied.set(el, now); return; }
    if (el.namespaceURI === SVGNS) svgPresentation(el);
    if (applied.get(el) === now) return;
    var st = el.style, attr = el.getAttribute('style');
    var done = wrote.get(el);
    if (!done) { done = {}; wrote.set(el, done); }
    // what the user writes (a mail being composed, an editor) keeps its own colours
    // in its markup: the dark colour goes into a property of ours, which a rule of
    // ours applies; the text sent or saved is the user's
    var editable = el.isContentEditable || _design.call(document) === 'on';
    var set = function (n, v, prio) {
      if (editable) { done['--ike-i-' + n] = writeProp(el, st, '--ike-i-' + n, v, ''); editRule(n); return; }
      done[n] = writeProp(el, st, n, v, prio);
    };
    if (attr && PRE.test(attr)) {
      var again = function () { if (calm(el)) { applied.delete(el); quiet(function () { inline(el); }); } };
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
          var nb = background(st, v, done, dBase(), again, skipElementImage(el));
          if (nb) set(n, nb);
        } else if ((n === 'box-shadow' || n === 'text-shadow') && v && v !== 'none' && v.indexOf('var(') < 0) {
          set(n, mapColors(v, 'bg'));
        } else if (n.charCodeAt(0) === 45 && n.charCodeAt(1) === 45 && n.indexOf('--ike-') !== 0 &&
                   v.indexOf('url(') >= 0) {
          var pic = mapImage(v.trim(), dBase(), again, skipElementImage(el));
          if (pic.value) set(n, pic.value, st.getPropertyPriority(n));
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
    var clear = 0, n = 0, lum = 0, sq = 0;
    for (var i = 0; i < d.length; i += 4) {
      if (d[i + 3] < 30) { clear++; continue; }
      n++;
      var y = (0.2126 * d[i] + 0.7152 * d[i + 1] + 0.0722 * d[i + 2]) / 255;
      lum += y; sq += y * y;
    }
    // a flat dark drawing on transparency (a logo, an icon); a round avatar or a
    // cut-out photo has corners as clear but many tones, and is left as it is
    var mean = n ? lum / n : 1, sdev = n ? Math.sqrt(Math.max(0, sq / n - mean * mean)) : 1;
    if (clear > 0.3 * 576 && n && mean < 0.3 && sdev < 0.15) img.classList.add('ike-de-lift');
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
    else if (e.shadowRoot || e.localName.indexOf('-') > 0) shadow(e);
  }
  function tree(root) {
    var l, i;
    if (root.nodeType === 1) {
      if (needsInline(root)) inline(root);
      visit(root);
      if (!root.firstElementChild) return;              // most added nodes: nothing below
    }
    l = root.querySelectorAll(SEL);
    for (i = 0; i < l.length; i++) { try { inline(l[i]); } catch (e) {} }
    l = root.querySelectorAll('*');
    for (i = 0; i < l.length; i++) { try { visit(l[i]); } catch (e) {} }
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
    var l = adoptedOf(root);
    if (l.indexOf(sheet) < 0) setAdopted(root, l.concat([sheet]));
  }
  function base() {
    var t = ':root{color-scheme:dark!important}' +
      (window === window.top ? 'html{background-color:' + BGHEX + '!important}' : '') +
      ':where(html,body){color:' + FGHEX + ';border-color:' + hex(FG[0], FG[1], 0.41) + '}' +
      ':where(input,textarea,select,button){color:' + FGHEX + '}:where(a:any-link){color:' + LINK + '}' +
      '::selection{background-color:' + SELECTION + '!important;color:' + FGHEX + '!important}' +
      (LOOK.pictures ? ':where(img,video):not(.ike-de-lift){filter:brightness(' + (100 - LOOK.pictures) + '%)}' : '');
    // one selector the engine cannot read would void the whole list: each is checked
    var inv = (fix.invert || []).filter(function (sel) {
      try { dq(sel); return true; } catch (e) { return false; }
    }).join(',');
    if (inv) t += inv + '{filter:invert(100%) hue-rotate(180deg)!important}';
    if (fix.css) {
      t += fix.css.replace(/var\(--darkreader-neutral-background\)/g, BGHEX)
        .replace(/var\(--darkreader-neutral-text\)/g, FGHEX)
        .replace(/var\(--darkreader-selection-background\)/g, SELECTION)
        .replace(/var\(--darkreader-selection-text\)/g, FGHEX)
        .replace(/([\w-]+)\s*:\s*\$\{([^}]+)\}/g, function (m, prop, col) {
          var c = parse(col.trim());
          var kind = /background|shadow/.test(prop) ? 'bg' : /border|outline/.test(prop) ? 'border' : 'fg';
          return prop + ':' + (c ? mapColor(c, kind) : col);
        });
    }
    // placeholders: Dark Reader's common fix halves their opacity, below 3:1 on dark fields
    t += '::placeholder{opacity:1!important;color:' + hex(FG[0], FG[1], LF * 0.72) + '}';
    // the engine's own dark controls draw a disabled button's text at about 2:1
    t += ':where(button,input,select,textarea):disabled{color:' + hex(FG[0], FG[1], LF * 0.78) + '}';
    // the engine's own dark button face is mid-grey: a page's grey button text on it is unreadable
    t += ':where(button,select,input[type=button],input[type=submit],input[type=reset]){background-color:' +
      hex(BG[0], BG[1], LB + 0.07) + '}';
    t += '.ike-de-lift{filter:invert(100%) hue-rotate(180deg)!important}';
    // text made light over a photo the engine keeps as it is: a dark halo keeps it readable
    t += '.ike-de-halo{text-shadow:0 0 2px rgba(0,0,0,.95),0 0 6px rgba(0,0,0,.7)!important}';
    var s = makeStyle();
    s.textContent = t;
    return s;
  }

  // --- a page that is dark already is left alone --------------------------------
  function darkPalette() {
    var theme = (dRoot().getAttribute('data-theme') || '').toLowerCase();
    if (theme !== 'dark' && (theme !== 'system' || !matchMedia('(prefers-color-scheme: dark)').matches)) {
      return false;
    }
    // Verify a declared palette against the author's canvas colors. Our
    // temporary cover and default foreground would otherwise bias the result.
    var sheet = baseSheet || (baseEl && baseEl.sheet);
    if (sheet) sheet.disabled = true;
    try {
      var root = getComputedStyle(dRoot());
      var body = dBody() ? getComputedStyle(dBody()) : root;
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
  // A page built dark without saying so: its own colours are looked at where the
  // reader sees them. 25 points of the window; at each, the background really
  // drawn there (the element's and its ancestors' colours, translucent ones
  // blended, down to the page's canvas). Dark when nearly every point is dark
  // and the text there reads light. Pictures do not count (a dark photo on a
  // light page is not a dark page). The engine's own cover is left out.
  function canvasColor() {
    var scheme = getComputedStyle(dRoot()).colorScheme || '';
    return /^\s*dark\b|only dark/.test(scheme) ? [18, 18, 18, 1] : [255, 255, 255, 1];
  }
  function drawnBackground(el, canvas) {
    var layers = [];
    for (var x = el; x && x.nodeType === 1; x = x.parentElement) {
      var c = parse(getComputedStyle(x).backgroundColor);
      if (c && c[3] > 0) {
        layers.push(c);
        if (c[3] >= 0.95) break;
      }
    }
    var out = layers.length && layers[layers.length - 1][3] >= 0.95 ? layers.pop() : canvas;
    for (var i = layers.length - 1; i >= 0; i--) {
      var l = layers[i];
      out = [l[0] * l[3] + out[0] * (1 - l[3]), l[1] * l[3] + out[1] * (1 - l[3]), l[2] * l[3] + out[2] * (1 - l[3]), 1];
    }
    return out;
  }
  function looksDark() {
    var t0 = performance.now();
    try { return looksDarkNow(); } finally { stats.looks++; stats.looksMs += performance.now() - t0; }
  }
  function looksDarkNow() {
    if (!dBody() || innerWidth < 8 || innerHeight < 8) return false;
    var sheet = baseSheet || (baseEl && baseEl.sheet);
    if (sheet) sheet.disabled = true;
    try {
      var canvas = canvasColor(), dark = 0, seen = 0, w = innerWidth, h = innerHeight;
      // a frame shows its parent through a transparent canvas: only an opaque one counts
      if (window !== window.top) {
        var own = drawnBackground(dBody(), [0, 0, 0, 0]);
        if (own[3] < 0.95) return false;
      }
      // three points first (the middle, the top, the left): two light ones and
      // the page cannot be dark at 85 % of the points
      var light = 0, quick = [[2, 2], [2, 0], [0, 2]];
      for (var q = 0; q < quick.length; q++) {
        var qe = _efp.call(document, (quick[q][0] + 0.5) * w / 5, (quick[q][1] + 0.5) * h / 5);
        if (qe && lum(drawnBackground(qe, canvas)) >= 0.2 && ++light >= 2) return false;
      }
      for (var iy = 0; iy < 5; iy++) {
        for (var ix = 0; ix < 5; ix++) {
          var el = _efp.call(document, (ix + 0.5) * w / 5, (iy + 0.5) * h / 5);
          if (!el || el.tagName === 'IMG' || el.tagName === 'VIDEO' || el.tagName === 'CANVAS') continue;
          var bg = drawnBackground(el, canvas), lb = lum(bg);
          seen++;
          if (lb >= 0.2) continue;
          var fg = parse(getComputedStyle(el).color);
          if (fg && fg[3] > 0.3 && contrast(fg, bg, lb) < 3) continue;     // dark text on dark: not a theme
          dark++;
        }
      }
      if (seen < 8 || dark < 0.85 * seen) return false;
      // a dark hero, splash or scrim filling the window over a light page is not a
      // dark page: the page's own background must be dark too, or the page no
      // taller than what is seen, all of it dark
      var bodyBg = drawnBackground(dBody(), canvas);
      if (lum(bodyBg) < 0.2) return true;
      var root = dRoot();
      return dark === seen && Math.max(root.scrollHeight, dBody().scrollHeight) <= h * 1.5;
    } catch (e) {
      return false;
    } finally {
      if (sheet) sheet.disabled = false;
    }
  }
  function isDarkAlready() {
    if (dq('meta[name="darkreader-lock"]')) return true;
    if (!LOOK.detect) return false;
    if (siteFix.chosen) return false;
    var m = dq('meta[name="color-scheme"]');
    if (m && /^\s*(?:only\s+dark|dark(?:\s+only)?)\s*$/i.test(m.content)) return true;
    var hint = fix.hint;
    if (!hint) return (window === window.top && darkPalette()) || looksDark();
    if (hint.noDarkTheme || (window !== window.top && !hint.iframe)) return false;
    if (hint.systemTheme && matchMedia('(prefers-color-scheme: dark)').matches) return true;
    if (!hint.target || !hint.match || !hint.match.length) return false;
    try {
      var target = dq(hint.target);
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
  // characterData: the text of a <style> changed in place (a framework that
  // rewrites its style element's text node): the sheet is a new one
  var OBS = { childList: true, subtree: true, attributes: true, characterData: true,
    attributeFilter: ['style', 'bgcolor', 'fill', 'stroke', 'href', 'rel', 'media', 'disabled'] };
  function stop() {
    off = true;
    queue = [];
    undo();
    coverSheet = coverRule = null;
    if (wait) wait.disconnect();
    mo.disconnect();
    if (baseEl) baseEl.remove();
    if (baseSheet) {
      setAdopted(document, adoptedOf(document).filter(function (sheet) {
        return sheet !== baseSheet;
      }));
    }
  }
  function waitForLightTheme() {
    stop();
    var preference = matchMedia('(prefers-color-scheme: dark)');
    var observer = new MutationObserver(check);

    function watch() {
      observer.disconnect();
      var root = dRoot();
      var meta = dq('meta[name="color-scheme"]');
      observer.observe(document, { childList: true });
      if (root) observer.observe(root, { childList: true, attributes: true, attributeFilter: ['data-theme', 'class', 'style'] });
      if (dBody()) observer.observe(dBody(), { attributes: true, attributeFilter: ['class', 'style', 'data-theme'] });
      if (dHead()) observer.observe(dHead(), { childList: true });
      if (meta) observer.observe(meta, { attributes: true, attributeFilter: ['content', 'name'] });
      if (!fix.hint || !fix.hint.target) return;
      var target;
      try { target = dq(fix.hint.target); } catch (e) { return; }
      if (target) {
        observer.observe(target, { attributes: true, childList: target === root || target === dHead() });
        for (var parent = target.parentElement; parent && parent !== root && parent !== dHead();
             parent = parent.parentElement) {
          observer.observe(parent, { childList: true });
        }
      }
    }

    function check() {
      if (!dRoot() || isDarkAlready()) { watch(); return; }
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
  function restart() {
    if (!off) return;
    baseEl = baseSheet = null;
    csp = off = false;
    ready.done = false;
    readyWait = 99;
    ready();
  }
  window.__ikeDELook = function (look) {
    if (!look || typeof look !== 'object' || printing) return false;
    setLook(look);
    if (!off) stop();
    restart();
    return true;
  };
  var printing = false;
  addEventListener('beforeprint', function () {
    if (off || !ready.done) return;
    printing = true;
    stop();
  });
  addEventListener('afterprint', function () {
    if (!printing) return;
    printing = false;
    restart();
  });
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
        if (ready.done && baseEl && !csp && !baseEl.isConnected && dHead()) dHead().insertBefore(baseEl, dHead().firstChild);
        if (ready.done && baseSheet && adoptedOf(document).indexOf(baseSheet) < 0) adopt(document, baseSheet);
        if (ready.done) grown();
      });
      trimPicturesLater();
      later();
    });
  }
  // rules a page inserts with insertRule change no node, so nothing tells us:
  // after a burst of changes the sheets' lengths are looked at again a few
  // times (0.3, 1.5, 5 and 15 s later), then not until the page changes again
  var LATER = [300, 1500, 5000, 15000], laterStep = 0, laterTimer = 0;
  function later() {
    if (laterTimer || off || laterStep >= LATER.length) return;
    laterTimer = setTimeout(function () { laterTimer = 0; laterStep++; schedule(); }, LATER[laterStep]);
  }
  // work done outside the observer: the page's changes still waiting are
  // handled first, the records of our own writes are dropped after
  function quiet(fn) {
    if (off) return;
    var t0 = performance.now();
    var waiting = mo.takeRecords();
    if (queue.length) { waiting = queue.concat(waiting); queue = []; }
    if (waiting.length) handle(waiting);
    if (off) return;                     // the page asked to be left alone meanwhile
    fn();
    mo.takeRecords();
    stats.ms += performance.now() - t0;
  }
  var touched = new Set();
  function handle(list) {
    stats.batches++;
    for (var i = 0; i < list.length; i++) {
      var m = list[i], t = m.target;
      if (!t.isConnected) continue;
      if (m.type === 'characterData') {
        var sp = t.parentNode;
        if (sp && sp.localName === 'style' && !own(sp)) { try { sheetOf(sp); } catch (e) {} }
        continue;
      }
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
          // a page that asks later not to be darkened (Dark Reader's lock) gets its colours back
          if (n.localName === 'meta' && n.getAttribute('name') === 'darkreader-lock') { stop(); return; }
          try { tree(n); } catch (e) {}
        }
      }
      if (t && t.localName === 'style' && !own(t)) { try { sheetOf(t); } catch (e) {} }
    }
    if (touched.size) {
      touched.forEach(function (el) { try { if (el.isConnected) inline(el); } catch (e) {} });
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
    if (laterStep) { laterStep = 0; clearTimeout(laterTimer); laterTimer = 0; }
    for (var i = 0; i < ms.length; i++) queue.push(ms[i]);
    if (queue.length > 20000) quiet(function () {});
    else schedule();
  });
  function start() {
    if (baseEl || off) return true;
    var root = dRoot();
    if (!root) return false;
    baseEl = base();
    (dHead() || root).insertBefore(baseEl, (dHead() || root).firstChild);
    if (!baseEl.sheet) {                          // refused by the page's policy
      csp = true;
      baseSheet = new CSSStyleSheet();
      baseSheet.replaceSync(baseEl.textContent);
      baseEl.remove();
      adopt(document, baseSheet);
    }
    // The body can paint while a parser-blocking resource is pending.
    // Cover its canvas background until the author declarations are mapped. In a
    // frame too (a page in a frame painted its own white until mapped: Speedometer's
    // pages, a shop's embedded parts); the cover goes as soon as the mapping starts,
    // and a frame meant to be transparent is transparent again from then on.
    coverSheet = baseSheet || baseEl.sheet;
    coverRule = coverSheet.cssRules[coverSheet.insertRule(window === window.top
      ? ':root:root > body{background-color:' + BGHEX + '!important;color:' + FGHEX + '}'
      : ':root:root, :root:root > body{background-color:' + BGHEX + '!important;color:' + FGHEX + '}', 0)];
    return true;
  }
  if (!start()) {
    wait = new MutationObserver(function () { if (start()) wait.disconnect(); });
    wait.observe(document, { childList: true });
  }
  // style sheets of the page still loading: the page is judged once they are
  // there (at most 1.5 s; the dark cover stays meanwhile)
  function sheetsPending() {
    var links = dqa('link[rel~="stylesheet"]');
    for (var i = 0; i < links.length; i++) {
      var l = links[i];
      if (!l.sheet && !l.disabled && (!l.media || matchMedia(l.media).matches) && !l.__ikeDEFailed) return l;
    }
    return null;
  }
  var readyWait = 0;
  _listen.call(document, 'error', function (e) {
    var t = e.target;
    if (t && t.localName === 'link') t.__ikeDEFailed = true;
  }, true);
  // begun while the page arrived: shadow roots attached by its scripts meanwhile
  // (on any element: no change of the document tells of them) are found now
  function lateRoots() {
    quiet(function () {
      var all = dqa('*');
      for (var i = 0; i < all.length; i++) {
        var sr = all[i].shadowRoot;
        if (sr && !roots.has(sr)) { try { shadow(all[i]); } catch (e) {} }
      }
    });
  }
  function ready() {
    if (ready.done && earlyDone && !lateRoots.done) { lateRoots.done = true; lateRoots(); }
    if (off || ready.done) return;
    var pend = sheetsPending();
    if (pend && readyWait < 15) {
      readyWait++;
      pend.addEventListener('error', function () { this.__ikeDEFailed = true; }, { once: true });
      setTimeout(ready, 100);
      return;
    }
    if (wait) wait.disconnect();
    start();
    if (isDarkAlready()) { waitForLightTheme(); return; }
    begin();
  }
  // The mapping of the page, from now on (at DOMContentLoaded, or earlier: see early())
  function begin() {
    if (off || ready.done) return;
    if (earlyWatch) { earlyWatch.disconnect(); earlyWatch = null; }
    ready.done = true;
    // Wait for the page's color-scheme metadata before rewriting author styles.
    mo.observe(document, OBS);
    var t0 = performance.now();
    // first in <head>: the page's own rules come after the defaults
    if (!csp && baseEl && baseEl.parentNode !== dHead() && dHead()) dHead().insertBefore(baseEl, dHead().firstChild);
    mo.takeRecords();
    queue = [];                          // the whole page is looked at now
    try {
      adopted(document);
      tree(dRoot());
    } finally {                          // the cover never stays, whatever the page holds
      try { if (coverSheet && coverSheet.cssRules[0] === coverRule) coverSheet.deleteRule(0); } catch (e) {}
      coverSheet = coverRule = null;
    }
    mo.takeRecords();
    stats.ms += performance.now() - t0;
    // CSS-in-JS and components that start late: looked at again a few times
    [500, 1500, 4000].forEach(function (t) { setTimeout(function () { quiet(function () { hosts.forEach(function (h) { if (h.shadowRoot) shadow(h); }); grown(true); halos(); }); }, t); });
    // pictures that arrive later (as the page is scrolled): their captions too
    _listen.call(document, 'load', function (e) { if (e.target && e.target.localName === 'img') halosLater(); }, true);
  }
  // --- an early start: the page is darkened while it arrives -----------------------
  // A page that comes slowly (a big shop) was drawn with its own light panels until
  // DOMContentLoaded: seconds of white. As soon as its <body> exists and its style
  // sheets are there, a page that is plainly light is darkened at once, and what
  // arrives after is handled as it comes. Anything that may say "dark already"
  // (Dark Reader's lock, a dark colour scheme, a dark theme marker, a hint of the
  // lists, a dark canvas or body) leaves the judgement to DOMContentLoaded, as before.
  var earlyWatch = null, earlyDone = false;
  function earlyLight() {
    if (dq('meta[name="darkreader-lock"]')) return false;
    var m = dq('meta[name="color-scheme"]');
    if (m && /dark/i.test(m.content || '')) return false;
    if (!LOOK.detect || siteFix.chosen) return true;
    if (fix.hint && !fix.hint.noDarkTheme) return false;
    var root = dRoot();
    if (/dark/i.test((root.getAttribute('data-theme') || '') + ' ' + (root.className && root.className.baseVal === undefined ? root.className : ''))) return false;
    var sheet = baseSheet || (baseEl && baseEl.sheet);
    if (sheet) sheet.disabled = true;
    try {
      return lum(drawnBackground(dBody(), canvasColor())) >= 0.2;
    } catch (e) {
      return false;
    } finally {
      if (sheet) sheet.disabled = false;
    }
  }
  function early() {
    if (off || ready.done || earlyDone || !dBody() || sheetsPending()) return;
    earlyDone = true;
    if (earlyWatch) { earlyWatch.disconnect(); earlyWatch = null; }
    if (earlyLight()) begin();
  }
  if (_ready.call(document) !== 'loading' && dBody()) ready();
  else {
    _listen.call(document, 'DOMContentLoaded', ready, { once: true });
    earlyWatch = new MutationObserver(early);
    earlyWatch.observe(document, { childList: true, subtree: true });
    _listen.call(document, 'load', function (e) {
      var t = e.target;
      if (t && t.localName === 'link' && !earlyDone) early();
    }, true);
  }
  window.addEventListener('load', function () { quiet(function () { grown(true); }); }, { once: true });
  window.__ikeDEStats = stats;           // isolated world only: for tests/dark_engine
  }
})();
