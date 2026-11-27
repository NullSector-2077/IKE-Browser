"""AUTOMAT, 2026-11-27 (run 45983654916, PR #111): the free models of Z.AI, OpenRouter and Groq alike spent the
whole answer on their reasoning and gave no text ("cutoff"). Proved here, offline: each provider is asked for
little reasoning with its own parameter, and a model cut off is asked once more with its reasoning off.
"""

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ZAI = "https://api.z.ai/api/paas/v4/chat/completions"
GROQ = "https://api.groq.com/openai/v1/chat/completions"
OPENROUTER = "https://openrouter.ai/api/v1/chat/completions"


@pytest.fixture(scope="module")
def reserve():
    spec = importlib.util.spec_from_file_location("cutoff_reserve", ROOT / "tools" / "autofix-reserve.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_each_provider_gets_its_own_parameter(reserve):
    p = reserve.reasoning_params
    assert p(OPENROUTER, "x:free", "less") == {"reasoning": {"effort": "minimal", "exclude": True}}
    assert p(OPENROUTER, "x:free", "off") == {"reasoning": {"effort": "none", "exclude": True}}
    assert p(ZAI, "glm-4.7-flash", "less") == {} and p(ZAI, "glm-4.7-flash", "off") == {"thinking": {"type": "disabled"}}
    assert p(GROQ, "openai/gpt-oss-120b", "less") == p(GROQ, "openai/gpt-oss-120b", "off") == {"reasoning_effort": "low"}
    assert p(GROQ, "qwen/qwen3.8-27b", "less") == {} and p(GROQ, "qwen/qwen3.8-27b", "off") == {"reasoning_effort": "none"}
    assert p("https://example.org/v1/chat/completions", "m", "off") == {} and p(ZAI, "m", "") == {}


class Answer:
    headers = {}

    def __init__(self, data):
        self.data = data

    def read(self, _limit):
        return json.dumps(self.data).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


CUT = {"choices": [{"message": {"content": ""}, "finish_reason": "length"}]}


def test_a_model_cut_off_is_asked_again_with_its_reasoning_off(reserve, tmp_path, monkeypatch):
    sent = []

    def opener(req, timeout=0):
        body = json.loads(req.data)
        sent.append(body)
        if body.get("thinking") != {"type": "disabled"}:
            return Answer(CUT)
        return Answer({"choices": [{"message": {"content": '{"fixable": false, "summary": "no"}'},
                                    "finish_reason": "stop"}]})

    monkeypatch.setattr(reserve.time, "sleep", lambda _s: None)
    base = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]

    class A:
        allow_adblock = lists = inner = False
        builder = ""
    outcome, text, _refused = reserve.one_model(ZAI, "k", "glm-4.7-flash", base, 2000,
                                                reserve.time.monotonic() + 600, opener, tmp_path, [], A(), "", [])
    assert [b.get("thinking") for b in sent] == [None, {"type": "disabled"}]
    assert outcome == "none" and text == "no"


def test_a_ping_cut_off_counts_as_an_answer(reserve):
    assert reserve._ping_one(GROQ, "k", "openai/gpt-oss-120b", lambda req, timeout=0: Answer(CUT)) == "ok"
