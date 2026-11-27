"""The menu bar and the ☰ menu, described in one place (1.1.30, the owner's
reorganisation).

Both are made of the window's own QActions and QMenus (window._build_menus
creates them, features._build_feature_actions too): an entry does the same
thing, with the same shortcut, wherever it is. The lists below only say
where each one goes, so moving an entry is a change of one line here.

An entry is
- "name": an attribute of the window, a QAction or a QMenu (a QMenu is shown
  as its submenu in the menu bar);
- "-": a line between groups;
- ("section", "Title"): a group's name, drawn small and dimmed;
- ("inline", "name"): in the ☰ menu, a submenu of the menu bar shown in place
  as a named group of its entries, so that the ☰ menu never goes deeper than
  its categories (the owner: at most two levels); filled again each time;
- ("levels",): the protection levels, one for every site;
- ("extensions",): I.K.E.'s extensions under their headings (ikeextensions.CATEGORIES);
- ("library",): ☰'s bookmarks and history (window._fill_library).

Entries of the window that do not exist (a private window has no containers)
are left out, and so is a group left empty.
"""

from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QMenu

from .i18n import T


def _t(text):
    """A text translated where it is shown (marked for tools/check-lang.py)."""
    return text


# --- the menu bar: (title with its "&" key, key, entries) ---------------------
MENUBAR = (
    (_t("&File"), "file", (
        "act_open_file", "act_save_page", "act_pdf", "act_print", "act_shot", "-",
        "act_downloads", "-",
        "act_import", "act_backup", "act_restore", "-",
        "act_quit")),
    (_t("&Edit"), "edit", (
        "act_undo", "act_redo", "-",
        "act_cut", "act_copy", "act_paste", "act_select_all", "-",
        "act_find")),
    (_t("T&abs"), "tabs", (
        "act_new_tab", "act_new_window", "act_new_private", "m_containers", "m_profiles", "-",
        "act_reopen", "act_search_tabs", "-",
        "act_split", "m_workspaces", "-",
        "act_close_tab", "act_close_window")),
    (_t("&Page"), "page", (
        "act_zoom_in", "act_zoom_out", "act_zoom_reset", "-",
        "act_reader", "m_dark", "act_translate", "-",
        "act_mute", "act_float", "-",
        "act_source", "act_devtools")),
    (_t("&View"), "view", (
        "act_fullscreen", "-",
        "act_vertical", "act_menubar", "act_bookbar", "act_titlebar", "-",
        "act_customise")),
    (_t("Hi&story"), "history", ()),                 # filled when it opens: window._fill_history
    (_t("&Bookmarks"), "bookmarks", ()),             # window._fill_bookmarks
    (_t("P&rivacy"), "privacy", (
        ("levels",), "-",
        "act_repair", "act_permissions", "act_update_lists", "-",
        "act_clear", "act_passwords", "act_fill_login", "-",
        "act_protection_settings")),
    (_t("E&xtensions"), "extensions", (
        ("extensions",), "-",
        "act_manage_ext", "act_store")),
    (_t("&Tools"), "tools", (
        "act_command_bar", "-",
        "act_resources", "act_suspend", "act_watches", "-",
        "act_engines", "-",
        "act_settings")),
    (_t("&Help"), "help", (
        "act_shortcuts", "act_check_updates", "-",
        "act_about", "act_about_qt")),
)

# --- the ☰ menu: entries, and its categories ----------------------------------
# a category: ("category", key, title, icon names, tooltip, entries)
BURGER = (
    "act_new_tab", "act_new_window", "act_new_private", "-",
    ("category", "tabs", _t("Tabs and windows"), ("tab-duplicate", "window-duplicate", "tab-new"),
     _t("Reopen, find, split and close tabs; containers, workspaces and profiles"), (
         "act_reopen", "act_search_tabs", "act_split", "-",
         "act_close_tab", "act_close_window",
         ("inline", "m_containers"), ("inline", "m_workspaces"), ("inline", "m_profiles"))),
    ("category", "page", _t("Web page"), ("internet-web-browser", "applications-internet", "text-html",
                                             "view-readermode"),
     _t("Find, zoom, read, translate, dark mode and the page's source"), (
         "act_find", "act_reader", "act_translate", "act_fullscreen",
         ("section", _t("Zoom")), "act_zoom_in", "act_zoom_out", "act_zoom_reset",
         ("inline", "m_dark"),
         ("section", _t("Developer")), "act_source", "act_devtools")),
    ("category", "edit", _t("Edit"), ("edit-copy", "document-edit", "edit-paste"),
     _t("Undo, cut, copy and paste"), (
         "act_undo", "act_redo", "-",
         "act_cut", "act_copy", "act_paste", "act_select_all")),
    ("category", "file", _t("File and downloads"), ("document-multiple", "folder-documents", "document-open"),
     _t("Open a file, save or print the page, screenshots and downloads"), (
         "act_open_file", "act_save_page", "act_pdf", "act_print",
         ("inline", "m_shot"), "-",
         "act_downloads")),
    ("category", "media", _t("Audio and video"), ("applications-multimedia", "media-playback-start",
                                              "audio-volume-high"),
     _t("The sound of the tab and the video in a floating window"), (
         "act_mute", "act_float")),
    ("category", "library", _t("Bookmarks and history"), ("bookmarks", "user-bookmarks-symbolic", "view-history"),
     _t("Your bookmarks, the pages visited recently and all the history"), (
         ("library",),)),
    ("category", "privacy", _t("Privacy and security"), None,           # the shield of the level (window)
     _t("How much I.K.E. blocks, passwords, and the tools to repair or clean a site"), (
         ("levels",), "-",
         "act_repair", "act_permissions", "act_update_lists", "-",
         "act_clear", "act_passwords", "act_fill_login", "-",
         "act_protection_settings")),
    ("category", "look", _t("Browser appearance"), ("preferences-desktop-theme", "preferences-desktop"),
     _t("Vertical tabs, the menu bar, the bookmarks bar and the toolbar"), (
         "act_vertical", "act_menubar", "act_bookbar", "act_titlebar", "-",
         "act_customise")),
    ("category", "extensions", _t("I.K.E. extensions"), ("plugins", "preferences-plugin", "application-x-addon"),
     _t("Features of I.K.E. you can switch on and off"), (
         ("extensions",), "-",
         "act_manage_ext", "act_store")),
    ("category", "tools", _t("Performance and tools"), ("tools", "applications-utilities", "utilities-system-monitor"),
     _t("Command bar, site resources, sleeping tabs, watched pages and search engines"), (
         "act_command_bar", "-",
         "act_resources", "act_suspend", "act_watches", "-",
         "act_engines")),
    ("category", "backup", _t("Backup and restore"), ("document-save-as", "document-export", "document-save"),
     _t("Import from another browser, back up I.K.E.'s data or restore it"), (
         "act_import", "act_backup", "act_restore")),
    "-",
    "act_settings",
    ("category", "help", _t("Help"), ("help-contents", "help-about", "system-help"),
     _t("Keyboard shortcuts, updates and the versions of Qt"), (
         "act_shortcuts", "act_check_updates", "act_about_qt")),
    "-",
    "act_about", "act_quit",
)


def _get(win, name):
    if name in getattr(win, "menu_skip", ()):
        return None
    return getattr(win, name, None)


def _add(win, m, entry, burger):
    """Put one entry in menu m. Returns whether something was added."""
    if entry == "-":
        m.addSeparator()
        return False
    if isinstance(entry, str):
        obj = _get(win, entry)
        if obj is None:
            return False
        if isinstance(obj, QMenu):
            m.addMenu(obj)
        else:
            m.addAction(obj)
        return True
    kind = entry[0]
    if kind == "section":
        m.addSection(T(entry[1]))
        return False
    if kind == "inline":
        sub = _get(win, entry[1])
        if sub is None:
            return False
        if not burger:
            m.addMenu(sub)
            return True
        act = sub.menuAction()
        if not act.isVisible():                  # its extension is off
            return False
        sub.aboutToShow.emit()                   # dynamic menus fill themselves when they open
        m.addSection(_plain(sub.title()))
        for a in sub.actions():
            if a.isSeparator():
                continue                         # the group's own lines would split it in two
            if a.parent() is sub:
                # made by the submenu's filler, which deletes it when it fills
                # again: a copy that does the same
                c = QAction(a.icon(), a.text(), m)
                c.setCheckable(a.isCheckable())
                c.setChecked(a.isChecked())
                c.setEnabled(a.isEnabled())
                if a.toolTip() != a.text():         # (Qt gives its text as the tooltip otherwise)
                    c.setToolTip(a.toolTip())
                c.triggered.connect(lambda _c=False, a=a: a.trigger())
                a = c
            m.addAction(a)
        return True
    if kind == "levels":
        m.addSection(T("Protection level for every site"))
        for a in win.level_group.actions():
            m.addAction(a)
        return True
    if kind == "extensions":
        from . import ikeextensions
        for _key, name, _icons, exts in ikeextensions.by_category():
            m.addSection(T(name))
            for e in exts:
                m.addAction(win.ext_actions[e.id])
        return True
    if kind == "library":
        win._fill_library(m)
        return True
    return False


def _plain(title):
    """A menu's title as a group's name: no "&" of the menu bar, no final "…"."""
    return title.replace("&&", "\0").replace("&", "").replace("\0", "&").rstrip("…").rstrip()


def fill(win, m, entries, burger=False):
    """Fill menu m with entries."""
    m.clear()
    for entry in entries:
        _add(win, m, entry, burger)
    _tidy(m)


def _tidy(m):
    """A group's name with nothing shown under it goes. (Lines between
    groups that are hidden are dropped by Qt itself: separatorsCollapsible.)"""
    acts = m.actions()
    for i, a in enumerate(acts):
        if a.isSeparator() and a.text():
            for b in acts[i + 1:]:
                if b.isSeparator():
                    m.removeAction(a)
                    break
                if b.isVisible():
                    break
            else:
                m.removeAction(a)


def build_menubar(win, menu_factory):
    """The menus of the menu bar. Returns {key: QMenu}."""
    mb = win.menuBar()
    menus = {}
    for title, key, entries in MENUBAR:
        if key == "history":
            m = win.m_history = mb.addMenu(T(title))
            m.aboutToShow.connect(lambda m=m: win._fill_history(m))
        elif key == "bookmarks":
            m = win.m_bookmarks = mb.addMenu(T(title))
            m.aboutToShow.connect(lambda m=m: win._fill_bookmarks(m))
        else:
            m = mb.addMenu(T(title))
            fill(win, m, entries)
        m.setToolTipsVisible(True)
        menus[key] = m
    return menus


def build_burger(win, menu_factory, privacy_icon):
    """The ☰ menu: its direct entries and its categories, each a submenu
    filled again when it opens (dynamic entries stay current). Returns it and
    {key: category QMenu}."""
    burger = QMenu(win)
    burger.setToolTipsVisible(True)
    cats = {}
    for entry in BURGER:
        if isinstance(entry, tuple) and entry[0] == "category":
            _c, key, title, icons, tip, entries = entry
            sub = menu_factory(T(title), privacy_icon if icons is None else icons, T(tip))
            # filled when it opens (dynamic entries stay current; nothing is
            # done for it while the window starts)
            sub.aboutToShow.connect(lambda sub=sub, e=entries: fill(win, sub, e, burger=True))
            burger.addMenu(sub)
            cats[key] = sub
        else:
            _add(win, burger, entry, True)
    return burger, cats
