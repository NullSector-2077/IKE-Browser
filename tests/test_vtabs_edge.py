"""The vertical tabs' panel ends in a separator line when it slides in over
the page from its hidden edge (1.1.19, the owner's request): one pixel on its
right edge, in the colour Breeze gives its separators (as in Dolphin's side
panels). Pinned, the splitter's own handle already parts it from the page, so
no second line is drawn there. Only the panel's last pixel column changes."""

STEPS = r'''
from PyQt6.QtGui import QColor

def look(win, out, key):
    panel, edge = win.vtab_panel, win.vtabs_edge
    img = panel.grab().toImage()
    ratio = img.devicePixelRatio()
    y = int(panel.height() / 2 * ratio)
    out[key] = {
        "visible": edge.isVisible(),
        "geometry": [edge.x(), edge.y(), edge.width(), edge.height()],
        "panel": [panel.width(), panel.height()],
        "edge_px": img.pixelColor(int((panel.width() - 1) * ratio), y).name(),
        "inner_px": img.pixelColor(int((panel.width() - 4) * ratio), y).name(),
        "want": edge.colour(edge.palette()).name(),
    }

def steps(ike, qapp, out):
    win = ike.windows[0]
    yield 1200
    look(win, out, "pinned")
    ike.config["vtabs_autohide"] = True
    win._apply_vtabs(True)
    yield 400
    win._vtabs_reveal()
    win._vtabs_timer.stop()             # no mouse here: keep it open as if the mouse were over it
    yield 900
    look(win, out, "revealed")
'''


def test_the_panel_has_its_separator_line(run_ike):
    out = run_ike(STEPS, settings={"tabs_position": "vertical"}, timeout=60)
    assert out["pinned"]["visible"] is False, out["pinned"]             # pinned: the splitter's line only
    for key in ("revealed",):
        o = out[key]
        assert o["visible"] is True, (key, o)
        w, h = o["panel"]
        assert o["geometry"] == [w - 1, 0, 1, h], (key, o)              # one pixel, the whole right edge
        assert o["edge_px"] == o["want"], (key, o)                       # drawn in the separator colour
        assert o["inner_px"] != o["want"], (key, o)                      # and only there
