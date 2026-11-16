"""The Linux packages (PKGBUILD, packaging/debian, packaging/rpm) agree with
each other and with the program: one version, the same files installed in
the same places, the dependencies I.K.E. needs, no key or personal data."""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def version():
    return re.search(r'^__version__ = "([^"]+)"', (ROOT / "ike/__init__.py").read_text("utf-8"), re.M).group(1)


def test_one_version_everywhere():
    v = version()
    assert re.search(r"^pkgver=%s$" % re.escape(v), (ROOT / "PKGBUILD").read_text("utf-8"), re.M)
    deb = (ROOT / "packaging/debian/changelog").read_text("utf-8").splitlines()[0]
    assert deb.startswith("ike-browser (%s-" % v), deb
    spec = (ROOT / "packaging/rpm/ike-browser.spec").read_text("utf-8")
    assert re.search(r"^Version: +%s$" % re.escape(v), spec, re.M)


def test_dependencies_cover_what_the_code_imports():
    control = (ROOT / "packaging/debian/control").read_text("utf-8")
    spec = (ROOT / "packaging/rpm/ike-browser.spec").read_text("utf-8")
    pkgbuild = (ROOT / "PKGBUILD").read_text("utf-8")
    for need in ("python3-pyqt6", "python3-pyqt6.qtwebengine", "python3-cryptography", "python3-jeepney",
                 "libqt6webenginecore6 (>= 6.8)", "qt6-svg-plugins"):
        assert need in control, need
    for need in ("python3-pyqt6", "python3-pyqt6-webengine", "qt6-qtwebengine >= 6.8", "qt6-qtsvg",
                 "python3-cryptography", "python3-jeepney"):
        assert re.search(r"^Requires: +%s$" % re.escape(need), spec, re.M), need
    for need in ("python-pyqt6-webengine", "python-cryptography", "python-jeepney"):
        assert need in pkgbuild, need
    # no codec, no FFmpeg among what I.K.E. itself depends on
    for text in (control, spec):
        assert "ffmpeg" not in text.lower() and "openh264" not in text.lower()


def test_install_layout_matches_the_arch_package(tmp_path):
    """tools/install-linux.sh (DEB and RPM) installs what the PKGBUILD's
    package() does, in the same places."""
    engine = tmp_path / "libike_adblock.so"
    engine.write_bytes(b"\x7fELF engine")
    launcher = tmp_path / "launcher"
    launcher.write_bytes(b"\x7fELF launcher")
    dest = tmp_path / "root"
    subprocess.run(["sh", "tools/install-linux.sh", str(dest), str(engine), str(launcher),
                    "/usr/share/licenses/ike-browser", "/usr/share/doc/ike-browser"],
                   cwd=ROOT, check=True)
    lib = dest / "usr/lib/ike-browser"
    for rel in ("ike_boot.py", "update.json", "vendor/adblock/__init__.py",
                "vendor/adblock/ike_adblock.abi3.so", "ike/__init__.py", "ike/resources/newtab.html"):
        assert (lib / rel).is_file(), rel
    assert (dest / "usr/bin/ike-browser").read_bytes() == launcher.read_bytes()
    assert (dest / "usr/share/applications/ike-browser.desktop").is_file()
    for size in (48, 64, 128, 256, 512):
        assert (dest / ("usr/share/icons/hicolor/%dx%d/apps/ike-browser.png" % (size, size))).is_file()
    assert (dest / "usr/share/icons/hicolor/scalable/apps/ike-browser.svg").is_file()
    assert (dest / "usr/share/licenses/ike-browser/LICENSE").is_file()
    assert (dest / "usr/share/licenses/ike-browser/THIRD-PARTY.md").is_file()
    assert (dest / "usr/share/doc/ike-browser/CHANGELOG.md").is_file()
    # the same Python files as the repository, no caches, no test data
    repo = sorted(p.relative_to(ROOT / "ike").as_posix() for p in (ROOT / "ike").rglob("*")
                  if p.is_file() and "__pycache__" not in p.parts)
    inst = sorted(p.relative_to(lib / "ike").as_posix() for p in (lib / "ike").rglob("*") if p.is_file())
    assert inst == repo
    everything = [p for p in dest.rglob("*") if p.is_file()]
    assert not [p for p in everything if p.suffix in (".key", ".pem", ".mp4", ".m4a", ".webm")]
    # the same paths as the PKGBUILD names
    pkgbuild = (ROOT / "PKGBUILD").read_text("utf-8")
    for path in ("vendor/adblock/ike_adblock.abi3.so", "/usr/share/applications/ike-browser.desktop",
                 "/usr/share/pixmaps/ike-browser.png", "update.json"):
        assert path.lstrip("/").split("/")[-1] in pkgbuild


def test_debian_rules_and_spec_use_the_shared_installer():
    rules = (ROOT / "packaging/debian/rules").read_text("utf-8")
    spec = (ROOT / "packaging/rpm/ike-browser.spec").read_text("utf-8")
    assert "tools/install-linux.sh" in rules and "tools/install-linux.sh" in spec
    assert "\n\tcargo build --release --locked" in rules and "cargo build --release --locked" in spec
    # rules is a makefile: recipe lines start with a tab
    assert all(not line.startswith("    ") for line in rules.splitlines() if line.strip()
               and not line.startswith(("#", "\t", "%", "export", "override_")))
