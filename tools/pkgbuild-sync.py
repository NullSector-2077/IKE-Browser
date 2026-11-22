#!/usr/bin/env python3
"""The PKGBUILD's dependencies kept right by themselves (WP10 (d) of the maintenance; no AI here).

What I.K.E. needs is read from the code, never guessed:

- the inventory's findings (tools/inventory.py): a module, Qt module or
  program that ike/ uses and no package of the PKGBUILD declares ("used but
  not declared": a required import or Qt module goes into depends, an
  optional import or a program ike/ starts into optdepends, with what uses
  it), and a package needed at run time that is only in optdepends or
  makedepends ("declared too weakly": into depends);
- the minima the code declares where it needs them: a comment
  ``# needs: <package> >= <version>`` in ike/ or ike_boot.py (one package,
  one version: the version from which the code works). The PKGBUILD's
  ``'<package>>=<version>'`` follows the highest one; a minimum is only ever
  raised here, never lowered or removed.

``plan`` says what would change, ``apply`` writes it (the daily maintenance's
candidate ``automation/update/pkgbuild``: its own commit
``pkgbuild: ... (tools/pkgbuild-sync.py, no AI)``), and ``problem`` is the rule
tools/automerge.py checks before that candidate merges by itself: the PKGBUILD
differs from main's only in depends and optdepends (entries added, minima
raised, an optional entry moved into depends) and in the version lines; any
other change of the package recipe waits for a person. pacman -U installs a
new dependency when arch.yml installs the package, so the candidate's Arch
run proves it.

    pkgbuild-sync.py plan --inventory inventory.json [--root DIR] [--json OUT]
    pkgbuild-sync.py apply --inventory inventory.json [--root DIR]
    pkgbuild-sync.py problem --old FILE --new FILE
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NEEDS = re.compile(r"#\s*needs:\s*([a-z0-9][a-z0-9+._-]*)\s*>=\s*([0-9][0-9A-Za-z.:+~-]*)")
PACKAGE = re.compile(r"^[a-z0-9][a-z0-9+._-]{0,80}$")
VERSION_LINE = re.compile(r"^pkg(ver|rel)=")
COMMIT = re.compile(r"^pkgbuild: .{1,200} \(tools/pkgbuild-sync\.py, no AI\)$")


def _array(text, key):
    """(start, end, [entries]) of `key=( ... )` in a PKGBUILD (entries as written, unquoted)."""
    m = re.search(r"^%s=\(" % key, text, re.M)
    if not m:
        return None
    i, words, quote, word, comment = m.end(), [], "", None, False
    while i < len(text):
        ch = text[i]
        if comment:
            comment = ch != "\n"
        elif quote:
            if ch == quote:
                quote = ""
            else:
                word += ch
        elif ch in "'\"":
            quote, word = ch, word if word is not None else ""
        elif ch == "#" and word is None:
            comment = True
        elif ch.isspace() or ch == ")":
            if word is not None:
                words.append(word)
                word = None
            if ch == ")":
                return m.end(), i, words
        else:
            word = (word or "") + ch
        i += 1
    return None


def _name(entry):
    return re.split(r"[<>=:]", entry, maxsplit=1)[0].strip()


def _minimum(entry):
    m = re.search(r">=\s*([^\s:]+)", entry.split(":", 1)[0])
    return m.group(1) if m else ""


def vkey(v):
    return tuple(int(x) for x in re.findall(r"\d+", v or ""))


def markers(root=ROOT):
    """{package: highest version} of the `# needs: package >= version` comments in ike/ and ike_boot.py."""
    out = {}
    files = sorted((Path(root) / "ike").rglob("*.py")) + [Path(root) / "ike_boot.py"]
    for f in files:
        if not f.is_file():
            continue
        for m in NEEDS.finditer(f.read_text("utf-8", "replace")):
            if vkey(m.group(2)) > vkey(out.get(m.group(1), "")):
                out[m.group(1)] = m.group(2)
    return out


def plan(text, inventory, needs=None):
    """{"depends": [packages to add], "optdepends": [(package, why)], "move": [packages from optdepends
    into depends], "minima": {package: version}, "person": [findings no tool can settle]}."""
    deps = _array(text, "depends")
    opts = _array(text, "optdepends")
    have_dep = {_name(e): e for e in (deps[2] if deps else [])}
    have_opt = {_name(e): e for e in (opts[2] if opts else [])}
    records = {r.get("id"): r for r in (inventory or {}).get("components", [])}
    out = {"depends": [], "optdepends": [], "move": [], "minima": {}, "person": []}
    for f in (inventory or {}).get("findings", []):
        rec = records.get(f.get("component")) or {}
        pkgs = rec.get("provided_by")
        pkgs = pkgs if isinstance(pkgs, list) else [pkgs] if pkgs else []
        pkgs = [p for p in pkgs if isinstance(p, str) and PACKAGE.match(p)]
        if f.get("finding") not in ("used but not declared", "declared too weakly") or not pkgs:
            out["person"].append("%s: %s" % (f.get("finding", "?"), f.get("detail", "")[:200]))
            continue
        optional = rec.get("type") == "optional" or rec.get("kind") == "runtime-tool"
        where = ", ".join(x for x in (rec.get("origin") or [])[:2] if isinstance(x, str)) or "ike/"
        for p in pkgs:
            if f["finding"] == "declared too weakly" or (not optional and p in have_opt):
                if p not in have_dep and p not in out["move"]:
                    out["move" if p in have_opt else "depends"].append(p)
            elif optional:
                if p not in have_opt and p not in have_dep and p not in [x for x, _ in out["optdepends"]]:
                    what = rec.get("name", p)
                    out["optdepends"].append((p, "used by I.K.E. (%s in %s)" % (what, where)))
            elif p not in have_dep and p not in out["depends"]:
                out["depends"].append(p)
    for p, v in sorted((needs or {}).items()):
        if p in have_dep or p in out["depends"] or p in out["move"]:
            if vkey(v) > vkey(_minimum(have_dep.get(p, ""))):
                out["minima"][p] = v
    return out


def empty(p):
    return not (p["depends"] or p["optdepends"] or p["move"] or p["minima"])


def apply(text, p):
    """The PKGBUILD with the plan written (entries kept in their order, new ones at the end)."""
    deps = _array(text, "depends")
    if deps is None:
        raise ValueError("the PKGBUILD has no depends")
    entries = list(deps[2])
    names = [_name(e) for e in entries]
    for pkg in p["move"] + p["depends"]:
        if pkg not in names:
            entries.append(pkg)
            names.append(pkg)
    for pkg, ver in p["minima"].items():
        i = names.index(pkg)
        entries[i] = "%s>=%s" % (pkg, ver)
    body = " ".join("'%s'" % e for e in entries)
    text = text[:deps[0]] + _wrap(body, "depends=(") + text[deps[1]:]
    opts = _array(text, "optdepends")
    if opts is not None and (p["optdepends"] or p["move"]):
        kept = [e for e in opts[2] if _name(e) not in p["move"]]
        kept += ["%s: %s" % (pkg, why.replace("'", "")) for pkg, why in p["optdepends"]]
        lines = "\n            ".join("'%s'" % e for e in kept)
        text = text[:opts[0]] + lines + text[opts[1]:]
    elif p["optdepends"]:
        lines = "\n            ".join("'%s: %s'" % (pkg, why.replace("'", "")) for pkg, why in p["optdepends"])
        text = text.replace("\ninstall=", "\noptdepends=(%s)\ninstall=" % lines, 1)
    return text


def _wrap(body, lead, width=100):
    words, lines, line = body.split(" "), [], ""
    for w in words:
        if line and len(lead) + len(line) + 1 + len(w) > width:
            lines.append(line)
            line = w
        else:
            line = (line + " " + w).strip()
    lines.append(line)
    return ("\n" + " " * len(lead)).join(lines)


def problem(old, new):
    """Why the new PKGBUILD is more than this tool's change of the old one (and the version lines), or ""."""
    def masked(text):
        out = text
        for key in ("depends", "optdepends"):
            a = _array(out, key)
            if a:
                out = out[:a[0]] + "<%s>" % key + out[a[1]:]
        return "\n".join("<version>" if VERSION_LINE.match(x) else x for x in out.split("\n"))
    if masked(old) != masked(new):
        return "the PKGBUILD changed outside depends, optdepends and the version"
    a_dep, b_dep = _array(old, "depends"), _array(new, "depends")
    if not a_dep or not b_dep:
        return "depends not readable"
    a_opt, b_opt = _array(old, "optdepends"), _array(new, "optdepends")
    old_dep = {_name(e): e for e in a_dep[2]}
    new_dep = {_name(e): e for e in b_dep[2]}
    old_opt = {_name(e): e for e in (a_opt[2] if a_opt else [])}
    new_opt = {_name(e): e for e in (b_opt[2] if b_opt else [])}
    for name, entry in old_dep.items():
        if name not in new_dep:
            return "%s: removed from depends" % name
        if vkey(_minimum(new_dep[name])) < vkey(_minimum(entry)):
            return "%s: its minimum was lowered" % name
    for name, entry in new_dep.items():
        if not PACKAGE.match(name) or re.sub(r">=[^\s]+$", "", entry) != name:
            return "%s: not a plain package (with a minimum)" % entry[:60]
    for name, entry in old_opt.items():
        if name not in new_opt and name not in new_dep:
            return "%s: removed from optdepends" % name
        if name in new_opt and new_opt[name] != entry:
            return "%s: its optdepends entry changed" % name
    for name, entry in new_opt.items():
        if name not in old_opt and (not PACKAGE.match(name) or "`" in entry or "$" in entry):
            return "%s: not a plain optional package" % entry[:60]
    for x, y in zip([v for v in old.split("\n") if VERSION_LINE.match(v)],
                    [v for v in new.split("\n") if VERSION_LINE.match(v)]):
        if x != y and not re.fullmatch(r"pkg(ver=\d+\.\d+\.\d+|rel=\d+)", y):
            return "a version line that is not a version: %s" % y[:60]
    return ""


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("plan", "apply"):
        p = sub.add_parser(name)
        p.add_argument("--inventory", required=True)
        p.add_argument("--root", default=str(ROOT))
        p.add_argument("--json")
    q = sub.add_parser("problem")
    q.add_argument("--old", required=True)
    q.add_argument("--new", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "problem":
        why = problem(Path(a.old).read_text("utf-8"), Path(a.new).read_text("utf-8"))
        print(why or "only depends, optdepends and the version: accepted")
        return 1 if why else 0
    root = Path(a.root)
    inv = json.loads(Path(a.inventory).read_text("utf-8"))
    text = (root / "PKGBUILD").read_text("utf-8")
    p = plan(text, inv, markers(root))
    if a.json:
        Path(a.json).write_text(json.dumps(p, indent=1) + "\n", "utf-8")
    print(json.dumps(p, indent=1))
    if a.cmd == "apply" and not empty(p):
        (root / "PKGBUILD").write_text(apply(text, p), "utf-8")
        print("the PKGBUILD now declares what the code needs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
