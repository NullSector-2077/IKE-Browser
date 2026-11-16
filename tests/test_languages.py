"""Language packs and start-up in other languages."""

import subprocess
import sys

import pytest
from conftest import ROOT

EXPECTED = {"it": ("&File", "Impostazioni"), "de": ("&Datei", "Einstellungen"),
            "fr": ("&Fichier", "Paramètres"), "zh": ("文件(&F)", "设置"),
            "ja": ("ファイル(&F)", "設定"), "en": ("&File", "Settings")}


def test_check_lang_reports_no_errors():
    proc = subprocess.run([sys.executable, str(ROOT / "tools" / "check-lang.py")],
                          cwd=str(ROOT), capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "unknown:" not in proc.stdout
    # every bundled language is complete
    for line in proc.stdout.splitlines():
        if not line.startswith(" "):
            assert ", 0 missing," in line, line


def test_settings_list_each_language_once(run_ice):
    out = run_ice("""
        def steps(ice, qapp, out):
            yield 400
            dlg = ice.show_settings(ice.windows[0])
            yield 200
            out["codes"] = [dlg.language.itemData(i) for i in range(dlg.language.count())]
            dlg.close()
    """)
    codes = out["codes"]
    assert codes[:3] == ["auto", "it", "en"]
    assert len(codes) == len(set(codes))
    assert {"de", "es", "fr", "pt", "zh", "ja"} <= set(codes)


@pytest.mark.parametrize("code", ["it", "de", "zh", "ja"])
def test_start_in_language(run_ice, code):
    out = run_ice("""
        def steps(ice, qapp, out):
            yield 600
            from ice import i18n
            out["lang"] = i18n.current()
            win = ice.windows[0]
            out["menus"] = [a.text() for a in win.menuBar().actions()]
            out["settings"] = i18n.T("Settings")
    """, settings={"language": code})
    assert out["lang"] == code
    assert out["settings"] == EXPECTED[code][1]
    assert EXPECTED[code][0] in out["menus"]


@pytest.mark.parametrize("env_lang,code", [("de_DE.UTF-8", "de"), ("it_IT.UTF-8", "it"),
                                           ("zh_TW.UTF-8", "zh"), ("en_US.UTF-8", "en")])
def test_language_from_system(run_ice, env_lang, code):
    out = run_ice("""
        def steps(ice, qapp, out):
            yield 600
            from ice import i18n
            out["lang"] = i18n.current()
            out["settings"] = i18n.T("Settings")
    """, env={"LANG": env_lang})
    assert out["lang"] == code
    assert out["settings"] == EXPECTED[code][1]
