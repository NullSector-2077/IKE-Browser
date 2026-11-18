"""Site tint (1.1.14): the navigation bar takes a light tint of the site's colour.

The colour comes from the page's theme-color (read in I.K.E.'s isolated world),
greys give no tint, I.K.E.'s own pages and the option switched off bring the
bar back to the theme's own colour.
"""

STEPS = r"""
from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QPalette

def load(v, html, url, done):
    done.clear()
    v.setHtml(html, QUrl(url))

def steps(ike, qapp, out):
    win = ike.windows[0]
    v = win.current_view()
    done = {}
    v.page().loadFinished.connect(lambda ok: done.setdefault("ok", ok))
    base = win.palette().color(QPalette.ColorRole.Window)
    out["base"] = base.name()

    load(v, '<!doctype html><meta name="theme-color" content="#d32f2f"><title>r</title>',
         "https://red.example/", done)
    while "ok" not in done:
        yield 20
    yield 600
    t = win.site_tint.shown
    out["red"] = t.name() if t is not None else None
    out["bar_red"] = win.nav.palette().color(win.nav.backgroundRole()).name()

    load(v, '<!doctype html><meta name="theme-color" content="rgb(250, 250, 250)"><title>w</title>',
         "https://white.example/", done)
    while "ok" not in done:
        yield 20
    yield 600
    out["grey"] = win.site_tint.shown

    load(v, '<!doctype html><meta name="theme-color" content="#1565c0"><title>b</title>',
         "https://blue.example/", done)
    while "ok" not in done:
        yield 20
    yield 600
    out["blue"] = win.site_tint.shown.name() if win.site_tint.shown is not None else None
    ike.config["site_tint"] = False
    ike.refresh_windows()
    yield 600
    out["off"] = win.site_tint.shown
    out["autofill_off"] = win.nav.autoFillBackground()
"""


def _rgb(name):
    return tuple(int(name[i:i + 2], 16) for i in (1, 3, 5))


def test_the_bar_takes_the_site_colour(run_ike):
    out = run_ike(STEPS)
    base = _rgb(out["base"])
    red = _rgb(out["red"])
    assert red != base and red[0] > red[2], out          # nudged towards red...
    assert max(abs(a - b) for a, b in zip(red, base)) < 60, out   # ...lightly
    assert out["bar_red"] == out["red"], out
    assert out["grey"] is None, out                        # a grey gives no tint
    blue = _rgb(out["blue"])
    assert blue[2] > blue[0], out
    assert out["off"] is None and not out["autofill_off"], out
