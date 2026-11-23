"""The tab bar, effects and polish of 1.1.24 (the owner's work package B1).

Each touch is checked offscreen in the real browser, by its geometry or its
state, and then that it leaves nothing running: the window's animations and
active timers after it settles are the ones it had at rest before (the
probes of test_effects.py and test_fluidity.py), so it costs nothing at
rest. With "Interface effects" off or the desktop's reduced motion each
changes at once.

1. the mark of the current tab is Breeze's line along the top edge of the
   tab, following its rounded top corners, and it glides; Breeze's own
   fixed mark is not drawn: in Breeze the tab bar is the same, pixel for
   pixel, as Breeze draws it with its own mark;
2. the current tab a shade lighter;
3. the close button glows Breeze's red under the mouse;
4. tabs slide aside while one is dragged (horizontal: Qt's own, its time
   from the style and I.K.E.'s switch; vertical: I.K.E.'s);
5. the vertical tabs' panel widens and narrows smoothly, and keeps the
   width the user gave it (after a restart, in a new window, when vertical
   tabs are chosen again; a width out of range is brought back);
6. a tab pulled out of the window opens in a new window, its picture
   following the mouse;
7. quick actions say they were done in a small box with an icon;
8. tooltips fade in and out;
9. the find bar slides in; its field flashes red when nothing is found;
10. a touchpad swipe goes back or forward, a pinch zooms;
11. Ctrl or Alt held for a second: the toolbar buttons show their keys;
12. tab groups in Breeze's colours, folding smoothly.
"""

import pytest
from conftest import screen

COMMON = r'''
import json
from PyQt6.QtCore import QAbstractAnimation, QEvent, QPoint, QPointF, Qt, QTimer, QUrl
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

def busy(win):
    """What runs now (test_effects.running, test_fluidity): the window's
    animations and its active timers, and those of the application's touches."""
    found = [type(a.parent()).__name__ + ":anim" for a in win.findChildren(QAbstractAnimation)
             if a.state() == QAbstractAnimation.State.Running]
    for t in win.findChildren(QTimer) + win.app.touches.findChildren(QTimer):
        if t.isActive():
            found.append((t.objectName() or type(t.parent()).__name__) + ":timer:" + str(t.interval()))
    return sorted(found)

def more(now, rest):
    """What runs now that did not run at rest."""
    left = list(rest)
    extra = []
    for x in now:
        if x in left:
            left.remove(x)
        else:
            extra.append(x)
    return extra

def page(view, title, url="http://local.test/"):
    view.setHtml("<!doctype html><title>%s</title><body>x</body>" % title, QUrl(url))

def hl(widget):
    return widget.palette().color(QPalette.ColorRole.Highlight)

def near(c, want, tol=12):
    c, want = QColor(c), QColor(want)
    return abs(c.red() - want.red()) + abs(c.green() - want.green()) + abs(c.blue() - want.blue()) <= tol
'''

# --- 1, 2, 3: the mark, the raised tab, the close button ----------------------------

TABBAR = COMMON + r'''
def steps(ike, qapp, out):
    from ike import polish
    win = ike.windows[0]
    win.resize(1200, 800)
    yield 600
    for t in ("Two", "Three"):
        page(win.add_tab("ike:newtab"), t)
    page(win.views[0], "One")
    yield 1200
    bar = win.tabbar
    bar.setCurrentIndex(1)
    yield 400
    rest = busy(win)
    out["style"] = bar.label_style.baseStyle().name()
    # --- 1: where the mark is, and its shape
    r = bar.tabRect(1)
    t = bar.mark.target()
    out["target"] = [t.x() == r.x(), t.y() == r.y(), t.width() == r.width(), t.height()]
    img = bar.grab().toImage()
    accent = hl(bar)
    cx = r.center().x()
    out["top_rows"] = [near(img.pixelColor(cx, r.top() + y), accent) for y in range(6)]
    # no line under the tab any more (1.1.3-1.1.23)
    out["bottom"] = [near(img.pixelColor(cx, r.bottom() - y), accent) for y in range(4)]
    # the ends follow the rounded corners: the very corner is not the full colour,
    # the line comes down the corner a little, never down the sides
    corner = img.pixelColor(r.left(), r.top())
    out["corner"] = [not near(corner, accent, 6), near(img.pixelColor(r.left() + 5, r.top()), accent),
                     not near(img.pixelColor(r.left(), r.top() + 9), accent, 60)]
    # the same as Breeze's path drawn alone at that place
    from PyQt6.QtGui import QImage, QPainter
    ref = QImage(img.size(), QImage.Format.Format_ARGB32_Premultiplied)
    ref.fill(Qt.GlobalColor.transparent)
    p = QPainter(ref)
    polish.paint_top_line(p, polish.top_line_rect(r), accent)
    p.end()
    inside = [(x, y) for y in range(r.top(), r.top() + 6) for x in range(r.left(), r.right() + 1)
              if ref.pixelColor(x, y).alpha() == 255]
    out["path_pixels"] = [len(inside), sum(near(img.pixelColor(x, y), accent, 3) for x, y in inside)]
    # one mark: the style's own is not drawn (Breeze compares pixel for pixel below)
    bar.own_mark = False
    plain = bar.grab().toImage()
    bar.own_mark = True
    if out["style"].lower() == "breeze":
        for scheme in ("light", "dark"):
            if scheme == "dark":
                pal = QPalette(bar.palette())
                for role, c in ((QPalette.ColorRole.Window, "#202326"), (QPalette.ColorRole.WindowText, "#fcfcfc"),
                                (QPalette.ColorRole.Base, "#141618"), (QPalette.ColorRole.Text, "#fcfcfc"),
                                (QPalette.ColorRole.Button, "#292c30"), (QPalette.ColorRole.ButtonText, "#fcfcfc"),
                                (QPalette.ColorRole.Highlight, "#3daee9")):
                    pal.setColor(role, QColor(c))
                bar.setPalette(pal)
            a = bar.grab().toImage()
            bar.own_mark = False
            b = bar.grab().toImage()
            bar.own_mark = True
            out["breeze_" + scheme] = [a.size() == b.size(),
                                       sum(1 for y in range(a.height()) for x in range(a.width())
                                           if a.pixel(x, y) != b.pixel(x, y)),
                                       near(b.pixelColor(cx, r.top() + 1), hl(bar), 3)]
        bar.setPalette(QPalette())
    else:
        out["fixed_mark"] = sum(near(plain.pixelColor(x, r.top() + 1), accent) for x in range(r.left(), r.right()))
    # --- 1: it glides to the next tab, then rests
    bar.repaint()
    bar.setCurrentIndex(2)
    yield 50
    shown = bar.mark._shown
    out["glide"] = [bar.mark.gliding, shown is not None and bar.tabRect(1).x() < shown.x() < bar.tabRect(2).x()]
    yield 400
    bar.repaint()
    out["glide_end"] = [bar.mark.gliding, bar.mark._shown == bar.mark.target()]
    # --- 2: the current tab is a shade lighter
    def tab_fill(i):
        im = bar.grab().toImage()
        rr = bar.tabRect(i)
        return QColor(im.pixel(rr.left() + 3, rr.bottom() - 3)).lightness()
    raised = tab_fill(2)
    polish.PARTS["tab_raised"] = False
    flat = tab_fill(2)
    polish.PARTS["tab_raised"] = True
    out["raised"] = [raised, flat]
    # --- 3: the close button glows red, softly
    from PyQt6.QtGui import QEnterEvent
    from PyQt6.QtWidgets import QTabBar
    btn = bar.tabButton(2, QTabBar.ButtonPosition.RightSide) or bar.tabButton(2, QTabBar.ButtonPosition.LeftSide)
    def red(w):
        im = w.grab().toImage()
        return sum(1 for x in range(im.width()) for y in range(im.height())
                   if near(im.pixelColor(x, y), polish.close_red(), 30))
    out["red_rest"] = red(btn)
    c = QPointF(btn.width() / 2, btn.height() / 2)
    QApplication.sendEvent(btn, QEnterEvent(c, c, QPointF(btn.mapToGlobal(c.toPoint()))))
    yield 40
    level = btn.property("ike_glow")
    out["glow_mid"] = level is not None and 0.0 < float(level) < 1.0
    yield 250
    out["glow_end"] = [float(btn.property("ike_glow")), red(btn) > 10]
    QApplication.sendEvent(btn, QEvent(QEvent.Type.Leave))
    yield 300
    out["glow_gone"] = [float(btn.property("ike_glow")), red(btn)]
    # --- 4: Qt's own slide of the tabs: its time follows I.K.E.'s switch
    from PyQt6.QtWidgets import QStyle
    out["slide_ms"] = bar.style().styleHint(QStyle.StyleHint.SH_Widget_Animation_Duration, None, bar)
    yield 300
    out["more"] = more(busy(win), rest)
'''


def test_the_current_tab_has_breezes_mark_raised_and_a_red_close(run_ike):
    out = run_ike(TABBAR, env={"IKE_REDUCED_MOTION": "0"}, timeout=120)
    assert out["target"] == [True, True, True, 3], out
    assert out["top_rows"][:3] == [True, True, True] and out["top_rows"][4:] == [False, False], out
    assert out["bottom"] == [False] * 4, out
    assert out["corner"] == [True, True, True], out
    assert out["path_pixels"][0] > 100 and out["path_pixels"][1] == out["path_pixels"][0], out
    if out["style"].lower() == "breeze":
        # Breeze's own mark and I.K.E.'s, the same pixels, light and dark
        assert out["breeze_light"] == [True, 0, True], out
        assert out["breeze_dark"] == [True, 0, True], out
    else:
        assert out["fixed_mark"] == 0, out
    assert out["glide"] == [True, True] and out["glide_end"] == [False, True], out
    assert out["raised"][0] > out["raised"][1], out
    assert out["red_rest"] < 3, out
    assert out["glow_mid"] is True, out
    assert out["glow_end"][0] == 1.0 and out["glow_end"][1] is True, out
    assert out["glow_gone"][0] == 0.0 and out["glow_gone"][1] < 3, out
    assert out["slide_ms"] > 0, out
    assert out["more"] == [], out


def test_the_tab_mark_draws_breezes_own_geometry_in_breeze(run_ike):
    """Breeze's own render, measured: in Breeze, the whole tab bar with
    I.K.E.'s gliding mark is the same picture as with Breeze's fixed mark."""
    out = run_ike(TABBAR, env={"IKE_REDUCED_MOTION": "0", "QT_STYLE_OVERRIDE": "Breeze"}, timeout=120)
    if out["style"].lower() != "breeze":
        pytest.skip("Breeze (the widget style) is not installed here")
    assert out["breeze_light"] == [True, 0, True], out
    assert out["breeze_dark"] == [True, 0, True], out
    assert out["top_rows"][:3] == [True, True, True], out
    assert out["more"] == [], out


AT_ONCE = COMMON + r'''
def steps(ike, qapp, out):
    from ike import polish
    from PyQt6.QtWidgets import QStyle, QTabBar
    from PyQt6.QtGui import QEnterEvent
    win = ike.windows[0]
    yield 600
    win.add_tab("ike:newtab")
    yield 800
    bar = win.tabbar
    bar.setCurrentIndex(0)
    yield 30
    out["glide"] = bar.mark.gliding
    out["slide_ms"] = bar.style().styleHint(QStyle.StyleHint.SH_Widget_Animation_Duration, None, bar)
    btn = bar.tabButton(1, QTabBar.ButtonPosition.RightSide) or bar.tabButton(1, QTabBar.ButtonPosition.LeftSide)
    c = QPointF(btn.width() / 2, btn.height() / 2)
    QApplication.sendEvent(btn, QEnterEvent(c, c, QPointF(btn.mapToGlobal(c.toPoint()))))
    out["glow"] = float(btn.property("ike_glow") or 0)
    win.findbar.open_bar()
    out["slide_in"] = win.findbar.findChild(polish.QWidget, "ike_slide_in") is not None
    win.findbar._nothing(True)
    out["tint"] = round(win.findbar.tint_level, 2)
    win.findbar.close_bar()
    win.app.config["vtabs_icons_only"] = True
    win.app.config["tabs_position"] = "vertical"
    win.apply_layout()
    yield 200
    win.app.config["vtabs_icons_only"] = False
    win.apply_layout()
    out["resize"] = getattr(win, "_vtabs_width_anim", None) is None or \
        win._vtabs_width_anim.state() != QAbstractAnimation.State.Running
    win.vtabs.drag_row = 0
    win.vtabs.slide_to(2)
    out["offsets"] = [win.vtabs.offset(1), win.vtabs._slide is None]
    win.vtabs._end_slide()
    out["rest"] = busy(win)
'''


@pytest.mark.parametrize("how", ["setting-off", "reduced-motion"])
def test_the_touches_change_at_once_without_effects(run_ike, how):
    out = run_ike(AT_ONCE, settings={"ui_effects": how != "setting-off"},
                  env={"IKE_REDUCED_MOTION": "1" if how == "reduced-motion" else "0"}, timeout=120)
    assert out["glide"] is False, out                      # the mark jumps
    assert out["slide_ms"] == 0, out                       # the tabs move aside at once
    assert out["glow"] == 1.0, out                         # the red at once
    assert out["slide_in"] is False and out["tint"] == 0.22, out
    assert out["resize"] is True, out
    assert out["offsets"][0] < 0 and out["offsets"][1] is True, out
    assert not [x for x in out["rest"] if x.endswith(":anim")], out


# --- 4, 6: dragging: tabs slide aside, a tab pulled out opens a new window ----------

DRAG = COMMON + r'''
def steps(ike, qapp, out):
    from ike import tabs
    win = ike.windows[0]
    win.resize(1200, 800)
    yield 600
    for i in range(3):
        page(win.add_tab("ike:newtab"), "T%d" % i, "http://local.test/%d" % i)
    page(win.views[0], "Home", "http://local.test/home")
    yield 1500
    rest = busy(win)
    bar = win.tabbar
    # --- a tab pulled down out of the bar: its picture follows the mouse; dropped
    # outside every tab bar, it opens in a new window
    drags = []
    def fake(drag, actions):
        drags.append(drag.pixmap().width() / (drag.pixmap().devicePixelRatio() or 1))
        return answer[0]
    tabs.run_drag = fake
    answer = [Qt.DropAction.IgnoreAction]
    view = win.views[2]
    url = view.url().toString()
    start = bar.tabRect(2).center()
    QTest.mousePress(bar, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
    QTest.mouseMove(bar, start + QPoint(4, 10))
    yield 20
    out["dragging"] = bar.dragging
    QTest.mouseMove(bar, start + QPoint(8, 30))
    yield 20
    out["still_here"] = [len(drags), view in win.views]
    QTest.mouseMove(bar, QPoint(start.x() + 10, bar.height() + bar.TEAR_PX + 30))
    yield 600
    # (the new window may ask for https first: the same page)
    out["torn"] = [len(drags), drags[0] if drags else 0, view in win.views, len(ike.windows),
                   ike.windows[-1].current_view().url().toString().split("://")[-1]
                   if len(ike.windows) > 1 else ""]
    out["url"] = url.split("://")[-1]
    out["dragging_after"] = bar.dragging
    new = ike.windows[-1]
    # --- dropped back on its own tab bar (or Esc): it stays
    answer[0] = Qt.DropAction.MoveAction
    n = len(win.views)
    win._tear_off(1)
    out["stays"] = [len(win.views) == n, len(ike.windows)]
    # --- dropped on another window's tab bar: it moves there
    key = win._tab_key(win.views[1])
    moved_url = win.views[1].url().toString()
    new._take_tab(key)
    yield 500
    out["taken"] = [len(win.views) == n - 1,
                    new.current_view().url().toString().split("://")[-1] == moved_url.split("://")[-1]]
    new.close()
    yield 300
    # --- vertical tabs: the rows slide aside while one is dragged
    for i in range(4):
        page(win.add_tab("ike:newtab"), "V%d" % i, "http://local.test/v%d" % i)
    yield 800
    win.app.config["tabs_position"] = "vertical"
    win.apply_layout()
    yield 400
    vt = win.vtabs
    h = vt.visualItemRect(vt.item(1)).height()
    vt.drag_row = 0
    vt.gap = 0
    vt.slide_to(3)
    yield 40
    out["v_mid"] = [vt._slide.state() == QAbstractAnimation.State.Running, -h < vt.offset(1) < 0,
                    vt.offset(3)]
    yield 300
    out["v_end"] = [vt.offset(1) == -h, vt.offset(2) == -h, vt.offset(3)]
    vt.slide_to(0)
    yield 300
    out["v_back"] = [vt.offset(1), vt.offset(2)]
    # dropped where the place opened: the tab moves there, in both lists
    first = win.views[0]
    vt.slide_to(3)
    yield 250
    vt.drop_at(vt.visualItemRect(vt.item(3)).top() + 2)
    yield 200
    out["v_drop"] = [win.views.index(first), vt.drag_row, vt.currentRow() == win.views.index(win.current_view())]
    # a row dropped outside the list opens in a new window
    answer[0] = Qt.DropAction.IgnoreAction
    v2 = win.views[1]
    vt.setCurrentRow(1)
    yield 100
    vt.startDrag(Qt.DropAction.MoveAction)
    yield 600
    out["v_torn"] = [v2 in win.views, len(ike.windows), drags[-1]]
    for w in ike.windows[1:]:
        w.close()
    yield 600
    out["more"] = more(busy(win), rest)
'''


def test_tabs_slide_aside_and_a_tab_pulled_out_opens_a_window(run_ike):
    out = run_ike(DRAG, env={"IKE_REDUCED_MOTION": "0"}, timeout=150)
    assert out["dragging"] is True, out
    assert out["still_here"] == [0, True], out             # near the bar: only moved along it
    assert out["torn"][0] == 1 and 100 <= out["torn"][1] <= 170, out   # the picture followed the mouse
    assert out["torn"][2:] == [False, 2, out["url"]], out
    assert out["dragging_after"] is False, out
    assert out["stays"] == [True, 2], out
    assert out["taken"] == [True, True], out
    assert out["v_mid"][:2] == [True, True] and out["v_mid"][2] == 0, out
    assert out["v_end"] == [True, True, 0], out
    assert out["v_back"] == [0, 0], out
    assert out["v_drop"] == [2, -1, True], out
    assert out["v_torn"][:2] == [False, 2], out
    assert out["more"] == [], out


# --- 5: the vertical tabs' panel: smooth, and its width kept ------------------------

SIDEBAR = COMMON + r'''
def steps(ike, qapp, out):
    win = ike.windows[0]
    yield 900
    out["start"] = [win.vtab_panel.width(), win.app.config["vtabs_width"]]
    rest = busy(win)
    # the user drags the panel's edge
    win.splitter.moveSplitter(310, 1)
    yield 1100                                      # saved a moment later
    out["moved"] = [win.vtab_panel.width(), win.app.config["vtabs_width"]]
    # only the icons, and back: the panel glides both ways
    win._toggle_vtabs_icons()
    yield 60
    out["narrowing"] = [win._vtabs_width_anim.state() == QAbstractAnimation.State.Running,
                        48 < win.vtab_panel.width() < 310]
    yield 400
    out["narrow"] = win.vtab_panel.width()
    win._toggle_vtabs_icons()
    yield 60
    out["widening"] = 48 < win.vtab_panel.width() < 310
    yield 400
    out["wide"] = win.vtab_panel.width()
    # horizontal tabs, then vertical again: the same width
    win._toggle_vertical()
    yield 300
    win._toggle_vertical()
    yield 400
    out["again"] = win.vtab_panel.width()
    # a new window: the same width
    w2 = win.app.new_window()
    yield 900
    out["new_window"] = w2.vtab_panel.width()
    w2.close()
    yield 400
    out["more"] = more(busy(win), rest)
'''

RESTARTED = COMMON + r'''
def steps(ike, qapp, out):
    win = ike.windows[0]
    yield 900
    out["width"] = win.vtab_panel.width()
'''


def test_the_tab_panel_glides_and_keeps_its_width(run_ike, tmp_path):
    env = dict(screen(tmp_path, 1600, 1000), IKE_REDUCED_MOTION="0")
    settings = {"tabs_position": "vertical", "start_maximized": False}
    out = run_ike(SIDEBAR, settings=settings, env=env, timeout=150)
    assert out["moved"] == [310, 310], out
    assert out["narrowing"] == [True, True], out
    assert out["narrow"] == 48, out
    assert out["widening"] is True and out["wide"] == 310, out
    assert out["again"] == 310, out
    assert out["new_window"] == 310, out
    assert out["more"] == [], out
    # I.K.E. started again: the width the user gave it
    again = run_ike(RESTARTED, keep_profile=True, env=env, timeout=90)
    assert again["width"] == 310, again


@pytest.mark.parametrize("stored, want", [(5000, 720), (10, 120), (-40, 120), (900, 720), (260, 260)])
def test_a_tab_panel_width_out_of_range_is_brought_back(run_ike, tmp_path, stored, want):
    env = dict(screen(tmp_path, 1600, 1000), IKE_REDUCED_MOTION="0")
    out = run_ike(RESTARTED, settings={"tabs_position": "vertical", "start_maximized": False,
                                      "vtabs_width": stored}, env=env, timeout=90)
    assert out["width"] == want, out


def test_a_tab_panel_never_takes_more_than_half_a_small_screen(run_ike, tmp_path):
    env = dict(screen(tmp_path, 1000, 700), IKE_REDUCED_MOTION="0")
    out = run_ike(RESTARTED, settings={"tabs_position": "vertical", "start_maximized": False,
                                      "vtabs_width": 700}, env=env, timeout=90)
    assert out["width"] == 500, out


# --- 7, 8, 9: the on-screen box, tooltips, the find bar --------------------------------

OSD = COMMON + r'''
def steps(ike, qapp, out):
    from PyQt6.QtWidgets import QMenu, QToolTip
    from ike.i18n import T
    win = ike.windows[0]
    win.resize(1200, 800)
    yield 600
    v = win.current_view()
    page(v, "A page", "http://local.test/page")
    yield 1200
    rest = busy(win)
    win.urlbar.setFocus()
    yield 50
    focus = QApplication.focusWidget()
    pill = win.toast_pill
    # --- 7: bookmark added
    win.toggle_bookmark()
    yield 60
    out["bookmark"] = [pill.isVisible(), pill.text, pill.icon is not None, pill._opacity < 1.0,
                       QApplication.focusWidget() is focus, pill.focusPolicy() == Qt.FocusPolicy.NoFocus,
                       pill.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)]
    yield 400
    out["shown"] = [pill.isVisible(), pill._opacity]
    yield 1300
    out["gone"] = pill.isVisible()
    # a link copied from the page's menu
    m = QMenu()
    a = m.addAction(T("Copy link address"))
    v._osd_for(m)
    a.trigger()
    yield 50
    out["link"] = [pill.isVisible(), pill.text, pill.icon is not None]
    # the zoom
    win.zoom(+1)
    yield 50
    out["zoom"] = [pill.text, pill.icon is not None]
    win.zoom(0)
    yield 1800
    out["zoom_gone"] = pill.isVisible()
    # --- 8: a tooltip fades in, and out
    QToolTip.showText(win.mapToGlobal(QPoint(200, 200)), "A tooltip", win)
    yield 30
    tips = [w for w in QApplication.topLevelWidgets() if w.inherits("QTipLabel") and w.isVisible()]
    out["tip_in"] = [len(tips), tips[0].windowOpacity() < 1.0 if tips else None]
    yield 300
    out["tip_full"] = tips[0].windowOpacity() if tips else None
    ghosts = win.app.touches.ghosts
    QToolTip.hideText()
    yield 600
    out["tip_out"] = win.app.touches.ghosts - ghosts
    yield 300
    out["ghosts_left"] = [w.objectName() for w in QApplication.topLevelWidgets()
                          if w.objectName() == "ike_tip_ghost" and w.isVisible()]
    # --- 9: the find bar slides in from the bottom
    fb = win.findbar
    fb.open_bar()
    from ike import polish
    slide = fb.findChild(polish._SlideIn, "ike_slide_in")
    yield 40
    out["slide"] = [slide is not None, slide is not None and 0 < slide.offset() < fb.height(),
                    slide is not None and slide.geometry() == fb.rect()]
    yield 400
    out["slid"] = fb.findChild(polish._SlideIn, "ike_slide_in") is None
    QTest.keyClicks(fb.edit, "zzqqxxnothing")
    for _ in range(30):
        if fb.edit.property("nothing_found"):
            break
        yield 50
    out["flash"] = round(fb.tint_level, 2)
    yield 600
    out["tint"] = round(fb.tint_level, 2)
    fb.edit.clear()
    yield 300
    out["clear"] = [fb.tint_level, fb.edit.property("nothing_found")]
    fb.close_bar()
    yield 300
    out["more"] = more(busy(win), rest)
'''


def test_quick_actions_tooltips_and_the_find_bar(run_ike):
    out = run_ike(OSD, env={"IKE_REDUCED_MOTION": "0"}, timeout=120)
    assert out["bookmark"] == [True, "Bookmark added", True, True, True, True, True], out
    assert out["shown"] == [True, 1.0], out
    assert out["gone"] is False, out                       # about 1.2 s, then gone
    assert out["link"] == [True, "Link copied", True], out
    assert out["zoom"] == ["Zoom: 110%", True], out
    assert out["zoom_gone"] is False, out
    assert out["tip_in"] == [1, True] and out["tip_full"] == 1.0, out
    assert out["tip_out"] == 1 and out["ghosts_left"] == [], out
    assert out["slide"] == [True, True, True] and out["slid"] is True, out
    assert out["flash"] > 0.3 and out["tint"] == 0.22, out
    assert out["clear"] == [0.0, False], out
    assert out["more"] == [], out


# --- 10: touchpad gestures --------------------------------------------------------

GESTURES = COMMON + r'''
def steps(ike, qapp, out):
    from PyQt6.QtGui import QNativeGestureEvent, QPointingDevice
    win = ike.windows[0]
    win.resize(1200, 800)
    yield 600
    v = win.current_view()
    page(v, "First", "http://local.test/first")
    yield 800
    dev = QPointingDevice.primaryPointingDevice()
    at = QPointF(200, 200)
    out["url"] = v.url().toString()
    def gesture(kind, value=0.0, delta=QPointF()):
        fp = v.focusProxy()                 # the page's own widget (a new one after some loads)
        ev = QNativeGestureEvent(kind, dev, 2, at, at, QPointF(fp.mapToGlobal(at.toPoint())), value, delta)
        QApplication.sendEvent(fp, ev)
    G = Qt.NativeGestureType
    # a pinch: the page zooms, the zoom shows in the box
    gesture(G.BeginNativeGesture)
    for _ in range(5):
        gesture(G.ZoomNativeGesture, 0.04)
    gesture(G.EndNativeGesture)
    yield 50
    out["pinch"] = [round(v.zoomFactor(), 2), win.toast_pill.isVisible(), win.toast_pill.text,
                    win.app.config["site_zoom"].get("local.test")]
    win.zoom(0)
    yield 300
    v.load(QUrl("data:text/html,<title>Second</title>second"))
    yield 1200
    rest = busy(win)
    # a swipe to the right: back, the page sliding away
    out["before"] = v.title()
    gesture(G.BeginNativeGesture)
    for _ in range(6):
        gesture(G.PanNativeGesture, 0.0, QPointF(30, 2))
    gesture(G.EndNativeGesture)
    yield 60
    from ike.gestures import PageSlide
    slides = win.findChildren(PageSlide)
    out["slide"] = [len(slides), slides[0].shift() > 0 if slides else None]
    yield 1500
    out["back"] = v.title()
    # a short stroke does nothing
    gesture(G.BeginNativeGesture)
    gesture(G.PanNativeGesture, 0.0, QPointF(-40, 0))
    gesture(G.EndNativeGesture)
    yield 500
    out["short"] = v.title()
    # and to the left: forward
    gesture(G.BeginNativeGesture)
    for _ in range(6):
        gesture(G.PanNativeGesture, 0.0, QPointF(-30, 0))
    gesture(G.EndNativeGesture)
    yield 1500
    out["forward"] = v.title()
    yield 300
    out["slides_left"] = len(win.findChildren(PageSlide))
    out["more"] = more(busy(win), rest)
'''


def test_touchpad_swipe_goes_back_and_pinch_zooms(run_ike):
    out = run_ike(GESTURES, env={"IKE_REDUCED_MOTION": "0"}, timeout=120)
    assert out["pinch"][0] > 1.15 and out["pinch"][1] is True, out
    assert out["pinch"][2] == "Zoom: %d%%" % round(out["pinch"][0] * 100), out
    assert abs(out["pinch"][3] - out["pinch"][0]) < 0.01, out   # kept for the site, as Ctrl+wheel
    assert out["before"] == "Second" and out["slide"] == [1, True], out
    assert out["back"] == "First" and out["short"] == "First" and out["forward"] == "Second", out
    assert out["slides_left"] == 0 and out["more"] == [], out


# --- 11: the keys of the toolbar buttons --------------------------------------------

KEYS = COMMON + r'''
def steps(ike, qapp, out):
    from PyQt6.QtGui import QKeyEvent
    from ike.motion import KeyHint
    win = ike.windows[0]
    win.resize(1400, 800)
    yield 900
    win.activateWindow()
    QApplication.setActiveWindow(win)
    yield 100
    rest = busy(win)
    target = win.urlbar
    def key(kind, k, mods):
        QApplication.sendEvent(target, QKeyEvent(kind, k, mods))
    def hints():
        return sorted(h.text for h in win.findChildren(KeyHint) if h.isVisible())
    key(QEvent.Type.KeyPress, Qt.Key.Key_Alt, Qt.KeyboardModifier.AltModifier)
    yield 500
    out["early"] = hints()
    yield 800
    out["alt"] = hints()
    inside = [win.rect().contains(h.geometry()) for h in win.findChildren(KeyHint) if h.isVisible()]
    out["inside"] = all(inside) and bool(inside)
    key(QEvent.Type.KeyRelease, Qt.Key.Key_Alt, Qt.KeyboardModifier.NoModifier)
    yield 50
    out["released"] = hints()
    # Ctrl: the keys with Ctrl
    key(QEvent.Type.KeyPress, Qt.Key.Key_Control, Qt.KeyboardModifier.ControlModifier)
    yield 1300
    out["ctrl"] = hints()
    # a shortcut typed (Ctrl+L): no labels
    key(QEvent.Type.KeyPress, Qt.Key.Key_L, Qt.KeyboardModifier.ControlModifier)
    yield 50
    out["typed"] = hints()
    key(QEvent.Type.KeyRelease, Qt.Key.Key_Control, Qt.KeyboardModifier.NoModifier)
    # Ctrl pressed and let go at once: nothing
    key(QEvent.Type.KeyPress, Qt.Key.Key_Control, Qt.KeyboardModifier.ControlModifier)
    yield 300
    key(QEvent.Type.KeyRelease, Qt.Key.Key_Control, Qt.KeyboardModifier.NoModifier)
    yield 1200
    out["quick"] = hints()
    yield 300
    out["more"] = more(busy(win), rest)
'''


def test_holding_ctrl_or_alt_shows_the_keys_of_the_buttons(run_ike):
    out = run_ike(KEYS, env={"IKE_REDUCED_MOTION": "0"}, timeout=120)
    assert out["early"] == [], out
    assert "Alt+Left" in out["alt"] and "Alt+Right" in out["alt"] and "Alt+Home" in out["alt"], out
    assert not [k for k in out["alt"] if "Ctrl" in k], out
    assert out["inside"] is True, out
    assert out["released"] == [], out
    assert "Ctrl+R" in out["ctrl"] and "Ctrl+D" in out["ctrl"], out
    assert not [k for k in out["ctrl"] if "Alt" in k], out
    assert out["typed"] == [] and out["quick"] == [], out
    assert out["more"] == [], out


# --- 12: tab groups ------------------------------------------------------------------

GROUPS = COMMON + r'''
def steps(ike, qapp, out):
    from ike import features, polish
    win = ike.windows[0]
    win.resize(1200, 800)
    yield 600
    for i in range(4):
        win.add_tab("ike:newtab")
    yield 1200
    rest = busy(win)
    a, b, c = win.views[1], win.views[2], win.views[3]
    for v in (a, b, c):
        win.group_add(v, "Work")
    win.group_add(win.views[4], "Play")
    yield 200
    out["colours"] = [win.groups["Work"]["color"], win.groups["Play"]["color"],
                      hl(win).name(), features.group_colours(win.palette())[:2]]
    win.set_current(win.views[0])
    yield 300
    bar = win.tabbar
    wide = bar.tabRect(3).right()
    win.group_toggle("Work")
    yield 50
    folds = win.findChildren(polish.FoldStrip)
    out["folding"] = [len(folds), folds[0].anim.state() == QAbstractAnimation.State.Running if folds else None,
                      0 < folds[0].open_part() < 1 if folds else None,
                      [bar.isTabVisible(i) for i in range(1, 4)]]
    yield 400
    out["folded"] = [len(win.findChildren(polish.FoldStrip)), [bar.isTabVisible(i) for i in range(1, 4)]]
    win.group_toggle("Work")
    yield 50
    folds = win.findChildren(polish.FoldStrip)
    out["unfolding"] = [len(folds), 0 < folds[0].open_part() < 1 if folds else None]
    yield 400
    out["unfolded"] = [len(win.findChildren(polish.FoldStrip)), [bar.isTabVisible(i) for i in range(1, 4)],
                       bar.tabRect(3).right() == wide]
    # vertical tabs fold too
    win.app.config["tabs_position"] = "vertical"
    win.apply_layout()
    yield 300
    win.group_toggle("Work")
    yield 50
    folds = win.findChildren(polish.FoldStrip)
    out["v_folding"] = [len(folds), folds[0].vertical if folds else None]
    yield 400
    out["v_folded"] = [len(win.findChildren(polish.FoldStrip)), [win.vtabs.item(i).isHidden() for i in range(1, 4)]]
    out["more"] = more(busy(win), rest)
'''


def test_tab_groups_have_breezes_colours_and_fold_smoothly(run_ike):
    out = run_ike(GROUPS, env={"IKE_REDUCED_MOTION": "0"}, timeout=120)
    work, play, accent, first = out["colours"]
    assert work == accent and [work, play] == first, out    # the desktop's accent, then Breeze's green
    assert out["folding"][:3] == [1, True, True], out
    assert out["folding"][3] == [False, False, False] or out["folding"][3] == [True, False, False], out
    assert out["folded"] == [0, [True, False, False]], out
    assert out["unfolding"] == [1, True], out
    assert out["unfolded"] == [0, [True, True, True], True], out
    assert out["v_folding"] == [1, True], out
    assert out["v_folded"] == [0, [False, True, True]], out
    assert out["more"] == [], out
