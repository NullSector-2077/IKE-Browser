#!/usr/bin/env python3
"""Tier B in its narrowest safe form, behind the owner's switch (AUTOMAT part 2; no AI here).

Tier B (tools/fix-guard.py) is what no AI changes: the workflows, the tests, the tools, the engine's
sandbox and start, the signing and update channel, the package. The owner asked that nothing stays
behind; the concern stands: a workflow step an AI may edit is arbitrary shell in a job that holds
tokens. So this file opens only what a program can prove harmless, and only when the owner turned the
repository variable ``AUTOMAT_TIER_B`` to ``on`` (GitHub's settings: only the owner can; a file of the
repository never can). Off, the default: nothing here is used and tier B is never an AI's.

What opens, and nothing else:

1. **A workflow where nothing changes but a pinned version** (workflow_problem; the logic of
   tools/ci-pins.py, line by line): the file keeps its number of lines; every changed line is, before
   and after, the same pin: an action's full commit with its version comment (the same action, a
   release tag, and that commit is the tag's own, read with `git ls-remote` from the action's
   repository), a tool's version string (cargo-deny), or a runtime version (Python, Node.js, a numeric
   Rust toolchain). Never older than before. So never a command, a permission, a secret, a trigger,
   `runs-on`, a new step or any other line: such a line is no pin and is refused.
2. **Python in ike/app.py, ike/updater.py and ike_boot.py** under tier A's additive rule and
   capability rule of tools/fix-guard.py (every old statement still there, no old name bound again,
   nothing new that reaches out), plus fixed invariants (python_problems):
   - *frozen functions*: every function of the update channel (ike/updater.py, ike_boot.py:
     FROZEN_FILES) and, in ike/app.py, every function or method whose code decides the sandbox and
     isolation switches, the update check or the extensions (FROZEN) keeps the very same tree: an
     added `if ...: return True` inside `verify_signature` would be additive, and is refused here. The signature check therefore still refuses an unsigned or
     wrongly signed update, which the protected tests prove on every commit (SIGNATURE_TESTS:
     tests/test_updater.py, a tier-B file no AI may change);
   - *the protection lists only grow*: UNSAFE_SWITCHES, UNSAFE_FEATURES, UNSAFE_ENV, LNA_FEATURES,
     ENGINE_SAFETY (and NOTICE_SWITCHES, PRIVACY_FEATURES) keep every entry, and no new code names
     them at all (an alias could change a dict in place);
   - *the update check stays once every 24 hours*: the comparison with ``last_app_check`` is the
     same, and its interval is 24 * 3600 seconds;
   - *new code stays away from what decides* (reach_problems): it may not name a frozen function
     or the updater (a new line that calls ``save_state(...)`` or ``self.updater.run(...)`` would
     change the update channel without changing one of its functions), may not write to or call the
     configuration, may not call a setter (``set...(...)``: an engine setting, a permission, an
     attribute), may not give a constant to an attribute or an entry of any object
     (``self.blocker.enabled = False``), and may not hold a text that names an engine switch or a
     sandbox setting.
3. **A third independent free reviewer** for any change of these files (tools/ai-review.py,
   tools/automerge.py: needed_reviews), and the change is listed first in the signing notice
   (tools/release-notice.py).

**The stricter gate** (permanent: the owner's decision of 2026-11-24; switch or no switch): an AI's
change of a file of STRICT_GATE_FILES (ike/resources/fingerprint.js, tier A) also needs three
independent reviewers (needed_reviews), and tools/automerge.py asks "Nothing gets worse" for only
"stricter" rows of the fingerprinting surface (strict_gate). Why: an independent review showed
weakened copies of fingerprint.js that pass both tools/fix-guard.py and "Nothing gets worse" (only one
first-party test site, APIs and realms it never reads, fonts judged on the settings, noise not tied to
the key). No person is involved: a change that does not meet the gate is refused like any other AI fix
and the automatic fix tries again with the reason.

Everything else of tier B stays never an AI's, and so do the rule-keepers: tools/fix-guard.py,
tools/automerge.py, tools/ai-review.py, tools/no-regression.py, tools/check-autofix-patch.py, this
file and chatgpt-guard.yml (a workflow: only a pin of it could ever change).

    tier-b.py verify --base REV --head REV [--repo DIR]     (the workflows between two commits; git ls-remote)
    tier-b.py state                                         (on or off, from AUTOMAT_TIER_B)
"""

import argparse
import ast
import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path

SWITCH = "AUTOMAT_TIER_B"
PYTHON = ("ike/app.py", "ike/updater.py", "ike_boot.py")
WORKFLOW = re.compile(r"^\.github/(?:workflows/[A-Za-z0-9_.-]+\.yml|actions/[A-Za-z0-9_./-]+/action\.yml)$")
ONLY_GROW = ("UNSAFE_SWITCHES", "UNSAFE_FEATURES", "UNSAFE_ENV", "LNA_FEATURES", "ENGINE_SAFETY",
             "NOTICE_SWITCHES", "PRIVACY_FEATURES")
INTERVAL_NAME = "last_app_check"
INTERVAL_SECONDS = 24 * 3600
# the protected tests that prove the signature check refuses an unsigned or wrongly signed update
SIGNATURE_TESTS = ("tests/test_updater.py::test_signature", "tests/test_updater.py::test_bad_signature_is_refused")
# an old function whose code names one of these is frozen: the same tree before and after
FROZEN = re.compile(
    r"verify|signature|pubkey|sha256|sha512|hashlib|safe_extract|tarfile|UNSAFE_|ENGINE_SAFETY|LNA_FEATURES"
    r"|NOTICE_SWITCHES|PRIVACY_FEATURES|sandbox|isolat|refuse_root|unsafe_allowed|IKE_ALLOW_UNSAFE|last_app_check"
    r"|app_updates|rollback|usable|choose|version_dir|version_in|load_state|save_state|manifest|min_system"
    r"|updater|update\.json|execv|setuid|QTWEBENGINE|chromium_flags|__version__|security|extension", re.I)
# the update channel and the choice of the signed update: every function there is frozen
FROZEN_FILES = ("ike/updater.py", "ike_boot.py")
# what new code of these files may not reach (reach_problems)
SENSITIVE = ("updater", "config")
SETTER = re.compile(r"^set[A-Z_]|^setattr$|^__setattr__$|^__setitem__$")
SWITCH_TEXT = re.compile(r"--[a-z][a-z0-9]*-[a-z0-9-]+|QTWEBENGINE_|QT_QPA_|IKE_ALLOW_UNSAFE|sandbox|isolat|site-per-process"
                         r"|remote-debugging|web-security|update\.json|pubkey", re.I)
MAX_PIN_LINES = 40
REVIEWS = 3
# PERMANENT (the owner's decision of 2026-11-24): the stricter automatic gate of an AI's change of these
# files: three independent reviewers (needed_reviews) and only "stricter" fingerprinting rows of "Nothing
# gets worse" (tools/automerge.py strict_gate). Why: an independent review showed weakened copies of
# fingerprint.js that pass both tools/fix-guard.py and "Nothing gets worse" (one first-party test site,
# unread APIs and realms, fonts judged on the settings, noise not tied to the key).
STRICT_GATE_FILES = ("ike/resources/fingerprint.js",)


def on(env=None):
    """True only when the owner set the repository variable AUTOMAT_TIER_B to "on"."""
    env = os.environ if env is None else env
    return str(env.get(SWITCH) or "").strip().lower() == "on"


def allowed(path):
    """A tier-B file this narrow form opens (with the switch on)."""
    path = str(path or "")
    return path in PYTHON or (bool(WORKFLOW.match(path)) and ".." not in path)


def needed_reviews(paths):
    """Three independent reviewers when a tier-B file, or a file of the stricter gate (STRICT_GATE_FILES),
    is among the AI's files, else two."""
    return REVIEWS if any(allowed(p) or str(p or "") in STRICT_GATE_FILES for p in paths or ()) else 2


def _tool(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), Path(__file__).resolve().parent /
                                                  (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --- a workflow: nothing but a pinned version ------------------------------------------------------

def workflow_problem(name, old, new, tags=None):
    """Why the change of one workflow file is more than pinned versions, or "". tags(repo): {tag:
    commit} of an action's repository (git ls-remote; a test passes its own)."""
    ci = _tool("ci-pins")
    tags = tags or ci.ls_remote_tags
    a, b = (old or "").split("\n"), (new or "").split("\n")
    if len(a) != len(b):
        return "%s: lines added or removed in a workflow (only a pinned version may change)" % name
    changed = 0
    for x, y in zip(a, b):
        if x == y:
            continue
        changed += 1
        px, py = ci.pin_of_line(x), ci.pin_of_line(y)
        if not px or not py or px[0] != py[0] or px[1] != py[1]:
            return "%s: a line that is not a pinned version changed (%s): never a command, a permission, a " \
                   "secret, a trigger, runs-on or a step" % (name, y.strip()[:80])
        if px[1] == "action":
            mx, my = ci.ACTION.match(x), ci.ACTION.match(y)
            if mx.group("action") != my.group("action") or mx.group("lead") != my.group("lead") or \
                    mx.group("gap") != my.group("gap"):
                return "%s: another action, or more than its commit and version, on the line (%s)" % (
                    name, y.strip()[:80])
            if not ci.RELEASE_TAG.match(my.group("tag")):
                return "%s: not a release tag: %s" % (name, my.group("tag"))
            if ci.vkey(my.group("tag")) < ci.vkey(mx.group("tag")):
                return "%s: an older release than before (%s -> %s)" % (name, mx.group("tag"), my.group("tag"))
            if y != "%s%s@%s%s%s" % (my.group("lead"), my.group("action"), my.group("sha"), my.group("gap"),
                                     my.group("tag")):
                return "%s: more than the action's commit and version on the line (%s)" % (name, y.strip()[:80])
            try:
                found = tags(py[2]).get(my.group("tag"))
            except Exception as e:
                return "%s: the release tag could not be checked (%s): not verified" % (name, str(e)[:100])
            if found != my.group("sha"):
                return "%s: %s@%s is not the commit of its release %s" % (
                    name, my.group("action"), my.group("sha")[:12], my.group("tag"))
        else:
            if not re.fullmatch(r"\d+(?:\.\d+){0,2}", px[3]) or not re.fullmatch(r"\d+(?:\.\d+){0,2}", py[3]):
                return "%s: not a numeric version (%s)" % (name, y.strip()[:80])
            # the old line with only its pin's version replaced must be the new line, exactly
            if px[1] == "cargo-deny":
                expected = ci.CARGO_DENY.sub(lambda m: "cargo-deny%s%s" % (m.group("sep"), py[3]), x)
            elif px[1] == "rust":
                expected = ci.RUST.sub("rustup toolchain install %s" % py[3], x)
            else:
                m = (ci.PYTHON if px[1] == "python" else ci.NODE).match(x)
                expected = "%s%s%s%s" % (m.group("lead"), m.group("q"), py[3], m.group("q"))
            if y != expected:
                return "%s: more than the version on the line (%s)" % (name, y.strip()[:80])
            if ci.vkey(py[3]) < ci.vkey(px[3]):
                return "%s: an older version than before (%s -> %s)" % (name, px[3], py[3])
    if changed > MAX_PIN_LINES:
        return "%s: too many pinned lines changed at once (%d)" % (name, changed)
    return "" if changed else "%s: nothing changed" % name


# --- Python of the sandbox, the start and the update channel: the invariants -------------------------

def _dump(node):
    return ast.dump(node, annotate_fields=False, include_attributes=False) if node is not None else ""


def functions(tree, source):
    """{qualified name: (tree dump, source text)} of every function and method of a module."""
    out = {}

    def walk(body, prefix):
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = prefix + node.name
                out[name] = (_dump(node), ast.get_source_segment(source, node) or ast.unparse(node))
                walk(node.body, name + ".")
            elif isinstance(node, ast.ClassDef):
                walk(node.body, prefix + node.name + ".")
            elif isinstance(node, (ast.If, ast.Try, ast.With, ast.For, ast.While)):
                for part in ("body", "orelse", "finalbody"):
                    walk(getattr(node, part, []) or [], prefix)
                for h in getattr(node, "handlers", []) or []:
                    walk(h.body, prefix)
    walk(tree.body, "")
    return out


def frozen(source, name=""):
    """The names of the functions of a file that are frozen: every one in the update channel
    (FROZEN_FILES), elsewhere those whose code names what FROZEN lists."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return set()
    return {fn for fn, (_dump_, text) in functions(tree, source).items()
            if name in FROZEN_FILES or FROZEN.search(text)}


def _tables(tree):
    """{name: value node} of the module-level assignments of the protection lists."""
    out = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id in ONLY_GROW:
                    out[t.id] = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id in ONLY_GROW:
            out[node.target.id] = node.value
    return out


def _mentions(tree):
    """How many times each protection list is named anywhere in the module."""
    out = {}
    for node in ast.walk(tree):
        name = node.id if isinstance(node, ast.Name) else node.attr if isinstance(node, ast.Attribute) else \
            node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None
        if name in ONLY_GROW:
            out[name] = out.get(name, 0) + 1
    return out


def _seconds(node):
    """The number a constant expression of + and * gives (24 * 3600), or None."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Mult, ast.Add)):
        a, b = _seconds(node.left), _seconds(node.right)
        if a is None or b is None:
            return None
        return a * b if isinstance(node.op, ast.Mult) else a + b
    return None


def intervals(tree):
    """[(dump of the comparison, seconds or None)] of every comparison that reads last_app_check."""
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare) and INTERVAL_NAME in ast.unparse(node):
            out.append((_dump(node), [_seconds(c) for c in node.comparators]))
    return out


def _chain(node):
    """The names of an attribute, index or call chain (self.config["x"].get -> self, config, get)."""
    out = []
    while True:
        if isinstance(node, ast.Attribute):
            out.append(node.attr)
            node = node.value
        elif isinstance(node, (ast.Subscript, ast.Call)):
            node = node.value if isinstance(node, ast.Subscript) else node.func
        elif isinstance(node, ast.Name):
            out.append(node.id)
            return out
        else:
            return out


def _constant(value):
    """A value that is a constant (False, None, 0, "", an empty list...)."""
    if isinstance(value, ast.Constant):
        return True
    if isinstance(value, ast.UnaryOp):
        return _constant(value.operand)
    if isinstance(value, (ast.List, ast.Tuple, ast.Set)):
        return not value.elts
    if isinstance(value, ast.Dict):
        return not value.keys
    return isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and not value.args and \
        not value.keywords and value.func.id in ("set", "list", "dict", "tuple", "frozenset", "str", "bool", "int")


def reach(tree, kept):
    """A count of what a module's code reaches of the things that decide: references to the frozen
    functions (kept: their names) and to the updater, writes to and calls on the configuration,
    setter calls, and texts that name an engine switch or a sandbox setting."""
    import collections
    out = collections.Counter()
    names = {k.rsplit(".", 1)[-1] for k in kept} | {"updater"}
    tables = {id(n) for v in _tables(tree).values() for n in ast.walk(v)}       # the protection lists' own entries
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in names:
            out["a reference to %s" % node.id] += 1
        elif isinstance(node, ast.Attribute) and node.attr in names:
            out["a reference to .%s" % node.attr] += 1
        if isinstance(node, ast.Call):
            chain = _chain(node.func)
            if chain and SETTER.search(chain[0]):
                out["a call of the setter %s()" % chain[0]] += 1
            if any(n in SENSITIVE[1:] for n in chain[1:]):
                out["a call on the configuration"] += 1
        targets = []
        if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        elif isinstance(node, ast.Delete):
            targets = node.targets
        fixed = isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None and _constant(node.value)
        for t in targets:
            for sub in ([t] if not isinstance(t, (ast.Tuple, ast.List)) else t.elts):
                if isinstance(sub, (ast.Attribute, ast.Subscript)) and any(n in SENSITIVE[1:] for n in _chain(sub)):
                    out["a write to the configuration"] += 1
                elif isinstance(sub, (ast.Attribute, ast.Subscript)) and (fixed or isinstance(node, ast.Delete)):
                    out["a constant given to an attribute or an entry (or one deleted)"] += 1
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in tables \
                and SWITCH_TEXT.search(node.value):
            out["a text that names an engine switch or a sandbox setting"] += 1
    return out


def reach_problems(name, a, b, kept):
    """New code may not reach what decides: nothing of reach() may be there more often than before."""
    return ["%s: new code has %s (new code of this file stays away from the functions that decide, the updater, "
            "the configuration, the setters and the engine's switches)" % (name, what)
            for what in sorted(reach(b, kept) - reach(a, kept))]


def python_problems(name, old, new, guard):
    """Why an AI's change of ike/app.py, ike/updater.py or ike_boot.py is refused (a list). guard: the
    functions of tools/fix-guard.py (additive_problems, capability_problems, _grows)."""
    try:
        a, b = ast.parse(old), ast.parse(new)
    except (SyntaxError, ValueError):
        return ["%s: the file does not parse" % name]
    out = list(guard.capability_problems(name, old, new)) + list(guard.additive_problems(name, old, new))
    # frozen functions: the same tree
    before, after = functions(a, old), functions(b, new)
    kept = frozen(old, name)
    for fn in sorted(kept):
        if fn not in after:
            out.append("%s: %s is gone (it decides the signature, the update or the sandbox: frozen)" % (name, fn))
        elif after[fn][0] != before[fn][0]:
            out.append("%s: %s is frozen (it decides the signature, the update, the sandbox or the update check): "
                       "not one statement of it may change, not even an added one" % (name, fn))
    # a new function may not take the name of a frozen one in another place (a nested or later copy)
    for fn in sorted(set(after) - set(before)):
        if fn.rsplit(".", 1)[-1] in {x.rsplit(".", 1)[-1] for x in kept}:
            out.append("%s: a new function is named like the frozen %s" % (name, fn.rsplit(".", 1)[-1]))
    # the protection lists only grow, and no new code names them
    old_tables, new_tables = _tables(a), _tables(b)
    for table, value in sorted(old_tables.items()):
        if table not in new_tables:
            out.append("%s: %s is gone (the engine's protection lists only grow)" % (name, table))
        elif not guard._grows(value, new_tables[table]):
            out.append("%s: an entry of %s is removed or changed (the engine's protection lists only grow)"
                       % (name, table))
    was, now = _mentions(a), _mentions(b)
    for table in sorted(now):
        if now[table] > was.get(table, 0):
            out.append("%s: new code names %s (the protection lists are only read by the code that is there)"
                       % (name, table))
    # the update check: the same comparison, 24 hours
    then, here = intervals(a), intervals(b)
    if [d for d, _s in then] != [d for d, _s in here]:
        out.append("%s: the update check's comparison with %s changed or a new one was added (it stays once "
                   "every 24 hours)" % (name, INTERVAL_NAME))
    for _d, seconds in here:
        if INTERVAL_SECONDS not in seconds:
            out.append("%s: the update check is not once every 24 hours (%s seconds)" % (name, seconds))
    # new code stays away from what decides (a new entry of a protection list is the lists' own rule, above)
    return out + reach_problems(name, a, b, kept)


def file_problems(name, old, new, guard, tags=None):
    """Why this tier-B file's change is refused in the narrow form (a list; empty: accepted)."""
    if not allowed(name):
        return ["%s: tier B, never changed by an AI (not one of the files the owner's switch opens)" % name]
    if old is None or new is None:
        return ["%s: added, removed or renamed (only an existing file's change)" % name]
    if name in PYTHON:
        return python_problems(name, old, new, guard)
    why = workflow_problem(name, old, new, tags)
    return [why] if why else []


# --- the workflows between two commits (the fix's push: checked once more, with the network) -----------

def _show(repo, rev, path):
    out = subprocess.run(["git", "-C", str(repo), "show", "%s:%s" % (rev, path)], capture_output=True)
    return out.stdout.decode("utf-8", "replace") if out.returncode == 0 else None


def verify(repo, base, head, tags=None):
    """The reasons the changes under .github/ between two commits are more than pinned versions."""
    names = [n for n in subprocess.run(["git", "-C", str(repo), "diff", "--name-only", "-z", base, head, "--",
                                        ".github"], capture_output=True, text=True).stdout.split("\0") if n]
    out = []
    for n in names:
        old, new = _show(repo, base, n), _show(repo, head, n)
        if not allowed(n) or old is None or new is None:
            out.append("%s: not an existing workflow of this repository" % n)
            continue
        why = workflow_problem(n, old, new, tags)
        if why:
            out.append(why)
    return names, out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("verify")
    v.add_argument("--repo", default=".")
    v.add_argument("--base", required=True)
    v.add_argument("--head", required=True)
    sub.add_parser("state")
    a = ap.parse_args(argv)
    if a.cmd == "state":
        print("on" if on() else "off")
        return 0
    names, reasons = verify(a.repo, a.base, a.head)
    for r in reasons:
        print(re.sub(r":(?=:)", ": ", re.sub(r"\s+", " ", r))[:400])
    if not reasons:
        print("%d workflow file(s): only pinned versions changed" % len(names))
    return 1 if reasons else 0


if __name__ == "__main__":
    sys.exit(main())
