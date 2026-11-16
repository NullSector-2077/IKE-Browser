"""Page watcher: a page, or a part of it, checked in the background for changes.

A local server plays a shop: the price is read from a file the test (inside the
browser) can change, and every load also changes a counter elsewhere on the
page. Cookies sent to the server are recorded.
"""

import http.server
import threading

import pytest


@pytest.fixture
def shop(tmp_path):
    price = tmp_path / "price"
    price.write_text("10")
    seen = {"n": 0, "cookies": []}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != "/":
                self.send_response(404)
                self.end_headers()
                return
            seen["n"] += 1
            seen["cookies"].append(self.headers.get("Cookie") or "")
            p = price.read_text()
            body = ("<!doctype html><title>Shop</title><body style='margin:0'>"
                    "<h1>Shop</h1><p>loaded %d</p>"
                    "<div><span>prike:</span> <b id='price' style='font-size:40px'>%s</b></div>"
                    "<ul><li>a</li><li style='font-size:40px'>%s euro</li></ul>"
                    "<script>document.cookie='seen=1; max-age=3600'</script>"
                    % (seen["n"], p, p)).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield "http://127.0.0.1:%d/" % httpd.server_address[1], price, seen
    httpd.shutdown()


SCRIPT = """
import json
from PyQt6.QtCore import QPoint

URL, TARGET, PART, PRICE = %r, %r, %r, %r


def wait_check(ice):
    for _ in range(60):
        yield 250
        if ike.watcher._current is None:
            return


def steps(ice, qapp, out):
    notes = []
    ike._desktop_notify = notes.append
    yield 300
    win = ike.windows[0]
    out["timer_idle"] = ike.watcher.timer.isActive()
    view = win.add_tab(URL)
    yield 2000
    shield_before = ike.shields.total("127.0.0.1")
    requests_before = ike.shields.requests.get("127.0.0.1", 0)
    res = {}
    for _ in range(40):                  # the page may still be loading on a slow computer
        view.page().runJavaScript(
            "(function(){var r=%%s.getBoundingClientRect();return [r.left+r.width/2,r.top+r.height/2]})()"
            %% TARGET, lambda v: res.__setitem__("pt", v))
        yield 400
        if res.get("pt"):
            break
    from ike.watcher import pick_and_watch
    pick_and_watch(view, QPoint(int(res["pt"][0]), int(res["pt"][1])), PART)
    yield 600
    dlg = ike._dialogs["watch-add"]
    dlg.interval.setCurrentIndex(0)
    dlg.accept()
    w = ike.watcher.watches[0]
    out["watch"] = {k: w[k] for k in ("selector", "excerpt", "interval", "url")}
    out["timer_on"] = ike.watcher.timer.isActive()
    out["due_now"] = len(ike.watcher.due())
    ike.watcher.check(w)                 # nothing changed but the counter elsewhere
    yield from wait_check(ice)
    out["first"] = {k: w[k] for k in ("status", "changed")}
    out["notes1"] = list(notes)
    open(PRICE, "w").write("12")
    ike.watcher.check(w)
    yield from wait_check(ice)
    out["second"] = {k: w[k] for k in ("status", "changed", "excerpt")}
    out["notes2"] = list(notes)
    out["shield_same"] = ike.shields.total("127.0.0.1") == shield_before
    out["requests_same"] = ike.shields.requests.get("127.0.0.1", 0) == requests_before
    dlg = ike.show_watches()
    yield 300
    out["rows"] = dlg.table.rowCount()
    out["bold"] = dlg.table.item(0, 0).font().bold()
    out["state_cell"] = dlg.table.item(0, 4).text()
    n_tabs = len(win.views)
    dlg._open()
    yield 300
    out["opened"] = len(win.views) == n_tabs + 1
    out["seen"] = w["changed"] is False
    saved = json.loads(ike.config.path.read_text("utf-8"))
    out["saved"] = saved["page_watches"][0]["excerpt"]
    dlg._remove()
    out["left"] = len(ike.watcher.watches)
    out["timer_after"] = ike.watcher.timer.isActive()
"""


def _run(run_ice, shop, target, part):
    url, price, seen = shop
    out = run_ice(SCRIPT % (url, target, part, str(price)))
    return out, seen


def test_watch_part(run_ice, shop):
    out, seen = _run(run_ice, shop, "document.getElementById('price')", True)
    assert out["timer_idle"] is False
    assert out["watch"]["selector"] == "#price" and out["watch"]["excerpt"] == "10"
    assert out["watch"]["interval"] == 15 and out["timer_on"] and out["due_now"] == 0
    assert out["first"] == {"status": "ok", "changed": False} and out["notes1"] == []
    assert out["second"] == {"status": "ok", "changed": True, "excerpt": "12"}
    assert len(out["notes2"]) == 1 and "Shop" in out["notes2"][0]
    assert out["shield_same"] and out["requests_same"]
    # the background checks carry none of the user's cookies
    # (loads: the tab, the two checks, the tab opened from the list)
    assert len(seen["cookies"]) == 4, seen
    assert all("seen=1" not in c for c in seen["cookies"][1:3]), seen
    assert "seen=1" in seen["cookies"][3]
    assert out["rows"] == 1 and out["bold"] and out["state_cell"] == "Changed"
    assert out["opened"] and out["seen"]
    assert out["saved"] == "12"
    assert out["left"] == 0 and out["timer_after"] is False


def test_watch_part_without_id(run_ice, shop):
    out, _ = _run(run_ice, shop, "document.querySelectorAll('li')[1]", True)
    assert out["watch"]["selector"] == "body > ul:nth-of-type(1) > li:nth-of-type(2)"
    assert out["watch"]["excerpt"] == "10 euro"
    assert out["first"]["changed"] is False
    assert out["second"]["changed"] is True and out["second"]["excerpt"] == "12 euro"


def test_watch_whole_page(run_ice, shop):
    out, _ = _run(run_ice, shop, "document.body", False)
    assert out["watch"]["selector"] == ""
    # the counter on the page changes at every load: the whole page differs each time
    assert out["first"]["changed"] is True
    assert "12 euro" in out["second"]["excerpt"]


def test_watch_due_and_missing(run_ice, shop):
    url, _price, _seen = shop
    out = run_ice("""
        def steps(ice, qapp, out):
            yield 300
            w = ike.watcher.watches[0]
            out["timer"] = ike.watcher.timer.isActive()
            ike.watcher.check_due()          # due: last checked long ago
            out["started"] = ike.watcher._current is w
            for _ in range(60):
                yield 250
                if ike.watcher._current is None:
                    break
            out["status"] = w["status"]
            out["checked"] = w["last_check"] > 0
            dlg = ike.show_watches()
            out["cell"] = dlg.table.item(0, 4).text()
    """, settings={"page_watches": [{"url": url, "selector": "#gone", "name": "Gone", "interval": 15,
                                     "last_check": 0, "hash": "", "excerpt": "", "changed": False,
                                     "status": "ok"}]})
    assert out["timer"] and out["started"]
    assert out["status"] == "missing" and out["checked"]
    assert out["cell"] == "The part was not found"


def test_watch_switched_off(run_ice, shop):
    url, _price, _seen = shop
    out = run_ice("""
        def steps(ice, qapp, out):
            yield 300
            out["timer"] = ike.watcher.timer.isActive()
            ike.watcher.check_due()
            out["started"] = ike.watcher._current is not None
    """, settings={"page_watch_on": False,
                   "page_watches": [{"url": url, "selector": "", "name": "x", "interval": 15,
                                     "last_check": 0, "hash": "", "excerpt": ""}]})
    assert out["timer"] is False and out["started"] is False
