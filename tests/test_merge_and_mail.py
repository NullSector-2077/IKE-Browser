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
CODE = [{"filename": "ike/shields.py", "status": "modified", "patch": "@@ -1 +1 @@\n-a\n+b"},
        {"filename": "CHANGELOG.md", "status": "modified", "patch": "+- Automatic fix"}]
COMMITS = [{"commit": {"message": "autofix: attempt 1 after a failure of \"Tests\""}}]


def decide(p=None, commits=COMMITS, files=CODE, checks=OK_CHECKS):
    return merge.decide(REPO, p or pr(), commits, files, checks, set(guard.FORBIDDEN_FILES),
                        tuple(guard.FORBIDDEN_PREFIXES))


def test_a_green_fix_of_code_is_merged():
    assert decide() == (True, "")
    version = [{"filename": "ike/__init__.py", "status": "modified",
                "patch": '@@ -5 +5 @@\n-__version__ = "1.1.19"\n+__version__ = "1.1.20"'},
               {"filename": "PKGBUILD", "status": "modified", "patch": "-pkgver=1.1.19\n+pkgver=1.1.20"},
               {"filename": "README.md", "status": "modified",
                "patch": "-**Version 1.1.19** - see\n+**Version 1.1.20** - see"}]
    assert decide(files=CODE + version) == (True, "")                       # the automation's own version raise
    gpt = OK_CHECKS + [{"name": "guard", "status": "completed", "conclusion": "success"}]
    assert decide(pr("chatgpt/fix-20261121-0505"), checks=gpt) == (True, "")


def test_everything_else_waits_for_a_person():
    cases = {
        "trial": decide(commits=COMMITS + [{"commit": {"message": "Autofix trial 5 (deliberate errors)"}}]),
        "tests": decide(files=CODE + [{"filename": "tests/test_x.py", "status": "modified", "patch": "+x"}]),
        "updater": decide(files=[{"filename": "ike/updater.py", "status": "modified", "patch": "+x"}]),
        "workflow": decide(files=[{"filename": ".github/workflows/tests.yml", "status": "modified", "patch": "+x"}]),
        "adblock": decide(files=[{"filename": "ike/blocker.py", "status": "modified", "patch": "+x"}]),
        "engine": decide(files=[{"filename": "ike-adblock/Cargo.toml", "status": "modified", "patch": "+x"}]),
        "youtube": decide(files=[{"filename": "ike/resources/videoads.js", "status": "modified", "patch": "+x"}]),
        "version+": decide(files=[{"filename": "ike/__init__.py", "status": "modified",
                                   "patch": '+__version__ = "1.1.20"\n+__min_system__ = "1.1.20"'}]),
        "removed": decide(files=[{"filename": "ike/x.py", "status": "removed"}]),
        "running": decide(checks=OK_CHECKS + [{"name": "Arch Linux", "status": "in_progress"}]),
        "failed": decide(checks=OK_CHECKS + [{"name": "sandbox", "status": "completed", "conclusion": "failure"}]),
        "no tests": decide(checks=OK_CHECKS[1:]),
        "gpt unguarded": decide(pr("chatgpt/fix-1")),
        "person": decide(pr("fix/1.1.20-something")),
        "maintenance": decide(pr("automation/daily-maintenance")),
        "fork": decide(pr(repo="someone/IKE-Browser")),
    }
    wrong = {k: v for k, v in cases.items() if v[0]}
    assert not wrong, wrong


def test_the_workflows_are_wired():
    am = (WORKFLOWS / "automerge.yml").read_text()
    assert 'workflows: ["Tests", "Security", "ChatGPT fix guard", "Arch Linux"]' in am
    assert "ref: main" in am and "tools/automerge.py" in am and "persist-credentials: false" in am
    assert "if: github.event.workflow_run.conclusion == 'success'" in am
    text = (ROOT / "tools" / "automerge.py").read_text()
    assert '"sha=" + a.sha' in text and '"workflow", "run", "tests.yml"' in text


def test_no_fix_can_change_the_rules_it_is_judged_by():
    """An automatic or ChatGPT fix touching tools/automerge.py could change
    the merge rules for the next ones: both tools are protected files."""
    assert "tools/automerge.py" in guard.FORBIDDEN_FILES
    assert decide(files=[{"filename": "tools/automerge.py", "status": "modified", "patch": "+x"}])[0] is False
