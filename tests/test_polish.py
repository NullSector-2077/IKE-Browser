"""The small touches of 1.1.3 (ike/polish.py): the gliding mark of the current
tab, titles that fade out, icons that change with a fade, the vertical rows
(hover, new row), the pulsing speaker, the rounded address field, the
suggestions, the zoom sign, Reload/Stop, the find bar, the finished
download, the tab preview and the new tab page. Clicks and keys are real
(QTest); with the effects off everything changes at once and nothing is left
running."""

import pytest
from test_effects import slow_site  # noqa: F401  (the fixture)
from test_security import JS

COMMON = r'''
import json
from PyQt6.QtCore import QAbstractAnimation, QPoint, Qt, QUrl
from PyQt6.QtGui import QColor, QIcon, QPixmap
from PyQt6.QtTest import QTest

LONG = "A rather long page title that does not fit in a tab at all, not even close"

def running(win):
    return sorted(type(a.parent()).__name__ for a in win.findChildren(QAbstractAnimation)
                  if a.state() == QAbstractAnimation.State.Running)

def page(view, title):
    view.setHtml("<!doctype html><title>%s</title><body>x</body>" % title, QUrl("http://local.test/"))

def red_icon():
    pm = QPixmap(32, 32)
    pm.fill(QColor("#e01010"))
    return QIcon(pm)

def reddish(icon):
    c = QColor(icon.pixmap(32, 32).toImage().pixel(16, 16))
    return c.red() > 150 and c.green() < 90
'''

HORIZONTAL = COMMON + r'''
def steps(ike, qapp, out):
    win = ike.windows[0]
    win.resize(1200, 800)
    yield 600
    a = win.current_view()
    b = win.add_tab("ike:newtab")
    c = win.add_tab("ike:newtab")
    page(a, "First")
    page(c, LONG)
    yield 1200
    bar = win.tabbar
    out["current"] = bar.currentIndex()
    # a real click on the first tab: the mark glides there
    QTest.mouseClick(bar, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, bar.tabRect(0).center())
    yield 40
    target = bar.mark.target()
    shown = bar.mark._shown
    out["mid"] = [bar.currentIndex(), bar.mark.gliding, shown is not None and shown.x() > target.x() + 1]
    yield 400
    bar.repaint()
    out["end"] = [bar.mark.gliding, abs(bar.mark._shown.x() - bar.mark.target().x()) < 0.5,
                  abs(bar.mark._shown.width() - bar.mark.target().width()) < 0.5]
    # the long title: the tab keeps its size, the title fades out
    i = win.views.index(c)
    fm = bar.fontMetrics()
    out["long_width"] = [bar.tabRect(i).width(), len(bar.tabText(i)), bar.tabData(i),
                         fm.averageCharWidth() * 27 + 80]
    out["no_dots"] = not bar.tabText(i).endswith("…")
    before = bar.label_style.faded
    bar.repaint()
    out["faded"] = bar.label_style.faded > before
    # a new site icon comes in with a fade, and ends as the icon itself
    win._icon_changed(a, red_icon())
    yield 30
    out["icon_fading"] = id(a) in win.__dict__.get("_ike_icon_fades", {})
    yield 400
    out["icon_end"] = [id(a) in win.__dict__.get("_ike_icon_fades", {}), reddish(bar.tabIcon(0))]
    # a tab playing sound: the speaker pulses, and stops with the sound
    a.page().recentlyAudible = lambda: True
    win._tab_changed(a)
    yield 300
    out["pulse"] = [win._audio_timer.isActive(), bar.label_style.audio_phase is not None,
                    bar.tabText(0).startswith("🔊 ")]
    a.page().recentlyAudible = lambda: False
    win._tab_changed(a)
    yield 100
    out["pulse_end"] = [win._audio_timer.isActive(), bar.label_style.audio_phase]
    yield 300
    out["rest"] = running(win)
'''


def test_horizontal_tabs(run_ike):
    out = run_ike(HORIZONTAL, env={"IKE_REDUCED_MOTION": "0"}, timeout=120)
    assert out["current"] == 2
    assert out["mid"] == [0, True, True]                 # on its way from the third tab to the first
    assert out["end"] == [False, True, True]
    tab_w, chars, data, cap = out["long_width"]
    assert chars == 27 and data == "cut" and tab_w <= cap     # held to its width: the end of the title fades
    assert out["no_dots"] and out["faded"]
    assert out["icon_fading"] and out["icon_end"] == [False, True]
    assert out["pulse"] == [True, True, True]
    assert out["pulse_end"] == [False, None]
    assert out["rest"] == []


VERTICAL = COMMON + r'''
def steps(ike, qapp, out):
    win = ike.windows[0]
    win.resize(1200, 800)
    yield 600
    first = win.current_view()
    page(first, LONG)
    second = win.add_tab("ike:newtab")
    yield 30
    d = win.vtabs.itemDelegate()
    row = win.views.index(second)
    out["enter"] = row in d._enter
    yield 400
    out["enter_end"] = row in d._enter
    yield 800
    vp = win.vtabs.viewport()
    rect0 = win.vtabs.visualItemRect(win.vtabs.item(0))
    # the mouse over the first row: its hover colour comes in softly, and goes
    QTest.mouseMove(vp, rect0.center())
    yield 30
    out["hover"] = 0 in d._levels
    yield 300
    out["hover_end"] = 0 in d._levels
    QTest.mouseMove(vp, QPoint(rect0.center().x(), vp.height() - 5))
    yield 30
    out["leave"] = 0 in d._levels
    yield 400
    # a real click on the first row: the bar on its left glides there
    QTest.mouseClick(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, rect0.center())
    yield 40
    out["mark_mid"] = [win.vtabs.currentRow(), win.vtabs.mark.gliding]
    yield 400
    vp.repaint()
    t = win.vtabs.mark.target()
    out["mark_end"] = [win.vtabs.mark.gliding, abs(win.vtabs.mark._shown.y() - t.y()) < 0.5,
                       rect0.top() <= t.y() <= rect0.bottom()]
    yield 300
    out["rest"] = running(win)
'''


def test_vertical_tabs(run_ike):
    out = run_ike(VERTICAL, settings={"tabs_position": "vertical"}, env={"IKE_REDUCED_MOTION": "0"}, timeout=120)
    assert out["enter"] is True and out["enter_end"] is False
    assert out["hover"] is True and out["hover_end"] is False and out["leave"] is True
    assert out["mark_mid"] == [0, True]
    assert out["mark_end"] == [False, True, True]
    assert out["rest"] == []


FIELD = COMMON + r'''
SITE = "__SITE__"

def steps(ike, qapp, out):
    from PyQt6.QtGui import QPalette
    from PyQt6.QtWidgets import QToolButton
    win = ike.windows[0]
    win.resize(1200, 800)
    win.show()
    win.activateWindow()
    yield 800
    url = win.urlbar
    # the address field is the system's own again (1.1.6): a frame, an opaque background
    out["pill"] = [url.hasFrame(), url.palette().color(QPalette.ColorRole.Base).alpha(), url._pill]
    QTest.mouseClick(url, Qt.MouseButton.LeftButton)
    yield 40
    out["focus_mid"] = [url.hasFocus()]
    yield 300
    # the suggestions: taller rows with an icon
    ike.storage.add_visit("https://example.org/page", "Example")
    QTest.keyClicks(url, "exam")
    yield 900
    popup = url._completer.popup()
    out["popup"] = [popup.isVisible(), type(popup.itemDelegate()).__name__]
    if popup.isVisible() and popup.model().rowCount():
        idx = popup.model().index(0, 0)
        out["row"] = popup.sizeHintForRow(0)
        from PyQt6.QtWidgets import QStyleOptionViewItem
        opt = QStyleOptionViewItem()
        popup.itemDelegate().initStyleOption(opt, idx)
        out["row_icon"] = not opt.icon.isNull()
    QTest.keyClick(popup if popup.isVisible() else url, Qt.Key.Key_Escape)      # the list closes
    yield 100
    out["field_kept"] = [popup.isVisible()]
    url.clearFocus()
    yield 400
    # the zoom sign: shown away from the usual zoom; a real click on it brings the page back
    out["zoom_rest"] = url.zoom_act.isVisible()
    win.zoom(+1)
    yield 100
    out["zoom_away"] = url.zoom_act.isVisible()
    btn = [b for b in url.findChildren(QToolButton) if b.defaultAction() is url.zoom_act]
    out["zoom_button"] = len(btn)
    if btn:
        QTest.mouseClick(btn[0], Qt.MouseButton.LeftButton)
    yield 200
    out["zoom_back"] = [round(win.current_view().zoomFactor(), 2), url.zoom_act.isVisible()]
    # Reload becomes Stop with a short fade, and back
    view = win.current_view()
    view.load(QUrl(SITE + "/slow"))
    for _ in range(100):
        if win.act_reload.text() == "Stop":
            break
        yield 10
    out["stop"] = [win.act_reload.text(), "reload" in win.__dict__.get("_ike_icon_fades", {})]
    for _ in range(40):
        if not view.loading:
            break
        yield 100
    yield 300
    out["reload"] = win.act_reload.text()
    # Ctrl+F: the find bar fades in
    QTest.keyClick(win.current_view().focusProxy() or win, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
    yield 40
    out["find_mid"] = [win.findbar.isVisible(), win.findbar.graphicsEffect() is not None]
    yield 300
    out["find_end"] = [win.findbar.isVisible(), win.findbar.graphicsEffect() is None]
    win.findbar.close_bar()
    # a finished download: the tick comes in with a pop
    win.show_download_progress("active", 0.5)
    win.show_download_progress("done")
    yield 40
    out["pop"] = win._dl_pop.state() == QAbstractAnimation.State.Running
    yield 500
    img = win.act_downloads.icon().pixmap(32, 32).toImage()
    out["tick"] = sum(1 for x in range(32) for y in range(32)
                      if QColor(img.pixel(x, y)).green() > 140 and QColor(img.pixel(x, y)).red() < 90)
    win.show_download_progress("idle")
    # the tab preview: from one tab to the next the picture blends
    from ike.tabpreview import TabPreview
    prev = TabPreview(win)
    pa, pb = QPixmap(240, 120), QPixmap(240, 120)
    pa.fill(QColor("#ff0000"))
    pb.fill(QColor("#0000ff"))
    prev.show_for(0, pa, "a", win.mapToGlobal(QPoint(50, 50)))
    yield 200
    prev.show_for(1, pb, "b", win.mapToGlobal(QPoint(90, 50)))
    yield 30
    out["preview_blend"] = prev._blend.state() == QAbstractAnimation.State.Running
    yield 300
    c = QColor(prev.picture.pixmap().toImage().pixel(10, 10))
    out["preview_end"] = [c.blue() > 200, c.red() < 50]
    prev.hide_preview()
    # the new tab page fades in and its tiles lift, with the effects on
    view.load(QUrl("ike:newtab"))
    yield 1200
    box = {}
    view.page().runJavaScript("document.body.className", lambda r: box.setdefault("c", r))
    yield 300
    out["newtab_class"] = box.get("c")
    yield 300
    out["rest"] = running(win)
'''


def test_address_field_toolbar_and_bars(run_ike, slow_site):  # noqa: F811
    out = run_ike(FIELD.replace("__SITE__", slow_site), env={"IKE_REDUCED_MOTION": "0"}, timeout=150)
    assert out["pill"] == [True, 255, None]
    assert out["focus_mid"] == [True]
    assert out["popup"] == [True, "SuggestionDelegate"]
    assert out["row"] >= 30 and out["row_icon"] is True
    assert out["field_kept"][0] is False
    assert out["zoom_rest"] is False and out["zoom_away"] is True and out["zoom_button"] == 1
    assert out["zoom_back"] == [1.0, False]
    assert out["stop"] == ["Stop", True] and out["reload"] == "Reload"
    assert out["find_mid"] == [True, True] and out["find_end"] == [True, True]
    assert out["pop"] is True and out["tick"] > 5
    assert out["preview_blend"] is True and out["preview_end"] == [True, True]
    assert out["newtab_class"] == "fx"
    assert out["rest"] == []


WITHOUT = COMMON + r'''
def steps(ike, qapp, out):
    win = ike.windows[0]
    yield 600
    a = win.current_view()
    win.add_tab("ike:newtab")
    yield 600
    bar = win.tabbar
    QTest.mouseClick(bar, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, bar.tabRect(0).center())
    yield 30
    out["glide"] = bar.mark.gliding
    win._icon_changed(a, red_icon())
    out["icon"] = [id(a) in win.__dict__.get("_ike_icon_fades", {}), reddish(bar.tabIcon(0))]
    win.urlbar.setFocus()
    yield 30
    win.findbar.open_bar()
    out["find"] = win.findbar.graphicsEffect() is None
    a.page().recentlyAudible = lambda: True
    win._tab_changed(a)
    out["pulse"] = getattr(win, "_audio_timer", None) is not None and win._audio_timer.isActive()
    win.show_download_progress("active", 0.5)
    win.show_download_progress("done")
    out["pop"] = getattr(win, "_dl_pop", None) is not None
    out["shield_pulse"] = win.shield_pulse.fire()
    a.load(QUrl("ike:newtab"))
    yield 1200
    box = {}
    a.page().runJavaScript("document.body.className", lambda r: box.setdefault("c", r))
    yield 300
    out["newtab_class"] = box.get("c")
    out["rest"] = running(win)
'''


@pytest.mark.parametrize("how", ["setting-off", "reduced-motion"])
def test_everything_at_once_without_effects(run_ike, how):
    out = run_ike(WITHOUT, settings={"ui_effects": how != "setting-off"},
                  env={"IKE_REDUCED_MOTION": "1" if how == "reduced-motion" else "0"}, timeout=120)
    assert out["glide"] is False
    assert out["icon"] == [False, True]
    assert out["find"] is True
    assert out["pulse"] is False and out["pop"] is False and out["shield_pulse"] is False
    assert out["newtab_class"] == ""
    assert out["rest"] == []


# --- 1.1.5: shield, downloads, suggestions, reader mode -----------------------------

ARTICLE = ("<!doctype html><title>An article</title><body><nav>menu</nav><article><h1>An article</h1>"
           + "".join("<p>%s</p>" % ("Words of a long article that goes on and on. " * 12) for _ in range(12))
           + "</article><img src='http://ads.example.test/banner.png'></body>")


@pytest.fixture
def pages():
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.startswith("/file.pdf"):
                body, kind = b"%PDF-1.4 test\n" * 200, "application/pdf"
            else:
                body, kind = ARTICLE.encode(), "text/html"
            self.send_response(200)
            self.send_header("Content-Type", kind)
            if kind == "application/pdf":
                self.send_header("Content-Disposition", "attachment; filename=file.pdf")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield "http://127.0.0.1:%d" % srv.server_address[1]
    srv.shutdown()


SHIELD_READER = JS + COMMON + r'''
SITE = "__SITE__"

def steps(ike, qapp, out):
    from PyQt6.QtGui import QIcon, QPixmap
    win = ike.windows[0]
    win.resize(1200, 800)
    win.show()
    view = win.current_view()
    yield from load(view, SITE + "/article")
    yield 1200
    # one more advert once the page is in view: a block that comes while the
    # tab still shows the address it is leaving cannot open the ring
    view.page().runJavaScript("new Image().src = 'http://ads.example.test/late.png'; 1")
    yield 1200
    # the page asked for an ad: the shield blocked it and its ring opened once
    out["pulse"] = [win.shield_pulse.fired, ike.shields.site_stats("127.0.0.1")["ads"]]
    win.shield_pulse.fire()
    out["pulse_again"] = win.shield_pulse.fire()          # at once again: no, it rests a moment
    # the shield panel shows the bars by kind
    win.shield_menu.popup(win.shield_btn.mapToGlobal(win.shield_btn.rect().bottomLeft()))
    yield 400
    kinds = win.shield_panel.kinds
    out["bars"] = [kinds.isVisible(), [n for _l, n in kinds.rows][:1], kinds.height() > 0]
    win.shield_menu.hide()
    # a search suggestion shows the search engine's own icon, once it is known
    pm = QPixmap(16, 16)
    pm.fill(QColor("#123456"))
    engine_url = ike.config.engine()["url"].replace("{q}", "")
    ike.favicons.store(engine_url, QIcon(pm))
    ic = win.urlbar._icon_for("some words to search")
    out["engine_icon"] = QColor(ic.pixmap(16, 16).toImage().pixel(8, 8)).name()
    # reader mode: light, sepia or dark and the text size, remembered
    win.toggle_reader()
    yield 800
    out["reader"] = json.loads((yield from js(view, "JSON.stringify({tools: document.querySelectorAll('.ike-tools button').length, "
        "meta: (document.querySelector('.ike-meta') || {}).textContent || ''})")))
    yield from js(view, "document.querySelectorAll('.ike-tools button')[3].click(); "
                        "document.querySelectorAll('.ike-tools button')[1].click(); 1")
    yield 400
    theme = yield from js(view, "document.documentElement.getAttribute('data-theme')")
    out["reader_after"] = [theme]
    out["saved"] = [ike.config["reader_theme"], ike.config["reader_size"]]
    # a page cannot change the reader settings with a console message of its own
    yield from js(view, "console.log('\\u0001ike-reader:' + 'x:' + JSON.stringify({theme: 'dark', size: 28})); 1")
    yield 200
    out["not_changed"] = [ike.config["reader_theme"], ike.config["reader_size"]]
    # a download: the file's icon and a bar under its size
    view.page().download(QUrl(SITE + "/file.pdf"))
    for _ in range(30):
        yield 200
        if ike.downloads and ike.downloads[0].isFinished():
            break
    dlg = ike.show_downloads()
    yield 800
    from ike.polish import FRACTION_ROLE
    item = dlg.tree.topLevelItem(0)
    out["download"] = [item is not None and item.data(1, FRACTION_ROLE), item is not None and not item.icon(0).isNull(),
                       dlg.tree.visualItemRect(item).height() if item is not None else 0]
    dlg.close()
'''


def test_shield_downloads_suggestions_and_reader(run_ike, pages, tmp_path):
    out = run_ike(SHIELD_READER.replace("__SITE__", pages), env={"IKE_REDUCED_MOTION": "0"},
                  settings={"download_dir": str(tmp_path / "dl"), "ask_download_location": False}, timeout=150)
    fired, ads = out["pulse"]
    assert ads >= 1 and fired >= 1 and out["pulse_again"] is False
    assert out["bars"][0] is True and out["bars"][1][0] >= 1 and out["bars"][2] is True
    assert out["engine_icon"] == "#123456"
    assert out["reader"]["tools"] == 5 and "min read" in out["reader"]["meta"]
    assert out["reader_after"] == ["sepia"]
    assert out["saved"] == ["sepia", 20]
    assert out["not_changed"] == ["sepia", 20]
    assert out["download"][0] == 1.0 and out["download"][1] is True and out["download"][2] >= 34


# --- 1.1.6: toolbar, window buttons, address bar ---------------------------------

WINDOW_116 = JS + COMMON + r'''
SITE = "__SITE__"

def steps(ike, qapp, out):
    import os
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QEnterEvent
    from PyQt6.QtWidgets import QApplication, QToolButton
    from ike import icons
    win = ike.windows[0]
    win.showNormal()
    win.resize(1300, 800)
    yield 500
    out["icon_size"] = win.nav.iconSize().width()
    out["smooth"] = "--enable-smooth-scrolling" in os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "").split()
    out["sets"] = [k for k, _l in icons.SETS]
    out["order"] = list(ike.config["toolbar_order"])
    # the maximize button: the arrow in a window of its own size, the diamond when maximized
    b = win._max_btn
    out["normal"] = [b.toolTip(), b.icon().name()]
    win.showMaximized()
    yield 500
    out["maximized"] = [b.toolTip(), b.icon().name()]
    win.showNormal()
    yield 500
    out["normal_again"] = b.toolTip()
    # its soft circle under the mouse
    centre = QPointF(b.width() / 2, b.height() / 2)
    QApplication.sendEvent(b, QEnterEvent(centre, centre, QPointF(b.mapToGlobal(centre.toPoint()))))
    yield 30
    out["hover_mid"] = b._glide.moving or 0 < b._glide.value < 1
    yield 300
    out["hover_end"] = b._glide.value
    # the line between the bars and the page
    edge = win.chrome_edge
    out["edge"] = [edge.isVisible(), edge.height(), edge.y() == win.content.y(), edge.width() == win.content.width()]
    view = win.current_view()
    # on the new tab page: no translation sign in the address bar
    out["translate_newtab"] = win.urlbar.translate_act.isVisible()
    yield from load(view, SITE + "/article")
    yield 800
    out["translate_site"] = win.urlbar.translate_act.isVisible()
    # the bookmark button of the toolbar: a real click
    btn = [w for w in win.nav.findChildren(QToolButton) if w.defaultAction() is win.act_tb_bookmark][0]
    QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
    yield 300
    out["bookmarked"] = [ike.storage.is_bookmarked(view.url().toString()), win.act_tb_bookmark.toolTip()]
    # the translation sign: a real click opens the page through the translation service
    tbtn = [w for w in win.urlbar.findChildren(QToolButton) if w.defaultAction() is win.urlbar.translate_act][0]
    QTest.mouseClick(tbtn, Qt.MouseButton.LeftButton)
    yield 1200
    out["translated"] = view.url().toString()
    # the arrow of the Downloads button moves while files arrive, and stops after
    win.show_download_progress("active", 0.3)
    yield 300
    out["arrow"] = win._dl_arrow.isActive()
    win.show_download_progress("done")
    yield 600
    out["arrow_end"] = win._dl_arrow.isActive()
    win.show_download_progress("idle")
'''


def test_toolbar_window_buttons_and_address_bar(run_ike, pages):
    out = run_ike(WINDOW_116.replace("__SITE__", pages), env={"IKE_REDUCED_MOTION": "0"},
                  settings={"system_titlebar": False, "start_maximized": False, "translate_confirmed": True,
                            "translate_url": pages + "/translated?u={url}",
                            "toolbar_order": ["shield", "reload", "translate", "reader", "downloads", "menu"]},
                  timeout=150)
    assert out["icon_size"] == 24 and out["smooth"] is True
    assert "phosphor-bold" in out["sets"]
    assert "translate" not in out["order"] and out["order"][:3] == ["shield", "reload", "bookmark"]
    assert out["normal"] == ["Maximize", "window-maximize"] or out["normal"][0] == "Maximize"
    assert out["maximized"][0] == "Restore"
    assert out["normal_again"] == "Maximize"
    assert out["hover_mid"] is True and out["hover_end"] == 1.0
    assert out["edge"] == [True, 1, True, True]
    assert out["translate_newtab"] is False and out["translate_site"] is True
    assert out["bookmarked"] == [True, "Remove bookmark"]
    assert out["translated"].startswith(pages + "/translated?u=")
    assert out["arrow"] is True and out["arrow_end"] is False


def test_bold_icon_set_is_complete():
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent / "ike/resources/icons/sets"
    fill = sorted(p.name for p in (root / "phosphor").glob("*.svg"))
    bold = sorted(p.name for p in (root / "phosphor-bold").glob("*.svg"))
    assert fill == bold and len(bold) > 50
    for name in bold:
        text = (root / "phosphor-bold" / name).read_text()
        assert text.startswith("<svg") and 'fill="currentColor"' in text and "<script" not in text


# --- 1.1.7: messages in a pill, find bar, shield number, panels, Settings, new tab page ------

TOUCHES_117 = JS + COMMON + r'''
SITE = "__SITE__"

def steps(ike, qapp, out):
    from PyQt6.QtWidgets import QLabel
    win = ike.windows[0]
    win.resize(1300, 800)
    win.show()
    yield 600
    out["urlbar_width"] = ike.config["urlbar_width"]
    view = win.current_view()
    # the new tab page: its two buttons, the clock at the bottom right, the logo
    out["newtab"] = json.loads((yield from js(view, "JSON.stringify({"
        "settings: !!document.querySelector('a.nt-settings[href^=\"ike:open?what=settings&k=\"]'), "
        "photo: !!document.querySelector('a.nt-photo[href^=\"ike:open?what=background&k=\"]'), "
        "corner: getComputedStyle(document.querySelector('.corner')).bottom, "
        "logo: !!document.querySelector('img.logo'), name: !!document.querySelector('h1 svg')})")))
    # a click on "Background photo": the Settings open at the new tab page's own page
    yield from js(view, "document.querySelector('a.nt-photo').click(); 1")
    yield 1200
    dlg = ike._dialogs.get("settings")
    out["photo_opens"] = bool(dlg is not None and dlg.isVisible()) and dlg.PAGES[dlg.stack.currentIndex()]
    # another page of the Settings: the old one fades away
    dlg.nav.setCurrentRow(0)
    yield 20
    out["settings_fade"] = bool(dlg.stack.findChildren(QLabel, "ike_theme_fade"))
    dlg.close()
    yield 300
    # a website cannot open the Settings
    yield from load(view, SITE + "/article")
    yield 1000
    view.page().runJavaScript("var i = new Image(); i.src = 'ike:open?what=settings'; "
                              "fetch('ike:open?what=settings').catch(function () {}); 1")
    yield 1000
    dlg = ike._dialogs.get("settings")
    out["site_opens"] = bool(dlg is not None and dlg.isVisible())
    # the shield: its number grew on this page, and a "+N" rose. One more
    # advert asked for once the shield shows the first one: with a single
    # block the shield could see it at once and have nothing to grow from.
    view.page().runJavaScript("new Image().src = 'http://ads.example.test/late.png'; 1")
    yield 1200
    out["count"] = [win.shield_btn.text(), win.shield_count.shown]
    # the "+N" starts right of the shield icon and of the number, never over the icon
    out["plus_left"] = [win.shield_count.text_left(), win.shield_btn.iconSize().width()]
    # the shield panel and the site panel show the site's icon
    win.shield_menu.popup(win.shield_btn.mapToGlobal(win.shield_btn.rect().bottomLeft()))
    yield 300
    out["shield_icon"] = win.shield_panel.site_icon.isVisible()
    win.shield_menu.hide()
    win.show_site_info()
    yield 300
    out["info_icon"] = win.site_info.site_icon.isVisible()
    win.site_info_menu.hide()
    # messages in a pill over the page, not in the status bar
    win.zoom(1)
    yield 200
    pill = win.toast_pill
    out["zoom_pill"] = [pill.isVisible(), pill.text, win.statusBar().isVisible()]
    yield 2200
    out["zoom_gone"] = pill.isVisible()
    win.zoom(0)
    ike._notify("A note")
    yield 200
    out["note"] = [pill.isVisible(), pill.text]
    # the find bar: "N of M" in a pill, the field tinted when nothing is found
    win.findbar.open_bar()
    QTest.keyClicks(win.findbar.edit, "zzqqxx")
    yield 600
    out["nothing"] = [win.findbar.info.text(), win.findbar.edit.property("nothing_found")]
    win.findbar.edit.clear()
    QTest.keyClicks(win.findbar.edit, "article")
    yield 600
    out["found"] = [win.findbar.info.text(), win.findbar.edit.property("nothing_found")]
    win.findbar.close_bar()
'''


def test_touches_of_117(run_ike, pages):
    out = run_ike(TOUCHES_117.replace("__SITE__", pages), env={"IKE_REDUCED_MOTION": "0"},
                  settings={"urlbar_width": 60}, timeout=150)
    assert out["urlbar_width"] == 50                     # the old 60 becomes half of the window
    nt = out["newtab"]
    assert nt["settings"] and nt["photo"] and nt["logo"] and nt["name"] and nt["corner"] == "22px"
    assert out["photo_opens"] == "newtab" and out["settings_fade"] is True
    assert out["site_opens"] is False
    assert out["count"][0] and int(out["count"][0]) >= 1 and out["count"][1] >= 1
    assert out["plus_left"][0] > out["plus_left"][1] + 8
    assert out["shield_icon"] is True and out["info_icon"] is True
    assert out["zoom_pill"] == [True, "Zoom: 110%", False] and out["zoom_gone"] is False
    assert out["note"] == [True, "A note"]
    assert out["nothing"] == ["0 of 0", True]
    assert out["found"][0].endswith("of %s" % out["found"][0].split(" of ")[1]) and out["found"][1] is False
    assert out["found"][0] != "0 of 0"
