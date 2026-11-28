"""Does every text of the interface fit its place? (1.1.21)

Loaded inside the browser by tests/test_text_fit.py. ``check(widget)`` looks
at the visible widgets under ``widget`` and returns one line per problem:

- a button (push button, tool button with text): its text and icon fit
  inside the button, at least MARGIN pixels from its frame on each side, and
  are centred where the style centres them;
- a check box or a radio button: its text fits beside the box;
- a label: its whole text fits (a wrapped label is tall enough for all of its
  lines, a long word does not stick out), unless the label cuts its text on
  purpose (the property ``ike_elides``);
- a combo box: the chosen entry fits its field (unless the box was made
  narrow on purpose, ``ike_elides``), and in its open list every entry fits;
- a group box: its title fits;
- every widget lies inside its parents (nothing cut by the edge of a frame
  or a window, no sideways scrolling in a scroll area) and every window
  inside the screen.

``check_menu(menu)`` does the same for the entries of a menu: each text and
its shortcut fit the entry, the menu fits the screen's width, and a menu
taller than the screen scrolls; since 1.1.24 also the text of an entry that
opens a submenu keeps ARROW_GAP px from its arrow (the "More" menu of the ☰
menu, in KDE's Breeze, had "View" and "Tools" touching it).
"""

import re

from PyQt6.QtCore import QPoint, QRect, Qt
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import (
    QAbstractButton,
    QAbstractScrollArea,
    QCheckBox,
    QComboBox,
    QFontComboBox,
    QGroupBox,
    QLabel,
    QListWidget,
    QMenu,
    QPushButton,
    QRadioButton,
    QStyle,
    QStyleOptionButton,
    QStyleOptionComboBox,
    QStyleOptionGroupBox,
    QToolButton,
    QWidget,
)

MARGIN = 4


def plain(text):
    """The text as shown: without the "&" of a keyboard accelerator."""
    return re.sub(r"&(.)", r"\1", text or "")


def _name(w):
    n = type(w).__name__
    if w.objectName():
        n += "#" + w.objectName()
    return n


def _screen_area(w):
    s = w.screen() if w is not None else None
    s = s or QGuiApplication.primaryScreen()
    return s.availableGeometry()


def _width(fm, text):
    return max((fm.horizontalAdvance(line) for line in text.split("\n")), default=0)


def _clipped(w, top):
    """Where w is cut by one of its parents (None: nowhere)."""
    r = QRect(QPoint(0, 0), w.size())
    child = w
    p = w.parentWidget()
    while p is not None:
        r.translate(child.pos())
        inside = p.rect()
        viewport = isinstance(p.parentWidget(), QAbstractScrollArea) and p is p.parentWidget().viewport()
        if viewport:
            # a scroll area may scroll up and down; sideways it must not have to
            if r.left() < inside.left() - 1 or r.right() > inside.right() + 1:
                return "needs sideways scrolling in %s (sticks out by %d px)" % (
                    _name(p.parentWidget()), max(inside.left() - r.left(), r.right() - inside.right()))
        else:
            if not p.isWindow() and isinstance(p, QAbstractScrollArea):
                pass
            elif (r.left() < inside.left() - 1 or r.right() > inside.right() + 1
                  or r.top() < inside.top() - 1 or r.bottom() > inside.bottom() + 1):
                # the visible part only: a widget scrolled out of a viewport is not cut
                return "cut by %s (%d,%d %dx%d in %dx%d)" % (_name(p), r.x(), r.y(), r.width(), r.height(),
                                                             inside.width(), inside.height())
        if p is top or p.isWindow():
            break
        child = p
        p = p.parentWidget()
        if viewport:
            break           # what the viewport holds is checked, the scroll area itself below
    return None


def _button_problem(b):
    text = plain(b.text())
    if not text.strip():
        return None
    fm = b.fontMetrics()
    tw = _width(fm, text)
    icon = 0
    if not b.icon().isNull():
        icon = b.iconSize().width() + 4
    if isinstance(b, (QCheckBox, QRadioButton)):
        opt = QStyleOptionButton()
        b.initStyleOption(opt)
        sub = (QStyle.SubElement.SE_CheckBoxContents if isinstance(b, QCheckBox)
               else QStyle.SubElement.SE_RadioButtonContents)
        r = b.style().subElementRect(sub, opt, b)
        if tw + icon > r.width() + 1:
            return "text cut (%d px of text in %d px)" % (tw + icon, r.width())
        if fm.height() > b.height() + 1:
            return "text taller than the box (%d > %d)" % (fm.height(), b.height())
        return None
    if isinstance(b, QToolButton) and b.toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonIconOnly:
        return None
    if isinstance(b, QToolButton) and b.toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonTextOnly:
        icon = 0
    frame = b.style().pixelMetric(QStyle.PixelMetric.PM_DefaultFrameWidth, None, b)
    if isinstance(b, QPushButton) and b.menu() is not None:
        icon += b.style().pixelMetric(QStyle.PixelMetric.PM_MenuButtonIndicator, None, b)
    if isinstance(b, QToolButton) and b.arrowType() != Qt.ArrowType.NoArrow:
        icon += 12
    room = b.width() - 2 * frame - tw - icon
    if room < 2 * MARGIN:
        return "text too close to the edge (%d px left for %d px of text, wants %d on each side)" % (
            b.width() - 2 * frame, tw + icon, MARGIN)
    v = b.height() - 2 * frame - fm.height()
    if v < 2:
        return "text too close to the top or bottom (%d px for a %d px line)" % (
            b.height() - 2 * frame, fm.height())
    return None


def _label_problem(lab):
    text = lab.text()
    if not text.strip() or lab.property("ike_elides"):
        return None
    if lab.pixmap() is not None and not lab.pixmap().isNull():
        return None
    w, h = lab.width(), lab.height()
    if lab.wordWrap():
        need = lab.heightForWidth(w)
        if need > h + 1:
            return "wrapped text cut (needs %d px of height, has %d)" % (need, h)
        least = lab.minimumSizeHint().width()
        if least > w + 1:
            return "a word is wider than the label (%d > %d)" % (least, w)
        return None
    hint = lab.sizeHint()
    if hint.width() > w + 1:
        return "text cut (needs %d px, has %d)" % (hint.width(), w)
    if hint.height() > h + 1:
        return "text cut at the bottom (needs %d px, has %d)" % (hint.height(), h)
    return None


def _combo_problem(c):
    if c.isEditable() or c.property("ike_elides"):
        return None
    text = c.currentText()
    if not text:
        return None
    opt = QStyleOptionComboBox()
    c.initStyleOption(opt)
    field = c.style().subControlRect(QStyle.ComplexControl.CC_ComboBox, opt,
                                     QStyle.SubControl.SC_ComboBoxEditField, c)
    need = _width(c.fontMetrics(), text)
    if not c.itemIcon(c.currentIndex()).isNull():
        need += c.iconSize().width() + 4
    if need > field.width():
        return "chosen entry cut (%d px of text in %d px)" % (need, field.width())
    return None


def _combo_items(c):
    """Problems of the entries of a combo box's list, open."""
    out = []
    if c.count() == 0 or isinstance(c, QFontComboBox):
        return out             # the names of the fonts, each drawn in its own font
    c.showPopup()
    view = c.view()
    try:
        fm = view.fontMetrics()
        avail = view.viewport().width()
        for row in range(c.count()):
            text = c.itemText(row)
            if not text:
                continue
            need = _width(fm, text) + 2 * MARGIN
            if not c.itemIcon(row).isNull():
                need += c.iconSize().width() + 4
            if need > avail + 1:
                out.append(("item %r" % text, "list entry cut (%d px for %d px)" % (avail, need)))
    finally:
        c.hidePopup()
    return out


def _group_problem(g):
    title = plain(g.title())
    if not title:
        return None
    opt = QStyleOptionGroupBox()
    g.initStyleOption(opt)
    r = g.style().subControlRect(QStyle.ComplexControl.CC_GroupBox, opt,
                                 QStyle.SubControl.SC_GroupBoxLabel, g)
    if r.right() > g.width() or r.left() < 0:
        return "title cut (%d px in %d px)" % (r.width(), g.width())
    return None


def _list_items(lst):
    out = []
    fm = lst.fontMetrics()
    for row in range(lst.count()):
        it = lst.item(row)
        r = lst.visualItemRect(it)
        need = _width(fm, it.text()) + 2 * MARGIN
        if not it.icon().isNull():
            need += lst.iconSize().width() + 4
        if need > min(r.width(), lst.viewport().width()) + 1:
            out.append(("item %r" % it.text(), "list entry cut (%d px for %d px)" % (r.width(), need)))
    return out


def check(top, where, combos=True):
    """[(where, widget, text, problem)] for the visible widgets under top."""
    out = []
    widgets = [top] + top.findChildren(QWidget)
    area = _screen_area(top)
    win = top.window()
    if win.width() > area.width() + 1 or win.height() > area.height() + 1:
        out.append((where, _name(win), win.windowTitle(),
                    "window larger than the screen (%dx%d on %dx%d)" % (
                        win.width(), win.height(), area.width(), area.height())))
    for w in widgets:
        if not w.isVisible() or w.width() <= 0 or w.height() <= 0 or isinstance(w, QMenu):
            continue
        if w.isWindow() and w is not top:
            continue
        problem, text = None, ""
        if isinstance(w, QAbstractButton):
            text = plain(w.text())
            problem = _button_problem(w)
        elif isinstance(w, QLabel):
            text = w.text()
            problem = _label_problem(w)
        elif isinstance(w, QComboBox):
            text = w.currentText()
            problem = _combo_problem(w)
            if combos:
                for t, p in _combo_items(w):
                    out.append((where, _name(w), t, p))
        elif isinstance(w, QGroupBox):
            text = w.title()
            problem = _group_problem(w)
        elif isinstance(w, QListWidget) and w.objectName() == "settingsNav":
            for t, p in _list_items(w):
                out.append((where, _name(w), t, p))
        if problem:
            out.append((where, _name(w), text, problem))
        if w is not top and (text or isinstance(w, (QAbstractButton, QComboBox))):
            cut = _clipped(w, win)
            if cut:
                out.append((where, _name(w), text or w.toolTip(), cut))
    return out


def _far(c, r, g, b):
    return abs(((c >> 16) & 255) - r) + abs(((c >> 8) & 255) - g) + abs((c & 255) - b) > 90


ARROW_GAP = 6       # px at least between the text of an entry and the arrow of its submenu (1.1.24)


def _entry_picture(menu, a, text=None):
    """The entry of a menu as the style draws it, with its own text or with text."""
    from PyQt6.QtGui import QImage, QPainter
    from PyQt6.QtWidgets import QStyleOptionMenuItem
    r = menu.actionGeometry(a)
    opt = QStyleOptionMenuItem()
    try:
        menu.initStyleOption(opt, a)
    except RuntimeError:
        # a menu made by Qt itself (the menu bar's addMenu): the option as QMenu
        # fills it for an entry that opens a submenu
        T = QStyleOptionMenuItem.MenuItemType
        opt.initFrom(menu)
        if not a.isEnabled():
            opt.state &= ~QStyle.StateFlag.State_Enabled
        opt.font = menu.font()
        opt.fontMetrics = menu.fontMetrics()
        opt.text = a.text()
        opt.icon = a.icon()
        opt.menuItemType = T.SubMenu
        opt.checkType = QStyleOptionMenuItem.CheckType.NotCheckable
        opt.menuHasCheckableItems = any(x.isCheckable() for x in menu.actions())
        icons = any(not x.icon().isNull() for x in menu.actions())
        opt.maxIconWidth = (menu.style().pixelMetric(QStyle.PixelMetric.PM_SmallIconSize, None, menu) + 4
                            if icons else 0)
        opt.reservedShortcutWidth = 0
        opt.menuRect = menu.rect()
    opt.rect = QRect(0, 0, r.width(), r.height())
    opt.state &= ~QStyle.StateFlag.State_Selected
    if text is not None:
        opt.text = text
    img = QImage(r.width(), r.height(), QImage.Format.Format_ARGB32)
    img.fill(menu.palette().color(menu.backgroundRole()))
    p = QPainter(img)
    p.setLayoutDirection(menu.layoutDirection())       # as QMenu's own painter (right to left: AlignLeft is right)
    p.setFont(menu.font())
    menu.style().drawControl(QStyle.ControlElement.CE_MenuItem, opt, p, menu)
    p.end()
    return img


def arrow_gap(menu, a):
    """Pixels between the end of an entry's text and the arrow of its submenu
    (None: nothing to measure). The entry is drawn by the style twice, with
    and without its text: the text is what differs; the arrow is what is
    drawn on the far half of the entry without a text."""
    if a.menu() is None or not a.text():
        return None
    with_text, without = _entry_picture(menu, a), _entry_picture(menu, a, "")
    w, h = with_text.width(), with_text.height()
    rtl = menu.isRightToLeft()
    text_x = [x for x in range(w) for y in range(h) if with_text.pixel(x, y) != without.pixel(x, y)]
    if not text_x:
        return None
    counts = {}
    for x in range(w):
        for y in range(h):
            c = without.pixel(x, y)
            counts[c] = counts.get(c, 0) + 1
    bg = max(counts, key=counts.get)
    br, bgg, bb = (bg >> 16) & 255, (bg >> 8) & 255, bg & 255
    half = range(0, w // 2) if rtl else range(w // 2, w)
    arrow_x = [x for x in half for y in range(h) if _far(without.pixel(x, y), br, bgg, bb)]
    if not arrow_x:
        return None
    if rtl:
        return min(text_x) - max(arrow_x) - 1
    return min(arrow_x) - max(text_x) - 1


def check_menu(menu, where):
    """[(where, "QMenu", text, problem)] for the entries of an open menu."""
    out = []
    # 1.1.24: the text of an entry never touches the arrow of its submenu
    for a in menu.actions():
        if a.isVisible() and a.menu() is not None and not a.isSeparator():
            gap = arrow_gap(menu, a)
            if gap is not None and gap < ARROW_GAP:
                out.append((where, "QMenu", plain(a.text()),
                            "text %d px from its submenu's arrow (wants %d)" % (gap, ARROW_GAP)))
    area = _screen_area(menu)
    if menu.width() > area.width() + 1:
        out.append((where, "QMenu", menu.title(), "menu wider than the screen"))
    if menu.height() > area.height() + 1:
        out.append((where, "QMenu", menu.title(), "menu taller than the screen (%d > %d)" % (
            menu.height(), area.height())))
    elif menu.sizeHint().height() > area.height() + 1 and not menu.style().styleHint(
            QStyle.StyleHint.SH_Menu_Scrollable, None, menu):
        out.append((where, "QMenu", menu.title(), "a menu taller than the screen does not scroll"))
    # the entries: nothing drawn within MARGIN px of the menu's sides (looked at in
    # a picture of the menu, so it holds whatever the style)
    img = menu.grab().toImage()
    ratio = img.devicePixelRatio() or 1.0
    # the frame: the style's panel, at least the one line every style draws
    panel = max(1, menu.style().pixelMetric(QStyle.PixelMetric.PM_MenuPanelWidth, None, menu))
    left, right = panel, menu.width() - 1 - panel
    for a in menu.actions():
        if a.isSeparator() or not a.isVisible():
            continue
        r = menu.actionGeometry(a)
        if r.isEmpty():
            continue
        if r.left() < 0 or r.right() > menu.width() - 1:
            out.append((where, "QMenu", plain(a.text()), "entry sticks out of the menu (%d px wide, the entry %d..%d)"
                        % (menu.width(), r.left(), r.right())))
            continue
        if not a.text() or getattr(a, "defaultWidget", None) is not None and a.defaultWidget():
            continue
        start = list(range(left, left + MARGIN))
        end = list(range(right - MARGIN + 1, right + 1))
        if menu.isRightToLeft():
            start, end = end, start
        # the side where a text ends (its shortcut, its arrow) always; the side where it
        # starts unless the entry can be ticked (some styles frame a ticked icon up to the edge)
        band = end if a.isCheckable() else start + end
        ys = range(max(0, r.top() + 2), min(menu.height(), r.bottom() - 1))
        colours = {}
        for x in band:
            for y in ys:
                c = img.pixel(int(x * ratio), int(y * ratio))
                colours[c] = colours.get(c, 0) + 1
        if not colours:
            continue
        bg = max(colours, key=colours.get)
        br, bgg, bb = (bg >> 16) & 255, (bg >> 8) & 255, bg & 255
        touching = [x for x in band for y in ys
                    if _far(img.pixel(int(x * ratio), int(y * ratio)), br, bgg, bb)]
        if touching:
            side = "left" if min(touching) < left + MARGIN else "right"
            out.append((where, "QMenu", plain(a.text()),
                        "entry drawn within %d px of the menu's %s side" % (MARGIN, side)))
    return out
