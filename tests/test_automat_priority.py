"""Real updates first (the owner's decision of 2026-11-24): every day's free quota used, above all for real updates.

In the owner's words: "use the free AIs every day, always when needed, above all for real updates; what is
left goes to self-evolution, drills etc.". The proofs, all offline (no AI, no network, a fake GitHub):

- the order: security fixes, then the updates of what ships, then the CI's, then background work, by the
  branch (tools/ai-quota.py priority_of); the daily check starts its waiting work in that order;
- the reserve: a share of each provider's day stays kept for classes 1 and 2; classes 3 and 4 use only
  what is above it, classes 1 and 2 may use everything;
- the pause: background work (the drill) waits by itself while a real update is pending or retrying
  (AUTOMAT's memory), and its fix is not started when its reviews would have to take the reserve;
- the end of the day: in the last hours before a provider's own reset what is left above a small margin
  goes to the background too, even while real work is pending (nothing wasted);
- OpenRouter: all its ":free" models are one budget of the account, read from GET /api/v1/key when the
  key is there, else the documented default; the read never makes the budget say "nothing left";
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
    assert 0.5 <= data["reserve_share"] < 1 and 0 < data["release_margin"] <= 0.2 and 1 <= data["release_hours"] <= 6
    assert "2026-11-24" in data["source"] and "drill" in data["about"]
    bad = quota.load_priority({"background": ["automation/update/", "automation/", "automation/builder/",
                                              "automation/update/security-", "automation/daily-maintenance"],
                               "ci": ["automation/update/"], "reserve_share": 7, "release_margin": -1,
                               "release_hours": "3", "pending_days": 0})
    assert bad == quota.load_priority(None) == quota.PRIORITY            # each refused: the defaults
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
# 2. The reserve of classes 1 and 2
# =====================================================================================================

def test_background_and_ci_use_only_what_is_above_the_reserve_and_real_work_everything():
    limit = quota.load_limits()["providers"]["Groq"]["requests_per_day"]
    keep = int(limit * quota.load_limits()["priority"]["reserve_share"])
    # nothing used yet: the background may use the part above the reserve
    assert budget(DRILL).allows("Groq", 2000) == (True, "")
    above = used("Groq", limit - keep - 1, klass=quota.BACKGROUND)
    assert budget(DRILL, above).allows("Groq", 2000) == (True, "")
    above = used("Groq", limit - keep, klass=quota.BACKGROUND)
    ok, why = budget(DRILL, above).allows("Groq", 2000)
    assert ok is False and "the reserve for security fixes and real updates" in why and "class 4" in why
    ok, why = budget("automation/update/ci-pins", above).allows("Groq", 2000)
    assert ok is False and "class 3" in why                              # the CI's updates too
    # a real update and a security fix take from the reserve
    assert budget(REAL, above).allows("Groq", 2000) == (True, "")
    assert budget("automation/update/security-sandbox", above).allows("Groq", 2000) == (True, "")
    # what real work already used counts against its own reserve: the rest is the background's
    real = used("Groq", keep, klass=quota.UPDATE)
    assert budget(DRILL, real).reserve_left("Groq", "requests") == 0
    assert budget(DRILL, real).allows("Groq", 2000) == (True, "")
    # tokens are kept the same way
    tokens = quota.load_limits()["providers"]["Groq"]["tokens_per_day"]
    full = used("Groq", 1, tokens - int(tokens * 0.6) - 1000, klass=quota.BACKGROUND)
    assert "tokens" in budget(DRILL, full).allows("Groq", 2000)[1]


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


def test_background_pauses_by_itself_while_real_work_is_pending_and_real_work_never_does():
    pending = quota.pending_work(memory_with((REAL, 1, TODAY)), None, NOW)
    ok, why = budget(DRILL, pending=pending).allows("Groq", 2000)
    assert ok is False and "paused for real updates first" in why and REAL in why
    assert budget(DRILL, pending=pending).pick(["Groq", "Z.AI", "OpenRouter"], 2000) == []
    # a review of a fix already made is not paused (the quota of the fix is not wasted); the reserve still holds
    assert budget(DRILL, pending=pending).allows("Groq", 2000, "review") == (True, "")
    # the CI's updates do not pause; real work and security fixes never do
    assert budget("automation/update/ci-pins", pending=pending).allows("Groq", 2000) == (True, "")
    assert budget(REAL, pending=pending).allows("Groq", 2000) == (True, "")
    assert budget("automation/update/security-y", pending=pending).allows("Groq", 2000) == (True, "")
    # background work named as pending is no reason to pause
    assert budget(DRILL, pending=[DRILL, "automation/update/ci-pins"]).allows("Groq", 2000) == (True, "")


def test_a_background_fix_waits_when_its_reviews_would_have_to_take_the_reserve():
    state = {"schema": 1, "days": {TODAY: {"providers": {}}}}
    for name in ("Z.AI", "OpenRouter", "Antigravity"):
        limit = quota.load_limits()["providers"][name]["requests_per_day"]
        state["days"][TODAY]["providers"][name] = {
            "requests": limit - int(limit * 0.6), "tokens": 0,
            "classes": {"4": {"requests": limit - int(limit * 0.6), "tokens": 0}}}
    ok, why = budget(DRILL, state).allows("Groq", 2000)
    assert ok is False and "the reviewers' reserve" in why
    assert budget(REAL, state).allows("Groq", 2000) == (True, "")             # real work: its reviewers may use all


# =====================================================================================================
# 4. The end of a provider's day: nothing wasted
# =====================================================================================================

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


def test_in_the_last_hours_what_is_left_above_the_margin_goes_to_the_background():
    late = dt.datetime(2026, 11, 24, 22, 0, tzinfo=dt.timezone.utc)       # two hours before Groq's reset
    pending = [REAL]
    limit = quota.load_limits()["providers"]["Groq"]["requests_per_day"]
    margin = int(limit * quota.load_limits()["priority"]["release_margin"])
    b = budget(DRILL, now=late, pending=pending)
    assert b.release_window("Groq")[0] is True and b.release_window("Antigravity")[0] is False
    assert b.allows("Groq", 2000) == (True, "")                          # released, although real work is pending
    assert "paused" in b.allows("Antigravity", 0, requests=10)[1]        # its own day still has ten hours
    assert b.reserve_left("Groq", "requests") == margin
    # the margin stays kept for real work arriving late
    nearly = used("Groq", limit - margin, klass=quota.BACKGROUND)
    ok, why = budget(DRILL, nearly, now=late, pending=pending).allows("Groq", 2000)
    assert ok is False and "the reserve" in why
    assert budget(REAL, nearly, now=late, pending=pending).allows("Groq", 2000) == (True, "")
    # earlier the same day the reserve holds
    assert budget(DRILL, used("Groq", limit - 2 * margin, klass=quota.BACKGROUND)).allows("Groq", 2000)[0] is False


def test_the_signing_notice_shows_what_stays_kept_for_real_updates():
    state = used("Groq", 30, klass=quota.UPDATE)
    rows = {r["provider"]: r for r in quota.summary(quota.load_limits(), state, NOW)}
    assert rows["Groq"]["real_requests"] == 30 and rows["Groq"]["reserve_requests"] == 120 - 30
    assert rows["Groq"]["reset_verified"] is False
    lines = load("release-notice").quota_lines([rows["Groq"]])
    assert "Tenute per sicurezza e aggiornamenti veri: 90 richieste (già usate da loro oggi: 30)." in lines[0]


def test_background_status_says_open_paused_released_or_no_room():
    limits = quota.load_limits()
    mem = memory_with((REAL, 1, TODAY))
    assert quota.background_status(limits, quota.empty_state(), None, NOW)["state"] == "open"
    paused = quota.background_status(limits, quota.empty_state(), mem, NOW)
    assert paused["state"] == "paused" and paused["pending"] == [REAL] and "real updates first" in paused["why"]
    late = quota.background_status(limits, quota.empty_state(), mem, dt.datetime(2026, 11, 24, 23, tzinfo=dt.timezone.utc))
    assert late["state"] == "released" and "Groq" in late["providers"] and "Antigravity" not in late["providers"]
    spent = quota.empty_state()
    for name in quota.NAMES:
        quota._prov(spent, TODAY, name)["spent"] = "429"
    assert quota.background_status(limits, spent, None, NOW)["state"] == "no-room"
    # the class of a branch, for the logs
    out = io.StringIO()
    import contextlib
    with contextlib.redirect_stdout(out):
        assert quota.main(["priority", "--candidate", DRILL]) == 0
        assert quota.main(["priority", "--candidate", "automation/update/security-z"]) == 0
    assert "class=4\nwhat=background\nbackground=open" in out.getvalue() and "class=1" in out.getvalue()


# =====================================================================================================
# 5. OpenRouter: one budget for all its free models
# =====================================================================================================

class Answer(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_openrouters_free_models_share_one_budget_of_the_account():
    conf = json.loads((ROOT / "tools/ai-quota.json").read_text("utf-8"))["providers"]["OpenRouter"]
    assert conf["shared_free_models"] is True and conf["account"]["url"] == registry.OPENROUTER_KEY_INFO
    assert conf["account"]["free_tier_requests_per_day"] == conf["requests_per_day"]
    # every :free model is the one provider "OpenRouter": two models' calls count against one cap
    b = budget(REAL)
    limit = b.day_limit("OpenRouter", "requests")
    for _model in registry.RESERVES[-1][4]:
        assert registry.is_free_model("OpenRouter", _model)
        b.note("OpenRouter", 100, "review")
    assert b.remaining("OpenRouter")["requests"] == limit - len(registry.RESERVES[-1][4])
    assert set(quota.NAMES) == {"Antigravity", "Groq", "Z.AI", "OpenRouter"}     # no model is a budget of its own


@pytest.mark.parametrize("answer, limit", [
    ({"data": {"is_free_tier": True, "usage": 0, "limit": None}}, 50),
    ({"data": {"is_free_tier": True, "rate_limit": {"requests": 200, "interval": "1d"}}}, 200),
    ({"data": {"requests_per_day": 5000}}, 1000),                        # never above the file's ceiling
    ({"data": {"is_free_tier": False, "usage": 3.5, "limit": 10}}, None),    # credits are money, never requests
    ({"data": {"rate_limit": {"requests": 20, "interval": "10s"}}}, None),
    ({"error": "no"}, None), ("x", None), (None, None),
])
def test_the_accounts_daily_cap_is_read_from_the_key_or_the_default_stays(answer, limit):
    conf = quota.load_limits()["providers"]["OpenRouter"]
    assert quota.account_limit(conf, answer) == limit
    b = budget(REAL)
    assert b.account("OpenRouter", answer) is bool(limit)
    assert b.day_limit("OpenRouter", "requests") == (limit or conf["requests_per_day"])
    assert b.remaining("OpenRouter")["requests"] == (limit or conf["requests_per_day"])


def test_the_key_is_read_with_one_get_and_the_cap_survives_the_merge_without_reading_as_spent():
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
    b = budget(REAL)
    b.account("OpenRouter", info)
    b.note("OpenRouter", 100, "fix")
    state = quota.merge(quota.empty_state(), json.loads(json.dumps(b.delta())), now=NOW)
    after = quota.Budget(quota.load_limits(), state, REAL, now=NOW)
    assert after.remaining("OpenRouter")["requests"] == 49 and not after.spent("OpenRouter")
    assert after.allows("OpenRouter", 100) == (True, "")


def test_the_runs_that_hold_the_key_read_the_account_and_pass_the_memory():
    reserve = (ROOT / "tools/autofix-reserve.py").read_text("utf-8")
    review = (ROOT / "tools/ai-review.py").read_text("utf-8")
    agent = (ROOT / "tools/autofix-agent.py").read_text("utf-8")
    for text in (reserve, review):
        assert 'account(' in text and "read_account" in text and "OPENROUTER_KEY_INFO" in text
    for text in (reserve, agent):
        assert "--quota-memory" in text and "pending=quota.pending_work(" in text
    wf = (ROOT / ".github/workflows/autofix.yml").read_text("utf-8")
    assert wf.count('--quota-memory $RUNNER_TEMP/memory.json"; fi') == 2


def test_a_background_fix_is_deferred_by_the_reserve_chain_with_no_model_asked(tmp_path):
    reserve = load("autofix-reserve")
    work = tmp_path / "w"
    (work / ".autofix").mkdir(parents=True)
    (work / ".autofix" / "failure.md").write_text("FAILED tests/test_x.py::test_y\nE   AttributeError: x\n", "utf-8")
    (tmp_path / "prompt.md").write_text("rules", "utf-8")
    mem = tmp_path / "memory.json"
    mem.write_text(json.dumps(memory_with((REAL, 1, dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")))), "utf-8")
    asked = []

    def opener(req, timeout=0):
        asked.append(req.full_url)
        if req.full_url.endswith("/api/v1/key"):
            return Answer(json.dumps({"data": {"is_free_tier": True}}).encode())
        raise AssertionError("a model was asked: %s" % req.full_url)
    env = {"GROQ_API_KEY": "g", "ZAI_API_KEY": "z", "OPENROUTER_API_KEY": "o"}
    status = tmp_path / "status.json"
    usage = tmp_path / "usage.json"
    assert reserve.main(["--workdir", str(work), "--prompt", str(tmp_path / "prompt.md"), "--status", str(status),
                         "--quota-limits", str(ROOT / "tools/ai-quota.json"), "--quota-usage", str(usage),
                         "--quota-memory", str(mem), "--candidate", DRILL], env=env, opener=opener) == 0
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
    assert drill.priority(None, {"days": "x"}, NOW)["state"] == "open"


def test_the_drill_workflow_says_it_and_keeps_its_permissions():
    wf = (ROOT / ".github/workflows/automat-drill.yml").read_text("utf-8")
    assert "Real updates first" in wf and "actions: write" in wf and "contents: write" in wf
    assert '"41 */3 * * *"' in wf


def test_the_documents_say_it():
    doc = (ROOT / "docs/MAINTENANCE.md").read_text("utf-8")
    section = doc.split("### Real updates first, and every day's free quota used (2026-11-24)", 1)[1].split("\n## ", 1)[0]
    for word in ("reserve_share", "pending_days", "release_hours", "release_margin", "--quota-memory", "/api/v1/key",
                 "shared_free_models", "Not verified", "automation/update/drill-*", "automation/update/ci-*",
                 "automation/update/security-*", "tests/test_automat_priority.py", "run/<id>"):
        assert word in section, word
    roadmap = (ROOT / "ROADMAP.md").read_text("utf-8")
    assert "AUTOMAT, block 1" in roadmap and "AUTOMAT block 1 (2026-11-24" in roadmap.split("## Status", 1)[1]
