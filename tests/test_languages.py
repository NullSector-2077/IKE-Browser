"""Language packs and start-up in other languages."""

import re
import subprocess
import sys

import pytest
from conftest import ROOT

EXPECTED = {"it": ("&File", "Impostazioni"), "de": ("&Datei", "Einstellungen"),
            "fr": ("&Fichier", "Paramètres"), "zh": ("文件(&F)", "设置"),
            "ja": ("ファイル(&F)", "設定"), "en": ("&File", "Settings"),
            "ru": ("&Файл", "Настройки"), "uk": ("&Файл", "Налаштування"), "pl": ("&Plik", "Ustawienia"),
            "cs": ("&Soubor", "Nastavení"), "sr": ("&Датотека", "Подешавања"), "bg": ("&Файл", "Настройки")}

SLAVIC = {"ru", "uk", "be", "bg", "pl", "cs", "sk", "sl", "hr", "sr", "bs", "mk"}


def test_check_lang_reports_no_errors():
    proc = subprocess.run([sys.executable, str(ROOT / "tools" / "check-lang.py")],
                          cwd=str(ROOT), capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "unknown:" not in proc.stdout
    # every bundled language is complete
    for line in proc.stdout.splitlines():
        if not line.startswith(" "):
            assert ", 0 missing," in line, line


def test_settings_list_each_language_once(run_ike):
    out = run_ike("""
        def steps(ike, qapp, out):
            yield 400
            dlg = ike.show_settings(ike.windows[0])
            yield 200
            out["codes"] = [dlg.language.itemData(i) for i in range(dlg.language.count())]
            dlg.close()
    """)
    codes = out["codes"]
    assert codes[:3] == ["auto", "it", "en"]
    assert len(codes) == len(set(codes))
    assert {"de", "es", "fr", "pt", "zh", "ja"} | SLAVIC <= set(codes)


@pytest.mark.parametrize("code", ["it", "de", "zh", "ja", "ru", "uk", "pl", "cs", "sr", "bg"])
def test_start_in_language(run_ike, code):
    out = run_ike("""
        def steps(ike, qapp, out):
            yield 600
            from ike import i18n
            out["lang"] = i18n.current()
            win = ike.windows[0]
            out["menus"] = [a.text() for a in win.menuBar().actions()]
            out["settings"] = i18n.T("Settings")
    """, settings={"language": code})
    assert out["lang"] == code
    assert out["settings"] == EXPECTED[code][1]
    assert EXPECTED[code][0] in out["menus"]


@pytest.mark.parametrize("env_lang,code", [("de_DE.UTF-8", "de"), ("it_IT.UTF-8", "it"),
                                           ("zh_TW.UTF-8", "zh"), ("en_US.UTF-8", "en"),
                                           ("ru_RU.UTF-8", "ru"), ("sr_RS.UTF-8", "sr"), ("pl_PL.UTF-8", "pl")])
def test_language_from_system(run_ike, env_lang, code):
    out = run_ike("""
        def steps(ike, qapp, out):
            yield 600
            from ike import i18n
            out["lang"] = i18n.current()
            out["settings"] = i18n.T("Settings")
    """, env={"LANG": env_lang})
    assert out["lang"] == code
    assert out["settings"] == EXPECTED[code][1]


def test_slavic_packs_are_complete_and_in_their_script():
    """The twelve Slavic packs (1.1.2): every text translated, the native name,
    and Cyrillic where the language is written in it."""
    import json
    cyrillic = re.compile("[\u0400-\u04ff]")
    every = set(json.loads((ROOT / "ike/resources/lang/it.json").read_text("utf-8"))["strings"])   # the reference
    for code in SLAVIC:
        pack = json.loads((ROOT / ("ike/resources/lang/%s.json" % code)).read_text("utf-8"))
        assert pack["code"] == code
        strings = pack["strings"]
        assert set(strings) == every and all(v.strip() for v in strings.values()), code
        uses_cyrillic = bool(cyrillic.search(strings["Settings"] + pack["name"]))
        assert uses_cyrillic == (code in {"ru", "uk", "be", "bg", "sr", "mk"}), code
        # the browser engine in About, not a search engine
        assert strings["Engine"] not in ("Wyszukiwarka", "Vyhledávač", "Vyhľadávač", "Iskalnik",
                                         "Tražilica", "Претраживач", "Pretraživač", "Пребарувач"), code


# 1.1.20: forty more languages, each in its own script (the owner's request)
SCRIPTS = {
    "Latin": ("[A-Za-zÀ-ɏ]", "af az ca da et eu fi fil gl hu id is lt lv ms nb nl ro sq sv sw tr uz vi"),
    "Greek": ("[Ͱ-Ͽ]", "el"), "Cyrillic": ("[Ѐ-ӿ]", "kk"),
    "Arabic": ("[؀-ۿ]", "ar fa ur"), "Hebrew": ("[֐-׿]", "he"),
    "Devanagari": ("[ऀ-ॿ]", "hi mr ne"), "Bengali": ("[ঀ-৿]", "bn"),
    "Tamil": ("[஀-௿]", "ta"), "Telugu": ("[ఀ-౿]", "te"), "Thai": ("[฀-๿]", "th"),
    "Georgian": ("[Ⴀ-ჿ]", "ka"), "Armenian": ("[԰-֏]", "hy"), "Hangul": ("[가-힯]", "ko"),
}


def test_the_new_packs_are_complete_and_in_their_script():
    import json
    every = set(json.loads((ROOT / "ike/resources/lang/it.json").read_text("utf-8"))["strings"])
    bidi = re.compile("[‎‏‪-‮⁦-⁩]")
    for script, (pattern, codes) in SCRIPTS.items():
        for code in codes.split():
            pack = json.loads((ROOT / ("ike/resources/lang/%s.json" % code)).read_text("utf-8"))
            assert pack["code"] == code and pack["name"], code
            strings = pack["strings"]
            assert set(strings) == every and all(v.strip() for v in strings.values()), code
            assert re.search(pattern, strings["Settings"] + pack["name"]), (code, script)
            assert not any(bidi.search(v) for v in strings.values()), code       # no hidden direction marks


@pytest.mark.parametrize("code,rtl", [("ar", True), ("he", True), ("fa", True), ("ur", True), ("nl", False),
                                      ("ko", False)])
def test_right_to_left_languages_turn_the_interface(run_ike, code, rtl):
    """Arabic, Hebrew, Persian and Urdu: the whole interface from right to left."""
    out = run_ike("""
        def steps(ike, qapp, out):
            yield 600
            from PyQt6.QtCore import Qt
            from ike import i18n
            out["lang"] = i18n.current()
            out["rtl"] = qapp.layoutDirection() == Qt.LayoutDirection.RightToLeft
            out["menus"] = [a.text() for a in ike.windows[0].menuBar().actions()]
    """, settings={"language": code})
    assert out["lang"] == code and out["rtl"] is rtl, out
    assert all(m for m in out["menus"]), out
