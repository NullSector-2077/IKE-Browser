"""WP8 and WP9 of the automatic maintenance (2026-11-22), offline.

- tools/filter-lists.py: every finding of the filter lists in one of five
  classes, by written rules, on recorded real rules
  (tests/data/filter-lists-classes.txt, tests/data/filter-lists-snapshot.txt);
  an unknown scriptlet becomes an AI plan on an isolated branch, a YouTube rule
  needs a person;
- tools/check-autofix-patch.py --lists: the AI analysis may change only
  I.K.E.'s adapter (never the lists, the bundled resources, YouTube's code or
  the tests, never less protection);
- tools/provider-check.py and the reserves: only free providers (OpenRouter's
  ":free" models priced zero, no billing error, no cost in an answer), Gemini
  asked too, no key ever written;
- tools/ai-work.py in the maintenance ledger: no free provider gives
  "retry-later", then a resume, then the cap and the owner told once.

No network: every HTTP answer is a stand-in."""

import datetime as dt
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import textwrap
import urllib.error

import pytest
from conftest import APP, ROOT, needs_engine

WORKFLOWS = ROOT / ".github" / "workflows"
NOW = dt.datetime(2026, 11, 22, 5, 30, tzinfo=dt.timezone.utc)


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), ROOT / "tools" / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


lists_tool = load("filter-lists")
work_tool = load("ai-work")
registry = load("ai-providers")
guard = load("check-autofix-patch")
ledger_tool = load("maintenance-ledger")

UBO = "https://ublockorigin.github.io/uAssets/filters/filters.txt"
BADWARE = "https://ublockorigin.github.io/uAssets/filters/badware.txt"
EASY = "https://easylist.to/easylist/easylist.txt"
CLASSES = (ROOT / "tests/data/filter-lists-classes.txt").read_bytes()
SNAPSHOT = (ROOT / "tests/data/filter-lists-snapshot.txt").read_bytes()


def scriptlets():
    import sys
    if str(APP) not in sys.path:
        sys.path.insert(0, str(APP))
    import ike.scriptlets as scr
    return scr


# --- WP8: the five classes, by the written rules ------------------------------------------

# (rule, the engine's reason as recorded on 2026-11-22, list, trusted) -> (rule id, class)
RECORDED = [
    ('bild.de##+js(rpnt, script, "adBlockWallEnabled":true, "adBlockWallEnabled":false)',
     "cosmetic filter error: scriptlet args could not be parsed", "uBlock filters", True, "run-by-ike", "supported"),
    ('bild.de##+js(rpnt, script, "adBlockWallEnabled":true, "adBlockWallEnabled":false)',
     "cosmetic filter error: scriptlet args could not be parsed", "EasyList", False, "untrusted-scriptlet",
     "harmless"),
    ("wetteronline.*##^script:has-text(runCount)", "cosmetic filter error: html filtering is unsupported",
     "uBlock filters", True, "other-platform", "harmless"),
    ("@@||player.fm^$cname", "network filter error: unrecognised option", "uBlock filters - Unbreak", True,
     "exception-without-blocking", "harmless"),
    ("@@||startpage.com^$popup,domain=msn.com", "network filter error: unrecognised option",
     "uBlock filters - Unbreak", True, "exception-without-blocking", "harmless"),
    ("@@||che168.com^$xhr,removeparam=s_cid", "network filter error: removeparam with exception",
     "uBlock filters - Unbreak", True, "exception-dropped", "breaking"),
    ("@@||magyarhang.org^$shide", "network filter error: unrecognised option", "uBlock filters", True,
     "exception-dropped", "breaking"),
    ("||blogger.googleusercontent.com/img/$domain=/^main\\.uxsyplayer[a-z0-9-]+\\.click$/",
     "network filter error: unrecognised option", "uBlock filters", True, "rule-dropped", "breaking"),
    ("cmp.e24.no,cmp.minmote.no,cmp.tek.no,cmp.vg.no##button.sp_choice_type_SAVE_AND_EXIT:remove-attr(/^(aria-)?"
     "disabled$/)", "cosmetic filter error: unsupported syntax", "uBlock filters - Cookie notices", True,
     "rule-dropped", "breaking"),
    ("||reddit.com^$doc,removeparam=/web_only=/", "network filter error: removeparam regex unsupported",
     "uBlock filters - Privacy", True, "protection-dropped", "security"),
    ("||uppit.com^$document,csp=script-src 'self' 'unsafe-eval' 'unsafe-inline' data: *.cloudflare.com",
     "network filter error: csp with content type", "uBlock filters", True, "protection-dropped", "security"),
    ("*$script,3p,denyallow=googleapis.com,domain=skidrowcodexgames.com", "network filter error: unrecognised option",
     "uBlock filters", True, "protection-dropped", "security"),
    ("||bit.ly^$popup,domain=eurogamer.net", "network filter error: unrecognised option", "uBlock filters", True,
     "protection-dropped", "security"),
    ("||adslink.pw/*/api?url=http$doc,urlskip=?url", "network filter error: unrecognised option", "uBlock filters",
     True, "protection-dropped", "security"),
    ("||guildpass.one^$doc,reason=malicious", "network filter error: unrecognised option", "uBlock filters - Badware",
     True, "protective-list", "security"),
    ("||guildpass.one^$doc,reason=malicious", "network filter error: unrecognised option", "uBlock filters", True,
     "page-blocking", "security"),
    ('||youtube.com/youtubei/v1/get_watch?$xhr,1p,replace=/"adSlots"/"no_ads"/',
     "network filter error: unrecognised option", "uBlock filters", True, "youtube", "person"),
    ("youjizz.com##+js(noeval)", "cosmetic filter error: scriptlet args could not be parsed", "uBlock filters", True,
     "known-resource", "person"),
]


@pytest.mark.parametrize("rule, why, list_name, trusted, rule_id, cls", RECORDED)
def test_each_recorded_rule_has_its_class(rule, why, list_name, trusted, rule_id, cls):
    """The written rules (tools/filter-lists.py RULES) on rules recorded from
    the real lists; no engine needed: its reasons were recorded with them."""
    scr = scriptlets()
    got, _detail = lists_tool.classify_rule(rule, why, list_name, trusted, scr.Library(), scr)
    assert got == rule_id, (rule, got)
    assert lists_tool.RULE[got][1] == cls
    assert rule in CLASSES.decode()                         # a recorded rule, not one made up here


def test_the_rules_are_written_once_and_cover_five_classes():
    assert {r[1] for r in lists_tool.RULES} == set(lists_tool.CLASSES)
    assert len({r[0] for r in lists_tool.RULES}) == len(lists_tool.RULES)
    assert all(not r[2] for r in lists_tool.RULES if r[1] in ("supported", "harmless", "person"))
    assert not lists_tool.RULE["youtube"][2] and not lists_tool.RULE["known-resource"][2]
    doc = (ROOT / "docs/MAINTENANCE.md").read_text()
    for rule_id, _cls, _ai, _why in lists_tool.RULES:
        assert "`%s`" % rule_id in doc, rule_id                # the rules are written down for people too
    # the same known resources as the lists check
    check = load("check-components")
    assert lists_tool.KNOWN_UNRUN_SCRIPTLETS == check.KNOWN_UNRUN_SCRIPTLETS


def test_the_options_of_a_rule():
    assert lists_tool.options_of("||reddit.com^$doc,removeparam=/web_only=/") == ["doc", "removeparam"]
    assert lists_tool.options_of("*$script,3p,denyallow=a.com|b.com,domain=c.com") == \
        ["script", "3p", "denyallow", "domain"]
    assert lists_tool.options_of("/^https:\\/\\/x\\.com\\/a$/$script,1p,strict1p")[-1] == "strict1p"
    assert lists_tool.options_of("/ng.gif?s*&e=$image,strict3p") == ["image", "strict3p"]
    assert lists_tool.options_of("||x.com/navi/$doc,uritransform=/navi/virgo\\$1/") == ["doc", "uritransform"]
    # YouTube by its hosts and player data, not by a site that only allows it
    assert lists_tool.is_youtube("||youtube.com/watch?$xhr") and lists_tool.is_youtube("x##+js(set, ytInitialData, 1)")
    assert not lists_tool.is_youtube("*$frame,denyallow=facebook.com|youtube.com,domain=foxseotools.com")
    assert not lists_tool.is_youtube("@@||ga.com/a.js$script,redirect-rule,domain=youtube.videodeck.net")


def _lists_info():
    """A lists report as tools/check-components.py --filter-lists writes it."""
    scr_ = [{"name": "uBlock filters", "state": "ok", "trusted": True, "group": "ads", "network": 100,
             "cosmetic": 100, "unread_share": 0.02, "scriptlets": {"rules": 5},
             "unread": [["error", "||bit.ly^$popup,domain=eurogamer.net", "network filter error: unrecognised option"],
                        ["error", "wetteronline.*##^script:has-text(runCount)",
                         "cosmetic filter error: html filtering is unsupported"]]}]
    return {"state": "findings", "lists": scr_, "findings": [], "engine": {"built": True, "backend": "adblock"},
            "unknown_scriptlets": {
                "no-such-scriptlet": {"count": 2, "lists": ["uBlock filters"], "example":
                                      "other.example##+js(no-such-scriptlet, x)", "known": False},
                "noeval": {"count": 29, "lists": ["uBlock filters"], "example": "youjizz.com##+js(noeval)",
                           "known": True},
                "yt-ads-x": {"count": 1, "lists": ["uBlock filters"],
                             "example": "www.youtube.com##+js(yt-ads-x, playerResponse.adPlacements)"}}}


def test_the_findings_of_a_lists_report_in_five_classes():
    result = lists_tool.classify(_lists_info())
    by = {f["rule"]: f for f in result["findings"]}
    assert by["unknown-scriptlet"]["class"] == "breaking" and by["unknown-scriptlet"]["ai"]
    assert by["unknown-scriptlet"]["count"] == 2 and by["unknown-scriptlet"]["detail"] == "no-such-scriptlet"
    assert by["known-resource"]["class"] == "person" and not by["known-resource"]["ai"]
    assert by["youtube"]["class"] == "person" and by["youtube"]["youtube"] and not by["youtube"]["ai"]
    assert by["protection-dropped"]["class"] == "security" and by["protection-dropped"]["detail"] == "option popup"
    assert by["other-platform"]["class"] == "harmless"
    assert result["counts"]["supported"] == 205
    # the same lists twice: the same findings (keys are stable, for the ledger)
    assert lists_tool.classify(_lists_info()) == result
    # list-level findings: a list that is no list, an engine that does not build,
    # a quarter unread, and an unread share risen since the day before
    info = _lists_info()
    info["lists"].append({"name": "Broken", "state": "unusable"})
    info["lists"].append(dict(info["lists"][0], name="Half", unread_share=0.31, unread=[]))
    info["lists"].append(dict(info["lists"][0], name="Rising", unread_share=0.12, unread=[]))
    info["engine"] = {"built": False, "backend": "adblock"}
    result = lists_tool.classify(info, baseline={"Rising": 0.02, "uBlock filters": 0.02})
    rules = {f["rule"]: f for f in result["findings"]}
    assert rules["list-unusable"]["class"] == "person"
    assert rules["engine"]["class"] == rules["unread-share"]["class"] == rules["share-rise"]["class"] == "breaking"
    assert not any(rules[r]["ai"] for r in ("engine", "unread-share", "share-rise", "list-unusable"))
    assert "Rising: 2.0% -> 12.0%" in rules["share-rise"]["detail"]
    md = lists_tool.markdown(result)
    assert "possible security regression" in md and "needs a person" in md


@needs_engine
def test_the_recorded_snapshots_through_the_real_check():
    """The real engine and library on the recorded snapshots: every class is
    found, each rule where the written rules put it."""
    check = load("check-components")
    pages = {UBO: CLASSES + b"\n" + SNAPSHOT, BADWARE: CLASSES, EASY: CLASSES}
    lists = [{"name": "uBlock filters", "group": "ads", "url": UBO},
             {"name": "uBlock filters - Badware", "group": "ads", "url": BADWARE},
             {"name": "EasyList", "group": "ads", "url": EASY}]

    def get(url):
        if url not in pages:
            raise OSError("unreachable")
        return pages[url]
    info = check.check_filter_lists(APP, get=get, lists=lists)
    assert info["engine"]["built"], info["engine"]
    assert [r["trusted"] for r in info["lists"]] == [True, True, False]
    assert all("unread" in r and len(r["examples"]) <= check.LIST_EXAMPLES for r in info["lists"])
    result = lists_tool.classify(info)
    classes = {f["class"] for f in result["findings"]}
    assert classes == {"supported", "harmless", "breaking", "security", "person"}, classes

    def where(rule, list_name):
        found = [f for f in result["findings"] if any(e["rule"] == rule and e["list"] == list_name
                                                      for e in f["examples"])]
        return {(f["rule"], f["class"]) for f in found}
    assert ("protective-list", "security") in where("||guildpass.one^$doc,reason=malicious", "uBlock filters - Badware")
    assert ("page-blocking", "security") in where("||guildpass.one^$doc,reason=malicious", "uBlock filters")
    rpnt = 'bild.de##+js(rpnt, script, "adBlockWallEnabled":true, "adBlockWallEnabled":false)'
    assert ("run-by-ike", "supported") in where(rpnt, "uBlock filters")
    assert ("untrusted-scriptlet", "harmless") in where(rpnt, "EasyList")
    youtube = [f for f in result["findings"] if f["youtube"]]
    assert youtube and all(f["class"] == "person" and not f["ai"] for f in youtube)
    assert any(f["rule"] == "known-resource" and f["detail"] == "noeval" for f in result["findings"])


# --- WP8: an AI plan on an isolated branch, never for YouTube --------------------------------

def _decide_regex():
    text = (WORKFLOWS / "autofix.yml").read_text()
    return re.search(r"grep -Eq '(\^\(lists/[^']+)'", text).group(1)


def test_an_unknown_scriptlet_becomes_an_ai_plan_on_an_isolated_branch():
    info = _lists_info()
    key = "lists/unknown-scriptlet/no-such-scriptlet@breaking"
    work = "lists/2026-11-22/" + key
    # the work id passes the workflow's own check and the queue's
    assert re.fullmatch(_decide_regex(), work) and work_tool.WORK_ID.match(work)
    outputs, failure, recorded = lists_tool.plan(info, work, "abc123main")
    assert outputs["action"] == "fix" and outputs["kind"] == "lists" and outputs["mode"] == "lists"
    assert outputs["push_branch"] == "automation/update/lists-2026-11-22" != "main"
    assert outputs["checkout"] == "abc123main" and outputs["attempt"] == "1" and outputs["allow_adblock"] == "true"
    assert outputs["recorded"] == "tests/data/lists-recorded/2026-11-22-breaking-unknown-scriptlet-no-such-scriptlet.txt"
    assert re.fullmatch(r"tests/data/lists-recorded/[0-9]{4}-[0-9]{2}-[0-9]{2}-[a-z0-9.-]+\.txt", outputs["recorded"])
    assert "other.example##+js(no-such-scriptlet, x)" in failure and "other.example##+js(no-such-scriptlet, x)" in recorded
    for path in ("ike/scriptlets.py", "ike/blocker.py", "ike-adblock/src/lib.rs"):
        assert path in failure
    assert "Never touch YouTube's ad blocking" in failure and "Never weaken blocking" in failure
    assert "Do not write tests" in failure
    # the branch is kept: a later attempt starts from its tip, at most MAX_ATTEMPTS
    outputs, _f, _r = lists_tool.plan(info, work, "abc123main", branch_tip="tip456", attempts=1)
    assert outputs["checkout"] == "tip456" and outputs["attempt"] == "2" and outputs["push_tip"] == "tip456"
    outputs, _f, _r = lists_tool.plan(info, work, "abc123main", branch_tip="tip456", attempts=2)
    assert outputs["action"] == "issue"
    # a finding that is gone: nothing to do
    info["unknown_scriptlets"].pop("no-such-scriptlet")
    outputs, _f, _r = lists_tool.plan(info, work, "abc123main")
    assert outputs["action"] == "skip" and "no longer reported" in outputs["reason"]
    # the workflow: the plan reads the lists work with this tool, the agent and the
    # reserves get --lists, the guard checks with --lists and adds the recorded rules
    text = (WORKFLOWS / "autofix.yml").read_text()
    assert 'tools/filter-lists.py plan --run-id "$RUN_ID" --work "$WORK"' in text
    assert text.count('if [ -f "$RUNNER_TEMP/lists-mode" ]; then allow="$allow --lists"; fi') == 2
    assert 'if [ "$MODE" = "lists" ]; then allow="$allow --lists"; fi' in text
    assert 'cp "$RUNNER_TEMP/failure/recorded.txt" "$RECORDED"' in text


def test_the_ledger_takes_each_finding_once_and_starts_one_analysis():
    info = _lists_info()
    work = {"run_id": "777", "run_url": "u", "lists": info, "outcomes": []}
    led = ledger_tool.update(None, {"components": [], "findings": []}, now=NOW, work=work)
    entries = led["entries"]
    unknown = entries["lists/unknown-scriptlet/no-such-scriptlet@breaking"]
    popup = entries["lists/protection-dropped/option-popup@security"]
    youtube = next(e for k, e in entries.items() if "/youtube/" in k)
    assert youtube["state"] == "needs-person" and "rule youtube" in youtube["reason"]
    # one entry per group: its count, the lists concerned and at most three samples
    assert popup["from"] == "1 rules" and popup["lists"] == "uBO filters" and popup["to"] == "security"
    assert popup["samples"] == ["||bit.ly^$popup,domain=eurogamer.net"]
    assert unknown["from"] == "2 rules" and len(unknown["samples"]) <= 3
    assert "samples" not in entries["lists/other-platform/html-filtering@harmless"]     # finished: a count
    assert entries["lists/known-resource/noeval@person"]["state"] == "needs-person"
    assert entries["lists/other-platform/html-filtering@harmless"]["state"] == "passed"
    # the most severe first, one at a time: the security finding, on an isolated branch
    assert popup["state"] == "fixing" and popup["work"]["branch"] == "automation/update/lists-2026-11-22"
    assert unknown["state"] == "detected"
    assert led["dispatch"] == [{"key": popup["key"], "run_id": "777",
                                "work": "lists/2026-11-22/" + popup["key"]}]
    assert not any(d["work"].endswith(youtube["key"]) for d in led["dispatch"])
    # the next day: the same findings are not added again, and nothing new starts
    # while the first analysis runs
    body = ledger_tool.render(led)
    again = ledger_tool.parse_body(body)
    assert again is not None and again["lists_seen"].keys() == led["lists_seen"].keys()
    led2 = ledger_tool.update(again, {"components": [], "findings": []}, now=NOW + dt.timedelta(hours=20),
                              work=dict(work, run_id="778"))
    assert led2["entries"].keys() == entries.keys() and led2["dispatch"] == []
    # once pruned, a finding still reported is not added again
    del again["entries"][unknown["key"]]
    led3 = ledger_tool.update(again, {"components": [], "findings": []}, now=NOW + dt.timedelta(hours=20),
                              work=dict(work, run_id="778"))
    assert unknown["key"] not in led3["entries"]
    # at most one analysis started a day, also when the first one is over the same day
    deferred = {"work": led["dispatch"][0]["work"], "outcome": "deferred", "run": "9", "artifact": "x",
                "created": "2026-11-22T06:00:00Z"}
    gone = json.loads(json.dumps(info))
    gone["lists"][0]["unread"] = [u for u in gone["lists"][0]["unread"] if "popup" not in u[1]]
    same_day = ledger_tool.update(json.loads(json.dumps(led)), {"components": [], "findings": []},
                                  now=NOW + dt.timedelta(hours=3), work={"run_id": "779", "lists": gone,
                                                                         "outcomes": [deferred]})
    assert same_day["entries"][popup["key"]]["state"] == "passed" and same_day["dispatch"] == []
    next_day = ledger_tool.update(same_day, {"components": [], "findings": []}, now=NOW + dt.timedelta(days=1),
                                  work={"run_id": "780", "lists": gone, "outcomes": []})
    assert [d["key"] for d in next_day["dispatch"]] == [unknown["key"]]
    # the dispatch the job makes of it (no network: dry run)
    started = work_tool.dispatch(led, "o/r", dry_run=True)
    assert started == ["lists/2026-11-22/" + popup["key"]]


def test_a_youtube_rule_needs_a_person():
    info = _lists_info()
    result = lists_tool.classify(info)
    yt = next(f for f in result["findings"] if f["youtube"])
    assert yt["class"] == "person" and not yt["ai"] and "CLAUDE.md" in yt["why"]
    work = "lists/2026-11-22/" + yt["key"]
    assert work_tool.WORK_ID.match(work)
    outputs, failure, recorded = lists_tool.plan(info, work, "abc")
    assert outputs["action"] == "skip" and "no AI analysis" in outputs["reason"] and not failure and not recorded
    # a YouTube rule the engine does not read is a person's too, whatever its option
    scr = scriptlets()
    for rule in ("||youtube.com/youtubei/v1/player?$xhr,removeparam=/ad/", "www.youtube.com##+js(trusted-x, 1)",
                 "m.youtube.com##.ytd-ad-slot-renderer:remove()"):
        assert lists_tool.classify_rule(rule, "network filter error: unrecognised option", "uBlock filters",
                                        True, scr.Library(), scr)[0] == "youtube", rule


# --- WP8: the guard of the lists' analysis -------------------------------------------------

def _git(cwd, *args):
    out = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, check=False)
    assert out.returncode == 0, out.stderr
    return out.stdout


@pytest.fixture
def adapter_repo(tmp_path):
    r = tmp_path / "repo"
    for rel in ("ike/scriptlets.py", "ike/blocker.py", "ike/config.py", "ike/resources/videoads.js",
                "ike/resources/ubo-scriptlets.json", "tests/test_adblock.py", "tests/data/filter-lists-snapshot.txt"):
        (r / rel).parent.mkdir(parents=True, exist_ok=True)
        if rel == "ike/resources/ubo-scriptlets.json":
            (r / rel).write_text('{"scriptlets": {}}\n')
        else:
            shutil.copy(ROOT / rel, r / rel)
    (r / "ike-adblock/src").mkdir(parents=True)
    (r / "ike-adblock/src/lib.rs").write_text("// I.K.E.'s wrapper\nfn add_filter_list() {}\n")
    _git(tmp_path, "init", "-q", str(r))
    _git(r, "-c", "user.name=t", "-c", "user.email=t@t", "add", "-A")
    _git(r, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "base")
    return r


def _patch(repo, rel, old, new):
    path = repo / rel
    text = path.read_text()
    assert old in text, (rel, old)
    path.write_text(text.replace(old, new, 1))
    _git(repo, "add", "-A")
    patch = _git(repo, "diff", "--cached")
    _git(repo, "reset", "-q", "--hard")
    return patch


def test_the_guard_of_the_lists_analysis(adapter_repo, tmp_path):
    repo = adapter_repo
    alias = _patch(repo, "ike/scriptlets.py", "        name = self._alias.get(name, name)\n",
                   "        name = self._alias.get(name, name)\n        name = MAPPED.get(name, name)\n")
    assert guard.check(repo, alias, lists=True) == []                   # the adapter: accepted
    assert guard.check(repo, alias)                                     # without --lists: the ad blocker is not
    refused = {
        "the lists": _patch(repo, "ike/config.py", "easylist.txt", "easylist-lite.txt"),
        "the bundled resources": _patch(repo, "ike/resources/ubo-scriptlets.json", "{}", '{"noeval.js": {}}'),
        "YouTube's script": _patch(repo, "ike/resources/videoads.js", "\n", "\n// x\n"),
        "a test": _patch(repo, "tests/test_adblock.py", "\n", "\n# x\n"),
        "the tests' data": _patch(repo, "tests/data/filter-lists-snapshot.txt", "\n", "\nx.example##.ad\n"),
        "YouTube's code in the adapter": _patch(
            repo, "ike/scriptlets.py", "        split = {h: self._split(h) for h in hosts}\n",
            "        split = {h: self._split(h) for h in hosts}  # all hosts\n"),
        "a YouTube rule": _patch(repo, "ike/blocker.py", "||youtube.com/ptracking^\n", "||youtube.com/ptracking^$xhr\n"),
        "a protection removed": _patch(repo, "ike/scriptlets.py",
                                       '            if lib.entry(name).get("trust") and not trusted:\n'
                                       "                continue\n", ""),
    }
    for what, patch in refused.items():
        reasons = guard.check(repo, patch, lists=True)
        assert reasons and guard.safety_refusal(reasons), (what, reasons)
    assert any("YouTube" in r for r in guard.check(repo, refused["YouTube's code in the adapter"], lists=True))
    assert any("weakens blocking" in r for r in guard.check(repo, refused["a protection removed"], lists=True))
    # the command line: a refusal for safety (exit 3), nothing applied
    patch_file = tmp_path / "p.patch"
    patch_file.write_text(refused["a test"])
    assert guard.main(["--repo", str(repo), "--patch", str(patch_file), "--lists", "--check-only"]) == 3
    patch_file.write_text(alias)
    assert guard.main(["--repo", str(repo), "--patch", str(patch_file), "--lists", "--check-only"]) == 0
    # the reserves cannot even write outside the adapter in this run
    reserve = load("autofix-reserve")
    with pytest.raises(ValueError, match="filter lists' analysis"):
        reserve.apply_edits(repo, [{"file": "tests/test_adblock.py", "find": "import", "replace": "import"}],
                            {"tests/test_adblock.py": ""}, True, lists=True)
    assert "ONLY ike/scriptlets.py" in reserve.instructions(True, True)
    agent = load("autofix-agent")
    assert "filter lists" in agent.engine_note(True, lists=True)


def test_the_new_tools_are_protected():
    ctx = load("autofix-context")
    for path in ("tools/filter-lists.py", "tools/ai-work.py", "tools/ai-providers.py", "tools/provider-check.py",
                 "tests/test_lists_recorded.py"):
        assert path in guard.FORBIDDEN_FILES and path in ctx.NOT_RECENT, path
        assert guard.allowed_path(path, True), path
    assert set(guard.FORBIDDEN_FILES) <= ctx.NOT_RECENT
    text = (WORKFLOWS / "autofix.yml").read_text()
    assert "tools/filter-lists.py, tools/ai-work.py, tools/ai-providers.py or tools/provider-check.py" in text
    # the registry travels with the tools that read it, from main
    assert "check-autofix-patch.py ai-providers.py; do" in text
    assert "tools/autofix-agent.py tools/check-autofix-patch.py tools/ai-providers.py" in text


# --- WP9: only free providers --------------------------------------------------------------

class Answer:
    def __init__(self, body, status=200):
        self.body, self.status = body if isinstance(body, bytes) else json.dumps(body).encode(), status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self, n=-1):
        return self.body


def http_error(url, code, body):
    return urllib.error.HTTPError(url, code, "err", {}, io.BytesIO(json.dumps(body).encode()))


KEYS = {"GEMINI_API_KEY": "AIzaTESTONLY-gemini", "GROQ_API_KEY": "gsk_TESTONLY", "ZAI_API_KEY": "zai.TESTONLY",
        "OPENROUTER_API_KEY": "sk-or-TESTONLY", "AUTOFIX_OPENROUTER_MODELS": "good/model:free"}
OK = {"choices": [{"message": {"content": "OK"}}], "usage": {"prompt_tokens": 9, "completion_tokens": 1}}


def provider_opener(seen, groq=None, zai=None, key_info=None, cost=0):
    def opener(req, timeout=0):
        url = req.full_url
        body = json.loads(req.data) if req.data else None
        seen.append((url, req.get_method(), (body or {}).get("model"), dict(req.header_items())))
        if "generativelanguage" in url:
            if url.endswith("pageSize=1000"):
                return Answer({"models": [{"name": "models/gemini-3.8-flash"}, {"name": "models/gemini-pro"}]})
            return Answer({"candidates": [{"content": {"parts": [{"text": "OK"}]}}]})
        if "groq" in url:
            if groq:
                raise http_error(url, *groq)
            return Answer(OK)
        if "z.ai" in url:
            if zai:
                raise http_error(url, *zai)
            return Answer(OK)
        if url.endswith("/api/v1/models"):
            return Answer({"data": [{"id": "good/model:free", "pricing": {"prompt": "0", "completion": "0"}},
                                    {"id": "pricey/model:free", "pricing": {"prompt": "0.000001", "completion": "0"}}]})
        if url.endswith("/api/v1/key"):
            return Answer({"data": key_info or {"is_free_tier": True, "usage": 0, "limit": None}})
        return Answer(dict(OK, usage={"prompt_tokens": 9, "cost": cost}))
    return opener


def test_the_provider_check_refuses_paid_openrouter_models_and_billing(tmp_path):
    check = load("provider-check")
    seen = []
    env = dict(KEYS, AUTOFIX_OPENROUTER_MODELS="paid/model, good/model:free, pricey/model:free")
    rows = check.check(env, provider_opener(seen))
    by = {(r["provider"], r["model"]): r for r in rows}
    # Gemini is asked too, the key in a header, never in the address
    gem = by[("Antigravity", "Gemini 3.8 Flash (High)")]
    assert gem["state"] == "available" and "not provable" in gem["free"]
    gemini_calls = [s for s in seen if "generativelanguage" in s[0]]
    assert len(gemini_calls) == 2 and all("TESTONLY" not in s[0] for s in gemini_calls)
    assert all(s[3].get("X-goog-api-key") == KEYS["GEMINI_API_KEY"] for s in gemini_calls)
    assert any(s[0].endswith("/models/gemini-3.8-flash:generateContent") for s in gemini_calls)
    # OpenRouter: a model without ":free" is refused and never asked; a ":free" one
    # priced above zero by OpenRouter itself is refused too; the free one answers
    assert by[("OpenRouter", "paid/model")]["state"] == "unavailable"
    assert "not a :free model" in by[("OpenRouter", "paid/model")]["reason"]
    assert by[("OpenRouter", "pricey/model:free")]["state"] == "unavailable"
    assert by[("OpenRouter", "good/model:free")]["state"] == "available"
    assert by[("OpenRouter", "good/model:free")]["free"].startswith("proven")
    asked = [s[2] for s in seen if s[1] == "POST" and "openrouter" in s[0]]
    assert asked == ["good/model:free"]
    assert by[("Groq", "qwen/qwen3.8-27b")]["state"] == "available"
    assert check.unavailable_of(rows) == []
    # a billing error marks a provider unavailable: Groq's 402, Z.AI's code 1113 (on a 429)
    seen = []
    rows = check.check(KEYS, provider_opener(
        seen, groq=(402, {"error": {"message": "Payment Required"}}),
        zai=(429, {"error": {"code": "1113", "message": "Insufficient balance or no resource package"}})))
    states = {r["provider"]: r["state"] for r in rows}
    assert states["Groq"] == states["Z.AI"] == "unavailable" and states["OpenRouter"] == "available"
    assert check.unavailable_of(rows) == ["Groq", "Z.AI"]
    # a plain rate limit is busy, not a billing error (Groq's advice names its paid tier)
    rows = check.check(KEYS, provider_opener([], groq=(429, {"error": {"message": "Rate limit reached. Need more "
                       "tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing"}})))
    assert {r["provider"]: r["state"] for r in rows}["Groq"] == "busy"
    # an answer that reports a cost, or an OpenRouter key off the free tier: unavailable
    rows = check.check(KEYS, provider_opener([], cost=0.0004))
    assert {r["provider"]: r["state"] for r in rows}["OpenRouter"] == "unavailable"
    rows = check.check(KEYS, provider_opener([], key_info={"is_free_tier": False, "usage": 0}))
    assert check.unavailable_of(rows) == ["OpenRouter"]
    # the file and the summary hold no key; the owner is told (Automation health)
    out = tmp_path / "ai-providers.json"
    assert check.main(["check", str(out), "--markdown", str(tmp_path / "p.md")], env=KEYS,
                      opener=provider_opener([], groq=(402, {"error": {"message": "payment required"}}))) == 0
    text = out.read_text() + (tmp_path / "p.md").read_text()
    assert "TESTONLY" not in text and json.loads(out.read_text())["unavailable"] == ["Groq"]
    health = load("automation-health")
    found = "\n".join(health.problems(NOW, {}, [], True, main_protected=True,
                                      providers=json.loads(out.read_text())["providers"]))
    assert "The AI provider Groq" in found and "marked unavailable" in found and "OpenRouter" not in found


def test_the_reserves_use_free_models_only_and_stop_at_a_cost(monkeypatch):
    reserve = load("autofix-reserve")
    plan = reserve.chain({"OPENROUTER_API_KEY": "k", "AUTOFIX_OPENROUTER_MODELS": "paid/x,free/y:free"})
    assert [p[3] for p in plan] == ["free/y:free"]                  # the paid one refused, also from the variable
    assert reserve.chain({"OPENROUTER_API_KEY": "k", "GROQ_API_KEY": "g", "AUTOFIX_UNAVAILABLE": "Groq"})[0][0] == \
        "OpenRouter"                                                # marked by the weekly check: skipped
    # an answer that reports a cost, or an error that asks for money: not free here
    with pytest.raises(reserve.Stop) as stop:
        reserve.ask("https://openrouter.ai/x", "k", "m", [], opener=lambda r, timeout=0: Answer(
            dict(OK, usage={"cost": 0.002})))
    assert stop.value.args[0] == "unavailable"
    with pytest.raises(reserve.Stop) as stop:
        reserve.ask("https://api.z.ai/x", "k", "m", [], opener=lambda r, timeout=0: (_ for _ in ()).throw(
            http_error(r.full_url, 429, {"error": {"code": "1113", "message": "余额不足或无可用资源包"}})))
    assert stop.value.args[0] == "unavailable"
    with pytest.raises(reserve.Stop) as stop:                       # a quota's advice is still a quota
        reserve.ask("https://api.groq.com/x", "k", "m", [], opener=lambda r, timeout=0: (_ for _ in ()).throw(
            http_error(r.full_url, 429, {"error": {"message": "Upgrade to Dev Tier: console.groq.com/settings/billing"}})))
    assert stop.value.args[0] == "quota"
    assert reserve.free_models("k", lambda r, timeout=0: Answer({"data": [
        {"id": "a/b:free", "context_length": 64000, "pricing": {"prompt": "0.1", "completion": "0"}},
        {"id": "c/d:free", "context_length": 64000, "pricing": {"prompt": "0", "completion": "0"}}]})) == ["c/d:free"]
    # Antigravity: marked unavailable, it does not start; a billing error is not a quota
    agent = load("autofix-agent")
    assert agent.classify(1, 'AGY_ERROR: {"error_code": 400, "status": "FAILED_PRECONDITION", "message": '
                             '"BILLING_DISABLED"}')[0] == "unavailable"
    assert agent.classify(1, "Error 429 RESOURCE_EXHAUSTED quota per day, check your plan and billing details")[0] \
        == "day"


def test_antigravity_marked_unavailable_does_not_start(tmp_path, monkeypatch):
    agent = load("autofix-agent")
    (tmp_path / "prompt.md").write_text("RULES")
    status = tmp_path / "status.json"
    monkeypatch.setenv("AUTOFIX_UNAVAILABLE", "Antigravity")
    started = []
    monkeypatch.setattr(agent.subprocess, "run", lambda *a, **k: started.append(a))
    assert agent.main(["--workdir", str(tmp_path), "--prompt", str(tmp_path / "prompt.md"), "--out",
                       str(tmp_path / "out"), "--status", str(status)]) == 0
    assert json.loads(status.read_text())["result"] == "unavailable" and not started


def test_the_registry_is_the_one_place():
    reserve, agent = load("autofix-reserve"), load("autofix-agent")
    assert reserve.PROVIDERS == tuple(tuple(p) for p in registry.RESERVES)
    assert agent.FREE_MODELS == registry.GEMINI_MODELS and agent.TOTAL_TIMEOUT == registry.TOTAL_TIMEOUT
    assert reserve.TOTAL_TIMEOUT == registry.RESERVES_TIMEOUT
    assert registry.all_names()[0] == "Antigravity" and registry.RETRY_CAP >= 1
    assert all(m.endswith(":free") for p in registry.RESERVES if p[0] == "OpenRouter" for m in p[4])
    # health: Gemini pinged too, the keys in that step only
    text = (WORKFLOWS / "health.yml").read_text()
    step = text.split("- name: The AI providers answer and are free", 1)[1].split("- uses:", 1)[0]
    assert "GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}" in step and "tools/provider-check.py check" in step
    assert text.count("${{ secrets.GEMINI_API_KEY }}") == 1
    assert "PROVIDER_CHECK: ${{ runner.temp }}/providers/ai-providers.json" in text
    assert "name: ai-providers" in text
    plan = (WORKFLOWS / "autofix.yml").read_text().split("\n  rerun:\n", 1)[0]
    assert "tools/provider-check.py unavailable" in plan and "secrets." not in plan


# --- WP9: no free provider: retry-later, resume, cap, the owner told ------------------------

def _empty():
    return {"components": [], "findings": []}


def test_no_provider_waits_then_resumes_then_the_owner_is_told():
    deferred = {"work": "run/4242", "outcome": "deferred", "workflow": "Tests", "url": "r1", "run": "1",
                "created": "2026-11-22T04:00:00Z", "artifact": "ai-work-outcome-report"}
    led = ledger_tool.update(None, _empty(), now=NOW, work={"run_id": "9", "outcomes": [deferred]})
    e = led["entries"]["ai-work/4242@retry"]
    assert e["state"] == "retry-later" and e["work"]["retries"] == 1 and e["attempts"] == 1
    assert e["next_retry"] == "2026-11-23T05:30:00Z" and led["dispatch"] == [] and led["notify"] == []
    # the same outcome read again changes nothing
    led = ledger_tool.update(led, _empty(), now=NOW + dt.timedelta(hours=1), work={"run_id": "9",
                                                                                  "outcomes": [deferred]})
    assert led["entries"]["ai-work/4242@retry"]["work"]["retries"] == 1
    now = NOW
    for n in range(2, registry.RETRY_CAP + 1):
        now += dt.timedelta(hours=registry.RETRY_HOURS + 1)
        led = ledger_tool.update(led, _empty(), now=now, work={"run_id": "9", "outcomes": []})
        e = led["entries"]["ai-work/4242@retry"]
        # resumed: the same failed run again, its attempts kept
        assert led["dispatch"] == [{"key": e["key"], "run_id": "4242", "work": "run/4242"}]
        assert e["state"] == "fixing" and e["attempts"] == 1 and led["notify"] == []
        again = dict(deferred, run=str(n), created=now.strftime("%Y-%m-%dT%H:%M:%SZ"))
        led = ledger_tool.update(led, _empty(), now=now + dt.timedelta(minutes=30),
                                 work={"run_id": "9", "outcomes": [again]})
        e = led["entries"]["ai-work/4242@retry"]
        if n < registry.RETRY_CAP:
            assert e["state"] == "retry-later" and e["work"]["retries"] == n and led["notify"] == []
    # the cap: a person, told once
    assert e["state"] == "needs-person" and "the owner is told" in e["reason"]
    assert led["notify"] == [e["key"]]
    text = work_tool.notify_text(led, "Owner")
    assert text.startswith("@Owner:") and "RETRY_CAP in tools/ai-providers.py" in text
    led = ledger_tool.update(led, _empty(), now=now + dt.timedelta(days=2), work={"run_id": "9", "outcomes": []})
    assert led["notify"] == [] and led["dispatch"] == []
    # the cap is one number, in one place
    one = ledger_tool.update(None, _empty(), now=NOW, work={"run_id": "9", "outcomes": [deferred]})
    one = work_tool.merge(one, {"outcomes": [dict(deferred, run="x")]}, NOW, ledger_tool.set_state, cap=2)
    assert one["entries"]["ai-work/4242@retry"]["state"] == "needs-person" and one["notify"]


def test_a_lists_analysis_without_provider_keeps_its_branch():
    info = _lists_info()
    led = ledger_tool.update(None, _empty(), now=NOW, work={"run_id": "777", "lists": info, "outcomes": []})
    key, wid = led["dispatch"][0]["key"], led["dispatch"][0]["work"]
    deferred = {"work": wid, "outcome": "deferred", "run": "5", "created": "2026-11-22T06:00:00Z",
                "artifact": "ai-work-outcome-report"}
    later = NOW + dt.timedelta(hours=2)
    led = ledger_tool.update(led, _empty(), now=later, work={"run_id": "778", "lists": info, "outcomes": [deferred]})
    e = led["entries"][key]
    assert e["state"] == "retry-later" and e["work"]["branch"] == "automation/update/lists-2026-11-22"
    # the next day: started again on the same branch, with today's lists report
    led = ledger_tool.update(led, _empty(), now=later + dt.timedelta(hours=25),
                             work={"run_id": "800", "lists": info, "outcomes": []})
    assert led["dispatch"] == [{"key": key, "run_id": "800", "work": wid}]
    assert wid.startswith("lists/2026-11-22/")
    # published: its tests decide; once the finding is gone, it passed
    published = {"work": wid, "outcome": "published", "branch": "automation/update/lists-2026-11-22", "pr": "120",
                  "run": "6", "created": "2026-11-23T08:00:00Z", "artifact": "ai-work-outcome-publish"}
    led = ledger_tool.update(led, _empty(), now=later + dt.timedelta(hours=27),
                             work={"run_id": "801", "lists": info, "outcomes": [published]})
    assert led["entries"][key]["state"] == "testing" and "PR #120" in led["entries"][key]["reason"]
    fixed = json.loads(json.dumps(info))
    fixed["lists"][0]["unread"] = [u for u in fixed["lists"][0]["unread"] if "popup" not in u[1]]
    led = ledger_tool.update(led, _empty(), now=later + dt.timedelta(days=2),
                             work={"run_id": "802", "lists": fixed, "outcomes": []})
    assert led["entries"][key]["state"] == "passed"
    # the next finding is analysed now
    assert led["dispatch"] and led["dispatch"][0]["key"].endswith("no-such-scriptlet@breaking")


def test_a_fix_after_the_lists_branch_failed_its_tests_keeps_the_entry_coherent():
    """PR #111 (2026-11-22): the analysis' change failed its tests; the automatic fix of that branch
    (work run/<id>, tools/autofix-plan.py) reports to the finding's own entry by its branch."""
    info = _lists_info()
    led = ledger_tool.update(None, _empty(), now=NOW, work={"run_id": "777", "lists": info, "outcomes": []})
    key, wid = led["dispatch"][0]["key"], led["dispatch"][0]["work"]
    branch = "automation/update/lists-2026-11-22"
    published = {"work": wid, "outcome": "published", "branch": branch, "pr": "111", "run": "6",
                 "created": "2026-11-22T06:00:00Z", "artifact": "ai-work-outcome-publish"}
    now = NOW + dt.timedelta(hours=2)
    led = ledger_tool.update(led, _empty(), now=now, work={"run_id": "778", "lists": info, "outcomes": [published]})
    assert led["entries"][key]["state"] == "testing"
    attempts = led["entries"][key]["attempts"]
    # attempt 2 after the tests failed: still testing, the days counted again from the new change
    retry = {"work": "run/45039352924", "outcome": "published", "branch": branch, "pr": "111", "run": "7",
             "created": "2026-11-28T06:00:00Z", "artifact": "ai-work-outcome-publish"}
    now += dt.timedelta(days=6)
    led = ledger_tool.update(led, _empty(), now=now, work={"run_id": "779", "lists": info, "outcomes": [retry]})
    e = led["entries"][key]
    assert e["state"] == "testing" and "after its tests failed" in e["reason"] and "PR #111" in e["reason"]
    assert "ai-work/45039352924@retry" not in led["entries"] and e["attempts"] == attempts
    now += dt.timedelta(days=4)                  # 10 days after the first change, 4 after the new one
    led = ledger_tool.update(led, _empty(), now=now, work={"run_id": "780", "lists": info, "outcomes": []})
    assert led["entries"][key]["state"] == "testing"
    # the cap (or the AI or the checks could not): a person; the report's issue tells the owner
    person = {"work": "run/45043411828", "outcome": "person", "branch": branch, "run": "8",
              "reason": "needs-person: 4 automatic changes of I.K.E.'s adapter did not make it pass",
              "created": "2026-12-02T07:00:00Z", "artifact": "ai-work-outcome-report"}
    led = ledger_tool.update(led, _empty(), now=now + dt.timedelta(hours=1),
                             work={"run_id": "781", "lists": info, "outcomes": [person]})
    e = led["entries"][key]
    assert e["state"] == "needs-person" and "4 automatic changes" in e["reason"] and led["notify"] == []
    # an outcome of another branch, or of no branch, is not the finding's
    for other in ("automation/update/lists-foo", "automation/update/darkreader", ""):
        fresh = ledger_tool.update(None, _empty(), now=NOW, work={"run_id": "777", "lists": info, "outcomes": []})
        fresh = ledger_tool.update(fresh, _empty(), now=NOW + dt.timedelta(hours=2),
                                   work={"run_id": "778", "lists": info, "outcomes": [published]})
        fresh = ledger_tool.update(fresh, _empty(), now=NOW + dt.timedelta(hours=3), work={
            "run_id": "779", "lists": info, "outcomes": [dict(person, branch=other)]})
        assert fresh["entries"][key]["state"] == "testing", other
    # no free provider for that fix: it waits as any other fix does (its own entry, started again)
    deferred = dict(person, outcome="deferred", run="9")
    fresh = ledger_tool.update(fresh, _empty(), now=NOW + dt.timedelta(hours=4),
                               work={"run_id": "782", "lists": info, "outcomes": [deferred]})
    assert fresh["entries"]["ai-work/45043411828@retry"]["state"] == "retry-later"
    assert fresh["entries"][key]["state"] == "testing"
    # the report says the branch of the work
    script = _step("Work that waits, or the filter lists' analysis")
    assert '--arg branch "$PUSH_BRANCH"' in script and "branch: $branch" in script


def _step(name, workflow="autofix.yml"):
    lines = (WORKFLOWS / workflow).read_text().splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.strip() == "- name: %s" % name)
    run = next(i for i in range(start, len(lines)) if lines[i].strip() == "run: |")
    indent = len(lines[run]) - len(lines[run].lstrip())
    body = []
    for ln in lines[run + 1:]:
        if ln.strip() and len(ln) - len(ln.lstrip()) <= indent:
            break
        body.append(ln)
    return textwrap.dedent("\n".join(body)) + "\n"


@pytest.mark.parametrize("agent, reserve, deferred", [
    ("quota", {"result": "quota", "no_provider": True}, "true"),             # every provider busy
    ("unavailable", {"result": "unavailable", "no_provider": True}, "true"),  # not free anywhere
    ("quota", {"result": "error", "no_provider": False}, "false"),          # a model answered
    ("timeout", {"result": "quota", "no_provider": True}, "false"),         # Antigravity worked
    ("quota", None, "true"),                                                # no reserve keys, Gemini busy
    ("nokey", None, "false"),                                               # no key at all: the owner's
])
def test_the_fix_job_says_when_no_provider_answered(tmp_path, agent, reserve, deferred):
    script = _step("Reserves, then the patch")
    snippet = script.split("deferred=$(python3 -I - \"$out\" <<'PY'\n", 1)[1].split("\nPY\n", 1)[0]
    out = tmp_path / "out"
    out.mkdir()
    (out / "status.json").write_text(json.dumps({"result": agent}))
    if reserve is not None:
        (out / "reserve.json").write_text(json.dumps(reserve))
    run = subprocess.run(["python3", "-I", "-", str(out)], input=snippet, capture_output=True, text=True)
    assert run.stdout.strip() == deferred, run.stderr


@pytest.mark.parametrize("env, tell, outcome", [
    ({"ACTION": "fix", "DEFERRED": "true", "KIND": "main"}, "false", "deferred"),
    ({"ACTION": "fix", "DEFERRED": "false", "KIND": "main"}, "true", "person"),
    ({"ACTION": "fix", "DEFERRED": "false", "KIND": "lists"}, "false", "person"),
    ({"ACTION": "issue", "DEFERRED": "", "KIND": "lists"}, "false", "person"),
    ({"ACTION": "issue", "DEFERRED": "", "KIND": "infra"}, "true", None),
])
def test_the_report_asks_nobody_when_the_work_waits(tmp_path, env, tell, outcome):
    if not shutil.which("jq"):
        pytest.skip("jq is not installed (GitHub's runners have it)")
    script = _step("Work that waits, or the filter lists' analysis")
    out = tmp_path / "gh-output"
    full = dict(os.environ, RUNNER_TEMP=str(tmp_path), GITHUB_OUTPUT=str(out), WORK="run/4242", AGENT="quota",
                REASON="", WORKFLOW="Tests", RUN_URL="u", **env)
    run = subprocess.run(["bash", "-e", "-c", script], env=full, capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    assert "tell=%s" % tell in out.read_text()
    written = tmp_path / "outcome" / "outcome.json"
    if outcome is None:
        assert not written.exists()
    else:
        data = json.loads(written.read_text())
        assert data["outcome"] == outcome and data["work"] == "run/4242"
        assert work_tool.WORK_ID.match(data["work"])
    report = (WORKFLOWS / "autofix.yml").read_text()
    assert "if: steps.wait.outputs.tell != 'false'" in report


def test_the_daily_check_runs_the_queue():
    text = (WORKFLOWS / "daily-check.yml").read_text()
    assert "tools/filter-lists.py classify --lists lists.json --json classes.json --markdown classes.md" in text
    assert 'tools/ai-work.py gather --repo "$GITHUB_REPOSITORY" --run-id "$GITHUB_RUN_ID"' in text
    assert "--out ledger.md --json ledger.json --work work.json" in text
    assert "tools/ai-work.py notify --ledger ledger.json" in text
    job = text.split("\n  ai-work:\n", 1)[1].split("\n  start-arch:\n", 1)[0]
    assert "actions: write" in job and "continue-on-error: true" in job and "issues:" not in job
    assert "tools/ai-work.py dispatch --ledger ledger/ledger.json" in job
    # the dispatch starts autofix.yml with the run id and the work, nothing else
    led = {"dispatch": [{"run_id": "1", "work": "run/1"}, {"run_id": "x; rm", "work": "run/2"},
                        {"run_id": "3", "work": "lists/../../etc"}]}
    calls = []
    work_tool.dispatch(led, "o/r", run=lambda cmd, **k: calls.append(cmd) or subprocess.CompletedProcess(cmd, 0))
    assert calls == [["gh", "workflow", "run", "autofix.yml", "--repo", "o/r", "--ref", "main", "-f", "run_id=1",
                      "-f", "work=run/1"]]


def test_the_outcomes_are_read_from_the_runs_artifacts():
    import zipfile
    blob = io.BytesIO()
    with zipfile.ZipFile(blob, "w") as z:
        z.writestr("outcome.json", json.dumps({"work": "run/7", "outcome": "deferred"}))
    calls = []

    def api(path, raw=False):
        calls.append(path)
        if raw:
            return blob.getvalue()
        if "name=ai-work-outcome-fix" in path:
            return {"artifacts": [], "total_count": 0}
        if "name=ai-work-outcome-report" in path:
            return {"artifacts": [{"id": 1, "created_at": "2026-11-22T04:00:00Z", "workflow_run": {"id": 55}},
                                  {"id": 2, "created_at": "2026-11-10T04:00:00Z", "workflow_run": {"id": 44}}]}
        return {"artifacts": []}
    found = work_tool.gather("o/r", api=api, now=NOW)
    assert found == [{"work": "run/7", "outcome": "deferred", "run": "55", "created": "2026-11-22T04:00:00Z",
                      "artifact": "ai-work-outcome-report"}]
    assert len(calls) == len(work_tool.OUTCOME_ARTIFACTS) + 1     # one listing each, one download


def test_five_thousand_findings_fit_in_the_ledger_issue():
    """GitHub's limit for an issue body is 65,536 characters: 5,000 rules the
    engine does not read, in many lists, with many options and unknown
    scriptlets, next to 22 updates of components (PR #100's dry run), give one
    entry per group, a body under MAX_BODY, and every open entry in it."""
    options = sorted(lists_tool.PROTECTIVE | lists_tool.NO_BLOCKING) + ["reason", "requestheader", "top", "shide"]
    names = ["uBlock filters", "uBlock filters - Privacy", "uBlock filters - Badware", "uBlock filters - Unbreak",
             "uBlock filters - Quick fixes", "EasyList", "EasyPrivacy", "EasyList Italy"]
    rows = []
    for i, name in enumerate(names):
        unread = []
        for n in range(5000 // len(names)):
            option = options[(n + i) % len(options)]
            rule = "%s||site%d.example^$script,%s=x" % ("@@" if n % 7 == 0 else "", n, option)
            unread.append(["error", rule, "network filter error: unrecognised option"])
        unread += [["error", "s%d.example##^script:has-text(ad)" % n, "cosmetic filter error: html filtering is "
                    "unsupported"] for n in range(5)]
        rows.append({"name": name, "state": "ok", "trusted": i < 5, "network": 1000, "cosmetic": 1000,
                     "unread_share": 0.05, "scriptlets": {"rules": 10}, "unread": unread})
    unknown = {"made-up-%d" % n: {"count": 3, "lists": ["uBlock filters"], "example":
                                  "x%d.example##+js(made-up-%d, a)" % (n, n)} for n in range(30)}
    info = {"state": "findings", "lists": rows, "findings": [], "engine": {"built": True, "backend": "adblock"},
            "unknown_scriptlets": unknown}
    assert sum(len(r["unread"]) for r in rows) >= 5000
    led = ledger_tool.update(None, _empty(), now=NOW, work={"run_id": "1", "lists": info, "outcomes": []})
    for n in range(22):
        key = "crate:c%d@1.0.%d" % (n, n)
        led["entries"][key] = {"key": key, "component": "crate:c%d" % n, "name": "crate c%d" % n, "kind": "crate",
                               "from": "1.0.0", "to": "1.0.%d" % n, "state": ("candidate", "blocked", "passed")[n % 3],
                               "reason": "r" * 150, "attempts": 1, "first_seen": "2026-11-21T05:00:00Z",
                               "last_seen": "2026-11-22T05:00:00Z", "changed": "2026-11-2%dT05:00:00Z" % (n % 2),
                               "last_run": "https://github.com/o/r/actions/runs/123456789", "next_retry": "",
                               "history": [["2026-11-22T05:00:00Z", "candidate", "h" * 150]] * 4}
    lists = [e for e in led["entries"].values() if e["kind"] == "filter-list"]
    assert 50 <= len(lists) < 200                                  # one per group, never one per rule
    body = ledger_tool.render(led)
    assert len(body) <= ledger_tool.MAX_BODY, len(body)
    back = ledger_tool.parse_body(body)
    assert back is not None
    opened = [k for k, e in led["entries"].items() if e["state"] != "passed"]
    assert opened and all(k in back["entries"] and back["entries"][k]["state"] == led["entries"][k]["state"]
                          for k in opened)
    # only finished entries were folded, and the issue says how many
    folded = [k for k in led["entries"] if k not in back["entries"]]
    assert all(led["entries"][k]["state"] == "passed" for k in folded)
    if folded:
        assert back["folded"] == len(folded) and "%d older finished entries were folded" % len(folded) in body
    # the next day reads it back: no finding added twice, nothing open lost
    again = ledger_tool.update(back, _empty(), now=NOW + dt.timedelta(days=1),
                               work={"run_id": "2", "lists": info, "outcomes": []})
    assert all(k in again["entries"] for k in opened)
    assert not any(k in again["entries"] for k in folded if k.startswith("lists/"))
    assert len(ledger_tool.render(again)) <= ledger_tool.MAX_BODY
