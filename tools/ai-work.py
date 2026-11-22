#!/usr/bin/env python3
"""The AI work of the maintenance in the ledger: queued, started, waiting for a free provider (WP8, WP9).

No AI here. Two kinds of work live in the maintenance ledger
(tools/maintenance-ledger.py, its issue "Maintenance ledger"):

- "filter-list": each finding of the filter lists, classified by
  tools/filter-lists.py, becomes one entry, once (key
  ``lists/<rule>/<detail>@<class>``). Supported and harmless
  ones are "passed" at once; "needs a person" ones (YouTube, uBlock Origin's
  own resources, a list that is not a list) and those no AI may touch are
  "needs-person"; breaking and security findings about the syntax of rules or
  an unknown scriptlet are queued ("detected") for an AI analysis on an
  isolated branch, automation/update/lists-<date>: one at a time, the most
  severe first;
- "ai-work": an automatic fix (autofix.yml) that found no free provider at
  all (every one busy, out of quota or not free): it waits here.

Work that found no free provider is "retry-later": its branch and its
attempts are kept, and the daily check starts it again after RETRY_HOURS
(tools/ai-providers.py). After RETRY_CAP such tries it is "needs-person" and
the owner is told once (a comment naming the owner on the ledger issue);
before that, nobody is asked.

What each run of autofix.yml did comes back as a small artifact
(``ai-work-outcome-<job>``: work, outcome, url): published (a branch and a
pull request: "testing"), deferred (no provider: "retry-later"), person (the
AI could not, or a guard refused: "needs-person"), skipped (nothing to do any
more: "passed"). A fix of a lists branch after its tests failed (work
``run/<id>``, planned by tools/autofix-plan.py) counts for that finding's
entry, by its branch: published keeps it "testing" from the new change,
person makes it "needs-person".

    ai-work.py gather --repo OWNER/NAME --out work.json [--lists lists.json] [--run-id ID]
        GET calls only: the outcomes of the last days' autofix runs, and today's lists report
    ai-work.py dispatch --ledger ledger.json [--repo OWNER/NAME] [--dry-run]
        starts autofix.yml for each work the ledger made due today (job ai-work of daily-check.yml,
        whose only permission starts workflows)
    ai-work.py notify --ledger ledger.json [--repo OWNER/NAME] [--dry-run]
        tells the owner once about work that reached the cap (one comment on the ledger issue)
"""

import argparse
import datetime as dt
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import time
import zipfile
from pathlib import Path

WORK_KINDS = ("filter-list", "ai-work")
OUTCOMES = ("published", "deferred", "person", "skipped")
OUTCOME_ARTIFACTS = ("ai-work-outcome-plan", "ai-work-outcome-fix", "ai-work-outcome-publish",
                     "ai-work-outcome-report")
OUTCOME_DAYS = 3               # autofix runs looked at
STUCK_HOURS = 30               # a started work that never reported back is started again (counts as a try)
TESTING_DAYS = 7               # a published lists branch whose finding is still there after this: a person
SEEN_DAYS = 14                 # a finding not reported for this long is forgotten (it may come back as new)
MAX_LIST_WORK = 1              # lists analyses running at the same time
SEVERITY = {"security": 0, "breaking": 1}
WORK_ID = re.compile(r"^(lists/\d{4}-\d\d-\d\d/lists/[a-z-]+/[a-z0-9.-]+@[a-z]+|run/\d{1,20})$")
BOT = "github-actions[bot]"


def _tool(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"),
                                                  Path(__file__).resolve().parent / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


REGISTRY = _tool("ai-providers")


def stamp(when):
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_time(text):
    try:
        return dt.datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError:
        return None


def _entry(key, name, kind, now, run_url=""):
    """A ledger entry, small: the issue holds every one of them (the rules
    themselves stay in the daily check's artifact filter-lists)."""
    e = {"key": key, "component": key.split("@", 1)[0], "name": name, "kind": kind, "from": "", "to":
         key.split("@", 1)[1], "state": "", "reason": "", "attempts": 1, "first_seen": stamp(now),
         "last_seen": stamp(now), "history": []}
    if run_url:
        e["last_run"] = run_url
    return e


CLASS_SHORT = {"supported": "supported", "harmless": "unsupported but harmless",
               "breaking": "breaking incompatibility", "security": "possible security regression",
               "person": "needs a person"}


def _first_state(f):
    """(state, reason) of a new finding; the rule's reason is in docs/MAINTENANCE.md."""
    cls = CLASS_SHORT[f["class"]]
    if f["class"] in ("supported", "harmless"):
        return "passed", cls
    if f["class"] == "person" or f["youtube"]:
        return "needs-person", "%s (rule %s)" % (cls, f["rule"])
    if f["ai"]:
        return "detected", "%s: queued for an AI analysis" % cls
    return "retrying", ("%s (rule %s): the engine drops the rule as today; it goes with a new engine (its own "
                        "candidate), and the lists check looks again every day" % (cls, f["rule"]))


def _short_list(name):
    return name.replace("uBlock filters - ", "uBO ").replace("uBlock filters", "uBO filters")


def _work(e):
    return e.setdefault("work", {"branch": "", "retries": 0, "started": "", "date": ""})


def _dispatch(e, work_id, run_id, now, set_state, why):
    w = _work(e)
    w["started"] = stamp(now)
    w["id"] = work_id
    set_state(e, "fixing", why, now)
    return {"key": e["key"], "run_id": str(run_id), "work": work_id}


def _defer(e, now, set_state, why, cap, notify, what="no free AI provider"):
    """The work could not be done today (no free provider, or the AI could not, or a check refused its
    change): "retrying", started again after RETRY_HOURS with another provider first, as many times
    as it takes (2026-11-22: nothing is given up). After `cap` tries the owner gets one informational
    note; the work goes on all the same."""
    w = _work(e)
    w["retries"] = w.get("retries", 0) + 1
    set_state(e, "retrying", "%s (%s): tried again after %d hours, try %d" % (
        what, why, REGISTRY.RETRY_HOURS, w["retries"]), now)
    e["retries"] = w["retries"]
    e["next_retry"] = stamp(now + dt.timedelta(hours=REGISTRY.RETRY_HOURS))
    if w["retries"] >= cap and not e.get("told"):
        e["told"] = stamp(now)
        notify.append(e["key"])


LISTS_BRANCH = re.compile(r"^automation/update/lists-\d{4}-\d\d-\d\d$")


def _lists_entries(entries, branch):
    """The open filter-list entries whose analysis works on this lists branch."""
    if not LISTS_BRANCH.match(branch or ""):
        return []
    return [e for e in entries.values() if e.get("kind") == "filter-list" and e.get("state") != "passed"
            and (e.get("work") or {}).get("branch") == branch]


def _retry_outcome(e, out, what, now, set_state):
    """A fix of the lists branch after its tests failed: still "testing" with the new change (the days
    of TESTING_DAYS count again from it), or "needs-person" (the cap, or the AI or the checks could
    not; the report's issue tells the owner)."""
    e["last_seen"] = stamp(now)
    if out.get("url"):
        e["last_run"] = out["url"]
    branch = out.get("branch") or "its branch"
    if what == "published":
        set_state(e, "testing", "a new automatic fix after its tests failed is on %s%s (run %s): its tests "
                  "decide, then the owner" % (branch, " (PR #%s)" % out["pr"] if out.get("pr") else "",
                                              out.get("run") or "?"), now)
    else:
        reason = str(out.get("reason") or "")[:160]
        set_state(e, "retrying", "the automatic fix after its tests failed on %s could not make them pass today%s: "
                  "it tries again every day, the engine drops the rule until then"
                  % (branch, ": " + reason if reason else ""), now)


def merge(ledger, work, now, set_state, cap=None):
    """Today's AI work into the ledger (returns it). Pure: no network.

    work: {"run_id", "run_url", "lists": the lists report or None, "outcomes":
    [{"work", "outcome", "url", "created", "run", "reason", "pr"}]}. Writes
    ledger["dispatch"] (work to start today) and ledger["notify"] (keys the
    owner is told about today)."""
    cap = REGISTRY.RETRY_CAP if cap is None else cap
    work = work or {}
    entries = ledger.setdefault("entries", {})
    seen = ledger.setdefault("lists_seen", {})          # finding -> day last reported (once: never added again)
    done = ledger.get("outcomes_seen")
    done = done if isinstance(done, dict) else {}       # outcome -> day read
    dispatch, notify = [], []
    run_id = str(work.get("run_id") or "")

    # 1. what the autofix runs did (each run's outcome once, oldest first)
    for out in sorted(work.get("outcomes") or [], key=lambda o: o.get("created", "")):
        wid, what = out.get("work", ""), out.get("outcome")
        mark = "%s:%s" % (out.get("run", ""), out.get("artifact", what))
        if not WORK_ID.match(wid or "") or what not in OUTCOMES or mark in done:
            continue
        done[mark] = stamp(now)[:10]
        if wid.startswith("lists/"):
            key = wid.split("/", 2)[2]
            e = entries.get(key)
        else:
            key = "ai-work/%s@retry" % wid.split("/", 1)[1]
            e = entries.get(key)
            if e is None and what in ("published", "person"):
                # a fix of a filter lists' branch after its tests failed (tools/autofix-plan.py):
                # it belongs to that finding's entry
                lists_e = _lists_entries(entries, out.get("branch"))
                for le in lists_e:
                    _retry_outcome(le, out, what, now, set_state)
                if lists_e:
                    continue
            if e is None and what in ("deferred", "person"):
                e = entries[key] = _entry(key, "Automatic fix of \"%s\" (run %s)" % (
                    out.get("workflow") or "?", wid.split("/", 1)[1]), "ai-work", now, out.get("url", ""))
                e["work"] = {"branch": out.get("branch", ""), "retries": 0, "started": "", "id": wid}
        if e is None:
            continue
        e["last_seen"] = stamp(now)
        if out.get("url"):
            e["last_run"] = out["url"]
        reason = str(out.get("reason") or "")[:160]
        if what == "deferred":
            _defer(e, now, set_state, reason or "every provider busy, out of quota or not free", cap, notify)
        elif what == "published":
            _work(e)["branch"] = out.get("branch") or _work(e).get("branch", "")
            set_state(e, "testing" if e["kind"] == "filter-list" else "passed",
                      "the AI's change is on %s%s: its tests decide, then the owner" % (
                          out.get("branch") or "its branch", " (PR #%s)" % out["pr"] if out.get("pr") else ""), now)
        elif what == "person":
            _defer(e, now, set_state, reason or "see its run", cap, notify,
                   what="the AI could not do it today, or the checks refused its change")
        else:
            set_state(e, "passed", "nothing to do any more: %s" % (reason or "the plan skipped it"), now)
    old = (now - dt.timedelta(days=OUTCOME_DAYS + 1)).strftime("%Y-%m-%d")
    ledger["outcomes_seen"] = {k: d for k, d in done.items() if d >= old}

    # 2. today's filter-list findings: each one an entry, once
    lists = work.get("lists")
    if lists is not None and any(r.get("state") == "ok" for r in lists.get("lists", [])):
        fl = _tool("filter-lists")
        result = fl.classify(lists, ledger.get("lists_baseline"))
        ledger["lists_baseline"] = result["shares"]
        today = set()
        for f in result["findings"]:
            key = f["key"]
            today.add(key)
            known = key in seen
            seen[key] = stamp(now)[:10]
            e = entries.get(key)
            if e is None:
                if known:
                    continue                  # already had its entry (since pruned or folded): once
                e = entries[key] = _entry(key, "Filter lists: %s (%s)" % (str(f["detail"])[:60], f["rule"]),
                                          "filter-list", now)
                e["ai"] = f["ai"]                 # the class is the entry's "to" (its key ends in it)
                if f["youtube"]:
                    e["youtube"] = True
                set_state(e, *_first_state(f), now)
            # one entry per group: its count, the lists concerned and at most three
            # sample rules (all the rules: the artifact filter-lists of the run)
            e["last_seen"] = stamp(now)
            e["from"] = "%d rules" % f["count"]
            if e["state"] != "passed":         # a finished one needs no more than its count
                e["lists"] = ", ".join(_short_list(n) for n in f["lists"])[:90]
                e["samples"] = [x["rule"][:80] for x in f["examples"][:3]]
            else:
                e.pop("lists", None)
                e.pop("samples", None)
        for key, e in entries.items():
            branch = (e.get("work") or {}).get("branch")
            if e.get("kind") == "filter-list" and key not in today and e["state"] != "passed":
                set_state(e, "passed", "no longer reported by the lists check%s" % (
                    " (the AI's change on %s, or the lists changed)" % branch if branch else ""), now)
        limit = (now - dt.timedelta(days=SEEN_DAYS)).strftime("%Y-%m-%d")
        for key in [k for k, day in seen.items() if day[:10] < limit]:
            del seen[key]

    # 3. work in flight: started but silent, published but still found, waiting for a provider
    for e in entries.values():
        if e.get("kind") not in WORK_KINDS:
            continue
        if e["state"] not in ("passed",):
            e["last_seen"] = stamp(now) if e.get("kind") == "ai-work" else e["last_seen"]
        w = e.get("work") or {}
        started = parse_time(w.get("started") or "")
        if e["state"] == "fixing" and started and now - started > dt.timedelta(hours=STUCK_HOURS):
            _defer(e, now, set_state, "the run did not report back", cap, notify)
        elif e["state"] == "testing" and now - (parse_time(e.get("changed") or "") or now) > \
                dt.timedelta(days=TESTING_DAYS):
            set_state(e, "retrying", "the AI's change on %s is not in main after %d days: its branch keeps being "
                      "fixed and judged every day (the next finding does not wait for it)"
                      % (w.get("branch") or "its branch", TESTING_DAYS), now)
        elif e["state"] in ("retry-later", "retrying") and e.get("next_retry") and \
                (parse_time(e.get("next_retry") or "") or now) <= now:
            wid = w.get("id") or ""
            if e["kind"] == "ai-work" and wid.startswith("run/"):
                dispatch.append(_dispatch(e, wid, wid.split("/", 1)[1], now, set_state,
                                          "started again: a free provider may answer now (try %d of %d)"
                                          % (w.get("retries", 0) + 1, cap)))
            elif e["kind"] == "filter-list" and run_id and wid.startswith("lists/") and \
                    ledger.get("lists_started") != stamp(now)[:10]:
                ledger["lists_started"] = stamp(now)[:10]
                dispatch.append(_dispatch(e, wid, run_id, now, set_state,
                                          "AI analysis started again on %s (try %d of %d)"
                                          % (w.get("branch"), w.get("retries", 0) + 1, cap)))

    # 4. a new lists analysis: the most severe queued finding, one at a time (one that
    # waits for a free provider counts: a new one would only wait too)
    busy = sum(1 for e in entries.values() if e.get("kind") == "filter-list"
               and e["state"] in ("fixing", "testing", "retry-later"))
    queued = sorted((e for e in entries.values() if e.get("kind") == "filter-list" and e["state"] == "detected"
                     and e.get("ai") and not e.get("youtube")),
                    key=lambda e: (SEVERITY.get(e["to"], 9), e["first_seen"], e["key"]))
    if ledger.get("lists_started") == stamp(now)[:10]:
        busy = MAX_LIST_WORK                  # at most one analysis started a day
    for e in queued[:max(0, MAX_LIST_WORK - busy)] if run_id else []:
        date = now.strftime("%Y-%m-%d")
        ledger["lists_started"] = date
        w = _work(e)
        if not w.get("branch"):
            w["branch"], w["date"] = "automation/update/lists-%s" % date, date
        wid = "lists/%s/%s" % (w["date"], e["key"])
        dispatch.append(_dispatch(e, wid, run_id, now, set_state,
                                  "an AI analysis of I.K.E.'s adapter works on it on %s" % w["branch"]))
    ledger["dispatch"] = dispatch
    ledger["notify"] = notify
    return ledger


# --- GitHub --------------------------------------------------------------------------------

def gh_api(path, raw=False, method="GET", data=None):
    cmd = ["gh", "api", "-X", method, path]
    if data is not None:
        cmd += ["--input", "-"]
    for n in range(3):
        out = subprocess.run(cmd, input=json.dumps(data).encode() if data is not None else None,
                             capture_output=True, check=False)
        if not out.returncode:
            break
        time.sleep(5 * (n + 1))
    if out.returncode:
        raise RuntimeError("gh api %s: %s" % (path, out.stderr.decode("utf-8", "replace").strip()[:200]))
    return out.stdout if raw else (json.loads(out.stdout) if out.stdout.strip() else {})


def gather(repo, api=gh_api, now=None):
    """The outcomes the autofix runs of the last OUTCOME_DAYS days left (GET only)."""
    now = now or dt.datetime.now(dt.timezone.utc)
    out = []
    for name in OUTCOME_ARTIFACTS:
        arts = api("repos/%s/actions/artifacts?name=%s&per_page=50" % (repo, name)).get("artifacts", [])
        for art in arts:
            made = parse_time(art.get("created_at") or "")
            if art.get("expired") or not made or now - made > dt.timedelta(days=OUTCOME_DAYS):
                continue
            try:
                data = api("repos/%s/actions/artifacts/%s/zip" % (repo, art["id"]), raw=True)
                with zipfile.ZipFile(io.BytesIO(data)) as z:
                    info = json.loads(z.read(z.namelist()[0]).decode("utf-8"))
            except Exception as e:
                print("::warning::an outcome of the AI work could not be read: %s" % str(e)[:160].replace("::", ": "))
                continue
            if not isinstance(info, dict):
                continue
            info.update(run=str((art.get("workflow_run") or {}).get("id", "")), created=art.get("created_at", ""),
                        artifact=name)
            out.append(info)
    return out


def dispatch(ledger, repo, run=subprocess.run, dry_run=False):
    started = []
    for d in ledger.get("dispatch") or []:
        if not WORK_ID.match(d.get("work") or "") or not re.match(r"^\d{1,20}$", d.get("run_id") or ""):
            continue
        cmd = ["gh", "workflow", "run", "autofix.yml", "--repo", repo, "--ref", "main",
               "-f", "run_id=%s" % d["run_id"], "-f", "work=%s" % d["work"]]
        if dry_run:
            print(" ".join(cmd))
            started.append(d["work"])
            continue
        out = run(cmd, capture_output=True, text=True, check=False)
        if out.returncode:
            print("::warning::%s not started: %s" % (d["work"], out.stderr.strip()[:200].replace("::", ": ")))
            continue          # the ledger finds it silent after STUCK_HOURS and starts it again
        started.append(d["work"])
    return started


def notify_text(ledger, owner):
    keys = ledger.get("notify") or []
    if not keys:
        return ""
    entries = ledger.get("entries", {})
    lines = ["@%s: nota informativa, non serve fare niente. Questi lavori non sono riusciti per %d volte (nessun "
             "assistente AI gratuito libero, oppure la correzione non ha superato i controlli) e AUTOMAT (la "
             "manutenzione automatica) continua a riprovarli ogni giorno:" % (owner, REGISTRY.RETRY_CAP), ""]
    for k in keys:
        e = entries.get(k) or {}
        lines.append("- %s: %s" % (e.get("name", k), e.get("reason", "")))
    lines += ["", "Nothing is given up: each work is started again every %d hours. This note comes once, after "
              "RETRY_CAP tries (tools/ai-providers.py); the providers' weekly check is in the issue "
              "\"Automation health\"." % REGISTRY.RETRY_HOURS]
    return "\n".join(lines) + "\n"


def notify(ledger, repo, api=gh_api, dry_run=False):
    text = notify_text(ledger, repo.split("/")[0])
    if not text:
        return None
    if dry_run:
        print(text)
        return 0
    for issue in api("repos/%s/issues?state=open&labels=maintenance-ledger&per_page=20" % repo):
        if "pull_request" in issue or (issue.get("user") or {}).get("login") != BOT:
            continue
        api("repos/%s/issues/%s/comments" % (repo, issue["number"]), method="POST", data={"body": text})
        return issue["number"]
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("gather")
    g.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    g.add_argument("--out", required=True)
    g.add_argument("--lists")
    g.add_argument("--run-id", default=os.environ.get("GITHUB_RUN_ID", ""))
    for name in ("dispatch", "notify"):
        s = sub.add_parser(name)
        s.add_argument("--ledger", required=True)
        s.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
        s.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "gather":
        work = {"run_id": a.run_id, "run_url": "%s/%s/actions/runs/%s" % (
            os.environ.get("GITHUB_SERVER_URL", "https://github.com"), a.repo, a.run_id) if a.run_id else "",
            "lists": None, "outcomes": []}
        if a.lists:
            try:
                work["lists"] = json.loads(Path(a.lists).read_text("utf-8"))
            except (OSError, ValueError):
                print("::warning::no lists report today: the filter-list findings are not updated")
        try:
            work["outcomes"] = gather(a.repo)
        except Exception as e:                # GitHub did not answer: today without outcomes
            print("::warning::the outcomes of the AI work could not be read: %s" % str(e)[:200].replace("::", ": "))
        Path(a.out).write_text(json.dumps(work) + "\n", "utf-8")
        return 0
    try:
        ledger = json.loads(Path(a.ledger).read_text("utf-8"))
    except (OSError, ValueError):
        print("::warning::no ledger to read: nothing started")
        return 0
    if a.cmd == "dispatch":
        started = dispatch(ledger, a.repo, dry_run=a.dry_run)
        print("AI work started: %s" % (", ".join(started) or "none"))
        return 0
    number = notify(ledger, a.repo, dry_run=a.dry_run)
    print("owner told: %s" % ("issue #%s" % number if number else "nothing to tell"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
