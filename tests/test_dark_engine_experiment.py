"""The I.K.E. Dark Engine experiment (ike/darkengine.py) behind its hidden
setting: off by default (Dark Reader as before); on, it takes Dark Reader's
place at every protection level in ApplicationWorld."""

import json
import random
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from test_security import JS

PAGE = ("<!doctype html><html><head><title>light</title><style>body{background:#fff;color:#111}"
        ".box{background:#f4f4f4;color:#222;height:80px}</style></head><body><main><h1>Light</h1>"
        "<div id='a' class='box'>Text in a box</div><p>Text.</p></main></body></html>")
NATIVE = """<!doctype html><meta name="color-scheme" content="dark">
<style id="native" class="ike-de">#panel { background: #234; color: #eee }</style>
<div id="panel" style="border: 2px solid #456">Native dark</div><script src="/slow.js"></script>"""
NATIVE_HINT = NATIVE.replace('<meta name="color-scheme" content="dark">', '').replace(
    '<div id="panel"', '<div id="panel" class="site-dark"')
DUAL_THEME = PAGE.replace("<html>", '<html data-theme="light dark">')
MODERN = """<!doctype html><style id="modern">
.first { background: #f4f4f4; color: #222 }
.wide { background: oklch(.98 .01 200); color: color(display-p3 .12 .12 .12) }
.last { background: #f4f4f4; color: #222 }
.custom { --tone: white !important; background: var(--tone); color: #222 }
.custom { --tone: red }
.translucent { background: #e0e0e0; color: rgba(85,85,85,.65) }
</style>
<p class="first">First</p><p class="wide">Modern CSS colors</p><p class="last">Last</p>
<p class="custom" style="--ink: black !important; color: var(--ink)">Custom colors</p>
<p class="translucent">Translucent text</p>"""
ICON = ('<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24">'
        '<path fill="%s" d="M4 4H20V20H4Z"/></svg>')
SVG = """<!doctype html><style>#specific { fill: blue }</style>
<svg width="24" height="24"><path id="specific" fill="red" d="M4 4H20V20H4Z"/>
<path id="dynamic" fill="black" d="M4 4H20V20H4Z"/></svg>"""


@pytest.fixture
def site():
    release_image = threading.Event()

    def noise_tile():
        from PyQt6.QtCore import QBuffer
        from PyQt6.QtGui import QImage

        rng = random.Random(917)
        pixels = bytes(192 + rng.getrandbits(6) for _ in range(512 * 512))
        tile = QImage(pixels, 512, 512, QImage.Format.Format_Grayscale8)
        buffer = QBuffer()
        tile.save(buffer, "PNG")
        return bytes(buffer.data())

    tile = None

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            nonlocal tile
            content_type = "text/html; charset=utf-8"
            if self.path == "/slow.js":
                time.sleep(0.3)
                content_type = "application/javascript"
                data = b""
            elif self.path in ("/black.svg", "/white.svg"):
                content_type = "image/svg+xml"
                data = (ICON % self.path[1:-4]).encode()
            elif self.path == "/delayed.svg":
                release_image.wait(15)
                content_type = "image/svg+xml"
                data = (ICON % "black").encode()
            elif self.path == "/release-image":
                release_image.set()
                data = b""
            elif self.path == "/wait-for-paint.js":
                release_image.wait(15)
                content_type = "application/javascript"
                data = b""
            elif self.path == "/flash":
                data = b"""<!doctype html><style id="authored">body{background:white}#card{background:#ddd}</style>
                    <main id="card">Card</main><script src="/wait-for-paint.js"></script>"""
            elif self.path == "/overlaid-frame":
                data = b"""<!doctype html><style>body{background:#588a60}
                    iframe{height:180px;width:360px;border:0}</style>
                    <iframe src="/frame-scrim"></iframe>"""
            elif self.path == "/frame-scrim":
                data = b"""<!doctype html><style>#scrim{background:rgba(0,0,0,.45);position:fixed;inset:0}
                    #dialog{background:#fff;color:#111}</style>
                    <div id="scrim"><div id="dialog">Content</div></div>"""
            elif self.path == "/details":
                data = b"""<!doctype html><style>
                    #panel { color:white; background:#0e1420; border:1px solid rgba(255,255,255,.12) }
                    #panel::before { content:''; display:block; height:20px;
                      background:linear-gradient(rgba(255,255,255,.035) 1px, transparent 1px) }
                    #chip { background:rgba(255,255,255,.05) }
                    #scrim { background:rgba(32,32,32,.8) }
                    #figure { color:#80df60; background:color-mix(in srgb, currentColor 8%, transparent) }
                    :where(a[href]) {color:inherit}
                    .explicit {color:white}
                    </style><section id="panel"><a href="#" id="inherited">Conversation</a>
                    <a id="anchor">Anchor</a><a class="explicit" href="#">Explicit</a>
                    <span id="chip">Quality</span><span id="figure">Feature</span>
                    <button id="scrim">Video control</button></section>"""
            elif self.path in ("/native-palette", "/declared-but-light"):
                color = "#234" if self.path == "/native-palette" else "white"
                data = f"""<!doctype html><html data-theme="dark"><body style="background:{color};color:#eee">
                    <p>Author palette</p>""".encode()
            elif self.path.startswith("/tile.png?"):
                if tile is None:
                    tile = noise_tile()
                content_type = "image/png"
                data = tile
            elif self.path in ("/red.css", "/blue.css"):
                content_type = "text/css"
                data = ("#cross { background: %s }" % self.path[1:-4]).encode()
            elif self.path == "/cross":
                data = b"""<!doctype html><style>#cross { background: white }</style>
                    <p id="cross">Cross-origin stylesheet</p>"""
            elif self.path == "/layers":
                data = b"""<!doctype html><style>#rule { background-image:
                    linear-gradient(white, white), url(/black.svg), url(/missing.svg) }</style>
                    <p id="rule">Style rule</p><p id="inline" style="background-image:
                    linear-gradient(white, white), url(/black.svg), url(/missing.svg)">Inline</p>
                    <p id="unavailable" style="background-image:
                    linear-gradient(white, white), url(/missing.svg)">Unavailable image</p>"""
            elif self.path == "/missing.svg":
                self.send_error(404)
                return
            else:
                data = {"/native": NATIVE, "/native-hint": NATIVE_HINT,
                        "/dual-theme": DUAL_THEME, "/modern": MODERN, "/svg": SVG}.get(self.path, PAGE).encode()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):
            pass
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield "http://127.0.0.1:%d" % srv.server_address[1]
    srv.shutdown()


JSW = r'''
def jsw(view, code):
    box = {}
    view.page().runJavaScript(code, 1, lambda r: box.setdefault("r", r))
    for _ in range(200):
        if "r" in box:
            break
        yield 20
    return box.get("r")
'''


STEPS = JS + JSW + r'''
SITE = "__SITE__"

def steps(ike, qapp, out):
    from PyQt6.QtWebEngineCore import QWebEngineSettings
    view = ike.windows[0].current_view()
    yield 500
    yield from load(view, SITE + "/page")
    yield 2500
    out["page"] = json.loads((yield from js(view, """JSON.stringify({
      dr: document.querySelectorAll('style.darkreader').length,
      body: getComputedStyle(document.body).backgroundColor,
      box: getComputedStyle(document.getElementById('a')).backgroundColor,
      experimentVisible: typeof window.__ikeDEStats !== 'undefined'})""")))
    out["engine"] = (yield from jsw(view, "JSON.stringify(window.__ikeDEStats || null)"))
    out["native"] = view.page().settings().testAttribute(QWebEngineSettings.WebAttribute.ForceDarkMode)
    out["scripts"] = sorted({s.name().split(":")[0] for s in view.page().profile().scripts().toList()
                             if s.name().startswith("ike-dark")})
'''


def lightness(css):
    import re
    m = re.match(r"rgba?\((\d+), (\d+), (\d+)", css or "")
    r, g, b = (int(x) for x in m.groups())
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255


def run(run_ike, site, **settings):
    base = {"dark_mode": "on", "dark_engine": "reader"}
    base.update(settings)
    return run_ike(STEPS.replace("__SITE__", site), settings=base, timeout=150)


def test_the_engine_by_default_and_no_dark_reader(run_ike, site):
    # 1.1.30: Dark Reader is no longer part of I.K.E.; a profile that chose it gets the engine
    out = run(run_ike, site)
    assert out["page"]["dr"] == 0 and json.loads(out["engine"])["sheets"] >= 1 and out["native"] is False, out
    assert "ike-dark-engine-x" in out["scripts"], out
    assert not [s for s in out["scripts"] if "darkreader" in s or s == "ike-dark-proxy"], out


@pytest.mark.parametrize("level", ["off", "compatibility", "balanced", "strict", "maximum"])
def test_on_it_replaces_dark_reader(run_ike, site, level):
    out = run(run_ike, site, dark_engine_experiment=True, shield_level=level)
    p = out["page"]
    assert p["dr"] == 0 and out["native"] is False, out
    assert json.loads(out["engine"])["sheets"] >= 1, out
    assert lightness(p["body"]) < 0.3 and lightness(p["box"]) < 0.3, out
    assert p["experimentVisible"] is False, out
    assert "ike-dark-engine-x" in out["scripts"], out
    assert "ike-dark-engine" not in out["scripts"] and "ike-dark-proxy" not in out["scripts"], out


def test_preserves_native_dark_author_styles(run_ike, site):
    steps = JS + '''
def steps(ike, qapp, out):
    view = ike.windows[0].current_view()
    yield from load(view, "__SITE__/native")
    out["styles"] = yield from js(view, """JSON.stringify({
      generated: document.querySelectorAll('style.ike-de:not(#native)').length,
      panel: getComputedStyle(document.querySelector('#panel')).borderTopColor,
      background: document.querySelector('#native').sheet.cssRules[0].style.backgroundColor
    })""")
'''
    out = run_ike(steps.replace("__SITE__", site), settings={
        "dark_mode": "on", "dark_engine": "reader", "dark_engine_experiment": True})
    assert json.loads(out["styles"]) == {
        "generated": 0, "panel": "rgb(68, 85, 102)", "background": "rgb(34, 51, 68)"}


def test_maps_modern_colors_and_preserves_custom_property_priority(run_ike, site):
    steps = JS + '''
def steps(ike, qapp, out):
    view = ike.windows[0].current_view()
    yield from load(view, "__SITE__/modern")
    out["colors"] = yield from js(view, """(() => {
      const text = getComputedStyle(document.querySelector('.translucent'));
      const bg = text.backgroundColor.match(/[\\d.]+/g).map(Number);
      const fg = text.color.match(/[\\d.]+/g).map(Number);
      const a = fg[3];
      const painted = bg.map((component, i) => component * (1 - a) + fg[i] * a);
      const linear = n => n <= .04045 ? n / 12.92 : ((n + .055) / 1.055) ** 2.4;
      const lum = rgb => rgb.reduce((sum, n, i) => sum + linear(n / 255) * [.2126, .7152, .0722][i], 0);
      return JSON.stringify({
      backgrounds: [...document.querySelectorAll('p')].map(e => getComputedStyle(e).backgroundColor),
      ratio: (lum(painted) + .05) / (lum(bg) + .05),
      alpha: a,
      priorities: ['--tone', '--ike-fg-tone'].map(p =>
          document.querySelector('#modern').sheet.cssRules[3].style.getPropertyPriority(p))
          .concat(['--ink', '--ike-fg-ink'].map(p =>
              document.querySelector('.custom').style.getPropertyPriority(p)))
    }); })()""")
'''
    out = run_ike(steps.replace("__SITE__", site), settings={
        "dark_mode": "on", "dark_engine": "reader", "dark_engine_experiment": True,
        "shield_level": "maximum"})
    colors = json.loads(out["colors"])
    assert colors["priorities"] == ["important"] * 4, colors
    assert all(lightness(color) < 0.3 for color in colors["backgrounds"]), colors
    assert colors["alpha"] == 0.65 and colors["ratio"] >= 4.5, colors


@pytest.mark.parametrize("chosen", [False, True])
def test_initial_dark_reader_hint_respects_explicit_dark_choice(run_ike, site, chosen):
    steps = JS + '''
def steps(ike, qapp, out):
    from ike import darkfixes
    darkfixes.hints_for = lambda url: [{"target": "#panel", "match": [".site-dark"]}]
    view = ike.windows[0].current_view()
    yield from load(view, "__SITE__/native-hint")
    out["generated"] = yield from js(view, "document.querySelectorAll('style.ike-de:not(#native)').length")
    out["border"] = yield from js(view, "getComputedStyle(document.querySelector('#panel')).borderTopColor")
'''
    out = run_ike(steps.replace("__SITE__", site), settings={
        "dark_mode": "off" if chosen else "on", "dark_sites": ["127.0.0.1"] if chosen else [],
        "dark_engine": "reader", "dark_engine_experiment": True})
    assert bool(out["generated"]) is chosen, out
    assert (out["border"] != "rgb(68, 85, 102)") is chosen, out


def test_dual_theme_metadata_uses_the_current_preference(run_ike, site):
    steps = JS + '''
def steps(ike, qapp, out):
    from ike import darkfixes
    darkfixes.hints_for = lambda url: [{"target": "html", "match": ['[data-theme*="dark"]']}]
    view = ike.windows[0].current_view()
    yield from load(view, "__SITE__/dual-theme")
    out["prefer_dark"] = yield from js(view, "matchMedia('(prefers-color-scheme: dark)').matches")
    out["generated"] = yield from js(view, "document.querySelectorAll('style.ike-de').length")
'''
    out = run_ike(steps.replace("__SITE__", site), settings={
        "dark_mode": "on", "dark_engine": "reader", "dark_engine_experiment": True})
    assert bool(out["generated"]) is not out["prefer_dark"], out


def test_native_dark_page_can_switch_to_light_without_reload(run_ike, site):
    steps = JS + '''
def steps(ike, qapp, out):
    from ike import darkfixes
    darkfixes.hints_for = lambda url: [{"target": "#panel", "match": [".site-dark"]}]
    view = ike.windows[0].current_view()
    yield from load(view, "__SITE__/native-hint")
    out["before"] = yield from js(view, "getComputedStyle(document.querySelector('#panel')).backgroundColor")
    yield from js(view, """const panel = document.querySelector('#panel');
      panel.style.backgroundColor = 'white'; panel.classList.remove('site-dark');
      window.sameDocument = true;""")
    yield 200
    out["after"] = yield from js(view, "getComputedStyle(document.querySelector('#panel')).backgroundColor")
    out["same_document"] = yield from js(view, "window.sameDocument === true")
'''
    out = run_ike(steps.replace("__SITE__", site), settings={
        "dark_mode": "on", "dark_engine": "ike", "shield_level": "maximum"})
    assert out["before"] == "rgb(34, 51, 68)", out
    assert out["after"] == "rgb(24, 26, 27)" and out["same_document"], out


@pytest.mark.parametrize("native", [True, False])
def test_declared_native_palette_matches_the_authored_colors(run_ike, site, native):
    steps = JS + '''
def steps(ike, qapp, out):
    view = ike.windows[0].current_view()
    yield from load(view, "__SITE__/__PAGE__")
    out["before"] = yield from js(view, "getComputedStyle(document.body).backgroundColor")
    yield from js(view, """document.body.style.backgroundColor = 'white';
      document.documentElement.dataset.theme = 'light';""")
    yield 200
    out["after"] = yield from js(view, "getComputedStyle(document.body).backgroundColor")
'''
    page = "native-palette" if native else "declared-but-light"
    out = run_ike(steps.replace("__SITE__", site).replace("__PAGE__", page), settings={
        "dark_mode": "on", "dark_engine": "ike", "shield_level": "maximum"})
    assert out["before"] == ("rgb(34, 51, 68)" if native else "rgb(24, 26, 27)"), out
    assert out["after"] == "rgb(24, 26, 27)", out


def test_replacing_dark_only_metadata_resumes_dark_engine(run_ike, site):
    steps = JS + '''
def steps(ike, qapp, out):
    view = ike.windows[0].current_view()
    yield from load(view, "__SITE__/native")
    out["initial"] = yield from js(view, "getComputedStyle(document.querySelector('#panel')).backgroundColor")
    yield from js(view, """document.head.replaceWith(document.createElement('head'));
      document.body.style.backgroundColor = 'white';""")
    yield 200
    out["resumed"] = yield from js(view, "getComputedStyle(document.body).backgroundColor")
'''
    out = run_ike(steps.replace("__SITE__", site), settings={
        "dark_mode": "on", "dark_engine": "ike", "shield_level": "maximum"})
    assert out["initial"] == "rgb(34, 51, 68)" and out["resumed"] == "rgb(24, 26, 27)", out


def test_foreign_image_leaves_local_icons_and_source_changes_working(run_ike, site):
    steps = JS + '''
def steps(ike, qapp, out):
    view = ike.windows[0].current_view()
    yield from load(view, "__SITE__/page")
    yield from js(view, """(async () => {
      const foreign = document.body.appendChild(new Image());
      foreign.src = "__FOREIGN__/black.svg";
      await foreign.decode();
      const local = document.body.appendChild(new Image());
      local.src = "/black.svg";
      await local.decode();
      await new Promise(done => setTimeout(done, 150));
      const dark = local.classList.contains("ike-de-lift");
      local.src = "/white.svg";
      await local.decode();
      await new Promise(done => setTimeout(done, 150));
      window.imageResult = [foreign.classList.contains("ike-de-lift"),
                            dark, local.classList.contains("ike-de-lift")];
    })()""")
    for _ in range(100):
        result = yield from js(view, "JSON.stringify(window.imageResult || null)")
        if result != "null":
            out["images"] = json.loads(result)
            break
        yield 50
'''
    out = run_ike(steps.replace("__SITE__", site).replace("__FOREIGN__", site.replace("127.0.0.1", "localhost")),
                  settings={"dark_mode": "on", "dark_engine": "reader", "dark_engine_experiment": True})
    assert out["images"] == [False, True, False], out


def test_svg_presentation_colors_keep_their_cascade_and_follow_changes(run_ike, site):
    steps = JS + '''
def steps(ike, qapp, out):
    view = ike.windows[0].current_view()
    yield from load(view, "__SITE__/svg")
    out["before"] = json.loads((yield from js(view, """JSON.stringify(
        [...document.querySelectorAll('path')].map(p => [getComputedStyle(p).fill, p.style.fill]))""")))
    yield from js(view, "document.querySelector('#dynamic').setAttribute('fill', 'green')")
    yield 200
    out["after"] = yield from js(view, "getComputedStyle(document.querySelector('#dynamic')).fill")
'''
    out = run_ike(steps.replace("__SITE__", site), settings={
        "dark_mode": "on", "dark_engine": "reader", "dark_engine_experiment": True})
    [r, g, b] = [int(value) for value in out["before"][0][0][4:-1].split(", ")]
    assert b > r and b > g, out
    assert all(inline_fill == "" for _, inline_fill in out["before"]), out
    assert lightness(out["before"][1][0]) > 0.75, out
    assert out["after"] not in ("rgb(0, 128, 0)", out["before"][1][0]), out


def test_cross_origin_override_tracks_source_media_replacement_and_removal(run_ike, site):
    steps = JS + '''
COLOR = "getComputedStyle(document.querySelector('#cross')).backgroundColor"

def color(view):
    return (yield from js(view, COLOR))

def wait_for_override(view, expected):
    for _ in range(100):
        found = yield from js(view, """document.querySelector('#other').nextElementSibling
            ?.sheet?.cssRules[0]?.style.backgroundColor === '""" + expected + """'""")
        if found:
            return True
        yield 50
    return False

def steps(ike, qapp, out):
    view = ike.windows[0].current_view()
    yield from load(view, "__SITE__/cross")
    yield from js(view, """const wrapper = document.createElement('div');
      wrapper.innerHTML = '<link id="other" rel="stylesheet" media="not all" href="__FOREIGN__/red.css">';
      document.body.appendChild(wrapper);""")
    out["red_rule"] = yield from wait_for_override(view, "rgb(173, 0, 0)")
    out["inactive"] = yield from color(view)
    yield from js(view, "document.querySelector('#other').media = 'all'")
    yield 200
    out["red"] = yield from color(view)
    yield from js(view, "document.querySelector('#other').href = '__FOREIGN__/blue.css'")
    out["blue_rule"] = yield from wait_for_override(view, "rgb(0, 0, 204)")
    out["blue"] = yield from color(view)
    yield from js(view, "document.querySelector('#other').remove()")
    yield 200
    out["removed"] = yield from color(view)
'''
    out = run_ike(steps.replace("__SITE__", site).replace("__FOREIGN__", site.replace("127.0.0.1", "localhost")),
                  settings={"dark_mode": "on", "dark_engine": "reader", "dark_engine_experiment": True,
                            "shield_level": "maximum"})
    assert out["red_rule"] and out["blue_rule"], out
    assert lightness(out["inactive"]) < 0.3, out
    assert out["red"] == "rgb(173, 0, 0)", out    # red made dark enough for light text on it
    assert out["blue"] == "rgb(0, 0, 204)", out
    assert out["removed"] == out["inactive"], out


def test_mixed_background_layers_finish_after_their_images_resolve(run_ike, site):
    steps = JS + '''
def steps(ike, qapp, out):
    view = ike.windows[0].current_view()
    yield from load(view, "__SITE__/layers")
    for _ in range(60):
        out["layers"] = json.loads((yield from js(view, """JSON.stringify(
            [...document.querySelectorAll('p')].map(p => getComputedStyle(p).backgroundImage))""")))
        if (all("data:image/png" in layer for layer in out["layers"][:2])
                and "rgb(24, 26, 27)" in out["layers"][2]):
            break
        yield 50
'''
    out = run_ike(steps.replace("__SITE__", site), settings={
        "dark_mode": "on", "dark_engine": "reader", "dark_engine_experiment": True,
        "shield_level": "maximum"})
    for layer in out["layers"][:2]:
        assert "rgb(24, 26, 27)" in layer and "data:image/png" in layer and "missing.svg" in layer, layer
    assert "rgb(24, 26, 27)" in out["layers"][2] and "missing.svg" in out["layers"][2], out


def test_slow_background_image_does_not_delay_gradient(run_ike, site):
    steps = JS + '''
LAYERS = """JSON.stringify(['rule', 'inline', 'replaced'].map(
    id => getComputedStyle(document.getElementById(id)).backgroundImage))"""

def steps(ike, qapp, out):
    view = ike.windows[0].current_view()
    yield from load(view, "__SITE__/page")
    yield from js(view, """const html = '<style>#rule{background-image:linear-gradient(white,white),url(/delayed.svg)}</style>' +
      '<p id="rule">Rule</p><p id="inline" style="background-image:linear-gradient(white,white),url(/delayed.svg)">Inline</p>' +
      '<p id="replaced" style="background-image:linear-gradient(white,white),url(/delayed.svg)">Replaced</p>';
      document.body.insertAdjacentHTML('beforeend', html);""")
    yield 250
    out["before"] = json.loads((yield from js(view, LAYERS)))
    yield from js(view, """document.getElementById('replaced').style.backgroundImage = 'none';
      fetch('/release-image');""")
    for _ in range(60):
        out["after"] = json.loads((yield from js(view, LAYERS)))
        if all("data:image/png" in layer for layer in out["after"][:2]):
            break
        yield 50
'''
    out = run_ike(steps.replace("__SITE__", site), settings={
        "dark_mode": "on", "dark_engine": "reader", "dark_engine_experiment": True,
        "shield_level": "maximum"})
    assert all("rgb(24, 26, 27)" in layer and "delayed.svg" in layer for layer in out["before"]), out
    assert all("rgb(24, 26, 27)" in layer and "data:image/png" in layer for layer in out["after"][:2]), out
    assert out["after"][2] == "none", out


@pytest.mark.parametrize(("count", "tiles"), [(270, False), (24, True)])
def test_background_image_cache_releases_completed_entries(run_ike, site, count, tiles):
    steps = JS + JSW + '''
COUNT = __COUNT__
TILES = __TILES__

def steps(ike, qapp, out):
    view = ike.windows[0].current_view()
    yield from load(view, "__SITE__/page")
    yield from js(view, """window.addIcon = function (n, tiles) {
      const icon = document.body.appendChild(document.createElement('p'));
      const svg = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24">' +
                  '<desc>' + n + '</desc><path fill="black" d="M4 4H20V20H4Z"/></svg>';
      const source = tiles ? '/tile.png?' + n : 'data:image/svg+xml,' + encodeURIComponent(svg);
      icon.style.backgroundImage = 'url("' + source + '")';
      icon.className = 'test-cache-icon';
    };
    for (let n = 0; n < %d; n++) addIcon(n, %s);""" % (COUNT, json.dumps(TILES)))
    for _ in range(100):
        out["converted"] = yield from js(view, """[...document.querySelectorAll('.test-cache-icon')].filter(
            e => getComputedStyle(e).backgroundImage.includes('data:image/png')).length""")
        out["cache"] = json.loads((yield from jsw(view, "JSON.stringify(window.__ikeDEStats)")))
        if out["converted"] == COUNT and 0 < out["cache"].get("pictureCacheEntries", COUNT) < COUNT:
            break
        yield 50
    yield from js(view, "addIcon(0, %s)" % json.dumps(TILES))
    for _ in range(80):
        out["reused"] = yield from js(view, """getComputedStyle(document.body.lastElementChild)
            .backgroundImage.includes('data:image/png')""")
        if out["reused"]:
            break
        yield 50
'''
    script = steps.replace("__SITE__", site).replace("__COUNT__", str(count)).replace("__TILES__", repr(tiles))
    out = run_ike(script, settings={
        "dark_mode": "on", "dark_engine": "reader", "dark_engine_experiment": True,
        "shield_level": "maximum"})
    assert out["converted"] == count and out["reused"], out
    assert 0 < out["cache"]["pictureCacheEntries"] <= min(256, count - 1), out
    assert 0 < out["cache"]["pictureCacheChars"] <= 4 * 1024 * 1024, out


def test_shadow_roots_are_released_and_reobserved_after_reattachment(run_ike, site):
    steps = JS + JSW + '''
def stats(view):
    return json.loads((yield from jsw(view, "JSON.stringify(window.__ikeDEStats)")))

def steps(ike, qapp, out):
    view = ike.windows[0].current_view()
    yield from load(view, "__SITE__/page")
    yield 4300
    yield from js(view, """window.host = document.body.appendChild(document.createElement('test-component'));
      window.root = host.attachShadow({mode:'open'});
      root.innerHTML = '<p style="background:white">First</p>';
      const persistent = document.body.appendChild(document.createElement('other-component'));
      window.liveRoot = persistent.attachShadow({mode:'open'});
      liveRoot.innerHTML = '<p>Persistent component</p>';""")
    yield 150
    out["initial"] = (yield from stats(view)).get("shadowRoots")
    yield from js(view, "host.remove()")
    yield 150
    out["detached"] = (yield from stats(view)).get("shadowRoots")
    yield from js(view, """root.innerHTML = '<p style="background:white">While detached</p>';
      liveRoot.firstElementChild.style.backgroundColor = 'white';""")
    yield 150
    out["detached_style"] = yield from js(view, "root.firstElementChild.style.backgroundColor")
    out["persistent_style"] = yield from js(view, "getComputedStyle(liveRoot.firstElementChild).backgroundColor")
    yield from js(view, "document.body.appendChild(host)")
    yield 150
    out["attached_style"] = yield from js(view, "getComputedStyle(root.firstElementChild).backgroundColor")
    out["reattached"] = (yield from stats(view)).get("shadowRoots")
    yield from js(view, "root.firstElementChild.style.backgroundColor = 'red'")
    yield 150
    out["updated_style"] = yield from js(view, "getComputedStyle(root.firstElementChild).backgroundColor")
'''
    out = run_ike(steps.replace("__SITE__", site), settings={
        "dark_mode": "on", "dark_engine": "reader", "dark_engine_experiment": True,
        "shield_level": "maximum"})
    assert (out["initial"], out["detached"], out["reattached"]) == (2, 1, 2), out
    assert out["detached_style"] == "white", out
    assert out["persistent_style"] == "rgb(24, 26, 27)", out
    assert out["attached_style"] == "rgb(24, 26, 27)" and out["updated_style"] == "rgb(173, 0, 0)", out


def test_authored_link_colors_and_translucent_details_survive(run_ike, site):
    steps = JS + '''
def steps(ike, qapp, out):
    view = ike.windows[0].current_view()
    yield from load(view, "__SITE__/details")
    out["styles"] = json.loads((yield from js(view, """JSON.stringify({
      panel: getComputedStyle(document.querySelector('#panel')).color,
      links: [...document.querySelectorAll('a')].map(e => getComputedStyle(e).color),
      border: getComputedStyle(document.querySelector('#panel')).borderTopColor,
      grid: getComputedStyle(document.querySelector('#panel'), '::before').backgroundImage,
      chip: getComputedStyle(document.querySelector('#chip')).backgroundColor,
      scrim: getComputedStyle(document.querySelector('#scrim')).backgroundColor,
      figure: getComputedStyle(document.querySelector('#figure')).backgroundColor})""")))
'''
    styles = run_ike(steps.replace("__SITE__", site), settings={
        "dark_mode": "on", "dark_engine": "ike", "shield_level": "maximum"})["styles"]
    assert styles["links"] == [styles["panel"]] * 3, styles
    assert styles["border"] == "rgba(255, 255, 255, 0.12)", styles
    assert styles["chip"] == "rgba(255, 255, 255, 0.05)", styles
    assert styles["scrim"] == "rgba(32, 32, 32, 0.8)", styles
    assert "rgba(255, 255, 255, 0.035)" in styles["grid"], styles
    assert styles["figure"] != "rgba(0, 0, 0, 0.08)" and "0.08" in styles["figure"], styles


def test_body_is_dark_before_dom_ready_and_cards_keep_their_color(run_ike, site):
    steps = JS + '''
def steps(ike, qapp, out):
    from PyQt6.QtCore import QUrl
    view = ike.windows[0].current_view()
    view.load(QUrl("__SITE__/flash"))
    for _ in range(120):
        state = yield from js(view, """document.querySelector('#card') && JSON.stringify([
          document.readyState, getComputedStyle(document.body).backgroundColor])""")
        if state:
            out["before"] = json.loads(state)
            break
        yield 25
    yield from js(view, "fetch('/release-image')")
    for _ in range(120):
        state = yield from js(view, """document.readyState !== 'loading' && JSON.stringify([
          document.querySelector('#authored').sheet.cssRules[0].style.backgroundColor,
          getComputedStyle(document.querySelector('#card')).backgroundColor])""")
        if state:
            out["after"] = json.loads(state)
            break
        yield 25
'''
    out = run_ike(steps.replace("__SITE__", site), settings={
        "dark_mode": "on", "dark_engine": "ike", "shield_level": "maximum"})
    assert out["before"] == ["loading", "rgb(24, 26, 27)"], out
    assert out["after"][0] != "white" and 0.08 < lightness(out["after"][1]) < 0.3, out


def test_transparent_frame_keeps_the_underlying_page_visible(run_ike, site):
    steps = JS + '''
def steps(ike, qapp, out):
    view = ike.windows[0].current_view()
    yield from load(view, "__SITE__/overlaid-frame")
    yield 300
    out["inside"] = json.loads((yield from js(view, """(() => {
      const frame = document.querySelector('iframe').contentWindow;
      return JSON.stringify(['html', 'body', '#scrim', '#dialog'].map(
        s => frame.getComputedStyle(frame.document.querySelector(s)).backgroundColor));
    })()""")))
    image = view.grab().toImage()
    scale = image.devicePixelRatio()
    out["pixels"] = [image.pixelColor(round(x * scale), round(100 * scale)).getRgb()[:3] for x in (100, 400)]
'''
    out = run_ike(steps.replace("__SITE__", site), settings={
        "dark_mode": "on", "dark_engine": "ike", "shield_level": "maximum"})
    assert out["inside"][:3] == ["rgba(0, 0, 0, 0)", "rgba(0, 0, 0, 0)", "rgba(0, 0, 0, 0.45)"], out
    assert out["inside"][3] == "rgb(24, 26, 27)", out
    dimmed, background = out["pixels"]
    assert max(background) > 30 and all(abs(a - 0.55 * b) <= 3 for a, b in zip(dimmed, background)), out

