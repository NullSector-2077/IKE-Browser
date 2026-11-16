"""The navigation toolbar: its layout model, moving buttons with real mouse
events (long press and "Customise toolbar" mode), what is saved, and how the
toolbar behaves at other window sizes and screen scales."""

import json
import os
import random

import pytest

from ike.config import DEFAULTS, TOOLBAR_ITEMS
from ike.toolbar import LEFT, RIGHT, ToolbarLayout, default_layout

SHOTS = os.environ.get("IKE_TEST_SHOTS", "")
KEYS = ["shield", "reload", "translate", "reader", "screenshot", "pip", "split", "dark", "private",
        "cleansite", "downloads", "menu"]


# ----------------------------------------------------------------------
# the model
# ----------------------------------------------------------------------
def test_layout_from_settings():
    lay = ToolbarLayout(KEYS, DEFAULTS["toolbar_order"], DEFAULTS["toolbar_left"], ["split", "dark"])
    assert lay.left == ["shield", "reload", "translate"]
    assert lay.right == ["reader", "screenshot", "pip", "split", "dark", "private", "cleansite", "downloads", "menu"]
    assert lay.shown(RIGHT) == ["reader", "screenshot", "pip", "private", "cleansite", "downloads", "menu"]
    # every key once, whatever the settings hold
    for order, left, hidden in (
            ([], [], []),
            (None, None, None),
            ("reload", {"a": 1}, 7),
            (["menu", "menu", "gone", 3, None, "reader", "reader"], ["reader", "gone", 5], ["gone", "shield", "menu"]),
            (list(reversed(KEYS)), KEYS, KEYS)):
        lay = ToolbarLayout(KEYS, order, left, hidden)
        assert sorted(lay.left + lay.right) == sorted(KEYS), (order, left)
        assert not ({"shield", "menu"} & lay.hidden)            # never hidden
        assert "shield" in lay.shown(lay.zone_of("shield")) and "menu" in lay.shown(lay.zone_of("menu"))
    # settings written before a button existed: it joins the right zone, before the menu
    old = [k for k in DEFAULTS["toolbar_order"] if k not in ("pip", "cleansite")]
    lay = ToolbarLayout(KEYS, old, ["shield"], [])
    assert lay.right[-3:] == ["pip", "cleansite", "menu"] and lay.left == ["shield"]
    # a button the program no longer has is forgotten
    lay = ToolbarLayout(KEYS[:-2] + ["menu"], DEFAULTS["toolbar_order"], [], [])
    assert "downloads" not in lay.left + lay.right


def test_layout_moves():
    lay = ToolbarLayout(KEYS, DEFAULTS["toolbar_order"], DEFAULTS["toolbar_left"], ["split", "dark"])
    assert lay.slot_of("reader") == (RIGHT, 0) and lay.slot_of("translate") == (LEFT, 2)
    assert not lay.move("reader", RIGHT, 0)                     # already there
    assert lay.move("reader", RIGHT, 2)
    assert lay.shown(RIGHT)[:3] == ["screenshot", "pip", "reader"]
    # it goes right before the shown button that had that place; hidden ones stay where they were
    assert lay.right == ["screenshot", "pip", "split", "dark", "reader", "private", "cleansite", "downloads", "menu"]
    assert lay.move("reader", LEFT, 0) and lay.left == ["reader", "shield", "reload", "translate"]
    assert lay.move("reader", LEFT, 99) and lay.left[-1] == "reader"
    assert lay.move("reader", RIGHT, 99) and lay.right[-1] == "reader"
    assert lay.move("reader", RIGHT, -5) and lay.right[0] == "reader"
    assert not lay.move("unknown", LEFT, 0) and not lay.move("reader", "middle", 0)
    # both zones can be emptied and filled again
    for key in list(lay.left):
        assert lay.move(key, RIGHT, 0)
    assert lay.left == [] and lay.shown(LEFT) == []
    assert lay.move("menu", LEFT, 0) and lay.left == ["menu"]
    # any sequence of moves keeps every key exactly once
    rng = random.Random(7)
    for _ in range(500):
        key = rng.choice(KEYS)
        lay.move(key, rng.choice((LEFT, RIGHT)), rng.randint(-2, 14))
        assert sorted(lay.left + lay.right) == sorted(KEYS)
        zone, index = lay.slot_of(key)
        assert lay.shown(zone)[index] == key if key not in lay.hidden else True


def test_layout_is_stored_and_read_back():
    lay = ToolbarLayout(KEYS, DEFAULTS["toolbar_order"], DEFAULTS["toolbar_left"], ["split"])
    lay.move("downloads", LEFT, 1)
    lay.move("shield", RIGHT, 3)
    cfg = {"toolbar_hidden": ["split"]}
    lay.store(cfg)
    assert cfg["toolbar_hidden"] == ["split"]                   # not this function's business
    assert json.loads(json.dumps(cfg)) == cfg
    again = ToolbarLayout.from_config(cfg, KEYS)
    assert (again.left, again.right, again.hidden) == (lay.left, lay.right, lay.hidden)
    first = default_layout(KEYS, DEFAULTS, TOOLBAR_ITEMS)
    assert first.left == DEFAULTS["toolbar_left"] and first.left + first.right == DEFAULTS["toolbar_order"]
    assert first.hidden == {"split", "dark", "private", "cleansite"}


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
    first_button = button(win, "reader")
    shape = geometry(win)

    # 1. long press, then drag past Downloads
    moves = []
    yield from drag(win, "reader", after(win, "downloads"), moves_out=moves)
    out["moves"] = [[m[0], m[1], m[2], m[3]] for m in moves]
    out["toolbar_untouched_during_drag"] = all(m[4] == out["start"] and m[5] == shape for m in moves)
    out["after_first"] = keys(win)
    out["saved_first"] = [list(ike.config["toolbar_order"]), list(ike.config["toolbar_left"])]
    out["rebuilt"] = button(win, "reader") is not first_button
    out["ghost_gone"] = [win.toolbar_mover._ghost is None, win.toolbar_mover.overlay.isVisible()]
    out["status_after"] = [win.statusBar().isVisible(), win.statusBar().currentMessage()]

    # 2. the rebuilt button can be moved again, to the other side of the address bar
    yield from drag(win, "reader", before(win, "reload"))
    out["after_second"] = keys(win)

    # 3. a press shorter than the long press, then a move: nothing moves, and it is a click
    yield from drag(win, "reader", after(win, "menu"), hold=150)
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
    far = after(win, "menu") + QPoint(0, 300)
    yield from drag(win, "screenshot", far)
    out["cancelled"] = [keys(win) == was, list(fired), win.toolbar_mover._ghost is None]

    # 6. the fixed buttons: no key, a long press and drag does nothing
    home = win.nav.widgetForAction(win.act_home)
    out["home_key"] = home.property("ikeToolbarKey")
    ev(home, QEvent.Type.MouseButtonPress, centre(home), LEFT_BTN, LEFT_BTN)
    yield 900
    for x in (40, 120, 300):
        ev(home, QEvent.Type.MouseMove, centre(home) + QPoint(x, 0), NO_BTN, LEFT_BTN)
        yield 15
    ev(home, QEvent.Type.MouseButtonRelease, centre(home) + QPoint(300, 0), LEFT_BTN, NO_BTN)
    yield 150
    out["after_home_drag"] = keys(win) == was
    # dropped on Back: the button becomes the first of the left zone, after the separator
    yield from drag(win, "pip", centre(win.nav.widgetForAction(win.act_back)))
    out["after_drop_on_back"] = keys(win)
    acts = win.nav.actions()
    out["fixed"] = [acts.index(win.act_back), acts.index(win.act_fwd), acts.index(win.act_home),
                    acts.index(win.home_sep_act), acts[3].isSeparator(), acts.index(win._win_btns[0]) > acts.index(win.urlbar_act),
                    [acts.index(a) for a in win._win_btns] == sorted(acts.index(a) for a in win._win_btns),
                    acts[-1] is win._win_btns[-1]]
    out["final"] = keys(win)
    out["final_saved"] = [list(ike.config["toolbar_order"]), list(ike.config["toolbar_left"])]
    ''', settings={"system_titlebar": False, "start_maximized": False}, timeout=150)
    left, right = out["start"]
    assert left == ["shield", "reload", "translate"] and right == ["reader", "screenshot", "pip", "downloads", "menu"]
    # the drag: a marker and a ghost from the first real move, the toolbar itself untouched
    assert all(m[0] and m[2] and m[3] and isinstance(m[1], int) for m in out["moves"]), out["moves"]
    assert out["toolbar_untouched_during_drag"]
    assert len({m[1] for m in out["moves"]}) <= 5              # the marker snaps to the few places between buttons
    assert out["after_first"] == [left, ["screenshot", "pip", "downloads", "reader", "menu"]]
    order, saved_left = out["saved_first"]
    assert saved_left == left and order.index("downloads") < order.index("reader") < order.index("menu")
    assert sorted(order) == sorted(KEYS)
    assert out["rebuilt"] and out["ghost_gone"] == [True, False]
    assert out["status_after"] == [False, ""]
    assert out["after_second"] == [["shield", "reader", "reload", "translate"], ["screenshot", "pip", "downloads", "menu"]]
    assert out["after_short"] == out["after_second"]
    assert out["click"] == ["screenshot"]
    assert out["hint"][0] is True and out["hint"][1]
    assert out["long_press_no_click"] == [] and out["hint_gone"] == [False, "", False]
    assert out["cancelled"] == [True, [], True]
    assert not out["home_key"] and out["after_home_drag"]
    assert out["after_drop_on_back"][0] == ["pip", "shield", "reader", "reload", "translate"]
    assert out["fixed"] == [0, 1, 2, 3, True, True, True, True]
    assert out["final_saved"][0][:5] == out["final"][0] and out["final_saved"][1] == out["final"][0]

    # the arrangement is there at the next start
    again = run_ike(HELPERS + r'''
def steps(ike, qapp, out):
    yield 600
    out["keys"] = keys(ike.windows[0])
    ''', keep_profile=True)
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
    # the shield's panel does not open either
    s = button(win, "shield")
    ev(s, QEvent.Type.MouseButtonPress, centre(s), LEFT_BTN, LEFT_BTN)
    ev(s, QEvent.Type.MouseButtonRelease, centre(s), LEFT_BTN, NO_BTN)
    yield 150
    out["shield_menu_open"] = win.shield_menu.isVisible()
    # dragging starts at once, without the long press
    yield from drag(win, "reader", after(win, "translate"), hold=30)
    out["dragged"] = keys(win)
    yield from drag(win, "shield", after(win, "menu"), hold=30)
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
    entries["dark"].setChecked(True)
    choose.triggered.emit(entries["dark"])
    yield 200
    choose.aboutToShow.emit()
    entries = {a.data(): a for a in choose.actions()}
    entries["home"].setChecked(False)
    choose.triggered.emit(entries["home"])
    yield 200
    out["shown_dark"] = "dark" in keys(win)[1]
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
    assert out["outlines_match"]
    assert out["click_in_mode"] == [[], True]
    assert out["shield_menu_open"] is False
    assert out["dragged"] == [["shield", "reload", "translate", "reader"], ["screenshot", "pip", "downloads", "menu"]]
    assert out["shield_moved"] == [["reload", "translate", "reader"], ["screenshot", "pip", "downloads", "menu", "shield"]]
    assert out["outlines_after"] == 8
    assert out["entries"] == sorted(k for k, _h in TOOLBAR_ITEMS)
    assert out["shown_dark"] and out["outlines_with_dark"] == 9
    assert out["home_hidden"] == [False, True, True]
    order, left, hidden = out["saved"]
    assert left == ["reload", "translate", "reader"] and order[-1] == "shield" and sorted(order) == sorted(KEYS)
    assert hidden == ["cleansite", "home", "private", "split"]
    assert out["second"] == [["reload", "translate", "reader"], ["screenshot", "pip", "dark", "downloads", "menu", "shield"]]
    assert out["second_mode"] == [False, False]
    keys_after, hidden, order, left, home, sep = out["reset"]
    assert keys_after == [["shield", "reload", "translate"], ["reader", "screenshot", "pip", "downloads", "menu"]]
    assert hidden == ["cleansite", "dark", "private", "split"]
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
    fixed = [at(a) for a in (win.act_back, win.act_fwd, win.act_home, win.home_sep_act)]
    if fixed != [0, 1, 2, 3]:
        bad.append("fixed %s" % fixed)
    if at(win.urlbar_act) is None:
        bad.append("address bar hidden")
    elif win.urlbar.width() < least:
        bad.append("address bar %d" % win.urlbar.width())
    ext = nav.findChild(QWidget, "qt_toolbar_ext_button")
    if ext is not None and ext.isVisible():
        bad.append("Qt's own overflow button")
    # the menu, the shield and the window buttons are always in view, the window buttons last
    for a in (win.shield_act, win.menu_act) + tuple(win._win_btns):
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
                               ub.mapTo(win, QPoint(ub.width() // 2, 0)).x(), sorted(win.toolbar_spilled)]
    # every button shown, some moved to the left: the fullest toolbar there can be
    ike.config["toolbar_hidden"] = []
    ike.config["toolbar_left"] = ["shield", "reload", "translate", "dark", "split"]
    ike.refresh_toolbars()
    for width in (2560, 1920, 1280, 1024, 900, 800, 700, 640, 560, 1366, 3840):
        win.resize(width, 700)
        yield 450
        note("full-%d" % width)
    # the default toolbar
    win.reset_toolbar()
    for width in (1920, 1280, 800, 640, 560):
        win.resize(width, 700)
        yield 450
        note("default-%d" % width)
    win.resize(480, 700)
    yield 450
    note("default-480", least=120)
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
    yield from drag(win, "downloads", before(win, "shield"))
    out["moved"] = keys(win)
    yield from drag(win, "translate", after(win, "menu"))
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
    for name, (bad, bar, width, centre, spilled) in out["checks"].items():
        assert bad == [], (name, bad)
        if width >= 1280:
            assert spilled == [], (name, spilled)
        if name.startswith("default") and width >= 1280:
            # the usual case: the address bar has its share of the window, in the middle
            assert bar >= width * 0.5 and abs(centre - width / 2) <= 1, (name, bar, width, centre)
    assert out["checks"]["full-560"][4] and out["checks"]["default-480"][4]
    assert "downloads" in out["under_more"] and out["fired"] == ["downloads"]
    assert out["moved"] == [["downloads", "shield", "reload", "translate"], ["reader", "screenshot", "pip", "menu"]]
    assert out["moved_back"] == [["downloads", "shield", "reload"], ["reader", "screenshot", "pip", "menu", "translate"]]
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
                    win.home_sep_act.isVisible()]
    out["hidden"] = list(ike.config["toolbar_hidden"])
        ''', settings=settings)
        left, right = out["keys"]
        shown = left + right
        assert len(shown) == len(set(shown)) and {"shield", "menu"} <= set(shown), (settings, out["keys"])
        if settings["toolbar_left"] == ["menu", "nothing"]:
            assert left == ["menu"] and right[0] == "reader"
        if "back" in settings["toolbar_hidden"]:
            assert out["fixed"] == [False, False, False, False]
        else:
            assert out["fixed"] == [True, True, True, True]
