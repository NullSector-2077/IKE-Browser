"""1.1.27: the launcher's icons follow the version in use; the protection
octagon shows its level's letter again and its animations sit on it.

- The package installs the menu's icons under /usr/share/icons, which a
  self-update never touches: 1.1.27's new logo would have reached the menu
  only after the package was installed by hand. I.K.E. copies the icons of
  the version in use into the user's icon folder (read first by every
  desktop): the same files the package installs, only those that differ,
  nothing for a copy that is not installed, nothing when they are equal.
- The ring that opens when something is blocked is centred on the octagon,
  and the rising "+N" starts after the number beside it (the ring was a few
  pixels to the right of the octagon drawn by 1.1.27's ShieldButton).
- The level's letter (C, B, S, M) is inside the octagon again, as in the
  shield of 1.1.26, each in a colour of its own with a contrast of 7:1 or
  more on the octagon's dark centre; off is a grey octagon with a white X.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def env_for(tmp_path, desktop="user"):
    data = tmp_path / "data"
    env = {"HOME": str(tmp_path), "XDG_DATA_HOME": str(data), "XDG_DATA_DIRS": str(tmp_path / "sys")}
    if desktop == "user":
        (data / "applications").mkdir(parents=True)
        (data / "applications" / "ike-browser.desktop").write_text("[Desktop Entry]\n")
    elif desktop == "system":
        (tmp_path / "sys" / "applications").mkdir(parents=True)
        (tmp_path / "sys" / "applications" / "ike-browser.desktop").write_text("[Desktop Entry]\n")
    return env


def test_the_same_icons_as_the_package():
    from ike import desktopicons
    pkg = (ROOT / "PKGBUILD").read_text()
    sizes = re.search(r"for size in ([0-9 ]+); do\s+install -Dm644 \"data/icons/ike-browser-\$size.png\"", pkg)
    assert sizes, "the PKGBUILD's icon sizes were not found"
    assert tuple(int(s) for s in sizes.group(1).split()) == desktopicons.SIZES
    for rel, src in desktopicons.wanted().items():
        name = "ike-browser.svg" if rel.startswith("scalable") else src.name
        assert src.read_bytes() == (ROOT / "data" / "icons" / name).read_bytes(), rel
    assert len(desktopicons.wanted()) == len(desktopicons.SIZES) + 1


def test_icons_copied_only_when_they_differ(tmp_path):
    from ike import desktopicons
    env = env_for(tmp_path, "system")
    assert desktopicons.sync(env=env) == len(desktopicons.SIZES) + 1
    root = tmp_path / "data" / "icons" / "hicolor"
    png = root / "48x48" / "apps" / "ike-browser.png"
    assert png.read_bytes() == (ROOT / "ike/resources/icons/ike-browser-48.png").read_bytes()
    assert (root / "scalable/apps/ike-browser.svg").read_bytes() == (ROOT / "ike/resources/ike.svg").read_bytes()
    assert desktopicons.sync(env=env) == 0                       # the same: nothing written
    png.write_bytes(b"old logo")
    assert desktopicons.sync(env=env) == 1                       # the old one replaced
    assert png.read_bytes() == (ROOT / "ike/resources/icons/ike-browser-48.png").read_bytes()
    assert not list(root.rglob("*.ike-tmp"))


def test_nothing_for_a_copy_that_is_not_installed(tmp_path):
    from ike import desktopicons
    env = env_for(tmp_path, None)
    assert desktopicons.sync(env=env) == 0
    assert not (tmp_path / "data" / "icons").exists()
    assert desktopicons.installed(env_for(tmp_path / "u", "user"))


def test_a_read_only_home_changes_nothing(tmp_path):
    from ike import desktopicons
    env = env_for(tmp_path, "user")
    (tmp_path / "data" / "icons").write_text("not a folder")      # cannot be made
    assert desktopicons.sync(env=env) == 0


RING = r'''
from PyQt6.QtCore import QUrl

def steps(ike, qapp, out):
    w = ike.windows[0]
    yield 400
    v = w.current_view()
    v.setHtml("<title>t</title><body>x</body>", QUrl("https://www.example.test/"))
    yield 800
    host = w.current_host()
    st = ike.shields.stats.setdefault(host, dict.fromkeys(ike.shields.KINDS, 0))
    st["ads"] = 1234
    w.update_shield()
    yield 300
    b = w.shield_btn
    r = b.icon_rect()
    ring = w.shield_pulse._ring(0.5, 1.0).toImage()
    # the ring's left and right ends on the middle row
    y = ring.height() // 2
    xs = [x for x in range(ring.width()) if ring.pixelColor(x, y).alpha() > 40]
    out["ring_centre"] = (xs[0] + xs[-1]) / 2 if xs else None
    out["icon_centre"] = r.center().x()
    out["count_end"] = b.count_end()
    out["plus_left"] = w.shield_count.text_left()
    out["width"] = b.width()
'''


def test_the_ring_and_the_plus_n_sit_on_the_octagon(run_ike):
    out = run_ike(RING, settings={"shield_level": "balanced"}, timeout=60)
    assert "error" not in out, out.get("error")
    assert out["ring_centre"] is not None and abs(out["ring_centre"] - out["icon_centre"]) <= 1.0, out
    assert out["count_end"] <= out["width"] and 3 <= out["plus_left"] - out["count_end"] <= 7, out


def _luminance(hex_colour):
    c = [int(hex_colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def test_the_level_letter_is_back_and_readable():
    """The owner (2026-11-27): the level's letter inside the octagon, as in the
    shield of 1.1.26, in a colour of its own for each level, readable."""
    from ike.shieldpanel import CENTRE_COLOUR, LEVEL_COLOUR, LEVEL_LETTER
    assert LEVEL_LETTER == {"compatibility": "C", "balanced": "B", "strict": "S", "maximum": "M"}
    assert len(set(LEVEL_COLOUR.values())) == 4
    dark = _luminance(CENTRE_COLOUR)
    for level, colour in LEVEL_COLOUR.items():
        ratio = (_luminance(colour) + 0.05) / (dark + 0.05)
        assert ratio >= 7.0, (level, colour, ratio)


LETTERS = r'''
from PyQt6.QtCore import QSize

def steps(ike, qapp, out):
    from ike.shieldpanel import LEVEL_COLOUR, shield_icon
    yield 100
    pics = {}
    for level in ("off", "compatibility", "balanced", "strict", "maximum"):
        img = shield_icon(level, grow=1.15).pixmap(QSize(48, 48), 1.0).toImage()
        pics[level] = bytes(img.constBits().asarray(img.sizeInBytes()))
        want = LEVEL_COLOUR.get(level)
        found = 0
        for y in range(12, 36):
            for x in range(12, 36):
                c = img.pixelColor(x, y)
                if want and c.name().lower() == want.lower():
                    found += 1
        out[level] = found
    out["distinct"] = len(set(pics.values()))
    w = ike.windows[0]
    out["tip"] = w.shield_btn.toolTip()
'''


def test_each_level_shows_its_own_octagon(run_ike):
    out = run_ike(LETTERS, settings={"shield_level": "strict"}, timeout=60)
    assert "error" not in out, out.get("error")
    assert out["distinct"] == 5, out                 # the four levels and off: five pictures
    for level in ("compatibility", "balanced", "strict", "maximum"):
        assert out[level] >= 10, out                 # the letter, in the level's colour
    assert out["off"] == 0, out
    assert out["tip"].endswith("Strict") or "Strict" in out["tip"], out
