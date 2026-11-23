"""tools/publish.py, the owner's one command to sign and publish (no network).

The versions read from ike/__init__.py and the PKGBUILD, the package name with
its pkgrel (1.1.10-3, not always -1), the release notes taken from CHANGELOG.md,
the state of the "tests" check on GitHub, and the read-back of the published
files with a real Ed25519 key: a wrong signature, version or hash stops it.
"""

import base64
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
cryptography = pytest.importorskip("cryptography")
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat  # noqa: E402


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


publish = load("publish", ROOT / "tools" / "publish.py")
make_release = load("make_release", ROOT / "tools" / "make-release.py")


def test_versions_of_this_repository_agree():
    version, pkgver, pkgrel = publish.versions(ROOT)
    assert version == pkgver and pkgrel.isdigit()


def test_package_name_keeps_the_pkgrel():
    assert publish.package_name("1.1.10", "3") == "ike-browser-1.1.10-3-x86_64.pkg.tar.zst"


def test_release_notes_are_the_version_section():
    log = "# Changelog\n\n## 1.1.11\n\n- Fix A.\n- Fix B.\n\n## 1.1.10\n\n- Old.\n"
    assert publish.release_notes(log, "1.1.11") == "- Fix A.\n- Fix B.\n"
    assert publish.release_notes(log, "1.1.10") == "- Old.\n"
    with pytest.raises(publish.Stop):
        publish.release_notes(log, "1.1.12")
    with pytest.raises(publish.Stop):
        publish.release_notes("# Changelog\n\n## 1.1.12\n\n## 1.1.11\n- x\n", "1.1.12")
    # the real CHANGELOG has a section for the current version
    version = publish.versions(ROOT)[0]
    assert publish.release_notes((ROOT / "CHANGELOG.md").read_text("utf-8"), version).strip()


@pytest.mark.parametrize("runs,state", [
    ([{"name": "tests", "status": "completed", "conclusion": "success"}], "ok"),
    ([{"name": "tests", "status": "completed", "conclusion": "failure"},
      {"name": "tests", "status": "completed", "conclusion": "success"}], "ok"),
    ([{"name": "tests", "status": "in_progress", "conclusion": None}], "running"),
    ([{"name": "tests", "status": "completed", "conclusion": "failure"}], "failed"),
    ([{"name": "tests", "status": "completed", "conclusion": "cancelled"}], "failed"),
    ([{"name": "build", "status": "completed", "conclusion": "success"}], "missing"),
    ([], "missing"),
])
def test_state_of_the_tests_on_github(runs, state):
    assert publish.tests_passed(runs) == state


def test_published_files_are_read_back(tmp_path):
    key = Ed25519PrivateKey.generate()
    pub = base64.b64encode(key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode()
    payload = b"the ike folder"
    manifest = (json.dumps({"version": "1.1.11", "payload": "ike-1.1.11.tar.gz",
                            "sha256": hashlib.sha256(payload).hexdigest()}) + "\n").encode()
    sig = base64.b64encode(key.sign(manifest)).decode()
    publish.check_published(manifest, sig + "\n", payload, "1.1.11", pub, make_release.verify)

    with pytest.raises(publish.Stop, match="firma"):
        publish.check_published(manifest.replace(b"1.1.11", b"1.1.12"), sig, payload, "1.1.11",
                                pub, make_release.verify)
    with pytest.raises(publish.Stop, match="versione"):
        publish.check_published(manifest, sig, payload, "1.1.12", pub, make_release.verify)
    with pytest.raises(publish.Stop, match="hash"):
        publish.check_published(manifest, sig, b"something else", "1.1.11", pub, make_release.verify)
    other = base64.b64encode(Ed25519PrivateKey.generate().public_key().public_bytes(
        Encoding.Raw, PublicFormat.Raw)).decode()
    with pytest.raises(publish.Stop, match="firma"):
        publish.check_published(manifest, sig, payload, "1.1.11", other, make_release.verify)


def test_nothing_secret_and_no_force():
    text = (ROOT / "tools" / "publish.py").read_text("utf-8")
    assert "--force" not in text and "push" not in text       # it never writes to the repository
    assert "--target" in text and "--dry-run" in text
    # the private key is only handed to make-release.py, never read here
    assert "load_key" not in text and "read_bytes" not in text


def test_each_check_is_asked_by_its_name():
    """1.1.23: a commit of main carried 112 checks; the first 100 held no "tests", and the
    publication stopped with "not started" although the tests had passed. Each check is now
    asked by its own name."""
    path = publish.check_runs_path("a" * 40, "tests")
    assert "check_name=tests" in path and "/commits/" + "a" * 40 + "/check-runs" in path
    assert "check_name=sandbox" in publish.check_runs_path("a" * 40, "sandbox")
    src = (publish.ROOT / "tools" / "publish.py").read_text("utf-8")
    assert "check-runs?per_page=100\" % (REPO, sha)" not in src
