"""1.1.24, work package B3 (the owner's approved list):

- the history window grouped by day: Today, Yesterday, then the dates as the
  interface's language writes them; the search still works, a day's heading
  is never opened nor deleted;
- reader mode: the column narrow, medium or wide and serif or sans-serif
  type, chosen on the page and remembered;
- screenshots of the visible part, of the whole page (fixed bars once) and
  of an area chosen with the mouse, from the "Screenshot…" submenu;
  Ctrl+Shift+S and the toolbar's button take the visible part as before;
- dark PDFs: off by default; on, the engine's PDF viewer shows the pages
  with their colours turned around; other pages are never touched;
- the welcome of the first start: four steps, skippable, never again, its
  choices saved; a profile that already had settings never sees it;
- "Copy clean link" in a link's menu and in the address bar, "Paste and go"
  in the address bar;
- History → Recently closed tabs, with titles and icons; Ctrl+Shift+T
  still opens the last one.
"""

import json

import pytest
from conftest import screen

LONG_PAGE = """<!doctype html><html><head><title>Long</title><style>
body{margin:0} .bar{position:fixed;top:0;left:0;right:0;height:40px;background:rgb(0,0,255)}
.s{height:600px} #a{background:rgb(255,0,0)} #b{background:rgb(0,255,0)} #c{background:rgb(255,255,0)}
</style></head><body><div class=bar></div><div class=s id=a></div><div class=s id=b></div>
<div class=s id=c></div></body></html>"""

ARTICLE = ("<!doctype html><html><head><title>Story</title></head><body><nav>menu</nav><article><h1>Story</h1>"
           + "".join("<p>%s</p>" % ("A sentence of the article that goes on for a while. " * 6)
                     for _ in range(12)) + "</article></body></html>")


def test_history_grouped_by_day(run_ike):
    out = run_ike(r'''
def steps(ike, qapp, out):
    import time
    from PyQt6.QtCore import QDate, QDateTime, QLocale, QTime
    from ike import i18n
    st = ike.storage
    now = int(time.time())
    noon = QDateTime(QDate.currentDate(), QTime(12, 0)).toSecsSinceEpoch()
    rows = [("https://today.example/", "Today page", noon),
            ("https://yesterday.example/", "Yesterday page", noon - 86400),
            ("https://older.example/", "Older page", noon - 5 * 86400),
            ("https://older.example/two", "Older two", noon - 5 * 86400 + 60)]
    for url, title, last in rows:
        st.add_visit(url, title)
        st.db.execute("UPDATE history SET last=? WHERE url=?", (last, url))
    st.db.commit()
    dlg = ike.show_history()
    yield 200
    def tree():
        t = dlg.tree
        return [[t.topLevelItem(i).text(0), [t.topLevelItem(i).child(j).text(0)
                                             for j in range(t.topLevelItem(i).childCount())]]
                for i in range(t.topLevelItemCount())]
    out["groups"] = tree()
    out["older_name"] = QLocale(i18n.current()).toString(QDate.currentDate().addDays(-5),
                                                         QLocale.FormatType.LongFormat)
    top = dlg.tree.topLevelItem(0)
    out["heading"] = [top.isExpanded(), bool(top.flags() & top.flags().ItemIsSelectable), top.font(0).bold()]
    out["time"] = top.child(0).text(2)
    dlg.search.setText("older")
    yield 100
    out["search"] = tree()
    # a heading selected with its rows: only the rows are deleted
    dlg.search.setText("")
    yield 100
    dlg.tree.topLevelItem(2).child(0).setSelected(True)
    dlg.tree.topLevelItem(0).setSelected(True)
    dlg._delete()
    yield 100
    out["after_delete"] = tree()
    dlg.close()
''')
    g = out["groups"]
    assert [x[0] for x in g] == ["Today", "Yesterday", out["older_name"]], g
    assert g[0][1] == ["Today page"] and g[1][1] == ["Yesterday page"]
    assert g[2][1] == ["Older two", "Older page"]                 # newest first inside a day
    assert out["heading"] == [True, False, True]
    assert ":" in out["time"] or "." in out["time"]               # a time of day, no date
    assert out["search"] == [[out["older_name"], ["Older two", "Older page"]]]
    assert out["after_delete"] == [["Today", ["Today page"]], ["Yesterday", ["Yesterday page"]],
                                   [out["older_name"], ["Older page"]]]


def test_history_days_in_the_interface_language():
    from PyQt6.QtCore import QDate, QLocale

    from ike import i18n
    from ike.dialogs import HistoryDialog
    i18n.setup("it")
    try:
        today = QDate(2026, 11, 23)
        assert HistoryDialog.day_name(today, today, QLocale("it")) == "Oggi"
        assert HistoryDialog.day_name(today.addDays(-1), today, QLocale("it")) == "Ieri"
        older = HistoryDialog.day_name(QDate(2026, 11, 2), today, QLocale("it"))
        assert "novembre" in older and "2026" in older, older
    finally:
        i18n.setup("en")


READER = r'''
def steps(ike, qapp, out):
    import os
    from PyQt6.QtCore import QUrl
    path = os.path.join(os.environ["HOME"], "story.html")
    open(path, "w").write(ARTICLE)
    win = ike.windows[0]
    win.resize(1200, 800)
    v = win.current_view()
    v.load(QUrl.fromLocalFile(path))
    yield 1500
    res = {}
    def js(code, key):
        v.page().runJavaScript(code, 0, lambda r: res.__setitem__(key, r))
    win.toggle_reader()
    yield 800
    js("[getComputedStyle(document.querySelector('main')).maxWidth, getComputedStyle(document.body).fontFamily,"
       " Array.from(document.querySelectorAll('.ike-tools button')).map(b => [b.title, b.getAttribute('aria-pressed')])]",
       "first")
    yield 300
    out["first"] = res.get("first")
    if CLICK:
        # wide, then sans-serif: clicked as the user does (the page's world)
        js("var b=document.querySelectorAll('.ike-tools button');"
           "Array.from(b).find(x=>x.title=='Wide column').click();"
           "Array.from(b).find(x=>x.title=='Sans-serif font').click();"
           "[getComputedStyle(document.querySelector('main')).maxWidth, getComputedStyle(document.body).fontFamily]",
           "clicked")
        yield 600
        out["clicked"] = res.get("clicked")
    out["saved"] = [ike.config["reader_width"], ike.config["reader_font"]]
'''


def test_reader_column_and_font_are_remembered(run_ike):
    script = READER.replace("ARTICLE", repr(ARTICLE))
    out = run_ike(script.replace("CLICK", "True"))
    width, family, buttons = out["first"]
    assert width == "%dpx" % (42 * 19) and "Georgia" in family, out["first"]
    titles = [b[0] for b in buttons]
    for t in ("Narrow column", "Medium column", "Wide column", "Serif font", "Sans-serif font"):
        assert t in titles, titles
    pressed = {b[0]: b[1] for b in buttons}
    assert pressed["Medium column"] == "true" and pressed["Serif font"] == "true"
    assert pressed["Wide column"] == "false" and pressed["Sans-serif font"] == "false"
    assert out["clicked"][0] == "%dpx" % (56 * 19) and "Georgia" not in out["clicked"][1], out["clicked"]
    assert out["saved"] == ["wide", "sans"]
    # the next time, the same column and type
    again = run_ike(script.replace("CLICK", "False"), settings={"reader_width": "wide", "reader_font": "sans"})
    width, family, buttons = again["first"]
    assert width == "%dpx" % (56 * 19) and "Georgia" not in family, again["first"]
    assert {b[0]: b[1] for b in buttons}["Narrow column"] == "false"


def test_reader_prefs_refuse_unknown_values(run_ike):
    out = run_ike(r'''
def steps(ike, qapp, out):
    page = ike.windows[0].current_view().page()
    yield 300
    page._reader_prefs('{"theme": "dark", "size": 20, "width": "huge", "font": "sans"}')
    out["bad_width"] = [ike.config["reader_theme"], ike.config["reader_width"]]
    page._reader_prefs('{"theme": "dark", "size": 20, "width": "narrow", "font": "comic"}')
    out["bad_font"] = [ike.config["reader_theme"], ike.config["reader_font"]]
    page._reader_prefs('{"theme": "sepia", "size": 21, "width": "narrow", "font": "sans"}')
    out["good"] = [ike.config[k] for k in ("reader_theme", "reader_size", "reader_width", "reader_font")]
    page._reader_prefs('{"theme": "light", "size": 18}')            # a reader of before 1.1.24
    out["old"] = [ike.config[k] for k in ("reader_theme", "reader_size", "reader_width", "reader_font")]
''')
    assert out["bad_width"] == ["auto", "medium"] and out["bad_font"] == ["auto", "serif"]
    assert out["good"] == ["sepia", 21, "narrow", "sans"]
    assert out["old"] == ["light", 18, "medium", "serif"]


SHOTS = r'''
def steps(ike, qapp, out):
    import os
    from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt, QUrl
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtWidgets import QFileDialog
    from ike import screenshot
    home = os.environ["HOME"]
    path = os.path.join(home, "long.html")
    open(path, "w").write(LONG_PAGE)
    win = ike.windows[0]
    win.showNormal()
    win.resize(1000, 700)
    v = win.current_view()
    v.load(QUrl.fromLocalFile(path))
    yield 1500
    saved = []
    def fake_save(*a, **k):
        name = os.path.join(home, "shot%d.png" % len(saved))
        saved.append(name)
        return name, ""
    QFileDialog.getSaveFileName = staticmethod(fake_save)
    # the menus: "Screenshot…" with its three choices, the same in the ☰ menu, File and a page's menu
    out["submenu"] = [a.text() for a in win.act_shot.menu().actions()]
    out["in_burger"] = win.act_shot in win.burger.actions()
    from ike import contextmenu
    out["in_page_menu"] = win.act_shot in contextmenu.build(v, None).actions()
    out["keys"] = [a.shortcut().toString() for a in win.m_shot.actions()]
    # the visible part (Ctrl+Shift+S, the toolbar's button)
    win.m_shot.actions()[0].trigger()
    yield 200
    from PyQt6.QtGui import QImage
    img = QImage(saved[-1])
    out["visible"] = [img.width(), img.height(), v.width(), v.height()]
    # the whole page
    got = []
    screenshot.whole_page(v, got.append)
    for _ in range(80):
        yield 100
        if got:
            break
    page = got[0].toImage()
    out["page"] = [page.width(), page.height()]
    out["colours"] = [page.pixelColor(page.width() // 2, y).name() for y in (10, 300, 900, 1500, page.height() - 5)]
    res = {}
    v.page().runJavaScript("[scrollY, getComputedStyle(document.querySelector('.bar')).visibility]", 0,
                           lambda r: res.__setitem__("after", r))
    yield 300
    out["after"] = res.get("after")
    # through the submenu: the whole page saved
    n = len(saved)
    [a for a in win.m_shot.actions() if a.data() == "page"][0].trigger()
    for _ in range(80):
        yield 100
        if len(saved) > n:
            break
    out["page_saved"] = QImage(saved[-1]).height() if len(saved) > n else 0
    # an area chosen with the mouse
    [a for a in win.m_shot.actions() if a.data() == "area"][0].trigger()
    yield 200
    picker = win.findChild(screenshot.AreaPicker)
    out["picker"] = picker is not None and picker.isVisible()
    def mouse(kind, x, y, button=Qt.MouseButton.LeftButton):
        held = Qt.MouseButton.NoButton if kind == QEvent.Type.MouseButtonRelease else button
        e = QMouseEvent(kind, QPointF(x, y), picker.mapToGlobal(QPointF(x, y)), button, held,
                        Qt.KeyboardModifier.NoModifier)
        qapp.sendEvent(picker, e)
    n = len(saved)
    mouse(QEvent.Type.MouseButtonPress, 100, 100)
    mouse(QEvent.Type.MouseMove, 250, 180)
    mouse(QEvent.Type.MouseButtonRelease, 300, 200)
    yield 200
    area = QImage(saved[-1]) if len(saved) > n else None
    out["area"] = [area.width(), area.height(), area.pixelColor(100, 50).name()] if area else None
    out["picker_gone"] = not [p for p in win.findChildren(screenshot.AreaPicker) if p.isVisible()]
    # Esc cancels: nothing saved
    [a for a in win.m_shot.actions() if a.data() == "area"][0].trigger()
    yield 200
    n = len(saved)
    picker = [p for p in win.findChildren(screenshot.AreaPicker) if p.isVisible()][0]
    from PyQt6.QtGui import QKeyEvent
    qapp.sendEvent(picker, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))
    yield 200
    out["esc"] = [len(saved) == n, not [p for p in win.findChildren(screenshot.AreaPicker) if p.isVisible()]]
'''


def test_screenshot_modes(run_ike, tmp_path):
    out = run_ike(SHOTS.replace("LONG_PAGE", repr(LONG_PAGE)), timeout=120,
                  settings={"start_maximized": False}, env=screen(tmp_path, 1366, 768))
    assert out["submenu"] == ["Visible part", "Whole page", "Selected area"]
    assert out["in_burger"] and out["in_page_menu"] and out["keys"] == ["Ctrl+Shift+S", "", ""]
    w, h, vw, vh = out["visible"]
    assert (w, h) == (vw, vh)
    pw, ph = out["page"]
    assert pw == vw and 1790 <= ph <= 1810, out["page"]           # 3 x 600 px, not only the visible part
    top, red, green, yellow, end = out["colours"]
    assert top == "#0000ff"                                       # the fixed bar, at the top
    assert (red, green, yellow, end) == ("#ff0000", "#00ff00", "#ffff00", "#ffff00"), out["colours"]
    assert out["after"] == [0, "visible"]                         # scrolled back, the bar shown again
    assert 1790 <= out["page_saved"] <= 1810
    assert out["picker"] and out["picker_gone"]
    assert out["area"] is not None and out["area"][:2] == [200, 100], out["area"]
    assert out["area"][2] == "#ff0000"
    assert out["esc"] == [True, True]


def test_whole_page_bars_appear_once(run_ike, tmp_path):
    """A fixed bar is in the picture once, at its top: not over every part."""
    out = run_ike(SHOTS.split("    # through the submenu")[0].replace("LONG_PAGE", repr(LONG_PAGE)),
                  timeout=120, settings={"start_maximized": False}, env=screen(tmp_path, 1366, 768))
    page_h = out["page"][1]
    assert page_h > out["visible"][1]
    # where the second part begins (one view height down) there is no blue bar
    assert "#0000ff" not in out["colours"][1:]


PDF = r'''
def steps(ike, qapp, out):
    import os
    from PyQt6.QtCore import QUrl
    from PyQt6.QtGui import QPainter, QPdfWriter
    from ike.webview import dark_pdf
    p = os.path.join(os.environ["HOME"], "doc.pdf")
    w = QPdfWriter(p)
    pa = QPainter(w)
    pa.drawText(100, 100, "Hello PDF")
    pa.end()
    win = ike.windows[0]
    win.showNormal()
    win.resize(1000, 700)
    v = win.current_view()
    v.load(QUrl.fromLocalFile(p))
    yield 3000
    res = {}
    def filt(key):
        v.page().runJavaScript("(document.querySelector('embed')||{style:{}}).style.filter||''", 1,
                               lambda r: res.__setitem__(key, r))
    filt("start")
    yield 300
    out["start"] = res.get("start")
    out["centre_start"] = v.grab().toImage().pixelColor(500, 350).name()
    dlg = win.open_settings("appearance")
    from PyQt6.QtWidgets import QLabel
    out["switch"] = [bool([w for w in dlg.findChildren(QLabel) if w.text() == "Show PDFs with dark colours"]),
                     dlg.dark_pdf.isChecked()]
    dlg.dark_pdf.setChecked(not dlg.dark_pdf.isChecked())
    dlg.apply()
    dlg.close()
    yield 800
    filt("after")
    yield 300
    out["after"] = res.get("after")
    out["centre_after"] = v.grab().toImage().pixelColor(500, 350).name()
    out["saved"] = ike.config["dark_pdf"]
    # a web page is never touched
    v.setHtml("<body style='background:#fff'>page</body>", QUrl("https://example.org/"))
    yield 800
    dark_pdf(v, True, lambda r: res.__setitem__("html", r))
    yield 300
    v.page().runJavaScript("document.documentElement.style.filter", 1, lambda r: res.__setitem__("html_filter", r))
    yield 300
    out["html"] = [res.get("html"), res.get("html_filter")]
'''


@pytest.mark.parametrize("on", [False, True])
def test_dark_pdfs(run_ike, on):
    out = run_ike(PDF, settings={"dark_pdf": on}, timeout=90)
    assert out["switch"] == [True, on]
    if on:      # on from the start: dark at once, then switched off in the Settings
        assert out["start"].startswith("invert") and out["centre_start"] != "#ffffff"
        assert out["after"] == "" and out["centre_after"] == "#ffffff" and out["saved"] is False
    else:       # off by default: as the engine shows it, then switched on
        assert out["start"] == "" and out["centre_start"] == "#ffffff"
        assert out["after"].startswith("invert") and out["centre_after"] != "#ffffff" and out["saved"] is True
    assert out["html"] == [False, ""]


def test_dark_pdfs_off_by_default():
    from ike.config import DEFAULTS
    assert DEFAULTS["dark_pdf"] is False


WELCOME = r'''
def steps(ike, qapp, out):
    yield 300
    dlg = getattr(ike, "welcome", None)
    out["shown"] = dlg is not None and dlg.isVisible()
    out["windows_before"] = len(ike.windows)
    if dlg is None:
        return
    pages = []
    out["title"] = dlg.windowTitle()
    for step in range(4):
        pages.append([dlg.count.text(), dlg.question.text(), dlg.next.text(), dlg.back.isVisible()])
        if step < 3:
            dlg.next.click()
            yield 50
    out["pages"] = pages
    out["levels"] = [[r.text(), line.text()] for r, line in dlg.level_rows.values()]
    out["default_ticked"] = dlg.default.isChecked()
    if MODE == "choose":
        dlg.go(1)
        dlg.level_rows["strict"][0].setChecked(True)
        dlg.go(2)
        dlg.engine.setCurrentIndex(dlg.engine.findData("DuckDuckGo"))
        dlg.go(3)
        dlg.next.click()
    elif MODE == "language":
        dlg.go(0)
        dlg.language.setCurrentIndex(dlg.language.findData("it"))
        yield 50
        out["italian"] = [dlg.windowTitle(), dlg.question.text(), dlg.skip.text(), dlg.next.text()]
        dlg.go(3)
        dlg.next.click()
    else:
        dlg.skip.click()
    yield 1500
    out["welcome_after"] = getattr(ike, "welcome", None) is None
    out["windows_after"] = len(ike.windows)
    import json, os
    saved = json.load(open(os.path.join(os.environ["XDG_CONFIG_HOME"], "ike-browser", "settings.json")))
    out["saved"] = {k: saved.get(k) for k in ("welcome_done", "shield_level", "default_engine", "language")}
'''


def test_welcome_on_the_first_start_then_never(run_ike):
    out = run_ike(WELCOME.replace("MODE", repr("choose")), settings={"welcome_done": False})
    assert out["shown"] and out["windows_before"] == 0
    assert out["title"] == "Welcome to I.K.E."
    assert [p[0] for p in out["pages"]] == ["Step 1 of 4", "Step 2 of 4", "Step 3 of 4", "Step 4 of 4"]
    assert [p[2] for p in out["pages"]] == ["Next", "Next", "Next", "Done"]
    assert [p[3] for p in out["pages"]] == [False, True, True, True]
    assert all(p[1].endswith("?") for p in out["pages"])
    assert [x[0] for x in out["levels"]] == ["Compatibility", "Balanced", "Strict"]
    assert all(x[1] for x in out["levels"])
    assert out["default_ticked"] is False                          # never chosen for the user
    assert out["welcome_after"] and out["windows_after"] == 1
    assert out["saved"]["welcome_done"] is True
    assert out["saved"]["shield_level"] == "strict" and out["saved"]["default_engine"] == "DuckDuckGo"
    # the next start: no welcome, the window at once
    again = run_ike(WELCOME.replace("MODE", repr("choose")), keep_profile=True)
    assert again["shown"] is False and again["windows_before"] == 1


def test_welcome_skipped_changes_nothing(run_ike):
    out = run_ike(WELCOME.replace("MODE", repr("skip")), settings={"welcome_done": False})
    assert out["shown"] and out["windows_after"] == 1
    assert out["saved"] == {"welcome_done": True, "shield_level": "balanced", "default_engine": "Startpage",
                            "language": "auto"}


def test_welcome_in_the_language_chosen(run_ike):
    out = run_ike(WELCOME.replace("MODE", repr("language")), settings={"welcome_done": False})
    title, question, skip, nxt = out["italian"]
    assert title == "Benvenuto in I.K.E." or title != "Welcome to I.K.E.", out["italian"]
    assert question != "Which language should I.K.E. use?" and skip != "Skip" and nxt != "Next"
    assert out["saved"]["language"] == "it"


def test_existing_profiles_never_see_the_welcome(tmp_path):
    from ike.config import Config
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"shield_level": "strict"}), "utf-8")
    assert Config(p)["welcome_done"] is True                       # had settings before 1.1.24
    p.write_text(json.dumps({"welcome_done": False}), "utf-8")
    assert Config(p)["welcome_done"] is False                      # the welcome not answered yet
    assert Config(tmp_path / "none.json")["welcome_done"] is False  # a new profile


LINKS = r'''
class Req:
    def __init__(self, link):
        from PyQt6.QtCore import QUrl
        self._link = QUrl(link)
    def linkUrl(self): return self._link
    def mediaUrl(self):
        from PyQt6.QtCore import QUrl
        return QUrl()
    def mediaType(self):
        from PyQt6.QtWebEngineCore import QWebEngineContextMenuRequest as R
        return R.MediaType.MediaTypeNone
    def selectedText(self): return ""
    def isContentEditable(self): return False
    def editFlags(self):
        from PyQt6.QtWebEngineCore import QWebEngineContextMenuRequest as R
        return R.EditFlag(0)
    def mediaFlags(self):
        from PyQt6.QtWebEngineCore import QWebEngineContextMenuRequest as R
        return R.MediaFlag(0)
    def misspelledWord(self): return ""
    def spellCheckerSuggestions(self): return []
    def linkText(self): return "a link"
    def position(self):
        from PyQt6.QtCore import QPoint
        return QPoint(5, 5)

def steps(ike, qapp, out):
    from PyQt6.QtCore import QTimer, QUrl
    from PyQt6.QtGui import QGuiApplication
    from PyQt6.QtWidgets import QApplication, QMenu
    from ike import contextmenu
    win = ike.windows[0]
    v = win.current_view()
    v.setHtml("<p>page", QUrl("https://example.org/a?utm_source=x&id=7&fbclid=abc&gclid=1&mc_eid=9"))
    yield 800
    dirty = "https://shop.example/item?id=42&utm_source=news&utm_medium=mail&fbclid=XYZ&gclid=Q&mc_eid=1#top"
    menu = contextmenu.build(v, Req(dirty))
    texts = [a.text() for a in menu.actions() if a.text()]
    out["link_menu"] = texts
    [a for a in menu.actions() if a.text() == "Copy clean link"][0].trigger()
    yield 100
    out["copied"] = QGuiApplication.clipboard().text()
    out["ftp"] = "Copy clean link" in [a.text() for a in contextmenu.build(v, Req("ftp://x.example/f")).actions()]
    # the address bar's own menu
    seen = {}
    def look():
        m = [w for w in QApplication.topLevelWidgets() if isinstance(w, QMenu) and w.isVisible()]
        if m:
            seen["bar"] = [a.text() for a in m[0].actions() if a.text()]
            for a in m[0].actions():
                if a.text() == WHICH:
                    a.trigger()
            m[0].close()
    from PyQt6.QtGui import QContextMenuEvent
    for which in ("Copy clean link", "Paste and go"):
        WHICH = which
        if which == "Paste and go":
            QGuiApplication.clipboard().setText("https://example.com/pasted")
        QTimer.singleShot(300, look)
        win.urlbar.contextMenuEvent(QContextMenuEvent(QContextMenuEvent.Reason.Mouse,
                                                      win.urlbar.rect().center()))
        yield 1500
        out[which] = [seen.get("bar"), QGuiApplication.clipboard().text(), win.current_view().url().toString()]
'''


def test_copy_clean_link_and_paste_and_go(run_ike):
    out = run_ike(LINKS, timeout=90)
    links = out["link_menu"]
    assert links.index("Copy clean link") == links.index("Copy link address") + 1
    assert out["copied"] == "https://shop.example/item?id=42#top"
    assert out["ftp"] is False
    bar, clip, _url = out["Copy clean link"]
    assert bar[:2] == ["Paste and go", "Copy clean link"], bar
    assert clip == "https://example.org/a?id=7"
    bar, _clip, url = out["Paste and go"]
    assert url == "https://example.com/pasted"


def test_clean_link_keeps_an_address_without_trackers():
    from ike.contextmenu import clean_link
    assert clean_link("https://example.org/a?q=1") == "https://example.org/a?q=1"
    assert clean_link("https://example.org/") == "https://example.org/"
    assert clean_link("https://example.org/?utm_campaign=x") == "https://example.org/"


def test_recently_closed_tabs(run_ike):
    out = run_ike(r'''
def steps(ike, qapp, out):
    from PyQt6.QtCore import QUrl
    win = ike.windows[0]
    views = []
    for i in range(12):
        v = win.add_tab(QUrl("about:blank"))
        v.setHtml("<title>Page %d</title>" % i, QUrl("https://site%d.example/" % i))
        views.append(v)
    yield 1500
    for v in views:
        win.close_tab(v)
    yield 200
    win.m_history.aboutToShow.emit()
    entries = [a.text() for a in win.m_history.actions()]
    out["history_menu"] = entries
    out["enabled"] = win.m_closed.menuAction().isEnabled()
    win.m_closed.aboutToShow.emit()
    acts = win.m_closed.actions()
    out["closed"] = [[a.text(), a.toolTip(), not a.icon().isNull()] for a in acts]
    # one picked from the list, then Ctrl+Shift+T: the last one closed
    acts[3].trigger()
    yield 300
    out["picked"] = win.current_view().pending_url or win.current_view().url().toString()
    win.act_reopen.trigger()
    yield 300
    out["reopened"] = win.current_view().pending_url or win.current_view().url().toString()
    out["left"] = len(win.closed_tabs)
    out["keys"] = win.act_reopen.shortcut().toString()
    # the same submenu in the ☰ menu's History
    hist = [a.menu() for a in win.burger.actions() if a.menu() is not None and a.text() == "History"][0]
    hist.aboutToShow.emit()
    out["burger"] = win.m_closed in [a.menu() for a in hist.actions()]
''', timeout=90)
    h = out["history_menu"]
    assert h.index("Recently closed tabs") == h.index("Reopen closed tab") + 1
    assert out["enabled"]
    closed = out["closed"]
    assert len(closed) == 10
    assert [c[0] for c in closed] == ["Page %d" % i for i in range(11, 1, -1)]
    assert closed[0][1] == "https://site11.example/" and all(c[2] for c in closed)
    assert out["picked"].startswith("https://site8.example")
    assert out["reopened"].startswith("https://site11.example")
    assert out["left"] == 10 and out["keys"] == "Ctrl+Shift+T" and out["burger"]


def test_recently_closed_tabs_empty_and_private(run_ike):
    out = run_ike(r'''
def steps(ike, qapp, out):
    win = ike.windows[0]
    yield 300
    win.m_history.aboutToShow.emit()
    out["empty"] = win.m_closed.menuAction().isEnabled()
    priv = ike.new_window(private=True)
    v = priv.add_tab("https://example.org/")
    yield 300
    priv.close_tab(v)
    out["private"] = len(priv.closed_tabs)
    priv.close()
''')
    assert out["empty"] is False and out["private"] == 0
