"""tools/audit-deps.py: known vulnerabilities are reported, and a tool that is
missing or fails is an error, never "nothing found"."""

import importlib.util
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load():
    spec = importlib.util.spec_from_file_location("audit_deps", ROOT / "tools/audit-deps.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_missing_tools_are_errors(monkeypatch, tmp_path):
    mod = load()
    monkeypatch.setattr(mod.shutil, "which", lambda name: None)
    out = tmp_path / "gh"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    mod.main(["--json", str(tmp_path / "a.json"), "--markdown", str(tmp_path / "a.md")])
    rep = json.loads((tmp_path / "a.json").read_text())
    assert rep["errors"] and not rep["rust"] and not rep["python"]
    md = (tmp_path / "a.md").read_text()
    assert "Could not check" in md and "None known" not in md
    assert "audit_errors=%d" % len(rep["errors"]) in out.read_text()


def test_findings_are_reported(monkeypatch, tmp_path):
    mod = load()
    monkeypatch.setattr(mod.shutil, "which", lambda name: "/usr/bin/" + name)

    def fake_run(cmd, **kw):
        if cmd[0] == "cargo":
            data = {"vulnerabilities": {"list": [{"advisory": {"id": "RUSTSEC-2099-0001", "title": "bad"},
                                                  "package": {"name": "pyo3", "version": "0.1.0"}}]}}
        else:
            data = {"dependencies": [{"name": "certifi", "version": "1.0", "vulns": [
                {"id": "PYSEC-2099-1", "fix_versions": ["2.0"]}]}]}
        return subprocess.CompletedProcess(cmd, 1, json.dumps(data), "")
    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    out = tmp_path / "gh"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    mod.main(["--markdown", str(tmp_path / "a.md")])
    md = (tmp_path / "a.md").read_text()
    assert "RUSTSEC-2099-0001" in md and "PYSEC-2099-1" in md and "fixed in 2.0" in md
    n = len(mod.requirement_files(ROOT))
    assert "vulnerabilities=%d" % (1 + n) in out.read_text()


def test_unreadable_output_is_an_error(monkeypatch, tmp_path):
    mod = load()
    monkeypatch.setattr(mod.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(mod.subprocess, "run",
                        lambda cmd, **kw: subprocess.CompletedProcess(cmd, 2, "not json", "network down"))
    mod.main(["--json", str(tmp_path / "a.json")])
    rep = json.loads((tmp_path / "a.json").read_text())
    assert len(rep["errors"]) == 1 + len(mod.requirement_files(ROOT))
    assert all("network down" in e for e in rep["errors"])
