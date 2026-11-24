"""Bounce-tracking protection (1.1.24, on by default).

A tracker that cannot set cookies inside other sites' pages (I.K.E. blocks
cross-site cookies) can still have the user pass through its own site for a
moment: a link goes to tracker.example, which redirects at once to the real
destination. During that hop tracker.example is the site in the address bar,
so its cookies are first-party and it recognises the user on every such hop.

I.K.E. notes the sites a page only passed through: a redirect of the main
frame (the server's, or the page's own without a click) away from a site of
another registrable domain, with no click or key on it. Half a minute later
such a site loses the cookies and the data it stored (local storage,
databases, caches, service workers), unless:

- the user used it (a click or a key on one of its pages, its address typed)
  in the last KEEP_DAYS days, or it was in the history when the protection
  first ran;
- it is open in a tab, or bookmarked;
- its protection is off, or its cookies are allowed, in the shield;
- it is a sign-in, payment or other sensitive service I.K.E. already leaves
  alone (config.LOGIN_HOSTS, SENSITIVE_HOSTS, PAYMENT_SITES).

Cheap: one check per main-frame navigation (no work per request), and the
clean-up only when such a site has cookies. Private windows are left alone
(everything of theirs goes when they close) and record nothing.

The stored data of a site is removed from a hidden page that has the site's
address but loads nothing (setHtml with that base address): the engine has no
call to remove one site's storage while it runs.
"""

import time

from PyQt6.QtCore import QObject, QTimer, QUrl
from PyQt6.QtWebEngineCore import QWebEnginePage

DELAY_MS = 30 * 1000           # "shortly after": the clean-up waits this long
KEEP_DAYS = 45                 # a site the user used stays untouched this long (as Firefox)
MAX_USED = 5000                # remembered sites; the oldest go first
MAX_PENDING = 64
HISTORY_SEED = 20000           # history rows read once, when the protection first runs

CLEAR_JS = ("(async function(){try{localStorage.clear();sessionStorage.clear();}catch(e){}"
            "try{var d=await indexedDB.databases();d.forEach(function(x){indexedDB.deleteDatabase(x.name);});}catch(e){}"
            "try{var k=await caches.keys();await Promise.all(k.map(function(x){return caches.delete(x);}));}catch(e){}"
            "try{var r=await navigator.serviceWorker.getRegistrations();"
            "await Promise.all(r.map(function(x){return x.unregister();}));}catch(e){}"
            "document.title='ike-cleaned';})(); 1")
CLEANED = "ike-cleaned"


def today(now=None):
    return int((time.time() if now is None else now) // 86400)


def _site(host):
    from .shields import site_of
    return site_of((host or "").lower().strip("."))


def _web(url):
    return url.scheme() in ("http", "https") and bool(url.host())


def is_redirect(nav_type):
    return nav_type == QWebEnginePage.NavigationType.NavigationTypeRedirect


def hop(previous, url, nav_type, user_acted):
    """The site `previous` only bounced the user on to `url`: its registrable
    domain, else None."""
    if previous is None or not is_redirect(nav_type) or user_acted:
        return None
    if not _web(previous) or not _web(url):
        return None
    a, b = previous.host().lower(), url.host().lower()
    if a == b:
        return None
    site = _site(a)
    if not site or site == _site(b):
        return None                     # within one site (www., http -> https...)
    return site


def protected_site(config, site, hosts=()):
    """Sites the protection never cleans: sign-in, payment and the other
    sensitive services, and those the user allowed in the shield."""
    from .config import LOGIN_HOSTS, PAYMENT_SITES, SENSITIVE_HOSTS
    for h in LOGIN_HOSTS + SENSITIVE_HOSTS + PAYMENT_SITES:
        if _site(h) == site:
            return True
    for h in set(hosts) | {site}:
        if config.level_for(h) == "off" or config.site_opt(h, "cookies") == "allow":
            return True
    return False


def prune(used, now=None, keep=KEEP_DAYS, most=MAX_USED):
    """Drop the sites not used for `keep` days, then the oldest above `most`."""
    day = today(now)
    for site in [s for s, d in used.items() if not isinstance(d, int) or day - d > keep]:
        used.pop(site, None)
    if len(used) > most:
        for site, _d in sorted(used.items(), key=lambda kv: kv[1])[:len(used) - most]:
            used.pop(site, None)
    return used


class BounceGuard(QObject):
    """Notes the hops of the pages' navigations and cleans those sites."""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.pending = {}               # (id(profile), site) -> {"profile", "site", "hosts", "origins"}
        self.purged = []                # sites cleaned in this session
        self._last = None               # the last site recorded as used
        self._timer = None
        self._cleaning = []             # [(profile, origin)] waiting for the hidden page
        self._cleaner = None

    def on(self):
        return bool(self.app.config.get("bounce_protect", True))

    def _used_map(self):
        cfg = self.app.config
        used = cfg.get("bounce_used")
        if not isinstance(used, dict):
            used = cfg["bounce_used"] = {}
        return used

    # --- what the pages tell ------------------------------------------------
    def used(self, page, url=None):
        """The user acted on a page (a click, a key, an address typed)."""
        url = page.url() if url is None else url
        if not _web(url) or page.profile().isOffTheRecord():
            return
        host = url.host().lower()
        day = today()
        if self._last == (host, day):
            return                      # the same site again: nothing to do
        self._last = (host, day)
        site = _site(host)
        if site:
            used = self._used_map()
            used[site] = day
            if len(used) > MAX_USED + 100:
                prune(used)

    def navigation(self, page, url, nav_type, user_acted):
        """A navigation of the main frame starts (WebPage.acceptNavigationRequest)."""
        previous = getattr(page, "_ike_bounce_from", None)
        page._ike_bounce_from = QUrl(url)
        if nav_type == QWebEnginePage.NavigationType.NavigationTypeTyped:
            self.used(page, url)
            return
        if not self.on() or page.profile().isOffTheRecord():
            return
        site = hop(previous, url, nav_type, user_acted)
        if site is None:
            return
        key = (id(page.profile()), site)
        entry = self.pending.get(key)
        if entry is None:
            if len(self.pending) >= MAX_PENDING:
                return
            entry = self.pending[key] = {"profile": page.profile(), "site": site,
                                         "hosts": set(), "origins": set()}
        entry["hosts"].add(previous.host().lower())
        port = previous.port()
        entry["origins"].add("%s://%s%s/" % (previous.scheme(), previous.host().lower(),
                                             (":%d" % port) if port > 0 else ""))
        if self._timer is None:
            self._timer = QTimer(self)
            self._timer.setSingleShot(True)
            self._timer.timeout.connect(self.purge)
        if not self._timer.isActive():
            self._timer.start(DELAY_MS)

    # --- the clean-up --------------------------------------------------------
    def _seed(self):
        """The first time: every site of the history counts as used today (the
        protection never takes the cookies of a site the user knew before it)."""
        cfg = self.app.config
        if cfg.get("bounce_seeded"):
            return
        used = self._used_map()
        day = today()
        try:
            rows = self.app.storage.db.execute(
                "SELECT url FROM history ORDER BY last DESC LIMIT ?", (HISTORY_SEED,)).fetchall()
        except Exception:
            rows = []
        for (u,) in rows:
            site = _site(QUrl(u).host())
            if site:
                used.setdefault(site, day)
        prune(used)
        cfg["bounce_seeded"] = True

    def _kept_sites(self):
        """Sites open in a tab or bookmarked."""
        out = set()
        for w in list(getattr(self.app, "windows", [])):
            views = w.all_views() if hasattr(w, "all_views") else getattr(w, "views", [])
            for v in views:
                for u in (v.url(), QUrl(getattr(v, "pending_url", None) or "")):
                    if _web(u):
                        out.add(_site(u.host()))
        try:
            for row in self.app.storage.bookmarks():
                u = QUrl(row[0] if isinstance(row, (tuple, list)) else str(row))
                if _web(u):
                    out.add(_site(u.host()))
        except Exception:
            pass
        return out

    def purge(self):
        """Clean the sites that only bounced the user on (DELAY_MS after the first)."""
        pending, self.pending = self.pending, {}
        if not pending or not self.on():
            return []
        self._seed()
        used = self._used_map()
        day = today()
        kept = self._kept_sites()
        cfg = self.app.config
        done = []
        for entry in pending.values():
            site, profile = entry["site"], entry["profile"]
            if site in kept or day - used.get(site, -10 ** 6) <= KEEP_DAYS:
                continue
            if protected_site(cfg, site, entry["hosts"]):
                continue
            cookies = self.app.shields.site_cookies(profile, site)
            if not cookies:
                continue                # it stored nothing that follows the user
            store = profile.cookieStore()
            for c in cookies:
                store.deleteCookie(c)
            for origin in sorted(entry["origins"]):
                self._cleaning.append((profile, origin))
            done.append(site)
        self.purged.extend(done)
        if self._cleaning and self._cleaner is None:
            QTimer.singleShot(0, self._clean_next)
        return done

    def _clean_next(self):
        """The site's stored data, from a hidden page at its address that loads nothing."""
        if self._cleaner is not None:
            return
        if not self._cleaning:
            return
        profile, origin = self._cleaning.pop(0)
        page = self._cleaner = QWebEnginePage(profile, self)
        finished = {"done": False}

        def done(*_a):
            if finished["done"]:
                return
            finished["done"] = True
            self._cleaner = None
            page.deleteLater()
            QTimer.singleShot(0, self._clean_next)

        def loaded(ok):
            if not ok:
                done()
                return
            page.runJavaScript(CLEAR_JS, 0)

        page.loadFinished.connect(loaded)
        # the clearing is asynchronous: the page says when it has finished
        page.titleChanged.connect(lambda t: done() if t == CLEANED else None)
        QTimer.singleShot(8000, done)    # never stuck on one site
        page.setHtml("<!doctype html><title></title>", QUrl(origin))
