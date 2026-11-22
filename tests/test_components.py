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
from conftest import APP, ROOT, needs_engine

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
    assert out.read_text() == "updates=1\nerrors=0\nrefused=0\n"


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

def test_the_test_tools_are_pinned_too():
    """1.1.19: pytest and ruff were installed at their newest version on every
    run, so a new release (a new lint rule) could turn main red with no change
    of I.K.E. They are pinned with the rest and follow the component check."""
    import re
    req = (ROOT / "tools/test-requirements.txt").read_text()
    assert re.search(r"^pytest==\d", req, re.M) and re.search(r"^ruff==\d", req, re.M)
    assert "pytest ruff" not in (ROOT / ".github/actions/ike-test-env/action.yml").read_text()
    autofix = (ROOT / ".github/workflows/autofix.yml").read_text()
    assert "-q ruff\n" not in autofix and autofix.count("grep -oE '^ruff==[0-9][0-9.]*$'") == 2
    tool = (ROOT / "tools/check-components.py").read_text()
    assert '"pytest", "ruff")' in tool


# --- Arch Linux's own packages (the system I.K.E. runs on) ---------------------
# Answers of Arch's package site as they look (archlinux.org/packages/search/json),
# written here by hand: the site is not reachable from every test machine.

ARCH_NOW = {"qt6-webengine": "6.140.0-1", "qt6-base": "6.12.0-5", "qt6-webchannel": "6.12.0-1",
            "qt6-svg": "6.12.0-1", "python-pyqt6": "6.12.1-1", "python-pyqt6-webengine": "6.140.1-1",
            "python": "3.14.10-1", "python-cryptography": "50.0.2-2", "python-jeepney": "0.9.0-3",
            "publicsuffix-list": "20260507.2070-1", "rust": "1:1.100.0-1",
            # 1.1.21-1.1.22: the font allowlist, the widget styles and KDE's theme, video
            "fontconfig": "2:2.17.1-1", "noto-fonts": "1:2026.11.01-1", "ttf-dejavu": "2.37+18+g9b5d1b2f-7",
            "breeze": "6.5.3-1", "oxygen": "6.5.3-1", "kvantum": "1.1.5-1", "plasma-integration": "6.5.3-1",
            "breeze-icons": "6.20.0-1", "ffmpeg": "2:8.0-3"}


def arch_site(versions, down=(), testing=None):
    """A stand-in for Arch's site: {package: "epoch:pkgver-pkgrel"}; packages in
    `down` raise as an unreachable site does; `testing` adds newer versions in
    the -testing repositories, which never count."""
    asked = []

    def entry(name, version, repo):
        epoch, _, rest = version.rpartition(":")
        pkgver, pkgrel = rest.rsplit("-", 1)
        return {"pkgname": name, "repo": repo, "arch": "x86_64", "pkgver": pkgver, "pkgrel": pkgrel,
                "epoch": int(epoch or 0)}

    def get(url, timeout=60):
        name = url.rsplit("=", 1)[1]
        asked.append(name)
        if name in down:
            raise OSError("network unreachable")
        results = []
        if name in (testing or {}):
            results.append(entry(name, testing[name], "extra-testing"))
        if name in versions:
            results.append(entry(name, versions[name], "core" if name == "python" else "extra"))
        return json.dumps({"version": 2, "limit": 250, "valid": True, "results": results}).encode()
    get.asked = asked
    return get


def arch_tested(packages, **facts):
    record = {"schema": 1, "packages": dict(packages), "python": "3.14.10", "qt": "6.12.0", "pyqt": "6.12.1",
              "chromium": "140.0.7339.264"}
    record.update(facts)
    record["run"] = {"id": 44934030244, "url": "https://github.com/o/r/actions/runs/44934030244",
                     "sha": "cd5cf6a0123456789", "date": "2026-11-21T18:10:00Z"}
    return {"tested": record}


def test_arch_versions_changed_unchanged_unreachable():
    """The Arch packages I.K.E. runs on, in core/extra now, against what the last
    green "Arch Linux" run on main tested. A site that cannot be reached is
    "source unreachable", never a change; -testing repositories never count."""
    mod = load_tool()
    assert set(mod.ARCH_PACKAGES) == set(ARCH_NOW)
    newer = {"qt6-webengine": "6.141.0-1", "python": "3.15.0-1"}
    same = mod.check_arch(arch_tested(ARCH_NOW), arch_site(ARCH_NOW, testing=newer))
    assert same["state"] == "same" and same["changed"] == [] and same["current"] == ARCH_NOW
    assert same["current"]["rust"] == "1:1.100.0-1"               # with its epoch, as pacman -Q writes it
    # a new engine and a rebuild of python (a new pkgrel counts: a rebuild can break too)
    moved = mod.check_arch(arch_tested(ARCH_NOW), arch_site(dict(ARCH_NOW, **{"qt6-webengine": "6.141.0-1",
                                                                         "python": "3.14.10-2"})))
    assert moved["state"] == "changed"
    assert moved["changed"] == [("qt6-webengine", "6.140.0-1", "6.141.0-1"), ("python", "3.14.10-1", "3.14.10-2")]
    # the site does not answer: nothing changed, never an update
    site = arch_site(ARCH_NOW, down=set(ARCH_NOW))
    down = mod.check_arch(arch_tested(ARCH_NOW), site)
    assert down["state"] == "unreachable" and down["changed"] == [] and down["current"] == {}
    assert set(down["unreachable"]) == set(ARCH_NOW)
    assert len(site.asked) == mod.ARCH_NETWORK_FAILURES            # not asked eleven times for nothing
    # one package unreachable, another one changed: the change still counts
    part = mod.check_arch(arch_tested(ARCH_NOW), arch_site(dict(ARCH_NOW, **{"qt6-base": "6.13.0-1"}),
                                                      down={"python-jeepney"}))
    assert part["state"] == "changed" and [c[0] for c in part["changed"]] == ["qt6-base"]
    assert list(part["unreachable"]) == ["python-jeepney"]
    gone = mod.check_arch(arch_tested(ARCH_NOW), arch_site({k: v for k, v in ARCH_NOW.items() if k != "qt6-svg"}))
    assert gone["state"] == "unreachable" and "not in Arch's core or extra" in gone["unreachable"]["qt6-svg"]
    # nothing tested yet (or GitHub could not be read): verify, even with the site down
    for saved in ({"tested": None}, {"tested": None, "error": "RuntimeError: HTTP 502"}, {}):
        assert mod.check_arch(saved, arch_site(ARCH_NOW, down=set(ARCH_NOW)))["state"] == "untested"
    # a package the tested run did not record (a newly followed one) is a change
    fewer = {k: v for k, v in ARCH_NOW.items() if k != "publicsuffix-list"}
    assert mod.check_arch(arch_tested(fewer), arch_site(ARCH_NOW))["changed"] == [
        ("publicsuffix-list", "", "20260507.2070-1")]
    # one the tested run recorded as not installed (arch.yml does not install it
    # yet) was not tested: no change to verify, or arch.yml would start every day
    absent = dict(ARCH_NOW, kvantum="")
    quiet = mod.check_arch(arch_tested(absent), arch_site(ARCH_NOW))
    assert quiet["state"] == "same" and quiet["changed"] == []
    assert "| kvantum | 1.1.5-1 | not installed by arch.yml: **not verified** | - |" in mod.arch_markdown(quiet)
    # the Arch failure's description still names it (the fix's AI reads it)
    assert mod.arch_changes(absent, ARCH_NOW) == [("kvantum", "", "1.1.5-1")]


def _zip(record):
    import io
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("arch-versions.json", json.dumps(record))
    return buf.getvalue()


def test_the_tested_versions_come_from_the_last_green_run_on_main(tmp_path):
    """Read back with GET calls of GitHub's API only: the newest green arch.yml
    run on main that kept its versions (older runs did not record them)."""
    mod = load_tool()
    record = arch_tested(ARCH_NOW)["tested"]
    del record["run"]
    paths = []

    def api(path, raw=False):
        paths.append(path)
        if "/workflows/arch.yml/runs?" in path:
            assert "branch=main" in path and "status=success" in path
            return {"workflow_runs": [
                {"id": 3, "conclusion": "success", "head_branch": "main", "head_sha": "c3", "html_url": "u3"},
                {"id": 2, "conclusion": "success", "head_branch": "main", "head_sha": "c2", "html_url": "u2",
                 "run_started_at": "2026-11-22T03:41:00Z"},
                {"id": 1, "conclusion": "success", "head_branch": "main", "head_sha": "c1", "html_url": "u1"}]}
        if path.endswith("/runs/3/artifacts?name=arch-versions"):
            return {"artifacts": [{"id": 30, "name": "arch-versions", "expired": True}]}     # gone
        if path.endswith("/runs/2/artifacts?name=arch-versions"):
            return {"artifacts": [{"id": 20, "name": "arch-versions", "expired": False}]}
        if path.endswith("/artifacts/20/zip"):
            assert raw
            return _zip(record)
        raise AssertionError(path)
    got = mod.last_tested_arch("o/r", api)
    assert got["packages"] == ARCH_NOW and got["python"] == "3.14.10"
    assert got["run"] == {"id": 2, "url": "u2", "sha": "c2", "date": "2026-11-22T03:41:00Z"}
    assert not any(p.startswith("-") or " " in p for p in paths)           # paths of GETs, nothing else
    # nothing recorded on main yet; GitHub not answering: the check verifies
    assert mod.last_tested_arch("o/r", lambda path, raw=False: {"workflow_runs": []}) is None

    def broken(path, raw=False):
        raise RuntimeError("gh api: HTTP 502")
    saved = mod.save_arch_tested(tmp_path / "t.json", "o/r", broken)
    assert saved["tested"] is None and "HTTP 502" in saved["error"]
    assert json.loads((tmp_path / "t.json").read_text()) == saved
    # the tool asks gh for GETs only
    text = (ROOT / "tools/check-components.py").read_text()
    body = text.split("def gh_api(", 1)[1].split("\ndef ", 1)[0]
    assert '["gh", "api", path]' in body and "-X" not in body and "--method" not in body


def test_arch_records_what_it_really_tests(tmp_path, monkeypatch):
    """arch.yml records pacman's versions and Python, Qt, PyQt and Chromium as
    I.K.E. reports them; what cannot be read is recorded empty, never a failure."""
    mod = load_tool()
    monkeypatch.setenv("GITHUB_SHA", "abc123")
    monkeypatch.setenv("GITHUB_RUN_ID", "77")
    pacman = "\n".join("%s %s" % (n, v) for n, v in ARCH_NOW.items() if n != "python-jeepney")
    probe = json.dumps({"python": "3.14.10", "qt": "6.12.0", "pyqt": "6.12.1", "chromium": "140.0.7339.264"})
    out = tmp_path / "out" / "arch-versions.json"
    md = mod.record_arch(out, query=lambda: pacman, probe=lambda: probe)
    record = json.loads(out.read_text())
    assert record["packages"] == dict(ARCH_NOW, **{"python-jeepney": ""})
    assert (record["python"], record["chromium"], record["commit"], record["run"]) == \
        ("3.14.10", "140.0.7339.264", "abc123", "77")
    assert "| rust | 1:1.100.0-1 |" in md and "| python-jeepney | not installed |" in md
    assert "Chromium 140.0.7339.264 (as I.K.E. reports it)" in md

    def no_pacman():
        raise FileNotFoundError("pacman")
    mod.record_arch(out, query=no_pacman, probe=lambda: "not json")
    record = json.loads(out.read_text())
    assert set(record["packages"].values()) == {""} and "error" in record
    # this very probe, here: the engine's version as chromever.py gives it
    real = json.loads(subprocess.run([mod.sys.executable, "-c", mod.ARCH_PROBE], cwd=str(ROOT), capture_output=True,
                                     text=True, timeout=300).stdout.strip().splitlines()[-1])
    assert real["python"] and re.fullmatch(r"\d+\.\d+\.\d+\.\d+", real.get("chromium", "")), real


@needs_node
def test_the_report_says_what_was_really_tested(tool, repo, tmp_path, monkeypatch):
    """--arch: the report and the outputs say whether Arch changed and which
    versions were really tested; the bundled components' counts and the
    maintenance (--apply, no --arch) stay as they were."""
    saved = tmp_path / "arch-tested.json"
    saved.write_text(json.dumps(arch_tested(ARCH_NOW)))
    monkeypatch.setattr(tool, "arch_current",
                        lambda get=None: (dict(ARCH_NOW, **{"qt6-webengine": "6.141.0-1"}), {}))
    out = tmp_path / "gh-output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    tool.main(["--root", str(repo), "--ubo-src", str(tool.ubo), "--arch", str(saved),
               "--json", str(tmp_path / "r.json"), "--markdown", str(tmp_path / "r.md")])
    assert out.read_text() == "updates=0\nerrors=0\nrefused=0\narch=changed\n"
    data = json.loads((tmp_path / "r.json").read_text())
    assert data["updates"] == 0 and len(data["components"]) == 5
    assert data["arch"]["state"] == "changed"
    assert data["arch"]["changed"] == [{"package": "qt6-webengine", "tested": "6.140.0-1", "now": "6.141.0-1"}]
    assert data["arch"]["tested"]["run"]["sha"] == "cd5cf6a0123456789"
    md = (tmp_path / "r.md").read_text()
    assert "**Arch changed: compatibility to verify.**" in md and "Not a release by itself" in md
    assert "Really tested: run [44934030244](https://github.com/o/r/actions/runs/44934030244) on commit " \
           "`cd5cf6a012`" in md and "Python 3.14.10, Qt 6.12.0, PyQt 6.12.1, Chromium 140.0.7339.264" in md
    assert "| qt6-webengine | 6.141.0-1 | 6.140.0-1 | **yes** |" in md
    assert "| python | 3.14.10-1 | 3.14.10-1 | no |" in md
    # unreachable: said so, no change; a missing file of tested versions: verify
    monkeypatch.setattr(tool, "arch_current", lambda get=None: ({}, {n: "OSError: down" for n in ARCH_NOW}))
    out.write_text("")
    tool.main(["--root", str(repo), "--ubo-src", str(tool.ubo), "--arch", str(saved), "--markdown",
               str(tmp_path / "r.md")])
    assert out.read_text().endswith("arch=unreachable\n")
    md = (tmp_path / "r.md").read_text()
    assert "| qt6-webengine | source unreachable |" in md and "Source unreachable: OSError: down" in md
    out.write_text("")
    tool.main(["--root", str(repo), "--ubo-src", str(tool.ubo), "--arch", str(tmp_path / "missing.json")])
    assert out.read_text().endswith("arch=untested\n")
    # without --arch (the daily maintenance): not asked, not written
    monkeypatch.setattr(tool, "arch_current", lambda get=None: pytest.fail("Arch asked without --arch"))
    out.write_text("")
    assert tool.main(["--root", str(repo), "--ubo-src", str(tool.ubo), "--apply"]) == 0
    assert out.read_text() == "updates=0\nerrors=0\nrefused=0\n"


def test_the_arch_workflows():
    """arch.yml tests and records the followed packages, runs on every push to
    main and when the daily check finds Arch changed; the daily check reads
    with GET only, and only its own small job may start a workflow."""
    mod = load_tool()
    arch = (ROOT / ".github/workflows/arch.yml").read_text()
    head = arch.split("\njobs:\n", 1)[0]
    assert "push:\n    branches: [main]" in head and "workflow_dispatch:" in head and "schedule:" in head
    assert "permissions:\n  contents: read\n" in head and "pull_request_target" not in arch
    install = arch.split("- name: Arch's packages", 1)[1].split("- name:", 1)[0]
    # what is recorded is installed (qt6-base comes with python-pyqt6 and qt6-webengine,
    # fontconfig with qt6-base)
    brought = {"qt6-base", "fontconfig"}
    # followed since 1.1.22 (the font allowlist, the widget styles and KDE's
    # theme, video); arch.yml installs them on branch fix/1.1.22, which this
    # branch must not touch: until it is merged they are recorded as "not
    # installed" (not verified, never a change: test above). Only these may wait.
    waiting = {"noto-fonts", "ttf-dejavu", "breeze", "oxygen", "kvantum", "plasma-integration", "breeze-icons",
               "ffmpeg"}
    assert waiting <= set(mod.ARCH_PACKAGES)
    for name in mod.ARCH_PACKAGES:
        assert name in brought | waiting or re.search(r"\s%s[\s\\]" % re.escape(name), install), name
    depends = re.search(r"^depends=\(([^)]*)\)", (ROOT / "PKGBUILD").read_text(), re.M).group(1)
    for name in re.findall(r"'([^']+)'", depends):
        assert name in mod.ARCH_PACKAGES or name == "hicolor-icon-theme", name   # every runtime dependency
    record = arch.split("- name: The versions tested", 1)[1].split("- name:", 1)[0]
    assert "tools/check-components.py --record-arch out/arch-versions.json" in record
    assert '"$GITHUB_STEP_SUMMARY"' in record
    upload = arch.split("name: %s\n" % mod.ARCH_ARTIFACT, 1)
    assert len(upload) == 2 and "path: out/%s" % mod.ARCH_FILE in upload[1].split("\n      - ", 1)[0]
    assert arch.index("- name: The versions tested") < arch.index("- name: Tests (Arch's Qt)")
    daily = (ROOT / ".github/workflows/daily-check.yml").read_text()
    parts = re.split(r"^  ([a-z-]+):\n", daily.split("\njobs:\n", 1)[1], flags=re.M)
    jobs = dict(zip(parts[1::2], parts[2::2]))
    assert set(jobs) == {"check", "lists", "update-issue", "start-arch", "ledger", "ai-work"}
    # WP8, WP9: the AI work the ledger made due; it only starts workflows
    assert re.search(r"permissions:\n\s+actions: write .*\n\s+contents: read\n\s+steps:", jobs["ai-work"])
    assert "issues:" not in jobs["ai-work"] and "needs: ledger" in jobs["ai-work"]
    # 1.1.20: the filter lists in main's engine; reads the repository only, no token
    lists = jobs["lists"]
    assert re.search(r"permissions:\n\s+contents: read\n\s+outputs:", lists) and "GH_TOKEN" not in lists
    assert "tools/check-components.py --filter-lists lists.json --markdown lists.md" in lists
    assert "needs: [check, lists]" in jobs["update-issue"] and "needs.check.result == 'success'" in jobs["update-issue"]
    assert re.search(r"permissions:\n\s+actions: read .*\n\s+contents: read\n", jobs["check"])
    assert "--save-arch-tested arch-tested.json" in jobs["check"] and "--arch arch-tested.json" in jobs["check"]
    # the token only in the step that reads GitHub, not where others' sources are built
    steps = jobs["check"].split("      - ")
    assert [s.split("\n")[0] for s in steps if "GH_TOKEN" in s] == ["name: The Arch versions last tested on main"]
    assert "write" not in jobs["check"]
    assert "arch: ${{ steps.check.outputs.arch }}" in jobs["check"]
    start = jobs["start-arch"]
    assert "needs.check.outputs.arch == 'changed' || needs.check.outputs.arch == 'untested'" in start
    assert re.search(r"permissions:\n\s+actions: write .*\n\s+steps:", start)
    assert "gh workflow run arch.yml --ref main" in start and "checkout" not in start


# --- a builder that refuses a new upstream version (1.1.20) -------------------
# "source unreachable" (the network, a site, git) stays infrastructure and
# applies nothing; a builder of a customised component that refuses the new
# version keeps that component at the version in use, with I.K.E.'s changes,
# reports why, and lets every other component be applied and tested.


@needs_node
def test_a_refused_builder_keeps_its_component_and_the_others_go_on(tool, repo, tmp_path, monkeypatch):
    tool.up["adblock"] = "0.14.0"
    # uBlock Origin moves its scriptlet library: the builder cannot read it
    lib = tool.ubo / "src" / "js" / "resources"
    (lib / "scriptlets.js").rename(lib / "scriptlets-core.js")
    commit = ["git", "-C", str(tool.ubo), "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run(commit + ["add", "-A"], check=True)
    subprocess.run(commit + ["commit", "-q", "-m", "moved"], check=True)
    r = by_name(tool.check_all(repo, tool.ubo, tmp_path / "w"))
    ubo = r["uBlock"]
    assert ubo["refused"] and not ubo["update"] and not ubo["error"]
    rep = ubo["refused"]
    assert rep["component"] == "uBlock Origin scriptlets" and "build-ubo-scriptlets.mjs" in rep["step"]
    assert rep["current"] != rep["latest"] and rep["reason"].startswith("the builder stopped")
    assert "src/js/resources/scriptlets.js is not in the new version" in rep["context"]
    assert "scriptlets-core.js" in rep["context"] and rep["log"]
    assert r["adblock-rust"]["update"] and not r["adblock-rust"].get("refused")
    # --apply: the others are applied (the engine), the refused one stays as it is
    before = (repo / "ike/resources/ubo-scriptlets.json").read_text()
    out = tmp_path / "gh-output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    assert tool.main(["--root", str(repo), "--ubo-src", str(tool.ubo), "--apply", "--json", str(tmp_path / "r.json"),
                      "--markdown", str(tmp_path / "r.md")]) == 0
    assert 'adblock = { version = "=0.14.0"' in (repo / "ike-adblock/Cargo.toml").read_text()
    assert (repo / "ike/resources/ubo-scriptlets.json").read_text() == before
    assert out.read_text() == "updates=1\nerrors=0\nrefused=1\n"
    data = json.loads((tmp_path / "r.json").read_text())
    assert data["refused"] == 1 and data["errors"] == 0
    assert by_name(data["components"])["uBlock"]["refused"]["step"] == rep["step"]
    md = (tmp_path / "r.md").read_text()
    assert md.startswith("Un componente non accetta più le modifiche di I.K.E.")
    assert "| uBlock Origin scriptlets |" in md and "**refused**" in md
    assert "### Component incompatibility: a builder refused the new upstream version" in md
    assert "stays at the version in use, with I.K.E.'s changes" in md and "automatic fix" in md
    assert "<summary>The new upstream version around the anchor</summary>" in md
    # a library whose scriptlets need an entry it does not have is refused too
    (lib / "scriptlets-core.js").rename(lib / "scriptlets.js")
    (lib / "scriptlets.js").write_text(UBO_JS.replace("dependencies: ['safe-self.fn']", "dependencies: ['gone.fn']") % "v9")
    subprocess.run(commit + ["commit", "-q", "-am", "dep"], check=True)
    ubo = by_name(tool.check_all(repo, tool.ubo, tmp_path / "w2"))["uBlock"]
    assert ubo["refused"] and "gone.fn" in ubo["refused"]["reason"]


def darkreader_upstream(tool, monkeypatch, tmp_path, lib_text, version="9.9.9"):
    """Stand-ins for npm (the "darkreader" package with this engine, and its
    sha512) and for Dark Reader's repository (its lists)."""
    import base64
    import hashlib
    import io
    import tarfile
    tgz = io.BytesIO()
    with tarfile.open(fileobj=tgz, mode="w:gz") as tar:
        data = lib_text.encode()
        info = tarfile.TarInfo("package/darkreader.js")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    blob = tgz.getvalue()
    meta = {"version": version, "dist": {
        "tarball": "https://registry.npmjs.org/darkreader/-/darkreader-%s.tgz" % version,
        "integrity": "sha512-" + base64.b64encode(hashlib.sha512(blob).digest()).decode()}}

    def fetch_source(url, timeout=60):
        return json.dumps(meta).encode() if url == tool.DARKREADER_NPM else blob
    monkeypatch.setattr(tool, "fetch_source", fetch_source)
    src = tmp_path / "dr"
    cfg = src / "src" / "config"
    cfg.mkdir(parents=True)
    (cfg / "dynamic-theme-fixes.config").write_text("*\n\nCSS\nbody { color: red }\n")
    (cfg / "dark-sites.config").write_text("dark.example\n")
    (cfg / "detector-hints.config").write_text("own.example\n\nNO DARK THEME\n")
    commit = ["git", "-C", str(src), "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run(commit[:3] + ["init", "-q"], check=True)
    subprocess.run(commit + ["add", "-A"], check=True)
    subprocess.run(commit + ["commit", "-q", "-m", "lists"], check=True)
    return src


@pytest.mark.skipif(not shutil.which("git"), reason="needs git")
def test_a_dark_reader_patch_that_no_longer_fits_is_reported_with_its_anchor(repo, tmp_path, monkeypatch):
    """Dark Reader changes the text one of I.K.E.'s patches changes: the
    report names the patch, the versions and the new engine's lines around
    the anchor; nothing of Dark Reader is replaced."""
    from test_darkreader import build_tool, fake_engine
    tool = load_tool()
    for rel in ("ike/resources/darkreader-data.json", "tools/build-darkreader.py"):
        shutil.copy(ROOT / rel, repo / rel)
    patches = build_tool().PATCHES
    old = dict((n, o) for n, o, _new in patches)["style-moves"]
    changed = old.replace("nextStyleSiblings.set(style, style.nextElementSibling);",
                          "nextStyleSiblings.set(style, getNext(style));")
    # (fake_engine runs the texts together: the changed one on lines of its own)
    lib = fake_engine(patches, skip="style-moves").replace("})();\r\n", "\r\n" + changed.replace("\n", "\r\n") + "})();\r\n")
    src = darkreader_upstream(tool, monkeypatch, tmp_path, lib)
    results = tool.check_all(repo, work=tmp_path / "w", dr_src=src)
    dr = by_name(results)["Dark"]
    assert dr["refused"] and not dr["update"] and not dr["error"], dr
    rep = dr["refused"]
    assert rep["step"] == "tools/build-darkreader.py, I.K.E.'s patch 'style-moves' (PATCHES)"
    current = json.loads((ROOT / "ike/resources/darkreader-data.json").read_text())["version"]
    assert rep["current"].startswith(current + ", lists") and rep["latest"].startswith("9.9.9, lists")
    assert "found 0 times instead of once" in rep["reason"] and "'style-moves'" in rep["log"]
    assert "anchor lines not found in the new version (1 of 4):" in rep["context"]
    assert "nextStyleSiblings.set(style, style.nextElementSibling);" in rep["context"]
    assert 'the new version around the anchor line "function saveStylePosition(style) {"' in rep["context"]
    assert "nextStyleSiblings.set(style, getNext(style));" in rep["context"]     # the upstream lines, numbered
    md = tool.to_markdown(results)
    assert "**Dark Reader (engine and lists)**: %s" % rep["current"] in md and "patch 'style-moves'" in md

    # Dark Reader's site unreachable: infrastructure, never "refused"
    def down(url, timeout=60):
        raise tool.SourceUnreachable("%s: timed out" % url)
    monkeypatch.setattr(tool, "fetch_source", down)
    dr = by_name(tool.check_all(repo, work=tmp_path / "w2", dr_src=src))["Dark"]
    assert dr["error"].startswith("source unreachable: SourceUnreachable") and not dr["refused"]


def test_anchor_context_places():
    tool = load_tool()
    text = "a\nb\nanchor 1\nanchor 2\nc\nanchor 1\nanchor 2\nd\n"
    twice = tool.anchor_context(text, "anchor 1\nanchor 2\n", around=1)
    assert "found at line 3:" in twice and "found at line 6:" in twice
    gone = tool.anchor_context("x\ny\n", "nothing\nof this\n")
    assert "(2 of 2)" in gone and "no line of the anchor is found once" in gone


def test_the_maintenance_and_the_plan_tell_refused_from_unreachable():
    """The maintenance's check step fails only when a source is unreachable
    (infrastructure); a refused builder does not stop it, and its report
    reaches a person through the components issue and the candidate's PR."""
    maint = (ROOT / ".github/workflows/daily-maintenance.yml").read_text()
    assert "- name: Check and apply component updates (an unreachable source stops all" in maint
    plan = (ROOT / "tools/autofix-plan.py").read_text()
    assert 'SOURCES_STEP = "Check and apply component updates"' in plan
    assert "a component source could not be reached" in plan
    daily = (ROOT / ".github/workflows/daily-check.yml").read_text()
    assert "REFUSED: ${{ needs.check.outputs.refused }}" in daily
    assert '"$REFUSED" -gt 0' in daily and "Component incompatibility" in daily


# --- the default filter lists in the bundled engine (1.1.20) -----------------

SNAPSHOT = (ROOT / "tests/data/filter-lists-snapshot.txt").read_bytes()
UBO_URL = "https://ublockorigin.github.io/uAssets/filters/filters.txt"
LISTS = [{"name": "uBlock filters", "group": "ads", "enabled": True, "url": UBO_URL},
         {"name": "EasyList", "group": "ads", "enabled": True, "url": "https://easylist.to/easylist/easylist.txt"},
         {"name": "Cookies", "group": "consent", "enabled": True, "url": "https://cookies.example/list.txt"},
         {"name": "Off", "group": "ads", "enabled": False, "url": "https://off.example/list.txt"}]


def served(pages):
    """A stand-in for the lists' sites: their pages, or "unreachable"."""
    def get(url):
        if url not in pages:
            raise OSError("network unreachable: %s" % url)
        return pages[url]
    return get


def _ike_root():
    """The copy of I.K.E. under test: the one this test run has already
    imported (the checkout, or the installed package with IKE_TEST_APP),
    else APP. The check refuses to mix two copies."""
    import sys
    mod = sys.modules.get("ike")
    if mod is not None and getattr(mod, "__file__", None):
        return Path(mod.__file__).resolve().parent.parent
    return APP


@needs_engine
def test_the_default_lists_in_the_bundled_engine():
    tool = load_tool()
    sub = b"! sub-list\n||sub.example^\nsub.example##+js(set, a, 1)\n"
    pages = {UBO_URL: SNAPSHOT + b"\n!#include sub.txt\n!#include missing.txt\n",
             "https://ublockorigin.github.io/uAssets/filters/sub.txt": sub,
             "https://easylist.to/easylist/easylist.txt": SNAPSHOT + b"\nother.example##+js(no-such-scriptlet, x)\n",
             "https://cookies.example/list.txt": b"! cookies\ncookies.example##+js(unknown-there, x)\n##.cookie-bar\n"}
    info = tool.check_filter_lists(_ike_root(), get=served(pages), lists=LISTS)
    assert [r["name"] for r in info["lists"]] == ["uBlock filters", "EasyList", "Cookies"]     # enabled only
    assert info["engine"]["built"] and info["engine"]["parse_report"], info["engine"]
    ubo, easy, cookies = info["lists"]
    assert ubo["state"] == "ok" and ubo["includes_missing"] == ["missing.txt"]
    assert ubo["network"] >= 3 and ubo["cosmetic"] >= 15 and ubo["errors"] >= 2 and ubo["unsupported"] == 0
    assert any("html filtering" in e[2] for e in ubo["examples"])
    # the scriptlets as I.K.E. reads them: the trusted ones only from uBlock Origin's own site;
    # the "!#else" branch (another blocker's rules) is not read
    assert ubo["scriptlets"]["rules"] == 15 and ubo["scriptlets"]["untrusted"] == 0          # 14 + the sub-list's
    assert easy["scriptlets"]["untrusted"] == 3 and easy["scriptlets"]["rules"] == 11
    assert cookies["scriptlets"] is None                     # I.K.E. runs no scriptlets of the cookie lists
    # uBlock Origin's own resources: known, a note; a name nobody knows: a finding (drift)
    assert set(info["unknown_scriptlets"]) == {"noeval", "nofab", "popads.net", "fingerprint2", "no-such-scriptlet"}
    assert info["unknown_scriptlets"]["noeval"]["lists"] == ["uBlock filters", "EasyList"]
    assert info["state"] == "findings" and len(info["findings"]) == 1
    assert "`no-such-scriptlet` (1 rules in EasyList)" in info["findings"][0] and "drift" in info["findings"][0]
    assert sum("`noeval`" in n for n in info["notes"]) == 1
    md = tool.lists_markdown(info)
    assert "### The default filter lists in the bundled engine" in md and "**Findings about the components**" in md
    assert "| uBlock filters | ok |" in md and "not read (cookie list)" in md and "built from the lists: yes" in md
    # every list unreachable: said so, nothing found, nothing failed
    info = tool.check_filter_lists(_ike_root(), get=served({}), lists=LISTS)
    assert info["state"] == "unreachable" and info["unreachable"] == 3 and not info["findings"]
    assert "source unreachable" in tool.lists_markdown(info)
    # a list that is no list (binary, empty): a finding about that list
    info = tool.check_filter_lists(_ike_root(), get=served({UBO_URL: b"\x00" * 100}), lists=LISTS[:1])
    assert info["state"] == "findings" and "not a usable list" in info["findings"][0]


@needs_engine
def test_the_lists_check_writes_its_report(tmp_path, monkeypatch):
    tool = load_tool()
    monkeypatch.setattr(tool, "fetch_source", lambda url, timeout=60: served({UBO_URL: SNAPSHOT})(url))
    real = tool.check_filter_lists
    monkeypatch.setattr(tool, "check_filter_lists", lambda root: real(_ike_root(), lists=LISTS[:2]))
    out = tmp_path / "gh-output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    assert tool.main(["--filter-lists", str(tmp_path / "lists.json"), "--markdown", str(tmp_path / "lists.md")]) == 0
    assert out.read_text() == "lists=ok\nlists_findings=0\nlists_unreachable=1\n"
    data = json.loads((tmp_path / "lists.json").read_text())
    assert data["state"] == "ok" and data["lists"][0]["scriptlets"]["rules"] == 14
    md = (tmp_path / "lists.md").read_text()
    assert "Some lists could not be downloaded today (source unreachable): EasyList." in md


@pytest.mark.skipif(not os.environ.get("IKE_TEST_NETWORK"), reason="IKE_TEST_NETWORK=1 to use the real lists")
@needs_engine
def test_the_real_default_lists(tmp_path):
    """The lists of today, from their sites: whatever they hold, the check
    reports and never fails."""
    out = tmp_path / "lists.json"
    subprocess.run(["python3", str(ROOT / "tools/check-components.py"), "--filter-lists", str(out)], check=True)
    data = json.loads(out.read_text())
    assert data["state"] in ("ok", "findings", "unreachable")
    if data["state"] != "unreachable":
        assert data["engine"]["built"], data["engine"]


FAKE_THIRD_PARTY = """\
import json
from pathlib import Path
root = Path(__file__).resolve().parent.parent
data = json.loads((root / "ike/resources/ubo-scriptlets.json").read_text("utf-8"))
(root / "licenses").mkdir(exist_ok=True)
with open(root / "licenses/seen.txt", "a", encoding="utf-8") as f:
    f.write(data["scriptlets"]["abort-on-property-read.js"]["src"] + "\\n")
"""


@needs_node
def test_the_licences_follow_every_component_applied(tool, repo, tmp_path):
    """The trials of 2026-11-22: the candidate brought new uBlock Origin
    scriptlets, but tools/third-party.py ran only for the crates, before the
    scriptlets were copied; licenses/NOTICE.ubo-scriptlets kept the old commit
    and the candidate's tests failed at "Licences". It now runs once, after
    every component is applied, and sees the new scriptlets."""
    (repo / "tools/third-party.py").write_text(FAKE_THIRD_PARTY, "utf-8")
    make_ubo(tool.ubo, "v3")
    assert tool.main(["--root", str(repo), "--ubo-src", str(tool.ubo), "--apply"]) == 0
    seen = (repo / "licenses/seen.txt").read_text("utf-8").splitlines()
    assert seen and "'v3'" in seen[-1], seen
