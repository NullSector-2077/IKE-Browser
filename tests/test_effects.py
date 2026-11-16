"""The interface's extra effects (ike/effects.py): they follow the setting and
the desktop's reduced-motion choice, change nothing in what the interface
does, and leave no timer or animation running when the interface is still."""

import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

SHOTS = os.environ.get("IKE_TEST_SHOTS", "")


def test_reduced_motion_on_windows(monkeypatch):
    """Windows: the answer is Windows' own "Animation effects" switch
    (SPI_GETCLIENTAREAANIMATION), not a settings file; the override of the
    tests and the user's own switch work as everywhere."""
    from ike import effects, winapi
    monkeypatch.delenv("IKE_REDUCED_MOTION", raising=False)
    asked = []
    for wanted in (True, False):
        monkeypatch.setattr(winapi, "animations_wanted", lambda wanted=wanted: asked.append(1) or wanted,
                            raising=False)
        assert effects._desktop_reduced("win32") is (not wanted)
    assert len(asked) == 2
    assert winapi.SPI_GETCLIENTAREAANIMATION == 0x1042
    if os.name == "nt":                          # the real question, where there is a Windows to ask
        monkeypatch.undo()
        monkeypatch.delenv("IKE_REDUCED_MOTION", raising=False)
        effects._checked["at"] = -1e9
        assert effects.reduced_motion() is (not winapi.animations_wanted())
    monkeypatch.setenv("IKE_REDUCED_MOTION", "1")
    assert effects.reduced_motion() is True and effects.on({"ui_effects": True}) is False
    monkeypatch.setenv("IKE_REDUCED_MOTION", "0")
    assert effects.on({"ui_effects": True}) is True and effects.on({"ui_effects": False}) is False


@pytest.mark.linux_only("reads Plasma's kdeglobals and GTK's settings.ini; on Windows the answer comes "
                        "from Windows itself (test_reduced_motion_on_windows)")
def test_reduced_motion_is_read_from_the_desktop(tmp_path, monkeypatch):
    from ike import effects
    monkeypatch.delenv("IKE_REDUCED_MOTION", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    def reduced():
        effects._checked["at"] = -1e9            # look again now
        return effects.reduced_motion()
    assert reduced() is False                    # nothing said: effects allowed
    (tmp_path / "kdeglobals").write_text("[General]\nName=x\n[KDE]\nAnimationDurationFactor=0\n")
    assert reduced() is True                     # Plasma: animation speed "instant"
    (tmp_path / "kdeglobals").write_text("[KDE]\nAnimationDurationFactor=0.5\n")
    assert reduced() is False
    (tmp_path / "kdeglobals").write_text("[KDE]\nAnimationDurationFactor=nonsense\n")
    assert reduced() is False
    (tmp_path / "kdeglobals").unlink()
    (tmp_path / "gtk-3.0").mkdir()
    (tmp_path / "gtk-3.0" / "settings.ini").write_text("[Settings]\ngtk-enable-animations=0\n")
    assert reduced() is True                     # GTK desktops
    (tmp_path / "gtk-3.0" / "settings.ini").write_text("[Settings]\ngtk-enable-animations=true\n")
    assert reduced() is False
    # the answer is kept for a few seconds, not read from disk at every hover
    (tmp_path / "gtk-3.0" / "settings.ini").write_text("[Settings]\ngtk-enable-animations=0\n")
    assert effects.reduced_motion() is False
    monkeypatch.setenv("IKE_REDUCED_MOTION", "1")
    assert effects.reduced_motion() is True
    assert effects.on({"ui_effects": True}) is False
    monkeypatch.setenv("IKE_REDUCED_MOTION", "0")
    assert effects.on({"ui_effects": True}) is True and effects.on({"ui_effects": False}) is False
    assert effects.on({}) is True and effects.on(None) is True      # a missing setting never breaks a paint
    c = effects.blend("#000000", "#ffffff", 0.5)
    assert (c.red(), c.green(), c.blue()) == (128, 128, 128)
    assert effects.blend("#102030", "#ffffff", -3).name() == "#102030"
    assert effects.blend("#102030", "#ffffff", 7).name() == "#ffffff"


@pytest.fixture
def slow_site():
    """A page whose body arrives after two seconds, and a page that never ends."""
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            if self.path.startswith("/endless"):
                self.end_headers()
                self.wfile.write(b"<!doctype html><title>endless</title>start")
                self.wfile.flush()
                try:
                    for _ in range(600):
                        time.sleep(0.1)
                        self.wfile.write(b" ")
                        self.wfile.flush()
                except OSError:
                    pass
                return
            body = b"<!doctype html><title>slow</title>done"
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if self.path.startswith("/slow"):
                time.sleep(2.0)
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield "http://127.0.0.1:%d" % srv.server_address[1]
    srv.shutdown()


STEPS = r'''
import os
from PyQt6.QtCore import QAbstractAnimation, QEvent, QPointF, QTimer, Qt, QUrl
from PyQt6.QtGui import QColor, QEnterEvent
from PyQt6.QtWidgets import QApplication

SITE = %r

def running(win):
    """Animations and repeating timers of the window that are active now."""
    found = [type(a).__name__ + ":" + (a.parent().objectName() or type(a.parent()).__name__)
             for a in win.findChildren(QAbstractAnimation) if a.state() == QAbstractAnimation.State.Running]
    spin = getattr(win, "_spin", None)
    if spin is not None and spin.isActive():
        found.append("spin")
    return found

def mark(win, i):
    """Does the icon of tab i carry the loading mark? (accent-coloured ring, upper left)"""
    img = win.tabbar.tabIcon(i).pixmap(32, 32).toImage()
    accent = win.tabbar.palette().color(win.tabbar.palette().ColorRole.Highlight)
    n = 0
    for x in range(0, img.width() // 2):
        for y in range(0, img.height() // 2):
            c = QColor.fromRgba(img.pixel(x, y))
            if c.alpha() > 200 and abs(c.red() - accent.red()) + abs(c.green() - accent.green()) \
                    + abs(c.blue() - accent.blue()) < 40:
                n += 1
    return n

def red(widget):
    img = widget.grab().toImage()
    n = 0
    for x in range(img.width()):
        for y in range(img.height()):
            c = QColor(img.pixel(x, y))
            if c.red() > 150 and c.green() < 110 and c.blue() < 110:
                n += 1
    return n

def steps(ike, qapp, out):
    from ike import effects
    win = ike.windows[0]
    yield 1200
    out["on"] = effects.on(ike.config)
    out["idle_start"] = running(win)

    # --- a tab that loads: the mark comes after a moment, turns, and goes away
    view = win.add_tab(SITE + "/slow", background=True)
    i = win.views.index(view)
    yield 120
    out["mark_at_once"] = mark(win, i)
    yield 500
    first = win.tabbar.tabIcon(i).pixmap(32, 32).toImage()
    out["mark_loading"] = mark(win, i)
    out["spin_active"] = "spin" in running(win)
    yield 300
    second = win.tabbar.tabIcon(i).pixmap(32, 32).toImage()
    out["mark_turned"] = first != second
    out["vtab_icon_same"] = win.vtabs.item(i).icon().pixmap(32, 32).toImage() == second
    for _ in range(40):
        if not view.loading:
            break
        yield 100
    yield 300
    out["mark_after"] = mark(win, i)
    out["after_load"] = running(win)
    out["title"] = view.title()
    # the new tab page loads at once: it never shows the mark
    fast = win.add_tab("ike:newtab", background=True)
    seen = []
    for _ in range(8):
        yield 60
        seen.append(mark(win, win.views.index(fast)))
    out["mark_fast"] = max(seen)

    # --- a page that never finishes: the mark stops turning after a while, the timer stops
    win.MARK_TURNS_FOR = 1.2
    endless = win.add_tab(SITE + "/endless", background=True)
    j = win.views.index(endless)
    yield 700
    out["endless_mark"] = mark(win, j)
    out["endless_spinning"] = "spin" in running(win)
    yield 1500
    a = win.tabbar.tabIcon(j).pixmap(32, 32).toImage()
    yield 400
    b = win.tabbar.tabIcon(j).pixmap(32, 32).toImage()
    out["endless_still"] = [mark(win, j) > 0, a == b, running(win)]
    win.close_tab(endless)
    yield 300

    # --- menus fade in and always end fully visible
    win.shield_menu.popup(win.shield_btn.mapToGlobal(win.shield_btn.rect().bottomLeft()))
    yield 10
    out["menu_start"] = [round(win.shield_menu.windowOpacity(), 2), win.shield_menu.isVisible(),
                         win.shield_panel.isVisible()]
    yield 400
    out["menu_shown"] = [round(win.shield_menu.windowOpacity(), 2), win.shield_menu.isVisible()]
    win.shield_menu.hide()
    # closed in the middle of the fade: opaque again the next time, whatever the setting
    win.shield_menu.popup(win.shield_btn.mapToGlobal(win.shield_btn.rect().bottomLeft()))
    yield 20
    win.shield_menu.hide()
    yield 50
    out["menu_interrupted"] = round(win.shield_menu.windowOpacity(), 2)
    yield 300
    out["after_menu"] = running(win)

    # --- the window close button: the red glides in on hover
    from ike.closebutton import WindowCloseButton
    btn = win.findChild(WindowCloseButton)
    out["rest_red"] = red(btn)
    centre = QPointF(btn.width() / 2, btn.height() / 2)
    QApplication.sendEvent(btn, QEnterEvent(centre, centre, QPointF(btn.mapToGlobal(centre.toPoint()))))
    yield 25
    out["hover_mid"] = [red(btn), round(btn._glide.value, 2), btn._glide.moving]
    yield 400
    out["hover_full"] = [red(btn), btn._glide.value, btn._glide.moving]
    QApplication.sendEvent(btn, QEvent(QEvent.Type.Leave))
    yield 400
    out["hover_left"] = [red(btn), btn._glide.value, btn._glide.moving]

    # --- the loading line advances and ends
    line = win.loading_line
    win.set_current(view)
    view.load(QUrl(SITE + "/slow?again"))
    values = []
    for _ in range(12):
        yield 60
        values.append(round(line.value, 3))
    out["line_values"] = values
    for _ in range(40):
        if not view.loading:
            break
        yield 100
    yield 800
    out["line_after"] = [line.isVisible(), running(win)]
    out["idle_end"] = running(win)
'''


@pytest.mark.parametrize("mode", ["on", "setting-off", "reduced-motion"])
def test_effects_and_what_stays_the_same_without_them(run_ike, slow_site, mode):
    settings = {"system_titlebar": False, "ui_effects": mode != "setting-off"}
    env = {"IKE_REDUCED_MOTION": "1" if mode == "reduced-motion" else "0", "IKE_TEST_SHOTS": SHOTS}
    out = run_ike(STEPS % slow_site, settings=settings, env=env, timeout=150)
    effects = mode == "on"
    assert out["on"] is effects
    assert out["idle_start"] == [] and out["idle_end"] == [] and out["after_load"] == []
    assert out["after_menu"] == []
    # the loading mark: never for a page that loads at once, there while a slow one loads
    assert out["mark_at_once"] == 0 and out["mark_fast"] == 0
    assert out["mark_loading"] > 8 and out["mark_after"] == 0 and out["title"] == "slow"
    assert out["vtab_icon_same"]
    assert out["mark_turned"] is effects             # it turns only with the effects on
    assert out["endless_mark"] > 8
    still, same, left = out["endless_still"]
    assert still and same and left == []             # stays, no longer turns, nothing left running
    # menus open and are fully visible in every mode
    assert out["menu_start"][1:] == [True, True]
    assert out["menu_start"][0] < 1.0 if effects else out["menu_start"][0] == 1.0
    assert out["menu_shown"] == [1.0, True]
    assert out["menu_interrupted"] == 1.0
    # the close button: same resting and hovered looks; only the way between differs
    assert out["rest_red"] < 5
    assert out["hover_full"][0] > 20 and out["hover_full"][1:] == [1.0, False]
    assert out["hover_left"][0] < 5 and out["hover_left"][1:] == [0.0, False]
    if effects:
        assert 0.0 < out["hover_mid"][1] < 1.0 and out["hover_mid"][2] is True
    else:
        assert out["hover_mid"][0] > 20 and out["hover_mid"][1:] == [1.0, False]
    # the loading line reaches the end either way
    assert max(out["line_values"]) > 0 and out["line_after"] == [False, []]
