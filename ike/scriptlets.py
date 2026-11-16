"""Scriptlet rules ("example.com##+js(name, args)") from the filter lists.

The filter engine in use cannot run uBlock Origin's scriptlets, which is what
removes ads that are part of a page's own data (video ads). This module reads
those rules from the lists and runs them with uBlock Origin's own scriptlet
library (resources/ubo-scriptlets.json, GPL-3.0, generated from the uBlock
sources by build-ubo-scriptlets.mjs in the documentation folder), so every scriptlet the lists use is
available, with the same behaviour as in uBlock Origin.
"""

import json
import re

from .config import RES_DIR

LIB_FILE = RES_DIR / "ubo-scriptlets.json"
_RULE = re.compile(r"^([^#\s]*)#(@?)#\+js\((.*)\)\s*$")


# uBlock Origin's list directives ("!#if env_firefox" ... "!#else" ... "!#endif").
# The lists carry one set of rules per browser family; loading every branch
# mixes Firefox-only rules with the Chromium ones. I.K.E. answers as uBlock
# Origin does on a Chromium engine without HTML filtering.
_ENV = {"env_chromium": True, "ext_ublock": True, "cap_user_stylesheet": True}
_PP_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_PP_SAFE = re.compile(r"^[\sA-Za-z()]*$")


def _pp_eval(expr):
    py = expr.replace("&&", " and ").replace("||", " or ").replace("!", " not ")
    py = _PP_TOKEN.sub(lambda m: m.group(0) if m.group(0) in ("and", "or", "not")
                       else str(bool(_ENV.get(m.group(0), False))), py)
    if not _PP_SAFE.match(py):
        return True
    try:
        return bool(eval(py, {"__builtins__": {}}, {}))
    except Exception:
        return True               # unreadable condition: keep the rules


def preprocess(text):
    """Drop the lines inside "!#if" branches that do not apply to I.K.E."""
    if "!#if" not in text:
        return text
    out, stack = [], []           # stack of [parent_active, this_branch_true]
    for line in text.splitlines():
        t = line.strip()
        if t.startswith("!#if "):
            parent = all(a and b for a, b in stack)
            stack.append([parent, _pp_eval(t[5:])])
            continue
        if t == "!#else":
            if stack:
                stack[-1][1] = not stack[-1][1]
            continue
        if t == "!#endif":
            if stack:
                stack.pop()
            continue
        if all(b for _a, b in stack):
            out.append(line)
    return "\n".join(out)


class Library:
    """uBlock Origin's scriptlets: name -> {fn, src, deps, trust, world}."""

    def __init__(self):
        self._data = None
        self.version = "none"

    def _load(self):
        if self._data is not None:
            return
        self._data, self._alias = {}, {}
        try:
            raw = json.loads(LIB_FILE.read_text("utf-8"))
        except (OSError, ValueError):
            return
        self._data = raw.get("scriptlets", {})
        self.version = (raw.get("commit") or "none")[:12]
        for name, entry in self._data.items():
            for alias in entry.get("aliases", ()):
                self._alias[alias] = name

    def lib_version(self):
        self._load()
        return self.version

    def resolve(self, token):
        """Rule token ("set", "json-prune.js") -> library name, or None."""
        self._load()
        if not token:
            return None
        name = token if token.endswith(".js") else token + ".js"
        name = self._alias.get(name, name)
        return name if name in self._data else None

    def entry(self, name):
        self._load()
        return self._data.get(name)

    def closure(self, names):
        """The given entries plus everything they depend on, each once."""
        self._load()
        seen, order = set(), []
        stack = list(names)
        while stack:
            name = stack.pop()
            if name in seen or name not in self._data:
                continue
            seen.add(name)
            order.append(name)
            stack.extend(self._data[name].get("deps", ()))
        return order


LIBRARY = Library()


def split_args(raw):
    """Split scriptlet arguments: commas separate, quotes and \\, protect."""
    args, cur, i, n = [], "", 0, len(raw)
    while i < n and raw[i] == " ":
        i += 1
    while i <= n:
        if i == n:
            args.append(cur.strip())
            break
        ch = raw[i]
        if not cur.strip() and ch in "'\"`":
            j = i + 1
            buf = ""
            while j < n and raw[j] != ch:
                if raw[j] == "\\" and j + 1 < n and raw[j + 1] == ch:
                    j += 1
                buf += raw[j]
                j += 1
            k = j + 1
            while k < n and raw[k] == " ":
                k += 1
            if j < n and (k == n or raw[k] == ","):
                args.append(buf)
                cur = ""
                i = k + 1
                if k == n:
                    break
                continue
        if ch == "\\" and i + 1 < n and raw[i + 1] == ",":
            cur += ","
            i += 2
            continue
        if ch == ",":
            args.append(cur.strip())
            cur = ""
            i += 1
            continue
        cur += ch
        i += 1
    return args


def _own_host():
    """JS: the document's host name (an empty frame takes its parent's)."""
    return ("var h = location.hostname;"
            "if (!h) { try { h = parent.location.hostname; } catch (e) {} }")


class Scriptlets:
    def __init__(self):
        self.by_domain = {}        # domain -> [[name, args...]]
        self.negated = {}          # domain -> set of json rules excluded there
        self.exceptions = {}       # domain -> set of names ("" = all)
        self._embed_cache = {}

    def clear(self):
        self.by_domain, self.negated, self.exceptions = {}, {}, {}
        self._embed_cache = {}

    def add_list(self, text, trusted):
        lib = LIBRARY
        for line in preprocess(text).splitlines():
            if "+js(" not in line:
                continue
            m = _RULE.match(line.strip())
            if not m:
                continue
            domains = m.group(1).strip()
            args = split_args(m.group(3))
            if m.group(2):        # exception: domain#@#+js(name) or #@#+js()
                name = (lib.resolve(args[0]) or args[0]) if args and args[0] else ""
                # uBO supports a global exception (#@#+js()) as well as
                # domain-scoped exceptions. The previous parser discarded
                # global exceptions because the domain field is empty.
                targets = [d.strip().lower() for d in domains.split(",") if d.strip()]
                if not targets:
                    targets = ["*"]
                for d in targets:
                    self.exceptions.setdefault(d, set()).add(name)
                continue
            if not domains:
                continue          # generic scriptlet injections remain unsupported
            name = lib.resolve(args[0]) if args else None
            if name is None:
                continue
            if lib.entry(name).get("trust") and not trusted:
                continue
            rule = [name] + args[1:]
            key = json.dumps(rule)
            for d in m.group(1).split(","):
                d = d.strip().lower()
                if not d:
                    continue
                if d.startswith("~"):
                    self.negated.setdefault(d[1:], set()).add(key)
                else:
                    rules = self.by_domain.setdefault(d, [])
                    if rule not in rules:
                        rules.append(rule)

    @staticmethod
    def _chain(host):
        """www.a.b.c -> ['www.a.b.c', 'a.b.c', 'b.c', 'c'] plus entity forms."""
        host = host.lower()
        parts = host.split(".")
        out = [".".join(parts[i:]) for i in range(len(parts))]
        for i in range(len(parts) - 1):       # entity rules: "google.*"
            out.append(".".join(parts[i:-1]) + ".*")
        return out

    def for_host(self, host):
        chain = self._chain(host)
        blocked_names = set()
        excluded = set()
        blocked_names |= self.exceptions.get("*", set())
        for d in chain:
            blocked_names |= self.exceptions.get(d, set())
            excluded |= self.negated.get(d, set())
        if "" in blocked_names:
            return []
        out = []
        for d in chain:
            for rule in self.by_domain.get(d, ()):
                if rule[0] in blocked_names or json.dumps(rule) in excluded or rule in out:
                    continue
                out.append(rule)
        return out

    def has_rules(self, host):
        return bool(self.for_host(host))

    def _split(self, host):
        """Rules of a host by the world they run in."""
        worlds = {"MAIN": [], "ISOLATED": []}
        for rule in self.for_host(host):
            entry = LIBRARY.entry(rule[0])
            if entry:
                worlds[entry.get("world", "MAIN")].append(rule)
        return worlds

    @staticmethod
    def _calls(rules):
        return "\n".join("try { %s(...%s); } catch (e) { }"
                         % (LIBRARY.entry(r[0])["fn"], json.dumps(r[1:])) for r in rules)

    @staticmethod
    def _sources(rules):
        return "\n".join(LIBRARY.entry(n)["src"] for n in LIBRARY.closure(r[0] for r in rules))

    def scripts_for(self, host):
        """{"MAIN": code, "ISOLATED": code} for the page of this host.

        Runs in documents of this host only, page or frame ('' = nothing to run).
        """
        out = {}
        for world, rules in self._split(host).items():
            if not rules:
                out[world] = ""
                continue
            out[world] = "\n".join((
                "(function () {",
                "%sif (h !== %s) return;" % (_own_host(), json.dumps(host)),
                "const scriptletGlobals = {};",
                self._sources(rules), self._calls(rules), "})();"))
        return out

    def host_scripts(self, hosts):
        """One script per world for a fixed set of hosts (the video sites).

        It runs wherever a document of one of these hosts is loaded, as a page
        or as a frame of another page, and does nothing anywhere else. It is
        meant to be installed in the profile, so that it is already in place
        whichever way the page is reached.
        """
        split = {h: self._split(h) for h in hosts}
        out = {}
        for world in ("MAIN", "ISOLATED"):
            used = [h for h in hosts if split[h][world]]
            if not used:
                out[world] = ""
                continue
            every = [r for h in used for r in split[h][world]]
            code = ["(function () {", _own_host(),
                    "if (%s.indexOf(h) < 0) return;" % json.dumps(used),
                    "const scriptletGlobals = {};", self._sources(every)]
            for h in used:
                code.append("if (h === %s) {\n%s\n}" % (json.dumps(h), self._calls(split[h][world])))
            code.append("})();")
            out[world] = "\n".join(code)
        return out

    def embed_scripts(self, hosts):
        """Like scripts_for, for sites that other pages embed (video players).

        One script per world covers all the given hosts; it only does something
        inside a frame whose host is one of them. It has to be installed with
        the page itself: a frame of another site lives in its own process, and
        only receives the scripts that existed when that process was set up.
        """
        key = tuple(hosts)
        if key in self._embed_cache:
            return self._embed_cache[key]
        split = {h: self._split(h) for h in hosts}
        out = {}
        for world in ("MAIN", "ISOLATED"):
            used = [h for h in hosts if split[h][world]]
            if not used:
                out[world] = ""
                continue
            every = [r for h in used for r in split[h][world]]
            code = ["(function () {", "if (self === top) return;", _own_host(),
                    "if (%s.indexOf(h) < 0) return;" % json.dumps(used),
                    "const scriptletGlobals = {};", self._sources(every)]
            for h in used:
                code.append("if (h === %s) {\n%s\n}" % (json.dumps(h), self._calls(split[h][world])))
            code.append("})();")
            out[world] = "\n".join(code)
        self._embed_cache[key] = out
        return out

    # --- cache -------------------------------------------------------
    def dump(self):
        return json.dumps({"d": self.by_domain,
                           "n": {k: sorted(v) for k, v in self.negated.items()},
                           "e": {k: sorted(v) for k, v in self.exceptions.items()}})

    def load(self, text):
        data = json.loads(text)
        self.by_domain = data["d"]
        self.negated = {k: set(v) for k, v in data["n"].items()}
        self.exceptions = {k: set(v) for k, v in data["e"].items()}
        self._embed_cache = {}
