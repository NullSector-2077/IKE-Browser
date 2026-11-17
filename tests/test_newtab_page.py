"""The new tab page of 1.1.0: the counter per month and the site tiles (the
suggestion of the Cyber theme went with the theme in 1.1.2). Titles and addresses shown on the page come
from outside, so the hostile cases are tested here too (on this computer only)."""

import sys
import time

from conftest import ROOT
from test_security import JS

sys.path.insert(0, str(ROOT))


class Cfg:
    def __init__(self, **data):
        self.data = {"blocked_total": 0, "blocked_month": {}, "blocked_counter": "month"}
        self.data.update(data)

    def __getitem__(self, key):
        return self.data[key]


def at(year, month, day=15):
    return time.mktime((year, month, day, 12, 0, 0, 0, 0, -1))


def test_the_counter_starts_again_each_month():
    from ike import newtab

    cfg = Cfg(blocked_total=1000)                       # an installation that counted before 1.1.0
    for _ in range(5):
        newtab.count_blocked(cfg, at(2026, 11))
    assert cfg["blocked_total"] == 1005                 # the total goes on, nothing is reset
    assert cfg["blocked_month"] == {"key": "2026-11", "count": 5, "prev_key": "", "prev": 0}

    newtab.count_blocked(cfg, at(2026, 11, 30))
    newtab.count_blocked(cfg, at(2026, 12, 1))          # the first of the month
    assert cfg["blocked_month"] == {"key": "2026-12", "count": 1, "prev_key": "2026-11", "prev": 6}
    assert cfg["blocked_total"] == 1007

    newtab.roll(cfg, at(2027, 1, 2))                    # a new year, nothing blocked yet
    assert cfg["blocked_month"] == {"key": "2027-01", "count": 0, "prev_key": "2026-12", "prev": 1}

    newtab.roll(cfg, at(2027, 6))                       # the browser was not used for months:
    assert cfg["blocked_month"] == {"key": "2027-06", "count": 0, "prev_key": "", "prev": 0}

    newtab.roll(cfg, at(2027, 5))                       # the clock of the computer set back
    assert cfg["blocked_month"]["key"] == "2027-05" and cfg["blocked_month"]["count"] == 0


def test_a_damaged_month_record_does_not_stop_the_count():
    from ike import newtab

    for bad in (None, [], "x", {"key": 7, "count": "many"}, {"key": "2026-11", "count": -3, "prev": True},
                {"key": "2026-11", "count": 2.5}):
        cfg = Cfg(blocked_month=bad)
        newtab.count_blocked(cfg, at(2026, 11))
        assert cfg["blocked_month"]["key"] == "2026-11" and cfg["blocked_month"]["count"] == 1, bad


def test_what_the_counter_shows():
    from ike import newtab

    cfg = Cfg(blocked_total=40000, blocked_month={"key": "2026-11", "count": 12480,
                                                  "prev_key": "2026-10", "prev": 21906})
    page = newtab.stats_html(cfg, "Protection level", "Balanced", at(2026, 11))
    assert "12.480" in page and "21.906" in page and "40.000" not in page
    cfg.data["blocked_counter"] = "total"
    page = newtab.stats_html(cfg, "Protection level", "Balanced", at(2026, 11))
    assert "40.000" in page and "12.480" not in page
    # the level's name is text, never markup
    assert "<script>" not in newtab.stats_html(cfg, "<script>x</script>", "<script>y</script>", at(2026, 11))


def test_only_web_addresses_become_tiles():
    from ike import newtab

    good = {"example.org": "https://example.org", "http://a.example/x?y=1": "http://a.example/x?y=1",
            "  https://b.example/  ": "https://b.example/"}
    for text, address in good.items():
        assert newtab.web_address(text) == address
    for text in ("", "javascript:alert(1)", "data:text/html,x", "file:///etc/passwd", "ike:newtab",
                 "https://", "https://a b.example", 'https://x.example/"onmouseover="1', "https://x.example/<b>",
                 "vbscript:x", "https://" + "a" * 3000 + ".example"):
        assert newtab.web_address(text) == "", text


def test_tiles_from_bookmarks_and_from_history(run_ike):
    out = run_ike(JS + r'''
def steps(ike, qapp, out):
    from PyQt6.QtCore import QUrl
    win = ike.windows[0]
    view = win.current_view()
    st = ike.storage
    st.add_bookmark("https://example.org/a", "First <img src=x onerror=window.pwned=1>")
    st.add_bookmark("javascript:window.pwned=2", "Not a site")
    st.add_bookmark("https://wiki.example.net/", "")
    st.add_bookmark('https://evil.example/"><script>window.pwned=3</script>', "Quote")
    for i in range(40):
        st.add_bookmark("https://many%d.example/" % i, "Many %d" % i)
    for url, n in (("https://often.example/page", 9), ("https://www.often.example/other", 3),
                   ("https://seldom.example/", 1), ("http://plain.example/x", 5)):
        for _ in range(n):
            st.add_visit(url, "t")
    read = """JSON.stringify({pwned: window.pwned || 0,
        links: Array.from(document.querySelectorAll('.tile > a:first-child')).map(function (a) { return a.getAttribute('href'); }),
        names: Array.from(document.querySelectorAll('.tile .name')).map(function (n) { return n.textContent; }),
        imgs: document.querySelectorAll('.tile .name img, .tile .name script').length,
        add: !!document.querySelector('.tile.add'),
        row: (function () { var t = document.querySelectorAll('.tile'); if (!t.length) return 0;
            var top = t[0].offsetTop, n = 0; t.forEach(function (x) { if (x.offsetTop === top) n++; }); return n; })()})"""
    ike.windows[0].resize(1800, 1000)        # a wide window, as on a 1440p screen
    yield from load(view, "ike:newtab")
    yield 400
    out["bookmarks"] = json.loads((yield from js(view, read)))

    # hide the first tile, as its small cross does: the bookmark stays
    yield from js(view, "document.querySelector('.tile .hide').click(); 1")
    yield 1200
    out["after_hide"] = json.loads((yield from js(view, read)))
    out["still_bookmarked"] = st.is_bookmarked("https://example.org/a")
    out["url_after_hide"] = view.url().toString()

    # add one with the "Add" tile itself: a click opens the field, the address is typed, Enter sends it
    out["add_closed"] = yield from js(view, "getComputedStyle(document.querySelector('.tile.add input')).display")
    yield from js(view, "document.querySelector('.tile.add .open').click(); 1")
    yield 200
    out["add_open"] = json.loads((yield from js(view, """JSON.stringify([
        getComputedStyle(document.querySelector('.tile.add input')).display,
        document.activeElement === document.querySelector('.tile.add input'),
        document.querySelector('.tile.add .open').getAttribute('aria-expanded')])""")))
    yield from js(view, """var f = document.querySelector('.tile.add input'); f.value = 'clicked.example';
        document.querySelector('.tile.add').requestSubmit(); 1""")
    yield 1200
    out["added_by_click"] = [st.is_bookmarked("https://clicked.example"), view.url().toString(),
                             (yield from js(view, "Array.from(document.querySelectorAll('.tile .name')).map(function (n) { return n.textContent; }).indexOf('clicked.example') >= 0"))]
    # an empty field sends nothing, and Escape closes it
    yield from js(view, "document.querySelector('.tile.add .open').click(); document.querySelector('.tile.add').requestSubmit(); 1")
    yield 400
    out["empty"] = view.url().toString()
    yield from js(view, "document.querySelector('.tile.add input').dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true})); 1")
    out["escaped"] = yield from js(view, "getComputedStyle(document.querySelector('.tile.add input')).display")
    # the address the tile sends, directly
    yield from load(view, "ike:tile?add=new.example")
    yield 300
    out["added"] = [st.is_bookmarked("https://new.example"), view.url().toString()]
    out["first_tiles"] = json.loads((yield from js(view, read)))["links"][:2]
    yield from load(view, "ike:tile?add=" + "javascript%3Aalert(1)")
    out["not_added"] = [u for u, _t, _f in st.bookmarks() if u.startswith("javascript:alert")]

    ike.config["newtab_tiles"] = "visited"
    yield from load(view, "ike:newtab")
    yield 400
    out["visited"] = json.loads((yield from js(view, read)))
    ike.config["newtab_tiles"] = "none"
    yield from load(view, "ike:newtab")
    out["none"] = json.loads((yield from js(view, read)))
''', timeout=180)
    b = out["bookmarks"]
    assert b["pwned"] == 0 and b["imgs"] == 0
    assert b["links"][:2] == ["https://example.org/a", "https://wiki.example.net/"]
    assert all(link.startswith("https://") for link in b["links"]) and len(b["links"]) == 32    # never more
    assert b["row"] >= 16                    # a wide window: sixteen tiles side by side
    assert b["names"][0].startswith("First <img") and b["names"][1] == "wiki.example.net"
    assert b["add"] is True
    assert out["after_hide"]["links"][0] == "https://wiki.example.net/" and out["still_bookmarked"] is True
    assert out["url_after_hide"] == "ike:newtab"
    assert out["add_closed"] == "none" and out["add_open"] == ["block", True, "true"]
    assert out["added_by_click"] == [True, "ike:newtab", True]
    assert out["empty"] == "ike:newtab" and out["escaped"] == "none"
    assert out["added"] == [True, "ike:newtab"] and out["not_added"] == []
    # with more bookmarks than tiles, the sites added from the page are still shown: first, the newest first
    assert out["first_tiles"] == ["https://new.example", "https://clicked.example"]
    v = out["visited"]
    assert v["links"][:2] == ["https://often.example/", "http://plain.example/"]       # by visits, one per site
    assert v["names"][:3] == ["often.example", "plain.example", "seldom.example"] and v["add"] is False
    assert out["none"]["links"] == [] and out["none"]["add"] is False


def test_a_web_page_cannot_answer_for_the_user(run_ike):
    """Hiding a tile or adding a bookmark are answers of the new tab page
    itself: a site that links, frames or loads those addresses changes
    nothing (nor do the addresses of the Cyber suggestion, gone in 1.1.2)."""
    out = run_ike(JS + r'''
def steps(ike, qapp, out):
    from PyQt6.QtCore import QUrl
    view = ike.windows[0].current_view()
    ike.storage.add_bookmark("https://example.org/a", "First")
    page = """<body><img src="ike:tile?hide=https%3A%2F%2Fexample.org%2Fa">
        <iframe src="ike:theme?try=cyber"></iframe><iframe src="ike:tile?add=evil.example"></iframe>
        <form id=f action="ike:tile" method="get"><input name="add" value="form.example"></form>
        <script>fetch('ike:theme?try=cyber').catch(function () {});
        setTimeout(function () { document.getElementById('f').submit(); }, 300);</script>"""
    view.setHtml(page, QUrl("http://site.example/"))
    yield 2000
    view.setHtml("<script>location.href = 'ike:theme?try=cyber';</script>", QUrl("http://site.example/2"))
    yield 1500
    out["scheme"] = ike.config["ui_scheme"]
    out["hidden"] = ike.config["newtab_tiles_hidden"]
    out["bookmarks"] = sorted(u for u, _t, _f in ike.storage.bookmarks())
''', timeout=120)
    assert out["scheme"] == "system"
    assert out["hidden"] == [] and out["bookmarks"] == ["https://example.org/a"]


def test_the_cyber_theme_is_gone_and_its_users_follow_the_system(run_ike):
    """1.1.2 removed the Cyber theme. Whoever had it chosen starts with "Follow
    the system", its settings leave settings.json, nothing is left of it on the
    new tab page, in the windows or in Settings, and its old addresses do nothing."""
    out = run_ike(JS + r'''
def steps(ike, qapp, out):
    import pathlib
    from ike import themes
    win = ike.windows[0]
    view = win.current_view()
    out["scheme"] = ike.config["ui_scheme"]
    out["left"] = sorted(k for k in ike.config.data if k.startswith("cyber_") or k == "newtab_grid")
    out["themes"] = [k for k, _label in themes.names()]
    out["nav_sheet"] = win.nav.styleSheet()
    out["tab_style"] = type(win.tabbar.style()).__name__
    yield from load(view, "ike:newtab")
    out["class"] = yield from js(view, "document.body.className")
    out["hint"] = yield from js(view, "!!document.querySelector('.hint')")
    out["tiles"] = yield from js(view, "!!document.querySelector('.tile.add')")
    yield from load(view, "ike:theme?try=cyber")
    out["after_try"] = ike.config["ui_scheme"]
    ike.config.save()
    stored = json.loads(pathlib.Path(ike.config.path).read_text("utf-8"))
    out["stored"] = sorted(k for k in stored if k.startswith("cyber_") or k == "newtab_grid")
    dlg = ike.show_settings(win)
    yield 300
    out["choices"] = [dlg.ui_scheme.itemData(i) for i in range(dlg.ui_scheme.count())]
    out["choice"] = dlg.ui_scheme.currentData()
    dlg.close()
''', settings={"ui_scheme": "theme:cyber", "cyber_hint": "trial", "cyber_accent": "#ff5fa8",
               "cyber_shape": "lama", "cyber_glow": True, "cyber_corners": True, "newtab_grid": True},
       timeout=120)
    assert out["scheme"] == "system" and out["after_try"] == "system"
    assert out["left"] == [] and out["stored"] == []
    assert "cyber" not in out["themes"] and "ike" in out["themes"]
    assert out["nav_sheet"] == "" and out["tab_style"] != "TabStyle"
    assert "cyber" not in out["class"] and out["hint"] is False and out["tiles"] is True
    assert "theme:cyber" not in out["choices"] and out["choice"] == "system"


def test_counting_does_not_look_at_the_calendar_each_time():
    """The quick way taken for every blocked request gives the same figures,
    and gives way as soon as the month, or the record, is not the expected one."""
    from ike import newtab

    cfg = Cfg()
    for _ in range(50):
        newtab.count_blocked(cfg)
    key = newtab.month_key()
    assert cfg["blocked_month"]["key"] == key and cfg["blocked_month"]["count"] == 50 and cfg["blocked_total"] == 50
    assert newtab._known[1] == key and newtab._known[0] > time.time()
    cfg.data["blocked_month"] = "damaged"                  # the record replaced behind its back
    newtab.count_blocked(cfg)
    assert cfg["blocked_month"]["count"] == 1
    cfg.data["blocked_month"] = {"key": "2001-01", "count": 7, "prev_key": "", "prev": 0}      # an old month
    newtab.count_blocked(cfg)
    assert cfg["blocked_month"]["key"] == key and cfg["blocked_month"]["count"] == 1
    newtab._known[0] = 0.0                                 # the first of the month has come
    newtab.count_blocked(cfg)
    assert cfg["blocked_month"]["count"] == 2
