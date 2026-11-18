"""Credits (1.1.14): docs/THIRD-PARTY.md follows the AdBlock engine.

The Rust libraries listed there are exactly the ones of ike-adblock/Cargo.lock,
and the adblock-rust version in the components table is the one in use. The
daily maintenance rewrites the file with tools/third-party.py whenever it moves
the engine to a new version; this test catches a list left behind.
"""

import importlib.util
import re
from pathlib import Path

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


def test_render_follows_a_new_engine():
    tool = _tool()
    doc = (ROOT / "docs" / "THIRD-PARTY.md").read_text("utf-8")
    new = tool.render(doc, [("adblock", "9.9.9"), ("zz-lib", "1.0.0")],
                      {("adblock", "9.9.9"): "MPL-2.0"})
    assert "adblock-rust 9.9.9 (filter engine, by Brave)" in new
    assert "adblock v9.9.9 — MPL-2.0\nzz-lib v1.0.0 — see the crate\n```" in new
    assert new.count("## Rust libraries linked into `ike_adblock`") == 1


# --- 1.1.16: Peter Lowe's list off by default until its terms are confirmed -----

PGL = "https://pgl.yoyo.org/adservers/serverlist.php?hostformat=adblockplus&showintro=0&mimetype=plaintext"
LISTS = r"""
def steps(ike, qapp, out):
    out["lists"] = {e["name"]: e["enabled"] for e in ike.config["filter_lists"]}
    out["flag"] = ike.config["pgl_off_1116"]
    yield 0
"""


def test_peter_lowe_off_for_new_profiles(run_ike):
    out = run_ike(LISTS)
    assert out["lists"]["Peter Lowe's list"] is False
    assert out["lists"]["EasyList"] is True and out["flag"] is True


def test_peter_lowe_turned_off_once_then_the_users_choice(run_ike):
    on = [{"name": "Peter Lowe's list", "group": "ads", "enabled": True, "url": PGL}]
    # an existing profile that had it on: turned off once
    out = run_ike(LISTS, settings={"filter_lists": on})
    assert out["lists"]["Peter Lowe's list"] is False
    # a user who turned it on again after 1.1.16 keeps it on
    out = run_ike(LISTS, settings={"filter_lists": on, "pgl_off_1116": True})
    assert out["lists"]["Peter Lowe's list"] is True
