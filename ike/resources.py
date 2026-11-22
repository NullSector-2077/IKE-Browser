"""Per-site resources: memory, CPU and network of each site, and optional limits.

Memory and CPU come from the page's renderer process (``/proc/<pid>`` on
Linux: proportional memory from ``smaps_rollup`` and CPU time from ``stat``);
tabs of the same site share their numbers when they share a process. Network
is the number of requests made for the site (counted by the shield) and the
data the page reports through its own resource timing, so some third-party
files show as zero bytes: the figure is a lower bound.

Nothing is measured while the window is closed and no limit is set. With a
limit, background tabs are checked every few seconds:
- over the memory limit: the site's background tabs are suspended (the
  memory is freed; the page reloads when the tab is opened again);
- over the CPU limit for three checks in a row: they are frozen (the page
  stops running until the tab is opened again).
The tab being looked at, tabs playing sound and the split-view tab are never
touched. Qt WebEngine offers no way to cap CPU or network use itself.
"""

import os
import time

from PyQt6.QtCore import QObject, Qt, QTimer
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineScript
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from .i18n import T
from .shields import site_of
from .uistyle import Switch

_WORLD = QWebEngineScript.ScriptWorldId.ApplicationWorld   # unseen by the page
CHECK_MS = 5000
CPU_STRIKES = 3
_TICKS = os.sysconf("SC_CLK_TCK")

_NET_JS = r"""(function () {
  try {
    if (!window.__ikeRes) { window.__ikeRes = 1; performance.setResourceTimingBufferSize(5000); }
    var t = 0, e = performance.getEntriesByType('navigation').concat(performance.getEntriesByType('resource'));
    for (var i = 0; i < e.length; i++) t += e[i].transferSize || e[i].encodedBodySize || 0;
    return t;
  } catch (x) { return 0; }
})()"""


def proc_memory(pid):
    """Memory of a process in bytes (proportional set size), or None."""
    try:
        with open("/proc/%d/smaps_rollup" % pid, encoding="ascii") as f:
            for line in f:
                if line.startswith("Pss:"):
                    return int(line.split()[1]) * 1024
    except (OSError, ValueError):
        pass
    try:
        with open("/proc/%d/status" % pid, encoding="ascii") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) * 1024
    except (OSError, ValueError):
        pass
    return None


def proc_cpu_ticks(pid):
    """User + system CPU time of a process in clock ticks, or None."""
    try:
        with open("/proc/%d/stat" % pid, encoding="ascii") as f:
            data = f.read()
        fields = data[data.rindex(")") + 2:].split()
        return int(fields[11]) + int(fields[12])
    except (OSError, ValueError, IndexError):
        return None


def site_of_view(view):
    url = view.url()
    if url.scheme() not in ("http", "https", "file"):
        return ""
    return site_of(url.host().lower()) or ("file" if url.scheme() == "file" else "")


def pid_of(view):
    if getattr(view, "sleeping", False) or getattr(view, "pending_url", None):
        return 0
    try:
        return int(view.page().renderProcessPid() or 0)
    except Exception:
        return 0


class Monitor(QObject):
    """Samples the open tabs; enforces the user's limits on background tabs."""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self._cpu = {}          # pid -> (ticks, time)
        self.cpu_pct = {}       # pid -> % of one core since the previous sample
        self.net = {}           # id(view) -> bytes reported by the page
        self._strikes = {}      # site -> CPU checks over the limit in a row
        self.watchers = 0       # open resource windows
        self.timer = QTimer(self)
        self.timer.setInterval(CHECK_MS)
        self.timer.timeout.connect(self._tick)
        self.settings_changed()

    def limits(self):
        cfg = self.app.config
        if not cfg.get("ext_resources", True):        # the extension is off (1.1.20)
            return 0, 0
        return max(0, int(cfg["res_mem_limit"] or 0)), max(0, int(cfg["res_cpu_limit"] or 0))

    def settings_changed(self):
        mem, cpu = self.limits()
        if mem or cpu:
            self.timer.start()
        else:
            self.timer.stop()
            self._strikes.clear()

    def views(self):
        for w in list(self.app.windows):
            for v in w.all_views():
                yield w, v

    def sample(self, net=True):
        """[{site, tabs, pids, memory, cpu, requests, data, frozen, sleeping, views}] sorted by memory.

        net=False: the limits' own check, which needs memory and CPU only; the
        pages are not asked for the data they downloaded (it would wake every
        background tab every few seconds for a column nobody sees, 1.1.17)."""
        now = time.monotonic()
        sites = {}
        seen = set()
        for _w, v in self.views():
            site = site_of_view(v)
            if not site:
                continue
            row = sites.setdefault(site, {"site": site, "views": [], "pids": set(), "data": 0,
                                          "sleeping": 0, "frozen": 0})
            row["views"].append(v)
            if getattr(v, "sleeping", False) or getattr(v, "pending_url", None):
                row["sleeping"] += 1
                continue
            if getattr(v, "frozen", False):
                row["frozen"] += 1
            pid = pid_of(v)
            if pid:
                row["pids"].add(pid)
            row["data"] += self.net.get(id(v), 0)
            if net:
                v.page().runJavaScript(_NET_JS, _WORLD, lambda n, k=id(v): self.net.__setitem__(k, int(n or 0)))
        for row in sites.values():
            mem, cpu, known = 0, 0.0, False
            for pid in row["pids"]:
                m = proc_memory(pid)
                if m is not None:
                    mem += m
                    known = True
                if pid in seen:
                    continue
                seen.add(pid)
                ticks = proc_cpu_ticks(pid)
                if ticks is None:
                    continue
                prev = self._cpu.get(pid)
                self._cpu[pid] = (ticks, now)
                if prev and now > prev[1]:
                    self.cpu_pct[pid] = 100.0 * (ticks - prev[0]) / _TICKS / (now - prev[1])
                cpu += self.cpu_pct.get(pid, 0.0)
            row["memory"] = mem if known else None
            row["cpu"] = cpu if known else None
            row["tabs"] = len(row["views"])
            row["requests"] = self.app.shields.requests.get(row["site"], 0)
        for pid in list(self._cpu):
            if pid not in seen:
                self._cpu.pop(pid, None)
                self.cpu_pct.pop(pid, None)
        alive = {id(v) for _w, v in self.views()}
        for k in list(self.net):
            if k not in alive:
                self.net.pop(k)
        return sorted(sites.values(), key=lambda r: -(r["memory"] or 0))

    # --- limits ----------------------------------------------------------
    def _background(self, win, view):
        if view is win.current_view() or view is getattr(win, "split", None):
            return False
        if getattr(view, "sleeping", False) or getattr(view, "pending_url", None):
            return False
        try:
            return not view.page().recentlyAudible()
        except Exception:
            return False

    def _tick(self):
        mem_mb, cpu_pct = self.limits()
        if not (mem_mb or cpu_pct):
            return
        rows = self.sample(net=bool(self.watchers))     # the window shows the data column
        owner = {id(v): w for w, v in self.views()}
        for row in rows:
            site = row["site"]
            over_mem = mem_mb and row["memory"] is not None and row["memory"] > mem_mb * 1024 * 1024
            if cpu_pct and row["cpu"] is not None and row["cpu"] > cpu_pct:
                self._strikes[site] = self._strikes.get(site, 0) + 1
            else:
                self._strikes.pop(site, None)
            over_cpu = self._strikes.get(site, 0) >= CPU_STRIKES
            if not (over_mem or over_cpu):
                continue
            for v in row["views"]:
                w = owner.get(id(v))
                if w is None or not self._background(w, v):
                    continue
                if over_mem:
                    self.suspend(w, v)
                elif not getattr(v, "frozen", False):
                    self.freeze(v)
            self._strikes.pop(site, None)

    def suspend(self, win, view):
        if view in win.views:
            return bool(win._suspend(view))
        try:
            view.page().setLifecycleState(QWebEnginePage.LifecycleState.Discarded)
            view.sleeping = True
            return True
        except Exception:
            return False

    @staticmethod
    def freeze(view):
        try:
            view.page().setLifecycleState(QWebEnginePage.LifecycleState.Frozen)
        except Exception:
            return False
        view.frozen = view.page().lifecycleState() == QWebEnginePage.LifecycleState.Frozen
        return view.frozen

    @staticmethod
    def wake(view):
        """A frozen tab is shown again."""
        if getattr(view, "frozen", False):
            view.frozen = False
            try:
                view.page().setLifecycleState(QWebEnginePage.LifecycleState.Active)
            except Exception:
                pass


def _size(n):
    if n is None:
        return "—"
    if n < 1024 * 1024:
        return "%d KB" % max(0, n // 1024)
    if n < 1024 ** 3:
        return "%.0f MB" % (n / 1024 / 1024)
    return "%.1f GB" % (n / 1024 ** 3)


class ResourcesDialog(QDialog):
    COLS = ("Site", "Tabs", "Memory", "CPU", "Requests", "Data", "State")

    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self.mon = app.resources
        self.rows = []
        self.setWindowTitle(T("Site resources"))
        self.resize(720, 460)
        lay = QVBoxLayout(self)
        self.table = QTableWidget(0, len(self.COLS), self)
        self.table.setHorizontalHeaderLabels([T(c) for c in self.COLS])
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for c in range(1, len(self.COLS)):
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        lay.addWidget(self.table, 1)
        note = QLabel(T("CPU is the share of one processor core. Data counts what the pages report: "
                        "some files from other sites are not included."), self)
        note.setWordWrap(True)
        lay.addWidget(note)
        row = QHBoxLayout()
        self.suspend_btn = QPushButton(T("Suspend this site's background tabs"), self)
        self.suspend_btn.clicked.connect(self._suspend_selected)
        row.addWidget(self.suspend_btn)
        row.addStretch(1)
        lay.addLayout(row)

        mem, cpu = self.mon.limits()
        cfg = app.config
        self.mem_on = Switch(T("Suspend background tabs of a site using more memory than"), self)
        self.mem = QSpinBox(self)
        self.mem.setRange(100, 64000)
        self.mem.setSingleStep(100)
        self.mem.setSuffix(" MB")
        self.mem.setValue(mem or int(cfg["res_mem_default"]))
        self.mem_on.setChecked(bool(mem))
        self.cpu_on = Switch(T("Freeze background tabs of a site using more CPU than"), self)
        self.cpu = QSpinBox(self)
        self.cpu.setRange(5, 400)
        self.cpu.setSingleStep(5)
        self.cpu.setSuffix(" %")
        self.cpu.setValue(cpu or int(cfg["res_cpu_default"]))
        self.cpu_on.setChecked(bool(cpu))
        for check, spin in ((self.mem_on, self.mem), (self.cpu_on, self.cpu)):
            r = QHBoxLayout()
            r.addWidget(check)
            r.addWidget(spin)
            r.addStretch(1)
            lay.addLayout(r)
            check.toggled.connect(self._limits_changed)
            spin.valueChanged.connect(self._limits_changed)
        hint = QLabel(T("The tab you are looking at and tabs playing sound are never touched. "
                        "A suspended or frozen tab comes back when you open it."), self)
        hint.setWordWrap(True)
        lay.addWidget(hint)
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        box.rejected.connect(self.close)
        lay.addWidget(box)
        self.timer = QTimer(self)
        self.timer.setInterval(2000)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        self.mon.watchers += 1
        self.refresh()
        QTimer.singleShot(400, self.refresh)        # CPU needs two samples

    def _limits_changed(self, *_):
        cfg = self.app.config
        cfg["res_mem_limit"] = self.mem.value() if self.mem_on.isChecked() else 0
        cfg["res_cpu_limit"] = self.cpu.value() if self.cpu_on.isChecked() else 0
        cfg["res_mem_default"], cfg["res_cpu_default"] = self.mem.value(), self.cpu.value()
        cfg.save()
        self.mon.settings_changed()

    def refresh(self):
        if self.isMinimized():
            return                       # nobody looks: the next refresh after it is shown again
        sel = self.table.currentRow()
        site = self.rows[sel]["site"] if 0 <= sel < len(self.rows) else None
        self.rows = self.mon.sample()
        self.table.setRowCount(len(self.rows))
        for r, row in enumerate(self.rows):
            if row["sleeping"] == row["tabs"]:
                state = T("Suspended")
            elif row["frozen"]:
                state = T("Frozen")
            else:
                state = ""
            cpu = "—" if row["cpu"] is None else "%.0f %%" % row["cpu"]
            vals = (row["site"], str(row["tabs"]), _size(row["memory"]), cpu,
                    str(row["requests"]), _size(row["data"]), state)
            for c, val in enumerate(vals):
                it = self.table.item(r, c)
                if it is None:
                    it = QTableWidgetItem()
                    self.table.setItem(r, c, it)
                it.setText(val)
                if c:
                    it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if row["site"] == site:
                self.table.selectRow(r)
        self.suspend_btn.setEnabled(bool(self.rows))

    def _suspend_selected(self):
        r = self.table.currentRow()
        if not 0 <= r < len(self.rows):
            return
        owner = {id(v): w for w, v in self.mon.views()}
        for v in self.rows[r]["views"]:
            w = owner.get(id(v))
            if w is not None and self.mon._background(w, v):
                self.mon.suspend(w, v)
        self.refresh()

    def closeEvent(self, event):
        if self.timer.isActive():
            self.timer.stop()
            self.mon.watchers -= 1
        super().closeEvent(event)
