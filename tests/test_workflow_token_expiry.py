"""AUTOMAT block 2: the weekly check says when the owner's IKE_WORKFLOW_TOKEN is about to expire, or is refused.

The workflow's step reads only GitHub's answer to the token (its HTTP code and the header
GitHub-Authentication-Token-Expiration) and writes those two, never the token (.github/workflows/health.yml).
"""

import datetime as dt
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NOW = dt.datetime(2026, 11, 25, 7, 41, tzinfo=dt.timezone.utc)


def health():
    spec = importlib.util.spec_from_file_location("health_token", ROOT / "tools" / "automation-health.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_header_is_read_in_both_forms():
    h = health()
    want = dt.datetime(2026, 12, 31, 23, 59, 59, tzinfo=dt.timezone.utc)
    assert h.token_expiry("2026-12-31 23:59:59 UTC") == want
    assert h.token_expiry("2026-12-31 23:59:59 +0000") == want
    assert h.token_expiry("") is None and h.token_expiry("never") is None


def test_a_token_that_expires_soon_is_said_and_a_far_one_is_not():
    h = health()
    soon = h.token_problem({"status": "200", "expires": "2026-12-05 10:00:00 UTC"}, NOW)
    assert "IKE_WORKFLOW_TOKEN" in soon and "2026-12-05" in soon
    assert h.token_problem({"status": "200", "expires": "2027-03-01 10:00:00 UTC"}, NOW) == ""
    assert h.token_problem({"status": "200", "expires": ""}, NOW) == ""       # a token with no expiry


def test_a_refused_token_is_said_and_an_unset_one_is_not():
    h = health()
    assert "refuses" in h.token_problem({"status": "401", "expires": ""}, NOW)
    assert h.token_problem({"unset": True}, NOW) == "" and h.token_problem(None, NOW) == ""


def test_problems_carries_the_line():
    h = health()
    found = h.problems(NOW, {}, [], True, token={"status": "200", "expires": "2026-11-30 00:00:00 UTC"})
    assert any("IKE_WORKFLOW_TOKEN" in line for line in found)


def test_the_workflow_never_writes_the_token():
    text = (ROOT / ".github" / "workflows" / "health.yml").read_text("utf-8")
    step = text.split("- name: When the owner's workflow token expires", 1)[1].split("- name:", 1)[0]
    assert "secrets.IKE_WORKFLOW_TOKEN" in step
    assert "echo \"$WORKFLOW_TOKEN" not in step and "WORKFLOW_TOKEN\" >" not in step
    assert 'rm -f "$headers"' in step and "TOKEN_CHECK" in text
