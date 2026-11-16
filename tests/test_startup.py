"""Start-up: one window with the new tab page, and a clean exit."""


def test_starts_with_new_tab(run_ike):
    out = run_ike("""
        def steps(ike, qapp, out):
            yield 1500
            win = ike.windows[0]
            out["windows"] = len(ike.windows)
            out["tabs"] = len(win.views)
            out["url"] = win.current_view().url().toString()
            out["title"] = win.windowTitle()
            out["version"] = __import__("ike").__version__
            out["visible"] = win.isVisible()
    """)
    assert out["windows"] == 1
    assert out["tabs"] == 1
    assert out["url"].startswith("ike:")
    assert out["visible"]
    assert "I.K.E." in out["title"]
    assert out["_exit"] == 0


def test_opens_address_from_command_line(run_ike):
    out = run_ike("""
        def steps(ike, qapp, out):
            yield 1500
            views = ike.windows[0].views
            out["tabs"] = len(views)
            out["title"] = views[0].title()
    """, args=["data:text/html,<title>hello</title>hi"])
    assert out["tabs"] == 1
    assert out["title"] == "hello"


def test_private_window(run_ike):
    out = run_ike("""
        def steps(ike, qapp, out):
            yield 800
            win = ike.windows[0]
            out["private"] = win.private
            out["off_the_record"] = win.current_view().page().profile().isOffTheRecord()
    """, args=["--private"])
    assert out["private"] is True
    assert out["off_the_record"] is True
