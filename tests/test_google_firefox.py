"""Google's sites see a current Firefox, with the protections on (1.1.27, the
owner's decision).

Google's sign-in and its anti-abuse checks refuse Qt WebEngine's Chromium
("this browser may not be secure"). Until 1.1.26 only accounts.google.com was
given a Firefox, a fixed Firefox 140 more than a year old, while the engine's
client hints still said "Chromium";v="140" in the same request, and Google's
sensitive services (AI Studio's API keys, the cloud console...) were left with
no protection at all instead. Now:

- every request of a page of Google's sites, a Google sign-in page embedded in
  another site and what that page loads carry the Firefox of the calendar in
  the header, and the engine's client hints go out empty;
- the same pages see that Firefox in JavaScript, in every frame, with getters
  that read as the engine's own, no navigator.userAgentData and no
  window.chrome; also where the user turned the fingerprint protection off
  for the site (the header is changed there too);
- other sites keep the engine's own identity;
- Google's services keep the user's level: no "Compatibility" or "off" forced
  any more (PayPal's and Stripe's stay as they were);
- Google's own domains count as the site on Google's pages ("same site, free
  way" at Balanced), its ad and analytics domains do not.

SIMULATION: Google's host names are mapped to a local server
(--host-resolver-rules), over https with a certificate of the test's own (the
engine sends client hints and userAgentData to secure origins only); the
server records each request's headers.
"""

import ssl
import threading
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

# the proxy of the environment would see Google's names, not the local server
NO_PROXY_ENV = {"http_proxy": "", "https_proxy": "", "HTTP_PROXY": "", "HTTPS_PROXY": "", "all_proxy": "",
                "ALL_PROXY": "", "no_proxy": "*", "NO_PROXY": "*"}

HOSTS = ("www.google.com", "aistudio.google.com", "accounts.google.com", "www.gstatic.com",
         "shop.example.test", "www.example.test")

REPORT = b"""<script>
function report() {
  var d = Object.getOwnPropertyDescriptor(Navigator.prototype, 'userAgent');
  return {host: location.hostname, ua: navigator.userAgent,
          uad: 'userAgentData' in navigator,
          chrome: 'chrome' in window, oscpu: navigator.oscpu || '', vendor: navigator.vendor,
          getter: Function.prototype.toString.call(d.get),
          own: Function.prototype.toString.call(Object.getOwnPropertyDescriptor(Navigator.prototype, 'oscpu') ?
               Object.getOwnPropertyDescriptor(Navigator.prototype, 'oscpu').get : function () {})};
}
fetch('https://www.gstatic.com/res-' + location.hostname, {mode: 'no-cors'}).catch(function () {});
if (window.top !== window) window.top.postMessage(JSON.stringify(report()), '*');
</script>"""

PAGES = {
    # a page of Google's with a frame of another site in it
    "www.google.com": b"<!doctype html><title>g</title>" + REPORT +
                      b"<iframe src='https://www.example.test/framed'></iframe>",
    "aistudio.google.com": b"<!doctype html><title>a</title>" + REPORT,
    # another site with Google's sign-in embedded
    "shop.example.test": b"<!doctype html><title>s</title>" + REPORT +
                         b"<iframe src='https://accounts.google.com/gsi/button'></iframe>",
    "accounts.google.com": b"<!doctype html><title>b</title>" + REPORT,
    "www.example.test": b"<!doctype html><title>e</title>" + REPORT,
}
FRAMES = b"""<script>window.frames_ = []; window.addEventListener('message', function (e) {
  window.frames_.push(e.data); });</script>"""


def _certificate(folder):
    """A certificate of the test's own for every host name of HOSTS."""
    import datetime

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, HOSTS[0])])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=2))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(h) for h in HOSTS]), critical=False)
            .sign(key, hashes.SHA256()))
    cert_file, key_file = folder / "cert.pem", folder / "key.pem"
    cert_file.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_file.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                           serialization.NoEncryption()))
    return cert_file, key_file


@pytest.fixture
def site(tmp_path_factory):
    seen = []

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            host = self.headers.get("Host", "").split(":")[0]
            seen.append({"host": host, "path": self.path, "ua": self.headers.get("User-Agent", ""),
                         "hints": {k.lower(): v for k, v in self.headers.items()
                                   if k.lower().startswith("sec-ch-ua")}})
            body = PAGES.get(host, b"ok") if not self.path.startswith("/res") else b"ok"
            if body != b"ok" and self.path == "/":
                body = FRAMES + body
            self.send_response(200)
            self.send_header("Content-Type", "text/html" if body != b"ok" else "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(*(str(f) for f in _certificate(tmp_path_factory.mktemp("cert"))))
    srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1], seen
    srv.shutdown()


STEPS = r'''
import json
from PyQt6.QtCore import QUrl

PORT = %d

def steps(ike, qapp, out):
    view = ike.windows[0].current_view()
    for host in ("www.google.com", "aistudio.google.com", "shop.example.test"):
        done = {}
        view.page().loadFinished.connect(lambda ok, d=done: d.setdefault("ok", ok))
        view.load(QUrl("https://%%s/" %% host))
        while "ok" not in done:
            yield 20
        res = {}
        for _ in range(100):
            view.page().runJavaScript("JSON.stringify([report(), window.frames_ || []])", 0,
                                      lambda r, res=res: res.__setitem__("r", r))
            while "r" not in res:
                yield 20
            page, frames = json.loads(res.pop("r") or "[{}, []]")
            if host == "aistudio.google.com" or frames:
                break
            yield 100
        yield 600
        out[host] = {"page": page, "frames": [json.loads(f) for f in frames]}
    c = ike.config
    out["levels"] = [c.level_for(h) for h in ("aistudio.google.com", "accounts.google.com",
                                               "console.cloud.google.com", "www.paypal.com",
                                               "login.live.com")]
    out["handsoff"] = [c.sensitive_hands_off(h) for h in ("aistudio.google.com", "www.paypal.com")]
    fp = [s.sourceCode() for s in ike.profile.scripts().find("content")]
    out["fp_aistudio_off"] = any('"aistudio.google.com": "off"' in f for f in fp)
    out["fp_accounts_compat"] = any('"accounts.google.com": "compatibility"' in f for f in fp)
    out["fp_live_compat"] = any('"login.live.com": "compatibility"' in f for f in fp)
'''


def run(run_ike, site, settings):
    port, seen = site
    rules = ", ".join("MAP %s 127.0.0.1:%d" % (h, port) for h in HOSTS)
    # the test's own certificate is accepted (IKE_ALLOW_UNSAFE_ENGINE keeps the switch in tests)
    env = dict(NO_PROXY_ENV, QTWEBENGINE_CHROMIUM_FLAGS='--no-sandbox "--host-resolver-rules=%s" '
               '--ignore-certificate-errors' % rules)
    base = {"shield_level": "balanced", "login_compat": True}
    base.update(settings)
    out = run_ike(STEPS % port, settings=base, env=env, timeout=150)
    assert "error" not in out, out.get("error")
    return out, seen


def firefox(ua):
    return ua.startswith("Mozilla/5.0 (X11; Linux x86_64; rv:") and "Gecko/20100101 Firefox/" in ua \
        and "Chrome" not in ua


def test_the_firefox_of_the_calendar():
    from ike import osinfo
    assert osinfo.firefox_major(date(2026, 11, 24)) == 161
    assert osinfo.firefox_major(date(2026, 12, 21)) == 161          # never ahead of a release
    assert osinfo.firefox_major(date(2027, 11, 24)) == 161 + 365 // 28
    assert osinfo.firefox_major(date(2025, 1, 1)) == 161            # a wrong clock: never older
    ua = osinfo.firefox_user_agent(170)
    assert ua == "Mozilla/5.0 (X11; Linux x86_64; rv:170.0) Gecko/20100101 Firefox/170.0"
    assert osinfo.firefox_major() >= 161


def test_google_sites_by_name():
    from ike.config import google_site
    for h in ("google.com", "www.google.com", "aistudio.google.com", "accounts.google.com",
              "www.google.it", "google.co.uk", "www.google.com.br", "www.gstatic.com",
              "fonts.googleapis.com", "accounts.youtube.com"):
        assert google_site(h), h
    for h in ("notgoogle.com", "google.com.evil.example", "www.youtube.com", "youtube.com",
              "google.example.test", "www.doubleclick.net", "www.google-analytics.com",
              "googletagmanager.com", ""):
        assert not google_site(h), h


def test_google_sees_a_current_firefox_with_the_protections_on(run_ike, site):
    out, seen = run(run_ike, site, {})
    from ike import osinfo
    want = "Firefox/%d.0" % osinfo.firefox_major()

    def requests(host, path=None):
        return [r for r in seen if r["host"] == host and (path is None or r["path"].startswith(path))]

    # headers: Google's pages, everything they load, the sign-in embedded in a shop
    for host, path in (("www.google.com", "/"), ("aistudio.google.com", "/"),
                       ("www.gstatic.com", "/res-www.google.com"), ("www.example.test", "/framed"),
                       ("www.gstatic.com", "/res-www.example.test"), ("accounts.google.com", "/gsi"),
                       ("www.gstatic.com", "/res-accounts.google.com")):
        got = requests(host, path)
        assert got, (host, path, seen)
        for r in got:
            assert firefox(r["ua"]) and r["ua"].endswith(want), r
            assert r["hints"].get("sec-ch-ua") == "", r              # no "Chromium" beside Firefox
            assert all(v == "" for v in r["hints"].values()), r
    # another site: the engine's own identity
    for r in [r for r in requests("shop.example.test", "/") if r["path"] != "/favicon.ico"] + \
            requests("www.gstatic.com", "/res-shop.example.test"):
        assert "Chrome/" in r["ua"] and not firefox(r["ua"]), r
        assert "Chromium" in r["hints"].get("sec-ch-ua", ""), r

    # JavaScript: the same Firefox in every frame of Google's pages and in the sign-in frame
    g, a, s = out["www.google.com"], out["aistudio.google.com"], out["shop.example.test"]
    frame_in_google = [f for f in g["frames"] if f["host"] == "www.example.test"]
    signin_in_shop = [f for f in s["frames"] if f["host"] == "accounts.google.com"]
    assert frame_in_google and signin_in_shop, out
    for r in (g["page"], a["page"], frame_in_google[0], signin_in_shop[0]):
        assert firefox(r["ua"]) and r["ua"].endswith(want), r
        assert not r["uad"] and not r["chrome"], r
        assert r["oscpu"] == "Linux x86_64" and r["vendor"] == "", r
        assert r["getter"] == "function get userAgent() { [native code] }", r
        assert r["own"] == "function get oscpu() { [native code] }", r
    assert "Chrome/" in s["page"]["ua"] and s["page"]["uad"] and s["page"]["oscpu"] == "", s

    # the protections stay on: the user's level, no hands-off for Google (PayPal's kept)
    assert out["levels"] == ["balanced", "balanced", "balanced", "compatibility", "compatibility"], out
    assert out["handsoff"] == [False, True], out
    assert not out["fp_aistudio_off"] and not out["fp_accounts_compat"], out
    assert out["fp_live_compat"], out                              # Microsoft's sign-in as before


def test_firefox_also_without_the_fingerprint_protection(run_ike, site):
    # the user turned the fingerprint protection off on Google's sites: the
    # header still says Firefox, so the page must say it too
    out, seen = run(run_ike, site, {"site_opts": {"google.com": {"fp": False}}})
    page = out["aistudio.google.com"]["page"]
    assert firefox(page["ua"]) and not page["uad"] and not page["chrome"], page
    assert page["getter"] == "function get userAgent() { [native code] }", page


def test_nothing_changes_with_the_shield_off(run_ike, site):
    out, seen = run(run_ike, site, {"shield_level": "off"})
    page = out["aistudio.google.com"]["page"]
    assert "Chrome/" in page["ua"] and page["uad"], page
    for r in seen:
        assert not firefox(r["ua"]), r


def test_without_the_sign_in_help_nothing_changes(run_ike, site):
    out, seen = run(run_ike, site, {"login_compat": False})
    assert "Chrome/" in out["www.google.com"]["page"]["ua"]
    for r in seen:
        assert not firefox(r["ua"]), r


def test_google_family_is_one_site_on_googles_pages():
    """At Balanced Google's own domains go the free way on Google's pages, as
    a site's own requests do; on other sites, and its ad domains, as before."""
    from ike.shields import firefox_request
    assert firefox_request("www.google.com", "www.gstatic.com", "www.google.com")
    assert firefox_request("shop.example", "accounts.google.com", "shop.example")
    assert firefox_request("shop.example", "www.gstatic.com", "accounts.google.com")
    assert not firefox_request("shop.example", "www.gstatic.com", "shop.example")
    assert not firefox_request("www.youtube.com", "www.youtube.com", "www.youtube.com")

