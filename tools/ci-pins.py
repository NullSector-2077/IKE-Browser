#!/usr/bin/env python3
"""The pins of the workflows, kept current by a deterministic tool (no AI here).

The workflows pin what they run: every GitHub Action by the commit of a
release (with the release as a comment, 1.1.17), cargo-deny's version, the
Python and Node.js versions of setup-python and setup-node, and the Rust
toolchain. Since 2026-11-22 this tool, NOT an AI, updates them, each pin on
its own isolated branch ``automation/update/ci-<name>`` (daily-maintenance.yml):

- an Action only to the commit of an official release tag of the SAME
  action (vX.Y.Z, read with `git ls-remote` from github.com/<owner>/<repo>,
  the annotated tag peeled to its commit), and the comment to that tag;
- cargo-deny to its newest release on crates.io;
- Python to the version Arch Linux ships (users run Arch's Python), when
  setup-python offers it; Node.js to the newest LTS line;
- the Rust toolchain: "stable" follows Rust's releases by itself (nothing to
  pin); a numeric toolchain moves to the newest stable release.

Its commit is ``ci: <name> <old> -> <new> (tools/ci-pins.py, no AI)`` and changes
one line per pin and nothing else. The tests run on that branch, and the
verified merge (tools/automerge.py, verify_change below) accepts exactly these
edits of the workflows: every changed line one pin of the named one, the same
action, a commit that `git ls-remote` shows is the release tag written beside
it; any other workflow change keeps the pull request for a person. An AI never
edits a workflow: a workflow change an AI wants is a written proposal for a
person (tools/autofix-plan.py, WP12).

Dependabot stays on for the Actions, monthly, as a double check (its pull
request is a person's to merge; when this tool's candidate merged first,
Dependabot closes its own).

    ci-pins.py scan [--root DIR] [--json OUT]
    ci-pins.py check [--root DIR] --json OUT          (the network: newest versions)
    ci-pins.py apply --id ci-<name> --to VERSION [--sha SHA] [--root DIR]
    ci-pins.py verify --base REF --head REF --id ci-<name>   (git ls-remote)
"""

import argparse
import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ACTION = re.compile(r"^(?P<lead>\s*-?\s*uses:\s*)(?P<action>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_./-]+)?)"
                    r"@(?P<sha>[0-9a-f]{40})(?P<gap>\s*#\s*)(?P<tag>v?\d+(?:\.\d+){0,2})\s*$")
RELEASE_TAG = re.compile(r"^v?\d+\.\d+\.\d+$")
CARGO_DENY = re.compile(r"cargo-deny(?P<sep>@|-| )(?P<version>\d+\.\d+\.\d+)")
PYTHON = re.compile(r"^(?P<lead>\s*python-version:\s*)(?P<q>[\"']?)(?P<version>3\.\d+)(?P=q)\s*$")
NODE = re.compile(r"^(?P<lead>\s*node-version:\s*)(?P<q>[\"']?)(?P<version>\d+)(?P=q)\s*$")
RUST = re.compile(r"rustup toolchain install (?P<version>stable|\d+\.\d+(?:\.\d+)?)\b")
COMMIT = re.compile(r"^ci: (ci-[a-z0-9-]+) (\S{1,80}) -> (\S{1,80}) \(tools/ci-pins\.py, no AI\)$")
UA = {"User-Agent": "ike-browser-ci-pins"}


def workflow_files(root):
    gh = Path(root) / ".github"
    return sorted(gh.glob("workflows/*.yml")) + sorted(gh.glob("actions/**/action.yml"))


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60]


def pin_of_line(line):
    """(id, kind, name, version, sha) of the pin on one line, or None."""
    m = ACTION.match(line)
    if m:
        repo = "/".join(m.group("action").split("/")[:2])
        return ("ci-" + slug(repo), "action", repo, m.group("tag"), m.group("sha"))
    m = CARGO_DENY.search(line)
    if m:
        return ("ci-cargo-deny", "cargo-deny", "cargo-deny", m.group("version"), "")
    m = PYTHON.match(line)
    if m:
        return ("ci-python", "python", "Python", m.group("version"), "")
    m = NODE.match(line)
    if m:
        return ("ci-node", "node", "Node.js", m.group("version"), "")
    m = RUST.search(line)
    if m:
        return ("ci-rust", "rust", "Rust toolchain", m.group("version"), "")
    return None


def scan(root=ROOT):
    """{id: {"kind", "name", "versions": {version}, "shas": {sha}, "lines": [(file, line number)]}}."""
    out = {}
    for f in workflow_files(root):
        rel = str(f.relative_to(root))
        for n, line in enumerate(f.read_text("utf-8").split("\n"), 1):
            pin = pin_of_line(line)
            if not pin:
                continue
            pid, kind, name, version, sha = pin
            rec = out.setdefault(pid, {"id": pid, "kind": kind, "name": name, "versions": set(), "shas": set(),
                                       "lines": []})
            rec["versions"].add(version)
            if sha:
                rec["shas"].add(sha)
            rec["lines"].append((rel, n))
    return out


def vkey(v):
    return tuple(int(x) for x in re.findall(r"\d+", v or ""))


def ls_remote_tags(repo, run=subprocess.run):
    """{tag: commit} of github.com/<repo>'s tags, annotated tags peeled to their commit."""
    done = run(["git", "ls-remote", "--tags", "https://github.com/%s" % repo], capture_output=True, text=True,
               check=False, timeout=60)
    if done.returncode:
        raise RuntimeError("git ls-remote %s: %s" % (repo, done.stderr.strip()[:200]))
    tags, peeled = {}, {}
    for line in done.stdout.splitlines():
        parts = line.split()
        if len(parts) != 2 or not parts[1].startswith("refs/tags/"):
            continue
        name = parts[1][len("refs/tags/"):]
        if name.endswith("^{}"):
            peeled[name[:-3]] = parts[0]
        else:
            tags[name] = parts[0]
    tags.update(peeled)
    return tags


def newest_release(tags, current):
    """The newest release tag (vX.Y.Z, the same style as the current one) and its commit, or None."""
    style_v = current.startswith("v")
    best = None
    for tag, sha in tags.items():
        if not RELEASE_TAG.match(tag) or tag.startswith("v") != style_v:
            continue
        if best is None or vkey(tag) > vkey(best[0]):
            best = (tag, sha)
    return best


def fetch_json(url, get=None):
    if get:
        return json.loads(get(url))
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def newest_cargo_deny(get=None):
    data = (get or _get)("https://index.crates.io/ca/rg/cargo-deny")
    versions = [json.loads(x)["vers"] for x in data.splitlines() if x.strip()]
    versions = [v for v in versions if re.fullmatch(r"\d+\.\d+\.\d+", v)]
    return max(versions, key=vkey) if versions else ""


def _get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8")


def arch_python(get=None):
    """Arch's python as major.minor (users run it)."""
    data = fetch_json("https://archlinux.org/packages/search/json/?name=python", get)
    for r in data.get("results", []):
        if r.get("pkgname") == "python" and r.get("repo") in ("core", "extra"):
            return ".".join(r["pkgver"].split(".")[:2])
    return ""


def setup_python_offers(minor, get=None):
    data = fetch_json("https://raw.githubusercontent.com/actions/python-versions/main/versions-manifest.json", get)
    return any(isinstance(e, dict) and e.get("stable") and str(e.get("version", "")).startswith(minor + ".")
               for e in data)


def newest_node_lts(get=None):
    data = fetch_json("https://nodejs.org/dist/index.json", get)
    majors = [int(e["version"].lstrip("v").split(".")[0]) for e in data if e.get("lts")]
    return str(max(majors)) if majors else ""


def newest_rust(get=None):
    text = (get or _get)("https://static.rust-lang.org/dist/channel-rust-stable.toml")
    m = re.search(r'^\[pkg\.rust\]\s*\nversion = "(\d+\.\d+\.\d+)', text, re.M)
    return m.group(1) if m else ""


def check(root=ROOT, tags=ls_remote_tags, get=None):
    """[{"id", "name", "kind", "from", "to", "sha", "note"}] of the pins with a newer version (or an error)."""
    out = []
    for pid, rec in sorted(scan(root).items()):
        current = max(rec["versions"], key=vkey)
        row = {"id": pid, "name": rec["name"], "kind": rec["kind"], "from": current, "to": "", "sha": "",
               "lines": len(rec["lines"])}
        try:
            if rec["kind"] == "action":
                best = newest_release(tags(rec["name"]), current)
                if best and (vkey(best[0]) > vkey(current) or len(rec["versions"]) > 1 or len(rec["shas"]) > 1):
                    if best[1] not in rec["shas"] or len(rec["shas"]) > 1:
                        row.update(to=best[0], sha=best[1])
            elif rec["kind"] == "cargo-deny":
                new = newest_cargo_deny(get)
                if new and vkey(new) > vkey(current):
                    row["to"] = new
            elif rec["kind"] == "python":
                new = arch_python(get)
                if new and vkey(new) > vkey(current) and setup_python_offers(new, get):
                    row["to"] = new
            elif rec["kind"] == "node":
                new = newest_node_lts(get)
                if new and vkey(new) > vkey(current):
                    row["to"] = new
            elif rec["kind"] == "rust":
                if current == "stable":
                    row["note"] = "follows Rust's stable releases by itself: nothing to pin"
                else:
                    new = newest_rust(get)
                    if new and vkey(new) > vkey(current):
                        row["to"] = new
        except Exception as e:          # the network: nothing to make today
            row["error"] = "%s: %s" % (type(e).__name__, str(e)[:200])
        out.append(row)
    return out


def candidates(rows):
    """The candidate records (as tools/update-candidates.py plans them) of the pins with a newer version."""
    return [{"id": r["id"], "component": "CI pin: %s" % r["name"], "from": r["from"], "to": r["to"],
             "sha": r.get("sha", ""), "error": r.get("error", "")} for r in rows if r.get("to") or r.get("error")]


def apply(root, pid, to, sha=""):
    """Rewrite every line of the pin pid to version `to` (an action: to its commit sha and tag)."""
    changed = 0
    for f in workflow_files(root):
        lines = f.read_text("utf-8").split("\n")
        new = []
        for line in lines:
            orig = line
            pin = pin_of_line(line)
            if pin and pin[0] == pid:
                if pin[1] == "action":
                    if not re.fullmatch(r"[0-9a-f]{40}", sha or ""):
                        raise ValueError("an action needs the release's commit")
                    m = ACTION.match(line)
                    line = "%s%s@%s%s%s" % (m.group("lead"), m.group("action"), sha, m.group("gap"), to)
                elif pin[1] == "cargo-deny":
                    line = CARGO_DENY.sub(lambda m: "cargo-deny%s%s" % (m.group("sep"), to), line)
                elif pin[1] in ("python", "node"):
                    rx = PYTHON if pin[1] == "python" else NODE
                    m = rx.match(line)
                    line = "%s%s%s%s" % (m.group("lead"), m.group("q"), to, m.group("q"))
                else:
                    line = RUST.sub("rustup toolchain install %s" % to, line)
                changed += line != orig
            new.append(line)
        if new != lines:
            f.write_text("\n".join(new), "utf-8")
    return changed


def verify_change(pid, old_text, new_text, tags=ls_remote_tags):
    """Why the change of one workflow file is more than this tool's edit of the pin pid, or "".

    Every changed line must be one pin of pid on both sides, at the same place (same number of
    lines), the same action, only its version (and an action's commit) changed; an action's new
    commit must be the commit of the release tag written beside it (git ls-remote of that action)."""
    a, b = old_text.split("\n"), new_text.split("\n")
    if len(a) != len(b):
        return "lines added or removed in a workflow"
    seen = False
    for x, y in zip(a, b):
        if x == y:
            continue
        px, py = pin_of_line(x), pin_of_line(y)
        if not px or not py or px[0] != pid or py[0] != pid or px[1] != py[1]:
            return "a workflow line that is not the pin of %s changed: %s" % (pid, y.strip()[:100])
        if px[1] == "action":
            mx, my = ACTION.match(x), ACTION.match(y)
            if mx.group("action") != my.group("action") or mx.group("lead") != my.group("lead"):
                return "another action on the line: %s" % y.strip()[:100]
            if not RELEASE_TAG.match(my.group("tag")):
                return "not a release tag: %s" % my.group("tag")
            try:
                found = tags(py[2]).get(my.group("tag"))
            except Exception as e:
                return "the release tag could not be checked (%s): not verified" % str(e)[:100]
            if found != my.group("sha"):
                return "%s@%s is not the commit of its release %s" % (my.group("action"), my.group("sha")[:12],
                                                                    my.group("tag"))
        else:
            if re.sub(r"\d+(?:\.\d+)*", "V", x) != re.sub(r"\d+(?:\.\d+)*", "V", y):
                return "more than the version on the line: %s" % y.strip()[:100]
        seen = True
    return "" if seen else "nothing changed"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan")
    s.add_argument("--root", default=str(ROOT))
    s.add_argument("--json")
    c = sub.add_parser("check")
    c.add_argument("--root", default=str(ROOT))
    c.add_argument("--json", required=True)
    p = sub.add_parser("apply")
    p.add_argument("--root", default=str(ROOT))
    p.add_argument("--id", required=True)
    p.add_argument("--to", required=True)
    p.add_argument("--sha", default="")
    v = sub.add_parser("verify")
    v.add_argument("--id", required=True)
    v.add_argument("--base", required=True)
    v.add_argument("--head", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "scan":
        data = {k: dict(v, versions=sorted(v["versions"]), shas=sorted(v["shas"])) for k, v in scan(a.root).items()}
        text = json.dumps(data, indent=1)
        if a.json:
            Path(a.json).write_text(text + "\n", "utf-8")
        print(text)
        return 0
    if a.cmd == "check":
        rows = check(a.root)
        Path(a.json).write_text(json.dumps({"pins": rows, "candidates": candidates(rows)}, indent=1) + "\n", "utf-8")
        for r in rows:
            print("%-28s %-10s %s -> %s %s" % (r["id"], r["kind"], r["from"], r["to"] or "-",
                                             r.get("error") or r.get("note", "")))
        return 0
    if a.cmd == "apply":
        if not re.fullmatch(r"ci-[a-z0-9-]{1,60}", a.id) or not re.fullmatch(r"v?\d+(?:\.\d+){0,2}", a.to):
            print("::error::not a pin or not a version")
            return 1
        n = apply(Path(a.root), a.id, a.to, a.sha)
        print("%d line(s) of %s now at %s" % (n, a.id, a.to))
        return 0 if n else 1
    # verify: every commit base..head is this tool's and every changed file a workflow pin edit
    out = subprocess.run(["git", "log", "--format=%s", "%s..%s" % (a.base, a.head)], capture_output=True,
                         text=True, check=True).stdout.splitlines()
    if not out or any(not COMMIT.match(x) or COMMIT.match(x).group(1) != a.id for x in out):
        print("::error::a commit that is not this tool's for %s" % a.id)
        return 1
    names = subprocess.run(["git", "diff", "--name-only", a.base, a.head], capture_output=True, text=True,
                           check=True).stdout.split()
    for name in names:
        if not name.startswith((".github/workflows/", ".github/actions/")):
            print("::error::%s: not a workflow" % name)
            return 1
        old = subprocess.run(["git", "show", "%s:%s" % (a.base, name)], capture_output=True, text=True).stdout
        new = subprocess.run(["git", "show", "%s:%s" % (a.head, name)], capture_output=True, text=True).stdout
        why = verify_change(a.id, old, new)
        if why:
            print("::error::%s: %s" % (name, why))
            return 1
    print("only the pin of %s changed, to a release of the same action" % a.id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
