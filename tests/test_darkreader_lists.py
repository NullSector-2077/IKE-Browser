"""The builder of the copy of Dark Reader's lists I.K.E. comes with
(tools/build-darkreader-lists.py, 1.1.29: Dark Reader's engine left I.K.E., its
lists stay).

- It writes only ike/resources/darkreader-data.json, in the shape the browser
  reads (version, lists_commit, lists_date, fixes, dark_sites, detector_hints;
  compact JSON), the version from the checkout's package.json.
- It reads and checks the lists with the browser's own functions
  (ike/darklists.py): the common fix first, nothing that looks like a script,
  no list much shorter than the copy in use. A refusal STOPS the build and
  writes nothing.
- IKE_TEST_NETWORK=1: the bundled copy is rebuilt from the commit it records,
  byte for byte.

SIMULATION: a stand-in checkout of Dark Reader's repository (no network).
"""

import importlib.util
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "tools" / "build-darkreader-lists.py"
BUNDLED = ROOT / "ike" / "resources" / "darkreader-data.json"

FIXES = """*

INVERT
.logo

CSS
body { color: red }

================================

example.test

IGNORE INLINE STYLE
.x
"""
HINTS = "own.example\n\nTARGET\nhtml\n\nMATCH\n.dark\n\nNO DARK THEME\n"


def load():
    spec = importlib.util.spec_from_file_location("build_darkreader_lists", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def checkout(tmp_path, fixes=FIXES, version="4.9.200", package=True):
    src = tmp_path / "darkreader"
    cfg = src / "src" / "config"
    cfg.mkdir(parents=True)
    if package:
        (src / "package.json").write_text(json.dumps({"name": "darkreader", "version": version}))
    (cfg / "dynamic-theme-fixes.config").write_text(fixes)
    (cfg / "dark-sites.config").write_text("dark.example\n*.night.example\n")
    (cfg / "detector-hints.config").write_text(HINTS)
    return src


def run(tmp_path, src, *extra):
    out = tmp_path / "out"
    out.mkdir(exist_ok=True)
    done = subprocess.run(["python3", str(TOOL), "--src", str(src), "--commit", "c" * 40, "--date", "2026-11-27",
                           "--out", str(out), "--bundled", "", *extra], capture_output=True, text=True, check=False)
    return done, out


def test_the_lists_are_written_as_the_browser_reads_them(tmp_path):
    done, out = run(tmp_path, checkout(tmp_path))
    assert done.returncode == 0, done.stderr
    assert sorted(p.name for p in out.iterdir()) == ["darkreader-data.json"]
    text = (out / "darkreader-data.json").read_text("utf-8")
    data = json.loads(text)
    assert list(data) == ["version", "lists_commit", "lists_date", "fixes", "dark_sites", "detector_hints"]
    assert (data["version"], data["lists_commit"], data["lists_date"]) == ("4.9.200", "c" * 40, "2026-11-27")
    assert data["fixes"] == [{"url": ["*"], "invert": [".logo"], "css": "body { color: red }"},
                             {"url": ["example.test"], "ignoreInlineStyle": [".x"]}]
    assert data["dark_sites"] == ["dark.example", "*.night.example"]
    assert data["detector_hints"] == [{"url": ["own.example"], "target": "html", "match": [".dark"],
                                       "noDarkTheme": True}]
    assert text == json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n"
    assert "Dark Reader 4.9.200 lists: 2 site fixes, 2 dark sites, 1 detector hints" in done.stdout


def test_the_builder_uses_the_browsers_reader():
    """The builder reads the lists with the checkout's own ike/darklists.py (the copy it builds for), never a
    reader of its own; in the installed package's shards the imported I.K.E. is the installed copy, so the
    checkout's file is compared, not the imported module (tests/test_lessons.py, lesson 1)."""
    tool = load()
    assert Path(tool.darklists().__file__).resolve() == (ROOT / "ike" / "darklists.py").resolve()
    assert "PyQt6" not in TOOL.read_text("utf-8") and "PATCHES" not in TOOL.read_text("utf-8")


@pytest.mark.parametrize("fixes, why", [
    (FIXES.replace("body { color: red }", "body { background: url(javascript:alert(1)) }"), "could be a script"),
    (FIXES.replace("body { color: red }", "</style><script>alert(1)</script>"), "could be a script"),
    (FIXES.replace("IGNORE INLINE STYLE\n.x", "INVERT\nimg[onerror=alert(1)]"), "could be a script"),
    ("example.test\n\nCSS\nbody { color: red }\n", "common fix"),
])
def test_anything_like_a_script_stops_the_build_and_writes_nothing(tmp_path, fixes, why):
    done, out = run(tmp_path, checkout(tmp_path, fixes))
    assert done.returncode != 0 and why in done.stderr, done.stderr
    assert list(out.iterdir()) == []


def test_a_list_much_shorter_than_the_copy_in_use_stops_the_build(tmp_path):
    done, out = run(tmp_path, checkout(tmp_path), "--bundled", str(BUNDLED))
    assert done.returncode != 0 and "entries where I.K.E. came with" in done.stderr, done.stderr
    assert list(out.iterdir()) == []


@pytest.mark.parametrize("package, version", [(False, ""), (True, "not a version"), (True, "")])
def test_no_version_in_the_checkout_stops_the_build(tmp_path, package, version):
    done, out = run(tmp_path, checkout(tmp_path, version=version, package=package))
    assert done.returncode != 0 and "package.json" in done.stderr, done.stderr
    assert list(out.iterdir()) == []


def test_the_bundled_copy_is_one_the_browser_accepts():
    from ike import darklists
    data = json.loads(BUNDLED.read_text("utf-8"))
    assert list(data) == ["version", "lists_commit", "lists_date", "fixes", "dark_sites", "detector_hints"]
    assert darklists.check(data, data) == ""
    # the engine left in 1.1.29; darkmode.js (unused) stays until it leaves tools/fix-guard.py PROTECTED_JS, a
    # change of the guard's own list made by a person
    assert [p.name for p in sorted(BUNDLED.parent.glob("dark*.js"))] == ["darkmode.js"]


@pytest.mark.skipif(not os.environ.get("IKE_TEST_NETWORK") or not shutil.which("git"),
                    reason="IKE_TEST_NETWORK=1 to rebuild the bundled copy from Dark Reader's repository")
def test_the_bundled_copy_is_rebuilt_byte_for_byte(tmp_path):
    data = json.loads(BUNDLED.read_text("utf-8"))
    src = tmp_path / "src"
    subprocess.run(["git", "clone", "-q", "--filter=blob:none", "--no-checkout",
                    "https://github.com/darkreader/darkreader", str(src)], check=True, timeout=300)
    subprocess.run(["git", "-C", str(src), "checkout", "-q", data["lists_commit"]], check=True, timeout=300)
    out = tmp_path / "out"
    out.mkdir()
    subprocess.run(["python3", str(TOOL), "--src", str(src), "--commit", data["lists_commit"], "--date",
                    data["lists_date"], "--out", str(out)], check=True)
    assert (out / "darkreader-data.json").read_bytes() == BUNDLED.read_bytes()
