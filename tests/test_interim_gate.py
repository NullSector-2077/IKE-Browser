"""The temporary stricter gate of the fingerprint protection (2026-11-24, approved by the owner).

An independent review showed weakened copies of ike/resources/fingerprint.js that pass both the static
guard (tools/fix-guard.py) and "Nothing gets worse". Until the owner's word removes it, an AI's change of
that file merges by itself only with three independent reviewers and with only "stricter" rows of the
fingerprinting surface in the report of "Nothing gets worse". No person is involved: a change short of it
is refused like any other AI fix and the automatic fix tries again with the reason. Everything else of
AUTOMAT is judged as before. All offline: a fake GitHub, no key.
"""

import copy
import importlib.util
import io
import json
import sys
import zipfile
from pathlib import Path

import pytest
import test_full_auto as fa
import test_merge_and_mail as mm

ROOT = Path(__file__).resolve().parent.parent
FINGERPRINT = "ike/resources/fingerprint.js"
LISTS = "automation/update/lists-2026-11-22"
SHA = fa.SHA


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_") + "_gate", ROOT / "tools" / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


tb = load("tier-b")
nr = load("no-regression")
plan_tool = load("autofix-plan")
merge = mm.merge

NEW_JS = fa.JS.replace("  protect(level());\n", "  function extra(a) {\n    if (a) { return 1; }\n    return 2;\n  }\n"
                       "  protect(level());\n")
THREE = ("Antigravity", "Z.AI", "OpenRouter")          # none of them the author (Groq)


def snap(**obs):
    return {"format": nr.FORMAT, "errors": [], "repo": {"commit": "a" * 40, "version": "1.1.23"},
            "corpus": {"requests": 1, "elements": 1}, "seconds": 1,
            "observations": {k: {"rule": r, "value": v} for k, (r, v) in obs.items()}}


BASE = {"fingerprint/strict/fonts": ("no-new", ["Arial", "DejaVu Sans"]),
        "fingerprint/strict/navigator.hardwareConcurrency": ("exact", 4),
        "fingerprint-config/strict/features": ("switches", ["a"]),
        "requests/balanced/ok-news-image": ("block", "allow"),
        "network/fresh-profile": ("no-new", ["easylist.to"])}


def report(changes=None, allow=()):
    """A real report of tools/no-regression.py compare, main's snapshot against one with these values."""
    base = snap(**BASE)
    cand = copy.deepcopy(base)
    for key, value in (changes or {}).items():
        cand["observations"][key]["value"] = value
    return nr.compare(base, cand, list(allow))


STRICTER = {"fingerprint/strict/fonts": ["Arial"]}                    # a font fewer for a page to read
CHANGED = {"fingerprint-config/strict/features": ["a", "b"]}          # neither weaker nor stricter


def fingerprint_pr(ref=LISTS, new=NEW_JS, also=()):
    pr = dict(mm.pr(ref), head={"ref": ref, "sha": SHA, "repo": {"full_name": mm.REPO}})
    files = [{"filename": FINGERPRINT, "status": "modified", "patch": "@@ -1 +1,5 @@\n a\n+b", "changes": 5,
              "old_source": fa.JS, "new_source": new}] + list(also)
    commits = [dict(fa.commit("Groq"), files=[f["filename"] for f in files])]
    return pr, commits, files


def review(reviewers=THREE, verdict="approve"):
    return {"status": True, "result": dict(fa.review_of(verdict, reviewers=reviewers), files=[FINGERPRINT])}


def evidence(rep):
    out = copy.deepcopy(fa.EVIDENCE)
    if rep is not None:
        out["no_regression_report"] = rep
    return out


def judged(rev, rep, ref=LISTS, **kw):
    pr, commits, files = fingerprint_pr(ref, **kw)
    return merge.judge(mm.REPO, pr, commits, files, mm.FULL_CHECKS, lambda n: fa.guard.allowed_path(n, False),
                       review=rev, evidence=evidence(rep), main_version="1.1.19")


# --- the constant, and the three reviewers it asks for ------------------------------------------------------

def test_the_gate_names_exactly_the_fingerprint_protection_and_asks_three_reviewers():
    assert tb.STRICT_GATE_FILES_INTERIM == ("ike/resources/fingerprint.js",)
    assert (ROOT / FINGERPRINT).is_file() and fa.fg.tier(FINGERPRINT) == "A"
    assert tb.needed_reviews([FINGERPRINT]) == 3 == tb.REVIEWS
    assert tb.needed_reviews(["ike/tabs.py", FINGERPRINT]) == 3
    # every other protected file keeps its two reviewers
    for name in fa.fg.PROTECTED_PY + fa.fg.PROTECTED_JS + fa.fg.PROTECTED_JSON:
        if name != FINGERPRINT:
            assert tb.needed_reviews([name]) == 2, name
    # the request of the review and the merge's count both read it from tools/tier-b.py
    assert '"needed": _tool("tier-b").needed_reviews(files)' in (ROOT / "tools/ai-review.py").read_text("utf-8")
    source = (ROOT / "tools/automerge.py").read_text("utf-8")
    assert 'needed = _tool("tier-b").needed_reviews([f.get("filename", "") for f in mine])' in source
    assert '_tool("tier-b").STRICT_GATE_FILES_INTERIM' in source
    # dated, with the condition of its removal
    text = (ROOT / "tools/tier-b.py").read_text("utf-8")
    block = text.split("STRICT_GATE_FILES_INTERIM = ", 1)[0].rsplit("REVIEWS = 3\n", 1)[1]
    assert "TEMPORARY (2026-11-24" in block and "owner's word" in block and "re-checked" in block


# --- an AI's change of fingerprint.js ----------------------------------------------------------------------

def test_with_three_approvals_and_only_stricter_fingerprint_rows_it_merges():
    rep = report(dict(STRICTER, **{"requests/balanced/ok-news-image": "block"}))
    assert rep["verdict"] == "pass" and rep["stricter"] and not rep["changed"]
    assert merge.strict_gate(rep) == ("passed", "")
    assert judged(review(), rep) == ("merge", "")
    assert judged(review(), report()) == ("merge", "")           # nothing differs: no row at all
    # the automatic fix's own branch too
    pr, commits, files = fingerprint_pr(merge.FIX_MAIN)
    files.append({"filename": "ike/__init__.py", "status": "modified", "patch": "@@ -1 +1 @@\n-x\n+y"})
    assert merge.ai_requirements(pr, commits, files, evidence(rep), review()) == ("merge", "")


def test_with_two_reviewers_it_is_refused_and_the_automatic_fix_tries_again():
    kind, why = judged(review(reviewers=("Z.AI", "OpenRouter")), report(STRICTER))
    assert kind == "person" and "does not count" in why and "fewer than 3" in why, why
    assert merge.next_step(why, LISTS, True) == "fix" and merge.next_step(why, merge.FIX_MAIN, True) == "fix"
    text = merge.person_text(7, why, "owner", SHA, "fix")
    assert "@owner" not in text and merge.NEXT["fix"] in text and merge.VERDICT % (SHA, "retrying") in text


@pytest.mark.parametrize("changes, allow, word", [
    (CHANGED, (), "changed"),
    (dict(STRICTER, **CHANGED), (), "changed"),
    ({"fingerprint/strict/navigator.hardwareConcurrency": 8},
     [{"key": "fingerprint/*/navigator.hardwareConcurrency", "base": 4, "candidate": 8, "why": "x"}], "accepted"),
])
def test_any_fingerprint_row_but_stricter_refuses_it_and_the_fix_tries_again(changes, allow, word):
    rep = report(changes, allow)
    assert rep["verdict"] == "pass"                                  # "Nothing gets worse" alone would let it in
    kind, why = judged(review(), rep)
    assert kind == "person" and why.startswith(merge.STRICT_WHY) and FINGERPRINT in why and word in why, why
    assert merge.next_step(why, LISTS, True) == "fix" and merge.next_step(why, merge.FIX_MAIN, True) == "fix"
    # the reason is fed back to the next attempt (the plan reads it from the one comment)
    note = merge.person_text(7, why, "owner", SHA, "fix")
    assert "@owner" not in note
    assert merge.STRICT_WHY in plan_tool.refusal_notes([{"user": {"login": plan_tool.REPORTER}, "body": note}])
    # the reviewers are not asked for a change the gate refuses
    assert judged(None, rep)[1].startswith(merge.STRICT_WHY)


def test_a_kind_of_row_the_gate_does_not_know_or_a_count_alone_refuses_too():
    rep = report(STRICTER)
    unjudged = dict(rep, unjudged=[{"key": "fingerprint/strict/worker.realm", "section": "fingerprinting",
                                    "detail": "not compared"}])
    assert merge.strict_gate(unjudged)[0] == "refused" and "unjudged" in merge.strict_gate(unjudged)[1]
    counted = copy.deepcopy(rep)
    counted["sections"]["fingerprinting"]["changed"] = 2
    assert merge.strict_gate(counted)[0] == "refused" and "2 fingerprinting rows changed" in merge.strict_gate(counted)[1]
    # a row of another section is not the gate's business
    other = report({"requests/balanced/ok-news-image": "block"})
    assert other["stricter"] and merge.strict_gate(other) == ("passed", "")


def test_a_report_that_cannot_be_read_is_not_verified_and_its_checks_run_again():
    for rep in (None, {}, dict(report(), compared={})):
        kind, why = judged(review(), rep)
        assert kind == "person" and why.startswith(merge.NO_REGRESSION + " not verified"), why
        assert merge.next_step(why, LISTS, True) == "checks"
    failed = dict(report(), verdict="fail", errors=["candidate, fingerprint: no result"])
    assert merge.strict_gate(failed)[0] == "refused"


# --- everything else, unchanged ---------------------------------------------------------------------------

def test_another_protected_file_and_an_update_with_no_ai_are_judged_as_before():
    two = {"status": True, "result": fa.review_of(sha=SHA)}
    # ike/blocker.py by an AI: two reviewers, no report of rows needed
    assert fa.judged(two) == ("merge", "")
    pr, commits, files = fa.lists_pr()
    assert merge.strict_gate_files(LISTS, commits, files) == []
    assert merge.ai_requirements(pr, commits, files, fa.EVIDENCE, two) == ("merge", "")
    # still refused by the guard when it removes logic (fix, as before)
    kind, why = fa.judged(two, new=fa.OLD.replace("    if not url:\n        return False\n", ""))
    assert kind == "person" and why.startswith(merge.GUARD_WHY) and merge.next_step(why, LISTS, True) == "fix"
    # an update with no AI commit: no gate, no review
    assert merge.strict_gate_files(mm.CAND, [mm.MAINT], mm.CAND_FILES) == []
    assert merge.ai_requirements(mm.pr(mm.CAND), [mm.MAINT], mm.CAND_FILES, mm.with_no_regression(mm.VERIFIED),
                                 None) == ("merge", "")
    # fingerprint.js changed by a commit no AI wrote (a person's, an update's) is not under the gate
    pr, commits, files = fingerprint_pr()
    assert merge.strict_gate_files(LISTS, [mm.MAINT], files) == []
    assert merge.strict_gate_files(LISTS, commits, files) == [FINGERPRINT]
    # an AI commit that changed another file of the same pull request: not under the gate either
    other = [dict(commits[0], files=["ike/blocker.py"])]
    assert merge.strict_gate_files(LISTS, other, files) == []


# --- through main(): the report read from the run's artifact, and what follows ------------------------------

def _world(monkeypatch, reviewers, rep):
    sha = "c" * 40
    p = dict(mm.pr(LISTS), head={"ref": LISTS, "sha": sha, "repo": {"full_name": "o/r"}},
             base={"ref": "main", "sha": "b" * 40})
    c = dict(fa.commit("Groq"), files=[FINGERPRINT])
    files = [{"filename": FINGERPRINT, "status": "modified", "patch": "@@ -1 +1,5 @@\n a\n+b", "changes": 5}]
    calls = mm._main_world(monkeypatch, p, [c], files, mm.FULL_CHECKS)
    monkeypatch.setattr(merge, "file_at", lambda repo, name, ref: fa.JS if ref == "b" * 40 else NEW_JS)
    monkeypatch.setattr(merge, "released", lambda *a: False)
    monkeypatch.setattr(merge, "gather_review", lambda repo, n, s: mm.approved(s, reviewers=reviewers))
    asked = []
    monkeypatch.setattr(merge, "gather_no_regression_report", lambda repo, ev: asked.append(ev) or rep)
    monkeypatch.setenv("GITHUB_RUN_ID", "99")
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    assert merge.main(["--repo", "o/r", "--sha", sha]) == 0
    return sha, [" ".join(map(str, x[1:])) for x in calls if x[0] == "gh"], asked


def test_main_merges_it_only_through_the_gate(monkeypatch):
    sha, flat, asked = _world(monkeypatch, THREE, report(STRICTER))
    assert asked and any(c.startswith("api -X PUT repos/o/r/pulls/7/merge") for c in flat), flat
    # two reviewers: not merged, the automatic fix is started with the reason, nobody named
    sha, flat, _ = _world(monkeypatch, ("Z.AI", "OpenRouter"), report(STRICTER))
    assert not any("pulls/7/merge" in c for c in flat)
    assert "workflow run autofix.yml --repo o/r --ref main -f run_id=99 -f work=refused/" + sha in flat
    said = [c for c in flat if c.startswith("pr comment 7")]
    assert len(said) == 1 and "@o" not in said[0] and merge.NEXT_MARK % "fix" in said[0]
    # three reviewers, a changed fingerprint row: the same
    sha, flat, _ = _world(monkeypatch, THREE, report(CHANGED))
    assert not any("pulls/7/merge" in c for c in flat)
    assert "workflow run autofix.yml --repo o/r --ref main -f run_id=99 -f work=refused/" + sha in flat
    assert any(merge.STRICT_WHY in c for c in flat if c.startswith("pr comment 7"))


def test_the_report_is_read_from_the_artifact_of_the_commits_tests_run(monkeypatch):
    rep = report(STRICTER)
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as z:
        z.writestr("collected.txt", "x")
        z.writestr(merge.NR_REPORT, json.dumps(rep))
    asked = []

    class Ledger:
        @staticmethod
        def gh_api(path, raw=False):
            asked.append(path)
            if path == "repos/o/r/actions/runs/41/artifacts?name=tests-checks":
                return {"artifacts": [{"id": 5, "name": "tests-checks", "expired": True},
                                      {"id": 6, "name": "tests-checks", "expired": False}]}
            if path == "repos/o/r/actions/artifacts/6/zip" and raw:
                return data.getvalue()
            raise RuntimeError(path)
    real = merge._tool
    monkeypatch.setattr(merge, "_tool", lambda name: Ledger if name == "maintenance-ledger" else real(name))
    ev = {"runs": {"tests.yml": {"id": 41}}}
    assert merge.gather_no_regression_report("o/r", ev) == json.loads(json.dumps(rep))
    assert asked[-1] == "repos/o/r/actions/artifacts/6/zip"
    assert merge.gather_no_regression_report("o/r", {"runs": {"tests.yml": {"id": 42}}}) is None
    assert merge.gather_no_regression_report("o/r", {"runs": {}}) is None
    # the step's report is in that artifact: tests.yml uploads test-results/ with it
    tests = (ROOT / ".github/workflows/tests.yml").read_text("utf-8")
    assert 'out="$RUNNER_TEMP/test-results/no-regression"' in tests and "name: tests-checks" in tests
