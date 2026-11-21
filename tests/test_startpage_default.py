"""Startpage is the default search engine since 1.1.19 (the owner's choice).
A profile on the old default, DuckDuckGo, moves to Startpage once; another
engine the user chose stays, and DuckDuckGo chosen again afterwards stays."""

import json
import sys

from conftest import APP

sys.path.insert(0, str(APP))
from ike import config as ike_config  # noqa: E402


def load(tmp_path, stored):
    p = tmp_path / "settings.json"
    p.write_text(json.dumps(stored))
    return ike_config.Config(p)


def test_a_new_profile_starts_with_startpage(tmp_path):
    assert ike_config.Config(tmp_path / "none.json")["default_engine"] == "Startpage"


def test_the_old_default_moves_once(tmp_path):
    c = load(tmp_path, {"default_engine": "DuckDuckGo"})
    assert c["default_engine"] == "Startpage" and c["engine_1119"] is True
    c["default_engine"] = "DuckDuckGo"                 # chosen again afterwards
    c.save()
    assert ike_config.Config(tmp_path / "settings.json")["default_engine"] == "DuckDuckGo"


def test_another_engine_chosen_stays(tmp_path):
    for name in ("Brave Search", "Qwant", "Google"):
        assert load(tmp_path, {"default_engine": name})["default_engine"] == name
