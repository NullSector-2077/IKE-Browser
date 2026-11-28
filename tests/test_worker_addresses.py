"""Inline workers keep the protection whatever their address looks like (1.1.31).

Found by the independent review of the Trusted Types change (older than it):
- an address the engine takes but the protection did not see as blob: or
  data: (' blob:...', 'BLOB:...', ' data:...') started the worker without the
  protection, in a page and in a worker inside a worker;
- a blob address made in another frame, whose text the page cannot read (a
  policy whose connect-src leaves blob: out), started as asked, without it.
Now the address is read as the engine reads it, and a blob the protection
cannot read is started from the protection, which then loads it.

Each worker draws the same picture as the page; with the protection in it the
picture carries the page's noise (a data: worker has a seed of its own:
another noise, never none). The shield off gives the engine's own picture.

SIMULATION: a local server; "nocsp" has no policy, "noconnect" a policy that
lets no address be read (connect-src 'none').
"""

import http.server
import json
import threading

import pytest
from test_trusted_types_workers import COMMON

PAGE = r"""<!doctype html><title>w</title><body><script>
""" + COMMON + r"""
function nested(prefix) {
  // a worker that starts a worker of its own from such an address
  var inner = 'var u = URL.createObjectURL(new Blob([' + JSON.stringify(WORKER) + ']));' +
    'var n = new Worker(' + JSON.stringify(prefix) + ' + u.slice(5)); n.onmessage = function (e) { postMessage(e.data); };' +
    'n.onerror = function () { postMessage({}); };';
  return new Worker(URL.createObjectURL(new Blob([inner], { type: 'text/javascript' })));
}
window.__run = async function () {
  var out = { page: 'pic:' + draw(new OffscreenCanvas(96, 40)) };
  out.space = await start(function () { return new Worker(' ' + blobUrl()); });
  out.upper = await start(function () { return new Worker('BLOB:' + blobUrl().slice(5)); });
  out.dataSpace = await start(function () { return new Worker(' data:text/javascript,' + encodeURIComponent(WORKER)); });
  out.nestedSpace = await start(function () { return nested(' blob:'); });
  out.nestedUpper = await start(function () { return nested('BLOB:'); });
  // a blob address made in a frame of the page, used by the page
  var f = document.createElement('iframe');
  document.body.appendChild(f);
  var foreign = f.contentWindow.URL.createObjectURL(new f.contentWindow.Blob([WORKER], { type: 'text/javascript' }));
  out.foreign = await start(function () { return new Worker(foreign); });
  return out;
};
</script></body>"""

PAGES = {"/nocsp.html": None, "/noconnect.html": "connect-src 'none'"}


@pytest.fixture
def site():
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            path = self.path.split("?")[0]
            if path not in PAGES:
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            body = PAGE.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            if PAGES[path]:
                self.send_header("Content-Security-Policy", PAGES[path])
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1]
    srv.shutdown()


def run(run_ike, port, level):
    from test_trusted_types_workers import STEPS
    pages = [("nocsp", "http://127.0.0.1:%d/nocsp.html"), ("noconnect", "http://127.0.0.1:%d/noconnect.html")]
    out = run_ike("PAGES = %r\n" % [(k, u % port) for k, u in pages] + STEPS,
                  settings={"shield_level": level}, timeout=200)
    return {k: json.loads(out[k]) for k, _ in pages}


@pytest.mark.parametrize("level", ["balanced", "strict", "maximum"])
def test_inline_workers_keep_the_protection_whatever_their_address(run_ike, site, level):
    real = run(run_ike, site, "off")["nocsp"]["page"]
    got = run(run_ike, site, level)
    for key, r in got.items():
        assert r["page"] != real, (level, key, r, real)
        for w in ("space", "upper", "nestedSpace", "nestedUpper"):
            assert r[w] == r["page"], (level, key, w, r)
        # a data: worker has a seed of its own: another noise, never none
        assert r["dataSpace"].startswith("pic:") and r["dataSpace"] != real, (level, key, r)
        # a blob of a frame of the page: protected, read or not
        assert r["foreign"] == r["page"], (level, key, r)
