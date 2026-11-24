"""Lessons of AUTOMAT's own small jams, kept as checks so they never come back.

Each check is a mistake that once stopped a pull request on GitHub for a
reason that had nothing to do with the change it carried (2026-11-24, the
owner: "fai in modo che automat impari anche da questi errori semplici e
banali"). A new test, written by Claude or proposed by an AI, fails here
before it can fail on GitHub.
"""

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"
ME = Path(__file__).name


def _test_sources():
    return sorted(p for p in TESTS.glob("*.py") if p.name != ME)


# ---------------------------------------------------------------------------
# 1. Tests import I.K.E. from the copy under test (conftest.APP), never from
#    the checkout. In the installed package's shards (IKE_TEST_APP) a test that
#    put the checkout first on sys.path imported the sources, tested them
#    instead of the package, and left them imported for the next test of the
#    same process: tools/check-components.py then found "another copy of
#    I.K.E." (PR #155, test_credits then test_lists_providers).
# ---------------------------------------------------------------------------

CHECKOUT_ON_PATH = re.compile(r"sys\.path\.(?:insert|append)\([^)]*\bstr\(ROOT\)")


def test_no_test_puts_the_checkout_on_the_import_path():
    found = []
    for p in _test_sources():
        for n, line in enumerate(p.read_text("utf-8").splitlines(), 1):
            if CHECKOUT_ON_PATH.search(line):
                found.append("%s:%d: %s" % (p.name, n, line.strip()))
    assert not found, ("import I.K.E. from conftest.APP (the installed copy in its shards, the checkout "
                       "otherwise), not from ROOT:\n" + "\n".join(found))


def test_the_guard_sees_the_mistake_it_guards():
    assert CHECKOUT_ON_PATH.search("    sys.path.insert(0, str(ROOT))")
    assert CHECKOUT_ON_PATH.search("sys.path.append(str(ROOT))")
    assert not CHECKOUT_ON_PATH.search("sys.path.insert(0, str(APP))")


# ---------------------------------------------------------------------------
# 2. Tests import only what the test environment installs. Three new tests
#    imported yaml, which tools/test-requirements.txt does not list: on GitHub
#    they stopped with ModuleNotFoundError before checking anything (PR #155).
#    A module that is not in the standard library, the repository or the
#    requirements needs a reason here.
# ---------------------------------------------------------------------------

# requirement name (as pip writes it) -> the module it gives
PROVIDES = {"pyqt6": "PyQt6", "pyqt6_webengine": "PyQt6", "pyqt6_sip": "PyQt6"}
INTERNAL = {"_pytest": "pytest"}          # a package's own internal module -> the package

# the repository's own modules that tests import
OWN = {"ike", "ike_adblock", "adblock", "conftest"}

# imports allowed although the test environment does not install them, each
# with the file it is in and why
ALLOWED = {
    ("PIL", "measure_smooth.py"): "a measuring tool run by hand, never collected by pytest",
}


def _requirements():
    names = set()
    for line in (ROOT / "tools" / "test-requirements.txt").read_text("utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if "==" in line:
            name = line.split("==", 1)[0].strip().lower().replace("-", "_")
            names.add(PROVIDES.get(name, name))
    return names


def _imports(path):
    tree = ast.parse(path.read_text("utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.module.split(".")[0]


def test_tests_import_only_what_the_test_environment_installs():
    installed = _requirements()
    local = {p.stem for p in TESTS.glob("*.py")}
    missing = []
    for p in _test_sources():
        for top in sorted(set(_imports(p))):
            if (top in sys.stdlib_module_names or top in OWN or top in local
                    or top.lower() in installed or top in installed or INTERNAL.get(top) in installed
                    or (top, p.name) in ALLOWED):
                continue
            missing.append("%s imports %s" % (p.name, top))
    assert not missing, ("not installed by tools/test-requirements.txt (read the file as text, or add the "
                         "package to the requirements, or give a reason in ALLOWED):\n" + "\n".join(missing))


def test_every_allowed_exception_is_still_needed():
    for (module, name), reason in ALLOWED.items():
        assert reason
        p = TESTS / name
        assert p.is_file() and module in set(_imports(p)), "%s no longer imports %s: remove it" % (name, module)
