"""Nothing gets worse (tools/no-regression.py): the comparison, and that it really sees a weakening.

The comparator is checked on hand-made snapshots: each kind of regression
(a request blocked on main and allowed here, an element hidden on main and
shown here, a fingerprinting value changed that cannot be judged, a new host
contacted, a weaker engine switch or setting) fails; the same snapshot, or a
stricter one, passes; a change a person accepted in the allowlist passes, that
change only. The values the fingerprinting protection disguises are judged by
what protects (2026-11-24): a stronger noise (pull request #148, the audio)
passes with no allowlist; the noise off, the same in every session or smaller,
a disguised value back to the real one, and what cannot be judged, fail. Then
the real check runs on this repository and on a copy weakened as an AI fix
could weaken it (the AdBlock path letting one rule through, fingerprint.js
with its canvas noise off, site isolation dropped, a new host contacted at
start): it must catch every one of them; and on copies with the audio noise
ten times larger (passes) and off (fails).
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


# --- the fingerprinting values, judged by what protects (2026-11-24) -------------------------------
REAL_UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) QtWebEngine/6.10.1 "
           "Chrome/134.0.6998.208 Safari/537.36")
COMMON_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
REAL_GPU = "ANGLE (Mesa, llvmpipe (LLVM 20.1.2 256 bits), OpenGL ES 3.2)"
REAL_FONTS = "Arial,DejaVu Sans,FreeSans,Noto Color Emoji"
REAL_EXT = "A,B,C,D,E,F,G,H"
AUDIO_OFF = "172.6716509661"
CANVAS_OFF = ["76ddd77a", "5a63666b", 140.515625]


def fixed(value):
    return {"rule": "exact", "value": value, "session2": copy.deepcopy(value)}


def disguised(value, session2, noise=None):
    o = {"rule": "fingerprint", "value": value, "session2": session2}
    if noise is not None:
        o["noise"] = noise
    return o


# main's observations at Off (the real values) and Strict; the audio and canvas numbers are those of
# the real run of 2026-11-24 (main 1.1.24 and pull request #148)
FP_MAIN = {
    "fingerprint/off/audio": fixed(AUDIO_OFF),
    "fingerprint/off/canvas": fixed(CANVAS_OFF),
    "fingerprint/off/navigator.userAgent": fixed(REAL_UA),
    "fingerprint/off/navigator.hardwareConcurrency": fixed(4),
    "fingerprint/off/screen.width": fixed(2560),
    "fingerprint/off/webgl.unmasked_renderer": fixed(REAL_GPU),
    "fingerprint/off/webgl.extensions": fixed(REAL_EXT),
    "fingerprint/off/fonts_measured": fixed(REAL_FONTS),
    "fingerprint/off/frame": fixed([4, REAL_UA, CANVAS_OFF]),
    "fingerprint/off/natives.toDataURL": fixed("true:toDataURL:0"),
    "fingerprint/strict/audio": disguised("172.6714897020", "172.6710743882", 5.00269e-05),
    "fingerprint/strict/audio.noised": {"rule": "safer-true", "value": True},
    "fingerprint/strict/canvas": disguised(["116ec122", "5a63666b", 140.51590603125],
                                           ["47441ec7", "5a63666b", 140.5153861234375], 0.0149155),
    "fingerprint/strict/canvas.noised": {"rule": "safer-true", "value": True},
    "fingerprint/strict/navigator.userAgent": disguised(COMMON_UA, COMMON_UA),
    "fingerprint/strict/navigator.hardwareConcurrency": disguised(4, 4),
    "fingerprint/strict/screen.width": disguised(1920, 1920),
    "fingerprint/strict/webgl.unmasked_renderer": disguised(None, None),
    "fingerprint/strict/webgl.extensions": disguised("A,B,D,F,H", "B,C,E,G,H"),
    "fingerprint/strict/fonts_measured": disguised("Arial,DejaVu Sans", "Arial,DejaVu Sans"),
    "fingerprint/strict/frame": disguised([4, COMMON_UA, ["116ec122", "5a63666b", 140.51590603125]],
                                          [4, COMMON_UA, ["47441ec7", "5a63666b", 140.5153861234375]]),
    "fingerprint/strict/natives.toDataURL": fixed("true:toDataURL:0"),
}
# pull request #148: the audio noise +-0.1 % instead of +-0.01 % per sample (the real run's values)
PR148 = {"fingerprint/strict/audio": disguised("172.6700392903", "172.6658836618", 0.000500259)}


def fp_snap(changes=None, drop=()):
    s = snap()
    s["observations"] = copy.deepcopy(FP_MAIN)
    for k, v in (changes or {}).items():
        s["observations"][k] = copy.deepcopy(v)
    for k in drop:
        s["observations"].pop(k)
    return s


def judged(report, key):
    """(kind, detail) of one key in a report; "same" when it is in no list."""
    for kind in ("worse", "accepted", "stricter", "changed"):
        for r in report[kind]:
            if r["key"] == key:
                return kind, r["detail"]
    return "same", ""


def test_the_case_of_148_passes_with_no_allowlist():
    """A stronger noise (audio noised on both sides, different in each session, ten times larger)
    changes the number a page reads: it passes by itself, reported as stricter, and no person
    needs to accept it (2026-11-24: before, the raw number changed and it was "worse")."""
    report = nr.compare(fp_snap(), fp_snap(PR148), [])
    assert report["verdict"] == "pass", report["worse"]
    assert not report["accepted"] and not report["unused_allowlist"]
    kind, detail = judged(report, "fingerprint/strict/audio")
    assert kind == "stricter" and "noise larger" in detail, detail
    assert "**Passed**" in nr.markdown(report)
    # the same noise size, written by another noise: changed, still protected
    other = disguised("172.6712000000", "172.6719000000", 4.8e-05)
    kind, detail = judged(nr.compare(fp_snap(), fp_snap({"fingerprint/strict/audio": other}), []),
                          "fingerprint/strict/audio")
    assert kind == "changed" and "still protected" in detail, detail


def test_the_noise_turned_off_is_worse():
    off = {"fingerprint/strict/audio": disguised(AUDIO_OFF, AUDIO_OFF, 0.0),
           "fingerprint/strict/audio.noised": {"rule": "safer-true", "value": False}}
    report = nr.compare(fp_snap(), fp_snap(off), [])
    assert report["verdict"] == "fail"
    assert keys(report["worse"]) == {"fingerprint/strict/audio", "fingerprint/strict/audio.noised"}
    assert "real value" in judged(report, "fingerprint/strict/audio")[1]
    # off in the second session only: worse too
    half = {"fingerprint/strict/audio": disguised("172.6700392903", AUDIO_OFF, 0.00025)}
    assert judged(nr.compare(fp_snap(), fp_snap(half), []), "fingerprint/strict/audio")[0] == "worse"
    # the canvas noise off: the real picture, its noise 0
    canvas = {"fingerprint/strict/canvas": disguised(CANVAS_OFF, CANVAS_OFF, 0.0)}
    assert judged(nr.compare(fp_snap(), fp_snap(canvas), []), "fingerprint/strict/canvas")[0] == "worse"


def test_a_noise_the_same_in_every_session_is_worse():
    same = {"fingerprint/strict/audio": disguised("172.6715397447", "172.6715397447", 4.96687e-05)}
    report = nr.compare(fp_snap(), fp_snap(same), [])
    assert report["verdict"] == "fail"
    kind, detail = judged(report, "fingerprint/strict/audio")
    assert kind == "worse" and "the same in every session" in detail, detail
    # the first session as on main, the second one no longer different: still worse
    first = {"fingerprint/strict/audio": disguised("172.6714897020", "172.6714897020", 5.0e-05)}
    assert judged(nr.compare(fp_snap(), fp_snap(first), []), "fingerprint/strict/audio")[0] == "worse"


def test_a_smaller_noise_is_worse():
    small = {"fingerprint/strict/audio": disguised("172.6716348558", "172.6715934083", 5.00225e-06)}
    report = nr.compare(fp_snap(), fp_snap(small), [])
    assert report["verdict"] == "fail"
    kind, detail = judged(report, "fingerprint/strict/audio")
    assert kind == "worse" and "noise is smaller" in detail, detail
    # within NOISE_TOLERANCE (a tenth smaller): the same protection, measured once more
    near = {"fingerprint/strict/audio": disguised("172.6712000000", "172.6719000000", 4.5e-05)}
    assert nr.compare(fp_snap(), fp_snap(near), [])["verdict"] == "pass"
    # the canvas noise halved; its size not measured at all here
    for value in (0.007, None):
        canvas = {"fingerprint/strict/canvas": disguised(["0badc0de", "5a63666b", 140.5159], ["1badc0de", "5a63666b",
                                                                                            140.5154], value)}
        assert judged(nr.compare(fp_snap(), fp_snap(canvas), []), "fingerprint/strict/canvas")[0] == "worse", value
    # a list randomised on main changing fewer names (1 in each session here, 3 on main)
    fewer = {"fingerprint/strict/webgl.extensions": disguised("A,B,C,D,E,F,G", "A,B,C,D,E,F,H")}
    kind, detail = judged(nr.compare(fp_snap(), fp_snap(fewer), []), "fingerprint/strict/webgl.extensions")
    assert kind == "worse" and "fewer names" in detail, detail
    other = {"fingerprint/strict/webgl.extensions": disguised("B,C,D,F,G", "A,C,E,F,H")}
    assert judged(nr.compare(fp_snap(), fp_snap(other), []), "fingerprint/strict/webgl.extensions")[0] == "changed"


def test_a_disguised_value_back_to_the_real_one_is_worse():
    for key, value in (("navigator.userAgent", REAL_UA), ("screen.width", 2560), ("fonts_measured", REAL_FONTS)):
        report = nr.compare(fp_snap(), fp_snap({"fingerprint/strict/" + key: disguised(value, value)}), [])
        kind, detail = judged(report, "fingerprint/strict/" + key)
        assert kind == "worse" and "real value" in detail, (key, detail)
    # in the second session only
    report = nr.compare(fp_snap(), fp_snap({"fingerprint/strict/screen.width": disguised(1920, 2560)}), [])
    assert judged(report, "fingerprint/strict/screen.width")[0] == "worse"
    # the card's name, hidden on main, readable here (even a made-up one)
    fake = "ANGLE (Intel, Mesa Intel(R) UHD Graphics 630 (CFL GT2), OpenGL 4.6)"
    report = nr.compare(fp_snap(), fp_snap({"fingerprint/strict/webgl.unmasked_renderer": disguised(fake, fake)}), [])
    kind, detail = judged(report, "fingerprint/strict/webgl.unmasked_renderer")
    assert kind == "worse" and "hidden on main" in detail, detail
    # a font of the real list that main hid
    value = "Arial,DejaVu Sans,FreeSans,Hack"
    report = nr.compare(fp_snap(), fp_snap({"fingerprint/strict/fonts_measured": disguised(value, value)}), [])
    kind, detail = judged(report, "fingerprint/strict/fonts_measured")
    assert kind == "worse" and "shows more of the real list: FreeSans" in detail, detail
    # a list closer to the real one (main: every real font and three more; here: one more only)
    wide = REAL_FONTS + ",Hack,Monaco,Ubuntu"
    main = fp_snap({"fingerprint/strict/fonts_measured": disguised(wide, wide)})
    value = REAL_FONTS + ",Hack"
    report = nr.compare(main, fp_snap({"fingerprint/strict/fonts_measured": disguised(value, value)}), [])
    kind, detail = judged(report, "fingerprint/strict/fonts_measured")
    assert kind == "worse" and "closer to the real list" in detail, detail
    # a part that went back to the real value is not hidden by another part that changed
    frame = disguised([4, REAL_UA, ["0badc0de", "5a63666b", 140.5159]], [4, REAL_UA, ["1badc0de", "5a63666b", 140.5154]])
    kind, detail = judged(nr.compare(fp_snap(), fp_snap({"fingerprint/strict/frame": frame}), []),
                          "fingerprint/strict/frame")
    assert kind == "worse" and detail.startswith("[1] the real value"), detail
    # one disguise for another, neither the real value: changed, it passes
    other = {"fingerprint/strict/screen.width": disguised(1680, 1680),
             "fingerprint/strict/navigator.userAgent": disguised(COMMON_UA.replace("140", "141"),
                                                                 COMMON_UA.replace("140", "141")),
             "fingerprint/strict/fonts_measured": disguised("Arial,Liberation Sans", "Arial,Liberation Sans")}
    report = nr.compare(fp_snap(), fp_snap(other), [])
    assert report["verdict"] == "pass", report["worse"]
    assert keys(report["changed"]) == set(other)


def test_what_cannot_be_judged_stays_worse(tmp_path):
    cases = {
        # not a disguised value: the exact rule
        "fingerprint/strict/natives.toDataURL": fixed("false:toDataURL:0"),
        # main gave the real value: a change cannot be judged, even to a common one
        "fingerprint/strict/navigator.hardwareConcurrency": disguised(8, 8),
        # the page could not read it here
        "fingerprint/strict/screen.width": disguised("error TypeError: x", "error TypeError: x"),
        # no second session measured here
        "fingerprint/strict/webgl.extensions": {"rule": "fingerprint", "value": "B,C,D,F,G"},
    }
    for key, obs in cases.items():
        report = nr.compare(fp_snap(), fp_snap({key: obs}), [])
        assert report["verdict"] == "fail" and keys(report["worse"]) == {key}, (key, report["worse"])
    # the Off level not measured (one level only): a changed value cannot be judged
    off_keys = [k for k in FP_MAIN if k.startswith("fingerprint/off/")]
    report = nr.compare(fp_snap(drop=off_keys), fp_snap(PR148, drop=off_keys), [])
    assert judged(report, "fingerprint/strict/audio")[0] == "worse"
    # it changes between sessions at Off too: nothing to tell the protection from
    shaky = {"fingerprint/off/audio": {"rule": "exact", "value": AUDIO_OFF, "session2": "172.6716509662"}}
    report = nr.compare(fp_snap(shaky), fp_snap(dict(PR148, **shaky)), [])
    assert judged(report, "fingerprint/strict/audio")[0] == "worse"
    # missing here
    report = nr.compare(fp_snap(), fp_snap(drop=["fingerprint/strict/audio"]), [])
    assert judged(report, "fingerprint/strict/audio")[0] == "worse"
    # the allowlist stays a person's, for a real weakening: an entry accepts it, that change only
    weak = {"fingerprint/strict/audio": disguised(AUDIO_OFF, AUDIO_OFF, 0.0)}
    entries = [{"key": "fingerprint/*/audio", "candidate": AUDIO_OFF, "why": "a test", "accepted": "a person"},
               {"key": "fingerprint/*/canvas", "why": "never used"}]
    report = nr.compare(fp_snap(), fp_snap(weak), entries)
    assert report["verdict"] == "pass" and keys(report["accepted"]) == {"fingerprint/strict/audio"}
    assert [e["key"] for e in report["unused_allowlist"]] == ["fingerprint/*/canvas"]
    assert nr.compare(fp_snap(), fp_snap(PR148), entries)["unused_allowlist"] == entries


def test_a_snapshot_of_the_older_copy_compares_safely():
    """main measured by a copy of the tool before 2026-11-24 (no second session, no noise size, the
    exact rule everywhere) against a candidate measured by this one: no crash and no false worse."""
    old = fp_snap()
    for k, o in old["observations"].items():
        o.pop("session2", None)
        o.pop("noise", None)
        o["rule"] = "exact"
    report = nr.compare(old, fp_snap(), [])
    assert report["verdict"] == "pass" and not report["worse"] and not report["changed"], report
    # pull request #148: still noised and different in each session; main's noise size unknown
    report = nr.compare(old, fp_snap(PR148), [])
    assert report["verdict"] == "pass", report["worse"]
    assert judged(report, "fingerprint/strict/audio")[0] == "changed"
    # what the candidate shows is still judged: the noise off, or the same in every session
    for audio in (disguised(AUDIO_OFF, AUDIO_OFF, 0.0), disguised("172.6715397447", "172.6715397447", 5e-05)):
        report = nr.compare(old, fp_snap({"fingerprint/strict/audio": audio}), [])
        assert judged(report, "fingerprint/strict/audio")[0] == "worse", audio
    # and the other way round (an older candidate): its values are judged, nothing crashes
    report = nr.compare(fp_snap(), old, [])
    assert report["verdict"] == "pass" and not report["worse"]


def test_the_rules_of_the_fingerprinting_values():
    assert nr._rule("fingerprint/strict/audio", {"rule": "exact"}, None) == "fingerprint"
    assert nr._rule("fingerprint/strict/canvas.noised", {"rule": "exact"}, None) == "safer-true"
    assert nr._rule("fingerprint/off/audio", {"rule": "exact"}, None) == "exact"
    for name in ("natives.toDataURL", "third_party", "permissions.camera", "navigator.webdriver",
                 "navigator.globalPrivacyControl", "local_fonts", "keyboard", "ike_scheme"):
        assert nr._rule("fingerprint/strict/" + name, {"rule": "exact"}, None) == "exact", name
    for name in ("canvas", "canvas_blob", "audio", "webgl.unmasked_renderer", "navigator.userAgent",
                 "screen.width", "hints.high", "intl.timeZone", "fonts_measured", "media_queries", "frame"):
        assert nr.FP_JUDGED.match(name), name
    # the parts of a value
    assert nr._parts("(pointer: fine)=true (hover: hover)=false", "media_queries") == {
        "[(hover: hover)]": "false", "[(pointer: fine)]": "true"}
    assert nr._parts('{"bitness":"64","brands":[{"brand":"A"}]}', "hints.high") == {
        "[bitness]": "64", "[brands][0][brand]": "A"}
    assert nr._parts("x", "screen.width") == {"": "x"}
    # the size of the noise
    assert nr._noise("audio", [{"audio_samples": [1.0, 2.2]}], {"audio_samples": [1.0, 2.0]}) == 0.05
    assert nr._noise("audio", [{"audio_samples": [1.0]}], {"audio_samples": [1.0, 2.0]}) is None
    assert nr._noise("canvas", [{"canvas_noise": 0.01}, {"canvas_noise": 0.02}], {}) == 0.015
    assert nr._noise("canvas", [{"canvas_noise": "error x"}], {}) is None


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


def source_copy(dest):
    for part in ("ike", "vendor", "data"):
        shutil.copytree(ROOT / part, dest / part, symlinks=True,
                        ignore=shutil.ignore_patterns("__pycache__", "_engine"))
    shutil.copy2(ROOT / "ike_boot.py", dest / "ike_boot.py")


def weakened_copy(dest):
    source_copy(dest)
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


# the noise factor of each rendered audio sample (fingerprint.js, audioNoise): 1 +- (0..1000) / N
AUDIO_RETURN = re.compile(r"return 1 \+ \(\(\(x >>> 0\) % 2001\) - 1000\) / (\d+);")


def audio_copy(dest, stronger):
    """A copy whose audio noise is ten times larger (as pull request #148 made it), or off."""
    source_copy(dest)
    f = dest / "ike" / "resources" / "fingerprint.js"
    text = f.read_text("utf-8")
    found = AUDIO_RETURN.findall(text)
    assert len(found) == 1, found
    new = "return 1 + (((x >>> 0) %% 2001) - 1000) / %d;" % (int(found[0]) // 10) if stronger else "return 1;"
    f.write_text(AUDIO_RETURN.sub(lambda m: new, text), "utf-8")


@needs_engine
def test_the_check_judges_the_audio_noise_by_what_protects(tmp_path):
    """Pull request #148 measured for real: a larger audio noise passes with no allowlist (it was
    "worse" only because the number changed); the noise off fails."""
    if os.environ.get("IKE_TEST_APP"):
        pytest.skip("the sources are checked once, not for the installed copy")
    how = {"levels": ["off", "strict"], "sections": ["fingerprint"]}
    audio_copy(tmp_path / "stronger", True)
    audio_copy(tmp_path / "off", False)
    base = nr.snapshot(ROOT, **how)
    assert not base["errors"], base["errors"]
    main = base["observations"]["fingerprint/strict/audio"]
    assert main["value"] != base["observations"]["fingerprint/off/audio"]["value"]
    assert main["session2"] != main["value"] and main["noise"] > 0, main
    stronger = nr.snapshot(tmp_path / "stronger", **how)
    report = nr.compare(base, stronger, [])
    assert report["verdict"] == "pass", (report["worse"], report["errors"])
    kind, detail = judged(report, "fingerprint/strict/audio")
    assert kind == "stricter" and "noise larger" in detail, detail
    assert stronger["observations"]["fingerprint/strict/audio"]["noise"] > 5 * main["noise"]
    off = nr.snapshot(tmp_path / "off", **how)
    report = nr.compare(base, off, [])
    assert report["verdict"] == "fail"
    assert {"fingerprint/strict/audio", "fingerprint/strict/audio.noised"} <= keys(report["worse"]), report["worse"]
