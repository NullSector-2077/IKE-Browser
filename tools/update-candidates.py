#!/usr/bin/env python3
"""One isolated candidate per component (WP5 of the maintenance; no AI here).

The daily maintenance (daily-maintenance.yml) no longer puts every update into
one combined candidate: each component, or small coherent group, gets its own
branch ``automation/update/<id>`` made from main, with its own tests, Arch run,
automatic fix, ledger entry and verified merge (tools/automerge.py).

    id                 what it updates (tools/check-components.py --only ID --apply)
    adblock            the AdBlock engine library (exact pin, ENGINE_VERSION, Cargo.lock)
    crates             every semver-compatible crate of the engine (cargo update)
    pyo3               a new pyo3 release line (the requirement in Cargo.toml raised)
    crate-major-<c>    a new major version of another direct crate of the engine
    ubo-scriptlets     uBlock Origin's scriptlets (rebuilt by tools/build-ubo-scriptlets.mjs)
    darkreader         Dark Reader's engine and lists (rebuilt by tools/build-darkreader.py)
    test-qt            Qt's wheels of the automatic tests
    test-tools         pytest, ruff and what they bring
    test-libs          the other libraries of the automatic tests
    pkgbuild           the PKGBUILD's depends, optdepends and minima (tools/pkgbuild-sync.py)
    ci-<name>          a pin of the workflows (tools/ci-pins.py: actions, cargo-deny, Python, Node.js, Rust)

Rules (the plan below; the workflow follows them):

- idempotent: an open candidate is rebuilt from main and pushed only when its
  files differ from the published branch, so the same update is never opened
  twice and a candidate whose update is already open is not duplicated;
- serialised: candidates that change the same file one at a time (SERIAL: the
  engine's Cargo.lock, with the security fixes' branches; the test packages'
  pins): while one of a group is open the others wait ("queued"), the first
  by PRIORITY goes first;
- a builder that refuses the new upstream version starts the builder's own
  path instead (``automation/builder/<id>``, WP11: an AI may only re-anchor
  I.K.E.'s existing patches, tools/builder-anchor.py);
- a source unreachable today makes nothing (the next run tries again).

Each candidate's own commit is ``update: <id> <from> -> <to> (no AI)`` and may
change only FILES of its id, the licence files and, when it ships, the version
files (the version raised by tools/prepare-maintenance.py when main's version
is published). The same function (commit_problem) is what the workflow checks
before it pushes and what tools/automerge.py checks before it merges.

    update-candidates.py plan --report report.json [--branches branches.json] --out plan.json
    update-candidates.py message --report report.json --id ID
    update-candidates.py check --id ID --base REF --head REF
    update-candidates.py branches --repo OWNER/NAME --out branches.json   (GET calls only)
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PREFIX = "automation/update/"
BUILDER_PREFIX = "automation/builder/"
SECURITY_PREFIX = PREFIX + "security-"
ID = re.compile(r"^(adblock|crates|pyo3|crate-major-[a-z0-9_-]{1,40}|ubo-scriptlets|darkreader|test-qt|test-tools"
                r"|test-libs|pkgbuild|ci-[a-z0-9-]{1,60})$")
ENGINE_FILES = ("ike-adblock/Cargo.toml", "ike-adblock/Cargo.lock")
LICENCE_FILES = ("docs/THIRD-PARTY.md", "licenses/")
VERSION_FILES = ("ike/__init__.py", "PKGBUILD", "README.md", "CHANGELOG.md")
# id (or prefix ending in "-") -> what its own commit may change, its serial group, whether it
# ships to users (then the version is raised), and whether the automatic fix may adapt I.K.E.'s
# wrapper of the engine on its branch (allow_adblock)
SPECS = {
    "adblock": {"files": ENGINE_FILES + ("ike-adblock/src/lib.rs",), "serial": "cargo", "ships": True,
                "wrapper": True, "kinds": ("adblock-engine", "crate")},
    "crates": {"files": ("ike-adblock/Cargo.lock",), "serial": "cargo", "ships": True, "wrapper": True,
               "kinds": ("crate",)},
    "pyo3": {"files": ENGINE_FILES, "serial": "cargo", "ships": True, "wrapper": True,
             "kinds": ("adblock-engine", "crate")},
    "crate-major-": {"files": ENGINE_FILES, "serial": "cargo", "ships": True, "wrapper": True,
                     "kinds": ("adblock-engine", "crate")},
    "ubo-scriptlets": {"files": ("ike/resources/ubo-scriptlets.json",), "serial": "", "ships": True,
                       "wrapper": False, "kinds": ("integrated",), "builder": "tools/build-ubo-scriptlets.mjs"},
    "darkreader": {"files": ("ike/resources/darkreader.js", "ike/resources/darkreader-proxy.js",
                             "ike/resources/darkreader-data.json"), "serial": "", "ships": True,
                   "wrapper": False, "kinds": ("npm", "integrated"), "builder": "tools/build-darkreader.py"},
    "test-qt": {"files": ("tools/test-requirements.txt",), "serial": "test-requirements", "ships": False,
                "wrapper": False, "kinds": ("pypi-test",)},
    "test-tools": {"files": ("tools/test-requirements.txt",), "serial": "test-requirements", "ships": False,
                   "wrapper": False, "kinds": ("pypi-test",)},
    "test-libs": {"files": ("tools/test-requirements.txt",), "serial": "test-requirements", "ships": False,
                  "wrapper": False, "kinds": ("pypi-test",)},
    "pkgbuild": {"files": (), "serial": "", "ships": True, "wrapper": False, "kinds": ("arch-package",)},
    "ci-": {"files": (".github/workflows/", ".github/actions/"), "serial": "", "ships": False, "wrapper": False,
            "kinds": ("github-action",)},
}
# the order in which candidates of one serial group go (the security fixes' branches always count as open)
PRIORITY = ("adblock", "pyo3", "crates", "crate-major-", "test-qt", "test-tools", "test-libs")
UPDATE_COMMIT = re.compile(r"^update: ([a-z0-9-]+) (.{1,300}) -> (.{1,300}) \(no AI\)$")
CI_COMMIT = re.compile(r"^ci: ([a-z0-9-]+) (\S{1,80}) -> (\S{1,80}) \(tools/ci-pins\.py, no AI\)$")


def spec(cid):
    """The SPECS entry of a candidate id, or None."""
    if not cid or not ID.match(cid):
        return None
    if cid in SPECS:
        return SPECS[cid]
    for key, value in SPECS.items():
        if key.endswith("-") and cid.startswith(key):
            return value
    return None


def branch_for(cid):
    return PREFIX + cid


def builder_branch(cid):
    return BUILDER_PREFIX + cid


def id_of_branch(ref):
    """The candidate id of automation/update/<id> or automation/builder/<id>, or ""."""
    for prefix in (PREFIX, BUILDER_PREFIX):
        if ref.startswith(prefix):
            cid = ref[len(prefix):]
            if spec(cid) and not (prefix == BUILDER_PREFIX and not spec(cid).get("builder")):
                return cid
    return ""


def priority(cid):
    for n, key in enumerate(PRIORITY):
        if cid == key or (key.endswith("-") and cid.startswith(key)):
            return n
    return len(PRIORITY)


def wrapper_allowed(ref):
    """The automatic fix may adapt I.K.E.'s wrapper of the engine on this branch (a new engine, a new
    pyo3, a new major crate: the owner's rule of 2026-11-22, item 2)."""
    s = spec(id_of_branch(ref)) if ref.startswith(PREFIX) else None
    return bool(s and s.get("wrapper"))


def message(cand):
    """The first line of a candidate's own commit."""
    def clean(text):
        text = re.sub(r"\s+", " ", str(text or "?")).strip().replace("->", "to")
        return text[:120] or "?"
    return "update: %s %s -> %s (no AI)" % (cand["id"], clean(cand.get("from")), clean(cand.get("to")))


def commit_problem(cid, first_line, files):
    """Why a commit of the candidate cid is not its own update commit, or "" (files: the names it
    changed). Used before the push (daily-maintenance.yml) and before the merge (tools/automerge.py)."""
    s = spec(cid)
    m = UPDATE_COMMIT.match(first_line or "")
    if not s or not m or m.group(1) != cid:
        return "not the update's own commit of %s (%s)" % (cid or "?", (first_line or "")[:60])
    if cid.startswith("ci-") or cid == "pkgbuild":
        return "%s: its own tool writes its commit (not an update commit)" % cid
    for name in files:
        if not name:
            continue
        if name in VERSION_FILES:
            if not s["ships"]:
                return "%s: the version may not move for %s (nothing shipped)" % (name, cid)
            continue
        if not name.startswith(s["files"] + LICENCE_FILES):
            return "%s: the update of %s may not change it" % (name, cid)
    return ""


def plan(report, branches=None):
    """What today's run does with each candidate (pure): [{"id", "action", "branch", "reason", ...}].

    report: tools/check-components.py --json (its "candidates"); branches: {branch: {"pr", "sha",
    "subject"}} of the open pull requests of automation/update/* and automation/builder/*.
    action: make (rebuilt from main, pushed when it differs), queued (another candidate of its serial
    group is open), builder (the builder refused: the builder's path), unreachable, skip."""
    branches = branches or {}
    out, taken = [], {}
    open_serial = {}
    for ref in branches:
        cid = id_of_branch(ref)
        s = spec(cid)
        if ref.startswith(SECURITY_PREFIX):
            open_serial.setdefault("cargo", ref)
        elif s and s["serial"] and ref.startswith(PREFIX):
            open_serial.setdefault(s["serial"], ref)
    cands = sorted((c for c in (report or {}).get("candidates") or () if spec(c.get("id"))),
                   key=lambda c: (priority(c["id"]), c["id"]))
    for c in cands:
        cid, s = c["id"], spec(c["id"])
        row = {"id": cid, "branch": branch_for(cid), "from": c.get("from", ""), "to": c.get("to", ""),
               "component": c.get("component", ""), "wrapper": s["wrapper"], "ships": s["ships"]}
        if c.get("error"):
            out.append(dict(row, action="unreachable", reason="its source could not be read today: %s"
                            % c["error"][:200]))
            continue
        if c.get("refused"):
            b = builder_branch(cid)
            if not s.get("builder"):
                out.append(dict(row, action="skip", reason="refused, and no builder of I.K.E.'s for it"))
            elif b in branches:
                out.append(dict(row, action="skip", branch=b, reason="the builder's re-anchoring already waits on "
                                "%s (PR #%s)" % (b, branches[b].get("pr", "?"))))
            else:
                out.append(dict(row, action="builder", branch=b, reason="the builder refused the new version "
                                "(%s): an AI may re-anchor I.K.E.'s existing patches on %s" % (c.get("step", "?"), b)))
            continue
        if not c.get("to"):
            out.append(dict(row, action="skip", reason="nothing newer"))
            continue
        group = s["serial"]
        mine = row["branch"]
        holder = open_serial.get(group) if group else None
        if group and holder and holder != mine:
            out.append(dict(row, action="queued", reason="waits for %s (one change of %s at a time)" % (
                holder, "the engine's Cargo.lock" if group == "cargo" else "the test packages' pins")))
            continue
        if group and taken.get(group) and taken[group] != mine:
            out.append(dict(row, action="queued", reason="waits for %s, made first today (one at a time)"
                            % taken[group]))
            continue
        if group:
            taken[group] = mine
        known = branches.get(mine) or {}
        why = "rebuilt from main; pushed only when it differs from the open candidate (PR #%s)" % known["pr"] \
            if known else "a new candidate from main"
        out.append(dict(row, action="make", reason=why, message=message(c)))
    return out


def matrix(rows):
    """The candidates the workflow's matrix makes today (make and builder)."""
    return [{"id": r["id"], "action": r["action"]} for r in rows if r["action"] in ("make", "builder")]


def markdown(rows):
    if not rows:
        return "### One candidate per component\n\nNo component has a newer version today.\n"
    out = ["### One candidate per component", "", "| Candidate | From | To | Today | Why |", "|---|---|---|---|---|"]
    for r in rows:
        out.append("| `%s` | %s | %s | %s | %s |" % (r["id"], _md(r["from"]), _md(r["to"]), r["action"],
                                                    _md(r["reason"])))
    return "\n".join(out) + "\n"


def _md(text):
    return str(text or "").replace("|", "\\|").replace("\n", " ")[:300]


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout


def check_range(cid, base, head):
    """The problems of the commits base..head of candidate cid: each one its own update commit
    (commit_problem) or a commit of the automatic fix (carried over from the open candidate)."""
    bad = []
    for c in git("rev-list", "--reverse", "%s..%s" % (base, head)).split():
        first = git("log", "-1", "--format=%s", c).strip()
        parents = git("rev-list", "--parents", "-n", "1", c).split()[1:]
        files = [f for f in git("diff-tree", "--no-commit-id", "--name-only", "-r", "-z", c).split("\0") if f]
        if len(parents) != 1:
            bad.append("%s: a merge commit" % c[:10])
        elif first.startswith("autofix: "):
            continue                     # carried over: tools/automerge.py judges it with its own rules
        else:
            why = commit_problem(cid, first, files)
            if why:
                bad.append("%s: %s" % (c[:10], why))
    return bad


def gh_api(path):
    out = subprocess.run(["gh", "api", path], capture_output=True, text=True, check=False)
    if out.returncode:
        raise RuntimeError("gh api %s: %s" % (path, out.stderr.strip()[:200]))
    return json.loads(out.stdout or "null")


def open_branches(repo, api=gh_api):
    """{branch: {"pr", "sha", "subject"}} of the open pull requests of this repository's own
    automation/update/* and automation/builder/* branches (GET only)."""
    out = {}
    for pr in api("repos/%s/pulls?state=open&per_page=100" % repo) or []:
        head = pr.get("head") or {}
        ref = head.get("ref") or ""
        if (head.get("repo") or {}).get("full_name") != repo or not ref.startswith((PREFIX, BUILDER_PREFIX)):
            continue
        out[ref] = {"pr": pr.get("number"), "sha": head.get("sha", ""), "title": pr.get("title", "")[:200]}
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan")
    p.add_argument("--report", required=True)
    p.add_argument("--branches")
    p.add_argument("--out", required=True)
    p.add_argument("--markdown")
    m = sub.add_parser("message")
    m.add_argument("--report", required=True)
    m.add_argument("--id", required=True)
    c = sub.add_parser("check")
    c.add_argument("--id", required=True)
    c.add_argument("--base", required=True)
    c.add_argument("--head", required=True)
    b = sub.add_parser("branches")
    b.add_argument("--repo", required=True)
    b.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "branches":
        try:
            data = open_branches(a.repo)
        except RuntimeError as e:
            print("::warning::the open candidates could not be read: %s" % str(e).replace("::", ": "))
            data = {}
        Path(a.out).write_text(json.dumps(data, indent=1) + "\n", "utf-8")
        return 0
    if a.cmd == "check":
        if not spec(a.id):
            print("::error::not a candidate: %s" % a.id[:80])
            return 1
        bad = check_range(a.id, a.base, a.head)
        if bad:
            print("::error::the candidate changes what its update may not change:\n" + "\n".join(bad[:40]))
            return 1
        print("the candidate %s changes only its own files" % a.id)
        return 0
    report = json.loads(Path(a.report).read_text("utf-8"))
    if a.cmd == "message":
        cand = next((x for x in report.get("candidates") or () if x.get("id") == a.id), None)
        if not cand or not cand.get("to"):
            print("::error::no update of %s in the report" % a.id[:80])
            return 1
        print(message(cand))
        return 0
    branches = json.loads(Path(a.branches).read_text("utf-8")) if a.branches else {}
    rows = plan(report, branches)
    Path(a.out).write_text(json.dumps({"rows": rows, "matrix": matrix(rows)}, indent=1) + "\n", "utf-8")
    if a.markdown:
        Path(a.markdown).write_text(markdown(rows), "utf-8")
    print(markdown(rows), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
