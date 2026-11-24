"""Credits (1.1.14, 1.1.18): docs/THIRD-PARTY.md follows the AdBlock engine,
and a filter list I.K.E. may not use is gone for good.

The Rust libraries listed there are exactly the ones of ike-adblock/Cargo.lock,
and the adblock-rust version in the components table is the one in use. The
daily maintenance rewrites the file with tools/third-party.py whenever it moves
the engine to a new version; this test catches a list left behind. The full
check against the crates' sources is tools/third-party.py --check (GitHub
Actions, step "Licences"); tests/test_licences.py has the rest.
"""

import importlib.util
import json
import re
import sys
from pathlib import Path

from conftest import APP

ROOT = Path(__file__).resolve().parent.parent


def _tool():
    spec = importlib.util.spec_from_file_location("third_party", ROOT / "tools" / "third-party.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_rust_libraries_match_cargo_lock():
    tool = _tool()
    locked = tool.locked_packages((ROOT / "ike-adblock" / "Cargo.lock").read_text("utf-8"))
    doc = (ROOT / "docs" / "THIRD-PARTY.md").read_text("utf-8")
    listed = re.findall(r"^(\S+) v(\S+) — ", doc, re.M)
    assert sorted(listed) == sorted(locked)
    adblock = dict(locked)["adblock"]
    assert "adblock-rust %s (filter engine, by Brave)" % adblock in doc
    shipped = doc.split(tool.DOC_SHIPPED, 1)[1].split(tool.DOC_BUILD, 1)[0]
    assert "adblock v%s — MPL-2.0" % adblock in shipped and "pyo3 v" in shipped
    # procedural macros and build scripts are not in the engine
    assert "serde_derive v" not in shipped and "pyo3-build-config v" not in shipped


def test_render_follows_a_new_engine():
    tool = _tool()
    doc = (ROOT / "docs" / "THIRD-PARTY.md").read_text("utf-8")
    new = tool.render_doc(doc, "9.9.9", [("adblock", "9.9.9", "MPL-2.0", "https://x.test/adblock"),
                                         ("zz-lib", "1.0.0", "MIT", "")],
                          [("zz-macro", "2.0.0", "MIT OR Apache-2.0", "https://x.test/m")])
    assert "adblock-rust 9.9.9 (filter engine, by Brave)" in new
    assert "adblock v9.9.9 — MPL-2.0 — https://x.test/adblock\nzz-lib v1.0.0 — MIT — no repository stated\n```" \
        in new
    assert "zz-macro v2.0.0 — MIT OR Apache-2.0 — https://x.test/m\n```" in new
    assert new.count(tool.DOC_SHIPPED) == 1 and new.count(tool.DOC_BUILD) == 1
    adblock = dict(tool.locked_packages((ROOT / "ike-adblock" / "Cargo.lock").read_text("utf-8")))["adblock"]
    before = new.split(tool.DOC_SHIPPED)[0].replace("adblock-rust 9.9.9 (", "adblock-rust %s (" % adblock)
    assert before == doc.split(tool.DOC_SHIPPED)[0]                      # the rest is left alone


# --- 1.1.18: a filter list whose terms do not allow I.K.E. to use it ----------

WITHDRAWN = "https://pgl.yoyo.org/adservers/serverlist.php?hostformat=adblockplus&showintro=0&mimetype=plaintext"
LISTS = r"""
def steps(ike, qapp, out):
    out["urls"] = [e["url"] for e in ike.config["filter_lists"]]
    out["version"] = ike.config["lists_version"]
    yield 0
"""


def test_withdrawn_list_is_never_offered(run_ike):
    sys.path.insert(0, str(APP))
    try:
        from ike import config
    finally:
        sys.path.remove(str(APP))
    hosts = [e["url"].split("/")[2] for e in config.DEFAULT_LISTS]
    assert not [h for h in hosts if config._withdrawn_list("https://%s/" % h)]
    out = run_ike(LISTS)
    assert out["version"] == 5
    assert not [u for u in out["urls"] if "yoyo" in u]
    assert "https://easylist.to/easylist/easylist.txt" in out["urls"]


def _fresh_config(monkeypatch, tmp_path):
    import importlib
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.delenv("IKE_PROFILE", raising=False)
    from ike import config as C
    return importlib.reload(C)


def test_withdrawn_list_dropped_from_old_settings(monkeypatch, tmp_path):
    """Settings of 1.1.17 or earlier lose the list once, whether it was on or
    off, also under another address of the same server; its downloaded copy is
    deleted, the other lists stay as they were, nothing is fetched again."""
    sys.path.insert(0, str(APP))
    try:
        C = _fresh_config(monkeypatch, tmp_path)
        others = [dict(e) for e in C.DEFAULT_LISTS]
        mine = [{"name": "My list", "group": "ads", "enabled": False, "url": "https://lists.example/mine.txt"}]
        stored = {
            "lists_version": 4, "last_lists_update": 123, "pgl_off_1116": True,
            "filter_lists": others[:3] + [
                {"name": "Peter Lowe's list", "group": "ads", "enabled": False, "url": WITHDRAWN},
                {"name": "copy", "group": "ads", "enabled": True,
                 "url": "http://PGL.yoyo.org./as/serverlist.php?hostformat=adblock"},
                {"name": "broken", "url": "http://[bad"},
                {"name": "no address"},
            ] + others[3:] + mine,
        }
        path = Path(C.CONFIG_DIR) / "settings.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(stored), "utf-8")
        copy = C._list_copy(WITHDRAWN)
        copy.parent.mkdir(parents=True, exist_ok=True)
        copy.write_text("||ads.example^\n", "utf-8")
        cfg = C.Config()
        urls = [e.get("url") for e in cfg["filter_lists"]]
        assert not [u for u in urls if u and "yoyo" in u.lower()]
        assert urls == [e["url"] for e in others[:3]] + ["http://[bad", None] + \
            [e["url"] for e in others[3:]] + ["https://lists.example/mine.txt"]
        assert cfg["lists_version"] == 5 and cfg["last_lists_update"] == 123
        assert "pgl_off_1116" not in cfg.data
        assert not copy.exists()
        cfg.save()
        saved = json.loads(path.read_text("utf-8"))
        assert "pgl_off_1116" not in saved and saved["lists_version"] == 5
        assert "yoyo" not in json.dumps(saved["filter_lists"]).lower()
        again = C.Config()                                   # once only: nothing changes now
        assert [e.get("url") for e in again["filter_lists"]] == urls
    finally:
        sys.path.remove(str(APP))


def test_withdrawn_list_on_for_a_user_is_dropped_too(monkeypatch, tmp_path):
    sys.path.insert(0, str(APP))
    try:
        C = _fresh_config(monkeypatch, tmp_path)
        path = Path(C.CONFIG_DIR) / "settings.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"lists_version": 2, "filter_lists": [
            {"name": "Peter Lowe's list", "group": "ads", "enabled": True, "url": WITHDRAWN}]}), "utf-8")
        cfg = C.Config()
        assert not [e for e in cfg["filter_lists"] if "yoyo" in e["url"]]
        assert cfg["lists_version"] == 5
        # the older steps still ran (the lists of video-ad rules and of malware)
        assert any("quick-fixes" in e["url"] for e in cfg["filter_lists"])
    finally:
        sys.path.remove(str(APP))
