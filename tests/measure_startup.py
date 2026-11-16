"""Start-up time of I.K.E.: from starting the program to its first window on
screen, median of several starts, each with an empty profile (as the tests).

    python tests/measure_startup.py [runs]           this repository
    ICE_TEST_EXE=...\\ike-browser.exe python tests/measure_startup.py   an installed copy (Windows)
    ICE_TEST_APP=/usr/lib/ike-browser python3 tests/measure_startup.py  an installed copy (Linux)

The first start is not counted (it fills the disk cache).
"""

import hashlib
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = Path(os.environ.get("ICE_TEST_APP") or ROOT)
HOOK = '''
import json, os, time
from PyQt6.QtCore import QTimer
def check():
    if ice.windows and ice.windows[0].isVisible():
        with open(os.environ["ICE_T_OUT"], "w") as f:
            f.write(json.dumps(time.time()))
        for w in list(ice.windows):
            w.close()
        QTimer.singleShot(50, qapp.quit)
        return
    QTimer.singleShot(5, check)
check()
'''


def main(runs):
    work = Path(tempfile.mkdtemp(prefix="ice-startup-"))
    hook = work / "hook.py"
    hook.write_text(HOOK, "utf-8")
    cmd = [os.environ["ICE_TEST_EXE"]] if os.environ.get("ICE_TEST_EXE") else [sys.executable, str(APP / "ike_boot.py")]
    times = []
    for i in range(runs + 1):
        home = work / ("home%d" % i)
        cfg = home / ".config" / "ike-browser"
        cfg.mkdir(parents=True)
        (cfg / "settings.json").write_text(json.dumps({
            "lists_version": 3, "last_lists_update": 4102444800, "last_fast_update": 4102444800,
            "chrome_checked": 4102444800, "app_updates": "off", "auto_update": False}))
        lists = home / ".local/share/ike-browser/lists"
        lists.mkdir(parents=True)
        name = hashlib.sha1(b"https://easylist.to/easylist/easylist.txt").hexdigest()[:16] + ".txt"
        (lists / name).write_text("||ads.example.test^\n")
        out = home / "t.json"
        env = {k: v for k, v in os.environ.items() if not k.startswith(("XDG_", "ICE_"))}
        env.update(HOME=str(home), XDG_CONFIG_HOME=str(home / ".config"),
                   XDG_DATA_HOME=str(home / ".local/share"), XDG_CACHE_HOME=str(home / ".cache"),
                   QT_QPA_PLATFORM=os.environ.get("ICE_TEST_QPA") or "offscreen",
                   QTWEBENGINE_CHROMIUM_FLAGS="--no-sandbox", ICE_NO_SINGLE="1",
                   ICE_TEST_HOOK=str(hook), ICE_T_OUT=str(out), DBUS_SESSION_BUS_ADDRESS="")
        t0 = time.time()
        subprocess.run(cmd, env=env, capture_output=True, timeout=120)
        if i:
            times.append(json.loads(out.read_text()) - t0)
    print("start-up: median %.3f s over %d starts (%s)"
          % (statistics.median(times), len(times), " ".join("%.2f" % t for t in times)))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 9)
