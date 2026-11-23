"""The greeting of the new tab page (1.1.24): the rules (ike/greeting.py and their twin in
newtab.html are compared over many moments), the switch, the local memory and the text fitting
beside the Settings button in every language."""

import datetime
import json
import sys

from conftest import ROOT
from test_security import JS

sys.path.insert(0, str(ROOT))

NORTH = {"first": 1, "weekend": [6, 7]}
GULF = {"first": 6, "weekend": [5, 6]}
IRAN = {"first": 6, "weekend": [5]}
US = {"first": 7, "weekend": [6, 7]}
WEATHERS = [{}, {"k": "rain"}, {"k": "snow"}, {"k": "fog"}, {"k": "clear", "warm": True},
            {"k": "clear", "warm": False}, {"k": "", "hot": True}, {"k": "", "cold": True},
            {"k": "", "wind": True}]


def test_periods_of_the_day():
    from ike import greeting

    for hour, name in ((5, "morning"), (11, "morning"), (12, "afternoon"), (17, "afternoon"),
                       (18, "evening"), (22, "evening"), (23, "night"), (0, "night"), (4, "night")):
        assert greeting.period(hour) == name, hour


def test_the_second_line_rules():
    from ike import greeting
    c = greeting.choose

    assert c(3, 3)[1] == "late" and c(1, 3)[1] == "late" and c(5, 3)[1] is None and c(0, 3)[1] is None
    assert c(9, 1)[1] == "week" and c(14, 1)[1] is None            # Monday morning only
    assert c(14, 5)[1] == "soon"                                    # Friday
    assert c(14, 6)[1] == "weekend" and c(14, 7)[1] == "weekend"
    assert c(14, 3)[1] is None                                      # nothing at all: just the greeting
    # the week of the language: Friday-Saturday weekend, Sunday first workday
    assert c(9, 7, week=GULF)[1] == "week" and c(14, 4, week=GULF)[1] == "soon"
    assert c(14, 5, week=GULF)[1] == "weekend" and c(14, 6, week=GULF)[1] == "weekend"
    assert c(14, 5, week=IRAN)[1] == "weekend" and c(14, 6, week=IRAN)[1] is None
    assert c(9, 7, week=US)[1] == "weekend" and c(9, 1, week=US)[1] == "week"     # Sunday is weekend there
    # weather
    assert c(14, 3, {"k": "rain"})[1] == "rain" and c(14, 3, {"k": "snow"})[1] == "snow"
    assert c(14, 3, {"k": "fog"})[1] == "fog" and c(14, 3, {"wind": True})[1] == "wind"
    assert c(14, 3, {"hot": True})[1] == "hot" and c(14, 3, {"cold": True})[1] == "cold"
    assert c(14, 3, {"k": "clear", "warm": True})[1] == "sun"
    assert c(22, 3, {"k": "clear", "warm": True})[1] is None        # the sun by day only
    assert c(14, 3, {"k": "clear"})[1] is None
    assert c(3, 3, {"k": "rain"})[1] == "late"                       # the rest comes first
    # what the page remembers
    assert c(14, 3, gap=1)[1] == "welcome" and c(14, 3, gap=3)[1] == "away" and c(14, 3, gap=0)[1] is None
    assert c(14, 3, gap=-1)[1] is None                               # a first use: no "back"
    assert c(14, 3, gap=5, updated="1.1.24")[1] == "updated"
    assert c(19, 3, dst=True)[1] == "dst" and c(10, 3, dst=True)[1] is None
    assert c(14, 3, season="spring")[1] == "spring"
    # no holiday anywhere
    keys = {k for k, _ in greeting.WORDS}
    assert not keys & {"newyear", "xmas", "eve", "easter", "eid"}


def test_seasons_by_hemisphere():
    from ike import greeting

    assert greeting.season_of(3, 1, 1) == "spring" and greeting.season_of(3, 1, -1) == "autumn"
    assert greeting.season_of(12, 1, 1) == "winter" and greeting.season_of(12, 1, -1) == "summer"
    assert greeting.season_of(6, 1, 1) == "summer" and greeting.season_of(9, 1, -1) == "spring"
    assert greeting.season_of(3, 2, 1) is None and greeting.season_of(4, 1, 1) is None
    assert greeting.season_of(3, 1, 0) is None and greeting.season_of(3, 1, None) is None   # unknown: skipped


def test_weather_kinds():
    from ike import greeting
    k = greeting.weather_kind

    assert k(63, 10)["k"] == "rain" and k(95, 10)["k"] == "rain" and k(73, 0)["k"] == "snow"
    assert k(45, 10)["k"] == "fog" and k(0, 25) == {"k": "clear", "warm": True, "hot": False, "cold": False,
                                                    "wind": False}
    assert k(3, 10)["k"] == ""
    assert k(0, 36)["hot"] and not k(0, 34)["hot"] and k(0, -5)["cold"] and not k(0, -4)["cold"]
    assert k(0, 96, "°F")["hot"] and not k(0, 94, "°F")["hot"] and k(0, 22, "°F")["cold"]
    assert k(0, 20, wind=50)["wind"] and not k(0, 20, wind=49)["wind"]
    assert k(None) == {} and k("x") == {} and k(True) == {}


def test_the_words_go_into_the_page_as_data():
    from ike import greeting

    hostile = lambda text: "</script><script>window.pwned=1</script>&amp;"        # noqa: E731
    data = greeting.page_data(hostile, {"k": "rain"}, 2, "1.1.24", 1)
    assert "<" not in data and ">" not in data and "&" not in data
    back = json.loads(data)
    assert back["s"]["morning"] == "</script><script>window.pwned=1</script>&amp;"
    assert back["g"] == 2 and back["v"] == "1.1.24" and back["h"] == 1 and back["w"] == {"k": "rain"}


class Cfg(dict):
    pass


class Fake:
    def __init__(self, **data):
        self.config = Cfg(greeting_last_open="", greeting_version="", greeting_update_day="")
        self.config.update(data)


def test_what_the_greeting_remembers():
    from ike import __version__, shields

    day = datetime.date(2026, 11, 23)
    fake = Fake()
    state = lambda today: shields.Shields.greeting_state(fake, today)               # noqa: E731
    assert state(day) == (-1, "")                       # a first use: never before, no update to tell
    assert fake.config == {"greeting_last_open": "2026-11-23", "greeting_version": __version__,
                           "greeting_update_day": ""}   # a date and a version, nothing else
    assert state(day) == (0, "")
    assert state(day + datetime.timedelta(days=1))[0] == 1
    assert state(day + datetime.timedelta(days=5))[0] == 4
    # a new version: told that day
    fake.config["greeting_version"] = "1.0.0"
    assert state(day + datetime.timedelta(days=5)) == (0, __version__)
    assert state(day + datetime.timedelta(days=5)) == (0, __version__)
    assert state(day + datetime.timedelta(days=6))[1] == ""
    # a damaged date does not stop anything
    fake.config["greeting_last_open"] = "not a date"
    assert state(day)[0] == -1
    # the clock set back
    fake.config["greeting_last_open"] = "2030-01-01"
    assert state(day)[0] == 0


def test_the_hemisphere_comes_from_the_cities_latitude():
    from ike import shields

    for lat, want in ((41.89, 1), (-33.87, -1), (0.0, 0), (None, 0), ("x", 0)):
        fake = Fake()
        fake.config["weather_lat"] = lat
        assert shields.Shields.greeting_hemisphere(fake) == want, lat


def test_the_switch_is_on_by_default_and_in_settings():
    from ike.config import DEFAULTS

    assert DEFAULTS["newtab_greeting"] is True
    assert DEFAULTS["greeting_last_open"] == "" and DEFAULTS["greeting_version"] == ""
    src = (ROOT / "ike" / "dialogs.py").read_text("utf-8")
    assert 'T("Show a greeting")' in src and 'cfg["newtab_greeting"] = self.nt_greeting.isChecked()' in src


def moments():
    """(date, week, weather, state) over a week, every hour, the weathers and the weeks."""
    for day in range(23, 30):                           # Monday 23 November 2026 ... Sunday 29
        for hour in range(24):
            for week in (NORTH, GULF, IRAN, US):
                for w in WEATHERS:
                    for gap, updated in ((-1, ""), (0, ""), (1, ""), (3, ""), (0, "1.1.24")):
                        yield (2026, 11, day, hour), week, w, {"g": gap, "v": updated, "h": 1}


STEPS_PARITY = JS + r'''
def steps(ike, qapp, out):
    view = ike.windows[0].current_view()
    yield 1500
    cases = json.loads(CASES)
    code = """(function () {
      var cases = %s, res = [];
      for (var i = 0; i < cases.length; i++) {
        var c = cases[i], r = ikeGreetFor(new Date(c[0][0], c[0][1] - 1, c[0][2], c[0][3], 30), c[2], c[1], c[3]);
        res.push([r[0], r[1], r[2].dst, r[2].season]);
      }
      return res; })()""" % json.dumps(cases)
    out["res"] = yield from js(view, code)
    # the hemisphere and the seasons over a whole year, and the weather's own hemisphere
    code = """(function () {
      var res = [];
      for (var h = -1; h <= 1; h += 2) for (var m = 0; m < 12; m++) for (var d = 1; d <= 28; d++) {
        var r = ikeGreetFor(new Date(2026, m, d, 14, 0), {}, {first: 1, weekend: [6, 7]}, {g: 0, v: "", h: h});
        res.push([h, m + 1, d, r[2].season]);
      }
      return res; })()"""
    out["seasons"] = yield from js(view, code)
    out["text"] = yield from js(view, "[document.getElementById('greet-t').textContent,"
                                      " document.getElementById('greet-l').textContent,"
                                      " document.getElementById('greet').getAttribute('dir')]")
    out["add"] = yield from js(view, """(function () {
      var ico = getComputedStyle(document.querySelector('.tile.add .ico')),
          name = getComputedStyle(document.querySelector('.tile.add .open'));
      return [ico.borderTopStyle, name.color, getComputedStyle(document.body).color, ico.backgroundColor,
              getComputedStyle(document.querySelector('.nt-settings .ico')).borderTopStyle]; })()""")
'''


def test_the_page_follows_the_rules_of_greeting_py(run_ike):
    from ike import greeting

    cases = []
    for when, week, w, st in moments():
        cases.append([list(when), week, w, st])
    out = run_ike(STEPS_PARITY.replace("CASES", repr(json.dumps(cases))), timeout=180)
    assert len(out["res"]) == len(cases)
    for (when, week, w, st), (period, key, dst, season) in zip(moments(), out["res"]):
        y, mo, d, h = when
        weekday = datetime.date(y, mo, d).isoweekday()
        want = greeting.choose(h, weekday, w, week, st["g"], st["v"], dst, season)
        assert (period, key) == want, (when, week, w, st)
        assert dst is False and season is None           # 23-29 November in UTC: nothing yet
    for h, m, d, season in out["seasons"]:
        assert season == greeting.season_of(m, d, h), (h, m, d)
    title, line, direction = out["text"]
    assert title in ("Good morning", "Good afternoon", "Good evening", "Good night") and direction == "auto"
    # the Add tile is as visible as Settings: a solid border and the text colour, 1.1.24
    ico_border, name_colour, text_colour, ico_back, settings_border = out["add"]
    assert ico_border == "solid" == settings_border and name_colour == text_colour
    assert ico_back != "rgba(0, 0, 0, 0)"


STEPS_TZ = JS + r'''
def steps(ike, qapp, out):
    view = ike.windows[0].current_view()
    yield 1500
    code = """(function () {
      var res = [];
      [[2026, 3, 27], [2026, 3, 28], [2026, 3, 29], [2026, 10, 24], [2026, 10, 25], [2026, 6, 15],
       [2026, 9, 30], [2026, 10, 3], [2026, 10, 4], [2026, 4, 3], [2026, 4, 4], [2026, 4, 5]].forEach(function (d) {
        var r = ikeGreetFor(new Date(d[0], d[1] - 1, d[2], 19, 0), {}, {first: 1, weekend: [6, 7]}, {g: 0, v: "", h: 0});
        res.push([d, r[1], r[2].dst]);
      });
      // no city: the hemisphere is read from the months of summer time (Rome north, Sydney south)
      [[2026, 3, 1], [2026, 9, 1], [2026, 12, 1]].forEach(function (d) {
        var r = ikeGreetFor(new Date(d[0], d[1] - 1, d[2], 14, 0), {}, {first: 1, weekend: [6, 7]}, {g: 0, v: "", h: 0});
        res.push([d, r[1], r[2].season]);
      });
      return res; })()"""
    out["res"] = yield from js(view, code)
'''


def test_the_evening_before_the_clocks_change_and_the_hemisphere_from_the_time_zone(run_ike):
    rome = run_ike(STEPS_TZ, env={"TZ": "Europe/Rome"})["res"]
    on = {tuple(d) for d, key, dst in rome[:12] if dst}
    assert on == {(2026, 3, 28), (2026, 10, 24)}, rome
    assert [key for d, key, dst in rome[:12] if tuple(d) in on] == ["dst", "dst"]
    assert [s for d, key, s in rome[12:]] == ["spring", "autumn", "winter"]
    sydney = run_ike(STEPS_TZ, env={"TZ": "Australia/Sydney"})["res"]
    on = {tuple(d) for d, key, dst in sydney[:12] if dst}
    assert on == {(2026, 10, 3), (2026, 4, 4)}, sydney
    assert [s for d, key, s in sydney[12:]] == ["autumn", "spring", "summer"]
    utc = run_ike(STEPS_TZ, env={"TZ": "UTC"})["res"]
    assert not any(dst for d, key, dst in utc[:12])
    assert [s for d, key, s in utc[12:]] == [None, None, None]          # no summer time, no city: skipped


STEPS_OFF = JS + r'''
def steps(ike, qapp, out):
    view = ike.windows[0].current_view()
    yield 1500
    out["off"] = yield from js(view, "[!!document.getElementById('greet'), !!document.getElementById('greet-data'),"
                                     " !!document.querySelector('.greet'), typeof ikeGreetFor,"
                                     " !!document.querySelector('.clock')]")
'''


def test_switched_off_nothing_is_on_the_page(run_ike):
    out = run_ike(STEPS_OFF, settings={"newtab_greeting": False})
    assert out["off"][:3] == [False, False, False] and out["off"][4] is True        # the clock stays


STEPS_FIT = JS + r'''
def steps(ike, qapp, out):
    win = ike.windows[0]
    view = win.current_view()
    yield 1500
    packs = json.loads(PACKS)
    res = {}
    for width in WIDTHS:
        win.resize(width, 700)
        yield 700
        code = """(function () {
          var packs = %s, bad = [], t = document.getElementById('greet-t'), l = document.getElementById('greet-l'),
              g = document.getElementById('greet'), s = document.querySelector('.nt-settings');
          for (var code in packs) {
            var lines = packs[code].lines;
            for (var i = 0; i < lines.length; i++) {
              t.textContent = packs[code].title; l.textContent = lines[i];
              var a = g.getBoundingClientRect(), b = s.getBoundingClientRect();
              var overlap = a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;
              if (overlap || a.right > window.innerWidth || a.left < 0) bad.push([code, lines[i], a.right, b.left]);
            }
          }
          return [window.innerWidth, bad]; })()""" % json.dumps(packs)
        res[width] = yield from js(view, code)
    out["fit"] = res
'''


def test_the_greeting_stays_clear_of_settings_in_every_language(run_ike):
    from ike import greeting

    packs = {}
    folder = ROOT / "ike" / "resources" / "lang"
    for f in sorted(folder.glob("*.json")):
        strings = json.loads(f.read_text("utf-8"))["strings"]
        title = max((strings[v] for _, v in greeting.GREETINGS), key=len)
        lines = [strings[v].replace("{version}", "1.1.24") for _, v in greeting.WORDS]
        packs[f.stem] = {"title": title, "lines": lines}
    assert len(packs) >= 59
    out = run_ike(STEPS_FIT.replace("PACKS", repr(json.dumps(packs))).replace("WIDTHS", "(800, 500)"),
                  timeout=180)
    for width, (inner, bad) in out["fit"].items():
        assert inner <= int(width) and not bad, (width, bad[:5])
