"""Every text of the new tab page reads over any photo (1.1.24): a white one, a black one, a busy
one of large black and white squares and I.K.E.'s own. The page is drawn for real (offscreen) and,
under each group of text, the colour that is really there is measured against the colour of the text:
4.5:1 for small text, 3:1 for the large figures and the K of the wordmark (WCAG level AA).
Without a photo nothing of it is on the page."""

import os
import shutil
import sys

import pytest
from conftest import APP, ROOT
from test_security import JS

sys.path.insert(0, str(APP))


def make_photos(folder):
    """white, black and a busy picture (squares of 160 pixels, black and white): PNG files."""
    from PyQt6.QtGui import QColor, QImage, QPainter
    out = {}
    for name in ("white", "black"):
        image = QImage(960, 540, QImage.Format.Format_RGB32)
        image.fill(QColor("white" if name == "white" else "black"))
        out[name] = str(folder / (name + ".png"))
        image.save(out[name])
    image = QImage(960, 540, QImage.Format.Format_RGB32)
    p = QPainter(image)
    for y in range(0, 540, 90):
        for x in range(0, 960, 90):
            p.fillRect(x, y, 90, 90, QColor("white" if (x // 90 + y // 90) % 2 else "black"))
    p.end()
    out["busy"] = str(folder / "busy.png")
    image.save(out["busy"])
    return out


def test_the_grid_of_a_photo(tmp_path):
    from PyQt6.QtGui import QGuiApplication

    from ike import newtabbg
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")      # no screen on the test machines
    app = QGuiApplication.instance() or QGuiApplication([])
    photos = make_photos(tmp_path)
    w, h, cells = newtabbg.grid(photos["white"], True)
    assert (w, h) == (64, 36) and cells == "ff" * (64 * 36)
    assert newtabbg.grid(photos["white"], False)[2] == "ff" * (64 * 36)
    assert newtabbg.grid(photos["black"], True)[2] == "00" * (64 * 36)
    busy = newtabbg.grid(photos["busy"], True)
    assert "ff" in busy[2] and "00" in busy[2]
    assert newtabbg.grid(photos["busy"], True) is newtabbg.grid(photos["busy"], True)       # kept
    assert newtabbg.grid(str(tmp_path / "missing.png"), True) is None
    # I.K.E.'s own photo: dark in the main, a few bright cells
    own = newtabbg.grid(newtabbg.DEFAULT_FILE, True)
    values = [int(own[2][i:i + 2], 16) for i in range(0, len(own[2]), 2)]
    assert 0 < sum(1 for v in values if v > 200) < len(values) // 4
    del app


GATHER = """(function () {
  var out = [];
  function rgb(s) { var m = /(\\d+)[ ,]+(\\d+)[ ,]+(\\d+)/.exec(s); return m ? [+m[1], +m[2], +m[3]] : null; }
  function add(name, boxSel, textSel, least, prop) {
    var box = document.querySelector(boxSel), t = document.querySelector(textSel);
    if (!box || !t) return;
    var r = box.getBoundingClientRect();
    out.push([name, [r.left, r.top, r.width, r.height], rgb(getComputedStyle(t)[prop || "color"]), least,
              box.className]);
  }
  add("greeting", ".greet", "#greet-t", 4.5); add("greeting line", ".greet", "#greet-l", 4.5);
  add("clock", ".corner", ".clock", 4.5); add("date", ".corner", ".date", 4.5);
  add("counter", ".stats", ".stats b", 3); add("counter label", ".stats", ".stats span", 4.5);
  add("wordmark", "h1", "h1 svg path:not(.k)", 4.5, "fill"); add("K", "h1", "h1 svg .k", 3, "fill");
  add("settings", ".nt-settings .name", ".nt-settings .name", 4.5);
  add("photo button", ".nt-photo .name", ".nt-photo .name", 4.5);
  add("add tile", ".tile.add .name", ".tile.add .name", 4.5);
  return {rows: out, body: document.body.className, bg: getComputedStyle(document.documentElement).getPropertyValue("--bg").trim(),
          k: document.querySelectorAll("h1 svg path.k").length, kvar: getComputedStyle(document.documentElement).getPropertyValue("--k").trim(), label: document.querySelector("h1 svg").getAttribute("aria-label"),
          title: document.querySelector("h1 svg title").textContent, glass: !!document.getElementById("glass-data")};
})()"""

STEPS = JS + r'''
def steps(ike, qapp, out):
    import os
    from PyQt6.QtCore import QPoint, QUrl
    from ike import newtabbg
    win = ike.windows[0]
    win.resize(1100, 700)
    view = win.current_view()
    yield 800
    shots = SHOTS
    for name, path in PHOTOS:
        if name == "none":
            ike.config["newtab_bg"] = ""
        elif name == "default":
            newtabbg.use_default(ike.config)
        else:
            assert newtabbg.set_photo(ike.config, path) == ""
        ike.config["newtab_bg_veil"] = VEIL
        view.load(QUrl("ike:newtab"))
        yield 1800
        out[name] = yield from js(view, GATHER)
        yield 300
        view.grab().save(os.path.join(shots, SCHEME.replace(":", "-") + "-" + name + ".png"))
'''


def run_scheme(run_ike, tmp_path, scheme, veil=35, names=("white", "black", "busy", "default")):
    photos = make_photos(tmp_path)
    shots = tmp_path / "shots"
    shots.mkdir(exist_ok=True)
    script = (STEPS.replace("PHOTOS", repr([(n, photos.get(n, "")) for n in names]))
              .replace("GATHER", repr(GATHER)).replace("SHOTS", repr(str(shots))).replace("SCHEME", repr(scheme)).replace("VEIL", str(veil)))
    out = run_ike(script, settings={"ui_scheme": scheme, "newtab_bg": ""}, timeout=240)
    keep = os.environ.get("IKE_TEST_SHOTS")
    if keep:
        os.makedirs(keep, exist_ok=True)
        for f in shots.iterdir():
            shutil.copy(f, keep)
    return out, shots


def check(out, shots, scheme, names=("white", "black", "busy", "default")):
    from PyQt6.QtGui import QGuiApplication, QImage
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")      # no screen on the test machines
    app = QGuiApplication.instance() or QGuiApplication([])
    seen = 0
    for name in names:
        page = out[name]
        assert page["glass"] and "photo" in page["body"] and "glass" in page["body"], (scheme, name, page["body"])
        image = QImage(str(shots / ("%s-%s.png" % (scheme.replace(":", "-"), name))))
        assert not image.isNull() and image.width() >= 800
        for label, (left, top, width, height), colour, least, cls in page["rows"]:
            x, y = int(left) + 4, int(top + height / 2)
            assert 0 <= x < image.width() and 0 <= y < image.height(), (name, label)
            c = image.pixelColor(x, y)
            ratio = _ratio(colour, (c.red(), c.green(), c.blue()))
            assert ratio >= least - 0.1, (scheme, name, label, ratio, least, colour, (c.red(), c.green(), c.blue()), cls)
            seen += 1
    assert seen >= len(names) * 9
    del app


def _ratio(a, b):
    def lum(c):
        def ch(v):
            v /= 255.0
            return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
        return 0.2126 * ch(c[0]) + 0.7152 * ch(c[1]) + 0.0722 * ch(c[2])
    la, lb = lum(a), lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


@pytest.mark.parametrize("scheme", ["theme:ike", "light"])
def test_every_text_reads_over_any_photo(run_ike, tmp_path, scheme):
    out, shots = run_scheme(run_ike, tmp_path, scheme)
    check(out, shots, scheme)
    first = out["white"]
    assert first["k"] in (0, 1) and first["label"] == "Internet Kontrol Experience"       # the K path: brand-k branch
    assert first["title"] == "Internet Kontrol Experience"


def test_a_strong_or_no_veil_changes_nothing_about_the_guarantee(run_ike, tmp_path):
    for veil in (0, 90):
        out, shots = run_scheme(run_ike, tmp_path, "theme:ike", veil=veil, names=("white", "busy"))
        check(out, shots, "theme:ike", names=("white", "busy"))


def test_the_k_colour_and_nothing_extra_without_a_photo(run_ike, tmp_path):
    out, _shots = run_scheme(run_ike, tmp_path, "theme:ike", names=("none",))
    page = out["none"]
    assert page["body"].strip() in ("fx", "") and page["glass"] is False
    assert page["kvar"] == "#7df3ff"                                   # the light cyan on a dark page
    assert not [r for r in page["rows"] if "g0" in r[4]]               # no pane classes without a photo
    out, _shots = run_scheme(run_ike, tmp_path, "light", names=("none",))
    page = out["none"]
    bg, k = page["bg"], page["kvar"]
    ratio = _ratio((int(k[1:3], 16), int(k[3:5], 16), int(k[5:7], 16)),
                   (int(bg[1:3], 16), int(bg[3:5], 16), int(bg[5:7], 16)))
    assert ratio >= 3.0 and k != "#7df3ff"                             # darkened until it reads on a light page
    # the K of the wordmark takes it once the wordmark has the K as a path of its own (class k)
    css = (ROOT / "ike" / "resources" / "newtab.html").read_text("utf-8")
    assert "h1 svg .k{fill:var(--k)}" in css


