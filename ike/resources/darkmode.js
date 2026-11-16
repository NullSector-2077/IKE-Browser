// I.K.E. dark mode for pages: runs Dark Reader's own engine (resources/darkreader.js,
// MIT licence, https://darkreader.org) in the isolated world of every frame of a
// page that should be dark. The two IKE_DR placeholders below are replaced with
// the library and with {theme: {...}} when the script is installed.
(function () {
  'use strict';
  if (window.__iceDark) return;
  window.__iceDark = true;
  var CFG = __IKE_DR_CFG__;
  var DR;
  try {
    var module = { exports: {} }, exports = module.exports;
    (function () {
__IKE_DR_LIB__
    }).call(window);
    DR = module.exports;
  } catch (e) { return; }
  if (!DR || typeof DR.enable !== 'function') return;

  // Style sheets of other sites cannot be read by a page; the browser fetches
  // them instead (top frame only, style sheets only).
  var pending = {}, seq = 0, hooked = false;
  function bridgeReady() {
    // the bridge is set up a moment after the page starts loading
    return new Promise(function (resolve, reject) {
      var tries = 0;
      (function look() {
        var b = window.__iceBridge;
        if (b && typeof b.fetchCss === 'function' && b.cssFetched) { resolve(b); return; }
        if (window.top !== window || ++tries > 60) { reject(new Error('no bridge')); return; }
        setTimeout(look, 100);
      })();
    });
  }
  function viaBrowser(url) {
    return bridgeReady().then(function (bridge) {
      return new Promise(function (resolve, reject) {
        if (!hooked) {
          hooked = true;
          bridge.cssFetched.connect(function (id, ok, text) {
            var p = pending[id];
            if (!p) return;
            delete pending[id];
            if (ok) p[0](new Response(text, { status: 200, headers: { 'content-type': 'text/css' } }));
            else p[1](new Error('fetch failed'));
          });
        }
        var id = String(++seq);
        pending[id] = [resolve, reject];
        bridge.fetchCss(id, String(url));
        setTimeout(function () {
          if (pending[id]) { delete pending[id]; reject(new Error('timeout')); }
        }, 15000);
      });
    });
  }
  try {
    DR.setFetchMethod(function (url) {
      return window.fetch(url).then(function (r) {
        if (!r.ok) throw new Error('status');
        return r;
      }).catch(function () { return viaBrowser(url); });
    });
  } catch (e) {}

  // Until the engine is running, a plain dark background hides the white flash.
  var early = null;
  function cover() {
    if (early || !document.documentElement) return;
    early = document.createElement('style');
    early.textContent = 'html{background:#181a1b!important}';
    document.documentElement.appendChild(early);
  }
  function start() {
    try { DR.enable(CFG.theme); } catch (e) {}
    if (early) {
      var s = early;
      early = null;
      setTimeout(function () { try { s.remove(); } catch (e) {} }, 400);
    }
  }
  if (document.head) { start(); return; }
  cover();
  new MutationObserver(function (_m, obs) {
    cover();
    if (document.head) { obs.disconnect(); start(); }
  }).observe(document, { childList: true, subtree: true });
})();
