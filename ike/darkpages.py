"""The scripts that make pages dark with Dark Reader (resources/darkmode.js).

They are installed in the profile, not in a single page: a script given to a
page at the moment it starts to navigate can miss the new page when the engine
runs it in another process (a new tab page, then a site, for one), so the
first site opened in a tab stayed light. The profile has:

- "ike-dark-engine"  Dark Reader and darkmode.js, every frame of every page;
                     it does nothing on a page whose site is not registered;
- "ike-dark-proxy"   Dark Reader's style-sheet proxy, in the pages' own world;
                     it waits for the engine's event, whose name carries a
                     token of this session;
- "ike-dark-site:<host>"  one small script per dark site (the most recent
                     SITES_MAX): registers the site's fix and detector
                     settings; the engine then makes that site's pages dark.

The engine and the proxy are only there while some page can be made dark
with Dark Reader (dark mode on, or sites turned dark one by one).
"""

import json
import secrets

from .config import RES_DIR

SITES_MAX = 40
_TOKEN = secrets.token_hex(8)
_sources = {}
_state = {}                  # id(profile): {"key": ..., "sites": {host: cfg}, "order": [host, ...]}


def _source(name):
    if name not in _sources:
        _sources[name] = (RES_DIR / name).read_text("utf-8")
    return _sources[name]


def _script(name, source, main_world):
    from PyQt6.QtWebEngineCore import QWebEngineScript
    s = QWebEngineScript()
    s.setName(name)
    s.setSourceCode(source)
    s.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
    s.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld if main_world
                 else QWebEngineScript.ScriptWorldId.ApplicationWorld)
    s.setRunsOnSubFrames(True)
    return s


def _remove(scripts, prefix):
    for s in list(scripts.toList()):
        if s.name() == prefix or s.name().startswith(prefix + ":"):
            scripts.remove(s)


def clear(profile):
    """Take every dark-mode script out of the profile."""
    scripts = profile.scripts()
    for name in ("ike-dark-engine", "ike-dark-proxy", "ike-dark-site"):
        _remove(scripts, name)
    _state.pop(id(profile), None)


def _engine(theme):
    from . import darkfixes
    lib = _source("darkreader.js").replace("__IKE_DR_TOKEN__", _TOKEN)
    src = _source("darkmode.js")
    # the library goes in last: nothing inside it is taken for a placeholder
    src = (src.replace("__IKE_DR_THEME__", json.dumps(theme))
              .replace("__IKE_DR_COMMON__", json.dumps(darkfixes.common_fix())))
    return src.replace("__IKE_DR_LIB__", lib)


def prepare(profile, url, host, theme, dark, chosen):
    """A page of host is about to load (main frame). dark: should it be dark with
    Dark Reader? chosen: did the user turn this site dark himself? Returns
    whether the page will be made dark (False for a site on Dark Reader's list
    of dark sites, unless chosen)."""
    from . import darkfixes
    scripts = profile.scripts()
    st = _state.get(id(profile))
    key = json.dumps(theme, sort_keys=True)
    if not host:
        return False
    page = url
    if dark and not chosen and darkfixes.in_dark_list(page):
        dark = False
    if not dark:
        if st and host in st["sites"]:
            _remove(scripts, "ike-dark-site:" + host)
            del st["sites"][host]
            st["order"].remove(host)
        return False
    if st is None or st["key"] != key:
        clear(profile)
        scripts.insert(_script("ike-dark-proxy", _source("darkreader-proxy.js").replace("__IKE_DR_TOKEN__", _TOKEN),
                               True))
        scripts.insert(_script("ike-dark-engine", _engine(theme), False))
        st = _state[id(profile)] = {"key": key, "sites": {}, "order": []}
    cfg = json.dumps({"fix": darkfixes.fix_for(page), "detect": not chosen,
                      "hints": [] if chosen else darkfixes.hints_for(page)})
    if st["sites"].get(host) != cfg:
        _remove(scripts, "ike-dark-site:" + host)
        h = json.dumps(host)
        scripts.insert(_script("ike-dark-site:" + host,
                               "(window.__ikeDarkCfg || (window.__ikeDarkCfg = {}))[%s] = %s;\n"
                               "if (window.__ikeDarkGo) window.__ikeDarkGo(%s);" % (h, cfg, h), False))
        st["sites"][host] = cfg
    if host in st["order"]:
        st["order"].remove(host)
    st["order"].append(host)
    while len(st["order"]) > SITES_MAX:
        gone = st["order"].pop(0)
        _remove(scripts, "ike-dark-site:" + gone)
        st["sites"].pop(gone, None)
    return True


def forget(profile):
    """No page of this profile can be dark with Dark Reader any more (dark mode
    off and no site chosen, or the engine of Qt chosen)."""
    if id(profile) in _state:
        clear(profile)
