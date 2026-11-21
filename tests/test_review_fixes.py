"""Fixes of the independent review of 1.1.19 (security and privacy), each
shown by a test that failed before the fix."""

from test_updater import CHECK, PASS, keypair, load_tool, make_update_json, releases, update_env  # noqa: F401

STEPS_M2 = r'''
def steps(ike, qapp, out):
    from PyQt6.QtWebEngineCore import QWebEnginePermission as P
    from ike import webview
    yield 300
    box, allow, block = webview.permission_box(ike.windows[0], "evil.example", P.PermissionType.MediaVideoCapture)
    box.show()
    out["default"] = box.defaultButton() is block
    out["escape"] = box.escapeButton() is block
    out["allow_at_once"] = allow.isEnabled()
    yield webview.SAFE_DELAY_MS + 300
    out["allow_later"] = allow.isEnabled()
    box.close()
'''


def test_m2_a_key_press_never_grants_a_permission(run_ike):
    """M2: "Allow" was the default button, so Enter or Space (a page asks at
    the moment the user types) granted camera, microphone or location. Now
    Enter and Esc block, and Allow can be clicked only a moment later."""
    out = run_ike(STEPS_M2, timeout=60)
    assert out["default"] and out["escape"], out
    assert out["allow_at_once"] is False and out["allow_later"] is True, out


def _ua_server(seen):
    import http.server
    import threading

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append((self.path, self.headers.get("User-Agent", "")))
            body = (b"// ==UserScript==\n// @name t\n// @match *://*/*\n// ==/UserScript==\n"
                    if self.path.endswith(".user.js") else b"<title>p</title>")
            self.send_response(200)
            self.send_header("Content-Type", "text/javascript" if self.path.endswith(".js") else "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


STEPS_M1 = r'''
P = %d

def steps(ike, qapp, out):
    import time
    from PyQt6.QtCore import QUrl
    v = ike.windows[0].current_view()
    offers = out["offers"] = []
    real_offer = ike.userscripts.offer
    ike.userscripts.offer = lambda parent, url="", text=None, home_ok=True: offers.append([url, home_ok])
    yield 800
    # a public page sends the tab to a script on the home network by itself
    v.setHtml("<title>pub</title>", QUrl("https://www.public.test/"))
    yield 800
    v.page().runJavaScript("location.href = 'http://127.0.0.1:%%d/page-made.user.js'" %% P)
    yield 1500
    out["after_page"] = list(offers)
    # the same after a click of the user: offered, but not from the home network
    v.page()._ike_input = time.monotonic()
    v.page().runJavaScript("location.href = 'http://127.0.0.1:%%d/clicked.user.js'" %% P)
    yield 1500
    out["after_click"] = list(offers)
    # an address the user typed: offered, the home network allowed
    v.load(QUrl("http://127.0.0.1:%%d/typed.user.js" %% P))
    yield 1500
    out["after_typed"] = list(offers)
    # opened in a new tab: by a click of the user yes, by the page alone no
    v.setHtml("<title>pub2</title>", QUrl("https://www.public.test/two"))
    yield 800
    v.page().runJavaScript("window.open('http://127.0.0.1:%%d/popup.user.js')" %% P)
    yield 1500
    # a real click on a link that opens a new tab
    from PyQt6.QtCore import QPoint, Qt
    from PyQt6.QtTest import QTest
    v.setHtml("<title>pub3</title><a target=_blank href='http://127.0.0.1:%%d/newtab.user.js' "
              "style='display:block;width:100vw;height:100vh'>x</a>" %% P, QUrl("https://www.public.test/three"))
    yield 1200
    v.window().activateWindow()
    QTest.mouseClick(v.focusProxy(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(40, 40))
    yield 1500
    out["after_tabs"] = list(offers)
    ike.userscripts.offer = real_offer
    # the download itself: refused from home when not allowed, and with the
    # browser's own User-Agent
    got = out["fetch"] = {}
    ike.userscripts.fetch(lambda g, e: got.__setitem__("home_refused", g is None),
                          "http://127.0.0.1:%%d/refused.user.js" %% P, home_ok=False)
    ike.userscripts.fetch(lambda g, e: got.__setitem__("ok", g is not None),
                          "http://127.0.0.1:%%d/ua.user.js" %% P)
    yield 2500
    out["ua"] = ike.shields.user_agent()
'''


def test_m1_a_page_cannot_make_ike_fetch_a_user_script(run_ike):
    """M1: any main-frame navigation to a .user.js, also one made by a page's
    own script, made I.K.E. download it before asking, from any address (the
    router's too) and with a User-Agent that named I.K.E. Now only the user's
    own act offers an install, the home network only when the user typed the
    address (or is already on it), and the request looks like the browser."""
    seen = []
    srv = _ua_server(seen)
    try:
        out = run_ike(STEPS_M1 % srv.server_address[1], settings={"https_only": False}, timeout=60)
    finally:
        srv.shutdown()
    paths = [p for p, _ in seen]
    assert out["after_page"] == [], out
    assert len(out["after_click"]) == 1 and out["after_click"][0][1] is False, out
    assert out["after_click"][0][0].endswith("/clicked.user.js"), out
    assert len(out["after_typed"]) == 2 and out["after_typed"][1][1] is True, out
    assert [u for u, _ in out["after_tabs"][2:]] == ["http://127.0.0.1:%d/newtab.user.js" % srv.server_address[1]], out
    assert "/page-made.user.js" not in paths and "/clicked.user.js" not in paths, paths
    assert out["fetch"] == {"home_refused": True, "ok": True}, out
    assert "/refused.user.js" not in paths, paths
    ua = [u for p, u in seen if p == "/ua.user.js"]
    assert ua == [out["ua"]] and "I.K.E." not in ua[0], (ua, out["ua"])


BOOT = r'''
import json, sys, time
sys.path.insert(0, %r)
import ike_boot
folder, state, _ = ike_boot.choose()
print(json.dumps([str(folder), state.get("bad", [])]), flush=True)
if sys.argv[1] == "hold":
    time.sleep(60)
'''


def test_h2_a_second_start_does_not_roll_back_a_running_update(tmp_path):
    """H2: an update's first start is counted; a second start of I.K.E. within
    its first 20 s (a link from a mail program) took it for a failed start,
    went back to the old version and never installed that update again. Now a
    second start sees that the first is still running; only a first start that
    ended without confirming is rolled back, as before."""
    import json
    import os
    import subprocess
    import sys

    from conftest import APP
    updates = tmp_path / "ike-browser" / "updates"
    vdir = updates / "versions" / "99.0.0" / "ike"
    vdir.mkdir(parents=True)
    (vdir / "__init__.py").write_text('__version__ = "99.0.0"\n')
    (updates / "state.json").write_text(json.dumps({"current": "99.0.0", "status": "pending", "attempts": 0}))
    env = dict(os.environ, XDG_DATA_HOME=str(tmp_path))
    code = BOOT % str(APP)

    first = subprocess.Popen([sys.executable, "-c", code, "hold"], env=env, stdout=subprocess.PIPE, text=True)
    try:
        got1 = json.loads(first.stdout.readline())
        second = subprocess.run([sys.executable, "-c", code, "once"], env=env, capture_output=True, text=True,
                                timeout=30)
        got2 = json.loads(second.stdout)
    finally:
        first.kill()
        first.wait()
    assert got1[0].endswith("99.0.0") and got2[0].endswith("99.0.0"), (got1, got2)
    state = json.loads((updates / "state.json").read_text())
    assert state["current"] == "99.0.0" and not state.get("bad"), state
    # the first start is gone without confirming: the next start goes back
    third = subprocess.run([sys.executable, "-c", code, "once"], env=env, capture_output=True, text=True, timeout=30)
    got3 = json.loads(third.stdout)
    assert not got3[0].endswith("99.0.0") and got3[1] == ["99.0.0"], got3


STEPS_L9 = r'''
def steps(ike, qapp, out):
    from PyQt6.QtGui import QGuiApplication
    from ike import contextmenu
    yield 500
    contextmenu._insert_password(ike.windows[0].current_view())
    yield 300
    data = QGuiApplication.clipboard().mimeData()
    out["hint"] = bytes(data.data("x-kde-passwordManagerHint")).decode()
    out["text"] = len(data.text())
'''


def test_l9_a_generated_password_stays_out_of_clipboard_history(run_ike):
    """L9: the password generated from the page menu went on the clipboard as
    plain text, kept by clipboard history; the vault's copies were already
    marked as secret and taken off after 45 s."""
    out = run_ike(STEPS_L9, timeout=60)
    assert out["hint"] == "secret" and out["text"] > 8, out


def _updater_imports():
    import sys

    from conftest import APP
    sys.path.insert(0, str(APP))
    from ike import updater
    return updater


def test_l1_a_manifest_signed_for_beta_is_refused_on_stable(run_ike, releases, keypair, tmp_path):  # noqa: F811
    """L1: every channel's manifest was the same signed file, so a beta one
    served as stable.json verified and installed. Now each names its channel
    (tools/make-release.py) and the updater refuses another channel's."""
    key, key_path, pub = keypair
    releases.publish(key, "99.0.0", min_system="0", extra={"channel": "beta"})
    out = run_ike(CHECK, env=update_env(tmp_path, releases, pub), timeout=240)
    assert out["kind"] == "error" and "another channel" in out["data"], out
    assert not out["state"].get("current"), out
    import json
    tool = load_tool()
    upd = make_update_json(tmp_path, pub)
    tool.make(key_path, tmp_path / "rel", ["stable", "beta"], passphrase=PASS, update_file=upd)
    for ch in ("stable", "beta"):
        assert json.loads((tmp_path / "rel" / (ch + ".json")).read_text())["channel"] == ch


def test_l2_halt_withdraws_a_staged_copy(tmp_path, monkeypatch):
    """L2: a version stopped by the owner ("halt") already staged, not yet
    started, still ran at the next start. Now it is withdrawn and never
    installed again; a version already proved, or another version, is left."""
    import json
    updater = _updater_imports()
    monkeypatch.setattr(updater, "UPDATES", tmp_path)
    monkeypatch.setattr(updater, "STATE", tmp_path / "state.json")
    staged = {"current": "99.0.0", "previous": "98.0.0", "status": "pending", "attempts": 0}
    for state, manifest, withdrawn in (
            (staged, {"version": "99.0.0", "halt": True}, True),
            (staged, {"version": "99.0.0"}, False),
            (staged, {"version": "99.0.1", "halt": True}, False),
            (dict(staged, status="ok"), {"version": "99.0.0", "halt": True}, False)):
        (tmp_path / "state.json").write_text(json.dumps(state))
        assert updater.withdraw(manifest) is withdrawn
        now = json.loads((tmp_path / "state.json").read_text())
        if withdrawn:
            assert now["current"] == "98.0.0" and now["bad"] == ["99.0.0"] and now["status"] == "ok", now
        else:
            assert now == state, now


STEPS_L3 = r'''
def steps(ike, qapp, out):
    asked = out["asked"] = []
    ike.favicons.fetch = lambda url: asked.append(url)
    yield 5000                         # past the start's own icon request
    out["at_start"] = list(asked)
    ike.windows[0]._fill_engine_menu()
    out["menu"] = list(asked)
    other = [e["name"] for e in ike.config["search_engines"] if e["name"] != ike.config["default_engine"]][0]
    ike.set_engine(other)
    out["chosen"] = list(asked)
    out["default_url"] = [e["url"] for e in ike.config["search_engines"]
                          if e["name"] == ike.config["default_engine"]][0]
    from ike import osinfo
    out["ua"] = [osinfo.browser_user_agent(), ike.shields.user_agent()]
'''


def test_l3_no_request_of_ike_names_ike_and_unused_engines_are_not_asked(run_ike):
    """L3: the filter lists, updates, version check and DRM download sent a
    User-Agent of their own ("I.K.E. filter updater"...); at the first start
    every search engine, Google and Bing included, was asked for its icon.
    Now all of I.K.E.'s requests carry the pages' User-Agent, and only the
    engine in use is asked."""
    import re

    from conftest import APP
    for path in sorted((APP / "ike").glob("*.py")):
        for value in re.findall(r'"User-Agent"\s*:\s*([^}\n]+)', path.read_text("utf-8")):
            assert "browser_user_agent()" in value, (path.name, value)
        assert "I.K.E. filter updater" not in path.read_text("utf-8"), path.name
    out = run_ike(STEPS_L3, timeout=60)
    assert out["ua"][0] == out["ua"][1], out
    assert len(out["at_start"]) == 1 and out["menu"] == out["at_start"], out
    assert len(out["chosen"]) == 2 and out["chosen"][1] == out["default_url"], out


def _icon_server(body):
    import http.server
    import threading

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "image/x-icon")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


STEPS_L7 = r'''
SVG, PNG = %d, %d

def steps(ike, qapp, out):
    yield 300
    ike.favicons.fetch("http://127.0.0.1:%%d/" %% SVG)
    ike.favicons.fetch("http://localhost:%%d/" %% PNG)
    yield 2500
    out["svg"] = ike.favicons.icon("http://127.0.0.1:%%d/" %% SVG).isNull()
    out["png"] = ike.favicons.icon("http://localhost:%%d/" %% PNG).isNull()
'''


def test_l7_favicons_only_png_or_ico(run_ike):
    """L7: an icon from a site never visited was decoded by any image plugin
    Qt has (SVG, and on Plasma many more), in the browser outside the engine's
    sandbox. Now only PNG and ICO, told by their first bytes."""
    import base64
    png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg==")
    svg = (b'<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16">'
           b'<rect width="16" height="16" fill="red"/></svg>')
    a, b = _icon_server(svg), _icon_server(png)
    try:
        out = run_ike(STEPS_L7 % (a.server_address[1], b.server_address[1]),
                      settings={"https_only": False}, timeout=60)
    finally:
        a.shutdown()
        b.shutdown()
    assert out["svg"] is True and out["png"] is False, out


STEPS_L11 = r'''
def steps(ike, qapp, out):
    yield 300
    out["args"] = qapp.arguments()
    out["rtl"] = qapp.layoutDirection() == __import__("PyQt6.QtCore").QtCore.Qt.LayoutDirection.RightToLeft
'''


def test_l11_unknown_arguments_do_not_reach_qt(run_ike):
    """L11: an argument I.K.E. does not know (an "address" starting with "-"
    from another program) went to Qt as one of its options. Now it is dropped."""
    out = run_ike(STEPS_L11, args=["-reverse", "--no-sandbox"], timeout=60)
    assert out["args"][1:] == [] and out["rtl"] is False, out


def _pb(number, payload):
    """One length-delimited protocol buffer field."""
    def varint(n):
        out = b""
        while True:
            b = n & 0x7F
            n >>= 7
            out += bytes([b | (0x80 if n else 0)])
            if not n:
                return out
    return varint(number << 3 | 2) + varint(len(payload)) + payload


def _crx3(archive, ecdsa=False, other_key=None):
    """A CRX3 package signed as the Chrome Web Store's are (developer key)."""
    import hashlib
    import struct

    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
    key = ec.generate_private_key(ec.SECP256R1()) if ecdsa else rsa.generate_private_key(65537, 2048)
    pub = key.public_key().public_bytes(serialization.Encoding.DER,
                                        serialization.PublicFormat.SubjectPublicKeyInfo)
    named = other_key or pub
    crx_id = hashlib.sha256(named).digest()[:16]
    signed = _pb(1, crx_id)
    message = b"CRX3 SignedData\x00" + struct.pack("<I", len(signed)) + signed + archive
    sig = (key.sign(message, ec.ECDSA(hashes.SHA256())) if ecdsa
           else key.sign(message, padding.PKCS1v15(), hashes.SHA256()))
    header = _pb(3 if ecdsa else 2, _pb(1, pub) + _pb(2, sig)) + _pb(10000, signed)
    ext_id = "".join("abcdefghijklmnop"[c >> 4] + "abcdefghijklmnop"[c & 15] for c in crx_id)
    return b"Cr24" + struct.pack("<II", 3, len(header)) + header + archive, ext_id


def test_l8_store_packages_must_carry_the_extensions_signature():
    """L8: the package downloaded for an extension was unpacked with its
    header skipped: only TLS vouched for it, and a package of any other
    extension (or none) was installed under the id asked for. Now it must be
    a CRX3 whose id is the one asked for and whose signature by that id's key
    covers the archive (checked also on Chromium's own CRX3 test files)."""
    import io
    import struct
    import zipfile

    import pytest
    _updater_imports()
    from ike import extensions
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("manifest.json", '{"manifest_version": 3, "name": "t", "version": "1"}')
    archive = buf.getvalue()
    for ecdsa in (False, True):
        data, ext_id = _crx3(archive, ecdsa=ecdsa)
        assert extensions.verify_crx(ext_id, data) is True
        tampered = data[:-40] + bytes([data[-40] ^ 1]) + data[-39:]
        with pytest.raises(ValueError):
            extensions.verify_crx(ext_id, tampered)
        with pytest.raises(ValueError):
            extensions.verify_crx("a" * 32, data)                # another extension's package
    forged, ext_id = _crx3(archive, other_key=b"the real extension's key")
    with pytest.raises(ValueError):
        extensions.verify_crx(ext_id, forged)                    # signed by a key of its own
    for plain in (archive, b"Cr24" + struct.pack("<III", 2, 0, 0) + archive):
        with pytest.raises(ValueError):
            extensions.verify_crx(ext_id, plain)                 # a bare ZIP, or CRX2: no signature


def _doh_and_site():
    """A provider of encrypted DNS that alone knows *.doh.test (127.0.0.1),
    and the site those names lead to, which notes the Host of each request."""
    import base64
    import http.server
    import struct
    import threading
    from urllib.parse import parse_qs, urlsplit
    asked, seen = [], []
    png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg==")

    class Doh(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = base64.urlsafe_b64decode(parse_qs(urlsplit(self.path).query)["dns"][0] + "==")
            i, labels = 12, []
            while q[i]:
                labels.append(q[i + 1:i + 1 + q[i]].decode())
                i += 1 + q[i]
            name, qtype = ".".join(labels), struct.unpack(">H", q[i + 1:i + 3])[0]
            asked.append((name, qtype))
            answer = b""
            if name.endswith(".doh.test") and qtype == 1:
                answer = b"\xc0\x0c" + struct.pack(">HHIH", 1, 1, 60, 4) + bytes([127, 0, 0, 1])
            body = q[:2] + struct.pack(">HHHHH", 0x8180, 1, 1 if answer else 0, 0, 0) + q[12:i + 5] + answer
            self.send_response(200)
            self.send_header("Content-Type", "application/dns-message")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    class Site(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append((self.headers.get("Host", ""), self.path))
            if self.path.startswith("/redirect"):
                self.send_response(302)
                self.send_header("Location", self.path.split("?", 1)[1])
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            body, ctype = ((png, "image/png") if self.path == "/favicon.ico"
                           else (b"body{color:#123456}", "text/css") if self.path.endswith(".css")
                           else (b"ok", "text/plain"))
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    servers = [http.server.ThreadingHTTPServer(("127.0.0.1", 0), h) for h in (Doh, Site)]
    for s in servers:
        threading.Thread(target=s.serve_forever, daemon=True).start()
    return servers, asked, seen


STEPS_M3 = r'''
P = %d

def steps(ike, qapp, out):
    from PyQt6.QtCore import QObject, QUrl
    from ike import doh, userscripts
    from ike.passwords import PageBridge
    out["active"] = doh.active()

    class Page(QObject):
        def __init__(self, url):
            super().__init__()
            self._url, self._dark_on = QUrl(url), True

        def url(self):
            return self._url
    answers, keep = {}, []
    for name, page_url, css in (
            ("own_sheet", "http://127.0.0.1:%%d/page" %% P, "http://css.doh.test:%%d/a.css" %% P),
            ("redirected", "http://127.0.0.1:%%d/page" %% P,
             "http://css.doh.test:%%d/redirect?http://css2.doh.test:%%d/b.css" %% (P, P)),
            # a public page: its sheet's name points home by encrypted DNS too
            ("public_to_home", "http://news.example.org/", "http://home.doh.test:%%d/c.css" %% P)):
        page = Page(page_url)
        bridge = PageBridge(ike.passwords, page)
        bridge.cssFetched.connect(lambda ident, ok, text: answers.__setitem__(ident, ok))
        keep.append((page, bridge))
        bridge.fetchCss(name, css)
    ike.favicons.fetch("http://icon.doh.test:%%d/" %% P)
    # the user scripts' requests (GM_xmlhttpRequest) are sent this way
    from PyQt6.QtNetwork import QNetworkRequest
    gm = []
    doh.get(ike.userscripts.network, QNetworkRequest(QUrl("http://gm.doh.test:%%d/x" %% P)),
            lambda reply: reply.finished.connect(lambda: gm.append(bytes(reply.readAll()).decode())),
            custom=b"GET")
    out["urllib"] = doh.urlopen("http://lists.doh.test:%%d/list.txt" %% P, timeout=10).read().decode()
    out["script"] = userscripts._get("http://script.doh.test:%%d/s.txt" %% P, 1000)[0].decode()
    for _ in range(200):
        if len(answers) == 3 and not ike.favicons.icon("http://icon.doh.test:%%d/" %% P).isNull():
            break
        yield 25
    out["answers"] = answers
    out["gm"] = gm
    out["icon"] = not ike.favicons.icon("http://icon.doh.test:%%d/" %% P).isNull()
'''


def test_m3_encrypted_dns_also_for_ikes_own_requests(run_ike):
    """M3: encrypted DNS covered only the pages: the style sheets of dark mode,
    the sites' icons, user scripts, updates and filter lists were looked up
    by the system, in clear. Here the names exist only at the provider:
    every one of these requests reaches its site, by the provider's answer."""
    servers, asked, seen = _doh_and_site()
    doh_port, P = servers[0].server_address[1], servers[1].server_address[1]
    try:
        out = run_ike(STEPS_M3 % P, settings={"https_only": False}, timeout=90,
                      env={"IKE_TEST_DOH": "http://127.0.0.1:%d/dns-query" % doh_port,
                           "http_proxy": "", "https_proxy": "", "HTTP_PROXY": "", "HTTPS_PROXY": "",
                           "all_proxy": "", "ALL_PROXY": "", "no_proxy": "*", "NO_PROXY": "*"})
    finally:
        for s in servers:
            s.shutdown()
    assert out["active"] is True, out
    assert out["answers"] == {"own_sheet": True, "redirected": True, "public_to_home": False}, out
    assert out["icon"] is True and out["urllib"] == "ok" and out["script"] == "ok" and out["gm"] == ["ok"], out
    hosts = {h.split(":")[0] for h, _ in seen}
    assert {"css.doh.test", "css2.doh.test", "icon.doh.test", "lists.doh.test", "script.doh.test",
            "gm.doh.test"} <= hosts, seen
    assert "home.doh.test" not in hosts, seen
    assert {"css.doh.test", "home.doh.test", "icon.doh.test"} <= {n for n, _ in asked}, asked


def test_l4_an_update_into_the_pages_world_asks_first():
    """L4: an update that added @grant unsafeWindow moved a script, and its
    token, into the page's own world without asking."""
    _updater_imports()
    from ike.userscripts import parse_meta, update_needs_consent
    text = ("// ==UserScript==\n// @name s\n// @version 2\n// @match https://a.test/*\n"
            "// @grant GM_setValue\n%s// ==/UserScript==\n")
    old = {"match": ["https://a.test/*"], "include": [], "exclude": [], "grant": ["GM_setValue"],
           "connect": [], "noframes": False}
    same = {"meta": parse_meta(text % ""), "source": "https://example.test/s.user.js"}
    into_page = {"meta": parse_meta(text % "// @grant unsafeWindow\n"), "source": "https://example.test/s.user.js"}
    assert not update_needs_consent(old, same)
    assert update_needs_consent(old, into_page)


STEPS_L6 = r'''
def steps(ike, qapp, out):
    from PyQt6.QtCore import QUrl
    v = ike.windows[0].current_view()
    v.setHtml("<title>t</title><input type=password>", QUrl("https://www.example.org/"))
    yield 2500
    # another script of that world opens a second channel on the transport
    v.page().runJavaScript(
        "window.__second = 'none'; try { new QWebChannel(qt.webChannelTransport, function (c) {"
        " window.__second = c.objects.ike && c.objects.ike.fillRequested ? 'vault' : 'other'; });"
        " } catch (e) { window.__second = 'refused'; }", 1)
    yield 1500
    got = {}
    v.page().runJavaScript(
        "JSON.stringify({second: window.__second,"
        " bridge: Object.keys(window.__ikeBridge || {}).sort(),"
        " fill: !!(window.__ikeBridge && window.__ikeBridge.fillRequested)})", 1,
        lambda r: got.__setitem__("r", r))
    yield 500
    out["r"] = got.get("r")
    # the helper's own channel still works: dark mode's call answers
    ans = {}
    v.page().runJavaScript(
        "window.__css = null; window.__ikeBridge.cssFetched.connect(function (i, ok) {"
        " if (i === 'l6') window.__css = ok; }); window.__ikeBridge.fetchCss('l6', 'ftp://x/');", 1)
    yield 800
    v.page().runJavaScript("String(window.__css)", 1, lambda r: ans.__setitem__("r", r))
    yield 300
    out["css"] = ans.get("r")
'''


def test_l6_the_logins_channel_is_the_password_helpers_alone(run_ike):
    """L6: the password helper published the whole channel object to its
    world, where list scriptlets and Dark Reader also run: one bug in either
    and the chosen login could be read. Now the transport is gone from that
    world and the others get only the three calls they use."""
    import json
    out = run_ike(STEPS_L6, timeout=60)
    r = json.loads(out["r"])
    assert r["second"] in ("none", "refused") and r["fill"] is False, r
    assert r["bridge"] == ["adClick", "adClickEmbedded", "cssFetched", "fetchCss"], r
    assert out["css"] == "false", out             # answered (refused: not http) through the helper's channel


PSL_SAMPLE = """// a part of the Public Suffix List, in its own format
// ===BEGIN ICANN DOMAINS===
com
uk
co.uk
*.ck
!www.ck
// ===BEGIN PRIVATE DOMAINS===
wordpress.com
blogspot.it
s3.amazonaws.com
pp.ua
""" + "".join("filler%d\n" % i for i in range(1200))


def test_l10_the_site_of_a_name_follows_the_public_suffix_list(tmp_path, monkeypatch):
    """L10: an approximation made unrelated blogs and buckets one "site" (the
    filter lists' free way, the permissions, the noise). With the system's
    Public Suffix List (a dependency of the package) each is its own; without
    it, the approximation knows these hosts too."""
    _updater_imports()
    from ike import shields
    psl = tmp_path / "psl.dat"
    psl.write_text(PSL_SAMPLE)
    monkeypatch.setattr(shields, "PSL_PATHS", [str(psl)])
    monkeypatch.setattr(shields, "_PSL", [])
    shields.site_of.cache_clear()
    try:
        s = shields.site_of
        assert s("a.wordpress.com") == "a.wordpress.com" != s("b.wordpress.com")
        assert s("x.y.blogspot.it") == "y.blogspot.it"
        assert s("bucket.s3.amazonaws.com") == "bucket.s3.amazonaws.com"
        assert s("shop.pp.ua") == "shop.pp.ua"
        assert s("www.bbc.co.uk") == "bbc.co.uk" and s("news.example.com") == "example.com"
        assert s("a.b.ck") == "a.b.ck" and s("www.ck") == "www.ck"
        assert s("www.example.zz") == "example.zz" and s("example.com") == "example.com"
        assert s("127.0.0.1") == "127.0.0.1" and s("localhost") == "localhost"
        # without the list: the approximation
        monkeypatch.setattr(shields, "PSL_PATHS", [str(tmp_path / "missing")])
        monkeypatch.setattr(shields, "_PSL", [])
        shields.site_of.cache_clear()
        assert s("a.wordpress.com") != s("b.wordpress.com") and s("www.bbc.co.uk") == "bbc.co.uk"
    finally:
        monkeypatch.undo()
        shields.site_of.cache_clear()


FP_PROBE = r"""
(async function () {
  var R = {};
  function h(a) { var x = 2166136261; for (var i = 0; i < a.length; i++) { x ^= a[i]; x = Math.imul(x, 16777619); } return (x >>> 0).toString(16); }
  function draw(grey) {
    var c = document.createElement('canvas'); c.width = 120; c.height = 40;
    var x = c.getContext('2d');
    if (grey) { x.fillStyle = 'rgb(128,128,128)'; x.fillRect(0, 0, 120, 40); }
    else { x.fillStyle = '#f60'; x.fillRect(0, 0, 120, 40); x.fillStyle = '#069'; x.font = '16px sans-serif';
           x.fillText('I.K.E. probe', 4, 24); }
    return x.getImageData(0, 0, 120, 40).data;
  }
  var a = draw(false), a2 = draw(false), g = draw(true), rec = new Uint8Array(a.length);
  for (var i = 0; i < a.length; i++) rec[i] = (i & 3) === 3 ? a[i] : a[i] ^ (g[i] ^ 128);
  R.recovered = h(rec); R.stable = h(a) === h(a2);
  // audio: a buffer the page wrote itself comes back as written
  var ctx = new OfflineAudioContext(1, 1000, 44100), own = ctx.createBuffer(1, 1000, 44100);
  var ones = new Float32Array(1000).fill(1); own.copyToChannel(ones, 0);
  var back = new Float32Array(1000); own.copyFromChannel(back, 0);
  R.ownUntouched = back.every(function (v) { return v === 1; }) && own.getChannelData(0)[5] === 1;
  // a rendered one: the same values by both ways, noise beyond every 97th sample
  var o = ctx.createOscillator(); o.frequency.value = 1000; o.connect(ctx.destination); o.start(0);
  var buf = await ctx.startRendering(), cp = new Float32Array(1000);
  buf.copyFromChannel(cp, 0);
  var d = buf.getChannelData(0), same = true;
  for (var j = 0; j < 1000; j++) if (cp[j] !== d[j]) same = false;
  R.renderedConsistent = same; R.sample1 = d[1];
  var m = document.createElement('canvas').getContext('2d');
  R.emptyWidth = m.measureText('').width;
  try { Object.getOwnPropertyDescriptor(Navigator.prototype, 'hardwareConcurrency').get.call({}); R.receiver = 'no error'; }
  catch (e) { R.receiver = e.constructor.name; }
  R.gpu = ('gpu' in navigator) && navigator.gpu !== undefined;
  R.adapter = navigator.gpu ? await navigator.gpu.requestAdapter() : 'none';
  R.battery = typeof navigator.getBattery === 'function';
  if (R.battery) { var b = await navigator.getBattery(); R.batteryLevel = [b.charging, b.level]; }
  R.lang = navigator.language;
  R.intl = new Intl.DateTimeFormat().resolvedOptions().locale;
  R.number = (1234.5).toLocaleString();
  R.intlNative = Function.prototype.toString.call(Intl.DateTimeFormat);
  window.__fp = JSON.stringify(R);
})();
"""

STEPS_FP = r'''
PROBE = %r

def steps(ike, qapp, out):
    from PyQt6.QtCore import QUrl
    v = ike.windows[0].current_view()
    v.setHtml("<title>fp</title>", QUrl("https://www.example.org/"))
    yield 2000
    v.page().runJavaScript(PROBE, 0)
    got = {}
    for _ in range(100):
        yield 100
        v.page().runJavaScript("window.__fp || ''", 0, lambda r: got.__setitem__("r", r))
        if got.get("r"):
            break
    out["r"] = got.get("r")
'''


def _fp(run_ike, level):
    import json
    out = run_ike(STEPS_FP % FP_PROBE, settings={"shield_level": level}, timeout=90)
    return json.loads(out["r"])


def test_h1_m5_noise_cannot_be_peeled_off_and_spoofed_values_look_like_chrome(run_ike):
    """H1: the canvas noise depended only on the session's key and the size,
    so a grey canvas of the same size gave the mask away and XOR-ing it back
    gave the real pixels, the same in every session; audio noise was one
    factor on every 97th sample, read back from a buffer the page wrote;
    measureText('') was the text offset itself. M5: replaced getters never
    threw on a wrong object, Strict had "gpu" with no value and no
    getBattery, Maximum's Intl kept the real language."""
    a, b = _fp(run_ike, "strict"), _fp(run_ike, "strict")
    assert a["recovered"] != b["recovered"], (a, b)       # nothing the same across sessions to recover
    assert a["stable"] and a["ownUntouched"] and a["renderedConsistent"], a
    assert a["emptyWidth"] == 0, a
    assert a["receiver"] == "TypeError", a
    assert a["gpu"] is True and a["adapter"] is None, a
    assert a["battery"] is True and a["batteryLevel"] == [True, 1], a
    m = _fp(run_ike, "maximum")
    assert m["lang"] == "en-US" and m["intl"] == "en-US" and m["number"] == "1,234.5", m
    assert "[native code]" in m["intlNative"], m


def test_m5_strict_sends_the_one_language_it_shows():
    _updater_imports()
    from ike import shields
    assert shields._one_language("it-IT,it;q=0.9,en;q=0.8") == b"it-IT,it;q=0.9"
    assert shields._one_language("de") == b"de"
    assert shields._one_language("") == b"en-US,en;q=0.9"
    assert shields._one_language("x y z") == b"en-US,en;q=0.9"
