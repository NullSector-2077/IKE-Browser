// a file worker: what a fingerprinting script reads there
onmessage = async function () {
  var o = {};
  try {
    var c = new OffscreenCanvas(300, 60), x = c.getContext('2d');
    var fonts = ['Arial', 'DejaVu Sans', 'Liberation Sans', 'Noto Sans', 'Cantarell', 'Ubuntu', 'Fira Code', 'Noto Color Emoji', 'Times New Roman', 'Helvetica', 'Courier New', 'Bitstream Vera Sans', 'Droid Sans', 'NoSuchFont123'];
    x.font = '72px monospace'; var base = x.measureText('mmmmmmmmmmlli').width; x.font = '72px serif'; var base2 = x.measureText('mmmmmmmmmmlli').width;
    o.fonts = fonts.filter(function (f) { x.font = "72px '" + f + "', monospace"; var a = x.measureText('mmmmmmmmmmlli').width; x.font = "72px '" + f + "', serif"; var b = x.measureText('mmmmmmmmmmlli').width; return a !== base || b !== base2; });
    x.font = '16px Arial'; x.fillText('Cwm fjordbank glyphs vext quiz 😃', 2, 20); x.arc(200, 30, 20, 0, 7); x.stroke();
    var d = x.getImageData(0, 0, 300, 60).data, h = 2166136261; for (var i = 0; i < d.length; i++) { h ^= d[i]; h = Math.imul(h, 16777619); } o.canvasHash = h >>> 0;
    var d2 = x.getImageData(0, 0, 300, 60).data, h2 = 2166136261; for (i = 0; i < d2.length; i++) { h2 ^= d2[i]; h2 = Math.imul(h2, 16777619); } o.canvasHash2 = h2 >>> 0;
  } catch (e) { o.err = String(e); }
  o.tz = Intl.DateTimeFormat().resolvedOptions().timeZone; o.hc = navigator.hardwareConcurrency; o.dm = navigator.deviceMemory;
  try { var q = await navigator.storage.estimate(); o.quota = q.quota; } catch (e) {}
  try { o.fontsApi = self.fonts ? self.fonts.check('16px "DejaVu Sans"') : null; } catch (e) {}
  postMessage(o);
};
