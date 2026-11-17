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
    patch = make_patch(repo, edit("tests/test_window.py", "def test_width():\n    assert 1\n    assert 3\n"))
    assert run_guard(repo, patch, tmp_path)[0] == 0


@pytest.mark.parametrize("rel", [".github/workflows/tests.yml", "PKGBUILD", "data/update.json",
                                 "ike/__init__.py", "ike/updater.py", "tests/conftest.py",
                                 "README.md", "launcher/x.c", "ike_boot.py", "pyproject.toml"])
def test_protected_files_are_refused(repo, tmp_path, rel):
    patch = make_patch(repo, edit(rel, "# changed\n", "a"))
    code, report = run_guard(repo, patch, tmp_path)
    assert code == 1 and rel in report
    assert (repo / "ike/window.py").read_text() == "def width():\n    return 10\n"   # nothing applied
    assert git(repo, "status", "--porcelain") == ""


def test_the_ad_blocker_only_with_an_engine_update(repo, tmp_path):
    for rel in ("ike-adblock/src/lib.rs", "ike/blocker.py"):
        patch = make_patch(repo, edit(rel, "// fixed\n", "a"))
        code, report = run_guard(repo, patch, tmp_path)
        assert code == 1 and "ad blocker" in report
        code, _ = run_guard(repo, patch, tmp_path, "--allow-adblock")
        assert code == 0
        git(repo, "reset", "-q", "--hard")


@pytest.mark.parametrize("line", ["    pytest.skip('flaky')\n", "@pytest.mark.xfail\n",
                                  "    pytest.importorskip('x')\n"])
def test_skips_and_xfails_are_refused(repo, tmp_path, line):
    patch = make_patch(repo, edit("tests/test_window.py", line, "a"))
    code, report = run_guard(repo, patch, tmp_path)
    assert code == 1 and "skip or xfail" in report


def test_removed_assertions_and_tests_are_refused(repo, tmp_path):
    patch = make_patch(repo, edit("tests/test_window.py", "def test_width():\n    assert 1\n"))
    code, report = run_guard(repo, patch, tmp_path)
    assert code == 1 and "assertion(s) removed" in report
    patch = make_patch(repo, lambda r: (r / "tests/test_window.py").unlink())
    code, report = run_guard(repo, patch, tmp_path)
    assert code == 1 and "test file removed" in report


def test_keys_binaries_links_and_size_are_refused(repo, tmp_path):
    key = "AIza" + "B" * 35
    patch = make_patch(repo, edit("ike/window.py", "KEY = '%s'\n" % key, "a"))
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
    assert code == 1
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


def test_plan_one_fix_of_main_at_a_time_and_no_repeats():
    assert plan_tool.decide(failed_run(), [job("tests")], "31")["action"] == "skip"
    title = plan_tool.ISSUE_TITLE % "Daily component check"
    p = plan_tool.decide(failed_run(name="Daily component check"), [job("check")], "", [title])
    assert p["action"] == "skip" and "already reported" in p["reason"]


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
    assert set(jobs) == {"plan", "fix", "guard", "publish", "report"}
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
    assert "--dangerously-skip-permissions" in jobs["fix"] and '"modelProvider": "gemini"' in jobs["fix"]


def test_no_workflow_publishes_merges_or_runs_forks():
    for path in WORKFLOWS.glob("*.yml"):
        text = path.read_text()
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
