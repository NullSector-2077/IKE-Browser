"""What the display of this computer looks like to Qt: platform plug-in,
style, font and its width, screen - and, with --webgl, whether software WebGL
holds over several pages with a few sets of engine switches.

    python tests/show_display.py [--webgl]

Printed by the Windows workflow at the start of its test job: the layout
tests measure text, and this tells what they measured with.
"""
import json
import os
import subprocess
import sys

CHILD = r'''
import json, sys
from PyQt6.QtGui import QFontInfo, QFontMetrics
from PyQt6.QtWidgets import QApplication, QCheckBox, QPushButton, QStyleFactory
app = QApplication(sys.argv[:1])
f = app.font()
fi = QFontInfo(f)
fm = QFontMetrics(f)
scr = app.primaryScreen()
c = QCheckBox("Load restored tabs only when they are opened (faster start)")
b = QPushButton("Make I.K.E. the default browser")
print("FACTS " + json.dumps({
    "platform": app.platformName(), "style": app.style().objectName(), "styles": QStyleFactory.keys(),
    "font": [f.family(), f.pointSizeF(), f.pixelSize(), fi.family(), fi.pointSizeF(), fi.pixelSize()],
    "sample_width": fm.horizontalAdvance("The quick brown fox jumps over the lazy dog 0123456789"),
    "height": fm.height(), "checkbox": [c.sizeHint().width(), c.sizeHint().height()],
    "button": [b.sizeHint().width(), b.sizeHint().height()],
    "screen": [scr.size().width(), scr.size().height(), scr.devicePixelRatio(), scr.logicalDotsPerInch()],
}), flush=True)
'''

WEBGL = r'''
import json, sys
from PyQt6.QtCore import QTimer, QUrl
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QApplication
app = QApplication(sys.argv[:1])
v = QWebEngineView()
v.resize(800, 600)
v.show()
got = []
import os
JS = """(function(){var g=document.createElement('canvas').getContext('webgl'); if(!g) return null;
var d=g.getExtension('WEBGL_debug_renderer_info'); return d ? g.getParameter(d.UNMASKED_RENDERER_WEBGL).slice(0, 40) : 'no debug info';})()"""
GPU = """(async function(){ try { if (!navigator.gpu) { window.wg = 'no navigator.gpu'; return; }
var ad = await Promise.race([navigator.gpu.requestAdapter(), new Promise(function (ok) { setTimeout(ok, 1500, 'slow'); })]);
window.wg = ad === 'slow' ? 'slow' : (ad ? 'adapter' : 'no adapter'); } catch (e) { window.wg = 'error ' + e; } })()"""
def ask(ok):
    def webgl(r):
        if os.environ.get("SHOW_WEBGPU"):
            v.page().runJavaScript(GPU)
            QTimer.singleShot(2500, lambda: v.page().runJavaScript("window.wg", lambda w: (got.append([r, w]), nxt())))
        else:
            got.append(r)
            nxt()
    v.page().runJavaScript(JS, webgl)
def nxt():
    if len(got) >= 4:
        print("WEBGL " + json.dumps(got), flush=True)
        app.quit()
    else:
        v.load(QUrl("data:text/html,<p>page %d</p>" % len(got)))
v.loadFinished.connect(ask)
v.page().renderProcessTerminated.connect(lambda s, c: print("WEBGL renderer ended", s, c, flush=True))
nxt()
QTimer.singleShot(60000, lambda: (print("WEBGL timeout " + json.dumps(got), flush=True), app.quit()))
app.exec()
'''


def run(code, env, label):
    e = {k: v for k, v in os.environ.items() if not k.startswith("QTWEBENGINE")}
    e.update(env)
    try:
        r = subprocess.run([sys.executable, "-c", code], env=e, capture_output=True, text=True, timeout=150)
        lines = [line for line in r.stdout.splitlines() if line.startswith(("FACTS", "WEBGL"))]
        print("%s: %s" % (label, " | ".join(lines) or "no answer (exit %s) %s" % (r.returncode, r.stderr[-400:])))
    except subprocess.TimeoutExpired:
        print("%s: no answer in time" % label)


def main():
    for platform in ("offscreen",) + (("windows",) if sys.platform == "win32" else ()):
        run(CHILD, {"QT_QPA_PLATFORM": platform}, platform)
    if sys.platform == "win32":
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from conftest import windows_fonts
        run(CHILD, {"QT_QPA_PLATFORM": "offscreen", "QT_QPA_FONTDIR": windows_fonts() or ""},
            "offscreen with the fonts of the tests (%s)" % windows_fonts())
    if "--webgl" in sys.argv:
        for flags in ("", "--ignore-gpu-blocklist", "--ignore-gpu-blocklist --use-angle=d3d11-warp",
                      "--ignore-gpu-blocklist --use-angle=d3d11",
                      "--enable-unsafe-swiftshader --use-angle=swiftshader --ignore-gpu-blocklist",
                      "--enable-unsafe-swiftshader --use-gl=angle --use-angle=swiftshader-webgl --ignore-gpu-blocklist",
                      "--enable-unsafe-swiftshader --ignore-gpu-blocklist --disable-gpu"):
            run(WEBGL, {"QT_QPA_PLATFORM": "offscreen", "QTWEBENGINE_CHROMIUM_FLAGS": flags},
                "webgl with [%s]" % flags)
        for flags in ("--ignore-gpu-blocklist",
                      "--enable-unsafe-swiftshader --use-angle=swiftshader --ignore-gpu-blocklist"):
            run(WEBGL, {"QT_QPA_PLATFORM": "offscreen", "QTWEBENGINE_CHROMIUM_FLAGS": flags, "SHOW_WEBGPU": "1"},
                "webgl, then webgpu, with [%s]" % flags)
    print(json.dumps({"python": sys.version.split()[0], "system": sys.platform}))


if __name__ == "__main__":
    main()
