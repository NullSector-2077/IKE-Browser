#!/usr/bin/env python3
"""Keep the licences of what I.K.E. ships in step with its sources (1.1.14, 1.1.18).

Writes, from ``ike-adblock/Cargo.lock``, ``cargo metadata`` and the crates'
own sources (in Cargo's download folder):

- in docs/THIRD-PARTY.md, the adblock-rust version of the components table and
  the lists of the Rust libraries: those compiled into the AdBlock engine
  (shipped) and those used only to build it (not shipped);
- licenses/RUST-CRATES.txt: every Rust library compiled into the engine, with
  its licence, copyright lines, repository, the checksum of its source on
  crates.io and the full text of every licence and notice file of its source
  (a standard text where the crate has none);
- licenses/NOTICE.ubo-scriptlets: copyright, licence and corresponding source
  of the uBlock Origin scriptlets, from ike/resources/ubo-scriptlets.json.

Every licence must be in the "allow" list of ike-adblock/deny.toml (the same
list cargo-deny checks); a licence that is not, or that cannot be read, stops
the tool with an error: it never passes silently. See docs/THIRD-PARTY.md,
"Approving a new licence".

    python3 tools/third-party.py            rewrite the files
    python3 tools/third-party.py --check    only compare; exit 1 if anything differs

The daily maintenance runs it whenever it moves adblock-rust to a new version
(tools/check-components.py); GitHub Actions runs --check on every pull request.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOC = ROOT / "docs" / "THIRD-PARTY.md"
MANIFEST = ROOT / "ike-adblock" / "Cargo.toml"
LOCK = ROOT / "ike-adblock" / "Cargo.lock"
DENY = ROOT / "ike-adblock" / "deny.toml"
CRATES_FILE = ROOT / "licenses" / "RUST-CRATES.txt"
UBO_JSON = ROOT / "ike" / "resources" / "ubo-scriptlets.json"
UBO_NOTICE = ROOT / "licenses" / "NOTICE.ubo-scriptlets"
STANDARD_TEXTS = ROOT / "tools" / "licence-texts"
TARGET = "x86_64-unknown-linux-gnu"

DOC_SHIPPED = "## Rust libraries compiled into `ike_adblock`"
DOC_BUILD = "## Rust libraries used only to build `ike_adblock`"
DOC_OTHER = "## Rust libraries of other platforms"

# names of the licence and notice files of a crate's source
LICENCE_FILE = re.compile(r"(?i)^(licen[cs]e|copying|copyright|notice|unlicense)([-._][a-z0-9._-]*)?$")
# what a licence file is, from words every copy of that licence has
FINGERPRINTS = (
    ("Apache-2.0", ("Apache License", "Version 2.0", "TERMS AND CONDITIONS FOR USE, REPRODUCTION, AND DISTRIBUTION")),
    ("MIT", ("Permission is hereby granted, free of charge, to any person obtaining a copy of this software",)),
    ("MPL-2.0", ("Mozilla Public License Version 2.0",)),
    ("Unicode-3.0", ("UNICODE LICENSE V3",)),
    ("Unicode-3.0", ("Unicode License v3",)),
    ("Unicode-DFS-2016", ("UNICODE, INC. LICENSE AGREEMENT - DATA FILES AND SOFTWARE",)),
    ("Unlicense", ("This is free and unencumbered software released into the public domain",)),
    ("ISC", ("Permission to use, copy, modify, and/or distribute this software for any",)),
    ("LLVM-exception", ("LLVM Exceptions to the Apache 2.0 License",)),
)


class LicenceError(Exception):
    """A licence that is not approved, or that cannot be read or met."""


# --- the approved licences and SPDX expressions ------------------------------

def approved(deny_text):
    """The licences of the "allow" list of deny.toml, in order."""
    m = re.search(r"^allow\s*=\s*\[(.*?)\]", deny_text, re.S | re.M)
    if not m:
        raise LicenceError("ike-adblock/deny.toml has no licence allow list")
    body = "\n".join(line.split("#", 1)[0] for line in m.group(1).splitlines())
    return re.findall(r'"([^"]+)"', body)


def _tokens(expr):
    expr = re.sub(r"\s*/\s*", " OR ", expr.strip())       # the old "MIT/Apache-2.0"
    return re.findall(r"\(|\)|[A-Za-z0-9.+:-]+", expr)


def parse(expr):
    """An SPDX licence expression as a tree: ("OR"|"AND", [..]) or a leaf
    string ("MIT", "Apache-2.0 WITH LLVM-exception"). AND binds tighter than OR.
    Anything else is an error."""
    toks = _tokens(expr or "")
    pos = 0

    def peek():
        return toks[pos] if pos < len(toks) else None

    def take():
        nonlocal pos
        pos += 1
        return toks[pos - 1] if pos <= len(toks) else None

    def leaf():
        tok = peek()
        if tok == "(":
            take()
            node = either()
            if take() != ")":
                raise LicenceError("unbalanced brackets in %r" % expr)
            return node
        if tok is None or tok in (")", "AND", "OR", "WITH"):
            raise LicenceError("cannot read the licence %r" % expr)
        name = take()
        if peek() == "WITH":
            take()
            exc = peek()
            if exc is None or exc in ("(", ")", "AND", "OR", "WITH"):
                raise LicenceError("cannot read the licence %r" % expr)
            name += " WITH " + take()
        return name

    def both():
        items = [leaf()]
        while peek() == "AND":
            take()
            items.append(leaf())
        return items[0] if len(items) == 1 else ("AND", items)

    def either():
        items = [both()]
        while peek() == "OR":
            take()
            items.append(both())
        return items[0] if len(items) == 1 else ("OR", items)

    if not toks:
        raise LicenceError("no licence stated")
    tree = either()
    if pos != len(toks):
        raise LicenceError("cannot read the licence %r" % expr)
    return tree


def leaves(tree):
    if isinstance(tree, str):
        return [tree]
    return [x for item in tree[1] for x in leaves(item)]


def normalised(expr):
    def show(tree, top=True):
        if isinstance(tree, str):
            return tree
        inner = (" %s " % tree[0]).join(show(t, False) for t in tree[1])
        return inner if top else "(%s)" % inner
    return show(expr if isinstance(expr, tuple) else parse(expr))


def check_approved(name, expr, allow):
    """Every licence of the expression must be approved: an alternative that is
    not approved is refused as well, so a person looks at it."""
    tree = parse(expr)
    bad = [x for x in leaves(tree) if x not in allow]
    if bad:
        raise LicenceError("%s: licence %s not approved (ike-adblock/deny.toml)" % (name, ", ".join(bad)))
    return tree


def satisfied(tree, have):
    """Is the expression met by the licences whose text we have?"""
    if isinstance(tree, str):
        base, _, exc = tree.partition(" WITH ")
        return base in have and (not exc or exc in have)
    test = any if tree[0] == "OR" else all
    return test(satisfied(t, have) for t in tree[1])


def needed(tree, have):
    """The licences still to add, as standard texts, so the expression is met."""
    if satisfied(tree, have):
        return []
    if isinstance(tree, str):
        base, _, exc = tree.partition(" WITH ")
        return [x for x in (base, exc) if x and x not in have]
    if tree[0] == "AND":
        return [x for t in tree[1] for x in needed(t, have)]
    options = [needed(t, have) for t in tree[1]]
    return min(options, key=len)


def kinds_of(text):
    flat = " ".join(text.split())
    return sorted({kind for kind, words in FINGERPRINTS if all(w in flat for w in words)})


# --- what cargo builds -------------------------------------------------------

def locked_packages(lock_text):
    """[(name, version)] of Cargo.lock, sorted as cargo lists them."""
    return re.findall(r'\[\[package\]\]\nname = "([^"]+)"\nversion = "([^"]+)"', lock_text)


def checksums(lock_text):
    return {(n, v): c for n, v, c in re.findall(
        r'\[\[package\]\]\nname = "([^"]+)"\nversion = "([^"]+)"\nsource = "[^"]+"\nchecksum = "([0-9a-f]+)"',
        lock_text)}


def metadata(platform=TARGET):
    """cargo metadata of the engine, for the target of the package (None: for
    every platform)."""
    cmd = ["cargo", "metadata", "--format-version", "1", "--locked", "--manifest-path", str(MANIFEST)]
    if platform:
        cmd += ["--filter-platform", platform]
    out = subprocess.run(cmd, check=True, capture_output=True, text=True).stdout
    return json.loads(out)


def classify(meta):
    """(shipped, build_only, other) package ids. Shipped: what the release
    build of the engine compiles into the module, i.e. its normal
    dependencies, followed from the engine, without procedural macros (they
    run in the compiler only) and without build scripts' dependencies."""
    pkgs = {p["id"]: p for p in meta["packages"]}
    nodes = {n["id"]: n for n in meta["resolve"]["nodes"]}
    root = meta["resolve"]["root"]

    def proc_macro(pid):
        return any("proc-macro" in t["kind"] for t in pkgs[pid]["targets"])

    shipped, todo = set(), [root]
    while todo:
        pid = todo.pop()
        if pid in shipped:
            continue
        shipped.add(pid)
        for dep in nodes[pid]["deps"]:
            normal = any(k.get("kind") is None for k in dep.get("dep_kinds", []))
            if normal and not proc_macro(dep["pkg"]):
                todo.append(dep["pkg"])
    built = set(nodes)
    return shipped, built - shipped, set(pkgs) - built


def licence_files(crate_dir):
    """Licence and notice files of a crate's source (any folder), relative."""
    found = []
    for folder, dirs, files in os.walk(crate_dir):
        dirs[:] = sorted(d for d in dirs if d not in ("target", ".git"))
        for name in sorted(files):
            if LICENCE_FILE.match(name):
                p = Path(folder) / name
                found.append(p.relative_to(crate_dir).as_posix())
    return found


def read_text(path):
    text = Path(path).read_bytes().decode("utf-8", "replace").replace("\r\n", "\n").replace("\r", "\n")
    return text.rstrip() + "\n"


def copyright_lines(texts):
    out = []
    for text in texts:
        for line in text.splitlines():
            line = " ".join(line.split())
            if not re.match(r"(?i)^(copyright\b|©|\(c\) *\d)", line):
                continue
            if re.search(r"\[yyyy\]|\{yyyy\}|<year>|Free Software Foundation|copyright owner\]|"
                         r"copyright holders|^copyright notice|^copyright license|copyright and permission notice",
                         line, re.I):
                continue
            if line not in out:
                out.append(line)
    return out


def authors(pkg):
    return [re.sub(r"\s*<[^>]*>", "", a).strip() for a in pkg.get("authors") or []]


def crate_entry(pkg, allow, sums, standard_dir=STANDARD_TEXTS):
    """Everything RUST-CRATES.txt says of one shipped crate."""
    name, version = pkg["name"], pkg["version"]
    expr = pkg.get("license")
    if not expr:
        raise LicenceError("%s %s states no licence (only a licence file): approve it by hand"
                           % (name, version))
    tree = check_approved("%s %s" % (name, version), expr, allow)
    crate_dir = Path(pkg["manifest_path"]).parent
    files = []
    for rel in licence_files(crate_dir):
        text = read_text(crate_dir / rel)
        files.append({"file": rel, "text": text, "kinds": kinds_of(text)})
    have = {k for f in files for k in f["kinds"]}
    for lic in needed(tree, have):
        std = Path(standard_dir) / ("%s.txt" % lic)
        if not std.is_file():
            raise LicenceError("%s %s: no text of %s in its source and no standard text in %s"
                               % (name, version, lic, standard_dir.relative_to(ROOT)
                                  if Path(standard_dir).is_relative_to(ROOT) else standard_dir))
        files.append({"file": "(standard text of %s: the crate's source has none)" % lic,
                      "text": read_text(std), "kinds": [lic]})
    local = pkg.get("source") is None
    return {
        "name": name, "version": version, "licence": normalised(expr),
        "repository": (pkg.get("repository") or "").rstrip("/") or
        ("the I.K.E. repository, ike-adblock/" if local else ""),
        "source": "ike-adblock/ in the I.K.E. repository (this release's tag)" if local else
        "https://crates.io/api/v1/crates/%s/%s/download (sha256 %s)" % (name, version,
                                                                      sums.get((name, version), "?")),
        "copyright": ["Copyright (C) 2026 the I.K.E. project"] if local else
        copyright_lines(f["text"] for f in files),
        "authors": authors(pkg),
        "files": files,
    }


# --- what is written ---------------------------------------------------------

HEADER = """\
Rust libraries compiled into the I.K.E. AdBlock Engine
======================================================

The AdBlock engine of I.K.E. (/usr/lib/ike-browser/vendor/adblock/
ike_adblock.abi3.so, and ike/_engine/adblock/ in the signed self-update) is
built from the sources in ike-adblock/ of the I.K.E. repository and statically
contains the Rust libraries ("crates") below, each under its own licence. This
file lists every one of them, with the full text of every licence and notice
file of its source (line endings normalised); where a crate's source has no
licence text, the standard text of its licence is given and said so.

Generated by tools/third-party.py from ike-adblock/Cargo.lock; do not edit.
The libraries used only while building (procedural macros, build scripts)
are not part of the engine: docs/THIRD-PARTY.md lists them.

Source code of the MPL-2.0 libraries (Mozilla Public License 2.0, section 3.2):
the engine contains them unmodified; their exact sources are the crates.io
downloads named below (the sha256 is the one pinned in ike-adblock/Cargo.lock),
also reachable from their repositories. The I.K.E. AdBlock Engine's own source
(MPL-2.0) is ike-adblock/ in https://github.com/NullSector-2077/IKE-Browser.

The Rust standard library is compiled into the engine as well: Copyright The
Rust Project Developers, licensed under the Apache License 2.0 or the MIT
licence, at your option, with the third-party parts listed in the notice of the
compiler that built the engine (installed next to this file as
RUST-STD-COPYRIGHT.html). Both licence texts are reproduced below.
"""


def render_crates(entries, extra_texts=()):
    """RUST-CRATES.txt: the inventory, then each different licence text once
    with the crates whose source carries it."""
    texts, users = [], {}
    for e in entries:
        for f in e["files"]:
            key = hashlib.sha256(f["text"].encode("utf-8")).hexdigest()
            if key not in users:
                users[key] = []
                texts.append((key, f))
            users[key].append("%s %s (%s)" % (e["name"], e["version"], f["file"]))
    for kind, text in extra_texts:                  # the Rust standard library's licences
        key = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if key not in users:
            users[key] = []
            texts.append((key, {"text": text, "kinds": [kind]}))
        users[key].append("the Rust standard library")
    number = {key: i for i, (key, _f) in enumerate(texts, 1)}
    out = [HEADER, "", "Inventory (%d libraries)" % len(entries), "-" * 24, ""]
    for e in entries:
        refs = []
        for f in e["files"]:
            key = hashlib.sha256(f["text"].encode("utf-8")).hexdigest()
            refs.append("[%d] %s" % (number[key], f["file"]))
        out.append("%s %s" % (e["name"], e["version"]))
        out.append("  licence:    %s" % e["licence"])
        out.append("  copyright:  %s" % ("; ".join(e["copyright"]) or
                                         "not stated in its licence files; authors: %s"
                                         % (", ".join(e["authors"]) or "not stated")))
        out.append("  repository: %s" % (e["repository"] or "not stated"))
        out.append("  source:     %s" % e["source"])
        out.append("  texts:      %s" % ("; ".join(refs)))
        out.append("")
    out += ["", "Licence and notice texts", "-" * 24, ""]
    for key, f in texts:
        out.append("=" * 79)
        out.append("[%d] %s" % (number[key], ", ".join(f["kinds"]) or "notice"))
        out.append("Used by: %s" % ", ".join(users[key]))
        out.append("=" * 79)
        out.append("")
        out.append(f["text"].rstrip("\n"))
        out.append("")
    return "\n".join(out).rstrip("\n") + "\n"


def render_doc(text, adblock_version, shipped, build_only, foreign=()):
    """docs/THIRD-PARTY.md with the version of adblock-rust and the lists.
    shipped / build_only / foreign: [(name, version, licence, repository)];
    foreign: in Cargo.lock for other platforms only, never built here."""
    if adblock_version:
        text = re.sub(r"adblock-rust [0-9][^ ]* \(filter engine, by Brave\)",
                      "adblock-rust %s (filter engine, by Brave)" % adblock_version, text)

    def block(title, intro, rows):
        lines = ["%s v%s — %s — %s" % (n, v, lic, repo or "no repository stated")
                 for n, v, lic, repo in rows]
        return "%s\n\n%s\n\n```\n%s\n```\n" % (title, intro, "\n".join(lines))

    new = (block(DOC_SHIPPED,
                 "Shipped (category 1): statically linked into the engine module. Their licence\n"
                 "texts and notices are in `licenses/RUST-CRATES.txt`, installed as\n"
                 "`/usr/share/licenses/ike-browser/RUST-CRATES.txt`. Generated by\n"
                 "`tools/third-party.py`.", shipped) + "\n" +
           block(DOC_BUILD,
                 "Not shipped (category 3): procedural macros, build scripts and their\n"
                 "libraries run only in the compiler. Generated by `tools/third-party.py`.",
                 build_only))
    if foreign:
        new += "\n" + block(DOC_OTHER,
                            "Not built (in `Cargo.lock` for other platforms only). Generated by\n"
                            "`tools/third-party.py`.", foreign)
    # the two lists end the file
    at = text.find("\n" + DOC_SHIPPED + "\n")
    if at < 0 or text.find(DOC_BUILD, at) < 0:
        raise LicenceError("docs/THIRD-PARTY.md has no lists of Rust libraries to update")
    return text[:at + 1] + new


def render_ubo_notice(data):
    """licenses/NOTICE.ubo-scriptlets from the header of ubo-scriptlets.json."""
    commit, date = data["commit"], data["date"]
    names = sorted(data["scriptlets"])
    return """\
uBlock Origin scriptlets in I.K.E.
==================================

File: /usr/lib/ike-browser/ike/resources/ubo-scriptlets.json (and
ike/resources/ubo-scriptlets.json in the signed self-update).

{copyright}
Upstream: {source}
Licence: {licence}. These scriptlets keep their own licence, the GNU General
Public License version 3 or (at your option) any later version, as stated in
every source file of uBlock Origin they come from; it is not I.K.E.'s licence
passed on to them (I.K.E. happens to use the same licence). The full text of
the GNU General Public License version 3 is in the file LICENSE next to this
one (/usr/share/licenses/ike-browser/LICENSE).

The file holds {count} scriptlets of uBlock Origin, taken from its source at

  commit {commit} ({date})
  {source}/tree/{commit}/src/js/resources

Corresponding source. The JSON file is generated: tools/build-ubo-scriptlets.mjs
of the I.K.E. repository (https://github.com/NullSector-2077/IKE-Browser, the
same file in the tag of this release) loads src/js/resources/scriptlets.js of
uBlock Origin at that commit with Node.js and writes, for each scriptlet, the
source text of its function exactly as uBlock Origin wrote it, its name,
aliases, dependencies and flags; nothing in the code is changed. The
corresponding source is therefore:

  1. uBlock Origin's sources at the commit above:
       git clone https://github.com/gorhill/uBlock src
       git -C src checkout {commit}
  2. the build tool: tools/build-ubo-scriptlets.mjs of I.K.E.;
  3. the command, run in the folder that holds "src":
       node /path/to/build-ubo-scriptlets.mjs
     which writes the same ubo-scriptlets.json, byte for byte.

The JSON file itself also carries the readable source of every scriptlet.

Scriptlets: {names}
""".format(copyright=data["copyright"], source=data["source"].rstrip("/"),
           licence=data["license"], commit=commit, date=date, count=len(names),
           names=", ".join(names))


# --- running -----------------------------------------------------------------

def rust_std_texts():
    return [("MIT", read_text(STANDARD_TEXTS / "MIT.txt")),
            ("Apache-2.0", read_text(STANDARD_TEXTS / "Apache-2.0.txt"))]


def generate(meta=None, every=None):
    """{path: new text} of every file this tool writes. meta: cargo metadata
    for the package's target; every: for all platforms (the crates of
    Cargo.lock that other platforms only would build)."""
    lock_text = LOCK.read_text("utf-8")
    allow = approved(DENY.read_text("utf-8"))
    meta = meta or metadata()
    every = every or metadata(None)
    pkgs = {p["id"]: p for p in meta["packages"]}
    shipped, build_only, other = classify(meta)
    if other:
        raise LicenceError("packages outside the build for %s: %s; classify them by hand"
                           % (TARGET, ", ".join(sorted(pkgs[i]["name"] for i in other))))
    locked = set(locked_packages(lock_text))
    known = {(p["name"], p["version"]) for p in every["packages"]}
    if known != locked:
        raise LicenceError("cargo metadata and Cargo.lock disagree: %s"
                           % sorted(known.symmetric_difference(locked)))
    built = {(p["name"], p["version"]) for p in meta["packages"]}
    foreign = sorted((p for p in every["packages"] if (p["name"], p["version"]) not in built),
                     key=lambda p: (p["name"], p["version"]))
    order = lambda ids: sorted(ids, key=lambda i: (pkgs[i]["name"], pkgs[i]["version"]))  # noqa: E731
    sums = checksums(lock_text)
    errors, entries = [], []
    for pid in order(shipped):
        try:
            entries.append(crate_entry(pkgs[pid], allow, sums))
        except LicenceError as exc:
            errors.append(str(exc))
    rows_build = []
    for pid in order(build_only):
        p = pkgs[pid]
        try:
            rows_build.append((p["name"], p["version"],
                               normalised(check_approved("%s %s" % (p["name"], p["version"]),
                                                         p.get("license") or "", allow)),
                               (p.get("repository") or "").rstrip("/")))
        except LicenceError as exc:
            errors.append(str(exc))
    rows_foreign = []
    for p in foreign:
        try:
            rows_foreign.append((p["name"], p["version"],
                                 normalised(check_approved("%s %s" % (p["name"], p["version"]),
                                                           p.get("license") or "", allow)),
                                 (p.get("repository") or "").rstrip("/")))
        except LicenceError as exc:
            errors.append(str(exc))
    if errors:
        raise LicenceError("\n".join(errors))
    rows_shipped = [(e["name"], e["version"], e["licence"], e["repository"]) for e in entries]
    adblock = dict(locked_packages(lock_text)).get("adblock")
    return {
        CRATES_FILE: render_crates(entries, rust_std_texts()),
        DOC: render_doc(DOC.read_text("utf-8"), adblock, rows_shipped, rows_build, rows_foreign),
        UBO_NOTICE: render_ubo_notice(json.loads(UBO_JSON.read_text("utf-8"))),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="compare only; exit 1 if a file differs")
    a = ap.parse_args(argv)
    try:
        new = generate()
    except LicenceError as exc:
        print("LICENCE CHECK FAILED:\n%s" % exc, file=sys.stderr)
        return 1
    except (OSError, subprocess.CalledProcessError) as exc:
        print("cannot read the Rust libraries: %s" % (getattr(exc, "stderr", "") or exc), file=sys.stderr)
        return 1
    stale = [p for p, text in new.items() if not p.is_file() or p.read_text("utf-8") != text]
    if a.check:
        for p in stale:
            print("out of date: %s (run python3 tools/third-party.py)" % p.relative_to(ROOT), file=sys.stderr)
        if not stale:
            print("licences: %d files up to date" % len(new))
        return 1 if stale else 0
    for p in stale:
        p.write_text(new[p], "utf-8")
        print("%s updated" % p.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
