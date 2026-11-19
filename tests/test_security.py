"""Regression tests of the 1.0.3 security review (docs/review/): each one
simulates the attack or the fault on this computer only (local files, a local
web server), never against another site."""

import json
import os
import socket
import stat
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from conftest import APP, ROOT, needs_engine

JS = r'''
import json

def js(view, code):
    box = {}
    view.page().runJavaScript(code, lambda r: box.setdefault("r", r))
    for _ in range(200):
        if "r" in box:
            break
        yield 20
    return box.get("r")

def load(view, url):
    from PyQt6.QtCore import QUrl
    done = {}
    def finished(ok):
        done.setdefault("ok", ok)
    view.page().loadFinished.connect(finished)
    view.load(QUrl(url) if isinstance(url, str) else url)
    for _ in range(300):
        if "ok" in done:
            break
        yield 20
    view.page().loadFinished.disconnect(finished)
    yield 400
    return done.get("ok")
'''


# ----------------------------------------------------------------------
# a page opened from a file
# ----------------------------------------------------------------------
PROBE = '''<!doctype html><title>%(title)s</title>
<link rel="stylesheet" href="%(css)s"><body>
<img id="pic" src="%(img)s"><div id="styled"></div>
%(frames)s
<script src="%(script)s"></script>
<script>
window.res = {fetch: {}, xhr: {}, frame: {}};
function tryFetch(name, url) {
  fetch(url).then(function (r) { return r.text(); }).then(function (t) { res.fetch[name] = t.slice(0, 40); })
    .catch(function () { res.fetch[name] = "blocked"; });
  var x = new XMLHttpRequest();
  x.onload = function () { res.xhr[name] = x.responseText.slice(0, 40); };
  x.onerror = function () { res.xhr[name] = "blocked"; };
  try { x.open("GET", url); x.send(); } catch (e) { res.xhr[name] = "blocked"; }
}
%(fetches)s
window.addEventListener("load", function () {
  var pic = document.getElementById("pic");
  res.img = [pic.naturalWidth, pic.naturalHeight];
  res.css = document.getElementById("styled").offsetWidth;
  res.script = window.scriptRan === true;
  document.querySelectorAll("iframe").forEach(function (f) {
    try { res.frame[f.id] = f.contentDocument.body.innerText.slice(0, 40); }
    catch (e) { res.frame[f.id] = "blocked"; }
  });
});
</script>'''


def _png(width, height):
    """A valid one-colour PNG picture of the given size."""
    import struct
    import zlib

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    rows = b"".join(b"\x00" + b"\xc0\x20\x20" * width for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


def _local_site(root):
    """A folder tree with a "secret" outside the page's folder:

        root/secret.txt, root/outside.html, root/shared/{pic.png,style.css,code.js}
        root/site/page.html           the page under test
        root/site/own/inner.html      inside the page's folder
        root/site/own/link.html  ->   root/secret.txt   (a link that leaves the folder)
        root/downloads/page.html, root/downloads/other.html, root/downloads/page_files/part.html
    """
    png = _png(3, 5)
    for d in ("shared", "site/own", "downloads/page_files"):
        (root / d).mkdir(parents=True)
    (root / "secret.txt").write_text("TOP-SECRET-KEY-MATERIAL")
    (root / "outside.html").write_text("<!doctype html><body>OUTSIDE-PAGE-TEXT</body>")
    (root / "shared/pic.png").write_bytes(png)
    (root / "shared/style.css").write_text("#styled{width:123px;height:4px;display:block}")
    (root / "shared/code.js").write_text("window.scriptRan = true;")
    (root / "site/own/inner.html").write_text("<!doctype html><body>OWN-FOLDER-TEXT</body>")
    os.symlink(root / "secret.txt", root / "site/own/link.html")
    (root / "downloads/other.html").write_text("<!doctype html><body>ANOTHER-DOWNLOAD</body>")
    (root / "downloads/page_files/part.html").write_text("<!doctype html><body>SAVED-PART</body>")
    common = {"css": "../shared/style.css", "img": "../shared/pic.png", "script": "../shared/code.js"}
    (root / "site/page.html").write_text(PROBE % dict(
        common, title="site",
        frames='<iframe id="own" src="own/inner.html"></iframe><iframe id="outside" src="../outside.html"></iframe>'
               '<iframe id="secret" src="../secret.txt"></iframe><iframe id="link" src="own/link.html"></iframe>'
               '<iframe id="etc" src="file:///etc/hostname"></iframe><iframe id="dir" src="../"></iframe>',
        fetches='tryFetch("secret", "../secret.txt"); tryFetch("own", "own/inner.html");'
                'tryFetch("etc", "file:///etc/hostname"); tryFetch("self", "page.html");'))
    (root / "downloads/page.html").write_text(PROBE % dict(
        common, title="download",
        frames='<iframe id="sibling" src="other.html"></iframe><iframe id="part" src="page_files/part.html"></iframe>',
        fetches='tryFetch("sibling", "other.html");'))


def test_reach_of_a_local_page(tmp_path):
    from ike.shields import local_file_in_reach as reach
    _local_site(tmp_path)
    page = str(tmp_path / "site/page.html")
    assert reach(page, str(tmp_path / "site/own/inner.html"))
    assert reach(page, str(tmp_path / "site/other.html")) and reach(page, page)
    assert not reach(page, str(tmp_path / "outside.html"))
    assert not reach(page, str(tmp_path / "site/../secret.txt"))
    assert not reach(page, str(tmp_path / "site/own/link.html"))          # the link leads outside
    assert not reach(page, "/etc/passwd") and not reach(page, str(tmp_path))
    assert not reach(page, str(tmp_path / "site-other/x.html"))           # a folder whose name only starts the same
    assert not reach("", "/etc/passwd") and not reach(page, "") and not reach(page, "/etc/pass\0wd")
    # a page lying directly in a shared folder gets only its "<name>_files" folder
    shared = {str(tmp_path / "downloads")}
    page = str(tmp_path / "downloads/page.html")
    assert reach(page, str(tmp_path / "downloads/page_files/part.html"), shared)
    assert not reach(page, str(tmp_path / "downloads/other.html"), shared)
    assert not reach(page, str(tmp_path / "downloads/other_files/x.html"), shared)
    assert reach(page, str(tmp_path / "downloads/other.html"))            # not shared: the whole folder
    assert not reach(str(tmp_path / "downloads/.html"), str(tmp_path / "downloads/_files/x"), shared)
    from ike.shields import shared_folders
    folders = shared_folders((str(tmp_path / "downloads"),))
    assert os.path.realpath(os.path.expanduser("~")) in folders and "/tmp" in folders and "/" in folders
    assert str(tmp_path / "downloads") in folders


def test_a_local_page_cannot_read_other_files(run_ike, tmp_path):
    root = tmp_path / "files"
    root.mkdir()
    _local_site(root)
    # a PDF, to check that the engine's own viewer still gets its file
    out = run_ike(JS + r'''
import os
ROOT = %r

def steps(ike, qapp, out):
    from PyQt6.QtCore import QUrl
    from PyQt6.QtGui import QPageSize, QPainter, QPdfWriter
    win = ike.windows[0]
    view = win.current_view()
    yield from load(view, QUrl.fromLocalFile(ROOT + "/site/page.html"))
    yield 1200
    out["site"] = json.loads((yield from js(view, "JSON.stringify(res)")))
    out["site_title"] = view.title()
    # from the page, a link to another local page still opens it
    yield from js(view, "location.href = '../outside.html'; 1")
    yield 1200
    out["followed"] = [view.url().fileName(), (yield from js(view, "document.body.innerText"))]
    yield from load(view, QUrl.fromLocalFile(ROOT + "/downloads/page.html"))
    yield 1200
    out["download"] = json.loads((yield from js(view, "JSON.stringify(res)")))
    writer = QPdfWriter(ROOT + "/doc.pdf")
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A6))
    p = QPainter(writer)
    p.drawText(200, 400, "pdf")
    p.end()
    ok = yield from load(view, QUrl.fromLocalFile(ROOT + "/doc.pdf"))
    out["pdf"] = [ok, view.title(), view.url().fileName()]
''' % str(root), settings={"download_dir": str(root / "downloads")}, timeout=150)
    site = out["site"]
    assert out["site_title"] == "site"
    # what a page needs to look right still loads, from anywhere
    assert site["img"] == [3, 5] and site["css"] == 123 and site["script"] is True
    # reading files with fetch / XMLHttpRequest: never, not even in its own folder
    assert set(site["fetch"].values()) == {"blocked"} and len(site["fetch"]) == 4, site["fetch"]
    assert set(site["xhr"].values()) == {"blocked"} and len(site["xhr"]) == 4, site["xhr"]
    # frames: its own folder yes, everything else no
    assert site["frame"]["own"] == "OWN-FOLDER-TEXT"
    for name in ("outside", "secret", "link", "etc", "dir"):
        assert site["frame"][name] in ("blocked", ""), (name, site["frame"])
    assert "TOP-SECRET" not in json.dumps(site) and "OUTSIDE-PAGE" not in json.dumps(site)
    assert out["followed"] == ["outside.html", "OUTSIDE-PAGE-TEXT"]
    down = out["download"]
    assert down["img"] == [3, 5] and down["css"] == 123 and down["script"] is True
    assert down["frame"]["part"] == "SAVED-PART"                      # the saved page's own parts
    assert down["frame"]["sibling"] in ("blocked", "")                # another download next to it
    assert down["fetch"] == {"sibling": "blocked"} and "ANOTHER-DOWNLOAD" not in json.dumps(down)
    assert out["pdf"][0] is True and out["pdf"][2] == "doc.pdf"


# ----------------------------------------------------------------------
# I.K.E.'s own addresses
# ----------------------------------------------------------------------
OUTSIDER = b"""<!doctype html><title>outsider</title><body>
<img id="logo" src="ike:logo"><iframe id="tab" src="ike:newtab"></iframe>
<iframe id="boxed" sandbox="allow-scripts" srcdoc="<img id=i src='ike:logo' onload='parent.postMessage(&quot;sandbox:loaded&quot;,&quot;*&quot;)' onerror='parent.postMessage(&quot;sandbox:blocked&quot;,&quot;*&quot;)'>"></iframe>
<form id="f" action="ike:search" method="get" target="hidden"><input name="q" value="from-the-outsider"></form>
<iframe name="hidden" id="hidden"></iframe>
<script>
window.res = {};
var logo = document.getElementById("logo");
logo.onload = function () { res.logo = [logo.naturalWidth, logo.naturalHeight]; };
logo.onerror = function () { res.logo = "blocked"; };
if (logo.complete) res.logo = logo.naturalWidth ? [logo.naturalWidth, logo.naturalHeight] : "blocked";
addEventListener("message", function (e) { if (String(e.data).indexOf("sandbox:") === 0) res.sandbox = e.data.slice(8); });
fetch("ike:newtab").then(function () { res.fetch = "loaded"; }).catch(function () { res.fetch = "blocked"; });
var css = document.createElement("link"); css.rel = "stylesheet"; css.href = "ike:newtab";
css.onload = function () { res.css = "loaded"; }; css.onerror = function () { res.css = "blocked"; };
document.head.appendChild(css);
document.getElementById("f").submit();
</script></body>"""


@pytest.fixture
def web():
    """A local web server: "/" is the page of an outsider; it also plays the
    search engine and notes every request it gets."""
    seen = []

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append(self.path)
            if self.path.startswith("/search"):
                body = b"<!doctype html><title>results</title>ok"
            elif self.path.startswith("/ask"):
                body = (b"<!doctype html><title>ask</title><script>window.asked = [];"
                        b"function ask() { Notification.requestPermission().then(function (r) { asked.push(r); }); }"
                        b"</script>")
            else:
                body = OUTSIDER
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield "http://127.0.0.1:%d" % srv.server_address[1], seen
    srv.shutdown()


def test_a_web_page_cannot_use_the_ike_addresses(run_ike, web):
    """A site must not recognise the browser by loading its logo, nor show the
    user's new tab page inside its own page, nor drive its search."""
    base, seen = web
    engines = [{"name": "Local", "url": base + "/search?q={q}", "keyword": "l"}]
    out = run_ike(JS + r'''
BASE = %r

def steps(ike, qapp, out):
    from PyQt6.QtCore import QUrl
    from ike import shields
    asked = []
    original = shields.IkeSchemeHandler.requestStarted
    def watch(self, job):
        asked.append([job.requestUrl().toString().split("?")[0], job.initiator().toString()[:16],
                      shields.IkeSchemeHandler.own_request(job)])
        original(self, job)
    shields.IkeSchemeHandler.requestStarted = watch
    win = ike.windows[0]
    view = win.current_view()
    yield 1200
    # the new tab page itself is untouched: logo, and its search box
    out["newtab"] = yield from js(view, "(function () { var i = document.querySelector('img');"
                                       " return [location.href, i.complete && i.naturalWidth]; })()")
    yield from js(view, "document.querySelector('input').value = 'hello world';"
                       " document.querySelector('form').submit(); 1")
    yield 1500
    out["searched"] = [view.url().toString(), view.title()]
    # the outsider
    yield from load(view, BASE + "/")
    yield 2000
    out["outsider"] = json.loads((yield from js(view, "JSON.stringify(res)")))
    out["frame"] = yield from js(view, "(function () { try { return document.getElementById('tab')"
                                      ".contentDocument ? 'readable' : 'opaque'; } catch (e) { return 'opaque'; } })()")
    # it sends the whole tab there
    yield from js(view, "location.href = 'ike:newtab'; 1")
    yield 1200
    out["sent_tab"] = [view.url().toString(), view.title()]
    # a page made of a data: address tries too
    yield from load(view, "data:text/html,<title>data</title><img id=i src='ike:logo'>")
    yield 800
    out["data_page"] = yield from js(view, "document.getElementById('i').naturalWidth")
    out["asked"] = asked
    # the user's own ways in still work: address bar, home, a new tab
    win.navigate("ike:newtab")
    yield 1200
    out["typed"] = [view.url().toString(), (yield from js(view, "document.querySelector('img').naturalWidth"))]
    other = win.add_tab()
    yield 1200
    out["new_tab"] = [other.url().toString(), (yield from js(other, "document.querySelector('img').naturalWidth"))]
''' % base, settings={"search_engines": engines, "default_engine": "Local", "https_only": False}, timeout=150)
    assert out["newtab"][0] == "ike:newtab" and out["newtab"][1] > 0
    assert out["searched"][1] == "results" and "/search?q=hello%20world" in seen, (out["searched"], seen)
    res = out["outsider"]
    assert res["logo"] == "blocked" and res["fetch"] == "blocked" and res["css"] == "blocked", res
    assert res.get("sandbox") == "blocked", res
    assert out["frame"] == "opaque"
    assert out["data_page"] == 0
    assert out["sent_tab"][1] != "I.K.E."                              # the tab did not land on the new tab page
    assert not any("from-the-outsider" in path for path in seen), seen  # its form never reached the search engine
    outsiders = [a for a in out["asked"] if not a[2]]
    assert {a[0] for a in outsiders} >= {"ike:logo", "ike:newtab", "ike:search"}
    assert all(a[1].startswith(("http://127.0.0.1", "null", "data")) for a in outsiders), outsiders
    assert out["typed"][0] == "ike:newtab" and out["typed"][1] > 0
    assert out["new_tab"][0] == "ike:newtab" and out["new_tab"][1] > 0


# ----------------------------------------------------------------------
# the filter engine fails
# ----------------------------------------------------------------------
@needs_engine
def test_a_failing_filter_engine_never_stops_the_browser(run_ike, web):
    base, _seen = web
    out = run_ike(JS + r'''
BASE = %r

def steps(ike, qapp, out):
    import adblock
    from ike import blocker as blocker_module
    win = ike.windows[0]
    view = win.current_view()
    b = ike.blocker
    yield 600
    out["engine_at_start"] = b.engine is not None
    # 1. the engine reports a fault on every call (what the module answers when
    #    the Rust library panics): requests go through, the fault is counted
    class Faulty:
        def __getattr__(self, name):
            def call(*a, **k):
                raise RuntimeError("the filter engine failed in %%s: boom" %% name)
            return call
    real = b.engine
    b.engine = Faulty()
    before = b.errors
    out["action"] = b.request_action(BASE + "/x.js", BASE + "/", "script")
    out["css"] = list(b.cosmetic_css(BASE + "/"))[0]
    out["generic"] = b.generic_css(["a"], ["b"], set())
    ok = yield from load(view, BASE + "/ask")
    out["page_loaded"] = [ok, view.title()]
    out["counted"] = b.errors - before
    b.engine = real
    # 2. building the engine fails (a list the library cannot digest)
    for old in blocker_module.CACHE_DIR.glob("engine-*.dat"):
        old.unlink()
    real_engine, real_set = adblock.Engine, adblock.FilterSet
    class BadEngine:
        def __init__(self, *a, **k):
            raise RuntimeError("the filter engine failed in Engine: boom")
    adblock.Engine = BadEngine
    before = b.errors
    ike.config["custom_filters"] = "||first-list.example.test^"     # something changed: the engine is built anew
    b.load()
    out["no_engine"] = [b.engine is None, b.errors - before]
    ok = yield from load(view, BASE + "/ask?again")
    out["page_without_engine"] = [ok, view.title()]
    # 3. one list cannot be read: the others still make an engine
    adblock.Engine = real_engine
    calls = []
    class PickySet:
        def __init__(self, *a, **k):
            self.real = real_set(*a, **k)
        def add_filter_list(self, text, *a, **k):
            calls.append(len(text))
            if len(calls) == 1:
                raise RuntimeError("the filter engine failed in add_filter_list: boom")
            return self.real.add_filter_list(text, *a, **k)
    adblock.FilterSet = PickySet
    adblock.Engine = lambda fs, *a: real_engine(fs.real if isinstance(fs, PickySet) else fs, *a)
    ike.config["custom_filters"] = "||second-list.example.test^"
    before = b.errors
    b.load()                              # (cache name changes with the filters)
    adblock.FilterSet, adblock.Engine = real_set, real_engine
    out["rebuilt"] = [b.engine is not None, len(calls) >= 2, b.errors - before,
                      b.should_block("https://second-list.example.test/a.js", BASE + "/", "script")]
    # the real module answers a request it cannot read with an error value, not an exception
    r = real_engine(real_set()).check_network_urls("not a url", "", "script")
    out["unreadable"] = [r.matched, bool(r.error)]
''' % base, timeout=120)
    assert out["engine_at_start"]
    assert out["action"] == ["allow", None] and out["css"] == "" and out["generic"] == ""
    assert out["page_loaded"] == [True, "ask"] and out["counted"] >= 3
    assert out["no_engine"][0] is True and out["no_engine"][1] >= 1
    assert out["page_without_engine"] == [True, "ask"]
    assert out["rebuilt"] == [True, True, 1, True]
    assert out["unreadable"] == [False, True]


# ----------------------------------------------------------------------
# a second start hands its addresses to the running browser
# ----------------------------------------------------------------------
def test_hand_over_message_is_checked():
    from ike.app import handed_over
    assert handed_over(b'{"urls": ["https://a.example/"], "private": false}') == (["https://a.example/"], False)
    assert handed_over(b'{"urls": [], "private": true}') == ([], True)
    assert handed_over(b'{"private": "yes"}') == ([], False)
    urls, _private = handed_over(json.dumps({"urls": ["ok", 5, None, ["x"], "", "y" * 30000] + ["u"] * 300}).encode())
    assert urls[0] == "ok" and set(urls[1:]) == {"u"} and len(urls) <= 100
    for bad in (b"", b"[]", b"null", b"5", b'"text"', b"{", b"\xff\xfe", b'{"urls": "https://a/"}',
                b'{"urls": {"0": "x"}}'):
        assert handed_over(bad) is None, bad


def test_instance_socket_is_private_to_the_user(run_ike, tmp_path, monkeypatch):
    import shutil
    import tempfile

    from ike import app
    run = Path(tempfile.mkdtemp(prefix="ikr"))     # short: a socket path cannot be long
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(run))
    first, legacy = app.instance_addresses()
    assert first[0] == str(run / ("ike-browser-%d-default.sock" % os.getuid())) and first[1] is False
    assert not os.path.isabs(legacy[0])
    # the old place: a socket of another user with the expected name is not ours
    squat = Path(tempfile.gettempdir()) / legacy[0]
    if not squat.exists() and os.getuid() == 0:
        s = socket.socket(socket.AF_UNIX)
        try:
            s.bind(str(squat))
            os.chown(squat, 12345, 12345)
            assert app.instance_addresses()[1][1] is False
            os.chown(squat, 0, 0)
            assert app.instance_addresses()[1][1] is True
        finally:
            s.close()
            squat.unlink()
    # no runtime folder, or one of somebody else: only the old name is left
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "missing"))
    assert [a for a, _ours in app.instance_addresses()] == [legacy[0]]

    # the real thing: the first start listens in the runtime folder, for the user only;
    # a second start hands over its address; rubbish sent to the socket is ignored
    out = run_ike(r'''
import json, os, socket, stat, subprocess, sys
def steps(ike, qapp, out):
    yield 600
    run = os.environ["XDG_RUNTIME_DIR"]
    socks = [n for n in os.listdir(run) if n.endswith(".sock")]
    out["socket"] = socks
    path = os.path.join(run, socks[0])
    out["mode"] = oct(stat.S_IMODE(os.lstat(path).st_mode))
    for rubbish in (b"[]", b"\xff\x00garbage", b'{"urls": 7}', b"null", b""):
        s = socket.socket(socket.AF_UNIX)
        s.connect(path)
        if rubbish:
            s.sendall(rubbish)
        s.close()
        yield 150
    win = ike.windows[0]
    out["tabs_before"] = len(win.views)
    env = dict(os.environ)
    env.pop("IKE_TEST_HOOK", None)
    second = subprocess.run([sys.executable, os.environ["IKE_APP_BOOT"], "data:text/html,<title>handed over</title>x"],
                            env=env, capture_output=True, timeout=60)
    out["second_exit"] = second.returncode
    yield 1500
    out["tabs_after"] = [v.title() for v in win.views]
''', env={"IKE_NO_SINGLE": "", "XDG_RUNTIME_DIR": str(run), "IKE_APP_BOOT": str(APP / "ike_boot.py")}, timeout=120)
    assert out["socket"] == ["ike-browser-%d-default.sock" % os.getuid()]
    assert int(out["mode"], 8) & 0o077 == 0, out["mode"]          # nothing for the group or for others
    assert out["second_exit"] == 0 and out["tabs_before"] == 1
    shutil.rmtree(run, ignore_errors=True)
    assert out["tabs_after"][-1] == "handed over" and len(out["tabs_after"]) == 2


# ----------------------------------------------------------------------
# small things
# ----------------------------------------------------------------------
def test_notification_text_cannot_become_an_option(tmp_path, monkeypatch):
    from ike import osinfo
    log = tmp_path / "argv.json"
    fake = tmp_path / "notify-send"
    fake.write_text("#!%s\nimport json, sys\njson.dump(sys.argv[1:], open(%r, 'w'))\n" % (sys.executable, str(log)))
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", "%s:%s" % (tmp_path, os.environ["PATH"]))
    import time
    shown = []
    for title, text in (("--icon=/etc/passwd", "-u critical"),
                        ("Site", '<a href="https://evil.example/">click</a> <img src="file:///etc/passwd"> & more'),
                        ("", ""), ("x" * 5000, "y" * 50000)):
        if log.exists():
            log.unlink()
        osinfo.notify(title, text)
        for _ in range(100):
            if log.exists() and log.stat().st_size:
                break
            time.sleep(0.05)
        argv = json.loads(log.read_text())
        sep = argv.index("--")
        # the fixed options, "--", then exactly two texts: nothing a page wrote is an option
        assert argv[:sep] == ["-a", "I.K.E.", "-i", "ike-browser"] and len(argv) == sep + 3, argv
        shown_title, shown_text = argv[sep + 1:]
        assert "<" not in shown_text and ">" not in shown_text
        assert len(shown_title) <= 200 and len(shown_text) <= 12000
        shown.append((shown_title, shown_text))
    assert shown[0] == ("--icon=/etc/passwd", "-u critical")
    assert shown[1][1].startswith("&lt;a href=") and "&amp; more" in shown[1][1]
    osinfo.notify("nul\0byte", "x")              # cannot be passed to a program: ignored, no error


def test_switches_that_turn_protections_off_need_a_test_session(monkeypatch):
    from ike.osinfo import test_switch
    monkeypatch.setenv("IKE_TEST_INSECURE", "1")
    monkeypatch.setenv("IKE_TEST_PERMS", "grant")
    monkeypatch.delenv("IKE_TEST_HOOK", raising=False)
    assert test_switch("IKE_TEST_INSECURE") == "" and test_switch("IKE_TEST_PERMS") == ""
    monkeypatch.setenv("IKE_TEST_HOOK", "/some/test.py")
    assert test_switch("IKE_TEST_INSECURE") == "1" and test_switch("IKE_TEST_PERMS") == "grant"
    # the program reads them nowhere else
    for path in (ROOT / "ike").glob("*.py"):
        text = path.read_text("utf-8")
        for name in ("IKE_TEST_INSECURE", "IKE_TEST_PERMS"):
            assert 'environ.get("%s")' % name not in text and 'environ["%s"]' % name not in text, path.name


def test_boot_does_not_follow_a_tampered_state_file(tmp_path, monkeypatch):
    """ike_boot.py runs the copy the updater's notes name. Notes that name
    something that is not a version must never lead to another folder."""
    data = tmp_path / "data"
    updates = data / "ike-browser" / "updates"
    (updates / "versions" / "99.0.0" / "ike").mkdir(parents=True)
    (updates / "versions" / "99.0.0" / "ike" / "__init__.py").write_text('__version__ = "99.0.0"\n')
    evil = tmp_path / "evil" / "ike"
    evil.mkdir(parents=True)
    (evil / "__init__.py").write_text('__version__ = "99.0.0"\nraise SystemExit("evil code ran")\n')
    monkeypatch.setenv("XDG_DATA_HOME", str(data))
    import importlib.util
    spec = importlib.util.spec_from_file_location("ike_boot_under_test", APP / "ike_boot.py")
    boot = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(boot)
    state = updates / "state.json"

    def chosen(notes):
        state.write_text(notes if isinstance(notes, str) else json.dumps(notes))
        return boot.choose()[0]
    assert chosen({"current": "99.0.0", "status": "ok"}) == updates / "versions" / "99.0.0"     # a real one
    for current in ("../../../evil", str(tmp_path / "evil"), "99.0.0/../../../../evil", "", None, 5, ["99.0.0"],
                    {"a": 1}, "99.0.0\n", "99", "v99.0.0", "99.0.0.0.0"):
        assert chosen({"current": current, "status": "ok"}) == boot.SYSTEM_DIR, current
    for notes in ("[]", "null", '"text"', "{", "", "5"):
        assert chosen(notes) == boot.SYSTEM_DIR, notes
    # odd values in the other fields do not stop the start
    assert chosen({"current": "99.0.0", "status": "pending", "attempts": "many", "bad": "x"}) \
        in (updates / "versions" / "99.0.0", boot.SYSTEM_DIR)
    assert boot.version_dir("1.2.3") == updates / "versions" / "1.2.3"
    assert boot.version_dir("../x") is None and boot.version_dir(None) is None


def test_settings_of_the_wrong_kind_fall_back(tmp_path, run_ike):
    from ike.config import DEFAULTS, Config, sound_settings
    rubbish = {"toolbar_hidden": 7, "toolbar_known": "abc", "toolbar_order": {"a": 1}, "search_engines": ["x", 5, {"name": "A", "url": "https://a/?q={q}"}],
               "filter_lists": "none", "site_levels": {"a.example": 3, "b.example": "strict", 4: "off"},
               "site_opts": {"a.example": "no", "b.example": {"ads": False}}, "shield_level": 5,
               "urlbar_width": "wide", "default_zoom": None, "homepage": ["x"], "ui_themes": [],
               "https_only": "yes", "start_maximized": 1, "newtab_clock": 0, "vtabs_width": float("nan"),
               "session": "last", "weather_lat": "north", "something_new": {"kept": True}, 12: "not a name"}
    clean = sound_settings(rubbish)
    assert clean["search_engines"] == [{"name": "A", "url": "https://a/?q={q}"}]
    assert clean["site_levels"] == {"b.example": "strict"} and clean["site_opts"] == {"b.example": {"ads": False}}
    assert clean["start_maximized"] is True and clean["newtab_clock"] is False
    assert clean["weather_lat"] == "north" and clean["something_new"] == {"kept": True}       # no fixed kind / unknown: kept
    for key in ("toolbar_hidden", "toolbar_known", "toolbar_order", "filter_lists", "shield_level", "urlbar_width",
                "default_zoom", "homepage", "ui_themes", "https_only", "vtabs_width", "session", 12):
        assert key not in clean, key
    # sound settings pass unchanged
    assert sound_settings(json.loads(json.dumps(DEFAULTS))) == json.loads(json.dumps(DEFAULTS))
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({k: v for k, v in rubbish.items() if isinstance(k, str)}))
    cfg = Config(path)
    assert isinstance(cfg["toolbar_hidden"], list) and isinstance(cfg["toolbar_known"], list)
    assert cfg["shield_level"] == DEFAULTS["shield_level"] and cfg["urlbar_width"] == DEFAULTS["urlbar_width"]
    assert cfg["homepage"] == DEFAULTS["homepage"] and cfg["filter_lists"] == DEFAULTS["filter_lists"]
    for text in ("[]", "null", '"x"', "{", ""):
        path.write_text(text)
        assert Config(path)["homepage"] == DEFAULTS["homepage"]
    # the browser starts with such a file
    out = run_ike("""
        def steps(ike, qapp, out):
            yield 800
            win = ike.windows[0]
            out["tabs"] = len(win.views)
            out["url"] = win.current_view().url().toString()
            out["level"] = ike.config["shield_level"]
            dlg = ike.show_settings(win)
            yield 300
            out["settings_open"] = dlg.isVisible()
            dlg.close()
    """, settings={k: v for k, v in rubbish.items() if isinstance(k, str) and k not in ("vtabs_width", "filter_lists")})
    assert out["tabs"] == 1 and out["url"].startswith("ike:") and out["level"] == "balanced" and out["settings_open"]


def test_an_error_in_a_handler_does_not_end_the_browser(run_ike):
    out = run_ike("""
        import os
        from PyQt6.QtCore import QTimer

        def steps(ike, qapp, out):
            yield 500
            from ike import app
            win = ike.windows[0]
            out["before"] = len(app.INTERNAL_ERRORS)
            def broken():
                return {}["no such key"]
            QTimer.singleShot(0, broken)                       # a timer's handler fails
            yield 300
            win.act_tb_shot.triggered.disconnect()
            win.act_tb_shot.triggered.connect(lambda *a: 1 / 0)   # ... and the handler of a button
            win.act_tb_shot.trigger()
            yield 200
            win.add_tab("ike:newtab")                          # the browser still does its work
            yield 800
            out["errors"] = len(app.INTERNAL_ERRORS)
            out["kinds"] = sorted({e.strip().splitlines()[-1].split(":")[0] for e in app.INTERNAL_ERRORS})
            out["alive"] = [win.isVisible(), len(win.views)]
            log = os.path.join(os.environ["XDG_CACHE_HOME"], "ike-browser", "errors.log")
            out["log"] = open(log, encoding="utf-8").read()
            out["about"] = win.about_text()
    """, internal_errors=True)
    assert out["before"] == 0 and out["errors"] >= 2
    assert out["kinds"] == ["KeyError", "ZeroDivisionError"]
    assert out["alive"] == [True, 2]
    assert "KeyError" in out["log"] and "ZeroDivisionError" in out["log"] and "--- I.K.E. " in out["log"]
    assert "errors.log" in out["about"] and "Internal errors this session" in out["about"]
    assert out["_exit"] == 0
    assert "internal error, the browser goes on" in out["_stderr"]


def test_about_tells_the_state_of_the_engine(run_ike, monkeypatch):
    from ike.app import sandbox_off
    monkeypatch.delenv("QTWEBENGINE_DISABLE_SANDBOX", raising=False)
    monkeypatch.setenv("QTWEBENGINE_CHROMIUM_FLAGS", "--enable-features=X")
    assert sandbox_off() is False
    monkeypatch.setenv("QTWEBENGINE_CHROMIUM_FLAGS", "--foo --no-sandbox")
    assert sandbox_off() is True
    monkeypatch.setenv("QTWEBENGINE_CHROMIUM_FLAGS", "")
    monkeypatch.setenv("QTWEBENGINE_DISABLE_SANDBOX", "1")
    assert sandbox_off() is True
    monkeypatch.setenv("QTWEBENGINE_DISABLE_SANDBOX", "0")
    assert sandbox_off() is False
    out = run_ike("""
        def steps(ike, qapp, out):
            yield 400
            from PyQt6.QtWebEngineCore import qWebEngineChromiumVersion
            out["about"] = ike.windows[0].about_text()
            out["chromium"] = qWebEngineChromiumVersion()
    """)
    about = out["about"]
    assert out["chromium"] in about and "Qt WebEngine" in about
    assert "Engine sandbox: OFF" in about            # the tests run without it, and About says so
    assert "Internal errors" not in about


def test_a_page_cannot_nag_for_a_permission(run_ike, web):
    """Told no once, a site is not asked about again: neither when its page
    asks over and over, nor after a reload."""
    base, _seen = web
    out = run_ike(JS + r'''
BASE = %r

def steps(ike, qapp, out):
    from ike import webview
    asked = []
    def ask(self, origin, ptype):
        asked.append(origin)
        return False
    webview.WebPage.ask_permission = ask
    win = ike.windows[0]
    view = win.current_view()
    yield from load(view, BASE + "/ask")
    for _ in range(4):
        yield from js(view, "ask(); 1")
        yield 250
    out["first_page"] = [list(asked), (yield from js(view, "asked"))]
    yield from load(view, BASE + "/ask?second")
    for _ in range(3):
        yield from js(view, "ask(); 1")
        yield 250
    out["second_page"] = [len(asked), (yield from js(view, "asked"))]
''' % base, env={"IKE_TEST_PERMS": ""}, timeout=120)
    asked, answers = out["first_page"]
    assert asked == ["127.0.0.1"] and len(answers) == 4 and set(answers) <= {"denied", "default"}, out["first_page"]
    assert out["second_page"][0] == 1 and set(out["second_page"][1]) <= {"denied", "default"}


def test_a_link_never_starts_another_application_without_asking(run_ike):
    """A link such as "mailto:" or the private kind of an installed program
    goes to the desktop only after the user said so, and never from a script
    alone or from a tab in the background."""
    out = run_ike(JS + r'''
from PyQt6.QtCore import QCoreApplication, QEvent, QObject, QPointF, Qt, QUrl, pyqtSlot
from PyQt6.QtGui import QDesktopServices, QMouseEvent

class Desktop(QObject):
    def __init__(self):
        super().__init__()
        self.started = []
    @pyqtSlot(QUrl)
    def handle(self, url):
        self.started.append(bytes(url.toEncoded()).decode())

def click(view, x, y):
    target = view.focusProxy() or view
    for kind, held in ((QEvent.Type.MouseButtonPress, Qt.MouseButton.LeftButton),
                       (QEvent.Type.MouseButtonRelease, Qt.MouseButton.NoButton)):
        QCoreApplication.sendEvent(target, QMouseEvent(kind, QPointF(x, y), QPointF(view.mapToGlobal(QPointF(x, y).toPoint())),
                                                       Qt.MouseButton.LeftButton, held, Qt.KeyboardModifier.NoModifier))

PAGE = ("<body style='margin:0'><a href='iketestproto://run/this?arg=--dangerous%20option' "
        "style='display:block;width:400px;height:120px;background:#ccc'>link</a>")

def steps(ike, qapp, out):
    from ike import webview
    desktop = Desktop()
    ike._desktop_stand_in = desktop
    QDesktopServices.setUrlHandler("iketestproto", desktop, "handle")
    asked = []
    answer = [False]
    def ask(self, origin, url):
        asked.append([origin, bytes(url.toEncoded()).decode()])
        return answer[0]
    webview.WebPage.ask_external = ask
    win = ike.windows[0]
    view = win.current_view()
    view.setHtml(PAGE, QUrl("http://site.example/page"))
    yield 800
    click(view, 60, 60)
    yield 500
    out["refused"] = [list(asked), list(desktop.started), view.url().toString()]
    answer[0] = True
    click(view, 60, 60)
    yield 500
    out["allowed"] = [len(asked), list(desktop.started)]
    # a script alone (no click)
    view.setHtml("<script>setTimeout(function () { location.href = 'iketestproto://by/script'; }, 300);</script>",
                 QUrl("http://site.example/auto"))
    yield 1500
    out["script"] = [len(asked), len(desktop.started)]
    # a tab that is not in view
    view.setHtml(PAGE, QUrl("http://site.example/page"))
    yield 600
    other = win.add_tab("ike:newtab")
    yield 600
    view.page()._external_link(QUrl("iketestproto://from/background"))
    yield 200
    out["background"] = [len(asked), len(desktop.started)]
    # the kinds of address the browser shows itself are never taken for external ones
    own = webview.WebPage.OWN_SCHEMES
    out["own"] = [s in own for s in ("http", "https", "file", "ike", "data", "blob", "about", "view-source")]
    out["external"] = [s in own for s in ("mailto", "tel", "magnet", "ssh", "smb", "steam", "iketestproto")]
''', timeout=120)
    asked, started, url = out["refused"]
    assert asked == [["http://site.example", "iketestproto://run/this?arg=--dangerous%20option"]]
    assert started == [] and url.startswith("http://site.example/")          # the page stays where it was
    assert out["allowed"] == [2, ["iketestproto://run/this?arg=--dangerous%20option"]]
    assert out["script"] == [2, 1]                                           # neither asked nor started
    assert out["background"] == [2, 1]
    assert all(out["own"]) and not any(out["external"])


def test_clearing_site_data_removes_what_sites_stored(run_ike, tmp_path):
    """ "Cookies and site data" must also take away local storage and
    databases: a tracker keeps its identifier there just as well as in a
    cookie. The engine cannot delete them while it runs, so they go when
    I.K.E. starts next; the history, passwords and settings stay."""
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            body = b"<!doctype html><title>store</title><body>page"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    site = "http://127.0.0.1:%d/" % srv.server_address[1]
    read = JS + r'''
import os
SITE = os.environ["IKE_SITE"]

def stored(view):
    yield from js(view, """window._r = null; (async function () {
        var db = await new Promise(function (ok) {
            var q = indexedDB.open('ikedb', 1);
            q.onupgradeneeded = function () { q.result.createObjectStore('s'); };
            q.onsuccess = function () { ok(q.result); }; q.onerror = function () { ok(null); }; });
        var v = db && await new Promise(function (ok) {
            var g = db.transaction('s').objectStore('s').get('id');
            g.onsuccess = function () { ok(g.result || null); }; g.onerror = function () { ok('error'); }; });
        window._r = JSON.stringify([localStorage.getItem('id'), v]); })(); 1""")
    yield 500
    return json.loads((yield from js(view, "window._r")))
'''
    try:
        out = run_ike(read + r'''
def steps(ike, qapp, out):
    view = ike.windows[0].current_view()
    yield from load(view, SITE)
    yield from js(view, """localStorage.setItem('id', 'tracker-1234');
        var q = indexedDB.open('ikedb', 1);
        q.onupgradeneeded = function () { q.result.createObjectStore('s'); };
        q.onsuccess = function () { q.result.transaction('s', 'readwrite').objectStore('s').put('tracker-5678', 'id'); }; 1""")
    yield 800
    out["written"] = yield from stored(view)
''', env={"IKE_SITE": site}, timeout=120)
        assert out["written"] == ["tracker-1234", "tracker-5678"]

        out = run_ike(read + r'''
def steps(ike, qapp, out):
    from ike import sitedata
    view = ike.windows[0].current_view()
    yield from load(view, SITE)
    out["kept"] = yield from stored(view)             # an ordinary restart keeps it
    out["asked_before"] = sitedata.asked()
    ike.clear_data(False, True, False, False)         # "Cookies and site data"
    out["asked"] = sitedata.asked()
''', env={"IKE_SITE": site}, keep_profile=True, timeout=120)
        assert out["kept"] == ["tracker-1234", "tracker-5678"]
        assert out["asked_before"] is False and out["asked"] is True

        out = run_ike(read + r'''
def steps(ike, qapp, out):
    from ike import sitedata
    view = ike.windows[0].current_view()
    out["asked"] = sitedata.asked()
    yield from load(view, SITE)
    out["after"] = yield from stored(view)
    out["history"] = [h[0] for h in ike.storage.history("127.0.0.1", 10)]
''', env={"IKE_SITE": site}, keep_profile=True, timeout=120)
        assert out["after"] == [None, None]
        assert out["asked"] is False                  # done once, not at every start
        assert out["history"]                         # the history was not asked for: still there
    finally:
        srv.shutdown()


def test_clear_when_closed_leaves_no_site_data(run_ike, tmp_path):
    """With "clear when I.K.E. is closed" nothing a site stored survives the session."""
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            body = b"<!doctype html><title>store</title><body>page"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    script = JS + r'''
import os

def steps(ike, qapp, out):
    view = ike.windows[0].current_view()
    yield from load(view, os.environ["IKE_SITE"])
    out["found"] = yield from js(view, "localStorage.getItem('id')")
    yield from js(view, "localStorage.setItem('id', 'tracker-1234'); 1")
    yield 600
'''
    env = {"IKE_SITE": "http://127.0.0.1:%d/" % srv.server_address[1]}
    try:
        first = run_ike(script, settings={"clear_on_exit": True}, env=env, timeout=120)
        left = [p.name for p in (tmp_path / "home/.local/share/ike-browser/profile").glob("Local Storage/leveldb/*.log")
                if b"tracker-1234" in p.read_bytes()]
        second = run_ike(script, settings={"clear_on_exit": True}, env=env, keep_profile=True, timeout=120)
    finally:
        srv.shutdown()
    assert first["found"] is None and second["found"] is None
    assert left == []                                 # already gone from the disk when the browser closed


def test_site_data_is_removed_without_following_links(tmp_path):
    """The clean-up works inside the profile folders only: a link placed there
    is removed itself, what it points to is not touched."""
    from ike import sitedata

    data = tmp_path / "data"
    profile = data / "profile"
    work = data / "containers" / "work"
    for folder in (profile, work):
        (folder / "Local Storage" / "leveldb").mkdir(parents=True)
        (folder / "Local Storage" / "leveldb" / "000003.log").write_text("x")
        (folder / "IndexedDB").mkdir()
        (folder / "Cookies").write_text("x")
        (folder / "History").write_text("history")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "precious.txt").write_text("keep me")
    (profile / "Service Worker").symlink_to(outside)
    (data / "containers" / "linked").symlink_to(outside)        # not a container: a link
    (data / "passwords.json").write_text("vault")

    assert sitedata.at_start(data) is False                      # nothing was asked for
    assert (profile / "Local Storage").exists()
    sitedata.ask(data)
    assert sitedata.asked(data)
    assert sitedata.at_start(data) is True
    for folder in (profile, work):
        assert not (folder / "Local Storage").exists() and not (folder / "IndexedDB").exists()
        assert not (folder / "Cookies").exists()
        assert (folder / "History").read_text() == "history"
    assert not (profile / "Service Worker").is_symlink()
    assert (outside / "precious.txt").read_text() == "keep me"
    assert (data / "passwords.json").read_text() == "vault"
    assert not sitedata.asked(data)


def _self_signed(folder, host="127.0.0.1"):
    """A certificate nobody vouches for, for a local server: (cert file, key file)."""
    import datetime
    import ipaddress

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, host)])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=2))
            .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address(host))]), critical=False)
            .sign(key, hashes.SHA256()))
    cert_file, key_file = folder / "cert.pem", folder / "key.pem"
    cert_file.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_file.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                           serialization.NoEncryption()))
    return cert_file, key_file


@needs_engine
def test_a_server_with_an_untrusted_certificate_is_refused(run_ike, tmp_path):
    """Somebody between the user and the site answers with a certificate of
    their own: the page is not shown, its scripts do not run, and there is no
    way to go on from inside the page."""
    import ssl

    hits = []

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append(self.path)
            body = b"<!doctype html><title>secret page</title><body>SECRET<script>document.title = 'ran';</script>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    cert_file, key_file = _self_signed(tmp_path)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(str(cert_file), str(key_file))
    srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        out = run_ike(JS + r'''
import os

def steps(ike, qapp, out):
    view = ike.windows[0].current_view()
    out["ok"] = yield from load(view, os.environ["IKE_SITE"])
    out["title"] = view.page().title()
    out["text"] = yield from js(view, "document.body ? document.body.innerText : ''")
''', env={"IKE_SITE": "https://127.0.0.1:%d/page" % srv.server_address[1]}, timeout=120)
    finally:
        srv.shutdown()
    assert out["ok"] is False
    assert "SECRET" not in (out["text"] or "") and out["title"] != "ran" and "secret page" not in out["title"]
    assert hits == []                                 # the request was never sent


@needs_engine
def test_a_download_cannot_choose_a_place_outside_the_download_folder(run_ike, tmp_path):
    """A server names its file "../../.bashrc" or an absolute path: the file
    lands in the download folder under a plain name, and nothing is opened."""
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            names = {"/a": '../../.bashrc', "/b": '/tmp/ike-test-absolute.txt', "/c": '..\\..\\evil.desktop'}
            body = b"echo owned\n"
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Disposition", 'attachment; filename="%s"' % names[self.path])
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    folder = tmp_path / "home" / "Downloads"
    try:
        out = run_ike(JS + r'''
import os
from PyQt6.QtCore import QUrl

def steps(ike, qapp, out):
    view = ike.windows[0].current_view()
    for path in ("/a", "/b", "/c"):
        view.load(QUrl(os.environ["IKE_SITE"] + path))
        yield 1500
    out["paths"] = [str(ike.download_path(d)) for d in ike.downloads]
''', settings={"download_dir": str(folder)}, env={"IKE_SITE": "http://127.0.0.1:%d" % srv.server_address[1]},
                      timeout=120)
    finally:
        srv.shutdown()
    assert len(out["paths"]) == 3
    for path in out["paths"]:
        assert Path(path).parent == folder, path
        assert Path(path).exists()
    assert not (tmp_path / "home" / ".bashrc").exists() and not (tmp_path / ".bashrc").exists()
    assert not Path("/tmp/ike-test-absolute.txt").exists()
    assert sorted(p.name for p in folder.iterdir()) == sorted(Path(p).name for p in out["paths"])


def test_password_files_are_private_from_the_start(tmp_path):
    from ike import passwords
    old = os.umask(0)                     # the most permissive creation mask there is
    try:
        target = tmp_path / "export.csv"
        target.write_text("older file")
        target.chmod(0o666)
        seen = []
        real_open = os.open

        def watching(path, flags, mode=0o777, *a, **k):
            fd = real_open(path, flags, mode, *a, **k)
            if str(path).startswith(str(tmp_path)):
                seen.append(oct(stat.S_IMODE(os.fstat(fd).st_mode)))
            return fd
        os.open = watching
        try:
            passwords.write_private(target, "url,username,password\nhttps://a.example,me,secret\n")
            vault = passwords.Vault(tmp_path / "vault.bin")
            vault.create("master")
        finally:
            os.open = real_open
        assert seen and set(seen) == {"0o600"}, seen                 # at the moment each file came to be
        assert oct(stat.S_IMODE(target.stat().st_mode)) == "0o600"
        assert oct(stat.S_IMODE((tmp_path / "vault.bin").stat().st_mode)) == "0o600"
        assert "secret" in target.read_text()
    finally:
        os.umask(old)


def test_a_copied_password_is_marked_secret_and_cleared(run_ike):
    out = run_ike("""
        def steps(ike, qapp, out):
            yield 300
            from PyQt6.QtGui import QGuiApplication
            from ike import passwords
            passwords.CLIPBOARD_SECONDS = 1
            cb = QGuiApplication.clipboard()
            passwords.copy_secret("hunter2-secret")
            out["text"] = cb.text()
            out["hint"] = bytes(cb.mimeData().data("x-kde-passwordManagerHint")).decode()
            yield 1500
            out["after"] = cb.text()
            # something else copied meanwhile is left alone
            passwords.copy_secret("another-secret")
            cb.setText("the user's own text")
            yield 1500
            out["kept"] = cb.text()
    """)
    assert out["text"] == "hunter2-secret" and out["hint"] == "secret"
    assert out["after"] == "" and out["kept"] == "the user's own text"


def test_update_channel_is_one_of_the_known_two(tmp_path, monkeypatch):
    from ike import background, updater
    started = []
    monkeypatch.setattr(background, "start", started.append)
    monkeypatch.setattr(updater, "source", lambda: {"url": "https://updates.example/x", "pubkey": "k"})

    class Cfg(dict):
        def save(self):
            pass
    for stored, used in (("stable", "stable"), ("beta", "beta"), ("../../other", "stable"), ("", "stable"),
                         (None, "stable"), ("stable/../x", "stable"), (7, "stable")):
        up = updater.Updater(Cfg(update_channel=stored))
        assert up.run(install=False) is True
        assert started[-1].channel == used, stored
        up._worker = None


def test_list_conditions_are_read_without_running_code():
    from ike.scriptlets import _pp_eval, preprocess
    truth = {"env_chromium": True, "env_firefox": False, "!env_firefox": True,
             "env_chromium && !cap_html_filtering": True, "env_firefox || env_chromium": True,
             "!(env_firefox || env_safari)": True, "env_mv3": False, "!env_mv3": True,
             "env_chromium && (env_firefox || ext_ublock)": True, "env_firefox&&env_chromium": False,
             "!!env_chromium": True, "env_chromium && env_firefox || ext_ublock": True, "ext_abp": False,
             "cap_user_stylesheet": True, "( env_chromium )": True}
    for text, value in truth.items():
        assert _pp_eval(text) is value, text
    # what cannot be read keeps the rules (true) and is never executed
    marker = Path("/tmp/ike-test-pp-eval-ran")
    if marker.exists():
        marker.unlink()
    for text in ("", "&&", "env_chromium &&", "((env_chromium)", "env_chromium)", "1 == 1", "a.b", "[x]",
                 "__import__('os').system('touch %s')" % marker, "open('%s','w')" % marker,
                 "env_chromium; import os", "(" * 5000 + "x" + ")" * 5000, "!" * 100000 + "x", "x " * 1000):
        assert _pp_eval(text) is True, text[:40]
    assert not marker.exists()
    text = "a\n!#if env_firefox\nfirefox-only\n!#else\nchromium\n!#endif\n!#if env_chromium && !env_mv3\nb\n!#endif\nc"
    assert preprocess(text).split("\n") == ["a", "chromium", "b", "c"]


def test_closing_while_a_download_waits_does_not_abort(run_ike):
    """A background thread still busy when the browser closes used to end the
    program with "QThread: Destroyed while thread is still running" (abort)."""
    out = run_ike("""
        import time
        from PyQt6.QtCore import QThread

        class Waiting(QThread):
            def run(self):
                time.sleep(6)            # a server that does not answer

        class Quick(QThread):
            def run(self):
                pass

        def steps(ike, qapp, out):
            yield 400
            from ike import background
            quick = Quick(ike)
            background.start(quick)
            yield 200
            slow = Waiting(ike)
            ike._waiting = slow
            background.start(slow)
            yield 300
            out["busy"] = [t is slow for t in background.busy()]
    """, timeout=60)
    assert out["busy"] == [True]
    assert out["_exit"] == 0, out["_stderr"][-600:]
    assert "Destroyed while" not in out["_stderr"]


def test_no_private_key_material_or_test_backdoor_in_the_program():
    """What a reviewer would grep for."""
    for path in list((ROOT / "ike").glob("*.py")) + [ROOT / "ike_boot.py"]:
        text = path.read_text("utf-8")
        assert "eval(" not in text.replace("_pp_eval(", ""), path.name
        assert "shell=True" not in text and "os.system(" not in text and "pickle" not in text, path.name
        assert "--disable-web-security" not in text and "--ignore-certificate-errors" not in text, path.name
    # the only place that turns the engine's sandbox off is the start as administrator
    hits = [p.name for p in (ROOT / "ike").glob("*.py") if '"--no-sandbox"' in p.read_text("utf-8")]
    assert hits == ["app.py"]
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    done = subprocess.run([sys.executable, str(APP / "ike_boot.py"), "--version"], env=env, capture_output=True, text=True)
    assert done.returncode == 0 and "I.K.E." in done.stdout


# ----------------------------------------------------------------------
# review of 1.1.17: dark mode's style sheets, user script updates, cookies
# ----------------------------------------------------------------------
@pytest.fixture
def css_server():
    """A local server that plays every site: style sheets, a redirect, and it
    notes each request (through the proxy the path is the whole address)."""
    seen = []

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append(self.path)
            if "/redirect?" in self.path:
                self.send_response(302)
                self.send_header("Location", self.path.split("?", 1)[1])
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            body = b"body{color:#123456}"
            self.send_response(200)
            self.send_header("Content-Type", "text/css")
            self.send_header("Set-Cookie", "track=me; Path=/")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1], seen
    srv.shutdown()


def test_dark_mode_never_reads_the_home_network_for_a_web_site(run_ike, css_server):
    """Dark mode fetches the style sheets a page cannot read itself and puts
    them, restyled, into the page. A web site must not use that to read what
    this computer or a router serves; a page of the home network itself still
    gets its own sheets, and every redirect is checked too."""
    port, seen = css_server
    out = run_ike(r'''
PORT = %d

def steps(ike, qapp, out):
    from PyQt6.QtCore import QObject, QUrl
    from PyQt6.QtNetwork import QNetworkProxy
    from ike.passwords import PageBridge

    class Page(QObject):
        def __init__(self, url, dark=True):
            super().__init__()
            self._url, self._dark_on = QUrl(url), dark

        def url(self):
            return self._url
    # other sites through the local server, as a proxy
    ike.network.setProxy(QNetworkProxy(QNetworkProxy.ProxyType.HttpProxy, "127.0.0.1", PORT))
    local = "http://127.0.0.1:%%d" %% PORT
    cases = {
        "public_to_this_computer": ("https://news.example.test/", local + "/a.css"),
        "public_to_router_name": ("https://news.example.test/", "http://router.example.test/b.css"),
        "public_to_localhost": ("https://news.example.test/", "http://localhost:%%d/c.css" %% PORT),
        "public_to_cdn": ("https://news.example.test/", "http://cdn.example.test/d.css"),
        "redirect_to_home": ("https://news.example.test/",
                             "http://cdn.example.test/redirect?http://192.168.1.1/e.css"),
        "home_page_own_sheet": (local + "/page", local + "/f.css"),
        "dark_off": ("https://news.example.test/", "http://cdn.example.test/g.css"),
    }
    answers, keep = {}, []
    for name, (page_url, css) in cases.items():
        page = Page(page_url, dark=(name != "dark_off"))
        bridge = PageBridge(ike.passwords, page)
        bridge.cssFetched.connect(lambda ident, ok, text: answers.__setitem__(ident, [ok, text]))
        keep.append((page, bridge))
        bridge.fetchCss(name, css)
    for _ in range(300):
        if len(answers) == len(cases):
            break
        yield 20
    out["answers"] = answers
    out["cookies"] = len(ike.network.cookieJar().cookiesForUrl(QUrl("http://cdn.example.test/")))
''' % port, env={"IKE_TEST_RESOLVE": "router.example.test=192.168.1.1"}, timeout=120)
    a = out["answers"]
    for refused in ("public_to_this_computer", "public_to_router_name", "public_to_localhost",
                    "redirect_to_home", "dark_off"):
        assert a[refused] == [False, ""], (refused, a)
    assert a["public_to_cdn"] == [True, "body{color:#123456}"], a
    assert a["home_page_own_sheet"] == [True, "body{color:#123456}"], a
    reached = " ".join(seen)
    for never in ("/a.css", "/b.css", "/c.css", "/g.css"):
        assert never not in reached, seen
    assert not any(path.startswith("http://192.168.1.1") for path in seen), seen   # the redirect's target
    assert "/d.css" in reached and "/f.css" in reached
    assert out["cookies"] == 0                    # the browser's own requests keep no cookies


def test_user_script_updates_that_ask_for_more_need_the_user():
    """The daily check installs a newer version by itself only when it asks
    for nothing new and loads everything over https; otherwise the user is
    asked, as for a new script. Plain http update addresses are not checked."""
    sys.path.insert(0, str(APP))
    try:
        from ike.userscripts import parse_meta, update_needs_consent
    finally:
        sys.path.remove(str(APP))

    def got(extra="", source="https://example.test/s.user.js"):
        text = ("// ==UserScript==\n// @name s\n// @version 2\n// @match https://a.test/*\n"
                "// @grant GM_setValue\n// @connect api.test\n%s// ==/UserScript==\n" % extra)
        return {"meta": parse_meta(text), "source": source}
    old = {"match": ["https://a.test/*"], "include": [], "exclude": [], "grant": ["GM_setValue"],
           "connect": ["api.test"], "noframes": False}
    assert not update_needs_consent(old, got())
    assert not update_needs_consent(old, got("// @require https://cdn.test/lib.js\n"))
    assert not update_needs_consent(old, got("// @require lib.js\n"))        # relative to https
    assert update_needs_consent(old, got("// @require http://cdn.test/lib.js\n"))
    assert update_needs_consent(old, got("// @resource css http://cdn.test/x.css\n"))
    assert update_needs_consent(old, got("// @match https://*/*\n"))
    assert update_needs_consent(old, got("// @include *\n"))
    assert update_needs_consent(old, got("// @grant GM_xmlhttpRequest\n"))
    assert update_needs_consent(old, got("// @connect *\n"))
    assert update_needs_consent(old, got("// @connect bank.test\n"))
    assert update_needs_consent(dict(old, exclude=["https://a.test/private/*"]), got())
    assert update_needs_consent(dict(old, noframes=True), got())
    assert not update_needs_consent(dict(old, connect=[]), got())         # it had any host already
    text = (APP / "ike" / "userscripts.py").read_text()
    assert 'if not url.startswith("https://"):\n                continue' in text
