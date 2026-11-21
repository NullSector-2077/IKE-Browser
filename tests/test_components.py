"""Daily component check (tools/check-components.py): versions read from the
repository, new versions found and applied, failures kept apart, report and
GitHub workflow. Upstream answers are stand-ins, except for the scriptlets,
which are rebuilt by the real Node.js tool from a stand-in uBlock checkout;
IKE_TEST_NETWORK=1 also runs the check against the real sources."""

import importlib.util
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from conftest import ROOT

needs_node = pytest.mark.skipif(not (shutil.which("node") and shutil.which("git")),
                                reason="needs Node.js and git")


def load_tool():
    spec = importlib.util.spec_from_file_location("check_components", ROOT / "tools" / "check-components.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


UBO_JS = """
function abortOnPropertyRead(chain = '') { return '%s' + chain; }
function safeSelf() { return {}; }
export const builtinScriptlets = [
  { name: 'abort-on-property-read.js', aliases: ['aopr.js'], fn: abortOnPropertyRead,
    dependencies: ['safe-self.fn'] },
  { name: 'safe-self.fn', fn: safeSelf },
];
"""


def make_ubo(path, marker="v1", commit=True):
    js = path / "src" / "js" / "resources"
    js.mkdir(parents=True, exist_ok=True)
    (js / "scriptlets.js").write_text(UBO_JS % marker, "utf-8")
    git = ["git", "-C", str(path), "-c", "user.name=t", "-c", "user.email=t@t"]
    if not (path / ".git").exists():
        subprocess.run(git[:3] + ["init", "-q"], check=True)
    if commit:
        subprocess.run(git + ["add", "-A"], check=True)
        subprocess.run(git + ["commit", "-q", "-m", marker], check=True)
    return path


@pytest.fixture
def repo(tmp_path):
    """A copy of the files the check reads and writes."""
    root = tmp_path / "repo"
    for rel in ("ike-adblock/Cargo.toml", "ike-adblock/Cargo.lock", "ike-adblock/src/lib.rs",
                "ike/resources/ubo-scriptlets.json", "tools/test-requirements.txt",
                "tools/build-ubo-scriptlets.mjs"):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / rel, root / rel)
    return root


@pytest.fixture
def tool(monkeypatch, tmp_path, repo):
    """The tool with stand-in upstream answers equal to what the repository uses."""
    mod = load_tool()
    pins = mod.read_pins(repo)
    up = {"adblock": mod.current_adblock(repo), "set": dict(pins), "arch": ""}
    monkeypatch.setattr(mod, "latest_adblock", lambda: up["adblock"])
    monkeypatch.setattr(mod, "resolve_test_packages", lambda: dict(up["set"]))
    monkeypatch.setattr(mod, "arch_webengine", lambda: up["arch"])
    up["pyo3"] = mod.current_pyo3(repo) + ".0"
    monkeypatch.setattr(mod, "latest_pyo3", lambda: up["pyo3"])
    calls = []
    real_run = mod.run
    monkeypatch.setattr(mod, "run", lambda cmd, **kw: calls.append(cmd) if cmd[0] == "cargo" else real_run(cmd, **kw))
    mod.up, mod.calls = up, calls
    # Dark Reader: the engine and the lists the repository has (its own test: test_darkreader.py)
    monkeypatch.setattr(mod, "check_darkreader", lambda root, work, dr_src=None: {
        "current": "same", "latest": "same", "update": False, "note": ""})
    # scriptlets: the repository's file is replaced by one built from a stand-in checkout
    ubo = make_ubo(tmp_path / "ubo")
    if shutil.which("node"):
        built = mod.build_scriptlets(repo, Path(mod.tempfile.mkdtemp(dir=tmp_path)), ubo)
        shutil.copy(built, repo / "ike/resources/ubo-scriptlets.json")
    mod.ubo = ubo
    return mod


def by_name(results):
    return {r["name"].split(" ")[0]: r for r in results}


def test_repository_versions_agree():
    mod = load_tool()
    version = mod.current_adblock(ROOT)
    assert re.search(r'const ENGINE_VERSION: &str = "%s"' % re.escape(version),
                     (ROOT / "ike-adblock/src/lib.rs").read_text())
    assert re.search(r'name = "adblock"\nversion = "%s"' % re.escape(version),
                     (ROOT / "ike-adblock/Cargo.lock").read_text())
    pins = mod.read_pins(ROOT)
    for name in mod.QT_PACKAGES + ("cryptography", "certifi", "jeepney"):
        assert name in pins, name
    # PyQt6 and its Qt wheel belong to the same Qt release
    assert pins["pyqt6"][1].split(".")[:2] == pins["pyqt6-qt6"][1].split(".")[:2]


@needs_node
def test_nothing_new(tool, repo, tmp_path):
    results = tool.check_all(repo, tool.ubo, tmp_path / "w")
    assert [r["error"] for r in results] == [""] * 5
    assert not any(r["update"] for r in results)
    assert not any(r["also"] for r in results)


@needs_node
def test_each_new_version_found(tool, repo, tmp_path):
    tool.up["adblock"] = "0.14.0"
    tool.up["set"]["pyqt6-webengine-qt6"] = ("PyQt6-WebEngine-Qt6", "6.141.0")
    tool.up["arch"] = "6.14.1-1"
    make_ubo(tool.ubo, "v2")
    r = by_name(tool.check_all(repo, tool.ubo, tmp_path / "w"))
    assert r["adblock-rust"]["update"] and r["adblock-rust"]["latest"] == "0.14.0"
    assert "self-update" in r["adblock-rust"]["note"] and "__min_system__" not in r["adblock-rust"]["note"]
    assert r["uBlock"]["update"] and r["uBlock"]["note"] == "1 changed, 0 new, 0 removed"
    assert r["Qt"]["update"] and "6.141.0" in r["Qt"]["note"] and "6.141.0" in r["Qt"]["latest"]
    assert "Arch Linux qt6-webengine 6.14.1-1" in r["Qt"]["note"]


@needs_node
def test_minor_changes_do_not_count(tool, repo, tmp_path):
    """A new uBlock commit with the same scriptlets, a new certifi: reported,
    but no update."""
    (tool.ubo / "README.md").write_text("new commit")
    make_ubo(tool.ubo, "v1")
    tool.up["set"]["certifi"] = ("certifi", "2999.1.1")
    r = by_name(tool.check_all(repo, tool.ubo, tmp_path / "w"))
    assert not any(x["update"] for x in r.values())
    assert "certifi" in r["Qt"]["also"]
    # older versions upstream are never "new"
    tool.up["adblock"] = "0.1.0"
    assert not tool.check_adblock(repo)["update"]


@needs_node
def test_apply_rewrites_the_version_files(tool, repo, tmp_path):
    tool.up["adblock"] = "0.14.0"
    tool.up["set"]["pyqt6"] = ("PyQt6", "6.13.0")
    tool.up["set"]["pyqt6-qt6"] = ("PyQt6-Qt6", "6.13.1")
    tool.up["set"]["certifi"] = ("certifi", "2999.1.1")
    tool.up["set"]["newdep"] = ("NewDep", "1.0")
    del tool.up["set"]["pycparser"]
    make_ubo(tool.ubo, "v2")
    assert tool.main(["--root", str(repo), "--ubo-src", str(tool.ubo), "--apply"]) == 0
    assert 'adblock = { version = "=0.14.0"' in (repo / "ike-adblock/Cargo.toml").read_text()
    assert 'const ENGINE_VERSION: &str = "0.14.0"' in (repo / "ike-adblock/src/lib.rs").read_text()
    assert ["cargo", "update", "-p", "adblock", "--precise", "0.14.0"] in [c[:6] for c in tool.calls]
    req = (repo / "tools/test-requirements.txt").read_text()
    assert req.startswith("# Python packages the automatic tests run with")
    assert "PyQt6==6.13.0\nPyQt6-Qt6==6.13.1\n" in req and "certifi==2999.1.1" in req
    assert "NewDep==1.0" in req and "pycparser" not in req
    data = json.loads((repo / "ike/resources/ubo-scriptlets.json").read_text())
    assert "'v2'" in data["scriptlets"]["abort-on-property-read.js"]["src"]
    # applied: checking again finds nothing new
    tool.calls.clear()
    results = tool.check_all(repo, tool.ubo, tmp_path / "again")
    assert not any(r["update"] or r["also"] for r in results)


@needs_node
def test_failing_source_is_reported_alone(tool, repo, tmp_path, monkeypatch):
    def offline():
        raise OSError("network unreachable")
    monkeypatch.setattr(tool, "latest_adblock", offline)
    tool.up["set"]["pyqt6-webengine-qt6"] = ("PyQt6-WebEngine-Qt6", "6.141.0")
    r = by_name(tool.check_all(repo, tool.ubo, tmp_path / "w"))
    assert "network unreachable" in r["adblock-rust"]["error"] and not r["adblock-rust"]["update"]
    assert r["Qt"]["update"] and not r["Qt"]["error"]
    # --apply fails closed: no component is changed when any source failed.
    before_adblock = (repo / "ike-adblock/Cargo.toml").read_text()
    before_requirements = (repo / "tools/test-requirements.txt").read_text()
    assert tool.main(["--root", str(repo), "--ubo-src", str(tool.ubo), "--apply"]) == 1
    assert (repo / "ike-adblock/Cargo.toml").read_text() == before_adblock
    assert (repo / "tools/test-requirements.txt").read_text() == before_requirements


@needs_node
def test_report_files(tool, repo, tmp_path, monkeypatch):
    tool.up["adblock"] = "0.14.0"
    out = tmp_path / "gh-output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    tool.main(["--root", str(repo), "--ubo-src", str(tool.ubo),
               "--json", str(tmp_path / "r.json"), "--markdown", str(tmp_path / "r.md")])
    data = json.loads((tmp_path / "r.json").read_text())
    assert data["updates"] == 1 and data["errors"] == 0 and len(data["components"]) == 5
    assert not any(k.startswith("_") for c in data["components"] for k in c)
    md = (tmp_path / "r.md").read_text()
    assert md.startswith("Nuove versioni trovate") and "| adblock-rust (AdBlock engine) | 0.13" in md
    assert md.count("\n|") == 7           # header, separator, five components
    assert out.read_text() == "updates=1\nerrors=0\n"


def test_workflows():
    daily = (ROOT / ".github/workflows/daily-check.yml").read_text()
    assert re.search(r'cron: "\d+ \d+ \* \* \*"', daily)
    assert "tools/check-components.py --json report.json --markdown report.md" in daily
    assert "issues: write" in daily and "contents: read" in daily and "contents: write" not in daily
    assert "--label components" in daily
    tests = (ROOT / ".github/workflows/tests.yml").read_text()
    env = (ROOT / ".github/actions/ike-test-env/action.yml").read_text()
    assert "pull_request:" in tests and "ruff check ." in tests and "python -m pytest" in tests
    assert "uses: ./.github/actions/ike-test-env" in tests
    assert "-r tools/test-requirements.txt" in env
    assert "makepkg -d -f" in tests and "IKE_TEST_APP=" in tests and "ike-browser-package" in tests
    assert "windows" not in tests.lower() and "appimage" not in tests.lower()

def test_maintenance_artifact_paths_are_consistent():
    workflow = (ROOT / ".github/workflows/daily-maintenance.yml").read_text()
    assert 'mkdir -p "$RUNNER_TEMP/maintenance-candidate"' in workflow
    assert 'git bundle create "$RUNNER_TEMP/maintenance-candidate/candidate.bundle" HEAD' in workflow
    assert 'cp component-report.md "$RUNNER_TEMP/maintenance-candidate/component-report.md"' in workflow
    assert 'path: ${{ runner.temp }}/maintenance-candidate/*' in workflow
    assert 'path: ${{ runner.temp }}/maintenance-candidate' in workflow
    assert 'test -s "$RUNNER_TEMP/maintenance-candidate/candidate.bundle"' in workflow
    assert 'test -s "$RUNNER_TEMP/maintenance-candidate/component-report.md"' in workflow
    assert 'git bundle verify "$RUNNER_TEMP/maintenance-candidate/candidate.bundle"' in workflow
    assert 'git fetch "$RUNNER_TEMP/maintenance-candidate/candidate.bundle" HEAD:refs/heads/automation/daily-maintenance' in workflow


@pytest.mark.skipif(not os.environ.get("IKE_TEST_NETWORK"), reason="IKE_TEST_NETWORK=1 to use the real sources")
def test_real_sources(tmp_path):
    out = tmp_path / "r.json"
    subprocess.run(["python3", str(ROOT / "tools/check-components.py"), "--json", str(out)], check=True)
    data = json.loads(out.read_text())
    assert data["errors"] == 0, data




@needs_node
def test_informational_rebuilds_are_deferred_without_actionable_updates(tool, repo, tmp_path):
    """A new certifi alone must not make a release."""
    tool.up["set"]["certifi"] = ("certifi", "2999.1.1")
    before_requirements = (repo / "tools/test-requirements.txt").read_text()
    assert tool.main(["--root", str(repo), "--ubo-src", str(tool.ubo), "--apply"]) == 0
    assert (repo / "tools/test-requirements.txt").read_text() == before_requirements


def test_prepare_maintenance_bumps_candidate_version(tmp_path):
    root = tmp_path / "repo"
    for rel in ("ike/__init__.py", "PKGBUILD", "README.md"):
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / rel, dest)
    (root / "CHANGELOG.md").write_text("# Changelog\n\n## 1.0.0\n\n- First release.\n", "utf-8")
    report = tmp_path / "report.json"
    report.write_text(json.dumps({"errors": 0, "components": [{
        "name": "adblock-rust (AdBlock engine)", "current": "0.13.5",
        "latest": "0.14.0", "update": True, "note": "system API update", "also": ""
    }]}), "utf-8")
    script = ROOT / "tools" / "prepare-maintenance.py"
    subprocess.run(["python3", str(script), "--root", str(root), "--report", str(report),
                    "--base-version", "1.0.0"], check=True)
    init = (root / "ike/__init__.py").read_text()
    assert '__version__ = "1.0.1"' in init
    # the engine travels in the self-update (1.1.12): the minimum system stays
    minimum = re.search(r'^__min_system__ = "[^"]+"$', (ROOT / "ike/__init__.py").read_text(), re.M).group(0)
    assert minimum in init
    assert "pkgver=1.0.1" in (root / "PKGBUILD").read_text()
    readme = (root / "README.md").read_text()
    assert "**Version 1.0.1**" in readme and "ike-browser-1.0.1-1-x86_64.pkg.tar.zst" in readme
    log = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    assert log.startswith("# Changelog\n\n## 1.0.1\n") and "## 1.0.0" in log

    # the next day's candidate for the same release adds to the same section
    report.write_text(json.dumps({"errors": 0, "components": [{
        "name": "uBlock Origin scriptlets", "current": "old", "latest": "new",
        "update": True, "note": "scriptlet changes", "also": ""
    }]}), "utf-8")
    subprocess.run(["python3", str(script), "--root", str(root), "--report", str(report),
                    "--base-version", "1.0.0"], check=True)
    assert '__version__ = "1.0.1"' in (root / "ike/__init__.py").read_text()
    log = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    assert log.count("## 1.0.1") == 1 and "scriptlet changes" in log and "adblock-rust" in log


def test_the_engines_other_crates_are_followed(tool, repo, tmp_path, monkeypatch):
    """1.1.19: pyo3, serde_json and every crate they bring were never updated
    (only adblock was followed). Newer compatible crates and a new pyo3 line
    are found; the requirement is raised when applied."""
    r = by_name(tool.check_all(repo, tool.ubo, tmp_path / "w"))
    assert not r["Rust"]["update"] and not r["Rust"]["error"], r["Rust"]
    assert [tool.pyo3_requirement("0.30", v) for v in ("0.30.9", "0.31.2", "1.2.0", "0.29.0")] == \
        ["0.30", "0.31", "1", "0.30"]
    assert tool.pyo3_requirement("1", "1.4.0") == "1" and tool.pyo3_requirement("1", "2.0.0") == "2"
    lock = (repo / "ike-adblock/Cargo.lock").read_text()
    old = tool.lock_packages(lock)
    assert old["adblock"] == tool.current_adblock(repo) and "pyo3" in old and "serde_json" in old
    newer = lock.replace('name = "serde_json"\nversion = "%s"' % old["serde_json"],
                         'name = "serde_json"\nversion = "99.0.0"')
    monkeypatch.setattr(tool, "updated_lock", lambda root, req: newer)
    tool.up["pyo3"] = "0.99.1"
    info = tool.check_crates(repo)
    assert info["update"] and info["_requirement"] == "0.99", info
    assert "pyo3 %s -> 0.99" % tool.current_pyo3(repo) in info["note"]
    assert "serde_json %s -> 99.0.0" % old["serde_json"] in info["note"]
    tool.apply_crates(repo, info)
    assert 'pyo3 = { version = "0.99"' in (repo / "ike-adblock/Cargo.toml").read_text()
    assert tool.calls[-1][:2] == ["cargo", "update"] and "-p" not in tool.calls[-1]
