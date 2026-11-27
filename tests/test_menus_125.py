"""1.1.25: one look for the menus, and the new History menu (the owner's
choices, ike/uistyle.py and ike/window.py).

- Every entry of the menus (the menu bar's, the ☰ menu and its submenus, a
  tab's right-click menu with its submenus, the toolbar's right-click menu, a
  link's "Open link in container", "Send to device") has an icon: no gap in
  the column of the icons.
- The titles inside a menu (Protection's "Protection level for every site",
  the toolbar menu's "Toolbar buttons", History's days) are real sections.
- History: Back, Forward, Home, Reopen closed tab and Recently closed tabs at
  the top; the last 15 pages under Today, Yesterday, This week and Earlier
  (by the day they were seen, a fixed clock here), each title shortened in
  its middle to 290 px with its site on the right; "Show all history" and
  "Clear recent history…" at the bottom. "Clear browsing data…" stays
  under Protection.
- "Clear recent history…" deletes only the pages of the chosen time: the
  last hour, today or all; nothing else, and nothing of a private window.
- Where the style is not Breeze, Oxygen or Kvantum, I.K.E. draws the menus:
  measured in pictures of the open menus, every icon and every capital in
  the middle of its row (1 px), the texts and the sections' names on one
  left edge, the shortcuts on one right edge. With Breeze (and Oxygen,
  Kvantum) the style draws them as before.
"""

import pytest
from conftest import screen

NON_NATIVE = ["Fusion", "Windows"]
NATIVE = ["Breeze", "Oxygen", "kvantum"]

WALK = r'''
def entries(menu, seen, path, out, fill=True):
    """[(path, text, has icon)] of every entry of menu and its submenus."""
    if menu is None or id(menu) in seen:
        return out
    seen.add(id(menu))
    if fill:
        menu.aboutToShow.emit()
    for a in menu.actions():
        if a.isSeparator() or not a.isVisible() or not a.text():
            continue
        if getattr(a, "defaultWidget", None) is not None and a.defaultWidget() is not None:
            continue
        out.append([path, a.text(), not a.icon().isNull()])
        if a.menu() is not None:
            entries(a.menu(), seen, path + " > " + a.text().replace("&", ""), out, fill)
    return out
'''


def test_every_menu_entry_has_an_icon(run_ike):
    out = run_ike(WALK + r'''
from PyQt6.QtCore import QPoint, QTimer, QUrl
from PyQt6.QtWidgets import QApplication

def steps(ike, qapp, out):
    from ike import contextmenu, icons
    win = ike.windows[0]
    yield 500
    # what fills the menus that are empty at first: history, a closed tab, bookmarks, containers,
    # two workspaces, a tab group, a paired phone and tablet
    ike.storage.add_visit("https://example.org/page", "Example page")
    ike.storage.add_bookmark("https://example.org/", "Example")
    win.closed_tabs.append(("https://example.net/", "Closed one"))
    ike.config["ext_containers"] = True
    ike.config["containers"] = [{"name": "Work", "color": "#3daee9"}]
    v = win.current_view()
    win.group_add(v, "Group A")
    yield 200
    win.workspaces.setdefault("Second", [])
    ike.desktop.devices = {"p1": "Pixel", "t1": "Tab", "x1": "Unknown"}
    ike.desktop.device_types = {"p1": "phone", "t1": "tablet"}
    ike.desktop.bus = ike.desktop.bus or object()
    ike.config["di_kdeconnect"] = True
    found = []
    seen = set()
    for a in win.menuBar().actions():
        entries(a.menu(), seen, a.text().replace("&", ""), found)
    entries(win.burger, seen, "☰", found)
    win._fill_send_menu()
    entries(win.m_send, seen, "toolbar > Send to device", found, fill=False)
    # the menus made when they are asked for: a tab's, the toolbar's, a link's
    def grab_popup(where):
        shown = QApplication.activePopupWidget()
        if shown is None:
            QTimer.singleShot(50, lambda: grab_popup(where))
            return
        entries(shown, set(), where, found, fill=False)
        shown.close()
    QTimer.singleShot(100, lambda: grab_popup("tab"))
    win._tab_menu(0, win.mapToGlobal(QPoint(40, 40)))
    yield 100
    QTimer.singleShot(100, lambda: grab_popup("toolbar"))
    win._toolbar_menu(win.nav.widgetForAction(win.act_reload).geometry().center())
    yield 100

    class Request:
        def linkUrl(self):
            return QUrl("https://example.com/")
        def mediaUrl(self):
            return QUrl()
        def mediaType(self):
            from PyQt6.QtWebEngineCore import QWebEngineContextMenuRequest as Req
            return Req.MediaType.MediaTypeNone
        def selectedText(self):
            return ""
        def isContentEditable(self):
            return False
        def editFlags(self):
            from PyQt6.QtWebEngineCore import QWebEngineContextMenuRequest as Req
            return Req.EditFlag(0)
        def mediaFlags(self):
            from PyQt6.QtWebEngineCore import QWebEngineContextMenuRequest as Req
            return Req.MediaFlag(0)
        def misspelledWord(self):
            return ""
        def spellCheckerSuggestions(self):
            return []
        def position(self):
            return QPoint(10, 10)
    page_menu = contextmenu.build(win.current_view(), Request())
    entries(page_menu, set(), "link", found, fill=False)
    out["found"] = found
    out["asked"] = [list(k) for k in icons.seen]
    page_menu.deleteLater()
''', settings={"ext_containers": True, "ext_split": True}, timeout=120)
    found = out["found"]
    where = {p.split(" > ")[0] for p, _t, _i in found}
    assert {"File", "View", "History", "Privacy", "Help", "☰", "tab", "toolbar", "link"} <= where, where
    missing = ["%s > %s" % (p, t) for p, t, has in found if not has]
    assert not missing, "entries without an icon:\n" + "\n".join(missing)
    texts = {t.replace("&", "") for _p, t, _i in found}
    for t in ("About Qt", "Save as PDF…", "Page source", "Tab group", "Reopen in container", "Open link in container",
              "Reset to default layout", "Pixel", "Tab", "Unknown"):
        assert t in texts, t
    asked = [tuple(k) for k in out["asked"]]
    # the names of the owner's choice first, the earlier ones after them
    assert ("document-export", "application-pdf", "document-save") in asked
    assert ("format-text-code", "text-html", "view-source") in asked
    assert ("plugins", "preferences-plugin", "application-x-addon") in asked
    # a device's icon by its kind (KDE Connect's), its own where the kind is not known
    assert ("smartphone", "phone") in asked and ("tablet", "phone") in asked
    assert ("kdeconnect", "smartphone", "phone") in asked


SECTIONS = r'''
def steps(ike, qapp, out):
    from PyQt6.QtCore import QPoint, QTimer
    from PyQt6.QtWidgets import QApplication
    win = ike.windows[0]
    yield 500
    bar = {a.text(): a.menu() for a in win.menuBar().actions()}
    def first(m):
        a = [x for x in m.actions() if x.isVisible()][0]
        return [a.isSeparator(), a.text(), a.isEnabled()]
    win.m_level.aboutToShow.emit()
    out["protection"] = [first(bar["P&rivacy"]), first(win.m_level)]
    seen = {}
    def grab():
        shown = QApplication.activePopupWidget()
        if shown is None:
            QTimer.singleShot(50, grab)
            return
        seen["first"] = first(shown)
        seen["second"] = [shown.actions()[1].isSeparator(), shown.actions()[1].isCheckable()]
        # no entry of these menus is a disabled stand-in for a title any more
        seen["greyed"] = [a.text() for a in shown.actions() if not a.isSeparator() and not a.isEnabled()]
        shown.close()
    QTimer.singleShot(100, grab)
    win._toolbar_menu(win.nav.widgetForAction(win.act_reload).geometry().center())
    yield 100
    out["toolbar"] = seen
    out["greyed_protection"] = [a.text() for a in bar["P&rivacy"].actions()
                                if not a.isSeparator() and not a.isEnabled()]
'''


def test_titles_in_menus_are_sections(run_ike):
    out = run_ike(SECTIONS)
    for got in out["protection"]:
        assert got[:2] == [True, "Protection level for every site"], got
    assert out["toolbar"]["first"][:2] == [True, "Toolbar buttons"], out
    assert out["toolbar"]["second"] == [False, True], out          # straight after it, the buttons
    assert out["toolbar"]["greyed"] == [] and out["greyed_protection"] == [], out


HISTORY = r'''
import time

def steps(ike, qapp, out):
    import ike.window as W
    from PyQt6.QtCore import Qt
    win = ike.windows[0]
    yield 400
    # a fixed clock: Tuesday 24 November 2026, 18:00 (the computer's own time zone)
    now = time.mktime((2026, 11, 24, 18, 0, 0, 0, 0, -1))
    W._now = lambda: now
    long_title = "Pasta e patate alla napoletana: la ricetta originale passo passo della nonna"
    rows = [("https://www.example.org/a", "Page A", now - 600),
            ("https://news.example.com/b", long_title, now - 5 * 3600),
            ("https://example.net/c", "Page C", time.mktime((2026, 11, 23, 23, 30, 0, 0, 0, -1))),
            ("https://example.net/d", "Page D", time.mktime((2026, 11, 23, 0, 30, 0, 0, 0, -1))),
            ("https://week.example/e", "Page E", time.mktime((2026, 11, 20, 12, 0, 0, 0, 0, -1))),
            ("https://week.example/f", "Page F", time.mktime((2026, 11, 18, 12, 0, 0, 0, 0, -1))),
            ("file:///home/me/notes.html", "Notes", time.mktime((2026, 11, 18, 9, 0, 0, 0, 0, -1)))]
    rows += [("https://old.example/%d" % i, "Old %d" % i, time.mktime((2026, 10, 1 + i, 9, 0, 0, 0, 0, -1)))
             for i in range(12)]
    ike.storage.clear_history()
    ike.storage.import_history([(u, t, int(when), 1) for u, t, when in rows])
    win.closed_tabs.append(("https://www.closed.example/x", "Closed tab"))
    res = {}
    for name, m in (("bar", win.m_history),):
        m.aboutToShow.emit()
        res[name] = [["section" if a.isSeparator() and a.text() else "separator" if a.isSeparator() else "entry",
                      a.text(), a.toolTip(), not a.icon().isNull()] for a in m.actions()]
        res[name + "_acts"] = [a is b for a, b in zip(m.actions()[:4], (win.act_back, win.act_fwd, win.act_home,
                                                                         win.act_reopen))]
        res[name + "_closed"] = m.actions()[4].menu() is win.m_closed
        res[name + "_bottom"] = [m.actions()[-2] is win.act_history, m.actions()[-1] is win.act_clear_recent]
        res[name + "_clear_data"] = win.act_clear in m.actions()
        fm = m.fontMetrics()
        res[name + "_widths"] = [fm.horizontalAdvance(a.text().split("\t")[0].replace("&&", "&"))
                                 for a in m.actions() if "\t" in a.text()]
    win.m_closed.aboutToShow.emit()
    res["closed"] = [a.text() for a in win.m_closed.actions()]
    # ☰ → Bookmarks and history (1.1.30): the same commands, then the last pages
    # visited (each with its site), the tabs closed last and the bookmarks, each under its name
    lib = win.burger_menus["library"]
    lib.aboutToShow.emit()
    res["lib"] = [["section" if a.isSeparator() and a.text() else "separator" if a.isSeparator() else "entry",
                   a.text()] for a in lib.actions()]
    res["lib_acts"] = [a in lib.actions() for a in (win.act_back, win.act_fwd, win.act_home,
                                                    win.act_history, win.act_clear_recent, win.act_bookmark,
                                                    win.act_bookmarks)]
    res["keys"] = [win.act_history.shortcut().toString(), win.act_reopen.shortcut().toString(),
                   win.act_back.shortcut().toString()]
    bar = {a.text(): a.menu() for a in win.menuBar().actions()}
    win.m_level.aboutToShow.emit()
    res["clear_data_in_protection"] = win.act_clear in bar["P&rivacy"].actions() and \
        win.act_clear in win.m_level.actions()
    res["long_title"] = long_title
    res["room"] = W.Window.TITLE_ROOM if hasattr(W, "Window") else win.TITLE_ROOM
    out.update(res)
'''


def test_history_menu_by_day_with_the_site(run_ike):
    out = run_ike(HISTORY, timeout=90)
    for name in ("bar",):
        rows = out[name]
        assert out[name + "_acts"] == [True] * 4 and out[name + "_closed"], name
        assert out[name + "_bottom"] == [True, True] and not out[name + "_clear_data"], name
        assert rows[-3][0] == "separator"
        middle = rows[5:-3]
        sections = [r[1] for r in middle if r[0] == "section"]
        assert sections == ["Today", "Yesterday", "This week", "Earlier"], sections
        pages = [r for r in middle if r[0] == "entry"]
        assert len(pages) == 15                                      # the limit of before
        grouped, day = {}, None
        for r in middle:
            if r[0] == "section":
                day = r[1]
            else:
                grouped.setdefault(day, []).append(r[1].split("\t")[0])
        assert grouped["Today"][0] == "Page A" and len(grouped["Today"]) == 2
        assert grouped["Yesterday"] == ["Page C", "Page D"]
        assert grouped["This week"] == ["Page E", "Page F", "Notes"]
        assert grouped["Earlier"] == ["Old %d" % i for i in range(11, 3, -1)]
        # the site on the right, without "www."; none for a file
        sites = {r[1].split("\t")[0]: (r[1].split("\t") + [""])[1] for r in pages}
        assert sites["Page A"] == "example.org" and sites["Page C"] == "example.net"
        assert sites["Notes"] == "" and "\t" not in [r[1] for r in pages if r[1].startswith("Notes")][0]
        # a long title shortened in its middle, to 290 px at most
        long = [r for r in pages if r[2] == "https://news.example.com/b"][0][1].split("\t")[0]
        assert "…" in long and long != out["long_title"]
        head, tail = long.split("…")
        assert out["long_title"].startswith(head) and out["long_title"].endswith(tail) and head and tail
        assert max(out[name + "_widths"]) <= out["room"]
        assert all(r[3] for r in pages)                              # each page with its icon
    assert out["closed"] == ["Closed tab\tclosed.example"]
    lib = out["lib"]
    assert all(out["lib_acts"]), out["lib_acts"]
    sections = [r[1] for r in lib if r[0] == "section"]
    assert sections == ["Recently visited", "Recently closed tabs"], sections
    i = lib.index(["section", "Recently visited"])
    visited = lib[i + 1:lib.index(["section", "Recently closed tabs"])]
    assert [r[1].split("\t")[0] for r in visited][:1] == ["Page A"] and len(visited) == 15
    assert lib[-1] == ["entry", "Closed tab\tclosed.example"]
    assert out["keys"] == ["Ctrl+H", "Ctrl+Shift+T", "Alt+Left"]
    assert out["clear_data_in_protection"]


def test_history_days():
    import time

    from ike.window import history_day, site_name
    now = time.mktime((2026, 11, 24, 0, 5, 0, 0, 0, -1))        # five minutes after midnight
    def day(d, h, m):
        return time.mktime((2026, 11, d, h, m, 0, 0, 0, -1))
    assert history_day(day(24, 0, 1), now) == "today"
    assert history_day(day(23, 23, 59), now) == "yesterday"
    assert history_day(day(22, 12, 0), now) == "week"
    assert history_day(day(18, 0, 0), now) == "week"
    assert history_day(day(17, 23, 59), now) == "earlier"
    assert history_day(now + 3600, now) == "today"                 # a clock moved back: not lost
    assert history_day(None, now) == "earlier"
    assert site_name("https://www.example.org/x") == "example.org"
    assert site_name("https://www.org/") == "www.org" and site_name("about:blank") == ""


CLEAR = r'''
import time

def steps(ike, qapp, out):
    from PyQt6.QtCore import QUrl
    win = ike.windows[0]
    yield 400
    now = time.mktime((2026, 11, 24, 18, 0, 0, 0, 0, -1))
    rows = [("https://hour.example/", "Hour", now - 600),
            ("https://today.example/", "Today", now - 5 * 3600),
            ("https://yesterday.example/", "Yesterday", now - 26 * 3600)]
    ike.storage.add_bookmark("https://kept.example/", "Kept")
    ike.config["bounce_used"] = {"kept.example": "2026-11-24"}
    calls = []
    real = ike.clear_data
    ike.clear_data = lambda *a: (calls.append(list(a)), real(*a))
    priv = ike.new_window(private=True)
    pv = priv.add_tab(QUrl("about:blank"))
    yield 300
    priv_tabs = len(priv.views)
    priv.closed_tabs.append(("https://private.example/", "Private"))
    res = {}
    for span in ("hour", "today", "all"):
        ike.storage.clear_history()
        ike.storage.import_history([(u, t, int(w), 1) for u, t, w in rows])
        ike.clear_recent_history(span, now=now)
        res[span] = sorted(t for _u, t, _l in ike.storage.history())
        res[span + "_calls"] = list(calls)
        calls.clear()
    res["bookmarks"] = [t for _u, t, _f in ike.storage.bookmarks()]
    res["bounce"] = ike.config["bounce_used"]
    res["private"] = [len(priv.views) == priv_tabs, priv.isVisible(), len(priv.closed_tabs),
                      priv.current_view() is pv]
    # the menu's entry opens the small dialog: three choices, Last hour first
    ike.storage.import_history([(u, t, int(time.time() - 60), 1) for u, t, _w in rows])
    win.act_clear_recent.trigger()
    yield 200
    dlg = ike._dialogs["clear_history"]
    res["dialog"] = [dlg.isVisible(), [dlg.span.itemData(i) for i in range(dlg.span.count())],
                     dlg.span.currentData()]
    dlg.span.setCurrentIndex(2)
    dlg._clear()
    res["after_dialog"] = [len(ike.storage.history()), list(calls)]
    priv.close()
    out.update(res)
'''


def test_clear_recent_history_only_the_pages(run_ike):
    out = run_ike(CLEAR, timeout=90)
    assert out["hour"] == ["Today", "Yesterday"], out
    assert out["today"] == ["Yesterday"], out
    assert out["all"] == [], out
    # the last hour and today touch nothing else; "all" is the history-only part of Clear browsing data
    assert out["hour_calls"] == [] and out["today_calls"] == []
    assert out["all_calls"] == [[True, False, False, False]]
    assert out["bookmarks"] == ["Kept"]
    assert out["private"] == [True, True, 1, True], out
    assert out["dialog"] == [True, ["hour", "today", "all"], "hour"], out
    assert out["after_dialog"] == [0, [[True, False, False, False]]], out


MEASURE = r'''
from PyQt6.QtCore import QPoint, QRect
from PyQt6.QtGui import QColor, QFontMetrics, QImage

def steps(ike, qapp, out):
    import time
    import ike.window as W
    from ike import uistyle
    win = ike.windows[0]
    win.resize(1300, 900)
    now = time.time()
    W._now = lambda: now
    ike.storage.import_history([("https://www.example.org/%d" % i, "Example page number %d" % i, int(now - i * 40000), 1)
                                for i in range(15)])
    win.closed_tabs.append(("https://example.net/", "Closed"))
    yield 600
    st = qapp.style()
    out["style"] = st.baseStyle().name() if hasattr(st, "baseStyle") else st.name()
    out["own"] = st.own_menus() if hasattr(st, "own_menus") else None

    def settle():
        for _ in range(4):
            qapp.processEvents()
            yield 20

    bar = [a.menu() for a in win.menuBar().actions()]
    view = [m for m in bar if win.act_fullscreen in m.actions()][0]
    protection = [m for m in bar if win.act_protection_settings in m.actions()][0]
    res = {}
    for name, m in (("History", win.m_history), ("View", view), ("Protection", protection),
                    ("☰", win.burger)):
        m.popup(win.mapToGlobal(QPoint(60, 40)))
        yield from settle()
        yield 150
        pm = m.grab()
        img = pm.toImage().convertToFormat(QImage.Format.Format_ARGB32)
        ratio = pm.devicePixelRatio()
        rows = []
        for a in m.actions():
            if not a.isVisible():
                continue
            g = m.actionGeometry(a)
            if g.isEmpty():
                continue
            bg = img.pixelColor(round((g.left() + 3) * ratio), round((g.top() + g.height() // 2) * ratio))

            def ink(rect, far=200):
                xs, ys = [], []
                x0, y0 = round(rect.left() * ratio), round(rect.top() * ratio)
                x1, y1 = round((rect.right() + 1) * ratio), round((rect.bottom() + 1) * ratio)
                for y in range(max(0, y0), min(img.height(), y1)):
                    for x in range(max(0, x0), min(img.width(), x1)):
                        c = img.pixelColor(x, y)
                        if abs(c.red() - bg.red()) + abs(c.green() - bg.green()) + abs(c.blue() - bg.blue()) > far:
                            xs.append(x)
                            ys.append(y)
                if not xs:
                    return None
                return [min(xs) / ratio, (max(xs) + 1) / ratio, min(ys) / ratio, (max(ys) + 1) / ratio]

            opt_off = uistyle.MENU_PAD + uistyle.MENU_ICON + uistyle.MENU_GAP
            row = {"text": a.text(), "top": g.top(), "h": g.height(), "left": g.left(), "right": g.right(),
                   "section": a.isSeparator() and bool(a.text()), "separator": a.isSeparator() and not a.text()}
            if a.isSeparator():
                if a.text():
                    row["ink"] = ink(QRect(g.left() + uistyle.MENU_PAD, g.top(), g.width() - 2 * uistyle.MENU_PAD,
                                           g.height()), 120)
                rows.append(row)
                continue
            # the text's start: the item drawn with and without its text
            with_text = m.grab(g).toImage()
            t = a.text()
            a.setText("")
            yield from settle()
            without = m.grab(g).toImage()
            a.setText(t)
            yield from settle()
            r = with_text.devicePixelRatio() or 1
            xs = [x for x in range(min(with_text.width(), without.width()))
                  for y in range(min(with_text.height(), without.height()))
                  if with_text.pixel(x, y) != without.pixel(x, y)]
            row["text_left"] = g.left() + min(xs) / r if xs else None
            # the icon: in the column before the text
            if row["text_left"] is not None:
                ix = int(row["text_left"]) - uistyle.MENU_GAP - uistyle.MENU_ICON - 2
                faint = 60 if not a.isEnabled() else 120       # a disabled entry's icon is dimmed
                row["icon"] = ink(QRect(ix, g.top() + 2, uistyle.MENU_ICON + 3, g.height() - 4), faint)
                first = t.replace("&&", "&").lstrip("&")[:1]
                if first.isascii() and first.isupper() and first not in "QJ":
                    fm = QFontMetrics(m.font())
                    # the capital's own ink width (its tight box), not its advance: the advance
                    # runs past the ink by the left side bearing and caught the next letter's
                    # descender ("Update": the "p" in Noto Sans, Arch's runner)
                    row["capital"] = ink(QRect(int(row["text_left"]) - 1, g.top() + 1,
                                               fm.tightBoundingRect(first).width() + 1,
                                               g.height() - 2), 200 if a.isEnabled() else 60)
                if "\t" in t or not a.shortcut().isEmpty():
                    end = g.right() - uistyle.MENU_PAD - uistyle.MENU_ARROW - 2
                    row["short"] = ink(QRect(end - 160, g.top() + 2, 160, g.height() - 4), faint)
            rows.append(row)
        res[name] = rows
        m.hide()
        yield from settle()
    out["menus"] = res
'''


@pytest.mark.parametrize("lang", ["en", "it"])
@pytest.mark.parametrize("style", NON_NATIVE)
def test_own_menus_aligned(run_ike, tmp_path, style, lang):
    env = dict(screen(tmp_path, 2800, 1800), QT_STYLE_OVERRIDE=style, QT_SCALE_FACTOR="2")
    out = run_ike(MEASURE, env=env, settings={"language": lang}, timeout=400)
    assert "error" not in out, out.get("error")
    if style.lower() not in (out["style"] or "").lower():
        pytest.skip("the %s style is not installed here (got %r)" % (style, out["style"]))
    assert out["own"] is True, out["style"]
    problems = []
    for name, rows in out["menus"].items():
        items = [r for r in rows if not r["section"] and not r["separator"]]
        heights = {r["h"] for r in items}
        if len(heights) != 1:
            problems.append("%s: rows of %s px" % (name, sorted(heights)))
        lefts = [r["text_left"] for r in items if r.get("text_left") is not None]
        if max(lefts) - min(lefts) > 2:
            problems.append("%s: texts start between %.1f and %.1f" % (name, min(lefts), max(lefts)))
        for r in items:
            mid = r["top"] + r["h"] / 2
            if r.get("icon") is None:
                problems.append("%s: %r has no icon drawn" % (name, r["text"]))
            elif abs((r["icon"][2] + r["icon"][3]) / 2 - mid) > 1:
                problems.append("%s: %r icon centre %.1f, row middle %.1f" % (
                    name, r["text"], (r["icon"][2] + r["icon"][3]) / 2, mid))
            # the capital's ink, at scale 2: within one logical pixel (2 device pixels) of the middle. The
            # rasterizer of GitHub's runner put the 'S' of "System title bar" 2 device pixels low where this
            # computer, with the same font, gives 0 (PR #162); the icons keep the stricter 1.
            if r.get("capital") and abs((r["capital"][2] + r["capital"][3]) / 2 - mid) > 2:
                problems.append("%s: %r text centre %.1f, row middle %.1f" % (
                    name, r["text"], (r["capital"][2] + r["capital"][3]) / 2, mid))
        shorts = [r["short"][1] for r in items if r.get("short")]
        if shorts and max(shorts) - min(shorts) > 2:
            problems.append("%s: shortcuts end between %.1f and %.1f" % (name, min(shorts), max(shorts)))
        for r in rows:
            if r["section"]:
                if not r.get("ink"):
                    problems.append("%s: section %r not drawn" % (name, r["text"]))
                elif abs(r["ink"][0] - min(lefts)) > 2:
                    problems.append("%s: section %r starts at %.1f, the texts at %.1f" % (
                        name, r["text"], r["ink"][0], min(lefts)))
    assert not problems, "%s %s\n%s" % (style, lang, "\n".join(problems))
    assert [r["text"] for r in out["menus"]["History"] if r["section"]], "History has its days"


NATIVE_SCRIPT = r'''
from PyQt6.QtWidgets import QStyle, QStyleFactory

def steps(ike, qapp, out):
    win = ike.windows[0]
    yield 500
    st = qapp.style()
    out["style"] = st.baseStyle().name() if hasattr(st, "baseStyle") else st.name()
    out["own"] = st.own_menus()
    plain = QStyleFactory.create(out["style"])
    m = win.burger
    PM = QStyle.PixelMetric
    out["metrics"] = [[st.pixelMetric(k, None, m), plain.pixelMetric(k, None, m)]
                      for k in (PM.PM_MenuPanelWidth, PM.PM_MenuVMargin, PM.PM_SubMenuOverlap, PM.PM_SmallIconSize)]
    out["sections"] = [st.styleHint(QStyle.StyleHint.SH_Menu_SupportsSections, None, m),
                       plain.styleHint(QStyle.StyleHint.SH_Menu_SupportsSections, None, m)]
'''


@pytest.mark.parametrize("style", NATIVE)
def test_native_menus_left_to_the_style(run_ike, tmp_path, style):
    """Breeze, Oxygen and Kvantum draw I.K.E.'s menus themselves, as before:
    the same measures and sections as the style alone."""
    env = dict(screen(tmp_path, 1366, 768), QT_STYLE_OVERRIDE=style)
    out = run_ike(NATIVE_SCRIPT, env=env)
    if style.lower() not in (out.get("style") or "").lower():
        pytest.skip("the %s style is not installed here (got %r)" % (style, out.get("style")))
    assert "error" not in out, out.get("error")
    assert out["own"] is False
    assert all(a == b for a, b in out["metrics"]), out["metrics"]
    assert out["sections"][0] == out["sections"][1]


def test_which_styles_draw_their_own_menus():
    from ike import polish
    for name in ("Breeze", "breeze", "Oxygen", "kvantum", "kvantum-dark"):
        assert polish.native_popup_style(name), name
    for name in ("Fusion", "Windows", "", None):
        assert not polish.native_popup_style(name), name
