"""1.1.30: the engine privacy layer (Engine Privacy Layer study, 2026-11-27,
docs/review/engine-privacy-study.md).

- Attribution Reporting and Topics off in the engine: Qt WebEngine kept an
  advertiser's attribution source in the profile (Chromium 140 keeps none)
  and sent the Topics header.
- --lang at every level, from the first language sites are told: workers,
  Intl and the engine's own texts agree with the page.
- Accept-Language as Chrome writes it (q-values); "Common English language"
  in the Octagon tells sites en-US at every level.
- Balanced and above: window.chrome as Chromium 140 has it, Chromium's
  answers to permissions.query, the common network in pages and headers.
"""

import http.server
import json
import sys
import threading

import pytest
from conftest import APP

sys.path.insert(0, str(APP))
from ike import app as ike_app  # noqa: E402
from ike import config as ike_config  # noqa: E402


@pytest.mark.parametrize("given, chrome", [
    ("de-DE,de,en-US,en", "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7"),
    ("en-US,en", "en-US,en;q=0.9"),
    ("it-IT,it;q=0.5,en", "it-IT,it;q=0.9,en;q=0.8"),     # the user's weights: Chrome's
    ("fr", "fr"),
    ("", "en-US,en;q=0.9"),
    ("x y,pt-BR", "pt-BR"),                              # a word that is no language is left out
])
def test_accept_language_as_chrome_writes_it(given, chrome):
    assert ike_config.chrome_accept_language(given) == chrome


def test_eleven_languages_and_more_end_at_q_one_tenth():
    out = ike_config.chrome_accept_language(",".join("l%s" % c for c in "abcdefghijkl"))
    assert out.endswith("lj;q=0.1,lk;q=0.1,ll;q=0.1"), out


def _cfg(tmp_path, **values):
    c = ike_config.Config(tmp_path / "settings.json")
    for k, v in values.items():
        c[k] = v
    return c


@pytest.mark.parametrize("level, common, want", [
    ("balanced", False, "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7"),
    ("compatibility", False, "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7"),
    ("strict", False, "de-DE,de;q=0.9"),
    ("maximum", False, "en-US,en;q=0.9"),
    ("balanced", True, "en-US,en;q=0.9"),
    ("strict", True, "en-US,en;q=0.9"),
])
def test_the_language_the_engine_is_given(tmp_path, level, common, want):
    cfg = _cfg(tmp_path, shield_level=level, common_english=common, accept_language="de-DE,de,en-US,en")
    assert ike_config.engine_language(cfg) == want
    assert ike_app.engine_lang_switch(want) == want.split(",")[0]


def test_common_english_is_off_at_first(tmp_path):
    assert ike_config.Config(tmp_path / "settings.json")["common_english"] is False


def _flags(monkeypatch, tmp_path, inherited="", **values):
    monkeypatch.setattr(ike_app, "CONFIG_DIR", tmp_path)
    monkeypatch.setenv("QTWEBENGINE_CHROMIUM_FLAGS", inherited)
    monkeypatch.setenv("IKE_ALLOW_UNSAFE_ENGINE", "1")
    ike_app._chromium_flags(_cfg(tmp_path, **values))
    return ike_app.split_flags(__import__("os").environ["QTWEBENGINE_CHROMIUM_FLAGS"])


@pytest.mark.parametrize("level", ["compatibility", "balanced", "strict", "maximum"])
def test_every_level_gets_its_language_and_no_advertising_measurement(monkeypatch, tmp_path, level):
    flags = _flags(monkeypatch, tmp_path, shield_level=level, accept_language="it-IT,it,en-US,en")
    lang = [f for f in flags if f.startswith("--lang=")]
    assert lang == ["--lang=" + ("en-US" if level == "maximum" else "it-IT")], flags
    off = [f for f in flags if f.startswith("--disable-features=")]
    assert len(off) == 1, flags                                   # the engine reads one only
    assert {"ConversionMeasurement", "BrowsingTopics"} <= set(off[0].split("=", 1)[1].split(",")), off
    blink = [f for f in flags if f.startswith("--disable-blink-features=")]
    assert len(blink) == 1 and {"AttributionReporting", "TopicsAPI"} <= set(blink[0].split("=", 1)[1].split(",")), flags


def test_http3_and_partitioned_connections(monkeypatch, tmp_path):
    flags = _flags(monkeypatch, tmp_path, shield_level="balanced")
    assert "--enable-quic" in flags, flags
    on = [f for f in flags if f.startswith("--enable-features=")]
    assert len(on) == 1 and "PartitionConnectionsByNetworkIsolationKey" in on[0].split("=", 1)[1].split(","), flags
    # the user's own --disable-quic is kept, and nothing turns it back on
    flags = _flags(monkeypatch, tmp_path, inherited="--disable-quic", shield_level="balanced")
    assert "--disable-quic" in flags and "--enable-quic" not in flags, flags


def test_inherited_switches_are_merged_and_an_explicit_choice_wins(monkeypatch, tmp_path):
    flags = _flags(monkeypatch, tmp_path, inherited="--disable-blink-features=Foo --lang=fr --enable-features=BrowsingTopics",
                   shield_level="balanced")
    assert [f for f in flags if f.startswith("--lang")] == ["--lang=fr"]                 # the user's own
    blink = [f for f in flags if f.startswith("--disable-blink-features=")]
    assert len(blink) == 1 and blink[0].split("=", 1)[1].split(",")[0] == "Foo", blink
    off = [f for f in flags if f.startswith("--disable-features=")]
    assert "BrowsingTopics" not in ",".join(off) and "ConversionMeasurement" in ",".join(off), flags


SHAPE = r'''
import json
from PyQt6.QtCore import QUrl

PROBE = """(async () => {
  const c = window.chrome, d = Object.getOwnPropertyDescriptor(window, 'chrome'), ts = Function.prototype.toString;
  const r = {configurable: d.configurable, keys: Reflect.ownKeys(c).map(String)};
  if (c.app) {
    r.app = Reflect.ownKeys(c.app).map(String);
    r.texts = [ts.call(c.loadTimes), ts.call(c.csi), ts.call(c.app.getDetails), ts.call(c.app.installState)];
    r.names = [c.loadTimes.name, c.app.getDetails.name, 'prototype' in c.loadTimes, 'prototype' in c.app.getDetails];
    r.values = [c.app.isInstalled, c.app.getDetails(), c.app.getIsInstalled(), c.app.runningState(),
                c.app.InstallState.NOT_INSTALLED, c.app.RunningState.CANNOT_RUN];
    try { c.app.getDetails(1); r.err = 'none'; } catch (e) { r.err = e.constructor.name + ': ' + e.message; }
    r.install = await new Promise(ok => c.app.installState(ok));
    const lt = c.loadTimes(), csi = c.csi();
    r.lt = Object.keys(lt); r.ltStart = lt.requestTime > 1e9 && lt.requestTime < 1e10; r.conn = lt.connectionInfo;
    r.csi = Object.keys(csi); r.tran = csi.tran;
    r.proto = Object.getPrototypeOf(c.app.getDetails) === Function.prototype;
  }
  r.perm = await Promise.all(['midi', 'accelerometer', 'clipboard-write', 'notifications'].map(n =>
    navigator.permissions.query({name: n}).then(s => s.state)));
  r.net = navigator.connection ? [navigator.connection.rtt, navigator.connection.downlink] : null;
  r.ads = ['attributionSrc' in HTMLImageElement.prototype, typeof document.browsingTopics];
  r.lang = [navigator.language, Intl.DateTimeFormat().resolvedOptions().locale];
  window.result = JSON.stringify(r);
})()"""

def steps(ike, qapp, out):
    view = ike.windows[0].current_view()
    done = {}
    view.page().loadFinished.connect(lambda ok, d=done: d.setdefault("ok", ok))
    view.load(QUrl("http://127.0.0.1:%d/page"))
    while "ok" not in done:
        yield 20
    view.page().runJavaScript(PROBE, 0)
    for _ in range(200):
        res = {}
        view.page().runJavaScript("window.result || ''", 0, lambda r, res=res: res.__setitem__("r", r))
        while "r" not in res:
            yield 20
        if res["r"]:
            out["r"] = res["r"]
            return
        yield 50
'''


@pytest.fixture
def page_site():
    seen = []

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append(dict((k.lower(), v) for k, v in self.headers.items()))
            body = b"<!doctype html><title>t</title><p>page"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1], seen
    srv.shutdown()


@pytest.mark.parametrize("level", ["balanced", "strict"])
def test_window_chrome_permissions_and_network_as_chromium(run_ike, page_site, level):
    port, seen = page_site
    out = run_ike(SHAPE % port, settings={"shield_level": level, "accept_language": "en-US,en"}, timeout=120)
    r = json.loads(out["r"])
    # the shape measured on Chromium 140 (the study's probe page, not kept)
    assert r["configurable"] is False and r["keys"] == ["loadTimes", "csi", "app"], r
    assert r["app"] == ["isInstalled", "getDetails", "getIsInstalled", "installState", "runningState",
                        "InstallState", "RunningState"], r
    assert r["texts"] == ["function () { [native code] }", "function () { [native code] }",
                          "function getDetails() { [native code] }", "function installState() { [native code] }"], r
    assert r["names"] == ["", "getDetails", True, False], r
    assert r["values"] == [False, None, False, "cannot_run", "not_installed", "cannot_run"], r
    assert r["err"] == "TypeError: Error in invocation of app.getDetails(): ", r
    assert r["install"] == "not_installed" and r["proto"] is True, r
    assert r["lt"][:3] == ["requestTime", "startLoadTime", "commitLoadTime"] and len(r["lt"]) == 13 and r["ltStart"], r
    assert r["csi"] == ["startE", "onloadT", "pageT", "tran"] and r["tran"] == 15, r
    # Chromium's answers where Qt said "denied"; a real one unchanged
    assert r["perm"][:3] == ["prompt", "granted", "granted"], r
    assert r["net"] == [50, 10], r
    assert r["ads"] == [False, "undefined"], r
    assert r["lang"] == ["en-US", "en-US"], r
    # the language header as Chrome writes it, and no advertising headers
    page = [h for h in seen if "accept-language" in h][0]
    assert page["accept-language"] == "en-US,en;q=0.9", page
    assert not any("attribution-reporting-eligible" in h or "sec-browsing-topics" in h for h in seen), seen


def test_compatibility_leaves_window_chrome_as_the_engine_has_it(run_ike, page_site):
    port, _seen = page_site
    out = run_ike(SHAPE % port, settings={"shield_level": "compatibility"}, timeout=120)
    r = json.loads(out["r"])
    assert r["keys"] == [] and "app" not in r, r
