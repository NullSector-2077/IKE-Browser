#!/usr/bin/env python3
"""The static guard of an AI fix: a program, not an AI, reads the change (2026-11-22).

The owner's decision of 2026-11-22 ("human intervention only for the signature; I.K.E. looks for
its updates, installs, tests and fixes them by itself on GitHub; 100% work of a team of AIs"): an AI
fix reaches main by itself when it is verified. This file is the part a program checks, used by the
automatic fix before a patch is kept (tools/check-autofix-patch.py --auto) and again by the verified
merge (tools/automerge.py), both read from main.

Two tiers, by file (tier()):

- tier B, never changed by an AI: the workflows (.github/), the tests, every tool (the guard and
  merge tools among them), the engine's sandbox and start (ike/app.py, ike_boot.py, launcher/), the
  signing and update channel (ike/updater.py, ike/__init__.py, ike/extensions.py), the package
  recipe, what comes from others or is generated (Dark Reader, uBlock Origin's scriptlets, the icon
  sets, the Cargo files, vendor/), YouTube's ad blocking (videoads.js, videorelay.js, mediahook.js,
  Scriptlets.host_scripts) and anything this file does not know. An update that needs one of them
  stays open and is tried again every day ("retrying", with a note for the owner): no AI touches it.
- tier A, protected code an AI may fix: I.K.E.'s ad-blocking adapter (ike/blocker.py,
  ike/scriptlets.py, ike-adblock/src/*.rs, vendor/adblock/__init__.py), the modules that decide the
  user's safety (PROTECTED_PY), I.K.E.'s own page scripts (fingerprint.js and the others) and the
  look-alike table. It merges by itself only with this guard, the two independent AI reviews
  (tools/ai-review.py), every required test category ("no-regression" among them) and no test
  changed.

The rules of a tier-A file, each one testable:

1. **Additive only** (Python, by the syntax trees of the file before and after: additive_problems).
   Every statement of the old file is still there, unchanged, in the same order and at the same
   nesting; the new file only has more statements between them. So no branch, condition, return or
   raise is removed or changed: an `if`, `while`, `for`, `with`, `try` or `match` keeps its header
   (its condition) and every statement of each of its bodies, a `try` keeps its handlers in order
   (new ones only after them), a function or class keeps its name, arguments and decorators.
2. **No entry leaves a table.** An assignment to the same name may only grow: a list or tuple keeps
   its elements in order, a set its members, a dict its keys with their values, a text its lines in
   order (a block of filter rules), `frozenset({...})`-like calls their literal. Any other changed
   value is a removed statement.
3. **No new way out of old code.** A new statement may not leave a function or a loop before the
   old statements that follow it: a new `return`, `raise`, `break`, `continue` or exit call is
   allowed only under a new condition that is not a constant, or as the last statement of a
   function. A new statement may not give a constant to a name the old function already sets, nor
   delete it (the flag that says "blocked" overridden after the fact).
3b. **No old name is bound again** (_rebinds, part 2 of AUTOMAT). A new statement may not define,
   import, assign, loop over or delete a name the old module or class already binds (a second
   `def allowed(...)` at the end of the file would silently replace the old one, `TABLE = TABLE[:1]`
   would empty a table after it was written), may not shadow an old function, class or import inside a
   function, and may not change an old module-level object through an attribute, an index or a
   method that removes entries (`K.method = ...`, `TABLE[k] = ...`, `TABLE.clear()`).
4. **Nothing new that reaches out** (capability_problems): no new import but a few harmless modules
   (SAFE_IMPORTS), no more calls than before of eval, exec, compile, __import__, open, os.system and
   the process, file-writing, loading and network calls (RISKY), and no new text that looks like an
   address or a host name (new_hosts).
5. **Page scripts, Rust and the JSON table** have no Python tree: their old lines of code must all
   still be there, in order (line_additive); a new line may not leave old code (a `return`, `throw`,
   `break` or `continue` outside a block the change itself opens), give a constant to a name the old
   file has (a protection switched off), or reach out (JS_RISKY, RUST_RISKY, a new address). The
   JSON table may only grow (json_superset). On a candidate of the engine the wrapper follows the
   engine's new interface: there the additive rule does not apply to it, the others do.
7. **The component manifest** (components.json) may get a new entry for a file from upstream that has
   none (the inventory guard says which): only added entries, a plain download from an allowed host of
   a file that is already in the repository with the sha256 the entry declares, never a build command
   (tools/component-manifest.py ai_entry_problems).
6. **Small**: at most MAX_FILES files and MAX_LINES changed lines in all the AI commits of a pull
   request; no file added, removed or renamed.

What this does not prove: a fix can weaken a protection by adding code (a new condition that is
true too often, a new entry in a list of exceptions). That is what the differential check
("Nothing gets worse", category no-regression), the whole suite and the two reviewers are for.

**Tier B behind the owner's switch** (part 2 of AUTOMAT). With the repository variable
``AUTOMAT_TIER_B`` set to ``on`` by the owner (only the owner can: a setting of the repository, never
a file), and only then, callers pass ``tier_b=True`` and a few tier-B files open in their narrowest
form, judged by tools/tier-b.py: a workflow where nothing changes but a pinned version, and
ike/app.py, ike/updater.py and ike_boot.py under the additive rule above plus fixed invariants (the
signature check, the engine's protection lists only grow, the 24-hour update check). Everything
else of tier B stays never an AI's, and so do the rule-keepers (this file, the merge, the reviewers,
"Nothing gets worse", the patch checker, ChatGPT's guard). Off, the default: nothing changes.

    fix-guard.py --base REV --head REV [--repo DIR] [--engine-candidate] [FILE ...]
"""

import argparse
import ast
import collections
import json
import re
import subprocess
import sys
from pathlib import Path

MAX_FILES = 8          # of all the AI commits of one pull request (one attempt: 5, tools/check-autofix-patch.py)
MAX_LINES = 400

# --- tiers -------------------------------------------------------------------------------------

YOUTUBE_FILES = ("ike/resources/videoads.js", "ike/resources/videorelay.js", "ike/resources/mediahook.js")
TIER_B_PREFIXES = (".github/", "tests/", "tools/", "launcher/", "licenses/", "vendor/", "ike/resources/")
TIER_B_FILES = {
    "ike/app.py": "the engine's sandbox and start",
    "ike_boot.py": "the start of I.K.E. and the choice of the signed update",
    "ike/updater.py": "the update channel and its signature checks",
    "ike/__init__.py": "the version and the minimum system (only the automation's own raise)",
    "ike/extensions.py": "the signature check of extension packages",
    "PKGBUILD": "the package recipe", "PKGBUILD.in": "the package recipe",
    "ike-browser.install": "the package recipe", "pyproject.toml": "what decides which tests run",
    "ike-adblock/Cargo.toml": "the engine's crates", "ike-adblock/Cargo.lock": "the engine's crates",
    "ike-adblock/deny.toml": "the exceptions to advisories (a person's, with a reason)",
    "docs/THIRD-PARTY.md": "generated by tools/third-party.py",
}
# the modules where one line decides the user's safety (tools/automerge.py PERSON_FILES, without tier B)
PROTECTED_PY = ("ike/blocker.py", "ike/scriptlets.py", "vendor/adblock/__init__.py", "ike/__main__.py",
                "ike/config.py", "ike/osinfo.py", "ike/passwords.py", "ike/userscripts.py", "ike/webview.py",
                "ike/shields.py", "ike/doh.py", "ike/sitedata.py", "ike/drm.py", "ike/chromever.py")
# I.K.E.'s own page scripts (the others under ike/resources/ come from upstream or are YouTube's)
PROTECTED_JS = ("ike/resources/fingerprint.js", "ike/resources/consent.js", "ike/resources/darkmode.js",
                "ike/resources/passwords.js", "ike/resources/reader.js", "ike/resources/userscript.js")
PROTECTED_JSON = ("ike/resources/lookalike.json",)
PROTECTED_RS = re.compile(r"^ike-adblock/src/[A-Za-z0-9_/]+\.rs$")
# the wrapper of the engine: on a candidate of the engine it follows the engine's new interface
WRAPPER = ("vendor/adblock/__init__.py", "ike/blocker.py")
# YouTube's ad blocking inside a tier-A file: never by an AI (the owner's rule, CLAUDE.md)
TIER_B_FUNCTIONS = {"ike/scriptlets.py": ("Scriptlets.host_scripts",)}


MANIFEST = "components.json"       # the component manifest: an AI may add a missing entry (rule 7)
# tier B in its narrowest form, only with the owner's switch AUTOMAT_TIER_B (tools/tier-b.py judges them)
TIER_B_OPEN_PY = ("ike/app.py", "ike/updater.py", "ike_boot.py")
TIER_B_OPEN_WORKFLOW = re.compile(r"^\.github/(?:workflows/[A-Za-z0-9_.-]+\.yml|actions/[A-Za-z0-9_./-]+/action\.yml)$")


def tier_b_open(path):
    """A tier-B file an AI may change in its narrowest form when the owner turned AUTOMAT_TIER_B on."""
    path = str(path or "")
    return path in TIER_B_OPEN_PY or (bool(TIER_B_OPEN_WORKFLOW.match(path)) and ".." not in path)


def _tool(name):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), Path(__file__).resolve().parent /
                                                  (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def tier(path):
    """"A" (protected code an AI may fix under this guard), "B" (never changed by an AI) or "" (an
    ordinary interface module or document, under the rules it already had)."""
    path = str(path or "")
    if path == MANIFEST:
        return "A"
    if path in PROTECTED_PY or path in PROTECTED_JS or path in PROTECTED_JSON or PROTECTED_RS.match(path):
        return "A"
    if path in TIER_B_FILES or path.startswith(TIER_B_PREFIXES) or path.startswith("ike-adblock/"):
        return "B"
    if (path.startswith("ike/") and path.endswith(".py") and path.count("/") == 1) or \
            (path.startswith("docs/") and path.endswith(".md")):
        return ""
    return "B"                                   # not known here: never by an AI


def tier_b_reason(path):
    """Why the file is tier B, in a few words."""
    if path in TIER_B_FILES:
        return TIER_B_FILES[path]
    if path in YOUTUBE_FILES:
        return "YouTube's ad blocking (the owner's rule)"
    for prefix, why in ((".github/", "a workflow"), ("tests/", "a test"), ("tools/", "a tool of the automation"),
                        ("launcher/", "the launcher"), ("vendor/", "the vendored engine"),
                        ("ike-adblock/", "the engine's package"), ("licenses/", "the licences"),
                        ("ike/resources/", "a bundled resource: from upstream, generated or not code")):
        if path.startswith(prefix):
            return why
    return "not a file this guard knows"


# --- Python: additive only ---------------------------------------------------------------------

def _dump(node):
    return ast.dump(node, annotate_fields=False, include_attributes=False) if node is not None else ""


def _header(node):
    """What a compound statement must keep: its kind and its condition."""
    kind = type(node).__name__
    if isinstance(node, (ast.If, ast.While)):
        return kind, _dump(node.test)
    if isinstance(node, (ast.For, ast.AsyncFor)):
        return kind, _dump(node.target), _dump(node.iter)
    if isinstance(node, (ast.With, ast.AsyncWith)):
        return (kind,) + tuple(_dump(i) for i in node.items)
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return (kind, node.name, _dump(node.args), _dump(node.returns)) + tuple(_dump(d) for d in node.decorator_list)
    if isinstance(node, ast.ClassDef):
        return (kind, node.name) + tuple(_dump(x) for x in node.bases + node.keywords + node.decorator_list)
    if isinstance(node, ast.Match):
        return (kind, _dump(node.subject)) + tuple(_dump(c.pattern) + "|" + _dump(c.guard) for c in node.cases)
    if isinstance(node, (ast.Try, getattr(ast, "TryStar", ast.Try))):
        return (kind,)
    return None


def _bodies(node):
    """[(label, statements)] of a compound statement."""
    if isinstance(node, ast.Match):
        return [("case %d" % (i + 1), c.body) for i, c in enumerate(node.cases)]
    out = [(name, getattr(node, name)) for name in ("body", "orelse", "finalbody") if getattr(node, name, None)]
    return out


def _lines_superset(old, new):
    """The old text's lines are all in the new text, in order."""
    it = iter(new.split("\n"))
    return all(any(line == other for other in it) for line in old.split("\n"))


def _subsequence(old, new):
    it = iter(new)
    return all(any(x == y for y in it) for x in old)


def _grows(old, new):
    """The value of an assignment only grew (rule 2)."""
    if _dump(old) == _dump(new):
        return True
    if type(old) is not type(new):
        return False
    if isinstance(old, ast.Constant):
        return isinstance(old.value, str) and isinstance(new.value, str) and "\n" in old.value \
            and _lines_superset(old.value, new.value)
    if isinstance(old, (ast.List, ast.Tuple)):
        return _subsequence([_dump(e) for e in old.elts], [_dump(e) for e in new.elts])
    if isinstance(old, ast.Set):
        return {_dump(e) for e in old.elts} <= {_dump(e) for e in new.elts}
    if isinstance(old, ast.Dict):
        have = {_dump(k): v for k, v in zip(new.keys, new.values)}
        return all(_dump(k) in have and _grows(v, have[_dump(k)]) for k, v in zip(old.keys, old.values))
    if isinstance(old, ast.Call) and isinstance(old.func, ast.Name) and old.func.id in (
            "frozenset", "set", "tuple", "list", "dict", "sorted") and _dump(old.func) == _dump(new.func) \
            and len(old.args) == len(new.args) == 1 and not old.keywords and not new.keywords:
        return _grows(old.args[0], new.args[0])
    return False


def _same(old, new):
    """An old statement and the new statement that is still it (compound ones: by their header)."""
    if type(old) is not type(new):
        return False
    head = _header(old)
    if head is not None:
        return head == _header(new)
    if isinstance(old, ast.Assign) and [_dump(t) for t in old.targets] == [_dump(t) for t in new.targets]:
        return _grows(old.value, new.value)
    if isinstance(old, ast.AnnAssign) and _dump(old.target) == _dump(new.target) and old.value and new.value \
            and _dump(old.annotation) == _dump(new.annotation):
        return _grows(old.value, new.value)
    return _dump(old) == _dump(new)


EXIT_CALLS = {"exit", "quit", "_exit", "abort"}


def _const_truth(test):
    """True or False for a condition that is a constant, None for a real one."""
    if isinstance(test, ast.Constant):
        return bool(test.value)
    if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
        inner = _const_truth(test.operand)
        return None if inner is None else not inner
    if isinstance(test, (ast.Tuple, ast.List, ast.Set, ast.Dict)):
        return bool(getattr(test, "elts", None) or getattr(test, "keys", None))
    if isinstance(test, ast.BoolOp):
        truths = [_const_truth(v) for v in test.values]
        if isinstance(test.op, ast.Or) and any(t is True for t in truths):
            return True
        if isinstance(test.op, ast.And) and any(t is False for t in truths):
            return False
        return None if None in truths else truths[-1]
    if isinstance(test, ast.Compare) and len(test.ops) == 1 and _dump(test.left) == _dump(test.comparators[0]):
        return isinstance(test.ops[0], (ast.Eq, ast.Is, ast.LtE, ast.GtE))
    return None


def _leaves(stmts, in_loop=False):
    """These new statements leave the old code around them whatever happens (rule 3)."""
    for s in stmts:
        if isinstance(s, (ast.Return, ast.Raise)):
            return True
        if isinstance(s, (ast.Break, ast.Continue)) and not in_loop:
            return True
        if isinstance(s, ast.Expr) and isinstance(s.value, ast.Call):
            f = s.value.func
            if (f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")) in EXIT_CALLS:
                return True
        if isinstance(s, ast.If):
            truth = _const_truth(s.test)
            if (truth is True and _leaves(s.body, in_loop)) or (truth is False and _leaves(s.orelse, in_loop)) or \
                    (_leaves(s.body, in_loop) and _leaves(s.orelse, in_loop)):
                return True
        elif isinstance(s, (ast.For, ast.AsyncFor, ast.While)):
            if _leaves(s.body, True) or _leaves(s.orelse, in_loop):
                return True
        elif isinstance(s, (ast.With, ast.AsyncWith)):
            if _leaves(s.body, in_loop):
                return True
        elif isinstance(s, (ast.Try, getattr(ast, "TryStar", ast.Try))):
            if _leaves(s.body, in_loop) or _leaves(s.finalbody, in_loop):
                return True
        elif isinstance(s, ast.Match):
            if s.cases and all(_leaves(c.body, in_loop) for c in s.cases) and any(
                    isinstance(c.pattern, ast.MatchAs) and c.pattern.pattern is None and c.guard is None
                    for c in s.cases):
                return True
    return False


def _targets(stmts):
    """The names and attributes the statements assign (not inside nested functions or classes)."""
    out = set()
    todo = list(stmts)
    while todo:
        s = todo.pop()
        if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        if isinstance(s, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            for t in (s.targets if isinstance(s, ast.Assign) else [s.target]):
                for sub in ast.walk(t):
                    if isinstance(sub, (ast.Name, ast.Attribute, ast.Subscript)):
                        out.add(_dump(sub))
        todo.extend(ast.iter_child_nodes(s))
    return out


def _is_constant(value):
    if isinstance(value, ast.Constant):
        return True
    if isinstance(value, (ast.List, ast.Tuple, ast.Set, ast.Dict)):
        return not (getattr(value, "elts", None) or getattr(value, "keys", None))
    if isinstance(value, ast.UnaryOp):
        return _is_constant(value.operand)
    return isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and not value.args and \
        not value.keywords and value.func.id in ("set", "list", "dict", "tuple", "frozenset", "str", "bool", "int")


def _overrides(stmt, old_targets):
    """A new statement that gives a constant to, or deletes, something the old code sets."""
    todo = [stmt]
    while todo:
        s = todo.pop()
        if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)) and s is not stmt:
            continue
        if isinstance(s, (ast.Global, ast.Nonlocal)):
            return "a global or nonlocal statement"
        if isinstance(s, ast.Delete):
            for t in s.targets:
                if _dump(t) in old_targets:
                    return "deletes %s, which the old code sets" % ast.unparse(t)[:40]
        if isinstance(s, (ast.Assign, ast.AnnAssign, ast.AugAssign)) and s.value is not None and _is_constant(s.value):
            for t in (s.targets if isinstance(s, ast.Assign) else [s.target]):
                for sub in ([t] if not isinstance(t, (ast.Tuple, ast.List)) else t.elts):
                    if _dump(sub) in old_targets:
                        return "gives a constant to %s, which the old code sets" % ast.unparse(sub)[:40]
        todo.extend(ast.iter_child_nodes(s))
    return ""


def _line(node):
    return getattr(node, "lineno", 0)


# --- no old name is bound again (rule 3b) ---------------------------------------------------------

# methods that take entries out of a table or change one in place
REMOVING_METHODS = {"clear", "pop", "popitem", "remove", "discard", "difference_update", "intersection_update",
                    "symmetric_difference_update", "__delitem__", "__setitem__", "__setattr__", "__delattr__",
                    "__init__", "sort", "reverse", "insert"}


def _target_names(target):
    """The plain names a binding target binds (a tuple or a starred target: each of them)."""
    if isinstance(target, (ast.Attribute, ast.Subscript)):
        return set()
    return {n.id for n in ast.walk(target) if isinstance(n, ast.Name)}


def _bindings(stmts, callables=None):
    """The names the statements bind in their own scope (not inside nested functions or classes): defs,
    classes, imports, assignments, loop and with targets, handlers' names, walrus targets. callables,
    when given, gets the names bound by a def, a class or an import."""
    out = set()
    todo = list(stmts)
    while todo:
        s = todo.pop()
        if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(s.name)
            if callables is not None:
                callables.add(s.name)
            todo.extend(s.decorator_list)
            continue
        if isinstance(s, ast.Lambda):
            continue
        if isinstance(s, (ast.Import, ast.ImportFrom)):
            for a in s.names:
                name = a.asname or a.name.split(".")[0]
                out.add(name)
                if callables is not None:
                    callables.add(name)
        elif isinstance(s, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            for t in (s.targets if isinstance(s, ast.Assign) else [s.target]):
                out |= _target_names(t)
        elif isinstance(s, (ast.For, ast.AsyncFor, ast.comprehension)):
            out |= _target_names(s.target)
        elif isinstance(s, ast.withitem) and s.optional_vars is not None:
            out |= _target_names(s.optional_vars)
        elif isinstance(s, ast.ExceptHandler) and s.name:
            out.add(s.name)
        elif isinstance(s, ast.NamedExpr):
            out |= _target_names(s.target)
        elif isinstance(s, ast.Delete):
            for t in s.targets:
                out |= _target_names(t)
        elif isinstance(s, (ast.MatchAs, ast.MatchStar)) and s.name:
            out.add(s.name)
        todo.extend(ast.iter_child_nodes(s))
    return out


def _base_name(node):
    """The name an attribute or index chain starts from (K.m, TABLE[k].x -> K, TABLE), or ""."""
    while isinstance(node, (ast.Attribute, ast.Subscript)):
        node = node.value
    return node.id if isinstance(node, ast.Name) else ""


def _rebinds(stmt, kind, names, ctx):
    """Why a new statement binds again, shadows or changes in place something the old code defines, or
    "". kind: the scope the statement is added to ("module", "class" or "function"); names: what the old
    code binds in that scope; ctx: {"module": the old module's names, "callables": its defs, classes and
    imports, "locals": the old names of the function the statement is added to}."""
    module, callables = ctx.get("module", set()), ctx.get("callables", set())
    # 1. in the scope itself: the names the new statement binds
    taken = names if kind in ("module", "class") else (callables - ctx.get("locals", set()))
    again = sorted(_bindings([stmt]) & taken)
    if again:
        return "binds %s again, which the old code already defines (a later definition replaces it)" % again[0]
    # 2. anywhere inside it (a new function runs when the new code calls it): an old module-level object
    #    changed through an attribute, an index or a method that removes entries
    local = (_bindings([stmt]) | ctx.get("locals", set())) if kind == "function" else set()
    for node in ast.walk(stmt):
        targets = []
        if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        elif isinstance(node, ast.Delete):
            targets = node.targets
        for t in targets:
            for sub in ([t] if not isinstance(t, (ast.Tuple, ast.List)) else t.elts):
                base = _base_name(sub) if isinstance(sub, (ast.Attribute, ast.Subscript)) else ""
                if base and base in module and base not in local and base not in ("self", "cls"):
                    return "changes %s in place (%s), which the old code defines" % (base, ast.unparse(sub)[:50])
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and \
                node.func.attr in REMOVING_METHODS:
            base = _base_name(node.func.value)
            if base and base in module and base not in local and base not in ("self", "cls"):
                return "calls %s.%s(), which takes entries out of or rewrites what the old code defines" % (
                    base, node.func.attr)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node is not stmt \
                and kind != "class" and node.name in callables:
            return "defines %s again inside new code, which hides the old one" % node.name
    return ""


def _additive(old, new, where, tail_ok, old_targets, out, scope=None, ctx=None):
    """The new statements are the old ones, in order, with more between them (rules 1 to 3b)."""
    kind, names = scope or ("function", set())
    ctx = ctx or {}
    j = 0
    pairs, inserted = [], []
    for o in old:
        k = j
        while k < len(new) and not _same(o, new[k]):
            k += 1
        if k == len(new):
            out.append("%s: line %d of the old file is removed or changed (%s): this file may only get new "
                       "statements" % (where, _line(o), ast.unparse(o).split("\n")[0][:70]))
            return
        inserted += [(n, False) for n in new[j:k]]
        pairs.append((o, new[k]))
        j = k + 1
    inserted += [(n, tail_ok and i == len(new) - 1) for i, n in enumerate(new[j:], j)]
    for n, at_tail in inserted:
        if _leaves([n]) and not (at_tail and isinstance(n, (ast.Return, ast.Raise))):
            out.append("%s: line %d of the new file leaves the old code before it ran (%s): a new return, raise, "
                       "break or continue needs a new condition that is not a constant" % (
                           where, _line(n), ast.unparse(n).split("\n")[0][:70]))
        why = _overrides(n, old_targets) or _rebinds(n, kind, names, ctx)
        if why:
            out.append("%s: line %d of the new file %s" % (where, _line(n), why))
    for o, n in pairs:
        if _header(o) is None:
            continue
        inner = "%s > %s" % (where, getattr(o, "name", None) or "%s at line %d" % (type(o).__name__.lower(), _line(o)))
        is_scope = isinstance(o, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        targets = _targets(o.body) if is_scope else old_targets
        below, below_ctx = (kind, names), ctx
        if isinstance(o, ast.ClassDef):
            below = ("class", _bindings(o.body))
        elif is_scope:
            mine = _bindings(o.body) | {a.arg for a in ast.walk(o.args) if isinstance(a, ast.arg)}
            below, below_ctx = ("function", mine), dict(ctx, locals=mine)
        if isinstance(o, (ast.Try, getattr(ast, "TryStar", ast.Try))):
            if len(n.handlers) < len(o.handlers) or any(
                    _dump(a.type) != _dump(b.type) or a.name != b.name for a, b in zip(o.handlers, n.handlers)):
                out.append("%s: the handlers of the try at line %d are removed, changed or reordered" % (
                    where, _line(o)))
                continue
            for a, b in zip(o.handlers, n.handlers):
                _additive(a.body, b.body, inner + " > except", False, targets, out, below, below_ctx)
            for b in n.handlers[len(o.handlers):]:
                if _leaves(b.body) is False and not any(isinstance(x, ast.Raise) for x in ast.walk(b)) and \
                        _dump(b.type) in ("", _dump(ast.Name("Exception")), _dump(ast.Name("BaseException"))):
                    out.append("%s: a new handler at line %d catches every error of old code and goes on" % (
                        where, _line(b)))
        old_parts, new_parts = dict(_bodies(o)), dict(_bodies(n))
        for label, body in old_parts.items():
            is_tail = isinstance(o, (ast.FunctionDef, ast.AsyncFunctionDef)) and label == "body"
            _additive(body, new_parts.get(label, []), inner, is_tail, targets, out, below, below_ctx)
        for label, body in new_parts.items():
            if label not in old_parts:           # a new else or finally of an old statement
                if _leaves(body):
                    out.append("%s: a new %s at line %d leaves the old code that follows" % (
                        inner, "else" if label == "orelse" else label, _line(body[0])))
                for s in body:
                    why = _overrides(s, targets) or _rebinds(s, below[0], below[1], below_ctx)
                    if why:
                        out.append("%s: line %d of the new file %s" % (inner, _line(s), why))


def _function_ranges(tree, names):
    """{qualified name: dump} of the named functions (Class.method)."""
    out = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    out["%s.%s" % (node.name, sub.name)] = _dump(sub)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out[node.name] = _dump(node)
    return {n: out.get(n) for n in names}


def additive_problems(name, old, new):
    """Why the new Python source is more than the old one with statements added (a list)."""
    try:
        a, b = ast.parse(old), ast.parse(new)
    except (SyntaxError, ValueError):
        return ["%s: the file does not parse" % name]
    out = []
    frozen = TIER_B_FUNCTIONS.get(name, ())
    if frozen and _function_ranges(a, frozen) != _function_ranges(b, frozen):
        out.append("%s: %s is YouTube's ad blocking: never changed by an AI (tier B)" % (name, ", ".join(frozen)))
    callables = set()
    module = _bindings(a.body, callables)
    _additive(a.body, b.body, name, False, _targets(a.body), out, ("module", module),
              {"module": module, "callables": callables})
    return out


# --- Python: nothing new that reaches out ------------------------------------------------------

SAFE_IMPORTS = {"re", "json", "typing", "functools", "itertools", "collections", "dataclasses", "enum", "math",
                "string", "fnmatch", "unicodedata", "ipaddress", "datetime", "hashlib", "urllib.parse", "html",
                "textwrap", "operator", "abc", "contextlib", "bisect", "heapq", "codecs"}
RISKY_NAMES = {"eval", "exec", "compile", "__import__", "open", "getattr", "setattr", "delattr", "globals",
               "locals", "vars", "input", "breakpoint", "memoryview"}
RISKY_METHODS = {"system", "popen", "spawn", "Popen", "run", "call", "check_output", "check_call", "startDetached",
                 "execv", "execve", "execl", "execvp", "fork", "kill", "write_text", "write_bytes", "unlink", "rmtree",
                 "remove", "rmdir", "rename", "mkdir", "makedirs", "chmod", "chown", "symlink_to", "hardlink_to",
                 "touch", "open", "urlopen", "urlretrieve", "connect", "create_connection", "import_module",
                 "exec_module", "load_source", "runJavaScript", "setUrlRequestInterceptor", "setFeaturePermission",
                 "setHttpUserAgent", "setProxy", "setRawHeader", "environ", "putenv", "getenv", "dlopen", "CDLL"}
RISKY_MODULES = {"os", "sys", "subprocess", "socket", "ssl", "http", "urllib", "requests", "ctypes", "importlib",
                 "pickle", "marshal", "shutil", "tempfile", "threading", "multiprocessing", "asyncio", "signal",
                 "builtins", "atexit", "inspect", "gc", "QProcess", "QNetworkAccessManager", "QNetworkRequest",
                 "QTcpSocket", "QUdpSocket", "QWebSocket", "QLibrary", "QFile", "QSaveFile"}
# a text that names an address or a host: a scheme, or a dotted name that does not end like a file
URL = re.compile(r"[a-z][a-z0-9+.-]*://|\bwss?:|\bdata:|\bjavascript:", re.I)
HOST = re.compile(r"(?<![\w./@-])(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+([a-z]{2,24})(?![\w-])", re.I)
NOT_A_TLD = {"py", "js", "json", "txt", "html", "htm", "css", "svg", "png", "jpg", "jpeg", "gif", "ico", "dat",
             "rs", "md", "toml", "lock", "so", "zst", "log", "tmp", "bak", "ini", "conf", "xml", "desktop", "qm",
             "ts", "mjs", "sh", "db", "sqlite", "key", "pem", "sig", "zip", "gz", "tar", "pkg", "woff", "woff2",
             "prototype", "length", "call", "apply", "bind", "value", "style", "data", "id", "name", "get", "set"}
IP = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])|\[[0-9a-f:]{3,}\]", re.I)


def hosts_in(text):
    """The addresses and host names a text names (a Counter)."""
    out = collections.Counter()
    for m in URL.finditer(text or ""):
        out["an address (%s)" % m.group(0).lower()] += 1
    for m in HOST.finditer(text or ""):
        if m.group(1).lower() not in NOT_A_TLD:
            out["a host name (%s)" % m.group(0).lower()] += 1
    for m in IP.finditer(text or ""):
        out["a network address (%s)" % m.group(0)] += 1
    return out


def capabilities(source):
    """A Counter of what a Python source can reach, or None when it does not parse (rule 4)."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return None
    out = collections.Counter()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name not in SAFE_IMPORTS:
                    out["import %s" % a.name] += 1
        elif isinstance(node, ast.ImportFrom):
            mod = "." * node.level + (node.module or "")
            for a in node.names:
                if mod not in SAFE_IMPORTS:
                    out["from %s import %s" % (mod, a.name)] += 1
        elif isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name) and f.id in RISKY_NAMES:
                out["a call of %s()" % f.id] += 1
            elif isinstance(f, ast.Attribute) and f.attr in RISKY_METHODS:
                out["a call of .%s()" % f.attr] += 1
        elif isinstance(node, ast.Attribute) and node.attr in ("environ", "__dict__", "__globals__", "__builtins__",
                                                               "__class__", "__subclasses__", "modules", "argv"):
            out["the attribute .%s" % node.attr] += 1
        elif isinstance(node, ast.Name) and node.id in RISKY_MODULES:
            out["the name %s" % node.id] += 1
        elif isinstance(node, ast.Constant) and isinstance(node.value, (str, bytes)):
            text = node.value.decode("latin-1") if isinstance(node.value, bytes) else node.value
            out.update(hosts_in(text))
    return out


def capability_problems(name, old, new):
    a, b = capabilities(old), capabilities(new)
    if a is None or b is None:
        return ["%s: the file does not parse" % name]
    return ["%s: the change adds %s (nothing new may reach the network, the system, files or other code)"
            % (name, what) for what in sorted(b - a)]


# --- page scripts, Rust, the JSON table --------------------------------------------------------

JS_RISKY = re.compile(r"\bfetch\s*\(|XMLHttpRequest|WebSocket|EventSource|sendBeacon|importScripts|\bimport\s*\("
                      r"|\beval\s*\(|\bFunction\s*\(|document\.write|\.src\s*=|\.href\s*=|location\s*(?:\.\w+\s*)?="
                      r"|postMessage|localStorage|sessionStorage|indexedDB|document\.cookie|window\.open|__IKE_CFG__"
                      r"|qt\.webChannelTransport|new\s+Worker|serviceWorker|\bdebugger\b")
RUST_RISKY = re.compile(r"\bunsafe\b|std::(process|net|fs|env|os|ffi|ptr|mem::transmute)|\bCommand\b"
                        r"|include_(bytes|str)!|\benv!|option_env!|\basm!|global_asm!|\bextern\b|#\s*\[\s*link"
                        r"|#\s*\[\s*no_mangle|\blibc\b|\bTcp|\bUdp|\bFile::|\bOpenOptions\b|\bprintln!"
                        r"|\bpanic!|\bunreachable!|\btodo!|\bunimplemented!|#\s*\[\s*cfg|\bstd::process::exit")
EXIT_WORD = re.compile(r"(?<![\w$.])(return|throw|break|continue)(?![\w$])")
CONSTANT_ASSIGN = re.compile(r"^\s*(?:var\s+|let\s+|const\s+|let\s+mut\s+)?([\w$.\[\]'\"]+)\s*(?::[^=]+)?=\s*"
                             r"(?:false|true|null|undefined|None|!0|!1|0|1|''|\"\"|'off'|\"off\"|\{\s*\}|\[\s*\])\s*[;,]?\s*$")


# a declaration (JavaScript and Rust), and an assignment to a name, a property or an index
DECLARES = re.compile(r"^\s*(?:export\s+)?(?:pub(?:\([a-z]+\))?\s+)?(?:async\s+)?"
                      r"(function\s*\*?\s+|var\s+|let\s+mut\s+|let\s+|const\s+|static\s+(?:mut\s+)?|fn\s+)"
                      r"([A-Za-z_$][\w$]*)")
ASSIGNS = re.compile(r"^\s*(?:\}\s*)?([A-Za-z_$][\w$]*)((?:\s*\.\s*[\w$]+|\s*\[[^\]]*\])*)\s*"
                     r"(?:[-+*/%|&^]|\|\||&&|\?\?|<<|>>>?)?=(?![=>])")


def declared(text):
    """The names a script declares (function, var, let, const, fn, static)."""
    return {m.group(2) for m in (DECLARES.match(_strip_strings(ln)) for ln in (text or "").split("\n")) if m}


def _code_lines(text):
    """The lines of code of a script, without blank lines and whole-line comments."""
    return [ln.strip() for ln in (text or "").split("\n")
            if ln.strip() and not ln.strip().startswith(("//", "/*", "*", "#!"))]


def _strings(text):
    """The texts a script holds (its string literals), where an address would be."""
    return "\n".join(m.group(0) for m in re.finditer(
        r"'(?:\\.|[^'\\\n])*'|\"(?:\\.|[^\"\\\n])*\"|`(?:\\.|[^`\\])*`", text or ""))


def _strip_strings(line):
    return re.sub(r"'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"|`(?:\\.|[^`\\])*`|//.*$", "''", line)


def line_additive(name, old, new, risky):
    """Rule 5: every old line of code is still there, in order; the new lines do not leave old code,
    switch something off or reach out."""
    a, b = _code_lines(old), _code_lines(new)
    out, j, runs, run = [], 0, [], []
    for line in a:
        k = j
        while k < len(b) and b[k] != line:
            k += 1
        if k == len(b):
            return ["%s: a line of the old file is removed or changed (%s): this file may only get new lines"
                    % (name, line[:70])]
        if k > j:
            runs.append(b[j:k])
        j = k + 1
    if j < len(b):
        runs.append(b[j:])
    known = set(re.findall(r"[A-Za-z_$][\w$]*", old or ""))
    had = declared(old)
    before = hosts_in(_strings(old))
    for run in runs:
        depth = 0
        mine = set()                              # what the new lines themselves declare inside their own blocks
        for line in run:
            bare = _strip_strings(line)
            opened_before = depth
            depth += bare.count("{") - bare.count("}")
            # a closing brace first ("} else {") ends the block before the line's own words
            level = min(opened_before, depth) if bare.lstrip().startswith("}") else opened_before
            # rule 3b: an old declaration is not declared again where the old code stands (a second
            # `function level()` replaces the first, a `let blocked` hides the old one), and nothing the
            # old file declares is assigned to (its value, a property, an index)
            d = DECLARES.match(bare)
            if d and d.group(2) in had and (level <= 0 or d.group(1).startswith("var")):
                out.append("%s: a new line declares %s again, which the old file already declares (%s)"
                           % (name, d.group(2), line[:60]))
            elif d and level > 0:
                mine.add(d.group(2))
            a = None if d else ASSIGNS.match(bare)
            if a and a.group(1) in had and a.group(1) not in mine and a.group(1) not in ("self", "this"):
                out.append("%s: a new line assigns to %s, which the old file declares (%s)"
                           % (name, (a.group(1) + a.group(2)).replace(" ", "")[:40], line[:60]))
            if EXIT_WORD.search(bare) and level <= 0 and not re.search(
                    r"\b(?:function\b|fn\s|=>)", bare.split("return")[0].split("throw")[0]):
                out.append("%s: a new line leaves the old code (%s): only inside a block the change itself opens"
                           % (name, line[:70]))
            if re.search(r"^\s*(?:\}\s*)?(?:else\s+)?if\s*\(\s*(?:true|1|!0|!false)\s*\)|^\s*if\s+true\b", bare):
                out.append("%s: a new condition that is always true (%s)" % (name, line[:70]))
            if risky.search(bare):
                out.append("%s: a new line reaches out or loads code (%s)" % (name, line[:70]))
            m = CONSTANT_ASSIGN.match(bare)
            if m and re.match(r"[A-Za-z_$][\w$]*", m.group(1)) and \
                    re.match(r"[A-Za-z_$][\w$]*", m.group(1)).group(0) in known and \
                    not re.match(r"\s*(?:var|let|const)\s", bare):
                out.append("%s: a new line gives a constant to %s, which the old file has (a protection switched off?)"
                           % (name, m.group(1)[:40]))
        if depth != 0:
            out.append("%s: the new lines open and close blocks of the old code (%s ...)" % (name, run[0][:50]))
    for what in sorted(hosts_in(_strings(new)) - before):
        out.append("%s: the change adds %s" % (name, what))
    return out


def json_superset(old, new):
    """The new JSON value is the old one with more in it."""
    if isinstance(old, dict):
        return isinstance(new, dict) and all(k in new and json_superset(v, new[k]) for k, v in old.items())
    if isinstance(old, list):
        if not isinstance(new, list):
            return False
        it = iter(new)
        return all(any(json_superset(x, y) for y in it) for x in old)
    return type(old) is type(new) and old == new


# --- one file, one pull request ----------------------------------------------------------------

def file_problems(name, old, new, status="modified", engine_candidate=False, sha_of=None, tier_b=False,
                  tags=None):
    """Why this file of an AI fix is refused by the static guard (a list; empty: accepted).
    sha_of(path): the sha256 of a file of the changed tree, or "" (for the manifest's entries).
    tier_b: the owner turned AUTOMAT_TIER_B on, so a few tier-B files open in their narrowest form
    (tools/tier-b.py); tags(repo): an action's release tags (git ls-remote; tests pass their own)."""
    level = tier(name)
    if level == "B":
        if tier_b and tier_b_open(name):
            if status != "modified" or old is None or new is None:
                return ["%s: added, removed or renamed (an AI fix changes existing files only)" % name]
            import types
            return ["tier B (the owner's switch): " + r for r in _tool("tier-b").file_problems(
                name, old, new, types.SimpleNamespace(additive_problems=additive_problems,
                                                      capability_problems=capability_problems, _grows=_grows), tags)]
        return ["%s: tier B, never changed by an AI (%s)" % (name, tier_b_reason(name))]
    if status != "modified" or old is None or new is None:
        return ["%s: added, removed or renamed (an AI fix changes existing files only)" % name]
    if level == "":
        return []                                 # an ordinary module or document: its own rules (the callers')
    if name == MANIFEST:
        return _tool("component-manifest").ai_entry_problems(old, new, sha_of)
    if name in PROTECTED_JSON:
        try:
            ok = json_superset(json.loads(old), json.loads(new))
        except ValueError:
            return ["%s: the file does not parse" % name]
        return [] if ok else ["%s: an entry of the table is removed or changed (it may only grow)" % name]
    if name.endswith(".py"):
        out = capability_problems(name, old, new)
        if not (engine_candidate and name in WRAPPER):
            out += additive_problems(name, old, new)
        return out
    risky = RUST_RISKY if name.endswith(".rs") else JS_RISKY
    if engine_candidate and name.endswith(".rs"):
        added = [ln for ln in _code_lines(new) if ln not in set(_code_lines(old))]
        out = ["%s: a new line reaches out or loads code (%s)" % (name, ln[:70]) for ln in added if risky.search(ln)]
        return out + ["%s: the change adds %s" % (name, w)
                      for w in sorted(hosts_in(_strings(new)) - hosts_in(_strings(old)))]
    return line_additive(name, old, new, risky)


def changed_lines(old, new):
    import difflib
    a, b = (old or "").split("\n"), (new or "").split("\n")
    return sum(max(i2 - i1, j2 - j1) for tag, i1, i2, j1, j2 in
               difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes() if tag != "equal")


def check(changes, engine_candidate=False, exempt=(), max_files=MAX_FILES, max_lines=MAX_LINES, sha_of=None,
          tier_b=False, tags=None):
    """The reasons the AI's changes are refused (empty: the static guard passes).

    changes: [{"filename", "status", "old_source", "new_source"}], the files the AI commits changed,
    each whole, before and after. exempt: files judged by a rule of their own (a builder's
    re-anchoring, tools/builder-anchor.py). tier_b: the owner's switch AUTOMAT_TIER_B is on."""
    out, lines, files = [], 0, 0
    for c in changes:
        name = c.get("filename", "")
        if name in exempt:
            continue
        files += 1
        old, new = c.get("old_source"), c.get("new_source")
        out += file_problems(name, old, new, c.get("status", "modified"), engine_candidate, sha_of, tier_b, tags)
        if old is not None and new is not None:
            lines += changed_lines(old, new)
    if files > max_files:
        out.append("too many files changed by the AI: %d (at most %d)" % (files, max_files))
    if lines > max_lines:
        out.append("too many lines changed by the AI: %d (at most %d)" % (lines, max_lines))
    return out


def protected(changes):
    """The tier-A files among the changes (they need the reviews and the no-regression check)."""
    return sorted(c.get("filename", "") for c in changes if tier(c.get("filename", "")) == "A")


def reserved(changes):
    """The tier-B files among the changes that the owner's switch opens (they need a third reviewer)."""
    return sorted(c.get("filename", "") for c in changes if tier_b_open(c.get("filename", "")))


def _show(repo, rev, path):
    out = subprocess.run(["git", "-C", str(repo), "show", "%s:%s" % (rev, path)], capture_output=True)
    return out.stdout.decode("utf-8", "replace") if out.returncode == 0 else None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--repo", default=".")
    ap.add_argument("--base", required=True)
    ap.add_argument("--head", required=True)
    ap.add_argument("--engine-candidate", action="store_true")
    ap.add_argument("--tier-b", action="store_true",
                    help="the owner turned AUTOMAT_TIER_B on: the narrow form of tools/tier-b.py")
    ap.add_argument("files", nargs="*", help="only these files (default: every file that differs)")
    a = ap.parse_args(argv)
    names = a.files or [n for n in subprocess.run(
        ["git", "-C", a.repo, "diff", "--name-only", "-z", a.base, a.head], capture_output=True,
        text=True).stdout.split("\0") if n]
    changes = []
    for n in names:
        old, new = _show(a.repo, a.base, n), _show(a.repo, a.head, n)
        changes.append({"filename": n, "old_source": old, "new_source": new,
                        "status": "modified" if old is not None and new is not None else "added or removed"})
    import hashlib

    def sha_of(path):
        text = _show(a.repo, a.head, path)
        return hashlib.sha256(subprocess.run(["git", "-C", a.repo, "show", "%s:%s" % (a.head, path)],
                                             capture_output=True).stdout).hexdigest() if text is not None else ""
    reasons = check(changes, a.engine_candidate, sha_of=sha_of, tier_b=a.tier_b)
    for r in reasons:
        print(re.sub(r":(?=:)", ": ", re.sub(r"\s+", " ", r))[:400])
    if not reasons:
        print("the static guard passes (%d files; tier A: %s)" % (len(changes), ", ".join(protected(changes)) or "none"))
    return 1 if reasons else 0


if __name__ == "__main__":
    sys.exit(main())
