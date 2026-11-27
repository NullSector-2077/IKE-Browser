"""The launcher's icons follow the version in use (1.1.27).

The package installs I.K.E.'s icons under /usr/share/icons (the menu, the
task bar, the application launcher), and a self-update never touches /usr:
until 1.1.27 a new logo reached the windows only, and the menu kept the old
one until the package was installed by hand. That breaks the project's rule
that every release reaches every user by itself.

Now, a few seconds after each start, I.K.E. copies the icons of the version in
use into the user's own icon folder (~/.local/share/icons/hicolor, or under
$XDG_DATA_HOME), which every desktop reads before /usr/share/icons: the same
files the package installs (the sizes of the hicolor theme and the scalable
one). Only a file that differs is written, nothing at all when they are the
same; the folder's time is touched so desktops that keep a cache read them
again (Plasma shows the new icon from the next login at the latest). Nothing
else is written; a failure (a read-only home) changes nothing.
"""

import os
from pathlib import Path

from .config import RES_DIR

# the hicolor theme's sizes the package installs (PKGBUILD)
SIZES = (16, 22, 24, 32, 48, 64, 128, 256, 512, 1024)
NAME = "ike-browser"


def icons_dir(env=None):
    env = os.environ if env is None else env
    base = env.get("XDG_DATA_HOME") or str(Path(env.get("HOME") or Path.home()) / ".local" / "share")
    return Path(base) / "icons" / "hicolor"


def wanted(res=RES_DIR):
    """{path under hicolor: source file} of the version in use."""
    out = {}
    for size in SIZES:
        src = res / "icons" / ("%s-%d.png" % (NAME, size))
        if src.is_file():
            out["%dx%d/apps/%s.png" % (size, size, NAME)] = src
    svg = res / "ike.svg"
    if svg.is_file():
        out["scalable/apps/%s.svg" % NAME] = svg
    return out


def installed(env=None):
    """Is I.K.E. installed as an application here (its desktop entry found)?
    A copy run from its sources writes nothing."""
    env = os.environ if env is None else env
    home = env.get("XDG_DATA_HOME") or str(Path(env.get("HOME") or Path.home()) / ".local" / "share")
    dirs = [home] + (env.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share").split(":")
    return any(d and (Path(d) / "applications" / (NAME + ".desktop")).is_file() for d in dirs)


def sync(res=RES_DIR, env=None):
    """Write the icons that differ; returns how many were written."""
    if not installed(env):
        return 0
    root = icons_dir(env)
    written = 0
    for rel, src in wanted(res).items():
        dest = root / rel
        try:
            data = src.read_bytes()
            try:
                if dest.stat().st_size == len(data) and dest.read_bytes() == data:
                    continue
            except OSError:
                pass
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.with_name(dest.name + ".ike-tmp")
            tmp.write_bytes(data)
            os.replace(tmp, dest)
            written += 1
        except OSError:
            continue
    if written:
        try:
            os.utime(root)              # the icon theme changed: desktops with a cache read it again
        except OSError:
            pass
    return written
