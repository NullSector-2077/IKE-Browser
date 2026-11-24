"""Real updates first (the owner's decision of 2026-11-24): every day's free quota used, above all for real updates.

In the owner's words: "use the free AIs every day, always when needed, above all for real updates; what is
left goes to self-evolution, drills etc.". The proofs, all offline (no AI, no network, a fake GitHub):

- the order: security fixes, then the updates of what ships, then the CI's, then background work, by the
  branch (tools/ai-quota.py priority_of); the daily check starts its waiting work in that order;
- all of it for real updates: security fixes and real updates may always use ALL of every free quota; the
  CI's updates and background work get only what they leave, and all of it; a 429 that work of class 3
  or 4 got never spends the provider for classes 1 and 2;
- the pause: CI and background work (the drill) wait at once while a real update is pending or retrying
  (an open pull request whose checks are not green, AUTOMAT's memory's rows whose pull request was not
  closed), and a fix is not started when its reviewers have nothing left for it;
- the leftover window: only the last hours before the provider's own reset, verified or not (an unverified
  one is more careful: the data file's time counts, and never during the real day's maintenance window);
  each provider's use counted on its own day; never while real work is pending, nor while that cannot be
  read (fail closed);
- the share of one candidate holds only while another real update is pending at the same time;
- OpenRouter: all its ":free" models are one budget of the account; GET /api/v1/key (no redirect followed)
  is read only for is_free_tier, the documented cap always stays, and the signing notice says when the
  account is not on the free tier;
- the drill's scheduler (tools/automat-drill.py): it says when the drill is paused, and starts a held-back
  fix again only when background work may run.
"""

import datetime as dt
import importlib.util
import io
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
NOW = dt.datetime(2026, 11, 24, 12, 0, tzinfo=dt.timezone.utc)          # 04:00 in California, noon UTC
TODAY = "2026-11-24"
REAL = "automation/update/pyqt6"
DRILL = "automation/update/drill-qt"


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_") + "_priority", ROOT / "tools" / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


quota = load("ai-quota")
drill = load("automat-drill")
work_tool = load("ai-work")
ledger_tool = load("maintenance-ledger")
registry = load("ai-providers")


def budget(candidate, state=None, now=NOW, **kw):
    return quota.Budget(quota.load_limits(), state, candidate, now=now, **kw)


def used(provider, requests, tokens=0, klass=quota.UPDATE):
    """A day's record where work of one class already used this much of a provider."""
    return {"schema": 1, "days": {TODAY: {"providers": {provider: {
        "requests": requests, "tokens": tokens, "classes": {str(klass): {"requests": requests, "tokens": tokens}}}}}}}


# =====================================================================================================
# 1. The order
# =====================================================================================================

@pytest.mark.parametrize("ref, klass", [
    ("automation/update/security-RUSTSEC-2026-0001", 1), ("automation/update/security-sandbox", 1),
    ("automation/update/security-sandbox-pyqt6", 1),
    ("automation/update/adblock", 2), ("automation/update/darkreader", 2), ("automation/builder/ubo-scriptlets", 2),
    ("automation/update/lists-2026-11-24", 2), ("automation/update/pyqt6", 2), ("automation/update/breeze-icons", 2),
    ("automation/daily-maintenance", 2), ("automation/autofix-main", 2), ("automation/update/arch-testing-2026-11-24", 2),
    ("", 2), ("something-unknown", 2),
    ("automation/update/ci-actions-checkout", 3),
    ("automation/update/drill-qt", 4), ("drill-qt", 4), ("automation/bench/replay", 4), ("automation/evolve/x", 4),
])
def test_every_piece_of_ai_work_has_its_class(ref, klass):
    assert quota.priority_of(ref, quota.load_limits()) == klass
    assert quota.priority_of(ref) == klass                               # the same without the data file


def test_the_classes_are_data_and_a_real_update_can_never_be_made_background():
    data = json.loads((ROOT / "tools/ai-quota.json").read_text("utf-8"))["priority"]
    assert 1 <= data["release_hours"] <= 6 and data["maintenance_window"]["zone"] == "UTC"
    assert "2026-11-24" in data["source"] and "drill" in data["about"] and "ALL of every provider" in data["about"]
    for gone in ("reserve_share", "release_margin", "security_slice"):
        assert gone not in data and gone not in quota.PRIORITY                 # no fixed share, no slice: all of it
    bad = quota.load_priority({"background": ["automation/update/", "automation/", "automation/builder/",
                                              "automation/update/security-", "automation/daily-maintenance",
                                              "automation/update/d", "automation/update/x-", "automation/bench",
                                              "automation/update/a/../b-", "automation/x/", "automation/update/s"],
                               "ci": ["automation/update/", "automation/update/c"], "release_hours": "3",
                               "pending_days": 0, "maintenance_window": {"start": "25:00", "end": "x"}})
    # each refused but two: a prefix ends in "-" or "/", is one segment longer than automation/<word>/ when under
    # automation/update/ or automation/builder/, and never covers a real update's own branches
    assert bad["background"] == ("automation/update/x-", "automation/x/")
    assert bad["ci"] == quota.PRIORITY["ci"]
    for key in ("release_hours", "pending_days", "maintenance_window"):
        assert bad[key] == quota.PRIORITY[key], key
    assert quota.load_priority(None) == quota.PRIORITY
    assert quota.priority_of("automation/update/pyqt6", {"priority": bad}) == 2


def test_the_daily_check_starts_waiting_work_in_the_order_of_the_classes():
    now = dt.datetime(2026, 11, 22, 5, 30, tzinfo=dt.timezone.utc)
    outcomes = []
    for n, branch in enumerate((DRILL, "automation/update/ci-pins", REAL, "automation/update/security-sandbox")):
        outcomes.append({"work": "run/%d" % (100 + n), "outcome": "deferred", "workflow": "Tests", "url": "u",
                         "run": str(n), "created": "2026-11-22T0%d:00:00Z" % n, "branch": branch,
                         "artifact": "ai-work-outcome-report"})
    empty = {"components": [], "findings": []}
    led = ledger_tool.update(None, empty, now=now, work={"run_id": "9", "outcomes": outcomes})
    assert led["dispatch"] == []
    led = ledger_tool.update(led, empty, now=now + dt.timedelta(hours=registry.RETRY_HOURS + 1),
                             work={"run_id": "9", "outcomes": []})
    assert [d["work"] for d in led["dispatch"]] == ["run/103", "run/102", "run/101", "run/100"]


# =====================================================================================================
# 2. Real updates may use all of it; the background only what they leave
# =====================================================================================================

MAINTENANCE = dt.datetime(2026, 11, 24, 6, 30, tzinfo=dt.timezone.utc)   # the daily candidates' hour
LATE = dt.datetime(2026, 11, 24, 22, 0, tzinfo=dt.timezone.utc)          # the last hours of a UTC day


def test_real_updates_may_always_use_all_of_every_free_quota():
    limit = quota.load_limits()["providers"]["Groq"]["requests_per_day"]
    heavy = used("Groq", limit - 1, klass=quota.BACKGROUND)
    for when in (NOW, MAINTENANCE, dt.datetime(2026, 11, 24, 23, 30, tzinfo=dt.timezone.utc)):
        for ref in (REAL, "automation/update/security-x", "automation/daily-maintenance"):
            assert budget(ref, heavy, now=when, pending=[REAL]).allows("Groq", 2000) == (True, ""), (ref, when)
            assert budget(ref, now=when).priority_why("Antigravity", 10, 0) == ""
    # only the provider's own quota stops them
    assert "used up" in budget(REAL, used("Groq", limit)).allows("Groq", 2000)[1]


def test_the_background_takes_what_real_work_leaves_and_all_of_it():
    limit = quota.load_limits()["providers"]["Groq"]["requests_per_day"]
    # no real work pending, the last hours of Groq's day (its reset is not verified): everything left
    nearly = used("Groq", limit - 1, klass=quota.UPDATE)
    assert budget(DRILL, nearly, now=LATE).allows("Groq", 2000, "review") == (True, "")
    assert budget("automation/update/ci-pins", nearly, now=LATE).allows("Groq", 2000, "review") == (True, "")
    assert "used up" in budget(DRILL, used("Groq", limit), now=LATE).allows("Groq", 2000, "review")[1]
    # while the real day's maintenance runs, its needs are not known yet: the background waits
    ok, why = budget(DRILL, now=MAINTENANCE).allows("Groq", 2000)
    assert ok is False and "maintenance is over" in why and "04:00-12:00 UTC" in why
    ok, why = budget("automation/update/ci-pins", now=MAINTENANCE).allows("Groq", 2000)
    assert ok is False and "class 3" in why
    # once it is over, still only the last hours of the provider's own day (review H1 of 2026-11-24: an
    # unverified reset is never a reason to open earlier)
    assert budget(DRILL, now=dt.datetime(2026, 11, 24, 21, 0, tzinfo=dt.timezone.utc)).allows("Groq", 2000)[0]
    assert budget(DRILL, now=dt.datetime(2026, 11, 24, 23, 59, tzinfo=dt.timezone.utc)).allows("Groq", 2000)[0]
    for hour, minute in ((3, 59), (12, 0), (12, 1), (20, 59)):
        ok, why = budget(DRILL, now=dt.datetime(2026, 11, 24, hour, minute, tzinfo=dt.timezone.utc)).allows("Groq", 2000)
        assert ok is False and "last 3 hours" in why and "unverified reset" in why, (hour, minute)


def test_the_use_of_each_class_is_recorded_by_the_run_and_by_the_job_that_merges_it():
    b = budget(DRILL)
    b.note("Groq", 1000, "fix")
    b.note("Z.AI", 500, "review")
    assert b.class_used("Groq", (quota.BACKGROUND,)) == (1, 1000) and b.class_used("Groq") == (0, 0)
    state = quota.merge(quota.empty_state(), json.loads(json.dumps(b.delta())), now=NOW)
    groq = state["days"][TODAY]["providers"]["Groq"]
    assert groq["classes"] == {"4": {"requests": 1, "tokens": 1000}}
    real = budget(REAL)
    real.note("Groq", 700, "fix")
    state = quota.merge(state, json.loads(json.dumps(real.delta())), now=NOW)
    assert quota.Budget(quota.load_limits(), state, DRILL, now=NOW).class_used("Groq") == (1, 700)
    # a delta's candidate with strange characters counts as real work (never starves anything)
    odd = quota.merge(quota.empty_state(), {"schema": 1, "day": TODAY, "candidate": "x y",
                                            "calls": [{"provider": "Groq", "requests": 1, "tokens": 1}]}, now=NOW)
    assert list(odd["days"][TODAY]["providers"]["Groq"]["classes"]) == ["2"]


def test_a_quota_answer_to_background_work_never_spends_the_provider_for_real_work():
    for why_body in ({"status": 429, "body": "Rate limit reached: requests per day (RPD)"},
                     {"status": 429, "headers": {"retry-after": "40000"}}):
        low = budget(DRILL)
        low.note("Groq", 100, "fix", **why_body)
        assert low.spent("Groq") and low.allows("Groq", 100)[0] is False
        state = quota.merge(quota.empty_state(), json.loads(json.dumps(low.delta())), now=NOW)
        assert state["days"][TODAY]["providers"]["Groq"]["spent_low"] and not \
            state["days"][TODAY]["providers"]["Groq"]["spent"]
        assert budget(REAL, state).allows("Groq", 100) == (True, "")                 # real work still asks
        assert budget("automation/update/security-x", state).allows("Groq", 100) == (True, "")
        assert budget("automation/update/ci-x", state).allows("Groq", 100)[0] is False
        assert quota.background_status(quota.load_limits(), state, None, NOW)["providers"].count("Groq") == 0
    # the agent's own word for a 429 of the day, too (mark_spent)
    low = budget(DRILL)
    low.mark_spent("Antigravity", "429: the quota of the day")
    assert budget(REAL, low.state).allows("Antigravity", 0, requests=10)[0] is True
    # a real update's 429, and money asked by anyone, spend it for everybody
    real = budget(REAL)
    real.note("Groq", 100, "fix", status=429, body="requests per day")
    assert budget("automation/update/security-x", real.state).allows("Groq", 100)[0] is False
    paid = budget(DRILL)
    paid.note("Z.AI", 100, "fix", status=402)
    assert budget(REAL, paid.state).allows("Z.AI", 100)[0] is False


# =====================================================================================================
# 3. The pause while real work is pending
# =====================================================================================================

def memory_with(*rows):
    return {"schema": 1, "attempts": {}, "solved": {}, "streak": {c: {"sig": "s", "n": n, "since": d, "date": d}
                                                                for c, n, d in rows}}


def test_the_pending_real_work_is_read_from_automats_memory():
    mem = memory_with((REAL, 2, TODAY), ("automation/update/security-x", 1, "2026-11-23"),
                      ("automation/update/old", 3, "2026-11-20"), (DRILL, 5, TODAY),
                      ("automation/update/ci-pins", 1, TODAY))
    assert quota.pending_work(mem, quota.load_limits(), NOW) == [REAL, "automation/update/security-x"]
    assert quota.pending_work(None, None, NOW) == [] and quota.pending_work({"streak": "x"}, None, NOW) == []
    # a merged fix ends the row (tools/automat-memory.py merged): nothing pending any more
    memory = load("automat-memory")
    m = memory.empty()
    memory.note(m, REAL, "sig", "published", provider="Groq", now=NOW)
    assert quota.pending_work(m, None, NOW) == [REAL]
    memory.merged(m, REAL, now=NOW)
    assert quota.pending_work(m, None, NOW) == []
    # any merge ends it, also one with no fix of an AI recorded; and a closed pull request ends it too
    m = memory_with((REAL, 2, TODAY), ("automation/update/adblock", 1, TODAY))
    memory.merged(m, REAL, now=NOW)
    memory.closed(m, ["automation/update/adblock"])
    assert quota.pending_work(m, None, NOW) == [] and m["attempts"] == {}


class FakePRs:
    """Open pull requests, the runs of their last commit, and closed ones (GET only)."""

    def __init__(self, open_prs, runs, closed=(), closed_at="2026-11-24T10:00:00Z"):
        self.open, self.runs, self.closed, self.calls = open_prs, runs, set(closed), []
        self.closed_at = closed_at

    def __call__(self, path, *a):
        self.calls.append(path)
        if path.startswith("repos/o/r/pulls?state=open"):
            return [{"head": {"ref": ref, "sha": sha}} for ref, sha in self.open]
        if path.startswith("repos/o/r/actions/runs?head_sha="):
            sha = path.split("head_sha=", 1)[1].split("&", 1)[0]
            if self.runs.get(sha) == "error":
                raise RuntimeError("HTTP 500")
            return {"workflow_runs": self.runs.get(sha, [])}
        if path.startswith("repos/o/r/pulls?state=closed&head=o:"):
            ref = path.split("head=o:", 1)[1].split("&", 1)[0]
            return [{"number": 1}] if ref in self.closed else []
        if path.startswith("repos/o/r/pulls?state=all&head=o:"):            # the newest pull request of a branch
            assert "sort=created&direction=desc&per_page=1" in path
            ref = path.split("head=o:", 1)[1].split("&", 1)[0]
            return [{"number": 1, "state": "closed", "closed_at": self.closed_at}] if ref in self.closed else []
        raise AssertionError(path)


def sha(n):
    return "%040x" % n


def test_the_pending_real_work_is_also_read_from_the_open_pull_requests():
    green = [{"status": "completed", "conclusion": "success"}, {"status": "completed", "conclusion": "skipped"}]
    api = FakePRs([("automation/update/adblock", sha(1)), ("automation/update/darkreader", sha(2)),
                   ("automation/update/security-x", sha(3)), ("automation/update/lists-2026-11-24", sha(4)),
                   (DRILL, sha(5)), ("automation/update/ci-pins", sha(6)), ("chatgpt/fix", sha(7)),
                   ("automation/builder/darkreader", sha(8))],
                  {sha(1): green, sha(2): green + [{"status": "completed", "conclusion": "failure"}],
                   sha(3): [{"status": "in_progress", "conclusion": None}], sha(4): [], sha(5): [],
                   sha(6): [{"status": "completed", "conclusion": "failure"}], sha(8): "error"})
    prs = quota.pending_from_prs("o/r", api)
    # not green: failed, still running, no run yet, runs not readable; background, CI and people's branches never
    assert prs["pending"] == ["automation/builder/darkreader", "automation/update/darkreader",
                              "automation/update/lists-2026-11-24", "automation/update/security-x"]
    assert "chatgpt/fix" not in prs["open"] and DRILL in prs["open"]
    assert not any(sha(5) in c or sha(6) in c for c in api.calls)                # no run read for class 3 or 4
    # the memory's rows: a closed pull request leaves them out, an open one or none at all keeps them
    mem = memory_with((REAL, 1, TODAY), ("automation/update/gone", 1, TODAY), ("automation/update/adblock", 1, TODAY))
    api.closed = {"automation/update/gone"}
    full = quota.gather_prs("o/r", api, mem, None, NOW)
    assert full["closed"] == ["automation/update/gone"]
    assert quota.pending_all(mem, None, NOW, full) == sorted(
        prs["pending"] + [REAL, "automation/update/adblock"])
    assert quota.pending_all(mem, None, NOW, None) == ["automation/update/adblock", "automation/update/gone", REAL]
    status = quota.background_status(quota.load_limits(), quota.empty_state(), None, NOW,
                                     prs={"pending": ["automation/update/darkreader"], "open": [], "closed": []})
    assert status["state"] == "paused" and status["pending"] == ["automation/update/darkreader"]


def test_the_run_reads_the_plans_list_of_pending_work(tmp_path):
    plan = tmp_path / "pending"
    plan.write_text("automation/update/darkreader\n%s\nautomation/update/ci-x\nnot a branch\n" % DRILL, "utf-8")
    mem = tmp_path / "memory.json"
    mem.write_text(json.dumps(memory_with((REAL, 1, dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")))), "utf-8")
    assert quota.pending_for_run(str(mem), str(plan)) == ["automation/update/darkreader"]
    # a list that should be there and is not: unknown, the background pauses (review H3: fail closed)
    assert quota.pending_for_run(str(mem), str(tmp_path / "none")) == [REAL, quota.UNKNOWN]
    assert quota.pending_for_run(str(mem), None) == [REAL]
    plan.write_text("", "utf-8")
    assert quota.pending_for_run(str(mem), str(plan)) == []          # the plan saw nothing pending (rows closed)


def test_background_and_ci_pause_at_once_while_real_work_is_pending_and_real_work_never_does():
    pending = quota.pending_work(memory_with((REAL, 1, TODAY)), None, NOW)
    ok, why = budget(DRILL, pending=pending).allows("Groq", 2000)
    assert ok is False and "paused for real updates first" in why and REAL in why
    assert budget(DRILL, pending=pending).pick(["Groq", "Z.AI", "OpenRouter"], 2000) == []
    ok, why = budget("automation/update/ci-pins", pending=pending).allows("Groq", 2000)
    assert ok is False and "paused for real updates first" in why              # the CI's updates too
    # the reviews of background work pause too (it resumes once real work is done)
    assert "paused" in budget(DRILL, pending=pending).allows("Groq", 2000, "review")[1]
    # real work and security fixes never pause
    assert budget(REAL, pending=pending).allows("Groq", 2000) == (True, "")
    assert budget("automation/update/security-y", pending=pending).allows("Groq", 2000) == (True, "")
    # background work named as pending is no reason to pause (in the last hours of Groq's day)
    assert budget(DRILL, pending=[DRILL, "automation/update/ci-pins"], now=LATE).allows("Groq", 2000) == (True, "")


def test_a_background_fix_waits_when_its_reviewers_have_nothing_left_for_it():
    limits = quota.load_limits()
    for name in ("Z.AI", "OpenRouter", "Antigravity"):
        limits["providers"][name]["reset"] = {"time": "12:00", "zone": "UTC", "verified": True}
    # in the last hours of Groq's day the others' day has fourteen hours left: their leftovers are not the
    # background's yet, so nobody could review
    ok, why = quota.Budget(limits, None, DRILL, now=LATE).allows("Groq", 2000)
    assert ok is False and "the reviewers' reserve" in why
    assert quota.Budget(limits, None, REAL, now=LATE).allows("Groq", 2000) == (True, "")   # real work: all of it


# =====================================================================================================
# 4. The end of a provider's day: nothing wasted, nothing real starved
# =====================================================================================================

def verified(provider, time="00:00", zone="UTC"):
    limits = quota.load_limits()
    limits["providers"][provider]["reset"] = {"time": time, "zone": zone, "verified": True}
    return limits


def test_each_provider_has_its_day_and_unverified_ones_say_so():
    data = json.loads((ROOT / "tools/ai-quota.json").read_text("utf-8"))["providers"]
    for name, conf in data.items():
        reset = conf["reset"]
        assert quota.RESET.match(reset["time"]) and quota.ZONE.match(reset["zone"]), name
        assert isinstance(reset["verified"], bool) and len(reset["source"]) > 40, name
        if not reset["verified"]:
            assert "could not be reached" in reset["source"] or "not checked" in reset["source"], name
    limits = quota.load_limits()
    assert quota.next_reset(limits["providers"]["Groq"], NOW) == dt.datetime(2026, 11, 25, tzinfo=dt.timezone.utc)
    # Gemini's day ends at midnight in California: 08:00 UTC in winter, 07:00 in summer
    assert quota.next_reset(limits["providers"]["Antigravity"], NOW) == dt.datetime(
        2026, 11, 25, 8, tzinfo=dt.timezone.utc)
    assert quota.next_reset(limits["providers"]["Antigravity"], dt.datetime(2026, 7, 1, 6, tzinfo=dt.timezone.utc)) == \
        dt.datetime(2026, 7, 1, 7, tzinfo=dt.timezone.utc)
    # an unreadable zone or time is the repository's own day
    assert quota.next_reset({"reset": quota._reset({"time": "25:00", "zone": "../etc"})}, NOW) == dt.datetime(
        2026, 11, 25, tzinfo=dt.timezone.utc)


def test_the_providers_own_reset_header_is_used_when_it_was_read():
    groq = {"x-ratelimit-limit-requests": "1000", "x-ratelimit-remaining-requests": "990",
            "x-ratelimit-reset-requests": "2h0m0s"}
    b = budget(REAL)
    b.note("Groq", 100, "fix", headers=groq)
    assert b.next_reset("Groq") == NOW + dt.timedelta(hours=2)
    state = quota.merge(quota.empty_state(), json.loads(json.dumps(b.delta())), now=NOW)
    later = budget(REAL, state, now=NOW + dt.timedelta(minutes=30))
    assert later.next_reset("Groq") == NOW + dt.timedelta(hours=2)            # kept with when it was read
    # a reset that is past, or absurdly far, is not used: the provider's "reset" of the data file is
    assert budget(REAL, state, now=NOW + dt.timedelta(hours=3)).next_reset("Groq") == dt.datetime(
        2026, 11, 25, tzinfo=dt.timezone.utc)
    obs = {"window": "day", "reset": 10 ** 6, "at": int(NOW.timestamp())}
    assert quota.next_reset(quota.load_limits()["providers"]["Groq"], NOW, obs) == dt.datetime(
        2026, 11, 25, tzinfo=dt.timezone.utc)
    # with a verified reset, the provider's own word places its last hours
    limits = verified("Groq")
    b = quota.Budget(limits, None, DRILL, now=NOW)
    b.note("Groq", 10, "review", headers=dict(groq, **{"x-ratelimit-reset-requests": "1h0m0s"}))
    assert b.leftover_window("Groq")[0] is True


def test_each_providers_use_is_counted_on_its_own_day():
    early = dt.datetime(2026, 11, 25, 3, 0, tzinfo=dt.timezone.utc)      # 19:00 of the 24th in California
    limits = quota.load_limits()
    assert quota.provider_day(limits["providers"]["Antigravity"], early) == "2026-11-24"
    assert quota.provider_day(limits["providers"]["Groq"], early) == "2026-11-25"
    b = budget(DRILL, now=early)
    b.note("Antigravity", 0, "fix", requests=10)
    b.note("Groq", 100, "fix")
    assert b.delta()["days"]["Antigravity"] == "2026-11-24" and b.delta()["days"]["Groq"] == "2026-11-25"
    state = quota.merge(quota.empty_state(), json.loads(json.dumps(b.delta())), now=early)
    assert state["days"]["2026-11-24"]["providers"]["Antigravity"]["requests"] == 10
    assert state["days"]["2026-11-25"]["providers"]["Groq"]["requests"] == 1
    # the same Gemini day, read later in UTC's next day: the use is still there; after its reset it is not
    assert budget(REAL, state, now=dt.datetime(2026, 11, 25, 7, 0, tzinfo=dt.timezone.utc)).used("Antigravity")[0] == 10
    assert budget(REAL, state, now=dt.datetime(2026, 11, 25, 8, 30, tzinfo=dt.timezone.utc)).used("Antigravity")[0] == 0
    # a provider day in a delta that is not of today or yesterday falls back to the run's day
    bad = quota.merge(quota.empty_state(), {"schema": 1, "day": "2026-11-25", "days": {"Groq": "2020-01-01"},
                                            "calls": [{"provider": "Groq", "requests": 1, "tokens": 1}]}, now=early)
    assert bad["days"]["2026-11-25"]["providers"]["Groq"]["requests"] == 1 and "2020-01-01" not in bad["days"]


def test_with_a_verified_reset_the_background_takes_the_leftovers_in_the_last_hours_of_the_providers_day():
    limits = verified("Groq")
    late = dt.datetime(2026, 11, 24, 22, 0, tzinfo=dt.timezone.utc)
    limit = limits["providers"]["Groq"]["requests_per_day"]
    assert quota.Budget(limits, None, DRILL, now=late).leftover_window("Groq")[0] is True
    ok, why = quota.Budget(limits, None, DRILL, now=NOW).allows("Groq", 2000)
    assert ok is False and "last 3 hours" in why                         # verified: only its last hours
    # everything left, no margin
    assert quota.Budget(limits, used("Groq", limit - 1, klass=quota.UPDATE), DRILL, now=late).allows(
        "Groq", 2000, "review") == (True, "")
    # NEVER while real work is pending: it pauses at once, also in the last hours
    ok, why = quota.Budget(limits, None, DRILL, now=late, pending=[REAL]).allows("Groq", 2000)
    assert ok is False and "paused for real updates first" in why
    assert quota.background_status(limits, quota.empty_state(), memory_with((REAL, 1, TODAY)), late)["state"] == \
        "paused"
    released = quota.background_status(limits, quota.empty_state(), None, late)
    assert released["state"] == "released" and "Groq" in released["providers"]
    # Gemini's verified day ends at 08:00 UTC: its last hours are 05:00-08:00 UTC, whatever UTC's day says
    gemini = verified("Antigravity", "00:00", "America/Los_Angeles")
    assert quota.Budget(gemini, None, DRILL, now=dt.datetime(2026, 11, 25, 6, tzinfo=dt.timezone.utc)
                        ).leftover_window("Antigravity")[0] is True
    assert quota.Budget(gemini, None, DRILL, now=late).leftover_window("Antigravity")[0] is False


def test_the_signing_notice_shows_what_real_work_and_the_background_used():
    state = used("Groq", 30, klass=quota.UPDATE)
    state["days"][TODAY]["providers"]["Groq"]["classes"]["4"] = {"requests": 12, "tokens": 0}
    rows = {r["provider"]: r for r in quota.summary(quota.load_limits(), state, NOW)}
    assert rows["Groq"]["real_requests"] == 30 and rows["Groq"]["background_requests"] == 12
    assert rows["Groq"]["reset_verified"] is False and rows["Groq"]["day"] == TODAY
    lines = load("release-notice").quota_lines([rows["Groq"]])
    assert "Oggi a sicurezza e aggiornamenti veri 30 richieste, al lavoro di fondo (quello che avanzava) 12." in \
        lines[0]


def test_background_status_says_open_paused_released_or_no_room():
    limits = quota.load_limits()
    mem = memory_with((REAL, 1, TODAY))
    assert quota.background_status(limits, quota.empty_state(), None, LATE)["state"] == "open"
    assert quota.background_status(limits, quota.empty_state(), None, NOW)["state"] == "no-room"   # 12 h left
    paused = quota.background_status(limits, quota.empty_state(), mem, NOW)
    assert paused["state"] == "paused" and paused["pending"] == [REAL] and "real updates first" in paused["why"]
    late = quota.background_status(limits, quota.empty_state(), mem, dt.datetime(2026, 11, 24, 23, tzinfo=dt.timezone.utc))
    assert late["state"] == "paused"                                     # never over pending real work
    assert quota.background_status(limits, quota.empty_state(), None, MAINTENANCE)["state"] == "no-room"
    spent = quota.empty_state()
    for name in quota.NAMES:
        quota._prov(spent, quota.provider_day(limits["providers"][name], NOW), name)["spent"] = "429"
    assert quota.background_status(limits, spent, None, NOW)["state"] == "no-room"
    # the class of a branch, for the logs
    out = io.StringIO()
    import contextlib
    with contextlib.redirect_stdout(out):
        assert quota.main(["priority", "--candidate", DRILL]) == 0
        assert quota.main(["priority", "--candidate", "automation/update/security-z"]) == 0
    assert "class=4\nwhat=background\nbackground=" in out.getvalue() and "class=1" in out.getvalue()


# =====================================================================================================
# 5. OpenRouter: one budget for all its free models
# =====================================================================================================

class Answer(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_openrouters_free_models_share_one_budget_of_the_account():
    conf = json.loads((ROOT / "tools/ai-quota.json").read_text("utf-8"))["providers"]["OpenRouter"]
    assert conf["shared_free_models"] is True and set(conf["account"]) == {"free_tier_requests_per_day", "verified",
                                                                           "source"}
    assert conf["account"]["free_tier_requests_per_day"] == conf["requests_per_day"]
    assert "OPENROUTER_KEY_INFO" in conf["account"]["source"]
    # every :free model is the one provider "OpenRouter": two models' calls count against one cap
    b = budget(REAL)
    limit = b.day_limit("OpenRouter", "requests")
    for _model in registry.RESERVES[-1][4]:
        assert registry.is_free_model("OpenRouter", _model)
        b.note("OpenRouter", 100, "review")
    assert b.remaining("OpenRouter")["requests"] == limit - len(registry.RESERVES[-1][4])
    assert set(quota.NAMES) == {"Antigravity", "Groq", "Z.AI", "OpenRouter"}     # no model is a budget of its own


@pytest.mark.parametrize("answer, tier", [
    ({"data": {"is_free_tier": True, "usage": 0, "limit": None}}, "free"),
    ({"data": {"is_free_tier": True, "rate_limit": {"requests": 200, "interval": "1d"}}}, "free"),
    ({"data": {"requests_per_day": 5000, "is_free_tier": False}}, "not-free"),
    ({"data": {"is_free_tier": False, "usage": 3.5, "limit": 10}}, "not-free"),
    ({"data": {"rate_limit": {"requests": 20, "interval": "10s"}}}, ""),
    ({"data": {"is_free_tier": "yes"}}, ""), ({"error": "no"}, ""), ("x", ""), (None, ""),
])
def test_only_is_free_tier_is_read_and_the_documented_cap_always_stays(answer, tier):
    conf = quota.load_limits()["providers"]["OpenRouter"]
    assert quota.account_tier(answer) == tier
    assert quota.account_limit(conf, answer) == (50 if tier == "free" else None)
    b = budget(REAL)
    assert b.account("OpenRouter", answer) is (tier == "free")
    assert b.day_limit("OpenRouter", "requests") == conf["requests_per_day"] == 50   # nothing ever raises it
    assert b.remaining("OpenRouter")["requests"] == 50
    rows = {r["provider"]: r for r in quota.summary(quota.load_limits(), quota.merge(
        quota.empty_state(), json.loads(json.dumps(b.delta())), now=NOW), NOW)}
    assert rows["OpenRouter"]["account"] == tier
    line = load("release-notice").quota_lines([rows["OpenRouter"]])[0]
    assert ("OpenRouter account is not free tier" in line) is (tier == "not-free")


def test_the_key_is_read_with_one_get_no_redirect_and_the_cap_survives_the_merge():
    seen = []

    def opener(req, timeout=0):
        seen.append((req.full_url, req.get_method(), req.headers.get("Authorization")))
        return Answer(json.dumps({"data": {"is_free_tier": True, "usage": 0}}).encode())
    conf = quota.load_limits()["providers"]["OpenRouter"]
    info = quota.read_account(conf, "k-test", opener, registry.OPENROUTER_KEY_INFO)
    assert seen == [(registry.OPENROUTER_KEY_INFO, "GET", "Bearer k-test")]
    assert quota.read_account(conf, "", opener) is None and len(seen) == 1                # no key, no call

    def broken(req, timeout=0):
        raise OSError("down")
    assert quota.read_account(conf, "k", broken) is None
    # the real opener follows no redirect: the key's header never goes to another address
    import urllib.request
    handler = [h for h in quota._no_redirects().__self__.handlers if isinstance(h, urllib.request.HTTPRedirectHandler)]
    assert handler and handler[0].redirect_request(urllib.request.Request("https://openrouter.ai/api/v1/key"), None,
                                                   302, "Found", {}, "https://elsewhere.example/") is None
    b = budget(REAL)
    b.account("OpenRouter", info)
    b.note("OpenRouter", 100, "fix")
    state = quota.merge(quota.empty_state(), json.loads(json.dumps(b.delta())), now=NOW)
    after = quota.Budget(quota.load_limits(), state, REAL, now=NOW)
    assert after.remaining("OpenRouter")["requests"] == 49 and not after.spent("OpenRouter")
    assert after.allows("OpenRouter", 100) == (True, "")


def test_the_runs_that_hold_the_key_read_the_account_and_pass_the_pending_work():
    reserve = (ROOT / "tools/autofix-reserve.py").read_text("utf-8")
    review = (ROOT / "tools/ai-review.py").read_text("utf-8")
    agent = (ROOT / "tools/autofix-agent.py").read_text("utf-8")
    for text in (reserve, review):
        assert 'account(' in text and "read_account" in text and "OPENROUTER_KEY_INFO" in text
    for text in (reserve, agent):
        assert "--quota-memory" in text and "--quota-pending" in text and "pending=quota.pending_for_run(" in text
    wf = (ROOT / ".github/workflows/autofix.yml").read_text("utf-8")
    assert wf.count('--quota-memory $RUNNER_TEMP/memory.json"; fi') == 2
    assert wf.count('--quota-pending $RUNNER_TEMP/pending"') == 2
    assert "python3 -I tools/ai-quota.py pending --repo" in wf and "pending: ${{ steps.plan.outputs.pending }}" in wf
    assert "PENDING: ${{ needs.plan.outputs.pending }}" in wf
    merge = (ROOT / ".github/workflows/automerge.yml").read_text("utf-8")
    step = merge.split("- name: AUTOMAT's memory of the fix that was merged", 1)[1]
    assert "if: always()" in step.split("run: |", 1)[0] and " closed --memory memory.json --closed " in step
    assert "pending --repo" in step and "--no-runs" in step
    am = (ROOT / "tools/automerge.py").read_text("utf-8")
    assert 'if os.environ.get("GITHUB_OUTPUT") and ref.startswith("automation/"):' in am      # every merge


def test_a_background_fix_is_deferred_by_the_reserve_chain_with_no_model_asked(tmp_path):
    reserve = load("autofix-reserve")
    work = tmp_path / "w"
    (work / ".autofix").mkdir(parents=True)
    (work / ".autofix" / "failure.md").write_text("FAILED tests/test_x.py::test_y\nE   AttributeError: x\n", "utf-8")
    (tmp_path / "prompt.md").write_text("rules", "utf-8")
    pending = tmp_path / "pending"
    pending.write_text(REAL + "\n", "utf-8")
    asked = []

    def opener(req, timeout=0):
        asked.append(req.full_url)
        if req.full_url.endswith("/api/v1/key"):
            return Answer(json.dumps({"data": {"is_free_tier": True}}).encode())
        raise AssertionError("a model was asked: %s" % req.full_url)
    env = {"GROQ_API_KEY": "g", "ZAI_API_KEY": "z", "OPENROUTER_API_KEY": "o"}
    for candidate in (DRILL, "automation/update/ci-pins"):
        status = tmp_path / "status.json"
        usage = tmp_path / "usage.json"
        asked.clear()
        assert reserve.main(["--workdir", str(work), "--prompt", str(tmp_path / "prompt.md"), "--status", str(status),
                             "--quota-limits", str(ROOT / "tools/ai-quota.json"), "--quota-usage", str(usage),
                             "--quota-pending", str(pending), "--candidate", candidate], env=env, opener=opener) == 0
        result = json.loads(status.read_text("utf-8"))
        assert result["result"] == "budget" and result["no_provider"] is True        # the work waits: deferred
        assert all("paused for real updates first" in why for why in result["budget"].values())
        assert asked == [registry.OPENROUTER_KEY_INFO]                       # only the account was read
        assert json.loads(usage.read_text("utf-8"))["calls"] == []


# =====================================================================================================
# 6. The drill's scheduler
# =====================================================================================================

def drill_info(conclusion="failure", created="2026-11-24T08:00:00Z", complete=False, state="open"):
    return {"now": "2026-11-24T12:00:00+00:00", "drills": [{
        "branch": DRILL, "pr": {"number": 9, "state": state}, "complete": complete,
        "tests_run": {"id": 4242, "conclusion": conclusion, "status": "completed", "created_at": created}}]}


def test_the_drill_starts_a_held_back_fix_again_only_when_background_work_may_run():
    open_ = {"state": "open"}
    assert drill.to_resume(drill_info(), open_, set(), False) == [(DRILL, "4242")]
    assert drill.to_resume(drill_info(), {"state": "released"}, set(), False) == [(DRILL, "4242")]
    for status in ({"state": "paused", "pending": [REAL]}, {"state": "no-room"}, {}, None):
        assert drill.to_resume(drill_info(), status, set(), False) == []
    assert drill.to_resume(drill_info(), open_, set(), True) == []                    # a fix runs now
    assert drill.to_resume(drill_info(created="2026-11-24T11:00:00Z"), open_, set(), False) == []    # too fresh
    assert drill.to_resume(drill_info("success"), open_, set(), False) == []
    assert drill.to_resume(drill_info(complete=True), open_, set(), False) == []
    assert drill.to_resume(drill_info(state="closed"), open_, set(), False) == []
    assert drill.to_resume(drill_info(), open_, {("4242", TODAY)}, False) == []          # once a day per run
    assert drill.to_resume(drill_info(), open_, {("4242", "2026-11-23")}, False) == [(DRILL, "4242")]
    # started: the automatic fix's own form of work, and a mark on the drill's issue
    calls = []

    def api(path, method="GET", data=None, **kw):
        calls.append((path, method, data))
        return {}
    assert drill.resume("o/r", [(DRILL, "4242")], api) == ["4242"]
    assert calls == [("repos/o/r/actions/workflows/autofix.yml/dispatches", "POST",
                      {"ref": "main", "inputs": {"run_id": "4242", "work": "run/4242"}})]
    body = drill.with_resumed("x\n" + drill.ISSUE_MARK % "qt-1", ["4242"], TODAY)
    assert drill.resumed_marks(body) == {("4242", TODAY)} and drill.ISSUE_MARK % "qt-1" in body
    many = body
    for n in range(30):
        many = drill.with_resumed(many, [str(n)], TODAY)
    assert len(drill.resumed_marks(many)) == drill.KEEP_MARKS
    # a fix that runs or waits: nothing is started; not known: rather not
    assert drill.autofix_busy("o/r", lambda p, *a: {"total_count": 1}) is True
    assert drill.autofix_busy("o/r", lambda p, *a: {"total_count": 0, "workflow_runs": []}) is False

    def down(path, *a):
        raise RuntimeError("down")
    assert drill.autofix_busy("o/r", down) is True


def test_the_drills_report_says_when_it_waits_for_real_updates():
    info = drill_info()
    d = info["drills"][0]
    d.update(title="Qt", breaks=[], commits=[], reviews=[], attempts=[], quota={}, checks={}, started="", head="")
    info["priority"] = {"state": "paused", "pending": [REAL]}
    text = drill.markdown(info)
    assert "lavoro di fondo" in text and "prima gli aggiornamenti veri" in text and REAL in text
    info["priority"] = {"state": "released", "pending": [REAL]}
    assert "ultima parte della loro giornata" in drill.markdown(info)
    assert "Priorità" not in drill.markdown(info, final=True)
    status = drill.priority(memory_with((REAL, 1, TODAY)), None, NOW)
    assert status["state"] == "paused" and status["pending"] == [REAL]
    assert drill.priority(None, {"days": "x"}, LATE)["state"] == "open"
    # with the repository: an open real update whose checks fail pauses the drill, and a memory row whose pull
    # request was closed does not
    api = FakePRs([("automation/update/darkreader", sha(2))], {sha(2): [{"status": "completed",
                                                                        "conclusion": "failure"}]},
                  closed={REAL})
    status = drill.priority(memory_with((REAL, 1, TODAY)), None, NOW, "o/r", api)
    assert status["state"] == "paused" and status["pending"] == ["automation/update/darkreader"]

    def down(path, *a):
        raise RuntimeError("down")
    # not read: unknown, the drill pauses (review H3: fail closed), also with nothing in the memory
    assert drill.priority(memory_with((REAL, 1, TODAY)), None, NOW, "o/r", down)["pending"] == [REAL, quota.UNKNOWN]
    status = drill.priority(None, None, LATE, "o/r", down)
    assert status["state"] == "paused" and status["pending"] == [quota.UNKNOWN] and "could not be read" in status["why"]


def test_the_drill_workflow_says_it_and_keeps_its_permissions():
    wf = (ROOT / ".github/workflows/automat-drill.yml").read_text("utf-8")
    assert "Real updates first" in wf and "actions: write" in wf and "contents: write" in wf
    assert '"41 */3 * * *"' in wf


def test_the_documents_say_it():
    doc = (ROOT / "docs/MAINTENANCE.md").read_text("utf-8")
    section = doc.split("### Real updates first, and every day's free quota used (2026-11-24)", 1)[1].split("\n## ", 1)[0]
    section = " ".join(section.split())
    for word in ("pending_days", "release_hours", "maintenance_window", "--quota-memory", "--quota-pending",
                 "/api/v1/key", "shared_free_models", "Not verified", "automation/update/drill-*",
                 "automation/update/ci-*", "may use all of the free quota", "goes to self-improvement",
                 "automation/update/security-*", "tests/test_automat_priority.py", "run/<id>"):
        assert word in section, word
    roadmap = (ROOT / "ROADMAP.md").read_text("utf-8")
    assert "AUTOMAT, block 1" in roadmap and "AUTOMAT block 1 (2026-11-24" in roadmap.split("## Status", 1)[1]


# =====================================================================================================
# 7. The second review of 2026-11-24
# =====================================================================================================

def at(hour, minute=0, day=24):
    return dt.datetime(2026, 11, day, hour, minute, tzinfo=dt.timezone.utc)


def test_an_unverified_reset_never_opens_the_background_before_the_last_hours_of_the_providers_day():
    """H1: Antigravity's day ends at 08:00 UTC (midnight in California, not verified): drills at 12:05 and 15:00
    UTC must not take its twenty requests a security fix needs at 06:30 the next morning; a UTC provider is not
    emptied at 12:01 with twelve hours of its day left."""
    limits = quota.load_limits()
    assert not limits["providers"]["Antigravity"]["reset"]["verified"]
    for when in (at(12, 5), at(15), at(23), at(6, 30, 25), at(7, 59, 25)):
        ok, why = quota.Budget(limits, None, DRILL, now=when).allows("Antigravity", 0, requests=10)
        assert ok is False, when
        assert "Antigravity" not in quota.background_status(limits, quota.empty_state(), None, when)["providers"]
    # its last hours (05:00-08:00 UTC) fall in the real day's maintenance: an unverified reset waits for a person
    assert "not verified" in quota.Budget(limits, None, DRILL, now=at(6, 0, 25)).leftover_window("Antigravity")[1]
    assert quota.Budget(limits, None, REAL, now=at(6, 30, 25)).allows("Antigravity", 0, requests=10) == (True, "")
    # a UTC provider: not at 12:01, only in its last three hours
    for name in ("Groq", "Z.AI", "OpenRouter"):
        assert quota.Budget(limits, None, DRILL, now=at(12, 1)).leftover_window(name)[0] is False, name
        assert quota.Budget(limits, None, DRILL, now=at(21, 30)).leftover_window(name)[0] is True, name
    # an unverified provider's own header saying its day ends soon never opens it earlier than the data file
    b = quota.Budget(limits, None, DRILL, now=at(12, 1))
    b.note("Groq", 10, "review", headers={"x-ratelimit-limit-requests": "1000", "x-ratelimit-remaining-requests": "990",
                                           "x-ratelimit-reset-requests": "2m59.56s"})
    assert b.leftover_window("Groq")[0] is False
    # the window is data: release_hours of tools/ai-quota.json
    wide = quota.load_limits()
    wide["priority"]["release_hours"] = 12
    assert quota.Budget(wide, None, DRILL, now=at(12, 1)).leftover_window("Groq")[0] is True


def test_a_long_lived_branch_is_never_closed_and_a_closed_row_is_marked_never_deleted():
    """H2: automation/autofix-main and automation/daily-maintenance had closed pull requests and none is open
    while their fix fails before it publishes: they stay pending; a row of another branch is only marked, so the
    count of failures in a row (tools/automat-help.py) stays."""
    memory = load("automat-memory")
    assert memory.LONG_LIVED == quota.LONG_LIVED
    long_lived = ("automation/autofix-main", "automation/daily-maintenance")
    mem = memory_with(*[(ref, 3, TODAY) for ref in long_lived + ("automation/update/adblock",)])
    api = FakePRs([], {}, closed=set(long_lived) | {"automation/update/adblock"})
    prs = quota.gather_prs("o/r", api, mem, None, NOW, runs=False)
    assert prs["closed"] == ["automation/update/adblock"]
    assert quota.pending_all(mem, None, NOW, prs) == sorted(long_lived)
    assert quota.background_status(quota.load_limits(), quota.empty_state(), mem, LATE, prs=prs)["state"] == "paused"
    # a pull request closed BEFORE the row's last failure: the work goes on (a new candidate fails again)
    old = FakePRs([], {}, closed={"automation/update/adblock"}, closed_at="2026-11-23T10:00:00Z")
    assert quota.gather_prs("o/r", old, mem, None, NOW, runs=False)["closed"] == []
    # no row, or pull requests that cannot be read: not closed
    assert quota.closed_branches("o/r", api, ["automation/update/adblock"], None) == []

    def down(path, *a):
        raise RuntimeError("down")
    assert quota.closed_branches("o/r", down, ["automation/update/adblock"], mem) == []
    # the memory: marked, never deleted; never a long-lived branch
    memory.closed(mem, list(long_lived) + ["automation/update/adblock"], now=NOW)
    for ref in long_lived + ("automation/update/adblock",):
        assert memory.consecutive(mem, ref) == ("s", 3), ref
    assert mem["streak"]["automation/update/adblock"]["closed"] == TODAY
    assert not any("closed" in mem["streak"][ref] for ref in long_lived)
    assert quota.pending_work(mem, None, NOW) == sorted(long_lived)
    # a long-lived row with a mark (by hand, an old file) is still pending
    mem["streak"]["automation/autofix-main"]["closed"] = TODAY
    assert "automation/autofix-main" in quota.pending_work(mem, None, NOW)
    # failing again after the close clears the mark: pending again, and the row goes on counting
    memory.note(mem, "automation/update/adblock", "s", "tests-failed", provider="Groq", now=NOW)
    assert "automation/update/adblock" in quota.pending_work(mem, None, NOW)
    assert memory.consecutive(mem, "automation/update/adblock") == ("s", 4)
    wf = (ROOT / ".github/workflows/automerge.yml").read_text("utf-8")
    assert "memory.pop" not in (ROOT / "tools/automat-memory.py").read_text("utf-8").split("def closed(", 1)[1][:900]
    assert " closed --memory memory.json --closed " in wf


def test_an_unknown_list_of_pending_work_pauses_the_background_and_never_real_work(tmp_path, monkeypatch):
    """H3: when the plan cannot read GitHub, the list is "unknown" (or missing): background work pauses, real
    work and security fixes never wait for it."""
    plan = tmp_path / "pending"
    plan.write_text("unknown\n", "utf-8")
    pending = quota.pending_for_run(None, str(plan))
    assert pending == [quota.UNKNOWN]
    for ref in (DRILL, "automation/update/ci-pins"):
        ok, why = budget(ref, now=LATE, pending=pending).allows("Groq", 2000)
        assert ok is False and "could not be read" in why, ref
    for ref in (REAL, "automation/update/security-x", "automation/autofix-main"):
        assert budget(ref, now=LATE, pending=pending).allows("Groq", 2000) == (True, ""), ref
    status = quota.background_status(quota.load_limits(), quota.empty_state(), None, LATE, pending=pending)
    assert status["state"] == "paused"
    # the command of the plan: GitHub not read -> "unknown" and a failure, never an empty list
    def down(path):
        raise RuntimeError("HTTP 502")
    monkeypatch.setattr(quota, "gh_api", down)
    out = io.StringIO()
    import contextlib
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        assert quota.main(["pending", "--repo", "o/r"]) == 1
    assert out.getvalue().strip() == quota.UNKNOWN
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        assert quota.main(["pending", "--repo", "o/r", "--out", str(tmp_path / "p.json")]) == 1
    assert not (tmp_path / "p.json").exists()                        # nothing is closed on a guess
    # the workflow: an error is "unknown", nothing pending is "none", and a missing output is "unknown"
    wf = (ROOT / ".github/workflows/autofix.yml").read_text("utf-8")
    plan_step = wf.split("python3 -I tools/ai-quota.py pending --repo", 1)[1][:700]
    assert '2> /dev/null || true' not in plan_step.split("fi\n", 1)[0]
    assert 'echo "pending=${pending:-none}" >> "$GITHUB_OUTPUT"' in plan_step
    assert 'echo "pending=unknown" >> "$GITHUB_OUTPUT"' in plan_step
    assert 'none) : > "$RUNNER_TEMP/pending" ;;' in wf and '""|unknown) echo unknown > "$RUNNER_TEMP/pending" ;;' in wf


def test_a_lone_real_update_may_use_all_of_a_provider_and_two_pending_share_it():
    """M1 (the owner, 2026-11-24: no fixed share for real updates): the share of one candidate holds only while
    another security fix or real update is pending at the same time."""
    sec = "automation/update/security-x"
    limit = quota.load_limits()["providers"]["Antigravity"]["requests_per_day"]
    session = quota.load_limits()["providers"]["Antigravity"]["session_requests"]
    lone = quota.Budget(quota.load_limits(), None, sec, now=NOW, pending=[sec, quota.UNKNOWN])
    for _ in range(limit // session):
        assert lone.allows("Antigravity", 0, requests=session) == (True, "")
        lone.note("Antigravity", 0, "fix", requests=session)
    assert "used up" in lone.allows("Antigravity", 0, requests=session)[1]        # only the provider's own quota
    # with another real update pending at the same time: the second session of the same candidate waits
    two = quota.Budget(quota.load_limits(), None, sec, now=NOW, pending=[sec, REAL])
    assert two.allows("Antigravity", 0, requests=session) == (True, "")
    two.note("Antigravity", 0, "fix", requests=session)
    ok, why = two.allows("Antigravity", 0, requests=session)
    assert ok is False and "already used its share" in why and "while another real update is pending" in why
    other = quota.Budget(quota.load_limits(), two.state, REAL, now=NOW, pending=[sec, REAL])
    assert other.allows("Antigravity", 0, requests=session) == (True, "")             # the other one gets its half
    # the candidate's own id (without the prefix) is not "another one"
    assert quota.Budget(quota.load_limits(), two.state, "security-x", now=NOW, pending=[sec]).allows(
        "Antigravity", 0, requests=session) == (True, "")


def test_only_the_newest_run_of_each_workflow_decides_whether_a_pull_request_is_pending():
    """L1: a cancelled or superseded run of the same workflow on the head commit no longer keeps it pending."""
    def run(wf, conclusion, created, status="completed"):
        return {"workflow_id": wf, "status": status, "conclusion": conclusion, "created_at": created}
    api = FakePRs([("automation/update/adblock", sha(1)), ("automation/update/darkreader", sha(2)),
                   ("automation/update/pyqt6", sha(3))],
                  {sha(1): [run(1, "success", "2026-11-24T10:00:00Z"), run(1, "cancelled", "2026-11-24T09:00:00Z"),
                            run(2, "success", "2026-11-24T09:30:00Z")],
                   sha(2): [run(1, "cancelled", "2026-11-24T08:00:00Z"), run(1, "failure", "2026-11-24T10:00:00Z")],
                   sha(3): [run(1, "success", "2026-11-24T08:00:00Z"), run(1, None, "2026-11-24T10:00:00Z",
                                                                        "in_progress")]})
    assert quota.pending_from_prs("o/r", api)["pending"] == ["automation/update/darkreader", "automation/update/pyqt6"]
    assert [r["conclusion"] for r in quota.latest_runs([run(1, "cancelled", "1"), run(1, "success", "2")])] == \
        ["success"]
    # runs that name no workflow each count
    assert len(quota.latest_runs([{"conclusion": "success"}, {"conclusion": "failure"}])) == 2


def test_the_memory_of_a_merge_is_written_in_the_memorys_queue_and_retried_never_lost_in_silence():
    """M2: the merge workflow writes AUTOMAT's memory in the queue of the automatic fix's own record
    (automat-memory), makes the record again from the newest commit when the branch moved, and warns when it
    could not."""
    import yaml
    wf = yaml.safe_load((ROOT / ".github/workflows/automerge.yml").read_text("utf-8"))
    job = wf["jobs"]["memory"]
    assert job["needs"] == "merge" and job["concurrency"] == {"group": "automat-memory", "cancel-in-progress": False}
    assert job["permissions"] == {"contents": "write", "pull-requests": "read"}
    assert wf["jobs"]["merge"]["outputs"]["merged"] == "${{ steps.merge.outputs.merged }}"
    assert not any("automat-memory" in str(s) for s in wf["jobs"]["merge"]["steps"])
    run = job["steps"][-1]["run"]
    assert "for attempt in 1 2 3 4 5; do" in run and "|| return 1" in run and "record || code=$?" in run
    assert run.count("::warning title=AUTOMAT's memory::") == 2
    assert "COMPONENT: ${{ needs.merge.outputs.merged }}" in (ROOT / ".github/workflows/automerge.yml").read_text()
    autofix = yaml.safe_load((ROOT / ".github/workflows/autofix.yml").read_text("utf-8"))
    assert autofix["jobs"]["remember"]["concurrency"]["group"] == job["concurrency"]["group"]
