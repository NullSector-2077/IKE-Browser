// Runs in I.K.E.'s own world (ApplicationWorld): the page cannot see it.
// What a page shows and does; __CHECK__ is the site's own check (an
// expression evaluated in an async function: it may await).
(async function () {
  var r = {};
  try {
    r.href = location.href;
    r.title = document.title.slice(0, 120);
    r.ready = document.readyState;
    var b = document.body;
    r.text = b ? (b.innerText || '').length : -1;
    r.sample = b ? (b.innerText || '').replace(/\s+/g, ' ').slice(0, 220) : '';
    r.nodes = document.getElementsByTagName('*').length;
    r.iframes = document.getElementsByTagName('iframe').length;
    r.canvas = document.getElementsByTagName('canvas').length;
    r.imgs = Array.prototype.filter.call(document.images, function (i) { return i.complete && i.naturalWidth > 0; }).length;
    var cs = function (el) { try { return getComputedStyle(el).backgroundColor; } catch (e) { return null; } };
    r.bg = [cs(document.documentElement), b ? cs(b) : null];
    r.colorScheme = getComputedStyle(document.documentElement).colorScheme;
    r.ikeDark = !!document.querySelector('style.ike-dark, #ike-dark, [data-ike-dark]') ||
      document.documentElement.hasAttribute('data-ike-dark');
    r.media = Array.prototype.map.call(document.querySelectorAll('video,audio'), function (m) {
      return { tag: m.tagName, rs: m.readyState, t: Math.round(m.currentTime * 10) / 10, paused: m.paused,
               err: m.error ? m.error.code : 0, d: isFinite(m.duration) ? Math.round(m.duration) : String(m.duration),
               src: String(m.currentSrc || '').slice(0, 60) };
    }).slice(0, 4);
    try {
      r.swController = !!(navigator.serviceWorker && navigator.serviceWorker.controller);
      var regs = navigator.serviceWorker ? await navigator.serviceWorker.getRegistrations() : [];
      r.swRegs = regs.map(function (x) { return [x.scope, !!x.active, !!x.installing, !!x.waiting]; });
    } catch (e) { r.swErr = String(e).slice(0, 120); }
    try { r.resources = performance.getEntriesByType('resource').length; } catch (e) {}
  } catch (e) { r.err = String(e).slice(0, 200); }
  try { r.check = await (async function () { return __CHECK__; })(); } catch (e) { r.check = 'EXC ' + String(e).slice(0, 200); }
  window['__ikeProbe___TAG__'] = JSON.stringify(r);
  return true;
})();
