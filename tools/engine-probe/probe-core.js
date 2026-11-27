// Engine probe, shared part: runs in a window, a dedicated worker, a shared
// worker and a service worker. Collects what a website can observe of the
// web engine (engine-privacy-layer feasibility study, 2026-11). Diagnostic
// tool only: never loaded by the browser itself.
/* eslint-disable no-new-func */
var PROBE = (function () {
  'use strict';
  var G = typeof self !== 'undefined' ? self : this;
  var OWN = Object.getOwnPropertyNames;

  function safe(fn, dflt) {
    try { return fn(); } catch (e) { return dflt === undefined ? 'ERR:' + (e && e.name) + ':' + (e && e.message) : dflt; }
  }
  async function asafe(fn) {
    try { return await fn(); } catch (e) { return 'ERR:' + (e && e.name) + ':' + (e && e.message); }
  }
  function withTimeout(p, ms) {
    return Promise.race([p, new Promise(function (ok) { setTimeout(function () { ok('TIMEOUT'); }, ms); })]);
  }

  // ---- Web IDL / JS surface: every global, every interface's members --------
  var SKIP = { PROBE: 1, __probe: 1, onmessage: 1 };
  function protoNames(p) {
    return safe(function () { return OWN(p).concat(Object.getOwnPropertySymbols(p).map(String)).sort(); }, []);
  }
  function surface(g) {
    var out = {};
    var names = OWN(g).filter(function (n) { return !SKIP[n] && !/^(?:\d+|probe.*)$/.test(n); }).sort();
    names.forEach(function (n) {
      var d = safe(function () { return Object.getOwnPropertyDescriptor(g, n); }, null);
      var v = d && ('value' in d) ? d.value : undefined;
      var kind = d ? (('value' in d) ? typeof v : 'accessor') : '?';
      var e = { k: kind };
      if (kind === 'function' && v.prototype && /^[A-Z]/.test(n)) {
        e.p = protoNames(v.prototype).filter(function (x) { return x !== 'constructor'; });
        e.s = OWN(v).filter(function (x) { return ['length', 'name', 'prototype', 'arguments', 'caller'].indexOf(x) < 0; }).sort();
        var parent = Object.getPrototypeOf(v.prototype);
        e.i = parent && parent.constructor ? parent.constructor.name : null;
      } else if (kind === 'object' && v && /^[A-Z]/.test(n) && n !== 'PROBE') {
        // namespaces: Math, Intl, WebAssembly, CSS, Atomics, Reflect, JSON, Temporal...
        e.m = OWN(v).sort();
        if (n === 'Intl' || n === 'WebAssembly' || n === 'Temporal') {
          e.sub = {};
          e.m.forEach(function (m) {
            var c = v[m];
            if (typeof c === 'function' && c.prototype) e.sub[m] = { p: protoNames(c.prototype), s: OWN(c).sort() };
          });
        }
      }
      out[n] = e;
    });
    // the global's own prototype chain (Window.prototype, EventTarget...), for workers too
    var chain = [], p = Object.getPrototypeOf(g);
    while (p && p !== Object.prototype) { chain.push({ n: safe(function () { return p.constructor.name; }, '?'), m: protoNames(p) }); p = Object.getPrototypeOf(p); }
    return { globals: out, chain: chain };
  }

  // ---- V8: error messages, stack format, native function text -------------
  var ERRS = [
    'null.x', 'undefined.x()', 'var a; a()', '({}).x()', 'new (function(){}).x', 'x = y_undefined_var',
    'JSON.parse("{")', 'JSON.parse("")', 'new Array(-1)', '(1).toFixed(200)', 'Symbol() + ""', 'BigInt(1.5)',
    '1n + 1', 'structuredClone(function(){})', 'new Proxy({}, {get(){ throw 1 }}).x; null.y', 'class A { #x; static t(o){ return o.#x } }; A.t({})',
    'Object.defineProperty(Object.freeze({}), "a", {value:1})', '"use strict"; Object.freeze([]).push(1)', 'new Uint8Array(-1)',
    'decodeURIComponent("%")', 'new RegExp("[")', '"abc".repeat(-1)', 'await_x', 'let z = 1; let z = 2', 'Reflect.construct(1)',
    'new Intl.DateTimeFormat("en", {timeZone: "Bad/Zone"})', 'atob("*")', 'new URL("x")', 'new ArrayBuffer(1, {maxByteLength: 0})',
    'Array.prototype.at.call(null)', '[].reduce(function(){})', 'new WeakRef(1)', 'Iterator.from(1)', 'structuredClone(Symbol())',
    'new Set().union(1)', 'Promise.withResolvers.call(1)', 'Object.groupBy(null)', 'Atomics.wait(new Int32Array(1), 0, 0, 0)',
    'new Function("a", "return a +")', 'eval("{")', 'async function* g(){}; g().next.call(1)', 'Math.sumPrecise([1n])',
    'Error.captureStackTrace(1)', 'Uint8Array.fromBase64("*")', 'new Float16Array(-1)', 'RegExp.escape(1)'
  ];
  function errors() {
    var out = {};
    ERRS.forEach(function (src) {
      try { (0, eval)(src); out[src] = 'no error'; } catch (e) { out[src] = (e && e.constructor && e.constructor.name) + ': ' + (e && e.message); }
    });
    return out;
  }
  function stackShape() {
    function inner() { return new Error('probe').stack; }
    var s = safe(function () { return inner(); }, '');
    var lines = String(s).split('\n').map(function (l) { return l.replace(/(https?|blob):[^\s)]+/g, 'URL').replace(/:\d+:\d+/g, ':L:C'); });
    return {
      lines: lines.slice(0, 4),
      limit: Error.stackTraceLimit,
      capture: typeof Error.captureStackTrace,
      prepare: typeof Error.prepareStackTrace,
      isError: typeof Error.isError,
      evalStack: safe(function () { return String((0, eval)('new Error("e").stack')).split('\n')[1].replace(/:\d+:\d+/g, ':L:C').replace(/(https?|blob):[^\s)]+/g, 'URL'); }),
      asyncStack: null
    };
  }
  function natives() {
    var fts = Function.prototype.toString;
    function t(f) { return safe(function () { return fts.call(f); }); }
    return {
      max: t(Math.max), toStr: t(fts), getter: t(Object.getOwnPropertyDescriptor(Symbol.prototype, 'description').get),
      bound: t(function a() {}.bind(null)), cls: t(class Q { m() {} }), arrow: t(() => 1), proxy: t(new Proxy(function () {}, {})),
      async: t(async function a() {}), gen: t(function* g() {}), fetchName: G.fetch ? G.fetch.name + '/' + G.fetch.length : null
    };
  }

  // ---- Intl / ICU ------------------------------------------------------------
  function intl() {
    var d = new Date(Date.UTC(2026, 2, 29, 1, 30, 0));
    var out = {
      resolved: safe(function () { return Intl.DateTimeFormat().resolvedOptions(); }),
      numberResolved: safe(function () { return new Intl.NumberFormat().resolvedOptions(); }),
      dateToString: safe(function () { return new Date(0).toString(); }),
      tzOffset: new Date(0).getTimezoneOffset(),
      fmt: {}
    };
    ['calendar', 'collation', 'currency', 'numberingSystem', 'timeZone', 'unit'].forEach(function (k) {
      out['values_' + k] = safe(function () { var v = Intl.supportedValuesOf(k); return { n: v.length, h: hash(v.join(',')), sample: v.slice(0, 3) }; });
    });
    out.tzNames = safe(function () { return Intl.supportedValuesOf('timeZone').filter(function (z) { return /Kyiv|Kiev|Calcutta|Kolkata|Ciudad_Juarez|Nuuk|Godthab/.test(z); }); });
    [['en-US', { dateStyle: 'full', timeStyle: 'full', timeZone: 'America/New_York' }],
      ['de-DE', { dateStyle: 'full', timeStyle: 'long', timeZone: 'Europe/Rome' }],
      ['ja-JP-u-ca-japanese', { dateStyle: 'full', timeZone: 'Asia/Tokyo' }],
      ['ar-EG', { dateStyle: 'medium', timeStyle: 'medium', timeZone: 'Africa/Cairo' }],
      ['en-IN', { timeStyle: 'full', timeZone: 'Asia/Kolkata' }],
      ['it-IT', { dateStyle: 'full', timeZone: 'Pacific/Apia' }]].forEach(function (a) {
      out.fmt[a[0] + ' ' + JSON.stringify(a[1])] = safe(function () { return new Intl.DateTimeFormat(a[0], a[1]).format(d); });
    });
    out.num = safe(function () {
      return [new Intl.NumberFormat('de-CH').format(1234567.891), new Intl.NumberFormat('en', { style: 'unit', unit: 'kilowatt-hour' }).format(3),
        new Intl.NumberFormat('hi-IN', { notation: 'compact' }).format(123456789), new Intl.NumberFormat('en', { style: 'currency', currency: 'EUR', currencyDisplay: 'name' }).format(2.5)];
    });
    out.rel = safe(function () { return new Intl.RelativeTimeFormat('es', { numeric: 'auto' }).format(-1, 'day'); });
    out.list = safe(function () { return new Intl.ListFormat('fr', { type: 'disjunction' }).format(['a', 'b', 'c']); });
    out.display = safe(function () { return [new Intl.DisplayNames('en', { type: 'region' }).of('TR'), new Intl.DisplayNames('en', { type: 'language' }).of('yue-Hant')]; });
    out.collate = safe(function () { return ['ä', 'a', 'z', 'ø', 'ç', 'C', 'ss', 'ß'].sort(new Intl.Collator('sv').compare).join(''); });
    out.seg = safe(function () { return Array.from(new Intl.Segmenter('th', { granularity: 'word' }).segment('สวัสดีครับ')).length; });
    out.duration = safe(function () { return new Intl.DurationFormat('en', { style: 'long' }).format({ hours: 1, minutes: 2 }); });
    out.localeInfo = safe(function () { var l = new Intl.Locale('ar-EG'); return [typeof l.getWeekInfo, typeof l.weekInfo, JSON.stringify(l.getWeekInfo ? l.getWeekInfo() : l.weekInfo)]; });
    out.toLocale = safe(function () { return [(1234.5).toLocaleString(), d.toLocaleString(), 'İ'.toLocaleLowerCase('tr')]; });
    return out;
  }

  function hash(s) { var h = 2166136261; s = String(s); for (var i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return (h >>> 0).toString(16); }

  // ---- navigator --------------------------------------------------------------
  async function nav() {
    var n = G.navigator || {};
    var out = {};
    ['userAgent', 'appVersion', 'appName', 'appCodeName', 'platform', 'product', 'productSub', 'vendor', 'vendorSub', 'language',
      'languages', 'hardwareConcurrency', 'deviceMemory', 'maxTouchPoints', 'pdfViewerEnabled', 'webdriver', 'cookieEnabled',
      'doNotTrack', 'globalPrivacyControl', 'onLine', 'oscpu', 'buildID'].forEach(function (k) {
      out[k] = safe(function () { var v = n[k]; return v && typeof v === 'object' ? Array.from(v) : v; });
    });
    out.connection = safe(function () { var c = n.connection; return c ? { type: c.type, effectiveType: c.effectiveType, rtt: c.rtt, downlink: c.downlink, downlinkMax: c.downlinkMax, saveData: c.saveData } : null; });
    if (n.userAgentData) {
      out.uaLow = safe(function () { return n.userAgentData.toJSON(); });
      out.uaHigh = await asafe(function () {
        return withTimeout(n.userAgentData.getHighEntropyValues(['architecture', 'bitness', 'brands', 'formFactors', 'fullVersionList',
          'model', 'mobile', 'platform', 'platformVersion', 'uaFullVersion', 'wow64']), 3000);
      });
    } else { out.uaLow = null; }
    if (n.storage && n.storage.estimate) out.quota = await asafe(function () { return withTimeout(n.storage.estimate().then(function (e) { return e.quota; }), 3000); });
    if (n.storage && n.storage.persisted) out.persisted = await asafe(function () { return withTimeout(n.storage.persisted(), 2000); });
    out.plugins = safe(function () {
      return n.plugins ? Array.from(n.plugins).map(function (p) { return [p.name, p.filename, p.description, Array.from(p).map(function (m) { return m.type + '|' + m.suffixes; }).join(',')]; }) : null;
    });
    out.mimeTypes = safe(function () { return n.mimeTypes ? Array.from(n.mimeTypes).map(function (m) { return m.type + '|' + m.suffixes + '|' + (m.enabledPlugin && m.enabledPlugin.name); }) : null; });
    out.gpu = !!n.gpu;
    if (n.gpu) {
      out.webgpu = await asafe(function () {
        return withTimeout(n.gpu.requestAdapter().then(function (a) {
          if (!a) return null;
          var i = a.info || {};
          var lim = {}; for (var k in a.limits) lim[k] = a.limits[k];
          return { vendor: i.vendor, architecture: i.architecture, device: i.device, description: i.description, isFallback: i.isFallbackAdapter,
            features: Array.from(a.features).sort(), limits: lim };
        }), 5000);
      });
      out.wgsl = safe(function () { return n.gpu.wgslLanguageFeatures ? Array.from(n.gpu.wgslLanguageFeatures).sort() : null; });
      out.gpuPreferred = safe(function () { return n.gpu.getPreferredCanvasFormat(); });
    }
    return out;
  }

  // ---- WebGL (window or OffscreenCanvas) ------------------------------------
  function webgl() {
    var out = {};
    ['webgl', 'webgl2'].forEach(function (kind) {
      out[kind] = safe(function () {
        var c = typeof document !== 'undefined' ? document.createElement('canvas') : new OffscreenCanvas(16, 16);
        var g = c.getContext(kind);
        if (!g) return null;
        var r = { ext: (g.getSupportedExtensions() || []).slice().sort() };
        var P = ['VENDOR', 'RENDERER', 'VERSION', 'SHADING_LANGUAGE_VERSION', 'MAX_TEXTURE_SIZE', 'MAX_RENDERBUFFER_SIZE', 'MAX_VIEWPORT_DIMS',
          'MAX_VERTEX_ATTRIBS', 'MAX_VERTEX_UNIFORM_VECTORS', 'MAX_FRAGMENT_UNIFORM_VECTORS', 'MAX_VARYING_VECTORS', 'MAX_COMBINED_TEXTURE_IMAGE_UNITS',
          'MAX_TEXTURE_IMAGE_UNITS', 'MAX_VERTEX_TEXTURE_IMAGE_UNITS', 'MAX_CUBE_MAP_TEXTURE_SIZE', 'ALIASED_LINE_WIDTH_RANGE', 'ALIASED_POINT_SIZE_RANGE',
          'MAX_SAMPLES', 'MAX_3D_TEXTURE_SIZE', 'MAX_ARRAY_TEXTURE_LAYERS', 'MAX_DRAW_BUFFERS', 'MAX_UNIFORM_BLOCK_SIZE', 'MAX_COLOR_ATTACHMENTS'];
        r.p = {};
        P.forEach(function (k) { if (g[k] !== undefined) { var v = g.getParameter(g[k]); r.p[k] = v && v.length !== undefined && typeof v !== 'string' ? Array.from(v) : v; } });
        var dbg = g.getExtension('WEBGL_debug_renderer_info');
        if (dbg) { r.p.UNMASKED_VENDOR = g.getParameter(dbg.UNMASKED_VENDOR_WEBGL); r.p.UNMASKED_RENDERER = g.getParameter(dbg.UNMASKED_RENDERER_WEBGL); }
        var hp = g.getShaderPrecisionFormat(g.FRAGMENT_SHADER, g.HIGH_FLOAT);
        r.prec = hp ? [hp.rangeMin, hp.rangeMax, hp.precision] : null;
        r.attrs = g.getContextAttributes();
        return r;
      });
    });
    return out;
  }

  // ---- media, codecs, DRM -------------------------------------------------
  var TYPES = ['video/mp4; codecs="avc1.42E01E"', 'video/mp4; codecs="avc1.640028"', 'video/mp4; codecs="hev1.1.6.L93.B0"', 'video/mp4; codecs="hvc1.1.6.L123.00"',
    'video/mp4; codecs="av01.0.05M.08"', 'video/mp4; codecs="vp09.00.10.08"', 'video/mp4; codecs="dvh1.05.06"', 'video/webm; codecs="vp8"', 'video/webm; codecs="vp9"',
    'video/webm; codecs="vp09.02.10.10"', 'video/webm; codecs="av1"', 'video/ogg; codecs="theora"', 'video/x-matroska', 'video/mp2t', 'video/quicktime',
    'audio/mp4; codecs="mp4a.40.2"', 'audio/mp4; codecs="mp4a.40.5"', 'audio/mp4; codecs="ac-3"', 'audio/mp4; codecs="ec-3"', 'audio/mp4; codecs="opus"',
    'audio/mp4; codecs="flac"', 'audio/mpeg', 'audio/aac', 'audio/ogg; codecs="opus"', 'audio/ogg; codecs="vorbis"', 'audio/ogg; codecs="flac"', 'audio/flac', 'audio/wav',
    'audio/webm; codecs="opus"', 'audio/x-m4a', 'application/vnd.apple.mpegurl', 'application/x-mpegurl', 'audio/mp4; codecs="alac"', 'audio/x-matroska'];
  var REC = ['video/webm', 'video/webm;codecs=vp8', 'video/webm;codecs=vp9', 'video/webm;codecs=av1', 'video/webm;codecs=h264', 'video/webm;codecs=vp8,opus',
    'video/x-matroska;codecs=avc1', 'video/mp4', 'video/mp4;codecs=avc1', 'video/mp4;codecs=avc3', 'video/mp4;codecs=hvc1', 'video/mp4;codecs=av01', 'video/mp4;codecs=vp9',
    'video/mp4;codecs=avc1,mp4a.40.2', 'video/mp4;codecs=avc1,opus', 'audio/webm;codecs=opus', 'audio/mp4', 'audio/mp4;codecs=mp4a.40.2', 'audio/mp4;codecs=opus',
    'audio/ogg;codecs=opus', 'audio/webm;codecs=pcm'];
  async function media() {
    var out = {};
    if (typeof document !== 'undefined') {
      var v = document.createElement('video');
      out.canPlay = {}; TYPES.forEach(function (t) { out.canPlay[t] = v.canPlayType(t); });
    }
    var MS = G.MediaSource || G.ManagedMediaSource;
    if (MS) { out.mse = {}; TYPES.forEach(function (t) { out.mse[t] = safe(function () { return MS.isTypeSupported(t); }); }); }
    if (G.MediaRecorder) { out.rec = {}; REC.forEach(function (t) { out.rec[t] = MediaRecorder.isTypeSupported(t); }); }
    if (G.VideoDecoder) {
      out.webcodecs = {};
      var vc = ['avc1.42001E', 'avc1.640028', 'vp8', 'vp09.00.10.08', 'av01.0.04M.08', 'hvc1.1.6.L123.00', 'hev1.1.6.L93.B0'];
      for (var i = 0; i < vc.length; i++) {
        var c = vc[i];
        out.webcodecs['dec ' + c] = await asafe(function () { return withTimeout(VideoDecoder.isConfigSupported({ codec: c }).then(function (r) { return r.supported; }), 3000); });
        out.webcodecs['enc ' + c] = await asafe(function () { return withTimeout(VideoEncoder.isConfigSupported({ codec: c, width: 640, height: 480, bitrate: 1e6, framerate: 30 }).then(function (r) { return r.supported; }), 3000); });
      }
      var ac = ['opus', 'mp4a.40.2', 'flac', 'mp3', 'vorbis', 'ulaw', 'alaw', 'pcm-s16'];
      for (var j = 0; j < ac.length; j++) {
        var a = ac[j];
        out.webcodecs['adec ' + a] = await asafe(function () { return withTimeout(AudioDecoder.isConfigSupported({ codec: a, sampleRate: 48000, numberOfChannels: 2 }).then(function (r) { return r.supported; }), 3000); });
        out.webcodecs['aenc ' + a] = await asafe(function () { return withTimeout(AudioEncoder.isConfigSupported({ codec: a, sampleRate: 48000, numberOfChannels: 2, bitrate: 128000 }).then(function (r) { return r.supported; }), 3000); });
      }
    }
    if (G.navigator && navigator.mediaCapabilities) {
      out.mcap = {};
      var cfgs = { h264: 'video/mp4; codecs="avc1.640028"', vp9: 'video/webm; codecs="vp09.00.10.08"', av1: 'video/mp4; codecs="av01.0.05M.08"', hevc: 'video/mp4; codecs="hvc1.1.6.L123.00"' };
      for (var k in cfgs) {
        var ct = cfgs[k];
        out.mcap[k] = await asafe(function () {
          return withTimeout(navigator.mediaCapabilities.decodingInfo({ type: 'media-source', video: { contentType: ct, width: 1920, height: 1080, bitrate: 5e6, framerate: 30 } })
            .then(function (r) { return [r.supported, r.smooth, r.powerEfficient]; }), 3000);
        });
      }
    }
    if (G.RTCRtpSender && RTCRtpSender.getCapabilities) {
      out.rtc = safe(function () {
        return ['audio', 'video'].map(function (k) { var c = RTCRtpSender.getCapabilities(k); return c.codecs.map(function (x) { return x.mimeType + ' ' + (x.sdpFmtpLine || ''); }).join(' | '); });
      });
      out.rtcRecv = safe(function () { return ['audio', 'video'].map(function (k) { return RTCRtpReceiver.getCapabilities(k).codecs.length; }); });
    }
    if (G.navigator && navigator.requestMediaKeySystemAccess) {
      out.eme = {};
      var cfg = [{ initDataTypes: ['cenc'], videoCapabilities: [{ contentType: 'video/mp4; codecs="avc1.42E01E"' }], audioCapabilities: [{ contentType: 'audio/mp4; codecs="mp4a.40.2"' }] }];
      var ks = ['com.widevine.alpha', 'org.w3.clearkey', 'com.microsoft.playready', 'com.apple.fps'];
      for (var m = 0; m < ks.length; m++) {
        var key = ks[m];
        out.eme[key] = await asafe(function () { return withTimeout(navigator.requestMediaKeySystemAccess(key, cfg).then(function (a) { var c = a.getConfiguration(); return 'ok ' + (c.videoCapabilities || []).map(function (x) { return x.robustness; }).join(','); }), 4000); });
      }
    }
    if (G.speechSynthesis) {
      out.voices = await asafe(function () {
        return withTimeout(new Promise(function (ok) {
          var v0 = speechSynthesis.getVoices();
          if (v0.length) return ok(v0);
          speechSynthesis.onvoiceschanged = function () { ok(speechSynthesis.getVoices()); };
          setTimeout(function () { ok(speechSynthesis.getVoices()); }, 1500);
        }).then(function (vs) { return vs.map(function (x) { return x.name + '|' + x.lang + '|' + x.localService; }); }), 3000);
      });
    }
    if (G.AudioContext || G.OfflineAudioContext) {
      out.audio = safe(function () {
        var ctx = new (G.OfflineAudioContext)(1, 44100, 44100);
        return { rate: ctx.sampleRate, base: (G.AudioContext && new AudioContext().baseLatency) };
      });
    }
    return out;
  }

  // ---- permissions -------------------------------------------------------------
  var PERMS = ['geolocation', 'notifications', 'push', 'midi', 'camera', 'microphone', 'speaker-selection', 'background-fetch', 'background-sync',
    'periodic-background-sync', 'persistent-storage', 'ambient-light-sensor', 'accelerometer', 'gyroscope', 'magnetometer', 'clipboard-read',
    'clipboard-write', 'payment-handler', 'idle-detection', 'screen-wake-lock', 'system-wake-lock', 'nfc', 'display-capture', 'storage-access',
    'top-level-storage-access', 'window-management', 'local-fonts', 'captured-surface-control', 'keyboard-lock', 'pointer-lock', 'fullscreen',
    'web-app-installation', 'local-network-access', 'local-network', 'loopback-network', 'web-printing', 'handwriting-recognition'];
  async function perms() {
    if (!(G.navigator && navigator.permissions)) return null;
    var out = {};
    for (var i = 0; i < PERMS.length; i++) {
      var name = PERMS[i];
      var d = name === 'push' ? { name: name, userVisibleOnly: true } : name === 'midi' ? { name: name, sysex: true } : { name: name };
      out[name] = await asafe(function () { return withTimeout(navigator.permissions.query(d).then(function (s) { return s.state; }), 2000); });
    }
    return out;
  }

  // ---- timers --------------------------------------------------------------
  function timer() {
    var min = Infinity, last = performance.now(), t0 = last, n = 0;
    while (n < 200000) { var t = performance.now(); if (t !== last) { min = Math.min(min, t - last); last = t; } n++; if (t - t0 > 30) break; }
    return { minStep: Math.round(min * 1e6) / 1e6, origin: G.crossOriginIsolated };
  }

  // ---- everything for one realm -------------------------------------------
  async function collect(where) {
    var r = { where: where, t0: Date.now() };
    r.surface = surface(G);
    r.errors = errors();
    r.stack = stackShape();
    r.natives = natives();
    r.intl = intl();
    r.nav = await nav();
    r.webgl = webgl();
    r.media = await media();
    r.perms = await perms();
    r.timer = timer();
    r.misc = {
      isSecure: G.isSecureContext,
      wasm: typeof WebAssembly,
      sab: typeof SharedArrayBuffer,
      atomicsPause: typeof (G.Atomics && Atomics.pause),
      temporal: typeof G.Temporal,
      sym: OWN(Symbol).filter(function (s) { return typeof Symbol[s] === 'symbol'; }).sort(),
      maxString: safe(function () { var s = 'x'; try { 'x'.repeat(2 ** 30); return '>=2^30'; } catch (e) { return String(e.message); } })
    };
    r.ms = Date.now() - r.t0;
    return r;
  }

  return { collect: collect, hash: hash, safe: safe, asafe: asafe, withTimeout: withTimeout };
})();
if (typeof self !== 'undefined') self.PROBE = PROBE;
