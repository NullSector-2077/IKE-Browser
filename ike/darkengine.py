"""I.K.E. Dark Engine: an EXPERIMENT, off by default and not used by the
browser (nothing imports it). I.K.E.'s own dark mode for pages, meant to look
like Dark Reader at a fraction of its cost: darkengine.js (next to this file,
kept out of resources/ while it is an experiment) walks the page's style
sheets and inline styles once, writes one override style sheet per source
sheet, then handles only what is added later. Dark Reader's lists
(resources/darkreader-data.json, through darkfixes.py) give the per-site fixes
(their CSS and INVERT selectors). Measured by tests/dark_engine/.
"""

import json
from pathlib import Path

_NAME = "ike-dark-engine-x"


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


def install(profile):
    """Make every page of the profile dark with the experimental engine."""
    remove(profile)
    profile.scripts().insert(_script(_NAME, source()))


def site(profile, url, host):
    """Register the Dark Reader fix of a site (call before its page loads)."""
    from . import darkfixes
    name = _NAME + ":" + host
    for s in profile.scripts().find(name):
        profile.scripts().remove(s)
    cfg = "(window.__ikeDECfg || (window.__ikeDECfg = {}))[%s] = %s;" % (
        json.dumps(host), json.dumps(_fix(darkfixes.fix_for(url))))
    profile.scripts().insert(_script(name, cfg))
    for s in profile.scripts().find(_NAME):        # the engine runs after the sites' settings
        profile.scripts().remove(s)
        profile.scripts().insert(s)


def remove(profile):
    for s in list(profile.scripts().toList()):
        if s.name() == _NAME or s.name().startswith(_NAME + ":"):
            profile.scripts().remove(s)
