"""Nothing gets worse (tools/no-regression.py): the comparison, and that it really sees a weakening.

The comparator is checked on hand-made snapshots: each kind of regression
(a request blocked on main and allowed here, an element hidden on main and
shown here, a fingerprinting value changed, a new host contacted, a weaker
engine switch or setting) fails; the same snapshot, or a stricter one, passes;
a change a person accepted in the allowlist passes, that change only. Then the
real check runs on this repository and on a copy weakened as an AI fix could
weaken it (the AdBlock path letting one rule through, fingerprint.js with its
canvas noise off, site isolation dropped, a new host contacted at start): it
must catch every one of them.
"""

import copy
import importlib.util
import json
import os
import re
import shutil
import sys
from pathlib import Path

import pytest
from conftest import needs_engine

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "tests" / "data" / "no-regression"


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_") + "_nr", ROOT / "tools" / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


nr = load("no-regression")
tc = load("test-categories")


def snap(**obs):
    """A snapshot with these observations: {key: (rule, value)}."""
    return {"format": nr.FORMAT, "errors": [], "repo": {"commit": "a" * 40, "version": "1.1.22"},
            "corpus": {"requests": 1, "elements": 1}, "seconds": 1,
            "observations": {k.replace("__", "/"): {"rule": r, "value": v} for k, (r, v) in obs.items()}}


BASE = {
    "requests__balanced__ad-gpt": ("block", "block"),
    "requests__balanced__yt-stats-ads": ("block", "block"),
    "requests__strict__page-https-upgrade": ("block", "https-upgrade"),
    "requests__balanced__ok-news-image": ("block", "allow"),
    "cosmetic__balanced__news__ad-banner": ("hidden", "hidden"),
    "cosmetic__balanced__news__article": ("hidden", "shown"),
    "fingerprint__strict__navigator.hardwareConcurrency": ("exact", 4),
    "fingerprint__strict__canvas.noised": ("exact", True),
    "network__fresh-profile": ("no-new", ["easylist.to"]),
    "switches__added": ("switches", ["--enable-smooth-scrolling", "--site-per-process"]),
    "switches__hostile-kept": ("no-new", []),
    "webengine__balanced__page__JavascriptCanOpenWindows": ("setting", False),
    "webengine__balanced__page__AutoLoadImages": ("setting", True),
    "webengine__balanced__page__DnsPrefetchEnabled": ("setting", True),
    "scriptlets__www.youtube.com": ("kept", ['["json-prune.js", "playerResponse.adPlacements"]']),
    "lists__app.UNSAFE_SWITCHES": ("kept", ["--disable-web-security", "--no-sandbox"]),
    "lists__config.SENSITIVE_HOSTS": ("no-new", ["paypal.com"]),
    "permissions__balanced__geolocation": ("permission", "prompt"),
    "defaults__https_only": ("safer-true", True),
    "defaults__shield_level": ("level", "balanced"),
    "headers__strict__third-party__referer": ("exact", "http://127.0.0.1:PORT/"),
}

# each regression kind, as a candidate would show it
WORSE = {
    "requests__balanced__ad-gpt": "allow",                                     # blocked -> allowed
    "requests__balanced__yt-stats-ads": "allow",                               # YouTube's ad request let through
    "requests__strict__page-https-upgrade": "allow",                           # automatic HTTPS lost
    "cosmetic__balanced__news__ad-banner": "shown",                            # hidden -> shown
    "fingerprint__strict__navigator.hardwareConcurrency": 8,                   # a value that reveals more
    "fingerprint__strict__canvas.noised": False,                               # the canvas noise off
    "network__fresh-profile": ["easylist.to", "telemetry.example"],            # a new host
    "switches__added": ["--enable-smooth-scrolling"],                          # site isolation dropped
    "switches__hostile-kept": ["--no-sandbox"],                                # a hostile switch kept
    "webengine__balanced__page__JavascriptCanOpenWindows": True,               # a weaker setting
    "webengine__balanced__page__AutoLoadImages": False,                        # an unknown setting changed
    "scriptlets__www.youtube.com": [],                                         # a scriptlet lost
    "lists__app.UNSAFE_SWITCHES": ["--no-sandbox"],                            # an unsafe switch no longer dropped
    "lists__config.SENSITIVE_HOSTS": ["evil.example", "paypal.com"],           # a new hands-off site
    "permissions__balanced__geolocation": "granted",                           # a permission given by itself
    "defaults__https_only": False,                                             # a protective default off
    "defaults__shield_level": "compatibility",                                 # a lower default level
    "headers__strict__third-party__referer": "http://127.0.0.1:PORT/fp?lv=strict",   # the Referer no longer cut
}

STRICTER = {
    "requests__balanced__ok-news-image": "block",
    "cosmetic__balanced__news__article": "hidden",
    "network__fresh-profile": [],
    "webengine__balanced__page__DnsPrefetchEnabled": False,
    "scriptlets__www.youtube.com": ['["json-prune.js", "playerResponse.adPlacements"]', '["set-constant.js", "x"]'],
    "lists__app.UNSAFE_SWITCHES": ["--disable-web-security", "--no-sandbox", "--single-process"],
    "lists__config.SENSITIVE_HOSTS": [],
    "permissions__balanced__geolocation": "denied",
    "defaults__shield_level": "strict",
}


def with_values(base, values):
    out = copy.deepcopy(base)
    for k, v in values.items():
        out["observations"][k.replace("__", "/")]["value"] = v
    return out


def keys(rows):
    return {r["key"] for r in rows}


def test_identical_snapshots_pass():
    base = snap(**BASE)
    report = nr.compare(base, copy.deepcopy(base))
    assert report["verdict"] == "pass"
    assert not report["worse"] and not report["stricter"] and not report["changed"]


def test_every_kind_of_regression_fails():
    base = snap(**BASE)
    for key, value in WORSE.items():
        report = nr.compare(base, with_values(base, {key: value}))
        assert report["verdict"] == "fail", key
        assert keys(report["worse"]) == {key.replace("__", "/")}, (key, report["worse"])
    report = nr.compare(base, with_values(base, WORSE))
    assert keys(report["worse"]) == {k.replace("__", "/") for k in WORSE}


def test_stricter_passes_and_is_reported():
    base = snap(**BASE)
    report = nr.compare(base, with_values(base, STRICTER))
    assert report["verdict"] == "pass", report["worse"]
    assert keys(report["stricter"]) == {k.replace("__", "/") for k in STRICTER}
    # stopped either way: a block that became a harmless redirect is not worse
    report = nr.compare(base, with_values(base, {"requests__balanced__ad-gpt": "redirect-data"}))
    assert report["verdict"] == "pass" and keys(report["changed"]) == {"requests/balanced/ad-gpt"}
    # an added switch that does not read as weaker is only reported; one that does is worse
    report = nr.compare(base, with_values(base, {"switches__added": BASE["switches__added"][1] + ["--lang=en-US"]}))
    assert report["verdict"] == "pass" and keys(report["changed"]) == {"switches/added"}
    report = nr.compare(base, with_values(base, {"switches__added": BASE["switches__added"][1] +
                                                 ["--disable-web-security"]}))
    assert report["verdict"] == "fail"


def test_not_measured_is_never_passed():
    base = snap(**BASE)
    missing = copy.deepcopy(base)
    del missing["observations"]["requests/balanced/ad-gpt"]
    report = nr.compare(base, missing)
    assert report["verdict"] == "fail" and keys(report["worse"]) == {"requests/balanced/ad-gpt"}
    broken = copy.deepcopy(base)
    broken["errors"] = [{"section": "fingerprint", "error": "the probe page gave no result at strict"}]
    report = nr.compare(base, broken)
    assert report["verdict"] == "fail" and report["errors"] and not report["worse"]
    assert "could not be measured" in nr.markdown(report)
    report = nr.compare(dict(base, format=0), base)
    assert report["verdict"] == "fail"


def test_allowlist_accepts_exactly_what_a_person_read(tmp_path):
    base = snap(**BASE)
    cand = with_values(base, {"fingerprint__strict__navigator.hardwareConcurrency": 8,
                              "requests__balanced__ad-gpt": "allow"})
    entries = [{"key": "fingerprint/*/navigator.hardwareConcurrency", "base": 4, "candidate": 8,
                "why": "the new spoofed value of 1.1.23", "accepted": "owner, 2026-11-22"},
               {"key": "requests/*/yt-*", "why": "never used"}]
    report = nr.compare(base, cand, entries)
    assert keys(report["accepted"]) == {"fingerprint/strict/navigator.hardwareConcurrency"}
    assert keys(report["worse"]) == {"requests/balanced/ad-gpt"} and report["verdict"] == "fail"
    assert [e["key"] for e in report["unused_allowlist"]] == ["requests/*/yt-*"]
    # pinned to one value: another one is still worse
    other = with_values(base, {"fingerprint__strict__navigator.hardwareConcurrency": 16})
    assert nr.compare(base, other, entries)["verdict"] == "fail"
    # an entry without a reason is not an entry
    f = tmp_path / "allow.json"
    f.write_text(json.dumps({"entries": [{"key": "*"}, {"key": "x", "why": " "}]}), "utf-8")
    entries, note = nr.load_allowlist(f)
    assert entries == [] and "ignored" in note
    entries, note = nr.load_allowlist(tmp_path / "missing.json")
    assert entries == [] and "nothing is accepted" in note


def test_the_report_in_plain_words():
    base = snap(**BASE)
    report = nr.compare(base, with_values(base, WORSE))
    text = nr.markdown(report)
    assert text.startswith("### Nothing gets worse") and "**Failed**" in text
    assert "request `ad-gpt` at Balanced: block on main, allowed here" in text
    assert "element `ad-banner` of the page `news` at Balanced: hidden on main, shown here" in text
    assert "telemetry.example" in text
    assert "**Passed**" in nr.markdown(nr.compare(base, base))


def test_the_allowlist_and_the_corpus_are_protected_and_sound():
    """Only a person edits them: tests/data/ is refused to the automatic fix and, as a test file
    changed, keeps the automation's pull request for a person (tools/automerge.py)."""
    guard = load("check-autofix-patch")
    merge = load("automerge")
    for name in ("tests/data/no-regression/allowlist.json", "tests/data/no-regression/corpus.json",
                 "tests/data/no-regression/lists/easylist.txt"):
        assert (ROOT / name).is_file()
        assert guard.allowed_path(name, False) == "protected file", name
        assert merge.TEST_FILE.search(name), name
    assert nr.ALLOWLIST == FIX / "allowlist.json"
    allow = json.loads(nr.ALLOWLIST.read_text("utf-8"))
    assert isinstance(allow["entries"], list) and "Only a person edits this file" in allow["about"]
    corpus = nr.load_corpus()
    ids = [q["id"] for q in corpus["requests"]]
    assert len(ids) == len(set(ids)) and len(ids) >= 100
    assert sum(1 for q in corpus["requests"] if "youtube" in q["url"] or "youtube" in q["source"]) >= 20
    for path in corpus["lists"].values():
        assert Path(path).is_file(), path
    from ike.config import DEFAULT_LISTS
    assert set(corpus["lists"]) <= {e["url"] for e in DEFAULT_LISTS}


def test_the_check_is_a_required_category():
    assert tc.CATEGORIES["no-regression"][1] == ("tests.yml", "tests", "Nothing gets worse")
    for kind in ("integrated", "adblock-engine", "crate", "npm", "filter-list", "arch-package", "vendored"):
        assert "no-regression" in tc.required_for([kind]), kind
        assert "no-regression" in tc.merge_required([kind]), kind
    rows = tc.verify(["no-regression"], {"no-regression": ""})
    assert rows[0]["state"] == "not verified"


def test_the_step_of_tests_yml():
    text = (ROOT / ".github" / "workflows" / "tests.yml").read_text("utf-8")
    at = text.index("- name: Nothing gets worse\n")
    step = text[at:text.index("\n      - ", at + 10)]
    assert "if:" not in step.split("run: |")[0], "it runs on every commit"
    assert "tools/no-regression.py" in step and "git worktree add" in step
    assert '"$where/tools/no-regression.py"' in step, "main's copy of the tool measures both"
    assert "HEAD^1" in step and "refs/heads/main" in step, "on main: the commit before"
    assert "tests/data/no-regression/allowlist.json" in step
    assert text.index("- name: Nothing gets worse") < text.index("- name: What the tests verified")


# --- the real check: this repository against a weakened copy ---------------------------------------
WEAKENINGS = (
    # ike/blocker.py: one rule's requests let through (doubleclick.net)
    ("ike/blocker.py", '        method = (method or "GET").upper()\n',
     '        method = (method or "GET").upper()\n        if "doubleclick.net" in url:\n'
     '            return "allow", None\n'),
    # fingerprint.js: the noise of what canvases give back switched off
    ("ike/resources/fingerprint.js", "  function noiseImage(img) {\n", "  function noiseImage(img) { return;\n"),
    # ike/app.py: site isolation no longer asked for
    ("ike/app.py", '        flags.append("--site-per-process")\n', "        pass\n"),
    # ike/app.py: a new host contacted at start, by I.K.E.'s own code
    ("ike/app.py", "    def start(self, urls=None, private=False):\n",
     "    def start(self, urls=None, private=False):\n        import threading\n        import urllib.request\n"
     "        threading.Thread(target=lambda: _nr_try(urllib.request.urlopen, 'https://telemetry.example/p'),"
     " daemon=True).start()\n"),
    ("ike/app.py", "\ndef memory_low(", "\ndef _nr_try(f, *a):\n    try:\n        f(*a, timeout=5)\n"
     "    except Exception:\n        pass\n\n\ndef memory_low("),
)


def weakened_copy(dest):
    for part in ("ike", "vendor", "data"):
        shutil.copytree(ROOT / part, dest / part, symlinks=True,
                        ignore=shutil.ignore_patterns("__pycache__", "_engine"))
    shutil.copy2(ROOT / "ike_boot.py", dest / "ike_boot.py")
    for rel, old, new in WEAKENINGS:
        f = dest / rel
        text = f.read_text("utf-8")
        assert text.count(old) == 1, (rel, old)
        f.write_text(text.replace(old, new), "utf-8")


@needs_engine
def test_the_check_catches_a_realistic_weakening(tmp_path):
    if os.environ.get("IKE_TEST_APP"):
        pytest.skip("the sources are checked once, not for the installed copy")
    weak = tmp_path / "weak"
    weakened_copy(weak)
    how = {"levels": ["balanced", "strict"], "sections": ["requests", "fingerprint", "security", "network"]}
    base = nr.snapshot(ROOT, **how)
    cand = nr.snapshot(weak, **how)
    assert not base["errors"] and not cand["errors"], (base["errors"], cand["errors"])
    report = nr.compare(base, cand)
    worse = keys(report["worse"])
    assert report["verdict"] == "fail"
    # the blocker: every doubleclick.net request of the corpus, YouTube's too, and nothing else
    let_through = {k for k in worse if k.startswith("requests/")}
    assert {"requests/balanced/ad-gpt", "requests/balanced/yt-googleads", "requests/strict/yt-instream",
            "requests/balanced/tr-dc-stats", "requests/balanced/pay-shop-ad"} <= let_through, let_through
    assert all("doubleclick.net" in next(q["url"] for q in nr.load_corpus()["requests"]
                                         if q["id"] == k.rsplit("/", 1)[1]) for k in let_through)
    # fingerprint.js: what a page reads of a canvas changed (at both levels)
    assert {"fingerprint/balanced/canvas", "fingerprint/strict/canvas"} <= worse, sorted(worse)
    # the engine switches: site isolation lost
    assert "switches/added" in worse
    assert any("--site-per-process" in r["detail"] for r in report["worse"] if r["key"] == "switches/added")
    # the network: the new host, seen by the audit hook and refused (nothing left the computer)
    row = next(r for r in report["worse"] if r["key"] == "network/fresh-profile")
    assert "telemetry.example" in row["detail"]
    assert "telemetry.example" not in base["observations"]["network/fresh-profile"]["value"]
    # and the same commit measured again: nothing worse (deterministic)
    again = nr.snapshot(ROOT, levels=["balanced"], sections=["requests", "fingerprint"])
    same = nr.compare(base, again)
    assert not [r for r in same["worse"] if r["key"].startswith(("requests/balanced/", "fingerprint/balanced/"))], \
        same["worse"]
    assert re.search(r"\*\*Failed\*\*: \d+ things worse than on main", nr.markdown(report))


def test_the_run_waits_for_the_font_check_before_measuring():
    """2026-11-24: Strict and Maximum mask every listed font until ike/fontcheck.py has asked the
    engine (about 15 s after the start), then only the fonts found here. A level measured before
    the answer and the same level measured after it differed, and "Nothing gets worse" called
    fingerprint-config/maximum/fonts worse on pull requests that changed nothing there. The run
    now asks at once and measures only once the answer is known (or after 60 s)."""
    src = nr.HOOK[nr.HOOK.index("def _start():"):nr.HOOK.index("QTimer.singleShot(300, _start)")]
    calls = []

    class Timer:
        @staticmethod
        def singleShot(ms, fn):
            calls.append(("timer", ms))

    class FontModule:
        answer = None

        @classmethod
        def findable(cls):
            return cls.answer

    class Check:
        def _run(self):
            calls.append(("asked",))

    class App:
        welcome = None
        font_check = Check()

    g = {"ike": App(), "QTimer": Timer, "sys": type("S", (), {"modules": {"ike.fontcheck": FontModule}}),
         "PLAN": {"mode": "measure"}, "_FONT_WAIT": [0], "_gen": None,
         "measure": lambda: calls.append(("measure",)) or iter(()), "network": lambda: iter(()),
         "_step": lambda: calls.append(("step",))}
    exec(src, g)
    g["_start"]()
    g["_start"]()
    assert calls == [("asked",), ("timer", 500), ("timer", 500)]          # asked once, then waits
    FontModule.answer = ["Arial"]
    g["_start"]()
    assert calls[-2:] == [("measure",), ("step",)]                         # measured once known
    # never forever: after 60 s without an answer it measures all the same
    calls.clear()
    FontModule.answer = None
    g["_FONT_WAIT"][0] = 120
    g["_start"]()
    assert calls == [("measure",), ("step",)]
