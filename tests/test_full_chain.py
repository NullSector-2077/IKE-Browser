"""The last block of the automatic maintenance (2026-11-22): every updatable external
component through the whole chain by itself, the owner only signs.

End-to-end proofs with no network (WP14): each one walks the real tools, in the order
the workflows call them, with GitHub's and the upstreams' answers stood in:

- a new version of the AdBlock engine (with a new crate) is detected, gets its own
  candidate, its tests fail, the AI adapts I.K.E.'s wrapper, the tests pass, the
  verified merge happens, main's checks start and the release notice follows;
- a change in the full dependency closure of I.K.E.'s Arch packages starts arch.yml;
- a GitHub Action's pin is updated by the tool (never an AI) and merges;
- a builder that refused a new upstream version is re-anchored and merges;
- a major version of a crate of the engine is taken, and the AI adapts the wrapper.

Each new protective rule has a test here that fails without it.
"""

import datetime as dt
import importlib.util
import json
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"
REPO = "o/r"
# the weekly round of the low-risk candidates (tools/update-candidates.py WEEKLY): the chain is proved on a Monday
MONDAY = dt.date(2026, 11, 30)


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_") + "_chain", ROOT / "tools" / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cc = load("check-components")
uc = load("update-candidates")
ci = load("ci-pins")
anchor = load("builder-anchor")
pk = load("pkgbuild-sync")
merge = load("automerge")
guard = load("check-autofix-patch")
plan_tool = load("autofix-plan")
ledger_tool = load("maintenance-ledger")
tc = load("test-categories")
providers = load("ai-providers")
reserve = load("autofix-reserve")
lists_tool = load("filter-lists")


# --- what GitHub would answer --------------------------------------------------------------

CHECKS = [{"name": n, "status": "completed", "conclusion": "success"}
          for n in ("tests", "sandbox", "rust-advisories", "Arch Linux")] + \
         [{"name": "hand-over", "status": "completed", "conclusion": "skipped"}]
EXPECTED = [{"test": "tests/test_sandbox.py::test_on", "area": "security and privacy", "junit": "junit.xml",
             "reason": "IKE_TEST_SANDBOX=1 only (needs a system where the sandbox works)"}]


def runs(filter_lists=True, **changes):
    """Every category's job and step passed on the commit (as tools/maintenance-ledger.py run_info
    reads them); the filter lists' step only when the commit's engine was checked."""
    out = {}
    for cat, (_desc, (workflow, job, step)) in tc.CATEGORIES.items():
        if not workflow or (cat == "filter-lists" and not filter_lists):
            continue
        run = out.setdefault(workflow, {"id": 1, "status": "completed", "conclusion": "success", "jobs": {},
                                        "url": "https://x/runs/1"})
        j = run["jobs"].setdefault(job, {"status": "completed", "conclusion": "success", "steps": {}})
        if step:
            j["steps"][step] = "success"
    for cat, result in changes.items():
        workflow, job, step = tc.CATEGORIES[cat.replace("_", "-")][1]
        out[workflow]["jobs"][job]["steps" if step else "conclusion"] = (
            dict(out[workflow]["jobs"][job]["steps"], **{step: result}) if step else result)
    return out


def pr(ref):
    return {"number": 41, "state": "open", "draft": True, "title": "Update", "base": {"ref": "main"},
            "head": {"ref": ref, "sha": "a" * 40, "repo": {"full_name": REPO}}}


def decide(ref, commits, files, evidence=None, checks=CHECKS, **kw):
    return merge.decide(REPO, pr(ref), commits, files, checks, lambda n: guard.allowed_path(n, False),
                        evidence=evidence or {"runs": runs(), "skips": EXPECTED}, **kw)


def commit(message, files):
    return {"sha": "c" * 40, "commit": {"message": message}, "files": files}


def change(name, patch, old=None, new=None, status="modified"):
    out = {"filename": name, "status": status, "patch": patch}
    if old is not None:
        out.update(old_source=old, new_source=new)
    return out


VERSION_FILES = [
    change("ike/__init__.py", '@@ -5 +5 @@\n-__version__ = "1.1.22"\n+__version__ = "1.1.23"'),
    change("PKGBUILD", "@@ -6 +6 @@\n-pkgver=1.1.22\n+pkgver=1.1.23"),
    change("CHANGELOG.md", "@@ -3,0 +4,3 @@\n+## 1.1.23\n+\n+- adblock-rust: 0.13.6 -> 0.14.0"),
]
AUTOFIX = 'autofix: attempt 1 after a failure of "Tests"\n\nPrepared by the automatic fix...'
LIB_RS = ('@@ -10,3 +10,4 @@\n-const ENGINE_VERSION: &str = "0.13.6";\n+const ENGINE_VERSION: &str = "0.14.0";\n'
          ' fn engine() {}\n-    let r = e.check(a, b);\n+    let r = e.check_network_request(&Request::new(a, b));\n'
          '+    let _ = r.matched;\n')


def test_a_new_engine_goes_through_the_whole_chain_by_itself(monkeypatch, tmp_path):
    """WP14 (1): detected, its own candidate, tests fail, the AI adapts the wrapper, tests pass,
    the verified merge, main's checks, the release notice; the ledger follows every step."""
    # 1. detected: the daily maintenance's check (tools/check-components.py), a new adblock that brings a new crate
    results = [{"id": "adblock", "name": "adblock-rust (AdBlock engine)", "current": "0.13.6", "latest": "0.14.0",
                "update": True, "note": "engine", "also": "", "error": "", "refused": None},
               {"id": "crates", "name": "Rust crates of the AdBlock engine", "current": "", "latest": "",
                "update": True, "note": "", "also": "", "error": "", "refused": None,
                "_candidates": [{"id": "crates", "from": "80 crates", "to": "81 crates", "note": "new: newcrate"}]}]
    report = {"candidates": cc.candidates_of(results)}
    assert [c["id"] for c in report["candidates"]] == ["adblock", "crates"]
    # 2. its own candidate; the crates' one waits (one change of Cargo.lock at a time)
    rows = {r["id"]: r for r in uc.plan(report, {}, today=MONDAY)}
    assert rows["adblock"]["action"] == "make" and rows["adblock"]["branch"] == "automation/update/adblock"
    assert rows["crates"]["action"] == "queued" and "Cargo.lock" in rows["crates"]["reason"]
    message = rows["adblock"]["message"]
    assert message == "update: adblock 0.13.6 -> 0.14.0 (no AI)"
    files = ["ike-adblock/Cargo.toml", "ike-adblock/Cargo.lock", "ike-adblock/src/lib.rs", "licenses/newcrate-MIT",
             "docs/THIRD-PARTY.md", "ike/__init__.py", "PKGBUILD", "CHANGELOG.md"]
    assert uc.commit_problem("adblock", message, files) == ""
    # the ledger: detected, then the candidate's runs
    inv = {"components": [{"id": "adblock-engine:adblock", "kind": "adblock-engine", "name": "adblock",
                           "installed": "0.13.6", "available": "0.14.0", "result": "update available",
                           "origin": ["ike-adblock/Cargo.toml"]}], "findings": []}
    ledger = ledger_tool.update(None, inv, {}, now=ledger_tool.parse_time("2026-11-23T05:30:00Z"))
    key = "adblock-engine:adblock@0.14.0"
    assert ledger["entries"][key]["state"] == "detected"
    # 3. its tests fail (the engine's API changed): the AI fixes that branch, wrapper allowed, Antigravity first
    run = {"name": "Tests", "head_branch": "automation/update/adblock", "conclusion": "failure", "head_sha": "b" * 40,
           "head_repository": {"full_name": REPO}, "_repo": REPO, "_tip": "b" * 40, "_main_tip": "m" * 40,
           "_attempts": 0, "_engine_update": True}
    failed = [{"name": "tests", "conclusion": "failure",
               "steps": [{"name": "AdBlock engine (Rust tests)", "conclusion": "failure"}]}]
    p = plan_tool.decide(run, failed, "")
    assert (p["action"], p["kind"], p["push_branch"], p["allow_adblock"]) == (
        "fix", "update", "automation/update/adblock", "true")
    assert plan_tool.first_provider(p) == "Antigravity"
    status = {"update_branches": {"automation/update/adblock": {
        "branch": "automation/update/adblock", "sha": "b" * 40, "pr": 41, "url": "u", "autofix_commits": 0,
        "runs": runs(unit_integration="failure"), "skips": EXPECTED}}}
    status["update_branches"]["automation/update/adblock"]["runs"]["tests.yml"]["jobs"]["tests"]["steps"][
        "AdBlock engine (Rust tests)"] = "failure"
    ledger = ledger_tool.update(ledger, inv, status, now=ledger_tool.parse_time("2026-11-23T07:00:00Z"))
    assert ledger["entries"][key]["state"] == "fixing"
    assert "automation/update/adblock" in ledger["entries"][key]["reason"]
    # the AI's change of the wrapper passes the guard on that branch
    repo = tmp_path / "repo"
    (repo / "ike-adblock" / "src").mkdir(parents=True)
    (repo / "ike-adblock" / "src" / "lib.rs").write_text("fn a() {\n    let r = e.check(a, b);\n}\n")
    patch = ("diff --git a/ike-adblock/src/lib.rs b/ike-adblock/src/lib.rs\n--- a/ike-adblock/src/lib.rs\n"
             "+++ b/ike-adblock/src/lib.rs\n@@ -1,3 +1,3 @@\n fn a() {\n-    let r = e.check(a, b);\n"
             "+    let r = e.check_network_request(&Request::new(a, b));\n }\n")
    assert guard.check(repo, patch, allow_adblock=True) == []
    assert guard.check(repo, patch, allow_adblock=False)                  # never without an engine update
    # 4. the tests pass (the filter lists in its own engine included): the verified merge
    commits = [commit(message, files), commit(AUTOFIX, ["ike-adblock/src/lib.rs"])]
    pr_files = [change("ike-adblock/Cargo.toml", '@@ -14 +14 @@\n-adblock = { version = "=0.13.6" }\n'
                       '+adblock = { version = "=0.14.0" }'),
                change("ike-adblock/Cargo.lock", '@@ -1,3 +1,3 @@\n [[package]]\n name = "adblock"\n'
                       '-version = "0.13.6"\n+version = "0.14.0"'),
                change("ike-adblock/src/lib.rs", LIB_RS),
                change("licenses/newcrate-MIT", "@@ -0,0 +1 @@\n+MIT", status="added"),
                change("docs/THIRD-PARTY.md", "@@ -1 +1 @@\n-a\n+b")] + VERSION_FILES
    assert decide("automation/update/adblock", commits, pr_files, published=True) == ("merge", "")
    # without the filter lists checked on its own commit it is not verified
    kind, why = decide("automation/update/adblock", commits, pr_files,
                       evidence={"runs": runs(filter_lists=False), "skips": EXPECTED})
    assert kind == "person" and "filter-lists not verified" in why
    status["update_branches"]["automation/update/adblock"].update(runs=runs(), autofix_commits=1)
    ledger = ledger_tool.update(ledger, inv, status, now=ledger_tool.parse_time("2026-11-23T09:00:00Z"))
    assert ledger["entries"][key]["state"] == "passed"
    # 5. merged at exactly that commit; main's Tests, Security and Arch Linux start; then the notice
    calls = []
    monkeypatch.setattr(merge, "gh", lambda *a: calls.append(a) or "")
    monkeypatch.setattr(merge, "api", lambda path: [])
    merge.merge_it(REPO, pr("automation/update/adblock"), "a" * 40)
    flat = [" ".join(c) for c in calls]
    assert any("repos/o/r/pulls/41/merge" in c and "sha=" + "a" * 40 in c for c in flat), flat
    for wf in ("tests.yml", "security.yml", "arch.yml"):
        assert "workflow run %s --repo o/r --ref main" % wf in flat, flat
    tests = (WORKFLOWS / "tests.yml").read_text().split("\n  merge-ready:\n", 1)[1]
    assert 'gh workflow run release-ready.yml --ref main' in tests
    rr = (WORKFLOWS / "release-ready.yml").read_text()
    assert "python3 tools/publish.py" in rr and "(merged by itself" in rr


def test_the_crates_wait_one_change_of_cargo_lock_at_a_time():
    """Idempotent and serialised: an open security fix or another candidate holds Cargo.lock; the same
    candidate open already is rebuilt, never opened twice; the test packages wait for each other."""
    report = {"candidates": [{"id": "crates", "from": "a", "to": "b"}, {"id": "pyo3", "from": "0.30", "to": "0.31"},
                             {"id": "test-qt", "from": "1", "to": "2"}, {"id": "test-tools", "from": "1", "to": "2"},
                             {"id": "darkreader", "from": "1", "to": "2"}]}
    rows = {r["id"]: r for r in uc.plan(report, {"automation/update/security-rustsec-2026-0001": {"pr": 9}}, today=MONDAY)}
    assert rows["crates"]["action"] == rows["pyo3"]["action"] == "queued"
    assert rows["test-qt"]["action"] == "make" and rows["test-tools"]["action"] == "queued"
    assert rows["darkreader"]["action"] == "make"
    rows = {r["id"]: r for r in uc.plan(report, {"automation/update/pyo3": {"pr": 12}}, today=MONDAY)}
    assert rows["pyo3"]["action"] == "make" and "PR #12" in rows["pyo3"]["reason"]      # rebuilt, not duplicated
    assert rows["crates"]["action"] == "queued" and "automation/update/pyo3" in rows["crates"]["reason"]
    # an unreachable source makes nothing; a refused builder starts the builders' path once
    report = {"candidates": [{"id": "ubo-scriptlets", "error": "source unreachable: git clone"},
                             {"id": "darkreader", "refused": True, "step": "patch 'style-moves'"}]}
    rows = {r["id"]: r for r in uc.plan(report, {}, today=MONDAY)}
    assert rows["ubo-scriptlets"]["action"] == "unreachable"
    assert rows["darkreader"]["action"] == "builder" and rows["darkreader"]["branch"] == "automation/builder/darkreader"
    again = {r["id"]: r for r in uc.plan(report, {"automation/builder/darkreader": {"pr": 3}}, today=MONDAY)}
    assert again["darkreader"]["action"] == "skip"
    assert [m["id"] for m in uc.matrix(uc.plan(report, {}, today=MONDAY))] == ["darkreader"]


def test_an_update_commit_changes_only_its_own_files():
    """The update's own commit of one candidate may not change another component's files, a protected
    file, or the version when it ships nothing; a candidate id is never taken from a stranger's text."""
    msg = "update: darkreader 4.9.1 -> 4.9.2 (no AI)"
    assert uc.commit_problem("darkreader", msg, ["ike/resources/darkreader.js", "CHANGELOG.md"]) == ""
    assert "may not change" in uc.commit_problem("darkreader", msg, ["ike/resources/ubo-scriptlets.json"])
    assert "may not change" in uc.commit_problem("darkreader", msg, ["ike/updater.py"])
    assert "not the update's own commit" in uc.commit_problem("adblock", msg, ["ike/resources/darkreader.js"])
    tools = "update: test-tools pytest 9.1.1 -> 9.2.0 (no AI)"
    assert uc.commit_problem("test-tools", tools, ["tools/test-requirements.txt"]) == ""
    assert "version may not move" in uc.commit_problem("test-tools", tools, ["tools/test-requirements.txt",
                                                                             "ike/__init__.py"])
    assert uc.spec("rm -rf") is None and uc.id_of_branch("automation/update/../main") == ""
    assert uc.id_of_branch("automation/builder/adblock") == ""        # only a builder has the builders' path
    # tools/automerge.py reads the same rule: another component's file keeps it for a person
    commits = [commit(msg, ["ike/resources/darkreader.js", "ike/resources/ubo-scriptlets.json"])]
    files = [change("ike/resources/darkreader.js", "@@ -1 +1 @@\n-a\n+b"),
             change("ike/resources/ubo-scriptlets.json", "@@ -1 +1 @@\n-a\n+b")]
    kind, why = decide("automation/update/darkreader", commits, files)
    assert kind == "person" and "ubo-scriptlets.json" in why


# --- the Arch closure ------------------------------------------------------------------------

QI = """Name            : qt6-webengine
Version         : 6.10.1-1
Depends On      : qt6-base  nss  libva.so=2-64  ffmpeg>=7
Provides        : None

Name            : qt6-base
Version         : 6.10.1-1
Depends On      : icu  mesa
Provides        : None

Name            : nss
Version         : 3.117-1
Depends On      : None
Provides        : None

Name            : libva
Version         : 2.22.0-1
Depends On      : None
Provides        : libva.so=2-64

Name            : ffmpeg
Version         : 2:7.1-3
Depends On      : None
Provides        : None

Name            : icu
Version         : 77.1-1
Depends On      : None
Provides        : None

Name            : mesa
Version         : 1:25.2.0-1
Depends On      : None
Provides        : None

Name            : unrelated
Version         : 1-1
Depends On      : None
Provides        : None
"""


def test_the_whole_closure_is_recorded_and_a_change_starts_arch(tmp_path):
    """WP14 (2), WP10 (a): arch.yml records every package pacman installed for I.K.E. (Mesa, ffmpeg,
    NSS, ICU, the virtual libva.so), and one of them in another version in Arch starts arch.yml."""
    closure = cc.dependency_closure(["qt6-webengine"], cc.parse_pacman_qi(QI))
    assert closure == {"ffmpeg": "2:7.1-3", "icu": "77.1-1", "libva": "2.22.0-1", "mesa": "1:25.2.0-1",
                       "nss": "3.117-1", "qt6-base": "6.10.1-1", "qt6-webengine": "6.10.1-1"}
    out = tmp_path / "arch-versions.json"
    cc.record_arch(out, query=lambda: "", probe=lambda: "{}", qi=lambda: QI)
    assert "mesa" in json.loads(out.read_text())["closure"]
    versions = {n: "1-1" for n in cc.ARCH_PACKAGES}

    def site(url, timeout=30):
        name = url.rsplit("=", 1)[1]
        return json.dumps({"results": [{"pkgname": name, "repo": "extra", "pkgver": "1", "pkgrel": "1"}]}).encode()
    saved = {"tested": {"packages": dict(versions), "closure": closure}}
    same = cc.check_arch(saved, get=site, db=(dict(closure), {}))
    assert same["state"] == "same" and same["closure_changed"] == []
    moved = cc.check_arch(saved, get=site, db=(dict(closure, mesa="1:25.2.1-1"), {}))
    assert moved["state"] == "changed" and moved["closure_changed"] == [("mesa", "1:25.2.0-1", "1:25.2.1-1")]
    assert "| mesa | 1:25.2.0-1 | 1:25.2.1-1 |" in cc.arch_markdown(moved)
    # the repositories' databases that cannot be read: never a change, said
    down = cc.check_arch(saved, get=site, db=({}, {"extra": "OSError: down"}))
    assert down["state"] == "unreachable"
    # and "changed" is what starts arch.yml on main (daily-check.yml, job start-arch)
    daily = (WORKFLOWS / "daily-check.yml").read_text().split("\n  start-arch:\n", 1)[1]
    assert "needs.check.outputs.arch == 'changed'" in daily and "gh workflow run arch.yml --ref main" in daily
    assert "--arch arch-tested.json" in (WORKFLOWS / "daily-check.yml").read_text()


def test_a_repository_database_is_read():
    import io
    import tarfile
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, ver in (("mesa", "1:25.2.1-1"), ("nss", "3.118-1")):
            data = ("%%NAME%%\n%s\n\n%%VERSION%%\n%s\n" % (name, ver)).encode()
            info = tarfile.TarInfo("%s-%s/desc" % (name, ver))
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    assert cc.parse_repo_db(buf.getvalue()) == {"mesa": "1:25.2.1-1", "nss": "3.118-1"}
    versions, errors = cc.arch_repo_versions(("core",), get=lambda url, timeout=0: buf.getvalue())
    assert versions["nss"] == "3.118-1" and errors == {}
    versions, errors = cc.arch_repo_versions(("core",), get=lambda url, timeout=0: (_ for _ in ()).throw(OSError("x")))
    assert versions == {} and "OSError" in errors["core"]


def test_arch_testing_runs_weekly_and_its_fix_needs_stable_and_testing():
    """WP10 (b): arch.yml once a week with Arch's testing repositories; its failure on main is fixed on
    automation/update/arch-testing-<date>, which merges only with both runs green."""
    wf = (WORKFLOWS / "arch-testing.yml").read_text()
    assert "uses: ./.github/workflows/arch.yml" in wf and "testing: true" in wf and "schedule:" in wf
    assert "gh workflow run arch-testing.yml --ref main" in wf          # the run the automation hands over
    arch = (WORKFLOWS / "arch.yml").read_text()
    assert "workflow_call:" in arch and "[core-testing]" in arch and "[extra-testing]" in arch
    assert "if: inputs.testing" in arch
    run = {"name": "Arch Linux (testing)", "head_branch": "main", "conclusion": "failure", "head_sha": "s" * 40,
           "head_repository": {"full_name": REPO}, "_repo": REPO, "_tip": "s" * 40, "_main_tip": "s" * 40,
           "_attempts": 0, "_engine_update": False, "_tests": "success", "created_at": "2026-11-25T04:30:00Z"}
    failed = [{"name": "Arch Linux", "conclusion": "failure",
               "steps": [{"name": "AdBlock engine", "conclusion": "failure"}]}]
    p = plan_tool.decide(run, failed, "")
    assert (p["action"], p["kind"], p["push_branch"]) == ("fix", "arch-testing",
                                                          "automation/update/arch-testing-2026-11-25")
    assert p["checkout"] == "s" * 40 and p["attempt"] == "1"
    assert plan_tool.decide(dict(run, _tests="failure"), failed, "")["action"] == "skip"
    waiting = plan_tool.decide(dict(run, _arch_testing_open={"automation/update/arch-testing-2026-11-18": 5}),
                               failed, "")
    assert waiting["action"] == "skip" and "already waits" in waiting["reason"]
    # the merge waits for the testing run, and needs it green
    ref = "automation/update/arch-testing-2026-11-25"
    commits = [commit(AUTOFIX.replace('"Tests"', '"Arch Linux (testing)"'),
                      ["ike/window.py"] + [v["filename"] for v in VERSION_FILES])]
    code = change("ike/window.py", "@@ -1 +1 @@\n-a = 1\n+a = 2", "a = 1\n", "a = 2\n")
    kind, why = decide(ref, commits, [code] + VERSION_FILES)
    assert kind == "wait" and "Arch Linux (testing)" in why
    testing = CHECKS + [{"name": "Arch Linux (testing) / Arch Linux", "status": "completed", "conclusion": "success"},
                        {"name": "Arch Linux (testing) / merge-ready", "status": "in_progress"}]
    assert decide(ref, commits, [code] + VERSION_FILES, checks=testing) == ("merge", "")
    red = [dict(c, conclusion="failure") if c["name"].endswith("/ Arch Linux") else c for c in testing]
    assert decide(ref, commits, [code] + VERSION_FILES, checks=red)[0] == "person"


# --- the workflows' pins -----------------------------------------------------------------------

OLD_SHA, NEW_SHA = "1" * 40, "2" * 40
WORKFLOW = ("jobs:\n  t:\n    steps:\n      - uses: actions/checkout@%s # v7.0.1\n"
            "      - uses: actions/cache@%s # v6.1.0\n      - run: cargo install --locked cargo-deny@0.20.2\n")


def tags(repo):
    return {"actions/checkout": {"v7.0.1": OLD_SHA, "v7.1.0": NEW_SHA, "v8.0.0-beta": "9" * 40},
            "actions/cache": {"v6.1.0": "3" * 40}}.get(repo, {})


def test_an_action_pin_takes_the_tool_path_and_merges(tmp_path):
    """WP14 (3), item 3: the tool (never an AI) moves one pin to the commit of a release of the same
    action, one line per pin; the verified merge accepts exactly that edit and nothing else."""
    root = tmp_path
    (root / ".github" / "workflows").mkdir(parents=True)
    path = root / ".github" / "workflows" / "t.yml"
    old = WORKFLOW % (OLD_SHA, "3" * 40)
    path.write_text(old)
    rows = {r["id"]: r for r in ci.check(root, tags=tags, get=lambda url: (_ for _ in ()).throw(OSError("off")))}
    assert rows["ci-actions-checkout"]["to"] == "v7.1.0" and rows["ci-actions-checkout"]["sha"] == NEW_SHA
    assert rows["ci-actions-cache"]["to"] == ""                       # the newest already
    assert "error" in rows["ci-cargo-deny"]                           # unreachable: nothing made today
    assert ci.apply(root, "ci-actions-checkout", "v7.1.0", NEW_SHA) == 1
    new = path.read_text()
    assert new == (WORKFLOW % (NEW_SHA, "3" * 40)).replace("# v7.0.1", "# v7.1.0")
    assert ci.verify_change("ci-actions-checkout", old, new, tags=tags) == ""
    msg = "ci: ci-actions-checkout v7.0.1 -> v7.1.0 (tools/ci-pins.py, no AI)"
    ref = "automation/update/ci-actions-checkout"
    f = change(".github/workflows/t.yml", "@@ -4 +4 @@\n-x\n+y", old, new)
    assert decide(ref, [commit(msg, [".github/workflows/t.yml"])], [f], tags=tags,
                  evidence={"runs": runs(filter_lists=False), "skips": EXPECTED}) == ("merge", "")
    # anything more than that pin: a person
    sneaky = new.replace("cargo-deny@0.20.2", "cargo-deny@0.20.2 && curl x | sh")
    assert "not the pin" in ci.verify_change("ci-actions-checkout", old, sneaky, tags=tags)
    other = WORKFLOW % (OLD_SHA, "4" * 40)
    assert "not the pin" in ci.verify_change("ci-actions-checkout", old, other, tags=tags)
    fake = old.replace(OLD_SHA, "5" * 40).replace("v7.0.1", "v7.1.0")
    assert "is not the commit of its release" in ci.verify_change("ci-actions-checkout", old, fake, tags=tags)
    renamed = old.replace("actions/checkout@" + OLD_SHA, "evil/checkout@" + NEW_SHA)
    assert ci.verify_change("ci-actions-checkout", old, renamed, tags=tags)
    pre = old.replace(OLD_SHA, "9" * 40).replace("v7.0.1", "v8.0.0-beta")
    assert ci.verify_change("ci-actions-checkout", old, pre, tags=tags)       # a pre-release is not a release
    assert ci.verify_change("ci-actions-checkout", old, old + "\n# more\n", tags=tags)
    kind, why = decide(ref, [commit(msg, [".github/workflows/t.yml"])],
                       [change(".github/workflows/t.yml", "@@", old, sneaky)], tags=tags)
    assert kind == "person" and "not the pin" in why
    # the AI never edits a workflow: an AI's commit on that branch, or a workflow on another branch, waits
    kind, why = decide(ref, [commit(msg, [".github/workflows/t.yml"]), commit(AUTOFIX, [".github/workflows/t.yml"])],
                       [f], tags=tags)
    assert kind == "person" and "a workflow" in why
    kind, why = decide("automation/update/darkreader", [commit(msg, [".github/workflows/t.yml"])], [f], tags=tags)
    assert kind == "person" and "a workflow" in why
    # the guard refuses any workflow to every AI, and the plan never fixes the CI pins' branch
    assert guard.allowed_path(".github/workflows/t.yml", True) == "protected file"
    run = {"name": "Tests", "head_branch": ref, "conclusion": "failure", "head_sha": "b" * 40,
           "head_repository": {"full_name": REPO}, "_repo": REPO, "_tip": "b" * 40, "_main_tip": "m" * 40,
           "_attempts": 0, "_engine_update": False}
    p = plan_tool.decide(run, [{"name": "tests", "conclusion": "failure",
                                "steps": [{"name": "Lint", "conclusion": "failure"}]}], "")
    # an AI never edits a workflow (tier B): the candidate stays open and is tried again, nobody is asked
    assert p["action"] == "retry" and "never edits a workflow" in p["reason"] and "stays open" in p["reason"]


def test_the_tools_pins_and_dependabot_are_decided_and_documented():
    """Item 3: the decision on Dependabot (kept monthly as a double check) is written where it applies."""
    dep = (ROOT / ".github" / "dependabot.yml").read_text()
    assert "package-ecosystem: github-actions" in dep and "double check" in dep and "tools/ci-pins.py" in dep
    scan = ci.scan(ROOT)
    assert {"ci-actions-checkout", "ci-cargo-deny", "ci-python", "ci-node", "ci-rust"} <= set(scan)
    assert all(len(v["shas"]) <= 1 for k, v in scan.items() if v["kind"] == "action"), scan
    doc = (ROOT / "docs" / "MAINTENANCE.md").read_text()
    assert "IKE_WORKFLOW_TOKEN" in doc and "tools/ci-pins.py" in doc


# --- the builders' re-anchoring ---------------------------------------------------------------

BUILDER = '''import re

PATCHES = [
    ("alpha", "function a() {\\n    return 1;\\n}", "function a() {\\n    return 2;\\n}"),
    ("beta", "var b = 1;", "var b = 2;"),
]


def apply_patches(engine):
    return engine
'''


def _git(cwd, *args):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-C", str(cwd), *args],
                          capture_output=True, text=True, check=True).stdout


def _builder_repo(tmp_path, text=BUILDER):
    repo = tmp_path / "b"
    (repo / "tools").mkdir(parents=True)
    (repo / "tools" / "build-darkreader.py").write_text(text)
    _git(tmp_path, "init", "-q", str(repo))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "base")
    return repo


def _patch(repo, new_text):
    (repo / "tools" / "build-darkreader.py").write_text(new_text)
    diff = _git(repo, "diff")
    _git(repo, "checkout", "-q", "--", ".")
    return diff


def test_a_builder_is_re_anchored_and_merges(tmp_path):
    """WP14 (4), WP11: only the anchor side of I.K.E.'s existing patches may change; the same patches
    in the same order, the same replacements, nothing else of the builder."""
    moved = BUILDER.replace('"var b = 1;", "var b = 2;"', '"let b = 1;", "var b = 2;"')
    assert anchor.problem("darkreader", BUILDER, moved) == ""
    refused = {
        "a new patch": BUILDER.replace('    ("beta",', '    ("gamma", "x", "y"),\n    ("beta",'),
        "a patch removed": BUILDER.replace('    ("beta", "var b = 1;", "var b = 2;"),\n', ""),
        "a replacement changed": BUILDER.replace('"var b = 1;", "var b = 2;"', '"let b = 1;", "var b = 3;"'),
        "the code changed": moved.replace("return engine", "return engine.upper()"),
        "renamed": BUILDER.replace('("beta"', '("delta"'),
        "nothing re-anchored": BUILDER,
    }
    for case, text in refused.items():
        assert anchor.problem("darkreader", BUILDER, text), case
    # the guard's --builder mode: the builder only, by that rule
    repo = _builder_repo(tmp_path)
    assert guard.check(repo, _patch(repo, moved), builder="darkreader") == []
    reasons = guard.check(repo, _patch(repo, refused["a replacement changed"]), builder="darkreader")
    assert reasons and guard.safety_refusal(reasons)
    assert guard.check(repo, _patch(repo, moved), builder="") != []      # protected for every other run
    # uBlock Origin: only the library's import path
    mjs = (ROOT / "tools" / "build-ubo-scriptlets.mjs").read_text()
    path = "/src/src/js/resources/scriptlets.js"
    assert anchor.problem("ubo-scriptlets", mjs, mjs.replace(path, "/src/src/js/scriptlets/index.js")) == ""
    assert anchor.problem("ubo-scriptlets", mjs, mjs.replace(path, "/src/../../etc/x.js"))
    assert anchor.problem("ubo-scriptlets", mjs, mjs.replace("out.scriptlets[s.name] = {", "evil(); {"))
    # the reserves cannot even write another file in that run
    with pytest.raises(ValueError, match="only tools/build-darkreader.py"):
        reserve.apply_edits(repo, [{"file": "ike/window.py", "find": "a", "replace": "b"}], {"ike/window.py": ""},
                            builder="darkreader")
    # the verified merge: the re-anchoring (the automatic fix) and the update the builder now accepts
    ref = "automation/builder/darkreader"
    commits = [commit(AUTOFIX.replace('"Tests"', '"Builder darkreader"'), ["tools/build-darkreader.py"]),
               commit("update: darkreader 4.9.1 -> 4.9.2 (no AI)", ["ike/resources/darkreader.js",
                                                                       "ike/resources/darkreader-data.json",
                                                                       "ike/__init__.py", "PKGBUILD", "CHANGELOG.md"])]
    files = [change("tools/build-darkreader.py", "@@ -5 +5 @@\n-a\n+b", BUILDER, moved),
             change("ike/resources/darkreader.js", "@@ -1 +1 @@\n-a\n+b"),
             change("ike/resources/darkreader-data.json", "@@ -1 +1 @@\n-a\n+b")] + VERSION_FILES
    evidence = {"runs": runs(filter_lists=False), "skips": EXPECTED}
    assert decide(ref, commits, files, evidence=evidence, published=True) == ("merge", "")
    files[0] = change("tools/build-darkreader.py", "@@", BUILDER, refused["a replacement changed"])
    kind, why = decide(ref, commits, files, evidence=evidence)
    assert kind == "person" and "more than a re-anchoring" in why
    # the builder's path starts from the daily maintenance: the refusal is the failure description
    report = {"components": [{"name": "Dark Reader (engine and lists)", "refused": {
        "current": "4.9.1", "latest": "4.9.2", "step": "I.K.E.'s patch 'beta'", "reason": "anchor gone",
        "context": "let b = 1;"}}]}
    text = plan_tool.builder_failure(report, "darkreader")
    assert "tools/build-darkreader.py" in text and "let b = 1;" in text and "never a new patch" in text


def test_the_builders_path_is_planned_and_capped(tmp_path):
    report = {"components": [{"name": "Dark Reader (engine and lists)", "refused": {
        "current": "1", "latest": "2", "step": "x", "reason": "y"}}]}

    def api(path, raw=False):
        if path.endswith("artifacts?name=component-report"):
            return {"artifacts": [{"id": 5}]}
        import io
        import zipfile
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("report.json", json.dumps(report))
        return buf.getvalue()
    p = plan_tool.plan_builder(REPO, "builder/darkreader/2026-11-23", "77", tmp_path, api=api,
                               tip_of=lambda b: "" if "builder" in b else "m" * 40, attempts_of=lambda b: 0)
    assert (p["action"], p["kind"], p["mode"], p["builder"], p["push_branch"]) == (
        "fix", "builder", "builder", "darkreader", "automation/builder/darkreader")
    assert (tmp_path / "related.txt").read_text() == "tools/build-darkreader.py\n"
    # the cap is per day (2026-11-22): today's attempts used up, it stays open and goes on tomorrow
    tired = plan_tool.plan_builder(REPO, "builder/darkreader/2026-11-23", "77", tmp_path, api=api,
                                   tip_of=lambda b: "t" * 40, attempts_of=lambda b: plan_tool.ISOLATED_ATTEMPTS,
                                   today_of=lambda b: plan_tool.ISOLATED_ATTEMPTS)
    assert tired["action"] == "retry" and "tries again tomorrow" in tired["reason"] and "stays" in tired["reason"]
    again = plan_tool.plan_builder(REPO, "builder/darkreader/2026-11-23", "77", tmp_path, api=api,
                                   tip_of=lambda b: "t" * 40, attempts_of=lambda b: plan_tool.ISOLATED_ATTEMPTS,
                                   today_of=lambda b: 0)
    assert again["action"] == "fix" and again["attempt"] == str(plan_tool.ISOLATED_ATTEMPTS + 1)
    assert plan_tool.plan_builder(REPO, "builder/../x", "77", tmp_path, api=api)["action"] == "skip"


# --- a major version of a crate of the engine ---------------------------------------------------

def test_a_major_crate_is_taken_and_the_ai_adapts_the_wrapper(tmp_path, monkeypatch):
    """WP14 (5), item 2: a new major version of a direct crate gets its own candidate that raises
    the requirement; the AI may adapt the wrapper on that branch only, never with unsafe code."""
    root = tmp_path
    (root / "ike-adblock").mkdir()
    (root / "ike-adblock" / "Cargo.toml").write_text(
        '[dependencies]\nadblock = { version = "=0.13.6" }\npyo3 = { version = "0.30" }\nserde_json = "1"\n')
    monkeypatch.setattr(cc, "latest_crate", lambda name: {"serde_json": "2.0.1"}[name])
    cands = cc.crate_candidates(root, {"serde_json": "1.0.140"}, {"serde_json": "1.0.140"}, "0.30", "0.30")
    major = next(c for c in cands if c["id"] == "crate-major-serde_json")
    assert (major["from"], major["to"], major["requirement"]) == ("1", "2", "2")
    calls = []
    monkeypatch.setattr(cc, "run", lambda cmd, **kw: calls.append(cmd) or "")
    monkeypatch.setattr(cc.shutil, "which", lambda name: "/usr/bin/" + name)
    cc.apply_requirement(root, "serde_json", "2")
    assert 'serde_json = "2"' in (root / "ike-adblock" / "Cargo.toml").read_text()
    assert calls[0][:4] == ["cargo", "update", "-p", "serde_json"]
    msg = uc.message({"id": "crate-major-serde_json", "from": "1", "to": "2"})
    assert uc.commit_problem("crate-major-serde_json", msg, ["ike-adblock/Cargo.toml", "ike-adblock/Cargo.lock",
                                                             "docs/THIRD-PARTY.md", "CHANGELOG.md"]) == ""
    ref = uc.branch_for("crate-major-serde_json")
    assert uc.wrapper_allowed(ref) and not uc.wrapper_allowed("automation/update/darkreader")
    run = {"name": "Tests", "head_branch": ref, "conclusion": "failure", "head_sha": "b" * 40,
           "head_repository": {"full_name": REPO}, "_repo": REPO, "_tip": "b" * 40, "_main_tip": "m" * 40,
           "_attempts": 1, "_engine_update": True}
    p = plan_tool.decide(run, [{"name": "tests", "conclusion": "failure",
                                "steps": [{"name": "AdBlock engine (Rust tests)", "conclusion": "failure"}]}], "")
    assert (p["action"], p["allow_adblock"], p["attempt"]) == ("fix", "true", "2")
    assert plan_tool.first_provider(p) == "Groq"                          # attempt 2: another free provider first
    commits = [commit(msg, ["ike-adblock/Cargo.toml", "ike-adblock/Cargo.lock"] + [v["filename"] for v in VERSION_FILES]),
               commit(AUTOFIX, ["ike-adblock/src/lib.rs"])]
    rs = "@@ -1,2 +1,2 @@\n fn f() {\n-    serde_json::from_str::<V>(t)\n+    serde_json::from_str::<V>(t).ok()\n"
    files = [change("ike-adblock/Cargo.toml", '@@ -4 +4 @@\n-serde_json = "1"\n+serde_json = "2"'),
             change("ike-adblock/Cargo.lock", '@@ -1,3 +1,3 @@\n [[package]]\n name = "serde_json"\n'
                    '-version = "1.0.140"\n+version = "2.0.1"'),
             change("ike-adblock/src/lib.rs", rs)] + VERSION_FILES
    assert decide(ref, commits, files) == ("merge", "")
    for risky in ("    unsafe { libc::exit(0) }", "    let _ = std::process::Command::new(\"sh\");",
                  "    let _ = std::fs::read(\"/etc/passwd\");", "    let k = env!(\"KEY\");"):
        bad = [change("ike-adblock/src/lib.rs", rs.replace("+1,2 @@", "+1,3 @@") + "+" + risky)] + files[:2] + \
            VERSION_FILES
        kind, why = decide(ref, commits, bad)
        assert kind == "person" and "a person must read" in why, risky
    # the wrapper is never the AI's on a candidate that does not update the engine
    kind, why = decide("automation/update/darkreader", [commit("update: darkreader 1 -> 2 (no AI)", []),
                                                       commit(AUTOFIX, ["ike-adblock/src/lib.rs"])],
                       [change("ike-adblock/src/lib.rs", rs)])
    assert kind == "person"
    # a major version only adblock brings has no candidate of its own: it waits for a new adblock
    assert uc.candidate_for({"kind": "crate", "name": "thiserror", "type": "transitive",
                             "compatibility": "major update: needs a requirement change"}) == ""
    assert uc.candidate_for({"kind": "crate", "name": "serde_json", "type": "direct",
                             "compatibility": "major update: needs a requirement change"}) == "crate-major-serde_json"


# --- more attempts, other free providers, the cap ----------------------------------------------

def test_more_attempts_rotate_the_free_providers_and_stop_at_the_cap():
    """Item 9: a configurable cap (tools/ai-providers.py), a fresh run per attempt starting with the
    next free provider; at the cap the branch is kept and the owner told (the ledger: needs-person)."""
    names = providers.all_names()
    assert [providers.first_provider(n) for n in range(1, len(names) + 2)] == list(names) + [names[0]]
    assert providers.FIX_ATTEMPTS >= 3 and plan_tool.ISOLATED_ATTEMPTS == providers.FIX_ATTEMPTS
    assert plan_tool.MAX_ATTEMPTS == providers.FIX_ATTEMPTS_MAIN
    chain = [("Groq", "u", "k", "m1", 1, 1), ("Z.AI", "u", "k", "m2", 1, 1), ("OpenRouter", "u", "k", "m3", 1, 1)]
    assert [c[0] for c in reserve.rotated(chain, "Z.AI")] == ["Z.AI", "OpenRouter", "Groq"]
    assert reserve.rotated(chain, "Nobody") == chain and reserve.rotated(chain, "") == chain
    run = {"name": "Tests", "head_branch": "automation/update/darkreader", "conclusion": "failure",
           "head_sha": "b" * 40, "head_repository": {"full_name": REPO}, "_repo": REPO, "_tip": "b" * 40,
           "_main_tip": "m" * 40, "_attempts": providers.FIX_ATTEMPTS, "_engine_update": False}
    p = plan_tool.decide(run, [{"name": "tests", "conclusion": "failure",
                                "steps": [{"name": "Lint", "conclusion": "failure"}]}], "")
    # the cap is per day: nothing is closed, no one is asked; the next day it goes on, another provider first
    assert p["action"] == "retry" and "stays open" in p["reason"] and "tries again tomorrow" in p["reason"]
    p = plan_tool.decide(dict(run, _attempts_today=0), [{"name": "tests", "conclusion": "failure",
                                                        "steps": [{"name": "Lint", "conclusion": "failure"}]}], "")
    assert p["action"] == "fix" and p["attempt"] == str(providers.FIX_ATTEMPTS + 1)
    assert plan_tool.first_provider(p, 1) == providers.first_provider(providers.FIX_ATTEMPTS + 2)
    # the ledger at the cap: retrying (never needs-person), an informational note only after days
    inv = {"components": [{"id": "integrated:Dark Reader", "kind": "integrated", "name": "Dark Reader",
                           "installed": "4.9.1", "available": "4.9.2", "result": "update available",
                           "origin": ["ike/resources"]}], "findings": []}
    ledger = ledger_tool.update(None, inv, {}, now=ledger_tool.parse_time("2026-11-23T05:00:00Z"))
    failing = runs(filter_lists=False, unit_integration="failure")
    status = {"update_branches": {"automation/update/darkreader": {
        "branch": "automation/update/darkreader", "sha": "b" * 40, "pr": 50, "url": "u",
        "autofix_commits": providers.FIX_ATTEMPTS, "runs": failing, "skips": EXPECTED}}}
    told = []
    ledger = ledger_tool.update(ledger, inv, status, now=ledger_tool.parse_time("2026-11-23T08:00:00Z"),
                                notices=told)
    entry = ledger["entries"]["integrated:Dark Reader@4.9.2"]
    assert entry["state"] == "retrying" and "stays open" in entry["reason"] and told == []
    told2 = []
    days = ledger_tool.RETRY_NOTE_DAYS + 1
    for day in range(1, days + 2):
        ledger = ledger_tool.update(ledger, inv, status, notices=told2,
                                    now=ledger_tool.parse_time("2026-11-23T08:00:00Z") + dt.timedelta(days=day))
    entry = ledger["entries"]["integrated:Dark Reader@4.9.2"]
    assert entry["state"] == "retrying" and entry["retries"] == days + 2
    assert len(told2) == 1 and "nota informativa" in told2[0]              # told once, and it asks nothing
    assert "retrying (%d)" % entry["retries"] in ledger_tool.render(ledger)
    # the workflow: the attempt's first provider only when it has a key, and the CHANGELOG line
    af = (WORKFLOWS / "autofix.yml").read_text()
    assert "HAS_GROQ: ${{ secrets.GROQ_API_KEY != '' }}" in af and '--first $(cat "$RUNNER_TEMP/first")' in af


def test_every_shipped_automation_fix_raises_the_version():
    """Item 5: every automation PR that changes what ships gets the next version when main's is
    published, with a CHANGELOG line written from the report (no code, no link)."""
    af = (WORKFLOWS / "autofix.yml").read_text()
    step = af.split("- name: A new version for users when a fix of main changes the browser", 1)[1]
    step = step.split("\n      - name:", 1)[0]
    for kind in ("main", "lists", "security", "update", "builder", "arch-testing"):
        assert "needs.plan.outputs.kind == '%s'" % kind in step, kind
    assert "grep -qvE '^(tools|tests|docs|\\.github)/'" in step and '"$REASON"' in step
    assert "tr -d '`\\r'" in step and "https?://" in step
    sec = af.split("\n  security-update:\n", 1)[1].split("\n  report:\n", 1)[0]
    assert "prepare-maintenance.py" in sec
    dm = (WORKFLOWS / "daily-maintenance.yml").read_text().split("\n  candidate:\n", 1)[1]
    assert "tools/prepare-maintenance.py" in dm and "update-candidates.py bullet" in dm
    line = uc.bullet({"id": "darkreader", "component": "Dark Reader", "from": "4.9.1", "to": "4.9.2",
                      "note": "see `x` https://evil.example/a"})
    assert "`" not in line and "https://" not in line and line.startswith("- Dark Reader: 4.9.1 -> 4.9.2")
    assert merge.version_problem("CHANGELOG.md", "@@ -3,0 +4,2 @@\n+## 1.1.23\n+" + line, REPO) == ""


# --- the filter lists on the candidate's commit ---------------------------------------------------

def test_the_filter_lists_are_compared_with_mains_engine_on_the_commit():
    """Item 4: the candidate's engine against main's on the same day's lists: worse fails, a list not
    downloaded is not verified (never passed)."""
    def info(share, state="ok", built=True, findings=()):
        return {"engine": {"built": built, "error": "" if built else "boom"}, "findings": list(findings),
                "lists": [{"name": "uBlock filters", "url": "u1", "state": state, "unread_share": share, "error": ""}]}
    assert lists_tool.compare(info(0.10), info(0.11))[0] == "pass"
    assert lists_tool.compare(info(0.10), info(0.20))[0] == "fail"
    assert lists_tool.compare(info(0.10), info(0.10, built=False))[0] == "fail"
    assert lists_tool.compare(info(0.10), info(0.10, findings=["uBlock filters: the engine refused the list"]))[0] \
        == "fail"
    assert lists_tool.compare(info(0.10), info(0.10, state="unreachable"))[0] == "unverified"
    assert lists_tool.compare(info(0.10), {"lists": []})[0] == "unverified"
    assert tc.CATEGORIES["filter-lists"][1] == ("tests.yml", "tests", "Filter lists in this engine")
    text = (WORKFLOWS / "tests.yml").read_text()
    # since 2026-11-24 the step runs once in the job "tests checks", and the gate "tests" (the job the
    # category reads) restates its outcome under the same name: skipped there, skipped here
    checks = text.split("\n  checks:\n", 1)[1].split("\n  base-tests:\n", 1)[0]
    step = checks.split("- name: Filter lists in this engine", 1)[1].split("\n      - ", 1)[0]
    assert "steps.lists.outputs.verdict == 'pass'" in step and "'unverified'" not in step   # skipped: not verified
    assert "tools/filter-lists.py compare" in checks
    assert "filter-lists: ${{ steps.filter-lists.outcome }}" in checks and "id: filter-lists" in step
    tests = text.split("\n  tests:\n", 1)[1].split("\n  hand-over:\n", 1)[0]
    mirror = tests.split("- name: Filter lists in this engine", 1)[1].split("\n      - ", 1)[0]
    assert "needs.checks.outputs.filter-lists == 'success' || needs.checks.outputs.filter-lists == 'failure'" in mirror
    assert 'test "$OUTCOME" = success' in mirror and "'skipped'" not in mirror


# --- the PKGBUILD's dependencies -------------------------------------------------------------------

def test_the_pkgbuild_follows_what_the_code_needs():
    """WP10 (d): a module or program used and not declared becomes a PKGBUILD candidate; minima come
    from the code's own "# needs:" markers; the merge accepts only that change of the recipe."""
    text = (ROOT / "PKGBUILD").read_text()
    inv = {"components": [{"id": "python-module:yaml", "kind": "python-module", "name": "yaml", "type": "runtime",
                           "provided_by": "python-yaml", "origin": ["ike/x.py"]},
                          {"id": "runtime-tool:kioclient", "kind": "runtime-tool", "name": "kioclient",
                           "type": "runtime", "provided_by": "kio", "origin": ["ike/y.py"]}],
           "findings": [{"finding": "used but not declared", "component": "python-module:yaml", "detail": "d"},
                        {"finding": "used but not declared", "component": "runtime-tool:kioclient", "detail": "d"},
                        {"finding": "unknown provider", "component": "x", "detail": "z"}]}
    p = pk.plan(text, inv, {"qt6-webengine": "6.10"})
    assert p["depends"] == ["python-yaml"] and [x[0] for x in p["optdepends"]] == ["kio"]
    assert p["minima"] == {"qt6-webengine": "6.10"} and len(p["person"]) == 1
    new = pk.apply(text, p)
    assert "'python-yaml'" in new and "'qt6-webengine>=6.10'" in new and "'kio: used by I.K.E." in new
    assert pk.problem(text, new) == ""
    assert pk.problem(text, new.replace("makedepends=('rust' 'gcc')", "makedepends=('rust' 'gcc' 'curl')"))
    assert pk.problem(text, text.replace("'python-jeepney' ", ""))                          # a depend removed
    assert pk.problem(new, new.replace("'qt6-webengine>=6.10'", "'qt6-webengine>=6.9'"))   # a minimum lowered
    assert pk.problem(text, text.replace("package() {", "package() {\n  curl x | sh"))
    assert pk.markers(ROOT) == {} or all(re.match(r"^[0-9]", v) for v in pk.markers(ROOT).values())
    # its candidate and the verified merge
    rows = uc.plan(uc.gather({"candidates": []}, None, p), {}, today=MONDAY)
    assert rows[0]["id"] == "pkgbuild" and rows[0]["action"] == "make"
    msg = "pkgbuild: what the code needs (tools/pkgbuild-sync.py, no AI)"
    ref = "automation/update/pkgbuild"
    f = change("PKGBUILD", "@@ -12 +12 @@\n-a\n+b", text, new)
    assert decide(ref, [commit(msg, ["PKGBUILD", "ike/__init__.py", "CHANGELOG.md"])],
                  [f] + [v for v in VERSION_FILES if v["filename"] != "PKGBUILD"]) == ("merge", "")
    bad = change("PKGBUILD", "@@", text, new.replace("options=('!debug')", "options=('debug')"))
    kind, why = decide(ref, [commit(msg, ["PKGBUILD"])], [bad])
    assert kind == "person" and "outside depends" in why


# --- the skips, the guard's protected files, the documentation --------------------------------------

def test_the_expected_skips_are_environmental_and_an_unexpected_one_still_blocks():
    """Item 6: the skips a real Tests run on GitHub's runners has (no desktop, no Arch, no root, no
    sandbox) are named with where they are verified instead; anything else still keeps the merge for a person."""
    # every reason of the real run 45020817248 (PR #105, GitHub's runners), and the optional dependencies
    real = ("IKE_TEST_NETWORK=1 to use the real lists", "IKE_TEST_NETWORK=1 to use the real sources",
            "IKE_UI_SHOTS=<folder> takes the pictures", "KDE's Breeze icons and platform theme are not installed here",
            "Qt's kde platform theme is not installed",
            "the desktops are tested as Arch Linux packages them (not Arch here)",
            "only for the installed package (IKE_TEST_APP)", "the sources are checked once, not for the installed copy",
            "IKE_TEST_SANDBOX=1 only (needs a system where the sandbox works)", "only as root (the Arch container)",
            "the Breeze style is not installed here (got ' / fusion')",
            "the Oxygen style is not installed here (got ' / fusion')",
            "the kvantum style is not installed here (got ' / fusion')",
            "optional dependency libnotify is not installed here (an Arch package: arch.yml installs it "
            "and runs this test): not verified",
            "optional dependency chromium-widevine is not installed here (an AUR package: no check of GitHub "
            "installs it): not verified")
    for reason in real:
        assert tc.unexpected_skips([{"test": "t", "reason": reason}]) == [], reason
    # 1.1.24: the tab mark drawn as Breeze draws it runs on Arch only (Ubuntu's runners have no Breeze);
    # unregistered, it held every update of 2026-11-24 back (#149, #150)
    assert tc.unexpected_skips([{"test": "t", "reason": "Breeze (the widget style) is not installed here"}]) == []
    assert tc.unexpected_skips([{"test": "t", "reason": "Breeze (the widget style) is not installed here, so"}])
    # strict: what GitHub's runners do run (the IPv6 loopback is there) still blocks when skipped
    for reason in ("ffmpeg not installed", "flaky", "", "not verified", "no IPv6 loopback on this machine",
                   "the desktops are tested elsewhere", "optional dependency x is not installed here"):
        assert tc.unexpected_skips([{"test": "t", "reason": reason}]), reason
    assert all(isinstance(p, str) and why for p, why in tc.EXPECTED_SKIPS)


def test_no_agent_may_change_the_chains_own_tools():
    ctx = load("autofix-context")
    for path in ("tools/update-candidates.py", "tools/ci-pins.py", "tools/builder-anchor.py",
                 "tools/pkgbuild-sync.py", "tests/test_full_chain.py"):
        assert path in guard.FORBIDDEN_FILES and path in ctx.NOT_RECENT, path
        assert guard.allowed_path(path, True), path
    assert guard.allowed_path("tools/build-darkreader.py", True)            # a builder only by --builder


def test_the_workflows_are_wired_for_the_whole_chain():
    dm = (WORKFLOWS / "daily-maintenance.yml").read_text()
    for job in ("plan-candidates:", "candidate:", "publish:", "retire-combined:", "prepare:", "publish-candidate:"):
        assert "\n  %s\n" % job in dm, job
    assert "github.event.inputs.mode == 'combined'" in dm.split("\n  prepare:\n", 1)[1].split("\n", 1)[0]
    assert "python3 -I tools/update-candidates.py check --id" in dm
    assert 'gh workflow run autofix.yml --ref main -f run_id="$GITHUB_RUN_ID" -f work="builder/$ID/' in dm
    assert "IKE_WORKFLOW_TOKEN" in dm and "persist-credentials: false" in dm
    make = dm.split("- name: Make the candidate (no credentials)", 1)[1].split("\n      - ", 1)[0]
    assert "GH_TOKEN" not in make and "secrets." not in make
    af = (WORKFLOWS / "autofix.yml").read_text()
    assert "builder/(darkreader|ubo-scriptlets)/" in af and "--builder-work" in af
    assert "workflow-proposal.patch" in af and "mai applicata" in af                # WP12
    assert 'gh workflow run daily-maintenance.yml --ref main -f mode=builder' in af
    am = (WORKFLOWS / "automerge.yml").read_text()
    assert "IKE_WORKFLOW_TOKEN: ${{ secrets.IKE_WORKFLOW_TOKEN }}" in am
    for name in ("tests.yml", "arch.yml"):
        hand = (WORKFLOWS / name).read_text().split("\n  hand-over:\n", 1)[1]
        assert "startsWith(github.ref_name, 'automation/builder/')" in hand, name
