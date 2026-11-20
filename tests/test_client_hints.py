"""Chrome's version in the client hints a site asks for (1.1.18, owner's
decision): at Strict and Maximum JavaScript gives the reduced version
(140.0.0.0) and the headers say the same; at Balanced both carry the engine's
real full version, as before. Only hints the engine sends are changed: a site
that asked for none gets none.

SIMULATION: a local server that asks for the full-version hints (Accept-CH)
and records what the next requests carry.
"""

import http.server
import threading

import pytest

PAGE = b"""<!doctype html><title>hints</title><body><script>
navigator.userAgentData.getHighEntropyValues(['uaFullVersion', 'fullVersionList']).then(function (v) {
  window.js = JSON.stringify([v.uaFullVersion, v.fullVersionList.map(function (b) { return b.version; })]);
});
fetch('/sub?' + Math.random());
</script></body>"""


@pytest.fixture
def site():
    seen = []

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            hints = {k.lower(): v for k, v in self.headers.items() if k.lower().startswith("sec-ch-ua")}
            seen.append((self.headers.get("Host", "").split(":")[0], self.path.split("?")[0], hints))
            body = PAGE if self.path.startswith(("/ask", "/plain")) else b"ok"
            self.send_response(200)
            if self.path.startswith("/ask"):
                self.send_header("Accept-CH", "Sec-CH-UA-Full-Version, Sec-CH-UA-Full-Version-List")
            self.send_header("Content-Type", "text/html" if body is PAGE else "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1], seen
    srv.shutdown()


STEPS = r'''
from PyQt6.QtCore import QUrl
from PyQt6.QtWebEngineCore import qWebEngineChromiumVersion

def steps(ike, qapp, out):
    view = ike.windows[0].current_view()
    out["engine"] = qWebEngineChromiumVersion()
    # the second load carries the hints asked for; localhost is another site, which asked for none
    for path in ("127.0.0.1:%d/ask", "127.0.0.1:%d/ask", "localhost:%d/plain"):
        done = {}
        view.page().loadFinished.connect(lambda ok, d=done: d.setdefault("ok", ok))
        view.load(QUrl("http://" + path))
        while "ok" not in done:
            yield 20
        res = {}
        for _ in range(100):
            view.page().runJavaScript("window.js || ''", 0, lambda r, res=res: res.__setitem__("r", r))
            while "r" not in res:
                yield 20
            if res.pop("r"):
                break
            yield 50
        yield 500
    view.page().runJavaScript("window.js", 0, lambda r: out.__setitem__("js", r))
    while "js" not in out:
        yield 20
'''


@pytest.mark.parametrize("level", ["balanced", "strict", "maximum"])
def test_the_version_in_the_client_hints(run_ike, site, level):
    import json
    port, seen = site
    out = run_ike(STEPS % (port, port, port), settings={"shield_level": level}, timeout=120)
    full, major = out["engine"], out["engine"].split(".")[0]
    want = full if level == "balanced" else major + ".0.0.0"
    asked = [h for host, p, h in seen if host == "127.0.0.1" and "sec-ch-ua-full-version" in h]
    assert len(asked) >= 2, seen                         # the engine sent the hints the site asked for
    assert not [h for host, p, h in seen if host == "localhost" and "sec-ch-ua-full-version" in h], seen
    for h in asked:
        assert h["sec-ch-ua-full-version"] == '"%s"' % want, (level, h)
        assert '"Chromium";v="%s"' % want in h["sec-ch-ua-full-version-list"], (level, h)
    js = json.loads(out["js"])
    assert js[0] == want and want in js[1], (level, js)          # the same as JavaScript
