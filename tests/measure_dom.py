"""DOM work in a loaded page, at one protection level (1.1.18). Not part of
the automatic tests; to compare two versions on the same computer.

    python3 tests/measure_dom.py LISTS_DIR LEVEL [ROUNDS]
    IKE_TEST_APP=/path/to/other/copy python3 tests/measure_dom.py ...

The page adds 12,000 elements, removes them and sets innerHTML 300 times, seven
times; the median of the seven is one round. Prints the median of the rounds
(ms). LISTS_DIR as for measure_perf.py --lists.
"""
import shutil
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import measure_perf as M  # noqa: E402

lists_dir, level = sys.argv[1], sys.argv[2]
rounds = int(sys.argv[3]) if len(sys.argv) > 3 else 7
PAGE = b"""<!doctype html><title>dom</title><body><ul id=list></ul><script>
window.bench = function () {
  var t = [], list = document.getElementById('list');
  for (var r = 0; r < 7; r++) {
    var a = performance.now();
    for (var i = 0; i < 4000; i++) {
      var li = document.createElement('li'); var s = document.createElement('span');
      s.textContent = 'item ' + i; li.appendChild(s);
      var b = document.createElement('button'); b.className = 'destroy'; li.appendChild(b);
      list.appendChild(li);
    }
    for (var i = 0; i < 2000; i++) list.removeChild(list.firstChild);
    list.innerHTML = '';
    for (var i = 0; i < 300; i++) { var d = document.createElement('div'); d.innerHTML = '<p><b>x</b> <i>y</i></p>'; list.appendChild(d); }
    list.textContent = '';
    t.push(performance.now() - a);
  }
  t.sort(function (x, y) { return x - y; });
  return t[3];
};
</script></body>"""
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.send_header("Content-Type", "text/html"); self.send_header("Content-Length", str(len(PAGE)))
        self.end_headers(); self.wfile.write(PAGE)
    def log_message(self, *a): pass
srv = ThreadingHTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
base = "http://127.0.0.1:%d" % srv.server_address[1]
lists = M.fetch_lists(None, lists_dir)
STEPS = r'''
ROUNDS = %d
def steps(ike, qapp, out):
    from PyQt6.QtCore import QUrl
    view = ike.windows[0].current_view()
    yield 1500
    xs = []
    for r in range(ROUNDS):
        ms = yield from load(view, BASE + "/?%%d" %% r)
        yield 300
        res = {}
        view.page().runJavaScript("bench()", 0, lambda x: res.__setitem__("x", x))
        while "x" not in res:
            yield 20
        xs.append(round(res["x"], 1))
    out["ms"] = xs
'''
home = Path(tempfile.mkdtemp())
M.make_home(home, lists, {"shield_level": level})
M.run(M.START, home)
out = M.run(M.COMMON + "BASE = %r\n" % base + STEPS % rounds, home)
xs = sorted(out["ms"])
print(level, "median", xs[len(xs) // 2], out["ms"])
shutil.rmtree(home, ignore_errors=True)
