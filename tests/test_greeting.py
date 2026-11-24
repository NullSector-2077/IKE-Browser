"""The greeting and the friendly messages of the new tab page (1.1.24): the pool and its rotation,
what the greeting remembers (and nothing else), the holidays (all off unless chosen), the switches
in Settings, and the text fitting beside the Settings button in every language. The page's logic
(ike/resources/greeting.js) runs in the real engine; the rest is plain Python."""

import datetime
import json
import re
import sys

from conftest import APP, ROOT
from test_security import JS

sys.path.insert(0, str(APP))

PERIOD_WORDS = ("Good morning", "Good afternoon", "Good evening", "Good night")


# --- plain Python ----------------------------------------------------------------------------------
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
    data = greeting.page_data(hostile, {"k": "rain"}, 1, "1.1.24", "friendly", ["christian", "nope"],
                              {"days": 3, "bags": {"fact": ["fact1", "<b>"]}}, "key")
    assert "<" not in data and ">" not in data and "&" not in data
    back = json.loads(data)
    assert back["s"]["morning"] == "</script><script>window.pwned=1</script>&amp;"
    assert back["hol"] == ["christian"] and back["h"] == 1 and back["w"] == {"k": "rain"} and back["k"] == "key"
    assert back["st"]["bags"] == {"fact": ["fact1"]}
    # greetings only: no friendly line and no holiday words unless a tradition is chosen
    only = json.loads(greeting.page_data(lambda t: t, tone="greetings"))
    assert set(only["s"]) == {"morning", "afternoon", "evening", "night"} and only["hol"] == []
    assert only["tab"] == {}


def test_what_the_greeting_keeps_and_nothing_else():
    from ike import greeting

    hostile = {"first": "2026-11-23", "last": "https://example.org/secret", "upd": "x", "ver": "<script>",
               "days": 5, "streak": -1, "hn": True, "hour": 99, "url": "https://example.org/", "history": ["a"],
               "bags": {"fact": ["fact2", "zzz", 5], "nonsense": ["fact1"], "cheer": "no"},
               "cool": {"fact2": 20000, "https://x": 3, "cheer1": "soon"},
               "cur": {"p": "morning", "d": "2026-11-23", "t": 5, "k": "nope"}}
    got = greeting.clean_state(hostile)
    assert set(got) == {"first", "last", "upd", "ver", "updDone", "days", "streak", "hn", "hour", "bags", "cool", "cur"}
    assert got["first"] == "2026-11-23" and got["last"] == "" and got["ver"] == "" and got["days"] == 5
    assert got["streak"] == 0 and got["hn"] == 0 and got["hour"] == 0
    assert got["bags"] == {}                                                    # a list with anything foreign in it
    assert got["cool"] == {"fact2": 20000} and got["cur"] == {}
    assert greeting.clean_state("x") == {} and greeting.clean_state(None) == {}
    good = {"first": "2026-11-01", "last": "2026-11-23", "upd": "", "ver": "1.1.24", "updDone": "", "days": 9,
            "streak": 3, "hn": 9, "hour": 8.25, "bags": {"fact": ["fact1", "fact2"]}, "cool": {"fact3": 20400},
            "cur": {"p": "night", "d": "2026-11-23", "t": 1790000000000, "k": "late"}}
    assert greeting.clean_state(good) == good


def test_holidays_are_off_by_default_and_the_tables_are_sane():
    from ike import greeting
    from ike.config import DEFAULTS

    assert DEFAULTS["newtab_greeting"] is True and DEFAULTS["newtab_greeting_tone"] == "friendly"
    assert DEFAULTS["greeting_holidays"] == [] and DEFAULTS["greeting_state"] == {}
    assert greeting.holiday_tables([]) == {}
    tab = greeting.holiday_tables(["hindu", "buddhist"])
    assert set(tab) == {"diwali", "holi", "vesak"}
    assert set(greeting.holiday_tables(["lunar"])) == {"lunarny"}
    for days in tab.values():
        for d in days:
            datetime.date.fromisoformat(d)
    assert greeting.holiday_tables(["hindu"]).keys() == {"diwali", "holi"}
    assert {t[0] for t in greeting.TRADITIONS} == {"christian", "orthodox", "islamic", "jewish", "hindu", "buddhist",
                                                   "lunar", "nowruz", "civil"}


def test_the_pool_is_small_enough_to_fit_and_nothing_leaves_the_computer():
    from ike import greeting

    for key, text in greeting.WORDS + greeting.HOLIDAY_WORDS + greeting.GREETINGS:
        assert len(text) <= 60, (key, text)
    js = (ROOT / "ike" / "resources" / "greeting.js").read_text("utf-8")
    for word in ("fetch(", "XMLHttpRequest", "sendBeacon", "WebSocket", "EventSource", "importScripts", "eval(",
                 "document.write", "innerHTML", "setInterval", "setTimeout", "Image(", "http:", "https:"):
        assert word not in js, word          # the page's own script sends the state home, this file never does


def test_the_switches_are_in_settings():
    src = (ROOT / "ike" / "dialogs.py").read_text("utf-8")
    assert 'T("Greeting on the new tab page")' in src and 'cfg["newtab_greeting"] = self.nt_greeting.isChecked()' in src
    assert 'T("Holidays to remember")' in src and 'cfg["greeting_holidays"]' in src and 'T("Tone")' in src


# --- the page's logic in the engine ---------------------------------------------------------------
STEPS_LOGIC = JS + r'''
def steps(ike, qapp, out):
    view = ike.windows[0].current_view()
    yield 1500
    out["res"] = yield from js(view, SCRIPT)
'''

HEAD = r"""
var G = IkeGreeting;
function rngFrom(seed) { return function () { seed |= 0; seed = seed + 0x6D2B79F5 | 0; var t = Math.imul(seed ^ seed >>> 15, 1 | seed);
  t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }
function D(extra) { var d = {st: {}, s: {}, w: {}, h: 1, v: "1.1.24", tone: "friendly", hol: [], tab: {}, lang: "en"};
  for (var k in extra) d[k] = extra[k]; return d; }
function at(y, m, d, h, mi) { return new Date(y, m - 1, d, h, mi || 0); }
"""


def run_logic(run_ike, script, **kw):
    code = STEPS_LOGIC.replace("SCRIPT", repr("(function () {" + HEAD + script + "})()"))
    return run_ike(code, timeout=kw.pop("timeout", 120), **kw)["res"]


def test_the_keys_of_the_page_and_of_the_words_are_the_same(run_ike):
    from ike import greeting

    res = run_logic(run_ike, "return [G.keys(), G.groups()];")
    keys, groups = res
    assert sorted(keys) == sorted(greeting.ALL_KEYS) and len(keys) == len(set(keys))
    assert {g: tuple(k) for g, k in groups} == greeting.GROUP_KEYS
    assert len(greeting.WORDS) >= 95


def test_a_line_is_not_shown_again_until_the_others_of_its_group_were_(run_ike):
    from ike import greeting
    nfacts = len(dict(greeting.POOL)["fact"])
    res = run_logic(run_ike, "var FACTS = %d;" % nfacts + r"""
      var st = {}, c = {p: "morning"}, out = {bags: [], cool: null}, rng = rngFrom(7), today = 20000;
      for (var round = 0; round < 3; round++) {
        var bag = [];
        for (var i = 0; i < FACTS; i++) bag.push(G.bag("fact", st, c, today + round * 10 + i * 0, rng));
        out.bags.push(bag);
      }
      // cooldown: all but one shown the very day: that one comes
      var st2 = {cool: {}}; for (var i = 1; i < FACTS; i++) st2.cool["fact" + i] = 30000;
      out.cool = G.bag("fact", st2, c, 30000, rngFrom(3));
      // all of them in cooldown: still one (never nothing)
      var st3 = {cool: {}}; for (var i = 1; i <= FACTS; i++) st3.cool["fact" + i] = 30000;
      out.all = G.bag("fact", st3, c, 30001, rngFrom(3));
      // a group of one comes every time
      out.single = [G.bag("late", {}, c, 1, rngFrom(1)), G.bag("late", {bags: {late: []}, cool: {late: 1}}, c, 1, rngFrom(1))];
      // only the lines that fit the period: the bag keeps the others for later
      var st4 = {}, seen = [];
      for (var i = 0; i < 6; i++) seen.push(G.bag("period", st4, {p: "evening"}, 100 + i * 10, rngFrom(i)));
      out.evening = seen;
      return out;""")
    from ike import greeting
    facts = {k for k, _ in dict(greeting.POOL)["fact"]}
    for bag in res["bags"]:
        assert len(bag) == len(facts) and set(bag) == facts, bag                  # every one once before any again
    assert res["cool"] == "fact%d" % len(facts) and res["all"] in facts
    assert res["single"] == ["late", "late"]
    evening = {"evening1", "evening2", "evening3", "evening4"}
    assert set(res["evening"]) <= evening and set(res["evening"][:4]) == evening       # all four before any again


def test_the_line_is_kept_for_a_while_then_changes(run_ike):
    res = run_logic(run_ike, r"""
      var d = D({}), out = {}, rng = rngFrom(11);
      var a = G.decide(d, at(2026, 11, 25, 14, 0), rng), cur = JSON.stringify(d.st.cur);
      var b = G.decide(d, at(2026, 11, 25, 14, 50), rngFrom(99));     // another new tab soon after
      var c = G.decide(d, at(2026, 11, 25, 15, 59), rngFrom(5));      // still under two hours
      out.same = [a.key, b.key, c.key]; out.kept = JSON.stringify(d.st.cur) === cur;
      var e = G.decide(d, at(2026, 11, 25, 16, 30), rngFrom(1));      // two hours and a half
      out.later_t = d.st.cur.t > JSON.parse(cur).t;
      var f = G.decide(d, at(2026, 11, 25, 18, 5), rngFrom(2));       // the period changed
      out.period = [d.st.cur.p, f.p];
      // a new day
      G.decide(d, at(2026, 11, 26, 14, 10), rngFrom(3));
      out.day = d.st.cur.d;
      return out;""")
    assert res["same"][0] == res["same"][1] == res["same"][2] and res["kept"]
    assert res["later_t"] and res["period"] == ["evening", "evening"] and res["day"] == "2026-11-26"


def test_what_decides_the_line(run_ike):
    res = run_logic(run_ike, r"""
      var out = {};
      function pick(extra, when, n) {
        var set = {}, upd = {};
        for (var s = 1; s <= n; s++) { var d = D(JSON.parse(JSON.stringify(extra))); set[G.decide(d, when, rngFrom(s)).key] = 1; }
        return Object.keys(set);
      }
      // first opening after five days: "It's been a while" can come; after one day "Welcome back"
      out.away = pick({st: {last: "2026-11-18", days: 4, streak: 2}}, at(2026, 11, 25, 14), 80);
      out.welcome = pick({st: {last: "2026-11-24", days: 4, streak: 2}}, at(2026, 11, 25, 14), 80);
      out.streak = pick({st: {last: "2026-11-24", days: 9, streak: 8}}, at(2026, 11, 25, 14), 120);
      // an update: that line, once
      var d = D({st: {ver: "1.0.0", last: "2026-11-24"}});
      var one = G.decide(d, at(2026, 11, 25, 9), rngFrom(1)).key;
      var two = G.decide(d, at(2026, 11, 25, 13), rngFrom(1)).key;
      out.update = [one, two, d.st.updDone, d.st.ver];
      var fresh = D({}); out.install = pick({}, at(2026, 11, 25, 9), 40);
      // the small hours, the weather, the evening before the clocks change (a day of summer time's end elsewhere: not here)
      out.late = pick({st: {last: "2026-11-25"}}, at(2026, 11, 25, 3), 80);
      out.rain = pick({st: {last: "2026-11-25"}, w: {k: "rain"}}, at(2026, 11, 25, 14), 150);
      out.hot = pick({st: {last: "2026-11-25"}, w: {k: "clear", warm: true, hot: true}}, at(2026, 11, 25, 14), 150);
      out.sunnight = pick({st: {last: "2026-11-25"}, w: {k: "clear", warm: true}}, at(2026, 11, 25, 22), 150);
      // greetings only: nothing under the greeting
      out.only = pick({tone: "greetings", st: {last: "2026-11-18"}}, at(2026, 11, 25, 14), 40);
      return out;""")
    assert "away" in res["away"] and "welcome" not in res["away"]
    assert "welcome" in res["welcome"] and "away" not in res["welcome"]
    assert {"streak3", "streak7"} & set(res["streak"])
    assert res["update"] == ["updated", res["update"][1], "1.1.24", "1.1.24"] and res["update"][1] != "updated"
    assert "updated" not in res["install"] and "away" not in res["install"] and "welcome" not in res["install"]
    assert "late" in res["late"] and "rain" in res["rain"] and "hot" in res["hot"]
    assert "sun" not in res["sunnight"]                                        # the sun by day only
    assert res["only"] == [""]


def test_the_signals_kept_locally(run_ike):
    res = run_logic(run_ike, r"""
      var st = {}, out = [], days = [[2026, 11, 20, 8, 0], [2026, 11, 20, 20, 0], [2026, 11, 21, 10, 0], [2026, 11, 22, 9, 0],
                                     [2026, 11, 25, 7, 30], [2026, 11, 26, 8, 0]];
      days.forEach(function (x) { var u = G.usage(st, at(x[0], x[1], x[2], x[3], x[4]), "1.1.24");
        out.push([u.first, u.gap, st.days, st.streak, st.first, st.last, st.hour, st.hn, st.ver]); });
      return {rows: out, keys: Object.keys(st).sort()};""")
    rows = res["rows"]
    assert rows[0][:6] == [True, -1, 1, 1, "2026-11-20", "2026-11-20"]
    assert rows[1][0] is False and rows[1][2:4] == [1, 1]                      # the same day: nothing counted again
    assert rows[2][1:4] == [1, 2, 2] and rows[3][1:4] == [1, 3, 3]            # the streak grows
    assert rows[4][1:4] == [3, 4, 1] and rows[4][4] == "2026-11-20"           # a break: the streak starts again
    assert rows[5][2:4] == [5, 2] and rows[5][8] == "1.1.24"
    assert rows[0][6] == 8.0 and abs(rows[2][6] - 9.0) < 0.01 and rows[5][7] == 5      # a running average of the first hour
    assert set(res["keys"]) <= {"first", "last", "upd", "updDone", "ver", "days", "streak", "hour", "hn"}


def test_the_week_the_seasons_and_the_clocks(run_ike):
    res = run_logic(run_ike, r"""
      var out = {};
      function keys(c) { var o = {}; G.options(c).forEach(function (g) { o[g[0]] = g[2]; }); return o; }
      function ctx(d, extra) { var c = G.context(D(extra || {}), d, {first: false, gap: 0}); return c; }
      var NORTH = {first: 1, weekend: [6, 7]}, GULF = {first: 6, weekend: [5, 6]}, US = {first: 7, weekend: [6, 7]};
      function week(d, w) { var c = ctx(d); c.week = w; return (keys(c).week || []); }
      out.mon = [week(at(2026, 11, 23, 9), NORTH), week(at(2026, 11, 23, 14), NORTH)];
      out.fri = week(at(2026, 11, 27, 14), NORTH); out.sat = week(at(2026, 11, 28, 14), NORTH);
      out.gulf = [week(at(2026, 11, 22, 9), GULF), week(at(2026, 11, 26, 14), GULF), week(at(2026, 11, 27, 14), GULF)];
      out.us = [week(at(2026, 11, 22, 9), US), week(at(2026, 11, 23, 9), US)];
      out.tue = week(at(2026, 11, 24, 14), NORTH);
      // seasons: the 1st of March, June, September, December, by hemisphere
      var s = [];
      [1, -1].forEach(function (h) { [[3, 1], [6, 1], [9, 1], [12, 1], [3, 2], [4, 1]].forEach(function (m) {
        s.push([h, m[0], m[1], ctx(at(2026, m[0], m[1], 14), {h: h}).season]); }); });
      out.seasons = s;
      out.weekinfo = [G.weekOf("en-US"), G.weekOf("it"), G.weekOf("ar-SA"), G.weekOf("xx-nonsense-")];
      return out;""")
    assert res["mon"] == [["week"], []] and res["fri"] == ["soon"] and res["sat"] == ["weekend"]
    assert res["gulf"] == [["week"], ["soon"], ["weekend"]]
    assert res["us"] == [["weekend"], ["week"]] and res["tue"] == []
    want = {1: ["spring", "summer", "autumn", "winter", None, None], -1: ["autumn", "winter", "spring", "summer", None, None]}
    for h in (1, -1):
        assert [x[3] for x in res["seasons"] if x[0] == h] == want[h]
    assert res["weekinfo"][1]["first"] == 1 and res["weekinfo"][1]["weekend"] == [6, 7]
    assert res["weekinfo"][0]["first"] == 7                                    # the American week starts on Sunday


STEPS_TZ = JS + r'''
def steps(ike, qapp, out):
    view = ike.windows[0].current_view()
    yield 1500
    code = """(function () {
      var G = IkeGreeting, res = [];
      function c(d, h) { return G.context({st: {}, w: {}, h: h, v: "", lang: "en"}, d, {first: false, gap: 0}); }
      [[2026, 3, 27], [2026, 3, 28], [2026, 3, 29], [2026, 10, 24], [2026, 10, 25], [2026, 6, 15],
       [2026, 10, 3], [2026, 10, 4], [2026, 4, 3], [2026, 4, 4], [2026, 4, 5]].forEach(function (d) {
        res.push([d, c(new Date(d[0], d[1] - 1, d[2], 19, 0), 0).dst]); });
      [[2026, 3, 1], [2026, 9, 1], [2026, 12, 1]].forEach(function (d) {
        res.push([d, c(new Date(d[0], d[1] - 1, d[2], 14, 0), 0).season]); });
      return res; })()"""
    out["res"] = yield from js(view, code)
'''


def test_the_evening_before_the_clocks_change_and_the_hemisphere_from_the_time_zone(run_ike):
    for zone, change, seasons in (("Europe/Rome", {(2026, 3, 28), (2026, 10, 24)}, ["spring", "autumn", "winter"]),
                                  ("Australia/Sydney", {(2026, 10, 3), (2026, 4, 4)}, ["autumn", "spring", "summer"]),
                                  ("UTC", set(), [None, None, None])):
        res = run_ike(STEPS_TZ, env={"TZ": zone})["res"]
        assert {tuple(d) for d, dst in res[:11] if dst} == change, (zone, res)
        assert [s for d, s in res[11:]] == seasons, (zone, res)


def test_the_holidays_of_known_years(run_ike):
    from ike import greeting

    tables = greeting.holiday_tables(greeting.TRADITION_IDS)
    res = run_logic(run_ike, "var tab = %s;" % json.dumps(tables) + r"""
      var out = {};
      // the engine's own Chinese calendar, without the table
      out.lunar_engine = [];
      for (var y = 2028; y <= 2029; y++) for (var m = 0; m < 3; m++) for (var d = 1; d <= 31; d++) {
        var dt = new Date(y, m, d, 12); if (dt.getMonth() !== m) continue;
        if (G.holidayOn(dt, ["lunar"], {})) out.lunar_engine.push(y + "-0" + (m + 1) + "-" + (d < 10 ? "0" : "") + d);
      }
      ["christian", "orthodox", "islamic", "jewish", "hindu", "buddhist", "lunar", "nowruz", "civil"].forEach(function (t) {
        var found = [];
        for (var y = 2026; y <= 2028; y++) for (var m = 0; m < 12; m++) for (var d = 1; d <= 31; d++) {
          var date = new Date(y, m, d, 12); if (date.getMonth() !== m) continue;
          var h = G.holidayOn(date, [t], tab); if (h) found.push([y + "-" + (m + 1 < 10 ? "0" : "") + (m + 1) + "-" + (d < 10 ? "0" : "") + d, h]);
        }
        out[t] = found; });
      var none = 0;
      for (var y = 2026; y <= 2028; y++) for (var m = 0; m < 12; m++) for (var d = 1; d <= 31; d++)
        if (G.holidayOn(new Date(y, m, d, 12), [], tab)) none++;
      out.none = none;
      // never on a day without the tradition chosen, and the line wins all day, for every new tab
      var st = {last: "2026-12-25"}, dd = D({hol: ["christian"], st: st});
      out.xmas = [G.decide(dd, at(2026, 12, 25, 9), rngFrom(1)).key, G.decide(dd, at(2026, 12, 25, 21), rngFrom(2)).key];
      var off = D({st: {last: "2026-12-25"}}); out.xmas_off = G.decide(off, at(2026, 12, 25, 9), rngFrom(1)).key;
      var go = D({hol: ["christian"], tone: "greetings", st: {last: "2026-12-25"}});
      out.xmas_only = G.decide(go, at(2026, 12, 25, 9), rngFrom(1)).key;
      out.easter = [G.easter(2027, false).toDateString(), G.easter(2027, true).toDateString(),
                    G.easter(2025, false).toDateString(), G.easter(2025, true).toDateString()];
      return out;""")
    assert res["none"] == 0                                                    # nothing without a chosen tradition
    assert res["xmas"] == ["christmas", "christmas"] and res["xmas_off"] != "christmas"
    assert res["xmas_only"] == "christmas"
    assert res["easter"] == ["Sun Mar 28 2027", "Sun May 02 2027", "Sun Apr 20 2025", "Sun Apr 20 2025"]
    traditions = ("christian", "orthodox", "islamic", "jewish", "hindu", "buddhist", "lunar", "nowruz", "civil")
    got = {t: dict((d, k) for d, k in res[t]) for t in traditions}

    def near(tradition, key, want, tolerance=0):
        day = datetime.date.fromisoformat(want)
        days = [datetime.date.fromisoformat(d) for d, k in res[tradition] if k == key]
        assert any(abs((d - day).days) <= tolerance for d in days), (tradition, key, want, res[tradition])

    # Christian: Christmas and Easter (Gregorian computus)
    assert got["christian"]["2026-12-25"] == "christmas" and got["christian"]["2027-03-28"] == "easter"
    assert got["christian"]["2026-04-05"] == "easter" and got["christian"]["2028-04-16"] == "easter"
    # Orthodox: Christmas on 7 January, Easter by the Julian computus
    assert got["orthodox"]["2027-01-07"] == "christmas" and got["orthodox"]["2027-05-02"] == "easter"
    assert got["orthodox"]["2026-04-12"] == "easter" and got["orthodox"]["2028-04-16"] == "easter"
    # Islamic (Umm al-Qura of the engine: a day either way of the local sighting)
    near("islamic", "ramadan", "2027-02-08", 1)
    near("islamic", "eid", "2027-03-10", 1)
    near("islamic", "eid", "2027-05-17", 1)
    assert len([1 for k in got["islamic"].values() if k == "eid"]) >= 4      # both Eids, three years
    # Jewish (the day itself; the holiday begins at the evening before)
    near("jewish", "shana", "2027-10-02")
    near("jewish", "kippur", "2027-10-11")
    near("jewish", "hanukkah", "2027-12-25")
    near("jewish", "hanukkah", "2026-12-05")
    near("jewish", "passover", "2027-04-22")
    # Lunar New Year, Nowruz, the civil year, the tables
    assert got["lunar"]["2027-02-06"] == "lunarny" and got["lunar"]["2026-02-17"] == "lunarny"
    assert got["lunar"]["2028-01-26"] == "lunarny"
    assert res["lunar_engine"] and all(d in ("2028-01-26", "2028-01-27", "2029-02-12", "2029-02-13", "2029-02-14")
                                       for d in res["lunar_engine"])            # the engine alone: a day either way
    assert set(got["nowruz"]) == {"2026-03-21", "2027-03-21", "2028-03-21"}
    assert set(got["civil"]) == {"2026-01-01", "2027-01-01", "2028-01-01"}
    assert got["hindu"]["2027-03-22"] == "holi" and got["hindu"]["2027-10-29"] == "diwali"
    assert got["buddhist"]["2027-05-20"] == "vesak"


# --- the page and the browser ---------------------------------------------------------------------
STEPS_PAGE = JS + r'''
def steps(ike, qapp, out):
    view = ike.windows[0].current_view()
    yield 1500
    out["text"] = yield from js(view, "[document.getElementById('greet-t').textContent,"
                                      " document.getElementById('greet-l').textContent,"
                                      " document.getElementById('greet').getAttribute('dir')]")
    yield 500
    out["state"] = ike.config["greeting_state"]
    out["add"] = yield from js(view, """(function () {
      var ico = getComputedStyle(document.querySelector('.tile.add .ico')),
          name = getComputedStyle(document.querySelector('.tile.add .open'));
      return [ico.borderTopStyle, name.color, getComputedStyle(document.body).color, ico.backgroundColor,
              getComputedStyle(document.querySelector('.nt-settings .ico')).borderTopStyle]; })()""")
    # a web page cannot write the state, with the key of the session or without it
    ike.config["greeting_state"] = {"days": 1}
    key = ike.shields.action_key
    from PyQt6.QtCore import QUrl
    page = ('<body><img src="ike:greet?k=%s&s=%%7B%%22days%%22%%3A99%%7D"><img src="ike:greet?s=%%7B%%22days%%22%%3A98%%7D">'
            '<script>fetch("ike:greet?k=%s&s=%%7B%%22days%%22%%3A97%%7D").catch(function () {});</script>' % (key, key))
    view.setHtml(page, QUrl("http://site.example/"))
    yield 1500
    out["web"] = ike.config["greeting_state"]
    # the page's own address, with the key, does
    view.load(QUrl("ike:greet?k=%s&s=%%7B%%22days%%22%%3A7%%7D" % key))
    yield 800
    out["own"] = ike.config["greeting_state"].get("days")
    # junk and an oversized state are refused
    ike.shields.keep_greeting("not json")
    ike.shields.keep_greeting("{\"days\": 5, \"x\": \"" + "a" * 9000 + "\"}")
    out["junk"] = ike.config["greeting_state"].get("days")
'''


def test_the_page_greets_and_keeps_only_its_own_state(run_ike):
    out = run_ike(STEPS_PAGE)
    title, line, direction = out["text"]
    assert title in PERIOD_WORDS and direction == "auto"
    today = datetime.date.today().isoformat()
    assert out["state"]["last"] == today and out["state"]["days"] == 1 and out["state"]["streak"] == 1
    assert out["state"]["ver"]                                                  # the version seen
    ico_border, name_colour, text_colour, ico_back, settings_border = out["add"]
    assert ico_border == "solid" == settings_border and name_colour == text_colour
    assert ico_back != "rgba(0, 0, 0, 0)"
    assert out["web"] == {"days": 1}                                           # nothing from a web page
    assert out["own"] == 7 and out["junk"] == 7


STEPS_OFF = JS + r'''
def steps(ike, qapp, out):
    view = ike.windows[0].current_view()
    yield 1500
    out["off"] = yield from js(view, "[!!document.getElementById('greet'), !!document.getElementById('greet-data'),"
                                     " !!document.querySelector('.greet'), typeof IkeGreeting,"
                                     " !!document.querySelector('.clock')]")
    yield 500
    ike.shields.keep_greeting('{"days": 5}')
    out["state"] = ike.config["greeting_state"]
'''


def test_switched_off_nothing_is_on_the_page_and_nothing_is_kept(run_ike):
    out = run_ike(STEPS_OFF, settings={"newtab_greeting": False})
    assert out["off"][:4] == [False, False, False, "undefined"] and out["off"][4] is True      # the clock stays
    assert out["state"] == {}


STEPS_TONE = JS + r'''
def steps(ike, qapp, out):
    win = ike.windows[0]
    yield 600
    dlg = ike.show_settings(win, "newtab")
    yield 300
    out["start"] = [dlg.nt_greeting.isChecked(), dlg.nt_tone.currentData(),
                    sorted(i for i, sw in dlg.nt_holidays.items() if sw.isChecked()), sorted(dlg.nt_holidays)]
    dlg.nt_holidays["christian"].setChecked(True)
    dlg.nt_holidays["islamic"].setChecked(True)
    dlg.nt_tone.setCurrentIndex(dlg.nt_tone.findData("greetings"))
    dlg.apply()
    dlg.close()
    out["saved"] = [ike.config["newtab_greeting_tone"], ike.config["greeting_holidays"]]
'''


def test_the_choices_in_settings(run_ike):
    out = run_ike(STEPS_TONE)
    assert out["start"][:3] == [True, "friendly", []]                          # on, friendly, no holiday
    assert out["start"][3] == ["buddhist", "christian", "civil", "hindu", "islamic", "jewish", "lunar", "nowruz",
                               "orthodox"]
    assert out["saved"][0] == "greetings" and sorted(out["saved"][1]) == ["christian", "islamic"]


STEPS_FIT = JS + r'''
def steps(ike, qapp, out):
    win = ike.windows[0]
    view = win.current_view()
    yield 1500
    res = {}
    for width in (800, 500):
        win.resize(width, 700)
        yield 700
        code = """(function () {
          var packs = %s, bad = [], t = document.getElementById('greet-t'), l = document.getElementById('greet-l'),
              g = document.getElementById('greet'), s = document.querySelector('.nt-settings'), n = 0;
          for (var code in packs) {
            var lines = packs[code].lines, titles = packs[code].titles;
            for (var i = 0; i < lines.length; i++) {
              t.textContent = titles[i %% titles.length]; l.textContent = lines[i]; n++;
              var a = g.getBoundingClientRect(), b = s.getBoundingClientRect();
              var overlap = a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;
              if (overlap || a.right > window.innerWidth || a.left < 0) bad.push([code, lines[i], a.right, b.left]);
            }
          }
          // the labels of the two buttons: never cut (no ellipsis, nothing hidden), at most two lines, on the screen
          var names = [document.querySelector('.nt-settings .name'), document.querySelector('.nt-photo .name')];
          for (var code in packs) {
            for (var j = 0; j < 2; j++) {
              var el = names[j], cs = getComputedStyle(el);
              el.textContent = packs[code].labels[j];
              var r = el.getBoundingClientRect(), line = parseFloat(cs.lineHeight) || 15;
              if (el.scrollWidth > el.clientWidth + 1 || r.height > line * 2 + 4 || r.left < 0 || r.right > window.innerWidth ||
                  cs.textOverflow === 'ellipsis' || cs.overflow === 'hidden') bad.push([code, 'label', packs[code].labels[j], r.width, r.height]);
              n++;
            }
          }
          return [window.innerWidth, bad, n]; })()""" % json.dumps(PACKS)
        res[width] = yield from js(view, code)
    out["fit"] = res
'''


def test_the_greeting_stays_clear_of_settings_in_every_language(run_ike):
    from ike import greeting

    packs = {}
    for f in sorted((ROOT / "ike" / "resources" / "lang").glob("*.json")):
        strings = json.loads(f.read_text("utf-8"))["strings"]
        lines = [strings[t].replace("{version}", "1.1.24").replace("%d", "30")
                 for _k, t in greeting.WORDS + greeting.HOLIDAY_WORDS]
        packs[f.stem] = {"titles": [strings[t] for _k, t in greeting.GREETINGS], "lines": lines,
                         "labels": [strings["Settings"], strings["Background photo"]]}
    assert len(packs) >= 59
    out = run_ike(STEPS_FIT.replace("PACKS", repr(packs)), timeout=180)
    for width, (inner, bad, n) in out["fit"].items():
        assert inner <= int(width) and not bad and n > 59 * 60, (width, bad[:5], n)
    assert re.fullmatch(r"\d+", str(len(packs)))
