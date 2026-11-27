"""1.1.29 (the owner): the address of the link under the mouse is shown again,
as other browsers show it, without moving the page (1.0 put it in the status
bar, which took room from the page: the page shook). It lies over the page in
a corner, the other corner when the mouse is there, and goes when the mouse
leaves the link."""

STEPS = r'''
from PyQt6.QtCore import QPoint, QUrl

def steps(ike, qapp, out):
    win = ike.windows[0]
    win.resize(1200, 800)
    win.show()
    view = win.current_view()
    done = {}
    view.page().loadFinished.connect(lambda ok, d=done: d.setdefault("ok", ok))
    view.setHtml("<body style='margin:0'><a id=l href='https://example.org/a/very/long/path?x=1' "
                 "style='display:block;width:300px;height:80px'>link</a></body>", QUrl("https://site.example/"))
    while "ok" not in done:
        yield 20
    yield 300
    before = [view.geometry().height(), view.mapTo(win, QPoint(0, 0)).y(), win.statusBar().isVisible()]
    lp = win.link_preview
    view.page().linkHovered.emit("https://example.org/a/very/long/path?x=1")
    yield 100
    out["shown"] = [lp.isVisible(), lp.text, lp.parentWidget() is win.content.parentWidget()]
    g, c = lp.geometry(), win.content.geometry()
    out["corner"] = [g.left() == c.left(), g.bottom() == c.bottom()]
    out["page_still"] = before == [view.geometry().height(), view.mapTo(win, QPoint(0, 0)).y(),
                                   win.statusBar().isVisible()]
    from PyQt6.QtCore import Qt
    out["mouse"] = lp.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    view.page().linkHovered.emit("")
    yield 50
    out["stays_a_moment"] = lp.isVisible()
    yield 300
    out["gone"] = not lp.isVisible()
    # a tab left: its link's address goes with it
    view.page().linkHovered.emit("https://example.org/b")
    yield 50
    win.add_tab(QUrl("about:blank"))
    yield 200
    out["tab_left"] = not lp.isVisible()
'''


def test_link_address_over_the_page(run_ike):
    out = run_ike(STEPS, timeout=90)
    assert out["shown"] == [True, "https://example.org/a/very/long/path?x=1", True], out
    assert out["corner"] == [True, True], out
    assert out["page_still"] and out["mouse"], out
    assert out["stays_a_moment"] and out["gone"] and out["tab_left"], out
