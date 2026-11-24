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
  waits and nothing is wasted); and one candidate's fixes take at most ``share_per_candidate`` of a
  provider's day, so one candidate cannot drain everything. A limit per minute is waited out when
  it is short (wait_seconds).
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
  checks are not green, a row of failures in AUTOMAT's memory whose pull request was not closed), and
  only in the provider's leftover window (leftover_window): the last release_hours hours before its own
  reset when a person verified it, else once the real day's maintenance window (UTC) is over. Each
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
            "headers": {}, "day_words": ["per day", "daily"]}
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
            words = raw.get("day_words")
            conf["day_words"] = [str(w) for w in words][:12] if isinstance(words, list) else FALLBACK["day_words"]
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
        if re.fullmatch(r"[A-Za-z0-9._/-]{1,120}", str(component)) and priority_of(component, limits) <= UPDATE:
            out.append(str(component))
    return sorted(out)


GREEN = ("success", "skipped", "neutral")


def pending_from_prs(repo, api, limits=None):
    """The work of class 1 or 2 that is pending from GitHub itself: an open pull request of the automation
    (automation/update/*, automation/builder/*, automation/daily-maintenance, automation/autofix-main) whose last
    commit has a run that is not green (failed, cancelled, or still running): {"pending": [...], "open": [...]},
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
            if not runs or any(r.get("status") != "completed" or r.get("conclusion") not in GREEN for r in runs):
                out["pending"].append(ref)
        if len(prs) < 100:
            break
    out["pending"] = sorted(set(out["pending"]))
    out["open"] = sorted(set(out["open"]))
    return out


def closed_branches(repo, api, refs):
    """Of these branches, those whose pull request was closed (merged or not) and none is open: their row of
    failures in AUTOMAT's memory is over."""
    out = []
    owner = repo.split("/")[0]
    for ref in refs:
        try:
            got = api("repos/%s/pulls?state=closed&head=%s:%s&per_page=1" % (repo, owner, ref)) or []
        except RuntimeError:
            continue
        if got:
            out.append(ref)
    return sorted(out)


def gather_prs(repo, api, memory=None, limits=None, now=None, runs=True):
    """pending_from_prs, and "closed": the memory's rows whose branch has no open pull request any more but had
    one (GET calls only)."""
    prs = pending_from_prs(repo, api, limits) if runs else {"pending": [], "open": []}
    if not runs:
        for page in range(1, 6):
            got = api("repos/%s/pulls?state=open&per_page=100&page=%d" % (repo, page)) or []
            prs["open"] += [str((x.get("head") or {}).get("ref") or "") for x in got]
            if len(got) < 100:
                break
        prs["open"] = sorted({r for r in prs["open"] if r.startswith("automation/")})
    rows = [r for r in pending_work(memory, limits, now) if r not in prs["open"]]
    prs["closed"] = closed_branches(repo, api, rows)
    return prs


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
    requests are known, a memory row of a branch that had a pull request and has none open any more is left out
    (its pull request was closed)."""
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
    daily window's reset in seconds and when it was read, "at"), else its "reset" (a time in its own zone)."""
    now = now_utc(now)
    obs = observed if isinstance(observed, dict) else {}
    if obs.get("window") == "day" and isinstance(obs.get("reset"), int) and isinstance(obs.get("at"), int) \
            and obs["reset"] > 0:
        moment = dt.datetime.fromtimestamp(obs["at"] + obs["reset"], dt.timezone.utc)
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
        self.pending = sorted({str(c) for c in pending or () if priority_of(c, self.limits) <= UPDATE})
        self.available = tuple(available) if available is not None else NAMES
        self.calls = []                 # [(provider, requests, tokens, purpose)] of this run
        self.recent = {}                # provider -> [(time, requests, tokens)] for the limits per minute
        self.blocked_until = {}         # provider -> time: a 429 with a short retry-after
        self.skipped = {}
        self.result = ""

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

    def spent(self, provider):
        """Why the provider is spent today for this run's class ("" when it is not): a 429 that work of class 3
        or 4 got spends it only for classes 3 and 4 (spent_low), never for security fixes and real updates."""
        p = self._p(provider)
        if self.priority >= CI and p.get("spent_low"):
            return p.get("spent") or p["spent_low"]
        return p.get("spent") or ""

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
        clock alone: a provider whose reset a person verified, in the last release_hours hours of its own day;
        one whose reset is not verified, once the real day's maintenance window has passed (its use is
        counted on its own day). (False, why not) otherwise."""
        hours = (self.next_reset(provider) - self.now).total_seconds() / 3600.0
        if (self.conf(provider).get("reset") or {}).get("verified"):
            if hours <= float(self.limits["priority"]["release_hours"]):
                return True, "the last %.1f hours of its day" % hours
            return False, ("its day's leftovers go to the background only in its last %s hours (%.1f hours to its "
                           "reset)" % (self.limits["priority"]["release_hours"], hours))
        if self.in_maintenance():
            win = self.limits["priority"].get("maintenance_window") or PRIORITY["maintenance_window"]
            return False, ("its reset is not verified: the background waits until the real day's maintenance is "
                           "over (%s-%s UTC)" % (win["start"], win["end"]))
        return True, "the real day's maintenance is over (its reset is not verified)"

    def paused(self, provider=None):
        """Why work of class 3 or 4 pauses now ("" when it may run): work of class 1 or 2 is pending or retrying.
        Never lifted while it is: real updates may always use everything."""
        if not self.pending:
            return ""
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
        ok, why = self.leftover_window(provider)
        return "" if ok else "class %d (%s) uses only what real work leaves: %s" % (klass, CLASSES[klass], why)

    def reviewers_left(self, author):
        """The providers other than the author that still have room for one review today (for this run's
        class: a background fix whose reviews would have to take the reserve waits too)."""
        r = self.limits["reserve"]
        return [n for n in self.available if n != author and n in self.limits["providers"] and not self.spent(n)
                and not self._room(n, r["review_requests"], r["review_tokens"])
                and not self.priority_why(n, r["review_requests"], r["review_tokens"], "review")]

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
            for kind, need in (("requests", requests), ("tokens", tokens)):
                limit = self.day_limit(provider, kind)
                if limit is None or not self.candidate:
                    continue
                most = max(1 if kind == "requests" else need, int(limit * share))
                if int(mine.get(kind) or 0) + need > most:
                    return False, ("this candidate already used its share of today's %s (%d of %d; at most %d%% of "
                                   "a provider's day goes to one candidate)" % (
                                       kind, int(mine.get(kind) or 0), limit, int(share * 100)))
            left = self.reviewers_left(provider)
            if len(left) < self.reviews_needed():
                return False, ("the reviewers' reserve: after a fix by %s only %d other provider(s) would have room "
                               "for a review today (%s), and %d are needed: the fix waits" % (
                                   provider, len(left), ", ".join(left) or "none", self.reviews_needed()))
        return True, ""

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
                p["spent"] = "its own headers say nothing is left today"
            if obs.get("window") == "minute" and obs.get("remaining") == 0 and obs.get("reset"):
                self.blocked_until[provider] = self.clock() + min(obs["reset"], 120)
        if status == 429:
            wait = retry_after(headers)
            daily = any(w and w.lower() in str(body or "").lower() for w in conf.get("day_words") or ())
            if daily or wait > 3600:
                why = "429: the quota of the day (%s)" % ("it says so" if daily else "retry after %d s" % wait)
                # work of class 3 or 4 spends it only for itself: security fixes and real updates still ask
                p["spent_low" if self.priority >= CI else "spent"] = why
            else:
                self.blocked_until[provider] = self.clock() + (wait if wait > 0 else 60)
        elif status == 402:
            p["spent"] = "it asked for money (not free)"

    def mark_spent(self, provider, why):
        """Spent today: for everybody, except a quota answer (429) that work of class 3 or 4 got."""
        if provider in self.limits["providers"]:
            low = self.priority >= CI and "429" in str(why)
            self._p(provider)["spent_low" if low else "spent"] = str(why)[:120]

    def delta(self):
        """What this run adds, for the job that writes the data branch (numbers and known names only); each
        provider's use goes to its own day (days)."""
        mine = {n: self._p(n) for n in NAMES if n in self.limits["providers"]}
        return {"schema": SCHEMA, "day": self.day, "days": {n: self.day_for(n) for n in mine},
                "candidate": self.candidate, "calls": self.calls,
                "spent": {n: p.get("spent") for n, p in mine.items() if p.get("spent")},
                "spent_low": {n: p.get("spent_low") for n, p in mine.items() if p.get("spent_low")},
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
    for field in ("spent", "spent_low"):
        for name, why in (delta.get(field) or {}).items() if isinstance(delta.get(field), dict) else ():
            if name in NAMES and why:
                _prov(state, day_of_provider(name), name)[field] = _text(why, 120)
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


def ran(state, result, day=None, now=None):
    """One run of the automatic fix: a provider answered, or none at all was free."""
    d = _day(state, day or day_of(now))
    d["runs"] += 1
    d["answered" if result == "answered" else "no_provider"] += 1
    return state


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
    budget = Budget(limits, state, "", now=now, available=names, pending=pending)
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
    open pull requests with checks not green and the memory's rows still open, one branch a line), else the
    memory's rows alone."""
    if pending_path:
        try:
            lines = Path(pending_path).read_text("utf-8").split()
        except OSError:
            lines = None
        if lines is not None:
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
        prs = gather_prs(a.repo, gh_api, _read_json(a.memory), limits, runs=not a.no_runs)
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
        Path(a.state).write_text(json.dumps(bound(ran(state, a.result)), indent=1, sort_keys=True) + "\n", "utf-8")
        return 0
    limits = load_limits(a.limits)
    if a.cmd == "show":
        for row in summary(limits, state):
            print("%-12s requests %s/%s, tokens %s/%s%s%s" % (
                row["provider"], row["requests"], row["requests_limit"], row["tokens"], row["tokens_limit"],
                "" if row["verified"] else " (limit not verified)", " SPENT: " + row["spent"] if row["spent"] else ""))
        return 0
    names = tuple(n for n in a.available.split(",") if n) or None
    ok, why = Budget(limits, state, a.candidate, tier_b=a.tier_b, available=names,
                     pending=pending_work(_read_json(a.memory), limits)).allows(
        a.provider, a.tokens, a.purpose, a.requests)
    print("%s: %s" % (a.provider, "may be asked" if ok else "not asked: " + why))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
