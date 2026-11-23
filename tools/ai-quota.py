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

    ai-quota.py merge --state quota.json --delta FILE [--delta FILE ...]   (the job that writes the branch)
    ai-quota.py ran --state quota.json --result answered|no-provider
    ai-quota.py show --state quota.json [--limits tools/ai-quota.json]
    ai-quota.py gate --state quota.json --provider NAME --tokens N [--purpose fix|review] [--candidate ID]
                     [--available A,B,C] [--tier-b]                       (exit 0: it may be asked)
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
        out["providers"][name] = conf
    return out


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
    return p


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

    def __init__(self, limits=None, state=None, candidate="", now=None, tier_b=False, available=None, clock=None):
        self.limits = limits or load_limits()
        self.state = state if isinstance(state, dict) and isinstance(state.get("days"), dict) else empty_state()
        self.candidate = str(candidate or "")[:120]
        self.tier_b = bool(tier_b)
        self.clock = clock or time.time
        self.day = day_of(now)
        self.available = tuple(available) if available is not None else NAMES
        self.calls = []                 # [(provider, requests, tokens, purpose)] of this run
        self.recent = {}                # provider -> [(time, requests, tokens)] for the limits per minute
        self.blocked_until = {}         # provider -> time: a 429 with a short retry-after
        self.skipped = {}
        self.result = ""

    # --- what is left ---
    def conf(self, provider):
        return self.limits["providers"].get(provider) or dict(FALLBACK)

    def used(self, provider):
        p = _prov(self.state, self.day, provider)
        return p["requests"], p["tokens"]

    def spent(self, provider):
        return _prov(self.state, self.day, provider).get("spent") or ""

    def day_limit(self, provider, kind):
        """Today's limit of requests or tokens: what the provider's own headers said, else the data file."""
        obs = (_prov(self.state, self.day, provider).get("observed") or {}).get(kind) or {}
        if obs.get("window") == "day" and isinstance(obs.get("limit"), int) and obs["limit"] > 0:
            return obs["limit"]
        return self.conf(provider).get("%s_per_day" % kind)

    def remaining(self, provider):
        """{"requests": n or None, "tokens": n or None} left today (None: no daily limit known)."""
        p = _prov(self.state, self.day, provider)
        out = {}
        for kind in ("requests", "tokens"):
            limit = self.conf(provider).get("%s_per_day" % kind)
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
        obs = (_prov(self.state, self.day, provider).get("observed") or {}).get(kind) or {}
        if obs.get("window") == "minute" and isinstance(obs.get("limit"), int) and obs["limit"] > 0:
            return obs["limit"]
        return self.conf(provider).get("%s_per_minute" % kind)

    def reviewers_left(self, author):
        """The providers other than the author that still have room for one review today."""
        r = self.limits["reserve"]
        return [n for n in self.available if n != author and n in self.limits["providers"] and not self.spent(n)
                and not self._room(n, r["review_requests"], r["review_tokens"])]

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
        if purpose == "fix":
            p = _prov(self.state, self.day, provider)
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
        p = _prov(self.state, self.day, provider)
        p["requests"] += requests
        p["tokens"] += tokens
        if self.candidate and purpose == "fix":
            mine = p["by"].setdefault(self.candidate, {"requests": 0, "tokens": 0})
            mine["requests"] = int(mine.get("requests") or 0) + requests
            mine["tokens"] = int(mine.get("tokens") or 0) + tokens
        self.calls.append({"provider": provider, "requests": requests, "tokens": tokens,
                           "purpose": purpose if purpose in PURPOSES else "fix"})
        self.recent.setdefault(provider, []).append((self.clock(), requests, tokens))
        seen = observe(conf, headers)
        for kind, obs in seen.items():
            obs["mark"] = p[kind]
            p["observed"][kind] = obs
            if obs.get("window") == "day" and obs.get("remaining") == 0:
                p["spent"] = "its own headers say nothing is left today"
            if obs.get("window") == "minute" and obs.get("remaining") == 0 and obs.get("reset"):
                self.blocked_until[provider] = self.clock() + min(obs["reset"], 120)
        if status == 429:
            wait = retry_after(headers)
            daily = any(w and w.lower() in str(body or "").lower() for w in conf.get("day_words") or ())
            if daily or wait > 3600:
                p["spent"] = "429: the quota of the day (%s)" % ("it says so" if daily else "retry after %d s" % wait)
            else:
                self.blocked_until[provider] = self.clock() + (wait if wait > 0 else 60)
        elif status == 402:
            p["spent"] = "it asked for money (not free)"

    def mark_spent(self, provider, why):
        if provider in self.limits["providers"]:
            _prov(self.state, self.day, provider)["spent"] = str(why)[:120]

    def delta(self):
        """What this run adds, for the job that writes the data branch (numbers and known names only)."""
        day = _day(self.state, self.day)
        return {"schema": SCHEMA, "day": self.day, "candidate": self.candidate, "calls": self.calls,
                "spent": {n: p.get("spent") for n, p in day["providers"].items() if p.get("spent")},
                "observed": {n: p.get("observed") for n, p in day["providers"].items() if p.get("observed")},
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
    candidate = _text(delta.get("candidate"), 120)
    for call in (delta.get("calls") or [])[:400] if isinstance(delta.get("calls"), list) else ():
        if not isinstance(call, dict) or call.get("provider") not in NAMES:
            continue
        p = _prov(state, day, call["provider"])
        requests, tokens = _count(call.get("requests"), 10 ** 4), _count(call.get("tokens"))
        p["requests"] += requests
        p["tokens"] += tokens
        if candidate and call.get("purpose") == "fix" and re.fullmatch(r"[A-Za-z0-9._/-]{1,120}", candidate):
            mine = p["by"].setdefault(candidate, {"requests": 0, "tokens": 0})
            mine["requests"] = _count(mine.get("requests")) + requests
            mine["tokens"] = _count(mine.get("tokens")) + tokens
            if len(p["by"]) > 40:
                del p["by"][sorted(p["by"])[0]]
    for name, why in (delta.get("spent") or {}).items() if isinstance(delta.get("spent"), dict) else ():
        if name in NAMES and why:
            _prov(state, day, name)["spent"] = _text(why, 120)
    for name, seen in (delta.get("observed") or {}).items() if isinstance(delta.get("observed"), dict) else ():
        if name not in NAMES or not isinstance(seen, dict):
            continue
        p = _prov(state, day, name)
        for kind in ("requests", "tokens"):
            obs = seen.get(kind)
            if not isinstance(obs, dict):
                continue
            # the mark is the count at the reading in that run: here, the count after this run's calls
            p["observed"][kind] = {"limit": _count(obs.get("limit"), 10 ** 10), "remaining": _count(
                obs.get("remaining"), 10 ** 10), "reset": _count(obs.get("reset"), 10 ** 7),
                "window": "day" if obs.get("window") == "day" else "minute", "mark": p[kind]}
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
                     "live": bool((_prov(state, budget.day, name).get("observed") or {})),
                     "week_requests": week[0], "week_tokens": week[1]})
    return rows


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
    a = ap.parse_args(argv)
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
    ok, why = Budget(limits, state, a.candidate, tier_b=a.tier_b, available=names).allows(
        a.provider, a.tokens, a.purpose, a.requests)
    print("%s: %s" % (a.provider, "may be asked" if ok else "not asked: " + why))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
