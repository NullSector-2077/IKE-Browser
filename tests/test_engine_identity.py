"""The weekly check of the engine's identity (1.1.29: engine-identity.yml,
tools/engine-probe/identity_guard.py): what it reads, what it tells the
owner in the signing notice, and that a finding never fails the run."""

import copy
import json
import subprocess
import sys

from conftest import APP

GUARD = APP / "tools" / "engine-probe" / "identity_guard.py"
BASELINE = APP / "tools" / "engine-probe" / "baseline.json"


def realm(ua="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
          lang="en-US"):
    return {"nav": {"userAgent": ua, "platform": "Linux x86_64", "language": lang,
                    "uaHigh": {"fullVersionList": [{"brand": "Chromium", "version": "140.0.7339.264"}],
                               "platformVersion": ""},
                    "connection": {"rtt": 50, "downlink": 10}},
            "intl": {"resolved": {"locale": lang}},
            "perms": {"midi": "prompt", "accelerometer": "granted", "clipboard-write": "granted"},
            "surface": {"globals": {"Document": {"p": ["title"]}, "HTMLImageElement": {"p": ["src"]},
                                    "PaymentRequest": {"p": []}}}}


def result(chrome_keys=("loadTimes", "csi", "app")):
    page = realm()
    return {"result": {"page": page, "iframe": realm(), "dedicated": realm(), "shared": realm(), "service": realm(),
                       "chrome": {"keys": list(chrome_keys)}},
            "tls": [{"hello": {"ja4": "t13d1516h2_8daaf6152771_d8a2da3f94cd"}}]}


def run(tmp_path, ike=None, strict=None, ref=None, extra=None):
    ref = ref or result()
    ike = ike or copy.deepcopy(ref)
    for g in ("PaymentRequest",):                 # the engine's known gap (baseline.json)
        ike["result"]["page"]["surface"]["globals"].pop(g, None)
    files = {"chromium": ref, "ike-balanced": ike, "ike-strict": strict or copy.deepcopy(ike),
             "ike-balanced-extra": extra or {"conversions_sources": None}}
    for name, data in files.items():
        (tmp_path / (name + ".json")).write_text(json.dumps(data))
    proc = subprocess.run([sys.executable, str(GUARD), str(tmp_path), str(BASELINE), str(tmp_path / "n.md"),
                           str(tmp_path / "r.json"), "https://github.com/run/1"], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr                    # a finding never fails the run
    return (tmp_path / "n.md").read_text(), json.loads((tmp_path / "r.json").read_text())


def test_all_as_expected(tmp_path):
    notice, res = run(tmp_path)
    assert res["ok"] is True and notice.startswith("**Identità del motore**"), notice
    assert "Tutto come previsto" in notice and "https://github.com/run/1" in notice


def test_each_finding_is_named(tmp_path):
    ike = result(chrome_keys=())
    ike["result"]["page"]["perms"]["midi"] = "denied"
    ike["result"]["page"]["nav"]["connection"] = {"rtt": 0, "downlink": 9.5}
    ike["result"]["page"]["surface"]["globals"]["HTMLImageElement"]["p"].append("attributionSrc")
    ike["result"]["shared"]["nav"]["language"] = "en"
    ike["tls"][0]["hello"]["ja4"] = "t13d1517h2_other"
    ike["result"]["page"]["surface"]["globals"].pop("Document")          # a new gap
    notice, res = run(tmp_path, ike=ike, extra={"conversions_sources": 3})
    assert res["ok"] is False
    for words in ("window.chrome diverso", "permessi diversi: midi", "rete comune no", "attributionSrc",
                  "identità diversa in shared (language)", "fonti pubblicitarie salvate nel profilo: 3",
                  "JA4", "**nuove**: Document"):
        assert words in notice, (words, notice)


def test_another_version_of_chromium_is_said_and_not_compared(tmp_path):
    ref = result()
    ref["result"]["page"]["nav"]["userAgent"] = ref["result"]["page"]["nav"]["userAgent"].replace("140.0", "158.0")
    ref["tls"][0]["hello"]["ja4"] = "t13d1517h2_newer"
    ike = result()
    notice, res = run(tmp_path, ike=ike, ref=ref)
    assert "un'altra versione (158, il motore 140)" in notice, notice
    assert "JA4" not in notice and "nuove" not in notice, notice


def test_a_known_gap_that_is_gone_is_told(tmp_path):
    ref = result()
    ref["result"]["page"]["surface"]["globals"].pop("PaymentRequest")       # the engine caught up
    notice, res = run(tmp_path, ref=ref)
    assert "PaymentRequest" in res["gone"] and "elenco di riferimento" in notice, notice


def test_the_workflow_and_the_notice():
    wf = (APP / ".github" / "workflows" / "engine-identity.yml").read_text()
    assert "schedule:" in wf and "workflow_dispatch:" in wf
    assert "qWebEngineChromiumVersion" in wf and "archive.archlinux.org/packages/c/chromium/" in wf
    for target in ("ike:balanced", "ike:strict", "@chromium", "@ike-balanced-extra", "@chromium-extra"):
        assert target in wf, target
    assert "identity_guard.py" in wf and "name: engine-identity" in wf
    perms = wf.split("permissions:", 1)[1].split("concurrency:", 1)[0]
    assert perms.split() == ["contents:", "read"], perms                          # it changes nothing
    notice = (APP / ".github" / "workflows" / "release-ready.yml").read_text()
    assert "--workflow engine-identity.yml" in notice and "-n engine-identity" in notice
    baseline = json.loads(BASELINE.read_text())
    assert len(baseline["gaps"]) >= 30 and "PaymentRequest" in baseline["gaps"]
