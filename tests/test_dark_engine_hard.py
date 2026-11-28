"""The I.K.E. Dark Engine on the hard cases of modern sites (an independent review
of round 3): Tailwind's colours with a variable alpha, colour channels in
variables (design systems, shadcn/ui), editors whose text must stay the user's,
gradient text, charts, shadow roots on plain elements, registered custom
properties (@property's initial value), a variable's fallback colour, rules added
later without a node changing, pages that name their
elements like the document's own methods, logical borders, animations, a dark
hero over a light page, and a frame filled by script. Real engine, local pages.
"""

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from test_security import JS

LONG = "<p>" + "Text of the page. " * 200 + "</p>"
PAGES = {
    "tailwind": """<!doctype html><style>
      body{margin:0}
      .bg-white{--tw-bg-opacity:1;background-color:rgb(255 255 255 / var(--tw-bg-opacity))}
      .text-gray-900{--tw-text-opacity:1;color:rgb(17 24 39 / var(--tw-text-opacity))}
      .half{background-color:rgb(255 255 255 / 0.5)}
    </style><div id="box" class="bg-white text-gray-900" style="height:200px">Tailwind card</div>""",
    "channels": """<!doctype html><style>
      :root{--c: 59 130 246; --scale: 1 1 1; --background: 0 0% 100%; --foreground: 222 47% 11%}
      body{background:hsl(var(--background));color:hsl(var(--foreground))}
      .btn{background:rgb(var(--c) / 1);color:#fff;padding:8px}
    </style><p id="text">shadcn text</p><div id="btn" class="btn">Button</div>""",
    "editor": """<!doctype html><style>body{background:#fff;color:#222}</style>
      <div contenteditable="true" id="ed"><p id="edp" style="color: #222222; background-color: #ffffff">Reply text</p>
      <font id="edf" color="#333333">old mail</font></div>""",
    "gradient-text": """<!doctype html><style>body{background:#fff}
      .grad{background:linear-gradient(90deg,#1e3a8a,#7c3aed);-webkit-background-clip:text;background-clip:text;
            color:transparent;font-size:40px}</style><h1 id="g" class="grad">Gradient title</h1>""",
    "chart": """<!doctype html><style>body{background:#fff;color:#222}</style>
      <svg width="400" height="200"><rect id="plot" width="400" height="200" fill="#ffffff"/>
      <text id="label" x="10" y="20" fill="#333333">Label</text><circle id="dot" cx="50" cy="50" r="5" fill="#000000"/></svg>""",
    "shadow-div": """<!doctype html><style>body{background:#fff;color:#222}</style><div id="host"></div>
      <script>var r=document.getElementById('host').attachShadow({mode:'open'});
      r.innerHTML='<style>p{background:#ffffff;color:#222222;padding:10px}</style><p id="in">Consent text</p>';</script>""",
    "clobber": """<!doctype html><style>body{background:#fff;color:#222}.light{background:#f4f4f4;height:100px}</style>
      <img name="querySelectorAll"><img name="querySelector"><form name="head"></form><form name="body"></form>
      <form id="f" style="background:#ffffff"><select name="style"></select></form>
      <div id="box" class="light">Light box</div>""",
    "logical": """<!doctype html><style>body{background:#fff;color:#222}
      .lb{border-inline-start:4px solid #000000;border-block-end:4px solid #000000;padding:10px}</style>
      <div id="lb" class="lb">Logical borders</div>""",
    "keyframes": """<!doctype html><style>body{background:#fff;color:#222}
      @keyframes glow{from{background-color:#ffffff}to{background-color:#fefefe}}
      .anim{animation:glow 60s infinite alternate;height:80px}</style><div id="anim" class="anim">Animated</div>""",
    "hero": """<!doctype html><style>body{background:#fff;color:#222;margin:0}
      .hero{background:#111;color:#fff;height:100vh}</style><div class="hero">Welcome</div>""" + LONG,
    "print": """<!doctype html><style>body{background:#ffffff;color:#222}</style><p>Printed page</p>""",
    "registered": """<!doctype html><style>body{background:#fff;color:#111;margin:0}
      @property --band-bg { syntax: '<color>'; inherits: true; initial-value: #ffffff; }
      @property --card-bg { syntax: '<color>'; inherits: false; initial-value: rgb(250, 250, 250); }
      @property --ink { syntax: '<color>'; inherits: true; initial-value: #222222; }
      .band .inner{background:var(--band-bg);color:var(--ink);height:120px}
      .card{background-color:var(--card-bg);height:60px}
      .own{--band-bg:#fffbe6}</style>
      <div class="band"><div id="band" class="inner">A band of the home page</div></div>
      <div id="card" class="card">Card</div>
      <div class="band own"><div id="own" class="inner">Its own colour</div></div>""",
    "fallback": """<!doctype html><style>body{background:#fff;color:#111;margin:0}
      .band{--band-bg:var(--theme-undefined-bg, #fff)} .band .inner{background:var(--band-bg);height:80px}
      .tile{background:var(--theme-undefined-tile,#f7f7f7);height:40px}</style>
      <div class="band"><div id="band" class="inner">Band</div></div>
      <div class="band" style="--band-bg: var(--theme-undefined-x, #fff)"><div id="band2" class="inner">Band 2</div></div>
      <div id="tile" class="tile">Tile</div>""",
    "gradvar": """<!doctype html><style>body{background:#fff;color:#111;margin:0}
      .p1{background-image:linear-gradient(0deg,#fff,#fff),var(--panel-picture,none);height:60px}
      .p2{background-image:linear-gradient(0deg,var(--u-panel,#fff),var(--u-panel,#fff)),var(--other-picture,none);height:60px}
      </style><div id="p1" class="p1">Panel one</div><div id="p2" class="p2">Panel two</div>""",
    "halo": """<!doctype html><style>body{background:#fff;color:#111;margin:0}
      .card{position:relative;width:400px;height:300px}.card img{position:absolute;inset:0;width:400px;height:300px}
      .card h2{position:absolute;top:20px;left:20px;margin:0;color:#333}</style>
      <div class="card"><img src="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='400' height='300'%3E%3Crect width='400' height='300' fill='%23eeeeee'/%3E%3C/svg%3E">
      <h2 id="over">Ecco la nuova gamma</h2></div><p id="below">A caption under the picture</p>""",
    "late": """<!doctype html><style>body{background:#fff;color:#111;margin:0}</style><style id="js"></style>
      <div id="a" class="a" style="height:40px">a</div><div id="b" class="b" style="height:40px">b</div>
      <div id="c" class="c" style="height:40px">c</div>
      <script>
      setTimeout(function(){ document.getElementById('js').sheet.insertRule('.a{background:var(--u1,#fff)}',0); },800);
      setTimeout(function(){ var s=document.createElement('style'); document.head.appendChild(s);
        setTimeout(function(){ s.sheet.insertRule('.b{background:#fafafa}',0); },50); },300);
      var s3=document.createElement('style'); s3.textContent='.c{background:#000}'; document.head.appendChild(s3);
      setTimeout(function(){ s3.firstChild.data='.c{background:#ffffff}'; },500);
      </script>""",
    "frame": """<!doctype html><style>body{background:#fff;color:#222}</style><iframe id="fr" width="300" height="120"></iframe>
      <script>var d=document.getElementById('fr').contentDocument;
      d.body.innerHTML='<p id="x" style="background:#ffffff;color:#222222">Message in a frame</p>';</script>""",
}


@pytest.fixture
def site():
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            body = PAGES.get(self.path.strip("/").split("?")[0])
            if body is None:
                self.send_error(404)
                return
            data = body.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
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


READS = {
    "tailwind": "var e=document.getElementById('box');var s=getComputedStyle(e);"
                "return {bg:s.backgroundColor,color:s.color}",
    "channels": "var r=document.documentElement;return {body:getComputedStyle(document.body).backgroundColor,"
                "text:getComputedStyle(document.getElementById('text')).color,"
                "btn:getComputedStyle(document.getElementById('btn')).backgroundColor,"
                "scale:getComputedStyle(r).getPropertyValue('--scale').trim()}",
    "editor": "var p=document.getElementById('edp'),f=document.getElementById('edf');"
              "return {style:p.getAttribute('style'),color:getComputedStyle(p).color,bg:getComputedStyle(p).backgroundColor,"
              "font:f.getAttribute('color'),fontColor:getComputedStyle(f).color,html:document.getElementById('ed').innerHTML}",
    "gradient-text": "return {img:getComputedStyle(document.getElementById('g')).backgroundImage}",
    "chart": "return {plot:getComputedStyle(document.getElementById('plot')).fill,"
             "label:getComputedStyle(document.getElementById('label')).fill,"
             "dot:getComputedStyle(document.getElementById('dot')).fill}",
    "shadow-div": "var p=document.getElementById('host').shadowRoot.getElementById('in');"
                  "return {bg:getComputedStyle(p).backgroundColor,color:getComputedStyle(p).color}",
    "clobber": "return {box:getComputedStyle(document.getElementById('box')).backgroundColor,"
               "form:getComputedStyle(document.getElementById('f')).backgroundColor}",
    "logical": "var s=getComputedStyle(document.getElementById('lb'));"
               "return {start:s.borderLeftColor,end:s.borderBottomColor}",
    "keyframes": "return {bg:getComputedStyle(document.getElementById('anim')).backgroundColor}",
    "hero": "return {body:getComputedStyle(document.body).backgroundColor}",
    "print": "dispatchEvent(new Event('beforeprint'));var a=getComputedStyle(document.body).backgroundColor;"
             "dispatchEvent(new Event('afterprint'));var b=getComputedStyle(document.body).backgroundColor;"
             "return {printed:a,after:b}",
    "registered": "function s(i){return getComputedStyle(document.getElementById(i));}"
                  "return {band:s('band').backgroundColor,ink:s('band').color,card:s('card').backgroundColor,"
                  "own:s('own').backgroundColor}",
    "fallback": "function s(i){return getComputedStyle(document.getElementById(i)).backgroundColor;}"
                "return {band:s('band'),band2:s('band2'),tile:s('tile')}",
    "gradvar": "function s(i){return getComputedStyle(document.getElementById(i)).backgroundImage;}"
               "return {p1:s('p1'),p2:s('p2')}",
    "halo": "function s(i){return getComputedStyle(document.getElementById(i)).textShadow;}"
            "return {over:s('over'),below:s('below')}",
    "late": "function s(i){return getComputedStyle(document.getElementById(i)).backgroundColor;}"
            "return {a:s('a'),b:s('b'),c:s('c')}",
    "frame": "var p=document.getElementById('fr').contentDocument.getElementById('x');"
             "return {bg:getComputedStyle(p).backgroundColor,color:getComputedStyle(p).color}",
}

STEPS = JS + r'''
SITE = "__SITE__"
READS = __READS__

def steps(ike, qapp, out):
    view = ike.windows[0].current_view()
    yield 500
    for name, code in READS.items():
        yield from load(view, SITE + "/" + name)
        yield 2500
        out[name] = json.loads((yield from js(view, "JSON.stringify((function(){" + code + "})())")))
'''


def rgb(css):
    m = re.search(r"rgba?\((\d+), (\d+), (\d+)", css or "")
    return tuple(int(x) for x in m.groups()) if m else None


def light(css):
    c = rgb(css)
    return (0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]) / 255


def test_hard_cases(run_ike, site):
    script = STEPS.replace("__SITE__", site).replace("__READS__", json.dumps(READS))
    out = run_ike(script, settings={"dark_mode": "on", "dark_engine": "reader", "dark_engine_experiment": True},
                  timeout=240)
    p = out["tailwind"]
    assert light(p["bg"]) < 0.3 and light(p["color"]) > 0.6, p
    p = out["channels"]
    assert light(p["body"]) < 0.3 and light(p["text"]) > 0.6, p
    assert rgb(p["btn"]) and rgb(p["btn"])[2] > rgb(p["btn"])[0], p            # still a blue button
    assert p["scale"] == "1 1 1", p                                             # not a colour: untouched
    p = out["editor"]
    assert "#222222" in p["style"] or "rgb(34, 34, 34)" in p["style"], p      # the user's own colour is kept
    assert p["font"] == "#333333" and light(p["color"]) > 0.6 and light(p["bg"]) < 0.3, p
    assert light(p["fontColor"]) > 0.6, p
    p = out["gradient-text"]
    first = re.search(r"rgba?\([^)]*\)", p["img"]).group(0)
    assert light(first) > 0.35, p                                               # the title stays visible
    p = out["chart"]
    assert light(p["plot"]) < 0.3 and light(p["label"]) > 0.6 and light(p["dot"]) > 0.6, p
    p = out["shadow-div"]
    assert light(p["bg"]) < 0.3 and light(p["color"]) > 0.6, p
    p = out["clobber"]
    assert light(p["box"]) < 0.3, p
    p = out["logical"]
    assert light(p["start"]) > 0.25 and light(p["end"]) > 0.25, p
    p = out["keyframes"]
    assert light(p["bg"]) < 0.3, p
    p = out["hero"]
    assert light(p["body"]) < 0.3, p                                            # darkened, not left as it is
    p = out["print"]
    assert p["printed"] == "rgb(255, 255, 255)" and light(p["after"]) < 0.3, p    # paper gets the page's colours
    p = out["registered"]                                                       # @property's initial values
    assert light(p["band"]) < 0.3 and light(p["card"]) < 0.3 and light(p["ink"]) > 0.6, p
    assert light(p["own"]) < 0.3 and p["own"] != p["band"], p                  # the page's own value still wins
    p = out["fallback"]                                                         # var(--undefined, #fff)
    assert light(p["band"]) < 0.3 and light(p["band2"]) < 0.3 and light(p["tile"]) < 0.3, p
    p = out["gradvar"]                                    # a gradient next to a variable in the same value
    for k in ("p1", "p2"):
        first = re.search(r"rgba?\([^)]*\)", p[k]).group(0)
        assert light(first) < 0.3, p
    p = out["halo"]                                           # light text over a photo: a dark halo
    assert "rgba(0, 0, 0" in p["over"] and p["below"] == "none", p
    p = out["late"]                                    # insertRule with no node changed, a style's text changed
    assert light(p["a"]) < 0.3 and light(p["b"]) < 0.3 and light(p["c"]) < 0.3, p
    p = out["frame"]
    assert light(p["bg"]) < 0.3 and light(p["color"]) > 0.6, p
