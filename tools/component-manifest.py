#!/usr/bin/env python3
"""The component manifest: the one place an external integrated component is declared (no AI here).

components.json, at the root of the repository, declares every component that comes from upstream
and lives in I.K.E.'s tree (2026-11-22, the owner's rule: a component added later is catalogued and
updated by the chain itself, with no change of code):

    "<id>": {
      "name":     what it is,
      "upstream": {"git": URL, "tag": "v*"} | {"npm": NAME} | {"pypi": NAME}   where its versions are read,
      "files":    the files it produces in the repository,
      "build":    an existing builder of I.K.E.'s (tools/build-*.py or .mjs: Dark Reader's lists, uBlock
                  Origin, KDE's Breeze icons), or
      "download": [{"url": "https://.../{version}/x.js", "file": "ike/resources/x.js", "sha256": "..."}]
                  with "version": the version in use (a plain download, checked by its sha256),
      "licence":  its licence file under licenses/,
      "kinds":    the inventory's kinds (default: integrated),
      "tests":    the test categories an update of it needs (never fewer than DEFAULT_TESTS)
    }

tools/update-candidates.py gives every entry its candidate ``automation/update/<id>`` (spec());
tools/check-components.py finds its newer version and applies it (check_entry, apply_entry); the rest
of the chain is the same for all: tests, Arch Linux, the automatic fix on its branch with daily
retries, "Nothing gets worse", the AI reviews, the verified merge.

A plain download is trusted only as far as it can be checked: before any update is made, the
entry's own version is downloaded again and must give exactly the bytes the repository has (the
sha256 of each file). An upstream that does not reproduce the file makes no candidate. Hosts are
limited to ALLOWED_HOSTS, over HTTPS.

An entry the automatic fix adds (the inventory guard told it which file has none) is a data change
judged by ai_entry_problems(): only new entries, a plain download (never a build command), the
allowed hosts, files that exist with the sha256 it declares, no file another entry has, a licence
file, and every default test category. It then goes through the whole verification like any fix.

    component-manifest.py check [--root DIR]        validates components.json
    component-manifest.py list  [--root DIR]        ids and files
"""

import argparse
import fnmatch
import hashlib
import json
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILE = "components.json"
SCHEMA = 1
ID = re.compile(r"^[a-z0-9][a-z0-9-]{1,40}$")
# ids the chain already uses for other things (tools/update-candidates.py, the security and lists branches)
RESERVED = ("adblock", "crates", "pyo3", "pkgbuild", "test-qt", "test-tools", "test-libs")
RESERVED_PREFIXES = ("crate-major-", "ci-", "arch-testing-", "security-", "lists-", "revert-")
BUILDERS = ("tools/build-darkreader-lists.py", "tools/build-ubo-scriptlets.mjs", "tools/build-breeze-icons.py")
ALLOWED_HOSTS = ("github.com", "raw.githubusercontent.com", "codeload.github.com", "registry.npmjs.org",
                 "pypi.org", "files.pythonhosted.org", "crates.io", "static.crates.io")
FILE_ROOTS = ("ike/resources/", "vendor/", "data/", "ike/")
DEFAULT_TESTS = ("unit-integration", "licences", "installed", "tests-kept", "no-regression")
DEFAULT_KINDS = ("integrated",)
SHA = re.compile(r"^[0-9a-f]{64}$")
VERSION = re.compile(r"^[0-9A-Za-z][0-9A-Za-z._+-]{0,60}$")
MAX_BYTES = 32 * 1024 * 1024
KEYS = {"name", "upstream", "files", "build", "download", "version", "licence", "kinds", "tests", "note"}


class Unverified(Exception):
    """The declared upstream does not give the file the repository has: no update is made from it."""


def read(root=ROOT):
    """The manifest's data; ValueError when it is missing or not valid."""
    try:
        data = json.loads((Path(root) / FILE).read_text("utf-8"))
    except (OSError, ValueError) as e:
        raise ValueError("%s could not be read: %s" % (FILE, e))
    bad = problems(data)
    if bad:
        raise ValueError("%s: %s" % (FILE, "; ".join(bad[:5])))
    return data


def components(root=ROOT):
    """{id: entry}; {} when there is no valid manifest (the callers then know no generic component)."""
    try:
        return read(root)["components"]
    except ValueError:
        return {}


def _host_ok(url):
    try:
        parts = urllib.parse.urlsplit(str(url))
        return parts.scheme == "https" and parts.hostname in ALLOWED_HOSTS and not parts.username and \
            parts.port in (None, 443)
    except ValueError:
        return False


def _path_ok(path):
    return isinstance(path, str) and path.startswith(FILE_ROOTS) and ".." not in Path(path).parts and \
        not path.startswith("/") and "\\" not in path and not path.endswith("/")


def entry_problems(cid, e):
    """What is wrong with one entry (a list)."""
    out = []
    if not ID.match(str(cid)) or str(cid).startswith(RESERVED_PREFIXES):
        out.append("%s: not a component id (lower-case letters, digits and dashes; not a reserved prefix)" % cid)
    if not isinstance(e, dict):
        return out + ["%s: not an object" % cid]
    out += ["%s: unknown key %s" % (cid, k) for k in sorted(set(e) - KEYS)]
    if not isinstance(e.get("name"), str) or not e["name"].strip():
        out.append("%s: no name" % cid)
    up = e.get("upstream")
    if not isinstance(up, dict) or not ({"git", "npm", "pypi"} & set(up)) or set(up) - {"git", "npm", "pypi", "tag"}:
        out.append("%s: upstream must name git (with an optional tag pattern), npm or pypi" % cid)
    else:
        if "git" in up and not _host_ok(up["git"]):
            out.append("%s: the git upstream is not on an allowed host over https (%s)" % (cid, ", ".join(ALLOWED_HOSTS)))
        for k in ("npm", "pypi", "tag"):
            if k in up and not re.fullmatch(r"[@A-Za-z0-9._/*-]{1,100}", str(up[k])):
                out.append("%s: upstream.%s is not a plain name" % (cid, k))
    files = e.get("files")
    if not isinstance(files, list) or not files or not all(_path_ok(f) for f in files):
        out.append("%s: files must be paths of the repository under %s" % (cid, ", ".join(FILE_ROOTS)))
        files = []
    build, down = e.get("build"), e.get("download")
    if (build is None) == (down is None):
        out.append("%s: exactly one of build (an existing builder) and download (with version)" % cid)
    if build is not None and build not in BUILDERS:
        out.append("%s: build must be one of I.K.E.'s builders (%s)" % (cid, ", ".join(BUILDERS)))
    if down is not None:
        if not VERSION.match(str(e.get("version", ""))):
            out.append("%s: a download needs the version in use" % cid)
        if not isinstance(down, list) or not down:
            out.append("%s: download must be a list" % cid)
            down = []
        for d in down:
            if not isinstance(d, dict) or set(d) != {"url", "file", "sha256"} or not _host_ok(d.get("url")) \
                    or not SHA.match(str(d.get("sha256"))) or d.get("file") not in files \
                    or not ("{version}" in str(d.get("url")) or "{tag}" in str(d.get("url"))):
                out.append("%s: each download is {url (https, an allowed host, with {version} or {tag}), file (one "
                           "of files), sha256}" % cid)
        if sorted(str(d.get("file")) for d in down if isinstance(d, dict)) != sorted(files):
            out.append("%s: every file needs exactly one download" % cid)
    lic = e.get("licence")
    if not isinstance(lic, str) or not re.fullmatch(r"licenses/[A-Za-z0-9._-]{1,80}", lic):
        out.append("%s: licence must be a file under licenses/" % cid)
    tests = e.get("tests", list(DEFAULT_TESTS))
    if not isinstance(tests, list) or not set(DEFAULT_TESTS) <= set(tests):
        out.append("%s: tests may not leave out %s" % (cid, ", ".join(DEFAULT_TESTS)))
    kinds = e.get("kinds", list(DEFAULT_KINDS))
    if not isinstance(kinds, list) or not kinds or not all(isinstance(k, str) for k in kinds):
        out.append("%s: kinds must be a list of the inventory's kinds" % cid)
    return out


def problems(data):
    """What is wrong with the manifest (a list; empty: valid)."""
    if not isinstance(data, dict) or data.get("schema") != SCHEMA or not isinstance(data.get("components"), dict):
        return ["not a manifest (schema %d, components)" % SCHEMA]
    out, owner = [], {}
    for cid, e in data["components"].items():
        if cid in RESERVED:
            out.append("%s: an id the chain already uses" % cid)
        out += entry_problems(cid, e)
        for f in (e.get("files") if isinstance(e, dict) and isinstance(e.get("files"), list) else ()):
            if f in owner:
                out.append("%s: %s already belongs to %s" % (cid, f, owner[f]))
            owner[f] = cid
    return out


def spec(cid, root=ROOT):
    """The candidate's rules of a manifest entry, in tools/update-candidates.py's shape, or None."""
    e = components(root).get(cid)
    if not e:
        return None
    out = {"files": tuple(e["files"]) + ((FILE,) if e.get("download") else ()), "serial": "", "ships": True,
           "wrapper": False, "kinds": tuple(e.get("kinds") or DEFAULT_KINDS), "manifest": True,
           "tests": tuple(e.get("tests") or DEFAULT_TESTS)}
    if e.get("build"):
        out["builder"] = e["build"]
    return out


def owner_of(path, root=ROOT):
    """The id of the entry that declares this file, or ""."""
    for cid, e in components(root).items():
        if path in e["files"] or path == e.get("licence"):
            return cid
    return ""


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def fetch(url, timeout=60):
    if not _host_ok(url):
        raise ValueError("not an allowed host: %s" % url[:120])
    req = urllib.request.Request(url, headers={"User-Agent": "ike-browser-component-check"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("more than %d bytes: %s" % (MAX_BYTES, url[:120]))
    return data


def git_tags(url, timeout=120):
    out = subprocess.run(["git", "ls-remote", "--tags", "--refs", url], capture_output=True, text=True,
                         timeout=timeout, check=False)
    if out.returncode:
        raise OSError("git ls-remote %s: %s" % (url, out.stderr.strip()[:200]))
    return [line.split("refs/tags/", 1)[1] for line in out.stdout.splitlines() if "refs/tags/" in line]


def vkey(version):
    return tuple(int(x) for x in re.findall(r"\d+", str(version))[:6])


def _stable(version):
    return bool(re.fullmatch(r"\d+(\.\d+){0,4}", version))


def latest(entry, get=fetch, tags=git_tags):
    """(version, tag) of the newest stable release upstream."""
    up = entry["upstream"]
    if "npm" in up:
        v = str(json.loads(get("https://registry.npmjs.org/%s/latest" % up["npm"]).decode("utf-8")).get("version", ""))
        return v, "v" + v
    if "pypi" in up:
        v = str(json.loads(get("https://pypi.org/pypi/%s/json" % up["pypi"]).decode("utf-8"))["info"]["version"])
        return v, "v" + v
    pattern = up.get("tag", "v*")
    found = []
    for tag in tags(up["git"]):
        if fnmatch.fnmatchcase(tag, pattern):
            version = tag[len(pattern.split("*")[0]):] if "*" in pattern else tag
            if _stable(version):
                found.append((vkey(version), version, tag))
    if not found:
        raise OSError("no release tag like %s upstream" % pattern)
    return max(found)[1:]


def _tag_of(entry, version):
    pattern = entry["upstream"].get("tag", "v*")
    return pattern.replace("*", version) if "*" in pattern else version


def downloads(entry, version, tag, get=fetch):
    """{file: bytes} of the entry at a version."""
    return {d["file"]: get(d["url"].replace("{version}", version).replace("{tag}", tag)) for d in entry["download"]}


def check_entry(root, cid, get=fetch, tags=git_tags):
    """Today's state of a download entry, in tools/check-components.py's shape: {"current", "latest",
    "update", "note"}. Unverified when its own version does not reproduce the repository's files."""
    entry = components(root)[cid]
    current = entry["version"]
    have = downloads(entry, current, _tag_of(entry, current), get)
    for d in entry["download"]:
        local = Path(root) / d["file"]
        on_disk = sha256(local.read_bytes()) if local.is_file() and not local.is_symlink() else ""
        if not (sha256(have[d["file"]]) == d["sha256"] == on_disk):
            raise Unverified("%s: the declared upstream at %s does not reproduce %s as the repository has it (no "
                             "update is made from an upstream that cannot be checked)" % (cid, current, d["file"]))
    version, tag = latest(entry, get, tags)
    info = {"current": current, "latest": version, "update": vkey(version) > vkey(current), "note": "", "also": ""}
    if info["update"]:
        info["_files"] = downloads(entry, version, tag, get)
        info["_cid"] = cid
        info["note"] = "plain download, sha256 recorded in %s" % FILE
    return info


def apply_entry(root, info):
    """Write the new files and the entry's new version and checksums."""
    root = Path(root)
    data = json.loads((root / FILE).read_text("utf-8"))
    entry = data["components"][info["_cid"]]
    for d in entry["download"]:
        blob = info["_files"][d["file"]]
        (root / d["file"]).write_bytes(blob)
        d["sha256"] = sha256(blob)
    entry["version"] = info["latest"]
    (root / FILE).write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", "utf-8")


def _parse(text):
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return None
    return data if not problems(data) else None


def update_problem(cid, old_text, new_text, sha_of):
    """Why the candidate's own change of the manifest is more than its entry's new version and
    checksums, or "". sha_of(path): the sha256 of the file in the candidate, or ""."""
    old, new = _parse(old_text), _parse(new_text)
    if old is None or new is None:
        return "the manifest does not parse or is not valid"
    a, b = old["components"], new["components"]
    if set(a) != set(b) or {k: v for k, v in old.items() if k != "components"} != \
            {k: v for k, v in new.items() if k != "components"}:
        return "entries added or removed, or the manifest's own fields changed"
    for other in a:
        if other != cid and a[other] != b[other]:
            return "the entry of %s changed (only %s may)" % (other, cid)
    if cid not in a or not a[cid].get("download"):
        return "%s has no download entry" % cid

    def frozen(e):
        return dict(e, version="", download=[dict(d, sha256="") for d in e["download"]])
    if frozen(a[cid]) != frozen(b[cid]):
        return "more than the version and the checksums of %s changed" % cid
    if vkey(b[cid]["version"]) <= vkey(a[cid]["version"]):
        return "the version of %s does not go up" % cid
    for d in b[cid]["download"]:
        if sha_of(d["file"]) != d["sha256"]:
            return "%s is not the file whose sha256 the manifest records" % d["file"]
    return ""


def ai_entry_problems(old_text, new_text, sha_of):
    """Why an AI's change of the manifest is refused (a list; empty: accepted): only new entries, each
    a plain download from an allowed host of files that exist with the sha256 it declares."""
    old, new = _parse(old_text), _parse(new_text)
    if old is None:
        return ["%s: the manifest before the change does not parse" % FILE]
    if new is None:
        try:
            bad = problems(json.loads(new_text))
        except (TypeError, ValueError):
            bad = ["it does not parse"]
        return ["%s: %s" % (FILE, b) for b in bad[:6]]
    if {k: v for k, v in old.items() if k != "components"} != {k: v for k, v in new.items() if k != "components"}:
        return ["%s: only entries may be added" % FILE]
    out = []
    for cid, e in old["components"].items():
        if new["components"].get(cid) != e:
            out.append("%s: the entry %s is changed or removed (an AI may only add a missing entry)" % (FILE, cid))
    added = [c for c in new["components"] if c not in old["components"]]
    if not added and not out:
        out.append("%s: nothing added" % FILE)
    for cid in added:
        e = new["components"][cid]
        if e.get("build") or not e.get("download"):
            out.append("%s: %s: an AI's entry is a plain download, never a build command" % (FILE, cid))
            continue
        for d in e["download"]:
            if not sha_of or sha_of(d["file"]) != d["sha256"]:
                out.append("%s: %s: %s does not exist in the repository with the sha256 the entry declares (an "
                           "entry describes a file that is already there)" % (FILE, cid, d["file"]))
        if not sha_of or not sha_of(e["licence"]):
            out.append("%s: %s: the licence file %s does not exist" % (FILE, cid, e["licence"]))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("cmd", choices=("check", "list"))
    ap.add_argument("--root", default=str(ROOT))
    a = ap.parse_args(argv)
    try:
        data = read(a.root)
    except ValueError as e:
        print("::error::%s" % str(e).replace("::", ": "))
        return 1
    for cid, e in sorted(data["components"].items()):
        missing = [f for f in e["files"] + [e["licence"]] if not (Path(a.root) / f).is_file()]
        if missing:
            print("::error::%s: missing in the repository: %s" % (cid, ", ".join(missing)))
            return 1
        if a.cmd == "list":
            print("%s\t%s\t%s" % (cid, e.get("build") or "download %s" % e.get("version"), " ".join(e["files"])))
    print("%s: %d components declared" % (FILE, len(data["components"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
