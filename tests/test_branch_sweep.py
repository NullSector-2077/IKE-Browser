"""The cleanup of the branches (tools/branch-sweep.py, branch-sweep.yml; tools/automerge.py delete_head).

GitHub's "delete head branches" does not fire for a merge made by github-actions[bot]. The proofs, all
offline with a fake GitHub:

- after its own verified merge tools/automerge.py deletes the head branch it merged, only an isolated
  candidate (automation/update/<id>, automation/builder/<id>) and only while its tip is the merged
  commit; automation/autofix-main, automation/daily-maintenance, automat/memory, a drill's branch and
  anything else stay;
- the weekly sweep deletes only a branch fully contained in main, with no open pull request, older than
  seven days, not protected (one list), release/* only once its pull request is merged; a branch with
  commits not in main is never deleted; a branch that moved during the sweep stays; every deletion is in
  the run's summary;
- the workflows hold only the permissions this needs.
"""

import datetime as dt
import importlib.util
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"
REPO = "o/r"
NOW = dt.datetime(2026, 11, 29, 3, 17, tzinfo=dt.timezone.utc)


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_") + "_sweep", ROOT / "tools" / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


sweep_tool = load("branch-sweep")
merge = load("automerge")


def sha(n):
    return ("%040x" % n)


class FakeGitHub:
    """A repository's branches, open and merged pull requests, what is in main, and the commits' dates."""

    def __init__(self, branches, in_main=(), open_heads=(), merged_heads=(), dates=None, moved=None, ghprotected=()):
        self.branches = dict(branches)              # name -> sha
        self.in_main = set(in_main)                 # shas contained in main
        self.open_heads = set(open_heads)
        self.merged_heads = set(merged_heads)
        self.dates = dates or {}
        self.moved = dict(moved or {})              # name -> sha it points at when read again
        self.ghprotected = set(ghprotected)
        self.deleted, self.calls = [], []

    def __call__(self, path, method="GET"):
        self.calls.append((method, path))
        if method == "DELETE":
            m = re.fullmatch(r"repos/o/r/git/refs/heads/(.+)", path)
            assert m, path
            self.deleted.append(m.group(1))
            self.branches.pop(m.group(1), None)
            return {}
        if path == "repos/o/r":
            return {"default_branch": "main"}
        if path.startswith("repos/o/r/pulls?state=open"):
            return [{"head": {"ref": h, "repo": {"full_name": REPO}}} for h in sorted(self.open_heads)]
        m = re.match(r"repos/o/r/pulls\?state=closed&head=o:([^&]+)&", path)
        if m:
            return [{"merged_at": "2026-11-01T00:00:00Z"}] if m.group(1) in self.merged_heads else \
                [{"merged_at": None}]
        if path.startswith("repos/o/r/branches?"):
            page = int(re.search(r"&page=(\d+)", path).group(1))
            rows = [{"name": n, "commit": {"sha": s}, "protected": n in self.ghprotected}
                    for n, s in sorted(self.branches.items())]
            return rows[(page - 1) * 100:page * 100]
        m = re.fullmatch(r"repos/o/r/compare/main\.\.\.([0-9a-f]{40})", path)
        if m:
            inside = m.group(1) in self.in_main
            return {"ahead_by": 0 if inside else 3, "status": "behind" if inside else "diverged"}
        m = re.fullmatch(r"repos/o/r/commits/([0-9a-f]{40})", path)
        if m:
            return {"commit": {"committer": {"date": self.dates.get(m.group(1), "2026-11-01T00:00:00Z")}}}
        m = re.fullmatch(r"repos/o/r/git/ref/heads/(.+)", path)
        if m:
            name = m.group(1)
            if name not in self.branches:
                raise RuntimeError("HTTP 404")
            return {"object": {"sha": self.moved.get(name, self.branches[name])}}
        raise AssertionError("unexpected call: %s %s" % (method, path))


# =====================================================================================================
# 1. One list of what is protected
# =====================================================================================================

@pytest.mark.parametrize("ref", [
    "main", "automat/memory", "automation/autofix-main", "automation/daily-maintenance", "automation/audit",
    "windows/port", "windows/engine", "linux/packages", "linux/flatpak", "linux/distro-checks",
    "docs/multiplatform-plan", "experiment/file-workers",
])
def test_the_owners_list_is_protected(ref):
    assert sweep_tool.protected(ref) and not sweep_tool.deletable_after_merge(ref)
    assert sweep_tool.main(["protected", ref]) == 0


def test_the_archive_of_claude_md_is_all_in_the_list():
    claude = (ROOT / "CLAUDE.md").read_text("utf-8")
    archive = re.search(r"their branches \(([^)]*)\)", re.sub(r"\s+", " ", claude)).group(1)
    for name in re.findall(r"[a-z]+/[a-z-]+", archive):
        assert name in sweep_tool.PROTECTED, name


@pytest.mark.parametrize("ref, after_merge", [
    ("automation/update/adblock", True), ("automation/update/security-RUSTSEC-2026-0001", True),
    ("automation/update/lists-2026-11-24", True), ("automation/builder/darkreader", True),
    ("automation/update/drill-qt", False),                      # a drill's branch is its record
    ("automation/autofix-main", False), ("automation/daily-maintenance", False), ("automat/memory", False),
    ("automation/update/", False), ("automation/builder/", False), ("automation/audit", False),
    ("chatgpt/fix-1", False), ("claude/x", False), ("release/1.1.24", False), ("main", False),
    ("automation/update/../main", False), ("automation/update/a b", False),
])
def test_after_its_merge_only_an_isolated_candidate_goes(ref, after_merge):
    assert sweep_tool.deletable_after_merge(ref) is after_merge


# =====================================================================================================
# 2. After the verified merge
# =====================================================================================================

def test_the_verified_merge_deletes_the_head_branch_it_merged_and_only_that():
    gh = FakeGitHub({"automation/update/adblock": sha(1)})
    assert sweep_tool.delete_after_merge(REPO, "automation/update/adblock", sha(1), gh) == ""
    assert gh.deleted == ["automation/update/adblock"]
    # moved after the merge: its new commits are not in main, it stays
    gh = FakeGitHub({"automation/update/adblock": sha(1)}, moved={"automation/update/adblock": sha(2)})
    assert "moved after the merge" in sweep_tool.delete_after_merge(REPO, "automation/update/adblock", sha(1), gh)
    assert gh.deleted == []
    # already gone, or never the right kind: nothing is deleted
    assert "could not be read" in sweep_tool.delete_after_merge(REPO, "automation/update/x", sha(1), FakeGitHub({}))
    for ref in ("automation/autofix-main", "automation/daily-maintenance", "automat/memory", "automation/update/drill-qt"):
        gh = FakeGitHub({ref: sha(1)})
        assert sweep_tool.delete_after_merge(REPO, ref, sha(1), gh).startswith("kept") and gh.calls == [], ref


def pr(ref, repo=REPO):
    return {"number": 41, "title": "update", "draft": False, "head": {"ref": ref, "repo": {"full_name": repo}}}


def test_merge_it_deletes_the_branch_after_the_merge_with_the_workflows_token(monkeypatch):
    calls = []
    tips = {"automation/update/adblock": "a" * 40, "automation/autofix-main": "a" * 40}

    def gh(*args, data=None):
        calls.append(args)
        if args[:3] == ("api", "-X", "GET") and "/git/ref/heads/" in args[3]:
            return json.dumps({"object": {"sha": tips[args[3].split("/git/ref/heads/", 1)[1]]}})
        return ""
    monkeypatch.setattr(merge, "gh", gh)
    monkeypatch.setattr(merge, "api", lambda path: [])
    merge.merge_it(REPO, pr("automation/update/adblock"), "a" * 40)
    flat = [" ".join(c) for c in calls]
    merged = next(i for i, c in enumerate(flat) if "repos/o/r/pulls/41/merge" in c)
    deleted = flat.index("api -X DELETE repos/o/r/git/refs/heads/automation/update/adblock")
    assert merged < deleted == len(flat) - 1                     # the last step, after main's checks started
    # the automatic fix's long-lived branch stays: not even read
    calls.clear()
    merge.merge_it(REPO, pr("automation/autofix-main"), "a" * 40)
    assert not any("/git/ref" in " ".join(c) for c in calls)
    # a branch of another repository is never touched
    calls.clear()
    assert merge.delete_head(REPO, pr("automation/update/adblock", "fork/r"), "a" * 40).startswith("kept")
    assert calls == []

    # an error while deleting never undoes or fails the merge: the weekly sweep takes the branch later
    def failing(*args, data=None):
        if "DELETE" in args:
            raise RuntimeError("HTTP 422")
        return gh(*args, data=data)
    monkeypatch.setattr(merge, "gh", failing)
    assert "HTTP 422" in merge.delete_head(REPO, pr("automation/update/adblock"), "a" * 40)


def test_the_merge_keeps_its_one_merge_call_and_its_permissions():
    text = (ROOT / "tools/automerge.py").read_text("utf-8")
    assert text.count('/merge"') == 1 and text.count("merge_it(") == 2
    body = text.split("def merge_it(", 1)[1].split("\ndef ", 1)[0]
    assert body.rstrip().endswith("delete_head(repo, pr, sha)")
    wf = (WORKFLOWS / "automerge.yml").read_text("utf-8")
    assert "contents: write" in wf and "its head branch deleted after the merge" in wf


# =====================================================================================================
# 3. The weekly sweep
# =====================================================================================================

def world():
    old, new = "2026-11-10T00:00:00Z", "2026-11-27T00:00:00Z"
    branches = {
        "main": sha(1), "automat/memory": sha(2), "automation/autofix-main": sha(3), "windows/port": sha(4),
        "claude/old-merged": sha(10),                 # fully in main, old: goes
        "automation/update/adblock": sha(11),         # fully in main, old (the merge's own deletion failed): goes
        "claude/fresh-merged": sha(12),               # fully in main but newer than seven days: stays
        "claude/unmerged": sha(13),                   # commits not in main: stays, whatever its age
        "claude/open-pr": sha(14),                    # an open pull request: stays
        "release/1.1.23": sha(15),                    # its pull request merged: goes
        "release/1.1.24": sha(16),                    # its pull request not merged yet: stays
        "automation/update/drill-qt": sha(17),        # a drill's record: not in main, stays
        "automation/daily-maintenance": sha(18),      # protected even when fully in main
        "ruled": sha(19),                             # protected by GitHub's own rules
        "weird name": sha(20),
    }
    in_main = {sha(n) for n in (1, 2, 3, 4, 10, 11, 12, 14, 15, 16, 18, 19, 20)}
    dates = {s: old for s in branches.values()}
    dates[sha(12)] = new
    return FakeGitHub(branches, in_main=in_main, open_heads={"claude/open-pr"}, merged_heads={"release/1.1.23"},
                      dates=dates, ghprotected={"ruled"})


def test_the_sweep_deletes_only_what_is_fully_in_main_old_and_unprotected():
    gh = world()
    result = sweep_tool.sweep(REPO, gh, NOW)
    assert sorted(gh.deleted) == ["automation/update/adblock", "claude/old-merged", "release/1.1.23"]
    assert sorted(r for r, _s, _w in result["deleted"]) == sorted(gh.deleted)
    kept = result["kept"]
    assert kept["claude/unmerged"] == "3 commit(s) not in main"
    assert kept["automation/update/drill-qt"] == "3 commit(s) not in main"
    assert kept["claude/fresh-merged"] == "newer than 7 days"
    assert kept["claude/open-pr"] == "an open pull request"
    assert kept["release/1.1.24"] == "a release branch whose pull request is not merged"
    for name in ("main", "automat/memory", "automation/autofix-main", "windows/port", "automation/daily-maintenance",
                 "weird name"):
        assert kept[name] == "protected", name
    assert kept["ruled"] == "protected by GitHub's rules"
    # nothing protected or with commits outside main was ever compared for deletion and then deleted
    assert not any(m == "DELETE" and ("main" == p.rsplit("/", 1)[-1] or "memory" in p) for m, p in gh.calls)
    # every deletion is in the run's summary
    text = sweep_tool.summary(result)
    for ref in gh.deleted:
        assert "| `%s` |" % ref in text
    assert "Kept:" in text and "some commits not in main" in text


def test_a_dry_run_deletes_nothing_and_a_branch_that_moves_stays():
    gh = world()
    result = sweep_tool.sweep(REPO, gh, NOW, dry_run=True)
    assert gh.deleted == [] and len(result["deleted"]) == 3 and "dry run" in sweep_tool.summary(result, True)
    gh = world()
    gh.moved["claude/old-merged"] = sha(99)
    result = sweep_tool.sweep(REPO, gh, NOW)
    assert "claude/old-merged" not in gh.deleted and result["kept"]["claude/old-merged"] == "it moved during the sweep"


def test_errors_never_stop_the_sweep_and_are_reported():
    gh = world()
    real = gh.__call__

    def api(path, method="GET"):
        if method == "DELETE" and path.endswith("claude/old-merged"):
            raise RuntimeError("HTTP 422 protected")
        if path.endswith("/compare/main...%s" % sha(15)):
            raise RuntimeError("HTTP 500")
        return real(path, method)
    result = sweep_tool.sweep(REPO, api, NOW)
    assert [r for r, _s, _w in result["deleted"]] == ["automation/update/adblock"]
    assert result["kept"]["release/1.1.23"] == "not compared with main"
    assert result["errors"] and "claude/old-merged" in result["errors"][0]


def test_at_most_a_few_deletions_a_run_and_many_branches_are_read_page_by_page():
    branches = {"claude/b%03d" % i: sha(1000 + i) for i in range(sweep_tool.MAX_DELETIONS + 30)}
    gh = FakeGitHub(dict(branches, main=sha(1)), in_main=set(branches.values()) | {sha(1)})
    result = sweep_tool.sweep(REPO, gh, NOW)
    assert len(gh.deleted) == sweep_tool.MAX_DELETIONS
    assert sum(1 for w in result["kept"].values() if w.startswith("the most of one run")) == 30


def test_the_weekly_workflow_is_small_runs_from_main_and_writes_its_summary():
    wf = (WORKFLOWS / "branch-sweep.yml").read_text("utf-8")
    assert "\n  schedule:\n" in wf and "workflow_dispatch:" in wf and "permissions: {}" in wf
    assert "contents: write" in wf and "pull-requests: read" in wf
    assert not re.search(r"^\s+(actions|issues|checks|statuses|id-token): write", wf, re.M)
    assert "persist-credentials: false" in wf and "github.ref == 'refs/heads/main'" in wf
    assert '--summary "$GITHUB_STEP_SUMMARY"' in wf and "--dry-run" not in wf.split("jobs:", 1)[1]
    assert "secrets." not in wf
    health = (WORKFLOWS / "health.yml").read_text("utf-8")
    assert "grep -q '^  schedule:'" in health                  # kept turned on like every scheduled workflow
