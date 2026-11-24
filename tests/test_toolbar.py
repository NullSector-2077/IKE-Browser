"""The navigation toolbar: its layout model, moving buttons with real mouse
events (long press and "Customise toolbar" mode), what is saved, and how the
toolbar behaves at other window sizes and screen scales."""

import json
import os
import random

import pytest
from conftest import screen

from ike.config import DEFAULTS, TOOLBAR_ITEMS
from ike.toolbar import LEFT, RIGHT, ToolbarLayout, default_layout

SHOTS = os.environ.get("IKE_TEST_SHOTS", "")
# the movable buttons; Back, Forward, Home, Reload and the shield have fixed places (1.1.9)
KEYS = ["bookmark", "reader", "screenshot", "pip", "split", "dark", "private", "cleansite", "downloads"]
LEFT_DEFAULT = ["dark", "private", "cleansite", "screenshot", "split"]          # pip starts hidden
RIGHT_DEFAULT = ["bookmark", "downloads", "reader"]
# 1.1.24: buttons a user can add, hidden until chosen (tests/test_menus_124.py); the
# model's tests below use the buttons of 1.1.23, the real toolbar has these too
NEW_KEYS = ["zoom", "bookmarks", "print", "send", "resources"]


# ----------------------------------------------------------------------
# the model
# ----------------------------------------------------------------------
def test_layout_from_settings():
    lay = ToolbarLayout(KEYS, DEFAULTS["toolbar_order"], DEFAULTS["toolbar_left"], ["pip"])
    assert lay.left == LEFT_DEFAULT + ["pip"]
    assert lay.right == RIGHT_DEFAULT
    assert lay.shown(LEFT) == LEFT_DEFAULT and lay.shown(RIGHT) == RIGHT_DEFAULT
    # every key once, whatever the settings hold
    for order, left, hidden in (
            ([], [], []),
            (None, None, None),
            ("reload", {"a": 1}, 7),
            (["menu", "menu", "gone", 3, None, "reader", "reader"], ["reader", "gone", 5], ["gone", "shield", "menu"]),
            (list(reversed(KEYS)), KEYS, KEYS)):
        lay = ToolbarLayout(KEYS, order, left, hidden)
        assert sorted(lay.left + lay.right) == sorted(KEYS), (order, left)
    # settings written before a button existed: it joins the end of the right zone
    old = [k for k in DEFAULTS["toolbar_order"] if k not in ("pip", "cleansite")]
    lay = ToolbarLayout(KEYS, old, ["dark"], [])
    assert lay.right[-2:] == ["pip", "cleansite"] and lay.left == ["dark"]
    # settings of 1.1.8, when the shield and Reload were movable: they are simply not in the zones
    lay = ToolbarLayout(KEYS, ["shield", "reload", "bookmark", "reader", "downloads", "menu"],
                        ["shield", "reload", "bookmark"], ["shield", "reload"])
    assert lay.left == ["bookmark"] and not ({"shield", "reload"} & set(lay.left + lay.right))
    assert sorted(lay.left + lay.right) == sorted(KEYS)
    # a button the program no longer has is forgotten
    lay = ToolbarLayout(KEYS[:-1], DEFAULTS["toolbar_order"] + ["menu"], [], [])
    assert "downloads" not in lay.left + lay.right


def test_layout_moves():
    lay = ToolbarLayout(KEYS, DEFAULTS["toolbar_order"], DEFAULTS["toolbar_left"], ["pip"])
    assert lay.slot_of("reader") == (RIGHT, 2) and lay.slot_of("screenshot") == (LEFT, 3)
    assert not lay.move("reader", RIGHT, 2)                     # already there
    assert lay.move("reader", RIGHT, 0)
    assert lay.shown(RIGHT)[:3] == ["reader", "bookmark", "downloads"]
    # past the last shown button it goes right after it; hidden ones stay where they were
    assert lay.move("dark", LEFT, 99)
    assert lay.left == ["private", "cleansite", "screenshot", "split", "dark", "pip"]
    assert lay.move("reader", LEFT, 0) and lay.left[0] == "reader"
    assert not lay.move("shield", LEFT, 0) and not lay.move("reload", RIGHT, 0)   # fixed: not movable
    assert lay.move("reader", LEFT, 99) and lay.shown(LEFT)[-1] == "reader" and lay.left[-1] == "pip"
    assert lay.move("reader", RIGHT, 99) and lay.right[-1] == "reader"
    assert lay.move("reader", RIGHT, -5) and lay.right[0] == "reader"
    assert not lay.move("unknown", LEFT, 0) and not lay.move("reader", "middle", 0)
    # both zones can be emptied and filled again
    for key in list(lay.left):
        assert lay.move(key, RIGHT, 0)
    assert lay.left == [] and lay.shown(LEFT) == []
    assert lay.move("downloads", LEFT, 0) and lay.left == ["downloads"]
    # any sequence of moves keeps every key exactly once
    rng = random.Random(7)
    for _ in range(500):
        key = rng.choice(KEYS)
        lay.move(key, rng.choice((LEFT, RIGHT)), rng.randint(-2, 14))
        assert sorted(lay.left + lay.right) == sorted(KEYS)
        zone, index = lay.slot_of(key)
        assert lay.shown(zone)[index] == key if key not in lay.hidden else True


def test_layout_is_stored_and_read_back():
    lay = ToolbarLayout(KEYS, DEFAULTS["toolbar_order"], DEFAULTS["toolbar_left"], ["pip"])
    lay.move("downloads", LEFT, 1)
    lay.move("bookmark", RIGHT, 3)
    cfg = {"toolbar_hidden": ["pip"]}
    lay.store(cfg)
    assert cfg["toolbar_hidden"] == ["pip"]                     # not this function's business
    assert json.loads(json.dumps(cfg)) == cfg
    again = ToolbarLayout.from_config(cfg, KEYS)
    assert (again.left, again.right, again.hidden) == (lay.left, lay.right, lay.hidden)
    first = default_layout(KEYS, DEFAULTS, TOOLBAR_ITEMS)
    assert first.left == DEFAULTS["toolbar_left"]
    assert first.left + first.right == [k for k in DEFAULTS["toolbar_order"] if k in KEYS]
    assert first.hidden == {"pip"} | set(NEW_KEYS)              # (1.1.24: the new ones start hidden too)
    full = default_layout(KEYS + NEW_KEYS, DEFAULTS, TOOLBAR_ITEMS)
    assert full.left + full.right == DEFAULTS["toolbar_order"]


# ----------------------------------------------------------------------
# the real toolbar
# ----------------------------------------------------------------------
HELPERS = r'''
from PyQt6.QtCore import QCoreApplication, QEvent, QPoint, QPointF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QWidget

LEFT_BTN, NO_BTN = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton

def ev(w, kind, gpos, button, buttons):
    lp = QPointF(w.mapFromGlobal(gpos))
    QCoreApplication.sendEvent(w, QMouseEvent(kind, lp, QPointF(gpos), button, buttons,
                                              Qt.KeyboardModifier.NoModifier))

def centre(w):
    return w.mapToGlobal(w.rect().center())

def keys(win):
    """Keys of the movable buttons as the toolbar shows them: [left zone], [right zone]."""
    by_act = {a: k for k, a, _x in win._nav_items}
    acts = win.nav.actions()
    split = acts.index(win.urlbar_act)
    return ([by_act[a] for a in acts[:split] if a in by_act], [by_act[a] for a in acts[split:] if a in by_act])

def button(win, key):
    act = {k: a for k, a, _x in win._nav_items}[key]
    return win.nav.widgetForAction(act)

def geometry(win):
    """Every visible widget of the toolbar: [name, x, width], left to right."""
    found = []
    for a in win.nav.actions():
        w = win.nav.widgetForAction(a)
        if w is not None and w.isVisible() and a.isVisible():
            found.append([w.property("ikeToolbarKey") or w.objectName() or type(w).__name__,
                          w.mapTo(win.nav, QPoint(0, 0)).x(), w.width()])
    return found

def drag(win, key, to, hold=900, steps=8, release=True, moves_out=None):
    """Press the button of key, hold, move to the global point in steps, release.
    A generator: use with "yield from"."""
    b = button(win, key)
    start = centre(b)
    ev(b, QEvent.Type.MouseButtonPress, start, LEFT_BTN, LEFT_BTN)
    yield hold
    for i in range(1, steps + 1):
        p = QPoint(round(start.x() + (to.x() - start.x()) * i / steps),
                   round(start.y() + (to.y() - start.y()) * i / steps))
        ev(b, QEvent.Type.MouseMove, p, NO_BTN, LEFT_BTN)
        if moves_out is not None:
            m = win.toolbar_mover
            moves_out.append([m._dragging, m.overlay.marker, m.overlay.isVisible(), m._ghost is not None,
                              keys(win), geometry(win)])
        yield 15
    if release:
        ev(b, QEvent.Type.MouseButtonRelease, to, LEFT_BTN, NO_BTN)
        yield 250

def after(win, key, dx=6):
    """A point just right of the middle of key's button."""
    return centre(button(win, key)) + QPoint(dx, 0)

def before(win, key, dx=6):
    return centre(button(win, key)) - QPoint(dx, 0)
'''


def test_long_press_moves_a_button_and_saves_it(run_ike, tmp_path):
    out = run_ike(HELPERS + r'''
def steps(ike, qapp, out):
    win = ike.windows[0]
    win.showNormal()
    win.resize(1400, 800)
    yield 600
    fired = []
    win.act_tb_reader.triggered.connect(lambda *_a: fired.append("reader"))
    win.act_tb_shot.triggered.disconnect()
    win.act_tb_shot.triggered.connect(lambda *_a: fired.append("screenshot"))
    out["start"] = keys(win)
    first_button = button(win, "bookmark")
    shape = geometry(win)

    # 1. long press, then drag past the last button (far enough for every step to be a real move)
    moves = []
    yield from drag(win, "bookmark", centre(win.menu_btn), moves_out=moves)     # dropped on the fixed menu: last of its zone
    out["moves"] = [[m[0], m[1], m[2], m[3]] for m in moves]
    out["toolbar_untouched_during_drag"] = all(m[4] == out["start"] and m[5] == shape for m in moves)
    out["after_first"] = keys(win)
    out["saved_first"] = [list(ike.config["toolbar_order"]), list(ike.config["toolbar_left"])]
    out["rebuilt"] = button(win, "bookmark") is not first_button
    out["ghost_gone"] = [win.toolbar_mover._ghost is None, win.toolbar_mover.overlay.isVisible()]
    out["status_after"] = [win.statusBar().isVisible(), win.statusBar().currentMessage()]

    # 2. the rebuilt button can be moved again, to the other side of the address bar
    yield from drag(win, "bookmark", before(win, "screenshot"))
    out["after_second"] = keys(win)

    # 3. a press shorter than the long press, then a move: nothing moves, and it is a click
    yield from drag(win, "bookmark", after(win, "reader"), hold=150)
    out["after_short"] = keys(win)

    # 4. a plain click still does the button's job; a long press without moving does not
    fired.clear()
    b = button(win, "screenshot")
    ev(b, QEvent.Type.MouseButtonPress, centre(b), LEFT_BTN, LEFT_BTN)
    yield 60
    ev(b, QEvent.Type.MouseButtonRelease, centre(b), LEFT_BTN, NO_BTN)
    yield 100
    out["click"] = list(fired)
    fired.clear()
    ev(b, QEvent.Type.MouseButtonPress, centre(b), LEFT_BTN, LEFT_BTN)
    yield 900
    out["hint"] = [win.statusBar().isVisible(), win.statusBar().currentMessage()]
    ev(b, QEvent.Type.MouseButtonRelease, centre(b), LEFT_BTN, NO_BTN)
    yield 100
    out["long_press_no_click"] = list(fired)
    out["hint_gone"] = [win.statusBar().isVisible(), win.statusBar().currentMessage(), b.isDown()]

    # 5. released far from the toolbar: cancelled
    fired.clear()
    was = keys(win)
    far = after(win, "reader") + QPoint(0, 300)
    yield from drag(win, "screenshot", far)
    out["cancelled"] = [keys(win) == was, list(fired), win.toolbar_mover._ghost is None]

    # 6. the fixed buttons (Home, Reload; the shield is in the address bar): no key, a long press and drag does nothing
    out["home_key"] = []
    for fixed in (win.nav.widgetForAction(win.act_home), win.nav.widgetForAction(win.act_reload)):
        out["home_key"].append(fixed.property("ikeToolbarKey"))
        ev(fixed, QEvent.Type.MouseButtonPress, centre(fixed), LEFT_BTN, LEFT_BTN)
        yield 900
        for x in (40, 120, 300):
            ev(fixed, QEvent.Type.MouseMove, centre(fixed) + QPoint(x, 0), NO_BTN, LEFT_BTN)
            yield 15
        ev(fixed, QEvent.Type.MouseButtonRelease, centre(fixed) + QPoint(300, 0), LEFT_BTN, NO_BTN)
        yield 150
    out["home_key"].append(win.shield_btn.property("ikeToolbarKey"))
    out["after_home_drag"] = keys(win) == was
    acts = win.nav.actions()
    out["shield_place"] = (win.shield_btn.parentWidget() is win.urlbar and win.shield_btn.geometry().right() > win.urlbar.width() - 20)
    # dropped on Back: the button becomes the first of the left zone, after the separator
    yield from drag(win, "split", centre(win.nav.widgetForAction(win.act_back)))
    out["after_drop_on_back"] = keys(win)
    acts = win.nav.actions()
    out["fixed"] = [acts.index(win.act_back), acts.index(win.act_fwd), acts.index(win.act_home),
                    acts.index(win.act_reload), acts.index(win.home_sep_act), acts[4].isSeparator(),
                    (win.shield_btn.parentWidget() is win.urlbar and win.shield_btn.geometry().right() > win.urlbar.width() - 20),
                    acts.index(win.win_sep_act) > acts.index(win.urlbar_act),
                    acts.index(win.menu_act) == acts.index(win.win_sep_act) + 1 == acts.index(win._win_btns[0]) - 1,
                    [acts.index(a) for a in win._win_btns] == sorted(acts.index(a) for a in win._win_btns),
                    acts[-1] is win._win_btns[-1]]
    out["final"] = keys(win)
    out["final_saved"] = [list(ike.config["toolbar_order"]), list(ike.config["toolbar_left"])]
    ''', settings={"system_titlebar": False, "start_maximized": False}, timeout=150,
       env=screen(tmp_path, 1600, 900))
    left, right = out["start"]
    assert left == LEFT_DEFAULT and right == RIGHT_DEFAULT
    # the drag: a marker and a ghost from the first real move, the toolbar itself untouched
    assert all(m[0] and m[2] and m[3] and isinstance(m[1], int) for m in out["moves"]), out["moves"]
    assert out["toolbar_untouched_during_drag"]
    assert len({m[1] for m in out["moves"]}) <= 5              # the marker snaps to the few places between buttons
    assert out["after_first"] == [left, ["downloads", "reader", "bookmark"]]
    order, saved_left = out["saved_first"]
    assert [k for k in saved_left if k != "pip"] == left            # pip: hidden, kept in its place
    assert order.index("downloads") < order.index("reader") < order.index("bookmark")
    assert sorted(order) == sorted(KEYS + NEW_KEYS)
    assert out["rebuilt"] and out["ghost_gone"] == [True, False]
    assert out["status_after"] == [False, ""]
    assert out["after_second"] == [["dark", "private", "cleansite", "bookmark", "screenshot", "split"],
                                   ["downloads", "reader"]]
    assert out["after_short"] == out["after_second"]
    assert out["click"] == ["screenshot"]
    assert out["hint"][0] is True and out["hint"][1]
    assert out["long_press_no_click"] == [] and out["hint_gone"] == [False, "", False]
    assert out["cancelled"] == [True, [], True]
    assert not any(out["home_key"]) and out["after_home_drag"] and out["shield_place"]
    assert out["after_drop_on_back"][0] == ["split", "dark", "private", "cleansite", "bookmark", "screenshot"]
    assert out["fixed"] == [0, 1, 2, 3, 4, True, True, True, True, True, True]
    saved_order, saved_left = out["final_saved"]
    assert [k for k in saved_left if k != "pip"] == out["final"][0]
    assert [k for k in saved_order if k != "pip"][:len(out["final"][0])] == out["final"][0]

    # the arrangement is there at the next start
    again = run_ike(HELPERS + r'''
def steps(ike, qapp, out):
    yield 600
    out["keys"] = keys(ike.windows[0])
    ''', keep_profile=True, env=screen(tmp_path, 1600, 900))   # a window never larger than the screen (1.1.21)
    assert again["keys"] == out["final"]


def test_customise_mode(run_ike):
    out = run_ike(HELPERS + r'''
def steps(ike, qapp, out):
    win = ike.windows[0]
    win.showNormal()
    win.resize(1400, 800)
    yield 600
    fired = []
    win.act_tb_reader.triggered.connect(lambda *_a: fired.append("reader"))
    m = win.toolbar_mover
    out["off"] = [win.custom_bar.isVisible(), m.overlay.isVisible(), m.customising]
    win.act_customise.trigger()
    yield 300
    left, right = keys(win)
    out["on"] = [win.custom_bar.isVisible(), m.overlay.isVisible(), m.customising,
                 len(m.overlay.outlines), len(left) + len(right)]
    # the outlines are on the buttons
    out["outlines_match"] = all(
        any(r.contains(button(win, k).mapTo(win.nav, button(win, k).rect().center())) for r in m.overlay.outlines)
        for k in left + right)
    # a click arranges nothing and does not run the button
    b = button(win, "reader")
    ev(b, QEvent.Type.MouseButtonPress, centre(b), LEFT_BTN, LEFT_BTN)
    yield 40
    ev(b, QEvent.Type.MouseButtonRelease, centre(b), LEFT_BTN, NO_BTN)
    yield 100
    out["click_in_mode"] = [list(fired), keys(win) == (left, right)]
    # the fixed shield has no outline: it is not arranged
    sc = win.shield_btn.mapTo(win.nav, win.shield_btn.rect().center())
    out["shield_outlined"] = any(r.contains(sc) for r in m.overlay.outlines)
    # dragging starts at once, without the long press
    yield from drag(win, "reader", after(win, "bookmark"), hold=30)
    out["dragged"] = keys(win)
    yield from drag(win, "dark", after(win, "downloads"), hold=30)
    out["shield_moved"] = keys(win)
    yield 100
    out["outlines_after"] = len(m.overlay.outlines)
    # show a hidden button from the strip's menu, hide another one
    menu = win.custom_bar.findChildren(QWidget)
    from PyQt6.QtWidgets import QMenu
    choose = win.custom_bar.findChild(QMenu)
    choose.aboutToShow.emit()
    entries = {a.data(): a for a in choose.actions()}
    out["entries"] = sorted(entries)
    entries["pip"].setChecked(True)
    choose.triggered.emit(entries["pip"])
    yield 200
    choose.aboutToShow.emit()
    entries = {a.data(): a for a in choose.actions()}
    entries["home"].setChecked(False)
    choose.triggered.emit(entries["home"])
    yield 200
    out["shown_dark"] = "pip" in keys(win)[0]
    out["home_hidden"] = [win.act_home.isVisible(), win.home_sep_act.isVisible(), win.act_back.isVisible()]
    out["outlines_with_dark"] = len(m.overlay.outlines)
    out["saved"] = [list(ike.config["toolbar_order"]), list(ike.config["toolbar_left"]),
                    sorted(ike.config["toolbar_hidden"])]
    import os
    if os.environ.get("IKE_TEST_SHOTS"):
        win.grab().save(os.path.join(os.environ["IKE_TEST_SHOTS"], "toolbar-customise.png"))
    # a second window shows the same arrangement
    second = ike.new_window()
    yield 500
    out["second"] = keys(second)
    out["second_mode"] = [second.custom_bar.isVisible(), second.toolbar_mover.customising]
    second.close()
    yield 200
    # reset
    from PyQt6.QtWidgets import QToolButton
    reset = [w for w in win.custom_bar.findChildren(QToolButton) if w.text().startswith("Reset")][0]
    reset.click()
    yield 300
    out["reset"] = [keys(win), sorted(ike.config["toolbar_hidden"]), list(ike.config["toolbar_order"]),
                    list(ike.config["toolbar_left"]), win.act_home.isVisible(), win.home_sep_act.isVisible()]
    out["still_on"] = m.customising
    # Esc leaves the mode
    from PyQt6.QtTest import QTest
    win.activateWindow()
    yield 200
    out["active"] = qapp.activeWindow() is win
    QTest.keyClick(win, Qt.Key.Key_Escape)
    yield 200
    out["left_mode"] = [win.custom_bar.isVisible(), m.overlay.isVisible(), m.customising]
    fired.clear()
    b = button(win, "reader")
    ev(b, QEvent.Type.MouseButtonPress, centre(b), LEFT_BTN, LEFT_BTN)
    yield 40
    ev(b, QEvent.Type.MouseButtonRelease, centre(b), LEFT_BTN, NO_BTN)
    yield 100
    out["click_after"] = list(fired)
    ''', settings={"start_maximized": False}, env={"IKE_TEST_SHOTS": SHOTS}, timeout=150)
    assert out["off"] == [False, False, False]
    assert out["on"][:3] == [True, True, True] and out["on"][3] == out["on"][4] == 8
    assert out["outlines_match"] and out["shield_outlined"] is False
    assert out["click_in_mode"] == [[], True]
    assert out["dragged"] == [LEFT_DEFAULT, ["bookmark", "reader", "downloads"]]
    assert out["shield_moved"] == [["private", "cleansite", "screenshot", "split"],
                                   ["bookmark", "reader", "downloads", "dark"]]
    assert out["outlines_after"] == 8
    assert out["entries"] == sorted(k for k, _h in TOOLBAR_ITEMS)
    assert out["shown_dark"] and out["outlines_with_dark"] == 9
    assert out["home_hidden"] == [False, True, True]
    order, left, hidden = out["saved"]
    assert left == ["private", "cleansite", "screenshot", "split", "pip"]
    assert [k for k in order if k not in NEW_KEYS][-1] == "dark"          # (the hidden new ones stay after it)
    assert sorted(order) == sorted(KEYS + NEW_KEYS) and hidden == sorted(["home"] + NEW_KEYS)
    assert out["second"] == [["private", "cleansite", "screenshot", "split", "pip"],
                             ["bookmark", "reader", "downloads", "dark"]]
    assert out["second_mode"] == [False, False]
    keys_after, hidden, order, left, home, sep = out["reset"]
    assert keys_after == [LEFT_DEFAULT, RIGHT_DEFAULT]
    assert hidden == sorted(["pip"] + NEW_KEYS)
    assert order == DEFAULTS["toolbar_order"] and left == DEFAULTS["toolbar_left"] and home and sep
    assert out["still_on"] is True
    assert out["left_mode"] == [False, False, False]
    assert out["click_after"] == ["reader"]


SIZES = r'''
def check(win, least=180):
    """Problems of the toolbar as it is now."""
    bad = []
    nav = win.nav
    items = []
    for a in nav.actions():
        w = nav.widgetForAction(a)
        if w is None or not a.isVisible() or not w.isVisible():
            continue
        r = QRect(w.mapTo(nav, QPoint(0, 0)), w.size())
        items.append((w.property("ikeToolbarKey") or w.objectName() or type(w).__name__, r, a))
    for (n1, r1, _a), (n2, r2, _b) in zip(items, items[1:]):
        if r1.right() >= r2.left() + 1 and r1.width() > 0 and r2.width() > 0:
            bad.append("overlap %s/%s" % (n1, n2))
    for name, r, _a in items:
        if r.left() < 0 or r.right() > nav.width() or r.top() < 0 or r.bottom() > nav.height():
            bad.append("outside %s" % name)
    acts = [a for _n, _r, a in items]
    def at(a):
        return acts.index(a) if a in acts else None
    fixed = [at(a) for a in (win.act_back, win.act_fwd, win.act_home, win.act_reload, win.home_sep_act)]
    if fixed != [0, 1, 2, 3, 4]:
        bad.append("fixed %s" % fixed)
    if at(win.urlbar_act) is None:
        bad.append("address bar hidden")
    elif not (win.shield_btn.parentWidget() is win.urlbar and win.shield_btn.geometry().right() > win.urlbar.width() - 20):
        bad.append("shield not inside the address bar at its right end")
    elif win.urlbar.width() < least:
        bad.append("address bar %d" % win.urlbar.width())
    ext = nav.findChild(QWidget, "qt_toolbar_ext_button")
    if ext is not None and ext.isVisible():
        bad.append("Qt's own overflow button")
    # the menu, the shield and the window buttons are always in view, the window buttons last
    if win.shield_btn.isHidden():
        bad.append("missing shield")
    for a in (win.menu_act,) + tuple(win._win_btns):
        if at(a) is None:
            bad.append("missing %s" % (nav.widgetForAction(a).property("ikeToolbarKey") or "window button"))
    if [at(a) for a in win._win_btns] != list(range(len(acts) - len(win._win_btns), len(acts))):
        bad.append("window buttons not last")
    # every button to show is either in the toolbar or under the » button, never both, never lost
    left, right = keys(win)
    listed = [a.text() for a in win.more_menu.actions()]
    by_key = {k: a for k, a, _x in win._nav_items}
    lay = win.toolbar_layout
    want = lay.shown("left") + lay.shown("right")
    spilled = [k for k in want if k in win.toolbar_spilled]
    if sorted(left + right + spilled) != sorted(want) or set(left + right) & set(spilled):
        bad.append("lost or doubled: %s + %s" % (left + right, spilled))
    if listed != [by_key[k].text() for k in spilled]:
        bad.append("» lists %s, not %s" % (listed, spilled))
    if win.more_act.isVisible() != bool(spilled) or (spilled and at(win.more_act) is None):
        bad.append("» shown %s with %d buttons" % (win.more_act.isVisible(), len(spilled)))
    if [k for k in want if k not in spilled] != left + right:
        bad.append("order %s" % (left + right))
    return bad
'''


@pytest.mark.parametrize("scale", ["1", "1.5", "2"])
def test_toolbar_at_other_sizes_and_scales(run_ike, scale):
    out = run_ike(HELPERS + "from PyQt6.QtCore import QRect\n" + SIZES + r'''
def steps(ike, qapp, out):
    win = ike.windows[0]
    win.showNormal()
    out["ratio"] = win.devicePixelRatioF()
    out["checks"] = {}
    def note(name, least=180):
        ub = win.urlbar
        out["checks"][name] = [check(win, least), ub.width(), win.width(),
                               ub.mapTo(win, QPoint(ub.width() // 2, 0)).x(), sorted(win.toolbar_spilled),
                               win._nav_spacers[0].width()]
    # every button shown, some moved to the left: the fullest toolbar there can be
    ike.config["toolbar_hidden"] = []
    ike.config["toolbar_left"] = ["dark", "private", "cleansite", "screenshot", "split", "pip", "bookmark"]
    ike.refresh_toolbars()
    for width in (2560, 1920, 1280, 1024, 900, 800, 700, 640, 560, 1366, 3840):
        win.resize(width, 700)
        yield 450
        # Back, Forward, Home, Reload and the shield never go under the » button (1.1.9):
        # in a very narrow window with every button shown the bar keeps a little less
        note("full-%d" % width, least=140 if width <= 560 else 180)
    # the default toolbar
    win.reset_toolbar()
    for width in (1920, 1280, 800, 640, 560):
        win.resize(width, 700)
        yield 450
        note("default-%d" % width, least=140 if width <= 560 else 180)
    win.resize(480, 700)
    yield 450
    note("default-480", least=80)      # the fixed buttons first (1.1.9)
    # a button listed under » still works from there
    fired = []
    win.act_downloads.triggered.disconnect()
    win.act_downloads.triggered.connect(lambda *_a: fired.append("downloads"))
    listed = {a.text(): a for a in win.more_menu.actions()}
    out["under_more"] = sorted(win.toolbar_spilled)
    listed[win.act_downloads.text()].trigger()
    out["fired"] = list(fired)
    # ... and comes back when there is room again
    win.resize(1500, 700)
    yield 500
    note("default-1500")
    # moving still lands where the mouse is
    yield from drag(win, "downloads", before(win, "dark"))
    out["moved"] = keys(win)
    yield from drag(win, "bookmark", after(win, "reader"))
    out["moved_back"] = keys(win)
    out["end"] = check(win)
    import os
    if os.environ.get("IKE_TEST_SHOTS"):
        win.resize(600, 500)
        yield 400
        win.grab().save(os.path.join(os.environ["IKE_TEST_SHOTS"], "toolbar-narrow-x%s.png" % os.environ["QT_SCALE_FACTOR"]))
    ''', settings={"system_titlebar": False, "start_maximized": False},
                  env={"QT_SCALE_FACTOR": scale, "IKE_TEST_SHOTS": SHOTS}, timeout=180)
    assert abs(out["ratio"] - float(scale)) < 0.01
    for name, (bad, bar, width, centre, spilled, pad) in out["checks"].items():
        assert bad == [], (name, bad)
        if width >= 1280:
            assert spilled == [], (name, spilled)
        if name.startswith("default") and width >= 1280:
            # the usual case: the address bar has its share of the window, in the middle - or,
            # where the left side's buttons leave too little room, as near to it as it gets
            # (1.1.9's default shows nine buttons besides the fixed ones: at 1280 px the bar
            # gets the room that is left, a little under half the window)
            assert bar >= width * (0.5 if width >= 1600 else 0.45), (name, bar, width)
            assert abs(centre - width / 2) <= 1 or (pad == 0 and centre > width / 2), (name, centre, pad)
    assert out["checks"]["full-560"][4] and out["checks"]["default-480"][4]
    assert "downloads" in out["under_more"] and out["fired"] == ["downloads"]
    assert out["moved"] == [["downloads"] + LEFT_DEFAULT, ["bookmark", "reader"]]
    assert out["moved_back"] == [["downloads"] + LEFT_DEFAULT, ["reader", "bookmark"]]
    assert out["end"] == []


def test_toolbar_reads_old_and_damaged_settings(run_ike):
    """Settings from before a button existed, with unknown names, doubles or the
    wrong type never break the toolbar: every button is there once."""
    for settings in ({"toolbar_order": ["menu", "reader", "nothing", "reader"], "toolbar_left": ["menu", "nothing"],
                      "toolbar_hidden": ["shield", "menu", "nothing"]},
                     {"toolbar_order": "reload", "toolbar_left": 5, "toolbar_hidden": []},
                     {"toolbar_order": [], "toolbar_left": [], "toolbar_hidden": ["back", "forward", "home"]}):
        out = run_ike(HELPERS + r'''
def steps(ike, qapp, out):
    yield 500
    win = ike.windows[0]
    out["keys"] = keys(win)
    out["fixed"] = [win.act_back.isVisible(), win.act_fwd.isVisible(), win.act_home.isVisible(),
                    win.act_reload.isVisible(), win.home_sep_act.isVisible(), not win.shield_btn.isHidden()]
    out["menu"] = win.menu_act.isVisible() and win.nav.actions().index(win.menu_act) == win.nav.actions().index(win._win_btns[0]) - 1
    out["hidden"] = list(ike.config["toolbar_hidden"])
        ''', settings=settings)
        left, right = out["keys"]
        shown = left + right
        assert len(shown) == len(set(shown)) and "menu" not in shown and out["menu"], (settings, out)
        if settings["toolbar_left"] == ["menu", "nothing"]:
            assert left == [] and right[0] == "reader"     # the menu of old settings: fixed now (1.1.16)
        if "back" in settings["toolbar_hidden"]:
            assert out["fixed"] == [False, False, False, True, True, True]     # Reload is still there
        else:
            assert out["fixed"] == [True, True, True, True, True, True]
