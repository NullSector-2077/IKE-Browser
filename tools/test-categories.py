#!/usr/bin/env python3
"""Test categories, and what a run really verified (WP4 of the maintenance plan).

A test that was skipped, or a check that did not run, is **not verified**,
never "passed" (ROADMAP.md: "Never report a check that was not actually
run"). This tool knows:

- CATEGORIES: every category of check, and where its result comes from (a step
  of tests.yml, the job of arch.yml or security.yml, the filter lists of the
  candidate);
- REQUIRED: the categories each kind of component needs before an update of it
  counts as verified (tools/inventory.py gives each component its kind);
- AREAS: which part of I.K.E. a test file checks, so the skipped tests are
  listed by area with their reasons.

    test-categories.py --junit FILE [--junit FILE ...] [--json OUT] [--markdown OUT]

reads pytest's junit files (tests.yml writes them) and writes the tests run,
failed and skipped, the skipped ones with their reasons by area, as JSON and as
Markdown for the run's summary. It never fails the run: it only reports.
`verify()` (used by tools/maintenance-report.py) turns the results of a
candidate's runs into a state per required category: passed, failed or not
verified (with the reason). `merge_required()` and `unexpected_skips()` are
what tools/automerge.py asks before the automation's own pull request goes
into main by itself (the verified merge, 2026-11-22).

No network, no GitHub token: the GitHub answers are read by the callers.
"""

import argparse
import fnmatch
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

# category -> (what it checks, where its result comes from: (workflow, job, step))
# step None: the job's own conclusion
CATEGORIES = {
    "lint": ("ruff on the whole repository", ("tests.yml", "tests", "Lint")),
    "unit-integration": ("the whole Python suite with the real Qt WebEngine (headless): unit, integration, "
                         "features, resources", ("tests.yml", "tests", "Tests")),
    "rust": ("the AdBlock engine's own Rust tests", ("tests.yml", "tests", "AdBlock engine (Rust tests)")),
    "licences": ("cargo-deny licences, bans, sources and the licence files (tools/third-party.py --check)",
                 ("tests.yml", "tests", "Licences")),
    "tests-kept": ("no test of the starting commit lost or weakened",
                   ("tests.yml", "tests", "No tests lost")),
    "build": ("the Arch package built with makepkg from the PKGBUILD", ("tests.yml", "tests", "Arch package")),
    "old-cpu": ("the package runs on an emulated Ivy Bridge processor",
                ("tests.yml", "tests", "The package runs on an old processor")),
    "installed": ("the whole suite against the installed package (install and start)",
                  ("tests.yml", "tests", "Tests of the installed package")),
    "arch-packaging": ("Arch Linux's own Python, Qt and Qt WebEngine: suite, makepkg, pacman -U, suite as installed",
                       ("arch.yml", "Arch Linux", None)),
    "sandbox": ("the security tests with the engine's sandbox really on", ("security.yml", "sandbox", None)),
    "advisories": ("RustSec advisories of every crate (cargo-deny)", ("security.yml", "rust-advisories", None)),
    # the full chain, item 4 (2026-11-22): on the commit itself, its engine against main's on today's lists
    "filter-lists": ("today's default filter lists in this commit's engine, no worse than in main's",
                     ("tests.yml", "tests", "Filter lists in this engine")),
    # 2026-11-22: what I.K.E. does for its users (ad and tracker blocking, the fingerprinting
    # surface, the hosts contacted by itself, the security settings) measured on the commit and on
    # main's, in the same job, on the same inputs (tools/no-regression.py): anything weaker fails
    "no-regression": ("nothing gets worse: blocking, fingerprinting surface, network and security settings "
                      "measured on this commit and on main's, nothing weaker",
                      ("tests.yml", "tests", "Nothing gets worse")),
    "desktop": ("a real desktop session (KDE Plasma, notifications, default browser), a real graphics card",
                ("", "", None)),
}
# never run by GitHub Actions: always "not verified", said plainly
NEVER_RUN = {"desktop": "GitHub's runners have no desktop session and no graphics card (software rendering only)"}

# component kind (tools/inventory.py) -> the categories an update of it needs.
# "no-regression" for every kind that changes what reaches users: the AdBlock engine and its
# crates, the builders' Dark Reader ("npm") and uBlock Origin scriptlets ("integrated"), I.K.E.'s
# own code (an AI fix or a security fix is "integrated", tools/automerge.py kinds_of), the filter
# lists, the PKGBUILD ("arch-package")
_ENGINE = ["rust", "licences", "unit-integration", "build", "old-cpu", "installed", "advisories", "tests-kept",
           "no-regression"]
REQUIRED = {
    "crate": _ENGINE,
    "adblock-engine": _ENGINE + ["filter-lists", "arch-packaging"],
    "arch-package": ["arch-packaging", "unit-integration", "installed", "no-regression"],
    "arch-optional": ["arch-packaging", "desktop"],
    "arch-build": ["build", "old-cpu", "arch-packaging"],
    "python-module": ["unit-integration", "arch-packaging", "installed"],
    "pyqt-module": ["unit-integration", "arch-packaging", "installed"],
    "pypi-test": ["lint", "unit-integration", "tests-kept"],
    "pypi-ci": ["lint", "unit-integration"],
    "npm": ["unit-integration", "licences", "installed", "no-regression"],
    "node": ["unit-integration"],
    "integrated": ["unit-integration", "licences", "installed", "tests-kept", "no-regression"],
    "filter-list": ["filter-lists", "no-regression"],
    "github-action": ["lint", "unit-integration", "build"],
    "ci-tool": ["licences", "advisories"],
    "ci-runtime": ["lint", "unit-integration", "build"],
    "runtime-tool": ["desktop"],
    "build-tool": ["build", "old-cpu", "arch-packaging"],
    "vendored": _ENGINE,
}

# the part of I.K.E. a test file checks, for the list of skipped tests
AREAS = (
    ("licences", ("test_licences.py", "test_credits.py")),
    ("automation and maintenance", ("test_components.py", "test_automation.py", "test_merge_and_mail.py",
                                    "test_publish.py", "test_inventory*.py", "test_maintenance*.py")),
    ("ad blocking", ("test_adblock.py", "test_videoads.py", "test_freeway.py", "test_userscript*.py")),
    ("dark mode (Dark Reader)", ("test_darkreader*.py", "test_dark_*.py", "test_sitetint.py")),
    ("security and privacy", ("test_sandbox.py", "test_security.py", "test_site_isolation.py", "test_fingerprint*.py",
                              "test_home_network*.py", "test_frame_guard*.py", "test_referrer.py",
                              "test_client_hints.py", "test_engine_switches.py", "test_lookalike.py",
                              "test_passwords.py", "test_media_secret.py", "test_page_traces.py",
                              "test_accept_language.py", "test_switches.py", "test_safe_downloads.py",
                              "test_clean_site.py")),
    ("desktop integration", ("test_plasma.py", "test_platform.py", "test_mailto.py", "test_videogpu.py",
                             "test_mediacheck.py", "test_handoff.py")),
    ("updates", ("test_updater.py", "test_update_safety.py", "test_versions.py", "test_engine_age.py",
                 "test_repair.py")),
    ("speed", ("test_performance.py", "test_speed.py", "test_startup.py", "test_darkreader_cost.py")),
)
DEFAULT_AREA = "interface and features"
MAX_LISTED = 200


# The verified merge (2026-11-22, the owner's decision): the automation's own
# pull request goes into main by itself only when every category below passed
# on its last commit, whatever components it changes (the owner's words:
# "tests, sandbox, Security, Arch Linux"), plus what its components' kinds
# need (REQUIRED). "desktop" (never run by GitHub) is not here: a kind that
# needs it is never fully verified, so it waits for the owner. "filter-lists"
# is read on the commit itself since the full chain (tests.yml, the step
# "Filter lists in this engine"), so a new AdBlock engine can be fully verified.
MERGE_ALWAYS = ("lint", "unit-integration", "rust", "licences", "tests-kept", "build", "old-cpu", "installed",
                "arch-packaging", "sandbox", "advisories")

# A skipped test is a required test not run, and keeps the merge for the
# owner, unless another check of the same commit runs it or it only runs on
# purpose. (reason, as pytest writes it) -> where it is verified instead.
EXPECTED_SKIPS = (
    (r"^IKE_TEST_SANDBOX=1 only", "security.yml's sandbox job runs it with the sandbox on (and fails if it skips)"),
    (r"^this run has every protection on", "the sandbox run of security.yml"),
    (r"^only for the installed package \(IKE_TEST_APP\)", "the tests of the installed package"),
    (r"^the sources are checked once, not for the installed copy", "the tests of the sources"),
    (r"^cargo is not installed here: GitHub Actions runs this check", "the Licences step"),
    (r"^only as root \(the Arch container\)", "arch.yml runs as root"),
    (r"^IKE_TEST_NETWORK=1 ", "the daily component check uses the real sources"),
    (r"^IKE_UI_SHOTS=", "pictures for a person, not a check"),
    (r"^IKE_FIT_LANGS: one group", "a split run of the same test"),
    (r"^KDE's Breeze icons and platform theme are not installed here|^KDE's theme did not load here"
     r"|^the \S+ style is not installed here|^desktop \w+: ", "arch.yml installs the desktops' themes and runs it"),
    # 2026-11-22, read from a real Tests run on GitHub's runners (run 45020817248 of PR #105, its
    # "What the tests verified"): environmental there, each verified elsewhere
    (r"^the desktops are tested as Arch Linux packages them \(not Arch here\)$",
     "arch.yml: the desktops' icons and colours as Arch packages them (tests/desktops.py), each desktop a case"),
    (r"^Qt's kde platform theme is not installed$",
     "arch.yml installs plasma-integration and runs KDE's colours (its step \"Interface in every widget style\")"),
    # the PKGBUILD's optional dependencies (tests/test_optional_deps.py, WP10 (e)): Arch packages, not on
    # Ubuntu's runners
    (r"^optional dependency [a-z0-9+._-]+ is not installed here \(an Arch package: arch\.yml installs it",
     "arch.yml installs the optional dependencies Arch ships and runs their cases"),
    (r"^optional dependency [a-z0-9+._-]+ is not installed here \(an AUR package: no check of GitHub installs it",
     "never: an AUR package no check can install; said as not verified (the owner's own system)"),
)


def merge_required(kinds):
    """The categories a merge by itself needs for components of these kinds, in CATEGORIES' order."""
    need = set(required_for(kinds)) | set(MERGE_ALWAYS)
    return [c for c in CATEGORIES if c in need]


def unexpected_skips(skips):
    """The skipped tests that no other check of the commit runs (EXPECTED_SKIPS): required tests not run."""
    return [s for s in skips or () if not any(re.search(p, s.get("reason") or "") for p, _ in EXPECTED_SKIPS)]


def area_of(test_file):
    name = Path(test_file or "").name
    for area, patterns in AREAS:
        if any(fnmatch.fnmatch(name, p) for p in patterns):
            return area
    return DEFAULT_AREA


def required_for(kinds):
    """The categories needed by components of these kinds, in CATEGORIES' order."""
    need = set()
    for kind in kinds:
        need.update(REQUIRED.get(kind, ["unit-integration"]))
    return [c for c in CATEGORIES if c in need]


def _file_of(case):
    """The test file of a junit testcase (pytest writes tests.test_x as classname)."""
    f = case.get("file")
    if f:
        return f
    parts = (case.get("classname") or "").split(".")
    for i in range(len(parts), 0, -1):
        if parts[i - 1].startswith("test_"):
            return "/".join(parts[:i]) + ".py"
    return "?"


def read_junit(paths):
    """{"files": [...], "tests", "passed", "failed", "skipped", "errors", "skips": [{"test", "area", "reason"}],
    "failures": [test ids], "unreadable": [path: why]} over every junit file; a missing or broken file is
    listed as unreadable, never counted as passed."""
    out = {"files": [], "tests": 0, "passed": 0, "failed": 0, "skipped": 0, "errors": 0, "skips": [],
           "failures": [], "unreadable": []}
    for path in paths:
        try:
            root = ET.parse(path).getroot()
        except (OSError, ET.ParseError) as e:
            out["unreadable"].append("%s: %s" % (path, type(e).__name__))
            continue
        out["files"].append(str(path))
        for case in root.iter("testcase"):
            out["tests"] += 1
            test = "%s::%s" % (_file_of(case), case.get("name") or "?")
            skipped = case.find("skipped")
            if case.find("failure") is not None:
                out["failed"] += 1
                out["failures"].append(test)
            elif case.find("error") is not None:
                out["errors"] += 1
                out["failures"].append(test)
            elif skipped is not None:
                out["skipped"] += 1
                reason = (skipped.get("message") or skipped.text or "no reason given").strip()
                out["skips"].append({"test": test, "area": area_of(_file_of(case)), "reason": reason[:300],
                                     "junit": Path(path).name})
            else:
                out["passed"] += 1
    return out


def skips_by_area(skips):
    """{area: {reason: [tests]}}."""
    out = {}
    for s in skips:
        out.setdefault(s["area"], {}).setdefault(s["reason"], []).append(s["test"])
    return out


def junit_markdown(info):
    """The run summary: counts, then every skipped test as NOT VERIFIED, by area and reason."""
    out = ["### What the tests verified", ""]
    if not info["files"]:
        out += ["**Not verified**: no test results could be read (%s)." % ("; ".join(info["unreadable"]) or
                                                                            "no junit file"), ""]
        return "\n".join(out) + "\n"
    out.append("Tests: %d; passed %d, failed %d, errors %d, **skipped %d (not verified)**." % (
        info["tests"], info["passed"], info["failed"], info["errors"], info["skipped"]))
    if info["unreadable"]:
        out.append("Results not read (not verified): %s." % "; ".join(info["unreadable"]))
    if info["skipped"]:
        out += ["", "A skipped test is **not verified**, never passed:", "",
                "| Area | Reason | Tests |", "|---|---|---|"]
        listed = 0
        for area, reasons in sorted(skips_by_area(info["skips"]).items()):
            for reason, tests in sorted(reasons.items()):
                shown = ", ".join("`%s`" % t.replace("|", "\\|") for t in tests[:6])
                more = " and %d more" % (len(tests) - 6) if len(tests) > 6 else ""
                out.append("| %s | %s | %d: %s%s |" % (area, reason.replace("|", "\\|").replace("\n", " "),
                                                      len(tests), shown, more))
                listed += 1
                if listed >= MAX_LISTED:
                    break
    return "\n".join(out) + "\n"


def verify(required, results, skips=None):
    """The state of each required category for one candidate.

    results: {category: "success" | "failure" | "skipped" | "cancelled" | "running" | "" (not run) ...}
    as the callers read them from GitHub; skips: read_junit()'s "skips" of that run, or None when the
    junit could not be read. Returns [{"category", "state", "detail"}], state one of "passed", "failed",
    "not verified": a skipped step, a run that did not happen or is still running, a category GitHub cannot
    run, or a suite whose skipped tests are listed (the category passed, those tests did not)."""
    rows = []
    for cat in required:
        res = (results or {}).get(cat, "")
        desc = CATEGORIES.get(cat, ("unknown category", None))[0]
        if cat in NEVER_RUN:
            rows.append({"category": cat, "state": "not verified", "detail": NEVER_RUN[cat]})
        elif res == "success":
            detail = desc
            if cat in ("unit-integration", "installed") and skips is None:
                rows.append({"category": cat, "state": "not verified",
                             "detail": "the step passed, but its test results could not be read"})
                continue
            if cat in ("unit-integration", "installed") and skips:
                mine = [s for s in skips if (s.get("junit") == "junit-installed.xml") == (cat == "installed")]
                if mine:
                    detail = "%s; %d skipped tests not verified" % (desc, len(mine))
            rows.append({"category": cat, "state": "passed", "detail": detail})
        elif res in ("failure", "timed_out"):
            rows.append({"category": cat, "state": "failed", "detail": desc})
        else:
            why = {"skipped": "the step was skipped", "cancelled": "the run was cancelled",
                   "running": "still running", "queued": "still queued",
                   "": "not run (yet) on this commit"}.get(res, "result: %s" % res)
            rows.append({"category": cat, "state": "not verified", "detail": why})
    return rows


def results_from_runs(runs):
    """{category: result} from the runs of one commit, as tools/maintenance-ledger.py gathers them:
    runs = {"tests.yml": run, "arch.yml": run, "security.yml": run, "daily-maintenance.yml": run}, each
    None (no run) or {"status", "conclusion", "jobs": {job: {"status", "conclusion", "steps": {step: result}}}}.
    A step or job that has not finished in a running run is "running"; one a finished run does not have
    is "" (not run)."""
    out = {}
    for cat, (_desc, (workflow, job, step)) in CATEGORIES.items():
        if not workflow:
            continue
        run = (runs or {}).get(workflow)
        if not run:
            out[cat] = ""
            continue
        busy = run.get("status") not in ("completed", None)
        j = (run.get("jobs") or {}).get(job)
        if j is None:
            out[cat] = "running" if busy else ""
            continue
        if step is None:
            res = j.get("conclusion") or ""
        else:
            res = (j.get("steps") or {}).get(step) or ""
        if not res and (busy or j.get("status") not in ("completed", None)):
            res = "running"
        out[cat] = res
    return out


def verdict(rows):
    """"failed" if any required category failed, "not verified" if any is not verified, else "passed"."""
    states = {r["state"] for r in rows}
    return "failed" if "failed" in states else "not verified" if "not verified" in states or not rows else "passed"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--junit", action="append", default=[], help="a pytest junit file (repeatable)")
    ap.add_argument("--json", help="write the summary as JSON")
    ap.add_argument("--markdown", help="write the summary as Markdown")
    args = ap.parse_args(argv)
    info = read_junit(args.junit)
    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(info, indent=1) + "\n", "utf-8")
    text = junit_markdown(info)
    if args.markdown:
        Path(args.markdown).write_text(text, "utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
