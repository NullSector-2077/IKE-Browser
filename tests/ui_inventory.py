"""Everything the interface offers, as data (1.1.29's reorganisation of the
menus and of Settings): every entry of the menu bar and of the ☰ menu with
its shortcut and the action behind it, every toolbar button, every page of
Settings with its groups and options, every keyboard shortcut of the window.

Runs inside the real browser (tests/harness.py): ``steps`` below fills
``out["inventory"]``. tests/test_menus_reorg.py compares a run with the
inventory recorded before the reorganisation (tests/data/ui-inventory-before.json):
nothing that was reachable may be lost.
"""

STEPS = r'''
def steps(ike, qapp, out):
    from PyQt6.QtGui import QAction
    from PyQt6.QtWidgets import (QAbstractButton, QCheckBox, QComboBox, QGroupBox, QLabel, QLineEdit, QMenu,
                                 QSpinBox, QWidget)
    win = ike.windows[0]
    yield 400
    names = {}
    for k, v in list(vars(win).items()):
        if isinstance(v, QAction):
            names.setdefault(id(v), k)
        elif isinstance(v, QMenu):
            names.setdefault(id(v.menuAction()), k)
            names.setdefault(id(v), k)

    def ident(a):
        return names.get(id(a)) or (a.menu() is not None and names.get(id(a.menu()))) or ""

    def dump(menu, depth=0, seen=None):
        seen = set() if seen is None else seen
        if id(menu) in seen or depth > 4:
            return []
        seen.add(id(menu))
        menu.aboutToShow.emit()                   # menus filled when they open
        rows = []
        for a in menu.actions():
            if a.isSeparator():
                rows.append({"sep": a.text()})
                continue
            row = {"text": a.text(), "id": ident(a),
                   "keys": [s.toString() for s in a.shortcuts()], "visible": a.isVisible(),
                   "checkable": a.isCheckable(), "icon": not a.icon().isNull()}
            if a.menu() is not None:
                row["menu"] = dump(a.menu(), depth + 1, seen)
            rows.append(row)
        return rows

    inv = {"menubar": [], "burger": dump(win.burger)}
    for a in win.menuBar().actions():
        if a.menu() is not None:
            inv["menubar"].append({"text": a.text(), "id": ident(a), "menu": dump(a.menu())})
    inv["toolbar"] = [ident(a) or a.text() for a in win.nav.actions()]
    inv["shortcuts"] = sorted({(s.toString(), ident(a) or a.text()) for a in win.findChildren(QAction)
                               for s in a.shortcuts() if not s.isEmpty()})
    # Settings: each page, its groups and options in the order shown
    dlg = win.open_settings()
    yield 600
    pages = []
    for row in range(dlg.nav.count()):
        page = dlg.stack.widget(row).widget()
        items = []
        for w in page.findChildren(QWidget):
            if not w.isVisibleTo(page):
                continue
            if isinstance(w, QGroupBox):
                items.append(("group", w.title()))
            elif isinstance(w, QCheckBox):
                items.append(("switch", w.text()))
            elif isinstance(w, QComboBox):
                items.append(("choice", [w.itemText(i) for i in range(w.count())][:12]))
            elif isinstance(w, QAbstractButton) and w.text():
                items.append(("button", w.text()))
            elif isinstance(w, QLabel) and w.text() and w.objectName() not in ("ike_page_title",):
                items.append(("label", w.text()[:140]))
            elif isinstance(w, (QLineEdit, QSpinBox)):
                items.append(("field", w.objectName() or type(w).__name__))
        key = dlg.PAGES[row] if hasattr(dlg, "PAGES") and row < len(dlg.PAGES) else str(row)
        pages.append({"key": key, "name": dlg.nav.item(row).text(), "items": items})
    inv["settings"] = pages
    inv["settings_icon"] = [dlg.nav.iconSize().width(), dlg.nav.iconSize().height()]
    dlg.close()
    from ike import ikeextensions
    inv["extensions"] = [e.id for e in ikeextensions.EXTENSIONS]
    out["inventory"] = inv
'''
