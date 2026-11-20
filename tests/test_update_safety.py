"""The signed update channel against a kept-back, stopped or too-fast release
(1.1.18, security audit F5).

Every manifest made by tools/make-release.py now carries when it was issued,
when it expires (180 days later) and a staged release: each installation has
a fixed place (0-99) and its turn comes within 24 hours (0: all at once). An
expired manifest installs nothing and says so; a manifest re-signed with
"halt" stops a release; a check the user asks for does not wait for its turn.
Manifests of earlier releases (none of these fields) work as before, and a
wrong clock never blocks updates for good.
"""

import json
import sys
import time

from conftest import APP
from test_updater import CHECK, PASS, keypair, load_tool, make_update_json, releases, update_env  # noqa: F401

sys.path.insert(0, str(APP))
from ike import updater  # noqa: E402

NOW = 2_000_000_000


def m(**kw):
    out = {"version": "99.0.0"}
    out.update(kw)
    return out


def test_what_stops_an_install():
    p = updater.manifest_problem
    assert p(m(), NOW) is None                                            # an earlier release's manifest
    assert p(m(halt=True), NOW) == "halted"
    assert p(m(expires=NOW - 1), NOW) == "expired"
    assert p(m(expires="never"), NOW) == "expired"
    assert p(m(expires=NOW + 10), NOW) is None
    staged = m(rollout={"start": NOW, "hours": 24})
    assert p(staged, NOW + 3600, place=50) == "waiting"                    # 4 % of the way: not yet
    assert p(staged, NOW + 13 * 3600, place=50) is None                   # 54 %: its turn
    assert p(staged, NOW + 3600, place=3) is None                         # an early place
    assert p(staged, NOW + 3600, place=99, manual=True) is None           # the user asked
    assert p(staged, NOW + 25 * 3600, place=99) is None                   # after the window: everyone
    assert p(staged, NOW - 3 * 86400, place=99) is None                   # a clock days behind: never stuck
    assert p(m(rollout={"start": NOW, "hours": 0}), NOW, place=99) is None
    assert p(m(rollout={"start": "x", "hours": 24}), NOW, place=99) is None
    assert p(m(halt=True), NOW, manual=True) == "halted"                  # a stop is a stop


def test_release_tool_writes_the_new_fields(keypair, tmp_path):  # noqa: F811
    tool = load_tool()
    _, key_path, pub = keypair
    upd = make_update_json(tmp_path, pub)
    _, man = tool.make(key_path, tmp_path / "r1", ["stable"], passphrase=PASS, update_file=upd, now=NOW)
    assert man["issued"] == NOW and man["expires"] == NOW + 180 * 86400
    assert man["rollout"] == {"start": NOW, "hours": 24} and "halt" not in man
    _, man = tool.make(key_path, tmp_path / "r2", ["stable"], passphrase=PASS, update_file=upd, now=NOW,
                       rollout_hours=0, halt=True)
    assert man["rollout"]["hours"] == 0 and man["halt"] is True
    raw = (tmp_path / "r2" / "stable.json").read_bytes()
    assert json.loads(raw) == man and updater.verify_signature(
        pub, raw, (tmp_path / "r2" / "stable.json.sig").read_text().strip())


MANUAL = CHECK.replace("ike.updater.run(install=True)", "ike.updater.run(install=True, manual=True)")
PLACE = """
    def steps(ike, qapp, out):
        from ike import updater
        st = updater.load_state(); st["bucket"] = 99; updater.save_state(st)
        yield 10
"""


def test_expired_halted_and_waiting_releases_install_nothing(run_ike, releases, keypair, tmp_path):  # noqa: F811
    key, _, pub = keypair
    env = update_env(tmp_path, releases, pub)
    now = int(time.time())
    releases.publish(key, "99.0.0", min_system="0", extra={"expires": now - 60})
    out = run_ike(CHECK, env=env, timeout=240)
    assert out["kind"] == "error" and "out of date" in out["data"] and out["versions"] == [], out
    releases.publish(key, "99.0.0", min_system="0", extra={"halt": True})
    out = run_ike(CHECK, env=env, keep_profile=True, timeout=240)
    assert out["kind"] == "current" and out["versions"] == [], out
    run_ike(PLACE, env=env, keep_profile=True, timeout=60)               # this installation: place 99
    releases.publish(key, "99.0.0", min_system="0",
                     extra={"expires": now + 86400, "rollout": {"start": now, "hours": 1000}})
    out = run_ike(CHECK, env=env, keep_profile=True, timeout=240)
    assert out["kind"] == "current" and out["versions"] == [], out       # not its turn yet
    out = run_ike(MANUAL, env=env, keep_profile=True, timeout=240)
    assert out["kind"] == "installed" and out["versions"] == ["99.0.0"], out   # the user asked: now
