"""The toolbar's Screenshot button opens a menu (1.1.27, the owner): the
visible part, the whole page and an area chosen with the mouse, the same
three entries as Page -> Screenshot..., in I.K.E.'s menu look; a click on the
button opens the menu (it took the visible part at once before), with no
arrow beside the icon, as Print and Zoom; each entry takes its picture."""

STEPS = r'''
from PyQt6.QtCore import QUrl
from PyQt6.QtWidgets import QToolButton, QWidget

def steps(ike, qapp, out):
    w = ike.windows[0]
    w.resize(1000, 500)
    v = w.current_view()
    v.setHtml("<title>t</title><body style='height:3000px;background:#3a7'>x</body>", QUrl("https://shot.example/"))
    yield 1200
    btn = w.nav.widgetForAction(w.act_tb_shot)
    out["visible"] = btn is not None and btn.isVisible()
    out["instant"] = btn.popupMode() == QToolButton.ToolButtonPopupMode.InstantPopup
    out["no_arrow"] = bool(btn.property("ike_no_arrow"))
    m = w.act_tb_shot.menu()
    out["entries"] = [(a.data(), a.text()) for a in m.actions()]
    out["same_as_page_menu"] = [a for a in m.actions()] == [a for a in w.m_shot.actions()]
    out["key"] = m.actions()[0].shortcut().toString()
    pictures = []
    w._save_screenshot = lambda pm: pictures.append(None if pm is None else (pm.width(), pm.height()))
    by_mode = {a.data(): a for a in m.actions()}
    by_mode["visible"].trigger()
    yield 200
    by_mode["page"].trigger()
    for _ in range(100):
        if len(pictures) >= 2:
            break
        yield 100
    by_mode["area"].trigger()
    yield 300
    out["pictures"] = pictures
    out["picker"] = w.findChild(QWidget, "ike_area_picker") is not None
    out["view"] = [v.width(), v.height()]
'''


def test_the_screenshot_button_opens_its_menu(run_ike):
    out = run_ike(STEPS, timeout=90)
    assert "error" not in out, out.get("error")
    assert out["visible"] and out["instant"] and out["no_arrow"], out
    assert out["entries"] == [["visible", "Visible part"], ["page", "Whole page"], ["area", "Selected area"]], out
    assert out["same_as_page_menu"] and out["key"] == "Ctrl+Shift+S", out
    shots = out["pictures"]
    assert len(shots) == 2 and all(shots), out
    (vw, vh), (pw, ph) = shots
    assert vw == pw and ph > vh * 2, out              # the whole page is taller than what is shown
    assert out["picker"], out                          # the area: the picker over the page
