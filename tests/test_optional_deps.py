"""The PKGBUILD's optional dependencies, each with a targeted test (WP10 (e), 2026-11-22).

An optional dependency is used by I.K.E. only when the user installed it.
Each one in the PKGBUILD's optdepends gets a test that runs where the package
is installed (arch.yml installs those Arch ships; pacman knows them) and checks
what I.K.E. uses of it. Where it is not installed the test is skipped with the
words "not verified": never "incompatible", never passed. A package added to
optdepends later (tools/pkgbuild-sync.py) is tested at least by pacman's own
check of its files, with no change here.
"""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
# the Arch packages no GitHub check can install (the AUR): said as never verified here
AUR = {"chromium-widevine"}


def optdepends():
    """The package names of the PKGBUILD's optdepends, in order."""
    text = (ROOT / "PKGBUILD").read_text("utf-8")
    m = re.search(r"^optdepends=\(", text, re.M)
    words, quote, word = [], "", ""
    for ch in text[m.end():] if m else "":
        if quote:
            quote, word = ("", word) if ch == quote else (quote, word + ch)
        elif ch in "'\"":
            quote = ch
        elif ch.isspace() or ch == ")":
            if word:
                words.append(word)
            word = ""
            if ch == ")":
                break
        else:
            word += ch
    return [re.split(r"[<>=:]", w, maxsplit=1)[0].strip() for w in words]


def installed(package):
    """True when pacman has the package (Arch, arch.yml); False elsewhere (Ubuntu's Tests)."""
    if not shutil.which("pacman"):
        return False
    return subprocess.run(["pacman", "-Qq", package], capture_output=True, check=False).returncode == 0


def not_verified(package):
    where = ("an AUR package: no check of GitHub installs it" if package in AUR
             else "an Arch package: arch.yml installs it and runs this test")
    pytest.skip("optional dependency %s is not installed here (%s): not verified" % (package, where))


def _fc(*args):
    if not shutil.which("fc-list"):
        return ""
    return subprocess.run(["fc-list", *args], capture_output=True, text=True, check=False).stdout


# what I.K.E. uses of each optional dependency it names (ike/ and the PKGBUILD's reasons)
def check_libnotify():
    """ike/osinfo.py notify(): the notification is sent with notify-send."""
    path = shutil.which("notify-send")
    assert path, "notify-send is not on the PATH"
    assert "notify-send" in (ROOT / "ike" / "osinfo.py").read_text("utf-8")


def check_noto_fonts_cjk():
    """Chinese, Japanese and Korean text: fontconfig finds a Noto CJK font."""
    assert "CJK" in _fc(":lang=ja", "family"), "no Noto CJK font for Japanese"


def check_noto_fonts():
    """The other scripts: fontconfig finds Noto Sans and a Noto font for Arabic."""
    families = _fc(":", "family")
    assert "Noto Sans" in families
    assert "Noto" in _fc(":lang=ar", "family"), "no Noto font for Arabic"


def check_plasma_integration():
    """KDE's own platform theme for Qt 6 (colours and file dialogs)."""
    found = list(Path("/usr/lib/qt6/plugins/platformthemes").glob("KDEPlasmaPlatformTheme*.so"))
    assert found, "KDE's platform theme plugin for Qt 6 is not there"


def check_chromium_widevine():
    """ike/drm.py: the system-wide Widevine library is the one I.K.E. finds."""
    from ike import drm
    assert "/usr/lib/chromium-widevine/libwidevinecdm.so" in drm.SYSTEM_LIBS
    assert Path("/usr/lib/chromium-widevine/libwidevinecdm.so").is_file()


def check_libva_nvidia_driver():
    """Video decoding with NVIDIA cards: its VA-API driver is where libva looks."""
    assert list(Path("/usr/lib/dri").glob("nvidia_drv_video.so")), "nvidia_drv_video.so is not in /usr/lib/dri"


def check_intel_media_driver():
    """Video decoding with Intel cards: its VA-API driver is where libva looks."""
    assert list(Path("/usr/lib/dri").glob("iHD_drv_video.so")), "iHD_drv_video.so is not in /usr/lib/dri"


CHECKS = {
    "libnotify": check_libnotify,
    "noto-fonts-cjk": check_noto_fonts_cjk,
    "noto-fonts": check_noto_fonts,
    "plasma-integration": check_plasma_integration,
    "chromium-widevine": check_chromium_widevine,
    "libva-nvidia-driver": check_libva_nvidia_driver,
    "intel-media-driver": check_intel_media_driver,
}


def test_every_optional_dependency_is_read_from_the_pkgbuild():
    """The tests below follow the PKGBUILD: each optional dependency is one case."""
    names = optdepends()
    assert names and len(names) == len(set(names))
    assert set(CHECKS) <= set(names) | {"noto-fonts"}, set(CHECKS) - set(names)


@pytest.mark.parametrize("package", optdepends())
def test_an_optional_dependency_where_it_is_installed(package):
    """Where the package is installed: what I.K.E. uses of it works, and pacman finds all its files.
    Where it is not: not verified (a skip that says so), never "incompatible"."""
    if not installed(package):
        not_verified(package)
    done = subprocess.run(["pacman", "-Qk", package], capture_output=True, text=True, check=False)
    assert done.returncode == 0 and " 0 missing files" in done.stdout, done.stdout + done.stderr
    check = CHECKS.get(package)
    if check is not None:
        check()


def test_absent_is_not_verified_never_incompatible(monkeypatch):
    """The skip of an absent package says "not verified", never that it fails or is incompatible."""
    monkeypatch.setattr(shutil, "which", lambda name: None)
    assert installed("libnotify") is False
    with pytest.raises(pytest.skip.Exception) as e:
        not_verified("libnotify")
    assert "not verified" in str(e.value) and "incompatible" not in str(e.value)
    with pytest.raises(pytest.skip.Exception) as e:
        not_verified("chromium-widevine")
    assert "AUR" in str(e.value) and "not verified" in str(e.value)
