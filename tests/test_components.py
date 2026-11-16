"""Tests for the Arch-only component update checker."""

import json
import runpy
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load_tool():
    namespace = runpy.run_path(
        ROOT / "tools" / "check-components.py", run_name="ike_check_components"
    )
    return SimpleNamespace(**namespace)

def make_adblock_repo(root, version="0.13.5"):
    crate = root / "ike-adblock"
    (crate / "src").mkdir(parents=True)
    (crate / "Cargo.toml").write_text(
        '[package]\nname = "ike-adblock"\nversion = "1.0.0"\n\n'
        '[dependencies]\nadblock = { version = "=%s" }\n' % version,
        encoding="utf-8",
    )
    (crate / "src" / "lib.rs").write_text(
        'const ENGINE_VERSION: &str = "%s";\n' % version, encoding="utf-8"
    )
    (crate / "Cargo.lock").write_text(
        '[[package]]\nname = "adblock"\nversion = "%s"\n' % version,
        encoding="utf-8",
    )
    return crate


def test_version_order_and_stability():
    tool = load_tool()
    assert tool.vkey("0.14.0") > tool.vkey("0.13.9")
    assert tool.is_stable("0.14.0")
    assert not tool.is_stable("0.14.0-beta.1")


def test_current_adblock_checks_all_three_version_pins(tmp_path):
    tool = load_tool()
    make_adblock_repo(tmp_path)
    assert tool.current_adblock(tmp_path) == "0.13.5"
    (tmp_path / "ike-adblock" / "src" / "lib.rs").write_text(
        'const ENGINE_VERSION: &str = "0.13.4";\n', encoding="utf-8"
    )
    with pytest.raises(RuntimeError, match="version mismatch"):
        tool.current_adblock(tmp_path)


def test_latest_adblock_ignores_yanked_and_prerelease(monkeypatch):
    tool = load_tool()
    lines = [
        {"vers": "0.13.5", "yanked": False},
        {"vers": "0.14.0-beta.1", "yanked": False},
        {"vers": "0.13.9", "yanked": True},
        {"vers": "0.14.0", "yanked": False},
    ]
    monkeypatch.setattr(tool, "fetch", lambda _url: "\n".join(map(json.dumps, lines)).encode())
    assert tool.latest_adblock() == "0.14.0"


def test_apply_adblock_updates_manifest_engine_and_lock_command(tmp_path, monkeypatch):
    tool = load_tool()
    crate = make_adblock_repo(tmp_path)
    calls = []
    monkeypatch.setattr(tool.shutil, "which", lambda _name: "/usr/bin/cargo")
    monkeypatch.setattr(tool, "run", lambda command, **_kwargs: calls.append(command) or "")
    tool.apply_adblock(tmp_path, {"latest": "0.14.0"})
    assert 'version = "=0.14.0"' in (crate / "Cargo.toml").read_text(encoding="utf-8")
    assert '"0.14.0"' in (crate / "src" / "lib.rs").read_text(encoding="utf-8")
    assert calls and calls[0][:5] == [
        "cargo", "update", "-p", "adblock", "--precise"
    ]
    assert calls[0][5] == "0.14.0"


def test_scriptlets_hash_tracks_payload_not_metadata():
    tool = load_tool()
    first = {"commit": "a", "date": "today", "scriptlets": {"one.js": {"code": "a"}}}
    second = {"commit": "b", "date": "tomorrow", "scriptlets": {"one.js": {"code": "a"}}}
    third = {"commit": "b", "date": "tomorrow", "scriptlets": {"one.js": {"code": "b"}}}
    assert tool.scriptlets_hash(first) == tool.scriptlets_hash(second)
    assert tool.scriptlets_hash(first) != tool.scriptlets_hash(third)


def test_check_scriptlets_detects_changed_scriptlet(tmp_path, monkeypatch):
    tool = load_tool()
    resource = tmp_path / "ike" / "resources"
    resource.mkdir(parents=True)
    (resource / "ubo-scriptlets.json").write_text(json.dumps({
        "commit": "old", "date": "yesterday", "scriptlets": {"one.js": {"code": "old"}},
    }), encoding="utf-8")
    work = tmp_path / "work"
    work.mkdir()

    def build(_root, _work, _source):
        output = work / "ubo-scriptlets.json"
        output.write_text(json.dumps({
            "commit": "new", "date": "today", "scriptlets": {"one.js": {"code": "new"}},
        }), encoding="utf-8")
        return output

    monkeypatch.setattr(tool, "build_scriptlets", build)
    result = tool.check_scriptlets(tmp_path, work)
    assert result["update"] is True
    assert result["note"] == "1 changed, 0 new, 0 removed"
    tool.apply_scriptlets(tmp_path, result)
    assert json.loads((resource / "ubo-scriptlets.json").read_text(encoding="utf-8"))["commit"] == "new"


def test_check_all_keeps_one_component_error_separate(tmp_path, monkeypatch):
    tool = load_tool()

    def failed(_root):
        raise RuntimeError("crates.io unavailable")

    def good(_root, _work, _source):
        return {"current": "a", "latest": "a", "update": False, "note": ""}

    monkeypatch.setattr(tool, "check_adblock", failed)
    monkeypatch.setattr(tool, "check_scriptlets", good)
    results = tool.check_all(tmp_path, work=tmp_path / "work")
    assert results[0]["error"] == "RuntimeError: crates.io unavailable"
    assert results[1]["error"] == ""
    assert results[1]["update"] is False


def test_prepare_maintenance_does_not_require_ike_readme_markers(tmp_path):
    package = tmp_path / "ike"
    package.mkdir()
    (package / "__init__.py").write_text(
        '__version__ = "1.6.1"\n__min_system__ = "1.6.1"\n', encoding="utf-8"
    )
    (tmp_path / "PKGBUILD").write_text(
        "pkgver=1.6.1\npkgrel=2\n", encoding="utf-8"
    )
    readme = "# I.K.E. Browser\n\nArch / CachyOS only.\n"
    (tmp_path / "README.md").write_text(readme, encoding="utf-8")
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## 1.6.1\n\nExisting release.\n", encoding="utf-8"
    )
    report = tmp_path / "report.json"
    report.write_text(json.dumps({
        "errors": 0,
        "components": [{
            "name": "uBlock Origin scriptlets",
            "current": "old",
            "latest": "new",
            "update": True,
            "note": "payload changed",
        }],
    }), encoding="utf-8")
    subprocess.run([
        sys.executable, str(ROOT / "tools" / "prepare-maintenance.py"),
        "--root", str(tmp_path), "--report", str(report), "--base-version", "1.6.1",
    ], check=True)
    assert '__version__ = "1.6.2"' in (package / "__init__.py").read_text(encoding="utf-8")
    assert "pkgver=1.6.2" in (tmp_path / "PKGBUILD").read_text(encoding="utf-8")
    assert "pkgrel=1" in (tmp_path / "PKGBUILD").read_text(encoding="utf-8")
    assert (tmp_path / "README.md").read_text(encoding="utf-8") == readme
    assert "## 1.6.2" in (tmp_path / "CHANGELOG.md").read_text(encoding="utf-8")
