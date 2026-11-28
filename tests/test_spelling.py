"""Spell checking while typing (ike/spelling.py, Unreleased).

The choice of the dictionaries runs everywhere. The engine's own check needs
real `.bdic` dictionaries: Arch's `hunspell-en_us` and `hunspell-it` (the Arch
Linux job installs them), or a folder named by IKE_TEST_DICTIONARIES. Without
them those tests are skipped, and say so.
"""

import os
import sys
from pathlib import Path

import pytest
from conftest import APP


def _spelling():
    sys.path.insert(0, str(APP))
    try:
        from ike import spelling
        return spelling
    finally:
        sys.path.remove(str(APP))


def test_dictionaries_follow_the_language():
    s = _spelling()
    have = ["de_DE", "en_GB", "en_US", "en_US-large", "it_CH", "it_IT"]
    assert s.choose(have, ["it_IT", "it"]) == ["it_IT"]
    assert s.choose(have, ["it_CH.UTF-8"]) == ["it_CH"]
    assert s.choose(have, ["it-IT"]) == ["it_IT"]
    assert s.choose(have, ["en_AU", "en"]) == ["en_US"]          # the main one of a language
    assert s.choose(have, ["en_GB"]) == ["en_GB"]
    assert s.choose(have, ["fr_FR", "fr"]) == ["en_US"]          # none of the language: English
    assert s.choose(["de_DE"], ["fr_FR"]) == []                  # nothing fitting at all
    assert s.choose(have, ["C", ""]) == ["en_US"]
    assert s.choose(have, ["it_IT", "de_DE", "en_US", "en_GB"]) == ["it_IT", "de_DE", "en_US"]
    assert s.choose(have, ["it_IT"], ["de_DE", "xx_YY"]) == ["de_DE"]   # the user's list
    assert s.choose(have, ["it_IT"], ["xx_YY"]) == ["it_IT"]


def test_installed_dictionaries_are_found(tmp_path, monkeypatch):
    s = _spelling()
    (tmp_path / "it_IT.bdic").write_bytes(b"BDic")
    (tmp_path / "en_US.bdic").write_bytes(b"BDic")
    (tmp_path / "empty.bdic").write_bytes(b"")
    (tmp_path / "it_IT.dic").write_text("x")
    (tmp_path / "folder.bdic").mkdir()
    assert s.installed(tmp_path) == ["en_US", "it_IT"]
    assert s.installed(tmp_path / "missing") == []
    monkeypatch.setenv("QTWEBENGINE_DICTIONARIES_PATH", str(tmp_path))
    assert s.dictionary_dir() == tmp_path
    assert s.languages({"spellcheck": False}) == []
    assert s.languages({"spellcheck": True, "spellcheck_langs": "bad"}) in (["en_US"], ["it_IT"])


def _dictionaries():
    folder = os.environ.get("IKE_TEST_DICTIONARIES")
    folder = Path(folder) if folder else _spelling().dictionary_dir()
    if not (folder / "en_US.bdic").is_file():
        pytest.skip("no en_US.bdic in %s (install hunspell-en_us, or set IKE_TEST_DICTIONARIES)" % folder)
    return folder


STEPS = r'''
from PyQt6.QtCore import QPoint, Qt, QUrl
from PyQt6.QtTest import QTest

def steps(ike, qapp, out):
    yield 300
    win = ike.windows[0]
    v = win.current_view()
    prof = v.page().profile()
    out["on"] = [prof.isSpellCheckEnabled(), list(prof.spellCheckLanguages())]
    done = {}
    v.page().loadFinished.connect(lambda ok: done.setdefault("ok", ok))
    v.load(QUrl.fromLocalFile(PAGE))
    while "ok" not in done:
        yield 20
    yield 300
    target = v.focusProxy() or v
    QTest.mouseClick(target, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(200, 30))
    yield 300
    QTest.keyClicks(target, WORD + " ")
    yield 1500
    val = {}
    v.page().runJavaScript("document.getElementById('t').value", 0, lambda r: val.setdefault("v", r))
    while "v" not in val:
        yield 20
    out["typed"] = val["v"]
    # a right click on the word: the engine's request names it and its corrections
    QTest.mouseClick(target, Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier, QPoint(14, 12))
    yield 800
    req = v.lastContextMenuRequest()
    out["word"] = req.misspelledWord() if req else None
    out["suggestions"] = list(req.spellCheckerSuggestions()) if req else []
    menu = getattr(v, "_ctx_menu", None)
    out["menu"] = [a.text() for a in menu.actions()] if menu is not None else []
    if menu is not None:
        menu.close()
    # switched off in the settings: the profiles stop checking
    ike.config["spellcheck"] = False
    ike.shields.apply_settings()
    out["off"] = prof.isSpellCheckEnabled()
'''

PAGE = (b"<!doctype html><meta charset=utf-8><title>spell</title>"
        b"<textarea id=t style='position:absolute;left:0;top:0;width:400px;height:60px;"
        b"font:16px monospace' spellcheck=true></textarea>")


@pytest.mark.parametrize("lang,word,expect", [("C", "helo", "en_US"), ("it_IT.UTF-8", "ciaoo", "it_IT")])
def test_the_engine_underlines_and_corrects(run_ike, tmp_path, lang, word, expect):
    folder = _dictionaries()
    if not (folder / ("%s.bdic" % expect)).is_file():
        pytest.skip("no %s.bdic in %s" % (expect, folder))
    page = tmp_path / "spell.html"
    page.write_bytes(PAGE)
    head = "PAGE = %r\nWORD = %r\n" % (str(page), word)
    out = run_ike(head + STEPS, env={"QTWEBENGINE_DICTIONARIES_PATH": str(folder), "LANG": lang},
                  timeout=120)
    assert out["on"][0] is True and out["on"][1] == [expect], out["on"]
    assert out["word"] == word, out
    assert out["suggestions"], out
    assert out["suggestions"][0] in out["menu"]
    assert out["off"] is False
