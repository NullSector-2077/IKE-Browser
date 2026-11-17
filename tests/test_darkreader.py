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
