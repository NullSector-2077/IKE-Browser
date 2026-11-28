"""1.1.31, the owner's small graphic touches: the page mode's sun turns into the moon (and back)."""

from test_security import JS

MORPH = JS + r'''
def steps(ike, qapp, out):
    from PyQt6.QtCore import QUrl
    from ike import polish
    win = ike.windows[0]
    view = win.current_view()
    view.setHtml("<p>hi</p>", QUrl("https://site.example/"))
    yield 800
    dark = {"on": False}
    ike.shields.dark_for = lambda host: dark["on"]
    win.sync_dark_icon()
    first = win.act_dark.icon().cacheKey()
    dark["on"] = True
    win.sync_dark_icon()
    anim = win.__dict__.get("_ike_icon_fades", {}).get("dark")
    out["running"] = anim is not None
    yield 140
    out["midway"] = win.act_dark.icon().cacheKey() not in (first,)
    yield 500
    out["after"] = win.__dict__.get("_ike_icon_fades", {}).get("dark") is None
    from ike.window import icon
    out["moon"] = win.act_dark.icon().cacheKey() == icon(("weather-clear-night", "weather-clear-night-symbolic")).cacheKey()
    # the same mode again (a new page of the same site): nothing moves
    win.sync_dark_icon()
    out["again"] = win.__dict__.get("_ike_icon_fades", {}).get("dark") is None
'''


def test_the_sun_turns_into_the_moon(run_ike):
    out = run_ike(MORPH, settings={"ui_effects": True, "welcome_done": True}, env={"IKE_REDUCED_MOTION": "0"},
                  timeout=90)
    assert out["running"] and out["midway"] and out["after"] and out["moon"] and out["again"], out


def test_without_effects_the_moon_at_once(run_ike):
    out = run_ike(MORPH, settings={"ui_effects": False, "welcome_done": True}, timeout=90)
    assert not out["running"] and out["moon"], out


def test_the_morph_draws_one_then_the_other():
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtCore import QSize
    from PyQt6.QtGui import QColor, QGuiApplication, QIcon, QPixmap
    app = QGuiApplication.instance() or QGuiApplication([])
    from ike import polish

    def solid(colour):
        pm = QPixmap(32, 32)
        pm.fill(QColor(colour))
        return QIcon(pm)
    a, b = solid("#ff0000"), solid("#0000ff")

    def mid(t):
        img = polish.morph_icon(a, b, t).pixmap(QSize(32, 32)).toImage()
        return img.pixelColor(16, 16)
    assert mid(0).red() > 240 and mid(0).blue() < 10
    assert mid(1).blue() > 240 and mid(1).red() < 10
    assert mid(0.5).alpha() < 60                            # between the two, almost nothing
    assert mid(0.25).red() > 0 and mid(0.25).blue() == 0      # the first going
    assert mid(0.8).blue() > 0 and mid(0.8).red() == 0        # the second coming
    del app


FADE = JS + r'''
def steps(ike, qapp, out):
    import time
    from PyQt6.QtCore import QTimer, QUrl
    from PyQt6.QtWidgets import QLabel
    win = ike.windows[0]
    view = win.current_view()
    seen = []
    def look():
        c = view.findChild(QLabel, "ike_page_fade")
        e = c.graphicsEffect() if c is not None else None
        seen.append((time.monotonic(), c is not None and c.isVisible(), e.opacity() if e is not None else None))
    t = QTimer()
    t.timeout.connect(look)
    t.start(10)
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class Slow(BaseHTTPRequestHandler):
        def do_GET(self):
            time.sleep(0.35)                  # as a real site: the answer comes after a while
            colour = self.path.strip("/") or "red"
            # as a real page: it takes a moment to draw after it arrives (a script that runs first)
            body = ("<head><script>var t = Date.now(); while (Date.now() - t < 150) {}</script></head>"
                    "<body style='background:%s'><h1>page %s</h1>" % (colour, colour)).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Slow)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    page = lambda colour: QUrl("http://127.0.0.1:%d/%s" % (srv.server_address[1], colour))
    yield from load(view, page("red"))
    yield 800
    runs = {}
    for name, go in (("another page", lambda: view.load(page("blue"))), ("again", view.reload),
                     ("third", lambda: view.load(page("green")))):
        del seen[:]
        t0 = time.monotonic()
        done = {}
        view.page().loadFinished.connect(lambda ok, d=done: d.setdefault("at", time.monotonic()))
        go()
        yield 2000
        shown = [s for s in seen if s[1]]
        runs[name] = {"shown": len(shown), "first": (shown[0][0] - t0) if shown else None,
                      "last": (shown[-1][0] - t0) if shown else None, "loaded": done.get("at", 0) - t0,
                      "faded": any(s[2] is not None and s[2] < 0.5 for s in shown),
                      "left": view.findChild(QLabel, "ike_page_fade") is not None,
                      "through": None}
    out["runs"] = runs
    t.stop()
'''


def test_the_old_page_fades_into_the_new(run_ike):
    out = run_ike(FADE, settings={"ui_effects": True, "welcome_done": True}, env={"IKE_REDUCED_MOTION": "0"},
                  timeout=120)
    print(out["runs"])
    for name, r in out["runs"].items():
        assert r["shown"] > 0 and r["faded"] and not r["left"], (name, r)
        assert r["last"] < r["loaded"] + 1.2, (name, r)          # gone soon after the page came


def test_no_fade_without_effects(run_ike):
    out = run_ike(FADE, settings={"ui_effects": False, "welcome_done": True}, timeout=120)
    assert all(r["shown"] == 0 for r in out["runs"].values()), out["runs"]


def test_the_flip_shows_one_side_then_the_other():
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtCore import QSize
    from PyQt6.QtGui import QColor, QGuiApplication, QIcon, QPixmap
    app = QGuiApplication.instance() or QGuiApplication([])
    from ike import polish

    def solid(colour):
        pm = QPixmap(32, 32)
        pm.fill(QColor(colour))
        return QIcon(pm)
    a, b = solid("#ff0000"), solid("#0000ff")

    def at(t, x):
        return polish.flip_icon(a, b, t).pixmap(QSize(32, 32)).toImage().pixelColor(x, 16)
    assert at(0, 2).red() > 240 and at(1, 2).blue() > 240
    assert at(0.25, 16).red() > 0 and at(0.25, 16).blue() == 0 and at(0.25, 2).alpha() == 0   # narrower
    assert at(0.75, 16).blue() > 0 and at(0.75, 16).red() == 0 and at(0.75, 2).alpha() == 0
    assert at(0.5, 8).alpha() == 0                                                            # edge-on
    del app


SHIELD = JS + r'''
def steps(ike, qapp, out):
    win = ike.windows[0]
    old = ike.config["shield_level"]
    [a for a in win.level_group.actions() if a.data() and a.data() != old][0].trigger()
    yield 30
    anim = win.__dict__.get("_ike_icon_fades", {}).get("shield")
    out["flip"] = anim is not None and anim.duration() == 340
    yield 700
    out["done"] = "shield" not in win.__dict__.get("_ike_icon_fades", {})
'''


def test_the_shield_turns_to_the_new_level(run_ike):
    out = run_ike(SHIELD, settings={"ui_effects": True, "welcome_done": True}, env={"IKE_REDUCED_MOTION": "0"},
                  timeout=90)
    assert out["flip"] and out["done"], out
