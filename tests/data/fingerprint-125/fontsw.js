// which fonts a script finds by measuring text (1.1.25 test, review round 3):
// the same function in a page, a frame and every kind of worker
var FONTS = ['Arial', 'Times New Roman', 'Helvetica', 'Courier New', 'DejaVu Sans', 'DejaVu Serif', 'DejaVu Sans Mono',
  'Liberation Sans', 'Liberation Serif', 'Liberation Mono', 'Noto Sans', 'Cantarell', 'Ubuntu', 'Fira Code',
  'Bitstream Vera Sans', 'Droid Sans', 'Comic Sans MS', 'Impact', 'NoSuchFont123'];
function found(x) {
  var s = 'mmmmmmmmmmlli', bases = ['monospace', 'serif'], base = {}, generic = {};
  ['monospace', 'serif', 'sans-serif', 'cursive', 'fantasy'].forEach(function (b) { x.font = '72px ' + b; generic[b] = base[b] = x.measureText(s).width; });
  return { generic: generic, fonts: FONTS.filter(function (f) {
    return bases.some(function (b) { x.font = "72px '" + f + "', " + b; return x.measureText(s).width !== base[b]; });
  }) };
}
if (typeof WorkerGlobalScope !== 'undefined') {
  onmessage = function (e) {
    if (e.data === 'nested') {
      var k = new Worker('fontsw.js');
      k.onmessage = function (m) { postMessage(m.data); };
      k.postMessage('go');
      return;
    }
    postMessage(found(new OffscreenCanvas(300, 60).getContext('2d')));
  };
}
