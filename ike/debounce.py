"""Skip the tracker's stop (1.1.29, the owner's decision of 2026-11-27).

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

- a rule only names trackers: a pattern for every site ("*://*/*") or for a
  whole public suffix ("*.co.uk") is left out, a template may only lead to
  TEMPLATE_HOSTS, and a regular expression may not nest or pile up repeats
  (it runs on every page opened: no expression may take long); a list that
  breaks these rules fails tests/test_debounce.py, so it never reaches main by
  itself;
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

No Qt here: shields.Interceptor asks skip() for every page opened, and checks
the address again as the engine reads it (QUrl) before opening it.
"""

import base64
import binascii
import functools
import json
import re
from urllib.parse import parse_qsl, unquote, urlsplit

try:                                       # the parser of re (Python 3.11 and later)
    from re import _parser as _re_parser
except ImportError:                        # Python 3.9 and 3.10
    import sre_parse as _re_parser

LIST_FILE = "brave-debounce.json"
# actions of Brave's list I.K.E. knows; a rule with another action is left out
ACTIONS = ("redirect", "base64,redirect", "regex-path", "regex-path-template")
# Brave's switches a rule may name: the AMP rules are its "De-AMP" (on in I.K.E.
# with the rest); a rule behind any other switch is left out
PREFS = ("brave.de_amp.enabled",)
# the hosts a "regex-path-template" rule may lead to (y2u.be's short links)
TEMPLATE_HOSTS = ("www.youtube.com",)
MAX_STOPS = 3                 # stops skipped in a row at most
MAX_LENGTH = 8192             # longer addresses are left as they are
MAX_PATH = 2048               # a rule's regular expression never reads more than this
MAX_STARS = 6                 # "*" in one pattern at most
MAX_UNBOUNDED = 2             # unbounded repeats ("+", "*") in one regular expression at most
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


def compile_rules(data, site_of=None, refused=None):
    """The rules I.K.E. uses; `refused` (a list), when given, gets a line for
    every rule or pattern left out because it breaks I.K.E.'s limits (not for
    an action or a switch I.K.E. does not know)."""
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
            if action == "regex-path-template" and not _template_ok(template):
                _say(refused, "template that may lead anywhere: %r" % template)
                continue
            regex = None
            if action.startswith("regex-path"):
                if not _regex_ok(param):
                    _say(refused, "regular expression that could take long: %r" % param)
                    continue
                regex = re.compile(param)
            include = []
            for text in rule.get("include") or ():
                pattern = _pattern(text, site_of)
                if pattern:
                    include.append(pattern)
                else:
                    _say(refused, "pattern: %r" % (text,))
            exclude = tuple(p for p in (_pattern(t, site_of, broad=True) for t in rule.get("exclude") or ()) if p)
        except (AttributeError, TypeError, re.error, ValueError):
            _say(refused, "rule: %r" % (rule,))
            continue
        if include:
            out.append((tuple(include), exclude, action, regex or param, prepend, template))
    return tuple(out)


def _say(refused, line):
    if refused is not None:
        refused.append(line)


def _template_ok(template):
    """A template's host is fixed and one of TEMPLATE_HOSTS; only its path or query takes the
    captured parts."""
    try:
        parts = urlsplit(template)
    except ValueError:
        return False
    return parts.scheme == "https" and "$" not in parts.netloc and parts.hostname in TEMPLATE_HOSTS \
        and parts.netloc == parts.hostname


def _regex_ok(pattern):
    """No repeat inside a repeat, no back-reference or look-around, at most MAX_UNBOUNDED
    unbounded repeats: such an expression stays fast on any address."""
    try:
        tree = _re_parser.parse(pattern)
    except (re.error, TypeError, ValueError, RecursionError):
        return False
    unbounded = [0]

    def walk(items, in_repeat):
        for op, av in items:
            name = str(op)
            if name in ("MAX_REPEAT", "MIN_REPEAT", "POSSESSIVE_REPEAT"):
                lo, hi, sub = av
                if in_repeat:
                    return False
                if hi == _re_parser.MAXREPEAT:
                    unbounded[0] += 1
                if not walk(sub, True):
                    return False
            elif name == "SUBPATTERN":
                if not walk(av[-1], in_repeat):
                    return False
            elif name == "BRANCH":
                if not all(walk(b, in_repeat) for b in av[1]):
                    return False
            elif name in ("GROUPREF", "GROUPREF_EXISTS", "ASSERT", "ASSERT_NOT", "ATOMIC_GROUP"):
                return False
        return True
    return walk(tree, False) and unbounded[0] <= MAX_UNBOUNDED


def _pattern(text, site_of=None, broad=False):
    """A match pattern as Chrome's extensions write them ("*://*.example.com/r?*")
    -> (schemes, host, any subdomain, path pieces), or None. Unless `broad` (an
    exclusion, which can only narrow a rule), every site or a whole public suffix
    is refused."""
    m = re.fullmatch(r"(\*|https?)://(\*|(?:\*\.)?[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*)(/.*)", str(text or ""))
    if not m:
        return None
    scheme, host, path = m.groups()
    schemes = ("http", "https") if scheme == "*" else (scheme,)
    host = host.lower()
    if host == "*":
        if not broad:
            return None
        sub, host = True, ""
    else:
        sub = host.startswith("*.")
        host = host[2:] if sub else host
        if not broad and ("." not in host or (sub and _public_suffix(host, site_of))):
            return None
    pieces = path.split("*")
    if len(pieces) - 1 > MAX_STARS:
        return None
    return schemes, host, sub, tuple(pieces)


def _public_suffix(host, site_of):
    probe = "x-ike-probe." + host
    return _site(probe, site_of) == probe


def _glob(pieces, text):
    """Does `text` match the pattern path cut at its "*" into `pieces`? Leftmost
    matching of each piece is exact for "*" alone, in linear time."""
    first, last = pieces[0], pieces[-1]
    if len(pieces) == 1:
        return text == first
    if not text.startswith(first) or len(text) < len(first) + len(last) or not text.endswith(last):
        return False
    pos, end = len(first), len(text) - len(last)
    for piece in pieces[1:-1]:
        found = text.find(piece, pos, end)
        if found < 0:
            return False
        pos = found + len(piece)
    return True


def _matches(pattern, scheme, host, path_query):
    schemes, phost, sub, pieces = pattern
    if scheme not in schemes:
        return False
    if phost and host != phost and not (sub and host.endswith("." + phost)):
        return False
    return _glob(pieces, path_query)


def _query_value(query, name, plus_is_space=True):
    if plus_is_space:
        return next((v for k, v in parse_qsl(query, keep_blank_values=True) if k == name), "")
    for pair in query.split("&"):
        key, _, value = pair.partition("=")
        if unquote(key) == name:
            return unquote(value)            # a "+" of base64 stays a "+"
    return ""


def _value(parts, rule):
    """The address a rule finds in a link, or ""."""
    _inc, _exc, action, param, prepend, template = rule
    if action == "redirect":
        value = _query_value(parts.query, param)
    elif action == "base64,redirect":
        value = _base64(_query_value(parts.query, param, plus_is_space=False))
    else:
        if len(parts.path) > MAX_PATH:
            return ""
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
    if not text:
        return ""
    for decode in (lambda s: base64.b64decode(s, validate=True), base64.urlsafe_b64decode):
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
    host = host.rstrip(".")
    if host in _login_hosts():
        return True
    path = re.sub(r"/{2,}", "/", path).lower()
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
    if "%" in parts.netloc or not host.isascii():
        # an escaped or Unicode host can be read otherwise by the engine ("%31%39%32.168.1.1",
        # full-width digits): only a plain host is judged here (shields.py checks the engine's own
        # reading again)
        return None
    from .userscripts import is_local_name
    if is_local_name(host.rstrip(".")):
        return None
    return parts


def _one(address, rule_set):
    """The address one rule finds in this link (unchecked), or ""."""
    parts = urlsplit(address)
    scheme, host = parts.scheme.lower(), (parts.hostname or "").lower().rstrip(".")
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
        host = (cur.hostname or "").lower().rstrip(".")
        site = _site(host, site_of)
        if _safety_stop(host, cur.path, site):
            break
        value = _one(current, rule_set)
        if not value:
            break
        nxt = _usable(value)
        if nxt is None or _site((nxt.hostname or "").lower().rstrip("."), site_of) == site:
            break
        current = found = value
    else:
        return None                    # still a tracker after MAX_STOPS: leave the link as it is
    return found
