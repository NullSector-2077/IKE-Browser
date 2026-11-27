"""AUTOMAT block 2 (2026-11-27): PyQt's API compared from the type stubs of its wheels (tools/upstream-diff.py).

PyQt6 and PyQt6-WebEngine have no repository on GitHub, so "what changed upstream" was empty for a Qt update.
Offline: wheels made here, PyPI's answers stood in."""

import importlib.util
import io
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

OLD = '''
class QWebEnginePage:
    class Feature:
        Notifications = ...
        Geolocation = ...
    def setFeaturePermission(self, origin, feature, policy): ...
    def title(self): ...
class Gone: ...
'''
NEW = '''
class QWebEnginePage:
    class Feature:
        Notifications = ...
        Geolocation = ...
    def setPermission(self, origin, feature, policy): ...
    def title(self): ...
    def icon(self, size): ...
'''


def ud():
    spec = importlib.util.spec_from_file_location("stub_ud", ROOT / "tools" / "upstream-diff.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def wheel(text):
    raw = io.BytesIO()
    with zipfile.ZipFile(raw, "w") as z:
        z.writestr("PyQt6/QtWebEngineCore.pyi", text)
        z.writestr("PyQt6/QtWebEngineCore.abi3.so", b"\0binary, never read")
    return raw.getvalue()


def pypi(url):
    version = url.rstrip("/").split("/")[-2]
    return {"urls": [{"filename": "PyQt6_WebEngine-%s-cp39-abi3-win_amd64.whl" % version,
                      "url": "https://files.pythonhosted.org/win-%s.whl" % version},
                     {"filename": "PyQt6_WebEngine-%s-cp39-abi3-manylinux_2_28_x86_64.whl" % version,
                      "url": "https://files.pythonhosted.org/linux-%s.whl" % version}]}


def test_removed_added_and_the_sure_rename_are_found():
    u = ud()
    got = []

    def get_bytes(url):
        got.append(url)
        return wheel(OLD if "6.9.0" in url else NEW)
    data = u.stub_compare({"name": "PyQt6-WebEngine", "old": "6.9.0", "new": "6.10.0"}, pypi, get_bytes)
    assert got == ["https://files.pythonhosted.org/linux-6.9.0.whl", "https://files.pythonhosted.org/linux-6.10.0.whl"]
    assert data["removed"] == ["QtWebEngineCore.Gone", "QtWebEngineCore.QWebEnginePage.setFeaturePermission"]
    assert data["added"] == ["QtWebEngineCore.QWebEnginePage.icon", "QtWebEngineCore.QWebEnginePage.setPermission"]
    assert "renamed setFeaturePermission to setPermission" in data["notes"]
    assert u.rename_pairs([f["patch"] for f in data["files"]], data["notes"]) == [("setFeaturePermission",
                                                                                   "setPermission")]


def test_the_component_update_section_uses_the_stubs():
    u = ud()
    old_req, new_req = "PyQt6-WebEngine==6.9.0\n", "PyQt6-WebEngine==6.10.0\n"

    def show(rev, path):
        return old_req if rev == "origin/main" else new_req
    text, data = u.build("automation/update/test-qt", show, "AttributeError: 'QWebEnginePage' object has no "
                         "attribute 'setFeaturePermission'", pypi, get_bytes=lambda url: wheel(
                             OLD if "6.9.0" in url else NEW))
    assert "setFeaturePermission -> setPermission" in text and "PyPI wheels" in text
    assert data["changes"][0]["renames"] == [["setFeaturePermission", "setPermission"]]


def test_only_pythonhosted_is_read_as_bytes():
    u = ud()
    for url in ("https://example.org/x.whl", "http://files.pythonhosted.org/x.whl"):
        try:
            u.fetch_bytes(url)
        except ValueError:
            continue
        raise AssertionError(url)
