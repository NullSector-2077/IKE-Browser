"""AUTOMAT's deadlock of 2026-11-25, reproduced and proved gone (offline: fake providers, no key, no network).

PR #111 (automation/update/lists-2026-11-22, an AI change refused by the static guard) is "retrying", so AUTOMAT
should try it again every day. For three days no attempt landed: the daily "Automatic fix" run 45559025046 asked
nobody, because every provider was skipped for a reason of its own:

- Antigravity: "rotated (this attempt starts with Z.AI)";
- Z.AI: "spent today (429: the quota of the day (it says so))", from a 429 of concurrency (Z.AI's code 1302 was
  one of its "day words");
- OpenRouter: "the reviewers' reserve: after a fix by OpenRouter only 0 other provider(s) would have room for a
  review today (none), and 2 are needed: the fix waits";
- Groq: "the request is larger than its limit per minute (7678 tokens, 6000 a minute)", which can never change.

What is proved here (the owner's rule: nothing stays behind, no human step but the signature):

1. a request larger than a provider's limit per minute is fitted to it and asked; only when even the smallest
   request cannot fit is the provider skipped, with that reason;
2. a 429 of a minute or of concurrency is waited out in the run, never the day's quota; the limit a provider tells
   is learned; a 503 is asked again with a growing pause;
3. when the reviewers' reserve alone would leave every provider unasked, the fix is written now and waits for its
   reviews on a later day (never merged without them); never for background work, never when too few providers
   could ever review it;
4. the rotation never skips Antigravity while it is the only one with room;
5. the watchdog: a branch that asked nobody for two days in a row is said in the notices;
6. the drill: today's four reasons exactly, and someone is asked.
"""

import datetime as dt
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest
import test_automat_part2 as p2


@pytest.fixture(autouse=True)
def _the_agent_cli_on(monkeypatch):
    """These tests prove the Antigravity CLI's own path; since 2026-11-28 it runs only with AUTOFIX_AGENT_CLI=on
    (tests/test_gemini_api_first.py proves the default)."""
    monkeypatch.setenv("AUTOFIX_AGENT_CLI", "on")

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"
NOW = dt.datetime(2026, 11, 25, 6, 14, tzinfo=dt.timezone.utc)
CANDIDATE = "automation/update/lists-2026-11-22"


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_") + "_deadlock", ROOT / "tools" / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


quota = load("ai-quota")
notice = load("release-notice")
LIMITS = quota.load_limits()

# Z.AI's own answers (docs.z.ai's codes, as remembered: tools/ai-quota.json words_source)
ZAI_CONCURRENCY = '{"error": {"code": "1302", "message": "High concurrency usage of this API, please reduce concurrency"}}'
ZAI_OVERLOADED = '{"error": {"code": "1305", "message": "The service may be temporarily overloaded, try again later"}}'
ZAI_DAY = ('{"error": {"code": "1308", "message": "Usage limit reached for 5 hour. Your limit will reset at '
           '2026-11-25 18:00:00"}}')
GROQ_TPM = ('{"error": {"message": "Request too large for model `qwen/qwen3.8-27b` in organization `org` service tier '
            '`on_demand` on tokens per minute (TPM): Limit 6000, Requested 7678, please reduce your message size"}}')


def state_of(**providers):
    """quota.json with each provider's row on its own day (today, for the real clock the tools use)."""
    state = quota.empty_state()
    for name, row in providers.items():
        quota._prov(state, quota.provider_day(LIMITS["providers"][name]), name).update(row)
    return state


# =====================================================================================================
# 2. A 429 of a minute is not the day's quota; a limit the provider tells is learned
# =====================================================================================================

@pytest.mark.parametrize("provider, body, headers, scope", [
    ("Z.AI", ZAI_CONCURRENCY, {}, "minute"),              # the very answer that spent Z.AI for days
    ("Z.AI", ZAI_OVERLOADED, {}, "minute"),
    ("Z.AI", ZAI_DAY, {}, "day"),
    ("Z.AI", '{"error": {"code": "1310", "message": "Weekly/Monthly Limit Exhausted"}}', {}, "day"),
    ("Z.AI", '{"usage": 13025, "id": "1302"}', {}, "minute"),        # a number elsewhere is no code
    ("Groq", GROQ_TPM, {"retry-after": "7"}, "minute"),
    ("Groq", '{"error": {"message": "Rate limit reached on requests per day (RPD): Limit 1000"}}', {}, "day"),
    ("Groq", "", {"x-ratelimit-limit-requests": "1000", "x-ratelimit-remaining-requests": "0"}, "day"),
    ("Groq", "", {"x-ratelimit-limit-tokens": "6000", "x-ratelimit-remaining-tokens": "0",
                  "x-ratelimit-reset-tokens": "7.66s"}, "minute"),
    ("OpenRouter", "Rate limit exceeded: free-models-per-day", {}, "day"),
    ("OpenRouter", "Rate limit exceeded: free-models-per-min", {}, "minute"),
    ("OpenRouter", "slow down", {"Retry-After": "7200"}, "day"),
    ("OpenRouter", '{"error": {"code": 429, "metadata": {"limit_source": "openrouter_free_tier_per_minute"}}}', {}, "minute"),
    ("OpenRouter", '{"error": {"code": 429, "metadata": {"limit_source": "upstream_provider_shared_pool"}}}', {}, "minute"),
    ("OpenRouter", '{"error": {"code": 429, "metadata": {"limit_source": "openrouter_free_tier_daily"}}}', {}, "day"),
    ("Antigravity", "Quota exceeded ... limit: 0, model: gemini-x", {}, "day"),
    ("Antigravity", "Please retry in 20s", {"retry-after": "400"}, "day"),          # over 300 s: Google's own rule
    ("Antigravity", "Quota exceeded for quota metric GenerateRequestsPerMinutePerProjectPerModel", {}, "minute"),
    ("Antigravity", "Quota exceeded: GenerateRequestsPerDayPerProjectPerModel-FreeTier", {}, "day"),
    ("Groq", "Too Many Requests", {}, "minute"),                     # nothing says which: a minute
])
def test_a_429_of_a_minute_or_of_concurrency_is_never_the_days_quota(provider, body, headers, scope):
    got, wait, why = quota.rate_limit_scope(LIMITS["providers"][provider], headers, body)
    assert got == scope, (provider, body, why)
    assert ("the quota of the day" in why) is (scope == "day")
    assert (0 < wait <= 120) if scope == "minute" else wait == 0


def test_a_minute_429_only_waits_and_the_limit_it_tells_is_learned():
    clock = [1000.0]
    b = quota.Budget(LIMITS, None, CANDIDATE, now=NOW, clock=lambda: clock[0])
    b.note("Z.AI", 100, "fix", status=429, body=ZAI_CONCURRENCY)
    assert not b.spent("Z.AI") and b.last_429["Z.AI"][0] == "minute" and b.wait_seconds("Z.AI", 100) == 60
    assert b.allows("Z.AI", 100)[0] is True                           # not spent: asked again after the wait
    b.note("Z.AI", 100, "fix", status=429, body=ZAI_DAY)
    assert "the quota of the day" in b.spent("Z.AI")
    # a request too large for Groq's minute: the limit its answer gives is learned, and kept for its day
    b.note("Groq", 0, "fix", status=413, body=GROQ_TPM.replace("6000", "5000"))
    assert b.minute_limit("Groq", "tokens") == 5000 and not b.spent("Groq")
    state = quota.merge(quota.empty_state(), json.loads(json.dumps(b.delta())), now=NOW)
    assert quota.Budget(LIMITS, state, CANDIDATE, now=NOW).minute_limit("Groq", "tokens") == 5000
    assert quota.learned_minute_tokens("no number here") is None and quota.learned_minute_tokens(GROQ_TPM) == 6000
    # the data: Z.AI's codes of concurrency and of an overloaded service are not its day's words any more
    zai = LIMITS["providers"]["Z.AI"]
    assert not any(w.endswith(("1302", "1305")) for w in zai["day_words"])
    assert {"code:1302", "code:1305"} <= set(zai["minute_words"])


def test_a_minute_429_is_waited_out_in_the_run_and_a_busy_service_is_asked_again(tmp_path):
    slept = []

    class Clock(p2.QuietTime):
        @staticmethod
        def sleep(seconds):
            slept.append(seconds)
    env = {"ZAI_API_KEY": "zai_TESTONLY", "AUTOFIX_ZAI_MODELS": "z1", "AUTOFIX_REVIEWERS": "Antigravity,Groq,Z.AI,OpenRouter"}
    usage = tmp_path / "usage.json"
    reserve = load("autofix-reserve")
    reserve.time = Clock()
    out, seen = run_reserve(reserve, tmp_path / "a", [(429, {}, ZAI_CONCURRENCY), p2.GOOD], env,
                            ["--quota-usage", str(usage), "--candidate", CANDIDATE])
    # (the fake clock does not move while it "sleeps", so the budget's own wait before the next ask is seen too)
    assert out["result"] == "ok" and [h for h, _b in seen] == ["api.z.ai", "api.z.ai"] and slept[0] == 61
    assert "Z.AI" not in json.loads(usage.read_text())["spent"]          # never spent for the day by it
    # a 503: asked again after 5, then 15 seconds (BACKOFF), without using up the model's tries
    slept.clear()
    out, seen = run_reserve(reserve, tmp_path / "b", [(503, {}, "busy"), (503, {}, "busy"), p2.GOOD], env,
                            ["--quota-usage", str(usage)])
    assert out["result"] == "ok" and len(seen) == 3 and slept[:2] == [5, 15]


# =====================================================================================================
# 1. A request larger than a provider's limit per minute is fitted to it, never skipped for its size
# =====================================================================================================

BIG = {"ike/big.py": "".join("VALUE_%04d = %d  # a line of a large file\n" % (i, i) for i in range(260))}
FAILURE = ("# Failure to fix\n\n## Job `tests` (failed step: Tests)\n\n```text\n" + "noise of the log\n" * 900 +
           "FAILED tests/test_window.py::test_width - AssertionError: assert 10 == 11\n```\n"
           "\n## Why earlier fixes were refused\n\nThe static guard refused it: a removed condition in ike/window.py\n")


CONTEXT = "# Code at the failure\n\n" + "".join("%5d  # the code around the failure, line %d\n" % (i, i)
                                                for i in range(1, 260))


def run_reserve(reserve, tmp_path, answers, env, extra, failure=None, files=None, related=None, context=None):
    repo = p2.make_repo(tmp_path, dict(p2.FILES, **(files or {})))
    auto = repo / ".autofix"
    auto.mkdir()
    (auto / "failure.md").write_text(failure or p2.FAILURE)
    (auto / "context.md").write_text(context or "# Code at the failure\n\n  1  def width():\n  2      return 10\n")
    (auto / "related.txt").write_text(related or "ike/window.py\n")
    (repo / ".git/info/exclude").write_text(".autofix/\n")
    prompt = tmp_path / "prompt.md"
    prompt.write_text("RULES")
    status, seen = tmp_path / "status.json", []
    reserve.main(["--workdir", str(repo), "--prompt", str(prompt), "--status", str(status), *extra], env=env,
                 opener=p2.opener_of(list(answers), seen))
    return json.loads(status.read_text()), seen


def that_day(tmp_path):
    """tools/ai-quota.json as it was on 2026-11-25 for Groq (6,000 tokens a minute; Groq's own page gives 8,000)."""
    data = json.loads((ROOT / "tools/ai-quota.json").read_text("utf-8"))
    data["providers"]["Groq"]["tokens_per_minute"] = 6000
    path = tmp_path / "ai-quota-that-day.json"
    path.write_text(json.dumps(data))
    return path


def size_of(body):
    """The tokens a request is counted as (tools/ai-quota.py estimate_tokens)."""
    return quota.estimate_tokens(sum(len(m["content"]) for m in body["messages"]), body["max_tokens"], LIMITS)


def test_a_request_larger_than_the_minute_is_fitted_and_asked(tmp_path, capsys):
    reserve = load("autofix-reserve")
    reserve.time = p2.QuietTime()
    env = {"GROQ_API_KEY": "gsk_TESTONLY", "AUTOFIX_GROQ_MODELS": "g1",
           "AUTOFIX_REVIEWERS": "Antigravity,Groq,Z.AI,OpenRouter"}
    out, seen = run_reserve(reserve, tmp_path, [p2.GOOD], env, ["--quota-usage", str(tmp_path / "u.json"),
                                                                "--quota-limits", str(that_day(tmp_path))],
                            failure=FAILURE, files=BIG, related="ike/window.py\nike/big.py\n", context=CONTEXT)
    assert out["result"] == "ok" and [h for h, _b in seen] == ["api.groq.com"]
    body = seen[0][1]
    user = body["messages"][1]["content"]
    assert size_of(body) <= 6000                                          # within Groq's minute
    # what must stay: the end of the failure, the refusal reasons, the files to change
    for kept in ("FAILED tests/test_window.py::test_width", "The static guard refused it", "- ike/window.py",
                 "def width():"):
        assert kept in user, kept
    assert "fitted to its limit per minute" in capsys.readouterr().out
    # without the fitting, the same request would not fit (the size the reserves used to skip it for)
    full = reserve.message_for(FAILURE, CONTEXT, {"ike/window.py": p2.FILES["ike/window.py"], **BIG}, 14_000)
    assert quota.estimate_tokens(len(body["messages"][0]["content"]) + len(full), 2000, LIMITS) > 6000
    # deterministic: the same inputs give the same request
    again = reserve.compact_message(FAILURE, "ctx", {"ike/window.py": "x\n", **BIG}, 5000, "r", ["ike/window.py"])
    assert again == reserve.compact_message(FAILURE, "ctx", {"ike/window.py": "x\n", **BIG}, 5000, "r",
                                            ["ike/window.py"]) and len(again) <= 5000


def test_only_a_request_that_cannot_fit_at_all_is_skipped_with_its_reason(tmp_path):
    reserve = load("autofix-reserve")
    small = quota.load_limits()
    small["providers"]["Groq"]["tokens_per_minute"] = 1500
    spend = quota.Budget(small, None, CANDIDATE)
    user, _tokens, why = reserve.fitted(spend, "Groq", "R" * 3000, "U" * 20000, 2000, lambda room: "u" * room)
    assert user is None and "even the smallest request" in why and "1500" in why
    # the real rules of today's task (the filter lists' analysis of a fix that may reach main by itself) fit
    # Groq's free minute with room for the failure: Groq is never unusable for this task by its size
    reserve.AUTO["on"] = True
    try:
        system = (ROOT / ".github/autofix/prompt.md").read_text("utf-8") + reserve.AUTO_RULES + "\n" + \
            reserve.instructions(False, lists=True)
    finally:
        reserve.AUTO["on"] = False
    spend = quota.Budget(quota.load_limits(), None, CANDIDATE)
    user, tokens, why = reserve.fitted(spend, "Groq", system, "U" * 40000, 2000,
                                       lambda room: reserve.compact_message(FAILURE, "C" * 9000, BIG, room, "r",
                                                                            ["ike/big.py"]))
    assert user is not None and "fitted" in why and tokens >= reserve.MIN_ANSWER
    assert quota.estimate_tokens(len(system) + len(user), tokens, LIMITS) <= LIMITS["providers"]["Groq"][
        "tokens_per_minute"]
    assert "FAILED tests/test_window.py::test_width" in user


# =====================================================================================================
# 3. The reviewers' reserve has a way forward; the reviews are never skipped
# =====================================================================================================

def test_the_way_forward_writes_the_fix_now_and_leaves_its_reviews_for_later():
    # today's state: Z.AI spent, Antigravity's requests used up
    state = state_of(**{"Z.AI": {"spent": "429: the quota of the day (it says so)"}, "Antigravity": {"requests": 20}})
    b = quota.Budget(LIMITS, state, CANDIDATE)
    # Groq reviews within its own minute now (it never counted as a reviewer: 9,000 tokens against 6,000)
    assert b.review_size("Groq") == min(9000, LIMITS["providers"]["Groq"]["tokens_per_minute"])
    assert "Groq" in b.reviewers_left("OpenRouter")
    small = quota.load_limits()
    small["providers"]["Groq"]["tokens_per_minute"] = 6000
    assert quota.Budget(small, state, CANDIDATE).review_size("Groq") == 6000
    for name in ("OpenRouter", "Groq"):
        ok, why = b.allows(name, 4000)
        assert ok is False and why.startswith(quota.RESERVE_WHY)
    assert b.way_forward(["Z.AI", "OpenRouter", "Groq"]) == ("OpenRouter", "reviews-later")
    assert b.defer_reviews is False                                       # only for the way forward's own question
    # the one that leaves the most reviewers with room today is preferred to the order
    room = quota.Budget(LIMITS, state_of(**{"Z.AI": {"spent": "x"}, "Antigravity": {"requests": 20},
                                            "OpenRouter": {"spent": "x"}}), CANDIDATE)
    assert room.way_forward(["OpenRouter", "Groq"])[0] == "Groq"
    # never for background work, which simply waits; never when too few providers could ever review it
    drill = quota.Budget(LIMITS, state, "automation/update/drill-x")
    assert drill.way_forward(["OpenRouter", "Groq"])[0] is None
    two = quota.Budget(LIMITS, state, CANDIDATE, available=["Groq", "OpenRouter"])
    assert two.way_forward(["OpenRouter", "Groq"])[0] is None
    two.defer_reviews = True
    assert "could ever review it" in two.allows("Groq", 4000)[1]
    # a provider that is free to be asked is asked now, with the reserve kept
    assert quota.Budget(LIMITS, None, CANDIDATE).way_forward(["Groq"]) == ("Groq", "now")


def test_a_fix_with_its_reviews_later_still_needs_two_independent_reviews_to_merge():
    # the merge requires the ai-review status of two independent providers on that very commit: nothing here
    # changes it (tools/automerge.py, tools/ai-review.py NEEDED)
    rv = load("ai-review")
    assert rv.NEEDED == 2 and rv.STATUS == "ai-review"
    text = (ROOT / "tools/automerge.py").read_text("utf-8")
    assert 'return "wait", "the status ai-review of the workflow is not on this commit yet"' in text
    assert "defer_reviews" not in text and "reviews_deferred" not in text


# =====================================================================================================
# 6. The drill: today's four reasons, exactly, and now someone is asked
# =====================================================================================================

def todays_state(tmp_path):
    path = tmp_path / "quota.json"
    path.write_text(json.dumps(state_of(**{"Z.AI": {"spent": "429: the quota of the day (it says so)", "requests": 3},
                                           "Antigravity": {"requests": 20}})))
    return path


ENV = dict(p2.ENV, AUTOFIX_GROQ_MODELS="qwen/qwen3.8-27b", AUTOFIX_ZAI_MODELS="glm-4.7-flash",
           AUTOFIX_OPENROUTER_MODELS="cohere/north-mini-code:free")


def test_the_drill_of_the_deadlock_of_2026_11_25_asks_someone(tmp_path, capsys):
    reserve = load("autofix-reserve")
    reserve.time = p2.QuietTime()
    state, usage = todays_state(tmp_path), tmp_path / "usage.json"
    out, seen = run_reserve(reserve, tmp_path / "w", [p2.GOOD], ENV, [
        "--quota-limits", str(that_day(tmp_path)), "--quota-state", str(state), "--quota-usage", str(usage),
        "--candidate", CANDIDATE, "--first", "Z.AI", "--order", "Z.AI,OpenRouter,Antigravity,Groq", "--task", "lists"],
        failure=FAILURE, files=BIG, related="ike/window.py\nike/big.py\n", context=CONTEXT)
    printed = capsys.readouterr().out
    # the first pass meets today's reasons, in today's order
    lines = printed.splitlines()
    assert lines[:2] == ["Reserve: Z.AI / glm-4.7-flash",
                         "  not asked: spent today (429: the quota of the day (it says so))"]
    assert "Reserve: OpenRouter / cohere/north-mini-code:free" in lines
    assert any(ln.startswith("  not asked: the reviewers' reserve: after a fix by OpenRouter") for ln in lines)
    # Groq's request is no longer "larger than its limit per minute": it is fitted, and only the reserve holds it
    assert "larger than its limit per minute" not in printed and "fitted to its limit per minute" in printed
    assert any(ln.startswith("  not asked: the reviewers' reserve: after a fix by Groq") for ln in lines)
    # ... and then someone is asked: the fix is written now, its two reviews come on a later day
    before = int(printed.split("tokens instead of ")[1].split()[0])
    assert before > 6000                                                   # the size it was skipped for, every day
    assert "writes the fix now" in printed
    assert [h for h, _b in seen] == ["openrouter.ai"] and out["result"] == "ok"
    assert out["model"] == "OpenRouter / cohere/north-mini-code:free" and out["reviews_deferred"] is True
    assert out["no_provider"] is False and "non entra in main senza di esse" in out["message"]
    delta = json.loads(usage.read_text())
    assert [c["provider"] for c in delta["calls"]] == ["OpenRouter"] and delta["result"] == "answered"


@pytest.fixture
def agent_run(tmp_path, monkeypatch):
    agent = load("autofix-agent")
    work = tmp_path / "work"
    (work / ".autofix").mkdir(parents=True)
    (work / ".autofix/failure.md").write_text(p2.FAILURE)
    prompt = tmp_path / "prompt.md"
    prompt.write_text("RULES")
    status, usage = tmp_path / "status.json", tmp_path / "usage.json"
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaTESTONLY")
    monkeypatch.setenv("AUTOFIX_REVIEWERS", "Antigravity,Groq,Z.AI,OpenRouter")
    for name in ("AUTOFIX_UNAVAILABLE", "AUTOFIX_FIRST", "AUTOFIX_MODEL"):
        monkeypatch.delenv(name, raising=False)
    started = []

    real_run = subprocess.run

    def fake_run(cmd, *a, **k):
        if cmd and cmd[0] == "git":
            return real_run(cmd, *a, **k)                                # the agent's own look at the tree
        started.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, b"{}", b"")
    monkeypatch.setattr(agent.subprocess, "run", fake_run)

    def run(state, *extra):
        assert agent.main(["--workdir", str(work), "--prompt", str(prompt), "--out", str(tmp_path / "out"),
                           "--status", str(status), "--auto", "--quota-limits", str(ROOT / "tools/ai-quota.json"),
                           "--quota-state", str(state), "--quota-usage", str(usage), "--candidate", CANDIDATE,
                           "--agent-cmd", "agy", *extra]) == 0
        return json.loads(status.read_text()), json.loads(usage.read_text()) if usage.is_file() else None, started
    return run


def test_the_drill_rotation_goes_to_the_reserves_while_one_of_them_can_be_asked(tmp_path, agent_run):
    out, _usage, started = agent_run(todays_state(tmp_path), "--first", "Z.AI")
    assert out["result"] == "rotated" and started == []                    # OpenRouter will write it (above)


def test_the_rotation_never_skips_antigravity_when_it_is_the_only_one_with_room(tmp_path, agent_run, capsys):
    path = tmp_path / "quota.json"
    path.write_text(json.dumps(state_of(**{n: {"spent": "429: the quota of the day (it says so)"}
                                           for n in ("Groq", "Z.AI", "OpenRouter")})))
    out, usage, started = agent_run(path, "--first", "Z.AI")
    assert len(started) == 1 and out["result"] == "ok" and out["reviews_deferred"] is True
    assert "non entra in main senza di esse" in out["message"] and "Antigravity goes on" in capsys.readouterr().out
    assert [c["provider"] for c in usage["calls"]] == ["Antigravity"]
    # not rotated: the same way forward (it used to wait for a reserve of reviewers that could not come today)
    out, _usage, started = agent_run(path)
    assert len(started) == 2 and out["result"] == "ok" and out["reviews_deferred"] is True
    # while a reserve can still be asked, Antigravity keeps the reviewers' reserve as before
    path.write_text(json.dumps(state_of(**{n: {"spent": "x"} for n in ("Groq", "Z.AI")})))
    out, _usage, started = agent_run(path)
    assert len(started) == 2 and out["result"] == "budget" and quota.RESERVE_WHY in out["detail"]


# =====================================================================================================
# 5. The watchdog: work that asked nobody for days is said, plainly
# =====================================================================================================

def test_the_watchdog_names_work_that_asked_nobody_for_two_days(tmp_path):
    state = quota.empty_state()
    yesterday = (NOW - dt.timedelta(days=1)).strftime("%Y-%m-%d")
    quota.ran(state, "no-provider", yesterday, component=CANDIDATE)
    assert quota.days_unasked(state, CANDIDATE, NOW) == 1 and quota.stuck(state, NOW) == []
    quota.ran(state, "answered", yesterday, component="automation/update/crates")         # another branch: no matter
    quota.ran(state, "no-provider", now=NOW, component=CANDIDATE)
    assert quota.days_unasked(state, CANDIDATE, NOW) == 2 and quota.stuck(state, NOW) == [(CANDIDATE, 2)]
    text = quota.stuck_text(state, NOW)
    assert "nessun assistente AI è stato interpellato" in text and CANDIDATE in text and "2 giorni" in text
    assert quota.days_unasked(state, CANDIDATE, NOW + dt.timedelta(days=1)) == 2           # nothing ran yet today
    quota.ran(state, "answered", now=NOW, component=CANDIDATE)
    assert quota.days_unasked(state, CANDIDATE, NOW) == 0 and quota.stuck_text(state, NOW) == ""
    # bounded, and only branches of the automation are recorded
    for i in range(60):
        quota.ran(state, "no-provider", now=NOW, component="automation/update/x-%02d" % i)
    quota.ran(state, "no-provider", now=NOW, component="not a branch")
    assert len(state["days"][NOW.strftime("%Y-%m-%d")]["unasked"]) <= quota.MAX_UNASKED
    assert "not a branch" not in json.dumps(state)
    # the command the workflow runs records the branch
    path = tmp_path / "quota.json"
    path.write_text(json.dumps(quota.empty_state()))
    assert quota.main(["ran", "--state", str(path), "--result", "no-provider", "--component", CANDIDATE]) == 0
    assert json.loads(path.read_text())["days"][quota.day_of()]["unasked"] == {CANDIDATE: 1}


def test_the_watchdog_reaches_the_signing_notice_and_the_reserves_message(tmp_path):
    yesterday = quota.day_of(quota.now_utc() - dt.timedelta(days=1))
    state = quota.empty_state()
    quota.ran(state, "no-provider", yesterday, component=CANDIDATE)
    quota.ran(state, "no-provider", component=CANDIDATE)
    info = {"last": "v1.1.25", "unread": [], "pending": ["#111"], "quota": quota.summary(LIMITS, state),
            "changes": [], "stuck": quota.stuck_text(state)}
    text = notice.body("1.1.26", "o/r", "owner", info)
    assert "niente deve rimanere indietro" in text and CANDIDATE in text
    assert text.index("niente deve rimanere indietro") < text.index("#111")
    assert "stuck_text(state)" in (ROOT / "tools/release-notice.py").read_text("utf-8")
    # the reserves' run that asks nobody again says so in its message (it reaches the pull request's comment)
    spent = state_of(**{n: {"spent": "429: the quota of the day (it says so)"} for n in ("Groq", "Z.AI", "OpenRouter")})
    quota.ran(spent, "no-provider", yesterday, component=CANDIDATE)
    path = tmp_path / "quota.json"
    path.write_text(json.dumps(spent))
    reserve = load("autofix-reserve")
    reserve.time = p2.QuietTime()
    out, seen = run_reserve(reserve, tmp_path / "w", [], ENV, ["--quota-state", str(path), "--candidate", CANDIDATE])
    assert seen == [] and out["no_provider"] is True and "niente deve rimanere indietro" in out["watchdog"]
    assert out["watchdog"] in out["message"]


def test_the_workflow_counts_a_rotated_attempt_that_asked_nobody_and_records_the_branch():
    fix = p2.jobs_of("autofix.yml")["fix"]
    assert '"nokey", "budget", "rotated")' in fix
    remember = p2.jobs_of("autofix.yml")["remember"]
    assert 'ran --state quota.json --result no-provider --component "$COMPONENT"' in remember
    assert 'ran --state quota.json --result answered --component "$COMPONENT"' in remember
    # the new proofs are the AIs' to keep, never to change (a test keeps the two lists together)
    assert "tests/test_automat_deadlock.py" in (ROOT / "tools/check-autofix-patch.py").read_text("utf-8")
    assert "tests/test_automat_deadlock.py" in (ROOT / "tools/autofix-context.py").read_text("utf-8")
    doc = (ROOT / "docs/MAINTENANCE.md").read_text("utf-8")
    assert "No deadlock of the free quotas" in doc and "tests/test_automat_deadlock.py" in doc


# =====================================================================================================
# The providers' own signals (their documentation and code, 2026-11-25: tools/ai-quota.json's sources)
# =====================================================================================================

def test_gemini_says_which_limit_and_a_model_that_is_gone_gives_way_to_the_next():
    agent = load("autofix-agent")

    def err(code, status, msg):
        return 'AGY_ERROR:{"error_code": %d, "status": "%s"}\n%s' % (code, status, msg)
    # the day first, before a short retryDelay is trusted (google-gemini/gemini-cli googleQuotaErrors.ts)
    assert agent.classify(1, err(429, "RESOURCE_EXHAUSTED", "quotaId: GenerateRequestsPerDayPerProjectPerModel-"
                                                            "FreeTier retryDelay: 20s"))[0] == "day"
    assert agent.classify(1, err(429, "RESOURCE_EXHAUSTED", "Quota exceeded, limit: 0, model: x retryDelay: 9s"))[0] \
        == "day"
    assert agent.classify(1, err(429, "RESOURCE_EXHAUSTED", "GenerateRequestsPerMinutePerProjectPerModel-FreeTier "
                                                            "retryDelay: 40s")) == ("minute", 40)
    assert agent.classify(1, err(429, "RESOURCE_EXHAUSTED", "reason: MODEL_CAPACITY_EXHAUSTED"))[0] == "temporary"
    # a model no longer offered (several free models were announced to leave Antigravity on 2026-11-30): the next one
    assert agent.MODEL_GONE.search("404 NOT_FOUND: models/gemini-3.8-flash is not found for API version v1beta")
    assert not agent.MODEL_GONE.search("API key not valid")


def test_a_gone_model_does_not_stop_antigravity(tmp_path, monkeypatch):
    agent = load("autofix-agent")
    work = tmp_path / "work"
    (work / ".autofix").mkdir(parents=True)
    (work / ".autofix/failure.md").write_text(p2.FAILURE)
    prompt = tmp_path / "prompt.md"
    prompt.write_text("RULES")
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaTESTONLY")
    monkeypatch.setenv("AUTOFIX_MODEL", "Gone Model")
    for name in ("AUTOFIX_UNAVAILABLE", "AUTOFIX_FIRST", "AUTOFIX_REVIEWERS"):
        monkeypatch.delenv(name, raising=False)
    real_run, asked = subprocess.run, []

    def fake_run(cmd, *a, **k):
        if cmd and cmd[0] == "git":
            return real_run(cmd, *a, **k)
        model = cmd[cmd.index("--model") + 1]
        asked.append(model)
        if model == "Gone Model":
            return subprocess.CompletedProcess(cmd, 1, b"", b'AGY_ERROR:{"error_code": 404, "status": "NOT_FOUND"}\n'
                                                           b"models/gone-model is not found")
        return subprocess.CompletedProcess(cmd, 0, b"{}", b"")
    monkeypatch.setattr(agent.subprocess, "run", fake_run)
    status = tmp_path / "status.json"
    assert agent.main(["--workdir", str(work), "--prompt", str(prompt), "--out", str(tmp_path / "out"), "--status",
                       str(status), "--agent-cmd", "agy"]) == 0
    assert json.loads(status.read_text())["result"] == "ok" and asked[:2] == ["Gone Model", agent.FREE_MODELS[0]]


def test_openrouters_privacy_setting_is_said_plainly_and_is_no_quota(tmp_path):
    reserve = load("autofix-reserve")
    reserve.time = p2.QuietTime()
    env = {"OPENROUTER_API_KEY": "sk-or-TESTONLY", "AUTOFIX_OPENROUTER_MODELS": "o1:free",
           "GROQ_API_KEY": "gsk_TESTONLY", "AUTOFIX_GROQ_MODELS": "g1"}
    policy = (404, {}, '{"error": {"message": "No endpoints found matching your data policy (Free model training)", '
                       '"code": 404}}')
    out, seen = run_reserve(reserve, tmp_path, [(429, {}, "busy"), policy], env, [])
    assert [h for h, _b in seen] == ["api.groq.com", "openrouter.ai"]       # no search for other free models
    assert "impostazioni di privacy dell'account" in out["message"] and out["result"] != "ok"
    assert out["no_provider"] is True


def test_the_data_names_its_sources_and_what_is_not_verified():
    data = json.loads((ROOT / "tools/ai-quota.json").read_text("utf-8"))["providers"]
    assert "googleQuotaErrors.ts" in data["Antigravity"]["signals_source"]
    assert data["Antigravity"]["day_wait_seconds"] == 300
    assert "console.groq.com/docs/rate-limits" in data["Groq"]["signals_source"]
    assert "docs.z.ai/api-reference/api-code" in data["Z.AI"]["words_source"]
    assert {"code:1308", "code:1309", "code:1310", "code:1313"} <= set(data["Z.AI"]["day_words"])
    assert "openrouter_free_tier_per_minute" in data["OpenRouter"]["minute_words"]
    assert data["OpenRouter"]["requests_per_minute"] == 20 and data["OpenRouter"]["requests_per_day"] == 50
    # nothing read only through a search excerpt is marked verified (a person verifies, the file says)
    assert all(p["verified"] is False for p in data.values())
    assert quota.load_limits()["providers"]["Groq"]["day_wait_seconds"] == quota.DAY_WAIT


# =====================================================================================================
# The values read on the providers' own pages on 2026-11-25, and the default models
# =====================================================================================================

@pytest.mark.parametrize("provider, body, headers, scope", [
    # Z.AI's official list: every limit is a 429, the code tells which (docs.z.ai/api-reference/api-code)
    ("Z.AI", '{"error": {"code": "1311", "message": "Your current subscription plan does not yet include access to '
             'glm-5"}}', {}, "day"),
    ("Z.AI", '{"error": {"code": "1314", "message": "Enterprise package expired"}}', {}, "day"),
    ("Z.AI", '{"error": {"code": "1321", "message": "Usage limit reached. Resets at 2026-11-26 00:00"}}', {}, "day"),
    ("Z.AI", '{"error": {"code": "1303", "message": "?"}}', {}, "minute"),          # not on the list: no day
    # the Interactions API's own codes (ai.google.dev/gemini-api/docs/api-errors)
    ("Antigravity", '{"error": {"code": "quota_exceeded", "message": "You exceeded your daily quota"}}', {}, "day"),
    ("Antigravity", '{"error": {"code": "rate_limit_exceeded", "message": "per-minute token limit"}}', {}, "minute"),
    # OpenRouter's documented 429 says the same for a minute and a day: no day without more
    ("OpenRouter", '{"error": {"code": 429, "message": "Rate limit exceeded", "metadata": {"error_type": '
                   '"rate_limit_exceeded"}}}', {}, "minute"),
    # its X-RateLimit-* come only with a 429, also inside the body: the limiter of a minute (OpenRouter's blog)
    ("OpenRouter", '{"error": {"message": "Rate limit exceeded: free-models-per-min. ", "code": 429, "metadata": '
                   '{"headers": {"X-RateLimit-Limit": "20", "X-RateLimit-Remaining": "0", "X-RateLimit-Reset": '
                   '"1792448640000"}, "limit_source": "openrouter_free_tier_per_minute"}}}', {}, "minute"),
    ("OpenRouter", "", {"X-RateLimit-Limit": "20", "X-RateLimit-Remaining": "0"}, "minute"),
])
def test_the_official_signals_of_2026_11_25(provider, body, headers, scope):
    assert quota.rate_limit_scope(LIMITS["providers"][provider], headers, body)[0] == scope, (provider, body)


def test_the_values_read_on_the_providers_pages_are_in_the_data_with_their_sources():
    data = json.loads((ROOT / "tools/ai-quota.json").read_text("utf-8"))
    groq = data["providers"]["Groq"]
    # console.groq.com/docs/rate-limits: 30 RPM, 1K RPD, 8K TPM, 200K TPD for the three free models
    assert (groq["requests_per_minute"], groq["requests_per_day"], groq["tokens_per_minute"], groq["tokens_per_day"]) \
        == (30, 1000, 8000, 200000)
    assert groq["headers"]["requests"]["window"] == "day" and groq["headers"]["tokens"]["window"] == "minute"
    router = data["providers"]["OpenRouter"]
    assert (router["requests_per_minute"], router["requests_per_day"]) == (20, 50)
    assert router["headers"]["requests"]["window"] == "minute" and router["reset"]["time"] == "00:00"
    zai = data["providers"]["Z.AI"]
    assert "code:1303" not in zai["minute_words"] + zai["day_words"]
    assert {"1211", "1261", "1311", "1314-1321"} <= set(zai["error_codes"])
    assert "Midnight Pacific".lower() in data["providers"]["Antigravity"]["reset"]["source"].lower()
    # read on the provider's page that day, but not a person's check: "verified" stays the person's
    for name, conf in data["providers"].items():
        assert conf["source_verified_on"] == "2026-11-25" and conf["verified"] is False, name
        assert conf["source_urls"] and all(u.startswith("https://") for u in conf["source_urls"]), name
    assert len(LIMITS["providers"]["Z.AI"]["day_words"]) == len(zai["day_words"])        # none cut off


def test_the_default_models_are_the_free_ones_of_2026_11_25():
    registry = load("ai-providers")
    rv = load("ai-review")
    # Antigravity keeps only Gemini 4 Hydrogen on its free plan after 2026-11-30; the same names serve the API
    assert registry.GEMINI_MODELS[0] == "Gemini 4 Hydrogen (High)"
    assert [rv.gemini_id(m) for m in registry.GEMINI_MODELS] == [
        "gemini-4-hydrogen", "gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite"]
    models = {r[0]: r[4] for r in registry.RESERVES}
    assert models["Groq"] == ("openai/gpt-oss-120b", "qwen/qwen3.8-27b", "openai/gpt-oss-20b")
    assert models["Z.AI"] == ("glm-4.7-flash", "glm-4.5-flash")
    assert dict((r[0], r[1]) for r in registry.RESERVES)["Z.AI"] == "https://api.z.ai/api/paas/v4/chat/completions"
    # OpenRouter: only free models that were in its own list at zero price that day; the gone ones never
    listed = {m["id"]: m for m in OR_MODELS}
    for model in models["OpenRouter"]:
        assert model.endswith(":free") and registry.is_free_model("OpenRouter", model)
        assert model in listed and load("autofix-reserve").priced_free(listed[model]), model
    for gone in ("cohere/north-mini-code:free", "openai/gpt-oss-120b:free", "qwen/qwen3-coder:free"):
        assert gone not in models["OpenRouter"]
    # the Free Models Router is free, and only the last resort; a model without ":free" never is
    assert registry.is_free_model("OpenRouter", registry.FREE_ROUTER) and registry.FREE_ROUTER == "openrouter/free"
    assert not registry.is_free_model("OpenRouter", "openai/gpt-oss-120b")


# a few rows of GET https://openrouter.ai/api/v1/models as read on 2026-11-25 (prices are strings of dollars a token)
OR_MODELS = [
    {"id": "particle-ai/particle-1:free", "context_length": 1048576, "pricing": {"prompt": "0", "completion": "0"}},
    {"id": "nvidia/nemotron-3-ultra-550b-a55b:free", "context_length": 1000000,
     "pricing": {"prompt": "0", "completion": "0"}},
    {"id": "inclusionai/ling-3.2-flash:free", "context_length": 1048576, "pricing": {"prompt": "0", "completion": "0"}},
    {"id": "google/gemma-4-31b-it:free", "context_length": 262144, "pricing": {"prompt": "0", "completion": "0"}},
    {"id": "baidu/ernie-5.5-flash-preview:free", "context_length": 1024000,
     "pricing": {"prompt": "0", "completion": "0"}},
    {"id": "openrouter/free", "context_length": 200000, "pricing": {"prompt": "0", "completion": "0"}},
    {"id": "openai/gpt-oss-120b", "context_length": 131072, "pricing": {"prompt": "0.0000001", "completion": "0.0000005"}},
    {"id": "trap/model:free", "context_length": 999999, "pricing": {"prompt": "0.000001", "completion": "0"}},
]


def test_openrouters_models_are_rebuilt_from_its_own_list_each_run():
    reserve = load("autofix-reserve")
    seen = []

    def opener(req, timeout=0):
        seen.append((req.full_url, req.get_method()))
        return _Listing({"data": OR_MODELS})
    env = {"OPENROUTER_API_KEY": "sk-or-TESTONLY", "GROQ_API_KEY": "gsk_TESTONLY",
           "AUTOFIX_OPENROUTER_MODELS": "cohere/north-mini-code:free, particle-ai/particle-1:free"}
    plan = reserve.refreshed(reserve.chain(env), opener)
    assert seen == [("https://openrouter.ai/api/v1/models", "GET")]
    names = [(p[0], p[3]) for p in plan]
    assert names[:3] == [("Groq", "openai/gpt-oss-120b"), ("Groq", "qwen/qwen3.8-27b"), ("Groq", "openai/gpt-oss-20b")]
    # the gone one is left out, the listed free one first, then the largest free ones now, the router last
    assert [m for p, m in names if p == "OpenRouter"] == [
        "particle-ai/particle-1:free", "inclusionai/ling-3.2-flash:free", "baidu/ernie-5.5-flash-preview:free",
        "openrouter/free"]
    assert "trap/model:free" not in str(names) and "openai/gpt-oss-120b" not in [m for p, m in names if p != "Groq"]
    # no list: the chain as it is (never an empty OpenRouter)
    def down(req, timeout=0):
        raise OSError("down")
    assert reserve.refreshed(reserve.chain(env), down) == reserve.chain(env)
    assert reserve.refreshed([p for p in reserve.chain(env) if p[0] == "Groq"], opener)[-1][0] == "Groq"


class _Listing:
    def __init__(self, data):
        self.body = json.dumps(data).encode()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self, n=-1):
        return self.body
