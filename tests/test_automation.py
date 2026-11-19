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
        if path.name != "chatgpt-guard.yml":
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
    # "cannot be fixed in the code": stop, no other model asked
    seen = []
    no = json.dumps({"summary": "Un server era giù.", "fixable": False, "edits": []})
    reserve.main(["--workdir", str(repo), "--prompt", str(prompt), "--status", str(status)],
                 env={"GROQ_API_KEY": "k", "OPENROUTER_API_KEY": "k2"}, opener=_opener([no], seen))
    assert json.loads(status.read_text())["result"] == "none" and len(seen) == 1


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
    assert runs == ["python3 -I tools/check-autofix-patch.py --repo . --patch \"$RUNNER_TEMP/pr.patch\" \\"], runs
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


def step_script(name):
    """The shell of one step of autofix.yml (its "run: |" block), without a YAML library."""
    import textwrap
    lines = (WORKFLOWS / "autofix.yml").read_text().splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.strip() == "- name: %s" % name)
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


@pytest.mark.parametrize("scenario, reserve_asked, refused_given, result, patch", [
    ("nothing", True, False, "ok", "false"),       # no fix: the first reserve
    ("big", True, True, "rejected", "false"),      # off target: undone, the reserves get the reason
    ("unsafe", False, False, "refused", "false"),  # a protected file: undone, nobody else asked
    ("good", False, False, "ok", "true"),          # accepted at once: the reserves stay quiet
])
def test_the_fix_step_of_the_workflow(repo, tmp_path, scenario, reserve_asked, refused_given, result, patch):
    """The real shell of the step "Agent, reserves, then the patch", with a stub
    agent and a stub reserve: what reaches the reserves, and what is kept."""
    import os
    import subprocess

    script = step_script("Agent, reserves, then the patch")
    script = script.replace("repo=/srv/autofix/repo", "repo=%s" % repo)
    temp = tmp_path / "runner"
    (temp / "autofix").mkdir(parents=True)
    (temp / "prompt.md").write_text("RULES")
    (temp / "autofix-agent.py").write_text(AGENT_STUB)
    (temp / "autofix-reserve.py").write_text(RESERVE_STUB)
    (temp / "check-autofix-patch.py").write_text((ROOT / "tools/check-autofix-patch.py").read_text())
    (temp / "autofix" / "related.txt").write_text("ike/window.py\n")
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    (bin_ / "sudo").write_text("#!/bin/sh\nexit 0\n")
    (bin_ / "sudo").chmod(0o755)
    out_file = tmp_path / "github_output"
    env = dict(os.environ, RUNNER_TEMP=str(temp), GITHUB_OUTPUT=str(out_file), SCENARIO=scenario,
               GEMINI_API_KEY="AIzaTESTONLY", GROQ_API_KEY="gsk_TESTONLY", OPENROUTER_API_KEY="",
               ALLOW_ADBLOCK="false", PATH="%s:%s" % (bin_, os.environ["PATH"]))
    run = subprocess.run(["bash", "-e", "-c", script], env=env, capture_output=True, text=True, timeout=120)
    assert run.returncode == 0, run.stdout + run.stderr
    outputs = dict(line.split("=", 1) for line in out_file.read_text().splitlines() if "=" in line)
    calls = temp / "autofix" / "reserve-calls.txt"
    asked = calls.read_text() if calls.exists() else ""
    assert bool(asked) is reserve_asked, (scenario, asked)
    assert ("--refused" in asked) is refused_given, (scenario, asked)
    if reserve_asked:
        assert "--checker" in asked and "--related" in asked and "--allow-adblock" not in asked
    assert outputs["result"] == result, (scenario, outputs, run.stdout)
    assert outputs["patch"] == patch, (scenario, outputs)
    if scenario in ("big", "unsafe"):           # nothing of a refused fix is kept
        assert git(repo, "status", "--porcelain") == "", scenario
        summary = (temp / "autofix" / "summary.md").read_text()
        assert "respinta dai controlli" in summary, summary


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
    # an explicit "fixable": false still ends it
    no = json.dumps({"summary": "Un server era giù.", "fixable": False, "edits": []})
    seen = []
    reserve.main(["--workdir", str(repo), "--prompt", str(prompt), "--status", str(status)],
                 env={"GROQ_API_KEY": "k", "OPENROUTER_API_KEY": "k2"}, opener=_opener([no], seen))
    assert json.loads(status.read_text())["result"] == "none" and len(seen) == 1


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
    assert "automation/autofix-main" in hand and "automation/daily-maintenance" in hand and "'main'" not in hand
    assert "permissions:\n      actions: write\n" in hand and "contents: write" not in hand
    assert 'gh workflow run autofix.yml --ref main -f run_id="$RUN_ID"' in hand
    assert "permissions:\n  contents: read\n" in text.split("jobs:")[0]
    # the plan waits for the run to close before reading its outcome
    states = [{"status": "in_progress"}, {"status": "in_progress"}, {"status": "completed", "conclusion": "failure"}]
    monkeypatch.setattr(plan_tool, "gh_api", lambda path, raw=False: states.pop(0))
    slept = []
    run = plan_tool.completed_run("o/r", "1", sleep=slept.append)
    assert run["conclusion"] == "failure" and len(slept) == 2
