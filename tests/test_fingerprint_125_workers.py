"""Workers a site starts from a file of its own, and the review of 1.1.25
(the independent adversarial review, rounds 2 and 3; its probes are in
tests/data/fingerprint-125/: p.html to p5.html and their workers).

At Strict and Maximum (the global level, or a site set to Strict by itself) a
dedicated worker from a file of the site, classic or module, nested in a
worker, in a frame of another site, gets the same protection as the page:
it is started from a blob address holding the protection and then runs the
site's script, with its real address (location, relative addresses, errors).
Where that cannot be done (a content security policy that refuses blob
workers) the worker is refused, as when its script cannot be fetched: it
never runs without the protection. Balanced is unchanged.

Also checked here: no change of a plain colour in WebGL reads, putImageData
read back exactly, text widths that do not depend on a missing font's name.

SIMULATION: a local server with the review's probe pages (127.0.0.1 and
localhost are two sites, both secure contexts).
"""

import http.server
import json
import threading
import time
from pathlib import Path

import pytest

DATA = Path(__file__).resolve().parent / "data" / "fingerprint-125"
GL_FLAGS = "--no-sandbox --enable-unsafe-swiftshader --use-angle=swiftshader --ignore-gpu-blocklist"


@pytest.fixture
def site():
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            path = self.path.split("?")[0].lstrip("/") or "p.html"
            if path == "slow.js":                     # a worker's script that takes 0.7 s to come
                time.sleep(0.7)
                path = "w4.js"
            f = DATA / path
            if "/" in path or not f.is_file():
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            body = f.read_bytes()
            self.send_response(200)
            kind = "text/html; charset=utf-8" if path.endswith(".html") else (
                "text/plain" if path.endswith(".txt") else "text/javascript")
            self.send_header("Content-Type", kind)
            if path == "csp.html":
                self.send_header("Content-Security-Policy", "worker-src 'self'")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1]
    srv.shutdown()


STEPS = r'''
from PyQt6.QtCore import QUrl

def steps(ike, qapp, out):
    view = ike.windows[0].current_view()
    for key, url in PAGES:
        done = {}
        view.page().loadFinished.connect(lambda ok, d=done: d.setdefault("ok", ok))
        view.load(QUrl(url))
        while "ok" not in done:
            yield 20
        yield 300
        view.page().runJavaScript("window.result = null; window.__run().then(function (r) { window.result = "
                                  "JSON.stringify(r); }, function (e) { window.result = JSON.stringify('ERR ' + e); }); 1",
                                  0, lambda r: None)
        for _ in range(1800):
            res = {}
            view.page().runJavaScript("window.result || ''", 0, lambda r, res=res: res.__setitem__("r", r))
            while "r" not in res:
                yield 20
            if res["r"]:
                out[key] = res["r"]
                break
            yield 100
'''


def run(run_ike, port, pages, level, sites=None, gl=True):
    settings = {"shield_level": level}
    if sites:
        settings["site_levels"] = sites
    script = "PAGES = %r\n" % [(k, u % port) for k, u in pages] + STEPS
    out = run_ike(script, settings=settings, env={"QTWEBENGINE_CHROMIUM_FLAGS": GL_FLAGS} if gl else None,
                  timeout=400)
    return {k: json.loads(out[k]) for k, u in pages}


def differ(a, b):
    """The values that tell a computer, as a fingerprinting script reads them:
    the names of those that differ between a and b."""
    def gl(o, kind):
        x = (o.get("gl") or {}).get(kind)
        if not isinstance(x, dict):
            return {"gl": x}
        return {kind + ".id": x["id"], kind + ".exts": x["exts"], kind + ".params": {k: v for k, v in x["params"].items()        # the limits (not the canvas's size)
                                                            if k.startswith(("MAX_", "MIN_", "ALIASED_", "SUBPIXEL", "UNIFORM_"))},
                kind + ".aniso": x.get("aniso"), kind + ".prec": x["prec"], kind + ".hidden": x["hiddenExt"],
                kind + ".flatBad": x["behave"]["flatBad"]}
    def pick(o):
        d = {k: o.get(k) for k in ("hc", "dm", "lang", "langs", "brands", "he", "net", "putRoundTripDiff", "gpu")}
        d.update(gl(o, "webgl"))
        d.update(gl(o, "webgl2"))
        return d
    pa, pb = pick(a), pick(b)
    return {k: (pa.get(k), pb.get(k)) for k in set(pa) | set(pb) if pa.get(k) != pb.get(k)}


@pytest.mark.parametrize("level", ["strict", "maximum", "site-strict"])
def test_workers_from_files_are_protected(run_ike, site, level):
    sites = None
    host = "localhost"
    if level == "site-strict":                       # a site set to Strict by itself, Balanced elsewhere
        level, sites = "balanced", {"localhost": "strict", "127.0.0.1": "strict"}
    r = run(run_ike, site, [("p", "http://%s:%%d/p.html" % host)], level, sites)["p"]
    page = r["window"]
    assert page["he"]["uaFullVersion"].endswith(".0.0.0") and page["net"][:3] == ["4g", 50, 10], page
    assert page["gl"]["webgl"]["id"][4:] == [None, None], page["gl"]["webgl"]["id"]     # no card name
    places = {"file": r["workers"]["file"], "fileModule": r["workers"]["fileModule"],
              "fileNestedBlob": r["workers"]["fileNestedBlob"], "blobNestedFile": r["workers"]["blobNestedFile"],
              "crossSiteFrame.file": r["frames"]["crossSite"]["fileWorker"],
              "sameSiteFrame.file": r["frames"]["sameSite"]["fileWorker"], "blob": r["workers"]["blob"]}
    bad = {k: (v if not isinstance(v, dict) else differ(v, page)) for k, v in places.items()}
    bad = {k: v for k, v in bad.items() if v}
    assert not bad, (level, json.dumps(bad)[:3000])
    # a shared worker from a file and a service worker: still not started
    assert r["workers"]["sharedFile"] == "ERR error event", r["workers"]["sharedFile"]
    assert r["sw"]["reg"].startswith("ERR TypeError"), r["sw"]


def test_balanced_workers_from_files_are_unchanged(run_ike, site):
    r = run(run_ike, site, [("p", "http://localhost:%d/p.html")], "balanced")["p"]
    assert r["sw"]["reg"] == "ok"
    for k in ("file", "fileModule", "fileNestedBlob"):
        v = r["workers"][k]
        assert isinstance(v, dict) and v["he"]["uaFullVersion"] == r["window"]["he"]["uaFullVersion"], (k, v)


def test_file_workers_keep_their_own_address(run_ike, site):
    pages = [("w", "http://localhost:%d/w.html")]
    off = run(run_ike, site, pages, "off", gl=False)["w"]
    got = run(run_ike, site, pages, "strict", gl=False)["w"]
    rel = got["rel"]
    assert isinstance(rel, dict), rel
    # relative addresses, the location, nested workers: as the site's own file
    assert (rel["loc"], rel["fetch"], rel["request"], rel["xhr"]) == \
        (off["rel"]["loc"], off["rel"]["fetch"], off["rel"]["request"], off["rel"]["xhr"]), (rel, off["rel"])
    assert rel["fetch"] == "relative ok" and rel["loc"][0].endswith("/relwk.js"), rel
    assert isinstance(rel["nested"], dict) and rel["nested"]["net"][:3] == ["4g", 50, 10], rel["nested"]
    assert rel["info"]["net"][:3] == ["4g", 50, 10] and rel["info"]["he"]["uaFullVersion"].endswith(".0.0.0"), rel["info"]
    # errors read as before: a syntax error, an exception, a missing script
    assert got["bad"] == off["bad"] and got["thrower"] == off["thrower"], (got, off)
    assert got["missing"] == off["missing"] == ["Event", "error"], (got, off)


@pytest.mark.parametrize("level", ["strict", "balanced"])
def test_a_policy_against_blob_workers(run_ike, site, level):
    """worker-src 'self' refuses the blob address: at Strict the worker is
    refused (never started from the file without the protection); Balanced
    starts it as before."""
    got = run(run_ike, site, [("c", "http://localhost:%d/csp.html")], level, gl=False)["c"]
    if level == "strict":
        assert got["got"] == "Event", got
    else:
        assert got["got"] == "data", got


def test_known_answers(run_ike, site):
    """The review's known-answer probes (p2.html, p3.html) at Strict, against
    the engine with the shield off: solid rectangles, the page's own pixels,
    a flat canvas copied, a plain WebGL colour, all read back exactly; the
    noise is still there (text) and the same in a file worker, an inline
    worker and the page."""
    pages = [("p2", "http://localhost:%d/p2.html"), ("p3", "http://localhost:%d/p3.html")]
    off = run(run_ike, site, pages, "off")
    got = run(run_ike, site, pages, "strict")
    t = got["p2"]["tests"]
    for k in ("fillRectOnly", "afterSaveRestore", "afterTranslate0", "rgbSyntax", "drawImageOfFlat", "putImageData"):
        assert t[k] == 0, (k, t[k])
    assert t["stripes1px"].startswith("0 of"), t["stripes1px"]
    for k in ("glFlat_webgl", "glFlat_webgl2"):
        assert t[k] == "0 of 65536", (k, t[k])
    assert got["p3"]["flatColoursWrong"] == "0 of 64", got["p3"]
    assert got["p3"]["putRandomChangedPixels"] == "0 of 16384" and got["p3"]["rereadChangedBytes"] == 0, got["p3"]
    fw, bw, win = got["p2"]["fileWorker"], got["p2"]["blobWorker"], got["p2"]["windowSame"]
    real = off["p2"]["fileWorker"]
    assert fw["fonts"] == bw["fonts"] == win["fonts"], (fw, bw, win)
    assert fw["canvasHash"] == fw["canvasHash2"] == bw["canvasHash"] == win["canvasHash"], (fw, bw, win)
    assert fw["canvasHash"] != real["canvasHash"], (fw, real)         # the noise, in the file worker too
    assert "NoSuchFont123" not in fw["fonts"], fw["fonts"]               # a missing font measures as the fallback


def test_missing_fonts_measure_the_same(run_ike, site):
    """Text width noise keyed on the real width (not on the font's name): two
    fonts that are not there measure the same, as in Chrome, in the page and
    in a worker; a real width still changes."""
    probe = r'''
    window.__run = async function () {
      function m(x) { x.font = '20px NoSuchFontA, monospace'; var a = x.measureText('Hello').width;
        x.font = '20px NoSuchFontB, monospace'; var b = x.measureText('Hello').width;
        x.font = '20px monospace'; return [a, b, x.measureText('Hello').width]; }
      var page = m(document.createElement('canvas').getContext('2d'));
      var src = "var x = new OffscreenCanvas(4, 4).getContext('2d'); " + m.toString() + " postMessage(m(x));";
      var w = await new Promise(function (ok) { var k = new Worker(URL.createObjectURL(new Blob([src], {type: 'text/javascript'})));
        k.onmessage = function (e) { ok(e.data); }; });
      return {page: page, worker: w};
    };'''
    (DATA / "measure.html").write_text("<!doctype html><script>%s</script>" % probe, "utf-8")
    try:
        off = run(run_ike, site, [("m", "http://localhost:%d/measure.html")], "off", gl=False)["m"]
        got = run(run_ike, site, [("m", "http://localhost:%d/measure.html")], "strict", gl=False)["m"]
    finally:
        (DATA / "measure.html").unlink()
    for where in ("page", "worker"):
        a, b, c = got[where]
        assert a == b == c, (where, got)                     # no font: the fallback's width, for every name
        assert a != off[where][0], (where, got, off)         # the noise is there
    assert got["page"] == got["worker"], got



def test_file_workers_start_like_the_engine(run_ike, site):
    """The review of 1.1.25, round 3 (its probes p4.html and p5.html), at
    Strict against the engine with the shield off: a message posted right
    after a module worker is made is answered (it was lost); a worker whose
    script is slow to come does not stop the page (the page waited for it);
    a classic worker keeps "use strict", its address, its name and its first
    stack frame; a script that throws, a missing one, a classic worker given
    a module, a URL object, an error raised later: the same events as the
    engine's, with the site's address, never the protection's blob address.
    A policy against blob workers: the worker is refused with no report
    naming the protection. A text file is refused (the engine runs it)."""
    pages = [("p4", "http://localhost:%d/p4.html"), ("p5", "http://localhost:%d/p5.html")]
    off = run(run_ike, site, pages, "off")
    got = run(run_ike, site, pages, "strict")
    assert got["p5"] == off["p5"], (got["p5"], off["p5"])
    assert got["p5"]["moduleImmediateMsg"][-1].startswith("got early"), got["p5"]
    a, b = got["p4"], off["p4"]
    assert a["slowCtor"]["ctorMs"] < 300, a["slowCtor"]                  # the page does not wait for the file
    for k in ("throwing", "missing", "classicAsModuleSyntax", "urlObj", "selfErr"):
        assert a[k].get("error") == b[k].get("error"), (k, a[k], b[k])
        assert k == "selfErr" or a[k].get("data") == b[k].get("data"), (k, a[k], b[k])
    assert a["selfErr"]["data"] == b["selfErr"]["data"], (a["selfErr"], b["selfErr"])
    for k in ("classic", "slowCtor"):
        x, y = a[k]["data"], b[k]["data"]
        for f in ("strict", "href", "locStr", "origin", "name", "ctor"):
            assert x[f] == y[f], (k, f, x[f], y[f])
        assert x["strict"] == "strict ok", x
        assert x["stack"].split(" | ")[0] == y["stack"].split(" | ")[0], (x["stack"], y["stack"])
        assert x["entries"] == y["entries"] == [], (x, y)       # its own script is not in its timeline
    x, y = a["module"]["data"], b["module"]["data"]
    for f in ("tag", "meta", "href", "stack", "name", "got"):
        assert x[f] == y[f], (f, x[f], y[f])
    assert a["csp"]["violations"] == [] and a["csp"]["worker"].startswith("ERROR"), a["csp"]
    assert b["csp"]["worker"]["href"].endswith("/rel-worker.js"), b["csp"]
    assert b["plainMime"]["data"] == "RAN from text/plain", b["plainMime"]
    assert "data" not in a["plainMime"] and a["plainMime"]["error"] == [None] * 4, a["plainMime"]
    assert "userscript" not in json.dumps(got) and "blob:" not in json.dumps(
        {k: v for k, v in a.items() if k not in ("classic", "slowCtor")}), got


def test_a_sandboxed_frame_gets_no_worker_from_a_file(run_ike, site):
    """A sandboxed frame has an opaque origin: the engine refuses a worker
    from a file there (SecurityError); at Strict too (review round 3: the
    protection compared the address with location.origin and started it). A
    frame of the site's own starts it, protected, as before."""
    pages = [("s", "http://localhost:%d/sbx.html")]
    off = run(run_ike, site, pages, "off", gl=False)["s"]
    got = run(run_ike, site, pages, "strict", gl=False)["s"]
    assert off["sandboxed"] == {"frame": "THROW SecurityError", "origin": "null"}, off
    assert got["sandboxed"] == off["sandboxed"], (got, off)
    assert got["own"] == off["own"] == {"frame": "worker", "origin": "http://localhost:%d" % site, "ok": True}, (got, off)
