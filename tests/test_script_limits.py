"""Where the engine runs I.K.E.'s profile scripts (1.1.23, comparison with
Falkon, docs/review/tests-and-performance.md "1.1.23").

- No profile script runs in the error page of a blocked frame
  (chrome-error://): the page cannot reach it, and every blocked ad frame
  paid for all of them. They still run in the page, in its frames, in empty
  frames (about:blank) and in srcdoc frames.
- A site's list scriptlets (ike-sl-*) are compiled only in that host's
  documents and its empty frames; their own check of the host stays.
- The video sites' scripts (ike-video-*, ike-videoads; the owner's OK of
  2026-11-22) only on the video sites' hosts, as a page or embedded in
  another site, and nowhere else; the relay of an embedded player's clicks
  runs in the top page of any site.

The engine decides from the "==UserScript==" lines of each script. The test
reads them from I.K.E.'s own scripts and runs small probes carrying exactly
those lines in pages served from a local server under the real names
(--host-resolver-rules), then checks the real scripts' own effects on the
video sites. SIMULATION: local pages shaped like the sites, not YouTube.
"""

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from conftest import needs_engine

from ike import shields

HEADER = "\n// ==UserScript=="
NO_PROXY_ENV = {"http_proxy": "", "https_proxy": "", "HTTP_PROXY": "", "HTTPS_PROXY": "", "all_proxy": "",
                "ALL_PROXY": "", "no_proxy": "*", "NO_PROXY": "*", "IKE_ALLOW_UNSAFE_ENGINE": "1"}


def header_of(source):
    """The engine's lines at the end of a script, as a list."""
    at = source.rfind(HEADER)
    assert at >= 0, source[-300:]
    return [line for line in source[at:].splitlines() if line.strip()]


# --- the lines themselves ---------------------------------------------------

def test_the_header_goes_at_the_end_and_keeps_the_script():
    src = "(function () {\n  var a = 1;\n})();"
    out = shields.limited(src)
    assert out.startswith(src)                     # the same lines, the same numbers in a stack
    assert header_of(out) == ["// ==UserScript==", "// @exclude chrome-error://*", "// ==/UserScript=="]
    out = shields.limited(src, shields.host_globs("www.example.test") + list(shields.EMPTY_FRAMES))
    assert header_of(out) == [
        "// ==UserScript==",
        "// @include *://www.example.test/*", "// @include *://www.example.test:*/*",
        "// @include *://*@www.example.test/*", "// @include *://*@www.example.test:*/*",
        "// @include about:blank*", "// @include about:srcdoc*",
        "// @exclude chrome-error://*", "// ==/UserScript=="]
    assert {"*://youtube.com/*", "*://*.youtube.com/*", "*://*.youtube.com:*/*"} <= set(
        shields.host_globs("youtube.com", subdomains=True))
    assert not any("*." in g for g in shields.host_globs("youtube.com"))


# --- in the engine ----------------------------------------------------------

PAGE = """<!doctype html><title>%(host)s</title><head><script>
window.__probes = window.__probes || [];
window.addEventListener('message', function (e) {
  if (e.data && e.data.ikeProbe) window.__probes.push(e.data.ikeProbe);
});
</script></head><body>
<iframe src="/frame"></iframe>
<iframe src="about:blank"></iframe>
<iframe srcdoc="<p>srcdoc</p>"></iframe>
<iframe src="http://tracker.test:%(port)d/ad"></iframe>
%(embed)s
</body>"""


@pytest.fixture
def sites():
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            host = (self.headers.get("Host") or "").split(":")[0]
            port = self.server.server_address[1]
            if self.path.startswith("/page"):
                embed = ('<iframe src="http://www.youtube-nocookie.com:%d/embed/x"></iframe>' % port
                         if "embed" in self.path else "")
                body = PAGE % {"host": host, "port": port, "embed": embed}
            else:
                body = "<!doctype html><p>%s %s</p>" % (host, self.path)
            data = body.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):
            pass
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1]
    srv.shutdown()


HOSTS = ["www.example.test", "other.test", "tracker.test", "www.youtube.com", "m.youtube.com",
         "music.youtube.com", "youtube.com", "www.youtube-nocookie.com"]
FILTERS = ("||tracker.test^\n"                     # a frame of another company, blocked
           "youtube.com##+js(set-constant, ikeTestYT, true)\n"
           "youtube-nocookie.com##+js(set-constant, ikeTestYT, true)\n"
           "www.example.test##+js(set-constant, ikeTestSL, true)\n")

STEPS = r'''
import json
from PyQt6.QtCore import QUrl
from PyQt6.QtWebEngineCore import QWebEngineScript

P = %d
NAMES = ("content", "content-2", "ike-consent", "ike-sl-main:www.example.test", "ike-video-main",
         "ike-video-iso", "ike-videoads", "ike-video-relay")
HEADER = "\n// ==UserScript=="


def load(view, url):
    done = {}
    view.loadFinished.connect(lambda ok: done.setdefault("ok", ok))
    view.load(QUrl(url))
    for _ in range(300):
        if "ok" in done:
            break
        yield 20
    yield 1200


def js(runner, code, world=0):
    res = {}
    runner.runJavaScript(code, world, lambda r: res.setdefault("r", r))
    for _ in range(250):
        if "r" in res:
            break
        yield 20
    return res.get("r")


def probe(name, header, subframes=True):
    s = QWebEngineScript()
    s.setName("probe|" + name)
    body = ("(function () { var r = %%s + '|' + location.href;"
            " if (window.top === window) (window.__probes = window.__probes || []).push(r);"
            " else try { parent.postMessage({ikeProbe: r}, '*'); } catch (e) {} })();" %% json.dumps(name))
    s.setSourceCode(body + header)
    s.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
    s.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
    s.setRunsOnSubFrames(subframes)
    return s


def steps(ike, qapp, out):
    win = ike.windows[0]
    view = win.current_view()
    yield 500
    # the site's scriptlets are installed when its page is asked for
    yield from load(view, "http://www.example.test:%%d/first" %% P)
    scripts = ike.profile.scripts()
    found = {}
    for name in NAMES:
        got = scripts.find(name)
        if got:
            src = got[0].sourceCode()
            found[name] = [src[src.rfind(HEADER):] if HEADER in src else "", got[0].runsOnSubFrames()]
    out["headers"] = found
    # a probe for each kind of limit, and one without any (the control)
    for name, (header, subframes) in found.items():
        scripts.insert(probe(name, header, subframes))
    scripts.insert(probe("control", ""))
    pages = {}
    for host, path in (("www.example.test", "/page"), ("other.test", "/page-embed"), ("www.youtube.com", "/page"),
                       ("m.youtube.com", "/page"), ("music.youtube.com", "/page"), ("youtube.com", "/page")):
        yield from load(view, "http://%%s:%%d%%s" %% (host, P, path))
        yield 600
        probes = json.loads((yield from js(view.page(), "JSON.stringify(window.__probes || [])")) or "[]")
        real = {"yt_main": (yield from js(view.page(), "String(window.ikeTestYT)")),
                "sl_main": (yield from js(view.page(), "String(window.ikeTestSL)")),
                "videoads": (yield from js(view.page(), "String(window.__ikeVideoAds)", 1))}
        # the real scripts' own effects in each frame (QWebEngineFrame, Qt 6.8)
        frames = {}
        main = view.page().mainFrame() if hasattr(view.page(), "mainFrame") else None
        for f in (main.children() if main is not None else []):
            u = f.url().toString()
            if u.startswith("chrome-error:") or "tracker.test" in u:      # the blocked frame
                continue
            frames[u] = {"yt_main": (yield from js(f, "String(window.ikeTestYT)")),
                         "sl_main": (yield from js(f, "String(window.ikeTestSL)")),
                         "videoads": (yield from js(f, "String(window.__ikeVideoAds)", 1))}
        pages[host] = {"probes": probes, "real": real, "frames": frames}
    out["pages"] = pages
'''


def _where(probes, name):
    """Where the probe `name` ran: "top", "frame", "blank", "srcdoc", "error", "embed"."""
    out = set()
    for p in probes:
        n, _, url = p.partition("|")
        if n != name:
            continue
        if url.startswith("chrome-error:"):
            out.add("error")
        elif url.startswith("about:blank"):
            out.add("blank")
        elif url.startswith("about:srcdoc"):
            out.add("srcdoc")
        elif "/embed/" in url:
            out.add("embed")
        elif url.endswith("/frame"):
            out.add("frame")
        else:
            out.add("top")
    return out


@needs_engine
def test_scripts_run_where_they_should(run_ike, sites):
    rules = ", ".join("MAP %s 127.0.0.1" % h for h in HOSTS)
    env = dict(NO_PROXY_ENV, QTWEBENGINE_CHROMIUM_FLAGS='--no-sandbox "--host-resolver-rules=%s"' % rules)
    out = run_ike(STEPS % sites, env=env, timeout=180,
                  settings={"https_only": False, "custom_filters": FILTERS, "video_ad_skip": True})
    headers = {k: v[0] for k, v in out["headers"].items()}
    # every script is there and never runs in an error page
    for name in ("content", "content-2", "ike-consent", "ike-sl-main:www.example.test", "ike-video-main",
                 "ike-videoads", "ike-video-relay"):
        assert name in headers and "// @exclude chrome-error://*" in headers[name], (name, headers)
    assert "@include" not in headers["content"] + headers["content-2"] + headers["ike-consent"]
    assert "@include" not in headers["ike-video-relay"]          # the top page of any site
    everywhere = {"top", "frame", "blank", "srcdoc"}
    empty = {"blank", "srcdoc"}
    pages = out["pages"]
    ex = pages["www.example.test"]["probes"]
    # the control shows that the blocked frame's error page runs profile scripts
    assert _where(ex, "control") == everywhere | {"error"}, ex
    for name in ("content", "content-2", "ike-consent"):
        assert _where(ex, name) == everywhere, (name, ex)
    # the site's scriptlets: its own page, frames, empty and srcdoc frames
    assert _where(ex, "ike-sl-main:www.example.test") == everywhere, ex
    assert pages["www.example.test"]["real"]["sl_main"] == "true"
    for name in ("ike-video-main", "ike-videoads"):
        # an empty frame has no address of its own: the scripts of a site are
        # still given to it, and stop at once (their check of the host)
        assert _where(ex, name) <= empty, (name, ex)
    # another site: no scriptlet of www.example.test and no video script in
    # its page or its own frames; the embedded player gets the video scripts
    other = pages["other.test"]["probes"]
    assert _where(other, "control") == everywhere | {"error", "embed"}, other
    assert _where(other, "content") == everywhere | {"embed"}, other
    assert _where(other, "ike-sl-main:www.example.test") <= empty, other
    assert _where(other, "ike-video-main") - empty == {"embed"}, other
    assert _where(other, "ike-videoads") == {"embed"}, other
    assert _where(other, "ike-video-relay") == {"top"}, other
    real = pages["other.test"]["real"]
    assert real == {"yt_main": "undefined", "sl_main": "undefined", "videoads": "undefined"}, real
    frames = pages["other.test"]["frames"]
    for url, got in frames.items():
        want = ({"yt_main": "true", "sl_main": "undefined", "videoads": "true"} if "/embed/" in url
                else {"yt_main": "undefined", "sl_main": "undefined", "videoads": "undefined"})
        assert got == want, (url, got)
    if frames:                                         # QWebEngineFrame: Qt 6.8 and later
        assert any("/embed/" in u for u in frames), frames
    # www.example.test's frames: its scriptlet runs in the same host's frames
    for url, got in pages["www.example.test"]["frames"].items():
        assert got["sl_main"] == "true" and got["yt_main"] == "undefined", (url, got)
    # the video sites: as before, in the page, its frames and its empty frames
    # (the player's fallback in documents of the sites, as its own check says)
    for host in ("www.youtube.com", "m.youtube.com", "music.youtube.com", "youtube.com"):
        probes = pages[host]["probes"]
        assert _where(probes, "ike-video-main") == everywhere, (host, probes)
        assert _where(probes, "ike-videoads") == {"top", "frame"}, (host, probes)
        assert "error" in _where(probes, "control"), (host, probes)
        assert pages[host]["real"] == {"yt_main": "true", "sl_main": "undefined", "videoads": "true"}, \
            (host, pages[host]["real"])
        for url, got in pages[host]["frames"].items():
            assert got["yt_main"] == "true", (host, url, got)
            assert got["videoads"] == ("undefined" if url.startswith("about:") else "true"), (host, url, got)
