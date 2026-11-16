"""Repair this site: the search for the protection that breaks a page.

A real page is served locally; it is "broken" while the ad blocker stops one of
its images (the test filter list blocks /banner-ad.*). The other tests answer
the questions from a rule, to check the search itself.
"""

import http.server
import json
import threading

import pytest
from conftest import needs_engine

PAGE = b"""<!doctype html><title>loading</title>
<img src="/banner-ad.png" onload="document.title='works'" onerror="document.title='broken'">"""
PNG = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082")


@pytest.fixture
def server():
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body, kind = (PAGE, "text/html") if self.path.startswith("/?") or self.path == "/" \
                else (PNG, "image/png")
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield "http://127.0.0.1:%d/" % httpd.server_address[1]
    httpd.shutdown()


@needs_engine
def test_repair_real_page(run_ice, server):
    out = run_ice("""
        def steps(ice, qapp, out):
            yield 300
            win = ice.windows[0]
            view = win.add_tab(%r)
            # Wait for the image's load/error handler, not only document.readyState.
            # On slower Windows runners the document can be complete before the
            # blocked image has fired onerror and updated the title.
            for _ in range(60):
                if view.url().host() and view.title() in ("broken", "works"):
                    break
                yield 500
            out["before"] = view.title()
            out["url"] = view.url().toString()
            out["button"] = True
            win.shield_panel.refresh()
            out["button"] = win.shield_panel.repair_btn.isVisibleTo(win.shield_panel)
            win.repair_site()
            r = win.repair_bar.repair
            out["candidates"] = list(r.candidates)
            out["asked"] = []
            for _ in range(12):
                yield 1500
                if r.state not in ("ask", "level"):
                    break
                works = view.title() == "works"
                out["asked"].append(works)
                r.answer(works)
            yield 1500
            out["state"] = r.state
            out["culprits"] = r.culprits
            out["bar"] = win.repair_bar.text.text()
            out["after"] = view.title()
            out["opts"] = dict(ice.config["site_opts"].get("127.0.0.1") or {})
            win.shield_panel.refresh()
            out["panel"] = win.shield_panel.repaired.text()
            win.shield_panel._undo_repair()
            yield 2000
            out["undone"] = view.title()
            out["opts_undone"] = ice.config["site_opts"].get("127.0.0.1")
    """ % server)
    assert out["before"] == "broken"
    assert out["button"]
    assert "ads" in out["candidates"] and len(out["candidates"]) >= 3
    assert out["asked"][0] is True          # everything off: the page works
    assert out["state"] == "found"
    assert out["culprits"] == ["ads"]
    assert out["after"] == "works"
    assert out["opts"] == {"ads": False, "repaired": ["ads"]}
    assert "Ad and tracker blocking" in out["bar"] and "Ad and tracker blocking" in out["panel"]
    assert out["undone"] == "broken" and out["opts_undone"] is None
    assert len(out["asked"]) <= 5


SEARCH = """
import json

def steps(ice, qapp, out):
    yield 300
    win = ice.windows[0]
    view = win.add_tab(%(url)r)
    yield 1200
    for _ in range(40):                  # the page may still be loading on a slow computer
        ready = []
        view.page().runJavaScript("document.readyState", 0, ready.append)
        yield 250
        if ready == ["complete"] and view.url().host():
            break
    cfg = ice.config
    before = json.dumps([cfg["site_opts"], cfg["site_noscript"], cfg["site_levels"]], sort_keys=True)
    from ice import repair
    need = %(need)r                      # protections that must be off for the page to work
    win.repair_site()
    r = win.repair_bar.repair
    out["candidates"] = list(r.candidates)
    n = 0
    while r.state in ("ask", "level") and n < 20:
        yield 50
        if r.state == "level":
            works = %(level_works)r
        else:
            now = repair.active(cfg, "127.0.0.1")
            works = not any(k in now for k in need) and %(fixable)r
        r.answer(works)
        n += 1
        if %(cancel_at)r and n == %(cancel_at)r:
            win.repair_bar.cancel()
            break
    yield 300
    out["questions"] = n
    out["state"] = r.state
    out["culprits"] = r.culprits
    out["level"] = cfg["site_levels"].get("127.0.0.1")
    out["same"] = before == json.dumps([cfg["site_opts"], cfg["site_noscript"], cfg["site_levels"]],
                                       sort_keys=True)
    saved = json.loads(cfg.path.read_text("utf-8"))
    out["saved_opts"] = saved.get("site_opts", {}).get("127.0.0.1")
"""


def _search(run_ice, server, need, fixable=True, level_works=False, cancel_at=0, settings=None):
    return run_ice(SEARCH % {"url": server, "need": need, "fixable": fixable,
                             "level_works": level_works, "cancel_at": cancel_at},
                   settings=settings or {"shield_level": "balanced"})


def test_repair_finds_one(run_ice, server):
    out = _search(run_ice, server, ["fp"])
    assert out["state"] == "found" and out["culprits"] == ["fp"]
    assert out["saved_opts"] == {"fp": False, "repaired": ["fp"]}
    assert out["questions"] <= 1 + 2 * len(out["candidates"])


def test_repair_finds_two(run_ice, server):
    out = _search(run_ice, server, ["cookies", "params"])
    assert out["state"] == "found" and sorted(out["culprits"]) == ["cookies", "params"]
    assert out["saved_opts"]["cookies"] == "allow" and out["saved_opts"]["params"] is False


def test_repair_not_the_cause(run_ice, server):
    out = _search(run_ice, server, [], fixable=False, level_works=False)
    assert out["state"] == "none"
    assert out["same"] and out["saved_opts"] is None and out["level"] is None


def test_repair_whole_shield(run_ice, server):
    out = _search(run_ice, server, [], fixable=False, level_works=True)
    assert out["state"] == "level-kept" and out["level"] == "off"


def test_repair_cancel_restores(run_ice, server):
    out = _search(run_ice, server, ["https"], cancel_at=2,
                  settings={"shield_level": "strict", "site_noscript": ["127.0.0.1"],
                            "site_opts": {"127.0.0.1": {"cookies": "3p"}}})
    assert "scripts" in out["candidates"] and "cookies" in out["candidates"]
    assert out["state"] == "cancelled"
    assert out["same"]
    assert json.dumps(out["saved_opts"]) in ("null", json.dumps({"cookies": "3p"}))


def test_repair_switch_off(run_ice, server):
    out = run_ice("""
        def steps(ice, qapp, out):
            yield 300
            win = ice.windows[0]
            win.add_tab(%r)
            yield 1200
            win.shield_panel.refresh()
            out["shown"] = win.shield_panel.repair_btn.isVisibleTo(win.shield_panel)
    """ % server, settings={"repair_button": False})
    assert out["shown"] is False
