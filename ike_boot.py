#!/usr/bin/env python3
"""I.K.E. bootstrap.

Chooses which copy of the program to run: the one installed by the package
manager (next to this file) or a newer, signature-verified update stored in the
user's data folder. A freshly installed update that fails to start is rolled
back automatically. This file is never replaced by a self-update.
"""

import json
import os
import re
import sys
from pathlib import Path

SYSTEM_DIR = Path(getattr(sys, "_MEIPASS", None) or Path(__file__).resolve().parent)
if os.environ.get("XDG_DATA_HOME") or sys.platform != "win32":
    _DATA = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")
else:      # the same folder as ike/osinfo.py's app_dir("data")
    _DATA = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
UPDATES = _DATA / "ike-browser" / "updates"
STATE = UPDATES / "state.json"


def vtuple(v):
    return tuple(int(x) for x in re.findall(r"\d+", v or "0")[:4])


def version_in(folder):
    try:
        text = (Path(folder) / "ike" / "__init__.py").read_text("utf-8")
        return re.search(r'__version__\s*=\s*"([^"]+)"', text).group(1)
    except Exception:
        return None


def load_state():
    try:
        return json.loads(STATE.read_text("utf-8"))
    except Exception:
        return {}


def save_state(state):
    try:
        UPDATES.mkdir(parents=True, exist_ok=True)
        tmp = STATE.with_suffix(".tmp")
        tmp.write_text(json.dumps(state), "utf-8")
        tmp.replace(STATE)
    except OSError:
        pass


def version_dir(version):
    return UPDATES / "versions" / version if version else None


def usable(version, sysver):
    d = version_dir(version)
    return bool(d and version_in(d) == version and vtuple(version) > vtuple(sysver))


def rollback(state, sysver, reason):
    bad = state.get("current")
    prev = state.get("previous")
    if bad and bad not in state.setdefault("bad", []):
        state["bad"].append(bad)          # never install this version again
    state.update({"current": prev if usable(prev, sysver) else None, "previous": None,
                  "status": "ok", "attempts": 0, "rolled_back": bad, "rollback_reason": reason})
    save_state(state)
    return version_dir(state["current"]) if state["current"] else SYSTEM_DIR


def choose():
    sysver = version_in(SYSTEM_DIR) or "0"
    state = load_state()
    cur = state.get("current")
    if not cur:
        return SYSTEM_DIR, state, sysver
    if not usable(cur, sysver):
        # removed, damaged, or the package manager installed something newer
        state.update({"current": None, "previous": None, "status": "ok", "attempts": 0})
        save_state(state)
        return SYSTEM_DIR, state, sysver
    if state.get("status") == "pending":
        if state.get("attempts", 0) >= 1:
            return rollback(state, sysver, "did not start correctly"), state, sysver
        state["attempts"] = state.get("attempts", 0) + 1
        save_state(state)
    return version_dir(cur), state, sysver


def run(folder):
    for name in [m for m in sys.modules if m == "ike" or m.startswith("ice.")]:
        del sys.modules[name]
    sys.path[:] = [p for p in sys.path if p != str(folder)]
    sys.path.insert(0, str(folder))
    vendor = SYSTEM_DIR / "vendor"
    if vendor.is_dir() and str(vendor) not in sys.path:
        sys.path.append(str(vendor))
    os.environ["IKE_APP_DIR"] = str(folder)
    os.environ["IKE_SYSTEM_DIR"] = str(SYSTEM_DIR)
    import ice
    ice.early_args(sys.argv[1:])
    from ice.app import main
    return main()


def windows_check(argv):
    """Windows: a newly installed version (a whole app/<version> folder) whose
    first start was not confirmed is given up at the next start; the launcher
    goes back to the previous folder (see ike/updater.py, replace_windows)."""
    root = os.environ.get("ICE_INSTALL_DIR")
    launcher = os.environ.get("ICE_LAUNCHER")
    if os.environ.get("ICE_PACKAGE") != "windows" or not root or not launcher:
        return
    state = load_state()
    win = state.get("windows") or {}
    mine = version_in(SYSTEM_DIR)
    if win.get("status") != "pending" or win.get("version") != mine:
        return
    if win.get("attempts", 0) < 1:
        win["attempts"] = 1
        save_state(state)
        return
    prev = win.get("previous") or ""
    if not (re.fullmatch(r"[0-9A-Za-z._-]+", prev) and ".." not in prev
            and (Path(root) / "app" / prev / "ike_boot.py").is_file()):
        return                     # nothing to go back to: keep trying this one
    tmp = Path(root) / "current.tmp"
    tmp.write_text(prev, "utf-8")
    tmp.replace(Path(root) / "current")
    if mine not in state.setdefault("bad", []):
        state["bad"].append(mine)
    win.update({"status": "rolled_back"})
    state.update({"rolled_back": mine, "rollback_reason": "did not start correctly"})
    save_state(state)
    import subprocess
    subprocess.Popen([launcher] + argv, close_fds=True)
    sys.exit(0)


def main():
    argv = sys.argv[1:]
    if (len(argv) == 2 and argv[0] == "--selftest-import") or argv == ["--selftest"]:
        # used by the updater to check a downloaded version (or AppImage)
        # before installing it
        sys.path.insert(0, argv[1] if len(argv) == 2 else str(SYSTEM_DIR))
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        import ice
        import ice.app  # noqa: F401  (every module must load)
        import ice.dialogs
        import ice.updater
        import ice.window
        print("IKE-SELFTEST-OK %s" % ice.__version__)
        return 0
    windows_check(argv)
    folder, state, sysver = choose()
    if folder == SYSTEM_DIR:
        return run(folder)
    try:
        return run(folder)
    except SystemExit:
        raise
    except BaseException as exc:      # the update is broken: go back at once
        if sys.stderr:                 # None without a console (Windows)
            sys.stderr.write("I.K.E.: update %s failed to start (%r), rolling back\n"
                             % (state.get("current"), exc))
        return run(rollback(state, sysver, repr(exc)[:200]))


if __name__ == "__main__":
    sys.exit(main())
