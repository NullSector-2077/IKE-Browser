importScripts('values.js');
self.addEventListener('install', function (e) { self.skipWaiting(); });
self.addEventListener('activate', function (e) { e.waitUntil(self.clients.claim()); });
self.addEventListener('message', function (e) { realmValues().then(function (v) { e.source.postMessage({ echo: e.data, sw: true, v: v }); }); });
self.addEventListener('fetch', function (e) { if (e.request.url.indexOf('/sw-ping') >= 0) e.respondWith(new Response('pong-from-sw')); });
