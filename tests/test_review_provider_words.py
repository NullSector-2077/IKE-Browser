"""The reviewers say the provider's own words when Gemini refuses (2026-11-28), never the key."""

import importlib.util
import io
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load(name):
    spec = importlib.util.spec_from_file_location("words_" + name.replace("-", "_"), ROOT / "tools" / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_a_refusal_of_gemini_is_logged_with_its_words_and_without_the_key():
    review, reserve = load("ai-review"), load("autofix-reserve")
    key = "AIzaFAKEKEY1234567890"
    said = ('{"error": {"code": 429, "message": "You exceeded your current quota (key %s), please check your plan",'
            ' "status": "RESOURCE_EXHAUSTED"}}' % key)

    def opener(req, timeout=0):
        raise urllib.error.HTTPError(req.full_url, 429, "Too Many Requests", {}, io.BytesIO(said.encode()))

    try:
        review.ask_gemini(key, "gemini-2.5-flash", "s", "u", opener, reserve)
    except reserve.Stop as s:
        kind, why = s.args[0], s.args[1]
    else:
        raise AssertionError("no Stop")
    assert kind == "quota"
    assert why.startswith("HTTP 429") and "exceeded your current quota" in why, why
    assert key not in why
