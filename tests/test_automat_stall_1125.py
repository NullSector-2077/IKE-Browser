"""AUTOMAT's stall of 2026-11-25 afternoon (run 45625320020), proved gone (offline: fake providers, no network).

Z.AI stayed "spent today" from a mark written before the reading of its codes was fixed, and every OpenRouter
free model failed: 429s waited out model after model as if the whole account were blocked, and reasoning models
gave no text. Proved here: a "spent today" mark is checked again after SPENT_RECHECK (a mark with no time at once,
money never); a 429 of one free model's upstream pool holds back no other model of the provider; the provider's
own words reach the log without URLs or keys; OpenRouter is asked for little reasoning; an answer cut off by its
reasoning says so.
"""

import datetime as dt
import importlib.util
import io
import json
import urllib.error
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
NOW = dt.datetime(2026, 11, 25, 14, 0, tzinfo=dt.timezone.utc)
CANDIDATE = "automation/update/lists-2026-11-22"
OPENROUTER = "https://openrouter.ai/api/v1/chat/completions"
UPSTREAM = json.dumps({"error": {"code": 429, "message": "google/gemma-4-31b-it:free is temporarily rate-limited "
                                 "upstream. Please retry shortly: https://openrouter.ai/settings/integrations",
                                 "metadata": {"limit_source": "upstream_provider_shared_pool"}}})


def load(name):
    spec = importlib.util.spec_from_file_location("stall_" + name.replace("-", "_"), ROOT / "tools" / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def quota():
    return load("ai-quota")


@pytest.fixture(scope="module")
def reserve():
    return load("autofix-reserve")


def test_a_mark_without_time_holds_for_the_day_as_before(quota):
    state = quota.empty_state()
    quota._prov(state, "2026-11-25", "Z.AI")["spent"] = "429: the quota of the day (it says so)"
    later = NOW + dt.timedelta(hours=6)
    assert quota.Budget(state=state, candidate=CANDIDATE, now=later).spent("Z.AI")


def test_a_fresh_mark_holds_and_expires_after_the_recheck_time(quota):
    state = quota.empty_state()
    budget = quota.Budget(state=state, candidate=CANDIDATE, now=NOW)
    budget.note("Z.AI", 100, status=429, body='{"error": {"code": "1310", "message": "usage limit"}}')
    assert budget.spent("Z.AI")
    later = NOW + dt.timedelta(seconds=quota.SPENT_RECHECK - 60)
    assert quota.Budget(state=state, candidate=CANDIDATE, now=later).spent("Z.AI")
    after = NOW + dt.timedelta(seconds=quota.SPENT_RECHECK + 60)
    assert quota.Budget(state=state, candidate=CANDIDATE, now=after).spent("Z.AI") == ""


def test_the_time_of_a_mark_survives_the_data_branch(quota):
    budget = quota.Budget(state=quota.empty_state(), candidate=CANDIDATE, now=NOW)
    budget.mark_spent("Z.AI", "429: the quota of the day (it says so)")
    state = quota.merge(quota.empty_state(), budget.delta(), now=NOW)
    row = state["days"]["2026-11-25"]["providers"]["Z.AI"]
    assert row["spent"] and row["spent_at"] == int(NOW.timestamp())
    assert quota.Budget(state=state, candidate=CANDIDATE, now=NOW + dt.timedelta(minutes=5)).spent("Z.AI")


def test_money_asked_never_expires(quota):
    budget = quota.Budget(state=quota.empty_state(), candidate=CANDIDATE, now=NOW)
    budget._p("Groq")["spent"] = "it asked for money (not free)"
    budget.started -= quota.SPENT_RECHECK * 3          # hours later, in the same day of the provider
    assert budget.spent("Groq")


def test_one_busy_free_model_does_not_hold_back_the_others(quota):
    budget = quota.Budget(state=quota.empty_state(), candidate=CANDIDATE, now=NOW)
    budget.note("OpenRouter", 100, status=429, body=UPSTREAM)
    assert "OpenRouter" not in budget.blocked_until and budget.spent("OpenRouter") == ""
    minute = json.dumps({"error": {"code": 429, "message": "Rate limit exceeded: free-models-per-min"}})
    budget.note("OpenRouter", 100, status=429, body=minute)
    assert budget.blocked_until.get("OpenRouter")


def fail(code, body):
    def opener(req, timeout=0):
        opener.sent = json.loads(req.data)
        raise urllib.error.HTTPError(req.full_url, code, "x", {}, io.BytesIO(body.encode()))
    return opener


def test_a_busy_model_hands_over_at_once_with_its_words(reserve):
    opener = fail(429, UPSTREAM)
    with pytest.raises(reserve.Stop) as stop:
        reserve.ask(OPENROUTER, "sk-or-secret", "google/gemma-4-31b-it:free", [], opener=opener)
    kind, detail, wait, code, scope = stop.value.args
    assert (kind, wait, code, scope) == ("quota", 0, 429, "model")
    assert "rate-limited upstream" in detail and "http" not in detail and "secret" not in detail
    assert opener.sent["reasoning"] == {"effort": "minimal", "exclude": True}


def test_other_providers_get_no_reasoning_field_and_their_words(reserve):
    opener = fail(429, json.dumps({"error": {"code": "1302", "message": "Rate limit reached for requests"}}))
    with pytest.raises(reserve.Stop) as stop:
        reserve.ask("https://api.z.ai/api/paas/v4/chat/completions", "k", "glm-4.7-flash", [], opener=opener)
    assert "reasoning" not in opener.sent
    assert len(stop.value.args) == 4 and "Rate limit reached" in stop.value.args[1]


class Answer:
    headers = {}

    def __init__(self, data):
        self.data = data

    def read(self, _limit):
        return json.dumps(self.data).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def test_an_answer_cut_off_by_its_reasoning_says_so(reserve):
    cut = {"choices": [{"message": {"content": ""}, "finish_reason": "length"}]}
    with pytest.raises(reserve.Stop) as stop:
        reserve.ask(OPENROUTER, "k", "m:free", [], opener=lambda req, timeout=0: Answer(cut))
    assert stop.value.args[0] == "cutoff"
    whole = {"choices": [{"message": {"content": '{"edits": []}'}, "finish_reason": "stop"}]}
    assert reserve.ask(OPENROUTER, "k", "m:free", [], opener=lambda req, timeout=0: Answer(whole)) == '{"edits": []}'


GEMINI_429 = json.dumps({"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "details": [
    {"@type": "type.googleapis.com/google.rpc.QuotaFailure", "violations": [
        {"quotaMetric": "generativelanguage.googleapis.com/generate_content_free_tier_requests",
         "quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier",
         "quotaDimensions": {"location": "global", "model": "gemini-4-hydrogen"}, "quotaValue": "250"}]},
    {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "35s"}]}})


def test_gemini_real_quota_is_learned_from_its_429(quota):
    assert quota.learned_quotas(GEMINI_429) == {"day_requests": 250}
    budget = quota.Budget(state=quota.empty_state(), candidate=CANDIDATE, now=NOW)
    budget.note("Antigravity", 10, status=429, body=GEMINI_429)
    assert budget.day_limit("Antigravity", "requests") == 250
    state = quota.merge(quota.empty_state(), budget.delta(), now=NOW)
    again = quota.Budget(state=state, candidate=CANDIDATE, now=NOW)
    assert again.day_limit("Antigravity", "requests") == 250


def test_nothing_is_learned_from_words_without_a_value(quota):
    assert quota.learned_quotas('{"error": {"message": "quota exceeded PerDay"}}') == {}
    assert quota.learned_quotas('quotaId: "GenerateRequestsPerDay-FreeTier", quotaValue: "0"') == {}


def test_a_learned_limit_is_kept_for_the_next_days(quota):
    """2026-11-27, the owner: what AUTOMAT learns of a provider's real quota replaces the data file's estimate
    for the next days too (the latest day that said it), until the provider says otherwise."""
    budget = quota.Budget(state=quota.empty_state(), candidate=CANDIDATE, now=NOW)
    budget.note("Antigravity", 10, status=429, body=GEMINI_429)
    state = quota.merge(quota.empty_state(), budget.delta(), now=NOW)
    later = quota.Budget(state=state, candidate=CANDIDATE, now=NOW + dt.timedelta(days=2))
    assert later.day_limit("Antigravity", "requests") == 250
    assert quota.Budget(state=quota.empty_state(), candidate=CANDIDATE, now=NOW).day_limit(
        "Antigravity", "requests") == quota.load_limits()["providers"]["Antigravity"]["requests_per_day"]
