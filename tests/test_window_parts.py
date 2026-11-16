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
    assert out["search"].startswith("https://duckduckgo.com/?q=hello")
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
