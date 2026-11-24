"""The list of downloads shown by the toolbar's Downloads panel (1.1.25,
downloadpanel.py).

One Entry per download: the file's name, where it is, its address, its size,
its state, when, the site; while it runs, the engine's own request
(QWebEngineDownloadRequest) gives the bytes, and the speed is smoothed from
the bytes over time. Downloads stopped by I.K.E.'s checks (safedownload.py)
are listed too, with the reason.

The list survives a restart (the owner's choice): the last KEEP entries of
normal windows, their metadata only (name, place, address, size, state, time,
site, a short note), in I.K.E.'s own database (storage.py, next to the
history). A private window's downloads are listed in private windows only and
never written anywhere. Clearing the history (or all browsing data) clears
the list too.
"""

import time
from urllib.parse import urlsplit

from PyQt6.QtCore import QObject, pyqtSignal

KEEP = 50                      # entries kept across restarts
LIVE = ("running", "paused")   # states of a download still going on
SMOOTH = 0.3                   # weight of the newest speed sample


class Entry:
    """One download in the list."""

    def __init__(self, name="", path="", url="", size=0, state="done", when=0, host="", note="",
                 private=False):
        self.name, self.path, self.url = name or "", path or "", url or ""
        self.size, self.got = int(size or 0), int(size or 0) if state == "done" else 0
        self.state, self.when, self.host, self.note = state, int(when or time.time()), host or "", note or ""
        self.private = bool(private)
        self.item = None             # the engine's request while it is known
        self.known = False           # a program from a site visited before (safedownload)
        self.risk = None             # stopped: what safedownload.risk found
        self.anyway = None           # stopped in this session: lets it through, at the user's risk
        self.speed = None            # bytes per second, smoothed
        self._sample = None

    @property
    def live(self):
        return self.state in LIVE

    def fraction(self):
        return min(1.0, self.got / self.size) if self.size > 0 else None

    def left(self):
        """Seconds still needed at the present speed, or None."""
        if self.state != "running" or not self.speed or self.size <= 0:
            return None
        return max(0.0, (self.size - self.got) / self.speed)

    def sync(self, path_of=None, now=None):
        """Read the engine's request: the state, the bytes, the speed. True when the
        state changed."""
        item = self.item
        if item is None:
            return False
        from PyQt6.QtWebEngineCore import QWebEngineDownloadRequest as DR
        S = DR.DownloadState
        try:
            st, got, total, paused = item.state(), item.receivedBytes(), item.totalBytes(), item.isPaused()
            reason = item.interruptReasonString() if st == S.DownloadInterrupted else ""
            path = str(path_of(item)) if path_of is not None else ""
        except RuntimeError:                 # deleted by the engine
            self.item = None
            if self.live:
                self.state = "failed"
                return True
            return False
        state = {S.DownloadCompleted: "done", S.DownloadCancelled: "cancelled",
                 S.DownloadInterrupted: "failed"}.get(st, "paused" if paused else "running")
        if path:
            self.path, self.name = path, path.rsplit("/", 1)[-1] or self.name
        self.got = got
        if total > 0:
            self.size = total
        now = time.monotonic() if now is None else now
        if state == "running":
            if self._sample is not None:
                t, before = self._sample
                if now - t >= 0.25:
                    rate = max(0.0, (got - before) / (now - t))
                    self.speed = rate if self.speed is None else (1 - SMOOTH) * self.speed + SMOOTH * rate
                    self._sample = (now, got)
            else:
                self._sample = (now, got)
        else:
            self.speed, self._sample = None, None
        changed = state != self.state
        if changed:
            self.state = state
            if state == "failed":
                self.note = reason
            if not self.live:
                self.when = int(time.time())
        return changed

    def row(self):
        return (self.name, self.path, self.url, self.size, self.state, self.when, self.host, self.note)


def host_of(url):
    try:
        return (urlsplit(url or "").hostname or "").lower()
    except ValueError:
        return ""


class DownloadList(QObject):
    """Every download of this session, and the last ones of earlier sessions."""

    changed = pyqtSignal()

    def __init__(self, storage=None, path_of=None, parent=None):
        super().__init__(parent)
        self.storage = storage
        self.path_of = path_of
        self.entries = []            # the newest first
        self.load()

    # --- what is shown ---------------------------------------------------
    def shown(self, private=False):
        """The entries of normal windows, or of private ones."""
        return [e for e in self.entries if e.private == bool(private)]

    def running(self, private=False):
        return [e for e in self.shown(private) if e.state == "running"]

    # --- new entries ---------------------------------------------------------
    def add_live(self, item, private=False, known=False):
        """A download the engine started."""
        url = item.url().toString()
        e = Entry(item.downloadFileName(), "", url, max(0, item.totalBytes()), "running", time.time(),
                  host_of(url), private=private)
        e.item, e.known = item, bool(known)
        e.sync(self.path_of)
        self.entries.insert(0, e)
        for signal in ("isFinishedChanged", "isPausedChanged", "stateChanged"):
            sig = getattr(item, signal, None)
            if sig is not None:
                sig.connect(lambda *_a, x=e: self._item_changed(x))
        self._changed()
        return e

    def add_stopped(self, url, name, risk, private=False):
        """A download stopped by I.K.E.'s checks: listed with the reason."""
        e = Entry(name, "", url, 0, "stopped", time.time(), host_of(url), (risk or {}).get("kind", ""),
                  private=private)
        e.risk = risk
        self.entries.insert(0, e)
        self._changed()
        return e

    def _item_changed(self, e):
        if e.sync(self.path_of):
            self._changed()

    def update_item(self, item):
        """The file of a download was moved to the place the user chose: read it again."""
        for e in self.entries:
            if e.item is item:
                e.sync(self.path_of)
                self._changed()
                return

    def tick(self):
        """While files arrive: their bytes and speed (app._download_tick)."""
        changed = False
        for e in self.entries:
            if e.item is not None and e.live:
                changed |= e.sync(self.path_of)
        if changed:
            self._changed()

    # --- removing ------------------------------------------------------------
    def remove(self, e):
        if e in self.entries:
            self.entries.remove(e)
            self._changed()

    def clear(self, private=False):
        """The finished, failed and stopped entries of normal (or private) windows
        leave the list; the downloads still going on stay; the files stay on the disk."""
        gone = [e for e in self.shown(private) if not e.live]
        if gone:
            self.entries[:] = [e for e in self.entries if e not in gone]
            self._changed()
        return gone

    def forget(self):
        """The history was cleared: every entry of normal windows that has ended goes,
        and nothing of them stays written."""
        self.entries[:] = [e for e in self.entries if e.private or e.live]
        if self.storage is not None:
            self.storage.clear_downloads()
        self._changed(save=False)

    # --- kept across restarts ----------------------------------------------
    def load(self):
        if self.storage is None:
            return
        try:
            rows = self.storage.downloads(KEEP)
        except Exception:
            return
        for name, path, url, size, state, when, host, note in rows:
            if state in LIVE:             # cut by the end of the last session
                state, note = "failed", note or ""
            if state not in ("done", "failed", "cancelled", "stopped"):
                continue
            self.entries.append(Entry(str(name or ""), str(path or ""), str(url or ""), size, state, when,
                                      str(host or ""), str(note or "")))

    def save(self):
        """The last KEEP entries of normal windows; a private window's never."""
        if self.storage is None:
            return
        rows = [e.row() for e in self.entries if not e.private][:KEEP]
        try:
            self.storage.set_downloads(rows)
        except Exception:
            pass

    def _changed(self, save=True):
        if save:
            self.save()
        self.changed.emit()


# --- texts ---------------------------------------------------------------------
def _locale():
    """The interface's language, for numbers, times and dates."""
    from PyQt6.QtCore import QLocale

    from . import i18n
    return QLocale(i18n.current())


def size_text(n):
    """1,2 MB: the size with the decimal mark of the interface's language."""
    n = float(max(0, n or 0))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            if unit == "B":
                return "%d %s" % (n, unit)
            return "%s %s" % (_locale().toString(n, "f", 1), unit)
        n /= 1024.0
    return ""


def time_left(seconds):
    from .i18n import T
    if seconds is None:
        return ""
    if seconds < 60:
        return T("%d s left") % max(1, round(seconds))
    if seconds < 90 * 60:
        return T("%d min left") % round(seconds / 60)
    return T("%d h left") % round(seconds / 3600)


def when_text(when):
    """The time of today, or the date of an earlier day, as the language writes it."""
    from PyQt6.QtCore import QDate, QDateTime, QLocale
    t = QDateTime.fromSecsSinceEpoch(int(when or 0))
    fmt = QLocale.FormatType.ShortFormat
    if t.date() == QDate.currentDate():
        return _locale().toString(t.time(), fmt)
    return _locale().toString(t.date(), fmt)


def stop_text(kind):
    """Why I.K.E.'s checks stopped a download (safedownload.risk's kind), in short."""
    from .i18n import T
    if kind == "mixed":
        return T("Stopped by I.K.E.: a file without protection (http) on a secure page")
    if kind == "listed":
        return T("Stopped by I.K.E.: the site is on the protection lists")
    return T("Stopped by I.K.E.: a program from a site never visited")


def status(e):
    """The one line under the file's name."""
    from .i18n import T
    sep = " · "
    if e.state == "running":
        parts = [T("%s of %s") % (size_text(e.got), size_text(e.size)) if e.size > 0 else size_text(e.got)]
        if e.speed:
            parts.append("%s/s" % size_text(e.speed))
        if e.left() is not None and e.speed:
            parts.append(time_left(e.left()))
        return sep.join(parts)
    if e.state == "paused":
        done = T("%s of %s") % (size_text(e.got), size_text(e.size)) if e.size > 0 else size_text(e.got)
        return T("Paused") + sep + done
    if e.state == "stopped":
        return stop_text(e.note)
    if e.state == "failed":
        return T("Failed") + (sep + e.note if e.note else "")
    if e.state == "cancelled":
        return sep.join(x for x in (T("Cancelled"), e.host) if x)
    if e.known:
        return size_text(e.size) + sep + T("Program from a site you visited before")
    return sep.join(x for x in (size_text(e.size), e.host, when_text(e.when)) if x)
