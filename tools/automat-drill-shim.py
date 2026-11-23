"""AUTOMAT's drill: a simulated major release of Qt and PyQt, in the drill's own test runs only.

Installed by ``tools/automat-drill.py shim --install`` into the test environment's Python (as the
module ``ike_automat_drill_shim`` and a ``.pth`` file that imports it at start), and only when the
checkout carries the drill's marker ``tools/automat-drill.active``: the composite action
``.github/actions/ike-test-env`` calls it, so the drill's Tests, its Security tests and the automatic
fix's job ``try`` see the "new Qt", and nothing else does. The browser that users install never has
it: it is no file of the package, and the marker exists only on a drill's branch.

At start it does nothing but put a finder in front of Python's own (``sys.meta_path``). When a
process imports one of the PyQt6 modules the drill's scenario names, the finder decides once whether
this process belongs to a drill's checkout: the first folder holding ``ike_boot.py`` above the
current folder, or above a file named on the command line or run as ``__main__``, must hold the
marker. A checkout of main in the same job (the "Nothing gets worse" check's base, the tests of the
starting commit) has no marker, and keeps today's Qt.

Then the module is loaded as usual and the scenario's breaks are applied to it, as a major release
would change it (the list is data: ``tools/automat-drill.json``, the scenario the marker names):

- ``rename``: ``Owner.old`` is gone (AttributeError, as for any missing name) and ``Owner.new`` is the
  very same thing (an enum member, a method, a signal);
- ``remove``: ``Owner.old`` is gone; the scenario's release notes say what replaces it;
- ``max_args``: the method takes at most N arguments now (a TypeError, as PyQt says it);
- on a module itself (no owner): the name is gone from it (``cannot import name``), or renamed.

Only the modules of the components a scenario may change are ever looked at (MODULES: PyQt6 and
jeepney, the D-Bus library that moves with the desktop's Qt).

Only I.K.E.'s own code sees the new release (the code of the drill's ike/ and ike_boot.py, from_ike):
the tests and their helpers, which no AI may change, and the libraries' own code (as a real release
changes its own code with its names) keep today's names. Nothing else changes: the real Qt still runs
underneath, so a fix that uses the new name, with a fallback to the old one, works in both worlds.
"""

import importlib.abc
import json
import os
import sys
import types
from pathlib import Path

MARKER = "tools/automat-drill.active"
MODULES = ("PyQt6.", "jeepney")            # the components a scenario may change (their modules only)
SCENARIOS = "tools/automat-drill.json"
_STATE = {"root": False, "breaks": None, "applied": []}


def tree_of(path):
    """The checkout above a folder or a file: the first folder that holds ike_boot.py, or None."""
    try:
        p = Path(path).resolve()
    except (OSError, RuntimeError, ValueError):
        return None
    if p.is_file():
        p = p.parent
    for d in [p, *p.parents][:8]:
        if (d / "ike_boot.py").is_file():
            return d
    return None


def drill_root(cwd=None, argv=None, main_file=None):
    """The drill's checkout this process belongs to, or None (the checkout has no marker)."""
    places = [cwd if cwd is not None else os.getcwd()]
    places += [a for a in (sys.argv if argv is None else argv) if isinstance(a, str) and a.endswith(".py")]
    if main_file is None:
        main_file = getattr(sys.modules.get("__main__"), "__file__", None)
    if main_file:
        places.append(main_file)
    for place in places:
        root = tree_of(place)
        if root is not None and (root / MARKER).is_file():
            return root
    return None


def load_breaks(root):
    """The breaks of the scenario the marker names: [dict]; [] when they cannot be read."""
    try:
        marker = json.loads((Path(root) / MARKER).read_text("utf-8"))
        data = json.loads((Path(root) / SCENARIOS).read_text("utf-8"))
        scenario = data["scenarios"][marker["scenario"]]
        return [b for b in scenario.get("breaks") or () if isinstance(b, dict) and b.get("module")]
    except (OSError, ValueError, KeyError, TypeError):
        return []


def _breaks():
    if _STATE["breaks"] is None:
        root = drill_root()
        _STATE["root"] = root
        _STATE["breaks"] = load_breaks(root) if root is not None else []
    return _STATE["breaks"]


_SEEN = {}


def from_ike(depth=2):
    """True when the code that reads the name is I.K.E.'s own (the drill's checkout: ike/ and ike_boot.py).
    The tests, their helpers and the libraries' own code keep today's names: an AI may not change them, and
    a real release changes its own code along with its names."""
    root = _STATE["root"]
    if not root:
        return False
    try:
        name = sys._getframe(depth).f_code.co_filename
    except ValueError:
        return False
    if name not in _SEEN:
        real = os.path.realpath(name)
        _SEEN[name] = real.startswith(os.path.join(str(root), "ike") + os.sep) or \
            real == os.path.join(str(root), "ike_boot.py")
    return _SEEN[name]


class _Gone:
    """A name the new release no longer has: reading it from I.K.E.'s code raises AttributeError, as for any
    other missing name; any other code still gets the real thing."""

    def __init__(self, owner, name, raw):
        self.owner, self.name, self.raw = owner, name, raw

    def __get__(self, instance, owner=None):
        if not from_ike():
            return self.raw.__get__(instance, owner) if hasattr(type(self.raw), "__get__") else self.raw
        if instance is None:
            raise AttributeError("type object '%s' has no attribute '%s'" % (self.owner, self.name))
        raise AttributeError("'%s' object has no attribute '%s'" % (type(instance).__name__, self.name))


class _NarrowModule(types.ModuleType):
    """A module some of whose names are gone for its importers (its own functions read its dictionary)."""

    def __getattribute__(self, name):
        gone = types.ModuleType.__getattribute__(self, "__dict__").get("_ike_drill_gone") or ()
        if name in gone and from_ike():
            raise AttributeError("module '%s' has no attribute '%s'" % (
                types.ModuleType.__getattribute__(self, "__name__"), name))
        return types.ModuleType.__getattribute__(self, name)

    def __dir__(self):
        gone = self.__dict__.get("_ike_drill_gone") or ()
        return [n for n in types.ModuleType.__dir__(self) if n not in gone]


def _resolve(module, path):
    obj = module
    for part in [p for p in str(path or "").split(".") if p]:
        obj = getattr(obj, part)
    return obj


def _raw(owner, name):
    """The attribute itself (an enum member, sip's method descriptor, a signal), not bound to the class."""
    getattr(owner, name)                      # sip fills the class's dictionary when a name is first read
    for klass in getattr(owner, "__mro__", (owner,)):
        if name in getattr(klass, "__dict__", {}):
            return klass.__dict__[name]
    return getattr(owner, name)


def _set(owner, name, value):
    import enum
    if isinstance(owner, enum.EnumMeta):
        type.__setattr__(owner, name, value)  # an enum refuses setattr for its members
    else:
        setattr(owner, name, value)


def apply_break(module, b):
    """One break of the scenario on a loaded module. Returns a line for the log."""
    owner = _resolve(module, b.get("owner"))
    label = getattr(owner, "__name__", str(b.get("owner")))
    old, kind = b["old"], b.get("kind")
    if isinstance(owner, types.ModuleType):
        # a name of the module itself: gone for whoever imports it ("cannot import name ..."), or there under
        # its new name; the module's own code still finds it (as the new release's code finds its new name)
        if kind == "rename":
            setattr(owner, b["new"], getattr(owner, old))
        if not isinstance(owner, _NarrowModule):
            owner.__class__ = _NarrowModule
        owner.__dict__.setdefault("_ike_drill_gone", set()).add(old)
        return "%s.%s %s" % (label, old, "-> " + b["new"] if kind == "rename" else "removed")
    raw = _raw(owner, old)
    if kind == "rename":
        _set(owner, b["new"], raw)
        _set(owner, old, _Gone(label, old, raw))
        return "%s.%s -> %s" % (label, old, b["new"])
    if kind == "remove":
        _set(owner, old, _Gone(label, old, raw))
        return "%s.%s removed" % (label, old)
    if kind == "max_args":
        limit, real = int(b["max_args"]), getattr(owner, old)
        shown = b.get("signature") or "%s(...)" % old

        def narrower(self, *args, **kw):
            if len(args) > limit and from_ike():
                raise TypeError("%s: too many arguments" % shown)
            return real(self, *args, **kw)
        narrower.__name__ = old
        _set(owner, old, narrower)
        return "%s.%s takes at most %d arguments" % (label, old, limit)
    raise ValueError("unknown kind of break: %r" % kind)


def apply_all(module, breaks=None):
    for b in breaks if breaks is not None else _breaks():
        if b.get("module") != module.__name__:
            continue
        try:
            _STATE["applied"].append(apply_break(module, b))
        except Exception as e:                # a scenario that does not fit this Qt: said, never silent
            sys.stderr.write("AUTOMAT drill: break %s not applied: %s\n" % (b.get("id"), e))


class _Loader(importlib.abc.Loader):
    def __init__(self, real):
        self.real = real

    def create_module(self, spec):
        return self.real.create_module(spec)

    def exec_module(self, module):
        self.real.exec_module(module)
        apply_all(module)


class Finder(importlib.abc.MetaPathFinder):
    """In front of Python's own finders: the drill's modules get their breaks once loaded."""

    def find_spec(self, name, path=None, target=None):
        if not name.startswith(MODULES) or not any(b.get("module") == name for b in _breaks()):
            return None
        for finder in sys.meta_path:
            if finder is self or not hasattr(finder, "find_spec"):
                continue
            spec = finder.find_spec(name, path, target)
            if spec is not None:
                if spec.loader is not None:
                    spec.loader = _Loader(spec.loader)
                return spec
        return None


def install():
    """Called by the .pth file at every start of Python in the drill's environment."""
    if not any(isinstance(f, Finder) for f in sys.meta_path):
        sys.meta_path.insert(0, Finder())


__all__ = ["install", "drill_root", "load_breaks", "apply_break", "apply_all", "Finder", "MARKER", "SCENARIOS"]
