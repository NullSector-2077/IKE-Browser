"""One version everywhere (Arch-first cleanup, 2026-11-20). ike/__init__.py is
the single source; the files that repeat it (PKGBUILD, README, CHANGELOG) must
say the same, as tools/prepare-maintenance.py writes them."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _version():
    text = (ROOT / "ike" / "__init__.py").read_text("utf-8")
    return re.search(r'^__version__ = "([0-9]+\.[0-9]+\.[0-9]+)"$', text, re.M).group(1)


def _key(v):
    return tuple(int(x) for x in v.split("."))


def test_pkgbuild_has_the_version():
    text = (ROOT / "PKGBUILD").read_text("utf-8")
    assert re.search(r"^pkgver=(.+)$", text, re.M).group(1) == _version()
    assert re.search(r"^pkgrel=([0-9]+)$", text, re.M)


def test_readme_has_the_version():
    text = (ROOT / "README.md").read_text("utf-8")
    v = _version()
    assert "**Version %s**" % v in text
    named = set(re.findall(r"ike-browser-([0-9]+\.[0-9]+\.[0-9]+)-[0-9]+-x86_64\.pkg\.tar\.zst", text))
    assert named <= {v}, named              # an install command names this version or none


def test_changelog_starts_with_the_version_and_goes_down():
    text = (ROOT / "CHANGELOG.md").read_text("utf-8")
    heads = re.findall(r"^## ([0-9]+\.[0-9]+\.[0-9]+)\b", text, re.M)
    assert heads and heads[0] == _version(), heads[:3]
    assert len(heads) == len(set(heads)), "a version twice in CHANGELOG.md"
    keys = [_key(h) for h in heads]
    assert keys == sorted(keys, reverse=True), "CHANGELOG.md versions out of order"


def test_min_system_is_not_newer_than_the_version():
    text = (ROOT / "ike" / "__init__.py").read_text("utf-8")
    low = re.search(r'^__min_system__ = "([0-9]+\.[0-9]+\.[0-9]+)"$', text, re.M).group(1)
    assert _key(low) <= _key(_version())
