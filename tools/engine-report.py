#!/usr/bin/env python3
"""What the engine of this system is and what it can play.

    python3 tools/engine-report.py [--json FILE] [--markdown FILE] [--app DIR]

Starts Qt WebEngine without a window (``QT_QPA_PLATFORM=offscreen`` unless a
platform is set), asks it which video and audio formats it plays with the same
probe as Help → About (ike/mediacheck.py), and prints the system, Python, Qt,
PyQt, Qt WebEngine, Chromium and its security patch level, and whether the
engine's sandbox is switched off by the environment. Nothing is downloaded and
no profile is written. Used by the GitHub workflows on every distribution
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


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--json")
    ap.add_argument("--markdown")
    ap.add_argument("--app", default=str(ROOT))
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
    QTimer.singleShot(mediacheck.TIMEOUT_MS + 2000, app.quit)
    timer = QTimer(interval=100)
    timer.timeout.connect(lambda: got and app.quit())
    timer.start()
    app.exec()
    report["formats"] = got[0] if got else {}

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
                ("Plays", ", ".join(yes) or "—"),
                ("Does not play", ", ".join(no) or "—")]
        md = "| | |\n|---|---|\n" + "".join("| %s | %s |\n" % r for r in rows)
        Path(args.markdown).write_text(md, "utf-8")
    return 0 if report["formats"] else 1


if __name__ == "__main__":
    sys.exit(main())
