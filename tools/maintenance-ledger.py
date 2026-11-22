#!/usr/bin/env python3
"""The maintenance ledger: one tracked state per component update (WP3 of the maintenance plan).

The ledger lives in one GitHub issue labelled ``maintenance-ledger``, written
only by the daily check (daily-check.yml, job ledger): a readable table and,
between two markers, a JSON block that the next run reads back. Each entry is
one update of one component, its key ``<component id>@<new version>``:

    component, kind, from -> to, state, reason, attempts, first and last seen,
    last run URL, next retry, update mode, a short history

States: detected, candidate, testing, fixing, passed, blocked, needs-person,
retry-later. The same update is never added twice (the key); a failed one
stays with its reason and is tried again when its time comes (retry-later)
or when main changes (blocked); an update that reached main is "passed", and
finished entries leave after PRUNE_DAYS. A new dependency found in the
repository (tools/inventory.py: a component id never seen before) is an entry
too: "passed" once the tests of main are green with it, "needs-person" when
the inventory says it is used but not declared.

    maintenance-ledger.py gather --repo OWNER/NAME --out status.json [--advisories FILE]
                                 [--candidate-sha SHA]
        GET calls of GitHub's API only (gh, GH_TOKEN): main's commit, the
        candidate's pull request and the runs of its commit (Tests, Arch Linux,
        Security, with their steps and the skipped tests), the last runs of
        main, the open reports of the automatic fix. --advisories writes the
        last RustSec result of main (security.yml) for tools/inventory.py.

    maintenance-ledger.py update --repo OWNER/NAME --inventory inventory.json
                                 [--candidate-inventory FILE] [--report report.json]
                                 [--status status.json] [--dry-run] [--out FILE]
        reads the ledger issue, applies today's facts, writes the issue back
        (--dry-run: only --out) and closes the automatic fix's reports whose
        failure is gone (a later run of the same branch passed every step the
        report named: issue #97, Licences, is closed by the next candidate that
        passes them).

No AI, no code of others runs here; the automatic fix may never change this
file (tools/check-autofix-patch.py).
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

SCHEMA = 1
LABEL = "maintenance-ledger"
TITLE = "Maintenance ledger"
BEGIN, END = "<!-- maintenance-ledger:begin -->", "<!-- maintenance-ledger:end -->"
STATES = ("detected", "candidate", "testing", "fixing", "passed", "blocked", "needs-person", "retry-later")
OPEN_STATES = ("detected", "candidate", "testing", "fixing", "retry-later")
BOT = "github-actions[bot]"
MAINTENANCE = "automation/daily-maintenance"
RETRY_DAYS = 1                 # retry-later: tried again the next day
MAJOR_RETRY_DAYS = 7           # a new major version cargo update cannot take: looked at again weekly
MAX_ATTEMPTS = 5               # then blocked, for a person
PRUNE_DAYS = 30                # finished entries (passed) leave the ledger after this
STALE_DAYS = 14                # an open entry no longer reported for this long leaves too
MAX_ENTRIES = 400
HISTORY = 8
MAX_BODY = 60000               # GitHub's limit is 65536 characters
CANDIDATE_KINDS = ("crate", "adblock-engine", "pypi-test", "pypi-ci", "integrated", "npm")
ARCH_KINDS = ("arch-package", "arch-optional", "arch-build")
PROPOSAL_KINDS = ("github-action", "ci-tool", "node", "ci-runtime")
# the automatic fix's reports this ledger may close (tools/autofix-plan.py's titles)
REPORT_WORKFLOWS = ("Tests",)
FAILED_STEP = re.compile(r"^## Job `([^`]+)` \(failed step: ([^)]*)\)", re.M)


def _tool(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), Path(__file__).resolve().parent /
                                                  (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def utcnow():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def stamp(when):
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_time(text):
    try:
        return dt.datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError:
        return None


def vkey(version):
    return tuple(int(n) for n in re.findall(r"\d+", str(version or "")))


# --- the ledger itself (no network) -------------------------------------------------

def empty():
    return {"schema": SCHEMA, "updated": "", "main": "", "known": {}, "entries": {}}


def parse_body(body):
    """The ledger in an issue body, or None when there is none or it is not valid (never trusted
    blindly: unknown states and fields of the wrong type make it invalid)."""
    text = body or ""
    if BEGIN not in text or END not in text:
        return None
    block = text.split(BEGIN, 1)[1].split(END, 1)[0]
    m = re.search(r"```json\n(.*?)\n```", block, re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
    except ValueError:
        return None
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        return None
    if not isinstance(data.get("entries"), dict) or not isinstance(data.get("known"), dict):
        return None
    for key, e in data["entries"].items():
        if not isinstance(e, dict) or e.get("state") not in STATES or not isinstance(e.get("attempts", 0), int):
            return None
        if e.get("key") != key:
            return None
    return data


def set_state(entry, state, reason, when, run_url=None):
    """Move an entry; the history grows only when the state or the reason changes (idempotent)."""
    assert state in STATES, state
    if run_url:
        entry["last_run"] = run_url
    if entry.get("state") == state and entry.get("reason") == reason:
        return False
    # a failed update that goes into a candidate again is a new attempt
    if state in ("candidate", "testing") and entry.get("state") in ("fixing", "blocked", "retry-later",
                                                                     "needs-person"):
        entry["attempts"] = entry.get("attempts", 0) + 1
    entry["state"], entry["reason"] = state, reason
    entry["changed"] = stamp(when)
    entry.setdefault("history", []).append([stamp(when), state, reason[:200]])
    entry["history"] = entry["history"][-HISTORY:]
    if state != "retry-later":
        entry["next_retry"] = ""
    return True


def new_entry(rec, to, when, reason, state="detected", from_=None):
    key = "%s@%s" % (rec["id"], to)
    e = {"key": key, "component": rec["id"], "name": rec["name"], "kind": rec["kind"],
         "from": from_ if from_ is not None else rec.get("installed", ""), "to": to, "state": "", "reason": "",
         "attempts": 1, "first_seen": stamp(when), "last_seen": stamp(when), "last_run": "", "next_retry": "",
         "update_mode": rec.get("update_mode", ""), "basis": "", "history": []}
    set_state(e, state, reason, when)
    return e


def _update_reason(rec):
    kind = rec["kind"]
    if kind in ARCH_KINDS:
        return "Arch changed since the last green arch.yml run on main: the daily check starts arch.yml on main"
    if kind == "github-action":
        return ("workflow file: changed only as a proposal a person reads (Dependabot's monthly pull request for "
                "the actions)")
    if kind in PROPOSAL_KINDS:
        return "workflow file: changed only as a proposal a person reads (the version is pinned in the workflow)"
    if rec.get("result") == "builder refused":
        return "I.K.E.'s builder refused the new version: a person adapts it (components issue)"
    if rec.get("result") == "vulnerable":
        return "a RustSec advisory: a fix on an isolated branch, or blocked (Security, Rust advisories issue)"
    if str(rec.get("compatibility", "")).startswith("major update"):
        return "a new major version: cargo update cannot take it; it comes with the crate that uses it"
    return "newer version: goes into the daily candidate (automation/daily-maintenance)"


def _first_state(rec):
    if rec["kind"] in PROPOSAL_KINDS or rec.get("result") == "builder refused":
        return "needs-person"
    if rec.get("result") == "vulnerable":
        return "blocked"
    if str(rec.get("compatibility", "")).startswith("major update"):
        return "retry-later"
    return "detected"


UPDATE_RESULTS = ("update available", "changed since last tested", "builder refused", "vulnerable")


def _candidate_verdict(status, kinds):
    """(state, reason, run url) of the candidate's tests for components of these kinds, or None
    when there is no candidate."""
    cand = (status or {}).get("candidate") or {}
    if not cand.get("sha"):
        return None
    tc = _tool("test-categories")
    runs = cand.get("runs") or {}
    required = tc.required_for(kinds)
    rows = tc.verify(required, tc.results_from_runs(runs), cand.get("skips"))
    url = ((runs.get("tests.yml") or {}).get("url") or cand.get("url") or "")
    failed = [r["category"] for r in rows if r["state"] == "failed"]
    waiting = [r["category"] for r in rows if r["state"] == "not verified"
               and r["detail"] in ("still running", "still queued")]
    unverified = [r for r in rows if r["state"] == "not verified" and r["category"] not in waiting]
    if not (runs.get("tests.yml") or {}).get("status"):
        return "candidate", "in the candidate (PR #%s); its tests have not run yet" % cand.get("pr", "?"), url
    if failed:
        if cand.get("autofix_issue"):
            return ("needs-person", "the candidate's tests fail (%s) and the automatic fix could not fix them: %s"
                    % (", ".join(failed), cand["autofix_issue"]), url)
        return ("fixing", "the candidate's tests fail (%s): the automatic fix works on it (%d fixes so far)"
                % (", ".join(failed), cand.get("autofix_commits", 0)), url)
    if waiting:
        return "testing", "the candidate's checks are running (%s)" % ", ".join(waiting), url
    if unverified:
        return ("needs-person", "the candidate's checks passed, but not verified: %s"
                % "; ".join("%s (%s)" % (r["category"], r["detail"]) for r in unverified), url)
    return "passed", "the candidate passed every required check: waits for the owner's merge (PR #%s)" \
        % cand.get("pr", "?"), url


def update(ledger, inv, status=None, report=None, cand_inv=None, now=None):
    """Today's facts into the ledger (returns it). Pure: no network."""
    now = now or utcnow()
    ledger = ledger if isinstance(ledger, dict) and ledger.get("schema") == SCHEMA else empty()
    entries, known = ledger["entries"], ledger["known"]
    first_run = not known
    records = {r["id"]: r for r in inv.get("components", [])}
    findings = {}
    for f in inv.get("findings", []):
        findings.setdefault(f["component"], []).append(f)
    main_sha = (status or {}).get("main_sha", "")
    cand_installed = {r["id"]: r.get("installed") for r in (cand_inv or {}).get("components", [])}

    # 1. new dependencies (a component id never seen) and changes of what main uses
    for rid, rec in records.items():
        inst = rec.get("installed", "")
        if rid not in known and not first_run:
            e = entries.get("%s@%s" % (rid, inst))
            if e is None:
                found = findings.get(rid)
                reason = ("new in the repository (%s): %s" % (", ".join(rec["origin"][:3]),
                                                             "; ".join(f["detail"] for f in found))
                          if found else "new in the repository (%s): waits for the tests of main"
                          % ", ".join(rec["origin"][:3]))
                e = new_entry(rec, inst, now, reason, "needs-person" if found else "detected", from_="(new)")
                e["new_dependency"] = True
                entries[e["key"]] = e
        elif rid in known and known[rid] != inst:
            # main moved to another version: the matching update reached main, older ones are moot
            for key in [k for k, e in entries.items() if e["component"] == rid and not e.get("new_dependency")]:
                e = entries[key]
                if e["to"] == inst:
                    set_state(e, "passed", "in main since %s" % stamp(now)[:10], now)
                    e["via"] = "main"
                elif e["state"] != "passed" and vkey(e["to"]) and vkey(e["to"]) <= vkey(inst):
                    del entries[key]
    # a new dependency is passed once main's tests are green with it
    tests_main = (status or {}).get("main_tests") or {}
    for e in entries.values():
        if e.get("new_dependency") and e["state"] == "detected" and e["component"] in records:
            if tests_main.get("conclusion") == "success" and parse_time(tests_main.get("created_at")) and \
                    parse_time(tests_main["created_at"]) >= parse_time(e["first_seen"]):
                set_state(e, "passed", "the tests of main are green with it (%s)" % str(tests_main.get("sha"))[:10],
                          now, tests_main.get("url"))
        if e.get("new_dependency") and e["state"] == "needs-person" and e["component"] in records \
                and e["component"] not in findings:
            set_state(e, "detected", "the inventory's finding is gone: waits for the tests of main", now)

    # 2. updates: one entry per component and new version
    seen = set()
    for rid, rec in records.items():
        if rec.get("result") not in UPDATE_RESULTS:
            continue
        to = str(rec.get("available") or "")
        if not to or to.startswith(("unknown", "not checked")):
            continue
        key = "%s@%s" % (rid, to)
        seen.add(key)
        e = entries.get(key)
        if e is None:
            e = entries[key] = new_entry(rec, to, now, _update_reason(rec), _first_state(rec))
            if e["state"] == "retry-later":
                e["next_retry"] = stamp(now + dt.timedelta(days=MAJOR_RETRY_DAYS))
        e["last_seen"] = stamp(now)
        e["from"] = rec.get("installed", e["from"])
        # today's facts that decide by themselves
        if rec.get("result") == "builder refused":
            set_state(e, "needs-person", _update_reason(rec), now)
        elif rec.get("result") == "vulnerable":
            set_state(e, "blocked", _update_reason(rec), now)

    # 3. source unreachable today (tools/check-components.py): those components wait for tomorrow
    for comp in (report or {}).get("components", []):
        if not comp.get("error"):
            continue
        for e in entries.values():
            if e["state"] in OPEN_STATES and comp.get("name", "").startswith(e["name"]):
                set_state(e, "retry-later", "source unreachable today: %s" % comp["error"][:160], now)
                e["next_retry"] = stamp(now + dt.timedelta(days=RETRY_DAYS))

    # 4. retries that are due, and failures to try again because main changed
    for e in entries.values():
        due = parse_time(e.get("next_retry") or "")
        if e["state"] == "retry-later" and due and due <= now:
            if e.get("attempts", 1) >= MAX_ATTEMPTS:
                set_state(e, "blocked", "tried %d times: a person looks (last: %s)" % (e["attempts"], e["reason"]),
                          now)
            else:
                e["attempts"] = e.get("attempts", 1) + 1
                set_state(e, "detected", "tried again (attempt %d)" % e["attempts"], now)
        elif e["state"] == "blocked" and main_sha and e.get("basis") and e["basis"] != main_sha \
                and e.get("attempts", 1) < MAX_ATTEMPTS and e["kind"] in CANDIDATE_KINDS \
                and e["key"] in seen and records.get(e["component"], {}).get("result") != "vulnerable":
            e["attempts"] = e.get("attempts", 1) + 1
            set_state(e, "detected", "main changed since it was blocked: tried again (attempt %d)" % e["attempts"],
                      now)

    # 5. the candidate flow: updates the candidate carries, and the result of its checks
    # (an entry the candidate's checks decided is decided again by today's checks)
    by_kind = {}
    for e in entries.values():
        moving = e["state"] in ("detected", "candidate", "testing", "fixing") or e.get("via") == "candidate"
        if moving and e["kind"] in CANDIDATE_KINDS and not e.get("new_dependency") \
                and cand_installed.get(e["component"]) == e["to"]:
            by_kind.setdefault(e["kind"], []).append(e)
    if by_kind:
        verdict = _candidate_verdict(status, sorted(by_kind))
        if verdict:
            state, reason, url = verdict
            for group in by_kind.values():
                for e in group:
                    set_state(e, state, reason, now, url)
                    e["via"] = "candidate"

    # 6. Arch: arch.yml on main after the change was seen
    arch = (status or {}).get("arch_main") or {}
    for e in entries.values():
        if e["kind"] not in ARCH_KINDS or e["state"] not in ("detected", "testing", "fixing"):
            continue
        rec = records.get(e["component"]) or {}
        if rec.get("installed") == e["to"]:
            set_state(e, "passed", "the last green arch.yml run on main tested it", now)
            continue
        started = parse_time(arch.get("created_at") or "")
        if not started or started < parse_time(e["first_seen"]) - dt.timedelta(hours=2):
            continue
        if arch.get("status") != "completed":
            set_state(e, "testing", "arch.yml runs on main with it", now, arch.get("url"))
        elif arch.get("conclusion") == "success":
            set_state(e, "passed", "arch.yml passed on main with it", now, arch.get("url"))
        elif arch.get("conclusion") == "failure":
            set_state(e, "fixing", "arch.yml failed on main: the automatic fix looks at it (an issue when it "
                      "cannot)", now, arch.get("url"))

    # 7. what blocked is tied to main's commit of today; old entries leave
    for key in list(entries):
        e = entries[key]
        if e["state"] in ("blocked", "needs-person") and not e.get("basis"):
            e["basis"] = main_sha
        elif e["state"] not in ("blocked", "needs-person"):
            e["basis"] = ""
        changed = parse_time(e.get("changed") or e["first_seen"]) or now
        last = parse_time(e.get("last_seen") or e["first_seen"]) or now
        if e["state"] == "passed" and now - changed > dt.timedelta(days=PRUNE_DAYS):
            del entries[key]
        elif e["state"] in OPEN_STATES and not e.get("new_dependency") and key not in seen \
                and now - last > dt.timedelta(days=STALE_DAYS):
            del entries[key]
    if len(entries) > MAX_ENTRIES:
        for key in sorted(entries, key=lambda k: entries[k].get("changed", ""))[:len(entries) - MAX_ENTRIES]:
            del entries[key]

    ledger["known"] = {rid: rec.get("installed", "") for rid, rec in sorted(records.items())}
    ledger["main"] = main_sha or ledger.get("main", "")
    ledger["updated"] = stamp(now)
    return ledger


# --- the issue body -----------------------------------------------------------------------

def _md(text):
    return str(text or "").replace("|", "\\|").replace("\n", " ")


def render(ledger, inv=None, closed=()):
    entries = sorted(ledger["entries"].values(), key=lambda e: (STATES.index(e["state"]), e["key"]))
    open_ = [e for e in entries if e["state"] != "passed"]
    done = [e for e in entries if e["state"] == "passed"]
    people = sum(e["state"] in ("needs-person", "blocked") for e in entries)
    out = ["Registro della manutenzione, scritto ogni giorno dal controllo dei componenti%s." % (
        ": %d aggiornamenti aspettano una persona" % people if people else ""), "",
        "# %s" % TITLE, "",
        "Updated %s UTC by the daily check (`tools/maintenance-ledger.py`), main at `%s`. One entry per update of "
        "one component; the same update is never added twice. States: %s." % (
            ledger["updated"][:16].replace("T", " "), (ledger.get("main") or "?")[:10], ", ".join(STATES)), ""]
    head = "| Component | From → to | State | Reason | Attempts | Last run | Next retry |\n|---|---|---|---|---|---|---|"
    out += ["## Open (%d)" % len(open_), ""]
    if open_:
        out.append(head)
        out += ["| %s | %s → %s | **%s** | %s | %d | %s | %s |" % (
            _md(e["name"]), _md(e["from"]), _md(e["to"]), e["state"], _md(e["reason"]), e.get("attempts", 1),
            "[run](%s)" % e["last_run"] if e.get("last_run") else "-", (e.get("next_retry") or "-")[:10])
            for e in open_]
    else:
        out.append("Nothing open.")
    out += ["", "## Finished, last %d days (%d)" % (PRUNE_DAYS, len(done)), ""]
    if done:
        out.append(head)
        out += ["| %s | %s → %s | %s | %s | %d | %s | - |" % (
            _md(e["name"]), _md(e["from"]), _md(e["to"]), e["state"], _md(e["reason"]), e.get("attempts", 1),
            "[run](%s)" % e["last_run"] if e.get("last_run") else "-") for e in done]
    else:
        out.append("None.")
    if inv:
        out += ["", "## Inventory", "", "%d components (%s). Findings: %s." % (
            inv.get("total", 0), ", ".join("%s %d" % kv for kv in inv.get("counts", {}).items()),
            "; ".join("%s `%s`" % (f["finding"], f["component"]) for f in inv.get("findings", [])) or "none")]
    if closed:
        out += ["", "Reports closed today because their failure is gone: %s." % ", ".join("#%s" % n for n in closed)]
    data = json.dumps(ledger, indent=0, sort_keys=True)
    out += ["", "<details><summary>Machine-readable state (read back by the next daily check)</summary>", "",
            BEGIN, "```json", data, "```", END, "", "</details>", ""]
    text = "\n".join(out)
    if len(text) > MAX_BODY:            # the history goes first, then the oldest finished entries
        slim = json.loads(json.dumps(ledger))
        for e in slim["entries"].values():
            e["history"] = e.get("history", [])[-2:]
        for key in sorted((k for k, e in slim["entries"].items() if e["state"] == "passed"),
                          key=lambda k: slim["entries"][k].get("changed", "")):
            if len(json.dumps(slim)) < MAX_BODY // 2:
                break
            del slim["entries"][key]
        if slim != ledger:
            return render(slim, inv, closed)
    return text


# --- the automatic fix's reports whose failure is gone ---------------------------------------

def report_steps(texts):
    """{job: [failed steps]} named by the report job's "## Job `x` (failed step: a, b)" lines."""
    out = {}
    for text in texts:
        for m in FAILED_STEP.finditer(text or ""):
            steps = [s.strip() for s in m.group(2).split(",") if s.strip() and s.strip() != "?"]
            out.setdefault(m.group(1), [])
            out[m.group(1)] += [s for s in steps if s not in out[m.group(1)]]
    return out


def finished_reports(reports, runs):
    """[(issue number, comment)] for reports to close.

    reports: [{"number", "title", "workflow", "marks": [(sha, branch)], "steps": {job: [steps]},
    "reported_at"}]; runs: {branch: the newest finished run of that workflow, {"head_sha", "created_at",
    "url", "conclusion", "jobs": {job: {"steps": {step: result}}}}}. A report is closed when, on every
    branch its marks name, a run of a later commit, started after the latest report, passed every
    step the report named as failed (with none named: the whole run passed)."""
    out = []
    for rep in reports:
        marks = [(s, b) for s, b in rep.get("marks", []) if s and b]
        if not marks:
            continue
        shas = {s for s, _ in marks}
        ok, where = True, []
        for branch in sorted({b for _, b in marks}):
            run = (runs or {}).get(rep.get("workflow", "Tests"), {}).get(branch)
            if not run or any(run.get("head_sha", "").startswith(s) or s.startswith(run.get("head_sha", "x"))
                              for s in shas):
                ok = False
                break
            started, reported = parse_time(run.get("created_at") or ""), parse_time(rep.get("reported_at") or "")
            if not started or (reported and started <= reported):
                ok = False
                break
            steps = rep.get("steps") or {}
            if steps:
                for job, names in steps.items():
                    have = ((run.get("jobs") or {}).get(job) or {}).get("steps") or {}
                    if not names or any(have.get(n) != "success" for n in names):
                        ok = False
            elif run.get("conclusion") != "success":
                ok = False
            if not ok:
                break
            where.append("%s ([run](%s), commit `%s`)" % (branch, run.get("url", ""), run.get("head_sha", "")[:10]))
        if ok:
            named = "; ".join("%s: %s" % (j, ", ".join(s)) for j, s in (rep.get("steps") or {}).items()) \
                or "the whole run"
            out.append((rep["number"], "The failure this report is about is gone: a later run passed what had "
                        "failed (%s) on %s. Closed by the daily check (`tools/maintenance-ledger.py`); it "
                        "opens again by itself if the failure comes back." % (named, ", ".join(where))))
    return out


# --- GitHub (gh api) --------------------------------------------------------------------------

def gh_api(path, method="GET", data=None, raw=False, tries=3):
    cmd = ["gh", "api", "-X", method, path]
    payload = None
    if data is not None:
        cmd += ["--input", "-"]
        payload = json.dumps(data)
    for n in range(tries):
        out = subprocess.run(cmd, input=payload.encode() if payload else None, capture_output=True, check=False)
        if not out.returncode:
            break
        if n + 1 < tries:
            time.sleep(5 * (n + 1))
    if out.returncode:
        raise RuntimeError("gh api %s %s: %s" % (method, path, out.stderr.decode("utf-8", "replace").strip()[:300]))
    if raw:
        return out.stdout
    return json.loads(out.stdout) if out.stdout.strip() else {}


def run_info(repo, workflow, api, sha=None, branch=None, completed=False):
    """The newest run of a workflow for a commit or a branch, with its jobs and steps, or None."""
    query = "per_page=10"
    if sha:
        query += "&head_sha=%s" % sha
    if branch:
        query += "&branch=%s" % branch
    if completed:
        query += "&status=completed"
    runs = api("repos/%s/actions/workflows/%s/runs?%s" % (repo, workflow, query)).get("workflow_runs", [])
    runs = [r for r in runs if (not sha or r.get("head_sha") == sha) and (not branch or r.get("head_branch") == branch)]
    if not runs:
        return None
    run = max(runs, key=lambda r: (r.get("created_at") or "", r.get("id") or 0))
    jobs = api("repos/%s/actions/runs/%s/jobs?per_page=100" % (repo, run["id"])).get("jobs", [])
    return {"id": run["id"], "url": run.get("html_url", ""), "status": run.get("status"),
            "conclusion": run.get("conclusion"), "head_sha": run.get("head_sha", ""),
            "created_at": run.get("created_at", ""),
            "jobs": {j["name"]: {"status": j.get("status"), "conclusion": j.get("conclusion"),
                                 "steps": {s["name"]: s.get("conclusion") or "" for s in j.get("steps", [])}}
                     for j in jobs}}


def run_skips(repo, run_id, api):
    """The skipped tests a Tests run recorded (its artifact "test-results"), or None."""
    try:
        arts = api("repos/%s/actions/runs/%s/artifacts?name=test-results" % (repo, run_id)).get("artifacts", [])
        for art in arts:
            if art.get("expired"):
                continue
            data = api("repos/%s/actions/artifacts/%s/zip" % (repo, art["id"]), raw=True)
            skips = []
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                for name in z.namelist():
                    if name.endswith(".json") and z.getinfo(name).file_size < 5_000_000:
                        info = json.loads(z.read(name).decode("utf-8"))
                        skips += info.get("skips", []) if isinstance(info, dict) else []
            return skips
    except Exception as e:
        print("::warning::the skipped tests could not be read: %s" % str(e)[:200].replace("::", ": "))
    return None


def open_reports(repo, api):
    """The automatic fix's open reports this ledger may close (see finished_reports)."""
    plan = _tool("autofix-plan")
    titles = {}
    for wf in REPORT_WORKFLOWS:
        titles[plan.ISSUE_TITLE % wf] = wf
        titles[plan.INFRA_TITLE % wf] = wf
    out = []
    for issue in api("repos/%s/issues?state=open&labels=autofix&per_page=100" % repo):
        if "pull_request" in issue or issue.get("title") not in titles or \
                (issue.get("user") or {}).get("login") != BOT:
            continue
        texts, marks, reported = [issue.get("body") or ""], [], issue.get("created_at") or ""
        sha, branch = plan.report_mark(issue.get("body"))
        marks.append((sha, branch))
        for c in api("repos/%s/issues/%s/comments?per_page=100" % (repo, issue["number"])):
            if (c.get("user") or {}).get("login") != BOT:
                continue                      # only the report job's own comments count
            sha, branch = plan.report_mark(c.get("body"))
            if sha:
                marks.append((sha, branch))
                texts.append(c.get("body") or "")
                reported = max(reported, c.get("created_at") or "")
        out.append({"number": issue["number"], "title": issue["title"], "workflow": titles[issue["title"]],
                    "marks": marks, "steps": report_steps(texts), "reported_at": reported})
    return out


def gather(repo, api=None, candidate_sha=None):
    """Everything the ledger and the candidate's report need from GitHub (GET only)."""
    api = api or gh_api
    owner = repo.split("/")[0]
    status = {"repo": repo, "gathered": stamp(utcnow()), "errors": []}

    def safe(key, fn):
        try:
            status[key] = fn()
        except Exception as e:          # GitHub did not answer: that part is "not checked"
            status[key] = None
            status["errors"].append("%s: %s" % (key, str(e)[:200]))

    safe("main_sha", lambda: api("repos/%s/commits/main" % repo).get("sha", ""))

    def candidate():
        prs = api("repos/%s/pulls?state=open&head=%s:%s" % (repo, owner, MAINTENANCE))
        sha = candidate_sha or (prs[0]["head"]["sha"] if prs else "")
        if not sha:
            return {}
        cand = {"sha": sha, "pr": prs[0]["number"] if prs else "", "url": prs[0].get("html_url", "") if prs else ""}
        cand["runs"] = {wf: run_info(repo, wf, api, sha=sha) for wf in ("tests.yml", "arch.yml", "security.yml")}
        tests = cand["runs"].get("tests.yml")
        cand["skips"] = run_skips(repo, tests["id"], api) if tests and tests.get("status") == "completed" else None
        try:
            cmp = api("repos/%s/compare/main...%s" % (repo, sha))
            cand["autofix_commits"] = sum(1 for c in cmp.get("commits", [])
                                          if (c.get("commit") or {}).get("message", "").startswith("autofix:"))
        except Exception:
            cand["autofix_commits"] = 0
        return cand
    safe("candidate", candidate)
    safe("arch_main", lambda: run_info(repo, "arch.yml", api, branch="main"))
    safe("main_tests", lambda: run_info(repo, "tests.yml", api, branch="main", completed=True))
    safe("security_main", lambda: run_info(repo, "security.yml", api, branch="main", completed=True))
    safe("tests_runs", lambda: {"Tests": {b: run_info(repo, "tests.yml", api, branch=b, completed=True)
                                          for b in ("main", MAINTENANCE)}})
    safe("reports", lambda: open_reports(repo, api))
    cand = status.get("candidate") or {}
    plan_titles = []
    for rep in status.get("reports") or []:
        if any(b == MAINTENANCE and cand.get("sha", "").startswith(s) for s, b in rep["marks"] if s):
            plan_titles.append("#%s" % rep["number"])
    if cand:
        cand["autofix_issue"] = ", ".join(plan_titles)
    return status


def advisories_of(status):
    """cargo-deny's last result on main (security.yml, job rust-advisories) for tools/inventory.py."""
    sec = (status or {}).get("security_main") or {}
    job = (sec.get("jobs") or {}).get("rust-advisories")
    if not job:
        return {"state": "unknown", "url": sec.get("url", ""), "date": sec.get("created_at", "")}
    state = {"success": "clean", "failure": "found"}.get(job.get("conclusion"), "unknown")
    return {"state": state, "url": sec.get("url", ""), "date": sec.get("created_at", ""), "crates": []}


def read_ledger(repo, api):
    """(issue number or None, ledger or None): the bot's open issue labelled LABEL."""
    for issue in api("repos/%s/issues?state=open&labels=%s&per_page=20" % (repo, LABEL)):
        if "pull_request" in issue or (issue.get("user") or {}).get("login") != BOT:
            continue
        return issue["number"], parse_body(issue.get("body"))
    return None, None


def write_ledger(repo, number, body, api):
    if number:
        api("repos/%s/issues/%s" % (repo, number), method="PATCH", data={"body": body, "title": TITLE})
        return number
    try:
        api("repos/%s/labels" % repo, method="POST", data={"name": LABEL, "color": "5319e7",
                                                         "description": "The maintenance ledger (daily check)"})
    except RuntimeError:
        pass                                  # the label exists already
    return api("repos/%s/issues" % repo, method="POST", data={"title": TITLE, "body": body,
                                                            "labels": [LABEL]}).get("number")


def close_reports(repo, closing, api):
    done = []
    for number, comment in closing:
        try:
            api("repos/%s/issues/%s/comments" % (repo, number), method="POST", data={"body": comment})
            api("repos/%s/issues/%s" % (repo, number), method="PATCH",
                data={"state": "closed", "state_reason": "completed"})
            done.append(number)
        except RuntimeError as e:
            print("::warning::report #%s not closed: %s" % (number, str(e)[:200].replace("::", ": ")))
    return done


# --- command line -----------------------------------------------------------------------------

def _read(path):
    if not path:
        return None
    try:
        return json.loads(Path(path).read_text("utf-8"))
    except (OSError, ValueError):
        return None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("gather")
    g.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    g.add_argument("--out", required=True)
    g.add_argument("--advisories")
    g.add_argument("--candidate-sha")
    u = sub.add_parser("update")
    u.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    u.add_argument("--inventory", required=True)
    u.add_argument("--candidate-inventory")
    u.add_argument("--report")
    u.add_argument("--status")
    u.add_argument("--dry-run", action="store_true")
    u.add_argument("--out", help="also write the issue body here")
    u.add_argument("--json", help="also write the ledger here")
    args = ap.parse_args(argv)
    if args.cmd == "gather":
        status = gather(args.repo, candidate_sha=args.candidate_sha)
        Path(args.out).write_text(json.dumps(status, indent=1) + "\n", "utf-8")
        if args.advisories:
            Path(args.advisories).write_text(json.dumps(advisories_of(status), indent=1) + "\n", "utf-8")
        for e in status["errors"]:
            print("::warning::not read from GitHub: %s" % e.replace("::", ": "))
        return 0
    inv = _read(args.inventory)
    if not inv:
        print("::error::no inventory to read (%s)" % args.inventory)
        return 1
    status = _read(args.status) or {}
    number, ledger = (None, None) if args.dry_run else read_ledger(args.repo, gh_api)
    if number and ledger is None:
        print("::warning::the ledger in issue #%s could not be read: it starts again" % number)
    ledger = update(ledger, inv, status, _read(args.report), _read(args.candidate_inventory))
    closing = finished_reports(status.get("reports") or [], status.get("tests_runs") or {})
    closed = [] if args.dry_run else close_reports(args.repo, closing, gh_api)
    body = render(ledger, inv, closed)
    if args.out:
        Path(args.out).write_text(body, "utf-8")
    if args.json:
        Path(args.json).write_text(json.dumps(ledger, indent=1) + "\n", "utf-8")
    if not args.dry_run:
        number = write_ledger(args.repo, number, body, gh_api)
        print("ledger: issue #%s" % number)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(body.split("<details><summary>Machine-readable", 1)[0])
    counts = {}
    for e in ledger["entries"].values():
        counts[e["state"]] = counts.get(e["state"], 0) + 1
    print("entries: %s; reports closed: %s" % (counts or "none", closed or (closing and "dry run") or "none"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
