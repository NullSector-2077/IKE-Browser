"""1.1.30 (the owner): the menus and Settings reorganised.

- Nothing that was reachable before is lost: every entry of the menu bar and
  of the ☰ menu, every keyboard shortcut (the same keys, on the same
  commands), every option of Settings (tests/ui_inventory.py, compared with
  tests/data/ui-inventory-before.json recorded on 1.1.29).
- The ☰ menu has no "More" and goes at most two levels deep.
- The extensions are under the owner's five headings, the same in the menus
  and in Settings.
- Settings: its pages in four areas, 28 px icons; every link opens its page
  (also the names of earlier versions); the search finds what moved; applying
  without changing anything changes no setting.
"""

import json
from pathlib import Path

from conftest import screen
from ui_inventory import STEPS as INVENTORY

BEFORE = json.loads((Path(__file__).parent / "data" / "ui-inventory-before.json").read_text("utf-8"))

# the old ☰ menu's own submenus: their entries are now in its categories
GONE_MENUS = {"More", "File", "Edit", "View", "Tools", "History", "Bookmarks", "Protection", "Zoom"}
# the one-line descriptions of the pages that were split (new ones replace them)
GONE_ABOUTS = {
    "Colours, icons, tabs, toolbar and the dark mode of pages.",
    "How I.K.E. works with your computer: desktop, video, memory and translation.",
    "The language of I.K.E. and the languages websites are asked for.",
    "What I.K.E. blocks: ads, trackers, fingerprinting and unsafe connections.",
    "What is kept on this computer, and what sites are allowed to use.",
}


def _rows(rows, out, depth=0, path=""):
    """Every entry of a dumped menu: (depth, path, row)."""
    for r in rows:
        if "sep" in r:
            continue
        out.append((depth, path, r))
        if "menu" in r:
            _rows(r["menu"], out, depth + 1, path + " > " + r["text"])
    return out


def _reach(inv, part):
    rows = []
    if part in ("menubar", "all"):
        for m in inv["menubar"]:
            _rows(m["menu"], rows, 1, m["text"])
    if part in ("burger", "all"):
        _rows(inv["burger"], rows, 1, "☰")
    return rows


def _sections(rows):
    out = set()
    for r in rows:
        if "sep" in r and r["sep"]:
            out.add(r["sep"])
        if "menu" in r:
            out |= _sections(r["menu"])
    return out


def _shortcuts(inv):
    """{key: text of its command}."""
    text = {r["id"]: r["text"] for _d, _p, r in _reach(inv, "all") if r["id"]}
    return sorted((k, text.get(name, name)) for k, name in inv["shortcuts"])


def test_nothing_reachable_was_lost(run_ike):
    after = run_ike(INVENTORY, timeout=150)["inventory"]
    before_all = _reach(BEFORE, "all")
    ids_before = {r["id"] for _d, _p, r in before_all if r["id"]} - {"m_more", "m_zoom"}
    ids_bar = {r["id"] for _d, _p, r in _reach(after, "menubar") if r["id"]}
    # everything is in the menu bar (but the ☰ menu's own submenus)
    burger_own = {"m_extensions", "m_help_burger", "m_level"}
    assert not ids_before - burger_own - ids_bar, sorted(ids_before - burger_own - ids_bar)
    # and in the ☰ menu (the submenus it shows in place: their entries, under their name)
    burger = _reach(after, "burger")
    ids_burger = {r["id"] for _d, _p, r in burger if r["id"]}
    inline = {"m_containers": "New tab in container", "m_profiles": "Profiles", "m_workspaces": "Workspaces",
              "m_dark": "Dark mode for pages", "act_shot": "Screenshot", "m_closed": None}
    missing = ids_before - ids_burger - set(inline)
    assert not missing, sorted(missing)
    sections = _sections(after["burger"])
    for name, title in inline.items():
        assert title is None or title in sections, (name, sorted(sections))
    # no entry's text was lost, only the old ☰ submenus that held them
    texts_before = {r["text"] for _d, _p, r in before_all}
    texts_after = {r["text"] for _d, _p, r in _reach(after, "all")}
    assert texts_before - texts_after <= GONE_MENUS, sorted(texts_before - texts_after)
    # the same keys on the same commands
    assert _shortcuts(after) == _shortcuts(BEFORE)
    # every option of Settings is still there
    items = [{json.dumps(i) for p in inv["settings"] for i in p["items"]} for inv in (BEFORE, after)]
    lost = {json.loads(i)[1] if json.loads(i)[0] == "label" else i for i in items[0] - items[1]}
    assert lost <= GONE_ABOUTS, sorted(lost - GONE_ABOUTS)
    assert after["extensions"] == BEFORE["extensions"]
    assert after["settings_icon"] == [28, 28]
    # the ☰ menu: no "More", at most two levels (a category, then its entries)
    top = [r["text"] for r in after["burger"] if "sep" not in r]
    assert "More" not in top
    assert max(d for d, _p, _r in burger) <= 2, [p for d, p, _r in burger if d > 2]
    assert top[:3] == ["New tab", "New window", "New private window"]
    assert top[-3:] == ["Help", "About I.K.E.", "Quit"] and "Settings…" in top


STEPS = r'''
def steps(ike, qapp, out):
    from ike import ikeextensions, menus
    from ike.dialogs import SettingsDialog
    win = ike.windows[0]
    yield 400
    # the extensions' headings: the same in the menu bar, the ☰ menu and Settings
    names = [n for _k, n, _i, _e in ikeextensions.by_category()]
    out["categories"] = names
    out["by_category"] = {n: [e.id for e in exts] for _k, n, _i, exts in ikeextensions.by_category()}
    bar = {k: m for k, m in win.menubar_menus.items()}

    def grouped(m):
        m.aboutToShow.emit()
        res, cur = {}, None
        for a in m.actions():
            if a.isSeparator():
                cur = a.text() or None
            elif cur is not None and a.data() in ikeextensions.BY_ID:
                res.setdefault(cur, []).append(a.data())
        return res
    out["ext_bar"] = grouped(bar["extensions"])
    out["ext_burger"] = grouped(win.m_extensions)
    # the ☰ menu's categories hold no submenu (two levels at most), in every case
    deep = []
    for a in win.burger.actions():
        if a.menu() is not None:
            a.menu().aboutToShow.emit()
            deep += [(a.text(), b.text()) for b in a.menu().actions() if b.menu() is not None]
    out["deep"] = deep
    # Settings: every link opens its page
    links = {}
    for name in list(SettingsDialog.PAGES) + list(SettingsDialog.ALIASES) + ["system", "unknown"]:
        dlg = win.open_settings(name)
        yield 150
        links[name] = dlg.PAGES[dlg.stack.currentIndex()]
        dlg.close()
    out["links"] = links
    for act in ("act_protection_settings", "act_engines", "act_manage_ext"):
        getattr(win, act).trigger()
        yield 300
        dlg = ike._dialogs.get("settings")
        out[act] = dlg.PAGES[dlg.stack.currentIndex()] if dlg is not None else None
        dlg.close()
        yield 100
    dlg = win.open_dark_settings()
    yield 300
    out["dark_link"] = dlg.PAGES[dlg.stack.currentIndex()]
    dlg.close()
    ext_pages = {}
    for e in ikeextensions.EXTENSIONS:
        if e.options.startswith("page:"):
            dlg = win.open_settings("extensions")
            yield 150
            dlg._ext_options(e.options)
            yield 150
            ext_pages[e.id] = dlg.PAGES[dlg.stack.currentIndex()]
            dlg.close()
    out["ext_pages"] = ext_pages
    # Settings: areas, rows and icons; the search finds what moved
    dlg = win.open_settings()
    yield 600
    from ike.dialogs import _NavDelegate
    out["areas"] = [dlg.nav.item(i).data(_NavDelegate.AREA) for i in range(dlg.nav.count())]
    out["icon"] = [dlg.nav.iconSize().width(), dlg.nav.iconSize().height()]
    out["rows"] = [dlg.nav.visualItemRect(dlg.nav.item(i)).height() for i in range(dlg.nav.count())]
    out["nav_scroll"] = dlg.nav.verticalScrollBar().maximum()          # the whole list in view
    found = {}
    for text in ("Translation service", "Filter lists", "Camera", "Do not let videos and sounds",
                 "Background depth", "Battery saver", "Privacy and security"):
        found[text] = sorted(dlg.find_options(text))
        yield 80
    out["found"] = found
    out["areas_searched"] = [dlg.nav.item(i).data(_NavDelegate.AREA) for i in range(dlg.nav.count())
                             if not dlg.nav.item(i).isHidden()]
    dlg.find_options("")
    # the extensions page: the same headings, in the same order
    page = dlg.stack.widget(dlg.PAGES.index("extensions")).widget()
    from PyQt6.QtWidgets import QFrame, QWidget
    heads = []
    for w in page.findChildren(QWidget):
        if w.objectName() == "ike_ext_category":
            heads.append((w.property("category"), w.mapTo(page, w.rect().topLeft()).y()))
    out["ext_heads"] = [k for k, _y in sorted(heads, key=lambda h: h[1])]
    cards = [(c.property("ext"), c.mapTo(page, c.rect().topLeft()).y()) for c in page.findChildren(QFrame)
             if c.objectName() == "ike_ext_card"]
    out["ext_cards"] = [k for k, _y in sorted(cards, key=lambda c: c[1])]
    # applying without changing anything changes no setting
    before = json.dumps(ike.config.data, sort_keys=True, default=str)
    dlg.apply()
    yield 300
    after = json.dumps(ike.config.data, sort_keys=True, default=str)
    out["kept"] = before == after
    if not out["kept"]:
        b, a = json.loads(before), json.loads(after)
        out["changed"] = {k: [b.get(k), a.get(k)] for k in set(a) | set(b) if a.get(k) != b.get(k)}
    dlg.close()
    out["spec_titles"] = [t for t, _k, _e in menus.MENUBAR]
'''


def test_links_search_extensions_and_settings_kept(run_ike, tmp_path):
    out = run_ike("import json\n" + STEPS, env=screen(tmp_path, 1366, 768), timeout=180)
    cats = out["categories"]
    assert cats == ["Privacy and security", "Browsing and appearance", "Audio and video", "Productivity",
                    "System and resources"]
    assert out["by_category"] == {
        "Privacy and security": ["passwords", "consent", "containers"],
        "Browsing and appearance": ["dark", "split", "autoscroll", "middleclick"],
        "Audio and video": ["videoads", "pip"],
        "Productivity": ["watcher", "translate", "commandbar", "userscripts"],
        "System and resources": ["resources", "weather", "plasma"]}
    assert out["ext_bar"] == out["by_category"] and out["ext_burger"] == out["by_category"]
    assert out["deep"] == [], out["deep"]
    links = out["links"]
    assert links["unknown"] == "general"
    assert links["components"] == links["userscripts"] == "extensions"
    assert links["translation"] == "language" and links["dark"] == "sites" and links["desktop"] == "system"
    pages = ["general", "language", "downloads", "updates", "appearance", "newtab", "search", "sites",
             "protection", "blocker", "privacy", "permissions", "system", "extensions"]
    assert [links[p] for p in pages] == pages
    assert out["act_protection_settings"] == "protection" and out["act_engines"] == "search"
    assert out["act_manage_ext"] == "extensions" and out["dark_link"] == "sites"
    assert out["ext_pages"] == {"dark": "sites", "translate": "language", "containers": "privacy",
                                "weather": "newtab", "plasma": "system"}, out["ext_pages"]
    areas = out["areas"]
    assert areas == ["Basics", None, None, None, "Appearance and browsing", None, None, None,
                     "Privacy and security", None, None, None, "System and extensions", None], areas
    assert out["icon"] == [28, 28]
    assert out["nav_scroll"] == 0, out["nav_scroll"]               # on a 1366 x 768 screen
    assert min(out["rows"]) >= 28 + 6, out["rows"]          # the icon never clipped (3 px around it)
    f = out["found"]
    assert "language" in f["Translation service"] and "blocker" in f["Filter lists"]
    assert "permissions" in f["Camera"] and f["Do not let videos and sounds"] == ["sites"]
    assert f["Background depth"] == ["sites"] and f["Battery saver"] == ["system"]
    assert set(f["Privacy and security"]) >= {"protection", "blocker", "privacy", "permissions"}
    assert out["ext_heads"] == ["privacy", "browsing", "media", "productivity", "system"]
    assert out["ext_cards"] == [i for c in out["by_category"].values() for i in c]
    assert out["kept"], out.get("changed")
    assert out["spec_titles"] == ["&File", "&Edit", "T&abs", "&Page", "&View", "Hi&story", "&Bookmarks",
                                  "P&rivacy", "E&xtensions", "&Tools", "&Help"]


def test_every_extension_has_a_category():
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from ike import ikeextensions
    keys = [k for k, _n, _i in ikeextensions.CATEGORIES]
    assert all(e.category in keys for e in ikeextensions.EXTENSIONS)
    assert sum(len(x[3]) for x in ikeextensions.by_category()) == len(ikeextensions.EXTENSIONS)
