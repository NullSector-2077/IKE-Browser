"""Shield button and the browser's own window close button."""

import sys


def test_shield_icon_levels(run_ice):
    out = run_ice("""
        from PyQt6.QtGui import QColor

        def steps(ice, qapp, out):
            yield 500
            from ice.shieldpanel import shield_icon
            res = {}
            for level in ("off", "compatibility", "balanced", "strict", "maximum"):
                for size in (16, 22):
                    img = shield_icon(level, size).pixmap(size, size).toImage()
                    w, h = img.width(), img.height()
                    # a pixel of the centre, off the letter (left of it)
                    c = QColor(img.pixel(int(w * 0.30), int(h * 0.55)))
                    res["%s-%d" % (level, size)] = [c.red(), c.green(), c.blue(), c.alpha()]
            out["pixels"] = res
            win = ice.windows[0]
            out["button_icon"] = not win.shield_btn.icon().isNull()
            ice.config["shield_level"] = "strict"
            win.update_shield()
            out["menu_icon"] = not win.m_level.icon().isNull()
    """)
    for key, (r, g, b, a) in out["pixels"].items():
        assert a > 200, key
        if key.startswith("off"):
            continue
        # dark-blue centre like the I.K.E. icon
        assert b >= r and b >= g and max(r, g, b) < 90, (key, r, g, b)
    assert out["button_icon"] and out["menu_icon"]


def test_window_close_button(run_ice):
    out = run_ice("""
        from PyQt6.QtCore import QPoint, Qt
        from PyQt6.QtGui import QColor
        from PyQt6.QtTest import QTest

        def red_pixels(btn):
            img = btn.grab().toImage()
            n = 0
            for x in range(img.width()):
                for y in range(img.height()):
                    c = QColor(img.pixel(x, y))
                    if c.red() > 150 and c.green() < 110 and c.blue() < 110:
                        n += 1
            return n

        def steps(ice, qapp, out):
            yield 800
            from ice.closebutton import WindowCloseButton
            win = ice.windows[0]
            buttons = [win.nav.widgetForAction(a) for a in win._win_btns]
            out["frameless"] = win._frameless
            out["visible"] = [a.isVisible() for a in win._win_btns]
            close = [b for b in buttons if isinstance(b, WindowCloseButton)]
            out["own_close"] = len(close)
            btn = close[0]
            out["rest_red"] = red_pixels(btn)
            btn._hovered = True
            out["hover_red"] = red_pixels(btn)
            btn._hovered = False
            second = ice.new_window()
            yield 500
            QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
            yield 800
            out["windows_after_click"] = len(ice.windows)
            out["closed_first"] = win not in ice.windows
    """, settings={"system_titlebar": False})
    assert out["frameless"] is True
    assert all(out["visible"])
    assert out["own_close"] == 1
    assert out["rest_red"] < 5
    assert out["hover_red"] > 20
    assert out["windows_after_click"] == 1 and out["closed_first"]


def test_system_titlebar_keeps_own_buttons_hidden(run_ice):
    out = run_ice("""
        def steps(ice, qapp, out):
            yield 600
            win = ice.windows[0]
            out["frameless"] = win._frameless
            out["visible"] = [a.isVisible() for a in win._win_btns]
    """)
    assert out["frameless"] is False
    assert not any(out["visible"])


def test_window_buttons_and_centred_address_bar(run_ice):
    """A separator before the window buttons, the buttons a little larger than
    the toolbar icons, and the address bar in the middle of a wide window."""
    out = run_ice("""
        from PyQt6.QtCore import QPoint

        def steps(ice, qapp, out):
            win = ice.windows[0]
            win.showNormal()
            out["sizes"] = []
            for width in (1920, 1400, 2560):
                win.resize(width, 800)
                yield 600
                ub = win.urlbar
                centre = ub.mapTo(win, QPoint(ub.width() // 2, 0)).x()
                # the real width: Windows keeps a window within the screen
                out["sizes"].append([win.width(), centre, ub.width()])
                out.setdefault("diag", []).append([width, win.nav.width(), getattr(win, "_urlbar_room", None),
                                                   getattr(win, "_urlbar_width", None),
                                                   win._nav_spacers[0].x(), win._nav_spacers[0].width()])
            first = win.nav.widgetForAction(win._win_btns[0])
            out["separator"] = type(first).__name__
            out["icon"] = win.nav.iconSize().height()
            out["buttons"] = [win.nav.widgetForAction(a).height() for a in win._win_btns[1:]]
            out["fits"] = all(win.nav.widgetForAction(a).isVisible() for a in win._win_btns[1:])
    """, settings={"system_titlebar": False})
    for (width, centre, bar), (_w, _nav, room, wanted, _start, pad) in zip(out["sizes"], out["diag"]):
        if sys.platform == "win32" and abs(centre - width / 2) > 1:
            # Windows' toolbar buttons are wider: at 1400 px the room right of the
            # middle is too small for a centred bar of half the window, so (as
            # designed) the bar keeps its width and goes as close to the middle
            # as it can
            assert bar == wanted and pad == room - wanted, (width, centre, out["diag"])
            continue
        assert abs(centre - width / 2) <= 1, (width, centre, out["diag"])
        assert bar >= width // 2
    assert out["separator"] != "WindowButton" and out["fits"]
    assert all(h >= out["icon"] * 1.2 for h in out["buttons"])


def test_toolbar_long_press_layout_and_private_badge(run_ice):
    out = run_ice("""
        from PyQt6.QtCore import QPoint

        def steps(ice, qapp, out):
            win = ice.windows[0]
            # The three navigation controls stay at the start, followed by a separator.
            actions = win.nav.actions()
            out["fixed_order"] = [actions.index(win.act_back) < actions.index(win.act_fwd)
                                  < actions.index(win.act_home)]
            home_index = actions.index(win.act_home)
            out["home_separator"] = actions[home_index + 1].isSeparator()

            # Moving an optional button to the left of the address field is persisted.
            left = win.urlbar.mapToGlobal(QPoint(0, win.urlbar.height() // 2))
            win._move_toolbar_action("reader", left)
            win._save_toolbar_layout()
            out["left_of_address"] = (win.nav.actions().index(win.act_tb_reader)
                                      < win.nav.actions().index(win.urlbar_act))
            out["saved_left"] = "reader" in ice.config["toolbar_left"]

            # It can also be returned to the right side.
            right = win.nav.mapToGlobal(QPoint(win.nav.width() - 8, win.nav.height() // 2))
            win._move_toolbar_action("reader", right)
            win._save_toolbar_layout()
            out["right_of_address"] = (win.nav.actions().index(win.act_tb_reader)
                                       > win.nav.actions().index(win.urlbar_act))
            out["saved_right"] = "reader" not in ice.config["toolbar_left"]

            # The shield and menu controls are movable too, but remain available.
            win._move_toolbar_action("shield", left)
            win._move_toolbar_action("menu", left)
            win._save_toolbar_layout()
            out["shield_left"] = win.nav.actions().index(win.shield_act) < win.nav.actions().index(win.urlbar_act)
            out["menu_left"] = win.nav.actions().index(win.menu_act) < win.nav.actions().index(win.urlbar_act)
            out["menu_not_hidden"] = win.menu_act in win.nav.actions()

            private = ice.new_window(private=True)
            yield 400
            from PyQt6.QtWidgets import QLabel
            badge = private.findChild(QLabel, "privateWindowBadge")
            out["private_badge"] = bool(badge and "border-radius" in badge.styleSheet())
    """)
    assert all(out["fixed_order"])
    assert out["home_separator"]
    assert out["left_of_address"] and out["saved_left"]
    assert out["right_of_address"] and out["saved_right"]
    assert out["shield_left"] and out["menu_left"] and out["menu_not_hidden"]
    assert out["private_badge"]
