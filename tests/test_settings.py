"""Settings dialog: sections, layout, applying without changes and with changes."""

import json

import pytest

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


@pytest.mark.parametrize("lang", ["en", "it", "de", "fr", "es", "pt", "zh", "ja"])
def test_settings_dialog(run_ike, lang):
    out = run_ike(SCRIPT, settings={"language": lang})
    assert out["sections"] == 7 and out["pages"] == 7
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
