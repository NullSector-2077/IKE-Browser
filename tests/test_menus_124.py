"""1.1.24, work package B2: the ☰ menu and the Settings regrouped (the
owner's go-ahead: "puoi riorganizzarli tu, ma devono essere fatti con
criterio e logica, e con le scritte centrate bene").

- Every entry of the menus of 1.1.23 is still there, in the menu bar and
  under the ☰ menu, and every keyboard shortcut still works.
- The ☰ menu's "More" holds the menu bar's File, Edit, View and Tools, each
  with its icon (in 1.1.23 they had none and their texts began left of the
  other menus'), and no text touches the arrow of its submenu, in every
  widget style (KDE's Breeze left 3 px or less: "View" and "Tools" touched
  it); Help is in the ☰ menu itself.
- The Settings' search field keeps the pages that have the words typed and
  marks the options, by their names, their ⓘ explanations and their choices,
  without accents and capitals; Esc empties it; nothing found says so.
- In each Settings page the options of every form start on one line.
- The toolbar buttons a user can add (Zoom, Manage bookmarks, Print or save
  as PDF, Send to device, Site resources) are hidden at first, are shown
  from the Settings or the toolbar's menu, stay after a new start, and do
  what they say.
"""

import pytest
from conftest import screen

STYLES = ["Breeze", "Fusion", "Windows", "Oxygen", "kvantum"]

# every entry of the menu bar of 1.1.23 (and of the menus it fills when they open)
ENTRIES_1123 = [
    "New tab", "New window", "New private window", "New tab in container", "Profiles", "Open file…",
    "Save page as…", "Save as PDF…", "Print…", "Screenshot…", "Import from another browser…",
    "Back up I.K.E. data…", "Restore a backup…", "Close tab", "Close window", "Quit", "Undo", "Redo", "Cut",
    "Copy", "Paste", "Select all", "Find in page…", "Vertical tabs", "Menu bar", "System title bar",
    "Customise toolbar…", "Split view", "Reader mode", "Workspaces", "Zoom in", "Zoom out", "Actual size",
    "Dark mode for pages", "On everywhere", "On for this site", "Full screen", "Page source",
    "Developer tools", "Protection level for every site", "Off", "Compatibility", "Balanced", "Strict",
    "Maximum", "Repair this site", "Site permissions…", "Update filter lists now", "Clear browsing data…",
    "Protection settings…", "User scripts", "Skip ads in videos", "Cookie banners", "Password manager",
    "Notify me when a page changes", "Video in a floating window", "Translate page", "Containers",
    "Site resources", "Weather on the new tab page", "Command bar", "Plasma integration",
    "Automatic scrolling", "Open selected text with middle click", "Manage extensions…", "Command bar…",
    "Downloads", "Passwords…", "Fill login on this page", "Search open tabs…", "Translate page…",
    "Video in floating window", "Mute tab", "Suspend inactive tabs now", "Site resources…",
    "Watched pages…", "Search engines…", "Chrome Web Store", "Settings…", "Keyboard shortcuts",
    "Check for I.K.E. updates", "About I.K.E.", "About Qt",
    # filled when their menu opens
    "Reopen closed tab", "Show all history", "Bookmark this page", "Manage bookmarks", "Manage containers…",
    "New profile…", "New workspace…", "Rename workspace…", "Delete workspace",
]
# the ☰ menu of 1.1.23, its own entries
BURGER_1123 = ["New tab", "New window", "New private window", "Protection", "I.K.E. extensions",
               "Dark mode for pages", "Zoom", "History", "Bookmarks", "Downloads", "Print…", "Save as PDF…",
               "Screenshot…", "More", "Settings…", "Check for I.K.E. updates", "About I.K.E.", "Quit"]
KEYS_1123 = [
    "Alt+1", "Alt+2", "Alt+3", "Alt+4", "Alt+5", "Alt+6", "Alt+7", "Alt+8", "Alt+9", "Alt+D", "Alt+Home",
    "Alt+Left", "Alt+Right", "Ctrl++", "Ctrl+,", "Ctrl+-", "Ctrl+0", "Ctrl+=", "Ctrl+D", "Ctrl+F", "Ctrl+F5",
    "Ctrl+H", "Ctrl+J", "Ctrl+L", "Ctrl+M", "Ctrl+N", "Ctrl+O", "Ctrl+P", "Ctrl+PgDown", "Ctrl+PgUp", "Ctrl+Q",
    "Ctrl+R", "Ctrl+S", "Ctrl+Shift+2", "Ctrl+Shift+A", "Ctrl+Shift+B", "Ctrl+Shift+Del", "Ctrl+Shift+E",
    "Ctrl+Shift+I", "Ctrl+Shift+K", "Ctrl+Shift+L", "Ctrl+Shift+M", "Ctrl+Shift+N", "Ctrl+Shift+O",
    "Ctrl+Shift+R", "Ctrl+Shift+S", "Ctrl+Shift+T", "Ctrl+Shift+Tab", "Ctrl+Shift+V", "Ctrl+Shift+W",
    "Ctrl+T", "Ctrl+Tab", "Ctrl+U", "Ctrl+W", "Esc", "F1", "F11", "F12", "F2", "F5", "F6", "F9", "Shift+Esc"]

WALK = r'''
def walk(menu, seen=None, path="", found=None):
    """{entry text: [paths]} of a menu and its submenus, the dynamic ones filled."""
    seen = set() if seen is None else seen
    found = {} if found is None else found
    if menu is None or id(menu) in seen:
        return found
    seen.add(id(menu))
    menu.aboutToShow.emit()
    for a in menu.actions():
        if a.isSeparator():
            continue
        t = a.text().replace("&", "")
        if t.startswith("Bookmarks bar:"):
            t = "Bookmarks bar"
        found.setdefault(t, []).append(path)
        if a.menu() is not None:
            walk(a.menu(), seen, path + " > " + t, found)
    return found
'''


def test_every_entry_and_shortcut_of_1123_is_still_there(run_ike):
    out = run_ike(WALK + r'''
def steps(ike, qapp, out):
    win = ike.windows[0]
    yield 600
    bar = {}
    seen = set()
    for a in win.menuBar().actions():
        walk(a.menu(), seen, a.text().replace("&", ""), bar)
    burger = walk(win.burger, path="☰")
    out["bar"] = sorted(bar)
    out["burger"] = sorted(burger)
    out["top"] = [a.text() for a in win.burger.actions() if not a.isSeparator()]
    out["keys"] = sorted({k.toString() for a in win.actions() for k in a.shortcuts()})
    # More: the menu bar's File, Edit, View and Tools, the same actions, an icon each; Help in ☰
    bar_menus = {a.text(): a.menu() for a in win.menuBar().actions()}
    more = win.m_more
    copies = [a.menu() for a in more.actions() if a.menu() is not None]
    out["more"] = [m.title() for m in copies]
    out["more_icons"] = [not m.icon().isNull() for m in copies]
    out["same"] = [[x.text() for x in m.actions()] == [x.text() for x in bar_menus[t].actions()]
                   and all(x is y for x, y in zip(m.actions(), bar_menus[t].actions()) if not x.isSeparator())
                   for m, t in zip(copies + [win.m_help_burger],
                                   ["&File", "&Edit", "&View", "&Tools", "&Help"])]
    out["help"] = [win.m_help_burger.title(), not win.m_help_burger.icon().isNull()]
    out["menubar_icons"] = [a.text() for a in win.menuBar().actions() if not a.icon().isNull()]
''')
    missing_bar = [e for e in ENTRIES_1123 if e not in out["bar"]]
    missing_burger = [e for e in ENTRIES_1123 + BURGER_1123 if e not in out["burger"]]
    assert not missing_bar and not missing_burger, (missing_bar, missing_burger)
    assert "Bookmarks bar" in out["bar"] and "Bookmarks bar" in out["burger"]
    assert [k for k in KEYS_1123 if k not in out["keys"]] == []
    assert out["more"] == ["File", "Edit", "View", "Tools"], out["more"]
    assert all(out["more_icons"]) and all(out["same"]), out
    assert out["help"] == ["Help", True] and out["menubar_icons"] == []
    # the ☰ menu: no entry twice (1.1.23 had "Check for updates" and "About" also under More → Help)
    assert len(out["top"]) == len(set(out["top"]))


def test_menu_titles_without_accelerators():
    """The ☰ menu's copies drop the menu bar's "&" (Latin or in brackets, CJK style)."""
    from ike.window import plain_title
    assert plain_title("&File") == "File" and plain_title("S&trumenti") == "Strumenti"
    assert plain_title("ファイル(&F)") == "ファイル" and plain_title("ملف (&F)") == "ملف"
    assert plain_title("A && B") == "A & B"


ARROWS = r'''
def steps(ike, qapp, out):
    import sys
    sys.path.insert(0, TESTS)
    import textfit
    from PyQt6.QtCore import QPoint
    from PyQt6.QtWidgets import QApplication
    win = ike.windows[0]
    win.resize(1300, 800)
    yield 700
    st = qapp.style()
    out["style"] = st.baseStyle().name() if hasattr(st, "baseStyle") else st.name()
    gaps, lefts, widths = {}, {}, {}
    seen = set()
    def settle():
        for _ in range(3):
            QApplication.processEvents()
    def look(m, path):
        if id(m) in seen:
            return
        seen.add(id(m))
        m.popup(win.mapToGlobal(QPoint(30, 30)))
        settle()
        for a in m.actions():
            if a.menu() is not None and a.isVisible():
                g = textfit.arrow_gap(m, a)
                if g is not None:
                    gaps[path + " > " + textfit.plain(a.text())] = g
        m.hide()
        for a in m.actions():
            if a.menu() is not None and a.isVisible():
                look(a.menu(), path + " > " + textfit.plain(a.text()))
    look(win.burger, "☰")
    out["gaps"] = gaps
    out["arrow_gap"] = textfit.ARROW_GAP
'''


@pytest.mark.parametrize("lang", ["it", "ar"])
@pytest.mark.parametrize("style", STYLES)
def test_no_text_touches_a_submenu_arrow(run_ike, tmp_path, style, lang):
    """The ☰ menu and every menu under it, "More" first: each text at least
    ARROW_GAP px from its submenu's arrow, in every widget style installed,
    left to right and right to left."""
    import os
    env = dict(screen(tmp_path, 1366, 768), QT_STYLE_OVERRIDE=style)
    out = run_ike(ARROWS.replace("TESTS", repr(os.path.dirname(__file__))), env=env,
                  settings={"language": lang}, timeout=200)
    if style.lower() not in (out["style"] or "").lower():
        pytest.skip("the %s style is not installed here (got %r)" % (style, out["style"]))
    close = {k: v for k, v in out["gaps"].items() if v < out["arrow_gap"]}
    assert not close, close
    if not (style == "Oxygen" and lang == "ar"):      # Oxygen draws no submenu arrows right to left
        assert any(k.startswith("☰ > ") and k.count(" > ") == 2 for k in out["gaps"]), out["gaps"]


SEARCH = r'''
def steps(ike, qapp, out):
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest
    win = ike.windows[0]
    yield 500
    dlg = win.open_settings("general")
    yield 400
    def state():
        shown = [dlg.PAGES[i] for i in range(dlg.nav.count()) if not dlg.nav.item(i).isHidden()]
        page = dlg.PAGES[dlg.stack.currentIndex()]
        marks = dlg._marks.get(dlg.stack.currentIndex())
        n = len(marks.targets) if marks is not None and marks.isVisible() else 0
        rects = marks.rects() if n else []
        return {"shown": shown, "page": page, "marks": n, "rects": len(rects),
                "none": dlg.search_none.isVisible()}
    res = {}
    for word in WORDS:
        dlg.search.setText(word)
        yield 250
        res[word] = state()
        res[word]["found"] = dlg.find_options()
    out["res"] = res
    # Esc empties the field first, the window stays; the pages come back, the marks go
    dlg.search.setFocus()
    QTest.keyClick(dlg.search, Qt.Key.Key_Escape)
    yield 200
    out["esc"] = [dlg.search.text(), dlg.isVisible(), state()]
    out["placeholder"] = dlg.search.placeholderText()
    dlg.close()
'''


def test_settings_search(run_ike, tmp_path):
    words = ["zoom", "modalita lettura", "va-api", "dark reader", "DOWNLOAD", "qqqxxyy", "vertic", "estensioni"]
    out = run_ike(SEARCH.replace("WORDS", repr(words)), env=screen(tmp_path, 1366, 768),
                  settings={"language": "it"})
    res = out["res"]
    # by an option's name ("Zoom predefinito"), on its page
    assert "appearance" in res["zoom"]["found"] and res["zoom"]["page"] == res["zoom"]["shown"][0]
    assert res["zoom"]["marks"] >= 1 and res["zoom"]["rects"] == res["zoom"]["marks"]
    assert "general" not in res["zoom"]["shown"]
    # by an explanation only (the ⓘ of the video decoding, page System)
    assert res["va-api"]["found"].get("system", 0) >= 1, res["va-api"]
    # by a choice of a combo box ("Dark Reader", Appearance)
    assert res["dark reader"]["found"].get("appearance", 0) >= 1
    # small or capital letters, accents: "DOWNLOAD", "modalita" for "modalità"
    assert "downloads" in res["DOWNLOAD"]["found"]
    assert res["modalita lettura"]["found"] or res["modalita lettura"]["none"] is False
    # a page by its name ("Estensioni di I.K.E.")
    assert "extensions" in res["estensioni"]["found"]
    # nothing: said, and every page stays in the list
    assert res["qqqxxyy"]["none"] and res["qqqxxyy"]["found"] == {} and len(res["qqqxxyy"]["shown"]) == 11
    assert out["esc"][0] == "" and out["esc"][1] is True
    assert out["esc"][2]["marks"] == 0 and len(out["esc"][2]["shown"]) == 11 and not out["esc"][2]["none"]
    assert out["placeholder"] == "Cerca un'impostazione"


ALIGN = r'''
def steps(ike, qapp, out):
    from PyQt6.QtCore import QPoint
    from PyQt6.QtWidgets import QFormLayout, QWidget
    win = ike.windows[0]
    yield 500
    dlg = win.open_settings()
    yield 300
    R = QFormLayout.ItemRole
    res = {}
    for i, page in enumerate(dlg.PAGES):
        dlg.nav.setCurrentRow(i)
        yield 150
        w = dlg.stack.widget(i).widget()
        rtl = w.isRightToLeft()
        starts = set()
        for f in w.findChildren(QFormLayout):
            for r in range(f.rowCount()):
                lab, field = f.itemAt(r, R.LabelRole), f.itemAt(r, R.FieldRole)
                if lab is None or field is None or lab.widget() is None or not lab.widget().isVisible():
                    continue
                g = field.geometry()
                owner = f.parentWidget()
                lg = lab.widget().geometry()
                if abs(lg.top() - g.top()) > g.height():          # the option under its name: not on the line
                    continue
                x = owner.mapTo(w, g.topRight() if rtl else g.topLeft()).x()
                starts.add(w.width() - x if rtl else x)
        res[page] = sorted(starts)
    out["starts"] = res
    dlg.close()
'''


@pytest.mark.parametrize("lang", ["en", "ar"])
def test_settings_options_start_on_one_line(run_ike, tmp_path, lang):
    out = run_ike(ALIGN, env=screen(tmp_path, 1600, 1000), settings={"language": lang})
    for page, starts in out["starts"].items():
        if len(starts) > 1:
            assert starts[-1] - starts[0] <= 1, (page, starts)
    assert len(out["starts"]["appearance"]) >= 1 and len(out["starts"]["system"]) >= 1


TOOLBAR = r'''
def steps(ike, qapp, out):
    win = ike.windows[0]
    win.resize(1500, 800)
    yield 600
    NEW = ["zoom", "bookmarks", "print", "send", "resources"]
    def keys():
        return set(win.toolbar_layout.shown("left") + win.toolbar_layout.shown("right"))
    out["start_hidden"] = [k in ike.config["toolbar_hidden"] for k in NEW]
    out["start_shown"] = [k in keys() for k in NEW]
    # the toolbar's own menu lists them (a right click on the toolbar)
    from PyQt6.QtWidgets import QMenu
    m = QMenu()
    win._fill_toolbar_buttons(m)
    out["menu_entries"] = [a.data() for a in m.actions() if a.data() in NEW]
    # shown from the Settings, Appearance
    dlg = win.open_settings("appearance")
    yield 300
    for k in NEW:
        dlg.tb_btns[k].setChecked(True)
    dlg.apply()
    dlg.close()
    yield 300
    out["after"] = [k in keys() for k in NEW]
    out["saved"] = [k in ike.config["toolbar_hidden"] for k in NEW]
    btn = {k: win.nav.widgetForAction(a) for k, a, _x in win._nav_items}
    out["buttons"] = [btn[k] is not None and btn[k].isVisible() for k in NEW] if not win.toolbar_spilled else "spilled"
    # what each does
    # 1.1.25: the Zoom button opens its panel (tests/test_zoom_panel.py); the ☰ menu keeps the submenu
    out["zoom_menu"] = [a.text() for a in win.m_zoom.actions()]
    out["zoom_button"] = [win.act_tb_zoom.menu() is None]
    btn["zoom"].click()
    yield 300
    zmenu, _zpanel = win.panel_of("zoom")
    out["zoom_button"].append(zmenu is not None and zmenu.isVisible())
    if zmenu is not None:
        zmenu.hide()
    out["print_menu"] = [a.text() for a in win.act_tb_print.menu().actions()]
    win.m_send.aboutToShow.emit()
    out["send_menu"] = [[a.text(), a.isEnabled()] for a in win.m_send.actions()]
    out["popup"] = [btn[k].popupMode().name for k in ("zoom", "print", "send")]
    calls = []
    ike.show_bookmarks = lambda *a: calls.append("bookmarks")
    ike.show_resources = lambda *a: calls.append("resources")
    win.act_tb_bookmarks.triggered.disconnect()
    win.act_tb_bookmarks.triggered.connect(lambda *_a: ike.show_bookmarks())
    win.act_tb_resources.triggered.disconnect()
    win.act_tb_resources.triggered.connect(lambda *_a: ike.show_resources())
    btn["bookmarks"].click()
    btn["resources"].click()
    yield 100
    out["calls"] = calls
    # Site resources goes with its extension
    from ike import ikeextensions
    ikeextensions.set_on(ike, "resources", False)
    yield 200
    out["resources_off"] = "resources" in keys()
    ikeextensions.set_on(ike, "resources", True)
    yield 200
    out["resources_on"] = "resources" in keys()
'''


def test_toolbar_buttons_to_add(run_ike, tmp_path):
    out = run_ike(TOOLBAR, env=screen(tmp_path, 1600, 1000), settings={"start_maximized": False})
    assert out["start_hidden"] == [True] * 5 and out["start_shown"] == [False] * 5
    assert out["menu_entries"] == ["zoom", "bookmarks", "print", "send", "resources"]
    assert out["after"] == [True] * 5 and out["saved"] == [False] * 5
    assert out["buttons"] == [True] * 5, out["buttons"]
    assert out["zoom_menu"] == ["Zoom in", "Zoom out", "Actual size"]
    assert out["zoom_button"] == [True, True]
    assert out["print_menu"] == ["Print…", "Save as PDF…"]
    # no KDE Connect here: one entry that says so, disabled
    assert out["send_menu"][0][1] is False and out["send_menu"][-1] == ["Desktop integration", True]
    assert out["popup"] == ["InstantPopup"] * 3
    assert out["calls"] == ["bookmarks", "resources"]
    assert out["resources_off"] is False and out["resources_on"] is True
    # after a new start they are still there
    again = run_ike("""
        def steps(ike, qapp, out):
            yield 500
            win = ike.windows[0]
            out["keys"] = win.toolbar_layout.shown("left") + win.toolbar_layout.shown("right")
    """, env=screen(tmp_path, 1600, 1000), keep_profile=True)
    assert {"zoom", "bookmarks", "print", "send", "resources"} <= set(again["keys"])
