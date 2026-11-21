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
