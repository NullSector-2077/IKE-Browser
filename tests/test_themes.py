"""Interface themes: apply, save, restart, delete, back to the system look."""


def test_builtin_themes_and_back_to_system(run_ice):
    out = run_ice("""
        from PyQt6.QtGui import QPalette

        def steps(ice, qapp, out):
            yield 600
            from ice import themes
            win = ice.windows[0]
            role = QPalette.ColorRole.Window
            out["system_window"] = qapp.palette().color(role).name()
            out["system_font"] = qapp.font().toString()
            out["applied"] = {}
            for key, _label in themes.names():
                ice.config["ui_scheme"] = "theme:" + key
                themes.apply(ice.config)
                yield 50
                out["applied"][key] = [qapp.palette().color(role).name(),
                                       win.nav.palette().color(role).name(),
                                       win.nav.autoFillBackground()]
            ice.config["ui_scheme"] = "system"
            themes.apply(ice.config)
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


def test_system_theme_touches_nothing(run_ice):
    out = run_ice("""
        from PyQt6.QtGui import QPalette

        def steps(ice, qapp, out):
            yield 600
            from ice import themes
            out["original"] = dict(themes._original)
            out["nav_fill"] = ice.windows[0].nav.autoFillBackground()
    """)
    assert out["original"] == {}
    assert out["nav_fill"] is False


def test_user_theme_saved_restored_and_deleted(run_ice):
    theme = {"background": "#202830", "text": "#f0f0f0", "accent": "#ff8800",
             "toolbar": "#101820", "tabs": "#303840", "font_family": "", "font_size": 13}
    first = run_ice("""
        def steps(ice, qapp, out):
            yield 600
            from ice import themes
            ice.config["ui_themes"] = {"Mine": %r}
            ice.config["ui_scheme"] = "user:Mine"
            ice.config.save()
            themes.apply(ice.config)
            yield 50
            out["font_size"] = qapp.font().pointSize()
    """ % theme)
    assert first["font_size"] == 13
    # same profile, new start: the saved theme is applied at start-up
    second = run_ice("""
        from PyQt6.QtGui import QPalette

        def steps(ice, qapp, out):
            yield 600
            from ice import themes
            out["window"] = qapp.palette().color(QPalette.ColorRole.Window).name()
            out["font_size"] = qapp.font().pointSize()
            # delete it, as the settings page does
            ice.config["ui_themes"] = {}
            ice.config["ui_scheme"] = "system"
            ice.config.save()
            themes.apply(ice.config)
            yield 50
            out["after_delete"] = themes.current(ice.config)
            out["original_kept"] = bool(themes._original)
    """, keep_profile=True)
    assert second["window"] == "#202830"
    assert second["font_size"] == 13
    assert second["after_delete"] is None
    assert second["original_kept"] is False
