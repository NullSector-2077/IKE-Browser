"""Shield button and the browser's own window close button."""



def test_shield_icon_levels(run_ike):
    out = run_ike("""
        from PyQt6.QtCore import QSize, QUrl
        from ike.config import LEVELS, LOGIN_HOSTS, SENSITIVE_HOSTS
        from PyQt6.QtGui import QColor
        from ike.shieldpanel import LEVEL_COLOUR, LEVEL_LETTER, TOOLBAR_SHIELD_GROW, shield_icon

        def steps(ike, qapp, out):
            yield 500
            out["letters"] = LEVEL_LETTER
            for size in (16, 22):
                glyphs = []
                for level in LEVELS:
                    img = shield_icon(level, size).pixmap(size, size).toImage()
                    fill, rim = ("#343c46", "#c4cbd3") if level == "off" else ("#061e37", "#3daee9")
                    assert img.pixelColor(0, 0).alpha() == 0
                    pixels = {(x, y): img.pixelColor(x, y) for x in range(size) for y in range(size)}
                    colours = {pixel.name() for pixel in pixels.values() if pixel.alpha() == 255}
                    assert {fill, rim} <= colours, (level, size, colours)
                    # the glyph: the white X when off, else the letter in the level's colour (1.1.27)
                    want = QColor(LEVEL_COLOUR.get(level, "#F1F3F6"))

                    def near(pixel):
                        return (abs(pixel.red() - want.red()) + abs(pixel.green() - want.green())
                                + abs(pixel.blue() - want.blue())) < 90
                    ink = [(x, y) for (x, y), pixel in pixels.items() if pixel.alpha() > 200 and near(pixel)]
                    assert len(ink) >= 4, (level, size)
                    for axis in zip(*ink):
                        assert abs((min(axis) + max(axis) + 1) / 2 - size / 2) <= 1, (level, size)
                    glyphs.append(tuple(ink))
                assert len(set(glyphs)) == len(LEVELS), size

            win = ike.windows[0]
            btn = win.shield_btn
            panel = win.shield_panel
            actions = {action.data(): action for action in win.level_group.actions()}
            for level in LEVELS:
                expected = shield_icon(level).pixmap(16, 16).toImage()
                assert actions[level].icon().pixmap(16, 16).toImage() == expected
                for combo in (panel.site_level, panel.global_level):
                    assert combo.itemIcon(combo.findData(level)).pixmap(16, 16).toImage() == expected

            ike.config["shield_level"] = "maximum"
            # 1.1.27: Google's sign-in and services keep the user's level (they see a
            # current Firefox instead); Microsoft's sign-in and PayPal stay in Compatibility
            login, sensitive = LOGIN_HOSTS[0], SENSITIVE_HOSTS[0]
            hosts = [("example.test", "maximum"), ("child.override.test", "strict"),
                     ("off.test", "off"), (login, "maximum"), (sensitive, "maximum"),
                     ("login.live.com", "compatibility"), ("www.paypal.com", "compatibility")]
            for host, level in (("override.test", "strict"), ("off.test", "off")):
                ike.config.set_site_level(host, level)
            for host, level in hosts:
                win.current_view().setHtml("<p>Test page", QUrl("https://" + host + "/"))
                yield 400
                assert win.current_host() == host
                win.update_shield()
                panel.refresh()
                yield 350
                size = QSize(btn.iconSize())
                expected = shield_icon(level, grow=TOOLBAR_SHIELD_GROW).pixmap(size).toImage()
                assert btn.icon().pixmap(size).toImage() == expected, host
                expected = shield_icon(level).pixmap(16, 16).toImage()
                assert win.m_level.icon().pixmap(16, 16).toImage() == expected, host
                assert panel.master.icon().pixmap(16, 16).toImage() == expected, host
                assert panel.site_level.currentData() == level and panel.global_level.currentData() == "maximum"
            out["hosts"] = len(hosts)
    """)
    assert out["letters"] == {"compatibility": "C", "balanced": "B", "strict": "S", "maximum": "M"}
    assert out["hosts"] == 7


def test_toolbar_shield_is_larger_in_the_same_button(run_ike):
    """The shield's drawing is 15-20% larger than the plain glyph, centred
    and inside its icon box at every screen scale, with sharp edges; the
    button, inside the address bar since 1.1.10, keeps its size and covers
    none of the field's own buttons."""
    out = run_ike("""
        from PyQt6.QtCore import QSize
        from PyQt6.QtGui import QColor

        def box(img):
            xs, ys = [], []
            for x in range(img.width()):
                for y in range(img.height()):
                    if QColor.fromRgba(img.pixel(x, y)).alpha() > 24:
                        xs.append(x)
                        ys.append(y)
            return [min(xs), min(ys), max(xs) + 1, max(ys) + 1]

        def soft_edge(img):
            # partly transparent pixels on the middle row, left of the drawing's centre
            y = img.height() // 2
            return sum(1 for x in range(img.width() // 2)
                       if 8 < QColor.fromRgba(img.pixel(x, y)).alpha() < 247)

        def steps(ike, qapp, out):
            yield 600
            from ike.shieldpanel import TOOLBAR_SHIELD_GROW, shield_icon
            win = ike.windows[0]
            btn = win.shield_btn
            side = btn.iconSize().height()
            out["grow"] = TOOLBAR_SHIELD_GROW
            out["side"] = side
            out["scales"] = {}
            for level in ("off", "balanced", "maximum"):
                for dpr in (1.0, 1.25, 1.5, 2.0, 3.0):
                    plain = shield_icon(level).pixmap(QSize(side, side), dpr).toImage()
                    big = shield_icon(level, grow=TOOLBAR_SHIELD_GROW).pixmap(QSize(side, side), dpr).toImage()
                    out["scales"]["%s@%s" % (level, dpr)] = {
                        "size": [big.width(), big.height(), int(side * dpr + 0.5)],
                        "plain": box(plain), "big": box(big), "soft": soft_edge(big)}
            # what the button really shows: the rows of its left part that are not background
            win.update_shield()
            yield 150
            shot = btn.grab().toImage()
            ratio = shot.devicePixelRatio() or 1.0
            back = QColor(shot.pixel(1, 1))
            rows = []
            for y in range(shot.height()):
                for x in range(min(shot.width(), int((side + 8) * ratio))):
                    c = QColor(shot.pixel(x, y))
                    if abs(c.red() - back.red()) + abs(c.green() - back.green()) + abs(c.blue() - back.blue()) > 90:
                        rows.append(y)
                        break
            out["shown"] = [min(rows) / ratio, (max(rows) + 1) / ratio, btn.height()]
            out["margin"] = win.urlbar.height() - btn.height()
            out["counter"] = []
            for n in ("7", "123", "9876"):
                btn.setText(n)
                win.urlbar.place_end()
                yield 50
                img = btn.grab().toImage()
                bg = img.pixelColor(img.width() - 1, 0)
                rows = [y for y in range(img.height())
                        if any(abs(img.pixelColor(x, y).lightness() - bg.lightness()) > 70
                               for x in range(round((side + btn.GAP) * ratio), img.width() - 1))]
                out["counter"].append((min(rows) + max(rows) + 1 - img.height()) / (2 * ratio))
            btn.setText("")
            win.urlbar.place_end()
            from PyQt6.QtWidgets import QWidget
            out["heights"] = [btn.height() <= win.urlbar.height()]
            # neighbours: nothing of the button overlaps the field's buttons beside it
            geo = btn.geometry()
            out["inside_toolbar"] = win.urlbar.rect().contains(geo)
            out["overlap"] = [w.objectName() or type(w).__name__ for w in win.urlbar.children()
                              if isinstance(w, QWidget) and w is not btn and w.isVisible()
                              and w.geometry().intersects(geo)]
            before = [geo.width(), geo.height()]
            for level in ("off", "compatibility", "balanced", "strict", "maximum"):
                ike.config["shield_level"] = level
                win.update_shield()
                yield 50
                assert [btn.width(), btn.height()] == before, (level, btn.width(), btn.height(), before)
            out["button"] = before
    """)
    assert 1.15 <= out["grow"] <= 1.20
    for key, m in out["scales"].items():
        w, h, want = m["size"]
        assert w == h == want, (key, m)
        px0, py0, px1, py1 = m["plain"]
        bx0, by0, bx1, by1 = m["big"]
        # inside the icon box
        assert bx0 >= 0 and by0 >= 0 and bx1 <= w and by1 <= h, (key, m)
        # 15-20% larger (one device pixel of tolerance on each measure)
        for plain, big in ((px1 - px0, bx1 - bx0), (py1 - py0, by1 - by0)):
            assert (big - 1) / (plain + 1) <= 1.20 and (big + 1) / (plain - 1) >= 1.15, (key, m)
            assert big > plain, (key, m)
        # centred: the same room left and right, and above and below
        assert abs(bx0 - (w - bx1)) <= 1 and abs(by0 - (h - by1)) <= 1, (key, m)
        # drawn for this scale, not a stretched picture: the edge is one or two pixels soft
        assert m["soft"] <= 2, (key, m)
    top, bottom, height = out["shown"]
    # the drawing nearly fills the toolbar's icon box and stays inside the button
    assert 0.9 * out["side"] <= bottom - top <= out["side"], out["shown"]
    assert 0 <= top <= 1.5 and 0 <= height - bottom <= 1.5, out["shown"]
    assert abs(top - (height - bottom)) <= 1, out["shown"]
    assert out["margin"] == 4
    assert all(abs(offset) <= 1.5 for offset in out["counter"]), out["counter"]
    assert out["inside_toolbar"]
    assert out["heights"] == [True], out["heights"]
    assert not out["overlap"], out["overlap"]


def test_window_close_button(run_ike):
    out = run_ike("""
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

        def steps(ike, qapp, out):
            yield 800
            from ike.closebutton import WindowCloseButton
            win = ike.windows[0]
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
            second = ike.new_window()
            yield 500
            QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
            yield 800
            out["windows_after_click"] = len(ike.windows)
            out["closed_first"] = win not in ike.windows
    """, settings={"system_titlebar": False})
    assert out["frameless"] is True
    assert all(out["visible"])
    assert out["own_close"] == 1
    assert out["rest_red"] < 5
    assert out["hover_red"] > 20
    assert out["windows_after_click"] == 1 and out["closed_first"]


def test_system_titlebar_keeps_own_buttons_hidden(run_ike):
    out = run_ike("""
        def steps(ike, qapp, out):
            yield 600
            win = ike.windows[0]
            out["frameless"] = win._frameless
            out["visible"] = [a.isVisible() for a in win._win_btns]
            acts = [a for a in win.nav.actions() if a.isVisible()]
            out["menu"] = [win.win_sep_act.isVisible(), win.menu_act.isVisible(),
                           acts[-2:] == [win.win_sep_act, win.menu_act]]
    """)
    assert out["frameless"] is False
    assert not any(out["visible"])
    assert out["menu"] == [True, True, True]        # the menu last, the separator before it (1.1.16)


def test_window_buttons_and_centred_address_bar(run_ike):
    """A separator before the window buttons, the buttons a little larger than
    the toolbar icons, and the address bar in the middle of a wide window."""
    out = run_ike("""
        from PyQt6.QtCore import QPoint

        def steps(ike, qapp, out):
            win = ike.windows[0]
            win.showNormal()
            out["sizes"] = []
            for width in (1920, 1400, 2560):
                win.resize(width, 800)
                yield 600
                ub = win.urlbar
                # 1.1.25: the address bar and its bookmark button are centred as one block
                bm = win.nav.widgetForAction(win.act_tb_bookmark)
                centre = (ub.mapTo(win, QPoint(0, 0)).x() + bm.mapTo(win, QPoint(bm.width(), 0)).x()) // 2
                out["sizes"].append([win.width(), centre, ub.width()])
                out.setdefault("diag", []).append([width, win.nav.width(), getattr(win, "_urlbar_room", None),
                                                   getattr(win, "_urlbar_width", None),
                                                   win._nav_spacers[0].x(), win._nav_spacers[0].width()])
            first = win.nav.widgetForAction(win.win_sep_act)
            out["separator"] = type(first).__name__
            out["icon"] = win.nav.iconSize().height()
            out["buttons"] = [win.nav.widgetForAction(a).height() for a in win._win_btns]
            out["fits"] = all(win.nav.widgetForAction(a).isVisible() for a in win._win_btns)
    """, settings={"system_titlebar": False})
    for (width, centre, bar), (_w, _nav, room, wanted, _start, pad) in zip(out["sizes"], out["diag"]):
        # in the middle; or, when the buttons of one side leave too little room (1.1.9's default
        # has more on the left), as near as it gets: no room left of it, never narrower than half
        assert abs(centre - width / 2) <= 1 or (pad == 0 and centre > width / 2), (width, centre, out["diag"])
        assert bar >= width // 2
    assert out["separator"] != "WindowButton" and out["fits"]
    assert all(h >= out["icon"] * 1.2 for h in out["buttons"])


def test_fixed_toolbar_buttons_and_private_badge(run_ike):
    """Back, Forward, Reload and Home at the start with their separator, the
    shield inside the address bar at its right end (moving the
    other buttons is in test_toolbar.py); the badge of a private window."""
    out = run_ike("""
        def steps(ike, qapp, out):
            win = ike.windows[0]
            actions = win.nav.actions()
            out["fixed_order"] = [actions.index(win.act_back), actions.index(win.act_fwd),
                                  actions.index(win.act_reload), actions.index(win.act_home),
                                  actions.index(win.home_sep_act),
                                  int(win.shield_btn.parentWidget() is win.urlbar)]
            out["home_separator"] = win.home_sep_act.isSeparator()
            private = ike.new_window(private=True)
            yield 400
            from PyQt6.QtWidgets import QLabel
            badge = private.findChild(QLabel, "privateWindowBadge")
            out["private_badge"] = bool(badge and "border-radius" in badge.styleSheet())
            out["badge_visible"] = bool(badge and badge.isVisible())
    """)
    assert out["fixed_order"] == [0, 1, 2, 3, 4, 1] and out["home_separator"]
    assert out["private_badge"] and out["badge_visible"]
