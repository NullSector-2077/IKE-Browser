"""Site colour (1.1.14, 1.1.16): the edge of the address bar takes the site's colour.

The colour comes from the page's theme-color (read in I.K.E.'s isolated world),
greys give none, the rest of the window keeps its theme, and the option
switched off takes the colour away.
"""

STEPS = r"""
from PyQt6.QtCore import QUrl

def load(v, html, url, done):
    done.clear()
    v.setHtml(html, QUrl(url))

def edge(win):
    e = getattr(win.urlbar, "site_edge", None)
    return e.name() if e is not None else None

def steps(ike, qapp, out):
    win = ike.windows[0]
    v = win.current_view()
    done = {}
    v.page().loadFinished.connect(lambda ok: done.setdefault("ok", ok))
    out["nav_before"] = win.nav.palette().color(win.nav.backgroundRole()).name()

    load(v, '<!doctype html><meta name="theme-color" content="#d32f2f"><title>r</title>',
         "https://red.example/", done)
    while "ok" not in done:
        yield 20
    yield 600
    out["red"] = edge(win)
    out["nav_after"] = win.nav.palette().color(win.nav.backgroundRole()).name()
    out["nav_fill"] = win.nav.autoFillBackground()
    # the outline is really drawn around the field
    img = win.urlbar.grab().toImage()
    reds = 0
    for x in range(img.width()):
        for y in (1, 2, img.height() - 2, img.height() - 3):
            c = img.pixelColor(x, y)
            if c.red() > 150 and c.green() < 110 and c.blue() < 110:
                reds += 1
    out["red_pixels"] = reds

    load(v, '<!doctype html><meta name="theme-color" content="rgb(250, 250, 250)"><title>w</title>',
         "https://white.example/", done)
    while "ok" not in done:
        yield 20
    yield 600
    out["grey"] = edge(win)

    load(v, '<!doctype html><meta name="theme-color" content="#1565c0"><title>b</title>',
         "https://blue.example/", done)
    while "ok" not in done:
        yield 20
    yield 600
    out["blue"] = edge(win)
    ike.config["site_tint"] = False
    ike.refresh_windows()
    yield 600
    out["off"] = edge(win)
"""


def test_the_address_bar_edge_takes_the_site_colour(run_ike):
    out = run_ike(STEPS)
    assert out["red"] == "#d32f2f", out
    assert out["red_pixels"] > 20, out                     # drawn around the field
    assert out["nav_after"] == out["nav_before"] and not out["nav_fill"], out   # the toolbar keeps its theme
    assert out["grey"] is None, out                        # a grey gives no colour
    assert out["blue"] == "#1565c0", out
    assert out["off"] is None, out
