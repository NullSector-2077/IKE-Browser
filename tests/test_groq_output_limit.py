"""A limit of the answer's tokens is not one of the request (Groq, the drill of 2026-11-28).

One Groq model said "on output tokens per minute (OTPM): Limit 1000"; it was learned as Groq's limit of tokens a
minute, kept for the next days, and no request fitted it any more: Groq was never asked again, so nothing could
correct it. Now the output limit is not learned, and what the headers said comes before a learned value."""

import datetime as dt
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NOW = dt.datetime(2026, 11, 28, 12, 0, tzinfo=dt.timezone.utc)
OTPM = ('{"error": {"message": "Request too large for model `qwen/qwen3.8-27b` in organization `org_x` service '
        'tier `on_demand` on output tokens per minute (OTPM): Limit 1000, Requested 4292"}}')
TPM = '{"error": {"message": "Request too large on tokens per minute (TPM): Limit 6000, Requested 7678"}}'


def load():
    spec = importlib.util.spec_from_file_location("groq_quota", ROOT / "tools" / "ai-quota.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_output_limit_is_not_learned_and_the_headers_come_first():
    quota = load()
    assert quota.learned_minute_tokens(OTPM) is None
    assert quota.learned_minute_tokens(TPM) == 6000
    budget = quota.Budget(state=quota.empty_state(), candidate="automation/update/x", now=NOW)
    before = budget.minute_limit("Groq", "tokens")
    budget.note("Groq", 10, status=413, body=OTPM)
    assert budget.minute_limit("Groq", "tokens") == before
    # the days kept: a header reading of 8000 on one day, a learned 1000 on a later one (as stored before the fix)
    state = {"days": {
        "2026-11-27": {"providers": {"Groq": {"observed": {"tokens": {"limit": 8000, "window": "minute"}}}}},
        "2026-11-28": {"providers": {"Groq": {"observed": {"tokens": {"limit": 1000, "window": "minute",
                                                                         "learned": True}}}}}}}
    later = quota.Budget(state=state, candidate="automation/update/x", now=NOW + dt.timedelta(days=1))
    assert later.last_seen("Groq", "tokens", "minute") == 8000
    only_learned = {"days": {"2026-11-28": state["days"]["2026-11-28"]}}
    assert quota.Budget(state=only_learned, candidate="automation/update/x", now=NOW + dt.timedelta(days=1)) \
        .last_seen("Groq", "tokens", "minute") == 1000
