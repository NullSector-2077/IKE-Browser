"""1.1.30 (the owner): three moving touches.

- A file that starts downloading flies, as its type's icon, to the
  Downloads button (polish.FlyingIcon, "download_fly").
- On the touchpad a round arrow comes in from the page's edge while the
  fingers swipe, and fills with the theme's colour when the swipe will act
  (polish.SwipeArrow, gestures._arrow, "swipe_arrow").
- On the new tab page I.K.E.'s own thoughts are written letter by letter
  (newtab.html, think()).
All of them follow "Interface effects" and the desktop's reduced motion.
"""

from conftest import APP

STEPS = r'''
from PyQt6.QtCore import QUrl

def steps(ike, qapp, out):
    from ike import gestures, polish
    win = ike.windows[0]
    win.show()
    view = win.current_view()
    for url in ("data:text/html,<p>one", "data:text/html,<p>two"):
        done = {}
        view.page().loadFinished.connect(lambda ok, d=done: d.setdefault("ok", ok))
        view.load(QUrl(url))
        while "ok" not in done:
            yield 20
    yield 300
    # the swipe's arrow: back is possible, forward is not
    gestures._arrow(view, gestures.SWIPE_PX * 0.5)
    arrow = view.__dict__.get("_ike_swipe_arrow")
    out["arrow"] = [arrow is not None and arrow.isVisible(), round(arrow.progress, 2), arrow.back,
                    arrow.geometry().center().x() < view.geometry().center().x()]
    gestures._arrow(view, gestures.SWIPE_PX * 2)
    out["arrow_full"] = arrow.progress
    gestures._arrow(view, None)
    out["arrow_gone"] = not arrow.isVisible()
    gestures._arrow(view, -gestures.SWIPE_PX)              # forward: there is no next page
    out["forward"] = arrow.isVisible()
    # the flying icon: made, and gone after its flight
    win.download_fly("report.pdf")
    flying = win.findChildren(polish.FlyingIcon)
    out["fly"] = len(flying)
    yield polish.FlyingIcon.MS + 400
    out["fly_after"] = len([w for w in win.findChildren(polish.FlyingIcon) if w.isVisible()])
    # effects off: nothing flies
    ike.config["ui_effects"] = False
    win.download_fly("report.pdf")
    out["fly_off"] = len(win.findChildren(polish.FlyingIcon))
'''


def test_download_fly_and_swipe_arrow(run_ike):
    out = run_ike(STEPS, settings={"ui_effects": True}, timeout=120)
    shown, progress, back, left = out["arrow"]
    assert shown and back and left and progress == 0.5, out["arrow"]
    assert out["arrow_full"] == 1.0 and out["arrow_gone"] and out["forward"] is False, out
    assert out["fly"] == 1 and out["fly_after"] == 0 and out["fly_off"] == 0, out


def test_the_thoughts_are_written_letter_by_letter_only_with_effects():
    page = (APP / "ike" / "resources" / "newtab.html").read_text("utf-8")
    js = (APP / "ike" / "resources" / "greeting.js").read_text("utf-8")
    assert 'els.line(r.key ? words(r.key, r.n) : "", r.key || "")' in js
    body = page[page.index("function think("):page.index("function tick()")]
    assert 'key.indexOf("thought") !== 0' in body                     # only I.K.E.'s own thoughts
    assert 'classList.contains("fx")' in body and "prefers-reduced-motion: reduce" in body
    assert "requestAnimationFrame" in body and "setTimeout" not in body and "setInterval" not in body
    assert 'setAttribute("aria-label", text)' in body                 # the whole line for a screen reader
    assert "Intl.Segmenter" in body                                   # whole letters in every script
