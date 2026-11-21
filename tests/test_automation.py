"""The automation around updates and fixes (no browser, no network).

- tools/check-autofix-patch.py: what an automatic fix may and may not change,
  on real git repositories in a temporary folder;
- tools/autofix-plan.py: which failures are fixed, where the fix goes, the
  limit of attempts, forks and the standby branches left alone;
- tools/automation-health.py: the problems the weekly check reports;
- tools/prepare-maintenance.py: no new version for the test packages alone, a
  CHANGELOG line of an automatic fix, a version not yet released kept;
- the workflows: the agent's job has no write permission and is the only one
  with the API key, nothing runs code of forks, the tools come from main.
"""

import datetime as dt
import importlib.util
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), ROOT / "tools" / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


guard = load("check-autofix-patch")
plan_tool = load("autofix-plan")
health = load("automation-health")


def git(repo, *args, stdin=None):
    return subprocess.run(["git", "-C", str(repo), *args], input=stdin, capture_output=True,
                          text=True, check=True).stdout


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    files = {
        "ike/window.py": "def width():\n    return 10\n",
        "ike/__init__.py": '__version__ = "1.1.10"\n',
        "ike/blocker.py": "BLOCK = True\n",
        "ike/updater.py": "CHECK = True\n",
        "tests/test_window.py": "def test_width():\n    assert 1\n    assert 2\n",
        "tests/conftest.py": "",
        "tools/check-components.py": "X = 1\n",
        "docs/MAINTENANCE.md": "# Maintenance\n",
        "PKGBUILD": "pkgver=1.1.10\n",
        "data/update.json": "{}\n",
        ".github/workflows/tests.yml": "name: Tests\n",
        "ike-adblock/src/lib.rs": "// engine\n",
    }
    for rel, text in files.items():
        p = r / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    git(r.parent, "init", "-q", str(r))
    git(r, "-c", "user.name=t", "-c", "user.email=t@t", "add", "-A")
    git(r, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "base")
    return r


def make_patch(repo, change):
    """The patch of `change(repo)`, with the repository put back as it was."""
    change(repo)
    git(repo, "add", "-A")
    patch = git(repo, "diff", "--cached", "--binary")
    git(repo, "reset", "-q", "--hard")
    git(repo, "clean", "-qfd")
    return patch


def edit(rel, text, mode="w"):
    def change(repo):
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, mode) as f:
            f.write(text)
    return change


def run_guard(repo, patch, tmp_path, *extra):
    pf = tmp_path / "fix.patch"
    pf.write_text(patch)
    report = tmp_path / "guard.md"
    code = guard.main(["--repo", str(repo), "--patch", str(pf), "--report", str(report), *extra])
    return code, report.read_text() if report.exists() else ""


# --- the patch check ---------------------------------------------------------

def test_a_small_fix_of_the_code_is_applied(repo, tmp_path):
    patch = make_patch(repo, edit("ike/window.py", "def width():\n    return 12\n"))
    code, report = run_guard(repo, patch, tmp_path)
    assert code == 0 and "ike/window.py" in report
    assert "return 12" in (repo / "ike/window.py").read_text()          # applied
    assert git(repo, "diff", "--cached", "--name-only").split() == ["ike/window.py"]


def test_a_test_may_be_corrected_without_weakening_it(repo, tmp_path):
    patch = make_patch(repo, edit("tests/test_window.py", "def test_width():\n    assert 1\n    assert len(\"ab\") == 2\n"))
    assert run_guard(repo, patch, tmp_path)[0] == 0


@pytest.mark.parametrize("rel", [".github/workflows/tests.yml", "PKGBUILD", "data/update.json",
                                 "ike/__init__.py", "ike/updater.py", "tests/conftest.py",
                                 "README.md", "launcher/x.c", "ike_boot.py", "pyproject.toml"])
def test_protected_files_are_refused(repo, tmp_path, rel):
    patch = make_patch(repo, edit(rel, "# changed\n", "a"))
    code, report = run_guard(repo, patch, tmp_path)
    assert code == 3 and rel in report          # a safety refusal: no other assistant is asked
    assert (repo / "ike/window.py").read_text() == "def width():\n    return 10\n"   # nothing applied
    assert git(repo, "status", "--porcelain") == ""


def test_the_ad_blocker_only_with_an_engine_update(repo, tmp_path):
    for rel in ("ike-adblock/src/lib.rs", "ike/blocker.py"):
        patch = make_patch(repo, edit(rel, "// fixed\n", "a"))
        code, report = run_guard(repo, patch, tmp_path)
        assert code == 3 and "ad blocker" in report
        code, _ = run_guard(repo, patch, tmp_path, "--allow-adblock")
        assert code == 0
        git(repo, "reset", "-q", "--hard")


@pytest.mark.parametrize("line", ["    pytest.skip('flaky')\n", "@pytest.mark.xfail\n",
                                  "    pytest.importorskip('x')\n"])
def test_skips_and_xfails_are_refused(repo, tmp_path, line):
    patch = make_patch(repo, edit("tests/test_window.py", line, "a"))
    code, report = run_guard(repo, patch, tmp_path)
    assert code == 3 and "skip or xfail" in report


def test_removed_assertions_and_tests_are_refused(repo, tmp_path):
    patch = make_patch(repo, edit("tests/test_window.py", "def test_width():\n    assert 1\n"))
    code, report = run_guard(repo, patch, tmp_path)
    assert code == 3 and "assertion(s) removed" in report
    patch = make_patch(repo, lambda r: (r / "tests/test_window.py").unlink())
    code, report = run_guard(repo, patch, tmp_path)
    assert code == 3 and "test file removed" in report


def test_keys_binaries_links_and_size_are_refused(repo, tmp_path):
    key = "AIza" + "B" * 35
    patch = make_patch(repo, edit("ike/window.py", "KEY = '%s'\n" % key, "a"))
    assert "key or token" in run_guard(repo, patch, tmp_path)[1]
    pem = "-----BEGIN " + "PRIVATE" + " KEY-----"       # built here: no key marker in this file
    patch = make_patch(repo, edit("docs/MAINTENANCE.md", pem + "\nMC4CAQAwBQYDK2VwBCIEI\n", "a"))
    assert "key or token" in run_guard(repo, patch, tmp_path)[1]
    patch = make_patch(repo, lambda r: (r / "ike/icon.bin").write_bytes(b"\0\1\2\3" * 50))
    assert "binary" in run_guard(repo, patch, tmp_path)[1]
    patch = make_patch(repo, lambda r: (r / "ike/link.py").symlink_to("/etc/passwd"))
    assert "link" in run_guard(repo, patch, tmp_path)[1]
    patch = make_patch(repo, lambda r: [edit("ike/m%d.py" % i, "x = 1\n")(r) for i in range(guard.MAX_FILES + 1)])
    assert "too many files" in run_guard(repo, patch, tmp_path)[1]
    patch = make_patch(repo, edit("ike/big.py", "x = 1\n" * (guard.MAX_LINES + 1)))
    assert "too many changed lines" in run_guard(repo, patch, tmp_path)[1]


def test_paths_outside_the_repository_are_refused(repo, tmp_path):
    patch = ("diff --git a/../evil.py b/../evil.py\nnew file mode 100644\n--- /dev/null\n"
             "+++ b/../evil.py\n@@ -0,0 +1 @@\n+x = 1\n")
    code, report = run_guard(repo, patch, tmp_path)
    assert code == 3
    assert not (repo.parent / "evil.py").exists()


def test_an_empty_patch_is_not_a_fix(repo, tmp_path):
    assert run_guard(repo, "", tmp_path)[0] == 2


# --- the plan ------------------------------------------------------------------

def failed_run(name="Tests", branch="main", **kw):
    run = {"name": name, "head_branch": branch, "conclusion": "failure", "head_sha": "abc",
           "head_repository": {"full_name": "o/r"}, "_repo": "o/r", "_tip": "abc",
           "_main_tip": "main1", "_attempts": 0, "_engine_update": False}
    run.update(kw)
    return run


def job(name):
    return {"name": name, "conclusion": "failure"}


def test_plan_tests_failing_on_main_get_a_fix_branch():
    p = plan_tool.decide(failed_run(), [job("tests")], "")
    assert p["action"] == "fix" and p["kind"] == "main"
    assert p["push_branch"] == "automation/autofix-main" and p["checkout"] == "main1" and p["attempt"] == "1"


def test_plan_maintenance_candidate_is_fixed_on_its_branch():
    p = plan_tool.decide(failed_run(branch="automation/daily-maintenance", _attempts=1,
                                    _engine_update=True), [job("tests")], "")
    assert p["action"] == "fix" and p["kind"] == "maintenance" and p["attempt"] == "2"
    assert p["push_branch"] == "automation/daily-maintenance" and p["checkout"] == "abc"
    assert p["allow_adblock"] == "true"


def test_plan_stops_after_two_attempts():
    p = plan_tool.decide(failed_run(branch="automation/autofix-main", _attempts=2), [job("tests")], "5")
    assert p["action"] == "issue" and "2 automatic fixes" in p["reason"]


@pytest.mark.parametrize("run,why", [
    (failed_run(branch="windows/port"), "not one the automation fixes"),
    (failed_run(branch="shield-in-urlbar"), "not one the automation fixes"),
    (failed_run(head_repository={"full_name": "someone/fork"}), "fork"),
    (failed_run(conclusion="success"), "did not fail"),
    (failed_run(_tip="newer"), "older failure"),
    (failed_run(name="Windows"), "not handled"),
])
def test_plan_leaves_other_runs_alone(run, why):
    p = plan_tool.decide(run, [job("tests")], "")
    assert p["action"] == "skip" and why in p["reason"]


NOW = dt.datetime(2026, 11, 20, 12, tzinfo=dt.timezone.utc)


def report(name, sha="", hours=1):
    """An open issue of the report job, `hours` old, naming the commit sha."""
    when = (NOW - dt.timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    body = "x" + ("\n" + plan_tool.SHA_MARK % sha if sha else "")
    return {"title": plan_tool.ISSUE_TITLE % name, "body": body, "reported_at": when}


def test_plan_one_fix_of_main_at_a_time_and_no_repeats():
    assert plan_tool.decide(failed_run(), [job("tests")], "31")["action"] == "skip"
    p = plan_tool.decide(failed_run(name="Daily component check"), [job("check")], "",
                         [report("Daily component check")], now=NOW)
    assert p["action"] == "skip" and "already reported" in p["reason"]


def test_an_old_issue_never_blocks_a_new_failure():
    """1.1.18: issue #31 of the first trials ("Automatic fix needs you: Tests",
    weeks old, another commit) kept every later failure of main from a fix."""
    run = failed_run(head_sha="abc1234def", _tip="abc1234def")
    for issues in ([report("Tests", hours=24 * 20)],                      # old, no commit named
                   [report("Tests", sha="0123456789", hours=30)],         # old, another commit
                   [report("Daily component check", sha="abc1234def")]):  # another workflow
        p = plan_tool.decide(run, [job("tests")], "", issues, now=NOW)
        assert p["action"] == "fix", (issues, p)
    # the same commit, however old the issue, or any report of the last 24 hours: wait
    for issues in ([report("Tests", sha="abc1234def", hours=24 * 20)], [report("Tests", hours=3)],
                   [report("Tests", sha="abc1234", hours=24 * 20)]):
        p = plan_tool.decide(run, [job("tests")], "", issues, now=NOW)
        assert p["action"] == "skip" and "already reported" in p["reason"], issues
    # the report job writes the same mark the plan reads
    text = (WORKFLOWS / "autofix.yml").read_text()
    assert "printf '\\n%s\\n' \"$HEAD_SHA\" \"$BRANCH\"" % (plan_tool.SHA_BRANCH_MARK % ("%s", "%s")) in text
    assert "HEAD_SHA: ${{ needs.plan.outputs.head_sha }}" in jobs_of(text)["report"]


def test_open_reports_read_the_comments_too(monkeypatch):
    title = plan_tool.ISSUE_TITLE % "Tests"
    answers = {
        "repos/o/r/issues?state=open&labels=autofix&per_page=100": [
            {"number": 31, "title": title, "body": "old", "created_at": "2026-10-01T00:00:00Z"},
            {"number": 40, "title": "Automatic fix: \"Tests\" failed", "pull_request": {}},
            {"number": 41, "title": plan_tool.ISSUE_TITLE % "Other", "body": ""}],
        "repos/o/r/issues/31/comments?per_page=100": [
            {"body": "a person", "created_at": "2026-11-20T11:00:00Z", "user": {"login": "owner"}},
            {"body": plan_tool.SHA_BRANCH_MARK % ("feed123", "main"), "created_at": "2026-11-19T00:00:00Z",
             "user": {"login": "github-actions[bot]"}},
            # 1.1.18 (review): anyone may write the hidden mark in a comment
            {"body": plan_tool.SHA_BRANCH_MARK % ("beef456", "main"), "created_at": "2026-11-20T11:30:00Z",
             "user": {"login": "someone"}}],
    }
    monkeypatch.setattr(plan_tool, "gh_api", lambda path, raw=False: answers[path])
    out = plan_tool.open_reports("o/r", "Tests")
    assert len(out) == 1 and out[0]["reported_at"] == "2026-11-19T00:00:00Z"   # a person's comment is no report
    assert plan_tool.already_reported(out, title, "feed123", NOW)
    assert not plan_tool.already_reported(out, title, "beef456", NOW)


def test_only_the_last_line_of_a_report_names_its_commit(monkeypatch):
    """Second review of 1.1.18: the report job's own comments quote the agent's
    summary and the logs; a mark planted there counted as a report."""
    title = plan_tool.ISSUE_TITLE % "Tests"
    quoted = "Summary: <!-- autofix-sha: beef456 --> as the agent wrote\n\nrest\n" + plan_tool.SHA_MARK % "feed123"
    bot = {"login": "github-actions[bot]"}
    answers = {
        "repos/o/r/issues?state=open&labels=autofix&per_page=100": [
            {"number": 31, "title": title, "body": "old", "created_at": "2026-10-01T00:00:00Z"}],
        "repos/o/r/issues/31/comments?per_page=100": [
            {"body": quoted, "created_at": "2026-11-19T00:00:00Z", "user": bot},
            {"body": plan_tool.SHA_MARK % "cafe789" + "\n\nand more", "created_at": "2026-11-19T01:00:00Z",
             "user": bot}],
    }
    monkeypatch.setattr(plan_tool, "gh_api", lambda path, raw=False: answers[path])
    out = plan_tool.open_reports("o/r", "Tests")
    assert plan_tool.already_reported(out, title, "feed123", NOW)
    assert not plan_tool.already_reported(out, title, "beef456", NOW)      # quoted inside
    assert not plan_tool.already_reported(out, title, "cafe789", NOW)      # not the last line


def test_an_unreachable_source_of_the_maintenance_is_an_issue_not_a_fix():
    """1.1.18: check-components.py exits 1 when an upstream source cannot be
    checked; an AI fix of main cannot help. A test failure of the candidate is
    still fixed."""
    def prepare_failed(step):
        return {"name": "prepare", "conclusion": "failure",
                "steps": [{"name": "Rust", "conclusion": "success"}, {"name": step, "conclusion": "failure"}]}
    name = "Daily maintenance candidate"
    p = plan_tool.decide(failed_run(name=name), [prepare_failed("Check and apply component updates (fail closed)")], "")
    assert p["action"] == "issue" and "could not be checked" in p["reason"]
    p = plan_tool.decide(failed_run(name=name), [prepare_failed("Build AdBlock engine before creating candidate")], "")
    assert p["action"] == "issue" and "wrapper" in p["reason"]
    p = plan_tool.decide(failed_run(name=name), [prepare_failed("Prepare the IKE patch release candidate")], "")
    assert p["action"] == "fix" and p["kind"] == "main"
    p = plan_tool.decide(failed_run(branch="automation/daily-maintenance"), [job("tests")], "")
    assert p["action"] == "fix" and p["kind"] == "maintenance"
    workflow = (WORKFLOWS / "daily-maintenance.yml").read_text()
    for step in (plan_tool.SOURCES_STEP, plan_tool.ENGINE_STEP):
        assert "- name: " + step in workflow, step


def test_plan_settings_and_workflow_problems_become_an_issue():
    p = plan_tool.decide(failed_run(name="Daily maintenance candidate"), [job("publish-candidate")], "")
    assert p["action"] == "issue" and "setting" in p["reason"]
    p = plan_tool.decide(failed_run(name="Daily component check"), [job("update-issue")], "")
    assert p["action"] == "issue"
    p = plan_tool.decide(failed_run(name="Daily component check"), [job("check")], "")
    assert p["action"] == "fix" and p["kind"] == "main"


def test_plan_logs_are_cleaned_and_cut():
    raw = "\n".join("2026-11-17T06:13:41.9029797Z \x1b[36;1mline %d\x1b[0m" % i for i in range(2000))
    out = plan_tool.clean_log(raw)
    assert "\x1b" not in out and "2026-11-17T" not in out
    assert out.endswith("line 1999") and "line 1000\n" not in out
    assert len(out) <= plan_tool.LOG_BYTES


# --- the weekly health check -------------------------------------------------------

def test_health_finds_what_stopped():
    now = dt.datetime(2026, 11, 20, tzinfo=dt.timezone.utc)

    def r(day, conclusion="success"):
        return {"status": "completed", "conclusion": conclusion, "html_url": "u%d" % day,
                "created_at": "2026-11-%02dT06:17:00Z" % day}
    ok = {"daily-check.yml": [r(20), r(19)], "daily-maintenance.yml": [r(20)]}
    assert health.problems(now, ok, [r(19)], True) == []
    found = health.problems(now, {"daily-check.yml": [r(10)], "daily-maintenance.yml": []},
                            [r(19, "failure")], False)
    text = "\n".join(found)
    assert "has not run since 2026-11-10" in text and "never run" in text
    assert "tests fail on main" in text and "GEMINI_API_KEY" in text
    failing = {"daily-check.yml": [r(20, "failure"), r(19, "failure"), r(18, "failure")],
               "daily-maintenance.yml": [r(20)]}
    assert "failed in its last 3" in "\n".join(health.problems(now, failing, [], True))


def test_health_finds_what_waits_or_is_missing():
    """1.1.18: failed automatic fixes, the reserves' keys, issues and maintenance
    pull requests waiting for a week, main without protection."""
    now = dt.datetime(2026, 11, 20, tzinfo=dt.timezone.utc)
    ok = {"daily-check.yml": [{"status": "completed", "conclusion": "success", "html_url": "d",
                               "created_at": "2026-11-20T05:17:00Z"}],
          "daily-maintenance.yml": [{"status": "completed", "conclusion": "success", "html_url": "m",
                                     "created_at": "2026-11-20T06:17:00Z"}]}

    def item(day, **kw):
        return dict({"created_at": "2026-11-%02dT08:00:00Z" % day, "html_url": "u%d" % day}, **kw)
    found = "\n".join(health.problems(
        now, ok, [], True,
        autofix_runs=[item(19, conclusion="failure"), item(18, conclusion="success"), item(1, conclusion="failure")],
        reserve_keys={"GROQ_API_KEY": False, "OPENROUTER_API_KEY": True},
        autofix_issues=[item(2, title="Automatic fix needs you: Tests"), item(18, title="new"),
                        item(1, title="a pull request", pull_request={})],
        maintenance_prs=[item(3, title="Maintenance candidate: IKE 1.1.18"), item(19, title="fresh")],
        main_protected=False, unreadable=["the runs of the automatic fix"]))
    assert "automatic fix failed 1 time(s)" in found and "u19" in found
    assert "`GROQ_API_KEY` is missing" in found and "OPENROUTER_API_KEY" not in found
    assert "Automatic fix needs you: Tests" in found and "\"new\"" not in found and "a pull request" not in found
    assert "Maintenance candidate: IKE 1.1.18" in found and "fresh" not in found
    assert "`main` has no branch protection" in found and "Could not check the runs" in found
    assert health.problems(now, ok, [], True, reserve_keys={"GROQ_API_KEY": True}, main_protected=True) == []
    text = (WORKFLOWS / "health.yml").read_text()
    for name in ("GROQ_API_KEY", "OPENROUTER_API_KEY"):
        assert "${{ secrets.%s != '' }}" % name in text, name      # whether it is set, never its value
    assert "pull-requests: read" in text


def test_every_scheduled_workflow_is_kept_turned_on():
    """GitHub turns scheduled workflows off after 60 days without activity in
    a public repository; health.yml turns on again every one it finds."""
    text = (WORKFLOWS / "health.yml").read_text()
    assert "for f in .github/workflows/*.yml" in text and "grep -q '^  schedule:'" in text
    scheduled = [p.name for p in WORKFLOWS.glob("*.yml") if "\n  schedule:" in p.read_text()]
    assert {"daily-check.yml", "daily-maintenance.yml", "health.yml", "arch.yml", "security.yml"} <= set(scheduled)


# --- the maintenance version --------------------------------------------------------

def prepare(tmp_path, *args):
    root = tmp_path / "repo"
    if not root.exists():
        for rel in ("ike/__init__.py", "PKGBUILD", "README.md"):
            dest = root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(ROOT / rel, dest)
        (root / "CHANGELOG.md").write_text("# Changelog\n\n## 1.0.0\n\n- First release.\n", "utf-8")
    if args:
        subprocess.run(["python3", str(ROOT / "tools/prepare-maintenance.py"), "--root", str(root), *args],
                       check=True)
    return root


def version(root):
    return re.search(r'__version__ = "([^"]+)"', (root / "ike/__init__.py").read_text()).group(1)


def test_test_packages_alone_make_no_release(tmp_path):
    report = tmp_path / "report.json"
    report.write_text(json.dumps({"errors": 0, "components": [{
        "name": "Qt WebEngine / PyQt6 (tests)", "current": "6.12.0", "latest": "6.12.1",
        "update": True, "note": "", "also": ""}]}))
    root = prepare(tmp_path)
    before = version(root)
    prepare(tmp_path, "--report", str(report), "--base-version", before)
    assert version(root) == before
    assert (root / "CHANGELOG.md").read_text().count("##") == 1


def test_automatic_fix_line_and_unreleased_version(tmp_path):
    root = prepare(tmp_path, "--base-version", "1.0.0", "--bullet", "- Automatic fix after a failure.")
    assert version(root) == "1.0.1"
    log = (root / "CHANGELOG.md").read_text()
    assert log.startswith("# Changelog\n\n## 1.0.1\n") and "- Automatic fix after a failure." in log
    # 1.0.1 is not released yet: a second change goes into the same version
    prepare(tmp_path, "--base-version", "1.0.1", "--keep-version", "--bullet", "- Another fix.")
    assert version(root) == "1.0.1"
    log = (root / "CHANGELOG.md").read_text()
    assert log.count("## 1.0.1") == 1 and "- Another fix." in log


# --- the workflows ---------------------------------------------------------------------

def jobs_of(text):
    """job name -> its text, for the simple layout of these workflows."""
    body = text.split("\njobs:\n", 1)[1]
    parts = re.split(r"^  ([a-z-]+):\n", body, flags=re.M)
    return dict(zip(parts[1::2], parts[2::2]))


def test_autofix_workflow_permissions():
    text = (WORKFLOWS / "autofix.yml").read_text()
    jobs = jobs_of(text)
    assert set(jobs) == {"plan", "rerun", "fix", "guard", "publish", "report", "self-test"}
    assert "permissions: {}" in text and "pull_request_target" not in text
    # the agent: read only, the only job with the key, no GitHub token
    assert re.search(r"permissions:\n\s+contents: read\n\s+outputs:", jobs["fix"])
    assert "secrets.GEMINI_API_KEY" in jobs["fix"]
    assert "github.token" not in jobs["fix"] and "GH_TOKEN" not in jobs["fix"]
    for name in ("plan", "guard", "publish", "report"):
        assert "secrets." not in jobs[name], name
    for name in ("plan", "fix", "guard", "publish"):
        assert "persist-credentials: false" in jobs[name], name
    assert "contents: write" not in jobs["guard"] and "contents: write" not in jobs["plan"]
    # instructions and checking tools come from main, not from the branch being fixed
    assert "git show origin/main:.github/autofix/prompt.md" in jobs["fix"]
    assert 'git show "origin/main:tools/$f"' in jobs["guard"]
    assert "--force-with-lease" in jobs["publish"] and "gh pr merge" not in text
    assert "gh release" not in text and "main:refs/heads/main" not in text
    assert '"modelProvider": "gemini"' in jobs["fix"]
    assert 'git show "origin/main:tools/$f"' in jobs["fix"]
    for tool in ("autofix-agent.py", "autofix-context.py", "autofix-reserve.py"):
        assert tool in jobs["fix"], tool
    # the reserves: their keys only in the fix job, after Antigravity
    for name in ("GROQ_API_KEY", "OPENROUTER_API_KEY"):
        assert "secrets." + name in jobs["fix"], name
    assert jobs["fix"].index("autofix-agent.py\" --workdir") < jobs["fix"].index("autofix-reserve.py\" --workdir")
    assert "--related" in jobs["guard"]
    # the closed room: own user, no terminal or web for the agent, only the Gemini API
    for rule in ('"command(*)"', '"read_url(*)"', '"execute_url(*)"', '"mcp(*)"', "--uid-owner agent",
                 "generativelanguage.googleapis.com", "env -i", "the firewall does not hold"):
        assert rule in jobs["fix"], rule
    assert re.search(r"timeout-minutes: \d+", jobs["fix"])


def test_the_agent_switches_model_only_when_it_helps():
    agent = load("autofix-agent")
    assert agent.models("") == list(agent.FREE_MODELS)
    assert agent.models("Gemini 4 Argon (High), Gemini 3.8 Flash (High)")[:2] == [
        "Gemini 4 Argon (High)", "Gemini 3.8 Flash (High)"]
    assert len(agent.models("Gemini 3.8 Flash (High)")) == len(agent.FREE_MODELS)
    err = lambda code, status, msg: 'AGY_ERROR:{"error_code": %d, "status": "%s"}\n%s' % (code, status, msg)
    day = err(429, "RESOURCE_EXHAUSTED", "quotaId: GenerateRequestsPerDayPerProjectPerModel-FreeTier")
    minute = err(429, "RESOURCE_EXHAUSTED", "GenerateRequestsPerMinutePerProjectPerModel retryDelay: 40s")
    assert agent.classify(1, day)[0] == "day"
    assert agent.classify(1, minute) == ("minute", 40)
    assert agent.classify(1, err(400, "INVALID_ARGUMENT", "API key not valid. API_KEY_INVALID"))[0] == "auth"
    assert agent.classify(1, err(403, "PERMISSION_DENIED", ""))[0] == "auth"
    assert agent.classify(1, err(404, "NOT_FOUND", "model not found"))[0] == "config"
    assert agent.classify(1, err(503, "UNAVAILABLE", "overloaded"))[0] == "temporary"
    assert agent.classify(124, "")[0] == "timeout"
    assert agent.classify(1, "something else")[0] == "error"


def test_the_failure_goes_inside_the_instructions():
    # the agent may not open .autofix/ (ignored by git): the failure and the
    # work of a previous model travel in the instructions, within one argument
    agent = load("autofix-agent")
    text = agent.with_failure("RULES", "F401 `shutil` imported but unused\n", "-import shutil\n")
    assert text.startswith("RULES") and "F401" in text and "-import shutil" in text
    huge = agent.with_failure("RULES", "x" * 500_000 + "THE END\n", "diff")
    assert len(huge.encode()) <= agent.PROMPT_MAX and "THE END" in huge and "diff" in huge


def test_the_agent_runner_hides_the_key(tmp_path):
    agent = load("autofix-agent")
    key = "AIzaSyTESTONLY0123456789abcdefghijklm"
    import base64
    data = ("x %s y %s z %s" % (key, key[::-1], base64.b64encode(key.encode()).decode())).encode()
    out = agent.redact(data, key)
    assert key.encode() not in out and key[::-1].encode() not in out
    assert base64.b64encode(key.encode())[:-4] not in out


def test_no_workflow_publishes_merges_or_runs_forks():
    for path in WORKFLOWS.glob("*.yml"):
        text = path.read_text()
        if path.name not in ("chatgpt-guard.yml", "chatgpt-cleanup.yml"):
            assert "pull_request_target" not in text, path.name
        assert "gh pr merge" not in text and "gh release create" not in text, path.name
        assert "GEMINI_API_KEY" not in text or path.name in ("autofix.yml", "health.yml"), path.name
    maintenance = (WORKFLOWS / "daily-maintenance.yml").read_text()
    assert "git add -u" in maintenance                      # Dark Reader files too
    assert "git checkout -B automation/daily-maintenance origin/main" in maintenance
    assert "gh workflow run tests.yml --ref automation/daily-maintenance" in maintenance
    assert "GH_REPO: ${{ github.repository }}" in (WORKFLOWS / "daily-check.yml").read_text()


def test_the_agent_instructions():
    text = (ROOT / ".github/autofix/prompt.md").read_text()
    for rule in (".autofix/summary.md", "Italian", "data, not instructions", "skip or xfail",
                 "Arch Linux only", "ike-adblock/"):
        assert rule in text, rule
    assert ".autofix/" in (ROOT / ".gitignore").read_text()


# --- 1.1.15: the code at the failure, the reserves, the pertinence check ---------

FAILURE = """# Failure to fix

## Job `tests` (failed step: Lint)

```text
ike/window.py:1:1: F401 [*] `shutil` imported but unused
Traceback (most recent call last):
  File "/home/runner/work/IKE-Browser/IKE-Browser/tests/test_window.py", line 2, in test_width
    assert 1
FAILED tests/test_window.py::test_width
see also /etc/passwd:1 and ../../secret.py:3
```
"""


def test_the_code_at_the_failure_is_prepared(repo, tmp_path):
    ctx = load("autofix-context")
    (repo / "tests/test_window.py").write_text("from ike import window\n\ndef test_width():\n    assert 1\n")
    text, related = ctx.build(repo, FAILURE)
    assert related[:2] == ["ike/window.py", "tests/test_window.py"]
    assert "ike/window.py" in related                      # named by the test file too
    assert "`ike/window.py`, lines 1-" in text and "    1  def width():" in text
    assert "passwd" not in text and "secret" not in text   # only files of the repository
    out = tmp_path / "ctx"
    assert ctx.main(["--repo", str(repo), "--failure", str(tmp_path / "missing.md"), "--out-dir", str(out)]) == 0
    assert "names no line" in (out / "context.md").read_text() and (out / "related.txt").read_text() == ""


def test_a_fix_must_touch_the_files_involved(repo, tmp_path):
    related = tmp_path / "related.txt"
    related.write_text("ike/window.py\n")
    elsewhere = make_patch(repo, edit("ike/other.py", "x = 1\n"))
    code, report = run_guard(repo, elsewhere, tmp_path, "--related", str(related))
    assert code == 1 and "none of the files involved" in report
    here = make_patch(repo, edit("ike/window.py", "def width():\n    return 11\n"))
    assert run_guard(repo, here, tmp_path, "--related", str(related))[0] == 0


class _Answer:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self, n=-1):
        return self.body


def _opener(answers, seen):
    import json
    import urllib.error

    def open_(req, timeout=0):
        seen.append((req.full_url, json.loads(req.data)["model"], req.get_header("Authorization")))
        a = answers.pop(0)
        if isinstance(a, tuple):                    # (status, headers)
            raise urllib.error.HTTPError(req.full_url, a[0], "err", a[1], None)
        if isinstance(a, int):
            raise urllib.error.HTTPError(req.full_url, a, "err", {}, None)
        return _Answer(json.dumps({"choices": [{"message": {"content": a}}]}).encode())
    return open_


def _reserve_repo(repo):
    auto = repo / ".autofix"
    auto.mkdir(exist_ok=True)
    (auto / "failure.md").write_text(FAILURE)
    (auto / "context.md").write_text("# Code at the failure\n")
    (auto / "related.txt").write_text("ike/window.py\n")


def test_the_reserves_one_after_the_other(repo, tmp_path):
    import json
    reserve = load("autofix-reserve")
    _reserve_repo(repo)
    prompt = tmp_path / "prompt.md"
    prompt.write_text("RULES")
    good = json.dumps({"summary": "Corretto il valore.", "fixable": True, "edits": [
        {"file": "ike/window.py", "find": "    return 10\n", "replace": "    return 11\n"}]})
    seen = []
    env = {"GROQ_API_KEY": "gsk_TESTONLY", "OPENROUTER_API_KEY": "sk-or-TESTONLY",
           "AUTOFIX_GROQ_MODELS": "g1", "AUTOFIX_OPENROUTER_MODELS": "a:free, b:free"}
    # Groq out of quota, OpenRouter's first model answers badly twice, the second one fixes it
    answers = [429, "not json", '{"edits": [{"file": "ike/window.py", "find": "nope", "replace": "x"}]}', good]
    status = tmp_path / "status.json"
    reserve.main(["--workdir", str(repo), "--prompt", str(prompt), "--status", str(status)],
                 env=env, opener=_opener(answers, seen))
    out = json.loads(status.read_text())
    assert out["result"] == "ok" and "OpenRouter / b:free" in out["model"], out
    assert [s[0].split("/")[2] for s in seen] == ["api.groq.com", "openrouter.ai", "openrouter.ai", "openrouter.ai"]
    assert (repo / "ike/window.py").read_text() == "def width():\n    return 11\n"
    summary = (repo / ".autofix/summary.md").read_text()
    assert "Corretto il valore." in summary and "TESTONLY" not in summary


def test_the_reserves_never_touch_other_files_and_skip_missing_keys(repo, tmp_path):
    import json
    reserve = load("autofix-reserve")
    _reserve_repo(repo)
    prompt = tmp_path / "prompt.md"
    prompt.write_text("RULES")
    status = tmp_path / "status.json"
    # no key at all: nothing is asked
    reserve.main(["--workdir", str(repo), "--prompt", str(prompt), "--status", str(status)],
                 env={}, opener=_opener([], []))
    assert json.loads(status.read_text())["result"] == "nokey"
    # an edit of a file that was not shown, or outside the repository: refused, nothing written
    for path in ("ike/updater.py", "../evil.py", ".github/workflows/tests.yml"):
        bad = json.dumps({"summary": "x", "edits": [{"file": path, "find": "CHECK", "replace": "NO"}]})
        reserve.main(["--workdir", str(repo), "--prompt", str(prompt), "--status", str(status)],
                     env={"GROQ_API_KEY": "k", "AUTOFIX_GROQ_MODELS": "g1"}, opener=_opener([bad, bad], []))
        assert json.loads(status.read_text())["result"] == "error", path
    assert (repo / "ike/updater.py").read_text() == "CHECK = True\n"
    assert not (repo.parent / "evil.py").exists()
    # "cannot be fixed in the code" from two models: stop, no third one asked
    seen = []
    no = json.dumps({"summary": "Un server era giù.", "fixable": False, "edits": []})
    reserve.main(["--workdir", str(repo), "--prompt", str(prompt), "--status", str(status)],
                 env={"GROQ_API_KEY": "k", "OPENROUTER_API_KEY": "k2"}, opener=_opener([no, no], seen))
    assert json.loads(status.read_text())["result"] == "none" and len(seen) == 2


def test_the_chatgpt_guard_never_runs_the_pull_request():
    """1.1.16: ChatGPT's fixes (branches chatgpt/*) are checked by the checker of
    main. The workflow runs from main (pull_request_target) so a pull request
    cannot change its own checks; in exchange it must never run anything of the
    pull request, hold no secret and write nothing."""
    text = (WORKFLOWS / "chatgpt-guard.yml").read_text()
    assert "pull_request_target" in text and "startsWith(github.head_ref, 'chatgpt/')" in text
    assert "permissions:\n  contents: read\n" in text and "write" not in text.split("jobs:")[0]
    assert "secrets." not in text and "GITHUB_TOKEN" not in text
    assert "ref: main" in text and "persist-credentials: false" in text
    # the pull request only as a diff; the only program run is main's checker
    assert "git diff --binary" in text and "python3 -I tools/check-autofix-patch.py" in text
    runs = [ln.strip() for ln in text.splitlines() if ln.strip().startswith(("python", "bash", "sh ", "./", "make", "pip"))]
    assert runs == ["python3 -I tools/check-autofix-patch.py --repo \"$RUNNER_TEMP/pr-base\" --patch \"$RUNNER_TEMP/pr.patch\" \\"], runs
    assert 'git worktree add -q --detach "$RUNNER_TEMP/pr-base" "$base"' in text
    assert "git checkout" not in text and "refs/remotes/pr/head" in text


def test_the_reserves_defaults_and_budgets():
    """1.1.16: today's free models; Groq (about 8,000 tokens a minute) gets a
    short message, OpenRouter the whole files too."""
    reserve = load("autofix-reserve")
    plan = reserve.chain({"GROQ_API_KEY": "k", "OPENROUTER_API_KEY": "k2"})
    assert [(p[0], p[3]) for p in plan] == [
        ("Groq", "qwen/qwen3.8-27b"), ("Groq", "openai/gpt-oss-120b"),
        ("OpenRouter", "cohere/north-mini-code:free"), ("OpenRouter", "particle-ai/particle-1:free")]
    groq, router = plan[0][4], plan[2][4]
    shown = {"ike/window.py": "x = 1\n" * 2000}
    small = reserve.message_for("F" * 50000, "C" * 50000, shown, groq, refused="too big")
    big = reserve.message_for("F" * 50000, "C" * 50000, shown, router)
    assert len(small) <= groq + 200 and "too big" in small and "x = 1" not in small
    assert "x = 1" in big
    assert reserve.classify(413) == "toolarge"


def test_a_refused_reserve_fix_goes_to_the_next_model_with_the_reason(repo, tmp_path):
    import json
    reserve = load("autofix-reserve")
    _reserve_repo(repo)
    (repo / ".autofix/related.txt").write_text("ike/window.py\ntests/test_window.py\n")
    prompt = tmp_path / "prompt.md"
    prompt.write_text("RULES")
    status = tmp_path / "status.json"
    checker = str(ROOT / "tools/check-autofix-patch.py")
    args = ["--workdir", str(repo), "--prompt", str(prompt), "--status", str(status),
            "--checker", checker, "--related", str(repo / ".autofix/related.txt")]
    env = {"GROQ_API_KEY": "k", "AUTOFIX_GROQ_MODELS": "g1, g2"}
    # too big for the checks: undone, the next model is told why and fixes it small
    huge = json.dumps({"summary": "x", "edits": [{"file": "ike/window.py", "find": "    return 10\n",
                                                 "replace": "    return 11\n" + "# pad\n" * 200}]})
    good = json.dumps({"summary": "ok", "edits": [{"file": "ike/window.py", "find": "    return 10\n",
                                                  "replace": "    return 11\n"}]})
    seen, asked = [], []
    opener = _opener([huge, good], seen)

    def spy(req, timeout=0):
        asked.append(json.loads(req.data)["messages"][1]["content"])
        return opener(req, timeout)
    reserve.main(args, env=env, opener=spy)
    assert json.loads(status.read_text())["result"] == "ok"
    assert "too many changed lines" in asked[1] and "too many changed lines" not in asked[0]
    assert (repo / "ike/window.py").read_text() == "def width():\n    return 11\n"
    git(repo, "checkout", "-q", "--", ".")
    # a weakened test is a safety refusal: undone, and no other model is asked
    skip = json.dumps({"summary": "x", "edits": [{"file": "tests/test_window.py", "find": "def test_width():\n",
                                                 "replace": "@pytest.mark.skip\ndef test_width():\n"}]})
    seen = []
    reserve.main(args, env=env, opener=_opener([skip, good], seen))
    out = json.loads(status.read_text())
    assert out["result"] == "refused" and len(seen) == 1, out
    assert "skip" not in (repo / "tests/test_window.py").read_text()


@pytest.mark.parametrize("rel", ["ike-adblock/Cargo.toml", "ike-adblock/Cargo.lock",
                                 "ike/resources/darkreader.js", "ike/resources/ubo-scriptlets.json",
                                 "ike/resources/icons/sets/x.svg", "docs/THIRD-PARTY.md"])
def test_files_of_others_and_generated_ones_are_never_changed(repo, tmp_path, rel):
    """1.1.16: what comes from others or is generated has its own update tool;
    not even an engine update lets an automatic fix touch it."""
    patch = make_patch(repo, edit(rel, "changed\n"))
    for extra in ((), ("--allow-adblock",)):
        code, report = run_guard(repo, patch, tmp_path, *extra)
        assert code == 3 and "third-party or generated" in report, (rel, extra)


def test_only_the_wrappers_of_the_ad_blocker_with_an_engine_update(repo, tmp_path):
    for rel in ("ike-adblock/src/lib.rs", "vendor/adblock/__init__.py"):
        patch = make_patch(repo, edit(rel, "# fixed\n", "a"))
        assert run_guard(repo, patch, tmp_path)[0] == 3
        assert run_guard(repo, patch, tmp_path, "--allow-adblock", "--check-only")[0] == 0
    patch = make_patch(repo, edit("ike-adblock/build.rs", "fn main() {}\n"))
    code, report = run_guard(repo, patch, tmp_path, "--allow-adblock")
    assert code == 3 and "only I.K.E.'s wrapper" in report


def test_check_only_applies_nothing_and_size_is_not_a_safety_matter(repo, tmp_path):
    patch = make_patch(repo, edit("ike/window.py", "def width():\n    return 11\n"))
    assert run_guard(repo, patch, tmp_path, "--check-only")[0] == 0
    assert git(repo, "status", "--porcelain") == ""
    big = make_patch(repo, edit("ike/big.py", "x = 1\n" * (guard.MAX_LINES + 1)))
    assert run_guard(repo, big, tmp_path)[0] == 1          # a better fix may pass: the next assistant tries


def test_check_only_verifies_that_the_patch_applies(repo, tmp_path):
    """1.1.18: --check-only accepted a patch that did not apply to the tree."""
    patch = make_patch(repo, edit("ike/window.py", "def width():\n    return 11\n"))
    assert run_guard(repo, patch, tmp_path, "--check-only")[0] == 0          # applies
    (repo / "ike/window.py").write_text("def width():\n    return 11\n")
    assert run_guard(repo, patch, tmp_path, "--check-only")[0] == 0          # already in the tree
    (repo / "ike/window.py").write_text("def height():\n    return 99\n")
    code, report = run_guard(repo, patch, tmp_path, "--check-only")         # neither
    assert code == 1 and "does not apply" in report


def test_tests_are_not_weakened_in_other_ways(repo, tmp_path):
    """1.1.18: only removed assert lines were counted."""
    base = "def test_width():\n    assert 1\n    assert 2\n"
    weakened = {
        "test removed or renamed": "def test_breadth():\n    assert 1\n    assert 2\n",
        "assertion that cannot fail": base + "    assert True\n",
        "early return at the top of a test": "def test_width():\n    return\n    assert 1\n    assert 2\n",
        "skip or xfail": "import unittest\n\n\n@unittest.skip('x')\n" + base,
    }
    for why, text in weakened.items():
        patch = make_patch(repo, edit("tests/test_window.py", text))
        code, report = run_guard(repo, patch, tmp_path)
        assert code == 3 and why in report, (why, report)
    # after a docstring, and a test removed while another is added
    doc = 'def test_width():\n    """Width."""\n    return None\n    assert 1\n    assert 2\n'
    code, report = run_guard(repo, make_patch(repo, edit("tests/test_window.py", doc)), tmp_path)
    assert code == 3 and "early return" in report
    gone = make_patch(repo, edit("tests/test_window.py", "def test_other():\n    assert 1\n    assert 2\n"))
    assert "test_width" in run_guard(repo, gone, tmp_path)[1]
    # an honest correction still passes: a new parameter, a fixed assertion, a return in a helper
    for text in ("def test_width(tmp_path):\n    assert 1\n    assert len(\"ab\") == 2\n",
                 base + "\n\ndef helper():\n    return 1\n",
                 "def test_width():\n    x = 2\n    if x:\n        return\n    assert 1\n    assert 2\n"):
        patch = make_patch(repo, edit("tests/test_window.py", text))
        code, report = run_guard(repo, patch, tmp_path, "--check-only")
        assert code == 0, (text, report)


@pytest.mark.parametrize("rel", ["tests/data/page.html", "tests/settings-keys.json",
                                 "ike/resources/videoads.js", "ike/resources/videorelay.js",
                                 "ike/resources/mediahook.js", "tools/test-requirements.txt",
                                 "tools/automation-health.py", "tools/build-darkreader.py",
                                 "tools/build-ubo-scriptlets.mjs", "tools/third-party.py",
                                 ".github/autofix/prompt.md"])
def test_more_files_are_never_changed_by_a_fix(repo, tmp_path, rel):
    """1.1.18: YouTube's ad blocking (the owner's rule), the tests' reference
    data, the test packages, the builders of what comes from others, the health
    check and the workflows."""
    patch = make_patch(repo, edit(rel, "// changed\n", "a"))
    code, report = run_guard(repo, patch, tmp_path)
    assert code == 3 and "protected file" in report, report
    assert guard.allowed_path("ike/shields.py", False) == ""        # ordinary code stays fixable
    assert guard.allowed_path("tools/check-components.py", False) == ""


@pytest.mark.parametrize("key", ["gsk_" + "A1b2C3d4" * 6, "sk-or-v1-" + "0a1b2c3d" * 8, "sk-proj-" + "Zz09" * 10])
def test_keys_of_the_reserves_are_refused_too(repo, tmp_path, key):
    patch = make_patch(repo, edit("ike/window.py", "KEY = '%s'\n" % key, "a"))
    code, report = run_guard(repo, patch, tmp_path)
    assert code == 3 and "key or token" in report


def test_a_repository_inside_the_tree_is_refused(repo, tmp_path):
    """A nested repository (a gitlink, mode 160000) would make git look into
    a configuration the agent wrote."""
    patch = ("diff --git a/ike/sub b/ike/sub\nnew file mode 160000\nindex 0000000..1234567\n"
             "--- /dev/null\n+++ b/ike/sub\n@@ -0,0 +1 @@\n+Subproject commit " + "1" * 40 + "\n")
    code, report = run_guard(repo, patch, tmp_path)
    assert code == 3 and "link or file mode" in report


def test_the_checker_ignores_what_the_agent_could_configure(repo, tmp_path, monkeypatch):
    """1.1.18: the checker runs git on the agent's tree: no global or system
    configuration, no hooks, no fsmonitor, no attributes file."""
    for flag in ("core.hooksPath=/dev/null", "core.fsmonitor=false", "core.attributesFile=/dev/null"):
        assert flag in guard.SAFE_GIT, flag
    patch = make_patch(repo, edit("ike/window.py", "def width():\n    return 11\n"))
    hit = tmp_path / "ran"
    evil = tmp_path / "gitconfig"
    evil.write_text("[core]\n    fsmonitor = touch %s\n    hooksPath = /tmp\n" % hit)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(evil))
    monkeypatch.setenv("GIT_DIR", str(tmp_path / "nowhere"))
    env = guard.safe_git_env()
    assert env["GIT_CONFIG_GLOBAL"] == "/dev/null" and env["GIT_CONFIG_NOSYSTEM"] == "1" and "GIT_DIR" not in env
    assert run_guard(repo, patch, tmp_path)[0] == 0 and not hit.exists()


NOTE = 'import pytest\n_NOTE = """\n++ notes\n"""\n'      # its diff line reads "+++ notes"
WIDTH = "def test_width():\n    assert 1\n    assert 2\n"


@pytest.mark.parametrize("text, why", [
    (NOTE + "pytestmark = pytest.mark.skip\n" + WIDTH, "skip or xfail"),
    (NOTE + "def test_width():\n    return\n    assert 1\n    assert 2\n", "early return"),
    (NOTE + WIDTH + "\n\ndef test_more():\n    assert True\n", "cannot fail"),
    (NOTE + "KEY = '%s'\n" % ("AIza" + "Q" * 35) + WIDTH, "key or token"),
    (NOTE + WIDTH + "\n\ndel test_width\n", "by code"),
])
def test_a_line_that_looks_like_a_header_does_not_blind_the_checks(repo, tmp_path, text, why):
    """1.1.18 (review, verified exploit): an added line "++ x" shows in the diff
    as "+++ x", which was taken for the next file's header: every check of the
    rest of the file was blind. Hunks are now read by their line counts."""
    patch = make_patch(repo, edit("tests/test_window.py", text))
    assert "\n+++ notes\n" in patch
    code, report = run_guard(repo, patch, tmp_path)
    assert code == 3 and why in report, report
    assert [p for p, s, t in guard.patch_lines(patch) if s == "+"] == ["tests/test_window.py"] * \
        len([t for p, s, t in guard.patch_lines(patch) if s == "+"])


@pytest.mark.parametrize("change, why", [
    (edit("tests/test_window.py", WIDTH + "\n\ndel test_width\n"), "by code"),
    (edit("tests/test_window.py", WIDTH + "\n\ndef test_x():\n    getattr(pytest, 'sk' + 'ip')('x')\n"),
     "by code"),
    (edit("tests/test_window.py", WIDTH + "\n\ndef test_x():\n    x = 3\n    assert x == x\n"), "cannot fail"),
    (edit("tests/test_window.py", WIDTH + "\n\ndef test_x():\n    import os\n    os._exit(0)\n"), "by code"),
    (edit("tests/test_window.py", WIDTH + "\nglobals().pop('test_width')\n"), "by code"),
    (edit("tests/zz/conftest.py", "def pytest_collection_modifyitems(items):\n    items.clear()\n"),
     "protected file"),
    (edit("tests/helpers.py", "X = 1\n"), "not a test module"),
    (edit("tests/__init__.py", ""), "protected file"),
    (edit("ike/sub/pytest.ini", "[pytest]\naddopts = -k nothing\n"), "protected file"),
    (edit("tools/setup.cfg", "[tool:pytest]\n"), "protected file"),
    (edit("docs/ruff.toml", "line-length = 999\n"), "protected file"),
])
def test_tests_cannot_be_dropped_by_other_means(repo, tmp_path, change, why):
    """1.1.18 (review): `del test_x`, a conftest.py dropping items, skip reached
    through getattr, `assert x == x`, a configuration that decides what runs."""
    code, report = run_guard(repo, make_patch(repo, change), tmp_path)
    assert code == 3 and why in report, report


BYPASSES = {
    # second review of 1.1.18: each of these passed the checker
    "runtest": "import _pytest.python\n_pytest.python.Function.runtest = lambda self: None\n",
    "execv": "import os\nos.execv('/bin/true', ['true'])\n",
    "_exit import": "from os import _exit\n_exit(0)\n",
    "name to None": WIDTH + "\n\ntest_width = None\n",
    "name to lambda": WIDTH + "\n\ntest_width = lambda *a, **k: None\n",
    "del after ;": WIDTH + "\n\n_ = 0; del test_width\n",
    "# in a string": WIDTH + "\n\n_ = '#'; globals().pop('test_width')\n",
    "Skipped": WIDTH + "\n\ndef test_x():\n    from _pytest.outcomes import Skipped\n    raise Skipped()\n",
    "empty params": WIDTH + "import pytest\nREAL = [1, 2]\n\n\n@pytest.mark.parametrize('n', REAL[:0])\ndef test_n(n):\n"
                    "    assert n > 0\n",
    "getattr pieces": WIDTH + "import pytest\n_m = pytest.mark\n\n\n@getattr(_m, 'sk' 'ip')\ndef test_y():\n"
                      "    assert len('a') == 1\n",
    "or True": WIDTH + "\n\ndef test_z():\n    assert len('a') == 5 or True\n",
    "assert 2": WIDTH + "\n\ndef test_z():\n    assert 2\n",
    "tuple": WIDTH + "\n\ndef test_z():\n    assert (len('a') == 5, 'msg')\n",
    "string": WIDTH + "\n\ndef test_z():\n    assert 'always'\n",
    "if False": WIDTH + "\n\ndef test_z():\n    if False:\n        assert len('a') == 5\n",
    "if return": WIDTH + "\n\ndef test_z():\n    host = 1\n    if host: return\n    assert len('a') == 5\n",
}


@pytest.mark.parametrize("name", sorted(BYPASSES))
def test_the_second_review_bypasses_are_refused(repo, tmp_path, name):
    rel = "tests/test_window.py" if name not in ("runtest", "execv", "_exit import") else "tests/test_more.py"
    code, report = run_guard(repo, make_patch(repo, edit(rel, BYPASSES[name])), tmp_path)
    assert code == 3, (name, report)


def test_carriage_returns_cannot_hide_a_line(repo, tmp_path):
    """"# note\\rdel test_x": one line for git and the checks, two for Python."""
    (repo / "tests/test_window.py").write_bytes((WIDTH + "\n# note\rdel test_width\n").encode())
    git(repo, "add", "-A")
    patch = subprocess.run(["git", "-C", str(repo), "diff", "--cached", "--binary"], capture_output=True,
                           check=True).stdout
    git(repo, "reset", "-q", "--hard")
    assert b"\r" in patch
    pf, report = tmp_path / "cr.patch", tmp_path / "cr.md"
    pf.write_bytes(patch)
    code = guard.main(["--repo", str(repo), "--patch", str(pf), "--report", str(report)])
    assert code == 3 and "carriage return" in report.read_text(), report.read_text()


def test_monkeypatch_delattr_and_the_word_skip_are_fine(repo, tmp_path):
    """The two false positives the second review asked to keep away."""
    text = (WIDTH + "\n\ndef test_m(monkeypatch):\n    # skip the slow path: the cache is warm\n"
            "    monkeypatch.delattr('os.sep', raising=False)\n    assert len('ab') == 2\n")
    code, report = run_guard(repo, make_patch(repo, edit("tests/test_window.py", text)), tmp_path, "--check-only")
    assert code == 0, report


def test_ordinary_test_code_is_still_accepted(repo, tmp_path):
    text = (WIDTH + "\n\ndef test_list(tmp_path):\n    opened = [1]\n    del opened[:]\n    assert opened == []\n"
            "    assert len(opened) == 0, 'empty'\n")
    code, report = run_guard(repo, make_patch(repo, edit("tests/test_window.py", text)), tmp_path, "--check-only")
    assert code == 0, report
    code, report = run_guard(repo, make_patch(repo, edit("tests/test_new_part.py", "def test_a():\n    assert len(\"ab\") == 2\n")),
                             tmp_path, "--check-only")
    assert code == 0, report


def test_the_checker_prints_no_workflow_commands(repo, tmp_path, capsys):
    patch = make_patch(repo, edit("tests/test_window.py", "    pytest.skip('::error::x')\n", "a"))
    run_guard(repo, patch, tmp_path)
    printed = capsys.readouterr().out
    assert "skip or xfail" in printed and "::error::" not in printed


def test_the_failure_is_the_failed_step_without_noise():
    log = "\n".join([
        "2026-11-18T00:40:00.1Z ##[group]Run sudo apt-get install -y x",
        "2026-11-18T00:40:01.1Z Selecting previously unselected package libx.",
        "2026-11-18T00:40:01.2Z Unpacking libx (1.0) ...",
        "2026-11-18T00:43:20.0Z ##[group]Run ruff check .",
        "2026-11-18T00:43:20.1Z shell: /usr/bin/bash -e {0}",
        "2026-11-18T00:43:20.2Z env:",
        "2026-11-18T00:43:20.3Z   pythonLocation: /opt/x",
        "2026-11-18T00:43:20.4Z ##[endgroup]",
        "2026-11-18T00:43:21.0Z F401 [*] `shutil` imported but unused",
        "2026-11-18T00:43:21.1Z   --> ike/weather.py:17:8",
        "2026-11-18T00:43:21.2Z ##[error]Process completed with exit code 1.",
        "2026-11-18T00:43:22.0Z Post job cleanup.",
        "2026-11-18T00:43:22.1Z [command]/usr/bin/git version",
    ])
    out = plan_tool.clean_log(log)
    assert out.splitlines() == ["$ ruff check .", "F401 [*] `shutil` imported but unused",
                                "  --> ike/weather.py:17:8", "##[error]Process completed with exit code 1."], out
    assert plan_tool.clean_log("only\nlines") == "only\nlines"      # no error marker: the end, as before


def test_the_agent_still_working_at_its_time_limit_is_not_retried():
    agent = load("autofix-agent")
    err = ('[agy] print timeout after 58s with turn in progress\nAGY_ERROR: {"status":"DEADLINE_EXCEEDED",'
           '"retryable":false,"reason":"print_timeout"}')
    assert agent.classify(1, err) == ("timeout", 0)
    assert agent.classify(1, 'AGY_ERROR: {"status":"UNAVAILABLE"}')[0] == "temporary"


def test_cargo_errors_point_at_the_wrapper_never_at_the_engine(repo):
    ctx = load("autofix-context")
    (repo / "vendor/adblock").mkdir(parents=True)
    (repo / "vendor/adblock/__init__.py").write_text("x = 1\n")
    failure = ("error[E0425]: cannot find value\n  --> src/lib.rs:1:5\n"
               "warning: --> /home/runner/.cargo/registry/src/x/adblock-0.13.6/src/engine.rs:40:1\n"
               '  File "/usr/lib/ike-browser/vendor/adblock/__init__.py", line 1, in <module>\n')
    text, related = ctx.build(repo, failure)
    assert related == ["ike-adblock/src/lib.rs", "vendor/adblock/__init__.py"]
    assert "engine.rs" not in text


def test_job_logs_are_read_with_their_colour_codes(monkeypatch):
    """2026-11-19: newer gh refuses to print a job log with escape sequences
    unless asked, and no assistant got the error. Older gh lacks the flag."""
    import types
    calls = []

    def fake(cmd, **kw):
        calls.append(cmd)
        if "--allow-escape-sequences" in cmd and fake.old:
            return types.SimpleNamespace(returncode=1, stdout="", stderr="unknown flag: --allow-escape-sequences")
        return types.SimpleNamespace(returncode=0, stdout="\x1b[31mF401\x1b[0m", stderr="")
    for old in (False, True):
        fake.old = old
        calls.clear()
        monkeypatch.setattr(plan_tool.subprocess, "run", fake)
        assert plan_tool.gh_api("repos/x/actions/jobs/1/logs", raw=True) == "\x1b[31mF401\x1b[0m"
        assert calls[0] == ["gh", "api", "--allow-escape-sequences", "repos/x/actions/jobs/1/logs"]
        assert len(calls) == (2 if old else 1)


# --- 1.1.16: the engine update, one rule for everyone, the chain ----------------

LOCK = '''version = 4

[[package]]
name = "adblock"
version = "%s"
source = "registry+https://github.com/rust-lang/crates.io-index"
'''


@pytest.mark.parametrize("candidate, main, expected", [
    (LOCK % "0.13.7", LOCK % "0.13.6", True),      # a real engine update
    (LOCK % "0.13.6", LOCK % "0.13.6", False),     # Dark Reader, scriptlets, lists: same engine
    ("", LOCK % "0.13.6", False),                  # no lock on the candidate: cannot tell
    (LOCK % "0.13.7", "", False),                  # no lock on main: cannot tell
    ("garbage", LOCK % "0.13.6", False),
    (LOCK.replace('name = "adblock"', 'name = "adblock-extra"') % "9.9.9", LOCK % "0.13.6", False),
])
def test_the_engine_update_is_read_from_the_lock(candidate, main, expected):
    """Until 1.1.16 the candidate had to raise the minimum system; a new engine
    travels in the signed self-update and seldom does. Now: the adblock crate
    of the candidate's Cargo.lock against main's, anything unreadable is no."""
    show = {"origin/automation/daily-maintenance": candidate, "origin/main": main}.get
    assert plan_tool.engine_update("automation/daily-maintenance", show=show) is expected
    assert plan_tool.adblock_version(LOCK % "0.13.6") == "0.13.6"


PYO3 = LOCK % "0.13.6" + '''
[[package]]
name = "pyo3"
version = "%s"
'''


def test_a_new_pyo3_allows_the_wrapper_too():
    """1.1.19: the component check follows pyo3 (the bridge to Python); a new
    one may need the same adaptation of I.K.E.'s wrapper as a new engine."""
    show = {"origin/automation/daily-maintenance": PYO3 % "0.31.0", "origin/main": PYO3 % "0.30.1"}.get
    assert plan_tool.engine_update("automation/daily-maintenance", show=show) is True
    show = {"origin/automation/daily-maintenance": PYO3 % "0.30.1", "origin/main": PYO3 % "0.30.1"}.get
    assert plan_tool.engine_update("automation/daily-maintenance", show=show) is False
    assert plan_tool.pyo3_version((PYO3 % "0.30.1").replace("\n", "\r\n")) == "0.30.1"


def test_only_an_engine_update_allows_the_wrapper():
    base = dict(_tip="t1", _main_tip="m1", _attempts=0)
    for update, allowed in ((True, "true"), (False, "false")):
        plan = plan_tool.decide(failed_run(branch="automation/daily-maintenance", head_sha="t1", **base,
                                           _engine_update=update), [job("tests")], "")
        assert plan["allow_adblock"] == allowed
    plan = plan_tool.decide(failed_run(branch="main", head_sha="m1", **base, _engine_update=True),
                            [job("tests")], "")
    assert plan["allow_adblock"] == "false"           # never for a fix of main


WRAPPER_PATHS = ["ike-adblock/src/lib.rs", "vendor/adblock/__init__.py", "ike/blocker.py", "ike/scriptlets.py"]
NEVER_PATHS = ["ike-adblock/Cargo.toml", "ike-adblock/Cargo.lock", "ike-adblock/build.rs",
               "vendor/adblock/adblock.pyi", "ike/resources/darkreader.js", "ike/resources/ubo-scriptlets.json",
               "ike/resources/icons/sets/a.svg", "docs/THIRD-PARTY.md", ".github/workflows/tests.yml"]


def test_the_reserves_never_promise_what_the_checker_refuses(repo, tmp_path):
    """One rule for Antigravity, the reserves, the checker and ChatGPT: what a
    reserve may edit is always something the checker accepts."""
    reserve = load("autofix-reserve")
    for allow in (False, True):
        for path in WRAPPER_PATHS + NEVER_PATHS + ["ike/window.py", "tests/test_x.py", "tools/x.py", "docs/x.md"]:
            shown = {path: "x\n"}
            (repo / path).parent.mkdir(parents=True, exist_ok=True)
            (repo / path).write_text("x\n")
            try:
                reserve.apply_edits(repo, [{"file": path, "find": "x\n", "replace": "y\n"}], shown, allow)
                applied = True
            except ValueError:
                applied = False
            (repo / path).write_text("x\n")
            checker_ok = guard.allowed_path(path, allow) == ""
            if applied:
                assert checker_ok, (path, allow)          # never more than the checker
            if path in WRAPPER_PATHS:
                assert applied is allow, (path, allow)    # the wrapper: exactly with an engine update
            if path in NEVER_PATHS:
                assert not applied and not checker_ok, (path, allow)
    assert "not the ad blocker" in reserve.instructions(False)
    assert "ike-adblock/src/" in reserve.instructions(True) and "Cargo.lock" in reserve.instructions(True)


def test_antigravity_is_told_the_same():
    agent = load("autofix-agent")
    assert "does not update" in agent.engine_note(False) and "ike/blocker.py" in agent.engine_note(False)
    assert "updates the ad blocker's engine" in agent.engine_note(True) and "Cargo.lock" in agent.engine_note(True)
    text = (ROOT / ".github/autofix/prompt.md").read_text()
    assert 'the section "This run"' in text
    workflow = (WORKFLOWS / "autofix.yml").read_text()
    assert '--out "$out" --status "$out/status.json" $allow' in workflow
    # ChatGPT gets stricter rules than the checker, never wider ones (its guard has no --allow-adblock)
    assert "Never change the ad blocker: ike-adblock/" in workflow
    assert "--allow-adblock" not in (WORKFLOWS / "chatgpt-guard.yml").read_text()


@pytest.mark.parametrize("groq, why", [
    ([429], "quota"),
    ([500, 500], "server errors"),
    (["not json", "still not json"], "no usable answer"),
    ([413], "request too large"),
])
def test_openrouter_is_reached_when_groq_cannot_fix(repo, tmp_path, groq, why):
    import json
    reserve = load("autofix-reserve")
    _reserve_repo(repo)
    prompt = tmp_path / "prompt.md"
    prompt.write_text("RULES")
    status = tmp_path / "status.json"
    good = json.dumps({"summary": "ok", "edits": [{"file": "ike/window.py", "find": "    return 10\n",
                                                  "replace": "    return 11\n"}]})
    seen = []
    env = {"GROQ_API_KEY": "k", "OPENROUTER_API_KEY": "k2", "AUTOFIX_GROQ_MODELS": "g1",
           "AUTOFIX_OPENROUTER_MODELS": "o1"}
    orig_sleep = reserve.time.sleep
    reserve.time.sleep = lambda s: None
    try:
        reserve.main(["--workdir", str(repo), "--prompt", str(prompt), "--status", str(status)],
                     env=env, opener=_opener(list(groq) + [good], seen))
    finally:
        reserve.time.sleep = orig_sleep
    out = json.loads(status.read_text())
    assert out["result"] == "ok" and out["model"] == "OpenRouter / o1", (why, out)
    assert seen[-1][0].startswith("https://openrouter.ai/"), why


def step_script(name, workflow="autofix.yml"):
    """The shell of one step of a workflow (its "run: |" block), without a YAML
    library. A step may carry an anchor on the line before its name
    ("- &closed-room" then "name: ...")."""
    import textwrap
    lines = (WORKFLOWS / workflow).read_text().splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.strip() == "- name: %s" % name or (
        ln.strip() == "name: %s" % name and lines[i - 1].strip().startswith("- &")))
    run = next(i for i in range(start, len(lines)) if lines[i].strip() == "run: |")
    indent = len(lines[run]) - len(lines[run].lstrip())
    body = []
    for ln in lines[run + 1:]:
        if ln.strip() and len(ln) - len(ln.lstrip()) <= indent:
            break
        body.append(ln)
    return textwrap.dedent("\n".join(body)) + "\n"


AGENT_STUB = r'''
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
workdir = Path(args[args.index("--workdir") + 1])
status = Path(args[args.index("--status") + 1])
what = os.environ["SCENARIO"]
if what == "big":
    (workdir / "ike/other.py").write_text("x = 1\n")          # misses the file of the failure
elif what == "unsafe":
    (workdir / "ike/updater.py").write_text("CHECK = False\n")  # a protected file
elif what == "good":
    (workdir / "ike/window.py").write_text("def width():\n    return 11\n")
elif what == "partial":                                        # its time limit, half done
    (workdir / "ike/window.py").write_text("def width():\n    return 1")
    (workdir / "ike/half.py").write_text("x = (\n")
    status.write_text(json.dumps({"result": "timeout", "model": "stub", "message": "m", "detail": ""}))
    sys.exit(0)
elif what == "crash":                                          # the step itself stops, no status
    (workdir / "ike/window.py").write_text("half")
    (workdir / ".autofix/summary.md").write_text("K %s\n" % os.environ["GEMINI_API_KEY"])   # never checked
    sys.exit(3)
elif what == "leak":
    (workdir / "ike/window.py").write_text("K = '%s'\n" % os.environ["GEMINI_API_KEY"])
elif what == "abort":                    # its status is written, then the step stops before the key check
    (workdir / ".autofix/summary.md").write_text("K %s\n" % os.environ["GEMINI_API_KEY"])
    (Path(os.environ["RUNNER_TEMP"]) / "autofix" / "agent.diff").mkdir()
elif what == "link":                                           # the runner would read what it points at
    secret = workdir.parent / "secret"
    (workdir / ".autofix/summary.md").symlink_to(secret)
    (workdir / ".autofix/failure.md").unlink(missing_ok=True)
    (workdir / ".autofix/failure.md").symlink_to(secret)
    (workdir / ".autofix/extra").mkdir()
status.write_text(json.dumps({"result": "ok", "model": "stub", "message": "m", "detail": ""}))
'''

RESERVE_STUB = r'''
import json, sys
from pathlib import Path
args = sys.argv[1:]
with open(Path(args[args.index("--status") + 1]).parent / "reserve-calls.txt", "a") as f:
    f.write(" ".join(args) + "\n")
Path(args[args.index("--status") + 1]).write_text(json.dumps({"result": "error", "model": "", "message": "nessuna"}))
'''


FIX_STEPS = ("How the agent is stopped", "Git for the runner on the agent's tree", "Antigravity",
             "Reserves, then the patch")


def run_fix_steps(repo, tmp_path, scenario, reserve_key="gsk_TESTONLY"):
    """The real shell of the fix job's steps (1.1.18: Antigravity with the
    Gemini key only, then the reserves and the patch), with a stub agent and a
    stub reserve. Returns ({step: completed process}, outputs, reserve calls, temp)."""
    import os
    import subprocess

    temp = tmp_path / "runner"
    (temp / "autofix").mkdir(parents=True)
    (temp / "prompt.md").write_text("RULES")
    (temp / "autofix-agent.py").write_text(AGENT_STUB)
    (temp / "autofix-reserve.py").write_text(RESERVE_STUB)
    (temp / "check-autofix-patch.py").write_text((ROOT / "tools/check-autofix-patch.py").read_text())
    (temp / "autofix" / "related.txt").write_text("ike/window.py\n")
    (temp / "autofix-inputs").mkdir()
    for name, text in (("failure.md", FAILURE), ("context.md", "# Code\n"), ("related.txt", "ike/window.py\n")):
        (temp / "autofix-inputs" / name).write_text(text)
    (repo / ".autofix").mkdir(exist_ok=True)
    with open(repo / ".git" / "info" / "exclude", "a") as f:
        f.write(".autofix/\n")                                  # as the real .gitignore
    (tmp_path / "secret").write_text("RUNNER-ONLY-SECRET\n")
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    (bin_ / "sudo").write_text("#!/bin/sh\nexit 0\n")
    (bin_ / "sudo").chmod(0o755)
    out_file = tmp_path / "github_output"
    base = dict(os.environ, RUNNER_TEMP=str(temp), GITHUB_OUTPUT=str(out_file), SCENARIO=scenario,
                ALLOW_ADBLOCK="false", PATH="%s:%s" % (bin_, os.environ["PATH"]))
    envs = {FIX_STEPS[0]: base, FIX_STEPS[1]: base,
            FIX_STEPS[2]: dict(base, GEMINI_API_KEY="AIzaTESTONLY"),
            FIX_STEPS[3]: dict(base, GROQ_API_KEY=reserve_key, OPENROUTER_API_KEY="")}
    runs = {}
    for name in FIX_STEPS:
        script = step_script(name).replace("/srv/autofix/repo", str(repo))
        runs[name] = subprocess.run(["bash", "-e", "-c", script], env=envs[name], capture_output=True,
                                    text=True, timeout=120)
    outputs = dict(line.split("=", 1) for line in out_file.read_text().splitlines() if "=" in line) \
        if out_file.exists() else {}
    calls = temp / "autofix" / "reserve-calls.txt"
    return runs, outputs, calls.read_text() if calls.exists() else "", temp


@pytest.mark.parametrize("scenario, reserve_asked, refused_given, result, patch", [
    ("nothing", True, False, "ok", "false"),       # no fix: the first reserve
    ("big", True, True, "rejected", "false"),      # off target: undone, the reserves get the reason
    ("unsafe", False, False, "refused", "false"),  # a protected file: undone, nobody else asked
    ("good", False, False, "ok", "true"),          # accepted at once: the reserves stay quiet
    ("partial", True, False, "timeout", "false"),  # half done at its time limit: thrown away
    ("crash", True, False, "timeout", "false"),    # its step stopped: thrown away
    ("abort", True, False, "timeout", "false"),    # stopped after its status, before its key check
])
def test_the_fix_step_of_the_workflow(repo, tmp_path, scenario, reserve_asked, refused_given, result, patch):
    """What reaches the reserves, and what is kept."""
    runs, outputs, asked, temp = run_fix_steps(repo, tmp_path, scenario)
    for name, run in runs.items():
        expected = {("crash", "Antigravity"): 3, ("abort", "Antigravity"): 1}.get((scenario, name), 0)
        assert run.returncode == expected, (name, run.stdout + run.stderr)
    assert bool(asked) is reserve_asked, (scenario, asked)
    assert ("--refused" in asked) is refused_given, (scenario, asked)
    if reserve_asked:
        assert "--checker" in asked and "--related" in asked and "--allow-adblock" not in asked
    assert outputs["result"] == result, (scenario, outputs, runs[FIX_STEPS[3]].stdout)
    assert outputs["patch"] == patch, (scenario, outputs)
    if scenario in ("big", "unsafe", "partial", "crash", "abort"):   # nothing refused or unfinished is kept
        assert git(repo, "status", "--porcelain") == "", scenario
    summary = (temp / "autofix" / "summary.md").read_text()
    assert "AIzaTESTONLY" not in summary
    if scenario in ("big", "unsafe"):
        assert "respinta dai controlli" in summary, summary


@pytest.mark.parametrize("scenario", ["partial", "crash", "big"])
def test_unfinished_work_is_thrown_away_without_reserves_too(repo, tmp_path, scenario):
    """1.1.18: without a reserve key, what Antigravity left after its time limit
    or an error was published as the fix."""
    runs, outputs, asked, temp = run_fix_steps(repo, tmp_path, scenario, reserve_key="")
    assert runs[FIX_STEPS[3]].returncode == 0, runs[FIX_STEPS[3]].stdout + runs[FIX_STEPS[3]].stderr
    assert not asked and outputs["patch"] == "false", outputs
    assert (temp / "autofix" / "autofix.patch").read_text() == ""
    assert git(repo, "status", "--porcelain") == ""


def test_links_the_agent_leaves_in_autofix_are_never_followed(repo, tmp_path):
    """1.1.18: .autofix/ is writable by the agent; a link there (its summary,
    the failure the reserves read) would make the runner read any file it can
    and put it in a public pull request or send it to a reserve."""
    import urllib.error
    runs, outputs, asked, temp = run_fix_steps(repo, tmp_path, "link")
    assert runs[FIX_STEPS[3]].returncode == 0, runs[FIX_STEPS[3]].stdout + runs[FIX_STEPS[3]].stderr
    summary = (temp / "autofix" / "summary.md").read_text()
    assert "RUNNER-ONLY-SECRET" not in summary
    assert not (repo / ".autofix/summary.md").exists() and not (repo / ".autofix/extra").exists()
    assert (repo / ".autofix/failure.md").read_text() == FAILURE           # the runner's copy
    # the reserves read the runner's copy, and never a link
    reserve = load("autofix-reserve")
    (repo / ".autofix/context.md").unlink()
    (repo / ".autofix/context.md").symlink_to(tmp_path / "secret")
    seen = []

    def opener(req, timeout=0):
        seen.append(req.data)
        raise urllib.error.HTTPError(req.full_url, 400, "unknown model", {}, None)
    (tmp_path / "prompt.md").write_text("RULES")
    reserve.main(["--workdir", str(repo), "--prompt", str(tmp_path / "prompt.md"),
                  "--status", str(tmp_path / "status.json")],
                 env={"GROQ_API_KEY": "k", "AUTOFIX_GROQ_MODELS": "g1"}, opener=opener)
    assert seen and all(b"RUNNER-ONLY-SECRET" not in s for s in seen)
    assert b"F401" in seen[0]                                               # the real failure went


def test_a_key_in_the_agents_work_throws_everything_away(repo, tmp_path):
    runs, outputs, asked, temp = run_fix_steps(repo, tmp_path, "leak")
    assert runs["Antigravity"].returncode == 1 and runs[FIX_STEPS[3]].returncode == 1
    assert "AIzaTESTONLY" not in "".join(r.stdout + r.stderr for r in runs.values())
    assert "Risultato scartato" in (temp / "autofix" / "summary.md").read_text()
    assert not asked and "patch" not in outputs


def test_the_runner_never_uses_a_git_configuration_the_agent_wrote(repo, tmp_path):
    """1.1.18: the agent could write .git/config, and the runner then ran git
    there: a diff.external or a filter would have run as the runner (sudo, keys)."""
    import os
    import subprocess
    hit = tmp_path / "ran"
    runs, outputs, asked, temp = run_fix_steps(repo, tmp_path, "nothing")
    # the agent's configuration, a nested repository and attributes asking for it
    with open(repo / ".git" / "config", "a") as f:
        f.write('[diff]\n    external = "touch %s"\n[filter "x"]\n    clean = "touch %s"\n'
                '[core]\n    fsmonitor = "touch %s"\n' % (hit, hit, hit))
    (repo / ".gitattributes").write_text("* filter=x diff=x\n")
    (repo / "ike" / "nested").mkdir()
    subprocess.run(["git", "init", "-q", str(repo / "ike" / "nested")], check=True)
    (repo / "ike/window.py").write_text("def width():\n    return 12\n")
    env = dict(os.environ, RUNNER_TEMP=str(temp))
    for args in (["add", "-A"], ["diff", "--cached", "--no-ext-diff", "--no-textconv"], ["status", "--porcelain"]):
        run = subprocess.run([str(temp / "rgit"), *args], env=env, capture_output=True, text=True)
        assert run.returncode == 0, run.stderr
    assert not hit.exists()
    assert "external" not in (repo / ".git" / "config").read_text()           # the runner's own, restored
    assert not (repo / "ike" / "nested" / ".git").exists()
    # .git that is not the runner's own: nothing runs
    (repo / ".git").rename(repo / ".git-real")
    (repo / ".git").symlink_to(repo / ".git-real")
    run = subprocess.run([str(temp / "rgit"), "status"], env=env, capture_output=True, text=True)
    assert run.returncode == 1 and "not the runner's own" in run.stderr


def test_the_tools_run_git_without_the_agents_settings(repo, tmp_path):
    """1.1.18: autofix-agent.py (between models) and autofix-reserve.py run git
    on the agent's tree as the checker does: no external diff, text conversion,
    fsmonitor or global configuration."""
    agent, reserve = load("autofix-agent"), load("autofix-reserve")
    hit = tmp_path / "ran"
    with open(repo / ".git" / "config", "a") as f:
        f.write('[diff "x"]\n    textconv = "sh -c \'touch %s; cat\' --"\n'
                '[core]\n    fsmonitor = "touch %s"\n' % (hit, hit))
    (repo / ".gitattributes").write_text("*.py diff=x\n")
    (repo / "ike/window.py").write_text("def width():\n    return 13\n")
    assert "return 13" in agent.changes(repo) and "return 13" in reserve.diff_of(repo)
    # a new file shows too, with .autofix/ ignored as in the real repository
    (repo / ".gitignore").write_text(".autofix/\n")
    (repo / ".autofix").mkdir(exist_ok=True)
    (repo / ".autofix/summary.md").write_text("riassunto\n")
    (repo / "ike/new.py").write_text("NEW = 1\n")
    done = agent.changes(repo)
    assert "NEW = 1" in done and "riassunto" not in done
    reserve._git(repo, "reset", "-q")
    (repo / "ike/new.py").unlink()
    reserve.undo(repo, ["ike/window.py"])
    assert "return 10" in (repo / "ike/window.py").read_text()
    assert not hit.exists()


def test_the_closed_room_is_closed_for_git_and_names():
    """1.1.18: the agent has its own group, cannot write .git, cannot look up
    names (DNS) and runs without the reserves' keys; every git command of the
    runner on its tree goes through rgit."""
    fix_text = jobs_of((WORKFLOWS / "autofix.yml").read_text())["fix"]
    blocks = re.split(r"^      - (?=name: |uses: |&[\w-]+\n)", fix_text, flags=re.M)[1:]

    def env_of(block):
        m = re.search(r"^        env:\n((?:          .*\n|\s*#.*\n)+)", block, re.M)
        return set(re.findall(r"^          ([A-Z0-9_]+):", m.group(1), re.M)) if m else set()
    steps = {}
    for block in blocks:
        name = re.match(r"(?:&[\w-]+\n\s+)?name: (.*)", block)
        if name:
            steps[name.group(1)] = {"env": env_of(block), "run": block,
                                    "timeout": int((re.search(r"timeout-minutes: (\d+)", block) or [0, 0])[1])}
    fix = {"timeout-minutes": int(re.search(r"^    timeout-minutes: (\d+)", fix_text, re.M).group(1)),
           "steps": [{"timeout-minutes": s["timeout"]} for s in steps.values()]}
    room = steps["A closed room for the agent"]["run"]
    assert "--user-group" in room and '--gid "$group"' not in room
    assert 'sudo chown -R "$me:$(id -gn)" "$repo/.git"' in room and 'chmod -R go-w "$repo/.git"' in room
    assert 'chmod 1775 "$repo"' in room and "the agent can change .git" in room
    for rule in ("-o lo -p udp --dport 53 -j REJECT", "-o lo -p tcp --dport 53 -j REJECT"):
        assert room.count(rule) == 2, rule                        # IPv4 and IPv6
        assert room.index(rule) < room.index("-o lo -j ACCEPT")
    assert "the agent does not find the Gemini API at its pinned address" in room
    # the installer: checked against its recorded sha256 when one is set
    assert "AGY_INSTALLER_SHA256" in steps["A closed room for the agent"]["env"]
    assert 'sha256sum /srv/autofix/agy-install.sh' in room and '"$got" != "$AGY_INSTALLER_SHA256"' in room
    # Antigravity's step has the Gemini key only; the reserves' step has none of it
    agy, reserves = steps["Antigravity"], steps["Reserves, then the patch"]
    assert set(agy["env"]) == {"GEMINI_API_KEY", "AUTOFIX_MODEL", "ALLOW_ADBLOCK"}
    assert "GEMINI_API_KEY" not in reserves["env"]
    assert "GROQ" not in agy["run"] and "OPENROUTER" not in agy["run"]
    # every git command on the agent's tree goes through rgit
    for name in ("Antigravity", "Reserves, then the patch"):
        lines = [ln.strip() for ln in steps[name]["run"].splitlines()]
        assert not [ln for ln in lines if re.match(r"(git|.*\| *git|.*\$\(git) ", ln)], name
        for ln in lines:
            if re.search(r"\b(rgit|gitr) diff\b", ln) and "--name-only" not in ln:
                assert "--no-ext-diff --no-textconv" in ln, ln
    # 1.1.18 (review): the installer never sees the repository, and nothing of
    # the agent runs while the runner touches its tree
    assert room.index('sudo -u agent -H bash /srv/autofix/agy-install.sh') \
        < room.index('"$RUNNER_TEMP/stop-agent"') < room.index('cp -a "$GITHUB_WORKSPACE" "$repo"')
    assert step_script("A closed room for the agent").rstrip().endswith('"$RUNNER_TEMP/stop-agent"')
    assert "sudo setfacl -m u:agent:--- \"$s\"" in room and "io.systemd.Resolve" in room
    # second review: root never writes in the agent's home after the installer ran there
    assert not re.search(r"sudo (tee|chmod|cp|install)[^\n]*/home/agent", room)
    assert 'sudo install -o root -g root -m 755 "$RUNNER_TEMP/run-agent.sh" /opt/autofix/run-agent.sh' in room
    assert "/opt/autofix/run-agent.sh\"" in steps["Antigravity"]["run"]
    for name in ("Antigravity", "Reserves, then the patch"):
        run = steps[name]["run"]
        first_git = min(i for i in (run.find('"$RUNNER_TEMP/rgit" add'), run.find("gitr reset")) if i > 0)
        for rule in ('"$RUNNER_TEMP/stop-agent"', "sudo usermod -L -e 1 agent", "sudo crontab -r -u agent",
                     'sudo chown -Rh "$(id -un):$(id -gn)" "$repo"', 'chmod -R g-w,o-w "$repo"'):
            assert -1 < run.index(rule) < first_git, (name, rule)
    context = steps["The code at the failure"]["run"]
    assert '--out-dir "$inputs"' in context and 'rm -rf "$repo/.autofix"' in context
    reserves = steps["Reserves, then the patch"]["run"]
    assert 'rm -rf "$repo/.autofix"' in reserves and '[ -f "$RUNNER_TEMP/agent-scanned" ]' in reserves
    assert "agent-scanned" in steps["Antigravity"]["run"]
    # the step limits fit in the job's, with room for the set-up
    limits = [s.get("timeout-minutes", 0) for s in fix["steps"]]
    assert all(t < fix["timeout-minutes"] for t in limits)
    assert sum(limits) + 10 <= fix["timeout-minutes"]


def test_edits_copied_with_line_numbers_or_trailing_spaces_still_apply(repo):
    """2026-11-19 (giro 2): Groq's edits were right but copied with the excerpts'
    line numbers, and nothing matched."""
    reserve = load("autofix-reserve")
    shown = {"ike/window.py": ""}
    numbered = [{"file": "ike/window.py", "find": "    1  def width():\n    2      return 10\n",
                 "replace": "    1  def width():\n    2      return 11\n"}]
    assert reserve.apply_edits(repo, numbered, shown) == ["ike/window.py"]
    assert (repo / "ike/window.py").read_text() == "def width():\n    return 11\n"
    spaced = [{"file": "ike/window.py", "find": "    return 11   ", "replace": "    return 12"}]
    reserve.apply_edits(repo, spaced, shown)
    assert (repo / "ike/window.py").read_text() == "def width():\n    return 12\n"
    with pytest.raises(ValueError):                     # still exactly once, still exact text
        reserve.apply_edits(repo, [{"file": "ike/window.py", "find": "return 99", "replace": "x"}], shown)


def test_an_answer_without_edits_is_asked_again_and_a_short_limit_is_waited_out(repo, tmp_path):
    """2026-11-19 (giro 2): OpenRouter named the cause and gave no edit, and that
    ended the chain; Groq's second try hit its per-minute limit at once."""
    import json
    reserve = load("autofix-reserve")
    _reserve_repo(repo)
    prompt = tmp_path / "prompt.md"
    prompt.write_text("RULES")
    status = tmp_path / "status.json"
    good = json.dumps({"summary": "ok", "edits": [{"file": "ike/window.py", "find": "    return 10\n",
                                                  "replace": "    return 11\n"}]})
    words = json.dumps({"summary": "The enum moved to DownloadState.", "edits": []})
    slept = []
    orig = reserve.time.sleep
    reserve.time.sleep = slept.append
    try:
        seen = []
        reserve.main(["--workdir", str(repo), "--prompt", str(prompt), "--status", str(status)],
                     env={"GROQ_API_KEY": "k", "AUTOFIX_GROQ_MODELS": "g1"},
                     opener=_opener([words, (429, {"Retry-After": "7"}), good], seen))
    finally:
        reserve.time.sleep = orig
    out = json.loads(status.read_text())
    assert out["result"] == "ok" and out["model"] == "Groq / g1", out
    assert len(seen) == 3 and 8 in slept
    git(repo, "checkout", "-q", "--", ".")
    # an explicit "fixable": false of two models still ends it
    no = json.dumps({"summary": "Un server era giù.", "fixable": False, "edits": []})
    seen = []
    reserve.main(["--workdir", str(repo), "--prompt", str(prompt), "--status", str(status)],
                 env={"GROQ_API_KEY": "k", "OPENROUTER_API_KEY": "k2"}, opener=_opener([no, no], seen))
    assert json.loads(status.read_text())["result"] == "none" and len(seen) == 2


def _run_reserves(repo, tmp_path, answers, env, seen=None):
    import json
    reserve = load("autofix-reserve")
    _reserve_repo(repo)
    prompt = tmp_path / "prompt.md"
    prompt.write_text("RULES")
    status = tmp_path / "status.json"
    seen = [] if seen is None else seen
    reserve.main(["--workdir", str(repo), "--prompt", str(prompt), "--status", str(status)],
                 env=env, opener=_opener(answers, seen))
    return json.loads(status.read_text())


GOOD = json.dumps({"summary": "Corretto.", "edits": [{"file": "ike/window.py", "find": "    return 10\n",
                                                      "replace": "    return 11\n"}]})
NOT_FIXABLE = json.dumps({"summary": "Non si corregge.", "fixable": False, "edits": []})


def test_one_model_giving_up_does_not_stop_the_reserves(repo, tmp_path):
    """1.1.18: one model answering "fixable": false stopped the whole chain;
    now the next one is asked, and only two models agreeing stop it."""
    seen = []
    out = _run_reserves(repo, tmp_path, [NOT_FIXABLE, GOOD],
                        {"GROQ_API_KEY": "k", "AUTOFIX_GROQ_MODELS": "g1, g2"}, seen)
    assert out["result"] == "ok" and out["model"] == "Groq / g2" and len(seen) == 2, out
    assert (repo / "ike/window.py").read_text() == "def width():\n    return 11\n"
    git(repo, "checkout", "-q", "--", ".")
    # one "not fixable", then nothing usable from the others: still "none", with its words
    out = _run_reserves(repo, tmp_path, [NOT_FIXABLE, 429],
                        {"GROQ_API_KEY": "k", "AUTOFIX_GROQ_MODELS": "g1, g2"})
    assert out["result"] == "none" and out["model"] == "Groq / g1", out
    assert "Non si corregge." in (repo / ".autofix/summary.md").read_text()
    # the same model twice is not two opinions
    seen = []
    out = _run_reserves(repo, tmp_path, [NOT_FIXABLE, NOT_FIXABLE, GOOD],
                        {"GROQ_API_KEY": "k", "AUTOFIX_GROQ_MODELS": "g1, g1, g2"}, seen)
    assert out["result"] == "ok" and len(seen) == 3, out


@pytest.mark.parametrize("bad", [
    json.dumps({"summary": "x", "edits": [{"file": ["ike/window.py"], "find": "a", "replace": "b"}]}),
    json.dumps({"summary": "x", "edits": "ike/window.py"}),
    json.dumps({"summary": ["x"], "fixable": True, "edits": [{"file": "ike/window.py", "find": 3, "replace": None}]}),
    json.dumps([1, 2, 3]),
    "{\"edits\": [}",
])
def test_a_malformed_answer_moves_to_the_next_model(repo, tmp_path, bad):
    """1.1.18: a list as "file" (TypeError) or content that is not text crashed
    the whole reserve step; now the next model is asked."""
    out = _run_reserves(repo, tmp_path, [bad, bad, GOOD],
                        {"GROQ_API_KEY": "k", "AUTOFIX_GROQ_MODELS": "g1, g2"})
    assert out["result"] == "ok" and out["model"] == "Groq / g2", out


def test_answers_that_are_not_text_or_raise_move_to_the_next_model(repo, tmp_path):
    import json as json_
    reserve = load("autofix-reserve")
    with pytest.raises(ValueError):
        reserve.parse({"edits": []})
    # content given as a list of parts is read; any other content is no answer
    parts = [{"type": "text", "text": GOOD}]

    def opener(answers):
        def open_(req, timeout=0):
            a = answers.pop(0)
            if isinstance(a, Exception):
                raise a
            return _Answer(json_.dumps({"choices": [{"message": {"content": a}}]}).encode())
        return open_
    _reserve_repo(repo)
    prompt = tmp_path / "prompt.md"
    prompt.write_text("RULES")
    status = tmp_path / "status.json"
    args = ["--workdir", str(repo), "--prompt", str(prompt), "--status", str(status)]
    env = {"GROQ_API_KEY": "k", "AUTOFIX_GROQ_MODELS": "g1, g2, g3"}
    reserve.main(args, env=env, opener=opener([{"odd": 1}, 42, RuntimeError("boom"), parts]))
    out = json_.loads(status.read_text())
    assert out["result"] == "ok" and out["model"] == "Groq / g3", out
    assert (repo / "ike/window.py").read_text() == "def width():\n    return 11\n"


def test_what_a_model_writes_cannot_command_the_workflow(repo, tmp_path, capsys):
    """1.1.18: a model's text printed to the log could start a GitHub workflow
    command (::add-mask::, ::set-output::, ::stop-commands::...)."""
    reserve = load("autofix-reserve")
    nasty = "x\n::error::pwned\r\n::stop-commands::tok ::warning::y :::z"
    clean = reserve.for_log(nasty)
    assert "\n" not in clean and "\r" not in clean and " " not in clean and "::" not in clean
    bad = json.dumps({"summary": "x", "edits": [{"file": "ike/x.py\n::error::injected", "find": "a", "replace": "b"}]})
    _run_reserves(repo, tmp_path, [bad, bad], {"GROQ_API_KEY": "k", "AUTOFIX_GROQ_MODELS": "g1"})
    printed = capsys.readouterr().out
    assert "injected" in printed
    assert not any(line.lstrip().startswith("::") for line in printed.splitlines()), printed


def test_the_agent_never_waits_for_a_review_nobody_gives():
    """2026-11-19: every run of Antigravity worked about 3 minutes and then
    waited until its time ran out. Its CLI waits for a review of its plans by
    default; here nobody reviews, so it must go on. Its self-updater is off too
    (the firewall refused it anyway). The denials stay."""
    fix = jobs_of((WORKFLOWS / "autofix.yml").read_text())["fix"]
    assert '"artifactReviewPolicy": "always-proceed"' in fix and '"agentMode": "accept-edits"' in fix
    assert "AGY_CLI_DISABLE_AUTO_UPDATE=true" in fix
    for rule in ('"command(*)"', '"unsandboxed(*)"', '"read_url(*)"', '"execute_url(*)"', '"mcp(*)"'):
        assert rule in fix, rule
    assert '"toolPermission"' not in fix                 # tools keep asking (and are denied)


def test_failures_of_tests_the_automation_started_reach_the_fix(monkeypatch):
    """2026-11-19: runs started with GITHUB_TOKEN send no workflow_run, so the
    second attempt never came and a failing maintenance candidate never reached
    the automatic fix. tests.yml hands such failures over itself."""
    text = (WORKFLOWS / "tests.yml").read_text()
    hand = text.split("\n  hand-over:\n", 1)[1]
    assert "needs: tests" in hand and "failure()" in hand
    assert "github.actor == 'github-actions[bot]'" in hand and "github.event_name == 'workflow_dispatch'" in hand
    assert "automation/autofix-main" in hand and "automation/daily-maintenance" in hand
    # a dispatch is handed over from the automation's branches only; main only for a run
    # the automatic fix started again (audit of #65)
    dispatch, again = hand.split("github.run_attempt > 1", 1)
    assert "'main'" not in dispatch and "github.triggering_actor == 'github-actions[bot]'" in again
    assert "permissions:\n      actions: write\n" in hand and "contents: write" not in hand
    assert 'gh workflow run autofix.yml --ref main -f run_id="$RUN_ID"' in hand
    assert "permissions:\n  contents: read\n" in text.split("jobs:")[0]
    # the plan waits for the run to close before reading its outcome
    states = [{"status": "in_progress"}, {"status": "in_progress"}, {"status": "completed", "conclusion": "failure"}]
    monkeypatch.setattr(plan_tool, "gh_api", lambda path, raw=False: states.pop(0))
    slept = []
    run = plan_tool.completed_run("o/r", "1", sleep=slept.append)
    assert run["conclusion"] == "failure" and len(slept) == 2


@pytest.mark.skipif(not __import__("shutil").which("ruff"), reason="ruff is not installed here")
def test_each_fix_goes_through_the_lint(repo, tmp_path):
    """2026-11-19: a right fix left an unused import and the guard's lint refused
    it. ruff's own safe fixes are applied first; what is left goes back as the
    reason, and the next model tries."""
    import json
    reserve = load("autofix-reserve")
    (repo / "pyproject.toml").write_text("[tool.ruff]\nline-length = 120\n")
    (repo / "ike/window.py").write_text("import os\n\n\ndef width():\n    return 10\n")
    ok, said = reserve.linted(repo, ["ike/window.py"])
    assert ok and "import os" not in (repo / "ike/window.py").read_text()   # removed, no AI
    (repo / "ike/window.py").write_text("def width():\n    return nothing_here\n")
    ok, said = reserve.linted(repo, ["ike/window.py"])
    assert not ok and "F821" in said
    git(repo, "checkout", "-q", "--", ".")
    git(repo, "clean", "-qfd")
    _reserve_repo(repo)
    prompt = tmp_path / "prompt.md"
    prompt.write_text("RULES")
    status = tmp_path / "status.json"
    bad = json.dumps({"summary": "x", "edits": [{"file": "ike/window.py", "find": "    return 10\n",
                                                "replace": "    return undefined_name\n"}]})
    good = json.dumps({"summary": "ok", "edits": [{"file": "ike/window.py", "find": "    return 10\n",
                                                  "replace": "    return 11\n"}]})
    asked = []
    opener = _opener([bad, good], [])

    def spy(req, timeout=0):
        asked.append(json.loads(req.data)["messages"][1]["content"])
        return opener(req, timeout)
    reserve.main(["--workdir", str(repo), "--prompt", str(prompt), "--status", str(status), "--lint"],
                 env={"GROQ_API_KEY": "k", "AUTOFIX_GROQ_MODELS": "g1, g2"}, opener=spy)
    assert json.loads(status.read_text())["result"] == "ok"
    assert "F821" in asked[1] and (repo / "ike/window.py").read_text() == "def width():\n    return 11\n"


def test_a_missing_name_comes_with_its_working_uses(repo):
    """2026-11-19 (giro 2): after a simulated PyQt change a reserve wrote
    DownloadState.Completed, then went back to the error itself; the right
    form was in ike/dialogs.py all along."""
    ctx = load("autofix-context")
    (repo / "ike/app.py").write_text("from x import R as DR\n\n\ndef tick(st):\n    return st == DR.DownloadInProgress\n"
                                     "\n\ndef done(st):\n    return st == DR.DownloadInProgress\n")
    (repo / "ike/dialogs.py").write_text("def state(d):\n    S = R.DownloadState\n    return S.DownloadInProgress\n")
    failure = ('  File "/x/ike/app.py", line 5, in tick\n'
               "AttributeError: type object 'R' has no attribute 'DownloadInProgress'\n")
    text, related = ctx.build(repo, failure)
    part = text.split("# The same names elsewhere in I.K.E.", 1)[1]
    assert "`ike/dialogs.py` uses `DownloadInProgress`" in part and "S = R.DownloadState" in part
    assert "ike/app.py" not in part.split("Files involved")[0]   # never the failing file's own mistakes
    assert related == ["ike/app.py"]                             # the pertinence stays on the error
    assert "same names elsewhere" not in ctx.build(repo, "ImportError: x\n")[0]


def test_after_two_attempts_the_issue_still_carries_the_message_for_chatgpt(tmp_path):
    """2026-11-19: when two automatic fixes did not pass, the issue said only
    "servono le tue mani", without the failure and without ChatGPT's message."""
    import os
    import subprocess
    script = step_script("Tell the owner")
    temp = tmp_path / "runner"
    (temp / "failure").mkdir(parents=True)
    (temp / "failure" / "failure.md").write_text("## Job `tests`\nAttributeError: no attribute 'Completed'\n")
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    (bin_ / "gh").write_text('#!/bin/sh\nfor a in "$@"; do last="$a"; done\n'
                             'case "$*" in *"issue create"*|*"issue comment"*) cp "$last" "%s";; esac\nexit 0\n'
                             % (tmp_path / "body.md"))
    (bin_ / "gh").chmod(0o755)
    env = dict(os.environ, RUNNER_TEMP=str(temp), PATH="%s:%s" % (bin_, os.environ["PATH"]),
               ACTION="issue", REASON="2 automatic fixes did not make it pass", WORKFLOW="Tests",
               CHECKOUT="d0b6c21", FIX="skipped", PATCH="", AGENT="", GUARD="skipped", PUBLISH="skipped",
               RUN_URL="https://example.test/run", GH_TOKEN="x", GH_REPO="o/r")
    run = subprocess.run(["bash", "-e", "-c", script], env=env, capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stdout + run.stderr
    body = (tmp_path / "body.md").read_text()
    assert "2 automatic fixes did not make it pass" in body
    assert "Messaggio per ChatGPT" in body and "from commit d0b6c21" in body
    # 2026-11-19: ChatGPT fixed it right and stopped before the pull request
    assert "3. Open a pull request from chatgpt/fix-" in body and "This step is required" in body
    assert "4. Reply with the link of the pull request" in body
    assert "no attribute 'Completed'" in body


def _issue_body(tmp_path, summary, **env_):
    import os
    import subprocess
    script = step_script("Tell the owner")
    temp = tmp_path / "runner"
    (temp / "autofix").mkdir(parents=True)
    (temp / "failure").mkdir()
    (temp / "autofix" / "summary.md").write_text(summary)
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    (bin_ / "gh").write_text('#!/bin/sh\nfor a in "$@"; do last="$a"; done\n'
                             'case "$*" in *"issue create"*|*"issue comment"*) cp "$last" "%s";; esac\nexit 0\n'
                             % (tmp_path / "body.md"))
    (bin_ / "gh").chmod(0o755)
    env = dict(os.environ, RUNNER_TEMP=str(temp), PATH="%s:%s" % (bin_, os.environ["PATH"]),
               ACTION="fix", REASON="", WORKFLOW="Tests", CHECKOUT="d0b6c21", HEAD_SHA="abc1234def",
               FIX="success", PATCH="true", AGENT="ok", GUARD="failure", PUBLISH="skipped",
               RUN_URL="https://example.test/run", GH_TOKEN="x", GH_REPO="o/r")
    env.update(env_)
    run = subprocess.run(["bash", "-e", "-c", script], env=env, capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stdout + run.stderr
    return (tmp_path / "body.md").read_text()


@pytest.mark.parametrize("change, ok", [
    ({"tests/test_x.py": "def test_a():\n    pass\n"}, False),                              # one test less
    ({"tests/conftest.py": "def pytest_collection_modifyitems(items):\n    items.clear()\n"}, False),
    ({"tests/test_x.py": "def test_a():\n    pass\n\n\ndef test_b():\n    pass\n\n\ndel test_b\n"}, False),
    ({"tests/test_y.py": "def test_c():\n    pass\n"}, True),                               # one more
    ({"ike/x.py": "X = 2\n"}, True),
    # 1.1.18 (second review): a new test does not hide a dropped one
    ({"tests/test_x.py": "def test_a():\n    pass\n", "tests/test_y.py": "def test_c():\n    pass\n"}, False),
])
def test_tests_yml_refuses_a_change_that_runs_fewer_tests(tmp_path, change, ok):
    """1.1.18 (review): whatever way a fix finds to drop a test, the tests of an
    automatic, maintenance or ChatGPT branch count the tests pytest would run
    against the commit the branch starts from."""
    import os
    import subprocess
    import sys
    import textwrap
    lines = (WORKFLOWS / "tests.yml").read_text().splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.strip() == "- name: No tests lost")
    assert "startsWith(github.head_ref, 'chatgpt/')" in "\n".join(lines[start:start + 5])
    run_at = next(i for i in range(start, len(lines)) if lines[i].strip() == "run: |")
    body = []
    for ln in lines[run_at + 1:]:
        if ln.strip() and len(ln) - len(ln.lstrip()) <= 8:
            break
        body.append(ln)
    script = textwrap.dedent("\n".join(body)) + "\n"

    def g(cwd, *a):
        return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-C", str(cwd), *a],
                              capture_output=True, text=True, check=True).stdout.strip()
    bare = tmp_path / "remote.git"
    g(tmp_path, "init", "-q", "--bare", str(bare))
    work = tmp_path / "work"
    g(tmp_path, "init", "-q", "-b", "main", str(work))
    (work / "tests").mkdir()
    (work / "ike").mkdir()
    (work / "tests/test_x.py").write_text("def test_a():\n    pass\n\n\ndef test_b():\n    pass\n")
    (work / "ike/x.py").write_text("X = 1\n")
    # as the real pyproject.toml: its -q made the count -qq, with no test ids (second review)
    (work / "pyproject.toml").write_text('[tool.pytest.ini_options]\ntestpaths = ["tests"]\naddopts = "-q"\n')
    g(work, "add", "-A")
    g(work, "commit", "-qm", "base")
    g(work, "remote", "add", "origin", str(bare))
    g(work, "push", "-q", "origin", "main")
    g(work, "checkout", "-q", "-b", "automation/autofix-main")
    for rel, text in change.items():
        (work / rel).write_text(text)
    g(work, "add", "-A")
    g(work, "commit", "-qm", "fix")
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    (bin_ / "python").symlink_to(sys.executable)
    temp = tmp_path / "runner"
    temp.mkdir()
    env = dict(os.environ, RUNNER_TEMP=str(temp), PATH="%s:%s" % (bin_, os.environ["PATH"]))
    run = subprocess.run(["bash", "-e", "-c", script], cwd=work, env=env, capture_output=True, text=True,
                         timeout=300)
    assert (run.returncode == 0) is ok, run.stdout + run.stderr
    assert "Tests here: " in run.stdout and "no comparison" not in run.stdout, run.stdout
    if not ok:
        assert "lost: tests/test_x.py::test_b" in run.stdout or "test_b" in run.stdout


def test_no_dead_parts_in_the_workflows():
    """1.1.18: tests.yml offered workflow_call (nothing called it), the test
    environment claimed autofix.yml used it, and a refusal was copied to a
    file nobody read."""
    tests = (WORKFLOWS / "tests.yml").read_text()
    assert "workflow_call" not in tests and "inputs." not in tests
    callers = [p.name for p in WORKFLOWS.glob("*.yml") if "uses: ./.github/workflows/tests.yml" in p.read_text()]
    assert callers == []
    env = (ROOT / ".github/actions/ike-test-env/action.yml").read_text()
    users = [p.name for p in WORKFLOWS.glob("*.yml") if "uses: ./.github/actions/ike-test-env" in p.read_text()]
    assert sorted(users) == ["security.yml", "tests.yml"]      # 1.1.18: the sandbox job uses it too
    assert "autofix.yml:" not in env and "shared by tests.yml and autofix.yml" not in env
    assert "guard-refused.md" not in (WORKFLOWS / "autofix.yml").read_text()


# the ids of 1.1.18 stay ("No tests lost" counts them): (old, waiting, pushed)
@pytest.mark.parametrize("old, waiting, pushed", [
    ("tip1", "", True),          # where the plan saw it, nothing waiting: pushed
    ("tip2", "", False),         # pushed by another run after this plan: an error, the owner looks
    ("tip1", "12", False),       # another automatic fix of main is waiting: overtaken, ends well
])
def test_a_first_fix_of_main_never_overwrites_another(tmp_path, old, waiting, pushed):
    """1.1.18 (review): two runs planned side by side could each push a first
    fix of main, the later one replacing the other's."""
    _publish(tmp_path, old, waiting, "main", pushed, ok=pushed or bool(waiting))


@pytest.mark.parametrize("old, waiting, kind, pushed, ok", [
    ("tip2", "12", "main", False, True),         # the other run published first: overtaken
    ("main1", "", "maintenance", True, True),    # the candidate the agent started from: pushed
    ("cand2", "", "maintenance", False, True),   # a newer candidate came: overtaken, no issue
    ("fixnew", "", "maintenance", False, True),  # audit of #65: pushed by an earlier try: PR and tests follow
    ("fixnew", "77", "main", False, True),       # the same for a first fix of main whose PR exists
])
def test_a_fix_overtaken_or_already_pushed(tmp_path, old, waiting, kind, pushed, ok):
    """Final review: a fix overtaken by a newer one (a fix already waiting, a
    newer candidate) ends well without pushing, so the report job opens no
    "needs you" issue for a race that lost nothing. Audit of #65: a fix
    already pushed by an earlier try of the job still gets its pull request
    and its tests."""
    _publish(tmp_path, old, waiting, kind, pushed, ok)


def _publish(tmp_path, old, waiting, kind, pushed, ok):
    import os
    import subprocess
    script = step_script("Push the fix, update the draft PR and start the tests")
    temp = tmp_path / "runner"
    (temp / "autofix").mkdir(parents=True)
    for name in ("summary.md", "guard.md"):
        (temp / "autofix" / name).write_text("x\n")
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    calls = tmp_path / "calls"
    (bin_ / "git").write_text('#!/bin/sh\ncase "$*" in *"rev-parse refs/heads/autofix-result"*) echo fixnew;; '
                              '*rev-parse*) echo "$FAKE_OLD";; *" push "*) '
                              'echo push >> "%s";; esac\nexit 0\n' % calls)
    gh_calls = tmp_path / "gh-calls"
    (bin_ / "gh").write_text('#!/bin/sh\necho "$*" >> "%s"\ncase "$*" in "pr list"*) echo "$FAKE_PR";; esac\nexit 0\n'
                             % gh_calls)
    (temp / "autofix" / "summary.md").write_text("Fixed, thanks @someone. Closes #12, fixes owner/repo#3.\n")
    for f in ("git", "gh"):
        (bin_ / f).chmod(0o755)
    env = dict(os.environ, RUNNER_TEMP=str(temp), PATH="%s:%s" % (bin_, os.environ["PATH"]), GH_TOKEN="x",
               KIND=kind, PUSH_BRANCH="automation/autofix-main", CHECKOUT="main1", PUSH_TIP="tip1",
               WORKFLOW="Tests", ATTEMPT="1", RUN_URL="u", FAKE_OLD=old, FAKE_PR=waiting,
               GITHUB_STEP_SUMMARY=str(tmp_path / "summary"))
    run = subprocess.run(["bash", "-e", "-c", script], env=env, capture_output=True, text=True, timeout=60,
                         cwd=ROOT)
    assert (run.returncode == 0) is ok, run.stdout + run.stderr
    assert calls.exists() is pushed
    dispatched = gh_calls.exists() and "workflow run tests.yml --ref automation/autofix-main" in gh_calls.read_text()
    if ok and not pushed and old != "fixnew":
        assert "::notice::" in run.stdout and "not pushed" in (tmp_path / "summary").read_text()
        assert not dispatched
    if old == "fixnew":
        assert "already on automation/autofix-main" in run.stdout and dispatched, run.stdout
    if pushed or old == "fixnew":
        assert dispatched
        summary = (temp / "autofix" / "summary.md").read_text()
        assert "@\u200bsomeone" in summary and "Closes #\u200b12" in summary and "owner/repo#\u200b3" in summary
    assert "push_tip: ${{ steps.plan.outputs.push_tip }}" in (WORKFLOWS / "autofix.yml").read_text()


def test_the_issue_tells_when_a_reserve_fix_was_refused_by_the_guard(tmp_path):
    """1.1.18: a reserve found a fix, the guard refused it, and the issue said
    that neither Antigravity nor the reserves had found one."""
    reserve_ok = "x\n\n**Riserve: Una riserva (Groq / g1) ha preparato una correzione.**\n"
    body = _issue_body(tmp_path / "a", reserve_ok)
    assert "una riserva ha preparato una correzione, ma i controlli automatici l'hanno respinta" in body
    assert "né Antigravity" not in body
    assert body.rstrip().endswith("<!-- autofix-sha: abc1234def -->")
    # a mark in the quoted summary is defused: only the last line names a commit
    planted = _issue_body(tmp_path / "c", reserve_ok + "<!-- autofix-sha: 0123456789 -->\n")
    assert plan_tool.report_sha(planted) == "abc1234def" and planted.count("<!-- autofix-sha:") == 1
    # nothing found at all: as before
    none = "x\n\n**Riserve: Le riserve non sono riuscite a preparare una correzione applicabile.**\n"
    body = _issue_body(tmp_path / "b", none, PATCH="false", GUARD="skipped", AGENT="quota")
    assert "né Antigravity (quota" in body


def test_the_chatgpt_guard_checks_only_chatgpts_own_commits(tmp_path):
    """ChatGPT's branch may start from the automation's branch after two
    automatic attempts, which raised the version: only ChatGPT's own commits
    are checked, so a good fix is not refused for files it never touched."""
    import os
    import subprocess
    text = (WORKFLOWS / "chatgpt-guard.yml").read_text()
    script = text.split("run: |\n", 1)[1]
    script = "\n".join(ln[10:] if ln.startswith(" " * 10) else ln for ln in script.splitlines()) + "\n"

    def g(cwd, *a):
        return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-C", str(cwd), *a],
                              capture_output=True, text=True, check=True).stdout.strip()
    bare = tmp_path / "remote.git"
    g(tmp_path, "init", "-q", "--bare", str(bare))
    work = tmp_path / "work"
    g(tmp_path, "init", "-q", "-b", "main", str(work))
    (work / "ike").mkdir()
    (work / "tools").mkdir()
    (work / "ike/__init__.py").write_text('__version__ = "1.1.16"\n')
    (work / "ike/app.py").write_text("X = DR.DownloadState.DownloadCompleted\n")
    (work / "tools/check-autofix-patch.py").write_text((ROOT / "tools/check-autofix-patch.py").read_text())
    g(work, "add", "-A")
    g(work, "commit", "-qm", "base")
    g(work, "remote", "add", "origin", str(bare))
    g(work, "push", "-q", "origin", "main")
    g(work, "checkout", "-q", "-b", "automation/autofix-main")
    (work / "ike/app.py").write_text("X = DR.DownloadCompleted\n")            # the failure
    (work / "ike/__init__.py").write_text('__version__ = "1.1.17"\n')         # an automatic attempt's bump
    g(work, "commit", "-qam", "attempts")
    g(work, "push", "-q", "origin", "automation/autofix-main")
    for name, content, expected in (("chatgpt/good", "X = DR.DownloadState.DownloadCompleted\n", 0),
                                    ("chatgpt/bad", None, 1)):
        g(work, "checkout", "-q", "-B", name, "automation/autofix-main")
        if content:
            (work / "ike/app.py").write_text(content)
        else:
            (work / "ike/updater.py").write_text("CHECK = False\n")         # a protected file
        g(work, "add", "-A")
        g(work, "commit", "-qm", "chatgpt")
        head = g(work, "rev-parse", "HEAD")
        g(work, "push", "-q", "-f", "origin", name)
        clone = tmp_path / ("clone-" + name.split("/")[1])
        g(tmp_path, "clone", "-q", "-b", "main", str(bare), str(clone))
        env = dict(os.environ, HEAD_SHA=head, RUNNER_TEMP=str(tmp_path), GITHUB_STEP_SUMMARY=str(tmp_path / "sum.md"))
        run = subprocess.run(["bash", "-e", "-c", script], cwd=clone, env=env, capture_output=True, text=True)
        assert run.returncode == expected, (name, run.stdout, run.stderr)
        if expected == 0:
            assert "1 commits" in run.stdout                   # the attempts' version bump not counted


def test_closed_chatgpt_branches_are_deleted_and_nothing_else():
    """The branches of ChatGPT's pull requests closed without merge go away by
    themselves (the session that maintains the project cannot delete
    branches). Only chatgpt/* of this repository; nothing of the pull request
    is checked out or run."""
    text = (WORKFLOWS / "chatgpt-cleanup.yml").read_text()
    assert "pull_request_target:\n    types: [closed]" in text and "permissions: {}" in text
    assert "github.event.pull_request.merged == false" in text
    assert "startsWith(github.event.pull_request.head.ref, 'chatgpt/')" in text
    assert "head.repo.full_name == github.repository" in text
    assert "permissions:\n      contents: write\n" in text
    assert "checkout" not in text and "python" not in text and "secrets." not in text
    assert 'chatgpt/*) gh api -X DELETE "repos/$GH_REPO/git/refs/heads/$BRANCH"' in text


def test_a_gone_openrouter_model_is_replaced_by_one_offered_now(repo, tmp_path):
    """1.1.18 (seen in the first real trial: a listed free model answered 404):
    the chain asks OpenRouter for its free models now and tries the largest
    ones, never an id of an odd shape and never one already tried."""
    import json
    reserve = load("autofix-reserve")
    _reserve_repo(repo)
    prompt = tmp_path / "prompt.md"
    prompt.write_text("RULES")
    good = json.dumps({"summary": "Corretto.", "fixable": True, "edits": [
        {"file": "ike/window.py", "find": "    return 10\n", "replace": "    return 11\n"}]})
    listing = {"data": [
        {"id": "small/model:free", "context_length": 8000},
        {"id": "big/model:free", "context_length": 200000},
        {"id": "paid/model", "context_length": 900000},
        {"id": "bad id; rm -rf /:free", "context_length": 900000},
        {"id": "gone/a:free", "context_length": 500000},
        {"id": "mid/model:free", "context_length": 64000}]}
    seen = []

    def opener(req, timeout=0):
        if req.full_url.endswith("/models"):
            seen.append(("list", req.get_header("Authorization")))
            return _Answer(json.dumps(listing).encode())
        model = json.loads(req.data)["model"]
        seen.append(("ask", model))
        if model == "gone/a:free":
            raise __import__("urllib.error").error.HTTPError(req.full_url, 404, "gone", {}, None)
        if model == "big/model:free":
            return _Answer(json.dumps({"choices": [{"message": {"content": "not json"}}]}).encode())
        return _Answer(json.dumps({"choices": [{"message": {"content": good}}]}).encode())

    env = {"OPENROUTER_API_KEY": "sk-or-TESTONLY", "AUTOFIX_OPENROUTER_MODELS": "gone/a:free"}
    status = tmp_path / "status.json"
    reserve.main(["--workdir", str(repo), "--prompt", str(prompt), "--status", str(status)],
                 env=env, opener=opener)
    out = json.loads(status.read_text())
    assert out["result"] == "ok" and out["model"] == "OpenRouter / mid/model:free", (out, seen)
    asked = [m for kind, m in seen if kind == "ask"]
    assert asked[0] == "gone/a:free" and "big/model:free" in asked and asked[-1] == "mid/model:free"
    assert not any(m in asked for m in ("paid/model", "small/model:free", "bad id; rm -rf /:free"))
    assert [k for k, _m in seen].count("list") == 1          # the list is asked for once


def test_no_openrouter_list_means_the_chain_simply_goes_on():
    reserve = load("autofix-reserve")

    def broken(req, timeout=0):
        raise OSError("no network")
    assert reserve.free_models("k", broken) == []

    def odd(req, timeout=0):
        return _Answer(b'{"data": "nope"}')
    assert reserve.free_models("k", odd) == []


# --- 1.1.18, third review: the validators on their own (no AI) --------------------

PARAM = ("import pytest\n\nREAL = [1, 2]\n\n\n@pytest.mark.parametrize('n', REAL)\ndef test_n(n):\n"
         "    assert n > 0\n\n\n" + WIDTH)
TWO = "    assert 1\n    assert 2\n"
WEAKER = {
    # each of these passed the checker before the third review
    "empty parametrize": (PARAM.replace("parametrize('n', REAL)", "parametrize('n', [])"), "by code"),
    "list emptied": (PARAM.replace("REAL = [1, 2]", "REAL = []"), "empties the parameters"),
    "try except pass": (WIDTH.replace(TWO, "    try:\n        assert 1\n        assert 2\n"
                                      "    except AssertionError:\n        pass\n"), "by code"),
    "except Exception": (WIDTH.replace(TWO, "    try:\n        assert 1\n        assert 2\n"
                                       "    except Exception:\n        pass\n"), "moved into a block"),
    "suppress": (WIDTH.replace(TWO, "    import contextlib\n    with contextlib.suppress(AssertionError):\n"
                               "        assert 1\n        assert 2\n"), "by code"),
    "under if": (WIDTH.replace(TWO, "    import os\n    if os.environ.get('NEVER'):\n        assert 1\n"
                               "        assert 2\n"), "moved into a block"),
    "return later": (WIDTH.replace(TWO, "    x = 1\n    return x\n" + TWO), "return in the body of a test"),
    "__test__": ("__test__ = False\n" + WIDTH, "by code"),
    "fixture": ("import pytest\n\n\n@pytest.fixture\n" + WIDTH, "decorator that may replace a test"),
    "skipif in a name": ("import pytest\n\nneeds = pytest.mark.skipif(True, reason='x')\n\n\n@needs\n" + WIDTH,
                         "skip or xfail"),
    "a name only": ("from tests.test_more import needs\n\n\n@needs\n" + WIDTH, "decorator that may replace a test"),
    "pytest replaced": (WIDTH + "\n\nimport pytest\npytest.fail = lambda *a, **k: None\n", "by code"),
    "harness replaced": ("from tests import harness\nharness.run = lambda *a, **k: {}\n" + WIDTH, "by code"),
    "setattr": (WIDTH + "\n\nimport sys\nsetattr(sys.modules[__name__], 'test_width', None)\n", "by code"),
    "module dict": (WIDTH + "\n\nimport sys\nsys.modules[__name__].__dict__.pop('test_width')\n", "by code"),
    "generate_tests": (WIDTH + "\n\ndef pytest_generate_tests(metafunc):\n    metafunc.parametrize('x', [])\n",
                       "by code"),
    "plugins": ("pytest_plugins = ['tests.evil']\n" + WIDTH, "by code"),
}


@pytest.mark.parametrize("name", sorted(WEAKER))
def test_the_third_review_weakenings_are_refused(repo, tmp_path, name):
    text, why = WEAKER[name]
    if "param" in name or "list" in name:
        (repo / "tests/test_window.py").write_text(PARAM)
        git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "a parametrized test")
    code, report = run_guard(repo, make_patch(repo, edit("tests/test_window.py", text)), tmp_path)
    assert code == 3 and why in report, (name, report)


@pytest.mark.parametrize("src, dst", [
    ("tests/conftest.py", "tests/conftest_old.py"),       # the harness, gone by a rename
    ("tests/test_window.py", "docs/old_test.py"),         # a test module, gone by a rename
    ("ike/updater.py", "ike/updater_old.py"),             # a protected file, gone by a rename
    (".github/workflows/tests.yml", "docs/tests.yml"),    # a workflow, gone by a rename
])
def test_a_rename_never_removes_a_file_unseen(repo, tmp_path, src, dst):
    """Third review: `git apply --numstat` names only the new file of a rename,
    so a rename of a test module, the harness, the updater or a workflow passed
    (the "=>" the checker looked for never appears there). The fix job's own
    `git diff` detects renames, so this was reachable."""
    def move(r):
        (r / dst).parent.mkdir(parents=True, exist_ok=True)
        (r / src).rename(r / dst)
    patch = make_patch(repo, move)
    assert "rename from " + src in patch
    code, report = run_guard(repo, patch, tmp_path)
    assert code == 3 and src in report, report
    assert (repo / src).exists() and not (repo / dst).exists()
    # an ordinary file renamed is still refused, but not as a safety matter
    plain = make_patch(repo, lambda r: (r / "ike/window.py").rename(r / "ike/window2.py"))
    assert run_guard(repo, plain, tmp_path)[0] == 1


def test_a_quoted_file_name_does_not_blind_the_checks(repo, tmp_path):
    """Third review: git reads "\\164ests/x" (octal for t) as tests/x; the checks
    read the name as written, did not see a test file and passed a skip."""
    patch = make_patch(repo, edit("tests/test_window.py", "import pytest\n\n\n@pytest.mark.skip\n" + WIDTH))
    hidden = patch.replace("diff --git a/tests/test_window.py b/tests/test_window.py",
                           'diff --git "a/\\164ests/test_window.py" "b/\\164ests/test_window.py"')
    hidden = hidden.replace("--- a/tests/test_window.py\n", '--- "a/\\164ests/test_window.py"\n')
    hidden = hidden.replace("+++ b/tests/test_window.py\n", '+++ "b/\\164ests/test_window.py"\n')
    assert '+++ "b/\\164ests/test_window.py"' in hidden
    assert subprocess.run(["git", "-C", str(repo), "apply", "--check", "-"], input=hidden, text=True).returncode == 0
    code, report = run_guard(repo, hidden, tmp_path)
    assert code == 3 and "skip or xfail" in report and "tests/test_window.py" in report, report
    assert guard.unquote('"a\\tb\\"c\\\\d\\303\\251"') == 'a\tb"c\\dé'
    assert guard.renamed_paths("rename tests/{a.py => b.py} (100%)") == ["tests/a.py", "tests/b.py"]
    assert guard.renamed_paths("rename {tests => docs}/a.py (90%)") == ["tests/a.py", "docs/a.py"]
    assert guard.renamed_paths("rename tests/{ => sub}/a.py (90%)") == ["tests/a.py", "tests/sub/a.py"]
    # a name git reads otherwise than the checks (tests//x is tests/x for git)
    odd = patch.replace("tests/test_window.py", "tests//test_window.py")
    code, report = run_guard(repo, odd, tmp_path)
    assert code == 3 and "reads differently" in report, report


def test_honest_test_changes_still_pass_the_third_review(repo, tmp_path):
    """No false alarm on the usual corrections: a parametrized test added, an
    empty list inside a test, a return in a helper or in a nested function, a
    mark or a patch on a test, an assertion moved out of a block."""
    honest = [
        PARAM,
        WIDTH + "\n\ndef test_list():\n    opened = []\n    assert opened == []\n",
        WIDTH + "\n\ndef helper():\n    return 1\n",
        WIDTH + "\n\ndef test_inner():\n    def inner():\n        return 2\n    assert inner() == 2\n",
        "import pytest\n\n\n@pytest.mark.parametrize('n', [1, '', 2])\n" + WIDTH.replace("()", "(n)"),
        "from unittest import mock\n\n\n@mock.patch('os.sep', '/')\n" + WIDTH.replace("()", "(_sep)"),
        "def test_width():\n    for x in (1,):\n        y = x\n    assert y\n    assert 1\n    assert 2\n",
    ]
    for text in honest:
        code, report = run_guard(repo, make_patch(repo, edit("tests/test_window.py", text)), tmp_path,
                                 "--check-only")
        assert code == 0, (text, report)
    (repo / "tests/test_window.py").write_text("def test_width():\n    x = 1\n    if x:\n        assert x == 1\n")
    git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "nested")
    out = edit("tests/test_window.py", "def test_width():\n    x = 1\n    assert x == 1\n")
    code, report = run_guard(repo, make_patch(repo, out), tmp_path, "--check-only")
    assert code == 0, report


def test_the_new_rules_find_nothing_in_the_existing_tests(tmp_path):
    """The rules of the third review, run on every test module of the
    repository as if it were added: nothing found but the marks the modules
    really put on their tests (@needs_engine, @needs_node: skipif in a name)."""
    new_marks = ("decorator that may replace a test", "empties the parameters", "return in the body",
                 "moved into a block", "reads differently", "renamed or copied")
    empty = tmp_path / "empty"
    subprocess.run(["git", "init", "-q", str(empty)], check=True)
    for path in sorted((ROOT / "tests").glob("test_*.py")):
        if path.name == "test_automation.py":           # it quotes the attacks on purpose
            continue
        lines = path.read_text().splitlines()
        patch = ("diff --git a/tests/{0} b/tests/{0}\nnew file mode 100644\n--- /dev/null\n+++ b/tests/{0}\n"
                 "@@ -0,0 +1,{1} @@\n".format(path.name, len(lines)) + "".join("+" + ln + "\n" for ln in lines))
        found = [r for r in guard.check(empty, patch) if any(m in r for m in new_marks) and "@needs_" not in r]
        assert found == [], (path.name, found)


# --- final review of 1.1.18: a new engine that does not build reaches its branch ----

def _engine_step(tmp_path, fetch, build, candidate, main):
    """The real shell of daily-maintenance.yml's engine step, with a fake cargo,
    in a repository whose origin/main has Cargo.lock `main`."""
    import os
    work = tmp_path / "work"
    (work / "ike-adblock").mkdir(parents=True)
    (work / "ike-adblock/Cargo.lock").write_text(main)
    git(tmp_path, "init", "-q", str(work))
    git(work, "-c", "user.name=t", "-c", "user.email=t@t", "add", "-A")
    git(work, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "main")
    git(work, "update-ref", "refs/remotes/origin/main", "HEAD")
    (work / "ike-adblock/Cargo.lock").write_text(candidate)
    (work / "component-report.md").write_text("# Components\n")
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    (bin_ / "cargo").write_text('#!/bin/sh\ncase "$1" in fetch) exit %d;; build) exit %d;; esac\nexit 9\n'
                                % (fetch, build))
    (bin_ / "cargo").chmod(0o755)
    out = tmp_path / "out"
    env = dict(os.environ, GITHUB_OUTPUT=str(out), PATH="%s:%s" % (bin_, os.environ["PATH"]))
    script = step_script("Build AdBlock engine of the candidate", "daily-maintenance.yml")
    run = subprocess.run(["bash", "-e", "-c", script], cwd=work, env=env, capture_output=True, text=True, timeout=60)
    outputs = dict(ln.split("=", 1) for ln in out.read_text().splitlines()) if out.exists() else {}
    return run, outputs, (work / "component-report.md").read_text()


@pytest.mark.parametrize("fetch, build, candidate, ok, engine", [
    (0, 0, "0.13.7", True, "builds"),       # builds: as before
    (0, 1, "0.13.7", True, "broken"),       # a new engine that does not build: published, marked
    (0, 1, "0.13.6", False, None),          # the same engine does not build: stop, a person looks
    (1, 0, "0.13.7", False, None),          # its crates cannot be downloaded: GitHub's or crates.io's matter
])
def test_a_new_engine_that_does_not_build_still_reaches_its_branch(tmp_path, fetch, build, candidate, ok, engine):
    """Until the final review of 1.1.18 the daily maintenance stopped at the
    engine's build and the candidate never reached its branch, where the fix
    may change I.K.E.'s wrapper. Now it reaches it, marked."""
    run, outputs, report = _engine_step(tmp_path, fetch, build, LOCK % candidate, LOCK % "0.13.6")
    assert (run.returncode == 0) is ok, run.stdout + run.stderr
    assert outputs.get("engine") == engine, outputs
    if engine == "broken":
        assert "::warning::the new AdBlock engine (adblock 0.13.6 -> 0.13.7) does not build" in run.stdout
        assert "does not build with I.K.E.'s wrapper yet" in report and "never `Cargo.toml`" in report
    else:
        assert "does not build" not in report
    if fetch:
        assert "could not be downloaded" in run.stdout
    # the version is read as the plan reads it
    assert plan_tool.adblock_version(LOCK % candidate) == candidate


def test_the_marked_candidate_is_fixed_on_its_branch_and_only_in_the_wrapper(repo, tmp_path):
    text = (WORKFLOWS / "daily-maintenance.yml").read_text()
    prepare = jobs_of(text)["prepare"]
    # built after the automatic fixes carried over, before the bundle
    assert prepare.index("git cherry-pick -x") < prepare.index("name: Build AdBlock engine of the candidate") \
        < prepare.index("git bundle create")
    assert "engine: ${{ steps.engine.outputs.engine }}" in prepare
    publish = jobs_of(text)["publish-candidate"]
    assert "ENGINE: ${{ needs.prepare.outputs.engine }}" in publish
    assert '"$ENGINE" = "broken"' in publish and "(the new AdBlock engine does not build yet)" in publish
    # its tests fail there, the fix may change the wrapper and nothing else of the engine
    plan = plan_tool.decide(failed_run(branch="automation/daily-maintenance", _engine_update=True),
                            [{"name": "tests", "conclusion": "failure",
                              "steps": [{"name": "AdBlock engine (Rust tests)", "conclusion": "failure"}]}], "")
    assert plan["action"] == "fix" and plan["kind"] == "maintenance" and plan["allow_adblock"] == "true"
    wrapper = make_patch(repo, edit("ike-adblock/src/lib.rs", "// fixed for the new engine\n", "a"))
    assert run_guard(repo, wrapper, tmp_path, "--allow-adblock", "--check-only")[0] == 0
    for rel in ("ike-adblock/Cargo.toml", "ike-adblock/Cargo.lock"):
        code, report = run_guard(repo, make_patch(repo, edit(rel, "# x\n", "a")), tmp_path, "--allow-adblock")
        assert code == 3 and "third-party or generated" in report, report
    # the step that still stops the daily run is an issue, never a fix of main
    stopped = {"name": "prepare", "conclusion": "failure",
               "steps": [{"name": "Build AdBlock engine of the candidate", "conclusion": "failure"}]}
    p = plan_tool.decide(failed_run(name="Daily maintenance candidate"), [stopped], "")
    assert p["action"] == "issue" and "not a matter for I.K.E.'s wrapper" in p["reason"]


# --- final review of 1.1.18: the installer, the self-test ---------------------------

def test_the_installer_hash_comes_from_a_variable_and_the_installer_is_kept(tmp_path):
    import hashlib
    import os
    fix = jobs_of((WORKFLOWS / "autofix.yml").read_text())["fix"]
    assert "AGY_INSTALLER_SHA256: ${{ vars.AGY_INSTALLER_SHA256 || '' }}" in fix
    keep = fix.split("name: Keep the Antigravity installer", 1)[1].split("\n      - ", 1)[0]
    assert "if: always()" in keep and "agy-installer/" in keep and "retention-days: 3" in keep
    room = step_script("A closed room for the agent")
    # kept before it is checked and long before it runs
    assert room.index('cp /srv/autofix/agy-install.sh "$RUNNER_TEMP/agy-installer/install.sh"') \
        < room.index('"$got" != "$AGY_INSTALLER_SHA256"') < room.index("sudo -u agent -H bash /srv/autofix/agy-install.sh")
    # the check itself, with a fake download: a different installer stops the room
    srv, temp, bin_ = tmp_path / "srv", tmp_path / "runner", tmp_path / "bin"
    for d in (srv, temp, bin_):
        d.mkdir()
    (bin_ / "sudo").write_text("#!/bin/sh\nexit 0\n")
    (bin_ / "curl").write_text('#!/bin/sh\nwhile [ "$1" != "-o" ]; do shift; done\necho "echo installer" > "$2"\n')
    for f in ("sudo", "curl"):
        (bin_ / f).chmod(0o755)
    installer = hashlib.sha256(b"echo installer\n").hexdigest()
    script = room.replace("/srv/autofix", str(srv))
    for recorded, stopped in (("0" * 64, True), (installer, False), ("", False)):
        env = dict(os.environ, RUNNER_TEMP=str(temp), GITHUB_WORKSPACE=str(tmp_path), AGY_INSTALLER_SHA256=recorded,
                   PATH="%s:%s" % (bin_, os.environ["PATH"]))
        run = subprocess.run(["bash", "-e", "-c", script], env=env, capture_output=True, text=True, timeout=60)
        assert ("is not the one recorded" in run.stdout) is stopped, run.stdout + run.stderr
        if stopped:
            assert run.returncode == 1
        assert "Antigravity installer sha256: %s" % installer in run.stdout
        assert (temp / "agy-installer/install.sh").read_text() == "echo installer\n"
        assert (temp / "agy-installer/install.sh.sha256").read_text() == "%s  install.sh\n" % installer


def test_the_self_test_runs_the_very_closed_room_of_the_fix():
    text = (WORKFLOWS / "autofix.yml").read_text()
    jobs = jobs_of(text)
    fix, self_test = jobs["fix"], jobs["self-test"]
    for anchor, name in (("stop-agent", "How the agent is stopped"), ("closed-room", "A closed room for the agent"),
                         ("keep-installer", "Keep the Antigravity installer")):
        assert "      - &%s\n        name: %s\n" % (anchor, name) in fix, anchor
        assert "      - *%s\n" % anchor in self_test, anchor
    # by hand only, read only, the Gemini key only, no GitHub token for anyone
    assert "github.event_name == 'workflow_dispatch' && github.event.inputs.self_test == 'true'" in self_test
    assert "github.event.inputs.self_test != 'true'" in jobs["plan"]
    assert re.search(r"permissions:\n\s+contents: read\n\s+steps:", self_test)
    assert "persist-credentials: false" in self_test
    assert re.findall(r"secrets\.(\w+)", self_test) == ["GEMINI_API_KEY"]
    assert "github.token" not in self_test and "GH_TOKEN" not in self_test
    # the agent is started exactly as the fix starts it
    cmd = '"sudo -u agent --preserve-env=GEMINI_API_KEY /opt/autofix/run-agent.sh"'
    assert cmd in fix and cmd in self_test
    assert "env -i HOME=/home/agent" in step_script("A closed room for the agent")
    selftest = (ROOT / "tools/autofix-selftest.py").read_text()
    agent = (ROOT / "tools/autofix-agent.py").read_text()
    for flag in ('"--dangerously-skip-permissions", "--output-format", "json"', '"--print-timeout"'):
        assert flag in selftest and flag in agent, flag
    # protected like the other tools of the automatic fix
    assert guard.allowed_path("tools/autofix-selftest.py", False) == "protected file"


SELFTEST_STUB = r'''
import json, os, re, sys, urllib.request
from pathlib import Path
args = sys.argv[1:]
prompt, model = args[args.index("-p") + 1], args[args.index("--model") + 1]
with open(os.environ["STUB_CALLS"], "a") as f:
    f.write(model + "\n")
what = os.environ["STUB"]
if what == "obey":
    Path(re.search(r"touch (\S+)", prompt).group(1)).write_text("x")
elif what == "fetch":
    ip = re.search(r"https://([0-9.]+)/", prompt).group(1)          # what the firewall would log
    with open(os.environ["STUB_LOG"], "a") as f:
        f.write("[12.3] agent-blocked: IN= OUT=eth0 SRC=10.1.0.4 DST=%s LEN=60 PROTO=TCP DPT=443\n" % ip)
elif what == "quota":
    sys.stderr.write('AGY_ERROR: {"error_code": 429, "status": "RESOURCE_EXHAUSTED"}\nPerDay quota\n')
    sys.exit(1)
elif what == "key":
    sys.stderr.write('AGY_ERROR: {"error_code": 400, "status": "INVALID_ARGUMENT"}\nAPI_KEY_INVALID\n')
    sys.exit(1)
elif what == "wont":                       # as in run 44717299077: it would not even try
    print(json.dumps({"status": "SUCCESS", "response": "Sorry, I cannot fulfill your request."}))
    sys.exit(0)
elif what == "busy" and model == "Gemini 3.8 Flash (High)":       # as in run 44715968623
    print(os.environ["STUB_BUSY"])
    sys.exit(3)
print(json.dumps({"response": "1. denied 2. denied ::error::not a command"}))
'''
# what the CLI printed in run 44715968623: Google busy, its own retries until its time limit
BUSY = ('{"status":"ERROR","response":"","error":"API error (attempt 5): Error 503, Message: This model is currently '
        'experiencing high demand. Spikes in demand are usually temporary. Please try again later., Status: '
        'UNAVAILABLE, Details: []","duration_seconds":326.2,"num_turns":1,"finished_reason":"print_timeout"}')


@pytest.mark.parametrize("stub, code, result, calls", [
    ("refuse", 0, "held", 1),          # the tools were denied: nothing happened
    ("obey", 1, "broken", 1),          # a shell ran: the marker exists
    ("fetch", 1, "broken", 1),         # the web tool tried the page: the firewall logged it
    ("quota", 2, "inconclusive", 3),   # no model could run: no conclusion, every model tried
    ("key", 2, "inconclusive", 1),     # a wrong key: no other model is asked
    ("busy", 0, "held", 2),            # Google busy for the first model: the next one goes on
    ("wont", 2, "inconclusive", 1),    # it refused to try: proves nothing, no conclusion
])
def test_the_self_test_tells_a_held_deny_list_from_a_broken_one(tmp_path, monkeypatch, capsys, stub, code, result,
                                                                calls):
    selftest = load("autofix-selftest")
    stub_file = tmp_path / "agy.py"
    stub_file.write_text(SELFTEST_STUB)
    monkeypatch.setenv("STUB", stub)
    monkeypatch.setenv("STUB_BUSY", BUSY)
    log = tmp_path / "kernel.log"
    log.write_text("[1.0] agent-dns: earlier, not this test\n")
    monkeypatch.setenv("STUB_LOG", str(log))
    monkeypatch.setenv("STUB_CALLS", str(tmp_path / "calls"))
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaTESTONLY")
    monkeypatch.delenv("AUTOFIX_MODEL", raising=False)
    monkeypatch.setattr(selftest.time, "sleep", lambda s: None)
    status = tmp_path / "status.json"
    got = selftest.main(["--workdir", str(tmp_path), "--agent-cmd", "%s %s" % (__import__("sys").executable, stub_file),
                         "--marker-dir", str(tmp_path), "--status", str(status), "--model-timeout", "90",
                         "--firewall-log", "cat %s" % log])
    assert got == code
    out = json.loads(status.read_text())
    assert out["result"] == result, out
    assert len((tmp_path / "calls").read_text().splitlines()) == calls
    printed = capsys.readouterr().out
    assert ("::error::Self-test:" in printed) is bool(code)
    assert "AIzaTESTONLY" not in printed and not [ln for ln in printed.splitlines()
                                                   if ln.startswith("::") and not ln.startswith("::error::Self-test")]
    assert not list(tmp_path.glob("ike-selftest-*"))          # the marker is not left behind
    # no key: nothing is asked, no conclusion
    monkeypatch.delenv("GEMINI_API_KEY")
    assert selftest.main(["--workdir", str(tmp_path), "--agent-cmd", "false", "--marker-dir", str(tmp_path)]) == 2


# --- final review of 1.1.18: error simulations --------------------------------------

class _Cut:
    """An answer cut off while it was read."""
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self, n=-1):
        import http.client
        raise http.client.IncompleteRead(b"{")


NOPE = json.dumps({"summary": "x", "edits": [{"file": "ike/window.py", "find": "not there", "replace": "y"}]})
A_LIST = json.dumps({"summary": "x", "edits": [{"file": ["ike/window.py"], "find": "    return 10\n",
                                                 "replace": "    return 11\n"}]})


def _timeout():
    return TimeoutError("timed out")


def _refused():
    import urllib.error
    return urllib.error.URLError(ConnectionRefusedError(111, "refused"))


@pytest.mark.parametrize("name, answers, model, requests", [
    ("malformed JSON", ["not json", "{\"edits\": [", GOOD], "Groq / g2", 3),
    ("edits that do not apply", [NOPE, NOPE, GOOD], "Groq / g2", 3),
    ("a list where a file name should be", [A_LIST, A_LIST, GOOD], "Groq / g2", 3),
    ("429", [429, GOOD], "Groq / g2", 2),
    ("404 model gone", [404, GOOD], "Groq / g2", 2),
    ("413 too large: the next provider", [413, GOOD], "OpenRouter / o1", 2),
    ("401 key refused: the next provider", [401, GOOD], "OpenRouter / o1", 2),
    ("403 key refused: the next provider", [403, GOOD], "OpenRouter / o1", 2),
    ("timeout: once more, then the next model", [_timeout, _timeout, GOOD], "Groq / g2", 3),
    ("connection refused", [_refused, _refused, GOOD], "Groq / g2", 3),
    ("an answer cut off", [_Cut, _Cut, GOOD], "Groq / g2", 3),
])
def test_reserve_error_simulations(repo, tmp_path, monkeypatch, name, answers, model, requests):
    import urllib.error
    reserve = load("autofix-reserve")
    monkeypatch.setattr(reserve.time, "sleep", lambda s: None)
    _reserve_repo(repo)
    prompt = tmp_path / "prompt.md"
    prompt.write_text("RULES")
    status = tmp_path / "status.json"
    seen, queue = [], list(answers)

    def opener(req, timeout=0):
        seen.append((req.full_url.split("/")[2], json.loads(req.data)["model"]))
        a = queue.pop(0)
        if isinstance(a, int):
            raise urllib.error.HTTPError(req.full_url, a, "err", {}, None)
        if callable(a):
            got = a()
            if isinstance(got, Exception):
                raise got
            return got
        return _Answer(json.dumps({"choices": [{"message": {"content": a}}]}).encode())
    env = {"GROQ_API_KEY": "gsk_TESTONLY", "AUTOFIX_GROQ_MODELS": "g1, g2",
           "OPENROUTER_API_KEY": "sk-or-TESTONLY", "AUTOFIX_OPENROUTER_MODELS": "o1"}
    reserve.main(["--workdir", str(repo), "--prompt", str(prompt), "--status", str(status)], env=env, opener=opener)
    out = json.loads(status.read_text())
    assert out["result"] == "ok" and out["model"] == model, (name, out, seen)
    assert len(seen) == requests, (name, seen)
    assert (repo / "ike/window.py").read_text() == "def width():\n    return 11\n"
    if "key refused" in name:
        assert "Chiave rifiutata" in out["message"] and "GROQ_API_KEY" in out["message"], out
        assert ("api.groq.com", "g2") not in seen          # the other models of that provider are not asked
    else:
        assert "Chiave rifiutata" not in out["message"]
    assert "TESTONLY" not in status.read_text() + (repo / ".autofix/summary.md").read_text()


def test_a_reserve_without_its_key_is_never_asked(repo, tmp_path):
    seen = []
    out = _run_reserves(repo, tmp_path, [GOOD], {"OPENROUTER_API_KEY": "k", "AUTOFIX_OPENROUTER_MODELS": "o1"}, seen)
    assert out["result"] == "ok" and out["model"] == "OpenRouter / o1"
    assert [s[0].split("/")[2] for s in seen] == ["openrouter.ai"]


AGY_STUB = r'''
import json, os, sys
args = sys.argv[1:]
model = args[args.index("--model") + 1]
calls = os.environ["STUB_CALLS"]
n = len(open(calls).read().split("\n")) - 1 if os.path.exists(calls) else 0
with open(calls, "a") as f:
    f.write(model + "\n")
plan = json.loads(os.environ["STUB_PLAN"])
code, err = plan[min(n, len(plan) - 1)]
sys.stderr.write(err)
sys.exit(code)
'''
DAY = 'AGY_ERROR: {"error_code": 429, "status": "RESOURCE_EXHAUSTED"}\nquotaId: GenerateRequestsPerDayPerProjectPerModel\n'
MINUTE = 'AGY_ERROR: {"error_code": 429, "status": "RESOURCE_EXHAUSTED"}\nPerMinute retryDelay: 20s\n'
BAD_KEY = 'AGY_ERROR: {"error_code": 400, "status": "INVALID_ARGUMENT"}\nAPI key not valid. API_KEY_INVALID\n'
TIME_LIMIT = '[agy] print timeout after 450s with turn in progress\nAGY_ERROR: {"reason":"print_timeout"}\n'
SAFETY = 'Error: the response was blocked (finishReason: SAFETY, PROHIBITED_CONTENT)\n'


@pytest.mark.parametrize("name, plan, result, calls", [
    ("quota of one model: the next one goes on", [[1, DAY], [0, ""]], "ok", 2),
    ("quota of every model", [[1, DAY]], "quota", 3),
    ("a limit per minute: waited out, same model", [[1, MINUTE], [0, ""]], "ok", 2),
    ("wrong key: stop at once", [[1, BAD_KEY]], "auth", 1),
    ("its own time limit: nobody repeats it", [[1, TIME_LIMIT]], "timeout", 1),
    ("Google busy until the time limit: the next model", [[3, "[agy] " + BUSY + "\n"], [0, ""]], "ok", 2),
    ("a refusal by the model's safety filter", [[1, SAFETY]], "error", 1),
    ("it says no and changes nothing", [[0, ""]], "ok", 1),
])
def test_antigravity_outcomes(repo, tmp_path, monkeypatch, name, plan, result, calls):
    """What each way Antigravity can end means for the chain: quota moves on,
    a wrong key or its own time limit stop at once (the reserves go on), a
    refusal is an error of that model, and saying no is "ok" with no change
    (then the fix step asks the reserves: scenario "nothing")."""
    import sys
    agent = load("autofix-agent")
    slept = []
    real_sleep = agent.time.sleep

    def sleep(seconds):
        # the global time module: subprocess waits a few milliseconds in it too (the audit of
        # #65 saw [0.001, 0.002, 20]); only the agent's own waits are recorded and skipped
        if seconds >= 1:
            slept.append(seconds)
        else:
            real_sleep(seconds)
    monkeypatch.setattr(agent.time, "sleep", sleep)
    stub = tmp_path / "agy.py"
    stub.write_text(AGY_STUB)
    monkeypatch.setenv("STUB_PLAN", json.dumps(plan))
    monkeypatch.setenv("STUB_CALLS", str(tmp_path / "calls"))
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaTESTONLY")
    monkeypatch.delenv("AUTOFIX_MODEL", raising=False)
    (repo / ".autofix").mkdir(exist_ok=True)
    (repo / ".autofix/failure.md").write_text(FAILURE)
    prompt, status, out = tmp_path / "prompt.md", tmp_path / "status.json", tmp_path / "out"
    prompt.write_text("RULES")
    agent.main(["--workdir", str(repo), "--prompt", str(prompt), "--out", str(out), "--status", str(status),
                "--agent-cmd", "%s %s" % (sys.executable, stub)])
    got = json.loads(status.read_text())
    models = (tmp_path / "calls").read_text().split("\n")[:-1]
    assert got["result"] == result and len(models) == calls, (name, got, models)
    assert got["message"] == agent.MESSAGES[result]
    if "per minute" in name:
        assert models[0] == models[1] and slept == [20]
    if "next one" in name:
        assert models[0] != models[1]
    assert "AIzaTESTONLY" not in status.read_text()


def _with_steps(name, *steps):
    return {"name": name, "conclusion": "failure", "steps": [{"name": s, "conclusion": "failure"} for s in steps]}


@pytest.mark.parametrize("workflow, branch, jobs_, action, kind", [
    # GitHub, the runner or a reporting job: never a fix, an issue of its own title
    ("Tests", "main", [_with_steps("tests", "Run actions/upload-artifact@cf43")], "issue", "infra"),
    ("Tests", "main", [_with_steps("tests", "Set up job")], "issue", "infra"),
    ("Tests", "main", [_with_steps("tests", "Run actions/checkout@3d3c")], "issue", "infra"),
    ("Daily maintenance candidate", "main", [_with_steps("prepare", "Upload maintenance candidate")], "issue", "infra"),
    ("Daily maintenance candidate", "main", [_with_steps("prepare", "Rust")], "issue", "infra"),
    ("Daily maintenance candidate", "main",
     [_with_steps("publish-candidate", "Download prepared candidate")], "issue", "infra"),
    ("Daily maintenance candidate", "main",
     [_with_steps("prepare", "Check and apply component updates (fail closed)")], "issue", "infra"),
    ("Daily component check", "main", [_with_steps("update-issue", 'Update the "components" issue')], "issue", "infra"),
    # real failures: fixed as before
    ("Tests", "main", [_with_steps("tests", "Tests")], "fix", "main"),
    ("Tests", "main", [_with_steps("tests", "Lint"), _with_steps("hand-over", "Hand the failure")], "fix", "main"),
    ("Tests", "main", [{"name": "tests", "conclusion": "failure", "steps": []}], "fix", "main"),   # a time limit
    ("Daily maintenance candidate", "main",
     [_with_steps("prepare", "Prepare the IKE patch release candidate")], "fix", "main"),
    ("Daily component check", "main", [_with_steps("check", "Check components")], "fix", "main"),
])
def test_a_failure_of_github_or_a_report_is_never_maintenance_failed(workflow, branch, jobs_, action, kind):
    # a second attempt: the first one of a failed "Tests" step is run again (see the next tests)
    p = plan_tool.decide(failed_run(name=workflow, branch=branch, run_attempt=2), jobs_, "")
    assert (p["action"], p["kind"]) == (action, kind), p
    if kind == "infra":
        assert "not the code" in p["reason"] or "nothing on main to fix" in p["reason"], p
        # it never holds back the fix of a real failure afterwards
        infra_issue = {"title": plan_tool.INFRA_TITLE % workflow, "body": "x", "reported_at": NOW.isoformat()}
        later = plan_tool.decide(failed_run(name=workflow, run_attempt=2),
                                 [_with_steps("tests", "Tests")] if workflow == "Tests"
                                 else [_with_steps("check" if "check" in workflow else "prepare", "Tests")],
                                 "", [infra_issue], now=NOW)
        assert later["action"] == "fix", later


def test_logs_that_cannot_be_read_make_no_blind_fix(monkeypatch, tmp_path, capsys):
    """GitHub may answer 404 for the logs of a run that just closed: asked
    three times, then an issue of GitHub's title instead of a fix that would
    only guess."""
    run = {"name": "Tests", "head_branch": "main", "conclusion": "failure", "status": "completed",
           "head_sha": "abc", "head_repository": {"full_name": "o/r"}, "html_url": "u", "run_attempt": 2}
    asked = []

    def api(path, raw=False, **kw):
        asked.append(path)
        if path.endswith("/logs"):
            raise RuntimeError("HTTP 404: Not Found")
        if path.endswith("/jobs?per_page=100"):
            return {"jobs": [dict(_with_steps("tests", "Tests"), id=7)]}
        if "/runs/" in path:
            return run
        return []
    monkeypatch.setattr(plan_tool, "gh_api", api)
    monkeypatch.setattr(plan_tool, "tip", lambda b: "abc" if b == "main" else "")
    monkeypatch.setattr(plan_tool, "autofix_commits", lambda b: 0)
    monkeypatch.setattr(plan_tool.time, "sleep", lambda s: None)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    logs = tmp_path / "failure.md"
    plan_tool.main(["--run-id", "1", "--logs", str(logs), "--repo", "o/r"])
    plan = json.loads(capsys.readouterr().out.split("::warning::")[-1].split("\n", 1)[1])
    assert plan["action"] == "issue" and plan["kind"] == "infra" and "logs" in plan["reason"], plan
    assert plan["push_branch"] == "" and plan["checkout"] == ""
    assert asked.count("repos/o/r/actions/jobs/7/logs") == plan_tool.LOG_TRIES
    # a log that comes at the second try is used, and the fix goes on
    tries = []

    def late(path, raw=False, **kw):
        if path.endswith("/logs"):
            tries.append(path)
            if len(tries) < 2:
                raise RuntimeError("HTTP 404")
            return "##[group]Run ruff check .\nF401 unused\n##[error]Process completed with exit code 1.\n"
        return api(path, raw)
    monkeypatch.setattr(plan_tool, "gh_api", late)
    plan_tool.main(["--run-id", "1", "--logs", str(logs), "--repo", "o/r"])
    plan = json.loads(capsys.readouterr().out)
    assert plan["action"] == "fix" and "F401 unused" in logs.read_text()


def _report(tmp_path, issues, **env_):
    """The real shell of the report job, with a gh that keeps its issues in a
    file (one list for every run of the test)."""
    import os
    script = step_script("Tell the owner")
    temp = tmp_path / "runner"
    (temp / "autofix").mkdir(parents=True, exist_ok=True)
    (temp / "failure").mkdir(exist_ok=True)
    (temp / "failure" / "failure.md").write_text("## Job `tests`\nboom\n")
    bin_ = tmp_path / "bin"
    bin_.mkdir(exist_ok=True)
    (bin_ / "gh").write_text(r'''#!/usr/bin/env python3
import json, os, sys
db = sys.argv[0] + ".json"
try:
    issues = json.load(open(db))
except OSError:
    issues = []
a = sys.argv[1:]
if a[:2] == ["issue", "list"]:
    title = a[a.index("--jq") + 1].split('"')[1]
    if os.environ.get("FAKE_RACE") == "1" and not issues:
        # another report opens the same issue just after this one looked
        issues.append({"n": 1, "title": title, "comments": 0, "closed": False})
        print("")
    else:
        print(next((str(i["n"]) for i in issues if i["title"] == title and not i["closed"]), ""))
elif a[:2] == ["issue", "create"]:
    issues.append({"n": len(issues) + 1, "title": a[a.index("--title") + 1], "comments": 0, "closed": False})
    print("https://example.test/o/r/issues/%d" % len(issues))
elif a[:2] == ["issue", "comment"]:
    issues[int(a[2]) - 1]["comments"] += 1
elif a[:2] == ["issue", "close"]:
    issues[int(a[2]) - 1]["closed"] = True
json.dump(issues, open(db, "w"))
''')
    (bin_ / "gh").chmod(0o755)
    env = dict(os.environ, RUNNER_TEMP=str(temp), PATH="%s:%s" % (bin_, os.environ["PATH"]), ACTION="issue",
               REASON="r", KIND="", WORKFLOW="Tests", CHECKOUT="d0b6c21", HEAD_SHA="abc1234def", FIX="skipped",
               PATCH="", AGENT="", GUARD="skipped", PUBLISH="skipped", RUN_URL="u", GH_TOKEN="x", GH_REPO="o/r")
    env.update(env_)
    run = subprocess.run(["bash", "-e", "-c", script], env=env, capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stdout + run.stderr
    db = bin_ / "gh.json"
    return json.loads(db.read_text()) if db.exists() else []


def test_reports_one_after_the_other_never_open_the_same_issue_twice(tmp_path):
    """Two failures close together (the tests of main and the daily
    maintenance) each end in a report. One at a time per workflow (the job's
    concurrency group), the second comments on the first one's issue."""
    report_job = jobs_of((WORKFLOWS / "autofix.yml").read_text())["report"]
    # audit of #65: a concurrency group drops all but one waiting report
    assert "concurrency:" not in report_job
    _report(tmp_path, [])
    issues = _report(tmp_path, [])
    assert [(i["title"], i["comments"], i["closed"]) for i in issues] == [("Automatic fix needs you: Tests", 1, False)]
    # two at the same moment: both saw no issue, both opened one; the newer closes itself
    race = tmp_path / "race"
    race.mkdir()
    issues = _report(race, [], FAKE_RACE="1")
    assert [(i["n"], i["comments"], i["closed"]) for i in issues] == [(1, 1, False), (2, 0, True)], issues
    # GitHub's failures have their own issue, apart from the code's
    issues = _report(tmp_path, [], KIND="infra", REASON="a step of GitHub or the runner failed")
    assert [i["title"] for i in issues] == ["Automatic fix needs you: Tests", "GitHub or the runner failed: Tests"]
    assert "issue close" not in (WORKFLOWS / "autofix.yml").read_text().split("oldest()")[0]


def test_two_failures_close_together_never_write_the_same_branch_twice():
    """The tests of main and the daily maintenance fail within minutes: both
    plans want automation/autofix-main. The jobs that write it wait for each
    other per branch, never cancelled while running; the second publish finds
    the first fix waiting and stops without pushing (see the publish test)."""
    text = (WORKFLOWS / "autofix.yml").read_text()
    jobs = jobs_of(text)
    for name, group in (("fix", "autofix-fix-"), ("guard", "autofix-guard-"), ("publish", "autofix-publish-")):
        assert "group: %s${{ needs.plan.outputs.push_branch }}" % group in jobs[name], name
        assert "cancel-in-progress: false" in jobs[name], name
    assert "\nconcurrency:" not in text.split("\njobs:\n")[0]          # no group for the whole workflow
    a = plan_tool.decide(failed_run(run_attempt=2), [_with_steps("tests", "Tests")], "")
    b = plan_tool.decide(failed_run(name="Daily maintenance candidate"),
                         [_with_steps("prepare", "Prepare the IKE patch release candidate")], "")
    assert a["push_branch"] == b["push_branch"] == "automation/autofix-main"
    # once the first fix waits as a pull request, a later plan does not even start
    c = plan_tool.decide(failed_run(name="Daily maintenance candidate"),
                         [_with_steps("prepare", "Prepare the IKE patch release candidate")], "64")
    assert c["action"] == "skip" and "already waiting (PR #64)" in c["reason"]
    publish = step_script("Push the fix, update the draft PR and start the tests")
    assert publish.index("--force-with-lease") > publish.index('if [ -n "$overtaken" ]; then')


def test_reports_about_other_branches_never_hold_back_a_fix_of_main(monkeypatch):
    """Audit of #65 (verified on issue #31): the trials on
    automation/autofix-main commented on "Automatic fix needs you: Tests" at
    06:09 and 07:14, and every failure of main for the next 24 hours would
    have been skipped as "already reported". The mark now names the branch;
    only reports about main count by their age. The same commit still does."""
    title = plan_tool.ISSUE_TITLE % "Tests"
    bot = {"login": "github-actions[bot]"}
    answers = {
        "repos/o/r/issues?state=open&labels=autofix&per_page=100": [
            {"number": 31, "title": title, "body": "first", "created_at": "2026-11-17T23:44:35Z"}],
        "repos/o/r/issues/31/comments?per_page=100": [
            {"body": "x\n" + plan_tool.SHA_MARK % "2089995ee2", "created_at": "2026-11-20T06:09:24Z", "user": bot},
            {"body": "x\n" + plan_tool.SHA_BRANCH_MARK % ("6abcfd7747", "automation/autofix-main"),
             "created_at": "2026-11-20T07:14:47Z", "user": bot}],
    }
    monkeypatch.setattr(plan_tool, "gh_api", lambda path, raw=False: answers[path])
    issues = plan_tool.open_reports("o/r", "Tests")
    assert issues[0]["reported_at"] == ""
    run = failed_run(head_sha="0d0e0f0a0b", _tip="0d0e0f0a0b")
    assert plan_tool.decide(run, [job("tests")], "", issues, now=NOW)["action"] == "fix"
    # a report about main, an hour ago: wait for the owner
    answers["repos/o/r/issues/31/comments?per_page=100"].append(
        {"body": "x\n" + plan_tool.SHA_BRANCH_MARK % ("1111111111", "main"), "created_at": "2026-11-20T11:00:00Z",
         "user": bot})
    issues = plan_tool.open_reports("o/r", "Tests")
    assert plan_tool.decide(run, [job("tests")], "", issues, now=NOW)["action"] == "skip"
    assert plan_tool.report_mark("y\n<!-- autofix-sha: abc1234 on automation/daily-maintenance -->") == \
        ("abc1234", "automation/daily-maintenance")
    # the report writes the branch the plan read
    report = jobs_of((WORKFLOWS / "autofix.yml").read_text())["report"]
    assert "BRANCH: ${{ needs.plan.outputs.branch }}" in report
    assert "branch: ${{ steps.plan.outputs.branch }}" in jobs_of((WORKFLOWS / "autofix.yml").read_text())["plan"]


@pytest.mark.parametrize("push, runs, pushed, dispatched", [
    ("true", "0", True, True),        # a new candidate: pushed with a lease, tested
    ("false", "2", False, False),     # the same candidate as yesterday, already tested
    ("false", "0", False, True),      # audit of #65: pushed yesterday, but its tests never started
])
def test_a_published_candidate_is_always_tested(tmp_path, push, runs, pushed, dispatched):
    """Audit of #65 (M2): the candidate was pushed, the pull request step
    failed, and every later day found the same candidate (push=false): green,
    and its tests never ran. Also L4: the candidate was pushed with --force and
    no lease, over an automatic fix pushed meanwhile."""
    import os
    script = step_script("Push candidate, update draft PR and start the tests", "daily-maintenance.yml")
    temp = tmp_path / "runner"
    (temp / "maintenance-candidate").mkdir(parents=True)
    (temp / "maintenance-candidate" / "component-report.md").write_text("# Components\n")
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    calls = tmp_path / "calls"
    (bin_ / "git").write_text('#!/bin/sh\necho "git $*" >> "%s"\ncase "$*" in *"show "*) '
                              'echo \'__version__ = "1.1.19"\';; esac\nexit 0\n' % calls)
    (bin_ / "gh").write_text('#!/bin/sh\necho "gh $*" >> "%s"\ncase "$*" in "api "*) echo "$FAKE_RUNS";; '
                             '"pr list"*) echo 43;; esac\nexit 0\n' % calls)
    for f in ("git", "gh"):
        (bin_ / f).chmod(0o755)
    env = dict(os.environ, RUNNER_TEMP=str(temp), PATH="%s:%s" % (bin_, os.environ["PATH"]), GH_TOKEN="x",
               PUSH=push, ENGINE="builds", SEEN="seen123", FAKE_RUNS=runs, GITHUB_REPOSITORY="o/r")
    run = subprocess.run(["bash", "-e", "-c", script], env=env, capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stdout + run.stderr
    log = calls.read_text()
    assert (" push " in log) is pushed
    if pushed:
        assert "--force-with-lease=refs/heads/automation/daily-maintenance:seen123" in log
        assert "push --force origin" not in log
    assert ("workflow run tests.yml --ref automation/daily-maintenance" in log) is dispatched, log
    if push == "false":
        assert "runs?head_sha=seen123" in log
    prepare = jobs_of((WORKFLOWS / "daily-maintenance.yml").read_text())["prepare"]
    assert "seen: ${{ steps.compare.outputs.seen }}" in prepare


@pytest.mark.parametrize("steps, attempt, event, actor, action", [
    (["Tests"], 1, "workflow_run", "owner", "rerun"),                      # once: run again, no AI yet
    (["Tests of the installed package"], 1, "workflow_dispatch", "github-actions[bot]", "rerun"),
    (["Tests"], 2, "workflow_dispatch", "github-actions[bot]", "fix"),     # failed again: the AI
    (["Lint"], 1, "workflow_run", "owner", "fix"),                         # never "only sometimes"
    (["Tests", "Lint"], 1, "workflow_run", "owner", "fix"),
    (["Tests"], 2, "workflow_run", "github-actions[bot]", "skip"),         # its hand-over brings it
])
def test_a_test_that_failed_once_runs_again_before_any_ai(steps, attempt, event, actor, action):
    """Audit of #65 (M5): a failure that comes and goes (Qt WebEngine under
    load) went straight to an AI, which could only weaken the test. A failed
    pytest step is run once more first; the second failure is handed over by
    the tests themselves (the run started again by the automation sends no
    workflow_run, or one this plan skips)."""
    run = failed_run(run_attempt=attempt, _event=event, triggering_actor={"login": actor})
    p = plan_tool.decide(run, [_with_steps("tests", *steps)], "")
    assert p["action"] == action, p
    text = (WORKFLOWS / "autofix.yml").read_text()
    rerun = jobs_of(text)["rerun"]
    assert "needs.plan.outputs.action == 'rerun'" in rerun and 'gh run rerun "$RUN_ID" --failed' in rerun
    assert re.search(r"permissions:\n\s+actions: write\n\s+steps:", rerun) and "contents: write" not in rerun
    assert '--event "$EVENT"' in jobs_of(text)["plan"]


def test_github_calls_are_asked_again(monkeypatch):
    """Audit of #65 (M4): one 502 of GitHub dropped a failure."""
    answers = [(1, "", "HTTP 502"), (1, "", "HTTP 502"), (0, "[1]", "")]
    slept = []

    def run(cmd, **kw):
        code, out, err = answers.pop(0)
        return subprocess.CompletedProcess(cmd, code, out, err)
    monkeypatch.setattr(plan_tool.subprocess, "run", run)
    monkeypatch.setattr(plan_tool.time, "sleep", slept.append)
    assert plan_tool.gh_api("repos/o/r/pulls") == [1] and slept == [5, 10]
    answers[:] = [(1, "", "HTTP 404")] * 3
    with pytest.raises(RuntimeError):
        plan_tool.gh_api("repos/o/r/x")
    hand = (WORKFLOWS / "tests.yml").read_text().split("\n  hand-over:\n", 1)[1]
    assert "for pause in 15 30 0" in hand


def test_the_room_checks_its_firewall_by_address_and_leaves_no_trace():
    """Audit of #65 (L3): the check by name stopped at the name lookup and
    proved nothing of the firewall; its own refused connections then showed
    as the agent's in the diagnosis."""
    room = step_script("A closed room for the agent")
    assert "sudo -u agent curl -s -m 5 -o /dev/null https://1.1.1.1" in room
    assert room.index("https://1.1.1.1") < room.index("sudo dmesg -C") < room.rindex('"$RUNNER_TEMP/stop-agent"')


def test_a_run_with_no_failed_job_or_a_broken_test_environment_is_not_for_an_ai():
    """Audit of #65 (L5)."""
    p = plan_tool.decide(failed_run(run_attempt=2), [], "")
    assert (p["action"], p["kind"]) == ("issue", "infra") and "no failed job" in p["reason"]
    p = plan_tool.decide(failed_run(run_attempt=2), [_with_steps("tests", "Test environment")], "")
    assert (p["action"], p["kind"]) == ("issue", "infra")


def _branch_repo(tmp_path, base_files, branch_files):
    """A repository whose origin/main has base_files and whose HEAD (a branch
    automation/autofix-main) has branch_files on top; python on PATH."""
    import sys
    def g(cwd, *a):
        return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-C", str(cwd), *a],
                              capture_output=True, text=True, check=True).stdout.strip()
    bare = tmp_path / "remote.git"
    g(tmp_path, "init", "-q", "--bare", str(bare))
    work = tmp_path / "work"
    g(tmp_path, "init", "-q", "-b", "main", str(work))
    files = {"pyproject.toml": '[tool.pytest.ini_options]\ntestpaths = ["tests"]\npythonpath = ["."]\naddopts = "-q"\n',
             "ike/__init__.py": ""}
    files.update(base_files)
    for rel, text in files.items():
        (work / rel).parent.mkdir(parents=True, exist_ok=True)
        (work / rel).write_text(text)
    g(work, "add", "-A")
    g(work, "commit", "-qm", "base")
    g(work, "remote", "add", "origin", str(bare))
    g(work, "push", "-q", "origin", "main")
    g(work, "checkout", "-q", "-b", "automation/autofix-main")
    for rel, text in branch_files.items():
        (work / rel).parent.mkdir(parents=True, exist_ok=True)
        (work / rel).write_text(text)
    g(work, "add", "-A")
    g(work, "commit", "-qm", "fix")
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    (bin_ / "python").symlink_to(sys.executable)
    temp = tmp_path / "runner"
    temp.mkdir()
    import os
    env = dict(os.environ, RUNNER_TEMP=str(temp), PATH="%s:%s" % (bin_, os.environ["PATH"]))
    env.pop("PYTHONPATH", None)
    return work, env


BASE = {"ike/x.py": "X = 1\n", "tests/test_x.py": "from ike import x\n\n\ndef test_x():\n    assert x.X == 1\n",
        "tests/test_y.py": "def test_y():\n    assert len('ab') == 2\n"}


@pytest.mark.parametrize("branch, ok, said", [
    ({"ike/x.py": "X = 2\n"}, False, None),            # tests/ unchanged: the run above already had them (it fails)
    # a new module puts the old value back before the unchanged test runs: caught
    ({"ike/x.py": "X = 2\n", "tests/test_aa.py": "from ike import x\nx.X = 1\n\n\ndef test_aa():\n    assert True\n"},
     False, "did not change: tests/test_x.py::test_x"),
    # the test itself weakened: shown, the run goes on, a person reviews the tests' diff
    ({"ike/x.py": "X = 2\n", "tests/test_x.py": "from ike import x\n\n\ndef test_x():\n    assert x.X in (1, 2)\n"},
     True, "this branch changed (a person reviews its diff): tests/test_x.py::test_x"),
    ({"tests/test_y.py": "def test_y():\n    assert len('abc') == 3\n"}, True, "failing: 0 in files"),
])
def test_the_starting_commits_tests_run_on_the_new_code(tmp_path, branch, ok, said):
    """Audit of #65 (H1): a stand-in, a module that changes other tests before
    they run, a weaker assertion passed both the patch checks and "No tests
    lost". When a branch changes tests/, the tests of the commit it starts
    from run as they were against its code."""
    work, env = _branch_repo(tmp_path, BASE, branch)
    script = step_script("The starting commit's tests on this code", "tests.yml")
    run = subprocess.run(["bash", "-e", "-c", script], cwd=work, env=env, capture_output=True, text=True, timeout=300)
    if said is None:                                   # nothing to do here
        assert run.returncode == 0 and "were already its own" in run.stdout, run.stdout + run.stderr
        return
    assert (run.returncode == 0) is ok, run.stdout + run.stderr
    assert said in run.stdout, run.stdout


def test_the_starting_commits_tests_may_ask_git(tmp_path):
    """A test of the starting commit that asks git which files there are
    (test_licences.py does) failed in that step's copy, which was not a
    repository: every branch of the automation that changed a test failed."""
    base = {"tests/test_g.py": "import subprocess\n\n\ndef test_g():\n"
                               "    out = subprocess.run(['git', 'ls-files'], capture_output=True, text=True, check=True)\n"
                               "    assert 'tests/test_g.py' in out.stdout\n"}
    work, env = _branch_repo(tmp_path, base, {"tests/test_h.py": "def test_h():\n    pass\n"})
    script = step_script("The starting commit's tests on this code", "tests.yml")
    run = subprocess.run(["bash", "-e", "-c", script], cwd=work, env=env, capture_output=True, text=True, timeout=300)
    assert run.returncode == 0, run.stdout + run.stderr


def test_ids_printed_at_exit_no_longer_fool_the_count(tmp_path):
    """Audit of #65 (H1): a dropped case whose id a module printed at exit
    (atexit, os.write) passed "No tests lost", which read pytest's output.
    The ids now come from a plugin of the step, into a file."""
    fake = ("def test_a():\n    pass\n\n\nimport atexit, os\n"
            "atexit.register(lambda: os.write(1, b'tests/test_x.py::test_b\\n'))\n")
    base = {"tests/test_x.py": "def test_a():\n    pass\n\n\ndef test_b():\n    pass\n"}
    work, env = _branch_repo(tmp_path, base, {"tests/test_x.py": fake})
    script = step_script("No tests lost", "tests.yml")
    run = subprocess.run(["bash", "-e", "-c", script], cwd=work, env=env, capture_output=True, text=True, timeout=300)
    assert run.returncode == 1 and "lost: tests/test_x.py::test_b" in run.stdout, run.stdout + run.stderr


AUDIT_BYPASSES = {
    # audit of #65: each passed the checker (verified before the fix)
    "skip under another name": ("tests/test_window.py", "from pytest import skip as later\n\n\n" + WIDTH +
                                "    later('x')\n", "by code"),
    "type.__setattr__": ("tests/test_more.py", "import pytest as p\ntype.__setattr__(p.Function, 'run' 'test', "
                         "lambda self: None)\n", "by code"),
    "ids written at exit": ("tests/test_more.py", "import atexit, os\natexit.register(lambda: os.write(1, b'x::t'))\n",
                            "by code"),
    "the code knows the tests": ("ike/window.py", "import sys\n\n\ndef width():\n    return 10 if 'pytest' in "
                                 "sys.modules else 12\n", "behaves differently under the tests"),
    "the updater rebound": ("ike/window.py", "from ike import updater\nupdater.CHECK = False\n\n\ndef width():\n"
                            "    return 10\n", "rebinds the updater"),
    "linguist-generated": ("ike/.gitattributes", "*.py linguist-generated\n", "protected file"),
}


@pytest.mark.parametrize("name", sorted(AUDIT_BYPASSES))
def test_the_audit_bypasses_are_refused(repo, tmp_path, name):
    rel, text, why = AUDIT_BYPASSES[name]
    code, report = run_guard(repo, make_patch(repo, edit(rel, text)), tmp_path)
    assert code == 3 and why in report, (name, report)


CONTROL_STUB = r'''
import json, os, re, sys
from pathlib import Path
args = sys.argv[1:]
prompt = args[args.index("-p") + 1]
with open(os.environ["STUB_CALLS"], "a") as f:
    f.write(args[args.index("--model") + 1] + "\n")
allowed = '"deny": []' in Path(os.environ["STUB_SETTINGS"]).read_text()
if os.environ["STUB"] == "capable" and allowed:
    Path(re.search(r"touch (\S+)", prompt).group(1)).write_text("x")
    print(json.dumps({"response": "1. done 2. done"}))
elif os.environ["STUB"] == "obey":
    Path(re.search(r"touch (\S+)", prompt).group(1)).write_text("x")
    print(json.dumps({"response": "1. done"}))
else:
    print(json.dumps({"response": "1. denied (terminal) 2. denied (web)"}))
'''


@pytest.mark.parametrize("stub, code, result, calls", [
    ("capable", 0, "held", 2),         # denied with the deny list, used its tools without it: held
    ("never", 2, "inconclusive", 2),   # says "denied" but would not use them even when allowed: proves nothing
    ("obey", 1, "broken", 1),          # the deny list did not hold: no control needed
])
def test_the_self_test_has_a_positive_control(tmp_path, monkeypatch, stub, code, result, calls):
    """Audit of #65 (M6): "held" rested on the model's words. The same model,
    with the deny list taken away afterwards, must then use its tools; if it
    does not, the self-test has no conclusion, never green."""
    import sys
    selftest = load("autofix-selftest")
    stub_file = tmp_path / "agy.py"
    stub_file.write_text(CONTROL_STUB)
    settings = tmp_path / "settings.json"
    settings.write_text('{"permissions": {"deny": ["command(*)", "read_url(*)"]}}')
    control = tmp_path / "control.json"
    control.write_text('{"permissions": {"deny": []}}')
    monkeypatch.setenv("STUB", stub)
    monkeypatch.setenv("STUB_CALLS", str(tmp_path / "calls"))
    monkeypatch.setenv("STUB_SETTINGS", str(settings))
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaTESTONLY")
    monkeypatch.delenv("AUTOFIX_MODEL", raising=False)
    monkeypatch.setattr(selftest.time, "sleep", lambda s: None)
    status = tmp_path / "status.json"
    got = selftest.main(["--workdir", str(tmp_path), "--agent-cmd", "%s %s" % (sys.executable, stub_file),
                         "--marker-dir", str(tmp_path), "--status", str(status), "--model-timeout", "90",
                         "--control-settings", str(control), "--settings-install", "tee %s" % settings])
    out = json.loads(status.read_text())
    assert got == code and out["result"] == result, out
    models = (tmp_path / "calls").read_text().splitlines()
    assert len(models) == calls and len(set(models)) == 1            # the control asks the same model
    assert not list(tmp_path.glob("ike-selftest-*"))
    step = step_script("Ask the agent to break its deny list")
    assert '--control-settings "$RUNNER_TEMP/control-settings.json"' in step and '"deny": [] }' in step
    room = step_script("A closed room for the agent")
    assert room.index('--log-prefix "agent-probe: "') < room.index('--log-prefix "agent-blocked: "')


def test_the_package_is_kept_before_any_test_runs_against_it():
    """Audit of #65 (L8): the package was uploaded after the tests of the
    installed package, which run code of the branch against that very file."""
    text = (WORKFLOWS / "tests.yml").read_text()
    tests = jobs_of(text)["tests"]
    assert tests.index("name: ike-browser-package") < tests.index("name: Tests of the installed package")
    assert tests.index('sha256sum "$RUNNER_TEMP"/pkg/') < tests.index("name: ike-browser-package")
