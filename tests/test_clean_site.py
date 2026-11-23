""""Clear this site's data" (the cleansite button) tells what went (1.1.24): the cookies,
the site's storage (local and session storage, databases, service workers), its caches,
and the permissions it keeps, counted by the clean itself in I.K.E.'s own script world."""

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from test_security import JS


@pytest.fixture
def store_site():
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            body = b"<!doctype html><title>store</title><body>page"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Set-Cookie", "one=1; Path=/")
            self.send_header("Set-Cookie", "two=2; Path=/")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield "http://127.0.0.1:%d/" % srv.server_address[1]
    srv.shutdown()


def test_the_clean_says_what_it_removed(run_ike, store_site):
    """The server sets its two cookies again in every answer (the page, its icon): the
    engine then reports them removed and never added back, and until 1.1.24 the clean
    left them. Now both go, and the summary counts them."""
    out = run_ike(JS + r'''
SITE = %r

def steps(ike, qapp, out):
    from PyQt6.QtWidgets import QMessageBox
    from ike import window
    win = ike.windows[0]
    view = win.current_view()
    yield from load(view, SITE)
    yield from js(view, """window._done = false; (async function () {
        localStorage.setItem('a', '1'); localStorage.setItem('b', '2'); sessionStorage.setItem('c', '3');
        await new Promise(function (ok) { var q = indexedDB.open('ikedb', 1);
            q.onupgradeneeded = function () { q.result.createObjectStore('s'); };
            q.onsuccess = function () { q.result.close(); ok(); }; q.onerror = ok; });
        await caches.open('ike-cache');
        window._done = true; })(); 1""")
    for _ in range(50):
        if (yield from js(view, "window._done")):
            break
        yield 100
    yield 500
    seen = []
    real = win.site_cleaned
    win.site_cleaned = lambda *a: (seen.append(list(a)), real(*a))
    window.QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
    win.clear_site_data()
    for _ in range(60):
        yield 100
        if seen:
            break
    out["cookie_now"] = yield from js(view, "document.cookie")       # before the page loads again
    box = getattr(win, "_cleaned_box", None)
    out["summary"] = seen
    out["box"] = [box.text(), box.informativeText()] if box is not None else None
    # the page never saw I.K.E.'s counter (another script world)
    out["page_saw"] = yield from js(view, "typeof window.__ikeCleaned")
    if box is not None:
        box.close()
    yield 1500
    out["after"] = yield from js(view, "[localStorage.length, sessionStorage.length]")
''' % store_site, timeout=120)
    assert out["summary"] == [["127.0.0.1", 2, 4, 1, []]], out["summary"]
    assert out["box"] == ["Data of 127.0.0.1 deleted.", "Cookies: 2\nSite storage: 4\nCache: 1"], out["box"]
    assert out["page_saw"] == "undefined"
    assert out["after"] == [0, 0] and out["cookie_now"] == ""
