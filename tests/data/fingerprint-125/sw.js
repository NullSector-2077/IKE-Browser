importScripts('/info.js');
self.addEventListener('install', function () { self.skipWaiting(); });
self.addEventListener('activate', function (e) { e.waitUntil(clients.claim()); });
self.addEventListener('message', function (e) { collect().then(function (o) { e.source.postMessage(o); }); });
