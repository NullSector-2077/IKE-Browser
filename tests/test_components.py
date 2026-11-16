"""Daily component check (tools/check-components.py): versions read from the
repository, new versions found and applied, failures kept apart, report and
GitHub workflow. Upstream answers are stand-ins, except for the scriptlets,
which are rebuilt by the real Node.js tool from a stand-in uBlock checkout;
ICE_TEST_NETWORK=1 also runs the check against the real sources."""

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
                "ike/resources/ubo-scriptlets.json", "tools/appimage-requirements.txt",
                "tools/build-appimage.sh", "tools/build-windows.ps1", "tools/build-ubo-scriptlets.mjs"):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / rel, root / rel)
    return root


@pytest.fixture
def tool(monkeypatch, tmp_path, repo):
    """The tool with stand-in upstream answers equal to what the repository uses."""
    mod = load_tool()
    pins = mod.read_pins(repo)
    tag, python = mod.current_pbs(repo)
    sha = re.search(r"^PBS_SHA256=(\S+)", (repo / "tools/build-appimage.sh").read_text(), re.M).group(1)
    win_sha = re.search(r'^\$PBS_SHA256 = "(\S+)"', (repo / "tools/build-windows.ps1").read_text(), re.M).group(1)
    up = {"adblock": mod.current_adblock(repo), "set": dict(pins), "pbs": (tag, python, sha, win_sha)}
    monkeypatch.setattr(mod, "latest_adblock", lambda: up["adblock"])
    monkeypatch.setattr(mod, "resolve_appimage", lambda root: dict(up["set"]))
    monkeypatch.setattr(mod, "latest_pbs", lambda minor: up["pbs"])
    calls = []
    real_run = mod.run
    monkeypatch.setattr(mod, "run", lambda cmd, **kw: calls.append(cmd) if cmd[0] == "cargo" else real_run(cmd, **kw))
    mod.up, mod.calls = up, calls
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
    tag, python = mod.current_pbs(ROOT)
    assert re.fullmatch(r"\d{8}", tag) and re.fullmatch(r"3\.\d+\.\d+", python)
    build = (ROOT / "tools/build-appimage.sh").read_text()
    assert '-r "$ROOT/tools/appimage-requirements.txt"' in build
    assert "export PYTHONNOUSERSITE=1" in build
    # the Windows build: the same Python and the same Qt / PyQt6 versions
    win = (ROOT / "tools/build-windows.ps1").read_text()
    assert '$PBS_TAG = "%s"' % tag in win and '$PBS_PYTHON = "%s"' % python in win
    assert re.search(r'^\$PBS_SHA256 = "[0-9a-f]{64}"', win, re.M)
    assert "tools\\appimage-requirements.txt" in win


@needs_node
def test_nothing_new(tool, repo, tmp_path):
    results = tool.check_all(repo, tool.ubo, tmp_path / "w")
    assert [r["error"] for r in results] == [""] * 4
    assert not any(r["update"] for r in results)
    assert not any(r["also"] for r in results)


@needs_node
def test_each_new_version_found(tool, repo, tmp_path):
    tool.up["adblock"] = "0.14.0"
    tool.up["set"]["pyqt6-webengine-qt6"] = ("PyQt6-WebEngine-Qt6", "6.141.0")
    tag, python, sha, win_sha = tool.up["pbs"]
    tool.up["pbs"] = ("29991231", python.rsplit(".", 1)[0] + ".99", "ab" * 32, "cd" * 32)
    make_ubo(tool.ubo, "v2")
    r = by_name(tool.check_all(repo, tool.ubo, tmp_path / "w"))
    assert r["adblock-rust"]["update"] and r["adblock-rust"]["latest"] == "0.14.0"
    assert "__min_system__" in r["adblock-rust"]["note"]
    assert r["uBlock"]["update"] and r["uBlock"]["note"] == "1 changed, 0 new, 0 removed"
    assert r["Qt"]["update"] and "6.141.0" in r["Qt"]["note"] and "6.141.0" in r["Qt"]["latest"]
    assert r["Python"]["update"] and "build 29991231" in r["Python"]["latest"]


@needs_node
def test_minor_changes_do_not_count(tool, repo, tmp_path):
    """A new uBlock commit with the same scriptlets, a new certifi, a rebuild of
    the same Python: reported, but no update."""
    (tool.ubo / "README.md").write_text("new commit")
    make_ubo(tool.ubo, "v1")
    tool.up["set"]["certifi"] = ("certifi", "2999.1.1")
    tag, python, sha, win_sha = tool.up["pbs"]
    tool.up["pbs"] = ("29991231", python, "cd" * 32, "dc" * 32)
    r = by_name(tool.check_all(repo, tool.ubo, tmp_path / "w"))
    assert not any(x["update"] for x in r.values())
    assert "certifi" in r["Qt"]["also"] and "29991231" in r["Python"]["also"]
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
    tool.up["pbs"] = ("29991231", "3.13.99", "ef" * 32, "fe" * 32)
    make_ubo(tool.ubo, "v2")
    assert tool.main(["--root", str(repo), "--ubo-src", str(tool.ubo), "--apply"]) == 0
    assert 'adblock = { version = "=0.14.0"' in (repo / "ike-adblock/Cargo.toml").read_text()
    assert 'const ENGINE_VERSION: &str = "0.14.0"' in (repo / "ike-adblock/src/lib.rs").read_text()
    assert ["cargo", "update", "-p", "adblock", "--precise", "0.14.0"] == tool.calls[0][:6]
    req = (repo / "tools/appimage-requirements.txt").read_text()
    assert req.startswith("# Python packages bundled in the AppImage")
    assert "PyQt6==6.13.0\nPyQt6-Qt6==6.13.1\n" in req and "certifi==2999.1.1" in req
    assert "NewDep==1.0" in req and "pycparser" not in req
    build = (repo / "tools/build-appimage.sh").read_text()
    assert "PBS_TAG=29991231\n" in build and "PBS_PYTHON=3.13.99\n" in build
    assert "PBS_SHA256=" + "ef" * 32 + "\n" in build
    win = (repo / "tools/build-windows.ps1").read_text()
    assert '$PBS_TAG = "29991231"\n' in win and '$PBS_PYTHON = "3.13.99"\n' in win
    assert '$PBS_SHA256 = "%s"\n' % ("fe" * 32) in win
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
    before_requirements = (repo / "tools/appimage-requirements.txt").read_text()
    assert tool.main(["--root", str(repo), "--ubo-src", str(tool.ubo), "--apply"]) == 1
    assert (repo / "ike-adblock/Cargo.toml").read_text() == before_adblock
    assert (repo / "tools/appimage-requirements.txt").read_text() == before_requirements


@needs_node
def test_report_files(tool, repo, tmp_path, monkeypatch):
    tool.up["adblock"] = "0.14.0"
    out = tmp_path / "gh-output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    tool.main(["--root", str(repo), "--ubo-src", str(tool.ubo),
               "--json", str(tmp_path / "r.json"), "--markdown", str(tmp_path / "r.md")])
    data = json.loads((tmp_path / "r.json").read_text())
    assert data["updates"] == 1 and data["errors"] == 0 and len(data["components"]) == 4
    assert not any(k.startswith("_") for c in data["components"] for k in c)
    md = (tmp_path / "r.md").read_text()
    assert md.startswith("Nuove versioni trovate") and "| adblock-rust (AdBlock engine) | 0.13" in md
    assert md.count("\n|") == 6           # header, separator, four components
    assert out.read_text() == "updates=1\nerrors=0\n"


def test_workflows():
    daily = (ROOT / ".github/workflows/daily-check.yml").read_text()
    assert re.search(r'cron: "\d+ \d+ \* \* \*"', daily)
    assert "tools/check-components.py --json report.json --markdown report.md" in daily
    assert "issues: write" in daily and "contents: read" in daily and "contents: write" not in daily
    assert "--label components" in daily
    tests = (ROOT / ".github/workflows/tests.yml").read_text()
    assert "pull_request:" in tests and "ruff check ." in tests and "python -m pytest" in tests
    assert "-r tools/appimage-requirements.txt" in tests

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


@pytest.mark.skipif(not os.environ.get("ICE_TEST_NETWORK"), reason="ICE_TEST_NETWORK=1 to use the real sources")
def test_real_sources(tmp_path):
    out = tmp_path / "r.json"
    subprocess.run(["python3", str(ROOT / "tools/check-components.py"), "--json", str(out)], check=True)
    data = json.loads(out.read_text())
    assert data["errors"] == 0, data




@needs_node
def test_informational_rebuilds_are_deferred_without_actionable_updates(tool, repo, tmp_path):
    """A new certifi or a rebuild of the same Python alone must not make a release."""
    tool.up["set"]["certifi"] = ("certifi", "2999.1.1")
    tag, python, sha, win_sha = tool.up["pbs"]
    tool.up["pbs"] = ("29991231", python, "ab" * 32, "cd" * 32)
    before_requirements = (repo / "tools/appimage-requirements.txt").read_text()
    before_appimage = (repo / "tools/build-appimage.sh").read_text()
    before_windows = (repo / "tools/build-windows.ps1").read_text()
    assert tool.main(["--root", str(repo), "--ubo-src", str(tool.ubo), "--apply"]) == 0
    assert (repo / "tools/appimage-requirements.txt").read_text() == before_requirements
    assert (repo / "tools/build-appimage.sh").read_text() == before_appimage
    assert (repo / "tools/build-windows.ps1").read_text() == before_windows


def test_prepare_maintenance_bumps_candidate_version(tmp_path):
    root = tmp_path / "repo"
    for rel in ("ike/__init__.py", "PKGBUILD", "README.md", "CHANGELOG.md"):
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / rel, dest)
    report = tmp_path / "report.json"
    report.write_text(json.dumps({"errors": 0, "components": [{
        "name": "adblock-rust (AdBlock engine)", "current": "0.13.5",
        "latest": "0.14.0", "update": True, "note": "system API update", "also": ""
    }]}), "utf-8")
    script = ROOT / "tools" / "prepare-maintenance.py"
    subprocess.run(["python3", str(script), "--root", str(root), "--report", str(report)], check=True)
    init = (root / "ike/__init__.py").read_text()
    assert '__version__ = "1.6.2"' in init
    assert '__min_system__ = "1.6.2"' in init
    assert "pkgver=1.6.2" in (root / "PKGBUILD").read_text()
    assert "**Version 1.6.2**" in (root / "README.md").read_text()
    assert (root / "CHANGELOG.md").read_text(encoding="utf-8").startswith("# Changelog\n\n## 1.6.2\n")

    report.write_text(json.dumps({"errors": 0, "components": [{
        "name": "uBlock Origin scriptlets", "current": "old", "latest": "new",
        "update": True, "note": "scriptlet changes", "also": ""
    }]}), "utf-8")
    subprocess.run(["python3", str(script), "--root", str(root), "--report", str(report),
                    "--base-version", "1.6.0"], check=True)
    assert '__version__ = "1.6.1"' in (root / "ike/__init__.py").read_text()
    log = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    assert log.count("## 1.6.1") == 1 and "scriptlet changes" in log


@pytest.mark.skipif(not os.environ.get("ICE_TEST_APPIMAGE"), reason="needs ICE_TEST_APPIMAGE")
def test_appimage_has_exactly_the_pinned_packages(tmp_path):
    image = Path(os.environ["ICE_TEST_APPIMAGE"]).resolve()
    subprocess.run([str(image), "--appimage-extract", "usr/lib/ike-browser/BUNDLED.txt"],
                   cwd=tmp_path, check=True, capture_output=True)
    subprocess.run([str(image), "--appimage-extract", "usr/python/lib/*/site-packages/certifi/*"],
                   cwd=tmp_path, check=True, capture_output=True)
    bundled = (tmp_path / "squashfs-root/usr/lib/ike-browser/BUNDLED.txt").read_text().split()
    mod = load_tool()
    pins = {n: v for n, (_, v) in mod.read_pins(ROOT).items()}
    got = {mod.norm(x.split("==")[0]): x.split("==")[1] for x in bundled if not x.startswith(("Qt==", "pip=="))}
    assert got == pins
    assert list((tmp_path / "squashfs-root/usr/python/lib").glob("*/site-packages/certifi/cacert.pem"))
