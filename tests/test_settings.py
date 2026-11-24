"""Settings dialog: sections, layout, applying without changes and with changes."""

import json

import pytest
from conftest import screen

SCRIPT = """
    def steps(ike, qapp, out):
        yield 600
        import json
        from ike.config import CONFIG_DIR
        ike.config.save()
        before = json.loads((CONFIG_DIR / "settings.json").read_text("utf-8"))
        dlg = ike.show_settings(ike.windows[0])
        yield 400
        out["sections"] = dlg.nav.count()
        out["pages"] = dlg.stack.count()
        out["labels"] = [dlg.nav.item(i).text() for i in range(dlg.nav.count())]
        out["icons"] = [not dlg.nav.item(i).icon().isNull() for i in range(dlg.nav.count())]
        sideways = {}
        for i in range(dlg.stack.count()):
            dlg.nav.setCurrentRow(i)
            yield 100
            area = dlg.stack.widget(i)
            sideways[dlg.PAGES[i]] = area.horizontalScrollBar().maximum()
        out["sideways"] = sideways
        dlg.apply()                     # nothing changed
        yield 100
        after = json.loads((CONFIG_DIR / "settings.json").read_text("utf-8"))
        out["same_keys"] = sorted(before) == sorted(after)
        out["changed"] = sorted(k for k in before if k in after and before[k] != after[k]
                                and k not in ("session",))
        dlg.homepage.setText("https://example.org/")
        dlg.apply()
        yield 100
        out["homepage"] = json.loads((CONFIG_DIR / "settings.json").read_text("utf-8"))["homepage"]
        dlg.close()
"""


@pytest.mark.parametrize("lang", ["en", "it", "de", "fr", "es", "pt", "zh", "ja", "ru", "uk", "be", "bg",
                                  "pl", "cs", "sk", "sl", "hr", "sr", "bs", "mk"])
def test_settings_dialog(run_ike, tmp_path, lang):
    # 1.1.21: the window is never larger than the screen: a screen of a small laptop
    # (Qt's offscreen one, 800 x 800, is narrower than any desktop)
    out = run_ike(SCRIPT, settings={"language": lang}, env=screen(tmp_path, 1280, 800))
    # 1.1.0 added "New tab page"; 1.1.20: Language, Protection, Privacy, I.K.E. extensions,
    # Updates and System in place of "Privacy and protection", "Components and extensions"
    # and "User scripts"
    assert out["sections"] == 11 and out["pages"] == 11
    assert out["sideways"]["extensions"] == 0, out["sideways"]
    assert out["sideways"]["newtab"] == 0, out["sideways"]
    assert all(out["icons"])
    assert out["sideways"]["appearance"] == 0, out["sideways"]
    assert out["sideways"]["general"] == 0, out["sideways"]
    assert out["same_keys"]
    assert out["changed"] == [], out["changed"]
    assert out["homepage"] == "https://example.org/"


def test_settings_keys_unchanged(run_ike, tmp_path):
    """The keys written to settings.json are part of the user's data: a list of
    them is kept in tests/settings-keys.json and must not change by accident."""
    run_ike("""
        def steps(ike, qapp, out):
            yield 300
            ike.config.save()
    """)
    from conftest import ROOT
    keys = sorted(json.loads((tmp_path / "home/.config/ike-browser/settings.json")
                             .read_text("utf-8")))
    expected = json.loads((ROOT / "tests" / "settings-keys.json").read_text("utf-8"))
    assert keys == expected


def test_settings_write_the_weather_units(run_ike, tmp_path):
    """Wind speed and pressure sit next to the temperature unit (1.1.25): "Automatic" first, the choices
    as symbols; applying writes the keys."""
    out = run_ike("""
        def steps(ike, qapp, out):
            yield 600
            import json
            from ike.config import CONFIG_DIR
            dlg = ike.show_settings(ike.windows[0])
            yield 400
            out["wind_items"] = [dlg.wind_unit.itemText(i) for i in range(dlg.wind_unit.count())]
            out["wind_data"] = [dlg.wind_unit.itemData(i) for i in range(dlg.wind_unit.count())]
            out["p_items"] = [dlg.pressure_unit.itemText(i) for i in range(dlg.pressure_unit.count())]
            out["p_data"] = [dlg.pressure_unit.itemData(i) for i in range(dlg.pressure_unit.count())]
            out["start"] = [dlg.wind_unit.currentData(), dlg.pressure_unit.currentData()]
            dlg.wind_unit.setCurrentIndex(dlg.wind_unit.findData("kn"))
            dlg.pressure_unit.setCurrentIndex(dlg.pressure_unit.findData("mmhg"))
            dlg.apply()
            yield 100
            saved = json.loads((CONFIG_DIR / "settings.json").read_text("utf-8"))
            out["saved"] = [saved["weather_wind_unit"], saved["weather_pressure_unit"], saved["weather_unit"]]
            dlg.close()
            dlg = ike.show_settings(ike.windows[0])
            yield 400
            out["again"] = [dlg.wind_unit.currentData(), dlg.pressure_unit.currentData()]
            dlg.close()
    """, env=screen(tmp_path, 1280, 800))
    assert out["wind_items"][1:] == ["km/h", "mph", "m/s", "kn"]
    assert out["wind_data"] == ["auto", "kmh", "mph", "ms", "kn"]
    assert out["p_items"][1:] == ["hPa", "mbar", "inHg", "mmHg"]
    assert out["p_data"] == ["auto", "hpa", "mbar", "inhg", "mmhg"]
    assert out["start"] == ["auto", "auto"]
    assert out["saved"] == ["kn", "mmhg", "celsius"] and out["again"] == ["kn", "mmhg"]
