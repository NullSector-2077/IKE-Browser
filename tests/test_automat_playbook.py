"""AUTOMAT's playbook (tools/automat-playbook.py, 2026-11-27): the AIs are told what a failure of an updated
component means in I.K.E., where its fix goes and how to write it so the checks accept it.

PR #111 is the reason: given only the engine's error, the free models guessed (a helper nothing called, a
function put between two methods of a class) and the static guard refused it. Proved here: every entry points at
real files and functions, a sample of each kind of failure finds its entry, the advice reaches the context the
agent and the reserves read, no AI may change the playbook, and an engine limit is no longer given to an AI.
"""

import importlib.util
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def load(name):
    spec = importlib.util.spec_from_file_location("pb_" + name.replace("-", "_"), ROOT / "tools" / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def pb():
    return load("automat-playbook")


SAMPLES = {
    "adblock-csp-with-content-type": "possible security regression (network filter error: csp with content type)",
    "adblock-unrecognised-option": "rule-dropped (network filter error: unrecognised option)",
    "scriptlet-unknown": "a scriptlet the bundled library does not know: unknown scriptlet set-cookie-reload",
    "builder-anchor": "darkreader: builder refused 4.9.140: anchor 'createOrUpdateStyle' not found",
    "qt-api-renamed": "AttributeError: type object 'QWebEnginePage' has no attribute 'Feature'",
    "python-stdlib-removed": "ModuleNotFoundError: No module named 'imghdr'",
    "rust-wrapper-api": "error[E0599]: no method named `check_network_request` found\n --> ike-adblock/src/lib.rs:250",
    "nothing-gets-worse-fingerprint": "### Nothing gets worse\n\n**Failed**: 6 things worse than on main.",
    "tier-b-engine-switches": "a step changed .github/workflows/tests.yml",
}


def test_every_entry_is_complete_and_has_a_sample(pb):
    ids = [e["id"] for e in pb.PLAYBOOK]
    assert len(ids) == len(set(ids)) and set(ids) == set(SAMPLES)
    for entry in pb.PLAYBOOK:
        for field in ("meaning", "how", "never"):
            assert len(entry[field]) > 40, (entry["id"], field)
        for sign in entry["signs"]:
            re.compile(sign)
        assert entry in pb.match(SAMPLES[entry["id"]]), entry["id"]


def test_the_places_named_exist(pb):
    for entry in pb.PLAYBOOK:
        for path in entry["where"]:
            assert (ROOT / path).is_file(), (entry["id"], path)
    blocker = (ROOT / "ike/blocker.py").read_text("utf-8")
    assert re.search(r"^def sanitize\(text\):", blocker, re.M)
    assert re.search(r"^    def resolve\(self, token\):", (ROOT / "ike/scriptlets.py").read_text("utf-8"), re.M)
    rust = (ROOT / "ike-adblock/src/lib.rs").read_text("utf-8")
    for name in ("check_network_urls", "get_csp_directives", "url_cosmetic_resources", "hidden_class_id_selectors",
                 "add_resource", "serialize", "deserialize", "guarded"):
        assert "fn %s" % name in rust, name


def test_a_plain_traceback_is_not_taken_for_a_tier_b_failure(pb):
    plain = ('Traceback (most recent call last):\n  File "/x/ike/app.py", line 40, in main\n'
             '  File "/x/ike/weather.py", line 12, in fetch\nValueError: bad')
    assert not any(e["id"] == "tier-b-engine-switches" for e in pb.match(plain))


def test_the_advice_reaches_the_context_and_its_files_come_first(tmp_path):
    ctx = load("autofix-context")
    (tmp_path / "ike-adblock" / "src").mkdir(parents=True)
    (tmp_path / "ike-adblock" / "src" / "lib.rs").write_text("fn x() {}\n")
    failure = "error[E0599]: no method named `x`\n --> somewhere\n"
    text, related = ctx.build(tmp_path, failure, recent=False)
    assert related[0] == "ike-adblock/src/lib.rs" and "rust-wrapper-api" in text
    failure = "# Filter lists: possible security regression (network filter error: csp with content type)\n"
    text, related = ctx.build(tmp_path, failure, recent=False)
    assert "AUTOMAT's playbook" in text and "Rules of every fix" in text and "outside every class" in text
    assert "not fixable in I.K.E.'s adapter" in text.lower() or "Not fixable in I.K.E.'s adapter" in text
    text, related = ctx.build(tmp_path, "nothing known here\n", recent=False)
    assert "AUTOMAT's playbook" not in text


def test_no_ai_may_change_the_playbook():
    guard = load("check-autofix-patch")
    ctx = load("autofix-context")
    for path in ("tools/automat-playbook.py", "tests/test_automat_playbook.py"):
        assert path in guard.FORBIDDEN_FILES and path in ctx.NOT_RECENT, path


def test_an_engine_limit_is_no_longer_given_to_an_ai():
    lists = load("filter-lists")
    info = {"lists": [{"name": "uBlock filters", "state": "ok", "network": 1, "cosmetic": 0, "unread": [
        ["network", "||uppit.com^$document,csp=script-src 'self'", "network filter error: csp with content type"],
        ["network", "*$script,3p,denyallow=googleapis.com,domain=x.com", "network filter error: unrecognised option"],
    ]}]}
    found = {f["detail"]: f for f in lists.classify(info)["findings"]}
    csp = found["network filter error: csp with content type"]
    assert csp["class"] == "security" and csp["ai"] is False and "Qt WebEngine" in csp["why"]
    assert found["option denyallow"]["ai"] is True                 # other findings unchanged
    out, failure, _recorded = lists.plan(info, "lists/2026-11-27/" + csp["key"], "0" * 40)
    assert out["action"] == "skip" and "no AI analysis" in out["reason"] and failure == ""


def test_the_scriptlet_library_keeps_its_methods():
    """PR #111 put a function between two methods of Library and took entry() out of the class; the tests then
    did not notice. Every method the tools and the browser call is still the class's own."""
    src = (ROOT / "ike/scriptlets.py").read_text("utf-8")
    body = src.split("\nclass Library", 1)[1].split("\nclass ", 1)[0].split("\ndef ", 1)[0]
    for name in ("_load", "lib_version", "resolve", "entry"):
        assert re.search(r"^    def %s\(self" % name, body, re.M), name
