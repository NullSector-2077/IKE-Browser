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
    while b.building:                     # built in the background since 1.1.17
        yield 20
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
    while b.building:
        yield 20
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
# test_notification_text_cannot_become_an_option moved to tests/test_small_1124.py (1.1.24: D-Bus, not notify-send)


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
    assert sandbox_off() is True              # 1.1.18: Qt looks only at whether it is set
    monkeypatch.delenv("QTWEBENGINE_DISABLE_SANDBOX")
    monkeypatch.setenv("QTWEBENGINE_CHROMIUM_FLAGS", '"--no-sandbox"')
    assert sandbox_off() is True              # quoted, as Qt reads it
    monkeypatch.setenv("QTWEBENGINE_CHROMIUM_FLAGS", "-no-sandbox")
    assert sandbox_off() is True              # one dash: the same switch for Chromium
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
from PyQt6.QtGui import QMouseEvent

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
    # 1.1.24: links of other kinds go to the desktop portal (handoff.py), never through
    # Qt's QDesktopServices (xdg-open): the stand-in takes the portal's place
    ike.handoff.open_uri = lambda url, parent=None: desktop.handle(QUrl(url))
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
    # 1.1.24: "evil.desktop" is a program from a site never visited: I.K.E.
    # asks first (safedownload.py, tested in test_safe_downloads.py); here the
    # user downloads it anyway, and its name and place are still I.K.E.'s
    asked = []
    type(ike)._ask_download_risk = lambda self, found, anyway: (asked.append(found["kind"]), anyway())
    view = ike.windows[0].current_view()
    for path in ("/a", "/b", "/c"):
        view.load(QUrl(os.environ["IKE_SITE"] + path))
        yield 1500
    out["paths"] = [str(ike.download_path(d)) for d in ike.downloads]
    out["asked"] = asked
''', settings={"download_dir": str(folder)}, env={"IKE_SITE": "http://127.0.0.1:%d" % srv.server_address[1]},
                      timeout=120)
    finally:
        srv.shutdown()
    assert len(out["paths"]) == 3
    assert out["asked"] == ["new"], out["asked"]
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
        if path.name == "app.py":
            # 1.1.18: the list of switches I.K.E. takes AWAY from the engine
            # (UNSAFE_SWITCHES) names them; nowhere else may they appear
            start = text.index("UNSAFE_SWITCHES = (")
            text = text[:start] + text[text.index(")", start):]
        assert "eval(" not in text.replace("_pp_eval(", ""), path.name
        assert "shell=True" not in text and "os.system(" not in text and "pickle" not in text, path.name
        assert "--disable-web-security" not in text and "--ignore-certificate-errors" not in text, path.name
    # the only place that turns the engine's sandbox off is the start as
    # administrator, and only when the user asked (IKE_ALLOW_UNSAFE_ENGINE=1)
    hits = [p.name for p in (ROOT / "ike").glob("*.py") if '"--no-sandbox"' in p.read_text("utf-8")]
    assert hits == ["app.py"]
    app = (ROOT / "ike" / "app.py").read_text("utf-8")
    assert app.count('flags.append("--no-sandbox")') == 1 and "refuse_root()" in app
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
            seen.append("UA " + self.headers.get("User-Agent", ""))
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
        "public_to_cdn": ("http://news.example.test/", "http://cdn.example.test/d.css"),
        # review of 1.1.19, M4: never in clear for an encrypted page, never
        # what the filter lists block for the page
        "mixed_content": ("https://news.example.test/", "http://cdn.example.test/h.css"),
        "blocked_by_lists": ("http://news.example.test/", "http://ads.example.test/i.css"),
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
    out["ua"] = ike.shields.user_agent()
''' % port, env={"IKE_TEST_RESOLVE": "router.example.test=192.168.1.1"}, timeout=120,
                  settings={"custom_filters": "||ads.example.test^$stylesheet\n"})
    a = out["answers"]
    for refused in ("public_to_this_computer", "public_to_router_name", "public_to_localhost",
                    "redirect_to_home", "dark_off", "mixed_content", "blocked_by_lists"):
        assert a[refused] == [False, ""], (refused, a)
    assert a["public_to_cdn"] == [True, "body{color:#123456}"], a
    assert a["home_page_own_sheet"] == [True, "body{color:#123456}"], a
    reached = " ".join(seen)
    for never in ("/a.css", "/b.css", "/c.css", "/g.css", "/h.css", "/i.css"):
        assert never not in reached, seen
    assert not any(path.startswith("http://192.168.1.1") for path in seen), seen   # the redirect's target
    assert "/d.css" in reached and "/f.css" in reached
    assert out["cookies"] == 0                    # the browser's own requests keep no cookies
    # with the browser's own User-Agent, not Qt's (review of 1.1.19, M4)
    assert {s[3:] for s in seen if s.startswith("UA ")} == {out["ua"]}, seen


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
    known = dict(old, requires=[["https://cdn.test/old.js", ""]])          # a host it already used
    assert not update_needs_consent(known, got("// @require https://cdn.test/lib.js\n"))
    assert not update_needs_consent(dict(old, update="https://example.test/s.user.js"),
                                    got("// @require lib.js\n"))             # next to the script, https
    assert update_needs_consent(old, got("// @require https://cdn.test/lib.js\n"))   # a new host (1.1.17)
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


def test_github_actions_are_pinned_by_commit_hash():
    """The actions the workflows run (tests, automatic fixes, packages) are
    pinned to a commit, not to a tag that can be moved to other code; the
    version is kept as a comment for Dependabot."""
    import re
    root = ROOT / ".github"
    uses = []
    for f in list(root.glob("workflows/*.yml")) + list(root.glob("actions/*/action.yml")):
        for line in f.read_text().splitlines():
            m = re.match(r"\s*-?\s*uses:\s*(\S+)(.*)$", line)
            if m:
                uses.append((f.name, m.group(1), m.group(2)))
    assert uses
    for name, ref, rest in uses:
        if ref.startswith("./"):
            continue                       # this repository's own action
        assert re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", ref), (name, ref)
        assert re.fullmatch(r"\s+# v\d+(\.\d+)*", rest), (name, ref, rest)


def test_a_background_tab_asks_for_a_permission_only_when_shown(run_ike, web):
    """A page in a tab the user is not looking at asks for a permission: the
    question waits until its tab is shown, so it never appears over another
    site's page; asked over and over meanwhile, it is one question."""
    base, _seen = web
    out = run_ike(JS + r'''
BASE = %r

def steps(ike, qapp, out):
    from PyQt6.QtCore import QUrl
    from ike import webview
    asked = []
    def ask(self, origin, ptype):
        asked.append([origin, self.visible_tab()])
        return True
    webview.WebPage.ask_permission = ask
    win = ike.windows[0]
    front = win.current_view()
    back = win.add_tab(QUrl(BASE + "/ask"), background=True)
    for _ in range(100):
        if back.url().toString().endswith("/ask") and not getattr(back, "loading", False):
            break
        yield 50
    yield 800
    for _ in range(3):
        yield from js(back, "ask(); 1")
        yield 300
    yield 1500
    out["while_hidden"] = list(asked)
    out["front"] = win.current_view() is front
    win.set_current(back)
    yield 2000
    out["after_shown"] = list(asked)
    out["answers"] = yield from js(back, "asked")
''' % base, env={"IKE_TEST_PERMS": ""}, timeout=120)
    assert out["front"] and out["while_hidden"] == [], out
    assert out["after_shown"] == [["127.0.0.1", True]], out["after_shown"]
    assert out["answers"] and set(out["answers"]) == {"granted"}, out["answers"]


@pytest.fixture
def files_site():
    """A page that, once loaded, starts three downloads by itself."""
    seen = []
    page = (b"<!doctype html><title>files</title><script>"
            b"window.addEventListener('load', function () {"
            b" ['/f1', '/f2', '/f3'].forEach(function (p, i) { setTimeout(function () {"
            b"  var a = document.createElement('a'); a.href = p; a.download = '';"
            b"  document.body.appendChild(a); a.click(); }, 300 * i); }); });"
            b"</script>")

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append(self.path)
            if self.path.startswith("/f"):
                body = b"file " + self.path.encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Disposition", "attachment; filename=%s.bin" % self.path[1:])
            else:
                body = page
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


@pytest.mark.parametrize("answer", [True, False])
def test_a_site_asks_before_a_burst_of_downloads(run_ike, files_site, tmp_path, answer):
    """A page that starts download after download by itself gets its first
    file; the rest wait for one question. "Allow" brings them all, "Block"
    none. A download right after the user's own action never asks."""
    site, seen = files_site
    folder = tmp_path / "dl"
    out = run_ike(r'''
SITE, ANSWER = %r, %r

def steps(ike, qapp, out):
    from PyQt6.QtCore import QUrl
    from PyQt6.QtWebEngineCore import QWebEnginePage
    asked = []
    def ask(self, site, done):
        asked.append(site)
        done(ANSWER)
    type(ike)._ask_download_burst = ask
    win = ike.windows[0]
    view = win.current_view()
    yield 4000                            # well after the start page the browser opened
    # the page is opened by a script, not by the user: nothing marks it as theirs
    QWebEnginePage.load(view.page(), QUrl(SITE + "/page"))
    for _ in range(150):
        yield 100
        if len([d for d in ike.downloads if d.isFinished()]) >= (3 if ANSWER else 1) and asked:
            break
    yield 1500
    out["asked"] = asked
    out["files"] = sorted(p.name for p in __import__("pathlib").Path(%r).glob("*.bin"))
    # the user's own downloads, one after another: never a question
    before = len(asked)
    for name in ("f1", "f2"):
        view.page().download(QUrl(SITE + "/" + name))
        yield 400
    yield 1000
    out["asked_for_user"] = len(asked) - before
''' % (site, answer, str(folder)), settings={"download_dir": str(folder), "ask_download_location": False},
        timeout=120)
    assert out["asked"] == ["127.0.0.1"], out
    if answer:
        assert out["files"] == ["f1.bin", "f2.bin", "f3.bin"], out
    else:
        assert out["files"] == ["f1.bin"], out
    assert out["asked_for_user"] == 0


# ----------------------------------------------------------------------
# 1.1.17, decided with the owner: address bar code, no silent http, pages on
# the lists, an engine without recent fixes, the passwords window
# ----------------------------------------------------------------------
@pytest.fixture
def plain_site():
    """A local http server; it notes the paths asked for (TLS attempts are not
    requests and are not noted)."""
    seen = []

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append(self.path)
            body = b"<!doctype html><title>plain page</title><p>hello"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

        def log_error(self, *a):
            pass
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1], seen
    srv.shutdown()


def test_code_typed_in_the_address_bar_is_never_run(run_ike, plain_site):
    """"javascript:" typed or pasted in the address bar would run inside the
    site in view (the "paste this to get a gift" scam). It is refused there;
    a bookmark (bookmarklet) still runs its own."""
    port, _seen = plain_site
    out = run_ike(JS + r'''
PORT = %d

def steps(ike, qapp, out):
    win = ike.windows[0]
    view = win.current_view()
    yield from load(view, "http://127.0.0.1:%%d/" %% PORT)
    code = "javascript:void(document.title='pwned-'+document.domain)"
    win.urlbar.setText(code)
    win.urlbar.returnPressed.emit()                  # typed and Enter
    yield 1200
    out["typed"] = view.title()
    win.navigate(code, typed=True)                    # pasted and gone
    yield 1200
    out["pasted"] = view.title()
    win.navigate("javascript:void(document.title='bookmarklet')")    # from a bookmark
    yield 1200
    out["bookmark"] = view.title()
''' % port, settings={"https_only": False}, timeout=90)
    assert out["typed"] == "plain page" and out["pasted"] == "plain page", out
    assert out["bookmark"] == "bookmarklet"


def test_a_failed_secure_address_is_not_left_for_http_silently(run_ike, plain_site):
    """The secure address of a page asked for over http does not answer: the
    page stops with a warning, nothing is fetched over http until the user
    presses "Continue without protection" (until 1.1.17 it went to http by
    itself, which someone on the network can force)."""
    port, seen = plain_site
    out = run_ike(JS + r'''
PORT = %d

def steps(ike, qapp, out):
    from PyQt6.QtCore import QUrl
    win = ike.windows[0]
    view = win.current_view()
    sh = ike.shields
    yield 800
    # as if http://127.0.0.1:PORT had been upgraded by https_only: the server
    # speaks only http, so the secure address fails
    sh.upgraded.add("127.0.0.1")
    yield from load(view, QUrl("https://127.0.0.1:%%d/page" %% PORT))
    yield 1500
    out["bar"] = win.secure_bar.isVisible()
    out["text"] = win.secure_bar.text.text()
    out["url_after_failure"] = view.url().toString()
    out["allowed_before"] = "127.0.0.1" in sh.http_allowed
    win.secure_bar.go.click()
    yield 2000
    out["url_after_click"] = view.url().toString()
    out["title"] = view.title()
    out["bar_after"] = win.secure_bar.isVisible()
''' % port, timeout=90)
    assert out["bar"] and "127.0.0.1" in out["text"], out
    assert out["url_after_failure"].startswith("https://") and out["allowed_before"] is False
    assert out["url_after_click"] == "http://127.0.0.1:%d/page" % port and out["title"] == "plain page"
    assert out["bar_after"] is False
    assert [p for p in seen if p != "/favicon.ico"] == ["/page"], seen    # http only after the click


@needs_engine
def test_a_page_on_the_lists_is_stopped_with_a_way_through(run_ike, plain_site):
    """A whole page that the lists block (a site spreading malware) shows the
    window's warning; "Continue anyway" opens it for this session only."""
    port, seen = plain_site
    out = run_ike(JS + r'''
PORT = %d

def steps(ike, qapp, out):
    win = ike.windows[0]
    view = win.current_view()
    yield 800
    yield from load(view, "http://127.0.0.1:%%d/evil-download" %% PORT)
    yield 800
    out["bar"] = win.secure_bar.isVisible()
    out["text"] = win.secure_bar.text.text()
    out["title_blocked"] = view.title()
    win.secure_bar.go.click()
    yield 2000
    out["title"] = view.title()
    out["allowed"] = sorted(ike.shields.pages_allowed)
''' % port, settings={"https_only": False, "custom_filters": "/evil-download$document"}, timeout=90)
    assert out["bar"] and "127.0.0.1" in out["text"], out
    assert out["title"] == "plain page" and out["allowed"] == ["127.0.0.1"], out
    assert [p for p in seen if p != "/favicon.ico"] == ["/evil-download"], seen   # only after "Continue anyway"


def test_the_malware_list_reaches_new_and_existing_users(tmp_path, monkeypatch):
    """The Malicious URL Blocklist is on by default, and settings of an older
    version get it once (a user who turns it off later keeps it off)."""
    import importlib
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    sys.path.insert(0, str(APP))
    try:
        from ike import config as C
        importlib.reload(C)
        url = "https://malware-filter.gitlab.io/malware-filter/urlhaus-filter-online.txt"
        assert any(e["url"] == url and e["enabled"] for e in C.DEFAULT_LISTS)
        old = [e for e in C.DEFAULT_LISTS if e["url"] != url]
        path = Path(C.CONFIG_DIR) / "settings.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"filter_lists": old, "lists_version": 3, "last_lists_update": 123}))
        cfg = C.Config()
        mine = [e for e in cfg["filter_lists"] if e["url"] == url]
        assert len(mine) == 1 and mine[0]["enabled"] and cfg["lists_version"] >= 4
        assert cfg["last_lists_update"] == 0               # fetched at the next start
        mine[0]["enabled"] = False
        cfg.save()
        again = C.Config()
        assert [e["enabled"] for e in again["filter_lists"] if e["url"] == url] == [False]
    finally:
        sys.path.remove(str(APP))
    text = (ROOT / "docs" / "THIRD-PARTY.md").read_text()
    assert "Malicious URL Blocklist" in text and "CC0" in text


def test_an_engine_without_recent_security_fixes_is_reported(run_ike):
    """The system's web engine gets its security fixes from the system's
    updates: when they are months behind the current Chrome, I.K.E. says so
    once (a desktop notice) and in Help -> About."""
    out = run_ike(r'''
def steps(ike, qapp, out):
    from ike import chromever
    notes = []
    ike._desktop_notify = lambda text, *a, **k: notes.append(text)
    ike.config["chrome_major"] = 157
    real = chromever.security_major
    chromever.security_major = lambda: 157
    out["fresh"] = [ike._engine_security_notice(), list(notes)]
    chromever.security_major = lambda: 148
    out["old"] = [ike._engine_security_notice(), list(notes)]
    ike._engine_security_notice()
    out["once"] = len(notes)
    out["about"] = ike.windows[0].about_text(media={})
    chromever.security_major = real
    yield 10
''', settings={"language": "en"}, timeout=60)
    assert out["fresh"] == [0, []]
    behind, notes = out["old"]
    assert behind == 9 and len(notes) == 1 and "sudo pacman -Syu" in notes[0] and "9" in notes[0]
    assert out["once"] == 1
    assert "Security fixes: 9 Chrome versions behind" in out["about"]


def test_saved_passwords_need_the_master_password_to_be_seen(run_ike):
    """With the vault open, the Passwords window shows, copies or exports a
    password only after the master password is typed again (once every few
    minutes); a wrong one shows nothing. Filling a login into a site is
    unchanged."""
    out = run_ike(r'''
def steps(ike, qapp, out):
    import time
    from PyQt6.QtWidgets import QInputDialog, QMessageBox
    from PyQt6.QtGui import QGuiApplication
    from ike.passwords import PasswordsDialog
    pm = ike.passwords
    pm.vault.create("right master")
    pm.vault.put("https://site.test", "me", "secret-pw")
    asked = []
    answers = []
    def get_text(*a, **k):
        asked.append(a[1] if len(a) > 1 else "")
        return (answers.pop(0), True) if answers else ("", False)
    QInputDialog.getText = staticmethod(get_text)
    QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.StandardButton.No)
    pm._confirmed = time.monotonic() - 3600             # typed an hour ago
    dlg = PasswordsDialog(ike)
    dlg.show()
    yield 300
    dlg.tree.setCurrentItem(dlg.tree.topLevelItem(0))
    def shown():
        return dlg.tree.topLevelItem(0).text(2)
    QGuiApplication.clipboard().setText("untouched")
    answers[:] = ["wrong"]
    dlg._toggle()
    out["wrong"] = [shown(), dlg.shown]
    dlg._copy()
    out["copied_without"] = QGuiApplication.clipboard().text()
    answers[:] = ["right master"]
    dlg._toggle()
    out["right"] = shown()
    n = len(asked)
    dlg.tree.setCurrentItem(dlg.tree.topLevelItem(0))     # the list was filled again
    dlg._copy()
    out["copy_within_minutes"] = [QGuiApplication.clipboard().text(), len(asked) - n]
    out["verify"] = [pm.vault.verify("right master"), pm.vault.verify("nope")]
    dlg._lock()
    out["after_lock"] = pm._confirmed < 0
    yield 100
''', timeout=90)
    assert out["wrong"] == ["••••••••", False], out
    assert out["copied_without"] == "untouched"
    assert out["right"] == "secret-pw"
    assert out["copy_within_minutes"] == ["secret-pw", 0]
    assert out["verify"] == [True, False] and out["after_lock"] is True


# ----------------------------------------------------------------------
# full audit of 1.1.17 (docs/review/security-audit.md, "Full audit")
# ----------------------------------------------------------------------
@pytest.fixture
def lan_service():
    """A service of "the home network": it notes what reaches it."""
    seen = []

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append("GET " + self.path)
            if self.path.startswith("/redir"):
                self.send_response(302)
                self.send_header("Location", "http://127.0.0.1:%d/secret" % self.server.server_address[1])
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            body = b"<!doctype html><title>router</title>ROUTER-ADMIN-PASSWORD=hunter2"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            seen.append("POST " + self.path)
            self.send_response(200)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *a):
            pass
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1], seen
    srv.shutdown()


def _userscripts():
    sys.path.insert(0, str(APP))
    try:
        from ike import userscripts
        return userscripts
    finally:
        sys.path.remove(str(APP))


def test_user_script_libraries_never_come_from_the_home_network(lan_service, monkeypatch):
    """@require and @resource of a script from the Internet are not fetched
    from this computer or the home network, directly, through a redirect or a
    name that points there; a script installed from a computer at home may."""
    port, seen = lan_service
    us = _userscripts()
    monkeypatch.setenv("IKE_TEST_RESOLVE", "cdn.example.test=192.168.1.20")
    head = "// ==UserScript==\n// @name s\n// @match https://a.test/*\n%s// ==/UserScript==\n"
    for line in ("// @resource cfg http://127.0.0.1:%d/secret\n" % port,
                 "// @require http://localhost:%d/redir\n" % port,
                 "// @require https://cdn.example.test/lib.js\n",
                 "// @resource r https://192.168.1.1/admin\n"):
        with pytest.raises(ValueError):
            us.gather(head % line, "https://scripts.example.test/s.user.js")
    assert seen == [], seen                                  # nothing was even asked
    # a redirect from elsewhere to home is refused as well
    handler = us._Redirects(home_ok=False)
    with pytest.raises(Exception):
        handler.redirect_request(None, None, 302, "", {}, "http://127.0.0.1:%d/secret" % port)
    with pytest.raises(Exception):
        handler.redirect_request(None, None, 302, "", {}, "ftp://files.example.test/x")
    # installed from a computer at home: its own libraries may be there
    got = us.gather(head % ("// @resource cfg http://127.0.0.1:%d/secret\n" % port),
                    "http://127.0.0.1:%d/s.user.js" % port)
    assert "hunter2" in got["resources"]["cfg"]["text"]
    assert us.at_home("localhost") and us.at_home("192.168.1.1") and us.at_home("cdn.example.test")
    assert us.at_home("no-such-name.invalid")               # unknown: refused, not let through
    assert not us.at_home("93.184.216.34")


def test_a_user_script_update_loading_code_from_new_places_asks():
    us = _userscripts()

    def got(extra):
        text = ("// ==UserScript==\n// @name s\n// @version 2\n// @match https://a.test/*\n"
                "// @grant GM_setValue\n%s// ==/UserScript==\n" % extra)
        return {"meta": us.parse_meta(text), "source": "https://scripts.example.test/s.user.js"}
    old = {"match": ["https://a.test/*"], "include": [], "exclude": [], "grant": ["GM_setValue"],
           "connect": [], "noframes": False, "update": "https://scripts.example.test/s.user.js",
           "requires": [["https://cdn.example.test/lib.js", "x"]],
           "resources": {"css": {"url": "https://static.example.test/a.css", "text": ""}}}
    assert not us.update_needs_consent(old, got("// @require https://cdn.example.test/lib2.js\n"))
    assert not us.update_needs_consent(old, got("// @resource css https://static.example.test/b.css\n"))
    assert not us.update_needs_consent(old, got("// @require lib3.js\n"))         # next to the script
    assert us.update_needs_consent(old, got("// @require https://other.example.test/x.js\n"))
    assert us.update_needs_consent(old, got("// @resource r https://192.168.1.1/admin\n"))
    assert us.update_needs_consent(old, got("// @resource r https://localhost:631/admin\n"))


def test_one_click_is_worth_one_download(run_ike, tmp_path):
    """A page that answers one click of the user with many downloads gets the
    first one; the rest wait for the question (until 1.1.17 every download of
    the next 3 seconds went through)."""
    seen = []
    page = (b"<!doctype html><title>p</title>"
            b"<button id=b style='position:absolute;left:0;top:0;width:300px;height:100px'>read</button>"
            b"<script>document.getElementById('b').addEventListener('click', function () {"
            b" for (var i = 0; i < 8; i++) (function (i) { setTimeout(function () {"
            b"  var a = document.createElement('a'); a.href = '/f' + i; a.download = '';"
            b"  document.body.appendChild(a); a.dispatchEvent(new MouseEvent('click')); }, 120 * i); })(i);"
            b"}, {once: true});</script>")

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append(self.path)
            if self.path.startswith("/f"):
                body = b"x"
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Disposition", "attachment; filename=%s.bin" % self.path[1:])
            else:
                body = page
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    folder = tmp_path / "dl"
    try:
        out = run_ike(r'''
PORT = %d

def steps(ike, qapp, out):
    from PyQt6.QtCore import QPoint, Qt, QUrl
    from PyQt6.QtTest import QTest
    from PyQt6.QtWebEngineCore import QWebEnginePage
    asked = []
    type(ike)._ask_download_burst = lambda self, site, done: (asked.append(site), done(False))
    win = ike.windows[0]
    v = win.current_view()
    yield 4000                                    # well after the start page
    done = {}
    v.page().loadFinished.connect(lambda ok: done.setdefault("ok", ok))
    QWebEnginePage.load(v.page(), QUrl("http://127.0.0.1:%%d/" %% PORT))
    while "ok" not in done:
        yield 20
    yield 4000
    QTest.mouseClick(v.focusProxy() or v, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     QPoint(100, 50))
    yield 3000
    out["asked"] = asked
''' % srv.server_address[1], settings={"https_only": False, "download_dir": str(folder),
                                       "ask_download_location": False}, timeout=90)
    finally:
        srv.shutdown()
    assert out["asked"] == ["127.0.0.1"], out
    assert sorted(p.name for p in folder.iterdir()) == ["f0.bin"], list(folder.iterdir())


def test_a_web_page_link_to_an_internal_action_does_nothing(run_ike):
    """"Open link in new tab" on a page's link to ike:tile?add=... or
    ike:engine?name=... used to act as the user; now only the new tab page's
    own links (with the session's key) change anything."""
    out = run_ike(JS + r'''
def steps(ike, qapp, out):
    from PyQt6.QtCore import QUrl
    win = ike.windows[0]
    yield 1500
    before = ike.config["default_engine"]
    other = [e["name"] for e in ike.config["search_engines"] if e["name"] != before][0]
    for addr in ("ike:tile?add=https%3A%2F%2Fevil.example%2F", "ike:engine?name=" + other,
                 "ike:tile?add=https%3A%2F%2Fevil.example%2F&k=guessed"):
        win.add_tab(QUrl(addr), background=True)                 # what the menu does
        yield 800
    out["bookmarked"] = ike.storage.is_bookmarked("https://evil.example/")
    out["engine_kept"] = ike.config["default_engine"] == before
    html = ike.shields.newtab_html()
    out["own_links_keyed"] = ("&amp;k=" + ike.shields.action_key) in html and \
        ('name="k" value="%s"' % ike.shields.action_key) in html
    win.add_tab(QUrl("ike:tile?add=https%3A%2F%2Fmine.example%2F&k=" + ike.shields.action_key), background=True)
    yield 800
    out["own_works"] = ike.storage.is_bookmarked("https://mine.example/")
''', timeout=90)
    assert out["bookmarked"] is False and out["engine_kept"] is True, out
    assert out["own_links_keyed"] is True and out["own_works"] is True


def test_a_public_page_cannot_open_the_home_network(run_ike, lan_service):
    """Home network protection: a page of a public site that sends a form to a
    local service is stopped and the window asks; the user's "Allow for this
    site" lets it through for the session. Addresses the user opens are not
    touched."""
    port, seen = lan_service
    out = run_ike(JS + r'''
PORT = %d

def steps(ike, qapp, out):
    from PyQt6.QtCore import QUrl
    win = ike.windows[0]
    v = win.current_view()
    yield 1000
    v.setHtml("<title>public</title><form id=f method=POST action='http://127.0.0.1:%%d/router-setting'>"
              "<input name=a value=1></form><script>document.getElementById('f').submit();</script>" %% PORT,
              QUrl("https://news.example.test/"))
    yield 3000
    out["bar"] = [win.secure_bar.isVisible(), win.secure_bar.text.text()]
    win.secure_bar.go.click()
    yield 2500
    out["after_allow"] = v.title()
    other = win.add_tab(QUrl("http://127.0.0.1:%%d/typed" %% PORT))            # the user's own
    yield 2500
    out["typed"] = other.title()
''' % port, settings={"https_only": False}, timeout=90)
    assert out["bar"][0] is True and "example.test" in out["bar"][1], out
    assert not any(s.startswith("POST") for s in seen), seen     # the form never reached it
    assert out["after_allow"] == "router" and out["typed"] == "router"


def test_a_name_that_does_not_resolve_is_not_let_through(run_ike):
    """outside_home(): a failed lookup used to count as "not local"; a
    hostile name server could fail the check and answer the request itself."""
    out = run_ike(r'''
def steps(ike, qapp, out):
    from ike.userscripts import outside_home
    got = {}
    outside_home("no-such-name-for-ike.invalid", lambda ok: got.setdefault("bad", ok), "test")
    outside_home("93.184.216.34", lambda ok: got.setdefault("public", ok), "test")
    for _ in range(200):
        if len(got) == 2:
            break
        yield 50
    out["got"] = got
''', timeout=60, env={k: "" for k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY",
                                     "all_proxy", "ALL_PROXY")})            # no proxy resolving names
    assert out["got"] == {"bad": False, "public": True}, out


def test_automatic_ad_skip_clicks_are_not_the_users(run_ike):
    """The clicks I.K.E. makes to skip a video ad are real Qt events; they no
    longer count as the user's action (which lets a download through)."""
    out = run_ike(r'''
def steps(ike, qapp, out):
    from PyQt6.QtCore import QUrl
    v = ike.windows[0].current_view()
    v.setHtml("<title>video</title><p>player</p>", QUrl("https://www.youtube.com/watch?v=x"))
    yield 1500
    page = v.page()
    page._ike_input = -99.0
    out["clicked"] = page.trusted_click(30, 30, allow_embedded=True)
    yield 200
    out["input"] = page._ike_input
''', timeout=60)
    assert out["clicked"] is True and out["input"] == -99.0, out


def test_an_error_while_checking_a_request_is_counted_and_files_stay_refused(run_ike, tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP-SECRET")
    out = run_ike(r'''
SECRET = %r

def steps(ike, qapp, out):
    from PyQt6.QtCore import QByteArray, QUrl
    from PyQt6.QtWebEngineCore import QWebEngineUrlRequestInfo as RI
    yield 500

    class Info:
        def __init__(self, url, first):
            self.u, self.f, self.blocked = QUrl(url), QUrl(first), False
        def requestUrl(self): return self.u
        def firstPartyUrl(self): return self.f
        def initiator(self): return self.f
        def resourceType(self): return RI.ResourceType.ResourceTypeSubFrame
        def requestMethod(self): return QByteArray(b"GET")
        def block(self, b): self.blocked = b
        def redirect(self, u): pass
        def setHttpHeader(self, k, v): pass
    sh = ike.shields
    before = ike.blocker.errors
    real_rule, real_level = sh.interceptor._local_file, ike.config.level_for
    def broken(*a, **k):
        raise RuntimeError("fault")
    sh.interceptor._local_file = broken
    ike.config.level_for = broken
    f = Info(QUrl.fromLocalFile(SECRET).toString(), "file:///tmp/page.html")
    sh.interceptor.interceptRequest(f)
    w = Info("https://ads.example.test/a.js", "https://site.test/")
    sh.interceptor.interceptRequest(w)
    sh.interceptor._local_file, ike.config.level_for = real_rule, real_level
    out["file_blocked"] = f.blocked
    out["errors"] = ike.blocker.errors - before
''' % str(secret), timeout=60, internal_errors=True)
    assert out["file_blocked"] is True and out["errors"] == 2, out


# ----------------------------------------------------------------------
# final validation of 1.1.17 (the owner's five checks)
# ----------------------------------------------------------------------
def test_home_network_protection_in_every_case(run_ike, lan_service):
    """1. The protection stops a public site's pages and frames that open a
    local address (private IPv4, localhost, IPv6 loopback, a .local name, a
    redirect from a public address), says so in the window, and never touches
    what the user opens or a page of the home network itself. "Allow" is for
    that one site and this session only."""
    port, seen = lan_service
    out = run_ike(JS + r'''
PORT = %d

def steps(ike, qapp, out):
    from PyQt6.QtCore import QUrl
    from ike.shields import Interceptor
    from PyQt6.QtCore import QByteArray
    from PyQt6.QtWebEngineCore import QWebEngineUrlRequestInfo as RI
    sh = ike.shields
    icp = sh.interceptor
    T = RI.ResourceType

    class Info:
        def __init__(self, url, init, rtype=T.ResourceTypeMainFrame):
            self.u, self.i, self.t, self.blocked = QUrl(url), QUrl(init), rtype, False
        def requestUrl(self): return self.u
        def firstPartyUrl(self): return self.i if self.t != T.ResourceTypeMainFrame else self.u
        def initiator(self): return self.i
        def resourceType(self): return self.t
        def requestMethod(self): return QByteArray(b"GET")
        def block(self, b): self.blocked = b
        def redirect(self, u): pass
        def setHttpHeader(self, k, v): pass
    def stopped(url, init, rtype=T.ResourceTypeMainFrame):
        info = Info(url, init, rtype)
        icp.interceptRequest(info)
        return info.blocked
    pub = "https://news.example.test/"
    out["public_to"] = {u: stopped(u, pub) for u in (
        "http://192.168.1.1/", "http://10.0.0.8:8080/", "http://172.16.4.2/", "http://127.0.0.1:631/",
        "http://localhost:8080/", "http://[::1]:8080/", "http://[fd12::1]/", "http://nas.local/",
        "http://printer.localhost/")}
    out["public_frame"] = stopped("http://192.168.1.1/", pub, T.ResourceTypeSubFrame)
    out["public_to_public"] = stopped("https://other.example.test/", pub)
    out["typed"] = stopped("http://192.168.1.1/", "")                       # no initiator: the user
    out["home_to_home"] = stopped("http://192.168.1.1/", "http://nas.local/")
    out["home_to_home_ip"] = stopped("http://127.0.0.1:631/", "http://192.168.1.20/")
    # "Allow for this site": that site, this session
    sh.lan_allowed.add("example.test")
    out["allowed_site"] = stopped("http://192.168.1.1/", pub)
    out["other_site"] = stopped("http://192.168.1.1/", "https://evil.example.org/")
    sh.lan_allowed.clear()
    # a real page: a frame of the home network inside a public page
    v = ike.windows[0].current_view()
    v.setHtml("<title>dash</title><iframe src='http://127.0.0.1:%%d/frame'></iframe>" %% PORT,
              QUrl("https://dash.example.test/"))
    yield 3000
    win = ike.windows[0]
    out["frame_bar"] = [win.secure_bar.isVisible(), win.secure_bar.text.text()]
    import json as _json
    out["kept"] = [k for k in ike.config.data if "allowed" in k.lower() and "lan" in _json.dumps(ike.config.data[k])]
''' % port, settings={"https_only": False}, timeout=90)
    assert all(out["public_to"].values()), out["public_to"]
    assert out["public_frame"] is True and out["public_to_public"] is False
    assert out["typed"] is False and out["home_to_home"] is False and out["home_to_home_ip"] is False
    assert out["allowed_site"] is False and out["other_site"] is True
    assert out["frame_bar"][0] is True and "example.test" in out["frame_bar"][1], out["frame_bar"]
    assert "GET /frame" not in seen
    assert out["kept"] == []                                  # nothing allowed is written to the settings


@needs_engine
def test_a_redirect_from_a_public_address_to_home_is_stopped(run_ike, lan_service):
    """A public page sends the tab to a public address that redirects to the
    home network: stopped as well (each step of a redirect is checked)."""
    port, seen = lan_service
    out = run_ike(JS + r'''
PORT = %d

def steps(ike, qapp, out):
    from PyQt6.QtCore import QUrl
    v = ike.windows[0].current_view()
    yield 800
    # the "public" hop is the same local server under a public-looking page:
    # what matters is that the target of the redirect is checked
    v.setHtml("<title>public</title><script>location.href='http://localhost:%%d/redir';</script>" %% PORT,
              QUrl("https://news.example.test/"))
    yield 3000
    out["title"] = v.title()
''' % port, settings={"https_only": False}, timeout=90)
    assert "GET /secret" not in seen and "GET /redir" not in seen, seen
    assert out["title"] != "router"


def test_script_libraries_go_to_the_address_that_was_checked(monkeypatch):
    """2. DNS rebinding: a library's name is looked up once, checked, and the
    connection goes to that very address (the name is not looked up again);
    a name that resolves home is refused before any connection."""
    import socket as _socket
    us = _userscripts()
    monkeypatch.setenv("IKE_TEST_RESOLVE", "cdn.example.test=203.0.113.5,home.example.test=192.168.1.9")
    for k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "ALL_PROXY"):
        monkeypatch.delenv(k, raising=False)
    tried = []

    def connect(address, *a, **k):
        tried.append(address)
        raise OSError("no network in the test")
    monkeypatch.setattr(_socket, "create_connection", connect)
    monkeypatch.setattr(_socket, "getaddrinfo", lambda *a, **k: (_ for _ in ()).throw(AssertionError("looked up again")))
    with pytest.raises(Exception):
        us._get("https://cdn.example.test/lib.js", 1000, home_ok=False)
    assert tried and tried[0][0] == "203.0.113.5", tried
    tried.clear()
    with pytest.raises(Exception):
        us._get("https://home.example.test/lib.js", 1000, home_ok=False)
    assert tried == []                                        # refused before connecting


def test_script_updates_go_through_the_same_checks(lan_service, monkeypatch):
    """2. Installing, the daily check and "Check for updates" all gather a
    script's files with the same function: a local library is refused in each."""
    port, seen = lan_service
    us = _userscripts()
    text = ("// ==UserScript==\n// @name s\n// @version 3\n// @match https://a.test/*\n"
            "// @require http://127.0.0.1:%d/secret\n// ==/UserScript==\n" % port)
    # the install and both kinds of update go through Fetcher -> gather
    import inspect
    src = inspect.getsource(us.Fetcher.run)
    assert "gather(text, self.url)" in src
    assert "self.fetch(ready, url, newer=" in inspect.getsource(us.UserScripts.check_updates)
    with pytest.raises(ValueError):
        us.gather(text, "https://scripts.example.test/s.user.js")
    assert seen == []


def test_errors_while_checking_keep_protected_things_protected(run_ike):
    """3. A fault inside the checks: counted; a file, and a public page's way
    into the home network, stay refused; ordinary navigation goes on."""
    out = run_ike(r'''
def steps(ike, qapp, out):
    from PyQt6.QtCore import QByteArray, QUrl
    from PyQt6.QtWebEngineCore import QWebEngineUrlRequestInfo as RI
    yield 500

    class Info:
        def __init__(self, url, init):
            self.u, self.i, self.blocked = QUrl(url), QUrl(init), False
        def requestUrl(self): return self.u
        def firstPartyUrl(self): return self.u
        def initiator(self): return self.i
        def resourceType(self): return RI.ResourceType.ResourceTypeMainFrame
        def requestMethod(self): return QByteArray(b"GET")
        def block(self, b): self.blocked = b
        def redirect(self, u): pass
        def setHttpHeader(self, k, v): pass
    icp = ike.shields.interceptor
    real = type(icp)._intercept
    def broken(self, info):
        raise RuntimeError("fault")
    type(icp)._intercept = broken
    res = {}
    for name, url, init in (("lan", "http://192.168.1.1/", "https://news.example.test/"),
                            ("web", "https://news.example.test/next", "https://news.example.test/"),
                            ("typed_lan", "http://192.168.1.1/", "")):
        i = Info(url, init); icp.interceptRequest(i); res[name] = i.blocked
    type(icp)._intercept = real
    out["res"] = res
''', timeout=60, internal_errors=True)
    assert out["res"] == {"lan": True, "web": False, "typed_lan": False}, out


def test_two_profiles_never_write_the_update_state_over_each_other(tmp_path):
    """4. Two profiles share only the program updates: their state file is
    written through a temporary file of each process, and installing is one at
    a time (see test_updater.py). Here two processes write the state 200 times
    each at once: the file is always whole JSON."""
    script = r'''
import json, os, sys, time
sys.path[:0] = [%r]
os.environ["XDG_DATA_HOME"] = %r
from ike import updater
end = time.time() + 3
n = 0
while time.time() < end and n < 200:
    updater.save_state({"current": None, "writer": os.getpid(), "n": n, "pad": "x" * 4000})
    n += 1
'''
    data = tmp_path / "data"
    code = script % (str(APP), str(data))
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    procs = [subprocess.Popen([sys.executable, "-c", code], env=env) for _ in range(2)]
    bad = 0
    state = data / "ike-browser" / "updates" / "state.json"
    while any(p.poll() is None for p in procs):
        try:
            json.loads(state.read_text())
        except FileNotFoundError:
            pass
        except ValueError:
            bad += 1
    assert all(p.returncode == 0 for p in procs)
    assert bad == 0 and json.loads(state.read_text())["writer"] in [p.pid for p in procs]
