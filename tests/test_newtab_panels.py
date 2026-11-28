"""1.1.31: the new tab page is customised from the new tab page itself (the owner): a gear beside the
corner (clock and weather) and one beside the counter open a small panel with the settings of that
part; a choice in it changes only that setting, the page comes back in place with the same panel
open. Only the page itself can do it (the session's key); a web page cannot. The names of the
favourite sites are in the text colour, readable in the light and the dark theme."""

import sys

from conftest import APP
from test_security import JS

sys.path.insert(0, str(APP))


class Cfg:
    def __init__(self, **data):
        self.data = data


def test_a_panel_changes_only_its_own_settings():
    from ike import newtab

    cfg = Cfg(newtab_clock=True, weather_unit="celsius", newtab_tiles_hidden=["https://a.example/"],
              default_engine="Startpage")
    assert newtab.set_from_panel(cfg, "newtab_clock", "0") and cfg.data["newtab_clock"] is False
    assert not newtab.set_from_panel(cfg, "newtab_clock", "0")                    # already so
    assert newtab.set_from_panel(cfg, "weather_unit", "fahrenheit") and cfg.data["weather_unit"] == "fahrenheit"
    assert newtab.set_from_panel(cfg, "newtab_tiles_hidden", "clear") and cfg.data["newtab_tiles_hidden"] == []
    for name, value in (("weather_unit", "kelvin"), ("newtab_clock", "true"), ("default_engine", "Google"),
                        ("shield_level", "0"), ("blocked_counter", ""), ("newtab_tiles", "evil"), ("", "")):
        before = dict(cfg.data)
        assert not newtab.set_from_panel(cfg, name, value), (name, value)
        assert cfg.data == before, (name, value)


def test_the_panels_html_holds_only_page_links():
    import re

    from ike import newtab
    cfg = Cfg(newtab_clock=True, newtab_weather=True, weather_city='Roma"<b>', weather_unit="celsius",
              weather_wind_unit="auto", weather_pressure_unit="hpa", blocked_counter="month",
              newtab_tiles="bookmarks", newtab_tiles_hidden=["x"])
    for which in ("corner", "stats"):
        text = newtab.panel_html(cfg, which, "<svg></svg>")
        links = re.findall(r'href="([^"]*)"', text)
        assert links and all(u.startswith(("ike:ntset?", "ike:open?what=newtab")) for u in links), links
        for u in links:
            if u.startswith("ike:ntset?"):
                q = dict(p.split("=", 1) for p in u.split("?", 1)[1].split("&amp;"))
                assert q["v"] in newtab.PANEL_SETTINGS[q["s"]] and q["p"] == which, u
        assert "<b>" not in text
    corner = newtab.panel_html(cfg, "corner", "")
    assert 'data-s="weather_pressure_unit" href="ike:ntset?s=weather_pressure_unit&amp;v=hpa&amp;p=corner"' in corner
    assert re.search(r'aria-checked="true" data-s="weather_pressure_unit" href="[^"]*v=hpa&amp;p=corner"', corner)
    assert 'data-s="newtab_clock" href="ike:ntset?s=newtab_clock&amp;v=0&amp;p=corner"' in corner    # on: the switch turns it off
    cfg.data["newtab_weather"] = False                  # no weather: no city and no units in its panel
    assert "weather_unit" not in newtab.panel_html(cfg, "corner", "")


STEPS = JS + r'''
def steps(ike, qapp, out):
    import time
    from PyQt6.QtCore import QUrl
    ike.config["weather_city"], ike.config["weather_lat"], ike.config["weather_lon"] = "Roma", 41.89, 12.51
    ike.weather.data = {"key": [41.89, 12.51, "celsius"], "time": time.time(), "temp": 12, "code": 2,
                        "wind": 14.4}
    ike.storage.add_bookmark("https://example.org/", "Example")
    view = ike.windows[0].current_view()
    yield from load(view, "ike:newtab")
    yield 600
    out["first"] = yield from js(view, """(function () {
      var g = document.querySelectorAll('.np-gear'), name = document.querySelector('.tile .name');
      return {gears: g.length, open: document.querySelectorAll('.np-wrap.on').length,
              name: getComputedStyle(name).color, body: getComputedStyle(document.body).color,
              weight: getComputedStyle(name).fontWeight, links: [].map.call(document.querySelectorAll('.np a'),
                function (a) { return a.getAttribute('href'); })};
    })()""")
    out["opened"] = yield from js(view, """(function () {
      document.querySelector('.np-corner .np-gear').click();
      var p = document.querySelector('.np-corner .np'), r = p.getBoundingClientRect();
      var top = document.elementFromPoint(r.left + r.width / 2, r.top + r.height - 20);
      return {open: document.querySelectorAll('.np-wrap.on').length, shown: getComputedStyle(p).display,
              inside: r.left >= 0 && r.top >= 0 && r.right <= innerWidth && r.bottom <= innerHeight,
              onTop: p.contains(top), focus: document.activeElement.getAttribute('data-s')};
    })()""")
    steps_before = view.history().count()
    yield from js(view, "document.querySelector('.np-corner [data-s=weather_unit]:not([aria-checked=true])').click()")
    for _ in range(100):
        yield 50
        if ike.config["weather_unit"] == "fahrenheit" and not view.loading:
            break
    yield 900
    out["after"] = yield from js(view, """(function () {
      var f = document.activeElement;
      return {open: [].map.call(document.querySelectorAll('.np-wrap.on'), function (w) { return w.className; }),
              focus: [f.getAttribute('data-s'), f.textContent, f.getAttribute('aria-checked')],
              name: document.body.getAttribute("data-np"), still: document.body.classList.contains('still')};
    })()""")
    out["unit"] = ike.config["weather_unit"]
    out["url"] = view.url().toString()
    out["steps"] = [steps_before, view.history().count()]
    out["saved"] = __import__("json").load(open(ike.config.path))["weather_unit"]
    # Escape closes the panel
    out["esc"] = yield from js(view, """(function () {
      document.activeElement.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}));
      return document.querySelectorAll('.np-wrap.on').length;
    })()""")
    # the counter's panel: since installation
    yield from js(view, "document.querySelector('.np-stats .np-gear').click()")
    yield from js(view, "document.querySelector('.np-stats [data-s=blocked_counter]:not([aria-checked=true])').click()")
    for _ in range(100):
        yield 50
        if ike.config["blocked_counter"] == "total" and not view.loading:
            break
    yield 900
    out["counter"] = [ike.config["blocked_counter"], (yield from js(view,
        "[].map.call(document.querySelectorAll('.np-wrap.on'), function (w) { return w.className; })"))]
    # without the session's key (a web page's link opened by hand): nothing changes
    yield from load(view, "ike:ntset?s=weather_unit&v=celsius")
    yield from load(view, "ike:ntset?s=newtab_clock&v=0&k=wrong")
    out["no key"] = [ike.config["weather_unit"], ike.config["newtab_clock"], view.url().toString()]
    # with the key, a setting the panels do not have: nothing changes
    yield from load(view, "ike:ntset?s=default_engine&v=Google&k=" + ike.shields.action_key)
    out["other"] = ike.config["default_engine"]
    # a web page cannot use it, in any way
    page = """<body><img src="ike:ntset?s=newtab_clock&v=0"><iframe src="ike:ntset?s=newtab_clock&v=0"></iframe>
        <script>fetch('ike:ntset?s=newtab_clock&v=0').catch(function () {});</script>"""
    view.setHtml(page, QUrl("http://site.example/"))
    yield 1500
    view.setHtml("<script>location.href = 'ike:ntset?s=newtab_clock&v=0';</script>", QUrl("http://site.example/2"))
    yield 1500
    out["web"] = ike.config["newtab_clock"]
'''


def test_the_panels_on_the_page(run_ike):
    out = run_ike(STEPS, settings={"newtab_clock": True, "newtab_weather": True, "welcome_done": True},
                  env={"IKE_TEST_WEATHER": "http://127.0.0.1:9"}, timeout=150)
    f = out["first"]
    assert f["gears"] == 2 and f["open"] == 0, f
    assert f["name"] == f["body"] and int(f["weight"]) >= 500, f       # the names in the text colour
    assert all(u.startswith(("ike:ntset?", "ike:open?what=newtab")) and "k=" in u for u in f["links"]), f["links"]
    o = out["opened"]
    assert o["open"] == 1 and o["shown"] == "block" and o["inside"] and o["onTop"], o
    assert o["focus"] == "newtab_clock", o
    a = out["after"]
    assert out["unit"] == "fahrenheit" and out["saved"] == "fahrenheit"
    assert out["url"] == "ike:newtab", out["url"]
    assert a["open"] == ["np-wrap np-corner on"] and a["still"] and a["name"] == "corner.weather_unit", a
    assert a["focus"] == ["weather_unit", "°F", "true"], a
    assert out["steps"][1] == out["steps"][0], out["steps"]             # no new step in the history
    assert out["esc"] == 0
    assert out["counter"] == ["total", ["np-wrap np-stats on"]], out["counter"]
    assert out["no key"] == ["fahrenheit", True, "ike:newtab"], out["no key"]
    assert out["other"] == "Startpage"
    assert out["web"] is True
