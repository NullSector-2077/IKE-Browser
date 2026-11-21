#!/usr/bin/env python3
"""Merge a green fix into main by itself (1.1.19, the owner's decision; no AI here).

Called by .github/workflows/automerge.yml when a check of a pull request ends
(or by a dispatch from the automation's own Tests and Security runs), from
main's own copy of this file: a pull request cannot change the rules it is
judged by. A pull request is merged only when ALL of this holds:

- it comes from the automatic fix (automation/autofix-main, every commit one
  the fix wrote itself) or from ChatGPT (chatgpt/..., no "trial" and no
  maintenance commit), in this repository, into main;
- it changes only existing Python modules of the interface under ike/ (and
  docs/), with no added line that reaches the environment, the network, the
  system or the test run, and the version files exactly as the automation
  raises the version (hunks read by their counts);
- no new or removed file, no module that decides the user's safety
  (PERSON_FILES), no page script, test, tool, workflow, ad blocker or package;
- main's version is not published yet, or the fix raises it; and main holds
  no other fix merged by itself and not yet published;
- every check of its last commit ended, none failed, and "tests" and
  "sandbox" passed (and "guard" for ChatGPT); its last commit is still the
  one checked (the merge names it).

Anything else waits for a person: one comment names the owner (review 2 of
1.1.19, C1: AI-written code otherwise reached a signed release unread). After
a merge it starts the tests and the security tests of main.

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
BAD_CONCLUSIONS = {"failure", "cancelled", "timed_out", "startup_failure", "stale"}
# what the automatic fix writes (autofix.yml); anything else on its branch
# (a trial, by any spelling) is never merged
AUTOFIX_COMMIT = re.compile(r"^autofix: attempt \d+ after a failure of ")
TRIAL = re.compile(r"trial", re.I)
VERSION = re.compile(r"\d+\.\d+\.\d+(?:-\d+)?")
VERSION_LINES = {
    "ike/__init__.py": re.compile(r'^__version__ = "\d+\.\d+\.\d+"$'),
    "PKGBUILD": re.compile(r"^pkg(ver|rel)=[0-9.]+$"),
    # the two lines tools/prepare-maintenance.py writes
    "README.md": re.compile(r"^\*\*Version \d+\.\d+\.\d+\*\* - see \[CHANGELOG\.md\]\(CHANGELOG\.md\)\.$"
                            r"|^[^`]*ike-browser-\d+\.\d+\.\d+-\d+-x86_64\.pkg\.tar\.zst[^`]*$"),
}
NEVER_PREFIXES = (".github/", "tests/", "tools/", "ike-adblock/", "vendor/", "ike/resources/")
NEVER_FILES = {"PKGBUILD.in", "ike/blocker.py", "ike/scriptlets.py"}
# modules where one line decides the user's safety: always read by a person
# (review 2 of 1.1.19, C1; the update channel, the vault, the network checks)
PERSON_FILES = {"ike/__main__.py", "ike/app.py", "ike/config.py", "ike/osinfo.py", "ike/passwords.py",
                "ike/userscripts.py", "ike/extensions.py", "ike/webview.py", "ike/shields.py", "ike/doh.py",
                "ike/updater.py", "ike/sitedata.py", "ike/drm.py", "ike/chromever.py", "ike_boot.py"}
# added lines that can change where updates come from, reach the network or the
# system, or tell a test run from a real one: a person reads them (C1, H4)
PERSON_LINES = re.compile(
    r"\bos\.environ\b|\benviron\b|\bputenv\b|\bgetenv\b|IKE_\w+|update\.json|\bpubkey\b|\bsys\.modules\b"
    r"|__import__|\bimportlib\b|\bsubprocess\b|\bsocket\b|\burllib\b|\bhttp\b|\bexec\s*\(|\beval\s*\("
    r"|\bcompile\s*\(|\bbase64\b|\batexit\b|\bRUNNER_|\bGITHUB_|\bCI\b|\bpytest\b|\bunittest\b"
    r"|\bsys\._getframe\b|\binspect\b|\bgc\.get_|\bsetattr\s*\(|\bglobals\s*\(|\bopen\s*\(|\bos\.system\b"
    r"|\bctypes\b|\bpickle\b|\bmarshal\b|\bsignal\b|\bthreading\b|QProcess|QNetwork|runJavaScript"
    r"|setUrlRequestInterceptor|setFeaturePermission|QWebEngineScript")


def _guard():
    spec = importlib.util.spec_from_file_location("guard", ROOT / "tools" / "check-autofix-patch.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def hunks(patch):
    """[(new_start, removed lines, added lines)] of a file's patch as GitHub
    gives it, read by the counts of each hunk header (a content line "++x"
    is content, not a header: review 2 of 1.1.19, M3). None if unreadable."""
    out, old_left, new_left = [], 0, 0
    for line in (patch or "").split("\n"):
        if old_left > 0 or new_left > 0:
            sign, text = line[:1] or " ", line[1:]
            if sign == "\\":
                continue
            if sign == " ":
                old_left, new_left = old_left - 1, new_left - 1
            elif sign == "-":
                old_left -= 1
                out[-1][1].append(text)
            elif sign == "+":
                new_left -= 1
                out[-1][2].append(text)
            else:
                return None
            continue
        if not line:
            continue
        m = _HUNK.match(line)
        if not m:
            return None
        old_left = int(m.group(2) or 1)
        new_left = int(m.group(4) or 1)
        out.append((int(m.group(3)), [], []))
    if old_left > 0 or new_left > 0:
        return None
    return out


def changed_lines(patch):
    """The added and removed lines of a patch, without the +/- (hunk-accurate)."""
    parts = hunks(patch) or []
    return [line for _, removed, added in parts for line in removed + added]


def version_problem(name, patch, repo):
    """"" when the change only moves the version, as the automatic fix does."""
    parts = hunks(patch)
    if parts is None:
        return "%s: change not readable" % name
    removed = [x for _, r, _a in parts for x in r]
    added = [x for _, _r, a in parts for x in a]
    if name == "CHANGELOG.md":
        # only new lines at the top, linking nowhere but this repository
        links = re.findall(r"https?://[^\s)>\]]+", "\n".join(added))
        if removed or any(start > 12 for start, _r, _a in parts) or any(
                not u.startswith("https://github.com/%s/" % repo) for u in links):
            return "%s: more than a new entry at the top" % name
        return ""
    rule = VERSION_LINES[name]
    if any(not rule.search(x) for x in removed + added if x.strip()):
        return "%s: more than the version" % name
    if sorted(VERSION.sub("V", x) for x in removed) != sorted(VERSION.sub("V", x) for x in added):
        return "%s: more than the version" % name
    return ""


def file_problem(f, guard_allowed, repo=""):
    """Why this changed file keeps the pull request for a person, or ""."""
    name = f.get("filename", "")
    if f.get("status") in ("removed", "renamed", "copied") or f.get("previous_filename"):
        return "%s: removed or renamed" % name
    if f.get("status") == "added":
        return "%s: a new file" % name
    if f.get("patch") is None:
        return "%s: change not readable" % name
    if name == "CHANGELOG.md" or name in VERSION_LINES:
        return version_problem(name, f["patch"], repo)
    if name.startswith(NEVER_PREFIXES) or name in NEVER_FILES:
        return "%s: tests, workflows, tools, page scripts or the ad blocker" % name
    why = guard_allowed(name)
    if why:
        return "%s: %s" % (name, why)
    if not name.startswith(("ike/", "docs/")) or not name.endswith((".py", ".md")):
        return "%s: outside ike/ and docs/" % name
    if name in PERSON_FILES:
        return "%s: a module a person reads before it changes" % name
    parts = hunks(f["patch"])
    if parts is None:
        return "%s: change not readable" % name
    if name.endswith(".py"):
        for _start, _removed, added in parts:
            for line in added:
                if PERSON_LINES.search(line):
                    return "%s: a line a person must read (%s)" % (name, line.strip()[:80])
    return ""


def decide(repo, pr, commits, files, checks, guard_allowed, published=False, unread=False):
    """("merge", ""), ("wait", why) while checks run, or ("person", why)."""
    head = pr.get("head") or {}
    ref = head.get("ref", "")
    if pr.get("state") != "open" or (pr.get("base") or {}).get("ref") != "main":
        return "person", "not an open pull request into main"
    if (head.get("repo") or {}).get("full_name") != repo:
        return "person", "not a branch of this repository"
    chatgpt = ref.startswith("chatgpt/")
    if ref != "automation/autofix-main" and not chatgpt:
        return "person", "not a fix of the automation or of ChatGPT"
    messages = [((c.get("commit") or {}).get("message") or "") for c in commits]
    if not messages:
        return "person", "no commits"
    if ref == "automation/autofix-main" and not all(AUTOFIX_COMMIT.match(m) for m in messages):
        return "person", "a commit the automatic fix did not write (a trial?)"
    if any(TRIAL.search(m.split("\n", 1)[0]) or m.startswith("maintenance:") for m in messages):
        return "person", "a trial or a maintenance candidate"
    if not files or len(files) >= 100:
        return "person", "no files, or too many to read"
    for f in files:
        why = file_problem(f, guard_allowed, repo)
        if why:
            return "person", why
    if published and not any(f.get("filename") == "ike/__init__.py" for f in files):
        # the fix would never reach users: the version must be raised (M5)
        return "person", "main's version is published already: the version must be raised"
    if unread:
        return "person", "main already holds a fix merged by itself and not yet published (M9)"
    names = {}
    for c in checks:
        if c.get("status") != "completed":
            return "wait", "a check is still running: %s" % c.get("name")
        if c.get("conclusion") in BAD_CONCLUSIONS:
            return "person", "the check %s did not pass" % c.get("name")
        names[c.get("name")] = c.get("conclusion")
    need = ["tests", "sandbox"] + (["guard"] if chatgpt else [])
    for n in need:
        if names.get(n) != "success":
            return "wait", "the check %s has not passed yet" % n
    return "merge", ""


def gh(*args, data=None):
    out = subprocess.run(["gh", *args], capture_output=True, text=True, input=data)
    if out.returncode:
        raise RuntimeError("gh %s: %s" % (" ".join(args[:3]), out.stderr.strip()[:300]))
    return out.stdout


def api(path):
    return json.loads(gh("api", path))


def version_of_main():
    m = re.search(r'^__version__ = "([^"]+)"', (ROOT / "ike" / "__init__.py").read_text("utf-8"), re.M)
    return m.group(1) if m else ""


def released(repo, tag):
    try:
        gh("release", "view", tag, "--repo", repo, "--json", "tagName")
        return True
    except RuntimeError:
        return False


def unread_merge(repo):
    """main holds a fix merged by itself since the last published release."""
    try:
        tag = json.loads(gh("release", "view", "--repo", repo, "--json", "tagName"))["tagName"]
        commits = api("repos/%s/compare/%s...main" % (repo, tag)).get("commits", [])
    except (RuntimeError, KeyError, ValueError):
        return True                      # not known: a person decides
    return any("(merged by itself" in ((c.get("commit") or {}).get("message") or "") for c in commits)


MARK = "<!-- automerge: left for a person -->"


def tell_person(repo, n, why, owner):
    """One comment per pull request, naming the owner (a mail with GitHub's
    notification settings of docs/MAINTENANCE.md)."""
    said = gh("api", "repos/%s/issues/%d/comments?per_page=100" % (repo, n), "--jq",
              '[.[] | select(.user.login == "github-actions[bot]") | .body] | join("\\n")')
    if MARK in said:
        return
    gh("pr", "comment", str(n), "--repo", repo, "--body",
       "%s\n@%s: questa correzione **non** entra in `main` da sola: %s.\n\n"
       "Prima di unirla va letta: chiedi a Claude di revisionare la pull request #%d." % (MARK, owner, why, n))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--repo", required=True)
    ap.add_argument("--sha", required=True)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    if not re.fullmatch(r"[0-9a-f]{40}", a.sha):
        print("not a commit: %s" % a.sha[:60])
        return 0
    # the pull request of this repository, on an allowed branch, whose last
    # commit this is (a stranger's pull request on the same commit is not it: L5)
    prs = [p for p in api("repos/%s/pulls?state=open&per_page=100" % a.repo)
           if (p.get("head") or {}).get("sha") == a.sha
           and ((p.get("head") or {}).get("repo") or {}).get("full_name") == a.repo
           and ((p.get("head") or {}).get("ref") == "automation/autofix-main"
                or (p.get("head") or {}).get("ref", "").startswith("chatgpt/"))]
    if not prs:
        print("no pull request of the automation or of ChatGPT has this commit as its last one")
        return 0
    pr = prs[0]
    n = pr["number"]
    commits = api("repos/%s/pulls/%d/commits?per_page=100" % (a.repo, n))
    files = api("repos/%s/pulls/%d/files?per_page=100" % (a.repo, n))
    checks = api("repos/%s/commits/%s/check-runs?per_page=100" % (a.repo, a.sha)).get("check_runs", [])
    checks = [c for c in checks if c.get("name") != "merge"]          # this workflow's own job
    guard = _guard()
    published = released(a.repo, "v" + version_of_main())
    kind, why = decide(a.repo, pr, commits, files, checks, lambda name: guard.allowed_path(name, False),
                       published=published, unread=unread_merge(a.repo))
    print("#%d (%s): %s" % (n, pr["head"]["ref"], {"merge": "merge", "wait": "waiting: ",
                                                   "person": "left for a person: "}[kind] + why))
    if a.dry_run or kind == "wait":
        return 0
    if kind == "person":
        tell_person(a.repo, n, why, a.repo.split("/")[0])
        return 0
    if pr.get("draft"):
        gh("pr", "ready", str(n), "--repo", a.repo)
    gh("api", "-X", "PUT", "repos/%s/pulls/%d/merge" % (a.repo, n), "-f", "merge_method=merge", "-f", "sha=" + a.sha,
       "-f", "commit_title=Merge pull request #%d: %s (merged by itself: green, no test or protected file)"
       % (n, pr.get("title", "")[:120]))
    gh("pr", "comment", str(n), "--repo", a.repo, "--body",
       "Unita in `main` da sola: tutti i controlli verdi, nessun test e nessun file protetto toccati "
       "(tools/automerge.py). I test di `main` ripartono ora.")
    # a merge made with the workflow's token starts no workflow by itself:
    # the tests and the security tests of main are started here
    gh("workflow", "run", "tests.yml", "--repo", a.repo, "--ref", "main")
    gh("workflow", "run", "security.yml", "--repo", a.repo, "--ref", "main")
    print("merged #%d; the tests of main started" % n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
