#!/usr/bin/env python3
"""What the engine of this system is and what it can play.

    python3 tools/engine-report.py [--json FILE] [--markdown FILE] [--app DIR] [--decode DIR]

Starts Qt WebEngine without a window (``QT_QPA_PLATFORM=offscreen`` unless a
platform is set), asks it which video and audio formats it plays with the same
probe as Help → About (ike/mediacheck.py), and prints the system, Python, Qt,
PyQt, Qt WebEngine, Chromium and its security patch level, and whether the
engine's sandbox is switched off by the environment. Nothing is downloaded and
no profile is written.

What the engine declares is not always what it decodes: a distribution can
build the engine with H.264 enabled and a system FFmpeg without an H.264
decoder. --decode DIR (tests/media: two-second clips, test data only, never
packaged) decodes one clip per format and reports which really decoded:
video clips are played muted (frames shown), audio clips are decoded with
the Web Audio API (no sound device needed). Used by the GitHub workflows on every distribution
(docs/platforms/porting-plan.md, "the check every platform starts with") and
useful by hand on a new system. --app chooses an installed copy of I.K.E.
(default: this repository). Exit status 0 when the engine answered.
"""

import argparse
import json
import os
import platform
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def os_name():
    try:
        rel = {}
        for line in Path("/etc/os-release").read_text("utf-8").splitlines():
            k, _, v = line.partition("=")
            rel[k] = v.strip().strip('"')
        return rel.get("PRETTY_NAME") or rel.get("NAME") or platform.platform()
    except OSError:
        return platform.platform()


# one clip per format in the --decode folder, and whether it is video
CLIPS = {"H.264": ("h264.mp4", "video/mp4", True), "AAC": ("aac.m4a", "audio/mp4", False),
         "HEVC": ("hevc.mp4", "video/mp4", True), "VP9": ("vp9.webm", "video/webm", True),
         "AV1": ("av1.webm", "video/webm", True), "Opus": ("opus.webm", "audio/webm", False),
         "MP3": ("mp3.mp3", "audio/mpeg", False)}

_DECODE_JS = """(function (clips) {
  window.__ike_decoded = null;
  var out = {}, left = clips.length;
  function done(name, ok) {
    out[name] = ok;
    if (--left === 0) window.__ike_decoded = JSON.stringify(out);
  }
  clips.forEach(function (c) {
    if (!c.video) {
      // audio: decoded by the engine without a sound device (none in a container)
      fetch(c.url).then(function (r) { return r.arrayBuffer(); }).then(function (buf) {
        return new OfflineAudioContext(1, 44100, 44100).decodeAudioData(buf);
      }).then(function (b) { done(c.name, b.duration > 1); }, function () { done(c.name, false); });
      return;
    }
    var m = document.createElement("video");
    m.muted = true; m.preload = "auto";
    var settled = false;
    function finish(ok) {
      if (settled) return; settled = true; m.pause(); done(c.name, ok);
    }
    m.onerror = function () { finish(false); };
    var t0 = Date.now();
    var iv = setInterval(function () {
      var frames = 0;
      try { frames = m.getVideoPlaybackQuality().totalVideoFrames; } catch (e) {}
      var ok = m.videoWidth > 0 && (frames > 0 || m.currentTime > 0.3);
      if (ok || m.error || Date.now() - t0 > 6000) { clearInterval(iv); finish(!!ok && !m.error); }
    }, 100);
    document.body.appendChild(m);
    m.src = c.url;
    var p = m.play(); if (p && p.catch) p.catch(function () {});
  });
})(%s)"""


def decode(app, folder):
    """{format: bool}: did a clip of each format really play in the engine?"""
    import base64

    from PyQt6.QtCore import QTimer
    from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
    clips = []
    for name, (file, mime, video) in CLIPS.items():
        data = (folder / file).read_bytes()
        clips.append({"name": name, "video": video,
                      "url": "data:%s;base64,%s" % (mime, base64.b64encode(data).decode())})
    profile = QWebEngineProfile()                    # off the record
    page = QWebEnginePage(profile)
    result = {}
    state = {"loaded": False}

    def loaded(ok):
        state["loaded"] = True
        page.runJavaScript(_DECODE_JS % json.dumps(clips))

    def poll():
        if not state["loaded"]:
            return
        page.runJavaScript("window.__ike_decoded", lambda r: r and result.update(json.loads(r)))
        if result:
            app.quit()
    page.loadFinished.connect(loaded)
    page.setHtml("<!doctype html><body></body>")
    timer = QTimer(interval=300)
    timer.timeout.connect(poll)
    timer.start()
    give_up = QTimer(singleShot=True, interval=30000)
    give_up.timeout.connect(app.quit)
    give_up.start()
    app.exec()
    timer.stop()
    give_up.stop()
    page.deleteLater()
    return {name: bool(result.get(name)) for name in CLIPS} if result else {}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--json")
    ap.add_argument("--markdown")
    ap.add_argument("--app", default=str(ROOT))
    ap.add_argument("--decode", metavar="DIR")
    args = ap.parse_args()
    sys.path.insert(0, args.app)
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PyQt6.QtCore import PYQT_VERSION_STR, QT_VERSION_STR, QCoreApplication, Qt, QTimer
    from PyQt6.QtWebEngineCore import qWebEngineChromiumVersion, qWebEngineVersion
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    from PyQt6.QtWidgets import QApplication
    app = QApplication(sys.argv[:1])

    from ike import mediacheck
    try:
        from PyQt6.QtWebEngineCore import qWebEngineChromiumSecurityPatchVersion
        patch = qWebEngineChromiumSecurityPatchVersion()
    except ImportError:
        patch = ""
    flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "").split()
    report = {
        "system": os_name(),
        "python": platform.python_version(),
        "qt": QT_VERSION_STR,
        "pyqt": PYQT_VERSION_STR,
        "qt_webengine": qWebEngineVersion(),
        "chromium": qWebEngineChromiumVersion(),
        "chromium_security_patch": patch,
        "sandbox_off_by_environment": "--no-sandbox" in flags
        or os.environ.get("QTWEBENGINE_DISABLE_SANDBOX", "") not in ("", "0"),
        "formats": {},
    }
    got = []
    mediacheck.ask(None, got.append)
    give_up = QTimer(singleShot=True, interval=mediacheck.TIMEOUT_MS + 2000)
    give_up.timeout.connect(app.quit)
    give_up.start()
    timer = QTimer(interval=100)
    timer.timeout.connect(lambda: got and app.quit())
    timer.start()
    app.exec()
    timer.stop()
    give_up.stop()
    report["formats"] = got[0] if got else {}
    if args.decode:
        report["decoded"] = decode(app, Path(args.decode))

    text = json.dumps(report, indent=2)
    print(text)
    if args.json:
        Path(args.json).write_text(text + "\n", "utf-8")
    if args.markdown:
        yes, no = mediacheck.split(report["formats"]) if report["formats"] else ([], [])
        rows = [("System", report["system"]), ("Python", report["python"]),
                ("Qt / PyQt", "%s / %s" % (report["qt"], report["pyqt"])),
                ("Qt WebEngine", report["qt_webengine"]),
                ("Chromium", "%s (security patches %s)" % (report["chromium"], patch or "?")),
                ("Sandbox", "off (by the environment)" if report["sandbox_off_by_environment"] else "on"),
                ("Declares", ", ".join(yes) or "—"),
                ("Does not declare", ", ".join(no) or "—")]
        if "decoded" in report:
            dec = report["decoded"]
            rows.append(("Decodes (clips played)", ", ".join(k for k, v in dec.items() if v) or "—"))
            rows.append(("Does not decode", ", ".join(k for k, v in dec.items() if not v) or "—"))
        md = "| | |\n|---|---|\n" + "".join("| %s | %s |\n" % r for r in rows)
        Path(args.markdown).write_text(md, "utf-8")
    return 0 if report["formats"] else 1


if __name__ == "__main__":
    sys.exit(main())
