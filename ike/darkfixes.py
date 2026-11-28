"""Dark Reader's lists, used as the Dark Reader extension uses them: for the
address of a page, the fix for that site (with the common fix), whether the
site is on the list of sites that are dark already, and the hints that
recognise a site's own dark theme.

The lists are resources/darkreader-data.json (tools/build-darkreader-lists.py makes
it from Dark Reader's repository), or, since 1.1.27, the newer ones the
browser fetched itself (ike/darklists.py). The address patterns are matched as Dark
Reader matches them (src/utils/url.ts): "example.com", "*.example.com",
"example.*", "example.com/path", "^" and "$" for exact host and path, and
/regular expressions/.
"""

import json
import re
from functools import lru_cache
from urllib.parse import urlsplit

from .config import RES_DIR

_data = None
_index = None


def bundled():
    """The lists I.K.E. came with (resources/darkreader-data.json)."""
    try:
        return json.loads((RES_DIR / "darkreader-data.json").read_text("utf-8"))
    except (OSError, ValueError):
        return {"fixes": [{"url": ["*"]}], "dark_sites": [], "detector_hints": []}


def data():
    """The lists in use: the ones the browser fetched (1.1.27) when they are
    checked and at least as new as the copy I.K.E. came with, else that copy."""
    global _data
    if _data is None:
        _data = bundled()
        from . import darklists
        fetched = darklists.load_fetched()
        if darklists.newer_than(fetched, _data):
            _data = dict(_data, fixes=fetched["fixes"], dark_sites=fetched["dark_sites"],
                         detector_hints=fetched["detector_hints"], lists_date=fetched["lists_date"],
                         lists_fetched=True)
    return _data


def reset():
    """Read the lists again (new ones were fetched)."""
    global _data, _index
    _data = _index = None


# --- address patterns ------------------------------------------------------
@lru_cache(maxsize=4096)
def _pattern(pattern):
    if not pattern:
        return None
    exact_start, exact_end = pattern.startswith("^"), pattern.endswith("$")
    pattern = pattern[1 if exact_start else 0:len(pattern) - (1 if exact_end else 0)]
    protocol = ""
    i = pattern.find("://")
    if i > 0:
        protocol, pattern = pattern[:i + 1], pattern[i + 3:]
    slash = pattern.find("/")
    host = pattern if slash < 0 else pattern[:slash]
    name, port = host, "*"
    ipv6_end = host.find("]") if host.startswith("[") else -1
    colon = host.rfind(":")
    if colon >= 0 and (ipv6_end < 0 or ipv6_end < colon):
        name, port = host[:colon], host[colon + 1:]
    path = "" if slash < 0 else pattern[slash + 1:]
    parts = path.split("/")
    if not parts[-1]:
        parts.pop()
    return (tuple(reversed(name.lower().split("."))), tuple(parts), port, protocol, exact_start, exact_end)


@lru_cache(maxsize=64)
def _url(url):
    try:
        u = urlsplit(url)
        host = (u.hostname or "").lower()
        port = str(u.port) if u.port else ""
    except ValueError:
        return None
    if not host:
        return None
    parts = u.path.split("/")[1:]
    if parts and not parts[-1]:
        parts.pop()
    return (tuple(reversed(host.split("."))), tuple(parts), port, u.scheme + ":")


@lru_cache(maxsize=1024)
def _regex(pattern):
    try:
        return re.compile(pattern[1:-1])
    except re.error:
        return None


def matches(url, pattern):
    """Dark Reader's isURLMatched."""
    if pattern.startswith("/") and pattern.endswith("/") and len(pattern) > 2:
        rx = _regex(pattern)
        return bool(rx and rx.search(url))
    u, p = _url(url), _pattern(pattern)
    if not u or not p:
        return False
    uhost, upath, uport, uproto = u
    phost, ppath, pport, pproto, exact_start, exact_end = p
    if (len(phost) > len(uhost) or (exact_start and len(phost) != len(uhost))
            or (exact_end and len(ppath) != len(upath)) or (pport != "*" and pport != uport)
            or (pproto and pproto != uproto)):
        return False
    for a, b in zip(phost, uhost):
        if a != "*" and a != b:
            return False
    if (len(phost) >= 2 and phost[-1] != "*"
            and (len(phost) < len(uhost) - 1 or (len(phost) == len(uhost) - 1 and uhost[-1] != "www"))):
        return False
    if not ppath:
        return True
    if len(ppath) > len(upath):
        return False
    return all(a == "*" or a == b for a, b in zip(ppath, upath))


def in_list(url, patterns):
    return any(matches(url, p) for p in patterns)


# --- an index, so a page does not go through every pattern --------------------
def _key(pattern):
    """The last two labels of the pattern's host, or None (checked for every page)."""
    if pattern.startswith("/") and pattern.endswith("/") and len(pattern) > 2:
        return None
    p = _pattern(pattern)
    if not p or len(p[0]) < 2 or "*" in p[0][:2]:
        return None
    return p[0][0], p[0][1]


def _build(entries):
    keyed, always = {}, []
    for n, entry in enumerate(entries):
        keys = {_key(p) for p in entry.get("url", ())}
        if None in keys:
            always.append(n)
            keys.discard(None)
        for k in keys:
            keyed.setdefault(k, []).append(n)
    return keyed, always


def _index_of(name):
    global _index
    if _index is None:
        d = data()
        _index = {"fixes": _build(d["fixes"][1:]), "hints": _build(d["detector_hints"]),
                  "dark": _build([{"url": [p]} for p in d["dark_sites"]])}
    return _index[name]


def _candidates(name, url):
    u = _url(url)
    keyed, always = _index_of(name)
    found = set(always)
    if u and len(u[0]) >= 2:
        found.update(keyed.get((u[0][0], u[0][1]), ()))
    return sorted(found)


# --- what the extension asks of the lists --------------------------------------
def _combine(fixes):
    """Dark Reader's combineFixes."""
    def arrays(key):
        return [x for f in fixes for x in (f.get(key) or [])]
    return {"invert": arrays("invert"), "css": "\n".join(f["css"] for f in fixes if f.get("css")),
            "ignoreInlineStyle": arrays("ignoreInlineStyle"), "ignoreImageAnalysis": arrays("ignoreImageAnalysis"),
            "ignoreCSSUrl": arrays("ignoreCSSUrl"), "disableStyleSheetsProxy": False,
            "disableCustomElementRegistryProxy": False}


def common_fix():
    return _combine([data()["fixes"][0]])


def fix_for(url):
    """The common fix and the most relevant fix of the site, combined (Dark
    Reader's findRelevantFix: the longest first pattern wins, the first of equals)."""
    fixes = data()["fixes"]
    best, best_len = None, 0
    for n in _candidates("fixes", url):
        fix = fixes[n + 1]
        if in_list(url, fix.get("url", ())):
            length = len(fix["url"][0])
            if best is None or best_len < length:
                best, best_len = fix, length
    return _combine([fixes[0]] + ([best] if best else []))


def in_dark_list(url):
    """Is the site on Dark Reader's list of sites that are dark already?"""
    patterns = data()["dark_sites"]
    return any(matches(url, patterns[n]) for n in _candidates("dark", url))


def hints_for(url):
    """The hints that recognise this site's own dark theme."""
    hints = data()["detector_hints"]
    out = []
    for n in _candidates("hints", url):
        h = hints[n]
        if in_list(url, h.get("url", ())):
            out.append({k: v for k, v in h.items() if k != "url"})
    return out


# --- the part of a fix's CSS the I.K.E. Dark Engine can use (darkengine.py) ---
# Dark Reader's fixes are written for Dark Reader's own output. The Dark Engine
# replaces four of its variables (ENGINE_VARS, as darkengine.js base() does) and
# the "property: ${colour}" templates; a rule that needs anything else of Dark
# Reader (its other variables, its attributes in a selector, a template left in
# a gradient or a shadow) would be broken CSS there and is left out. Generic
# rules, no site names: a refreshed list is filtered the same way by itself.
ENGINE_VARS = ("neutral-background", "neutral-text", "selection-background", "selection-text")
_TEMPLATE = re.compile(r"\$\{[^{}]*\}")
_ENGINE_VAR = re.compile(r"var\(\s*--darkreader-(?:%s)\s*\)" % "|".join(ENGINE_VARS))
_PROP_TEMPLATE = re.compile(r"[\w-]+\s*:\s*\$\{[^{}]*\}")


def _rules(css):
    """Top-level blocks of css as (prelude, body) pairs (templates protected)."""
    out, depth, start, body_start = [], 0, 0, None
    for i, ch in enumerate(css):
        if ch == "{":
            if depth == 0:
                body_start = i
            depth += 1
        elif ch == "}" and depth:
            depth -= 1
            if depth == 0:
                out.append((css[start:body_start].strip(), css[body_start + 1:i]))
                start = i + 1
    return out


def _engine_rule(prelude, body, restore):
    prelude, body = restore(prelude), restore(body)
    if prelude.startswith("@"):
        inner = engine_css(body)
        return "%s {\n%s\n}" % (prelude, inner) if inner else ""
    if "darkreader" in prelude.lower():
        return ""
    if "darkreader" in _ENGINE_VAR.sub("", body).lower():
        return ""
    if "${" in _PROP_TEMPLATE.sub("", body):
        return ""
    return "%s {%s}" % (prelude, body)


@lru_cache(maxsize=256)
def engine_css(css):
    """The rules of a fix's css that the Dark Engine can use, in their order."""
    if not css or "{" not in css:
        return ""
    # a template's braces are not blocks
    keep = {}

    def protect(m):
        keep["\x00%d\x00" % len(keep)] = m.group(0)
        return "\x00%d\x00" % (len(keep) - 1)
    def restore(t):
        for k, v in keep.items():
            t = t.replace(k, v)
        return t
    text = _TEMPLATE.sub(protect, css)
    return "\n".join(r for r in (_engine_rule(p, b, restore) for p, b in _rules(text)) if r)
