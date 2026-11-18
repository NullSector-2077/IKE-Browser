"""Lighter pages (1.1.13).

- The cookie-banner handler (consent.js) still refuses consent: through a
  known platform's button, through a generic button whose hidden text differs
  from what is shown, and through a banner that appears late; a "Rifiuta"
  outside any banner is left alone. Its looks are now one query, without
  layout work, in the page's idle time.
- I.K.E.'s own rules block the telemetry of YouTube and Google that the lists
  let through, and never what the page needs (history, video servers).
- Persistent profiles get a large disk cache.
- The package and the AdBlock engine run on every x86_64 processor, old ones
  too, whatever processor builds them.
"""

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from conftest import needs_engine

PAGES = {
    "/known": b"""<!doctype html><title>known</title><body><p>page</p>
<div id="onetrust-banner-sdk"><button id="onetrust-reject-all-handler"
 onclick="document.title='clicked:known'">Rifiuta</button></div></body>""",
    "/generic": b"""<!doctype html><title>generic</title><body>
<div class="toolbar"><button onclick="document.title='wrong'">Rifiuta</button></div>
<div class="cookie-notice"><p>Usiamo i cookie</p>
<button onclick="document.title='clicked:generic'">Rifiuta tutto<span style="display:none">
 i cookie di profilazione e di terze parti</span></button></div></body>""",
    "/late": b"""<!doctype html><title>late</title><body><p>page</p><script>
setTimeout(function () {
  var d = document.createElement('div'); d.className = 'cc-window';
  d.innerHTML = '<a class="cc-btn cc-deny" href="#" onclick="document.title=\\'clicked:late\\';return false">No</a>';
  document.body.appendChild(d);
}, 1500);
</script></body>""",
}


@pytest.fixture
def site():
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            body = PAGES.get(self.path, b"<!doctype html><title>none</title>")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1]
    srv.shutdown()


CONSENT = r'''
from PyQt6.QtCore import QUrl

def steps(ike, qapp, out):
    v = ike.windows[0].current_view()
    done = {}
    v.page().loadFinished.connect(lambda ok: done.setdefault("ok", ok))
    for name in ("known", "generic", "late"):
        done.clear()
        v.load(QUrl("http://127.0.0.1:%d/" + name))
        while "ok" not in done:
            yield 20
        for _ in range(60):                       # at most 6 s
            if v.title().startswith(("clicked:", "wrong")):
                break
            yield 100
        out[name] = v.title()
    out["cache"] = ike.profile.httpCacheMaximumSize()
'''


def test_cookie_banners_refused_and_a_big_disk_cache(run_ike, site):
    out = run_ike(CONSENT % site, timeout=120)
    assert out["known"] == "clicked:known"
    assert out["generic"] == "clicked:generic"            # not the "Rifiuta" of the toolbar
    assert out["late"] == "clicked:late"
    assert out["cache"] == 512 * 1024 * 1024


RULES = r'''
def steps(ike, qapp, out):
    yield 300
    b = ike.blocker
    page = "https://www.youtube.com/watch?v=abc"
    for url, kind, method in (
            ("https://www.youtube.com/api/stats/qoe?fmt=1", "xmlhttprequest", "POST"),
            ("https://www.youtube.com/youtubei/v1/log_event?alt=json", "xmlhttprequest", "POST"),
            ("https://www.youtube.com/ptracking?ei=x", "image", "GET"),
            ("https://www.youtube.com/csi_204?v=3", "ping", "GET"),
            ("https://play.google.com/log?format=json", "xmlhttprequest", "POST"),
            ("https://www.youtube.com/api/stats/watchtime?ns=yt", "xmlhttprequest", "GET"),
            ("https://www.youtube.com/api/stats/playback?ns=yt", "xmlhttprequest", "GET"),
            ("https://rr1---sn-x.googlevideo.com/generate_204", "xmlhttprequest", "GET"),
            ("https://www.youtube.com/youtubei/v1/player?key=x", "xmlhttprequest", "POST"),
            ("https://www.youtube.com/s/player/abc/base.js", "script", "GET")):
        out[url.split("//", 1)[1].split("?")[0]] = b.request_action(url, page, kind, method)[0]
'''


@needs_engine
def test_youtube_telemetry_blocked_and_what_the_page_needs_kept(run_ike):
    out = run_ike(RULES)
    for path in ("www.youtube.com/api/stats/qoe", "www.youtube.com/youtubei/v1/log_event",
                 "www.youtube.com/ptracking", "www.youtube.com/csi_204", "play.google.com/log"):
        assert out[path] == "block", (path, out[path])
    for path in ("www.youtube.com/api/stats/watchtime", "www.youtube.com/api/stats/playback",
                 "rr1---sn-x.googlevideo.com/generate_204", "www.youtube.com/youtubei/v1/player",
                 "www.youtube.com/s/player/abc/base.js"):
        assert out[path] == "allow", (path, out[path])


def test_built_for_every_x86_64_processor():
    # the package and the engine of the self-update are built on the owner's
    # computer: never for its own processor only (1.1.13: an i5-3570K)
    from pathlib import Path
    recipe = (Path(__file__).resolve().parent.parent / "PKGBUILD").read_text()
    build = recipe.split("build() {", 1)[1].split("\n}", 1)[0]
    assert '-C target-cpu=x86-64"' in build and "cargo build" in build
    assert "-march=x86-64 -mtune=generic" in build
