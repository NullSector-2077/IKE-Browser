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
   engine's new interface: there the additive rule does not apply to it, the others do. In I.K.E.'s
   own page scripts (PROTECTED_JS: page_script_problems, the fourth review of "Nothing gets worse",
   2026-11-24) a new line also may not leave code anywhere but inside a function the change adds, read
   where or when the page is (PAGE_ENV), or change an object the old script has by a method or delete
   from it (PAGE_MUTATE, PAGE_DELETE); since round 5 (2026-11-25) also not assign anywhere in the line to a
   name the change does not declare (PAGE_ASSIGN, PAGE_INCDEC), run something later outside a function the
   change adds (PAGE_LATER), or name sites in a pattern or a text (PAGE_BRANDS). Since round 6 (2026-11-25)
   a page script is read by its syntax tree (page_tree_problems, the guard's own parser tools/js-parse.py;
   a script that does not parse is refused): every old statement still in its place, and what is added
   writes nothing the old script has, reads none of the page's environment, reaches no property by a
   computed name, leaves no old code, branches only on what "Nothing gets worse" measures (literals, its own
   names, the level, the users' configurations of tools/env-axes.py) and wraps no property the old script
   already names; the rules on lines keep only the old lines, the always-true conditions, what reaches out,
   the named sites and the new addresses there.
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
                    "__init__", "sort", "reverse", "insert", "update"}


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


# I.K.E.'s own page scripts (PROTECTED_JS), the fourth review of "Nothing gets worse" (2026-11-24): copies
# made of added lines only weakened the fingerprinting protection and passed rule 5. There a new line
# may not: leave code (return, throw, break, continue) anywhere but inside a function the change itself
# adds (an early exit in a new block skipped the noise on some sites, for sub-frames, for WebGL2);
# read where or when the page is (PAGE_ENV: an address, a frame, the time, chance) to decide anything;
# change an object the old script has by a method (PAGE_MUTATE: taking names out of the masked fonts,
# hidden extensions or any list, putting a site into a list of exceptions) or delete from it.
PAGE_ENV = re.compile(r"(?<![\w$])(location|hostname|protocol|origin|top|parent|frameElement|Date|performance"
                      r"|ancestorOrigins|referrer|domain)(?![\w$])|Math\s*\.\s*random")
PAGE_MUTATE = re.compile(r"(?<![\w$.])([A-Za-z_$][\w$]*)((?:\s*\.\s*[\w$]+|\s*\[[^\]]*\])*)\s*\.\s*"
                         r"(splice|pop|shift|unshift|push|fill|copyWithin|reverse|sort|clear|delete|add|set)\s*\(")
PAGE_DELETE = re.compile(r"(?<![\w$.])delete\s+([A-Za-z_$][\w$]*)")
# round 5 of the review of "Nothing gets worse" (2026-11-25): one-line weakenings that passed both layers.
# An assignment anywhere in a line (inside a callback, a loop, after a ";"), not only at its start
PAGE_ASSIGN = re.compile(r"(?<![\w$.])([A-Za-z_$][\w$]*)((?:\s*\.\s*[\w$]+|\s*\[[^\]]*\])*)\s*"
                         r"(?:\*\*|[-+*/%|&^]|\|\||&&|\?\?|<<|>>>?)?=(?![=>])")
PAGE_INCDEC = re.compile(r"(?:\+\+|--)\s*([A-Za-z_$][\w$]*)|(?<![\w$.])([A-Za-z_$][\w$]*)\s*(?:\+\+|--)")
# what declares a name in the new lines themselves: a var, let or const anywhere in the line, a new
# function's name and parameters, an arrow function's parameters
PAGE_DECLS = re.compile(r"(?<![\w$.])(?:var|let|const)\s+([A-Za-z_$][\w$]*)|\bfunction\s*\*?\s*([A-Za-z_$][\w$]*)")
PAGE_PARAMS = re.compile(r"\bfunction\s*\*?\s*[\w$]*\s*\(([^)]*)\)|\(([^()]*)\)\s*=>|(?<![\w$.])([A-Za-z_$][\w$]*)\s*=>")
# what runs later than the page's first script: a timer, a frame or idle callback, a microtask, a promise's
# continuation, a listener (a change deferred past the measurement's window: the noise key changed after 90 s)
PAGE_LATER = re.compile(r"(?<![\w$.])(setTimeout|setInterval|requestAnimationFrame|requestIdleCallback|queueMicrotask)"
                        r"(?![\w$])|\.\s*then\s*\(|\.\s*addEventListener\s*\(|(?<![\w$])await(?![\w$])")
# a site named in a pattern (a regular expression of brand names or top-level domains: hosts_in reads texts,
# not patterns) or a brand's host in a text
PAGE_BRANDS = re.compile(r"google|youtube|youtu\.be|facebook|instagram|whatsapp|amazon|cloudflare|captcha|microsoft"
                         r"|live\.com|apple|icloud|paypal|stripe|twitter|tiktok|baidu|yandex|bing|github|netflix"
                         r"|akamai|fastly|doubleclick|adsystem|\(\s*(?:com|org|net|io|it|de|fr|uk)\s*\||\\\.(?:com|org|net"
                         r"|io|co|uk)\b", re.I)
REGEX_LITERAL = re.compile(r"(?:^|[(,=:!&|?{;]|\breturn)\s*/((?:\\.|\[(?:\\.|[^\]\\])*\]|[^/\\\n*])(?:\\.|\[(?:\\.|"
                           r"[^\]\\])*\]|[^/\\\n])*)/[a-z]*")
# the protection's own state and where the page is: a new condition on them that guards an assignment of an
# old name or an early exit is refused with its own reason (the assignment and the exit are refused anyway)
PAGE_STATE = {"host", "lv", "level", "cores", "realCores", "n", "W", "H", "width", "height", "seed", "strict",
              "maximum", "CFG", "SITE_KEY", "MASKED", "hiddenExt", "usual", "langs", "rng", "me", "site", "key"}
PAGE_CONDITION = re.compile(r"(?<![\w$])(?:if|while|switch)\s*\(|\?[^?.:]|&&|\|\|")


def _declared_list(bare):
    """Every name a `var`, `let` or `const` statement of the line declares, the ones after a comma too
    (`var a = 1, b = f(x, y);`): the parts at bracket depth 0 up to the statement's end."""
    out = []
    for m in re.finditer(r"(?<![\w$.])(?:var|let|const)\s+", bare):
        depth, part, i = 0, "", m.end()
        while i < len(bare):
            ch = bare[i]
            if ch in "([{":
                depth += 1
            elif ch in ")]}":
                if depth == 0:
                    break
                depth -= 1
            elif ch in ",;" and depth == 0:
                n = re.match(r"\s*([A-Za-z_$][\w$]*)", part)
                if n:
                    out.append(n.group(1))
                part = ""
                if ch == ";":
                    break
                i += 1
                continue
            part += ch
            i += 1
        n = re.match(r"\s*([A-Za-z_$][\w$]*)", part)
        if n:
            out.append(n.group(1))
    return out


def page_script_problems(name, run, had, known=(), structural=True):
    """The rules of a page script's new lines (PROTECTED_JS): (problems). `run` is a run of new lines,
    `had` what the old script declares, `known` every name the old script has (its parameters too).
    structural=False: the script parsed, so its syntax trees judge writes, exits, reads and branches
    (page_tree_problems): only the sites named in patterns and texts are judged here."""
    out, stack, mine = [], [], set()
    known = set(known) | set(had)
    for line in run:
        bare = _strip_strings(line)
        d = DECLARES.match(bare)
        if d:
            mine.add(d.group(2))
        for m in PAGE_DECLS.finditer(bare):
            mine.add(m.group(1) or m.group(2))
        for part in _declared_list(bare):
            mine.add(part)
        for m in PAGE_PARAMS.finditer(bare):
            for p in re.split(r"[,\s]+", m.group(1) or m.group(2) or m.group(3) or ""):
                p = p.split("=")[0].strip(" .{}[]")
                if re.match(r"^[A-Za-z_$][\w$]*$", p):
                    mine.add(p)
        in_fn = "fn" in stack
        if not structural:
            out += _named_sites(name, line)
            continue
        # (i) an assignment anywhere in the line to a name the change did not declare itself (round 5, F5:
        # `seed = 1` inside a timer's callback; F1, F2, F3: lv, cores, n set under a new condition)
        targets = [m.group(1) for m in PAGE_ASSIGN.finditer(bare)] + \
            [m.group(1) or m.group(2) for m in PAGE_INCDEC.finditer(bare)]
        for t in targets:
            if t not in mine and t not in ("this",) and not re.match(r"^(?:var|let|const)$", t):
                out.append("%s: a new line assigns to %s, which the change does not declare (%s): in a page "
                           "script new code may only set its own names" % (name, t, line[:70]))
                break
        # (ii) code that runs later, outside a function the change adds
        if PAGE_LATER.search(bare) and not in_fn and not re.search(r"\bfunction\b|=>", bare.split("(")[0]):
            out.append("%s: a new line runs something later (%s): in a page script a timer, a promise's "
                       "continuation or a listener only inside a function the change adds" % (name, line[:70]))
        # (iii) a new condition on the protection's state or where the page is, guarding an assignment or an exit
        state = sorted({w for w in re.findall(r"(?<![\w$.])([A-Za-z_$][\w$]*)", bare)} & PAGE_STATE & known)
        if state and PAGE_CONDITION.search(bare) and (targets and any(t not in mine for t in targets)
                                                      or EXIT_WORD.search(bare)):
            out.append("%s: a new condition on %s decides what the protection does (%s)" % (
                name, ", ".join(state[:4]), line[:70]))
        # (iv) a site named in a pattern or a text
        out += _named_sites(name, line)
        # what the line itself opens before an exit word: a function written on the same line
        head = re.split(r"(?<![\w$.])(?:return|throw|break|continue)(?![\w$])", bare, maxsplit=1)[0]
        if EXIT_WORD.search(bare) and not in_fn and not re.search(r"\bfunction\b|=>", head):
            out.append("%s: a new line leaves code outside a function the change adds (%s): in a page script "
                       "an early exit skips the protection" % (name, line[:70]))
        if PAGE_ENV.search(bare):
            out.append("%s: a new line reads where or when the page is (%s): in a page script a protection may "
                       "not depend on the site, the frame, the time or chance" % (name, line[:70]))
        for m in PAGE_MUTATE.finditer(bare):
            if m.group(1) in had and m.group(1) not in mine and m.group(1) not in ("this", "self"):
                out.append("%s: a new line changes %s, which the old script has (%s): its lists and tables only "
                           "change by a person" % (name, m.group(1), line[:70]))
        for m in PAGE_DELETE.finditer(bare):
            if m.group(1) in had and m.group(1) not in mine:
                out.append("%s: a new line deletes from %s, which the old script has (%s)" % (name, m.group(1),
                                                                                           line[:70]))
        # the blocks this line opens and closes: a function or another block
        text = ""
        for ch in bare:
            if ch == "{":
                stack.append("fn" if re.search(r"\bfunction\b[^{}]*$|=>\s*$|\)\s*$", text) and
                             re.search(r"\bfunction\b|=>", text) else "blk")
                text = ""
            elif ch == "}":
                if stack:
                    stack.pop()
                text = ""
            else:
                text += ch
    return out


# --- I.K.E.'s page scripts by their syntax trees (round 6 of "Nothing gets worse", 2026-11-25) -----------
#
# Rules on lines kept leaking: a destructuring, a loop's target or a second declarator wrote to old
# names; Object.defineProperty, Reflect.set and Object.assign changed old objects; document.URL,
# window['loc' + 'ation'] or devicePixelRatio read where the page is; and a new call of an old helper
# re-wrapped what the old script protects, under a condition no measurement makes true (the real cores
# for every screen whose devicePixelRatio is not 1). So a page script (PROTECTED_JS) is read by its syntax
# tree (tools/js-parse.py, no dependency) and every statement of the old tree must still be in the new one,
# in order and at the same place (statements may only be added to a list of statements). What is added
# is the change; in it nothing may:
#  (a) write to what the old script has: a binding (any assignment or pattern, ++/--, a for-in/of's
#      target, a declaration of an old name, a parameter's too, one that hides an old name from old code),
#      an object (its properties, delete, a method that changes it, Object.defineProperty, assign,
#      setPrototypeOf, freeze..., Reflect.set, defineProperty, deleteProperty..., __proto__), a page
#      object or a global (new code changes only objects it makes itself, `{}`, `[]`, `new Map()`);
#  (b) read the page's environment (where, when, the screen, the device, chance, timers, events):
#      ENV_NAMES, as a global or a property, unless the matrix of "Nothing gets worse" measures it
#      (tools/env-axes.py COVERED_READS; matchMedia with a literal query of covered features), or the old
#      script reads exactly that too and the new code is inside a function the change adds (an interface's
#      prototype, `Date.prototype`, is no read);
#  (c) reach a property by a computed name (only a literal, or a number: arithmetic, a length, a counter),
#      call eval or Function, use `with`, `import()` or `.constructor`;
#  (d) leave code: return or throw outside a function the change adds, break or continue out of a loop
#      or switch the change did not add;
#  (e) branch on what no measurement covers: an if, ?:, &&, ||, ??, switch, a loop's test, an optional chain
#      `?.`, a default value, a for-in/of, a catch that does more than give a value back, whose test reads
#      anything but literals, the change's own clean names (set in their own function from clean values; a
#      parameter when every call gives clean values), the level (PROTECTION_STATE) and the users'
#      configurations "Nothing gets worse" measures in its matrix (tools/env-axes.py COVERED_READS, one list
#      for the probe and the guard: an axis added there is measured and allowed at once). A condition no
#      measurement makes true is exactly what hides a weakening (the owner's direction of 2026-11-25: the
#      configurations are measured up front, so the automatic fix needs no person for a condition on them);
#  (f) define or re-wrap a property through an I.K.E. helper (wrap, getter, setter... any old function
#      that defines properties) or Object.defineProperty and the like, unless every name it gives is a
#      literal the old script never has (a new disguise, never a second wrap of a protected one) and its
#      target is a prototype, never one of the language's own objects (BUILTINS); the one exception is a
#      copy of an old call with only the engine's renamed names changed (tools/engine-renames.json);
#  (g) round 7 (Fable's third review): run where it can stop the old code. New code comes after the last
#      old statement of its block (before it, a throw without `throw` stopped the old statements after it,
#      an old `catch` swallowed it and skipped the rest of its block, `0;` before 'use strict' demoted the
#      directive), and is a declaration that cannot throw or `try { ... } catch (e) {}`; it calls only the
#      old script's pure helpers and its property helpers (PAGE_HELPERS: install(window) again is a
#      person's); a measured value counts as measured only compared with a literal (the probe adds sessions
#      at that value and beside it: axis_literals, tools/env-axes.py derive).
#  (h) round 8 (Fable's fourth review): use a function that defines properties other than as the direct
#      callee of a call (wrap.call, .apply, .bind, Reflect.apply(wrap), (0, wrap)(), an alias, new, a tag),
#      or Object and Reflect other than by their functions' names; define a name every object has
#      (INHERITED_NAMES: then, toString, valueOf...); compare a covered read with a value the probe cannot
#      set (tools/env-axes.py read_measured, media_measured). The probe measures every combination of a
#      change's own values (env-axes.py _joint_rows).
#  (i) round 9 (Fable's review of round 8): define with arguments of another shape than one literal name,
#      functions, a plain descriptor and a page interface's prototype named by its chain (interface_target:
#      named in the old script, not GLOBAL_INTERFACES); change a new object deeper than one level; use
#      __defineGetter__ and its kin; read a covered name on another object than the configuration's own
#      (_covered_object); compare with a value the sessions do not really set (read_measured); compare both the
#      window's size and the screen's; compare with more values than a run measures (too_many).
# A text that does not parse is refused (and the rules on lines say what they see).

ENV_NAMES = frozenset("""
location top parent opener frames frameElement self Date performance Intl navigator screen devicePixelRatio
innerWidth innerHeight outerWidth outerHeight screenX screenY screenLeft screenTop scrollX scrollY pageXOffset
pageYOffset visualViewport matchMedia getComputedStyle setTimeout setInterval requestAnimationFrame
requestIdleCallback queueMicrotask crypto origin history localStorage sessionStorage indexedDB caches
MessageChannel BroadcastChannel postMessage Notification Worker SharedWorker fetch XMLHttpRequest WebSocket
EventSource orientation ontouchstart PointerEvent TouchEvent
URL baseURI documentURI referrer domain cookie visibilityState hidden hasFocus ancestorOrigins hostname host
href pathname protocol search port hash maxTouchPoints userAgent userAgentData platform language languages
hardwareConcurrency deviceMemory connection onLine webdriver plugins mimeTypes vendor oscpu timeZone
resolvedOptions getTimezoneOffset now random getRandomValues randomUUID timeOrigin availWidth availHeight
colorDepth pixelDepth then addEventListener lastModified readyState activeElement fonts pointerEnabled
msMaxTouchPoints standalone
""".split())
STMT_LISTS = {("Program", "body"), ("BlockStatement", "body"), ("StaticBlock", "body"),
              ("SwitchCase", "consequent")}
FUNCTIONS = ("FunctionDeclaration", "FunctionExpression", "ArrowFunctionExpression")
LOOPS = ("ForStatement", "ForInStatement", "ForOfStatement", "WhileStatement", "DoWhileStatement")
# what changes an object given as the first argument (and Object/Reflect's functions that do)
MUTATING_METHODS = {"splice", "pop", "shift", "unshift", "push", "fill", "copyWithin", "reverse", "sort",
                    "clear", "delete", "add", "set", "setPrototypeOf", "__defineGetter__", "__defineSetter__"}
OBJECT_MUTATORS = {("Object", "defineProperty"), ("Object", "defineProperties"), ("Object", "assign"),
                   ("Object", "setPrototypeOf"), ("Object", "freeze"), ("Object", "seal"),
                   ("Object", "preventExtensions"), ("Reflect", "set"), ("Reflect", "defineProperty"),
                   ("Reflect", "deleteProperty"), ("Reflect", "setPrototypeOf"), ("Reflect", "preventExtensions")}
DEFINERS = {("Object", "defineProperty"), ("Reflect", "defineProperty"), ("Reflect", "set"),
            ("Reflect", "deleteProperty")}
CONSTANT_GLOBALS = {"undefined", "NaN", "Infinity"}
# round 7 (Fable's third review): the language's own objects, which the old script relies on (its hashing,
# its seeds, its collections): no new wrap or definition on them or their prototypes
BUILTINS = frozenset("""Object Function Array String Number Boolean Symbol BigInt Math JSON Reflect Proxy Map Set
WeakMap WeakSet WeakRef FinalizationRegistry Promise RegExp Date Intl Error TypeError RangeError SyntaxError
ReferenceError EvalError URIError AggregateError ArrayBuffer SharedArrayBuffer DataView Atomics Int8Array
Uint8Array Uint8ClampedArray Int16Array Uint16Array Int32Array Uint32Array Float32Array Float64Array
BigInt64Array BigUint64Array Iterator globalThis eval isNaN isFinite parseInt parseFloat encodeURI
encodeURIComponent decodeURI decodeURIComponent escape unescape Float16Array AsyncIterator Temporal WebAssembly
DOMException console""".split())
# round 8 (Fable's fourth review): names every object has (Object.prototype's, and those the language or the
# old code looks up on any object: then makes it a promise's, toJSON its text, Symbol's well-known ones). A
# new getter of `then` or `toString` on a page interface is no new disguise: it changes what the old code's
# own coercions and promises do
INHERITED_NAMES = frozenset("""constructor __proto__ __defineGetter__ __defineSetter__ __lookupGetter__
__lookupSetter__ hasOwnProperty isPrototypeOf propertyIsEnumerable toLocaleString toString valueOf then toJSON
length name prototype caller arguments handleEvent Symbol.toPrimitive Symbol.iterator Symbol.asyncIterator
Symbol.hasInstance Symbol.toStringTag Symbol.species Symbol.isConcatSpreadable Symbol.unscopables Symbol.match
Symbol.matchAll Symbol.replace Symbol.search Symbol.split next done return throw catch finally apply call bind
value get set enumerable configurable writable raw""".split())
# what a descriptor given to Object.defineProperty may hold (round 9)
DESCRIPTOR_KEYS = frozenset(("get", "set", "value", "enumerable", "configurable", "writable"))
# page interfaces whose new properties every page and the old code itself meet (round 9, Fable's review of
# round 8: a getter on Window.prototype is a new global, on Event.prototype a changed isTrusted)
GLOBAL_INTERFACES = frozenset("""Window WindowProperties EventTarget Event Node Document HTMLDocument Location
History Element HTMLElement CustomEvent MessageEvent ErrorEvent PromiseRejectionEvent""".split())
# Object's and Reflect's functions that define or change (round 8: reached only as the direct callee of a call,
# never through .call, .apply, .bind, an alias, a comma, `new` or a tag, where rule (f) does not see them)
OBJECT_HOLDERS = frozenset(("Object", "Reflect"))
# the old functions of a page script new code may call (round 7: a call of an old function runs old code
# again, install(window) twice, or code that stores the new code in old state): pure helpers that read
# their arguments and give a value, and the helpers that define a property (wrap, getter, setter: rule (f)
# judges what they are given). Any other old function is a person's to call
PAGE_HELPERS = {
    "ike/resources/fingerprint.js": frozenset("""getterOf setterOf sslice sindex lower isBlob majorOf LEN TAG pixels
mul32 hash sha256 rng siteOf inPsl isIndex word nativeText mqValue mqCompare mqFeature hardSet hardMap
hardStrongMap wrap getter setter""".split()),
}
# what a new statement in the old code's own lists may be outside `try { ... } catch (e) {}`: a declaration
SAFE_UNARY = {"-", "+", "!", "~", "void"}
COMPARE = {"==", "===", "!=", "!==", "<", "<=", ">", ">="}


def _renames():
    """tools/engine-renames.json beside this file (round 7): the engine's renamed page APIs, from the
    comparison of its old and new interfaces (AUTOMAT's recipes write it; tier B). A re-wrap of a protected
    property is accepted only as a copy of an old wrap with these names changed and nothing else."""
    try:
        data = json.loads((Path(__file__).resolve().parent / "engine-renames.json").read_text("utf-8"))
        return {(str(r["from"]), str(r["to"])) for r in data.get("renames") or () if r.get("from") and r.get("to")}
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return set()


def _equal_renamed(a, b, renames, used, idents=None):
    """The same tree, positions aside, but texts and names changed as a rename of the engine's says (idents:
    the pairs of names met, for their bindings)."""
    if isinstance(a, dict) and isinstance(b, dict):
        if a.get("type") != b.get("type"):
            return False
        if a.get("type") == "Identifier" and idents is not None:
            idents.append((a, b))
        if a.get("type") == "Literal" and isinstance(a.get("value"), str) and isinstance(b.get("value"), str) \
                and a["value"] != b["value"]:
            if (a["value"], b["value"]) in renames:
                used.append((a["value"], b["value"]))
                return True
            return False
        if a.get("type") == "Identifier" and a["name"] != b["name"]:
            if (a["name"], b["name"]) in renames:
                used.append((a["name"], b["name"]))
                return True
            return False
        ka = [k for k in a if k not in ("start", "end")]
        if set(ka) != {k for k in b if k not in ("start", "end")}:
            return False
        return all(_equal_renamed(a[k], b[k], renames, used, idents) for k in ka)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_equal_renamed(x, y, renames, used, idents) for x, y in zip(a, b))
    return type(a) is type(b) and a == b
COVERED_HINT = ("only literals, the change's own names set from them, the level and the configurations "
                "\"Nothing gets worse\" measures: tools/env-axes.py")


def _js_parse(source):
    """The syntax tree of a page script (tools/js-parse.py beside this file), or (None, why)."""
    try:
        jsp = _tool("js-parse")
    except Exception as e:                               # the parser missing beside the guard: refuse
        return None, "the parser (tools/js-parse.py) could not be loaded: %s" % e
    try:
        return jsp.parse(source or ""), ""
    except jsp.JSSyntaxError as e:
        return None, str(e)


def _env_axes():
    """tools/env-axes.py beside this file: what "Nothing gets worse" measures of the users' configurations
    (COVERED_READS, COVERED_MEDIA, PROTECTION_STATE); None when it cannot be loaded (nothing is covered)."""
    try:
        return _tool("env-axes")
    except Exception:
        return None


MEDIA_FEATURE = re.compile(r"\(\s*([a-z-]+)\s*[:)]")


def _covered(node, scopes, axes):
    """A read of the page's environment that the matrix of "Nothing gets worse" measures (tools/env-axes.py):
    its key among COVERED_READS; matchMedia only with a literal query whose every feature is covered."""
    if axes is None:
        return False
    key = _env_key(node, scopes)
    if not key or key not in axes.COVERED_READS:
        return False
    if node["type"] == "MemberExpression" and not _covered_object(node["object"], scopes):
        return False                     # round 9: `document.body.dataset.language` is no configuration
    name = node.get("name") if node["type"] == "Identifier" else _prop_name(node)
    if name == "matchMedia":
        par = scopes.parent.get(id(node))
        call = par if par is not None and par["type"] == "CallExpression" and par["callee"] is node else None
        if call is None or not call["arguments"] or call["arguments"][0]["type"] != "Literal" or \
                not isinstance(call["arguments"][0].get("value"), str):
            return False
        feats = MEDIA_FEATURE.findall(call["arguments"][0]["value"])
        return bool(feats) and all(f in axes.COVERED_MEDIA for f in feats) and \
            axes.media_measured(call["arguments"][0]["value"])
    return True


COVERED_HOLDERS = frozenset(("navigator", "screen", "window", "self", "globalThis", "visualViewport"))


def _covered_object(obj, scopes):
    """What a covered property is read on (round 9, Fable's review of round 8: a read was recognised by its
    name on any object): the global navigator, screen, window..., or `Intl.DateTimeFormat().resolvedOptions()`
    and `Intl.DateTimeFormat`'s own `Intl`."""
    obj = _strip(obj)
    if obj["type"] == "Identifier":
        return obj["name"] in COVERED_HOLDERS | {"Intl"} and scopes.refs.get(id(obj), 0) is None
    if obj["type"] == "MemberExpression":
        return _prop_name(obj) in COVERED_HOLDERS and _covered_object(obj["object"], scopes) or \
            _prop_name(obj) == "DateTimeFormat" and _covered_object(obj["object"], scopes)
    if obj["type"] == "CallExpression" and not obj["arguments"]:
        c = _strip(obj["callee"])
        if c["type"] == "MemberExpression" and _prop_name(c) == "DateTimeFormat":
            return _covered_object(c["object"], scopes)
        if c["type"] == "MemberExpression" and _prop_name(c) == "resolvedOptions":
            inner = _strip(c["object"])
            return inner["type"] == "CallExpression" and not inner["arguments"] and \
                _strip(inner["callee"])["type"] == "MemberExpression" and \
                _prop_name(_strip(inner["callee"])) == "DateTimeFormat" and \
                _covered_object(_strip(inner["callee"])["object"], scopes)
    return False


PURE_CALLS = {("Math",), ("parseInt",), ("parseFloat",), ("Number",), ("String",), ("Boolean",), ("isNaN",),
              ("isFinite",), ("Array", "isArray")}


def _clean_bindings(tree, scopes, added_ids, axes):
    """The change's own names whose every value is clean (_clean): set only in their own function from
    literals, covered reads of the environment, the level and other clean names; a parameter of a new
    function is clean when every call of it in the change gives clean values (a function given to other code,
    a callback, is called with what that code gives: its parameters only shape what the new function does)."""
    own = {key for key, decl in scopes.decls.items() if key is not None and decl and
           all(id(d) in added_ids for d in decl)}
    params, calls, passed = {}, {}, set()
    for node in _walk(tree):
        if node["type"] in FUNCTIONS and id(node) in added_ids:
            fkey = None
            if node["type"] == "FunctionDeclaration" and node.get("id"):
                fkey = scopes.decl_of.get(id(node["id"]))
            else:
                par = scopes.parent.get(id(node))
                if par is not None and par["type"] == "VariableDeclarator" and par["init"] is node and \
                        par["id"]["type"] == "Identifier":
                    fkey = scopes.decl_of.get(id(par["id"]))
            for i, p in enumerate(node["params"]):
                for ident in _js_target_names(p):
                    k = scopes.decl_of.get(id(ident))
                    if k is not None:
                        params[k] = (fkey, i if p["type"] in ("Identifier", "AssignmentPattern") else None)
        if node["type"] == "Identifier" and scopes.refs.get(id(node)) is not None:
            par = scopes.parent.get(id(node))
            if par is not None and par["type"] == "CallExpression" and par["callee"] is node:
                calls.setdefault(scopes.refs[id(node)], []).append(par)
            else:
                passed.add(scopes.refs[id(node)])
    clean = set(own)
    changed = True
    while changed:
        changed = False
        for key in list(clean):
            if key in params:
                fkey, i = params[key]
                ok = fkey is not None and fkey not in passed and i is not None and all(
                    i >= len(c["arguments"]) or _clean(c["arguments"][i], scopes, clean, axes)
                    for c in calls.get(fkey, []))
                ok = ok or (fkey is None or fkey in passed) and i is not None
                # what the function gives it later (after the declaration's own unknown value)
                ok = ok and all(v is not None and _clean(v, scopes, clean, axes)
                                for v in scopes.values.get(key, [])[1:])
            else:
                vals = scopes.values.get(key, [])
                ok = all(v is not None and (v["type"] in FUNCTIONS or _clean(v, scopes, clean, axes)) for v in vals)
            if not ok:
                clean.discard(key)
                changed = True
    return clean


def _clean(e, scopes, clean, axes):
    """A value a measurement covers: built only from literals, the change's own clean names, the level
    (PROTECTION_STATE) and reads of the environment the matrix covers (COVERED_READS)."""
    if e is None:
        return False
    t = e["type"]
    if t in ("Literal", "_Update"):
        return True
    if t == "_Compound":
        return _clean(e["right"], scopes, clean, axes)
    if t == "TemplateLiteral":
        return all(_clean(x, scopes, clean, axes) for x in e["expressions"])
    if t == "Identifier":
        key = scopes.refs.get(id(e), 0)
        if key is None:
            return e["name"] in CONSTANT_GLOBALS or (_covered(e, scopes, axes) and _measured_use(e, scopes))
        if key in clean:
            return True
        return axes is not None and e["name"] in axes.PROTECTION_STATE and key != 0
    if t in ("UnaryExpression", "AwaitExpression"):
        return t == "UnaryExpression" and e["operator"] != "delete" and _clean(e["argument"], scopes, clean, axes)
    if t in ("BinaryExpression", "LogicalExpression"):
        return _clean(e["left"], scopes, clean, axes) and _clean(e["right"], scopes, clean, axes)
    if t == "ConditionalExpression":
        return all(_clean(e[k], scopes, clean, axes) for k in ("test", "consequent", "alternate"))
    if t == "SequenceExpression":
        return all(_clean(x, scopes, clean, axes) for x in e["expressions"])
    if t == "ArrayExpression":
        return all(x is not None and _clean(x, scopes, clean, axes) for x in e["elements"])
    if t == "ObjectExpression":
        return all(p["type"] == "Property" and not p["computed"] and _clean(p["value"], scopes, clean, axes)
                   for p in e["properties"])
    if t == "MemberExpression":
        if _covered(e, scopes, axes):
            return _measured_use(e, scopes)
        if e["computed"] and _prop_name(e) is None and not _clean(e["property"], scopes, clean, axes):
            return False
        return _clean(e["object"], scopes, clean, axes)
    if t == "CallExpression":
        callee = e["callee"]
        if not all(a["type"] != "SpreadElement" and _clean(a, scopes, clean, axes) for a in e["arguments"]):
            return False
        ch = _chain(callee) if callee["type"] in ("Identifier", "MemberExpression") else None
        if ch and scopes.refs.get(id(_root(callee)), 0) is None and (tuple(ch[:1]) in PURE_CALLS or
                                                                    tuple(ch[:2]) in PURE_CALLS):
            return True
        # round 8 (Fable's fourth review): a method of a covered read's result (`resolvedOptions().locale`,
        # `matchMedia(q).media.length`) is no measured value; matchMedia only as `matchMedia(q).matches`, with
        # a query the probe sets on both sides (tools/env-axes.py media_measured)
        if callee["type"] == "MemberExpression" and not _covered(callee, scopes, axes) and \
                _clean(callee["object"], scopes, clean, axes):
            return True
        if callee["type"] == "Identifier" and _covered(callee, scopes, axes) and callee["name"] == "matchMedia":
            par = scopes.parent.get(id(e))
            return par is not None and par["type"] == "MemberExpression" and par["object"] is e and \
                _prop_name(par) == "matches"
        return False
    if t == "ChainExpression":
        return _clean(e["expression"], scopes, clean, axes)
    return False


def _const_value(e):
    """A literal number or text (a negative number too), or None."""
    if e["type"] == "Literal" and isinstance(e.get("value"), (int, float, str)) and not isinstance(e.get("value"), bool) \
            and "bigint" not in e:
        return e["value"]
    if e["type"] == "UnaryExpression" and e["operator"] == "-" and e["argument"]["type"] == "Literal" and \
            isinstance(e["argument"].get("value"), (int, float)):
        return -e["argument"]["value"]
    if e["type"] == "TemplateLiteral" and not e["expressions"]:
        return e["quasis"][0]["value"].get("cooked")
    return None


TOUCH_READS = ("maxTouchPoints", "navigator.maxTouchPoints")


def _measured_use(node, scopes):
    """A covered read used as the matrix of "Nothing gets worse" measures it (round 7): compared with a
    literal (the probe adds sessions at that value and beside it: tools/env-axes.py derive), negated, or as
    a condition's own test. The touch points only against 0 to 5 (a touch screen has 5 there): a value the
    probe cannot give is no condition. Used otherwise (in arithmetic, kept in a name) it is not measured."""
    key = _env_key(node, scopes) or ""
    node = _use_node(node, scopes)
    par = scopes.parent.get(id(node))
    if par is None:
        return False
    if par["type"] == "BinaryExpression" and par["operator"] in COMPARE:
        other = par["right"] if par["left"] is node else par["left"]
        v = _const_value(other)
        if v is None:
            return False
        if key in TOUCH_READS:
            return isinstance(v, (int, float)) and (v in (0, 5) if par["operator"] in ("==", "===", "!=", "!==")
                                                     else 0 <= v <= 4)
        # round 8 (Fable's fourth review): only a value the probe can set (a text such as 'pt_BR.UTF-8',
        # a read with no axis such as the orientation was accepted and never measured)
        axes = _env_axes()
        return axes is not None and axes.read_measured(key, par["operator"], v)
    # round 8: a truth test of a read (`!deviceMemory`, `cores || 4`) is measured only for the touch points,
    # whose values 0 and 5 the matrix has; every other read is compared with a literal the probe sets
    if key in TOUCH_READS and (par["type"] == "UnaryExpression" and par["operator"] == "!" or
                               par["type"] in ("IfStatement", "ConditionalExpression") and par.get("test") is node):
        return True
    return False


def _use_node(node, scopes):
    """The whole read a covered name starts (`screen.width`, `screen.orientation.type` from `screen`)."""
    while True:
        par = scopes.parent.get(id(node))
        if par is None or par["type"] != "MemberExpression" or par["object"] is not node or par["computed"]:
            return node
        node = par


def axis_literals(name, old, new):
    """What a change's new conditions compare the users' configurations with (round 7): [{"read", "op",
    "value"}] and [{"media": query}], for the probe to add sessions at those values (tools/env-axes.py
    derive). Empty when the scripts do not parse or the change adds nothing."""
    if name not in PROTECTED_JS:
        return []
    told, tnew = _js_parse(old), _js_parse(new)
    if told[0] is None or tnew[0] is None:
        return []
    r = _embed(told[0], tnew[0])
    if r is None:
        return []
    return _literals_of(r[1], _Scopes(tnew[0]), _env_axes())


def _literals_of(added, sn, axes):
    """axis_literals of the statements a change adds: the comparisons of covered reads with literals, the
    literal media queries, and (round 9) the touch, scheme, motion and colour reads, whose both values the
    joint sessions then meet with the change's other values."""
    out = []
    for s in added:
        for node in _walk(s):
            if node["type"] in ("Identifier", "MemberExpression") and _covered(node, sn, axes):
                key = _env_key(node, sn)
                par = sn.parent.get(id(_use_node(node, sn)))
                if key and par is not None and par["type"] == "BinaryExpression" and par["operator"] in COMPARE:
                    other = par["right"] if par["left"] is _use_node(node, sn) else par["left"]
                    v = _const_value(other)
                    if v is not None:
                        item = {"read": key, "op": par["operator"], "value": v}
                        if item not in out:
                            out.append(item)
            if node["type"] == "CallExpression" and node["arguments"] and \
                    _chain(node["callee"]) and _chain(node["callee"])[-1] == "matchMedia" and \
                    node["arguments"][0]["type"] == "Literal" and isinstance(node["arguments"][0].get("value"), str):
                item = {"media": node["arguments"][0]["value"]}
                if item not in out:
                    out.append(item)
            if node["type"] == "Identifier" and node["name"] in ("maxTouchPoints", "ontouchstart") or \
                    node["type"] == "MemberExpression" and _prop_name(node) in ("maxTouchPoints", "ontouchstart"):
                if _covered(node, sn, axes) and {"axis": "touch"} not in out:
                    out.append({"axis": "touch"})
    return out


def _root(node):
    while node["type"] == "MemberExpression":
        node = node["object"]
    return node


def _kids(node):
    """(key, child) for every child node."""
    for k, v in node.items():
        if k in ("start", "end", "type"):
            continue
        if isinstance(v, dict) and "type" in v:
            yield k, v
        elif isinstance(v, list):
            for x in v:
                if isinstance(x, dict) and "type" in x:
                    yield k, x


def _walk(node):
    yield node
    for _, c in _kids(node):
        yield from _walk(c)


def _equal(a, b):
    """The same tree, positions aside."""
    if isinstance(a, dict) and isinstance(b, dict):
        ka = [k for k in a if k not in ("start", "end")]
        if len(ka) != len([k for k in b if k not in ("start", "end")]):
            return False
        return all(k in b and _equal(a[k], b[k]) for k in ka)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_equal(x, y) for x, y in zip(a, b))
    return type(a) is type(b) and a == b


def _embed(o, n):
    """The new tree holds the old one, with statements only added to lists of statements: (pairs of old
    and new nodes, the added statements) or None."""
    if not (isinstance(o, dict) and isinstance(n, dict)) or o.get("type") != n.get("type"):
        return None
    pairs, added = [(o, n)], []
    keys = [k for k in o if k not in ("start", "end")]
    if set(keys) != {k for k in n if k not in ("start", "end")}:
        return None
    for k in keys:
        a, b = o[k], n[k]
        if (o["type"], k) in STMT_LISTS:
            j = 0
            for x in a:
                while j < len(b):
                    r = _embed(x, b[j])
                    if r is not None:
                        pairs += r[0]
                        added += r[1]
                        j += 1
                        break
                    added.append(b[j])
                    j += 1
                else:
                    return None
            added += b[j:]
        elif isinstance(a, dict) and "type" in a:
            r = _embed(a, b)
            if r is None:
                return None
            pairs += r[0]
            added += r[1]
        elif isinstance(a, list):
            if not isinstance(b, list) or len(a) != len(b):
                return None
            for x, y in zip(a, b):
                if isinstance(x, dict) and "type" in x:
                    r = _embed(x, y)
                    if r is None:
                        return None
                    pairs += r[0]
                    added += r[1]
                elif not _equal(x, y):
                    return None
        elif not _equal(a, b):
            return None
    return pairs, added


class _Scopes:
    """The bindings of a script (strict code: let, const, class and functions in their block, var in the
    function) and what every name used refers to."""

    def __init__(self, tree):
        self.parent = {}                 # id(node) -> parent node
        self.refs = {}                   # id(identifier used) -> binding (scope id, name) or None (global)
        self.decls = {}                  # binding -> [identifier nodes that declare it]
        self.decl_of = {}                # id(declaring identifier) -> binding
        self.values = {}                 # binding -> [value nodes given to it] (None: unknown)
        self._pending, self._assigned, self._by_id = [], [], {}
        self._visit(tree, None, None)
        for node, scope in self._pending:
            self.refs[id(node)] = self._resolve(scope, node["name"])
        # what is given to a name later: `x = value` (a value), a pattern, `+=`, ++, a loop's target (unknown);
        # given inside another function than the one that declares the name, at an unknown time (a timer's
        # callback, a listener): unknown
        for value, scope, name in self._assigned:
            key = self._resolve(scope, name)
            if key is not None and self._func_scope(self._by_id[key[0]]) is not self._func_scope(scope):
                value = None
            self.values.setdefault(key or (None, name), []).append(value)

    def _scope(self, node, parent, function):
        s = {"id": id(node), "node": node, "parent": parent, "names": {}, "function": function}
        self._by_id[id(node)] = s
        return s

    def _resolve(self, scope, name):
        while scope is not None:
            if name in scope["names"]:
                return scope["names"][name]
            scope = scope["parent"]
        return None

    def _func_scope(self, scope):
        while not scope["function"]:
            scope = scope["parent"]
        return scope

    def _declare(self, ident, scope, value=None):
        key = scope["names"].setdefault(ident["name"], (scope["id"], ident["name"]))
        self.decls.setdefault(key, []).append(ident)
        self.decl_of[id(ident)] = key
        if value is not False:
            self.values.setdefault(key, []).append(value)
        return key

    def _pattern(self, p, scope, value, parent):
        """Declares the names of a binding pattern (value: what is given to a plain name, None: unknown)."""
        if p is None:
            return
        self.parent[id(p)] = parent
        t = p["type"]
        if t == "Identifier":
            self._declare(p, scope, value)
        elif t == "ObjectPattern":
            for q in p["properties"]:
                self.parent[id(q)] = p
                if q["type"] == "RestElement":
                    self._pattern(q["argument"], scope, None, q)
                else:
                    if q.get("computed"):
                        self._visit(q["key"], q, scope)
                    self._pattern(q["value"], scope, None, q)
        elif t == "ArrayPattern":
            for q in p["elements"]:
                self._pattern(q, scope, None, p)
        elif t == "RestElement":
            self._pattern(p["argument"], scope, None, p)
        elif t == "AssignmentPattern":
            self._pattern(p["left"], scope, None, p)
            self._visit(p["right"], p, scope)

    def _function(self, fn, scope):
        fs = self._scope(fn, scope, True)
        if fn["type"] == "FunctionExpression" and fn.get("id"):
            self.parent[id(fn["id"])] = fn
            self._declare(fn["id"], fs, fn)
        for p in fn["params"]:
            self._pattern(p, fs, None, fn)
        body = fn["body"]
        self.parent[id(body)] = fn
        if body["type"] == "BlockStatement":
            self._hoist(body["body"], fs, fs)
            for s in body["body"]:
                self._visit(s, body, fs)
        else:
            self._visit(body, fn, fs)

    def _hoist(self, stmts, scope, fscope):
        """Declarations a list of statements makes before it runs: functions in this block, `var` (in
        nested blocks and loops too) in the function."""
        for s in stmts:
            if s["type"] == "FunctionDeclaration" and s.get("id"):
                self._declare(s["id"], scope, s)
            elif s["type"] == "ClassDeclaration" and s.get("id"):
                self._declare(s["id"], scope, s)
            elif s["type"] == "VariableDeclaration" and s["kind"] != "var":
                for d in s["declarations"]:
                    self._names_only(d["id"], scope)

    def _names_only(self, p, scope):
        """let/const names known in their block from its start (the values come at the declaration)."""
        if p is None:
            return
        t = p["type"]
        if t == "Identifier":
            scope["names"].setdefault(p["name"], (scope["id"], p["name"]))
        elif t == "ObjectPattern":
            for q in p["properties"]:
                self._names_only(q["argument"] if q["type"] == "RestElement" else q["value"], scope)
        elif t == "ArrayPattern":
            for q in p["elements"]:
                self._names_only(q, scope)
        elif t in ("RestElement",):
            self._names_only(p["argument"], scope)
        elif t == "AssignmentPattern":
            self._names_only(p["left"], scope)

    def _block(self, node, stmts, scope):
        bs = self._scope(node, scope, False)
        self._hoist(stmts, bs, self._func_scope(scope))
        for s in stmts:
            self._visit(s, node, bs)

    def _visit(self, node, parent, scope):
        if node is None:
            return
        self.parent[id(node)] = parent
        t = node["type"]
        if t == "Program":
            ps = self._scope(node, None, True)
            self._hoist(node["body"], ps, ps)
            for s in node["body"]:
                self._visit(s, node, ps)
            return
        if t == "VariableDeclaration":
            target = self._func_scope(scope) if node["kind"] == "var" else scope
            for d in node["declarations"]:
                self.parent[id(d)] = node
                if node["kind"] != "var" and d["id"]["type"] == "Identifier":
                    # a let or const named in its block by _hoist: the declaration itself
                    self._declare(d["id"], target, d["init"])
                    self.parent[id(d["id"])] = d
                else:
                    self._pattern(d["id"], target, d["init"] if d["id"]["type"] == "Identifier" else None, d)
                    if d["init"] is None and d["id"]["type"] == "Identifier":
                        self.values[self.decl_of[id(d["id"])]].pop()
                self._visit(d["init"], d, scope)
            return
        if t == "FunctionDeclaration":
            if node.get("id"):
                self.parent[id(node["id"])] = node
                if id(node["id"]) not in self.decl_of:
                    self._declare(node["id"], scope, node)
            self._function(node, scope)
            return
        if t in ("FunctionExpression", "ArrowFunctionExpression"):
            self._function(node, scope)
            return
        if t in ("ClassDeclaration", "ClassExpression"):
            cs = self._scope(node, scope, False)
            if node.get("id"):
                self.parent[id(node["id"])] = node
                if t == "ClassDeclaration" and id(node["id"]) not in self.decl_of:
                    self._declare(node["id"], scope, node)
                elif t == "ClassExpression":
                    self._declare(node["id"], cs, node)
            self._visit(node.get("superClass"), node, scope)
            self.parent[id(node["body"])] = node
            for m in node["body"]["body"]:
                self.parent[id(m)] = node["body"]
                if m["type"] == "StaticBlock":
                    self._block(m, m["body"], self._scope(m, cs, True))
                    continue
                if m.get("computed"):
                    self._visit(m["key"], m, cs)
                else:
                    self.parent[id(m["key"])] = m
                self._visit(m.get("value"), m, cs)
            return
        if t == "BlockStatement":
            self._block(node, node["body"], scope)
            return
        if t in ("ForStatement", "ForInStatement", "ForOfStatement"):
            hs = self._scope(node, scope, False)
            for k in ("init", "left"):
                if node.get(k) is not None and node[k]["type"] == "VariableDeclaration" and node[k]["kind"] != "var":
                    for d in node[k]["declarations"]:
                        self._names_only(d["id"], hs)
            for k, c in _kids(node):
                self._visit(c, node, hs)
            if t != "ForStatement":
                left, right = node["left"], node["right"]
                pats = [d["id"] for d in left["declarations"]] if left["type"] == "VariableDeclaration" else [left]
                # over a literal list, a plain name takes its elements (of) or its indexes (in); else unknown
                given = [None]
                if right["type"] == "ArrayExpression" and len(pats) == 1 and pats[0]["type"] == "Identifier":
                    given = list(right["elements"]) if t == "ForOfStatement" else \
                        [{"type": "Literal", "value": str(i)} for i in range(len(right["elements"]))]
                for p in pats:
                    for ident in _js_target_names(p):
                        for v in given:
                            self._assigned.append((v, hs, ident["name"]))
            return
        if t == "SwitchStatement":
            self._visit(node["discriminant"], node, scope)
            ss = self._scope(node, scope, False)
            self._hoist([s for c in node["cases"] for s in c["consequent"]], ss, self._func_scope(scope))
            for c in node["cases"]:
                self.parent[id(c)] = node
                self._visit(c.get("test"), c, ss)
                for s in c["consequent"]:
                    self._visit(s, c, ss)
            return
        if t == "CatchClause":
            cs = self._scope(node, scope, False)
            self._pattern(node.get("param"), cs, None, node)
            self.parent[id(node["body"])] = node
            self._block(node["body"], node["body"]["body"], cs)
            return
        if t == "Identifier":
            self._pending.append((node, scope))
            return
        if t == "MemberExpression":
            self._visit(node["object"], node, scope)
            if node["computed"]:
                self._visit(node["property"], node, scope)
            else:
                self.parent[id(node["property"])] = node
            return
        if t == "Property":
            if node["computed"]:
                self._visit(node["key"], node, scope)
            else:
                self.parent[id(node["key"])] = node
            self._visit(node["value"], node, scope)
            return
        if t in ("LabeledStatement", "BreakStatement", "ContinueStatement"):
            if node.get("label"):
                self.parent[id(node["label"])] = node
            self._visit(node.get("body"), node, scope)
            return
        if t == "MetaProperty":
            return
        if t == "AssignmentExpression":
            if node["left"]["type"] == "Identifier":
                value = node["right"] if node["operator"] == "=" else \
                    {"type": "_Compound", "operator": node["operator"][:-1], "right": node["right"]}
                self._assigned.append((value, scope, node["left"]["name"]))
            else:
                for ident in _js_target_names(node["left"]):
                    self._assigned.append((None, scope, ident["name"]))
        if t == "UpdateExpression" and node["argument"]["type"] == "Identifier":
            self._assigned.append(({"type": "_Update"}, scope, node["argument"]["name"]))
        for _, c in _kids(node):
            self._visit(c, node, scope)

    def binding(self, ident):
        """The binding a name refers to or declares (None: a global)."""
        return self.decl_of.get(id(ident)) or self.refs.get(id(ident))


def _js_target_names(p):
    """The plain names a target or pattern writes."""
    if p is None:
        return
    t = p["type"]
    if t == "Identifier":
        yield p
    elif t == "ObjectPattern":
        for q in p["properties"]:
            yield from _js_target_names(q["argument"] if q["type"] == "RestElement" else q["value"])
    elif t == "ArrayPattern":
        for q in p["elements"]:
            yield from _js_target_names(q)
    elif t == "RestElement":
        yield from _js_target_names(p["argument"])
    elif t == "AssignmentPattern":
        yield from _js_target_names(p["left"])


def _chain(node):
    """The names of a member chain without calls (`Object.defineProperty` -> ["Object", "defineProperty"],
    `w.Navigator.prototype` -> ["w", "Navigator", "prototype"]), or None."""
    out = []
    while node["type"] == "MemberExpression":
        p = _prop_name(node)
        if p is None:
            return None
        out.append(p)
        node = node["object"]
    if node["type"] == "Identifier":
        return [node["name"]] + out[::-1]
    if node["type"] == "ThisExpression":
        return ["this"] + out[::-1]
    return None


def _prop_name(member):
    """A member's property name (a literal text or number in brackets too), or None (computed)."""
    p = member["property"]
    if not member["computed"]:
        return p.get("name")
    if p["type"] == "Literal" and isinstance(p.get("value"), (str, int, float)) and not p.get("regex"):
        return str(p["value"])
    if p["type"] == "TemplateLiteral" and not p["expressions"]:
        return p["quasis"][0]["value"].get("cooked")
    return None


def _strip(node):
    while node is not None and node["type"] in ("ChainExpression",):
        node = node["expression"]
    return node


def _source_names(tree):
    """Every name and text a script has (for "a name the old script never has")."""
    out = set()
    for n in _walk(tree):
        if n["type"] in ("Identifier", "PrivateIdentifier"):
            out.add(n["name"])
        elif n["type"] == "Literal" and isinstance(n.get("value"), str):
            out.add(n["value"])
        elif n["type"] == "TemplateElement":
            out.add(n["value"].get("cooked") or "")
    return out


def _env_key(node, scopes):
    """What of the page's environment a node reads (ENV_NAMES), as `name` or `name.member`, or None: a
    global of that name or a property of that name, not on the way to an interface's prototype."""
    if node["type"] == "Identifier":
        if scopes.refs.get(id(node), 0) is not None or node["name"] not in ENV_NAMES:
            return None
        name, cur = node["name"], node
    elif node["type"] == "MemberExpression":
        name, cur = _prop_name(node), node
        if name not in ENV_NAMES:
            return None
    else:
        return None
    key, nxt, first = name, cur, None
    while True:
        par = scopes.parent.get(id(nxt))
        if par is None or par["type"] != "MemberExpression" or par["object"] is not nxt:
            break
        pn = _prop_name(par)
        if pn == "prototype":
            return None
        if first is None:
            first = pn
        nxt = par
    return key + ("." + first if first else "")


def _old_reads(tree, scopes):
    return {k for k in (_env_key(n, scopes) for n in _walk(tree)) if k}


def _function_info(tree, scopes):
    """The old functions that define properties (they or a function they call give an object a property
    by Object.defineProperty or the like): the bindings of their names. And the bindings that hold one
    of Object's or Reflect's functions that change an object (an alias such as DEFPROP)."""
    aliases = {}
    for key, values in scopes.values.items():
        for v in values:
            c = _chain(v) if isinstance(v, dict) and v["type"] == "MemberExpression" else None
            if c and tuple(c[-2:]) in OBJECT_MUTATORS:
                aliases[key] = tuple(c[-2:])
    funcs = {}
    for key, values in scopes.values.items():
        for v in values:
            if isinstance(v, dict) and v["type"] in FUNCTIONS:
                funcs.setdefault(key, []).append(v)

    def calls(fn):
        for n in _walk(fn["body"]):
            if n["type"] == "CallExpression":
                yield n

    definers = set()
    changed = True
    while changed:
        changed = False
        for key, fns in funcs.items():
            if key in definers:
                continue
            for fn in fns:
                for c in calls(fn):
                    callee = _strip(c["callee"])
                    ch = _chain(callee) if callee["type"] in ("MemberExpression", "Identifier") else None
                    target = scopes.binding(callee) if callee["type"] == "Identifier" else None
                    if (ch and tuple(ch[-2:]) in DEFINERS) or target in definers or \
                            aliases.get(target) in DEFINERS:
                        definers.add(key)
                        changed = True
                        break
                if key in definers:
                    break
    return definers, aliases


def _fresh(value, scopes):
    """A value that is a new object of the change's own: a literal object or list, a function, a class,
    `new` of a global constructor."""
    if value is None:
        return True
    t = value["type"]
    if t in ("ObjectExpression", "ArrayExpression", "ClassExpression") or t in FUNCTIONS:
        return True
    if t == "NewExpression" and value["callee"]["type"] == "Identifier" and \
            scopes.refs.get(id(value["callee"]), 0) is None:
        return True
    return False


def _prototype_like(value, scopes, seen=()):
    """A page interface's prototype (`X.prototype`, `w.X && w.X.prototype`) or a name given only that."""
    if value is None:
        return False
    t = value["type"]
    if t == "MemberExpression":
        c = _chain(value)
        return bool(c) and c[-1] == "prototype"
    if t == "LogicalExpression" and value["operator"] == "&&":
        return _prototype_like(value["right"], scopes, seen)
    if t == "Identifier":
        key = scopes.binding(value)
        if key is None or key in seen:
            return False
        vals = scopes.values.get(key) or []
        return bool(vals) and all(_prototype_like(v, scopes, seen + (key,)) for v in vals)
    return False


def page_tree_problems(name, old, new):
    """The rules (a) to (g) above on what a change adds to a page script, read by the syntax trees."""
    told = _js_parse(old)
    tnew = _js_parse(new)
    if told[0] is None or tnew[0] is None:
        which = "the old file" if told[0] is None else "the new file"
        return ["%s: %s does not parse as this guard reads JavaScript (%s): a page script must parse to be "
                "judged" % (name, which, (told[1] or tnew[1])[:120])], False
    t_old, t_new = told[0], tnew[0]
    r = _embed(t_old, t_new)
    if r is None:
        return ["%s: a statement of the old script is changed, moved or removed (only new statements may be "
                "added between the old ones)" % name], True
    pairs, added = r
    so, sn = _Scopes(t_old), _Scopes(t_new)
    match = {id(a): b for a, b in pairs}
    added_ids = set()
    for s in added:
        added_ids.update(id(n) for n in _walk(s))
    out = []

    def say(node, why):
        snippet = re.sub(r"\s+", " ", new[node["start"]:node["end"]])[:70]
        msg = "%s: %s (%s)" % (name, why, snippet)
        if msg not in out:
            out.append(msg)

    # bindings: the old code's names refer to what they did (a new declaration hides none of them)
    def same_binding(key_old, key_new):
        if key_old is None or key_new is None:
            return key_old is None and key_new is None
        scope = match.get(key_old[0])
        return scope is not None and id(scope) == key_new[0] and key_old[1] == key_new[1]
    for a, b in pairs:
        if a["type"] == "Identifier" and id(a) in so.refs:
            if not same_binding(so.refs[id(a)], sn.refs.get(id(b))):
                say(b, "a new declaration changes what the old code's %s refers to" % a["name"])

    def old_binding(key):
        return key is not None and any(id(d) not in added_ids for d in sn.decls.get(key, []))

    old_reads = _old_reads(t_old, so)
    old_names = _source_names(t_old)
    definers, aliases = _function_info(t_new, sn)
    consts = _constant_bindings(t_new, sn, added_ids)
    axes = _env_axes()
    clean_keys = _clean_bindings(t_new, sn, added_ids, axes)

    def constant(e):
        return _constant(e, sn, consts)

    def clean(e):
        return _clean(e, sn, clean_keys, axes)

    def fresh_obj(node):
        """An object the change made itself, named directly (round 9, Fable's review of round 8: `h.a` of a new
        `h` may hold an old object, `{a: Navigator.prototype}`, so only the new name itself counts)."""
        node = _strip(node)
        if node["type"] != "Identifier":
            return False
        key = sn.refs.get(id(node))
        if key is None or old_binding(key):
            return False
        return all(_fresh(v, sn) for v in sn.values.get(key, [None]))

    def root_ok(target):
        """A target new code writes: a new name, or a member of an object the change made, one level deep."""
        node = _strip(target)
        if node["type"] == "MemberExpression":
            return _prop_name(node) != "__proto__" and fresh_obj(node["object"])
        return fresh_obj(node)

    def write_targets(p):
        """The names and members a pattern or a target writes."""
        p = _strip(p)
        t = p["type"]
        if t in ("Identifier", "MemberExpression"):
            yield p
        elif t == "ObjectPattern":
            for q in p["properties"]:
                yield from write_targets(q["argument"] if q["type"] == "RestElement" else q["value"])
        elif t == "ArrayPattern":
            for q in p["elements"]:
                if q is not None:
                    yield from write_targets(q)
        elif t == "RestElement":
            yield from write_targets(p["argument"])
        elif t == "AssignmentPattern":
            yield from write_targets(p["left"])

    def check_write(target, node):
        value = node.get("right") if node["type"] == "AssignmentExpression" else None
        how = " (it gives a constant: a protection switched off?)" if value is not None and \
            value["type"] == "Literal" else ""
        if target["type"] == "Identifier":
            key = sn.binding(target)
            if key is None:
                say(node, "a new line assigns to the global %s%s: new code may only set names it declares" %
                    (target["name"], how))
            elif old_binding(key):
                say(node, "a new line assigns to %s, which the old script has%s: new code may only set names it "
                          "declares" % (target["name"], how))
        elif target["type"] == "MemberExpression":
            if target["computed"] and _prop_name(target) is None and not _numeric(target["property"], sn, consts):
                say(node, "a new line assigns to a property by a computed name")
            if not root_ok(target):
                c = _chain(target)
                say(node, "a new line assigns to %s, an object the change did not make (the old script's, the "
                          "page's or a global)%s" % (".".join(c) if c else "a property", how))

    renames = _renames()

    def renamed_copy(call):
        """A copy of an old call with only the engine's renamed names changed (tools/engine-renames.json)."""
        if not renames:
            return False
        for c in _walk(t_old):
            if c["type"] == "CallExpression":
                used, idents = [], []
                if not (_equal_renamed(c, call, renames, used, idents) and used):
                    continue
                # every name means what it meant in the old call: the same binding outside it, the copy's own
                # declaration where the old call declared its own
                mine = {}
                for a, b in idents:
                    if id(a) in so.decl_of and id(b) in sn.decl_of:
                        mine[so.decl_of[id(a)]] = sn.decl_of[id(b)]
                if all(sn.refs.get(id(b)) == mine.get(so.refs[id(a)], object()) or
                       same_binding(so.refs[id(a)], sn.refs.get(id(b)))
                       for a, b in idents if id(a) in so.refs and a["name"] == b["name"]):
                    return True
        return False

    def builtin_target(a, seen=()):
        """A target that is one of the language's own objects or its prototype (BUILTINS), by its names or
        an old name given only such a chain."""
        a = _strip(a)
        if a["type"] == "LogicalExpression":
            return builtin_target(a["left"], seen) or builtin_target(a["right"], seen)
        if a["type"] in ("Identifier", "MemberExpression"):
            ch = _chain(a) or []
            if any(x in BUILTINS for x in ch):
                return True
            if a["type"] == "Identifier":
                key = sn.binding(a)
                if key is not None and key not in seen:
                    return any(isinstance(v, dict) and builtin_target(v, seen + (key,))
                               for v in sn.values.get(key, []) if v is not None)
        return False

    def defining_call(call, how):
        """(f): a call that defines a property (an I.K.E. helper or Object.defineProperty and the like)."""
        args = call["arguments"]
        if how == "native" and args and fresh_obj(args[0]):
            return
        if any(builtin_target(a) for a in args if a["type"] not in FUNCTIONS):
            say(call, "a new call defines or wraps a property of the language's own objects (String, Function, "
                      "Math, Reflect, Array...), which the old script relies on: only page interfaces")
            return
        if renamed_copy(call):
            return
        # round 9 (Fable's review of round 8): every argument is a literal name, a function, a descriptor of
        # literals and functions, or a page interface's prototype named by its chain; exactly one name. A
        # name or a target laundered through a new object (`h.prototype` of `{prototype: 'x'}`), an object
        # whose toString gives the name, or a decoy literal beside it, is no new disguise
        protos = [a for a in args if a["type"] not in FUNCTIONS and _fold_text(a, sn, consts) is None and
                  a["type"] != "ObjectExpression"]
        for a in protos:
            why = interface_target(a)
            if why:
                say(call, why)
                return
        names = [a for a in args if _fold_text(a, sn, consts) is not None]
        if len(names) != 1:
            say(call, "a new call that defines a property names %s by a literal: exactly one name, beside a "
                      "prototype and functions" % ("none" if not names else "more than one"))
            return
        for a in args:
            if a["type"] == "ObjectExpression" and not all(
                    p["type"] == "Property" and not p["computed"] and p["key"].get("type") == "Identifier" and
                    p["key"]["name"] in DESCRIPTOR_KEYS and
                    (p["value"]["type"] in FUNCTIONS or p["value"]["type"] == "Literal") for p in a["properties"]):
                say(call, "a new call that defines a property is given an object that is no plain descriptor "
                          "(get, set, value, enumerable, configurable, writable of functions and literals)")
                return
        texts = []
        for a in args:
            s = _fold_text(a, sn, consts)
            if s is not None:
                texts.append(s)
                continue
            if a["type"] in FUNCTIONS:
                continue
            if a["type"] == "ObjectExpression" and all(
                    p["type"] == "Property" and not p["computed"] and
                    (p["value"]["type"] in FUNCTIONS or p["value"]["type"] == "Literal") for p in a["properties"]):
                continue
            if _prototype_like(a, sn):
                continue
            say(call, "a new call that defines a property takes something that is neither a prototype nor a "
                      "literal name (%s): new code defines new properties only" %
                re.sub(r"\s+", " ", new[a["start"]:a["end"]])[:40])
            return
        if not texts:
            say(call, "a new call that defines a property names none by a literal")
        for s in texts:
            if s in INHERITED_NAMES:
                say(call, "a new call defines %s, a name every object has (the old code's coercions and promises "
                          "look it up): only a new name is a new disguise" % s)
            if s in old_names:
                say(call, "a new call defines or wraps %s again, which the old script already protects or "
                          "names: only a person changes a protection" % s)

    def interface_target(a, seen=()):
        """Why a target of a new definition is not a page interface's prototype the old script covers (None
        when it is): `X.prototype` or `w.X.prototype` (w a global or an old name), or a new name given only
        such chains; X named in the old script, neither one of the language's objects nor the window, its
        events and its document (a new global, a changed isTrusted)."""
        a = _strip(a)
        if a["type"] == "LogicalExpression" and a["operator"] == "&&":
            return interface_target(a["right"], seen)
        if a["type"] == "Identifier":
            key = sn.binding(a)
            vals = sn.values.get(key) or [] if key is not None else []
            if key is None or key in seen or not vals or old_binding(key) and not all(
                    isinstance(v, dict) for v in vals):
                return "a new call that defines a property on %s, which is not a page interface's prototype" % \
                    a["name"]
            for v in vals:
                why = interface_target(v, seen + (key,)) if isinstance(v, dict) else "unknown"
                if why:
                    return why
            return None
        ch = _chain(a) if a["type"] == "MemberExpression" else None
        if not ch or ch[-1] != "prototype" or len(ch) not in (2, 3):
            return "a new call that defines a property on something that is not a page interface's prototype"
        root = _strip(a["object"]["object"]) if len(ch) == 3 else _strip(a["object"])
        key = sn.refs.get(id(root), 0)
        # X.prototype: X a global; w.X.prototype: w a global or an old name (install's window)
        if root["type"] != "Identifier" or key == 0 or (len(ch) == 2 and key is not None) or \
                (key is not None and not old_binding(key)):
            return "a new call that defines a property on a prototype reached through a new object"
        iface = ch[-2]
        if not re.fullmatch(r"[A-Z][A-Za-z0-9]*", iface):
            return "a new call that defines a property on %s.prototype, which is no page interface" % iface
        if iface in BUILTINS:
            return ("a new call defines or wraps a property of the language's own objects (String, Function, "
                    "Math, Reflect, Array...), which the old script relies on: only page interfaces")
        if iface in GLOBAL_INTERFACES or iface not in old_names:
            return ("a new call that defines a property on %s: only the page interfaces the old script covers "
                    "(not the window, its events, nodes and document)" % iface)
        return None

    helpers = PAGE_HELPERS.get(name, frozenset())

    def old_function(key):
        """An old binding that holds one of the old script's own functions."""
        if not old_binding(key):
            return False
        decl = sn.decls.get(key) or []
        if any((sn.parent.get(id(d)) or {}).get("type") == "FunctionDeclaration" and
               sn.parent[id(d)].get("id") is d for d in decl):
            return True
        return any(isinstance(v, dict) and v.get("type") in FUNCTIONS for v in sn.values.get(key, []))

    def direct_callee(node):
        par = sn.parent.get(id(node))
        return par is not None and par["type"] == "CallExpression" and par["callee"] is node

    def visit(node, in_new_fn, loops, switches, labels):
        t = node["type"]
        if t == "CallExpression" and renamed_copy(node):
            return                       # an old wrap again, only the engine's renamed names changed
        # round 8 (Fable's fourth review): a function that defines a property is used only as the direct
        # callee of a call, where rule (f) judges what it is given (wrap.call(...), wrap.apply, wrap.bind,
        # Reflect.apply(wrap, ...), (0, wrap)(...), an alias, `new`, a tag re-wrapped a protected property)
        if t == "Identifier" and id(node) in sn.refs:
            key = sn.refs[id(node)]
            if key is not None and (key in definers or aliases.get(key) in OBJECT_MUTATORS) and \
                    not direct_callee(node):
                say(node, "a new indirect use of %s, a function that defines properties (only called directly, "
                          "where what it is given is judged)" % node["name"])
        if t in ("Identifier", "MemberExpression"):
            nm = node.get("name") if t == "Identifier" else _prop_name(node)
            global_name = t == "MemberExpression" or sn.refs.get(id(node), 0) is None
            par = sn.parent.get(id(node))
            if nm in OBJECT_HOLDERS and global_name and not (
                    par is not None and par["type"] == "MemberExpression" and par["object"] is node or
                    direct_callee(node) and nm == "Object" or
                    par is not None and par["type"] == "BinaryExpression" and par["operator"] == "instanceof" and
                    par["right"] is node or
                    par is not None and par["type"] == "UnaryExpression" and par["operator"] == "typeof"):
                say(node, "a new use of %s itself (only its functions, by name: an alias of it hides a "
                          "definition from the guard)" % nm)
            if t == "MemberExpression" and _prop_name(node) in ("__defineGetter__", "__defineSetter__",
                                                                 "__lookupGetter__", "__lookupSetter__"):
                say(node, "a new use of .%s" % _prop_name(node))
            if t == "MemberExpression" and _prop_name(node) in MUTATING_METHODS and not direct_callee(node):
                say(node, "a new indirect use of .%s, a method that changes its object (only called directly "
                          "on an object the change made)" % _prop_name(node))
            if t == "MemberExpression":
                ch = _chain(node)
                if ch and tuple(ch[-2:]) in OBJECT_MUTATORS and not direct_callee(node):
                    say(node, "a new indirect use of %s.%s (only called directly, where what it is given is "
                              "judged)" % tuple(ch[-2:]))
        if t == "Identifier" and id(node) in sn.refs:
            key = sn.refs[id(node)]
            if key is not None and old_function(key) and node["name"] not in helpers:
                say(node, "a new use of the old function %s (it runs old code again, or keeps new code in old "
                          "state): new code calls only the pure helpers and wrap, getter, setter" % node["name"])
        if t in ("FunctionDeclaration", "ClassDeclaration") and node.get("id"):
            key = sn.decl_of.get(id(node["id"]))
            if key is not None and old_binding(key):
                say(node, "a new line declares %s again, which the old script already has" % node["id"]["name"])
        if t in FUNCTIONS:
            if node.get("async") or node.get("generator"):
                say(node, "a new async function or generator (code that runs later)")
            for p in node["params"]:
                for q in _walk(p):
                    if q["type"] == "AssignmentPattern" and not clean(q["right"]):
                        say(q, "a new default value that is not a measured one (%s)" % COVERED_HINT)
            body = node["body"]
            for _, c in _kids(node):
                if c is not body and c not in node["params"]:
                    visit(c, in_new_fn, loops, switches, labels)
            for p in node["params"]:
                visit(p, True, 0, 0, ())
            visit(body, True, 0, 0, ())
            return
        if t in ("ReturnStatement", "ThrowStatement") and not in_new_fn:
            say(node, "a new line leaves the old code (%s outside a function the change adds)" %
                ("return" if t == "ReturnStatement" else "throw"))
        if t in ("BreakStatement", "ContinueStatement"):
            lab = node.get("label")
            if lab is not None:
                if lab["name"] not in labels:
                    say(node, "a new line leaves the old code (%s %s, a label the change did not add)" %
                        (t[:-9].lower(), lab["name"]))
            elif not (loops or (t == "BreakStatement" and switches)):
                say(node, "a new line leaves the old code (%s out of a loop or switch the change did not add)" %
                    t[:-9].lower())
        if t == "WithStatement":
            say(node, "a new with statement")
        if t == "ImportExpression":
            say(node, "a new import()")
        if t in ("IfStatement", "ConditionalExpression") and not clean(node["test"]):
            say(node, "a new condition on data no measurement covers (%s): a condition the measurement cannot "
                      "make true is what hides a weakening" % COVERED_HINT)
        if t == "LogicalExpression" and not clean(node["left"]):
            say(node, "a new %s on data no measurement covers (%s)" % (node["operator"], COVERED_HINT))
        if t == "SwitchStatement" and not (clean(node["discriminant"]) and
                                           all(c["test"] is None or clean(c["test"]) for c in node["cases"])):
            say(node, "a new switch on data no measurement covers (%s)" % COVERED_HINT)
        if t in ("WhileStatement", "DoWhileStatement", "ForStatement"):
            test = node.get("test")
            if test is None or (test["type"] == "Literal" and test.get("value")):
                say(node, "a new loop that never ends")
            elif not clean(test):
                say(node, "a new loop whose end depends on data no measurement covers (%s)" % COVERED_HINT)
        if t in ("ForInStatement", "ForOfStatement"):
            if not clean(node["right"]):
                say(node, "a new loop over data no measurement covers (%s)" % COVERED_HINT)
            if node["left"]["type"] != "VariableDeclaration":
                for tg in write_targets(node["left"]):
                    check_write(tg, node)
        if t == "ChainExpression":
            for q in _walk(node["expression"]):
                if q.get("optional") and not clean(q.get("object") or q.get("callee")):
                    say(node, "a new optional chain ?. on data no measurement covers (%s)" % COVERED_HINT)
                    break
        if t == "AssignmentPattern" and sn.parent.get(id(node), {}).get("type") not in FUNCTIONS and \
                not clean(node["right"]):
            say(node, "a new default value that is not a measured one (%s)" % COVERED_HINT)
        if t == "TryStatement" and (node.get("finalizer") or node.get("handler") and not all(
                s["type"] == "ReturnStatement" and (s["argument"] is None or clean(s["argument"]))
                for s in node["handler"]["body"]["body"])):
            say(node, "a new catch or finally that does something (a branch on an error; a catch may only give a "
                      "measured value back: %s)" % COVERED_HINT)
        if t == "AssignmentExpression":
            for tg in write_targets(node["left"]):
                check_write(tg, node)
            if node["operator"] in ("||=", "&&=", "??=") and not clean(node["left"]):
                say(node, "a new %s on data no measurement covers (%s)" % (node["operator"], COVERED_HINT))
        if t == "UpdateExpression":
            check_write(_strip(node["argument"]), node)
        if t == "UnaryExpression" and node["operator"] == "delete":
            arg = _strip(node["argument"])
            if arg["type"] == "MemberExpression":
                check_write(arg, node)
            else:
                say(node, "a new delete")
        if t == "VariableDeclarator":
            for q in _walk(node["id"]):
                if q["type"] == "Identifier" and id(q) in sn.decl_of and old_binding(sn.decl_of[id(q)]):
                    say(node, "a new line declares %s again, which the old script already has" % q["name"])
        if t == "MemberExpression":
            pn = _prop_name(node)
            if node["computed"] and pn is None and not _numeric(node["property"], sn, consts):
                say(node, "a new property reached by a computed name (only a literal, or a number from the "
                          "change's own counters)")
            if pn in ("constructor", "__proto__", "caller", "callee"):
                say(node, "a new reach of .%s" % pn)
        if t in ("Property", "MethodDefinition", "PropertyDefinition") and node.get("computed") and not (
                node["key"]["type"] == "Literal" or _numeric(node["key"], sn, consts)):
            say(node, "a new property with a computed name")
        if t == "Identifier" and sn.refs.get(id(node), 0) is None and node["name"] in ("eval", "Function"):
            par = sn.parent.get(id(node))
            if not (par and par["type"] == "MemberExpression" and par["object"] is node and
                    _prop_name(par) == "prototype"):
                say(node, "a new use of %s (code from a text)" % node["name"])
        if t in ("Identifier", "MemberExpression"):
            key = _env_key(node, sn)
            if key and not _covered(node, sn, axes) and not (in_new_fn and key in old_reads):
                say(node, "a new line reads the page's environment (%s): where or when the page is, its screen, "
                          "device or chance, timers and events (inside a function the change adds, only what the "
                          "old script reads too)" % key)
        if t == "AwaitExpression":
            say(node, "a new await (code that runs later)")
        if t == "CallExpression":
            callee = _strip(node["callee"])
            ch = _chain(callee) if callee["type"] in ("MemberExpression", "Identifier") else None
            key = sn.binding(callee) if callee["type"] == "Identifier" else None
            pair = tuple(ch[-2:]) if ch and len(ch) >= 2 else None
            native = pair in OBJECT_MUTATORS or aliases.get(key) in OBJECT_MUTATORS
            if native:
                kind = pair if pair in OBJECT_MUTATORS else aliases.get(key)
                if kind in DEFINERS:
                    defining_call(node, "native")
                elif not (node["arguments"] and fresh_obj(node["arguments"][0])):
                    say(node, "a new call of %s.%s changes an object the change did not make" % kind)
            elif key is not None and key in definers:
                defining_call(node, "helper")
            if callee["type"] == "MemberExpression":
                m = _prop_name(callee)
                if m in MUTATING_METHODS and not fresh_obj(callee["object"]):
                    say(node, "a new call of .%s changes an object the change did not make" % m)
                if m in ("call", "apply") and callee["object"]["type"] == "MemberExpression" and \
                        _prop_name(callee["object"]) in MUTATING_METHODS and \
                        not (node["arguments"] and fresh_obj(node["arguments"][0])):
                    say(node, "a new call of .%s on an object the change did not make" % _prop_name(callee["object"]))
            # Reflect.apply (or an old name for it) of a method that changes its object
            applied = pair == ("Reflect", "apply") or any(
                v is not None and v["type"] == "MemberExpression" and _chain(v) and tuple(_chain(v)[-2:]) ==
                ("Reflect", "apply") for v in (sn.values.get(key) or []) if isinstance(v, dict))
            if applied and len(node["arguments"]) >= 2:
                fn = _strip(node["arguments"][0])
                names = []
                if fn["type"] == "MemberExpression":
                    names = [_prop_name(fn)]
                elif fn["type"] == "Identifier":
                    for v in sn.values.get(sn.binding(fn), []) or []:
                        if isinstance(v, dict) and v["type"] == "MemberExpression":
                            names.append(_prop_name(v))
                if any(n in MUTATING_METHODS for n in names) and not fresh_obj(node["arguments"][1]):
                    say(node, "a new call applies a method that changes an object the change did not make")
        if t in LOOPS:
            for k, c in _kids(node):
                visit(c, in_new_fn, loops + (1 if k == "body" else 0), switches, labels)
            return
        if t == "SwitchStatement":
            for _, c in _kids(node):
                visit(c, in_new_fn, loops, switches + 1, labels)
            return
        if t == "LabeledStatement":
            visit(node["body"], in_new_fn, loops, switches, labels + (node["label"]["name"],))
            return
        for _, c in _kids(node):
            visit(c, in_new_fn, loops, switches, labels)

    def primitive(e, seen=()):
        """A value that cannot throw when read or combined: a literal (no BigInt), a covered read of the
        environment, a var of the change's or the old script's given only such values."""
        e = _strip(e)
        tt = e["type"]
        if tt == "Literal":
            return "bigint" not in e
        if tt == "TemplateLiteral":
            return all(primitive(x, seen) for x in e["expressions"])
        if _covered(e, sn, axes) or (tt == "CallExpression" and _covered(e["callee"], sn, axes)):
            return True
        if tt == "MemberExpression" and _prop_name(e) == "matches" and e["object"]["type"] == "CallExpression" \
                and _covered(e["object"]["callee"], sn, axes):
            return True
        if tt == "MemberExpression" and e["object"]["type"] == "Identifier" and _covered(e["object"], sn, axes):
            return True                  # screen.width: the read is named by the global and its member
        if tt == "Identifier":
            key = sn.refs.get(id(e), 0)
            if key is None:
                return e["name"] in CONSTANT_GLOBALS
            if key in (0,) or key in seen or binding_kind(key) not in ("var", "function"):
                return False
            vals = sn.values.get(key, [])
            return all(v is None or (isinstance(v, dict) and v["type"] in FUNCTIONS) or
                       (isinstance(v, dict) and primitive(v, seen + (key,))) for v in vals)
        if tt == "UnaryExpression":
            return e["operator"] in SAFE_UNARY and primitive(e["argument"], seen) or \
                e["operator"] == "typeof" and (e["argument"]["type"] == "Identifier" or primitive(e["argument"], seen))
        if tt in ("BinaryExpression", "LogicalExpression"):
            return e["operator"] not in ("in", "instanceof") and primitive(e["left"], seen) and primitive(e["right"], seen)
        if tt == "ConditionalExpression":
            return all(primitive(e[k], seen) for k in ("test", "consequent", "alternate"))
        return False

    def safe_init(e):
        """What a new declaration among the old statements may be given: it cannot throw."""
        if e is None or e["type"] in FUNCTIONS:
            return True
        if e["type"] == "ArrayExpression":
            return all(x is None or (x["type"] != "SpreadElement" and safe_init(x)) for x in e["elements"])
        if e["type"] == "ObjectExpression":
            return all(q["type"] == "Property" and not q["computed"] and
                       (q["kind"] != "init" or q["method"] or safe_init(q["value"])) for q in e["properties"])
        return primitive(e)

    def binding_kind(key):
        decl = (sn.decls.get(key) or [None])[0]
        par = sn.parent.get(id(decl)) if decl is not None else None
        if par is None:
            return None
        if par["type"] == "VariableDeclarator":
            return (sn.parent.get(id(par)) or {}).get("kind")
        if par["type"] == "FunctionDeclaration":
            return "function"
        if par["type"] in FUNCTIONS:
            return "param"
        return par["type"]

    def placed(s):
        """Round 7 (Fable's third review): a new statement in a list of the old code's own runs in the old
        code's flow, where a throw without `throw` (a property of undefined, a call of no function, a
        recursion, new Array(-1), 1n + 1, a let read too early) stops the old statements after it, or an old
        `catch` swallows it and skips the rest of its block; before the first statement it demotes a
        directive ('use strict'). So it comes after the last old statement of its list, and is a declaration
        that cannot throw, or `try { ... } catch (e) {}`."""
        par = sn.parent.get(id(s))
        if par is None or id(par) in added_ids:
            return
        lst = par.get("body") if par["type"] in ("Program", "BlockStatement", "StaticBlock") else \
            par.get("consequent") if par["type"] == "SwitchCase" else None
        if not isinstance(lst, list):
            return
        at = next((i for i, x in enumerate(lst) if x is s), None)
        olds = [i for i, x in enumerate(lst) if id(x) not in added_ids]
        if at is not None and olds and at < max(olds):
            say(s, "a new statement before an old one of its block (it can stop or skip the old ones after it, "
                   "or demote a directive): new code comes after the last old statement")
        kind = s["type"]
        if kind in ("FunctionDeclaration", "EmptyStatement"):
            return
        if kind == "VariableDeclaration" and s["kind"] == "var" and all(safe_init(d["init"]) for d in s["declarations"]):
            return
        if kind == "TryStatement" and s.get("handler") is not None and not s["handler"]["body"]["body"] and \
                s.get("finalizer") is None:
            return
        say(s, "a new statement that runs in the old code's flow and may throw (a throw without `throw` stops "
               "the old code): there only declarations that cannot throw; what runs goes in "
               "`try { ... } catch (e) {}` after the last old statement")

    for s in added:
        placed(s)
        visit(s, False, 0, 0, ())
    # round 9 (Fable's review of round 8): what the probe cannot set together. A window's size and its
    # screen's in one change (a half-width window on a wide screen: the sessions have the window at the
    # screen's size); more values or combinations than a run measures
    if axes is not None and added:
        kinds = set(axes.derive(_literals_of(added, sn, axes)))
        for dim in ("width", "height"):
            if {"viewport-" + dim, "screen-" + dim} <= kinds:
                say(added[0], "a new condition on both the window's %s and the screen's: the measurement sets "
                              "the window at the screen's size, so no session could tell them apart" % dim)
        if axes.too_many(_literals_of(added, sn, axes)):
            say(added[0], "a new condition compares the configurations with more values than a run of the "
                          "measurement sets (tools/env-axes.py MAX_DERIVED, MAX_JOINT)")
    return out, True


def _constant_bindings(tree, scopes, added_ids):
    """The change's own names given only constants (literals and other such names): its counters."""
    keys = {}
    for key, decl in scopes.decls.items():
        if key is not None and decl and all(id(d) in added_ids for d in decl):
            keys[key] = scopes.values.get(key, [])
    consts = set(keys)
    changed = True
    while changed:
        changed = False
        for key in list(consts):
            vals = keys[key]
            if not all(v is not None and _constant(v, scopes, consts) for v in vals):
                consts.discard(key)
                changed = True
    return consts


def _constant(e, scopes, consts):
    """Built only from literals and the change's own constant names."""
    if e is None:
        return False
    t = e["type"]
    if t in ("Literal", "_Update"):
        return True
    if t == "_Compound":
        return e["operator"] not in ("||", "&&", "??") and _constant(e["right"], scopes, consts)
    if t == "TemplateLiteral":
        return all(_constant(x, scopes, consts) for x in e["expressions"])
    if t == "Identifier":
        key = scopes.refs.get(id(e), 0)
        if key is None:
            return e["name"] in CONSTANT_GLOBALS
        return key in consts
    if t in ("UnaryExpression",):
        return e["operator"] != "delete" and _constant(e["argument"], scopes, consts)
    if t in ("BinaryExpression", "LogicalExpression"):
        return e["operator"] not in ("in", "instanceof") and _constant(e["left"], scopes, consts) and \
            _constant(e["right"], scopes, consts)
    if t == "ConditionalExpression":
        return all(_constant(e[k], scopes, consts) for k in ("test", "consequent", "alternate"))
    if t == "SequenceExpression":
        return all(_constant(x, scopes, consts) for x in e["expressions"])
    if t == "ArrayExpression":
        return all(x is not None and _constant(x, scopes, consts) for x in e["elements"])
    return False


NUMERIC_OPS = {"-", "*", "/", "%", "**", "|", "&", "^", "<<", ">>", ">>>"}


def _numeric(e, scopes, consts, seen=()):
    """A number, whatever its operands: a numeric literal, arithmetic (-, *, /, %, **, bit operations, unary
    -, + and ~ always give a number; + only of numbers), a length, an update, or the change's own name given
    only such numbers in its own function. A computed property's name built so is an index, never a text
    built from parts (`window['loc' + 'ation']`)."""
    t = e["type"]
    if t == "Literal":
        return isinstance(e.get("value"), (int, float)) and not isinstance(e.get("value"), bool)
    if t == "Identifier":
        key = scopes.refs.get(id(e), 0)
        if key in (0, None) or key in seen or not scopes.decls.get(key):
            return False
        vals = scopes.values.get(key, [])
        return bool(vals) and all(v is not None and _numeric(v, scopes, consts, seen + (key,)) for v in vals)
    if t == "UnaryExpression":
        return e["operator"] in ("-", "+", "~")
    if t == "BinaryExpression":
        if e["operator"] in NUMERIC_OPS:
            return True
        return e["operator"] == "+" and _numeric(e["left"], scopes, consts, seen) and \
            _numeric(e["right"], scopes, consts, seen)
    if t == "MemberExpression":
        return not e["computed"] and _prop_name(e) == "length"
    if t in ("UpdateExpression", "_Update"):
        return True
    if t == "_Compound":
        if e["operator"] in NUMERIC_OPS:
            return True
        return e["operator"] == "+" and _numeric(e["right"], scopes, consts, seen)
    if t == "ConditionalExpression":
        return _numeric(e["consequent"], scopes, consts, seen) and _numeric(e["alternate"], scopes, consts, seen)
    if t == "SequenceExpression":
        return _numeric(e["expressions"][-1], scopes, consts, seen)
    return False


def _fold_text(e, scopes, consts):
    """The text a constant expression gives (a literal, a template without names, `+` of such), or None."""
    t = e["type"]
    if t == "Literal" and isinstance(e.get("value"), str):
        return e["value"]
    if t == "TemplateLiteral" and not e["expressions"]:
        return e["quasis"][0]["value"].get("cooked")
    if t == "BinaryExpression" and e["operator"] == "+":
        a, b = _fold_text(e["left"], scopes, consts), _fold_text(e["right"], scopes, consts)
        if a is not None and b is not None:
            return a + b
        return None
    if t == "Identifier":
        key = scopes.refs.get(id(e), 0)
        if key in consts:
            vals = scopes.values.get(key, [])
            if len(vals) == 1 and vals[0] is not None:
                return _fold_text(vals[0], scopes, consts)
    return None


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


def _named_sites(name, line):
    """A site named in a pattern or a text of a new line of a page script (round 5, F1)."""
    out = []
    code = re.sub(r"//.*$", "", line) if "//" in line and not re.search(r"[\"'`/][^\"'`]*//", line) else line
    for m in REGEX_LITERAL.finditer(code):
        if PAGE_BRANDS.search(m.group(1)):
            out.append("%s: a new pattern names sites (/%s/): a protection may not depend on the site" % (
                name, m.group(1)[:50]))
            break
    for s in re.findall(r"'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"|`(?:\\.|[^`\\])*`", code):
        if re.search(r"(?:google|youtube|facebook|instagram|amazon|cloudflare|captcha|microsoft|apple|paypal"
                      r"|twitter|tiktok)\.", s, re.I) or re.search(r"\(\s*(?:com|org|net)\s*\|", s):
            out.append("%s: a new text names a site (%s)" % (name, s[:50]))
            break
    return out


def line_additive(name, old, new, risky, structural=True):
    """Rule 5: every old line of code is still there, in order; the new lines do not leave old code,
    switch something off or reach out. structural=False (a page script whose syntax trees judge it,
    page_tree_problems): only the old lines, the blocks, the always-true conditions, what reaches out,
    the named sites and the new addresses are judged here."""
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
        if name in PROTECTED_JS:
            out += page_script_problems(name, run, had, known, structural)
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
            if not structural:
                d = None
            if d and d.group(2) in had and (level <= 0 or d.group(1).startswith("var")):
                out.append("%s: a new line declares %s again, which the old file already declares (%s)"
                           % (name, d.group(2), line[:60]))
            elif d and level > 0:
                mine.add(d.group(2))
            a = None if d or not structural else ASSIGNS.match(bare)
            if a and a.group(1) in had and a.group(1) not in mine and a.group(1) not in ("self", "this"):
                out.append("%s: a new line assigns to %s, which the old file declares (%s)"
                           % (name, (a.group(1) + a.group(2)).replace(" ", "")[:40], line[:60]))
            if structural and EXIT_WORD.search(bare) and level <= 0 and not re.search(
                    r"\b(?:function\b|fn\s|=>)", bare.split("return")[0].split("throw")[0]):
                out.append("%s: a new line leaves the old code (%s): only inside a block the change itself opens"
                           % (name, line[:70]))
            if re.search(r"^\s*(?:\}\s*)?(?:else\s+)?if\s*\(\s*(?:true|1|!0|!false)\s*\)|^\s*if\s+true\b", bare):
                out.append("%s: a new condition that is always true (%s)" % (name, line[:70]))
            if risky.search(bare):
                out.append("%s: a new line reaches out or loads code (%s)" % (name, line[:70]))
            m = CONSTANT_ASSIGN.match(bare) if structural else None
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
    if name in PROTECTED_JS:
        tree, parsed = page_tree_problems(name, old, new)
        return line_additive(name, old, new, risky, structural=not parsed) + tree
    return line_additive(name, old, new, risky)


# What only the measuring tools say (2026-11-24, the review of "Nothing gets worse"): code an AI adds
# that names one of these could recognise the measurement or a test run and behave differently there.
MEASUREMENT = re.compile(r"IKE_TEST_\w*|IKE_NR\w*|IKE_ALLOW_UNSAFE_ENGINE|IKE_NO_SINGLE|nrResult|nr-third|"
                         r"no[-_ ]regression|nothing gets worse|offscreen|QT_QPA_PLATFORM|platformName|profile_keys|"
                         r"swiftshader|QTWEBENGINE_DISABLE_SANDBOX|DBUS_SESSION_BUS_ADDRESS|GITHUB_ACTIONS|"
                         r"\bCI\b|RUNNER_\w*|127\.0\.0\.1|\blocalhost\b|\.example\b|addaudithook|sys\.modules|"
                         r"Sphinx of black quartz|known ?bytes|1103515245", re.I)


def measurement_problems(name, old, new):
    """The names of the measurement (MEASUREMENT) a change adds to a file: refused."""
    def count(text):
        out = {}
        for m in MEASUREMENT.finditer(text or ""):
            out[m.group(0).lower()] = out.get(m.group(0).lower(), 0) + 1
        return out
    before, after = count(old), count(new)
    return ["%s: it names what measures it (%s): code must not tell a test or \"Nothing gets worse\" from a "
            "user" % (name, w) for w in sorted(after) if after[w] > before.get(w, 0)]


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
        out += measurement_problems(name, old, new)
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
