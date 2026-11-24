#!/usr/bin/env python3
"""AUTOMAT's drill: a realistic emergency rehearsed live on GitHub, that never reaches main or users.

The owner asked for it (2026-11-23): "un test fake fatto bene, molto complicato, uno scenario reale
di un aggiornamento massivo di Qt e di tutte le altre componenti installabili, per vedere se le IA
riescono a risolvere il problema". No AI runs here: this tool only prepares the drill, watches it
and reports. Everything in between is AUTOMAT's own chain, unchanged: the tests fail, the plan, the
recipes, the free AIs with the inner loop, the static guard, the job ``try``, the reviewers, the
retries and the memory.

**The scenario** (data: ``tools/automat-drill.json``). Each scenario is one isolated candidate of the
full chain, ``automation/update/drill-<name>`` (tools/update-candidates.py knows the ids ``drill-*``),
made from main by one commit of this tool, ``update: drill-<name> <from> -> <to> (no AI)``, that only
adds the drill's marker ``tools/automat-drill.active`` and writes the scenario's list of breaks into
``tools/automat-drill.json`` without the expected solutions and the release notes (so the AIs'
checkout does not hold the answers; main's copy keeps them, for the judge). In every test run of
that branch (Tests, the Security tests, the automatic fix's job ``try``: the composite action
``ike-test-env`` sees the marker) the test environment gets ``tools/automat-drill-shim.py``: a
simulated major release of Qt and PyQt in which some APIs I.K.E. really uses are renamed, removed or
narrowed. Only a process started from the drill's checkout sees it; main's checkout in the same job,
the Arch Linux job and the browser users install never do. The real Qt runs underneath, so the
right fix (the new API, with a fallback to today's) works in both worlds, and Arch Linux (today's
Qt) tells a fix that forgot the fallback.

**What makes it a drill, never more** (each tested in tests/test_automat_drill.py):

- the branch prefix ``automation/update/drill-``, the title prefix ``DRILL``, the label
  ``automat-drill`` and the marker file: any one of them is enough (is_drill_pr);
- tools/automerge.py judges a drill's pull request like any other (so the guard, "Nothing gets
  worse" and the two reviewers really run), but where it would merge it never does: it notes the
  drill complete on the pull request and asks this tool for the report (kind "drill");
- the signing notice (tools/release-notice.py) and the maintenance ledger leave the drill out;
- "DEVI AIUTARCI CON CHATGPT" fires for a drill only into an issue marked as an exercise, with no
  owner named or assigned (tools/automat-help.py);
- a Security failure of the drill's branch opens no security branch, and a failure of GitHub
  there opens no issue (tools/autofix-plan.py);
- no mail to the owner but one: the final summary, a comment naming the owner on the drill's issue;
- **real updates first** (the owner's decision of 2026-11-24): the drill is background work (class 4 of
  tools/ai-quota.py). Real updates may use all of the free quota; the drill's AI calls use only what they
  leave (each provider's leftover window), never while one of them is pending or retrying; the tick (every
  three hours) starts a fix the budget held back again only when background work may run (priority,
  to_resume), and the report says whether the drill is paused.

**The report** (``report``, ``tick``): for each break, fixed or not, by which provider (or recipe)
and at which attempt, after how long; the attempts of AUTOMAT's memory with how each ended (the
guard's rule, the reviewers' reasons); the reviewers' verdicts; the checks of the last commit and
"Nothing gets worse"; the free quota the drill used. Written to a file and to the run's summary;
the drill's issue holds the latest one (an edit, which mails nobody); at the end one comment.

    automat-drill.py start --repo OWNER/NAME [--scenario qt[,libs]] [--restart] [--dry-run]
    automat-drill.py tick --repo OWNER/NAME --out FILE        (every few hours: the report; the end when due;
                                                               a fix held back for real updates started again)
    automat-drill.py stop --repo OWNER/NAME --out FILE        (by hand: the final report now, and the end)
    automat-drill.py report --repo OWNER/NAME --out FILE [--json FILE]
    automat-drill.py shim --install [--root DIR] [--site DIR]
    automat-drill.py branch --scenario NAME [--repo-dir DIR] [--base REF]   (the drill's commit, local only)
"""

import argparse
import datetime as dt
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import sysconfig
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = "tools/automat-drill.json"
MARKER = "tools/automat-drill.active"
SHIM = "tools/automat-drill-shim.py"
SHIM_MODULE = "ike_automat_drill_shim"
PTH = "ike_automat_drill.pth"
PREFIX = "automation/update/drill-"
TITLE = "DRILL"
LABEL = "automat-drill"
BOT = "github-actions[bot]"
BOT_MAIL = "41898282+github-actions[bot]@users.noreply.github.com"
ISSUE_MARK = "<!-- automat-drill: %s -->"
ISSUE_RE = re.compile(r"<!-- automat-drill: ([0-9A-Za-z_.-]{1,80}) -->")
DONE_MARK = "<!-- automat-drill-complete: %s -->"           # written by tools/automerge.py
DONE_RE = re.compile(r"<!-- automat-drill-complete: ([0-9a-f]{40}) -->")
FINAL_MARK = "<!-- automat-drill-final: %s -->"
REPORT_BEGIN, REPORT_END = "<!-- automat-drill-report -->", "<!-- /automat-drill-report -->"
# what of a break the shim needs; the rest (the expected solution, the tests it breaks) stays on main
SHIM_KEYS = ("id", "kind", "module", "owner", "old", "new", "max_args", "signature")
DEFAULT_HOURS = 48
AUTOFIX_COMMIT = re.compile(r"^autofix: attempt (\d+) after a failure of \"([^\"]{1,80})\"")
AUTHOR = re.compile(r"^Author: (.{1,80})$", re.M)


# --- what is a drill -------------------------------------------------------------------------------

def is_drill_branch(ref):
    return str(ref or "").startswith(PREFIX) and len(str(ref)) > len(PREFIX)


def is_drill_title(title):
    return str(title or "").lstrip().upper().startswith(TITLE)


def is_drill_pr(pr, files=()):
    """A drill's pull request: its branch, its title, its label or its files say so (any one is enough)."""
    pr = pr or {}
    labels = {(x.get("name") if isinstance(x, dict) else x) for x in pr.get("labels") or ()}
    names = {(f.get("filename") if isinstance(f, dict) else f) for f in files or ()}
    names |= {(f.get("previous_filename") if isinstance(f, dict) else None) for f in files or ()}
    return is_drill_branch((pr.get("head") or {}).get("ref")) or is_drill_title(pr.get("title")) or \
        LABEL in labels or MARKER in names


# --- the scenarios ---------------------------------------------------------------------------------

def load_text(text):
    """The scenarios from the text of tools/automat-drill.json ({"scenarios": {}} when it is not one)."""
    try:
        data = json.loads(text or "")
    except ValueError:
        data = None
    if not isinstance(data, dict) or not isinstance(data.get("scenarios"), dict):
        return {"schema": 1, "scenarios": {}}
    return data


def load(root=ROOT):
    try:
        return load_text((Path(root) / DATA).read_text("utf-8"))
    except OSError:
        return {"schema": 1, "scenarios": {}}


def scenario_of(ref_or_id, root=ROOT, data=None):
    """(name, scenario) of a drill's branch or candidate id, or ("", None)."""
    cid = str(ref_or_id or "")
    if cid.startswith("automation/update/"):
        cid = cid[len("automation/update/"):]
    for name, sc in (data or load(root))["scenarios"].items():
        if sc.get("candidate") == cid:
            return name, sc
    return "", None


def attempts_for(ref, default, root=ROOT):
    """The automatic fix's attempts per day on a drill's branch (its scenario's attempts_per_day), else the default."""
    _name, sc = scenario_of(ref, root) if is_drill_branch(ref) else ("", None)
    try:
        n = int((sc or {}).get("attempts_per_day") or 0)
    except (TypeError, ValueError):
        n = 0
    return n if 1 <= n <= 12 else default


def notes_for(ref, root=ROOT, data=None):
    """The simulated release notes of a drill's scenario (what changed upstream), or ""."""
    _name, sc = scenario_of(ref, root, data) if is_drill_branch(ref) else ("", None)
    notes = (sc or {}).get("notes") or []
    return "\n".join(notes) if isinstance(notes, list) else str(notes)


def branch_data(data, name):
    """The JSON the drill's branch carries: only this scenario, each break with only what the shim needs."""
    sc = data["scenarios"][name]
    breaks = [{k: b[k] for k in SHIM_KEYS if k in b} for b in sc.get("breaks") or ()]
    return {"schema": data.get("schema", 1), "scenarios": {name: {"candidate": sc["candidate"], "breaks": breaks}},
            "note": "An AUTOMAT drill's branch: the scenario's breaks only (main's copy holds the rest)."}


def marker(name, sc, drill_id, started, main_sha):
    return {"scenario": name, "candidate": sc["candidate"], "drill": drill_id, "started": started,
            "main": main_sha, "hours": int(sc.get("hours") or DEFAULT_HOURS),
            "what": "AUTOMAT drill: an exercise, never merged into main and never shipped (tools/automat-drill.py)"}


def commit_message(sc):
    def one(text):
        return re.sub(r"\s+", " ", str(text)).replace("->", "to").strip()[:100]
    return "update: %s %s -> %s (no AI)" % (sc["candidate"], one(sc.get("from") or "?"), one(sc.get("to") or "?"))


# --- the branch -----------------------------------------------------------------------------------

def _git(cwd, *args, env=None, check=True):
    out = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, env=env)
    if check and out.returncode:
        raise RuntimeError("git %s: %s" % (" ".join(args[:2]), out.stderr.strip()[:300]))
    return out.stdout.strip()


def make_branch(repo_dir, name, data, drill_id, now, base="origin/main"):
    """The drill's commit on a local branch automat-drill-local-<candidate> made from base: (branch, sha, files)."""
    sc = data["scenarios"][name]
    base_sha = _git(repo_dir, "rev-parse", base)
    local = "automat-drill-local-" + sc["candidate"]
    _git(repo_dir, "checkout", "-q", "-B", local, base_sha)
    (Path(repo_dir) / MARKER).write_text(json.dumps(marker(name, sc, drill_id, now, base_sha), indent=2) + "\n",
                                         "utf-8")
    (Path(repo_dir) / DATA).write_text(json.dumps(branch_data(data, name), indent=2) + "\n", "utf-8")
    _git(repo_dir, "add", MARKER, DATA)
    env = dict(os.environ, GIT_AUTHOR_NAME=BOT, GIT_AUTHOR_EMAIL=BOT_MAIL, GIT_COMMITTER_NAME=BOT,
               GIT_COMMITTER_EMAIL=BOT_MAIL)
    _git(repo_dir, "commit", "-q", "-m", commit_message(sc) + "\n\nAUTOMAT drill %s: an exercise, never merged into "
         "main (tools/automat-drill.py)." % drill_id, env=env)
    sha = _git(repo_dir, "rev-parse", "HEAD")
    files = sorted(f for f in _git(repo_dir, "diff", "--name-only", base_sha, sha).split("\n") if f)
    return local, sha, files


# --- the shim -------------------------------------------------------------------------------------

def install_shim(root=".", site=None):
    """The simulated Qt in this Python, only when the checkout at root is a drill's. Returns True when installed."""
    root = Path(root)
    if not (root / MARKER).is_file():
        print("not a drill's checkout (no %s): nothing installed" % MARKER)
        return False
    site = Path(site or sysconfig.get_paths()["purelib"])
    site.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(root / SHIM, site / (SHIM_MODULE + ".py"))
    (site / PTH).write_text("import %s; %s.install()\n" % (SHIM_MODULE, SHIM_MODULE), "utf-8")
    m = json.loads((root / MARKER).read_text("utf-8"))
    print("AUTOMAT drill %s: the simulated release of scenario %s is installed in %s" % (
        m.get("drill", "?"), m.get("scenario", "?"), site))
    return True


# --- GitHub ---------------------------------------------------------------------------------------

def gh_api(path, method="GET", data=None, raw=False, token=None):
    """GitHub's API (gh), asked again on a network error; token: another token than GH_TOKEN for this call."""
    cmd = ["gh", "api", "-X", method, path] + (["--input", "-"] if data is not None else [])
    env = dict(os.environ, GH_TOKEN=token) if token else None
    for attempt in range(3):
        out = subprocess.run(cmd, input=json.dumps(data).encode() if data is not None else None, capture_output=True,
                             env=env)
        if out.returncode == 0:
            if raw:
                return out.stdout
            return json.loads(out.stdout) if out.stdout.strip() else {}
        err = out.stderr.decode("utf-8", "replace")
        if not re.search(r"\b(5\d\d|timeout|reset|EOF|connection)\b", err, re.I) or attempt == 2:
            raise RuntimeError("gh api %s: %s" % (path, err.strip()[:300]))
        import time
        time.sleep(10 * (attempt + 1))
    raise RuntimeError("gh api %s: no answer" % path)


def _tool(name):
    spec = importlib.util.spec_from_file_location("drill_" + name.replace("-", "_"), ROOT / "tools" / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def drill_issues(repo, api, state="open"):
    """The drills' own issues (not the help notices): [(issue, drill id)]."""
    out = []
    for issue in api("repos/%s/issues?state=%s&labels=%s&per_page=100" % (repo, state, LABEL)) or []:
        if "pull_request" in issue or (issue.get("user") or {}).get("login") != BOT:
            continue
        m = ISSUE_RE.search(issue.get("body") or "")
        if m:
            out.append((issue, m.group(1)))
    return out


def drill_prs(repo, api, state="open"):
    return [p for p in api("repos/%s/pulls?state=%s&per_page=100" % (repo, state)) or []
            if is_drill_branch((p.get("head") or {}).get("ref")) and
            ((p.get("head") or {}).get("repo") or {}).get("full_name") in (None, repo)]


# --- the report -----------------------------------------------------------------------------------

def _hours(a, b):
    try:
        t0 = dt.datetime.fromisoformat(str(a).replace("Z", "+00:00"))
        t1 = dt.datetime.fromisoformat(str(b).replace("Z", "+00:00"))
    except ValueError:
        return None
    return round((t1 - t0).total_seconds() / 3600, 1)


def junit_results(xml_text):
    """{test id "tests/x.py::name": "passed" | "failed" | "skipped"} of a junit file."""
    import xml.etree.ElementTree as ET
    out = {}
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return out
    for case in root.iter("testcase"):
        parts = (case.get("classname") or "").split(".")
        name = re.sub(r"\[.*$", "", case.get("name") or "")
        path = "/".join(parts) + ".py" if parts and parts[0] == "tests" else "/".join(parts[:-1]) + ".py"
        if case.find("failure") is not None or case.find("error") is not None:
            state = "failed"
        elif case.find("skipped") is not None:
            state = "skipped"
        else:
            state = "passed"
        key = "%s::%s" % (path, name)
        if out.get(key) != "failed":
            out[key] = state
    return out


def break_state(b, results):
    """"fixed", "broken" or "not read" for one break, from the junit results of a commit."""
    tests = b.get("tests") or []
    if not results or not tests:
        return "not read"
    seen = [results.get(t) for t in tests]
    if any(s == "failed" for s in seen):
        return "broken"
    if all(s == "passed" for s in seen):
        return "fixed"
    return "not read"


def junit_of_run(repo, run_id, api):
    """The junit results of a Tests run (its artifact "test-results"), or {}."""
    try:
        arts = api("repos/%s/actions/runs/%s/artifacts?per_page=50" % (repo, run_id)).get("artifacts", [])
        art = next((a for a in arts if a.get("name") == "test-results" and not a.get("expired")), None)
        if not art:
            return {}
        blob = api("repos/%s/actions/artifacts/%s/zip" % (repo, art["id"]), raw=True)
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            name = next((n for n in z.namelist() if n.endswith("junit.xml") and "installed" not in n), None)
            return junit_results(z.read(name).decode("utf-8", "replace")) if name else {}
    except (RuntimeError, ValueError, KeyError, zipfile.BadZipFile, StopIteration):
        return {}


def gather(repo, api=gh_api, memory=None, quota=None, now=None, root=ROOT):
    """What the report says, read from GitHub (GET only): {"drills": [...], "now"}."""
    led = _tool("maintenance-ledger")
    rv = _tool("ai-review")
    am = _tool("automerge")
    data = load(root)
    now = now or dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    out = {"now": now, "drills": []}
    prs = {}
    for state in ("open", "closed"):
        try:
            for p in drill_prs(repo, api, state):
                ref = p["head"]["ref"]
                if ref not in prs or (p.get("created_at") or "") > (prs[ref].get("created_at") or ""):
                    prs[ref] = p
        except RuntimeError:
            continue
    for name, sc in sorted(data["scenarios"].items()):
        ref = "automation/update/" + sc.get("candidate", "")
        p = prs.get(ref)
        d = {"scenario": name, "title": sc.get("title", name), "branch": ref, "pr": None, "breaks": [],
             "commits": [], "reviews": [], "checks": {}, "attempts": [], "quota": {}, "verdict": "", "complete": False,
             "started": "", "head": "", "hours": int(sc.get("hours") or DEFAULT_HOURS)}
        if not p:
            continue
        d["pr"] = {"number": p["number"], "state": p.get("state"), "url": p.get("html_url", ""),
                   "created_at": p.get("created_at", "")}
        d["started"] = p.get("created_at", "")
        sha = (p.get("head") or {}).get("sha", "")
        d["head"] = sha
        try:
            commits = api("repos/%s/pulls/%d/commits?per_page=100" % (repo, p["number"]))
        except RuntimeError:
            commits = []
        try:
            comments = api("repos/%s/issues/%d/comments?per_page=100" % (repo, p["number"]))
        except RuntimeError:
            comments = []
        for c in commits:
            msg = (c.get("commit") or {}).get("message") or ""
            m = AUTOFIX_COMMIT.match(msg)
            if not m:
                continue
            who = AUTHOR.search(msg)
            d["commits"].append({"sha": c.get("sha", ""), "attempt": int(m.group(1)), "workflow": m.group(2),
                                 "author": who.group(1).strip() if who else "?",
                                 "date": ((c.get("commit") or {}).get("committer") or {}).get("date", "")})
        for c in d["commits"]:
            r = rv.result_in(comments, c["sha"])
            if r:
                d["reviews"].append({"sha": c["sha"], "verdict": r.get("verdict"),
                                     "by": [(x.get("provider"), x.get("verdict"), "; ".join(x.get("reasons") or [])[:200])
                                            for x in r.get("reviews") or []]})
        for c in comments:
            body = c.get("body") or ""
            if (c.get("user") or {}).get("login") != BOT:
                continue
            if am.MARK in body:
                why = re.search(r"non è ancora entrata in `main`: (.*?)\.\n", body)
                d["verdict"] = why.group(1)[:300] if why else d["verdict"]
            m = DONE_RE.search(body)
            if m and m.group(1) == sha:
                d["complete"] = True
        try:
            runs = {wf: led.run_info(repo, wf, api, sha=sha) for wf in ("tests.yml", "security.yml", "arch.yml")}
        except Exception:
            runs = {}
        for wf, run in runs.items():
            d["checks"][wf] = (run or {}).get("conclusion") or (run or {}).get("status") or "no run"
        # the Tests run of the drill's last commit: its automatic fix may be started again (to_resume)
        d["tests_run"] = {k: (runs.get("tests.yml") or {}).get(k) for k in ("id", "conclusion", "status", "created_at")}
        try:
            d["checks"]["no-regression"] = am.no_regression({"runs": runs})[0]
        except Exception:
            d["checks"]["no-regression"] = "not read"
        # each break: its state now, and the first commit of an AI (or a recipe) after which its tests passed
        junits, tests_runs = {}, {}

        def junit_at(commit_sha):
            if commit_sha not in junits:
                try:
                    run = led.run_info(repo, "tests.yml", api, sha=commit_sha, completed=True)
                except Exception:
                    run = None
                tests_runs[commit_sha] = run
                junits[commit_sha] = junit_of_run(repo, run["id"], api) if run else {}
            return junits[commit_sha]
        head = junit_at(sha) if sha else {}
        for b in sc.get("breaks") or ():
            row = {"id": b.get("id"), "what": b.get("what", ""), "files": b.get("files", []),
                   "difficulty": b.get("difficulty", ""), "state": break_state(b, head), "by": "", "attempt": None,
                   "after_hours": None, "expected": (b.get("expected") or {}).get("summary", "")}
            if row["state"] == "fixed":
                for c in d["commits"]:
                    if break_state(b, junit_at(c["sha"])) == "fixed":
                        row.update(by=c["author"], attempt=c["attempt"], after_hours=_hours(d["started"], c["date"]))
                        break
            d["breaks"].append(row)
        # "Nothing gets worse" on each commit an AI or a recipe wrote: did it stay green all along?
        for c in d["commits"]:
            junit_at(c["sha"])
            run = tests_runs.get(c["sha"])
            try:
                c["no_regression"] = am.no_regression({"runs": {"tests.yml": run}})[0] if run else "no run"
            except Exception:
                c["no_regression"] = "not read"
        for key, records in ((memory or {}).get("attempts") or {}).items():
            if key.split("@", 1)[0] != ref:
                continue
            for r in records:
                d["attempts"].append({k: r.get(k) for k in ("date", "attempt", "provider", "model", "outcome", "detail",
                                                           "files", "task")})
        d["attempts"].sort(key=lambda r: (str(r.get("date")), int(r.get("attempt") or 0)))
        for day, info in sorted(((quota or {}).get("days") or {}).items()):
            for prov, p in (info.get("providers") or {}).items():
                mine = (p.get("by") or {}).get(ref)
                if mine:
                    q = d["quota"].setdefault(prov, {"requests": 0, "tokens": 0})
                    q["requests"] += int(mine.get("requests") or 0)
                    q["tokens"] += int(mine.get("tokens") or 0)
        try:
            notices = [(i["number"], i.get("html_url", ""), i.get("state")) for i, _s, comp in
                       _tool("automat-help").notices(repo, lambda path, *a: api(path))
                       if comp == ref]
        except Exception:
            notices = []
        d["help"] = notices
        out["drills"].append(d)
    return out


# --- real updates first (the owner's decision of 2026-11-24) -----------------------------------------

RESUME_AFTER_HOURS = 2          # a failed Tests run of the drill whose fix did not come: started again after this
RESUMED_MARK = "<!-- automat-drill-resumed: %s %s -->"
RESUMED_RE = re.compile(r"<!-- automat-drill-resumed: (\d{1,20}) (\d{4}-\d\d-\d\d) -->")
KEEP_MARKS = 20


def priority(memory, quota, now=None, repo=None, api=None):
    """Whether the drill's work may ask a free AI now (tools/ai-quota.py background_status): the drill is
    background work, class 4. It pauses while a security fix or a real update is pending or retrying (an open
    pull request whose checks are not green, read with GET calls when repo is given, or a row of failures in
    AUTOMAT's memory whose pull request was not closed after it; when the pull requests cannot be read, it
    pauses too: fail closed), and otherwise takes what real work leaves, in each provider's leftover window
    (the last hours of its own day; with a reset not verified, also never during the day's maintenance)."""
    q = _tool("ai-quota")
    limits = q.load_limits()
    state = quota if isinstance(quota, dict) and isinstance(quota.get("days"), dict) else q.empty_state()
    prs = None
    if repo and api:
        try:
            prs = q.gather_prs(repo, api, memory, limits, now)
        except Exception as e:                  # not read: unknown, the drill pauses (fail closed)
            print("::warning::the open pull requests could not be read: %s" % str(e)[:200])
            return q.background_status(limits, state, memory, now,
                                       pending=q.pending_work(memory, limits, now) + [q.UNKNOWN])
    return q.background_status(limits, state, memory, now, prs=prs)


def autofix_busy(repo, api):
    """True when an automatic fix runs or waits now (then nothing more is started)."""
    for status in ("in_progress", "queued"):
        try:
            got = api("repos/%s/actions/workflows/autofix.yml/runs?status=%s&per_page=1" % (repo, status)) or {}
        except RuntimeError:
            return True                        # not known: rather not start
        if int(got.get("total_count") or 0) or got.get("workflow_runs"):
            return True
    return False


def resumed_marks(body):
    return set(RESUMED_RE.findall(body or ""))


def to_resume(info, status, resumed, busy, now=None):
    """The drills whose last Tests run failed and whose automatic fix did not come (the budget held it back
    while real updates went first): [(branch, run id)]. Only when background work may run now, no automatic
    fix runs or waits, the failure is at least RESUME_AFTER_HOURS old and that run was not started again
    today already (the plan's cap per day still counts every attempt)."""
    if (status or {}).get("state") not in ("open", "released") or busy:
        return []
    now = now or info.get("now")
    today = str(now)[:10]
    out = []
    for d in info.get("drills") or ():
        run = d.get("tests_run") or {}
        if not d.get("pr") or (d["pr"].get("state") or "open") != "open" or d.get("complete"):
            continue
        if run.get("conclusion") != "failure" or not re.fullmatch(r"\d{1,20}", str(run.get("id") or "")):
            continue
        if (_hours(run.get("created_at"), now) or 0) < RESUME_AFTER_HOURS or (str(run["id"]), today) in resumed:
            continue
        out.append((d["branch"], str(run["id"])))
    return out


def resume(repo, todo, api=gh_api):
    """The automatic fix started again for each failed run (the work run/<id>, as the daily check does)."""
    started = []
    for branch, run_id in todo:
        try:
            api("repos/%s/actions/workflows/autofix.yml/dispatches" % repo, "POST",
                {"ref": "main", "inputs": {"run_id": run_id, "work": "run/%s" % run_id}})
        except RuntimeError as e:
            print("::warning::the drill's fix of %s could not be started again: %s" % (branch, str(e)[:200]))
            continue
        print("the drill's automatic fix of %s started again (run %s): background work may run now"
              % (branch, run_id))
        started.append(run_id)
    return started


def with_resumed(body, run_ids, today):
    """The issue's body with a mark for each run started again today (the newest KEEP_MARKS kept)."""
    marks = RESUMED_RE.findall(body or "") + [(r, today) for r in run_ids]
    body = RESUMED_RE.sub("", body or "").rstrip()
    keep = marks[-KEEP_MARKS:]
    return body + ("\n\n" + "\n".join(RESUMED_MARK % m for m in keep) + "\n" if keep else "\n")


PRIORITY_IT = {"open": "può usare quello che gli aggiornamenti veri hanno lasciato delle AI gratuite",
               "released": "può usare quello che avanza delle AI gratuite (è l'ultima parte della loro giornata)",
               "paused": "è in pausa: prima gli aggiornamenti veri",
               "no-room": "aspetta: ora le AI gratuite non hanno niente di avanzato per il lavoro di fondo"}


def due(info, now=None):
    """(done, why): the drill ends when every drill's pull request is complete, or after its hours."""
    drills = [d for d in info.get("drills") or () if d.get("pr")]
    if not drills:
        return True, "no drill's pull request"
    if all(d.get("complete") for d in drills):
        return True, "every break fixed, every check green and both reviews approve: the drill is complete"
    now = now or info.get("now")
    late = [d for d in drills if (_hours(d.get("started"), now) or 0) >= d.get("hours", DEFAULT_HOURS)]
    if len(late) == len(drills):
        return True, "the drill's time is over (%d hours)" % max(d.get("hours", DEFAULT_HOURS) for d in late)
    return False, ""


STATE_IT = {"fixed": "**risolto**", "broken": "non risolto", "not read": "non letto"}


def markdown(info, final=False, why=""):
    """The report, in plain Italian for the owner (the names of the code as they are)."""
    out = ["## Esercitazione AUTOMAT (DRILL)%s" % (": risultato finale" if final else ": a che punto è"), "",
           "Un'esercitazione: niente di questo entra in `main` o arriva agli utenti. %s" % (why or ""), ""]
    for d in info.get("drills") or ():
        if not d.get("pr"):
            continue
        pr = d["pr"]
        elapsed = _hours(d.get("started"), info.get("now"))
        fixed = sum(1 for b in d["breaks"] if b["state"] == "fixed")
        out += ["### %s (`%s`, PR #%s)" % (d.get("title"), d["branch"], pr["number"]), "",
                "Iniziata: %s; passate %s ore. Rotture risolte: **%d su %d**. %s" % (
                    d.get("started") or "?", elapsed if elapsed is not None else "?", fixed, len(d["breaks"]),
                    "Completata: tutto verde, avrebbe potuto entrare (ma non entra mai)." if d.get("complete") else ""),
                "", "| Rottura | File | Difficoltà | Esito | Da chi | Tentativo | Dopo (ore) |", "|---|---|---|---|---|---|---|"]
        for b in d["breaks"]:
            out.append("| %s %s | %s | %s | %s | %s | %s | %s |" % (
                b["id"], _md(b["what"]), _md(", ".join(b["files"])), b["difficulty"] or "-",
                STATE_IT.get(b["state"], b["state"]), _md(b["by"]) or "-", b["attempt"] or "-",
                b["after_hours"] if b["after_hours"] is not None else "-"))
        out += ["", "Controlli dell'ultimo commit (`%s`): test %s, Security %s, Arch Linux %s; \"Niente peggiora\" "
                "(no-regression): %s." % ((d.get("head") or "?")[:10], d["checks"].get("tests.yml", "?"),
                                          d["checks"].get("security.yml", "?"), d["checks"].get("arch.yml", "?"),
                                          d["checks"].get("no-regression", "?")), ""]
        if d.get("verdict"):
            out += ["Il giudizio di AUTOMAT sul merge: %s." % _md(d["verdict"]), ""]
        if d["commits"]:
            out += ["Correzioni pubblicate sul ramo:", ""]
            for c in d["commits"]:
                out.append("- tentativo %d, `%s`, scritta da **%s** (%s); \"niente peggiora\": %s" % (
                    c["attempt"], c["sha"][:10], _md(c["author"]), c["date"], c.get("no_regression", "?")))
            out.append("")
        if d["reviews"]:
            out += ["Revisioni delle AI:", ""]
            for r in d["reviews"]:
                said = "; ".join("%s %s%s" % (p, v, (": " + _md(why)) if why and v == "reject" else "")
                                 for p, v, why in r["by"])
                out.append("- `%s`: %s (%s)" % (r["sha"][:10], r["verdict"], said))
            out.append("")
        if d["attempts"]:
            out += ["Tentativi nella memoria di AUTOMAT (chi, come è finita):", ""]
            for a in d["attempts"][-30:]:
                out.append("- %s, tentativo %s: %s (%s): %s%s" % (
                    a.get("date"), a.get("attempt"), _md(a.get("provider") or "?"), _md(a.get("model") or "-"),
                    a.get("outcome"), (" — " + _md(a.get("detail"))) if a.get("detail") else ""))
            out.append("")
        if d["quota"]:
            out += ["Quota gratuita usata dall'esercitazione: " + "; ".join(
                "%s %d richieste, %d token" % (p, q["requests"], q["tokens"]) for p, q in sorted(d["quota"].items())),
                ""]
        if d.get("help"):
            out += ["Avviso \"DEVI AIUTARCI CON CHATGPT\" (in modalità esercitazione): " + ", ".join(
                "#%s (%s)" % (n, s) for n, _u, s in d["help"]), ""]
        if final:
            out += ["<details><summary>Le soluzioni attese, per giudicare</summary>", ""]
            for b in d["breaks"]:
                out.append("- %s: %s" % (b["id"], _md(b["expected"]) or "-"))
            out += ["", "</details>", ""]
    if not any(d.get("pr") for d in info.get("drills") or ()):
        out += ["Nessuna esercitazione in corso.", ""]
    status = info.get("priority")
    if status and not final and any(d.get("pr") for d in info.get("drills") or ()):
        # real updates first (2026-11-24): the drill is background work
        out += ["Priorità: l'esercitazione è lavoro di fondo e %s%s." % (
            PRIORITY_IT.get(status.get("state"), _md(status.get("state"))),
            " (in attesa: %s)" % ", ".join("`%s`" % _md(c) for c in (status.get("pending") or [])[:4])
            if status.get("state") == "paused" and status.get("pending") else ""), ""]
    return "\n".join(out) + "\n"


def _md(text):
    return re.sub(r"[|\n\r`]", " ", str(text or "")).replace("@", "@​")[:300].strip()


def with_report(body, report):
    """The drill issue's body with the latest report between its marks (an edit mails nobody)."""
    block = "%s\n%s\n%s" % (REPORT_BEGIN, report.strip(), REPORT_END)
    if REPORT_BEGIN in body and REPORT_END in body:
        return re.sub(re.escape(REPORT_BEGIN) + r".*?" + re.escape(REPORT_END), lambda _m: block, body, flags=re.S)
    return body.rstrip() + "\n\n" + block + "\n"


def read_data_branch(repo, name):
    """memory.json or quota.json of AUTOMAT's data branch, or None."""
    import base64
    try:
        got = gh_api("repos/%s/contents/%s?ref=automat/memory" % (repo, name))
        return json.loads(base64.b64decode(got["content"]).decode("utf-8"))
    except (RuntimeError, ValueError, KeyError, TypeError):
        return None


def summary_out(text):
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(text)


def finish(repo, info, report, owner, api=gh_api, why=""):
    """The end: one comment naming the owner on the drill's issue (the only mail of the drill), the
    drill's issue (with its last report), pull requests and help notices closed; the branches stay (the
    record)."""
    done = []
    for issue, drill_id in drill_issues(repo, api):
        mark = FINAL_MARK % drill_id
        said = api("repos/%s/issues/%s/comments?per_page=100" % (repo, issue["number"])) or []
        if not any(mark in (c.get("body") or "") for c in said if (c.get("user") or {}).get("login") == BOT):
            api("repos/%s/issues/%s/comments" % (repo, issue["number"]), "POST", {"body": (
                "@%s: l'esercitazione di AUTOMAT è finita (%s). Era solo una prova: niente è entrato in `main` e "
                "nessun utente ha ricevuto niente. Qui sotto il risultato.\n\n%s\n%s" % (owner, why or "fine", report,
                                                                                         mark))})
        # closed with its last report: the comment above is the mail; nothing of the drill stays open
        api("repos/%s/issues/%s" % (repo, issue["number"]), "PATCH", {
            "body": with_report(issue.get("body") or "", report), "state": "closed", "state_reason": "completed"})
        done.append(issue["number"])
    for p in drill_prs(repo, api):
        api("repos/%s/issues/%s/comments" % (repo, p["number"]), "POST", {"body": (
            "Esercitazione finita (%s): questa pull request si chiude da sola e non entra in `main`. Il ramo resta, "
            "come traccia. Il risultato è nell'issue dell'esercitazione." % (why or "fine"))})
        api("repos/%s/pulls/%s" % (repo, p["number"]), "PATCH", {"state": "closed"})
    try:
        helper = _tool("automat-help")
        for issue, _sig, comp in helper.notices(repo, lambda path, *a: api(path, *a)):
            if is_drill_branch(comp):
                api("repos/%s/issues/%s/comments" % (repo, issue["number"]), "POST", {"body": (
                    "Esercitazione finita: questo avviso di prova si chiude da solo.")})
                api("repos/%s/issues/%s" % (repo, issue["number"]), "PATCH", {"state": "closed",
                                                                             "state_reason": "completed"})
    except Exception as e:
        print("::warning::the drill's help notices could not be closed: %s" % str(e)[:200])
    return done


def issue_body(drill_id, scenarios, prs):
    lines = ["**DRILL: esercitazione di AUTOMAT, non serve fare niente.**", "",
             "Questa è una prova finta ma realistica: un aggiornamento enorme di Qt e PyQt che rompe I.K.E. in più "
             "punti, solo nell'ambiente di test di questi rami. Le AI gratuite provano a ripararlo da sole, con tutta "
             "la catena di AUTOMAT (test, piano, ricette, AI, controllo delle regole, revisori, nuovi tentativi).", "",
             "Niente di questo entra in `main`, niente arriva agli utenti, niente va firmato. Questa issue si aggiorna "
             "da sola; alla fine arriva **un solo** messaggio con il riepilogo.", ""]
    for name, sc in scenarios:
        n = prs.get(sc["candidate"])
        lines.append("- %s: ramo `automation/update/%s`%s" % (sc.get("title", name), sc["candidate"],
                                                               ", pull request #%s" % n if n else ""))
    lines += ["", "Per fermarla prima: `gh workflow run automat-drill.yml --ref main -f action=stop`.", "",
              ISSUE_MARK % drill_id]
    return "\n".join(lines) + "\n"


def pr_body(drill_id, name, sc):
    return ("**DRILL: un'esercitazione di AUTOMAT. Non entra mai in `main`.**\n\n"
            "Scenario `%s`: %s (%s -> %s, simulato). Il ramo è `main` più il segnale dell'esercitazione "
            "(`%s`): nei suoi test l'ambiente simula la nuova versione (`tools/automat-drill-shim.py`), e I.K.E. "
            "si rompe in %d punti. AUTOMAT la ripara da solo come una vera emergenza; `tools/automerge.py` la "
            "giudica come le altre ma, dove la unirebbe, non la unisce mai.\n\nDrill %s (tools/automat-drill.py).\n"
            % (name, sc.get("title", name), sc.get("from", "?"), sc.get("to", "?"), MARKER, len(sc.get("breaks") or ()),
               drill_id))


def start(repo, names, restart=False, dry_run=False, api=gh_api, repo_dir=".", now=None):
    """The drill begins: for each scenario its branch from main, its draft pull request, then its checks;
    one drill issue. Returns {candidate: pr number} (nothing pushed with dry_run)."""
    data = load(Path(repo_dir))
    now = now or dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    drill_id = "%s-%s" % ("-".join(names), re.sub(r"\D", "", now)[:12])
    chosen = []
    for name in names:
        sc = data["scenarios"].get(name)
        if not sc or not is_drill_branch("automation/update/" + str(sc.get("candidate"))):
            raise SystemExit("no drill scenario named %r" % name)
        chosen.append((name, sc))
    open_now = {} if dry_run else {p["head"]["ref"]: p for p in drill_prs(repo, api)}
    for name, sc in chosen:
        ref = "automation/update/" + sc["candidate"]
        if ref in open_now and not restart:
            raise SystemExit("a drill already runs on %s (PR #%s): stop it first (action=stop), or start with "
                             "restart" % (ref, open_now[ref]["number"]))
    prs = {}
    for name, sc in chosen:
        ref = "automation/update/" + sc["candidate"]
        local, sha, files = make_branch(repo_dir, name, data, drill_id, now)
        problems = _tool("update-candidates").check_range(sc["candidate"], "origin/main", local) \
            if not dry_run else []
        if problems:
            raise SystemExit("the drill's commit is not its own update commit: %s" % "; ".join(problems))
        print("%s: %s (%s), files %s" % (ref, sha[:10], commit_message(sc), ", ".join(files)))
        if dry_run:
            continue
        token = os.environ.get("WORKFLOW_TOKEN") or os.environ.get("GH_TOKEN") or ""
        import base64
        auth = base64.b64encode(("x-access-token:%s" % token).encode()).decode()
        _git(repo_dir, "-c", "http.https://github.com/.extraheader=AUTHORIZATION: basic %s" % auth, "push", "-q",
             "--force", "origin", "%s:refs/heads/%s" % (local, ref))
        if ref in open_now:
            api("repos/%s/issues/%s/comments" % (repo, open_now[ref]["number"]), "POST",
                {"body": "Una nuova esercitazione è partita (%s): il ramo è stato rifatto da `main`." % drill_id})
            prs[sc["candidate"]] = open_now[ref]["number"]
        else:
            try:
                api("repos/%s/labels" % repo, "POST", {"name": LABEL, "color": "c5def5",
                                                       "description": "An AUTOMAT drill: never merged, never shipped"})
            except RuntimeError:
                pass
            title = "%s: AUTOMAT, %s (%s -> %s, simulato; esercitazione, mai in main)" % (
                TITLE, sc.get("title", name), sc.get("from", "?"), sc.get("to", "?"))
            # with the owner's token when it is set (as the daily maintenance): the pull request's own checks start
            body = {"title": title[:240], "head": ref, "base": "main", "draft": True, "body": pr_body(drill_id, name, sc)}
            made = api("repos/%s/pulls" % repo, "POST", body, token=os.environ.get("WORKFLOW_TOKEN") or None) \
                if os.environ.get("WORKFLOW_TOKEN") else api("repos/%s/pulls" % repo, "POST", body)
            prs[sc["candidate"]] = made.get("number")
            api("repos/%s/issues/%s/labels" % (repo, made.get("number")), "POST", {"labels": [LABEL]})
        if not os.environ.get("WORKFLOW_TOKEN"):
            # pushed with the workflow's own token: GitHub starts no run by itself (daily-maintenance.yml does the same)
            for wf in ("tests.yml", "security.yml", "arch.yml"):
                try:
                    subprocess.run(["gh", "workflow", "run", wf, "--repo", repo, "--ref", ref], check=True,
                                   capture_output=True)
                except subprocess.CalledProcessError as e:
                    print("::warning::%s could not be started on %s: %s" % (wf, ref, e.stderr[:200]))
    if dry_run:
        return prs
    for issue, old in drill_issues(repo, api):
        api("repos/%s/issues/%s/comments" % (repo, issue["number"]), "POST",
            {"body": "Questa esercitazione è sostituita da una nuova (%s)." % drill_id})
        api("repos/%s/issues/%s" % (repo, issue["number"]), "PATCH", {"state": "closed", "state_reason": "not_planned"})
    made = api("repos/%s/issues" % repo, "POST", {
        "title": "%s: esercitazione di AUTOMAT in corso (%s), non serve fare niente" % (
            TITLE, ", ".join(sc.get("title", n) for n, sc in chosen))[:240],
        "body": issue_body(drill_id, chosen, prs), "labels": [LABEL]})
    print("the drill's issue: #%s" % made.get("number"))
    return prs


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("start")
    s.add_argument("--repo", required=True)
    s.add_argument("--scenario", default="qt")
    s.add_argument("--restart", action="store_true")
    s.add_argument("--dry-run", action="store_true")
    s.add_argument("--repo-dir", default=".")
    for cmd in ("tick", "stop", "report"):
        r = sub.add_parser(cmd)
        r.add_argument("--repo", required=True)
        r.add_argument("--out", required=True)
        r.add_argument("--json")
    h = sub.add_parser("shim")
    h.add_argument("--install", action="store_true", required=True)
    h.add_argument("--root", default=".")
    h.add_argument("--site")
    b = sub.add_parser("branch")
    b.add_argument("--scenario", required=True)
    b.add_argument("--repo-dir", default=".")
    b.add_argument("--base", default="origin/main")
    a = ap.parse_args(argv)
    if a.cmd == "shim":
        install_shim(a.root, a.site)
        return 0
    if a.cmd == "branch":
        local, sha, files = make_branch(a.repo_dir, a.scenario, load(Path(a.repo_dir)), "local",
                                        dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), a.base)
        print("%s %s %s" % (local, sha, " ".join(files)))
        return 0
    if a.cmd == "start":
        names = [n.strip() for n in a.scenario.split(",") if n.strip()]
        prs = start(a.repo, names, a.restart, a.dry_run, repo_dir=a.repo_dir)
        summary_out("### AUTOMAT drill started\n\n%s\n" % "\n".join("- `%s`: PR #%s" % kv for kv in prs.items()))
        return 0
    issues = drill_issues(a.repo, gh_api) if a.cmd != "report" else []
    if not issues and a.cmd == "tick":
        print("no drill runs: nothing to do")
        return 0
    memory, quota = read_data_branch(a.repo, "memory.json"), read_data_branch(a.repo, "quota.json")
    info = gather(a.repo, gh_api, memory, quota)
    info["priority"] = priority(memory, quota, repo=a.repo, api=gh_api)
    done, why = due(info)
    final = a.cmd == "stop" or (a.cmd == "tick" and done)
    if a.cmd == "stop":
        why = "fermata a mano"
    text = markdown(info, final, why if final else "")
    Path(a.out).write_text(text, "utf-8")
    if a.json:
        Path(a.json).write_text(json.dumps(info, indent=1) + "\n", "utf-8")
    summary_out(text)
    print(text)
    if a.cmd == "report":
        return 0
    if final:
        finish(a.repo, info, text, a.repo.split("/")[0], gh_api, why)
        return 0
    # real updates first: a drill's fix the budget held back starts again only when background work may run
    # (no real update pending, or the providers' last hours), never while one is
    resumed = set()
    for issue, _drill in issues:
        resumed |= resumed_marks(issue.get("body") or "")
    started = resume(a.repo, to_resume(info, info["priority"], resumed, autofix_busy(a.repo, gh_api)))
    for issue, _drill in issues:
        body = with_report(issue.get("body") or "", text)
        if started:
            body = with_resumed(body, started, str(info.get("now"))[:10])
        if body != (issue.get("body") or ""):
            gh_api("repos/%s/issues/%s" % (a.repo, issue["number"]), "PATCH", {"body": body})
    return 0

if __name__ == "__main__":
    sys.exit(main())
