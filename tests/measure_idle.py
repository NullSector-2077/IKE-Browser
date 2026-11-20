"""Processor time and memory of I.K.E. at rest and during ordinary use of its
interface, to compare two versions (same computer, same command).

    python tests/measure_idle.py [seconds]           this repository
    IKE_TEST_APP=/usr/lib/ike-browser python3 tests/measure_idle.py   an installed copy

The browser starts with an empty profile and the new tab page, as in the
tests. Measured over the whole process tree (browser, renderer, GPU, network):

  idle      CPU time used while nothing happens, as a share of one core
  interface the same while the toolbar is used: the mouse moves over the
            buttons, the shield panel and the menu open and close, two tabs
            are opened and closed
  memory    proportional set size (PSS) at the end, in MiB
"""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = Path(os.environ.get("IKE_TEST_APP") or ROOT)
TICK = os.sysconf("SC_CLK_TCK")
HOOK = '''
import json, os
from PyQt6.QtCore import QCoreApplication, QEvent, QPointF, Qt, QTimer
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QToolButton

SECONDS = float(os.environ["IKE_M_SECONDS"])

def mark(name):
    with open(os.environ["IKE_M_OUT"], "a") as f:
        f.write(name + "\\n")

def hover(widget):
    p = QPointF(widget.width() / 2, widget.height() / 2)
    QCoreApplication.sendEvent(widget, QMouseEvent(QEvent.Type.MouseMove, p, widget.mapToGlobal(p),
                               Qt.MouseButton.NoButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier))

def use_interface(win, until):
    import time
    buttons = [b for b in win.nav.findChildren(QToolButton) if b.isVisible()]
    state = {"i": 0}
    def step():
        if time.time() >= until:
            for m in (win.shield_menu, win.menu_btn.menu()):
                if m is not None:
                    m.hide()
            mark("interface-end")
            QTimer.singleShot(300, finish)
            return
        i = state["i"] = state["i"] + 1
        hover(buttons[i % len(buttons)])
        if i % 25 == 5:
            win.shield_menu.popup(win.shield_btn.mapToGlobal(win.shield_btn.rect().bottomLeft()))
        elif i % 25 == 12:
            win.shield_menu.hide()
            menu = win.menu_btn.menu()
            if menu is not None:
                menu.popup(win.menu_btn.mapToGlobal(win.menu_btn.rect().bottomLeft()))
        elif i % 25 == 18:
            menu = win.menu_btn.menu()
            if menu is not None:
                menu.hide()
            win.add_tab()
        elif i % 25 == 24 and len(win.views) > 1:
            win.close_tab(win.views[-1])
        QTimer.singleShot(80, step)
    step()

def finish():
    for w in list(ike.windows):
        w.close()
    QTimer.singleShot(100, qapp.quit)

def start():
    import time
    win = ike.windows[0]
    mark("idle-start")
    def interface():
        mark("idle-end")
        mark("interface-start")
        use_interface(win, time.time() + SECONDS)
    QTimer.singleShot(int(SECONDS * 1000), interface)

QTimer.singleShot(6000, start)          # let the start-up work end first
'''


def tree(pid):
    """pid and all its descendants."""
    children = {}
    for p in Path("/proc").iterdir():
        if not p.name.isdigit():
            continue
        try:
            stat = (p / "stat").read_text()
        except OSError:
            continue
        ppid = int(stat.rsplit(")", 1)[1].split()[1])
        children.setdefault(ppid, []).append(int(p.name))
    found, todo = [], [pid]
    while todo:
        cur = todo.pop()
        found.append(cur)
        todo += children.get(cur, [])
    return found


def cpu_seconds(pid):
    total = 0
    for p in tree(pid):
        try:
            fields = Path("/proc/%d/stat" % p).read_text().rsplit(")", 1)[1].split()
        except OSError:
            continue
        total += int(fields[11]) + int(fields[12])
    return total / TICK


def pss_mib(pid):
    total = 0
    for p in tree(pid):
        try:
            for line in Path("/proc/%d/smaps_rollup" % p).read_text().splitlines():
                if line.startswith("Pss:"):
                    total += int(line.split()[1])
        except OSError:
            continue
    return total / 1024


def main(seconds):
    work = Path(tempfile.mkdtemp(prefix="ike-idle-"))
    hook = work / "hook.py"
    hook.write_text(HOOK, "utf-8")
    home = work / "home"
    cfg = home / ".config" / "ike-browser"
    cfg.mkdir(parents=True)
    (cfg / "settings.json").write_text(json.dumps({
        "lists_version": 4, "last_lists_update": 4102444800, "last_fast_update": 4102444800,
        "chrome_checked": 4102444800, "app_updates": "off", "auto_update": False,
        "newtab_weather": False,
        **json.loads(os.environ.get("IKE_MEASURE_SETTINGS") or "{}")}))   # e.g. an interface theme
    lists = home / ".local/share/ike-browser/lists"
    lists.mkdir(parents=True)
    name = hashlib.sha1(b"https://easylist.to/easylist/easylist.txt").hexdigest()[:16] + ".txt"
    (lists / name).write_text("||ads.example.test^\n")
    marks = work / "marks"
    marks.write_text("")
    env = {k: v for k, v in os.environ.items() if not k.startswith(("XDG_", "IKE_"))}
    env.update(HOME=str(home), XDG_CONFIG_HOME=str(home / ".config"),
               XDG_DATA_HOME=str(home / ".local/share"), XDG_CACHE_HOME=str(home / ".cache"),
               QT_QPA_PLATFORM="offscreen", QTWEBENGINE_CHROMIUM_FLAGS="--no-sandbox", IKE_ALLOW_UNSAFE_ENGINE="1", IKE_NO_SINGLE="1",
               IKE_TEST_HOOK=str(hook), IKE_M_OUT=str(marks), IKE_M_SECONDS=str(seconds),
               DBUS_SESSION_BUS_ADDRESS="")
    proc = subprocess.Popen([sys.executable, str(APP / "ike_boot.py")], env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    seen, at, memory = 0, {}, [0.0]

    def watch():
        nonlocal seen
        while proc.poll() is None:
            lines = marks.read_text().split()
            for line in lines[seen:]:
                at[line] = (time.time(), cpu_seconds(proc.pid))
                if line == "interface-end":
                    memory[0] = pss_mib(proc.pid)
            seen = len(lines)
            time.sleep(0.02)
    t = threading.Thread(target=watch)
    t.start()
    proc.wait(timeout=seconds * 2 + 120)
    t.join()
    for phase in ("idle", "interface"):
        (t0, c0), (t1, c1) = at[phase + "-start"], at[phase + "-end"]
        print("%-9s %5.2f%% of one core (%.2f s of CPU in %.1f s)"
              % (phase, 100 * (c1 - c0) / (t1 - t0), c1 - c0, t1 - t0))
    print("memory    %.0f MiB (PSS, all processes)" % memory[0])


if __name__ == "__main__":
    main(float(sys.argv[1]) if len(sys.argv) > 1 else 20.0)
