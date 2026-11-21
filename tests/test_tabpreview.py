"""The tab preview (1.1.21, the owner's request): a card painted fully opaque
with rounded corners, and the tab's CPU and memory under its title."""

STEPS = r'''
def steps(ike, qapp, out):
    import os
    from PyQt6.QtCore import QPoint, QUrl
    from PyQt6.QtGui import QColor
    w = ike.windows[0]
    w.resize(1100, 760)
    v = w.current_view()
    v.setHtml("<body style='margin:0;background:linear-gradient(#36c,#c63);height:1600px'>"
              "<h1 style='color:white;font-family:sans-serif;padding:20px'>I.K.E.</h1></body>",
              QUrl("https://example.org/"))
    yield 2500
    w.add_tab(QUrl("about:blank"))
    yield 1500
    out["picture"] = getattr(v, "preview", None) is not None
    i = w.views.index(v)
    w._tab_preview_event  # the window's own handler shows it
    from ike.tabpreview import TabPreview
    prev = TabPreview(w)
    prev.show_for(i, v.preview, "Example Domain — example.org", w.mapToGlobal(QPoint(120, 40)), v)
    yield 1800
    img = prev.grab().toImage()
    W, H = img.width(), img.height()
    a = lambda x, y: QColor.fromRgba(img.pixel(x, y)).alpha()
    out["corner"] = [a(0, 0), a(W - 1, 0), a(0, H - 1), a(W - 1, H - 1)]
    # the card is full: every pixel a little inside its edge
    r = int(10 * img.devicePixelRatio())       # past the rounded corners
    out["full"] = min(a(x, y) for x in range(r, W - r, 3) for y in (2, H // 2, H - 3))
    out["full_side"] = min(a(x, y) for y in range(r, H - r, 3) for x in (2, W // 2, W - 3))
    out["pic_w"] = [prev.picture.width(), v.preview.devicePixelRatio()]
    out["cpu"] = [prev.cpu.label, prev.cpu.value]
    out["mem"] = [prev.mem.label, prev.mem.value]
    shots = os.environ.get("IKE_PREVIEW_SHOTS")
    if shots:
        prev.grab().save(os.path.join(shots, "preview-%s.png" % os.environ.get("IKE_PREVIEW_NAME", "light")))
    prev.hide_preview()
    yield 100
    out["stopped"] = not prev.timer.isActive()
'''


def test_preview_is_a_full_card_with_round_corners_and_the_tabs_load(run_ike):
    out = run_ike(STEPS, timeout=90)
    _check(out)


def test_preview_fills_the_card_on_a_scaled_screen(run_ike):
    """On a screen scaled 2x the picture was half the card's width."""
    out = run_ike(STEPS, env={"QT_SCALE_FACTOR": "2"}, timeout=90)
    assert out["pic_w"] == [240, 2.0], out
    _check(out)


def _check(out):
    assert out["picture"], out
    assert max(out["corner"]) == 0, out              # rounded: the corners are not painted
    assert out["full"] == 255 and out["full_side"] == 255, out    # and the rest is fully opaque
    assert out["cpu"][1].endswith("%"), out          # a reading, not "…" or "—"
    assert out["mem"][1].endswith(("KB", "MB", "GB")), out
    assert out["stopped"], out                       # nothing is read once it is hidden
