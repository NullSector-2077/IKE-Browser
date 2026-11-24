"""The toolbar's "Bookmark this page" button (1.1.25, the owner's design): fixed
just outside the address bar's right edge, 4 pixels after it and centred with
it in height; it can be neither moved nor hidden (settings of earlier versions
that moved or hid it are mended); the address bar and the button are centred
in the window as one block; a page already bookmarked shows a filled bookmark."""

import json

import pytest
from conftest import screen


def test_the_settings_of_earlier_versions_are_mended(tmp_path):
    from ike.config import DEFAULTS, TOOLBAR_ITEMS, Config
    assert "bookmark" not in DEFAULTS["toolbar_order"] and "bookmark" not in DEFAULTS["toolbar_left"]
    assert "bookmark" not in [k for k, _h in TOOLBAR_ITEMS]
    f = tmp_path / "settings.json"
    f.write_text(json.dumps({"toolbar_order": ["dark", "bookmark", "downloads", "reader"],
                             "toolbar_left": ["dark", "bookmark"], "toolbar_hidden": ["pip", "bookmark"]}), "utf-8")
    c = Config(f)
    assert c["toolbar_order"] == ["dark", "downloads", "reader"]
    assert c["toolbar_left"] == ["dark"] and c["toolbar_hidden"][:1] == ["pip"] and "bookmark" not in c["toolbar_hidden"]
    # 1.1.5's "translate" became "bookmark" in 1.1.6: now it leaves the arrangement too
    f.write_text(json.dumps({"toolbar_order": ["translate", "reader"], "toolbar_hidden": ["translate"]}), "utf-8")
    c = Config(f)
    assert "bookmark" not in c["toolbar_order"] and "bookmark" not in c["toolbar_hidden"]


STEPS = r'''
def filled_share(icon):
    """How much of its drawing's box the icon fills, in per cent (a filled shape: most of it)."""
    img = icon.pixmap(44, 44).toImage()
    pts = [(x, y) for y in range(img.height()) for x in range(img.width()) if img.pixelColor(x, y).alpha() > 128]
    if not pts:
        return 0
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return round(100 * len(pts) / ((max(xs) - min(xs) + 1) * (max(ys) - min(ys) + 1)))

def steps(ike, qapp, out):
    from PyQt6.QtCore import QPoint, Qt, QUrl
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QMenu
    from ike import icons
    win = ike.windows[0]
    win.showNormal()
    win.resize(1500, 800)
    yield 800
    nav = win.nav
    acts = nav.actions()
    i = acts.index(win.urlbar_act)
    out["order"] = [acts.index(win.act_tb_bookmark) - i, acts.index(win.act_tb_bookmark) < acts.index(win.space_right_act),
                    acts.index(win.act_tb_bookmark) < acts.index(win.store_act)]
    out["config"] = [ike.config["toolbar_order"], ike.config["toolbar_left"], ike.config["toolbar_hidden"]]
    out["movable"] = "bookmark" in [k for k, _a, _x in win._nav_items]
    b = nav.widgetForAction(win.act_tb_bookmark)
    ub = win.urlbar
    def place():
        u = QPoint(ub.mapTo(nav, QPoint(0, 0)))
        p = b.mapTo(nav, QPoint(0, 0))
        return [p.x() - (u.x() + ub.width()),                                # the gap
                (2 * p.y() + b.height()) - (2 * u.y() + ub.height()),        # 2 x the difference of the middles
                ub.mapTo(win, QPoint(0, 0)).x(), b.mapTo(win, QPoint(0, 0)).x() + b.width(), win.width(),
                b.isVisible(), min(w.width() for w in win._nav_spacers)]
    out["place"] = {}
    for width in (1920, 1500, 1280, 1000):
        win.resize(width, 800)
        yield 500
        out["place"][width] = place()
    win.resize(1500, 800)
    yield 500
    # neither moved nor hidden: no key for the mover, not in the lists of buttons
    out["key"] = b.property("ikeToolbarKey")
    m = QMenu()
    win._fill_toolbar_buttons(m)
    out["menu_keys"] = [a.data() for a in m.actions()]
    dlg = win.open_settings("appearance")
    yield 300
    out["settings_keys"] = sorted(dlg.tb_btns)
    dlg.close()
    win.act_customise.trigger()
    yield 300
    c = b.mapTo(nav, b.rect().center())
    out["outlined"] = any(r.contains(c) for r in win.toolbar_mover.overlay.outlines)
    win.customise_toolbar(False)
    yield 200
    # a long press and a drag do nothing to it
    from PyQt6.QtCore import QEvent, QPointF
    from PyQt6.QtGui import QMouseEvent
    def ev(w, kind, gpos, button, buttons):
        from PyQt6.QtCore import QCoreApplication
        QCoreApplication.sendEvent(w, QMouseEvent(kind, QPointF(w.mapFromGlobal(gpos)), QPointF(gpos), button,
                                                  buttons, Qt.KeyboardModifier.NoModifier))
    order = list(ike.config["toolbar_order"])
    start = b.mapToGlobal(b.rect().center())
    ev(b, QEvent.Type.MouseButtonPress, start, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton)
    yield 900
    for x in (40, 120, 300):
        ev(b, QEvent.Type.MouseMove, start + QPoint(x, 0), Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton)
        yield 15
    ev(b, QEvent.Type.MouseButtonRelease, start + QPoint(300, 0), Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton)
    yield 300
    out["dragged"] = [list(ike.config["toolbar_order"]) == order, nav.actions().index(win.act_tb_bookmark) - nav.actions().index(win.urlbar_act)]
    # the filled bookmark on a bookmarked page; the outline with a plus otherwise
    view = win.current_view()
    view.setHtml("<title>Page</title><p>hello", QUrl("https://example.org/page"))
    yield 1200
    win.sync_urlbar()
    yield 200
    empty = filled_share(win.act_tb_bookmark.icon())
    b = nav.widgetForAction(win.act_tb_bookmark)
    QTest.mouseClick(b, Qt.MouseButton.LeftButton)
    yield 900
    full = win.act_tb_bookmark.icon()
    filled = icons.themed("bookmarks-bookmarked")
    out["filled"] = [ike.storage.is_bookmarked("https://example.org/page"), empty, filled_share(full),
                     full.pixmap(22, 22).toImage() == filled.pixmap(22, 22).toImage(),
                     win.act_tb_bookmark.toolTip(), icons.seen.get(("bookmarks-bookmarked",))]
    QTest.mouseClick(b, Qt.MouseButton.LeftButton)
    yield 600
    out["unfilled"] = [ike.storage.is_bookmarked("https://example.org/page"),
                       filled_share(win.act_tb_bookmark.icon()), win.act_tb_bookmark.toolTip()]
'''


@pytest.mark.parametrize("scale", ["1", "2"])
def test_fixed_after_the_address_bar(run_ike, tmp_path, scale):
    from ike.i18n import T
    env = dict(screen(tmp_path, 2000, 1000), QT_SCALE_FACTOR=scale, IKE_REDUCED_MOTION="1")
    # settings of 1.1.24 that moved it to the left and hid it: it is back, fixed, shown
    out = run_ike(STEPS, env=env, settings={"system_titlebar": False, "start_maximized": False,
                                            "toolbar_left": ["dark", "bookmark"], "toolbar_hidden": ["pip", "bookmark"],
                                            "toolbar_order": ["dark", "bookmark", "private", "downloads", "reader"]})
    next_to, after, ok_before = out["order"]
    assert next_to in (1, 2) and after and ok_before, out["order"]      # (2: the small room of the gap first)
    order, left, hidden = out["config"]
    assert "bookmark" not in order + left + hidden, out["config"]
    assert out["movable"] is False
    for width, (gap, middles, bar_left, button_right, win_width, shown, free) in out["place"].items():
        width = int(width)
        assert shown and gap == 4, (width, out["place"][str(width)])
        assert abs(middles) <= 1, (width, middles)                # centred with the bar in height
        # the block (bar + button) in the middle of the window; where the buttons of one side leave
        # too little room, as near as it gets (no free room left on that side)
        centred = abs((bar_left + button_right) / 2 - win_width / 2) <= 1
        assert centred or free <= 1, (width, out["place"][str(width)])
        if width >= 1920:
            assert centred, (width, out["place"][str(width)])
    assert out["key"] is None and "bookmark" not in out["menu_keys"] and "bookmark" not in out["settings_keys"]
    assert out["outlined"] is False
    assert out["dragged"] == [True, next_to], out["dragged"]           # a long press and a drag move nothing
    marked, empty, full, same, tip, seen = out["filled"]
    assert marked and same and tip == T("Remove bookmark"), out["filled"]
    assert empty < 60 and full > 85, out["filled"]                # an outline before, filled after
    assert seen and seen[1] == "bookmarks-bookmarked", seen
    assert out["unfilled"][0] is False and out["unfilled"][1] < 60 and out["unfilled"][2] == T("Bookmark this page")
