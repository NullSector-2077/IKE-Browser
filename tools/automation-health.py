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
  automatic fix cannot start.

With problems it opens (or updates) the issue "Automation health"; without, it
closes that issue. --dry-run only prints.
"""

import argparse
import datetime as dt
import json
import os
import subprocess
import sys

DAYS = 3
RUNS = 3
DAILY = ("daily-check.yml", "daily-maintenance.yml")
TITLE = "Automation health"


def gh(*args):
    out = subprocess.run(["gh", *args], capture_output=True, text=True, check=False)
    if out.returncode:
        raise RuntimeError("gh %s: %s" % (" ".join(args[:2]), out.stderr.strip()[:300]))
    return out.stdout


def runs(repo, workflow, query):
    data = json.loads(gh("api", "repos/%s/actions/workflows/%s/runs?per_page=20&%s" % (repo, workflow, query)))
    return data.get("workflow_runs", [])


def problems(now, daily, main_tests, has_key):
    """The problems found (a list of lines), from data already fetched."""
    found = []
    for name, items in daily.items():
        done = [r for r in items if r.get("status") == "completed"]
        if not done:
            found.append("`%s` has never run on schedule." % name)
            continue
        last = dt.datetime.fromisoformat(done[0]["created_at"].replace("Z", "+00:00"))
        if now - last > dt.timedelta(days=DAYS):
            found.append("`%s` has not run since %s." % (name, last.date()))
        recent = done[:RUNS]
        if len(recent) == RUNS and all(r.get("conclusion") == "failure" for r in recent):
            found.append("`%s` failed in its last %d scheduled runs: %s" % (name, RUNS, recent[0]["html_url"]))
    done = [r for r in main_tests if r.get("status") == "completed"]
    if done and done[0].get("conclusion") == "failure":
        found.append("The tests fail on main: %s" % done[0]["html_url"])
    if not has_key:
        found.append("The repository secret `GEMINI_API_KEY` is missing: the automatic fix cannot start.")
    return found


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    now = dt.datetime.now(dt.timezone.utc)
    daily = {w: runs(a.repo, w, "event=schedule") for w in DAILY}
    main_tests = runs(a.repo, "tests.yml", "branch=main&event=push")
    found = problems(now, daily, main_tests, os.environ.get("HAS_KEY", "true") == "true")
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
