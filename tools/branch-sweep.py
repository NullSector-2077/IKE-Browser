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
- **the weekly sweep** (branch-sweep.yml, sweep): a branch goes only when a pull request of it was
  merged into the default branch with exactly its tip (head.ref, head.sha and base all match), its tip
  is fully contained in main (no commit of it is missing from main), no pull request of it is open and
  none has it as its base, its tip is older than MIN_AGE_DAYS days, and it is not protected: PROTECTED,
  a branch GitHub itself protects, the default branch. A release/* branch follows the same rule: kept
  until its pull request into the default branch is merged.

Every deletion is a compare-and-swap (delete_ref): ``git push --force-with-lease=refs/heads/<ref>:<sha>
<repo> :refs/heads/<ref>`` with the job's token, so GitHub deletes the branch only if it still points at
the commit that was judged; a branch that moved in between stays. Each deletion is written to the run's
summary.

Never a branch with commits that are not in main: such a branch is somebody's work (the archive of
the multiplatform branches, a drill's record, an open candidate), and it stays whatever its age.

    branch-sweep.py sweep --repo OWNER/NAME [--dry-run] [--summary FILE] [--now ISO]
    branch-sweep.py protected REF          (exit 0 when it is protected by name: never deleted)
"""

import argparse
import base64
import datetime as dt
import json
import os
import re
import subprocess
import sys
import tempfile

# the owner's list (2026-11-24): never deleted, whatever their state. The multiplatform archive
# (windows/port, windows/engine, linux/packages, linux/flatpak, linux/distro-checks, docs/multiplatform-plan,
# automation/audit) is the owner's decision of 2026-11-20 (CLAUDE.md)
PROTECTED = frozenset((
    "main", "automat/memory", "automation/autofix-main", "automation/daily-maintenance", "automation/audit",
    "windows/port", "windows/engine", "linux/packages", "linux/flatpak", "linux/distro-checks",
    "docs/multiplatform-plan", "experiment/file-workers",
))
RELEASE_PREFIX = "release/"          # kept until its pull request into the default branch is merged
# after the verified merge: only the isolated candidates of the full chain
AFTER_MERGE_PREFIXES = ("automation/update/", "automation/builder/")
DRILL_PREFIX = "automation/update/drill-"          # tools/automat-drill.py: a drill's branch is its record
MIN_AGE_DAYS = 7
MAX_DELETIONS = 100                  # one run deletes at most this many (the next week goes on)
NAME = re.compile(r"^[A-Za-z0-9._/-]{1,200}$")
SHA = re.compile(r"^[0-9a-f]{40}$")


def protected(ref):
    """True for a branch never deleted by its name alone (the owner's list, or a name that is not a plain one)."""
    ref = str(ref or "")
    return ref in PROTECTED or not NAME.match(ref) or ".." in ref or ref.startswith("/") or ref.endswith("/") \
        or ref.endswith(".lock") or "//" in ref


def deletable_after_merge(ref):
    """True for the head branch of a verified merge that goes right after it: an isolated candidate of
    the full chain (automation/update/<id>, automation/builder/<id>), never a drill's, never protected."""
    ref = str(ref or "")
    return not protected(ref) and ref.startswith(AFTER_MERGE_PREFIXES) and len(ref.split("/", 2)[-1]) > 0 \
        and not ref.startswith(DRILL_PREFIX) and not ref.startswith(RELEASE_PREFIX)


# --- GitHub -----------------------------------------------------------------------------------------

def gh_api(path):
    out = subprocess.run(["gh", "api", path], capture_output=True, text=True)
    if out.returncode:
        raise RuntimeError("gh api %s: %s" % (path, out.stderr.strip()[:300]))
    return json.loads(out.stdout) if out.stdout.strip() else {}


def _quote(ref):
    from urllib.parse import quote
    return quote(ref, safe="/")


def git_delete(repo, ref, sha, token=None, remote=None, run=subprocess.run):
    """The branch deleted only if it still points at sha (compare-and-swap: --force-with-lease with the expected
    commit). The token goes in the environment (never on the command line); the push runs in an empty
    repository of its own. Raises RuntimeError when GitHub refused (the branch moved, or is gone)."""
    if not SHA.match(str(sha or "")) or protected(ref):
        raise RuntimeError("not deleted: %s" % ref)
    token = os.environ.get("GH_TOKEN", "") if token is None else token
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    if token:
        auth = base64.b64encode(("x-access-token:%s" % token).encode()).decode()
        env.update(GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="http.https://github.com/.extraheader",
                   GIT_CONFIG_VALUE_0="AUTHORIZATION: basic %s" % auth)
    with tempfile.TemporaryDirectory() as tmp:
        run(["git", "init", "-q", tmp], capture_output=True, text=True, env=env)
        out = run(["git", "-C", tmp, "push", "--porcelain", "--force-with-lease=refs/heads/%s:%s" % (ref, sha),
                   remote or "https://github.com/%s" % repo, ":refs/heads/%s" % ref],
                  capture_output=True, text=True, env=env)
    if out.returncode:
        text = ((out.stdout or "") + " " + (out.stderr or "")).replace(token or "\0", "***")
        raise RuntimeError("the branch was not deleted (moved, gone or refused): %s" % " ".join(text.split())[-200:])


def delete_after_merge(repo, ref, sha, push=git_delete):
    """The verified merge's head branch deleted, when deletable_after_merge says so and only while its tip is
    still the commit that was merged (compare-and-swap). Returns why it stays, or ""."""
    if not deletable_after_merge(ref):
        return "kept: not an isolated candidate of the full chain"
    try:
        push(repo, ref, sha)
    except RuntimeError as e:
        return "kept: %s" % str(e)[:200]
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


def merged_pr(repo, api, ref, sha, default):
    """True when a pull request of this branch was merged into the default branch at exactly this commit."""
    prs = api("repos/%s/pulls?state=closed&head=%s:%s&base=%s&per_page=100" % (
        repo, repo.split("/")[0], _quote(ref), _quote(default))) or []
    return any(p.get("merged_at") and (p.get("head") or {}).get("ref") == ref and (p.get("head") or {}).get("sha") == sha
               and (p.get("base") or {}).get("ref") == default for p in prs)


def judge(repo, branch, api, now, open_heads, default, open_bases=()):
    """(delete?, why) for one branch of the repository's list (a dict of GET /branches)."""
    ref = branch.get("name") or ""
    sha = (branch.get("commit") or {}).get("sha") or ""
    if ref == default or protected(ref):
        return False, "protected"
    if branch.get("protected"):
        return False, "protected by GitHub's rules"
    if ref in open_heads:
        return False, "an open pull request"
    if ref in open_bases:
        return False, "the base of an open pull request"
    if not SHA.match(sha):
        return False, "its commit could not be read"
    try:
        if not merged_pr(repo, api, ref, sha, default):
            return False, ("a release branch whose pull request is not merged" if ref.startswith(RELEASE_PREFIX)
                           else "no pull request merged into %s at its tip" % default)
    except RuntimeError:
        return False, "its pull requests could not be read"
    try:
        cmp = api("repos/%s/compare/%s...%s" % (repo, _quote(default), sha))
    except RuntimeError:
        return False, "not compared with main"
    ahead = (cmp or {}).get("ahead_by")
    if not isinstance(ahead, int) or isinstance(ahead, bool) or ahead != 0 or \
            cmp.get("status") not in ("behind", "identical"):
        return False, "%s commit(s) not in main" % (ahead if isinstance(ahead, int) else "unknown")
    try:
        commit = api("repos/%s/commits/%s" % (repo, sha))
    except RuntimeError:
        return False, "its commit's date could not be read"
    age = _age_days(((commit.get("commit") or {}).get("committer") or {}).get("date"), now)
    if age is None or age < MIN_AGE_DAYS:
        return False, "newer than %d days" % MIN_AGE_DAYS
    return True, "merged into %s, fully in it, no open pull request, %d days old" % (default, int(age))


def sweep(repo, api=gh_api, now=None, dry_run=False, push=git_delete):
    """The weekly sweep: {"deleted": [(ref, sha, why)], "kept": {ref: why}, "errors": [...]}."""
    now = now or dt.datetime.now(dt.timezone.utc)
    info = api("repos/%s" % repo) or {}
    default = info.get("default_branch") or "main"
    opened = _pages(repo, "pulls?state=open", api)
    # every open pull request's branch stays, whatever repository it comes from, and every branch one is based on
    open_heads = {(p.get("head") or {}).get("ref") for p in opened}
    open_bases = {(p.get("base") or {}).get("ref") for p in opened}
    out = {"deleted": [], "kept": {}, "errors": []}
    for branch in _pages(repo, "branches", api):
        ref = branch.get("name") or ""
        try:
            go, why = judge(repo, branch, api, now, open_heads, default, open_bases)
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
            try:
                push(repo, ref, sha)                  # compare-and-swap: only if it still points at sha
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
        key = re.sub(r"^\S+ commit\(s\)", "some commits", why)
        reasons[key] = reasons.get(key, 0) + 1
    if reasons:
        lines += ["", "Kept: " + "; ".join("%d %s" % (n, why) for why, n in sorted(reasons.items()))]
    if result["errors"]:
        lines += ["", "Not deleted (refused or moved): " + "; ".join(result["errors"])]
    return "\n".join(lines) + "\n"


def notices(result):
    """The lines GitHub shows on the run's page (::warning) for what went wrong in a sweep that ran: the branches
    not deleted because GitHub refused, and those not judged because of an error."""
    out = []
    if result["errors"]:
        out.append("::warning title=Branch cleanup::%d branch(es) not deleted (refused or moved): %s" % (
            len(result["errors"]), "; ".join(result["errors"])[:900]))
    failed = sorted(ref for ref, why in result["kept"].items() if str(why).startswith("error:"))
    if failed:
        out.append("::warning title=Branch cleanup::%d branch(es) not judged because of an error: %s" % (
            len(failed), ", ".join(failed)[:900]))
    return out


def main(argv=None, api=gh_api):
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
        # the same rule as judge(): by name only; release/* and everything else go only once merged
        if protected(a.ref):
            print("protected: never deleted")
            return 0
        print("not protected by name: deleted only once its pull request into the default branch is merged at its "
              "tip, it is fully in main, nothing open uses it and it is %d days old" % MIN_AGE_DAYS)
        return 1
    now = dt.datetime.fromisoformat(a.now) if a.now else None
    try:
        result = sweep(a.repo, api, now, a.dry_run)
    except Exception as e:                           # the list of branches or pull requests could not be read
        line = "the weekly cleanup of the branches could not run: %s" % " ".join(str(e).split())[:300]
        print("::error title=Branch cleanup::%s" % line)
        if a.summary:
            with open(a.summary, "a", encoding="utf-8") as f:
                f.write("## Branch cleanup\n\nNot run: %s\n" % line)
        return 1
    text = summary(result, a.dry_run)
    print(text)
    for line in notices(result):
        print(line)
    for ref, sha, _why in result["deleted"]:
        print("%s %s (%s)" % ("would delete" if a.dry_run else "deleted", ref, sha[:10]))
    if a.summary:
        with open(a.summary, "a", encoding="utf-8") as f:
            f.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
