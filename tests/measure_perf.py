"""Repeatable performance measurements of I.K.E. (1.1.17, 1.1.18), to compare two
versions on the same computer. Not part of the automatic tests.

    python tests/measure_perf.py [--runs N] [--lists DIR] [--json FILE]
    IKE_TEST_APP=/usr/lib/ike-browser python3 tests/measure_perf.py      an installed copy

Everything runs against local pages made by this script (never a real site),
with the browser's default filter lists: downloaded from their maintainers at
the start (they are not part of the repository), or read from --lists DIR,
where each file is named as the last part of its address (easylist.txt,
filters.txt, ...). The AdBlock engine must be built (docs/BUILDING.md).

What is measured (median of the runs; times in ms unless said otherwise):

  start_warm_s / start_cold_s   start to the first window, engine from its cache / to rebuild
  rebuild_ms, rebuild_stall_ms  an engine rebuilt after a list update: total, and the
                                longest time the interface did not answer meanwhile
  heavy_load_ms                 a page with 400 requests, 150 of them to ad servers
  heavy_intercept_ms            time spent checking its requests (shield included)
  heavy_shield_redraws          how often the shield was redrawn for it
  heavy_main_cpu_ms             processor time of the interface's thread for it (load and the
                                1.2 s after it: requests, drawing, the engine's own work there)
  frames_<level>_ms             a page with 30 frames at each protection level
  idle_cpu_pct_<n>tabs          processor use at rest, all processes, share of one core
  pss_mb_<n>tabs                memory of all processes (PSS)
  session_mb                    main process memory after every 80 pages opened and closed
  ui_switch_tab_ms, ui_new_tab_ms, ui_refresh_ms   interface operations
"""

import argparse
import hashlib
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
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = Path(os.environ.get("IKE_TEST_APP") or ROOT)
sys.path.insert(0, str(APP))
from ike.config import DEFAULT_LISTS  # noqa: E402

ADS = ["https://securepubads.g.doubleclick.net/tag/js/gpt.js?n=%d", "https://www.googletagmanager.com/gtm.js?id=GTM-%d",
       "https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?x=%d", "https://www.google-analytics.com/collect?v=%d",
       "https://connect.facebook.net/en_US/fbevents.js?%d", "https://static.criteo.net/js/ld/publishertag.%d.js",
       "https://c.amazon-adsystem.com/aax2/apstag.js?%d", "https://sb.scorecardresearch.com/beacon.js?%d"]
PNG = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                    "1f15c4890000000d49444154789c6360000002000100e221bc330000000049454e44ae426082")


def heavy_page():
    parts = ["<!doctype html><title>heavy</title><style>img{width:20px;height:20px}</style>"]
    parts += ['<script src="/js/%d.js"></script>' % i for i in range(50)]
    for i in range(150):
        u = ADS[i % len(ADS)] % i
        parts.append('<script async src="%s"></script>' % u if i % 2 else '<img src="%s">' % u)
    parts += ['<img src="/img/%d.png">' % i for i in range(200)]
    parts += ['<div class="ad-slot banner-%d sponsored"><p>Article text %d</p></div>' % (i, i) for i in range(300)]
    return "".join(parts).encode()


def serve():
    heavy = heavy_page()
    frames = ("<!doctype html><title>frames</title>"
              + "".join('<iframe src="/frame%d"></iframe>' % i for i in range(30))).encode()

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.startswith("/img/"):
                b, t = PNG, "image/png"
            elif self.path.startswith("/js/"):
                b, t = b"window.x=(window.x||0)+1;", "application/javascript"
            elif self.path.startswith("/frames"):
                b, t = frames, "text/html"
            elif self.path.startswith("/frame"):
                b, t = b"<!doctype html><p>frame</p>", "text/html"
            else:
                b, t = heavy, "text/html"
            self.send_response(200)
            self.send_header("Content-Type", t)
            self.send_header("Content-Length", str(len(b)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(b)

        def log_message(self, *a):
            pass

        def handle(self):
            try:
                super().handle()
            except (BrokenPipeError, ConnectionResetError):
                pass
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def fetch_lists(folder, given):
    """The text of each default list (enabled ones), by address."""
    out = {}
    for e in DEFAULT_LISTS:
        if not e.get("enabled", True):
            continue
        name = e["url"].rsplit("/", 1)[-1]
        if given and (Path(given) / name).exists():
            out[e["url"]] = (Path(given) / name).read_bytes()
            continue
        try:
            req = urllib.request.Request(e["url"], headers={"User-Agent": "I.K.E. measurements"})
            with urllib.request.urlopen(req, timeout=60) as r:
                out[e["url"]] = r.read()
        except Exception as exc:
            print("  list not available, measured without it: %s (%s)" % (e["name"], exc))
    return out


def make_home(home, lists, settings=None):
    cfg = home / ".config" / "ike-browser"
    data = home / ".local/share" / "ike-browser" / "lists"
    cfg.mkdir(parents=True, exist_ok=True)
    data.mkdir(parents=True, exist_ok=True)
    s = {"lists_version": 4, "last_lists_update": 4102444800, "last_fast_update": 4102444800,
         "chrome_checked": 4102444800, "app_updates": "off", "auto_update": False, "https_only": False,
         "tab_sleep_minutes": 0}
    s.update(settings or {})
    (cfg / "settings.json").write_text(json.dumps(s))
    for url, body in lists.items():
        (data / (hashlib.sha1(url.encode()).hexdigest()[:16] + ".txt")).write_bytes(body)


def run(script, home, timeout=600):
    work = Path(tempfile.mkdtemp(prefix="ike-perf-"))
    sf = work / "steps.py"
    sf.write_text(textwrap.dedent(script))
    out = work / "out.json"
    env = {k: v for k, v in os.environ.items() if not k.startswith(("XDG_", "IKE_", "LANG", "LC_"))}
    env.update({"HOME": str(home), "XDG_CONFIG_HOME": str(home / ".config"),
                "XDG_DATA_HOME": str(home / ".local/share"), "XDG_CACHE_HOME": str(home / ".cache"),
                "XDG_RUNTIME_DIR": str(work), "QT_QPA_PLATFORM": "offscreen", "LANG": "C.UTF-8",
                "QTWEBENGINE_CHROMIUM_FLAGS": "--no-sandbox", "IKE_NO_SINGLE": "1", "IKE_TEST_NOASK": "1",
                "IKE_TEST_HOOK": str(ROOT / "tests" / "harness.py"), "IKE_TEST_SCRIPT": str(sf),
                "IKE_TEST_OUT": str(out), "DBUS_SESSION_BUS_ADDRESS": "", "PYTHONUTF8": "1",
                "IKE_T0": repr(time.time())})
    os.chmod(work, 0o700)
    p = subprocess.run([sys.executable, str(APP / "ike_boot.py")], env=env, capture_output=True,
                       text=True, timeout=timeout)
    if not out.exists():
        raise SystemExit("the browser ended without results (exit %s)\n%s" % (p.returncode, p.stderr[-2000:]))
    result = json.loads(out.read_text())
    shutil.rmtree(work, ignore_errors=True)
    return result


COMMON = r'''
import os, time
TICK = os.sysconf("SC_CLK_TCK")
def tree(pid):
    out = [pid]
    try:
        for c in open("/proc/%d/task/%d/children" % (pid, pid)).read().split():
            out += tree(int(c))
    except OSError:
        pass
    return out
def cpu(pids):
    t = 0
    for p in pids:
        try:
            f = open("/proc/%d/stat" % p).read(); f = f[f.rindex(")") + 2:].split(); t += int(f[11]) + int(f[12])
        except OSError:
            pass
    return t / TICK
def pss(pids):
    t = 0
    for p in pids:
        try:
            for line in open("/proc/%d/smaps_rollup" % p):
                if line.startswith("Pss:"):
                    t += int(line.split()[1])
        except OSError:
            pass
    return t // 1024
def load(view, url):
    from PyQt6.QtCore import QUrl
    done = {}
    view.page().loadFinished.connect(lambda ok, d=done: d.setdefault("t", time.perf_counter()))
    a = time.perf_counter()
    view.load(QUrl(url))
    while "t" not in done:
        yield 5
    return (done["t"] - a) * 1000
def stall_watch():
    """The longest gap between two ticks of a 5 ms timer: the interface did not answer meanwhile."""
    from PyQt6.QtCore import QTimer
    st = {"last": time.perf_counter(), "worst": 0.0}
    def tick():
        now = time.perf_counter(); st["worst"] = max(st["worst"], now - st["last"] - 0.005); st["last"] = now
    t = QTimer(); t.setInterval(5); t.timeout.connect(tick); t.start()
    st["timer"] = t
    return st
'''

START = COMMON + r'''
def steps(ike, qapp, out):
    out["since_start"] = time.time() - float(os.environ["IKE_T0"])
    out["engine"] = ike.blocker.engine is not None
    yield 10
'''

MAIN = r'''
BASE = %r
def steps(ike, qapp, out):
    import gc
    from PyQt6.QtCore import QUrl
    from ike.config import CACHE_DIR
    me = os.getpid()
    win = ike.windows[0]
    view = win.current_view()
    yield 2000
    # the engine rebuilt after a list update
    res = []
    for _ in range(3):
        for f in list(CACHE_DIR.glob("engine-*.dat")) + list(CACHE_DIR.glob("scriptlets-*.json")):
            f.unlink()
        ike.blocker._loaded = None
        st = stall_watch(); st["last"] = time.perf_counter()
        a = time.perf_counter()
        ike.blocker.load()
        while getattr(ike.blocker, "building", False):
            yield 2
        took = (time.perf_counter() - a) * 1000
        yield 50
        st["timer"].stop()
        res.append([took, st["worst"] * 1000])
    out["rebuild_ms"] = sorted(r[0] for r in res)[1]
    out["rebuild_stall_ms"] = sorted(r[1] for r in res)[1]
    # the heavy page
    icp = ike.shields.interceptor
    T = {"n": 0, "t": 0.0, "shield": 0}
    orig = type(icp).interceptRequest
    def timed(self, info):
        a = time.perf_counter(); orig(self, info); T["t"] += time.perf_counter() - a; T["n"] += 1
    type(icp).interceptRequest = timed
    o_us = type(win).update_shield
    def us(self):
        T["shield"] += 1; o_us(self)
    type(win).update_shield = us
    rows = []
    for i in range(5):
        T.update(n=0, t=0.0, shield=0)
        c0 = time.thread_time()
        ms = yield from load(view, BASE + "/heavy?%%d" %% i)
        yield 1200
        rows.append([ms, T["t"] * 1000, T["shield"], (time.thread_time() - c0) * 1000])
    rows = rows[1:]
    out["heavy_load_ms"] = sorted(r[0] for r in rows)[len(rows) // 2]
    out["heavy_intercept_ms"] = sorted(r[1] for r in rows)[len(rows) // 2]
    out["heavy_shield_redraws"] = sorted(r[2] for r in rows)[len(rows) // 2]
    out["heavy_main_cpu_ms"] = sorted(r[3] for r in rows)[len(rows) // 2]
    type(icp).interceptRequest = orig
    type(win).update_shield = o_us
    # frames, at each level
    for level in ("off", "balanced", "strict", "maximum"):
        ike.config["shield_level"] = level
        ike.shields.apply_settings()
        yield 300
        xs = []
        for i in range(5):
            ms = yield from load(view, BASE + "/frames?%%s%%d" %% (level, i))
            xs.append(ms); yield 300
        out["frames_%%s_ms" %% level] = sorted(xs[1:])[2]
    ike.config["shield_level"] = "balanced"
    ike.shields.apply_settings()
    # interface
    def timed_ui(f, n=15):
        xs = []
        for _ in range(n):
            a = time.perf_counter(); f(); xs.append((time.perf_counter() - a) * 1000)
        xs.sort(); return xs[len(xs) // 2]
    for i in range(5):
        win.add_tab(QUrl("about:blank"), background=True)
    yield 500
    views = win.views
    out["ui_switch_tab_ms"] = timed_ui(lambda: win.set_current(views[(views.index(win.current_view()) + 1) %% len(views)]))
    def newclose():
        v = win.add_tab(); win.close_tab(v)
    out["ui_new_tab_ms"] = timed_ui(newclose, 8)
    out["ui_refresh_ms"] = timed_ui(ike.refresh_windows)
    for v in list(win.views)[1:]:
        win.close_tab(v)
    yield 1000
    # rest and memory with 1 and 10 tabs
    def idle(sec):
        a = cpu(tree(me)); yield sec * 1000; return (cpu(tree(me)) - a) / sec * 100
    out["idle_cpu_pct_1tabs"] = yield from idle(15)
    out["pss_mb_1tabs"] = pss(tree(me))
    for i in range(9):
        win.add_tab(QUrl(BASE + "/heavy?tab%%d" %% i), background=True); yield 300
    yield 5000
    out["idle_cpu_pct_10tabs"] = yield from idle(20)
    out["pss_mb_10tabs"] = pss(tree(me))
    for v in list(win.views)[1:]:
        win.close_tab(v)
    yield 1000
    # a long session
    out["session_mb"] = [pss([me])]
    for r in range(4):
        for i in range(80):
            v = win.add_tab(QUrl(BASE + "/heavy?r%%d-%%d" %% (r, i))); yield 500
            win.close_tab(v); yield 60
        yield 2000; gc.collect(); yield 300
        out["session_mb"].append(pss([me]))
'''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--lists")
    ap.add_argument("--json")
    a = ap.parse_args()
    print("I.K.E. from", APP)
    lists = fetch_lists(None, a.lists)
    print("lists: %d, %.1f MB" % (len(lists), sum(len(b) for b in lists.values()) / 1e6))
    srv = serve()
    base = "http://127.0.0.1:%d" % srv.server_address[1]
    res = {}
    cold, warm = [], []
    for _ in range(a.runs):
        home = Path(tempfile.mkdtemp(prefix="ike-perf-home-"))
        make_home(home, lists)
        r = run(START, home)
        if not r.get("engine"):
            raise SystemExit("the AdBlock engine is not built: see docs/BUILDING.md")
        cold.append(r["since_start"])
        warm.append(run(START, home)["since_start"])
        shutil.rmtree(home, ignore_errors=True)
    res["start_cold_s"] = statistics.median(cold)
    res["start_warm_s"] = statistics.median(warm)
    home = Path(tempfile.mkdtemp(prefix="ike-perf-home-"))
    make_home(home, lists)
    run(START, home)                       # the engine's cache
    out = run(COMMON + MAIN % base, home, timeout=1800)
    res.update({k: v for k, v in out.items() if not k.startswith("_")})
    shutil.rmtree(home, ignore_errors=True)
    srv.shutdown()
    width = max(len(k) for k in res)
    for k, v in res.items():
        print("%s  %s" % (k.ljust(width), ("%.2f" % v) if isinstance(v, float) else v))
    if a.json:
        Path(a.json).write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
