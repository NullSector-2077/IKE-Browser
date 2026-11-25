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
ZAI_DAY = '{"error": {"code": "1304", "message": "The daily call limit for this API has been reached"}}'
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


def size_of(body):
    """The tokens a request is counted as (tools/ai-quota.py estimate_tokens)."""
    return quota.estimate_tokens(sum(len(m["content"]) for m in body["messages"]), body["max_tokens"], LIMITS)


def test_a_request_larger_than_the_minute_is_fitted_and_asked(tmp_path, capsys):
    reserve = load("autofix-reserve")
    reserve.time = p2.QuietTime()
    env = {"GROQ_API_KEY": "gsk_TESTONLY", "AUTOFIX_GROQ_MODELS": "g1",
           "AUTOFIX_REVIEWERS": "Antigravity,Groq,Z.AI,OpenRouter"}
    out, seen = run_reserve(reserve, tmp_path, [p2.GOOD], env, ["--quota-usage", str(tmp_path / "u.json")],
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
    assert quota.estimate_tokens(len(system) + len(user), tokens, LIMITS) <= 6000
    assert "FAILED tests/test_window.py::test_width" in user


# =====================================================================================================
# 3. The reviewers' reserve has a way forward; the reviews are never skipped
# =====================================================================================================

def test_the_way_forward_writes_the_fix_now_and_leaves_its_reviews_for_later():
    # today's state: Z.AI spent, Antigravity's requests used up
    state = state_of(**{"Z.AI": {"spent": "429: the quota of the day (it says so)"}, "Antigravity": {"requests": 20}})
    b = quota.Budget(LIMITS, state, CANDIDATE)
    # Groq reviews within its own minute now (it never counted as a reviewer: 9,000 tokens against 6,000)
    assert b.review_size("Groq") == 6000 and "Groq" in b.reviewers_left("OpenRouter")
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
        "--quota-limits", str(ROOT / "tools/ai-quota.json"), "--quota-state", str(state), "--quota-usage", str(usage),
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
