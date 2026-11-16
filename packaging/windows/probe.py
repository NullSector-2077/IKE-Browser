"""Temporary probe (removed before the port is finished): does Qt WebEngine
load a page on this runner, with which platform plug-in, with the sandbox?"""
import json
import os
import subprocess
import sys

CHILD = r'''
import sys, json
from PyQt6.QtCore import QTimer, QUrl
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QApplication
app = QApplication(sys.argv[:1])
v = QWebEngineView()
v.resize(3000, 900)
v.show()
out = {}
def loaded(ok):
    out["loaded"] = ok
    v.page().runJavaScript("JSON.stringify([navigator.userAgent, navigator.platform, innerWidth, "
                           "!!document.createElement('canvas').getContext('webgl')])", done)
def done(r):
    out["js"] = r
    out["size"] = [v.width(), v.height()]
    scr = app.primaryScreen()
    out["screen"] = [scr.size().width(), scr.size().height(), scr.devicePixelRatio()]
    print("PROBE " + json.dumps(out), flush=True)
    app.quit()
v.loadFinished.connect(loaded)
v.page().renderProcessTerminated.connect(lambda s, c: (print("PROBE terminated", s, c, flush=True), app.quit()))
v.setHtml("<!doctype html><p>hello</p>")
QTimer.singleShot(40000, lambda: (print("PROBE timeout " + json.dumps(out), flush=True), app.quit()))
app.exec()
'''
for name, env in (("offscreen+sandbox", {"QT_QPA_PLATFORM": "offscreen"}),
                  ("windows+sandbox", {}),
                  ("offscreen+nosandbox", {"QT_QPA_PLATFORM": "offscreen", "QTWEBENGINE_DISABLE_SANDBOX": "1"})):
    e = {k: v for k, v in os.environ.items() if not k.startswith("QTWEBENGINE")}
    e.update(env)
    try:
        r = subprocess.run([sys.executable, "-c", CHILD], env=e, capture_output=True, text=True, timeout=120)
        print("==", name, "exit", r.returncode)
        print(r.stdout[-3000:])
        print(r.stderr[-3000:])
    except subprocess.TimeoutExpired as t:
        print("==", name, "HUNG", (t.stdout or b"")[-2000:], (t.stderr or b"")[-2000:])
