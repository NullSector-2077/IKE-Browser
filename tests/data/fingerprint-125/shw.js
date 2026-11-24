importScripts('/info.js');
onconnect = function (e) { var p = e.ports[0]; collect().then(function (o) { p.postMessage(o); }); };
