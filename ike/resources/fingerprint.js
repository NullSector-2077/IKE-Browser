// I.K.E. fingerprinting protection. Runs in the page's main world before any
// page script, in every frame. __IKE_CFG__ is replaced at injection time.
//
// The protection is applied per "realm" (a window with its own set of built-in
// objects): the page itself, and every same-origin window the page can reach
// before the browser has injected this script there - brand new empty iframes
// and pop-ups, which would otherwise hand out the real, unprotected values.
// Inline (blob: and data:) workers get the same values through a prelude.
(function () {
  'use strict';
  var CFG = __IKE_CFG__;
  // lets instances recognise a protected realm; set below, per site (1.1.18)
  var SECRET = null;
  var origToString = Function.prototype.toString;
  // taken before any page script runs: a page that replaces call, bind or
  // Reflect.apply later cannot reach the protection's own calls (1.1.18)
  var CALL = Function.prototype.call, BIND = Function.prototype.bind, RAPPLY = Reflect.apply;
  // the number of frames of a window, from the engine's own getter: a page
  // writing window.length = 0 hid every new frame from the guard (1.1.18,
  // independent review; the same in 1.1.17)
  var LENGTH = (function () {
    var d = Object.getOwnPropertyDescriptor(window, 'length');
    return d && d.get;
  })();
  function framesOf(win) {
    try { return LENGTH ? RAPPLY(LENGTH, win, []) : win.length; } catch (e) { return 0; }
  }
  // the guards of the documents protected by this script, so that one
  // realm's document.open/write on another realm's document re-arms the
  // right watch (1.1.18, independent review)
  var GUARDS = new WeakMap();

  // The site the user is visiting (not the frame's own), so every frame of a
  // page shares the same protection level and the same noise.
  var host = location.hostname;
  try {
    var ao = location.ancestorOrigins;
    if (ao && ao.length) host = new URL(ao[ao.length - 1]).hostname || host;
  } catch (e) {}
  if (!host) { try { host = window.top.location.hostname || host; } catch (e) {} }

  function levelFor(h) {
    while (h) {
      if (Object.prototype.hasOwnProperty.call(CFG.sites, h)) return CFG.sites[h];
      var i = h.indexOf('.');
      if (i < 0) break;
      h = h.slice(i + 1);
    }
    return CFG.level;
  }
  // The frames of a payment service inside a shop (PayPal, Stripe) are left
  // exactly as they are: their anti-fraud checks refuse changed values (1.1.14).
  if (window.top !== window) {
    var me = location.hostname;
    if ((CFG.payframes || []).some(function (s) {
      return me === s || me.slice(-(s.length + 1)) === '.' + s;
    })) return;
  }
  // Google's sign-in refuses embedded Chromium engines: present the same
  // Firefox identity that is sent in the request header.
  // Not when the page around it is left alone (shield off there, or a
  // sensitive Google service: 1.1.14), as the request header is not changed either.
  if (CFG.ffua && location.hostname === 'accounts.google.com' && levelFor(host) !== 'off') {
    try {
      var np = Navigator.prototype;
      var ffv = { userAgent: CFG.ffua, appVersion: CFG.ffAppVersion || '5.0 (X11)', vendor: '',
        productSub: '20100101', userAgentData: undefined, oscpu: CFG.ffOscpu || 'Linux x86_64',
        buildID: '20181001000000' };
      Object.keys(ffv).forEach(function (k) {
        Object.defineProperty(np, k, { get: function () { return ffv[k]; }, configurable: true });
      });
      try { delete window.chrome; } catch (e) {}
    } catch (e) {}
  }
  var RANK = { off: 0, compatibility: 1, balanced: 2, strict: 3, maximum: 4 };
  var lv = RANK[levelFor(host)];
  if (lv === undefined) lv = 2;
  if (lv === 0) return;
  (function () {      // fingerprint protection switched off for this site only
    var h = host, list = CFG.nofp || [];
    while (h) {
      if (list.indexOf(h) >= 0) { lv = Math.min(lv, 1); return; }
      var i = h.indexOf('.');
      if (i < 0) return;
      h = h.slice(i + 1);
    }
  })();
  // Global Privacy Control is the only page-visible change in Compatibility.
  if (CFG.gpc && lv < 2) {
    try {
      Object.defineProperty(Navigator.prototype, 'globalPrivacyControl', {
        get: function () { return true; }, configurable: true, enumerable: true
      });
    } catch (e) {}
  }
  if (lv < 2) return;
  var strict = lv >= 3;
  var maximum = lv >= 4;

  // ---- seed: random per browser session, different for every site ----------
  function hash(str) {
    var h = 2166136261 >>> 0;
    for (var i = 0; i < str.length; i++) {
      h ^= str.charCodeAt(i);
      h = Math.imul(h, 16777619) >>> 0;
    }
    return h;
  }
  // Registrable domain ("bbc.co.uk", not "co.uk"), so unrelated sites never
  // share a seed.
  var SLD = { co: 1, com: 1, org: 1, net: 1, gov: 1, edu: 1, ac: 1, or: 1, ne: 1, go: 1, gob: 1,
    nom: 1, mil: 1, ltd: 1, plc: 1, sch: 1, nhs: 1, me: 1, info: 1, id: 1, gv: 1 };
  var HOSTED = /\.(github\.io|gitlab\.io|blogspot\.com|herokuapp\.com|pages\.dev|workers\.dev|netlify\.app|vercel\.app|web\.app|firebaseapp\.com|appspot\.com|cloudfront\.net|azurewebsites\.net|onrender\.com|neocities\.org)$/;
  function siteOf(h) {
    if (!h || /^[\d.]+$/.test(h) || h.indexOf(':') >= 0) return h;
    var p = h.split('.');
    if (p.length <= 2) return h;
    var three = HOSTED.test(h) || (p[p.length - 1].length === 2 && SLD[p[p.length - 2]] === 1);
    return p.slice(three ? -3 : -2).join('.');
  }
  // SHA-256, for the values derived from the session's key (1.1.18,
  // independent review): the key itself never reaches anything a page can
  // call or read, and what a page can learn on one site (its noise, the
  // marker of protected realms) tells nothing about another site. Until
  // 1.1.18 the marker was the session's key itself, the same on every site
  // (a page could read it), and the seed a plain FNV hash a page could undo.
  function sha256(text) {
    var H = [], K = [], n = 0, i, j;
    for (var c = 2; n < 64; c++) {
      for (j = 2; j * j <= c && c % j; j++) {}
      if (j * j > c) {
        if (n < 8) H[n] = (Math.pow(c, 1 / 2) * 4294967296) | 0;
        K[n++] = (Math.pow(c, 1 / 3) * 4294967296) | 0;
      }
    }
    var bytes = [];
    for (i = 0; i < text.length; i++) {
      var code = text.charCodeAt(i);
      if (code > 127) code = 63;                        // host names are ASCII (punycode)
      bytes.push(code);
    }
    var bits = bytes.length * 8;
    bytes.push(128);
    while (bytes.length % 64 !== 56) bytes.push(0);
    for (i = 7; i >= 0; i--) bytes.push(i > 3 ? 0 : (bits >>> (i * 8)) & 255);
    function rot(v, k) { return (v >>> k) | (v << (32 - k)); }
    for (var o = 0; o < bytes.length; o += 64) {
      var W = [];
      for (i = 0; i < 16; i++) {
        W[i] = (bytes[o + 4 * i] << 24) | (bytes[o + 4 * i + 1] << 16) | (bytes[o + 4 * i + 2] << 8) | bytes[o + 4 * i + 3];
      }
      for (i = 16; i < 64; i++) {
        var s0 = rot(W[i - 15], 7) ^ rot(W[i - 15], 18) ^ (W[i - 15] >>> 3);
        var s1 = rot(W[i - 2], 17) ^ rot(W[i - 2], 19) ^ (W[i - 2] >>> 10);
        W[i] = (W[i - 16] + s0 + W[i - 7] + s1) | 0;
      }
      var a = H[0], b = H[1], cc = H[2], d = H[3], e = H[4], f = H[5], g = H[6], h = H[7];
      for (i = 0; i < 64; i++) {
        var t1 = (h + (rot(e, 6) ^ rot(e, 11) ^ rot(e, 25)) + ((e & f) ^ (~e & g)) + K[i] + W[i]) | 0;
        var t2 = ((rot(a, 2) ^ rot(a, 13) ^ rot(a, 22)) + ((a & b) ^ (a & cc) ^ (b & cc))) | 0;
        h = g; g = f; f = e; e = (d + t1) | 0; d = cc; cc = b; b = a; a = (t1 + t2) | 0;
      }
      H[0] = (H[0] + a) | 0; H[1] = (H[1] + b) | 0; H[2] = (H[2] + cc) | 0; H[3] = (H[3] + d) | 0;
      H[4] = (H[4] + e) | 0; H[5] = (H[5] + f) | 0; H[6] = (H[6] + g) | 0; H[7] = (H[7] + h) | 0;
    }
    var out = '';
    for (i = 0; i < 8; i++) out += ('00000000' + (H[i] >>> 0).toString(16)).slice(-8);
    return out;
  }
  var SITE_KEY = sha256(CFG.key + '|' + siteOf(host));
  CFG.key = null;                                       // not kept once used
  SECRET = 'ike:' + sha256('realm|' + SITE_KEY).slice(0, 32);
  var seed = parseInt(SITE_KEY.slice(0, 8), 16) || 1;
  function rng(s) {
    var x = s || 1;
    return function () {
      x ^= x << 13; x >>>= 0;
      x ^= x >>> 17;
      x ^= x << 5; x >>>= 0;
      return x;
    };
  }
  // Invisible noise, always the same for one site in one session.
  function farble(data, seed, rng) {
    var next = rng(seed ^ data.length);
    var n = data.length;
    var step = n > 400000 ? 4 * Math.ceil(n / 400000) : 4;
    for (var i = 0; i < n; i += step) {
      var r = next();
      if ((r & 7) === 0 && data[i + 3] !== 0) {
        var c = i + (r >>> 3) % 3;
        data[c] = data[c] ^ 1;
      }
    }
  }
  // ---- values shared by every realm and by workers ---------------------------
  var realCores = navigator.hardwareConcurrency || 4;
  // A usual number of cores, chosen per site (Strict never goes above 8).
  var usual = (strict ? [2, 4, 6, 8] : [2, 4, 6, 8, 12, 16]).filter(function (n) { return n <= realCores; });
  var cores = usual.length ? usual[seed % usual.length] : realCores;
  // ---- graphics card (1.1.18) --------------------------------------------------
  // Balanced: each site gets one of a few models that are common on Linux,
  // written exactly as Chrome reports them there (vendor, renderer, and what
  // WebGPU says of the same card), a different one in every session. Only
  // models whose real name carries no driver version: Intel cards on Mesa and
  // NVIDIA cards on NVIDIA's driver. AMD cards are left out on purpose: on
  // Linux their name always carries the LLVM and DRM versions, which made
  // each such name very rare (seen in Cover Your Tracks). A fixed value of
  // our own would mark I.K.E.'s users; the real one marks the computer.
  // Strict and Maximum: no name at all. The WEBGL_debug_renderer_info
  // extension, the only source of the vendor and renderer pair, is hidden in
  // every frame and worker, and WebGPU is not offered.
  var DEBUG_GPU_EXTENSION = 'webgl_debug_renderer_info';
  var GPUS = [
    ['Google Inc. (Intel)', 'ANGLE (Intel, Mesa Intel(R) UHD Graphics 620 (KBL GT2), OpenGL 4.6)', 'intel', 'gen-9'],
    ['Google Inc. (Intel)', 'ANGLE (Intel, Mesa Intel(R) UHD Graphics 630 (CFL GT2), OpenGL 4.6)', 'intel', 'gen-9'],
    ['Google Inc. (Intel)', 'ANGLE (Intel, Mesa Intel(R) HD Graphics 520 (SKL GT2), OpenGL 4.6)', 'intel', 'gen-9'],
    ['Google Inc. (Intel)', 'ANGLE (Intel, Mesa Intel(R) Xe Graphics (TGL GT2), OpenGL 4.6)', 'intel', 'gen-12lp'],
    ['Google Inc. (Intel)', 'ANGLE (Intel, Mesa Intel(R) Graphics (ADL GT2), OpenGL 4.6)', 'intel', 'gen-12lp'],
    ['Google Inc. (NVIDIA Corporation)', 'ANGLE (NVIDIA Corporation, NVIDIA GeForce GTX 1650/PCIe/SSE2, OpenGL 4.5.0)', 'nvidia', 'turing'],
    ['Google Inc. (NVIDIA Corporation)', 'ANGLE (NVIDIA Corporation, NVIDIA GeForce GTX 1060 6GB/PCIe/SSE2, OpenGL 4.5.0)', 'nvidia', 'pascal'],
    ['Google Inc. (NVIDIA Corporation)', 'ANGLE (NVIDIA Corporation, NVIDIA GeForce RTX 3060/PCIe/SSE2, OpenGL 4.5.0)', 'nvidia', 'ampere']
  ];
  var PICK = seed >>> 7;
  // The model for this site among those of the real card's maker (1.1.18):
  // the limits and extensions WebGL and WebGPU report depend on the maker, so
  // an Intel name over an NVIDIA card's limits would be a contradiction a
  // script can see. The maker is no secret: those limits tell it anyway.
  // Cards of other makers (AMD, software renderers) get one of all the models.
  // Pure: it also runs inside workers (passed in the prelude).
  function gpuFor(real, gpus, pick) {
    var s = String(real || '').toLowerCase();
    var f = s.indexOf('nvidia') >= 0 ? 'nvidia' : (s.indexOf('intel') >= 0 ? 'intel' : '');
    var pool = f ? gpus.filter(function (g) { return g[2] === f; }) : gpus;
    return pool[pick % pool.length];
  }
  // Optional WebGL extensions that pages rarely use: a different subset is
  // hidden on every site, so the extension list is no stable identifier.
  var EXT_POOL = ['ext_clip_control', 'ext_depth_clamp', 'ext_polygon_offset_clamp',
    'ext_texture_mirror_clamp_to_edge', 'ext_texture_norm16', 'khr_parallel_shader_compile',
    'webgl_clip_cull_distance', 'webgl_polygon_mode', 'webgl_provoking_vertex',
    'webgl_blend_func_extended', 'ext_conservative_depth', 'nv_shader_noperspective_interpolation',
    'oes_sample_variables', 'oes_shader_multisample_interpolation', 'ext_render_snorm',
    'webgl_render_shared_exponent', 'webgl_stencil_texturing', 'ext_disjoint_timer_query',
    'ext_disjoint_timer_query_webgl2', 'webgl_multi_draw'];
  var hiddenExt = {};
  // a well-mixed bit per name (FNV's lowest bit is only the parity of the
  // text's characters: nearly the same list everywhere until 1.1.18)
  EXT_POOL.forEach(function (name) { if ((hash(seed + '|' + name) >>> 16) & 1) hiddenExt[name] = 1; });
  if (strict) hiddenExt[DEBUG_GPU_EXTENSION] = 1;      // no name of the card at all
  var langs = null;
  if (maximum) langs = ['en-US', 'en'];
  else if (strict) {
    var real = navigator.languages;
    langs = real && real.length ? [real[0]] : null;
  }
  var audioFactor = 1 + ((seed % 2000) - 1000) / 10000000;
  var textDelta = ((seed % 7) - 3) / 100000;
  var SCREENS = [[1280, 720], [1366, 768], [1440, 900], [1536, 864], [1600, 900], [1680, 1050],
    [1920, 1080], [1920, 1200], [2560, 1080], [2560, 1440], [3440, 1440], [3840, 2160]];
  function usualScreen(w, h) {
    for (var i = 0; i < SCREENS.length; i++) {
      if (SCREENS[i][0] >= w && SCREENS[i][1] >= h) return SCREENS[i];
    }
    return [w, h];
  }

  // ---- plugins ------------------------------------------------------------
  function word(next, len) {
    var a = 'bcdfghjklmnprstvwz', b = 'aeiou', out = '';
    for (var i = 0; i < len; i++) { var s = i % 2 ? b : a; out += s.charAt(next() % s.length); }
    return out.charAt(0).toUpperCase() + out.slice(1);
  }
  function pluginList(w, real) {
    var next = rng(seed ^ 0x51ed27), fakes = [], n = real.length;
    var proto = w.Plugin ? w.Plugin.prototype : w.Object.prototype;
    for (var i = 0; i < 2; i++) {
      var f = w.Object.create(proto);
      var vals = { name: word(next, 6 + next() % 5) + ' ' + word(next, 5 + next() % 4),
        description: word(next, 7 + next() % 6), filename: word(next, 8 + next() % 5).toLowerCase(),
        length: 0 };
      w.Object.keys(vals).forEach(function (k) {
        w.Object.defineProperty(f, k, { value: vals[k], enumerable: true, configurable: true });
      });
      w.Object.defineProperty(f, 'item', { value: method('item', function () { return null; }, proto.item || word) });
      w.Object.defineProperty(f, 'namedItem',
        { value: method('namedItem', function () { return null; }, proto.namedItem || word) });
      fakes.push(f);
    }
    function at(i) { return i < n ? real[i] : fakes[i - n]; }
    function named(name) {
      var r = real.namedItem(name);
      if (r) return r;
      for (var i = 0; i < fakes.length; i++) if (fakes[i].name === name) return fakes[i];
      return null;
    }
    var item = method('item', function (i) { return at(i >>> 0) || null; }, real.item);
    var namedItem = method('namedItem', function (name) { return named(String(name)); }, real.namedItem);
    return new w.Proxy(real, {
      get: function (t, prop) {
        if (prop === 'length') return n + fakes.length;
        if (prop === 'item') return item;
        if (prop === 'namedItem') return namedItem;
        if (typeof prop === 'string') {
          if (/^\d+$/.test(prop)) return at(+prop);
          var v = w.Reflect.get(t, prop, t);
          if (v === undefined) { var hit = named(prop); if (hit) return hit; }
          return typeof v === 'function' ? v.bind(t) : v;
        }
        if (prop === w.Symbol.iterator) {
          return function () {
            var all = [];
            for (var i = 0; i < n + fakes.length; i++) all.push(at(i));
            return all[w.Symbol.iterator]();
          };
        }
        var s = w.Reflect.get(t, prop, t);
        return typeof s === 'function' ? s.bind(t) : s;
      },
      has: function (t, prop) {
        if (typeof prop === 'string' && /^\d+$/.test(prop)) return +prop < n + fakes.length;
        return w.Reflect.has(t, prop);
      }
    });
  }

  // ---- making replaced functions look native --------------------------------
  var natives = new WeakMap();      // replacement -> source text of the original
  function method(name, impl, orig) {
    var holder = { [name]() { return impl.apply(this, arguments); } };
    var f = holder[name];
    try { Object.defineProperty(f, 'length', { value: orig.length, configurable: true }); } catch (e) {}
    natives.set(f, origToString.call(orig));
    return f;
  }
  function accessor(name, impl, orig) {
    var holder = { get [name]() { return impl.call(this); } };
    var g = Object.getOwnPropertyDescriptor(holder, name).get;
    natives.set(g, orig ? origToString.call(orig) : 'function get ' + name + '() { [native code] }');
    return g;
  }
  function wrap(obj, name, make) {
    if (!obj) return;
    var d = Object.getOwnPropertyDescriptor(obj, name);
    if (!d || typeof d.value !== 'function') return;
    d.value = method(d.value.name || name, make(d.value), d.value);
    try { Object.defineProperty(obj, name, d); } catch (e) {}
  }
  function getter(obj, name, fn) {
    if (!obj) return;
    var d = Object.getOwnPropertyDescriptor(obj, name);
    if (!d || !d.get) return;
    var orig = d.get;
    d.get = accessor(name, function () { return fn.call(this, orig); }, orig);
    try { Object.defineProperty(obj, name, d); } catch (e) {}
  }
  function setter(obj, name, after) {
    if (!obj) return;
    var d = Object.getOwnPropertyDescriptor(obj, name);
    if (!d || !d.set) return;
    var orig = d.set;
    var holder = { set [name](v) { RAPPLY(orig, this, [v]); after(this, v); } };
    var s = Object.getOwnPropertyDescriptor(holder, name).set;
    natives.set(s, origToString.call(orig));
    d.set = s;
    try { Object.defineProperty(obj, name, d); } catch (e) {}
  }
  // WebGPU names the same card as WebGL on this site (1.1.18): its vendor and
  // architecture, no device id or description (as Chrome on Linux gives).
  function gpuInfo(w) {
    var I = w.GPUAdapterInfo && w.GPUAdapterInfo.prototype;
    if (!I) return;
    var d = Object.getOwnPropertyDescriptor(I, 'vendor'), realVendor = d && d.get;
    function mine(info) {
      var v = '';
      try { v = realVendor.call(info); } catch (e) {}
      return gpuFor(v, GPUS, PICK);
    }
    getter(I, 'vendor', function () { return mine(this)[2]; });
    getter(I, 'architecture', function () { return mine(this)[3]; });
    getter(I, 'device', function () { return ''; });
    getter(I, 'description', function () { return ''; });
  }
  function isProtected(w) {
    try { return w.Function.prototype.toString.call(SECRET) === SECRET; } catch (e) { return false; }
  }

  // ---- inline workers -----------------------------------------------------------
  // Runs inside the worker; must not use anything from outside its own body.
  function workerPatch(c, rng, farble, gpuFor) {
    var toStr = Function.prototype.toString, nat = new WeakMap();
    function method(name, impl, orig) {
      var f = ({ [name]() { return impl.apply(this, arguments); } })[name];
      try { Object.defineProperty(f, 'length', { value: orig.length, configurable: true }); } catch (e) {}
      nat.set(f, toStr.call(orig));
      return f;
    }
    function wrap(obj, name, make) {
      var d = obj && Object.getOwnPropertyDescriptor(obj, name);
      if (!d || typeof d.value !== 'function') return;
      d.value = method(d.value.name || name, make(d.value), d.value);
      try { Object.defineProperty(obj, name, d); } catch (e) {}
    }
    function getter(obj, name, fn) {
      var d = obj && Object.getOwnPropertyDescriptor(obj, name);
      if (!d || !d.get) return;
      var orig = d.get;
      var g = Object.getOwnPropertyDescriptor({ get [name]() { return fn.call(this, orig); } }, name).get;
      nat.set(g, toStr.call(orig));
      d.get = g;
      try { Object.defineProperty(obj, name, d); } catch (e) {}
    }
    wrap(Function.prototype, 'toString', function (orig) {
      return function () {
        var s = nat.get(this);
        return s !== undefined ? s : orig.call(this);
      };
    });
    var N = self.WorkerNavigator && WorkerNavigator.prototype;
    getter(N, 'hardwareConcurrency', function () { return c.cores; });
    if (c.mem) getter(N, 'deviceMemory', function () { return c.mem; });
    if (c.langs) {
      var frozen = Object.freeze(c.langs.slice());
      getter(N, 'languages', function () { return frozen; });
      getter(N, 'language', function () { return frozen[0]; });
    }
    var O2 = self.OffscreenCanvasRenderingContext2D && OffscreenCanvasRenderingContext2D.prototype;
    var rawGet = O2 && O2.getImageData;
    wrap(O2, 'getImageData', function (orig) {
      return function () {
        var img = orig.apply(this, arguments);
        farble(img.data, c.seed, rng);
        return img;
      };
    });
    if (self.OffscreenCanvas && rawGet) {
      wrap(OffscreenCanvas.prototype, 'convertToBlob', function (orig) {
        return function () {
          var src = this;
          try {
            if (src.width && src.height) {
              var copy = new OffscreenCanvas(src.width, src.height);
              var ctx = copy.getContext('2d');
              ctx.drawImage(src, 0, 0);
              var img = rawGet.call(ctx, 0, 0, copy.width, copy.height);
              farble(img.data, c.seed, rng);
              ctx.putImageData(img, 0, 0);
              src = copy;
            }
          } catch (e) { src = this; }
          return orig.apply(src, arguments);
        };
      });
    }
    [self.WebGLRenderingContext, self.WebGL2RenderingContext].forEach(function (GL) {
      if (!GL) return;
      wrap(GL.prototype, 'getExtension', function (orig) {
        return function (name) {
          if (c.hidden[String(name).toLowerCase()] === 1) return null;
          return orig.apply(this, arguments);
        };
      });
      wrap(GL.prototype, 'getSupportedExtensions', function (orig) {
        return function () {
          var list = orig.apply(this, arguments);
          return list && list.filter(function (name) {
            return c.hidden[String(name).toLowerCase()] !== 1;
          });
        };
      });
      wrap(GL.prototype, 'getParameter', function (orig) {
        return function (p) {
          var r = orig.apply(this, arguments);
          // UNMASKED_VENDOR_WEBGL / UNMASKED_RENDERER_WEBGL.
          if ((p === 37445 || p === 37446) && typeof r === 'string') {
            if (c.strict) return null;
            return gpuFor(p === 37445 ? r : orig.call(this, 37445), c.gpus, c.pick)[p - 37445];
          }
          return r;
        };
      });
    });
    if (c.strict) getter(N, 'gpu', function () { return undefined; });
    else if (self.GPUAdapterInfo) {
      var GI = self.GPUAdapterInfo.prototype;
      var gd = Object.getOwnPropertyDescriptor(GI, 'vendor'), realVendor = gd && gd.get;
      var mine = function (info) {
        var v = '';
        try { v = realVendor.call(info); } catch (e) {}
        return gpuFor(v, c.gpus, c.pick);
      };
      getter(GI, 'vendor', function () { return mine(this)[2]; });
      getter(GI, 'architecture', function () { return mine(this)[3]; });
      getter(GI, 'device', function () { return ''; });
      getter(GI, 'description', function () { return ''; });
    }
    // workers started by this worker get the same prelude (1.1.18,
    // independent review: a worker inside a worker had none)
    try {
      var me = '(' + toStr.call(workerPatch) + ')(' + JSON.stringify(c) + ',' + toStr.call(rng) + ',' +
        toStr.call(farble) + ',' + toStr.call(gpuFor) + ');\n';
      while (me.length % 3) me += ' ';                 // so it can be joined to base64 data
      var Ur = self.URL, made = new Map(), mk = Ur && Ur.createObjectURL, rv = Ur && Ur.revokeObjectURL;
      if (mk && self.Blob) {
        wrap(Ur, 'createObjectURL', function (orig) {
          return function (o) {
            var u = orig.apply(this, arguments);
            try { if (o instanceof Blob) made.set(u, o); } catch (e) {}
            return u;
          };
        });
      }
      ['Worker', 'SharedWorker'].forEach(function (name) {
        var Orig = self[name];
        if (typeof Orig !== 'function' || !mk) return;
        var P = new Proxy(Orig, {
          construct: function (t, args, nt) {
            try {
              var u = String(args[0]), rest = Array.prototype.slice.call(args, 1), b = made.get(u);
              args = [u].concat(rest);
              if (b) {
                var pu = mk.call(Ur, new Blob([me, b], { type: b.type || 'text/javascript' }));
                args = [pu].concat(rest);
                setTimeout(function () { rv.call(Ur, pu); }, 30000);
              } else if (u.slice(0, 5) === 'data:' && u.indexOf(',') > 0) {
                var k = u.indexOf(','), b64 = /;base64$/i.test(u.slice(0, k));
                args = [u.slice(0, k + 1) + (b64 ? btoa(me) : encodeURIComponent(me)) +
                  u.slice(k + 1)].concat(rest);
              }
            } catch (e) {}
            return Reflect.construct(t, args, nt === P ? t : nt);
          }
        });
        nat.set(P, toStr.call(Orig));
        try { Object.defineProperty(self, name, { value: P, writable: true, configurable: true }); } catch (e) {}
      });
    } catch (e) {}
  }
  var PRELUDE = '(' + origToString.call(workerPatch) + ')(' +
    JSON.stringify({ cores: cores, mem: strict ? 8 : 0, langs: langs, seed: seed, strict: strict,
      gpus: GPUS, pick: PICK, hidden: hiddenExt }) +
    ',' + origToString.call(rng) + ',' + origToString.call(farble) + ',' + origToString.call(gpuFor) + ');\n';
  while (PRELUDE.length % 3) PRELUDE += ' ';     // so it can be joined to base64 data

  // ---- fonts: the same answer for every I.K.E. user (Strict and above) -------
  // Sites find the installed fonts by measuring text set in hundreds of known
  // font names. Each of those names gets an empty font face that covers no
  // character: text asking for it falls through to the next font in the list,
  // as if the font were not installed. Only the six families every system
  // answers to (Arial, Helvetica, Times, Times New Roman, Courier, Courier New)
  // stay visible. Fonts a page loads itself keep working. The faces are built
  // from a tiny blank font held in memory (one empty glyph, 0.6 kB), so nothing
  // is fetched and a page's content security policy is not involved.
  var BLANK_FONT = 'AAEAAAAKAIAAAwAgT1MvMiTgM5AAAAEoAAAAYGNtYXAADOBTAAABkAAAADRnbHlmAAAAAAAAAcwAAAABaGVhZC1P1eAAAACsAAAANmhoZWEDIgEuAAAA5AAAACRobXR4AfQAAAAAAYgAAAAGbG9jYQAAAAAAAAHEAAAABm1heHAAAwACAAABCAAAACBuYW1lWZqb1QAAAdAAAABjcG9zdHZnA3AAAAI0AAAAKgABAAAAAQAAVumIp18PPPUAAwPoAAAAAOccyoAAAAAA5xzKgAAAAAAAAAAAAAAAAwACAAAAAAAAAAEAAAMg/zgAAAH0AAAAAAAAAAEAAAAAAAAAAAAAAAAAAAABAAEAAAACAAAAAAAAAAAAAgAAAAAAAAAAAAAAAAAAAAAAAwH0AZAABQAEAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAAPz8/PwAA4ADgAAMg/zgAAAMgAMgAAAAAAAAAAAAAAAAAAAAgAAAB9AAAAAAAAAAAAAIAAAADAAAAFAADAAEAAAAUAAQAIAAAAAQABAABAADgAP//AADgAP//IAEAAQAAAAAAAAAAAAAAAAAAAAAAAAAEADYAAQAAAAAAAQAIAAAAAQAAAAAAAgAHAAgAAwABBAkAAQAQAA8AAwABBAkAAgAOAB9JY2VCbGFua1JlZ3VsYXIASQBjAGUAQgBsAGEAbgBrAFIAZQBnAHUAbABhAHIAAAIAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAgAAAQIDcHVhAAA=';
  var MASKED_FONTS = ["Abadi MT Condensed Light","Academy Engraved LET","ADOBE CASLON PRO","Adobe Garamond","ADOBE GARAMOND PRO","Adwaita Mono","Adwaita Sans","Agency FB","Aharoni","Albertus Extra Bold","Albertus Medium","Algerian","Amazone BT","American Typewriter","American Typewriter Condensed","AmerType Md BT","Andale Mono","Andalus","Angsana New","AngsanaUPC","Ani","AnjaliOldLipi","Anonymous Pro","Antique Olive","Aparajita","Apple Chancery","Apple Color Emoji","Apple SD Gothic Neo","Apple Symbols","AppleGothic","AppleMyungjo","AR PL UKai CN","AR PL UMing CN","Arabic Typesetting","ARCHER","Arial Black","Arial Hebrew","Arial MT","Arial Narrow","Arial Rounded MT Bold","Arial Unicode MS","Arimo","ARNO PRO","Arrus BT","Athelas","Aurora Cn BT","AvantGarde Bk BT","AvantGarde Md BT","AVENIR","Avenir Next","Avenir Next Condensed","Ayuthaya","Bahnschrift","Bandy","Bangla Sangam MN","Bank Gothic","BankGothic Md BT","Barlow","Baskerville","Baskerville Old Face","Batang","BatangChe","Bauer Bodoni","Bauhaus 93","Bazooka","Bell MT","Bembo","Benguiat Bk BT","Berlin Sans FB","Berlin Sans FB Demi","Bernard MT Condensed","BernhardFashion BT","BernhardMod BT","Big Caslon","BinnerD","Bitstream Charter","Bitstream Vera Sans","Bitstream Vera Sans Mono","Bitstream Vera Serif","Blackadder ITC","BlairMdITC TT","Bodoni 72","Bodoni 72 Oldstyle","Bodoni 72 Smallcaps","Bodoni MT","Bodoni MT Black","Bodoni MT Condensed","Bodoni MT Poster Compressed","Book Antiqua","Bookman Old Style","Bookshelf Symbol 7","Boulder","Bradley Hand","Bradley Hand ITC","Bremen Bd BT","Britannic Bold","Broadway","Browallia New","BrowalliaUPC","Brush Script MT","C059","Cabin","Caladea","Calibri","Calibri Light","Californian FB","Calisto MT","Calligrapher","Cambria","Cambria Math","Candara","Cantarell","Carlito","Cascadia Code","Cascadia Code PL","Cascadia Mono","CaslonOpnface BT","Castellar","Centaur","Century","Century Gothic","Century Schoolbook","Century Schoolbook L","Cezanne","CG Omega","CG Times","Chalkboard","Chalkboard SE","Chalkduster","Chandas","Charlesworth","Charter","Charter Bd BT","Charter BT","Chaucer","ChelthmITC Bk BT","Chiller","Clarendon","Clarendon Condensed","CloisterBlack BT","Cochin","Colonna MT","Comfortaa","Comic Sans","Comic Sans MS","Consolas","Constantia","Cooper Black","Copperplate","Copperplate Gothic","Copperplate Gothic Bold","Copperplate Gothic Light","CopperplGoth Bd BT","Corbel","Cordia New","CordiaUPC","Cornerstone","Coronet","Courier 10 Pitch","Courier Prime","Cousine","Cuckoo","Curlz MT","D050000L","DaunPenh","Dauphin","David","DB LCD Temp","DejaVu Math TeX Gyre","DejaVu Sans","DejaVu Sans Condensed","DejaVu Sans Light","DejaVu Sans Mono","DejaVu Serif","DejaVu Serif Condensed","DELICIOUS","Denmark","DFKai-SB","Didot","DilleniaUPC","DIN","DokChampa","Dosis","Dotum","DotumChe","Droid Sans","Droid Sans Fallback","Droid Sans Mono","Droid Serif","Dyuthi","Ebrima","Edwardian Script ITC","Elephant","English 111 Vivace BT","Engravers MT","EngraversGothic BT","Eras Bold ITC","Eras Demi ITC","Eras Light ITC","Eras Medium ITC","EucrosiaUPC","Euphemia","Euphemia UCAS","EUROSTILE","Exotc350 Bd BT","FangSong","Felix Titling","Fira Code","Fira Mono","Fira Sans","Fixedsys","FONTIN","Footlight MT Light","Forte","Franklin Gothic","Franklin Gothic Book","Franklin Gothic Demi","Franklin Gothic Heavy","Franklin Gothic Medium","FrankRuehl","Fransiscan","Freefrm721 Blk BT","FreeMono","FreeSans","FreeSerif","FreesiaUPC","Freestyle Script","French Script MT","FrnkGothITC Bk BT","Fruitger","FRUTIGER","Futura","Futura Bk BT","Futura Lt BT","Futura Md BT","Futura ZBlk BT","FuturaBlack BT","Gabriola","Gadugi","Galliard BT","Garamond","Gargi","Garuda","Gautami","Geeza Pro","Geneva","Gentium","Geometr231 BT","Geometr231 Hv BT","Geometr231 Lt BT","Georgia","GeoSlab 703 Lt BT","GeoSlab 703 XBd BT","Gigi","Gill Sans","Gill Sans MT","Gill Sans MT Condensed","Gill Sans MT Ext Condensed Bold","Gill Sans Ultra Bold","Gill Sans Ultra Bold Condensed","Gisha","Gloucester MT Extra Condensed","GOTHAM","GOTHAM BOLD","Goudy Old Style","Goudy Stout","GoudyHandtooled BT","GoudyOLSt BT","Gujarati Sangam MN","Gulim","GulimChe","Gungsuh","GungsuhChe","Gurmukhi MN","Hack","Haettenschweiler","Harlow Solid Italic","Harrington","Heather","Heiti SC","Heiti TC","HELV","Helvetica Neue","Helvetica Neue LT","Herald","High Tower Text","Hiragino Kaku Gothic ProN","Hiragino Mincho ProN","Hiragino Sans","Hiragino Sans GB","Hoefler Text","HoloLens MDL2 Assets","Humanst 521 Cn BT","Humanst521 BT","Humanst521 Lt BT","IBM Plex Mono","IBM Plex Sans","IBM Plex Serif","Impact","Imprint MT Shadow","Incised901 Bd BT","Incised901 BT","Incised901 Lt BT","INCONSOLATA","Inconsolata","Informal Roman","Informal011 BT","Ink Free","Inter","INTERSTATE","Iowan Old Style","IrisUPC","Iskoola Pota","JasmineUPC","Javanese Text","Jazz LET","Jenson","Jester","JetBrains Mono","Jokerman","Josefin Sans","Juice ITC","Kabel Bk BT","Kabel Ult BT","KacstOne","Kailasa","KaiTi","Kalimati","Kalinga","Kannada Sangam MN","Karla","Kartika","Karumbi","Kaufmann Bd BT","Kaufmann BT","Kefa","Keraleeyam","Khmer OS","Khmer UI","Kinnari","KodchiangUPC","Kohinoor Bangla","Kohinoor Devanagari","Kokila","Korinna BT","Kristen ITC","Krungthep","Kunstler Script","Laksaman","Lao UI","Latha","Lato","Leelawadee","Leelawadee UI","Letter Gothic","Levenim MT","Liberation Mono","Liberation Sans","Liberation Sans Narrow","Liberation Serif","LilyUPC","Linux Biolinum","Linux Libertine","Lithograph","Lithograph Light","Lohit Devanagari","Lohit Gujarati","Lohit Tamil","Loma","Long Island","Lucida Bright","Lucida Calligraphy","Lucida Console","Lucida Fax","LUCIDA GRANDE","Lucida Handwriting","Lucida Sans","Lucida Sans Typewriter","Lucida Sans Unicode","Luminari","Lydian BT","Magneto","Maiandra GD","Malayalam Sangam MN","Malgun Gothic","Malgun Gothic Semilight","Mangal","Manjari","Marigold","Marion","Marker Felt","Market","Marlett","Matisse ITC","Matura MT Script Capitals","Meera","Meiryo","Meiryo UI","Menlo","Merriweather","Microsoft Himalaya","Microsoft JhengHei","Microsoft JhengHei UI","Microsoft New Tai Lue","Microsoft PhagsPa","Microsoft Sans Serif","Microsoft Tai Le","Microsoft Uighur","Microsoft YaHei","Microsoft YaHei UI","Microsoft Yi Baiti","MingLiU","MingLiU-ExtB","MingLiU_HKSCS","MingLiU_HKSCS-ExtB","Minion","Minion Pro","Miriam","Miriam Fixed","Mistral","Modern","Modern No. 20","Mona Lisa Solid ITC TT","Monaco","Mongolian Baiti","MONO","Monotype Corsiva","Montserrat","MoolBoran","Mrs Eaves","MS Gothic","MS LineDraw","MS Mincho","MS Outlook","MS PGothic","MS PMincho","MS Reference Sans Serif","MS Reference Specialty","MS Sans Serif","MS Serif","MS UI Gothic","MT Extra","Mukti Narrow","Mulish","MUSEO","MV Boli","Myanmar Text","MYRIAD","MYRIAD PRO","Nadeem","Nakula","Narkisim","Navilu","NEVIS","New York","News Gothic","News GothicMT","NewsGoth BT","Niagara Engraved","Niagara Solid","Nimbus Mono L","Nimbus Mono PS","Nimbus Roman","Nimbus Roman No9 L","Nimbus Sans","Nimbus Sans L","Nimbus Sans Narrow","Nirmala UI","Norasi","Noteworthy","Noto Color Emoji","Noto Mono","Noto Sans","Noto Sans CJK JP","Noto Sans CJK KR","Noto Sans CJK SC","Noto Sans CJK TC","Noto Sans Mono","Noto Serif","Noto Serif CJK JP","Noto Serif CJK SC","NSimSun","Nunito","Nyala","OCR A Extended","Old Century","Old English Text MT","Onyx","Onyx BT","Open Sans","Open Sans Condensed","OpenSymbol","Optima","OPTIMA","Oriya Sangam MN","OSAKA","Oswald","Oxygen","Oxygen Mono","OzHandicraft BT","P052","Padauk","Pagul","Palace Script MT","Palatino","Palatino Linotype","Papyrus","Parchment","Party LET","Pegasus","Perpetua","Perpetua Titling MT","PetitaBold","Phosphate","Pickwick","PingFang HK","PingFang SC","PingFang TC","Plantagenet Cherokee","Playbill","Playfair Display","PMingLiU","PMingLiU-ExtB","Poor Richard","Poppins","Poster","PosterBodoni BT","PRINCETOWN LET","Pristina","PT Mono","PT Sans","PT Serif","PTBarnum BT","Purisa","Pythagoras","Quicksand","Raavi","Rachana","Rage Italic","Raleway","Rasa","Ravie","Rekha","Ribbon131 Bd BT","Roboto","Roboto Condensed","Roboto Mono","Roboto Slab","Rockwell","Rockwell Condensed","Rockwell Extra Bold","Rockwell Nova","Rod","Roman","Rubik","Saab","Sahadeva","Sakkal Majalla","Samanata","Samyak Devanagari","San Francisco","Santa Fe LET","Sarai","Savoye LET","Sawasdee","Sceptre","Script","Script MT Bold","SCRIPTINA","Segoe Fluent Icons","Segoe MDL2 Assets","Segoe Print","Segoe Script","Segoe UI","Segoe UI Emoji","Segoe UI Historic","Segoe UI Light","Segoe UI Semibold","Segoe UI Symbol","Segoe UI Variable","Seravek","Serifa","Serifa BT","Serifa Th BT","SF Mono","SF Pro","SF Pro Display","SF Pro Text","ShelleyVolante BT","Sherwood","Shonar Bangla","Showcard Gothic","Shruti","Signboard","SILKSCREEN","SimHei","Simplified Arabic","Simplified Arabic Fixed","SimSun","SimSun-ExtB","Sinhala Sangam MN","Sitka","Sitka Text","Sketch Rockwell","Skia","Small Fonts","Snap ITC","Snell Roundhand","Socket","Songti SC","Source Code Pro","Source Sans 3","Source Sans Pro","Source Serif Pro","Souvenir Lt BT","Staccato222 BT","Standard Symbols L","Standard Symbols PS","Steamer","Stencil","STFangsong","STHeiti","STIX","STIX Two Text","STKaiti","Storybook","STSong","Styllo","Subway","Superclarendon","Suruma","Swis721 BlkEx BT","Swiss911 XCm BT","Sylfaen","Symbol","Symbola","Synchro LET","System","Tahoma","Tamil Sangam MN","Technical","Teletype","Telugu Sangam MN","Tempus Sans ITC","Terminal","Terminus","Thonburi","Tibetan Machine Uni","Times New Roman PS","Tinos","Titillium Web","Tlwg Mono","Traditional Arabic","Trajan","TRAJAN PRO","Trattatello","Trebuchet MS","Tristan","Tubular","Tunga","Tw Cen MT","Tw Cen MT Condensed","Tw Cen MT Condensed Extra Bold","TypoUpright BT","Ubuntu","Ubuntu Condensed","Ubuntu Light","Ubuntu Mono","Umpush","Unicorn","Unifont","Univers","Univers CE 55 Medium","Univers Condensed","Uroob","URW Bookman","URW Bookman L","URW Chancery L","URW Gothic","URW Gothic L","URW Palladio L","Utsaah","Vagabond","Vani","Verdana","Vijaya","Viner Hand ITC","VisualUI","Vivaldi","Vladimir Script","Vrinda","Waree","Webdings","WenQuanYi Micro Hei","WenQuanYi Zen Hei","Westminster","WHITNEY","Wide Latin","Wingdings","Wingdings 2","Wingdings 3","Work Sans","Yrsa","Yu Gothic","Yu Gothic UI","Yu Mincho","Z003","ZapfEllipt BT","ZapfHumnst BT","ZapfHumnst Dm BT","Zapfino","Zurich BlkEx BT","Zurich Ex BT","ZWAdobeF"];
  // Only the names a page could find on this computer need a mask (1.1.17):
  // I.K.E. asks the engine once which of the list it can find (the same test
  // the fingerprinting scripts use) and passes them in CFG.fonts. A name the
  // engine cannot find looks absent anyway. Without that answer: the whole
  // list, as before. 714 masks in every frame cost about 20 ms per frame.
  var MASKED = (CFG.fonts instanceof Array) ? CFG.fonts : MASKED_FONTS;
  var maskedFaces = new WeakSet(), maskedDocs = new WeakSet();
  function maskFonts(w) {
    var doc = w.document;
    if (!doc || !doc.fonts || !w.FontFace || maskedDocs.has(doc)) return;
    maskedDocs.add(doc);
    var set = doc.fonts, own = [], blank = null;
    try {
      var bin = w.atob(BLANK_FONT);
      blank = new w.Uint8Array(bin.length);
      for (var k = 0; k < bin.length; k++) blank[k] = bin.charCodeAt(k);
    } catch (e) { return; }
    function fill() {
      for (var i = 0; i < MASKED.length; i++) {
        try {
          var face = own[i] || (own[i] = new w.FontFace(MASKED[i], blank,
            { unicodeRange: 'U+E000' }));
          maskedFaces.add(face);
          FSP_add.call(set, face);
        } catch (e) {}
      }
    }
    // the interface has no global name in this engine: take it from the object
    var FSP = Object.getPrototypeOf(set);
    if (!FSP) return;
    var FSP_add = FSP.add, FSP_forEach = FSP.forEach;
    function visible(target) {
      var out = [];
      FSP_forEach.call(target, function (f) { if (!maskedFaces.has(f)) out.push(f); });
      return out;
    }
    // the page sees only its own font faces
    getter(FSP, 'size', function () { return visible(this).length; });
    wrap(FSP, 'forEach', function () {
      return function (cb, thisArg) {
        var self = this;
        visible(this).forEach(function (f) { cb.call(thisArg, f, f, self); });
      };
    });
    wrap(FSP, 'values', function () { return function () { return visible(this).values(); }; });
    wrap(FSP, 'keys', function () { return function () { return visible(this).values(); }; });
    wrap(FSP, 'entries', function () {
      return function () { return visible(this).map(function (f) { return [f, f]; }).values(); };
    });
    try {
      var itDesc = Object.getOwnPropertyDescriptor(FSP, w.Symbol.iterator);
      if (itDesc && typeof itDesc.value === 'function') {
        itDesc.value = method('values', function () { return visible(this).values(); }, itDesc.value);
        Object.defineProperty(FSP, w.Symbol.iterator, itDesc);
      }
    } catch (e) {}
    wrap(FSP, 'has', function (orig) {
      return function (f) { return maskedFaces.has(f) ? false : orig.apply(this, arguments); };
    });
    wrap(FSP, 'delete', function (orig) {
      return function (f) { return maskedFaces.has(f) ? false : orig.apply(this, arguments); };
    });
    wrap(FSP, 'clear', function (orig) {
      return function () {
        var r = orig.apply(this, arguments);
        if (this === set) fill();
        return r;
      };
    });
    fill();
  }

  // ---- one realm ---------------------------------------------------------------
  function install(w) {
    if (!w || isProtected(w)) return;
    var doc = w.document;

    // Function.prototype.toString: natives stay "[native code]" in every realm
    wrap(w.Function.prototype, 'toString', function (orig) {
      return function () {
        if (this === SECRET) return SECRET;
        var s = natives.get(this);
        return s !== undefined ? s : orig.call(this);
      };
    });
    if (CFG.gpc) {
      try {
        Object.defineProperty(w.Navigator.prototype, 'globalPrivacyControl', {
          get: accessor('globalPrivacyControl', function () { return true; }, null),
          configurable: true, enumerable: true
        });
      } catch (e) {}
    }

    // ---- canvas: invisible per-site noise ----
    var C2D = w.CanvasRenderingContext2D && w.CanvasRenderingContext2D.prototype;
    var rawGetImageData = C2D && C2D.getImageData;
    function noisyCopy(canvas) {
      try {
        if (!canvas.width || !canvas.height) return canvas;
        var c = doc.createElement('canvas');
        c.width = canvas.width; c.height = canvas.height;
        var ctx = c.getContext('2d');
        ctx.drawImage(canvas, 0, 0);
        var img = rawGetImageData.call(ctx, 0, 0, c.width, c.height);
        farble(img.data, seed, rng);
        ctx.putImageData(img, 0, 0);
        return c;
      } catch (e) { return canvas; }
    }
    if (w.HTMLCanvasElement && rawGetImageData) {
      wrap(w.HTMLCanvasElement.prototype, 'toDataURL', function (orig) {
        return function () { return orig.apply(noisyCopy(this), arguments); };
      });
      wrap(w.HTMLCanvasElement.prototype, 'toBlob', function (orig) {
        return function () { return orig.apply(noisyCopy(this), arguments); };
      });
    }
    wrap(C2D, 'getImageData', function (orig) {
      return function () {
        var img = orig.apply(this, arguments);
        farble(img.data, seed, rng);
        return img;
      };
    });
    var O2D = w.OffscreenCanvasRenderingContext2D && w.OffscreenCanvasRenderingContext2D.prototype;
    var rawOffGet = O2D && O2D.getImageData;
    wrap(O2D, 'getImageData', function (orig) {
      return function () {
        var img = orig.apply(this, arguments);
        farble(img.data, seed, rng);
        return img;
      };
    });
    if (w.OffscreenCanvas && rawOffGet) {
      wrap(w.OffscreenCanvas.prototype, 'convertToBlob', function (orig) {
        return function () {
          var src = this;
          try {
            if (src.width && src.height) {
              var copy = new w.OffscreenCanvas(src.width, src.height);
              var ctx = copy.getContext('2d');
              ctx.drawImage(src, 0, 0);
              var img = rawOffGet.call(ctx, 0, 0, copy.width, copy.height);
              farble(img.data, seed, rng);
              ctx.putImageData(img, 0, 0);
              src = copy;
            }
          } catch (e) { src = this; }
          return orig.apply(src, arguments);
        };
      });
    }
    if (strict && w.TextMetrics) {
      getter(w.TextMetrics.prototype, 'width', function (orig) { return orig.call(this) + textDelta; });
    }

    // ---- WebGL: hide the raw GPU identity in strict profiles; retain pixel farbling ----
    [w.WebGLRenderingContext, w.WebGL2RenderingContext].forEach(function (GL) {
      if (!GL) return;
      wrap(GL.prototype, 'getExtension', function (orig) {
        return function (name) {
          if (hiddenExt[String(name).toLowerCase()] === 1) return null;
          return orig.apply(this, arguments);
        };
      });
      wrap(GL.prototype, 'getSupportedExtensions', function (orig) {
        return function () {
          var list = orig.apply(this, arguments);
          return list && list.filter(function (name) {
            return hiddenExt[String(name).toLowerCase()] !== 1;
          });
        };
      });
      wrap(GL.prototype, 'getParameter', function (orig) {
        return function (p) {
          var r = orig.apply(this, arguments);
          // UNMASKED_VENDOR_WEBGL / UNMASKED_RENDERER_WEBGL: the site's model,
          // or nothing where the extension is hidden (as without it)
          if ((p === 37445 || p === 37446) && typeof r === 'string') {
            if (strict) return null;
            return gpuFor(p === 37445 ? r : orig.call(this, 37445), GPUS, PICK)[p - 37445];
          }
          return r;
        };
      });
      wrap(GL.prototype, 'readPixels', function (orig) {
        return function () {
          var r = orig.apply(this, arguments);
          var buf = arguments[6];
          if (buf && buf.length && buf instanceof w.Uint8Array) farble(buf, seed, rng);
          return r;
        };
      });
    });
    if (strict) getter(w.Navigator.prototype, 'gpu', function () { return undefined; });
    else gpuInfo(w);

    // ---- audio ----
    var seenBuffers = new WeakSet();
    if (w.AudioBuffer) {
      wrap(w.AudioBuffer.prototype, 'getChannelData', function (orig) {
        return function () {
          var d = orig.apply(this, arguments);
          if (!seenBuffers.has(d)) {
            seenBuffers.add(d);
            for (var i = 0; i < d.length; i += 97) d[i] = d[i] * audioFactor;
          }
          return d;
        };
      });
      wrap(w.AudioBuffer.prototype, 'copyFromChannel', function (orig) {
        return function (dest) {
          var r = orig.apply(this, arguments);
          for (var i = 0; i < dest.length; i += 97) dest[i] = dest[i] * audioFactor;
          return r;
        };
      });
    }
    if (w.AnalyserNode) {
      ['getFloatFrequencyData', 'getFloatTimeDomainData'].forEach(function (name) {
        wrap(w.AnalyserNode.prototype, name, function (orig) {
          return function (arr) {
            var r = orig.apply(this, arguments);
            for (var i = 0; i < arr.length; i++) arr[i] = arr[i] * audioFactor;
            return r;
          };
        });
      });
    }

    // ---- hardware / device values ----
    var NP = w.Navigator.prototype;
    // Plugins: the real list plus two entries whose names differ on every site.
    if (w.Proxy && w.Reflect) {
      var pluginViews = new w.WeakMap();
      getter(NP, 'plugins', function (orig) {
        var real = orig.call(this);
        try {
          var view = pluginViews.get(real);
          if (!view) { view = pluginList(w, real); pluginViews.set(real, view); }
          return view;
        } catch (e) { return real; }
      });
    }
    getter(NP, 'hardwareConcurrency', function () { return cores; });
    if (strict) getter(NP, 'deviceMemory', function () { return 8; });
    if (langs) {
      var frozenLangs = w.Object.freeze(w.Array.from(langs));
      getter(NP, 'languages', function () { return frozenLangs; });
      if (maximum) getter(NP, 'language', function () { return frozenLangs[0]; });
    }
    // ---- speech voices (1.1.15): the installed voices tell the system and
    // its language packs apart. Balanced keeps the voices of the page's own
    // languages and English (what a site can use to read aloud); Strict and
    // above only the default voice.
    if (w.SpeechSynthesis) {
      var voiceLangs = [];
      try {
        (navigator.languages || [navigator.language || 'en']).concat(['en']).forEach(function (l) {
          var p = String(l || '').toLowerCase().split('-')[0];
          if (p && voiceLangs.indexOf(p) < 0) voiceLangs.push(p);
        });
      } catch (e) { voiceLangs = ['en']; }
      wrap(w.SpeechSynthesis.prototype, 'getVoices', function (orig) {
        return function () {
          var all = orig.apply(this, arguments), out = [];
          if (!all || !all.length) return all;
          for (var i = 0; i < all.length; i++) {
            var v = all[i];
            if (strict) { if (v['default']) { out.push(v); break; } continue; }
            var p = String(v.lang || '').toLowerCase().split(/[-_]/)[0];
            if (voiceLangs.indexOf(p) >= 0) out.push(v);
          }
          if (strict && !out.length) out.push(all[0]);
          return out;
        };
      });
    }
    if (strict) {
      maskFonts(w);
      try { delete NP.getBattery; } catch (e) {}
      // A usual monitor size instead of the real one (or, worse, the window's).
      var scr = w.Screen && w.Screen.prototype, size = null;
      var dW = scr && Object.getOwnPropertyDescriptor(scr, 'width');
      var dH = scr && Object.getOwnPropertyDescriptor(scr, 'height');
      var sized = function (self) {
        if (!size) size = usualScreen(dW.get.call(self), dH.get.call(self));
        return size;
      };
      if (dW && dH && dW.get && dH.get) {
        getter(scr, 'width', function () { return sized(this)[0]; });
        getter(scr, 'height', function () { return sized(this)[1]; });
        getter(scr, 'availWidth', function () { return sized(this)[0]; });
        getter(scr, 'availHeight', function () { return sized(this)[1]; });
      }
      getter(scr, 'availLeft', function () { return 0; });
      getter(scr, 'availTop', function () { return 0; });
      getter(scr, 'colorDepth', function () { return 24; });
      getter(scr, 'pixelDepth', function () { return 24; });
      // window position and frame size (these live on the window object itself)
      getter(w, 'outerWidth', function () { return w.innerWidth; });
      getter(w, 'outerHeight', function () { return w.innerHeight; });
      ['screenX', 'screenY', 'screenLeft', 'screenTop'].forEach(function (n) {
        getter(w, n, function () { return 0; });
      });
      if (w.MediaDevices) {
        wrap(w.MediaDevices.prototype, 'enumerateDevices', function () {
          return function () { return w.Promise.resolve([]); };
        });
      }
      if (w.Keyboard) {
        wrap(w.Keyboard.prototype, 'getLayoutMap', function () {
          return function () { return w.Promise.reject(new w.DOMException('', 'SecurityError')); };
        });
      }
      var denyLocalFonts = function () {
        return function () {
          return w.Promise.reject(new w.DOMException('Permission denied', 'NotAllowedError'));
        };
      };
      // Chromium exposes queryLocalFonts on Window.prototype. Patching only
      // the window instance misses the inherited method on several versions.
      if (w.Window && w.Window.prototype) wrap(w.Window.prototype, 'queryLocalFonts', denyLocalFonts);
      wrap(w, 'queryLocalFonts', denyLocalFonts); // fallback for engine variants
      if (w.NavigatorUAData) {
        wrap(w.NavigatorUAData.prototype, 'getHighEntropyValues', function (orig) {
          return function (hints) {
            var self = this;
            return orig.apply(this, arguments).then(function (v) {
              var major = (self.brands && self.brands[0] && self.brands[0].version) || '0';
              var out = { brands: v.brands, mobile: false, platform: CFG.platform || 'Linux' };
              var generic = { architecture: 'x86', bitness: '64', model: '',
                platformVersion: CFG.platformVersion || '6.0.0',
                uaFullVersion: major + '.0.0.0', wow64: false, formFactors: ['Desktop'],
                fullVersionList: (v.brands || []).map(function (b) {
                  return { brand: b.brand, version: b.version + '.0.0.0' };
                }) };
              (hints || []).forEach(function (h) { if (h in generic) out[h] = generic[h]; });
              return out;
            });
          };
        });
      }
    }

    // ---- inline workers get the same values ----
    var U = w.URL, blobs = new w.Map();
    var rawCreate = U && U.createObjectURL, rawRevoke = U && U.revokeObjectURL;
    if (rawCreate && rawRevoke && w.Blob) {
      wrap(U, 'createObjectURL', function (orig) {
        return function (obj) {
          var url = orig.apply(this, arguments);
          try {
            // every blob, whatever its type and size: a worker runs any of them
            // (1.1.18, independent review: other types and large ones got no prelude)
            if (obj instanceof w.Blob) blobs.set(url, obj);
          } catch (e) {}
          return url;
        };
      });
      wrap(U, 'revokeObjectURL', function (orig) {
        return function (url) {
          blobs.delete(url);
          return orig.apply(this, arguments);
        };
      });
      ['Worker', 'SharedWorker'].forEach(function (name) {
        var Orig = w[name];
        if (typeof Orig !== 'function') return;
        var P = new w.Proxy(Orig, {
          construct: function (target, args, newTarget) {
            try {
              var url = String(args[0]);
              // the address as read here is the one used (an object whose
              // text changes between two readings cannot slip past)
              args = [url].concat(Array.prototype.slice.call(args, 1));
              if (url.slice(0, 5) === 'blob:') {
                var blob = blobs.get(url);
                if (!blob) {
                  // a blob address made elsewhere (in a worker, another frame):
                  // its text is read here, once
                  try {
                    var x = new w.XMLHttpRequest();
                    x.open('GET', url, false);
                    x.send();
                    if (x.status === 200 || x.status === 0) blob = new w.Blob([x.responseText], { type: 'text/javascript' });
                  } catch (e) {}
                }
                if (blob) {
                  var patched = rawCreate.call(U, new w.Blob([PRELUDE, blob],
                    { type: blob.type || 'text/javascript' }));
                  args = [patched].concat(Array.prototype.slice.call(args, 1));
                  w.setTimeout(function () { rawRevoke.call(U, patched); }, 30000);
                }
              } else if (url.slice(0, 5) === 'data:') {
                var comma = url.indexOf(',');
                if (comma > 0) {
                  var b64 = /;base64$/i.test(url.slice(0, comma));
                  args = [url.slice(0, comma + 1) +
                    (b64 ? w.btoa(PRELUDE) : w.encodeURIComponent(PRELUDE)) +
                    url.slice(comma + 1)].concat(Array.prototype.slice.call(args, 1));
                }
              }
            } catch (e) {}
            return w.Reflect.construct(target, args, newTarget === P ? target : newTarget);
          }
        });
        natives.set(P, origToString.call(Orig));
        try {
          Object.defineProperty(Orig.prototype, 'constructor',
            { value: P, writable: true, configurable: true });
          Object.defineProperty(w, name, { value: P, writable: true, configurable: true });
        } catch (e) {}
      });
    }

    guard(w);
  }

  // ---- new empty windows: protect them before the page can use them --------
  var foreign = new WeakSet();          // frames of other sites: not ours to touch
  // Realms already protected, by their own Function object: a frame that loads
  // a new document keeps its window object but gets a new realm, which is then
  // protected again. Asking a realm whether it is protected (isProtected) costs a
  // call into it; asking this set is free, and pages insert nodes very often.
  var realms = new WeakSet();
  function adopt(cw) {
    if (!cw || foreign.has(cw)) return;
    var F;
    try {
      F = cw.Function;                                    // throws if cross-origin
      if (!F) { foreign.add(cw); return; }
    } catch (e) { foreign.add(cw); return; }
    if (realms.has(F)) return;
    try { install(cw); } catch (e) {}
    realms.add(F);
  }
  function sweep(win) {
    try {
      for (var i = 0, n = framesOf(win); i < n; i++) adopt(win[i]);
    } catch (e) {}
  }
  function guard(w) {
    // Looking into every frame is not free, so it is done only when the number
    // of frames changed, or after an operation that can swap one frame for another.
    var known = 0, watching = false;
    var own = w.document;
    function check(node, force) {
      // the usual case, first and cheap: a node of this document, no frame added
      if (!force && framesOf(w) === known && (!node || docOf(node) === own)) return;
      var d = node ? docOf(node) : own, win = w;
      if (d && d !== own) {
        try { win = defaultViewOf(d) || w; } catch (e) { win = w; }
      }
      if (win !== w) { if (framesOf(win)) sweep(win); return; }
      var n = framesOf(w);
      if (n !== known || (force && n)) { known = n; sweep(w); }
    }
    // the document of a node or of a Range, through the engine's getters (a
    // page's own ownerDocument or defaultView cannot mislead the guard)
    function docOf(node) {
      try {
        if (nodeTypeOf(node) === 9) return node;
        return ownerOf(node) || node;
      } catch (e) {}
      try {
        var c = startContainerOf(node);
        return nodeTypeOf(c) === 9 ? c : ownerOf(c);
      } catch (e) {}
      return own;
    }
    // innerHTML / outerHTML: only HTML that writes a frame can bring a new one
    function after(node, v) {
      if (typeof v !== 'string' || FRAME_HTML.test(v)) check(node, true);
    }
    // The DOM methods a page calls most (appendChild, insertBefore...) get one
    // native-looking function of their own instead of a wrapper around a
    // wrapper: one call less for every node a page inserts (1.1.12).
    function hook(obj, name, force) {
      var d = obj && Object.getOwnPropertyDescriptor(obj, name);
      if (!d || typeof d.value !== 'function') return;
      var orig = d.value;
      // the usual one or two arguments are passed on as they are (no array
      // made for each call: 1.1.18); any other number exactly as given
      var invoke = RAPPLY(BIND, CALL, [orig]);   // bound now: nothing the page changes later is looked up
      // A frame is new when this very call changed the number of frames, or
      // moved a node that was in a document already (a moved frame gets a new
      // window). Counting before and after the call, not against the count
      // of the last check: a frame removed earlier, then another added, keeps
      // the count the same (1.1.18, independent review).
      var f = ({ [orig.name || name](a, b) {
        var n = arguments.length, r, pre, moved;
        if (n === 1) {
          if (!force && !mayNode(a)) return invoke(this, a);
          pre = framesOf(w); moved = !force && placed(a);
          r = invoke(this, a);
        } else if (n === 2) {
          if (!force && !mayNode(a) && !mayNode(b)) return invoke(this, a, b);
          pre = framesOf(w); moved = !force && (placed(a) || placed(b));
          r = invoke(this, a, b);
        } else {
          if (!force && !mayAny(arguments)) return reflectApply(orig, this, arguments);
          pre = framesOf(w); moved = false;
          if (!force) for (var i = 0; i < arguments.length; i++) if (placed(arguments[i])) moved = true;
          r = reflectApply(orig, this, arguments);
        }
        if (force || moved || framesOf(w) !== pre || !ours(this)) check(this, true);
        return r;
      } })[orig.name || name];
      try { Object.defineProperty(f, 'length', { value: orig.length, configurable: true }); } catch (e) {}
      natives.set(f, origToString.call(orig));
      d.value = f;
      try { Object.defineProperty(obj, name, d); } catch (e) {}
    }
    // Can this insertion bring a frame into a document? Not when the target is
    // outside any document (frameworks build whole trees there first), nor for
    // text or an element without children that is not a frame itself.
    var FRAMES = { iframe: 1, frame: 1, object: 1, embed: 1 };
    var FRAME_HTML = /<\s*(i?frame|object|embed)\b/i;
    var reflectApply = RAPPLY;
    // The node's own properties are read through the engine's getters, taken
    // when the protection is installed: a page cannot make a frame look like
    // text by giving it a nodeType of its own (1.1.18, independent review).
    function native(P, n) {
      var d = P && Object.getOwnPropertyDescriptor(P, n);
      return d && d.get ? RAPPLY(BIND, CALL, [d.get]) : null;
    }
    var nodeTypeOf = native(w.Node && w.Node.prototype, 'nodeType');
    var localNameOf = native(w.Element && w.Element.prototype, 'localName');
    var connectedOf = native(w.Node && w.Node.prototype, 'isConnected');
    var firstElementOf = native(w.Element && w.Element.prototype, 'firstElementChild');
    function mayNode(a) {
      if (typeof a === 'string') return FRAME_HTML.test(a);      // insertAdjacentHTML, before('...')
      if (!a || (typeof a !== 'object' && typeof a !== 'function')) return false;
      var t;
      try { t = nodeTypeOf(a); } catch (e) { return true; }      // not a node (TrustedHTML...): may be HTML
      if (t === 11) return true;                                 // a fragment
      if (t !== 1) return false;                                 // text, comments
      try { return FRAMES[localNameOf(a)] === 1 || firstElementOf(a) !== null; } catch (e) { return true; }
    }
    var ownerOf = native(w.Node && w.Node.prototype, 'ownerDocument');
    var defaultViewOf = native(w.Document && w.Document.prototype, 'defaultView');
    var startContainerOf = native(w.AbstractRange && w.AbstractRange.prototype, 'startContainer') ||
      native(w.Range && w.Range.prototype, 'startContainer');
    var targetOf = native(w.Event && w.Event.prototype, 'target');
    var addedOf = native(w.MutationRecord && w.MutationRecord.prototype, 'addedNodes');
    var listLength = native(w.NodeList && w.NodeList.prototype, 'length');
    function mayAny(args) {
      for (var i = 0; i < args.length; i++) if (mayNode(args[i])) return true;
      return false;
    }
    // a node already in a document: moving it gives its frames new windows
    function placed(a) {
      if (!a || typeof a !== 'object') return false;
      try { return connectedOf(a) === true; } catch (e) { return false; }
    }
    // a target of this document (or outside any document), not of another one
    function ours(target) {
      return target === own || docOf(target) === own;
    }
    function hooked(obj, name) { hook(obj, name, false); }
    function swapped(obj, name) { hook(obj, name, true); }
    [w.HTMLIFrameElement, w.HTMLFrameElement, w.HTMLObjectElement, w.HTMLEmbedElement].forEach(function (E) {
      if (!E) return;
      getter(E.prototype, 'contentWindow', function (orig) {
        var cw = orig.call(this);
        adopt(cw);
        return cw;
      });
      getter(E.prototype, 'contentDocument', function (orig) {
        var d = orig.call(this);
        if (d) adopt(d.defaultView);
        return d;
      });
    });
    var N = w.Node && w.Node.prototype, E = w.Element && w.Element.prototype;
    ['appendChild', 'insertBefore'].forEach(function (n) { hooked(N, n); });
    swapped(N, 'replaceChild');
    [E, w.Document && w.Document.prototype, w.DocumentFragment && w.DocumentFragment.prototype]
      .forEach(function (p) {
        ['append', 'prepend'].forEach(function (n) { hooked(p, n); });
        swapped(p, 'replaceChildren');
      });
    [E, w.CharacterData && w.CharacterData.prototype].forEach(function (p) {
      ['before', 'after'].forEach(function (n) { hooked(p, n); });
      swapped(p, 'replaceWith');
    });
    ['insertAdjacentElement', 'insertAdjacentHTML'].forEach(function (n) { hooked(E, n); });
    swapped(E, 'setHTMLUnsafe');
    ['innerHTML', 'outerHTML'].forEach(function (n) { setter(E, n, after); });
    var opener = function (orig) {
      return function () {
        var r = orig.apply(this, arguments);
        adopt(r);
        return r;
      };
    };
    wrap(w, 'open', opener);
    wrap(w.Window && w.Window.prototype, 'open', opener);
    // the ways left that can put a frame into a page without the methods above
    var R = w.Range && w.Range.prototype;
    hooked(R, 'insertNode');
    // surroundContents takes the nodes it surrounds out and puts them back:
    // a frame among them gets a new window (independent review)
    swapped(R, 'surroundContents');
    hooked(E, 'moveBefore');
    var SR = w.ShadowRoot && w.ShadowRoot.prototype;
    setter(SR, 'innerHTML', after);
    swapped(SR, 'setHTMLUnsafe');
    swapped(w.Document && w.Document.prototype, 'execCommand');
    // and (1.1.18, independent review) a new body, a table's caption, head
    // or foot, and nodes put next to the doctype
    setter(w.Document && w.Document.prototype, 'body', function (node) { check(node, true); });
    var TB = w.HTMLTableElement && w.HTMLTableElement.prototype;
    ['caption', 'tHead', 'tFoot'].forEach(function (n) { setter(TB, n, function (node) { check(node, true); }); });
    var DT = w.DocumentType && w.DocumentType.prototype;
    ['before', 'after'].forEach(function (n) { hooked(DT, n); });
    swapped(DT, 'replaceWith');
    swapped(E, 'setHTML');
    // frames written in the page's own HTML: watched while the page is being
    // built (the parser inserts them, before the page's next script runs);
    // once it is built, every way in is one of the methods above, and
    // watching every change of the page cost DOM-heavy pages about a tenth
    // of their speed (1.1.18). If the end of the building is never seen,
    // the watch simply stays on, as before.
    // The end of the building is read from the engine itself (its own
    // readyState getter, a trusted event): a page cannot switch the watch off
    // early by faking either (1.1.18, independent review). A document opened
    // again (document.open, or document.write after the page was built) is
    // built anew by the parser, so the watch comes back for it.
    var MO = w.MutationObserver && w.MutationObserver.prototype;
    var moObserve = MO && MO.observe, moDisconnect = MO && MO.disconnect;
    var D = w.Document && w.Document.prototype;
    var readyStateOf = native(D, 'readyState');
    var addListener = w.EventTarget && w.EventTarget.prototype.addEventListener;
    var watch = null;
    function building() {
      try { return readyStateOf(own) === 'loading'; } catch (e) { return true; }
    }
    function built(ev) {
      if (!ev || ev.isTrusted !== true) return;
      check(null, false);
      if (watching && !building()) {
        try { RAPPLY(moDisconnect, watch, []); watching = false; } catch (e) {}
      }
    }
    function arm() {
      if (watching) return;
      try {
        // the parser's own insertions: a frame among them is looked at at once,
        // whatever the count (a frame removed and another written)
        if (!watch) watch = new w.MutationObserver(function (records) {
          var force = false;
          for (var i = 0; i < records.length && !force; i++) {
            var added, m;
            try { added = addedOf(records[i]); m = listLength(added); } catch (e) { force = true; break; }
            for (var j = 0; j < m; j++) if (mayNode(added[j])) { force = true; break; }
          }
          check(null, force);
        });
        RAPPLY(moObserve, watch, [own, { childList: true, subtree: true }]);
        watching = true;
      } catch (e) {}
      listen();
    }
    // the guard's listeners; added again after document.open, which removes
    // every listener of the document (independent review). The same function
    // added twice is kept once.
    function listen() {
      try {
        RAPPLY(addListener, own, ['DOMContentLoaded', built]);
        RAPPLY(addListener, own, ['readystatechange', built]);
        RAPPLY(addListener, own, ['load', loaded, true]);
      } catch (e) {}
    }
    // opening the document again: watched before the parser starts
    ['open', 'write', 'writeln'].forEach(function (n) {
      var d = D && Object.getOwnPropertyDescriptor(D, n);
      if (!d || typeof d.value !== 'function') return;
      var orig = d.value;
      var f = ({ [orig.name || n]() {
        // the document's own guard, whichever realm's open/write is used
        var g = GUARDS.get(this);
        if (g && (n === 'open' || !g.building())) g.arm();
        var r = RAPPLY(orig, this, arguments);
        if (g) { if (g.building()) g.arm(); g.listen(); }
        check(this, true);
        return r;
      } })[orig.name || n];
      try { Object.defineProperty(f, 'length', { value: orig.length, configurable: true }); } catch (e) {}
      natives.set(f, natives.get(orig) || origToString.call(orig));
      d.value = f;
      try { Object.defineProperty(D, n, d); } catch (e) {}
    });
    // A frame sent to a new empty page (location.replace('about:blank'),
    // its src set again...) gets a new set of built-in objects that the
    // engine adds no script to; it is protected when it has loaded, before
    // the page's own listeners hear of it (they come after this one, which
    // listens on the way down to the frame).
    function loaded(ev) {
      var t, name;
      try { t = targetOf(ev); } catch (e) { return; }
      if (t === own || !framesOf(w)) return;
      try { name = localNameOf(t); } catch (e) { return; }
      if (FRAMES[name] === 1) sweep(w);
    }
    GUARDS.set(own, { arm: arm, building: building, listen: listen });
    arm();
    if (!building()) built({ isTrusted: true });
    check(null, true);
  }

  install(window);
  // the page's own realm is known as protected: asking it again (a page that
  // calls window.open('', '_self')) never goes through functions it can replace
  try { realms.add(window.Function); } catch (e) {}
})();
