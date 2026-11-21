"""Address bar, vertical tabs, shield panel and find bar inside a window."""


def test_address_bar(run_ike):
    out = run_ike("""
        def steps(ike, qapp, out):
            yield 600
            win = ike.windows[0]
            r = lambda t: win.resolve(t).toString()
            out["host"] = r("example.org")
            out["local"] = r("localhost:8000/x")
            out["search"] = r("hello world")
            out["keyword"] = r("w Rome")
            win.urlbar.setText("data:text/html,<title>typed</title>")
            win.navigate(win.urlbar.text())
            yield 1200
            out["title"] = win.current_view().title()
            win.sync_urlbar()
            out["bar"] = win.urlbar.text()
    """)
    assert out["host"] == "http://example.org"
    assert out["local"] == "http://localhost:8000/x"
    assert out["search"].startswith("https://www.startpage.com/do/search?q=hello")      # the default since 1.1.19
    assert "wikipedia.org" in out["keyword"] and "Rome" in out["keyword"]
    assert out["title"] == "typed"
    assert out["bar"].startswith("data:text/html")


def test_vertical_tabs(run_ike):
    out = run_ike("""
        from PyQt6.QtCore import Qt

        def steps(ike, qapp, out):
            yield 600
            win = ike.windows[0]
            for i in range(3):
                win.add_tab("data:text/html,<title>t%d</title>" % i)
            yield 1500
            out["rows"] = win.vtabs.count()
            out["visible"] = win.vtab_panel.isVisible()
            out["titles"] = [win.vtabs.item(i).text() for i in range(win.vtabs.count())]
            # the close button of the last row
            delegate = win.vtabs.itemDelegate()
            row = win.vtabs.count() - 1
            rect = win.vtabs.visualItemRect(win.vtabs.item(row))
            out["zone_inside"] = rect.contains(delegate._zone(rect).center())
            delegate.close_requested.emit(row)
            yield 600
            out["rows_after"] = win.vtabs.count()
            out["tabs_after"] = len(win.views)
    """, settings={"tabs_position": "vertical"})
    assert out["visible"]
    assert out["rows"] == 4
    assert "t2" in out["titles"][-1]
    assert out["zone_inside"]
    assert out["rows_after"] == 3 and out["tabs_after"] == 3


def test_shield_panel(run_ike):
    out = run_ike("""
        def steps(ike, qapp, out):
            yield 600
            win = ike.windows[0]
            win.add_tab("data:text/html,<title>x</title>x")
            yield 800
            panel = win.shield_panel
            panel.refresh()
            out["count"] = panel.count.text()
            ike.config["shield_level"] = "maximum"
            win.update_shield()
            panel.refresh()
            out["ok"] = True
    """)
    assert out["ok"] and out["count"] != ""


def test_find_bar(run_ike):
    out = run_ike("""
        def steps(ike, qapp, out):
            yield 600
            win = ike.windows[0]
            win.add_tab("data:text/html,<p>alpha beta alpha</p>")
            yield 1000
            win.findbar.open_bar()
            out["open"] = win.findbar.isVisible()
            win.findbar.close_bar()
            out["closed"] = not win.findbar.isVisible()
    """)
    assert out["open"] and out["closed"]


def test_vertical_tabs_with_only_their_icons(run_ike):
    """1.1.16: a button at the top of the panel narrows it to the tabs' icons
    and back; the choice is kept, and the user's own width comes back."""
    out = run_ike("""
        from PyQt6.QtCore import QPoint, Qt
        from PyQt6.QtTest import QTest

        def steps(ike, qapp, out):
            win = ike.windows[0]
            win.showNormal()
            win.resize(1200, 800)
            yield 600
            for i in range(2):
                win.add_tab("data:text/html,<title>t%d</title>" % i)
            yield 1200
            out["before"] = [win.vtab_panel.width(), bool(win.vplus.text()), win.vicons_btn.toolTip()]
            QTest.mouseClick(win.vicons_btn, Qt.MouseButton.LeftButton)
            yield 600
            win = ike.windows[0]
            d = win.vtabs.itemDelegate()
            rect = win.vtabs.visualItemRect(win.vtabs.item(1))
            img = win.vtabs.viewport().grab(rect).toImage()
            out["on"] = [ike.config["vtabs_icons_only"], win.vtab_panel.width(), win.vplus.text(),
                         win.vicons_btn.toolTip(), d._hit(rect.center()), d._hit(QPoint(rect.right() - 4, rect.center().y())),
                         img.width() > 0, win.vtabs.count()]
            QTest.mouseClick(win.vicons_btn, Qt.MouseButton.LeftButton)
            yield 600
            out["off"] = [ike.config["vtabs_icons_only"], ike.windows[0].vtab_panel.width(),
                          bool(ike.windows[0].vplus.text()), ike.config["vtabs_width"]]
    """, settings={"tabs_position": "vertical", "vtabs_width": 260})
    width, has_text, tip = out["before"]
    assert width >= 200 and has_text and tip == "Show only the icons of the tabs"
    on, narrow, text, tip_on, hit_mid, hit_right, painted, rows = out["on"]
    assert on is True and narrow == 48 and text == "" and tip_on == "Show the titles of the tabs"
    assert hit_mid == [1, ""] and hit_right == [1, ""]      # no close button area: closing by middle click or menu
    assert painted and rows == 3
    off, wide, text_back, kept = out["off"]
    assert off is False and wide >= 200 and text_back and kept == 260
