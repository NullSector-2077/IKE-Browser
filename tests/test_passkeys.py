"""Passkey questions get an answer (1.1.31, the owner: "we must find a solution").

Arch's Qt WebEngine never settles the promises of
PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable(),
isConditionalMediationAvailable() and getClientCapabilities() (other builds
answer the first two, none the third): a sign-in page that waits for them
waits for ever, at every level and in Falkon too. From Compatibility up they
are answered as Chromium 140 answers them on Linux (measured with Chrome for
Testing 140.0.7339.207): false, true, and the same capabilities in the same
order; the functions look like the engine's own. Off changes nothing in a
page, as always.

SIMULATION: a local page (localhost: a secure context and a name passkeys accept).
"""

import http.server
import json
import threading

import pytest

PAGE = rb"""<!doctype html><title>pk</title><body><script>
function race(p) {
  return Promise.race([p.then(function (v) { return v; }, function (e) { return 'rejected ' + e.name; }),
    new Promise(function (ok) { setTimeout(function () { ok('pending'); }, 3000); })]);
}
(async function () {
  var P = PublicKeyCredential, out = {};
  out.uvpaa = await race(P.isUserVerifyingPlatformAuthenticatorAvailable());
  out.cond = await race(P.isConditionalMediationAvailable());
  var caps = await race(P.getClientCapabilities());
  out.caps = caps && typeof caps === 'object' ? Object.entries(caps) : caps;
  out.capsProto = caps && typeof caps === 'object' ? Object.getPrototypeOf(caps) === Object.prototype : null;
  out.texts = ['isUserVerifyingPlatformAuthenticatorAvailable', 'isConditionalMediationAvailable',
    'getClientCapabilities'].map(function (n) { return Function.prototype.toString.call(P[n]) + '|' + P[n].length + '|' + P[n].name; });
  out.promise = P.isConditionalMediationAvailable() instanceof Promise;
  // the answer comes in a task of its own, as the engine's does: not after a
  // few turns of the same task's microtasks
  var early = false;
  P.isConditionalMediationAvailable().then(function () { early = true; });
  for (var i = 0; i < 5; i++) await Promise.resolve();
  out.early = early;
  // Function.prototype.toString as a clean frame of the page reads it
  var f = document.createElement('iframe');
  document.body.appendChild(f);
  out.toStringText = f.contentWindow.Function.prototype.toString.call(Function.prototype.toString);
  // a conditional request waits without a word; aborted, a request for a
  // security key then reaches I.K.E.'s own window (webAuthUxRequested)
  var ac = new AbortController();
  out.conditional = 'pending';
  navigator.credentials.get({ mediation: 'conditional', signal: ac.signal,
    publicKey: { challenge: new Uint8Array(32) } }).then(function () { out.conditional = 'resolved'; },
    function (e) { out.conditional = 'rejected ' + e.name; });
  await new Promise(function (ok) { setTimeout(ok, 1500); });
  out.conditionalBefore = out.conditional;
  window.uxBefore = true;
  ac.abort();
  await new Promise(function (ok) { setTimeout(ok, 300); });
  navigator.credentials.get({ publicKey: { challenge: new Uint8Array(32), timeout: 60000 } }).catch(function () {});
  await new Promise(function (ok) { setTimeout(ok, 1500); });
  window.result = JSON.stringify(out);
})();
</script></body>"""

# Chrome for Testing 140.0.7339.207 on Linux (headless, no Bluetooth adapter)
CHROMIUM_140 = [["conditionalCreate", True], ["conditionalGet", True], ["extension:appid", True],
                ["extension:appidExclude", True], ["extension:credBlob", True], ["extension:credProps", True],
                ["extension:credentialProtectionPolicy", True], ["extension:enforceCredentialProtectionPolicy", True],
                ["extension:getCredBlob", True], ["extension:hmacCreateSecret", True], ["extension:largeBlob", True],
                ["extension:minPinLength", True], ["extension:payment", False], ["extension:prf", True],
                ["hybridTransport", False], ["passkeyPlatformAuthenticator", False], ["relatedOrigins", True],
                ["signalAllAcceptedCredentials", True], ["signalCurrentUserDetails", True],
                ["signalUnknownCredential", True], ["userVerifyingPlatformAuthenticator", False]]


@pytest.fixture
def site():
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(PAGE)))
            self.end_headers()
            self.wfile.write(PAGE)

        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1]
    srv.shutdown()


STEPS = r'''
from PyQt6.QtCore import QUrl

def steps(ike, qapp, out):
    view = ike.windows[0].current_view()
    ux = out.setdefault("ux", [])
    view.page().webAuthUxRequested.connect(lambda req, ux=ux: ux.append(str(req.state())))
    done = {}
    view.page().loadFinished.connect(lambda ok, d=done: d.setdefault("ok", ok))
    view.load(QUrl("http://localhost:%d/"))
    while "ok" not in done:
        yield 20
    for _ in range(200):
        res = {}
        view.page().runJavaScript("window.result || ''", 0, lambda r, res=res: res.setdefault("r", r))
        while "r" not in res:
            yield 20
        if res["r"]:
            out["r"] = res["r"]
            return
        yield 100
'''


@pytest.mark.parametrize("level", ["compatibility", "balanced", "strict", "maximum"])
def test_passkey_questions_are_answered_as_chromium_140(run_ike, site, level):
    out = run_ike(STEPS % site, settings={"shield_level": level}, timeout=120)
    r = json.loads(out["r"])
    assert r["uvpaa"] is False and r["cond"] is True, (level, r)
    assert r["early"] is False, (level, r)
    # a conditional request waits and shows nothing; the security key's
    # request after it reaches I.K.E.'s window
    assert r["conditionalBefore"] == "pending", (level, r)
    assert len(out["ux"]) == 1, (level, out["ux"])
    assert r["caps"] == CHROMIUM_140 and r["capsProto"] is True, (level, r)
    assert r["promise"] is True, r
    for text, name in zip(r["texts"], ["isUserVerifyingPlatformAuthenticatorAvailable",
                                       "isConditionalMediationAvailable", "getClientCapabilities"]):
        if level == "compatibility":
            # proxies of the engine's own functions: Function.prototype.toString
            # stays the engine's at Compatibility (the review: a replaced one
            # was a tell on the sign-in pages kept at Compatibility)
            assert text == "function () { [native code] }|0|%s" % name, (level, text)
        else:
            assert text == "function %s() { [native code] }|0|%s" % (name, name), (level, text)
    assert r["toStringText"] == "function toString() { [native code] }", (level, r["toStringText"])


def test_off_changes_nothing(run_ike, site):
    """With the shield off the page meets the engine as it is: no build of Qt
    WebEngine answers getClientCapabilities() (the reason for the answers
    above), and nothing of I.K.E.'s answers for it."""
    r = json.loads(run_ike(STEPS % site, settings={"shield_level": "off"}, timeout=120)["r"])
    assert r["caps"] == "pending", r


# Firefox 161 on Linux (measured; headless, no Bluetooth adapter)
FIREFOX_161 = [["conditionalCreate", False], ["conditionalGet", True], ["extension:appid", True],
               ["extension:credProps", True], ["extension:credentialProtectionPolicy", True],
               ["extension:enforceCredentialProtectionPolicy", True], ["extension:hmacCreateSecret", True],
               ["extension:largeBlob", False], ["extension:minPinLength", True], ["extension:prf", True],
               ["hybridTransport", False], ["passkeyPlatformAuthenticator", False], ["relatedOrigins", True],
               ["signalAllAcceptedCredentials", False], ["signalCurrentUserDetails", False],
               ["signalUnknownCredential", False], ["userVerifyingPlatformAuthenticator", False]]


@pytest.fixture
def google(tmp_path_factory):
    """www.google.com mapped to a local https server (as tests/test_google_firefox.py)."""
    import ssl

    from test_google_firefox import _certificate

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(PAGE)))
            self.end_headers()
            self.wfile.write(PAGE)

        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(*(str(f) for f in _certificate(tmp_path_factory.mktemp("cert"))))
    srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1]
    srv.shutdown()


@pytest.mark.parametrize("level", ["compatibility", "balanced"])
def test_on_googles_sites_the_answers_are_firefoxs(run_ike, google, level):
    from test_google_firefox import NO_PROXY_ENV
    env = dict(NO_PROXY_ENV, QTWEBENGINE_CHROMIUM_FLAGS='--no-sandbox "--host-resolver-rules=MAP www.google.com '
               '127.0.0.1:%d" --ignore-certificate-errors' % google)
    steps = STEPS.replace('"http://localhost:%d/"', '"https://www.google.com:%d/"') % google
    out = run_ike(steps, settings={"shield_level": level, "login_compat": True}, env=env, timeout=120)
    r = json.loads(out["r"])
    assert r["uvpaa"] is False and r["cond"] is True, (level, r)
    assert r["caps"] == FIREFOX_161 and r["capsProto"] is True, (level, r)
    assert all(t.endswith("{ [native code] }|0|" + t.split("|")[-1]) for t in r["texts"]), r
