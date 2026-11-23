"""The web engine's security advisory: "Update the system" (1.1.24).

The web engine (Arch's qt6-webengine) is updated by the system, not by I.K.E.
When a security problem of the engine is published and fixed in a newer
version, the signed update information that I.K.E. already reads once a day
(updater.py) can carry a small field, written by the release tool
(tools/make-release.py, from data/engine-advisory.json when that file
exists):

    "engine_advisory": {"id": "CVE-2026-0000",
                        "qtwebengine": "6.12.1",
                        "chromium_security": "158.0.7444.59"}

``qtwebengine`` is the first Qt WebEngine version with the fix and
``chromium_security`` the first Chromium security patch level with it
(qWebEngineChromiumSecurityPatchVersion); either may be missing. When the
installed engine is older than every version given, I.K.E. says once per
session, calmly: update the system (sudo pacman -Syu). No other request is
made, and the field is read only from information whose signature was
verified. Without the field (every release until one names an advisory)
nothing is shown; a field that is not exactly of this form is ignored.
"""

import re

FIELDS = ("qtwebengine", "chromium_security")
_VERSION = re.compile(r"\d{1,5}(\.\d{1,6}){0,3}")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:+-]{0,79}")
COMMAND = "sudo pacman -Syu"


def vtuple(v):
    if not isinstance(v, str) or not _VERSION.fullmatch(v):
        return None
    return tuple(int(x) for x in v.split("."))


def clean(data):
    """The advisory as I.K.E. uses it, or None when `data` is not one."""
    if not isinstance(data, dict):
        return None
    ident = data.get("id")
    if not isinstance(ident, str) or not _ID.fullmatch(ident):
        return None
    out = {"id": ident}
    for f in FIELDS:
        if f in data:
            if vtuple(data[f]) is None:
                return None
            out[f] = data[f]
    return out if len(out) > 1 else None


def installed():
    """The versions of the engine in use: {field: "x.y.z"} (those Qt tells)."""
    out = {}
    try:
        from PyQt6.QtWebEngineCore import qWebEngineVersion
        out["qtwebengine"] = qWebEngineVersion()
    except (ImportError, AttributeError):
        pass
    try:
        from PyQt6.QtWebEngineCore import qWebEngineChromiumSecurityPatchVersion
        out["chromium_security"] = qWebEngineChromiumSecurityPatchVersion()
    except (ImportError, AttributeError):
        pass
    return out


def applies(adv, have=None):
    """Is the installed engine older than every fixed version the advisory names?"""
    adv = clean(adv)
    if adv is None:
        return False
    have = installed() if have is None else have
    compared = False
    for f in FIELDS:
        if f not in adv:
            continue
        mine = vtuple(have.get(f))
        if mine is None:
            continue                    # not known here: says nothing either way
        compared = True
        fixed = vtuple(adv[f])
        n = max(len(mine), len(fixed))
        if mine + (0,) * (n - len(mine)) >= fixed + (0,) * (n - len(fixed)):
            return False                # this version has the fix
    return compared


def remember(config, data):
    """Keep the advisory of the last verified update information ({} when it
    named none: an advisory withdrawn is forgotten)."""
    adv = clean(data)
    config["engine_advisory"] = adv or {}
    return adv


def notice(config, have=None):
    """The text to show, or "" (no advisory, or the engine has its fix)."""
    adv = config.get("engine_advisory")
    if not applies(adv, have):
        return ""
    from .i18n import T
    have = installed() if have is None else have
    return T("The web engine (Qt WebEngine %s) has a known security problem (%s), fixed in a newer "
             "version. Open a terminal and run: %s") % (have.get("qtwebengine", "?"), adv["id"], COMMAND)
