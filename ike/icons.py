"""Icons: the chosen icon theme first, I.K.E.'s own glyphs when it has none.

Three kinds of choice (setting "icon_theme"):
  system          the desktop's icon theme (on Plasma nothing changes);
  theme:<name>    another icon theme installed on this computer;
  set:<name>      one of the sets shipped with I.K.E. (resources/icons/sets),
                  drawn in the text colour of the palette.
"""

from PyQt6.QtCore import QByteArray, QRectF, QSize, Qt
from PyQt6.QtGui import QGuiApplication, QIcon, QIconEngine, QPainter, QPalette, QPixmap

from .config import RES_DIR

_DIR = RES_DIR / "icons" / "fallback"
_SETS_DIR = RES_DIR / "icons" / "sets"
SETS = (("ike", "I.K.E."), ("lucide", "Lucide"), ("phosphor", "Phosphor"), ("phosphor-bold", "Phosphor Bold"),
        ("breeze", "Breeze (KDE)"))       # 1.1.24: KDE's own, built by tools/build-breeze-icons.py
_cache = {}
_system_theme = None
_set = None                 # name of the shipped set in use, if any


def installed_themes():
    """[(folder, shown name)] of the icon themes found on this computer."""
    from pathlib import Path
    found = {}
    for base in QIcon.themeSearchPaths():
        if base.startswith(":"):
            continue
        try:
            folders = sorted(Path(base).iterdir())
        except OSError:
            continue
        for d in folders:
            index = d / "index.theme"
            if d.name in found or d.name in ("hicolor", "default", "locolor") or not index.is_file():
                continue
            try:
                text = index.read_text("utf-8", "replace")[:20000]
            except OSError:
                continue
            if "Directories=" not in text or "\nHidden=true" in text:
                continue             # a cursor theme, or one not meant to be chosen
            name = d.name
            for line in text.splitlines():
                if line.startswith("Name="):
                    name = line[5:].strip() or d.name
                    break
            found[d.name] = name
    return sorted(found.items(), key=lambda kv: kv[1].lower())


def setup(config):
    """Apply the icon choice. Call once the application object exists."""
    global _system_theme, _set
    if _system_theme is None:
        _system_theme = QIcon.themeName()
    choice = str(config["icon_theme"] or "system")
    _set = None
    theme = _system_theme
    if choice.startswith("set:") and choice[4:] in dict(SETS):
        _set = choice[4:]
    elif choice.startswith("theme:") and choice[6:] in dict(installed_themes()):
        theme = choice[6:]
    if QIcon.themeName() != theme:
        QIcon.setThemeName(theme)
    _cache.clear()


def apply_scheme(config):
    """Light or dark interface, or whatever the system says (a colour theme
    counts as light or dark according to its background, see themes)."""
    from .themes import colour_scheme
    wanted = {"light": Qt.ColorScheme.Light, "dark": Qt.ColorScheme.Dark}.get(
        colour_scheme(config), Qt.ColorScheme.Unknown)
    try:
        hints = QGuiApplication.styleHints()
        if hints.colorScheme() != wanted or wanted == Qt.ColorScheme.Unknown:
            hints.setColorScheme(wanted)
    except AttributeError:               # Qt older than 6.8
        pass
    _cache.clear()


def _file(name, set_name):
    if set_name and set_name != "ike":
        path = _SETS_DIR / set_name / (name + ".svg")
        if path.is_file():
            return path
    return _DIR / (name + ".svg")


class _GlyphEngine(QIconEngine):
    """A shipped glyph drawn in the palette's colours at the moment it is
    painted, so it follows a change of interface colours without a restart."""

    ROLES = {
        QIcon.Mode.Normal: (QPalette.ColorGroup.Active, QPalette.ColorRole.ButtonText),
        QIcon.Mode.Active: (QPalette.ColorGroup.Active, QPalette.ColorRole.ButtonText),
        QIcon.Mode.Disabled: (QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText),
        QIcon.Mode.Selected: (QPalette.ColorGroup.Active, QPalette.ColorRole.HighlightedText),
    }

    def __init__(self, text):
        super().__init__()
        self.text = text
        self.pixmaps = {}

    def clone(self):
        return _GlyphEngine(self.text)

    def pixmap(self, size, mode, state):
        from PyQt6.QtSvg import QSvgRenderer
        group, role = self.ROLES.get(mode, self.ROLES[QIcon.Mode.Normal])
        colour = QGuiApplication.palette().color(group, role).name()
        key = (size.width(), size.height(), mode, colour)
        pm = self.pixmaps.get(key)
        if pm is None:
            if len(self.pixmaps) > 64:
                self.pixmaps.clear()
            pm = QPixmap(size)
            pm.fill(Qt.GlobalColor.transparent)
            renderer = QSvgRenderer(QByteArray(self.text.replace("currentColor", colour).encode()))
            if renderer.isValid():
                p = QPainter(pm)
                if mode == QIcon.Mode.Disabled:
                    p.setOpacity(0.45)
                renderer.render(p, QRectF(0, 0, size.width(), size.height()))
                p.end()
            self.pixmaps[key] = pm
        return pm

    def paint(self, painter, rect, mode, state):
        ratio = painter.device().devicePixelRatioF() if painter.device() else 1.0
        pm = self.pixmap(QSize(round(rect.width() * ratio), round(rect.height() * ratio)), mode, state)
        painter.drawPixmap(rect, pm)

    def availableSizes(self, mode=QIcon.Mode.Normal, state=QIcon.State.Off):
        return [QSize(s, s) for s in (16, 22, 32, 48)]


def bundled(name, set_name=None):
    """A shipped glyph for a theme icon name (null icon if there is none)."""
    key = (name, set_name)
    if key in _cache:
        return _cache[key]
    path = _file(name, set_name)
    try:
        from PyQt6.QtSvg import QSvgRenderer
        text = path.read_text("utf-8")
        valid = QSvgRenderer(QByteArray(text.encode())).isValid()
    except (ImportError, OSError):
        valid = False
    icon = QIcon(_GlyphEngine(text)) if valid else QIcon()
    _cache[key] = icon
    return icon


# where each icon asked for came from: names -> ("set" | "theme" | "own" |
# "shorter" | "qt" | "none", the name used). Following the system, every icon
# must come from the desktop's icon theme (1.1.22, the owner's rule):
# tests/test_icons.py reads this after opening every window and menu, in
# KDE Plasma, GNOME, Xfce, MATE, Cinnamon, LXQt and with Papirus.
seen = {}


class _SymbolicEngine(QIconEngine):
    """A theme's symbolic icon (a name ending in "-symbolic": one colour, made
    to be painted in the text colour, as GTK does) drawn in the palette's
    colours. Qt draws it as it is: Adwaita's dark grey on GNOME's dark
    windows, or MATE's light grey on light ones, could not be seen."""

    def __init__(self, icon):
        super().__init__()
        self.icon = icon
        self.pixmaps = {}

    def clone(self):
        return _SymbolicEngine(self.icon)

    def pixmap(self, size, mode, state):
        group, role = _GlyphEngine.ROLES.get(mode, _GlyphEngine.ROLES[QIcon.Mode.Normal])
        colour = QGuiApplication.palette().color(group, role)
        key = (size.width(), size.height(), mode, state, colour.rgba())
        pm = self.pixmaps.get(key)
        if pm is None:
            if len(self.pixmaps) > 64:
                self.pixmaps.clear()
            base = self.icon.pixmap(size, QIcon.Mode.Normal, state)
            pm = QPixmap(base.size())
            pm.fill(Qt.GlobalColor.transparent)
            p = QPainter(pm)
            if mode == QIcon.Mode.Disabled:
                p.setOpacity(0.45)
            p.drawPixmap(0, 0, base)
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
            p.fillRect(pm.rect(), colour)
            p.end()
            self.pixmaps[key] = pm
        return pm

    def paint(self, painter, rect, mode, state):
        ratio = painter.device().devicePixelRatioF() if painter.device() else 1.0
        pm = self.pixmap(QSize(round(rect.width() * ratio), round(rect.height() * ratio)), mode, state)
        painter.drawPixmap(rect, pm)

    def actualSize(self, size, mode, state):
        return self.icon.actualSize(size, mode, state)

    def availableSizes(self, mode=QIcon.Mode.Normal, state=QIcon.State.Off):
        return self.icon.availableSizes(mode, state)

    def iconName(self):
        return self.icon.name()


def _from_theme(name):
    """The theme's icon for exactly this name (or its variant: -rtl,
    -symbolic), not the shorter name Qt falls back to when the theme lacks it
    (Adwaita's "folder" for "folder-locked"); a null icon otherwise."""
    ic = QIcon.fromTheme(name)
    if ic.isNull():
        return ic
    found = ic.name()
    if found and found != name and not found.startswith(name + "-"):
        return QIcon()
    if name.endswith("-symbolic"):
        return QIcon(_SymbolicEngine(ic))
    return ic


def _plain_svg(path):
    """The text of an SVG file to be put in a page of I.K.E., its colour style
    dropped; "" when it cannot be read or holds anything but a drawing."""
    import re
    try:
        if not path.is_file() or path.stat().st_size > 64 * 1024:
            return ""
        text = path.read_text("utf-8")
    except (OSError, UnicodeDecodeError):
        return ""
    low = text.lower()
    if "<svg" not in low or re.search(r"<script|<foreignobject|\son\w+\s*=|javascript:|<!entity"
                                        r"|xlink:href\s*=\s*[\"'](?!#)|\shref\s*=\s*[\"'](?!#)", low):
        return ""             # only a plain drawing goes into the page
    text = re.sub(r"<\?xml[^>]*\?>", "", text)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.S | re.I)
    return text.strip()


def theme_svg(name, sizes=("22", "24", "symbolic", "32", "16")):
    """The text of the SVG for name that follows the icon choice, to be put in
    a page of I.K.E.: KDE's Breeze for the default choice and on Plasma, the
    chosen theme's or the chosen shipped set's otherwise (1.1.24, the owner's
    choice: KDE's Settings icon on the new tab page). Its colour style is
    dropped, so the icon takes the page's text colour. Where neither theme has
    it (Breeze not installed), the Breeze icon shipped with I.K.E.
    (resources/icons/sets/breeze); "" when there is none, or when the file
    holds anything but a drawing."""
    from pathlib import Path
    if _set:                  # a set shipped with I.K.E. was chosen: its own drawing
        try:
            return _file(name, _set).read_text("utf-8").strip()
        except OSError:
            return ""
    # the default ("system") and Plasma: KDE's Breeze first (the owner's choice);
    # another icon theme chosen in the Settings: that theme first
    chosen = QIcon.themeName() if _system_theme is not None and QIcon.themeName() != _system_theme else ""
    themes = [t for t in (chosen, "breeze", "breeze-dark", QIcon.themeName()) if t]
    for theme in dict.fromkeys(themes):
        for base in QIcon.themeSearchPaths():
            if base.startswith(":"):
                continue
            for size in sizes:
                text = _plain_svg(Path(base) / theme / "actions" / size / (name + ".svg"))
                if text:
                    return text
    return _plain_svg(_SETS_DIR / "breeze" / (name + ".svg"))


_found = {}          # (names, standard, set, theme): (icon, where it came from) (1.1.23)


def themed(names, standard=None):
    """The icon for the first usable name: shipped set (if chosen), theme,
    own glyph, the theme's shorter name, Qt.

    The answer is kept for the same names, icon set and desktop theme
    (1.1.23: the window asked 130 times at its start, many for the same
    names, each time looking through the theme)."""
    if isinstance(names, str):
        names = (names,)
    names = tuple(names)
    key = (names, standard, _set, QIcon.themeName(), QIcon.fallbackThemeName())
    got = _found.get(key)
    if got is not None:
        seen[names] = got[1]
        return got[0]
    ic = _themed(names, standard)
    if standard is None or seen.get(names, ("",))[0] != "qt":
        # Qt's own icons follow the widget style, which can change: not kept
        _found[key] = (ic, seen[names])
    return ic


def _themed(names, standard):
    if _set is not None:
        for name in names:
            ic = bundled(name, _set)
            if not ic.isNull():
                seen[names] = ("set", name)
                return ic
    for name in names:
        ic = _from_theme(name)
        if not ic.isNull():
            seen[names] = ("theme", name)
            return ic
    for last in (None, "lucide"):        # own glyphs, then the complete shipped set
        for name in names:
            ic = bundled(name, last)
            if not ic.isNull():
                seen[names] = ("own", name)
                return ic
    for name in names:                   # a more general icon of the theme (before 1.1.22 the first choice)
        ic = QIcon.fromTheme(name)
        if not ic.isNull():
            seen[names] = ("shorter", ic.name() or name)
            return ic
    if standard is not None:
        from PyQt6.QtWidgets import QApplication
        seen[names] = ("qt", str(standard))
        return QApplication.style().standardIcon(standard)
    seen[names] = ("none", "")
    return QIcon()
