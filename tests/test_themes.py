"""Interface themes: apply, save, restart, delete, back to the system look."""


def test_builtin_themes_and_back_to_system(run_ike):
    out = run_ike("""
        from PyQt6.QtGui import QPalette

        def steps(ike, qapp, out):
            yield 600
            from ike import themes
            win = ike.windows[0]
            role = QPalette.ColorRole.Window
            out["system_window"] = qapp.palette().color(role).name()
            out["system_font"] = qapp.font().toString()
            out["applied"] = {}
            for key, _label in themes.names():
                ike.config["ui_scheme"] = "theme:" + key
                themes.apply(ike.config)
                yield 50
                out["applied"][key] = [qapp.palette().color(role).name(),
                                       win.nav.palette().color(role).name(),
                                       # painted in the theme's colour: by the palette or, for the
                                       # Cyber theme, by the toolbar's own style sheet
                                       win.nav.autoFillBackground() or "background" in win.nav.styleSheet()]
            ike.config["ui_scheme"] = "system"
            themes.apply(ike.config)
            yield 50
            out["back_window"] = qapp.palette().color(role).name()
            out["back_font"] = qapp.font().toString()
            out["back_nav_fill"] = win.nav.autoFillBackground()
            out["builtin"] = {k: [v["background"], v["toolbar"]] for k, v in themes.BUILTIN.items()}
    """)
    for key, (window, toolbar, fill) in out["applied"].items():
        assert window == out["builtin"][key][0], key
        assert toolbar == out["builtin"][key][1], key
        assert fill, key
    assert out["back_window"] == out["system_window"]
    assert out["back_font"] == out["system_font"]
    assert out["back_nav_fill"] is False


def test_system_theme_touches_nothing(run_ike):
    out = run_ike("""
        from PyQt6.QtGui import QPalette

        def steps(ike, qapp, out):
            yield 600
            from ike import themes
            out["original"] = dict(themes._original)
            out["nav_fill"] = ike.windows[0].nav.autoFillBackground()
    """)
    assert out["original"] == {}
    assert out["nav_fill"] is False


def test_user_theme_saved_restored_and_deleted(run_ike):
    theme = {"background": "#202830", "text": "#f0f0f0", "accent": "#ff8800",
             "toolbar": "#101820", "tabs": "#303840", "font_family": "", "font_size": 13}
    first = run_ike("""
        def steps(ike, qapp, out):
            yield 600
            from ike import themes
            ike.config["ui_themes"] = {"Mine": %r}
            ike.config["ui_scheme"] = "user:Mine"
            ike.config.save()
            themes.apply(ike.config)
            yield 50
            out["font_size"] = qapp.font().pointSize()
    """ % theme)
    assert first["font_size"] == 13
    # same profile, new start: the saved theme is applied at start-up
    second = run_ike("""
        from PyQt6.QtGui import QPalette

        def steps(ike, qapp, out):
            yield 600
            from ike import themes
            out["window"] = qapp.palette().color(QPalette.ColorRole.Window).name()
            out["font_size"] = qapp.font().pointSize()
            # delete it, as the settings page does
            ike.config["ui_themes"] = {}
            ike.config["ui_scheme"] = "system"
            ike.config.save()
            themes.apply(ike.config)
            yield 50
            out["after_delete"] = themes.current(ike.config)
            out["original_kept"] = bool(themes._original)
    """, keep_profile=True)
    assert second["window"] == "#202830"
    assert second["font_size"] == 13
    assert second["after_delete"] is None
    assert second["original_kept"] is False
