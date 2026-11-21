"""The fonts the engine may use at the global levels Strict and Maximum (1.1.21).

fingerprint.js hides the computer's fonts from a page's scripts (maskFonts,
fontcheck.py), but two ways around it were out of a script's reach: a style
sheet's own `@font-face { src: local("Some Font") }` and the workers loaded
from an address, where no script of I.K.E.'s runs (fingerprinting audit,
"Known limits"; owner's decision: in 1.1.21). Only the engine can close
them, so at Strict and Maximum the engine sees only the font families most
Linux computers have: DejaVu, Liberation (which answer for Arial, Times New
Roman and Courier New), Noto (with emoji and CJK), Cantarell, and the usual
CJK families of Arch (Source Han, WenQuanYi). A font installed by the user,
or any other package's font, cannot be found or measured by a page.

How: fontconfig, the library that finds fonts for both the engine and Qt,
reads its configuration from FONTCONFIG_FILE. I.K.E. writes a file that
includes the system's own configuration and adds a <selectfont> rule:
every font file is rejected by its extension, the families above accepted
by their file name (fontconfig's globs must start with "/", and a rule that
matched directories would keep fontconfig from even scanning them).

What it changes:
- Read at start, like the engine's language at Maximum: a change of level
  applies after a restart.
- I.K.E.'s own interface also sees only these fonts (one process). A desktop
  whose interface font is one of them (Noto Sans on KDE, Cantarell on GNOME)
  sees no change.
- When none of these families is installed the rule is not written: the
  pages would have no font at all.
- The programs I.K.E. starts itself (another profile, the restart) get the
  user's own configuration back (child_env); a file opened from the
  downloads with the desktop's program inherits it (Qt starts xdg-open).
"""

import os
from pathlib import Path

ON_LEVELS = ("strict", "maximum")
SYSTEM_FONTS = ("/usr/share/fonts", "/usr/local/share/fonts")
# the families: the start of their file names (fonts of the Arch packages
# ttf-dejavu, ttf-liberation, noto-fonts*, cantarell-fonts,
# adobe-source-han-*, wqy-*)
ALLOWED = ("DejaVu", "Liberation", "Noto", "Cantarell", "SourceHan", "wqy-")
# the font files fontconfig reads, by extension (a file with any other
# extension, if fontconfig reads it, is not rejected)
EXTENSIONS = ("ttf", "otf", "ttc", "otc", "pfa", "pfb", "pcf", "pcf.gz", "pcf.Z", "bdf", "bdf.gz",
              "pfr", "t42", "dfont", "woff", "woff2", "snf", "TTF", "OTF", "TTC", "OTC", "PFA", "PFB",
              "Ttf", "Otf")
ENV = "FONTCONFIG_FILE"
FROM = "IKE_FONTCONFIG_FROM"      # the user's own FONTCONFIG_FILE ("" none) while I.K.E.'s is set


def _xml(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def system_config(environ=None):
    """The configuration fontconfig would read without I.K.E.'s, or None."""
    environ = os.environ if environ is None else environ
    own = environ.get(ENV)
    if own:
        return own if os.path.isfile(own) else None
    for d in [p for p in environ.get("FONTCONFIG_PATH", "").split(":") if p] + ["/etc/fonts"]:
        path = os.path.join(d, "fonts.conf")
        if os.path.isfile(path):
            return path
    return None


def any_allowed(dirs=SYSTEM_FONTS):
    """True when at least one font file of the allowed families is installed."""
    for top in dirs:
        for _root, _dirs, files in os.walk(top):
            if any(f.startswith(ALLOWED) for f in files):
                return True
    return False


def config_text(include):
    lines = ['<?xml version="1.0"?>',
             '<!DOCTYPE fontconfig SYSTEM "urn:fontconfig:fonts.dtd">',
             "<!-- Written by I.K.E. at every start at the levels Strict and Maximum",
             "     (ike/fontallow.py): the system's configuration, and only the most common",
             "     font families for the engine. Not read at the other levels. -->",
             "<fontconfig>",
             '  <include ignore_missing="no">%s</include>' % _xml(include),
             "  <selectfont>",
             "    <rejectfont>"]
    lines += ["      <glob>/*.%s</glob>" % e for e in EXTENSIONS]
    lines += ["    </rejectfont>", "    <acceptfont>"]
    lines += ["      <glob>/*/%s*</glob>" % _xml(a) for a in ALLOWED]
    lines += ["    </acceptfont>", "  </selectfont>", "</fontconfig>", ""]
    return "\n".join(lines)


def restore(environ=None):
    """Give back the user's own FONTCONFIG_FILE (I.K.E.'s may have come from
    the I.K.E. that started this one)."""
    environ = os.environ if environ is None else environ
    if FROM in environ:
        orig = environ.pop(FROM)
        if orig:
            environ[ENV] = orig
        else:
            environ.pop(ENV, None)


def child_env(environ):
    """A copy of `environ` for a program I.K.E. starts: the user's fonts."""
    env = dict(environ)
    restore(env)
    return env


def apply(level, config_dir, environ=None, dirs=SYSTEM_FONTS):
    """At the global levels Strict and Maximum, point fontconfig at I.K.E.'s
    configuration (before Qt or the engine reads it). Returns its path, or
    None when the fonts stay as they are."""
    environ = os.environ if environ is None else environ
    restore(environ)
    if level not in ON_LEVELS:
        return None
    include = system_config(environ)
    if include is None or not any_allowed(dirs):
        return None
    path = Path(config_dir) / "fonts-allowed.conf"
    text = config_text(include)
    try:
        if not path.is_file() or path.read_text("utf-8") != text:
            tmp = path.with_suffix(".tmp")
            tmp.write_text(text, "utf-8")
            os.replace(tmp, path)
    except OSError:
        return None
    environ[FROM] = environ.get(ENV, "")
    environ[ENV] = str(path)
    return path
