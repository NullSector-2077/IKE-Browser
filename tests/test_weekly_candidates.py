"""AUTOMAT made simpler (2026-11-27): the low-risk candidates are made once a week (tools/update-candidates.py
WEEKLY, on Mondays); what ships to users and changes their protection stays daily."""

import datetime as dt
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MONDAY, FRIDAY = dt.date(2026, 11, 30), dt.date(2026, 11, 27)


def uc():
    spec = importlib.util.spec_from_file_location("weekly_uc", ROOT / "tools" / "update-candidates.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def report(*ids):
    return {"candidates": [{"id": i, "component": i, "from": "1", "to": "2"} for i in ids]}


def test_low_risk_candidates_wait_for_monday_and_the_rest_stays_daily():
    u = uc()
    ids = ("crates", "test-tools", "test-libs", "ci-cargo-deny", "adblock", "darkreader", "ubo-scriptlets",
           "test-qt", "pyo3")
    friday = {r["id"]: r["action"] for r in u.plan(report(*ids), {}, today=FRIDAY)}
    assert {i for i, a in friday.items() if a == "weekly"} == {"crates", "test-tools", "test-libs", "ci-cargo-deny"}
    assert all(friday[i] in ("make", "queued") for i in ("adblock", "ubo-scriptlets", "test-qt", "pyo3"))
    monday = {r["id"]: r["action"] for r in u.plan(report(*ids), {}, today=MONDAY)}
    assert "weekly" not in monday.values()
    assert not [m for m in u.matrix(u.plan(report("crates"), {}, today=FRIDAY))]


def test_an_open_weekly_candidate_is_left_as_it_is_and_said():
    u = uc()
    rows = u.plan(report("crates"), {"automation/update/crates": {"pr": 185}}, today=FRIDAY)
    assert rows[0]["action"] == "weekly" and "PR #185" in rows[0]["reason"]


def test_security_branches_are_never_weekly():
    u = uc()
    assert not u.weekly("security-rustsec-2026-0001") and u.weekly("ci-node") and not u.weekly("crate-major-x")
