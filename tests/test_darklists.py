import json

import pytest

from ike import darkfixes, darklists

OLD = "a" * 40
NEW = "b" * 40
DATE = "2026-11-26T10:00:00Z"
BUNDLE = {
    "version": "4.9.135", "lists_commit": OLD, "lists_date": "2026-11-25",
    "fixes": [{"url": ["*"], "css": "body { color: white; }"}],
    "dark_sites": ["old.example"], "detector_hints": [{"url": ["old.example"]}],
}
FIXES = """*
CSS
body { background-image: url(https://other.example/external.png); }

================================

fresh.example
INVERT
.safe
}body{background:black
CSS
.notice { color: white; }
"""
HINTS = "fresh.example\nTARGET\nhtml\nMATCH\n.dark"


def responses(commit=NEW, date=DATE, fixes=FIXES):
    source = {darklists.HEAD: json.dumps(
        {"sha": commit, "commit": {"committer": {"date": date}}})}
    for name, contents in zip(darklists.FILES, (fixes, "fresh.example\n/(a+)+$/", HINTS)):
        source[f"{darklists.RAW}{commit}/src/config/{name}"] = contents
    return source


def test_refresh_pins_all_files_and_retains_safe_bundle_fallback(tmp_path):
    cache = tmp_path / "lists.json"
    source = responses()
    requested = []

    def read(url):
        requested.append(url)
        return source[url]

    assert darklists.refresh(BUNDLE, cache, read)
    assert requested == list(source)
    data = darklists.load(BUNDLE, cache)
    assert data["lists_commit"] == NEW and data["version"] == BUNDLE["version"]
    assert data["fixes"][0]["css"] == BUNDLE["fixes"][0]["css"]
    assert data["fixes"][1] == {"url": ["fresh.example"], "invert": [".safe"],
                               "css": ".notice { color: white; }"}
    assert data["dark_sites"] == ["fresh.example"]
    assert data["detector_hints"] == [{"url": ["fresh.example"], "target": "html", "match": [".dark"]}]
    requested.clear()
    assert not darklists.refresh(BUNDLE, cache, read)
    assert requested == [darklists.HEAD]


def test_failed_and_stale_refresh_leave_the_last_good_snapshot(tmp_path):
    cache = tmp_path / "lists.json"
    assert darklists.refresh(BUNDLE, cache, responses().__getitem__)
    previous = cache.read_bytes()
    old = responses("c" * 40, "2026-11-25T12:00:00Z")
    assert not darklists.refresh(BUNDLE, cache, old.__getitem__)
    invalid = responses("d" * 40, "2026-11-27T10:00:00Z", "truncated data")
    with pytest.raises(ValueError, match="incomplete"):
        darklists.refresh(BUNDLE, cache, invalid.__getitem__)
    assert cache.read_bytes() == previous
    cache.write_text("invalid JSON")
    assert darklists.load(BUNDLE, cache) == BUNDLE


def test_refresh_interval_is_saved_across_calls(tmp_path, monkeypatch):
    monkeypatch.setattr(darklists, "CACHE", tmp_path / "lists.json")
    assert darklists.due()
    assert not darklists.due()


def test_active_engines_keep_one_list_snapshot(tmp_path, monkeypatch):
    cache = tmp_path / "lists.json"
    load = darklists.load
    monkeypatch.setattr(darklists, "load", lambda bundled: load(bundled, cache))
    monkeypatch.setattr(darkfixes, "bundled_data", lambda: BUNDLE)
    monkeypatch.setattr(darkfixes, "_data", None)
    monkeypatch.setattr(darkfixes, "_index", None)
    assert darkfixes.in_dark_list("https://old.example")
    assert darklists.refresh(BUNDLE, cache, responses().__getitem__)
    assert not darkfixes.in_dark_list("https://fresh.example")
    monkeypatch.setattr(darkfixes, "_data", None)
    monkeypatch.setattr(darkfixes, "_index", None)
    assert darkfixes.in_dark_list("https://fresh.example")
    assert ".safe" in darkfixes.fix_for("https://fresh.example")["invert"]
