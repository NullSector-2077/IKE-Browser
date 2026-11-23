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
# 1.1.23: the sizes drawn for their own pixel grid (tools/make-small-icons.py),
# and the large ones, which stay the logo itself (tools/make-brand.py), unchanged
SMALL = (16, 22, 24, 32, 48, 64)
SMALL_DIR = "data/icons/small"
LOGO_SHA256 = "b5f68e388951f38dd8fdebaa80a9d0956517dfbfdb245a60d164c46e43bfc3fc"
LARGE_SHA256 = {128: "b3ea0fc32a92173a11919986c0aff01526dd128b8215bfc30d019e9ccaee5219",
                256: "f9dc03bc3ef7f966176dab9d06402140c0d65276879a1ab2bae8372c20b8635e",
                512: "e9796fc798f5027b55b0438afe3c02f395f195e371a032088b07b5e78629763f"}
# files of other projects, where the three letters mean something else
THIRD_PARTY = ("ike/resources/darkreader.js", "ike/resources/darkreader-proxy.js", "ike/resources/darkreader-data.json", "ike/resources/ubo-scriptlets.json", "ike-adblock/Cargo.lock",
               "ike/resources/icons/sets/")


def test_logo_files():
    logo = (APP / "ike/resources/ike.svg").read_text("utf-8")
    assert "<title>I.K.E</title>" in logo
    # drawn as shapes: no text, no font needed where it is shown
    assert "<text" not in logo and "font-family" not in logo and "@font-face" not in logo
    lettering = re.search(r'<path id="lettering"[^>]* d="([^"]+)"', logo)
    assert lettering, "the lettering path is missing"
    d = lettering.group(1)
    # I . K . E: five closed outlines, straight strokes only (the earlier lettering had curves)
    assert d.count("Z") == 5 and d.count("M") == 5
    assert not re.search(r"[CQSTA]", d)
    wordmark = (APP / "ike/resources/wordmark.svg").read_text("utf-8")
    assert 'aria-label="Internet Kontrol Experience"' in wordmark
    assert 'fill="currentColor"' in wordmark and "<text" not in wordmark
    # 25 letters, each at least one closed outline
    assert wordmark.count("Z") >= 25
    if APP == ROOT:
        assert (ROOT / "data/icons/ike-browser.svg").read_text("utf-8") == logo
        assert (ROOT / "licenses/LICENSE.orbitron").read_text("utf-8").count("SIL OPEN FONT LICENSE") >= 1
        assert "Orbitron" in (ROOT / "docs/THIRD-PARTY.md").read_text("utf-8")


def size(png):
    return int(re.search(r"-(\d+)\.png$", str(png)).group(1))


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_icons_are_the_logo(run_ike):
    """Every PNG icon is the SVG logo drawn at that size (none left from an earlier drawing):
    from 128 px up the scalable logo, below it the drawing made for that size (1.1.23)."""
    folders = [APP / "ike/resources/icons"] + ([ROOT / "data/icons"] if APP == ROOT else [])
    files = sorted(str(p) for folder in folders for p in folder.glob("ike-browser-*.png"))
    assert len(files) >= 4
    drawings = {str(p): str(ROOT / SMALL_DIR / p.name.replace(".png", ".svg")) if size(p) in SMALL
                else str(APP / "ike/resources/ike.svg") for p in map(Path, files)}
    out = run_ike("""
        from PyQt6.QtCore import QByteArray, QRectF
        from PyQt6.QtGui import QColor, QImage, QPainter
        from PyQt6.QtSvg import QSvgRenderer

        DRAWINGS = %r

        def steps(ike, qapp, out):
            yield 300
            out["valid"] = {}
            out["diff"] = {}
            for path, svg in sorted(DRAWINGS.items()):
                renderer = QSvgRenderer(QByteArray(open(svg, "rb").read()))
                out["valid"][svg] = renderer.isValid()
                png = QImage(path).convertToFormat(QImage.Format.Format_ARGB32)
                size = png.width()
                ref = QImage(size, size, QImage.Format.Format_ARGB32)
                ref.fill(0)
                p = QPainter(ref)
                p.setRenderHint(QPainter.RenderHint.Antialiasing)
                renderer.render(p, QRectF(0, 0, size, size))
                p.end()
                worst = total = 0
                for x in range(0, size, max(1, size // 96)):
                    for y in range(0, size, max(1, size // 96)):
                        a, b = QColor.fromRgba(png.pixel(x, y)), QColor.fromRgba(ref.pixel(x, y))
                        d = max(abs(a.red() - b.red()), abs(a.green() - b.green()),
                                abs(a.blue() - b.blue()), abs(a.alpha() - b.alpha()))
                        worst = max(worst, d)
                        total += d > 40
                out["diff"][path] = [png.width(), png.height(), worst, total]
            out["window_icon"] = not ike.windows[0].windowIcon().isNull()
    """ % drawings)
    assert out["valid"] and all(out["valid"].values()) and out["window_icon"]
    for path, (w, h, _worst, differing) in out["diff"].items():
        assert w == h == int(re.search(r"-(\d+)\.png$", path).group(1)), path
        assert differing <= 4, (path, out["diff"][path])


def test_small_icons(run_ike):
    """1.1.23: the sizes a panel, a title bar or a menu shows (16 to 64 px) are
    drawn for their own pixel grid, with letters that can be read: each one is
    there, at its size, in the desktop's folder and in the browser's, drawn as
    shapes on whole pixels (no text, no font), and the window icon carries them
    all, so Qt shows the small drawing instead of shrinking the large one."""
    for n in SMALL:
        pictures = [APP / "ike/resources/icons" / ("ike-browser-%d.png" % n)]
        if APP == ROOT:
            pictures.append(ROOT / "data/icons" / ("ike-browser-%d.png" % n))
        for png in pictures:
            head = png.read_bytes()[:24]
            assert head[:8] == b"\x89PNG\r\n\x1a\n" and struct.unpack(">II", head[16:24]) == (n, n), png
        assert len({sha256(p) for p in pictures}) == 1, n
        svg = (ROOT / SMALL_DIR / ("ike-browser-%d.svg" % n)).read_text("utf-8")
        assert '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d"' % (n, n) in svg
        assert "<title>I.K.E</title>" in svg
        assert "<text" not in svg and "font" not in svg and "<image" not in svg
        letters = re.search(r'<path id="lettering" fill="#eafcff" d="([^"]+)"/>', svg).group(1)
        # rectangles on whole pixels: no curve, no fraction of a pixel
        assert re.fullmatch(r"M\d+ \d+h\d+v\d+h-\d+Z( M\d+ \d+h\d+v\d+h-\d+Z)*", letters), n
    # the large ones stay the logo itself, unchanged
    assert sha256(APP / "ike/resources/ike.svg") == LOGO_SHA256
    for n in (128, 256):
        assert sha256(APP / "ike/resources/icons" / ("ike-browser-%d.png" % n)) == LARGE_SHA256[n], n
    if APP == ROOT:
        assert sha256(ROOT / "data/icons/ike-browser.svg") == LOGO_SHA256
        for n, digest in LARGE_SHA256.items():
            assert sha256(ROOT / "data/icons" / ("ike-browser-%d.png" % n)) == digest, n

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
    every = sorted(SMALL + (128, 256))
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
                var svg = document.querySelector("h1 svg"), img = document.querySelector("img");
                var r = svg ? svg.getBoundingClientRect() : null;
                return {label: svg && svg.getAttribute("aria-label"), w: r && r.width, h: r && r.height,
                        left: r && r.left, right: r && r.right, page: innerWidth,
                        colour: svg && getComputedStyle(svg).color,
                        mute: getComputedStyle(document.documentElement).getPropertyValue("--mute").trim(),
                        logo: img && img.complete && img.naturalWidth, alt: img && img.alt,
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
    """, env={"IKE_TEST_SHOTS": SHOTS})
    page = out["page"]
    assert out["url"].startswith("ike:")
    assert page["label"] == "Internet Kontrol Experience"
    assert 10 <= page["h"] <= 14 and page["w"] > 250
    # centred, inside the page
    assert page["left"] > 0 and page["right"] < page["page"]
    assert abs((page["left"] + page["right"]) / 2 - page["page"] / 2) <= 1.5
    assert page["logo"] and page["alt"] == "I.K.E." and page["title"] == "I.K.E."
    assert not page["template"] and page["fonts"] == 0
    # the wordmark takes the page's muted text colour (the theme's), not a colour of its own
    r, g, b = (int(page["mute"][i:i + 2], 16) for i in (1, 3, 5))
    assert page["colour"].replace(" ", "") == "rgb(%d,%d,%d)" % (r, g, b)
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
