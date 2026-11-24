// a worker from a file that uses addresses relative to its own (1.1.25 test)
importScripts('info.js');
onmessage = async function () {
  var o = {};
  try { o.loc = [location.href, location.pathname, String(location)]; } catch (e) { o.loc = 'ERR ' + e; }
  try { o.fetch = await (await fetch('data.txt')).text(); } catch (e) { o.fetch = 'ERR ' + e; }
  try { o.request = await (await fetch(new Request('data.txt'))).text(); } catch (e) { o.request = 'ERR ' + e; }
  try { var x = new XMLHttpRequest(); x.open('GET', 'data.txt', false); x.send(); o.xhr = x.responseText; } catch (e) { o.xhr = 'ERR ' + e; }
  try {
    o.nested = await new Promise(function (ok) {
      var w = new Worker('dw.js'); w.onmessage = function (e) { ok(e.data); }; w.onerror = function (e) { ok('ERR ' + e.message); };
      w.postMessage('go'); setTimeout(function () { ok('timeout'); }, 8000);
    });
  } catch (e) { o.nested = 'ERR ' + e; }
  o.info = await collect();
  postMessage(o);
};
