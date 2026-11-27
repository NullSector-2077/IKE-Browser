"""1.1.20: the menus grouped as the owner chose, the Settings in eleven pages
and I.K.E.'s own extensions with a switch each (ikeextensions.py).

The ☰ menu and the menu bar hold the same actions; every name of a Settings
page of earlier versions still opens the Settings; every setting the Settings
window saved before is still saved, keeping its meaning; each extension's
switch (from the menu and from the Settings) changes its own setting and
shows or hides its menu entries; "Check for I.K.E. updates" asks the updater
for a manual check; automatic scrolling and "open the selected text with the
middle button" work with real mouse events and leave the middle click on
links and fields alone. All on this computer."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from test_security import JS

LONG = ("<!doctype html><title>long</title><body style='margin:0'>"
        "<a id='link' href='/target?from=link' style='display:block;height:60px;background:#ccc'>a link</a>"
        "<textarea id='field' style='display:block;width:300px;height:60px'></textarea>"
        "<div id='empty' style='height:5000px'>empty space</div></body>")


@pytest.fixture
def site():
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            path = self.path.split("?")[0]
            if path == "/long":
                body = LONG
            else:
                body = "<!doctype html><title>%s</title><body>%s</body>" % (path.strip("/"), self.path)
            body = body.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1]
    srv.shutdown()


# ----------------------------------------------------------------------
# the menus
# ----------------------------------------------------------------------
def test_menu_bar_and_burger_menu(run_ike):
    out = run_ike("""
        def steps(ike, qapp, out):
            yield 600
            win = ike.windows[0]
            out["bar"] = [a.text() for a in win.menuBar().actions()]
            burger = win.menu_btn.menu()
            out["burger"] = [a.text() for a in burger.actions() if not a.isSeparator()]
            out["no_icon"] = [a.text() for a in burger.actions() if not a.isSeparator() and a.icon().isNull()]
            out["no_tip"] = [a.text() for a in burger.actions() if not a.isSeparator()
                             and (not a.toolTip() or a.toolTip() == a.text().replace("&", ""))]
            menus = {a.text(): a.menu() for a in win.menuBar().actions()}
            tools = [a.text() for a in menus["&Tools"].actions()]
            edit = [a.text() for a in menus["&Edit"].actions()]
            out["settings_in_tools"] = "Settings…" in tools and "Settings…" not in edit
            out["settings_keys"] = win.act_settings.shortcut().toString()
            out["help"] = [a.text() for a in menus["&Help"].actions()]
            # its title is a section since 1.1.25: an entry with its name, still the first
            out["protection"] = [a.text() for a in menus["P&rivacy"].actions() if not a.isSeparator() or a.text()]
            out["extensions"] = [a.text() for a in menus["E&xtensions"].actions()
                                 if not a.isSeparator() and a.isVisible()]
            # the same QActions in both places
            # (1.1.24: "Check for I.K.E. updates" is under ☰ → Help, the menu bar's Help with an icon)
            win.m_help_burger.aboutToShow.emit()
            out["same"] = (win.act_settings in burger.actions() and win.act_settings in menus["&Tools"].actions()
                           and win.act_check_updates in menus["&Help"].actions()
                           and win.act_check_updates in win.m_help_burger.actions()
                           and win.m_help_burger.menuAction() in burger.actions())
            out["level_icon"] = not win.m_level.icon().isNull()
            out["menubar_icons"] = [a.text() for a in win.menuBar().actions() if not a.icon().isNull()]
            # every action of every menu keeps a shortcut it had before
            keys = {}
            for act in win.actions():
                for k in act.shortcuts():
                    keys.setdefault(k.toString(), []).append(act.text())
            out["keys"] = sorted(keys)
            # Esc ends two modes that never meet (customising, full screen)
            out["twice"] = {k: v for k, v in keys.items() if len(v) > 1 and k != "Esc"}
    """)
    # 1.1.29 (the owner's reorganisation, ike/menus.py)
    assert out["bar"] == ["&File", "&Edit", "T&abs", "&Page", "&View", "Hi&story", "&Bookmarks", "P&rivacy",
                          "E&xtensions", "&Tools", "&Help"]
    # new tabs and windows; the owner's categories; Settings and Help; About; Quit
    assert out["burger"] == ["New tab", "New window", "New private window",
                             "Tabs and windows", "Web page", "Edit", "File and downloads", "Audio and video",
                             "Bookmarks and history", "Privacy and security", "Browser appearance",
                             "I.K.E. extensions", "Performance and tools", "Backup and restore",
                             "Settings…", "Help", "About I.K.E.", "Quit"]
    assert out["no_icon"] == [] and out["no_tip"] == [], out
    assert out["settings_in_tools"] and out["settings_keys"] == "Ctrl+,"
    assert out["help"] == ["Keyboard shortcuts", "Check for I.K.E. updates", "", "About I.K.E.", "About Qt"]
    assert out["protection"][1:6] == ["Off", "Compatibility", "Balanced", "Kontrol", "Maximum"]
    assert {"Repair this site", "Site permissions…", "Update filter lists now",
            "Clear browsing data…"} <= set(out["protection"])
    assert out["extensions"][0] == "Password manager" and out["extensions"][-1] == "Manage extensions…"
    assert len(out["extensions"]) == 17
    assert out["same"] and out["level_icon"] and out["menubar_icons"] == []
    for k in ("Ctrl+T", "Ctrl+N", "Ctrl+Shift+N", "Ctrl+,", "Ctrl+P", "Ctrl+Shift+S", "Ctrl+Q", "Ctrl+J",
              "Ctrl+Shift+Del", "Ctrl+H", "Ctrl+D", "Ctrl+Shift+O", "Ctrl+Shift+A", "F2", "Ctrl+Shift+K",
              "Ctrl+Shift+L", "Ctrl+Shift+V", "Shift+Esc", "Ctrl+Shift+2", "F9", "F1", "F11", "Ctrl++",
              "Ctrl+-", "Ctrl+0", "Ctrl+F", "Ctrl+U", "F12", "Ctrl+Shift+M", "Ctrl+M", "Ctrl+Shift+E",
              "Ctrl+Shift+B", "Ctrl+O", "Ctrl+S", "Ctrl+W", "Ctrl+Shift+W", "Ctrl+Shift+T"):
        assert k in out["keys"], k
    # no shortcut on two commands (Qt then runs neither): Ctrl+Shift+A opens
    # the extensions, the owner's choice
    assert out["twice"] == {}, out["twice"]


def test_manual_update_check_asks_the_updater(run_ike):
    """Help → Check for I.K.E. updates and Settings → Updates → Check now: the
    same path as the update prompt, with manual=True."""
    out = run_ike("""
        def steps(ike, qapp, out):
            yield 500
            calls = []
            ike.updater.configured = lambda: True
            ike.updater.run = lambda install, manual=False: calls.append((install, manual)) or False
            win = ike.windows[0]
            win.act_check_updates.trigger()
            yield 100
            out["menu"] = list(calls)
            dlg = win.open_settings("updates")
            yield 300
            out["page"] = dlg.PAGES[dlg.stack.currentIndex()]
            calls.clear()
            dlg._check_app_now()
            yield 100
            out["settings"] = list(calls)
            dlg.close()
    """, settings={"app_updates": "ask", "last_app_check": 4102444800})
    assert out["menu"] == [[False, True]]          # (install, manual)
    assert out["page"] == "updates"
    assert out["settings"] == [[False, True]]


# ----------------------------------------------------------------------
# the Settings
# ----------------------------------------------------------------------
def test_every_page_name_still_opens(run_ike):
    out = run_ike("""
        def steps(ike, qapp, out):
            yield 500
            win = ike.windows[0]
            pages = {}
            for name in ("general", "appearance", "newtab", "search", "privacy", "components",
                         "userscripts", "downloads", "language", "protection", "extensions", "updates",
                         "system", "sites", "blocker", "permissions", "nonsense", None):
                dlg = win.open_settings(name)
                yield 150
                pages[str(name)] = [dlg.isVisible(), dlg.PAGES[dlg.stack.currentIndex()],
                                    dlg.nav.currentItem().text()]
                dlg.close()
                yield 50
            out["pages"] = pages
            # every page has its sentence on top, every option-less hint shown
            dlg = win.open_settings()
            yield 200
            from PyQt6.QtWidgets import QLabel
            abouts = []
            for i in range(dlg.stack.count()):
                lab = dlg.stack.widget(i).findChild(QLabel, "ike_page_about")
                abouts.append(bool(lab and lab.text()))
            out["abouts"] = abouts
            # 1.1.21: each explanation in the ⓘ after its option, none left as a grey line under it
            from PyQt6.QtWidgets import QToolButton
            infos = dlg.findChildren(QToolButton, "ike_info")
            out["hints"] = len(infos)
            out["hint_lines"] = len(dlg.findChildren(QLabel, "ike_hint"))
            out["infos_named"] = all(b.accessibleName() and b.accessibleName() == b.whatsThis() for b in infos)
            # a card's Options… opens its page
            dlg._ext_options("page:newtab")
            out["options_page"] = dlg.PAGES[dlg.stack.currentIndex()]
            dlg._ext_options("dialog:show_userscripts")
            yield 200
            us = ike._dialogs.get("userscripts")
            out["userscripts_window"] = bool(us is not None and us.isVisible())
            us.close()
            dlg.close()
    """)
    expected = {"general": "general", "appearance": "appearance", "newtab": "newtab", "search": "search",
                "privacy": "privacy", "components": "extensions", "userscripts": "extensions",
                "downloads": "downloads", "language": "language", "protection": "protection",
                "extensions": "extensions", "updates": "updates", "system": "system",
                "sites": "sites", "blocker": "blocker", "permissions": "permissions",
                "nonsense": "general", "None": "general"}
    for name, page in expected.items():
        assert out["pages"][name][:2] == [True, page], (name, out["pages"][name])
    assert all(out["abouts"]) and len(out["abouts"]) == 14
    assert out["hints"] > 60 and out["hint_lines"] == 0 and out["infos_named"]
    assert out["options_page"] == "newtab" and out["userscripts_window"]


# every setting the Settings window saves, with a value that is not its default
NOT_DEFAULT = {
    "language": "it", "accept_language": "fr-FR,fr", "startup": "newtab", "mail_handler": "system",
    "video_hw": "off", "homepage": "https://example.org/", "tabs_position": "vertical",
    "newtab_tiles": "visited", "blocked_counter": "total", "userscripts_enabled": False,
    "show_menubar": True, "bookmarks_bar": "always", "system_titlebar": False, "vtabs_autohide": True,
    "start_maximized": False, "ui_effects": False, "site_tint": False,
    # (1.1.24: the buttons a user can add start hidden in a profile that did not know them)
    "toolbar_hidden": ["back", "pip", "zoom", "bookmarks", "print", "send", "resources"],
    "default_zoom": 1.25, "search_suggestions": False, "shield_level": "strict", "https_only": False,
    "block_third_party_cookies": False, "strip_tracking_params": False, "trim_referrer": False,
    "send_gpc": False, "webrtc_hide_ip": False, "clear_on_exit": True, "repair_button": False,
    "lookalike_warn": False, "doh": "Quad9", "comp_adblock": False, "comp_consent": False,
    "custom_filters": "##.my-own", "auto_update": False, "video_ad_skip": False, "login_compat": False,
    "lazy_restore": False, "di_media": False, "di_downloads": False, "di_krunner": False,
    "di_kdeconnect": False, "tab_sleep_minutes": 45, "app_updates": "ask", "update_channel": "beta",
    "translate_url": "https://translate.example/?u={url}&l={lang}", "autoplay_block": True,
    "mouse_gestures": True, "smooth_scrolling": False, "perm_block": ["camera", "location"],
    "experimental_extensions": False, "newtab_clock": False, "newtab_weather": False,
    "weather_unit": "fahrenheit", "download_dir": "/tmp/ike-test-downloads", "ask_download_location": False,
    "newtab_bg_fit": "centre", "newtab_bg_veil": 60, "comp_dark": False, "page_watch_on": False,
    "ext_passwords": False, "ext_split": False, "ext_pip": False, "ext_translate": False,
    "ext_containers": False, "ext_resources": False, "ext_command_bar": False, "ext_plasma": False,
    "ext_autoscroll": True, "ext_middleclick": True,
    # 1.1.24 (privacy package)
    "bounce_protect": False, "quiet_permissions": False, "battery_saver": True,
}


def test_apply_keeps_every_setting(run_ike):
    """Settings that are not the defaults are shown and saved again unchanged,
    on every page; with every switch and box turned over each is saved turned over."""
    out = run_ike("""
        NOT_DEFAULT = %r
        def steps(ike, qapp, out):
            yield 500
            import json
            from ike.config import CONFIG_DIR
            dlg = ike.show_settings(ike.windows[0])
            yield 300
            dlg.apply()
            yield 200
            saved = json.loads((CONFIG_DIR / "settings.json").read_text("utf-8"))
            out["kept"] = {k: saved.get(k) for k in NOT_DEFAULT}
            # turn every on / off option over through its own widget
            boxes = {"userscripts_enabled": None, "show_menubar": dlg.menubar, "system_titlebar": dlg.titlebar,
                     "vtabs_autohide": dlg.vauto, "start_maximized": dlg.maximized, "ui_effects": dlg.effects,
                     "site_tint": dlg.site_tint, "search_suggestions": dlg.suggest,
                     "comp_adblock": dlg.comp["comp_adblock"], "auto_update": dlg.auto_update,
                     "login_compat": dlg.login_compat, "lazy_restore": dlg.lazy, "autoplay_block": dlg.autoplay,
                     "mouse_gestures": dlg.gestures, "smooth_scrolling": dlg.smooth,
                     "newtab_clock": dlg.nt_clock, "ask_download_location": dlg.dl_ask,
                     "battery_saver": dlg.battery_saver}
            boxes.update(dlg.checks)
            boxes.update(dlg.di)
            from ike import ikeextensions
            for e in ikeextensions.EXTENSIONS:
                boxes[e.key] = dlg.ext_switch[e.id]
            for key, box in boxes.items():
                box.setChecked(not box.isChecked())
            dlg.apply()
            yield 300
            saved = json.loads((CONFIG_DIR / "settings.json").read_text("utf-8"))
            out["turned"] = {k: saved.get(k) for k in boxes}
            out["weather_page"] = dlg.nt_weather.isChecked()
            dlg.close()
            yield 200
    """ % NOT_DEFAULT, settings=dict(NOT_DEFAULT, last_app_check=4102444800))
    for key, value in NOT_DEFAULT.items():
        assert out["kept"][key] == value, (key, out["kept"][key], value)
    for key, value in out["turned"].items():
        assert value is (not NOT_DEFAULT[key]), (key, value)
    assert out["weather_page"] is True            # the extension's switch and the page's box move together


# ----------------------------------------------------------------------
# the extensions' switches
# ----------------------------------------------------------------------
def test_each_switch_changes_its_setting_and_its_menu_entries(run_ike):
    out = run_ike("""
        def steps(ike, qapp, out):
            yield 600
            import json
            from ike import ikeextensions
            from ike.config import CONFIG_DIR
            win = ike.windows[0]

            def shown(e):
                acts = []
                for name in e.actions:
                    obj = getattr(win, name)
                    act = obj.menuAction() if hasattr(obj, "menuAction") else obj
                    acts.append(act.isVisible() and act.isEnabled())
                keys = set(win.toolbar_layout.shown("left") + win.toolbar_layout.shown("right"))
                # (a button the user hid stays hidden either way: Video in a floating window by default)
                return acts + [k in keys for k in e.toolbar if k not in ike.config["toolbar_hidden"]]

            res = {}
            for e in ikeextensions.EXTENSIONS:
                before = ikeextensions.on(ike.config, e.id)
                act = win.ext_actions[e.id]
                checked = act.isChecked()
                act.trigger()                                  # from the menu
                yield 150
                saved = json.loads((CONFIG_DIR / "settings.json").read_text("utf-8")).get(e.key)
                off = shown(e)
                act_off = act.isChecked()
                act.trigger()
                yield 150
                back = json.loads((CONFIG_DIR / "settings.json").read_text("utf-8")).get(e.key)
                res[e.id] = [before, checked, saved, act_off, off, back, shown(e)]
            out["res"] = res
            # from the Settings: the same setting, and the menu follows
            dlg = win.open_settings("extensions")
            yield 300
            dlg.ext_switch["split"].setChecked(False)
            dlg.ext_switch["autoscroll"].setChecked(True)
            dlg.apply()
            yield 200
            out["settings"] = [ike.config["ext_split"], win.act_split.isVisible(),
                               win.ext_actions["split"].isChecked(), ike.config["ext_autoscroll"],
                               win.ext_actions["autoscroll"].isChecked(),
                               bool(ike.profile.scripts().find("ike-autoscroll"))]
            dlg.close()
            # an extension that is off does nothing when its shortcut's function is called
            n = len(win.views)
            win.toggle_split()
            yield 200
            out["split_off"] = [win.split is None, len(win.views) == n]
            ikeextensions.set_on(ike, "commandbar", False)
            out["bar_off"] = [win.open_command_bar() is None, win.act_command_bar.isEnabled()]
            yield 100
    """, settings={"comp_dark": True})
    for ext_id, (before, checked, saved, act_off, off, back, again) in out["res"].items():
        assert checked is before, ext_id
        assert saved is (not before) and act_off is (not before), ext_id
        assert back is before, ext_id
        if before:                       # on -> off: its entries hidden, then back
            assert not any(off) and all(again), (ext_id, off, again)
        else:
            assert all(off) and not any(again), (ext_id, off, again)
    assert out["settings"] == [False, False, False, True, True, True]
    assert out["split_off"] == [True, True]
    assert out["bar_off"] == [True, False]


def test_dark_mode_switch_off_keeps_pages_light(run_ike, site):
    """"Dark mode for pages" switched off: pages stay light even with dark mode
    chosen, and the dark mode setting itself is kept for when it is on again."""
    out = run_ike(JS + """
PORT = %d
def steps(ike, qapp, out):
    win = ike.windows[0]
    view = win.current_view()
    yield from load(view, "http://127.0.0.1:%%d/plain" %% PORT)
    yield 800
    out["on"] = ike.shields.dark_for("127.0.0.1")
    from ike import ikeextensions
    ikeextensions.set_on(ike, "dark", False)
    yield 800
    out["off"] = [ike.shields.dark_for("127.0.0.1"), ike.config["dark_mode"], win.m_dark.menuAction().isVisible()]
    ikeextensions.set_on(ike, "dark", True)
    yield 300
    out["again"] = [ike.shields.dark_for("127.0.0.1"), win.m_dark.menuAction().isVisible()]
""" % site, settings={"dark_mode": "on"})
    assert out["on"] is True
    assert out["off"] == [False, "on", False]
    assert out["again"] == [True, True]


# ----------------------------------------------------------------------
# the two new extensions, with real mouse events
# ----------------------------------------------------------------------
MOUSE = JS + r'''
from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

PORT = __PORT__
A = "http://127.0.0.1:%d" % PORT

def proxy(view):
    return view.focusProxy() or view

def move(view, pos):
    w = proxy(view)
    QApplication.sendEvent(w, QMouseEvent(QEvent.Type.MouseMove, QPointF(pos), QPointF(w.mapToGlobal(pos)),
                                          Qt.MouseButton.NoButton, Qt.MouseButton.NoButton,
                                          Qt.KeyboardModifier.NoModifier))

def middle(view, pos):
    QTest.mouseClick(proxy(view), Qt.MouseButton.MiddleButton, Qt.KeyboardModifier.NoModifier, pos)

def scroll_y(view):
    return (yield from js(view, "window.scrollY"))
'''

AUTOSCROLL = MOUSE + r'''
def steps(ike, qapp, out):
    win = ike.windows[0]
    win.resize(1000, 700)
    win.show()
    win.activateWindow()
    view = win.current_view()
    yield from load(view, A + "/long")
    yield 500
    start = QPoint(400, 400)                    # the empty part of the page
    middle(view, start)
    yield 100
    for i in range(1, 11):
        move(view, QPoint(400, 400 + i * 20))   # 200 pixels below: scroll down
        yield 30
    yield 800
    out["scrolled"] = yield from scroll_y(view)
    out["mark"] = yield from js(view, "document.documentElement.hasAttribute('data-ike-autoscroll')")
    QTest.keyClick(proxy(view), Qt.Key.Key_Escape)       # Esc stops it
    yield 200
    a = yield from scroll_y(view)
    yield 500
    b = yield from scroll_y(view)
    out["stopped"] = [a == b, (yield from js(view, "document.documentElement.hasAttribute('data-ike-autoscroll')"))]
    # a middle click on a link still opens it in a new tab, and scrolls nothing
    yield from js(view, "window.scrollTo(0, 0); 1")
    yield 200
    n = len(win.views)
    middle(view, QPoint(50, 20))
    yield 1500
    out["link"] = [len(win.views) - n, (yield from scroll_y(view))]
    # a middle click in a text field: no scrolling either
    middle(view, QPoint(100, 90))
    yield 100
    move(view, QPoint(100, 400))
    yield 600
    out["field"] = yield from scroll_y(view)
'''


def test_automatic_scrolling(run_ike, site):
    out = run_ike(AUTOSCROLL.replace("__PORT__", str(site)), settings={"ext_autoscroll": True}, timeout=150)
    assert out["scrolled"] > 50 and out["mark"] is True, out
    assert out["stopped"] == [True, False]
    assert out["link"] == [1, 0]
    assert out["field"] == 0


def test_automatic_scrolling_off_by_default(run_ike, site):
    out = run_ike(AUTOSCROLL.replace("__PORT__", str(site)).replace(
        'out["mark"] = ', 'return\n    out["mark"] = '), timeout=150)
    assert out["scrolled"] == 0


MIDDLECLICK = MOUSE + r'''
def steps(ike, qapp, out):
    from ike import ikeextensions
    win = ike.windows[0]
    win.resize(1000, 700)
    win.show()
    win.activateWindow()
    view = win.current_view()
    selection = {"text": A + "/target?from=selection"}
    ikeextensions.primary_selection = lambda: selection["text"]
    yield from load(view, A + "/long")
    yield 500
    n = len(win.views)
    # on a link: the link's own middle click (a new tab), the selection is not opened
    middle(view, QPoint(50, 20))
    yield 1500
    out["link"] = [len(win.views) - n, view.url().path()]
    # on the empty part of the page: the selection opens in this tab
    middle(view, QPoint(400, 400))
    yield 1500
    out["empty"] = view.url().toString()
    # words: a search with the default engine; code is never run, it is searched for
    yield from load(view, A + "/long")
    selection["text"] = "javascript:document.title='hacked'"
    middle(view, QPoint(400, 400))
    yield 1500
    out["code"] = [view.url().toString(), view.title()]
    yield from load(view, A + "/long")
    selection["text"] = "two   words"
    middle(view, QPoint(400, 400))
    yield 1500
    out["words"] = view.url().toString()
    # in a text field: nothing
    yield from load(view, A + "/long")
    selection["text"] = A + "/target?from=field"
    middle(view, QPoint(100, 90))
    yield 1200
    out["field"] = view.url().path()
'''

SEARCH = {"search_engines": [{"name": "Local", "keyword": "lo", "url": "http://127.0.0.1:__PORT__/search?q={q}",
                              "suggest": ""}],
          "default_engine": "Local", "search_suggestions": False}


def _search(site):
    return json.loads(json.dumps(SEARCH).replace("__PORT__", str(site)))


def test_open_selected_text_with_middle_click(run_ike, site):
    out = run_ike(MIDDLECLICK.replace("__PORT__", str(site)),
                  settings=dict(_search(site), ext_middleclick=True), timeout=150)
    assert out["link"] == [1, "/long"]
    assert out["empty"] == "http://127.0.0.1:%d/target?from=selection" % site
    assert out["code"][0].startswith("http://127.0.0.1:%d/search?q=javascript" % site), out["code"]
    assert out["code"][1] != "hacked"
    assert out["words"] == "http://127.0.0.1:%d/search?q=two words" % site, out["words"]
    assert out["field"] == "/long"


def test_middle_click_opens_nothing_by_default(run_ike, site):
    out = run_ike(MIDDLECLICK.replace("__PORT__", str(site)), settings=_search(site), timeout=150)
    assert out["link"] == [1, "/long"]
    assert out["empty"] == "http://127.0.0.1:%d/long" % site
