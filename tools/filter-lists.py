#!/usr/bin/env python3
"""The filter lists' findings, in five classes (WP8 of the maintenance; no AI here).

``tools/check-components.py --filter-lists`` loads the default filter lists
into the bundled AdBlock engine and reads their scriptlets: every rule the
engine does not read (with the engine's reason), every scriptlet the bundled
uBlock Origin library does not know, every list it cannot use. This tool puts
each of them into one class, by the written rules of RULES below (first match
wins), and groups them: one finding per class, rule and detail (an option, a
reason, a scriptlet), with how many rules, in which lists, and examples.

    supported    the engine does not read it, but I.K.E. runs it: a "+js()" rule
                 the engine's parser refuses is run by ike/scriptlets.py
    harmless     unsupported but harmless: a feature uBlock Origin has only on
                 another platform (HTML filtering, replace=) whose Chromium
                 alternative the same lists carry; an exception for a blocking
                 the engine never applies (pop-ups, CNAME); a scriptlet uBlock
                 Origin itself runs only from its trusted lists
    breaking     a breaking incompatibility: an exception the engine drops (it
                 blocks what the list unblocks: a site may break), a blocking
                 or hiding rule of the ads lists it cannot read, an unknown
                 scriptlet (list/library drift), a list the engine refuses, an
                 engine that does not build, a list whose unread share passes
                 LIST_UNREAD_SHARE or rose by more than SHARE_RISE since the
                 day before
    security     a possible security regression: a protection the engine drops
                 or reads differently ($removeparam, $csp, $redirect,
                 $permissions, $urlskip, $denyallow, pop-up blocking, ... see
                 PROTECTIVE), any dropped rule of a privacy or badware list, a
                 page-blocking ($doc) rule dropped, a trusted scriptlet that
                 does not run
    person       needs a person: anything about YouTube (CLAUDE.md: YouTube's
                 ad blocking is not changed without the owner), uBlock
                 Origin's own resources used as scriptlets
                 (KNOWN_UNRUN_SCRIPTLETS: bundling them is the owner's
                 decision), a list that is not a list

A finding of the classes breaking or security that is about the syntax of
rules or an unknown scriptlet (``ai``: true) may be given to an AI analysis on
an isolated branch, ``automation/update/lists-<date>`` (``plan`` below,
autofix.yml): it may change I.K.E.'s adapter only (ike/scriptlets.py,
ike/blocker.py, ike-adblock/src/; tools/check-autofix-patch.py --lists), never
the lists, the bundled uBlock Origin resources, YouTube's ad blocking or the
tests, and never weaken blocking. The recorded rules go into
tests/data/lists-recorded/ (written by the workflow, not by the AI), and
tests/test_lists_recorded.py proves that I.K.E. now reads each of them with
every option it has.

    filter-lists.py classify --lists lists.json [--json OUT] [--markdown OUT] [--baseline FILE]
    filter-lists.py compare --base main.json --candidate cand.json [--markdown OUT]
        (the full chain, item 4: a candidate's engine against main's on the same
        day's lists, on the candidate's own commit; prints pass, fail or
        unverified: tests.yml, job filter-lists, the category tools/automerge.py
        reads)
    filter-lists.py plan --run-id ID --work lists/<date>/<key> --out-dir DIR [--repo OWNER/NAME]
        (autofix.yml's plan, GET calls only: the lists report of that daily
        check run; GitHub outputs as tools/autofix-plan.py writes them, the
        failure description and the recorded rules)
"""

import argparse
import io
import json
import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLASSES = ("supported", "harmless", "breaking", "security", "person")
CLASS_TEXT = {"supported": "supported", "harmless": "unsupported but harmless",
              "breaking": "breaking incompatibility", "security": "possible security regression",
              "person": "needs a person"}
LIST_UNREAD_SHARE = 0.25       # as tools/check-components.py
SHARE_RISE = 0.05              # unread share risen by more than 5 points since the day before
EXAMPLES = 3
RECORDED_MAX = 12              # rules recorded for one AI analysis
RECORDED_DIR = "tests/data/lists-recorded"
BRANCH = "automation/update/lists-%s"
WORKFLOW = "Filter lists"
MAX_ATTEMPTS = 2               # AI fixes on one lists branch, as for any automatic fix
ADAPTER = ("ike/scriptlets.py", "ike/blocker.py", "ike-adblock/src/lib.rs")
# uBlock Origin's own resources used as scriptlets: as tools/check-components.py
KNOWN_UNRUN_SCRIPTLETS = ("noeval", "nofab", "popads-dummy", "popads.net", "fingerprint2")

# YouTube: its hosts in a rule's address or domains (not a list of exceptions
# such as denyallow=), and the player data its ad rules work on
YOUTUBE = re.compile(r"(?<![a-z0-9-])(?:youtube(?:-nocookie|kids)?\.(?:com|\*)|youtu\.be|ytimg\.com"
                     r"|googlevideo\.com)(?![a-z0-9-])", re.I)
YOUTUBE_DATA = re.compile(r"\b(?:ytInitial\w*|ytplayer|ytcfg|adPlacements|adSlots|playerAds|playerResponse)\b")
# options the AdBlock engine (adblock-rust) reads; an "unrecognised option" is
# named by the first option of the rule that is not one of these
ENGINE_OPTIONS = {
    "script", "image", "stylesheet", "css", "object", "xhr", "xmlhttprequest", "subdocument", "frame",
    "sub_frame", "ping", "beacon", "websocket", "font", "media", "other", "document", "doc", "1p", "3p",
    "first-party", "third-party", "firstparty", "thirdparty", "domain", "from", "important", "match-case",
    "redirect", "redirect-rule", "removeparam", "csp", "generichide", "ghide", "elemhide", "all", "badfilter", "tag", "rewrite", "empty", "mp4", "fetch", "webrtc",
    "object-subrequest", "xml", "image-subrequest", "genericblock", "content", "jsinject", "urlblock",
}
# a dropped blocking rule with one of these protects the user (privacy, security,
# pop-ups and malvertising): its loss is a possible security regression
PROTECTIVE = {"removeparam", "csp", "redirect", "redirect-rule", "permissions", "header", "urlskip",
              "uritransform", "urltransform", "inline-script", "inline-font", "strict1p", "strict3p",
              "strict-first-party", "strict-third-party", "ipaddress", "denyallow", "to", "method", "popup",
              "popunder"}
PAGE_BLOCKING = {"doc", "document", "all"}
# exceptions for a blocking the engine never applies: nothing to lift
NO_BLOCKING = {"popup", "popunder", "cname", "replace", "urlskip", "uritransform", "urltransform", "header",
               "permissions", "denyallow"}
PROTECTIVE_LISTS = re.compile(r"privacy|badware|malicious|malware|phishing", re.I)
OTHER_PLATFORM = re.compile(r"html filtering")
WORD = re.compile(r"^[a-z0-9_-]+$")

# The written rules: (id, class, AI analysis allowed, why). classify_rule()
# applies them in this order; docs/MAINTENANCE.md and tests/test_lists_providers.py
# keep the same list.
RULES = (
    ("youtube", "person", False, "YouTube's ad blocking is not changed without the owner (CLAUDE.md)"),
    ("known-resource", "person", False, "one of uBlock Origin's own resources: bundling them is the owner's "
                                        "decision (KNOWN_UNRUN_SCRIPTLETS)"),
    ("run-by-ike", "supported", False, "the engine's parser does not read this scriptlet rule, but I.K.E. runs "
                                       "it (ike/scriptlets.py)"),
    ("other-platform", "harmless", False, "a feature uBlock Origin has only on Firefox (HTML filtering, replace=); "
                                          "the lists carry the Chromium alternative"),
    ("untrusted-scriptlet", "harmless", False, "a trusted scriptlet in a list that is not uBlock Origin's own: "
                                               "uBlock Origin would not run it either"),
    ("exception-without-blocking", "harmless", False, "an exception for a blocking the engine never applies "
                                                      "(pop-ups, CNAME...): nothing to lift"),
    ("exception-dropped", "breaking", True, "an exception the engine drops: it blocks what the list unblocks, "
                                            "a site may break"),
    ("trusted-scriptlet", "security", True, "a trusted scriptlet that does not run"),
    ("protection-dropped", "security", True, "a protection the engine drops (privacy, security, pop-ups)"),
    ("protective-list", "security", True, "a rule of a privacy or badware list the engine drops"),
    ("page-blocking", "security", True, "a rule that blocks whole pages (badware) the engine drops"),
    ("unknown-scriptlet", "breaking", True, "a scriptlet the bundled library does not know: I.K.E. drops the rule "
                                            "(list/library drift)"),
    ("rule-dropped", "breaking", True, "a rule of an ads list the engine does not read"),
    ("list-unusable", "person", False, "a list that is not a list (empty, binary, too big): its publisher's "
                                       "matter"),
    ("list-refused", "breaking", False, "the engine refuses the list or fails while reading it"),
    ("engine", "breaking", False, "the engine does not load or build from the lists (the engine is a crate: a "
                                  "person)"),
    ("unread-share", "breaking", False, "the engine cannot read more than a quarter of the list"),
    ("share-rise", "breaking", False, "the engine reads clearly less of the list than the day before"),
)
RULE = {r[0]: r for r in RULES}

# Engine reasons no change of I.K.E.'s adapter can fix (2026-11-27, PR #111): the finding keeps its class (it is
# still a gap, said in the ledger and the notices) but is not given to an AI analysis, which could only guess
# (tests/test_lists_recorded.py refuses a rule rewritten without one of its options, rightly). Claude's work: an
# engine update (adblock-rust) or a feature of the browser.
ENGINE_LIMITS = {
    "network filter error: csp with content type": (
        "adblock-rust refuses a csp= rule that also names a content type ($doc), and the adapter may not drop "
        "the option; besides, I.K.E. applies no $csp rule at all (Qt WebEngine cannot add a response header): "
        "an engine update or a browser feature, not an AI analysis"),
}


def slug(text, size=60):
    return re.sub(r"[^a-z0-9.]+", "-", str(text).lower()).strip("-")[:size] or "x"


def finding_key(cls, rule, detail):
    """lists/<rule>/<detail>@<class>: short, it is written several times in the ledger's issue."""
    return "lists/%s/%s@%s" % (rule, slug(detail), cls)


def _scriptlets(root=ROOT):
    """ike.scriptlets of this checkout (no Qt needed)."""
    root = Path(root).resolve()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    import ike.scriptlets
    return ike.scriptlets


def is_youtube(text):
    text = re.sub(r"denyallow=[^,$]*", "", text or "")
    return bool(YOUTUBE.search(text) or YOUTUBE_DATA.search(text))


def options_of(rule):
    """The option names of a network rule ("~" and values left out)."""
    body = rule[2:] if rule.startswith("@@") else rule
    m = None
    if body.startswith("/"):            # a regular expression: the options start after its end
        m = re.search(r"/\$(?=~?[A-Za-z0-9_-]+(?:[=,]|$))", body[1:])
        at = 1 + m.start() + 1 if m else -1
    if m is None:                       # an address (also one that starts with a path)
        m = re.search(r"(?<!\\)\$(?=~?[A-Za-z0-9_-]+(?:[=,]|$))", body)
        at = m.start() if m else -1
    if at < 0:
        return []
    names = []
    for part in re.split(r",(?=~?[A-Za-z0-9_-]+(?:=|,|$))", body[at + 1:]):
        name = part.split("=", 1)[0].strip().lstrip("~").lower()
        if WORD.match(name):
            names.append(name)
    return names


def is_cosmetic(rule):
    return bool(re.search(r"#[@?$%]*#", rule)) and not rule.startswith("@@")


def scriptlet_name(rule, scr):
    m = scr._RULE.match(rule.strip())
    if not m:
        return None, None
    args = scr.split_args(m.group(3))
    return (args[0] if args else ""), m


def classify_rule(rule, why, list_name, trusted, lib, scr):
    """(rule id, detail) of one rule the engine does not read."""
    if is_youtube(rule):
        return "youtube", why
    if "+js(" in rule:
        name, m = scriptlet_name(rule, scr)
        if m is not None and m.group(2):
            return "exception-dropped", "scriptlet exception"
        base = re.sub(r"\.js$", "", name or "")
        if base in KNOWN_UNRUN_SCRIPTLETS:
            return "known-resource", base
        resolved = lib.resolve(name) if name else None
        if resolved and m is not None and m.group(1).strip():
            if (lib.entry(resolved) or {}).get("trust") and not trusted:
                return "untrusted-scriptlet", base
            return "run-by-ike", "scriptlet %s" % base
        if resolved is None and name and m is not None and m.group(1).strip():
            return None, None          # counted once, from the lists check's unknown scriptlets
        return "rule-dropped", why
    if OTHER_PLATFORM.search(why) or "##^" in rule:
        return "other-platform", "html filtering"
    if is_cosmetic(rule):
        if re.search(r"#@[?$%]*#", rule):
            return "exception-dropped", why
        if PROTECTIVE_LISTS.search(list_name):
            return "protective-list", why
        return "rule-dropped", why
    opts = options_of(rule)
    odd = [o for o in opts if o not in ENGINE_OPTIONS]
    detail = ("option %s" % odd[0]) if odd and why == "network filter error: unrecognised option" else why
    if "replace" in opts:
        return "other-platform", "option replace"
    if rule.startswith("@@"):
        if odd and all(o in NO_BLOCKING for o in odd):
            return "exception-without-blocking", "option %s" % odd[0]
        return "exception-dropped", detail
    if any(o in PROTECTIVE for o in odd) or (not odd and any(o in PROTECTIVE for o in opts)):
        return "protection-dropped", detail
    if PROTECTIVE_LISTS.search(list_name):
        return "protective-list", detail
    if any(o in PAGE_BLOCKING for o in opts):
        return "page-blocking", detail
    return "rule-dropped", detail


def _add(groups, rule_id, detail, rule_text, list_name, count=1):
    rid, cls, ai, why = RULE[rule_id]
    key = finding_key(cls, rule_id, detail)
    g = groups.get(key)
    if g is None:
        limit = ENGINE_LIMITS.get(detail)
        g = groups[key] = {"key": key, "class": cls, "rule": rule_id, "detail": detail,
                           "why": "%s; %s" % (why, limit) if limit else why, "ai": ai and not limit,
                           "youtube": rule_id == "youtube", "count": 0, "lists": [], "examples": []}
    g["count"] += count
    if list_name and list_name not in g["lists"]:
        g["lists"].append(list_name)
    if rule_text and len(g["examples"]) < EXAMPLES and not any(e["rule"] == rule_text for e in g["examples"]):
        g["examples"].append({"list": list_name, "rule": rule_text[:300]})


def classify(info, baseline=None, root=ROOT):
    """The findings of one lists report (tools/check-components.py
    --filter-lists), classified and grouped. baseline: {list name: unread
    share} of the day before, or None."""
    scr = _scriptlets(root)
    lib = scr.Library()
    groups, shares, supported = {}, {}, 0
    for row in info.get("lists", []):
        name = row.get("name", "")
        if row.get("state") == "unusable":
            _add(groups, "list-unusable", name, "", name)
            continue
        if row.get("state") != "ok":
            continue
        supported += int(row.get("network") or 0) + int(row.get("cosmetic") or 0)
        sc = row.get("scriptlets") or {}
        supported += int(sc.get("rules") or 0)
        if str(row.get("error", "")).startswith("parse report"):
            _add(groups, "list-refused", name, "", name)
        for kind, rule, why in row.get("unread", row.get("examples", [])):
            rid, detail = classify_rule(rule, why, name, bool(row.get("trusted")), lib, scr)
            if rid:
                _add(groups, rid, detail, rule, name)
        if "unread_share" in row:
            share = float(row["unread_share"])
            shares[name] = share
            if share > LIST_UNREAD_SHARE:
                _add(groups, "unread-share", name, "", name)
            elif baseline and name in baseline and share - float(baseline[name]) > SHARE_RISE:
                _add(groups, "share-rise", "%s: %.1f%% -> %.1f%%" % (name, float(baseline[name]) * 100,
                                                                     share * 100), "", name)
    for name, seen in sorted((info.get("unknown_scriptlets") or {}).items()):
        example = seen.get("example", "")
        base = re.sub(r"\.js$", "", name)
        if is_youtube(example):
            rid = "youtube"
        elif base in KNOWN_UNRUN_SCRIPTLETS:
            rid = "known-resource"
        elif base.startswith("trusted-"):
            rid = "trusted-scriptlet"
        else:
            rid = "unknown-scriptlet"
        detail = "scriptlet %s" % base if rid == "youtube" else base
        for list_name in seen.get("lists", []) or [""]:
            _add(groups, rid, detail, example, list_name, 0)
        groups[finding_key(RULE[rid][1], rid, detail)]["count"] += int(seen.get("count") or 0)
    for text in info.get("findings", []):
        if "engine refused the list" in text or "engine failed while reading" in text:
            _add(groups, "list-refused", text.split(":", 1)[0], "", text.split(":", 1)[0])
    eng = info.get("engine") or {}
    if info.get("lists") and any(r.get("state") == "ok" for r in info["lists"]) and not eng.get("built"):
        _add(groups, "engine", "not built" if eng.get("backend") else "not loaded", "", "")
    findings = sorted(groups.values(), key=lambda g: (-CLASSES.index(g["class"]), g["key"]))
    counts = {c: sum(g["count"] for g in findings if g["class"] == c) for c in CLASSES}
    counts["supported"] += supported
    return {"findings": findings, "counts": counts, "shares": shares, "state": info.get("state", ""),
            "checked": sum(1 for r in info.get("lists", []) if r.get("state") == "ok")}


def markdown(result):
    out = ["", "#### The findings in five classes (tools/filter-lists.py)", ""]
    if not result["checked"]:
        out.append("No list could be read today: nothing classified.")
        return "\n".join(out) + "\n"
    out.append("Rules: " + ", ".join("%s %d" % (CLASS_TEXT[c], result["counts"][c]) for c in CLASSES) + ".")
    shown = [f for f in result["findings"] if f["class"] != "supported"]
    if shown:
        out += ["", "| Class | Rule | Detail | Rules | Lists | AI analysis |", "|---|---|---|---|---|---|"]
        for f in shown:
            out.append("| %s | %s | %s | %d | %s | %s |" % (
                CLASS_TEXT[f["class"]], f["rule"], str(f["detail"]).replace("|", "\\|")[:80], f["count"],
                ", ".join(f["lists"])[:120], "yes" if f["ai"] else "no"))
    return "\n".join(out) + "\n"


# --- the AI analysis of one finding (autofix.yml's plan) ------------------------------------

def recorded_rules(finding):
    return [e["rule"] for e in finding["examples"]][:RECORDED_MAX]


def failure_text(finding, branch, lines=None):
    """The task given to the AI (the agent reads it as the failure)."""
    lines = lines or {}
    rules = recorded_rules(finding)
    out = ["# Filter lists: %s (%s)" % (CLASS_TEXT[finding["class"]], finding["detail"]), "",
           "The daily check loaded today's default filter lists into I.K.E.'s AdBlock engine. These real "
           "rules are not read by I.K.E. (%d rules like them, in: %s). Why it matters: %s." % (
               finding["count"], ", ".join(finding["lists"]) or "the lists", finding["why"]), "",
           "```text"] + rules + ["```", "",
           "## Your task", "",
           "Make I.K.E. read these rules with the meaning uBlock Origin gives them, by changing I.K.E.'s "
           "adapter only:", ""]
    for path in ADAPTER:
        out.append("- %s:%s" % (path, lines.get(path, 1)))
    out += ["",
            "Rules you must follow (the checks refuse anything else):", "",
            "- Change only the files above. Never the filter lists, ike/config.py, the bundled uBlock Origin "
            "resources (ike/resources/ubo-scriptlets.json), the engine's Cargo files, the tests or their data.",
            "- Never weaken blocking: never drop an option or a rule to make it parse, never turn a rule that "
            "modifies or redirects into one that blocks or allows, never remove an existing rule or check.",
            "- Never touch YouTube's ad blocking (ike/resources/videoads.js, videorelay.js, mediahook.js, "
            "Scriptlets.host_scripts, the YouTube rules of ike/blocker.py).",
            "- The workflow adds these rules to %s/ and tests/test_lists_recorded.py checks that I.K.E. reads "
            "each one with every option it has. Do not write tests." % RECORDED_DIR,
            "- If the engine itself (the adblock-rust crate) must change, change nothing and say so in the "
            "summary: that is for a person.", "",
            "Branch: %s (isolated; never main)." % branch]
    return "\n".join(out) + "\n"


def adapter_lines(root=ROOT):
    """Where the adapter reads rules (for the code shown to the AI)."""
    out = {}
    for path, pattern in (("ike/scriptlets.py", r"^\s*def resolve\b"), ("ike/blocker.py", r"^def sanitize\b"),
                          ("ike-adblock/src/lib.rs", r"fn add_filter_list\b")):
        try:
            text = (Path(root) / path).read_text("utf-8").splitlines()
        except OSError:
            continue
        out[path] = next((i + 1 for i, ln in enumerate(text) if re.search(pattern, ln)), 1)
    return out


WORK = re.compile(r"^lists/(\d{4}-\d\d-\d\d)/(lists/[a-z-]+/[a-z0-9.-]+@[a-z]+)$")


def parse_work(work):
    m = WORK.match(work or "")
    if not m:
        raise ValueError("not a lists work: %r" % (work or "")[:120])
    return m.group(1), m.group(2)


def recorded_path(date, key):
    rule_detail, cls = key.split("/", 1)[1].split("@")
    return "%s/%s-%s-%s.txt" % (RECORDED_DIR, date, cls, slug(rule_detail, 50))


def plan(info, work, main_sha, branch_tip="", attempts=0, root=ROOT):
    """The outputs of the plan for one lists work, the failure text and the
    recorded rules (no network)."""
    date, key = parse_work(work)
    branch = BRANCH % date
    out = {"action": "skip", "reason": "", "kind": "lists", "checkout": "", "push_branch": branch,
           "attempt": "0", "allow_adblock": "true", "workflow": WORKFLOW, "head_sha": main_sha, "branch": branch,
           "push_tip": branch_tip, "mode": "lists", "recorded": recorded_path(date, key)}
    result = classify(info, root=root)
    finding = next((f for f in result["findings"] if f["key"] == key), None)
    if finding is None:
        out["reason"] = "the finding %s is no longer reported by today's lists check" % key
        return out, "", ""
    if finding["youtube"] or not finding["ai"]:
        out["reason"] = "%s: %s, no AI analysis (%s)" % (key, CLASS_TEXT[finding["class"]], finding["why"])
        return out, "", ""
    attempt = attempts + 1
    out.update(attempt=str(attempt), checkout=branch_tip or main_sha)
    if attempt > MAX_ATTEMPTS:
        out.update(action="issue", reason="%d AI analyses did not make I.K.E. read these rules: a person looks"
                   % MAX_ATTEMPTS)
        return out, "", ""
    out.update(action="fix", reason="%s in today's filter lists (%s): an AI analysis of I.K.E.'s adapter on %s"
               % (CLASS_TEXT[finding["class"]], finding["detail"], branch))
    rules = recorded_rules(finding)
    recorded = "! %s\n! %s (%s), recorded by the daily check on %s\n%s\n" % (
        key, CLASS_TEXT[finding["class"]], finding["detail"], date, "\n".join(rules))
    return out, failure_text(finding, branch, adapter_lines(root)), recorded


def gh_api(path, raw=False):
    out = subprocess.run(["gh", "api", path], capture_output=True, check=False)
    if out.returncode:
        raise RuntimeError("gh api %s: %s" % (path, out.stderr.decode("utf-8", "replace").strip()[:200]))
    return out.stdout if raw else json.loads(out.stdout)


def run_lists(repo, run_id, api=gh_api):
    """lists.json of a daily check run (its artifact "filter-lists")."""
    for art in api("repos/%s/actions/runs/%s/artifacts?name=filter-lists" % (repo, run_id)).get("artifacts", []):
        if art.get("expired"):
            continue
        data = api("repos/%s/actions/artifacts/%s/zip" % (repo, art["id"]), raw=True)
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            return json.loads(z.read("lists.json").decode("utf-8"))
    raise RuntimeError("the daily check run %s has no lists report" % run_id)


def _git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True, check=False)


def compare(base, cand, rise=SHARE_RISE):
    """(verdict, lines) of a candidate's engine against main's on the same lists (both runs of
    tools/check-components.py --filter-lists, the same day). "fail": the candidate's engine does not
    load or build from them, refuses or fails on a list main's engine reads, or leaves a list's
    unread share higher by more than `rise`; "unverified": a list could not be downloaded in either
    run, or there were no lists (nothing compared is never passed); else "pass"."""
    lines, verdict = [], "pass"
    b_eng, c_eng = (base or {}).get("engine") or {}, (cand or {}).get("engine") or {}
    if b_eng.get("built") and not c_eng.get("built"):
        verdict = "fail"
        lines.append("the candidate's engine does not load or build from today's lists: %s"
                     % (c_eng.get("error") or "?"))
    b_rows = {r.get("url"): r for r in (base or {}).get("lists") or ()}
    c_rows = (cand or {}).get("lists") or []
    if not c_rows:
        return "unverified", ["no lists were checked"]
    refused_b = {f.split(":", 1)[0] for f in (base or {}).get("findings") or () if "the engine refused" in f}
    unverified = []
    for row in c_rows:
        b = b_rows.get(row.get("url"))
        name = row.get("name", "?")
        if b is None or "unreachable" in (row.get("state"), b.get("state")):
            unverified.append(name)
            continue
        if row.get("error", "").startswith("parse report") and not b.get("error", "").startswith("parse report"):
            verdict = "fail"
            lines.append("%s: the candidate's engine fails while reading it (%s)" % (name, row["error"][:160]))
        share_b, share_c = b.get("unread_share"), row.get("unread_share")
        if isinstance(share_b, (int, float)) and isinstance(share_c, (int, float)) and share_c > share_b + rise:
            verdict = "fail"
            lines.append("%s: unread %.1f%% with the candidate's engine, %.1f%% with main's" % (
                name, share_c * 100, share_b * 100))
        elif isinstance(share_c, (int, float)) and isinstance(share_b, (int, float)):
            lines.append("%s: unread %.1f%% (main's engine %.1f%%)" % (name, share_c * 100, share_b * 100))
    for f in (cand or {}).get("findings") or ():
        if "the engine refused" in f and f.split(":", 1)[0] not in refused_b:
            verdict = "fail"
            lines.append(f[:200])
    if unverified and verdict == "pass":
        verdict = "unverified"
        lines.append("not downloaded today, so not compared: %s" % ", ".join(unverified[:12]))
    return verdict, lines


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    k = sub.add_parser("compare")
    k.add_argument("--base", required=True)
    k.add_argument("--candidate", required=True)
    k.add_argument("--markdown")
    c = sub.add_parser("classify")
    c.add_argument("--lists", required=True)
    c.add_argument("--json")
    c.add_argument("--markdown")
    c.add_argument("--baseline")
    p = sub.add_parser("plan")
    p.add_argument("--run-id", required=True)
    p.add_argument("--work", required=True)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    a = ap.parse_args(argv)
    if a.cmd == "compare":
        def read(path):
            try:
                return json.loads(Path(path).read_text("utf-8"))
            except (OSError, ValueError):
                return {}
        verdict, lines = compare(read(a.base), read(a.candidate))
        if a.markdown:
            text = ["### The default filter lists in this commit's engine (against main's)", "",
                    "**%s**" % {"pass": "passed: no list is read worse than with main's engine",
                                "fail": "failed: the candidate's engine reads today's lists worse",
                                "unverified": "not verified"}[verdict], ""] + ["- " + x for x in lines]
            Path(a.markdown).write_text("\n".join(text) + "\n", "utf-8")
        print(verdict)
        return 0
    if a.cmd == "classify":
        info = json.loads(Path(a.lists).read_text("utf-8"))
        base = None
        if a.baseline:
            try:
                base = json.loads(Path(a.baseline).read_text("utf-8")).get("lists_baseline")
            except (OSError, ValueError, AttributeError):
                base = None
        result = classify(info, base)
        if a.json:
            Path(a.json).write_text(json.dumps(result, indent=1) + "\n", "utf-8")
        md = markdown(result)
        if a.markdown:
            Path(a.markdown).write_text(md, "utf-8")
        else:
            print(md)
        return 0
    out_dir = Path(a.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    main_sha = _git("rev-parse", "origin/main").stdout.strip()
    date, _key = parse_work(a.work)
    branch = BRANCH % date
    tip = _git("rev-parse", "-q", "--verify", "refs/remotes/origin/" + branch).stdout.strip()
    attempts = 0
    if tip:
        log = _git("log", "--format=%s", "origin/main.." + tip).stdout.splitlines()
        attempts = sum(1 for s in log if s.startswith("autofix: attempt"))
    try:
        info = run_lists(a.repo, a.run_id)
        outputs, failure, recorded = plan(info, a.work, main_sha, tip, attempts)
    except (RuntimeError, ValueError, KeyError, zipfile.BadZipFile) as e:
        outputs = {"action": "skip", "reason": "the lists work could not be planned: %s" % str(e)[:200],
                   "kind": "lists", "workflow": WORKFLOW}
        failure = recorded = ""
    (out_dir / "failure.md").write_text(failure or "(no AI analysis: %s)\n" % outputs["reason"], "utf-8")
    (out_dir / "recorded.txt").write_text(recorded, "utf-8")
    gh_out = os.environ.get("GITHUB_OUTPUT")
    lines = "".join("%s=%s\n" % (k, str(v).replace("\n", " ")) for k, v in outputs.items())
    if gh_out:
        with open(gh_out, "a", encoding="utf-8") as f:
            f.write(lines)
    print(lines, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
