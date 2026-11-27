"""Page dark mode under a strict Content-Security-Policy (1.1.26).

A site whose policy allows style sheets from itself only (archlinux.org:
"default-src 'self'", others "style-src 'self'") blocks every <style> element
added to the page, the ones Dark Reader adds included: the page stayed light.
Dark mode now gives those styles to the page as constructed style sheets
(adoptedStyleSheets), which such a policy does not block, from the isolated
world of I.K.E.'s scripts, without touching the policy. The page's own
protection is kept: its inline styles stay blocked."""

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from test_security import JS

CSS = ("html, body { background-color: rgb(255, 255, 255); color: rgb(0, 0, 0) }"
       ".box { background-color: rgb(250, 250, 250); color: rgb(20, 20, 20); height: 60px }"
       "a { color: rgb(0, 0, 238) }")
BODY = ("<body><div id='a' class='box'>Some text in a box</div><p id='t'>Text of the page, "
        "<a id='l' href='#'>a link</a></p><div id='inline' style='background-color: rgb(1, 2, 3)'>x</div>"
        "<p style='height:400px'>more text</p></body></html>")


def page(title):
    return ("<!doctype html><html><head><title>%s</title><link rel='stylesheet' href='/site.css'>"
            "<script src='/watch.js'></script></head>" % title + BODY)


PAGES = {
    # as archlinux.org: everything from the site itself, nothing inline
    "/default": (page("default"), {"Content-Security-Policy": "default-src 'self'"}),
    # style sheets from the site only (scripts unrestricted)
    "/style": (page("style"), {"Content-Security-Policy": "style-src 'self'"}),
    # no policy: as before
    "/open": (page("open"), {}),
    # the page sets its own constructed sheets once loaded: the copies stay after them
    "/later": (page("later").replace("</head>", "<script src='/later.js'></script></head>"),
               {"Content-Security-Policy": "default-src 'self'"}),
    "/later.js": ("addEventListener('load', function () { setTimeout(function () {"
                  "  var c = new CSSStyleSheet();"
                  "  c.replaceSync('#a { background-color: rgb(240, 240, 240) } #t { font-weight: bold }');"
                  "  document.adoptedStyleSheets = [c]; document.title = 'later set'; }, 300); });",
                  {"Content-Type": "application/javascript"}),
    # a site with a dark theme of its own under the same policy is recognised and left alone
    "/own": ("<!doctype html><html><head><title>own</title><link rel='stylesheet' href='/own.css'></head>"
             + BODY, {"Content-Security-Policy": "default-src 'self'"}),
    "/own.css": ("html, body { background-color: rgb(18, 18, 18); color: rgb(238, 238, 238) }"
                 "body { min-height: 600px }", {"Content-Type": "text/css"}),
    # a part of the page in an open shadow root, styled by its own sheet: Dark Reader's
    # <style> there is refused too, and its copy goes to the shadow root
    "/shadow": (page("shadow").replace("</head>", "<script src='/shadow.js'></script></head>"),
                {"Content-Security-Policy": "default-src 'self'"}),
    "/shadow.js": ("customElements.define('x-card', class extends HTMLElement { constructor() { super();"
                   "  var r = this.attachShadow({mode: 'open'});"
                   "  r.innerHTML = \"<link rel='stylesheet' href='/site.css'><div id='in' class='box'>"
                   "Text in a shadow root</div>\"; } });"
                   "addEventListener('DOMContentLoaded', function () {"
                   "  document.body.appendChild(document.createElement('x-card')); });",
                   {"Content-Type": "application/javascript"}),
    "/site.css": (CSS, {"Content-Type": "text/css"}),
    # the page counts the policy's refusals it is told of
    "/watch.js": ("window.__refused = [];"
                  "document.addEventListener('securitypolicyviolation', function (e) {"
                  "  window.__refused.push(e.effectiveDirective); });", {"Content-Type": "application/javascript"}),
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
  html: getComputedStyle(document.documentElement).backgroundColor,
  body: getComputedStyle(document.body).backgroundColor,
  text: getComputedStyle(document.getElementById('t')).color,
  a: getComputedStyle(document.getElementById('a')).backgroundColor,
  atext: getComputedStyle(document.getElementById('a')).color,
  link: getComputedStyle(document.getElementById('l')).color,
  inline: getComputedStyle(document.getElementById('inline')).backgroundColor,
  adopted: document.adoptedStyleSheets.length,
  shadow: (function () { var c = document.querySelector('x-card'); if (!c) return null;
    var i = c.shadowRoot.getElementById('in'), st = getComputedStyle(i);
    return {bg: st.backgroundColor, color: st.color, adopted: c.shadowRoot.adoptedStyleSheets.length}; })(),
  styles: document.querySelectorAll('style').length,
  refused: window.__refused || null,
  title: document.title})"""

def steps(ike, qapp, out):
    view = ike.windows[0].current_view()
    yield 500
    for name in ("default", "style", "open", "later", "own", "shadow"):
        yield from load(view, SITE + "/" + name)
        yield 2500
        out[name] = json.loads((yield from js(view, READ)))
'''


def lightness(css):
    import re
    m = re.match(r"rgba?\((\d+), (\d+), (\d+)", css or "")
    if not m:
        return None
    r, g, b = (int(x) for x in m.groups())
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255


def test_dark_mode_under_a_strict_policy(run_ike, site):
    out = run_ike(STEPS.replace("__SITE__", site), settings={"dark_mode": "on", "dark_engine": "reader"},
                  timeout=150)
    for name in ("default", "style", "open"):
        p = out[name]
        assert p["title"] == name, p
        # the page is dark, its text light and readable
        assert lightness(p["body"]) < 0.3 or lightness(p["html"]) < 0.3, (name, p)
        assert lightness(p["a"]) < 0.3, (name, p)
        assert lightness(p["text"]) > 0.6 and lightness(p["atext"]) > 0.6, (name, p)
        assert lightness(p["link"]) > 0.4, (name, p)
    for name in ("default", "style"):
        p = out[name]
        # the page's own protection holds: its inline style stays blocked
        assert p["inline"] == "rgba(0, 0, 0, 0)", (name, p)
        # the styles reached the page as constructed sheets
        assert p["adopted"] > 0, (name, p)
    # without a policy, Dark Reader's own <style> elements, as before
    assert out["open"]["styles"] > 0 and out["open"]["adopted"] == 0, out["open"]
    assert out["open"]["inline"] != "rgba(0, 0, 0, 0)", out["open"]
    # the page's own constructed sheet came later: darkened, and the copies are still there
    later = out["later"]
    assert later["title"] == "later set" and later["adopted"] > 1, later
    assert lightness(later["a"]) < 0.3 and lightness(later["body"]) < 0.3, later
    assert lightness(later["text"]) > 0.6, later
    # a shadow root under the policy: dark inside too, through its own copy
    sh = out["shadow"]
    assert lightness(sh["body"]) < 0.3 and sh["shadow"], sh
    assert lightness(sh["shadow"]["bg"]) < 0.3 and lightness(sh["shadow"]["color"]) > 0.6, sh
    assert sh["shadow"]["adopted"] > 0, sh
    # an own dark theme under the policy: left as it is (the copies were not taken for it)
    own = out["own"]
    assert own["body"] == "rgb(18, 18, 18)" and own["adopted"] == 0, own


def test_dark_mode_off_leaves_a_strict_page_as_it_is(run_ike, site):
    out = run_ike(STEPS.replace("__SITE__", site), settings={"dark_mode": "off", "dark_engine": "reader"},
                  timeout=150)
    for name in ("default", "style", "open"):
        p = out[name]
        assert p["body"] == "rgb(255, 255, 255)" and p["adopted"] == 0 and p["styles"] == 0, (name, p)
        # only the page's own inline style attributes are refused, by its own policy
        assert set(p["refused"]) <= {"style-src-attr"}, (name, p)
    assert out["open"]["refused"] == []
