#!/usr/bin/env python3
"""Decide what the automatic fix does about a failed workflow run (no AI here).

Called by .github/workflows/autofix.yml from a checkout of main with all
branches (no credentials besides a read-only GH_TOKEN for `gh api`). It looks
at the failed run and writes, as GitHub outputs:

    action          fix | issue | skip
    reason          one line, shown in the issue or the log
    kind            main | maintenance | infra (an issue for a failure of
                    GitHub, the runner or a reporting job: not the code)
    checkout        the commit the agent starts from
    push_branch     where the fix goes (automation/daily-maintenance or
                    automation/autofix-main)
    attempt         1, 2, ... (at most MAX_ATTEMPTS fixes for one failure)
    allow_adblock   true only on a maintenance candidate that updates the engine
    workflow        name of the failed workflow

and writes the end of the failed jobs' logs to --logs (Markdown).

Only failures on the automation's own branches are fixed: main, the daily
maintenance candidate and the automatic fix itself. Runs from forks, from
pull requests of people and from the standby branches are never touched.

"Arch Linux" (arch.yml: I.K.E. on Arch's own Python, Qt and Qt WebEngine) is
handled like "Tests", with two differences: pacman, Arch's mirrors and
keyring, the container and the crates' download are never the code's (an
issue of GitHub's title, no AI); and a failure of the build or of the tests is
fixed only when "Tests" passed on the same commit, as an incompatibility with
Arch alone (when "Tests" failed too, its own fix handles it). Its failure
description names the Arch packages that changed since the last green run on
main (old -> new, from the versions both runs recorded), the failed tests and
the files the logs name.

    autofix-plan.py --run-id ID --logs FILE [--repo OWNER/NAME]
"""

import argparse
import datetime as dt
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

MAX_ATTEMPTS = 2
MAINTENANCE = "automation/daily-maintenance"
FIX_MAIN = "automation/autofix-main"
FIXABLE_BRANCHES = ("main", MAINTENANCE, FIX_MAIN)
# 1.1.19, the owner's words: GitHub mails the owner the issue with this title
ISSUE_TITLE = "ATTENZIONE E' RICHIESTO IL TUO INTERVENTO PER FARE INTERVENIRE CHAT GPT NELL' AUTOFIX!!! (%s)"
# The report (autofix.yml, job report) ends each issue and comment with the
# failed commit in this form, so the plan can tell a repeat of the same failure
# from a new one (1.1.18).
SHA_MARK = "<!-- autofix-sha: %s -->"
# since the audit of #65 also the branch that failed: only reports about main
# hold back a fix of main for REPORT_FRESH_HOURS (the trials on
# automation/autofix-main commented on issue #31 and kept main from a fix)
SHA_BRANCH_MARK = "<!-- autofix-sha: %s on %s -->"
SHA_MARK_RE = re.compile(r"<!-- autofix-sha: ([0-9a-f]{7,40})(?: on ([A-Za-z0-9._/-]{1,100}))? -->")
REPORT_FRESH_HOURS = 24
REPORTER = "github-actions[bot]"      # the author of the report job's comments
# Steps of the daily maintenance's "prepare" job that no AI fix of main can
# help (1.1.18): the check and apply of the component updates fails only when
# an upstream source cannot be reached (tools/check-components.py exits 1).
# Since 1.1.20 a builder that refuses a new upstream version (a Dark Reader
# patch whose text is gone, uBlock Origin's library laid out differently) does
# not stop that step: the component stays at the version in use and the
# "components" issue reports the incompatibility to a person. The
# engine's build stops the job only when its crates cannot be downloaded or an
# engine that did not change does not build; a NEW engine that does not build
# with I.K.E.'s wrapper reaches automation/daily-maintenance marked, its tests
# fail there and the fix of the candidate may change the wrapper
# (engine_update, allow_adblock; final review of 1.1.18).
SOURCES_STEP = "Check and apply component updates"
ENGINE_STEP = "Build AdBlock engine"
# A failure of GitHub or the runner, or of a job that only reports, is not a
# failure of the code or of the maintenance (final review of 1.1.18): no AI fix
# of main, and an issue of its own title, which never holds back the fix of a
# real failure (already_reported reads ISSUE_TITLE only).
INFRA_TITLE = "GitHub or the runner failed: %s"
# "Arch Linux": I.K.E. on Arch Linux's own packages (arch.yml)
ARCH = "Arch Linux"
ARCH_JOB = "Arch Linux"              # the name of arch.yml's job that builds and tests
HANDLED = ("Tests", "Daily maintenance candidate", "Daily component check", ARCH)
REPORTING_JOBS = {"Tests": ("hand-over",), "Daily component check": ("update-issue", "start-arch"),
                  "Daily maintenance candidate": ("publish-candidate",), ARCH: ("hand-over", "merge-ready")}
INFRA_STEP = re.compile(r"^(Set up job|Complete job|Post |Check out|Run actions/(checkout|setup-|upload-artifact"
                        r"|download-artifact|cache)|Upload |Download |Validate downloaded|Rust$|Test environment$)")
# arch.yml's steps that only install Arch's packages (pacman: mirrors, keyring,
# a package not found, a conflict), start the container or download the
# engine's crates: never the code's
ARCH_INFRA_STEP = re.compile(r"^(Initialize containers|Stop containers|Git \(for the checkout\)|Git owner check"
                             r"|Arch's packages|AdBlock engine's crates)$")
LOG_TRIES = 3
# Steps where a test may fail only sometimes (Qt WebEngine under load): failed
# there once, the tests run once more before any AI is asked (audit of #65, M5)
RERUN_STEPS = ("Tests", "Tests of the installed package")
ARCH_RERUN_STEPS = ("Tests (Arch's Qt)", "Tests of the installed package (Arch)")
# An Arch failure is fixed only when "Tests" passed on the same commit: its
# result is waited for (arch.yml may end first), at most this long
TESTS_WAIT_TRIES, TESTS_WAIT_PAUSE = 50, 60
# what a failed Arch run's logs name: pytest's summary lines and I.K.E.'s files
FAILED_TEST = re.compile(r"^(?:FAILED|ERROR) ((?:tests/)?[\w./-]+\.py(?:::\S+)?)(?: - (.*))?$")
NAMED_FILE = re.compile(r'File "[^"]*?((?:ike|tests|tools)/[\w./-]+\.py)", line (\d+)'
                        r"|(?<![\w.-])((?:ike|tests|tools)/[\w./-]+\.(?:py|js))(?::(\d+))?")
BOT = "github-actions[bot]"
LOG_LINES = 160              # of the failed step only (1.1.16: the whole job's end was mostly noise)
LOG_BYTES = 20000
# lines that never explain a failure: package installs, downloads, the runner's cleanup
NOISE = re.compile(
    r"^(Selecting previously unselected|Preparing to unpack|Unpacking |Setting up |Processing triggers|"
    r"Get:\d|Hit:\d|Ign:\d|Fetched |Reading (package lists|database|state information)|"
    r"Building dependency tree|\(Reading database|Collecting |Downloading |Using cached |"
    r"Requirement already satisfied|Installing collected packages|Successfully installed |"
    r"\s+Compiling |\s+Downloaded |\s+Downloading crates|\[command\]|Temporarily overriding HOME|"
    r"Adding repository directory|Cleaning up orphan processes|Post job cleanup|##\[(start|end)-action|"
    r"##\[warning\]Node\.js)")
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
STAMP = re.compile(r"^\d{4}-\d\d-\d\dT[\d:.]+Z ?")
ENV_LINE = re.compile(r"^  [A-Za-z_][A-Za-z0-9_]*: ")


def gh_api(path, raw=False, tries=3, pause=5):
    """GitHub's API through gh, asked again after a pause when it fails (audit
    of #65: one 502 dropped a failure)."""
    cmd = ["gh", "api", path]
    if raw:
        # Job logs hold the runner's colour codes, and newer gh refuses to print
        # them unless asked (seen on 2026-11-19: no assistant got the error);
        # clean_log removes them. Older gh does not know the flag: then without.
        cmd.insert(2, "--allow-escape-sequences")
    for n in range(tries):
        out = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if out.returncode and raw and "unknown flag" in out.stderr:
            cmd = ["gh", "api", path]
            out = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if not out.returncode or n + 1 == tries:
            break
        time.sleep(pause * (n + 1))
    if out.returncode:
        raise RuntimeError("gh api %s: %s" % (path, out.stderr.strip()[:300]))
    return out.stdout if raw else json.loads(out.stdout)


def git(*args):
    out = subprocess.run(["git", *args], capture_output=True, text=True, check=False)
    return out.stdout.strip() if out.returncode == 0 else ""


def tip(branch):
    return git("rev-parse", "-q", "--verify", "refs/remotes/origin/%s^{commit}" % branch)


def autofix_commits(branch):
    """Automatic fixes already made on a branch, since it left main."""
    base = git("merge-base", "origin/main", "origin/" + branch)
    if not base:
        return 0
    out = git("rev-list", "--count", "--grep", "^autofix:", "%s..origin/%s" % (base, branch))
    return int(out or 0)


def previous_fix(branch, repo):
    """The earlier automatic fixes of a branch and the agent's last summary, for
    a second attempt: it starts from them instead of exploring again."""
    base = git("merge-base", "origin/main", "origin/" + branch)
    if not base:
        return ""
    diff = git("log", "--reverse", "--grep", "^autofix:", "-p", "--format=commit %h %s",
               "%s..origin/%s" % (base, branch),
               "--", ".", ":(exclude)ike/__init__.py", ":(exclude)CHANGELOG.md")   # not the version bump
    if not diff:
        return ""
    summary = ""
    try:
        owner = repo.split("/")[0]
        prs = gh_api("repos/%s/pulls?state=open&head=%s:%s" % (repo, owner, branch))
        if prs:
            comments = gh_api("repos/%s/issues/%s/comments?per_page=100" % (repo, prs[0]["number"]))
            for c in reversed(comments):
                body = c.get("body") or ""
                if "### Summary of the agent" in body:
                    summary = body.split("### Summary of the agent", 1)[1].split("### Automatic checks")[0]
                    break
    except RuntimeError:
        pass
    text = ("\n## Previous automatic fix (the tests above failed after it)\n\n"
            "Start from this fix: correct only what the logs above show. Do not explore again "
            "and do not undo it unless it is the cause.\n\n```diff\n%s\n```\n" % diff[:15000].replace("```", "'''"))
    if summary.strip():
        text += "\nWhat the agent wrote about it:\n\n%s\n" % summary.strip()[:2000]
    return text


def clean_log(text):
    """The part of a job's log that explains the failure: the step that failed
    (from its "Run" line to its last error), without install and cleanup noise.
    A log with no error marker keeps its last lines, as before."""
    lines = [STAMP.sub("", ANSI.sub("", ln.lstrip("\ufeff"))) for ln in text.splitlines()]
    errors = [i for i, ln in enumerate(lines) if ln.startswith("##[error]")]
    if errors:
        end = errors[-1] + 1
        starts = [i for i in range(end) if lines[i].startswith("##[group]Run ")]
        lines = lines[starts[-1] if starts else 0:end]
    keep, in_env = [], False
    for ln in lines:
        if in_env and ENV_LINE.match(ln):
            continue                       # the runner's environment: no part of the failure
        in_env = ln == "env:"
        if not ln.strip() or NOISE.match(ln) or in_env or ln.startswith("shell: "):
            continue
        if ln.startswith("##[group]Run "):
            ln = "$ " + ln[len("##[group]Run "):]
        elif ln.startswith(("##[group]", "##[endgroup]")):
            continue
        keep.append(ln)
    tail = "\n".join(keep[-LOG_LINES:])
    return tail[-LOG_BYTES:]


def job_log(repo, job, tries=LOG_TRIES, pause=10, sleep=None):
    """The cleaned log of a failed job, or None. GitHub may answer 404 for a
    few seconds after a run closes: asked again before giving up."""
    for n in range(tries):
        try:
            return clean_log(gh_api("repos/%s/actions/jobs/%s/logs" % (repo, job["id"]), raw=True, tries=1))
        except RuntimeError as e:
            if n + 1 == tries:
                print("::warning::the log of job %s is not available: %s" % (job["name"], e))
                return None
            (sleep or time.sleep)(pause)
    return None


def completed_run(repo, run_id, tries=40, pause=15, sleep=time.sleep):
    """The run, once it has finished. A failure handed over by the tests
    themselves (tests.yml, job hand-over) arrives while their run is still
    closing: wait for it (at most about ten minutes)."""
    run = gh_api("repos/%s/actions/runs/%s" % (repo, run_id))
    for _ in range(tries):
        if run.get("status") == "completed":
            break
        sleep(pause)
        run = gh_api("repos/%s/actions/runs/%s" % (repo, run_id))
    return run


def _when(stamp):
    try:
        return dt.datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        return None


def report_mark(text):
    """(commit, branch) a report names: only in the exact last line the report
    job writes (second review of 1.1.18: its comments quote the agent's summary
    and the logs, where a mark could be planted). The branch is "" in the
    marks written before the audit of #65."""
    lines = [ln for ln in (text or "").replace("\r", "").split("\n") if ln.strip()]
    m = SHA_MARK_RE.fullmatch(lines[-1]) if lines else None
    return (m.group(1), m.group(2) or "") if m else ("", "")


def report_sha(text):
    return report_mark(text)[0]


def already_reported(issues, title, sha, now):
    """The open issue that already reports this failure, or None.

    An open issue blocks a new automatic fix only when it names the same failed
    commit (SHA_MARK in its body or comments) or was reported within the last
    REPORT_FRESH_HOURS. Until 1.1.17 any open issue with the title blocked every
    later failure, weeks later and on other commits (issue #31 of the first
    trials kept the fix of main asleep). issues: [{"title", "body",
    "reported_at"}], the body holding the comments too."""
    for issue in issues:
        if issue.get("title") != title:
            continue
        marks = issue.get("shas")
        if marks is None:
            marks = [report_sha(issue.get("body"))]
        marks = [m for m in marks if m]
        if sha and any(sha.startswith(m) or m.startswith(sha) for m in marks):
            return issue
        when = _when(issue.get("reported_at") or "")
        if when and now - when < dt.timedelta(hours=REPORT_FRESH_HOURS):
            return issue
    return None


def failed_steps(job):
    return [s.get("name") or "" for s in job.get("steps", []) if s.get("conclusion") == "failure"]


def infra_failure(name, failed_jobs):
    """Why the failure is GitHub's, the runner's or a reporting job's, not the
    code's or the maintenance's; '' when it is a real failure. Only when every
    failed job reports, or every failed step is one of the runner's own (check
    out, set up, an artifact kept or fetched); a job that failed with no failed
    step (a time limit) counts as real."""
    names = [j["name"] for j in failed_jobs]
    if not names:
        # audit of #65 (L5): a run that failed with no failed job (a workflow
        # file GitHub refused, a cancelled set-up)
        return "the run failed with no failed job: GitHub or a workflow file, not the code"
    reporting = REPORTING_JOBS.get(name, ())
    if names and all(n in reporting for n in names):
        return ("only the job that reports or publishes failed (%s): GitHub, a permission or a repository "
                "setting, not the code and not the maintenance" % ", ".join(names))
    steps = [st for j in failed_jobs if j["name"] not in reporting for st in failed_steps(j)]
    if steps and all(INFRA_STEP.match(st) for st in steps):
        return ("a step of GitHub or the runner failed (%s), not the code and not the maintenance: "
                "the next run usually passes" % ", ".join(steps))
    if name == ARCH and steps and all(INFRA_STEP.match(st) or ARCH_INFRA_STEP.match(st) for st in steps):
        return ("Arch Linux's packages could not be installed or a download failed (%s): pacman, Arch's mirrors, "
                "keyring or package set, the container or crates.io, not the code: the next run usually passes"
                % ", ".join(steps))
    return ""


def logs_missing(plan):
    """The plan when no log of the failed jobs could be read: an AI fix with no
    error to read would only guess (final review of 1.1.18)."""
    if plan["action"] != "fix":
        return plan
    return dict(plan, action="issue", kind="infra", checkout="", push_branch="", attempt="0", allow_adblock="false",
                reason="the logs of the failed run could not be read from GitHub: no fix without the error "
                       "(run the automatic fix again by hand when GitHub answers)")


def rehearsal_reason(name, branch):
    """Why a daily workflow's failure on another branch than main gets no fix.

    The daily check and the daily maintenance run on main by themselves; on
    another branch only when a person starts them there, to rehearse a change
    of the tools or to try a fault on purpose (a trial). That failure is the
    branch's, not main's: a fix of main, made from main's code, would answer a
    failure main does not have (until the trials of 2026-11-22 the plan sent
    it to the automatic fix of main). The person who started it reads the
    run. A failure of a source or of GitHub stays an issue, as on main."""
    return ("%s failed on %s, not on main (started by hand: a rehearsal or a trial): its failure is not main's, "
            "no automatic fix of main" % (name, branch or "?"))


def decide(run, failed_jobs, open_fix_pr, open_issues=(), now=None):
    """The plan for a failed run (a dict of outputs), without network or git."""
    name, branch = run["name"], run.get("head_branch") or ""
    plan = {"action": "skip", "reason": "", "kind": "", "checkout": "", "push_branch": "",
            "attempt": "0", "allow_adblock": "false", "workflow": name}
    if run.get("conclusion") != "failure":
        plan["reason"] = "the run did not fail (%s)" % run.get("conclusion")
        return plan
    if (run.get("head_repository") or {}).get("full_name") != run.get("_repo"):
        plan["reason"] = "the run comes from another repository (fork)"
        return plan
    job_names = [j["name"] for j in failed_jobs]
    tested = name in ("Tests", ARCH)          # the workflows that test a branch
    if name in HANDLED:
        if tested and branch not in FIXABLE_BRANCHES:
            plan["reason"] = "branch %s is not one the automation fixes" % (branch or "?")
            return plan
        if tested and run.get("_tip") != run.get("head_sha"):
            plan["reason"] = "the branch has moved since this run: an older failure"
            return plan
        infra = infra_failure(name, failed_jobs)
        if infra:
            plan.update(action="issue", kind="infra", reason=infra)
            return plan
        attempt = int(run.get("run_attempt") or 1)
        if tested and attempt > 1 and run.get("_event") == "workflow_run" and \
                (run.get("triggering_actor") or {}).get("login") == BOT:
            plan["reason"] = "a run the automatic fix started again: the tests hand its failure over themselves"
            return plan
        job, again = ("tests", RERUN_STEPS) if name == "Tests" else (ARCH_JOB, ARCH_RERUN_STEPS)
        steps = [st for j in failed_jobs if j["name"] == job for st in failed_steps(j)]
        if tested and attempt == 1 and steps and all(st in again for st in steps):
            plan.update(action="rerun", reason="the tests failed once (step: %s): they run once more before any "
                        "automatic fix, a test that fails only sometimes is no matter for an AI" % ", ".join(steps))
            return plan

    if name == "Tests":
        target = branch
    elif name == ARCH:
        tests = run.get("_tests") or ""
        if tests == "failure":
            plan["reason"] = ("Tests failed on the same commit too: its own automatic fix handles it (an Arch "
                              "failure is fixed only when Tests passed)")
            return plan
        if tests != "success":
            plan.update(action="issue", reason="Arch Linux failed on %s, but Tests has no result on the same commit "
                        "(%s): an incompatibility with Arch alone cannot be told from a failure of the code, a "
                        "person looks" % (branch or "?", tests or "no run"))
            return plan
        target = branch
    elif name == "Daily maintenance candidate":
        if "prepare" not in job_names:
            plan.update(action="issue", reason="the maintenance candidate could not be published "
                        "(failed: %s); this is a repository setting or a workflow, not code" % ", ".join(job_names))
            return plan
        steps = [st for j in failed_jobs if j["name"] == "prepare" for st in failed_steps(j)]
        if any(st.startswith(SOURCES_STEP) for st in steps):
            plan.update(action="issue", kind="infra", reason="a component source could not be reached or could "
                        "not be checked (step: %s; a builder that refuses a new version does not stop it: that "
                        "is reported in the components issue); nothing on main to fix, the next daily run tries "
                        "again" % SOURCES_STEP)
            return plan
        if any(st.startswith(ENGINE_STEP) for st in steps):
            # a new engine that does not build is published and fixed on its branch;
            # this step stops only for crates that could not be downloaded or an
            # engine that does not build although it did not change
            plan.update(action="issue", reason="the AdBlock engine's crates could not be downloaded, or an "
                        "engine that this candidate does not change does not build (step: %s): not a matter "
                        "for I.K.E.'s wrapper, a person looks" % ENGINE_STEP)
            return plan
        if branch != "main":
            plan["reason"] = rehearsal_reason(name, branch)
            return plan
        target = "main"
    elif name == "Daily component check":
        if job_names == ["lists"]:
            # 1.1.20: findings and unreachable lists never fail it; main's engine
            # that does not build, or the check itself, stopped
            plan.update(action="issue", reason="the default filter lists could not be checked in main's AdBlock "
                        "engine (job lists: the engine did not build or the check stopped); findings and "
                        "unreachable lists never fail it: a person looks")
            return plan
        if "check" not in job_names:
            plan.update(action="issue", reason="the components issue could not be updated "
                        "(failed: %s); this is a workflow, not code" % ", ".join(job_names))
            return plan
        if branch != "main":
            plan["reason"] = rehearsal_reason(name, branch)
            return plan
        target = "main"
    else:
        plan["reason"] = "workflow %s is not handled" % name
        return plan

    now = now or dt.datetime.now(dt.timezone.utc)
    if target == "main" and already_reported(open_issues, ISSUE_TITLE % name, run.get("head_sha") or "", now):
        plan["reason"] = "already reported and waiting for the owner (issue: %s)" % (ISSUE_TITLE % name)
        return plan
    if target == "main":
        if open_fix_pr:
            plan["reason"] = "an automatic fix for main is already waiting (PR #%s)" % open_fix_pr
            return plan
        plan.update(kind="main", checkout=run["_main_tip"], push_branch=FIX_MAIN, attempt="1")
    elif target == FIX_MAIN:
        plan.update(kind="main", checkout=run["_tip"], push_branch=FIX_MAIN,
                    attempt=str(run["_attempts"] + 1))
    else:
        plan.update(kind="maintenance", checkout=run["_tip"], push_branch=MAINTENANCE,
                    attempt=str(run["_attempts"] + 1),
                    allow_adblock="true" if run.get("_engine_update") else "false")
    if int(plan["attempt"]) > MAX_ATTEMPTS:
        plan.update(action="issue", reason="%d automatic fixes did not make it pass" % MAX_ATTEMPTS)
        return plan
    plan.update(action="fix", reason="%s failed on %s (jobs: %s)" % (name, branch or "?", ", ".join(job_names)))
    if name == ARCH:
        changed = run.get("_arch_changes") or []
        what = ("changed since the last green run on main: " + ", ".join(changed[:6]) if changed
                else "no followed package changed since the last green run on main")
        plan["reason"] = ("Arch Linux failed on %s while Tests passed on the same commit: an incompatibility with "
                          "Arch Linux's own packages (%s)" % (branch or "?", what))
    return plan


_ADBLOCK_LOCK = re.compile(r'^\[\[package\]\]\s*\nname = "adblock"\s*\nversion = "([^"]+)"', re.M)


def adblock_version(lock_text):
    """The version of the adblock crate in a Cargo.lock, or None."""
    m = _ADBLOCK_LOCK.search(lock_text or "")
    return m.group(1) if m else None


_PYO3_LOCK = re.compile(r'^name = "pyo3"\nversion = "([^"]+)"', re.M)


def pyo3_version(lock_text):
    """The version of the pyo3 crate in a Cargo.lock, or None."""
    m = _PYO3_LOCK.search((lock_text or "").replace("\r\n", "\n"))
    return m.group(1) if m else None


def engine_update(branch, show=None):
    """The candidate builds another version of the AdBlock engine than main.

    Read from ike-adblock/Cargo.lock (what is really built), the candidate's
    against main's. Until 1.1.16 this compared __version__ with
    __min_system__, but a new engine reaches users through the signed
    self-update and seldom raises the minimum system. Anything that cannot be
    read gives False: only a real engine update lets a fix touch I.K.E.'s
    wrapper of the ad blocker."""
    show = show or (lambda ref: git("show", "%s:ike-adblock/Cargo.lock" % ref))
    cand_lock, main_lock = show("origin/" + branch), show("origin/main")
    candidate, current = adblock_version(cand_lock), adblock_version(main_lock)
    if candidate and current and candidate != current:
        return True
    # 1.1.19: a new pyo3 (the bridge to Python, followed by the component
    # check) may need the same adaptation of the wrapper
    candidate, current = pyo3_version(cand_lock), pyo3_version(main_lock)
    return bool(candidate and current and candidate != current)


def open_reports(repo, name):
    """The open issues ISSUE_TITLE % <name> for already_reported():
    each with the commits its reports name (the issue and the report job's
    comments, by their last line) and the time of its latest report about
    main (audit of #65: a report about another branch, or one whose mark names
    no branch, never holds back a fix of main by its age, only by its commit)."""
    out = []
    for i in gh_api("repos/%s/issues?state=open&labels=autofix&per_page=100" % repo):
        if "pull_request" in i or i.get("title") != ISSUE_TITLE % name:
            continue
        sha, branch = report_mark(i.get("body"))
        shas, reported = [sha], (i.get("created_at") or "") if branch == "main" else ""
        try:
            comments = gh_api("repos/%s/issues/%s/comments?per_page=100" % (repo, i["number"]))
        except RuntimeError:
            comments = []
        for c in comments:
            if (c.get("user") or {}).get("login") != REPORTER:
                continue                      # anyone may comment; only the report job's comments count
            mark, branch = report_mark(c.get("body"))
            if mark:
                shas.append(mark)
                if branch == "main" and (c.get("created_at") or "") > reported:
                    reported = c["created_at"]
        out.append({"title": i["title"], "shas": [m for m in shas if m], "reported_at": reported})
    return out


def tests_result(repo, sha, tries=TESTS_WAIT_TRIES, pause=TESTS_WAIT_PAUSE, sleep=time.sleep):
    """The conclusion of "Tests" on this commit: "success", "failure" (a time
    limit too), "running" when it did not end in time, "" when it never ran
    there (runs waiting for an approval, cancelled or skipped do not count).
    Waits while it runs: arch.yml may end first."""
    for n in range(tries):
        runs = gh_api("repos/%s/actions/workflows/tests.yml/runs?head_sha=%s&per_page=20" % (repo, sha))
        runs = [r for r in runs.get("workflow_runs", []) if r.get("head_sha") == sha]
        busy = [r for r in runs if r.get("status") != "completed"]
        done = [r for r in runs if r.get("status") == "completed"
                and r.get("conclusion") in ("success", "failure", "timed_out")]
        if busy and n + 1 < tries:
            sleep(pause)
            continue
        if busy:
            return "running"
        if not done:
            return ""
        last = max(done, key=lambda r: (r.get("run_started_at") or r.get("created_at") or "", r.get("id") or 0))
        return "success" if last["conclusion"] == "success" else "failure"
    return "running"


def _components():
    """tools/check-components.py, beside this file (it reads what arch.yml recorded)."""
    spec = importlib.util.spec_from_file_location("check_components", Path(__file__).resolve().parent /
                                                  "check-components.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def arch_versions(repo, run_id, components=None):
    """(what the failed Arch run recorded, what the last green run on main
    recorded); None for what cannot be read."""
    cc = components or _components()
    records = []
    for read in (lambda: cc.arch_record_of_run(repo, run_id), lambda: cc.last_tested_arch(repo)):
        try:
            records.append(read())
        except Exception as e:          # GitHub's API: the failure is still described, without them
            print("::warning::the Arch versions could not be read: %s" % str(e)[:200].replace("::", ": "))
            records.append(None)
    return records[0], records[1]


def arch_change_lines(failed, green, components=None):
    """'name old -> new' for every followed package, and the Python, Qt, PyQt
    and Chromium I.K.E. reported, that differ between the two records."""
    if not failed or not green:
        return []
    cc = components or _components()
    out = ["%s %s -> %s" % (n, o or "(not recorded)", v or "(not installed)")
           for n, o, v in cc.arch_changes(green.get("packages", {}), failed.get("packages", {}))]
    for key, label in (("python", "Python"), ("qt", "Qt"), ("pyqt", "PyQt"), ("chromium", "Chromium")):
        if failed.get(key) and green.get(key) and failed[key] != green[key]:
            out.append("%s %s -> %s" % (label, green[key], failed[key]))
    return out


def arch_failure(failed, green, changes, logs):
    """The part of failure.md for an Arch-only failure: what changed, what was
    tested, the failed tests and the files the logs name."""
    out = ["\n## Arch Linux: an incompatibility with Arch's own packages\n\n",
           "\"Tests\" (Ubuntu, Python 3.13, PyPI's Qt) passed on this commit; \"Arch Linux\" failed with Arch "
           "Linux's own Python, Qt, PyQt and Qt WebEngine, which users get with `pacman -Syu`. Adapt I.K.E.'s "
           "code (ike/ and its own page scripts) so that it works with the versions below and still with those "
           "of \"Tests\"; never the package, the engine, the builders, the workflows or the tests.\n\n"]
    run = (green or {}).get("run") or {}
    if changes:
        out.append("Components changed since the last green \"Arch Linux\" run on main (%s, commit %s):\n\n"
                   % (run.get("url") or "?", str(run.get("sha") or "?")[:10]))
        out += ["- %s\n" % c for c in changes]
    elif green:
        out.append("No followed Arch package changed since the last green run on main (%s): the cause is more "
                   "likely the commit itself, or a package not followed here.\n" % (run.get("url") or "?"))
    else:
        out.append("No green \"Arch Linux\" run on main recorded its versions yet (or they could not be read): "
                   "no comparison.\n")
    if failed:
        out.append("\nThis run tested: Python %s, Qt %s, PyQt %s, Chromium %s; %s.\n" % (
            failed.get("python", "?"), failed.get("qt", "?"), failed.get("pyqt", "?"), failed.get("chromium", "?"),
            ", ".join("%s %s" % (n, v or "(not installed)") for n, v in failed.get("packages", {}).items())))
    tests, files = [], []
    for line in logs.splitlines():
        m = FAILED_TEST.match(line.strip())
        if m and m.group(0) not in tests:
            tests.append(m.group(0))
        for f in NAMED_FILE.finditer(line):
            place = "%s:%s" % (f.group(1), f.group(2)) if f.group(1) else \
                (f.group(3) + (":" + f.group(4) if f.group(4) else ""))
            if place not in files:
                files.append(place)
    # a file named with a line once is not listed again without it
    files = [f for f in files if ":" in f or not any(g.startswith(f + ":") for g in files)]
    out.append("\n### Failed tests\n\n" + ("".join("- %s\n" % t[:300] for t in tests[:20]) or
                                          "(none named in the log: the build or a step before the tests)\n"))
    out.append("\n### Files named in the log\n\n" + ("".join("- %s\n" % f for f in files[:20]) or "(none)\n"))
    return "".join(out)


CLOSING = re.compile(r"\b(close[sd]?|fix(?:e[sd])?|resolve[sd]?)(\s*:?\s+)((?:[\w.-]+/[\w.-]+)?#)(?=\d)", re.I)
ZWSP = "​"


def neutralise(text):
    """Text an AI wrote, safe in a pull request's body (audit of #65): no
    @mention that notifies someone, no "closes #N" that closes an issue when
    the pull request is merged. A zero-width space breaks both and shows
    nothing."""
    text = re.sub(r"@(?=[A-Za-z0-9])", "@" + ZWSP, text)
    return CLOSING.sub(lambda m: m.group(1) + m.group(2) + m.group(3) + ZWSP, text)


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    if argv[:1] == ["--neutralise"]:                 # autofix-plan.py --neutralise FILE...
        for name in argv[1:]:
            p = Path(name)
            if p.is_file():
                p.write_text(neutralise(p.read_text("utf-8", "replace")), "utf-8")
        return 0
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--logs", required=True)
    ap.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    ap.add_argument("--event", default="", help="what started this plan: workflow_run or workflow_dispatch")
    a = ap.parse_args(argv)
    repo = a.repo
    run = completed_run(repo, a.run_id)
    jobs = gh_api("repos/%s/actions/runs/%s/jobs?per_page=100" % (repo, a.run_id))["jobs"]
    failed = [j for j in jobs if j.get("conclusion") == "failure"]
    branch = run.get("head_branch") or ""
    run["_repo"] = repo
    run["_event"] = a.event
    run["_tip"] = tip(branch) if branch else ""
    run["_main_tip"] = tip("main")
    run["_attempts"] = autofix_commits(branch) if branch in (MAINTENANCE, FIX_MAIN) else 0
    run["_engine_update"] = branch == MAINTENANCE and engine_update(MAINTENANCE)
    prs = gh_api("repos/%s/pulls?state=open&head=%s:%s" % (repo, repo.split("/")[0], FIX_MAIN))
    open_fix_pr = str(prs[0]["number"]) if prs else ""
    reports = open_reports(repo, run["name"])
    # An Arch failure is decided as if Tests had passed first: only one that
    # would then be fixed reads what it tested against the last green run on
    # main, and waits for the result of Tests on the same commit
    arch = None
    plan = decide(dict(run, _tests="success") if run["name"] == ARCH else run, failed, open_fix_pr, reports)
    if run["name"] == ARCH and plan["action"] == "fix":
        arch = arch_versions(repo, a.run_id)
        run["_arch_changes"] = arch_change_lines(*arch)
        run["_tests"] = tests_result(repo, run.get("head_sha", ""))
        plan = decide(run, failed, open_fix_pr, reports)
    # the commit that failed: the issue's message for ChatGPT starts from it when
    # no automatic fix is tried (after two attempts, for instance)
    plan["head_sha"] = run.get("head_sha", "")
    plan["branch"] = branch                     # for the report's mark (audit of #65)
    if plan["action"] == "skip":
        print("::notice::no automatic fix: %s" % plan["reason"].replace("::", ": "))

    parts = ["# Failure to fix\n",
             "- Workflow: %s\n- Branch: %s\n- Commit: %s\n- Run: %s\n" % (
                 run["name"], branch, run.get("head_sha", ""), run.get("html_url", ""))]
    read, logs = 0, []
    for job in failed:
        steps = [s["name"] for s in job.get("steps", []) if s.get("conclusion") == "failure"]
        log = job_log(repo, job) if plan["action"] in ("fix", "issue") else None
        if log is None:
            log = "(log not available)"
        else:
            read += 1
            logs.append(log)
        parts.append("\n## Job `%s` (failed step: %s)\n\nThe failed step's log:\n\n```text\n%s\n```\n"
                     % (job["name"], ", ".join(steps) or "?", log.replace("```", "'''")))
    if failed and not read:
        plan = logs_missing(plan)
    if arch and plan["action"] in ("fix", "issue"):
        parts.insert(2, arch_failure(arch[0], arch[1], run.get("_arch_changes") or [], "\n".join(logs)))
    # where the fix branch was when this plan was made: publish pushes only if
    # it is still there (1.1.18: two plans of main side by side could each push)
    plan["push_tip"] = tip(plan["push_branch"]) if plan["push_branch"] else ""
    if plan["action"] == "fix" and branch in (MAINTENANCE, FIX_MAIN) and run["_attempts"]:
        parts.append(previous_fix(branch, repo))
    Path(a.logs).write_text("".join(parts), "utf-8")

    print(json.dumps(plan, indent=1))
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            for k, v in plan.items():
                f.write("%s=%s\n" % (k, str(v).replace("\n", " ")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
