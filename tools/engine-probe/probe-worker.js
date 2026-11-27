// Engine probe inside a worker (dedicated, shared or service): the same
// collection as the page, sent back to whoever asks.
importScripts('/probe-core.js');
var KIND = (typeof SharedWorkerGlobalScope !== 'undefined' && self instanceof SharedWorkerGlobalScope) ? 'shared'
  : (typeof ServiceWorkerGlobalScope !== 'undefined' && self instanceof ServiceWorkerGlobalScope) ? 'service' : 'dedicated';
function reply(port) {
  PROBE.collect(KIND).then(function (r) { port.postMessage(r); }, function (e) { port.postMessage({ err: String(e && e.stack || e) }); });
}
if (KIND === 'dedicated') self.onmessage = function () { reply(self); };
if (KIND === 'shared') self.onconnect = function (e) { var p = e.ports[0]; p.onmessage = function () { reply(p); }; p.start(); };
if (KIND === 'service') {
  self.addEventListener('install', function () { self.skipWaiting(); });
  self.addEventListener('activate', function (e) { e.waitUntil(self.clients.claim()); });
  self.addEventListener('message', function (e) { reply(e.ports[0]); });
}
