#!/usr/bin/env python3
"""Decide what the automatic fix does about a failed workflow run (no AI here).

Called by .github/workflows/autofix.yml from a checkout of main with all
branches (no credentials besides a read-only GH_TOKEN for `gh api`). It looks
at the failed run and writes, as GitHub outputs:

    action          fix | issue | skip
    reason          one line, shown in the issue or the log
    kind            main | maintenance
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

    autofix-plan.py --run-id ID --logs FILE [--repo OWNER/NAME]
"""

import argparse
import datetime as dt
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
ISSUE_TITLE = "Automatic fix needs you: %s"
# The report (autofix.yml, job report) ends each issue and comment with the
# failed commit in this form, so the plan can tell a repeat of the same failure
# from a new one (1.1.18).
SHA_MARK = "<!-- autofix-sha: %s -->"
SHA_MARK_RE = re.compile(r"<!-- autofix-sha: ([0-9a-f]{7,40}) -->")
REPORT_FRESH_HOURS = 24
# Steps of the daily maintenance's "prepare" job that no AI fix of main can
# help (1.1.18): the check and apply of the component updates fails when an
# upstream source cannot be reached (tools/check-components.py exits 1), and a
# new AdBlock engine that does not build needs I.K.E.'s wrapper changed, which a
# fix of main may not do.
SOURCES_STEP = "Check and apply component updates"
ENGINE_STEP = "Build AdBlock engine"
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


def gh_api(path, raw=False):
    cmd = ["gh", "api", path]
    if raw:
        # Job logs hold the runner's colour codes, and newer gh refuses to print
        # them unless asked (seen on 2026-11-19: no assistant got the error);
        # clean_log removes them. Older gh does not know the flag: then without.
        cmd.insert(2, "--allow-escape-sequences")
    out = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if out.returncode and raw and "unknown flag" in out.stderr:
        out = subprocess.run(["gh", "api", path], capture_output=True, text=True, check=False)
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
        marks = SHA_MARK_RE.findall(issue.get("body") or "")
        if sha and any(sha.startswith(m) or m.startswith(sha) for m in marks):
            return issue
        when = _when(issue.get("reported_at") or "")
        if when and now - when < dt.timedelta(hours=REPORT_FRESH_HOURS):
            return issue
    return None


def failed_steps(job):
    return [s.get("name") or "" for s in job.get("steps", []) if s.get("conclusion") == "failure"]


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

    if name == "Tests":
        if branch not in FIXABLE_BRANCHES:
            plan["reason"] = "branch %s is not one the automation fixes" % (branch or "?")
            return plan
        if run.get("_tip") != run.get("head_sha"):
            plan["reason"] = "the branch has moved since this run: an older failure"
            return plan
        target = branch
    elif name == "Daily maintenance candidate":
        if "prepare" not in job_names:
            plan.update(action="issue", reason="the maintenance candidate could not be published "
                        "(failed: %s); this is a repository setting or a workflow, not code" % ", ".join(job_names))
            return plan
        steps = [st for j in failed_jobs if j["name"] == "prepare" for st in failed_steps(j)]
        if any(st.startswith(SOURCES_STEP) for st in steps):
            plan.update(action="issue", reason="a component source could not be checked or its update could "
                        "not be applied (step: %s); nothing on main to fix, the next daily run tries "
                        "again" % SOURCES_STEP)
            return plan
        if any(st.startswith(ENGINE_STEP) for st in steps):
            plan.update(action="issue", reason="the new AdBlock engine does not build with I.K.E.'s wrapper "
                        "(step: %s); a fix of main may not change the wrapper" % ENGINE_STEP)
            return plan
        target = "main"
    elif name == "Daily component check":
        if "check" not in job_names:
            plan.update(action="issue", reason="the components issue could not be updated "
                        "(failed: %s); this is a workflow, not code" % ", ".join(job_names))
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
    return plan


_ADBLOCK_LOCK = re.compile(r'^\[\[package\]\]\s*\nname = "adblock"\s*\nversion = "([^"]+)"', re.M)


def adblock_version(lock_text):
    """The version of Brave's adblock crate in a Cargo.lock, or None."""
    m = _ADBLOCK_LOCK.search(lock_text or "")
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
    candidate = adblock_version(show("origin/" + branch))
    current = adblock_version(show("origin/main"))
    return bool(candidate and current and candidate != current)


def open_reports(repo, name):
    """The open issues "Automatic fix needs you: <name>" for already_reported():
    each with its comments added to its body and the time of its latest report
    (the issue itself, or the latest comment of the report job)."""
    out = []
    for i in gh_api("repos/%s/issues?state=open&labels=autofix&per_page=100" % repo):
        if "pull_request" in i or i.get("title") != ISSUE_TITLE % name:
            continue
        body, reported = i.get("body") or "", i.get("created_at") or ""
        try:
            comments = gh_api("repos/%s/issues/%s/comments?per_page=100" % (repo, i["number"]))
        except RuntimeError:
            comments = []
        for c in comments:
            text = c.get("body") or ""
            body += "\n" + text
            if SHA_MARK_RE.search(text) and (c.get("created_at") or "") > reported:
                reported = c["created_at"]
        out.append({"title": i["title"], "body": body, "reported_at": reported})
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--logs", required=True)
    ap.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    a = ap.parse_args(argv)
    repo = a.repo
    run = completed_run(repo, a.run_id)
    jobs = gh_api("repos/%s/actions/runs/%s/jobs?per_page=100" % (repo, a.run_id))["jobs"]
    failed = [j for j in jobs if j.get("conclusion") == "failure"]
    branch = run.get("head_branch") or ""
    run["_repo"] = repo
    run["_tip"] = tip(branch) if branch else ""
    run["_main_tip"] = tip("main")
    run["_attempts"] = autofix_commits(branch) if branch in (MAINTENANCE, FIX_MAIN) else 0
    run["_engine_update"] = branch == MAINTENANCE and engine_update(MAINTENANCE)
    prs = gh_api("repos/%s/pulls?state=open&head=%s:%s" % (repo, repo.split("/")[0], FIX_MAIN))
    open_fix_pr = str(prs[0]["number"]) if prs else ""
    plan = decide(run, failed, open_fix_pr, open_reports(repo, run["name"]))
    # the commit that failed: the issue's message for ChatGPT starts from it when
    # no automatic fix is tried (after two attempts, for instance)
    plan["head_sha"] = run.get("head_sha", "")

    parts = ["# Failure to fix\n",
             "- Workflow: %s\n- Branch: %s\n- Commit: %s\n- Run: %s\n" % (
                 run["name"], branch, run.get("head_sha", ""), run.get("html_url", ""))]
    for job in failed:
        steps = [s["name"] for s in job.get("steps", []) if s.get("conclusion") == "failure"]
        try:
            log = clean_log(gh_api("repos/%s/actions/jobs/%s/logs" % (repo, job["id"]), raw=True))
        except RuntimeError as e:
            log = "(log not available: %s)" % e
            print("::warning::the log of job %s is not available: %s" % (job["name"], e))
        parts.append("\n## Job `%s` (failed step: %s)\n\nThe failed step's log:\n\n```text\n%s\n```\n"
                     % (job["name"], ", ".join(steps) or "?", log.replace("```", "'''")))
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
