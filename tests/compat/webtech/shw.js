importScripts('values.js');
onconnect = function (e) { var p = e.ports[0]; p.onmessage = async function (m) { p.postMessage({ echo: m.data, href: self.location.href, v: await realmValues() }); }; };
