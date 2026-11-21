"""1.1.21: every on / off option is a switch, like those of the I.K.E. extensions.

The owner asked for the switches of the "I.K.E. extensions" page everywhere,
in place of the old check boxes: in the windows and the Settings (ike.uistyle
.Switch), in the lists whose entries can be ticked (a switch drawn by
SwitchDelegate) and in the menus (a small switch drawn by the interface's
style for an entry that can be turned on and off; a choice among several
keeps its dot).

The windows are those tests/test_text_fit.py opens, in English and in Arabic
(right to left).
"""

import os
import re
from pathlib import Path

import pytest
from conftest import screen

ROOT = Path(__file__).resolve().parent.parent


def test_no_plain_check_box_in_the_code():
    """Every check box of the interface is made as a Switch (also in the
    windows the test below does not open)."""
    found = []
    for path in sorted((ROOT / "ike").rglob("*.py")):
        for n, line in enumerate(path.read_text("utf-8").splitlines(), 1):
            if re.search(r"\bQCheckBox\(", line) and "class " not in line:
                found.append("%s:%d: %s" % (path.relative_to(ROOT), n, line.strip()))
    assert not found, "plain check boxes:\n" + "\n".join(found)


STEPS = r"""
def steps(ike, qapp, out):
    from PyQt6.QtCore import QPoint, Qt
    from PyQt6.QtWidgets import QAbstractItemView, QApplication, QCheckBox
    from ike import i18n
    try:
        from ike.uistyle import Switch
    except ImportError:               # before 1.1.21: the switch of the extensions page only
        from ike.dialogs import Switch
    yield 400
    plain, lists, seen = [], [], {"boxes": 0, "switches": 0}

    def settle():
        for _ in range(3):
            QApplication.processEvents()

    def look(top, where):
        for w in [top] + top.findChildren(QCheckBox):
            if not isinstance(w, QCheckBox) or not w.isVisible():
                continue
            seen["boxes"] += 1
            if isinstance(w, Switch):
                seen["switches"] += 1
            else:
                plain.append([where, w.text() or w.accessibleName()])
        for v in top.findChildren(QAbstractItemView):
            m = v.model()
            if not v.isVisible() or m is None:
                continue
            ticked = [r for r in range(m.rowCount())               # entries with a tick of their own
                      if m.data(m.index(r, 0), Qt.ItemDataRole.CheckStateRole) is not None]
            if ticked and type(v.itemDelegate()).__name__ != "SwitchDelegate":
                lists.append([where, type(v).__name__, type(v.itemDelegate()).__name__])

    def dialog(where, dlg):
        settle()
        look(dlg, where)
        dlg.close()
        dlg.deleteLater()

    for code in LANGS:
        i18n.setup(code)
        qapp.setLayoutDirection(Qt.LayoutDirection.RightToLeft if i18n.right_to_left()
                                else Qt.LayoutDirection.LeftToRight)
        win = ike.new_window()
        yield 120
        win.showMaximized()
        yield 80
        look(win, code + ": window")
        win.findbar.open_bar()
        settle()
        look(win.findbar, code + ": find bar")
        win.findbar.close_bar()
        win.show_shield_menu()
        win.shield_panel.adv_btn.setChecked(True)
        settle()
        win.fit_shield_menu()
        settle()
        look(win.shield_scroll, code + ": shield panel")
        win.shield_panel.adv_btn.setChecked(False)
        win.shield_menu.hide()
        dlg = win.open_settings()
        settle()
        for i, page in enumerate(dlg.PAGES):
            dlg.nav.setCurrentRow(i)
            settle()
            look(dlg, code + ": Settings > " + page)
        dlg.close()
        dlg.deleteLater()
        for name in ("show_history", "show_bookmarks", "show_downloads", "show_clear_data",
                     "show_userscripts", "show_import", "show_resources", "show_watches",
                     "show_permissions"):
            dialog(code + ": " + name[5:], getattr(ike, name)())
        from ike.dialogs import LanguageDownloadDialog, ThemeEditor
        d = LanguageDownloadDialog(ike, win)
        d.show()
        dialog(code + ": languages", d)
        d = ThemeEditor(ike, "system", win)
        d.show()
        settle()
        look(d, code + ": colours")
        d.reject()
        win.close()
        win.deleteLater()
        yield 50
    out["plain"] = plain
    out["lists"] = lists
    out["seen"] = seen
"""


def test_every_check_box_is_a_switch(run_ike, tmp_path):
    out = run_ike(STEPS.replace("LANGS", repr(["en", "ar"])), env=screen(tmp_path, 1366, 768),
                  timeout=400)
    assert out["seen"]["boxes"] > 40, out["seen"]
    report = "\n".join("%s | %s" % tuple(p) for p in out["plain"])
    assert not out["plain"], "%d check boxes are not switches:\n%s" % (len(out["plain"]), report)
    assert not out["lists"], "lists with ticks instead of switches: %r" % out["lists"]


def test_menus_draw_a_switch_not_a_tick(run_ike, tmp_path):
    """An entry that can be turned on and off is drawn with a switch, not
    with the tick of the plain style; a choice among several keeps its dot."""
    out = run_ike("""
        def steps(ike, qapp, out):
            from PyQt6.QtCore import QRect, Qt
            from PyQt6.QtGui import QAction, QActionGroup, QColor, QImage, QPainter
            from PyQt6.QtWidgets import QMenu, QStyle, QStyleFactory, QStyleOptionMenuItem
            yield 300
            win = ike.windows[0]
            plain = QStyleFactory.create(qapp.style().baseStyle().name()
                                         if hasattr(qapp.style(), "baseStyle") else qapp.style().name())
            out["base"] = plain.name()
            toggles = QMenu(win)
            for text in ("Menu bar", "Vertical tabs"):
                toggles.addAction(text).setCheckable(True)
            choice = QMenu(win)
            group = QActionGroup(choice)
            for text in ("Standard", "Strict"):
                a = choice.addAction(text)
                a.setCheckable(True)
                group.addAction(a)

            def picture(style, menu, kind, checked, rtl=False):
                opt = QStyleOptionMenuItem()
                opt.initFrom(menu)
                opt.rect = QRect(0, 0, 220, 26)
                opt.text = "Menu bar"
                opt.menuItemType = QStyleOptionMenuItem.MenuItemType.Normal
                opt.checkType = kind
                opt.checked = checked
                opt.menuHasCheckableItems = True
                opt.maxIconWidth = 0
                opt.state |= QStyle.StateFlag.State_Enabled
                if checked:
                    opt.state |= QStyle.StateFlag.State_On
                if rtl:
                    opt.direction = Qt.LayoutDirection.RightToLeft
                img = QImage(220, 26, QImage.Format.Format_ARGB32)
                img.fill(QColor("white"))
                p = QPainter(img)
                style.drawControl(QStyle.ControlElement.CE_MenuItem, opt, p, menu)
                p.end()
                return img

            def differ(a, b):
                return sum(a.pixel(x, y) != b.pixel(x, y) for x in range(a.width()) for y in range(a.height()))

            CT = QStyleOptionMenuItem.CheckType
            ours, theirs = qapp.style(), plain
            out["toggle_on"] = differ(picture(ours, toggles, CT.NonExclusive, True),
                                      picture(theirs, toggles, CT.NonExclusive, True))
            out["toggle_off"] = differ(picture(ours, toggles, CT.NonExclusive, False),
                                       picture(theirs, toggles, CT.NonExclusive, False))
            out["toggle_rtl"] = differ(picture(ours, toggles, CT.NonExclusive, True, True),
                                       picture(theirs, toggles, CT.NonExclusive, True, True))
            # on and off look different (the knob moves)
            out["on_off"] = differ(picture(ours, toggles, CT.NonExclusive, True),
                                   picture(ours, toggles, CT.NonExclusive, False))
            out["dot"] = differ(picture(ours, choice, CT.Exclusive, True),
                                picture(theirs, choice, CT.Exclusive, True))
            # the real menus: the switch keeps the text whole, and it is drawn in them
            import sys
            sys.path.insert(0, TESTS)
            import textfit
            problems = []
            for menu in (win.m_extensions, toggles):
                menu.popup(win.mapToGlobal(win.rect().center()))
                yield 100
                problems += textfit.check_menu(menu, "menu")
                menu.hide()
            out["problems"] = problems
    """.replace("TESTS", repr(str(Path(__file__).resolve().parent))), env=screen(tmp_path, 1366, 768))
    assert out["toggle_on"] > 20 and out["toggle_off"] > 20 and out["toggle_rtl"] > 20, out
    assert out["on_off"] > 20, out
    assert out["dot"] == 0, out
    assert not out["problems"], out["problems"]


def test_switches_and_list_switches_toggle(run_ike, tmp_path):
    """A switch turns on and off with a click on it or on its text and with
    Space; a list's switch with a click on it and with Space. The setting
    follows, as with the check boxes before."""
    out = run_ike("""
        def steps(ike, qapp, out):
            from PyQt6.QtCore import Qt
            from PyQt6.QtTest import QTest
            from PyQt6.QtWidgets import QCheckBox
            yield 400
            win = ike.windows[0]
            dlg = win.open_settings("protection")
            yield 300
            lists = dlg.lists
            item = lists.item(0)
            before = item.checkState()
            r = lists.visualItemRect(item)
            delegate = lists.itemDelegate()
            out["delegate"] = type(delegate).__name__
            box = (delegate.switch_rect(lists, lists.model().index(0, 0)) if hasattr(delegate, "switch_rect")
                   else r)
            QTest.mouseClick(lists.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                             box.center())
            yield 50
            out["click"] = item.checkState() != before
            lists.setFocus()
            lists.setCurrentItem(item)
            QTest.keyClick(lists, Qt.Key.Key_Space)
            yield 50
            out["space"] = item.checkState() == before
            # the text of a list entry is not covered by the switch
            out["text_after_switch"] = (box.right() < r.right() - 40) if hasattr(delegate, "switch_rect") else None
            dlg.show_page("general")
            yield 200
            sw = dlg.smooth
            out["kind"] = type(sw).__name__
            was = sw.isChecked()
            got = []
            sw.toggled.connect(got.append)
            QTest.mouseClick(sw, Qt.MouseButton.LeftButton)
            yield 50
            out["sw_click"] = sw.isChecked() != was
            sw.setFocus()
            QTest.keyClick(sw, Qt.Key.Key_Space)
            yield 50
            out["sw_space"] = sw.isChecked() == was and len(got) == 2
            # a switch with its own text: a click on the text turns it too
            box = [b for b in dlg.findChildren(QCheckBox) if b.isVisible() and b.text()]
            out["texted"] = len(box)
            dlg.close()
            win.findbar.open_bar()
            yield 100
            case = win.findbar.case
            out["case_kind"] = type(case).__name__
            on = case.isChecked()
            from PyQt6.QtCore import QPoint
            QTest.mouseClick(case, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                             QPoint(case.width() - 6, case.height() // 2))
            yield 50
            out["text_click"] = case.isChecked() != on
            out["case_size"] = [case.width(), case.sizeHint().width()]
    """, env=screen(tmp_path, 1366, 768))
    assert out["delegate"] == "SwitchDelegate", out
    assert out["click"] and out["space"] and out["text_after_switch"], out
    assert out["kind"] == "Switch" and out["sw_click"] and out["sw_space"], out
    assert out["case_kind"] == "Switch" and out["text_click"], out


SHOTS = r"""
def steps(ike, qapp, out):
    import os
    from PyQt6.QtCore import QPoint, Qt
    from PyQt6.QtWidgets import QApplication
    from ike import i18n
    yield 400
    folder, scheme = FOLDER, SCHEME
    saved = []

    def save(widget, name):
        for _ in range(3):
            QApplication.processEvents()
        path = os.path.join(folder, "%s-%s.png" % (scheme, name))
        widget.grab().save(path)
        saved.append(path)

    for code in LANGS:
        i18n.setup(code)
        qapp.setLayoutDirection(Qt.LayoutDirection.RightToLeft if i18n.right_to_left()
                                else Qt.LayoutDirection.LeftToRight)
        win = ike.new_window()
        win.showNormal()
        win.resize(1400, 900)
        yield 300
        dlg = win.open_settings()
        yield 200
        for page in ("general", "protection", "privacy"):
            dlg.show_page(page)
            yield 150
            save(dlg, "%s-settings-%s" % (code, page))
        dlg.close()
        win.show_shield_menu()
        win.shield_panel.adv_btn.setChecked(True)
        yield 100
        win.fit_shield_menu()
        yield 150
        save(win.shield_menu, code + "-shield")
        win.shield_panel.adv_btn.setChecked(False)
        win.shield_menu.hide()
        view = [a.menu() for a in win.menuBar().actions() if a.menu() is not None][2]
        for name, menu in (("view", view), ("extensions", win.m_extensions), ("dark", win.m_dark)):
            menu.popup(win.mapToGlobal(QPoint(win.width() // 2 - 150, 60)))
            yield 120
            toggles = [a for a in menu.actions() if a.isCheckable()]
            if toggles:
                menu.setActiveAction(toggles[0])          # the highlight on an entry with a switch
            yield 80
            save(menu, "%s-menu-%s" % (code, name))
            menu.hide()
        win.close()
        yield 100
    out["saved"] = saved
"""


@pytest.mark.skipif(not os.environ.get("IKE_UI_SHOTS"), reason="IKE_UI_SHOTS=<folder> takes the pictures")
@pytest.mark.parametrize("scheme", ["light", "theme:ike"])
def test_switch_screenshots(run_ike, tmp_path, scheme):
    """Pictures of the switches (Settings > General, Protection, Privacy, the
    shield's panel, three menus) in en, de and ar, light and the dark I.K.E. theme."""
    folder = Path(os.environ["IKE_UI_SHOTS"])
    folder.mkdir(parents=True, exist_ok=True)
    langs = ["en", "de", "ar"]
    script = (SHOTS.replace("FOLDER", repr(str(folder))).replace("SCHEME", repr(scheme.replace("theme:", "")))
              .replace("LANGS", repr(langs)))
    out = run_ike(script, settings={"ui_scheme": scheme}, env=screen(tmp_path, 1920, 1200), timeout=300)
    assert len(out["saved"]) == 7 * len(langs)
