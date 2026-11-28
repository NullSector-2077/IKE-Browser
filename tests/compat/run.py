#!/usr/bin/env python3
"""Start I.K.E. (an installed copy by default) with a fresh profile at one
protection level and run steps.py over a list of sites.

    run.py --level strict --dark on --sites sites.json --out OUT [--switch strict,maximum]
           [--base BASE] [--app /usr/lib/ike-browser] [--set key=json ...]

BASE is a profile made once with the real filter lists (--warm BASE makes it).
Without a network proxy variable the engine connects directly; with
HTTPS_PROXY set it is handed to the engine as --proxy-server.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
QUIET = {"app_updates": "off", "auto_update": False, "chrome_checked": 4102444800,
         "newtab_bg": "", "newtab_bg_118": True, "app_updates_1113": True}
WARM = '''
def steps(ike, qapp, out):
    import time
    from PyQt6.QtCore import QUrl
    win = ike.windows[0]
    t = time.time()
    while time.time() - t < %d:
        yield 2000
    out["ok"] = 1
'''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--level", default="balanced")
    ap.add_argument("--dark", default="on")
    ap.add_argument("--engine", default="ike", help="ike | engine (dark renderer)")
    ap.add_argument("--sites")
    ap.add_argument("--out")
    ap.add_argument("--switch", default="")
    ap.add_argument("--base")
    ap.add_argument("--warm")
    ap.add_argument("--app", default="/usr/lib/ike-browser")
    ap.add_argument("--set", action="append", default=[])
    ap.add_argument("--timeout", type=int, default=3600)
    ap.add_argument("--flags", default="", help="more engine switches")
    ap.add_argument("--x11", action="store_true", help="run on Xvfb (xcb) instead of offscreen: the GPU path of a desktop")
    a = ap.parse_args()

    tmp = Path(tempfile.mkdtemp(prefix="ike-compat-"))
    home = tmp / "home"
    cfgdir, datadir = home / ".config/ike-browser", home / ".local/share/ike-browser"
    if a.base and not a.warm:
        shutil.copytree(Path(a.base) / ".local", home / ".local")
        shutil.copytree(Path(a.base) / ".config", home / ".config")
    cfgdir.mkdir(parents=True, exist_ok=True)
    datadir.mkdir(parents=True, exist_ok=True)
    sp = cfgdir / "settings.json"
    data = json.loads(sp.read_text("utf-8")) if sp.exists() else {}
    data.update(QUIET)
    if not a.warm:
        data.update({"last_lists_update": 4102444800, "last_fast_update": 4102444800,
                     "last_darklists_update": 4102444800})
    data.update({"shield_level": a.level, "dark_mode": a.dark, "dark_engine": a.engine})
    for kv in a.set:
        k, v = kv.split("=", 1)
        data[k] = json.loads(v)
    sp.write_text(json.dumps(data), "utf-8")

    script = tmp / "steps.py"
    if a.warm:
        script.write_text(WARM % 90, "utf-8")
    else:
        shutil.copy(HERE / "steps.py", script)
    out_file = tmp / "out.json"
    flags = ["--no-sandbox"] + a.flags.split()
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    if proxy:
        flags.append("--proxy-server=" + proxy)
    e = {k: v for k, v in os.environ.items() if not k.startswith(("XDG_", "IKE_", "LANG", "LC_"))}
    e.update({
        "HOME": str(home), "XDG_CONFIG_HOME": str(home / ".config"),
        "XDG_DATA_HOME": str(home / ".local/share"), "XDG_CACHE_HOME": str(home / ".cache"),
        "XDG_RUNTIME_DIR": str(tmp / "run"), "QT_QPA_PLATFORM": "offscreen",
        "QTWEBENGINE_CHROMIUM_FLAGS": " ".join(flags), "QTWEBENGINE_DISABLE_SANDBOX": "1",
        "IKE_ALLOW_UNSAFE_ENGINE": "1", "LANG": "C.UTF-8", "IKE_NO_SINGLE": "1", "IKE_TEST_NOASK": "1",
        "IKE_TEST_HOOK": str(Path(a.app) / "tests/harness.py") if (Path(a.app) / "tests/harness.py").exists()
        else str(HERE.parent / "harness.py"),
        "IKE_TEST_SCRIPT": str(script), "IKE_TEST_OUT": str(out_file), "PYTHONUTF8": "1",
        "DBUS_SESSION_BUS_ADDRESS": "",
    })
    if not a.warm:
        e.update({"COMPAT_SITES": str(Path(a.sites).resolve()), "COMPAT_OUTDIR": str(Path(a.out).resolve()),
                  "COMPAT_PROBE": str(HERE / "probe.js"), "COMPAT_SWITCH": a.switch,
                  "COMPAT_PATCH": os.environ.get("COMPAT_PATCH", "")})
        Path(a.out).mkdir(parents=True, exist_ok=True)
    (tmp / "run").mkdir(mode=0o700, exist_ok=True)
    cfg_screen = tmp / "screen.json"
    cfg_screen.write_text(json.dumps({"screens": [{"name": "s", "x": 0, "y": 0, "width": 1366, "height": 900,
                                                  "logicalDpi": 96, "dpr": 1}]}), "utf-8")
    e["QT_QPA_PLATFORM"] = "offscreen:configfile=%s" % cfg_screen
    cmd = [sys.executable, str(Path(a.app) / "ike_boot.py")]
    if a.x11:
        e["QT_QPA_PLATFORM"] = "xcb"
        cmd = ["xvfb-run", "-a", "-s", "-screen 0 1366x900x24"] + cmd
    proc = subprocess.run(cmd, cwd=str(tmp), env=e,
                          capture_output=True, text=True, errors="replace", timeout=a.timeout)
    if a.warm:
        if Path(a.warm).exists():
            shutil.rmtree(a.warm)
        shutil.copytree(home, a.warm, ignore=shutil.ignore_patterns("*Cache*", "*cache*"))
        print("warm profile:", a.warm, "lists:", os.listdir(Path(a.warm) / ".local/share/ike-browser/lists"))
    else:
        (Path(a.out) / "stderr.txt").write_text(proc.stderr[-20000:], "utf-8")
        try:
            (Path(a.out) / "out.json").write_text(out_file.read_text("utf-8"), "utf-8")
        except FileNotFoundError:
            pass
    print("exit", proc.returncode)
    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
