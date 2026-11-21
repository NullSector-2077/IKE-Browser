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
    for plain in (archive, b"Cr24" + struct.pack("<III", 2, 0, 0) + archive,
                  b"Cr24", b"Cr24\x03\x00\x00\x00"):     # review 4, N12: short ones too
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
        bridge.cssFetched.connect(lambda ident, ok, text: answers.setdefault(ident, []).append(ok))
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
    yield 1000                         # a second answer would come now
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
    # one answer each (a redirect followed as a new request answered twice:
    # first "failed", then the sheet)
    assert out["answers"] == {"own_sheet": [True], "redirected": [True], "public_to_home": [False]}, out
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
    # review 4, N6: replace the transport object itself and open a channel on
    # a stand-in that forwards to it: the answers must not reach it
    v.page().runJavaScript(r"""
      window.__third = 'none';
      try {
        var real = qt.webChannelTransport, fake = {send: function (m) { return real.send(m); }, onmessage: null};
        qt.webChannelTransport = fake;
        try { window.qt = {webChannelTransport: fake}; } catch (e) {}
        new QWebChannel(fake, function (c) {
          window.__third = c.objects.ike && c.objects.ike.fillRequested ? 'vault' : 'other'; });
      } catch (e) { window.__third = 'refused'; }""", 1)
    yield 1500
    got = {}
    v.page().runJavaScript(
        "JSON.stringify({third: window.__third, second: window.__second,"
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
    assert r["third"] in ("none", "refused"), r
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
    from ike import config
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")
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
        # the next start reads the parsed copy while the file is the same
        # (performance review of 1.1.20, L4): proven by a file of the same
        # size and time whose text would say otherwise
        import os
        assert len(list((tmp_path / "cache").glob("psl-*.bin"))) == 1
        st = os.stat(psl)
        psl.write_text(PSL_SAMPLE.replace("wordpress.com", "wordpress.xyz"))
        os.utime(psl, ns=(st.st_atime_ns, st.st_mtime_ns))
        monkeypatch.setattr(shields, "_PSL", [])
        shields.site_of.cache_clear()
        assert s("a.wordpress.com") == "a.wordpress.com"
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
  // the noisy pixels written back and read again: with a flipped bit the
  // noise undid itself and gave the real picture
  var c2 = document.createElement('canvas'); c2.width = 120; c2.height = 40;
  var x2 = c2.getContext('2d'); x2.putImageData(new ImageData(new Uint8ClampedArray(a), 120, 40), 0, 0);
  R.writeBackSame = h(x2.getImageData(0, 0, 120, 40).data) === h(a);
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
  // review 4, N5: an empty list or a language the engine lacks
  R.intlEmpty = new Intl.DateTimeFormat([]).resolvedOptions().locale;
  try { R.intlUnknown = new Intl.NumberFormat('tlh').resolvedOptions().locale; } catch (e) { R.intlUnknown = 'err ' + e; }
  R.numberEmpty = (1234.5).toLocaleString([]);
  R.numberUnknown = (1234.5).toLocaleString(['tlh']);
  R.dateUnknown = new Date(0).toLocaleDateString('tlh', {timeZone: 'UTC'});
  R.intlKnown = new Intl.NumberFormat(['tlh', 'de']).resolvedOptions().locale;
  try { new Intl.NumberFormat('not a language!'); R.badTag = 'no error'; } catch (e) { R.badTag = e.constructor.name; }
  try {
    var src = "postMessage([new Intl.DateTimeFormat().resolvedOptions().locale, (1234.5).toLocaleString(), " +
      "new Intl.DateTimeFormat([]).resolvedOptions().locale, (1234.5).toLocaleString('tlh')])";
    var wk = new Worker(URL.createObjectURL(new Blob([src], {type: 'text/javascript'})));
    R.workerIntl = await new Promise(function (ok) { wk.onmessage = function (e) { ok(e.data); };
      setTimeout(function () { ok('timeout'); }, 3000); });
  } catch (e) { R.workerIntl = 'error ' + e; }
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


def _fp(run_ike, level, italian=False):
    """The probe at one level; italian: an Italian system and browser (so
    that English shown at Maximum means something)."""
    import json
    settings, env = {"shield_level": level}, None
    if italian:
        settings.update({"language": "it", "accept_language": "it-IT,it;q=0.9"})
        env = {"LANG": "it_IT.UTF-8", "LC_ALL": "it_IT.UTF-8", "LANGUAGE": "it"}
    out = run_ike(STEPS_FP % FP_PROBE, settings=settings, env=env, timeout=90)
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
    assert a["writeBackSame"] is True, a                   # written back and read again: not the real picture
    assert a["emptyWidth"] == 0, a
    assert a["receiver"] == "TypeError", a
    assert a["gpu"] is True and a["adapter"] is None, a
    assert a["battery"] is True and a["batteryLevel"] == [True, 1], a
    it = _fp(run_ike, "balanced", italian=True)
    assert it["intl"].startswith("it") and it["number"] == "1.234,5", it     # the real language, below Maximum
    m = _fp(run_ike, "maximum", italian=True)
    assert m["lang"] == "en-US" and m["intl"] == "en-US" and m["number"] == "1,234.5", m
    assert "[native code]" in m["intlNative"], m
    assert m["workerIntl"] == ["en-US", "1,234.5", "en-US", "1,234.5"], m    # in workers too
    # review 4, N5: no language the engine has means the one shown as well
    assert m["intlEmpty"] == "en-US" and m["intlUnknown"] == "en-US", m
    assert m["numberEmpty"] == "1,234.5" and m["numberUnknown"] == "1,234.5", m
    assert m["dateUnknown"] == "1/1/1970", m
    assert m["intlKnown"] == "de" and m["badTag"] == "RangeError", m     # a known one, and errors, as Chrome


N4_PROBE = r"""
(async function () {
  var R = {}, IM = Math.imul, realHas = WeakSet.prototype.has, realThen = Promise.prototype.then;
  function hs(str) { var x = 2166136261; for (var i = 0; i < str.length; i++) { x ^= str.charCodeAt(i); x = IM(x, 16777619); } return (x >>> 0).toString(16); }
  function grab(a, n) { var o = []; for (var i = 0; i < n; i++) o.push(a[i]); return o; }
  function canvas() {
    var c = document.createElement('canvas'); c.width = 60; c.height = 20; var x = c.getContext('2d');
    x.fillStyle = '#f60'; x.fillRect(0, 0, 60, 20); x.fillStyle = '#069'; x.font = '14px sans-serif';
    x.fillText('IKE probe', 2, 15); return [c, x];
  }
  var N = 60 * 20 * 4;
  function render() {
    var ctx = new OfflineAudioContext(1, 2000, 44100), o = ctx.createOscillator();
    o.frequency.value = 3000; o.connect(ctx.destination); o.start(0); return ctx.startRendering();
  }
  async function step(name, fn) { try { R[name] = await fn(); } catch (e) { R[name] = 'err ' + e; } }
  await step('baseline', function () { return hs(canvas()[0].toDataURL()); });
  // the protection's own sets asked through the page's WeakSet.prototype.has
  await step('hasFalseAudio', async function () {
    WeakSet.prototype.has = function () { return false; };
    try { var b = await render(); return hs(grab(b.getChannelData(0), 2000).join()); }
    finally { WeakSet.prototype.has = realHas; }
  });
  await step('hasFalseFonts', function () {
    WeakSet.prototype.has = function () { return false; };
    try { return document.fonts.size; } finally { WeakSet.prototype.has = realHas; }
  });
  // the rendered buffer marked through the page's Promise.prototype.then
  await step('thenAudio', async function () {
    Promise.prototype.then = function (f, r) { return realThen.call(this, undefined, r); };
    var b;
    try { b = await render(); } finally { Promise.prototype.then = realThen; }
    return hs(grab(b.getChannelData(0), 2000).join());
  });
  // the noise made with the page's Math.imul
  await step('imulAudio', async function () {
    Math.imul = function () { return 0; };
    var b;
    try { b = await render(); var d = grab(b.getChannelData(0), 2000); } finally { Math.imul = IM; }
    return hs(d.join());
  });
  // the noisy copy made with the page's Uint32Array
  await step('u32Url', function () {
    var U32 = window.Uint32Array; window.Uint32Array = function () { throw new Error('no'); };
    try { return hs(canvas()[0].toDataURL()); } finally { window.Uint32Array = U32; }
  });
  // the length of the pixels read through the page's getter
  await step('lengthPixels', function () {
    var TAP = Object.getPrototypeOf(Uint8Array.prototype), d = Object.getOwnPropertyDescriptor(TAP, 'length'), px;
    Object.defineProperty(TAP, 'length', { get: function () { return 0; }, configurable: true });
    try { px = canvas()[1].getImageData(0, 0, 60, 20).data; } finally { Object.defineProperty(TAP, 'length', d); }
    return hs(grab(px, N).join());
  });
  // the pixels found through the page's ImageData.prototype.data
  await step('dataDecoy', function () {
    var d = Object.getOwnPropertyDescriptor(ImageData.prototype, 'data'), img;
    Object.defineProperty(ImageData.prototype, 'data', { get: function () { return new Uint8ClampedArray(4); }, configurable: true });
    try { img = canvas()[1].getImageData(0, 0, 60, 20); } finally { Object.defineProperty(ImageData.prototype, 'data', d); }
    return hs(grab(img.data, N).join());
  });
  // a canvas that reports no size of its own
  await step('widthUrl', function () {
    var c = canvas()[0]; Object.defineProperty(c, 'width', { get: function () { return 0; } });
    return hs(c.toDataURL());
  });
  // a channel number that changes between two reads
  await step('channelTrick', async function () {
    var b = await render(), k = 0, dest = new Float32Array(2000);
    try { b.copyFromChannel(dest, { valueOf: function () { return k++ === 0 ? 0 : 1; } }); } catch (e) {}
    return hs(grab(dest, 2000).join());
  });
  // what a ScriptProcessorNode is handed
  await step('processor', async function () {
    var ctx = new OfflineAudioContext(1, 16384, 44100), o = ctx.createOscillator(), all = [];
    o.frequency.value = 3000;
    var sp = ctx.createScriptProcessor(4096, 1, 1);
    sp.onaudioprocess = function (e) { all.push(grab(e.inputBuffer.getChannelData(0), 4096).join()); };
    o.connect(sp); sp.connect(ctx.destination); o.start(0);
    await ctx.startRendering();
    return all.length ? hs(all.join('|')) : 'none';
  });
  // the full version through the page's Promise.prototype.then
  await step('uaFull', async function () {
    if (!navigator.userAgentData) return 'none';
    var leaked = null;
    Promise.prototype.then = function (f, r) { if (!leaked) leaked = this; return realThen.call(this, f, r); };
    try { navigator.userAgentData.getHighEntropyValues(['uaFullVersion']); } finally { Promise.prototype.then = realThen; }
    if (!leaked) return 'none';
    var v = await leaked;
    return String(v && v.uaFullVersion);
  });
  // review 4, N12: on a wrong object Chrome's requestAdapter rejects
  await step('gpuWrong', async function () {
    if (!window.GPU) return 'TypeError';
    try { await GPU.prototype.requestAdapter.call({}); return 'resolved'; } catch (e) { return e.constructor.name; }
  });
  window.__fp = JSON.stringify(R);
})();
"""


def test_n4_a_page_replacing_built_ins_cannot_skip_the_noise(run_ike):
    """Review 4, N4: the protection called built-ins a page can replace
    (WeakSet/WeakMap methods, Promise.prototype.then, Math.imul,
    Uint32Array, the typed arrays' length, ImageData's data, a canvas's own
    size) while the page ran. Each replacement here gave the real values,
    the same in every session; now the noise stays, different per session."""
    import json
    runs = []
    for _ in range(2):
        out = run_ike((STEPS_FP % N4_PROBE).replace("range(100)", "range(300)"),
                      settings={"shield_level": "strict"}, timeout=120)
        runs.append(json.loads(out["r"]))
    a, b = runs
    for k in ("baseline", "hasFalseAudio", "thenAudio", "imulAudio", "u32Url", "lengthPixels",
              "dataDecoy", "widthUrl", "channelTrick", "processor"):
        assert not str(a[k]).startswith("err") and a[k] != "none", (k, a)
        assert a[k] != b[k], (k, a, b)          # the same in two sessions: the real values
    assert a["hasFalseFonts"] == 0, a           # the masked fonts stay hidden
    assert a["uaFull"] == "none" or a["uaFull"].endswith(".0.0.0"), a
    assert a["gpuWrong"] == "TypeError", a


HA_PROBE = r"""
(async function () {
  var R = {}, RA = Reflect.apply;
  async function step(name, fn) { try { R[name] = await fn(); } catch (e) { R[name] = 'err ' + e; } }
  var gl = document.createElement('canvas').getContext('webgl');
  R.cores = navigator.hardwareConcurrency;
  // the engine's own functions handed to a replaced call / apply
  await step('callCaught', function () {
    var call = Function.prototype.call, apply = Function.prototype.apply, seen = [];
    var args = function (a, from) { var o = []; for (var i = from; i < a.length; i++) o[o.length] = a[i]; return o; };
    Function.prototype.call = function (t) { seen[seen.length] = this; return RA(this, t, args(arguments, 1)); };
    Function.prototype.apply = function (t, a) { seen[seen.length] = this; return RA(this, t, a || []); };
    try {
      navigator.hardwareConcurrency; screen.width; navigator.plugins;
      var c = document.createElement('canvas'); c.width = 4; c.height = 4; c.getContext('2d').getImageData(0, 0, 1, 1);
    } finally { Function.prototype.call = call; Function.prototype.apply = apply; }
    var bad = [];
    for (var i = 0; i < seen.length; i++) if (typeof seen[i] === 'function') bad.push(seen[i].name);
    return bad.join(',');
  });
  // the hidden extension through a replaced filter, toLowerCase, or a name that changes
  await step('filterList', function () {
    var f = Array.prototype.filter;
    Array.prototype.filter = function () { return this; };
    try { return gl.getSupportedExtensions().indexOf('WEBGL_debug_renderer_info') >= 0; } finally { Array.prototype.filter = f; }
  });
  await step('lowerExt', function () {
    var l = String.prototype.toLowerCase;
    String.prototype.toLowerCase = function () { return 'x'; };
    try { return gl.getExtension('WEBGL_debug_renderer_info') !== null; } finally { String.prototype.toLowerCase = l; }
  });
  await step('twoFacedExt', function () {
    var k = 0;
    return gl.getExtension({ toString: function () { return k++ ? 'WEBGL_debug_renderer_info' : 'x'; } }) !== null;
  });
  // the full version through a replaced map or split
  await step('versionLeak', async function () {
    if (!navigator.userAgentData) return 'none';
    var map = Array.prototype.map, split = String.prototype.split, seen = [];
    Array.prototype.map = function () { seen.push(JSON.stringify(this)); return RA(map, this, arguments); };
    String.prototype.split = function () { seen.push(String(this)); return RA(split, this, arguments); };
    var v;
    try { v = await navigator.userAgentData.getHighEntropyValues(['fullVersionList', 'uaFullVersion']); }
    finally { Array.prototype.map = map; String.prototype.split = split; }
    var all = seen.join(' ') + JSON.stringify(v);
    return /\d+\.\d+\.[1-9]\d*\.\d+/.test(all) ? all : 'ok';
  });
  await step('keysInOrder', async function () {
    if (!navigator.userAgentData) return true;
    var v = await navigator.userAgentData.getHighEntropyValues(['wow64', 'architecture', 'model', 'bitness']);
    var k = Object.keys(v);
    return k.join() === k.slice().sort().join();
  });
  // inline workers whose prelude a replaced slice or Blob check would skip
  // (with the prelude the worker hides the debug-renderer extension at Strict)
  var WORKER_NOISE = "var g = new OffscreenCanvas(4, 4).getContext('webgl'); postMessage(g && !g.getExtension('WEBGL_debug_renderer_info') ? 1 : 0)";
  await step('sliceWorker', function () {
    var url = URL.createObjectURL(new Blob([WORKER_NOISE], {type: 'text/javascript'}));
    var sl = String.prototype.slice, w;
    String.prototype.slice = function () { return 'zzzzz'; };
    try { w = new Worker(url); } finally { String.prototype.slice = sl; }
    return new Promise(function (ok) { w.onmessage = function (e) { ok(e.data); }; setTimeout(function () { ok('timeout'); }, 4000); });
  });
  await step('blobCheckWorker', function () {
    Object.defineProperty(Blob, Symbol.hasInstance, { value: function () { return false; }, configurable: true });
    var url;
    try { url = URL.createObjectURL(new Blob([WORKER_NOISE], {type: 'text/javascript'})); }
    finally { delete Blob[Symbol.hasInstance]; }
    var w = new Worker(url);
    return new Promise(function (ok) { w.onmessage = function (e) { ok(e.data); }; setTimeout(function () { ok('timeout'); }, 4000); });
  });
  // a frame added while RegExp.prototype.exec says "no frame here"
  await step('execFrame', function () {
    var ex = RegExp.prototype.exec, d = document.createElement('div');
    document.body.appendChild(d);
    RegExp.prototype.exec = function () { return null; };
    try { d.innerHTML = '<iframe></iframe>'; return d.firstChild.contentWindow.navigator.hardwareConcurrency; }
    finally { RegExp.prototype.exec = ex; }
  });
  window.__fp = JSON.stringify(R);
})();
"""


def test_fp_audit_ha_no_built_in_of_the_page_is_used(run_ike):
    """Fingerprinting audit, H-A (and the rest of review 4's N4): a page that
    replaced call or apply was handed the engine's own functions; a replaced
    filter or toLowerCase showed the hidden WebGL extension, map or split
    the full version; a replaced slice or Blob check started an inline worker
    without its prelude; the keys of getHighEntropyValues came in another
    order than Chrome's."""
    import json
    out = run_ike((STEPS_FP % HA_PROBE).replace("range(100)", "range(300)"),
                  settings={"shield_level": "strict"}, timeout=120,
                  env={"QTWEBENGINE_CHROMIUM_FLAGS": "--no-sandbox --enable-unsafe-swiftshader "
                       "--use-angle=swiftshader --ignore-gpu-blocklist"})     # WebGL here (test only)
    r = json.loads(out["r"])
    assert r["callCaught"] == "", r
    assert r["filterList"] is False and r["lowerExt"] is False and r["twoFacedExt"] is False, r
    assert r["versionLeak"] in ("ok", "none"), r
    assert r["keysInOrder"] is True, r
    assert r["sliceWorker"] > 0 and r["blobCheckWorker"] > 0, r          # the prelude ran
    assert r["execFrame"] == r["cores"], r


HB_PROBE = r"""
(async function () {
  var R = {};
  async function step(name, fn) { try { R[name] = await fn(); } catch (e) { R[name] = 'err ' + e; } }
  function run(url, kind) {
    return new Promise(function (ok) {
      var w = new Worker(url), out = {};
      w.onmessage = function (e) { ok(e.data); };
      w.onerror = function (e) { e.preventDefault(); ok({ filename: e.filename, lineno: e.lineno }); };
      setTimeout(function () { ok('timeout'); }, 5000);
    });
  }
  var SELF = "fetch(self.location.href).then(function (r) { return r.text(); }).then(function (t) {" +
    " postMessage({href: self.location.href, text: t.indexOf('farb' + 'le') >= 0 ? 'prelude' : 'clean', stack: String(new Error('x').stack)}); }," +
    " function (e) { postMessage({href: self.location.href, text: 'failed', stack: String(new Error('x').stack)}); });";
  await step('blob', async function () {
    var url = URL.createObjectURL(new Blob([SELF], {type: 'text/javascript'}));
    var r = await run(url);
    r.same = r.href === url;
    return r;
  });
  await step('blobError', async function () {
    var url = URL.createObjectURL(new Blob(["\n\nthrow new Error('three')"], {type: 'text/javascript'}));
    var r = await run(url);
    return { same: r.filename === url, lineno: r.lineno };
  });
  await step('data', async function () {
    var url = 'data:text/javascript,' + encodeURIComponent(SELF);
    var r = await run(url), r2 = await run(url);
    var seeds = [r, r2].map(function (x) { var m = /\},(\d+),"data:/.exec(decodeURIComponent(x.stack || '')); return m ? m[1] : 'none'; });
    return { same: r.href === url, text: r.text, seeds: seeds };
  });
  await step('entries', async function () {
    var found = 'clean', list = performance.getEntriesByType('resource');
    for (var i = 0; i < list.length; i++) {
      if (list[i].name.slice(0, 5) !== 'blob:') continue;
      try { var t = await (await fetch(list[i].name)).text(); if (t.indexOf('farb' + 'le') >= 0) found = list[i].name; } catch (e) {}
    }
    return found;
  });
  window.__fp = JSON.stringify(R);
})();
"""


def test_fp_audit_hb_the_seed_cannot_be_read_from_a_worker(run_ike):
    """Fingerprinting audit, H-B: an inline worker's address held the
    prelude with the site's seed: fetch(self.location.href) in a blob worker,
    the text of a data: worker's address, or the page's ErrorEvent.filename
    gave it, and with the seed the noise could be removed exactly. Now the
    prelude revokes its own address, the worker's location and its errors
    name the page's own address and line, and a data: worker gets a seed of
    its own."""
    import json
    out = run_ike((STEPS_FP % HB_PROBE).replace("range(100)", "range(300)"),
                  settings={"shield_level": "strict"}, timeout=120)
    r = json.loads(out["r"])
    assert r["blob"]["same"] is True and r["blob"]["text"] in ("failed", "clean"), r
    assert r["blobError"] == {"same": True, "lineno": 3}, r
    assert r["data"]["same"] is True and r["data"]["text"] == "clean", r
    a, b = r["data"]["seeds"]
    assert a == "none" or a != b, r                  # a seed of its own, not the site's
    assert r["entries"] == "clean", r


HD_PROBE = r"""
(async function () {
  var R = {}, T = 'mmmmmmmmmmlli1WQ@#%&ABCxyz', PUA = '';
  async function step(name, fn) { try { R[name] = await fn(); } catch (e) { R[name] = 'err ' + e; } }
  function domW(f, t) {
    var e = document.createElement('span');
    e.style.cssText = 'font-size:72px;position:absolute;white-space:nowrap;font-family:' + f;
    e.textContent = t; document.body.appendChild(e); var w = e.offsetWidth + 'x' + e.offsetHeight; e.remove(); return w;
  }
  function same(t) { return domW("'DejaVu Sans',monospace", t) === domW("'No Such Font Xyz',monospace", t); }
  await step('installed', function () { return document.fonts.check('12px "DejaVu Sans"'); });
  await step('dom', function () { return same(T); });
  await step('pua', function () { return same(PUA); });
  await step('load', async function () {
    var a = await document.fonts.load('12px "DejaVu Sans"', ''), b = await document.fonts.load('12px "No Such Font Xyz"', '');
    return a.length === b.length;
  });
  async function local(name) {
    return new FontFace('t' + Math.random(), 'local("' + name + '")').load().then(function () { return 'loaded'; }, function () { return 'error'; });
  }
  await step('local', function () { return local('DejaVu Sans'); });
  await step('localFace', function () { return local('DejaVuSans-Bold'); });
  await step('clearOther', function () {
    var fr = document.createElement('iframe'); document.body.appendChild(fr);
    Object.getPrototypeOf(fr.contentWindow.document.fonts).clear.call(document.fonts);
    return same(T);
  });
  await step('worker', function () {
    var src = "var c = new OffscreenCanvas(10, 10).getContext('2d');" +
      "function m(f) { c.font = '72px ' + f; return c.measureText('" + T + "').width; }" +
      "var f = new FontFace('w1', 'local(\"DejaVu Sans\")');" +
      "f.load().then(function () { return 'loaded'; }, function () { return 'error'; }).then(function (l) {" +
      " postMessage([m(\"'DejaVu Sans',monospace\") === m(\"'No Such Font Xyz',monospace\"), l, self.fonts.size]); });";
    var w = new Worker(URL.createObjectURL(new Blob([src], {type: 'text/javascript'})));
    return new Promise(function (ok) { w.onmessage = function (e) { ok(e.data); }; setTimeout(function () { ok('timeout'); }, 6000); });
  });
  window.__fp = JSON.stringify(R);
})();
"""


def test_fp_audit_hd_installed_fonts_cannot_be_found(run_ike):
    """Fingerprinting audit, H-D (Strict): the installed fonts were found
    through local() in FontFace, through the masks themselves (U+E000 drawn
    with the mask's empty glyph, fonts.load()), after another realm's clear()
    on the page's font set, and in workers, which had no masks. Each now
    answers as for a font that does not exist."""
    import json
    out = run_ike((STEPS_FP % HD_PROBE).replace("range(100)", "range(300)"),
                  settings={"shield_level": "strict"}, timeout=120)
    r = json.loads(out["r"])
    assert r["dom"] is True and r["pua"] is True and r["load"] is True, r
    assert r["local"] == "error" and r["localFace"] == "error", r
    assert r["clearOther"] is True, r
    assert r["worker"][0] is True and r["worker"][1] == "error" and r["worker"][2] == 0, r


def test_fp_audit_hd_every_installed_family_is_tested():
    """H-D: names outside the list of 714 (IPAGothic, Inter Display) were
    never masked; now every installed family is tested too, but never the
    six every system answers to."""
    _updater_imports()
    from ike import fontcheck
    got = fontcheck.candidates(["IPAGothic", "Inter Display [Foundry]", "Arial", "DejaVu Sans"])
    assert "IPAGothic" in got and "Inter Display" in got and "Arial" not in got
    assert got.count("DejaVu Sans") == 1 and len(got) == len(fontcheck.masked_names()) + 2


HE_PROBE = r"""
(async function () {
  var R = {}, IM = Math.imul;
  async function step(name, fn) { try { R[name] = await fn(); } catch (e) { R[name] = 'err ' + e; } }
  function hs(a, n) { var x = 2166136261; for (var i = 0; i < n; i++) { x ^= a[i] & 255; x = IM(x, 16777619); } return (x >>> 0).toString(16); }
  function gl(kind) {
    // every pixel its own colour: the noise depends on the colours (N3)
    var c = document.createElement('canvas'); c.width = 16; c.height = 16;
    var g = c.getContext(kind, { preserveDrawingBuffer: true });
    g.enable(g.SCISSOR_TEST);
    for (var y = 0; y < 16; y++) for (var x = 0; x < 16; x++) {
      g.scissor(x, y, 1, 1); g.clearColor(x / 16, y / 16, (x * y) / 256, 1); g.clear(g.COLOR_BUFFER_BIT);
    }
    return g;
  }
  await step('clamped', function () {
    var g = gl('webgl'), a = new Uint8ClampedArray(1024); g.readPixels(0, 0, 16, 16, g.RGBA, g.UNSIGNED_BYTE, a); return hs(a, 1024);
  });
  await step('otherRealm', function () {
    var f = document.createElement('iframe'); document.body.appendChild(f);
    var g = gl('webgl'), a = new f.contentWindow.Uint8Array(1024); g.readPixels(0, 0, 16, 16, g.RGBA, g.UNSIGNED_BYTE, a); return hs(a, 1024);
  });
  await step('packBuffer', function () {
    var g = gl('webgl2'), b = g.createBuffer();
    g.bindBuffer(g.PIXEL_PACK_BUFFER, b); g.bufferData(g.PIXEL_PACK_BUFFER, 1024, g.STREAM_READ);
    g.readPixels(0, 0, 16, 16, g.RGBA, g.UNSIGNED_BYTE, 0);
    var out = new Uint8Array(1024); g.getBufferSubData(g.PIXEL_PACK_BUFFER, 0, out); return hs(out, 1024);
  });
  await step('videoFrame', async function () {
    if (!window.VideoFrame) return 'none';
    var c = document.createElement('canvas'); c.width = 16; c.height = 16;
    var x = c.getContext('2d'), gr = x.createLinearGradient(0, 0, 16, 16);
    gr.addColorStop(0, 'rgb(10,200,30)'); gr.addColorStop(1, 'rgb(200,10,190)'); x.fillStyle = gr; x.fillRect(0, 0, 16, 16);
    var vf = new VideoFrame(c, { timestamp: 0 }), buf = new Uint8Array(vf.allocationSize());
    await vf.copyTo(buf); vf.close(); return hs(buf, buf.length);
  });
  await step('float16', function () {
    var c = document.createElement('canvas'); c.width = 60; c.height = 20;
    var x = c.getContext('2d'); x.fillStyle = 'rgb(128,128,128)'; x.fillRect(0, 0, 60, 20);
    var d = x.getImageData(0, 0, 60, 20, { pixelFormat: 'rgba-float16' }).data;
    if (!(d instanceof Float16Array)) return 'none';
    var far = 0, changed = 0;
    for (var i = 0; i < d.length; i++) { if ((i & 3) === 3) continue; if (Math.abs(d[i] - 0.50196) > 0.002) far++; if (d[i] !== d[0]) changed++; }
    return { far: far, changed: changed > 0 };
  });
  await step('analyserBytes', async function () {
    var ctx = new OfflineAudioContext(1, 4096, 44100), o = ctx.createOscillator(), an = ctx.createAnalyser();
    o.frequency.value = 3000; o.connect(an); an.connect(ctx.destination); o.start(0);
    var got = null;
    ctx.suspend(2048 / 44100).then(function () { var a = new Uint8Array(an.frequencyBinCount); an.getByteFrequencyData(a); got = hs(a, a.length); ctx.resume(); });
    await ctx.startRendering(); return got;
  });
  window.__fp = JSON.stringify(R);
})();
"""


def test_fp_audit_he_other_routes_to_the_pixels_get_the_noise(run_ike):
    """Fingerprinting audit, H-E, M-1, M-8: readPixels into a
    Uint8ClampedArray or another realm's array, a WebGL2 pixel-pack buffer
    read with getBufferSubData, VideoFrame.copyTo and the analyser's byte
    data gave the real values (the same in every session); a 16-bit float
    getImageData was corrupted (values became 0 or 1)."""
    import json
    flags = {"QTWEBENGINE_CHROMIUM_FLAGS": "--no-sandbox --enable-unsafe-swiftshader "
             "--use-angle=swiftshader --ignore-gpu-blocklist"}               # WebGL here (test only)
    runs = []
    for _ in range(2):
        out = run_ike((STEPS_FP % HE_PROBE).replace("range(100)", "range(300)"),
                      settings={"shield_level": "balanced"}, timeout=120, env=flags)
        runs.append(json.loads(out["r"]))
    a, b = runs
    for k in ("clamped", "otherRealm", "packBuffer", "videoFrame", "analyserBytes"):
        if a[k] == "none":
            continue                       # not offered by this engine
        assert not str(a[k]).startswith("err") and a[k] is not None, (k, a)
        assert a[k] != b[k], (k, a, b)     # the same in two sessions: the real values
    if a["float16"] != "none":
        assert a["float16"]["far"] == 0 and a["float16"]["changed"] is True, a


def test_fp_audit_m4_the_storage_quota_does_not_tell_the_disk_size(run_ike):
    """Fingerprinting audit, M-4: navigator.storage.estimate().quota was
    60 % of the disk, to the byte; now the same 10 GiB for everyone."""
    out = run_ike((STEPS_FP % """
      navigator.storage.estimate().then(function (e) { window.__fp = JSON.stringify(e.quota); });
    """), timeout=90)
    assert out["r"] == str(10 * 1024 ** 3), out


N3_PROBE = r"""
(async function () {
  var R = {}, IM = Math.imul;
  function h(a, from) { var x = 2166136261; for (var i = from || 0; i < a.length; i++) { x ^= a[i]; x = IM(x, 16777619); } return (x >>> 0).toString(16); }
  function draw(corner) {
    var c = document.createElement('canvas'); c.width = 120; c.height = 40;
    var x = c.getContext('2d');
    x.fillStyle = '#f60'; x.fillRect(0, 0, 120, 40); x.fillStyle = '#069'; x.font = '16px sans-serif';
    x.fillText('I.K.E. probe', 4, 24);
    if (corner !== undefined) { x.fillStyle = 'rgb(' + corner + ',7,9)'; x.fillRect(0, 0, 1, 1); }
    return x.getImageData(0, 0, 120, 40).data;
  }
  // a majority vote over reads that differ in one corner pixel
  var K = 9, reads = [];
  for (var k = 0; k < K; k++) reads.push(draw(10 + 20 * k));
  var rec = new Uint8Array(reads[0].length);
  for (var i = 4; i < rec.length; i++) {
    var ones = 0; for (k = 0; k < K; k++) ones += reads[k][i] & 1;
    rec[i] = (reads[0][i] & 254) | (ones * 2 > K ? 1 : 0);
  }
  R.majority = h(rec, 4);
  // audio: the factors read from a buffer of known samples, then divided out
  async function render() {
    var ctx = new OfflineAudioContext(1, 5000, 44100), o = ctx.createOscillator();
    o.type = 'triangle'; o.frequency.value = 10000;
    var c = ctx.createDynamicsCompressor(); c.threshold.value = -50; c.knee.value = 40; c.ratio.value = 12;
    o.connect(c); c.connect(ctx.destination); o.start(0);
    return (await ctx.startRendering()).getChannelData(0);
  }
  var ctx2 = new OfflineAudioContext(1, 5000, 44100), own = ctx2.createBuffer(1, 5000, 44100);
  own.copyToChannel(new Float32Array(5000).fill(0.75), 0);
  var s = ctx2.createBufferSource(); s.buffer = own; s.connect(ctx2.destination); s.start(0);
  var known = (await ctx2.startRendering()).getChannelData(0), noisy = await render(), sum = 0;
  for (i = 4500; i < 5000; i++) sum += Math.abs(Math.fround(noisy[i] / (known[i] / 0.75)));
  R.audioDivided = sum.toFixed(4);           // as a fingerprint rounds it
  window.__fp = JSON.stringify(R);
})();
"""


def test_n3_repeated_reads_or_a_known_buffer_do_not_remove_the_noise(run_ike):
    """Review 4, N3: the canvas noise depended on the whole picture, so a
    majority vote over reads that differ in one corner gave the real pixels
    back; the audio factor depended only on the sample's place, so a buffer
    of known samples gave every factor and dividing by them gave the real
    sound. Both results were the same in every session."""
    import json
    runs = []
    for _ in range(2):
        out = run_ike(STEPS_FP % N3_PROBE, settings={"shield_level": "balanced"}, timeout=120)
        runs.append(json.loads(out["r"]))
    a, b = runs
    assert a["majority"] != b["majority"], (a, b)
    assert a["audioDivided"] != b["audioDivided"], (a, b)


def test_fp_audit_m3_default_fonts_are_chromes(run_ike):
    """Fingerprinting audit, M-3 (owner's decision): the default font
    families were Qt's, the desktop's own, readable by name and by measuring;
    now Chrome's names, at every level."""
    import json
    out = run_ike((STEPS_FP % r"""
      var s = document.createElement('span'); s.textContent = 'mmmmmmmmmmlli1WQ'; s.style.fontSize = '40px';
      document.body.appendChild(s);
      function w(f) { s.style.fontFamily = f; return s.offsetWidth; }
      window.__fp = JSON.stringify({ body: getComputedStyle(document.body).fontFamily,
        sans: w('sans-serif') === w('Arial'), serif: w('serif') === w('"Times New Roman"') });
    """), timeout=90)
    r = json.loads(out["r"])
    assert r == {"body": '"Times New Roman"', "sans": True, "serif": True}, r


M7_PROBE = r"""
(async function () {
  var R = {};
  var i = document.createElement('input'); i.required = true; R.validation = i.validationMessage;
  R.date = String(new Date(0));
  function worker(make) {
    return new Promise(function (ok) {
      try { make(function (v) { ok(v); }); } catch (e) { ok('err ' + e); }
      setTimeout(function () { ok('timeout'); }, 5000);
    });
  }
  var src = "postMessage([navigator.languages.join(','), new Intl.NumberFormat().resolvedOptions().locale])";
  var url = URL.createObjectURL(new Blob(["onconnect = function (e) { e.ports[0].postMessage([navigator.languages.join(','), new Intl.NumberFormat().resolvedOptions().locale]); }"], {type: 'text/javascript'}));
  R.shared = await worker(function (done) { var w = new SharedWorker(url); w.port.onmessage = function (e) { done(e.data); }; });
  window.__fp = JSON.stringify(R);
})();
"""


def test_fp_audit_m7_maximum_engine_speaks_en_us(run_ike):
    """Fingerprinting audit, M-7 (owner's decision): at the global level
    Maximum, on an Italian system, the engine's own texts, Date's zone name
    and shared workers gave the real language; now en-US."""
    import json
    env = {"LANG": "it_IT.UTF-8", "LC_ALL": "it_IT.UTF-8", "LANGUAGE": "it"}
    settings = {"shield_level": "maximum", "language": "it", "accept_language": "it-IT,it;q=0.9"}
    out = run_ike(STEPS_FP % M7_PROBE, settings=settings, env=env, timeout=90)
    r = json.loads(out["r"])
    assert "Please fill" in r["validation"], r
    assert "Coordinated Universal Time" in r["date"] and "Tempo" not in r["date"], r
    assert r["shared"][0].startswith("en") and r["shared"][1].startswith("en"), r


def test_n12_addresses_from_the_menu_are_never_options(monkeypatch):
    """Review 4, N12 (rest of L11): an "address" such as --profile=x or
    --private handed over by another program was an option of I.K.E.; the
    menu entry ends the options with "--"."""
    import os
    import pathlib

    _updater_imports()
    from conftest import APP

    import ike
    monkeypatch.delenv("IKE_PROFILE", raising=False)
    ike.early_args(["--", "--profile=x"])
    assert "IKE_PROFILE" not in os.environ
    ike.early_args(["--profile=y", "--", "https://example.org/"])
    assert os.environ["IKE_PROFILE"] == "y"
    entry = (pathlib.Path(APP) / "data" / "ike-browser.desktop").read_text()
    assert "Exec=ike-browser -- %U" in entry


def test_n12_dark_mode_style_sheets_carry_the_pages_headers():
    """Review 4, N12 (rest of M4): Sec-Fetch-Site of the style sheets the
    dark mode fetches for a page, as the engine would send it."""
    _updater_imports()
    from PyQt6.QtCore import QUrl

    from ike.passwords import fetch_site
    page = QUrl("https://www.example.co.uk/a")
    assert fetch_site(page, QUrl("https://www.example.co.uk/s.css")) == b"same-origin"
    assert fetch_site(page, QUrl("https://cdn.example.co.uk/s.css")) == b"same-site"
    assert fetch_site(page, QUrl("https://other.co.uk/s.css")) == b"cross-site"
    assert fetch_site(page, QUrl("http://www.example.co.uk/s.css")) == b"cross-site"


def test_m5_strict_sends_the_one_language_it_shows():
    _updater_imports()
    from ike import shields
    assert shields._one_language("it-IT,it;q=0.9,en;q=0.8") == b"it-IT,it;q=0.9"
    assert shields._one_language("de") == b"de"
    assert shields._one_language("") == b"en-US,en;q=0.9"
    assert shields._one_language("x y z") == b"en-US,en;q=0.9"


STEPS_L5 = r'''
P = %d

def steps(ike, qapp, out):
    from PyQt6.QtCore import QUrl
    ike.config["video_ad_skip_hosts"] = ["127.0.0.1"]       # the local server plays the video site
    v = ike.windows[0].current_view()
    page = v.page()
    clicks = out["clicks"] = []
    real = page._dispatch_click
    page._dispatch_click = lambda x, y, now: clicks.append([x, y]) or True
    frame = "<iframe src='http://127.0.0.1:%%d/embed' style='position:absolute;left:0;top:0;width:300px;height:200px;border:0'></iframe>" %% P
    cover = "<div style='position:absolute;left:0;top:0;width:300px;height:200px;background:red'></div>"
    cases = (("no_frame", "<p>no video here</p>"), ("covered", frame + cover), ("on_frame", frame))
    for name, html in cases:
        page._last_embedded = -99.0
        page._last_click = 0.0
        v.setHtml("<title>t</title>" + html, QUrl("https://www.example.org/" + name))
        yield 2500
        before = len(clicks)
        out[name] = page.trusted_click(50, 50, allow_embedded=True)
        yield 800
        out[name + "_clicked"] = len(clicks) - before
    # a second request at once: not again within 3 seconds
    page._last_click = 0.0
    out["again"] = page.trusted_click(50, 50, allow_embedded=True)
    page._dispatch_click = real
'''


def test_l5_the_embedded_video_click_lands_only_on_the_video(run_ike):
    """L5 (the owner chose to harden it): the click that skips an ad in an
    embedded video went wherever the point was when it arrived; the page
    hears the player's request too and could put something of its own there
    to get a real click. Now: only when the page holds a frame of a video
    site, the point must be on that frame when the click is made, and at
    most once every 3 seconds. The ad skip on the video site itself is as
    before (test_security.py, test_videoads.py)."""
    import http.server
    import threading

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = b"<title>player</title><video></video>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        out = run_ike(STEPS_L5 % srv.server_address[1], settings={"https_only": False}, timeout=60)
    finally:
        srv.shutdown()
    assert out["no_frame"] is False and out["no_frame_clicked"] == 0, out
    assert out["covered_clicked"] == 0, out                  # something of the page's own is on the point
    assert out["on_frame"] is True and out["on_frame_clicked"] == 1, out
    assert out["again"] is False, out


STEPS_PERF_M2 = r'''
def steps(ike, qapp, out):
    import sqlite3
    from ike.config import DATA_DIR
    yield 300
    path = str(DATA_DIR / "ike.sqlite")
    other = lambda: sqlite3.connect(path).execute(
        "SELECT COUNT(*) FROM history WHERE url LIKE 'https://perf.example/%'").fetchone()[0]
    for i in range(20):
        ike.storage.add_visit("https://perf.example/%d" % i, "p")
    out["same_connection"] = len(ike.storage.history("perf.example"))
    out["at_once"] = other()                  # not committed one by one
    yield 2600
    out["later"] = other()
    out["indexes"] = sorted(r[0] for r in ike.storage.db.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'history_%'"))
    # an icon drawn again with the same picture is not written again
    from PyQt6.QtGui import QIcon, QPixmap, QColor
    pm = QPixmap(16, 16)
    pm.fill(QColor("red"))
    writes = []
    real = ike.favicons.db
    class Counting:
        def execute(self, *a):
            if str(a[0]).startswith("INSERT"):
                writes.append(1)
            return real.execute(*a)
        def commit(self):
            return real.commit()
    ike.favicons.db = Counting()
    for _ in range(5):
        ike.favicons.store("https://icon.example/", QIcon(pm))
    ike.favicons.db = real
    out["icon_writes"] = len(writes)
    ike.storage.add_visit("https://perf.example/last", "p")     # committed when I.K.E. closes
'''


def test_perf_m2_visits_and_icons_are_committed_together(run_ike, tmp_path):
    """Performance review of 1.1.20, M2, L6, L1: a commit at every page load
    and every icon change waited for the disk in the interface thread; the
    same icon was written again at every redraw; the history had no index."""
    import sqlite3
    out = run_ike(STEPS_PERF_M2, timeout=60)
    assert out["same_connection"] == 20 and out["at_once"] == 0 and out["later"] == 20, out
    assert out["indexes"] == ["history_last", "history_visits"], out
    assert out["icon_writes"] == 1, out
    db = next(tmp_path.rglob("ike.sqlite"))
    n = sqlite3.connect(str(db)).execute(
        "SELECT COUNT(*) FROM history WHERE url = 'https://perf.example/last'").fetchone()[0]
    assert n == 1                           # the last visit, committed when I.K.E. closed


def test_perf_l3_no_download_code_at_start_up():
    """Performance review of 1.1.20, L3: urllib.request (and http.client,
    email) cost about 10 ms at every start, only to be used when something
    is downloaded."""
    import subprocess
    import sys

    from conftest import APP
    code = ("import sys; sys.path.insert(0, %r); import ike.app, ike.blocker, ike.updater, ike.userscripts, "
            "ike.doh, ike.chromever, ike.drm, ike.favicons, ike.shields, ike.passwords, ike.window; "
            "print('urllib.request' in sys.modules, 'http.client' in sys.modules)" % str(APP))
    res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         env={"QT_QPA_PLATFORM": "offscreen", "HOME": "/tmp"})
    assert res.stdout.split() == ["False", "False"], res.stdout + res.stderr


def test_perf_l8_encrypted_dns_asks_once_on_one_connection(monkeypatch):
    """Performance review of 1.1.20, L8: every question opened a new
    connection (a TLS handshake each with a real provider), and the same name
    asked by many requests at once was asked as many times."""
    import base64
    import http.server
    import struct
    import threading
    from urllib.parse import parse_qs, urlsplit
    _updater_imports()
    from ike import doh
    conns, questions = set(), []

    class Doh(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self):
            conns.add(self.client_address)
            q = base64.urlsafe_b64decode(parse_qs(urlsplit(self.path).query)["dns"][0] + "==")
            i = 12
            while q[i]:
                i += 1 + q[i]
            qtype = struct.unpack(">H", q[i + 1:i + 3])[0]
            questions.append(qtype)
            threading.Event().wait(0.05)
            answer = b"\xc0\x0c" + struct.pack(">HHIH", 1, 1, 60, 4) + bytes([127, 0, 0, 9]) if qtype == 1 else b""
            body = q[:2] + struct.pack(">HHHHH", 0x8180, 1, 1 if answer else 0, 0, 0) + q[12:i + 5] + answer
            self.send_response(200)
            self.send_header("Content-Type", "application/dns-message")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Doh)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    for k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "ALL_PROXY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("IKE_TEST_DOH", "http://127.0.0.1:%d/dns-query" % srv.server_address[1])
    monkeypatch.setenv("IKE_TEST_HOOK", "x")              # the tests' provider only in the tests (N10)
    try:
        doh.configure(None)
        got = []
        threads = [threading.Thread(target=lambda: got.append(doh.addresses("same.example")))
                   for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(10)
        assert got == [["127.0.0.9"]] * 10, got
        assert len(questions) == 2, questions               # A and AAAA, once
        for n in range(5):
            doh.addresses("name%d.example" % n)
        assert len(conns) == 1, conns                        # one connection for all
    finally:
        monkeypatch.delenv("IKE_TEST_DOH")
        doh.configure(None)
        srv.shutdown()


STEPS_PERF_L2 = r'''
def steps(ike, qapp, out):
    import threading
    from ike.blocker import Blocker
    out["ready_at_start"] = (ike.blocker.engine is not None or ike.blocker.fallback is not None)
    b = Blocker(ike.config, ike)
    names = []
    real = b._build
    b._build = lambda snap, sig: names.append(threading.current_thread().name) or real(snap, sig)
    b.prepare()
    b.load()                                  # waits for the one prepare() started
    out["threads"] = names
    out["installed"] = b.engine is not None or b.fallback is not None
    yield 10
'''


def test_perf_l2_the_first_engine_is_built_while_ike_sets_up(run_ike):
    """Performance review of 1.1.20, L2: the first ad-blocking engine was
    built in the interface thread before the window (about 245 ms cold).
    Now it is built in its own thread from the start of set-up, and load()
    takes it before any page can make a request."""
    out = run_ike(STEPS_PERF_L2, timeout=60)
    assert out["ready_at_start"] is True, out
    assert len(out["threads"]) == 1 and out["threads"][0].startswith("ike-adblock"), out
    assert out["installed"] is True, out


BOOT_CONFIRM = r'''
import json, sys
sys.path.insert(0, %r)
import ike_boot
folder, state, _ = ike_boot.choose()
print(json.dumps([str(folder), state.get("bad", [])]), flush=True)
for line in sys.stdin:
    if line.strip() == "confirm":
        from ike import updater
        updater.confirm_healthy()                 # what I.K.E. does after 20 s running fine
        print("confirmed", flush=True)
    else:
        break
'''


def test_n8_an_old_window_left_open_does_not_cost_the_next_update(tmp_path):
    """Review 4, N8: the lock of an update's first start was held for the
    whole life of that process. With that window still open when the next
    update restarted I.K.E., two starts from other programs rolled the new,
    healthy update back for good. The lock now ends when the start is
    confirmed healthy."""
    import json
    import os
    import subprocess
    import sys

    from conftest import APP
    updates = tmp_path / "ike-browser" / "updates"

    def stage(v, **st):
        d = updates / "versions" / v / "ike"
        d.mkdir(parents=True, exist_ok=True)
        (d / "__init__.py").write_text('__version__ = "%s"\n' % v)
        s = json.loads((updates / "state.json").read_text()) if (updates / "state.json").exists() else {}
        s.update(st)
        (updates / "state.json").write_text(json.dumps(s))
    env = dict(os.environ, XDG_DATA_HOME=str(tmp_path))
    code = BOOT_CONFIRM % str(APP)

    def start():
        p = subprocess.Popen([sys.executable, "-c", code], env=env, stdout=subprocess.PIPE, stdin=subprocess.PIPE,
                             text=True)
        return p, json.loads(p.stdout.readline())
    stage("98.0.0", current="98.0.0", status="pending", attempts=0)
    old, _ = start()                                   # the first start of 98, left open for days
    old.stdin.write("confirm\n")
    old.stdin.flush()
    assert old.stdout.readline().strip() == "confirmed"
    stage("99.0.0", current="99.0.0", previous="98.0.0", status="pending", attempts=0)
    new, _ = start()                                   # "restart to update": 99's first start
    old.stdin.close()                                  # the old window closes meanwhile
    old.wait(10)
    try:
        for _ in range(2):                             # two links from other programs within 20 s
            p, got = start()
            p.stdin.close()
            p.wait(10)
            assert got[0].endswith("99.0.0"), got
    finally:
        new.stdin.close()
        new.wait(10)
    state = json.loads((updates / "state.json").read_text())
    assert state["current"] == "99.0.0" and "99.0.0" not in state.get("bad", []), state


def test_n9_n10_encrypted_dns_addresses_and_answers(monkeypatch):
    """Review 4, N9: an address in Chrome's own form ("{?dns}") or two
    addresses made every own request fail without a word (updates and filter
    lists too). N10: a cut answer raised an error nobody caught; the tests'
    own provider was taken from the environment outside the tests."""
    _updater_imports()
    from ike import doh
    t = doh.own_template
    assert t("https://dns.example/dns-query{?dns}") == "https://dns.example/dns-query"
    assert t("https://a.example/q https://b.example/q") == "https://a.example/q"
    assert t("") is None and t("not a url") is None
    import pytest
    with pytest.raises(ValueError):
        doh.parse(b"\x00\x00\x81\x80\x00\x01\x00\x01\x00\x00\x00\x00\x01a\x00\x00\x01\x00\x01\xc0\x0c\x00", 1)
    monkeypatch.setenv("IKE_TEST_DOH", "http://127.0.0.1:9/dns-query")
    monkeypatch.delenv("IKE_TEST_HOOK", raising=False)
    try:
        doh.configure("https://dns.example/dns-query{?dns}")
        assert doh.TEMPLATE[0] == "https://dns.example/dns-query"        # not the environment's
        monkeypatch.setenv("IKE_TEST_HOOK", "x")
        doh.configure(None)
        assert doh.TEMPLATE[0] == "http://127.0.0.1:9/dns-query"
    finally:
        monkeypatch.delenv("IKE_TEST_DOH")
        doh.configure(None)


STEPS_N9 = r'''
def steps(ike, qapp, out):
    from ike import doh
    told = out["told"] = []
    ike._notify = lambda text: told.append(text)
    ike._apply_dns()
    got = []
    doh.lookup_async("nothing.example", lambda r: got.append(r))
    doh.lookup_async("other.example", lambda r: got.append(r))
    for _ in range(100):
        yield 100
        if len(got) == 2 and told:
            break
    yield 300
    out["got"] = got
'''


def test_n9_a_provider_that_does_not_answer_is_said_once(run_ike):
    out = run_ike(STEPS_N9, env={"IKE_TEST_DOH": "http://127.0.0.1:9/dns-query"}, timeout=60)
    assert out["got"] == [None, None], out
    assert len(out["told"]) == 1 and "Encrypted DNS" in out["told"][0], out
