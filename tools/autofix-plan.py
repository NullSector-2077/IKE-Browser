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
import json
import os
import re
import subprocess
import sys
from pathlib import Path

MAX_ATTEMPTS = 2
MAINTENANCE = "automation/daily-maintenance"
FIX_MAIN = "automation/autofix-main"
FIXABLE_BRANCHES = ("main", MAINTENANCE, FIX_MAIN)
ISSUE_TITLE = "Automatic fix needs you: %s"
LOG_LINES = 400
LOG_BYTES = 60000
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
STAMP = re.compile(r"^\d{4}-\d\d-\d\dT[\d:.]+Z ?")


def gh_api(path, raw=False):
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


def clean_log(text):
    lines = [STAMP.sub("", ANSI.sub("", ln.lstrip("\ufeff"))) for ln in text.splitlines()]
    lines = [ln for ln in lines if ln.strip() and not ln.startswith(("##[group]", "##[endgroup]"))]
    tail = "\n".join(lines[-LOG_LINES:])
    return tail[-LOG_BYTES:]


def decide(run, failed_jobs, open_fix_pr, open_issues=()):
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

    if target == "main" and ISSUE_TITLE % name in open_issues:
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


def engine_update(branch):
    """The candidate raises the minimum system: it updates the AdBlock engine."""
    text = git("show", "origin/%s:ike/__init__.py" % branch)
    version = re.search(r'^__version__ = "([^"]+)"', text, re.M)
    minimum = re.search(r'^__min_system__ = "([^"]+)"', text, re.M)
    return bool(version and minimum and version.group(1) == minimum.group(1))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--logs", required=True)
    ap.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    a = ap.parse_args(argv)
    repo = a.repo
    run = gh_api("repos/%s/actions/runs/%s" % (repo, a.run_id))
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
    issues = gh_api("repos/%s/issues?state=open&labels=autofix&per_page=100" % repo)
    plan = decide(run, failed, open_fix_pr, [i["title"] for i in issues])

    parts = ["# Failure to fix\n",
             "- Workflow: %s\n- Branch: %s\n- Commit: %s\n- Run: %s\n" % (
                 run["name"], branch, run.get("head_sha", ""), run.get("html_url", ""))]
    for job in failed:
        steps = [s["name"] for s in job.get("steps", []) if s.get("conclusion") == "failure"]
        try:
            log = clean_log(gh_api("repos/%s/actions/jobs/%s/logs" % (repo, job["id"]), raw=True))
        except RuntimeError as e:
            log = "(log not available: %s)" % e
        parts.append("\n## Job `%s` (failed step: %s)\n\nLast lines of its log:\n\n```text\n%s\n```\n"
                     % (job["name"], ", ".join(steps) or "?", log.replace("```", "'''")))
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
