#!/usr/bin/env python3
"""Deterministic recipes, tried before any AI is asked (AUTOMAT part 2; no AI here).

Some failures need no model at all: a program can see the fix. Each recipe below either produces a
change it is sure of or does nothing; what it produces is treated exactly like an AI's fix (the cheap
checks, the patch checker with the static guard, the lint, then the tests, "Nothing gets worse" and
the independent reviewers before any merge), so a recipe can never do more than an AI may. An AI is
asked only when no recipe applies, or when a recipe's result fails (it is undone, and AUTOMAT's memory
records that this recipe failed for this error, so it is not tried again for it).

1. **A fix that already solved this very error** (remembered): AUTOMAT's memory keeps the patch of a
   merged fix with the error's signature. When the same error comes back (a candidate rebuilt from
   main, another component), the patch is applied again if it still applies cleanly.
2. **A renamed symbol** (renamed): the failure names something that no longer exists ("has no
   attribute 'x'", "cannot find function `x`", "cannot import name 'x'"), and the upstream change of
   the component (tools/upstream-diff.py, upstream.json) says for sure that ``x`` was renamed to
   ``y``. Then ``x`` is replaced by ``y``, as a whole word, in the files of I.K.E. the failure
   involves.
3. **A builder's patch re-anchored** (reanchor): on a builder's branch, when one of I.K.E.'s patches
   of Dark Reader no longer finds its text, the new upstream lines the refusal shows are searched for
   the lines closest to the old anchor (difflib); a clear single match becomes the new anchor. Only
   the anchor changes: tools/builder-anchor.py checks that, and the builder itself that it is found
   exactly once.

    automat-recipes.py --workdir DIR --failure FILE --status FILE [--memory FILE --component ID]
                       [--upstream FILE] [--related FILE] [--builder ID] [--checker FILE] [--allow-adblock]
                       [--security] [--lists] [--auto] [--tier-b] [--lint] [--tried FILE] [--cargo-cmd CMD]
"""

import argparse
import ast
import difflib
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

AUTHOR = "Recipe"
RECIPES = ("remembered-fix", "renamed-symbol", "re-anchor")
MAX_RENAME_LINES = 60
MAX_FILE = 600_000
ANCHOR_RATIO = 0.84           # how close the new upstream lines must be to the old anchor (code of the same
#                               shape but another name is about 0.77: not close enough)
ANCHOR_MARGIN = 0.08          # and how much closer than any other place
MISSING = re.compile(r"has no attribute '(\w+)'|cannot find (?:function|value|type|struct|trait|macro|method) `(\w+)`"
                     r"|no (?:method|function|associated item|variant|field) named `(\w+)`"
                     r"|cannot import name '(\w+)'|unresolved import `[\w:]*?(\w+)`|name '(\w+)' is not defined"
                     r"|(\w+) is not a function|(\w+) is not defined")
IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{1,60}$")
NUMBERED = re.compile(r"^\s{0,6}(\d{1,7})  (.*)$")
SUMMARY = {
    "remembered-fix": "Lo stesso errore era già stato corretto in passato (%s): la stessa correzione è stata "
                      "applicata di nuovo da un programma, senza chiedere a nessuna AI. Passa comunque da tutti i "
                      "controlli e dai test.",
    "renamed-symbol": "Il componente aggiornato ha cambiato nome a %s: un programma ha sostituito il vecchio nome "
                      "con il nuovo nei file di I.K.E. coinvolti, senza chiedere a nessuna AI.",
    "re-anchor": "Il testo a cui era agganciata la modifica di I.K.E. \"%s\" in Dark Reader è cambiato: un "
                 "programma ha trovato le nuove righe corrispondenti e ha riagganciato la modifica (solo il punto "
                 "di aggancio), senza chiedere a nessuna AI.",
}


def _tool(name):
    spec = importlib.util.spec_from_file_location("recipe_" + name.replace("-", "_"),
                                                  Path(__file__).resolve().parent / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def error_part(failure):
    return re.split(r"\n## (?:One problem per attempt|AUTOMAT's memory of this error|What changed upstream"
                    r"|Why earlier fixes were refused|Previous automatic fix)", failure or "")[0]


def missing_names(failure):
    """The names the error says do not exist any more."""
    out = []
    for m in MISSING.finditer(error_part(failure)):
        for g in m.groups():
            if g and IDENT.match(g) and g not in out:
                out.append(g)
    return out


# --- 1. a fix that already solved this very error ------------------------------------------------------

def remembered(memory, sig, apply_check, apply):
    """(patch, summary) of the newest remembered patch for this signature that still applies, applied;
    None when there is none. apply_check(patch) -> bool, apply(patch) -> bool."""
    hints = [h for h in (memory.get("solved") or {}).get(sig, []) if h.get("patch")]
    for h in sorted(hints, key=lambda h: str(h.get("date", "")), reverse=True):
        patch = h["patch"]
        if apply_check(patch) and apply(patch):
            where = "%s, %s" % (re.sub(r"[^A-Za-z0-9._/-]", "", str(h.get("component", "?")))[:80],
                                re.sub(r"[^0-9-]", "", str(h.get("date", "?")))[:10])
            return patch, SUMMARY["remembered-fix"] % where
    return None


# --- 2. a renamed symbol -----------------------------------------------------------------------------

def rename_for(failure, upstream):
    """(old, new) when the failure misses exactly one name and the upstream change renamed it, for
    sure, to exactly one new name; None otherwise."""
    missing = missing_names(failure)
    pairs = []
    for change in (upstream or {}).get("changes") or []:
        for r in change.get("renames") or []:
            if isinstance(r, (list, tuple)) and len(r) == 2 and all(isinstance(x, str) and IDENT.match(x) for x in r):
                pairs.append((r[0], r[1]))
    found = {}
    for old, new in pairs:
        if old in missing and old != new:
            found.setdefault(old, set()).add(new)
    sure = [(old, sorted(news)[0]) for old, news in found.items() if len(news) == 1]
    return sure[0] if len(sure) == 1 else None


def renamed(failure, upstream, workdir, files):
    """(changed files, summary) after replacing the renamed name, as a whole word, in the given files of
    I.K.E.; None when no rename is sure or nothing uses the old name."""
    pair = rename_for(failure, upstream)
    if not pair:
        return None
    old, new = pair
    word = re.compile(r"(?<![\w$])%s(?![\w$])" % re.escape(old))
    changed, lines = {}, 0
    for name in files:
        path = Path(workdir) / name
        if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_FILE:
            continue
        text = path.read_text("utf-8", "replace")
        hits = sum(1 for ln in text.split("\n") if word.search(ln))
        if hits:
            changed[name] = word.sub(new, text)
            lines += hits
    if not changed or lines > MAX_RENAME_LINES:
        return None
    for name, text in changed.items():
        (Path(workdir) / name).write_text(text, "utf-8")
    return sorted(changed), SUMMARY["renamed-symbol"] % ("%s (ora %s)" % (old, new))


# --- 3. a builder's patch re-anchored -----------------------------------------------------------------

def refusal_of(failure):
    """(patch name, the new upstream lines around the anchor as [text]) of a builder's refusal, or
    (None, [])."""
    name = re.search(r"I\.K\.E\.'s patch '([^'\n]{1,80})' \(PATCHES\)", failure or "")
    block = re.search(r"## The new upstream version around the anchor\n\n```text\n(.*?)\n```", failure or "", re.S)
    if not name or not block:
        return None, []
    lines, last = [], None
    for raw in block.group(1).split("\n"):
        m = NUMBERED.match(raw)
        if not m:
            continue                              # a label ("found at line 12:"), not a line of the file
        number = int(m.group(1))
        if last is not None and number != last + 1:
            lines.append(None)                    # a gap: the lines before and after are not neighbours
        lines.append(m.group(2))
        last = number
    return name.group(1), lines


def closest(anchor, lines):
    """The lines of the new upstream closest to the old anchor: (new anchor, ratio), or (None, why).
    One clear place only: close enough (ANCHOR_RATIO) and closer than any other (ANCHOR_MARGIN)."""
    want = [ln for ln in anchor.split("\n")]
    while want and not want[-1].strip():
        want.pop()
    lead = 0
    while lead < len(want) and not want[lead].strip():
        lead += 1
    core = want[lead:]
    if not core:
        return None, "an empty anchor"
    target = "\n".join(ln.strip() for ln in core)
    scored = []
    for size in sorted({len(core), len(core) + 1, max(1, len(core) - 1)}):
        for start in range(0, len(lines) - size + 1):
            window = lines[start:start + size]
            if any(w is None or len(w) >= 200 for w in window):
                continue                          # a gap, or a line the report cut: not a place to anchor to
            ratio = difflib.SequenceMatcher(None, target, "\n".join(w.strip() for w in window), autojunk=False).ratio()
            scored.append((ratio, -abs(size - len(core)), start, size))
    if not scored:
        return None, "no whole lines of the new upstream to compare"
    scored.sort(reverse=True)
    best = scored[0]
    if best[0] >= 0.999 and best[3] == len(core):
        return None, "the anchor is still there: not a moved anchor"
    if best[0] < ANCHOR_RATIO:
        return None, "nothing close enough to the old anchor (%.2f)" % best[0]
    others = [s for s in scored[1:] if s[2] + s[3] <= best[2] or s[2] >= best[2] + best[3]]
    if others and best[0] - others[0][0] < ANCHOR_MARGIN:
        return None, "two places are about as close (%.2f and %.2f)" % (best[0], others[0][0])
    window = lines[best[2]:best[2] + best[3]]
    # each line as the old anchor wrote its own: with its indentation, or from its first character
    new = []
    for i, w in enumerate(window):
        model = core[min(i, len(core) - 1)]
        new.append(w if model[:1].isspace() else w.lstrip())
    text = "\n".join(new)
    if anchor.endswith("\n"):
        text += "\n"
    if anchor.startswith("\n"):
        text = "\n" + text
    joined = "\n".join(x for x in lines if x is not None)
    if joined.count(text.strip("\n")) != 1:
        return None, "the new anchor is not found exactly once in the lines shown"
    return text, best[0]


def literal(text, indent):
    """A Python literal of the text, one line of source per line of text."""
    parts = text.split("\n")
    pieces = [p + "\n" for p in parts[:-1]] + ([parts[-1]] if parts[-1] else [])
    if len(pieces) <= 1:
        return repr(text)
    return ("\n" + " " * indent).join(repr(p) for p in pieces)


def reanchor(failure, source):
    """(new source of the builder, patch name) with the refused patch's anchor replaced by the closest
    lines of the new upstream; (None, why) when no place is clear."""
    name, lines = refusal_of(failure)
    if not name:
        return None, "the refusal names no patch of PATCHES with its upstream lines"
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return None, "the builder does not parse"
    node = None
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "PATCHES" for t in stmt.targets) \
                and isinstance(stmt.value, ast.List):
            for item in stmt.value.elts:
                if isinstance(item, ast.Tuple) and len(item.elts) == 3 and all(
                        isinstance(e, ast.Constant) and isinstance(e.value, str) for e in item.elts) \
                        and item.elts[0].value == name:
                    node = item.elts[1]
    if node is None:
        return None, "PATCHES has no patch %r written as three plain texts" % name
    new_anchor, why = closest(node.value, lines)
    if new_anchor is None:
        return None, why
    rows = source.split("\n")
    before = "\n".join(rows[:node.lineno - 1] + [rows[node.lineno - 1][:node.col_offset]])
    after = "\n".join([rows[node.end_lineno - 1][node.end_col_offset:]] + rows[node.end_lineno:])
    return before + literal(new_anchor, node.col_offset) + after, name


# --- the recipes, one after the other -------------------------------------------------------------------

def already_failed(memory, component, sig):
    """The recipes AUTOMAT's memory says already failed for this error of this component."""
    out = set()
    for r in (memory.get("attempts") or {}).get("%s@%s" % (component, sig), []):
        if r.get("provider") == AUTHOR and r.get("outcome") != "merged" and r.get("outcome") != "published":
            out.add(str(r.get("model") or ""))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--failure", required=True)
    ap.add_argument("--status", required=True)
    ap.add_argument("--memory")
    ap.add_argument("--component", default="")
    ap.add_argument("--upstream")
    ap.add_argument("--related")
    ap.add_argument("--builder", default="")
    ap.add_argument("--checker")
    ap.add_argument("--allow-adblock", action="store_true")
    ap.add_argument("--security", action="store_true")
    ap.add_argument("--lists", action="store_true")
    ap.add_argument("--auto", action="store_true")
    ap.add_argument("--tier-b", action="store_true")
    ap.add_argument("--lint", action="store_true")
    ap.add_argument("--tried")
    ap.add_argument("--cargo-cmd", default="")
    a = ap.parse_args(argv)
    workdir = Path(a.workdir)

    def read(path):
        try:
            return Path(path).read_text("utf-8", "replace") if path else ""
        except OSError:
            return ""
    failure = read(a.failure)
    reserve, inner, mem = _tool("autofix-reserve"), _tool("autofix-inner"), _tool("automat-memory")
    reserve.AUTO["on"] = bool(a.auto)
    reserve.TIER_B["on"] = bool(a.auto and a.tier_b)
    memory = mem.load(a.memory) if a.memory else mem.empty()
    sig = mem.signature(failure)
    skip = already_failed(memory, a.component, sig)
    tried = set(read(a.tried).split())
    try:
        upstream = json.loads(read(a.upstream) or "{}")
    except ValueError:
        upstream = {}
    related = [x.strip() for x in read(a.related).splitlines() if x.strip()]

    def git_apply(patch, *flags):
        mod = reserve._checker()
        done = subprocess.run([*mod.SAFE_GIT, "-C", str(workdir), "apply", *flags, "-"], input=patch,
                              capture_output=True, text=True, check=False, env=mod.safe_git_env())
        return done.returncode == 0

    def apply_check(patch):
        return git_apply(patch, "--check")

    def apply(patch):
        return git_apply(patch)

    def changed_files():
        out = reserve._git(workdir, "status", "--porcelain", "--", ".", ":(exclude).autofix").stdout
        return sorted({line[3:].strip() for line in out.splitlines() if line[3:].strip()})

    def undo_all():
        reserve._git(workdir, "checkout", "-q", "--", ".")
        reserve._git(workdir, "clean", "-q", "-fd", "-e", ".autofix")

    status = {"result": "none", "recipe": "", "tried": [], "model": "", "message": "", "detail": ""}
    for recipe in RECIPES:
        if recipe in skip:
            status["tried"].append("%s: it already failed for this error (AUTOMAT's memory)" % recipe)
            continue
        summary = None
        try:
            if recipe == "remembered-fix" and not a.builder:
                got = remembered(memory, sig, apply_check, apply)
                summary = got[1] if got else None
            elif recipe == "renamed-symbol" and not a.builder and not a.lists:
                files = [f for f in dict.fromkeys(related + _tool("automat-route").code_files(error_part(failure)))
                         if reserve.editable(f, a.allow_adblock) and not f.startswith(("tests/", "tools/", "docs/"))]
                got = renamed(failure, upstream, workdir, files)
                summary = got[1] if got else None
            elif recipe == "re-anchor" and a.builder == "darkreader":
                target = workdir / reserve.BUILDERS["darkreader"]
                new, name = reanchor(failure, target.read_text("utf-8"))
                if new is None:
                    status["tried"].append("re-anchor: %s" % name)
                else:
                    target.write_text(new, "utf-8")
                    summary = SUMMARY["re-anchor"] % re.sub(r"[^\w .-]", "", name)[:80]
        except (OSError, ValueError, KeyError) as e:
            status["tried"].append("%s: %s" % (recipe, type(e).__name__))
            undo_all()
            continue
        files = changed_files()
        if not summary or not files:
            undo_all()
            continue
        # what the recipe made is checked as an AI's fix is: undone at the first thing a check finds
        why = ""
        fingerprint = mem.patch_hash(reserve.diff_of(workdir))
        if fingerprint in tried:
            why = "this very change already failed for this error"
        if not why:
            why = inner.cheap(workdir, files, a.cargo_cmd)[0]
        if not why and a.checker:
            code, reasons = reserve.checked(workdir, a.checker, a.related, a.allow_adblock, a.security, a.lists,
                                            a.builder)
            why = reasons if code else ""
        if not why and a.lint:
            ok, said = reserve.linted(workdir, files)
            why = "" if ok else said
        if why:
            status["tried"].append("%s: its result was refused (%s)" % (recipe, reserve.for_log(why, 200)))
            undo_all()
            continue
        auto = workdir / ".autofix"
        auto.mkdir(exist_ok=True)
        (auto / "summary.md").write_text(summary + "\n\n_(ricetta automatica \"%s\", nessuna AI)_\n" % recipe, "utf-8")
        status.update(result="ok", recipe=recipe, model=recipe, author="%s / %s" % (AUTHOR, recipe), files=files)
        break
    Path(a.status).write_text(json.dumps(status, ensure_ascii=False), "utf-8")
    print("Recipes: %s%s" % (status["result"], " (%s)" % status["recipe"] if status["recipe"] else ""))
    for line in status["tried"]:
        print("  %s" % reserve.for_log(line))
    return 0


if __name__ == "__main__":
    sys.exit(main())
