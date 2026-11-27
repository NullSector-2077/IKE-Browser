"""AUTOMAT block 2 (2026-11-27): the Chromium features I.K.E. sets still exist (tools/engine-features.py).
Chromium ignores an unknown feature name silently, so a renamed protection would turn off with no error.
Offline: GitHub's code search and Chromium's source stood in."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DECL = 'BASE_FEATURE(kStaticStorageQuota,\n             "StaticStorageQuota",\n             base::FEATURE_ENABLED_BY_DEFAULT);'


def tool():
    spec = importlib.util.spec_from_file_location("engine_features", ROOT / "tools" / "engine-features.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_names_are_read_from_the_browser_itself():
    names = tool().feature_names((ROOT / "ike" / "app.py").read_text("utf-8"))
    assert "LocalNetworkAccessChecks" in names and "StaticStorageQuota" in names
    assert "AcceleratedVideoDecodeLinux" in names
    assert all(":" not in n and "/" not in n for n in names)


def test_present_gone_now_going_away_and_not_verified():
    t = tool()
    files = {"Present": "quota.cc", "GoneNow": "gone.cc"}

    def search(query):
        name = query.split('"')[1]
        if name == "Unreadable":
            raise RuntimeError("rate limit")
        return [files[name]] if name in files else []

    def source(version, path):
        assert version == "140.0.7339.264"
        return DECL.replace("StaticStorageQuota", "Present") if path == "quota.cc" else "// nothing here"
    rows = {r["name"]: r for r in t.check(["Present", "GoneNow", "GoingAway", "Unreadable"], "140.0.7339.264",
                                          search, source, pause=lambda: None)}
    assert (rows["Present"]["main"], rows["Present"]["now"]) == ("present", "present")
    assert (rows["GoneNow"]["main"], rows["GoneNow"]["now"]) == ("present", "absent")
    assert (rows["GoingAway"]["main"], rows["GoingAway"]["now"]) == ("absent", "not verified")
    assert (rows["Unreadable"]["main"], rows["Unreadable"]["now"]) == ("not verified", "not verified")
    lines = t.problems(list(rows.values()), "140.0.7339.264")
    assert len(lines) == 2 and "GoneNow" in lines[0] and "GoingAway" in lines[1]


def test_a_source_that_cannot_be_read_is_never_present():
    t = tool()

    def source(version, path):
        raise RuntimeError("blocked")
    rows = t.check(["X"], "140.0.7339.264", lambda q: ["x.cc"], source, pause=lambda: None)
    assert rows[0]["now"] == "not verified" and t.problems(rows, "140") == []


def test_the_declaration_is_recognised():
    t = tool()
    assert t.declares(DECL, "StaticStorageQuota") and not t.declares(DECL, "StaticStorage")
    assert not t.declares('// "StaticStorageQuota" was removed', "StaticStorageQuota")


def test_the_weekly_check_runs_it_and_the_issue_reads_it():
    text = (ROOT / ".github" / "workflows" / "health.yml").read_text("utf-8")
    assert "tools/engine-features.py --chromium" in text and "ENGINE_FEATURES:" in text
    assert "ENGINE_FEATURES" in (ROOT / "tools" / "automation-health.py").read_text("utf-8")


def test_a_header_read_first_never_makes_a_feature_absent():
    t = tool()

    def source(version, path):
        return "BASE_DECLARE_FEATURE(kPresent);" if path.endswith(".h") else DECL.replace("StaticStorageQuota", "Present")
    rows = t.check(["Present"], "140.0.7339.264", lambda q: ["a/features.h", "a/features.cc"], source,
                   pause=lambda: None)
    assert rows[0]["now"] == "present" and rows[0]["file"] == "a/features.cc"
