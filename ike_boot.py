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

SYSTEM_DIR = Path(__file__).resolve().parent
_DATA = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")
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
    """The updater's notes, or {} when the file is missing or not what it should be."""
    try:
        state = json.loads(STATE.read_text("utf-8"))
    except Exception:
        return {}
    if not isinstance(state, dict):
        return {}
    if not isinstance(state.get("bad", []), list):
        state["bad"] = []
    if not isinstance(state.get("attempts", 0), int):
        state["attempts"] = 0
    return state


def save_state(state):
    try:
        UPDATES.mkdir(parents=True, exist_ok=True)
        # its own temporary name: two profiles of I.K.E. may write at the same time (1.1.17)
        tmp = STATE.with_name("state.%d.tmp" % os.getpid())
        tmp.write_text(json.dumps(state), "utf-8")
        tmp.replace(STATE)
    except OSError:
        pass


def version_dir(version):
    # the state file is only data: a "version" that is not one (a path, say)
    # is never turned into a folder to run code from
    if not isinstance(version, str) or not re.fullmatch(r"\d+(\.\d+){1,3}", version):
        return None
    return UPDATES / "versions" / version


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
    return version_dir(state["current"]) or SYSTEM_DIR


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
    for name in [m for m in sys.modules if m == "ike" or m.startswith("ike.")]:
        del sys.modules[name]
    sys.path[:] = [p for p in sys.path if p != str(folder)]
    sys.path.insert(0, str(folder))
    vendor = SYSTEM_DIR / "vendor"
    if vendor.is_dir() and str(vendor) not in sys.path:
        sys.path.append(str(vendor))
    os.environ["IKE_APP_DIR"] = str(folder)
    os.environ["IKE_SYSTEM_DIR"] = str(SYSTEM_DIR)
    import ike
    ike.early_args(sys.argv[1:])
    from ike.app import main
    return main()


def main():
    argv = sys.argv[1:]
    if (len(argv) == 2 and argv[0] == "--selftest-import") or argv == ["--selftest"]:
        # used by the updater to check a downloaded version before installing it
        sys.path.insert(0, argv[1] if len(argv) == 2 else str(SYSTEM_DIR))
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        import ike
        import ike.app  # noqa: F401  (every module must load)
        import ike.dialogs
        import ike.updater
        import ike.window
        print("IKE-SELFTEST-OK %s" % ike.__version__)
        return 0
    if (hasattr(os, "geteuid") and os.geteuid() == 0 and os.environ.get("IKE_ALLOW_UNSAFE_ENGINE") != "1"
            and not {"--version", "-h", "--help"} & set(argv)):
        # refused here, before a pending update is counted as a start that
        # failed (adversarial review of 1.1.18; ike/app.py says the same)
        sys.stderr.write("I.K.E.: I.K.E. does not start as root (administrator): the engine's sandbox, "
                         "which keeps web pages away from the computer, cannot work there. Start it as "
                         "your normal user. To start it as root anyway, without the sandbox and at your "
                         "own risk, set IKE_ALLOW_UNSAFE_ENGINE=1.\n")
        return 1
    folder, state, sysver = choose()
    if folder == SYSTEM_DIR:
        return run(folder)
    try:
        return run(folder)
    except SystemExit:
        raise
    except BaseException as exc:      # the update is broken: go back at once
        if sys.stderr:
            sys.stderr.write("I.K.E.: update %s failed to start (%r), rolling back\n"
                             % (state.get("current"), exc))
        return run(rollback(state, sysver, repr(exc)[:200]))


if __name__ == "__main__":
    sys.exit(main())
