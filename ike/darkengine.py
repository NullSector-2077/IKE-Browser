"""I.K.E. Dark Engine: an EXPERIMENT, off by default. I.K.E.'s own dark mode
for pages, meant to look like Dark Reader at a fraction of its cost:
darkengine.js (next to this file, kept out of resources/ while it is an
experiment) walks the page's style sheets and inline styles once, writes one
override style sheet per source sheet, then handles only what is added later.
Dark Reader's lists (resources/darkreader-data.json, through darkfixes.py) give
the per-site fixes (their CSS and INVERT selectors) and the sites that are dark
already. Measured by tests/dark_engine/.

Hidden setting (round 3): nothing in the menus or in Settings. With
"dark_engine_experiment": true written by hand in the profile's settings.json
(~/.config/ike-browser/settings.json, the browser closed) and the dark mode
method "Dark Reader", a page that would be made dark by Dark Reader is made
dark by this engine instead, at the protection levels Off, Compatibility and
Balanced; at Strict and Maximum no script darkens the page: Chromium's own
dark mode does (the owner's privacy rule). Without the key, or with false,
nothing changes.

The engine is installed for the whole profile and does nothing on its own: a
small script per dark site registers that site's fix (as darkpages.py does for
Dark Reader), and only a page whose top site is registered is made dark.

Style sheets of other sites: the script asks the page bridge that Dark Reader
already uses in I.K.E. (window.__ikeBridge.fetchCss, passwords.py PageBridge:
style sheets only, the address the page itself loaded, no cookies, checked by
the filter lists, only while the page is dark).
"""

import json
from pathlib import Path

SETTING = "dark_engine_experiment"
SITES_MAX = 40
_NAME = "ike-dark-engine-x"
_state = {}                  # id(profile): {"sites": {host: cfg}, "order": [host, ...]}


def wanted(cfg):
    """Is the experiment turned on (by hand, in settings.json)?"""
    return cfg.get(SETTING) is True


def _fix(fix):
    return {"invert": fix.get("invert") or [], "css": fix.get("css") or "",
            "ignoreInline": ",".join(fix.get("ignoreInlineStyle") or [])}


def _script(name, source):
    from PyQt6.QtWebEngineCore import QWebEngineScript
    s = QWebEngineScript()
    s.setName(name)
    s.setSourceCode(source)
    s.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
    s.setWorldId(QWebEngineScript.ScriptWorldId.ApplicationWorld)
    s.setRunsOnSubFrames(True)
    return s


def source():
    from . import darkfixes
    src = Path(__file__).with_name("darkengine.js").read_text("utf-8")
    return src.replace("__IKE_DE_COMMON__", json.dumps(_fix(darkfixes.common_fix())))


def _site_source(host, cfg):
    h = json.dumps(host)
    return ("(window.__ikeDECfg || (window.__ikeDECfg = {}))[%s] = %s;\n"
            "if (window.__ikeDEGo) window.__ikeDEGo(%s);" % (h, cfg, h))


def _remove(profile, name):
    for s in list(profile.scripts().toList()):
        if s.name() == name:
            profile.scripts().remove(s)


def install(profile):
    """Put the engine in the profile (it darkens only the registered sites)."""
    remove(profile)
    profile.scripts().insert(_script(_NAME, source()))
    _state[id(profile)] = {"sites": {}, "order": []}


def site(profile, url, host):
    """Register the Dark Reader fix of a site (call before its page loads)."""
    from . import darkfixes
    st = _state.get(id(profile))
    if st is None:
        install(profile)
        st = _state[id(profile)]
    cfg = json.dumps(_fix(darkfixes.fix_for(url)))
    if st["sites"].get(host) != cfg:
        _remove(profile, _NAME + ":" + host)
        profile.scripts().insert(_script(_NAME + ":" + host, _site_source(host, cfg)))
        st["sites"][host] = cfg
    if host in st["order"]:
        st["order"].remove(host)
    st["order"].append(host)
    while len(st["order"]) > SITES_MAX:
        gone = st["order"].pop(0)
        _remove(profile, _NAME + ":" + gone)
        st["sites"].pop(gone, None)


def prepare(profile, url, host, dark, chosen):
    """A page of host is about to load (main frame), the experiment on. dark:
    should it be dark? chosen: did the user turn this site dark himself (then
    Dark Reader's list of dark sites does not apply). Returns whether the
    page will be made dark by the engine."""
    from . import darkfixes
    if not host:
        return False
    if dark and not chosen and darkfixes.in_dark_list(url):
        dark = False
    st = _state.get(id(profile))
    if not dark:
        if st and host in st["sites"]:
            _remove(profile, _NAME + ":" + host)
            del st["sites"][host]
            st["order"].remove(host)
        return False
    site(profile, url, host)
    return True


def remove(profile):
    for s in list(profile.scripts().toList()):
        if s.name() == _NAME or s.name().startswith(_NAME + ":"):
            profile.scripts().remove(s)
    _state.pop(id(profile), None)


def forget(profile):
    """No page of this profile is made dark by the engine any more."""
    if id(profile) in _state:
        remove(profile)
