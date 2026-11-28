"""With AUTOMAT's memory, only the providers that really failed this error move down (the drill of 2026-11-28).

Attempt 1 was a recipe's; attempt 2 then started one provider further down and skipped Gemini's agent, which had
not tried at all. The number of the attempt counts only when the memory could not be read."""

import importlib.util
import io
import json
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load(name):
    spec = importlib.util.spec_from_file_location("rot_" + name.replace("-", "_"), ROOT / "tools" / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def plan(route, tmp_path, attempt, memory=None):
    failure = tmp_path / "failure.md"
    failure.write_text("FAILED tests/a.py::t1 - A: 1\nFAILED tests/a.py::t2 - B: 2\nFAILED tests/a.py::t3 - C: 3\n")
    args = ["plan", "--failure", str(failure), "--component", "automation/update/drill-qt", "--attempt", str(attempt)]
    if memory is not None:
        args += ["--memory", str(memory)]
    out = io.StringIO()
    with redirect_stdout(out):
        route.main(args)
    return dict(line.split("=", 1) for line in out.getvalue().splitlines() if "=" in line)


def test_a_recipes_attempt_does_not_skip_the_agent(tmp_path):
    route, mem = load("automat-route"), load("automat-memory")
    m = mem.empty()
    sig = mem.signature("FAILED tests/a.py::t1 - A: 1\nFAILED tests/a.py::t2 - B: 2\nFAILED tests/a.py::t3 - C: 3\n")
    mem.note(m, "automation/update/drill-qt", sig, "tests-failed", "Recipe", "renamed-symbol", ["ike/window.py"],
             "one of six", attempt=1, task="multi-file")
    path = tmp_path / "memory.json"
    path.write_text(json.dumps(m))
    assert plan(route, tmp_path, 2, path)["first"] == "Antigravity"
    # the agent failed this very error: the next attempt starts with another provider
    mem.note(m, "automation/update/drill-qt", sig, "no-fix", "Antigravity", "gemini", [], "nothing", attempt=2,
             task="multi-file")
    path.write_text(json.dumps(m))
    got = plan(route, tmp_path, 3, path)
    assert got["first"] != "Antigravity" and got["order"].split(",")[-1] == "Antigravity"
    # no memory to read: the number of the attempt moves the start, as before
    assert plan(route, tmp_path, 2, tmp_path / "missing.json")["first"] != "Antigravity"
    assert plan(route, tmp_path, 2)["first"] != "Antigravity"
