"""The panel of the toolbar's Downloads button (1.1.25): ike/downloadpanel.py, ike/downloadlist.py.

- the list: one entry per download, its state read from the engine, the speed
  smoothed from the bytes over time; the last 50 entries of normal windows kept
  across restarts (metadata only, in I.K.E.'s database), never a private
  window's; clearing the history clears it;
- the panel in the real browser: Ctrl+J and the button open it, under the
  button; the empty state; a finished download (its row, its actions, the
  right-click menu, "Copy link address"); pause and resume with the bytes
  standing still while paused; a failed download and "Retry" through the
  normal path; a download stopped by I.K.E.'s checks, listed with the reason,
  and "Download anyway…" asking the same question again with "Cancel" chosen;
  a program from a site visited before; "Remove from list", "Clear the list"
  (running downloads and the files stay); a private window's downloads; the
  green ring goes when the panel opens; everything on one left edge and one
  right edge, each text centred with its icon;
- after a restart: the list is back (a download cut by a crash is "failed");
  clearing the history empties it.
All on this computer: a local server.
"""

import http.server
import threading
import time

import pytest
from conftest import screen

from ike.downloadlist import KEEP, DownloadList, Entry, size_text, status, time_left

# --- the list ------------------------------------------------------------------

class FakeItem:
    """What downloadlist reads of the engine's request."""

    def __init__(self, total=1000):
        from PyQt6.QtWebEngineCore import QWebEngineDownloadRequest as DR
        self.S = DR.DownloadState
        self._state, self.got, self.total, self.paused = self.S.DownloadInProgress, 0, total, False

    def state(self):
        return self._state

    def receivedBytes(self):
        return self.got

    def totalBytes(self):
        return self.total

    def isPaused(self):
        return self.paused

    def interruptReasonString(self):
        return "Network error"


def test_states_speed_and_time_left():
    item = FakeItem(10_000_000)
    e = Entry("a.iso", "/tmp/a.iso", "https://example.org/a.iso", 0, "running")
    e.item = item
    assert e.sync(None, now=0.0) is False and e.state == "running" and e.speed is None
    item.got = 1_000_000
    e.sync(None, now=1.0)
    assert e.speed == pytest.approx(1_000_000)
    item.got = 3_000_000                       # 2 MB/s now: smoothed, not jumping
    e.sync(None, now=2.0)
    assert 1_000_000 < e.speed < 2_000_000
    assert e.left() == pytest.approx((10_000_000 - 3_000_000) / e.speed)
    item.paused = True
    assert e.sync(None, now=3.0) is True and e.state == "paused" and e.speed is None and e.left() is None
    item.paused = False
    e.sync(None, now=4.0)
    item._state = item.S.DownloadInterrupted
    assert e.sync(None, now=5.0) is True and e.state == "failed" and e.note == "Network error"
    item._state = item.S.DownloadCompleted
    e.sync(None, now=6.0)
    assert e.state == "done" and e.fraction() == pytest.approx(0.3)


def test_texts():
    from ike import i18n
    i18n.setup("it")
    try:
        assert size_text(1234567) == "1,2 MB" and size_text(12) == "12 B"
        assert time_left(30) == "30 s rimanenti" and time_left(300) == "5 min rimanenti"
        assert time_left(4 * 3600) == "4 h rimanenti"
        e = Entry("x.zip", "", "https://files.example/x.zip", 137 * 1024 * 1024, "paused")
        e.got = 48 * 1024 * 1024
        assert status(e) == "In pausa · 48,0 MB di 137,0 MB"
        e.state, e.note = "stopped", "new"
        assert status(e) == "Fermato da I.K.E.: programma da un sito mai visitato"
        e.state, e.note = "failed", ""
        assert status(e) == "Non riuscito"
        e.state, e.known = "done", True
        assert status(e) == "137,0 MB · Programma da un sito già visitato"
    finally:
        i18n.setup("en")


def test_kept_across_restarts_private_never(tmp_path):
    from ike.storage import Storage
    st = Storage(tmp_path / "ike.sqlite")
    log = DownloadList(st)
    for i in range(KEEP + 10):
        log.entries.insert(0, Entry("f%d.txt" % i, "/d/f%d.txt" % i, "https://a.example/%d" % i, i, "done",
                                    1000 + i, "a.example"))
    log.entries.insert(0, Entry("secret.txt", "/d/secret.txt", "https://private.example/s", 5, "done",
                                2000, "private.example", private=True))
    log.entries.insert(0, Entry("cut.iso", "/d/cut.iso", "https://a.example/cut", 9, "running", 3000, "a.example"))
    log.save()
    st.flush()
    rows = Storage(tmp_path / "ike.sqlite").downloads(1000)
    assert len(rows) == KEEP
    assert all("private" not in r[2] for r in rows)
    assert set(len(r) for r in rows) == {8}            # name, path, url, size, state, time, host, note
    again = DownloadList(Storage(tmp_path / "ike.sqlite"))
    assert [e.name for e in again.entries[:3]] == ["cut.iso", "f59.txt", "f58.txt"]
    assert again.entries[0].state == "failed"           # cut by the end of the session
    assert not any(e.private for e in again.entries)
    # the history cleared: the list goes, in the database too
    again.forget()
    assert again.entries == [] and Storage(tmp_path / "ike.sqlite").downloads() == []
    log.entries[:] = [Entry("x", "", "https://a.example/x", 1, "done")]
    log.save()
    st.clear_history()
    assert st.downloads() == []


def test_recent_history_cleared_takes_only_the_downloads_of_that_time(tmp_path):
    """History → Clear recent history… (1.1.25, the menus' branch) and the persistent list
    (this branch) together: the downloads of the last hour leave the list and the
    database, the older ones stay, private and running ones are not touched."""
    from ike.storage import Storage
    st = Storage(tmp_path / "ike.sqlite")
    log = DownloadList(st)
    old, new = Entry("old.txt", when=1000), Entry("new.txt", when=5000)
    run, priv = Entry("run.iso", state="running", when=5000), Entry("p.txt", when=5000, private=True)
    log.entries = [run, priv, new, old]
    log.save()
    st.clear_history(4000)
    log.forget(4000)
    assert log.entries == [run, priv, old]
    st.flush()
    names = [r[0] for r in Storage(tmp_path / "ike.sqlite").downloads()]
    assert "old.txt" in names and "new.txt" not in names and "p.txt" not in names


def test_clear_keeps_what_runs_and_the_private_ones():
    log = DownloadList(None)
    run, done, stop = (Entry("r", state="running"), Entry("d", state="done"), Entry("s", state="stopped"))
    priv = Entry("p", state="done", private=True)
    log.entries = [run, done, stop, priv]
    gone = log.clear(False)
    assert gone == [done, stop] and log.entries == [run, priv]
    assert log.shown(True) == [priv] and log.shown(False) == [run]


# --- in the browser ---------------------------------------------------------------

SLOW = 1_200_000
PIECE = 20_000


@pytest.fixture
def files_site():
    class H(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def send(self, body, name=None, kind="application/octet-stream", length=None):
            self.send_response(200)
            self.send_header("Content-Type", kind)
            if name:
                self.send_header("Content-Disposition", "attachment; filename=%s" % name)
            self.send_header("Content-Length", str(len(body) if length is None else length))
            self.end_headers()

        def do_GET(self):
            path = self.path.split("?")[0]
            try:
                if path in ("/small.txt", "/notes.txt"):
                    body = b"x" * 2048
                    self.send(body, path[1:])
                    self.wfile.write(body)
                elif path == "/slow.bin":
                    self.send(b"", "slow.bin", length=SLOW)
                    for _ in range(SLOW // PIECE):
                        self.wfile.write(b"s" * PIECE)
                        self.wfile.flush()
                        time.sleep(0.12)
                elif path == "/tool.sh":
                    body = b"#!/bin/sh\necho hello\n"
                    self.send(body, "tool.sh")
                    self.wfile.write(body)
                elif path == "/missing.bin":
                    self.send_response(404)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                else:
                    body = b"<!doctype html><title>page</title><p>files"
                    self.send(body, kind="text/html")
                    self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield "http://127.0.0.1:%d" % srv.server_address[1]
    srv.shutdown()


STEPS = r'''
import os
from pathlib import Path
SITE, FOLDER = %r, %r

def load(view, url):
    from PyQt6.QtCore import QUrl
    done = {}
    view.page().loadFinished.connect(lambda ok: done.setdefault("ok", ok))
    view.load(QUrl(url))
    for _ in range(200):
        if "ok" in done:
            break
        yield 25
    yield 300

def wait(cond, ms=15000):
    for _ in range(ms // 100):
        try:
            if cond():
                return True
        except IndexError:
            pass
        yield 100
    return False

def shown(row):
    return [k for k, b in row.buttons.items() if not b.isHidden()]

def steps(ike, qapp, out):
    from PyQt6.QtCore import QPoint, QUrl, Qt
    from PyQt6.QtGui import QGuiApplication
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QAbstractButton, QLabel, QWidget
    from ike import webview
    from ike.i18n import T
    ike.BURST_SECONDS = 0          # the downloads below are a script's: not a burst here
    win = ike.windows[0]
    win.resize(1300, 860)
    yield 800
    log = ike.download_log
    E = log.entries

    # 1. Ctrl+J (and the button) open the panel under the button; nothing yet
    out["key"] = win.act_downloads.shortcut().toString()
    win.act_downloads.trigger()
    yield 500
    menu, panel = win.panel_of("downloads")
    btn = win.nav.widgetForAction(win.act_downloads)
    g, b = menu.geometry(), btn.mapToGlobal(QPoint(0, 0))
    out["place"] = [g.top() - (b.y() + btn.height()), (g.right() + 1) - (b.x() + btn.width())]
    out["empty"] = [menu.isVisible(), panel.empty.isVisible(), panel.list_box.isVisible(), panel.clear.isVisible(),
                    panel.empty_title.text(), panel.empty_text.text(), panel.title.text()]
    menu.hide()
    yield 400
    QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
    yield 400
    out["click_opens"] = menu.isVisible()
    menu.hide()

    view = win.current_view()
    yield from load(view, SITE + "/")
    page = view.page()

    # 2. a small file: done, listed, kept; the panel opened: the ring is no longer green
    page.download(QUrl(SITE + "/small.txt"))
    ok = yield from wait(lambda: E and E[0].name == "small.txt" and E[0].state == "done")
    yield 300
    small = E[0]
    out["done"] = [ok, small.host, small.size, Path(small.path).parent == Path(FOLDER), ike._dl_done]
    win.show_downloads_panel()
    yield 500
    out["seen"] = ike._dl_done
    row = panel.rows[0]
    out["done_row"] = [row.name.full, row.status.full, shown(row), panel.empty.isVisible(), panel.clear.isVisible()]
    row.setFocus()
    yield 300
    out["done_focus"] = shown(row)
    out["db"] = [list(r) for r in ike.storage.downloads()]
    m = panel.row_menu(row, row.mapToGlobal(row.rect().center()))
    yield 300
    out["menu"] = [a.text() for a in m.actions() if a.text()]
    [a for a in m.actions() if a.text() == T("Copy link address")][0].trigger()
    out["clip"] = QGuiApplication.clipboard().text()
    m.hide()
    yield 200

    # 3. a slow file: running with its speed, paused (the bytes stand still), resumed
    page.download(QUrl(SITE + "/slow.bin"))
    ok = yield from wait(lambda: E[0].name == "slow.bin" and E[0].got > 0)
    yield 1800
    slow = E[0]
    row = panel.rows[0]
    out["running"] = [ok, slow.state, bool(slow.speed), row.status.full, panel.summary.text(), row.bar.isVisible(),
                      shown(row)]
    row.setFocus()
    yield 300
    out["running_focus"] = shown(row)
    row.buttons["pause"].click()
    yield 1000
    log.tick()
    got = slow.got
    yield 1500
    log.tick()
    row = panel.rows[0]
    out["paused"] = [slow.state, slow.item.isPaused(), row.status.full, slow.got - got, row.bar.paused]
    row.setFocus()
    yield 200
    out["paused_focus"] = shown(row)
    row.buttons["resume"].click()
    ok = yield from wait(lambda: slow.state == "done", 40000)
    out["resumed"] = [ok, slow.state, Path(slow.path).stat().st_size if slow.path else 0]

    # 4. a file the site does not have: failed; Retry, always shown, goes through the normal path again
    page.download(QUrl(SITE + "/missing.bin"))
    ok = yield from wait(lambda: E[0].url.endswith("/missing.bin") and E[0].state == "failed")
    yield 300
    failed = E[0]
    panel.setFocus()
    yield 200
    row = panel.rows[0]
    out["failed"] = [ok, row.status.full.startswith(T("Failed")), shown(row), row.status.palette().color(
        row.status.foregroundRole()).name()]
    asked = []
    real_download = type(ike)._download
    type(ike)._download = lambda self, item, private=False: (asked.append(item.url().toString()),
                                                              real_download(self, item, private))
    row.buttons["retry"].click()
    ok = yield from wait(lambda: asked)
    yield 500
    type(ike)._download = real_download
    out["retried"] = [ok, asked, failed not in E, E[0].url == SITE + "/missing.bin"]

    # 5. a program from a site never visited: stopped, listed with the reason; "Download anyway…"
    # asks the same question again, "Cancel" chosen
    page.download(QUrl(SITE + "/tool.sh"))
    ok = yield from wait(lambda: E[0].state == "stopped" and getattr(ike, "_risk_box", None) is not None)
    yield 300
    box = ike._risk_box
    first_text = box.text()
    [x for x in box.buttons() if x.text() == T("Cancel")][0].click()
    yield 300
    win.show_downloads_panel()          # (the question's window closed the panel)
    yield 500
    stopped = E[0]
    row = panel.rows[0]
    out["stopped"] = [ok, row.status.full, row.anyway.isHidden(), shown(row), Path(FOLDER, "tool.sh").exists()]
    row.setFocus()
    yield 300
    # the row is a line taller: the popup follows, its foot in view (no scrolling)
    out["stopped_focus"] = [row.anyway.isVisible(), shown(row), row.anyway.text(),
                            win._panels["downloads"][2].verticalScrollBar().maximum()]
    row.anyway.click()
    yield 500
    again = ike._risk_box
    out["again"] = [again is not box, again.isVisible(), again.text() == first_text,
                    again.defaultButton().text(), again.escapeButton().text(), menu.isVisible()]
    yield webview.SAFE_DELAY_MS + 200
    [x for x in again.buttons() if x.text() == T("Download anyway")][0].click()
    ok = yield from wait(lambda: Path(FOLDER, "tool.sh").exists() and E[0].state == "done")
    out["anyway"] = [ok, stopped not in E, E[0].name, E[0].known]

    # 6. a program from a site visited before: no question, a shield and the reason
    yield from load(view, SITE + "/second")
    page.download(QUrl(SITE + "/tool.sh?b"))
    ok = yield from wait(lambda: E[0].url.endswith("?b") and E[0].state == "done")
    win.show_downloads_panel()
    yield 500
    row = panel.rows[0]
    out["known"] = [ok, E[0].known, row.status.full, not row.mark.isHidden()]

    # 7. alignment (the owner): the panel's icons, the rows' icons and the links on one left
    # edge; the summary and the rows' buttons on one right edge; each text centred with its icon
    page.download(QUrl(SITE + "/slow.bin?align"))
    yield from wait(lambda: E[0].url.endswith("?align") and E[0].got > 0)
    yield 1500
    win.show_downloads_panel()
    yield 500
    win.fit_panel("downloads")
    yield 300
    row = panel.rows[0]
    row.setFocus()
    yield 300
    def box_of(w):
        o = w.mapTo(panel, QPoint(0, 0))
        return [o.x(), o.y(), o.x() + w.width(), o.y() + w.height()]
    lefts = [box_of(panel.head_icon)[0], box_of(panel.show_all)[0], box_of(panel.open_folder)[0],
             box_of(panel.clear)[0]] + [box_of(r.pic)[0] for r in panel.rows]
    buttons = [b for b in row.buttons.values() if not b.isHidden()]
    rights = [box_of(panel.summary)[2], box_of(buttons[-1])[2]]
    out["lefts"], out["rights"] = sorted(set(lefts)), sorted(set(rights))
    centres = []
    for r in panel.rows:
        pic, name, st = box_of(r.pic), box_of(r.name), box_of(r.status)
        block = (name[1] + (box_of(r.bar)[3] if not r.bar.isHidden() else st[3])) / 2
        centres.append(block - (pic[1] + pic[3]) / 2)
    for bb in buttons:
        centres.append((box_of(bb)[1] + box_of(bb)[3]) / 2 - (box_of(row)[1] + box_of(row)[3]) / 2)
    centres.append((box_of(panel.title)[1] + box_of(panel.title)[3]) / 2
                   - (box_of(panel.head_icon)[1] + box_of(panel.head_icon)[3]) / 2)
    centres.append((box_of(panel.summary)[1] + box_of(panel.summary)[3]) / 2
                   - (box_of(panel.title)[1] + box_of(panel.title)[3]) / 2)
    out["centres"] = centres
    texts = []
    for w in [panel] + panel.findChildren(QWidget):
        texts.append(w.toolTip() + " " + w.accessibleName())
        if isinstance(w, (QLabel, QAbstractButton)):
            texts.append(w.text())
    out["texts"] = " ".join(texts)
    out["focusable"] = all(w.focusPolicy() != Qt.FocusPolicy.NoFocus
                           for w in [panel.show_all, panel.open_folder, panel.clear, row] + buttons)

    # 8. remove one; clear the list: what runs stays, the files stay
    panel.act(small, "remove")
    yield 300
    out["removed"] = [small not in E, all(r[2] != small.url for r in ike.storage.downloads())]
    running = E[0]
    panel.clear.click()
    yield 500
    out["cleared"] = [[e.name for e in log.shown(False)], running.state,
                      sorted(p.name for p in Path(FOLDER).iterdir())]
    panel.rows[0].buttons["cancel"].click()
    ok = yield from wait(lambda: running.state == "cancelled")
    out["cancelled"] = [ok, panel.rows[0].status.full.startswith(T("Cancelled"))]
    menu.hide()

    # 9. a private window: its downloads in its own panel only, never written
    pw = ike.new_window(private=True)
    yield 800
    yield from load(pw.current_view(), SITE + "/")
    pw.current_view().page().download(QUrl(SITE + "/notes.txt"))
    ok = yield from wait(lambda: E[0].name == "notes.txt" and E[0].state == "done")
    pw.show_downloads_panel()
    yield 500
    _m, ppanel = pw.panel_of("downloads")
    out["private"] = [ok, E[0].private, [r.entry.name for r in ppanel.rows],
                      "notes.txt" in [e.name for e in log.shown(False)],
                      any("notes.txt" in (r[0] or "") for r in ike.storage.downloads())]
    pw.close()
    yield 300

    # 10. a download still going on when I.K.E. closes
    page.download(QUrl(SITE + "/slow.bin?cut"))
    yield from wait(lambda: E[0].url.endswith("?cut") and E[0].got > 0)
    ike.storage.flush()
    out["db_end"] = [[r[0], r[4], r[2]] for r in ike.storage.downloads()]
'''

AFTER = r'''
def steps(ike, qapp, out):
    win = ike.windows[0]
    yield 600
    win.show_downloads_panel()
    yield 500
    menu, panel = win.panel_of("downloads")
    out["rows"] = [[r.entry.name, r.entry.state] for r in panel.rows]
    ike.clear_data(True, False, False, False)
    yield 300
    out["after_clear"] = [[r.entry.name for r in panel.rows], panel.empty.isVisible(), ike.storage.downloads()]
'''


def test_the_panel_in_the_browser(run_ike, files_site, tmp_path):
    from ike.i18n import T
    folder = tmp_path / "dl"
    out = run_ike(STEPS % (files_site, str(folder)), timeout=240, env=screen(tmp_path, 1600, 1000),
                  settings={"download_dir": str(folder), "ask_download_location": False})
    assert out["key"] == "Ctrl+J"
    top, right = out["place"]
    assert 0 <= top <= 4 and abs(right) <= 8, out["place"]
    assert out["empty"] == [True, True, False, False, T("No downloads yet"),
                            T("The files you download appear here, with their state."), T("Downloads")]
    assert out["click_opens"] is True
    ok, host, size, place, ring = out["done"]
    assert ok and host == "127.0.0.1" and size == 2048 and place and ring is True, out["done"]
    assert out["seen"] is False                               # opening the panel: seen, the ring not green
    name, line, buttons, empty, clear = out["done_row"]
    assert name == "small.txt" and line.startswith("2.0 KB · 127.0.0.1 · "), out["done_row"]
    assert buttons == [] and empty is False and clear is True
    assert out["done_focus"] == ["open", "folder", "remove"]
    db = out["db"]
    assert db and db[0][0] == "small.txt" and db[0][2] == files_site + "/small.txt" and db[0][4] == "done", db
    assert T("Open file") in out["menu"] and T("Show in folder") in out["menu"]
    assert T("Copy link address") in out["menu"] and T("Remove from list") in out["menu"]
    assert out["clip"] == files_site + "/small.txt"
    ok, state, speed, line, summary, bar, buttons = out["running"]
    assert ok and state == "running" and speed and bar, out["running"]
    assert " of " in line and "/s" in line and "left" in line, line
    assert summary.startswith("1 in progress · ") and summary.endswith("/s"), summary
    assert buttons == [] and out["running_focus"] == ["pause", "cancel"]
    state, paused, line, grew, faded = out["paused"]
    assert state == "paused" and paused and line.startswith(T("Paused") + " · ") and grew == 0 and faded, \
        out["paused"]
    assert out["paused_focus"] == ["resume", "cancel"]
    assert out["resumed"] == [True, "done", 1_200_000], out["resumed"]
    ok, red_line, buttons, colour = out["failed"]
    assert ok and red_line and buttons == ["retry"] and colour.lower() == "#da4453", out["failed"]
    assert out["retried"] == [True, [files_site + "/missing.bin"], True, True], out["retried"]
    ok, line, hidden, buttons, on_disk = out["stopped"]
    assert ok and line == T("Stopped by I.K.E.: a program from a site never visited") and hidden, out["stopped"]
    assert buttons == [] and on_disk is False
    assert out["stopped_focus"] == [True, ["remove"], T("Download anyway") + "…", 0], out["stopped_focus"]
    assert out["again"] == [True, True, True, T("Cancel"), T("Cancel"), False], out["again"]
    assert out["anyway"] == [True, True, "tool.sh", False], out["anyway"]
    ok, known, line, shield = out["known"]
    assert ok and known and line.endswith(T("Program from a site you visited before")) and shield, out["known"]
    assert len(out["lefts"]) == 1 and len(out["rights"]) == 1, (out["lefts"], out["rights"])
    assert all(abs(c) <= 1 for c in out["centres"]), out["centres"]
    import re
    assert not re.search(r"https?:|www\.|://", out["texts"]), out["texts"]
    assert out["focusable"] is True
    assert out["removed"] == [True, True]
    names, state, files = out["cleared"]
    assert names == ["slow.bin"] and state == "running", out["cleared"]
    assert {"small.txt", "slow.bin", "tool.sh"} <= set(files)       # the files stay
    assert out["cancelled"] == [True, True]
    ok, private, rows, in_normal, written = out["private"]
    assert ok and private and rows == ["notes.txt"] and not in_normal and not written, out["private"]
    end = out["db_end"]
    assert end[0][1] == "running" and end[0][2].endswith("?cut") and len(end) <= 50, end
    assert not any(r[0] == "notes.txt" for r in end)

    after = run_ike(AFTER, keep_profile=True, env=screen(tmp_path, 1600, 1000),
                    settings={"download_dir": str(folder), "ask_download_location": False})
    rows = after["rows"]
    # the download I.K.E. stopped by closing: listed as cancelled (it can be tried again); one cut
    # by a crash is "failed" (test_kept_across_restarts_private_never)
    assert rows[0] == ["slow.bin", "cancelled"], rows
    assert [r[0] for r in rows] == [r[0] for r in end] and "notes.txt" not in [r[0] for r in rows]
    assert after["after_clear"] == [[], True, []], after["after_clear"]
