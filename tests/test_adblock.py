"""I.K.E. AdBlock engine: matching, and blocking in a real page load.

The page is served by a small local web server; the filter list is the test
list written by conftest.py in place of EasyList.
"""

import http.server
import threading

import pytest
from conftest import needs_engine

PAGE = b"""<!doctype html><title>adtest</title>
<img src="/banner-ad.png"><img src="/ok.png">
<div class="ice-test-ad" id="ad">ad</div><div id="plain">text</div>"""
PNG = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082")


@pytest.fixture
def server():
    seen = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append(self.path)
            body, kind = (PAGE, "text/html") if self.path == "/" else (PNG, "image/png")
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield "http://127.0.0.1:%d/" % httpd.server_address[1], seen
    httpd.shutdown()


@needs_engine
def test_engine_matching(run_ice):
    out = run_ice("""
        def steps(ice, qapp, out):
            yield 300
            b = ice.blocker
            out["native"] = b.native
            out["engine"] = b.engine is not None
            import adblock
            out["backend"] = getattr(adblock, "BACKEND", "")
            out["ad"] = b.should_block("https://ads.example.test/a.js", "https://site.test/", "script")
            out["ok"] = b.should_block("https://cdn.example.test/a.js", "https://site.test/", "script")
            out["css"] = b.cosmetic_css("https://site.test/") or ""
    """)
    assert out["native"] and out["engine"]
    assert out["ad"] is True
    assert out["ok"] is False
    assert out["backend"]


@needs_engine
def test_blocks_in_page(run_ice, server):
    url, seen = server
    out = run_ice("""
        def steps(ice, qapp, out):
            yield 300
            win = ice.windows[0]
            view = win.add_tab(%r)
            loaded = {"done": False, "ok": None}
            view.loadFinished.connect(lambda ok: loaded.update(done=True, ok=ok))
            for _ in range(200):
                if loaded["done"]:
                    break
                yield 100
            out["load_finished"] = loaded["done"] and loaded["ok"] is True
            out["title"] = view.title()
            res = {"done": False, "display": None}
            view.page().runJavaScript(
                "[getComputedStyle(document.getElementById('ad')).display,"
                " getComputedStyle(document.getElementById('plain')).display]",
                lambda value: res.update(done=True, display=value))
            for _ in range(50):
                if res["done"]:
                    break
                yield 100
            out["javascript_finished"] = res["done"]
            out["display"] = res["display"]
            out["count"] = ice.shields.total("127.0.0.1")
    """ % url, settings={"shield_level": "balanced"})
    assert out["load_finished"], f"page did not finish loading (title={out['title']!r}, requests={seen})"
    assert out["javascript_finished"], "JavaScript result callback did not complete"
    assert out["title"] == "adtest"
    assert "/ok.png" in seen
    assert "/banner-ad.png" not in seen
    assert out["display"] == ["none", "block"]
    assert out["count"] >= 1


@needs_engine
def test_engine_error_lets_request_through_and_is_counted(run_ice, server):
    """Fail-open is kept: when the engine fails on a request, the request goes
    on (blocking everything would break browsing). The error is counted and
    shown in Help → About."""
    url, seen = server
    out = run_ice("""
        def steps(ice, qapp, out):
            yield 300
            b = ice.blocker
            out["before"] = b.errors
            real = b.engine

            class Broken:
                def __getattr__(self, name):
                    attr = getattr(real, name)
                    if name in ("check_network_request", "check_network_urls", "url_cosmetic_resources"):
                        def fail(*a, **k):
                            raise RuntimeError("broken engine")
                        return fail
                    return attr
            b.engine = Broken()
            view = ice.windows[0].add_tab(%r)
            loaded = {"done": False, "ok": None}
            view.loadFinished.connect(lambda ok: loaded.update(done=True, ok=ok))
            for _ in range(200):
                if loaded["done"]:
                    break
                yield 100
            out["load_finished"] = loaded["done"] and loaded["ok"] is True
            out["title"] = view.title()
            out["url"] = view.url().toString()
            # Let post-load cosmetic filtering finish before inspecting the
            # engine error counter. Do not assume a fixed page-load duration.
            yield 500
            out["errors"] = b.errors
            out["about"] = ice.windows[0]._engine_about(b)
            b.engine = real
            out["blocked_again"] = b.should_block("https://ads.example.test/a.js", "https://site.test/", "script")
            out["errors_after"] = b.errors
    """ % url)
    assert out["before"] == 0
    assert out["load_finished"], f"page did not finish loading (title={out['title']!r}, url={out['url']!r}, requests={seen})"
    assert "/banner-ad.png" in seen                 # let through while the engine failed
    assert out["errors"] >= 2                       # the page, its images, its cosmetic filters
    assert ("Engine errors this session (let through unfiltered): %d" % out["errors"]) in out["about"]
    assert out["blocked_again"] is True and out["errors_after"] == out["errors"]
