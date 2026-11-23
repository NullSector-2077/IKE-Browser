#!/usr/bin/env python3
"""Build I.K.E.'s copy of KDE's Breeze icons (LGPL-3.0-or-later), the shipped icon set "breeze"
(1.1.24, the owner's request: KDE's icons in I.K.E. even where breeze-icons is not installed; it is
not a dependency of the package).

    python3 tools/build-breeze-icons.py --src DIR [--tag vX.Y.Z] [--commit SHA] [--date YYYY-MM-DD]
                                        [--out DIR] [--licence FILE] [--root DIR]
    python3 tools/build-breeze-icons.py --names [--root DIR]      (the names I.K.E. asks for)

--src  a checkout of https://github.com/KDE/breeze-icons (KDE's own is
       https://invent.kde.org/frameworks/breeze-icons) at a release tag. The tag, the commit and
       its date are read from it with git unless given.

Only the icons I.K.E. uses are copied, never the whole theme: every name the interface asks for
(read from ike/ without running it: the first argument of icons.themed(), bundled(), theme_svg(),
QIcon.fromTheme() and of the small wrappers around them, strings, tuples of strings and the two
sides of an "a if c else b") and every name the other shipped sets provide (resources/icons/
fallback, sets/lucide, sets/phosphor, sets/phosphor-bold). For each name, the first Breeze icon
drawn in one colour, in this order: the name itself, then its "-symbolic" form, then ALIASES (a
Breeze icon for the same thing under another name); in the folders of CONTEXTS, at 22 pixels
first (the toolbar's size in Breeze), then 16, then the larger ones. Symbolic links are resolved
inside the checkout (one outside it stops the build). A name Breeze has no one-colour icon for is
listed in the record and left to the theme and I.K.E.'s own glyphs (ike/icons.py).

Each icon is changed only so that it draws in the interface's text colour like the other shipped
sets: the XML declaration, comments and the colour-scheme <style> (with an empty <defs> left
behind) are removed, the root <svg> gets fill="currentColor" when it sets no fill of its own, and
an editor's own data (Inkscape's page colours) is dropped and the lines are trimmed; the drawing is the same. An icon that holds anything but a plain drawing
(a script, an event handler, an outside reference, an embedded image, an entity) stops the build.

Writes, deterministically (sorted, no time of the build):

- ike/resources/icons/sets/breeze/<name>.svg   one per name found (old files of the set removed);
- ike/resources/icons/sets/breeze/breeze-icons.json   upstream, tag, version, commit, date,
  licence, the Breeze file each name came from and the names Breeze has no icon for;
- licenses/LICENSE.breeze-icons   Breeze's COPYING-ICONS (copyright, licence, KDE's
  clarification) followed by the complete GNU LGPL version 3 (tools/licence-texts/LGPL-3.0.txt);
  the GNU GPL version 3 it builds on is LICENSE.

The daily component check (tools/check-components.py, "breeze-icons" of components.json) runs it
on the newest release tag; only a change of the icons themselves makes an update, and an icon the
set has that the new release no longer gives stops it (the builder refused: the set stays at the
version in use).
"""

import argparse
import ast
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UPSTREAM = "https://github.com/KDE/breeze-icons"
SET_DIR = "ike/resources/icons/sets/breeze"
RECORD = "breeze-icons.json"
LICENCE = "licenses/LICENSE.breeze-icons"
LGPL_TEXT = "tools/licence-texts/LGPL-3.0.txt"
COPYING = "COPYING-ICONS"
# the other shipped sets: Breeze gives the same names
OTHER_SETS = ("ike/resources/icons/fallback", "ike/resources/icons/sets/lucide",
              "ike/resources/icons/sets/phosphor", "ike/resources/icons/sets/phosphor-bold")
# the functions of ike/ whose first argument is an icon name, or names to try in order
CALLS = ("themed", "bundled", "theme_svg", "fromTheme", "_from_theme", "icon", "_icon", "_ic", "_theme")
NAME = re.compile(r"^[a-z][a-z0-9]*(?:[-_][a-z0-9]+)*$")
CONTEXTS = ("actions", "status", "places", "devices", "emblems", "categories", "apps", "mimetypes", "preferences",
            "applets", "animations")
# a Breeze icon for the same thing under another name (Breeze has no one-colour icon of that name)
ALIASES = {
    "picture-in-picture": ("window-minimize-pip",),
    "view-source": ("format-text-code",),
    "image-x-generic": ("viewimage", "insert-image"),
    "text-x-script": ("dialog-scripts", "format-text-code"),
    "utilities-system-monitor": ("office-chart-line", "monitor"),
    "preferences-desktop-theme": ("preferences-desktop-theme-global", "games-config-theme"),
    "preferences-desktop-keyboard": ("input-keyboard",),
    "spectacle": ("camera-photo",),
}
UNSAFE = re.compile(r"<script|<foreignobject|<image\b|<iframe|<!entity|<!doctype|\son[a-z]+\s*=|javascript:"
                    r"|(?:xlink:)?href\s*=\s*[\"'](?!#)|url\(\s*[\"']?(?!#)|@import", re.I)
COLOUR = re.compile(r"#[0-9a-f]{3,8}\b|\brgba?\(|\bhsla?\(|(?:^|[\s;\"'])(?:fill|stroke|stop-color|color)\s*[:=]\s*"
                    r"[\"']?(?!none\b|currentcolor\b|inherit\b|transparent\b|url\(#)[a-z]", re.I)
MAX_BYTES = 64 * 1024


class Refused(Exception):
    """The new upstream version cannot be built as I.K.E. uses it (the set stays as it is)."""


def _strings(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        yield node.value
    elif isinstance(node, (ast.Tuple, ast.List)):
        for e in node.elts:
            yield from _strings(e)
    elif isinstance(node, ast.IfExp):
        yield from _strings(node.body)
        yield from _strings(node.orelse)


def requests(root=ROOT):
    """[(file, names)]: every icon request of ike/ with literal names, in the order of the files
    (names: the alternatives tried in order; an "a if c else b" gives one request per side)."""
    out = []
    for path in sorted((Path(root) / "ike").rglob("*.py")):
        try:
            tree = ast.parse(path.read_text("utf-8"))
        except (OSError, SyntaxError, ValueError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            f = node.func
            called = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""
            if called not in CALLS:
                continue
            arg = node.args[0]
            sides = (arg.body, arg.orelse) if isinstance(arg, ast.IfExp) else (arg,)
            for side in sides:
                names = tuple(n for n in _strings(side) if NAME.match(n))
                if names:
                    out.append((str(path.relative_to(root)), names))
    return out


def wanted(root=ROOT):
    """The sorted names the set should have: every name asked for and every name of the other sets."""
    names = {n for _f, req in requests(root) for n in req}
    for folder in OTHER_SETS:
        names |= {p.stem for p in (Path(root) / folder).glob("*.svg")}
    return sorted(names)


def _size_order(name):
    """22 pixels first, then 16, then the others from the smallest; no @2x / @3x copies."""
    if not name.isdigit():
        return None
    n = int(name)
    return (0 if n == 22 else 1 if n == 16 else 2, n)


def folders(src):
    """The icon folders of the checkout, in the order they are searched."""
    icons = Path(src) / "icons"
    out = []
    for ctx_rank, ctx in enumerate(CONTEXTS):
        base = icons / ctx
        if not base.is_dir():
            continue
        for d in base.iterdir():
            order = _size_order(d.name)
            if order is not None and d.is_dir():
                out.append((order, ctx_rank, d))
    return [d for _o, _c, d in sorted(out, key=lambda t: (t[0], t[1]))]


def _resolve(src, path):
    """The real file of a Breeze icon, inside the checkout (symbolic links followed)."""
    real = Path(os.path.realpath(path))
    top = Path(os.path.realpath(src))
    if top not in real.parents:
        raise Refused("%s points outside the checkout" % path)
    return real


def clean(text, where=""):
    """The icon as the set ships it, or raises Refused (not a plain drawing). The second value says
    whether it draws in one colour (no colour of its own once the colour-scheme style is gone)."""
    text = re.sub(r"<!DOCTYPE\s+svg[^\[<>]*>", "", text, flags=re.I)     # a plain one, no internal subset
    if UNSAFE.search(text):
        raise Refused("%s holds more than a plain drawing (a script, a handler, an outside reference, an "
                      "image or an entity)" % where)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"<\?xml[^>]*\?>", "", text)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r"<style\b[^>]*>.*?</style>", "", text, flags=re.S | re.I)
    # an editor's own data (Inkscape's page colours), not part of the drawing
    text = re.sub(r"<sodipodi:namedview\b[^>]*/>|<sodipodi:namedview\b.*?</sodipodi:namedview>"
                  r"|<metadata\b.*?</metadata>", "", text, flags=re.S)
    text = re.sub(r"<defs\b[^>]*>\s*</defs>|<defs\b[^>]*/>", "", text)
    root = re.search(r"<svg\b[^>]*>", text)
    if not root:
        raise Refused("%s is not an SVG drawing" % where)
    if not re.search(r"\sfill\s*=", root.group(0)):
        tag = root.group(0)
        text = text.replace(tag, tag[:4] + ' fill="currentColor"' + tag[4:], 1)
    lines = [line.rstrip() for line in text.strip().split("\n")]
    text = "\n".join(line for line in lines if line.strip()) + "\n"
    return text, not COLOUR.search(text)


def find(src, name, dirs=None):
    """(Breeze name, the path relative to icons/ it was found at and, after a symbolic link, the
    file's own, the shipped text) of the first one-colour icon for name, or None."""
    dirs = folders(src) if dirs is None else dirs
    icons = Path(src) / "icons"
    for candidate in (name, name + "-symbolic") + ALIASES.get(name, ()):
        for d in dirs:
            path = d / (candidate + ".svg")
            if not path.is_file():
                continue
            real = _resolve(src, path)
            if real.stat().st_size > MAX_BYTES:
                continue
            text, mono = clean(real.read_text("utf-8"), str(path.relative_to(icons)))
            if mono:
                found = str(path.relative_to(icons))
                own = str(real.relative_to(Path(os.path.realpath(icons))))
                return candidate, found if own == found else "%s -> %s" % (found, own), text
    return None


def git(src, *args):
    done = subprocess.run(["git", "-C", str(src)] + list(args), capture_output=True, text=True, check=False)
    return done.stdout.strip() if done.returncode == 0 else ""


def build(src, root=ROOT, tag="", commit="", date=""):
    """{relative path: text} of everything the builder writes (the set, its record, the licence)."""
    src = Path(src)
    if not (src / "icons").is_dir():
        raise Refused("%s has no icons/ folder (not a breeze-icons checkout)" % src)
    copying = src / COPYING
    if not copying.is_file():
        raise Refused("the checkout has no %s (Breeze's licence notice)" % COPYING)
    notice = copying.read_text("utf-8").replace("\r\n", "\n")
    if not re.search(r"Lesser\s+General\s+Public\s+License.*?version\s+3", notice, re.S | re.I):
        raise Refused("%s no longer says LGPL version 3: a person reads the new licence first" % COPYING)
    tag = tag or git(src, "describe", "--tags", "--exact-match")
    commit = commit or git(src, "rev-parse", "HEAD")
    date = date or git(src, "log", "-1", "--format=%cs")
    if not re.fullmatch(r"v?\d+(\.\d+){1,3}", tag or ""):
        raise Refused("not a release tag: %r" % tag)
    if not re.fullmatch(r"[0-9a-f]{40}", commit or "") or not re.fullmatch(r"\d{4}-\d\d-\d\d", date or ""):
        raise Refused("the commit or its date could not be read (%r, %r)" % (commit, date))
    dirs = folders(src)
    out, icons, missing = {}, {}, []
    for name in wanted(root):
        hit = find(src, name, dirs)
        if hit is None:
            missing.append(name)
            continue
        breeze_name, rel, text = hit
        icons[name] = rel
        out["%s/%s.svg" % (SET_DIR, name)] = text
    if not icons:
        raise Refused("no icon I.K.E. uses was found in the checkout")
    record = {
        "name": "Breeze icons (KDE)",
        "source": UPSTREAM,
        "tag": tag,
        "version": tag.lstrip("v"),
        "commit": commit,
        "date": date,
        "licence": "LGPL-3.0-or-later",
        "licence_file": LICENCE,
        "builder": "tools/build-breeze-icons.py",
        "changed": "only to draw in the interface's text colour: XML declaration, plain DOCTYPE, comments, "
                   "the colour-scheme <style> and an editor's own data removed, fill=\"currentColor\" on the root "
                   "<svg> when it sets none, lines trimmed",
        "icons": dict(sorted(icons.items())),
        "not_in_breeze": missing,
    }
    out["%s/%s" % (SET_DIR, RECORD)] = json.dumps(record, indent=1, ensure_ascii=False) + "\n"
    lgpl = (Path(root) / LGPL_TEXT).read_text("utf-8")
    out[LICENCE] = (
        "KDE's Breeze icons in I.K.E.\n"
        "============================\n\n"
        "Files: /usr/lib/ike-browser/%s/*.svg (and the same folder of the\n"
        "signed self-update): the icons of the set \"Breeze (KDE)\" that I.K.E. uses,\n"
        "copied from %s at\n\n"
        "  tag %s, commit %s (%s)\n\n"
        "and changed only to draw in the interface's text colour (the colour-scheme\n"
        "style removed) by tools/build-breeze-icons.py of the I.K.E. repository;\n"
        "%s next to them says which Breeze file each one is.\n"
        "The SVG files are their own source code.\n\n"
        "Below: Breeze's own notice (%s of breeze-icons), then the complete\n"
        "GNU Lesser General Public License version 3. The GNU General Public License\n"
        "version 3, which it supplements, is the file LICENSE next to this one.\n\n"
        "--- %s ---\n\n%s\n\n--- GNU Lesser General Public License, version 3 ---\n\n%s"
        % (SET_DIR, UPSTREAM, tag, commit, date, RECORD, COPYING, COPYING, notice.strip("\n"), lgpl))
    return out


def write(files, root=ROOT):
    """Write the build; the old icons of the set it no longer has are removed."""
    root = Path(root)
    folder = root / SET_DIR
    folder.mkdir(parents=True, exist_ok=True)
    keep = {Path(p).name for p in files if p.startswith(SET_DIR + "/")}
    for old in sorted(folder.glob("*.svg")):
        if old.name not in keep:
            old.unlink()
    for rel, text in sorted(files.items()):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, "utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--src", help="a breeze-icons checkout at a release tag")
    ap.add_argument("--tag", default="")
    ap.add_argument("--commit", default="")
    ap.add_argument("--date", default="")
    ap.add_argument("--root", default=str(ROOT), help="the I.K.E. repository whose names are read")
    ap.add_argument("--out", default="", help="write into this folder instead of the repository")
    ap.add_argument("--names", action="store_true", help="only print the names I.K.E. asks for")
    a = ap.parse_args(argv)
    root = Path(a.root)
    if a.names:
        print("\n".join(wanted(root)))
        return 0
    if not a.src:
        ap.error("--src is required")
    try:
        files = build(a.src, root, a.tag, a.commit, a.date)
    except Refused as e:
        print("refused: %s" % e, file=sys.stderr)
        return 1
    write(files, Path(a.out) if a.out else root)
    record = json.loads(files["%s/%s" % (SET_DIR, RECORD)])
    print("breeze-icons %s: %d icons, %d names not in Breeze (%s)" % (
        record["version"], len(record["icons"]), len(record["not_in_breeze"]),
        ", ".join(record["not_in_breeze"]) or "none"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
