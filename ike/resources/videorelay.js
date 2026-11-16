// I.K.E. embedded YouTube click relay (isolated world).
// A cross-origin YouTube iframe cannot access QWebChannel in the top page.
// This relay verifies both the message origin and the iframe contentWindow,
// then translates the click point into the top page's viewport coordinates.
(function () {
  'use strict';
  if (window.top !== window || window.__ikeVideoRelay) return;
  window.__ikeVideoRelay = true;
  var HOSTS = __IKE_VIDEO_HOSTS__;
  function allowed(host) {
    host = String(host || '').toLowerCase();
    return HOSTS.some(function (base) { return host === base || host.endsWith('.' + base); });
  }
  function send(x, y, tries) {
    var bridge = window.__ikeBridge;
    if (bridge && typeof bridge.adClickEmbedded === 'function') {
      bridge.adClickEmbedded(x, y);
      return;
    }
    if (tries > 0) setTimeout(function () { send(x, y, tries - 1); }, 100);
  }
  window.addEventListener('message', function (event) {
    var data = event.data;
    if (!data || data.type !== 'ike-video-ad-skip' || !event.source) return;
    var frames = document.querySelectorAll('iframe');
    var frame = null;
    for (var i = 0; i < frames.length; i++) {
      if (frames[i].contentWindow === event.source) { frame = frames[i]; break; }
    }
    if (!frame) return;
    var parsed;
    try { parsed = new URL(frame.src || frame.getAttribute('src') || '', document.baseURI); }
    catch (e) { return; }
    if (!allowed(parsed.hostname) || event.origin !== parsed.origin) return;
    var width = Number(data.viewportWidth), height = Number(data.viewportHeight);
    var x = Number(data.x), y = Number(data.y);
    if (!Number.isFinite(x) || !Number.isFinite(y) || width <= 0 || height <= 0) return;
    if (x < 0 || y < 0 || x > width || y > height) return;
    var rect = frame.getBoundingClientRect();
    if (rect.width < 4 || rect.height < 4) return;
    x = rect.left + (x / width) * rect.width;
    y = rect.top + (y / height) * rect.height;
    if (x < 0 || y < 0 || x >= window.innerWidth || y >= window.innerHeight) return;
    // Do not click through an unrelated overlay outside the iframe.
    if (document.elementFromPoint(x, y) !== frame) return;
    send(x, y, 5);
  }, false);
})();
