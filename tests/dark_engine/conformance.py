"""Conformance of the I.K.E. Dark Engine with Dark Reader, element by element
(not part of the automatic tests).

    python3 tests/dark_engine/conformance.py FIXTURES_PY OUT_DIR [--modes off,dr,proto] [--only id,id]

FIXTURES_PY: a module with FIXTURES = [{id, html, script?, pre_script?, fix?,
checks?, skip?}, ...] (scenarios adapted from Dark Reader's own tests, MIT).
Each scenario is served as a local page and opened in every mode: off (no
dark mode), dr (Dark Reader as I.K.E. ships it, ike/darkpages.py), proto (the
Dark Engine, ike/darkengine.py; DE_JS_<mode>=file for a variant). After the
scenario's script, every element's computed colours, its box and the picture's
pixels inside the box are read. Compared with Dark Reader:

  text_dE    CIEDE2000 between the text colours of the two engines (elements with text)
  box_dE     CIEDE2000 between the mean colours of the element's box on screen
  hidden     elements shown without dark mode that the engine hides (size, display,
             visibility, opacity), or whose text is no longer drawn
  unreadable text below 3:1 against its box while it was 3:1 or more without dark mode

A scenario PASSes when nothing is hidden, nothing unreadable, and the worst
text_dE and box_dE stay under 10 (a difference anyone sees).
"""

import argparse
import importlib.util
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

import numpy as np  # noqa: E402
from metrics import ciede2000, lab  # noqa: E402

W, H = 900, 700

PROBE = r"""(function(){
function rgba(s){var m=/rgba?\(([^)]+)\)/.exec(s||'');if(!m)return null;var p=m[1].split(/[ ,\/]+/).filter(Boolean).map(Number);return [p[0],p[1],p[2],p.length>3?p[3]:1];}
var out=[],all=[document.documentElement].concat(Array.prototype.slice.call(document.body?document.body.querySelectorAll('*'):[]));
var n=0;
for(var i=0;i<all.length&&out.length<400;i++){var e=all[i];var t=e.tagName;
 if(/^(STYLE|SCRIPT|LINK|META|TITLE|HEAD|BR|NOSCRIPT|TEMPLATE)$/.test(t))continue;
 var cs=getComputedStyle(e),r=e.getBoundingClientRect();
 var own='';for(var c=e.firstChild;c;c=c.nextSibling)if(c.nodeType===3)own+=c.data;
 out.push({k:t+'#'+(n++),tag:t,rect:[r.left,r.top,r.width,r.height],display:cs.display,vis:cs.visibility,op:+cs.opacity,
  color:rgba(cs.color),bg:rgba(cs.backgroundColor),bimg:cs.backgroundImage.slice(0,60),text:own.trim().length>0});}
return JSON.stringify(out);})()"""


def load_fixtures(path):
    spec = importlib.util.spec_from_file_location("fixtures", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.FIXTURES


def page_html(fx):
    pre = fx.get("pre_script") or ""
    return ("<!doctype html><html><head><meta charset='utf-8'><title>fx</title></head><body>%s%s</body></html>"
            % (fx["html"], "<script>%s</script>" % pre if pre else ""))


def serve(fixtures):
    pages = {str(i): page_html(fx).encode() for i, fx in enumerate(fixtures)}

    class Hd(BaseHTTPRequestHandler):
        def do_GET(self):
            key = self.path.split("?")[0].strip("/").removeprefix("fx/").removesuffix(".html")
            body = pages.get(key)
            if body is None:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Hd)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv.server_address[1]


def contrast(a, b):
    def lum(c):
        c = np.asarray(c[:3], dtype=float) / 255
        c = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    la, lb = lum(a), lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def box_mean(img, rect):
    x, y, w, h = (int(round(v)) for v in rect)
    x0, y0, x1, y1 = max(0, x), max(0, y), min(img.shape[1], x + w), min(img.shape[0], y + h)
    if x1 - x0 < 2 or y1 - y0 < 2:
        return None
    return img[y0:y1, x0:x1].reshape(-1, 3).mean(axis=0)


def dominant(img, rect):
    """The commonest colour of a box (its background, text strokes left out)."""
    x, y, w, h = (int(round(v)) for v in rect)
    x0, y0, x1, y1 = max(0, x), max(0, y), min(img.shape[1], x + w), min(img.shape[0], y + h)
    if x1 - x0 < 2 or y1 - y0 < 2:
        return None
    px = (img[y0:y1, x0:x1].reshape(-1, 3) // 8).astype(int)
    keys, counts = np.unique(px[:, 0] * 1024 + px[:, 1] * 32 + px[:, 2], return_counts=True)
    k = keys[counts.argmax()]
    return np.array([(k // 1024) * 8 + 4, (k // 32 % 32) * 8 + 4, (k % 32) * 8 + 4])


def shown(e):
    return e["display"] != "none" and e["vis"] != "hidden" and e["op"] > 0.05 and e["rect"][2] > 1 and e["rect"][3] > 1


def compare(fx, res, engine="proto"):
    off, dr, pr = res.get("off"), res.get("dr"), res.get(engine)
    out = {"id": fx["id"], "hidden": [], "unreadable": [], "text_dE": 0.0, "box_dE": 0.0, "worst": ""}
    if not (off and dr and pr):
        out["error"] = "missing mode"
        return out
    eo = {e["k"]: e for e in off["els"]}
    ed = {e["k"]: e for e in dr["els"]}
    for e in pr["els"]:
        k = e["k"]
        o, d = eo.get(k), ed.get(k)
        if o and shown(o) and not shown(e):
            out["hidden"].append(k)
        if not d:
            continue
        if e["text"] and e["color"] and d["color"] and shown(e) and shown(d):
            de = ciede2000(lab(np.array(e["color"][:3], float)), lab(np.array(d["color"][:3], float)))
            if de > out["text_dE"]:
                out["text_dE"], out["worst"] = round(float(de), 1), "text " + k
        if shown(e) and shown(d) and e["rect"][2] * e["rect"][3] < W * H * 0.9:
            a, b = box_mean(pr["img"], e["rect"]), box_mean(dr["img"], d["rect"])
            if a is not None and b is not None:
                de = ciede2000(lab(a), lab(b))
                if de > out["box_dE"]:
                    out["box_dE"] = round(float(de), 1)
                    if de > out["text_dE"]:
                        out["worst"] = "box " + k
        if e["text"] and shown(e) and e["color"] and o and o["color"]:
            bg = dominant(pr["img"], e["rect"])
            bo = dominant(off["img"], o["rect"])
            if bg is not None and bo is not None:
                c_now = contrast(e["color"], bg)
                c_off = contrast(o["color"], bo)
                if c_now < 3 and c_off >= 3 and e["color"][3] > 0.5:
                    out["unreadable"].append("%s %.2f" % (k, c_now))
    out["verdict"] = "PASS" if not out["hidden"] and not out["unreadable"] and out["text_dE"] < 10 \
        and out["box_dE"] < 10 else "FAIL"
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("fixtures")
    ap.add_argument("out")
    ap.add_argument("--modes", default="off,dr,proto")
    ap.add_argument("--only", default="")
    ap.add_argument("--engine", default="proto", help="the mode compared with Dark Reader")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    fixtures = load_fixtures(a.fixtures)
    todo = [(i, fx) for i, fx in enumerate(fixtures) if not fx.get("skip")
            and (not a.only or fx["id"] in a.only.split(","))]
    port = serve(fixtures)

    from drcompare import darkpages as _drp
    from PyQt6.QtCore import QTimer, QUrl
    from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtWidgets import QApplication

    from ike import darkengine, darkfixes
    darkpages = _drp() if "dr" in a.modes.split(",") else None
    current = {"fix": None}
    orig_fix_for = darkfixes.fix_for

    def fix_for(url):
        base = orig_fix_for(url)
        f = current["fix"]
        if not f:
            return base
        merged = dict(base)
        for key in ("invert", "ignoreInlineStyle", "ignoreImageAnalysis"):
            merged[key] = list(base.get(key) or []) + list(f.get(key) or [])
        merged["css"] = (base.get("css") or "") + "\n" + (f.get("css") or "")
        return merged
    darkfixes.fix_for = fix_for

    app = QApplication(sys.argv[:1])
    modes = a.modes.split(",")
    profiles = {}

    def profile(mode):
        if mode not in profiles:
            prof = QWebEngineProfile(app)
            if mode.startswith("proto"):
                variant = os.environ.get("DE_JS_" + mode)
                if variant:
                    common = json.dumps(darkengine._fix(darkfixes.common_fix()))
                    src = Path(variant).read_text("utf-8").replace("__IKE_DE_COMMON__", common)
                    prof.scripts().insert(darkengine._script(darkengine._NAME, src))
                    darkengine._state[id(prof)] = {"sites": {}, "order": []}
                else:
                    darkengine.install(prof)
            profiles[mode] = prof
        return profiles[mode]

    jobs = [(i, fx, m) for i, fx in todo for m in modes]
    results = {}
    state = {"view": None}

    def next_job():
        if state["view"] is not None:
            state["view"].deleteLater()
            state["view"] = None
        if not jobs:
            finish()
            return
        i, fx, mode = jobs.pop(0)
        current["fix"] = fx.get("fix")
        prof = profile(mode)
        url = "http://127.0.0.1:%d/fx/%d.html?m=%s" % (port, i, mode)
        if mode == "dr":
            darkpages.prepare(prof, url, "127.0.0.1", {"brightness": 100, "contrast": 100, "sepia": 0}, True, True)
        elif mode.startswith("proto"):
            darkengine.prepare(prof, url, "127.0.0.1", True, True)
        view = QWebEngineView()
        page = QWebEnginePage(prof, view)
        view.setPage(page)
        view.resize(W, H)
        view.show()
        state["view"] = view
        done = {"v": False}

        def loaded(_ok):
            if done["v"]:
                return
            done["v"] = True
            script = fx.get("script")
            if script:
                QTimer.singleShot(700, lambda: page.runJavaScript(script, 0, lambda _r: QTimer.singleShot(1500, probe)))
            else:
                QTimer.singleShot(1200, probe)

        def probe():
            def got(js):
                img = view.grab().toImage()
                path = out / ("%s__%s.png" % (fx["id"].replace("/", "__"), mode))
                img.save(str(path))
                from PIL import Image
                arr = np.asarray(Image.open(path).convert("RGB"), dtype=np.float64)
                els = json.loads(js or "[]")
                path.with_suffix(".json").write_text(json.dumps(els))
                results.setdefault(fx["id"], {})[mode] = {"els": els, "img": arr}
                next_job()
            page.runJavaScript(PROBE, 0, got)
        page.loadFinished.connect(loaded)
        page.load(QUrl(url))
        QTimer.singleShot(15000, lambda: loaded(True))

    def finish():
        report = []
        for _i, fx in todo:
            report.append(compare(fx, results.get(fx["id"], {}), a.engine))
        (out / ("conformance-%s.json" % a.engine)).write_text(json.dumps(report, indent=1))
        passed = sum(r.get("verdict") == "PASS" for r in report)
        print("conformance: %d of %d PASS" % (passed, len(report)))
        for r in report:
            if r.get("verdict") != "PASS":
                print("  FAIL %s: text_dE %s box_dE %s worst %s hidden %s unreadable %s %s" % (
                    r["id"], r["text_dE"], r["box_dE"], r["worst"], r["hidden"][:4], r["unreadable"][:4],
                    r.get("error", "")))
        app.quit()

    QTimer.singleShot(0, next_job)
    app.exec()


if __name__ == "__main__":
    main()
