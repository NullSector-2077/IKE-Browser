"""How smoothly pages appear and scroll (1.1.19, the owner's request): the same
local test pages in I.K.E. and, by hand, in any other browser (Brave), so the
numbers compare. Not part of the automatic tests.

    python3 tests/measure_smooth.py [--runs N] [--json FILE]       I.K.E.: Dark Reader off / on / engine dark
    python3 tests/measure_smooth.py --serve                       only the pages: open the address it prints
                                                                  in Brave (or I.K.E. by hand), wait for "done"
    IKE_TEST_APP=/usr/lib/ike-browser python3 tests/measure_smooth.py      an installed copy

Needs Pillow (python-pillow) to make the pictures. Nothing comes from the
internet. Each page measures itself with the browser's own counters
(PerformanceObserver), the same in every Chromium browser, then scrolls down
on its own for five seconds, one step per frame, and sends its numbers to
this script; the next page follows by itself.

The pages:
  images       120 pictures of several sizes, with their sizes given
  big          six 6000x4000 photos (progressive JPEG)
  long         a long article; pictures that load when near (loading=lazy),
               half of them without a size (the page moves when they come)
  dynamic      a feed that adds 20 cards with pictures every 300 ms while it scrolls
  heavy        2000 style rules, 200 components with their own shadow root, an SVG chart
               of 2000 shapes
  progressive  the page and its pictures arrive slowly, in pieces

For each page (median of the runs):
  load_ms       navigation to the load event
  fcp_ms / lcp_ms   first and largest content painted
  cls           how much the page moved while loading (layout shift)
  long_n / long_ms / long_max   tasks of the page's main thread over 50 ms: count, time over
                50 ms in all (blocking time), the longest
  fps / ft_p95 / dropped        while scrolling: frames per second, the 95th percentile of the
                time between frames, frames that took more than 1.5 frames
  img_ms        the last picture decoded and shown, from the start (where measurable)
and for I.K.E. only (whole run): ui_stall_ms (the window did not answer), cpu_s, pss_mb.

The scrolling is driven from the page (window.scrollBy in each frame): it
shows what the page's main thread does to the frames (Dark Reader's work is
there). A wheel scroll by hand is mostly done by the compositor, off the main
thread, and is smoother than this. In a container without a graphics card
the frames are drawn in software: compare runs on the same computer only.
"""

import argparse
import io
import json
import os
import random
import statistics
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

PAGES = ("images", "big", "long", "dynamic", "heavy", "progressive")
SCROLL_S = 5

PROBE = r"""<script>
(function () {
  var page = %(page)r, next = %(next)r, run = %(run)r;
  var t0 = performance.now(), res = {page: page, run: run, ua: navigator.userAgent};
  var cls = 0, longs = [], lcp = 0, fcp = 0, lastImg = 0;
  function obs(type, cb) { try { new PerformanceObserver(function (l) { l.getEntries().forEach(cb); })
    .observe({type: type, buffered: true}); } catch (e) {} }
  obs("layout-shift", function (e) { if (!e.hadRecentInput) cls += e.value; });
  obs("longtask", function (e) { longs.push(e.duration); });
  obs("largest-contentful-paint", function (e) { lcp = e.startTime; });
  obs("paint", function (e) { if (e.name === "first-contentful-paint") fcp = e.startTime; });
  function imgs() { var all = document.images, n = 0;
    for (var i = 0; i < all.length; i++) if (all[i].complete && all[i].naturalWidth) n++;
    return n; }
  function scroll(done) {
    var times = [], start = performance.now(), prev = start;
    function step(now) {
      times.push(now - prev); prev = now;
      window.scrollBy(0, 12);
      if (now - start < %(scroll)d) requestAnimationFrame(step); else done(times.slice(1));
    }
    requestAnimationFrame(step);
  }
  addEventListener("load", function () {
    res.load_ms = performance.now();
    var waited = 0;
    (function settle() {        // pictures already asked for, decoded
      var ims = Array.prototype.filter.call(document.images, function (i) { return i.loading !== "lazy"; });
      var left = ims.filter(function (i) { return !(i.complete && i.naturalWidth); }).length;
      if (left && waited < 8000) { waited += 100; return setTimeout(settle, 100); }
      Promise.all(ims.slice(0, 200).map(function (i) { return i.decode ? i.decode().catch(function () {}) : 0; }))
        .then(function () {
          res.img_ms = performance.now();
          var longsBefore = longs.length;
          scroll(function (ft) {
            ft.sort(function (a, b) { return a - b; });
            var sum = ft.reduce(function (a, b) { return a + b; }, 0);
            var frame = ft[Math.floor(ft.length / 2)] || 16.7;
            res.fps = ft.length / (sum / 1000);
            res.ft_p95 = ft[Math.floor(ft.length * 0.95)] || 0;
            res.dropped = ft.filter(function (x) { return x > frame * 1.5; }).length;
            res.frames = ft.length;
            res.scroll_long_n = longs.length - longsBefore;
            res.cls = cls; res.lcp_ms = lcp; res.fcp_ms = fcp;
            res.long_n = longs.length;
            res.long_ms = longs.reduce(function (a, b) { return a + Math.max(0, b - 50); }, 0);
            res.long_max = longs.reduce(function (a, b) { return Math.max(a, b); }, 0);
            res.shown = imgs();
            fetch("/report", {method: "POST", body: JSON.stringify(res)}).then(function () {
              location.href = next;
            });
          });
        });
    })();
  });
})();
</script>"""


def pictures():
    from PIL import Image, ImageDraw, ImageFilter
    rnd = random.Random(7)

    def photo(w, h, progressive=False, q=82):
        im = Image.new("RGB", (w // 8, h // 8))
        d = ImageDraw.Draw(im)
        for _ in range(60):
            x, y = rnd.randrange(w // 8), rnd.randrange(h // 8)
            d.ellipse((x, y, x + rnd.randrange(5, w // 16 + 6), y + rnd.randrange(5, h // 16 + 6)),
                      fill=(rnd.randrange(256), rnd.randrange(256), rnd.randrange(256)))
        im = im.filter(ImageFilter.GaussianBlur(3)).resize((w, h), Image.BICUBIC)
        noise = Image.effect_noise((w, h), 24).convert("RGB")
        im = Image.blend(im, noise, 0.15)
        b = io.BytesIO()
        im.save(b, "JPEG", quality=q, progressive=progressive)
        return b.getvalue()
    sizes = [(320, 200), (640, 400), (1280, 800), (1920, 1080)]
    small = {"%dx%d" % s: photo(*s) for s in sizes}
    big = photo(6000, 4000, progressive=True)
    return small, big


def page_html(name, run, nxt):
    rnd = random.Random(name)
    probe = PROBE % {"page": name, "next": nxt, "run": run, "scroll": SCROLL_S * 1000}
    head = "<!doctype html><meta charset=utf-8><title>%s</title>%s<style>body{font:16px sans-serif;margin:20px;" \
           "background:#fafafa;color:#222}img{max-width:100%%;height:auto;display:block;margin:8px 0}" \
           ".card{border:1px solid #ccc;border-radius:8px;padding:10px;margin:10px 0;background:#fff;" \
           "box-shadow:0 1px 3px rgba(0,0,0,.2)}</style>" % (name, probe)
    para = ("<p>" + "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor. " * 6 + "</p>")
    sizes = ["320x200", "640x400", "1280x800", "1920x1080"]
    if name == "images":
        body = "".join("<img src='/img/%s?n=%d' width=%s height=%s>" % (s, i, s.split("x")[0], s.split("x")[1])
                       for i, s in ((i, sizes[i % 4]) for i in range(120)))
    elif name == "big":
        body = "".join("<p>photo %d</p><img src='/big?n=%d' width=6000 height=4000>" % (i, i) for i in range(6))
    elif name == "long":
        body = ""
        for i in range(300):
            body += "<h3>Section %d</h3>" % i + para
            if i % 10 == 5:
                s = sizes[i % 4]
                size = (" width=%s height=%s" % tuple(s.split("x"))) if i % 20 == 5 else ""
                body += "<img loading=lazy src='/img/%s?l=%d'%s>" % (s, i, size)
    elif name == "dynamic":
        body = ("<div id=feed></div><script>var n=0,feed=document.getElementById('feed');"
                "function more(){for(var i=0;i<20;i++,n++){var c=document.createElement('div');c.className='card';"
                "c.innerHTML='<b>Post '+n+'</b><p>'+'text of the post, '.repeat(20)+'</p>"
                "<img src=\"/img/640x400?d='+n+'\" width=640 height=400>';feed.appendChild(c);}}"
                "more();more();setInterval(more,300);</script>")
    elif name == "heavy":
        css = "".join(".c%d{color:#%06x;padding:%dpx;border-left:%dpx solid #%06x}" %
                      (i, rnd.randrange(1 << 24), i % 9, i % 4, rnd.randrange(1 << 24)) for i in range(2000))
        comps = ("<script>customElements.define('x-item',class extends HTMLElement{constructor(){super();"
                 "var r=this.attachShadow({mode:'open'});r.innerHTML='<style>:host{display:block;background:#eef;"
                 "color:#123;margin:4px;padding:6px;border:1px solid #99a}b{color:#a00}</style><b>item</b> "
                 "<slot></slot>';}});</script>")
        items = "".join("<x-item class='c%d'>component %d</x-item>" % (i * 7 % 2000, i) for i in range(200))
        svg = "<svg width=1200 height=600>" + "".join(
            "<rect x=%d y=%d width=6 height=%d fill='#%06x'/>" % (i % 200 * 6, 600 - (i * 37 % 500), i * 37 % 500,
                                                                  rnd.randrange(1 << 24)) for i in range(2000)) + "</svg>"
        body = "<style>%s</style>%s%s%s" % (css, comps, svg, items) + para * 40
    else:                                   # progressive: chunks from the server (see Handler)
        body = ""
    return head, body


class Results:
    def __init__(self):
        self.reports = []
        self.lock = threading.Lock()


def serve(port, small, big, results, runs=1):
    order = [(r, p) for r in range(runs) for p in PAGES]

    def next_of(run, name):
        i = order.index((run, name)) + 1
        return "/p/%s?run=%d" % (order[i][1], order[i][0]) if i < len(order) else "/done"

    class H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _send(self, body, ctype, slow=0):
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            if slow:
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()
                step = max(1, len(body) // slow)
                for i in range(0, len(body), step):
                    part = body[i:i + step]
                    self.wfile.write(b"%x\r\n%s\r\n" % (len(part), part))
                    self.wfile.flush()
                    time.sleep(0.06)
                self.wfile.write(b"0\r\n\r\n")
                return
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            data = self.rfile.read(n)
            if self.path == "/report":
                with results.lock:
                    results.reports.append(json.loads(data))
            self._send(b"ok", "text/plain")

        def do_GET(self):
            path, _, query = self.path.partition("?")
            run = int(dict(x.split("=", 1) for x in query.split("&") if "=" in x).get("run", 0))
            if path in ("/", "/start"):
                return self._send(("<!doctype html><title>start</title><script>setTimeout(function(){"
                                   "location.href='/p/%s?run=0'},500)</script>" % PAGES[0]).encode(), "text/html")
            if path == "/done":
                with results.lock:
                    rows = list(results.reports)
                text = "<!doctype html><title>done</title><pre>%s</pre>" % json.dumps(summary(rows), indent=1)
                return self._send(text.encode(), "text/html")
            if path.startswith("/img/"):
                data = small.get(path[5:], small["320x200"])
                return self._send(data, "image/jpeg", slow=8 if "p=" in query else 0)
            if path == "/big":
                return self._send(big, "image/jpeg")
            if path.startswith("/p/"):
                name = path[3:]
                head, body = page_html(name, run, next_of(run, name))
                if name == "progressive":
                    body = "".join("<h3>Part %d</h3><p>%s</p><img src='/img/1280x800?p=%d' width=1280 height=800>"
                                   % (i, "Some text arriving slowly. " * 30, i) for i in range(30))
                    return self._send((head + body).encode(), "text/html", slow=40)
                return self._send((head + body).encode(), "text/html")
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *a):
            pass

        def handle(self):
            try:
                super().handle()
            except (BrokenPipeError, ConnectionResetError):
                pass
    srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


KEYS = ("load_ms", "fcp_ms", "lcp_ms", "img_ms", "cls", "long_n", "long_ms", "long_max", "scroll_long_n",
        "fps", "ft_p95", "dropped")


def summary(rows):
    out = {}
    for name in PAGES:
        mine = [r for r in rows if r.get("page") == name]
        if mine:
            out[name] = {k: round(statistics.median(r.get(k) or 0 for r in mine), 3 if k == "cls" else 1)
                         for k in KEYS}
    return out


STEPS = r'''
import os, time
TICK = os.sysconf("SC_CLK_TCK")
def tree(pid):
    out = [pid]
    try:
        for c in open("/proc/%%d/task/%%d/children" %% (pid, pid)).read().split():
            out += tree(int(c))
    except OSError:
        pass
    return out
def cpu(pids):
    t = 0
    for p in pids:
        try:
            f = open("/proc/%%d/stat" %% p).read(); f = f[f.rindex(")") + 2:].split(); t += int(f[11]) + int(f[12])
        except OSError:
            pass
    return t / TICK
def pss(pids):
    t = 0
    for p in pids:
        try:
            for line in open("/proc/%%d/smaps_rollup" %% p):
                if line.startswith("Pss:"):
                    t += int(line.split()[1])
        except OSError:
            pass
    return t // 1024

def steps(ike, qapp, out):
    from PyQt6.QtCore import QTimer, QUrl
    win = ike.windows[0]
    win.resize(1280, 900)
    v = win.current_view()
    yield 1500
    st = {"last": time.perf_counter(), "worst": 0.0, "sum": 0.0}
    def tick():
        now = time.perf_counter(); gap = now - st["last"] - 0.005
        st["worst"] = max(st["worst"], gap); st["sum"] += max(0.0, gap - 0.05); st["last"] = now
    t = QTimer(); t.setInterval(5); t.timeout.connect(tick); t.start()
    c0 = cpu(tree(os.getpid()))
    v.load(QUrl("http://127.0.0.1:%d/start"))
    end = time.time() + %d
    while time.time() < end and v.title() != "done":
        yield 250
    out["finished"] = v.title() == "done"
    out["ui_stall_ms"] = round(st["worst"] * 1000, 1)
    out["ui_stall_sum_ms"] = round(st["sum"] * 1000, 1)
    out["cpu_s"] = round(cpu(tree(os.getpid())) - c0, 2)
    out["pss_mb"] = pss(tree(os.getpid()))
'''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--json")
    ap.add_argument("--serve", action="store_true", help="only serve the pages (for another browser)")
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--modes", default="off,reader,engine")
    a = ap.parse_args()
    try:
        small, big = pictures()
    except ImportError:
        raise SystemExit("Pillow is needed to make the pictures: sudo pacman -S python-pillow")
    if a.serve:
        results = Results()
        srv = serve(a.port or 8765, small, big, results, runs=a.runs)
        print("Open http://127.0.0.1:%d/start and wait for the page \"done\" (Ctrl+C here to stop)."
              % srv.server_address[1])
        try:
            while True:
                time.sleep(2)
                if results.reports and len(results.reports) == a.runs * len(PAGES):
                    print(json.dumps(summary(results.reports), indent=1))
                    results.reports.append({})
        except KeyboardInterrupt:
            return
    import tempfile

    from measure_perf import fetch_lists, make_home, run
    lists = fetch_lists(None, None)
    table = {}
    for mode in a.modes.split(","):
        settings = {"dark_mode": "off"} if mode == "off" else {"dark_mode": "on", "dark_engine": mode}
        rows, whole = [], []
        for r in range(a.runs):
            results = Results()
            srv = serve(0, small, big, results, runs=1)
            home = Path(tempfile.mkdtemp(prefix="ike-smooth-"))
            make_home(home, lists, settings)
            out = run(STEPS % (srv.server_address[1], 240), home, timeout=400)
            srv.shutdown()
            rows += results.reports
            whole.append(out)
            print(mode, "run", r + 1, "pages", len(results.reports), "finished", out.get("finished"), flush=True)
        table[mode] = summary(rows)
        table[mode]["_browser"] = {k: statistics.median(o[k] for o in whole)
                                   for k in ("ui_stall_ms", "ui_stall_sum_ms", "cpu_s", "pss_mb")}
    print(json.dumps(table, indent=1))
    if a.json:
        Path(a.json).write_text(json.dumps(table, indent=1))


if __name__ == "__main__":
    main()
