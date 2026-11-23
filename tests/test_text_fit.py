"""1.1.21: every text of the interface fits its place, in every language.

For each language pack (ike/resources/lang, and English) a new window is
opened in that language, inside one browser per group of languages, on a
screen of 1366 x 768 (a common laptop; the owner's QHD screen has more
room): the window itself, the ☰ menu and every submenu, the menus of the
menu bar, the shield's panel, the find bar, the notice of a page in full
screen, every page of the Settings and the other windows that open without
a question (About, history, bookmarks, downloads, clear data, user scripts,
the colours editor, languages, import, resources, watched pages, site
permissions, the command bar); since 1.1.24 also the menus of the toolbar
buttons a user can add and the Settings' search with nothing found.
tests/textfit.py says what is checked: a button's text at least 4 px from
its frame on each side, labels, check boxes and combo boxes with all of
their text, nothing cut by a parent or wider than the screen, menus taller
than the screen that scroll. Every problem is reported with its language,
place, widget and text.

IKE_UI_SHOTS=<folder>: pictures of the window (1600 x 1000), the ☰ menu, two
submenus, three Settings pages, the extensions page, an explanation opened
from its ⓘ and About in de, fi, ru, ar, he, ja and zh are saved there
(test_screenshots).
"""

import os
from pathlib import Path

import pytest
from conftest import screen

ROOT = Path(__file__).resolve().parent.parent
TESTS = Path(__file__).resolve().parent
LANGS = ["en"] + sorted(p.stem for p in (ROOT / "ike" / "resources" / "lang").glob("*.json"))
GROUPS = 4
# the writing system of each language not written in the Latin alphabet
SCRIPTS = {"ar": "Arabic", "fa": "Arabic", "ur": "Arabic", "he": "Hebrew", "hi": "Devanagari",
           "mr": "Devanagari", "ne": "Devanagari", "bn": "Bengali", "ta": "Tamil", "te": "Telugu",
           "th": "Thai", "ka": "Georgian", "hy": "Armenian", "ja": "Japanese", "zh": "SimplifiedChinese",
           "ko": "Korean", "el": "Greek", "ru": "Cyrillic", "uk": "Cyrillic", "be": "Cyrillic",
           "bg": "Cyrillic", "sr": "Cyrillic", "mk": "Cyrillic", "kk": "Cyrillic"}
SCREEN = (1366, 768)


STEPS = r"""
def steps(ike, qapp, out):
    import sys
    sys.path.insert(0, TESTS)
    import textfit
    from PyQt6.QtCore import QPoint, Qt
    from PyQt6.QtWidgets import QApplication
    from ike import i18n
    yield 400
    problems = []
    timing = {}

    import os
    def log(*a):
        if os.environ.get("IKE_FIT_LOG"):
            with open(os.environ["IKE_FIT_LOG"], "a") as f:
                print(*a, file=f)

    def settle():
        for _ in range(3):
            QApplication.processEvents()

    def menus_of(menu, path, seen):
        if menu is None or id(menu) in seen:
            return
        seen.add(id(menu))
        yield menu, path
        for a in menu.actions():
            if a.menu() is not None and a.isVisible():
                yield from menus_of(a.menu(), path + " > " + textfit.plain(a.text()), seen)

    def check_menu(menu, where, pos):
        log("menu", where)
        menu.popup(pos)
        settle()
        problems.extend(textfit.check_menu(menu, where))
        menu.hide()

    def dialog(where, dlg):
        log("dialog", where)
        settle()
        problems.extend(textfit.check(dlg, where))
        dlg.close()
        dlg.deleteLater()

    import time
    from PyQt6.QtGui import QFontDatabase
    have = {ws.name for ws in QFontDatabase.writingSystems()}
    out["no_font"] = []
    for code in LANGS:
        started = time.time()
        if SCRIPTS.get(code, "Latin") not in have:
            out["no_font"].append(code)          # nothing to measure: no font draws this language here
            continue
        i18n.setup(code)
        qapp.setLayoutDirection(Qt.LayoutDirection.RightToLeft if i18n.right_to_left()
                                else Qt.LayoutDirection.LeftToRight)
        log("lang", code)
        win = ike.new_window()
        yield 120
        win.showMaximized()
        yield 80
        problems.extend(textfit.check(win, code + ": window"))
        win.findbar.open_bar()
        settle()
        problems.extend(textfit.check(win.findbar, code + ": find bar"))
        win.findbar.close_bar()
        for kind in ("fullscreen", "mouse"):          # the notice over the page
            win.show_exclusive_notice("https://www.example-video-site.com", kind)
            settle()
            problems.extend(textfit.check(win._notice, code + ": notice " + kind))
        win._notice.hide()
        corner = win.mapToGlobal(QPoint(win.width() // 2, 40))
        seen = set()
        for menu, path in menus_of(win.burger, "☰", seen):
            check_menu(menu, code + ": " + path, corner)
        for a in win.menuBar().actions():
            for menu, path in menus_of(a.menu(), textfit.plain(a.text()), seen):
                check_menu(menu, code + ": " + path, corner)
        # 1.1.24: the menus of the toolbar buttons a user can add (Send to device:
        # its one entry that says no device is paired)
        for name in ("m_zoom", "m_print", "m_send"):
            menu = getattr(win, name, None)
            if menu is not None and id(menu) not in seen:
                seen.add(id(menu))
                menu.aboutToShow.emit()
                check_menu(menu, code + ": toolbar > " + name[2:], corner)
        win.show_shield_menu()
        settle()
        problems.extend(textfit.check(win.shield_scroll, code + ": shield panel"))
        problems.extend(textfit.check_menu(win.shield_menu, code + ": shield panel"))
        win.shield_panel.adv_btn.setChecked(True)
        settle()
        win.fit_shield_menu()
        settle()
        problems.extend(textfit.check(win.shield_scroll, code + ": shield panel, advanced"))
        win.shield_panel.adv_btn.setChecked(False)
        win.shield_menu.hide()
        dlg = win.open_settings()
        settle()
        for i, page in enumerate(dlg.PAGES):
            dlg.nav.setCurrentRow(i)
            settle()
            log("settings", page)
            problems.extend(textfit.check(dlg, code + ": Settings > " + page))
        if hasattr(dlg, "search"):
            # 1.1.24: the search field, nothing found (its note under the pages' list)
            dlg.search.setText("qqqxxyy")
            settle()
            problems.extend(textfit.check(dlg, code + ": Settings > search, nothing found"))
            dlg.search.clear()
            settle()
        dlg.close()
        dlg.deleteLater()
        if hasattr(win, "about_dialog"):
            about = win.about_dialog()
        else:                      # before 1.1.21: the message box of show_about
            from PyQt6.QtWidgets import QMessageBox
            about = QMessageBox(win)
            about.setTextFormat(Qt.TextFormat.RichText)
            about.setText(win.about_text())
        about.show()
        dialog(code + ": About", about)
        for name in ("show_history", "show_bookmarks", "show_downloads", "show_clear_data",
                     "show_userscripts", "show_import", "show_resources", "show_watches",
                     "show_permissions"):
            dialog(code + ": " + name[5:], getattr(ike, name)())
        from ike.dialogs import LanguageDownloadDialog, ThemeEditor
        d = LanguageDownloadDialog(ike, win)
        d.show()
        dialog(code + ": languages", d)
        log("dialog colours")
        d = ThemeEditor(ike, "system", win)
        log("made")
        d.show()
        settle()
        log("shown")
        problems.extend(textfit.check(d, code + ": colours"))
        log("checked")
        d.reject()
        log("rejected")
        from ike.palette import CommandBar
        bar = CommandBar(win)            # palette.open_bar runs its own loop
        bar.show()
        dialog(code + ": command bar", bar)
        win.close()
        win.deleteLater()
        yield 50
        timing[code] = round(time.time() - started, 2)
    out["problems"] = problems
    out["timing"] = timing
"""


def _groups():
    return [LANGS[i::GROUPS] for i in range(GROUPS)]


@pytest.mark.parametrize("group", range(GROUPS))
def test_every_text_fits_in_every_language(run_ike, tmp_path, group):
    langs = _groups()[group]
    if os.environ.get("IKE_FIT_LANGS"):          # a quick look at a few languages
        if group:
            pytest.skip("IKE_FIT_LANGS: one group")
        langs = os.environ["IKE_FIT_LANGS"].split(",")
    script = (STEPS.replace("TESTS", repr(str(TESTS))).replace("LANGS", repr(langs))
              .replace("SCRIPTS", repr(SCRIPTS)))
    env = screen(tmp_path, *SCREEN)
    if os.environ.get("IKE_FIT_LOG"):
        env["IKE_FIT_LOG"] = os.environ["IKE_FIT_LOG"]
    out = run_ike(script, env=env, timeout=600)
    problems = out["problems"]
    if out["no_font"]:
        import warnings
        warnings.warn("no font on this computer for %s: not measured" % ", ".join(out["no_font"]))
    assert len(out["no_font"]) < len(langs), "no language could be measured"
    report = "\n".join("%s | %s | %r | %s" % tuple(p) for p in problems)
    assert not problems, "%d texts do not fit:\n%s" % (len(problems), report)


SHOTS = r"""
def steps(ike, qapp, out):
    import os
    from PyQt6.QtCore import QPoint, Qt
    from PyQt6.QtWidgets import QApplication
    from ike import i18n
    yield 400
    folder = FOLDER
    saved = []

    def save(widget, name):
        for _ in range(3):
            QApplication.processEvents()
        path = os.path.join(folder, name + ".png")
        widget.grab().save(path)
        saved.append(path)

    for code in LANGS:
        i18n.setup(code)
        qapp.setLayoutDirection(Qt.LayoutDirection.RightToLeft if i18n.right_to_left()
                                else Qt.LayoutDirection.LeftToRight)
        win = ike.new_window()
        win.showNormal()
        win.resize(1600, 1000)
        yield 300
        save(win, code + "-window")
        burger = win.burger
        burger.popup(win.mapToGlobal(QPoint(win.width() - 380, 50)))
        yield 100
        save(burger, code + "-menu")
        sub = win.m_extensions
        sub.popup(win.mapToGlobal(QPoint(win.width() - 760, 120)))
        yield 100
        save(sub, code + "-submenu-extensions")
        sub.hide()
        protection = win.m_level
        protection.popup(win.mapToGlobal(QPoint(win.width() - 760, 120)))
        yield 100
        save(protection, code + "-submenu-protection")
        protection.hide()
        burger.hide()
        dlg = win.open_settings()
        yield 200
        for page in ("general", "appearance", "protection", "extensions"):
            dlg.show_page(page)
            yield 150
            save(dlg, "%s-settings-%s" % (code, page))
        # an explanation opened from its ⓘ (the longest of the protection page)
        from PyQt6.QtWidgets import QToolButton
        infos = [b for b in dlg.findChildren(QToolButton, "ike_info") if b.isVisible()]
        longest = max(infos, key=lambda b: len(b.accessibleName()))
        longest.show_text()
        yield 150
        tip = [w for w in QApplication.topLevelWidgets()
               if w.metaObject().className() == "QWhatsThat" and w.isVisible()]
        if tip:
            save(tip[0], code + "-explanation")
            tip[0].close()
        dlg.close()
        about = win.about_dialog()
        about.show()
        yield 150
        save(about, code + "-about")
        about.close()
        win.close()
        yield 100
    out["saved"] = saved
"""

SHOT_LANGS = ["de", "fi", "ru", "ar", "he", "ja", "zh"]


@pytest.mark.skipif(not os.environ.get("IKE_UI_SHOTS"), reason="IKE_UI_SHOTS=<folder> takes the pictures")
def test_screenshots(run_ike, tmp_path):
    folder = Path(os.environ["IKE_UI_SHOTS"])
    folder.mkdir(parents=True, exist_ok=True)
    script = SHOTS.replace("FOLDER", repr(str(folder))).replace("LANGS", repr(SHOT_LANGS))
    out = run_ike(script, env=screen(tmp_path, 1920, 1200), timeout=300)
    assert len(out["saved"]) == 10 * len(SHOT_LANGS)


def test_info_buttons_menus_and_windows_on_a_small_screen(run_ike, tmp_path):
    """The ⓘ of each option: its explanation as tooltip and accessible name, a
    window with it on a click, Space or Enter (Enter does not close the
    Settings), Esc or a click closes it. A menu longer than the
    screen scrolls; About and the Settings fit a small screen (1024 x 600)."""
    out = run_ike("""
        def steps(ike, qapp, out):
            from PyQt6.QtCore import QPoint, Qt
            from PyQt6.QtTest import QTest
            from PyQt6.QtWidgets import QApplication, QLabel, QMenu, QScrollArea, QToolButton
            yield 500
            win = ike.windows[0]
            area = win.screen().availableGeometry()
            dlg = win.open_settings("general")
            yield 300
            infos = dlg.findChildren(QToolButton, "ike_info")
            out["infos"] = len(infos)
            out["hint_lines"] = len(dlg.findChildren(QLabel, "ike_hint"))
            out["focusable"] = all(b.focusPolicy() & Qt.FocusPolicy.TabFocus for b in infos)
            out["named"] = all(b.accessibleName() and b.accessibleName() == b.whatsThis() for b in infos)
            out["tips"] = all(b.toolTip().startswith(("<p>", "<table")) for b in infos)
            out["wrapped_tips"] = sum("<table" in b.toolTip() for b in infos)

            def popup():          # Qt's own window of QWhatsThis, open
                return [w for w in QApplication.topLevelWidgets()
                        if w.metaObject().className() == "QWhatsThat" and w.isVisible()]
            b = [x for x in infos if x.isVisible()][0]
            out["text"] = b.accessibleName()
            b.setFocus()
            QTest.keyClick(b, Qt.Key.Key_Space)
            yield 200
            out["space"] = bool(popup())
            QTest.keyClick(popup()[0] if popup() else b, Qt.Key.Key_Escape)
            yield 200
            out["esc_closes"] = not popup()
            b.setFocus()
            QTest.keyClick(b, Qt.Key.Key_Return)
            yield 200
            out["enter"] = bool(popup()) and dlg.isVisible()
            shown = popup()
            QTest.mouseClick(shown[0] if shown else dlg, Qt.MouseButton.LeftButton)     # a click closes it
            yield 200
            out["click_closes"] = not popup()
            QTest.mouseClick(b, Qt.MouseButton.LeftButton)
            yield 200
            out["click"] = bool(popup())
            if popup():
                popup()[0].hide()
            out["settings"] = [dlg.width(), dlg.height(), area.width(), area.height()]
            dlg.close()
            # a long menu (history with many pages, a long list of engines...)
            m = QMenu(win)
            for i in range(80):
                m.addAction("Page %d" % i)
            m.popup(QPoint(10, 10))
            yield 200
            out["menu"] = [m.height(), area.height(), m.style().styleHint(m.style().StyleHint.SH_Menu_Scrollable)]
            m.hide()
            # About
            about = win.about_dialog()
            about.show()
            yield 200
            scroll = about.findChild(QScrollArea)
            out["about"] = [about.frameGeometry().height(), about.width(), area.width(),
                            scroll.verticalScrollBar().maximum()]
            label = about.findChild(QLabel, "ike_about_text")
            out["about_text"] = "Components and licences" in label.text()
            about.close()
    """, env=screen(tmp_path, 1024, 600))
    assert out["infos"] > 8 and out["hint_lines"] == 0, out
    assert out["focusable"] and out["named"] and out["tips"], out
    assert out["space"] and out["esc_closes"] and out["enter"] and out["click_closes"] and out["click"], out
    w, h, sw, sh = out["settings"]
    assert w <= sw and h <= sh, out["settings"]
    height, screen_h, scrollable = out["menu"]
    assert scrollable and height <= screen_h, out["menu"]
    about_h, about_w, sw2, about_scroll = out["about"]
    assert about_h <= 600 and about_w <= sw2 and about_scroll > 0 and out["about_text"], out["about"]
