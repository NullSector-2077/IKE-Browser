"""User scripts (the Greasemonkey / Tampermonkey / Violentmonkey kind).

Browser extensions cannot be installed in I.K.E.'s engine, so the scripts are
run by I.K.E. itself. A script is a ".user.js" file whose header says where it
applies; this module stores the installed ones, keeps them updated, and builds
for each a copy wrapped in resources/userscript.js, which supplies the usual
GM_* functions its "@grant" lines ask for (no "@grant" means none, as in
Violentmonkey and Greasemonkey 4). Requests a script makes to other sites, its
stored values, the clipboard and new tabs go through the page's console
channel to receive(): every message carries the script's own secret token,
and I.K.E. checks it and the script's grants before doing anything.

A script that needs nothing (or only "unsafeWindow") runs in the page itself,
as its authors expect; every other script runs in a separate world where the
page cannot reach its functions. Scripts in the page itself are injected when
the document is created, before any code of the page, keep the functions they
need to reach I.K.E., and then wait for their "@run-at" moment.

GM_xmlhttpRequest follows "@connect": the page's host ("self"), the listed
domains and their subdomains, or "*". Local and private addresses (this
computer, the home network) are reached only when "@connect" names them; the
check is repeated at every redirect and on the addresses a name resolves to.
A name that resolves differently between the check and the request (DNS
rebinding) is not caught.
"""

import base64
import functools
import hashlib
import ipaddress
import json
import os
import re
import secrets
import socket
import time
import urllib.error
import urllib.request
from urllib.parse import urljoin, urlsplit

from PyQt6.QtCore import QObject, QThread, QTimer, QUrl, pyqtSignal
from PyQt6.QtNetwork import QHostInfo, QNetworkReply, QNetworkRequest
from PyQt6.QtWebEngineCore import QWebEngineScript

from . import __version__
from .config import DATA_DIR, RES_DIR
from .i18n import T

DIR = DATA_DIR / "userscripts"
INDEX = DIR / "index.json"
WORLD = 2                                # QWebEngineScript.ScriptWorldId.UserWorld
MAX_SCRIPT = 5 * 1024 * 1024
MAX_REPLY = 20 * 1024 * 1024
UPDATE_INTERVAL = 24 * 3600
_BLOCK = re.compile(r"//\s*==UserScript==(.*?)//\s*==/UserScript==", re.S)
_LINE = re.compile(r"^\s*//\s*@([\w:-]+)(?:[ \t]+(.*?))?\s*$", re.M)
_MANY = ("match", "include", "exclude", "exclude-match", "grant", "require", "resource", "connect")
PREFIX = "\u0001ike-gm:"                 # console messages for I.K.E.: PREFIX + token + ":" + JSON
# operations a script sends to I.K.E. and the GM function that must be granted
OPS = {"set": "setvalue", "del": "deletevalue", "clip": "setclipboard", "tab": "openintab",
       "notify": "notification", "download": "download", "xhr": "xmlhttprequest"}
# this computer and private networks: reached only when "@connect" names them
_LOCAL_NETS = [ipaddress.ip_network(n) for n in (
    "0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16",
    "172.16.0.0/12", "192.168.0.0/16", "::/128", "::1/128", "fc00::/7", "fe80::/10")]


def granted(grants):
    """GM functions a script may use, from its "@grant" lines: lower-case names
    without "GM_" / "GM." ("GM_xmlhttpRequest" and "GM.xmlHttpRequest" are the
    same function). GM_info is always available."""
    return sorted({g[3:].lower() for g in grants or () if g[:3] in ("GM_", "GM.") and len(g) > 3})


def is_local_address(text):
    """True for an address of this computer or of a private network."""
    try:
        ip = ipaddress.ip_address(str(text).strip("[]").split("%")[0])
    except ValueError:
        return False
    if ip.version == 6:
        if ip.ipv4_mapped:
            ip = ip.ipv4_mapped
        elif int(ip) < 2 ** 32:      # IPv4-compatible (::a.b.c.d), ::1, ::
            ip = ipaddress.IPv4Address(int(ip))
    return any(ip in net for net in _LOCAL_NETS)


# names of the home network by their form alone, no lookup (1.1.18, security
# audit F2): routers and NAS boxes answer to these (fritz.box, router.lan,
# nas.home.arpa) and to single names with no dot ("router", "printer")
_HOME_SUFFIXES = (".localhost", ".local", ".lan", ".home.arpa", ".internal", ".intranet", ".home",
                  ".corp", ".fritz.box")
_HOME_NAMES = frozenset(("localhost", "fritz.box", "home.arpa"))


@functools.lru_cache(maxsize=4096)
def is_local_name(host):
    """True for a host name or address that means this computer or the home network."""
    h = (host or "").lower().rstrip(".").strip("[]")
    if h in _HOME_NAMES or h.endswith(_HOME_SUFFIXES):
        return True
    if is_local_address(h):
        return True
    if re.fullmatch(r"[0-9a-fx.]+", h):  # old IPv4 forms (2130706433, 0x7f.1, 0177.0.0.1)
        try:
            return is_local_address(socket.inet_ntoa(socket.inet_aton(h)))
        except OSError:
            pass                         # a name made of such letters ("cafe"): below
    # a single name with no dot ("router"): never a public site on the web
    return bool(h) and "." not in h and ":" not in h and re.fullmatch(r"[a-z0-9_-]+", h) is not None


def outside_home(host, done, who="", network=None):
    """done(True) if `host` is neither this computer nor the home network.

    A name is looked up first: a public name that points to a local address
    counts as local. Shared by the user scripts' requests and the style sheets
    dark mode fetches for a page, so a web page can never use the browser to
    read what a router, a printer or a program on this computer serves."""
    host = (host or "").lower().rstrip(".").strip("[]")
    if is_local_name(host):
        _debug("%s: local address %s refused" % (who, host))
        done(False)
        return
    try:
        ipaddress.ip_address(host)
        done(True)                       # a public address
        return
    except ValueError:
        pass
    fake = dict(p.split("=", 1) for p in os.environ.get("IKE_TEST_RESOLVE", "").split(",") if "=" in p)
    if host in fake:
        addresses = fake[host].split("|")
        QTimer.singleShot(0, lambda: _resolved(who, host, addresses, done))
        return

    def found(info):
        if info.error() != QHostInfo.HostInfoError.NoError:
            # A name that does not resolve here is refused (1.1.17; it was let
            # through): a hostile name server could fail the check and answer
            # the request itself with a local address. Behind a proxy, which
            # resolves names for the browser, the request goes on as before.
            done(_behind_proxy(host, network))
            return
        _resolved(who, host, [a.toString() for a in info.addresses()], done)
    QHostInfo.lookupHost(host, found)


def _behind_proxy(host, network=None):
    """True when the request will go through a proxy, which resolves the name
    itself: the proxy set on the connection that makes it, or the system's."""
    from PyQt6.QtNetwork import QNetworkProxy, QNetworkProxyFactory, QNetworkProxyQuery
    real = (QNetworkProxy.ProxyType.HttpProxy, QNetworkProxy.ProxyType.Socks5Proxy)
    try:
        if network is not None and network.proxy().type() in real:
            return True
    except Exception:
        pass
    try:
        found = QNetworkProxyFactory.systemProxyForQuery(QNetworkProxyQuery(QUrl("https://%s/" % host)))
    except Exception:
        return False
    return any(p.type() not in (QNetworkProxy.ProxyType.NoProxy, QNetworkProxy.ProxyType.DefaultProxy)
               for p in found)


def _resolved(who, host, addresses, done):
    if any(is_local_address(a) for a in addresses):
        _debug("%s: %s resolves to a local address, refused" % (who, host))
        done(False)
    else:
        done(True)


def connect_rule(connect, page_host, host):
    """(allowed, named) for a request to `host` by a script with these
    "@connect" lines, from a page on `page_host`. "named" means a line names the
    host itself (not just "*"): only then may it be a local address."""
    host = (host or "").lower().rstrip(".").strip("[]")
    page_host = (page_host or "").lower().rstrip(".").strip("[]")
    entries = [c.strip().lower().rstrip(".").strip("[]") for c in connect or () if c.strip()]
    if not entries:
        return True, False
    star = named = False
    for e in entries:
        if e == "*":
            star = True
            continue
        if e == "self":
            e = page_host
        elif e.startswith("*."):
            e = e[2:]
        if e and (host == e or host.endswith("." + e)):
            named = True
    return named or star, named


def parse_meta(text):
    """The header of a user script as a dict (None if there is no valid header)."""
    m = _BLOCK.search(text or "")
    if not m:
        return None
    meta = {k: [] for k in _MANY}
    for key, value in _LINE.findall(m.group(1)):
        value = (value or "").strip()
        if key in _MANY:
            if value:
                meta[key].append(value)
        elif key not in meta:
            meta[key] = value
    if not meta.get("name"):
        return None
    meta["_block"] = m.group(0)
    return meta


def script_id(meta):
    return hashlib.sha1(("%s\n%s" % (meta.get("namespace", ""), meta["name"])).encode()).hexdigest()[:16]


def version_tuple(v):
    return tuple(int(x) for x in re.findall(r"\d+", v or "")[:6]) or (0,)


def _glob(pattern):
    out = ""
    for ch in pattern:
        out += ".*" if ch == "*" else re.escape(ch)
    return out


def match_regex(pattern):
    """A "@match" pattern as a regular expression source (None if unusable)."""
    if pattern == "<all_urls>":
        return r"^https?://"
    m = re.match(r"^(\*|https?|http\*|file|ftp)://([^/]*)(/.*)?$", pattern)
    if not m:
        return include_regex(pattern)
    scheme, host, path = m.group(1), m.group(2), m.group(3) or "/*"
    if scheme in ("file", "ftp"):
        return None
    scheme = "https?" if scheme in ("*", "http*") else scheme
    if host == "*":
        host_re = r"[^/]+"
    elif host.startswith("*."):
        host_re = r"([^/]+\.)?" + _glob(host[2:])
    else:
        host_re = _glob(host)
    return "^%s://%s(:\\d+)?%s$" % (scheme, host_re, _glob(path))


def _compiled(sources):
    """The patterns userscript.js tests (JavaScript, case-insensitive) as
    Python regular expressions; None when one cannot be read here."""
    try:
        return [re.compile(r, re.I) for r in sources]
    except re.error:
        return None


def include_regex(pattern):
    """An "@include" / "@exclude" pattern: a glob, or a /regular expression/."""
    if len(pattern) > 2 and pattern.startswith("/") and pattern.endswith("/"):
        return pattern[1:-1]
    return "^" + _glob(pattern).replace(re.escape(".tld") + "/", r"\.[a-z.]{2,}/") + "$"


def at_home(host, unknown=True):
    """True if `host` is this computer or the home network, by its name, its
    address or what the name resolves to. A name that cannot be resolved here
    counts as at home (`unknown`): the check must not be skipped by a failing
    lookup. unknown=False asks the opposite question, "is it surely at home?"."""
    h = (host or "").lower().rstrip(".").strip("[]")
    if not h or is_local_name(h):
        return True
    try:
        ipaddress.ip_address(h)
        return False                     # a public address
    except ValueError:
        pass
    fake = dict(p.split("=", 1) for p in os.environ.get("IKE_TEST_RESOLVE", "").split(",") if "=" in p)
    if h in fake:
        return any(is_local_address(a) for a in fake[h].split("|"))
    try:
        infos = socket.getaddrinfo(h, None)
    except (OSError, UnicodeError):
        return unknown
    return any(is_local_address(i[4][0]) for i in infos)


class _Redirects(urllib.request.HTTPRedirectHandler):
    """Every redirect of a script's download is checked like the first address."""

    def __init__(self, home_ok):
        super().__init__()
        self.home_ok = home_ok

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parts = urlsplit(newurl)
        if parts.scheme not in ("http", "https") or (not self.home_ok and at_home(parts.hostname)):
            raise urllib.error.URLError(T("a redirect to a refused address"))
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _pin(host, home_ok):
    """The address to connect to for `host`, looked up once and checked: the
    connection goes to that address, so a name server cannot answer the check
    with a public address and the connection with a local one (DNS rebinding)."""
    import http.client
    h = (host or "").lower().rstrip(".").strip("[]")
    try:
        addresses = [str(ipaddress.ip_address(h))]
    except ValueError:
        fake = dict(p.split("=", 1) for p in os.environ.get("IKE_TEST_RESOLVE", "").split(",") if "=" in p)
        if h in fake:
            addresses = fake[h].split("|")
        else:
            try:
                addresses = [i[4][0] for i in socket.getaddrinfo(h, None, proto=socket.IPPROTO_TCP)]
            except (OSError, UnicodeError) as exc:
                raise http.client.HTTPException("%s: %s" % (h, exc)) from None
    if not addresses or (not home_ok and (is_local_name(h) or any(is_local_address(a) for a in addresses))):
        raise urllib.error.URLError(T("an address of this computer or of the home network: %s") % h)
    return addresses[0]


def _pinned_handlers(home_ok):
    import http.client

    class Plain(http.client.HTTPConnection):
        def connect(self):
            self.sock = socket.create_connection((_pin(self.host, home_ok), self.port),
                                                 self.timeout, self.source_address)

    class Secure(http.client.HTTPSConnection):
        def connect(self):
            sock = socket.create_connection((_pin(self.host, home_ok), self.port),
                                            self.timeout, self.source_address)
            self.sock = self._context.wrap_socket(sock, server_hostname=self.host)

    class PlainHandler(urllib.request.HTTPHandler):
        def http_open(self, req):
            return self.do_open(Plain, req)

    class SecureHandler(urllib.request.HTTPSHandler):
        def https_open(self, req):
            return self.do_open(Secure, req, context=self._context)
    return PlainHandler(), SecureHandler()


def _get(url, limit, home_ok=True):
    """Download `url` (at most `limit` bytes). home_ok=False: never from this
    computer or the home network, also through a redirect (1.1.17): the
    libraries and resources a script names must not let it read a router or
    a local service, which its @connect rule would refuse."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError(T("only http and https addresses can be used"))
    if not home_ok and at_home(parts.hostname):
        raise ValueError(T("an address of this computer or of the home network: %s") % parts.hostname)
    handlers = [_Redirects(home_ok)]
    proxies = urllib.request.getproxies()
    if not home_ok and not (proxies.get(parts.scheme) and not urllib.request.proxy_bypass(parts.hostname)):
        # without a proxy (which resolves names itself), every connection goes
        # to the address that was checked, also after a redirect
        handlers += list(_pinned_handlers(home_ok))
    opener = urllib.request.build_opener(*handlers)
    req = urllib.request.Request(url, headers={"User-Agent": "I.K.E. user scripts"})
    with opener.open(req, timeout=40) as r:
        data = r.read(limit + 1)
        ctype = r.headers.get_content_type() if r.headers else ""
    if len(data) > limit:
        raise ValueError(T("the file is too large"))
    return data, ctype


def dependency_urls(meta, source_url=""):
    """The addresses of a script's @require and @resource lines."""
    refs = list(meta["require"][:30]) + [r.split(None, 1)[1] for r in meta["resource"][:20]
                                          if len(r.split(None, 1)) == 2]
    return [urljoin(source_url, ref) if source_url else ref for ref in refs]


def gather(text, source_url=""):
    """Everything a script needs, fetched: {"meta", "text", "requires", "resources"}.

    Its libraries come from the home network only when the script itself does
    (the user installed it from a computer at home)."""
    meta = parse_meta(text)
    if meta is None:
        raise ValueError(T("this is not a user script (its header is missing)"))
    home_ok = bool(source_url) and at_home(urlsplit(source_url).hostname, unknown=False)
    requires, resources = [], {}
    for ref in meta["require"][:30]:
        url = urljoin(source_url, ref) if source_url else ref
        data, _ctype = _get(url, MAX_SCRIPT, home_ok)
        requires.append([url, data.decode("utf-8", "replace")])
    for ref in meta["resource"][:20]:
        bits = ref.split(None, 1)
        if len(bits) != 2:
            continue
        url = urljoin(source_url, bits[1]) if source_url else bits[1]
        data, ctype = _get(url, 2 * 1024 * 1024, home_ok)
        resources[bits[0]] = {"type": ctype, "b64": base64.b64encode(data).decode("ascii"),
                              "text": data.decode("utf-8", "replace"), "url": url}
    return {"meta": meta, "text": text, "requires": requires, "resources": resources,
            "source": source_url}


def update_needs_consent(old, got):
    """True when an update found by the daily check must not be installed
    silently: it runs on more sites, uses more GM_ functions, reaches more
    hosts or more frames than the installed version, or loads code (@require,
    @resource) over plain http. Anything else updates by itself, as before."""
    meta = got["meta"]

    def low(items):
        return {str(i).strip().lower() for i in items or () if str(i).strip()}
    if set(granted(meta["grant"])) - set(granted(old.get("grant", []))):
        return True
    if (low(meta["match"]) | low(meta["include"])) - (low(old.get("match")) | low(old.get("include"))):
        return True
    if low(old.get("exclude")) - (low(meta["exclude"]) | low(meta["exclude-match"])):
        return True
    before, after = low(old.get("connect")), low(meta["connect"])
    if before and (not after or after - before):
        return True                      # no @connect at all means any host
    if old.get("noframes") and "noframes" not in meta:
        return True
    source = got.get("source") or ""
    deps = dependency_urls(meta, source)
    if any(not u.startswith("https://") for u in deps):
        return True
    # code from a host the installed version did not load from (1.1.17)
    before_hosts = {urlsplit(u).hostname for u, _t in old.get("requires") or []}
    before_hosts |= {urlsplit(r.get("url", "")).hostname for r in (old.get("resources") or {}).values()
                     if isinstance(r, dict) and r.get("url")}
    before_hosts |= {urlsplit(old.get("update") or old.get("source") or "").hostname}
    return any(urlsplit(u).hostname not in before_hosts for u in deps)


class Fetcher(QThread):
    """Downloads a script (or takes its text) with what it requires."""
    done = pyqtSignal(object, str)       # gathered dict or None, error text

    def __init__(self, parent, url="", text=None, must_be_newer_than=None):
        super().__init__(parent)
        self.url, self.text, self.newer = url, text, must_be_newer_than

    def run(self):
        try:
            text = self.text
            if text is None:
                data, _ctype = _get(self.url, MAX_SCRIPT)
                text = data.decode("utf-8", "replace")
            if self.newer is not None:
                meta = parse_meta(text)
                if meta is None or version_tuple(meta.get("version")) <= version_tuple(self.newer):
                    self.done.emit(None, "")
                    return
            self.done.emit(gather(text, self.url), "")
        except Exception as exc:
            self.done.emit(None, str(exc) or exc.__class__.__name__)


class UserScripts(QObject):
    changed = pyqtSignal()

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        # their own manager: GM_xmlhttpRequest keeps the cookies its sites set,
        # as user scripts expect; the browser's own requests keep none (app.py)
        from PyQt6.QtNetwork import QNetworkAccessManager
        self.network = QNetworkAccessManager(self)
        self.secret = secrets.token_hex(16)   # names of the answer callbacks
        self.tokens, self._by_token = {}, {}  # one secret token per script, this session only
        self._patterns = {}                   # sid -> (include, exclude) compiled, for the bridge
        self.scripts = {}
        self._threads = set()
        self._template = None
        self._dirty = set()
        self._flush = QTimer(self)
        self._flush.setSingleShot(True)
        self._flush.setInterval(1500)
        self._flush.timeout.connect(self._write_values)
        self._load()

    # --- storage -----------------------------------------------------
    def _load(self):
        try:
            data = json.loads(INDEX.read_text("utf-8"))
            self.scripts = {k: v for k, v in data.items() if isinstance(v, dict) and v.get("name")}
        except (OSError, ValueError):
            self.scripts = {}

    def _save(self):
        try:
            DIR.mkdir(parents=True, exist_ok=True)
            tmp = INDEX.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.scripts, ensure_ascii=False, indent=1), "utf-8")
            tmp.replace(INDEX)
        except OSError:
            pass

    def _code(self, sid):
        try:
            return (DIR / (sid + ".user.js")).read_text("utf-8")
        except OSError:
            return ""

    def listing(self):
        return sorted(self.scripts.items(), key=lambda kv: kv[1]["name"].lower())

    def enabled(self):
        return bool(self.app.config["userscripts_enabled"])

    # --- install / remove --------------------------------------------
    def store(self, got):
        """Save a gathered script (new or replacing the same one). Returns its id."""
        meta = got["meta"]
        sid = script_id(meta)
        old = self.scripts.get(sid, {})
        DIR.mkdir(parents=True, exist_ok=True)
        (DIR / (sid + ".user.js")).write_text(got["text"], "utf-8")
        source = got.get("source") or old.get("source", "")
        self.scripts[sid] = {
            "name": meta["name"][:200], "namespace": meta.get("namespace", ""),
            "version": meta.get("version", ""), "description": meta.get("description", "")[:500],
            "enabled": old.get("enabled", True),
            "match": meta["match"], "include": meta["include"],
            "exclude": meta["exclude"] + meta["exclude-match"],
            "grant": meta["grant"], "connect": meta["connect"],
            "run_at": meta.get("run-at", "document-idle"),
            "noframes": "noframes" in meta,
            "source": source,
            "update": meta.get("downloadURL") or meta.get("updateURL") or source,
            "requires": got["requires"], "resources": got["resources"],
            "values": old.get("values", {}), "installed": old.get("installed") or int(time.time()),
            "updated": int(time.time()), "checked": int(time.time()),
        }
        self._save()
        self.apply_all()
        self.changed.emit()
        return sid

    def remove(self, sid):
        if self.scripts.pop(sid, None) is None:
            return
        try:
            (DIR / (sid + ".user.js")).unlink()
        except OSError:
            pass
        self._save()
        self.apply_all()
        self.changed.emit()

    def set_enabled(self, sid, on):
        s = self.scripts.get(sid)
        if s is None or s["enabled"] == bool(on):
            return
        s["enabled"] = bool(on)
        self._save()
        self.apply_all()
        self.changed.emit()

    def describe(self, meta):
        """Lines shown before installing: what the script is and where it runs."""
        where = meta["match"] + meta["include"]
        grants = [g for g in meta["grant"] if g != "none"]
        lines = [meta["name"] + ("  " + meta["version"] if meta.get("version") else "")]
        if meta.get("description"):
            lines.append(meta["description"])
        lines.append("")
        lines.append(T("Runs on: %s") % (", ".join(where[:8]) + (" …" if len(where) > 8 else "")
                                         if where else T("every site")))
        if grants:
            lines.append(T("Asks for: %s") % ", ".join(grants[:12]))
        if meta["connect"]:
            lines.append(T("Connects to: %s") % (", ".join(meta["connect"][:12])
                                                + (" …" if len(meta["connect"]) > 12 else "")))
        if meta["require"]:
            lines.append(T("Loads %d additional libraries") % len(meta["require"]))
        hosts = sorted({urlsplit(u).hostname or "" for u in dependency_urls(meta)} - {""})
        if hosts:
            lines.append(T("Code and files from: %s") % ", ".join(hosts[:8]))
        return "\n".join(lines)

    def fetch(self, callback, url="", text=None, newer=None):
        t = Fetcher(self, url, text, newer)
        self._threads.add(t)

        def done(got, err):
            self._threads.discard(t)
            callback(got, err)
        t.done.connect(done)
        from . import background
        background.start(t)

    def offer(self, parent, url="", text=None):
        """Download a script and ask the user whether to install it."""
        from PyQt6.QtWidgets import QMessageBox

        def ready(got, err):
            if got is None:
                QMessageBox.warning(parent, "I.K.E.", T("The user script could not be installed: %s") % err)
                return
            known = script_id(got["meta"]) in self.scripts
            box = QMessageBox(parent)
            box.setWindowTitle("I.K.E.")
            box.setIcon(QMessageBox.Icon.Question)
            box.setText(T("Update this user script?") if known else T("Install this user script?"))
            box.setInformativeText(self.describe(got["meta"]) + "\n\n" + T(
                "A user script can read and change the pages it runs on. Install only scripts you trust."))
            box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
            box.setDefaultButton(QMessageBox.StandardButton.Cancel)
            if box.exec() == QMessageBox.StandardButton.Yes:
                self.store(got)
                self.app._notify(T("User script installed: %s") % got["meta"]["name"])
        self.fetch(ready, url, text)

    # --- updates -----------------------------------------------------
    def check_updates(self, force=False):
        """Look for newer versions of the installed scripts (once a day unless forced)."""
        now = time.time()
        for sid, s in list(self.scripts.items()):
            url = s.get("update") or ""
            # only over https: on a plain http address anybody on the same
            # network could hand over a "newer version" of their own
            if not url.startswith("https://"):
                continue
            if not force and now - s.get("checked", 0) < UPDATE_INTERVAL:
                continue
            s["checked"] = int(now)

            def ready(got, _err, sid=sid, name=s["name"]):
                if got is None or script_id(got["meta"]) != sid or sid not in self.scripts:
                    return
                if update_needs_consent(self.scripts[sid], got):
                    self._confirm_update(got)
                    return
                self.store(got)
                self.app._notify(T("User script updated: %s") % name)
            self.fetch(ready, url, newer=s.get("version", ""))
        self._save()

    def _confirm_update(self, got):
        """An update that asks for more than the installed version: the user decides."""
        from PyQt6.QtWidgets import QMessageBox
        box = QMessageBox(self.app.active_window())
        box.setWindowTitle("I.K.E.")
        box.setIcon(QMessageBox.Icon.Question)
        box.setText(T("Update this user script?"))
        box.setInformativeText(self.describe(got["meta"]) + "\n\n" + T(
            "This update asks for more than the installed version (more sites, functions or "
            "connections) or loads code without encryption. Install it only if you trust it."))
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(QMessageBox.StandardButton.Cancel)
        if box.exec() == QMessageBox.StandardButton.Yes:
            self.store(got)
            self.app._notify(T("User script updated: %s") % got["meta"]["name"])

    # --- building ----------------------------------------------------
    def _world(self, s):
        grants = [g for g in s.get("grant", []) if g != "none"]
        if not grants or "unsafeWindow" in grants:
            return 0                     # the page itself
        return WORLD

    def _token(self, sid):
        tok = self.tokens.get(sid)
        if tok is None:
            tok = self.tokens[sid] = secrets.token_hex(16)
            self._by_token[tok] = sid
        return tok

    def _callback(self, sid):
        return "__ike_us_" + hashlib.sha1((self.secret + sid).encode()).hexdigest()[:20]

    def _connect(self, sid):
        """The script's "@connect" lines (read from its code for scripts installed by earlier versions)."""
        s = self.scripts[sid]
        if not isinstance(s.get("connect"), list):
            meta = parse_meta(self._code(sid))
            s["connect"] = meta["connect"] if meta else []
        return s["connect"]

    def build(self, sid):
        s = self.scripts[sid]
        if self._template is None:
            self._template = (RES_DIR / "userscript.js").read_text("utf-8")
        inc = [r for r in ([match_regex(p) for p in s.get("match", [])]
                           + [include_regex(p) for p in s.get("include", [])]) if r]
        if not s.get("match") and not s.get("include"):
            inc = [r"^https?://"]
        exc = [r for r in (include_regex(p) for p in s.get("exclude", [])) if r]
        self._patterns[sid] = (_compiled(inc), _compiled(exc))
        code = self._code(sid)
        meta = parse_meta(code)
        allow = granted(s.get("grant", []))
        bridge = any(name in allow for name in OPS.values())
        run_at = s.get("run_at", "")
        defer = ""
        if self._world(s) == 0:          # injected at document creation, started later
            defer = {"document-start": "", "document-end": "end", "document-body": "end"}.get(run_at, "idle")
        cfg = {"id": sid, "token": (PREFIX + self._token(sid) + ":") if bridge else "",
               "cb": self._callback(sid), "allow": allow, "defer": defer,
               "name": s["name"], "namespace": s.get("namespace", ""), "version": s.get("version", ""),
               "description": s.get("description", ""), "matches": s.get("match", []),
               "grant": s.get("grant", []), "runAt": run_at,
               "noframes": bool(s.get("noframes")), "inc": inc, "exc": exc,
               "values": s.get("values", {}) if {"getvalue", "listvalues"} & set(allow) else {},
               "resources": s.get("resources", {}) if {"getresourcetext", "getresourceurl"} & set(allow) else {},
               "ike": __version__, "meta": meta["_block"] if meta else ""}
        parts = [lib for _url, lib in s.get("requires", [])] + [code]
        # the engine reads user-script headers itself; I.K.E. does the matching
        body = "\n;\n".join(parts).replace("==UserScript==", "==UserScript ==")
        cfg_json = json.dumps(cfg).replace("==UserScript==", "\\u003d=UserScript==")
        head, rest = self._template.split("__US_CFG__", 1)
        middle, tail = rest.split("__US_CODE__", 1)
        return head + cfg_json + middle + body + "\n" + tail

    def _point(self, s):
        P = QWebEngineScript.InjectionPoint
        run_at = s.get("run_at", "")
        if run_at == "document-start" or self._world(s) == 0:
            return P.DocumentCreation
        if run_at in ("document-end", "document-body"):
            return P.DocumentReady
        return P.Deferred

    def apply(self, profile):
        """(Re)install the enabled scripts in a profile."""
        scripts = profile.scripts()
        for old in list(scripts.toList()):
            if old.name().startswith("ike-us:"):
                scripts.remove(old)
        if not self.enabled():
            return
        for sid, s in self.scripts.items():
            if not s.get("enabled", True):
                continue
            try:
                source = self.build(sid)
            except Exception:
                continue
            q = QWebEngineScript()
            q.setName("ike-us:" + sid)
            q.setSourceCode(source)
            q.setInjectionPoint(self._point(s))
            q.setWorldId(self._world(s))
            q.setRunsOnSubFrames(not s.get("noframes"))
            scripts.insert(q)

    def apply_all(self):
        for p in list(self.app.shields.profiles):
            try:
                self.apply(p)
            except RuntimeError:
                pass

    # --- the GM bridge -----------------------------------------------
    def receive(self, page, message):
        """A console message starting with PREFIX: find the script by its token."""
        rest = message[len(PREFIX):]
        token, sep, payload = rest.partition(":")
        sid = self._by_token.get(token) if sep else None
        if sid is None:
            _debug("message without a valid token refused")
            return
        self.handle(page, sid, payload)

    def _from_its_page(self, page, sid, claimed):
        """The message really comes from a page the script runs on (1.1.18,
        security audit F6: the token alone was checked, so a page that got it
        could act as the script anywhere). Checked here, in the browser: the
        address the script sends must be that of a frame this page really has
        (the engine's own frame tree, compared by origin, so a history.pushState
        in between does not matter) and must match the script's @match /
        @include and none of its @exclude."""
        url = QUrl(str(claimed or ""))
        if not url.isValid() or not url.scheme() or not isinstance(claimed, str):
            return False

        def origin(u):
            return (u.scheme().lower(), u.host().lower(), u.port())
        want, frames = origin(url), []
        try:
            todo = [page.mainFrame()]
            while todo and len(frames) < 500:
                f = todo.pop()
                frames.append(origin(f.url()))
                todo.extend(f.children())
        except (AttributeError, RuntimeError):
            frames = [origin(page.url())]
        if want not in frames:
            return False
        if sid not in self._patterns:
            try:
                self.build(sid)
            except Exception:
                return False
        inc, exc = self._patterns.get(sid, ([], []))
        if inc is None or exc is None:           # a pattern Python cannot read: the frame check only
            return True
        return any(r.search(claimed) for r in inc) and not any(r.search(claimed) for r in exc)

    def handle(self, page, sid, payload):
        """A message from running script `sid` (see send() in userscript.js)."""
        try:
            msg = json.loads(payload)
            op, d = msg["op"], msg.get("d") or {}
            s = self.scripts[sid]
            if msg["id"] != sid or not isinstance(d, dict):
                raise ValueError
        except (ValueError, KeyError, TypeError):
            _debug("malformed message refused")
            return
        if not s.get("enabled", True) or not self.enabled():
            return
        if not self._from_its_page(page, sid, msg.get("u")):
            _debug("%s: %r from a page the script does not run on refused" % (s["name"], op))
            return
        if OPS.get(op) not in granted(s.get("grant", [])):
            _debug("%s: %r not granted" % (s["name"], op))
            return
        if op == "set":
            if isinstance(d.get("k"), str) and isinstance(d.get("v"), str) and len(d["v"]) < 4_000_000:
                s.setdefault("values", {})[d["k"]] = d["v"]
                self._value_changed(sid)
        elif op == "del":
            if s.get("values", {}).pop(d.get("k"), None) is not None:
                self._value_changed(sid)
        elif op == "clip":
            from PyQt6.QtGui import QGuiApplication
            QGuiApplication.clipboard().setText(str(d.get("text", ""))[:1_000_000])
        elif op in ("tab", "download"):
            url = QUrl(str(d.get("url", "")))
            if url.scheme() in ("http", "https"):
                win = page.window_ref
                if op == "download":
                    page.download(url)
                else:
                    win.add_tab(url, background=bool(d.get("background")), after=win.view_of(page))
        elif op == "notify":
            self.app._desktop_notify("%s — %s" % (str(d.get("title", s["name"]))[:120],
                                                  str(d.get("text", ""))[:400]))
        elif op == "xhr":
            self._xhr(page, sid, d)

    def _value_changed(self, sid):
        self._dirty.add(sid)
        self._flush.start()

    def _write_values(self):
        """Stored values changed: save them and give new pages the new values."""
        self._dirty.clear()
        self._save()
        self.apply_all()

    def _answer(self, page, sid, rid, data):
        s = self.scripts.get(sid)
        if s is None:
            return
        cb = self._callback(sid)
        js = "window[%s] && window[%s](%s, %s);" % (json.dumps(cb), json.dumps(cb),
                                                 json.dumps(rid), json.dumps(data))
        try:
            page.runJavaScript(js, self._world(s))
        except RuntimeError:
            pass                          # the page is gone

    def _xhr(self, page, sid, d):
        rid = str(d.get("rid", ""))
        url = QUrl(str(d.get("url", "")))
        method = str(d.get("method", "GET")).upper()
        if (url.scheme() not in ("http", "https") or not rid
                or method not in ("GET", "POST", "PUT", "DELETE", "HEAD", "PATCH", "OPTIONS")):
            self._answer(page, sid, rid, {"error": "refused"})
            return
        page_host = page.url().host()

        def checked(ok):
            if ok:
                self._send(page, sid, d, rid, url, method, page_host)
            else:
                self._answer(page, sid, rid, {"error": "refused"})
        self.check_target(sid, page_host, url, checked)

    def check_target(self, sid, page_host, url, done):
        """done(True) if the script may reach `url` (see the module notes)."""
        name = self.scripts.get(sid, {}).get("name", sid)
        host = url.host().lower().rstrip(".")
        if url.scheme() not in ("http", "https") or not host:
            done(False)
            return
        allowed, named = connect_rule(self._connect(sid), page_host, host)
        if not allowed:
            _debug("%s: %s is not in @connect" % (name, host))
            done(False)
            return
        if named:
            done(True)
            return
        outside_home(host, done, name + " (not named by @connect)", self.network)

    def _send(self, page, sid, d, rid, url, method, page_host):
        req = QNetworkRequest(url)
        req.setRawHeader(b"User-Agent", self.app.shields.user_agent().encode())
        headers = d.get("headers") if isinstance(d.get("headers"), dict) else {}
        for k, v in list(headers.items())[:60]:
            name = str(k).strip()
            if re.fullmatch(r"[A-Za-z0-9!#$%&'*+.^_`|~-]{1,80}", name) and "\n" not in str(v) \
                    and "\r" not in str(v) and name.lower() not in ("host", "content-length"):
                req.setRawHeader(name.encode(), str(v).encode("utf-8", "replace"))
        # every redirect is checked like the first address (and never from https to http)
        req.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,
                         QNetworkRequest.RedirectPolicy.UserVerifiedRedirectPolicy)
        timeout = d.get("timeout") or 0
        req.setTransferTimeout(int(timeout) if isinstance(timeout, (int, float)) and 0 < timeout < 600000
                               else 60000)
        body = d.get("data")
        data = body.encode("utf-8") if isinstance(body, str) else b""
        if data and not req.hasRawHeader(b"Content-Type"):
            req.setRawHeader(b"Content-Type", b"application/x-www-form-urlencoded; charset=UTF-8")
        reply = self.network.sendCustomRequest(req, method.encode(), data)
        binary = bool(d.get("binary"))
        refused = []

        def redirected(target):
            target = reply.url().resolved(target) if target.isRelative() else target
            if reply.url().scheme() == "https" and target.scheme() != "https":
                refused.append(1)
                reply.abort()
                return

            def checked(ok):
                if refused or not reply.isRunning():
                    return
                if ok:
                    reply.redirectAllowed.emit()
                else:
                    refused.append(1)
                    reply.abort()
            self.check_target(sid, page_host, target, checked)
        reply.redirected.connect(redirected)

        def done():
            err = reply.error()
            status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
            raw = bytes(reply.read(MAX_REPLY + 1)) if reply.isOpen() else b""
            if refused:
                out = {"error": "refused"}
            elif status is None or len(raw) > MAX_REPLY:
                out = {"error": reply.errorString() or "failed",
                       "timeout": err in (QNetworkReply.NetworkError.TimeoutError,
                                          QNetworkReply.NetworkError.OperationCanceledError)}
            else:
                lines = "".join("%s: %s\r\n" % (bytes(k).decode("latin-1"), bytes(v).decode("latin-1"))
                                for k, v in reply.rawHeaderPairs())
                ctype = str(reply.header(QNetworkRequest.KnownHeaders.ContentTypeHeader) or "")
                out = {"status": int(status), "url": reply.url().toString(), "headers": lines,
                       "statusText": str(reply.attribute(
                           QNetworkRequest.Attribute.HttpReasonPhraseAttribute) or ""),
                       "type": ctype}
                if binary:
                    out["b64"] = base64.b64encode(raw).decode("ascii")
                else:
                    m = re.search(r"charset=([\w-]+)", ctype, re.I)
                    try:
                        out["text"] = raw.decode(m.group(1) if m else "utf-8", "replace")
                    except LookupError:
                        out["text"] = raw.decode("utf-8", "replace")
            reply.deleteLater()
            self._answer(page, sid, rid, out)
        reply.finished.connect(done)


def _debug(text):
    if os.environ.get("IKE_DEBUG"):
        print("[user scripts] " + text)
