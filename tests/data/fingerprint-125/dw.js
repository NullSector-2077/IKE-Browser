importScripts('/info.js');
onmessage = function (e) {
  if (e.data === 'nested') {
    var src = "importScripts('" + location.origin + "/info.js'); collect().then(function(o){ postMessage(o); });";
    var w = new Worker(URL.createObjectURL(new Blob([src], {type: 'text/javascript'})));
    w.onmessage = function (m) { postMessage(m.data); }; w.onerror = function (er) { postMessage('ERR nested ' + er.message); };
  } else collect().then(function (o) { postMessage(o); });
};
