#!/usr/bin/env python3
"""Security findings of the automatic maintenance (WP6 of the maintenance plan). No AI here.

A RustSec advisory that cargo-deny reports in security.yml, or a failed sandbox
and isolation test, becomes a ledger entry and an AutoFix plan whose target is
an isolated branch ``automation/update/security-<id>`` made from main
(tools/autofix-plan.py). For an advisory the first step is deterministic: this
tool runs ``cargo update`` for the crate, to the first version the advisory
says is fixed, and checks that cargo-deny no longer reports it. An AI may then
adapt only I.K.E.'s wrapper, under the guard's security rules
(tools/check-autofix-patch.py --security), if the new crate breaks the build.
An advisory with no fixed version upstream is **blocked** with its reason and
the owner is told: it is never silenced. An exception goes only in
ike-adblock/deny.toml, written by a person with its reason (check-ignores).

    security-fix.py parse LOG [--json OUT]
        cargo-deny's output (the human format of `check advisories`, also inside
        a GitHub job log) as findings: id, kind, crate, version, title,
        solution, the first fixed version ("" when there is none).
    security-fix.py apply --findings FILE --manifest ike-adblock/Cargo.toml --out FILE
        cargo update for each finding that has a fixed version; what was
        updated and what is blocked (with the reason).
    security-fix.py verify LOG --ids ID[,ID...]
        exit 1 while cargo-deny's new output still names one of the ids.
    security-fix.py report --out FILE [--findings FILE] [--result FILE] [--branch B]
                           [--run URL] [--autofix WORKFLOW] [--summary FILE] [--guard FILE] [--commits FILE]
        the pull request's body, in the candidate report's format (WP13).
    security-fix.py check-ignores [ike-adblock/deny.toml]
        exit 1 when an exception of [advisories] ignore has no reason.

Never changes ike-adblock/deny.toml, the sandbox or any test. The automatic fix
may never change this file (tools/check-autofix-patch.py, FORBIDDEN_FILES).
"""

import argparse
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

SECURITY_PREFIX = "automation/update/security-"
ADVISORY_URL = "https://rustsec.org/advisories/%s"
STAMP = re.compile(r"^\d{4}-\d\d-\d\dT[\d:.]+Z ?")
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
HEAD = re.compile(r"^(error|warning)\[([\w-]+)\]:\s*(.*)$")
# "2 │ smallvec 1.6.0 registry+https://github.com/rust-lang/crates.io-index"
CRATE = re.compile(r"(?:│|\|)\s*([A-Za-z0-9_-]+) (\d[\w.+-]*) (?:registry|git|path)\+")
CRATE_TREE = re.compile(r"^\s*├\s*([A-Za-z0-9_-]+) v(\d[\w.+-]*)\s*$")
ID = re.compile(r"\bID:\s*(RUSTSEC-\d{4}-\d{4})")
SOLUTION = re.compile(r"\bSolution:\s*(.+?)\s*$")
NO_FIX = re.compile(r"no safe upgrade", re.I)
VERSION = re.compile(r"\d+")
# what an exception's reason must at least be: a sentence a person wrote
MIN_REASON = 20
PLACEHOLDER = re.compile(r"^\s*(todo|tbd|fixme|x+|none|n/?a|ignore|ignored|\.+|-+)\s*$", re.I)


def clean(text):
    return [STAMP.sub("", ANSI.sub("", ln.lstrip("﻿"))).rstrip() for ln in (text or "").splitlines()]


def vkey(version):
    return tuple(int(n) for n in VERSION.findall(str(version or "")))


def compatible(old, new):
    """Cargo's semver compatibility: the same major (0.x: the same minor; 0.0.x: the same patch)."""
    a, b = vkey(old), vkey(new)
    if not a or not b:
        return False
    if a[0]:
        return a[0] == b[0]
    if len(a) > 1 and a[1]:
        return len(b) > 1 and b[0] == 0 and a[1] == b[1]
    return a[:3] == b[:3]


def fixed_version(solution, installed):
    """The first version the advisory says is fixed, for the crate at `installed`, or "".

    "Upgrade to >=0.6.14, <1.0.0 OR >=1.6.1 (try `cargo update -p smallvec`)" for 1.6.0 gives
    1.6.1: among the ranges whose lower bound is above the version in use, a semver-compatible
    one first (cargo update can take it), else the lowest. "No safe upgrade is available!": ""."""
    text = re.sub(r"\(try .*?\)", "", solution or "")
    if not text.strip() or NO_FIX.search(text):
        return ""
    lows = []
    for alt in re.split(r"\s+OR\s+", text.replace("Upgrade to", "")):
        m = re.search(r">=\s*(\d[\w.+-]*)", alt)
        if m and vkey(m.group(1)) > vkey(installed):
            lows.append(m.group(1))
    if not lows:
        return ""
    same = [v for v in lows if compatible(installed, v)]
    return min(same or lows, key=vkey)


def parse(text):
    """cargo-deny's findings in its human output (or a job log holding it), each once."""
    found, cur = [], None
    for line in clean(text):
        head = HEAD.match(line.strip())
        if head:
            cur = {"id": "", "kind": head.group(2), "level": head.group(1), "title": head.group(3).strip(),
                   "crate": "", "version": "", "solution": "", "fix": "", "url": ""}
            found.append(cur)
            continue
        if cur is None:
            continue
        m = CRATE.search(line)
        if m and not cur["crate"]:
            cur["crate"], cur["version"] = m.group(1), m.group(2)
        m = ID.search(line)
        if m and not cur["id"]:
            cur["id"] = m.group(1)
        m = SOLUTION.search(line)
        if m and not cur["solution"]:
            cur["solution"] = m.group(1)
        m = CRATE_TREE.match(line)
        if m and not cur["crate"]:
            cur["crate"], cur["version"] = m.group(1), m.group(2)
    out, seen = [], set()
    for f in found:
        if not f["crate"] and not f["id"]:
            continue                           # a summary line ("advisories FAILED"), not a finding
        if f["kind"] == "yanked":
            f["id"] = f["id"] or "yanked-%s-%s" % (f["crate"], f["version"])
            # a yanked crate: the newest compatible version (cargo update) is the fix
            f["fix"] = "newest compatible"
        else:
            f["fix"] = fixed_version(f["solution"], f["version"])
        if not f["id"]:
            f["id"] = "%s-%s-%s" % (f["kind"], f["crate"], f["version"])
        if f["id"].startswith("RUSTSEC-"):
            f["url"] = ADVISORY_URL % f["id"]
        key = (f["id"], f["crate"], f["version"])
        if key not in seen:
            seen.add(key)
            out.append(f)
    return out


def slug(text):
    """A branch-safe, lowercase form of an id: RUSTSEC-2021-0003 -> rustsec-2021-0003."""
    s = re.sub(r"[^a-z0-9.-]+", "-", str(text).lower()).strip("-.")
    return re.sub(r"-{2,}", "-", s)[:60] or "finding"


def branch_for(finding_id):
    return SECURITY_PREFIX + slug(finding_id)


# --- the deterministic update (cargo, no AI) -------------------------------------------------------

_LOCK = re.compile(r'^\[\[package\]\]\nname = "([^"]+)"\nversion = "([^"]+)"', re.M)


def lock_versions(text):
    out = {}
    for name, version in _LOCK.findall((text or "").replace("\r\n", "\n")):
        out.setdefault(name, []).append(version)
    return out


def _cargo(args, run):
    done = run(["cargo", *args], capture_output=True, text=True, check=False)
    return done.returncode, (done.stderr or "") + (done.stdout or "")


def apply(findings, manifest, run=subprocess.run):
    """cargo update for each finding with a fixed version. {"updates": [...], "blocked": [...]}:
    an update names the crate and from -> to; a blocked finding its reason (no fixed version
    upstream, or cargo could not take it: a requirement of the crate that uses it must change)."""
    lock = Path(manifest).with_name("Cargo.lock")
    result = {"updates": [], "blocked": []}
    for f in findings:
        crate, version, fix = f.get("crate"), f.get("version"), f.get("fix")
        if not crate or not version:
            result["blocked"].append(dict(f, reason="the advisory names no crate of Cargo.lock"))
            continue
        if not fix:
            result["blocked"].append(dict(f, reason="no fixed version upstream (%s): blocked, never ignored; an "
                                          "exception needs a reason a person writes in ike-adblock/deny.toml"
                                          % (f.get("solution") or "the advisory gives no solution")))
            continue
        before = lock_versions(lock.read_text("utf-8")) if lock.is_file() else {}
        spec = "%s@%s" % (crate, version)
        args = ["update", "--manifest-path", str(manifest), "-p", spec]
        code, log = _cargo(args + (["--precise", fix] if fix != "newest compatible" else []), run)
        if code and fix != "newest compatible":
            # the first fixed version may be gone (yanked): the newest compatible one, if it is fixed too
            code, log = _cargo(args, run)
        after = lock_versions(lock.read_text("utf-8")) if lock.is_file() else {}
        new = sorted(set(after.get(crate, [])) - set(before.get(crate, [])), key=vkey)
        target = new[-1] if new else ""
        if code or not target:
            lines = log.strip().splitlines()
            said = next((ln for ln in lines if ln.lstrip().startswith("error")), lines[-1] if lines else "")
            result["blocked"].append(dict(f, reason="cargo update could not take %s %s to %s (a requirement of "
                                          "the crate that uses it must change: a person): %s"
                                          % (crate, version, fix, said.strip()[:200] or "no newer version")))
        elif fix != "newest compatible" and vkey(target) < vkey(fix):
            result["blocked"].append(dict(f, reason="the newest version cargo can take (%s) is not fixed (%s)"
                                          % (target, fix)))
        else:
            result["updates"].append({"id": f["id"], "crate": crate, "from": version, "to": target,
                                      "title": f.get("title", ""), "url": f.get("url", "")})
    return result


def verify(text, ids):
    """The ids cargo-deny still reports in its new output."""
    still = {f["id"] for f in parse(text)}
    return sorted(i for i in ids if i in still)


# --- exceptions: only a person's, each with its reason ----------------------------------------------

def check_ignores(text):
    """Problems of [advisories] ignore in deny.toml: an entry without a reason (a bare id, an
    empty or placeholder reason) is refused; a person writes the reason (docs/THIRD-PARTY.md)."""
    import tomllib
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        return ["deny.toml cannot be read: %s" % e]
    problems = []
    for entry in (data.get("advisories") or {}).get("ignore") or []:
        if not isinstance(entry, dict):
            problems.append("%s: an exception without a reason (write { id = \"...\", reason = \"...\" })" % entry)
            continue
        what = entry.get("id") or entry.get("crate") or "?"
        reason = str(entry.get("reason") or "")
        if len(reason.strip()) < MIN_REASON or PLACEHOLDER.match(reason):
            problems.append("%s: its reason is missing or too short (a person writes why it does not apply)" % what)
    return problems


# --- the pull request's body (the candidate report's format, WP13) -------------------------------------

def _report_tool():
    spec = importlib.util.spec_from_file_location("maintenance_report", Path(__file__).resolve().parent /
                                                  "maintenance-report.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def report(findings=(), result=None, branch="", run_url="", autofix_of="", summary="", guard="", commits=""):
    """The body of a security fix's pull request: the finding, then the sections of the
    candidate's report (what changes, AutoFix, problems, tests: not verified until they run,
    security checks, licences, limits). autofix_of: the workflow whose failure the automatic
    fix answered on this branch (an AI's fix), "" for the deterministic update."""
    result = result or {}
    updates = result.get("updates") or []
    comps = [{"name": "Rust crates of the AdBlock engine (security)", "current": "%s %s" % (u["crate"], u["from"]),
              "latest": "%s %s" % (u["crate"], u["to"]), "update": True,
              "note": "%s: %s" % (u["id"], u.get("title") or "RustSec advisory")} for u in updates]
    out = ["## Security finding", ""]
    if autofix_of:
        out.append("- **%s** failed on this isolated branch%s. The automatic fix (an AI) worked here under the "
                   "guard's security rules (`tools/check-autofix-patch.py --security`): it may not touch the "
                   "sandbox and isolation switches, `ENGINE_SAFETY`, the security tests, `ike-adblock/deny.toml` "
                   "or name a RustSec advisory. Read its change before merging." % (
                       autofix_of, " (%s)" % run_url if run_url else ""))
    for f in findings:
        out.append("- **%s**: %s %s: %s%s" % (f.get("id"), f.get("crate") or "?", f.get("version") or "?",
                                              f.get("title") or f.get("kind", ""),
                                              " ([advisory](%s))" % f["url"] if f.get("url") else ""))
    for u in updates:
        out.append("- Fixed by `cargo update` alone (no AI), on this branch made from `main`: %s %s -> %s."
                   % (u["crate"], u["from"], u["to"]))
    for b in result.get("blocked") or []:
        out.append("- **Blocked**: %s %s %s: %s" % (b.get("id"), b.get("crate") or "", b.get("version") or "",
                                                     b.get("reason")))
    out += ["- Branch `%s`. Nothing merges by itself: this pull request waits for the owner's order." % (
        branch or "?"), "- An exception to an advisory is never written by the automation: only a person, in "
            "`ike-adblock/deny.toml`, with its reason.", ""]
    if summary.strip():
        out += ["### Summary of the agent", "", summary.strip(), ""]
    if guard.strip():
        out += ["### Automatic checks", "", guard.strip(), ""]
    body = _report_tool().compose({"components": comps}, "", None, commits, "", None, "", pushed=True)
    return "\n".join(out) + "\n" + body


# --- command line -----------------------------------------------------------------------------------

def _read(path, as_json=True):
    if not path:
        return None if as_json else ""
    try:
        text = Path(path).read_text("utf-8", "replace")
    except OSError:
        return None if as_json else ""
    if not as_json:
        return text
    try:
        return json.loads(text)
    except ValueError:
        return None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("parse")
    p.add_argument("log")
    p.add_argument("--json")
    a = sub.add_parser("apply")
    a.add_argument("--findings", required=True)
    a.add_argument("--manifest", required=True)
    a.add_argument("--out", required=True)
    v = sub.add_parser("verify")
    v.add_argument("log")
    v.add_argument("--ids", required=True)
    r = sub.add_parser("report")
    r.add_argument("--out", required=True)
    r.add_argument("--findings")
    r.add_argument("--result")
    r.add_argument("--branch", default="")
    r.add_argument("--run", default="")
    r.add_argument("--autofix", default="", help="the workflow whose failure an AI fixed on this branch")
    r.add_argument("--commits", help="the branch's commits, one per line (git log --oneline)")
    r.add_argument("--summary")
    r.add_argument("--guard")
    c = sub.add_parser("check-ignores")
    c.add_argument("deny", nargs="?", default="ike-adblock/deny.toml")
    args = ap.parse_args(argv)
    if args.cmd == "parse":
        found = parse(_read(args.log, False))
        if args.json:
            Path(args.json).write_text(json.dumps(found, indent=1) + "\n", "utf-8")
        for f in found:
            print("%s %s %s: fix %s" % (f["id"], f["crate"], f["version"], f["fix"] or "none upstream"))
        return 0
    if args.cmd == "apply":
        result = apply(_read(args.findings) or [], args.manifest)
        Path(args.out).write_text(json.dumps(result, indent=1) + "\n", "utf-8")
        for u in result["updates"]:
            print("updated: %s %s -> %s (%s)" % (u["crate"], u["from"], u["to"], u["id"]))
        for b in result["blocked"]:
            print("blocked: %s %s: %s" % (b.get("id"), b.get("crate"), b.get("reason")))
        return 0
    if args.cmd == "verify":
        still = verify(_read(args.log, False), [i for i in args.ids.split(",") if i])
        if still:
            print("still reported by cargo-deny: %s" % ", ".join(still))
            return 1
        print("cargo-deny no longer reports: %s" % args.ids)
        return 0
    if args.cmd == "report":
        body = report(_read(args.findings) or [], _read(args.result) or {}, args.branch, args.run, args.autofix,
                      _read(args.summary, False), _read(args.guard, False), _read(args.commits, False))
        Path(args.out).write_text(body, "utf-8")
        return 0
    problems = check_ignores(_read(args.deny, False))
    for p in problems:
        print("::error::%s: %s" % (args.deny, p.replace("::", ": ")))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
