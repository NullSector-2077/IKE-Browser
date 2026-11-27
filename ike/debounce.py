"""Skip the tracker's stop (1.1.28, the owner's decision of 2026-11-27).

Many links do not lead to their site: they go through a tracker first, which
counts the click and sends the browser on. The links of newsletters (Mailchimp,
ActiveCampaign, Amazon SES, Postmark...), of shops' affiliate programmes and of
some ad networks carry the real address inside the link itself:

    https://go.redirectingat.com/?id=1&url=https%3A%2F%2Fshop.example%2Fitem

I.K.E. reads that address and goes there at once: the tracker never sees the
click, and the page opens sooner. Google's AMP copies of articles
(``google.com/amp/s/...``, ``*.cdn.ampproject.org/c/s/...``) are taken the same
way to the article on the publisher's own site.

The rules are Brave's own public list (``brave-lists/debounce.json`` of
https://github.com/brave/adblock-lists, MPL-2.0, shipped unchanged as
``ike/resources/brave-debounce.json``; ``components.json`` entry
``brave-debounce`` keeps it up to date). A link no rule names is never
touched. On top of the list, I.K.E.'s own limits:

- only an http or https address with a host and no user name or password in
  it, never a script, a file or a page of I.K.E.;
- never an address of this computer or of the home network (the tracker would
  be asked as before, and the home network protection judges that);
- never the same site the link already belongs to;
- never a page whose stop also checks the destination for the user's safety
  (Facebook's and Instagram's link shim, Steam's link filter, Google's and
  YouTube's own redirect pages: SAFETY_STOPS), nor a sign-in or payment
  service;
- at most a few stops skipped in a row, then nothing is changed.

Pure Python, no Qt: shields.Interceptor asks skip() for every page opened.
"""

import base64
import binascii
import functools
import json
import re
from urllib.parse import parse_qsl, unquote, urlsplit

LIST_FILE = "brave-debounce.json"
# actions of Brave's list I.K.E. knows; a rule with another action is left out
ACTIONS = ("redirect", "base64,redirect", "regex-path", "regex-path-template")
# Brave's switches a rule may name: the AMP rules are its "De-AMP" (on in I.K.E.
# with the rest); a rule behind any other switch is left out
PREFS = ("brave.de_amp.enabled",)
MAX_STOPS = 3                 # stops skipped in a row at most
MAX_LENGTH = 8192             # longer addresses are left as they are
# (site, path prefix) whose stop also protects the user: the destination is
# checked there against the service's own list of dangerous sites, or the user
# is warned before leaving it. Kept even if a future list names them.
SAFETY_STOPS = (
    ("facebook.com", ""), ("instagram.com", ""), ("messenger.com", ""), ("threads.net", ""),
    ("steamcommunity.com", ""), ("steampowered.com", ""),
    ("youtube.com", "/redirect"), ("google.*", "/url"),
)
_CTRL = re.compile(r"[\x00-\x20\x7f\\]")


def _rules_path():
    from .config import RES_DIR
    return RES_DIR / LIST_FILE


@functools.lru_cache(maxsize=1)
def rules():
    """The usable rules of the shipped list, compiled once: a tuple of
    (include patterns, exclude patterns, action, param, prepend scheme, template).
    An unreadable list gives no rules (nothing is skipped)."""
    try:
        data = json.loads(_rules_path().read_text("utf-8"))
    except (OSError, ValueError):
        return ()
    return compile_rules(data)


def compile_rules(data):
    out = []
    if not isinstance(data, list):
        return ()
    for rule in data:
        try:
            action = rule.get("action")
            pref = rule.get("pref")
            param = rule.get("param")
            if action not in ACTIONS or (pref is not None and pref not in PREFS):
                continue
            if not isinstance(param, str) or not param:
                continue
            prepend = rule.get("prepend_scheme") or ""
            if prepend not in ("", "http", "https"):
                continue
            template = rule.get("redirect_url_template") or ""
            if action == "regex-path-template" and not template.startswith(("https://", "http://")):
                continue
            regex = re.compile(param) if action.startswith("regex-path") else None
            include = tuple(p for p in map(_pattern, rule.get("include") or ()) if p)
            exclude = tuple(p for p in map(_pattern, rule.get("exclude") or ()) if p)
        except (AttributeError, TypeError, re.error):
            continue
        if include:
            out.append((include, exclude, action, regex or param, prepend, template))
    return tuple(out)


def _pattern(text):
    """A match pattern as Chrome's extensions write them ("*://*.example.com/r?*")
    -> (schemes, host, any subdomain, compiled path), or None."""
    m = re.fullmatch(r"(\*|https?)://(\*|(?:\*\.)?[A-Za-z0-9.-]+)(/.*)", str(text or ""))
    if not m:
        return None
    scheme, host, path = m.groups()
    schemes = ("http", "https") if scheme == "*" else (scheme,)
    sub = host.startswith("*.")
    host = host[2:] if sub else host
    path_re = re.compile(".*".join(re.escape(p) for p in path.split("*")), re.S)
    return schemes, host.lower(), sub, path_re


def _matches(pattern, scheme, host, path_query):
    schemes, phost, sub, path_re = pattern
    if scheme not in schemes:
        return False
    if phost != "*" and host != phost and not (sub and host.endswith("." + phost)):
        return False
    return path_re.fullmatch(path_query) is not None


def _value(parts, rule):
    """The address a rule finds in a link, or ""."""
    _inc, _exc, action, param, prepend, template = rule
    if action in ("redirect", "base64,redirect"):
        value = next((v for k, v in parse_qsl(parts.query, keep_blank_values=True) if k == param), "")
        if action == "base64,redirect" and value:
            value = _base64(value)
    else:
        m = param.fullmatch(parts.path)
        if not m:
            return ""
        groups = [g or "" for g in m.groups()]
        if action == "regex-path-template":
            value = template
            for i in range(len(groups), 0, -1):          # $10 before $1
                value = value.replace("$%d" % i, groups[i - 1])
            return value
        value = unquote("".join(groups))
    if value and prepend and not re.match(r"(?i)https?://", value):
        value = prepend + "://" + value
    return value


def _base64(value):
    text = value.strip()
    for decode in (base64.b64decode, base64.urlsafe_b64decode):
        try:
            return decode(text + "=" * (-len(text) % 4)).decode("utf-8")
        except (binascii.Error, ValueError, UnicodeDecodeError):
            continue
    return ""


def _site(host, site_of):
    if site_of is None:
        from .shields import site_of
    return site_of(host)


def _safety_stop(host, path, site):
    if host in _login_hosts():
        return True
    for name, prefix in SAFETY_STOPS:
        same = site.startswith(name[:-1]) if name.endswith(".*") else site == name
        if same and path.startswith(prefix):
            return True
    from .config import payment_owned
    return payment_owned(host)


def _login_hosts():
    from .config import LOGIN_HOSTS
    return LOGIN_HOSTS


def _usable(address):
    """urlsplit() of an address I.K.E. may open in the tracker's place, or None."""
    if not address or len(address) > MAX_LENGTH or _CTRL.search(address):
        return None
    try:
        parts = urlsplit(address)
        host = (parts.hostname or "").lower()
        parts.port                                   # a bad port raises ValueError
    except ValueError:
        return None
    if parts.scheme.lower() not in ("http", "https") or not host or parts.username is not None \
            or parts.password is not None or "@" in parts.netloc:
        return None
    from .userscripts import is_local_name
    if is_local_name(host):
        return None
    return parts


def _one(address, rule_set):
    """The address one rule finds in this link (unchecked), or ""."""
    parts = urlsplit(address)
    scheme, host = parts.scheme.lower(), (parts.hostname or "").lower()
    path_query = parts.path + ("?" + parts.query if parts.query else "")
    for rule in rule_set:
        include, exclude = rule[0], rule[1]
        if any(_matches(p, scheme, host, path_query) for p in include) and \
                not any(_matches(p, scheme, host, path_query) for p in exclude):
            value = _value(parts, rule)
            if value:
                return value
    return ""


def skip(address, site_of=None, rule_set=None):
    """The address to open instead of a tracker's link, or None (leave it)."""
    rule_set = rules() if rule_set is None else rule_set
    if not rule_set:
        return None
    parts = _usable(address)
    if parts is None:
        return None
    current, found = address, None
    for _ in range(MAX_STOPS + 1):
        cur = urlsplit(current)
        host = (cur.hostname or "").lower()
        site = _site(host, site_of)
        if _safety_stop(host, cur.path, site):
            break
        value = _one(current, rule_set)
        if not value:
            break
        nxt = _usable(value)
        if nxt is None or _site((nxt.hostname or "").lower(), site_of) == site:
            break
        current = found = value
    else:
        return None                    # still a tracker after MAX_STOPS: leave the link as it is
    return found
