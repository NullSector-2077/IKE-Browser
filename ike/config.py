"""Persistent settings (JSON) and standard paths."""

import copy
import json
import os
from pathlib import Path

from . import osinfo

PROFILE = os.environ.get("IKE_PROFILE", "").strip() or "default"


def _xdg(kind):
    base = osinfo.app_dir(kind)
    # Extra profiles live in their own sub-tree; "default" keeps the base dirs.
    return base if PROFILE == "default" else base / "profiles" / PROFILE


def base_dir(kind="config"):
    return osinfo.app_dir(kind)


def list_profiles():
    out = ["default"]
    d = base_dir() / "profiles"
    if d.is_dir():
        out += sorted(p.name for p in d.iterdir() if p.is_dir())
    return out


CONFIG_DIR = _xdg("config")
DATA_DIR = _xdg("data")
CACHE_DIR = _xdg("cache")
PKG_DIR = Path(__file__).resolve().parent
RES_DIR = PKG_DIR / "resources"

LEVELS = ("off", "compatibility", "balanced", "strict", "maximum")
LEVEL_NAMES = {"off": "Off", "compatibility": "Compatibility", "balanced": "Balanced",
               "strict": "Strict", "maximum": "Maximum"}
_LEVEL_ALIASES = {"standard": "balanced"}


def rank(level):
    """0 = off ... 4 = maximum."""
    return LEVELS.index(level) if level in LEVELS else 2

DEFAULT_CONTAINERS = [
    {"name": "Personale", "color": "#3daee9"},
    {"name": "Lavoro", "color": "#f67400"},
    {"name": "Banca", "color": "#27ae60"},
    {"name": "Acquisti", "color": "#9b59b6"},
]
# Sign-in pages of the big identity providers. They refuse or break under
# fingerprint changes and need their own cookies when embedded in other sites.
LOGIN_HOSTS = ("accounts.google.com", "accounts.youtube.com", "login.live.com",
               "login.microsoftonline.com", "appleid.apple.com", "idmsa.apple.com")
FIREFOX_UA = osinfo.identity()["firefox_ua"]
PERMISSION_KINDS = ("camera", "microphone", "location", "notifications", "clipboard", "screen", "fonts")

DEFAULT_ENGINES = [
    {"name": "DuckDuckGo", "keyword": "d",
     "url": "https://duckduckgo.com/?q={q}",
     "suggest": "https://duckduckgo.com/ac/?q={q}&type=list"},
    {"name": "Startpage", "keyword": "sp",
     "url": "https://www.startpage.com/do/search?q={q}",
     "suggest": "https://www.startpage.com/osuggestions?q={q}"},
    {"name": "Brave Search", "keyword": "b",
     "url": "https://search.brave.com/search?q={q}",
     "suggest": "https://search.brave.com/api/suggest?q={q}"},
    {"name": "Qwant", "keyword": "q",
     "url": "https://www.qwant.com/?q={q}",
     "suggest": "https://api.qwant.com/v3/suggest?q={q}"},
    {"name": "Ecosia", "keyword": "e",
     "url": "https://www.ecosia.org/search?q={q}",
     "suggest": "https://ac.ecosia.org/autocomplete?q={q}&type=list"},
    {"name": "Mojeek", "keyword": "m",
     "url": "https://www.mojeek.com/search?q={q}", "suggest": ""},
    {"name": "Google", "keyword": "g",
     "url": "https://www.google.com/search?q={q}",
     "suggest": "https://suggestqueries.google.com/complete/search?client=firefox&q={q}"},
    {"name": "Bing", "keyword": "bi",
     "url": "https://www.bing.com/search?q={q}",
     "suggest": "https://api.bing.com/osjson.aspx?query={q}"},
    {"name": "Wikipedia", "keyword": "w",
     "url": "https://it.wikipedia.org/w/index.php?search={q}",
     "suggest": "https://it.wikipedia.org/w/api.php?action=opensearch&search={q}"},
    {"name": "YouTube", "keyword": "yt",
     "url": "https://www.youtube.com/results?search_query={q}",
     "suggest": "https://suggestqueries.google.com/complete/search?client=firefox&ds=yt&q={q}"},
]

DEFAULT_LISTS = [
    {"name": "EasyList", "group": "ads", "enabled": True,
     "url": "https://easylist.to/easylist/easylist.txt"},
    {"name": "EasyPrivacy", "group": "ads", "enabled": True,
     "url": "https://easylist.to/easylist/easyprivacy.txt"},
    {"name": "uBlock filters", "group": "ads", "enabled": True,
     "url": "https://ublockorigin.github.io/uAssets/filters/filters.txt"},
    {"name": "uBlock filters - Quick fixes", "group": "ads", "enabled": True,
     "url": "https://ublockorigin.github.io/uAssets/filters/quick-fixes.txt"},
    {"name": "uBlock filters - Privacy", "group": "ads", "enabled": True,
     "url": "https://ublockorigin.github.io/uAssets/filters/privacy.txt"},
    {"name": "uBlock filters - Badware", "group": "ads", "enabled": True,
     "url": "https://ublockorigin.github.io/uAssets/filters/badware.txt"},
    {"name": "uBlock filters - Unbreak", "group": "ads", "enabled": True,
     "url": "https://ublockorigin.github.io/uAssets/filters/unbreak.txt"},
    {"name": "Peter Lowe's list", "group": "ads", "enabled": True,
     "url": "https://pgl.yoyo.org/adservers/serverlist.php?hostformat=adblockplus&showintro=0&mimetype=plaintext"},
    {"name": "EasyList Italy", "group": "ads", "enabled": True,
     "url": "https://easylist-downloads.adblockplus.org/easylistitaly.txt"},
    {"name": "EasyList Cookie List", "group": "consent", "enabled": True,
     "url": "https://secure.fanboy.co.nz/fanboy-cookiemonster.txt"},
    {"name": "uBlock filters - Cookie notices", "group": "consent", "enabled": True,
     "url": "https://ublockorigin.github.io/uAssets/filters/annoyances-cookies.txt"},
]

DOH_PROVIDERS = {
    "Quad9": "https://dns.quad9.net/dns-query",
    "Mullvad": "https://dns.mullvad.net/dns-query",
    "Cloudflare": "https://cloudflare-dns.com/dns-query",
    "AdGuard": "https://dns.adguard-dns.com/dns-query",
}

DEFAULTS = {
    "language": "auto",                 # auto | it | en
    "accept_language": "it-IT,it,en-US,en",
    "startup": "restore",               # restore | home | newtab
    "homepage": "ike:newtab",
    "tabs_position": "horizontal",      # horizontal | vertical
    "show_menubar": True,
    "show_bookmarks_bar": False,        # (before 1.0.3; replaced by bookmarks_bar)
    "bookmarks_bar": "newtab",          # always | newtab | never
    "vtabs_autohide": False,            # vertical tabs appear when the mouse hits the left edge
    "vtabs_width": 240,
    "vtabs_anim_ms": 200,               # slide of the auto-hidden tab panel (0 = none)
    "toolbar_hidden": [],               # keys of TOOLBAR_ITEMS the user does not want
    "toolbar_known": ["back", "forward", "reload", "home", "downloads"],
    "toolbar_order": ["shield", "reload", "translate", "reader", "screenshot", "pip",
                      "split", "dark", "private", "cleansite", "downloads", "menu"],
    "toolbar_left": ["shield", "reload", "translate"],  # balance the address field around the window centre
    "urlbar_width": 60,                 # address bar: per cent of the window width
    "newtab_clock": True,               # clock and date on the new tab page
    "newtab_weather": True,             # weather on the new tab page (needs a city, see weather.py)
    "weather_city": "",                 # chosen by the user in Settings; never the system location
    "weather_lat": None,
    "weather_lon": None,
    "weather_unit": "celsius",          # celsius | fahrenheit
    "default_zoom": 1.0,
    "search_engines": DEFAULT_ENGINES,
    "default_engine": "DuckDuckGo",
    "search_suggestions": True,
    # protection
    "shield_level": "balanced",
    "site_levels": {},                  # host -> level
    "site_noscript": [],                # hosts with scripts blocked
    "site_opts": {},                    # host -> {"ads","cookies","fp","https","consent","params"}
                                        # overrides; "repaired": keys turned off by Repair this site
    "repair_button": True,              # "Repair this site" in the shield panel (see repair.py)
    "icon_theme": "system",             # system | theme:<installed theme> | set:<shipped set>
    "ui_scheme": "system",              # system | light | dark | theme:<key> | user:<name> (see themes)
    "ui_themes": {},                    # themes saved by the user: name -> colours and font
    "userscripts_enabled": True,        # run the installed user scripts
    "chrome_major": 0,                  # stable Chrome version presented to sites (see chromever)
    "chrome_checked": 0,
    "video_ad_skip": True,              # mute / fast-forward / skip ads in the players below
    "video_ad_skip_hosts": ["youtube.com", "youtube-nocookie.com"],
    "shield_advanced": False,           # advanced controls open in the shield panel
    "login_compat": True,               # gentle handling of Google/Microsoft/Apple sign-in
    "https_only": True,
    "strip_tracking_params": True,
    "send_gpc": True,
    "trim_referrer": True,
    "webrtc_hide_ip": True,
    "block_third_party_cookies": True,
    "clear_on_exit": False,
    "doh": "off",                       # off | provider name | custom URL
    # built-in components (removable)
    "comp_adblock": True,
    "comp_consent": True,
    "comp_dark": True,
    "dark_mode": "off",                 # off | on
    # reader: Dark Reader API; engine: Chromium Auto Dark Mode. Both support
    # per-site include/exclude rules and are applied at page navigation.
    "dark_engine": "reader",
    "dark_sites": [],                   # hosts that are dark while dark mode is off
    "dark_exclude": [],                 # hosts that stay light while dark mode is on
    "dark_theme": {"brightness": 100, "contrast": 100, "sepia": 0},
    "restore_once": False,              # reopen the last tabs at the next start (restart)
    "filter_lists": DEFAULT_LISTS,
    "custom_filters": "",
    "last_lists_update": 0,
    "last_fast_update": 0,              # urgent-fix lists (see blocker.FAST_INTERVAL)
    "lists_version": 3,                 # bumped when default lists are added
    "auto_update": True,
    # downloads
    "download_dir": "",
    "ask_download_location": True,
    # stats / session
    "blocked_total": 0,
    "session": [],
    "experimental_extensions": False,   # engine extension support is unstable
    "enabled_extensions": [],           # extension ids to re-enable at startup
    "ext_pending": "",                  # set while enabling; survives a crash
    # tabs / performance
    "page_watches": [],                 # pages checked for changes (see watcher.py)
    "page_watch_on": True,              # check them while I.K.E. is open
    # desktop integration through D-Bus (see plasma.py)
    "di_media": True,                   # media widget, lock screen and media keys (MPRIS)
    "di_downloads": True,               # downloads in Plasma's notifications
    "di_krunner": True,                 # open tabs and bookmarks in KRunner
    "di_kdeconnect": True,              # "Send to device" with KDE Connect
    "tab_sleep_minutes": 20,
    "res_mem_limit": 0,                 # MB: suspend background tabs of a site above it (0 = off)
    "res_cpu_limit": 0,                 # % of a core: freeze background tabs above it (0 = off)
    "res_mem_default": 1500,            # values offered when a limit is switched on
    "res_cpu_default": 50,            # 0 = never suspend background tabs
    "lazy_restore": True,               # restored tabs load when first shown
    "containers": DEFAULT_CONTAINERS,
    "perm_block": [],                   # permission kinds that are always refused
    # translation (external service, asked before first use)
    "translate_url": "https://translate.google.com/translate?sl=auto&tl={lang}&u={url}",
    "translate_confirmed": False,
    # program updates
    "app_updates": "ask",               # ask | auto | off
    "update_channel": "stable",         # stable | beta
    "last_app_check": 0,
    "passwords_offer_save": True,
    "crx_url": ("https://clients2.google.com/servike/update2/crx?response=redirect"
                "&prodversion={version}&acceptformat=crx2,crx3&x=id%3D{id}%26uc"),
    "lang_url": "",                     # where language packs are listed (index.json)
    "system_titlebar": True,            # False: own window buttons, more room for pages
    "start_maximized": True,            # new windows fill the screen
    "dark_env_migrated": False,         # a system-wide forced dark mode was taken over once
}


# Toolbar buttons the user can show or hide: (key, hidden when first seen)
TOOLBAR_ITEMS = (("back", False), ("forward", False), ("reload", False), ("home", False),
                 ("translate", False), ("reader", False), ("screenshot", False), ("pip", False),
                 ("split", True), ("dark", True), ("private", True), ("cleansite", True),
                 ("downloads", False))


class Config:
    def __init__(self, path=None):
        self.path = Path(path) if path else CONFIG_DIR / "settings.json"
        self.data = copy.deepcopy(DEFAULTS)
        self.load()
        # toolbar buttons added by a newer version start shown or hidden as designed
        known, hidden = list(self.data["toolbar_known"]), list(self.data["toolbar_hidden"])
        for key, hide in TOOLBAR_ITEMS:
            if key not in known:
                known.append(key)
                if hide and key not in hidden:
                    hidden.append(key)
        self.data["toolbar_known"], self.data["toolbar_hidden"] = known, hidden

    def load(self):
        try:
            stored = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if isinstance(stored, dict):
            self.data.update(stored)
        d = self.data
        if isinstance(stored, dict) and "bookmarks_bar" not in stored \
                and stored.get("show_bookmarks_bar"):
            d["bookmarks_bar"] = "always"       # keep what the user had chosen
        if isinstance(stored, dict) and stored.get("lists_version", 1) < 2:
            # 1.0.1 adds the list that carries the fast-moving video-ad rules
            have = {e.get("url") for e in d["filter_lists"]}
            ublock = any("ublockorigin.github.io/uAssets" in (u or "") for u in have)
            for entry in DEFAULT_LISTS:
                if "quick-fixes" in entry["url"] and entry["url"] not in have and ublock:
                    d["filter_lists"].insert(0, dict(entry))
                    d["last_lists_update"] = 0      # fetch it at the next start
            d["lists_version"] = 2
        if isinstance(stored, dict) and stored.get("lists_version", 1) < 3:
            # 1.1.1: the video-ad rules live in these two lists; make sure they
            # are present and enabled, and fetch everything again (the main
            # list now brings its sub-lists with it).
            for entry in DEFAULT_LISTS:
                if entry["name"] not in ("uBlock filters", "uBlock filters - Quick fixes"):
                    continue
                mine = [e for e in d["filter_lists"] if e.get("url") == entry["url"]]
                if mine:
                    mine[0]["enabled"] = True
                else:
                    d["filter_lists"].insert(0, dict(entry))
            d["last_lists_update"] = 0
            d["lists_version"] = 3
        # migrate level names from 0.1 ("standard" became "balanced")
        d["shield_level"] = _LEVEL_ALIASES.get(d["shield_level"], d["shield_level"])
        if d["shield_level"] not in LEVELS:
            d["shield_level"] = "balanced"
        d["site_levels"] = {h: _LEVEL_ALIASES.get(lv, lv) for h, lv in d["site_levels"].items()
                            if _LEVEL_ALIASES.get(lv, lv) in LEVELS}

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=1, ensure_ascii=False),
                       encoding="utf-8")
        tmp.replace(self.path)

    def __getitem__(self, key):
        return self.data[key]

    def __setitem__(self, key, value):
        self.data[key] = value

    def get(self, key, default=None):
        return self.data.get(key, default)

    # --- helpers -----------------------------------------------------
    def engine(self, name=None):
        name = name or self.data["default_engine"]
        engines = self.data["search_engines"]
        for e in engines:
            if e["name"] == name:
                return e
        return engines[0] if engines else DEFAULT_ENGINES[0]

    def level_for(self, host):
        full = host = (host or "").lower()
        levels = self.data["site_levels"]
        while host:
            if host in levels:
                return levels[host]
            if "." not in host:
                break
            host = host.split(".", 1)[1]
        level = self.data["shield_level"]
        if self.data["login_compat"] and full in LOGIN_HOSTS and LEVELS.index(level) > 1:
            return "compatibility"
        return level

    def site_opt(self, host, key):
        """Per-site override of one protection, or None to follow the level."""
        opts = self.data["site_opts"]
        host = (host or "").lower()
        while host:
            o = opts.get(host)
            if o is not None and key in o:
                return o[key]
            if "." not in host:
                break
            host = host.split(".", 1)[1]
        return None

    def set_site_opt(self, host, key, value):
        host = (host or "").lower()
        if not host:
            return
        o = self.data["site_opts"].setdefault(host, {})
        if value is None:
            o.pop(key, None)
        else:
            o[key] = value
        if not o:
            self.data["site_opts"].pop(host, None)

    def set_site_level(self, host, level):
        host = (host or "").lower()
        if not host:
            return
        if level is None or level == self.data["shield_level"]:
            self.data["site_levels"].pop(host, None)
        else:
            self.data["site_levels"][host] = level


def ensure_dirs():
    for d in (CONFIG_DIR, DATA_DIR, CACHE_DIR):
        d.mkdir(parents=True, exist_ok=True)
