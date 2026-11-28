"""Gemini through its own API, among the reserves (2026-11-28).

The Antigravity CLI never worked in the workflow's closed room: it looks up other names, which the firewall
refuses (about 150 refused lookups a run), and stopped as "temporary" (2026-11-25) or after its 8 minutes
(2026-11-28). It is no longer started unless AUTOFIX_AGENT_CLI=on; Gemini is asked through the API the reviewers
already use (one host, already allowed), under Antigravity's name and quota, with room for whole large files."""

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load(name):
    spec = importlib.util.spec_from_file_location("gapi_" + name.replace("-", "_"), ROOT / "tools" / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_cli_is_not_started_by_default(tmp_path, monkeypatch):
    agent = load("autofix-agent")
    monkeypatch.delenv("AUTOFIX_AGENT_CLI", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "g")
    (tmp_path / "prompt.md").write_text("rules\n")
    status = tmp_path / "status.json"
    started = []
    monkeypatch.setattr(agent.subprocess, "run", lambda *a, **k: started.append(a) or None)
    monkeypatch.setattr(agent.subprocess, "Popen", lambda *a, **k: started.append(a) or None)
    assert agent.main(["--workdir", str(tmp_path), "--prompt", str(tmp_path / "prompt.md"), "--out",
                       str(tmp_path / "out"), "--status", str(status), "--agent-cmd", "agy"]) == 0
    got = json.loads(status.read_text())
    assert got["result"] == "rotated" and "API" in got["message"] and not started


def test_gemini_is_a_reserve_under_antigravitys_name():
    reserve, reg = load("autofix-reserve"), load("ai-providers")
    plan = reserve.chain({"GEMINI_API_KEY": "g", "GROQ_API_KEY": "k"})
    gemini = [p for p in plan if p[0] == "Antigravity"]
    assert gemini and plan[0][0] == "Antigravity"
    assert all(p[1] == reg.GEMINI_OPENAI == "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
               and p[2] == "g" for p in gemini)
    assert [p[3] for p in gemini][:len(reg.GEMINI_MODELS)] == [reg.gemini_api_id(m) for m in reg.GEMINI_MODELS]
    assert reg.gemini_api_id("Gemini 3.8 Flash (High)") == "gemini-3.8-flash"
    # the configured model first, a discovered one after the known ones; no key or marked unavailable: none
    named = reserve.chain({"GEMINI_API_KEY": "g", "AUTOFIX_MODEL": "Gemini 5 Pro (High)",
                           "AUTOFIX_DISCOVERED": "Antigravity:gemini-5-flash"})
    assert named[0][3] == "gemini-5-pro" and "gemini-5-flash" in [p[3] for p in named if p[0] == "Antigravity"]
    assert "Antigravity" not in [p[0] for p in reserve.chain({"GROQ_API_KEY": "k"})]
    for off in ("Antigravity", "Gemini"):
        assert "Antigravity" not in [p[0] for p in reserve.chain({"GEMINI_API_KEY": "g",
                                                                   "AUTOFIX_UNAVAILABLE": off})]
    # a starting order of another provider puts Gemini after it, never out
    assert [p[0] for p in reserve.rotated(plan, "Groq")][0] == "Groq"
    assert "Antigravity" in [p[0] for p in reserve.rotated(plan, "Groq")]


def test_gemini_gets_whole_large_files():
    reserve, reg = load("autofix-reserve"), load("ai-providers")
    big = "x = 1\n" * 30000                                 # 180 000 characters, like ike/window.py
    msg = reserve.message_for("F" * 500, "C" * 500, {"ike/window.py": big}, reg.GEMINI_BUDGET)
    assert big in msg
    assert big not in reserve.message_for("F" * 500, "C" * 500, {"ike/window.py": big}, 14_000)
