"""1.1.15: "same site, free way" and the speech voices.

At Balanced and below what a site asks of itself is not checked against the
filter lists (as Brave's standard mode): faster pages, fewer broken sites. The
requests of other companies stay blocked; Strict and Maximum check
everything; the video sites (their ads come from the site itself) are always
checked. The fingerprinting protection hides the speech voices of other
languages, without a trace in the function.
"""

from conftest import needs_engine

STEPS = r"""
from PyQt6.QtCore import QUrl
from PyQt6.QtWebEngineCore import QWebEngineUrlRequestInfo as I

RT = I.ResourceType

class Info:
    def __init__(self, url, first, rtype=RT.ResourceTypeImage):
        self.u, self.f, self.t = QUrl(url), QUrl(first), rtype
        self.blocked, self.headers = False, {}
    def requestUrl(self): return self.u
    def firstPartyUrl(self): return self.f
    def initiator(self): return self.f
    def resourceType(self): return self.t
    def requestMethod(self): return b"GET"
    def block(self, b): self.blocked = bool(b)
    def redirect(self, u): pass
    def setHttpHeader(self, k, v): self.headers[bytes(k).decode()] = bytes(v).decode()

CASES = {
    "own_ad": ("https://cdn.news.example/ads/banner-ad.png", "https://www.news.example/article"),
    "other_ad": ("https://ads.example.test/a.png", "https://www.news.example/article"),
    "youtube_own": ("https://www.youtube.com/api/stats/ads?x=1", "https://www.youtube.com/watch?v=a"),
}

def steps(ike, qapp, out):
    b = ike.blocker
    for _ in range(300):
        if b.engine is not None and b.should_block(
                "https://ads.example.test/a.png", "https://site.test/", "image"):
            break
        yield 100
    icp = ike.shields.interceptor
    for name, (url, first) in CASES.items():
        info = Info(url, first)
        icp.interceptRequest(info)
        out[name] = info.blocked
    out["own_gpc"] = None
    info = Info(*CASES["own_ad"])
    icp.interceptRequest(info)
    out["own_gpc"] = info.headers.get("Sec-GPC")
"""


@needs_engine
def test_balanced_lets_a_sites_own_requests_through(run_ike):
    out = run_ike(STEPS, settings={"shield_level": "balanced", "send_gpc": True,
                                   "custom_filters": "/banner-ad.$image\n"})
    assert out["own_ad"] is False, out              # the site's own: free way
    assert out["other_ad"] is True, out             # another company: blocked
    assert out["youtube_own"] is True, out          # video sites: always checked
    assert out["own_gpc"] == "1", out               # the privacy signal still goes


@needs_engine
def test_strict_checks_everything(run_ike):
    out = run_ike(STEPS, settings={"shield_level": "strict", "custom_filters": "/banner-ad.$image\n"})
    assert out["own_ad"] is True and out["other_ad"] is True and out["youtube_own"] is True, out


VOICES = r"""
from PyQt6.QtCore import QUrl

def steps(ike, qapp, out):
    v = ike.windows[0].current_view()
    done = {}
    v.page().loadFinished.connect(lambda ok: done.setdefault("ok", ok))
    v.setHtml("<!doctype html><title>v</title>", QUrl("https://voices.example/"))
    while "ok" not in done:
        yield 20
    yield 200
    res = {}
    v.page().runJavaScript(
        "(function(){if(typeof speechSynthesis==='undefined')return JSON.stringify({missing:true});"
        "var f=document.createElement('iframe');document.body.appendChild(f);"
        "var ts=f.contentWindow.Function.prototype.toString;"
        "return JSON.stringify({native: ts.call(speechSynthesis.getVoices),"
        " array: Array.isArray(speechSynthesis.getVoices())});})()",
        lambda x: res.setdefault("r", x))
    while "r" not in res:
        yield 20
    out["r"] = res["r"]
"""


def test_speech_voices_wrapped_without_a_trace(run_ike):
    import json

    import pytest
    out = json.loads(run_ike(VOICES, settings={"shield_level": "balanced"})["r"])
    if out.get("missing"):
        pytest.skip("this build of the engine has no speech synthesis")
    assert out["array"] is True
    assert out["native"] == "function getVoices() { [native code] }", out
