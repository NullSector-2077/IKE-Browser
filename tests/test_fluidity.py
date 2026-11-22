"""Speed and fluidity of 1.1.23 (docs/review/tests-and-performance.md,
"1.1.23, speed and fluidity"): the interface does the same with less work.

- The new tab page's clock writes its text only when it changes and wakes
  up at the next minute, not every second.
- The picture of a tab for its preview card is taken when the mouse comes
  to the tabs, or once a page has loaded, not at every change of tab.
- The loading mark of a tab repaints that tab only, from pictures drawn once.
- History and site icons: SQLite in WAL mode, synchronous=NORMAL; a backup
  still has the last visits, and clearing leaves nothing in the -wal file.
"""

import sqlite3
import sys
import zipfile

from conftest import APP

sys.path.insert(0, str(APP))


# --- history and icons: WAL ---------------------------------------------------

def test_history_and_icons_in_wal_mode(tmp_path, monkeypatch):
    from ike import favicons, importer, storage
    s = storage.Storage(tmp_path / "ike.sqlite")
    assert s.db.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert s.db.execute("PRAGMA synchronous").fetchone()[0] == 1          # NORMAL
    monkeypatch.setattr(favicons, "DATA_DIR", tmp_path)
    icons = favicons.Favicons(None)
    assert icons.db.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert icons.db.execute("PRAGMA synchronous").fetchone()[0] == 1
    # the last visit is in the -wal file only, and still reaches a backup
    s.add_visit("https://example.org/last", "Last")
    s.flush()
    assert (tmp_path / "ike.sqlite-wal").stat().st_size > 0
    monkeypatch.setattr(importer, "DATA_DIR", tmp_path)
    monkeypatch.setattr(importer, "BACKUP_FILES", (("ike.sqlite", tmp_path),))
    target = tmp_path / "backup.zip"
    importer.make_backup(target, s)
    out = tmp_path / "unpacked"
    with zipfile.ZipFile(target) as z:
        z.extract("ike.sqlite", out)
    copy = sqlite3.connect(str(out / "ike.sqlite"))
    assert copy.execute("SELECT title FROM history WHERE url=?", ("https://example.org/last",)).fetchone() == ("Last",)
    copy.close()
    # cleared: nothing of it left in the -wal file
    s.add_visit("https://example.org/secret-page", "Secret")
    s.flush()
    s.clear_history()
    wal = tmp_path / "ike.sqlite-wal"
    assert not wal.exists() or wal.stat().st_size == 0
    assert s.history() == []
    s.db.close()
    # a restore never meets the -wal file of the database it replaces
    (tmp_path / "ike.sqlite-wal").write_bytes(b"left by a crash")
    (tmp_path / "ike.sqlite-shm").write_bytes(b"left by a crash")
    assert importer.restore_backup(target) == ["ike.sqlite"]
    assert not (tmp_path / "ike.sqlite-wal").exists() and not (tmp_path / "ike.sqlite-shm").exists()
    again = storage.Storage(tmp_path / "ike.sqlite")
    assert [u for u, _t, _l in again.history()] == ["https://example.org/last"]
    again.db.close()


# --- the new tab page's clock -------------------------------------------------

def test_the_clock_wakes_once_a_minute_not_every_second():
    page = (APP / "ike" / "resources" / "newtab.html").read_text("utf-8")
    script = page[page.index("var lang = "):page.index("// the \"Add\" tile")]
    assert "setInterval" not in script
    assert "setTimeout(tick, 60000 - now.getTime() % 60000" in script
    assert "visibilitychange" in script


CLOCK = r'''
import json

def js(view, code):
    res = {}
    view.page().runJavaScript(code, 0, lambda r: res.setdefault("r", r))
    while "r" not in res:
        yield 20
    return res["r"]

def steps(ike, qapp, out):
    view = ike.windows[0].current_view()
    for _ in range(100):
        if view.url().toString() == "ike:newtab" and not getattr(view, "loading", True):
            break
        yield 100
    yield 500
    # every change of the clock's and the date's text is counted for 3.5 s
    yield from js(view, """window.__changes = 0; window.__minute = new Date().getMinutes();
        var mo = new MutationObserver(function (m) { window.__changes += m.length; });
        ['clock', 'date'].forEach(function (id) {
            mo.observe(document.getElementById(id), {childList: true, characterData: true, subtree: true}); });
        1""")
    yield 3500
    out["seen"] = json.loads((yield from js(view, """JSON.stringify({changes: window.__changes,
        crossed: new Date().getMinutes() !== window.__minute,
        clock: document.getElementById('clock').textContent,
        want: (function () { try { return new Date().toLocaleString(document.documentElement.lang || undefined,
            {hour: '2-digit', minute: '2-digit'}); } catch (e) { return ''; } })(),
        date: document.getElementById('date').textContent})""")))
'''


def test_the_clock_writes_only_when_it_changes(run_ike):
    """With the new tab page in front the clock wrote its text every second:
    a new frame of the page, the window and the graphics process each second
    (5.5 % of a core against 2.2 % without it, speed study of 1.1.23)."""
    out = run_ike(CLOCK, settings={"newtab_clock": True})
    seen = out["seen"]
    assert seen["clock"] and seen["date"], seen
    if not seen["crossed"]:                       # the minute did not change meanwhile
        assert seen["changes"] == 0, seen
    else:
        assert seen["changes"] <= 4, seen


# --- the tab picture for the preview card, and the loading mark ----------------

TABS = r'''
from PyQt6.QtCore import QEvent, QObject, QRect
from PyQt6.QtWidgets import QApplication

def steps(ike, qapp, out):
    import time
    from ike import tabpreview
    win = ike.windows[0]
    win.resize(1200, 800)
    yield 600
    taken = []
    real = tabpreview.capture
    def counted(view):
        taken.append(win.views.index(view) if view in win.views else -1)
        return real(view)
    tabpreview.capture = counted
    for _ in range(5):
        win.add_tab("ike:newtab")
        yield 700
    yield 1200
    # each tab got its picture once its page had loaded
    out["after_loads"] = sorted(set(taken))
    out["pictures"] = [getattr(v, "preview", None) is not None for v in win.views[:-1]]
    # changing tabs takes no picture of the tabs that have one
    del taken[:]
    for i in (0, 3, 1, 4, 2, 5, 0, 2):
        win.tabbar.setCurrentIndex(i)
        yield 120
    out["on_switch"] = list(taken)
    # the mouse comes to the tabs: the tab in view, once, off the switch
    del taken[:]
    QApplication.sendEvent(win.tabbar, QEvent(QEvent.Type.Enter))
    yield 50
    out["on_enter"] = list(taken)
    QApplication.sendEvent(win.tabbar, QEvent(QEvent.Type.Leave))
    QApplication.sendEvent(win.tabbar, QEvent(QEvent.Type.Enter))
    yield 50
    out["enter_again_soon"] = list(taken)
    # a tab whose page changed since its picture: taken when it is left
    del taken[:]
    cur = win.current_view()
    cur.preview_stale = True
    win.tabbar.setCurrentIndex((win.views.index(cur) + 1) % len(win.views))
    yield 100
    out["stale_left"] = [t == win.views.index(cur) for t in taken]
    # the card's picture: the same as before 1.1.23 (smooth scaling of the
    # whole grab), within a few levels per colour
    from PyQt6.QtCore import Qt
    view = win.current_view()
    pm = view.grab()
    old = pm.scaledToWidth(round(tabpreview.WIDTH * pm.devicePixelRatio()), Qt.TransformationMode.SmoothTransformation)
    top = round(tabpreview.MAX_HEIGHT * pm.devicePixelRatio())
    if old.height() > top:
        old = old.copy(0, 0, old.width(), top)
    need = min(pm.height(), int(-(-pm.width() * tabpreview.MAX_HEIGHT // tabpreview.WIDTH)) + 2)
    new = tabpreview.shrink(pm.copy(QRect(0, 0, pm.width(), need)))
    a, b = old.toImage(), new.toImage()
    out["card_size"] = [a.width(), a.height(), b.width(), b.height()]
    diff, n = 0, 0
    for y in range(0, min(a.height(), b.height()), 3):
        for x in range(0, min(a.width(), b.width()), 3):
            p, q = a.pixelColor(x, y), b.pixelColor(x, y)
            diff += abs(p.red() - q.red()) + abs(p.green() - q.green()) + abs(p.blue() - q.blue())
            n += 3
    out["card_diff"] = diff / max(1, n)

    # --- the loading mark repaints its own tab only
    bar = win.tabbar
    for _ in range(4):
        win.add_tab("ike:newtab", background=True)
    yield 1500
    i = 2
    v = win.views[i]
    rects = []
    class Paints(QObject):
        def eventFilter(self, obj, ev):
            if obj is bar and ev.type() == QEvent.Type.Paint:
                rects.append(ev.rect())
            return False
    watch = Paints()
    bar.repaint()
    skipped = bar.label_style.skipped
    bar.installEventFilter(watch)
    v.loading, v.loading_since = True, time.monotonic() - 1
    win._loading_mark(v, True)
    v.loading_since = time.monotonic() - 1
    for _ in range(6):
        win._spin_step()
        yield 100
    bar.removeEventFilter(watch)
    tab = bar.tabRect(i).adjusted(-bar.label_style.BEYOND, -bar.label_style.BEYOND,
                                  bar.label_style.BEYOND, bar.label_style.BEYOND)
    out["mark_paints"] = len(rects)
    out["mark_rects_in_tab"] = all(tab.contains(r) for r in rects)
    out["tabs"] = bar.count()
    out["skipped_per_paint"] = (bar.label_style.skipped - skipped) / max(1, len(rects))
    # a whole repaint still draws every tab
    skipped = bar.label_style.skipped
    bar.repaint()
    out["full_skips"] = bar.label_style.skipped - skipped
    v.loading = False
    win._loading_mark(v, False)
    yield 300
'''


def test_tab_pictures_are_taken_off_the_switch_and_the_mark_repaints_one_tab(run_ike):
    out = run_ike(TABS, timeout=120)
    assert out["after_loads"] and out["pictures"] == [True] * len(out["pictures"]), out
    assert out["on_switch"] == [], out                   # no picture at a change of tab
    assert len(out["on_enter"]) == 1, out                # the tab in view, when the mouse comes
    assert out["enter_again_soon"] == out["on_enter"], out
    assert out["stale_left"] == [True], out
    assert out["card_size"][:2] == out["card_size"][2:], out
    assert out["card_diff"] < 4, out                     # the card shows the same picture
    assert out["mark_paints"] >= 3 and out["mark_rects_in_tab"] is True, out
    assert out["tabs"] >= 10 and out["skipped_per_paint"] >= out["tabs"] - 4, out
    assert out["full_skips"] == 0, out


# --- what a repaint of the toolbar and of the "+N" reaches --------------------

TOOLBAR = r'''
from PyQt6.QtCore import QEvent, QObject
from PyQt6.QtGui import QColor

def steps(ike, qapp, out):
    import time
    win = ike.windows[0]
    yield 800
    paints = []
    class Paints(QObject):
        def eventFilter(self, obj, ev):
            if ev.type() == QEvent.Type.Paint and obj is win:
                paints.append(1)
            return False
    watch = Paints()
    win.installEventFilter(watch)
    out["opaque"] = win.nav.autoFillBackground()
    # a button of the toolbar repainted (its hover, the cursor of the
    # address field): the window behind the toolbar is not painted again
    from PyQt6.QtWidgets import QToolButton
    [b for b in win.nav.findChildren(QToolButton) if b.isVisible()][0].repaint()
    out["window_paints"] = len(paints)
    win.removeEventFilter(watch)
    # the toolbar keeps the colour of the window around it
    img = win.grab().toImage()
    nav = win.nav.geometry()
    out["colours"] = [QColor(img.pixel(nav.right() - 2, nav.bottom() - 1)).name(),
                      win.palette().color(win.palette().ColorRole.Window).name()]
    # the "+N" rises at 30 pictures a second, not one per frame of the screen
    count = win.shield_count
    count.last, count.key = 0, ("k", "h")
    win.shield_btn.setText("1")
    start = time.monotonic()
    count.count(5, ("k", "h"))
    while count.isVisible() and time.monotonic() - start < 3:
        yield 20
    out["count"] = [count.frames, round(time.monotonic() - start, 2)]
'''


def test_the_toolbar_stops_repaints_and_the_count_rises_at_30_pictures(run_ike):
    out = run_ike(TOOLBAR, env={"IKE_REDUCED_MOTION": "0"})
    assert out["opaque"] is True, out                    # Fusion (offscreen): a flat window
    assert out["window_paints"] == 0, out
    assert out["colours"][0] == out["colours"][1], out
    frames, seconds = out["count"]
    assert frames and frames <= seconds * 30 + 3, out
