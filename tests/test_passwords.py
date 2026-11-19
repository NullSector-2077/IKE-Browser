"""Password manager: the vault file, and the origin a login is saved for and
filled on.

A vault opens only with its master password and only when it was sealed as
I.K.E.'s own (a file sealed for another program, or altered, is refused).

origin_of() rules (scheme, host case, default and explicit ports, IPv6), and in
the real browser: a saved login is offered and filled only on its exact origin
(not on another port, another scheme or a subdomain), and after a redirect the
origin of the page at fill time counts. Site names are mapped to a local
server with Chromium's host resolver rules.
"""

import base64
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from ike.passwords import origin_of

FORM = (b"<!doctype html><title>login</title><form><input name=user id=u>"
        b"<input type=password name=pw id=p><button>go</button></form>")


def test_origin_rules():
    assert origin_of("https://Site.Example/login?x=1") == "https://site.example"
    assert origin_of("https://site.example:443/") == "https://site.example"
    assert origin_of("http://site.example:80/") == "http://site.example"
    # the default port of the scheme only (earlier versions dropped both 80 and 443 for both)
    assert origin_of("http://site.example:443/") == "http://site.example:443"
    assert origin_of("https://site.example:80/") == "https://site.example:80"
    assert origin_of("https://site.example:8443/") == "https://site.example:8443"
    assert origin_of("HTTPS://site.example") == "https://site.example"
    assert origin_of("site.example") == "https://site.example"           # CSV import without a scheme
    assert origin_of("http://a.site.example/") != origin_of("http://site.example/")
    assert origin_of("http://[::1]:8080/") == "http://[::1]:8080"
    assert origin_of("http://site.example:99999/") == ""
    assert origin_of("http://site.example:port/") == ""
    assert origin_of("ftp://site.example/") == "" and origin_of("javascript:alert(1)") == ""
    # entries saved by older versions for ordinary addresses keep the same key
    for url in ("https://site.example/", "http://site.example/", "https://site.example:8443/a"):
        assert origin_of(url) == origin_of(origin_of(url))


def test_vault_opens_only_as_sealed_by_ike(tmp_path):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    from ike import passwords
    vault = passwords.Vault(tmp_path / "vault.bin")
    vault.create("master")
    vault.entries = [{"origin": "https://example.org", "user": "me", "password": "secret"}]
    vault.save()
    again = passwords.Vault(vault.path)
    assert not again.unlock("wrong") and not again.unlocked
    assert again.unlock("master") and again.entries[0]["password"] == "secret"

    original = vault.path.read_text("utf-8")
    blob = json.loads(original)
    key = vault._derive("master", base64.b64decode(blob["salt"]))
    # the same entries and key, sealed with another program's associated data
    for aad in (b"other-vault-1", b"", None):
        nonce = os.urandom(12)
        data = AESGCM(key).encrypt(nonce, json.dumps(vault.entries).encode(), aad)
        other = dict(blob, nonce=base64.b64encode(nonce).decode(), data=base64.b64encode(data).decode())
        vault.path.write_text(json.dumps(other), "utf-8")
        refused = passwords.Vault(vault.path)
        assert not refused.unlock("master") and not refused.unlocked, aad
        # a refused file is left exactly as it was
        assert json.loads(vault.path.read_text("utf-8")) == other
    # one byte of the sealed data changed
    raw = bytearray(base64.b64decode(blob["data"]))
    raw[0] ^= 1
    vault.path.write_text(json.dumps(dict(blob, data=base64.b64encode(bytes(raw)).decode())), "utf-8")
    assert not passwords.Vault(vault.path).unlock("master")
    # damaged or foreign files
    for text in ("", "{}", "not json", json.dumps({"salt": "x", "nonce": "y", "data": "z"})):
        vault.path.write_text(text, "utf-8")
        assert not passwords.Vault(vault.path).unlock("master")
    vault.path.write_text(original, "utf-8")
    assert passwords.Vault(vault.path).unlock("master")


@pytest.fixture
def site():
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.startswith("/redirect?"):
                self.send_response(302)
                self.send_header("Location", self.path.split("?", 1)[1])
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(FORM)))
            self.end_headers()
            self.wfile.write(FORM)

        def log_message(self, *a):
            pass
    servers = [ThreadingHTTPServer(("127.0.0.1", 0), H) for _ in range(2)]
    for s in servers:
        threading.Thread(target=s.serve_forever, daemon=True).start()
    yield [s.server_address[1] for s in servers]
    for s in servers:
        s.shutdown()


STEPS = r'''
import json
from PyQt6.QtCore import QUrl

def steps(ike, qapp, out):
    pm = ike.passwords
    pm.vault.create("test master")
    for origin, user in SAVED:
        pm.vault.put(origin, user, "pw-" + user)
    v = ike.windows[0].current_view()
    for url in PAGES:
        done = {}
        v.page().loadFinished.connect(lambda ok, done=done: done.setdefault("ok", ok))
        v.load(QUrl(url))
        while "ok" not in done:
            yield 20
        yield 400
        filled = pm.fill(v)
        yield 400
        res = {}
        v.page().runJavaScript("document.getElementById('u').value + '/' + document.getElementById('p').value",
                               0, lambda r, res=res: res.setdefault("r", r))
        while "r" not in res:
            yield 20
        out.setdefault("pages", []).append({"url": v.url().toString(), "origin": pm._origin(v.page()),
                                            "offered": json.loads(pm.logins_json(v.page())),
                                            "filled": filled, "fields": res["r"]})
'''


def test_fill_only_on_exact_origin(run_ike, site):
    port, port2 = site
    saved = [("http://localhost:%d" % port, "main"), ("http://a.localhost:%d" % port, "sub"),
             ("http://localhost:%d" % port2, "otherport"), ("https://localhost:%d" % port, "secure")]
    pages = ["http://LocalHost:%d/login" % port,                 # host case does not matter
             "http://b.localhost:%d/login" % port,               # another subdomain: nothing
             "http://localhost:%d/login" % port2,                # another port: its own login
             "http://c.localhost:%d/redirect?http://a.localhost:%d/login" % (port, port)]
    head = "SAVED = %r\nPAGES = %r\n" % (saved, pages)
    # the local server speaks plain HTTP: no automatic upgrade to HTTPS
    out = run_ike(head + STEPS, settings={"https_only": False}, timeout=120)
    main, other_sub, other_port, redirected = out["pages"]
    assert main["origin"] == "http://localhost:%d" % port
    assert [e["u"] for e in main["offered"]] == ["main"] and main["fields"] == "main/pw-main"
    assert other_sub["offered"] == [] and not other_sub["filled"] and other_sub["fields"] == "/"
    assert [e["u"] for e in other_port["offered"]] == ["otherport"]
    assert other_port["fields"] == "otherport/pw-otherport"
    # the page's origin at fill time: the redirect's target, not the address typed
    assert redirected["url"].startswith("http://a.localhost:%d" % port)
    assert [e["u"] for e in redirected["offered"]] == ["sub"] and redirected["fields"] == "sub/pw-sub"


HARVESTER = (b"<!doctype html><title>login</title><form><input name=user id=u>"
             b"<input type=password name=pw id=p><button>go</button></form><script>"
             b"window.stolen = [];"
             # a script of the page (an advert, say) makes its own tiny login form
             b"var f = document.createElement('form');"
             b"f.innerHTML = '<input id=hu><input type=password id=hp style=\"width:2px;height:2px;opacity:0\">';"
             b"document.body.appendChild(f);"
             b"var hp = document.getElementById('hp');"
             # and pretends to be the user: focus, click and pointer events of its own
             b"setTimeout(function () { hp.focus(); hp.click();"
             b" hp.dispatchEvent(new PointerEvent('pointerdown', {bubbles: true}));"
             b" hp.dispatchEvent(new KeyboardEvent('keyup', {key: 'Tab', bubbles: true})); }, 300);"
             b"setInterval(function () { var v = hp.value || document.getElementById('p').value;"
             b" if (v) stolen.push(v); }, 100);"
             b"</script>")


def test_a_page_cannot_harvest_a_saved_password(run_ike):
    """A saved login is filled in only when the user clicks into the form: a
    page that builds a hidden login form, or clicks and focuses it with its own
    script, reads nothing. A real click fills the user's form at once."""
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(HARVESTER)))
            self.end_headers()
            self.wfile.write(HARVESTER)

        def log_message(self, *a):
            pass
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    try:
        out = run_ike(r'''
PORT = %d

def steps(ike, qapp, out):
    from PyQt6.QtCore import QPoint, Qt, QUrl
    from PyQt6.QtTest import QTest
    pm = ike.passwords
    pm.vault.create("test master")
    pm.vault.put("http://localhost:%%d" %% PORT, "me", "secret-pw")
    v = ike.windows[0].current_view()
    done = {}
    v.page().loadFinished.connect(lambda ok: done.setdefault("ok", ok))
    v.load(QUrl("http://localhost:%%d/login" %% PORT))
    while "ok" not in done:
        yield 20
    yield 2500

    def js(code):
        res = {}
        v.page().runJavaScript(code, 0, lambda r: res.setdefault("r", r))
        return res
    r = js("JSON.stringify([window.stolen, document.getElementById('u').value,"
           " document.getElementById('p').value])")
    while "r" not in r:
        yield 20
    out["before_click"] = r["r"]
    r = js("(function () { var b = document.getElementById('p').getBoundingClientRect();"
           " return [b.left + b.width / 2, b.top + b.height / 2]; })()")
    while "r" not in r:
        yield 20
    x, y = r["r"]
    target = v.focusProxy() or v
    QTest.mouseClick(target, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     QPoint(int(x), int(y)))
    yield 1200
    r = js("[document.getElementById('u').value, document.getElementById('p').value]")
    while "r" not in r:
        yield 20
    out["after_click"] = r["r"]
''' % port, settings={"https_only": False}, timeout=120)
    finally:
        srv.shutdown()
    stolen, user, pw = json.loads(out["before_click"])
    assert stolen == [] and user == "" and pw == "", out["before_click"]
    assert out["after_click"] == ["me", "secret-pw"], out
