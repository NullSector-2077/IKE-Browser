"""AUTOMAT's weekly scoreboard (tools/automat-scoreboard.py, 2026-11-27): a few numbers, read with GET calls only,
in one issue in Italian. Offline: GitHub's answers stood in."""

import base64
import datetime as dt
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NOW = dt.datetime(2026, 11, 30, 7, 41, tzinfo=dt.timezone.utc)
REPO = "o/r"


def board():
    spec = importlib.util.spec_from_file_location("scoreboard", ROOT / "tools" / "automat-scoreboard.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def fake_api(path):
    if path.startswith("repos/o/r/pulls?state=closed"):
        return [{"number": 5, "title": "Update: crates", "merged_at": "2026-11-28T10:00:00Z", "merge_commit_sha": "a",
                 "head": {"ref": "automation/update/crates"}},
                {"number": 6, "title": "Update: test-qt", "merged_at": "2026-11-29T10:00:00Z", "merge_commit_sha": "b",
                 "head": {"ref": "automation/update/test-qt"}},
                {"number": 7, "title": "AUTOMAT: a fix", "merged_at": "2026-11-29T10:00:00Z", "merge_commit_sha": "c",
                 "head": {"ref": "automat/playbook"}},
                {"number": 8, "title": "Old", "merged_at": "2026-11-01T10:00:00Z", "merge_commit_sha": "d",
                 "head": {"ref": "automation/update/old"}}]
    if path == "repos/o/r/commits/a":
        return {"commit": {"message": "Merge pull request #5 (merged by itself: fully verified)"}}
    if path.startswith("repos/o/r/commits/"):
        return {"commit": {"message": "Merge pull request"}}
    if path.startswith("repos/o/r/pulls?state=open"):
        return [{"number": 9, "title": "Update: darkreader", "created_at": "2026-11-27T07:00:00Z",
                 "head": {"ref": "automation/update/darkreader"}},
                {"number": 130, "title": "DRILL", "created_at": "2026-11-23T07:00:00Z",
                 "head": {"ref": "automation/update/drill-qt"}}]
    if path.startswith("repos/o/r/contents/quota.json"):
        state = {"days": {"2026-11-29": {"runs": 3, "answered": 2, "no_provider": 1,
                                         "providers": {"Groq": {"requests": 4}, "Z.AI": {"requests": 2}}},
                          "2026-11-10": {"runs": 50, "answered": 0, "no_provider": 50, "providers": {}}}}
        return {"content": base64.b64encode(json.dumps(state).encode()).decode()}
    if "/workflows/tests.yml/runs?per_page=100" in path:
        return {"workflow_runs": [{"id": 1, "name": "Tests", "head_branch": "main", "run_attempt": 2,
                                   "conclusion": "success"},
                                  {"id": 2, "name": "Tests", "head_branch": "x", "run_attempt": 1,
                                   "conclusion": "success"}]}
    if "/workflows/arch.yml/runs?per_page=100" in path:
        return {"workflow_runs": []}
    if path == "repos/o/r/actions/runs/1/attempts/1/jobs?per_page=100":
        return {"jobs": [{"name": "tests shard 4/4", "conclusion": "failure"}, {"name": "tests plan",
                                                                               "conclusion": "success"}]}
    if "/workflows/tests.yml/runs?branch=main" in path:
        return {"workflow_runs": [{"name": "Tests", "conclusion": "cancelled"}, {"name": "Tests", "conclusion": "success"}]}
    if "/workflows/arch.yml/runs?branch=main" in path:
        return {"workflow_runs": [{"name": "Arch Linux", "conclusion": "failure"}]}
    raise RuntimeError("unexpected " + path)


def test_the_numbers_of_the_week():
    b = board()
    info = b.gather(REPO, fake_api, NOW)
    assert info["missing"] == []
    assert info["merged"] == [(5, "Update: crates", True), (6, "Update: test-qt", False)]     # not Claude's, not old
    assert info["open"] == [(9, "Update: darkreader", 3)]                                    # the drill left out
    assert info["ai"] == {"runs": 3, "answered": 2, "no_provider": 1, "requests": {"Groq": 4, "Z.AI": 2}}
    assert info["rerun"] == [("Tests", "main", ["tests shard 4/4"])]
    assert info["main"] == {"Tests": "success", "Arch Linux": "failure"}
    body = b.text(info)
    assert "**2, di cui **1 da soli**" in body.replace("** 2", "**2") or "2, di cui **1 da soli**" in body
    assert "ROSSO" in body and "tests shard 4/4" in body and "Groq 4" in body


def test_a_part_not_read_hides_nothing_else():
    b = board()

    def broken(path):
        if "quota.json" in path:
            raise RuntimeError("no memory branch")
        return fake_api(path)
    info = b.gather(REPO, broken, NOW)
    assert info["ai"] is None and info["merged"] and "ai (RuntimeError)" in info["missing"]
    assert "Non letto questa volta" in b.text(info)


def test_the_weekly_check_runs_it_with_a_read_token():
    text = (ROOT / ".github" / "workflows" / "health.yml").read_text("utf-8")
    step = text.split("- name: AUTOMAT's weekly scoreboard", 1)[1].split("- name:", 1)[0]
    assert "tools/automat-scoreboard.py" in step and "secrets." not in step
