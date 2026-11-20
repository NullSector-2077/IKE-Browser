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
    (tmp_path / "changed.js").write_bytes(fake_engine(patches, skip="style-moves").encode())
    run = subprocess.run([sys.executable, str(root / "tools/build-darkreader.py"), "--lib", str(tmp_path / "changed.js"),
                          "--config", str(cfg), "--out", str(tmp_path)], capture_output=True, text=True)
    assert run.returncode != 0 and "'style-moves'" in (run.stderr + run.stdout)
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
    # small shapes take the colour of text: white stays light, black becomes light
    for key in ("icon", "smallrect", "dynsmall", "dynsmall2"):
        assert light(out[key]), (key, out[key])
    assert out["line"] != "rgb(0, 0, 0)" and lightness(out["line"]) > 0.3, out["line"]
    # the moved style element's copy followed it
    assert out["movedcopy"], out
    # the fix's variable is defined; a colour no fix names needs no variable on :root
    assert dark(out["fixvar"]) and out["rootvar"], out
    assert out["newcvar"] == "", out
