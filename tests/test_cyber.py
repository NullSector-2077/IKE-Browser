"""The "I.K.E. Cyber" theme in the browser's windows (ike/cyber.py): the tab
shapes, the address field, what happens when the theme is switched on and
off, and that "Follow the system" is left exactly as it was."""

import sys

import pytest
from conftest import ROOT
from test_security import JS

sys.path.insert(0, str(ROOT))

COMMON = JS + r'''
from PyQt6.QtGui import QColor

def near(colour, other, tol=40):
    a, b = QColor(colour), QColor(other)
    return abs(a.red() - b.red()) + abs(a.green() - b.green()) + abs(a.blue() - b.blue()) <= tol

def count_near(image, colour, tol=40):
    n = 0
    for y in range(0, image.height()):
        for x in range(0, image.width()):
            if near(image.pixelColor(x, y), colour, tol):
                n += 1
    return n

def tabs(win, n=3):
    for _ in range(n):
        win.add_tab("ike:newtab")
'''


def test_shapes_stay_inside_their_rectangle():
    from PyQt6.QtCore import QPointF, QRectF

    from ike import cyber

    for w, h in ((200, 36), (90, 30), (40, 24), (12, 8), (3, 3), (400, 60)):
        rect = QRectF(10, 5, w, h)
        for shape in cyber.SHAPES:
            for path in (cyber.tab_path(rect, shape, 10), cyber.row_path(rect, shape, 10)):
                assert rect.adjusted(-0.01, -0.01, 0.01, 0.01).contains(path.boundingRect()), (shape, w, h)
                assert path.contains(rect.center())
    rect = QRectF(0, 0, 200, 36)
    assert not cyber.tab_path(rect, "smusso", 10).contains(QPointF(2, 2))          # the cut corner
    assert cyber.tab_path(rect, "smusso", 0).contains(QPointF(2, 2))               # "cut corners" off
    assert not cyber.tab_path(rect, "lama", 10).contains(QPointF(2, 2))            # the slant
    assert cyber.tab_path(rect, "lama", 10).contains(QPointF(2, 34))
    assert cyber.tab_path(rect, "mirino", 10).contains(QPointF(2, 2))
    both = cyber.cut_path(rect, 8, "tl br")
    assert not both.contains(QPointF(1, 1)) and not both.contains(QPointF(198, 35)) and both.contains(QPointF(198, 1))


@pytest.mark.parametrize("shape", ["smusso", "lama", "mirino"])
def test_cyber_tabs_are_drawn_and_work(run_ike, shape):
    out = run_ike(COMMON + r'''
def steps(ike, qapp, out):
    from ike import cyber
    win = ike.windows[0]
    tabs(win)
    yield 1200
    bar = win.tabbar
    out["style"] = type(bar.style()).__name__
    bar.setCurrentIndex(1)
    yield 600
    lk = cyber.look(ike.config)
    image = bar.grab().toImage()
    r = bar.tabRect(1)
    out["accent_on_current"] = count_near(image.copy(r), lk.accent) > 12
    out["accent_elsewhere"] = count_near(image.copy(bar.tabRect(2)), lk.accent)
    out["fill_differs"] = image.pixelColor(r.center().x() + 30, r.bottom() - 4).name() != \
        image.pixelColor(bar.tabRect(3).center().x() + 30, bar.tabRect(3).bottom() - 4).name()
    out["corner"] = [image.pixelColor(r.left() + 2, r.top() + 2).name(), image.pixelColor(r.left() + 30, r.top() + 12).name()]
    # the tabs go on working: move, close, titles
    first, second = win.views[0], win.views[1]
    bar.moveTab(0, 2)
    yield 300
    out["moved"] = win.views.index(first) == 2 and win.views.index(second) == 0
    n = len(win.views)
    bar.tabCloseRequested.emit(1)
    yield 400
    out["closed"] = len(win.views) == n - 1 and bar.count() == n - 1
    out["text"] = bar.tabText(0)
    out["tab_height"] = r.height()
''', settings={"ui_scheme": "theme:cyber", "cyber_shape": shape, "cyber_hint": "done"}, timeout=120)
    assert out["style"] == "TabStyle"
    assert out["accent_on_current"] is True and out["accent_elsewhere"] == 0
    assert out["fill_differs"] is True
    if shape in ("smusso", "lama"):
        assert out["corner"][0] != out["corner"][1]            # the corner is cut away
    assert out["moved"] is True and out["closed"] is True and out["text"]
    assert out["tab_height"] >= 28


def test_cyber_vertical_tabs_and_the_address_field(run_ike):
    out = run_ike(COMMON + r'''
def steps(ike, qapp, out):
    from ike import cyber
    win = ike.windows[0]
    tabs(win)
    yield 1200
    win.vtabs.setCurrentRow(2)
    yield 600
    lk = cyber.look(ike.config)
    delegate = win.vtabs.itemDelegate()
    out["look"] = delegate.look is not None
    port = win.vtabs.viewport()
    image = port.grab().toImage()
    row = win.vtabs.visualItemRect(win.vtabs.item(2))
    out["accent_on_current"] = count_near(image.copy(row), lk.accent) > 12
    out["accent_elsewhere"] = count_near(image.copy(win.vtabs.visualItemRect(win.vtabs.item(0))), lk.accent)
    out["text_drawn"] = count_near(image.copy(row), lk.text, 60) > 20
    out["rows"] = win.vtabs.count() == len(win.views)
    # close through the row's own button area still works
    n = len(win.views)
    delegate.close_requested.emit(0)
    yield 400
    out["closed"] = len(win.views) == n - 1
    field = win.urlbar
    out["frame"] = [field.hasFrame(), field.cyber is not None]
    img = field.grab().toImage()
    out["field_line"] = count_near(img, lk.mix(lk.toolbar, lk.text, 0.22), 30) > 40 or count_near(img, lk.accent) > 40
    out["field_corner"] = img.pixelColor(1, 1).name() != img.pixelColor(20, img.height() // 2).name()
    field.setText("https://example.org/a/long/address?with=things")
    out["text"] = field.text()
''', settings={"ui_scheme": "theme:cyber", "tabs_position": "vertical", "cyber_hint": "done"}, timeout=120)
    assert out["look"] is True and out["rows"] is True
    assert out["accent_on_current"] is True and out["accent_elsewhere"] == 0 and out["text_drawn"] is True
    assert out["closed"] is True
    assert out["frame"] == [False, True] and out["field_line"] is True and out["field_corner"] is True
    assert out["text"].startswith("https://example.org/")


def test_follow_the_system_is_left_alone(run_ike):
    """The default: none of the Cyber code touches the window."""
    out = run_ike(COMMON + r'''
def steps(ike, qapp, out):
    from PyQt6.QtWidgets import QMenu
    win = ike.windows[0]
    tabs(win, 2)
    yield 1000
    out["style"] = type(win.tabbar.style()).__name__
    out["app_style"] = type(qapp.style()).__name__
    out["same_style"] = win.tabbar.style() is qapp.style()
    out["delegate"] = win.vtabs.itemDelegate().look is None
    out["field"] = [win.urlbar.hasFrame(), win.urlbar.cyber is None]
    out["sheets"] = [win.nav.styleSheet(), win.styleSheet(), qapp.styleSheet()]
    out["menus"] = [m.styleSheet() for m in win.findChildren(QMenu) if m.styleSheet()]
    out["marks"] = [type(c).__name__ for c in win.tabbar.children() if type(c).__name__ == "MarkGlide"]
    out["cyber"] = getattr(win, "_cyber", None) is None
''', timeout=120)
    assert out["same_style"] is True and out["style"] == out["app_style"] != "TabStyle"
    assert out["delegate"] is True and out["field"] == [True, True]
    assert out["sheets"] == ["", "", ""] and out["menus"] == [] and out["marks"] == [] and out["cyber"] is True


def test_the_theme_goes_on_and_off_without_leftovers(run_ike):
    out = run_ike(COMMON + r'''
def steps(ike, qapp, out):
    from PyQt6.QtGui import QPalette
    from PyQt6.QtWidgets import QMenu
    from ike import cyber, themes
    win = ike.windows[0]
    tabs(win, 2)
    yield 800
    R = QPalette.ColorRole
    def state():
        return {"style": type(win.tabbar.style()).__name__, "frame": win.urlbar.hasFrame(),
                "nav": bool(win.nav.styleSheet()), "look": win.vtabs.itemDelegate().look is not None,
                "menus": sum(1 for m in win.findChildren(QMenu) if m.styleSheet()),
                "marks": sum(1 for c in win.tabbar.children() if type(c).__name__ == "MarkGlide"),
                "window": qapp.palette().color(R.Window).name(),
                "field_base": win.urlbar.palette().color(R.Base).alpha()}
    out["system"] = state()
    for scheme, accent, key in (("theme:cyber", "", "on"), ("theme:cyber", "#ff5fa8", "accent"),
                                ("theme:night", "", "other"), ("theme:cyber", "", "on_again"), ("system", "", "off")):
        ike.config["ui_scheme"] = scheme
        ike.config["cyber_accent"] = accent
        themes.apply(ike.config)
        yield 400
        out[key] = state()
        lk = cyber.look(ike.config)
        out[key]["accent"] = lk.accent.name() if lk else None
    out["tabs_work"] = len(win.views) == win.tabbar.count() == win.vtabs.count()
''', settings={"cyber_hint": "done"}, timeout=120)
    system = out["system"]
    assert system["style"] != "TabStyle" and system["frame"] and not system["nav"] and system["marks"] == 0
    on = out["on"]
    assert on["style"] == "TabStyle" and not on["frame"] and on["nav"] and on["look"] and on["menus"] > 3
    assert on["marks"] == 1 and on["window"] == "#070b14" and on["field_base"] == 0 and on["accent"] == "#2be4f5"
    assert out["accent"]["accent"] == "#ff5fa8" and out["accent"]["marks"] == 1         # replaced, not piled up
    other = out["other"]                              # another ready-made theme: colours only, no Cyber shapes
    assert other["style"] != "TabStyle" and other["frame"] and not other["nav"] and other["menus"] == 0
    assert other["marks"] == 0 and not other["look"] and other["window"] != "#070b14"
    assert out["on_again"]["style"] == "TabStyle" and out["on_again"]["marks"] == 1
    off = out["off"]
    assert {k: off[k] for k in system} == system      # exactly as before the theme was ever used
    assert out["tabs_work"] is True


def test_the_mark_glides_only_when_effects_are_wanted(run_ike):
    script = COMMON + r'''
def steps(ike, qapp, out):
    win = ike.windows[0]
    tabs(win)
    win.show()
    yield 1200
    glide = win._cyber["glides"][0]
    style = win._cyber["style"]
    win.tabbar.setCurrentIndex(0)
    yield 500
    win.tabbar.setCurrentIndex(3)
    seen = []
    for _ in range(30):
        seen.append([glide.isVisible(), style.gliding])
        yield 20
    out["during"] = any(v and g for v, g in seen)
    out["after"] = [glide.isVisible(), style.gliding]
'''
    settings = {"ui_scheme": "theme:cyber", "cyber_hint": "done"}
    moving = run_ike(script, settings=settings, env={"IKE_REDUCED_MOTION": "0"}, timeout=120)
    assert moving["during"] is True and moving["after"] == [False, False]
    still = run_ike(script, settings=settings, env={"IKE_REDUCED_MOTION": "1"}, timeout=120)
    assert still["during"] is False and still["after"] == [False, False]
    off = run_ike(script, settings=dict(settings, ui_effects=False), env={"IKE_REDUCED_MOTION": "0"}, timeout=120)
    assert off["during"] is False


def test_cyber_at_a_larger_scale(run_ike):
    out = run_ike(COMMON + r'''
def steps(ike, qapp, out):
    from ike import cyber
    win = ike.windows[0]
    tabs(win)
    yield 1200
    win.tabbar.setCurrentIndex(1)
    yield 500
    lk = cyber.look(ike.config)
    image = win.tabbar.grab().toImage()
    out["ratio"] = image.devicePixelRatio()
    out["accent"] = count_near(image, lk.accent) > 20
    out["style"] = type(win.tabbar.style()).__name__
''', settings={"ui_scheme": "theme:cyber", "cyber_shape": "lama", "cyber_hint": "done"},
                  env={"QT_SCALE_FACTOR": "1.5"}, timeout=120)
    assert out["style"] == "TabStyle" and out["accent"] is True and out["ratio"] == 1.5


def test_settings_show_the_choice_clearly(run_ike):
    out = run_ike(COMMON + r'''
def steps(ike, qapp, out):
    from ike.dialogs import SettingsDialog
    win = ike.windows[0]
    dlg = SettingsDialog(ike, win)
    dlg.show()
    yield 400
    combo = dlg.ui_scheme
    out["first"] = [combo.itemData(0), combo.currentData()]
    out["cyber_label"] = combo.itemText(combo.findData("theme:cyber"))
    out["hint_shown"] = [not dlg.cyber_hint.isHidden(), not dlg.cyber_box.isHidden()]
    dlg.cyber_try.click()
    yield 200
    out["after_try"] = [combo.currentData(), not dlg.cyber_hint.isHidden(), not dlg.cyber_box.isHidden()]
    dlg.cyber_shape.setCurrentIndex(dlg.cyber_shape.findData("lama"))
    dlg._pick_accent("#b6ff3c")
    dlg.cyber_glow.setChecked(False)
    dlg.nt_tiles.setCurrentIndex(dlg.nt_tiles.findData("visited"))
    dlg.nt_counter.setCurrentIndex(dlg.nt_counter.findData("total"))
    dlg.apply()
    yield 600
    cfg = ike.config
    out["saved"] = [cfg["ui_scheme"], cfg["cyber_shape"], cfg["cyber_accent"], cfg["cyber_glow"], cfg["cyber_corners"],
                    cfg["newtab_tiles"], cfg["blocked_counter"], cfg["cyber_hint"]]
    out["applied"] = type(win.tabbar.style()).__name__
    out["pages"] = [dlg.nav.item(i).text() for i in range(dlg.nav.count())]
    # and back to the default from the same place
    combo.setCurrentIndex(combo.findData("system"))
    dlg.apply()
    yield 400
    out["back"] = [cfg["ui_scheme"], type(win.tabbar.style()).__name__ != "TabStyle"]
    dlg.close()
''', timeout=120)
    assert out["first"] == ["system", "system"]                # the default is the desktop's look
    assert "recommended" in out["cyber_label"]
    assert out["hint_shown"] == [True, False]
    assert out["after_try"] == ["theme:cyber", False, True]
    assert out["saved"] == ["theme:cyber", "lama", "#b6ff3c", False, True, "visited", "total", "done"]
    assert out["applied"] == "TabStyle" and "New tab page" in out["pages"]
    assert out["back"] == ["system", True]


def test_the_small_moving_things(run_ike):
    """The shield's pulse, the equaliser of a tab that plays sound, the ring of
    the shield panel, the frame of the tab preview, the soft change of theme."""
    out = run_ike(COMMON + r'''
def steps(ike, qapp, out):
    from PyQt6.QtWidgets import QLabel
    from ike import cyber, effects
    from ike.tabpreview import TabPreview
    win = ike.windows[0]
    win.show()
    yield 1000
    lk = cyber.look(ike.config)
    pulse = win._cyber["pulse"]
    pulse.fire()
    out["pulse"] = [pulse.fired, pulse.isVisible()]
    pulse.fire()                                   # at once again: the shield does not flicker
    out["pulse_again"] = pulse.fired
    yield 700
    out["pulse_over"] = pulse.isVisible()
    ike.config["ui_effects"] = False
    pulse._last = 0.0
    pulse.fire()
    out["pulse_without_effects"] = pulse.fired
    ike.config["ui_effects"] = True

    icon = cyber.audio_icon(ike.icon, 1, lk.accent)
    image = icon.pixmap(32, 32).toImage()
    out["bars"] = count_near(image.copy(image.width() // 2, image.height() // 2, image.width() // 2, image.height() // 2), lk.accent) > 8
    out["bars_only_in_the_corner"] = count_near(image.copy(0, 0, image.width() // 2, image.height() // 2), lk.accent, 10) == 0

    panel = win.shield_panel
    panel.refresh()
    out["ring_shown"] = not panel.kinds.isHidden()
    panel.kinds.show_stats(lk, {"ads": 6, "scripts": 3, "cookies": 1}, {"ads": "ads"})
    panel.kinds.resize(260, 74)
    ring = panel.kinds.grab().toImage()
    out["ring"] = [count_near(ring, lk.accent) > 30, count_near(ring, "#ff5fa8") > 5]

    preview = TabPreview(win)
    cyber.style_preview(preview, ike.config)
    out["preview"] = lk.accent.name() in preview.styleSheet()

    out["fades"] = effects.cross_fade([win.nav, None], ike.config)
    out["fade_shown"] = len(win.nav.findChildren(QLabel, "ike_theme_fade"))
    yield 600
    out["fade_gone"] = len(win.nav.findChildren(QLabel, "ike_theme_fade"))
    out["equaliser_idle"] = win._equaliser.timer.isActive()        # nothing plays: no timer runs
''', settings={"ui_scheme": "theme:cyber", "cyber_hint": "done"}, env={"IKE_REDUCED_MOTION": "0"}, timeout=120)
    assert out["pulse"] == [1, True] and out["pulse_again"] == 1 and out["pulse_over"] is False
    assert out["pulse_without_effects"] == 1
    assert out["bars"] is True and out["bars_only_in_the_corner"] is True
    assert out["ring_shown"] is True and out["ring"] == [True, True]
    assert out["preview"] is True
    assert out["fades"] == 1 and out["fade_shown"] == 1 and out["fade_gone"] == 0
    assert out["equaliser_idle"] is False


def test_the_small_things_are_cyber_only(run_ike):
    out = run_ike(COMMON + r'''
def steps(ike, qapp, out):
    from ike import cyber
    from ike.tabpreview import TabPreview
    win = ike.windows[0]
    yield 800
    panel = win.shield_panel
    panel.refresh()
    out["ring_hidden"] = panel.kinds.isHidden()
    preview = TabPreview(win)
    cyber.style_preview(preview, ike.config)
    out["preview"] = preview.styleSheet()
    out["equaliser"] = hasattr(win, "_equaliser")
    view = win.current_view()
    yield from load(view, "ike:newtab")
    out["count_up"] = yield from js(view, "document.documentElement.innerHTML.indexOf('if (true &&') >= 0")
''', timeout=120)
    assert out["ring_hidden"] is True and out["preview"] == "" and out["equaliser"] is False
    assert out["count_up"] is False
