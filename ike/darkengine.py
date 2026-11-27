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
dark by this engine instead at every protection level, including Strict and
Maximum. This experimental configuration still requires privacy and performance
validation. Without the key, or with false, nothing changes.

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

# The look of the Dark Engine (its panel and Settings, 1.1.28): style, how dark
# the backgrounds are, how bright the text is, how much photos and videos are
# dimmed, and whether sites dark already are left as they are. darkengine.js
# reads the same keys (setLook) and checks them again.
STYLES = ("graphite", "midnight", "warm", "nordic")
LOOK = {"style": "graphite", "depth": 50, "text": 50, "pictures": 0, "detect": True}
RANGES = {"depth": (0, 100), "text": (0, 100), "pictures": (0, 60)}


def background(look):
    """The dark background of a look as #rrggbb (darkengine.js setLook: the
    page's background, also shown before the page paints)."""
    return colours(look)[0]


STYLE_COLOURS = {   # (background hue, saturation, depth factor), (text hue, saturation), link: as darkengine.js
    "graphite": ((200, 0.06, 1), (36, 0.098), "#3392ff"),
    "midnight": ((225, 0.12, 0.6), (220, 0.12), "#52a8ff"),
    "warm": ((30, 0.14, 1.05), (38, 0.32), "#f0a44c"),
    "nordic": ((220, 0.17, 1.5), (218, 0.27), "#87bfcf"),
}


def colours(look):
    """(background, text, link) of a look as #rrggbb: the panel's previews."""
    import colorsys
    look = clean_look(look)
    (bh, bs, dark), (th, ts), link = STYLE_COLOURS[look["style"]]
    d, t = look["depth"], look["text"]
    lb = (0.17 - d / 50 * 0.07 if d <= 50 else 0.1 - (d - 50) / 50 * 0.06) * dark
    lf = 0.78 + t / 50 * 0.12 if t <= 50 else 0.9 + (t - 50) / 50 * 0.08

    def hexa(h, s, li):
        r, g, b = colorsys.hls_to_rgb(h / 360, li, s)
        return "#%02x%02x%02x" % (round(r * 255), round(g * 255), round(b * 255))
    return hexa(bh, bs, lb), hexa(th, ts, lf), link


def clean_look(look):
    """A look with every key, each value of its kind and in its range (else the default)."""
    out = dict(LOOK)
    if not isinstance(look, dict):
        return out
    if look.get("style") in STYLES:
        out["style"] = look["style"]
    for key, (lo, hi) in RANGES.items():
        v = look.get(key)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and v == v:
            out[key] = int(min(hi, max(lo, round(v))))
    if isinstance(look.get("detect"), bool):
        out["detect"] = look["detect"]
    return out
SITES_MAX = 40
_NAME = "ike-dark-engine-x"
_state = {}                  # id(profile): {"sites": {host: cfg}, "order": [host, ...]}


def wanted(cfg):
    """Is the experiment turned on (by hand, in settings.json)?"""
    return cfg.get(SETTING) is True


def _fix(fix):
    from . import darkfixes
    # only the CSS rules the engine can use (darkfixes.engine_css)
    return {"invert": fix.get("invert") or [], "css": darkfixes.engine_css(fix.get("css") or ""),
            "ignoreInline": ",".join(fix.get("ignoreInlineStyle") or []),
            "ignoreImage": fix.get("ignoreImageAnalysis") or [],
            "ignoreSheet": fix.get("ignoreCSSUrl") or []}


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


def site(profile, url, host, chosen, look=None):
    """Register the Dark Reader fix of a site and the engine's look (call before its page loads)."""
    from . import darkfixes
    st = _state.get(id(profile))
    if st is None:
        install(profile)
        st = _state[id(profile)]
    fix = _fix(darkfixes.fix_for(url))
    hints = [] if chosen else darkfixes.hints_for(url)
    cfg = json.dumps({**fix, "chosen": chosen, "hint": hints[0] if hints else None,
                      "look": clean_look(look)})
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


def prepare(profile, url, host, dark, chosen, look=None):
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
    site(profile, url, host, chosen, look)
    return True


def set_look(view, look):
    """An open page takes a new look at once, without being loaded again (its main
    frame; its frames at their next load). The page cannot reach the function."""
    from PyQt6.QtWebEngineCore import QWebEngineScript
    code = "window.__ikeDELook && window.__ikeDELook(%s)" % json.dumps(clean_look(look))
    view.page().runJavaScript(code, QWebEngineScript.ScriptWorldId.ApplicationWorld)


def remove(profile):
    for s in list(profile.scripts().toList()):
        if s.name() == _NAME or s.name().startswith(_NAME + ":"):
            profile.scripts().remove(s)
    _state.pop(id(profile), None)


def forget(profile):
    """No page of this profile is made dark by the engine any more."""
    if id(profile) in _state:
        remove(profile)
