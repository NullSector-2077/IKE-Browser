"""The I.K.E. Dark Engine in the browser (1.1.28): its own panel under the
toolbar's Dark mode button, its look given to the open pages without loading
them again, its choice and options in Settings, and Dark Reader still there."""

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from test_security import JS

PAGE = ("<!doctype html><html><head><title>p</title><style>body{background:#ffffff;color:#222}"
        ".box{background:#f4f4f4;height:60px}</style></head><body><div class='box'>Box</div>"
        "<p>Text of the page.</p></body></html>")


@pytest.fixture
def site():
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            data = PAGE.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):
            pass
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield "http://127.0.0.1:%d" % srv.server_address[1]
    srv.shutdown()


STEPS = JS + r'''
SITE = "__SITE__"
SHOT = __SHOT__
READ = "JSON.stringify([getComputedStyle(document.body).backgroundColor, window.__ikeMarker || null])"

def steps(ike, qapp, out):
    win = ike.windows[0]
    a = win.current_view()
    yield from load(a, SITE + "/a")
    b = win.add_tab(SITE + "/b", background=True)
    yield 2500
    win.set_current(a)
    for v in (a, b):
        yield from js(v, "window.__ikeMarker = 'kept'")
    out["start"] = json.loads((yield from js(a, READ)))
    win.show_dark_panel()
    yield 400
    panel = win.dark_panel
    out["panel"] = type(panel).__name__
    out["title"] = panel.title.text()
    out["master"] = panel.master.isChecked()
    if SHOT:
        panel.grab().save(SHOT)
    # a style chosen: kept, and every open page takes it without loading again
    panel.cards._choose(2)
    yield 800
    out["style"] = ike.config["dark_engine_look"]["style"]
    out["warm_a"] = json.loads((yield from js(a, READ)))
    out["warm_b"] = json.loads((yield from js(b, READ)))
    # a slider moved: this tab at once, the others when it is let go
    s = panel.sliders["depth"]
    s.setSliderDown(True)
    s.setValue(95)
    yield 700
    out["during_a"] = json.loads((yield from js(a, READ)))
    out["during_b"] = json.loads((yield from js(b, READ)))
    s.setSliderDown(False)
    yield 700
    out["after_b"] = json.loads((yield from js(b, READ)))
    out["depth"] = ike.config["dark_engine_look"]["depth"]
    win.dark_menu.hide()
    yield 200
    # Settings: the engine by its name, with its own options
    dlg = ike.show_settings(win)
    yield 300
    out["methods"] = [dlg.dark_engine.itemText(i) for i in range(dlg.dark_engine.count())]
    out["method"] = dlg.dark_engine.currentData()
    out["dlg_style"] = dlg.de_style.currentData()
    dlg.close()
    # Dark Reader chosen again: its own panel
    ike.set_dark_mode("on", win, "reader")
    yield 1500
    win.show_dark_panel()
    yield 300
    out["panel_reader"] = type(win.dark_panel).__name__
    win.dark_menu.hide()
'''


def test_engine_panel_looks_and_settings(run_ike, site, tmp_path):
    shot = os.environ.get("IKE_PANEL_SHOT", "")
    out = run_ike(STEPS.replace("__SITE__", site).replace("__SHOT__", json.dumps(shot)),
                  settings={"dark_mode": "on", "dark_engine": "ike"}, timeout=180)
    assert out["panel"] == "EnginePanel" and out["title"] == "I.K.E. Dark Engine" and out["master"], out
    assert out["start"][0] == "rgb(24, 26, 27)", out                     # Graphite: Dark Reader's own grey
    assert out["style"] == "warm", out
    assert out["warm_a"][0] == out["warm_b"][0] != out["start"][0], json.dumps(out)   # every open page, warm
    assert out["warm_a"][1] == out["warm_b"][1] == "kept", out            # nothing loaded again
    assert out["during_a"][0] != out["warm_a"][0], out                    # this tab at once
    assert out["during_b"][0] == out["warm_b"][0], out                    # the other one: not yet
    assert out["after_b"][0] == out["during_a"][0], out                   # let go: the other one too
    assert out["depth"] == 95, out
    assert "I.K.E. Dark Engine" in out["methods"] and out["method"] == "ike" and out["dlg_style"] == "warm", out
    assert any("Dark Reader" in m for m in out["methods"]), out
    assert out["panel_reader"] == "DarkPanel", out


def test_the_hidden_switch_of_the_experiment_becomes_the_choice(run_ike, site):
    out = run_ike(JS + '''
def steps(ike, qapp, out):
    yield 300
    out["engine"] = ike.config["dark_engine"]
    out["flag"] = ike.config.get("dark_engine_experiment")
    out["look"] = ike.config["dark_engine_look"]
''', settings={"dark_mode": "on", "dark_engine": "reader", "dark_engine_experiment": True,
               "dark_engine_look": {"style": "nope", "depth": 999}})
    assert out["engine"] == "ike" and out["flag"] is False, out
    assert out["look"]["style"] == "graphite" and out["look"]["depth"] == 100, out
