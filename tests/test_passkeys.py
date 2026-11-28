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

SIMULATION: a local page (127.0.0.1 is a secure context).
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
    done = {}
    view.page().loadFinished.connect(lambda ok, d=done: d.setdefault("ok", ok))
    view.load(QUrl("http://127.0.0.1:%d/"))
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
    r = json.loads(run_ike(STEPS % site, settings={"shield_level": level}, timeout=120)["r"])
    assert r["uvpaa"] is False and r["cond"] is True, (level, r)
    assert r["caps"] == CHROMIUM_140 and r["capsProto"] is True, (level, r)
    assert r["promise"] is True, r
    for text, name in zip(r["texts"], ["isUserVerifyingPlatformAuthenticatorAvailable",
                                       "isConditionalMediationAvailable", "getClientCapabilities"]):
        assert text == "function %s() { [native code] }|0|%s" % (name, name), (level, text)


def test_off_changes_nothing(run_ike, site):
    """With the shield off the page meets the engine as it is: no build of Qt
    WebEngine answers getClientCapabilities() (the reason for the answers
    above), and nothing of I.K.E.'s answers for it."""
    r = json.loads(run_ike(STEPS % site, settings={"shield_level": "off"}, timeout=120)["r"])
    assert r["caps"] == "pending", r
