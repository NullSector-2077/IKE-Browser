// what a realm tells about the computer: the same function in the page and in every kind of worker
async function realmValues() {
  var v = {};
  try { v.cores = navigator.hardwareConcurrency; } catch (e) {}
  try { v.mem = navigator.deviceMemory; } catch (e) {}
  try { v.ua = navigator.userAgent; } catch (e) {}
  try { v.langs = (navigator.languages || []).join(','); } catch (e) {}
  try { v.tz = Intl.DateTimeFormat().resolvedOptions().timeZone; v.locale = Intl.DateTimeFormat().resolvedOptions().locale; } catch (e) {}
  try {
    if (navigator.userAgentData) {
      var h = await navigator.userAgentData.getHighEntropyValues(['platformVersion', 'fullVersionList', 'architecture', 'bitness', 'model', 'uaFullVersion']);
      v.uaPlatformVersion = h.platformVersion; v.uaFull = (h.fullVersionList || []).map(function (b) { return b.brand + '/' + b.version; }).join(' ');
      v.arch = h.architecture;
    }
  } catch (e) { v.uadErr = String(e); }
  try {
    var oc = new OffscreenCanvas(64, 32), g = oc.getContext('webgl');
    if (g) {
      var d = g.getExtension('WEBGL_debug_renderer_info');
      v.glRenderer = d ? g.getParameter(d.UNMASKED_RENDERER_WEBGL) : g.getParameter(g.RENDERER);
      v.glVendor = d ? g.getParameter(d.UNMASKED_VENDOR_WEBGL) : g.getParameter(g.VENDOR);
      v.glExt = (g.getSupportedExtensions() || []).length;
    }
    var c2 = new OffscreenCanvas(120, 30), x = c2.getContext('2d');
    x.textBaseline = 'top'; x.font = '14px Arial'; x.fillStyle = '#f60'; x.fillRect(5, 1, 60, 20);
    x.fillStyle = '#069'; x.fillText('I.K.E. 😃 fp', 2, 10); x.strokeStyle = 'rgba(102,204,0,0.7)'; x.arc(60, 15, 10, 0, 6); x.stroke();
    var px = x.getImageData(0, 0, 120, 30).data, hsh = 0;
    for (var i = 0; i < px.length; i++) hsh = (hsh * 31 + px[i]) | 0;
    v.canvasHash = hsh;
  } catch (e) { v.ocErr = String(e).slice(0, 100); }
  return v;
}
