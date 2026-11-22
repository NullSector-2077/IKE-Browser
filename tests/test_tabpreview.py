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


FIT = r'''
def steps(ike, qapp, out):
    from PyQt6.QtCore import QPoint, QUrl
    from PyQt6.QtGui import QPixmap
    from ike import i18n
    from ike.tabpreview import TabPreview
    w = ike.windows[0]
    yield 600
    found = []
    for code in LANGS:
        i18n.setup(code)
        prev = TabPreview(w)
        pm = QPixmap(240, 135)
        pm.fill()
        prev.show_for(0, pm, "Example — example.org", w.mapToGlobal(QPoint(60, 40)))
        yield 50
        for meter, label, value in ((prev.cpu, i18n.T("CPU"), "100 %"), (prev.mem, i18n.T("Memory"), "1023 MB")):
            meter.set(label, value, 1.0)
            fm = meter.fontMetrics()
            # the value and the name side by side, with room between them, inside the meter
            need = fm.horizontalAdvance(value) + fm.horizontalAdvance("  ") + fm.horizontalAdvance(label)
            if need > meter.width() or meter.geometry().right() > prev.width():
                found.append([code, label, value, need, meter.width()])
        prev.hide_preview()
        prev.deleteLater()
        yield 20
    out["found"] = found
'''


def test_cpu_and_memory_are_shown_whole_with_a_large_font(run_ike):
    """1.1.22, seen by the owner: the memory of the tab ended in "…" (the two
    values side by side, half the card each). With a large font (144 dpi)
    and in every language, the name and the whole value fit their line."""
    import json
    from pathlib import Path
    codes = sorted(p.stem for p in (Path(__file__).resolve().parent.parent / "ike/resources/lang").glob("*.json"))
    out = run_ike(FIT.replace("LANGS", json.dumps(["en"] + codes)), env={"QT_FONT_DPI": "144"}, timeout=180)
    assert not out["found"], out["found"][:10]


LETGO = r'''
def steps(ike, qapp, out):
    from PyQt6.QtCore import QEvent, QPoint, QUrl
    w = ike.windows[0]
    w.resize(1100, 760)
    a = w.current_view()
    a.setHtml("<body style='background:#36c'>a", QUrl("https://a.example/"))
    b = w.add_tab(QUrl("about:blank"))
    b.setHtml("<body style='background:#c63'>b", QUrl("https://b.example/"))
    yield 1500
    w.add_tab(QUrl("about:blank"))           # a and b both have their picture
    yield 1500
    w.set_current(a)
    yield 800
    w.set_current(w.views[2])
    yield 800
    out["pictures"] = [getattr(v, "preview", None) is not None for v in (a, b)]
    from ike.tabpreview import TabPreview
    prev = w._preview = TabPreview(w)
    prev.show_for(0, a.preview, "a", w.mapToGlobal(QPoint(100, 20)), a)
    yield 600
    prev.show_for(1, b.preview, "b", w.mapToGlobal(QPoint(200, 20)), b)   # the picture blends
    out["blending"] = getattr(prev, "_blend", None) is not None
    yield 600
    out["blend_after_end"] = getattr(prev, "_blend", None) is not None
    out["shown_picture"] = prev.picture.pixmap() is not None
    w._tab_preview_event(w.tabbar, QEvent(QEvent.Type.Leave))      # the mouse leaves the tabs
    yield 300
    out["hidden"] = [prev.isVisible(), prev.timer.isActive(), prev.picture.pixmap() is not None,
                     getattr(prev, "_blend", None) is not None]
    out["ticks"] = 0
    prev.timer.timeout.connect(lambda: out.__setitem__("ticks", out["ticks"] + 1))
    yield 2500
'''


def test_the_hidden_card_keeps_nothing(run_ike):
    """Measured for 1.1.23: once hidden, the card no longer reads anything
    (its timer stops) and holds no picture. Before, it kept the last tab's
    picture, and the finished blend both pictures, until it was shown again,
    even after their tabs were closed."""
    out = run_ike(LETGO, timeout=90)
    assert out["pictures"] == [True, True], out
    assert out["shown_picture"] and out["blending"], out
    assert not out["blend_after_end"], out           # the blend lets go when it ends
    assert out["hidden"] == [False, False, False, False], out
    assert out["ticks"] == 0, out
