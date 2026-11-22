#!/usr/bin/env python3
"""The body of the maintenance candidate's pull request (WP13 of the maintenance plan).

    maintenance-report.py --components component-report.json --out body.md
                          [--report-md component-report.md] [--status status.json]
                          [--autofix FILE] [--licences FILE] [--lists filter-lists.json]
                          [--engine builds|broken] [--pushed]

It lists, for the owner who decides the merge:

- the components, old -> new, and why (tools/check-components.py's report);
- the automatic fix's changes the candidate carries (--autofix: `git log
  --format='%h %s'` of its "autofix:" commits);
- the problems found: builders that refused, sources unreachable, a new engine
  that does not build, filter-list findings;
- the tests run on the candidate's commit and their results, by category
  (tools/test-categories.py), and what is **not verified**: a category not run
  (yet), a skipped test (by area, with its reason), what GitHub cannot run;
- the security checks (sandbox, RustSec advisories) and the licences
  (tools/third-party.py --check, --licences, and the "Licences" step);
- the limits of what the automation checked.

--status is tools/maintenance-ledger.py gather for the candidate's commit. A
candidate pushed in this run (--pushed) has no results yet: every category is
"not verified (not run yet)", and the next daily run writes the results here.
No network, no token.
"""

import argparse
import importlib.util
import json
import sys
from pathlib import Path

# tools/check-components.py's component names -> tools/inventory.py's kinds
KINDS = (("adblock-rust", "adblock-engine"), ("Rust crates", "crate"), ("uBlock Origin", "integrated"),
         ("Dark Reader", "integrated"), ("Qt WebEngine / PyQt6", "pypi-test"))
LIMITS = (
    "GitHub's runners have no desktop session and no graphics card: KDE Plasma, notifications, the default "
    "browser setting and video decoding are **not verified** here (the owner tries them on CachyOS).",
    "\"Arch Linux\" (arch.yml) runs on the candidate (since 2026-11-22): Arch's own Python, Qt and Qt WebEngine, "
    "the package built with makepkg and installed with pacman; again on `main` after the merge.",
    "A skipped test is not verified, never passed; the list above names each one with its reason.",
    "The automatic fix's commits (if any) were written by an AI under the guard's rules "
    "(tools/check-autofix-patch.py). The workflow merges the candidate by itself only when it is fully verified "
    "(tools/automerge.py); otherwise it waits for the owner and says why.",
    "Vulnerabilities: only the RustSec advisories of the engine's crates are checked (cargo-deny); Python, npm, "
    "Arch and the GitHub Actions are not checked for advisories yet.",
)


def _tests_tool():
    spec = importlib.util.spec_from_file_location("test_categories", Path(__file__).resolve().parent /
                                                  "test-categories.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _md(text):
    return str(text or "").replace("|", "\\|").replace("\n", " ")


def kind_of(name):
    for prefix, kind in KINDS:
        if str(name).startswith(prefix):
            return kind
    return "integrated"


def compose(components, report_md="", status=None, autofix="", licences="", lists=None, engine="",
            pushed=False):
    tc = _tests_tool()
    comps = (components or {}).get("components", [])
    moving = [c for c in comps if c.get("update") or c.get("also")]
    out = ["## What this candidate changes", ""]
    if moving:
        out += ["| Component | In use | New | Why |", "|---|---|---|---|"]
        for c in moving:
            why = "; ".join(x for x in (c.get("note"), ("also newer: " + c["also"]) if c.get("also") else "") if x)
            out.append("| %s | %s | %s | %s |" % (_md(c.get("name")), _md(c.get("current")), _md(c.get("latest")),
                                                  _md(why or "a newer version")))
    else:
        out.append("No component update (only carried automatic fixes, or a rebuild).")

    out += ["", "## Changes of the automatic fix (AutoFix)", ""]
    lines = [ln.strip() for ln in (autofix or "").splitlines() if ln.strip()]
    out += ["- `%s`" % _md(ln) for ln in lines] if lines else ["None."]

    out += ["", "## Problems found", ""]
    problems = []
    for c in comps:
        if c.get("refused"):
            r = c["refused"]
            problems.append("**%s**: I.K.E.'s builder refused %s (step: %s): kept at %s, a person adapts the builder"
                            % (c["name"], r.get("latest", "?"), r.get("step", "?"), r.get("current", "?")))
        if c.get("error"):
            problems.append("**%s**: not checked (%s)" % (c["name"], _md(c["error"])[:200]))
    if engine == "broken":
        problems.append("**the new AdBlock engine does not build with I.K.E.'s wrapper yet**: its tests fail here "
                        "and the automatic fix may change only the wrapper")
    if lists:
        problems += ["filter lists: %s" % _md(f) for f in lists.get("findings", [])]
        if lists.get("state") == "unreachable":
            problems.append("filter lists: none could be downloaded (not verified)")
    elif engine == "builds":
        problems.append("filter lists: not checked in the candidate's engine (not verified)")
    out += ["- " + p for p in problems] if problems else ["None found."]

    cand = (status or {}).get("candidate") or {}
    runs = {} if pushed else (cand.get("runs") or {})
    required = tc.required_for(sorted({kind_of(c.get("name")) for c in moving} or {"integrated"}))
    results = tc.results_from_runs(runs)
    if lists is not None:
        results["filter-lists"] = "failure" if lists.get("findings") else (
            "success" if lists.get("state") == "ok" else "")
    rows = tc.verify(required, results, None if pushed else cand.get("skips"))
    verdict = tc.verdict(rows)
    out += ["", "## Tests on this commit", ""]
    if pushed or not (runs.get("tests.yml") or {}).get("status"):
        out.append("The tests were started on this commit now: their results are in the checks below, and the "
                   "next daily run writes them here. Until then everything is **not verified**.")
        out.append("")
    skips = None if pushed else cand.get("skips")
    if verdict == "passed" and skips:
        out.append("Verdict: **passed** (%d skipped tests not verified: listed below)." % len(skips))
    else:
        out.append("Verdict: **%s**." % verdict)
    out += ["", "| Category | Result | Detail |", "|---|---|---|"]
    out += ["| %s | %s | %s |" % (r["category"], "**%s**" % r["state"] if r["state"] != "passed" else r["state"],
                                  _md(r["detail"])) for r in rows]
    unverified = [r["category"] for r in rows if r["state"] == "not verified"]
    if unverified:
        out += ["", "Not verified: %s." % ", ".join(unverified)]
    if skips:
        out += ["", "<details><summary>Skipped tests: not verified (%d)</summary>" % len(skips), "",
                "| Area | Reason | Tests |", "|---|---|---|"]
        for area, reasons in sorted(tc.skips_by_area(skips).items()):
            for reason, tests in sorted(reasons.items()):
                out.append("| %s | %s | %s |" % (area, _md(reason), _md(", ".join(tests[:8]) +
                                                                     (" ..." if len(tests) > 8 else ""))))
        out += ["", "</details>"]

    out += ["", "## Security checks", ""]
    for cat in ("sandbox", "advisories"):
        row = next((r for r in tc.verify([cat], results)), None)
        out.append("- %s: **%s** (%s)" % (tc.CATEGORIES[cat][0], row["state"], row["detail"]))

    out += ["", "## Licences", ""]
    lic = next(r for r in tc.verify(["licences"], results))
    out.append("- the \"Licences\" step on this commit: **%s** (%s)" % (lic["state"], lic["detail"]))
    text = (licences or "").strip()
    if text:
        last = text.splitlines()[-1]
        good = last.strip() == "exit 0"
        out.append("- `tools/third-party.py --check` when the candidate was made: **%s**" % (
            "passed" if good else "failed" if last.startswith("exit ") else "not verified"))
        out += ["", "```text", "\n".join(text.splitlines()[-12:]).replace("```", "'''"), "```"]
    else:
        out.append("- `tools/third-party.py --check` when the candidate was made: **not verified** (not run)")

    out += ["", "## Limits", ""] + ["- " + x for x in LIMITS]
    if report_md.strip():
        out += ["", "<details><summary>The component report</summary>", "", report_md.strip(), "", "</details>"]
    return "\n".join(out) + "\n"


def _read(path, as_json=True):
    if not path:
        return None if as_json else ""
    try:
        text = Path(path).read_text("utf-8")
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
    ap.add_argument("--components", required=True)
    ap.add_argument("--report-md")
    ap.add_argument("--status")
    ap.add_argument("--autofix")
    ap.add_argument("--licences")
    ap.add_argument("--lists")
    ap.add_argument("--engine", default="")
    ap.add_argument("--pushed", action="store_true")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    body = compose(_read(a.components) or {}, _read(a.report_md, False), _read(a.status), _read(a.autofix, False),
                   _read(a.licences, False), _read(a.lists), a.engine, a.pushed)
    Path(a.out).write_text(body, "utf-8")
    print(body, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
