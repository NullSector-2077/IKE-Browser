"""The I.K.E. brand: the logo and its icon files, the full name on the new tab
page, and no trace of an earlier name in the repository."""

import hashlib
import os
import re
import struct
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = Path(os.environ.get("IKE_TEST_APP") or ROOT)
SHOTS = os.environ.get("IKE_TEST_SHOTS", "")
OLD_NAME = re.compile(r"I\.C\.E|\bICE\b|\bIce\b|\bice[-_.:]\w")
SMALL = (16, 22, 24, 32, 48, 64)
# Hashes of the approved assets as supplied by the project owner.
ASSET_SHA256 = {'ike.svg': 'a268eb2d75fb19e53eb6b63381f2fcdec55ab4a86c54d3fc1c14517b30d0c6b9',
 'newtab-background.webp': '1a19c03e487fe347e80aea413cf8fc71d85811523904a6e96c93c37aa1d50583',
 'wordmark.svg': 'f99217d41284572167342b11490ee23cf1b48af2e6512e13e316ab48e1d36b50'}
PNG_SHA256 = {16: 'f2fde5e746d450cf8794d28c68cf9af975be29eb589ff5c55a1a487d6bcce0fb',
 22: 'd7a6c8c16f717d3539823e17e1e4afed17b5c3369265acde5cd9af8db7aa73e7',
 24: '1a847b49354ce19288f90ee8473207612ea483df5a68d79c4ff1ad4bc102c256',
 32: 'e9b7da9029c9a8a90442cbd76eb7a22e4abdb3a2eb9f751266199c8aecac946b',
 48: '43a02226294bb7fc3904853316c02534d8ace48de4f05f74a54f25e7d8402ce7',
 64: '2d52b07ed868a0612bf862fce273ab37cac96a7f4f45e232e66c85ca0c6484ad',
 128: 'dd1d424d5a524c05ad0dd1bf9455927eadbdf7d246433195536d309cda26cd13',
 256: '359807342ae6e19d106c21143ee9ce89a6496a4e41434c300064b072a90574e5',
 512: 'ca54e00be6156e8aaa02e771a9c6e71d6f51fe6c08c07ef8cf1ecacb048e9a3d',
 1024: 'eaaf64202dedf8b54ffb9d4159b0b85b4180faf6a44af1cbb16c2eb95f26ab48'}
SMALL_SVG_SHA256 = {16: 'dad111dad1910c879cd863ff7920a128c46bdfddd6bedc042c5865ebf1f5fd27',
 22: 'f195cfa9a7349271f7fd1f01fe36e8dd14b4acbf3ff92d389ac5bf5a7a8a43f9',
 24: '66efd4d07200fc1cfc9c66ad45cbdc71fd232992d436e69a10d64b2ee42e89a2',
 32: 'bdaef919979fa48ff7f92a21c28feb765eb04dc9b310cb4640eb74eaefffa6d7',
 48: '1b5843c40864570f14f29bc385c4f719ed59391f0facfc2bc80251112152e198',
 64: '1ec02fe49fdcf2e154f370dde5167b84818b39aa6e526c6974c1886b2ef7335f'}
# files of other projects, where the three letters mean something else
THIRD_PARTY = ("ike/resources/darkreader.js", "ike/resources/darkreader-proxy.js", "ike/resources/darkreader-data.json", "ike/resources/ubo-scriptlets.json", "ike-adblock/Cargo.lock",
               "ike/resources/icons/sets/")


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_approved_brand_files():
    from xml.etree import ElementTree

    resources = APP / "ike/resources"
    for name, expected in ASSET_SHA256.items():
        assert sha256(resources / name) == expected, name
    assert not (resources / "newtab-background.jpg").exists()
    for name in ("ike.svg", "wordmark.svg"):
        root = ElementTree.parse(resources / name).getroot()
        assert root.tag.endswith("}svg")
        assert not any(e.tag.endswith("}text") for e in root.iter())
    if APP == ROOT:
        assert sha256(ROOT / "data/icons/ike-browser.svg") == ASSET_SHA256["ike.svg"]
        for n, expected in SMALL_SVG_SHA256.items():
            assert sha256(ROOT / "data/icons/small" / ("ike-browser-%d.svg" % n)) == expected


def test_window_icons_use_the_approved_size_variants(run_ike):
    for n, expected in PNG_SHA256.items():
        paths = [APP / "ike/resources/icons" / ("ike-browser-%d.png" % n)]
        if APP == ROOT:
            paths.append(ROOT / "data/icons" / ("ike-browser-%d.png" % n))
        for png in paths:
            head = png.read_bytes()[:24]
            assert head[:8] == b"\x89PNG\r\n\x1a\n" and struct.unpack(">II", head[16:24]) == (n, n)
            assert sha256(png) == expected, png

    out = run_ike("""
        from PyQt6.QtCore import QSize
        from PyQt6.QtGui import QImage

        PREMUL = QImage.Format.Format_ARGB32_Premultiplied

        def steps(ike, qapp, out):
            yield 300
            from ike.app import ICON_SIZES
            from ike.config import RES_DIR
            out["sizes"] = list(ICON_SIZES)
            for name, icon in (("app", ike.icon), ("qapp", qapp.windowIcon()),
                               ("window", ike.windows[0].windowIcon())):
                out[name] = sorted(s.width() for s in icon.availableSizes())
                same = {}
                for n in ICON_SIZES:
                    shown = icon.pixmap(QSize(n, n)).toImage().convertToFormat(PREMUL)
                    own = QImage(str(RES_DIR / "icons" / ("ike-browser-%d.png" % n))).convertToFormat(
                        PREMUL)
                    same[n] = shown == own
                out[name + "_same"] = same
    """)
    every = sorted(PNG_SHA256)
    assert out["sizes"] == every
    for name in ("app", "qapp", "window"):
        assert out[name] == every, (name, out[name])
        # at each size the picture drawn for it, not a scaled one
        assert all(out[name + "_same"].values()), (name, out[name + "_same"])


def test_package_installs_every_icon_size(tmp_path):
    """PKGBUILD puts every size in the desktop's icon theme (hicolor), the small
    drawings included, so a panel at 16, 22, 24 or 32 px takes them (1.1.23).
    package() runs with `install` and the other commands only written down."""
    log = tmp_path / "install.log"
    script = r'''
        set -e
        source ./PKGBUILD
        install() { printf '%s\n' "$*" >> "$LOG"; }
        cp() { :; }
        find() { :; }
        rustc() { echo /nonexistent; }
        startdir="$PWD" srcdir=/nonexistent-src pkgdir=/nonexistent-pkg
        package
    '''
    subprocess.run(["bash", "-c", script], cwd=ROOT, check=True, capture_output=True,
                   env={**os.environ, "LOG": str(log)})
    lines = log.read_text("utf-8").splitlines()
    every = sorted(SMALL + (128, 256, 512))
    for n in every:
        assert ("-Dm644 data/icons/ike-browser-%d.png "
                "/nonexistent-pkg/usr/share/icons/hicolor/%dx%d/apps/ike-browser.png" % (n, n, n)) in lines, n
        assert (ROOT / "data/icons" / ("ike-browser-%d.png" % n)).is_file()
    assert ("-Dm644 data/icons/ike-browser.svg "
            "/nonexistent-pkg/usr/share/icons/hicolor/scalable/apps/ike-browser.svg") in lines
    # an installed copy (the package's own tests): the same pictures are there
    share = APP.parent.parent / "share/icons/hicolor"
    if APP != ROOT and share.is_dir():
        for n in every:
            installed = share / ("%dx%d" % (n, n)) / "apps/ike-browser.png"
            assert sha256(installed) == sha256(ROOT / "data/icons" / ("ike-browser-%d.png" % n)), n


def test_new_tab_shows_the_brand(run_ike):
    out = run_ike("""
        import os

        def js(view, code, out, key):
            view.page().runJavaScript(code, lambda v: out.__setitem__(key, v))

        def steps(ike, qapp, out):
            yield 1500
            win = ike.windows[0]
            view = win.current_view()
            out["url"] = view.url().toString()
            js(view, '''(function () {
                var mark = document.querySelector("h1 img"), img = document.querySelector(".logo");
                var r = mark.getBoundingClientRect(), emblem = img.getBoundingClientRect();
                return {label: mark.alt, w: r.width, h: r.height, left: r.left, right: r.right, page: innerWidth,
                        logoCentre: (emblem.left + emblem.right) / 2,
                        wordmark: mark.complete && mark.naturalWidth && mark.getAttribute("src"),
                        logo: img.complete && img.naturalWidth && img.getAttribute("src"), alt: img.alt,
                        title: document.title, text: document.body.innerText,
                        template: document.documentElement.outerHTML.indexOf("{{") >= 0,
                        fonts: Array.from(document.fonts || []).length};
            })()''', out, "page")
            yield 500
            shots = os.environ.get("IKE_TEST_SHOTS")
            if shots:
                win.grab().save(os.path.join(shots, "newtab-brand.png"))
            from ike import APP_LONG_NAME, APP_NAME
            out["names"] = [APP_NAME, APP_LONG_NAME, qapp.applicationDisplayName()]
            from ike import newtabbg
            out["bg"] = [newtabbg.probe(newtabbg.DEFAULT_FILE)[0], newtabbg.content(ike.config)[1].decode()]
            from PyQt6.QtWidgets import QLabel
            dialog = win.about_dialog()
            out["about_mark"] = any(label.accessibleName() == APP_LONG_NAME and not label.pixmap().isNull()
                                    for label in dialog.findChildren(QLabel))
    """, settings={"newtab_bg": "default"}, env={"IKE_TEST_SHOTS": SHOTS})
    page = out["page"]
    assert out["url"].startswith("ike:")
    assert page["label"] == "Internet Kontrol Experience"
    assert page["w"] > 250 and abs(page["w"] / page["h"] - 1834 / 160) < 0.02
    # centred, inside the page
    assert page["left"] > 0 and page["right"] < page["page"]
    assert abs((page["left"] + page["right"]) / 2 - page["page"] / 2) <= 1.5
    assert abs(page["logoCentre"] - page["page"] / 2) <= 1.5
    assert page["logo"] == "ike:logo" and page["alt"] == "I.K.E." and page["title"] == "I.K.E."
    assert page["wordmark"] == "ike:wordmark" and out["about_mark"]
    assert out["bg"] == [[3840, 2160], "image/webp"]
    assert not page["template"] and page["fonts"] == 0
    assert out["names"] == ["I.K.E.", "I.K.E. - Internet Kontrol Experience", "I.K.E."]


def test_no_earlier_name_left():
    if APP != ROOT or not (ROOT / ".git").exists():
        files = [p for p in (APP / "ike").rglob("*") if p.is_file() and "__pycache__" not in p.parts]
        rel = lambda p: "ike/" + p.relative_to(APP / "ike").as_posix()      # noqa: E731
    else:
        names = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout
        files = [ROOT / n for n in names.decode().split("\0") if n and (ROOT / n).is_file()]
        rel = lambda p: p.relative_to(ROOT).as_posix()                       # noqa: E731
    found = []
    for path in files:
        name = rel(path)
        if name.startswith(THIRD_PARTY) or name == "tests/test_brand.py":
            continue
        if OLD_NAME.search(name):
            found.append(name)
        try:
            text = path.read_text("utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        found += ["%s:%d" % (name, i) for i, line in enumerate(text.splitlines(), 1) if OLD_NAME.search(line)]
    assert not found, found
    assert not (APP / "ike/legacy.py").exists()


def test_new_tab_and_home_at_desktop_resolutions(run_ike, tmp_path):
    import textwrap

    from conftest import screen
    from test_security import JS

    out = run_ike(JS + textwrap.dedent("""
        import os
        from PyQt6.QtCore import QUrl

        def steps(ike, qapp, out):
            win = ike.windows[0]
            win.showNormal()
            view = win.current_view()
            yield 700
            view.load(QUrl("about:blank"))
            yield 250
            win.act_home.trigger()
            yield 550
            out["home"] = view.url().toString()
            win.act_reload.trigger()
            yield 500
            out["reloaded"] = view.url().toString()
            win.act_new_tab.trigger()
            view = win.current_view()
            yield 650

            out["views"] = []
            for width, height in ((1920, 1080), (2560, 1440), (3840, 2160), (3440, 1440)):
                win.resize(width, height)
                view.reload()
                for _ in range(12):
                    yield 350
                    check = yield from js(view, '''(() => {
                      const mark = document.querySelector("h1 img");
                      const logo = document.querySelector(".logo");
                      if (!mark || !logo || !mark.complete || !logo.complete) return null;
                      const css = getComputedStyle(document.documentElement);
                      const box = mark.getBoundingClientRect();
                      const img = logo.getBoundingClientRect();
                      return [innerWidth, innerHeight, css.backgroundSize, css.backgroundImage,
                              box.x + box.width / 2, img.x + img.width / 2, box.width / box.height, img.width / img.height];
                    })()''')
                    if check and check[0] == width:
                        break
                yield 400
                out["views"].append(check)
                shots = os.environ.get("IKE_TEST_SHOTS")
                if shots:
                    win.grab().save(os.path.join(shots, f"newtab-{width}x{height}.png"))
    """), settings={
        "newtab_bg": "default", "newtab_bg_fit": "fill", "start_maximized": False, "ui_scheme": "theme:ike"
    }, env=screen(tmp_path, 4300, 2400) | {"IKE_TEST_SHOTS": SHOTS})
    assert out["home"] == out["reloaded"] == "ike:newtab"
    for expected, result in zip((1920, 2560, 3840, 3440), out["views"]):
        width, height, fit, background, word_centre, logo_centre, word_ratio, logo_ratio = result
        assert width == expected and height >= 950
        assert "cover" in fit and "ike:background?" in background
        assert abs(word_centre - width / 2) <= 1 and abs(logo_centre - width / 2) <= 1
        assert abs(word_ratio - 1834 / 160) < 0.02 and logo_ratio == 1
