"""The colours of dark mode for pages (Dark Reader's theme), checked (1.1.25).

The Dark mode panel of the toolbar (darkpanel.py) changes them; they are kept
in the settings ("dark_theme" for every site, "dark_site_themes" for the
sites that have their own) and given to Dark Reader in the pages
(darkpages.py, resources/darkmode.js). Every value is checked here, in
Python, before it reaches a page: numbers in their ranges, colours as
#rrggbb, a font only from the fonts of this computer; anything else becomes
Dark Reader's own default. Nothing a page does can change them.

The keys are Dark Reader's own names, the defaults its own (those of the
extension on Linux), except "scrollbarColor": "hidden" is I.K.E.'s, the
page's scroll bars hidden (darkmode.js).
"""

import re

DEFAULTS = {
    "mode": 1,                          # 1 dark, 0 light
    "brightness": 100,
    "contrast": 100,
    "sepia": 0,
    "grayscale": 0,
    "useFont": False,
    "fontFamily": "Open Sans",
    "textStroke": 0,
    "darkSchemeBackgroundColor": "#181a1b",
    "darkSchemeTextColor": "#e8e6e3",
    "lightSchemeBackgroundColor": "#dcdad7",
    "lightSchemeTextColor": "#181a1b",
    "scrollbarColor": "auto",           # auto | hidden | #rrggbb
    "selectionColor": "auto",           # auto | #rrggbb
}
# the sliders: (key, lowest, highest), as in Dark Reader's own
RANGES = {"brightness": (50, 150), "contrast": (50, 150), "sepia": (0, 100), "grayscale": (0, 100)}
SLIDERS = ("brightness", "contrast", "sepia", "grayscale")
STROKES = (0, 0.3, 0.5, 1)
COLOURS = ("darkSchemeBackgroundColor", "darkSchemeTextColor",
           "lightSchemeBackgroundColor", "lightSchemeTextColor")
SITES_MAX = 500                         # sites with their own colours kept in the settings

_HEX = re.compile(r"#[0-9a-f]{6}")
_HOST = re.compile(r"[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*|\[[0-9a-f:.]+\]")
# a font's name goes into a style sheet: letters (any alphabet), digits, spaces and . - _ & + only
_FONT = re.compile(r"[^\W_]([\w .&+-]*[\w.+])?")


def colour(value):
    """'#rrggbb' (lower case) from a colour written that way, else None."""
    if isinstance(value, str):
        v = value.strip().lower()
        if _HEX.fullmatch(v):
            return v
    return None


def font_name_ok(name):
    return isinstance(name, str) and 0 < len(name) <= 64 and bool(_FONT.fullmatch(name))


def host_ok(host):
    return isinstance(host, str) and 0 < len(host) <= 253 and bool(_HOST.fullmatch(host))


def clean(theme):
    """A complete theme from what the settings hold: every key present, every
    value checked; unknown keys dropped, wrong values Dark Reader's default."""
    t = theme if isinstance(theme, dict) else {}
    out = dict(DEFAULTS)
    if t.get("mode") in (0, 1) and not isinstance(t.get("mode"), bool):
        out["mode"] = t["mode"]
    for key, (lo, hi) in RANGES.items():
        v = t.get(key)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and v == v:
            out[key] = int(round(min(hi, max(lo, v))))
    if isinstance(t.get("useFont"), bool):
        out["useFont"] = t["useFont"]
    if font_name_ok(t.get("fontFamily")):
        out["fontFamily"] = t["fontFamily"]
    v = t.get("textStroke")
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        for s in STROKES:
            if abs(v - s) < 1e-6:
                out["textStroke"] = s
    for key in COLOURS:
        c = colour(t.get(key))
        if c:
            out[key] = c
    v = t.get("scrollbarColor")
    if v in ("auto", "hidden") or colour(v):
        out["scrollbarColor"] = v if v in ("auto", "hidden") else colour(v)
    v = t.get("selectionColor")
    if v == "auto" or colour(v):
        out["selectionColor"] = "auto" if v == "auto" else colour(v)
    return out


def clean_sites(sites):
    """{host: theme} of the sites with their own colours, checked."""
    out = {}
    if isinstance(sites, dict):
        for host, theme in sites.items():
            if host_ok(host) and isinstance(theme, dict) and len(out) < SITES_MAX:
                out[host] = clean(theme)
    return out


def of(cfg, host=None):
    """(theme, own): the theme for host (its own when it has one) and whether it is its own."""
    sites = cfg.get("dark_site_themes") or {}
    if host and isinstance(sites, dict) and isinstance(sites.get(host), dict):
        return clean(sites[host]), True
    return clean(cfg.get("dark_theme")), False


_families = None


def system_fonts():
    """The font families of this computer whose names can go into a style sheet."""
    global _families
    if _families is None:
        from PyQt6.QtGui import QFontDatabase
        _families = sorted({f for f in QFontDatabase.families() if font_name_ok(f)}, key=str.lower)
    return _families


def for_page(theme, fonts=None):
    """What Dark Reader is given: the checked theme, the font quoted as a style
    sheet writes it, and only when it is one of the computer's fonts."""
    t = clean(theme)
    if t["useFont"]:
        names = system_fonts() if fonts is None else fonts
        if t["fontFamily"] in names:
            t["fontFamily"] = '"%s"' % t["fontFamily"]
        else:
            t["useFont"] = False
    if not t["useFont"]:
        t["fontFamily"] = '"%s"' % DEFAULTS["fontFamily"]
    return t
