"""AUTOMAT block 2 (2026-11-27): Arch's [testing] checked every day. A package of the closure I.K.E. was tested
with that entered [core-testing] or [extra-testing] in the last day starts "Arch Linux (testing)" on main.
Offline: Arch's databases made here."""

import importlib.util
import io
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NOW = 1_795_700_000


def check():
    spec = importlib.util.spec_from_file_location("testing_cc", ROOT / "tools" / "check-components.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def db(*entries):
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w:gz") as tar:
        for name, version, built in entries:
            text = "%%NAME%%\n%s\n\n%%VERSION%%\n%s\n\n%%BUILDDATE%%\n%d\n" % (name, version, built)
            info = tarfile.TarInfo("%s-%s/desc" % (name, version))
            info.size = len(text.encode())
            tar.addfile(info, io.BytesIO(text.encode()))
    return raw.getvalue()


def test_a_closure_package_new_in_testing_is_news_and_an_old_or_foreign_one_is_not():
    cc = check()
    dbs = {"core-testing": db(("python", "3.15.0-1", NOW - 3600), ("glibc", "2.43-1", NOW - 5 * 86400)),
           "extra-testing": db(("qt6-webengine", "6.141.0-1", NOW - 20 * 3600), ("gimp", "3.4-1", NOW - 60))}

    def get(url, timeout=0):
        return dbs[url.split("/")[3]]
    tested = {"closure": {"python": "3.14.3-1", "glibc": "2.42-1", "qt6-webengine": "6.140.0-1"},
              "packages": {"python-pyqt6": "6.12.1-1"}}
    news, errors = cc.arch_testing_news(tested, get=get, now=NOW)
    assert news == [("python", "3.15.0-1"), ("qt6-webengine", "6.141.0-1")] and errors == {}
    assert cc.parse_repo_db(dbs["core-testing"]) == {"python": "3.15.0-1", "glibc": "2.43-1"}   # unchanged form


def test_an_unreachable_mirror_is_never_news():
    cc = check()

    def get(url, timeout=0):
        raise OSError("down")
    news, errors = cc.arch_testing_news({"closure": {"python": "3"}}, get=get, now=NOW)
    assert news == [] and set(errors) == {"core-testing", "extra-testing"}


def test_the_daily_check_starts_the_testing_run_only_on_news():
    text = (ROOT / ".github" / "workflows" / "daily-check.yml").read_text("utf-8")
    job = text.split("  start-arch-testing:\n", 1)[1].split("\n  # ", 1)[0]
    assert "if: needs.check.outputs.arch_testing == 'new'" in job
    assert "gh workflow run arch-testing.yml --ref main" in job and "actions: write" in job
    assert "arch_testing: ${{ steps.check.outputs.arch_testing }}" in text
