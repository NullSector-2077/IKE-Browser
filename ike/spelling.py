"""Spell checking while typing in a page (Unreleased; Settings -> Language
and translation).

The engine underlines the misspelled words of text fields and editable parts
of a page, and the page's right-click menu offers the corrections (that part
was there already, contextmenu.py). Everything happens on this computer, with
Hunspell's dictionaries: nothing about what is typed is sent anywhere (unlike
the "enhanced" spell check of some browsers), and the page cannot read which
words were underlined.

The dictionaries are the engine's own `.bdic` files. On Arch Linux and
CachyOS each `hunspell-*` package installs them for Qt WebEngine
(`hunspell-it`: `/usr/share/qt6/qtwebengine_dictionaries/it_IT.bdic`), so no
conversion is needed. The engine reads one folder, chosen before it starts:
`QTWEBENGINE_DICTIONARIES_PATH` when it is set, otherwise Qt's own data folder.

The languages checked follow the interface: the system's language and
I.K.E.'s (`it_IT`, `it`), each matched with an installed dictionary of the
same language; English (`en_US`) when none of them has one. A list in
`spellcheck_langs` (dictionary names) is used instead when the user set it.
"""

import os
from pathlib import Path

MAX_LANGS = 3


def dictionary_dir():
    """The folder the engine reads its dictionaries from."""
    env = os.environ.get("QTWEBENGINE_DICTIONARIES_PATH")
    if env:
        return Path(env)
    try:
        from PyQt6.QtCore import QLibraryInfo
        return Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.DataPath)) / "qtwebengine_dictionaries"
    except Exception:
        return Path("/usr/share/qt6/qtwebengine_dictionaries")


def installed(folder=None):
    """The names of the installed dictionaries ("en_US", "it_IT"...), sorted."""
    folder = dictionary_dir() if folder is None else Path(folder)
    try:
        return sorted(p.stem for p in folder.iterdir()
                      if p.suffix == ".bdic" and p.is_file() and p.stat().st_size > 0)
    except OSError:
        return []


def _norm(tag):
    return str(tag or "").strip().replace("-", "_").split(".")[0].split("@")[0]


def choose(available, wanted, chosen=()):
    """The dictionaries to use: `chosen` (the user's list) when any of them is
    installed, otherwise the best match for each of `wanted` (language tags of
    the system and of the interface, best first), otherwise English."""
    avail = list(available)
    picked = [d for d in chosen if d in avail]
    if picked:
        return picked[:MAX_LANGS]
    lower = {d.lower(): d for d in avail}
    out = []
    for tag in wanted:
        tag = _norm(tag)
        if not tag:
            continue
        lang = tag.split("_")[0].lower()
        exact = lower.get(tag.lower())
        same = [d for d in avail if d.lower().split("_")[0] == lang and "-" not in d]
        # it -> it_IT before it_CH; en -> en_US before en_GB
        main = next((d for d in same if d.lower() == "%s_%s" % (lang, lang)), None)
        best = exact or main or ("en_US" if lang == "en" and "en_US" in avail else None) \
            or (same[0] if same else None)
        if best and best not in out:
            out.append(best)
    if not out and "en_US" in avail:
        out.append("en_US")
    return out[:MAX_LANGS]


def wanted_languages():
    """The system's language and I.K.E.'s interface language, best first."""
    tags = []
    try:
        from PyQt6.QtCore import QLocale
        tags.append(QLocale.system().name())
    except Exception:
        pass
    try:
        from .i18n import current
        tags.append(current())
    except Exception:
        pass
    tags.append(os.environ.get("LANG", ""))
    return tags


def languages(cfg):
    """The dictionaries the profiles check with now ([] when off or none is installed)."""
    if not cfg.get("spellcheck", True):
        return []
    chosen = cfg.get("spellcheck_langs") or []
    if not isinstance(chosen, list):
        chosen = []
    return choose(installed(), wanted_languages(), [str(x) for x in chosen])


def apply(profile, cfg):
    """Turn the engine's spell checking on or off for one profile."""
    langs = languages(cfg)
    try:
        if langs:
            if list(profile.spellCheckLanguages()) != langs:
                profile.setSpellCheckLanguages(langs)
            if not profile.isSpellCheckEnabled():
                profile.setSpellCheckEnabled(True)
        elif profile.isSpellCheckEnabled():
            profile.setSpellCheckEnabled(False)
    except (AttributeError, RuntimeError):
        pass
