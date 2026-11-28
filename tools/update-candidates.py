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
    darkreader         Dark Reader's lists (tools/build-darkreader-lists.py): never a candidate, the browser fetches them
    breeze-icons       KDE's Breeze icons of the set "Breeze (KDE)" (rebuilt by tools/build-breeze-icons.py)
    test-qt            Qt's wheels of the automatic tests
    test-tools         pytest, ruff and what they bring
    test-libs          the other libraries of the automatic tests
    pkgbuild           the PKGBUILD's depends, optdepends and minima (tools/pkgbuild-sync.py)
    ci-<name>          a pin of the workflows (tools/ci-pins.py: actions, cargo-deny, Python, Node.js, Rust)
    drill-<name>       an AUTOMAT drill (tools/automat-drill.py): never in a daily plan, never merged; its
                       commit only adds the drill's marker and the scenario's breaks

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
  I.K.E.'s existing changes, tools/builder-anchor.py; uBlock Origin's
  scriptlets only since 1.1.30), or, for a builder with nothing to re-anchor
  (Dark Reader's lists, KDE's Breeze icons), waits for a person;
- a source unreachable today makes nothing (the next run tries again).

Each candidate's own commit is ``update: <id> <from> -> <to> (no AI)`` and may
change only FILES of its id, the licence files and, when it ships, the version
files (the version raised by tools/prepare-maintenance.py when main's version
is published). The same function (commit_problem) is what the workflow checks
before it pushes and what tools/automerge.py checks before it merges.

    update-candidates.py plan --report report.json [--pins pins.json] [--pkgbuild pkgbuild.json]
                              [--branches branches.json] --out plan.json [--markdown OUT]
    update-candidates.py message --report report.json --id ID
    update-candidates.py bullet --report report.json --id ID      (the CHANGELOG line)
    update-candidates.py component --report report.json --id ID --out FILE
                              (the candidate as a component report, for tools/maintenance-report.py)
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
                r"|test-libs|pkgbuild|ci-[a-z0-9-]{1,60}|arch-testing-\d{4}-\d\d-\d\d|drill-[a-z0-9]{1,30})$")
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
    # Dark Reader, uBlock Origin's scriptlets and every component added later: components.json, the
    # component manifest (tools/component-manifest.py); see spec() and manifest_specs() below
    "test-qt": {"files": ("tools/test-requirements.txt",), "serial": "test-requirements", "ships": False,
                "wrapper": False, "kinds": ("pypi-test",)},
    "test-tools": {"files": ("tools/test-requirements.txt",), "serial": "test-requirements", "ships": False,
                   "wrapper": False, "kinds": ("pypi-test",)},
    "test-libs": {"files": ("tools/test-requirements.txt",), "serial": "test-requirements", "ships": False,
                  "wrapper": False, "kinds": ("pypi-test",)},
    "pkgbuild": {"files": (), "serial": "", "ships": True, "wrapper": False, "kinds": ("arch-package",)},
    "ci-": {"files": (".github/workflows/", ".github/actions/"), "serial": "", "ships": False, "wrapper": False,
            "kinds": ("github-action",)},
    # WP10 (b): a fix of main's code for Arch's next packages (only the automatic fix's commits)
    "arch-testing-": {"files": (), "serial": "", "ships": True, "wrapper": False, "kinds": ("arch-package",)},
    # an AUTOMAT drill (tools/automat-drill.py): its own commit only adds the drill's marker and writes the
    # scenario's breaks; no serial group (it never holds back a real candidate); tools/automerge.py never merges it
    "drill-": {"files": ("tools/automat-drill.active", "tools/automat-drill.json"), "serial": "", "ships": False,
               "wrapper": False, "kinds": ("pypi-test",), "drill": True},
}
# the order in which candidates of one serial group go (the security fixes' branches always count as open)
PRIORITY = ("adblock", "pyo3", "crates", "crate-major-", "test-qt", "test-tools", "test-libs")
# AUTOMAT made simpler (2026-11-27, the owner's approval): the low-risk candidates are made once a week, on
# WEEKLY_DAY (UTC), not every day. In the week of 2026-11-20 crates and ci-cargo-deny alone started 26 runs of
# Tests and 25 of Arch Linux, each rebuilt as an upstream moved by a patch release. What ships to users and
# changes their protection stays daily: the AdBlock engine, pyo3, a crate's new major version, uBlock Origin's
# scriptlets, Breeze, the PKGBUILD, and test-qt (the early warning of a Qt release). Security fixes
# are their own branches (automation/update/security-*) and never wait. An open weekly candidate is left as it
# is between Mondays: it still merges by itself when verified.
# 1.1.30: Dark Reader's engine left I.K.E.; its lists are fetched by the browser itself once a day
# (ike/darklists.py, 1.1.27: no new version every day for simple lists), so the copy I.K.E. comes with (for a
# new profile, or one that could not fetch them) is refreshed weekly: never more than a week old in a release.
WEEKLY = ("crates", "test-tools", "test-libs", "ci-")
WEEKLY_DAY = 0                  # Monday
UPDATE_COMMIT = re.compile(r"^update: ([a-z0-9_-]+) (.{1,300}) -> (.{1,300}) \(no AI\)$")
CI_COMMIT = re.compile(r"^ci: ([a-z0-9-]+) (\S{1,80}) -> (\S{1,80}) \(tools/ci-pins\.py, no AI\)$")


def _manifest():
    import importlib.util
    path = Path(__file__).resolve().parent / "component-manifest.py"
    sp = importlib.util.spec_from_file_location("component_manifest", path)
    mod = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(mod)
    return mod


def _anchor_builders():
    """The ids whose builder an AI may re-anchor on automation/builder/<id> (tools/builder-anchor.py)."""
    import importlib.util
    path = Path(__file__).resolve().parent / "builder-anchor.py"
    sp = importlib.util.spec_from_file_location("builder_anchor", path)
    mod = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(mod)
    return tuple(mod.BUILDERS)


def manifest_specs(root=ROOT):
    """{id: its candidate's rules} of every entry of the component manifest (components.json): its
    files, its builder, its kinds. A new entry gets its candidate with no change here."""
    mf = _manifest()
    return {cid: mf.spec(cid, root) for cid in mf.components(root)}


def spec(cid, root=ROOT):
    """The rules of a candidate id (SPECS, or the component manifest's entry), or None."""
    if not cid or not isinstance(cid, str):
        return None
    if cid in SPECS:
        return SPECS[cid]
    if ID.match(cid):
        for key, value in SPECS.items():
            if key.endswith("-") and cid.startswith(key):
                return value
    return manifest_specs(root).get(cid)


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


TEST_TOOLS = ("pytest", "ruff", "pluggy", "iniconfig", "packaging", "pygments", "colorama", "exceptiongroup",
              "tomli")                 # as tools/check-components.py's groups of the test packages


def candidate_for(rec):
    """The candidate id that carries an inventory record's update (tools/inventory.py), or "" when no
    candidate can (a major version of a crate only adblock brings: it comes with a new adblock)."""
    kind, name = rec.get("kind", ""), str(rec.get("name", ""))
    compat = str(rec.get("compatibility", ""))
    if rec.get("candidate") and spec(rec["candidate"]):
        return rec["candidate"]              # a component of the manifest: the inventory names its entry
    if kind == "adblock-engine":
        return "adblock"
    if kind == "crate":
        if name == "pyo3":
            return "pyo3" if compat.startswith("major") else "crates"
        if compat.startswith("major"):
            return "crate-major-%s" % name if rec.get("type") == "direct" else ""
        return "crates"
    if kind in ("integrated", "npm"):
        return "darkreader" if name.lower().startswith("dark") else "ubo-scriptlets" if "ublock" in name.lower() \
            else ""
    if kind == "pypi-test":
        low = re.sub(r"[-_.]+", "-", name).lower()
        return "test-qt" if low.startswith("pyqt6") else "test-tools" if low in TEST_TOOLS else "test-libs"
    if kind == "github-action":
        return "ci-" + re.sub(r"[^a-z0-9]+", "-", "/".join(name.split("/")[:2]).lower()).strip("-")
    if kind == "ci-tool" and name == "cargo-deny":
        return "ci-cargo-deny"
    if kind in ("ci-runtime", "node"):
        return "ci-node" if "node" in name.lower() else "ci-python" if "python" in name.lower() else ""
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


def weekly(cid):
    """True for a low-risk candidate made only on WEEKLY_DAY."""
    return any(cid == w or (w.endswith("-") and cid.startswith(w)) for w in WEEKLY)


def plan(report, branches=None, builder_apply=(), today=None):
    """What today's run does with each candidate (pure): [{"id", "action", "branch", "reason", ...}].

    report: tools/check-components.py --json (its "candidates"); branches: {branch: {"pr", "sha",
    "subject"}} of the open pull requests of automation/update/* and automation/builder/*.
    action: make (rebuilt from main, pushed when it differs), queued (another candidate of its serial
    group is open), builder (the builder refused: the builder's path), weekly (a low-risk candidate, made on
    WEEKLY_DAY only), unreachable, skip. today: the day of the run (UTC), for WEEKLY."""
    import datetime as dt
    today = today or dt.datetime.now(dt.timezone.utc).date()
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
               "component": c.get("component", ""), "wrapper": s["wrapper"], "ships": s["ships"],
               "sha": c.get("sha", ""), "base": "main"}
        on_builder = cid in (builder_apply or ()) and bool(s.get("builder"))
        if c.get("error"):
            out.append(dict(row, action="unreachable", reason="its source could not be read today: %s"
                            % c["error"][:200]))
            continue
        if on_builder and not c.get("refused") and c.get("to"):
            # WP11: the re-anchored builder accepts the new version: the update goes onto its branch
            b = builder_branch(cid)
            out.append(dict(row, action="make", branch=b, base=b, message=message(c),
                            reason="the re-anchored builder on %s accepts the new version: the update is applied "
                                   "there" % b))
            continue
        if c.get("refused"):
            b = builder_branch(cid)
            if not s.get("builder"):
                out.append(dict(row, action="skip", reason="refused, and no builder of I.K.E.'s for it"))
            elif cid not in _anchor_builders():
                # 1.1.24 (KDE's Breeze icons): a builder with no patches to re-anchor; the component stays
                # at the version in use, the daily check tries every new release again
                out.append(dict(row, action="skip", reason="refused by its builder (%s); it has no patches an AI "
                                "may re-anchor (tools/builder-anchor.py): the component stays at the version in "
                                "use and the daily report says why" % c.get("step", "?")))
            elif b in branches and not on_builder:
                out.append(dict(row, action="skip", branch=b, reason="the builder's re-anchoring already waits on "
                                "%s (PR #%s)" % (b, branches[b].get("pr", "?"))))
            else:
                out.append(dict(row, action="builder", branch=b, reason="the builder refused the new version "
                                "(%s): an AI may re-anchor I.K.E.'s existing patches on %s" % (c.get("step", "?"), b)))
            continue
        if not c.get("to"):
            out.append(dict(row, action="skip", reason="nothing newer"))
            continue
        if weekly(cid) and today.weekday() != WEEKLY_DAY:
            known = branches.get(row["branch"]) or {}
            out.append(dict(row, action="weekly", reason="a low-risk update: made on Mondays only%s" % (
                " (the open candidate, PR #%s, stays as it is and still merges by itself)" % known["pr"]
                if known else "")))
            continue
        group = s["serial"]
        mine = row["branch"]
        holder = open_serial.get(group) if group else None
        what = "the engine's Cargo.lock" if group == "cargo" else "the test packages' pins"
        if group and holder and holder != mine:
            out.append(dict(row, action="queued", reason="waits for %s (one change of %s at a time)" % (
                holder, what)))
            continue
        if group and taken.get(group) and taken[group] != mine:
            out.append(dict(row, action="queued", reason="waits for %s, made first today (one change of %s at "
                            "a time)" % (taken[group], what)))
            continue
        if group:
            taken[group] = mine
        known = branches.get(mine) or {}
        why = "rebuilt from main; pushed only when it differs from the open candidate (PR #%s)" % known["pr"] \
            if known else "a new candidate from main"
        out.append(dict(row, action="make", reason=why, message=message(c)))
    return out


def gather(report, pins=None, pkgbuild=None):
    """Every candidate of today: the components' (tools/check-components.py), the workflows' pins
    (tools/ci-pins.py check) and the PKGBUILD's dependencies (tools/pkgbuild-sync.py plan)."""
    cands = list((report or {}).get("candidates") or ())
    cands += [dict(c) for c in (pins or {}).get("candidates") or () if spec(c.get("id"))]
    p = pkgbuild or {}
    if p.get("depends") or p.get("optdepends") or p.get("move") or p.get("minima"):
        what = ["depends + " + ", ".join(p.get("depends", []) + p.get("move", []))] if (p.get("depends") or
                                                                                       p.get("move")) else []
        what += ["optdepends + " + ", ".join(x[0] for x in p.get("optdepends", []))] if p.get("optdepends") else []
        what += ["minima " + ", ".join("%s>=%s" % kv for kv in sorted(p.get("minima", {}).items()))] \
            if p.get("minima") else []
        cands.append({"id": "pkgbuild", "component": "PKGBUILD dependencies", "from": "the PKGBUILD of main",
                      "to": "; ".join(what), "note": "what the code needs (tools/inventory.py, # needs: markers)"})
    return {"candidates": cands}


def bullet(cand):
    """The CHANGELOG line of a candidate (no code, no link: tools/automerge.py version_problem)."""
    text = "- %s: %s -> %s" % (cand.get("component") or cand["id"], cand.get("from") or "current",
                               cand.get("to") or "updated")
    if cand.get("note"):
        text += " (%s)" % cand["note"]
    text = re.sub(r"https?://\S+", "", text.replace("`", "'"))
    return re.sub(r"\s+", " ", text).strip()[:400]


def component(cand):
    """A component report (tools/check-components.py's shape) of one candidate."""
    return {"updates": 1, "errors": 0, "refused": 0, "candidates": [cand],
            "components": [{"name": cand.get("component") or cand["id"], "current": cand.get("from", ""),
                            "latest": cand.get("to", ""), "update": True, "note": cand.get("note", ""), "also": "",
                            "error": "", "refused": None, "id": cand["id"]}]}


def matrix(rows):
    """The candidates the workflow's matrix makes today (make and builder)."""
    keys = ("id", "action", "branch", "base", "from", "to", "sha", "ships")
    return [{k: str(r.get(k, "")) for k in keys} for r in rows if r["action"] in ("make", "builder")]


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


def _tool(name):
    import importlib.util
    path = Path(__file__).resolve().parent / (name + ".py")
    sp = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    mod = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(mod)
    return mod


def check_range(cid, base, head):
    """The problems of the commits base..head of candidate cid: each one its own update commit
    (commit_problem) or a commit of the automatic fix (carried over from the open candidate); for a
    CI pin only tools/ci-pins.py's commits and edits, for the PKGBUILD only tools/pkgbuild-sync.py's."""
    if cid.startswith("ci-") or cid == "pkgbuild":
        return check_tool_range(cid, base, head)
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


def check_tool_range(cid, base, head):
    """A CI pin's or the PKGBUILD's candidate: only its tool's commits, and only its tool's edits."""
    bad = []
    tool = _tool("ci-pins" if cid.startswith("ci-") else "pkgbuild-sync")
    for c in git("rev-list", "--reverse", "%s..%s" % (base, head)).split():
        first = git("log", "-1", "--format=%s", c).strip()
        m = tool.COMMIT.match(first)
        if not m or (cid.startswith("ci-") and m.group(1) != cid):
            bad.append("%s: not the commit of %s's own tool (%s)" % (c[:10], cid, first[:60]))
    for name in [n for n in git("diff", "--name-only", "-z", base, head).split("\0") if n]:
        old = subprocess.run(["git", "show", "%s:%s" % (base, name)], capture_output=True, text=True).stdout
        new = subprocess.run(["git", "show", "%s:%s" % (head, name)], capture_output=True, text=True).stdout
        if cid.startswith("ci-"):
            why = tool.verify_change(cid, old, new) if name.startswith((".github/workflows/", ".github/actions/")) \
                else "not a workflow"
        elif name == "PKGBUILD":
            why = tool.problem(old, new)
        elif name in VERSION_FILES:
            why = ""                    # the version raised by tools/prepare-maintenance.py; the merge checks it
        else:
            why = "not the PKGBUILD"
        if why:
            bad.append("%s: %s" % (name, why))
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
    p.add_argument("--pins")
    p.add_argument("--pkgbuild")
    p.add_argument("--branches")
    p.add_argument("--builder-apply", default="", help="a builder's candidate applied on its own branch (WP11)")
    p.add_argument("--out", required=True)
    p.add_argument("--markdown")
    p.add_argument("--candidates-out", help="every candidate of today, as the matrix's jobs read them")
    for name in ("message", "bullet", "component"):
        m = sub.add_parser(name)
        m.add_argument("--report", required=True)
        m.add_argument("--id", required=True)
        m.add_argument("--out")
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
    if a.cmd in ("message", "bullet", "component"):
        cand = next((x for x in report.get("candidates") or () if x.get("id") == a.id), None)
        if not cand or not cand.get("to"):
            print("::error::no update of %s in the report" % a.id[:80])
            return 1
        text = message(cand) if a.cmd == "message" else bullet(cand) if a.cmd == "bullet" else \
            json.dumps(component(cand), indent=1)
        if a.out:
            Path(a.out).write_text(text + "\n", "utf-8")
        print(text)
        return 0

    def read(path):
        try:
            return json.loads(Path(path).read_text("utf-8")) if path else {}
        except (OSError, ValueError) as e:
            print("::warning::%s could not be read: %s" % (path, e))
            return {}
    branches = read(a.branches)
    everything = gather(report, read(a.pins), read(a.pkgbuild))
    if a.candidates_out:
        Path(a.candidates_out).write_text(json.dumps(everything, indent=1) + "\n", "utf-8")
    rows = plan(everything, branches, builder_apply=[a.builder_apply] if a.builder_apply else ())
    Path(a.out).write_text(json.dumps({"rows": rows, "matrix": matrix(rows)}, indent=1) + "\n", "utf-8")
    if a.markdown:
        Path(a.markdown).write_text(markdown(rows), "utf-8")
    print(markdown(rows), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
