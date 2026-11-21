#!/usr/bin/env python3
"""Merge a green fix into main by itself (1.1.19, the owner's decision; no AI here).

Called by .github/workflows/automerge.yml when a check of a pull request ends,
from main's own copy of this file (a pull request cannot change the rules it
is judged by). A pull request is merged only when ALL of this holds:

- it comes from the automatic fix (branch automation/autofix-main) or from
  ChatGPT (chatgpt/...), in this repository, into main;
- no commit of it is an autofix trial ("Autofix trial" at the start of its
  message: deliberate errors are never merged);
- it changes no test (tests/), no file a fix may never change
  (tools/check-autofix-patch.py's lists), no workflow, the ad blocker or the
  package; the version files only as the automatic fix raises the version
  (ike/__init__.py: __version__; PKGBUILD: pkgver, pkgrel; README.md: the
  version and the package name; CHANGELOG.md);
- every check of its last commit has ended, none failed, and "tests" passed
  (and "guard" for ChatGPT);
- its last commit is still the one checked (the merge names it).

Anything else waits for a person, as before. After a merge it starts the
tests of main (a merge made by a workflow starts no workflow by itself), and
then the mail "release ready" can come (release-ready.yml).

    automerge.py --repo OWNER/NAME --sha HEAD_SHA [--dry-run]
"""

import argparse
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TRIAL = "Autofix trial"
BAD_CONCLUSIONS = {"failure", "cancelled", "timed_out", "startup_failure", "stale"}
VERSION_LINES = {
    "ike/__init__.py": re.compile(r'^__version__ = "\d+\.\d+\.\d+"$'),
    "PKGBUILD": re.compile(r"^pkg(ver|rel)=[\w.]+$"),
    "README.md": re.compile(r"\*\*Version \d+\.\d+\.\d+\*\*|ike-browser-\d+\.\d+\.\d+-\d+-x86_64\.pkg\.tar\.zst"),
}
NEVER_PREFIXES = (".github/", "tests/", "ike-adblock/", "vendor/", "tools/build-")
NEVER_FILES = {"PKGBUILD.in", "ike/blocker.py", "ike/scriptlets.py"}


def _guard():
    spec = importlib.util.spec_from_file_location("guard", ROOT / "tools" / "check-autofix-patch.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def changed_lines(patch):
    """The added and removed lines of a unified diff, without the +/-."""
    out = []
    for line in (patch or "").splitlines():
        if line.startswith(("+++", "---", "@@")):
            continue
        if line.startswith(("+", "-")):
            out.append(line[1:])
    return out


def file_problem(f, forbidden, forbidden_prefixes):
    """Why this changed file keeps the pull request for a person, or ""."""
    name = f.get("filename", "")
    if f.get("status") in ("removed", "renamed") or f.get("previous_filename"):
        return "%s: removed or renamed" % name
    if name == "CHANGELOG.md":
        return ""
    if name in VERSION_LINES:
        if f.get("patch") is None:
            return "%s: change not readable" % name
        rule = VERSION_LINES[name]
        bad = [line for line in changed_lines(f["patch"]) if line.strip() and not rule.search(line)]
        return "%s: more than the version" % name if bad else ""
    if name.startswith(NEVER_PREFIXES) or name.startswith(forbidden_prefixes):
        return "%s: tests, workflows, ad blocker or builders" % name
    if name in forbidden or name in NEVER_FILES:
        return "%s: a file a fix may never change" % name
    if not name.startswith(("ike/", "tools/", "docs/")):
        return "%s: outside ike/, tools/ and docs/" % name
    return ""


def decide(repo, pr, commits, files, checks, forbidden, forbidden_prefixes):
    """(True, "") to merge, or (False, why)."""
    head = pr.get("head") or {}
    ref = head.get("ref", "")
    if pr.get("state") != "open" or (pr.get("base") or {}).get("ref") != "main":
        return False, "not an open pull request into main"
    if (head.get("repo") or {}).get("full_name") != repo:
        return False, "not a branch of this repository"
    chatgpt = ref.startswith("chatgpt/")
    if ref != "automation/autofix-main" and not chatgpt:
        return False, "not a fix of the automation or of ChatGPT"
    if any(((c.get("commit") or {}).get("message") or "").startswith(TRIAL) for c in commits):
        return False, "an autofix trial (deliberate errors)"
    if not files or len(files) >= 100:
        return False, "no files, or too many to read"
    for f in files:
        why = file_problem(f, forbidden, forbidden_prefixes)
        if why:
            return False, why
    names = {}
    for c in checks:
        if c.get("status") != "completed":
            return False, "a check is still running: %s" % c.get("name")
        if c.get("conclusion") in BAD_CONCLUSIONS:
            return False, "the check %s did not pass" % c.get("name")
        names[c.get("name")] = c.get("conclusion")
    need = ["tests"] + (["guard"] if chatgpt else [])
    for n in need:
        if names.get(n) != "success":
            return False, "the check %s has not passed" % n
    return True, ""


def gh(*args, data=None):
    out = subprocess.run(["gh", *args], capture_output=True, text=True, input=data)
    if out.returncode:
        raise RuntimeError("gh %s: %s" % (" ".join(args[:3]), out.stderr.strip()[:300]))
    return out.stdout


def api(path):
    return json.loads(gh("api", path))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--repo", required=True)
    ap.add_argument("--sha", required=True)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    if not re.fullmatch(r"[0-9a-f]{40}", a.sha):
        print("not a commit: %s" % a.sha[:60])
        return 0
    prs = [p for p in api("repos/%s/pulls?state=open&per_page=100" % a.repo) if (p.get("head") or {}).get("sha") == a.sha]
    if not prs:
        print("no open pull request has this commit as its last one")
        return 0
    pr = prs[0]
    n = pr["number"]
    commits = api("repos/%s/pulls/%d/commits?per_page=100" % (a.repo, n))
    files = api("repos/%s/pulls/%d/files?per_page=100" % (a.repo, n))
    checks = api("repos/%s/commits/%s/check-runs?per_page=100" % (a.repo, a.sha)).get("check_runs", [])
    checks = [c for c in checks if c.get("name") != "merge"]          # this workflow's own job
    guard = _guard()
    ok, why = decide(a.repo, pr, commits, files, checks, set(guard.FORBIDDEN_FILES),
                     tuple(guard.FORBIDDEN_PREFIXES))
    print("#%d (%s): %s" % (n, pr["head"]["ref"], "merge" if ok else "left for a person: " + why))
    if not ok or a.dry_run:
        return 0
    if pr.get("draft"):
        gh("pr", "ready", str(n), "--repo", a.repo)
    gh("api", "-X", "PUT", "repos/%s/pulls/%d/merge" % (a.repo, n), "-f", "merge_method=merge", "-f", "sha=" + a.sha,
       "-f", "commit_title=Merge pull request #%d: %s (merged by itself: green, no test or protected file)"
       % (n, pr.get("title", "")[:120]))
    gh("pr", "comment", str(n), "--repo", a.repo, "--body",
       "Unita in `main` da sola: tutti i controlli verdi, nessun test e nessun file protetto toccati "
       "(tools/automerge.py). I test di `main` ripartono ora.")
    gh("workflow", "run", "tests.yml", "--repo", a.repo, "--ref", "main")
    print("merged #%d; the tests of main started" % n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
