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
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OWN_JOBS = {"merge", "merge-ready", "hand-over", "sandbox-issue", "advisories-issue", "report", "tell"}
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
    r"|__import__|\bimportlib\b|\bsubprocess\b|\bsocket\b|\burllib\b|\bhttps?\b|://|\bexec\s*\(|\beval\s*\("
    r"|\bcompile\s*\(|\bbase64\b|\batexit\b|\bRUNNER_|\bGITHUB_|\bCI\b|\bpytest\b|\bunittest\b"
    r"|\bsys\._getframe\b|\binspect\b|\bgc\.get_|\bsetattr\s*\(|\bglobals\s*\(|\bopen\s*\(|\bos\.system\b"
    r"|\bctypes\b|\bpickle\b|\bmarshal\b|\bsignal\b|\bthreading\b|QProcess|QNetwork|runJavaScript"
    r"|setUrlRequestInterceptor|setFeaturePermission|QWebEngineScript")


# What a change to a Python module may not add without a person (review 4 of
# 1.1.19, N1: a list of words did not see an alias, a name built from parts,
# a new address or a test told by the command line). Judged on the syntax
# trees of the file before and after the change: anything of these kinds
# that the new file has more of than the old one keeps it for a person.
RISKY_CALLS = {"getattr", "setattr", "delattr", "vars", "globals", "locals", "eval", "exec", "compile",
               "__import__", "open", "input", "breakpoint", "type", "super"}
RISKY_METHODS = {"system", "popen", "spawn", "run", "call", "check_output", "Popen", "exec_module",
                 "import_module", "load_source", "platformName", "setUrlRequestInterceptor", "runJavaScript",
                 "setFeaturePermission", "setHttpUserAgent", "setDnsMode", "get", "post", "urlopen",
                 "setRawHeader", "insert", "setProxy", "write_text", "write_bytes", "unlink", "rmtree"}
RISKY_ATTRS = {"environ", "argv", "modules", "path", "executable", "stdin", "stdout", "stderr", "settrace",
               "setprofile", "_getframe", "f_back", "__dict__", "__class__", "__globals__", "__code__",
               "__builtins__", "__subclasses__", "__bases__", "__mro__", "f_globals", "f_locals"}
RISKY_NAMES = {"os", "sys", "subprocess", "socket", "urllib", "http", "importlib", "builtins", "ctypes",
               "pickle", "marshal", "base64", "atexit", "inspect", "gc", "threading", "signal", "shutil",
               "QProcess", "QNetworkAccessManager", "QNetworkRequest", "QWebEngineScript", "QLibrary"}
RISKY_WORDS = ("://", "environ", "ike_", "pytest", "github_", "runner_", "offscreen", "update.json", "pubkey",
               "conftest", "argv", "sandbox", "--")


def risky_features(source):
    """A Counter of the risky things in a Python source, or None when it does not parse."""
    import ast
    import collections
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return None
    out = collections.Counter()
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mod = getattr(node, "module", None) or ""
            for a in node.names:
                out["import %s.%s as %s" % (mod, a.name, a.asname)] += 1
                imported.add(a.asname or a.name.split(".")[0])
        elif isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name) and f.id in RISKY_CALLS:
                out["call %s()" % f.id] += 1
            elif isinstance(f, ast.Attribute) and f.attr in RISKY_METHODS:
                out["call .%s()" % f.attr] += 1
        elif isinstance(node, ast.Attribute):
            if node.attr in RISKY_ATTRS:
                out["attribute .%s" % node.attr] += 1
        elif isinstance(node, ast.Name):
            if node.id in RISKY_NAMES:
                out["name %s" % node.id] += 1
        elif isinstance(node, ast.Constant) and isinstance(node.value, (str, bytes)):
            text = node.value.decode("latin-1") if isinstance(node.value, bytes) else node.value
            low = text.lower()
            for w in RISKY_WORDS:
                if w in low:
                    out["text with %r" % w] += 1
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            out["global or nonlocal"] += 1
        elif isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for t in targets:
                for sub in ast.walk(t):
                    if isinstance(sub, ast.Attribute):
                        base = sub.value
                        while isinstance(base, ast.Attribute):
                            base = base.value
                        if not (isinstance(base, ast.Name) and base.id in ("self", "cls")):
                            out["assignment to %s" % ast.unparse(sub)[:60]] += 1
    for name in imported:
        out["module name in use: %s" % name] += 0       # imports are counted above
    return out


def tree_problem(name, old, new):
    """"" when the new source adds nothing risky to the old one (both whole files)."""
    a, b = risky_features(old or ""), risky_features(new or "")
    if a is None or b is None:
        return "%s: the file does not parse" % name
    more = b - a
    if more:
        return "%s: %s (a person reads it)" % (name, sorted(more)[0])
    return ""


DOC_LINK = re.compile(r"https?://(?!github\.com/NullSector-2077/IKE-Browser[/)\s])")


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
        # only new entries: a version heading, list items, blank lines, linking
        # nowhere but this repository; nothing removed. (They are added to the
        # top section, or appended to it when its version is not out yet:
        # tools/prepare-maintenance.py; the notes of a release come only from
        # its own section.)
        links = re.findall(r"https?://[^\s)>\]]+", "\n".join(added))
        shape = re.compile(r"^(## \d+\.\d+\.\d+|- .*|  .*|)$")
        if [x for x in removed if x.strip()] or any(not shape.match(x) for x in added) or "`" in "".join(added) \
                or any(not u.startswith("https://github.com/%s/" % repo) for u in links):
            return "%s: more than new entries" % name
        return ""
    rule = VERSION_LINES[name]
    if any(not rule.search(x) for x in removed + added if x.strip()):
        return "%s: more than the version" % name
    if sorted(VERSION.sub("V", x) for x in removed) != sorted(VERSION.sub("V", x) for x in added):
        return "%s: more than the version" % name
    # the version moves by one step at most (1.1.20 -> 1.1.21), never a jump (N1)
    for old, new in zip(sorted(removed), sorted(added)):
        a = re.search(r"(\d+)\.(\d+)\.(\d+)", old)
        b = re.search(r"(\d+)\.(\d+)\.(\d+)", new)
        if a and b:
            x, y = tuple(map(int, a.groups())), tuple(map(int, b.groups()))
            if y != x and y != (x[0], x[1], x[2] + 1):
                return "%s: the version jumps (%s -> %s)" % (name, a.group(0), b.group(0))
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
        if "old_source" not in f or "new_source" not in f:
            return "%s: the whole file could not be read" % name
        why = tree_problem(name, f["old_source"], f["new_source"])
        if why:
            return why
    if name.endswith(".md"):
        # the owner pastes commands from the documents: no new link outside
        # the repository, no code (N1)
        for _start, _removed, added in parts:
            for line in added:
                if DOC_LINK.search(line) or "`" in line or line.startswith(("    ", "\t")):
                    return "%s: a link or code a person must read (%s)" % (name, line.strip()[:80])
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
        if c.get("name") in OWN_JOBS:
            continue                             # the automation's own reporting jobs (N7)
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


def file_at(repo, path, ref):
    import base64
    data = api("repos/%s/contents/%s?ref=%s" % (repo, path, ref))
    return base64.b64decode(data["content"]).decode("utf-8")


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
    base = (pr.get("base") or {}).get("sha", "")
    for f in files:                       # the whole files, before and after (N1)
        if f.get("filename", "").endswith(".py") and f.get("status") == "modified":
            try:
                f["old_source"] = file_at(a.repo, f["filename"], base)
                f["new_source"] = file_at(a.repo, f["filename"], a.sha)
            except (RuntimeError, ValueError, KeyError):
                pass
    guard = _guard()
    published = released(a.repo, "v" + version_of_main())
    # a check still running (another workflow's last job): read again for a
    # while, so that the deciding run does not end on "wait" for good (N7)
    for _round in range(16):
        checks = api("repos/%s/commits/%s/check-runs?per_page=100" % (a.repo, a.sha)).get("check_runs", [])
        kind, why = decide(a.repo, pr, commits, files, checks, lambda name: guard.allowed_path(name, False),
                           published=published, unread=unread_merge(a.repo))
        if kind != "wait" or a.dry_run:
            break
        time.sleep(30)
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
