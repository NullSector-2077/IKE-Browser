"""The inventory guard and the component manifest (AUTOMAT, 2026-11-22).

A component added to I.K.E. later must be catalogued and updated by the chain itself. So:

- components.json is the one place an external integrated component is declared, and any entry
  there gets its candidate ``automation/update/<id>`` with no change of code (the generic updater:
  a plain download checked by its sha256, proven here end to end with a fake upstream);
- this guard fails when a file that looks like it comes from upstream has no entry (and says
  exactly which entry to add), or when a record of the inventory has no update path.

Offline. This file is protected: the automatic fix may add the missing entry to components.json,
never change the guard (tools/check-autofix-patch.py FORBIDDEN_FILES).
"""

import hashlib
import importlib.util
import json
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_") + "_guard", ROOT / "tools" / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


inventory = load("inventory")
manifest = load("component-manifest")
candidates = load("update-candidates")
components = load("check-components")
fg = load("fix-guard")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def test_everything_from_upstream_is_declared_and_has_an_update_path():
    """The repository itself: no undeclared file from upstream, every record of the inventory with
    an update path, the manifest valid and its files there."""
    problems = inventory.guard_problems(ROOT, inventory.inventory(ROOT, offline=True))
    assert problems == [], "\n\n".join(problems)
    data = manifest.read(ROOT)
    assert set(data["components"]) >= {"darkreader", "ubo-scriptlets"}
    for cid, entry in data["components"].items():
        for path in entry["files"] + [entry["licence"]]:
            assert (ROOT / path).is_file(), (cid, path)
        assert set(manifest.DEFAULT_TESTS) <= set(entry["tests"]) and "no-regression" in entry["tests"]
    # I.K.E.'s own resources are named one by one, and each is there
    for path in inventory.OWN_RESOURCES:
        assert (ROOT / path).is_file(), path
    listed = {p for p in inventory.tracked_files(ROOT) if p.startswith("ike/resources/")}
    declared = {f for e in data["components"].values() for f in e["files"]}
    for path in sorted(listed):
        assert path in inventory.OWN_RESOURCES or path.startswith(inventory.OWN_RESOURCE_DIRS) or path in declared, path


def test_dark_reader_and_ublock_origin_moved_into_the_manifest_unchanged():
    dark, ubo = candidates.spec("darkreader"), candidates.spec("ubo-scriptlets")
    assert dark["files"] == ("ike/resources/darkreader.js", "ike/resources/darkreader-proxy.js",
                             "ike/resources/darkreader-data.json")
    assert (dark["builder"], dark["kinds"], dark["ships"], dark["wrapper"], dark["serial"]) == (
        "tools/build-darkreader.py", ("npm", "integrated"), True, False, "")
    assert ubo["files"] == ("ike/resources/ubo-scriptlets.json",) and ubo["builder"] == "tools/build-ubo-scriptlets.mjs"
    assert ubo["kinds"] == ("integrated",)
    assert candidates.id_of_branch("automation/update/darkreader") == "darkreader"
    assert candidates.id_of_branch("automation/builder/ubo-scriptlets") == "ubo-scriptlets"
    assert candidates.commit_problem("darkreader", "update: darkreader 1 -> 2 (no AI)",
                                     ["ike/resources/darkreader.js", "CHANGELOG.md"]) == ""
    assert candidates.commit_problem("darkreader", "update: darkreader 1 -> 2 (no AI)", ["ike/app.py"])
    assert "darkreader" not in candidates.SPECS and components.family_of("darkreader") == "darkreader"
    for rec in inventory.inventory(ROOT, offline=True)["components"]:
        if rec["kind"] == "integrated":
            # 1.1.24: KDE's Breeze icons, the third integrated component (its own builder); 1.1.29:
            # Brave's debounce list, a plain download followed on its branch
            assert candidates.candidate_for(rec) in ("darkreader", "ubo-scriptlets", "breeze-icons",
                                                     "brave-debounce"), rec["name"]


@pytest.mark.parametrize("change, word", [
    ({"build": "tools/evil.sh", "download": None}, "one of I.K.E.'s builders"),
    ({"download": [{"url": "http://github.com/a/b/{tag}/x.js", "file": "ike/resources/x.js", "sha256": "0" * 64}]},
     "each download"),
    ({"download": [{"url": "https://evil.example/{tag}/x.js", "file": "ike/resources/x.js", "sha256": "0" * 64}]},
     "each download"),
    ({"files": ["../outside.js"]}, "files must be paths"), ({"files": ["tools/automerge.py"]}, "files must be paths"),
    ({"tests": ["unit-integration"]}, "tests may not leave out"), ({"licence": "LICENSE"}, "licence"),
    ({"upstream": {"git": "https://gitlab.example/a/b"}}, "allowed host"), ({"version": None}, "version in use"),
])
def test_an_entry_of_the_manifest_is_checked(change, word):
    entry = {"name": "X", "upstream": {"git": "https://github.com/a/b", "tag": "v*"}, "files": ["ike/resources/x.js"],
             "version": "1.0.0", "licence": "licenses/LICENSE.x",
             "download": [{"url": "https://raw.githubusercontent.com/a/b/{tag}/x.js", "file": "ike/resources/x.js",
                           "sha256": "0" * 64}]}
    assert manifest.entry_problems("x-lib", entry) == []
    bad = {k: v for k, v in dict(entry, **change).items() if v is not None}
    assert any(word in p for p in manifest.entry_problems("x-lib", bad)), manifest.entry_problems("x-lib", bad)
    for cid in ("ci-x", "security-x", "Upper", "a"):
        assert manifest.entry_problems(cid, entry)
    assert manifest.problems({"schema": 1, "components": {"crates": entry}})        # an id the chain already uses


# --- a new entry gets the whole chain: the generic updater, with a fake upstream ---------------------

OLD_JS, NEW_JS = b"/*! tiny-lib 1.0.0 | MIT */\nexport const v = 1;\n", b"/*! tiny-lib 1.1.0 | MIT */\nexport const v = 2;\n"
URL = "https://raw.githubusercontent.com/example/tiny-lib/%s/dist/tiny.js"


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    (root / "ike" / "resources").mkdir(parents=True)
    (root / "licenses").mkdir()
    for name in ("darkreader.js", "darkreader-proxy.js", "darkreader-data.json", "ubo-scriptlets.json"):
        shutil.copy(ROOT / "ike" / "resources" / name, root / "ike" / "resources" / name)
    shutil.copy(ROOT / "components.json", root / "components.json")
    (root / "ike/resources/tiny.js").write_bytes(OLD_JS)
    (root / "licenses/LICENSE.tiny-lib").write_text("MIT\n")
    return root


def declare(root, version="1.0.0", digest=None):
    data = json.loads((root / "components.json").read_text())
    data["components"]["tiny-lib"] = {
        "name": "tiny-lib (a fake component)", "upstream": {"git": "https://github.com/example/tiny-lib", "tag": "v*"},
        "files": ["ike/resources/tiny.js"], "version": version, "licence": "licenses/LICENSE.tiny-lib",
        "download": [{"url": URL % "{tag}", "file": "ike/resources/tiny.js", "sha256": digest or sha(OLD_JS)}],
        "tests": list(manifest.DEFAULT_TESTS)}
    (root / "components.json").write_text(json.dumps(data, indent=1) + "\n")
    return data


def upstream(files, tags=("v0.9.0", "v1.0.0", "v1.1.0", "v2.0.0-rc1", "other")):
    def get(url, timeout=60):
        if url not in files:
            raise OSError("404 %s" % url)
        return files[url]
    return get, (lambda url, timeout=120: list(tags))


def test_a_new_manifest_entry_produces_its_candidate_end_to_end(repo):
    """Declared in components.json only: found newer upstream, applied (the file and the entry's
    version and checksum), planned as automation/update/<id>, its commit and manifest change
    accepted by the merge's rules. No code names it."""
    declare(repo)
    get, tags = upstream({URL % "v1.0.0": OLD_JS, URL % "v1.1.0": NEW_JS})
    results = components.check_all(repo, only="tiny-lib", get=get, tags=tags)
    assert [(r["id"], r["current"], r["latest"], r["update"], r["error"]) for r in results] == [
        ("tiny-lib", "1.0.0", "1.1.0", True, "")]
    report = {"candidates": components.candidates_of(results)}
    assert report["candidates"][0]["id"] == "tiny-lib" and report["candidates"][0]["to"] == "1.1.0"
    cand = components.apply_candidate(repo, results, "tiny-lib")
    assert cand["to"] == "1.1.0" and (repo / "ike/resources/tiny.js").read_bytes() == NEW_JS
    entry = json.loads((repo / "components.json").read_text())["components"]["tiny-lib"]
    assert entry["version"] == "1.1.0" and entry["download"][0]["sha256"] == sha(NEW_JS)
    # the plan: its own candidate branch; the candidate's rules come from the manifest alone
    spec = manifest.spec("tiny-lib", repo)
    assert spec["files"] == ("ike/resources/tiny.js", "components.json") and spec["ships"] and not spec["wrapper"]
    assert candidates.spec("tiny-lib", repo)["kinds"] == ("integrated",)
    old_specs = dict(candidates.SPECS)
    try:
        candidates.SPECS.update({"tiny-lib": spec})          # (what spec() reads from the repository's own manifest)
        rows = candidates.plan(report, {})
        assert [(r["id"], r["action"], r["branch"]) for r in rows] == [("tiny-lib", "make", "automation/update/tiny-lib")]
        assert rows[0]["message"] == "update: tiny-lib 1.0.0 -> 1.1.0 (no AI)"
        assert candidates.commit_problem("tiny-lib", rows[0]["message"],
                                         ["ike/resources/tiny.js", "components.json", "CHANGELOG.md"]) == ""
        assert candidates.commit_problem("tiny-lib", rows[0]["message"], ["ike/blocker.py"])
    finally:
        candidates.SPECS.clear()
        candidates.SPECS.update(old_specs)
    # the merge's rule for the manifest: only that entry's version and checksums, and the real file's sha256
    before = json.dumps(_with_version(repo, "1.0.0", OLD_JS))
    after = (repo / "components.json").read_text()

    def sha_of(path):
        return sha((repo / path).read_bytes()) if (repo / path).is_file() else ""
    assert manifest.update_problem("tiny-lib", before, after, sha_of) == ""
    assert "not the file" in manifest.update_problem("tiny-lib", before, after, lambda p: "0" * 64)
    moved = json.loads(after)
    moved["components"]["tiny-lib"]["download"][0]["url"] = URL.replace("example", "evil") % "{tag}"
    assert "more than the version" in manifest.update_problem("tiny-lib", before, json.dumps(moved), sha_of)
    other = json.loads(after)
    other["components"]["darkreader"]["build"] = "tools/build-ubo-scriptlets.mjs"
    assert "darkreader changed" in manifest.update_problem("tiny-lib", before, json.dumps(other), sha_of)
    # the inventory: a record with its candidate, so the ledger follows it
    rec = [r for r in inventory.inventory(repo, offline=True)["components"] if r.get("candidate") == "tiny-lib"]
    assert len(rec) == 1 and "automation/update/tiny-lib" in rec[0]["update_mode"]
    assert inventory.update_path(dict(rec[0], candidate="darkreader")) == "candidate automation/update/darkreader"


def _with_version(repo, version, blob):
    data = json.loads((repo / "components.json").read_text())
    data["components"]["tiny-lib"]["version"] = version
    data["components"]["tiny-lib"]["download"][0]["sha256"] = sha(blob)
    return data


def test_an_upstream_that_does_not_reproduce_the_file_makes_no_candidate(repo):
    declare(repo)
    get, tags = upstream({URL % "v1.0.0": b"something else\n", URL % "v1.1.0": NEW_JS})
    results = components.check_all(repo, only="tiny-lib", get=get, tags=tags)
    assert not results[0]["update"] and "does not reproduce" in results[0]["error"]
    assert "source unreachable" not in results[0]["error"]
    with pytest.raises(LookupError):
        components.apply_candidate(repo, results, "tiny-lib")
    assert (repo / "ike/resources/tiny.js").read_bytes() == OLD_JS
    # a source that does not answer is unreachable (tried again tomorrow); nothing newer: nothing made
    get, tags = upstream({})
    assert "source unreachable" in components.check_all(repo, only="tiny-lib", get=get, tags=tags)[0]["error"]
    get, tags = upstream({URL % "v1.0.0": OLD_JS}, tags=("v1.0.0", "v0.9.0"))
    assert components.check_all(repo, only="tiny-lib", get=get, tags=tags)[0]["update"] is False


def test_the_guard_catches_an_undeclared_vendored_file(repo):
    """A file from upstream with no entry fails the guard, and the message is the entry to add."""
    files = ["ike/resources/tiny.js", "ike/resources/darkreader.js", "ike/tabs.py", "ike/vendor/lib/x.py",
             "ike/pagehelper.min.js"]
    (repo / "ike/vendor/lib").mkdir(parents=True)
    (repo / "ike/vendor/lib/x.py").write_text("x = 1\n")
    (repo / "ike/pagehelper.min.js").write_text("var a=1;\n")
    (repo / "ike/tabs.py").write_text("x = 1\n")
    problems = inventory.guard_problems(repo, files=files)
    assert len(problems) == 3
    tiny = [p for p in problems if p.startswith("ike/resources/tiny.js")][0]
    assert "no entry of components.json declares it" in tiny and "Add this entry" in tiny
    assert sha(OLD_JS) in tiny and '"file": "ike/resources/tiny.js"' in tiny and '"tests"' in tiny
    assert any("a folder of vendored code" in p for p in problems) and any("a minified file" in p for p in problems)
    # a licence header or minified code in one of I.K.E.'s folders is caught too
    (repo / "ike/extra.js").write_text("/*! @license MIT (c) 2020 Someone */\nvar x = 1;\n")
    (repo / "ike/long.js").write_text("var a=" + "1+" * 1500 + "1;\n")
    assert len(inventory.undeclared_files(repo, ["ike/extra.js", "ike/long.js"])) == 2
    # declared: the guard passes; a record with no update path fails it
    declare(repo)
    assert inventory.guard_problems(repo, files=["ike/resources/tiny.js", "ike/resources/darkreader.js"]) == []
    bad = {"components": [{"id": "integrated:Mystery", "kind": "integrated", "name": "Mystery",
                           "update_mode": inventory.UNKNOWN},
                          {"id": "integrated:Orphan", "kind": "integrated", "name": "Orphan", "update_mode": "candidate"}]}
    found = inventory.guard_problems(repo, bad, files=[])
    assert len(found) == 2 and all("has no update path" in p for p in found)


def test_the_automatic_fix_may_only_add_the_missing_entry(repo):
    """The manifest is a data file an AI may add an entry to (the static guard, rule 7): a plain
    download of a file that is already there with that sha256, never a build command, never a change
    of another entry."""
    before = (repo / "components.json").read_text()

    def sha_of(path):
        return sha((repo / path).read_bytes()) if (repo / path).is_file() else ""
    declare(repo)
    good = (repo / "components.json").read_text()
    assert manifest.ai_entry_problems(before, good, sha_of) == []
    assert fg.file_problems("components.json", before, good, sha_of=sha_of) == []
    assert fg.file_problems("components.json", before, good)                    # no way to check the files: refused
    cases = {}
    data = json.loads(good)
    data["components"]["tiny-lib"]["download"][0]["sha256"] = "0" * 64
    cases["another file's sha256"] = json.dumps(data)
    data = json.loads(good)
    data["components"]["tiny-lib"].pop("download")
    data["components"]["tiny-lib"].pop("version")
    data["components"]["tiny-lib"]["build"] = "tools/build-darkreader.py"
    cases["a build command"] = json.dumps(data)
    data = json.loads(good)
    data["components"]["darkreader"]["upstream"] = {"npm": "darkreader-evil"}
    cases["another entry changed"] = json.dumps(data)
    data = json.loads(good)
    del data["components"]["ubo-scriptlets"]
    cases["an entry removed"] = json.dumps(data)
    data = json.loads(good)
    data["components"]["tiny-lib"]["download"][0]["url"] = "https://evil.example/{tag}/tiny.js"
    cases["another host"] = json.dumps(data)
    data = json.loads(good)
    data["components"]["tiny-lib"]["licence"] = "licenses/LICENSE.missing"
    cases["no licence file"] = json.dumps(data)
    cases["not JSON"] = "{"
    cases["nothing added"] = before
    for what, text in cases.items():
        assert manifest.ai_entry_problems(before, text, sha_of), what
    guard = load("check-autofix-patch")
    context = load("autofix-context")
    assert guard.MANIFEST == "components.json" and "tests/test_inventory_guard.py" in guard.FORBIDDEN_FILES
    text = (ROOT / "tools/autofix-context.py").read_text()
    assert '"tests/test_inventory_guard.py" in failure' in text and context is not None
