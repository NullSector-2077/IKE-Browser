#!/usr/bin/env python3
"""What the engine of a copy of I.K.E. is and which formats it declares.

    python engine-check.py [--app DIR] [--json FILE] [--expect-free-only]

Starts Qt WebEngine without a window, asks it the same question as
Help → About (ike/mediacheck.py: ``canPlayType`` and Media Source support for
H.264, AAC, HEVC, VP9, AV1, Opus, MP3) and prints the versions of Python, Qt,
PyQt, Qt WebEngine and Chromium, and whether the engine's sandbox is switched
off by the environment. Nothing is downloaded and no profile is written.

The Windows workflow runs it with the installed copy's own Python
(.github/workflows/windows.yml). --expect-free-only fails when the engine does
not declare VP9, AV1, Opus and MP3, or does declare H.264 or AAC: the Windows
installer ships the official Qt WebEngine, which has no proprietary codec.
Exit status: 0 the engine answered (and the expectation holds), 1 otherwise.
"""

import argparse
import json
import os
import platform
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--app", default=str(ROOT))
    ap.add_argument("--json")
    ap.add_argument("--expect-free-only", action="store_true")
    args = ap.parse_args()
    sys.path.insert(0, args.app)
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PyQt6.QtCore import PYQT_VERSION_STR, QT_VERSION_STR, QCoreApplication, Qt, QTimer
    from PyQt6.QtWebEngineCore import qWebEngineChromiumVersion, qWebEngineVersion
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    from PyQt6.QtWidgets import QApplication
    app = QApplication(sys.argv[:1])

    import ike
    from ike import mediacheck
    try:
        from PyQt6.QtWebEngineCore import qWebEngineChromiumSecurityPatchVersion
        patch = qWebEngineChromiumSecurityPatchVersion()
    except ImportError:
        patch = ""
    flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "").split()
    report = {
        "ike": ike.__version__,
        "ike_from": str(Path(ike.__file__).resolve().parent),
        "system": platform.platform(),
        "python": platform.python_version(),
        "python_from": sys.executable,
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
    give_up = QTimer(singleShot=True, interval=mediacheck.TIMEOUT_MS + 5000)
    give_up.timeout.connect(app.quit)
    give_up.start()
    timer = QTimer(interval=100)
    timer.timeout.connect(lambda: got and app.quit())
    timer.start()
    app.exec()
    timer.stop()
    give_up.stop()
    report["formats"] = got[0] if got else {}
    text = json.dumps(report, indent=2)
    print(text)
    if args.json:
        Path(args.json).write_text(text + "\n", "utf-8")
    if not report["formats"]:
        print("engine-check: the engine did not answer", file=sys.stderr)
        return 1
    if args.expect_free_only:
        f = report["formats"]
        missing = [n for n in ("VP9", "AV1", "Opus", "MP3") if not f.get(n)]
        extra = [n for n in ("H.264", "AAC", "HEVC") if f.get(n)]
        if missing or extra:
            print("engine-check: expected the royalty-free formats only; missing %s, unexpected %s"
                  % (missing, extra), file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
