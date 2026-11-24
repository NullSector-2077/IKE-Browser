"""Nothing gets worse (tools/no-regression.py): the comparison, and that it really sees a weakening.

The comparator is checked on hand-made snapshots: each kind of regression
(a request blocked on main and allowed here, an element hidden on main and
shown here, a fingerprinting value changed that cannot be judged, a new host
contacted, a weaker engine switch or setting) fails; the same snapshot, or a
stricter one, passes; a change a person accepted in the allowlist passes, that
change only. The values the fingerprinting protection disguises are judged by
what protects (2026-11-24): a stronger noise (pull request #148, the audio)
passes with no allowlist; the noise off, the same in every session or smaller,
a disguised value back to the real one or nearer it, a mark turned false, a
protected value lost, and what cannot be judged, fail. Evidence (after the
independent review of 2026-11-24, "when in doubt, worse") accepts only a value
main left real now disguised, with a test a person bound to it that fails on
main and passes here, confirmed three times on each side; never a weakening,
even with a fixed test (adversarial cases); a request only by the list data, a
host only declared and named by the change's code, a security setting never.
The names that could reveal the measurement are random and refused in AI
fixes; the signing notice lists what passed by evidence. Then
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
import random
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
    # a list of hosts not measured on the candidate: never "nothing new"
    report = nr.compare(base, with_values(base, {"network__fresh-profile": None}))
    assert keys(report["worse"]) == {"network/fresh-profile"}
    # the hosts I.K.E.'s own code contacted not recorded (the audit hook did not report): an error
    raw = {"measure": {"errors": [], "levels": {}, "python_hosts": None, "proxy_hosts": []},
           "network": {"errors": [], "python_hosts": ["x.example"], "proxy_hosts": [], "probe_done": True}}
    errors, _obs = nr.observations(raw, ["balanced"], ["network"], {"requests": [], "pages": []})
    assert any("were not recorded (measure)" in e["error"] for e in errors), errors


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
                 "tests/data/no-regression/lists/easylist.txt", "tests/data/no-regression/endpoints.json",
                 "tests/data/no-regression/necessity.json", "tests/data/no-regression/noise-floor.json"):
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
    # the evidence (2026-11-24, after the independent review): main's test results read by a job of
    # their own, the only one with actions: read, that runs none of this commit's code (no checkout),
    # only from a run of tests.yml pushed to main that ended in success or failure
    jobs = text.split("\njobs:\n", 1)[1]
    fetch = jobs.split("\n  main-results:\n", 1)[1].split("\n  plan:\n", 1)[0]
    assert "permissions:\n      contents: read\n      actions: read\n" in fetch and "write" not in fetch
    assert "actions/checkout" not in fetch and "pytest" not in fetch and "ike_boot" not in fetch
    assert "--branch main --event push" in fetch and "--commit \"$base\"" in fetch
    assert '.conclusion == "success" or .conclusion == "failure"' in fetch and "gh run download" in fetch
    assert "name: main-test-results" in fetch and "base.txt" in fetch
    checks_job = jobs.split("\n  checks:\n", 1)[1].split("\n    steps:\n", 1)[0]
    assert "needs: main-results" in checks_job and "permissions" not in checks_job
    assert "if: ${{ !cancelled() }}" in checks_job, "the checks run even when main's results cannot be read"
    head = text.split("\njobs:\n", 1)[0]
    assert "permissions:\n  contents: read\n" in head and "actions" not in head
    # the step that runs this commit's code gets no token, takes main's results only of its own base,
    # hands the evidence only to a copy of the tool that reads it, and reads main's allowlist, endpoints
    # and bindings, never the candidate's
    assert "GH_TOKEN" not in step and "token" not in step
    assert "grep -q -- '\"--main-junit\"' \"$tool\"" in step and '[ "$read_base" = "$base" ]' in step
    assert "--candidate-junit" in step
    for name in ("allowlist", "endpoints", "necessity"):
        assert '"$where/tests/data/no-regression/%s.json"' % name in step, name
        assert " tests/data/no-regression/%s.json" % name not in step, name
    assert text.index("name: main-test-results\n          path:") < text.index("- name: Nothing gets worse\n")
    # the bound tests are run here on this commit (the shards run in other jobs), only main's bindings
    assert "$where/tests/data/no-regression/necessity.json\")" in step and "nr-candidate-junit.xml" in step
    # an AI's change of the page scripts or of shields.py: three measures with independent keys (N5)
    assert "runs=(--runs 3)" in step and '"${branch#automation/}" != "$branch"' in step
    assert "ike/resources/[a-z]+\\.js$|^ike/shields\\.py$" in step
    # the fingerprinting rows that are not the same or stricter: a step of their own, its outcome the
    # job's output, never a red; restated in "tests" only when it passed (tools/automerge.py reads it)
    fp = text[text.index("- name: Fingerprinting unchanged\n        id: fp-unchanged"):]
    fp = fp[:fp.index("\n      - ", 10)]
    assert "continue-on-error: true" in fp and "fingerprint_review" in fp
    assert "fp-unchanged: ${{ steps.fp-unchanged.outcome }}" in text
    gate = text.split("\n  tests:\n", 1)[1]
    again = gate[gate.index("- name: Fingerprinting unchanged"):]
    again = again[:again.index("\n      # ", 10)]
    assert "needs.checks.outputs.fp-unchanged == 'success'" in again and "test \"$" not in again


# --- the fingerprinting values, judged by what protects (2026-11-24) -------------------------------
REAL_UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) QtWebEngine/6.10.1 "
           "Chrome/134.0.6998.208 Safari/537.36")
COMMON_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
REAL_GPU = "ANGLE (Mesa, llvmpipe (LLVM 20.1.2 256 bits), OpenGL ES 3.2)"
REAL_FONTS = "Arial,DejaVu Sans,FreeSans,Noto Color Emoji"
REAL_EXT = "A,B,C,D,E,F,G,H"
AUDIO_OFF = "172.6716509661"
CANVAS_OFF = ["76ddd77a", "5a63666b", 140.515625]
# the noise sizes of the real run of 2026-11-24 (main 1.1.24, and pull request #148: the audio x10)
AUDIO_NOISE = {"dispersion": 4.98428e-05, "share": 1.0}
CANVAS_NOISE = {"png": 0.0015483, "png_share": 0.00133523, "pixels": 0.0146349, "pixels_share": 0.0146349,
                "widths": 1.48281e-06, "widths_share": 0.984375}


def fixed(value):
    return {"rule": "exact", "value": value, "session2": copy.deepcopy(value)}


def disguised(value, session2, noise=None):
    o = {"rule": "fingerprint", "value": value, "session2": session2}
    if noise is not None:
        o["noise"] = dict(noise)
    return o


def mark(value):
    return {"rule": "safer-true", "value": value}


# main's observations at Off (the real values) and Strict; the audio and canvas numbers are those of
# the real run of 2026-11-24
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
    "fingerprint/off/keyboard": fixed("map 49"),
    "fingerprint/strict/audio": disguised("172.6714897020", "172.6710743882", AUDIO_NOISE),
    "fingerprint/strict/audio.noised": mark(True),
    "fingerprint/strict/stable.audio": mark(True),
    "fingerprint/strict/canvas": disguised(["116ec122", "5a63666b", 140.51590603125],
                                           ["47441ec7", "5a63666b", 140.5153861234375], CANVAS_NOISE),
    "fingerprint/strict/canvas.noised": mark(True),
    "fingerprint/strict/stable.canvas": mark(True),
    "fingerprint/strict/site.canvas": mark(False),
    "fingerprint/natural/canvas.differs": mark(True),
    "fingerprint/natural/audio.noised": mark(True),
    "fingerprint/strict/navigator.userAgent": disguised(COMMON_UA, COMMON_UA),
    "fingerprint/strict/navigator.hardwareConcurrency": disguised(4, 4),
    "fingerprint/strict/screen.width": disguised(1920, 1920),
    "fingerprint/strict/webgl.unmasked_renderer": disguised(None, None),
    "fingerprint/strict/webgl.extensions": disguised("A,B,D,F,H", "B,C,E,G,H"),
    "fingerprint/strict/fonts_measured": disguised("Arial,DejaVu Sans", "Arial,DejaVu Sans"),
    "fingerprint/strict/frame": disguised([4, COMMON_UA, ["116ec122", "5a63666b", 140.51590603125]],
                                          [4, COMMON_UA, ["47441ec7", "5a63666b", 140.5153861234375]]),
    "fingerprint/strict/natives.toDataURL": fixed("true:toDataURL:0"),
    "fingerprint/strict/keyboard": fixed("refused SecurityError"),
    "fingerprint/strict/storage_quota": fixed(10737418240),
    "page-scriptlets/strict/news/canRunAds": {"rule": "exact", "value": "true"},
}
# pull request #148: the audio noise +-0.1 % instead of +-0.01 % per sample (the real run's values)
PR148 = {"fingerprint/strict/audio": disguised("172.6700392903", "172.6658836618",
                                               {"dispersion": 4.98428e-04, "share": 1.0})}


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
    for kind in ("worse", "evidence", "accepted", "stricter", "changed"):
        for r in report[kind]:
            if r["key"] == key:
                return kind, r["detail"]
    return "same", ""


def cmp(changes=None, base=None, evidence=None, floors=None, entries=(), common=None):
    return nr.compare(base or fp_snap(), fp_snap(changes), list(entries), evidence, {} if floors is None else floors,
                      {} if common is None else common)


def test_the_case_of_148_passes_with_no_allowlist():
    """A stronger noise (audio noised on both sides, different in each session, ten times larger)
    changes the number a page reads: it passes by itself, reported as stricter, and no person
    needs to accept it (2026-11-24: before, the raw number changed and it was "worse")."""
    for floors in ({}, nr.load_floors()):           # with and without the floors kept by a person
        report = cmp(PR148, floors=floors)
        assert report["verdict"] == "pass", report["worse"]
        assert not report["accepted"] and not report["unused_allowlist"] and not report["evidence"]
        kind, detail = judged(report, "fingerprint/strict/audio")
        assert kind == "stricter" and "noise larger" in detail, detail
    assert "**Passed**" in nr.markdown(report)
    # the same noise size, written by another noise: changed, still protected
    other = disguised("172.6712000000", "172.6719000000", {"dispersion": 4.8e-05, "share": 1.0})
    kind, detail = judged(cmp({"fingerprint/strict/audio": other}), "fingerprint/strict/audio")
    assert kind == "changed" and "still protected" in detail, detail


def test_the_noise_turned_off_is_worse():
    off = {"fingerprint/strict/audio": disguised(AUDIO_OFF, AUDIO_OFF, {"dispersion": 0.0, "share": 0.0}),
           "fingerprint/strict/audio.noised": mark(False)}
    report = cmp(off)
    assert report["verdict"] == "fail"
    assert keys(report["worse"]) == {"fingerprint/strict/audio", "fingerprint/strict/audio.noised"}
    assert "real value" in judged(report, "fingerprint/strict/audio")[1]
    assert all(r["weakening"] for r in report["worse"])
    # off in the second session only: worse too
    half = {"fingerprint/strict/audio": disguised("172.6700392903", AUDIO_OFF, AUDIO_NOISE)}
    assert judged(cmp(half), "fingerprint/strict/audio")[0] == "worse"
    # the canvas noise off: the real picture
    canvas = {"fingerprint/strict/canvas": disguised(CANVAS_OFF, CANVAS_OFF, dict.fromkeys(CANVAS_NOISE, 0.0))}
    assert judged(cmp(canvas), "fingerprint/strict/canvas")[0] == "worse"
    # the marks: not noised, the two natural starts alike, read twice differently, the frame of another
    # site no longer different
    for k in ("fingerprint/strict/canvas.noised", "fingerprint/natural/canvas.differs",
              "fingerprint/natural/audio.noised", "fingerprint/strict/stable.audio"):
        report = cmp({k: mark(False)})
        assert keys(report["worse"]) == {k} and report["worse"][0]["weakening"], k
    report = cmp({"fingerprint/strict/site.canvas": mark(True)})
    assert keys(report["stricter"]) == {"fingerprint/strict/site.canvas"}
    report = cmp(base=fp_snap({"fingerprint/strict/site.canvas": mark(True)}),
                 changes={"fingerprint/strict/site.canvas": mark(False)})
    assert keys(report["worse"]) == {"fingerprint/strict/site.canvas"}


def test_a_noise_the_same_in_every_session_is_worse():
    same = {"fingerprint/strict/audio": disguised("172.6715397447", "172.6715397447", AUDIO_NOISE)}
    report = cmp(same)
    assert report["verdict"] == "fail"
    kind, detail = judged(report, "fingerprint/strict/audio")
    assert kind == "worse" and "the same in every session" in detail, detail
    # the first session as on main, the second one no longer different: still worse
    first = {"fingerprint/strict/audio": disguised("172.6714897020", "172.6714897020", AUDIO_NOISE)}
    assert judged(cmp(first), "fingerprint/strict/audio")[0] == "worse"


def test_a_smaller_noise_is_worse():
    small = {"fingerprint/strict/audio": disguised("172.6716348558", "172.6715934083",
                                                   {"dispersion": 4.98e-06, "share": 1.0})}
    report = cmp(small)
    assert report["verdict"] == "fail"
    kind, detail = judged(report, "fingerprint/strict/audio")
    assert kind == "worse" and "noise is smaller" in detail and report["worse"][0]["weakening"], detail
    # a constant gain changes every sample by the same factor: no dispersion at all
    gain = {"fingerprint/strict/audio": disguised("172.7579867916", "172.7579867916" + "1",
                                                  {"dispersion": 0.0, "share": 1.0})}
    kind, detail = judged(cmp(gain), "fingerprint/strict/audio")
    assert kind == "worse" and "dispersion" in detail, detail
    # within NOISE_TOLERANCE (a tenth smaller): the same protection, measured once more
    near = {"fingerprint/strict/audio": disguised("172.6712000000", "172.6719000000",
                                                  {"dispersion": 4.5e-05, "share": 1.0})}
    assert cmp(near)["verdict"] == "pass"
    # a person's floor: main's own noise is no lower bound once it fell (the noise cannot be lowered
    # merge after merge)
    floors = {"audio": {"dispersion": 2e-04}}
    kind, detail = judged(cmp(near, floors=floors), "fingerprint/strict/audio")
    assert kind == "worse" and "floor" in detail, detail
    # the canvas: a smaller share of changed pixels, or a measure that could not be read here
    new = ["0badc0de", "5a63666b", 140.5159], ["1badc0de", "5a63666b", 140.5154]
    for noise, kind in ((dict(CANVAS_NOISE, pixels_share=0.002), "worse"),
                        ({k: v for k, v in CANVAS_NOISE.items() if k != "png"}, "worse"),
                        (CANVAS_NOISE, "changed")):
        report = cmp({"fingerprint/strict/canvas": disguised(new[0], new[1], noise)})
        assert judged(report, "fingerprint/strict/canvas")[0] == kind, (noise, report["worse"])
    # the tolerance of chance from the elements a size rests on (k): many, 20 %; few, wider, but never
    # above 35 % (more readings, not a looser rule; second review of 2026-11-24): a size halved is
    # always worse, however few its elements
    off = {"fingerprint/off/canvas_blob": fixed("0ffc0de")}
    for k, here_size, kind in ((7, 0.0006, "changed"), (7, 0.0004, "worse"), (8000, 0.0006, "worse")):
        main_noise = {"png": 0.000854, "png_share": 0.000854, "png_k": k, "png_share_k": k}
        base = fp_snap(dict(off, **{"fingerprint/strict/canvas_blob": disguised("1badc0de", "2badc0de", main_noise)}))
        here = dict(off, **{"fingerprint/strict/canvas_blob": disguised(
            "3badc0de", "4badc0de", {"png": here_size, "png_share": here_size, "png_k": k, "png_share_k": k})})
        assert judged(cmp(here, base=base), "fingerprint/strict/canvas_blob")[0] == kind, (k, here_size)
    # the floor of a person, with no tolerance: main's own noise already lowered cannot be lowered more
    floors = {"canvas_blob": {"png": 0.0007}}
    base = fp_snap(dict(off, **{"fingerprint/strict/canvas_blob": disguised(
        "1badc0de", "2badc0de", {"png": 0.00072, "png_k": 9000})}))
    here = dict(off, **{"fingerprint/strict/canvas_blob": disguised("3badc0de", "4badc0de",
                                                                    {"png": 0.00069, "png_k": 9000})})
    kind, detail = judged(cmp(here, base=base, floors=floors), "fingerprint/strict/canvas_blob")
    assert kind == "worse" and "floor 0.0007" in detail, detail
    # a number randomised on main (one text width) is judged from the 128 widths of the noise's size,
    # never from its two readings, which would be chance (2026-11-24, the false-alarm review: a check
    # of this test once said "worse" here)
    near_width = disguised(["0badc0de", "5a63666b", 140.5156251], ["1badc0de", "5a63666b", 140.5156249],
                           CANVAS_NOISE)
    assert judged(cmp({"fingerprint/strict/canvas": near_width}), "fingerprint/strict/canvas")[0] == "changed"
    small_widths = dict(near_width, noise=dict(CANVAS_NOISE, widths=1e-07))
    assert judged(cmp({"fingerprint/strict/canvas": small_widths}), "fingerprint/strict/canvas")[0] == "worse"
    # a list randomised on main changing fewer names: judged over eight sessions on each side
    # (test_what_chance_can_do_is_not_worse_and_what_it_cannot_is); with two sessions it cannot be
    # judged at all, so it is worse (second review of 2026-11-24: once a drop of 3 to 1 passed here)
    fewer = {"fingerprint/strict/webgl.extensions": disguised("A,B,C,D,E,F,G", "A,B,C,D,E,F,H")}
    assert judged(cmp(fewer), "fingerprint/strict/webgl.extensions")[0] == "worse"
    # the noise read again with the same value: a smaller size alone is worse too
    same_value = dict(FP_MAIN["fingerprint/strict/audio"], noise={"dispersion": 1e-06, "share": 1.0})
    assert judged(cmp({"fingerprint/strict/audio": same_value}), "fingerprint/strict/audio")[0] == "worse"


def test_a_disguised_value_back_to_the_real_one_is_worse():
    for key, value in (("navigator.userAgent", REAL_UA), ("screen.width", 2560), ("fonts_measured", REAL_FONTS)):
        report = cmp({"fingerprint/strict/" + key: disguised(value, value)})
        kind, detail = judged(report, "fingerprint/strict/" + key)
        assert kind == "worse" and "real value" in detail, (key, detail)
    # in the second session only
    assert judged(cmp({"fingerprint/strict/screen.width": disguised(1920, 2560)}),
                  "fingerprint/strict/screen.width")[0] == "worse"
    # main's real value, when the candidate's own Off moved (both Offs count)
    moved = {"fingerprint/off/screen.width": fixed(2048), "fingerprint/strict/screen.width": disguised(2560, 2560)}
    assert judged(cmp(moved), "fingerprint/strict/screen.width")[0] == "worse"
    # the card's name, hidden on main, readable here (even a made-up one)
    fake = "ANGLE (Intel, Mesa Intel(R) UHD Graphics 630 (CFL GT2), OpenGL 4.6)"
    kind, detail = judged(cmp({"fingerprint/strict/webgl.unmasked_renderer": disguised(fake, fake)}),
                          "fingerprint/strict/webgl.unmasked_renderer")
    assert kind == "worse" and "hidden on main" in detail, detail
    # a font of the real list that main hid
    value = "Arial,DejaVu Sans,FreeSans,Hack"
    kind, detail = judged(cmp({"fingerprint/strict/fonts_measured": disguised(value, value)}),
                          "fingerprint/strict/fonts_measured")
    assert kind == "worse" and "shows more of the real list: FreeSans" in detail, detail
    # a list closer to the real one (main: every real font and three more; here: one more only)
    wide = REAL_FONTS + ",Hack,Monaco,Ubuntu"
    main = fp_snap({"fingerprint/strict/fonts_measured": disguised(wide, wide)})
    value = REAL_FONTS + ",Hack"
    kind, detail = judged(cmp({"fingerprint/strict/fonts_measured": disguised(value, value)}, base=main),
                          "fingerprint/strict/fonts_measured")
    assert kind == "worse" and "closer to the real list" in detail, detail
    # a fixed number nearer the real one, a text with more of the real one's words or the real one in it
    for key, value, why in (("screen.width", 2400, "closer to the real value"),
                            ("navigator.userAgent", COMMON_UA.replace("Chrome/140.0.0.0", "QtWebEngine/6.10.1 "
                                                                      "Chrome/140.0.0.0"), "more of the real"),
                            ("navigator.userAgent", REAL_UA + " extra", "is in it")):
        kind, detail = judged(cmp({"fingerprint/strict/" + key: disguised(value, value)}), "fingerprint/strict/" + key)
        assert kind == "worse" and why in detail, (key, detail)
    # a part that went back to the real value is not hidden by another part that changed
    frame = disguised([4, REAL_UA, ["0badc0de", "5a63666b", 140.5159]], [4, REAL_UA, ["1badc0de", "5a63666b", 140.5154]])
    kind, detail = judged(cmp({"fingerprint/strict/frame": frame}), "fingerprint/strict/frame")
    assert kind == "worse" and detail.startswith("[1] the real value"), detail
    # one fixed disguise for another, no nearer the real one: it passes only when a person counts the
    # new value among the common ones (second review of 2026-11-24; once it passed by itself)
    other = {"fingerprint/strict/screen.width": disguised(1680, 1680),
             "fingerprint/strict/navigator.userAgent": disguised(COMMON_UA.replace("140", "141"),
                                                                 COMMON_UA.replace("140", "141")),
             "fingerprint/strict/fonts_measured": disguised("Arial,Liberation Sans", "Arial,Liberation Sans")}
    report = cmp(other)
    assert report["verdict"] == "fail" and keys(report["worse"]) == set(other)
    assert all("common values a person keeps" in r["detail"] for r in report["worse"]), report["worse"]
    common = {("screen.width", ""): [1680], ("navigator.userAgent", ""): [COMMON_UA.replace("140", "141")],
              ("fonts_measured", ""): ["Arial,Liberation Sans"]}
    report = nr.compare(fp_snap(), fp_snap(other), [], None, {}, common)
    assert report["verdict"] == "pass", report["worse"]
    assert keys(report["changed"]) == set(other)
    path = ROOT / "tests" / "data" / "no-regression" / "common-values.json"
    assert nr.load_common(path) == {} and "Only a person" in json.loads(path.read_text("utf-8"))["about"]


def test_unreadable_rules_are_an_error(monkeypatch, tmp_path):
    """The floors and the common values a person keeps are rules: a file that cannot be read fails
    the check (never "no floor", never "no common value")."""
    assert nr.load_floors(tmp_path / "missing.json") is None and nr.load_common(tmp_path / "missing.json") is None
    assert nr.compare(fp_snap(), fp_snap(), [])["verdict"] == "pass"          # both read from their files
    monkeypatch.setattr(nr, "NOISE_FLOORS", tmp_path / "missing.json")
    report = nr.compare(fp_snap(), fp_snap(), [])
    assert report["verdict"] == "fail" and "noise floors" in report["errors"][0]
    monkeypatch.setattr(nr, "NOISE_FLOORS", ROOT / "tests" / "data" / "no-regression" / "noise-floor.json")
    monkeypatch.setattr(nr, "COMMON_VALUES", tmp_path / "missing.json")
    report = nr.compare(fp_snap(), fp_snap(), [])
    assert report["verdict"] == "fail" and "common values" in report["errors"][0]
    (tmp_path / "c.json").write_text(json.dumps({"entries": [
        {"value": "screen.width", "common": [1680], "why": "a common laptop width"}, {"value": "x"}]}))
    assert nr.load_common(tmp_path / "c.json") == {("screen.width", ""): [1680]}


def drawn(values, noise=None):
    """A disguised value read in every session (SESSIONS of them)."""
    o = {"rule": "fingerprint", "value": values[0], "session2": values[1], "sessions": list(values)}
    if noise is not None:
        o["noise"] = dict(noise)
    return o


INTEL = ["ANGLE (Intel, Mesa Intel(R) UHD Graphics 630 (CFL GT2), OpenGL 4.6)",
         "ANGLE (Intel, Mesa Intel(R) HD Graphics 520 (SKL GT2), OpenGL 4.6)",
         "ANGLE (Intel, Mesa Intel(R) Xe Graphics (TGL GT2), OpenGL 4.6)"]
NVIDIA = ["ANGLE (NVIDIA Corporation, NVIDIA GeForce GTX 1650/PCIe/SSE2, OpenGL 4.5.0)",
          "ANGLE (NVIDIA Corporation, NVIDIA GeForce RTX 3060/PCIe/SSE2, OpenGL 4.5.0)"]


def test_what_chance_can_do_is_not_worse_and_what_it_cannot_is():
    """A rewrite of the noise draws every noised value anew. What chance can produce is not worse; what
    it can hardly produce (over SESSIONS sessions) is: the first review of 2026-11-24 measured 109 of
    132 pairs of main against main with a false "worse" from chance, the second asked that no
    weakening pass by the rules written against it. More readings, not looser rules."""
    gpu, off_gpu = "fingerprint/balanced/webgl.unmasked_renderer", {"fingerprint/off/webgl.unmasked_renderer":
                                                                    fixed(REAL_GPU)}
    models = INTEL + NVIDIA
    rnd = random.Random(3)
    main_draws = [rnd.choice(models) for _ in range(24)]          # 8 sessions and 16 draws of the small page
    base = fp_snap(dict(off_gpu, **{gpu: drawn(main_draws)}))

    def verdict(draws):
        return judged(cmp(dict(off_gpu, **{gpu: drawn(draws)}), base=base), gpu)
    # other draws of the same models, some alike: chance
    assert verdict([rnd.choice(models) for _ in range(24)])[0] == "changed"
    # the same model in all 24 draws: worse (an exact permutation test of the 48 draws: under 1e-4)
    kind, detail = verdict([INTEL[0]] * 24)
    assert kind == "worse" and "the same in every one of the 24 sessions" in detail, detail
    # with 8 draws alone the same is not judged (8 + 8 cannot tell it from chance at 1e-4)
    assert nr._chance_alike(main_draws[:8], [main_draws[0]] * 8) > nr.CHANCE
    # the real card in one session where main never gave it: worse
    assert verdict([INTEL[1], REAL_GPU] + main_draws[2:])[0] == "worse"
    # the real value where main gave it too: worse only where it comes far more often than on main
    # (an exact permutation test); before, any count passed
    cores, off_cores = "fingerprint/balanced/navigator.hardwareConcurrency", {
        "fingerprint/off/navigator.hardwareConcurrency": fixed(4)}
    cb = fp_snap(dict(off_cores, **{cores: drawn([4, 8] * 12)}))
    assert judged(cmp(dict(off_cores, **{cores: drawn([8, 4] * 12)}), base=cb), cores)[0] == "changed"
    kind, detail = judged(cmp(dict(off_cores, **{cores: drawn([4] * 24)}), base=cb), cores)
    assert kind == "worse" and "24 of 24 sessions here, 12 of 24 on main" in detail, detail
    assert nr._more_often(12, 24, 24, 24) < nr.CHANCE < nr._more_often(12, 24, 16, 24)
    # more of the real card's words than any of main's draws had: worse
    nearer = "ANGLE (Mesa, llvmpipe (LLVM 20.1.2 256 bits), OpenGL 4.6)"
    kind, detail = verdict([nearer] + main_draws[1:])
    assert kind == "worse" and "words" in detail, detail
    # the maker alone, of two: all eight alike is still likely by chance from main's draws (5 to 3)
    vendor, off_vendor = "fingerprint/balanced/webgl.unmasked_vendor", {"fingerprint/off/webgl.unmasked_vendor":
                                                                       fixed("Google Inc. (Mesa)")}
    makers = ["Google Inc. (Intel)", "Google Inc. (NVIDIA Corporation)"]
    maker_draws = [makers[i] for i in (0, 1, 0, 0, 1, 0, 1, 0) * 3]
    vb = fp_snap(dict(off_vendor, **{vendor: drawn(maker_draws)}))
    report = cmp(dict(off_vendor, **{vendor: drawn([makers[0]] * 24)}), base=vb)
    assert judged(report, vendor)[0] == "changed"
    assert nr._chance_alike(maker_draws, [makers[0]] * 24) > nr.CHANCE
    assert nr._chance_alike(main_draws, [INTEL[0]] * 24) < nr.CHANCE
    assert nr.PICK_DRAWS >= 16 and "webgl.unmasked_renderer" in nr.PICK_DRAWN
    # a list drawn per session (the extensions): as many names changed, as many different lists
    ext, off_ext = "fingerprint/strict/webgl.extensions", {"fingerprint/off/webgl.extensions": fixed(REAL_EXT)}
    rng = random.Random(7)
    names = REAL_EXT.split(",")

    def lists(hidden, n=8, distinct=True):
        """n lists, each hiding `hidden` names (never none, never all), different ones each session."""
        out = []
        while len(out) < n:
            gone = set(rng.sample(names, hidden))
            out.append(",".join(x for x in names if x not in gone))
        return out if distinct else [out[0], out[1]] * (n // 2)
    eb = fp_snap(dict(off_ext, **{ext: drawn(lists(4))}))
    assert judged(cmp(dict(off_ext, **{ext: drawn(lists(4))}), base=eb), ext)[0] == "changed"
    kind, detail = judged(cmp(dict(off_ext, **{ext: drawn(lists(1))}), base=eb), ext)
    assert kind == "worse" and "fewer names" in detail, detail
    kind, detail = judged(cmp(dict(off_ext, **{ext: drawn(lists(4, distinct=False))}), base=eb), ext)
    assert kind == "worse" and "2 different lists" in detail, detail
    # the real list, by chance, in one of 24 draws: every name is left out half the time, so chance
    # gives it (measured on main's 24 draws); in many of them it is worse
    pick = random.Random(5)
    halves = [",".join(x for x in names if pick.random() < 0.5) for _ in range(24)]
    hb = fp_snap(dict(off_ext, **{ext: drawn(halves)}))
    q = nr._real_chance("webgl.extensions", "", halves, REAL_EXT, None)
    assert 1 / 2000 < q < 1 / 50                    # eight names, each shown in about half of main's draws
    assert judged(cmp(dict(off_ext, **{ext: drawn([REAL_EXT] + halves[1:])}), base=hb), ext)[0] == "changed"
    kind, detail = judged(cmp(dict(off_ext, **{ext: drawn([REAL_EXT] * 8 + halves[8:])}), base=hb), ext)
    assert kind == "worse" and "8 of 24 sessions here: more than chance gives" in detail, detail
    # a list that adds names too: how often it adds none is not measured, so never by chance
    assert nr._real_chance("navigator.plugins", "", ["PDF Viewer,A%d" % i for i in range(8)], "PDF Viewer",
                           None) is None
    # the worker's list: measured on the page's extensions of the same level (more draws)
    assert nr._real_chance("worker", "[6][1]", ["B"] * 8, REAL_EXT, None, (halves, REAL_EXT)) == q
    # a single text width: its noise has 61 steps, one of them none; how often the real width comes is
    # measured on main's widths (here 2 of 128 unchanged)
    width, off_width = "fingerprint/strict/fonts_generic", {"fingerprint/off/fonts_generic": fixed([953.5, 960.0])}
    wn = {"widths": 1.5e-06, "widths_share": 0.984375, "widths_k": 1008, "widths_share_k": 1008,
          "widths_least": 0.97, "widths_least_k": 4000}
    sessions = [[953.5 + i / 1e4, 960.0 + i / 1e4] for i in range(1, 9)]
    wb = fp_snap(dict(off_width, **{width: drawn(sessions, wn)}))
    assert 0.01 < nr._real_chance("fonts_generic", "[0]", [], None, wn) < 0.02
    one = [[953.5, 960.0 + 1 / 1e4]] + sessions[1:]
    assert judged(cmp(dict(off_width, **{width: drawn(one, wn)}), base=wb), width)[0] == "changed"
    kind, detail = judged(cmp(dict(off_width, **{width: drawn([[953.5, 960.0 + i / 1e4] for i in range(1, 9)], wn)}),
                               base=wb), width)
    assert kind == "worse" and "[0] the real value (Off's) in 8 of 8 sessions" in detail, detail
    # and a session with no width noise at all: its widths' share is the least, worse
    kind, detail = judged(cmp(dict(off_width, **{width: drawn(one, dict(wn, widths_least=0.0))}), base=wb), width)
    assert kind == "worse" and "widths_least 0.97 on main" in detail, detail
    # where main's widths were not measured, the real width is never chance
    nb = fp_snap(dict(off_width, **{width: drawn(sessions)}))
    assert judged(cmp(dict(off_width, **{width: drawn(one)}), base=nb), width)[0] == "worse"
    # two sessions only: a count cannot be judged, so it is not passed
    assert judged(cmp({"fingerprint/strict/webgl.extensions": disguised("B,C,D,F,G", "A,C,E,F,H")}),
                  "fingerprint/strict/webgl.extensions")[0] == "worse"
    # a large space (random plugin names): fewer fakes added, even by one in every session, is worse
    plug, off_plug = "fingerprint/strict/navigator.plugins", {"fingerprint/off/navigator.plugins": fixed("PDF Viewer")}
    pb = fp_snap(dict(off_plug, **{plug: drawn(["PDF Viewer,A%d,B%d" % (i, i) for i in range(8)])}))
    assert judged(cmp(dict(off_plug, **{plug: drawn(["PDF Viewer,C%d,D%d" % (i, i) for i in range(8)])}), base=pb),
                  plug)[0] == "changed"
    kind, detail = judged(cmp(dict(off_plug, **{plug: drawn(["PDF Viewer,C%d" % i for i in range(8)])}), base=pb),
                          plug)
    assert kind == "worse" and "fewer names" in detail, detail
    # the large spaces must change with the session: alike in two of two is no chance
    for key, value in (("canvas", disguised(["0badc0de", "5a63666b", 140.5159], ["0badc0de", "5a63666b", 140.5154],
                                            CANVAS_NOISE)),
                       ("audio", disguised("172.6715397447", "172.6715397447", AUDIO_NOISE))):
        assert judged(cmp({"fingerprint/strict/" + key: value}), "fingerprint/strict/" + key)[0] == "worse", key
    # fewer sessions measured here than on main: cannot be judged
    report = cmp(dict(off_gpu, **{gpu: disguised(INTEL[0], NVIDIA[0])}), base=base)
    assert judged(report, gpu)[0] == "worse" and "fewer sessions" in judged(report, gpu)[1]
    assert nr._role("canvas", "[0]") == "noise" and nr._role("canvas", "[2]") == "pick"
    assert nr._role("worker", "[6][0]") == "pick" and nr._role("canvas_flat", "") == "noise"
    assert nr._role("screen.width", "") is None and nr._role("navigator.userAgent", "") is None
    assert nr.SESSIONS >= 8 and len(nr.fixed_keys(nr.SESSIONS)) == nr.SESSIONS == len(set(nr.fixed_keys(8)))


def test_a_fixed_disguise_must_not_follow_the_real_machine():
    """Another real environment (time zone, language, screen): a fixed disguise that stays the same
    there is marked env.<value> true; one that follows the real machine, false; main's true must stay."""
    probe = {"navigator": {"languages": "en-US,en"}, "intl": {"timeZone": "UTC"}}
    off = {"navigator": {"languages": "en-US"}, "intl": {"timeZone": "UTC"}}
    env2 = {"levels": {"off": {"probe": {"navigator": {"languages": "de-DE"}, "intl": {"timeZone": "Pacific/Auckland"}}},
                       "maximum": {"probe": {"navigator": {"languages": "en-US,en"}, "intl": {"timeZone": "UTC"}}}}}
    flats = [{"navigator.languages": {"value": "en-US,en"}, "intl.timeZone": {"value": "UTC"}}]
    assert nr._env_marks("maximum", probe, flats, off, env2) == {"navigator.languages": True, "intl.timeZone": True}
    env2["levels"]["maximum"]["probe"]["navigator"]["languages"] = "de-DE,en"
    assert nr._env_marks("maximum", probe, flats, off, env2)["navigator.languages"] is False
    # the same as the real value on this machine, kept on the other one: a fixed disguise too (a real
    # run once missed a copy that made Maximum's languages follow the machine)
    same = {"navigator": {"languages": "en-US,en"}, "intl": {"timeZone": "UTC"}}
    env2["levels"]["maximum"]["probe"]["navigator"]["languages"] = "en-US,en"
    assert nr._env_marks("maximum", same, flats, same, env2) == {"navigator.languages": True, "intl.timeZone": True}
    env2["levels"]["maximum"]["probe"]["navigator"]["languages"] = "de-DE,en"
    assert nr._env_marks("maximum", same, flats, same, env2)["navigator.languages"] is False
    report = cmp({"fingerprint/maximum/env.navigator.languages": mark(False)},
                 base=fp_snap({"fingerprint/maximum/env.navigator.languages": mark(True)}))
    assert keys(report["worse"]) == {"fingerprint/maximum/env.navigator.languages"}
    assert nr._rule("fingerprint/strict/env.screen.width", {"rule": "exact"}, None) == "safer-true"
    assert nr.OTHER_MACHINE["tz"] != "UTC" and not nr.OTHER_MACHINE["lang"].startswith(("C", "en"))


def test_what_cannot_be_judged_stays_worse():
    cases = {
        # main gave the real value: a change of it is at most "neutral", worse with no evidence
        "fingerprint/strict/navigator.hardwareConcurrency": disguised(8, 8),
        # the page could not read it here
        "fingerprint/strict/screen.width": disguised("error TypeError: x", "error TypeError: x"),
        # no second session measured here (main has one), even with the same value
        "fingerprint/strict/navigator.userAgent": {"rule": "fingerprint", "value": COMMON_UA},
        # a fixed disguise of another kind (no number, no text to compare with the real one)
        "fingerprint/strict/webgl.unmasked_renderer": disguised(False, False),
        # a value with a protective direction (no rule says which other value would still protect)
        "fingerprint/strict/storage_quota": fixed(2147483648),
        "page-scriptlets/strict/news/canRunAds": {"rule": "exact", "value": "false"},
    }
    for key, obs in cases.items():
        report = cmp({key: obs})
        assert report["verdict"] == "fail" and keys(report["worse"]) == {key}, (key, report["worse"])
    # the Off level not measured (one level only): a changed value cannot be judged
    off_keys = [k for k in FP_MAIN if k.startswith("fingerprint/off/")]
    report = nr.compare(fp_snap(drop=off_keys), fp_snap(PR148, drop=off_keys), [], None, {})
    assert judged(report, "fingerprint/strict/audio")[0] == "worse"
    # it changes between sessions at Off, on main or here: nothing to tell the protection from
    shaky = {"fingerprint/off/audio": {"rule": "exact", "value": AUDIO_OFF, "session2": "172.6716509662"}}
    assert judged(cmp(dict(PR148, **shaky), base=fp_snap(shaky)), "fingerprint/strict/audio")[0] == "worse"
    assert judged(cmp(dict(PR148, **shaky)), "fingerprint/strict/audio")[0] == "worse"
    # missing here
    report = nr.compare(fp_snap(), fp_snap(drop=["fingerprint/strict/audio"]), [], None, {})
    assert judged(report, "fingerprint/strict/audio")[0] == "worse"
    # the allowlist stays a person's, for a real weakening: an entry accepts it, that change only
    weak = {"fingerprint/strict/audio": disguised(AUDIO_OFF, AUDIO_OFF, {"dispersion": 0.0, "share": 0.0})}
    entries = [{"key": "fingerprint/*/audio", "candidate": AUDIO_OFF, "why": "a test", "accepted": "a person"},
               {"key": "fingerprint/*/canvas", "why": "never used"}]
    report = cmp(weak, entries=entries)
    assert report["verdict"] == "pass" and keys(report["accepted"]) == {"fingerprint/strict/audio"}
    assert [e["key"] for e in report["unused_allowlist"]] == ["fingerprint/*/canvas"]
    assert cmp(PR148, entries=entries)["unused_allowlist"] == entries


def test_the_values_with_a_protective_direction():
    # hidden, refused or native on main must stay so; becoming so is stricter
    for key, value in (("natives.toDataURL", "false:toDataURL:0"), ("keyboard", "map 49")):
        report = cmp({"fingerprint/strict/" + key: fixed(value)})
        assert keys(report["worse"]) == {"fingerprint/strict/" + key} and report["worse"][0]["weakening"], key
    report = cmp({"fingerprint/strict/keyboard": fixed("refused NotAllowedError")})
    assert report["verdict"] == "fail" and not report["worse"][0]["weakening"]   # another refusal: unjudged
    report = cmp(base=fp_snap({"fingerprint/strict/keyboard": fixed("map 49")}),
                 changes={"fingerprint/strict/keyboard": fixed("refused SecurityError")})
    assert keys(report["stricter"]) == {"fingerprint/strict/keyboard"}
    predicates = {name: nr._protective(name) for name in (
        "media_devices", "battery", "webgpu", "storage_quota", "local_fonts", "keyboard", "voices",
        "navigator.webdriver", "natives.getImageData", "third_party", "ike_scheme", "permissions.camera",
        "navigator.bluetooth", "navigator.globalPrivacyControl")}
    assert all(found for found, _test in predicates.values()), predicates
    test = dict((k, t) for k, (_f, t) in predicates.items())
    assert test["media_devices"]("") and test["media_devices"]("audioinput::|videoinput::")
    assert not test["media_devices"]("audioinput:abc:Mic")
    assert test["webgpu"]("no adapter") and not test["webgpu"](["intel/gen-9", ""])
    assert test["navigator.webdriver"](False) and not test["navigator.webdriver"](True)
    assert test["third_party"]("error") and not test["third_party"]("loaded")
    assert test["storage_quota"] is None
    for key in ("fingerprint/strict/media_devices", "fingerprint/strict/natives.x", "page-scriptlets/x/y/z"):
        assert nr._rule(key, {"rule": "exact"}, None) == "protective", key
    assert nr._rule("fingerprint/off/natives.x", {"rule": "exact"}, None) == "exact"


def test_a_snapshot_of_the_older_copy_compares_safely():
    """main measured by a copy of the tool before 2026-11-24 (no second session, no noise size, the
    exact rule everywhere) against a candidate measured by this one: no crash and no false worse."""
    old = fp_snap()
    for k, o in old["observations"].items():
        o.pop("session2", None)
        o.pop("noise", None)
        o["rule"] = "exact"
    report = nr.compare(old, fp_snap(), [], None, {})
    assert report["verdict"] == "pass" and not report["worse"] and not report["changed"], report
    # pull request #148: still noised and different in each session; main's noise size unknown
    report = nr.compare(old, fp_snap(PR148), [], None, {})
    assert report["verdict"] == "pass", report["worse"]
    assert judged(report, "fingerprint/strict/audio")[0] == "changed"
    # what the candidate shows is still judged: the noise off, or the same in every session
    for audio in (disguised(AUDIO_OFF, AUDIO_OFF), disguised("172.6715397447", "172.6715397447")):
        report = nr.compare(old, fp_snap({"fingerprint/strict/audio": audio}), [], None, {})
        assert judged(report, "fingerprint/strict/audio")[0] == "worse", audio
    # the other way round (a candidate measured without a second session while main has one): worse
    # (changed after the independent review of 2026-11-24, which this test once passed: a missing
    # second session hides whether the noise still changes with the session)
    report = nr.compare(fp_snap(), old, [], None, {})
    assert report["verdict"] == "fail"
    assert all("fewer sessions" in r["detail"] for r in report["worse"] if r["rule"] == "fingerprint")


def test_the_rules_of_the_fingerprinting_values():
    assert nr._rule("fingerprint/strict/audio", {"rule": "exact"}, None) == "fingerprint"
    assert nr._rule("fingerprint/strict/canvas.noised", {"rule": "exact"}, None) == "safer-true"
    for mark_key in ("stable.audio", "site.canvas", "canvas_flat.noised"):
        assert nr._rule("fingerprint/strict/" + mark_key, {"rule": "exact"}, None) == "safer-true"
    assert nr._rule("fingerprint/natural/canvas.differs", {"rule": "exact"}, None) == "safer-true"
    assert nr._rule("fingerprint/off/audio", {"rule": "exact"}, None) == "exact"
    for name in ("navigator.doNotTrack", "fonts_check_x", "hints2"):
        assert nr._rule("fingerprint/strict/" + name, {"rule": "exact"}, None) in ("exact", "protective"), name
    for name in ("canvas", "canvas_blob", "canvas_offset", "canvas_flat", "audio", "webgl.unmasked_renderer",
                 "navigator.userAgent", "screen.width", "hints.high", "intl.timeZone", "fonts_measured",
                 "media_queries", "frame", "worker"):
        assert nr.FP_JUDGED.match(name), name
    # the parts of a value
    assert nr._parts("(pointer: fine)=true (hover: hover)=false", "media_queries") == {
        "[(hover: hover)]": "false", "[(pointer: fine)]": "true"}
    assert nr._parts('{"bitness":"64","brands":[{"brand":"A"}]}', "hints.high") == {
        "[bitness]": "64", "[brands][0][brand]": "A"}
    assert nr._parts("x", "screen.width") == {"": "x"}


def png_url(width, rows, filters):
    """A PNG data: address of RGBA rows (lists of bytes), each with its filter type, as a browser writes."""
    import base64 as b64
    import struct
    import zlib

    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xffffffff)
    raw, prev = b"", [0] * (width * 4)
    for row, f in zip(rows, filters):
        enc = []
        for i, v in enumerate(row):
            a = row[i - 4] if i >= 4 else 0
            b, c = prev[i], (prev[i - 4] if i >= 4 else 0)
            p = a + b - c
            pr = a if abs(p - a) <= abs(p - b) and abs(p - a) <= abs(p - c) else b if abs(p - b) <= abs(p - c) else c
            enc.append((v - {0: 0, 1: a, 2: b, 3: (a + b) // 2, 4: pr}[f]) & 255)
        raw += bytes([f] + enc)
        prev = row
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, len(rows), 8, 6, 0, 0, 0)) + \
        chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")
    return "data:image/png;base64," + b64.b64encode(png).decode()


def test_the_size_of_the_noise_is_measured_against_off():
    rows = [[(x * 37 + y * 11 + c) & 255 for x in range(3) for c in range(4)] for y in range(5)]
    url = png_url(3, rows, [0, 1, 2, 3, 4])
    assert nr._png_bytes(url) == bytes(v for r in rows for v in r)
    assert nr._png_bytes("data:image/jpeg;base64,AAAA") is None and nr._png_bytes("x") is None
    noisy = [list(r) for r in rows]
    noisy[2][5] ^= 1
    off = {"png": {"blob": url}, "audio_samples": [0.5, -0.25, 0.125, 0.0], "text_widths": [10.0, 20.0],
           "canvas_pixels": "AAAA"}
    here = {"png": {"blob": png_url(3, noisy, [4] * 5)}, "audio_samples": [0.5005, -0.25, 0.1251, 0.0],
            "text_widths": [10.00001, 20.0], "canvas_pixels": "AAEA"}
    blob = nr._noise("canvas_blob", [here, here], off)
    assert blob["png"] == float("%.6g" % (1 / 60)) and blob["png_share"] == float("%.6g" % (1 / 60))
    assert blob["png_k"] == 2                            # one byte changed in each of two sessions
    # between the sessions: the same noise in both, nothing differs (a noise drawn the same every time)
    assert blob["png_between"] == 0.0
    other = {"png": {"blob": png_url(3, [list(r) for r in rows[:2]] + [[v ^ (i == 1) for i, v in enumerate(rows[2])]]
                                     + [list(r) for r in rows[3:]], [0] * 5)}}
    assert nr._noise("canvas_blob", [here, other], off)["png_between"] == float("%.6g" % (2 / 60))
    size = nr._noise("canvas", [here, here], off)
    assert size["pixels"] == float("%.6g" % (1 / 3)) and size["widths_share"] == 0.5 and size["widths"] > 0
    assert ("png", "png", "known") in nr.NOISE["canvas"] and ("site", "third_frame", None) in nr.NOISE["canvas"]
    assert nr.NOISE["canvas_flat"] == (("stripes", "canvas_flat_pixels", None),)
    # the flat stripes: the rows (16 pixels each) changed at all
    import base64 as b64
    flat_off = {"canvas_flat_pixels": b64.b64encode(bytes(64 * 4)).decode()}
    flat_here = {"canvas_flat_pixels": b64.b64encode(bytes(64) + bytes([1]) + bytes(63) + bytes(128)).decode()}
    stripes = nr._noise("canvas_flat", [flat_here, flat_here], flat_off)
    assert stripes["stripes"] == 0.25 and stripes["stripes_between"] == 0.0
    audio = nr._noise("audio", [here], off)
    assert audio["share"] == 0.5 and audio["dispersion"] > 0
    # a constant gain: every sample changed, no dispersion
    gain = {"audio_samples": [0.5 * 1.001, -0.25 * 1.001, 0.125 * 1.001, 0.0]}
    assert nr._noise("audio", [gain], off) == {"dispersion": 0.0, "share": 0.75, "dispersion_k": 3, "share_k": 3}
    # what cannot be measured is None, never 0
    assert nr._noise("audio", [{"audio_samples": [1.0]}], off) == {"dispersion": None, "share": None}
    assert nr._noise("canvas", [{}], off)["pixels"] is None
    # the session with the fewest widths changed: one session with no width noise is 0 there
    widths = nr._noise("fonts_generic", [here, here, {"text_widths": [10.0, 20.0]}], off)
    assert widths["widths_least"] == 0.0 and widths["widths_share"] == float("%.6g" % (1 / 3))
    assert nr._noise("fonts_generic", [here, here], off)["widths_least"] == 0.5
    # the real values the noise is measured against: the same on both sides, or it cannot be compared
    assert nr._samples_ref("audio", off) != nr._samples_ref("audio", dict(off, audio_samples=[0.5, -0.25, 0.126, 0.0]))
    ref = {"fingerprint/off/audio": dict(fixed(AUDIO_OFF), samples_ref="a")}
    report = cmp(dict(PR148, **{"fingerprint/off/audio": dict(fixed(AUDIO_OFF), samples_ref="b")}),
                 base=fp_snap(ref))
    kind, detail = judged(report, "fingerprint/strict/audio")
    assert kind == "worse" and "cannot be compared" in detail, detail
    # the tolerance: NOISE_Z (4) times the chance spread of two draws, never below 20 %;
    # one-sided chance of a false "worse" per measure 3e-5
    import math
    assert abs(0.5 * math.erfc(nr.NOISE_Z / 2 ** 0.5) - 3.17e-05) < 1e-06
    assert nr._tolerance("pixels", {"pixels": 0.0146, "pixels_k": 1076}) == 0.2
    assert round(nr._tolerance("pixels", {"pixels": 0.0144, "pixels_k": 265}), 3) == 0.347
    assert round(nr._tolerance("widths", {"widths": 1.5e-06, "widths_k": 251}), 3) == 0.214
    assert nr._tolerance("dispersion", {"dispersion": 5e-05, "dispersion_k": 1000}) == 0.2
    assert nr._tolerance("pixels", {"pixels": 0.01, "pixels_k": 30}) == nr.TOLERANCE_CAP == 0.35   # never looser
    assert nr._tolerance("pixels", {"pixels": 0.01}) == 0.2                 # no count known: 20 %
    floors = nr.load_floors()
    assert floors["audio"]["dispersion"] > 0 and set(floors) <= set(nr.NOISE)
    assert nr.load_floors(ROOT / "missing.json") is None


# --- evidence: a needed change passes by itself, a weakening never (2026-11-24) ---------------------
N3 = "tests/test_review_fixes.py::test_n3_repeated_reads_or_a_known_buffer_do_not_remove_the_noise"
FP_JS = "ike/resources/fingerprint.js"
BOUND = {"test": N3, "keys": ["fingerprint/*/navigator.hardwareConcurrency"], "files": [FP_JS], "why": "a test"}


def needed(test=N3, main="failed", here="passed", changed=(FP_JS,), bound=(BOUND,), confirmed=None, **more):
    """Evidence: `test` in main's results and here, confirmed by running it again, a person's binding."""
    ev = {"main_tests": {test: main} if main else {}, "candidate_tests": {test: here} if here else {},
          "changed": list(changed), "necessity": [dict(b) for b in bound],
          "confirmed": {test} if confirmed is None else set(confirmed)}
    ev.update(more)
    return ev


# a value main left real that this change makes differ, in both sessions: the one neutral kind
NEUTRAL = {"fingerprint/strict/navigator.hardwareConcurrency": disguised(8, 8)}


def test_a_needed_change_passes_by_itself_only_with_a_bound_confirmed_test():
    report = cmp(NEUTRAL)
    row = report["worse"][0]
    assert report["verdict"] == "fail" and row["weakening"] is False and row["neutral"] is True
    assert "a test bound to it" in nr.markdown(report)
    report = cmp(NEUTRAL, evidence=needed())
    assert report["verdict"] == "pass", report["worse"]
    row = report["evidence"][0]
    assert row["key"] == "fingerprint/strict/navigator.hardwareConcurrency" and row["passed_by"] == "necessity"
    assert N3 in row["why"] and FP_JS in row["why"] and "confirmed 3 times" in row["why"], row["why"]
    assert report["evidence_read"]["fixed_tests"] == [N3]
    text = nr.markdown(report)
    assert text.startswith("### Nothing gets worse\n\n**Passed, 1 by evidence**")
    assert "#### Passed by evidence, with no person" in text and "fixed here and confirmed" in text


def test_what_is_not_evidence_of_need():
    other = dict(BOUND, test="tests/test_downloads.py::test_a_download_is_saved")
    cases = {
        "a test not confirmed by running it again": needed(confirmed=()),
        "a test whose own file the change rewrote": needed(changed=(FP_JS, N3.split("::")[0])),
        "a test no person bound to the value": needed(bound=()),
        "a test bound to another value": needed(bound=(dict(BOUND, keys=["fingerprint/*/screen.width"]),)),
        "a binding of another test": needed(bound=(other,)),
        "a change that does not touch the binding's files": needed(changed=("ike/newtab.py",)),
        "no change known": needed(changed=()),
        "a test that fails here too": needed(here="failed"),
        "a test skipped here": needed(here="skipped"),
        "a test that passes on main": needed(main="passed"),
        "a test main does not have": needed(main=None),
        "a test this commit does not have": needed(here=None),
        "a binding for the Off level only": needed(bound=(dict(BOUND, keys=[
            "fingerprint/off/navigator.hardwareConcurrency"]),)),
    }
    for what, ev in cases.items():
        report = cmp(NEUTRAL, evidence=ev)
        assert report["verdict"] == "fail" and not report["evidence"], what
    # more values than NECESSITY_CAP claimed by one test: none of them
    many = {"fingerprint/%s/navigator.hardwareConcurrency" % lv: disguised(8, 8)
            for lv in ("compatibility", "balanced", "strict", "maximum", "x1")}
    base = fp_snap({k: disguised(4, 4) for k in many})
    report = cmp(many, base=base, evidence=needed())
    assert len(many) > nr.NECESSITY_CAP and not report["evidence"] and len(report["worse"]) == len(many)
    # a person's binding of the strict form only: exact test ids, keys with at most the level open
    for bad in ({"test": "*::*noise*"}, {"keys": ["fingerprint/*/*"]}, {"keys": ["fingerprint-config/*/x"]},
                {"keys": ["security/x/y"]}, {"files": ["ike/*"]}, {"files": ["tests/x.py"]}, {"why": ""}):
        assert nr.load_necessity_from([dict(BOUND, **bad)]) == [], bad
    assert nr.load_necessity_from([BOUND]) == [BOUND]
    assert nr.load_necessity() == [] or all(e["test"].startswith("tests/") for e in nr.load_necessity())


def test_no_evidence_ever_accepts_a_weakening():
    """An AI fix that turns a protection off and also makes a failing test pass (bound, confirmed,
    touching the files) is still worse; so is what the rules cannot judge."""
    weak = {"fingerprint/strict/audio": disguised(AUDIO_OFF, AUDIO_OFF, {"dispersion": 0.0, "share": 0.0}),
            "fingerprint/strict/audio.noised": mark(False),
            "fingerprint/strict/screen.width": disguised(2560, 2560),
            "fingerprint/strict/natives.toDataURL": fixed("false:toDataURL:0"),
            "fingerprint/strict/stable.audio": mark(False)}
    every = [dict(BOUND, keys=["fingerprint/*/" + k.split("/", 2)[2]]) for k in list(weak) + list(NEUTRAL)]
    report = cmp(dict(NEUTRAL, **weak), evidence=needed(bound=every))
    assert keys(report["worse"]) == set(weak), report["worse"]
    assert all(r["weakening"] for r in report["worse"])
    assert keys(report["evidence"]) == set(NEUTRAL)
    # what cannot be judged (not measured, could not be read, a protective value, the pages'
    # scriptlets): never accepted by evidence either
    unjudged = {"fingerprint/strict/screen.width": disguised("error x", "error x"),
                "fingerprint/strict/storage_quota": fixed(1),
                "fingerprint/strict/keyboard": fixed("refused NotAllowedError"),
                "page-scriptlets/strict/news/canRunAds": {"rule": "exact", "value": "false"}}
    every = [dict(BOUND, keys=["fingerprint/*/" + k.split("/", 2)[2]]) for k in unjudged if k.startswith("fing")]
    report = cmp(unjudged, evidence=needed(bound=every))
    assert keys(report["worse"]) == set(unjudged) and not report["evidence"]
    # a part that cannot be judged does not hide a smaller noise
    canvas = {"fingerprint/strict/canvas": disguised(["0badc0de", "0ddba11", 140.5159], ["1badc0de", "0ddba11",
                                                                                         140.5154],
                                                     dict(CANVAS_NOISE, pixels=0.001))}
    report = cmp(canvas, evidence=needed(bound=[dict(BOUND, keys=["fingerprint/*/canvas"])]))
    assert report["worse"][0]["weakening"] and "noise is smaller" in report["worse"][0]["detail"], report["worse"]
    # every kind of regression of the hand-made snapshot, with every test fixed and every file changed
    everything = needed(changed=(FP_JS, "ike/shields.py", "ike/blocker.py", "ike/app.py", "ike/config.py"),
                        bound=[dict(BOUND, keys=["fingerprint/*/navigator.hardwareConcurrency",
                                                 "fingerprint/*/canvas.noised"])])
    base = snap(**BASE)
    report = nr.compare(base, with_values(base, WORSE), [], everything, {})
    assert keys(report["worse"]) == {k.replace("__", "/") for k in WORSE} and not report["evidence"]
    # a security setting the rules cannot judge (a header): no exceptions
    referer = {"headers__strict__third-party__referer": "http://127.0.0.1:PORT/other"}
    report = nr.compare(base, with_values(base, referer), [], everything, {})
    assert report["verdict"] == "fail" and report["worse"][0]["weakening"] is False
    assert "only a person accepts it" in nr.markdown(report)


def test_a_test_counts_only_when_it_fails_on_main_and_passes_here_every_time():
    calls = []

    def runner(codes):
        def run(repo, test):
            calls.append((repo, test))
            return codes[repo].pop(0)
        return run
    for main, here, ok in (([1, 1, 1], [0, 0, 0], True),       # fails 3/3 on main, passes 3/3 here
                           ([1, 0, 1], [0, 0, 0], False),      # main fails by chance
                           ([1, 1, 1], [0, 1, 0], False),      # here passes by chance
                           ([1, 1, 1], [0, 0, None], False),   # a run that did not end
                           ([5, 5, 5], [0, 0, 0], False)):     # no such test on main
        record, confirmed = nr.confirm(["t"], "main", "here", runs=3, run=runner({"main": list(main),
                                                                                 "here": list(here)}))
        assert (confirmed == {"t"}) is ok, (main, here, record)
    assert nr.CONFIRM_RUNS == 3


def request_snap(value, lists, data):
    s = snap(**{"requests__balanced__ad-x": ("block", value)})
    if lists is not None:
        s["observations"]["requests/balanced/ad-x"]["lists"] = lists
    s["list_data"] = data
    return s


EASY = "https://easylist.to/easylist/easylist.txt"
UNBREAK = "https://ublockorigin.github.io/uAssets/filters/unbreak.txt"
BLOCKED = {"verdict": "block", "rule": "||ads.example^", "rule_list": EASY, "exception": None, "exception_list": None}
GONE = {"verdict": "allow", "rule": None, "rule_list": None, "exception": None, "exception_list": None}
EXCEPTED = {"verdict": "allow", "rule": "||ads.example^", "rule_list": EASY, "exception": "@@||ads.example/player.js",
            "exception_list": UNBREAK}
DATA = {EASY: "e1", UNBREAK: "u1"}


def test_a_request_let_through_passes_only_when_the_list_data_decides():
    base = request_snap("block", BLOCKED, DATA)
    # the rule is gone from the list's new data
    report = nr.compare(base, request_snap("allow", GONE, dict(DATA, **{EASY: "e2"})), [])
    assert report["verdict"] == "pass" and report["evidence"][0]["passed_by"] == "lists"
    assert "||ads.example^" in report["evidence"][0]["why"] and EASY in report["evidence"][0]["why"]
    # an exception in a list's new data
    report = nr.compare(base, request_snap("allow", EXCEPTED, dict(DATA, **{UNBREAK: "u2"})), [])
    assert report["verdict"] == "pass" and "@@||ads.example/player.js" in report["evidence"][0]["why"]
    worse = {
        "the list data the same (an engine or code change)": request_snap("allow", GONE, DATA),
        "the exception's list the same": request_snap("allow", EXCEPTED, dict(DATA, **{EASY: "e2"})),
        "another list changed": request_snap("allow", GONE, dict(DATA, **{UNBREAK: "u2"})),
        "the lists still stop it (I.K.E.'s own code let it through)": request_snap("allow", BLOCKED,
                                                                                   dict(DATA, **{EASY: "e2"})),
        "not let through but redirected elsewhere": request_snap("redirect https://x.example/", GONE,
                                                                 dict(DATA, **{EASY: "e2"})),
        "no list verdicts (an older snapshot)": request_snap("allow", None, dict(DATA, **{EASY: "e2"})),
    }
    for what, cand in worse.items():
        report = nr.compare(base, cand, [], needed(changed=("ike/blocker.py",)))
        assert report["verdict"] == "fail" and report["worse"][0]["weakening"], what
    # main blocked it by I.K.E.'s own rules, not the lists: the lists cannot let it through
    report = nr.compare(request_snap("block", GONE, DATA), request_snap("allow", GONE, dict(DATA, **{EASY: "e2"})), [])
    assert report["verdict"] == "fail"


def test_a_new_host_passes_only_declared_and_named_by_this_change():
    base = snap(**{"network__fresh-profile": ("no-new", ["easylist.to"])})
    cand = with_values(base, {"network__fresh-profile": ["easylist.to", "updates.example"]})
    declared = [{"host": "updates.example", "purpose": "I.K.E.'s update check", "key": "network/fresh-profile"}]
    diff = ("diff --git a/ike/updater.py b/ike/updater.py\n--- a/ike/updater.py\n+++ b/ike/updater.py\n"
            "@@ -1 +1 @@\n-URL = None\n+URL = 'https://updates.example/latest.json'\n")
    changed, added = nr.read_diff(diff)
    report = nr.compare(base, cand, [], {"endpoints": declared, "changed": changed, "added": added})
    assert report["verdict"] == "pass" and report["evidence"][0]["passed_by"] == "registry"
    assert "updates.example, I.K.E.'s update check" in report["evidence"][0]["why"]
    other = with_values(base, {"network__fresh-profile": ["easylist.to", "updates.example", "telemetry.example"]})
    in_a_comment = diff.replace("+URL = ", "+# URL = ")
    for what, c, ev in (
            ("not declared", cand, {"endpoints": [], "added": added}),
            ("declared for another observation", cand, {"endpoints": [dict(declared[0], key="network/while-measuring")],
                                                       "added": added}),
            ("not named by the change", cand, {"endpoints": declared, "added": "x = 1"}),
            ("only a longer name", cand, {"endpoints": declared, "added": "'https://updates.example.evil.test/'"}),
            ("only a name ending with it", cand, {"endpoints": declared, "added": "'https://myupdates.example/'"}),
            ("named only in tests/", cand, {"endpoints": declared, "added": nr.read_diff(
                diff.replace("ike/updater.py", "tests/test_updater.py"))[1]}),
            ("named only in a tool", cand, {"endpoints": declared, "added": nr.read_diff(
                diff.replace("ike/updater.py", "tools/x.py"))[1]}),
            ("named only in a comment", cand, {"endpoints": declared, "added": nr.read_diff(in_a_comment)[1]}),
            ("the change not known", cand, {"endpoints": declared}),
            ("one of two not declared", other, {"endpoints": declared, "added": added + " telemetry.example"}),
            ("a test fixed (no evidence for a host)", cand, needed(changed=("ike/updater.py",)))):
        report = nr.compare(base, c, [], ev)
        assert report["verdict"] == "fail" and report["worse"][0]["weakening"], what
    # the registry: entries default to the fresh profile, exact hosts only; main's is empty (a host main
    # already contacts is not new)
    assert nr.load_endpoints(nr.ENDPOINTS) == []
    path = ROOT / "tests" / "data" / "no-regression" / "endpoints.json"
    assert "Only a person" in json.loads(path.read_text("utf-8"))["about"]
    assert nr.load_endpoints(ROOT / "missing.json") == []


def test_the_security_settings_have_no_exceptions():
    base = snap(**BASE)
    everything = needed("tests/test_security.py::test_fp_noise_scriptlet",
                        changed=("ike/app.py", "ike/shields.py", "ike/config.py", FP_JS))
    for key in ("switches__added", "webengine__balanced__page__JavascriptCanOpenWindows",
                "webengine__balanced__page__AutoLoadImages", "defaults__https_only",
                "permissions__balanced__geolocation", "headers__strict__third-party__referer"):
        report = nr.compare(base, with_values(base, {key: WORSE[key]}), [], everything)
        assert report["verdict"] == "fail" and not report["evidence"], key
    report = nr.compare(base, with_values(base, {"defaults__shield_level": "strict"}), [], everything)
    assert report["verdict"] == "pass" and "the rule `level`: a higher protection level" in report["stricter"][0]["why"]


def test_the_report_says_why_each_difference_passed(capsys, monkeypatch):
    base = snap(**BASE)
    cand = with_values(base, dict(STRICTER, **{"requests__balanced__ad-gpt": "redirect-data",
                                               "fingerprint__strict__navigator.hardwareConcurrency": 8}))
    entries = [{"key": "fingerprint/*/navigator.hardwareConcurrency", "why": "a person read it", "accepted": "x"}]
    report = nr.compare(base, cand, entries)
    assert report["verdict"] == "pass"
    for kind in ("evidence", "accepted", "stricter", "changed"):
        for r in report[kind]:
            assert r["why"] and r["passed_by"] in ("rule", "necessity", "lists", "registry", "person"), r
    assert report["accepted"][0]["passed_by"] == "person"
    text = nr.markdown(report)
    assert "(accepted: a person read it)" in text and "(passed: the rule `block`: still stopped" in text
    assert "| What | Compared | Worse | Passed by evidence | Accepted by a person | Stricter | Changed |" in text
    assert "the files of this change not known" in text and text.startswith("### Nothing gets worse\n\n**Passed**:")
    # a worse row says whether it is weaker or cannot be judged
    report = nr.compare(base, with_values(base, {"requests__balanced__ad-gpt": "allow"}))
    assert "allowed here (weaker)" in nr.markdown(report)
    # on GitHub, what passed by evidence is also one notice of the run (the signing notice reads it)
    report = cmp(NEUTRAL, evidence=needed())
    args = type("A", (), {"json": None, "markdown": None})()
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    assert nr._finish(report, args) == 0
    out = capsys.readouterr().out
    assert out.startswith("::notice title=%s::1 passed by evidence: fingerprint/strict/navigator.hardwareConcurrency"
                          " (necessity): needed" % nr.EVIDENCE_TITLE) and out.count("\n") == 2
    monkeypatch.delenv("GITHUB_ACTIONS")
    nr._finish(report, args)
    assert "::notice" not in capsys.readouterr().out


def test_the_evidence_is_read_from_junit_and_diff(tmp_path):
    main_xml, here_xml = tmp_path / "main.xml", tmp_path / "here.xml"
    main_xml.write_text(
        '<testsuites><testsuite><testcase classname="tests.test_review_fixes" name="test_n3_noise">'
        '<failure message="x"/></testcase><testcase classname="tests.test_a" name="test_ok"/>'
        '<testcase classname="tests.test_a.TestB" name="test_c"><error/></testcase></testsuite></testsuites>')
    here_xml.write_text(
        '<testsuites><testsuite><testcase classname="tests.test_review_fixes" name="test_n3_noise"/>'
        '<testcase classname="tests.test_a" name="test_ok"><skipped/></testcase></testsuite></testsuites>')
    installed = tmp_path / "installed.xml"
    installed.write_text('<testsuites><testsuite><testcase classname="tests.test_a" name="test_ok"/>'
                         '</testsuite></testsuites>')
    assert nr.read_junit([main_xml]) == {"tests/test_review_fixes.py::test_n3_noise": "failed",
                                         "tests/test_a.py::test_ok": "passed", "tests/test_a.py::test_c": "failed"}
    assert nr.read_junit([here_xml, installed, tmp_path / "missing.xml"])["tests/test_a.py::test_ok"] == "passed"
    diff = ("diff --git a/ike/resources/fingerprint.js b/ike/resources/fingerprint.js\n"
            "--- a/ike/resources/fingerprint.js\n+++ b/ike/resources/fingerprint.js\n@@ -1 +1 @@\n-a\n+b\n"
            "diff --git a/ike/x.py b/ike/x.py\n--- a/ike/x.py\n+++ b/ike/x.py\n@@ -1 +1,2 @@\n-a\n+u = 1\n+# c\n"
            "diff --git a/tests/test_x.py b/tests/test_x.py\n--- /dev/null\n+++ b/tests/test_x.py\n@@ -0,0 +1 @@\n+t\n"
            "diff --git a/ike/old.py b/ike/old.py\n--- a/ike/old.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-gone\n")
    assert nr.read_diff(diff) == (["ike/old.py", "ike/resources/fingerprint.js", "ike/x.py", "tests/test_x.py"],
                                  "u = 1")
    # the whole way from the command line: the neutral change passes with a bound, confirmed test
    test = "tests/test_review_fixes.py::test_n3_noise"
    base, cand = tmp_path / "base.json", tmp_path / "cand.json"
    base.write_text(json.dumps(fp_snap()))
    cand.write_text(json.dumps(fp_snap(NEUTRAL)))
    (tmp_path / "change.diff").write_text(diff)
    allow, bound = tmp_path / "allow.json", tmp_path / "necessity.json"
    allow.write_text(json.dumps({"entries": []}))
    bound.write_text(json.dumps({"entries": [dict(BOUND, test=test)]}))
    argv = ["compare", "--base", str(base), "--candidate", str(cand), "--allowlist", str(allow),
            "--necessity", str(bound), "--json", str(tmp_path / "r.json"), "--main-junit", str(main_xml),
            "--candidate-junit", str(here_xml), "--diff", str(tmp_path / "change.diff")]
    assert nr.main(argv) == 1                                     # not confirmed by running it again
    assert nr.main(argv + ["--confirmed", test]) == 0
    report = json.loads((tmp_path / "r.json").read_text())
    assert report["evidence"][0]["passed_by"] == "necessity" and report["evidence_read"]["changed_files"] == 4


def test_the_masked_fonts_are_judged_by_what_protects():
    """fingerprint-config/<level>/fonts is the digest of the names fingerprint.js masks: they follow the
    computer's fonts and when its check answered, so two runs of the same code can differ (pull request
    #155, which touches no browser code, failed on it: a list on main, no answer yet here). Judged by
    what protects: every font a page can find, measured by the tool in the same run, is masked."""
    import hashlib

    def fonts(masked, findable, listed=None):
        o = {"rule": "exact", "value": "sha256 " + hashlib.sha256(json.dumps(masked).encode()).hexdigest()[:16],
             "masked": masked, "findable": findable}
        if masked is None:
            o["listed"] = listed
        return o
    key = "fingerprint-config/maximum/fonts"
    assert nr._rule(key, {"rule": "exact"}, None) == "fonts"           # the tool's own rule, whatever is carried
    main = fonts(["DejaVu Sans", "Liberation Sans"], ["DejaVu Sans", "Liberation Sans", "Arial"])
    base = fp_snap({key: main})
    # two different lists, as two computers or two answers give: each masks every font found there
    other = fonts(["Noto Color Emoji", "DejaVu Sans", "Liberation Sans"],
                  ["Noto Color Emoji", "DejaVu Sans", "Liberation Sans", "Courier New"])
    report = cmp({key: other}, base=base)
    kind, detail = judged(report, key)
    assert kind == "changed" and "every font a page can find is masked" in detail and report["verdict"] == "pass"
    # the case of #155: no answer yet here, so fingerprint.js's whole list is masked
    listed = ["DejaVu Sans", "Liberation Sans", "Noto Color Emoji", "Ubuntu"]
    assert judged(cmp({key: fonts(None, ["DejaVu Sans", "Liberation Sans"], listed)}, base=base), key)[0] == "changed"
    # a font a page can find left unmasked: worse (a shorter list, or the whole list without an installed family)
    kind, detail = judged(cmp({key: fonts(["DejaVu Sans"], ["DejaVu Sans", "Liberation Sans"])}, base=base), key)
    assert kind == "worse" and "not masked: liberation sans" in detail, detail
    kind, detail = judged(cmp({key: fonts(None, ["DejaVu Sans", "IPAGothic"], listed)}, base=base), key)
    assert kind == "worse" and "ipagothic" in detail, detail
    # one unmasked on main, none here: stricter
    loose = fp_snap({key: fonts(["DejaVu Sans"], ["DejaVu Sans", "Liberation Sans"])})
    assert judged(cmp({key: main}, base=loose), key)[0] == "stricter"
    # not measured here where main measured it: cannot be judged, so worse
    kind, detail = judged(cmp({key: {"rule": "exact", "value": other["value"], "masked": other["masked"]}},
                              base=base), key)
    assert kind == "worse" and "not measured here" in detail, detail
    # older snapshots with no measure on either side: the digest, as before
    old = {"rule": "exact", "value": main["value"]}
    assert judged(cmp({key: {"rule": "exact", "value": other["value"]}}, base=fp_snap({key: old})), key)[0] == "worse"
    assert judged(cmp({key: dict(old)}, base=fp_snap({key: old})), key)[0] == "same"


# a page script as fingerprint.js is built (the parts the fourth review's copies changed)
PAGE_OLD = """(function () {
  var CFG = __IKE_CFG__;
  var host = location.hostname;
  var MASKED_FONTS = ["Arial Black", "Calibri"];
  var MASKED = (CFG.fonts instanceof Array) ? CFG.fonts : MASKED_FONTS;
  var hiddenExt = {};
  function siteOf(h) {
    var p = h.split('.');
    return p.slice(-2).join('.');
  }
  function noiseImage(img) {
    var px = pixels(img), tag = TAG(px);
    if (tag === 'Uint8ClampedArray') farble(px, seed, rng, LEN(px));
  }
  function install(w) {
    if (!w || isProtected(w)) return;
    var doc = w.document;
    [w.WebGLRenderingContext, w.WebGL2RenderingContext].forEach(function (GL) {
      if (!GL) return;
      wrap(GL.prototype, 'getParameter', function (orig) {
        return function (p) { return RAPPLY(orig, this, [p]); };
      });
    });
  }
  install(window);
})();
"""


def test_the_guard_refuses_the_added_lines_that_weakened_the_fingerprinting():
    """The fourth review (2026-11-24): copies made of added lines only weakened the fingerprinting and
    tools/fix-guard.py accepted them. In I.K.E.'s page scripts a new line may not leave code but inside a
    function the change adds, read where or when the page is, or change (or delete from) an object the old
    script has. Each copy below was accepted before (fails on main's guard) and is refused now."""
    guard = load("fix-guard")
    name = "ike/resources/fingerprint.js"
    copies = {
        # vS: the noise left out on a few top-level domains
        "vS": ("    var px = pixels(img), tag = TAG(px);\n", "    var px = pixels(img), tag = TAG(px);\n"
               "    if (/\\\\.(com|org|net|it)$/.test(location.hostname)) {\n      return;\n    }\n"),
        # vF: eleven installed families taken out of the masked names at run time
        "vF": ("  var hiddenExt = {};\n", "  var hiddenExt = {};\n  if (MASKED.length > 11) MASKED.splice(0, 11);\n"),
        # a constant site, WebGL2 skipped, sub-frames skipped, hidden extensions shown, a site exempted
        "siteOf": ("    var p = h.split('.');\n", "    if (h) {\n      return 'web';\n    }\n    var p = h.split('.');\n"),
        "WebGL2": ("      if (!GL) return;\n", "      if (!GL) return;\n      if (GL === w.WebGL2RenderingContext) {\n"
                   "        return;\n      }\n"),
        "frames": ("    var doc = w.document;\n", "    var doc = w.document;\n    if (w !== window) {\n      return;\n    }\n"),
        "hiddenExt": ("  var hiddenExt = {};\n", "  var hiddenExt = {};\n  for (var k in hiddenExt) delete hiddenExt[k];\n"),
        "nofp": ("  var host = location.hostname;\n", "  var host = location.hostname;\n  if (CFG.nofp) CFG.nofp.push(host);\n"),
        "time": ("  var hiddenExt = {};\n", "  var hiddenExt = {};\n  var late = new Date().getHours() > 22;\n"),
        "chance": ("  var hiddenExt = {};\n", "  var hiddenExt = {};\n  var coin = Math.random() < 0.5;\n"),
    }
    for what, (old, new) in copies.items():
        assert PAGE_OLD.count(old) == 1, what
        problems = guard.file_problems(name, PAGE_OLD, PAGE_OLD.replace(old, new))
        assert problems, what
    # a new helper with its own exits, a new wrap: still accepted (only what the rules name is refused)
    helper = PAGE_OLD.replace("  var hiddenExt = {};\n", "  var hiddenExt = {};\n  function clamp(v) {\n"
                              "    if (v < 0) {\n      return 0;\n    }\n    return v;\n  }\n")
    assert guard.file_problems(name, PAGE_OLD, helper) == []
    wrap_more = PAGE_OLD.replace("  install(window);\n", "  [1, 2].forEach(function (n) {\n    if (!n) {\n"
                                 "      return;\n    }\n    wrap(n, 'x', function (orig) { return orig; });\n  });\n"
                                 "  install(window);\n")
    assert guard.file_problems(name, PAGE_OLD, wrap_more) == []
    # the rules are for I.K.E.'s page scripts: rule 5 as before elsewhere
    assert "ike/resources/fingerprint.js" in guard.PROTECTED_JS


def test_the_reviewers_see_the_fingerprinting_rows():
    """N5: what "Nothing gets worse" found changed in the fingerprinting on an AI's commit is added to what
    the two reviewers read (the artifact tests-checks of its run of tests.yml)."""
    import io
    import zipfile
    review = load("ai-review")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("no-regression/report.json", json.dumps({"fingerprint_review": [
            {"key": "fingerprint/strict/canvas", "detail": "the noise is smaller", "passed_by": ""}]}))

    def api(path, raw=False):
        if "actions/runs?head_sha=" in path:
            return {"workflow_runs": [{"id": 5, "path": ".github/workflows/arch.yml"},
                                      {"id": 6, "path": ".github/workflows/tests.yml"}]}
        if "/runs/6/artifacts?name=tests-checks" in path:
            return {"artifacts": [{"id": 9}]}
        if path.endswith("/artifacts/9/zip"):
            return buf.getvalue()
        raise AssertionError(path)
    text = review.fingerprint_rows("o/r", "a" * 40, api)
    assert text.startswith(review.FINGERPRINT_TITLE) and "fingerprint/strict/canvas: the noise is smaller" in text

    def down(path, raw=False):
        raise RuntimeError("down")
    assert review.fingerprint_rows("o/r", "a" * 40, down) == ""


def test_the_fourth_review_sites_keys_frames_and_fonts():
    """The fourth review's measures, as judged: N1 (the sites: other sites differ, under a public suffix of
    two labels too, two hosts of one site agree, every host noised), N2 (the first key again in another
    load; a large space drawn from a few keys; the frame's canvas the page's), N4 (the fonts a page can find
    still found in the protected page), N7 (a pick the same in every session is a fixed disguise for the
    other machine)."""
    # N1: one key for every site (vE): the sites alike; a host of one site with another noise; a TLD skipped
    real = {"pic": "p0", "url": "u0", "audio": "a0", "gl": "g0", "width": "w0"}
    good = {n: {v: "%s-%s" % (v, n if n != "a2" else "a") for v in nr.SITE_READS} for n in ("a", "a2", "b", "c", "d", "e")}
    marks = nr._site_marks(good, {"a": real})
    assert all(marks["sites.%s.%s" % (m, v)]["value"] is True for m in ("differ", "agree", "noised") for v in nr.SITE_READS)
    same = {n: {v: "%s-x" % v for v in nr.SITE_READS} for n in good}
    assert nr._site_marks(same, {"a": real})["sites.differ.pic"]["value"] is False            # vE
    psl = dict(good, c=dict(good["b"]))                     # x.co.uk and y.co.uk taken as one site
    assert nr._site_marks(psl, {"a": real})["sites.differ.audio"]["value"] is False
    split = dict(good, a2=dict(good["d"]))
    assert nr._site_marks(split, {"a": real})["sites.agree.gl"]["value"] is False
    skipped = dict(good, d=dict(real))                      # vS: the .com host left unnoised
    assert nr._site_marks(skipped, {"a": real})["sites.noised.pic"]["value"] is False
    assert nr._site_marks(dict(good, e=None), {"a": real})["sites.differ.pic"]["value"] is None   # not read
    key = "fingerprint/strict/sites.differ.pic"
    assert nr._rule(key, {"rule": "x"}, None) == "safer-true"
    assert judged(cmp({key: {"rule": "safer-true", "value": False}},
                      base=fp_snap({key: {"rule": "safer-true", "value": True}})), key)[0] == "worse"
    names = nr.run_names()
    s = names["sites"]
    assert s["a2"].endswith("." + s["a"]) and s["b"].endswith(".co.uk") and s["c"].endswith(".co.uk")
    assert s["b"] != s["c"] and s["d"].endswith(".com") and s["e"].rsplit(".", 1)[1] != s["a"].rsplit(".", 1)[1]
    assert not any(h.endswith((".example", ".test", ".localhost")) or h[0].isdigit() for h in s.values())
    assert not names["third"].endswith(".example")
    # N2: the first key again: a value read another way in another load is worse (vC); sessions of a large
    # space alike where main's all differed (vD); the frame's canvas no longer the page's
    here = {"probe_again": {"audio": "171.5", "canvas": ["h1", "x", 1.0]}}
    fp = {"audio": {"value": "171.4"}, "canvas": {"value": ["h1", "x", 1.0]}}
    errs = []
    assert nr._again_marks("strict", here, fp, errs) == {
        "again.audio": {"rule": "safer-true", "value": False}, "again.canvas": {"rule": "safer-true", "value": True}}
    assert nr._again_marks("strict", {"probe_again": None}, fp, errs) == {} and errs
    hashes = ["%08x" % (i * 2654435761 % 2 ** 32) for i in range(8)]
    canvas, off_canvas = "fingerprint/strict/canvas", {"fingerprint/off/canvas": fixed(CANVAS_OFF)}
    cb = fp_snap(dict(off_canvas, **{canvas: drawn([[h, "5a63666b", 140.515625] for h in hashes], CANVAS_NOISE)}))
    few = [[hashes[i % 3], "5a63666b", 140.515625] for i in range(8)]
    kind, detail = judged(cmp(dict(off_canvas, **{canvas: drawn(few, CANVAS_NOISE)}), base=cb), canvas)
    assert kind == "worse" and "only 3 different in 8 sessions here (on main all 8 differed)" in detail, detail
    assert nr._frame_agrees([{"frame": [4, "ua", 2, 800, ["h1", "x", 1]], "canvas": ["h1", "x", 1]}]) is True
    assert nr._frame_agrees([{"frame": [4, "ua", 2, 800, ["h2", "x", 1]], "canvas": ["h1", "x", 1]}]) is False
    assert nr._frame_agrees([{"frame": "error", "canvas": ["h1"]}]) is None
    # N4: the fonts a page can find, tested in the protected page: one found here and not on main is worse
    assert nr._judge("masked-fonts", [], ["arimo"])[0] == "worse"
    assert nr._judge("masked-fonts", ["arimo", "cousine"], ["arimo"])[0] == "stricter"
    assert nr._judge("masked-fonts", [], None)[0] == "unjudged"
    assert nr._judge("masked-fonts", None, [])[0] == "worse"            # main's not measured: cannot be judged
    assert nr.masked_fonts(ROOT)[:1] and "Calibri" in nr.masked_fonts(ROOT)
    # N7: the cores at Strict, a pick drawn the same in every session (4 of [4, 8] there): a fixed disguise
    # for the other machine, so one that follows its real value (3 processors there) is told
    probe = {"navigator": {"hardwareConcurrency": 4}}
    flats = [{"navigator.hardwareConcurrency": {"value": 4}}] * 7
    off = {"navigator": {"hardwareConcurrency": 4}}

    def env2(here_cores):
        return {"levels": {"strict": {"probe": {"navigator": {"hardwareConcurrency": here_cores}}},
                           "off": {"probe": {"navigator": {"hardwareConcurrency": 3}}}}}
    assert nr._env_marks("strict", probe, flats, off, env2(4)) == {"navigator.hardwareConcurrency": True}
    assert nr._env_marks("strict", probe, flats, off, env2(3)) == {"navigator.hardwareConcurrency": False}
    assert nr.OTHER_MACHINE["cpus"] == 3 and nr.OTHER_MACHINE["memory_gb"] == 2 and "_SC_PHYS_PAGES" in nr.MEMORY_SHIM


def test_the_fourth_review_rules_of_the_report():
    """N6 (a floor as text is an error; a floor far under main's noise is said), N9 (the allowlist pins a
    part, a detail, a version), N10 (measured on main as null, missing here: never "same"), N5 (the
    fingerprinting rows not the same or stricter; several runs, a row worse in any is worse)."""
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "f.json"
        p.write_text(json.dumps({"floors": {"audio": {"dispersion": "0.0004"}}}))
        assert nr.load_floors(p) is None
        p.write_text(json.dumps({"floors": {"audio": {"dispersion": 0}}}))
        assert nr.load_floors(p) is None
        p.write_text(json.dumps({"floors": {"audio": {"dispersion": 0.0004}}}))
        assert nr.load_floors(p) == {"audio": {"dispersion": 0.0004}}
    main = fp_snap({"fingerprint/strict/audio": disguised("1", "2", {"dispersion": 5e-4, "share": 1.0})})
    assert nr.stale_floors(main, {"audio": {"dispersion": 2.4e-5, "share": 0.9}}) == [
        "strict/audio dispersion: floor 2.4e-05, main 0.0005"]
    report = nr.compare(main, main, [], None, {"audio": {"dispersion": 2.4e-5}}, {})
    assert report["floor_notices"] and "Noise floors far under main's noise" in nr.markdown(report)
    floors = nr.load_floors()
    assert floors["audio"]["dispersion"] >= 4e-4                 # raised after #148 (main's is 5e-4)
    # N9: an entry for one part, one detail, one version
    rows = {"key": "fingerprint/strict/frame_x", "detail": "[3] the real value (Off's) here, in a session where main "
                                                           "never gave it"}
    e = [{"key": "fingerprint/strict/frame_x", "part": "[3]", "detail": "the real value", "version": "1.1.25",
          "why": "w"}]
    assert nr._accepted(e, rows["key"], 1, 2, rows["detail"], "1.1.25") == 0
    assert nr._accepted(e, rows["key"], 1, 2, rows["detail"], "1.1.26") is None
    assert nr._accepted(e, rows["key"], 1, 2, "[0] " + rows["detail"][4:], "1.1.25") is None
    assert nr._accepted(e, rows["key"], 1, 2, "[3] fewer names", "1.1.25") is None
    # N10: null on main, missing here
    for key, rule in (("network/fresh-profile", "no-new"), ("fingerprint/strict/battery", "protective")):
        b = snap(**{key.replace("/", "__"): (rule, None)})
        c = snap()
        kind, detail = judged(nr.compare(b, c, [], None, {}, {}), key)
        assert kind == "worse" and "not measured on the candidate" in detail, (key, kind, detail)
    # N5: the fingerprinting rows not the same or stricter, and several runs merged
    cand = fp_snap({"fingerprint/strict/screen.width": fixed(1680)})
    report = nr.compare(fp_snap(), cand, [], None, {}, {"fingerprint/strict/screen.width": [1680]} and {})
    assert any(r["key"] == "fingerprint/strict/screen.width" for r in report["fingerprint_review"])
    assert nr.compare(fp_snap(), fp_snap(), [], None, {}, {})["fingerprint_review"] == []
    one = nr.compare(fp_snap(), fp_snap(), [], None, {}, {})
    two = nr.compare(fp_snap(), cand, [], None, {}, {})
    merged = nr.merge_runs([one, two])
    assert merged["runs"] == 2 and merged["verdict"] == "fail"
    assert any(r["detail"].startswith("run 2: ") for r in merged["worse"])
    assert "Measured 2 times" in nr.markdown(merged)
    shape = nr.random_shape()
    assert 80 <= shape["pw"] <= 112 and 4096 <= shape["len"] <= 6144 and len(shape["text"].split()) == 4


def test_every_level_is_measured_after_the_font_check():
    """The fonts a page could find are asked 15 s after a start and change every level's settings: the
    hook's start asks at once and waits (pull request #157, the one wait); measure() then finds the
    answer there, and no answer is an error (a level measured before it and another after it)."""
    hook = nr.HOOK[nr.HOOK.index("def measure():"):nr.HOOK.index("def _start():")]
    assert "fc._run()" not in hook and nr.HOOK.count("fc._run()") == 1       # one wait, in _start
    assert hook.index("gave no answer in 60 s") < hook.index("yield from _fonts_findable()") < \
        hook.index('for lv in PLAN["levels"]:')
    # the fonts a page can find: the tool's own test, in a profile with none of I.K.E.'s scripts
    assert "QWebEngineProfile(qapp)" in nr.HOOK and "FONTS_JS" in nr.HOOK


def test_the_code_measured_cannot_find_the_tool_by_its_names():
    """The probe's path, query, title, global, the frame's host, the hook's files and variable are
    this run's own random names (review of 2026-11-24, a partial measure); what is kept has the fixed
    names back, so the snapshots of two runs compare."""
    a, b = nr.run_names(), nr.run_names()
    assert all(a[k] != b[k] for k in a if k != "dirs")
    for text in (nr.HOOK, nr.WRAPPER, nr.PROBE, nr.FRAME):
        for word in ("nrResult", "ike_nr_net", "IKE_NR", "no-regression", "no regression", "nothing gets worse",
                     "data-nr", "/fp?", "nr-third"):
            assert word.lower() not in text.lower(), word
    server = nr.Server({"pages": []}, a)
    try:
        server._keep("third-party", "strict", {"Referer": "http://127.0.0.1:%d/%s?%s=strict" % (
            server.port, a["path"], a["param"]), "Origin": "http://%s" % a["third"]})
        assert server.headers["strict"]["third-party"] == {"referer": "http://127.0.0.1:PORT/fp?lv=strict",
                                                          "origin": "http://%s" % nr.THIRD}
        page = server.page("balanced")
        assert a["third"] in page and a["global"] in page and "__" not in page.replace("__proto__", "")
    finally:
        server.close()
    # an AI fix that names what measures it is refused by the static guard and by the reviewers
    guard, review = load("fix-guard"), load("ai-review")
    for added in ("if os.environ.get('IKE_TEST_HOOK'): return", "if QGuiApplication.platformName() == 'offscreen':",
                  "skip = len(shields.profile_keys) > 1", "if os.environ.get('GITHUB_ACTIONS'): return",
                  "if 'swiftshader' in flags: pass", "if host.endswith('.example'): return",
                  "if 'ike_nr_net' in sys.modules: return", "single = os.environ.get('IKE_NO_SINGLE')",
                  "if os.environ.get('RUNNER_OS'): return", "if url.startswith('http://127.0.0.1'): return"):
        problems = guard.measurement_problems("ike/shields.py", "x = 1\n", "x = 1\n" + added + "\n")
        assert problems and "names what measures it" in problems[0], added
        diff = "--- a/ike/shields.py\n+++ b/ike/shields.py\n@@ -1 +1,2 @@\n x = 1\n+%s\n" % added
        asked = []
        result = review.review(diff, "", "Groq", opener=lambda *a, **k: asked.append(a))
        assert result["verdict"] == "reject" and "names what measures it" in result["why"] and not asked, result
    assert guard.measurement_problems("ike/shields.py", "a = 'IKE_TEST_HOOK'\n", "a = 'IKE_TEST_HOOK'\nb = 2\n") == []


def test_the_signing_notice_lists_what_passed_by_evidence():
    notice = load("release-notice")
    seen = []

    def api(path):
        seen.append(path)
        if "/check-runs?" in path:
            # the job that runs "Nothing gets worse" (since the shards: "tests checks"); a shard's notice
            # of the same title does not count (it runs the candidate's tests)
            return {"check_runs": [{"id": 7, "name": "tests checks"}, {"id": 8, "name": "tests shard 1/4"}]}
        return [{"title": notice.EVIDENCE_TITLE, "message": "1 passed by evidence: fingerprint/strict/x (necessity)"},
                {"title": "other", "message": "no"}]
    assert notice.evidence_of("o/r", "abc", api) == ["1 passed by evidence: fingerprint/strict/x (necessity)"]
    assert seen == ["repos/o/r/commits/abc/check-runs?per_page=50",
                    "repos/o/r/check-runs/7/annotations?per_page=100"]
    assert notice.EVIDENCE_TITLE == nr.EVIDENCE_TITLE

    def down(path):
        raise RuntimeError("down")
    assert notice.evidence_of("o/r", "abc", down) is None
    info = {"last": "v1.1.23", "unread": [], "pending": [], "changes": [
        {"n": 150, "title": "A fix", "self": True, "ai": False, "tier_a": [], "tier_b": [], "tier_b_ai": [],
         "files": ["ike/x.py"], "evidence": ["1 passed by evidence: fingerprint/strict/x (necessity): needed"]},
        {"n": 151, "title": "Another", "self": True, "ai": False, "tier_a": [], "tier_b": [], "tier_b_ai": [],
         "files": ["ike/y.py"], "evidence": None}]}
    text = notice.body("1.1.24", "o/r", "owner", info)
    at = text.index("### Differenze passate per prova, senza una persona")
    assert "**#150** 1 passed by evidence: fingerprint/strict/x (necessity): needed" in text[at:]
    assert "ha accettato per prova in: #151" in text


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
    assert main["session2"] != main["value"] and main["noise"]["dispersion"] > 0, main
    stronger = nr.snapshot(tmp_path / "stronger", **how)
    report = nr.compare(base, stronger, [])
    assert report["verdict"] == "pass", (report["worse"], report["errors"])
    kind, detail = judged(report, "fingerprint/strict/audio")
    assert kind == "stricter" and "noise larger" in detail, detail
    assert stronger["observations"]["fingerprint/strict/audio"]["noise"]["dispersion"] > 5 * main["noise"]["dispersion"]
    off = nr.snapshot(tmp_path / "off", **how)
    report = nr.compare(base, off, [])
    assert report["verdict"] == "fail"
    assert {"fingerprint/strict/audio", "fingerprint/strict/audio.noised"} <= keys(report["worse"]), report["worse"]
