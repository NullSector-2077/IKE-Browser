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
import subprocess
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
            'noto-fonts-cjk: Chinese, Japanese and Korean interface text')

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
        "libnotify": "0.8.8-1", "noto-fonts-cjk": "20240730-1", "qt6-base": "6.12.0-5", "breeze": "6.5.3-1",
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
        "arch-build:rust", "arch-build:gcc", "arch-optional:libnotify", "arch-optional:noto-fonts-cjk",
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
    assert found["arch-optional:noto-fonts-cjk"]["notes"] == ["Chinese, Japanese and Korean interface text"]
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
    assert len(pkg["optdepends"]) == 6 and "rust" in pkg["makedepends"]
    # 1.1.24: xdg-utils (advisory AVG-1420, no fix) is gone; files and links go to the desktop
    # portal or the desktop's own opener (ike/handoff.py), never xdg-open or xdg-settings
    assert "xdg-utils" not in [name for name, _ in pkg["optdepends"]] + pkg["depends"]
    lists = inv_tool.default_lists(ROOT)
    assert lists and all("filter-list:" + e["name"] in found for e in lists)
    crates = inv_tool.parse_cargo_lock((ROOT / "ike-adblock/Cargo.lock").read_text())
    assert sum(r["kind"] in ("crate", "adblock-engine") for r in inv["components"]) == len(crates) - 1
    for kind in ("python-module", "pyqt-module", "runtime-tool", "github-action", "pypi-test", "integrated",
                 "build-tool", "node", "ci-tool"):
        assert inv["counts"].get(kind), kind
    for name in ("PyQt6.QtWebEngineCore", "PyQt6.QtSvg", "PyQt6.QtWebChannel"):
        assert "pyqt-module:" + name in found
    for tool in ("kioclient", "gio", "exo-open"):
        assert "runtime-tool:" + tool in found
    # 1.1.24: notifications are a D-Bus call, no notify-send (libnotify) and no xdg-utils
    for tool in ("notify-send", "xdg-settings", "xdg-open", "xdg-mime", "xdg-email"):
        assert "runtime-tool:" + tool not in found, tool
    for tool in ("kioclient", "gio", "exo-open"):           # the desktop's own, not dependencies
        assert found["runtime-tool:" + tool]["declared"].startswith("the desktop's own"), found["runtime-tool:" + tool]
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
    assert new["python-module:yaml"]["state"] == "retrying" and "python-yaml" in new["python-module:yaml"]["reason"]
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
    assert new["python-module:yaml"]["state"] == "retrying"          # the PKGBUILD's candidate declares it
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
    assert e["github-action:actions/checkout"]["state"] == "detected"         # its pin's own candidate (ci-pins)
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
    assert ledger["entries"]["crate:serde_json@1.0.2"]["state"] == "retrying"     # fixed again every day
    # a person's fix: a new candidate, tested again (a new attempt)
    ledger = ledger_tool.update(ledger, inv, candidate(running), cand_inv=cand_inv,
                                now=DAY1 + dt.timedelta(hours=4, minutes=30))
    assert ledger["entries"]["crate:serde_json@1.0.2"]["state"] == "testing"
    # green, but the security checks did not run on it: not verified, never passed
    ledger = ledger_tool.update(ledger, inv, candidate({"tests.yml": ALL_GREEN}), cand_inv=cand_inv,
                                now=DAY1 + dt.timedelta(hours=5))
    entry = ledger["entries"]["crate:serde_json@1.0.2"]
    assert entry["state"] == "retrying" and "not verified: advisories" in entry["reason"]
    ledger = ledger_tool.update(ledger, inv, candidate({"tests.yml": ALL_GREEN, "security.yml": SECURITY_GREEN}),
                                cand_inv=cand_inv, now=DAY1 + dt.timedelta(hours=6))
    entry = ledger["entries"]["crate:serde_json@1.0.2"]
    assert entry["state"] == "passed" and "the verified merge takes it" in entry["reason"]
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
    # many attempts: never given up (2026-11-22), tried again as many times as it takes
    ledger["entries"][key]["attempts"] = ledger_tool.MAX_ATTEMPTS
    ledger = ledger_tool.update(ledger, inv, report=report, now=DAY3)
    ledger = ledger_tool.update(ledger, inv, now=DAY3 + dt.timedelta(days=2))
    assert ledger["entries"][key]["state"] == "detected" and "tried again" in ledger["entries"][key]["reason"]
    assert ledger["entries"][key]["attempts"] == ledger_tool.MAX_ATTEMPTS + 1
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
    {"name": "Dark Reader (lists)", "current": "4.9.135", "latest": "4.9.136", "update": False,
     "note": "", "also": "", "error": "", "refused": {"current": "4.9.135", "latest": "4.9.136",
                                                     "step": "tools/build-darkreader-lists.py, the site fixes list"}},
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
    jobs = _jobs((WORKFLOWS / "tests.yml").read_text())
    tests = jobs["tests"]
    # since 2026-11-24 each shard writes the junit of its part (tools/shard-tests.py run), and the gate
    # "tests" writes the run's two files from all of them, only when every shard's is there
    assert "tools/shard-tests.py run --kind source" in jobs["shard"]
    assert "tools/shard-tests.py run --kind installed" in jobs["installed"]
    assert '"--junitxml=%s" % junit' in (ROOT / "tools/shard-tests.py").read_text()
    assert '--merged-junit "$RUNNER_TEMP/test-results/junit.xml"' in tests
    assert '--merged-junit "$RUNNER_TEMP/test-results/junit-installed.xml"' in tests
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


# --- WP6: security findings into the maintenance and the automatic fix ---------------------------------
# --- WP7: vulnerability sources for the inventory (OSV, Arch's security tracker) ------------------------

security_fix = load("security-fix")
vulns = load("vulnerabilities")

# cargo-deny 0.20.2's own output (the positive control of docs/SECURITY.md, smallvec 1.6.0), as it
# appears in a GitHub job log (time stamps), and an advisory with no fixed version
CARGO_DENY_LOG = """2026-11-22T04:30:01.0000000Z ##[group]Run cargo deny --manifest-path ike-adblock/Cargo.toml check advisories
2026-11-22T04:30:09.1000000Z error[vulnerability]: Buffer overflow in SmallVec::insert_many
2026-11-22T04:30:09.1000000Z   ┌─ /home/runner/work/IKE-Browser/IKE-Browser/ike-adblock/Cargo.lock:2:1
2026-11-22T04:30:09.1000000Z   │
2026-11-22T04:30:09.1000000Z 2 │ smallvec 1.6.0 registry+https://github.com/rust-lang/crates.io-index
2026-11-22T04:30:09.1000000Z   │ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ security vulnerability detected
2026-11-22T04:30:09.1000000Z   │
2026-11-22T04:30:09.1000000Z   ├ ID: RUSTSEC-2021-0003
2026-11-22T04:30:09.1000000Z   ├ Advisory: https://rustsec.org/advisories/RUSTSEC-2021-0003
2026-11-22T04:30:09.1000000Z   ├ A bug in the `SmallVec::insert_many` method caused it to allocate a buffer that was smaller than needed.
2026-11-22T04:30:09.1000000Z   ├ Announcement: https://github.com/servo/rust-smallvec/issues/252
2026-11-22T04:30:09.1000000Z   ├ Solution: Upgrade to >=0.6.14, <1.0.0 OR >=1.6.1 (try `cargo update -p smallvec`)
2026-11-22T04:30:09.1000000Z   ├ smallvec v1.6.0
2026-11-22T04:30:09.1000000Z     └── ike-adblock v0.1.0
2026-11-22T04:30:09.1000000Z
2026-11-22T04:30:09.1000000Z error[unmaintained]: itoa is unmaintained
2026-11-22T04:30:09.1000000Z   ┌─ /home/runner/work/IKE-Browser/IKE-Browser/ike-adblock/Cargo.lock:9:1
2026-11-22T04:30:09.1000000Z   │
2026-11-22T04:30:09.1000000Z 9 │ itoa 1.0.0 registry+https://github.com/rust-lang/crates.io-index
2026-11-22T04:30:09.1000000Z   │
2026-11-22T04:30:09.1000000Z   ├ ID: RUSTSEC-2099-0001
2026-11-22T04:30:09.1000000Z   ├ Solution: No safe upgrade is available!
2026-11-22T04:30:09.1000000Z advisories FAILED
2026-11-22T04:30:09.2000000Z ##[error]Process completed with exit code 1.
"""

OSV_VULNS = {
    "GHSA-pyte-st00-0001": {"id": "GHSA-pyte-st00-0001", "summary": "pytest writes a temporary file insecurely",
                            "aliases": ["CVE-2026-0001"],
                            "affected": [{"package": {"ecosystem": "PyPI", "name": "pytest"},
                                          "ranges": [{"type": "ECOSYSTEM", "events": [
                                              {"introduced": "0"}, {"fixed": "9.0.1"}]}]}]},
    "GHSA-ruff-0000-0001": {"id": "GHSA-ruff-0000-0001", "summary": "ruff: a cache file can leak",
                            "affected": [{"package": {"ecosystem": "PyPI", "name": "ruff"},
                                          "ranges": [{"type": "ECOSYSTEM", "events": [{"introduced": "0"}]}]}]},
    "GHSA-chec-kout-0001": {"id": "GHSA-chec-kout-0001", "summary": "checkout keeps a token",
                            "affected": [{"package": {"ecosystem": "GitHub Actions", "name": "actions/checkout"},
                                          "ranges": [{"type": "ECOSYSTEM", "events": [
                                              {"introduced": "7.0.0"}, {"fixed": "7.0.2"}]}]}]},
}
ARCH_GROUPS = [
    {"name": "AVG-2801", "packages": ["python"], "status": "Fixed", "severity": "High",
     "type": "arbitrary code execution", "affected": "3.14.10-1", "fixed": "3.14.11-1", "issues": ["CVE-2026-1111"],
     "advisories": []},
    {"name": "AVG-2802", "packages": ["qt6-webengine", "qt6-base"], "status": "Vulnerable", "severity": "Critical",
     "type": "multiple issues", "affected": "6.140.0-1", "fixed": None, "issues": ["CVE-2026-2222"]},
    {"name": "AVG-2700", "packages": ["gcc"], "status": "Fixed", "severity": "Low", "type": "denial of service",
     "affected": "14.0-1", "fixed": "15.0-1", "issues": []},                 # older than ours: not vulnerable
    {"name": "AVG-2803", "packages": ["breeze"], "status": "Not affected", "affected": "6.5.3-1", "fixed": None},
]
OSV_DEFAULT = {("PyPI", "pytest", "9.0.0"): ["GHSA-pyte-st00-0001"] * 2,
               ("PyPI", "ruff", "0.17.6"): ["GHSA-ruff-0000-0001"],
               ("GitHub Actions", "actions/checkout", "7.0.1"): ["GHSA-chec-kout-0001"]}


class Advisories(Upstream):
    """Upstream, plus the OSV database and Arch's security tracker (stand-ins, no network)."""

    def __init__(self, osv=None, groups=None, **kw):
        super().__init__(**kw)
        self.osv = OSV_DEFAULT if osv is None else osv
        self.groups = ARCH_GROUPS if groups is None else groups
        self.posts = []

    def get(self, url):
        host = re.match(r"https://([^/]+)/", url).group(1)
        if host in ("api.osv.dev", "security.archlinux.org"):
            self.asked.append(url)
            if host in self.down:
                raise OSError("network unreachable")
            if host == "api.osv.dev":
                return json.dumps(OSV_VULNS[url.rsplit("/", 1)[1]]).encode()
            assert url == vulns.ARCH_TRACKER_URL
            return json.dumps(self.groups).encode()
        return super().get(url)

    def post(self, url, payload):
        self.posts.append((url, payload))
        if "api.osv.dev" in self.down:
            raise OSError("Tunnel connection failed: 403")
        assert url == vulns.OSV_BATCH_URL
        res = []
        for q in payload["queries"]:
            found = self.osv.get((q["package"]["ecosystem"], q["package"]["name"], q["version"]), [])
            res.append({"vulns": [{"id": i, "modified": "2026-11-01T00:00:00Z"} for i in found]} if found else {})
        return json.dumps({"results": res}).encode()

    def net(self):
        return inv_tool.Net(get=self.get, ls_remote=self.ls_remote, post=self.post)


def test_an_advisory_of_each_kind_is_found_and_recorded_once(fixture_repo):
    """WP7: a Python, GitHub Actions and Arch component with a known advisory is found, asked in one
    batch, and becomes one ledger entry per advisory, the same on the next day (an npm module is asked
    only with a version a lockfile pins: none here)."""
    up = Advisories()
    inv = take(fixture_repo, up, arch_tested=ARCH_TESTED)
    found = ids(inv)
    # one POST for every PyPI, npm and Action component (batched): names and versions only
    assert len(up.posts) == 1
    queries = {(q["package"]["ecosystem"], q["package"]["name"], q["version"]) for q in up.posts[0][1]["queries"]}
    assert {("PyPI", "pytest", "9.0.0"), ("PyPI", "ruff", "0.17.6"),
            ("GitHub Actions", "actions/checkout", "7.0.1"), ("GitHub Actions", "actions/setup-python", "7.1.0")} \
        <= queries
    # 1.1.30: Dark Reader's engine left I.K.E.; its lists are data, no advisory database is asked about them
    assert not [q for q in queries if q[1] == "darkreader"]
    pytest_ = found["pypi-test:pytest"]
    assert [a["id"] for a in pytest_["advisories"]] == ["GHSA-pyte-st00-0001"]        # twice in the answer, once here
    assert pytest_["advisories"][0]["fixed"] == ["9.0.1"] and pytest_["advisories"][0]["aliases"] == ["CVE-2026-0001"]
    assert pytest_["vulnerabilities"].startswith("1 known (OSV, PyPI 9.0.0): GHSA-pyte-st00-0001 fixed in 9.0.1")
    assert found["pypi-test:ruff"]["advisories"][0]["fixed"] == []                     # no fix upstream
    assert found["github-action:actions/setup-python"]["vulnerabilities"].startswith("none known (OSV")
    assert found["github-action:actions/checkout"]["advisories"][0]["fixed"] == ["7.0.2"]
    # Arch: by the version the last green arch.yml run tested
    assert [a["id"] for a in found["arch-package:python"]["advisories"]] == ["AVG-2801"]
    assert found["arch-package:python"]["advisories"][0]["fixed"] == ["3.14.11-1"]
    assert found["arch-package:qt6-webengine"]["advisories"][0]["fixed"] == []        # Vulnerable: no fix yet
    assert not found["arch-package:breeze"].get("advisories")                          # "Not affected"
    assert found["arch-build:gcc"]["vulnerabilities"].startswith("none known (Arch security tracker")
    assert inv["vulnerability_sources"] == {"api.osv.dev": "ok", "security.archlinux.org": "ok"}
    text = inv_tool.to_markdown(inv)
    assert "#### Known vulnerabilities" in text and "AVG-2802" in text and "**no fix upstream**" in text

    # the ledger: one entry per advisory of a component, never twice
    told = []
    ledger = ledger_tool.update(None, inv, now=DAY1, notices=told)
    sec = {k: e for k, e in ledger["entries"].items() if e.get("security")}
    assert set(sec) == {"pypi-test:pytest@GHSA-pyte-st00-0001", "pypi-test:ruff@GHSA-ruff-0000-0001",
                        "github-action:actions/checkout@GHSA-chec-kout-0001", "arch-package:python@AVG-2801",
                        "arch-package:qt6-webengine@AVG-2802", "arch-package:qt6-base@AVG-2802"}   # one group, two packages
    assert sec["pypi-test:pytest@GHSA-pyte-st00-0001"]["state"] == "detected"
    assert "the daily candidate takes the newer version" in sec["pypi-test:pytest@GHSA-pyte-st00-0001"]["reason"]
    assert sec["arch-package:python@AVG-2801"]["state"] == "detected"
    assert "pacman -Syu" in sec["arch-package:python@AVG-2801"]["reason"]
    assert sec["arch-package:qt6-webengine@AVG-2802"]["state"] == "blocked"
    assert sec["pypi-test:ruff@GHSA-ruff-0000-0001"]["state"] == "blocked"
    assert sec["github-action:actions/checkout@GHSA-chec-kout-0001"]["state"] == "detected"     # the pin's candidate
    assert len(told) == 3 and sum("AVG-2802" in n for n in told) == 2      # only what is blocked is told
    again = []
    ledger = ledger_tool.update(ledger, take(fixture_repo, Advisories(), arch_tested=ARCH_TESTED), now=DAY2,
                                notices=again)
    assert {k for k, e in ledger["entries"].items() if e.get("security")} == set(sec)   # recorded once
    assert again == [] and all(len(e["history"]) == 1 for k, e in ledger["entries"].items() if k in sec)
    assert ledger_tool.parse_body(ledger_tool.render(ledger, inv)) == ledger
    # gone from the answer of a source that answered: fixed
    ledger = ledger_tool.update(ledger, take(fixture_repo, Advisories(osv={}), arch_tested=ARCH_TESTED), now=DAY3)
    assert ledger["entries"]["pypi-test:pytest@GHSA-pyte-st00-0001"]["state"] == "passed"
    assert ledger["entries"]["arch-package:python@AVG-2801"]["state"] == "detected"     # Arch still reports it


def test_an_unreachable_vulnerability_source_is_not_checked(fixture_repo):
    """WP7: a source that does not answer (or answers nonsense) leaves its components "not checked", never
    "none known", and an open advisory is not taken for fixed."""
    ledger = ledger_tool.update(None, take(fixture_repo, Advisories(), arch_tested=ARCH_TESTED), now=DAY1)
    inv = take(fixture_repo, Advisories(down={"api.osv.dev", "security.archlinux.org"}), arch_tested=ARCH_TESTED)
    found = ids(inv)
    for rid in ("pypi-test:pytest", "pypi-test:ruff", "github-action:actions/checkout",
                "arch-package:python", "arch-build:gcc"):
        assert found[rid]["vulnerabilities"] == "not checked", rid
        assert "unreachable" in found[rid]["vulnerability_note"], rid
        assert not found[rid].get("advisories"), rid
    assert all(s.startswith("unreachable") for s in inv["vulnerability_sources"].values())
    assert not any(str(r["vulnerabilities"]).startswith("none known") for r in inv["components"])
    assert "are **not checked** today" in inv_tool.to_markdown(inv)
    later = ledger_tool.update(ledger, inv, now=DAY2)
    assert later["entries"]["pypi-test:pytest@GHSA-pyte-st00-0001"]["state"] == "detected"   # not "passed"
    assert later["entries"]["arch-package:qt6-webengine@AVG-2802"]["state"] == "blocked"

    # an answer laid out differently is not a clean answer either
    class Garbled(Advisories):
        def post(self, url, payload):
            return json.dumps({"results": []}).encode()
    inv = take(fixture_repo, Garbled(), arch_tested=ARCH_TESTED)
    assert ids(inv)["pypi-test:pytest"]["vulnerabilities"] == "not checked"
    assert inv["vulnerability_sources"]["api.osv.dev"].startswith("unreachable: ValueError")
    # a version that cannot be asked about is not checked, with the reason
    recs = {"pypi-ci:x": {"id": "pypi-ci:x", "kind": "pypi-ci", "name": "x", "installed": "unpinned"},
            "github-action:a/b": {"id": "github-action:a/b", "kind": "github-action", "name": "a/b",
                                  "pinned_sha": True, "release": ""}}
    assert vulns.check_osv(recs, lambda *a: pytest.fail("nothing to ask"), None) == "ok"
    assert {r["vulnerabilities"] for r in recs.values()} == {"not checked"}
    # offline: nothing asked at all
    assert inv_tool.inventory(fixture_repo, offline=True)["vulnerability_sources"] == {}
    # Arch's versions are compared as pacman does
    assert vulns.vercmp("1:1.0-1", "2.0-1") == 1 and vulns.vercmp("3.14.10-1", "3.14.11-1") == -1
    assert vulns.vercmp("6.140.0-2", "6.140.0-10") == -1 and vulns.vercmp("1.0rc1-1", "1.0-1") == -1


# --- WP6: the plan, the update and the stricter guard ---------------------------------------------------

def security_run(branch="main", **kw):
    run = {"name": "Security", "head_branch": branch, "conclusion": "failure", "head_sha": "abc123",
           "head_repository": {"full_name": "o/r"}, "_repo": "o/r", "_tip": "abc123", "_main_tip": "main1",
           "_attempts": 0, "_engine_update": False, "_security_prs": {}}
    run.update(kw)
    return run


def failed_job(name, *steps):
    return {"name": name, "conclusion": "failure", "steps": [{"name": s, "conclusion": "failure"} for s in steps]}


def _tests_run(branch, **kw):
    run = {"name": "Tests", "head_branch": branch, "conclusion": "failure", "head_sha": "abc",
           "head_repository": {"full_name": "o/r"}, "_repo": "o/r", "_tip": "abc", "_main_tip": "main1",
           "_attempts": 0, "_engine_update": False}
    run.update(kw)
    return run


ADVISORY_JOB = [failed_job("rust-advisories", "RustSec advisories (every crate of Cargo.lock)")]
SANDBOX_JOB = [failed_job("sandbox", "The sandbox is really on")]


def test_a_rustsec_finding_plans_an_isolated_security_fix():
    found = security_fix.parse(CARGO_DENY_LOG)
    assert [(f["id"], f["crate"], f["version"], f["fix"]) for f in found] == [
        ("RUSTSEC-2021-0003", "smallvec", "1.6.0", "1.6.1"), ("RUSTSEC-2099-0001", "itoa", "1.0.0", "")]
    assert security_fix.fixed_version("Upgrade to >=0.6.14, <1.0.0 OR >=1.6.1", "0.6.10") == "0.6.14"
    plan = plan_tool.decide(security_run(_advisories=found), ADVISORY_JOB, "")
    # a deterministic update first (no AI), on an isolated branch made from main, never main
    assert plan["action"] == "update" and plan["kind"] == "security" and plan["security"] == "true"
    assert plan["push_branch"] == "automation/update/security-rustsec-2021-0003" and plan["checkout"] == "main1"
    assert json.loads(plan["findings"])[0]["id"] == "RUSTSEC-2021-0003"
    assert "RUSTSEC-2099-0001" in plan["reason"] and "no fixed version upstream" in plan["reason"]
    # its branch waits already: nothing twice; the one with no fix is then blocked
    waiting = {"automation/update/security-rustsec-2021-0003": "120"}
    plan = plan_tool.decide(security_run(_advisories=found, _security_prs=waiting), ADVISORY_JOB, "")
    assert plan["action"] == "issue" and plan["reason"].startswith("blocked: no fixed version upstream")
    # the update's own tests fail there: the AI fixes that branch with the stricter guard
    tests = plan_tool.decide(_tests_run("automation/update/security-rustsec-2021-0003", _engine_update=True),
                             [failed_job("tests", "Tests of the AdBlock engine")], "")
    assert (tests["action"], tests["kind"], tests["security"]) == ("fix", "security", "true")
    assert tests["push_branch"] == "automation/update/security-rustsec-2021-0003" and tests["checkout"] == "abc"
    assert tests["allow_adblock"] == "true"                      # the new crate: I.K.E.'s wrapper only
    tired = plan_tool.decide(_tests_run("automation/update/security-rustsec-2021-0003", _attempts=2),
                             [failed_job("tests", "Lint")], "")
    # the cap is per day: tried again tomorrow, under the same security rules (nothing weakened, nothing closed)
    assert tired["action"] == "retry" and tired["reason"].startswith("today's 2 automatic fixes under the security")
    assert plan_tool.decide(_tests_run("automation/update/security-rustsec-2021-0003", _attempts=2,
                                       _attempts_today=0), [failed_job("tests", "Lint")], "")["action"] == "fix"
    # since WP5 (the full chain) the other candidates of automation/update/<id> are fixed on their own
    # branch too, never with the security rules; a branch that is no candidate of the chain is not
    crates = plan_tool.decide(_tests_run("automation/update/crates"), [failed_job("tests", "Lint")], "")
    assert (crates["action"], crates["kind"], crates["push_branch"], crates["security"]) == (
        "fix", "update", "automation/update/crates", "false")
    assert plan_tool.decide(_tests_run("automation/update/not-a-candidate"), [failed_job("tests", "Lint")],
                            "")["action"] == "skip"
    # a failed sandbox test: the AI on its isolated branch, from main or from the candidate's commit
    plan = plan_tool.decide(security_run(), SANDBOX_JOB, "")
    assert (plan["action"], plan["push_branch"], plan["checkout"], plan["security"]) == (
        "fix", "automation/update/security-sandbox", "abc123", "true")
    plan = plan_tool.decide(security_run("automation/daily-maintenance"), SANDBOX_JOB, "")
    assert plan["push_branch"] == "automation/update/security-sandbox-daily-maintenance" and plan["action"] == "fix"
    waiting = {"automation/update/security-sandbox": "121"}
    assert plan_tool.decide(security_run(_security_prs=waiting), SANDBOX_JOB, "")["action"] == "skip"
    plan = plan_tool.decide(security_run("automation/update/security-sandbox", _attempts=2), SANDBOX_JOB, "")
    assert plan["action"] == "retry" and "nothing was weakened" in plan["reason"]     # again tomorrow
    plan = plan_tool.decide(security_run("automation/update/security-sandbox", _attempts=2, _attempts_today=0),
                            SANDBOX_JOB, "")
    assert plan["action"] == "fix" and plan["attempt"] == "3"
    # never a person's pull request, a fork or a branch that moved; never main itself
    for run in (security_run("fix/1.1.23"), security_run(head_repository={"full_name": "x/fork"}),
                security_run(_tip="newer")):
        assert plan_tool.decide(run, SANDBOX_JOB, "")["action"] == "skip"
    for run in (security_run(), security_run("automation/daily-maintenance"), security_run("automation/autofix-main")):
        for jobs in (SANDBOX_JOB, ADVISORY_JOB):
            plan = plan_tool.decide(dict(run, _advisories=found), jobs, "")
            assert plan["push_branch"] == "" or plan["push_branch"].startswith("automation/update/security-"), plan
            assert plan["security"] == "true"
    # a candidate that brings an advisory is blocked
    cand = plan_tool.decide(security_run("automation/daily-maintenance", _advisories=found), ADVISORY_JOB, "")
    assert cand["action"] == "issue" and "the candidate is blocked" in cand["reason"]
    # what reaches the assistants: the security rules (from main), the same for all
    assert "Never touch the engine's sandbox" in plan_tool.SECURITY_NOTE
    assert "deny.toml" in load("autofix-agent").security_note(True) and load("autofix-agent").security_note(False) == ""
    assert "deny.toml" in load("autofix-reserve").SECURITY_RULES


def test_the_security_workflows_are_wired():
    sec = (WORKFLOWS / "security.yml").read_text()
    hand = _jobs(sec)["hand-over"]
    assert "needs: [sandbox, rust-advisories]" in hand and "failure()" in hand
    assert "github.event_name != 'pull_request'" in hand and "startsWith(github.ref_name, 'automation/update/')" in hand
    assert re.search(r"permissions:\n\s+actions: write\n\s+steps:", hand)
    assert 'gh workflow run autofix.yml --ref main -f run_id="$RUN_ID"' in hand
    assert "python3 -I tools/security-fix.py check-ignores ike-adblock/deny.toml" in _jobs(sec)["rust-advisories"]
    assert set(plan_tool.REPORTING_JOBS["Security"]) >= {"hand-over", "advisories-issue", "sandbox-issue"}
    jobs = _jobs((WORKFLOWS / "autofix.yml").read_text())
    # the stricter guard for the agent, the reserves and the guard job
    assert 'if [ -f "$RUNNER_TEMP/security-finding" ]; then allow="$allow --security"; fi' in jobs["fix"]
    assert 'if [ "$SECURITY" = "true" ]; then touch "$RUNNER_TEMP/security-finding"; fi' in jobs["fix"]
    assert jobs["fix"].count('if [ "$SECURITY" = "true" ]; then allow="$allow --security"; fi') == 1
    assert 'if [ "$SECURITY" = "true" ]; then allow="$allow --security"; fi' in jobs["guard"]
    assert "security: ${{ steps.plan.outputs.security }}" in jobs["plan"]
    update = jobs["security-update"]
    assert "tools/security-fix.py apply" in update and "tools/security-fix.py verify" in update
    assert 'if [ "$changed" != "ike-adblock/Cargo.lock " ]' in update
    assert 'gh workflow run tests.yml --ref "$PUSH_BRANCH"' in update
    assert 'gh workflow run security.yml --ref "$PUSH_BRANCH"' in update
    assert "gh pr merge" not in update and "--draft" in update
    assert "needs.security-update.outputs.outcome != 'ready'" in jobs["report"]
    assert "tools/security-fix.py report" in jobs["publish"] and 'if [ "$KIND" = "security" ]' in jobs["publish"]
    tests = (WORKFLOWS / "tests.yml").read_text()
    # both hand-over clauses cover a security branch: the dispatch by its ref, a run
    # started again by its pull request's own branch (the drill of 2026-11-23)
    assert tests.count("startsWith(github.ref_name, 'automation/update/security-')") == 1
    assert tests.count("startsWith((github.head_ref || github.ref_name), 'automation/update/security-')") == 1


def _guard_repo(tmp_path):
    root = tmp_path / "g"
    files = {"ike/app.py": (ROOT / "ike/app.py").read_text(), "ike/window.py": "def width():\n    return 10\n",
             "tests/test_sandbox.py": "def test_on():\n    assert 1\n",
             "ike-adblock/deny.toml": (ROOT / "ike-adblock/deny.toml").read_text(),
             "tools/helper.py": "X = 1\n", "docs/SECURITY.md": "# Security\n"}
    for rel, text in files.items():
        write(root, rel, text)
    for args in (["init", "-q"], ["add", "-A"], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "b"]):
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
    return root


def _patch(root, rel, old, new):
    p = root / rel
    text = p.read_text()
    assert old in text, (rel, old)
    p.write_text(text.replace(old, new, 1))
    out = subprocess.run(["git", "-C", str(root), "diff"], check=True, capture_output=True, text=True).stdout
    subprocess.run(["git", "-C", str(root), "checkout", "-q", "--", "."], check=True)
    return out


def _check(root, tmp_path, patch, *extra):
    pf = tmp_path / "x.patch"
    pf.write_text(patch)
    report = tmp_path / "r.md"
    report.unlink(missing_ok=True)
    code = guard.main(["--repo", str(root), "--patch", str(pf), "--report", str(report), "--check-only", *extra])
    return code, report.read_text() if report.exists() else ""


def test_the_guard_never_lets_a_fix_touch_the_protections(tmp_path):
    """WP6: each rule of the stricter guard refuses its case (exit 3: no other assistant is asked), and an
    ordinary fix still passes."""
    root = _guard_repo(tmp_path)
    sandbox_off = _patch(root, "ike/app.py", '    "--no-sandbox", ', "    ")
    engine_safety = _patch(root, "ike/window.py", "    return 10\n", "    ENGINE_SAFETY['kept'] = []\n    return 10\n")
    new_switch = _patch(root, "ike/window.py", "    return 10\n",
                        "    os.environ['QTWEBENGINE_CHROMIUM_FLAGS'] = '--disable-web-security'\n    return 10\n")
    features = _patch(root, "ike/window.py", "    return 10\n",
                      "    f = '--disable-features=IsolateOrigins'\n    return 10\n")
    for patch in (sandbox_off, engine_safety, new_switch, features):
        for extra in ((), ("--security",)):                     # in every mode, not only for security findings
            code, text = _check(root, tmp_path, patch, *extra)
            assert code == 3 and "touches the engine's protections" in text, (patch, extra, text)
    # the switches are read from ike/app.py itself: one added there later is protected with no change here
    p = root / "ike/app.py"
    p.write_text(p.read_text().replace('    "--ip-address-space-overrides",\n',
                                       '    "--ip-address-space-overrides",\n    "--made-up-unsafe-switch",\n'))
    subprocess.run(["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "s"],
                   check=True)
    made_up = _patch(root, "ike/window.py", "    return 10\n", "    f = '--made-up-unsafe-switch'\n    return 10\n")
    assert _check(root, tmp_path, made_up)[0] == 3
    assert "--made-up-unsafe-switch" in guard.protection_terms(root)
    assert "--made-up-unsafe-switch" not in guard.protection_terms(tmp_path / "nowhere")
    assert {"--no-sandbox", "ENGINE_SAFETY", "--site-per-process"} <= guard.protection_terms(tmp_path / "nowhere")
    # deny.toml's ignores: a person's, in every mode, even with --allow-adblock
    ignore = _patch(root, "ike-adblock/deny.toml", "ignore = []",
                    'ignore = [{ id = "RUSTSEC-2021-0003", reason = "not called" }]')
    for extra in ((), ("--security",), ("--allow-adblock",)):
        code, text = _check(root, tmp_path, ignore, *extra)
        assert code == 3 and "an exception to a RustSec advisory is a person's" in text, extra
    # a fix of a security finding: never a security test, a protection named in any file, an advisory named
    sec_test = _patch(root, "tests/test_sandbox.py", "    assert 1\n", "    assert 1\n    assert len('ab') == 2\n")
    assert _check(root, tmp_path, sec_test)[0] == 0                    # an ordinary fix may correct it
    code, text = _check(root, tmp_path, sec_test, "--security")
    assert code == 3 and "a security test" in text
    doc = _patch(root, "docs/SECURITY.md", "# Security\n", "# Security\n\nRun it with --no-sandbox.\n")
    assert _check(root, tmp_path, doc)[0] == 0
    code, text = _check(root, tmp_path, doc, "--security")
    assert code == 3 and "touches the engine's protections" in text
    named = _patch(root, "tools/helper.py", "X = 1\n", "X = 1\nIGNORED = 'RUSTSEC-2021-0003'\n")
    assert _check(root, tmp_path, named)[0] == 0
    code, text = _check(root, tmp_path, named, "--security")
    assert code == 3 and "names a RustSec advisory" in text
    # an ordinary fix of I.K.E.'s code still passes under the security rules
    ordinary = _patch(root, "ike/window.py", "    return 10\n", "    return 12\n")
    assert _check(root, tmp_path, ordinary, "--security")[0] == 0
    # the reserves refuse the same files before the checker sees them, and check each fix with --security
    reserve = load("autofix-reserve")
    rule = reserve._checker_rule()
    assert rule("tests/test_sandbox.py", False, True) and not rule("tests/test_sandbox.py", False, False)
    (root / "tests/test_sandbox.py").write_text("def test_on():\n    assert 1\n    assert len('ab') == 2\n")
    checker = str(ROOT / "tools/check-autofix-patch.py")
    assert reserve.checked(root, checker, None, False, True)[0] == 3
    assert reserve.checked(root, checker, None, False)[0] == 0
    subprocess.run(["git", "-C", str(root), "checkout", "-q", "--", "."], check=True)
    # the security tests are those security.yml runs with the sandbox on (and they exist)
    named_in_workflow = set(re.findall(r"tests/test_\w+\.py", (WORKFLOWS / "security.yml").read_text()))
    assert named_in_workflow and named_in_workflow <= guard.SECURITY_TESTS
    assert all((ROOT / t).is_file() for t in guard.SECURITY_TESTS)
    assert (ROOT / guard.DENY_CONFIG).is_file() and (ROOT / guard.ENGINE_FILE).is_file()
    # today's ike/app.py: every list the guard names is there, with its switches
    terms = guard.protection_terms(ROOT)
    assert {"--no-sandbox", "--disable-web-security", "QTWEBENGINE_REMOTE_DEBUGGING", "localnetworkaccesschecks",
            "LocalNetworkAccessChecks", "--disable-gpu-sandbox", "--ip-address-space-overrides"} <= terms
    app = (ROOT / guard.ENGINE_FILE).read_text()
    assert all(re.search(r"^%s\s*=" % name, app, re.M) for name in guard.PROTECTION_LISTS)


def test_no_safe_fix_is_blocked_and_the_owner_is_told(fixture_repo):
    found = security_fix.parse(CARGO_DENY_LOG)
    nofix = [f for f in found if not f["fix"]]
    plan = plan_tool.decide(security_run(_advisories=nofix), ADVISORY_JOB, "")
    assert (plan["action"], plan["kind"]) == ("issue", "security") and plan["push_branch"] == ""
    assert "never ignored" in plan["reason"] and "RUSTSEC-2099-0001" in plan["reason"]
    # reported once: the next daily run finds the same open report
    report = [{"title": plan_tool.ISSUE_TITLE % "Security", "shas": ["abc123"], "reported_at": ""}]
    assert plan_tool.decide(security_run(_advisories=nofix), ADVISORY_JOB, "", report)["action"] == "skip"
    # findings that cannot be read are a person's, never a clean result
    assert plan_tool.decide(security_run(_advisories=None), ADVISORY_JOB, "")["action"] == "issue"
    # the deterministic update: no fix, or cargo cannot take it -> blocked with the reason
    lock_ = fixture_repo / "ike-adblock" / "Cargo.lock"
    lock_.write_text(lock(("adblock", "0.13.6"), ("smallvec", "1.6.0"), ("itoa", "1.0.0")))

    def cargo_ok(cmd, **kw):
        lock_.write_text(lock_.read_text().replace('"smallvec"\nversion = "1.6.0"', '"smallvec"\nversion = "1.6.1"'))
        return subprocess.CompletedProcess(cmd, 0, "", "")
    result = security_fix.apply(found, fixture_repo / "ike-adblock" / "Cargo.toml", run=cargo_ok)
    assert result["updates"] == [{"id": "RUSTSEC-2021-0003", "crate": "smallvec", "from": "1.6.0", "to": "1.6.1",
                                  "title": "Buffer overflow in SmallVec::insert_many",
                                  "url": "https://rustsec.org/advisories/RUSTSEC-2021-0003"}]
    assert [b["id"] for b in result["blocked"]] == ["RUSTSEC-2099-0001"]
    assert "no fixed version upstream" in result["blocked"][0]["reason"]
    failing = security_fix.apply(found[:1], fixture_repo / "ike-adblock" / "Cargo.toml",
                                 run=lambda cmd, **kw: subprocess.CompletedProcess(
                                     cmd, 101, "", "error: failed to select a version for `smallvec`"))
    assert failing["updates"] == [] and "a person" in failing["blocked"][0]["reason"]
    assert "failed to select a version" in failing["blocked"][0]["reason"]
    assert security_fix.verify(CARGO_DENY_LOG, ["RUSTSEC-2021-0003"]) == ["RUSTSEC-2021-0003"]
    assert security_fix.verify("advisories ok\n", ["RUSTSEC-2021-0003"]) == []
    # the ledger: the advisory with no fix is blocked, and the owner is told once, by name
    lock_.write_text(lock(("adblock", "0.13.6"), ("smallvec", "1.6.0"), ("itoa", "1.0.0")))
    status = {"security_main": {"url": "https://x/runs/9", "head_sha": "main1", "jobs": {
        "rust-advisories": {"conclusion": "failure"}, "sandbox": {"conclusion": "failure"}}},
              "security_findings": found}
    inv = take(fixture_repo, advisories=ledger_tool.advisories_of(status))
    assert ids(inv)["crate:itoa"]["advisories"][0]["id"] == "RUSTSEC-2099-0001"
    told = []
    ledger = ledger_tool.update(None, inv, status, now=DAY1, notices=told)
    e = ledger["entries"]
    assert e["crate:itoa@RUSTSEC-2099-0001"]["state"] == "blocked"
    assert e["crate:smallvec@RUSTSEC-2021-0003"]["state"] == "detected"
    assert "automation/update/security-rustsec-2021-0003" in e["crate:smallvec@RUSTSEC-2021-0003"]["reason"]
    assert e["security:sandbox@failing on main"]["state"] == "fixing"
    assert len(told) == 1 and "RUSTSEC-2099-0001" in told[0]
    assert ledger_tool.notice_text(told, "owner").startswith("@owner: ")
    assert not [k for k in e if k.startswith("crate:itoa@") and "RUSTSEC" not in k]      # one entry, not two
    # the isolated branch's checks: running, failed (the AI works), gave up (blocked, told), passed (the owner)
    branch = "automation/update/security-rustsec-2021-0003"

    def run_(conclusion, state="completed"):
        return {"status": state, "conclusion": conclusion, "url": "https://x/runs/10"}
    steps = [({"tests.yml": run_(None, "in_progress"), "security.yml": run_(None, "queued")}, {}, "testing"),
             ({"tests.yml": run_("failure"), "security.yml": run_("success")}, {"autofix_commits": 1}, "fixing"),
             ({"tests.yml": run_("failure"), "security.yml": run_("success")}, {"autofix_issue": "#130"}, "blocked"),
             ({"tests.yml": run_("success"), "security.yml": run_("success")}, {}, "passed")]
    for n, (runs, extra, state) in enumerate(steps):
        info = dict({"branch": branch, "pr": 131, "runs": runs, "autofix_commits": 0}, **extra)
        told = []
        ledger = ledger_tool.update(ledger, inv, dict(status, security_branches={branch: info}),
                                    now=DAY1 + dt.timedelta(hours=n + 1), notices=told)
        entry = ledger["entries"]["crate:smallvec@RUSTSEC-2021-0003"]
        assert entry["state"] == state, (state, entry["reason"])
        assert bool(told) == (state == "blocked")
    assert "the verified merge takes it (PR #131)" in entry["reason"]
    # the sandbox passes on main again and cargo-deny reports nothing: both are finished
    clean = {"security_main": {"url": "u", "head_sha": "main2", "jobs": {"rust-advisories": {"conclusion": "success"},
                                                                         "sandbox": {"conclusion": "success"}}}}
    ledger = ledger_tool.update(ledger, take(fixture_repo, advisories=ledger_tool.advisories_of(clean)), clean,
                                now=DAY2)
    assert ledger["entries"]["security:sandbox@failing on main"]["state"] == "passed"
    assert ledger["entries"]["crate:itoa@RUSTSEC-2099-0001"]["state"] == "passed"


def test_an_exception_needs_a_reason_a_person_wrote(tmp_path):
    """Never silenced by an ignore without a documented reason: security.yml fails on one."""
    assert security_fix.check_ignores((ROOT / "ike-adblock/deny.toml").read_text()) == []
    base = "[advisories]\nignore = [%s]\n"
    assert security_fix.check_ignores(base % '{ id = "RUSTSEC-2021-0003", reason = "the vulnerable function '
                                              'insert_many is never called by the engine" }') == []
    for bad in ('"RUSTSEC-2021-0003"', '{ id = "RUSTSEC-2021-0003" }', '{ id = "RUSTSEC-2021-0003", reason = "TODO" }',
                '{ id = "RUSTSEC-2021-0003", reason = "ok" }'):
        assert security_fix.check_ignores(base % bad), bad
    deny = tmp_path / "deny.toml"
    deny.write_text(base % '"RUSTSEC-2021-0003"')
    assert security_fix.main(["check-ignores", str(deny)]) == 1
    assert security_fix.main(["check-ignores", str(ROOT / "ike-adblock/deny.toml")]) == 0


def test_the_security_fix_pull_request_carries_the_report():
    found = security_fix.parse(CARGO_DENY_LOG)
    result = {"updates": [{"id": "RUSTSEC-2021-0003", "crate": "smallvec", "from": "1.6.0", "to": "1.6.1",
                           "title": "Buffer overflow"}], "blocked": [dict(found[1], reason="no fixed version upstream")]}
    body = security_fix.report(found, result, "automation/update/security-rustsec-2021-0003", "https://x/runs/1",
                               commits="abc1234 security: RUSTSEC-2021-0003\n")
    for section in ("## Security finding", "## What this candidate changes", "## Changes of the automatic fix",
                    "## Problems found", "## Tests on this commit", "## Security checks", "## Licences", "## Limits"):
        assert section in body, section
    assert "smallvec 1.6.0 -> 1.6.1" in body and "no AI" in body and "**Blocked**: RUSTSEC-2099-0001" in body
    assert "waits for the owner's order" in body and "Until then everything is **not verified**" in body
    ai = security_fix.report(autofix_of="Security", branch="automation/update/security-sandbox", summary="Fatto.",
                             guard="Patch accepted")
    assert "--security" in ai and "### Summary of the agent" in ai and "Read its change before merging" in ai
    assert security_fix.branch_for("RUSTSEC-2021-0003") == "automation/update/security-rustsec-2021-0003"
    assert security_fix.branch_for("sandbox-daily maintenance") == "automation/update/security-sandbox-daily-maintenance"


def test_no_agent_may_change_the_security_tools():
    ctx = load("autofix-context")
    for path in ("tools/security-fix.py", "tools/vulnerabilities.py"):
        assert path in guard.FORBIDDEN_FILES and path in ctx.NOT_RECENT, path
        assert guard.allowed_path(path, False) and guard.allowed_path(path, True, True), path
    assert "tools/security-fix.py or tools/vulnerabilities.py" in (WORKFLOWS / "autofix.yml").read_text()


def test_the_vulnerability_sources_are_documented():
    """ROADMAP: no external service beyond those documented in README.md."""
    readme, doc = (ROOT / "README.md").read_text(), (ROOT / "docs/MAINTENANCE.md").read_text()
    for host in ("api.osv.dev", "security.archlinux.org"):
        assert host in readme and host in doc, host
    for word in ("automation/update/security-", "--security", "check-ignores", "not checked", "blocked"):
        assert word in doc, word
    assert vulns.OSV_BATCH_URL.startswith("https://api.osv.dev/")
    assert vulns.ARCH_TRACKER_URL.startswith("https://security.archlinux.org/")


def test_a_run_that_never_ran_does_not_hide_the_real_one():
    """#107 (2026-11-22): the automation's dispatched Tests run passed; a "pull_request" run of the
    same commit, created in the same second with a higher id, waited for approval and never ran
    ("action_required", no jobs). It was taken as the newest run and every category read "not run".
    A run still in progress stays the newest: a newer real run in progress still wins."""
    sha = "8920f0182891080fb229a0b3a8b55ed8055da73b"
    real = {"id": 45035583278, "head_sha": sha, "status": "completed", "conclusion": "success",
            "created_at": "2026-11-22T14:56:55Z", "html_url": "u1", "event": "workflow_dispatch"}
    never = {"id": 45035583918, "head_sha": sha, "status": "completed", "conclusion": "action_required",
             "created_at": "2026-11-22T14:56:55Z", "html_url": "u2", "event": "pull_request"}
    jobs = {real["id"]: [{"id": 1, "name": "tests", "status": "completed", "conclusion": "success",
                          "steps": [{"name": "Lint", "conclusion": "success"}]}], never["id"]: []}

    def api(runs):
        def call(path):
            if "/runs?" in path:
                return {"workflow_runs": runs}
            return {"jobs": jobs.get(int(path.split("/runs/")[1].split("/")[0]), [])}
        return call
    info = ledger_tool.run_info("o/r", "tests.yml", api([real, never]), sha=sha)
    assert info["id"] == real["id"] and info["jobs"]["tests"]["steps"]["Lint"] == "success"
    assert ledger_tool.run_info("o/r", "tests.yml", api([never]), sha=sha) is None      # nothing ran
    # a newer real run still in progress wins over the finished one
    running = dict(real, id=45035999999, status="in_progress", conclusion=None, created_at="2026-11-22T16:00:00Z")
    jobs[running["id"]] = []
    assert ledger_tool.run_info("o/r", "tests.yml", api([real, never, running]), sha=sha)["id"] == running["id"]
