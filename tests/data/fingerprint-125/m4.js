import { tag } from './m4dep.js';
var o = { tag: tag, meta: import.meta.url, href: location.href, stack: String(new Error('x').stack).split('\n').slice(1, 3).join(' | '), name: self.name };
try { o.entries = performance.getEntriesByType('resource').map(function (e) { return e.name.slice(0, 60) + ':' + e.initiatorType; }); } catch (e) {}
onmessage = function (e) { o.got = e.data; postMessage(o); };
