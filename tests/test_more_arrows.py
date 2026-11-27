"""Compare the painted overflow buttons and verify both bookmarks arrows use the Forward glyph."""

import pytest
from conftest import screen

STEPS = r'''
def ink(button):
    """(dx, dy): where the middle of what is drawn is, against the button's middle (logical px)."""
    pm = button.grab()
    img = pm.toImage()
    ratio = pm.devicePixelRatio()
    xs, ys = [], []
    for y in range(img.height()):
        for x in range(img.width()):
            c = img.pixelColor(x, y)
            if c.alpha() > 0 and abs(c.lightness() - BG) > 60:
                xs.append(x)
                ys.append(y)
    if not xs:
        return None
    return [round((min(xs) + max(xs) + 1) / 2 / ratio - button.width() / 2, 2),
            round((min(ys) + max(ys) + 1) / 2 / ratio - button.height() / 2, 2)]

def steps(ike, qapp, out):
    global BG
    from PyQt6.QtGui import QIcon, QPalette, QRegion
    win = ike.windows[0]
    win.showNormal()
    win.resize(1000, 700)
    yield 500
    BG = win.palette().color(QPalette.ColorRole.Window).lightness()
    out["ratio"] = win.devicePixelRatioF()
    bar = win.bookbar
    bar.show()
    bar.set_marks([(QIcon(), "Bookmark number %d" % i, "https://example.org/%d" % i) for i in range(40)],
                  lambda u: None)
    yield 500
    more = bar._more
    out["bookmarks"] = [bar._more_action.isVisible(), more.text(), more.icon().isNull(), more.width(),
                        more.height(), more.toolButtonStyle().name, more.toolTip(), more.accessibleName(),
                        ink(more), len(bar._menu.actions()) > 0]
    ratio = win.devicePixelRatioF()
    source = win.act_fwd.icon().pixmap(win.nav.iconSize(), ratio)
    source = source.copy(QRegion(source.mask()).boundingRect()).toImage()
    pair = more.icon().pixmap(more.iconSize(), ratio).toImage()
    # 1.1.29 (the owner): the desktop's double arrow, as tall as the Forward glyph
    from ike import icons as ike_icons
    double = ike_icons.themed(("arrow-right-double",)).pixmap(win.nav.iconSize(), ratio)
    double = double.copy(QRegion(double.mask()).boundingRect()).toImage()
    out["double"] = [pair.height(), source.height(), pair.width() > source.width() * 1.3,
                     pair.width() < source.width() * 2.2,
                     pair == double if double.height() == source.height() else None]
    from ike import icons
    out["names"] = icons.seen.get(("arrow-right-double", "go-next"))
    # the toolbar's own: every button shown, a narrow window
    ike.config["toolbar_hidden"] = []
    ike.refresh_toolbars()
    win.resize(640, 700)
    yield 600
    m = win.more_btn
    out["toolbar"] = [win.more_act.isVisible(), m.text(), m.icon().isNull(), m.width(), m.height(),
                      m.toolButtonStyle().name, m.toolTip(), m.accessibleName(), ink(m),
                      len(win.more_menu.actions()) > 0]
    nav = win.nav
    r = m.geometry()
    out["toolbar_middle"] = (2 * r.y() + r.height()) - nav.height()        # centred in the toolbar too
'''


@pytest.mark.parametrize("scale, theme", [("1", "set:breeze"), ("2", "set:lucide")])
def test_the_double_arrow_sits_in_the_middle(run_ike, tmp_path, scale, theme):
    from ike.i18n import T
    env = dict(screen(tmp_path, 1600, 1000), QT_SCALE_FACTOR=scale)
    out = run_ike(STEPS, env=env, settings={"bookmarks_bar": "always", "start_maximized": False,
                                            "system_titlebar": False, "icon_theme": theme})
    assert abs(out["ratio"] - float(scale)) < 0.01
    for key, tip in (("bookmarks", T("More bookmarks")), ("toolbar", T("More buttons"))):
        shown, text, null, w, h, style, tooltip, name, offset, listed = out[key]
        assert shown and listed, (key, out[key])
        assert text == "" and not null and style == "ToolButtonIconOnly", (key, out[key])
        assert h == 26 and (w >= h if key == "bookmarks" else w == h), (key, w, h)
        assert tooltip == name == tip
        assert offset and max(abs(v) for v in offset) <= 1, (key, offset)
    # 1.1.29 (the owner): the desktop's own double arrow, Forward's height
    height, forward, _wider, _narrow, same = out["double"]
    assert height == forward and same in (True, None), out["double"]
    assert out["names"] and out["names"][1] in ("arrow-right-double", "go-next"), out["names"]
    assert abs(out["toolbar_middle"]) <= 1, out["toolbar_middle"]
