"""What Dark Reader costs a page, against the engine's own dark mode and
against no dark mode (1.1.20): a budget that fails only on a clear regression.

One browser, one local page that does a fixed amount of work (style sheets,
styled elements, shadow roots, an SVG; then 30 bursts of new styles and
elements, each answered at once by Dark Reader's observers) and says how long
it took until the page was idle again. The three modes take turns, in a
different order each round, after one round that only warms up; the result is
the median of each round's RATIOS (Dark Reader / off, Dark Reader / engine),
never an absolute time: a GitHub runner is slower or busier from one minute to
the next, but all three modes see the same machine within a round.

The budget is the ratio recorded in tests/data/darkreader-cost.json times its
margin (2: the whole page with Dark Reader twice as slow, relative to the
page without it, as when the baseline was recorded). A new Dark Reader engine
or a change to I.K.E.'s patches (tools/build-darkreader.py) that makes it
clearly slower fails here, with the measured ratios in the message. On GitHub
the line "Dark Reader cost: ..." also goes into the run's summary.

To update the baseline after a deliberate change (docs/MAINTENANCE.md): run

    IKE_DARK_COST_RECORD=1 python3 -m pytest -q tests/test_darkreader_cost.py

which writes the measured ratios into tests/data/darkreader-cost.json (those
of the computer that ran it: compare with the "Dark Reader cost" lines in the
summaries of green GitHub runs, and keep the larger values)."""

import json
import os
import statistics
import threading
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from conftest import ROOT
from test_security import JS

BASELINE = ROOT / "tests" / "data" / "darkreader-cost.json"
ROUNDS = 7             # measured rounds (one more warms up)


def page_html():
    """A light page with work for Dark Reader: built the same every time."""
    css = "".join(".c%d{color:#%02x%02x%02x;background:#%02x%02x%02x;border-left:%dpx solid #%02x%02x%02x;"
                  "padding:%dpx}" % (i, i % 97, 40 + i % 60, i % 13 * 9, 250 - i % 7, 248 - i % 11, 240 - i % 5,
                                     i % 4 + 1, i % 200, 90, 160, i % 9)
                  for i in range(600))
    cards = "".join("<div class='c%d' style='background-color:rgb(%d,%d,%d)'><b>Card %d</b> some text of a card, "
                    "<a href='#a%d'>a link</a>, <span style='color:#%02x3366'>a coloured word</span>.</div>"
                    % (i * 7 % 600, 255 - i % 23, 250 - i % 17, 245 - i % 13, i, i, i % 256) for i in range(400))
    comps = ("<script>customElements.define('x-item',class extends HTMLElement{constructor(){super();"
             "var r=this.attachShadow({mode:'open'});r.innerHTML='<style>:host{display:block;background:#eef;"
             "color:#123;margin:4px;padding:6px;border:1px solid #99a}b{color:#a00}</style><b>item</b> "
             "<slot></slot>';}});</script>" + "".join("<x-item class='c%d'>component %d</x-item>" % (i * 11 % 600, i)
                                                      for i in range(60)))
    svg = "<svg width=1200 height=300>" + "".join(
        "<rect x=%d y=%d width=5 height=%d fill='#%02x%02x%02x'/>" % (i % 240 * 5, 300 - i * 37 % 280, i * 37 % 280,
                                                                     i % 256, 128, 255 - i % 256)
        for i in range(300)) + "</svg>"
    probe = r"""<script>
(function () {
  var longMs = 0, steps = 30, i = 0, ch = new MessageChannel();
  try { new PerformanceObserver(function (l) { l.getEntries().forEach(function (e) { longMs += e.duration; }); })
    .observe({type: "longtask", buffered: true}); } catch (e) {}
  function hex(a, b) { return ("00000" + ((a * 7919 + b * 104729) % 16777216).toString(16)).slice(-6); }
  function step() {
    var st = document.createElement("style"), css = "";
    for (var k = 0; k < 20; k++) {
      css += ".d" + i + "_" + k + "{color:#" + hex(i, k) + ";background:#" + hex(k, i) +
             ";border:1px solid #" + hex(i + k, 3) + "}";
    }
    st.textContent = css;
    document.head.appendChild(st);
    var box = document.createElement("div");
    for (var k = 0; k < 30; k++) {
      var e = document.createElement("p");
      e.className = "d" + i + "_" + (k % 20);
      e.style.backgroundColor = "rgb(" + (200 + k) + "," + (240 - i) + "," + (230 + k % 20) + ")";
      e.textContent = "dynamic " + i + " " + k;
      box.appendChild(e);
    }
    document.body.appendChild(box);
    void document.body.offsetHeight;
    i++;
    if (i < steps) ch.port2.postMessage(0); else settle();
  }
  ch.port1.onmessage = step;
  function idle(cb) {
    if (window.requestIdleCallback) requestIdleCallback(cb, {timeout: 4000}); else setTimeout(cb, 50);
  }
  function settle() {
    idle(function () { requestAnimationFrame(function () { idle(function () {
      document.title = "done:" + JSON.stringify({ms: Math.round(performance.now()), long_ms: Math.round(longMs)});
    }); }); });
  }
  addEventListener("load", function () { ch.port2.postMessage(0); });
})();
</script>"""
    return ("<!doctype html><meta charset=utf-8><title>cost</title><style>body{font:15px sans-serif;margin:16px;"
            "background:#fafafa;color:#222}div{margin:4px 0}%s</style>%s%s%s%s" % (css, probe, svg, comps, cards))


@pytest.fixture
def site():
    body = page_html().encode()

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
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
from PyQt6.QtCore import QUrl
from PyQt6.QtWebEngineCore import QWebEngineSettings
SITE = "__SITE__"
ROUNDS = __ROUNDS__
MODES = (("off", "off", None), ("reader", "on", "reader"), ("engine", "on", "engine"))

def steps(ike, qapp, out):
    win = ike.windows[0]
    win.resize(1280, 900)
    view = win.current_view()
    yield 800
    out["runs"] = []
    for r in range(ROUNDS + 1):              # round 0 only warms up
        for name, mode, engine in MODES[r % 3:] + MODES[:r % 3]:
            ike.set_dark_mode(mode, None, engine)
            yield 300
            view.load(QUrl("%s/cost?mode=%s&round=%d" % (SITE, name, r)))
            waited = 0
            while not view.title().startswith("done:") and waited < 40000:
                yield 50
                waited += 50
            title = view.title()
            run = json.loads(title[5:]) if title.startswith("done:") else {"timeout": True}
            run.update(mode=name, round=r)
            run["dr"] = (yield from js(view, "document.querySelectorAll('style.darkreader').length"))
            run["force_dark"] = view.page().settings().testAttribute(
                QWebEngineSettings.WebAttribute.ForceDarkMode)
            out["runs"].append(run)
'''


def ratios(runs):
    """Per measured round, Dark Reader / off, Dark Reader / engine and
    engine / off; their medians."""
    rounds = {}
    for r in runs:
        if r["round"] > 0:
            rounds.setdefault(r["round"], {})[r["mode"]] = r["ms"]
    per = [(m["reader"] / m["off"], m["reader"] / m["engine"], m["engine"] / m["off"]) for m in rounds.values()]
    return {"reader_vs_off": round(statistics.median(p[0] for p in per), 3),
            "reader_vs_engine": round(statistics.median(p[1] for p in per), 3),
            "engine_vs_off": round(statistics.median(p[2] for p in per), 3),
            "ms": {mode: round(statistics.median(m[mode] for m in rounds.values())) for mode in
                   ("off", "reader", "engine")}}


def test_ratios_are_medians_of_each_round():
    runs = [{"round": 0, "mode": "off", "ms": 1}, {"round": 0, "mode": "reader", "ms": 99},
            {"round": 0, "mode": "engine", "ms": 1}]          # warming up: not counted
    for r, (off, reader, engine) in enumerate([(100, 200, 110), (300, 450, 310), (100, 900, 100)], 1):
        runs += [{"round": r, "mode": "off", "ms": off}, {"round": r, "mode": "reader", "ms": reader},
                 {"round": r, "mode": "engine", "ms": engine}]
    got = ratios(runs)
    assert got["reader_vs_off"] == 2.0 and got["engine_vs_off"] == 1.033
    assert got["ms"] == {"off": 100, "reader": 450, "engine": 110}


def test_the_baseline_is_there():
    base = json.loads(BASELINE.read_text("utf-8"))
    assert base["margin"] >= 1.5          # a budget for a clear regression only, never for noise
    assert 1.0 <= base["reader_vs_off"] < 20 and 0.5 <= base["reader_vs_engine"] < 20


def test_dark_reader_stays_within_its_cost_budget(run_ike, site):
    out = run_ike(STEPS.replace("__SITE__", site).replace("__ROUNDS__", str(ROUNDS)), timeout=400)
    runs = out["runs"]
    assert not [r for r in runs if r.get("timeout")], runs
    # what is measured is what it claims to be: Dark Reader only in its mode, the engine's dark mode only in its
    for r in runs:
        assert (r["dr"] > 0) == (r["mode"] == "reader"), r
        assert r["force_dark"] == (r["mode"] == "engine"), r
    got = ratios(runs)
    base = json.loads(BASELINE.read_text("utf-8"))
    line = ("Dark Reader cost: Dark Reader / off %.2f, Dark Reader / engine dark %.2f, engine dark / off %.2f "
            "(median ms: off %d, Dark Reader %d, engine %d); baseline %.2f / %.2f, margin %.1f"
            % (got["reader_vs_off"], got["reader_vs_engine"], got["engine_vs_off"], got["ms"]["off"],
               got["ms"]["reader"], got["ms"]["engine"], base["reader_vs_off"], base["reader_vs_engine"],
               base["margin"]))
    print(line)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:             # on GitHub: the measured ratios in the run's summary, green or red
        try:
            with open(summary, "a", encoding="utf-8") as f:
                f.write("\n%s\n" % line)
        except OSError:
            pass
    if os.environ.get("IKE_DARK_COST_RECORD") == "1":
        base.update(reader_vs_off=got["reader_vs_off"], reader_vs_engine=got["reader_vs_engine"],
                    recorded="%s, %s" % (date.today().isoformat(), line))
        BASELINE.write_text(json.dumps(base, indent=1) + "\n", "utf-8")
        return
    assert got["reader_vs_off"] <= base["reader_vs_off"] * base["margin"], line
    assert got["reader_vs_engine"] <= base["reader_vs_engine"] * base["margin"], line
