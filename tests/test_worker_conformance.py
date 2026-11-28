"""The protected workers behave as the engine's own (1.1.32, the owner's brief
3.1): tests/compat/webtech/conformance.html in I.K.E. at Kontrol, with the
site's policy allowing blob: workers (the protected copy, the queue until its
hello) and refusing them (the site's own file taking the copy's place inside
the same object), against the same page in Chrome for Testing 140.0.7339.207
(conformance-chrome140.json, recorded with tests/compat/README.md's runner).

Order of 100 messages posted at once, the message event's fields, buffers
transferred (as a list and as {transfer}) and detached at once, a
MessagePort, an OffscreenCanvas, a clone made at the moment of posting, the
clone and transfer errors in the engine's words and kind, terminate() right
after posting, a listener set late, both listeners, an error in the worker,
a nested worker, a module worker, five at once, a missing file.

Known differences, kept on purpose and written down (docs/SECURITY.md): the
site's file is loaded by the protected worker itself, so the "error" of a
worker whose file is missing is I.K.E.'s copy of the engine's (isTrusted
false); in the fallback (a policy without blob:) the first worker's events
reach the page re-dispatched from the site's own worker (isTrusted false
too), and the document's further workers start from the site's file
directly.
"""

import http.server
import json
import threading
from functools import partial
from pathlib import Path

import pytest

WEBTECH = Path(__file__).resolve().parent / "compat" / "webtech"
CHROME = json.loads((WEBTECH / "conformance-chrome140.json").read_text("utf-8"))


@pytest.fixture
def site():
    class H(http.server.SimpleHTTPRequestHandler):
        extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, ".js": "text/javascript"}

        def end_headers(self):
            if "csp=noblob" in self.path:
                self.send_header("Content-Security-Policy", "worker-src 'self'; script-src 'self' 'unsafe-inline'")
            super().end_headers()

        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), partial(H, directory=str(WEBTECH)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1]
    srv.shutdown()


STEPS = r'''
import json
from PyQt6.QtCore import QUrl

def steps(ike, qapp, out):
    view = ike.windows[0].current_view()
    for key, q in (("plain", ""), ("noblob", "?csp=noblob")):
        done = {}
        view.page().loadFinished.connect(lambda ok, d=done: d.setdefault("ok", ok))
        view.load(QUrl("http://localhost:%d/conformance.html" + q))
        while "ok" not in done:
            yield 20
        for _ in range(600):
            res = {}
            view.page().runJavaScript("window.result || ''", 0, lambda r, res=res: res.__setitem__("r", r))
            while "r" not in res:
                yield 20
            if res["r"]:
                out[key] = json.loads(res["r"])
                break
            yield 100
'''

# the differences kept on purpose (see above): isTrusted only
KNOWN = {("plain", "missing"): ["Event", False], ("noblob", "missing"): ["Event", False],
         ("noblob", "event"): [False] + CHROME["event"][1:]}


@pytest.mark.parametrize("level", ["strict", "maximum"])
def test_the_queue_matches_chrome_140(run_ike, site, level):
    out = run_ike(STEPS % site, settings={"shield_level": level, "https_only": False}, timeout=200)
    # Maximum (2026-11-28): a policy without blob: workers leaves the site's
    # file unprotected, so it is refused there; only the protected copy is compared
    for key in ("plain", "noblob") if level == "strict" else ("plain",):
        got = out[key]
        for name, want in CHROME.items():
            if got[name] == KNOWN.get((key, name)):
                continue
            assert got[name] == want, (key, name, got[name], want)
