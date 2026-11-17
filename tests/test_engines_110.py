"""1.1.10: the search engine picker, in the address bar (right after the lock)
and in the new tab page's search box, with real clicks and keys: the default
engine's own icon, the list of the installed engines with theirs, the one
chosen becomes the default everywhere; a web page cannot choose one."""

from test_security import JS

HELPERS = JS + r'''
from PyQt6.QtCore import QCoreApplication, QEvent, QPoint, QPointF, Qt, QUrl
from PyQt6.QtGui import QColor, QIcon, QMouseEvent, QPixmap
from PyQt6.QtTest import QTest

def page_click(v, x, y):
    t = v.focusProxy() or v
    for et, b in ((QEvent.Type.MouseButtonPress, Qt.MouseButton.LeftButton),
                  (QEvent.Type.MouseButtonRelease, Qt.MouseButton.NoButton)):
        QCoreApplication.sendEvent(t, QMouseEvent(et, QPointF(x, y), QPointF(x, y), Qt.MouseButton.LeftButton,
                                                  b, Qt.KeyboardModifier.NoModifier))

def centre_of(v, sel):
    r = yield from js(v, "(function(){var e=document.querySelector(%s); if(!e) return null;"
                         "var r=e.getBoundingClientRect(); return [r.left+r.width/2, r.top+r.height/2];})()"
                      % json.dumps(sel))
    return r

def red_icon():
    pm = QPixmap(32, 32)
    pm.fill(QColor(220, 20, 20))
    return QIcon(pm)

def colour_of(icon):
    img = icon.pixmap(16, 16).toImage()
    c = QColor(img.pixel(8, 8))
    return [c.red(), c.green(), c.blue()]
'''


def test_engine_picker_in_the_address_bar(run_ike):
    out = run_ike(HELPERS + r'''
def steps(ike, qapp, out):
    yield 600
    win = ike.windows[0]
    win.resize(1400, 800)
    yield 400
    ub, eb = win.urlbar, win.engine_btn
    # an engine whose icon is known (as after its site was asked once): its own icon
    ike.favicons.store("https://www.mojeek.com/", red_icon())
    ike.favicons.store("https://duckduckgo.com/", red_icon())
    win.sync_engine()
    yield 100
    lock = [b for b in ub._icon_buttons() if b.defaultAction() is ub.lock][0]
    out["place"] = [eb.parentWidget() is ub, eb.x() - lock.geometry().right(), ub.textMargins().left(),
                    eb.geometry().right() < 60]
    out["icon"] = colour_of(eb.icon())
    out["tip"] = eb.toolTip()
    # a real click opens the list
    QTest.mouseClick(eb, Qt.MouseButton.LeftButton)
    for _ in range(20):
        if win.engine_menu.isVisible():
            break
        yield 50
    m = win.engine_menu
    acts = m.actions()
    out["open"] = m.isVisible()
    out["names"] = [a.text() for a in acts]
    out["checked"] = [a.text() for a in acts if a.isChecked()]
    out["icons"] = {a.text(): colour_of(a.icon()) for a in acts}
    out["no_icon_yet"] = [a.text() for a in acts if a.icon().isNull()]
    # a real click on Mojeek
    mo = [a for a in acts if a.text() == "Mojeek"][0]
    QTest.mouseClick(m, Qt.MouseButton.LeftButton, pos=m.actionGeometry(mo).center())
    yield 400
    out["after"] = [ike.config["default_engine"], m.isVisible(), colour_of(eb.icon()), eb.toolTip()]
    out["saved"] = json.loads(ike.config.path.read_text("utf-8"))["default_engine"]
    # a search typed in the address bar goes to the engine chosen
    out["search"] = ike.shields.search_url("hello")
    # the keyboard: the menu opens on Space with the button... it has no focus; Esc closes the list
    QTest.mouseClick(eb, Qt.MouseButton.LeftButton)
    yield 300
    QTest.keyClick(m, Qt.Key.Key_Escape)
    yield 300
    out["esc"] = [m.isVisible(), ike.config["default_engine"]]
    # the text: typed text starts after the engine button, and the shield is still at the end
    ub.setText("https://www.example.org/" + "x" * 300)
    ub.setCursorPosition(0)
    yield 100
    out["text_start"] = ub.cursorRect().left() >= eb.geometry().right() - 2
    out["shield_end"] = win.shield_btn.geometry().right() > ub.width() - 20
    # a narrow window: still after the lock, nothing on top of each other
    win.resize(640, 600)
    yield 600
    out["narrow"] = [eb.x() - lock.geometry().right(), eb.geometry().right() < win.shield_btn.x(),
                     eb.isVisible()]
''', timeout=120)
    assert out["place"][0] and 0 <= out["place"][1] <= 3 and out["place"][2] >= 20 and out["place"][3], out["place"]
    assert out["icon"][0] > 180 and out["icon"][1] < 60, out["icon"]          # DuckDuckGo's own icon (stored)
    assert "DuckDuckGo" in out["tip"]
    assert out["open"]
    assert out["names"][:3] == ["DuckDuckGo", "Startpage", "Brave Search"] and "Google" in out["names"]
    assert out["checked"] == ["DuckDuckGo"]
    assert out["icons"]["Mojeek"][0] > 180 and out["no_icon_yet"] == []       # unknown: a magnifier, never empty
    assert out["after"][0] == "Mojeek" and not out["after"][1] and out["after"][2][0] > 180, out["after"]
    assert "Mojeek" in out["after"][3] and out["saved"] == "Mojeek"
    assert out["search"].startswith("https://www.mojeek.com/search?q=hello")
    assert out["esc"] == [False, "Mojeek"]
    assert out["text_start"] and out["shield_end"]
    assert 0 <= out["narrow"][0] <= 3 and out["narrow"][1] and out["narrow"][2], out["narrow"]


def test_engine_picker_on_the_new_tab_page(run_ike):
    out = run_ike(HELPERS + r'''
def steps(ike, qapp, out):
    yield 500
    win = ike.windows[0]
    win.resize(1400, 900)
    view = win.current_view()
    ike.favicons.store("https://www.startpage.com/", red_icon())
    yield from load(view, "ike:newtab")
    yield 500
    read = """JSON.stringify({open: document.querySelector('.eng').classList.contains('on'),
        menu: getComputedStyle(document.querySelector('.eng-menu')).display,
        names: Array.from(document.querySelectorAll('.eng-menu .eng-name')).map(function (n) { return n.textContent; }),
        checked: Array.from(document.querySelectorAll('.eng-menu [aria-checked=true] .eng-name')).map(function (n) { return n.textContent; }),
        icon: (document.querySelector('.eng-btn img') || {}).src || '',
        shown: Array.from(document.querySelectorAll('.eng-menu img')).filter(function (i) { return i.complete && i.naturalWidth > 0; }).length,
        lens: document.querySelectorAll('.eng-menu .eng-ico svg').length,
        ph: document.querySelector('input[name=q]').placeholder,
        input: (function () { var i = document.querySelector('input[name=q]').getBoundingClientRect(),
                              b = document.querySelector('.eng-btn').getBoundingClientRect();
                              return [b.left > i.left, b.right < i.left + 70, b.top >= i.top - 1, b.bottom <= i.bottom + 1]; })()})"""
    out["closed"] = json.loads((yield from js(view, read)))
    # a real click on the engine button opens the list
    x, y = yield from centre_of(view, ".eng-btn")
    page_click(view, x, y)
    yield 500
    out["opened"] = json.loads((yield from js(view, read)))
    # the list is above the tiles: the point under the Startpage row is the row itself
    out["on_top"] = yield from js(view, """(function () { var a = document.querySelectorAll('.eng-menu a')[1],
        r = a.getBoundingClientRect(); return document.elementFromPoint(r.left + 20, r.top + r.height / 2).closest('a') === a; })()""")
    # a click elsewhere closes it, Esc too
    page_click(view, 30, 300)
    yield 300
    out["outside"] = json.loads((yield from js(view, read)))["open"]
    page_click(view, x, y)
    yield 300
    t = view.focusProxy() or view
    QTest.keyClick(t, Qt.Key.Key_Down)
    yield 100
    out["focus"] = yield from js(view, "document.activeElement.querySelector('.eng-name').textContent")
    QTest.keyClick(t, Qt.Key.Key_Escape)
    yield 300
    out["esc"] = json.loads((yield from js(view, read)))["open"]
    # a real click on Startpage: the default from now on, the page and the address bar show it
    page_click(view, x, y)
    yield 300
    sx, sy = yield from centre_of(view, ".eng-menu a:nth-child(2)")
    page_click(view, sx, sy)
    for _ in range(40):
        yield 100
        if ike.config["default_engine"] == "Startpage" and view.url().toString() == "ike:newtab" and not view.loading:
            break
    yield 800
    out["chosen"] = [ike.config["default_engine"], view.url().toString()]
    out["after"] = json.loads((yield from js(view, read)))
    out["bar"] = [win.engine_btn.toolTip(), colour_of(win.engine_btn.icon())]
    # a search from the page goes to the engine chosen
    out["search"] = ike.shields.search_url("hi")
    # an engine that is not installed changes nothing
    yield from load(view, "ike:engine?name=Nope")
    out["unknown"] = [ike.config["default_engine"], view.url().toString()]
''', timeout=150)
    c = out["closed"]
    assert not c["open"] and c["menu"] == "none" and all(c["input"]), c
    assert c["names"][:3] == ["DuckDuckGo", "Startpage", "Brave Search"] and c["checked"] == ["DuckDuckGo"]
    assert "ike:favicon?h=duckduckgo.com" in c["icon"] and c["lens"] == len(c["names"])
    o = out["opened"]
    assert o["open"] and o["menu"] == "block" and o["shown"] >= 1, o      # Startpage's own icon is shown
    assert out["on_top"] is True
    assert out["outside"] is False and out["esc"] is False
    assert out["focus"] in ("DuckDuckGo", "Startpage")
    assert out["chosen"] == ["Startpage", "ike:newtab"], out["chosen"]
    a = out["after"]
    assert a["checked"] == ["Startpage"] and "Startpage" in a["ph"] and "h=www.startpage.com" in a["icon"]
    assert "Startpage" in out["bar"][0] and out["bar"][1][0] > 180
    assert out["search"].startswith("https://www.startpage.com/")
    assert out["unknown"] == ["Startpage", "ike:newtab"]


def test_a_web_page_cannot_choose_the_engine(run_ike):
    out = run_ike(JS + r'''
def steps(ike, qapp, out):
    from PyQt6.QtCore import QUrl
    view = ike.windows[0].current_view()
    page = """<body><img src="ike:engine?name=Google"><iframe src="ike:engine?name=Google"></iframe>
        <script>fetch('ike:engine?name=Google').catch(function () {});</script>"""
    view.setHtml(page, QUrl("http://site.example/"))
    yield 1500
    view.setHtml("<script>location.href = 'ike:engine?name=Google';</script>", QUrl("http://site.example/2"))
    yield 1500
    out["engine"] = ike.config["default_engine"]
''', timeout=90)
    assert out["engine"] == "DuckDuckGo"
