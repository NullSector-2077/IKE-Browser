"""Per-site resources: measuring the open sites and the limits on background tabs.

Pages are served locally: "127.0.0.1" and "localhost" count as two sites.
"""

import http.server
import threading

import pytest

PAGES = {
    "/": b"<!doctype html><title>plain</title><img src='/a.png'><p>plain page</p>",
    "/big": b"<!doctype html><title>big</title><script>"
            b"window.keep=[];for(let i=0;i<40;i++)window.keep.push(new Array(1e6).fill(i));"
            b"</script>big",
    "/busy": b"<!doctype html><title>busy</title><script>"
             b"function spin(){var t=Date.now();while(Date.now()-t<900){}document.title='busy '+(++window.n||(window.n=1));"
             b"setTimeout(spin,5)}spin()</script>busy",
}
PNG = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082")


@pytest.fixture
def server():
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = PAGES.get(self.path)
            kind = "text/html"
            if body is None:
                body, kind = PNG, "image/png"
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield httpd.server_address[1]
    httpd.shutdown()


def test_measure(run_ike, server):
    out = run_ike("""
        def steps(ike, qapp, out):
            yield 300
            win = ike.windows[0]
            win.add_tab("http://127.0.0.1:%(p)d/")
            win.add_tab("http://localhost:%(p)d/big")
            yield 2500
            out["idle_timer"] = ike.resources.timer.isActive()
            dlg = ike.show_resources()
            yield 2500
            rows = {r["site"]: r for r in ike.resources.sample()}
            out["sites"] = sorted(rows)
            a, b = rows.get("127.0.0.1", {}), rows.get("localhost", {})
            out["a"] = {k: a.get(k) for k in ("tabs", "memory", "cpu", "requests", "data")}
            out["b"] = {k: b.get(k) for k in ("tabs", "memory", "cpu", "requests", "data")}
            out["table_rows"] = dlg.table.rowCount()
            out["table_sites"] = sorted(dlg.table.item(r, 0).text() for r in range(dlg.table.rowCount()))
            out["mem_cell"] = dlg.table.item(0, 2).text()
            dlg.close()
            out["watchers"] = ike.resources.watchers
    """ % {"p": server})
    assert out["idle_timer"] is False
    assert out["sites"] == ["127.0.0.1", "localhost"]
    assert out["a"]["tabs"] == 1 and out["a"]["memory"] > 1e6 and out["a"]["cpu"] is not None
    assert out["a"]["requests"] >= 2 and out["a"]["data"] > 0
    assert out["b"]["memory"] > out["a"]["memory"]          # the page keeping 40 big arrays
    assert out["table_rows"] == 2 and out["table_sites"] == out["sites"]
    assert out["mem_cell"].endswith("MB")
    assert out["watchers"] == 0


def test_memory_limit(run_ike, server):
    out = run_ike("""
        def steps(ike, qapp, out):
            yield 300
            win = ike.windows[0]
            bg = win.add_tab("http://localhost:%(p)d/big")
            yield 2000
            fg = win.add_tab("http://127.0.0.1:%(p)d/big")
            yield 2500
            out["timer"] = ike.resources.timer.isActive()
            ike.resources._tick()
            yield 500
            out["bg_sleeping"] = bool(bg.sleeping)
            out["fg_sleeping"] = bool(fg.sleeping)
            win.set_current(bg)
            yield 2000
            out["bg_back"] = not bg.sleeping and bg.title() == "big"
    """ % {"p": server}, settings={"res_mem_limit": 100})
    assert out["timer"]
    assert out["bg_sleeping"] and not out["fg_sleeping"]
    assert out["bg_back"]


def test_cpu_limit(run_ike, server):
    out = run_ike("""
        from PyQt6.QtWebEngineCore import QWebEnginePage

        def steps(ike, qapp, out):
            yield 300
            win = ike.windows[0]
            bg = win.add_tab("http://localhost:%(p)d/busy")
            yield 1500
            fg = win.add_tab("http://127.0.0.1:%(p)d/")
            yield 1000
            mon = ike.resources
            mon.timer.stop()                 # the checks are made by hand below
            mon.sample()
            states = []
            for _ in range(4):
                yield 1200
                mon._tick()
                states.append(bool(getattr(bg, "frozen", False)))
            out["states"] = states
            out["cpu"] = [r["cpu"] for r in mon.sample() if r["site"] == "localhost"]
            out["lifecycle"] = bg.page().lifecycleState() == QWebEnginePage.LifecycleState.Frozen
            t1 = bg.title()
            yield 1500
            out["stopped"] = bg.title() == t1
            win.set_current(bg)
            yield 1500
            out["woken"] = (not getattr(bg, "frozen", False)
                            and bg.page().lifecycleState() == QWebEnginePage.LifecycleState.Active
                            and bg.title() != t1)
            out["fg_untouched"] = not getattr(fg, "frozen", False)
    """ % {"p": server}, settings={"res_cpu_limit": 20})
    assert out["states"][:2] == [False, False]        # needs three checks over the limit
    assert out["states"][-1] is True and out["lifecycle"], out
    assert out["stopped"]
    assert out["woken"] and out["fg_untouched"], out


def test_off_by_default(run_ike):
    out = run_ike("""
        def steps(ike, qapp, out):
            yield 300
            out["timer"] = ike.resources.timer.isActive()
            out["limits"] = ike.resources.limits()
    """)
    assert out["timer"] is False and out["limits"] == [0, 0]


def test_memory_pressure_suspends_the_oldest_tabs(run_ike, server, tmp_path):
    """1.1.18: when the computer runs short of memory, the tabs left alone
    longest (at least five minutes) are suspended before their usual time, a
    few at each check; never the tab in view, never with suspension turned off."""
    from ike.app import memory_low
    low, fine = tmp_path / "low", tmp_path / "fine"
    low.write_text("MemTotal:       16000000 kB\nMemFree:  100 kB\nMemAvailable:    1000000 kB\n")
    fine.write_text("MemTotal:       16000000 kB\nMemAvailable:    8000000 kB\n")
    assert memory_low(str(low)) and not memory_low(str(fine))
    assert not memory_low(str(tmp_path / "missing")) and not memory_low("/dev/null")
    steps = """
        import time
        import ike.app as A
        def steps(ike, qapp, out):
            yield 300
            win = ike.windows[0]
            tabs = [win.add_tab("http://127.0.0.1:%(p)d/?%%d" %% i, background=True) for i in range(5)]
            yield 2500
            now = time.time()
            for i, v in enumerate(tabs):
                v.last_active = now - 600 + i * 60           # 10 to 6 minutes: not yet their usual time (20)
            tabs[4].last_active = now - 60                  # looked at a minute ago
            A.memory_low = lambda: %(low)s
            ike.sleep_tabs()
            yield 300
            out["sleeping"] = [bool(v.sleeping) for v in tabs]
            out["current"] = bool(win.current_view().sleeping)
            ike.sleep_tabs()
            yield 300
            out["again"] = [bool(v.sleeping) for v in tabs]
    """
    out = run_ike(steps % {"p": server, "low": True})
    assert out["sleeping"] == [True, True, True, False, False], out
    assert out["again"] == [True, True, True, True, False], out    # the next oldest, never the recent one
    assert out["current"] is False
    out = run_ike(steps % {"p": server, "low": False})
    assert out["sleeping"] == [False] * 5 and out["again"] == [False] * 5
    out = run_ike(steps % {"p": server, "low": True}, settings={"tab_sleep_minutes": 0})
    assert out["sleeping"] == [False] * 5 and out["again"] == [False] * 5    # suspension turned off: never
