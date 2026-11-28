importScripts('values.js');
onmessage = async function (e) { postMessage({ echo: e.data, href: self.location.href, v: await realmValues() }); };
