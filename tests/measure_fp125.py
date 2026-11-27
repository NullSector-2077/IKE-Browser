"""What the fingerprinting protection of 1.1.25 costs (owner's request, review
round 2). Not part of the automatic tests; compares two copies on the same
computer, start by start, alternated.

    python3 tests/measure_fp125.py LISTS_DIR BEFORE_DIR AFTER_DIR [STARTS] [LEVELS...]

LISTS_DIR as for measure_perf.py --lists; BEFORE_DIR and AFTER_DIR are two
copies of I.K.E. (a checkout each). Each start loads a local page that times,
in the page itself (performance.now), several rounds of:

  frames30        30 same-site frames put in and loaded (the protection is
                  installed in each): ms for all of them
  worker_blob     an inline worker started until its first message
  worker_file     a worker from a file of the site (classic) until its first message
  worker_module   the same as a module
  workers20       20 workers from a file at once, until all have answered
  rich_get / rich_url    getImageData / toDataURL of a 1000 x 1000 canvas with text
  flat_get / flat_url    the same of a canvas of solid rectangles only
  gl_param        10,000 getParameter(MAX_TEXTURE_SIZE)
  gl_read         20 readPixels of 256 x 256
  measure         10,000 measureText + width

Software WebGL (as the tests). Prints, per copy and level, the median of the
starts' medians and their spread (min-max), as JSON with --json FILE too.
"""

import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import measure_perf as M  # noqa: E402

WORKER = b"onmessage = function () { postMessage(1); }; postMessage(0);"
PAGE = b"""<!doctype html><title>fp</title><body><script>
function frames() {
  return new Promise(function (ok) {
    var t = performance.now(), n = 0, all = [];
    for (var i = 0; i < 30; i++) { var f = document.createElement('iframe'); f.src = '/frame?' + i;
      f.onload = function () { if (++n === 30) { ok(performance.now() - t); all.forEach(function (x) { x.remove(); }); } };
      all.push(f); document.body.appendChild(f); }
  });
}
function first(make) {
  return new Promise(function (ok) { var t = performance.now(), w = make();
    w.onmessage = function () { ok(performance.now() - t); w.terminate(); }; w.onerror = function () { ok(-1); }; });
}
function many() {
  return new Promise(function (ok) { var t = performance.now(), n = 0;
    for (var i = 0; i < 20; i++) { var w = new Worker('/w.js?' + i); w.onmessage = function (e) { this.terminate(); if (++n === 20) ok(performance.now() - t); }; w.onerror = function () { ok(-1); }; } });
}
function canvas(rich) {
  var c = document.createElement('canvas'); c.width = c.height = 1000; var x = c.getContext('2d');
  x.fillStyle = '#123456'; x.fillRect(0, 0, 1000, 1000); x.fillStyle = '#abcdef'; x.fillRect(100, 100, 300, 300);
  if (rich) { x.fillStyle = '#d02'; x.font = '40px sans-serif'; for (var i = 0; i < 20; i++) x.fillText('I.K.E. fingerprint ' + i, 10, 50 * i + 40); }
  var a = performance.now(); x.getImageData(0, 0, 1000, 1000); var g = performance.now() - a;
  a = performance.now(); c.toDataURL(); var u = performance.now() - a;
  return [g, u];
}
function gl() {
  var c = document.createElement('canvas'); c.width = c.height = 256; var g = c.getContext('webgl', { preserveDrawingBuffer: true });
  if (!g) return [-1, -1];
  var a = performance.now(); for (var i = 0; i < 10000; i++) g.getParameter(g.MAX_TEXTURE_SIZE); var p = performance.now() - a;
  g.clearColor(0.2, 0.4, 0.6, 1); g.clear(g.COLOR_BUFFER_BIT); var px = new Uint8Array(256 * 256 * 4);
  a = performance.now(); for (i = 0; i < 20; i++) g.readPixels(0, 0, 256, 256, g.RGBA, g.UNSIGNED_BYTE, px); return [p, performance.now() - a];
}
function measure() {
  var x = document.createElement('canvas').getContext('2d'); x.font = '16px sans-serif'; var s = 0, a = performance.now();
  for (var i = 0; i < 10000; i++) s += x.measureText('text ' + (i % 50)).width; return performance.now() - a;
}
window.bench = async function () {
  var R = {};
  function put(k, v) { (R[k] = R[k] || []).push(v); }
  for (var r = 0; r < 5; r++) {
    put('frames30', await frames());
    put('worker_blob', await first(function () { return new Worker(URL.createObjectURL(new Blob(['onmessage = function () {}; postMessage(0);'], {type: 'text/javascript'}))); }));
    put('worker_file', await first(function () { return new Worker('/w.js?c' + r); }));
    put('worker_module', await first(function () { return new Worker('/w.js?m' + r, { type: 'module' }); }));
    put('workers20', await many());
    var c = canvas(true); put('rich_get', c[0]); put('rich_url', c[1]);
    c = canvas(false); put('flat_get', c[0]); put('flat_url', c[1]);
    var g = gl(); put('gl_param', g[0]); put('gl_read', g[1]);
    put('measure', measure());
  }
  var out = {};
  Object.keys(R).forEach(function (k) { var v = R[k].slice().sort(function (a, b) { return a - b; }); out[k] = v[2]; });
  return JSON.stringify(out);
};
</script></body>"""


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?")[0]
        body, kind = (WORKER, "text/javascript") if path == "/w.js" else (
            (b"<!doctype html><p>frame", "text/html") if path == "/frame" else (PAGE, "text/html"))
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


STEPS = r'''
def steps(ike, qapp, out):
    view = ike.windows[0].current_view()
    yield 1500
    ms = yield from load(view, BASE + "/page")
    yield 500
    res = {}
    view.page().runJavaScript("window.__r = null; bench().then(function (x) { window.__r = x; }); 1", 0, lambda x: None)
    while True:
        view.page().runJavaScript("window.__r", 0, lambda x, res=res: res.__setitem__("x", x))
        while "x" not in res:
            yield 20
        if res["x"]:
            break
        res.clear()
        yield 200
    out["r"] = res["x"]
'''


def run(app, script, home, flags):
    work = Path(tempfile.mkdtemp(prefix="ike-fp125-"))
    (work / "steps.py").write_text(textwrap.dedent(script))
    out = work / "out.json"
    env = {k: v for k, v in os.environ.items() if not k.startswith(("XDG_", "IKE_", "LANG", "LC_"))}
    env.update({"HOME": str(home), "XDG_CONFIG_HOME": str(home / ".config"),
                "XDG_DATA_HOME": str(home / ".local/share"), "XDG_CACHE_HOME": str(home / ".cache"),
                "XDG_RUNTIME_DIR": str(work), "QT_QPA_PLATFORM": "offscreen", "LANG": "C.UTF-8",
                "QTWEBENGINE_CHROMIUM_FLAGS": flags, "IKE_ALLOW_UNSAFE_ENGINE": "1", "IKE_NO_SINGLE": "1",
                "IKE_TEST_NOASK": "1", "IKE_TEST_HOOK": str(M.ROOT / "tests" / "harness.py"),
                "IKE_TEST_SCRIPT": str(work / "steps.py"), "IKE_TEST_OUT": str(out), "DBUS_SESSION_BUS_ADDRESS": "",
                "PYTHONUTF8": "1", "IKE_T0": repr(time.time())})
    os.chmod(work, 0o700)
    p = subprocess.run([sys.executable, str(Path(app) / "ike_boot.py")], env=env, capture_output=True, text=True,
                       timeout=900)
    if not out.exists():
        raise SystemExit("no results (exit %s)\n%s" % (p.returncode, p.stderr[-2000:]))
    res = json.loads(out.read_text())
    shutil.rmtree(work, ignore_errors=True)
    return res


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dump = sys.argv[sys.argv.index("--json") + 1] if "--json" in sys.argv else None
    if dump in args:
        args.remove(dump)
    lists_dir, before, after = args[0], args[1], args[2]
    starts = int(args[3]) if len(args) > 3 else 5
    levels = args[4:] or ["balanced", "strict", "maximum"]
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:%d" % srv.server_address[1]
    lists = M.fetch_lists(None, lists_dir)
    flags = "--no-sandbox --enable-unsafe-swiftshader --use-angle=swiftshader --ignore-gpu-blocklist"
    script = M.COMMON + "BASE = %r\n" % base + STEPS
    got = {}
    for s in range(starts):
        for level in levels:
            for name, app in (("before", before), ("after", after)):
                home = Path(tempfile.mkdtemp(prefix="ike-fp125-home-"))
                M.make_home(home, lists, {"shield_level": level})
                M.APP = Path(app)
                run(app, M.START, home, flags)               # the engine's cache made once
                r = json.loads(run(app, script, home, flags)["r"])
                shutil.rmtree(home, ignore_errors=True)
                for k, v in r.items():
                    got.setdefault(level, {}).setdefault(k, {}).setdefault(name, []).append(round(v, 2))
                print(s, level, name, json.dumps(r), flush=True)
    table = {}
    for level, keys in got.items():
        for k, by in keys.items():
            for name, xs in by.items():
                table.setdefault(level, {}).setdefault(k, {})[name] = [statistics.median(xs), min(xs), max(xs)]
    print(json.dumps(table, indent=1))
    if dump:
        Path(dump).write_text(json.dumps({"runs": got, "table": table}, indent=1))


if __name__ == "__main__":
    main()
