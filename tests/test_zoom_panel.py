"""The panel of the toolbar's Zoom button (1.1.25): ike/zoompanel.py.

In the real browser: the button opens it under itself (no menu any more; the
☰ menu keeps its Zoom submenu); − and + change the page's zoom one step and
the panel stays open, without the box over the page; the slider takes the
same steps; "Actual size"; the zoom kept for the site, and not in a private
window (the panel says which); the default zoom is the setting of Settings →
Appearance, the pages at the old default follow it; the values under the
slider stand under their ticks (measured on the painted slider); every label
on one left edge, every control on one right edge, each label centred with
its control; keyboard; no address outside I.K.E.
"""

import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from conftest import screen
from test_security import JS


@pytest.fixture
def site():
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            data = b"<!doctype html><title>zoom</title><p>Some text to zoom."
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):
            pass
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield "http://127.0.0.1:%d" % srv.server_address[1]
    srv.shutdown()


STEPS = JS + r'''
SITE = "__SITE__"

def steps(ike, qapp, out):
    from PyQt6.QtCore import QPoint, Qt
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QAbstractButton, QComboBox, QLabel, QWidget
    win = ike.windows[0]
    win.resize(1400, 860)
    ike.config["toolbar_hidden"] = [k for k in ike.config["toolbar_hidden"] if k != "zoom"]
    win._apply_toolbar()
    yield 400
    btn = win.nav.widgetForAction(win.act_tb_zoom)
    out["no_menu"] = [win.act_tb_zoom.menu() is None, [a.text() for a in (win.act_zoom_in, win.act_zoom_out, win.act_zoom_reset)]]
    view = win.current_view()
    yield from load(view, SITE + "/page")
    QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
    yield 500
    menu, panel = win.panel_of("zoom")
    g, b = menu.geometry(), btn.mapToGlobal(QPoint(0, 0))
    out["place"] = [menu.isVisible(), g.top() - (b.y() + btn.height()), (g.right() + 1) - (b.x() + btn.width())]
    out["start"] = [panel.title.text(), panel.host.text(), panel.value.text(), panel.note.text(),
                    panel.reset.isEnabled(), panel.slider.value(), panel.default.currentText()]
    # + and −: one step, the panel stays open, no box over the page
    panel.plus.click()
    yield 300
    out["plus"] = [round(view.zoomFactor(), 2), panel.value.text(), panel.slider.value(), menu.isVisible(),
                   win.toast_pill.isVisible(), ike.config["site_zoom"].get("127.0.0.1"), panel.reset.isEnabled()]
    panel.slider.setValue(win.ZOOM_STEPS.index(2.0))
    yield 300
    out["slider"] = [round(view.zoomFactor(), 2), panel.value.text(), menu.isVisible(),
                     ike.config["site_zoom"].get("127.0.0.1")]
    panel.minus.click()
    yield 300
    out["minus"] = [round(view.zoomFactor(), 2), panel.value.text()]
    panel.reset.click()
    yield 300
    out["reset"] = [round(view.zoomFactor(), 2), panel.value.text(), "127.0.0.1" in ike.config["site_zoom"],
                    panel.reset.isEnabled(), menu.isVisible()]
    # the keys move the slider too
    panel.slider.setFocus()
    QTest.keyClick(panel.slider, Qt.Key.Key_Right)
    yield 300
    out["key"] = [round(view.zoomFactor(), 2), panel.value.text()]
    panel.reset.click()
    yield 300

    # the values under the slider stand under their ticks (found in the painted slider)
    img = panel.slider.grab().toImage()
    ratio = img.devicePixelRatio()
    bg = img.pixelColor(1, img.height() - 1)
    cols = []
    for x in range(img.width()):
        c = img.pixelColor(x, img.height() - int(4 * ratio))
        if abs(c.red() - bg.red()) + abs(c.green() - bg.green()) + abs(c.blue() - bg.blue()) > 20:
            cols.append(x)
    groups = []
    for x in cols:
        if groups and x - groups[-1][-1] <= 1:
            groups[-1].append(x)
        else:
            groups.append([x])
    ticks = [(gr[0] + gr[-1] + 1) / 2 / ratio for gr in groups]
    places = panel.marks.places()
    sx = panel.slider.mapTo(panel, QPoint(0, 0)).x()
    mx = panel.marks.mapTo(panel, QPoint(0, 0)).x()
    one = win.ZOOM_STEPS.index(1.0)
    out["ticks"] = [len(ticks), len(win.ZOOM_STEPS)]
    out["mark_100"] = (mx + places[1][1].center().x() + 0.5) - (sx + ticks[one]) if len(ticks) > one else None
    out["mark_ends"] = [mx + places[0][1].left() - sx, (mx + places[2][1].right() + 1) - (sx + panel.slider.width())]
    out["mark_texts"] = [t for t, _r in places]

    # the default zoom: the setting of Settings → Web pages; the pages at the old default follow it
    i = panel.default.findData(1.25)
    panel.default.setCurrentIndex(i)
    panel.default.activated.emit(i)
    yield 400
    saved = json.loads(open(ike.config.path, encoding="utf-8").read())["default_zoom"]
    dlg = win.open_settings("sites")
    yield 300
    out["default"] = [ike.config["default_zoom"], saved, round(view.zoomFactor(), 2), panel.value.text(),
                      round(dlg.zoom.value(), 2), panel.reset.isEnabled()]
    dlg.close()
    yield 200
    win.show_zoom_panel()
    yield 400

    # alignment (the owner): one left edge, one right edge, each label centred with its control
    def box(w):
        o = w.mapTo(panel, QPoint(0, 0))
        return [o.x(), o.y(), o.x() + w.width(), o.y() + w.height()]
    lefts = [box(w)[0] for w in (panel.head_icon, panel.minus, panel.slider, panel.note, panel.default_label,
                                 panel.hint)]
    lefts.append(mx + places[0][1].left())
    rights = [box(w)[2] for w in (panel.host, panel.plus, panel.slider, panel.reset, panel.default)]
    rights.append(mx + places[2][1].right() + 1)
    out["lefts"], out["rights"] = sorted(set(lefts)), sorted(set(rights))
    out["host_right"] = bool(panel.host.alignment() & Qt.AlignmentFlag.AlignRight)
    pairs = [(panel.title, panel.head_icon), (panel.host, panel.title), (panel.value, panel.minus),
             (panel.value, panel.plus), (panel.note, panel.reset), (panel.default_label, panel.default)]
    out["centres"] = [((box(a)[1] + box(a)[3]) - (box(b)[1] + box(b)[3])) / 2 for a, b in pairs]
    out["focus"] = [w.focusPolicy() != Qt.FocusPolicy.NoFocus
                    for w in (panel.minus, panel.plus, panel.slider, panel.reset, panel.default)]
    out["buddy"] = panel.default_label.buddy() is panel.default
    texts = []
    for w in [panel] + panel.findChildren(QWidget):
        texts.append(w.toolTip() + " " + w.accessibleName())
        if isinstance(w, (QLabel, QAbstractButton)):
            texts.append(w.text())
        if isinstance(w, QComboBox):
            texts += [w.itemText(k) for k in range(w.count())]
    out["texts"] = " ".join(texts)
    menu.hide()
    yield 300

    # a private window: its zoom is not kept, the panel says so
    pw = ike.new_window(private=True)
    pw.resize(1400, 860)
    pw.toolbar_layout.hidden.discard("zoom")
    pw._fit_urlbar(place=True)
    yield 600
    yield from load(pw.current_view(), SITE + "/private")
    pw.show_zoom_panel()
    yield 400
    _m, ppanel = pw.panel_of("zoom")
    before = dict(ike.config["site_zoom"])
    ppanel.plus.click()
    yield 300
    out["private"] = [ppanel.note.text(), round(pw.current_view().zoomFactor(), 2), ike.config["site_zoom"] == before]
    pw.close()
'''


def test_the_panel_in_the_browser(run_ike, site, tmp_path):
    from ike.i18n import T
    out = run_ike(STEPS.replace("__SITE__", site), env=screen(tmp_path, 1600, 1000), timeout=150,
                  settings={"start_maximized": False})
    no_menu, entries = out["no_menu"]
    assert no_menu and entries == [T("Zoom in"), T("Zoom out"), T("Actual size")]     # the ☰ menu keeps them
    shown, top, right = out["place"]
    assert shown and 0 <= top <= 4 and abs(right) <= 8, out["place"]
    assert out["start"] == [T("Zoom"), "127.0.0.1", "100%", T("Remembered for this site"), False, 5, "100%"]
    assert out["plus"] == [1.1, "110%", 6, True, False, 1.1, True], out["plus"]
    assert out["slider"] == [2.0, "200%", True, 2.0], out["slider"]
    assert out["minus"] == [1.75, "175%"], out["minus"]
    assert out["reset"] == [1.0, "100%", False, False, True], out["reset"]
    assert out["key"] == [1.1, "110%"], out["key"]
    assert out["ticks"] == [14, 14], out["ticks"]
    assert out["mark_100"] is not None and abs(out["mark_100"]) <= 1, out["mark_100"]
    assert out["mark_ends"] == [0, 0], out["mark_ends"]
    assert out["mark_texts"] == ["30%", "100%", "400%"]
    assert out["default"] == [1.25, 1.25, 1.25, "125%", 1.25, False], out["default"]
    assert len(out["lefts"]) == 1 and len(out["rights"]) == 1 and out["host_right"], (out["lefts"], out["rights"])
    assert all(abs(c) <= 1 for c in out["centres"]), out["centres"]
    assert all(out["focus"]) and out["buddy"]
    assert not re.search(r"https?:|www\.|://", out["texts"]), out["texts"]
    note, factor, kept = out["private"]
    assert note == T("Not remembered in a private window") and factor > 1.25 and kept, out["private"]
