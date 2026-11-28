"""The renamed-symbol recipe keeps both releases working (the drill, 2026-11-28).

A plain rename (recentlyAudible -> isRecentlyAudible) passed the new Qt's tests and broke today's Qt on Arch Linux
and a test that stubs the old name; the AIs then undid it. In Python the recipe now reads the old name when the
object has it and the new one otherwise."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load():
    spec = importlib.util.spec_from_file_location("rcr", ROOT / "tools" / "automat-recipes.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


SOURCE = '''from PyQt6.QtWebEngineCore import QWebEnginePage


def title(view):
    prefix = "💤 "
    if view.page().recentlyAudible():
        prefix = "🔊 "
    return prefix
'''


class Old:
    def recentlyAudible(self):
        return True


class New:
    def isRecentlyAudible(self):
        return True


def test_both_releases_work_after_the_recipe():
    recipes = load()
    out = recipes.compatible_python(SOURCE, "recentlyAudible", "isRecentlyAudible")
    assert 'hasattr(view.page(), "recentlyAudible")' in out and "💤" in out
    for page in (Old(), New()):
        space = {}
        exec(compile(out.replace("from PyQt6.QtWebEngineCore import QWebEnginePage\n", ""), "x", "exec"), space)
        view = type("V", (), {"page": lambda self, p=page: p})()
        assert space["title"](view) == "🔊 "
    # an imported or bare name is renamed; a text that does not parse or does not use it: None
    assert recipes.compatible_python("from j import serialise\nx = serialise(1)\n", "serialise", "serialize") == \
        "from j import serialize\nx = serialize(1)\n"
    assert recipes.compatible_python("def (:\n", "a", "b") is None
    assert recipes.compatible_python("x = 1\n", "a", "b") is None
