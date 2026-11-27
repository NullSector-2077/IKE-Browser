"""AUTOMAT block 2 (2026-11-27): the providers' new free models are found by AUTOMAT itself.

The owner: AUTOMAT keeps up with how our keys work and updates the names of the AI models by itself. Each week
tools/provider-check.py reads the providers' own lists of models, asks each new one a tiny question on the key
(no billing: an answer means free; Gemini's "limit: 0" means not on the free plan), and the automatic fix asks
what answered after the configured models (AUTOFIX_DISCOVERED). Offline: fake providers, no key, no network.
"""

import datetime as dt
import importlib.util
import io
import json
import urllib.error
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def load(name):
    spec = importlib.util.spec_from_file_location("disc_" + name.replace("-", "_"), ROOT / "tools" / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def check():
    return load("provider-check")


class Answer:
    status = 200
    headers = {}

    def __init__(self, data):
        self.data = data

    def read(self, _limit):
        return json.dumps(self.data).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def gemini_model(mid, methods=("generateContent",)):
    return {"name": "models/" + mid, "supportedGenerationMethods": list(methods)}


def fake(asked):
    def opener(req, timeout=0):
        url = req.full_url
        asked.append(url)
        if url.endswith("/models?pageSize=1000"):
            return Answer({"models": [gemini_model("gemini-4-hydrogen"), gemini_model("gemini-3.8-flash"),
                                      gemini_model("gemini-4-neon"), gemini_model("gemini-5-flash"),
                                      gemini_model("gemini-embedding-002", ("embedContent",)),
                                      gemini_model("gemini-4-flash-image")]})
        if "gemini-4-neon:generateContent" in url:
            raise urllib.error.HTTPError(url, 429, "x", {}, io.BytesIO(
                b'{"error": {"message": "Quota exceeded ... limit: 0, model: gemini-4-neon"}}'))
        if "gemini-3.6-flash:" in url or "gemini-3.5-flash-lite:" in url:      # configured, really gone
            raise urllib.error.HTTPError(url, 404, "x", {}, io.BytesIO(b'{"error": {"status": "NOT_FOUND"}}'))
        if ":generateContent" in url:
            return Answer({"candidates": [{"content": {"parts": [{"text": "OK"}]}}]})
        if url == "https://api.groq.com/openai/v1/models":
            return Answer({"data": [{"id": "openai/gpt-oss-120b"}, {"id": "openai/gpt-oss-20b"},
                                    {"id": "meta/llama-9-70b"}, {"id": "whisper-large-v4"}]})
        if url.endswith("/chat/completions"):
            if b"qwen" in (req.data or b""):                  # a configured model that is really gone
                raise urllib.error.HTTPError(url, 404, "x", {}, io.BytesIO(b'{"error": "model not found"}'))
            return Answer({"choices": [{"message": {"content": "OK"}}]})
        raise urllib.error.HTTPError(url, 404, "x", {}, io.BytesIO(b"{}"))
    return opener


ENV = {"GEMINI_API_KEY": "AIzaTEST", "GROQ_API_KEY": "gsk_TEST", "ZAI_API_KEY": "zai_TEST"}


def test_new_free_models_are_found_and_the_gone_ones_said(check):
    asked = []
    info = check.discover(ENV, fake(asked))
    assert info["discovered"] == {"Antigravity": ["gemini-5-flash"], "Groq": ["meta/llama-9-70b"]}
    assert info["not_free"] == {"Antigravity": ["gemini-4-neon"]}
    assert "qwen/qwen3.8-27b" in info["gone"]["Groq"] and "gemini-3.6-flash" in info["gone"]["Antigravity"]
    assert "Z.AI" not in info["gone"]                     # its list could not be read: nothing said
    assert not any("embedding" in u or "image" in u or "whisper" in u for u in asked if "generateContent" in u
                   or u.endswith("/chat/completions"))
    text = json.dumps(info)
    assert not any(k in text for k in ENV.values())


def test_the_line_for_the_fix_and_its_reading(check):
    registry = load("ai-providers")
    line = check.discovered_line({"discovered": {"Antigravity": ["gemini-5-flash"], "Groq": ["meta/llama-9-70b"],
                                                 "Evil": ["x"], "OpenRouter": ["a:free"]}})
    assert line == "Antigravity:gemini-5-flash;Groq:meta/llama-9-70b"
    env = {registry.DISCOVERED_VAR: line + ";Groq:bad id$;OpenRouter:x:free"}
    assert registry.discovered(env) == {"Antigravity": ["gemini-5-flash"], "Groq": ["meta/llama-9-70b"]}
    assert registry.gemini_cli_name("gemini-3.5-flash-lite") == "Gemini 3.5 Flash Lite (High)"


def test_the_fix_asks_them_after_the_configured_models(check, monkeypatch):
    reserve = load("autofix-reserve")
    env = {"GROQ_API_KEY": "g", "AUTOFIX_DISCOVERED": "Groq:meta/llama-9-70b;Antigravity:gemini-5-flash"}
    groq = [m for name, _u, _k, m, _b, _t in reserve.chain(env) if name == "Groq"]
    assert groq[-1] == "meta/llama-9-70b" and groq[0] == "openai/gpt-oss-120b"
    monkeypatch.setenv("AUTOFIX_DISCOVERED", "Antigravity:gemini-5-flash")
    agent = load("autofix-agent")
    assert agent.models("")[-1] == "Gemini 5 Flash (High)"
    review = load("ai-review")
    names = [m for m, _b, _f in review.models_of("Antigravity", {"GEMINI_API_KEY": "k",
                                                               "AUTOFIX_DISCOVERED": "Antigravity:gemini-5-flash"},
                                                 reserve)]
    assert names[-1] == "Gemini 5 Flash (High)" and review.gemini_id(names[-1]) == "gemini-5-flash"


def test_the_weekly_issue_says_a_gone_model_and_what_replaces_it():
    health = load("automation-health")
    now = dt.datetime(2026, 11, 30, tzinfo=dt.timezone.utc)
    found = health.problems(now, {}, [], True, models={"gone": {"Groq": ["qwen/qwen3.8-27b"]},
                                                        "discovered": {"Groq": ["meta/llama-9-70b"]}})
    assert any("qwen/qwen3.8-27b" in f and "meta/llama-9-70b" in f for f in found)


def test_the_workflow_passes_them_to_the_fix():
    text = (ROOT / ".github" / "workflows" / "autofix.yml").read_text("utf-8")
    assert "tools/provider-check.py discovered --repo" in text
    assert "discovered: ${{ steps.providers.outputs.discovered }}" in text
    assert text.count('AUTOFIX_DISCOVERED="$(cat "$RUNNER_TEMP/discovered"') == 2


def test_a_configured_model_that_answers_is_never_gone(check):
    """2026-11-27: Z.AI's list did not name its free GLM Flash models, which answer: no false alarm."""
    def opener(req, timeout=0):
        url = req.full_url
        if url == "https://api.z.ai/api/paas/v4/models":
            return Answer({"data": [{"id": "GLM-5.3"}]})
        if url.endswith("/chat/completions"):
            return Answer({"choices": [{"message": {"content": "OK"}}]})
        raise urllib.error.HTTPError(url, 404, "x", {}, io.BytesIO(b"{}"))
    info = check.discover({"ZAI_API_KEY": "zai_TEST"}, opener)
    assert "Z.AI" not in info["gone"] and info["discovered"] == {"Z.AI": ["GLM-5.3"]}
