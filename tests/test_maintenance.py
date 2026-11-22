"""The automatic maintenance's inventory, ledger, test categories and candidate
report (tools/inventory.py, tools/maintenance-ledger.py, tools/test-categories.py,
tools/maintenance-report.py), and the plan's git failures as infrastructure.

The proofs of WP14 run on fixture repositories in a temporary folder with
stand-ins for every upstream answer (Arch's site, crates.io, PyPI, npm,
GitHub's tags): no network.

(a) a dependency added to the repository (an import in ike/, a PKGBUILD
    depend, a crate, a `uses:`) is found with no change of the tools, and the
    ledger records it;
(b) an existing dependency updated upstream (Arch, a crate, an Action) is
    detected, recorded once, and follows the candidate flow.
"""

import datetime as dt
import importlib.util
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), ROOT / "tools" / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


inv_tool = load("inventory")
ledger_tool = load("maintenance-ledger")
tc = load("test-categories")
report_tool = load("maintenance-report")
plan_tool = load("autofix-plan")
guard = load("check-autofix-patch")

DAY1 = dt.datetime(2026, 11, 20, 5, 30, tzinfo=dt.timezone.utc)
DAY2 = DAY1 + dt.timedelta(days=1)
DAY3 = DAY2 + dt.timedelta(days=1)
CHECKOUT_SHA = "3d3c42e5aac5ba805825da76410c181273ba90b1"
NEW_CHECKOUT_SHA = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
CACHE_SHA = "55cc8345863c7cc4c66a329aec7e433d2d1c52a9"

PKGBUILD = """\
pkgname=ike-browser
pkgver=1.0.0
depends=('python' 'python-pyqt6' 'python-pyqt6-webengine' 'qt6-webengine' 'python-jeepney')
makedepends=('rust' 'gcc')
optdepends=('libnotify: desktop notifications'
            'xdg-utils: set the default browser (Settings, experimental)')

build() {
  cd "$startdir"
  RUSTFLAGS="${RUSTFLAGS:-} -C target-cpu=x86-64" \\
  cargo build --release --locked --manifest-path ike-adblock/Cargo.toml
  gcc $CFLAGS -o "$srcdir/launcher" launcher/ike-browser.c
}
"""
APP = """\
import subprocess

from PyQt6.QtWebEngineCore import QWebEngineProfile
from PyQt6.QtWidgets import QApplication

try:
    import jeepney
except ImportError:
    jeepney = None


def notify(text):
    subprocess.Popen(["notify-send", "--", text])
"""
CONFIG = """\
DEFAULT_LISTS = [
    {"name": "EasyList", "group": "ads", "enabled": True, "url": "https://easylist.to/easylist/easylist.txt"},
]
"""
CARGO_TOML = """\
[package]
name = "ike-adblock"
version = "1.0.0"

[dependencies]
adblock = { version = "=0.13.6", default-features = false }
serde_json = "1"
"""


def lock(*crates):
    out = ["version = 4", "", "[[package]]", 'name = "ike-adblock"', 'version = "1.0.0"',
           "dependencies = [", ' "adblock",', ' "serde_json",', "]"]
    for name, version in crates:
        out += ["", "[[package]]", 'name = "%s"' % name, 'version = "%s"' % version,
                'source = "registry+https://github.com/rust-lang/crates.io-index"']
    return "\n".join(out) + "\n"


WORKFLOW = """\
name: Tests
on: [push]
jobs:
  tests:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@%s # v7.0.1
      - uses: actions/setup-python@6d4fd22b20465ccc0f7354476588e8df7c9ca0e0 # v7.1.0
        with:
          python-version: "3.13"
      - run: |
          python -m pip install --disable-pip-version-check -q -r tools/test-requirements.txt
          cargo install --locked cargo-deny@0.20.2
          rustup toolchain install stable --profile minimal
""" % CHECKOUT_SHA


def write(root, rel, text):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, "utf-8")


@pytest.fixture
def fixture_repo(tmp_path):
    """A small repository laid out as I.K.E.'s, with one component of each kind."""
    root = tmp_path / "repo"
    write(root, "PKGBUILD", PKGBUILD)
    write(root, "ike/__init__.py", '__version__ = "1.0.0"\n')
    write(root, "ike/app.py", APP)
    write(root, "ike/config.py", CONFIG)
    write(root, "ike_boot.py", "import sys\n\nimport ike.app\n")
    write(root, "vendor/adblock/__init__.py", "")
    write(root, "ike/blocker.py", "import adblock\n")
    write(root, "ike-adblock/Cargo.toml", CARGO_TOML)
    write(root, "ike-adblock/Cargo.lock", lock(("adblock", "0.13.6"), ("serde_json", "1.0.1"), ("itoa", "1.0.0")))
    write(root, "tools/test-requirements.txt", "# pins\npytest==9.0.0\nruff==0.17.6\n")
    write(root, "tools/build-x.mjs", "import { writeFileSync } from 'node:fs';\n")
    write(root, "tools/check-components.py", 'ARCH_PACKAGES = ("python", "qt6-base", "breeze")\n')
    write(root, ".github/workflows/tests.yml", WORKFLOW)
    write(root, "ike/resources/darkreader-data.json",
          json.dumps({"version": "4.9.135", "lists_commit": "30e8a10e65381959", "lists_date": "2026-11-16"}))
    write(root, "ike/resources/ubo-scriptlets.json",
          json.dumps({"source": "https://github.com/gorhill/uBlock", "commit": "2bc679d99afe5bdd", "date": "2026-11-10",
                      "scriptlets": {}}))
    return root


# --- stand-ins for the upstream answers -----------------------------------------------------

ARCH = {"python": "3.14.10-1", "python-pyqt6": "6.12.1-1", "python-pyqt6-webengine": "6.140.1-1",
        "qt6-webengine": "6.140.0-1", "python-jeepney": "0.9.0-3", "rust": "1:1.100.0-1", "gcc": "16.1.1-1",
        "libnotify": "0.8.8-1", "xdg-utils": "1.2.1-2", "qt6-base": "6.12.0-5", "breeze": "6.5.3-1",
        "python-yaml": "6.0.3-1", "python-requests": "2.33.0-1", "pacman": "7.1.0-1"}
CRATES = {"adblock": ["0.13.6"], "serde_json": ["1.0.1"], "itoa": ["1.0.0"], "cargo-deny": ["0.20.2"],
          "base64": ["0.22.1"]}
PYPI = {"pytest": "9.0.0", "ruff": "0.17.6"}
TAGS = {"actions/checkout": {"v7.0.1": CHECKOUT_SHA}, "actions/setup-python": {
    "v7.1.0": "6d4fd22b20465ccc0f7354476588e8df7c9ca0e0"}, "actions/cache": {"v6.1.0": CACHE_SHA}}


class Upstream:
    """Every source the inventory asks, answered from the dicts above (a copy each)."""

    def __init__(self, arch=None, crates=None, pypi=None, tags=None, down=()):
        self.arch = dict(ARCH, **(arch or {}))
        self.crates = {k: list(v) for k, v in dict(CRATES, **(crates or {})).items()}
        self.pypi = dict(PYPI, **(pypi or {}))
        self.tags = {k: dict(v) for k, v in TAGS.items()}
        for k, v in (tags or {}).items():
            self.tags.setdefault(k, {}).update(v)
        self.down = set(down)
        self.asked = []

    def get(self, url):
        self.asked.append(url)
        host = re.match(r"https://([^/]+)/", url).group(1)
        if host in self.down:
            raise OSError("network unreachable")
        if host == "archlinux.org":
            name = url.rsplit("=", 1)[1]
            res = []
            if name in self.arch:
                epoch, _, rest = self.arch[name].rpartition(":")
                ver, rel = rest.rsplit("-", 1)
                res.append({"pkgname": name, "repo": "extra", "pkgver": ver, "pkgrel": rel, "epoch": int(epoch or 0)})
            return json.dumps({"results": res}).encode()
        if host == "index.crates.io":
            name = url.rsplit("/", 1)[1]
            if name not in self.crates:
                raise OSError("HTTP Error 404")
            return "\n".join(json.dumps({"name": name, "vers": v, "yanked": False})
                             for v in self.crates[name]).encode()
        if host == "pypi.org":
            name = url.split("/pypi/", 1)[1].split("/")[0]
            return json.dumps({"info": {"version": self.pypi.get(name, "0")}}).encode()
        if host == "registry.npmjs.org":
            return json.dumps({"version": "4.9.135"}).encode()
        raise OSError("not a stand-in: %s" % url)

    def ls_remote(self, url, *refs):
        self.asked.append(url)
        if "github.com" in self.down:
            raise OSError("network unreachable")
        repo = url.split("github.com/", 1)[1]
        if refs == ("HEAD",):
            return "2bc679d99afe5bdd\tHEAD\n"
        return "".join("%s\trefs/tags/%s\n" % (sha, tag) for tag, sha in self.tags.get(repo, {}).items())

    def net(self):
        return inv_tool.Net(get=self.get, ls_remote=self.ls_remote)


def take(root, upstream=None, **kw):
    return inv_tool.inventory(root, net=(upstream or Upstream()).net(), **kw)


def ids(inv):
    return {r["id"]: r for r in inv["components"]}


# --- WP2: the inventory ----------------------------------------------------------------------

FIELDS = ("name", "kind", "type", "origin", "distribution", "installed", "available", "update_mode",
          "tests_needed", "compatibility", "vulnerabilities", "last_check", "result")


def test_the_inventory_finds_every_kind_in_the_repository(fixture_repo):
    inv = take(fixture_repo, Upstream(crates={"adblock": ["0.13.6", "0.13.7"]}))
    found = ids(inv)
    expected = {
        "arch-package:python", "arch-package:qt6-webengine", "arch-package:breeze",       # depends, ARCH_PACKAGES
        "arch-build:rust", "arch-build:gcc", "arch-optional:libnotify", "arch-optional:xdg-utils",
        "build-tool:cargo", "build-tool:gcc", "build-tool:makepkg",
        "python-module:PyQt6", "python-module:jeepney", "pyqt-module:PyQt6.QtWidgets",
        "pyqt-module:PyQt6.QtWebEngineCore", "vendored:adblock", "runtime-tool:notify-send",
        "adblock-engine:adblock", "crate:serde_json", "crate:itoa", "node:Node.js",
        "pypi-test:pytest", "pypi-test:ruff", "ci-tool:cargo-deny", "ci-runtime:Rust toolchain (CI)",
        "ci-runtime:Python 3.13 (CI)", "ci-runtime:ubuntu-24.04", "github-action:actions/checkout",
        "github-action:actions/setup-python", "integrated:Dark Reader", "integrated:uBlock Origin scriptlets",
        "filter-list:EasyList"}
    assert expected <= set(found), sorted(expected - set(found))
    for rec in inv["components"]:
        for field in FIELDS:
            assert field in rec, (rec["id"], field)
        assert rec["tests_needed"], rec["id"]
    assert inv["findings"] == []
    # the details read from the repository
    assert found["arch-optional:xdg-utils"]["notes"] == ["set the default browser (Settings, experimental)"]
    assert found["python-module:jeepney"]["type"] == "optional"              # imported in try/except ImportError
    assert found["crate:itoa"]["type"] == "transitive" and found["crate:serde_json"]["type"] == "direct"
    assert found["crate:serde_json"]["requirement"] == "1"
    assert found["github-action:actions/checkout"]["pin"] == CHECKOUT_SHA
    assert found["build-tool:cargo"]["provided_by"] == "rust"
    assert found["runtime-tool:notify-send"]["origin"] == ["ike/app.py:13"]
    assert found["pyqt-module:PyQt6.QtWebEngineCore"]["provided_by"] == ["python-pyqt6-webengine", "qt6-webengine"]
    # available versions from each source; the same versions: nothing to do
    assert found["adblock-engine:adblock"]["available"] == "0.13.7"
    assert found["adblock-engine:adblock"]["compatibility"].startswith("pinned exactly")
    assert found["crate:serde_json"]["result"] == "ok" and found["pypi-test:pytest"]["result"] == "ok"
    assert found["github-action:actions/checkout"]["result"] == "ok"
    assert found["arch-package:qt6-webengine"]["available"] == "6.140.0-1"
    assert found["integrated:uBlock Origin scriptlets"]["result"] == "ok"
    # vulnerabilities only from a check that ran, never guessed
    assert {r["vulnerabilities"] for r in inv["components"]} == {"not checked"}


def test_unknown_or_unreachable_is_never_guessed(fixture_repo):
    up = Upstream(down={"index.crates.io", "pypi.org"})
    found = ids(take(fixture_repo, up))
    serde = found["crate:serde_json"]
    assert serde["available"].startswith("unknown (source unreachable") and serde["result"] == "unreachable"
    assert found["pypi-test:pytest"]["result"] == "unreachable"
    # a host that does not answer is asked at most NETWORK_FAILURES times
    assert sum("index.crates.io" in u for u in up.asked) <= inv_tool.NETWORK_FAILURES + inv_tool.WORKERS
    # offline: nothing read, everything "not checked"
    off = inv_tool.inventory(fixture_repo, offline=True)
    assert {r["available"] for r in off["components"]} == {"not checked"}
    assert all(r["result"] in ("not checked",) for r in off["components"]
               if r["kind"] not in ("integrated",)), [r for r in off["components"] if r["result"] != "not checked"]


def test_advisories_come_only_from_cargo_deny(fixture_repo):
    found = ids(take(fixture_repo, advisories={"state": "clean", "url": "https://x/runs/1"}))
    assert found["crate:serde_json"]["vulnerabilities"] == "none known (RustSec via cargo-deny, https://x/runs/1)"
    assert found["pypi-test:pytest"]["vulnerabilities"] == "not checked"
    bad = ids(take(fixture_repo, advisories={"state": "found", "url": "u", "crates": ["itoa"]}))
    assert bad["crate:itoa"]["result"] == "vulnerable"
    assert bad["crate:serde_json"]["vulnerabilities"].startswith("none named for this crate")


def test_the_real_repository_is_covered():
    """Offline, on this repository: every PKGBUILD dependency, every default
    filter list and every crate is there, and no module, program or build
    command is used without a declared package."""
    inv = inv_tool.inventory(ROOT, offline=True)
    found = ids(inv)
    assert inv["findings"] == [], inv["findings"]
    pkg = inv_tool.parse_pkgbuild((ROOT / "PKGBUILD").read_text())
    for name in pkg["depends"]:
        assert "arch-package:" + name in found, name
    for name, _ in pkg["optdepends"]:
        assert "arch-optional:" + name in found, name
    assert len(pkg["optdepends"]) == 8 and "rust" in pkg["makedepends"]
    lists = inv_tool.default_lists(ROOT)
    assert lists and all("filter-list:" + e["name"] in found for e in lists)
    crates = inv_tool.parse_cargo_lock((ROOT / "ike-adblock/Cargo.lock").read_text())
    assert sum(r["kind"] in ("crate", "adblock-engine") for r in inv["components"]) == len(crates) - 1
    for kind in ("python-module", "pyqt-module", "runtime-tool", "github-action", "pypi-test", "integrated",
                 "build-tool", "node", "ci-tool"):
        assert inv["counts"].get(kind), kind
    for name in ("PyQt6.QtWebEngineCore", "PyQt6.QtSvg", "PyQt6.QtWebChannel"):
        assert "pyqt-module:" + name in found
    for tool in ("notify-send", "xdg-settings", "xdg-open"):
        assert "runtime-tool:" + tool in found
    assert inv_tool.to_markdown(inv).startswith("### Inventory of the external components")


# --- WP14 (a): a new dependency, found with no change of the tools, and recorded -------------

def test_a_new_dependency_is_found_and_recorded(fixture_repo):
    day1 = take(fixture_repo)
    ledger = ledger_tool.update(None, day1, now=DAY1)
    assert ledger["entries"] == {} and "crate:serde_json" in ledger["known"]       # the first run only learns
    # someone adds dependencies: an import, a PKGBUILD depend, a crate, an action, a program
    write(fixture_repo, "ike/feeds.py", "import requests\nimport yaml\nimport subprocess\n\n\n"
                                        "def edit():\n    subprocess.run(['kwrite', 'x'])\n")
    text = (fixture_repo / "PKGBUILD").read_text().replace("'python-jeepney')", "'python-jeepney' 'python-requests')")
    write(fixture_repo, "PKGBUILD", text)
    write(fixture_repo, "ike-adblock/Cargo.lock", lock(("adblock", "0.13.6"), ("serde_json", "1.0.1"),
                                                       ("itoa", "1.0.0"), ("base64", "0.22.1")))
    write(fixture_repo, ".github/workflows/cache.yml", "jobs:\n  a:\n    steps:\n"
                                                       "      - uses: actions/cache@%s # v6.1.0\n" % CACHE_SHA)
    day2 = take(fixture_repo)
    found = ids(day2)
    for rid in ("python-module:requests", "python-module:yaml", "arch-package:python-requests", "crate:base64",
                "github-action:actions/cache", "runtime-tool:kwrite"):
        assert rid in found, rid
    findings = {(f["finding"], f["component"]) for f in day2["findings"]}
    assert ("used but not declared", "python-module:yaml") in findings          # python-yaml is not declared
    assert ("unknown provider", "runtime-tool:kwrite") in findings
    assert not any(c == "python-module:requests" for _, c in findings)          # its depend was added
    ledger = ledger_tool.update(ledger, day2, now=DAY2)
    new = {e["component"]: e for e in ledger["entries"].values()}
    assert {"python-module:yaml", "crate:base64", "github-action:actions/cache", "arch-package:python-requests",
            "python-module:requests"} <= set(new)
    assert new["python-module:yaml"]["state"] == "needs-person" and "python-yaml" in new["python-module:yaml"]["reason"]
    assert new["crate:base64"]["state"] == "detected" and new["crate:base64"]["from"] == "(new)"
    assert new["crate:base64"]["to"] == "0.22.1"
    # the same facts again: nothing added twice, nothing moved
    before = json.dumps(ledger["entries"], sort_keys=True)
    ledger = ledger_tool.update(ledger, day2, now=DAY2 + dt.timedelta(hours=1))
    assert json.dumps(ledger["entries"], sort_keys=True) == before
    # main's tests green after it was found: passed; the undeclared import waits for a person
    status = {"main_tests": {"conclusion": "success", "created_at": "2026-11-21T09:00:00Z", "sha": "abc",
                             "url": "https://x/runs/9"}}
    ledger = ledger_tool.update(ledger, day2, status, now=DAY3)
    new = {e["component"]: e for e in ledger["entries"].values()}
    assert new["crate:base64"]["state"] == "passed" and new["crate:base64"]["last_run"] == "https://x/runs/9"
    assert new["python-module:yaml"]["state"] == "needs-person"
    # the depend is added: the finding is gone, the import waits for main's tests
    write(fixture_repo, "PKGBUILD", (fixture_repo / "PKGBUILD").read_text().replace(
        "'python-requests')", "'python-requests' 'python-yaml')"))
    ledger = ledger_tool.update(ledger, take(fixture_repo), now=DAY3 + dt.timedelta(hours=1))
    assert {e["component"]: e for e in ledger["entries"].values()}["python-module:yaml"]["state"] == "detected"


# --- WP14 (b): an existing dependency updated upstream, detected and in the candidate flow --------

ARCH_TESTED = {"tested": {"packages": {"python": "3.14.10-1", "qt6-webengine": "6.140.0-1", "breeze": ""}}}
ALL_GREEN = {"status": "completed", "conclusion": "success", "url": "https://x/runs/7", "jobs": {"tests": {
    "status": "completed", "conclusion": "success",
    "steps": {s[2]: "success" for _, (_d, s) in tc.CATEGORIES.items() if s[0] == "tests.yml"}}}}
SECURITY_GREEN = {"status": "completed", "conclusion": "success", "jobs": {
    "sandbox": {"status": "completed", "conclusion": "success", "steps": {}},
    "rust-advisories": {"status": "completed", "conclusion": "success", "steps": {}}}}


def candidate(runs, skips=(), **kw):
    cand = {"sha": "c0ffee", "pr": 43, "url": "https://x/pull/43", "runs": runs, "skips": list(skips),
            "autofix_commits": 0, "autofix_issue": ""}
    cand.update(kw)
    return {"main_sha": "main1", "candidate": cand}


def test_an_update_is_detected_and_follows_the_candidate_flow(fixture_repo, tmp_path):
    up = Upstream(arch={"qt6-webengine": "6.141.0-1"}, crates={"serde_json": ["1.0.1", "1.0.2"]},
                  tags={"actions/checkout": {"v7.1.0": NEW_CHECKOUT_SHA}})
    inv = take(fixture_repo, up, arch_tested=ARCH_TESTED)
    found = ids(inv)
    assert found["arch-package:qt6-webengine"]["result"] == "changed since last tested"
    assert found["crate:serde_json"]["result"] == "update available"
    assert found["crate:serde_json"]["compatibility"] == "semver-compatible update (cargo update)"
    assert found["github-action:actions/checkout"]["result"] == "update available"
    assert found["github-action:actions/checkout"]["available_sha"] == NEW_CHECKOUT_SHA
    # a package arch.yml did not install is "not verified", never a change
    assert found["arch-package:breeze"]["result"] == "ok"
    assert inv_tool.updates_of(inv) and "serde_json" in inv_tool.to_markdown(inv)

    seed = ledger_tool.update(None, take(fixture_repo, arch_tested=ARCH_TESTED), now=DAY1 - dt.timedelta(days=1))
    ledger = ledger_tool.update(seed, inv, now=DAY1)
    e = {x["component"]: x for x in ledger["entries"].values()}
    assert e["crate:serde_json"]["state"] == "detected" and e["crate:serde_json"]["key"] == "crate:serde_json@1.0.2"
    assert (e["crate:serde_json"]["from"], e["crate:serde_json"]["to"]) == ("1.0.1", "1.0.2")
    assert e["arch-package:qt6-webengine"]["state"] == "detected"
    assert e["github-action:actions/checkout"]["state"] == "needs-person"
    assert "proposal" in e["github-action:actions/checkout"]["reason"]
    count = len(ledger["entries"])

    # the candidate carries the crate; its tests run, fail, are fixed, pass
    write(fixture_repo, "ike-adblock/Cargo.lock", lock(("adblock", "0.13.6"), ("serde_json", "1.0.2"),
                                                       ("itoa", "1.0.0")))
    cand_inv = inv_tool.inventory(fixture_repo, offline=True)
    running = {"tests.yml": {"status": "in_progress", "jobs": {"tests": {"status": "in_progress", "steps": {}}}}}
    ledger = ledger_tool.update(ledger, inv, candidate({}), cand_inv=cand_inv, now=DAY1 + dt.timedelta(hours=1))
    assert ledger["entries"]["crate:serde_json@1.0.2"]["state"] == "candidate"
    ledger = ledger_tool.update(ledger, inv, candidate(running), cand_inv=cand_inv, now=DAY1 + dt.timedelta(hours=2))
    assert ledger["entries"]["crate:serde_json@1.0.2"]["state"] == "testing"
    failed = json.loads(json.dumps(ALL_GREEN))
    failed["jobs"]["tests"]["steps"]["Licences"] = "failure"
    ledger = ledger_tool.update(ledger, inv, candidate({"tests.yml": failed, "security.yml": SECURITY_GREEN}),
                                cand_inv=cand_inv, now=DAY1 + dt.timedelta(hours=3))
    entry = ledger["entries"]["crate:serde_json@1.0.2"]
    assert entry["state"] == "fixing" and "licences" in entry["reason"] and entry["last_run"] == "https://x/runs/7"
    ledger = ledger_tool.update(ledger, inv, candidate({"tests.yml": failed}, autofix_issue="#97"),
                                cand_inv=cand_inv, now=DAY1 + dt.timedelta(hours=4))
    assert ledger["entries"]["crate:serde_json@1.0.2"]["state"] == "needs-person"
    # a person's fix: a new candidate, tested again (a new attempt)
    ledger = ledger_tool.update(ledger, inv, candidate(running), cand_inv=cand_inv,
                                now=DAY1 + dt.timedelta(hours=4, minutes=30))
    assert ledger["entries"]["crate:serde_json@1.0.2"]["state"] == "testing"
    # green, but the security checks did not run on it: not verified, never passed
    ledger = ledger_tool.update(ledger, inv, candidate({"tests.yml": ALL_GREEN}), cand_inv=cand_inv,
                                now=DAY1 + dt.timedelta(hours=5))
    entry = ledger["entries"]["crate:serde_json@1.0.2"]
    assert entry["state"] == "needs-person" and "not verified: advisories" in entry["reason"]
    ledger = ledger_tool.update(ledger, inv, candidate({"tests.yml": ALL_GREEN, "security.yml": SECURITY_GREEN}),
                                cand_inv=cand_inv, now=DAY1 + dt.timedelta(hours=6))
    entry = ledger["entries"]["crate:serde_json@1.0.2"]
    assert entry["state"] == "passed" and "owner's merge" in entry["reason"]
    assert entry["attempts"] == 2                          # it went into a candidate again after failing
    assert len(ledger["entries"]) == count                  # never added twice
    # Arch: arch.yml started on main after the change was seen
    arch_run = {"status": "in_progress", "created_at": "2026-11-20T06:00:00Z", "url": "https://x/runs/8"}
    ledger = ledger_tool.update(ledger, inv, {"arch_main": arch_run}, now=DAY1 + dt.timedelta(hours=7))
    assert ledger["entries"]["arch-package:qt6-webengine@6.141.0-1"]["state"] == "testing"
    ledger = ledger_tool.update(ledger, inv, {"arch_main": dict(arch_run, status="completed", conclusion="success")},
                                now=DAY1 + dt.timedelta(hours=8))
    assert ledger["entries"]["arch-package:qt6-webengine@6.141.0-1"]["state"] == "passed"

    # merged: main now has 1.0.2 and the tested Arch set has the new engine
    tested = {"tested": {"packages": {"python": "3.14.10-1", "qt6-webengine": "6.141.0-1", "breeze": ""}}}
    merged = take(fixture_repo, up, arch_tested=tested)
    ledger = ledger_tool.update(ledger, merged, now=DAY2)
    assert ledger["entries"]["crate:serde_json@1.0.2"]["reason"].startswith("in main since")
    # finished entries leave after PRUNE_DAYS
    later = DAY2 + dt.timedelta(days=ledger_tool.PRUNE_DAYS + 1)
    ledger = ledger_tool.update(ledger, merged, now=later)
    assert "crate:serde_json@1.0.2" not in ledger["entries"]


def test_failed_updates_stay_and_are_tried_again(fixture_repo):
    up = Upstream(crates={"serde_json": ["1.0.1", "1.0.2"]})
    inv = take(fixture_repo, up)
    ledger = ledger_tool.update(ledger_tool.update(None, take(fixture_repo), now=DAY1), inv, now=DAY1)
    key = "crate:serde_json@1.0.2"
    report = {"components": [{"name": "serde_json", "error": "source unreachable: OSError: down"}]}
    ledger = ledger_tool.update(ledger, inv, report=report, now=DAY1 + dt.timedelta(hours=1))
    assert ledger["entries"][key]["state"] == "retry-later" and "source unreachable" in ledger["entries"][key]["reason"]
    assert ledger["entries"][key]["next_retry"].startswith("2026-11-21")
    ledger = ledger_tool.update(ledger, inv, now=DAY1 + dt.timedelta(hours=2))     # not due yet
    assert ledger["entries"][key]["state"] == "retry-later"
    ledger = ledger_tool.update(ledger, inv, now=DAY2 + dt.timedelta(hours=1))
    assert ledger["entries"][key]["state"] == "detected" and ledger["entries"][key]["attempts"] == 2
    # too many attempts: blocked for a person, the reason kept
    ledger["entries"][key]["attempts"] = ledger_tool.MAX_ATTEMPTS
    ledger = ledger_tool.update(ledger, inv, report=report, now=DAY3)
    ledger = ledger_tool.update(ledger, inv, now=DAY3 + dt.timedelta(days=2))
    assert ledger["entries"][key]["state"] == "blocked" and "tried" in ledger["entries"][key]["reason"]
    # a major version cargo update cannot take waits a week, never a candidate
    major = take(fixture_repo, Upstream(crates={"itoa": ["1.0.0", "2.0.0"]}))
    ledger = ledger_tool.update(ledger, major, now=DAY3)
    assert ledger["entries"]["crate:itoa@2.0.0"]["state"] == "retry-later"


def test_the_ledger_issue_body_round_trips_and_is_checked(fixture_repo):
    inv = take(fixture_repo, Upstream(crates={"serde_json": ["1.0.1", "1.0.2"]}))
    ledger = ledger_tool.update(ledger_tool.update(None, take(fixture_repo), now=DAY1), inv, now=DAY2)
    body = ledger_tool.render(ledger, inv, closed=[97])
    assert "# Maintenance ledger" in body and "| serde_json | 1.0.1 → 1.0.2 | **detected** |" in body
    assert "#97" in body and len(body) < ledger_tool.MAX_BODY
    assert ledger_tool.parse_body(body) == ledger
    # a block written by hand with a state the ledger does not know, or a key that lies, is not read
    for bad in (body.replace('"state": "detected"', '"state": "merged"'),
                body.replace('"key": "crate:serde_json@1.0.2"', '"key": "crate:other@9"'),
                body.replace(ledger_tool.END, ""), "no ledger here"):
        assert ledger_tool.parse_body(bad) is None
    # a ledger too large for an issue is slimmed, never cut in the middle
    for n in range(400):
        ledger["entries"]["crate:x%d@1" % n] = dict(ledger["entries"]["crate:serde_json@1.0.2"],
                                                    key="crate:x%d@1" % n, state="passed", reason="r" * 150)
    big = ledger_tool.render(ledger, inv)
    assert len(big) <= ledger_tool.MAX_BODY + 20000 and ledger_tool.parse_body(big) is not None


# --- closing the automatic fix's reports whose failure is gone (issue #97) ------------------------

REPORT_97 = """**Tests** failed and could not be fixed automatically: ...

````text
# Failure to fix
- Workflow: Tests
- Branch: automation/daily-maintenance
- Commit: 97df120a222c9b6bc8cc6191d00a56a2ffe3ef23

## Job `tests` (failed step: Licences)

The failed step's log:
````

<!-- autofix-sha: 97df120a222c9b6bc8cc6191d00a56a2ffe3ef23 on automation/daily-maintenance -->
"""
COMMENT_97 = REPORT_97.replace("Licences", "No tests lost").replace("97df120a222c9b6bc8cc6191d00a56a2ffe3ef23",
                                                                     "46f76be6b6aaf99662b5789d246566ad76df6fab")


def _run(sha, created, **steps):
    return {"head_sha": sha, "created_at": created, "url": "https://x/runs/%s" % sha[:4], "conclusion": "failure",
            "jobs": {"tests": {"steps": {k.replace("_", " "): v for k, v in steps.items()}}}}


def test_a_report_is_closed_when_a_later_run_passes_what_failed():
    steps = ledger_tool.report_steps([REPORT_97, COMMENT_97])
    assert steps == {"tests": ["Licences", "No tests lost"]}
    rep = {"number": 97, "workflow": "Tests", "steps": steps, "reported_at": "2026-11-22T06:28:59Z",
           "marks": [("97df120a222c9b6bc8cc6191d00a56a2ffe3ef23", "automation/daily-maintenance"),
                     ("46f76be6b6aaf99662b5789d246566ad76df6fab", "automation/daily-maintenance")]}
    branch = "automation/daily-maintenance"

    def close(run):
        return ledger_tool.finished_reports([rep], {"Tests": {branch: run}})
    # the next candidate passes the licences and the bookkeeping (other steps may still fail)
    good = _run("beef" * 10, "2026-11-23T06:40:00Z", Licences="success", No_tests_lost="success", Tests="failure")
    done = close(good)
    assert [n for n, _ in done] == [97] and "Licences, No tests lost" in done[0][1]
    assert close(dict(good, jobs={"tests": {"steps": {"Licences": "failure", "No tests lost": "success"}}})) == []
    assert close(_run("beef" * 10, "2026-11-23T06:40:00Z", Licences="success")) == []   # a step not passed
    assert close(dict(good, head_sha="46f76be6b6aaf99662b5789d246566ad76df6fab")) == []    # the same commit
    assert close(dict(good, created_at="2026-11-22T06:00:00Z")) == []                     # before the report
    assert close(None) == []
    # a report that names no step: the whole run must pass
    whole = dict(rep, steps={})
    assert ledger_tool.finished_reports([whole], {"Tests": {branch: good}}) == []
    assert ledger_tool.finished_reports([whole], {"Tests": {branch: dict(good, conclusion="success")}})


def test_only_the_report_jobs_own_comments_count(monkeypatch):
    bot = {"login": "github-actions[bot]"}
    issue = {"number": 97, "title": plan_tool.ISSUE_TITLE % "Tests", "user": bot, "body": REPORT_97,
             "created_at": "2026-11-22T04:00:00Z"}
    answers = {
        "repos/o/r/issues?state=open&labels=autofix&per_page=100": [
            issue, dict(issue, number=5, user={"login": "someone"}),
            dict(issue, number=6, title="Something else")],
        "repos/o/r/issues/97/comments?per_page=100": [
            {"user": bot, "body": COMMENT_97, "created_at": "2026-11-22T06:28:59Z"},
            {"user": {"login": "someone"}, "body": COMMENT_97.replace("No tests lost", "Lint").replace(
                "46f76be", "1234567"), "created_at": "2026-11-22T07:00:00Z"}],
    }
    reports = ledger_tool.open_reports("o/r", lambda path, **kw: answers[path])
    assert [r["number"] for r in reports] == [97]
    assert reports[0]["steps"] == {"tests": ["Licences", "No tests lost"]}
    assert reports[0]["reported_at"] == "2026-11-22T06:28:59Z" and len(reports[0]["marks"]) == 2


def test_gather_reads_github_with_get_only():
    calls = []

    def api(path, method="GET", data=None, raw=False):
        calls.append((method, path))
        if path.endswith("/commits/main"):
            return {"sha": "main1"}
        if "/pulls?" in path:
            return [{"number": 43, "html_url": "https://x/pull/43", "head": {"sha": "c0ffee"}}]
        if "/runs?" in path:
            return {"workflow_runs": [{"id": 1, "head_sha": "c0ffee", "head_branch": "automation/daily-maintenance",
                                       "status": "completed", "conclusion": "success", "created_at": "2026-11-22T07:00:00Z",
                                       "html_url": "https://x/runs/1"}]}
        if path.endswith("/jobs?per_page=100"):
            return {"jobs": [{"name": "tests", "status": "completed", "conclusion": "success",
                              "steps": [{"name": "Licences", "conclusion": "success"}]}]}
        if "/artifacts?" in path:
            return {"artifacts": []}
        if "/compare/" in path:
            return {"commits": [{"commit": {"message": "autofix: attempt 1"}}, {"commit": {"message": "x"}}]}
        if "/issues?" in path:
            return []
        raise RuntimeError("HTTP 404")
    status = ledger_tool.gather("o/r", api)
    assert {m for m, _ in calls} == {"GET"}
    assert status["main_sha"] == "main1" and status["candidate"]["pr"] == 43
    assert status["candidate"]["autofix_commits"] == 1 and status["candidate"]["skips"] is None   # no artifact: not read
    assert status["candidate"]["runs"]["tests.yml"]["jobs"]["tests"]["steps"]["Licences"] == "success"
    assert ledger_tool.advisories_of({"security_main": {"url": "u", "jobs": {"rust-advisories": {
        "conclusion": "failure"}}}})["state"] == "found"
    assert ledger_tool.advisories_of({})["state"] == "unknown"


# --- WP4: not verified, never passed ----------------------------------------------------------------

JUNIT = """<?xml version="1.0" encoding="utf-8"?><testsuites><testsuite name="pytest">
<testcase classname="tests.test_plasma" name="test_video" time="0.1"><skipped message="ffmpeg not installed"/></testcase>
<testcase classname="tests.test_plasma" name="test_theme" time="0.1"/>
<testcase classname="tests.test_licences" name="test_crates" time="0.1"><skipped message="needs cargo"/></testcase>
<testcase classname="tests.test_window" name="test_width" time="0.1"><failure message="boom"/></testcase>
</testsuite></testsuites>"""


def test_a_skipped_test_is_not_verified(tmp_path):
    (tmp_path / "junit.xml").write_text(JUNIT)
    info = tc.read_junit([tmp_path / "junit.xml", tmp_path / "missing.xml"])
    assert (info["tests"], info["passed"], info["failed"], info["skipped"]) == (4, 1, 1, 2)
    assert info["unreadable"] and "missing.xml" in info["unreadable"][0]
    by_area = tc.skips_by_area(info["skips"])
    assert by_area["desktop integration"]["ffmpeg not installed"] == ["tests/test_plasma.py::test_video"]
    assert by_area["licences"]["needs cargo"] == ["tests/test_licences.py::test_crates"]
    text = tc.junit_markdown(info)
    assert "skipped 2 (not verified)" in text and "| desktop integration | ffmpeg not installed |" in text
    assert "not verified" in tc.junit_markdown(tc.read_junit([tmp_path / "missing.xml"])).lower()
    # the command line never fails the run
    assert tc.main(["--junit", str(tmp_path / "missing.xml"), "--json", str(tmp_path / "out/s.json")]) == 0
    assert json.loads((tmp_path / "out/s.json").read_text())["unreadable"]


def test_each_kind_has_its_required_tests_and_missing_ones_are_not_verified():
    for kind in ("crate", "adblock-engine", "arch-package", "pypi-test", "integrated", "github-action",
                 "filter-list", "runtime-tool", "build-tool", "python-module", "pyqt-module"):
        need = tc.required_for([kind])
        assert need and set(need) <= set(tc.CATEGORIES), kind
    assert {"licences", "advisories", "build", "installed"} <= set(tc.required_for(["crate"]))
    assert "arch-packaging" in tc.required_for(["arch-package"])
    assert "filter-lists" in tc.required_for(["adblock-engine"])
    runs = {"tests.yml": ALL_GREEN}
    results = tc.results_from_runs(runs)
    assert results["licences"] == "success" and results["advisories"] == "" and results["arch-packaging"] == ""
    rows = tc.verify(tc.required_for(["crate"]), results, [{"test": "t", "junit": "junit.xml"}])
    state = {r["category"]: r for r in rows}
    assert state["licences"]["state"] == "passed"
    assert state["advisories"]["state"] == "not verified" and "not run" in state["advisories"]["detail"]
    assert "1 skipped tests not verified" in state["unit-integration"]["detail"]
    assert tc.verdict(rows) == "not verified"
    # results unreadable: the suite is not verified even when its step passed
    assert {r["category"]: r["state"] for r in tc.verify(["unit-integration"], results, None)} == {
        "unit-integration": "not verified"}
    assert tc.verify(["desktop"], {"desktop": "success"})[0]["state"] == "not verified"
    assert tc.verdict(tc.verify(["licences"], {"licences": "failure"})) == "failed"
    assert tc.verdict(tc.verify(["licences"], {"licences": "success"})) == "passed"
    running = tc.results_from_runs({"tests.yml": {"status": "in_progress", "jobs": {"tests": {
        "status": "in_progress", "steps": {"Lint": "success"}}}}})
    assert running["lint"] == "success" and running["licences"] == "running"


# --- WP13: the candidate's pull request ---------------------------------------------------------------

COMPONENTS = {"components": [
    {"name": "Rust crates of the AdBlock engine", "current": "pyo3 0.30.1, 88 crates",
     "latest": "pyo3 0.30.1, 88 crates", "update": True, "note": "serde_json 1.0.1 -> 1.0.2", "also": "",
     "error": "", "refused": None},
    {"name": "Dark Reader (engine and lists)", "current": "4.9.135", "latest": "4.9.136", "update": False,
     "note": "", "also": "", "error": "", "refused": {"current": "4.9.135", "latest": "4.9.136",
                                                     "step": "tools/build-darkreader.py, patch 'x'"}},
    {"name": "uBlock Origin scriptlets", "current": "", "latest": "", "update": False, "note": "", "also": "",
     "error": "source unreachable: OSError: down", "refused": None}]}


def test_the_candidate_report_lists_what_the_owner_needs():
    body = report_tool.compose(COMPONENTS, "### the component report\n", candidate(
        {"tests.yml": ALL_GREEN, "security.yml": SECURITY_GREEN},
        skips=[{"test": "tests/test_plasma.py::test_video", "area": "desktop integration",
                "reason": "ffmpeg not installed", "junit": "junit.xml"}]),
        autofix="abc1234 autofix: attempt 1 (Tests)\n", licences="ok\nexit 0\n",
        lists={"state": "findings", "findings": ["scriptlet `x` unknown"]}, engine="builds")
    for section in ("## What this candidate changes", "## Changes of the automatic fix (AutoFix)",
                    "## Problems found", "## Tests on this commit", "## Security checks", "## Licences",
                    "## Limits", "<details><summary>The component report</summary>"):
        assert section in body, section
    assert "| Rust crates of the AdBlock engine | pyo3 0.30.1, 88 crates |" in body and "serde_json 1.0.1 -> 1.0.2" in body
    assert "`abc1234 autofix: attempt 1 (Tests)`" in body
    assert "I.K.E.'s builder refused 4.9.136" in body and "uBlock Origin scriptlets**: not checked" in body
    assert "filter lists: scriptlet `x` unknown" in body
    assert "| licences | passed |" in body and "third-party.py --check` when the candidate was made: **passed**" in body
    assert "Skipped tests: not verified (1)" in body and "ffmpeg not installed" in body
    assert "RustSec advisories of every crate (cargo-deny): **passed**" in body
    assert "Verdict: **passed** (1 skipped tests not verified" in body   # a skipped test is never hidden
    # a candidate pushed now: everything not verified, said plainly
    fresh = report_tool.compose(COMPONENTS, "", candidate({"tests.yml": ALL_GREEN}), pushed=True)
    assert "Until then everything is **not verified**" in fresh and "| licences | **not verified** |" in fresh
    assert "| licences | passed |" not in fresh
    assert "**not verified** (not run)" in fresh                       # no licence check given


# --- the plan: git failing to reach GitHub in a bookkeeping step (run 44990600858) -------------------

LOG_403 = """2026-11-22T06:20:01.0000000Z ##[group]Run git fetch -q --no-tags --unshallow origin main 2>/dev/null || git fetch -q --no-tags origin main
2026-11-22T06:20:01.0000000Z git fetch -q --no-tags --unshallow origin main 2>/dev/null || git fetch -q --no-tags origin main
2026-11-22T06:20:01.0000000Z shell: /usr/bin/bash -e {0}
2026-11-22T06:20:01.0000000Z ##[endgroup]
2026-11-22T06:20:02.0000000Z fatal: unable to access 'https://github.com/NullSector-2077/IKE-Browser/': The requested URL returned error: 403
2026-11-22T06:20:02.0000000Z ##[error]Process completed with exit code 128.
"""


def _failed(*steps):
    return [{"name": "tests", "conclusion": "failure",
             "steps": [{"name": s, "conclusion": "failure"} for s in steps]}]


def test_a_git_fetch_refused_in_a_bookkeeping_step_is_infrastructure():
    run = {"name": "Tests", "head_branch": "automation/daily-maintenance", "conclusion": "failure", "head_sha": "abc",
           "head_repository": {"full_name": "o/r"}, "_repo": "o/r", "_tip": "abc", "_main_tip": "m",
           "_attempts": 0, "_engine_update": False, "run_attempt": 1}
    jobs = _failed("No tests lost")
    plan = plan_tool.decide(run, jobs, "")
    assert plan["action"] == "fix"                        # from the step names alone it looked like the code's
    log = plan_tool.clean_log(LOG_403)
    assert plan_tool.git_network_failure(log)
    first = plan_tool.infra_in_logs(plan, "Tests", jobs, {"tests": log}, 1)
    assert first["action"] == "rerun" and first["kind"] == "infra" and first["push_branch"] == ""
    again = plan_tool.infra_in_logs(plan, "Tests", jobs, {"tests": log}, 2)
    assert again["action"] == "issue" and again["kind"] == "infra" and "git exit 128" in again["reason"]
    starting = plan_tool.infra_in_logs(plan, "Tests", _failed("The starting commit's tests on this code"),
                                       {"tests": log}, 2)
    assert starting["action"] == "issue"
    # still the code's: tests really lost, another step failed too, git's error with another exit code,
    # an error that is not git reaching GitHub, no log
    lost = "##[group]Run x\n::error::2 test(s) of abc are no longer run here\n##[error]Process completed with exit code 1."
    for jobs_, logs in ((jobs, {"tests": plan_tool.clean_log(lost)}),
                        (_failed("Lint", "No tests lost"), {"tests": log}),
                        (jobs, {"tests": log.replace("exit code 128", "exit code 1")}),
                        (jobs, {"tests": log.replace("fatal: unable to access", "error: pathspec").replace(
                            "The requested URL returned error: 403", "x")}),
                        (jobs, {})):
        assert plan_tool.infra_in_logs(plan, "Tests", jobs_, logs, 2)["action"] == "fix", logs
    # only "Tests" and only a planned fix
    assert plan_tool.infra_in_logs(dict(plan, action="skip"), "Tests", jobs, {"tests": log}, 2)["action"] == "skip"
    assert plan_tool.infra_in_logs(plan, "Arch Linux", jobs, {"tests": log}, 2)["action"] == "fix"


def test_a_failed_ledger_job_is_never_an_automatic_fix():
    run = {"name": "Daily component check", "head_branch": "main", "conclusion": "failure", "head_sha": "abc",
           "head_repository": {"full_name": "o/r"}, "_repo": "o/r", "_tip": "abc", "_main_tip": "m",
           "_attempts": 0, "_engine_update": False}
    plan = plan_tool.decide(run, [{"name": "ledger", "conclusion": "failure", "steps": []}], "")
    assert plan["action"] == "issue" and plan["kind"] == "infra"


# --- the protections and the workflows ----------------------------------------------------------------

NEW_TOOLS = ("tools/check-components.py", "tools/inventory.py", "tools/maintenance-ledger.py",
             "tools/test-categories.py", "tools/maintenance-report.py")


def test_no_agent_may_change_the_maintenance_tools():
    ctx = load("autofix-context")
    for path in NEW_TOOLS:
        assert path in guard.FORBIDDEN_FILES and path in ctx.NOT_RECENT, path
        assert guard.allowed_path(path, False), path
    autofix = (WORKFLOWS / "autofix.yml").read_text()
    assert all(p in autofix for p in NEW_TOOLS)            # the message for ChatGPT says so too


def _jobs(text):
    parts = re.split(r"^  ([a-z-]+):\n", text.split("\njobs:\n", 1)[1], flags=re.M)
    return dict(zip(parts[1::2], parts[2::2]))


def test_the_daily_check_writes_the_ledger_with_the_least_rights():
    daily = (WORKFLOWS / "daily-check.yml").read_text()
    job = _jobs(daily)["ledger"]
    assert re.search(r"permissions:\n\s+actions: read .*\n\s+contents: read\n\s+issues: write .*\n"
                     r"\s+pull-requests: read .*\n\s+steps:", job)
    assert "write" not in job.split("permissions:", 1)[1].split("steps:", 1)[0].replace("issues: write", "")
    assert "persist-credentials: false" in job and "ref: automation/daily-maintenance" in job
    steps = job.split("      - ")
    with_token = [s.split("\n")[0] for s in steps if "GH_TOKEN" in s]
    assert with_token == ["name: GitHub's state of the candidate, of Arch and of the security checks (GET only)",
                          "name: The maintenance ledger"]
    inventory = next(s for s in steps if s.startswith("name: Inventory of the external components"))
    assert "python3 tools/inventory.py --json inventory.json" in inventory and "--offline --root candidate" in inventory
    assert "tools/maintenance-ledger.py update" in job and "tools/maintenance-ledger.py gather" in job
    assert "needs: [check, lists]" in job and "needs.check.result == 'success'" in job
    assert "arch-tested.json" in _jobs(daily)["check"]


def test_the_tests_report_what_they_did_not_verify():
    tests = _jobs((WORKFLOWS / "tests.yml").read_text())["tests"]
    assert 'python -m pytest --junitxml="$RUNNER_TEMP/test-results/junit.xml"' in tests
    assert '--junitxml="$RUNNER_TEMP/test-results/junit-installed.xml"' in tests
    summary = tests.split("- name: What the tests verified", 1)[1]
    assert summary.lstrip().startswith("if: always()") and "tools/test-categories.py" in summary
    assert '>> "$GITHUB_STEP_SUMMARY" || true' in summary
    assert "name: test-results" in summary and "if: always()" in summary.split("name: test-results")[0]


def test_the_candidate_pull_request_carries_the_report():
    workflow = (WORKFLOWS / "daily-maintenance.yml").read_text()
    jobs = _jobs(workflow)
    publish = jobs["publish-candidate"]
    assert "python3 tools/maintenance-report.py --components" in publish
    assert "tools/maintenance-ledger.py gather" in publish and '--candidate-sha "$sha"' in publish
    assert "--grep '^autofix:'" in publish
    assert "gh workflow run security.yml --ref automation/daily-maintenance" in publish
    prepare = jobs["prepare"]
    assert "python3 tools/third-party.py --check > licences.txt" in prepare
    assert "for f in component-report.json filter-lists.json licences.txt" in prepare


def test_the_maintenance_is_documented():
    doc = (ROOT / "docs/MAINTENANCE.md").read_text()
    for word in ("tools/inventory.py", "tools/maintenance-ledger.py", "maintenance-ledger", "tools/test-categories.py",
                 "tools/maintenance-report.py", "not verified", "used but not declared"):
        assert word in doc, word
