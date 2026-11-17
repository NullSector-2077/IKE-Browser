"""Dark Reader's lists, used as the Dark Reader extension uses them: for the
address of a page, the fix for that site (with the common fix), whether the
site is on the list of sites that are dark already, and the hints that
recognise a site's own dark theme.

The lists are resources/darkreader-data.json (tools/build-darkreader.py makes
it from Dark Reader's repository). The address patterns are matched as Dark
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


def data():
    global _data
    if _data is None:
        try:
            _data = json.loads((RES_DIR / "darkreader-data.json").read_text("utf-8"))
        except (OSError, ValueError):
            _data = {"fixes": [{"url": ["*"]}], "dark_sites": [], "detector_hints": []}
    return _data


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
