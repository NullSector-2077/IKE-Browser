"""How the menus and the menu buttons look (1.1.23, the owner on KDE Plasma).

- The ☰ menu button and the dark mode button of the toolbar show their icon
  only, with no arrow and no part of their own for one, in every widget style
  that is installed (Breeze, Fusion, Windows, Oxygen, Kvantum): as wide as a
  plain icon button, and a click anywhere on them opens their menu as before
  (the dark mode button's panel since 1.1.25).
- In every menu (the ☰ menu, its "More" and the menus under it, the menu
  bar's, the tab menu) the texts of all entries start at the same x, in
  every style and in Italian and English.

The x where an entry's text starts is found in pictures of the open menu:
the entry drawn with its text and without it.
"""

import pytest
from conftest import screen

STYLES = ["Breeze", "Fusion", "Windows", "Oxygen", "kvantum"]
TOLERANCE = 2              # px: see test_menu_texts_share_one_left_edge

BUTTONS = r'''
from PyQt6.QtCore import QPoint, Qt, QTimer
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QStyle, QStyleOptionToolButton

def steps(ike, qapp, out):
    win = ike.windows[0]
    win.resize(1300, 800)
    ike.config["toolbar_hidden"] = [k for k in ike.config["toolbar_hidden"] if k != "dark"]
    win._apply_toolbar()
    yield 800
    st = qapp.style()
    out["style"] = st.baseStyle().name() if hasattr(st, "baseStyle") else st.name()
    plain = win.nav.widgetForAction(win.act_reload)
    dark = win.nav.widgetForAction(win.act_dark)
    out["plain"] = [plain.sizeHint().width(), plain.sizeHint().height()]
    res = {}
    # 1.1.25: the dark mode button opens its panel (made at its first click: asked for when looked at)
    for name, b, menu in (("menu", win.menu_btn, lambda: win.burger), ("dark", dark, lambda: win.dark_menu)):
        opt = QStyleOptionToolButton()          # as QToolButton makes it for a button with a menu
        opt.initFrom(b)
        F = QStyleOptionToolButton.ToolButtonFeature
        opt.features = F.HasMenu | F.MenuButtonPopup
        opt.subControls = QStyle.SubControl.SC_ToolButton | QStyle.SubControl.SC_ToolButtonMenu
        part = b.style().subControlRect(QStyle.ComplexControl.CC_ToolButton, opt,
                                        QStyle.SubControl.SC_ToolButtonMenu, b)
        clicks = []
        for x in (b.width() // 2, b.width() - 3):
            seen = {}
            def look(m=menu, s=seen):
                s["open"] = m() is not None and m().isVisible()
                if m() is not None:
                    m().hide()
            QTimer.singleShot(400, look)
            QTest.mouseClick(b, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(x, b.height() // 2))
            for _ in range(20):
                if "open" in seen:
                    break
                yield 50
            clicks.append(seen.get("open", False))
        res[name] = {"size": [b.sizeHint().width(), b.sizeHint().height()], "arrow_part": part.isValid(),
                     "clicks": clicks, "mode": b.popupMode().name}
    out["buttons"] = res
'''


@pytest.mark.parametrize("style", STYLES)
def test_menu_buttons_show_their_icon_only(run_ike, tmp_path, style):
    env = dict(screen(tmp_path, 1366, 768), QT_STYLE_OVERRIDE=style)
    out = run_ike(BUTTONS, env=env, timeout=200)
    if style.lower() not in (out["style"] or "").lower():
        pytest.skip("the %s style is not installed here (got %r)" % (style, out["style"]))
    for name, got in out["buttons"].items():
        assert got["size"] == out["plain"], (style, name, got, out["plain"])     # no room for an arrow
        assert got["arrow_part"] is False, (style, name, got)
        assert got["clicks"] == [True, True], (style, name, got)                 # a click opens the menu
        assert got["mode"] == "InstantPopup", got                                # no part for an arrow


ALIGN = r'''
from PyQt6.QtCore import QPoint

def text_lefts(menu, settle):
    """{entry: x where its text starts} for the entries of the open menu."""
    out = {}
    for a in menu.actions():
        if a.isSeparator() or not a.isVisible() or not a.text():
            continue
        r = menu.actionGeometry(a)
        if r.isEmpty():
            continue
        with_text = menu.grab(r).toImage()
        text = a.text()
        a.setText("")
        yield from settle()
        without = menu.grab(r).toImage()
        a.setText(text)
        yield from settle()
        xs = [x for x in range(min(with_text.width(), without.width()))
              for y in range(min(with_text.height(), without.height()))
              if with_text.pixel(x, y) != without.pixel(x, y)]
        if xs:
            out[text.replace("&", "")] = min(xs)
    return out

def steps(ike, qapp, out):
    win = ike.windows[0]
    win.resize(1300, 800)
    yield 800
    st = qapp.style()
    out["style"] = st.baseStyle().name() if hasattr(st, "baseStyle") else st.name()

    def settle():
        for _ in range(3):
            qapp.processEvents()
            yield 10

    menus = [("☰", win.burger)]
    more = [a.menu() for a in win.burger.actions() if a.menu() is not None]
    for m in more:
        menus.append(("☰ > " + m.title(), m))
        for a in m.actions():
            if a.menu() is not None:
                menus.append(("☰ > %s > %s" % (m.title(), a.menu().title()), a.menu()))
    res = {}
    seen = set()
    for where, m in menus:
        if id(m) in seen:
            continue
        seen.add(id(m))
        m.popup(win.mapToGlobal(QPoint(40, 40)))
        yield from settle()
        yield 150
        lefts = yield from text_lefts(m, settle)
        m.hide()
        yield from settle()
        if lefts:
            res[where] = lefts
    out["menus"] = res
'''


@pytest.mark.parametrize("lang", ["en", "it"])
@pytest.mark.parametrize("style", STYLES)
def test_menu_texts_share_one_left_edge(run_ike, tmp_path, style, lang):
    env = dict(screen(tmp_path, 1366, 768), QT_STYLE_OVERRIDE=style)
    out = run_ike(ALIGN, env=env, settings={"language": lang}, timeout=400)
    if style.lower() not in (out["style"] or "").lower():
        pytest.skip("the %s style is not installed here (got %r)" % (style, out["style"]))
    # the first coloured pixel of a text depends on its first letter's own
    # side bearing ("I" starts a pixel later than "R"): 2 px are allowed; an
    # icon or a switch column out of place is 15 px or more
    bad = []
    for where, lefts in out["menus"].items():
        if max(lefts.values()) - min(lefts.values()) > TOLERANCE:
            low = min(lefts.values())
            bad.append("%s: %s" % (where, ", ".join("%s +%d" % (k, v - low) for k, v in lefts.items()
                                                     if v - low > TOLERANCE)))
    assert out["menus"] and not bad, "%s %s\n%s" % (style, lang, "\n".join(bad))


PRIVATE = r'''
from PyQt6.QtCore import QPoint
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QLabel, QStyle

def steps(ike, qapp, out):
    from ike import polish
    win = ike.windows[0]
    private = ike.new_window(private=True)
    yield 800
    def bar(w):
        img = w.grab().toImage()
        g = w.nav.geometry()
        return QColor(img.pixel(g.left() + 2, g.top() + 2)).name()
    from ike import effects
    out["tint"] = [win.nav.tint() is None, private.nav.tint() is not None, bar(win), bar(private),
                   effects.blend(QColor(bar(win)), polish.PRIVATE_PURPLE, polish.PRIVATE_MIX).name()]
    badge = private.findChild(QLabel, "privateWindowBadge")
    sheet = badge.styleSheet()
    out["badge"] = {"icon": not badge.icon.isNull(), "border": "border: 1px solid" in sheet,
                    "radius": "border-radius" in sheet, "colours": badge.colours()[0].name() != badge.colours()[1].name(),
                    "visible": badge.isVisible(), "text_fits": badge.sizeHint().width() >=
                    badge.fontMetrics().horizontalAdvance(badge.text()) + 2 * badge.PAD_X + badge.ICON}
    out["normal_badge"] = win.findChild(QLabel, "privateWindowBadge") is None
    # the panels' menus and the suggestions: the one radius and a light shadow
    menu = win.shield_menu
    out["native"] = polish.native_popups()
    out["menu_style"] = type(menu.style()).__name__
    out["menu_panel"] = menu.style().pixelMetric(QStyle.PixelMetric.PM_MenuPanelWidth, None, menu)
    menu.popup(win.mapToGlobal(QPoint(300, 60)))
    yield 400
    img = menu.grab().toImage()
    out["menu_corner_alpha"] = QColor(img.pixelColor(1, 1)).alpha()
    out["menu_inside_alpha"] = QColor(img.pixelColor(img.width() // 2, polish.POPUP_SHADOW + 3)).alpha()
    menu.hide()
    pop = win.urlbar._completer.popup()
    out["list"] = [getattr(pop, "_ike_round", None) is not None, pop.frameShape().name]
    private.close()
'''


def test_private_window_and_rounded_popups(run_ike):
    """1.1.23: a private window's toolbar is a little purple and its badge has
    the private icon and a border; ordinary windows are unchanged. The
    shield's and the site's panels and the suggestions are rounded with the
    one radius and a light shadow (here Qt's Fusion, which has neither)."""
    out = run_ike(PRIVATE, timeout=120)
    normal_none, private_tinted, normal_px, private_px, mixed = out["tint"]
    assert normal_none and private_tinted, out
    assert normal_px != private_px, out
    near = [abs(int(private_px[i:i + 2], 16) - int(mixed[i:i + 2], 16)) <= 2 for i in (1, 3, 5)]
    assert all(near), out                                # the toolbar's own colour with 15 % purple
    assert all(out["badge"].values()), out
    assert out["normal_badge"], out
    assert out["native"] is False and out["menu_style"] == "PopupPanelStyle", out
    assert out["menu_panel"] >= 6, out
    assert out["menu_corner_alpha"] == 0 and out["menu_inside_alpha"] == 255, out
    assert out["list"] == [True, "NoFrame"], out


STALE = r'''
from PyQt6.QtCore import QSize
from PyQt6.QtWidgets import QPushButton, QStyle, QStyleOptionButton, QStyleOptionTab, QToolButton
from PyQt6.QtCore import Qt

def steps(ike, qapp, out):
    from ike import uistyle
    yield 300
    st = qapp.style()
    CT = QStyle.ContentsType
    b = QPushButton("Una scritta piuttosto lunga")
    t = QToolButton()
    t.setText("Testo")
    t.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
    size = QSize(40, 12)
    right = QStyleOptionButton()
    right.initFrom(b)
    right.text = b.text()
    # an option of another kind where a button's was expected: what PyQt 6.12
    # handed over now and then, a stale wrapper found at the same address
    wrong = QStyleOptionTab()
    wrong.text = ""
    out["push"] = [st.sizeFromContents(CT.CT_PushButton, right, size, b).width(),
                   st.sizeFromContents(CT.CT_PushButton, wrong, size, b).width()]
    out["tool"] = [st.sizeFromContents(CT.CT_ToolButton, right, size, t).width(),
                   st.sizeFromContents(CT.CT_ToolButton, wrong, size, t).width()]
    out["least"] = size.width() + 2 * uistyle.TEXT_ROOM
'''


def test_a_buttons_text_is_asked_of_the_button(run_ike):
    """1.1.23: "SystemError: Negative size passed to PyUnicode_New" in
    IkeStyle.sizeFromContents (tests on Arch, main too): PyQt 6.12 now and
    then hands a Python method of a style the wrapper of an option that no
    longer exists, of another kind, found at the same address; its text was
    then read as garbage (or the program crashed). The text and the tool
    button's style are asked of the button itself: an option of the wrong
    kind no longer loses the room around the text."""
    out = run_ike(STALE)
    # the room around the text is given from the button's own text, whatever
    # the option says (with an option of another kind it was not: 40 < 56)
    assert min(out["push"]) >= out["least"], out
    assert out["tool"][0] == out["tool"][1], out
