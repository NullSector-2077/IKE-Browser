#!/usr/bin/env python3
"""The budget of each provider's free quota (AUTOMAT part 2; no AI here: this counts what is asked).

Only free providers work for AUTOMAT (tools/ai-providers.py), and a free quota runs out. Until now a
provider out of quota was found by asking it (a 429) and the fix that had used the last answers left
none for its reviewers. This file is the scheduler:

- **The limits are data** (tools/ai-quota.json, never code): per provider the requests and tokens per
  day and per minute, each with its source, and ``"verified": false`` with a conservative value where
  the provider's documentation could not be read. The answers themselves correct it: the rate-limit
  headers of every call (observe: the names of each provider's headers are data too) and a 429 with
  its ``retry-after`` (note). What a provider says today counts more than what the file says.
- **The use is recorded per day** in ``quota.json`` on the data branch ``automat/memory`` (next to
  AUTOMAT's memory; written only by the workflows' own jobs, never by a step that holds a key): per
  provider the requests and tokens of the day, by candidate, whether it is spent today, and what its
  headers said last. The steps that hold the keys only write a small file of numbers (delta), which a
  job without keys merges (merge), after checking it is numbers and known names.
- **Before each call** (Budget.allows): a provider that is spent today is never asked; one without
  room for the estimated size is skipped; a fix is not started unless, after it, two other providers
  (three for a tier-B change) still have room for one review each (the reserve: without it the fix
  waits and nothing is wasted); and while another security fix or real update is pending at the same
  time, one candidate's fixes take at most ``share_per_candidate`` of a provider's day, so two real
  updates share it fairly (a lone real update may use all of it). A limit per minute is waited out
  when it is short (wait_seconds).
- **The signing notice** shows the use and what is left per provider (summary).
- A day when the automatic fix ran and no free provider at all could answer is counted (ran): two
  such days in a row start the notice "DEVI AIUTARCI CON CHATGPT" (tools/automat-help.py).
- **Real updates first** (the owner's decision of 2026-11-24: "use the free AIs every day, always
  when needed, above all for real updates; what is left goes to self-evolution, drills etc."). Every
  piece of AI work has a class by its branch (priority_of; the prefixes are data, "priority" in
  tools/ai-quota.json): 1 security fixes, 2 updates of what ships to users, 3 the CI and the tools,
  4 background (the AUTOMAT drill, the replay bench, self-evolution). Real updates (classes 1 and 2)
  may always use ALL of every free quota; classes 3 and 4 get only what real work leaves, and all of it:
  never while work of class 1 or 2 is pending or retrying (pending_all: an open pull request whose
  latest checks are not green, a row of failures in AUTOMAT's memory whose pull request was not closed
  after it), never while that list could not be read (UNKNOWN: fail closed), and only in the provider's
  leftover window (leftover_window): the last release_hours hours before its own reset; when a person
  has not verified that reset, also never during the real day's maintenance window (UTC). Each
  provider's use is counted on its own day (provider_day: the time and zone of its "reset"), and a
  quota answer (429) to work of class 3 or 4 never spends a provider for classes 1 and 2.
- **OpenRouter's free models share one budget**: every ":free" model counts against one daily cap
  of the account (the provider "OpenRouter", never a model). GET /api/v1/key is read (no redirect
  followed) only for is_free_tier: the documented cap stays, and the signing notice says when the
  account is not on the free tier.

    ai-quota.py merge --state quota.json --delta FILE [--delta FILE ...]   (the job that writes the branch)
    ai-quota.py ran --state quota.json --result answered|no-provider
    ai-quota.py show --state quota.json [--limits tools/ai-quota.json]
    ai-quota.py gate --state quota.json --provider NAME --tokens N [--purpose fix|review] [--candidate ID]
                     [--available A,B,C] [--tier-b] [--memory memory.json] (exit 0: it may be asked)
    ai-quota.py priority --candidate ID [--state quota.json] [--memory memory.json]
                     (the class of a branch and whether background work may run now; for the logs)
"""

import argparse
import datetime as dt
import json
import math
import re
import sys
import time
from pathlib import Path

BRANCH = "automat/memory"
FILE = "quota.json"
LIMITS = Path(__file__).resolve().parent / "ai-quota.json"
SCHEMA = 1
KEEP_DAYS = 8
MAX_BYTES = 96 * 1024
NAMES = ("Antigravity", "Groq", "Z.AI", "OpenRouter")
# what is used when the data file cannot be read: very little, so nothing is drained by mistake
FALLBACK = {"requests_per_day": 10, "requests_per_minute": 2, "tokens_per_day": 50000, "tokens_per_minute": 6000,
            "session_requests": 10, "verified": False, "source": "tools/ai-quota.json could not be read",
            "headers": {}, "day_words": ["per day", "daily"], "minute_words": ["per minute", "concurrency"]}
LIMIT_KEYS = ("requests_per_day", "requests_per_minute", "tokens_per_day", "tokens_per_minute")
PURPOSES = ("fix", "review")
# the classes of AI work (the owner's decision of 2026-11-24): the lower, the sooner
SECURITY, UPDATE, CI, BACKGROUND = 1, 2, 3, 4
CLASSES = {SECURITY: "security fix", UPDATE: "update of what ships", CI: "CI and tools", BACKGROUND: "background"}
CLASS_IT = {SECURITY: "correzione di sicurezza", UPDATE: "aggiornamento di ciò che arriva agli utenti",
            CI: "aggiornamento della CI e degli strumenti", BACKGROUND: "lavoro di fondo"}
# what is used when tools/ai-quota.json has no "priority" (or a value cannot be read)
PRIORITY = {"security": ("automation/update/security-",), "ci": ("automation/update/ci-",),
            "background": ("automation/update/drill-", "automation/bench/", "automation/evolve/"),
            "release_hours": 3, "pending_days": 2, "maintenance_window": {"start": "04:00", "end": "12:00"}}
# a reset the provider's own headers gave is used only this close to now
OBSERVED_RESET_MAX = 2 * 86400
# a branch is only ever made a background one by a prefix of the automation's own work, and never a
# security fix's or a real update's own branch prefix as a whole
NEVER_LOW = ("automation/update/", "automation/builder/", "automation/update/security-", "automation/daily-maintenance",
             "automation/autofix-main")
# the long-lived branches of the maintenance: never "closed" for the priority (their pull request is closed and
# opened again while the work goes on: a broken main's fix retrying stays pending)
LONG_LIVED = ("automation/autofix-main", "automation/daily-maintenance", "automation/audit")
# the pending work could not be read (the plan's call to GitHub failed): background work pauses, real work never
UNKNOWN = "unknown"
# the start of the reason a fix waits for the reviewers' reserve (tools/autofix-reserve.py reads it)
RESERVE_WHY = "the reviewers' reserve"
# the tokens a fix is counted as when its request is not built yet (way_forward): a request fitted to a small limit
# per minute (tools/autofix-reserve.py fitted), with its answer
FIX_TOKENS = 4000
# the watchdog (2026-11-25): a branch whose runs asked no provider at all for this many days in a row is named in the
# notices ("niente deve rimanere indietro")
UNASKED_DAYS = 2
MAX_UNASKED = 40
RESET = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
ZONE = re.compile(r"^[A-Za-z][A-Za-z0-9_+/-]{0,60}$")


def now_utc(now=None):
    return now or dt.datetime.now(dt.timezone.utc)


def day_of(now=None):
    return now_utc(now).strftime("%Y-%m-%d")


def load_limits(path=None):
    """The limits of tools/ai-quota.json, checked; what cannot be read becomes the small FALLBACK."""
    try:
        data = json.loads(Path(path or LIMITS).read_text("utf-8"))
        assert isinstance(data, dict) and isinstance(data.get("providers"), dict)
    except (OSError, ValueError, AssertionError):
        data = {"providers": {}}
    out = {"chars_per_token": 3, "share_per_candidate": 0.5, "providers": {},
           "reserve": {"reviews": 2, "reviews_tier_b": 3, "review_requests": 1, "review_tokens": 9000},
           "routing": data.get("routing") if isinstance(data.get("routing"), dict) else {}}
    cpt = data.get("chars_per_token")
    if isinstance(cpt, (int, float)) and not isinstance(cpt, bool) and 1 <= cpt <= 8:
        out["chars_per_token"] = cpt
    share = data.get("share_per_candidate")
    if isinstance(share, (int, float)) and not isinstance(share, bool) and 0 < share <= 1:
        out["share_per_candidate"] = share
    for key, value in (data.get("reserve") or {}).items() if isinstance(data.get("reserve"), dict) else ():
        if key in out["reserve"] and isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            out["reserve"][key] = value
    # never fewer reviewers than the merge asks for (tools/ai-review.py NEEDED, tools/tier-b.py REVIEWS)
    out["reserve"]["reviews"] = max(2, out["reserve"]["reviews"])
    out["reserve"]["reviews_tier_b"] = max(3, out["reserve"]["reviews_tier_b"])
    out["priority"] = load_priority(data.get("priority"))
    for name in NAMES:
        raw = data["providers"].get(name)
        conf = dict(FALLBACK)
        if isinstance(raw, dict):
            for key in LIMIT_KEYS + ("session_requests",):
                value = raw.get(key, conf.get(key))
                conf[key] = value if value is None or (isinstance(value, int) and not isinstance(value, bool)
                                                       and value >= 0) else FALLBACK.get(key)
            conf["verified"] = raw.get("verified") is True
            conf["source"] = str(raw.get("source") or "")[:600]
            conf["headers"] = raw.get("headers") if isinstance(raw.get("headers"), dict) else {}
            for field in ("day_words", "minute_words"):
                words = raw.get(field)
                conf[field] = [str(w) for w in words][:24] if isinstance(words, list) else FALLBACK[field]
            # a 429 of one free model's own pool, busy upstream (per_model): data too, none by default
            words = raw.get("model_words")
            conf["model_words"] = [str(w) for w in words][:24] if isinstance(words, list) else []
            # how a 429 is read is data too (rate_limit_scope): the wait above which it is the day's quota
            wait = raw.get("day_wait_seconds")
            conf["day_wait_seconds"] = wait if isinstance(wait, int) and not isinstance(wait, bool) and \
                60 <= wait <= 86400 else DAY_WAIT
            conf["reset"] = _reset(raw.get("reset"))
            conf["shared_free_models"] = raw.get("shared_free_models") is True
            account = raw.get("account")
            if isinstance(account, dict):
                value = account.get("free_tier_requests_per_day")
                if isinstance(value, int) and not isinstance(value, bool) and 0 < value <= 100000:
                    conf["account"] = {"free_tier_requests_per_day": value}
        out["providers"][name] = conf
    return out


def load_priority(raw):
    """The "priority" of tools/ai-quota.json, checked: what cannot be read is the default (PRIORITY)."""
    raw = raw if isinstance(raw, dict) else {}
    out = {}
    for key in ("security", "ci", "background"):
        value = raw.get(key)
        if isinstance(value, list) and value:
            good = tuple(str(p) for p in value if _good_prefix(p, key))
            out[key] = good if good else PRIORITY[key]
        else:
            out[key] = PRIORITY[key]
    # TEMPORARY (the owner, 2026-11-27): until this date (UTC, inclusive) the AUTOMAT drill (automation/update/
    # drill-*) may use the free quotas at any hour, not only in the leftover window, while no real update is
    # pending; then the rule of 2026-11-24 is back by itself. Removed once the drill succeeds with the free AIs
    until = str(raw.get("drill_any_hour_until") or "")
    if re.fullmatch(r"\d{4}-\d\d-\d\d", until):
        out["drill_any_hour_until"] = until
    for key, low, high in (("release_hours", 0, 12), ("pending_days", 1, 7)):
        value = raw.get(key)
        ok = isinstance(value, (int, float)) and not isinstance(value, bool) and low <= value <= high
        out[key] = value if ok else PRIORITY[key]
    win = raw.get("maintenance_window") if isinstance(raw.get("maintenance_window"), dict) else {}
    good = all(RESET.match(str(win.get(k) or "")) for k in ("start", "end")) and win.get("start") != win.get("end")
    out["maintenance_window"] = {"start": win["start"], "end": win["end"]} if good else \
        dict(PRIORITY["maintenance_window"])
    return out


def _good_prefix(p, key):
    """A prefix of the classes: a branch prefix of the automation that ends in "-" or "/" and is at least one
    segment longer than automation/<word>/ when it is under automation/update/ or automation/builder/; a
    background or CI prefix is never a prefix of a real update's own branches."""
    if not isinstance(p, str) or not p.startswith("automation/") or not p.endswith(("-", "/")) or ".." in p:
        return False
    if not re.fullmatch(r"automation/[a-z0-9._/-]{2,80}", p) or "//" in p or p.count("/") < 2:
        return False
    if p.startswith(("automation/update/", "automation/builder/")) and len(p.split("/", 2)[2]) < 2:
        return False
    return key == "security" or not any(n.startswith(p) for n in NEVER_LOW)


def _reset(raw):
    """A provider's day: {"time": "HH:MM", "zone": IANA name, "verified": bool}; the repository's day (UTC)
    when it cannot be read."""
    raw = raw if isinstance(raw, dict) else {}
    when = str(raw.get("time") or "")
    zone = str(raw.get("zone") or "")
    return {"time": when if RESET.match(when) else "00:00", "zone": zone if ZONE.match(zone) else "UTC",
            "verified": raw.get("verified") is True}


def priority_of(candidate, limits=None):
    """The class of a piece of AI work by its branch (or the candidate's id, automation/update/<id>):
    1 security, 2 an update of what ships (also anything unknown: never starved), 3 CI and tools,
    4 background."""
    pr = (limits or {}).get("priority") or PRIORITY
    ref = str(candidate or "").strip()
    if ref and not ref.startswith("automation/"):
        ref = "automation/update/" + ref
    if ref.startswith(tuple(pr.get("security") or PRIORITY["security"])):
        return SECURITY
    if ref.startswith(tuple(pr.get("background") or PRIORITY["background"])):
        return BACKGROUND
    if ref.startswith(tuple(pr.get("ci") or PRIORITY["ci"])):
        return CI
    return UPDATE


def pending_work(memory, limits=None, now=None):
    """The work of class 1 or 2 that is pending or retrying, from AUTOMAT's memory (tools/automat-memory.py):
    a component whose row of failures (or whose published fix waiting for its tests) was written in the last
    pending_days days. A merged fix ends the row, so a component in it has not reached main yet."""
    pr = (limits or {}).get("priority") or PRIORITY
    days = int(pr.get("pending_days") or PRIORITY["pending_days"])
    since = (now_utc(now).date() - dt.timedelta(days=days - 1)).isoformat()
    out = []
    streak = (memory or {}).get("streak") if isinstance(memory, dict) else None
    for component, row in (streak or {}).items() if isinstance(streak, dict) else ():
        if not isinstance(row, dict) or str(row.get("date") or row.get("since") or "") < since:
            continue
        if is_closed(component, row):
            continue
        if re.fullmatch(r"[A-Za-z0-9._/-]{1,120}", str(component)) and priority_of(component, limits) <= UPDATE:
            out.append(str(component))
    return sorted(out)


STAMP = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
DAY = re.compile(r"^\d{4}-\d\d-\d\d$")


def after_last_failure(moment, row):
    """True when moment (a UTC time, "YYYY-MM-DDTHH:MM:SSZ" as GitHub writes it) is strictly after the row's last
    failure: its time ("at", written by tools/automat-memory.py), or for an older row with only a date, a later
    day (the same day is not enough: the failure may have come after)."""
    moment = str(moment or "")
    if not STAMP.match(moment) or not isinstance(row, dict):
        return False
    at = str(row.get("at") or "")
    if STAMP.match(at):
        return moment > at
    day = str(row.get("date") or row.get("since") or "")
    return bool(DAY.match(day)) and moment[:10] > day


def is_closed(component, row):
    """True when the row was marked closed (tools/automat-memory.py closed marks it, never deletes it) strictly
    after its last failure: the row stays for the count of failures in a row, and is only left out of the
    priority. Never for a long-lived branch of the maintenance."""
    return str(component) not in LONG_LIVED and after_last_failure((row or {}).get("closed"), row)


GREEN = ("success", "skipped", "neutral")


def latest_runs(runs):
    """Only the newest run of each workflow (a cancelled or superseded run of the same workflow no longer
    counts); a run that names no workflow counts on its own."""
    out, seen = [], set()
    ordered = sorted((r for r in runs if isinstance(r, dict)), key=lambda r: str(r.get("created_at") or ""),
                     reverse=True)
    for n, r in enumerate(ordered):
        key = r.get("workflow_id") or r.get("path") or r.get("name") or ("#", n)
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def pending_from_prs(repo, api, limits=None):
    """The work of class 1 or 2 that is pending from GitHub itself: an open pull request of the automation
    (automation/update/*, automation/builder/*, automation/daily-maintenance, automation/autofix-main) whose last
    commit has a run that is not green (failed, cancelled, or still running; only the newest run of each
    workflow counts): {"pending": [...], "open": [...]},
    where "open" is every branch of the automation with an open pull request. GET calls only; a branch whose
    runs cannot be read counts as pending (rather wait than starve real work)."""
    out = {"pending": [], "open": []}
    for page in range(1, 6):
        prs = api("repos/%s/pulls?state=open&per_page=100&page=%d" % (repo, page)) or []
        for pr in prs:
            head = pr.get("head") or {}
            ref, sha = str(head.get("ref") or ""), str(head.get("sha") or "")
            if not ref.startswith("automation/") or not re.fullmatch(r"[A-Za-z0-9._/-]{1,120}", ref):
                continue
            out["open"].append(ref)
            if priority_of(ref, limits) > UPDATE or not re.fullmatch(r"[0-9a-f]{40}", sha):
                continue
            try:
                runs = (api("repos/%s/actions/runs?head_sha=%s&per_page=50" % (repo, sha)) or {}).get(
                    "workflow_runs") or []
            except RuntimeError:
                out["pending"].append(ref)
                continue
            runs = latest_runs(runs)
            if not runs or any(r.get("status") != "completed" or r.get("conclusion") not in GREEN for r in runs):
                out["pending"].append(ref)
        if len(prs) < 100:
            break
    out["pending"] = sorted(set(out["pending"]))
    out["open"] = sorted(set(out["open"]))
    return out


def closed_branches(repo, api, refs, memory=None):
    """Of these branches (none has an open pull request), those whose NEWEST pull request was closed (merged or
    not) strictly after the last failure of their row in AUTOMAT's memory (after_last_failure: full times):
    that work is over. Never a long-lived
    branch of the maintenance (LONG_LIVED), never a branch without a row, never one whose pull requests cannot
    be read: rather wait than drop real work."""
    out = []
    owner = repo.split("/")[0]
    streak = (memory or {}).get("streak") if isinstance(memory, dict) else None
    streak = streak if isinstance(streak, dict) else {}
    for ref in refs:
        row = streak.get(ref)
        if ref in LONG_LIVED or not isinstance(row, dict):
            continue
        try:
            got = api("repos/%s/pulls?state=all&head=%s:%s&sort=created&direction=desc&per_page=1"
                      % (repo, owner, ref)) or []
        except RuntimeError:
            continue
        newest = got[0] if isinstance(got, list) and got and isinstance(got[0], dict) else {}
        if newest.get("state") == "closed" and after_last_failure(newest.get("closed_at"), row):
            out.append(ref)
    return sorted(out)


def gather_prs(repo, api, memory=None, limits=None, now=None, runs=True):
    """pending_from_prs, and "closed": the memory's rows whose branch has no open pull request any more and whose
    newest pull request was closed strictly after the row's last failure (closed_branches; GET calls only)."""
    prs = pending_from_prs(repo, api, limits) if runs else {"pending": [], "open": []}
    if not runs:
        for page in range(1, 6):
            got = api("repos/%s/pulls?state=open&per_page=100&page=%d" % (repo, page)) or []
            prs["open"] += [str((x.get("head") or {}).get("ref") or "") for x in got]
            if len(got) < 100:
                break
        prs["open"] = sorted({r for r in prs["open"] if r.startswith("automation/")})
    rows = [r for r in pending_work(memory, limits, now) if r not in prs["open"]]
    prs["closed"] = closed_branches(repo, api, rows, memory)
    # 2026-11-27 (the drill): the row of a failure of main (automation/autofix-main) ends when main's tests are
    # green again after it, whoever fixed main (that evening a person's pull request did, and the row kept the
    # drill paused as if a real update were pending)
    if FIX_OF_MAIN in rows and main_green_since(repo, api, ((memory or {}).get("streak") or {}).get(FIX_OF_MAIN)):
        prs["closed"] = sorted(set(prs["closed"]) | {FIX_OF_MAIN})
    return prs


FIX_OF_MAIN = "automation/autofix-main"


def main_green_since(repo, api, row):
    """True when main's newest finished Tests run (a cancelled one skipped) passed and started after the row's last
    failure (after_last_failure). GET calls only; False when it cannot be read (rather wait than drop real work)."""
    if not isinstance(row, dict):
        return False
    try:
        runs = (api("repos/%s/actions/workflows/tests.yml/runs?branch=main&status=completed&per_page=10" % repo)
                or {}).get("workflow_runs") or []
    except Exception:                    # anything unread: rather wait than drop real work
        return False
    done = [r for r in runs if isinstance(r, dict) and r.get("conclusion") not in ("cancelled", "skipped")]
    return bool(done) and done[0].get("conclusion") == "success" and after_last_failure(done[0].get("created_at"), row)


def gh_api(path):
    """GitHub's API through gh (GET), for the CLI."""
    import subprocess
    out = subprocess.run(["gh", "api", path], capture_output=True, text=True)
    if out.returncode:
        raise RuntimeError("gh api %s: %s" % (path, out.stderr.strip()[:200]))
    return json.loads(out.stdout) if out.stdout.strip() else {}


def pending_all(memory, limits=None, now=None, prs=None):
    """The work of class 1 or 2 pending now: the open pull requests with checks that are not green (prs, from
    pending_from_prs) together with the rows of failures of AUTOMAT's memory (pending_work); when the open pull
    requests are known, a memory row of a branch whose newest pull request was closed after it is left out
    (closed_branches; never a long-lived branch). UNKNOWN in prs["pending"] stays: background work pauses."""
    rows = pending_work(memory, limits, now)
    if prs is not None:
        opened = set(prs.get("open") or ())
        closed = set(prs.get("closed") or ())
        rows = [r for r in rows if r in opened or r not in closed]
        rows += list(prs.get("pending") or ())
    return sorted({r for r in rows if priority_of(r, limits) <= UPDATE})


def _zone(name):
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(name)
    except Exception:
        return dt.timezone.utc


def provider_day(conf, now=None):
    """The provider's own day, as the date its current day began in its own zone (its "reset", verified or
    not): the key of its use in quota.json, so that a provider whose day ends at midnight in California is
    not counted on the day of UTC."""
    reset = (conf or {}).get("reset") or {"time": "00:00", "zone": "UTC"}
    hour, minute = (int(x) for x in reset.get("time", "00:00").split(":"))
    local = now_utc(now).astimezone(_zone(reset.get("zone") or "UTC"))
    start = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if start > local:
        start -= dt.timedelta(days=1)
    return start.date().isoformat()


def next_reset(conf, now=None, observed=None):
    """The next moment the provider's day starts again, in UTC: what its own headers said last (observed: a
    daily window's reset in seconds and when it was read, "at", in the last two days; a reset already past is
    rolled forward by whole days, so it keeps deciding), else its "reset" (a time in its own zone)."""
    now = now_utc(now)
    obs = observed if isinstance(observed, dict) else {}
    if obs.get("window") == "day" and isinstance(obs.get("reset"), int) and isinstance(obs.get("at"), int) \
            and obs["reset"] > 0 and obs["at"] >= now.timestamp() - OBSERVED_RESET_MAX:
        moment = dt.datetime.fromtimestamp(obs["at"] + obs["reset"], dt.timezone.utc)
        if moment <= now:
            # a reset already past: the provider's day starts again at the same time each day (whole days on)
            moment += dt.timedelta(days=math.floor((now - moment).total_seconds() / 86400) + 1)
        if now < moment <= now + dt.timedelta(seconds=OBSERVED_RESET_MAX):
            return moment
    reset = (conf or {}).get("reset") or {"time": "00:00", "zone": "UTC"}
    hour, minute = (int(x) for x in reset.get("time", "00:00").split(":"))
    zone = _zone(reset.get("zone") or "UTC")
    local = now.astimezone(zone)
    moment = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if moment <= local:
        moment = (local + dt.timedelta(days=1)).replace(hour=hour, minute=minute, second=0, microsecond=0)
    return moment.astimezone(dt.timezone.utc)


def account_tier(info):
    """What OpenRouter's GET /api/v1/key says of the account: "free" (is_free_tier true), "not-free" (false),
    or "" when the answer cannot be read. Nothing else of the answer is read: money (usage, limit: credits)
    is never requests, and the cap of the :free models stays the documented one of the data file."""
    data = info.get("data") if isinstance(info, dict) and isinstance(info.get("data"), dict) else None
    if not isinstance(data, dict) or not isinstance(data.get("is_free_tier"), bool):
        return ""
    return "free" if data["is_free_tier"] else "not-free"


def account_limit(conf, info):
    """OpenRouter's cap of requests a day for all its ":free" models together: the documented free-tier value
    when the account says it is on the free tier, else None (the file's value stays: never more)."""
    account = (conf or {}).get("account") or {}
    if account_tier(info) == "free" and account.get("free_tier_requests_per_day"):
        return account["free_tier_requests_per_day"]
    return None


def _no_redirects():
    """An opener that follows no redirect: the key's Authorization header never goes to another address."""
    import urllib.request

    class Refuse(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None
    return urllib.request.build_opener(Refuse()).open


def read_account(conf, key, opener=None, url="https://openrouter.ai/api/v1/key"):
    """GET /api/v1/key with the key (one call, no model is asked, nothing is counted, no redirect followed):
    its JSON, or None."""
    import urllib.request
    if not key:
        return None
    if opener is None or opener is urllib.request.urlopen:
        opener = _no_redirects()
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + key, "User-Agent": "IKE-autofix"})
    try:
        with opener(req, timeout=20) as r:
            if getattr(r, "status", 200) != 200:
                return None
            return json.loads(r.read(200_000).decode("utf-8", "replace"))
    except Exception:
        return None


def empty_state():
    return {"schema": SCHEMA, "days": {}}


def load_state(path):
    try:
        data = json.loads(Path(path).read_text("utf-8"))
    except (OSError, ValueError, TypeError):
        return empty_state()
    if not isinstance(data, dict) or data.get("schema") != SCHEMA or not isinstance(data.get("days"), dict):
        return empty_state()
    return data


def _day(state, day):
    d = state["days"].setdefault(day, {})
    d.setdefault("providers", {})
    for key in ("runs", "answered", "no_provider"):
        d[key] = int(d.get(key) or 0)
    return d


def _prov(state, day, name):
    p = _day(state, day)["providers"].setdefault(name, {})
    p["requests"] = int(p.get("requests") or 0)
    p["tokens"] = int(p.get("tokens") or 0)
    p.setdefault("by", {})
    p.setdefault("spent", "")
    p.setdefault("observed", {})
    if not isinstance(p.get("classes"), dict):
        p["classes"] = {}
    return p


def _add_class(p, klass, requests, tokens):
    """The day's use of one class of work (1 security ... 4 background): the reserve of classes 1 and 2."""
    row = p["classes"].setdefault(str(klass), {"requests": 0, "tokens": 0})
    row["requests"] = _count(row.get("requests")) + requests
    row["tokens"] = _count(row.get("tokens")) + tokens


def bound(state, now=None):
    """Only the last KEEP_DAYS days, and never more than MAX_BYTES."""
    keep = sorted(state["days"])[-KEEP_DAYS:]
    state["days"] = {d: state["days"][d] for d in keep}
    while len(json.dumps(state)) > MAX_BYTES and len(state["days"]) > 1:
        del state["days"][min(state["days"])]
    return state


def estimate_tokens(chars, answer_tokens=0, limits=None):
    """The tokens a request of this many characters is counted as (a careful estimate: rather too many)."""
    per = (limits or {}).get("chars_per_token") or 3
    return int(math.ceil(max(0, int(chars)) / float(per))) + max(0, int(answer_tokens or 0))


def parse_duration(text):
    """Seconds of a rate-limit header: "7.66s", "2m59.56s", "1h2m3s", "120" (seconds), a time in
    milliseconds or seconds since 1970 (then: until that time). 0 when it cannot be read."""
    text = str(text or "").strip()
    if not text:
        return 0
    if re.fullmatch(r"\d+(?:\.\d+)?", text):
        value = float(text)
        if value > 10 ** 11:                      # milliseconds since 1970
            return max(0, int(value / 1000 - time.time()))
        if value > 10 ** 9:                       # seconds since 1970
            return max(0, int(value - time.time()))
        return int(math.ceil(value))
    m = re.fullmatch(r"(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m(?!s))?(?:(\d+(?:\.\d+)?)s)?(?:(\d+)ms)?", text)
    if not m or not any(m.groups()):
        return 0
    days, hours, minutes, seconds, ms = m.groups()
    total = int(days or 0) * 86400 + int(hours or 0) * 3600 + int(minutes or 0) * 60 + float(seconds or 0) + \
        int(ms or 0) / 1000.0
    return int(math.ceil(total))


def _header(headers, name):
    if not headers or not name:
        return None
    try:
        items = headers.items()
    except AttributeError:
        return None
    for key, value in items:
        if str(key).lower() == str(name).lower():
            return str(value)
    return None


def observe(conf, headers):
    """What an answer's rate-limit headers say: {"requests" | "tokens": {"limit", "remaining", "reset",
    "window"}} (only what is there and reads as a number); {} when the provider sends none."""
    out = {}
    for kind, names in ((conf or {}).get("headers") or {}).items():
        if kind not in ("requests", "tokens") or not isinstance(names, dict):
            continue
        seen = {}
        for field in ("limit", "remaining"):
            raw = _header(headers, names.get(field))
            if raw is not None and re.fullmatch(r"\d{1,12}", raw.strip()):
                seen[field] = int(raw.strip())
        reset = _header(headers, names.get("reset"))
        if reset is not None:
            seen["reset"] = parse_duration(reset)
        if "limit" in seen or "remaining" in seen:
            seen["window"] = "day" if names.get("window") == "day" else "minute"
            out[kind] = seen
    return out


def retry_after(headers):
    return parse_duration(_header(headers, "retry-after"))


def said(words, text):
    """True when the text says one of the words: a plain word anywhere (case ignored), a "code:N" only as the
    value of a "code" field (Z.AI's {"error": {"code": "1302", ...}}), never a number anywhere in the text."""
    text = str(text or "")
    for w in words or ():
        w = str(w or "")
        if not w:
            continue
        if w.startswith("code:"):
            if re.search(r'"code"\s*:\s*"?%s(?![0-9])' % re.escape(w[5:]), text):
                return True
        elif w.lower() in text.lower():
            return True
    return False


# a long wait the provider asks for: more than this is the day's quota, not a limit per minute
DAY_WAIT = 3600
# a mark "spent today" is checked again after this many seconds with one request (2026-11-25: a wrong mark,
# written before the reading of Z.AI's codes was fixed, kept Z.AI unasked for the rest of the day). A mark of
# money asked (not free) never expires; a mark with no time (written before this rule, or by hand) holds for the
# day as before
SPENT_RECHECK = 3 * 3600
NEVER_EXPIRES = ("money", "not free")


def mark_expired(why, at, now):
    """True when a mark "spent today" may be checked again (SPENT_RECHECK): never for money asked."""
    why = str(why or "")
    if not why or any(w in why for w in NEVER_EXPIRES):
        return False
    if not isinstance(at, int) or isinstance(at, bool) or at <= 0:
        return False
    return now - at >= SPENT_RECHECK


def per_model(conf, body):
    """True when a 429 is one free model's own pool, busy upstream (OpenRouter: "temporarily rate-limited
    upstream"): the next model is asked at once, and the provider's other models are not held back."""
    return said((conf or {}).get("model_words") or (), body)
# what a provider says of its limit per minute when a request is too large for it (Groq: "on tokens per minute
# (TPM): Limit 6000, Requested 7678"): the limit is learned and the next request is fitted to it
TPM_LIMIT = re.compile(r"(?:tokens per minute|\bTPM\b)\D{0,40}?\blimit\W{0,3}(\d{3,9})", re.I)


def learned_minute_tokens(body):
    """The limit of tokens per minute an error's text gives, or None."""
    m = TPM_LIMIT.search(str(body or ""))
    value = int(m.group(1)) if m else 0
    return value if 100 <= value <= 10 ** 8 else None


# Gemini's free tier publishes no numbers (ai.google.dev/gemini-api/docs/rate-limits, read on 2026-11-25: "can be
# viewed in Google AI Studio"); its 429 names the limit it hit and its value (google.rpc.QuotaFailure: quotaId
# "GenerateRequestsPerDayPerProjectPerModel-FreeTier", quotaValue "250"): the real quota of the project, learned
QUOTA_FAILURE = re.compile(r'quotaId\W{1,6}([A-Za-z0-9_-]{3,120})(?:(?!quotaId).){0,600}?quotaValue\W{1,6}(\d{1,9})',
                           re.S)


def learned_quotas(body):
    """{"day_requests", "minute_tokens"}: the limits a provider's own error names with their values (Gemini's
    QuotaFailure), each only when it is plausible."""
    out = {}
    for quota_id, value in QUOTA_FAILURE.findall(str(body or "")[:20000]):
        value, low = int(value), quota_id.lower()
        if not 0 < value <= 10 ** 8:
            continue
        if "request" in low and ("perday" in low or "daily" in low):
            out.setdefault("day_requests", value)
        elif "token" in low and "perminute" in low and value >= 100:
            out.setdefault("minute_tokens", value)
    return out


def body_headers(headers, body):
    """The headers of an answer with those its error body carries (OpenRouter puts X-RateLimit-* inside
    error.metadata.headers too: openrouter.ai/docs/api-reference/limits); the real headers count more."""
    out = {}
    try:
        meta = ((json.loads(body or "{}") or {}).get("error") or {}).get("metadata") or {}
        inner = meta.get("headers") if isinstance(meta, dict) else None
        if isinstance(inner, dict):
            out.update({str(k): str(v) for k, v in list(inner.items())[:20]})
    except (ValueError, AttributeError, TypeError):
        pass
    try:
        out.update({str(k): str(v) for k, v in (headers or {}).items()})
    except AttributeError:
        pass
    return out


def rate_limit_scope(conf, headers, body):
    """What a 429 means (2026-11-25: a limit of concurrency taken for the day's quota left Z.AI unused for days):
    ("minute", seconds to wait, why) for a limit per minute, of concurrency or a busy service, which is waited out
    in the same run; ("day", 0, why) only for the day's quota: the provider says so in words and not of a minute,
    its own headers say nothing is left of its day, or it asks to wait longer than its "day_wait_seconds" (data;
    DAY_WAIT when the file has none). The words are data too (day_words, minute_words). When nothing
    says which, a minute: one more request tomorrow costs less than a provider lost for a whole day."""
    conf = conf or {}
    headers = body_headers(headers, body)
    wait = retry_after(headers)
    daily = said(conf.get("day_words") or FALLBACK["day_words"], body)
    minute = said(conf.get("minute_words") or FALLBACK["minute_words"], body)
    seen = observe(conf, headers)
    day_empty = any(o.get("window") == "day" and o.get("remaining") == 0 for o in seen.values())
    minute_empty = [o for o in seen.values() if o.get("window") == "minute" and o.get("remaining") == 0]
    if wait > int(conf.get("day_wait_seconds") or DAY_WAIT):
        return "day", 0, "429: the quota of the day (retry after %d s)" % wait
    if day_empty and not minute_empty:
        return "day", 0, "429: the quota of the day (its headers say nothing is left today)"
    if daily and not minute:
        return "day", 0, "429: the quota of the day (it says so)"
    if not wait and minute_empty:
        wait = max([int(o.get("reset") or 0) for o in minute_empty] + [0])
    why = "429: a limit per minute or of concurrency (%s)" % (
        "it says so" if minute else "it does not say it is the day's")
    return "minute", min(max(wait, 0), 120) or 60, why


class Budget:
    """Today's budget of the providers, for one run. state is changed in memory only; delta() is what
    the run leaves for the job that writes the data branch."""

    def __init__(self, limits=None, state=None, candidate="", now=None, tier_b=False, available=None, clock=None,
                 pending=None):
        self.limits = limits or load_limits()
        self.limits.setdefault("priority", load_priority(None))
        self.state = state if isinstance(state, dict) and isinstance(state.get("days"), dict) else empty_state()
        self.candidate = str(candidate or "")[:120]
        self.tier_b = bool(tier_b)
        self.clock = clock or time.time
        self.started = self.clock()
        self.now = now_utc(now)
        self.day = day_of(now)
        # real updates first (2026-11-24): this run's class, and the work of class 1 or 2 still pending
        self.priority = priority_of(self.candidate, self.limits)
        self.pending = sorted({str(c) for c in pending or () if c == UNKNOWN or priority_of(c, self.limits) <= UPDATE})
        self.available = tuple(available) if available is not None else NAMES
        self.calls = []                 # [(provider, requests, tokens, purpose)] of this run
        self.recent = {}                # provider -> [(time, requests, tokens)] for the limits per minute
        self.blocked_until = {}         # provider -> time: a 429 with a short retry-after
        self.skipped = {}
        self.result = ""
        self.last_429 = {}              # provider -> (scope, wait, why) of its last 429 in this run
        # a fix may be written now and reviewed on a later day (way_forward: the deadlock of 2026-11-25)
        self.defer_reviews = False

    # --- what is left ---
    def conf(self, provider):
        return self.limits["providers"].get(provider) or dict(FALLBACK)

    def day_for(self, provider):
        """The key of the provider's own day in quota.json (provider_day)."""
        return provider_day(self.conf(provider), self.now)

    def _p(self, provider):
        return _prov(self.state, self.day_for(provider), provider)

    def used(self, provider):
        p = self._p(provider)
        return p["requests"], p["tokens"]

    def moment(self):
        """Now, in seconds since 1970 (the run's start and the time it has run)."""
        return int(self.now.timestamp() + max(0, self.clock() - self.started))

    def _mark(self, p, field):
        """The mark of the field, or "" once it is old enough to be checked again (mark_expired)."""
        why = p.get(field) or ""
        if why and mark_expired(why, p.get(field + "_at"), self.moment()):
            return ""
        return why

    def spent(self, provider):
        """Why the provider is spent today for this run's class ("" when it is not): a 429 that work of class 3
        or 4 got spends it only for classes 3 and 4 (spent_low), never for security fixes and real updates.
        A mark older than SPENT_RECHECK is checked again with one request (mark_expired)."""
        p = self._p(provider)
        if self.priority >= CI and self._mark(p, "spent_low"):
            return self._mark(p, "spent") or self._mark(p, "spent_low")
        return self._mark(p, "spent")

    def _set_mark(self, p, field, why):
        p[field] = str(why)[:120]
        p[field + "_at"] = self.moment()

    def day_limit(self, provider, kind):
        """Today's limit of requests or tokens: what the provider's own headers said, else the data file."""
        obs = (self._p(provider).get("observed") or {}).get(kind) or {}
        if obs.get("window") == "day" and isinstance(obs.get("limit"), int) and obs["limit"] > 0:
            return obs["limit"]
        return self.conf(provider).get("%s_per_day" % kind)

    def remaining(self, provider):
        """{"requests": n or None, "tokens": n or None} left today (None: no daily limit known)."""
        p = self._p(provider)
        out = {}
        for kind in ("requests", "tokens"):
            limit = self.day_limit(provider, kind)
            left = None if limit is None else max(0, limit - p[kind])
            obs = (p.get("observed") or {}).get(kind) or {}
            if obs.get("window") == "day" and isinstance(obs.get("remaining"), int):
                # the provider's own count, less what was asked since it was read
                since = max(0, p[kind] - int(obs.get("mark") or 0))
                left = max(0, obs["remaining"] - since)
            out[kind] = left
        return out

    def _room(self, provider, requests, tokens):
        left = self.remaining(provider)
        if left["requests"] is not None and left["requests"] < requests:
            return "its requests of today are used up (%d left, %d needed)" % (left["requests"], requests)
        if left["tokens"] is not None and left["tokens"] < tokens:
            return "its tokens of today are used up (%d left, %d needed)" % (left["tokens"], tokens)
        per_minute = self.minute_limit(provider, "tokens")
        if per_minute is not None and tokens > per_minute:
            return "the request is larger than its limit per minute (%d tokens, %d a minute)" % (tokens, per_minute)
        return ""

    def minute_limit(self, provider, kind):
        obs = (self._p(provider).get("observed") or {}).get(kind) or {}
        if obs.get("window") == "minute" and isinstance(obs.get("limit"), int) and obs["limit"] > 0:
            return obs["limit"]
        return self.conf(provider).get("%s_per_minute" % kind)

    # --- real updates first (the owner's decision of 2026-11-24) ---
    def account(self, provider, info):
        """What the provider's account says about its day (OpenRouter's GET /api/v1/key): whether it is on the free
        tier (recorded for the signing notice) and then the documented cap of requests a day that all its free
        models share. True when the free tier's cap was taken; otherwise the file's value stays."""
        if provider not in self.limits["providers"]:
            return False
        p = self._p(provider)
        tier = account_tier(info)
        if tier:
            p["account"] = tier
        limit = account_limit(self.conf(provider), info)
        if not limit:
            return False
        obs = p["observed"].get("requests") or {}
        if obs.get("window") == "day" and isinstance(obs.get("remaining"), int):
            obs["limit"] = limit               # the headers' own count of the day stays
        else:
            p["observed"]["requests"] = {"limit": limit, "window": "day", "mark": p["requests"], "account": True}
        return True

    def class_used(self, provider, classes=(SECURITY, UPDATE)):
        """(requests, tokens) used today by the work of these classes."""
        by = self._p(provider).get("classes") or {}
        return (sum(int((by.get(str(c)) or {}).get("requests") or 0) for c in classes),
                sum(int((by.get(str(c)) or {}).get("tokens") or 0) for c in classes))

    def next_reset(self, provider):
        obs = (self._p(provider).get("observed") or {}).get("requests")
        return next_reset(self.conf(provider), self.now, obs)

    def in_maintenance(self):
        """True while the real day's maintenance runs (maintenance_window, UTC: the security tests, the daily
        check and candidates, and their automatic fixes): the day's real needs are not known yet."""
        win = self.limits["priority"].get("maintenance_window") or PRIORITY["maintenance_window"]
        minute = self.now.hour * 60 + self.now.minute
        start, end = (int(win[k][:2]) * 60 + int(win[k][3:]) for k in ("start", "end"))
        return start <= minute < end if start <= end else (minute >= start or minute < end)

    def leftover_window(self, provider):
        """(True, why) when the background (classes 3 and 4) may take this provider's leftovers now, by the
        clock alone: only in the last release_hours hours of the provider's own day, never while its day has
        more than that left. A reset a person verified: the provider's own reset header counts more than the
        data file. One not verified is more careful: the later of the data file's reset (its "reset", even
        unverified) and the header's, and never during the real day's maintenance window (UTC), when the
        day's real needs are not known yet. (False, why not) otherwise."""
        conf = self.conf(provider)
        release = float(self.limits["priority"]["release_hours"])
        hours = (self.next_reset(provider) - self.now).total_seconds() / 3600.0
        checked = bool((conf.get("reset") or {}).get("verified"))
        if not checked:
            hours = max(hours, (next_reset(conf, self.now) - self.now).total_seconds() / 3600.0)
            if self.in_maintenance():
                win = self.limits["priority"].get("maintenance_window") or PRIORITY["maintenance_window"]
                return False, ("its reset is not verified: the background waits until the real day's maintenance "
                               "is over (%s-%s UTC)" % (win["start"], win["end"]))
        if hours <= release:
            return True, "the last %.1f hours of its day%s" % (hours, "" if checked else " (its reset is not verified)")
        return False, ("its day's leftovers go to the background only in its last %s hours (%.1f hours to its "
                       "%sreset)" % (self.limits["priority"]["release_hours"], hours, "" if checked else "unverified "))

    def drill_any_hour(self):
        """True while the owner's temporary rule holds (priority "drill_any_hour_until", a date of today or later)
        for this run, which is the drill's (automation/update/drill-*)."""
        until = self.limits["priority"].get("drill_any_hour_until") or ""
        return bool(until) and self.candidate.startswith("automation/update/drill-") and \
            self.now.date().isoformat() <= until

    def paused(self, provider=None):
        """Why work of class 3 or 4 pauses now ("" when it may run): work of class 1 or 2 is pending or retrying.
        Never lifted while it is: real updates may always use everything."""
        if not self.pending:
            return ""
        if UNKNOWN in self.pending:
            return ("paused for real updates first: the pending security fixes and real updates could not be read "
                    "(unknown), so the background waits")
        return ("paused for real updates first: work of class 1 or 2 is pending or retrying (%s)"
                % ", ".join(self.pending[:4]) + (" and %d more" % (len(self.pending) - 4) if len(self.pending) > 4 else ""))

    def priority_why(self, provider, requests=1, tokens=0, purpose="fix", klass=None):
        """"" when work of this class may ask the provider now, else why not (the owner's rule of 2026-11-24):
        security fixes and real updates (classes 1 and 2) may always use all of every free quota; the CI's
        updates and background work (classes 3 and 4) only what real work leaves: never while work of class 1 or
        2 is pending, and only in the provider's leftover window (leftover_window). Then everything left is
        theirs (the provider's own limits still hold)."""
        klass = self.priority if klass is None else klass
        if klass <= UPDATE:
            return ""
        why = self.paused(provider)
        if why:
            return why
        if self.drill_any_hour():
            return ""                    # the owner's temporary rule: the drill at any hour, nothing real pending
        ok, why = self.leftover_window(provider)
        return "" if ok else "class %d (%s) uses only what real work leaves: %s" % (klass, CLASSES[klass], why)

    def others_pending(self):
        """The other security fixes and real updates pending now, besides this run's own (UNKNOWN is none)."""
        mine = self.candidate if self.candidate.startswith("automation/") else "automation/update/" + self.candidate
        return [c for c in self.pending if c != UNKNOWN and c not in (self.candidate, mine)]

    def reviewers_left(self, author):
        """The providers other than the author that still have room for one review today (for this run's
        class: a background fix whose reviews would have to take the reserve waits too)."""
        r = self.limits["reserve"]
        return [n for n in self.available if n != author and n in self.limits["providers"] and not self.spent(n)
                and not self._room(n, r["review_requests"], self.review_size(n))
                and not self.priority_why(n, r["review_requests"], self.review_size(n), "review")]

    def review_size(self, provider):
        """The tokens one review is counted as for this provider: the reserve's review_tokens, within the provider's
        limit per minute (the same rule as background_status; 2026-11-25: Groq's 6,000 tokens a minute against
        9,000 made it never count as a reviewer, whatever was left of its day)."""
        size = self.limits["reserve"]["review_tokens"]
        return min(size, self.minute_limit(provider, "tokens") or size)

    def reviewers_ever(self, author):
        """The providers other than the author that could review a fix on some day (a key, not marked unavailable),
        whatever is left of today."""
        return [n for n in self.available if n != author and n in self.limits["providers"]]

    def reviews_needed(self):
        r = self.limits["reserve"]
        return r["reviews_tier_b"] if self.tier_b else r["reviews"]

    def allows(self, provider, tokens, purpose="fix", requests=1):
        """(True, "") when the provider may be asked now for this size and purpose, else (False, why)."""
        if provider not in self.limits["providers"]:
            return False, "not a provider of AUTOMAT"
        if self.spent(provider):
            return False, "spent today (%s)" % self.spent(provider)
        why = self._room(provider, requests, tokens)
        if why:
            return False, why
        why = self.priority_why(provider, requests, tokens, purpose)
        if why:
            return False, why
        if purpose == "fix":
            p = self._p(provider)
            mine = p["by"].get(self.candidate) or {}
            share = self.limits["share_per_candidate"]
            # the share holds only while ANOTHER security fix or real update is pending at the same time (two
            # real updates share a provider fairly); a lone one may use all of it (the owner, 2026-11-24)
            for kind, need in (("requests", requests), ("tokens", tokens)) if self.others_pending() else ():
                limit = self.day_limit(provider, kind)
                if limit is None or not self.candidate:
                    continue
                most = max(1 if kind == "requests" else need, int(limit * share))
                if int(mine.get(kind) or 0) + need > most:
                    return False, ("this candidate already used its share of today's %s (%d of %d; while another "
                                   "real update is pending, at most %d%% of a provider's day goes to one candidate)" % (
                                       kind, int(mine.get(kind) or 0), limit, int(share * 100)))
            if self.defer_reviews and self.priority <= UPDATE:
                # the way forward when the reserve would leave every provider unasked (way_forward): the fix is
                # written now and waits for its reviews on a later day. Never merged without them
                # (tools/automerge.py requires the status ai-review), and only when enough other providers could
                # review it at all
                ever = self.reviewers_ever(provider)
                if len(ever) < self.reviews_needed():
                    return False, ("%s: after a fix by %s only %d other provider(s) could ever review it (%s), and "
                                   "%d are needed: the fix waits" % (RESERVE_WHY, provider, len(ever),
                                                                     ", ".join(ever) or "none", self.reviews_needed()))
                return True, ""
            left = self.reviewers_left(provider)
            if len(left) < self.reviews_needed():
                return False, ("%s: after a fix by %s only %d other provider(s) would have room "
                               "for a review today (%s), and %d are needed: the fix waits" % (
                                   RESERVE_WHY, provider, len(left), ", ".join(left) or "none", self.reviews_needed()))
        return True, ""

    def way_forward(self, names, sizes=None):
        """Who writes the fix, when the reviewers' reserve alone would leave every provider unasked (the deadlock
        of 2026-11-25, PR #111: nobody was asked for three days). names: the providers in the order of this
        attempt; sizes: {name: (tokens, requests)} of a fix by each (default: FIX_TOKENS, one request). Returns
        (name, "now") for the first one allows() lets through; else (name, "reviews-later") for the one that,
        asked with its reviews left for a later day (defer_reviews), leaves the most reviewers with room today
        (the order of names breaks a tie); else (None, why). Only for security fixes and real updates (classes 1
        and 2): background work simply waits. The fix is never merged without its reviews."""
        sizes = sizes or {}
        names = [n for n in names if n in self.limits["providers"]]
        why = ""
        for n in names:
            tokens, requests = sizes.get(n, (FIX_TOKENS, 1))
            ok, no = self.allows(n, tokens, "fix", requests)
            if ok:
                return n, "now"
            why = why or "%s: %s" % (n, no)
        if self.priority > UPDATE or self.defer_reviews:
            return None, why
        best = []
        self.defer_reviews = True
        try:
            for n in names:
                tokens, requests = sizes.get(n, (FIX_TOKENS, 1))
                if self.allows(n, tokens, "fix", requests)[0]:
                    best.append((-len(self.reviewers_left(n)), names.index(n), n))
        finally:
            self.defer_reviews = False
        if best:
            return min(best)[2], "reviews-later"
        return None, why

    def wait_seconds(self, provider, tokens, requests=1):
        """Seconds until the provider's limit per minute has room for this request (0: now)."""
        now = self.clock()
        wait = max(0, self.blocked_until.get(provider, 0) - now)
        recent = [(t, r, k) for t, r, k in self.recent.get(provider, []) if now - t < 60]
        self.recent[provider] = recent
        for kind, need, index in (("requests", requests, 1), ("tokens", tokens, 2)):
            limit = self.minute_limit(provider, kind)
            if limit is None:
                continue
            used = sum(x[index] for x in recent)
            if used + need > limit and recent:
                # the oldest calls leave the window one after the other
                free, acc = 0, used
                for t, r, k in recent:
                    acc -= (r if index == 1 else k)
                    free = t + 60 - now
                    if acc + need <= limit:
                        break
                wait = max(wait, free)
        return int(math.ceil(wait))

    def pick(self, names, tokens, purpose="fix", requests=1):
        """The providers of names, in order, that may be asked; the others are remembered with the reason."""
        out = []
        for n in names:
            ok, why = self.allows(n, tokens, purpose, requests)
            if ok:
                out.append(n)
            else:
                self.skipped[n] = why
        return out

    # --- what was asked, and what the provider said ---
    def note(self, provider, tokens, purpose="fix", requests=1, usage=None, headers=None, status=200, body=""):
        """One call (or one session of the agent): counted, and the budget corrected by the answer: the
        real token count when the answer gives it, its rate-limit headers, a 429 and its retry-after."""
        if provider not in self.limits["providers"]:
            return
        conf = self.conf(provider)
        real = None
        if isinstance(usage, dict):
            value = usage.get("total_tokens") or usage.get("totalTokenCount")
            if isinstance(value, int) and not isinstance(value, bool) and 0 < value < 10 ** 8:
                real = value
        tokens = int(real if real is not None else max(0, int(tokens or 0)))
        requests = max(0, int(requests))
        p = self._p(provider)
        p["requests"] += requests
        p["tokens"] += tokens
        if self.candidate and purpose == "fix":
            mine = p["by"].setdefault(self.candidate, {"requests": 0, "tokens": 0})
            mine["requests"] = int(mine.get("requests") or 0) + requests
            mine["tokens"] = int(mine.get("tokens") or 0) + tokens
        _add_class(p, self.priority, requests, tokens)
        self.calls.append({"provider": provider, "requests": requests, "tokens": tokens,
                           "purpose": purpose if purpose in PURPOSES else "fix"})
        self.recent.setdefault(provider, []).append((self.clock(), requests, tokens))
        seen = observe(conf, headers)
        for kind, obs in seen.items():
            obs["mark"] = p[kind]
            # when it was read, so that a reset of the day can be placed in time (next_reset)
            obs["at"] = int(self.now.timestamp() + max(0, self.clock() - self.started))
            p["observed"][kind] = obs
            if obs.get("window") == "day" and obs.get("remaining") == 0:
                self._set_mark(p, "spent", "its own headers say nothing is left today")
            if obs.get("window") == "minute" and obs.get("remaining") == 0 and obs.get("reset"):
                self.blocked_until[provider] = self.clock() + min(obs["reset"], 120)
        if status in (413, 429):
            # a request larger than the provider's limit per minute: its own text gives the limit, learned for the
            # rest of its day (the next request is fitted to it: tools/autofix-reserve.py fitted)
            tpm = learned_minute_tokens(body)
            if tpm:
                p["observed"]["tokens"] = {"limit": tpm, "window": "minute", "mark": p["tokens"], "learned": True,
                                           "at": int(self.now.timestamp() + max(0, self.clock() - self.started))}
        if status == 429:
            self.learn(provider, body)
            scope, wait, why = rate_limit_scope(conf, headers, body)
            self.last_429[provider] = (scope, wait, why)
            if scope == "day":
                # work of class 3 or 4 spends it only for itself: security fixes and real updates still ask
                self._set_mark(p, "spent_low" if self.priority >= CI else "spent", why)
            elif not per_model(conf, body):
                # one free model busy upstream holds back only that model, never the provider's others
                self.blocked_until[provider] = max(self.blocked_until.get(provider, 0), self.clock() + wait)
        elif status == 402:
            self._set_mark(p, "spent", "it asked for money (not free)")

    def learn(self, provider, body):
        """The limits the provider's own error names with their values (learned_quotas), kept for the rest of its
        day like a reading of its headers: Gemini's real quota of requests a day, and of tokens a minute."""
        if provider not in self.limits["providers"]:
            return {}
        found = learned_quotas(body)
        p = self._p(provider)
        at = self.moment()
        if found.get("day_requests"):
            p["observed"]["requests"] = {"limit": found["day_requests"], "window": "day", "mark": p["requests"],
                                         "learned": True, "at": at}
        if found.get("minute_tokens") and (p["observed"].get("tokens") or {}).get("window") != "day":
            p["observed"]["tokens"] = {"limit": found["minute_tokens"], "window": "minute", "mark": p["tokens"],
                                       "learned": True, "at": at}
        return found

    def mark_spent(self, provider, why):
        """Spent today: for everybody, except a quota answer (429) that work of class 3 or 4 got."""
        if provider in self.limits["providers"]:
            low = self.priority >= CI and "429" in str(why)
            self._set_mark(self._p(provider), "spent_low" if low else "spent", why)

    def delta(self):
        """What this run adds, for the job that writes the data branch (numbers and known names only); each
        provider's use goes to its own day (days)."""
        mine = {n: self._p(n) for n in NAMES if n in self.limits["providers"]}
        return {"schema": SCHEMA, "day": self.day, "days": {n: self.day_for(n) for n in mine},
                "candidate": self.candidate, "calls": self.calls,
                "spent": {n: p.get("spent") for n, p in mine.items() if p.get("spent")},
                "spent_low": {n: p.get("spent_low") for n, p in mine.items() if p.get("spent_low")},
                "spent_at": {n: {f: p.get(f + "_at") for f in ("spent", "spent_low") if p.get(f + "_at")}
                             for n, p in mine.items() if p.get("spent_at") or p.get("spent_low_at")},
                "accounts": {n: p.get("account") for n, p in mine.items() if p.get("account") in ("free", "not-free")},
                "observed": {n: p.get("observed") for n, p in mine.items() if p.get("observed")},
                "skipped": dict(self.skipped), "result": self.result}


def _text(value, limit=160):
    return re.sub(r"\s+", " ", re.sub(r"[\x00-\x1f\x7f`<>]+", " ", str(value or ""))).strip()[:limit]


def _count(value, most=10 ** 8):
    return value if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= most else 0


def merge(state, delta, now=None):
    """A run's delta added to the state (checked: only known providers, counts and short texts)."""
    if not isinstance(delta, dict) or delta.get("schema") != SCHEMA:
        return state
    day = str(delta.get("day") or "")
    if not re.fullmatch(r"\d{4}-\d\d-\d\d", day) or abs(
            (dt.date.fromisoformat(day) - now_utc(now).date()).days) > 1:
        return state                               # not of today (or yesterday, around midnight)
    days = delta.get("days") if isinstance(delta.get("days"), dict) else {}

    def day_of_provider(name):
        """The provider's own day the run gave, when it is a date of today or yesterday; else the run's day."""
        value = str(days.get(name) or "")
        if re.fullmatch(r"\d{4}-\d\d-\d\d", value):
            try:
                if abs((dt.date.fromisoformat(value) - now_utc(now).date()).days) <= 1:
                    return value
            except ValueError:
                pass
        return day
    candidate = _text(delta.get("candidate"), 120)
    # the class of the run's work, by its branch (the reserve of classes 1 and 2 is counted per day)
    klass = priority_of(candidate if re.fullmatch(r"[A-Za-z0-9._/-]{1,120}", candidate) else "", load_limits())
    for call in (delta.get("calls") or [])[:400] if isinstance(delta.get("calls"), list) else ():
        if not isinstance(call, dict) or call.get("provider") not in NAMES:
            continue
        p = _prov(state, day_of_provider(call["provider"]), call["provider"])
        requests, tokens = _count(call.get("requests"), 10 ** 4), _count(call.get("tokens"))
        p["requests"] += requests
        p["tokens"] += tokens
        _add_class(p, klass, requests, tokens)
        if candidate and call.get("purpose") == "fix" and re.fullmatch(r"[A-Za-z0-9._/-]{1,120}", candidate):
            mine = p["by"].setdefault(candidate, {"requests": 0, "tokens": 0})
            mine["requests"] = _count(mine.get("requests")) + requests
            mine["tokens"] = _count(mine.get("tokens")) + tokens
            if len(p["by"]) > 40:
                del p["by"][sorted(p["by"])[0]]
    marks_at = delta.get("spent_at") if isinstance(delta.get("spent_at"), dict) else {}
    for field in ("spent", "spent_low"):
        for name, why in (delta.get(field) or {}).items() if isinstance(delta.get(field), dict) else ():
            if name in NAMES and why:
                p = _prov(state, day_of_provider(name), name)
                p[field] = _text(why, 120)
                at = (marks_at.get(name) or {}).get(field) if isinstance(marks_at.get(name), dict) else None
                if isinstance(at, int) and not isinstance(at, bool) and 0 < at < 10 ** 11:
                    p[field + "_at"] = at
    for name, tier in (delta.get("accounts") or {}).items() if isinstance(delta.get("accounts"), dict) else ():
        if name in NAMES and tier in ("free", "not-free"):
            _prov(state, day_of_provider(name), name)["account"] = tier
    for name, seen in (delta.get("observed") or {}).items() if isinstance(delta.get("observed"), dict) else ():
        if name not in NAMES or not isinstance(seen, dict):
            continue
        p = _prov(state, day_of_provider(name), name)
        for kind in ("requests", "tokens"):
            obs = seen.get(kind)
            if not isinstance(obs, dict):
                continue
            # the mark is the count at the reading in that run: here, the count after this run's calls. Only
            # what the reading had: a cap read from the account (no count) must not read as "nothing left"
            row = {"window": "day" if obs.get("window") == "day" else "minute", "mark": p[kind]}
            for field, most in (("limit", 10 ** 10), ("remaining", 10 ** 10), ("reset", 10 ** 7), ("at", 10 ** 11)):
                if isinstance(obs.get(field), int) and not isinstance(obs.get(field), bool):
                    row[field] = _count(obs.get(field), most)
            if "limit" in row or "remaining" in row:
                p["observed"][kind] = row
    return bound(state, now)


def ran(state, result, day=None, now=None, component=""):
    """One run of the automatic fix: a provider answered, or none at all was free. component: the branch it worked
    on, for the watchdog (days_unasked): the branches whose runs asked nobody today, and those that were answered."""
    d = _day(state, day or day_of(now))
    d["runs"] += 1
    d["answered" if result == "answered" else "no_provider"] += 1
    component = str(component or "")
    if re.fullmatch(r"automation/[A-Za-z0-9._/-]{1,110}", component):
        field = "answered_for" if result == "answered" else "unasked"
        row = d.get(field) if isinstance(d.get(field), dict) else {}
        row[component] = _count(row.get(component)) + 1
        while len(row) > MAX_UNASKED:
            del row[sorted(row)[0]]
        d[field] = row
    return state


def days_unasked(state, component, now=None):
    """How many days in a row, ending today or yesterday, the automatic fix ran on this branch and asked no provider
    at all (no run of it was answered that day). A day with no run of it breaks the row only when it is older than
    yesterday."""
    today = now_utc(now).date()
    count = 0
    for back in range(KEEP_DAYS):
        d = ((state or {}).get("days") or {}).get((today - dt.timedelta(days=back)).isoformat()) or {}
        unasked = d.get("unasked") if isinstance(d.get("unasked"), dict) else {}
        answered = d.get("answered_for") if isinstance(d.get("answered_for"), dict) else {}
        if answered.get(component):
            break
        if not unasked.get(component):
            if back == 0:
                continue                           # nothing ran on it yet today: yesterday decides
            break
        count += 1
    return count


def stuck(state, now=None, days=UNASKED_DAYS):
    """[(branch, days)] of the work that asked no provider at all for `days` days in a row or more (the watchdog of
    2026-11-25: "niente deve rimanere indietro"), the longest first."""
    names = set()
    for d in ((state or {}).get("days") or {}).values():
        if isinstance(d, dict) and isinstance(d.get("unasked"), dict):
            names.update(str(n) for n in d["unasked"])
    rows = [(n, days_unasked(state, n, now)) for n in sorted(names)]
    return sorted([(n, k) for n, k in rows if k >= days], key=lambda r: (-r[1], r[0]))


def stuck_text(state, now=None, days=UNASKED_DAYS):
    """The watchdog's line for the notices, in Italian (the owner's language), or ""."""
    rows = stuck(state, now, days)
    if not rows:
        return ""
    return ("ATTENZIONE (niente deve rimanere indietro): da %d o più giorni di fila nessun assistente AI è stato "
            "interpellato per: %s. AUTOMAT riprova ogni giorno; questo avviso resta finché qualcuno non viene "
            "interpellato." % (days, ", ".join("%s (%d giorni)" % (_text(n, 120), k) for n, k in rows[:8])))


def days_without_provider(state, now=None):
    """How many days in a row, ending today or yesterday, the automatic fix ran and no free provider
    at all could answer (a day with no run breaks the row only when it is older than yesterday)."""
    today = now_utc(now).date()
    count = 0
    for back in range(KEEP_DAYS):
        d = state["days"].get((today - dt.timedelta(days=back)).isoformat())
        if not d or not int(d.get("runs") or 0):
            if back == 0:
                continue                           # nothing ran yet today: yesterday decides
            break
        if int(d.get("answered") or 0) or not int(d.get("no_provider") or 0):
            break
        count += 1
    return count


def summary(limits, state, now=None):
    """Rows for the signing notice: per provider today's use, the limit, what is left, verified or not."""
    budget = Budget(limits, state, now=now)
    rows = []
    for name in NAMES:
        conf = budget.conf(name)
        used = budget.used(name)
        left = budget.remaining(name)
        week = [0, 0]
        for d in state["days"].values():
            p = (d.get("providers") or {}).get(name) or {}
            week[0] += int(p.get("requests") or 0)
            week[1] += int(p.get("tokens") or 0)
        rows.append({"provider": name, "requests": used[0], "tokens": used[1],
                     "requests_limit": budget.day_limit(name, "requests"),
                     "tokens_limit": budget.day_limit(name, "tokens"),
                     "requests_left": left["requests"], "tokens_left": left["tokens"],
                     "verified": bool(conf.get("verified")), "spent": budget.spent(name),
                     "live": bool((budget._p(name).get("observed") or {})),
                     "week_requests": week[0], "week_tokens": week[1],
                     # real updates first: today's use of classes 1 and 2, and what stays kept for them
                     "real_requests": budget.class_used(name)[0],
                     "background_requests": budget.class_used(name, (CI, BACKGROUND))[0],
                     "day": budget.day_for(name),
                     "reset_verified": bool((conf.get("reset") or {}).get("verified")),
                     "account": (budget._p(name).get("account") or "")})
    return rows


def background_status(limits, state, memory=None, now=None, available=None, pending=None, klass=BACKGROUND, prs=None):
    """Whether background work (class 4; or class 3 with klass) may ask a free AI now: {"state": "open" |
    "released" | "paused" | "no-room", "why", "pending", "providers": [those with room]}. Read by the drill's
    scheduler (tools/automat-drill.py) before it starts any of the drill's work again. prs: what
    pending_from_prs read of the open pull requests (with "closed": branches whose pull request was closed)."""
    limits = limits or load_limits()
    pending = pending_all(memory, limits, now, prs) if pending is None else list(pending)
    names = tuple(available) if available is not None else NAMES
    # read by the drill's scheduler: its own work (the owner's temporary rule drill_any_hour_until applies to it)
    budget = Budget(limits, state, "automation/update/drill-" if klass == BACKGROUND else "", now=now,
                    available=names, pending=pending)
    reserve = limits["reserve"]
    room, released, why = [], [], ""
    for name in names:
        if name not in limits["providers"] or budget.spent(name) or \
                budget._p(name).get("spent_low"):
            continue
        # one request of the size of a review (within the provider's limit per minute)
        size = min(reserve["review_tokens"], budget.minute_limit(name, "tokens") or reserve["review_tokens"])
        if budget._room(name, 1, size):
            continue
        no = budget.priority_why(name, 1, size, "fix", klass)
        if no:
            why = why or no
            continue
        room.append(name)
        if (budget.conf(name).get("reset") or {}).get("verified"):
            released.append(name)
    if pending:
        state_, why = "paused", budget.paused()
    elif room:
        state_ = "released" if released else "open"
        why = "what real work left today goes to the background (%s)" % ", ".join(room)
    else:
        state_ = "no-room"
        why = why or "no free provider has anything left for the background now"
    return {"state": state_, "why": why, "pending": pending, "providers": room}


def pending_for_run(memory_path=None, pending_path=None, limits=None):
    """The pending work of class 1 or 2 a run of the automatic fix waits for: the plan's list (pending_path: the
    open pull requests with checks not green and the memory's rows still open, one branch a line; empty: nothing
    pending), else the memory's rows alone. Fail closed: a list that says UNKNOWN (the plan could not read
    GitHub) or that is missing gives the memory's rows and UNKNOWN, so background work pauses; real work never
    waits for it."""
    if pending_path:
        try:
            lines = Path(pending_path).read_text("utf-8").split()
        except OSError:
            lines = [UNKNOWN]
        if UNKNOWN in lines:
            return sorted(set(pending_work(_read_json(memory_path), limits)) | {UNKNOWN})
        return sorted({x for x in lines if re.fullmatch(r"automation/[A-Za-z0-9._/-]{1,110}", x)
                       and priority_of(x, limits) <= UPDATE})
    return pending_work(_read_json(memory_path), limits)


def _read_json(path):
    try:
        return json.loads(Path(path).read_text("utf-8")) if path else None
    except (OSError, ValueError):
        return None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("merge")
    m.add_argument("--state", required=True)
    m.add_argument("--delta", action="append", default=[])
    r = sub.add_parser("ran")
    r.add_argument("--state", required=True)
    r.add_argument("--result", required=True, choices=("answered", "no-provider"))
    r.add_argument("--component", default="", help="the branch the run worked on (the watchdog: days_unasked)")
    s = sub.add_parser("show")
    s.add_argument("--state", required=True)
    s.add_argument("--limits")
    g = sub.add_parser("gate")
    g.add_argument("--state", required=True)
    g.add_argument("--limits")
    g.add_argument("--provider", required=True)
    g.add_argument("--tokens", type=int, default=0)
    g.add_argument("--requests", type=int, default=1)
    g.add_argument("--purpose", default="fix", choices=PURPOSES)
    g.add_argument("--candidate", default="")
    g.add_argument("--available", default="")
    g.add_argument("--tier-b", action="store_true")
    g.add_argument("--memory", help="AUTOMAT's memory.json: the work of class 1 or 2 still pending")
    q = sub.add_parser("priority")
    q.add_argument("--candidate", default="")
    q.add_argument("--state", default="")
    q.add_argument("--limits")
    q.add_argument("--memory")
    w = sub.add_parser("pending")
    w.add_argument("--repo", required=True)
    w.add_argument("--memory")
    w.add_argument("--limits")
    w.add_argument("--out", help="the JSON {pending, open, closed}; without it the pending branches, comma-separated")
    w.add_argument("--no-runs", action="store_true", help="only the open and closed pull requests (no runs read)")
    a = ap.parse_args(argv)
    if a.cmd == "pending":
        limits = load_limits(a.limits)
        try:
            prs = gather_prs(a.repo, gh_api, _read_json(a.memory), limits, runs=not a.no_runs)
        except Exception as e:                   # not read: UNKNOWN (background pauses), and nothing is closed
            print("::warning::the pending work could not be read: %s" % _text(e, 200), file=sys.stderr)
            if not a.out:
                print(UNKNOWN)
            return 1
        prs["all"] = pending_all(_read_json(a.memory), limits, None, prs)
        if a.out:
            Path(a.out).write_text(json.dumps(prs, indent=1, sort_keys=True) + "\n", "utf-8")
        else:
            print(",".join(prs["all"]))
        return 0
    if a.cmd == "priority":
        limits = load_limits(a.limits)
        klass = priority_of(a.candidate, limits)
        print("class=%d" % klass)
        print("what=%s" % CLASSES[klass])
        if klass >= CI:
            status = background_status(limits, load_state(a.state) if a.state else empty_state(),
                                       _read_json(a.memory), klass=klass)
            print("background=%s" % status["state"])
            if status["why"]:
                print("why=%s" % _text(status["why"], 300))
        return 0
    state = load_state(a.state)
    if a.cmd == "merge":
        for path in a.delta:
            try:
                state = merge(state, json.loads(Path(path).read_text("utf-8")))
            except (OSError, ValueError):
                print("a delta could not be read: skipped")
        Path(a.state).write_text(json.dumps(bound(state), indent=1, sort_keys=True) + "\n", "utf-8")
        print("the quota's record: %d day(s), %d bytes" % (len(state["days"]), len(json.dumps(state))))
        return 0
    if a.cmd == "ran":
        state = ran(state, a.result, component=a.component)
        Path(a.state).write_text(json.dumps(bound(state), indent=1, sort_keys=True) + "\n", "utf-8")
        if a.component and days_unasked(state, a.component) >= UNASKED_DAYS:
            print("::warning title=AUTOMAT watchdog::%s asked no provider for %d days in a row" % (
                _text(a.component, 120), days_unasked(state, a.component)))
        return 0
    limits = load_limits(a.limits)
    if a.cmd == "show":
        for row in summary(limits, state):
            print("%-12s requests %s/%s, tokens %s/%s%s%s" % (
                row["provider"], row["requests"], row["requests_limit"], row["tokens"], row["tokens_limit"],
                "" if row["verified"] else " (limit not verified)", " SPENT: " + row["spent"] if row["spent"] else ""))
        for name, days in stuck(state):
            print("WATCHDOG: %s asked no provider for %d days in a row" % (name, days))
        return 0
    names = tuple(n for n in a.available.split(",") if n) or None
    ok, why = Budget(limits, state, a.candidate, tier_b=a.tier_b, available=names,
                     pending=pending_work(_read_json(a.memory), limits)).allows(
        a.provider, a.tokens, a.purpose, a.requests)
    print("%s: %s" % (a.provider, "may be asked" if ok else "not asked: " + why))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
