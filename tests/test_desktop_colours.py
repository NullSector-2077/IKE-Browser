"""Following the system, I.K.E.'s windows take the desktop's colours (1.1.22).

In each desktop of tests/desktops.py, light and dark where it has both, with
"Follow the system" (the default):

- the palette Qt gives a plain Qt program in that desktop is the palette of
  the application, and the window's background and text are its colours;
- the main window, the shield panel, the tab preview, the Settings with their
  switches and ⓘ use the palette Qt gives each of them (nothing of I.K.E.'s
  own in their place);
- every text (labels, switches, choices, the tab preview's values, the new
  tab page's) can be
  read: the colour Qt draws it in (its palette's, in an active and in an
  inactive window), against the background drawn behind it on the screen,
  is at least 4.5:1, WCAG's level AA for normal text. Disabled options are
  not measured (WCAG leaves them out).
"""

import json
import sys

import desktops
import pytest
from conftest import APP, screen

ROLES = ("Window", "WindowText", "Base", "Text", "Button", "ButtonText", "Highlight", "HighlightedText")

# a plain Qt program in the desktop: the palette its platform theme gives
PLAIN = r"""
import json, os, sys
from PyQt6.QtGui import QPalette
from PyQt6.QtWidgets import QApplication
app = QApplication(sys.argv[:1])
pal = app.palette()
roles = ROLES
out = {"palette": {r: pal.color(QPalette.ColorGroup.Active, getattr(QPalette.ColorRole, r)).name() for r in roles}}
with open(os.environ["IKE_TEST_OUT"], "w", encoding="utf-8") as f:
    json.dump(out, f)
"""

STEPS = r"""
def steps(ike, qapp, out):
    from PyQt6.QtCore import QPoint, QRect, Qt
    from PyQt6.QtGui import QColor, QImage, QPalette, QPixmap
    from PyQt6.QtWidgets import (QApplication, QCheckBox, QComboBox, QLabel, QRadioButton, QStyle,
                                 QStyleOptionButton, QToolButton)
    from ike.uistyle import Switch
    yield 400
    R, G = QPalette.ColorRole, QPalette.ColorGroup

    def colours(pal):
        return {r: pal.color(G.Active, getattr(R, r)).name() for r in ROLES}

    def settle():
        for _ in range(3):
            QApplication.processEvents()

    out["app"] = colours(qapp.palette())
    places, own, low = {}, [], []

    def follows(where, w):
        # the widget's colours are those Qt gives its kind of widget in this desktop
        got, want = colours(w.palette()), colours(QApplication.palette(w))
        places[where] = got
        if got != want:
            own.append([where, type(w).__name__, {k: [got[k], want[k]] for k in got if got[k] != want[k]}])

    def lum(rgb):
        def ch(v):
            v /= 255
            return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
        return 0.2126 * ch(rgb >> 16 & 255) + 0.7152 * ch(rgb >> 8 & 255) + 0.0722 * ch(rgb & 255)

    def ratio(a, b):
        la, lb = lum(a), lum(b)
        return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)

    def background(img, rect):
        # the commonest colour of the text's box, as drawn on the screen
        sub = img.copy(rect).convertToFormat(QImage.Format.Format_RGB32)
        counts = {}
        for y in range(0, sub.height(), 2):
            for x in range(0, sub.width(), 2):
                c = sub.pixel(x, y) & 0xFFFFFF
                counts[c] = counts.get(c, 0) + 1
        return max(counts, key=counts.get) if counts else None

    def check(where, text, kind, img, rect, inks):
        # inks: what the text is drawn in (the palette's, as Qt draws it)
        bg = background(img, rect)
        if bg is None:
            return 0
        for c in inks:
            a = c.alphaF()                # a colour that lets the background through, as drawn
            rgb = 0
            for shift in (16, 8, 0):
                rgb |= round((c.rgb() >> shift & 255) * a + (bg >> shift & 255) * (1 - a)) << shift
            r = ratio(rgb, bg)
            if r < 4.5:
                low.append([where, text[:60], kind, round(r, 2), c.name(), "#%06x" % bg])
        return 1

    def drawn(w, role):
        return [w.palette().color(g, role) for g in (G.Active, G.Inactive)]

    def texts(top, where, img=None):
        if img is None:
            img = top.grab().toImage()
        scale = img.devicePixelRatio()
        n = 0
        for w in top.findChildren(QLabel) + top.findChildren(QCheckBox) + top.findChildren(QRadioButton):
            if not w.isVisible() or not w.isEnabled() or w.window() is not top.window():
                continue
            if not w.text().strip() or isinstance(w, QLabel) and w.pixmap() is not None and not w.pixmap().isNull():
                continue
            if isinstance(w, QLabel):
                box = w.contentsRect()
            else:
                opt = QStyleOptionButton()
                w.initStyleOption(opt)
                box = w.style().subElementRect(QStyle.SubElement.SE_CheckBoxContents
                                               if isinstance(w, QCheckBox) else
                                               QStyle.SubElement.SE_RadioButtonContents, opt, w)
            box = box.intersected(w.visibleRegion().boundingRect())
            if box.width() < 4 or box.height() < 4:
                continue
            at = w.mapTo(top, box.topLeft())
            rect = QRect(round(at.x() * scale), round(at.y() * scale),
                         round(box.width() * scale), round(box.height() * scale))
            inks = drawn(w, w.foregroundRole())
            if "<a " in w.text():
                inks += drawn(w, R.Link)
            n += check(where, w.text(), type(w).__name__, img, rect, inks)
        return n

    measured = {}
    win = ike.windows[0]
    win.showMaximized()
    yield 300
    follows("window", win)
    out["window"] = [win.palette().color(R.Window).name(), win.palette().color(R.WindowText).name()]
    measured["window"] = texts(win, "window")

    win.show_shield_menu()
    settle()
    win.shield_panel.adv_btn.setChecked(True)
    settle()
    win.fit_shield_menu()
    settle()
    follows("shield panel", win.shield_panel)
    follows("shield menu", win.shield_menu)
    for i, sw in enumerate(x for x in win.shield_panel.findChildren(Switch) if x.isVisible()):
        follows("shield switch %d" % i, sw)
    measured["shield panel"] = texts(win.shield_menu, "shield panel")
    win.shield_panel.adv_btn.setChecked(False)
    win.shield_menu.hide()

    from ike.tabpreview import TabPreview
    prev = TabPreview(win)
    picture = QPixmap(320, 180)
    picture.fill(QColor("#808080"))
    prev.show_for(0, picture, "Example Domain — example.org", win.mapToGlobal(QPoint(120, 40)),
                  win.current_view())
    yield 400
    follows("tab preview", prev)
    img = prev.grab().toImage()
    measured["tab preview"] = texts(prev, "tab preview", img)
    scale = img.devicePixelRatio()
    for name in ("cpu", "mem"):           # the name of each value, painted by the card itself
        meter = getattr(prev, name)
        at = meter.mapTo(prev, QPoint(0, 0))
        rect = QRect(round(at.x() * scale), round(at.y() * scale), round(meter.width() * scale),
                     round(meter.fontMetrics().height() * scale))
        if hasattr(meter, "colours"):
            inks = list(meter.colours())
        else:                             # before 1.1.22: the text's colour (the card's window is
            pal = meter.palette()         # never active), the name at 65 % of it
            text, bg = pal.color(G.Inactive, R.WindowText), pal.color(G.Inactive, R.Window)
            inks = [QColor(round(text.red() * 0.65 + bg.red() * 0.35),
                              round(text.green() * 0.65 + bg.green() * 0.35),
                              round(text.blue() * 0.65 + bg.blue() * 0.35)), text]
        measured["tab preview"] += check("tab preview", name + ": " + meter.label, "meter", img, rect, inks)
    prev.hide_preview()

    dlg = win.open_settings()
    settle()
    follows("settings", dlg)
    for i, page in enumerate(dlg.PAGES):
        dlg.nav.setCurrentRow(i)
        settle()
        measured["settings " + page] = texts(dlg, "Settings > " + page)
        if page == "protection":
            for j, sw in enumerate(x for x in dlg.findChildren(Switch) if x.isVisible()):
                follows("switch %d" % j, sw)
            for j, b in enumerate(x for x in dlg.findChildren(QToolButton, "ike_info") if x.isVisible()):
                follows("info %d" % j, b)
            for j, c in enumerate(x for x in dlg.findChildren(QComboBox) if x.isVisible()):
                follows("choice %d" % j, c)
    dlg.close()

    # the new tab page, I.K.E.'s own page in the desktop's colours: its text
    # (4.5:1), its large numbers and the outlines in the accent (3:1, WCAG's
    # level for large text and for the parts of a page one acts on)
    import re
    root = dict(re.findall(r"--(\w+):(#[0-9a-fA-F]{6})", ike.shields.newtab_html().split("}", 1)[0]))
    bg = int(root["bg"][1:], 16)
    for var, least in (("fg", 4.5), ("mute", 4.5), ("acc", 3.0)):
        r = ratio(int(root[var][1:], 16), bg)
        if r < least:
            low.append(["new tab page", "--" + var, "page", round(r, 2), root[var], root["bg"]])
    measured["new tab page"] = 3
    out["places"] = places
    out["own"] = own
    out["low"] = low
    out["measured"] = measured
""".replace("ROLES", repr(ROLES))


@pytest.mark.parametrize("desktop", list(desktops.DESKTOPS))
def test_windows_take_the_desktops_colours(run_ike, tmp_path, desktop):
    try:
        env = desktops.prepare(desktop, tmp_path / "home")
    except desktops.Unavailable as why:
        pytest.skip(str(why))
    env.update(screen(tmp_path, 1366, 768))
    plain = tmp_path / "plain.py"
    plain.write_text(PLAIN.replace("roles = ROLES", "roles = " + repr(ROLES)), "utf-8")
    want = run_ike("", env=env, command=[sys.executable, str(plain)])["palette"]
    out = run_ike(STEPS, env=env, timeout=300)
    assert out["app"] == want, "I.K.E.'s palette is not the desktop's:\n%s\n%s" % (out["app"], want)
    assert out["window"] == [want["Window"], want["WindowText"]], out["window"]
    assert len(out["places"]) > 10 and sum(out["measured"].values()) > 100, (out["places"].keys(), out["measured"])
    assert not out["own"], "colours of I.K.E.'s own in place of the desktop's:\n" + "\n".join(map(json.dumps, out["own"]))
    assert not out["low"], "%d texts below 4.5:1:\n%s" % (len(out["low"]), "\n".join(map(json.dumps, out["low"])))


def test_readable_keeps_a_colour_that_reads_and_mends_one_that_does_not():
    """uistyle.readable, used by the notes of the Settings and the tab
    preview: a colour that reads stays as it is; a pale one (KDE's Breeze
    light placeholder, 3.7:1) is taken towards the text until it reads 4.5:1;
    when the text itself reads less (GNOME's inactive text), towards black or
    white; a colour that lets the background through counts as drawn."""
    sys.path.insert(0, str(APP))
    from PyQt6.QtGui import QColor

    from ike.uistyle import contrast, readable
    assert readable("#232629", "#eff0f1", "#232629").name() == "#232629"
    mended = readable("#707d8a", "#eff0f1", "#232629")
    assert round(contrast("#707d8a", "#eff0f1"), 2) == 3.69
    assert 4.5 <= contrast(mended, "#eff0f1") < 5.2 and mended.name() != "#232629"
    assert contrast(readable("#5e5e5e", "#323232", "#919190"), "#323232") >= 4.5
    assert contrast(readable("#5e5e5e", "#323232", "#919190", 5.0), "#323232") >= 5.0
    half = QColor(0, 0, 0, 128)                     # black at 50 % on white: #7f7f7f, 4.0:1
    assert contrast(readable(half, "#ffffff", "#000000"), "#ffffff") >= 4.5
    yellow = readable("#ffff00", "#ffffff", "#ffffff")       # white text on white: towards black
    assert contrast(yellow, "#ffffff") >= 4.5 and yellow.red() == yellow.green() > yellow.blue() == 0
