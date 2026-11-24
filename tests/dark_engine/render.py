"""Renders the study's pages offscreen under several dark modes and saves, for each
page and mode, a screenshot (PNG) and what the page holds (JSON: rectangles of
text, media and checked elements). Not part of the automatic tests.

    QT_QPA_PLATFORM=offscreen QTWEBENGINE_CHROMIUM_FLAGS=--no-sandbox \
        python3 tests/dark_engine/render.py OUT_DIR [--modes off,dr,native,proto] [--bench N]

Modes: off (no dark mode), dr (Dark Reader, I.K.E.'s current engine, through
ike/darkpages.py as the browser installs it), native (Chromium's ForceDarkMode),
proto (the I.K.E. Dark Engine prototype, ike/darkengine.py).
"""

import argparse
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--no-sandbox")

import pages  # noqa: E402

PROBE = r"""(function(){
function R(r){return [Math.round(r.left),Math.round(r.top),Math.round(r.width),Math.round(r.height)]}
var text=[],media=[],checks=[];
var w=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);var n;
while((n=w.nextNode())){if(!n.data.trim())continue;var p=n.parentElement;if(!p||/^(SCRIPT|STYLE|OPTION)$/.test(p.tagName))continue;
 var rg=document.createRange();rg.selectNodeContents(n);var rs=rg.getClientRects();
 for(var i=0;i<rs.length;i++){var r=rs[i];if(r.width>4&&r.height>4&&r.top<innerHeight)text.push(R(r));}}
document.querySelectorAll('input,textarea,select,button').forEach(function(e){var r=e.getBoundingClientRect();
 var t=e.value||e.placeholder||e.textContent.trim();if(t)text.push([Math.round(r.left)+3,Math.round(r.top)+3,Math.min(Math.round(r.width)-6,8*t.length+8),Math.min(Math.round(r.height)-6,22)]);});
document.querySelectorAll('img,canvas,video,[data-media]').forEach(function(e){media.push(R(e.getBoundingClientRect()))});
document.querySelectorAll('[data-check]').forEach(function(e){checks.push({kind:e.dataset.check,rect:R(e.getBoundingClientRect()),tag:e.tagName})});
var de=[].map.call(document.querySelectorAll('style.ike-de'),function(e){return e.textContent.slice(0,400)});
return JSON.stringify({text:text,media:media,checks:checks,de:de});})()"""


def serve(port_holder):
    imgs = pages.images()
    docs = dict(pages.PAGES, bench=pages.BENCH)
    extra = getattr(pages, "EXTRA", {})
    docs.update(extra)

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            p = self.path.split("?")[0].strip("/")
            if p.startswith("img/") and p[4:] in imgs:
                body, ctype = imgs[p[4:]], "image/png"
            elif p.removesuffix(".html") in docs:
                body, ctype = docs[p.removesuffix(".html")].encode(), "text/html; charset=utf-8"
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    port_holder.append(srv.server_address[1])
    threading.Thread(target=srv.serve_forever, daemon=True).start()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--modes", default="off,dr,native,proto")
    ap.add_argument("--pages", default="")
    ap.add_argument("--bench", type=int, default=0, help="runs of the speed proxy per mode (0: none)")
    ap.add_argument("--settle", type=int, default=1500, help="ms to wait after the load")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    from PyQt6.QtCore import QTimer, QUrl
    from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineSettings
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtWidgets import QApplication

    class Page(QWebEnginePage):
        def javaScriptConsoleMessage(self, level, msg, line, src):
            if os.environ.get("DE_DEBUG"):
                print("console:", msg, line, src[-40:], flush=True)

    app = QApplication(sys.argv[:1])
    port = []
    serve(port)
    base = "http://127.0.0.1:%d/" % port[0]
    names = [p for p in (a.pages.split(",") if a.pages else pages.PAGES)]
    jobs = [(m, n) for m in a.modes.split(",") for n in names]
    jobs += [(m, "bench") for m in a.modes.split(",") for _ in range(a.bench)]
    results = {"bench": {}}
    profiles = {}
    state = {"view": None}

    def profile_for(mode):
        if mode not in profiles:
            prof = QWebEngineProfile(app)          # off the record
            if mode == "proto":
                from ike import darkengine
                darkengine.install(prof)
            profiles[mode] = prof
        return profiles[mode]

    def next_job():
        if state["view"] is not None:
            state["view"].deleteLater()
        if not jobs:
            (out / "bench.json").write_text(json.dumps(results["bench"], indent=1))
            app.quit()
            return
        mode, name = jobs.pop(0)
        prof = profile_for(mode)
        url = base + name + ".html"
        if mode == "dr":
            from ike import darkpages
            darkpages.prepare(prof, url, "127.0.0.1", {"brightness": 100, "contrast": 100, "sepia": 0}, True, False)
        view = QWebEngineView()
        page = Page(prof, view)
        view.setPage(page)
        page.settings().setAttribute(QWebEngineSettings.WebAttribute.ForceDarkMode, mode == "native")
        view.resize(pages.W, pages.H)
        view.show()
        state["view"] = view

        def loaded(ok):
            if name == "bench":
                QTimer.singleShot(a.settle, lambda: page.runJavaScript(
                    "bench().then(function(t){window.__bt=t})", 0,
                    lambda _: QTimer.singleShot(200, poll)))
            else:
                QTimer.singleShot(a.settle, shoot)

        def poll():
            def got(v):
                if v is None:
                    QTimer.singleShot(100, poll)
                else:
                    results["bench"].setdefault(mode, []).append(round(v, 1))
                    print("bench", mode, round(v, 1), flush=True)
                    next_job()
            page.runJavaScript("window.__bt", 0, got)

        def shoot():
            def probed(js):
                img = view.grab().toImage()
                img.save(str(out / ("%s__%s.png" % (name, mode))))
                (out / ("%s__%s.json" % (name, mode))).write_text(js or "{}")
                print("shot", mode, name, flush=True)
                next_job()
            page.runJavaScript(PROBE, 0, probed)

        page.loadFinished.connect(loaded)
        page.load(QUrl(url))

    QTimer.singleShot(0, next_job)
    app.exec()


if __name__ == "__main__":
    main()
