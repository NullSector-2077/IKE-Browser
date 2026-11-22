"""The Linux desktops I.K.E. is tested in when it follows the system (1.1.22).

Each desktop is Qt's platform theme for it (the part of Qt that reads the
desktop's icons, colours and fonts) with the desktop's defaults as Arch
Linux packages them, written into the test's empty home folder:

  kde            KDE Plasma: whatever the computer's kdeglobals says (the
                 Arch job writes Breeze Dark), icons Breeze
  plasma-papirus, plasma-papirus-dark
                 KDE Plasma with Papirus (Breeze Light colours) or
                 Papirus-Dark (Breeze Dark colours), common on CachyOS
  gnome, gnome-dark
                 GNOME: Qt's GTK theme (gtk3), Adwaita icons and colours,
                 Adwaita Sans 11; dark as GTK_THEME=Adwaita:dark
  xfce, xfce-dark
                 Xfce: gtk3, xfce4-settings' defaults (icons "elementary",
                 GTK theme Adwaita, Sans 10); dark with Adwaita's dark variant
  mate           MATE: gtk3, mate-desktop's default icons "menta" (from
                 mate-icon-theme); its GTK theme Menta (mate-themes) is
                 replaced by Adwaita
  cinnamon       Cinnamon: gtk3; Arch's cinnamon package sets the icons to
                 Papirus (its schema override), the GTK theme Mint-Y is not
                 in Arch's repositories: Adwaita
  lxqt, lxqt-dark
                 LXQt: its own platform theme (lxqt-qtplugin) with
                 lxqt-session's defaults (icons Breeze, Fusion, Sans 11) and
                 the "Light" or "Dark" palette of lxqt-themes
  qt             no desktop: Qt without a platform theme

IKE_TEST_DESKTOP=<name> runs any test of the browser in that desktop
(conftest.run_ike), e.g. the text-fit test in GNOME. The GTK theme needs an X
display: one is started with Xvfb when there is none.
"""

import atexit
import ctypes
import os
import shutil
import subprocess
from pathlib import Path

ICON_DIRS = [Path("/usr/share/icons"), Path("/usr/local/share/icons")]
COLOR_SCHEMES = Path("/usr/share/color-schemes")

# lxqt-session 2.5's /usr/share/lxqt/lxqt.conf (the defaults of a new user)
LXQT_CONF = """[General]
theme=Clearlooks
icon_theme=breeze
single_click_activate=false
tool_button_style=ToolButtonTextBesideIcon
palette_override=true

[Qt]
font="Sans,11,-1,5,50,0,0,0,0,0,0,0,0,0,0,1"
doubleClickInterval=400
style=Fusion
wheelScrollLines=3
"""
# lxqt-themes 2.5's palettes "Light" and "Dark" (/usr/share/lxqt/palettes)
LXQT_PALETTES = {
    "light": {"base_color": "#ffffff", "highlight_color": "#3c8ce6", "highlighted_text_color": "#ffffff",
              "link_color": "#0000ff", "link_visited_color": "#ff00ff", "text_color": "#000000",
              "tooltip_base_color": "#fffeed", "tooltip_text_color": "#000000",
              "window_color": "#efefef", "window_text_color": "#000000"},
    "dark": {"base_color": "#282828", "highlight_color": "#640b0c", "highlighted_text_color": "#ebfdff",
             "link_color": "#8c9bff", "link_visited_color": "#ffb3f7", "text_color": "#b8b8b8",
             "tooltip_base_color": "#232323", "tooltip_text_color": "#b8b8b8",
             "window_color": "#232323", "window_text_color": "#e1e6e6"},
}

# name: platform theme, the icon theme it must report (None: the computer's
# own KDE settings), XDG_CURRENT_DESKTOP, and its settings
DESKTOPS = {
    "kde": {"platform": "kde", "icons": None, "desktop": "KDE"},
    "plasma-papirus": {"platform": "kde", "icons": "Papirus", "desktop": "KDE", "colours": "BreezeLight"},
    "plasma-papirus-dark": {"platform": "kde", "icons": "Papirus-Dark", "desktop": "KDE",
                            "colours": "BreezeDark"},
    "gnome": {"platform": "gtk3", "icons": "Adwaita", "desktop": "GNOME", "font": "Adwaita Sans 11"},
    "gnome-dark": {"platform": "gtk3", "icons": "Adwaita", "desktop": "GNOME", "font": "Adwaita Sans 11",
                   "dark": True},
    "xfce": {"platform": "gtk3", "icons": "elementary", "desktop": "XFCE", "font": "Sans 10"},
    "xfce-dark": {"platform": "gtk3", "icons": "elementary", "desktop": "XFCE", "font": "Sans 10",
                  "dark": True},
    "mate": {"platform": "gtk3", "icons": "menta", "desktop": "MATE", "font": "Sans 10"},
    "cinnamon": {"platform": "gtk3", "icons": "Papirus", "desktop": "X-Cinnamon", "font": "Adwaita Sans 11"},
    "lxqt": {"platform": "lxqt", "icons": "breeze", "desktop": "LXQt", "palette": "light"},
    "lxqt-dark": {"platform": "lxqt", "icons": "breeze", "desktop": "LXQt", "palette": "dark"},
    "qt": {"platform": "", "icons": "", "desktop": ""},
}
PLUGINS = {"kde": "KDEPlasmaPlatformTheme6.so", "gtk3": "libqgtk3.so", "lxqt": "libqtlxqt.so"}


class Unavailable(Exception):
    """The desktop cannot be tried on this computer (the reason is its text)."""


def theme_dir(name):
    for base in ICON_DIRS:
        if (base / name / "index.theme").is_file():
            return base / name
    return None


def chain(theme):
    """The icon themes looked into for theme, in the order of the icon theme
    specification: the theme, the themes it inherits (Inherits=, depth
    first), hicolor last."""
    order = []

    def walk(name):
        d = theme_dir(name)
        if name in order or name == "hicolor" or d is None:
            return
        order.append(name)
        for line in (d / "index.theme").read_text("utf-8", "replace").splitlines():
            if line.startswith("Inherits="):
                for parent in line[9:].split(","):
                    if parent.strip():
                        walk(parent.strip())
                break
    walk(theme)
    return order + ["hicolor"]


_names = {}


def names(theme):
    """Every icon name the theme itself has (its files and links)."""
    if theme not in _names:
        found = set()
        for base in ICON_DIRS:
            d = base / theme
            if d.is_dir():
                for f in d.rglob("*"):
                    if f.suffix in (".svg", ".png", ".xpm") and (f.is_file() or f.is_symlink()):
                        found.add(f.name.rsplit(".", 1)[0])
        _names[theme] = found
    return _names[theme]


def _plugins_dir():
    from PyQt6.QtCore import QLibraryInfo
    return Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.PluginsPath)) / "platformthemes"


_display = []


def display():
    """An X display for GTK: the computer's, or one started with Xvfb."""
    if os.environ.get("DISPLAY"):
        return os.environ["DISPLAY"]
    if _display:
        return _display[0]
    if not shutil.which("Xvfb"):
        return None
    r, w = os.pipe()
    proc = subprocess.Popen(["Xvfb", "-displayfd", str(w), "-screen", "0", "1920x1200x24", "-nolisten", "tcp"],
                            pass_fds=(w,), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    os.close(w)
    with os.fdopen(r) as f:
        number = f.readline().strip()
    if not number:
        proc.kill()
        return None
    atexit.register(proc.kill)
    _display.append(":" + number)
    return _display[0]


def available(name):
    """Raise Unavailable when the desktop cannot be tried here."""
    d = DESKTOPS[name]
    if d["platform"] and name != "kde":
        if not Path("/etc/arch-release").exists():
            raise Unavailable("the desktops are tested as Arch Linux packages them (not Arch here)")
    if d["platform"] and not (_plugins_dir() / PLUGINS[d["platform"]]).exists():
        raise Unavailable("Qt's %s platform theme is not installed" % d["platform"])
    if d["icons"] and theme_dir(d["icons"]) is None:
        raise Unavailable("the %s icon theme is not installed" % d["icons"])
    if d.get("colours") and not (COLOR_SCHEMES / (d["colours"] + ".colors")).is_file():
        raise Unavailable("KDE's %s colours are not installed" % d["colours"])
    if d["platform"] == "gtk3":
        try:
            ctypes.CDLL("libgtk-3.so.0")
        except OSError:
            raise Unavailable("GTK 3 is not installed") from None


def prepare(name, home):
    """Write the desktop's settings into the home folder of a test; the
    environment variables to add. Raises Unavailable."""
    available(name)
    d = DESKTOPS[name]
    config = Path(home) / ".config"
    config.mkdir(parents=True, exist_ok=True)
    env = {"QT_QPA_PLATFORMTHEME": d["platform"], "XDG_CURRENT_DESKTOP": d["desktop"]}
    if d["platform"] == "gtk3":
        shown = display()
        if not shown:
            raise Unavailable("GTK needs an X display (install xorg-server-xvfb)")
        env["DISPLAY"] = shown
        (config / "gtk-3.0").mkdir(exist_ok=True)
        (config / "gtk-3.0" / "settings.ini").write_text(
            "[Settings]\ngtk-theme-name=Adwaita\ngtk-icon-theme-name=%s\ngtk-font-name=%s\n"
            % (d["icons"], d["font"]), "utf-8")
        if d.get("dark"):
            env["GTK_THEME"] = "Adwaita:dark"
    elif d["platform"] == "lxqt":
        (config / "lxqt").mkdir(exist_ok=True)
        palette = "".join("%s=%s\n" % kv for kv in LXQT_PALETTES[d["palette"]].items())
        (config / "lxqt" / "lxqt.conf").write_text(
            LXQT_CONF.replace("icon_theme=breeze", "icon_theme=" + d["icons"]) + "\n[Palette]\n" + palette,
            "utf-8")
    elif d.get("colours"):
        scheme = (COLOR_SCHEMES / (d["colours"] + ".colors")).read_text("utf-8")
        (config / "kdeglobals").write_text(
            scheme + "\n[General]\nColorScheme=%s\n\n[KDE]\nwidgetStyle=Breeze\n\n[Icons]\nTheme=%s\n"
            % (d["colours"], d["icons"]), "utf-8")
    return env
