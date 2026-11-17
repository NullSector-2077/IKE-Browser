"""The I.K.E. brand: the logo and its icon files, the full name on the new tab
page, and no trace of an earlier name in the repository."""

import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = Path(os.environ.get("IKE_TEST_APP") or ROOT)
SHOTS = os.environ.get("IKE_TEST_SHOTS", "")
OLD_NAME = re.compile(r"I\.C\.E|\bICE\b|\bIce\b|\bice[-_.:]\w")
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


def test_icons_are_the_logo(run_ike):
    """Every PNG icon is the SVG logo drawn at that size (none left from an earlier drawing)."""
    folders = [APP / "ike/resources/icons"] + ([ROOT / "data/icons"] if APP == ROOT else [])
    files = sorted(str(p) for folder in folders for p in folder.glob("ike-browser-*.png"))
    assert len(files) >= 4
    out = run_ike("""
        from PyQt6.QtCore import QByteArray, QRectF
        from PyQt6.QtGui import QColor, QImage, QPainter
        from PyQt6.QtSvg import QSvgRenderer

        FILES = %r
        SVG = %r

        def steps(ike, qapp, out):
            yield 300
            renderer = QSvgRenderer(QByteArray(open(SVG, "rb").read()))
            out["valid"] = renderer.isValid()
            out["diff"] = {}
            for path in FILES:
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
    """ % (files, str(APP / "ike/resources/ike.svg")))
    assert out["valid"] and out["window_icon"]
    for path, (w, h, _worst, differing) in out["diff"].items():
        assert w == h == int(re.search(r"-(\d+)\.png$", path).group(1)), path
        assert differing <= 4, (path, out["diff"][path])


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
