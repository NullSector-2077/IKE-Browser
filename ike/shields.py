"""Protection layer: request interception, cookies, injected scripts, profile."""

import json
import os
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

from . import osinfo
from .config import CACHE_DIR, DATA_DIR, FIREFOX_UA, LEVEL_NAMES, LOGIN_HOSTS, RES_DIR, rank

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
           ".neocities.org")


def site_of(host):
    """Registrable domain of a host: "www.bbc.co.uk" -> "bbc.co.uk"."""
    host = host or ""
    parts = host.split(".")
    if len(parts) <= 2 or host.replace(".", "").isdigit() or ":" in host:
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

    def interceptRequest(self, info):
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
        first = url if main else info.firstPartyUrl()
        if not main and first.isEmpty():
            try:
                first = info.initiator()
            except AttributeError:
                pass
        if first.isEmpty():
            first = url
        first_host = first.host().lower()
        if not self.quiet:
            site = site_of(first_host)
            s.requests[site] = s.requests.get(site, 0) + 1      # per-site resources
        lv = rank(cfg.level_for(first_host))
        if lv == 0:
            return
        host = url.host().lower()
        get = bytes(info.requestMethod()) == b"GET"
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
            if (scheme == "http" and cfg["https_only"] and cfg.site_opt(host, "https") is not False
                    and host not in _LOCAL
                    and host not in s.http_allowed and "." in host
                    and not host.replace(".", "").isdigit()):
                https = QUrl(url)
                https.setScheme("https")
                s.upgraded.add(host)
                self._count(host, "https")
                s.redirected.add(https.toString())
                info.redirect(https)
                return
            if cfg["strip_tracking_params"] and cfg.site_opt(host, "params") is not False:
                clean = strip_tracking(url.toString())
                if clean:
                    self._count(host, "params")
                    s.redirected.add(QUrl(clean).toString())
                    info.redirect(QUrl(clean))
                    return

        # Main-frame GET requests must also be evaluated by the filter engine.
        # Previously the `elif` paired with the main-frame URL rewriting branch
        # skipped network filters for every normal top-level navigation.
        if ((cfg["comp_adblock"] or cfg["comp_consent"])
                and cfg.site_opt(first_host, "ads") is not False):
            try:
                method = bytes(info.requestMethod()).decode("ascii", "ignore").upper() or "GET"
            except Exception:
                method = "GET"
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
        if lv >= 4 and cfg.site_opt(first_host, "fp") is not False:
            info.setHttpHeader(b"Accept-Language", b"en-US,en;q=0.9")
        if (lv >= 2 and cfg["trim_referrer"] and not main
                and site_of(host) != site_of(first_host)
                and cfg.site_opt(first_host, "params") is not False):
            origin = "%s://%s/" % (first.scheme(), first.host())
            if first.port() > 0:
                origin = "%s://%s:%d/" % (first.scheme(), first.host(), first.port())
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
        if path in ("tile", "theme"):
            # answers given on the new tab page itself (a tile hidden or added, the
            # suggestion of the Cyber theme); the page is shown again afterwards
            from PyQt6.QtCore import QUrlQuery
            items = QUrlQuery(url).queryItems(QUrl.ComponentFormattingOption.FullyDecoded)
            self.s.newtab_answer(path, {k: v.replace("+", " ") if path == "theme" else v for k, v in items})
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
    theme_changed = pyqtSignal()     # the theme was changed from the new tab page

    def __init__(self, config, blocker, parent=None):
        super().__init__(parent)
        self.config = config
        self.blocker = blocker
        # One fingerprint-noise key per WebEngine profile. Private and
        # container profiles must not share the same per-site noise stream.
        self.profile_keys = {}
        self.stats = {}
        self.requests = {}               # site -> requests made for it (see resources)
        self.redirected = set()
        self.upgraded = set()
        self.http_allowed = set()
        self.profiles = []
        self.user_scripts = None         # set by the application
        self.interceptor = Interceptor(self)
        self.scheme_handler = IkeSchemeHandler(self)
        self._fp_src = (RES_DIR / "fingerprint.js").read_text("utf-8")
        self._consent_src = (RES_DIR / "consent.js").read_text("utf-8")
        # the full name is drawn as paths (tools/make-brand.py), in the colour of the page text
        self._newtab_src = (RES_DIR / "newtab.html").read_text("utf-8").replace(
            "{{wordmark}}", (RES_DIR / "wordmark.svg").read_text("utf-8").strip())
        self._videoads_src = (RES_DIR / "videoads.js").read_text("utf-8")
        self._videorelay_src = (RES_DIR / "videorelay.js").read_text("utf-8")
        self._site_lru = {}              # id(profile) -> [host, ...] most recent last
        blocker.rebuilt.connect(self._rules_changed)

    # --- stats -------------------------------------------------------
    KINDS = ("ads", "scripts", "cookies", "https", "params")

    def count(self, host, kind):
        st = self.stats.get(host)
        if st is None:
            st = self.stats[host] = dict.fromkeys(self.KINDS, 0)
        st[kind] += 1
        if kind in ("ads", "scripts"):
            from . import newtab
            newtab.count_blocked(self.config)        # the total and the month's own count
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
        """A choice made on the new tab page: a tile hidden or added, the Cyber theme tried or left."""
        from . import newtab
        app = self.parent()
        storage = getattr(app, "storage", None)
        if what == "tile":
            if query.get("hide"):
                newtab.hide_tile(self.config, query["hide"])
            address = newtab.web_address(query.get("add", ""))
            if address and storage is not None and not storage.is_bookmarked(address):
                from urllib.parse import urlsplit
                host = urlsplit(address).hostname or address
                storage.add_bookmark(address, host[4:] if host.startswith("www.") else host)
                refresh = getattr(app, "refresh_windows", None)
                if refresh is not None:
                    from PyQt6.QtCore import QTimer
                    QTimer.singleShot(0, refresh)             # the bookmarks bar and menu
        elif newtab.answer_hint(self.config, query):
            self.theme_changed.emit()
        self.config.save()

    def search_url(self, query, engine=None):
        e = self.config.engine(engine)
        return e["url"].replace("{q}", quote(query, safe=""))

    def newtab_html(self):
        from .i18n import T
        e = self.config.engine()
        html = self._newtab_src
        from PyQt6.QtGui import QGuiApplication, QPalette
        pal = QGuiApplication.palette()
        R = QPalette.ColorRole
        colors = {"{{bg}}": pal.color(R.Window), "{{fg}}": pal.color(R.WindowText),
                  "{{card}}": pal.color(R.Base), "{{acc}}": pal.color(R.Highlight),
                  "{{line}}": pal.color(R.Mid), "{{mute}}": pal.color(R.PlaceholderText)}
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
        from . import effects, newtab, themes
        photo = newtabbg.style(self.config)
        theme = themes.current(self.config)
        classes = newtab.body_class(self.config, theme) + ("" if photo else " plain")
        html = html.replace("{{background}}", photo)
        app = self.parent()
        for k, v in {
            "{{placeholder}}": _html.escape(T("Search with %s or enter address") % e["name"], quote=True),
            "{{class}}": classes.strip(),
            # the counter counts up with the Cyber theme only: the desktop's look stays as it was
            "{{effects}}": "true" if themes.is_cyber(theme) and effects.on(self.config) else "false",
            "{{tiles}}": newtab.tiles_html(self.config, getattr(app, "storage", None)),
            "{{stats}}": newtab.stats_html(self.config, T("Protection level"),
                                           T(LEVEL_NAMES[self.config["shield_level"]])),
            "{{hint}}": newtab.hint_html(self.config, theme),
        }.items():
            html = html.replace(k, v)
        return html

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

    def _identity(self, profile):
        """Present the current stable Chrome version (header, JavaScript, client hints)."""
        if profile.httpUserAgent() != self.user_agent():
            profile.setHttpUserAgent(self.user_agent())
        try:
            hints = profile.clientHints()
            major = self.chrome_major()
            hints.setFullVersionList({"Chromium": major, "Google Chrome": major,
                                      "Not=A?Brand": "24"})
            hints.setFullVersion(major + ".0.0.0")
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
            profile.setPersistentCookiesPolicy(
                QWebEngineProfile.PersistentCookiesPolicy.AllowPersistentCookies)
        self.profile_keys[id(profile)] = secrets.token_hex(16)
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

    def apply_settings(self, profile=None):
        """(Re)apply everything that depends on the configuration."""
        cfg = self.config
        for p in ([profile] if profile else list(self.profiles)):
            p.setHttpAcceptLanguage(cfg["accept_language"])
            p.settings().setAttribute(
                QWebEngineSettings.WebAttribute.WebRTCPublicInterfacesOnly,
                bool(cfg["webrtc_hide_ip"]))
            self._identity(p)
            # site settings may have changed: scriptlets follow them again
            self._drop_site_scripts(p)
            self._video_scripts(p)
            scripts = p.scripts()
            for old in (scripts.find("ike-fp") + scripts.find("ike-consent")
                        + scripts.find("ike-pw")):
                scripts.remove(old)
            if getattr(self, "pw_source", ""):
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
            ident = osinfo.identity()
            fp_cfg = {"level": cfg["shield_level"], "sites": sites,
                      "key": self.profile_keys[id(p)],
                      "gpc": bool(cfg["send_gpc"]),
                      "nofp": [h for h, o in cfg["site_opts"].items() if o.get("fp") is False],
                      "ffua": FIREFOX_UA if cfg["login_compat"] else "",
                      "os": ident["os"], "platform": ident["platform"],
                      "platformVersion": ident["platform_version"],
                      "ffAppVersion": ident["firefox_app_version"],
                      "ffOscpu": ident["firefox_oscpu"]}
            s = QWebEngineScript()
            s.setName("ike-fp")
            s.setSourceCode(self._fp_src.replace("__IKE_CFG__", json.dumps(fp_cfg)))
            s.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
            s.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
            s.setRunsOnSubFrames(True)
            scripts.insert(s)
            if cfg["comp_consent"]:
                off = [h for h, lv in cfg["site_levels"].items() if lv == "off"]
                off += [h for h, o in cfg["site_opts"].items() if o.get("consent") is False]
                if cfg["shield_level"] == "off":
                    continue
                c = QWebEngineScript()
                c.setName("ike-consent")
                c.setSourceCode(self._consent_src.replace(
                    "__IKE_CFG__", json.dumps({"off": off})))
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
    def _script(name, source, main_world, subframes=True):
        s = QWebEngineScript()
        s.setName(name)
        s.setSourceCode(source)
        s.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        s.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld if main_world
                     else QWebEngineScript.ScriptWorldId.ApplicationWorld)
        s.setRunsOnSubFrames(bool(subframes))
        return s

    def _ads_on(self, host):
        cfg = self.config
        return bool(cfg["comp_adblock"]) and cfg.level_for(host) != "off" \
            and cfg.site_opt(host, "ads") is not False

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
        if code["MAIN"]:
            scripts.insert(self._script("ike-video-main", code["MAIN"], True))
        if code["ISOLATED"]:
            scripts.insert(self._script("ike-video-iso", code["ISOLATED"], False))
        if self.config["video_ad_skip"]:
            bases = [b for b in self.config["video_ad_skip_hosts"] if self._ads_on("www." + b)]
            scripts.insert(self._script(
                "ike-videoads", self._videoads_src.replace("__IKE_VA__", json.dumps({"hosts": bases})),
                False))
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
        if not host or not self._ads_on(host) or host in self.video_hosts():
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
        if code["MAIN"]:
            scripts.insert(self._script("ike-sl-main:" + host, code["MAIN"], True))
        if code["ISOLATED"]:
            scripts.insert(self._script("ike-sl-iso:" + host, code["ISOLATED"], False))
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

            from .config import DOH_PROVIDERS
            mode = G.DnsMode()
            if doh and doh != "off":
                mode.secureMode = G.SecureDnsMode.SecureOnly
                mode.serverTemplates = DOH_PROVIDERS.get(doh, doh)
            else:
                mode.secureMode = G.SecureDnsMode.SystemOnly
            return G.setDnsMode(mode)
        except Exception:
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
