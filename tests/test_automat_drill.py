"""AUTOMAT's drill (tools/automat-drill.py): a realistic emergency rehearsed live, never in main.

The proofs, all offline (no AI, no network, fake providers and a fake GitHub):

- the drill's branch is an ordinary candidate of the full chain, built from main by one commit that
  only adds the marker and the scenario's breaks (without the expected solutions);
- the simulated release (tools/automat-drill-shim.py) really breaks the chosen APIs, only in a
  process started from a drill's checkout, and the normal test environment is untouched;
- tools/automerge.py never merges a drill, even fully verified and reviewed; merge_it refuses one;
- the signing notice and the maintenance ledger leave a drill out;
- "DEVI AIUTARCI CON CHATGPT" fires for a drill only as an exercise, naming and assigning nobody;
- the plan opens no security branch and no issue for a drill, and gives it its attempts per day;
- what changed upstream is the drill's simulated release notes, read from main's copy only;
- the report is produced, and the end mails the owner once.

These tests never read the drill's own marker in this checkout: on a drill's branch they pass the same.
"""

import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_merge_and_mail as mm  # noqa: E402


def load(name):
    spec = importlib.util.spec_from_file_location("drilltest_" + name.replace("-", "_"),
                                                  ROOT / "tools" / ("%s.py" % name))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


drill = load("automat-drill")
merge = load("automerge")
uc = load("update-candidates")
plan_tool = load("autofix-plan")
helper = load("automat-help")
notice = load("release-notice")
ledger = load("maintenance-ledger")
upstream = load("upstream-diff")
guard = load("check-autofix-patch")
REPO = mm.REPO
BRANCH = "automation/update/drill-qt"
# main's copy of the scenarios (on a drill's branch this file holds only the breaks: see the test below)
MAIN_DATA = drill.load(ROOT)
ON_DRILL_BRANCH = (ROOT / drill.MARKER).is_file()


def main_scenarios():
    """The scenarios as main holds them: this checkout's, or (on a drill's branch) main's from git."""
    if not ON_DRILL_BRANCH:
        return MAIN_DATA
    out = subprocess.run(["git", "-C", str(ROOT), "show", "origin/main:" + drill.DATA], capture_output=True, text=True)
    return drill.load_text(out.stdout) if out.returncode == 0 and out.stdout.strip() else None


# --- the scenario ----------------------------------------------------------------------------------

def test_the_scenario_is_a_real_emergency_with_its_expected_solutions():
    data = main_scenarios()
    if data is None:
        return                                      # (a drill's branch without main in its history)
    qt = data["scenarios"]["qt"]
    assert qt["candidate"] == "drill-qt" and drill.is_drill_branch("automation/update/" + qt["candidate"])
    breaks = qt["breaks"]
    assert 5 <= len(breaks) <= 8
    files = {f for b in breaks for f in b["files"]}
    assert len(files) >= 5                           # different files of I.K.E.
    assert {"easy", "medium", "hard"} <= {b["difficulty"] for b in breaks}
    fg = load("fix-guard")
    for b in breaks:
        assert set(drill.SHIM_KEYS) >= {k for k in b if k in ("id", "kind", "module", "owner", "old", "new")}
        assert b["kind"] in ("rename", "remove", "max_args") and b["module"].startswith(("PyQt6.", "jeepney"))
        assert b["tests"] and all(t.startswith("tests/test_") and "::" in t for t in b["tests"]), b["id"]
        assert len(b["expected"]["summary"]) > 40, b["id"]
        for f in b["files"]:
            assert (ROOT / f).is_file() and fg.tier(f) in ("", "A"), f    # an AI may fix it
            assert re.search(r"\b%s\b" % re.escape(b["old"]), (ROOT / f).read_text("utf-8")) or ON_DRILL_BRANCH, \
                (b["id"], f)
    # the notes say what a real release's would: the renames in words a program understands
    notes = "\n".join(qt["notes"])
    for b in breaks:
        if b["kind"] == "rename":
            assert re.search(r"renamed %s to %s" % (b["old"], b["new"]), notes), b["id"]
    assert 1 <= qt["attempts_per_day"] <= 12 and 12 <= qt["hours"] <= 96


def test_the_drill_is_a_candidate_of_the_full_chain_never_planned_daily():
    assert uc.id_of_branch(BRANCH) == "drill-qt" and uc.spec("drill-qt")["drill"] is True
    s = uc.spec("drill-qt")
    assert s["serial"] == "" and s["ships"] is False and s["wrapper"] is False
    assert s["files"] == (drill.MARKER, drill.DATA)
    assert plan_tool.isolated(BRANCH) and plan_tool.fixable("Tests", BRANCH)
    # the daily plan never makes it: no report of the components ever holds a drill
    report = {"candidates": [{"id": "test-qt", "from": "1", "to": "2"}]}
    rows = uc.plan(report, {BRANCH: {"pr": 9, "sha": "a" * 40}})
    assert [r["id"] for r in rows] == ["test-qt"] and rows[0]["action"] == "make"      # nor holds one back
    first = drill.commit_message(MAIN_DATA["scenarios"]["qt"] if not ON_DRILL_BRANCH else
                                 {"candidate": "drill-qt", "from": "PyQt6 6.12.1", "to": "PyQt6 7.0"})
    assert uc.UPDATE_COMMIT.match(first) and "trial" not in first.lower()
    assert uc.commit_problem("drill-qt", first, [drill.MARKER, drill.DATA]) == ""
    assert uc.commit_problem("drill-qt", first, ["ike/window.py"])            # nothing else
    assert uc.commit_problem("drill-qt", first, ["ike/__init__.py"])          # not even the version


@pytest.fixture
def repo(tmp_path):
    """A repository of a few of main's files, its main as origin/main."""
    r = tmp_path / "repo"
    for rel in ("tools/automat-drill.json", "tools/automat-drill-shim.py", "tools/update-candidates.py",
                "tools/component-manifest.py", "components.json", "ike_boot.py"):
        (r / rel).parent.mkdir(parents=True, exist_ok=True)
        (r / rel).write_bytes((ROOT / rel).read_bytes())
    data = main_scenarios() or MAIN_DATA
    (r / drill.DATA).write_text(json.dumps(data, indent=2), "utf-8")
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t",
               GIT_COMMITTER_EMAIL="t@t")
    for args in (["init", "-q", "-b", "main"], ["add", "-A"], ["commit", "-q", "-m", "main"],
                 ["update-ref", "refs/remotes/origin/main", "HEAD"]):
        subprocess.run(["git", "-C", str(r), *args], check=True, env=env, capture_output=True)
    return r


def test_the_drill_branch_is_built_correctly(repo, monkeypatch):
    data = drill.load(repo)
    local, sha, files = drill.make_branch(repo, "qt", data, "qt-202611231400", "2026-11-23T14:00:00+00:00")
    assert files == sorted([drill.DATA, drill.MARKER])
    first = subprocess.run(["git", "-C", str(repo), "log", "-1", "--format=%s%n%an"], capture_output=True,
                           text=True).stdout.split("\n")
    assert uc.UPDATE_COMMIT.match(first[0]) and first[0].startswith("update: drill-qt ") and first[1] == drill.BOT
    monkeypatch.chdir(repo)
    assert uc.check_range("drill-qt", "origin/main", local) == []       # what the daily maintenance checks
    m = json.loads((repo / drill.MARKER).read_text())
    assert m["scenario"] == "qt" and m["candidate"] == "drill-qt" and m["drill"] == "qt-202611231400"
    assert m["main"] == subprocess.run(["git", "-C", str(repo), "rev-parse", "origin/main"], capture_output=True,
                                       text=True).stdout.strip() and "never merged" in m["what"]
    # the branch's copy: only this scenario's breaks, nothing of the answers or the notes
    on_branch = json.loads((repo / drill.DATA).read_text())
    assert list(on_branch["scenarios"]) == ["qt"]
    text = json.dumps(on_branch)
    for word in ("expected", "notes", "tests", "difficulty", "summary"):
        assert '"%s"' % word not in text, word
    breaks = on_branch["scenarios"]["qt"]["breaks"]
    assert len(breaks) == len(data["scenarios"]["qt"]["breaks"])
    assert all(set(b) <= set(drill.SHIM_KEYS) for b in breaks)


def test_on_a_drill_branch_the_answers_are_not_in_the_tree():
    """This checkout itself: main holds the answers, a drill's branch only the breaks."""
    data = drill.load(ROOT)
    for sc in data["scenarios"].values():
        for b in sc["breaks"]:
            assert ("expected" in b) is not ON_DRILL_BRANCH, b.get("id")


# --- the simulated release ---------------------------------------------------------------------------

PROBE = r"""
import json, sys
site = sys.argv[1]
import site as _site
_site.addsitedir(site)
heavy = [m for m in ("argparse", "traceback", "logging", "dataclasses", "inspect") if m in sys.modules]
import importlib
data = json.loads(sys.argv[2])
out = {}
for b in data:
    mod = importlib.import_module(b["module"])
    owner = mod
    for part in [p for p in b.get("owner", "").split(".") if p]:
        owner = getattr(owner, part)
    row = {"old": hasattr(owner, b["old"])}
    if b.get("new"):
        row["new"] = hasattr(owner, b["new"])
    if b["kind"] == "max_args":
        try:
            getattr(owner, b["old"])(None, "a", None, None)
            row["narrow"] = False
        except TypeError as e:
            row["narrow"] = "too many arguments" in str(e)
    out[b["id"]] = row
import ike_automat_drill_shim as shim
out["_root"] = str(shim._STATE["root"])
out["_heavy"] = heavy
print(json.dumps(out))
"""


def _probe(script, cwd, site, breaks):
    """The probe run as the file `script` (I.K.E.'s code when it is under a checkout's ike/) from `cwd`."""
    script = Path(script)
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(PROBE, "utf-8")
    args = [sys.executable, "-s", str(script), str(site), json.dumps(breaks)]
    env = {k: v for k, v in os.environ.items() if not k.startswith(("PYTHON", "IKE_"))}
    env["QT_QPA_PLATFORM"] = "offscreen"
    out = subprocess.run(args, cwd=str(cwd), env=env, capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr[-2000:]
    return json.loads(out.stdout.strip().splitlines()[-1])


def _untouched(got, breaks, where):
    for b in breaks:
        assert got[b["id"]]["old"] is True, (where, b["id"])
        if b["kind"] == "max_args":
            assert got[b["id"]]["narrow"] is False, (where, b["id"])


def test_the_simulated_release_breaks_only_ikes_code_in_a_drills_checkout(repo, tmp_path):
    pytest.importorskip("PyQt6.QtWebEngineWidgets")
    pytest.importorskip("jeepney")
    data = drill.load(repo)
    drill.make_branch(repo, "qt", data, "qt-1", "2026-11-23T14:00:00+00:00")
    breaks = json.loads((repo / drill.DATA).read_text())["scenarios"]["qt"]["breaks"]
    site = tmp_path / "site"
    assert drill.install_shim(repo, site) is True
    assert (site / drill.PTH).read_text().startswith("import %s;" % drill.SHIM_MODULE)
    # I.K.E.'s code in the drill's checkout: every chosen API is broken the way a major release breaks it
    got = _probe(repo / "ike" / "_drill_probe.py", repo, site, breaks)
    assert got["_root"] == str(repo.resolve())
    assert got["_heavy"] == []                     # the start loads nothing more (tests/test_start_speed.py)
    for b in breaks:
        row = got[b["id"]]
        assert row["old"] is (b["kind"] == "max_args"), b["id"]
        if b["kind"] == "rename":
            assert row["new"] is True, b["id"]
        if b["kind"] == "max_args":
            assert row["narrow"] is True, b["id"]
    # the same, started from elsewhere (as the tests and "Nothing gets worse" start the browser)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    assert _probe(repo / "ike" / "_drill_probe.py", elsewhere, site, breaks)["_root"] == \
        str(repo.resolve())
    # the tests and their helpers in the same checkout keep today's names (no AI may change them)
    got = _probe(repo / "tests" / "_drill_probe.py", repo, site, breaks)
    assert got["_root"] == str(repo.resolve())
    _untouched(got, breaks, "tests")
    # main's checkout in the same environment (the base of "Nothing gets worse"): untouched
    main = tmp_path / "main"
    (main / "ike").mkdir(parents=True)
    (main / "ike_boot.py").write_text("")
    got = _probe(main / "ike" / "_drill_probe.py", main, site, breaks)
    assert got["_root"] == "None"
    _untouched(got, breaks, "main")


def test_the_simulated_release_is_installed_only_on_a_drills_checkout(tmp_path, repo):
    site = tmp_path / "site"
    assert drill.install_shim(repo, site) is False and not site.exists()        # main: nothing installed
    drill.make_branch(repo, "qt", drill.load(repo), "qt-1", "2026-11-23T14:00:00+00:00")
    assert drill.install_shim(repo, site) is True and (site / (drill.SHIM_MODULE + ".py")).is_file()
    action = (ROOT / ".github/actions/ike-test-env/action.yml").read_text()
    step = action.split("The AUTOMAT drill's simulated release", 1)[1]
    assert "if [ -f tools/automat-drill.active ]; then" in step
    assert "python tools/automat-drill.py shim --install --root ." in step
    # the normal test job is untouched: tests.yml and the package know nothing of the drill
    for name in ("tests.yml", "arch.yml", "release-ready.yml"):
        assert "automat-drill" not in (WORKFLOWS / name).read_text(), name
    assert "automat-drill" not in (ROOT / "PKGBUILD").read_text()


# --- never merged, never in the notice or the ledger --------------------------------------------------

OLD_WIN = mm.BASE
NEW_WIN = OLD_WIN.replace("        return 1", "        if self.label is None:\n            return 0\n        return 1")
DRILL_COMMITS = [
    {"sha": "b" * 40, "commit": {"message": "update: drill-qt PyQt6 6.12.1 -> PyQt6 7.0 (simulated) (no AI)"},
     "files": [drill.MARKER, drill.DATA]},
    {"sha": "c" * 40, "commit": {"message": 'autofix: attempt 1 after a failure of "Tests"\n\nPrepared by...\n'
                                            'Author: Groq / qwen/qwen3.8-27b\n'}, "files": ["ike/window.py"]}]
DRILL_FILES = [
    {"filename": drill.MARKER, "status": "added", "patch": "@@ -0,0 +1 @@\n+{}", "changes": 1},
    {"filename": drill.DATA, "status": "modified", "patch": "@@ -1 +1 @@\n-{}\n+{}", "changes": 2},
    {"filename": "ike/window.py", "status": "modified", "changes": 2,
     "patch": "@@ -6,0 +7,2 @@\n+        if self.label is None:\n+            return 0", "old_source": OLD_WIN,
     "new_source": NEW_WIN}]


def drill_pr(ref=BRANCH, title="DRILL: AUTOMAT, simulated update", labels=("automat-drill",)):
    return dict(mm.pr(ref), title=title, labels=[{"name": x} for x in labels])


def judged(p, review=mm.approved("a" * 40), files=DRILL_FILES, commits=DRILL_COMMITS):
    return merge.judge(REPO, p, commits, files, mm.FULL_CHECKS, lambda n: guard.allowed_path(n, False),
                       review=review, evidence=mm.with_no_regression(mm.VERIFIED), main_version="1.1.24")


def test_a_drill_is_judged_like_any_other_but_never_merged():
    # the very same pull request on a real candidate's branch would merge: so every check really ran
    real = dict(mm.pr("automation/update/drill-qt"), title="Update: x")
    assert drill.is_drill_pr(real)                 # its branch alone says it is a drill
    assert judged(drill_pr()) == ("drill", merge.DRILL_WHY)
    # any one mark is enough: the branch, the title, the label, the marker file
    for p, files in ((drill_pr(title="x", labels=()), DRILL_FILES),
                     (dict(mm.pr("automation/update/test-qt"), title="DRILL: x"), DRILL_FILES),
                     (dict(mm.pr("automation/update/test-qt"), title="x", labels=[{"name": "automat-drill"}]),
                      DRILL_FILES),
                     (dict(mm.pr("automation/update/test-qt"), title="x"), DRILL_FILES[:1])):
        assert drill.is_drill_pr(p, files), p
    assert not drill.is_drill_pr(dict(mm.pr("automation/update/test-qt"), title="Update: test-qt"), DRILL_FILES[2:])
    # what is not complete is said as for any candidate: the reviews, then "Nothing gets worse"
    assert judged(drill_pr(), review=None) == ("wait", merge.NO_REVIEW)
    kind, why = merge.judge(REPO, drill_pr(), DRILL_COMMITS, DRILL_FILES, mm.FULL_CHECKS,
                            lambda n: guard.allowed_path(n, False), review=mm.approved("a" * 40),
                            evidence=mm.with_no_regression(mm.VERIFIED, "failure"), main_version="1.1.24")
    assert kind == "person"
    assert merge.next_step(why, BRANCH, True) == "checks"
    # nothing about a drill is rebuilt by the daily maintenance, and no comment names the owner
    assert merge.rebuilt_daily(BRANCH) is False and merge.rebuilt_daily("automation/update/test-qt") is True
    for why in (merge.SECURITY_WHY + ": RUSTSEC-1", merge.TOKEN_WHY + " (x)", "the check tests did not pass"):
        assert "@NullSector-2077" not in merge.person_text(7, why, "NullSector-2077", "a" * 40, drill_pr=True)
    assert "@NullSector-2077" in merge.person_text(7, merge.SECURITY_WHY + ": x", "NullSector-2077", "a" * 40)


def test_merge_it_refuses_a_drill_before_any_call_that_writes(monkeypatch):
    calls = []
    monkeypatch.setattr(merge, "api", lambda path: DRILL_FILES if path.endswith("/files?per_page=100") else {})
    monkeypatch.setattr(merge, "gh", lambda *a, **k: calls.append(a) or "")
    for p in (drill_pr(), dict(mm.pr("automation/update/test-qt"), title="x")):
        with pytest.raises(RuntimeError, match="AUTOMAT drill"):
            merge.merge_it(REPO, p, "a" * 40)
    assert calls == []


def test_a_complete_drill_asks_for_its_report_and_names_nobody(monkeypatch):
    calls = []
    monkeypatch.setattr(merge, "gh", lambda *a, **k: calls.append(a) or "")
    merge.drill_complete(REPO, drill_pr(), "a" * 40)
    comment = [c for c in calls if c[:2] == ("pr", "comment")][0]
    body = comment[comment.index("--body") + 1]
    assert drill.DONE_MARK % ("a" * 40) in body and "@" not in body
    assert ("workflow", "run", "automat-drill.yml", "--repo", REPO, "--ref", "main", "-f", "action=tick") in calls
    assert not any("merge" in " ".join(c) for c in calls)
    # said once per commit
    calls.clear()
    monkeypatch.setattr(merge, "gh", lambda *a, **k: calls.append(a) or (drill.DONE_MARK % ("a" * 40)
                                                                         if a[0] == "api" else ""))
    merge.drill_complete(REPO, drill_pr(), "a" * 40)
    assert not [c for c in calls if c[:2] == ("pr", "comment")]


def test_the_signing_notice_and_the_ledger_leave_a_drill_out():
    merged = {"commits": [
        {"commit": {"message": "Merge pull request #50 from x\n\nDRILL: AUTOMAT"}, "parents": [1, 2]},
        {"commit": {"message": "Merge pull request #51: Update: crates (merged by itself: fully verified)"},
         "parents": [1, 2]}]}
    prs = {50: drill_pr(), 51: dict(mm.pr("automation/update/crates"), title="Update: crates", number=51)}
    ledger_body = {"entries": {
        "drill-qt@7.0": {"key": "drill-qt@7.0", "component": "drill-qt", "name": "drill", "state": "retrying",
                         "reason": "x", "via": BRANCH},
        "crates@2": {"key": "crates@2", "component": "crates", "name": "crates", "state": "retrying",
                     "reason": "y"}}}

    def api(path):
        if path.endswith("/releases/latest"):
            return {"tag_name": "v1.1.23"}
        if "/compare/" in path:
            return merged
        m = re.search(r"/pulls/(\d+)(/commits|/files)?", path)
        if m:
            n = int(m.group(1))
            return {None: prs[n], "/commits": [], "/files": DRILL_FILES if n == 50 else []}[m.group(2)]
        raise RuntimeError("not read")
    led = notice._tool("maintenance-ledger")
    orig = led.read_ledger
    try:
        notice._tool = (lambda real: (lambda name: _with_ledger(real(name), ledger_body) if name ==
                                      "maintenance-ledger" else real(name)))(notice._tool)
        info = notice.gather(REPO, api)
    finally:
        notice._tool = load("release-notice")._tool
        led.read_ledger = orig
    assert [c["n"] for c in info["changes"]] == [51]
    assert len(info["pending"]) == 1 and "crates" in info["pending"][0]
    # the ledger: a drill's branch is no update
    seen = []

    def lapi(path):
        seen.append(path)
        if path.startswith("repos/%s/pulls?" % REPO):
            return [{"number": 9, "head": {"ref": BRANCH, "sha": "a" * 40, "repo": {"full_name": REPO}}}]
        raise AssertionError("a drill's branch is never read for the ledger: %s" % path)
    assert ledger.update_branches(REPO, lapi) == {}


def _with_ledger(mod, body):
    mod.read_ledger = lambda repo, api: (1, body)
    return mod


# --- the plan, the help notice, what changed upstream --------------------------------------------------

def failed_run(**kw):
    run = {"name": "Tests", "head_branch": BRANCH, "conclusion": "failure", "_repo": REPO,
           "head_repository": {"full_name": REPO}, "head_sha": "t" * 40, "_tip": "t" * 40, "_main_tip": "m" * 40,
           "run_attempt": 2, "_attempts": 0, "_attempts_today": 0}
    run.update(kw)
    return run


def job(name, steps=("Tests",)):
    return {"name": name, "steps": [{"name": s, "conclusion": "failure"} for s in steps]}


def test_the_plan_fixes_a_drill_like_a_candidate_and_tells_nobody():
    cap = drill.attempts_for(BRANCH, plan_tool.ISOLATED_ATTEMPTS)
    if not ON_DRILL_BRANCH:                         # (a drill's branch holds the breaks only; main plans it)
        assert cap == MAIN_DATA["scenarios"]["qt"]["attempts_per_day"]
    assert drill.attempts_for("automation/update/test-qt", 4) == 4 and drill.attempts_for("main", 2) == 2
    p = plan_tool.decide(failed_run(), [job("tests")], "")
    assert p["action"] == "fix" and p["kind"] == "update" and p["push_branch"] == BRANCH
    p = plan_tool.decide(failed_run(_attempts=cap, _attempts_today=cap), [job("tests")], "")
    assert p["action"] == "retry"
    if cap > plan_tool.ISOLATED_ATTEMPTS:
        assert plan_tool.decide(failed_run(_attempts_today=plan_tool.ISOLATED_ATTEMPTS), [job("tests")], "")[
            "action"] == "fix"
    # the drill's Security run: no security branch, no issue
    sec = plan_tool.decide(failed_run(name="Security"), [job("sandbox", ("The sandbox is really on",))], "")
    assert sec["action"] == "skip" and "AUTOMAT drill" in sec["reason"]
    # what would open an issue (GitHub failed) is retried instead
    quiet = plan_tool.quiet_drill({"action": "issue", "reason": "GitHub failed"}, BRANCH)
    assert quiet["action"] == "retry" and "opens no issue" in quiet["reason"]
    assert plan_tool.quiet_drill({"action": "issue", "reason": "x"}, "main")["action"] == "issue"


def test_devi_aiutarci_con_chatgpt_in_drill_mode_is_an_exercise(tmp_path):
    mem = load("automat-memory")
    memory = mem.empty()
    failure = "FAILED tests/test_polish.py::test_touches_of_117 - AttributeError: no attribute 'findText'\n"
    sig = mem.signature(failure)
    for n in range(5):
        mem.note(memory, BRANCH, sig, "tests-failed", provider="Groq", attempt=n + 1)
    (tmp_path / "memory.json").write_text(json.dumps(memory))
    (tmp_path / "failure.md").write_text(failure)
    quota = {"schema": 1, "days": {}}
    (tmp_path / "quota.json").write_text(json.dumps(quota))
    calls = []

    def api(path, method="GET", data=None):
        calls.append((path, method, data))
        if method == "POST" and path.endswith("/issues"):
            return {"number": 77}
        return []
    args = ["check", "--repo", REPO, "--component", BRANCH, "--workflow", "Tests", "--checkout", "c" * 40,
            "--failure", str(tmp_path / "failure.md"), "--memory", str(tmp_path / "memory.json"),
            "--quota", str(tmp_path / "quota.json")]
    assert helper.main(args, env={}, api=api) == 0
    made = [d for p, m, d in calls if m == "POST" and p.endswith("/issues")]
    assert len(made) == 1
    issue = made[0]
    assert issue["title"].startswith("DRILL (esercitazione) " + helper.PHRASE)
    assert "assignees" not in issue and set(issue["labels"]) == {helper.LABEL, "automat-drill"}
    assert "@NullSector-2077" not in issue["body"] and "ESERCITAZIONE" in issue["body"].split("\n", 1)[0]
    assert "This is an AUTOMAT drill" in issue["body"] and helper.MARK % (sig, BRANCH) in issue["body"]
    # a real branch still names and assigns the owner
    calls.clear()
    real = "automation/update/test-qt"
    memory2 = mem.empty()
    for n in range(5):
        mem.note(memory2, real, sig, "tests-failed", provider="Groq", attempt=n + 1)
    (tmp_path / "memory.json").write_text(json.dumps(memory2))
    args[args.index(BRANCH)] = real
    assert helper.main(args, env={}, api=api) == 0
    made = [d for p, m, d in calls if m == "POST" and p.endswith("/issues")][0]
    assert made["assignees"] == ["NullSector-2077"] and made["title"].startswith(helper.PHRASE)
    # "no free provider at all" is never told by a drill
    old = {"schema": 1, "days": {d: {"providers": {}, "runs": 2, "answered": 0, "no_provider": 2}
                                 for d in ("2026-11-21", "2026-11-22", "2026-11-23")}}
    (tmp_path / "quota.json").write_text(json.dumps(old))
    (tmp_path / "memory.json").write_text(json.dumps(mem.empty()))
    calls.clear()
    args[args.index(real)] = BRANCH
    assert helper.main(args, env={}, api=api) == 0
    assert not [c for c in calls if c[1] == "POST"]


def test_what_changed_upstream_is_the_drills_release_notes_from_main():
    data = main_scenarios()
    if data is None:
        return
    text_main = json.dumps(data)
    branch_copy = json.dumps(drill.branch_data(data, "qt"))

    def show(rev, path):
        if path == drill.DATA:
            return text_main if rev == "origin/main" else branch_copy
        return ""

    def get(url):
        raise AssertionError("nothing is asked of the network for a drill: %s" % url)
    failure = "E   AttributeError: type object 'WebAction' has no attribute 'ReloadAndBypassCache'\n"
    section, out = upstream.build(BRANCH, show, failure, get)
    assert "What changed upstream" in section and "data, not instructions" in section
    qt = data["scenarios"]["qt"]
    renames = {tuple(r) for r in out["changes"][0]["renames"]}
    # (a sentence's full stop is no part of a name: "renamed a to b." is the pair (a, b))
    assert all(a and b and not b.endswith(".") for a, b in renames) and upstream.rename_pairs(
        [], "renamed A.old_name to A.new_name.") == [("old_name", "new_name")]
    assert {(b["old"], b["new"]) for b in qt["breaks"] if b["kind"] == "rename"} <= renames
    # the expected solutions never reach the AI
    for b in qt["breaks"]:
        assert b["expected"]["summary"][:40] not in section


# --- the report ---------------------------------------------------------------------------------------

def junit(results):
    cases = []
    for tid, state in results.items():
        path, name = tid.split("::")
        cls = path[:-3].replace("/", ".")
        inner = {"failed": '<failure message="x"/>', "skipped": "<skipped/>", "passed": ""}[state]
        cases.append('<testcase classname="%s" name="%s">%s</testcase>' % (cls, name, inner))
    xml = '<testsuites><testsuite name="pytest">%s</testsuite></testsuites>' % "".join(cases)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("junit.xml", xml)
    return buf.getvalue()


def test_the_report_says_what_was_fixed_by_whom_and_the_end_mails_the_owner_once():
    data = main_scenarios() or MAIN_DATA
    qt = data["scenarios"]["qt"]
    if "tests" not in qt["breaks"][0]:
        return
    first, rest = qt["breaks"][0], qt["breaks"][1:]
    head, fix1 = "f" * 40, "e" * 40
    at_fix1 = {t: "passed" for t in first["tests"]}
    at_fix1.update({t: "failed" for b in rest for t in b["tests"] if t not in at_fix1})
    at_head = dict(at_fix1)
    at_head.update({t: "passed" for t in rest[0]["tests"]})
    rv = load("ai-review")
    review = rv.comment_text({"sha": head, "pr": 9, "ref": BRANCH, "verdict": "approve", "author": "Z.AI", "why": "",
                              "files": ["ike/window.py"],
                              "reviews": [{"provider": "Groq", "model": "m", "verdict": "approve", "reasons": []},
                                          {"provider": "OpenRouter", "model": "m", "verdict": "approve",
                                           "reasons": []}]})
    pr = dict(drill_pr(), number=9, html_url="https://github.com/o/r/pull/9", created_at="2026-11-23T14:00:00Z",
              head={"ref": BRANCH, "sha": head, "repo": {"full_name": REPO}})
    commits = [
        {"sha": "b" * 40, "commit": {"message": "update: drill-qt a -> b (no AI)",
                                     "committer": {"date": "2026-11-23T14:00:00Z"}}},
        {"sha": fix1, "commit": {"message": 'autofix: attempt 1 after a failure of "Tests"\n\nx\nAuthor: Recipe / '
                                            'renamed-symbol\n', "committer": {"date": "2026-11-23T15:00:00Z"}}},
        {"sha": head, "commit": {"message": 'autofix: attempt 2 after a failure of "Tests"\n\nx\nAuthor: Z.AI / '
                                            'glm\n', "committer": {"date": "2026-11-23T16:30:00Z"}}}]
    runs = {fix1: 11, head: 12}
    junits = {11: junit(at_fix1), 12: junit(at_head)}
    calls = []

    def api(path, method="GET", data=None, raw=False, token=None):
        calls.append((path, method, data))
        if method != "GET":
            return {"number": 1}
        if path.startswith("repos/%s/pulls?state=open" % REPO):
            return [pr]
        if path.startswith("repos/%s/pulls?state=closed" % REPO):
            return []
        if path.endswith("/pulls/9/commits?per_page=100"):
            return commits
        if path.endswith("/issues/9/comments?per_page=100"):
            return [{"user": {"login": "github-actions[bot]"}, "body": review},
                    {"user": {"login": "github-actions[bot]"}, "body": drill.DONE_MARK % head}]
        m = re.search(r"actions/workflows/([a-z.]+)/runs\?.*head_sha=([0-9a-f]{40})", path)
        if m:
            wf, sha = m.groups()
            rid = runs.get(sha) if wf == "tests.yml" else None
            return {"workflow_runs": [{"id": rid, "head_sha": sha, "conclusion": "success", "status": "completed",
                                       "created_at": "x"}] if rid else []}
        m = re.search(r"actions/runs/(\d+)/jobs", path)
        if m:
            return {"jobs": [{"name": "tests", "conclusion": "success", "steps": [
                {"name": "Nothing gets worse", "conclusion": "success"}]}]}
        m = re.search(r"actions/runs/(\d+)/artifacts", path)
        if m:
            return {"artifacts": [{"id": int(m.group(1)), "name": "test-results"}]}
        m = re.search(r"actions/artifacts/(\d+)/zip", path)
        if m:
            return junits[int(m.group(1))]
        if "/issues?state=open&labels=automat-help" in path:
            return [{"number": 33, "user": {"login": "github-actions[bot]"}, "state": "open", "html_url": "u",
                     "body": helper.MARK % ("abcd1234", BRANCH)}]
        if "/issues?state=open&labels=automat-drill" in path:
            return [{"number": 30, "user": {"login": "github-actions[bot]"}, "body": "x\n" + drill.ISSUE_MARK % "qt-1"}]
        if path.endswith("/issues/30/comments?per_page=100"):
            return []
        return []
    memory = {"attempts": {BRANCH + "@sig1": [
        {"date": "2026-11-23", "attempt": 1, "provider": "Groq", "model": "m", "outcome": "guard-refused",
         "detail": "rule 1: an old statement changed", "files": ["ike/window.py"]},
        {"date": "2026-11-23", "attempt": 2, "provider": "Z.AI", "model": "glm", "outcome": "published",
         "detail": "", "files": ["ike/window.py"]}]}}
    quota = {"days": {"2026-11-23": {"providers": {"Z.AI": {"by": {BRANCH: {"requests": 7, "tokens": 51000}}},
                                                   "Groq": {"by": {"automation/update/crates": {"requests": 1,
                                                                                                "tokens": 9}}}}}}}
    info = drill.gather(REPO, api, memory, quota, now="2026-11-23T18:00:00+00:00", root=ROOT if not ON_DRILL_BRANCH
                        else None) if not ON_DRILL_BRANCH else None
    if info is None:
        return
    d = info["drills"][0]
    states = {b["id"]: b for b in d["breaks"]}
    assert states[first["id"]]["state"] == "fixed" and states[first["id"]]["by"] == "Recipe / renamed-symbol"
    assert states[first["id"]]["attempt"] == 1 and states[first["id"]]["after_hours"] == 1.0
    assert states[rest[0]["id"]]["state"] == "fixed" and states[rest[0]["id"]]["by"] == "Z.AI / glm"
    assert states[rest[0]["id"]]["after_hours"] == 2.5
    assert all(states[b["id"]]["state"] == "broken" for b in rest[1:] if not set(b["tests"]) & set(at_head)
               or any(at_head.get(t) == "failed" for t in b["tests"]))
    assert d["checks"]["no-regression"] == "passed" and d["complete"] is True
    assert d["quota"] == {"Z.AI": {"requests": 7, "tokens": 51000}}
    assert [r["verdict"] for r in d["reviews"]] == ["approve"] and d["help"] == [(33, "u", "open")]
    assert drill.due(info) == (True, "every break fixed, every check green and both reviews approve: the drill is "
                                     "complete")
    text = drill.markdown(info, final=True, why="completa")
    for word in ("Esercitazione AUTOMAT (DRILL)", "**risolto**", "non risolto", "Recipe / renamed-symbol",
                 "Z.AI / glm", "rule 1: an old statement changed", "51000 token", "no-regression): passed",
                 "Le soluzioni attese", first["expected"]["summary"][:30], "#33"):
        assert word in text, word
    assert "@" not in text.replace("@​", "")
    # the end: the owner is named once, on the drill's issue; the pull request and the help notice closed
    calls.clear()
    drill.finish(REPO, info, text, "NullSector-2077", api, "completa")
    posts = [(p, d) for p, m, d in calls if m == "POST"]
    named = [p for p, d in posts if "@NullSector-2077" in json.dumps(d)]
    assert named == ["repos/%s/issues/30/comments" % REPO]
    patches = {p: d for p, m, d in calls if m == "PATCH"}
    assert patches["repos/%s/pulls/9" % REPO] == {"state": "closed"}
    assert patches["repos/%s/issues/33" % REPO]["state"] == "closed"
    assert drill.FINAL_MARK % "qt-1" in json.dumps(posts)
    assert not any("/merge" in p for p, _m, _d in calls)


def test_the_drill_ends_after_its_hours_and_waits_before():
    info = {"now": "2026-11-25T15:00:00+00:00", "drills": [
        {"pr": {"number": 9}, "complete": False, "started": "2026-11-23T14:00:00Z", "hours": 48}]}
    assert drill.due(info)[0] is True and "48 hours" in drill.due(info)[1]
    info["now"] = "2026-11-24T15:00:00+00:00"
    assert drill.due(info) == (False, "")
    assert drill.with_report("a", "R1").endswith(drill.REPORT_END + "\n")
    twice = drill.with_report(drill.with_report("a", "R1"), "R2")
    assert "R1" not in twice and twice.count(drill.REPORT_BEGIN) == 1 and "R2" in twice


def test_the_drill_workflow_holds_no_key_and_runs_only_on_main():
    text = (WORKFLOWS / "automat-drill.yml").read_text()
    assert "\npermissions: {}\n" in text and "if: github.ref == 'refs/heads/main'" in text
    assert "GEMINI" not in text and "GROQ" not in text and "OPENROUTER" not in text and "ZAI" not in text
    assert "gh pr merge" not in text and "/merge" not in text and "pull_request" not in text
    assert "tools/automat-drill.py start" in text and "unset WORKFLOW_TOKEN" in text
    assert "persist-credentials: false" in text and "ref: main" in text
    # the one command of the owner's drill
    assert "gh workflow run automat-drill.yml --ref main" in text
    assert "gh workflow run automat-drill.yml --ref main" in (ROOT / "docs/MAINTENANCE.md").read_text()
