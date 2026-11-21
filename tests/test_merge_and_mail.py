"""1.1.19, the owner's decisions: a green fix of the automation or of ChatGPT
goes into main by itself when it changes no test and no protected file
(tools/automerge.py); a mail with an exact subject says that a release is
ready to publish, with the command, and that ChatGPT has to step in
(tools/send-mail.py). The addresses and the password are secrets only."""

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


mail = load("send-mail")
merge = load("automerge")
guard = load("check-autofix-patch")
REPO = "NullSector-2077/IKE-Browser"


class FakeSMTP:
    sent, logins, fail = [], [], 0

    def __init__(self, host, port, context=None, timeout=0):
        self.host, self.port = host, port

    def __enter__(self):
        if FakeSMTP.fail:
            FakeSMTP.fail -= 1
            raise OSError("smtp down: secret-in-message")
        return self

    def __exit__(self, *a):
        return False

    def login(self, user, password):
        FakeSMTP.logins.append((user, password))

    def send_message(self, msg):
        FakeSMTP.sent.append(msg)


def test_a_mail_is_sent_with_the_exact_subject_to_every_address(capsys):
    FakeSMTP.sent, FakeSMTP.logins, FakeSMTP.fail = [], [], 1
    env = {"MAIL_USERNAME": "sender@example.test", "MAIL_APP_PASSWORD": "app-pass-TESTONLY",
           "MAIL_TO": "one@example.test, two@example.test"}
    subject = "C'E' UNA NUOVA RELEASE IN MAIN PRONTA DA PUBBLICARE!!!"
    assert mail.send(subject, "corpo", env=env, smtp=FakeSMTP, sleep=lambda s: None) is True
    msg = FakeSMTP.sent[0]
    assert msg["Subject"] == subject and msg["To"] == "one@example.test, two@example.test"
    assert FakeSMTP.logins == [("sender@example.test", "app-pass-TESTONLY")]
    out = capsys.readouterr().out
    assert "TESTONLY" not in out and "example.test" not in out and "secret-in-message" not in out


def test_without_secrets_nothing_is_sent_and_it_says_so(capsys):
    FakeSMTP.sent = []
    assert mail.send("x", "y", env={"MAIL_TO": "a@example.test"}, smtp=FakeSMTP) is False
    assert FakeSMTP.sent == [] and "not configured" in capsys.readouterr().out


def test_no_address_is_written_in_the_repository():
    """The repository is public: the owner's addresses live in the secrets only."""
    for path in [*WORKFLOWS.glob("*.yml"), ROOT / "tools" / "send-mail.py", ROOT / "tools" / "automerge.py"]:
        text = path.read_text()
        assert not re.search(r"[\w.+-]+@gmail\.com", text), path.name
    rr = (WORKFLOWS / "release-ready.yml").read_text()
    af = (WORKFLOWS / "autofix.yml").read_text()
    for text in (rr, af):
        assert "MAIL_TO: ${{ secrets.MAIL_TO }}" in text and "MAIL_APP_PASSWORD: ${{ secrets.MAIL_APP_PASSWORD }}" in text
    assert "C'E' UNA NUOVA RELEASE IN MAIN PRONTA DA PUBBLICARE!!!" in rr
    assert ("cd ~/IKE-Browser && git checkout main && git pull --ff-only && python3 tools/publish.py" in rr)
    assert "ATTENZIONE E' RICHIESTO IL TUO INTERVENTO PER FARE INTERVENIRE CHAT GPT NELL' AUTOFIX!!!" in af


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
    rr = (WORKFLOWS / "release-ready.yml").read_text()
    assert "release-mail-${{ steps.v.outputs.version }}-${{ steps.v.outputs.week }}" in rr
    assert "if: steps.mail.outputs.sent == 'true'" in rr and 'gh release view "v$version"' in rr


def test_no_fix_can_change_the_rules_it_is_judged_by():
    """An automatic or ChatGPT fix touching tools/automerge.py could change
    the merge rules for the next ones: both tools are protected files."""
    assert {"tools/automerge.py", "tools/send-mail.py"} <= set(guard.FORBIDDEN_FILES)
    assert decide(files=[{"filename": "tools/automerge.py", "status": "modified", "patch": "+x"}])[0] is False
