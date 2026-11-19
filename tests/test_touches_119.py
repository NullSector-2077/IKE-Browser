"""1.1.9 graphic touches (polish.py), with real mouse moves, clicks and pages:
the round hover of the toolbar buttons, the bookmark star's pop, the shield
fading between levels, the dot on a background tab that finished loading, a
closed vertical tab fading out, the shield panel's bars growing, the tiles of
the new tab page coming in. Without effects every one of them stays still."""

import http.server
import threading

import pytest

COMMON = r'''
import json
from PyQt6.QtCore import QPoint, Qt, QUrl
from PyQt6.QtGui import QColor
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QToolButton

SITE = "__SITE__"

def load(view, url):
    done = {}
    view.page().loadFinished.connect(lambda ok, d=done: d.setdefault("ok", ok))
    view.load(QUrl(url))
    for _ in range(200):
        if "ok" in done:
            break
        yield 25
    yield 300

def js(view, code):
    res = {}
    view.page().runJavaScript(code, 0, lambda v: res.setdefault("v", v))
    for _ in range(100):
        if "v" in res:
            break
        yield 20
    return res.get("v")

def tinted(widget, accent):
    """How many pixels of the widget lean to the accent colour."""
    img = widget.grab().toImage()
    n = 0
    for x in range(0, img.width(), 2):
        for y in range(0, img.height(), 2):
            c = QColor(img.pixel(x, y))
            if abs(c.hue() - accent.hue()) < 25 and c.saturation() > 25:
                n += 1
    return n

def button_of(win, action):
    return win.nav.widgetForAction(action)
'''

STEPS = COMMON + r'''
def steps(ike, qapp, out):
    win = ike.windows[0]
    win.resize(1400, 860)
    win.show()
    view = win.current_view()
    yield from load(view, SITE + "/page")
    acc = win.palette().color(win.palette().ColorRole.Highlight)

    # --- the round hover of a toolbar button, with the real mouse (a button on the left:
    # the test screen of the offscreen platform is 800 px wide, the mouse goes no further)
    h = button_of(win, win.act_tb_private)
    out["styled"] = type(h.style()).__name__
    QTest.mouseMove(win, QPoint(5, win.height() - 5))
    yield 300
    before = tinted(h, acc)
    QTest.mouseMove(h, h.rect().center())
    yield 60
    mid = float(h.property("ike_hover") or 0)
    yield 300
    out["hover"] = [before, mid, float(h.property("ike_hover") or 0), tinted(h, acc)]
    # 1.1.16: a rectangle with soft corners, not a circle: near the corner it is tinted too
    img = h.grab().toImage()
    k = img.width() / max(1, h.width())
    near = QColor(img.pixel(int(5 * k), int(img.height() / 2)))
    corner = QColor(img.pixel(int(6 * k), int(6 * k)))
    out["shape"] = [abs(near.hue() - acc.hue()) < 25 and near.saturation() > 25,
                    abs(corner.hue() - acc.hue()) < 25 and corner.saturation() > 25]
    QTest.mouseMove(win, QPoint(5, win.height() - 5))
    yield 400
    out["hover_gone"] = float(h.property("ike_hover") or 0)
    b = button_of(win, win.act_tb_bookmark)
    out["own_hover_untouched"] = all(not w.property("ike_hover") for w in win.nav.findChildren(QToolButton)
                                     if w.property("ike_own_hover"))

    # --- the bookmark star: a click, a pop, then the filled star
    QTest.mouseClick(b, Qt.MouseButton.LeftButton)
    yield 60
    out["star_popping"] = bool(win.__dict__.get("_ike_pops", {}).get("star"))
    yield 600
    out["star_after"] = [ike.storage.is_bookmarked(view.url().toString()),
                         not bool(win.__dict__.get("_ike_pops", {}).get("star")),
                         win.act_tb_bookmark.toolTip()]

    # --- the shield fades from one level to the next
    old = ike.config["shield_level"]
    target = [a for a in win.level_group.actions() if a.data() and a.data() != old][0]
    target.trigger()
    yield 60
    fades = win.__dict__.get("_ike_icon_fades", {})
    out["shield_fading"] = "shield" in fades
    yield 500
    out["shield_done"] = ["shield" not in win.__dict__.get("_ike_icon_fades", {}), win._shield_shown]
    ike.config["shield_level"] = old
    ike.settings_changed()
    yield 500

    # --- a background tab that finished loading gets a dot until it is opened
    bg = win.add_tab(SITE + "/other", background=True)
    for _ in range(80):
        if not getattr(bg, "loading", True) and bg.url().toString().endswith("/other"):
            break
        yield 50
    yield 400
    i = win.views.index(bg)
    out["unseen"] = [getattr(bg, "unseen", False)]
    QTest.mouseClick(win.tabbar, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     win.tabbar.tabRect(i).center())
    yield 400
    out["seen"] = [win.current_view() is bg, getattr(bg, "unseen", False)]
    # the tab that is in view while it loads never gets the dot
    yield from load(bg, SITE + "/page")
    out["current_no_dot"] = getattr(bg, "unseen", False)

    # --- the shield panel's bars grow from zero
    yield from load(view, SITE + "/ads")
    yield 600
    win.set_current(view)
    yield 300
    # the shield's number appeared: the address bar was placed again at once (before 1.1.9 it
    # stayed where it was until something else moved it)
    where = lambda: [win.urlbar.mapTo(win, QPoint(0, 0)).x(), win.urlbar.width()]
    settled = where()
    win._fit_urlbar()
    yield 200
    out["centred"] = [settled, where(), win.shield_btn.text()]
    win.shield_menu.popup(win.shield_btn.mapToGlobal(win.shield_btn.rect().bottomLeft()))
    yield 40
    k0 = win.shield_panel.kinds.k
    yield 600
    out["bars"] = [win.shield_panel.kinds.isVisible(), k0 < 0.6, win.shield_panel.kinds.k]
    win.shield_menu.hide()
    yield 200

    # --- the new tab page: the tiles come in one after the other
    ike.storage.add_bookmark("https://one.example/", "One")
    ike.storage.add_bookmark("https://two.example/", "Two")
    nt = win.add_tab()
    yield 1500
    out["tiles"] = json.loads((yield from js(nt, "JSON.stringify(Array.from(document.querySelectorAll('.tile'))"
                                              ".slice(0, 3).map(function (t) { var s = getComputedStyle(t); "
                                              "return [s.animationName, s.animationDelay]; }))")))
'''

VERTICAL = COMMON + r'''
def steps(ike, qapp, out):
    win = ike.windows[0]
    win.resize(1400, 860)
    win.show()
    yield from load(win.current_view(), SITE + "/page")
    second = win.add_tab(SITE + "/other")
    yield 1200
    third = win.add_tab(SITE + "/page")
    yield 1200
    out["vertical"] = win.vtabs.isVisible()
    # close the middle row
    i = win.views.index(second)
    rect = win.vtabs.visualItemRect(win.vtabs.item(i))
    win.close_tab(second)
    yield 40
    from PyQt6.QtWidgets import QLabel
    ghosts = win.vtabs.viewport().findChildren(QLabel, "ike_row_ghost")
    out["ghost"] = [len(ghosts), ghosts[0].geometry().top() == rect.top() if ghosts else None]
    yield 400
    out["ghost_gone"] = len(win.vtabs.viewport().findChildren(QLabel, "ike_row_ghost"))
    out["rows"] = win.vtabs.count()
'''

STILL = COMMON + r'''
def steps(ike, qapp, out):
    win = ike.windows[0]
    win.resize(1400, 860)
    win.show()
    view = win.current_view()
    yield from load(view, SITE + "/page")
    h = button_of(win, win.act_tb_private)
    QTest.mouseMove(h, h.rect().center())
    yield 30
    out["hover_at_once"] = float(h.property("ike_hover") or 0)
    b = button_of(win, win.act_tb_bookmark)
    QTest.mouseClick(b, Qt.MouseButton.LeftButton)
    yield 30
    out["no_pop"] = not win.__dict__.get("_ike_pops", {}).get("star")
    old = ike.config["shield_level"]
    [a for a in win.level_group.actions() if a.data() and a.data() != old][0].trigger()
    yield 30
    out["no_shield_fade"] = "shield" not in win.__dict__.get("_ike_icon_fades", {})
    nt = win.add_tab()
    yield 1500
    out["tiles"] = (yield from js(nt, "var t = document.querySelector('.tile'); t ? getComputedStyle(t).animationName : 'none'"))
'''


@pytest.fixture
def site():
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            pages = {"/page": b"<!doctype html><title>A page</title><p>text</p>",
                     "/other": b"<!doctype html><title>Other page</title><p>more text</p>",
                     "/ads": b"<!doctype html><title>Ads</title><img src='http://ads.example.test/a.png'>"
                             b"<img src='http://ads.example.test/b.png'>"}
            body = pages.get(self.path, b"<title>x</title>")
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield "http://127.0.0.1:%d" % srv.server_address[1]
    srv.shutdown()


def test_touches_of_119(run_ike, site):
    out = run_ike(STEPS.replace("__SITE__", site), env={"IKE_REDUCED_MOTION": "0"}, timeout=150)
    assert out["styled"] == "RoundHoverStyle"
    before, mid, end, after = out["hover"]
    assert 0 < mid < 1 and end == 1.0 and after > before, out["hover"]   # it glides in, round and accent-coloured
    assert out["hover_gone"] == 0.0 and out["own_hover_untouched"]
    assert out["shape"] == [True, True], out["shape"]          # flat sides, rounded corners (1.1.16)
    assert out["star_popping"]
    assert out["star_after"][0] and out["star_after"][1] and out["star_after"][2] == "Remove bookmark"
    assert out["shield_fading"] and out["shield_done"][0]
    assert out["unseen"][0] is True
    assert out["seen"] == [True, False] and out["current_no_dot"] is False
    # (before 1.1.9 the bar stayed 8 px off; the toolbar's own layout may still move it a few px)
    assert out["centred"][2] and abs(out["centred"][0][0] - out["centred"][1][0]) <= 4
    visible, started_low, k = out["bars"]
    assert visible and started_low and k == 1.0
    names = [n for n, _d in out["tiles"]]
    assert names and all(n == "ike-tile-in" for n in names)
    delays = [d for _n, d in out["tiles"]]
    assert delays[0] in ("0s", "0ms") and delays[1] != delays[0]   # one after the other


def test_closed_vertical_tab_fades_out(run_ike, site):
    out = run_ike(VERTICAL.replace("__SITE__", site), settings={"tabs_position": "vertical"},
                  env={"IKE_REDUCED_MOTION": "0"}, timeout=120)
    assert out["vertical"]
    assert out["ghost"] == [1, True]
    assert out["ghost_gone"] == 0 and out["rows"] == 2


@pytest.mark.parametrize("mode", ["setting-off", "reduced-motion"])
def test_touches_of_119_stay_still_without_effects(run_ike, site, mode):
    out = run_ike(STILL.replace("__SITE__", site), settings={"ui_effects": mode != "setting-off"},
                  env={"IKE_REDUCED_MOTION": "1" if mode == "reduced-motion" else "0"}, timeout=120)
    assert out["hover_at_once"] in (0.0, 1.0)              # no glide: at once
    assert out["no_pop"] and out["no_shield_fade"]
    assert out["tiles"] == "none"
