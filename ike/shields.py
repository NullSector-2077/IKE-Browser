"""Protection layer: request interception, cookies, injected scripts, profile."""

import functools
import json
import os
import re
import secrets
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, QObject, QUrl, pyqtSignal
from PyQt6.QtWebEngineCore import (
    QWebEngineProfile,
    QWebEngineScript,
    QWebEngineSettings,
    QWebEngineUrlRequestInfo,
    QWebEngineUrlRequestInterceptor,
    QWebEngineUrlRequestJob,
    QWebEngineUrlScheme,
    QWebEngineUrlSchemeHandler,
)

from . import fontcheck, newtab, osinfo
from .config import (
    CACHE_DIR,
    DATA_DIR,
    FIREFOX_UA,
    LEVEL_NAMES,
    LOGIN_HOSTS,
    PAYMENT_SITES,
    RES_DIR,
    SENSITIVE_HOSTS,
    payment_owned,
    rank,
)

TRACKING_PARAMS = {
    "fbclid", "gclid", "gclsrc", "dclid", "gbraid", "wbraid", "msclkid", "yclid",
    "twclid", "ttclid", "igshid", "igsh", "mc_eid", "mc_cid", "_hsenc", "_hsmi",
    "__hssc", "__hstc", "__hsfp", "hsctatracking", "mkt_tok", "oly_anon_id",
    "oly_enc_id", "vero_id", "vero_conv", "s_cid", "rb_clickid", "ml_subscriber",
    "ml_subscriber_hash", "wickedid", "srsltid", "_openstat", "ysclid", "li_fat_id",
    "epik", "irclickid", "sc_cid", "ref_src", "ref_url", "__s", "_ga", "_gl",
}
TRACKING_PREFIXES = ("utm_", "pk_", "mtm_", "stm_")

_RT = QWebEngineUrlRequestInfo.ResourceType
_NT = QWebEngineUrlRequestInfo.NavigationType
_TYPES = {
    _RT.ResourceTypeMainFrame: "document", _RT.ResourceTypeSubFrame: "subdocument",
    _RT.ResourceTypeStylesheet: "stylesheet", _RT.ResourceTypeScript: "script",
    _RT.ResourceTypeImage: "image", _RT.ResourceTypeFontResource: "font",
    _RT.ResourceTypeSubResource: "other", _RT.ResourceTypeObject: "object",
    _RT.ResourceTypeMedia: "media", _RT.ResourceTypeXhr: "xmlhttprequest",
    _RT.ResourceTypePing: "ping", _RT.ResourceTypeCspReport: "csp",
    _RT.ResourceTypeFavicon: "image", _RT.ResourceTypeWebSocket: "websocket",
}
# Qt adds resource kinds over time. Resolve optional enum values without making
# the browser depend on one exact PyQt build; map worker scripts as scripts and
# other auxiliary fetches to the closest ABP/uBlock request category.
for _name, _kind in (
    ("ResourceTypeWorker", "script"), ("ResourceTypeSharedWorker", "script"),
    ("ResourceTypeServiceWorker", "script"), ("ResourceTypePluginResource", "object"),
    ("ResourceTypePrefetch", "other"), ("ResourceTypeJson", "xmlhttprequest"),
    ("ResourceTypeNavigationPreloadMainFrame", "document"),
    ("ResourceTypeNavigationPreloadSubFrame", "subdocument"),
):
    _value = getattr(_RT, _name, None)
    if _value is not None:
        _TYPES[_value] = _kind
_LOCAL = ("localhost", "127.0.0.1", "::1")

# --- pages opened from a file ------------------------------------------
# Qt WebEngine lets a page opened from a file read every other file of the
# computer (fetch, XMLHttpRequest, the content of a framed file); its own
# switch for that also stops the page's pictures and style sheets, so the rules
# are applied here, request by request (Interceptor._local_file):
#   - fetch / XMLHttpRequest / beacons to files: never (as in Chrome and Firefox);
#   - pictures, media, style sheets, scripts, fonts: from anywhere, as always;
#   - frames, embedded objects and everything else, whose content the page
#     could read: only from the page's own folder; for a page lying directly
#     in a shared folder (home, Downloads, Desktop, Documents, ... or /tmp),
#     only from the "<name>_files" folder a saved page keeps its parts in.
_FILE_NEVER = frozenset(t for t in (getattr(_RT, n, None) for n in (
    "ResourceTypeXhr", "ResourceTypePing", "ResourceTypeCspReport", "ResourceTypeJson")) if t is not None)
_FILE_ANYWHERE = frozenset(t for t in (getattr(_RT, n, None) for n in (
    "ResourceTypeImage", "ResourceTypeMedia", "ResourceTypeStylesheet", "ResourceTypeScript",
    "ResourceTypeFontResource", "ResourceTypeFavicon")) if t is not None)
_shared_folders = None


def shared_folders(extra=()):
    """Folders that hold unrelated files of the user: a page lying directly in
    one of them is not given the whole folder."""
    global _shared_folders
    if _shared_folders is None:
        from PyQt6.QtCore import QStandardPaths
        L = QStandardPaths.StandardLocation
        found = {os.path.realpath(os.path.expanduser("~")), "/", "/tmp", "/var/tmp", "/dev/shm"}
        for loc in (L.HomeLocation, L.DesktopLocation, L.DocumentsLocation, L.DownloadLocation,
                    L.MusicLocation, L.MoviesLocation, L.PicturesLocation, L.TempLocation):
            for path in QStandardPaths.standardLocations(loc):
                if path:
                    found.add(os.path.realpath(path))
        _shared_folders = found
    return _shared_folders | {os.path.realpath(p) for p in extra if p}


def local_file_in_reach(page, target, shared=()):
    """May the page opened from the file `page` embed the file `target` as a
    frame or object? (see the rules above; links are followed first, so a link
    inside the page's folder that points elsewhere does not widen it)"""
    try:
        if not page or not target or "\0" in page or "\0" in target:
            return False
        page, target = os.path.realpath(page), os.path.realpath(target)
    except (OSError, ValueError):
        return False
    folder = os.path.dirname(page)
    if folder in shared:
        stem = os.path.splitext(os.path.basename(page))[0]
        if not stem:
            return False
        root = os.path.join(folder, stem + "_files")
    else:
        root = folder
    return target == page or target.startswith(root.rstrip(os.sep) + os.sep)


HTTP_CACHE_BYTES = 512 * 1024 * 1024


def register_scheme():
    """Must run before QApplication is created."""
    s = QWebEngineUrlScheme(b"ike")
    s.setSyntax(QWebEngineUrlScheme.Syntax.Path)
    # The internal start/search pages only need a secure origin. They do not
    # need permission to read local files or bypass a page's CSP.
    s.setFlags(QWebEngineUrlScheme.Flag.SecureScheme)
    QWebEngineUrlScheme.registerScheme(s)


_SLD = frozenset("co com org net gov edu ac or ne go gob nom mil ltd plc sch nhs me info id gv".split())
_HOSTED = (".github.io", ".gitlab.io", ".blogspot.com", ".herokuapp.com", ".pages.dev",
           ".workers.dev", ".netlify.app", ".vercel.app", ".web.app", ".firebaseapp.com",
           ".appspot.com", ".cloudfront.net", ".azurewebsites.net", ".onrender.com",
           ".neocities.org", ".wordpress.com", ".tumblr.com", ".s3.amazonaws.com", ".pp.ua",
           ".myshopify.com", ".substack.com", ".wixsite.com", ".weebly.com", ".fly.dev", ".glitch.me",
           ".repl.co", ".surge.sh", ".ngrok.io", ".ngrok-free.app", ".duckdns.org", ".no-ip.org")
# the Public Suffix List of the system (Arch: publicsuffix-list, a dependency
# of the package, kept current by pacman); the short lists above only when
# it is missing (review of 1.1.19, L10: "a.wordpress.com" and
# "b.wordpress.com" were one site for the filter lists and the permissions)
PSL_PATHS = ["/usr/share/publicsuffix/public_suffix_list.dat"]
_PSL = []
_PSL_FILE = []           # (cache file named after the list's size and time, its sets) of the list in use


def _psl_cached(path):
    """The list as parsed at an earlier start, while the file is the same
    (size and time): about 1 ms instead of about 16 (performance review of
    1.1.20, L4). (cache file, its sets or None)."""
    import marshal
    import os

    from .config import CACHE_DIR
    try:
        st = os.stat(path)
    except OSError:
        return None, None
    cache = CACHE_DIR / ("psl-%d-%d.bin" % (st.st_size, st.st_mtime_ns))
    try:
        rules, wild, exc = marshal.loads(cache.read_bytes())
        if len(rules) > 1000:
            return cache, (frozenset(rules), frozenset(wild), frozenset(exc))
    except (OSError, ValueError, EOFError, TypeError):
        pass
    return cache, None


def _psl_keep(cache, found):
    import marshal
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        for old in cache.parent.glob("psl-*.bin"):
            old.unlink(missing_ok=True)
        tmp = cache.with_suffix(".tmp")
        tmp.write_bytes(marshal.dumps(tuple(tuple(sorted(s)) for s in found)))
        tmp.replace(cache)
    except OSError:
        pass


def _psl():
    """(rules, wildcards, exceptions) of the Public Suffix List, or None."""
    if not _PSL:
        found = None
        _PSL_FILE.clear()
        for path in PSL_PATHS:
            cache, found = _psl_cached(path)
            if found is not None:
                if cache is not None:
                    _PSL_FILE.append((cache, found))
                break
            try:
                with open(path, encoding="utf-8") as f:
                    rules, wild, exc = set(), set(), set()
                    for line in f:
                        r = line.split("//", 1)[0].strip().lower()
                        if not r:
                            continue
                        try:
                            r = r.encode("idna").decode("ascii") if not r.isascii() else r
                        except UnicodeError:
                            pass
                        if r.startswith("!"):
                            exc.add(r[1:])
                        elif r.startswith("*."):
                            wild.add(r[2:])
                        else:
                            rules.add(r)
                if len(rules) > 1000:
                    found = (frozenset(rules), frozenset(wild), frozenset(exc))
                    if cache is not None:
                        _psl_keep(cache, found)
                        _PSL_FILE.append((cache, found))
                    break
            except (OSError, UnicodeError):
                continue
        _PSL.append(found)
    return _PSL[0]


def _site_psl(host, psl):
    rules, wild, exc = psl
    labels = host.split(".")
    for i in range(len(labels)):
        cand = ".".join(labels[i:])
        if cand in exc:                       # "!www.ck": www.ck is the site
            return cand
        parent = ".".join(labels[i + 1:])
        if cand in rules or (i + 1 < len(labels) and parent in wild):
            # cand is a public suffix: the site is one more label
            return ".".join(labels[i - 1:]) if i > 0 else host
    # not in the list: the default rule "*" (the last label is the suffix)
    return ".".join(labels[-2:])


# The Public Suffix List for fingerprint.js's siteOf() (1.1.21, fingerprinting
# audit L-2): its own short list of hosting domains made two unrelated sites
# under another one (a.altervista.org, b.altervista.org) one site, with the
# same noise. The page gets the list's rules as 24-bit FNV-1a hashes, four
# characters each, sorted (about 35 KB instead of 130; a binary search): the
# rules of two labels or more, "*.x" and "!x" (one-label rules answer as the
# default rule does). A hash that matches by chance (about 1 in 2000 names)
# makes that site one label longer: its noise differs from its parent's, never
# shared with another site.
PSL_DIGITS = "-.0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
_PSL_CODES = []


def psl_code(rule):
    h = 2166136261
    for ch in rule:
        h ^= ord(ch)
        h = (h * 16777619) & 0xFFFFFFFF
    v = h >> 8
    return "".join(PSL_DIGITS[(v >> k) & 63] for k in (18, 12, 6, 0))


def _psl_codes_of(psl):
    rules, wild, exc = psl
    names = [r for r in rules if "." in r] + ["*." + w for w in wild] + ["!" + e for e in exc]
    return "".join(sorted({psl_code(n) for n in names}))


# The codes are kept next to the parsed list, under the same size and time of
# the system's file (1.1.22): working them out took about 19 ms at every
# start, before the first page. The number changes whenever psl_code or the
# choice of rules above changes, so an older answer is never read.
PSL_CODES_FORMAT = 1


def psl_codes():
    """The sorted codes of the list's rules for fingerprint.js, or "" (no list)."""
    if not _PSL_CODES:
        psl = _psl()
        out = ""
        if psl is not None:
            kept = None
            if _PSL_FILE and _PSL_FILE[0][1] is psl:
                src = _PSL_FILE[0][0]
                kept = src.with_name("pslcodes-%d-%s.txt" % (PSL_CODES_FORMAT, src.stem[len("psl-"):]))
                try:
                    out = kept.read_text("ascii")
                except (OSError, ValueError):
                    out = ""
            # read back only whole codes of the list's own characters
            # (strip leaves nothing when every character is one of them)
            if not out or len(out) % 4 or out.strip(PSL_DIGITS):
                out = _psl_codes_of(psl)
                if kept is not None:
                    try:
                        for old in kept.parent.glob("pslcodes-*.txt"):
                            old.unlink(missing_ok=True)
                        tmp = kept.with_suffix(".tmp")
                        tmp.write_text(out, "ascii")
                        tmp.replace(kept)
                    except OSError:
                        pass
        _PSL_CODES.append(out)
    return _PSL_CODES[0]


def _referer(info):
    """The Referer the engine is about to send with this request, or ""."""
    try:
        for k, v in info.httpHeaders().items():
            if bytes(k).lower() == b"referer":
                return bytes(v).decode("latin-1")
    except Exception:
        pass
    return ""


_FULL_VERSION = (b"sec-ch-ua-full-version", b"sec-ch-ua-full-version-list")


def _reduce_full_version(info):
    """At Strict and Maximum JavaScript gives Chrome's version as 140.0.0.0
    (fingerprint.js, getHighEntropyValues); the client hints a site asked for
    say the same (1.1.18, owner's decision): before, the headers carried the
    full version, so the page saw two different ones. Only hints the engine is
    already sending are changed; none is added."""
    try:
        headers = info.httpHeaders()
    except Exception:
        return
    for k, v in headers.items():
        name = bytes(k)
        if name.lower() in _FULL_VERSION:
            value = bytes(v)
            reduced = re.sub(rb'"(\d+)(?:\.\d+)+"', rb'"\1.0.0.0"', value)
            if reduced != value:
                info.setHttpHeader(name, reduced)


# The names of the two scripts that run in the page's own world: an error's
# stack names them ("userscript:<name>"), and "ike-fp" named I.K.E.
# (fingerprinting audit, M-5)
FP_SCRIPT = "content"
MEDIA_SCRIPT = "content-2"


# 1.1.23 (comparison with Falkon): where the engine runs a profile script.
# A blocked frame shows the engine's own error page (chrome-error://), which
# no page can reach: the scripts protect nothing there, and every blocked ad
# frame paid for all of them (-25 % of the load time of a page with 20
# blocked frames). The scripts of a site (its list scriptlets, the video
# sites' scripts) are compiled only in documents of that site and in the
# empty frames that take their parent's site; their own check of the host
# stays, as a second guard. Qt reads these lines wherever they are in the
# script: they go at its end, so the line numbers of the script, which an
# error's stack shows, stay as they were.
ERROR_PAGES = "chrome-error://*"
EMPTY_FRAMES = ("about:blank*", "about:srcdoc*")


def host_globs(host, subdomains=False):
    """The addresses of one host, as Qt's @include patterns: any scheme and
    port, with or without a user name (the script still checks the host)."""
    out = []
    for h in ([host, "*." + host] if subdomains else [host]):
        for head in ("*://", "*://*@"):
            out += [head + h + "/*", head + h + ":*/*"]
    return out


def limited(source, include=()):
    """source with the header that tells the engine where it runs: never in an
    error page, and only at the addresses of `include` when it is given."""
    lines = ["", "// ==UserScript=="]
    lines += ["// @include " + g for g in include]
    lines += ["// @exclude " + ERROR_PAGES, "// ==/UserScript==", ""]
    return source + "\n".join(lines)


def one_language(cfg):
    """The Accept-Language of Strict: the first language in use, and its base
    language after it, as Chrome sends one language ("it-IT,it;q=0.9")."""
    from .config import engine_language
    return _one_language(engine_language(cfg))


@functools.lru_cache(maxsize=16)
def _one_language(header):
    first = (header or "").split(",")[0].split(";")[0].strip() or "en-US"
    if not re.fullmatch(r"[A-Za-z]{1,8}(-[A-Za-z0-9]{1,8})*", first):
        first = "en-US"
    base = first.split("-")[0]
    return (first if base == first else "%s,%s;q=0.9" % (first, base)).encode("ascii")


@functools.lru_cache(maxsize=4096)
def site_of(host):
    """Registrable domain of a host: "www.bbc.co.uk" -> "bbc.co.uk".

    Asked several times for every request of every page, always for the same
    few hosts: remembered (a pure function of its argument, 1.1.17)."""
    host = (host or "").rstrip(".")
    parts = host.split(".")
    if len(parts) < 2 or host.replace(".", "").isdigit() or ":" in host:
        return host
    psl = _psl()
    if psl is not None:
        return _site_psl(host.lower(), psl)
    if len(parts) <= 2:
        return host
    three = host.endswith(_HOSTED) or (len(parts[-1]) == 2 and parts[-2] in _SLD)
    return ".".join(parts[-3 if three else -2:])


def strip_tracking(url):
    """Return url without known tracking parameters (or None if unchanged)."""
    parts = urlsplit(url)
    if not parts.query:
        return None
    pairs = parse_qsl(parts.query, keep_blank_values=True)
    kept = [(k, v) for k, v in pairs
            if k.lower() not in TRACKING_PARAMS
            and not k.lower().startswith(TRACKING_PREFIXES)]
    if len(kept) == len(pairs):
        return None
    return urlunsplit(parts._replace(query=urlencode(kept, quote_via=quote)))


class Interceptor(QWebEngineUrlRequestInterceptor):
    def __init__(self, shields, quiet=False):
        super().__init__(shields)
        self.s = shields
        # quiet: the same protections, but nothing is counted in the shield
        # (pages loaded by I.K.E. itself, such as the page watcher)
        self.quiet = quiet

    def _count(self, host, kind):
        if not self.quiet:
            self.s.count(host, kind)

    def _local_file(self, info, url):
        """A request for a file of the computer: is it allowed? (rules at the top)"""
        rtype = info.resourceType()
        if rtype == _RT.ResourceTypeMainFrame:
            return True                      # opening a file: the engine's own rules apply
        first = info.firstPartyUrl()
        if first.scheme() != "file":
            # A web page never gets a file (the engine refuses that itself);
            # the engine's own viewers may fetch the file they were opened for.
            web = ("http", "https", "ws", "wss", "data", "blob", "ike")
            return first.scheme() not in web and info.initiator().scheme() not in web
        if rtype in _FILE_NEVER:
            return False
        if rtype in _FILE_ANYWHERE:
            return True
        cfg = self.s.config
        return local_file_in_reach(first.toLocalFile(), url.toLocalFile(),
                                   shared_folders((cfg["download_dir"],)))

    def _https_upgrade(self, info, url, host, scheme):
        """An http page sent to its https address (automatic HTTPS); True when it was."""
        s, cfg = self.s, self.s.config
        if not (scheme == "http" and cfg["https_only"] and cfg.site_opt(host, "https") is not False
                and host not in _LOCAL
                and host not in s.http_allowed and "." in host
                and not host.replace(".", "").isdigit()):
            return False
        https = QUrl(url)
        https.setScheme("https")
        s.upgraded.add(host)
        self._count(host, "https")
        s.redirected.add(https.toString())
        info.redirect(https)
        return True

    def _lan_refused(self, info, url, main):
        """Home network protection (1.1.17): a page of a public site that opens
        an address of this computer or of the home network (a form sent to the
        router, a frame of a local service) is stopped, and the window asks
        the user (securebar.py). Since 1.1.18 every kind of request is looked
        at (security audit F2: the engine stopped none of them - a POST from
        fetch, a picture, a script, a WebSocket all reached the router), and a
        stopped one shows the same notice ("a part of this page"). Addresses
        the user opens are not touched; only names and addresses that are
        local by their form are looked at (no lookup here)."""
        from .userscripts import is_local_name
        if not is_local_name(url.host()):
            return False
        try:
            init = info.initiator()
        except AttributeError:
            return False
        scheme = init.scheme()
        if scheme in ("http", "https"):
            if is_local_name(init.host()):
                return False              # a page of the home network itself
            who = site_of(init.host().lower())
        elif scheme:
            return False                  # I.K.E.'s own pages (ike:), the user's files
        elif main:
            # no initiator: the user typed or chose the address - unless it is
            # a link or a form of a page with no origin of its own (a
            # sandboxed frame's popup, a data: page): those are a public
            # page's (1.1.18, adversarial review)
            nav = info.navigationType()
            if nav not in (_NT.NavigationTypeLink, _NT.NavigationTypeFormSubmitted):
                return False
            who = ""
        else:
            # a sandboxed or data: frame has no origin, so no initiator: it is
            # judged by the page it is in (1.1.18, adversarial review: such a
            # frame of a public page reached the router)
            first = info.firstPartyUrl()
            if first.scheme() not in ("http", "https") or is_local_name(first.host()):
                return False
            who = site_of(first.host().lower())
        s = self.s
        if who and who in s.lan_allowed:
            return False
        info.block(True)
        if not self.quiet:
            if len(s.lan_blocked) > 100:
                s.lan_blocked.clear()
            if main:
                s.lan_blocked[url.toString()] = who
            else:
                # a frame or a part of the page: the page itself loads, and the
                # window says what was stopped in it (no silent breakage)
                s.lan_blocked["frame:" + info.firstPartyUrl().toString()] = who
        return True

    def interceptRequest(self, info):
        """Every request of every page. An unexpected error in the checks is
        counted and logged like the engine's own (Help -> About), and a file
        of the computer stays refused (1.1.17: such an error let the request
        through unnoticed)."""
        try:
            self._intercept(info)
        except Exception as exc:
            try:
                url = info.requestUrl()
                self.s.blocker._engine_error("checking a request", url.toString(), exc)
                # what was protected stays protected: a file of the computer,
                # and an address of the home network asked for by a public site
                from .userscripts import is_local_name
                init = info.initiator()
                if url.scheme() == "file" or (
                        is_local_name(url.host()) and init.scheme() in ("http", "https")
                        and not is_local_name(init.host())):
                    info.block(True)
            except Exception:
                pass

    def _intercept(self, info):
        s = self.s
        cfg = s.config
        url = info.requestUrl()
        scheme = url.scheme()
        if scheme == "file":
            if not self._local_file(info, url):
                info.block(True)
            return
        if scheme not in ("http", "https", "ws", "wss"):
            return
        rtype = info.resourceType()
        main = rtype == _RT.ResourceTypeMainFrame
        if self._lan_refused(info, url, main):
            return
        first = url if main else info.firstPartyUrl()
        # the page the request belongs to is known (not a service worker's own
        # request, which has none): only then can it go the "free way"
        first_known = main or not first.isEmpty()
        if not main and first.isEmpty():
            try:
                first = info.initiator()
            except AttributeError:
                pass
        if first.isEmpty():
            first = url
        first_host = first.host().lower()
        first_site = site_of(first_host)
        if not self.quiet:
            s.requests[first_site] = s.requests.get(first_site, 0) + 1      # per-site resources
        lv = rank(cfg.level_for(first_host))
        if lv == 0:
            return
        host = url.host().lower()
        host_site = site_of(host)
        method = bytes(info.requestMethod())
        get = method == b"GET"
        if cfg.sensitive_hands_off(first_host, host):
            # a sensitive Google service (AI Studio, Cloud Console, account,
            # payments): Google's own requests go through untouched - no filter
            # list, no address clean-up, no changed header (1.1.14); the
            # connection is still made secure (1.1.18, independent review: an
            # http address of such a service was not upgraded)
            if main and get and self._https_upgrade(info, url, host, scheme):
                return
            if main and not self.quiet:
                key = url.toString()
                if key in s.redirected:
                    s.redirected.discard(key)
                else:
                    s.reset_count(host)
            return
        if not main and payment_owned(host):
            # PayPal's and Stripe's own parts of a shop (payment buttons and
            # fields, anti-fraud checks): never blocked or changed (1.1.14)
            return
        if host == "accounts.google.com" and cfg["login_compat"]:
            # Google refuses sign-in from embedded Chromium engines; it accepts
            # the same request when it comes with a Firefox identity.
            info.setHttpHeader(b"User-Agent", FIREFOX_UA.encode())

        if main:
            # a new page starts: restart the per-site counters, except when this
            # request is the continuation of our own redirect
            key = url.toString()
            if key in s.redirected:
                s.redirected.discard(key)
            elif not self.quiet:
                s.reset_count(host)
        if main and get:
            if self._https_upgrade(info, url, host, scheme):
                return
            if cfg["strip_tracking_params"] and cfg.site_opt(host, "params") is not False:
                clean = strip_tracking(url.toString())
                if clean:
                    self._count(host, "params")
                    s.redirected.add(QUrl(clean).toString())
                    info.redirect(QUrl(clean))
                    return

        if (not main and lv <= 2 and first_known and host_site == first_site
                and first_site not in s.full_blocking_sites()):
            # "Same site, free way" (1.1.15): at Balanced and below, what a site
            # asks of itself is not checked against the filter lists - faster
            # (most requests of a page are the site's own) and fewer broken sites. The ads and trackers of
            # other companies stay blocked, element hiding stays on, Strict and
            # Maximum block everything, and the video sites always do.
            if cfg["send_gpc"]:
                info.setHttpHeader(b"Sec-GPC", b"1")
            return

        # Main-frame GET requests must also be evaluated by the filter engine.
        # Previously the `elif` paired with the main-frame URL rewriting branch
        # skipped network filters for every normal top-level navigation.
        if ((cfg["comp_adblock"] or cfg["comp_consent"])
                and cfg.site_opt(first_host, "ads") is not False
                and not (main and host in s.pages_allowed)):
            method = method.decode("ascii", "ignore").upper() or "GET"
            action, target = s.blocker.request_action(
                url.toString(), first.toString(), _TYPES.get(rtype, "other"), method)
            if action == "redirect" and target:
                # Redirect resources supplied by adblock-rust are data: URLs.
                # Do not let a filter list turn the interceptor into an
                # unrestricted redirector.
                if target.startswith("data:"):
                    info.redirect(QUrl(target))
                else:
                    info.block(True)
                self._count(first_host, "scripts" if rtype == _RT.ResourceTypeScript else "ads")
                return
            if action == "block":
                info.block(True)
                if main and not self.quiet:
                    if len(s.blocked_pages) > 100:
                        s.blocked_pages.clear()
                    s.blocked_pages.add(url.toString())   # the window explains it (securebar.py)
                self._count(first_host, "scripts" if rtype == _RT.ResourceTypeScript else "ads")
                return
            if action == "rewrite" and target and method == "GET":
                # A list rule removed tracking parameters from the address. Only
                # the query may differ: same scheme, host and path.
                new = QUrl(target)
                if (new.isValid() and new.scheme() == url.scheme() and new.host() == url.host()
                        and new.path() == url.path() and new != url):
                    info.redirect(new)
                    self._count(first_host, "params")
                    return

        if cfg["send_gpc"]:
            info.setHttpHeader(b"Sec-GPC", b"1")
        if lv >= 3 and cfg.site_opt(first_host, "fp") is not False:
            _reduce_full_version(info)
            if lv >= 4:
                info.setHttpHeader(b"Accept-Language", b"en-US,en;q=0.9")
            else:
                # Strict: the one language navigator.languages shows, as
                # Chrome writes it; the full list in the header contradicted
                # it (review of 1.1.19, M5)
                info.setHttpHeader(b"Accept-Language", one_language(cfg))
        if (lv >= 2 and cfg["trim_referrer"] and not main
                and host_site != first_site
                and cfg.site_opt(first_host, "params") is not False):
            # Only a Referer the request already carries is cut to its origin
            # (1.1.18, independent review): adding one where the page's
            # referrer policy sends none (no-referrer, same-origin) made the
            # engine cancel the request, and a frame's own requests got the
            # top site's origin instead of the frame's.
            ref = _referer(info)
            if ref:
                r = QUrl(ref)
                if r.scheme() in ("http", "https") and r.host():
                    origin = "%s://%s/" % (r.scheme(), r.host())
                    if r.port() > 0:
                        origin = "%s://%s:%d/" % (r.scheme(), r.host(), r.port())
                    if origin != ref:
                        info.setHttpHeader(b"Referer", origin.encode())


class IkeSchemeHandler(QWebEngineUrlSchemeHandler):
    """Serves ike:newtab, ike:search?q=..., ike:logo and ike:background.

    Only to I.K.E. itself: a request that comes from a web page (a picture,
    a frame, a form, a link) is refused. Otherwise any site could recognise
    the browser by loading its logo, or show the user's own new tab page
    inside a page of its own."""

    def __init__(self, shields):
        super().__init__(shields)
        self.s = shields

    @staticmethod
    def own_request(job):
        """True for the address bar, bookmarks and the like (no initiator) and
        for requests made by I.K.E.'s own pages."""
        who = job.initiator()
        return who.isEmpty() or who.scheme() == "ike"

    def requestStarted(self, job):
        url = job.requestUrl()
        path = url.path()
        if not self.own_request(job):
            job.fail(QWebEngineUrlRequestJob.Error.RequestDenied)
            return
        if path == "search":
            from PyQt6.QtCore import QUrlQuery
            q = QUrlQuery(url).queryItemValue("q", QUrl.ComponentFormattingOption.FullyDecoded)
            q = q.replace("+", " ")
            job.redirect(QUrl(self.s.search_url(q)))
            return
        if path in ("open", "engine", "tile") and not secrets.compare_digest(
                QUrlQuery_value(url, "k") or "", self.s.action_key):
            # an address that changes something works only from the new tab
            # page itself, which carries this session's key in its links: a
            # web page's link opened from the right-click menu (no initiator)
            # cannot add a bookmark or change the search engine (1.1.17)
            job.redirect(QUrl("ike:newtab"))
            return
        if path == "open":
            # the Settings or the background photo, asked for on the new tab page itself
            what = QUrlQuery_value(url, "what")
            if what in ("settings", "background"):
                self.s.open_requested.emit(what)
            job.redirect(QUrl("ike:newtab"))
            return
        if path == "engine":
            # an engine chosen in the new tab page's search box: the default from now on
            self.s.choose_engine(QUrlQuery_value(url, "name"))
            job.redirect(QUrl("ike:newtab"))
            return
        if path == "tile":
            # an answer given on the new tab page itself (a tile hidden or added);
            # the page is shown again afterwards
            from PyQt6.QtCore import QUrlQuery
            items = QUrlQuery(url).queryItems(QUrl.ComponentFormattingOption.FullyDecoded)
            self.s.newtab_answer(path, dict(items))
            job.redirect(QUrl("ike:newtab"))
            return
        if path == "favicon":
            data = self.s.favicon_png(QUrlQuery_value(url, "h"))
            mime = b"image/png"
            if not data:
                job.fail(QWebEngineUrlRequestJob.Error.UrlNotFound)
                return
        elif path == "logo":
            data = (RES_DIR / "ike.svg").read_bytes()
            mime = b"image/svg+xml"
        elif path == "background":
            from . import newtabbg
            data, mime = newtabbg.content(self.s.config)         # the user's own photo
            if data is None:
                job.fail(QWebEngineUrlRequestJob.Error.RequestDenied)
                return
        else:
            data = self.s.newtab_html().encode("utf-8")
            mime = b"text/html"
        buf = QBuffer(job)
        buf.setData(QByteArray(data))
        buf.open(QIODevice.OpenModeFlag.ReadOnly)
        job.reply(mime, buf)


def QUrlQuery_value(url, key):
    from PyQt6.QtCore import QUrlQuery
    return QUrlQuery(url).queryItemValue(key, QUrl.ComponentFormattingOption.FullyDecoded)


class Shields(QObject):
    blocked = pyqtSignal(str)  # first-party host
    open_requested = pyqtSignal(str)     # "settings" / "background" asked for on the new tab page
    engine_chosen = pyqtSignal(str)      # an engine chosen on the new tab page (1.1.10)

    def __init__(self, config, blocker, parent=None):
        super().__init__(parent)
        self.config = config
        self.blocker = blocker
        # One fingerprint-noise key per WebEngine profile. Private and
        # container profiles must not share the same per-site noise stream.
        self.profile_keys = {}
        # the media-command events' own secret (mediahook.js), never derived
        # from the fingerprinting key (1.1.18, security audit: it was the
        # key's first 96 bits, readable on media sites)
        self.media_keys = {}
        self.action_key = secrets.token_hex(16)   # the new tab page's own links (IkeSchemeHandler)
        self.stats = {}
        self.requests = {}               # site -> requests made for it (see resources)
        self.redirected = set()
        self.upgraded = set()
        self.http_allowed = set()
        self.pages_allowed = set()      # sites the user opened anyway though the lists block them (securebar.py)
        self.blocked_pages = set()      # whole pages the lists stopped, until their error is shown
        self.lan_blocked = {}           # local address a public page tried to open -> that site
        self.lan_allowed = set()        # public sites the user let open local addresses (session)
        self.profiles = []
        self.user_scripts = None         # set by the application
        self.interceptor = Interceptor(self)
        self.scheme_handler = IkeSchemeHandler(self)
        self._fp_src = (RES_DIR / "fingerprint.js").read_text("utf-8")
        self._media_src = (RES_DIR / "mediahook.js").read_text("utf-8")
        self._consent_src = (RES_DIR / "consent.js").read_text("utf-8")
        # the full name is drawn as paths (tools/make-brand.py), in the colour of the page text
        self._newtab_src = (RES_DIR / "newtab.html").read_text("utf-8").replace(
            "{{wordmark}}", (RES_DIR / "wordmark.svg").read_text("utf-8").strip())
        self._videoads_src = (RES_DIR / "videoads.js").read_text("utf-8")
        self._videorelay_src = (RES_DIR / "videorelay.js").read_text("utf-8")
        self._site_lru = {}              # id(profile) -> [host, ...] most recent last
        self._blocked_due = set()        # sites whose blocks the windows have not heard of yet
        blocker.rebuilt.connect(self._rules_changed)

    # --- stats -------------------------------------------------------
    KINDS = ("ads", "scripts", "cookies", "https", "params")

    def count(self, host, kind):
        st = self.stats.get(host)
        if st is None:
            st = self.stats[host] = dict.fromkeys(self.KINDS, 0)
        st[kind] += 1
        if kind in ("ads", "scripts"):
            newtab.count_blocked(self.config)       # the total and the month's own count
            # A page full of ads blocks hundreds of things while it loads: the
            # windows hear of it once per site every few milliseconds, after
            # the counts are in (1.1.18: once per request, a third of the
            # time spent checking a page's requests)
            due = self._blocked_due
            if host not in due:
                due.add(host)
                if len(due) == 1:
                    from PyQt6.QtCore import QTimer
                    QTimer.singleShot(self.BLOCKED_EVERY_MS, self._tell_blocked)

    BLOCKED_EVERY_MS = 16

    def _tell_blocked(self):
        due, self._blocked_due = self._blocked_due, set()
        for host in due:
            self.blocked.emit(host)

    def site_stats(self, host):
        return self.stats.get(host) or dict.fromkeys(self.KINDS, 0)

    def total(self, host):
        st = self.stats.get(host)
        return (st["ads"] + st["scripts"]) if st else 0

    def reset_count(self, host):
        self.stats.pop(host, None)

    # --- search / new tab --------------------------------------------
    def favicon_png(self, host):
        """PNG of the icon kept for a site (for the tiles), or b""."""
        icons = getattr(self.parent(), "favicons", None)
        if icons is None or not host or len(host) > 255:
            return b""
        row = icons.db.execute("SELECT png FROM icons WHERE host=?", (host.lower(),)).fetchone()
        return bytes(row[0]) if row and row[0] else b""

    def newtab_answer(self, what, query):
        """A choice made on the new tab page: a tile hidden or added."""
        from . import newtab
        app = self.parent()
        storage = getattr(app, "storage", None)
        if what == "tile":
            if query.get("hide"):
                newtab.hide_tile(self.config, query["hide"])
            address = newtab.web_address(query.get("add", ""))
            if address:
                newtab.put_first(self.config, address)
            if address and storage is not None and not storage.is_bookmarked(address):
                from urllib.parse import urlsplit
                host = urlsplit(address).hostname or address
                storage.add_bookmark(address, host[4:] if host.startswith("www.") else host)
                refresh = getattr(app, "refresh_windows", None)
                if refresh is not None:
                    from PyQt6.QtCore import QTimer
                    QTimer.singleShot(0, refresh)             # the bookmarks bar and menu
        self.config.save()

    def choose_engine(self, name):
        """The default engine, chosen on the new tab page (before the page is shown again)."""
        if name and name != self.config["default_engine"] and any(
                isinstance(e, dict) and e.get("name") == name for e in self.config["search_engines"]):
            self.config["default_engine"] = name
            self.config.save()
            self.engine_chosen.emit(name)

    def search_url(self, query, engine=None):
        e = self.config.engine(engine)
        return e["url"].replace("{q}", quote(query, safe=""))

    def newtab_palette(self):
        """The colours of the new tab page: the interface's, or the I.K.E.
        theme's behind I.K.E.'s own (dark) photo on a light interface."""
        from PyQt6.QtGui import QGuiApplication, QPalette

        from . import newtabbg
        pal = QGuiApplication.palette()
        if newtabbg.is_default(self.config) and newtabbg.current(self.config) is not None \
                and pal.color(QPalette.ColorRole.Window).lightnessF() >= 0.5:
            # I.K.E.'s own photo is dark: on a light interface the page takes the
            # colours of the I.K.E. theme, so that its text stays readable on it
            from . import themes
            pal = themes.palette(themes.BUILTIN["ike"])
        return pal

    def newtab_background(self):
        """The colour the new tab page paints first (its --bg)."""
        from PyQt6.QtGui import QPalette
        return self.newtab_palette().color(QPalette.ColorRole.Window)

    def newtab_html(self):
        from .i18n import T
        e = self.config.engine()
        html = self._newtab_src
        from PyQt6.QtGui import QPalette
        pal = self.newtab_palette()
        R = QPalette.ColorRole
        colors = {"{{bg}}": pal.color(R.Window), "{{fg}}": pal.color(R.WindowText),
                  "{{card}}": pal.color(R.Base), "{{acc}}": pal.color(R.Highlight),
                  "{{line}}": pal.color(R.Mid), "{{mute}}": pal.color(R.PlaceholderText)}
        # the dimmed text and the accent (the large numbers, the outlines) as
        # readable on the page as WCAG asks, 4.5:1 and 3:1 (1.1.22: LXQt's dark
        # palette gave a dark red #640b0c on #232323, 1.4:1)
        from .uistyle import readable
        bg, fg = colors["{{bg}}"], colors["{{fg}}"]
        colors["{{mute}}"] = readable(colors["{{mute}}"], bg, fg)
        colors["{{acc}}"] = readable(colors["{{acc}}"], bg, fg, 3.0)
        for k, c in colors.items():
            html = html.replace(k, c.name())
        import html as _html
        corner = ""
        if self.config["newtab_clock"]:
            corner += '<div class="clock" id="clock"></div><div class="date" id="date"></div>'
        if self.config["newtab_weather"]:
            corner += '<div class="weather" id="weather">%s</div>' % _html.escape(self.weather_text())
        from . import i18n, newtabbg
        html = html.replace("{{corner}}", corner).replace("{{lang}}", i18n.current().replace("_", "-"))
        from . import effects, newtab
        photo = newtabbg.style(self.config)
        html = html.replace("{{background}}", photo)
        app = self.parent()
        for k, v in {
            "{{placeholder}}": _html.escape(T("Search with %s or enter address") % e["name"], quote=True),
            # tiles lift on hover, only with the interface effects on (polish.py)
            "{{fx}}": "fx" if effects.on(self.config) else "",
            "{{photo}}": " photo" if photo else "",
            "{{buttons}}": self._newtab_buttons(),
            "{{engines}}": newtab.engines_html(self.config),
            "{{tiles}}": newtab.tiles_html(self.config, getattr(app, "storage", None)),
            "{{stats}}": newtab.stats_html(self.config, T("Protection level"),
                                           T(LEVEL_NAMES[self.config["shield_level"]])),
        }.items():
            html = html.replace(k, v)
        return self.with_action_key(html)

    def with_action_key(self, html):
        """The new tab page's addresses that change something carry the
        session's key (see IkeSchemeHandler); the page is built by I.K.E., the
        key never reaches a web page."""
        import re
        key = self.action_key
        html = re.sub(r'href="(ike:(?:open|engine|tile)\?[^"]*)"', lambda m: 'href="%s&amp;k=%s"' % (m.group(1), key), html)
        # the key goes last in the form: the page's script looks for its first field
        start = html.find('action="ike:tile"')
        end = html.find("</form>", start) if start >= 0 else -1
        if end < 0:
            return html
        return html[:end] + '<input type="hidden" name="k" value="%s">' % key + html[end:]

    def _newtab_buttons(self):
        """Settings (top right) and the background photo (bottom left) on the new tab page;
        they are answers of the page itself (ike:open), refused from websites."""
        import html as _html

        from .config import RES_DIR
        from .i18n import T
        out = []
        for cls, what, icon, label in (("nt-settings", "settings", "configure", T("Settings")),
                                       ("nt-photo", "background", "image-x-generic", T("Background photo"))):
            try:
                svg = (RES_DIR / "icons" / "sets" / "lucide" / (icon + ".svg")).read_text("utf-8")
            except OSError:
                svg = ""
            out.append('<a class="nt-btn %s" href="ike:open?what=%s" title="%s"><span class="ico">%s</span>'
                       '<span class="name">%s</span></a>' % (cls, what, _html.escape(label, quote=True), svg,
                                                            _html.escape(label)))
        return "".join(out)

    def weather_text(self):
        """"☁ 12 °C · Cloudy · Rome", or "" (no city, switched off, not known yet)."""
        from .i18n import T
        weather = getattr(self.parent(), "weather", None)
        w = weather.current() if weather is not None else None
        if not w:
            return ""
        parts = ["%s %s %s" % (w["symbol"], w["temp"], w["unit"]), T(w["label"]) if w["label"] else "",
                 w["city"]]
        return " · ".join(p.strip() for p in parts if p and p.strip())

    # --- profile -----------------------------------------------------
    def chrome_major(self):
        from . import chromever
        return str(chromever.current(self.config))

    def user_agent(self):
        return osinfo.chrome_user_agent(self.chrome_major())

    def request_language(self, first_host):
        """The Accept-Language a request of a page of first_host carries (as
        the request check writes it), for I.K.E.'s own requests on a page's
        behalf."""
        cfg = self.config
        if rank(cfg.level_for(first_host)) >= 3 and cfg.site_opt(first_host, "fp") is not False:
            return b"en-US,en;q=0.9" if rank(cfg.level_for(first_host)) >= 4 else one_language(cfg)
        from .config import engine_language
        return engine_language(cfg).encode("ascii", "replace")

    def _identity(self, profile):
        """Present the engine's own Chrome version, the same in the header, in
        JavaScript and in the client hints (1.1.14; see chromever)."""
        if profile.httpUserAgent() != self.user_agent():
            profile.setHttpUserAgent(self.user_agent())
        try:
            from . import chromever
            hints = profile.clientHints()
            full = chromever.engine_full()
            hints.setFullVersionList({"Chromium": full, "Google Chrome": full,
                                      "Not=A?Brand": "24.0.0.0"})
            hints.setFullVersion(full)
            ident = osinfo.identity()
            hints.setPlatform(ident["platform"])
            hints.setPlatformVersion(ident["platform_version"])
            hints.setModel("")
        except Exception:
            pass

    def make_profile(self, private=False, parent=None, container=None, quiet=False):
        """quiet: a private profile whose pages are not counted in the shield."""
        if private:
            profile = QWebEngineProfile(parent)
        else:
            sub = "profile" if not container else "containers/" + container
            profile = QWebEngineProfile("ike" if not container else "ike-" + container, parent)
            profile.setPersistentStoragePath(str(DATA_DIR / sub))
            profile.setCachePath(str(CACHE_DIR / ("web" if not container else "web-" + container)))
            # a disk cache big enough for the scripts of the heavy sites
            # (YouTube's player alone is several MB) and their compiled code,
            # so a second visit starts from the disk, not the network (1.1.13)
            profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.DiskHttpCache)
            profile.setHttpCacheMaximumSize(HTTP_CACHE_BYTES)
            profile.setPersistentCookiesPolicy(
                QWebEngineProfile.PersistentCookiesPolicy.AllowPersistentCookies)
        self.profile_keys[id(profile)] = secrets.token_hex(16)
        self.media_keys[id(profile)] = secrets.token_hex(16)
        self._identity(profile)
        if quiet:
            profile._ike_interceptor = Interceptor(self, quiet=True)
            profile.setUrlRequestInterceptor(profile._ike_interceptor)
        else:
            profile.setUrlRequestInterceptor(self.interceptor)
        profile.installUrlSchemeHandler(b"ike", self.scheme_handler)
        profile.cookieStore().setCookieFilter(
            (lambda r: self._cookie_filter(r, quiet=True)) if quiet else self._cookie_filter)
        self._track_cookies(profile)
        st = profile.settings()
        A = QWebEngineSettings.WebAttribute
        for attr, val in (
            (A.FullScreenSupportEnabled, True), (A.ScrollAnimatorEnabled, True),
            (A.PluginsEnabled, True), (A.PdfViewerEnabled, True),
            (A.DnsPrefetchEnabled, False), (A.HyperlinkAuditingEnabled, False),
            (A.JavascriptCanOpenWindows, False), (A.ScreenCaptureEnabled, True),
            (A.PlaybackRequiresUserGesture, False), (A.LocalStorageEnabled, True),
            # Clipboard access by page JavaScript remains disabled. Browser UI
            # copy/paste continues to use Qt's clipboard directly; web pages
            # must request the ClipboardReadWrite permission when supported.
            (A.JavascriptCanAccessClipboard, False),
        ):
            st.setAttribute(attr, val)
        self.profiles.append(profile)
        self.apply_settings(profile)
        return profile

    def _cookie_filter(self, request, quiet=False):
        cfg = self.config
        host = request.firstPartyUrl.host().lower()
        mode = cfg.site_opt(host, "cookies")      # None | "allow" | "3p" | "all"
        if mode == "allow":
            return True
        if mode == "all" and cfg.level_for(host) != "off":
            if not quiet:
                self._count_cookie(host)
            return False
        if not request.thirdParty:
            return True
        if cfg["login_compat"] and request.origin.host().lower() in LOGIN_HOSTS:
            return True                           # "Sign in with Google" and similar
        if payment_owned(request.origin.host()):
            return True                           # PayPal's and Stripe's frames in a shop (1.1.14)
        if mode != "3p":
            if not cfg["block_third_party_cookies"]:
                return True
            if rank(cfg.level_for(host)) < 2:     # off / compatibility keep them
                return True
        elif cfg.level_for(host) == "off":
            return True
        if not quiet:
            self._count_cookie(host)
        return False

    def _count_cookie(self, host):
        st = self.stats.get(host)
        if st is None:
            st = self.stats[host] = dict.fromkeys(self.KINDS, 0)
        st["cookies"] += 1

    def media_token(self, profile):
        """The secret of a profile's media-command events (mediahook.js)."""
        return "m" + self.media_keys.get(id(profile), "")

    # The default font families Chrome uses on Linux (owner's decision for
    # 1.1.20, fingerprinting audit M-3): Qt's own defaults are the desktop's
    # fonts, which a page read by name (getComputedStyle: "DejaVu Serif") and
    # measured (the interface font as sans-serif). The fonts drawn are the
    # system's own substitutes for these names (fontconfig).
    CHROME_FONTS = (("StandardFont", "Times New Roman"), ("SerifFont", "Times New Roman"),
                    ("SansSerifFont", "Arial"), ("FixedFont", "Monospace"),
                    ("CursiveFont", "Comic Sans MS"), ("FantasyFont", "Impact"))

    def _chrome_fonts(self, profile):
        s = profile.settings()
        for which, family in self.CHROME_FONTS:
            kind = getattr(QWebEngineSettings.FontFamily, which)
            if s.fontFamily(kind) != family:
                s.setFontFamily(kind, family)

    def apply_settings(self, profile=None):
        """(Re)apply everything that depends on the configuration."""
        cfg = self.config
        for p in ([profile] if profile else list(self.profiles)):
            from .config import engine_language
            p.setHttpAcceptLanguage(engine_language(cfg))
            self._chrome_fonts(p)
            p.settings().setAttribute(
                QWebEngineSettings.WebAttribute.WebRTCPublicInterfacesOnly,
                bool(cfg["webrtc_hide_ip"]))
            self._identity(p)
            # site settings may have changed: scriptlets follow them again
            self._drop_site_scripts(p)
            self._video_scripts(p)
            scripts = p.scripts()
            for old in (scripts.find(FP_SCRIPT) + scripts.find("ike-consent")
                        + scripts.find("ike-pw") + scripts.find(MEDIA_SCRIPT)
                        + scripts.find("ike-autoscroll")):
                scripts.remove(old)
            from . import ikeextensions
            if (cfg.get("di_media", True) and ikeextensions.on(cfg, "plasma")
                    and not p.isOffTheRecord()):
                # "next" / "previous" of the desktop's media controls (plasma.py);
                # inserted before ike-fp: both keep replaced functions native-looking
                m = QWebEngineScript()
                m.setName(MEDIA_SCRIPT)
                sites = [str(h).lower().strip(".") for h in cfg.get("media_sites") or [] if h]
                m.setSourceCode(limited(self._media_src.replace("__IKE_MEDIA_TOKEN__", self.media_token(p))
                                        .replace("__IKE_MEDIA_SITES__", json.dumps(sites))))
                m.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
                m.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
                m.setRunsOnSubFrames(True)
                scripts.insert(m)
            if ikeextensions.on(cfg, "autoscroll"):
                # automatic scrolling (1.1.20): I.K.E.'s own world, unseen by the page
                a = QWebEngineScript()
                a.setName("ike-autoscroll")
                a.setSourceCode(ikeextensions.AUTOSCROLL_JS)
                a.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentReady)
                a.setWorldId(QWebEngineScript.ScriptWorldId.ApplicationWorld)
                a.setRunsOnSubFrames(True)
                scripts.insert(a)
            if getattr(self, "pw_source", "") and ikeextensions.on(cfg, "passwords"):
                pw = QWebEngineScript()
                pw.setName("ike-pw")
                pw.setSourceCode(self.pw_source)
                pw.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentReady)
                pw.setWorldId(QWebEngineScript.ScriptWorldId.ApplicationWorld)
                pw.setRunsOnSubFrames(False)
                scripts.insert(pw)
            if self.user_scripts is not None:
                self.user_scripts.apply(p)
            sites = dict(cfg["site_levels"])
            if cfg["login_compat"] and rank(cfg["shield_level"]) > 1:
                for h in LOGIN_HOSTS:
                    sites.setdefault(h, "compatibility")
            for h in SENSITIVE_HOSTS:
                # as config.sensitive_hands_off: nothing changed in the page
                # (1.1.14; "compatibility" from 1.1.12 still added the GPC
                # signal and the Firefox identity of embedded sign-in frames)
                if cfg.sensitive_hands_off(h):
                    sites.setdefault(h, "off")
            ident = osinfo.identity()
            fp_cfg = {"level": cfg["shield_level"], "sites": sites,
                      "key": self.profile_keys[id(p)],
                      "gpc": bool(cfg["send_gpc"]),
                      "nofp": [h for h, o in cfg["site_opts"].items() if o.get("fp") is False],
                      "payframes": list(PAYMENT_SITES),
                      "ffua": FIREFOX_UA if cfg["login_compat"] else "",
                      "os": ident["os"], "platform": ident["platform"],
                      "platformVersion": ident["platform_version"],
                      "ffAppVersion": ident["firefox_app_version"],
                      "ffOscpu": ident["firefox_oscpu"],
                      # the masked names a page can find here (fontcheck.py); None: all of them
                      "fonts": fontcheck.findable(),
                      # the Public Suffix List's rules, for the site of the noise (L-2)
                      "psl": psl_codes()}
            s = QWebEngineScript()
            s.setName(FP_SCRIPT)
            s.setSourceCode(limited(self._fp_src.replace("__IKE_CFG__", json.dumps(fp_cfg))))
            s.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
            s.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
            s.setRunsOnSubFrames(True)
            scripts.insert(s)
            if cfg["comp_consent"]:
                off = [h for h, lv in cfg["site_levels"].items() if lv == "off"]
                off += [h for h, o in cfg["site_opts"].items() if o.get("consent") is False]
                off += [h for h in SENSITIVE_HOSTS if cfg.sensitive_hands_off(h)]
                if cfg["shield_level"] == "off":
                    continue
                c = QWebEngineScript()
                c.setName("ike-consent")
                c.setSourceCode(limited(self._consent_src.replace(
                    "__IKE_CFG__", json.dumps({"off": off}))))
                c.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentReady)
                c.setWorldId(QWebEngineScript.ScriptWorldId.ApplicationWorld)
                c.setRunsOnSubFrames(True)
                scripts.insert(c)

    # --- page scripts ------------------------------------------------
    # Scripts that must be in a page from its first instant are kept in the
    # profile, each limited to its own hosts. A script added to a single page
    # while a navigation starts is delivered to the document being left, not
    # to the one being loaded, whenever the engine changes process (that is,
    # whenever the site changes): the new page would run without it.
    SITE_SCRIPTS_MAX = 24

    @staticmethod
    def _script(name, source, main_world, subframes=True, include=()):
        """A profile script that runs from the document's first instant; never
        in an error page, and only at the addresses of `include` when given."""
        s = QWebEngineScript()
        s.setName(name)
        s.setSourceCode(limited(source, include))
        s.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        s.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld if main_world
                     else QWebEngineScript.ScriptWorldId.ApplicationWorld)
        s.setRunsOnSubFrames(bool(subframes))
        return s

    def _ads_on(self, host):
        cfg = self.config
        return bool(cfg["comp_adblock"]) and cfg.level_for(host) != "off" \
            and cfg.site_opt(host, "ads") is not False

    def full_blocking_sites(self):
        """Sites where even their own requests go through the filter lists at
        every level: the video sites, whose ads come from the site itself."""
        bases = tuple(self.config["video_ad_skip_hosts"] or ())
        if getattr(self, "_full_sites_key", None) != bases:
            self._full_sites_key = bases
            self._full_sites = frozenset(site_of(b.lower()) for b in bases)
        return self._full_sites

    def video_hosts(self):
        """Host names of the video sites where ad blocking is active."""
        out = []
        for base in self.config["video_ad_skip_hosts"]:
            for h in (base, "www." + base, "m." + base, "music." + base):
                if h not in out and self._ads_on(h):
                    out.append(h)
        return out

    def _video_scripts(self, profile):
        """(Re)install the always-present scripts of the video sites."""
        import json
        scripts = profile.scripts()
        for name in ("ike-videoads", "ike-video-relay", "ike-video-main", "ike-video-iso"):
            for old in scripts.find(name):
                scripts.remove(old)
        hosts = self.video_hosts()
        if not hosts:
            return
        code = self.blocker.scriptlets.host_scripts(hosts)
        # 1.1.23 (the owner's OK): compiled only on the video sites' own hosts
        # and in their empty frames, which take their parent's host
        on_hosts = [g for h in hosts for g in host_globs(h)] + list(EMPTY_FRAMES)
        if code["MAIN"]:
            scripts.insert(self._script("ike-video-main", code["MAIN"], True, include=on_hosts))
        if code["ISOLATED"]:
            scripts.insert(self._script("ike-video-iso", code["ISOLATED"], False, include=on_hosts))
        if self.config["video_ad_skip"]:
            bases = [b for b in self.config["video_ad_skip_hosts"] if self._ads_on("www." + b)]
            # the player's fallback: the sites and their subdomains (it does
            # nothing in an empty frame, which has no host of its own); the
            # relay below runs in the top page of any site that embeds a
            # player, so it is limited to no host
            scripts.insert(self._script(
                "ike-videoads", self._videoads_src.replace("__IKE_VA__", json.dumps({"hosts": bases})),
                False, include=[g for b in bases for g in host_globs(b, subdomains=True)]))
            scripts.insert(self._script(
                "ike-video-relay", self._videorelay_src.replace("__IKE_VIDEO_HOSTS__", json.dumps(bases)),
                False, False))

    def _drop_site_scripts(self, profile):
        scripts = profile.scripts()
        for host in self._site_lru.pop(id(profile), []):
            for name in ("ike-sl-main:" + host, "ike-sl-iso:" + host):
                for old in scripts.find(name):
                    scripts.remove(old)

    def _rules_changed(self):
        """The filter lists were rebuilt: renew every installed script."""
        for p in list(self.profiles):
            self._drop_site_scripts(p)
            self._video_scripts(p)

    def site_scripts(self, profile, host):
        """Make sure the list scriptlets of this host are installed (page about to load)."""
        if (not host or not self._ads_on(host) or host in self.video_hosts()
                or self.config.sensitive_hands_off(host)):
            return
        lru = self._site_lru.setdefault(id(profile), [])
        if host in lru:
            lru.remove(host)
            lru.append(host)
            return
        code = self.blocker.scriptlets.scripts_for(host)
        if not (code["MAIN"] or code["ISOLATED"]):
            return
        scripts = profile.scripts()
        # only in this host's documents and its empty frames (1.1.23): the
        # other sites' scriptlets were compiled in every page and frame
        on_host = host_globs(host) + list(EMPTY_FRAMES)
        if code["MAIN"]:
            scripts.insert(self._script("ike-sl-main:" + host, code["MAIN"], True, include=on_host))
        if code["ISOLATED"]:
            scripts.insert(self._script("ike-sl-iso:" + host, code["ISOLATED"], False, include=on_host))
        lru.append(host)
        while len(lru) > self.SITE_SCRIPTS_MAX:
            gone = lru.pop(0)
            for name in ("ike-sl-main:" + gone, "ike-sl-iso:" + gone):
                for old in scripts.find(name):
                    scripts.remove(old)

    def apply_dns(self):
        doh = self.config["doh"]
        try:
            from PyQt6.QtWebEngineCore import QWebEngineGlobalSettings as G

            from . import doh as own
            from .config import DOH_PROVIDERS
            mode = G.DnsMode()
            template = None
            if doh and doh != "off":
                mode.secureMode = G.SecureDnsMode.SecureOnly
                template = mode.serverTemplates = DOH_PROVIDERS.get(doh, doh)
            else:
                mode.secureMode = G.SecureDnsMode.SystemOnly
            ok = G.setDnsMode(mode)
            # I.K.E.'s own requests ask the same provider (review of 1.1.19, M3)
            own.configure(template if ok else None)
            return ok
        except Exception:
            from . import doh as own
            own.configure(None)
            return False

    # --- per page ----------------------------------------------------
    def _track_cookies(self, profile):
        """Keep a list of the profile's cookies, to be able to delete one site's."""
        jar = {}
        if not hasattr(self, "cookie_jars"):
            self.cookie_jars = {}
        self.cookie_jars[profile] = jar
        store = profile.cookieStore()

        def key(c):
            return (c.domain(), c.path(), bytes(c.name()))
        from PyQt6.QtNetwork import QNetworkCookie
        # a copy: the object handed to the signal only lives during the call
        store.cookieAdded.connect(lambda c: jar.__setitem__(key(c), QNetworkCookie(c)))
        store.cookieRemoved.connect(lambda c: jar.pop(key(c), None))

    def site_cookies(self, profile, site):
        """Cookies of a registrable domain (and its subdomains) in a profile."""
        out = []
        for c in list(getattr(self, "cookie_jars", {}).get(profile, {}).values()):
            domain = c.domain().lstrip(".").lower()
            if domain == site or domain.endswith("." + site):
                out.append(c)
        return out

    def dark_for(self, host):
        """Whether this host should use the selected dark renderer."""
        cfg = self.config
        if not cfg.get("comp_dark", True):        # the extension is off (1.1.20)
            return False
        on = cfg["dark_mode"] == "on"
        listed = cfg["dark_exclude"] if on else cfg["dark_sites"]
        h = (host or "").lower().strip(".")
        while h:
            if h in listed:
                return not on
            if "." not in h:
                break
            h = h.split(".", 1)[1]
        return on

    def autoplay_blocked(self, host):
        """May video and audio of this site start by themselves? (False = they may)"""
        opt = self.config.site_opt(host, "autoplay")
        if opt is not None:
            return not opt
        return bool(self.config["autoplay_block"])

    def dark_chosen(self, host):
        """Did the user turn this site dark himself (dark mode off, the site on
        its own list)? Then it is made dark whatever Dark Reader's lists say."""
        cfg = self.config
        if cfg["dark_mode"] == "on" or not cfg.get("comp_dark", True):
            return False
        h = (host or "").lower().strip(".")
        while h:
            if h in cfg["dark_sites"]:
                return True
            if "." not in h:
                break
            h = h.split(".", 1)[1]
        return False

    def scripts_allowed(self, host):
        h = (host or "").lower()
        blocked = self.config["site_noscript"]
        while h:
            if h in blocked:
                return False
            if "." not in h:
                break
            h = h.split(".", 1)[1]
        return True
