#!/usr/bin/env python3
"""Weekly check that the automation still works (no AI here).

Called by .github/workflows/health.yml with a GH_TOKEN for `gh api`. It finds
what would otherwise break in silence:

- a daily workflow that has not run for DAYS days (GitHub turns scheduled
  workflows off in a public repository after 60 days without activity; the
  workflow turns them on again before this check);
- a daily workflow whose last RUNS scheduled runs all failed;
- the tests failing on main;
- the GEMINI_API_KEY secret missing (HAS_KEY=false), without which the
  automatic fix cannot start;
- (1.1.18) runs of the automatic fix that failed in the last WAITING days; the
  reserves' secrets GROQ_API_KEY, ZAI_API_KEY (1.1.19) and OPENROUTER_API_KEY
  missing (HAS_GROQ_KEY, HAS_ZAI_KEY, HAS_OPENROUTER_KEY: the workflow passes only whether they are
  set, never their values); issues of the automatic fix and maintenance pull
  requests waiting for more than WAITING days; main without branch protection.

With problems it opens (or updates) the issue "Automation health"; without, it
closes that issue. --dry-run only prints.
"""

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

DAYS = 3
RUNS = 3
WAITING = 7
DAILY = ("daily-check.yml", "daily-maintenance.yml")
# 1.1.19: the other scheduled checks are watched too (a weekly Arch run or the
# daily security job that failed or stopped told nobody): (days without a
# scheduled run, failed runs in a row) before it is reported
WATCHED = {"daily-check.yml": (DAYS, RUNS), "daily-maintenance.yml": (DAYS, RUNS),
           "security.yml": (DAYS, 2), "arch.yml": (9, 1)}
PING_ADVICE = {"auth": "the key was refused: make a new one and put it in the secret",
               "config": "the model is unknown there: set the variable of its models (docs/MAINTENANCE.md)",
               "toolarge": "the provider refused even a tiny request"}
TITLE = "Automation health"


def gh(*args):
    out = subprocess.run(["gh", *args], capture_output=True, text=True, check=False)
    if out.returncode:
        raise RuntimeError("gh %s: %s" % (" ".join(args[:2]), out.stderr.strip()[:300]))
    return out.stdout


def api(path):
    return json.loads(gh("api", path))


def runs(repo, workflow, query):
    data = api("repos/%s/actions/workflows/%s/runs?per_page=20&%s" % (repo, workflow, query))
    return data.get("workflow_runs", [])


def _when(item):
    return dt.datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))


def problems(now, daily, main_tests, has_key, autofix_runs=(), reserve_keys=None, autofix_issues=(),
             maintenance_prs=(), main_protected=None, unreadable=(), pings=()):
    """The problems found (a list of lines), from data already fetched."""
    found = []
    for name, items in daily.items():
        done = [r for r in items if r.get("status") == "completed"]
        if not done:
            found.append("`%s` has never run on schedule." % name)
            continue
        days, in_row = WATCHED.get(name, (DAYS, RUNS))
        last = _when(done[0])
        if now - last > dt.timedelta(days=days):
            found.append("`%s` has not run since %s." % (name, last.date()))
        recent = done[:in_row]
        if len(recent) == in_row and all(r.get("conclusion") == "failure" for r in recent):
            found.append("`%s` failed in its last %d scheduled run(s): %s"
                         % (name, in_row, recent[0]["html_url"]))
    done = [r for r in main_tests if r.get("status") == "completed"]
    if done and done[0].get("conclusion") == "failure":
        found.append("The tests fail on main: %s" % done[0]["html_url"])
    if not has_key:
        found.append("The repository secret `GEMINI_API_KEY` is missing: the automatic fix cannot start.")
    week = dt.timedelta(days=WAITING)
    failed = [r for r in autofix_runs if r.get("conclusion") == "failure" and now - _when(r) <= week]
    if failed:
        found.append("The automatic fix failed %d time(s) in the last %d days (latest: %s)."
                     % (len(failed), WAITING, failed[0]["html_url"]))
    for name, present in (reserve_keys or {}).items():
        if not present:
            found.append("The repository secret `%s` is missing: that reserve of the automatic fix is "
                         "never asked." % name)
    for issue in autofix_issues:
        if "pull_request" not in issue and now - _when(issue) > week:
            found.append("The issue \"%s\" has waited for more than %d days: %s"
                         % (issue.get("title", ""), WAITING, issue.get("html_url", "")))
    for pr in maintenance_prs:
        if now - _when(pr) > week:
            found.append("The maintenance pull request \"%s\" has waited for more than %d days: %s"
                         % (pr.get("title", ""), WAITING, pr.get("html_url", "")))
    if main_protected is False:
        found.append("`main` has no branch protection: Settings, Branches (docs/MAINTENANCE.md).")
    for provider, model, result in pings:
        if result in PING_ADVICE:
            found.append("The reserve %s (%s) did not answer the weekly question: %s."
                         % (provider, model, PING_ADVICE[result]))
    for what in unreadable:
        found.append("Could not check %s." % what)
    return found


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    now = dt.datetime.now(dt.timezone.utc)
    daily = {w: runs(a.repo, w, "event=schedule") for w in WATCHED}
    main_tests = runs(a.repo, "tests.yml", "branch=main&event=push")
    unreadable = []

    def fetch(what, default, read):
        try:
            return read()
        except (RuntimeError, ValueError, KeyError) as e:
            print("::warning::%s: %s" % (what, str(e).replace("\n", " ")[:200]))
            unreadable.append(what)
            return default
    since = (now - dt.timedelta(days=WAITING)).date().isoformat()
    autofix_runs = fetch("the runs of the automatic fix", [],
                         lambda: runs(a.repo, "autofix.yml", "created=%3E%3D" + since))
    autofix_issues = fetch("the issues of the automatic fix", [],
                           lambda: api("repos/%s/issues?state=open&labels=autofix&per_page=100" % a.repo))
    maintenance_prs = fetch("the maintenance pull requests", [], lambda: [
        p for p in api("repos/%s/pulls?state=open&per_page=100" % a.repo)
        if p.get("head", {}).get("ref") == "automation/daily-maintenance"
        or any(lb.get("name") == "maintenance" for lb in p.get("labels", []))])
    protected = fetch("the protection of main", None,
                      lambda: bool(api("repos/%s/branches/main" % a.repo)["protected"]))
    keys = {"GROQ_API_KEY": os.environ.get("HAS_GROQ_KEY", "true") == "true",
            "ZAI_API_KEY": os.environ.get("HAS_ZAI_KEY", "true") == "true",
            "OPENROUTER_API_KEY": os.environ.get("HAS_OPENROUTER_KEY", "true") == "true"}
    pings = []
    if os.environ.get("RESERVE_PING"):          # written by the workflow's step before (1.1.19)
        try:
            pings = [tuple(x) for x in json.loads(Path(os.environ["RESERVE_PING"]).read_text("utf-8"))]
        except (OSError, ValueError, TypeError):
            unreadable.append("the answers of the reserves")
    found = problems(now, daily, main_tests, os.environ.get("HAS_KEY", "true") == "true", autofix_runs,
                     keys, autofix_issues, maintenance_prs, protected, unreadable, pings)
    text = ("The weekly check found problems in the automation:\n\n" + "".join("- %s\n" % p for p in found)
            + "\nControllo settimanale: l'automazione ha bisogno di te.\n") if found else ""
    print(text or "Everything works.")
    if a.dry_run:
        return 0
    issues = json.loads(gh("issue", "list", "--repo", a.repo, "--label", "automation-health",
                           "--state", "open", "--json", "number,title"))
    open_issue = next((i["number"] for i in issues if i["title"] == TITLE), None)
    if found:
        gh("label", "create", "automation-health", "--repo", a.repo, "--color", "b60205",
           "--description", "The automation needs the owner", "--force")
        if open_issue:
            gh("issue", "comment", str(open_issue), "--repo", a.repo, "--body", text)
        else:
            gh("issue", "create", "--repo", a.repo, "--title", TITLE, "--label", "automation-health",
               "--body", text)
    elif open_issue:
        gh("issue", "close", str(open_issue), "--repo", a.repo, "--comment", "Everything works again.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
