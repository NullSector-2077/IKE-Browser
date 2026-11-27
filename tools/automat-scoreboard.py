#!/usr/bin/env python3
"""AUTOMAT's weekly scoreboard: a few numbers that say whether the automatic maintenance really works (no AI here).

The owner (2026-11-27): "simple, but it must work". Once a week (health.yml) this tool reads, with GET calls only:

- the automation's pull requests merged in the last 7 days, and how many merged by themselves (fully verified);
- the automation's pull requests still open, and how many days the oldest has waited;
- the AI work of the last 7 days from AUTOMAT's memory (automat/memory quota.json): runs, runs in which a free
  provider answered, runs in which none did, and the requests each provider used;
- the runs of Tests and Arch Linux that passed only when started again (a test that fails only sometimes, or the
  infrastructure), with their jobs;
- whether the latest Tests and Arch Linux runs of main passed.

It writes one issue, "AUTOMAT: tabellone settimanale" (label automat-scoreboard), edited every week, in Italian
for the owner; never a new issue each week, and nobody is mailed by an edit.

    automat-scoreboard.py [--repo OWNER/NAME] [--dry-run]
"""

import argparse
import base64
import datetime as dt
import json
import os
import subprocess
import sys

TITLE = "AUTOMAT: tabellone settimanale"
LABEL = "automat-scoreboard"
DAYS = 7
# the automation's own pull requests (what the verified merge may merge by itself), not Claude's working branches
AUTOMATION = ("automation/update/", "automation/builder/", "automation/daily-maintenance", "automation/autofix-main")
MERGED_BY_ITSELF = "merged by itself"
CHECKED = ("tests.yml", "arch.yml")


def gh_api(path):
    out = subprocess.run(["gh", "api", path], capture_output=True, text=True, check=False)
    if out.returncode:
        raise RuntimeError("gh api %s: %s" % (path, out.stderr.strip()[:200]))
    return json.loads(out.stdout)


def _when(text):
    return dt.datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)


def merged_prs(repo, api, since):
    """The automation's pull requests merged since `since`: [(number, title, by itself)]."""
    out = []
    for pr in api("repos/%s/pulls?state=closed&sort=updated&direction=desc&per_page=100" % repo):
        ref = (pr.get("head") or {}).get("ref", "")
        if pr.get("merged_at") and ref.startswith(AUTOMATION) and _when(pr["merged_at"]) >= since:
            commit = ""
            if pr.get("merge_commit_sha"):
                try:
                    commit = api("repos/%s/commits/%s" % (repo, pr["merge_commit_sha"]))["commit"]["message"]
                except (RuntimeError, KeyError, TypeError):
                    commit = ""
            out.append((pr["number"], pr.get("title", ""), MERGED_BY_ITSELF in commit))
    return out


def open_prs(repo, api, now):
    """The automation's open pull requests: [(number, title, days open)], the oldest first."""
    rows = [(pr["number"], pr.get("title", ""), (now - _when(pr["created_at"])).days)
            for pr in api("repos/%s/pulls?state=open&per_page=100" % repo)
            if (pr.get("head") or {}).get("ref", "").startswith(AUTOMATION)
            and "drill" not in (pr.get("head") or {}).get("ref", "")]
    return sorted(rows, key=lambda r: -r[2])


def ai_week(repo, api, now):
    """{"runs", "answered", "no_provider", "requests": {provider: n}} of AUTOMAT's memory for the last DAYS days."""
    data = api("repos/%s/contents/quota.json?ref=automat/memory" % repo)
    state = json.loads(base64.b64decode(data.get("content", "")).decode("utf-8"))
    first = (now - dt.timedelta(days=DAYS - 1)).date().isoformat()
    out = {"runs": 0, "answered": 0, "no_provider": 0, "requests": {}}
    for day, row in (state.get("days") or {}).items():
        if day < first or not isinstance(row, dict):
            continue
        for key in ("runs", "answered", "no_provider"):
            out[key] += int(row.get(key) or 0)
        for name, p in (row.get("providers") or {}).items():
            if isinstance(p, dict):
                out["requests"][name] = out["requests"].get(name, 0) + int(p.get("requests") or 0)
    return out


def rerun_only(repo, api, since):
    """Runs of Tests and Arch Linux that passed only when started again: [(workflow, branch, failed jobs)]."""
    out = []
    for wf in CHECKED:
        runs = api("repos/%s/actions/workflows/%s/runs?per_page=100&created=%%3E%%3D%s"
                   % (repo, wf, since.date().isoformat())).get("workflow_runs", [])
        for run in runs:
            if int(run.get("run_attempt") or 1) < 2 or run.get("conclusion") != "success":
                continue
            try:
                jobs = api("repos/%s/actions/runs/%s/attempts/1/jobs?per_page=100" % (repo, run["id"]))["jobs"]
            except (RuntimeError, KeyError, TypeError):
                jobs = []
            failed = sorted({j.get("name", "?") for j in jobs if j.get("conclusion") == "failure"})
            if failed:
                out.append((run.get("name", wf), run.get("head_branch", ""), failed))
    return out


def main_state(repo, api):
    """{workflow name: conclusion} of the latest completed run of main (a run cancelled by a newer one skipped)."""
    out = {}
    for wf in CHECKED:
        runs = api("repos/%s/actions/workflows/%s/runs?branch=main&status=completed&per_page=10" % (repo, wf))
        rows = [r for r in runs.get("workflow_runs", []) if r.get("conclusion") not in ("cancelled", "skipped")]
        if rows:
            out[rows[0].get("name", wf)] = rows[0].get("conclusion", "")
    return out


def gather(repo, api=gh_api, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    since = now - dt.timedelta(days=DAYS)
    info, missing = {"when": now.strftime("%Y-%m-%d")}, []
    for key, read in (("merged", lambda: merged_prs(repo, api, since)), ("open", lambda: open_prs(repo, api, now)),
                      ("ai", lambda: ai_week(repo, api, now)), ("rerun", lambda: rerun_only(repo, api, since)),
                      ("main", lambda: main_state(repo, api))):
        try:
            info[key] = read()
        except Exception as e:                  # one part not read never hides the others
            info[key] = None
            missing.append("%s (%s)" % (key, type(e).__name__))
    info["missing"] = missing
    return info


def text(info):
    """The issue's body, in Italian for the owner."""
    out = ["Aggiornato da solo ogni settimana (`tools/automat-scoreboard.py`). Ultima lettura: %s." % info["when"], ""]
    merged = info.get("merged")
    if merged is not None:
        alone = sum(1 for _n, _t, by in merged if by)
        out += ["**Aggiornamenti entrati in `main` negli ultimi 7 giorni:** %d, di cui **%d da soli** (verificati, "
                "senza nessuno)." % (len(merged), alone)]
        out += ["- #%d %s%s" % (n, t[:90], "" if by else " (unito da Claude)") for n, t, by in merged[:12]]
        out.append("")
    waiting = info.get("open")
    if waiting is not None:
        if waiting:
            out += ["**Aggiornamenti in attesa:** %d; il più vecchio aspetta da %d giorni." % (len(waiting),
                                                                                           waiting[0][2])]
            out += ["- #%d %s (%d giorni)" % (n, t[:90], d) for n, t, d in waiting[:8]]
        else:
            out.append("**Aggiornamenti in attesa:** nessuno.")
        out.append("")
    ai = info.get("ai")
    if ai is not None:
        used = ", ".join("%s %d" % (n, r) for n, r in sorted(ai["requests"].items()) if r) or "nessuna"
        out += ["**Lavoro delle AI (7 giorni):** %d tentativi; in %d ha risposto un'AI gratuita, in %d nessuna. "
                "Richieste usate: %s." % (ai["runs"], ai["answered"], ai["no_provider"], used), ""]
    rerun = info.get("rerun")
    if rerun is not None:
        if rerun:
            out += ["**Prove passate solo al secondo tentativo (test instabili o guasti di GitHub/Arch):** %d."
                    % len(rerun)]
            out += ["- %s su `%s`: %s" % (w, b, ", ".join(j)[:160]) for w, b, j in rerun[:10]]
        else:
            out.append("**Prove passate solo al secondo tentativo:** nessuna.")
        out.append("")
    state = info.get("main")
    if state is not None:
        out += ["**`main` adesso:** " + (", ".join("%s %s" % (k, "verde" if v == "success" else "ROSSO (%s)" % v)
                                                  for k, v in sorted(state.items())) or "nessuna prova letta"), ""]
    if info.get("missing"):
        out += ["Non letto questa volta: %s." % ", ".join(info["missing"]), ""]
    return "\n".join(out).rstrip() + "\n"


def publish(repo, body):
    found = json.loads(subprocess.run(["gh", "issue", "list", "--repo", repo, "--label", LABEL, "--state", "open",
                                       "--json", "number,title"], capture_output=True, text=True,
                                      check=False).stdout or "[]")
    number = next((i["number"] for i in found if i.get("title") == TITLE), None)
    if number:
        subprocess.run(["gh", "issue", "edit", str(number), "--repo", repo, "--body", body], check=True)
        return number
    subprocess.run(["gh", "label", "create", LABEL, "--repo", repo, "--color", "0e8a16", "--description",
                    "AUTOMAT's weekly scoreboard"], capture_output=True, check=False)
    subprocess.run(["gh", "issue", "create", "--repo", repo, "--title", TITLE, "--label", LABEL, "--body", body],
                   check=True)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    body = text(gather(a.repo))
    print(body)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write("### %s\n\n%s" % (TITLE, body))
    if not a.dry_run:
        publish(a.repo, body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
