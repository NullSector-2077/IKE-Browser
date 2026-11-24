"""The suite split across parallel jobs, and its completeness gate (2026-11-24).

tools/shard-tests.py splits the suite by whole test files into shards balanced
by their recorded durations, and its "verify" is the gate of tests.yml ("tests",
main's required check) and arch.yml ("Arch Linux"): every collected test ran
exactly once across the shards, every shard is there and passed. Proved here
on a real pytest run of a small suite in a temporary folder (no browser, no
network), then with every way a test can go missing or run twice; and the
workflows, the plan of the automatic fix and the categories are held to it.
"""

import importlib.util
import json
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), ROOT / "tools" / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


shards = load("shard-tests")
plan_tool = load("autofix-plan")
tc = load("test-categories")

SUITE = {
    "pyproject.toml": '[tool.pytest.ini_options]\ntestpaths = ["tests"]\naddopts = "-q"\n',
    "tests/test_a.py": "def test_one():\n    pass\n\n\ndef test_two():\n    pass\n",
    "tests/test_b.py": ("import pytest\n\n\n@pytest.mark.parametrize('x', ['a::b', 'c[d]', 'e f'])\n"
                        "def test_odd(x):\n    pass\n\n\nclass TestGroup:\n    def test_in_class(self):\n"
                        "        pass\n"),
    "tests/test_c.py": ("import pytest\n\n\n@pytest.mark.skip(reason='not here')\ndef test_skipped():\n"
                        "    pass\n\n\ndef test_three():\n    pass\n"),
    "tests/test_d.py": "import pytest\n\npytest.importorskip('ike_no_such_module')\n\n\ndef test_never():\n    pass\n",
    "tests/test_e.py": "def test_four():\n    pass\n",
    "tests/test_f.py": "def test_five():\n    pass\n",
    # a class skipped whole at collection (a collector of its own that skips)
    "tests/conftest.py": ("import pytest\n\n\nclass Skipper(pytest.Class):\n    def collect(self):\n"
                          "        pytest.skip('this class is skipped')\n\n\n"
                          "def pytest_pycollect_makeitem(collector, name, obj):\n    if name == 'TestSkipped':\n"
                          "        return Skipper.from_parent(collector, name=name, obj=obj)\n"),
    "tests/test_g.py": "class TestSkipped:\n    def test_never(self):\n        pass\n\n\ndef test_six():\n    pass\n",
}
SHARDS = 3


def _suite(tmp_path):
    root = tmp_path / "repo"
    for rel, text in SUITE.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    return root


def _run_all(root, out, kind="source", sha="s1"):
    """Every shard of the small suite, as the shard jobs run them (a real pytest each)."""
    import os
    env = dict(os.environ, GITHUB_SHA=sha, GITHUB_RUN_ID="r1", GITHUB_RUN_ATTEMPT="1")
    env.pop("IKE_TEST_APP", None)
    env.pop("IKE_PACKAGE_SHA256", None)
    for k in range(1, SHARDS + 1):
        run = subprocess.run([sys.executable, str(ROOT / "tools/shard-tests.py"), "run", "--kind", kind,
                              "--shard", str(k), "--shards", str(SHARDS), "--out", str(out / ("part-%d" % k)),
                              "--timings", str(out / "none.json")],
                             cwd=root, env=env, capture_output=True, text=True, timeout=300)
        assert run.returncode == 0, run.stdout + run.stderr
    ref = out / "collected.txt"
    assert shards.collect(ref, cwd=root)
    return ref


@pytest.fixture(scope="module")
def ran(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("shards")
    root = _suite(tmp)
    out = tmp / "parts"
    ref = _run_all(root, out)
    return root, out, ref


def _copy(ran, tmp_path):
    out = tmp_path / "parts"
    shutil.copytree(ran[1], out)
    return out, ran[2]


def _verify(out, ref, **kw):
    return shards.verify(kw.pop("kind", "source"), SHARDS, out, [ref], sha=kw.pop("sha", "s1"),
                         run_id=kw.pop("run_id", "r1"), timings_path=out / "none.json", **kw)


def test_the_collection_holds_every_test_and_each_file_skipped_whole(ran):
    ids = shards.read_ids(ran[2])
    assert "tests/test_b.py::test_odd[a::b]" in ids and "tests/test_b.py::TestGroup::test_in_class" in ids
    assert "tests/test_c.py::test_skipped" in ids
    assert "tests/test_d.py" in ids                       # a module skipped whole is one id: its file
    assert "tests/test_g.py::TestSkipped" in ids           # and so is a class skipped whole
    assert len(ids) == len(set(ids)) == 13
    assert shards.read_ids(str(ran[2]) + ".skipped") == ["tests/test_d.py", "tests/test_g.py::TestSkipped"]


def test_the_plan_puts_every_file_in_exactly_one_shard_and_is_always_the_same():
    ids = ["tests/test_%s.py::test_x" % c for c in "abcdefgh"] + ["tests/test_z.py"]
    timings = {"tests/test_a.py": 100, "tests/test_b.py": 60, "tests/test_c.py": 50}
    parts = shards.plan(ids, 3, timings, default=10)
    flat = [f for part in parts for f in part]
    assert sorted(flat) == sorted({shards.file_of(i) for i in ids}) and len(flat) == len(set(flat))
    assert parts == shards.plan(list(reversed(ids)), 3, dict(timings), default=10)       # deterministic
    assert all(part == sorted(part) for part in parts)
    loads = [sum(timings.get(f, 10) for f in part) for part in parts]
    assert max(loads) - min(loads) <= 60                       # the longest first, into the lightest shard
    assert shards.plan(ids[:2], 4)[2:] == [[], []]             # more shards than files: some run nothing
    with pytest.raises(shards.Problem):
        shards.plan(["tests"], 2)                              # a skipped directory cannot be split by file
    with pytest.raises(shards.Problem):
        shards.plan(ids, 0)


def test_a_junit_name_is_pytests_own():
    """The gate matches a junit test case to a collected id with pytest's own rule."""
    from _pytest.junitxml import bin_xml_escape, mangle_test_address
    for nodeid in ("tests/test_a.py::test_one", "tests/test_b.py::test_odd[a::b]", "tests/test_b.py::test_odd[c[d]]",
                   "tests/test_b.py::TestGroup::test_in_class", "tests/sub/test_x.py::test_y[\x07]",
                   "tests/test_d.py", "tests/test_b.py::test_odd[è \U0001f600]"):
        names = mangle_test_address(nodeid)
        assert shards.junit_key(nodeid) == (".".join(names[:-1]), bin_xml_escape(names[-1])), nodeid


def test_every_shard_ran_and_every_test_ran_once(ran, tmp_path):
    out, ref = _copy(ran, tmp_path)
    merged = tmp_path / "junit.xml"
    problems, report = _verify(out, ref, merged_junit=merged)
    assert problems == [], problems
    assert "13 tests collected" in report[0] and "10 passed, 0 failed, 3 skipped (not verified)" in report[0]
    # the run's one junit file, as tools/test-categories.py and the ledger read it: skips stay "not verified"
    info = tc.read_junit([merged])
    assert info["tests"] == 13 and info["skipped"] == 3 and info["failed"] == 0
    assert "tests/test_c.py::test_skipped" in {s["test"] for s in info["skips"]} and len(info["skips"]) == 3
    # the command line says the same, and passes
    run = subprocess.run([sys.executable, str(ROOT / "tools/shard-tests.py"), "verify", "--kind", "source",
                          "--shards", str(SHARDS), "--dir", str(out), "--collected", str(ref), "--sha", "s1", "--run-id", "r1",
                          "--timings", str(out / "none.json")], capture_output=True, text=True, timeout=60)
    assert run.returncode == 0 and "Complete: every collected test ran exactly once" in run.stdout, run.stdout


def _drop_case(junit, name):
    tree = ET.parse(junit)
    for suite in tree.getroot().iter("testsuite"):
        for case in list(suite):
            if case.tag == "testcase" and case.get("name") == name:
                suite.remove(case)
                tree.write(junit)
                return case
    raise AssertionError(name)


def _add_case(junit, case):
    tree = ET.parse(junit)
    next(tree.getroot().iter("testsuite")).append(case)
    tree.write(junit)


def _shard_with(out, file):
    for k in range(1, SHARDS + 1):
        if file in json.loads((out / ("part-%d" % k) / "shard.json").read_text())["files"]:
            return out / ("part-%d" % k)
    raise AssertionError(file)


def test_a_test_that_did_not_run_fails_the_gate(ran, tmp_path):
    out, ref = _copy(ran, tmp_path)
    _drop_case(_shard_with(out, "tests/test_a.py") / "junit.xml", "test_two")
    problems, _ = _verify(out, ref)
    assert any("did not run: tests/test_a.py::test_two" in p for p in problems), problems
    # and on the command line: exit 1, the error said, the run not verified
    run = subprocess.run([sys.executable, str(ROOT / "tools/shard-tests.py"), "verify", "--kind", "source",
                          "--shards", str(SHARDS), "--dir", str(out), "--collected", str(ref), "--sha", "s1", "--run-id", "r1",
                          "--timings", str(out / "none.json")], capture_output=True, text=True, timeout=60)
    assert run.returncode == 1 and "::error::1 collected test(s) did not run" in run.stdout, run.stdout
    assert "NOT COMPLETE" in run.stdout


def test_a_skipped_test_or_module_still_counts_only_once(ran, tmp_path):
    out, ref = _copy(ran, tmp_path)
    # a skipped test dropped from the results is as missing as a passed one
    _drop_case(_shard_with(out, "tests/test_c.py") / "junit.xml", "test_skipped")
    problems, _ = _verify(out, ref)
    assert any("did not run: tests/test_c.py::test_skipped" in p for p in problems), problems
    out, ref = _copy(ran, tmp_path / "again")
    _drop_case(_shard_with(out, "tests/test_d.py") / "junit.xml", "tests.test_d")
    problems, _ = _verify(out, ref)
    assert any("did not run: tests/test_d.py" in p for p in problems), problems


def test_a_test_run_twice_or_in_another_shard_fails_the_gate(ran, tmp_path):
    out, ref = _copy(ran, tmp_path)
    home = _shard_with(out, "tests/test_e.py")
    case = _drop_case(home / "junit.xml", "test_four")
    _add_case(home / "junit.xml", case)
    other = next(out / ("part-%d" % k) for k in range(1, SHARDS + 1) if out / ("part-%d" % k) != home)
    _add_case(other / "junit.xml", case)
    problems, _ = _verify(out, ref)
    assert any("ran more than once: tests/test_e.py::test_four" in p for p in problems), problems
    assert any("a test of another shard" in p for p in problems), problems


def test_a_test_that_was_not_collected_fails_the_gate(ran, tmp_path):
    out, ref = _copy(ran, tmp_path)
    _add_case(out / "part-1" / "junit.xml", ET.Element("testcase", classname="tests.test_a", name="test_ghost"))
    problems, _ = _verify(out, ref)
    assert any("not collected" in p and "test_ghost" in p for p in problems), problems


def test_a_missing_failed_or_foreign_shard_fails_the_gate(ran, tmp_path):
    out, ref = _copy(ran, tmp_path)
    shutil.rmtree(out / "part-2")
    merged = tmp_path / "merged.xml"
    problems, report = _verify(out, ref, merged_junit=merged)
    assert any("shard 2 of 3 is missing" in p for p in problems), problems
    assert any("did not run" in p for p in problems), problems
    assert not merged.exists() and any("no merged results" in r for r in report)   # never a partial suite
    for change, said in (({"exit": 1}, "pytest ended with exit code 1"), ({"sha": "other"}, "ran commit"),
                         ({"shards": 4}, "split 4 ways"), ({"files": []}, "other files than its part")):
        out, ref = _copy(ran, tmp_path / said.replace(" ", "-"))
        rec = json.loads((out / "part-1" / "shard.json").read_text())
        rec.update(change)
        (out / "part-1" / "shard.json").write_text(json.dumps(rec))
        problems, _ = _verify(out, ref)
        assert any(said in p for p in problems), (said, problems)
    # the jobs GitHub reports as cancelled, failed or skipped: never complete
    out, ref = _copy(ran, tmp_path / "jobs")
    for result in ("cancelled", "failure", "skipped", ""):
        assert any("not success" in p for p in _verify(out, ref, jobs_result=result)[0]), result
    # a shard that is there twice
    shutil.copytree(out / "part-3", out / "part-3-again")
    assert any("is there 2 times" in p for p in _verify(out, ref)[0])


def test_the_shards_and_the_independent_collection_must_agree(ran, tmp_path):
    out, ref = _copy(ran, tmp_path)
    other = tmp_path / "other.txt"
    other.write_text(ref.read_text() + "tests/test_new.py::test_more\n")
    problems, _ = _verify(out, other)
    assert any("collected other tests" in p for p in problems), problems
    assert any("did not run: tests/test_new.py::test_more" in p for p in problems), problems
    # a shard's own collection that differs (another tree, another environment)
    out, ref = _copy(ran, tmp_path / "b")
    lines = (out / "part-1" / "collected.txt").read_text().splitlines()
    (out / "part-1" / "collected.txt").write_text("\n".join(lines[1:]) + "\n")
    assert any("shard 1 collected other tests" in p for p in _verify(out, ref)[0])
    # unreadable results
    out, ref = _copy(ran, tmp_path / "c")
    (out / "part-1" / "junit.xml").write_text("<testsuites><testcase")
    assert any("cannot be read" in p for p in _verify(out, ref)[0])


def test_a_shard_with_no_file_runs_nothing(tmp_path):
    """pytest with no file would run the whole suite: a shard with no part runs nothing."""
    root = tmp_path / "repo"
    for rel in ("pyproject.toml", "tests/test_a.py"):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(SUITE[rel])
    code = shards.run_shard("source", 2, 2, tmp_path / "out", timings_path=tmp_path / "none.json", cwd=root)
    rec = json.loads((tmp_path / "out" / "shard.json").read_text())
    assert code == 0 and rec["files"] == [] and rec["exit"] == 0
    assert tc.read_junit([tmp_path / "out" / "junit.xml"])["tests"] == 0


def test_a_broken_collection_stops_the_shard(tmp_path):
    root = tmp_path / "repo"
    (root / "tests").mkdir(parents=True)
    (root / "pyproject.toml").write_text(SUITE["pyproject.toml"])
    (root / "tests/test_a.py").write_text("import ike_no_such_module\n\n\ndef test_a():\n    pass\n")
    with pytest.raises(shards.Problem):
        shards.run_shard("source", 1, 2, tmp_path / "out", timings_path=tmp_path / "none.json", cwd=root)


def test_printed_names_cannot_start_a_workflow_command():
    assert shards._line("a\n::set-output name=x::y\r\nb") == "a ::set-output name=x::y b"


def test_the_durations_come_from_junit(tmp_path):
    junit = tmp_path / "j.xml"
    junit.write_text('<testsuites><testsuite><testcase classname="tests.test_a" name="test_x" time="1.5"/>'
                     '<testcase classname="tests.test_a.TestG" name="test_y[p]" time="2"/>'
                     '<testcase classname="" name="tests.test_d" time="0.1"/></testsuite></testsuites>')
    assert shards.durations([junit]) == {"tests/test_a.py": 3.5, "tests/test_d.py": 0.1}
    timings = tmp_path / "t.json"
    data = shards.write_timings(shards.durations([junit]), timings)
    assert data["files"] == {"tests/test_a.py": 3.5, "tests/test_d.py": 0.1} and data["default"] > 0
    assert shards.load_timings(timings)[0] == data["files"]
    # the recorded durations are the real suite's (a new test file counts as "default" until recorded)
    recorded, default = shards.load_timings()
    assert default > 0 and len(recorded) > 50
    assert all(f.startswith("tests/test_") and f.endswith(".py") for f in recorded)


# --- the workflows hold to it -----------------------------------------------------------------------

def _jobs(text):
    parts = re.split(r"^  ([a-z-]+):\n", text.split("\njobs:\n", 1)[1], flags=re.M)
    return dict(zip(parts[1::2], parts[2::2]))


def _steps(job):
    return re.findall(r"^      - name: (.+)$", job, re.M)


def test_tests_yml_gate_is_the_required_check_and_fails_on_anything_missing():
    text = (WORKFLOWS / "tests.yml").read_text()
    jobs = _jobs(text)
    # "main-results" (2026-11-24, "Nothing gets worse"'s evidence): main's junit for the job "tests checks";
    # it never fails (anything unread is a notice), and has no if either
    assert set(jobs) == {"main-results", "plan", "package", "shard", "installed", "checks", "base-tests", "tests",
                         "hand-over", "merge-ready"}
    assert "needs: main-results" in jobs["checks"] and "\n    if:" not in jobs["main-results"].split("steps:", 1)[0]
    assert "exit 1" not in jobs["main-results"] and "if-no-files-found: ignore" in jobs["main-results"]
    # one number of shards, for both kinds of shard, read by the plan, the shards and the gate
    assert len(re.findall(r'^  SHARDS: "(\d+)"$', text, re.M)) == 1 and text.count("SHARDS:") == 1
    assert 'echo "list=[$(seq -s, 1 "$SHARDS")]"' in jobs["plan"]
    for name in ("shard", "installed"):
        assert "shard: ${{ fromJSON(needs.plan.outputs.shards) }}" in jobs[name] and "fail-fast: false" in jobs[name]
        assert 'name: tests %s${{ matrix.shard }}/${{ strategy.job-total }}' % (
            "shard " if name == "shard" else "installed ") in jobs[name]
        assert "overwrite: true" in jobs[name] and "if: always()" in jobs[name]
    gate = jobs["tests"]
    # the job's name is "tests": no other name (main's protection asks for the check "tests")
    assert "\n    name:" not in gate.split("steps:", 1)[0]
    assert "needs: [plan, package, shard, installed, checks, base-tests]" in gate and "\n    if: always()\n" in gate
    source = gate.split("- name: Tests\n", 1)[1].split("\n      - ", 1)[0]
    assert "if: ${{ !cancelled() }}" in source and "set -o pipefail" in source
    assert "tools/shard-tests.py verify --kind source" in source and "--jobs-result \"$RESULT\"" in source
    assert "RESULT: ${{ needs.shard.result }}" in source and '--sha "$GITHUB_SHA"' in source
    assert '--collected "$RUNNER_TEMP/parts/tests-checks/collected.txt"' in source        # the independent one
    installed = gate.split("- name: Tests of the installed package\n", 1)[1].split("\n      - ", 1)[0]
    assert "tools/shard-tests.py verify --kind installed" in installed
    assert "RESULT: ${{ needs.installed.result }}" in installed
    assert "tools/shard-tests.py collect" in jobs["checks"]
    # the gate's own verdict: every part, whatever happened
    final = gate.split("- name: Every part of the tests passed\n", 1)[1]
    assert final.lstrip().startswith("if: always()") and "toJSON(needs)" in final
    for job in ("plan", "package", "shard", "installed", "checks", "base-tests"):
        assert '"%s"' % job in final, job
    assert 'if result != "success":' in final
    # nothing on the way can be skipped (a skipped need would skip merge-ready): only the gate has an if
    for name in ("plan", "package", "shard", "installed", "checks", "base-tests"):
        assert "\n    if:" not in jobs[name].split("steps:", 1)[0], name
    assert "needs: tests" in jobs["hand-over"] and "needs: tests" in jobs["merge-ready"]


def test_the_categories_read_the_step_itself_restated_by_the_gate():
    """tools/test-categories.py reads tests.yml's job "tests", by step name: each step it names is in the
    gate, and (but "Tests" and "Tests of the installed package", the completeness itself) restates the
    outcome of the step of that very name, in the job that runs it."""
    text = (WORKFLOWS / "tests.yml").read_text()
    jobs = _jobs(text)
    gate = jobs["tests"]
    for cat, (_d, (workflow, job, step)) in tc.CATEGORIES.items():
        if workflow != "tests.yml":
            continue
        assert job == "tests" and step in _steps(gate), (cat, step)
        if step in ("Tests", "Tests of the installed package"):
            continue
        mirror = gate.split("- name: %s\n" % step, 1)[1].split("\n      - ", 1)[0]
        where, output = re.search(r"OUTCOME: \$\{\{ needs\.([a-z-]+)\.outputs\.([a-z-]+) \}\}", mirror).groups()
        assert "needs.%s.outputs.%s == 'success' || needs.%s.outputs.%s == 'failure'" % (
            where, output, where, output) in mirror, step
        assert 'test "$OUTCOME" = success' in mirror, step
        source = jobs[where]
        assert step in _steps(source), (step, where)
        ident = re.search(r"- name: %s\n        id: ([a-z-]+)\n" % re.escape(step), source).group(1)
        assert "      %s: ${{ steps.%s.outcome }}\n" % (output, ident) in source, (step, output, ident)
    # every other step of tests.yml runs once per commit: in no shard
    for name in ("shard", "installed"):
        assert _steps(jobs[name]) in (["Test environment", "Tests"],
                                      ["Test environment", "The package, as built", "Tests of the installed package"])
    once = [s for name in ("package", "checks", "base-tests") for s in _steps(jobs[name]) if s != "Test environment"]
    assert len(once) == len(set(once))
    for step in ("Lint", "Licences", "AdBlock engine (Rust tests)", "A test that must fail still fails", "No tests lost",
                 "The starting commit's tests on this code", "Arch package", "The package runs on an old processor",
                 "Filter lists in this engine", "Nothing gets worse"):
        assert step in once, step


def test_arch_yml_gate_is_arch_linux_and_fails_on_anything_missing():
    text = (WORKFLOWS / "arch.yml").read_text()
    jobs = _jobs(text)
    assert set(jobs) == {"plan", "part", "arch", "hand-over", "merge-ready"}
    assert len(re.findall(r'^  SHARDS: "(\d+)"$', text, re.M)) == 1 and text.count("SHARDS:") == 1
    part = jobs["part"]
    assert "name: ${{ matrix.name }}" in part and "matrix: ${{ fromJSON(needs.plan.outputs.parts) }}" in part
    assert "timeout-minutes: 60" in part and "image: archlinux:latest" in part
    assert "tools/shard-tests.py run --kind source" in part and "tools/shard-tests.py run --kind installed" in part
    assert "if: matrix.kind == 'installed'" in part.split("- name: Arch package (makepkg, pacman)", 1)[1][:60]
    # the engine's cache: by the Cargo.lock, its sources and the compiler
    assert "key: arch-adblock-${{ steps.packages.outputs.rust }}-${{ hashFiles('ike-adblock/Cargo.lock'," in part
    gate = jobs["arch"]
    assert "    name: Arch Linux\n" in gate and "needs: [plan, part]" in gate and "\n    if: always()\n" in gate
    assert "tools/shard-tests.py verify --kind source" in gate and "tools/shard-tests.py verify --kind installed" in gate
    final = gate.split("- name: Every part of Arch Linux passed\n", 1)[1]
    assert final.lstrip().startswith("if: always()") and '("plan", "part")' in final
    assert "\n    if:" not in jobs["plan"].split("steps:", 1)[0] and "\n    if:" not in part.split("steps:", 1)[0]
    assert "needs: arch" in jobs["hand-over"] and "needs: arch" in jobs["merge-ready"]
    # the parts' names: no " / " (a called workflow's check is "<caller> / <job>")
    plan = jobs["plan"]
    for name in ('"Arch Linux shard %d/%d"', '"Arch Linux installed %d/%d"', '"Arch Linux styles"'):
        assert name in plan, name
    # arch-testing.yml calls it as it is
    assert "uses: ./.github/workflows/arch.yml" in (WORKFLOWS / "arch-testing.yml").read_text()


# --- the automatic fix reads the part that failed, not the gate ------------------------------------

def _run(name="Tests", attempt=1):
    return {"name": name, "head_branch": "main", "conclusion": "failure", "head_sha": "abc", "run_attempt": attempt,
            "head_repository": {"full_name": "o/r"}, "_repo": "o/r", "_tip": "abc", "_main_tip": "main1",
            "_attempts": 0, "_engine_update": False, "_tests": "success"}


def _job(name, *steps):
    return {"name": name, "conclusion": "failure", "steps": [{"name": s, "conclusion": "failure"} for s in steps]}


@pytest.mark.parametrize("workflow, jobs_, action, kind", [
    # a shard's set-up failed (GitHub's or the runner's): the gate's "Tests" says it again, an issue as before
    ("Tests", [_job("tests shard 2/4", "Test environment"), _job("tests", "Tests", "Every part of the tests passed")],
     "issue", "infra"),
    ("Tests", [_job("tests package", "Packaging tools"), _job("tests", "Tests of the installed package")],
     "issue", "infra"),
    # a test failed in a shard: run once more first, as the one job's "Tests" was
    ("Tests", [_job("tests shard 3/4", "Tests"), _job("tests", "Tests")], "rerun", ""),
    ("Tests", [_job("tests installed 1/4", "Tests of the installed package"), _job("tests", "Tests of the installed "
                                                                                      "package")], "rerun", ""),
    # with a lint error too: never "only sometimes"
    ("Tests", [_job("tests shard 3/4", "Tests"), _job("tests checks", "Lint"), _job("tests", "Tests", "Lint")],
     "fix", "main"),
    # the gate alone: a test that did not run, or ran twice, is the gate's own failure
    ("Tests", [_job("tests", "Tests")], "rerun", ""),
    ("Tests", [_job("tests", "Run actions/download-artifact@9000")], "issue", "infra"),
    # Arch: a part's pacman, the gate after it
    ("Arch Linux", [_job("Arch Linux installed 2/4", "Arch's packages"), _job("Arch Linux", "Tests of the installed "
                                                                                         "package (Arch)")],
     "issue", "infra"),
    ("Arch Linux", [_job("Arch Linux shard 1/4", "Tests (Arch's Qt)"), _job("Arch Linux", "Tests (Arch's Qt)")],
     "rerun", ""),
])
def test_the_plan_reads_the_failed_part_not_the_gate(workflow, jobs_, action, kind):
    p = plan_tool.decide(_run(workflow), jobs_, "")
    assert (p["action"], p["kind"]) == (action, kind), p
    # the second time a test fails, the AI fixes it, reading the shard's own failure
    if action == "rerun":
        p = plan_tool.decide(_run(workflow, attempt=2), jobs_, "")
        assert p["action"] == "fix", p
        if workflow == "Tests":
            assert p["reason"].endswith("(jobs: %s)" % jobs_[0]["name"]), p      # the part, not the gate


def test_the_gate_is_set_aside_only_when_a_part_failed():
    gate, part, hand = _job("tests", "Tests"), _job("tests shard 1/4", "Tests"), _job("hand-over", "Hand")
    assert plan_tool.without_gate("Tests", [gate, part, hand]) == [part, hand]
    assert plan_tool.without_gate("Tests", [gate, hand]) == [gate, hand]       # a reporting job is no part
    assert plan_tool.without_gate("Tests", [gate]) == [gate]
    arch = _job("Arch Linux", "Tests (Arch's Qt)")
    assert plan_tool.without_gate("Arch Linux (testing)", [arch, _job("Arch Linux styles", "x")])[0]["name"] != \
        "Arch Linux"
    assert plan_tool.without_gate("Security", [_job("sandbox", "x"), _job("tests", "y")])[1]["name"] == "tests"


# --- the review of 2026-11-24 (seven findings), each held here ----------------------------------------

def test_every_shard_records_its_run_and_the_gate_checks_it(ran, tmp_path):
    """Finding 7: a shard's results name the commit, the run and its attempt, and (installed) the copy
    and the package tested; the gate refuses results it cannot tie to this commit and this run."""
    out, ref = _copy(ran, tmp_path)
    rec = json.loads((out / "part-1" / "shard.json").read_text())
    assert (rec["sha"], rec["run"], rec["attempt"], rec["app"], rec["package_sha256"]) == ("s1", "r1", "1", "", "")
    assert any("--sha" in p for p in _verify(out, ref, sha="")[0])
    assert any("--run-id" in p for p in _verify(out, ref, run_id="")[0])
    assert any("is of run" in p for p in _verify(out, ref, run_id="r2")[0])
    for change, said in (({"sha": ""}, "ran commit ''"), ({"run": "r0"}, "is of run 'r0'"),
                         ({"app": "/usr/lib/ike-browser"}, "tested an installed copy")):
        out, ref = _copy(ran, tmp_path / said[:12].replace(" ", "-").replace("'", ""))
        rec = json.loads((out / "part-2" / "shard.json").read_text())
        rec.update(change)
        (out / "part-2" / "shard.json").write_text(json.dumps(rec))
        assert any(said in p for p in _verify(out, ref)[0]), (said, _verify(out, ref)[0])
    # the same results as the installed package's: they must name the copy and the package tested
    out, ref = _copy(ran, tmp_path / "installed")
    for k in range(1, SHARDS + 1):
        f = out / ("part-%d" % k) / "shard.json"
        rec = json.loads(f.read_text())
        rec.update(kind="installed", app="/usr/lib/ike-browser", package_sha256="ab" * 32)
        f.write_text(json.dumps(rec))
    assert _verify(out, ref, kind="installed", package_sha256="ab" * 32)[0] == []
    assert any("another package" in p for p in _verify(out, ref, kind="installed", package_sha256="cd" * 32)[0])
    rec = json.loads((out / "part-3" / "shard.json").read_text())
    rec.update(app="", package_sha256="")
    (out / "part-3" / "shard.json").write_text(json.dumps(rec))
    problems = _verify(out, ref, kind="installed")[0]
    assert any("tested no installed copy" in p for p in problems) and any("recorded no package" in p for p in problems)


def test_a_missing_independent_collection_fails_but_the_rest_is_still_checked(ran, tmp_path):
    """Finding 2: the job that collects stopped early (a lint error): the gate says so and goes on with
    the shards' own lists and the merge, never a crash."""
    out, ref = _copy(ran, tmp_path)
    merged = tmp_path / "junit.xml"
    problems, report = _verify(out, tmp_path / "no-such" / "collected.txt", merged_junit=merged)
    assert problems == ["the independent collection is missing (%s)" % (tmp_path / "no-such" / "collected.txt")]
    assert merged.exists() and "13 tests collected" in report[0]
    run = subprocess.run([sys.executable, str(ROOT / "tools/shard-tests.py"), "verify", "--kind", "source",
                          "--shards", str(SHARDS), "--dir", str(out), "--collected", str(tmp_path / "none.txt"),
                          "--sha", "s1", "--run-id", "r1", "--timings", str(out / "none.json")],
                         capture_output=True, text=True, timeout=60)
    assert run.returncode == 1 and "independent collection is missing" in run.stdout and "Traceback" not in run.stderr
    # and the collection is the first step of "tests checks", right after the environment
    checks = _jobs((WORKFLOWS / "tests.yml").read_text())["checks"]
    assert _steps(checks)[:2] == ["Test environment", "The tests to run"]


def test_a_shard_of_files_skipped_whole_passes_and_a_skipped_class_counts(tmp_path, monkeypatch):
    """Finding 5: pytest ends with "no tests" (exit 5) when every file it runs is skipped whole; that
    shard passed, and its skips are still in its junit for the gate."""
    root = tmp_path / "repo"
    for rel in ("pyproject.toml", "tests/test_d.py", "tests/test_a.py", "tests/conftest.py", "tests/test_g.py"):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(SUITE[rel])
    (root / "tests/test_g.py").write_text("class TestSkipped:\n    def test_never(self):\n        pass\n")
    timings = tmp_path / "t.json"
    timings.write_text(json.dumps({"default": 1, "files": {"tests/test_a.py": 100}}))
    monkeypatch.setenv("GITHUB_SHA", "s1")
    monkeypatch.setenv("GITHUB_RUN_ID", "r1")
    monkeypatch.delenv("IKE_TEST_APP", raising=False)
    codes = [shards.run_shard("source", k, 2, tmp_path / ("part-%d" % k), timings_path=timings, cwd=root)
             for k in (1, 2)]
    parts = [json.loads((tmp_path / ("part-%d" % k) / "shard.json").read_text())["files"] for k in (1, 2)]
    assert parts == [["tests/test_a.py"], ["tests/test_d.py", "tests/test_g.py"]] and codes == [0, 0]
    shards.collect(tmp_path / "ref.txt", cwd=root)
    problems, report = shards.verify("source", 2, tmp_path, [tmp_path / "ref.txt"], sha="s1", run_id="r1",
                                     timings_path=timings)
    assert problems == [] and "2 skipped (not verified)" in report[0], problems
    # a failing file next to a skipped one keeps its failure
    (root / "tests/test_d.py").write_text(SUITE["tests/test_d.py"] + "\n\ndef test_x():\n    pass\n")
    (root / "tests/test_g.py").write_text("def test_bad():\n    assert 0\n")
    assert shards.run_shard("source", 2, 2, tmp_path / "again", timings_path=timings, cwd=root) == 1


def test_the_gate_failing_alone_is_never_an_ais(tmp_path):
    """Finding 4: a part cancelled or out of time, results missing, a test that did not run exactly
    once, the Arch parts on other packages: the whole run once more, then an issue; never a fix."""
    parts = {"tests plan": "success", "tests shard 1/4": "success", "tests shard 2/4": "cancelled",
             "tests installed 1/4": "success", "tests checks": "success"}
    for workflow, gate, step, stopped in (
            ("Tests", "tests", "Tests", parts),
            ("Tests", "tests", "Run actions/download-artifact@9000", dict(parts, **{"tests shard 2/4": "success"})),
            ("Arch Linux", "Arch Linux", "The same Arch packages in every part",
             {"Arch Linux plan": "success", "Arch Linux shard 1/4": "success", "Arch Linux styles": "success"}),
            ("Arch Linux", "Arch Linux", "Tests (Arch's Qt)", {"Arch Linux shard 1/4": "timed_out"})):
        jobs_ = [_job(gate, step), _job("hand-over", "Hand the failure to the automatic fix")]
        first = plan_tool.decide(dict(_run(workflow), _parts=stopped), jobs_, "")
        assert (first["action"], first.get("rerun")) == ("rerun", "all"), first
        if "cancelled" in stopped.values() or "timed_out" in stopped.values():
            assert "cancelled or out of time" in first["reason"], first
        again = plan_tool.decide(dict(_run(workflow, attempt=2), _parts=stopped), jobs_, "")
        assert (again["action"], again["kind"]) == ("issue", "infra"), again
    # a part that failed is still the part's (the gate set aside), as before
    p = plan_tool.decide(dict(_run(), _parts=parts), [_job("tests shard 1/4", "Tests"), _job("tests", "Tests")], "")
    assert p["action"] == "rerun" and "rerun" not in p
    # the automatic fix runs the whole run again when the plan says "all"
    rerun = _jobs((WORKFLOWS / "autofix.yml").read_text())["rerun"]
    assert "WHICH: ${{ needs.plan.outputs.rerun }}" in rerun and 'retry gh run rerun "$RUN_ID"\n' in rerun
    assert 'if [ "$WHICH" = all ]; then' in rerun and 'gh run rerun "$RUN_ID" --failed' in rerun
    assert "rerun: ${{ steps.plan.outputs.rerun }}" in _jobs((WORKFLOWS / "autofix.yml").read_text())["plan"]


def test_a_cancelled_run_is_not_handed_over_nor_planned():
    """Finding 3: a cancelled run's gate runs (if: always()) and fails: no hand-over, no plan."""
    for name, gate in (("tests.yml", "tests"), ("arch.yml", "arch")):
        hand = _jobs((WORKFLOWS / name).read_text())["hand-over"]
        assert "needs: %s" % gate in hand and "failure() && !cancelled() && (" in hand, name
    p = plan_tool.decide(dict(_run(), conclusion="cancelled", _parts={"tests shard 1/4": "cancelled"}),
                         [_job("tests", "Tests")], "")
    assert p["action"] == "skip" and p["reason"].startswith("cancelled"), p


def test_the_installed_suite_is_held_to_the_sources_collection():
    """Finding 6: the installed shards' ids are compared with an independent collection of the sources."""
    tests = _jobs((WORKFLOWS / "tests.yml").read_text())["tests"]
    installed = tests.split("- name: Tests of the installed package\n", 1)[1].split("\n      - ", 1)[0]
    assert '--collected "$RUNNER_TEMP/parts/tests-checks/collected.txt"' in installed
    assert '--package-sha256 "$PACKAGE"' in installed and "PACKAGE: ${{ needs.package.outputs.sha256 }}" in installed
    shard = _jobs((WORKFLOWS / "tests.yml").read_text())["installed"]
    assert "IKE_PACKAGE_SHA256: ${{ needs.package.outputs.sha256 }}" in shard
    arch = _jobs((WORKFLOWS / "arch.yml").read_text())
    collect = arch["part"].split("- name: The tests to run\n", 1)[1].split("\n      - ", 1)[0]
    assert "if: matrix.kind == 'styles'" in collect and "tools/shard-tests.py collect --out out/collected.txt" in collect
    for kind in ("source", "installed"):
        step = arch["arch"].split("verify --kind %s" % kind, 1)[1].split("\n      - ", 1)[0]
        assert '--collected "$RUNNER_TEMP/parts/arch-styles-0/collected.txt"' in step and "--run-id" in step, kind
    assert "IKE_PACKAGE_SHA256=$(sha256sum out/ike-browser-" in arch["part"]


def _same_packages_script():
    gate = _jobs((WORKFLOWS / "arch.yml").read_text())["arch"]
    body = gate.split("- name: The same Arch packages in every part\n", 1)[1].split("\n      - ", 1)[0]
    assert "if: ${{ !cancelled() }}" in body
    import textwrap
    script = body.split("<<'PY'\n", 1)[1].split("\n          PY", 1)[0]
    return textwrap.dedent(script)


@pytest.mark.parametrize("change, ok", [
    (None, True),
    ({"date": "2026-11-25T00:00:00Z", "run": "2"}, True),            # when and where it ran: not the packages
    ({"packages": {"qt6-webengine": "6.141.0-1"}}, False),
    ({"closure": {"mesa": "1:26.0-2"}}, False),
    ("missing", False),
])
def test_the_arch_parts_must_have_tested_the_same_packages(tmp_path, change, ok):
    """Finding 1: the gate fails when a part had other Arch packages, or a part's record is missing."""
    record = {"schema": 1, "packages": {"qt6-webengine": "6.140.0-1"}, "closure": {"mesa": "1:26.0-1"},
              "python": "3.14.1", "qt": "6.12.0", "pyqt": "6.12.1", "chromium": "140", "date": "x", "run": "1"}
    names = ["arch-source-1", "arch-source-2", "arch-installed-1", "arch-installed-2", "arch-styles-0"]
    for i, name in enumerate(names):
        rec = dict(record)
        if i == 2 and isinstance(change, dict):
            rec.update(change)
        if i == 2 and change == "missing":
            continue
        (tmp_path / name).mkdir()
        (tmp_path / name / "arch-versions.json").write_text(json.dumps(rec))
    (tmp_path / "arch-versions").mkdir()                       # the record kept for the daily check: not a part
    (tmp_path / "arch-versions" / "arch-versions.json").write_text("{}")
    run = subprocess.run([sys.executable, "-I", "-", str(tmp_path), "2"], input=_same_packages_script(),
                         capture_output=True, text=True, timeout=60)
    assert (run.returncode == 0) is ok, run.stdout + run.stderr
    if not ok:
        assert "::error::" in run.stdout


def test_every_arch_part_installs_one_snapshot_of_arch():
    """Finding 1: the plan picks one day of the Arch Linux Archive (today's when it is there, the testing
    repositories too for arch-testing.yml); every part reads its databases from it and nothing else."""
    arch = _jobs((WORKFLOWS / "arch.yml").read_text())
    plan = arch["plan"]
    assert "snapshot: ${{ steps.snapshot.outputs.snapshot }}" in plan
    assert 'for day in "$(date -u +%Y/%m/%d)" "$(date -u -d yesterday +%Y/%m/%d)"; do' in plan
    assert 'url="https://archive.archlinux.org/repos/$day"' in plan
    assert 'repos="$repos core-testing extra-testing"' in plan and "TESTING: ${{ inputs.testing && 'true' || 'false' }}" in plan
    part = arch["part"]
    names = _steps(part)
    assert names.index("Arch's testing repositories (arch-testing.yml only)") < names.index("Arch's snapshot") < \
        names.index("Git (for the checkout)") < names.index("Arch's packages")
    snap = part.split("- name: Arch's snapshot\n", 1)[1].split("\n      - ", 1)[0]
    assert "SNAPSHOT: ${{ needs.plan.outputs.snapshot }}" in snap
    # the databases come from the snapshot alone (curl, retried, dropped when too slow), then
    # pacman's mirrorlist ends with it; only when they did not come, Arch's mirrors with a warning
    assert '"$SNAPSHOT/$repo/os/x86_64/$repo.db"' in snap and "--speed-limit" in snap and "--retry" in snap
    assert "install -m644 /tmp/sync/*.db /var/lib/pacman/sync/" in snap
    assert 'echo "Server = $SNAPSHOT/\\$repo/os/\\$arch"; } > /tmp/mirrorlist' in snap
    assert snap.count("pacman -Syy") == 2 and snap.count("::warning::") == 2
    assert snap.index("install -m644") < snap.index("pacman -Syy")
    # after it no database is read again: the upgrade and the installs use the snapshot's
    after = part.split("- name: Arch's snapshot\n", 1)[1].split("\n      - ", 1)[1]
    assert "pac -Su --noconfirm --needed git" in after and "pacman -Su" not in after.split("pac() {")[0]
    assert not re.search(r"pacman -S\w*y", after) and "pacman -Sy" not in after
    assert plan_tool.ARCH_INFRA_STEP.match("Arch's snapshot")


def test_a_mirror_without_a_snapshot_file_falls_back_to_the_archive():
    """2026-11-25: a mirror had already dropped zxing-cpp-3.1.1-1's signature, pacman gave
    up and every Arch run of AUTOMAT's candidates failed. The packages and git steps retry
    with the snapshot's own archive alone, which keeps every version."""
    text = (ROOT / ".github/workflows/arch.yml").read_text("utf-8")
    assert text.count("grep -m1 '^Server = https://archive.archlinux.org/' /etc/pacman.d/mirrorlist") == 2
    assert 'pac -S --noconfirm --needed "${pkgs[@]}"' in text
    assert "pac -Su --noconfirm --needed git" in text


def test_a_slow_archive_is_asked_again_with_the_mirrors_after_it():
    """2026-11-27: the fallback to the archive alone failed on main, every part at once: the archive sent nothing
    for 10 s ("Operation too slow") and pacman gave up. The retry puts the archive first and the mirrors after it,
    so each file comes from the first server that has it in time, and asks again after growing pauses."""
    text = (ROOT / ".github/workflows/arch.yml").read_text("utf-8")
    assert text.count("pac() {") == 2
    body = text.split("pac() {", 1)[1].split("\n          }\n", 1)[0]
    assert 'printf \'%s\\n%s\\n\' "$archive" "$mirrors" > /tmp/mirrorlist.again' in body
    assert "for pause in 30 120 300; do" in body and 'pacman --disable-download-timeout "$@" && return 0' in body
    assert "ParallelDownloads = 1" in body and body.rstrip().endswith("return 1")
    assert 'echo "$archive" > /etc/pacman.d/mirrorlist' not in text          # never the archive alone again
