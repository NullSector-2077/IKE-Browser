"""Dark Reader in frames (1.1.23): a frame that is not shown (display:none, or
a frame of a pixel or two, as trackers and advertisers use) does not start
Dark Reader until it gets a size; a frame that is shown is dark as before, and
a hidden frame shown later is dark too.

The benchmark is Speedometer's way of working: one frame after the other,
created, loaded and removed, on the same page. It measures how long a frame
takes to load with Dark Reader and without dark mode, in turns, and compares
the RATIOS (never an absolute time, which depends on the computer)."""

import statistics
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from test_security import JS

# a small light page with work for Dark Reader: 150 rules with colours
CSS = "".join(".t%d{color:#%02x%02x%02x;background:#%02x%02x%02x;border:1px solid #%02x%02x%02x}"
              % (i, i % 90, 40 + i % 50, i % 13 * 9, 250 - i % 7, 248 - i % 11, 240 - i % 5, i % 200, 90, 160)
              for i in range(150))
FRAME = ("<!doctype html><meta charset=utf-8><title>frame</title>"
         "<style>body{font:14px sans-serif;background:#fff;color:#222}li{padding:2px}" + CSS + "</style>"
         "<h1>todos</h1><ul>" + "".join("<li class=t%d>item %d</li>" % (i, i) for i in range(30)) + "</ul>")

TOP = r"""<!doctype html><meta charset=utf-8><title>top</title><body style="background:#fff">
<script>
var STYLES = {visible: 'width:800px;height:600px;border:0;position:absolute;left:0;top:0',
              hidden: 'display:none', tiny: 'width:1px;height:1px;border:0'};
function one(style, i) {
  return new Promise(function (ok) {
    var f = document.createElement('iframe'), t = performance.now();
    f.style.cssText = STYLES[style];
    f.onload = function () { var ms = performance.now() - t; f.remove(); setTimeout(function () { ok(ms); }, 0); };
    f.src = '/frame?' + style + i;
    document.body.appendChild(f);
  });
}
// Speedometer's way: one frame after the other, each loaded and then removed
async function bench(style, n) {
  var out = [];
  for (var i = 0; i < n; i++) out.push(await one(style, i));
  window.__bench = JSON.stringify(out);
}
function dark(f) {
  var d = f.contentDocument;
  return {dr: d.querySelectorAll('style.darkreader').length, body: getComputedStyle(d.body).backgroundColor};
}
// a frame shown, one hidden and one of a pixel; then the hidden ones are shown
function frames() {
  var made = {};
  return Promise.all(['visible', 'hidden', 'tiny'].map(function (style) {
    return new Promise(function (ok) {
      var f = document.createElement('iframe');
      f.style.cssText = STYLES[style];
      f.onload = function () { ok(); };
      f.src = '/frame?show-' + style;
      made[style] = f;
      document.body.appendChild(f);
    });
  })).then(function () {
    return new Promise(function (ok) { setTimeout(ok, 1500); });
  }).then(function () {
    var before = {visible: dark(made.visible), hidden: dark(made.hidden), tiny: dark(made.tiny)};
    made.hidden.style.cssText = 'display:block;width:400px;height:300px;border:0';
    made.tiny.style.cssText = 'width:400px;height:300px;border:0';
    return new Promise(function (ok) { setTimeout(ok, 1500); }).then(function () {
      window.__frames = JSON.stringify({before: before, after: {hidden: dark(made.hidden), tiny: dark(made.tiny)}});
    });
  });
}
</script>"""


@pytest.fixture
def site():
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            body = (FRAME if self.path.startswith("/frame") else TOP).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield "http://127.0.0.1:%d" % srv.server_address[1]
    srv.shutdown()


STEPS = JS + r'''
SITE = "__SITE__"
ROUNDS = 3
N = 16

def wait_for(view, name):
    for _ in range(1500):
        v = yield from js(view, "window.%s || ''" % name)
        if v:
            return json.loads(v)
        yield 20
    return None

def steps(ike, qapp, out):
    win = ike.windows[0]
    win.resize(1280, 900)
    view = win.current_view()
    yield 500
    ike.set_dark_mode("on", None, "reader")
    yield 300
    yield from load(view, SITE + "/top?frames")
    yield from js(view, "frames(); 1")
    out["frames"] = yield from wait_for(view, "__frames")
    out["bench"] = []
    for r in range(ROUNDS + 1):                     # round 0 only warms up
        for mode in (("on", "off") if r % 2 else ("off", "on")):
            ike.set_dark_mode(mode, None, "reader")
            yield 300
            for style in ("hidden", "visible"):
                yield from load(view, SITE + "/top?%s-%s-%d" % (mode, style, r))
                yield from js(view, "bench('%s', %d); 1" % (style, N))
                times = yield from wait_for(view, "__bench")
                out["bench"].append({"round": r, "mode": mode, "style": style, "ms": times})
'''


def test_hidden_frames_wait_and_shown_frames_are_dark(run_ike, site):
    out = run_ike(STEPS.replace("__SITE__", site), settings={"dark_mode": "on", "dark_engine": "reader"},
                  timeout=300)
    fr = out["frames"]
    assert fr, out
    before, after = fr["before"], fr["after"]
    # a frame that is shown is dark, as before
    assert before["visible"]["dr"] > 0 and before["visible"]["body"] == "rgb(24, 26, 27)", fr
    # a frame that is not shown has not started Dark Reader
    assert before["hidden"]["dr"] == 0 and before["tiny"]["dr"] == 0, fr
    # shown later, it is dark exactly as the frame shown from the start
    assert after["hidden"] == before["visible"] and after["tiny"] == before["visible"], fr

    rows = [b for b in out["bench"] if b["round"] > 0]
    assert all(b["ms"] and len(b["ms"]) == 16 for b in rows), rows

    def medians(style):
        per_round = {}
        for b in rows:
            if b["style"] == style:
                per_round.setdefault(b["round"], {})[b["mode"]] = statistics.median(b["ms"])
        return list(per_round.values())

    def ratio(style):
        return statistics.median(m["on"] / m["off"] for m in medians(style))

    def extra(style):                       # what Dark Reader adds to a frame, ms
        return statistics.median(m["on"] - m["off"] for m in medians(style))
    hidden, visible = ratio("hidden"), ratio("visible")
    line = ("Dark Reader in frames: load time with Dark Reader / without, hidden frames %.2f, shown frames %.2f; "
            "added per frame %.1f ms hidden, %.1f ms shown" % (hidden, visible, extra("hidden"), extra("visible")))
    print(line)
    # a hidden frame costs about what it costs without dark mode; before 1.1.23
    # Dark Reader's whole start was added to it, about as much as to a shown one
    assert extra("hidden") < 0.4 * extra("visible"), line
    assert hidden < 1.8, line
