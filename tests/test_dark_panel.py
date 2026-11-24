"""The panel of the toolbar's Dark mode button (1.1.25): ike/darkpanel.py, ike/darktheme.py.

- the colours kept in the settings: Dark Reader's own keys and defaults, the
  settings of earlier versions completed, every value checked (ranges,
  #rrggbb colours, a font only from the computer's, the hosts), whatever the
  settings file holds;
- what the pages are given: every site's colours, a site's own (darkpages.py),
  and the colours changed while a page is open, taken at once without loading
  it again, and only in the isolated world (the page itself cannot reach it);
- the panel in the real browser: it opens under its button, its switches and
  sliders change the settings, a slider moved shows on the page of the tab
  (without a reload), let go every open page gets the colours; "Only for this
  site"; Chromium's own dark mode greys what does not work with it; with no
  web page the switches of the site are off; its last button opens I.K.E.'s
  own Settings; the panel holds no address outside I.K.E.
All on this computer.
"""

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from test_security import JS

ROOT = Path(__file__).resolve().parent.parent


# --- the values ------------------------------------------------------------------

def test_the_defaults_are_dark_readers_own():
    """Every key of Dark Reader's theme that the panel sets, with the default the
    engine shipped with I.K.E. has (its scroll bars: the extension's own default on
    Linux, "auto"; its font: the one it names on Linux)."""
    from ike import darktheme
    from ike.config import DEFAULTS
    engine = (ROOT / "ike/resources/darkreader.js").read_text("utf-8")
    block = engine[engine.index("const DEFAULT_THEME = {"):]
    block = block[:block.index("};")]
    colours = engine[engine.index("const DEFAULT_COLORS = {"):]
    colours = colours[:colours.index("};")]
    found = re.findall(r'"(#[0-9a-f]{6})"', colours)
    assert found == ["#181a1b", "#e8e6e3", "#dcdad7", "#181a1b"], found
    d = darktheme.DEFAULTS
    for key, value in (("mode", 1), ("brightness", 100), ("contrast", 100), ("grayscale", 0), ("sepia", 0),
                       ("useFont", "false"), ("textStroke", 0), ("selectionColor", '"auto"')):
        assert re.search(r"\b%s: %s," % (key, value), block), key
        want = {"false": False, '"auto"': "auto"}.get(value, value)
        assert d[key] == want, key
    assert '"Open Sans"' in block and d["fontFamily"] == "Open Sans"
    assert (d["darkSchemeBackgroundColor"], d["darkSchemeTextColor"], d["lightSchemeBackgroundColor"],
            d["lightSchemeTextColor"]) == tuple(found)
    assert d["scrollbarColor"] == "auto"
    assert DEFAULTS["dark_theme"] == d and DEFAULTS["dark_site_themes"] == {}
    assert set(d) - {"mode", "brightness", "contrast", "sepia", "grayscale", "useFont", "fontFamily",
                     "textStroke", "scrollbarColor", "selectionColor"} == set(darktheme.COLOURS)


def test_the_settings_of_earlier_versions_are_completed(tmp_path):
    """1.1.24 kept three values: they stay, the rest is Dark Reader's default; a
    damaged entry, or values out of range, never stop the browser."""
    from ike import darktheme
    from ike.config import Config
    f = tmp_path / "settings.json"
    f.write_text(json.dumps({"dark_theme": {"brightness": 120, "contrast": 90, "sepia": 10}}), "utf-8")
    c = Config(f)
    assert c["dark_theme"] == dict(darktheme.DEFAULTS, brightness=120, contrast=90, sepia=10)
    assert c["dark_site_themes"] == {}
    f.write_text(json.dumps({"dark_theme": "dark", "dark_site_themes": ["x"]}), "utf-8")
    c = Config(f)
    assert c["dark_theme"] == darktheme.DEFAULTS and c["dark_site_themes"] == {}
    f.write_text(json.dumps({
        "dark_theme": {"brightness": 9999, "contrast": -4, "sepia": "50", "grayscale": float("nan"),
                       "mode": True, "useFont": 1, "fontFamily": "x;}body{display:none", "textStroke": 0.4,
                       "darkSchemeBackgroundColor": "red", "darkSchemeTextColor": "#ABCDEF",
                       "scrollbarColor": "url(https://example.com/x)", "selectionColor": "#123",
                       "stylesheet": "body{}", "engine": "cssFilter"},
        "dark_site_themes": {"example.org": {"mode": 0, "sepia": 30}, "EVIL host": {"mode": 0},
                             "bad.example": "x", "x.example": {"brightness": 70}}}), "utf-8")
    c = Config(f)
    t = c["dark_theme"]
    assert set(t) == set(darktheme.DEFAULTS)                       # nothing else reaches Dark Reader
    assert (t["brightness"], t["contrast"], t["sepia"], t["grayscale"]) == (150, 50, 0, 0)
    assert t["mode"] == 1 and t["useFont"] is False and t["fontFamily"] == "Open Sans"
    assert t["textStroke"] == 0 and t["darkSchemeBackgroundColor"] == "#181a1b"
    assert t["darkSchemeTextColor"] == "#abcdef"
    assert t["scrollbarColor"] == "auto" and t["selectionColor"] == "auto"
    assert sorted(c["dark_site_themes"]) == ["example.org", "x.example"]
    assert c["dark_site_themes"]["example.org"] == dict(darktheme.DEFAULTS, mode=0, sepia=30)
    c.save()
    assert json.loads(f.read_text("utf-8"))["dark_theme"] == t


def test_every_value_is_checked():
    from ike import darktheme as d
    assert d.clean({"brightness": 49.6})["brightness"] == 50
    assert d.clean({"sepia": 33.4})["sepia"] == 33
    assert [d.clean({"textStroke": s})["textStroke"] for s in (0, 0.3, 0.5, 1, 0.31, 2, True)] == \
        [0, 0.3, 0.5, 1, 0, 0, 0]
    assert d.clean({"scrollbarColor": "hidden"})["scrollbarColor"] == "hidden"
    assert d.clean({"scrollbarColor": "#3DAEE9"})["scrollbarColor"] == "#3daee9"
    assert d.clean({"selectionColor": "hidden"})["selectionColor"] == "auto"
    for bad in ("#12345", "#1234567", "rgb(1,2,3)", "#gggggg", " #123456;x", None, 5):
        assert d.colour(bad) is None, bad
    for name in ("Noto Sans", "DejaVu Sans Mono", "Noto Sans CJK JP", "Source Code Pro", "Ubuntu"):
        assert d.font_name_ok(name), name
    for name in ('Noto"Sans', "a;b", "a}b", "a{b", "x/*", "a\\b", "a\nb", "", " lead", "x" * 65,
                 "a<b", "a'b"):
        assert not d.font_name_ok(name), name
    assert d.host_ok("example.org") and d.host_ok("127.0.0.1") and d.host_ok("xn--bcher-kva.example")
    for host in ("", "Example.org", "a b", "a/b", "a..b", "-a.org", "x" * 300):
        assert not d.host_ok(host), host
    many = {"s%d.example" % i: {} for i in range(d.SITES_MAX + 10)}
    assert len(d.clean_sites(many)) == d.SITES_MAX


def test_what_a_page_is_given():
    """The font only when it is one of the computer's, quoted; the theme is the
    site's own when it has one."""
    from ike import darktheme as d
    fonts = ["Noto Sans", "DejaVu Serif"]
    t = d.for_page({"useFont": True, "fontFamily": "DejaVu Serif"}, fonts=fonts)
    assert t["useFont"] is True and t["fontFamily"] == '"DejaVu Serif"'
    t = d.for_page({"useFont": True, "fontFamily": "Comic Neue"}, fonts=fonts)
    assert t["useFont"] is False and t["fontFamily"] == '"Open Sans"'
    cfg = {"dark_theme": {"brightness": 80}, "dark_site_themes": {"example.org": {"brightness": 130}}}
    assert d.of(cfg, "example.org") == (dict(d.DEFAULTS, brightness=130), True)
    assert d.of(cfg, "www.example.org") == (dict(d.DEFAULTS, brightness=80), False)
    assert d.of(cfg, "") == (dict(d.DEFAULTS, brightness=80), False)


class _Scripts:
    def __init__(self):
        self.items = []

    def toList(self):
        return list(self.items)

    def insert(self, s):
        self.items.append(s)

    def remove(self, s):
        self.items.remove(s)


class _Profile:
    def __init__(self):
        self._s = _Scripts()

    def scripts(self):
        return self._s


def test_the_scripts_of_a_profile_carry_the_colours():
    """darkpages: every site's colours in the engine, a site's own in its small
    script; retheme() gives the pages loaded from now on the changed colours,
    without taking away the sites already registered."""
    from ike import darkpages, darktheme
    p = _Profile()
    glob = darktheme.for_page({"brightness": 80}, fonts=[])
    own = darktheme.for_page({"brightness": 130, "mode": 0}, fonts=[])
    assert darkpages.prepare(p, "https://a.example/", "a.example", glob, True, True, None)
    assert darkpages.prepare(p, "https://b.example/", "b.example", glob, True, True, own)
    names = {s.name(): s.sourceCode() for s in p.scripts().toList()}
    assert set(names) == {"ike-dark-proxy", "ike-dark-engine", "ike-dark-site:a.example", "ike-dark-site:b.example"}
    assert json.dumps(glob) in names["ike-dark-engine"]
    assert '"theme"' not in names["ike-dark-site:a.example"]
    assert json.dumps(own) in names["ike-dark-site:b.example"]
    newer = darktheme.for_page({"brightness": 60, "sepia": 40}, fonts=[])
    darkpages.retheme(p, newer, lambda h: own if h == "a.example" else None)
    names = {s.name(): s.sourceCode() for s in p.scripts().toList()}
    assert set(names) == {"ike-dark-proxy", "ike-dark-engine", "ike-dark-site:a.example", "ike-dark-site:b.example"}
    assert json.dumps(newer) in names["ike-dark-engine"] and json.dumps(glob) not in names["ike-dark-engine"]
    assert json.dumps(own) in names["ike-dark-site:a.example"]
    assert '"theme"' not in names["ike-dark-site:b.example"]
    # the next page with the same colours: nothing is installed again
    before = list(p.scripts().toList())
    assert darkpages.prepare(p, "https://b.example/x", "b.example", newer, True, True, None)
    assert p.scripts().toList() == before
    darkpages.forget(p)
    assert p.scripts().toList() == []
    darkpages.retheme(p, newer, lambda h: None)          # nothing dark: nothing installed
    assert p.scripts().toList() == []


def test_the_panel_has_no_address_outside_ike():
    """No link, page or service outside I.K.E. in the panel (no Dark Reader news,
    donations or social sites): its only way out is I.K.E.'s own Settings."""
    for name in ("ike/darkpanel.py", "ike/darktheme.py"):
        text = (ROOT / name).read_text("utf-8")
        assert not re.search(r"https?:|www\.|ftp:|mailto:|\.(com|org|net|io)\b", text), name
        assert "QDesktopServices" not in text and "openUrl" not in text and "QUrl" not in text, name


# --- in the browser ------------------------------------------------------------------

PAGE = ("<!doctype html><html><head><title>light</title><style>body{background:#fff;color:#111}"
        "main{height:3000px}</style></head><body><main><h1>Light</h1><p>Text.</p></main></body></html>")


@pytest.fixture
def site():
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            data = PAGE.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):
            pass
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield "http://127.0.0.1:%d" % srv.server_address[1]
    srv.shutdown()


STEPS = JS + r'''
SITE = "__SITE__"
READ = """JSON.stringify({bg: getComputedStyle(document.body).backgroundColor,
  marker: window.__ikeMarker || null, bars: !!document.querySelector('style.darkreader--ike-bars'),
  dr: document.querySelectorAll('style.darkreader').length})"""

def lum(css):
    import re
    m = re.match(r"rgba?\((\d+), (\d+), (\d+)", css or "")
    return round(sum(w * int(x) for w, x in zip((0.2126, 0.7152, 0.0722), m.groups())), 1) if m else None

def steps(ike, qapp, out):
    from PyQt6.QtCore import QPoint, Qt
    from PyQt6.QtTest import QTest
    from PyQt6.QtWebEngineCore import QWebEngineScript
    win = ike.windows[0]
    win.resize(1300, 800)
    ike.config["toolbar_hidden"] = [k for k in ike.config["toolbar_hidden"] if k != "dark"]
    win._apply_toolbar()
    yield 300
    # with no web page: the site's switches are off
    btn = win.nav.widgetForAction(win.act_dark)
    QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
    yield 400
    menu, panel = win.dark_menu, win.dark_panel
    out["newtab"] = [menu.isVisible(), panel.site.isEnabled(), panel.only_site.isEnabled(),
                     panel.master.isChecked()]
    g, b = menu.geometry(), btn.mapToGlobal(QPoint(0, 0))
    out["place"] = [g.top() - (b.y() + btn.height()), (g.right() + 1) - (b.x() + btn.width()), g.width(),
                    g.left() - b.x()]
    texts = []
    from PyQt6.QtWidgets import QAbstractButton, QComboBox, QLabel, QWidget
    for w in [panel] + panel.findChildren(QWidget):
        texts.append(w.toolTip() + " " + w.accessibleName() + " " + w.statusTip() + " " + w.whatsThis())
        if isinstance(w, (QLabel, QAbstractButton)):
            texts.append(w.text())
        if isinstance(w, QComboBox):
            texts += [w.itemText(i) for i in range(w.count())]
    out["texts"] = texts
    out["focus"] = [w.focusPolicy() != Qt.FocusPolicy.NoFocus for w in
                    (panel.master, panel.site, panel.mode, panel.reset, panel.more_btn, panel.settings)
                    + tuple(panel.sliders.values())]
    out["buddies"] = [panel.slider_labels[k].buddy() is panel.sliders[k] for k in panel.sliders]
    menu.hide()
    yield 400
    # a page made dark
    view = win.current_view()
    yield from load(view, SITE + "/one")
    yield 2500
    first = json.loads((yield from js(view, READ)))
    yield from js(view, "window.__ikeMarker = 'kept'")
    out["first"] = first
    out["main_world"] = (yield from js(view, "typeof window.__ikeDarkTheme"))
    QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
    yield 400
    out["site"] = [panel.site.isEnabled(), panel.site.isChecked(), panel.site_label.text(),
                   panel.master.isChecked(), panel.only_site.isEnabled(), panel.note.isVisible(),
                   panel.sliders["brightness"].isEnabled(), panel.mode.isEnabled()]
    # a slider moved: the page shows it at once, not loaded again, nothing kept yet
    s = panel.sliders["brightness"]
    s.setSliderDown(True)
    s.setValue(50)
    yield 600
    live = json.loads((yield from js(view, READ)))
    out["live"] = [live["marker"], lum(first["bg"]), lum(live["bg"]), ike.config["dark_theme"]["brightness"],
                   panel.values["brightness"].text()]
    saved = json.loads(open(ike.config.path, encoding="utf-8").read()).get("dark_theme", {}).get("brightness")
    s.setSliderDown(False)            # let go: kept, every page
    yield 300
    saved_after = json.loads(open(ike.config.path, encoding="utf-8").read())["dark_theme"]["brightness"]
    out["kept"] = [saved, saved_after]
    eng = [x.sourceCode() for x in view.page().profile().scripts().toList() if x.name() == "ike-dark-engine"]
    out["engine_has"] = bool(eng) and '"brightness": 50' in eng[0]
    # the keys move it too, and it is kept after a moment
    s.setFocus()
    QTest.keyClick(s, Qt.Key.Key_Right)
    yield 900
    out["key"] = [ike.config["dark_theme"]["brightness"],
                  json.loads(open(ike.config.path, encoding="utf-8").read())["dark_theme"]["brightness"]]
    # Reset
    panel.reset.click()
    yield 500
    back = json.loads((yield from js(view, READ)))
    out["reset"] = [ike.config["dark_theme"]["brightness"], s.value(), lum(back["bg"]), back["marker"]]
    # More: hidden scroll bars, the light mode, this site only
    panel.more_btn.click()
    yield 300
    out["more"] = [panel.more.isVisible(), panel.font_combo.count() > 0,
                   menu.geometry().bottom() <= menu.screen().availableGeometry().bottom() + 1]
    # the owner: everything aligned. One left edge for every label, the arrow of More and the
    # last button; one right edge for the switches, the choice, the values, Reset and the fields;
    # each label centred on its control's row
    from PyQt6.QtCore import QPoint as _P
    def box(w):
        o = w.mapTo(panel, _P(0, 0))
        return [o.x(), o.y(), o.x() + w.width(), o.y() + w.height()]
    rows = [(panel.title, panel.master), (panel.site_label, panel.site)]
    rows += [(panel.slider_labels[k], panel.sliders[k]) for k in panel.sliders]
    rows += [(panel.slider_labels[k], panel.values[k]) for k in panel.sliders]
    rows += list(zip(panel.more_labels, [panel.font_switch, panel.stroke, panel.bg, panel.fg, panel.bars,
                                        panel.selection]))
    out["centres"] = [((box(b)[1] + box(b)[3]) - (box(a)[1] + box(a)[3])) / 2 for a, b in rows]
    out["lefts"] = sorted({box(w)[0] for w in [panel.site_label, panel.head_icon, panel.more_btn, panel.settings,
                                                panel.only_site] + list(panel.slider_labels.values())
                           + panel.more_labels})
    out["rights"] = sorted({box(w)[2] for w in [panel.master, panel.site, panel.mode, panel.reset, panel.font_combo,
                                                 panel.stroke, panel.bg, panel.fg, panel.bars, panel.selection]
                            + list(panel.values.values())})
    out["values_right"] = all(v.alignment() & Qt.AlignmentFlag.AlignRight for v in panel.values.values())
    panel.bars.setCurrentIndex(panel.bars.findData("hidden"))
    panel.bars.activated.emit(panel.bars.currentIndex())
    yield 500
    out["bars"] = [ike.config["dark_theme"]["scrollbarColor"], json.loads((yield from js(view, READ)))["bars"]]
    panel.bars.setCurrentIndex(panel.bars.findData("auto"))
    panel.bars.activated.emit(panel.bars.currentIndex())
    yield 400
    out["bars_back"] = json.loads((yield from js(view, READ)))["bars"]
    panel.mode.setCurrent(1, emit=True)
    yield 500
    light = json.loads((yield from js(view, READ)))
    out["light"] = [ike.config["dark_theme"]["mode"], panel.bg.text(), panel.fg.text(), lum(light["bg"]),
                    light["marker"]]
    panel.mode.setCurrent(0, emit=True)
    yield 300
    panel.only_site.click()
    yield 300
    host = "127.0.0.1"
    out["own"] = [host in ike.config["dark_site_themes"], panel.only_site.isChecked()]
    panel.sliders["sepia"].setValue(40)
    yield 900
    out["own_values"] = [ike.config["dark_site_themes"][host]["sepia"], ike.config["dark_theme"]["sepia"]]
    sites = [x.sourceCode() for x in view.page().profile().scripts().toList()
             if x.name() == "ike-dark-site:" + host]
    out["site_script"] = bool(sites) and '"sepia": 40' in sites[0] and '"theme"' in sites[0]
    panel.only_site.click()
    yield 400
    out["own_off"] = [host in ike.config["dark_site_themes"], panel.sliders["sepia"].value()]
    # the switches: this site, then every site
    panel.site.click()
    yield 1500
    out["site_off"] = [ike.config["dark_exclude"], ike.shields.dark_for(host)]
    panel.site.click()
    yield 1500
    panel.master.click()
    yield 300
    out["master_off"] = ike.config["dark_mode"]
    panel.master.click()
    yield 300
    out["master_on"] = ike.config["dark_mode"]
    menu.hide()
    yield 300
    # Chromium's own dark mode: what works only with Dark Reader is greyed, with a note
    ike.config["dark_engine"] = "engine"
    win.show_dark_panel()
    yield 400
    out["engine"] = [panel.note.isVisible(), panel.note.text(), panel.mode.isEnabled(), panel.reset.isEnabled(),
                     panel.more_btn.isEnabled(), panel.more.isEnabled(),
                     any(x.isEnabled() for x in panel.sliders.values()),
                     panel.master.isEnabled(), panel.site.isEnabled(), panel.settings.isEnabled()]
    ike.config["dark_engine"] = "reader"
    # the last button: I.K.E.'s own Settings, at the dark mode of pages
    panel.settings.click()
    yield 800
    dlg = ike._dialogs.get("settings")
    out["settings"] = [menu.isVisible(), dlg is not None and dlg.isVisible(),
                       dlg is not None and dlg.PAGES[dlg.nav.currentRow()],
                       dlg is not None and dlg.dark.hasFocus()]
    if dlg is not None:
        dlg.close()
'''


def test_the_panel_in_the_browser(run_ike, site):
    from ike.i18n import T
    out = run_ike(STEPS.replace("__SITE__", site), settings={"dark_mode": "on", "dark_engine": "reader"},
                  timeout=200)
    assert out["newtab"] == [True, False, False, True], out["newtab"]
    top, right, width, left = out["place"]
    # under the button, its right edge at the button's (on the left of the toolbar: its left edge)
    assert 0 <= top <= 4 and (abs(right) <= 8 or abs(left) <= 8) and width >= 340, out["place"]
    texts = " ".join(out["texts"])
    assert not re.search(r"https?:|www\.|://", texts), texts
    assert all(out["focus"]) and all(out["buddies"]), (out["focus"], out["buddies"])
    first = out["first"]
    assert first["dr"] > 0 and first["marker"] is None, first
    assert out["main_world"] == "undefined"                  # the page cannot reach the colours
    assert out["site"] == [True, True, "This site: 127.0.0.1", True, True, False, True, True], out["site"]
    marker, before, during, kept, label = out["live"]
    assert marker == "kept", out["live"]                     # not loaded again
    assert during < before, out["live"]                      # darker at once
    assert kept == 50 and label == "50%", out["live"]
    assert out["kept"][0] in (None, 100) and out["kept"][1] == 50, out["kept"]   # kept when let go, not while moved
    assert out["engine_has"] is True
    assert out["key"] == [51, 51], out["key"]
    assert out["reset"][:2] == [100, 100] and out["reset"][3] == "kept", out["reset"]
    assert abs(out["reset"][2] - before) < 3, (out["reset"], before)
    assert out["more"] == [True, True, True], out["more"]
    assert all(abs(c) <= 1 for c in out["centres"]), out["centres"]
    assert len(out["lefts"]) == 1 and len(out["rights"]) == 1 and out["values_right"], (out["lefts"], out["rights"])
    assert out["bars"] == ["hidden", True] and out["bars_back"] is False, (out["bars"], out["bars_back"])
    mode, bg, fg, light, marker = out["light"]
    assert mode == 0 and (bg, fg) == ("#dcdad7", "#181a1b") and marker == "kept", out["light"]
    assert light > before + 60, (light, before)              # Dark Reader's light colours
    assert out["own"] == [True, True], out["own"]
    assert out["own_values"] == [40, 0], out["own_values"]   # the site's own; every site's untouched
    assert out["site_script"] is True
    assert out["own_off"] == [False, 0], out["own_off"]
    assert out["site_off"] == [["127.0.0.1"], False], out["site_off"]
    assert out["master_off"] == "off" and out["master_on"] == "on"
    note = out["engine"]
    assert note[0] is True and note[1] == T("The sliders work with Dark Reader"), note
    assert note[2:7] == [False, False, False, False, False], note
    assert note[7:] == [True, True, True], note
    assert out["settings"] == [False, True, "appearance", True], out["settings"]


TWO_TABS = JS + r'''
SITE = "__SITE__"
def steps(ike, qapp, out):
    win = ike.windows[0]
    a = win.current_view()
    yield from load(a, SITE + "/a")
    b = win.add_tab(SITE + "/b", background=True)
    yield 2500
    win.set_current(a)
    for v in (a, b):
        yield from js(v, "window.__ikeMarker = 'kept'")
    read = "JSON.stringify([getComputedStyle(document.body).backgroundColor, window.__ikeMarker || null])"
    before = json.loads((yield from js(b, read)))
    win.show_dark_panel()
    yield 300
    panel = win.dark_panel
    s = panel.sliders["contrast"]
    s.setSliderDown(True)
    s.setValue(60)
    yield 600
    out["during"] = json.loads((yield from js(b, read)))       # the other tab: not yet
    s.setSliderDown(False)
    yield 600
    out["after"] = json.loads((yield from js(b, read)))        # let go: the other tab too
    out["before"] = before
    win.dark_menu.hide()
'''


def test_the_other_tabs_get_the_colours_when_the_slider_is_let_go(run_ike, site):
    out = run_ike(TWO_TABS.replace("__SITE__", site), settings={"dark_mode": "on", "dark_engine": "reader",
                                                                "dark_theme": {"contrast": 150}}, timeout=150)
    assert out["before"][1] == "kept"
    assert out["during"] == out["before"], out
    assert out["after"][1] == "kept" and out["after"][0] != out["before"][0], out
