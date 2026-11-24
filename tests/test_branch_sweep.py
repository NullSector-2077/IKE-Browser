"""The cleanup of the branches (tools/branch-sweep.py, branch-sweep.yml; tools/automerge.py delete_head).

GitHub's "delete head branches" does not fire for a merge made by github-actions[bot]. The proofs, all
offline with a fake GitHub (and a real git with a local repository for the compare-and-swap):

- after its own verified merge tools/automerge.py deletes the head branch it merged, only an isolated
  candidate (automation/update/<id>, automation/builder/<id>) of this repository and only while its tip
  is the merged commit (a compare-and-swap push); automation/autofix-main, automation/daily-maintenance,
  automat/memory, a drill's branch and anything else stay; nothing there can stop the steps after the merge;
- the weekly sweep deletes only a branch with a pull request merged into the default branch at exactly its
  tip, fully contained in main, with no open pull request of it or based on it, older than seven days and
  not protected (one list); release/* the same way, once merged; a branch with commits not in main is
  never deleted; a branch that moved is never deleted (the push's lease); every deletion is in the summary;
- the workflows hold only the permissions this needs.
"""

import datetime as dt
import importlib.util
import re
import subprocess
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
    """A repository's branches, open and merged pull requests, what is in main, and the commits' dates (GET);
    the deletions go through push(), a compare-and-swap like git's lease."""

    def __init__(self, branches, in_main=(), open_prs=(), merged=None, dates=None, ghprotected=(), ahead=None):
        self.branches = dict(branches)              # name -> sha
        self.in_main = set(in_main)                 # shas contained in main
        self.open_prs = list(open_prs)              # (head ref, base ref, head repo)
        self.merged = dict(merged or {})            # ref -> [(head sha, base ref)] of its merged pull requests
        self.dates = dates or {}
        self.ghprotected = set(ghprotected)
        self.ahead = dict(ahead or {})              # sha -> what compare says of ahead_by
        self.deleted, self.calls = [], []

    def __call__(self, path):
        self.calls.append(path)
        if path == "repos/o/r":
            return {"default_branch": "main"}
        if path.startswith("repos/o/r/pulls?state=open"):
            return [{"head": {"ref": h, "repo": {"full_name": r}}, "base": {"ref": b}} for h, b, r in self.open_prs]
        m = re.match(r"repos/o/r/pulls\?state=closed&head=o:([^&]+)&base=main&", path)
        if m:
            return [{"merged_at": "2026-11-01T00:00:00Z", "head": {"ref": m.group(1), "sha": s}, "base": {"ref": b}}
                    for s, b in self.merged.get(m.group(1), [])] + [{"merged_at": None, "head": {"ref": m.group(1)}}]
        if path.startswith("repos/o/r/branches?"):
            page = int(re.search(r"&page=(\d+)", path).group(1))
            rows = [{"name": n, "commit": {"sha": s}, "protected": n in self.ghprotected}
                    for n, s in sorted(self.branches.items())]
            return rows[(page - 1) * 100:page * 100]
        m = re.fullmatch(r"repos/o/r/compare/main\.\.\.([0-9a-f]{40})", path)
        if m:
            if m.group(1) in self.ahead:
                return {"ahead_by": self.ahead[m.group(1)], "status": "behind"}
            inside = m.group(1) in self.in_main
            return {"ahead_by": 0 if inside else 3, "status": "behind" if inside else "diverged"}
        m = re.fullmatch(r"repos/o/r/commits/([0-9a-f]{40})", path)
        if m:
            return {"commit": {"committer": {"date": self.dates.get(m.group(1), "2026-11-01T00:00:00Z")}}}
        raise AssertionError("unexpected call: %s" % path)

    def push(self, repo, ref, expected):
        """git push --force-with-lease=refs/heads/<ref>:<expected> origin :refs/heads/<ref>"""
        if self.branches.get(ref) != expected:
            raise RuntimeError("stale info")
        self.deleted.append(ref)
        del self.branches[ref]


def merged_at_tip(branches, *names):
    return {n: [(branches[n], "main")] for n in names}


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


def test_the_protected_command_agrees_with_the_sweep():
    # release/* is not protected by name: like every branch it goes only once its pull request is merged
    for ref in ("release/1.1.24", "claude/x", "automation/update/adblock"):
        assert sweep_tool.main(["protected", ref]) == 1 and not sweep_tool.protected(ref)


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
    ("automation/update/../main", False), ("automation/update/a b", False), ("automation/update/x.lock", False),
])
def test_after_its_merge_only_an_isolated_candidate_goes(ref, after_merge):
    assert sweep_tool.deletable_after_merge(ref) is after_merge


# =====================================================================================================
# 2. After the verified merge: a compare-and-swap
# =====================================================================================================

def test_the_verified_merge_deletes_the_head_branch_it_merged_and_only_that():
    gh = FakeGitHub({"automation/update/adblock": sha(1)})
    assert sweep_tool.delete_after_merge(REPO, "automation/update/adblock", sha(1), gh.push) == ""
    assert gh.deleted == ["automation/update/adblock"]
    # moved after the merge: the lease refuses, its new commits stay
    gh = FakeGitHub({"automation/update/adblock": sha(2)})
    assert "stale info" in sweep_tool.delete_after_merge(REPO, "automation/update/adblock", sha(1), gh.push)
    assert gh.deleted == []
    for ref in ("automation/autofix-main", "automation/daily-maintenance", "automat/memory", "automation/update/drill-qt"):
        gh = FakeGitHub({ref: sha(1)})
        assert sweep_tool.delete_after_merge(REPO, ref, sha(1), gh.push).startswith("kept") and gh.deleted == [], ref


def git(*args, cwd=None):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


def test_the_deletion_is_a_real_compare_and_swap_with_git(tmp_path):
    """git push --force-with-lease against a real (local) repository: the branch goes only while it points at
    the expected commit; the token never appears on the command line."""
    remote = tmp_path / "remote.git"
    work = tmp_path / "work"
    git("init", "-q", "--bare", str(remote))
    git("init", "-q", str(work))
    git("-c", "user.name=t", "-c", "user.email=t@e", "commit", "-q", "--allow-empty", "-m", "one", cwd=work)
    first = git("rev-parse", "HEAD", cwd=work)
    git("push", "-q", str(remote), "HEAD:refs/heads/automation/update/x", "HEAD:refs/heads/automation/update/y",
        cwd=work)
    git("-c", "user.name=t", "-c", "user.email=t@e", "commit", "-q", "--allow-empty", "-m", "two", cwd=work)
    git("push", "-q", str(remote), "HEAD:refs/heads/automation/update/y", cwd=work)       # y moved on
    seen = []

    def run(cmd, **kw):
        seen.append((cmd, kw.get("env", {}).get("GIT_CONFIG_VALUE_0", "")))
        return subprocess.run(cmd, **kw)
    sweep_tool.git_delete(REPO, "automation/update/x", first, token="t0ken", remote=str(remote), run=run)
    assert "automation/update/x" not in git("branch", "--list", cwd=remote)
    with pytest.raises(RuntimeError) as e:
        sweep_tool.git_delete(REPO, "automation/update/y", first, token="t0ken", remote=str(remote), run=run)
    assert "t0ken" not in str(e.value)
    assert "automation/update/y" in git("branch", "--list", cwd=remote)                   # moved: it stays
    assert all("t0ken" not in " ".join(cmd) for cmd, _env in seen)                       # never on the command line
    assert any(env.startswith("AUTHORIZATION: basic ") for _cmd, env in seen)
    push = next(cmd for cmd, _env in seen if "push" in cmd)
    assert "--force-with-lease=refs/heads/automation/update/x:%s" % first in push and ":refs/heads/automation/update/x" in push
    for bad in ("main", "automat/memory"):
        with pytest.raises(RuntimeError):
            sweep_tool.git_delete(REPO, bad, first, token="t", remote=str(remote), run=run)
    with pytest.raises(RuntimeError):
        sweep_tool.git_delete(REPO, "automation/update/z", "not-a-sha", token="t", remote=str(remote), run=run)


def pr(ref, repo=REPO):
    return {"number": 41, "title": "update", "draft": False, "head": {"ref": ref, "repo": {"full_name": repo}}}


def test_merge_it_deletes_the_branch_as_its_last_step_and_never_fails_for_it(monkeypatch):
    calls = []
    monkeypatch.setattr(merge, "gh", lambda *a, data=None: calls.append(a) or "")
    monkeypatch.setattr(merge, "api", lambda path: [])
    monkeypatch.setattr(merge, "delete_head", lambda repo, p, s: calls.append(("delete_head", p["head"]["ref"], s)))
    merge.merge_it(REPO, pr("automation/update/adblock"), "a" * 40)
    assert calls[-1] == ("delete_head", "automation/update/adblock", "a" * 40)
    assert any("repos/o/r/pulls/41/merge" in " ".join(c) for c in calls[:-1])


def test_delete_head_deletes_only_this_repositorys_candidates_and_swallows_every_error():
    gh = FakeGitHub({"automation/update/adblock": "a" * 40, "automation/autofix-main": "a" * 40})
    assert merge.delete_head(REPO, pr("automation/update/adblock"), "a" * 40, gh.push) == ""
    assert gh.deleted == ["automation/update/adblock"]
    assert merge.delete_head(REPO, pr("automation/autofix-main"), "a" * 40, gh.push).startswith("kept")
    assert merge.delete_head(REPO, pr("automation/update/adblock", "fork/r"), "a" * 40, gh.push).startswith("kept")
    assert merge.delete_head("O/R", pr("automation/update/x", "o/r"), "a" * 40, gh.push).startswith("kept")

    def explode(*a):
        raise ValueError("anything at all")
    assert "anything at all" in merge.delete_head(REPO, pr("automation/update/adblock"), "a" * 40, explode)
    assert "kept" in merge.delete_head(REPO, {"head": None}, "a" * 40, explode)


def test_every_merge_of_the_automation_ends_its_row_and_the_merge_keeps_its_one_merge_call():
    text = (ROOT / "tools/automerge.py").read_text("utf-8")
    assert text.count('/merge"') == 1 and text.count("merge_it(") == 2
    body = text.split("def merge_it(", 1)[1].split("\ndef ", 1)[0]
    assert body.rstrip().endswith("delete_head(repo, pr, sha)")
    assert "except Exception as e:" in text.split("def delete_head(", 1)[1].split("\ndef ", 1)[0]
    wf = (WORKFLOWS / "automerge.yml").read_text("utf-8")
    assert "contents: write" in wf and "its head branch deleted after the merge" in wf


# =====================================================================================================
# 3. The weekly sweep
# =====================================================================================================

def world():
    old, new = "2026-11-10T00:00:00Z", "2026-11-27T00:00:00Z"
    branches = {
        "main": sha(1), "automat/memory": sha(2), "automation/autofix-main": sha(3), "windows/port": sha(4),
        "claude/old-merged": sha(10),                 # merged at its tip, fully in main, old: goes
        "automation/update/adblock": sha(11),         # the same (the merge's own deletion failed): goes
        "claude/fresh-merged": sha(12),               # merged but newer than seven days: stays
        "claude/unmerged": sha(13),                   # commits not in main: stays, whatever its age
        "claude/open-pr": sha(14),                    # an open pull request: stays
        "release/1.1.23": sha(15),                    # its pull request merged: goes
        "release/1.1.24": sha(16),                    # its pull request not merged yet: stays
        "automation/update/drill-qt": sha(17),        # a drill's record: not in main, stays
        "automation/daily-maintenance": sha(18),      # protected even when fully in main
        "ruled": sha(19),                             # protected by GitHub's own rules
        "weird name": sha(20),
        "claude/in-main-no-pr": sha(21),              # fully in main, but no pull request was merged: stays
        "claude/merged-elsewhere": sha(22),           # merged into another branch, not main: stays
        "claude/moved-after-merge": sha(23),          # merged at an older commit: stays
        "claude/base-of-open": sha(24),               # merged, but an open pull request is based on it: stays
        "claude/fork-head": sha(25),                  # an open pull request from a fork has this name: stays
    }
    in_main = {sha(n) for n in (1, 2, 3, 4, 10, 11, 12, 14, 15, 16, 18, 19, 20, 21, 22, 23, 24, 25)}
    dates = {s: old for s in branches.values()}
    dates[sha(12)] = new
    merged = merged_at_tip(branches, "claude/old-merged", "automation/update/adblock", "claude/fresh-merged",
                           "release/1.1.23", "claude/base-of-open", "claude/fork-head", "claude/unmerged")
    merged["claude/merged-elsewhere"] = [(sha(22), "develop")]
    merged["claude/moved-after-merge"] = [(sha(99), "main")]
    open_prs = [("claude/open-pr", "main", REPO), ("feature/x", "claude/base-of-open", REPO),
                ("claude/fork-head", "main", "Someone/R")]
    return FakeGitHub(branches, in_main=in_main, open_prs=open_prs, merged=merged, dates=dates, ghprotected={"ruled"})


def test_the_sweep_deletes_only_what_was_merged_at_its_tip_is_in_main_old_and_unprotected():
    gh = world()
    result = sweep_tool.sweep(REPO, gh, NOW, push=gh.push)
    assert sorted(gh.deleted) == ["automation/update/adblock", "claude/old-merged", "release/1.1.23"]
    assert sorted(r for r, _s, _w in result["deleted"]) == sorted(gh.deleted)
    kept = result["kept"]
    assert kept["claude/unmerged"] == "3 commit(s) not in main"
    assert kept["automation/update/drill-qt"] == "no pull request merged into main at its tip"
    assert kept["claude/fresh-merged"] == "newer than 7 days"
    assert kept["claude/open-pr"] == "an open pull request"
    assert kept["claude/fork-head"] == "an open pull request"            # whatever repository it comes from
    assert kept["claude/base-of-open"] == "the base of an open pull request"
    assert kept["release/1.1.24"] == "a release branch whose pull request is not merged"
    for name in ("claude/in-main-no-pr", "claude/merged-elsewhere", "claude/moved-after-merge"):
        assert kept[name] == "no pull request merged into main at its tip", name
    for name in ("main", "automat/memory", "automation/autofix-main", "windows/port", "automation/daily-maintenance",
                 "weird name"):
        assert kept[name] == "protected", name
    assert kept["ruled"] == "protected by GitHub's rules"
    # every deletion is in the run's summary
    text = sweep_tool.summary(result)
    for ref in gh.deleted:
        assert "| `%s` |" % ref in text
    assert "Kept:" in text and "some commits not in main" in text


@pytest.mark.parametrize("ahead", [None, "0", 1, True, 0.0])
def test_ahead_by_must_be_the_integer_zero(ahead):
    gh = FakeGitHub({"claude/x": sha(5), "main": sha(1)}, merged={"claude/x": [(sha(5), "main")]},
                    ahead={sha(5): ahead})
    result = sweep_tool.sweep(REPO, gh, NOW, push=gh.push)
    assert gh.deleted == [] and "not in main" in result["kept"]["claude/x"]


def test_a_dry_run_deletes_nothing_and_a_branch_that_moves_stays():
    gh = world()
    result = sweep_tool.sweep(REPO, gh, NOW, dry_run=True, push=gh.push)
    assert gh.deleted == [] and len(result["deleted"]) == 3 and "dry run" in sweep_tool.summary(result, True)
    gh = world()

    def moving(repo, ref, expected):
        if ref == "claude/old-merged":
            gh.branches[ref] = sha(98)                 # someone pushed in between: the lease refuses
        return gh.push(repo, ref, expected)
    result = sweep_tool.sweep(REPO, gh, NOW, push=moving)
    assert "claude/old-merged" not in gh.deleted and "claude/old-merged" in gh.branches
    assert any(e.startswith("claude/old-merged:") for e in result["errors"])


def test_errors_never_stop_the_sweep_and_are_reported():
    gh = world()
    real = gh.__call__

    def api(path):
        if path.endswith("/compare/main...%s" % sha(15)):
            raise RuntimeError("HTTP 500")
        return real(path)

    def push(repo, ref, expected):
        if ref == "claude/old-merged":
            raise RuntimeError("HTTP 422 protected")
        return gh.push(repo, ref, expected)
    result = sweep_tool.sweep(REPO, api, NOW, push=push)
    assert [r for r, _s, _w in result["deleted"]] == ["automation/update/adblock"]
    assert result["kept"]["release/1.1.23"] == "not compared with main"
    assert result["errors"] and "claude/old-merged" in result["errors"][0]


def test_at_most_a_few_deletions_a_run_and_many_branches_are_read_page_by_page():
    branches = {"claude/b%03d" % i: sha(1000 + i) for i in range(sweep_tool.MAX_DELETIONS + 30)}
    gh = FakeGitHub(dict(branches, main=sha(1)), in_main=set(branches.values()) | {sha(1)},
                    merged=merged_at_tip(branches, *branches))
    result = sweep_tool.sweep(REPO, gh, NOW, push=gh.push)
    assert len(gh.deleted) == sweep_tool.MAX_DELETIONS
    assert sum(1 for w in result["kept"].values() if w.startswith("the most of one run")) == 30


def test_the_weekly_workflow_is_small_runs_from_main_and_writes_its_summary():
    wf = (WORKFLOWS / "branch-sweep.yml").read_text("utf-8")
    assert "\n  schedule:\n" in wf and "workflow_dispatch:" in wf and "permissions: {}" in wf
    assert "contents: write" in wf and "pull-requests: read" in wf
    assert not re.search(r"^\s+(actions|issues|checks|statuses|id-token): write", wf, re.M)
    assert "persist-credentials: false" in wf and "github.ref == 'refs/heads/main'" in wf
    assert '--summary "$GITHUB_STEP_SUMMARY"' in wf and "--dry-run" not in wf.split("jobs:", 1)[1]
    assert "secrets." not in wf and "GH_TOKEN: ${{ github.token }}" in wf
    health = (WORKFLOWS / "health.yml").read_text("utf-8")
    assert "grep -q '^  schedule:'" in health                  # kept turned on like every scheduled workflow
    tool = (ROOT / "tools/branch-sweep.py").read_text("utf-8")
    assert '"DELETE"' not in tool and "--force-with-lease=refs/heads/" in tool   # never an unconditional delete


def test_the_documents_say_it():
    doc = (ROOT / "docs/MAINTENANCE.md").read_text("utf-8")
    section = doc.split("### The cleanup of the branches (2026-11-24)", 1)[1].split("\n## ", 1)[0]
    for name in sorted(sweep_tool.PROTECTED):
        assert "`%s`" % name in section, name
    for word in ("delete_head", "branch-sweep.yml", "release/*", "never deleted", "--dry-run", "summary",
                 "--force-with-lease", "merged into", "base of an open"):
        assert word in section, word
    assert "`branch-sweep.yml`" in doc.split("## What runs by itself", 1)[1]
