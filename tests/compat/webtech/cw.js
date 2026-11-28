// The worker of conformance.html (1.1.32): answers what the page sends.
self.onmessage = function (e) {
  var d = e.data;
  if (d && d.kind === 'buf') { postMessage({ kind: 'buf', len: d.buf.byteLength }); return; }
  if (d && d.kind === 'port') { d.port.postMessage('via port ' + e.ports.length); return; }
  if (d && d.kind === 'canvas') {
    var g = d.canvas.getContext('2d'); g.fillRect(0, 0, 1, 1);
    postMessage({ kind: 'canvas', w: d.canvas.width }); return;
  }
  if (d && d.kind === 'boom') { throw new Error('boom'); }
  if (d && d.kind === 'nested') {
    var n = new Worker('cw.js');
    n.onmessage = function (m) { postMessage({ kind: 'nested', got: m.data }); };
    n.postMessage({ kind: 'echo', v: 'inner' }); return;
  }
  if (d && d.kind === 'echo') { postMessage(d.v); return; }
  postMessage(d);
};
