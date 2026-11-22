"""A window closed while its download is under way (1.1.21): the language
packs window wrote its "could not load" text to a label already deleted,
an error inside the browser (seen in CI's run of the installed package)."""

import http.server
import threading
import time

STEPS = r'''
def steps(ike, qapp, out):
    from ike.dialogs import LanguageDownloadDialog
    w = ike.windows[0]
    ike.config["lang_url"] = URL
    for _ in range(3):
        d = LanguageDownloadDialog(ike, w)
        d.show()
        yield 100
        d.close()
        d.deleteLater()
        yield 50
    yield 2500                      # the slow answers arrive after the windows are gone
    out["done"] = True
'''


def test_language_window_closed_while_its_list_downloads(run_ike):
    class Slow(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            time.sleep(1.0)
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Slow)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        url = "http://127.0.0.1:%d/lang" % srv.server_address[1]
        out = run_ike("URL = %r\n" % url + STEPS, timeout=60)
    finally:
        srv.shutdown()
    assert out["done"], out
