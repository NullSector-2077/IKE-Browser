"use strict";
var o = {};
try { undeclared_xyz = 1; o.strict = 'SLOPPY (no ReferenceError)'; } catch (e) { o.strict = 'strict ok'; }
o.href = location.href; o.locStr = String(location); o.origin = self.origin; o.name = self.name;
o.stack = String(new Error('x').stack).split('\n').slice(1, 4).join(' | ');
o.ctor = Object.prototype.toString.call(self); o.isSecure = self.isSecureContext; o.coi = self.crossOriginIsolated; o.sab = typeof SharedArrayBuffer;
try { o.entries = performance.getEntriesByType('resource').map(function (e) { return e.name.slice(0, 60) + ':' + e.initiatorType; }); } catch (e) {}
try { importScripts('rel.js'); o.rel = self.__rel; } catch (e) { o.rel = 'ERR ' + e.message; }
try { o.importFn = Function.prototype.toString.call(importScripts) + '/' + importScripts.length + '/' + Function.prototype.toString.call(fetch); } catch (e) {}
try { importScripts('nope-404.js'); } catch (e) { o.import404 = e.name + ': ' + e.message + ' || ' + String(e.stack).split('\n').slice(1, 3).join(' | '); }
try { o.urlRel = new URL('x.js', location).href; o.reqUrl = new Request('rel.js').url; } catch (e) { o.urlRel = 'ERR ' + e; }
o.globals = Object.getOwnPropertyNames(self).filter(function (k) { return !/^(on|[A-Z])/.test(k); }).sort().join(',').slice(0, 900);
var early = [];
onmessage = function (e) {
  fetch('rel.js').then(function (r) { o.fetchRel = r.status + ' ' + r.url; }, function (e2) { o.fetchRel = 'ERR ' + e2; }).then(function () {
    var x = new XMLHttpRequest(); try { x.open('GET', 'rel.js', false); x.send(); o.xhrRel = x.status + ' ' + x.responseURL; } catch (e3) { o.xhrRel = 'ERR ' + e3; }
    try { var w = new Worker('rel-worker.js'); w.onmessage = function (m) { o.nested = m.data; postMessage(o); }; w.onerror = function (er) { o.nested = 'ERR ' + er.message + ' @' + er.filename; postMessage(o); }; } catch (e4) { o.nested = 'THROW ' + e4; postMessage(o); }
  });
};
