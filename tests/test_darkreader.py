"""Page dark mode with Dark Reader as the Dark Reader extension uses it (1.1.4):
its lists (fixes for single sites, sites that are dark already, hints of a
site's own dark theme), its style-sheet proxy in the page's own world even
under a strict Content-Security-Policy, and its detector of a site's own dark
theme. All on this computer: local pages that behave as the hard cases do."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from test_security import JS

# --- the lists ----------------------------------------------------------------


def test_address_patterns_as_dark_reader_matches_them():
    from ike.darkfixes import matches
    assert matches("https://example.com/a", "example.com")
    assert matches("https://www.example.com/a", "example.com")            # www. counts as the site
    assert not matches("https://sub.example.com/", "example.com")
    assert matches("https://sub.example.com/", "*.example.com")
    assert matches("https://example.com/", "example.*")
    assert matches("https://example.com/docs/x", "example.com/docs")
    assert not matches("https://example.com/blog", "example.com/docs")
    assert matches("https://example.com/docs", "example.com/docs$")
    assert not matches("https://example.com/docs/x", "example.com/docs$")
    assert matches("https://example.com:8080/", "example.com:8080")
    assert not matches("https://example.com:8081/", "example.com:8080")
    assert matches("https://anything.test/x", r"/anything\.test/")
    assert not matches("not an address", "example.com")


def test_the_lists_are_there_and_give_what_the_extension_gives():
    from ike import darkfixes
    d = darkfixes.data()
    assert d["version"] and len(d["fixes"]) > 1000 and d["fixes"][0]["url"] == ["*"]
    assert len(d["dark_sites"]) > 100 and len(d["detector_hints"]) > 50
    common = darkfixes.common_fix()
    # a site of the list gets the common fix and its own one
    site = next(f for f in d["fixes"][1:] if f.get("css") and not f["url"][0].startswith(("/", "^", "*"))
                and "/" not in f["url"][0] and "*" not in f["url"][0] and ":" not in f["url"][0])
    fix = darkfixes.fix_for("https://%s/" % site["url"][0])
    assert fix["css"].startswith(common["css"]) and site["css"] in fix["css"]
    # a site not in the list: the common fix alone
    assert darkfixes.fix_for("https://nothing-of-this.invalid/") == common
    # a site of the dark list, and one that is not
    dark = next(p for p in d["dark_sites"] if "*" not in p and "/" not in p and not p.startswith(("^", "$")))
    assert darkfixes.in_dark_list("https://%s/" % dark)
    assert not darkfixes.in_dark_list("https://nothing-of-this.invalid/")
    # the proxy is asked for with the extension's own event, never as an inline script
    from ike.config import RES_DIR
    engine = (RES_DIR / "darkreader.js").read_text("utf-8")
    assert "__darkreader__stylesheetProxy__arg" in engine and 'createOrUpdateScript("darkreader--proxy")' not in engine
    proxy = (RES_DIR / "darkreader-proxy.js").read_text("utf-8")
    assert "function injectProxy(" in proxy and "__darkreader__stylesheetProxy__arg" in proxy


def build_tool():
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location(
        "build_darkreader", Path(__file__).resolve().parent.parent / "tools" / "build-darkreader.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def fake_engine(patches, skip=None):
    """An engine with the proxy injection and the text every I.K.E. patch changes."""
    body = "".join(old for name, old, _new in patches if name != skip)
    return ("/**\r\n * Dark Reader v9.9.9\r\n */\r\n(function () {\r\n"
            "    function injectProxy(\r\n        a,\r\n        b\r\n    ) {\r\n        if (a) { b(); }\r\n    }\r\n"
            "    function other() {\r\n        {\r\n"
            "            const proxyScript = createOrUpdateScript(\"darkreader--proxy\");\r\n"
            "            proxyScript.append(`(${injectProxy})(${a}, ${b})`);\r\n"
            "            proxyScript.remove();\r\n        }\r\n    }\r\n"
            + body.replace("\n", "\r\n") + "})();\r\n")


def test_the_build_tool(tmp_path):
    """tools/build-darkreader.py: the proxy taken out of the engine and asked for
    by an event, I.K.E.'s changes made, the lists read; an engine it does not
    recognise is refused."""
    import subprocess
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    patches = build_tool().PATCHES
    (tmp_path / "lib.js").write_bytes(fake_engine(patches).encode())
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "dynamic-theme-fixes.config").write_text(
        "*\n\nINVERT\n.logo\n\nCSS\nbody { color: red }\n\n====\n\nexample.com\n*.example.org\n\n"
        "IGNORE INLINE STYLE\n.x\n.y\n")
    (cfg / "dark-sites.config").write_text("dark.example\nnight.example/app\n")
    (cfg / "detector-hints.config").write_text("own.example\n\nTARGET\nhtml\n\nMATCH\n.dark\n\n"
                                               "====\n\nnever.example\n\nNO DARK THEME\n")
    out = tmp_path / "out"
    out.mkdir()
    run = subprocess.run([sys.executable, str(root / "tools/build-darkreader.py"), "--lib", str(tmp_path / "lib.js"),
                          "--config", str(cfg), "--out", str(out), "--commit", "abc"], capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    engine = (out / "darkreader.js").read_bytes().decode()
    assert "createOrUpdateScript" not in engine and "__darkreader__stylesheetProxy__arg__IKE_DR_TOKEN__" in engine
    assert "\r\n" in engine and "\n" not in engine.replace("\r\n", "")   # the engine's own line ends are kept
    for _name, old, new in patches:                           # every change made, in those line ends
        assert new.replace("\n", "\r\n") in engine
    proxy = (out / "darkreader-proxy.js").read_text()
    assert "function injectProxy(" in proxy and "if (a) { b(); }" in proxy and "other()" not in proxy
    data = json.loads((out / "darkreader-data.json").read_text())
    assert data["version"] == "9.9.9" and data["lists_commit"] == "abc"
    assert data["fixes"][0] == {"url": ["*"], "invert": [".logo"], "css": "body { color: red }"}
    assert data["fixes"][1] == {"url": ["example.com", "*.example.org"], "ignoreInlineStyle": [".x", ".y"]}
    assert data["dark_sites"] == ["dark.example", "night.example/app"]
    assert data["detector_hints"] == [{"url": ["own.example"], "target": "html", "match": [".dark"]},
                                      {"url": ["never.example"], "noDarkTheme": True}]
    (tmp_path / "bad.js").write_text("/**\n * Dark Reader v9.9.9\n */\nfunction injectProxy(\n    a\n) {\n}\n")
    run = subprocess.run([sys.executable, str(root / "tools/build-darkreader.py"), "--lib", str(tmp_path / "bad.js"),
                          "--config", str(cfg), "--out", str(out)], capture_output=True, text=True)
    assert run.returncode != 0 and "proxy injection" in (run.stderr + run.stdout)
    # an engine where one of the texts I.K.E. changes is missing is not half-adapted
    (tmp_path / "changed.js").write_bytes(fake_engine(patches, skip="shadow-texts").encode())
    run = subprocess.run([sys.executable, str(root / "tools/build-darkreader.py"), "--lib", str(tmp_path / "changed.js"),
                          "--config", str(cfg), "--out", str(tmp_path)], capture_output=True, text=True)
    assert run.returncode != 0 and "'shadow-texts'" in (run.stderr + run.stdout)
    assert not (tmp_path / "darkreader.js").exists()


def test_the_engine_is_the_npm_engine_with_the_changes():
    """ike/resources/darkreader.js is what the build tool makes: undoing I.K.E.'s
    changes gives back Dark Reader's own text, and every change is in it once."""
    from ike.config import RES_DIR
    tool = build_tool()
    engine = (RES_DIR / "darkreader.js").read_bytes().decode()
    for name, old, new in tool.PATCHES:
        new, old = new.replace("\n", "\r\n"), old.replace("\n", "\r\n")
        assert engine.count(new) == 1, name
        engine = engine.replace(new, old)
    assert engine.count(tool.PROXY_EVENT) == 1


# The families kept because their gain was measured (2026-11-21: four against
# all of 1.1.20's changes, five more when added back to a build with fewer
# changes), and what the families dropped for no measurable gain left in the
# engine (their names and their "I.K.E.:" notes): none of it may come back
# unmeasured.
KEPT_FAMILIES = ("shadow-host-walk", "color-variables", "style-groups", "shadow-texts",
                 "dark-copy", "shadow-styles-once", "declarations-modifiable", "variables-none",
                 "style-moves")
DROPPED_MARKS = (
    "ikeSVGRect", "ikeWithSVGRects", "ikePendingSVG",                               # svg-sizes
    "ikeSheets", "the list is changed here and set once",                         # adopted-once
    "ikeAnyImageSelector",                                                        # image-selectors
    "one loop, the same text as filter",                                          # inline-style-key
    "ikeRuleText", "ikeWriteAll", "ikeGroupText",                                   # one-text
    "ikeVarRuleTexts",                                                            # var-rule-same-text
    "ikeMatchedSheets", "ikeNewSheet",                                             # adopted-vars-first
)


def test_the_engine_has_only_the_measured_changes():
    """The shipped engine carries the changes of the nine measured families
    and nothing of the ones dropped: every "I.K.E.:" note in it is one of a
    kept change, each once."""
    import re
    from ike.config import RES_DIR
    tool = build_tool()
    families = {name for name, _old, _new in tool.PATCHES}
    assert {f for f in KEPT_FAMILIES if any(n == f or n.startswith(f + "-") for n in families)} == set(KEPT_FAMILIES)
    assert all(any(n == f or n.startswith(f + "-") for f in KEPT_FAMILIES) for n in families), families
    engine = (RES_DIR / "darkreader.js").read_bytes().decode()
    notes = re.findall(r"// I\.K\.E\.:[^\r\n]*", engine)
    kept_notes = [m for _n, _o, new in tool.PATCHES for m in re.findall(r"// I\.K\.E\.:[^\n]*", new)]
    assert notes and sorted(notes) == sorted(kept_notes) and len(set(notes)) == len(notes), notes
    for mark in DROPPED_MARKS:
        assert mark not in engine, mark
        assert all(mark not in new for _n, _o, new in tool.PATCHES), mark


# --- in the browser -------------------------------------------------------------

PAGES = {
    # a strict policy: no inline script at all; the page's own script adds its styles
    # through the CSSOM (insertRule) and as a constructed style sheet
    "/csp": ("<!doctype html><html><head><title>csp</title><script src='/app.js'></script></head>"
             "<body><div id='a' class='box'>insertRule</div><div id='b' class='adopted'>adopted</div>"
             "<p style='height:400px'>text</p></body></html>",
             {"Content-Security-Policy": "script-src 'self'; style-src 'self' 'unsafe-inline'"}),
    "/app.js": ("document.addEventListener('DOMContentLoaded', function () {"
                "  var s = document.createElement('style'); document.head.appendChild(s);"
                "  s.sheet.insertRule('.box { background-color: rgb(255, 255, 255); color: rgb(0, 0, 0); height: 60px }', 0);"
                "  var c = new CSSStyleSheet();"
                "  c.replaceSync('.adopted { background-color: rgb(250, 250, 250); color: rgb(10, 10, 10); height: 60px }');"
                "  document.adoptedStyleSheets = [c];"
                "  document.title = 'ready';"
                "});", {"Content-Type": "application/javascript"}),
    # a site with a dark theme of its own
    "/dark": ("<!doctype html><html><head><title>dark</title><style>html,body{background:#121212;color:#eee}"
              "main{height:600px}</style></head><body><main><h1>Own dark theme</h1><p>Some text here.</p>"
              "<p>More text.</p></main></body></html>", {}),
    # an ordinary light page
    "/light": ("<!doctype html><html><head><title>light</title><style>body{background:#fff;color:#111}"
               "main{height:600px}</style></head><body><main><h1>Light</h1><p>Text.</p></main></body></html>", {}),
}


@pytest.fixture
def site():
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            body, headers = PAGES.get(self.path.split("?")[0], ("", {}))
            if not body:
                self.send_response(404)
                self.end_headers()
                return
            data = body.encode()
            self.send_response(200)
            self.send_header("Content-Type", headers.get("Content-Type", "text/html; charset=utf-8"))
            for k, v in headers.items():
                if k != "Content-Type":
                    self.send_header(k, v)
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


STEPS = JS + r'''
SITE = "__SITE__"
READ = """JSON.stringify({
  dr: document.querySelectorAll('style.darkreader, .darkreader--sync').length,
  html: getComputedStyle(document.documentElement).backgroundColor,
  a: document.getElementById('a') ? getComputedStyle(document.getElementById('a')).backgroundColor : null,
  b: document.getElementById('b') ? getComputedStyle(document.getElementById('b')).backgroundColor : null,
  body: getComputedStyle(document.body).backgroundColor,
  title: document.title})"""

def steps(ike, qapp, out):
    win = ike.windows[0]
    view = win.current_view()
    yield 500
    for name in ("csp", "dark", "light"):
        yield from load(view, SITE + "/" + name)
        yield 2500
        out[name] = json.loads((yield from js(view, READ)))
        # the page itself cannot start Dark Reader's proxy: its event carries a token of the session
        out[name]["page_starts_proxy"] = (yield from js(view,
            "document.dispatchEvent(new CustomEvent('__darkreader__stylesheetProxy__arg', {detail: {}})); "
            "document.documentElement.dataset.darkreaderProxyInjected === 'true'"))
'''


def lightness(css):
    import re
    m = re.match(r"rgba?\((\d+), (\d+), (\d+)", css or "")
    if not m:
        return None
    r, g, b = (int(x) for x in m.groups())
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255


def test_dark_mode_on_for_every_site(run_ike, site):
    steps = STEPS.replace("__SITE__", site)
    out = run_ike(steps, settings={"dark_mode": "on", "dark_engine": "reader"}, timeout=150)
    # the first site opened from the new tab page is dark too (a script of the page alone
    # missed it when the engine started the site in another process)
    csp = out["csp"]
    assert csp["title"] == "ready" and csp["dr"] > 0, csp
    # the styles the page made itself, under a policy that blocks inline scripts, are darkened too
    assert lightness(csp["a"]) < 0.3, csp
    assert lightness(csp["b"]) < 0.3, csp
    # a site with its own dark theme is recognised and left as it is
    dark = out["dark"]
    assert dark["dr"] == 0 and dark["body"] == "rgb(18, 18, 18)", dark
    assert dark["page_starts_proxy"] is False
    # an ordinary light page is made dark
    assert out["light"]["dr"] > 0 and lightness(out["light"]["body"]) < 0.3, out["light"]


def test_a_site_turned_dark_by_hand_is_always_dark(run_ike, site):
    """Dark mode off, the site on its own list: no detector, no list can undo the user's choice."""
    steps = STEPS.replace("__SITE__", site)
    out = run_ike(steps, settings={"dark_mode": "off", "dark_engine": "reader", "dark_sites": ["127.0.0.1"]},
                  timeout=150)
    assert out["dark"]["dr"] > 0
    assert out["csp"]["dr"] > 0 and lightness(out["csp"]["a"]) < 0.3


def test_dark_mode_off_changes_nothing(run_ike, site):
    out = run_ike(STEPS.replace("__SITE__", site), settings={"dark_mode": "off", "dark_engine": "reader"},
                  timeout=150)
    assert out["light"]["dr"] == 0 and out["light"]["body"] == "rgb(255, 255, 255)"
    assert out["csp"]["dr"] == 0 and out["csp"]["a"] == "rgb(255, 255, 255)"
    assert json.dumps(out["dark"]["body"]) == '"rgb(18, 18, 18)"'


# --- what Dark Reader darkens (I.K.E.'s changes to its engine keep all of it) ------

CASES = r"""<!doctype html><html><head><title>cases</title>
<style>
body { background: #fff; color: #111 }
.box { background-color: rgb(255, 255, 255); color: rgb(0, 0, 0); height: 30px }
#fixvar { background-color: #fff; height: 20px }
.mv { background-color: rgb(255, 255, 254); height: 20px }
.img1 { height: 64px; background-repeat: no-repeat; background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='64' height='64'><rect width='64' height='64' fill='white'/></svg>") }
.img2 { height: 64px; background-repeat: no-repeat; background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='64' height='64'><rect width='64' height='64' fill='white'/></svg>") }
.img3 { height: 64px; background-repeat: no-repeat; background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='64' height='64'><rect width='64' height='64' fill='white'/></svg>") }
</style>
<style id="moved">.mv { background-color: rgb(254, 254, 254) }</style>
</head><body>
<div id="plain" class="box">plain</div>
<div id="inline" style="background-color: rgb(250, 250, 250); color: rgb(10, 10, 10); height: 30px">inline</div>
<div id="fixvar">fix</div>
<div id="mv" class="mv">moved style</div>
<svg id="icon" width="16" height="16"><path id="iconpath" d="M0 0h16v16H0z" fill="#000000"/></svg>
<svg id="chart" width="300" height="200"><rect id="bigrect" width="300" height="200" fill="#ffffff"/>
<rect id="smallrect" x="1" y="1" width="10" height="10" fill="#ffffff"/>
<line id="line" x1="0" y1="0" x2="300" y2="200" stroke="#000000"/></svg>
<div id="dsd"><template shadowrootmode="open"><style>.d { background-color: #fff; height: 20px }</style>
<div class="d" id="dsdin">declarative shadow root</div></template></div>
<div id="host"></div>
<iframe id="frame" src="/frame" width="300" height="100"></iframe>
<script src="/cases.js"></script>
</body></html>"""

CASES_JS = r"""
window.addEventListener('load', function () {
  // a shadow root with its own style element, an inline style and an adopted style sheet
  var root = document.getElementById('host').attachShadow({mode: 'open'});
  root.innerHTML = '<style>.s { background-color: #fff; color: #000; height: 30px }</style>' +
    '<div class="s" id="sdiv">shadow</div><div id="sinline" style="background-color: #ffffff; height: 30px">x</div>' +
    '<div class="a" id="sadopted">adopted</div>';
  var sheet = new CSSStyleSheet();
  sheet.replaceSync('.a { background-color: rgb(253, 253, 253); color: rgb(0, 0, 0); height: 30px }');
  root.adoptedStyleSheets = [sheet];
  // a colour the page shows only now, from a style element added now
  var st = document.createElement('style');
  st.textContent = '.newc { background-color: rgb(255, 250, 240); color: rgb(5, 5, 5); height: 30px }';
  document.head.appendChild(st);
  var d = document.createElement('div'); d.className = 'newc'; d.id = 'newc'; d.textContent = 'new colour';
  document.body.appendChild(d);
  // a chart drawn after the page loaded: big shapes are backgrounds, small ones are like text
  var ns = 'http://www.w3.org/2000/svg', svg = document.createElementNS(ns, 'svg');
  svg.setAttribute('width', '300'); svg.setAttribute('height', '200');
  [['dynbig', 0, 0, 300, 150], ['dynsmall', 2, 2, 8, 8], ['dynsmall2', 20, 2, 8, 8]].forEach(function (r) {
    var e = document.createElementNS(ns, 'rect');
    e.id = r[0]; e.setAttribute('x', r[1]); e.setAttribute('y', r[2]);
    e.setAttribute('width', r[3]); e.setAttribute('height', r[4]); e.setAttribute('fill', '#fafafa');
    svg.appendChild(e);
  });
  document.body.appendChild(svg);
  setTimeout(function () {
    // fill colours changed later; a large change of the page; a style element moved
    // to the end of the head (its rules now come later, Dark Reader's copy must follow)
    document.getElementById('dynbig').setAttribute('fill', '#f0f0f0');
    document.getElementById('dynsmall').setAttribute('fill', '#f0f0f0');
    var many = document.createElement('div');
    for (var i = 0; i < 1200; i++) many.appendChild(document.createElement('span'));
    document.body.appendChild(many);
    for (var j = 0; j < 1100; j++) document.body.appendChild(document.createElement('i'));
    document.head.appendChild(document.getElementById('moved'));
    // elements for background-image rules that matched nothing until now
    var img = document.createElement('div'); img.className = 'img2'; img.id = 'img2';
    document.body.appendChild(img);
    document.title = 'ready';
  }, 600);
});
"""

FRAME = ("<!doctype html><html><head><style>body { background: #fff; color: #000 }</style></head>"
         "<body><p id='fp'>frame</p></body></html>")

CASE_STEPS = JS + r'''
SITE = "__SITE__"
READ = """(function () {
  function cs(el) { return el ? getComputedStyle(el) : null; }
  var root = document.getElementById('host').shadowRoot, dsd = document.getElementById('dsd').shadowRoot;
  var fdoc = document.getElementById('frame').contentDocument;
  var moved = document.getElementById('moved');
  var rootStyle = getComputedStyle(document.documentElement);
  return JSON.stringify({
    title: document.title,
    body: cs(document.body).backgroundColor,
    plain: [cs(document.getElementById('plain')).backgroundColor, cs(document.getElementById('plain')).color],
    inline: [cs(document.getElementById('inline')).backgroundColor, cs(document.getElementById('inline')).color],
    fixvar: cs(document.getElementById('fixvar')).backgroundColor,
    rootvar: rootStyle.getPropertyValue('--darkreader-background-ffffff').trim(),
    newcvar: rootStyle.getPropertyValue('--darkreader-background-fffaf0').trim(),
    newc: [cs(document.getElementById('newc')).backgroundColor, cs(document.getElementById('newc')).color],
    mv: cs(document.getElementById('mv')).backgroundColor,
    img2: cs(document.getElementById('img2')).backgroundImage.slice(0, 40),
    movedcopy: !!(moved.nextElementSibling && moved.nextElementSibling.classList.contains('darkreader--sync')),
    icon: cs(document.getElementById('iconpath')).fill,
    bigrect: cs(document.getElementById('bigrect')).fill,
    smallrect: cs(document.getElementById('smallrect')).fill,
    line: cs(document.getElementById('line')).stroke,
    dynbig: cs(document.getElementById('dynbig')).fill,
    dynsmall: cs(document.getElementById('dynsmall')).fill,
    dynsmall2: cs(document.getElementById('dynsmall2')).fill,
    sdiv: [cs(root.getElementById('sdiv')).backgroundColor, cs(root.getElementById('sdiv')).color],
    sinline: cs(root.getElementById('sinline')).backgroundColor,
    sadopted: [cs(root.getElementById('sadopted')).backgroundColor, cs(root.getElementById('sadopted')).color],
    dsdin: dsd ? cs(dsd.getElementById('dsdin')).backgroundColor : null,
    frame: fdoc ? [getComputedStyle(fdoc.body).backgroundColor, getComputedStyle(fdoc.getElementById('fp')).color]
                : null
  });
})()"""

def steps(ike, qapp, out):
    from ike import darkfixes
    common = darkfixes.fix_for
    def fix_for(url):
        # a site's fix that names a colour variable without a fallback, as some in the list do
        fix = dict(common(url))
        fix["css"] = ((fix.get("css") or "")
                      + "\n#fixvar { background-color: var(--darkreader-background-ffffff) !important; }")
        return fix
    darkfixes.fix_for = fix_for
    view = ike.windows[0].current_view()
    yield 500
    yield from load(view, SITE + "/cases")
    for _ in range(40):
        yield 250
        if (yield from js(view, "document.title")) == "ready":
            break
    yield 2500
    out.update(json.loads((yield from js(view, READ))))
'''


def test_what_dark_reader_darkens(run_ike, site):
    """Every kind of content Dark Reader darkens is still darkened with I.K.E.'s
    changes to its engine: style sheets, inline styles, SVG shapes (big ones as
    backgrounds, small ones as text, as Dark Reader tells them apart), content
    added after the page loaded, a style element the page moves, shadow roots
    (made by script or declared in the page) with their style elements, inline
    styles and adopted style sheets, a frame of the same site, and a site's fix
    that names a colour variable."""
    PAGES["/cases"] = (CASES, {})
    PAGES["/cases.js"] = (CASES_JS, {"Content-Type": "application/javascript"})
    PAGES["/frame"] = (FRAME, {})
    out = run_ike(CASE_STEPS.replace("__SITE__", site), settings={"dark_mode": "on", "dark_engine": "reader"},
                  timeout=150)
    assert out.get("title") == "ready", out

    def dark(c):
        return lightness(c) is not None and lightness(c) < 0.3

    def light(c):
        return lightness(c) is not None and lightness(c) > 0.6
    assert dark(out["body"]), out
    for key in ("plain", "inline", "newc", "sdiv", "sadopted", "frame"):
        bg, fg = out[key]
        assert dark(bg) and light(fg), (key, out[key])
    for key in ("mv", "sinline", "dsdin", "bigrect", "dynbig"):
        assert dark(out[key]), (key, out[key])
    # a light background image whose rule matched nothing until the element came is replaced
    assert out["img2"].startswith('url("data:image/svg+xml;base64,'), out["img2"]
    # small shapes take the colour of text: white stays light, black becomes light
    for key in ("icon", "smallrect", "dynsmall", "dynsmall2"):
        assert light(out[key]), (key, out[key])
    assert out["line"] != "rgb(0, 0, 0)" and lightness(out["line"]) > 0.3, out["line"]
    # the moved style element's copy followed it
    assert out["movedcopy"], out
    # the fix's variable is defined; a colour no fix names needs no variable on :root
    assert dark(out["fixvar"]) and out["rootvar"], out
    assert out["newcvar"] == "", out


# --- identical style elements share one Dark Reader copy (the cascade is unchanged) --

ICON = "<svg class='icon' width='16' height='16'><style>.ic { fill: #464646 }</style><path class='ic' d='M0 0h16v16H0z'/></svg>"
GROUPS = ("<!doctype html><html><head><title>groups</title>"
          "<style>.m { height: 10px }</style></head><body>"
          "<div id='icons'>" + ICON * 5 + "<svg id='x1'><style>.ic { fill: #eeeeee }</style></svg>"
          + ICON.replace("class='icon'", "class='icon' id='i6'") + "</div>"
          "<svg><style>.ref1 { fill: #464646 }</style><path id='ref1' class='ref1' d='M0 0h1v1H0z'/></svg>"
          "<svg><style>.ref2 { fill: #eeeeee }</style><path id='ref2' class='ref2' d='M0 0h1v1H0z'/></svg>"
          "<style media='(min-width: 1px)'>.m { background-color: #fafafa }</style>"
          "<style media='(min-width: 1px)'>.m { background-color: #fafafa }</style>"
          "<style>.m { background-color: #ff0000 }</style>"
          "<style media='(min-width: 1px)'>.m { background-color: #fafafa }</style>"
          "<style media='(min-width: 1px)'>.mref { background-color: #fafafa }</style>"
          "<style>.mref2 { background-color: #ff0000 }</style>"
          "<div id='m' class='m'>m</div><div id='mref' class='mref' style='height: 10px'>ref</div>"
          "<div id='mref2' class='mref2' style='height: 10px'>ref</div>"
          "<div id='host'></div><script src='/groups.js'></script></body></html>")

GROUPS_JS = r"""
var SICON = "<svg class='sicon' width='16' height='16'><style>.sc { fill: #464646 }</style><path class='sc' d='M0 0h16v16H0z'/></svg>";
var shadow = document.getElementById('host').attachShadow({mode: 'open'});
shadow.innerHTML = SICON + SICON + "<svg><style>.sc { fill: #eeeeee }</style></svg>" + SICON;
function groupStyles() {
  return Array.prototype.filter.call(document.querySelectorAll('svg.icon > style'), function (s) {
    return s.textContent === '.ic { fill: #464646 }';
  });
}
window.phase = function (n) {
  var icons = document.getElementById('icons'), x1 = document.getElementById('x1');
  if (n === 1) {       // the last identical one moved before a different rule that it overrode
    icons.insertBefore(document.getElementById('i6'), x1);
    shadow.appendChild(document.createRange().createContextualFragment("<svg><style>.sc { fill: #eeeeee }</style></svg>"));
  } else if (n === 2) {   // a new identical one after it
    var t = document.createElement('template'); t.innerHTML = "<svg class='icon' id='i7' width='16' height='16'><style>.ic { fill: #464646 }</style><path class='ic' d='M0 0h16v16H0z'/></svg>";
    icons.appendChild(t.content);
    var u = document.createElement('template'); u.innerHTML = SICON; shadow.appendChild(u.content);
  } else if (n === 3) {   // that one removed again
    document.getElementById('i7').remove();
  } else if (n === 4) {   // texts changed: the different rule's, and the last of a group's
    x1.querySelector('style').textContent = '.ic { fill: #464646 }';
    document.querySelectorAll('style[media="(min-width: 1px)"]')[2].textContent = '.m { background-color: #ff0000 }';
  } else if (n === 5) {   // a rule added through the CSSOM to the last identical one
    x1.remove();
    var g = groupStyles(); g[g.length - 1].sheet.insertRule('.ic { fill: #eeeeee }', 1);
    var ms = document.querySelectorAll('style[media="(min-width: 1px)"]'); ms[2].sheet.insertRule('.m { background-color: #ff0000 }', 1);
  } else if (n === 6) {   // a large change of the page that also puts the first icon last
    var many = document.createElement('div');
    for (var i = 0; i < 1500; i++) many.appendChild(document.createElement('span'));
    document.body.appendChild(many);
    icons.appendChild(icons.querySelector('svg.icon'));
  }
  document.title = 'phase' + n;
};
document.title = 'phase0';
"""

GROUP_STEPS = JS + r'''
SITE = "__SITE__"
READ = """(function () {
  function fill(el) { return getComputedStyle(el).fill; }
  var shadow = document.getElementById('host').shadowRoot;
  var copies = Array.prototype.filter.call(document.querySelectorAll('svg.icon > style'), function (s) {
    return s.nextElementSibling && s.nextElementSibling.classList.contains('darkreader--sync');
  }).length;
  return JSON.stringify({
    title: document.title,
    ic: Array.prototype.map.call(document.querySelectorAll('path.ic'), fill),
    sc: Array.prototype.map.call(shadow.querySelectorAll('path.sc'), fill),
    ref1: fill(document.getElementById('ref1')), ref2: fill(document.getElementById('ref2')),
    m: getComputedStyle(document.getElementById('m')).backgroundColor,
    mref: getComputedStyle(document.getElementById('mref')).backgroundColor,
    mref2: getComputedStyle(document.getElementById('mref2')).backgroundColor,
    icons: document.querySelectorAll('svg.icon').length, copies: copies
  });
})()"""

def steps(ike, qapp, out):
    view = ike.windows[0].current_view()
    yield 500
    yield from load(view, SITE + "/groups")
    yield 2000
    out["phases"] = [json.loads((yield from js(view, READ)))]
    for n in range(1, 7):
        yield from js(view, "phase(%d)" % n)
        yield 1200
        out["phases"].append(json.loads((yield from js(view, READ))))
'''


def test_identical_style_elements_share_one_copy(run_ike, site):
    """Many identical style elements (an SVG icon repeated, as on the
    Complex-DOM pages of Speedometer) share one Dark Reader copy, after the
    last of them; the colours are those of the rule that wins in the page's
    own cascade, also when the page moves, adds or removes them, puts a
    different rule between them, changes their text or their rules, inside a
    shadow root and with a media attribute."""
    PAGES["/groups"] = (GROUPS, {})
    PAGES["/groups.js"] = (GROUPS_JS, {"Content-Type": "application/javascript"})
    out = run_ike(GROUP_STEPS.replace("__SITE__", site), settings={"dark_mode": "on", "dark_engine": "reader"},
                  timeout=150)
    phases = out.get("phases")
    assert phases and len(phases) == 7, out
    # which rule wins in the page's own cascade, phase by phase (#464646 -> ref1, #eeeeee -> ref2);
    # in phase 5 Dark Reader itself does not follow a rule added through the CSSOM to an SVG
    # style element, so its copy (#464646) still wins, as without I.K.E.'s change
    expect_ic = ["ref1", "ref2", "ref1", "ref2", "ref1", "ref1", "ref1"]
    expect_m = ["mref"] * 4 + ["mref2"] * 3
    expect_sc = ["ref1", "ref2", "ref1", "ref1", "ref1", "ref1", "ref1"]
    for n, p in enumerate(phases):
        assert p["title"] == "phase%d" % n, p
        assert p["ref1"] != p["ref2"] and p["ref1"] != "rgb(70, 70, 70)", p
        assert set(p["ic"]) == {p[expect_ic[n]]}, (n, p)
        assert set(p["sc"]) == {p[expect_sc[n]]}, (n, p)
        assert p["m"] == p[expect_m[n]] and lightness(p["m"]) < 0.3, (n, p)
    # one copy for the five-to-seven identical icons, not one each
    assert phases[0]["icons"] == 6 and phases[0]["copies"] == 1, phases[0]


# --- groups and disabled style elements (1.1.18 review) --------------------------
# The same page twice: once with identical style elements (they share one copy)
# and once with each text made unique by a comment (no group: Dark Reader's own
# behaviour, one copy each). Every phase must give the same colours in both.
def disabled_page(unique):
    def st(i, text, sid=""):
        body = text + ("/*%d*/" % i if unique else "")
        return "<style%s>%s</style>" % (" id='%s'" % sid if sid else "", body)
    light, red = ".d { background-color: #fafafa }", ".d { background-color: #ff0000 }"
    return ("<!doctype html><html><head><title>disabled</title></head><body>"
            + st(1, light, "s1") + st(2, red, "r") + st(3, light, "s3") + st(4, light, "s4")
            + "<div id='d' class='d' style='height: 10px'>d</div>"
            "<script src='/disabled.js'></script></body></html>")


DISABLED_JS = r"""
var UNIQUE = /\/\*\d+\*\//.test(document.getElementById('s1').textContent);
var n = 10;
function light() { n++; var s = document.createElement('style');
  s.textContent = '.d { background-color: #fafafa }' + (UNIQUE ? '/*' + n + '*/' : ''); return s; }
document.getElementById('s4').disabled = true;          // the last one starts disabled
window.phase = function (k) {
  var s1 = document.getElementById('s1'), s3 = document.getElementById('s3'), s4 = document.getElementById('s4');
  if (k === 1) { s3.disabled = true; }                  // every identical one after the red rule disabled
  else if (k === 2) { s3.sheet.disabled = false; s4.sheet.disabled = false; s1.sheet.disabled = true; } // CSSOM
  else if (k === 3) { document.body.insertBefore(s1, document.getElementById('d')); }  // a disabled one moved last
  else if (k === 4) { s4.remove(); s3.remove(); }                             // enabled ones removed
  else if (k === 5) { var s = light(); s.disabled = true; document.body.insertBefore(s, document.getElementById('d'));
                      s1.disabled = false; }                                    // a disabled one added
  else if (k === 6) { var a = light(); document.head.appendChild(a); a.disabled = true;   // added, disabled at once
                      document.body.insertBefore(document.getElementById('r'), document.getElementById('d')); }
  document.title = 'phase' + k;
};
document.title = 'phase0';
"""

DISABLED_STEPS = JS + r'''
SITE = "__SITE__"
READ = """JSON.stringify({title: document.title, d: getComputedStyle(document.getElementById('d')).backgroundColor,
  styles: Array.prototype.map.call(document.querySelectorAll('style:not(.darkreader)'), function (s) {
    return (s.id || '-') + (s.sheet && s.sheet.disabled ? ':off' : ':on'); }).join(' ')})"""

def steps(ike, qapp, out):
    view = ike.windows[0].current_view()
    yield 500
    for page in ("same", "unique"):
        yield from load(view, SITE + "/disabled-" + page)
        yield 2000
        rows = [json.loads((yield from js(view, READ)))]
        for k in range(1, 7):
            yield from js(view, "phase(%d)" % k)
            yield 1200
            rows.append(json.loads((yield from js(view, READ))))
        out[page] = rows
'''


def test_groups_with_disabled_style_elements_change_no_colour(run_ike, site):
    """Identical style elements with different enabled states (the disabled
    property, also through the CSSOM), moved, removed, added disabled: the
    colours with the shared copy are exactly those of Dark Reader's own one
    copy per element, in every phase."""
    PAGES["/disabled-same"] = (disabled_page(False), {})
    PAGES["/disabled-unique"] = (disabled_page(True), {})
    PAGES["/disabled.js"] = (DISABLED_JS, {"Content-Type": "application/javascript"})
    out = run_ike(DISABLED_STEPS.replace("__SITE__", site),
                  settings={"dark_mode": "on", "dark_engine": "reader"}, timeout=150)
    same, unique = out.get("same"), out.get("unique")
    assert same and unique and len(same) == len(unique) == 7, out
    for k, (a, b) in enumerate(zip(same, unique)):
        assert a["title"] == b["title"] == "phase%d" % k, (a, b)
        assert a["styles"] == b["styles"], (k, a, b)            # the same states in both pages
        assert a["d"] == b["d"], ("a colour changed by the shared copy", k, a, b)


# --- groups and style elements filled through the CSSOM (CSS-in-JS) ----------------
# emotion / MUI and styled-components make empty <style> elements and fill them
# with sheet.insertRule: the texts are the same (empty, or a common base) and
# the rules differ. Such elements must never share a copy. The same page twice,
# as above: "same" as those libraries write it, "unique" with a comment in each
# text, which never groups (Dark Reader's own one copy per element).
def cssinjs_page(unique):
    boxes = "".join("<div id='%s' class='%s' style='height: 10px'>%s</div>" % (c, c, c) for c in "abcdefghijklmnop")
    return ("<!doctype html><html><head><title>cssinjs</title><script>var UNIQUE = %s;</script>"
            "<script src='/cssinjs.js'></script></head><body>" % ("true" if unique else "false")
            + boxes + "<script>document.title = 'phase0';</script></body></html>")


CSSINJS_JS = r"""
var n = 0;
function filled(cls, text) {              // a style element made by script, its rule added through the CSSOM
  var s = document.createElement('style');
  s.textContent = (text || '') + (UNIQUE ? '/*' + (++n) + '*/' : '');
  document.head.appendChild(s);
  if (cls) s.sheet.insertRule('.' + cls + ' { background-color: #fff; color: #000 }', s.sheet.cssRules.length);
  return s;
}
// while the page loads: empty texts, then a common text, each with a rule of its own
filled('a'); filled('b'); filled('c');
filled('d', '.base { margin: 0 }'); filled('e', '.base { margin: 0 }'); filled('f', '.base { margin: 0 }');
var later = [];
window.phase = function (k) {
  if (k === 1) {            // the same after the page loaded
    filled('g'); filled('h'); filled('i');
    filled('j', '.base { margin: 0 }'); filled('k', '.base { margin: 0 }'); filled('l', '.base { margin: 0 }');
    later = [filled(''), filled(''), filled('m'), filled('m')];      // two empty ones, two really identical ones
  } else if (k === 2) {     // rules added later to elements that were empty or identical until now
    later[0].sheet.insertRule('.n { background-color: #fff; color: #000 }', 0);
    later[1].sheet.insertRule('.o { background-color: #fff; color: #000 }', 0);
    later[2].sheet.insertRule('.p { background-color: #fff; color: #000 }', 1);
  } else if (k === 3) {     // a rule replaced by another one: the number of rules stays the same
    later[3].sheet.deleteRule(0);
    later[3].sheet.insertRule('.m { background-color: #000; color: #fff }', 0);
  }
  document.title = 'phase' + k;
};
"""

CSSINJS_STEPS = JS + r'''
SITE = "__SITE__"
READ = """(function () {
  var boxes = {};
  Array.prototype.forEach.call(document.querySelectorAll('body > div'), function (d) {
    var cs = getComputedStyle(d); boxes[d.id] = [cs.backgroundColor, cs.color]; });
  return JSON.stringify({title: document.title, boxes: boxes,
    styles: document.querySelectorAll('head > style:not(.darkreader)').length,
    copies: document.querySelectorAll('head > style.darkreader--sync').length});
})()"""

def steps(ike, qapp, out):
    view = ike.windows[0].current_view()
    yield 500
    for page in ("same", "unique"):
        yield from load(view, SITE + "/cssinjs-" + page)
        yield 2000
        rows = [json.loads((yield from js(view, READ)))]
        for k in range(1, 4):
            yield from js(view, "phase(%d)" % k)
            yield 1200
            rows.append(json.loads((yield from js(view, READ))))
        out[page] = rows
'''


def test_style_elements_filled_through_the_cssom_keep_their_own_copies(run_ike, site):
    """Style elements with the same text and different rules (CSS-in-JS: an
    empty element filled with insertRule) each keep their own Dark Reader copy:
    every box is dark, while the page loads and after it, also when the rules
    come later or are replaced, and the colours are those of Dark Reader's own
    one copy per element."""
    PAGES["/cssinjs-same"] = (cssinjs_page(False), {})
    PAGES["/cssinjs-unique"] = (cssinjs_page(True), {})
    PAGES["/cssinjs.js"] = (CSSINJS_JS, {"Content-Type": "application/javascript"})
    out = run_ike(CSSINJS_STEPS.replace("__SITE__", site),
                  settings={"dark_mode": "on", "dark_engine": "reader"}, timeout=150)
    same, unique = out.get("same"), out.get("unique")
    assert same and unique and len(same) == len(unique) == 4, out
    ruled = ["abcdef", "abcdefghijklm", "abcdefghijklmnop", "abcdefghijklmnop"]     # boxes with a rule
    for k, (a, b) in enumerate(zip(same, unique)):
        assert a["title"] == b["title"] == "phase%d" % k, (a, b)
        assert a["styles"] == b["styles"] == (6 if k == 0 else 16), (k, a, b)
        assert a["boxes"] == b["boxes"], ("a colour changed by the shared copy", k, a, b)
        for box in ruled[k]:
            bg, fg = a["boxes"][box]
            assert lightness(bg) < 0.3 and lightness(fg) > 0.6, (k, box, a["boxes"])
    # the reference: one copy for each element
    assert [b["copies"] for b in unique] == [6, 16, 16, 16], unique
    # only the really identical ones share a copy (the two empty elements and the two ".m"
    # ones), until the page changes the rules of one of them
    assert [a["copies"] for a in same] == [6, 14, 16, 16], same
