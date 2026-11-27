"""The I.K.E. brand: the logo and its icon files, the full name on the new tab
page, and no trace of an earlier name in the repository."""

import hashlib
import os
import re
import struct
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
APP = Path(os.environ.get("IKE_TEST_APP") or ROOT)
SHOTS = os.environ.get("IKE_TEST_SHOTS", "")
OLD_NAME = re.compile(r"I\.C\.E|\bICE\b|\bIce\b|\bice[-_.:]\w")
# Hashes of the approved assets as supplied by the project owner (16, 22 and 24 px
# redrawn on 2026-11-27 at the owner's request: I K E inside the octagon, not a plain dot).
ASSET_SHA256 = {'ike.svg': '02e809d5688cb12c5ff858b54dd29c03a9ddd6bf0bdc1f6a52c58198d84ab1aa',
 'newtab-background.webp': '1a19c03e487fe347e80aea413cf8fc71d85811523904a6e96c93c37aa1d50583',
 'newtab-preview.png': '8f4ff86982dc2dcaa94b360831e73aba5f4122369dd89023d5116aa8b322f6fd',
 'wordmark.svg': '243492fe1eef8d65fbc483de9fe06052bcde871b88e81e2245839f795ac72ab1'}
PNG_SHA256 = {16: '6fa050086ba2a67202579948aed322ef9613cdb56525f04c9cc799d5fc68a58f',
 22: '1da5bf88af14f8a5934b3594e4592a0643ef2edd85e7058bcfdefd840792aace',
 24: 'e3670974f4bfba6fdc2502afd6b7c96fd672e93b391953206662c748855ce07c',
 32: '4ecb2ed2bdf23853d6f0d9fd97785a5fba8d6fd55266927b9456534e8e00c0e0',
 48: 'd0fb16bc270c33faac09af465593afa03e4d67efed5d5deeb9f183104c672545',
 64: 'f6daf5a963bc6e234957fd71948197b5957ef289927d072b854263ec41d07502',
 128: 'bc2a77b9b3e93ed6dd00c7ce09b9fbb2a2b765602496b4c4d3f1678796e8ca5f',
 256: '647da4186b5964ba09e62d81f942fbc168fe7889f094c784cf1d7583f822b4da',
 512: '1e3bf27c5a6bfa20dfd781c6f275462c4442b81130754b47b644094df49085f5',
 1024: '8235d4a181d211a7a11d821e3b173de1c81a8df33c869762aff48315e342f5d6'}
SMALL_SVG_SHA256 = {16: '193c884e0cc94b6cb1f24f88276fd013e3161e9ae99604de296080a3c6ed92c6',
 22: '6692e4d12c0b3c5f706024edf49f2cbf3e6fcae5740403de3fa571a55914ab99',
 24: '82207cf62903e511ad2a6afd35716f08f79d48bda1c9d2e5f968e3e889ffb360',
 32: '91db670157d03bd0cd19e6b770627680d26a93dadbb610e17e739fe070ae52de',
 48: 'ffb097a2be1e95faea3890329d170ed26366e2e1a0a995e4efc0108cff078c96',
 64: '3d68835324cdfddd739438e3356185ff0206d67ff4ade0fb1d761e83664abae6'}
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
            win = ike.windows[0]
            index = win.views.index(win.current_view())
            # the new tab page loaded and its icon's fade over (1.1.27: on GitHub's slower
            # runners the tab still showed the loading mark, a single 32 px picture, at 0.3 s)
            for _ in range(200):
                view = win.current_view()
                if (not getattr(view, "loading_marked", False)
                        and len(win.tabbar.tabIcon(index).availableSizes()) > 1):
                    break
                yield 50
            yield 400
            for name, icon in (("app", ike.icon), ("qapp", qapp.windowIcon()),
                               ("window", win.windowIcon()), ("horizontal", win.tabbar.tabIcon(index)),
                               ("vertical", win.vtabs.item(index).icon()), ("about", win.act_about.icon())):
                out[name] = sorted(s.width() for s in icon.availableSizes())
                same = {}
                for n in ICON_SIZES:
                    shown = icon.pixmap(QSize(n, n)).toImage().convertToFormat(PREMUL)
                    own = QImage(str(RES_DIR / "icons" / ("ike-browser-%d.png" % n))).convertToFormat(
                        PREMUL)
                    same[n] = shown == own
                out[name + "_same"] = same
                for n in (16, 22, 24, 32):
                    shown = icon.pixmap(QSize(16, 16), n / 16).toImage().convertToFormat(PREMUL)
                    own = QImage(str(RES_DIR / "icons" / ("ike-browser-%d.png" % n))).convertToFormat(PREMUL)
                    same["16@%d" % n] = shown == own
    """)
    # the windows' icon: every picture up to 256 (1.1.27: 512 and 1024 made the
    # window's icon 5.6 MB, and Plasma's task bar flickered black on each hover)
    every = sorted(n for n in PNG_SHA256 if n <= 256)
    assert out["sizes"] == every
    for name in ("app", "qapp", "window", "horizontal", "vertical", "about"):
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
    every = sorted(PNG_SHA256)
    for n in every:
        assert ("-Dm644 data/icons/ike-browser-%d.png "
                "/nonexistent-pkg/usr/share/icons/hicolor/%dx%d/apps/ike-browser.png" % (n, n, n)) in lines, n
        assert (ROOT / "data/icons" / ("ike-browser-%d.png" % n)).is_file()
    assert ("-Dm644 data/icons/ike-browser.svg "
            "/nonexistent-pkg/usr/share/icons/hicolor/scalable/apps/ike-browser.svg") in lines
    # an installed copy (the package's own tests): the same pictures are there
    share = APP.parent.parent / "share/icons/hicolor"
    if APP != ROOT:
        for n in every:
            installed = share / ("%dx%d" % (n, n)) / "apps/ike-browser.png"
            assert sha256(installed) == PNG_SHA256[n], n
        assert sha256(share / "scalable/apps/ike-browser.svg") == ASSET_SHA256["ike.svg"]
        assert sha256(share.parent.parent / "pixmaps/ike-browser.png") == PNG_SHA256[256]


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
            out["about_text"] = dialog.text().count(APP_LONG_NAME)
            icons = [label.pixmap() for label in dialog.findChildren(QLabel) if not label.pixmap().isNull()]
            out["about_logos"] = [pix.deviceIndependentSize().width() for pix in icons]
            if shots:
                dialog.show()
                yield 200
                dialog.grab().save(os.path.join(shots, "about-brand.png"))
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
    assert page["wordmark"] == "ike:wordmark"
    assert out["about_text"] == 1 and out["about_logos"] == [64]
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


@pytest.mark.parametrize("width,height", [(1920, 1080), (2560, 1440), (3840, 2160), (3440, 1440)])
def test_new_tab_and_home_at_desktop_resolutions(run_ike, tmp_path, width, height):
    import textwrap

    from conftest import screen
    from test_security import JS

    out = run_ike(JS + textwrap.dedent("""
        import os
        from PyQt6.QtCore import QUrl

        def steps(ike, qapp, out):
            win = ike.windows[0]
            view = win.current_view()
            yield 1300
            if WIDTH == 1920:
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
                yield 600

            for _ in range(10):
                result = yield from js(view, '''(() => {
                  const mark = document.querySelector("h1 img");
                  const logo = document.querySelector(".logo");
                  if (!mark || !logo || !mark.complete || !logo.complete) return null;
                  const css = getComputedStyle(document.documentElement);
                  const box = mark.getBoundingClientRect();
                  const img = logo.getBoundingClientRect();
                  return [innerWidth, innerHeight, css.backgroundSize, css.backgroundImage,
                          box.x + box.width / 2, img.x + img.width / 2, box.width / box.height, img.width / img.height];
                })()''')
                if result and abs(result[0] - WIDTH) <= 4:
                    break
                yield 350
            out["view"] = result
            shots = os.environ.get("IKE_TEST_SHOTS")
            if shots:
                yield 500
                win.grab().save(os.path.join(shots, "newtab-%dx%d.png" % (WIDTH, HEIGHT)))
    """).replace("WIDTH", str(width)).replace("HEIGHT", str(height)), settings={
        "newtab_bg": "default", "newtab_bg_fit": "fill", "start_maximized": True, "ui_scheme": "theme:ike"
    }, env=screen(tmp_path, width, height) | {
        "IKE_TEST_SHOTS": SHOTS,
        # A 4K frame can exhaust the default 64 MiB /dev/shm of a test container.
        "QTWEBENGINE_CHROMIUM_FLAGS": "--disable-dev-shm-usage",
    })
    if width == 1920:
        assert out["home"] == out["reloaded"] == "ike:newtab"
    assert out["view"], out
    viewport, page_height, fit, background, word_centre, logo_centre, word_ratio, logo_ratio = out["view"]
    assert abs(viewport - width) <= 4 and page_height >= height - 140
    assert "cover" in fit and "ike:background?" in background
    assert abs(word_centre - viewport / 2) <= 1 and abs(logo_centre - viewport / 2) <= 1
    assert abs(word_ratio - 1834 / 160) < 0.02 and logo_ratio == 1
