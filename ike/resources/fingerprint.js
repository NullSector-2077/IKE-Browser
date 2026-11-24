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
  // The same for everything the protection itself uses while a page runs
  // (review of 1.1.19, N4): a page that replaced WeakSet.prototype.has,
  // Promise.prototype.then, the length of typed arrays or Math.imul could
  // otherwise skip the noise, see what the protection keeps, or be handed
  // the real values. Its collections have their methods as own, frozen
  // properties, which nothing on a prototype can reach.
  var GOPD = Object.getOwnPropertyDescriptor, FREEZE = Object.freeze;
  function getterOf(proto, name) {
    try { var d = proto && GOPD(proto, name); return d && d.get; } catch (e) { return undefined; }
  }
  var WS_ = WeakSet, WS_HAS = WeakSet.prototype.has, WS_ADD = WeakSet.prototype.add;
  var WM_ = WeakMap, WM_GET = WeakMap.prototype.get, WM_SET = WeakMap.prototype.set;
  function hardSet() {
    var s = new WS_();
    return FREEZE({
      has: function (o) { return RAPPLY(WS_HAS, s, [o]); },
      add: function (o) { RAPPLY(WS_ADD, s, [o]); return this; }
    });
  }
  function hardMap() {
    var m = new WM_();
    return FREEZE({
      get: function (k) { return RAPPLY(WM_GET, m, [k]); },
      set: function (k, v) { RAPPLY(WM_SET, m, [k, v]); return this; }
    });
  }
  var THEN = Promise.prototype.then, DEFPROP = Object.defineProperty, SPECIES = Symbol.species;
  // A promise of the engine's, given a reaction of the protection: then()
  // asks the promise for its constructor (the "species"), and a getter on
  // Promise.prototype.constructor was handed the engine's own promise, with
  // the real values (verification of 1.1.20, V-1). An own constructor of
  // the promise answers first; P is the promise class of its realm.
  function then(p, fn, P) {
    try {
      var sp = {};
      DEFPROP(sp, SPECIES, { value: P || Promise });
      DEFPROP(p, 'constructor', { value: sp, configurable: true });
    } catch (e) {}
    return RAPPLY(THEN, p, [fn]);
  }
  // an element written without asking the prototype chain: a setter on
  // Array.prototype's index names was handed every element (V-2)
  function put(a, i, v) {
    DEFPROP(a, i, { value: v, writable: true, enumerable: true, configurable: true });
    return v;
  }
  // strings and arrays the same way (fingerprinting audit, H-A)
  var S_SLICE = String.prototype.slice, S_INDEX = String.prototype.indexOf, S_LOWER = String.prototype.toLowerCase;
  function sslice(s, a, b) { return RAPPLY(S_SLICE, s, b === undefined ? [a] : [a, b]); }
  function sindex(s, x, from) { return RAPPLY(S_INDEX, s, from === undefined ? [x] : [x, from]); }
  function lower(s) { return RAPPLY(S_LOWER, s, []); }
  var HASOWN = Object.prototype.hasOwnProperty, RE_EXEC = RegExp.prototype.exec, RE_TEST = RegExp.prototype.test;
  function own(o, k) { return RAPPLY(HASOWN, o, [k]); }
  var M_ = Map, M_GET = Map.prototype.get, M_SET = Map.prototype.set, M_DEL = Map.prototype['delete'];
  function hardStrongMap() {
    var m = new M_();
    return FREEZE({
      get: function (k) { return RAPPLY(M_GET, m, [k]); },
      set: function (k, v) { RAPPLY(M_SET, m, [k, v]); return this; },
      'delete': function (k) { return RAPPLY(M_DEL, m, [k]); }
    });
  }
  var BLOB_SIZE = getterOf(window.Blob && Blob.prototype, 'size');
  var BLOB_TYPE = getterOf(window.Blob && Blob.prototype, 'type');
  function isBlob(o) { try { RAPPLY(BLOB_SIZE, o, []); return true; } catch (e) { return false; } }
  // the first part of a version ("140" of "140.0.7339.264")
  function majorOf(v) { var s = `${v}`, i = sindex(s, '.'); return i < 0 ? s : sslice(s, 0, i); }
  var TA_PROTO = Object.getPrototypeOf(Uint8Array.prototype);
  var TA_LEN = getterOf(TA_PROTO, 'length'), TA_TAG = getterOf(TA_PROTO, Symbol.toStringTag);
  function LEN(a) { return RAPPLY(TA_LEN, a, []); }
  function TAG(a) { try { return RAPPLY(TA_TAG, a, []); } catch (e) { return undefined; } }
  var IMG_DATA = getterOf(window.ImageData && ImageData.prototype, 'data');
  function pixels(img) { return RAPPLY(IMG_DATA, img, []); }
  function setterOf(proto, name) {
    try { var d = proto && GOPD(proto, name); return d && d.set; } catch (e) { return undefined; }
  }
  // what the noisy copy of a canvas is made with: a page that changed the
  // size it reports, or getContext, drawImage or putImageData, made the copy
  // fail, and the real picture was given out instead
  var HCP = window.HTMLCanvasElement && HTMLCanvasElement.prototype;
  var C2P = window.CanvasRenderingContext2D && CanvasRenderingContext2D.prototype;
  var OC = window.OffscreenCanvas, OCP = OC && OC.prototype;
  var O2P = window.OffscreenCanvasRenderingContext2D && OffscreenCanvasRenderingContext2D.prototype;
  var CV = {
    w: getterOf(HCP, 'width'), h: getterOf(HCP, 'height'), sw: setterOf(HCP, 'width'), sh: setterOf(HCP, 'height'),
    ctx: HCP && HCP.getContext, draw: C2P && C2P.drawImage, put: C2P && C2P.putImageData,
    make: Document.prototype.createElement,
    ow: getterOf(OCP, 'width'), oh: getterOf(OCP, 'height'), octx: OCP && OCP.getContext,
    odraw: O2P && O2P.drawImage, oput: O2P && O2P.putImageData
  };
  // the noise for what getImageData gives: one byte per colour only; other
  // formats (floats) are left to the engine's own values
  var DVP = window.DataView && DataView.prototype;
  var TV = FREEZE({ RA: RAPPLY, tag: TA_TAG, buf: getterOf(TA_PROTO, 'buffer'), off: getterOf(TA_PROTO, 'byteOffset'),
    blen: getterOf(TA_PROTO, 'byteLength'), dvBuf: getterOf(DVP, 'buffer'), dvOff: getterOf(DVP, 'byteOffset'),
    dvLen: getterOf(DVP, 'byteLength'), abLen: getterOf(ArrayBuffer.prototype, 'byteLength'),
    sabLen: getterOf(window.SharedArrayBuffer && SharedArrayBuffer.prototype, 'byteLength'),
    U8: Uint8Array, U16: Uint16Array });
  function noiseImage(img) {
    var px = pixels(img), tag = TAG(px);
    if (tag === 'Uint8ClampedArray') farble(px, seed, rng, LEN(px));
    // a 16-bit float picture: its own noise; the byte noise made values 0 or 1
    else if (tag === 'Float16Array') viewNoise(TV, px, 0, -1, seed, rng, farble, true);
  }
  // a 32-bit multiply of our own (Math.imul belongs to the page)
  // a sample's float32 bits (made before any page script runs)
  var F32 = new Float32Array(1), B32 = new Uint32Array(F32.buffer);
  function bitsOf(x) { F32[0] = x; return B32[0] >>> 9; }
  function mul32(a, b) {
    var lo = (a & 0xffff) * b, hi = ((a >>> 16) * b) & 0xffff;
    return (lo + (hi << 16)) | 0;
  }
  // the number of frames of a window, from the engine's own getter: a page
  // writing window.length = 0 hid every new frame from the guard (1.1.18,
  // independent review; the same in 1.1.17)
  var LENGTH = (function () {
    var d = Object.getOwnPropertyDescriptor(window, 'length');
    return d && d.get;
  })();
  var lengthOf = LENGTH ? RAPPLY(BIND, CALL, [LENGTH]) : null;   // a bound call: no array per call (1.1.24)
  function framesOf(win) {
    try { return lengthOf ? lengthOf(win) : win.length; } catch (e) { return 0; }
  }
  // the guards of the documents protected by this script, so that one
  // realm's document.open/write on another realm's document re-arms the
  // right watch (1.1.18, independent review)
  var GUARDS = hardMap();

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
      if (RAPPLY(Object.prototype.hasOwnProperty, CFG.sites, [h])) return CFG.sites[h];
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
      h = mul32(h, 16777619) >>> 0;
    }
    return h;
  }
  // Registrable domain ("bbc.co.uk", not "co.uk"), so unrelated sites never
  // share a seed.
  var SLD = { co: 1, com: 1, org: 1, net: 1, gov: 1, edu: 1, ac: 1, or: 1, ne: 1, go: 1, gob: 1,
    nom: 1, mil: 1, ltd: 1, plc: 1, sch: 1, nhs: 1, me: 1, info: 1, id: 1, gv: 1 };
  var HOSTED = /\.(github\.io|gitlab\.io|blogspot\.com|herokuapp\.com|pages\.dev|workers\.dev|netlify\.app|vercel\.app|web\.app|firebaseapp\.com|appspot\.com|cloudfront\.net|azurewebsites\.net|onrender\.com|neocities\.org|wordpress\.com|tumblr\.com|s3\.amazonaws\.com|pp\.ua|myshopify\.com|substack\.com|wixsite\.com|weebly\.com|fly\.dev|glitch\.me|repl\.co|surge\.sh|ngrok\.io|ngrok-free\.app|duckdns\.org|no-ip\.org)$/;
  // The Public Suffix List (1.1.21, fingerprinting audit L-2), from the
  // system's copy (shields.py psl_codes): each rule as the 24-bit FNV-1a hash
  // of its text in four sortable characters, sorted. The short lists above
  // only when the list is missing.
  var PSL = typeof CFG.psl === 'string' ? CFG.psl : '';
  var PSL_DIGITS = '-.0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz';
  function inPsl(rule) {
    var v = hash(rule) >>> 8, code = '';
    for (var k = 18; k >= 0; k -= 6) code += PSL_DIGITS.charAt((v >>> k) & 63);
    var lo = 0, hi = (PSL.length / 4) | 0;
    while (lo < hi) {
      var mid = (lo + hi) >>> 1, at = PSL.substr(mid * 4, 4);
      if (at === code) return true;
      if (at < code) lo = mid + 1; else hi = mid;
    }
    return false;
  }
  function siteOf(h) {
    if (!h || /^[\d.]+$/.test(h) || h.indexOf(':') >= 0) return h;
    var p = h.split('.');
    if (PSL) {
      // as shields.py _site_psl: the first suffix of the list, and one label more
      for (var i = 0; i < p.length; i++) {
        var cand = p.slice(i).join('.');
        if (inPsl('!' + cand)) return cand;
        if ((p.length - i >= 2 && inPsl(cand)) || (i + 1 < p.length && inPsl('*.' + p.slice(i + 1).join('.')))) {
          return i > 0 ? p.slice(i - 1).join('.') : h;
        }
      }
      return p.slice(-2).join('.');
    }
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
  // window.name across sites (1.1.21, fingerprinting audit L-3): a page could
  // write an identifier there and read it back on another site the tab moved
  // to (Firefox and Tor Browser empty it). Emptied in a top-level document
  // that another site (or nothing: a typed address, a bookmark) led to, on a
  // new navigation (not a reload or a step back or forward), in a tab not
  // opened by a script (a pop-up keeps the name its opener targets it by).
  try {
    if (window.top === window && !window.opener && window.name !== '') {
      var navs = performance.getEntriesByType('navigation');
      var how = navs && navs.length ? navs[0].type : 'navigate';
      var from = '';
      try { from = document.referrer ? new URL(document.referrer).hostname : ''; } catch (e) {}
      if (how === 'navigate' && (!from || siteOf(from) !== siteOf(location.hostname))) window.name = '';
    }
  } catch (e) {}
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
  // Invisible noise, always the same for one site in one session. Which
  // pixel is changed, and to what, depends on the site's key and on the
  // pixel's own colour and that of the pixel before it, the lowest bits left
  // out (review 4, N3). Not on the place in the picture, nor on the whole
  // picture: before, one changed corner changed the noise everywhere, and a
  // majority vote over a few such reads gave the real picture back; a grey
  // canvas of the same size gave the pattern away before 1.1.20 (H1). A
  // second read, or the noisy pixels written back and read again, give the
  // same pixels: the lowest bit is set to the noise, not flipped.
  // n is the length, read by the caller through the engine's own getter;
  // nothing a page can replace is used here (review of 1.1.19, N4).
  // Self-contained: it also runs inside workers (passed by its source).
  function farble(data, seed, rng, n) {
    var step = n > 400000 ? 4 * (((n + 399999) / 400000) | 0) : 4, prev = 0;
    for (var i = 0; i + 3 < n; i += step) {
      var word = (data[i] & 254) | ((data[i + 1] & 254) << 8) | ((data[i + 2] & 254) << 16) | (data[i + 3] << 24);
      if (data[i + 3] !== 0) {
        // the multiply by the FNV prime written as shifts (no Math.imul)
        var h = (seed ^ word) | 0;
        h = (h + (h << 1) + (h << 4) + (h << 7) + (h << 8) + (h << 24)) | 0;
        h ^= prev;
        h = (h + (h << 1) + (h << 4) + (h << 7) + (h << 8) + (h << 24)) | 0;
        h ^= h >>> 15;
        h = (h + (h << 1) + (h << 4) + (h << 7) + (h << 8) + (h << 24)) | 0;
        h ^= h >>> 13;
        if ((h & 7) === 0) {
          var c = i + ((h >>> 3) & 0xffff) % 3;
          data[c] = (data[c] & 254) | ((h >>> 20) & 1);
        }
      }
      prev = word;
    }
  }
  // A @font-face source list without its local() entries: comments taken
  // out and CSS escapes decoded first, entries split at the commas outside
  // quotes and brackets. Nothing left: a local() of no font at all.
  // Self-contained: it also runs inside workers (passed by its source).
  function cssLocal(text, fcp) {
    var LOW = { A: 'a', B: 'b', C: 'c', D: 'd', E: 'e', F: 'f', G: 'g', H: 'h', I: 'i', J: 'j', K: 'k', L: 'l', M: 'm',
      N: 'n', O: 'o', P: 'p', Q: 'q', R: 'r', S: 's', T: 't', U: 'u', V: 'v', W: 'w', X: 'x', Y: 'y', Z: 'z' };
    var HEX = { 0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6, 7: 7, 8: 8, 9: 9, a: 10, b: 11, c: 12, d: 13, e: 14, f: 15,
      A: 10, B: 11, C: 12, D: 13, E: 14, F: 15 };
    var WS = { ' ': 1, '\t': 1, '\n': 1, '\r': 1, '\f': 1 };
    var t = '', i = 0, n = text.length;
    while (i < n) {
      var ch = text[i];
      if (ch === '/' && text[i + 1] === '*') {
        var e = i + 2;
        while (e < n && !(text[e] === '*' && text[e + 1] === '/')) e++;
        i = e + 2;
        continue;
      }
      if (ch === '\\' && i + 1 < n) {
        var h = 0, k = i + 1, d = 0;
        while (k < n && d < 6 && HEX[text[k]] !== undefined) { h = h * 16 + HEX[text[k]]; k++; d++; }
        if (d) {
          if (WS[text[k]] === 1) k++;
          t += fcp(h === 0 || h > 0x10FFFF || (h >= 0xD800 && h <= 0xDFFF) ? 0xFFFD : h);
          i = k;
        } else { t += text[i + 1]; i += 2; }
        continue;
      }
      t += ch;
      i++;
    }
    var out = '', entry = '', depth = 0, q = '', kept = 0;
    var flush = function () {
      var s0 = 0, z = entry.length, head = '';
      while (s0 < z && WS[entry[s0]] === 1) s0++;
      for (var j = s0; j < z && j < s0 + 6; j++) head += LOW[entry[j]] || entry[j];
      if (s0 < z && head !== 'local(') out += (kept++ ? ',' : '') + entry;
      entry = '';
    };
    for (i = 0; i < t.length; i++) {
      var c = t[i];
      if (q) { if (c === q) q = ''; entry += c; continue; }
      if (c === '"' || c === "'") { q = c; entry += c; continue; }
      if (c === '(') depth++;
      else if (c === ')') depth--;
      if (c === ',' && depth <= 0) { flush(); continue; }
      entry += c;
    }
    flush();
    return kept ? out : 'local("x-absent")';
  }
  // Noise for bytes the engine wrote into a buffer of the page's
  // (fingerprinting audit, H-E): any typed array (of any realm or kind), a
  // DataView or an ArrayBuffer; `from` bytes into it, `count` bytes (or to
  // its end when count < 0). half: the values are 16-bit floats (an HDR
  // canvas): the lowest bit of the chosen values is set, not of bytes (M-8).
  // T holds the engine's own getters, taken before the page ran.
  // Self-contained: it also runs inside workers (passed by its source).
  function viewNoise(T, target, from, count, seed, rng, farble, half) {
    var buf, off, len, tag;
    try { tag = T.RA(T.tag, target, []); } catch (e) { tag = undefined; }
    try {
      if (tag !== undefined) {
        buf = T.RA(T.buf, target, []); off = T.RA(T.off, target, []); len = T.RA(T.blen, target, []);
      } else {
        try { buf = T.RA(T.dvBuf, target, []); off = T.RA(T.dvOff, target, []); len = T.RA(T.dvLen, target, []); }
        catch (e) {
          // an ArrayBuffer, or a SharedArrayBuffer (verification V-9)
          try { len = T.RA(T.abLen, target, []); } catch (e2) { len = T.RA(T.sabLen, target, []); }
          buf = target; off = 0;
        }
      }
    } catch (e) { return; }
    from = from > 0 ? from : 0;
    var n = count >= 0 && from + count < len ? count : len - from;
    if (n <= 0) return;
    if (!half) { farble(new T.U8(buf, off + from, n), seed, rng, n); return; }
    // 16-bit floats (target is the Float16Array itself): the noise at the
    // scale of 8-bit colours, as farble makes it, so the picture rounded to
    // 8 bits is the noisy one too (verification V-6: a change in the last
    // place of a float was an eighth of one 8-bit step, and rounding undid it)
    var m = n >> 1, b = new T.U8(m), was = new T.U8(m);
    for (var k = 0; k < m; k++) {
      var v = target[k] * 255 + 0.5;
      v = v > 0 ? (v < 255 ? v : 255) : 0;
      b[k] = v; was[k] = v;
    }
    farble(b, seed, rng, m);
    for (k = 0; k < m; k++) if (b[k] !== was[k]) target[k] = target[k] + (b[k] - was[k]) / 255;
  }
  // WebGL reads with the noise (fingerprinting audit H-E; verification V-5:
  // every number is read once and the engine called with the values read,
  // so a type, target or offset given as text or as an object cannot skip
  // it). Byte arrays only: float reads stay exact. A WebGL2 pixel-pack
  // buffer filled by readPixels is marked; getBufferSubData of a marked
  // buffer adds the noise, copyBufferSubData carries the mark.
  // Self-contained: it also runs inside workers (passed by its source).
  function glReads(GLP, wrap, RA, tagOf, noise, packed, getParam) {
    var BIND = { 34962: 34964, 34963: 34965, 35051: 35053, 35052: 35055, 36662: 36662, 36663: 36663,
      35982: 35983, 35345: 35368 };
    var ll = function (v) { var x = +v; return x === x && x !== 1 / 0 && x !== -1 / 0 ? x - x % 1 : 0; };
    var bytes = function (v) {
      var t;
      try { t = tagOf(v); } catch (e) { return false; }
      return t === 'Uint8Array' || t === 'Uint8ClampedArray';
    };
    wrap(GLP, 'readPixels', function (orig) {
      return function (x, y, width, height, format, type, dst, dstOffset) {
        var n = arguments.length;
        if (n < 7) return RA(orig, this, arguments);
        var view = dst !== null && typeof dst === 'object';
        var d = view || dst === null || dst === undefined ? dst : ll(dst);
        var a = n > 7 ? [x | 0, y | 0, width | 0, height | 0, format >>> 0, type >>> 0, d, dstOffset >>> 0]
          : [x | 0, y | 0, width | 0, height | 0, format >>> 0, type >>> 0, d];
        var r = RA(orig, this, a);
        if (view) {
          if (bytes(dst)) noise(dst, n > 7 ? a[7] : 0, a[4] === 0x1908 && a[5] === 0x1401 ? (a[2] >>> 0) * (a[3] >>> 0) * 4 : -1);
        } else if (dst !== null && a[5] === 0x1401 && getParam) {
          var pb = RA(getParam, this, [0x88ED]);              // PIXEL_PACK_BUFFER_BINDING
          if (pb) packed.add(pb);
        }
        return r;
      };
    });
    wrap(GLP, 'getBufferSubData', function (orig) {
      return function (target, srcOffset, dst, dstOffset, length) {
        var n = arguments.length;
        if (n < 3) return RA(orig, this, arguments);
        var t = target >>> 0, so = ll(srcOffset);
        var a = n > 4 ? [t, so, dst, dstOffset >>> 0, length >>> 0] : n > 3 ? [t, so, dst, dstOffset >>> 0] : [t, so, dst];
        var r = RA(orig, this, a), bd = BIND[t];
        var held = bd && getParam ? RA(getParam, this, [bd]) : null;
        if (held && packed.has(held) && bytes(dst)) noise(dst, n > 3 ? a[3] : 0, n > 4 && a[4] > 0 ? a[4] : -1);
        return r;
      };
    });
    wrap(GLP, 'copyBufferSubData', function (orig) {
      return function (readTarget, writeTarget, readOffset, writeOffset, size) {
        var rt = readTarget >>> 0, wt = writeTarget >>> 0;
        var r = RA(orig, this, arguments.length < 5 ? arguments : [rt, wt, ll(readOffset), ll(writeOffset), ll(size)]);
        if (getParam && BIND[rt] && BIND[wt]) {
          var from = RA(getParam, this, [BIND[rt]]);
          if (from && packed.has(from)) {
            var to = RA(getParam, this, [BIND[wt]]);
            if (to) packed.add(to);
          }
        }
        return r;
      };
    });
  }
  // ---- values shared by every realm and by workers ---------------------------
  var realCores = navigator.hardwareConcurrency || 4;
  // A number of cores that most computers report, so the value itself is
  // common: 4 or 8, no more than the computer has (and 4 at least). Balanced
  // picks one of them per site; Strict and above always the higher one.
  // Before 1.1.21 rarer values (2, 6, 12) were picked too, and made the
  // browser stand out (Cover Your Tracks: "2 cores", 5.7 bits).
  var usual = [4, 8].filter(function (n) { return n <= Math.max(realCores, 4); });
  var cores = strict ? usual[usual.length - 1] : usual[seed % usual.length];
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
  // No method of the page's is used: a page that replaced toLowerCase was
  // handed the real card's name (fingerprinting audit, H-A).
  function gpuFor(real, gpus, pick) {
    var s = `${real || ''}`, UP = { n: 'N', v: 'V', i: 'I', d: 'D', a: 'A', t: 'T', e: 'E', l: 'L' };
    var has = function (w) {
      for (var i = 0; i + w.length <= s.length; i++) {
        for (var j = 0; j < w.length; j++) if (s[i + j] !== w[j] && s[i + j] !== UP[w[j]]) break;
        if (j === w.length) return true;
      }
      return false;
    };
    // a table with no prototype: no setter of the page's sees the models
    var f = has('nvidia') ? 'nvidia' : (has('intel') ? 'intel' : ''), pool = { __proto__: null }, m = 0;
    for (var k = 0; k < gpus.length; k++) if (!f || gpus[k][2] === f) pool[m++] = gpus[k];
    return pool[pick % m];
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
  var SCREENS = [[1280, 720], [1366, 768], [1440, 900], [1536, 864], [1600, 900], [1680, 1050],
    [1920, 1080], [1920, 1200], [2560, 1080], [2560, 1440], [3440, 1440], [3840, 2160]];
  function usualScreen(w, h) {
    for (var i = 0; i < SCREENS.length; i++) {
      if (SCREENS[i][0] >= w && SCREENS[i][1] >= h) return SCREENS[i];
    }
    return [w, h];
  }

  // Media queries on the screen's size (1.1.21, fingerprinting audit M-2): a
  // binary search with matchMedia('(min-device-width: Npx)') gave the real
  // size behind Strict's usual one. matchMedia now answers device-width,
  // device-height and device-aspect-ratio (min-/max-, and the range form
  // "device-width >= 800px") for the shown size: each such feature becomes
  // one that is always true or always false, and the engine evaluates the
  // rest. A feature it cannot read (calc(), units of the viewport) makes the
  // query false. Style sheets' own @media still see the real size: the engine
  // evaluates them (a stated limit, docs/SECURITY.md). Only the captured
  // built-ins are used: it runs while the page does.
  var MQ_TRUE = '(width >= 0px)', MQ_FALSE = '(width < 0px)';
  var MQ_PLAIN = /^\s*(min-|max-)?device-(width|height|aspect-ratio)\s*(?::\s*([^]*?))?\s*$/;
  var MQ_RANGE = /^\s*(?:([^<>=]+?)\s*(<=|>=|<|>|=)\s*)?device-(width|height|aspect-ratio)\s*(?:(<=|>=|<|>|=)\s*([^<>=]+?))?\s*$/;
  var MQ_LEN = /^(-?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?)(px|em|rem|in|cm|mm|pt|pc|q)?$/;
  var MQ_RATIO = /^((?:\d+\.?\d*|\.\d+))\s*(?:\/\s*((?:\d+\.?\d*|\.\d+)))?$/;
  var MQ_UNIT = { px: 1, em: 16, rem: 16, 'in': 96, cm: 96 / 2.54, mm: 96 / 25.4, pt: 96 / 72, pc: 16, q: 96 / 101.6 };
  function mqValue(kind, text) {
    if (text === undefined) return NaN;
    var t = text, m;
    while (t.length && (t[t.length - 1] === ' ' || t[0] === ' ')) t = t[0] === ' ' ? sslice(t, 1) : sslice(t, 0, -1);
    if (kind === 'aspect-ratio') {
      m = RAPPLY(RE_EXEC, MQ_RATIO, [t]);
      if (!m) return NaN;
      var b = m[2] === undefined ? 1 : +m[2];
      return b > 0 ? +m[1] / b : NaN;
    }
    m = RAPPLY(RE_EXEC, MQ_LEN, [t]);
    if (!m || (m[2] === undefined && +m[1] !== 0)) return NaN;
    return +m[1] * (m[2] === undefined ? 1 : MQ_UNIT[m[2]]);
  }
  function mqCompare(a, op, b) {
    var eq = Math.abs(a - b) < 1e-6;
    return op === '=' ? eq : op === '<' ? a < b && !eq : op === '<=' ? a < b || eq
      : op === '>' ? a > b && !eq : a > b || eq;
  }
  function mqFeature(c, W, H) {
    // true, false, or null (not a feature of the screen's size it can read)
    var m = RAPPLY(RE_EXEC, MQ_PLAIN, [c]), v, x;
    if (m) {
      v = m[2] === 'width' ? W : m[2] === 'height' ? H : W / H;
      if (m[3] === undefined) return m[1] ? null : v !== 0;
      x = mqValue(m[2], m[3]);
      if (x !== x) return null;
      return mqCompare(v, m[1] === 'min-' ? '>=' : m[1] === 'max-' ? '<=' : '=', x);
    }
    m = RAPPLY(RE_EXEC, MQ_RANGE, [c]);
    if (!m || (m[2] === undefined && m[4] === undefined)) return null;
    v = m[3] === 'width' ? W : m[3] === 'height' ? H : W / H;
    var ok = true;
    if (m[2] !== undefined) {
      x = mqValue(m[3], m[1]);
      if (x !== x) return null;
      ok = mqCompare(x, m[2], v);
    }
    if (m[4] !== undefined) {
      x = mqValue(m[3], m[5]);
      if (x !== x) return null;
      ok = ok && mqCompare(v, m[4], x);
    }
    return ok;
  }
  function mqRewrite(text, W, H) {
    // the query with every screen-size feature replaced; 'not all' when one
    // cannot be read
    var low = lower(text), out = '', i = 0;
    for (;;) {
      var d = sindex(low, 'device-', i);
      if (d < 0) break;
      var a = d;
      while (a > i && low[a - 1] !== '(' && low[a - 1] !== ')') a--;
      var b = sindex(low, ')', d);
      if (a <= i || low[a - 1] !== '(' || b < 0 || sindex(sslice(low, a, b), '(') >= 0) return 'not all';
      var r = mqFeature(sslice(low, a, b), W, H);
      if (r === null) return 'not all';
      out += sslice(text, i, a - 1) + (r ? MQ_TRUE : MQ_FALSE);
      i = b + 1;
    }
    return out + sslice(text, i);
  }

  // ---- plugins ------------------------------------------------------------
  // The two invented plugins answer through the engine's own getters and
  // methods (Plugin.prototype, PluginArray.prototype), as real entries do:
  // they had own properties, and the prototype's getters and item() threw
  // on them and on the list (fingerprinting audit, M-6). No method of the
  // page's is used to make them (audit, H-A).
  var PLUGIN_VIEWS = hardMap(), PLUGIN_FAKES = hardMap(), NONE = {};
  var R_GET = Reflect.get, R_HAS = Reflect.has, O_CREATE = Object.create, R_OWNKEYS = Reflect.ownKeys;
  var R_GOPD = Reflect.getOwnPropertyDescriptor, R_CONSTRUCT = Reflect.construct;
  var CAPS = { b: 'B', c: 'C', d: 'D', f: 'F', g: 'G', h: 'H', j: 'J', k: 'K', l: 'L', m: 'M', n: 'N', p: 'P',
    r: 'R', s: 'S', t: 'T', v: 'V', w: 'W', z: 'Z' };
  function word(next, len, low) {
    var a = 'bcdfghjklmnprstvwz', b = 'aeiou', out = '';
    for (var i = 0; i < len; i++) {
      var set = i % 2 ? b : a, ch = set[next() % set.length];
      out += i === 0 && !low ? CAPS[ch] || ch : ch;
    }
    return out;
  }
  function isIndex(p) {
    if (!p.length) return false;
    for (var i = 0; i < p.length; i++) if (p[i] < '0' || p[i] > '9') return false;
    return true;
  }
  function pluginList(w, real, PA) {
    var next = rng(seed ^ 0x51ed27), fakes = { __proto__: null, length: 2 }, n = RAPPLY(PA.len, real, []);
    var proto = w.Plugin ? w.Plugin.prototype : w.Object.prototype;
    for (var i = 0; i < 2; i++) {
      var f = O_CREATE(proto);
      PLUGIN_FAKES.set(f, { name: word(next, 6 + next() % 5) + ' ' + word(next, 5 + next() % 4),
        description: word(next, 7 + next() % 6), filename: word(next, 8 + next() % 5, true) });
      fakes[i] = f;
    }
    var info = {
      real: real, n: n + fakes.length,
      at: function (k) { return k < n ? real[k] : fakes[k - n]; },
      named: function (name) {
        var r = RAPPLY(PA.named, real, [name]);
        if (r) return r;
        for (var k = 0; k < fakes.length; k++) if (PLUGIN_FAKES.get(fakes[k]).name === name) return fakes[k];
        return null;
      }
    };
    var view = new w.Proxy(real, {
      get: function (t, prop) {
        if (prop === 'length') return info.n;
        if (typeof prop === 'string') {
          if (isIndex(prop)) return info.at(+prop);
          var v = R_GET(t, prop, t);
          if (v === undefined) { var hit = info.named(prop); if (hit) return hit; }
          return v;       // the prototype's own functions, which answer for this view
        }
        return R_GET(t, prop, t);     // the iterator reads through this view
      },
      has: function (t, prop) {
        if (typeof prop === 'string' && isIndex(prop)) return +prop < info.n;
        return R_HAS(t, prop);
      },
      // its own keys and entries list the invented ones too (verification
      // V-11: 5 keys with a length of 7)
      ownKeys: function (t) {
        var keys = [], all = R_OWNKEYS(t), k;
        for (k = 0; k < info.n; k++) put(keys, keys.length, '' + k);
        for (k = 0; k < all.length; k++) if (typeof all[k] !== 'string' || !isIndex(all[k])) put(keys, keys.length, all[k]);
        for (k = 0; k < fakes.length; k++) put(keys, keys.length, PLUGIN_FAKES.get(fakes[k]).name);
        return keys;
      },
      getOwnPropertyDescriptor: function (t, prop) {
        if (typeof prop === 'string' && isIndex(prop) && +prop < info.n) {
          return { value: info.at(+prop), writable: false, enumerable: true, configurable: true };
        }
        var d = R_GOPD(t, prop);
        if (d || typeof prop !== 'string') return d;
        for (var k = 0; k < fakes.length; k++) {
          if (PLUGIN_FAKES.get(fakes[k]).name === prop) return { value: fakes[k], writable: false, enumerable: false, configurable: true };
        }
        return undefined;
      }
    });
    PLUGIN_VIEWS.set(view, info);
    return view;
  }
  function pluginPrototypes(w) {
    var PAP = w.PluginArray && w.PluginArray.prototype, PP = w.Plugin && w.Plugin.prototype;
    function answer(proto, name, pick) {
      var d = proto && GOPD(proto, name);
      if (!d || !d.get) return;
      var orig = d.get;
      d.get = accessor(name, function () { var r = pick(this); return r !== NONE ? r : RAPPLY(orig, this, []); }, orig);
      try { Object.defineProperty(proto, name, d); } catch (e) {}
    }
    answer(PAP, 'length', function (me) { var i = PLUGIN_VIEWS.get(me); return i ? i.n : NONE; });
    wrap(PAP, 'item', function (orig) {
      return function (k) {
        var i = PLUGIN_VIEWS.get(this);
        if (!i || !arguments.length) return RAPPLY(orig, i ? i.real : this, arguments);
        return i.at(k >>> 0) || null;
      };
    });
    wrap(PAP, 'namedItem', function (orig) {
      return function (name) {
        var i = PLUGIN_VIEWS.get(this);
        if (!i || !arguments.length) return RAPPLY(orig, i ? i.real : this, arguments);
        return i.named(`${name}`);
      };
    });
    wrap(PAP, 'refresh', function (orig) {
      return function () { var i = PLUGIN_VIEWS.get(this); return RAPPLY(orig, i ? i.real : this, arguments); };
    });
    ['name', 'description', 'filename', 'length'].forEach(function (k) {
      answer(PP, k, function (me) { var v = PLUGIN_FAKES.get(me); return v ? (k === 'length' ? 0 : v[k]) : NONE; });
    });
    ['item', 'namedItem'].forEach(function (k) {
      wrap(PP, k, function (orig) {
        return function () { return PLUGIN_FAKES.get(this) && arguments.length ? null : RAPPLY(orig, this, arguments); };
      });
    });
  }


  // ---- making replaced functions look native --------------------------------
  // An error thrown through a replaced function (a wrong object, say) had
  // the protection's own lines in its stack ("userscript:..."): they are
  // taken out, as the engine's own functions have no lines there either
  // (fingerprinting audit, M-5)
  function clean(e) {
    try {
      if (e === null || (typeof e !== 'object' && typeof e !== 'function')) return;
      var st = e.stack;
      if (typeof st !== 'string' || sindex(st, 'userscript:') < 0) return;
      // line by line with the captured indexOf and slice: split() asked
      // the page's String.prototype[Symbol.split] (V-12)
      var out = '', from = 0, first = true;
      for (;;) {
        var nl = sindex(st, '\n', from), line = nl < 0 ? sslice(st, from) : sslice(st, from, nl);
        if (sindex(line, 'userscript:') < 0) { out += (first ? '' : '\n') + line; first = false; }
        if (nl < 0) break;
        from = nl + 1;
      }
      e.stack = out;
    } catch (x) {}
  }
  var natives = hardMap();         // replacement -> source text of the original
  function method(name, impl, orig) {
    var holder = { [name]() { try { return RAPPLY(impl, this, arguments); } catch (e) { clean(e); throw e; } } };
    var f = holder[name];
    try { Object.defineProperty(f, 'length', { value: orig.length, configurable: true }); } catch (e) {}
    natives.set(f, RAPPLY(origToString, orig, []));
    return f;
  }
  function accessor(name, impl, orig) {
    var holder = { get [name]() { try { return RAPPLY(impl, this, []); } catch (e) { clean(e); throw e; } } };
    var g = Object.getOwnPropertyDescriptor(holder, name).get;
    natives.set(g, orig ? RAPPLY(origToString, orig, []) : 'function get ' + name + '() { [native code] }');
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
    // the engine's own getter first: on a wrong object it throws as in
    // Chrome ("Illegal invocation"); a replacement that never threw told
    // I.K.E. apart with one line (review of 1.1.19, M5)
    d.get = accessor(name, function () { RAPPLY(orig, this, []); return RAPPLY(fn, this, [orig]); }, orig);
    try { Object.defineProperty(obj, name, d); } catch (e) {}
  }
  function setter(obj, name, after) {
    if (!obj) return;
    var d = Object.getOwnPropertyDescriptor(obj, name);
    if (!d || !d.set) return;
    var orig = d.set;
    var holder = { set [name](v) { try { RAPPLY(orig, this, [v]); } catch (e) { clean(e); throw e; } after(this, v); } };
    var s = Object.getOwnPropertyDescriptor(holder, name).set;
    natives.set(s, RAPPLY(origToString, orig, []));
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
      try { v = RAPPLY(realVendor, info, []); } catch (e) {}
      return gpuFor(v, GPUS, PICK);
    }
    getter(I, 'vendor', function () { return mine(this)[2]; });
    getter(I, 'architecture', function () { return mine(this)[3]; });
    getter(I, 'device', function () { return ''; });
    getter(I, 'description', function () { return ''; });
  }
  function isProtected(w) {
    try { return RAPPLY(w.Function.prototype.toString, SECRET, []) === SECRET; } catch (e) { return false; }
  }

  // ---- inline workers -----------------------------------------------------------
  // Runs inside the worker; must not use anything from outside its own body.
  function workerPatch(c, rng, farble, gpuFor, viewNoise, cssLocal, glReads, seed, address) {
    var toStr = Function.prototype.toString, RAW = Reflect.apply, GD = Object.getOwnPropertyDescriptor;
    var CJ = JSON.stringify(c), JS = JSON.stringify, here = '';
    c.seed = seed;
    // the address of this worker's own prelude: revoked before the worker's
    // code runs, so its text (the seed) cannot be read (audit, H-B)
    try {
      here = self.location.href;
      if (address !== null && here.slice(0, 5) === 'blob:') URL.revokeObjectURL(here);
    } catch (e) {}
    // taken before the worker's own code, as in the page (review of 1.1.19, N4)
    var nat = (function () {
      var m = new WeakMap(), get = WeakMap.prototype.get, put = WeakMap.prototype.set;
      return Object.freeze({
        get: function (k) { return RAW(get, m, [k]); },
        set: function (k, v) { RAW(put, m, [k, v]); return this; }
      });
    })();
    var THEN = Promise.prototype.then, DEFP = Object.defineProperty, SPEC = Symbol.species;
    // as in the page (verification of 1.1.20, V-1, V-2): the engine's promise
    // gets an own constructor before then(); elements are written without
    // asking the prototype chain
    var thenW = function (p, fn) {
      try { var sp = {}; DEFP(sp, SPEC, { value: Promise }); DEFP(p, 'constructor', { value: sp, configurable: true }); }
      catch (e) {}
      return RAW(THEN, p, [fn]);
    };
    var putW = function (a, i, v) {
      DEFP(a, i, { value: v, writable: true, enumerable: true, configurable: true });
      return v;
    };
    var ARR = Array;
    var SSL = String.prototype.slice, SIX = String.prototype.indexOf, SLO = String.prototype.toLowerCase;
    var lower = function (x) { return RAW(SLO, x, []); };
    var major = function (x) { var t = `${x}`, i = RAW(SIX, t, ['.']); return i < 0 ? t : RAW(SSL, t, [0, i]); };
    var getOf = function (proto, name) { var d = proto && GD(proto, name); return d && d.get; };
    var TAP = Object.getPrototypeOf(Uint8Array.prototype);
    var LENG = getOf(TAP, 'length'), TAGG = getOf(TAP, Symbol.toStringTag);
    var IMGD = getOf(self.ImageData && ImageData.prototype, 'data');
    var DVW = self.DataView && DataView.prototype;
    var TW = Object.freeze({ RA: RAW, tag: TAGG, buf: getOf(TAP, 'buffer'), off: getOf(TAP, 'byteOffset'),
      blen: getOf(TAP, 'byteLength'), dvBuf: getOf(DVW, 'buffer'), dvOff: getOf(DVW, 'byteOffset'),
      dvLen: getOf(DVW, 'byteLength'), abLen: getOf(ArrayBuffer.prototype, 'byteLength'),
      sabLen: getOf(self.SharedArrayBuffer && SharedArrayBuffer.prototype, 'byteLength'), U8: Uint8Array, U16: Uint16Array });
    var noiseImage = function (img) {
      var px = RAW(IMGD, img, []), tg = RAW(TAGG, px, []);
      if (tg === 'Uint8ClampedArray') farble(px, c.seed, rng, RAW(LENG, px, []));
      else if (tg === 'Float16Array') viewNoise(TW, px, 0, -1, c.seed, rng, farble, true);
    };
    var OCW = self.OffscreenCanvas, OCWP = OCW && OCW.prototype;
    var O2WP = self.OffscreenCanvasRenderingContext2D && OffscreenCanvasRenderingContext2D.prototype;
    var OCV = { w: getOf(OCWP, 'width'), h: getOf(OCWP, 'height'), ctx: OCWP && OCWP.getContext,
      draw: O2WP && O2WP.drawImage, put: O2WP && O2WP.putImageData };
    function method(name, impl, orig) {
      var f = ({ [name]() { return RAW(impl, this, arguments); } })[name];
      try { Object.defineProperty(f, 'length', { value: orig.length, configurable: true }); } catch (e) {}
      nat.set(f, RAW(toStr, orig, []));
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
      var g = Object.getOwnPropertyDescriptor({ get [name]() { RAW(orig, this, []); return RAW(fn, this, [orig]); } }, name).get;
      nat.set(g, RAW(toStr, orig, []));
      d.get = g;
      try { Object.defineProperty(obj, name, d); } catch (e) {}
    }
    wrap(Function.prototype, 'toString', function (orig) {
      return function () {
        var s = nat.get(this);
        return s !== undefined ? s : RAW(orig, this, []);
      };
    });
    // the worker's own fonts get the page's masks (fingerprinting audit, H-D)
    if (c.fonts && c.blank && self.fonts && self.FontFace) {
      try {
        var fset = self.fonts, FSW = Object.getPrototypeOf(fset), fAdd = FSW.add, fEach = FSW.forEach;
        var FFW = FontFace, raw = atob(c.blank), fb = new Uint8Array(raw.length);
        for (var q = 0; q < raw.length; q++) fb[q] = raw.charCodeAt(q);
        var masks = (function () {
          var m = new WeakSet(), has = WeakSet.prototype.has, add = WeakSet.prototype.add;
          return Object.freeze({ has: function (o) { return RAW(has, m, [o]); }, add: function (o) { RAW(add, m, [o]); } });
        })();
        var ownFaces = { __proto__: null };
        var fillW = function () {
          for (var i = 0; i < c.fonts.length; i++) {
            try {
              var f = ownFaces[i] || (ownFaces[i] = new FFW(c.fonts[i], fb, { unicodeRange: 'U+D800' }));   // no prototype: V-2
              masks.add(f);
              RAW(fAdd, fset, [f]);
            } catch (e) {}
          }
        };
        var seen = function (t) {
          var out = [];
          RAW(fEach, t, [function (f) { if (!masks.has(f)) putW(out, out.length, f); }]);
          return out;
        };
        getter(FSW, 'size', function () { return seen(this).length; });
        wrap(FSW, 'forEach', function () {
          return function (cb, thisArg) {
            var me2 = this, l = seen(this);
            for (var i = 0; i < l.length; i++) RAW(cb, thisArg, [l[i], l[i], me2]);
          };
        });
        ['values', 'keys'].forEach(function (n) {
          wrap(FSW, n, function () { return function () { return seen(this).values(); }; });
        });
        wrap(FSW, 'entries', function () {
          return function () { var l = seen(this), o = []; for (var i = 0; i < l.length; i++) o[i] = [l[i], l[i]]; return o.values(); };
        });
        var itw = GD(FSW, Symbol.iterator);
        if (itw && typeof itw.value === 'function') {
          itw.value = method('values', function () { return seen(this).values(); }, itw.value);
          Object.defineProperty(FSW, Symbol.iterator, itw);
        }
        wrap(FSW, 'has', function (orig) { return function (f) { return masks.has(f) ? false : RAW(orig, this, arguments); }; });
        wrap(FSW, 'delete', function (orig) { return function (f) { return masks.has(f) ? false : RAW(orig, this, arguments); }; });
        wrap(FSW, 'clear', function (orig) {
          return function () { var r = RAW(orig, this, arguments); if (this === fset) fillW(); return r; };
        });
        wrap(FSW, 'load', function (orig) {
          return function () {
            return thenW(RAW(orig, this, arguments), function (l) {
              if (!l) return l;
              var o = new ARR();
              for (var i = 0, n = l.length; i < n; i++) if (!masks.has(l[i])) putW(o, o.length, l[i]);
              return o;
            });
          };
        });
        // FontFace sources: every local() entry taken out (audit H-D, V-7)
        var FCPW = String.fromCodePoint, ABL = getOf(ArrayBuffer.prototype, 'byteLength');
        var scrub = function (x) {
          if (x !== null && typeof x === 'object') {
            try { RAW(ABL, x, []); return x; } catch (e) {}
            try { RAW(TAGG, x, []); return x; } catch (e) {}
            try { RAW(getOf(DataView.prototype, 'byteLength'), x, []); return x; } catch (e) {}
          }
          return cssLocal(`${x}`, FCPW);
        };
        var RCW = Reflect.construct;
        var PFW = new Proxy(FFW, {
          construct: function (t, args, nt) {
            var a = [];
            for (var i = 0; i < args.length; i++) putW(a, i, args[i]);
            if (args.length > 1) putW(a, 1, scrub(a[1]));
            return RCW(t, a, nt === PFW ? t : nt);
          }
        });
        nat.set(PFW, RAW(toStr, FFW, []));
        Object.defineProperty(FFW.prototype, 'constructor', { value: PFW, writable: true, configurable: true });
        Object.defineProperty(self, 'FontFace', { value: PFW, writable: true, configurable: true });
        fillW();
      } catch (e) {}
    }
    // the worker's location and its own errors: the page's address
    if (address !== null && typeof address === 'string' && self.WorkerLocation && self.URL) {
      try {
        var home = new URL(address), UP = URL.prototype, WL = WorkerLocation.prototype;
        ['href', 'protocol', 'host', 'hostname', 'port', 'pathname', 'search', 'hash', 'origin'].forEach(function (n) {
          var g = getOf(UP, n);
          if (g) getter(WL, n, function () { return RAW(g, home, []); });
        });
        var hrefOf = getOf(UP, 'href');
        wrap(WL, 'toString', function () { return function () { return RAW(hrefOf, home, []); }; });
        if (self.ErrorEvent) {
          var EP = ErrorEvent.prototype, fn = getOf(EP, 'filename');
          getter(EP, 'filename', function (orig) { var f = RAW(orig, this, []); return f === here ? address : f; });
          getter(EP, 'lineno', function (orig) {
            var n = RAW(orig, this, []);
            return fn && RAW(fn, this, []) === here && n > c.lines ? n - c.lines : n;
          });
        }
      } catch (e) {}
    }
    var N = self.WorkerNavigator && WorkerNavigator.prototype;
    getter(N, 'hardwareConcurrency', function () { return c.cores; });
    if (c.mem) getter(N, 'deviceMemory', function () { return c.mem; });
    if (c.langs) {
      var frozen = Object.freeze(c.langs.slice());
      getter(N, 'languages', function () { return frozen; });
      getter(N, 'language', function () { return frozen[0]; });
    }
    if (c.maximum && c.langs && self.Intl && self.Proxy) {
      // as in the page: no language asked for means the one shown (M5)
      var LOC = c.langs[0], RCON = Reflect.construct, SL = Array.prototype.slice;
      var GCL = Intl.getCanonicalLocales, SUP = {};
      // an empty list or unknown languages: the one shown too (review 4, N5)
      var fix = function (args, at, kind) {
        var a = RAW(SL, args, []), v = a[at];
        if (v === undefined) { putW(a, at, LOC); return a; }
        var list = RAW(GCL, Intl, [v]), sup = SUP[kind];
        putW(a, at, list);
        if (!list.length || (sup && !RAW(sup[0], sup[1], [list]).length)) putW(a, at, LOC);
        return a;
      };
      ['DateTimeFormat', 'NumberFormat', 'Collator', 'PluralRules', 'RelativeTimeFormat', 'ListFormat',
        'DisplayNames', 'Segmenter', 'DurationFormat'].forEach(function (n) {
        var C = Intl[n];
        if (typeof C !== 'function') return;
        if (typeof C.supportedLocalesOf === 'function') SUP[n] = [C.supportedLocalesOf, C];
        var P = new Proxy(C, {
          construct: function (t, args, nt) { return RCON(t, fix(args, 0, n), nt === P ? t : nt); },
          apply: function (t, me, args) { return RAW(t, me, fix(args, 0, n)); }
        });
        nat.set(P, RAW(toStr, C, []));
        try {
          Object.defineProperty(Intl, n, { value: P, writable: true, configurable: true, enumerable: false });
          Object.defineProperty(C.prototype, 'constructor', { value: P, writable: true, configurable: true });
        } catch (e) {}
      });
      [[Date.prototype, ['toLocaleString', 'toLocaleDateString', 'toLocaleTimeString'], 'DateTimeFormat'],
        [Number.prototype, ['toLocaleString'], 'NumberFormat'],
        [self.BigInt && BigInt.prototype, ['toLocaleString'], 'NumberFormat'],
        [String.prototype, ['localeCompare'], 'Collator'],
        [String.prototype, ['toLocaleUpperCase', 'toLocaleLowerCase'], '']].forEach(function (pair) {
        pair[1].forEach(function (name) {
          wrap(pair[0], name, function (orig) {
            var at = name === 'localeCompare' ? 1 : 0;
            return function () { return RAW(orig, this, fix(arguments, at, pair[2])); };
          });
        });
      });
    }
    var O2 = self.OffscreenCanvasRenderingContext2D && OffscreenCanvasRenderingContext2D.prototype;
    var rawGet = O2 && O2.getImageData;
    wrap(O2, 'getImageData', function (orig) {
      return function () {
        var img = RAW(orig, this, arguments);
        noiseImage(img);
        return img;
      };
    });
    if (self.OffscreenCanvas && rawGet) {
      wrap(OffscreenCanvas.prototype, 'convertToBlob', function (orig) {
        return function () {
          var src = this;
          try {
            var ow = RAW(OCV.w, src, []), oh = RAW(OCV.h, src, []);
            if (ow && oh) {
              var copy = new OCW(ow, oh);
              var ctx = RAW(OCV.ctx, copy, ['2d']);
              RAW(OCV.draw, ctx, [src, 0, 0]);
              var img = RAW(rawGet, ctx, [0, 0, ow, oh]);
              noiseImage(img);
              RAW(OCV.put, ctx, [img, 0, 0]);
              src = copy;
            }
          } catch (e) { src = this; }
          return RAW(orig, src, arguments);
        };
      });
    }
    var packedW = (function () {
      var m = new WeakSet(), has = WeakSet.prototype.has, add = WeakSet.prototype.add;
      return Object.freeze({ has: function (o) { return RAW(has, m, [o]); }, add: function (o) { RAW(add, m, [o]); } });
    })();
    [self.WebGLRenderingContext, self.WebGL2RenderingContext].forEach(function (GL) {
      if (!GL) return;
      var rawParamW = GL.prototype.getParameter;
      wrap(GL.prototype, 'getExtension', function (orig) {
        return function (name) {
          var nm = `${name}`;
          if (c.hidden[lower(nm)] === 1) { RAW(orig, this, [nm]); return null; }
          return RAW(orig, this, [nm]);
        };
      });
      wrap(GL.prototype, 'getSupportedExtensions', function (orig) {
        return function () {
          var list = RAW(orig, this, arguments);
          if (!list) return list;
          var o = new ARR();
          for (var i = 0, n = list.length; i < n; i++) if (c.hidden[lower(`${list[i]}`)] !== 1) putW(o, o.length, list[i]);
          return o;
        };
      });
      wrap(GL.prototype, 'getParameter', function (orig) {
        return function (p) {
          var r = RAW(orig, this, arguments);
          // UNMASKED_VENDOR_WEBGL / UNMASKED_RENDERER_WEBGL.
          if ((p === 37445 || p === 37446) && typeof r === 'string') {
            if (c.strict) return null;
            return gpuFor(p === 37445 ? r : RAW(orig, this, [37445]), c.gpus, c.pick)[p - 37445];
          }
          return r;
        };
      });
      // pixels read back, as in the page (fingerprinting audit H-E, V-5)
      glReads(GL.prototype, wrap, RAW, function (v) { return RAW(TAGG, v, []); }, function (d, f, n) {
        viewNoise(TW, d, f, n, c.seed, rng, farble, false);
      }, packedW, rawParamW);
    });
    if (self.VideoFrame) {
      wrap(VideoFrame.prototype, 'copyTo', function (orig) {
        return function (dest) {
          return thenW(RAW(orig, this, arguments), function (layout) {
            viewNoise(TW, dest, 0, -1, c.seed, rng, farble, false);
            return layout;
          });
        };
      });
    }
    if (c.strict && self.NavigatorUAData) {
      // the same reduced Chrome version as the page and the headers (1.1.18,
      // docs review: a worker read the full one)
      wrap(self.NavigatorUAData.prototype, 'getHighEntropyValues', function (orig) {
        return function () {
          var ua = this;
          return thenW(RAW(orig, this, arguments), function (v) {
            var m = (ua.brands && ua.brands[0] && ua.brands[0].version) || '0';
            if (v && 'uaFullVersion' in v) v.uaFullVersion = m + '.0.0.0';
            if (v && v.fullVersionList) {
              // no method of the worker's on the real versions (audit, H-A)
              var full = v.fullVersionList, list = [];
              for (var i = 0; i < full.length; i++) putW(list, i, { brand: full[i].brand, version: major(full[i].version) + '.0.0.0' });
              v.fullVersionList = list;
            }
            return v;
          });
        };
      });
    }
    if (c.strict) {
      // as Chrome on a card it does not support: WebGPU there, no adapter
      // (review of 1.1.19, M5: "gpu" in navigator with no value was Chrome's never)
      var GP = self.GPU && GPU.prototype, gb = getOf(GP, 'wgslLanguageFeatures');
      var PRM = Promise, PRES = Promise.resolve, PREJ = Promise.reject;
      wrap(GP, 'requestAdapter', function () {
        return function () {
          try { if (gb) RAW(gb, this, []); } catch (e) { return RAW(PREJ, PRM, [e]); }
          return RAW(PRES, PRM, [null]);
        };
      });
    } else if (self.GPUAdapterInfo) {
      var GI = self.GPUAdapterInfo.prototype;
      var gd = Object.getOwnPropertyDescriptor(GI, 'vendor'), realVendor = gd && gd.get;
      var mine = function (info) {
        var v = '';
        try { v = RAW(realVendor, info, []); } catch (e) {}
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
      var meHead = '(' + RAW(toStr, workerPatch, []) + ')(' + CJ + ',' + RAW(toStr, rng, []) + ',' +
        RAW(toStr, farble, []) + ',' + RAW(toStr, gpuFor, []) + ',' + RAW(toStr, viewNoise, []) + ',' +
        RAW(toStr, cssLocal, []) + ',' + RAW(toStr, glReads, []) + ',';
      var RBUF = new Uint32Array(1), RGV = crypto.getRandomValues, CR = crypto;
      var preludeOf = function (addr, own) {
        var sd = c.seed;
        if (own) { RAW(RGV, CR, [RBUF]); sd = RBUF[0] || 1; }
        var p = meHead + sd + ',' + RAW(JS, JSON, [addr]) + ');\n';
        while (p.length % 3) p += ' ';                 // so it can be joined to base64 data
        return p;
      };
      var Ur = self.URL, mk = Ur && Ur.createObjectURL, rv = Ur && Ur.revokeObjectURL;
      var made = (function () {
        var m = new Map(), get = Map.prototype.get, put = Map.prototype.set;
        return Object.freeze({ get: function (k) { return RAW(get, m, [k]); },
          set: function (k, v) { RAW(put, m, [k, v]); } });
      })();
      var BSZ = getOf(self.Blob && Blob.prototype, 'size'), BTY = getOf(self.Blob && Blob.prototype, 'type');
      // taken before the worker's own code: the prelude goes to no function
      // the worker could have replaced since (1.1.18, security audit)
      var NB = self.Blob, RA = Reflect.apply, RC = Reflect.construct, LT = self.setTimeout;
      var XR = self.XMLHttpRequest, XRP = XR && XR.prototype, XO = XRP && XRP.open, XS = XRP && XRP.send;
      var XST = getOf(XRP, 'status'), XTX = getOf(XRP, 'responseText');
      var b2a = self.btoa, enc = self.encodeURIComponent;
      if (mk && NB) {
        wrap(Ur, 'createObjectURL', function (orig) {
          return function (o) {
            var u = RAW(orig, this, arguments);
            try { RAW(BSZ, o, []); made.set(u, o); } catch (e) {}     // a Blob (its own getter tells)
            return u;
          };
        });
      }
      ['Worker', 'SharedWorker'].forEach(function (name) {
        var Orig = self[name];
        if (typeof Orig !== 'function' || !mk) return;
        var P = new Proxy(Orig, {
          construct: function (t, args, nt0) {
            var nt = nt0 === P ? t : nt0;
            if (!args.length) return RC(t, args, nt);             // the engine's own TypeError
            var u = `${args[0]}`, given = args.length > 1, o = args[1], ov = o, module = false;
            if (given && o !== null && (typeof o === 'object' || typeof o === 'function')) {
              // read once, handed on as a new object (as in the page, V-3)
              ov = {};
              var ks = ['credentials', 'extendedLifetime', 'name', 'sameSiteCookies', 'type'];
              for (var q = 0; q < 5; q++) {
                var v = o[ks[q]];
                if (v === undefined) continue;
                v = ks[q] === 'extendedLifetime' ? !!v : `${v}`;
                if (ks[q] === 'type') module = v === 'module';
                DEFP(ov, ks[q], { value: v, writable: true, enumerable: true, configurable: true });
              }
            }
            var send = function (x) { return given ? [x, ov] : [x]; };
            args = send(u);
            try {
              var b = made.get(u);
              if (!b && lower(RAW(SSL, u, [0, 5])) === 'blob:' && XR) {
                // an address made elsewhere (by the page, say): its text read
                // here, once (verification V-4: such a worker had nothing)
                try {
                  var xr = new XR();
                  RAW(XO, xr, ['GET', u, false]);
                  RAW(XS, xr, []);
                  var xst = RAW(XST, xr, []);
                  if (xst === 200 || xst === 0) b = new NB([RAW(XTX, xr, [])], { type: 'text/javascript' });
                } catch (e) {}
              }
              if (b) {
                var pu = RA(mk, Ur, [new NB([preludeOf(u, module), b], { type: RAW(BTY, b, []) || 'text/javascript' })]);
                args = send(pu);
                RA(LT, self, [function () { RA(rv, Ur, [pu]); }, 30000]);
              } else if (lower(RAW(SSL, u, [0, 5])) === 'data:' && RAW(SIX, u, [',']) > 0) {
                var k = RAW(SIX, u, [',']), b64 = lower(RAW(SSL, u, [k - 7 < 0 ? 0 : k - 7, k])) === ';base64';
                var mine = preludeOf(u, true);
                args = send(RAW(SSL, u, [0, k + 1]) + (b64 ? RA(b2a, self, [mine]) : RA(enc, self, [mine])) +
                  RAW(SSL, u, [k + 1]));
              }
            } catch (e) {}
            return RC(t, args, nt);
          }
        });
        nat.set(P, RAW(toStr, Orig, []));
        try { Object.defineProperty(self, name, { value: P, writable: true, configurable: true }); } catch (e) {}
      });
    } catch (e) {}
  }
  // The prelude of an inline worker. A worker could read its own address
  // (self.location.href, or the page through ErrorEvent.filename) and with
  // it the prelude, the site's seed included, and remove the noise exactly
  // (fingerprinting audit, H-B). Now a blob worker's prelude revokes its own
  // address before the worker's code runs, the worker's location and its
  // errors name the page's own address, and a data: worker, whose address
  // is its text, gets a seed of its own instead of the site's.
  var WP_HEAD = '(' + RAPPLY(origToString, workerPatch, []) + ')(';
  var WP_TAIL = ',' + RAPPLY(origToString, rng, []) + ',' + RAPPLY(origToString, farble, []) + ',' +
    RAPPLY(origToString, gpuFor, []) + ',' + RAPPLY(origToString, viewNoise, []) + ',' +
    RAPPLY(origToString, cssLocal, []) + ',' + RAPPLY(origToString, glReads, []) + ',';
  var JSON_STR = JSON.stringify;
  var PRELUDE_LINES = 1;
  (function () {
    var all = WP_HEAD + WP_TAIL;
    for (var i = 0; i < all.length; i++) if (all[i] === '\n') PRELUDE_LINES++;
  })();
  var WCFG = '';                  // after the font list, below
  var RND = new Uint32Array(1), RND_GET = crypto.getRandomValues, CRYPTO = crypto;
  function preludeFor(address, ownSeed) {
    var sd = seed;
    if (ownSeed) { RAPPLY(RND_GET, CRYPTO, [RND]); sd = RND[0] || 1; }
    var p = WP_HEAD + WCFG + WP_TAIL + sd + ',' + RAPPLY(JSON_STR, JSON, [address]) + ');\n';
    while (p.length % 3) p += ' ';               // so it can be joined to base64 data
    return p;
  }
  // patched address -> the page's own, for the errors the page is shown
  var PATCHED = hardStrongMap();
  // A worker's options, read once, in the engine's order, and handed on as
  // a new object: a getter could answer "classic" here and "module" to the
  // engine. A module worker's imports run before the prelude and could read
  // it: such a worker gets a seed of its own (verification V-3).
  var OPT_KEYS = ['credentials', 'extendedLifetime', 'name', 'sameSiteCookies', 'type'];
  function workerOptions(o, given) {
    if (!given) return { given: false, value: undefined, module: false };
    if (o === null || (typeof o !== 'object' && typeof o !== 'function')) return { given: true, value: o, module: false };
    var lit = {}, module = false;
    for (var i = 0; i < OPT_KEYS.length; i++) {
      var k = OPT_KEYS[i], v = o[k];
      if (v === undefined) continue;
      v = k === 'extendedLifetime' ? !!v : `${v}`;
      if (k === 'type') module = v === 'module';
      DEFPROP(lit, k, { value: v, writable: true, enumerable: true, configurable: true });
    }
    return { given: true, value: lit, module: module };
  }

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
  // the workers' configuration, made before any page script (its arrays
  // could otherwise be turned into something else by the page's toJSON);
  // at Strict and above it carries the masks for the workers' own fonts
  WCFG = JSON_STR({ cores: cores, mem: strict ? 8 : 0, langs: langs, strict: strict, maximum: maximum,
    gpus: GPUS, pick: PICK, hidden: hiddenExt, lines: PRELUDE_LINES,
    fonts: strict ? MASKED : null, blank: strict ? BLANK_FONT : null });
  // A FontFace source written by the page at Strict and above: every local()
  // entry taken out, so no installed font can be asked for by name, however
  // it is spelt (fingerprinting audit H-D; verification V-7: tabs, CSS
  // escapes, comments, objects); a picture of the font (url) still loads.
  var FCP = String.fromCodePoint;
  function fontSource(x) {
    if (x !== null && typeof x === 'object') {
      try { RAPPLY(TV.abLen, x, []); return x; } catch (e) {}
      if (TAG(x) !== undefined) return x;
      try { RAPPLY(TV.dvLen, x, []); return x; } catch (e) {}
    }
    return cssLocal(`${x}`, FCP);
  }
  var FILLS = hardMap();          // each masked font set -> how to put its masks back
  var maskedFaces = hardSet(), maskedDocs = hardSet();
  function maskFonts(w) {
    var WPr = w.Promise;            // this realm's, for then()
    var doc = w.document;
    if (!doc || !doc.fonts || !w.FontFace || maskedDocs.has(doc)) return;
    maskedDocs.add(doc);
    // own: a table with no prototype (a setter on Array.prototype's index
    // names was handed every mask, the installed fonts by name; V-2)
    var set = doc.fonts, own = { __proto__: null }, blank = null, FF = w.FontFace, WArrF = w.Array;
    try {
      var bin = w.atob(BLANK_FONT);
      blank = new w.Uint8Array(bin.length);
      for (var k = 0; k < bin.length; k++) blank[k] = bin.charCodeAt(k);
    } catch (e) { return; }
    function fill() {
      for (var i = 0; i < MASKED.length; i++) {
        try {
          // a range no text can reach (a lone surrogate is drawn as U+FFFD):
          // with U+E000 the masks themselves told which fonts were installed
          // (fingerprinting audit, H-D)
          var face = own[i] || (own[i] = new FF(MASKED[i], blank, { unicodeRange: 'U+D800' }));
          maskedFaces.add(face);
          RAPPLY(FSP_add, set, [face]);
        } catch (e) {}
      }
    }
    // the interface has no global name in this engine: take it from the object
    var FSP = Object.getPrototypeOf(set);
    if (!FSP) return;
    var FSP_add = FSP.add, FSP_forEach = FSP.forEach;
    function visible(target) {
      var out = [];
      RAPPLY(FSP_forEach, target, [function (f) { if (!maskedFaces.has(f)) put(out, out.length, f); }]);
      return out;
    }
    // the page sees only its own font faces
    getter(FSP, 'size', function () { return visible(this).length; });
    wrap(FSP, 'forEach', function () {
      return function (cb, thisArg) {
        var self = this;
        visible(this).forEach(function (f) { RAPPLY(cb, thisArg, [f, f, self]); });
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
      return function (f) { return maskedFaces.has(f) ? false : RAPPLY(orig, this, arguments); };
    });
    wrap(FSP, 'delete', function (orig) {
      return function (f) { return maskedFaces.has(f) ? false : RAPPLY(orig, this, arguments); };
    });
    FILLS.set(set, fill);
    // clear() of any realm on any masked set puts that set's masks back: the
    // frame's own clear() did not refill the page's set (audit, H-D)
    wrap(FSP, 'clear', function (orig) {
      return function () {
        var r = RAPPLY(orig, this, arguments), again = FILLS.get(this);
        if (again) again();
        return r;
      };
    });
    wrap(FSP, 'load', function (orig) {
      return function () {
        return then(RAPPLY(orig, this, arguments), function (list) {
          if (!list) return list;
          // a loop, not filter(): filter() asked the list for its constructor (V-1)
          var out = new WArrF();
          for (var i = 0, n = list.length; i < n; i++) if (!maskedFaces.has(list[i])) put(out, out.length, list[i]);
          return out;
        }, WPr);
      };
    });
    if (typeof FF === 'function' && w.Proxy) {
      var PF = new w.Proxy(FF, {
        construct: function (t, args, nt) {
          var a = [];
          for (var i = 0; i < args.length; i++) put(a, i, args[i]);
          if (args.length > 1) put(a, 1, fontSource(a[1]));
          try { return nConstructFF(t, a, nt === PF ? t : nt); } catch (e) { clean(e); throw e; }
        }
      });
      var nConstructFF = Reflect.construct;
      natives.set(PF, RAPPLY(origToString, FF, []));
      try {
        Object.defineProperty(FF.prototype, 'constructor', { value: PF, writable: true, configurable: true });
        Object.defineProperty(w, 'FontFace', { value: PF, writable: true, configurable: true });
      } catch (e) {}
    }
    fill();
  }

  // ---- one realm ---------------------------------------------------------------
  function install(w) {
    var WPr = w.Promise;            // this realm's, for then()
    if (!w || isProtected(w)) return;
    var doc = w.document;

    // Function.prototype.toString: natives stay "[native code]" in every realm
    wrap(w.Function.prototype, 'toString', function (orig) {
      return function () {
        if (this === SECRET) return SECRET;
        var s = natives.get(this);
        return s !== undefined ? s : RAPPLY(orig, this, []);
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
        var cw = RAPPLY(CV.w, canvas, []), ch = RAPPLY(CV.h, canvas, []);
        if (!cw || !ch) return canvas;
        var c = RAPPLY(CV.make, doc, ['canvas']);
        RAPPLY(CV.sw, c, [cw]); RAPPLY(CV.sh, c, [ch]);
        var ctx = RAPPLY(CV.ctx, c, ['2d']);
        RAPPLY(CV.draw, ctx, [canvas, 0, 0]);
        var img = RAPPLY(rawGetImageData, ctx, [0, 0, cw, ch]);
        noiseImage(img);
        RAPPLY(CV.put, ctx, [img, 0, 0]);
        return c;
      } catch (e) { return canvas; }
    }
    if (w.HTMLCanvasElement && rawGetImageData) {
      wrap(w.HTMLCanvasElement.prototype, 'toDataURL', function (orig) {
        return function () { return RAPPLY(orig, noisyCopy(this), arguments); };
      });
      wrap(w.HTMLCanvasElement.prototype, 'toBlob', function (orig) {
        return function () { return RAPPLY(orig, noisyCopy(this), arguments); };
      });
    }
    wrap(C2D, 'getImageData', function (orig) {
      return function () {
        var img = RAPPLY(orig, this, arguments);
        noiseImage(img);
        return img;
      };
    });
    var O2D = w.OffscreenCanvasRenderingContext2D && w.OffscreenCanvasRenderingContext2D.prototype;
    var rawOffGet = O2D && O2D.getImageData;
    wrap(O2D, 'getImageData', function (orig) {
      return function () {
        var img = RAPPLY(orig, this, arguments);
        noiseImage(img);
        return img;
      };
    });
    if (w.OffscreenCanvas && rawOffGet) {
      wrap(w.OffscreenCanvas.prototype, 'convertToBlob', function (orig) {
        return function () {
          var src = this;
          try {
            var ow = RAPPLY(CV.ow, src, []), oh = RAPPLY(CV.oh, src, []);
            if (ow && oh) {
              var copy = new OC(ow, oh);
              var ctx = RAPPLY(CV.octx, copy, ['2d']);
              RAPPLY(CV.odraw, ctx, [src, 0, 0]);
              var img = RAPPLY(rawOffGet, ctx, [0, 0, ow, oh]);
              noiseImage(img);
              RAPPLY(CV.oput, ctx, [img, 0, 0]);
              src = copy;
            }
          } catch (e) { src = this; }
          return RAPPLY(orig, src, arguments);
        };
      });
    }
    if (strict && w.TextMetrics) {
      // a tiny change of each text's width, its own for every text and font
      // and site, and none for an empty text: the same offset for every text
      // was read with measureText('') (review of 1.1.19, H1)
      var measured = hardMap();
      [w.CanvasRenderingContext2D, w.OffscreenCanvasRenderingContext2D].forEach(function (C) {
        if (!C) return;
        wrap(C.prototype, 'measureText', function (orig) {
          return function (text) {
            var m = RAPPLY(orig, this, arguments);
            // the parts only; the key is made when the width is read (L5 of the
            // performance review: joining here cost each call)
            try { measured.set(m, [text, this.font]); } catch (e) {}
            return m;
          };
        });
      });
      getter(w.TextMetrics.prototype, 'width', function (orig) {
        var real = RAPPLY(orig, this, []);
        var key = measured.get(this);
        if (!real || key === undefined) return real;
        return real * (1 + (((hash(seed + '|' + String(key[0]) + '|' + key[1]) >>> 8) % 61) - 30) / 10000000);
      });
    }

    // ---- WebGL: hide the raw GPU identity in strict profiles; retain pixel farbling ----
    var packed = hardSet();
    [w.WebGLRenderingContext, w.WebGL2RenderingContext].forEach(function (GL) {
      if (!GL) return;
      var rawGetParam = GL.prototype.getParameter;
      var WArrG = w.Array;
      wrap(GL.prototype, 'getExtension', function (orig) {
        return function (name) {
          // the name read once, and that text is what the engine gets
          var nm = `${name}`;
          if (hiddenExt[lower(nm)] === 1) { RAPPLY(orig, this, [nm]); return null; }
          return RAPPLY(orig, this, [nm]);
        };
      });
      wrap(GL.prototype, 'getSupportedExtensions', function (orig) {
        return function () {
          var list = RAPPLY(orig, this, arguments);
          if (!list) return list;
          // a loop, not filter(): filter() asked the list for its constructor (V-1)
          var out = new WArrG();
          for (var i = 0, n = list.length; i < n; i++) {
            if (hiddenExt[lower(`${list[i]}`)] !== 1) put(out, out.length, list[i]);
          }
          return out;
        };
      });
      wrap(GL.prototype, 'getParameter', function (orig) {
        return function (p) {
          var r = RAPPLY(orig, this, arguments);
          // UNMASKED_VENDOR_WEBGL / UNMASKED_RENDERER_WEBGL: the site's model,
          // or nothing where the extension is hidden (as without it)
          if ((p === 37445 || p === 37446) && typeof r === 'string') {
            if (strict) return null;
            return gpuFor(p === 37445 ? r : RAPPLY(orig, this, [37445]), GPUS, PICK)[p - 37445];
          }
          return r;
        };
      });
      glReads(GL.prototype, wrap, RAPPLY, TAG, function (d, f, n) {
        viewNoise(TV, d, f, n, seed, rng, farble, false);
      }, packed, rawGetParam);
    });
    // a VideoFrame made from a canvas (or a picture) copied out as bytes
    if (w.VideoFrame) {
      wrap(w.VideoFrame.prototype, 'copyTo', function (orig) {
        return function (dest) {
          return then(RAPPLY(orig, this, arguments), function (layout) {
            viewNoise(TV, dest, 0, -1, seed, rng, farble, false);
            return layout;
          }, WPr);
        };
      });
    }
    if (strict) {
      // as Chrome on a card it does not support: WebGPU there, no adapter (M5)
      // on a wrong object Chrome's rejects, as every promise of the engine's
      // does (review 4, N12): the engine's own getter tells
      var GPUP = w.GPU && w.GPU.prototype, gpuBrand = getterOf(GPUP, 'wgslLanguageFeatures');
      var PRM = w.Promise, PRES = PRM && PRM.resolve, PREJ = PRM && PRM.reject;
      wrap(GPUP, 'requestAdapter', function () {
        return function () {
          try { if (gpuBrand) RAPPLY(gpuBrand, this, []); } catch (e) { return RAPPLY(PREJ, PRM, [e]); }
          return RAPPLY(PRES, PRM, [null]);
        };
      });
    } else gpuInfo(w);

    // ---- audio ----
    var seenBuffers = hardSet();
    // Only what the engine rendered is changed, every sample by its own tiny
    // factor (review of 1.1.19, H1): every 97th sample by one factor could be
    // read back from a buffer the page wrote itself, or skipped.
    // The factor of a sample comes from the site's key, the sample's own
    // value and the one before it (review 4, N3): by its place alone, one
    // buffer of known samples rendered through the engine gave every factor,
    // and dividing by them gave the real sound.
    // the sample's own bits (its float32 form, the lowest 9 bits left out):
    // keyed on its size, every sample under 2^-20 had one factor, and a
    // quiet signal was divided back exactly (verification V-8)
    function audioNoise(v, before) {
      var q = bitsOf(v), p = bitsOf(before);
      var x = mul32((q ^ seed) >>> 0, 0x9E3779B1);
      x ^= x >>> 15; x = mul32((x ^ p) >>> 0, 0x85EBCA77); x ^= x >>> 13;
      return 1 + (((x >>> 0) % 2001) - 1000) / 10000000;
    }
    var rendered = hardSet();
    [w.OfflineAudioContext, w.BaseAudioContext].forEach(function (C) {
      if (!C) return;
      wrap(C.prototype, 'startRendering', function (orig) {
        return function () {
          var p = RAPPLY(orig, this, arguments);
          try {
            return then(p, function (buf) { try { rendered.add(buf); } catch (e) {} return buf; }, WPr);
          } catch (e) { return p; }
        };
      });
    });
    if (w.OfflineAudioCompletionEvent) {
      getter(w.OfflineAudioCompletionEvent.prototype, 'renderedBuffer', function (orig) {
        var buf = RAPPLY(orig, this, []);
        try { if (buf) rendered.add(buf); } catch (e) {}
        return buf;
      });
    }
    if (w.AudioProcessingEvent) {
      // what a ScriptProcessorNode hands the page was rendered by the engine
      // too (review of 1.1.19, N4: the real samples came through it)
      getter(w.AudioProcessingEvent.prototype, 'inputBuffer', function (orig) {
        var buf = RAPPLY(orig, this, []);
        try { if (buf) rendered.add(buf); } catch (e) {}
        return buf;
      });
    }
    if (w.AudioBuffer) {
      wrap(w.AudioBuffer.prototype, 'getChannelData', function (orig) {
        return function () {
          var d = RAPPLY(orig, this, arguments);
          if (rendered.has(this) && !seenBuffers.has(d)) {
            seenBuffers.add(d);
            for (var i = 0, n = LEN(d), was = 0; i < n; i++) { var v = d[i]; d[i] = v * audioNoise(v, was); was = v; }
          }
          return d;
        };
      });
      var newGetData = w.AudioBuffer.prototype.getChannelData;
      wrap(w.AudioBuffer.prototype, 'copyFromChannel', function (orig) {
        return function (dest, channel, start) {
          // the numbers read once, and the noisy samples taken before the
          // real ones are copied: a channel that changed between two reads,
          // or a wrong one, left the real samples in dest (review of 1.1.19, N4)
          var ch = channel >>> 0, from = start >>> 0;
          var d = rendered.has(this) ? RAPPLY(newGetData, this, [ch]) : null;
          var r = RAPPLY(orig, this, arguments.length > 2 ? [dest, ch, from] : [dest, ch]);
          if (d) {
            // the same values getChannelData gives (noised once)
            for (var i = 0, n = LEN(dest), m = LEN(d); i < n && from + i < m; i++) dest[i] = d[from + i];
          }
          return r;
        };
      });
    }
    if (w.AnalyserNode) {
      ['getFloatFrequencyData', 'getFloatTimeDomainData'].forEach(function (name) {
        wrap(w.AnalyserNode.prototype, name, function (orig) {
          return function (arr) {
            var r = RAPPLY(orig, this, arguments);
            for (var i = 0, n = LEN(arr), was = 0; i < n; i++) { var v = arr[i]; arr[i] = v * audioNoise(v, was); was = v; }
            return r;
          };
        });
      });
      // the byte versions too: the lowest bit of some values set to the
      // noise (fingerprinting audit, M-1)
      ['getByteFrequencyData', 'getByteTimeDomainData'].forEach(function (name) {
        wrap(w.AnalyserNode.prototype, name, function (orig) {
          return function (arr) {
            var r = RAPPLY(orig, this, arguments);
            for (var i = 0, n = LEN(arr); i < n; i++) {
              var x = mul32((i ^ seed ^ 0x5bd1e995) >>> 0, 0x9E3779B1) >>> 0;
              x ^= x >>> 15;
              if ((x & 7) === 0) arr[i] = (arr[i] & 254) | ((x >>> 4) & 1);
            }
            return r;
          };
        });
      });
    }

    // ---- hardware / device values ----
    var NP = w.Navigator.prototype;
    // Plugins: the real list plus two entries whose names differ on every site.
    if (w.Proxy && w.Reflect) {
      var pluginViews = hardMap(), PAP0 = w.PluginArray && w.PluginArray.prototype;
      // the engine's own, taken before they are wrapped below
      var PA = { len: getterOf(PAP0, 'length'), named: PAP0 && PAP0.namedItem };
      pluginPrototypes(w);
      getter(NP, 'plugins', function (orig) {
        var real = RAPPLY(orig, this, []);
        try {
          var view = pluginViews.get(real);
          if (!view) { view = pluginList(w, real, PA); pluginViews.set(real, view); }
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
    if (maximum && w.Intl && w.Proxy) {
      // Maximum shows en-US: dates, numbers and sorting with no language
      // asked for follow it too; they gave the real language away and
      // contradicted navigator.language (review of 1.1.19, M5)
      var LOC = frozenLangs ? frozenLangs[0] : 'en-US', RCON = Reflect.construct;
      var SLICE = Array.prototype.slice, GCL = w.Intl.getCanonicalLocales, SUPPORTED = {};
      // An empty list, or languages the engine does not have, fell back to
      // the system's own language too (review 4, N5). The list is read once,
      // as the engine itself would, and handed on already read.
      // The engine's own objects of each kind, taken before any page script.
      // When the engine itself already answers as LOC (the global level
      // Maximum starts it in en-US), a call that asks for no language is
      // handed on as it is: the same answer, and the engine keeps its quick
      // way (localeCompare was about 30 times slower through the rewrite).
      // Decided once per kind, on the first call, from the engine's own
      // resolved options of both (every field the same, and the language
      // exactly LOC); any difference keeps the rewrite (1.1.23).
      var ORIGC = { __proto__: null }, SAME = { __proto__: null };
      var sameDefault = function (kind) {
        var same = SAME[kind];
        if (same !== undefined) return same;
        same = false;
        var c = ORIGC[kind === '' ? 'DateTimeFormat' : kind];
        if (c) {
          try {
            var d = RAPPLY(c[1], R_CONSTRUCT(c[0], [], c[0]), []);
            var x = RAPPLY(c[1], R_CONSTRUCT(c[0], [LOC], c[0]), []);
            var kd = R_OWNKEYS(d), kx = R_OWNKEYS(x);
            same = d.locale === LOC && kd.length === kx.length;
            for (var i = 0; same && i < kd.length; i++) same = kd[i] === kx[i] && d[kd[i]] === x[kx[i]];
          } catch (e) { same = false; }
        }
        SAME[kind] = same;
        return same;
      };
      var fixLocales = function (args, at, kind) {
        if ((at < args.length ? args[at] : undefined) === undefined && sameDefault(kind)) return args;
        var a = RAPPLY(SLICE, args, []), v = a[at];
        if (v === undefined) { put(a, at, LOC); return a; }
        var list = RAPPLY(GCL, w.Intl, [v]), sup = SUPPORTED[kind];
        put(a, at, list);
        if (!list.length || (sup && !RAPPLY(sup[0], sup[1], [list]).length)) put(a, at, LOC);
        return a;
      };
      ['DateTimeFormat', 'NumberFormat', 'Collator', 'PluralRules', 'RelativeTimeFormat', 'ListFormat',
        'DisplayNames', 'Segmenter', 'DurationFormat'].forEach(function (n) {
        var C = w.Intl[n];
        if (typeof C !== 'function') return;
        if (typeof C.supportedLocalesOf === 'function') SUPPORTED[n] = [C.supportedLocalesOf, C];
        if (C.prototype && typeof C.prototype.resolvedOptions === 'function') ORIGC[n] = [C, C.prototype.resolvedOptions];
        var fix = function (args) { return fixLocales(args, 0, n); };
        var P = new w.Proxy(C, {
          construct: function (t, args, nt) {
            try { return RCON(t, fix(args), nt === P ? t : nt); } catch (e) { clean(e); throw e; }
          },
          apply: function (t, self, args) {
            try { return RAPPLY(t, self, fix(args)); } catch (e) { clean(e); throw e; }
          }
        });
        natives.set(P, RAPPLY(origToString, C, []));
        try {
          Object.defineProperty(w.Intl, n, { value: P, writable: true, configurable: true, enumerable: false });
          Object.defineProperty(C.prototype, 'constructor', { value: P, writable: true, configurable: true,
            enumerable: false });
        } catch (e) {}
      });
      [[w.Date.prototype, ['toLocaleString', 'toLocaleDateString', 'toLocaleTimeString'], 'DateTimeFormat'],
        [w.Number.prototype, ['toLocaleString'], 'NumberFormat'],
        [w.BigInt && w.BigInt.prototype, ['toLocaleString'], 'NumberFormat'],
        [w.String.prototype, ['localeCompare'], 'Collator'],
        [w.String.prototype, ['toLocaleUpperCase', 'toLocaleLowerCase'], '']].forEach(function (pair) {
        pair[1].forEach(function (name) {
          wrap(pair[0], name, function (orig) {
            var at = name === 'localeCompare' ? 1 : 0;
            return function () { return RAPPLY(orig, this, fixLocales(arguments, at, pair[2])); };
          });
        });
      });
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
      // the voices' own getters, and no method of the page's: a page that
      // replaced one was shown every hidden voice (fingerprinting audit, H-A)
      var SVP = w.SpeechSynthesisVoice && w.SpeechSynthesisVoice.prototype;
      var vLang = getterOf(SVP, 'lang'), vDefault = getterOf(SVP, 'default');
      var langOf = function (v) {
        var s = lower(`${(vLang ? RAPPLY(vLang, v, []) : v.lang) || ''}`), i = 0;
        while (i < s.length && s[i] !== '-' && s[i] !== '_') i++;
        return sslice(s, 0, i);
      };
      var wanted = function (p) {
        for (var k = 0; k < voiceLangs.length; k++) if (voiceLangs[k] === p) return true;
        return false;
      };
      wrap(w.SpeechSynthesis.prototype, 'getVoices', function (orig) {
        return function () {
          var all = RAPPLY(orig, this, arguments), out = [];
          if (!all || !all.length) return all;
          for (var i = 0; i < all.length; i++) {
            var v = all[i];
            if (strict) {
              if (vDefault ? RAPPLY(vDefault, v, []) : v['default']) { put(out, out.length, v); break; }
              continue;
            }
            if (wanted(langOf(v))) put(out, out.length, v);
          }
          if (strict && !out.length) put(out, 0, all[0]);
          return out;
        };
      });
    }
    if (strict) {
      maskFonts(w);
      // the battery as a computer on mains power reports it (review of 1.1.19,
      // M5: no getBattery at all is no Chrome's)
      var BM = w.BatteryManager && w.BatteryManager.prototype;
      getter(BM, 'charging', function () { return true; });
      getter(BM, 'level', function () { return 1; });
      getter(BM, 'chargingTime', function () { return 0; });
      getter(BM, 'dischargingTime', function () { return Infinity; });
      // A usual monitor size instead of the real one (or, worse, the window's).
      var scr = w.Screen && w.Screen.prototype, size = null;
      var dW = scr && Object.getOwnPropertyDescriptor(scr, 'width');
      var dH = scr && Object.getOwnPropertyDescriptor(scr, 'height');
      var sized = function (self) {
        if (!size) size = usualScreen(RAPPLY(dW.get, self, []), RAPPLY(dH.get, self, []));
        return size;
      };
      if (dW && dH && dW.get && dH.get) {
        getter(scr, 'width', function () { return sized(this)[0]; });
        getter(scr, 'height', function () { return sized(this)[1]; });
        getter(scr, 'availWidth', function () { return sized(this)[0]; });
        getter(scr, 'availHeight', function () { return sized(this)[1]; });
      }
      var SCREEN0 = w.screen, MQL = w.MediaQueryList && w.MediaQueryList.prototype;
      var MQLE = w.MediaQueryListEvent && w.MediaQueryListEvent.prototype;
      var MQL_MEDIA = getterOf(MQL, 'media'), EV_TARGET = getterOf(w.Event && w.Event.prototype, 'target');
      var mediaOf = hardMap();          // the query answered -> the page's own text, as the engine writes it
      if (dW && dH && dW.get && dH.get && MQL_MEDIA && SCREEN0) {
        wrap(w, 'matchMedia', function (orig) {
          return function (query) {
            if (!arguments.length) return RAPPLY(orig, this, arguments);
            var text = `${query}`;                 // read once
            if (sindex(lower(text), 'device-') < 0) return RAPPLY(orig, this, [text]);
            var real = RAPPLY(orig, this, [text]);
            var sz = sized(SCREEN0), list = RAPPLY(orig, this, [mqRewrite(text, sz[0], sz[1])]);
            mediaOf.set(list, RAPPLY(MQL_MEDIA, real, []));
            return list;
          };
        });
        getter(MQL, 'media', function (orig) {
          var t = mediaOf.get(this);
          return t !== undefined ? t : RAPPLY(orig, this, []);
        });
        if (EV_TARGET) {
          getter(MQLE, 'media', function (orig) {
            var list = RAPPLY(EV_TARGET, this, []), t = list ? mediaOf.get(list) : undefined;
            return t !== undefined ? t : RAPPLY(orig, this, []);
          });
        }
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
            return then(RAPPLY(orig, this, arguments), function (v) {
              var major = (self.brands && self.brands[0] && self.brands[0].version) || '0';
              var list = [], brands = v.brands || [];
              for (var i = 0; i < brands.length; i++) {
                put(list, i, { brand: brands[i].brand, version: brands[i].version + '.0.0.0' });
              }
              var generic = { architecture: 'x86', bitness: '64', model: '', mobile: false,
                platform: CFG.platform || 'Linux', platformVersion: CFG.platformVersion || '6.0.0',
                uaFullVersion: major + '.0.0.0', wow64: false, formFactors: ['Desktop'],
                fullVersionList: list };
              // the engine's own answer with its values replaced: its keys stay
              // in the engine's order (fingerprinting audit, L-1)
              for (var k in generic) if (own(generic, k) && own(v, k)) v[k] = generic[k];
              return v;
            }, WPr);
          };
        });
      }
    }

    // ---- inline workers get the same values ----
    var U = w.URL, blobs = hardStrongMap();
    var rawCreate = U && U.createObjectURL, rawRevoke = U && U.revokeObjectURL;
    // taken before the page's scripts: the prelude (with this site's seed)
    // is never handed to a function the page could have replaced since
    // (1.1.18, security audit: a page that wrapped Blob read it)
    var NBlob = w.Blob, NXHR = w.XMLHttpRequest, nBtoa = w.btoa, nEnc = w.encodeURIComponent;
    var nLater = w.setTimeout, nConstruct = w.Reflect.construct;
    var XP = NXHR && NXHR.prototype, xOpen = XP && XP.open, xSend = XP && XP.send;
    // Trusted Types (verification V-13): a TrustedScriptURL is read through
    // its own method and passed on as it is when nothing is added; an
    // address with the prelude gets a policy of the protection's own
    var TTP = w.trustedTypes, TT_MAKE = TTP && TTP.createPolicy;
    var TT_URL = w.TrustedTypePolicy && w.TrustedTypePolicy.prototype.createScriptURL;
    var TSU_STR = w.TrustedScriptURL && w.TrustedScriptURL.prototype.toString, ttPolicy = null, TT_NAME = 'p' + seed;
    var trustedText = function (v) {
      if (!TSU_STR || v === null || typeof v !== 'object') return null;
      try { return RAPPLY(TSU_STR, v, []); } catch (e) { return null; }
    };
    var asTrusted = function (u) {
      try {
        if (!ttPolicy) ttPolicy = RAPPLY(TT_MAKE, TTP, [TT_NAME, { createScriptURL: function (x) { return x; } }]);
        return RAPPLY(TT_URL, ttPolicy, [u]);
      } catch (e) { return u; }
    };
    var xStatus = getterOf(XP, 'status'), xText = getterOf(XP, 'responseText');
    if (rawCreate && rawRevoke && NBlob) {
      wrap(U, 'createObjectURL', function (orig) {
        return function (obj) {
          var url = RAPPLY(orig, this, arguments);
          try {
            // every blob, whatever its type and size: a worker runs any of them
            // (1.1.18, independent review: other types and large ones got no prelude)
            if (isBlob(obj)) blobs.set(url, obj);
          } catch (e) {}
          return url;
        };
      });
      wrap(U, 'revokeObjectURL', function (orig) {
        return function (url) {
          blobs.delete(url);
          return RAPPLY(orig, this, arguments);
        };
      });
      ['Worker', 'SharedWorker'].forEach(function (name) {
        var Orig = w[name];
        if (typeof Orig !== 'function') return;
        var P = new w.Proxy(Orig, {
          construct: function (target, args, newTarget) {
            var nt = newTarget === P ? target : newTarget;
            // no address: the engine's own TypeError (V-13)
            if (!args.length) { try { return nConstruct(target, args, nt); } catch (e) { clean(e); throw e; } }
            // the address as read here is the one used (an object whose text
            // changes between two readings cannot slip past); a real
            // TrustedScriptURL is read by its own method and kept
            var first = args[0], tt = trustedText(first);
            var url = tt !== null ? tt : `${first}`;
            var opt = workerOptions(args[1], args.length > 1);
            var send = function (u) { return opt.given ? [u, opt.value] : [u]; };
            var call = send(tt !== null ? first : url);
            try {
              if (sslice(url, 0, 5) === 'blob:') {
                var blob = blobs.get(url);
                if (!blob) {
                  // a blob address made elsewhere (in a worker, another frame):
                  // its text is read here, once
                  try {
                    var x = new NXHR();
                    RAPPLY(xOpen, x, ['GET', url, false]);
                    RAPPLY(xSend, x, []);
                    var st = RAPPLY(xStatus, x, []);
                    if (st === 200 || st === 0) blob = new NBlob([RAPPLY(xText, x, [])], { type: 'text/javascript' });
                  } catch (e) {}
                }
                if (blob) {
                  var patched = RAPPLY(rawCreate, U, [new NBlob([preludeFor(url, opt.module), blob],
                    { type: RAPPLY(BLOB_TYPE, blob, []) || 'text/javascript' })]);
                  call = send(tt !== null ? asTrusted(patched) : patched);
                  PATCHED.set(patched, url);
                  // the prelude revokes it at once; this is the fallback
                  RAPPLY(nLater, w, [function () { RAPPLY(rawRevoke, U, [patched]); }, 30000]);
                }
              } else if (lower(sslice(url, 0, 5)) === 'data:') {
                var comma = sindex(url, ',');
                if (comma > 0) {
                  var b64 = lower(sslice(url, comma - 7 < 0 ? 0 : comma - 7, comma)) === ';base64';
                  var pre = preludeFor(url, true);
                  var made = sslice(url, 0, comma + 1) +
                    (b64 ? RAPPLY(nBtoa, w, [pre]) : RAPPLY(nEnc, w, [pre])) + sslice(url, comma + 1);
                  call = send(tt !== null ? asTrusted(made) : made);
                  PATCHED.set(made, url);
                }
              }
            } catch (e) {}
            // the engine's own errors (a policy of Trusted Types, say) without
            // the protection's lines in their stack (M-5)
            try { return nConstruct(target, call, nt); } catch (e) { clean(e); throw e; }
          }
        });
        natives.set(P, RAPPLY(origToString, Orig, []));
        try {
          Object.defineProperty(Orig.prototype, 'constructor',
            { value: P, writable: true, configurable: true });
          Object.defineProperty(w, name, { value: P, writable: true, configurable: true });
        } catch (e) {}
      });
    }
    // a worker's error names the page's own address and line (audit, H-B)
    if (w.ErrorEvent) {
      var errName = getterOf(w.ErrorEvent.prototype, 'filename');
      getter(w.ErrorEvent.prototype, 'filename', function (orig) {
        var f = RAPPLY(orig, this, []), o = typeof f === 'string' ? PATCHED.get(f) : undefined;
        return o !== undefined ? o : f;
      });
      getter(w.ErrorEvent.prototype, 'lineno', function (orig) {
        var n = RAPPLY(orig, this, []), f = errName ? RAPPLY(errName, this, []) : '';
        return typeof f === 'string' && PATCHED.get(f) !== undefined && n > PRELUDE_LINES ? n - PRELUDE_LINES : n;
      });
    }

    guard(w);
  }

  // ---- new empty windows: protect them before the page can use them --------
  var foreign = hardSet();              // frames of other sites: not ours to touch
  // Realms already protected, by their own Function object: a frame that loads
  // a new document keeps its window object but gets a new realm, which is then
  // protected again. Asking a realm whether it is protected (isProtected) costs a
  // call into it; asking this set is free, and pages insert nodes very often.
  var realms = hardSet();
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
      // no frame in this window and a node of this document: check() would
      // find nothing to look at, so the HTML is not searched (1.1.23: the
      // search cost pages that rewrite big lists through innerHTML)
      if (framesOf(w) === 0 && ours(node)) { known = 0; return; }
      if (typeof v !== 'string' || RAPPLY(RE_TEST, FRAME_HTML, [v])) check(node, true);
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
      // With no frame in the window before the call, a node already in this
      // document holds none of its frames: only the count can tell of a new
      // one, and the moved node is not looked at (1.1.23). The guard's count
      // is then left as check() leaves it.
      // What a call costs is mostly the looks (1.1.24, measured in a page:
      // about 50 ns for each of the engine's getters called this way, as much
      // again for the number of frames), so each one is taken only when it
      // can still tell something, in this order:
      // - the nodes put in, as before (text and an element without children
      //   cannot be or hold a frame: one or three looks, and done);
      // - then the target: outside any document (a tree a framework builds
      //   before it puts it in, a fragment, a template's content), nothing
      //   put there gets a window and nothing more is looked at. Taken before
      //   the call, since a replaceWith takes the target itself out. A node
      //   in a shadow root is in the document when its host is;
      // - a call that swaps nodes (force) is looked at after it in any case,
      //   so the count before it, never used, is no longer read;
      // - with no frame in the window at the guard's last look (known 0), the
      //   count before the call is taken as 0: none after it either, no frame
      //   came in; any after it, every frame of the window is looked at,
      //   whatever the call did (a frame added or moved, or one the guard
      //   had not counted yet). With frames at the last look, both counts
      //   are read as before.
      var f = ({ [orig.name || name](a, b) {
        var n = arguments.length, r, pre = 0, moved = false, post;
        if (n === 1) {
          if ((!force && !mayNode(a)) || outside(this)) return invoke(this, a);
          if (!force && known !== 0) { pre = framesOf(w); moved = pre !== 0 && placed(a); }
          r = invoke(this, a);
        } else if (n === 2) {
          if ((!force && !mayNode(a) && !mayNode(b)) || outside(this)) return invoke(this, a, b);
          if (!force && known !== 0) { pre = framesOf(w); moved = pre !== 0 && (placed(a) || placed(b)); }
          r = invoke(this, a, b);
        } else {
          if ((!force && !mayAny(arguments)) || outside(this)) return reflectApply(orig, this, arguments);
          if (!force && known !== 0) {
            pre = framesOf(w);
            if (pre !== 0) for (var i = 0; i < arguments.length; i++) if (placed(arguments[i])) moved = true;
          }
          r = reflectApply(orig, this, arguments);
        }
        if (force) { check(this, true); return r; }
        post = framesOf(w);
        if (moved || post !== pre || !ours(this)) check(this, true);
        else if (post === 0) known = 0;
        return r;
      } })[orig.name || name];
      try { Object.defineProperty(f, 'length', { value: orig.length, configurable: true }); } catch (e) {}
      natives.set(f, RAPPLY(origToString, orig, []));
      d.value = f;
      try { Object.defineProperty(obj, name, d); } catch (e) {}
    }
    // Can this insertion bring a frame into a document? Not for text or an
    // element without children that is not a frame itself, nor when the
    // target is outside any document (outside(), below).
    var FRAMES = { iframe: 1, frame: 1, object: 1, embed: 1 };
    var FRAME_HTML = /<\s*(i?frame|object|embed)\b/i;
    // its own exec and test: RegExp.prototype.test asks the object for exec,
    // which a page could replace (fingerprinting audit, H-A)
    try { Object.defineProperty(FRAME_HTML, 'exec', { value: RE_EXEC }); } catch (e) {}
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
      if (typeof a === 'string') return RAPPLY(RE_TEST, FRAME_HTML, [a]);      // insertAdjacentHTML, before('...')
      if (!a || (typeof a !== 'object' && typeof a !== 'function')) return false;
      var t;
      try { t = nodeTypeOf(a); } catch (e) { return true; }      // not a node (TrustedHTML...): may be HTML
      if (t === 11) return true;                                 // a fragment
      if (t !== 1) return false;                                 // text, comments
      // children first (the usual subtree), then the element's own name,
      // compared as it is (no lookup by a name: 1.1.24)
      try {
        if (firstElementOf(a) !== null) return true;
        var ln = localNameOf(a);
        return ln === 'iframe' || ln === 'frame' || ln === 'object' || ln === 'embed';
      } catch (e) { return true; }
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
    // a target outside any document (a tree being built, a fragment, a
    // template's content): a frame put there gets no window, and the nodes a
    // call puts next to it (before, after, replaceWith) are outside too. A
    // node in a shadow root counts as in the document when its host is. Not
    // a node (a Range, anything else): not outside (1.1.24).
    function outside(t) {
      try { return connectedOf(t) === false; } catch (e) { return false; }
    }
    // a target of this document (or outside any document), not of another one
    function ours(target) {
      if (target === own) return true;
      // the usual answer first: a node of this document (1.1.23)
      try { if (ownerOf(target) === own) return true; } catch (e) {}
      return docOf(target) === own;
    }
    function hooked(obj, name) { hook(obj, name, false); }
    function swapped(obj, name) { hook(obj, name, true); }
    [w.HTMLIFrameElement, w.HTMLFrameElement, w.HTMLObjectElement, w.HTMLEmbedElement].forEach(function (E) {
      if (!E) return;
      getter(E.prototype, 'contentWindow', function (orig) {
        var cw = RAPPLY(orig, this, []);
        adopt(cw);
        return cw;
      });
      getter(E.prototype, 'contentDocument', function (orig) {
        var d = RAPPLY(orig, this, []);
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
        var r = RAPPLY(orig, this, arguments);
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
      natives.set(f, natives.get(orig) || RAPPLY(origToString, orig, []));
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
