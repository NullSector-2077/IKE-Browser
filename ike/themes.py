"""Interface themes: colours and font of the browser's own windows.

The choice is stored in config["ui_scheme"]:
  "system"        follow the desktop (default: nothing is changed)
  "light"/"dark"  the desktop style in its light or dark variant
  "theme:<key>"   one of the ready-made themes below
  "user:<name>"   a theme saved by the user in config["ui_themes"]

A theme is a dict with five colours and an optional font:
  background, text, accent, toolbar, tabs   ("#rrggbb")
  font_family ("" = system font), font_size (0 = system size, in points)
Web pages are not affected (page dark mode is a separate setting).
"""

from PyQt6.QtGui import QColor, QFont, QGuiApplication, QPalette
from PyQt6.QtWidgets import QApplication

from .i18n import T

COLOURS = ("background", "text", "accent", "toolbar", "tabs")

# names are translated when shown (see names())
BUILTIN = {
    # the theme with a look of its own (cut corners, luminous lines: see cyber.py)
    "cyber": {"name": "I.K.E. Cyber", "background": "#070b14", "text": "#e6f1ff", "accent": "#2be4f5",
              "toolbar": "#121c2e", "tabs": "#0a101c", "look": "cyber"},
    "ike": {"name": "I.K.E.", "background": "#0f1d2b", "text": "#e6f4ff", "accent": "#19c3e6",
            "toolbar": "#0a1622", "tabs": "#12324a"},
    "night": {"name": "Night", "background": "#1f2023", "text": "#e4e4e7", "accent": "#7aa2f7",
              "toolbar": "#18191b", "tabs": "#2a2b30"},
    "paper": {"name": "Paper", "background": "#f7f4ed", "text": "#2b2a27", "accent": "#b5651d",
              "toolbar": "#ece6d9", "tabs": "#e2dac9"},
    "forest": {"name": "Forest", "background": "#1c2620", "text": "#e3ece4", "accent": "#6fbf73",
               "toolbar": "#151d18", "tabs": "#26342b"},
    "contrast": {"name": "High contrast", "background": "#000000", "text": "#ffffff",
                 "accent": "#ffd400", "toolbar": "#000000", "tabs": "#000000"},
}

_original = {}          # the desktop's palette and font, kept while a theme is in use


def names():
    """[(key, label)] of the ready-made themes."""
    return [(k, T(v["name"])) for k, v in BUILTIN.items()]


def current(config):
    """The theme dict in use, or None (system / light / dark)."""
    choice = config["ui_scheme"] or "system"
    if choice == "theme:cyber":
        theme = dict(BUILTIN["cyber"])
        accent = config.data.get("cyber_accent") if hasattr(config, "data") else ""
        if isinstance(accent, str) and accent.startswith("#") and QColor.isValidColorName(accent):
            theme["accent"] = accent
        return theme
    if choice.startswith("theme:"):
        return BUILTIN.get(choice[6:])
    if choice.startswith("user:"):
        theme = (config["ui_themes"] or {}).get(choice[5:])
        return theme if valid(theme) else None
    return None


def is_cyber(theme):
    """Does this theme have the Cyber look (shapes and lines of its own)?"""
    return isinstance(theme, dict) and theme.get("look") == "cyber"


def valid(theme):
    return isinstance(theme, dict) and all(QColor.isValidColorName(str(theme.get(k, "")))
                                           for k in COLOURS)


def is_dark(theme):
    return QColor(theme["background"]).lightnessF() < 0.5


def _mix(a, b, t):
    a, b = QColor(a), QColor(b)
    return QColor(round(a.red() + (b.red() - a.red()) * t),
                  round(a.green() + (b.green() - a.green()) * t),
                  round(a.blue() + (b.blue() - a.blue()) * t))


def _on(colour):
    """Black or white, whichever reads better on colour."""
    c = QColor(colour)
    light = (0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()) / 255
    return QColor("#000000") if light > 0.55 else QColor("#ffffff")


def palette(theme, window=None, list_base=False):
    """A complete QPalette from the five colours of a theme.

    window: paint the Window/Button roles with this colour instead of the
    background (used for the toolbars and the tabs); list_base: the same colour
    for the Base role too (the vertical tab list)."""
    bg = QColor(window or theme["background"])
    text = QColor(theme["text"])
    accent = QColor(theme["accent"])
    dark = QColor(theme["background"]).lightnessF() < 0.5
    # text fields: a little lighter than the window on dark themes, near white on light ones
    base = _mix(theme["background"], theme["text"], 0.09) if dark \
        else _mix(theme["background"], "#ffffff", 0.6)
    if list_base:
        base = bg
    button = _mix(bg, text, 0.08)
    pal = QPalette()
    R, G = QPalette.ColorRole, QPalette.ColorGroup
    for group in (G.Active, G.Inactive, G.Disabled):
        dim = group == G.Disabled
        fg = _mix(text, bg, 0.5) if dim else text
        roles = {
            R.Window: bg, R.WindowText: fg, R.Base: base, R.AlternateBase: _mix(base, text, 0.04),
            R.Text: fg, R.Button: button, R.ButtonText: fg, R.BrightText: _on(accent),
            R.Highlight: _mix(accent, bg, 0.5) if dim else accent, R.HighlightedText: _on(accent),
            R.ToolTipBase: base, R.ToolTipText: text, R.PlaceholderText: _mix(text, bg, 0.45),
            R.Link: accent, R.LinkVisited: _mix(accent, text, 0.35),
            R.Light: _mix(button, "#ffffff", 0.3), R.Midlight: _mix(button, "#ffffff", 0.15),
            R.Mid: _mix(button, text, 0.25), R.Dark: _mix(button, "#000000", 0.35),
            R.Shadow: QColor("#000000"),
        }
        try:
            roles[R.Accent] = accent
        except AttributeError:            # Qt older than 6.6
            pass
        for role, colour in roles.items():
            pal.setColor(group, role, colour)
    return pal


def font(theme):
    f = QFont(_original.get("font") or QApplication.font())
    if theme.get("font_family"):
        f.setFamily(theme["font_family"])
    if int(theme.get("font_size") or 0) > 0:
        f.setPointSize(int(theme["font_size"]))
    return f


def apply(config, preview=None):
    """Apply the interface theme of config (or the preview theme) to the whole
    application. With "Follow the system" nothing is touched unless a theme
    was in use before, in which case the desktop's palette and font return."""
    app = QApplication.instance()
    theme = preview if preview is not None else current(config)
    if preview is None:
        from . import effects
        for w in app.topLevelWidgets():          # the bars of each window: the new look comes in softly
            if hasattr(w, "apply_theme") and w.isVisible():
                effects.cross_fade([w.menuBar(), getattr(w, "nav", None), getattr(w, "htab_row", None),
                                    getattr(w, "vtab_panel", None), getattr(w, "bookbar", None)], config)
    if theme is not None:
        if not _original:
            _original["palette"] = QPalette(app.palette())
            _original["font"] = QFont(app.font())
        _scheme(dark=is_dark(theme))
        app.setPalette(palette(theme))
        app.setFont(font(theme))
    else:
        if _original:
            app.setPalette(_original.pop("palette"))
            app.setFont(_original.pop("font"))
        from . import icons
        icons.apply_scheme(config)
    for w in app.topLevelWidgets():
        if hasattr(w, "apply_theme"):
            w.apply_theme(theme)


def _scheme(dark):
    try:
        from PyQt6.QtCore import Qt
        QGuiApplication.styleHints().setColorScheme(
            Qt.ColorScheme.Dark if dark else Qt.ColorScheme.Light)
    except AttributeError:               # Qt older than 6.8
        pass


def colour_scheme(config):
    """"light" / "dark" / "system" for icons.apply_scheme."""
    theme = current(config)
    if theme is not None:
        return "dark" if is_dark(theme) else "light"
    choice = config["ui_scheme"]
    return choice if choice in ("light", "dark") else "system"


def style_window(win, theme):
    """Toolbars and tabs of a browser window in the theme's colours."""
    bars = [win.nav, win.menuBar(), getattr(win, "bookbar", None), getattr(win, "custom_bar", None)]
    tabs = [getattr(win, n, None) for n in ("htab_row", "tabbar", "vtab_panel", "vtabs")]
    for widgets, key in ((bars, "toolbar"), (tabs, "tabs")):
        for w in widgets:
            if w is None:
                continue
            if theme is None:
                w.setPalette(QPalette())          # back to the inherited colours
                if w is not win.vtab_panel:
                    w.setAutoFillBackground(False)
            else:
                w.setPalette(palette(theme, window=theme[key], list_base=w is win.vtabs))
                w.setAutoFillBackground(True)
