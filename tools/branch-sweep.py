#!/usr/bin/env python3
"""The cleanup of the branches (no AI here): what was merged goes, nothing else ever does.

GitHub's setting "delete the head branch when a pull request is merged" does not fire for a merge
made by github-actions[bot] (tools/automerge.py's verified merge), so the automation's merged
branches stayed. Two parts, one rule of what is protected, kept here in one place:

- **after the verified merge** (tools/automerge.py, deletable_after_merge): the head branch it just
  merged goes, only an isolated candidate of the full chain (automation/update/<id>,
  automation/builder/<id>; never an AUTOMAT drill's), and only while its tip is still the commit that
  was merged. automation/autofix-main is the automatic fix's long-lived branch and stays, as
  automation/daily-maintenance, automat/memory and everything else;
- **the weekly sweep** (branch-sweep.yml, sweep): a branch goes when its tip is fully contained in
  main (no commit of it is missing from main), no pull request of it is open, its tip is older than
  MIN_AGE_DAYS days, and it is not protected: PROTECTED, a branch GitHub itself protects, the default
  branch, and release/* until its pull request is merged. Each deletion is written to the run's
  summary; right before each one the branch is read again, and a branch that moved stays.

Never a branch with commits that are not in main: such a branch is somebody's work (the archive of
the multiplatform branches, a drill's record, an open candidate), and it stays whatever its age.

    branch-sweep.py sweep --repo OWNER/NAME [--dry-run] [--summary FILE] [--now ISO]
    branch-sweep.py protected REF          (exit 0 when the sweep never deletes it)
"""

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys

# the owner's list (2026-11-24): never deleted, whatever their state. The multiplatform archive
# (windows/port, windows/engine, linux/packages, linux/flatpak, linux/distro-checks, docs/multiplatform-plan,
# automation/audit) is the owner's decision of 2026-11-20 (CLAUDE.md)
PROTECTED = frozenset((
    "main", "automat/memory", "automation/autofix-main", "automation/daily-maintenance", "automation/audit",
    "windows/port", "windows/engine", "linux/packages", "linux/flatpak", "linux/distro-checks",
    "docs/multiplatform-plan", "experiment/file-workers",
))
RELEASE_PREFIX = "release/"          # protected until its pull request is merged
# after the verified merge: only the isolated candidates of the full chain
AFTER_MERGE_PREFIXES = ("automation/update/", "automation/builder/")
DRILL_PREFIX = "automation/update/drill-"          # tools/automat-drill.py: a drill's branch is its record
MIN_AGE_DAYS = 7
MAX_DELETIONS = 100                  # one run deletes at most this many (the next week goes on)
NAME = re.compile(r"^[A-Za-z0-9._/-]{1,200}$")
SHA = re.compile(r"^[0-9a-f]{40}$")


def protected(ref):
    """True for a branch the sweep and the merge never delete by name (release/* is decided by its PR)."""
    ref = str(ref or "")
    return ref in PROTECTED or not NAME.match(ref) or ".." in ref or ref.startswith("/") or ref.endswith("/")


def deletable_after_merge(ref):
    """True for the head branch of a verified merge that goes right after it: an isolated candidate of
    the full chain (automation/update/<id>, automation/builder/<id>), never a drill's, never protected."""
    ref = str(ref or "")
    return not protected(ref) and ref.startswith(AFTER_MERGE_PREFIXES) and len(ref.split("/", 2)[-1]) > 0 \
        and not ref.startswith(DRILL_PREFIX) and not ref.startswith(RELEASE_PREFIX)


# --- GitHub -----------------------------------------------------------------------------------------

def gh_api(path, method="GET"):
    out = subprocess.run(["gh", "api", "-X", method, path], capture_output=True, text=True)
    if out.returncode:
        raise RuntimeError("gh api %s %s: %s" % (method, path, out.stderr.strip()[:300]))
    return json.loads(out.stdout) if out.stdout.strip() else {}


def _quote(ref):
    from urllib.parse import quote
    return quote(ref, safe="/")


def tip(repo, ref, api):
    """The commit the branch points at now, or ""."""
    try:
        got = api("repos/%s/git/ref/heads/%s" % (repo, _quote(ref)))
    except RuntimeError:
        return ""
    sha = ((got or {}).get("object") or {}).get("sha") or ""
    return sha if SHA.match(sha) else ""


def delete_ref(repo, ref, api):
    api("repos/%s/git/refs/heads/%s" % (repo, _quote(ref)), "DELETE")


def delete_after_merge(repo, ref, sha, api=gh_api):
    """The verified merge's head branch deleted, when deletable_after_merge says so and its tip is still the
    commit that was merged (a branch that moved keeps its new commits). Returns why it stays, or ""."""
    if not deletable_after_merge(ref):
        return "kept: not an isolated candidate of the full chain"
    now = tip(repo, ref, api)
    if not now:
        return "kept: the branch could not be read (or is already gone)"
    if now != sha:
        return "kept: the branch moved after the merge (%s), its new commits are not in main" % now[:10]
    delete_ref(repo, ref, api)
    return ""


def _pages(repo, path, api, most=20):
    out = []
    for page in range(1, most + 1):
        got = api("repos/%s/%s%sper_page=100&page=%d" % (repo, path, "&" if "?" in path else "?", page)) or []
        out += got
        if len(got) < 100:
            break
    return out


def _age_days(when, now):
    try:
        t = dt.datetime.fromisoformat(str(when).replace("Z", "+00:00"))
    except ValueError:
        return None
    return (now - t).total_seconds() / 86400.0


def judge(repo, branch, api, now, open_heads, default):
    """(delete?, why) for one branch of the repository's list (a dict of GET /branches)."""
    ref = branch.get("name") or ""
    sha = (branch.get("commit") or {}).get("sha") or ""
    if ref == default or protected(ref):
        return False, "protected"
    if branch.get("protected"):
        return False, "protected by GitHub's rules"
    if ref in open_heads:
        return False, "an open pull request"
    if not SHA.match(sha):
        return False, "its commit could not be read"
    if ref.startswith(RELEASE_PREFIX):
        try:
            prs = api("repos/%s/pulls?state=closed&head=%s:%s&per_page=100" % (repo, repo.split("/")[0], _quote(ref)))
        except RuntimeError:
            return False, "release branch: its pull request could not be read"
        if not any(p.get("merged_at") for p in prs or ()):
            return False, "a release branch whose pull request is not merged"
    try:
        cmp = api("repos/%s/compare/%s...%s" % (repo, _quote(default), sha))
    except RuntimeError:
        return False, "not compared with main"
    if int(cmp.get("ahead_by", 1) or 0) != 0 or cmp.get("status") not in ("behind", "identical"):
        return False, "%s commit(s) not in main" % cmp.get("ahead_by", "?")
    try:
        commit = api("repos/%s/commits/%s" % (repo, sha))
    except RuntimeError:
        return False, "its commit's date could not be read"
    age = _age_days(((commit.get("commit") or {}).get("committer") or {}).get("date"), now)
    if age is None or age < MIN_AGE_DAYS:
        return False, "newer than %d days" % MIN_AGE_DAYS
    return True, "fully in main, no open pull request, %d days old" % int(age)


def sweep(repo, api=gh_api, now=None, dry_run=False):
    """The weekly sweep: {"deleted": [(ref, sha, why)], "kept": {ref: why}, "errors": [...]}."""
    now = now or dt.datetime.now(dt.timezone.utc)
    info = api("repos/%s" % repo) or {}
    default = info.get("default_branch") or "main"
    open_heads = {(p.get("head") or {}).get("ref") for p in _pages(repo, "pulls?state=open", api)
                  if ((p.get("head") or {}).get("repo") or {}).get("full_name") in (None, repo)}
    out = {"deleted": [], "kept": {}, "errors": []}
    for branch in _pages(repo, "branches", api):
        ref = branch.get("name") or ""
        try:
            go, why = judge(repo, branch, api, now, open_heads, default)
        except Exception as e:                       # one branch's error never stops the sweep
            go, why = False, "error: %s" % str(e)[:120]
        if not go:
            out["kept"][ref] = why
            continue
        if len(out["deleted"]) >= MAX_DELETIONS:
            out["kept"][ref] = "the most of one run reached: next week"
            continue
        sha = branch["commit"]["sha"]
        if not dry_run:
            # read again right before: a branch that moved since the list stays
            if tip(repo, ref, api) != sha:
                out["kept"][ref] = "it moved during the sweep"
                continue
            try:
                delete_ref(repo, ref, api)
            except RuntimeError as e:
                out["errors"].append("%s: %s" % (ref, str(e)[:200]))
                continue
        out["deleted"].append((ref, sha, why))
    return out


def summary(result, dry_run=False):
    """The run's summary (Markdown): every deletion, and how many stayed and why."""
    lines = ["## Branch cleanup%s" % (" (dry run: nothing deleted)" if dry_run else ""), ""]
    if result["deleted"]:
        lines += ["| Branch | Commit | Why |", "|---|---|---|"]
        lines += ["| `%s` | `%s` | %s |" % (ref, sha[:10], why) for ref, sha, why in result["deleted"]]
    else:
        lines.append("No branch deleted.")
    reasons = {}
    for why in result["kept"].values():
        key = re.sub(r"^\d+ commit\(s\)", "some commits", why)
        reasons[key] = reasons.get(key, 0) + 1
    if reasons:
        lines += ["", "Kept: " + "; ".join("%d %s" % (n, why) for why, n in sorted(reasons.items()))]
    if result["errors"]:
        lines += ["", "Not deleted (error): " + "; ".join(result["errors"])]
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sweep")
    s.add_argument("--repo", required=True)
    s.add_argument("--dry-run", action="store_true")
    s.add_argument("--summary", default=os.environ.get("GITHUB_STEP_SUMMARY", ""))
    s.add_argument("--now", default="")
    p = sub.add_parser("protected")
    p.add_argument("ref")
    a = ap.parse_args(argv)
    if a.cmd == "protected":
        return 0 if protected(a.ref) or a.ref.startswith(RELEASE_PREFIX) else 1
    now = dt.datetime.fromisoformat(a.now) if a.now else None
    result = sweep(a.repo, gh_api, now, a.dry_run)
    text = summary(result, a.dry_run)
    print(text)
    for ref, sha, _why in result["deleted"]:
        print("%s %s (%s)" % ("would delete" if a.dry_run else "deleted", ref, sha[:10]))
    if a.summary:
        with open(a.summary, "a", encoding="utf-8") as f:
            f.write(text)
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
