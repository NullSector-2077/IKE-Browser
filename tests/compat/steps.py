"""Runs inside I.K.E. (tests/harness.py): opens each site of COMPAT_SITES in
its own tab at the profile's level, lets it work, then records what the page
did (see probe.js), the engine's console messages, the requests I.K.E.
blocked and a screenshot. Optionally changes the level while the page is open
(COMPAT_SWITCH) to reproduce the owner's "white page after a level change".
"""
import json
import os
import time


def steps(ike, qapp, out):
    from PyQt6.QtCore import QUrl
    from PyQt6.QtWebEngineCore import QWebEngineScript

    from ike import shields, webview

    sites = json.load(open(os.environ["COMPAT_SITES"], encoding="utf-8"))
    outdir = os.environ["COMPAT_OUTDIR"]
    probe_src = open(os.environ["COMPAT_PROBE"], encoding="utf-8").read()
    switch = os.environ.get("COMPAT_SWITCH", "")          # "strict,maximum,balanced" ...
    os.makedirs(outdir, exist_ok=True)
    # an experiment: Python run inside the browser before the first site
    # (e.g. "shields._WORKER_SCRIPTS = frozenset()" lifts one rule only)
    if os.environ.get("COMPAT_PATCH"):
        exec(os.environ["COMPAT_PATCH"], {"ike": ike, "shields": shields, "webview": webview})
    cur = {"key": None}
    logs, blocked = {}, {}

    orig_cm = webview.WebPage.javaScriptConsoleMessage

    def console(self, level, message, line, source):
        k = cur["key"]
        if k is not None:
            lst = logs.setdefault(k, [])
            if len(lst) < 400:
                lst.append([getattr(level, "value", level), str(message)[:400], str(source)[:160], line])
        return orig_cm(self, level, message, line, source)
    webview.WebPage.javaScriptConsoleMessage = console

    orig_ir = shields.Interceptor.interceptRequest
    from PyQt6.QtWebEngineCore import QWebEngineUrlRequestInfo
    orig_block = QWebEngineUrlRequestInfo.block

    def block(info, on):
        k = cur["key"]
        if on and k is not None:
            lst = blocked.setdefault(k, [])
            if len(lst) < 400:
                try:
                    rt = info.resourceType().name
                except Exception:
                    rt = "?"
                lst.append([rt.replace("ResourceType", ""), info.requestUrl().toString()[:200]])
        return orig_block(info, on)
    QWebEngineUrlRequestInfo.block = block

    def intercept(self, info):
        return orig_ir(self, info)
    shields.Interceptor.interceptRequest = intercept

    win = ike.windows[0]
    win.showMaximized()
    yield 1500
    results = []
    for site in sites:
        key = site["key"]
        cur["key"] = key
        t0 = time.time()
        v = win.add_tab(QUrl(site["url"]))
        win.stack.setCurrentWidget(v) if hasattr(win, "stack") else None
        state = {"loads": []}
        v.loadFinished.connect(lambda ok, s=state, vv=v: s["loads"].append([bool(ok), vv.url().toString()[:200]]))
        waited = 0
        wait = int(site.get("wait", 14000))
        while waited < wait:
            yield 1000
            waited += 1000
        rec = {"key": key, "url": site["url"], "level": ike.config["shield_level"],
               "dark": ike.config["dark_mode"]}

        def probe(tag):
            box = {}
            js = probe_src.replace("__CHECK__", site.get("check") or "null").replace("__TAG__", tag)
            v.page().runJavaScript(js, QWebEngineScript.ScriptWorldId.ApplicationWorld,
                                   lambda r, b=box: b.setdefault("r", r))
            return box

        probe("p1")
        box2 = {}
        for _ in range(20):             # a check may wait itself (a video playing): up to 20 s
            yield 1000
            box2 = {}
            v.page().runJavaScript("window.__ikeProbe_p1 || null", QWebEngineScript.ScriptWorldId.ApplicationWorld,
                                   lambda r, b=box2: b.setdefault("r", r))
            yield 300
            if box2.get("r"):
                break
        try:
            rec["probe"] = json.loads(box2.get("r") or "null")
        except Exception as e:
            rec["probe"] = {"parse_error": str(e), "raw": str(box2.get("r"))[:300]}

        def shot(name):
            try:
                if os.environ.get("QT_QPA_PLATFORM", "").startswith("xcb"):
                    # the X server's own picture: grab() misses what the GPU composes
                    top = v.window()
                    top.raise_()
                    top.activateWindow()
                    qapp.processEvents()
                    g = v.mapToGlobal(v.rect().topLeft())
                    img = qapp.primaryScreen().grabWindow(0, g.x(), g.y(), v.width(), v.height()).toImage()
                else:
                    img = v.grab().toImage()
                img.save(os.path.join(outdir, name + ".png"))
                small = img.scaled(64, 40)
                tot, n, white = 0, 0, 0
                for y in range(small.height()):
                    for x in range(small.width()):
                        lt = small.pixelColor(x, y).lightness()
                        tot += lt
                        n += 1
                        white += lt > 245
                return {"mean": round(tot / max(n, 1)), "white": round(white / max(n, 1), 2)}
            except Exception as e:
                return {"error": str(e)}
        rec["windows"] = len(ike.windows)
        rec["shot"] = shot(key)
        rec["final_url"] = v.url().toString()[:300]
        rec["title"] = v.title()[:120]
        rec["loads"] = state["loads"]

        # level changes while the page is open, through the shield's own path
        if switch:
            rec["switch"] = []
            for step in switch.split(","):
                lv, _, ms = step.partition(":")      # "strict:3000": wait 3 s after this change
                cfg = ike.config
                cfg["shield_level"] = lv
                cfg.save()
                ike.shields.apply_settings()
                ike.refresh_windows()
                v.reload()
                w2 = 0
                while w2 < int(ms or site.get("switch_wait", 12000)):
                    yield 1000
                    w2 += 1000
                probe("p_" + lv)
                box2 = {}
                for _ in range(20):
                    yield 1000
                    box2 = {}
                    v.page().runJavaScript("window.__ikeProbe_p_%s || null" % lv,
                                           QWebEngineScript.ScriptWorldId.ApplicationWorld,
                                           lambda r, b=box2: b.setdefault("r", r))
                    yield 300
                    if box2.get("r"):
                        break
                try:
                    pr = json.loads(box2.get("r") or "null")
                except Exception:
                    pr = None
                rec["switch"].append({"level": lv, "probe": pr, "shot": shot("%s__to_%s" % (key, lv)),
                                      "console_n": len(logs.get(key, []))})
        # what the shield's octagon said (1.1.32): the diagnosis, a safety
        # warning, the green confirmation of the page's load
        try:
            f = ike.diagnosis.finding(v)
            rec["octagon"] = {"state": win.interference_state(v)[0],
                              "finding": [f.detector, list(f.keys), f.severity] if f else None,
                              "green": getattr(v, "_ike_confirmed", None) is not None}
        except Exception as e:
            rec["octagon"] = {"error": str(e)[:200]}
        rec["console"] = logs.get(key, [])
        rec["blocked"] = blocked.get(key, [])
        rec["secs"] = round(time.time() - t0, 1)
        dl = os.path.join(os.environ.get("HOME", "/"), "Downloads")
        rec["downloads_dir"] = sorted(os.listdir(dl)) if os.path.isdir(dl) else []
        results.append(rec)
        with open(os.path.join(outdir, "results.json"), "w", encoding="utf-8") as f:
            json.dump(results, f, indent=1, default=str)
        cur["key"] = None
        win.close_tab(v)
        yield 1500
    out["done"] = len(results)
