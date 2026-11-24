// usable in window and workers: collect() -> promise of an object
var G = (typeof self !== 'undefined') ? self : window;
G.collect = async function collect() {
  var n = G.navigator, o = {};
  o.ua = n.userAgent; o.appVersion = n.appVersion; o.platform = n.platform;
  o.hc = n.hardwareConcurrency; o.dm = n.deviceMemory; o.lang = n.language; o.langs = Array.from(n.languages || []);
  try { o.brands = n.userAgentData.brands.map(function (b) { return b.brand + '/' + b.version; });
    var he = await n.userAgentData.getHighEntropyValues(['platformVersion', 'fullVersionList', 'uaFullVersion', 'architecture', 'bitness', 'model', 'wow64', 'formFactors']);
    o.he = JSON.parse(JSON.stringify(he)); o.heKeys = Object.keys(he);
    o.toJSON = JSON.stringify(n.userAgentData.toJSON()); } catch (e) { o.he = 'ERR ' + e; }
  try { var c = n.connection; o.net = c ? [c.effectiveType, c.rtt, c.downlink, c.saveData, c.type] : null; } catch (e) { o.net = 'ERR ' + e; }
  try { var r = Intl.DateTimeFormat().resolvedOptions(); o.intl = [r.locale, r.timeZone, new Intl.NumberFormat().resolvedOptions().locale, (1234.5).toLocaleString(), new Date(0).toLocaleString()]; } catch (e) {}
  try { o.gpu = G.navigator.gpu ? String(await G.navigator.gpu.requestAdapter()) : 'nogpu'; } catch (e) { o.gpu = 'ERR ' + e; }
  o.gl = {};
  ['webgl', 'webgl2'].forEach(function (kind) {
    try {
      var cv = (typeof OffscreenCanvas !== 'undefined' && typeof document === 'undefined') ? new OffscreenCanvas(8, 8) : document.createElement('canvas');
      var g = cv.getContext(kind); if (!g) { o.gl[kind] = null; return; }
      var x = {};
      x.pre = [g.getParameter(37445), g.getParameter(37446), g.getError()];
      x.exts = g.getSupportedExtensions();
      var d = g.getExtension('WEBGL_debug_renderer_info');
      x.id = [g.getParameter(g.VENDOR), g.getParameter(g.RENDERER), g.getParameter(g.VERSION), g.getParameter(g.SHADING_LANGUAGE_VERSION), d ? g.getParameter(37445) : null, d ? g.getParameter(37446) : null];
      var P = {};
      for (var k in g) { if (/^[A-Z0-9_]+$/.test(k) && typeof g[k] === 'number') { try { var v = g.getParameter(g[k]); if (g.getError() === 0 && v !== null && (typeof v === 'number' || typeof v === 'boolean' || (v && v.length !== undefined && typeof v !== 'string'))) P[k] = (typeof v === 'object') ? Array.from(v) : v; } catch (e) {} } }
      x.params = P;
      var ex = g.getExtension('EXT_texture_filter_anisotropic'); if (ex) x.aniso = g.getParameter(ex.MAX_TEXTURE_MAX_ANISOTROPY_EXT);
      var sp = {};
      ['VERTEX_SHADER', 'FRAGMENT_SHADER'].forEach(function (s) { ['LOW_FLOAT', 'MEDIUM_FLOAT', 'HIGH_FLOAT', 'LOW_INT', 'MEDIUM_INT', 'HIGH_INT'].forEach(function (p) { var f = g.getShaderPrecisionFormat(g[s], g[p]); sp[s[0] + p] = [f.rangeMin, f.rangeMax, f.precision]; }); });
      x.prec = sp; x.attrs = g.getContextAttributes();
      x.hiddenExt = ['EXT_disjoint_timer_query', 'EXT_disjoint_timer_query_webgl2', 'WEBGL_compressed_texture_astc', 'WEBGL_compressed_texture_etc', 'EXT_texture_norm16', 'WEBGL_polygon_mode', 'EXT_clip_control'].map(function (e) { return !!g.getExtension(e); });
      // behaviour probes of the real limits
      var b = {};
      try { var mt = g.getParameter(g.MAX_TEXTURE_SIZE); var t = g.createTexture(); g.bindTexture(g.TEXTURE_2D, t); g.getError();
        g.texImage2D(g.TEXTURE_2D, 0, g.RGBA, mt * 2, 1, 0, g.RGBA, g.UNSIGNED_BYTE, null); b.tex2x = g.getError(); } catch (e) { b.tex2x = 'ERR ' + e; }
      try { var mu = g.getParameter(g.MAX_COMBINED_TEXTURE_IMAGE_UNITS); var hi = 0; for (var u = mu; u < 512; u++) { g.activeTexture(g.TEXTURE0 + u); if (g.getError() !== 0) break; hi = u + 1; } b.units = [mu, hi]; g.activeTexture(g.TEXTURE0); } catch (e) { b.units = 'ERR ' + e; }
      try { var ma = g.getParameter(g.MAX_VERTEX_ATTRIBS); var ha = 0; for (var a = ma; a < 128; a++) { g.enableVertexAttribArray(a); if (g.getError() !== 0) break; ha = a + 1; } b.attribs = [ma, ha]; } catch (e) {}
      try { var mr = g.getParameter(g.MAX_RENDERBUFFER_SIZE); var rb = g.createRenderbuffer(); g.bindRenderbuffer(g.RENDERBUFFER, rb); g.renderbufferStorage(g.RENDERBUFFER, g.RGBA4, mr * 2, 1); b.rb2x = g.getError(); } catch (e) {}
      try { var mv = g.getParameter(g.MAX_VIEWPORT_DIMS); g.viewport(0, 0, 65536, 65536); b.viewport = [Array.from(mv), Array.from(g.getParameter(g.VIEWPORT))]; } catch (e) {}
      try { g.lineWidth(100); b.line = [Array.from(g.getParameter(g.ALIASED_LINE_WIDTH_RANGE)), g.getParameter(g.LINE_WIDTH)]; } catch (e) {}
      try { var ds = g.getExtension('WEBGL_debug_shaders'); if (ds) { var sh = g.createShader(g.FRAGMENT_SHADER); g.shaderSource(sh, 'precision mediump float; void main(){ gl_FragColor = vec4(1.0); }'); g.compileShader(sh); b.translated = ds.getTranslatedShaderSource(sh).slice(0, 300); } } catch (e) { b.translated = 'ERR ' + e; }
      // flat colour readPixels
      try { g.bindFramebuffer(g.FRAMEBUFFER, null); g.viewport(0, 0, 8, 8); g.clearColor(0.2, 0.4, 0.6, 1); g.clear(g.COLOR_BUFFER_BIT); var px = new Uint8Array(8 * 8 * 4); g.readPixels(0, 0, 8, 8, g.RGBA, g.UNSIGNED_BYTE, px);
        var bad = 0; for (var i = 0; i < px.length; i += 4) if (px[i] !== 51 || px[i + 1] !== 102 || px[i + 2] !== 153 || px[i + 3] !== 255) bad++; b.flatBad = bad; b.flat0 = Array.from(px.slice(0, 8)); } catch (e) { b.flatBad = 'ERR ' + e; }
      x.behave = b;
      o.gl[kind] = x;
    } catch (e) { o.gl[kind] = 'ERR ' + e + ' ' + (e.stack || ''); }
  });
  // 2D known answer in this context
  try {
    var OC = (typeof document === 'undefined') ? new OffscreenCanvas(16, 16) : (function () { var c = document.createElement('canvas'); c.width = c.height = 16; return c; })();
    var c2 = OC.getContext('2d'); var id = new ImageData(16, 16);
    for (var i2 = 0; i2 < id.data.length; i2 += 4) { var q = (i2 / 4); id.data[i2] = (q * 37) & 255; id.data[i2 + 1] = (q * 91) & 255; id.data[i2 + 2] = (q * 13) & 255; id.data[i2 + 3] = 255; }
    c2.putImageData(id, 0, 0); var back = c2.getImageData(0, 0, 16, 16).data, diff = 0;
    for (var i3 = 0; i3 < back.length; i3++) if (back[i3] !== id.data[i3]) diff++;
    o.putRoundTripDiff = diff;
  } catch (e) { o.putRoundTripDiff = 'ERR ' + e; }
  return o;
};
