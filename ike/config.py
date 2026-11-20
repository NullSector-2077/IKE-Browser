"""Persistent settings (JSON) and standard paths."""

import copy
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

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
_RANK = {name: i for i, name in enumerate(LEVELS)}
LEVEL_NAMES = {"off": "Off", "compatibility": "Compatibility", "balanced": "Balanced",
               "strict": "Strict", "maximum": "Maximum"}
_LEVEL_ALIASES = {"standard": "balanced"}


def rank(level):
    """0 = off ... 4 = maximum."""
    try:
        return _RANK.get(level, 2)
    except TypeError:                     # not a name at all
        return 2


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
# Google services whose anti-abuse checks protect sensitive operations (API keys,
# cloud projects, payments, account security): any trace of a changed page can
# make them refuse ("permission denied"). They get "Compatibility" unless the
# user chose a level for them (1.1.12).
SENSITIVE_HOSTS = ("aistudio.google.com", "console.cloud.google.com", "myaccount.google.com",
                   "pay.google.com", "payments.google.com", "admin.google.com",
                   # payments (1.1.14): PayPal's sign-in and Stripe's checkout page
                   "www.paypal.com", "paypal.com", "checkout.stripe.com")
# Google's own sites. On a sensitive service the shield leaves their requests
# alone (1.1.14): "Compatibility" was not enough, because the filter lists still
# blocked some of Google's own requests and its anti-abuse checks then refused
# the operation. Brave gets there with a hand-written list of exceptions; here
# the service simply works as with the shield off, while the trackers of other
# companies stay blocked. Ad and analytics domains (doubleclick.net,
# google-analytics.com, googletagmanager.com, ...) are not in this list.
GOOGLE_SITES = ("google.com", "googleapis.com", "gstatic.com", "googleusercontent.com",
                "recaptcha.net")


# The payment services found in shops everywhere (1.1.14). Their anti-fraud
# checks refuse a payment when part of them is blocked or changed, so their own
# requests, frames and cookies are left alone on every site; the rest of the
# shop keeps its protections.
PAYMENT_SITES = ("paypal.com", "paypalobjects.com", "stripe.com", "stripe.network")


def _owned(host, sites):
    """host is one of sites or a name under one of them. `sites` may also be
    the tuple of ".site" endings made by _endings (faster: asked for every
    request of every page)."""
    host = (host or "").lower().rstrip(".")
    if not sites or not sites[0].startswith("."):
        sites = _endings(sites)
    return ("." + host).endswith(sites)


def _endings(sites):
    return tuple("." + s for s in sites)


_GOOGLE_ENDINGS = _endings(GOOGLE_SITES)
_PAYMENT_ENDINGS = _endings(PAYMENT_SITES)


def google_owned(host):
    return _owned(host, _GOOGLE_ENDINGS)


def payment_owned(host):
    return _owned(host, _PAYMENT_ENDINGS)

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
    # sites that spread malware right now (abuse.ch URLhaus), as uBlock Origin
    # has it on by default; CC0 / MIT (1.1.17, docs/THIRD-PARTY.md)
    {"name": "Malicious URL Blocklist", "group": "ads", "enabled": True,
     "url": "https://malware-filter.gitlab.io/malware-filter/urlhaus-filter-online.txt"},
    {"name": "uBlock filters - Unbreak", "group": "ads", "enabled": True,
     "url": "https://ublockorigin.github.io/uAssets/filters/unbreak.txt"},
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
    "show_menubar": False,              # 1.1.9: off for a new installation (it takes room for little)
    "show_bookmarks_bar": False,        # (before 1.0.3; replaced by bookmarks_bar)
    "bookmarks_bar": "newtab",          # always | newtab | never
    "vtabs_autohide": False,            # vertical tabs appear when the mouse hits the left edge
    "vtabs_width": 240,
    "vtabs_icons_only": False,          # vertical tabs: only their icons, a narrow panel (1.1.16)
    "vtabs_anim_ms": 200,               # slide of the auto-hidden tab panel (0 = none)
    "ui_effects": True,                 # short fades and the loading mark of tabs (see effects.py)
    "toolbar_hidden": [],               # keys of TOOLBAR_ITEMS the user does not want
    "toolbar_known": ["back", "forward", "reload", "home", "downloads"],
    # 1.1.9: the owner's arrangement (Reload is fixed, toolbar.py; the shield is in the address bar)
    "toolbar_order": ["dark", "private", "cleansite", "screenshot", "split", "pip",
                      "bookmark", "downloads", "reader"],    # the menu: fixed before the window buttons (1.1.16)
    "toolbar_left": ["dark", "private", "cleansite", "screenshot", "split", "pip"],
    "urlbar_width": 50,                 # address bar: per cent of the window width (60 until 1.1.6)
    "urlbar_width_117": False,          # the old default of 60 was moved to 50 once (1.1.7)
    "newtab_clock": True,               # clock and date on the new tab page
    "newtab_weather": True,             # weather on the new tab page (needs a city, see weather.py)
    "newtab_bg": "default",             # photo behind the new tab page: "default" (I.K.E.'s own), "" or the user's copy (see newtabbg.py)
    "newtab_bg_118": False,             # I.K.E.'s own photo was given once to whoever had none (1.1.8)
    "newtab_bg_fit": "fill",            # fill | fit | centre
    "newtab_bg_veil": 35,               # veil in the page's colour over the photo, per cent (0-90)
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
    "chrome_major": 0,                  # current stable Chrome, for the engine age in About (see chromever)
    "chrome_checked": 0,
    "video_ad_skip": True,              # mute / fast-forward / skip ads in the players below
    "video_ad_skip_hosts": ["youtube.com", "youtube-nocookie.com"],
    "shield_advanced": False,           # advanced controls open in the shield panel
    "login_compat": True,               # gentle handling of Google/Microsoft/Apple sign-in
    "lookalike_warn": True,             # warn about sites imitating well-known ones (1.1.14, lookalike.py)
    "lookalike_ok": [],                 # sites the user marked as fine
    "video_hw": "auto",                 # video decoding with the graphics card: auto | on | off (1.1.16, app.py)
    "video_hw_fell_back": False,        # "on" was turned back to "auto" after a bad exit: say so once
    "mail_handler": "ask",              # email links: ask | system | gmail | outlook | proton | yahoo (1.1.16, mailto.py)
    "site_tint": True,                  # the toolbar takes a light tint of the site's colour (1.1.14)
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
    "lists_version": 5,                 # bumped when the default lists change
    "auto_update": True,
    # downloads
    "download_dir": "",
    "ask_download_location": True,
    # stats / session
    "blocked_total": 0,
    "blocked_month": {},             # {"key": "2026-11", "count": n, "prev_key": "2026-10", "prev": n}
    "blocked_counter": "month",      # what the new tab page shows: "month" | "total"
    # new tab page
    "newtab_tiles": "bookmarks",     # "bookmarks" | "visited" | "none"
    "newtab_tiles_hidden": [],       # addresses of the tiles the user hid
    "newtab_tiles_first": [],        # sites added with the "Add" tile: shown before the other bookmarks
    "session": [],
    "experimental_extensions": False,   # engine extension support is unstable
    "enabled_extensions": [],           # extension ids to re-enable at startup
    "ext_pending": "",                  # set while enabling; survives a crash
    # tabs / performance
    "page_watches": [],                 # pages checked for changes (see watcher.py)
    "page_watch_on": True,              # check them while I.K.E. is open
    # desktop integration through D-Bus (see plasma.py)
    "di_media": True,                   # media widget, lock screen and media keys (MPRIS)
    # sites (and their subdomains) where "next" and "previous" of the desktop's
    # media controls are read from the page (mediahook.js); nowhere else is a
    # page touched for them (1.1.12)
    "media_sites": ["youtube.com", "youtube-nocookie.com", "spotify.com", "soundcloud.com",
                    "twitch.tv", "vimeo.com", "dailymotion.com", "deezer.com", "tidal.com",
                    "bandcamp.com", "mixcloud.com", "music.apple.com", "jamendo.com",
                    "netflix.com", "primevideo.com", "disneyplus.com", "raiplay.it",
                    "raiplaysound.it", "nebula.tv", "odysee.com", "kick.com", "pocketcasts.com"],
    "di_downloads": True,               # downloads in Plasma's notifications
    "di_krunner": True,                 # open tabs and bookmarks in KRunner
    "di_kdeconnect": True,              # "Send to device" with KDE Connect
    "tab_sleep_minutes": 20,
    "autoplay_block": False,            # video and audio do not start by themselves (site_opts "autoplay")
    "mouse_gestures": False,            # right button held and dragged: back, forward, reload, close tab
    "site_zoom": {},
    "reader_theme": "auto",             # reader mode: auto | light | sepia | dark
    "reader_size": 19,                  # reader mode: text size in pixels (14 - 28)
    "smooth_scrolling": True,           # pages scroll smoothly (an engine switch: after a restart)                    # host: zoom factor chosen for that site (not in private windows)
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
    # auto | ask | off. "auto" is the default (1.1.13, the owner's rule): users only
    # browse, every signed release installs by itself; "off" is the user's choice
    "app_updates": "auto",
    "app_updates_1113": False,          # an old default "ask" was moved to "auto" once (1.1.13)
    "update_channel": "stable",         # stable | beta
    "last_app_check": 0,
    "passwords_offer_save": True,
    "crx_url": ("https://clients2.google.com/service/update2/crx?response=redirect"
                "&prodversion={version}&acceptformat=crx2,crx3&x=id%3D{id}%26uc"),
    "lang_url": "",                     # where language packs are listed (index.json)
    "system_titlebar": True,            # False: own window buttons, more room for pages
    "start_maximized": True,            # new windows fill the screen
    "dark_env_migrated": False,         # a system-wide forced dark mode was taken over once
}


# Toolbar buttons the user can show or hide: (key, hidden when first seen)
TOOLBAR_ITEMS = (("back", False), ("forward", False), ("reload", False), ("home", False),
                 ("bookmark", False), ("reader", False), ("screenshot", False), ("pip", True),
                 ("split", False), ("dark", False), ("private", False), ("cleansite", False),
                 ("downloads", False))


# settings of the Cyber theme, removed in 1.1.2: dropped from settings.json when it is read
_REMOVED = ("cyber_accent", "cyber_shape", "cyber_glow", "cyber_corners", "cyber_hint", "newtab_grid")
_LISTS_OF_DICTS = ("search_engines", "filter_lists", "containers", "page_watches")


def sound_settings(stored):
    """The stored settings without the values that are not of the kind the
    program expects (a settings file edited by hand, damaged, or written by
    something else): those fall back to their defaults instead of stopping
    the browser at start. Settings the program does not know are kept."""
    clean = {}
    for key, value in stored.items():
        if not isinstance(key, str):
            continue
        default = DEFAULTS.get(key)
        if key not in DEFAULTS or default is None:
            clean[key] = value
        elif isinstance(default, bool):
            if isinstance(value, bool) or value in (0, 1):
                clean[key] = bool(value)
        elif isinstance(default, (int, float)):
            if isinstance(value, (int, float)) and not isinstance(value, bool) and value == value \
                    and abs(value) != float("inf"):
                clean[key] = value
        elif isinstance(default, str):
            if isinstance(value, str):
                clean[key] = value
        elif isinstance(default, list):
            if isinstance(value, list):
                if key in _LISTS_OF_DICTS:
                    value = [v for v in value if isinstance(v, dict)]
                clean[key] = value
        elif isinstance(default, dict):
            if isinstance(value, dict):
                if key in ("site_levels", "site_opts", "ui_themes"):
                    want = str if key == "site_levels" else dict
                    value = {k: v for k, v in value.items() if isinstance(k, str) and isinstance(v, want)}
                clean[key] = value
    return clean


# Filter lists I.K.E. no longer offers because their terms do not allow it to
# use them (1.1.18): the hosts they are downloaded from. Settings of earlier
# versions that name one of them lose it once (see Config.load).
WITHDRAWN_LIST_HOSTS = ("pgl.yoyo.org",)


def _withdrawn_list(url):
    try:
        host = (urlsplit(str(url or "").strip()).hostname or "").rstrip(".")
    except ValueError:
        return False
    return any(host == h or host.endswith("." + h) for h in WITHDRAWN_LIST_HOSTS)


def _list_copy(url):
    """Where blocker.list_path keeps the downloaded copy of a list."""
    return DATA_DIR / "lists" / (hashlib.sha1(url.encode()).hexdigest()[:16] + ".txt")


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
            self.data.update(sound_settings(stored))
        d = self.data
        # 1.1.7: the address bar takes half of the window (the owner's choice); 60 was the old default
        if d.get("urlbar_width") == 60 and not d.get("urlbar_width_117"):
            d["urlbar_width"] = 50
        d["urlbar_width_117"] = True
        # 1.1.13: program updates install by themselves for everyone (the owner's rule);
        # "ask" was the old default, so it becomes "auto" once; "off" stays the user's choice
        if d.get("app_updates") == "ask" and not d.get("app_updates_1113"):
            d["app_updates"] = "auto"
        d["app_updates_1113"] = True
        # 1.1.8: the new tab page gets I.K.E.'s own photo; whoever had none before gets it once
        if d.get("newtab_bg") == "" and not d.get("newtab_bg_118"):
            d["newtab_bg"] = "default"
        d["newtab_bg_118"] = True
        # 1.1.6: "Translate page" moved into the address bar; "Bookmark this page" takes its place
        for key in ("toolbar_order", "toolbar_left", "toolbar_hidden", "toolbar_known"):
            if isinstance(d.get(key), list) and "translate" in d[key]:
                items = [x for x in d[key] if x != "bookmark"]
                d[key] = ["bookmark" if x == "translate" else x for x in items]
        # the Cyber theme is gone (1.1.2): whoever used it follows the system again
        if d.get("ui_scheme") == "theme:cyber":
            d["ui_scheme"] = "system"
        for key in _REMOVED:
            d.pop(key, None)
        if isinstance(stored, dict) and "bookmarks_bar" not in stored \
                and stored.get("show_bookmarks_bar"):
            d["bookmarks_bar"] = "always"       # keep what the user had chosen
        if isinstance(stored, dict) and stored.get("lists_version", 1) < 2:
            # older settings: add the list that carries the fast-moving video-ad rules
            have = {e.get("url") for e in d["filter_lists"]}
            ublock = any("ublockorigin.github.io/uAssets" in (u or "") for u in have)
            for entry in DEFAULT_LISTS:
                if "quick-fixes" in entry["url"] and entry["url"] not in have and ublock:
                    d["filter_lists"].insert(0, dict(entry))
                    d["last_lists_update"] = 0      # fetch it at the next start
            d["lists_version"] = 2
        if isinstance(stored, dict) and stored.get("lists_version", 1) < 3:
            # older settings: the video-ad rules live in these two lists; make sure they
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
        if isinstance(stored, dict) and stored.get("lists_version", 1) < 4:
            # 1.1.17: the list of sites that spread malware, for everybody
            # (once: whoever turns it off later keeps it off)
            entry = next(e for e in DEFAULT_LISTS if "urlhaus-filter" in e["url"])
            if not any(e.get("url") == entry["url"] for e in d["filter_lists"]):
                d["filter_lists"].append(dict(entry))
                d["last_lists_update"] = 0      # fetch it at the next start
            d["lists_version"] = 4
        if isinstance(stored, dict) and stored.get("lists_version", 1) < 5:
            # 1.1.18: a list whose terms do not allow I.K.E. to use it is removed
            # from every profile, on or off, with the copy kept on disk; it is
            # never downloaded or used again (the owner's decision)
            dropped = [e for e in d["filter_lists"] if _withdrawn_list(e.get("url"))]
            d["filter_lists"] = [e for e in d["filter_lists"] if e not in dropped]
            if self.path == CONFIG_DIR / "settings.json":
                for e in dropped:
                    try:
                        _list_copy(e["url"]).unlink(missing_ok=True)
                    except (OSError, TypeError, AttributeError):
                        pass
            d["lists_version"] = 5
        d.pop("pgl_off_1116", None)             # the flag of 1.1.16, no longer used
        # older level names ("standard" became "balanced")
        d["shield_level"] = _LEVEL_ALIASES.get(d["shield_level"], d["shield_level"])
        if d["shield_level"] not in LEVELS:
            d["shield_level"] = "balanced"
        d["site_levels"] = {h: _LEVEL_ALIASES.get(lv, lv) for h, lv in d["site_levels"].items()
                            if _LEVEL_ALIASES.get(lv, lv) in LEVELS}

    def save(self):
        """Write the settings, unless the file already holds exactly them: the
        session is saved every minute, and an unchanged minute writes nothing
        (1.1.17)."""
        text = json.dumps(self.data, indent=1, ensure_ascii=False)
        if text == getattr(self, "_written", None) and self.path.exists():
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(self.path)
        self._written = text

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
        while levels and host:            # asked for every request: no list, no walk (1.1.18)
            if host in levels:
                return levels[host]
            i = host.find(".")
            if i < 0:
                break
            host = host[i + 1:]
        level = self.data["shield_level"]
        if self.data["login_compat"] and full in LOGIN_HOSTS and LEVELS.index(level) > 1:
            return "compatibility"
        if full in SENSITIVE_HOSTS and LEVELS.index(level) > 1:
            return "compatibility"
        return level

    def sensitive_hands_off(self, site, host=None):
        """True when the page `site` is a sensitive service (Google's, PayPal,
        Stripe's checkout) whose level the user did not choose, and `host` (if
        given) belongs to Google or to a payment service: the shield then
        changes nothing, as if it were off (1.1.14)."""
        full = (site or "").lower()
        if full not in SENSITIVE_HOSTS or self.data["shield_level"] == "off":
            return False
        h, levels = full, self.data["site_levels"]
        while h:
            if h in levels:
                return False                      # the user's own choice wins
            if "." not in h:
                break
            h = h.split(".", 1)[1]
        return host is None or google_owned(host) or payment_owned(host)

    def site_opt(self, host, key):
        """Per-site override of one protection, or None to follow the level."""
        opts = self.data["site_opts"]
        if not opts:
            return None                   # asked for every request: most users have none (1.1.18)
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
