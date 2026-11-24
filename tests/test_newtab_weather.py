"""The weather of the new tab page, 1.1.25: the symbol and its text aligned as one block (measured in
the page drawn for real, offscreen: the boxes and the ink of the pixels), and the small row of details
under it as in Plasma's weather widget, kept simple (felt temperature, wind and where it comes from,
humidity, pressure, chance of precipitation: one discreet row), asked in the same request to
Open-Meteo, with the units of the setting (°C with km/h and hPa, °F with mph and inHg). No test here reaches the network: a stand-in server answers,
or the weather is put in place before the page is drawn."""

import http.server
import json
import sys
import threading

import pytest
from conftest import ROOT
from test_security import JS

sys.path.insert(0, str(ROOT))

# what Open-Meteo answers for the request I.K.E. makes (its "current" block; recorded shape)
FULL = {"latitude": 41.9, "longitude": 12.5, "current_units": {"temperature_2m": "°C", "wind_speed_10m": "km/h"},
        "current": {"time": "2026-11-24T14:00", "interval": 900, "temperature_2m": 12.4, "weather_code": 2,
                    "wind_speed_10m": 14.4, "wind_direction_10m": 312, "apparent_temperature": 10.2,
                    "relative_humidity_2m": 78, "pressure_msl": 1016.4, "precipitation_probability": 20}}
FIELDS = ("temperature_2m%2Cweather_code%2Cwind_speed_10m%2Cwind_direction_10m%2Capparent_temperature"
          "%2Crelative_humidity_2m%2Cpressure_msl")
NO_NETWORK = {"IKE_TEST_WEATHER": "http://127.0.0.1:9"}     # nothing listens there: never the real service


# --- plain Python ------------------------------------------------------------------------------------
def test_the_answer_is_read_with_its_details():
    from ike import weather
    got = weather.parse(FULL)
    assert got == {"temp": 12, "code": 2, "wind": 14.4, "wind_dir": 312.0, "feels": 10.2, "humidity": 78.0,
                   "pressure": 1016.4, "rain": 20.0}
    # what I.K.E. does not show is not kept, even if the answer had it
    assert weather.parse({"current": dict(FULL["current"], cloud_cover=40, uv_index=2.5)}) == got
    # a detail the service did not give (null), or gave in a form that is not a number, is left out
    odd = {"current": dict(FULL["current"], precipitation_probability="20", relative_humidity_2m=True,
                           wind_direction_10m=float("nan"), pressure_msl=None)}
    del odd["current"]["apparent_temperature"]
    assert weather.parse(odd) == {"temp": 12, "code": 2, "wind": 14.4}
    assert weather.parse({"current": dict(FULL["current"], precipitation_probability=None)}).get("rain") is None
    # the 1.1.24 answer still works
    assert weather.parse({"current": {"temperature_2m": 12.4, "weather_code": 3}}) == {"temp": 12, "code": 3, "wind": 0.0}
    for broken in ({}, {"current": {"weather_code": 3}}, {"current": {"temperature_2m": "warm", "weather_code": 3}}):
        with pytest.raises((KeyError, ValueError, TypeError)):
            weather.parse(broken)


def test_the_request_asks_for_the_details_and_nothing_more():
    from ike import weather
    assert weather.FIELDS == ("temperature_2m", "weather_code", "wind_speed_10m", "wind_direction_10m",
                              "apparent_temperature", "relative_humidity_2m", "pressure_msl",
                              "precipitation_probability")
    assert weather.BASIC + weather.MORE + weather.HOURLY == weather.FIELDS


def _w(unit="°C", **kw):
    w = {"temp": 12, "unit": unit, "code": 2, "wind": 14.4, "wind_dir": 312.0, "feels": 10.2, "humidity": 78.0,
         "pressure": 1016.4, "rain": 20.0}
    w.update(kw)
    return {k: v for k, v in w.items() if v is not None}


def test_the_details_and_their_units():
    from ike import weather
    assert weather.details(_w()) == [
        {"k": "feels", "l": "Feels like", "v": "10 °C"},
        {"k": "wind", "l": "Wind", "v": "14 km/h NW"},
        {"k": "humidity", "l": "Humidity", "v": "78%"},
        {"k": "pressure", "l": "Pressure", "v": "1016 hPa"},
        {"k": "rain", "l": "Chance of precipitation", "v": "20%"}]
    assert len(weather.details(_w())) <= 5                                    # a few, the owner: simple
    # °F (the answer is in °F already): the wind in mph and the pressure in inHg, worked out here
    f = weather.details(_w("°F", feels=50.4, wind=40.0, wind_dir=90.0))
    assert [x["v"] for x in f] == ["50 °F", "25 mph E", "78%", "30.01 inHg", "20%"]
    assert weather.details(_w("°F", wind=1.6))[1]["v"] == "1 mph NW"
    # still air: no direction; a value the answer lacked: no line for it; the 1.1.24 cache: no details
    calm = weather.details(_w(wind=0.3))[1]
    assert calm == {"k": "wind", "l": "Wind", "v": "0 km/h"}
    assert [x["k"] for x in weather.details(_w(rain=None, feels=None))] == ["wind", "humidity", "pressure"]
    old = {"temp": 12, "unit": "°C", "code": 2, "wind": 14.4}
    assert weather.details(old) == [] and weather.details(None) == [] and weather.details({}) == []
    # the words go through the translation
    tr = {"Feels like": "Percepita", "Wind": "Vento", "NW": "NO"}
    it = weather.details(_w(), lambda t: tr.get(t, t))
    assert it[0]["l"] == "Percepita" and it[1] == {"k": "wind", "l": "Vento", "v": "14 km/h NO"}


def test_the_points_of_the_compass():
    from ike import weather
    want = {0: "N", 22: "N", 23: "NE", 45: "NE", 90: "E", 135: "SE", 180: "S", 202: "S", 203: "SW", 270: "W",
            292: "W", 293: "NW", 337: "NW", 338: "N", 359.9: "N", 360: "N", -45: "NW", 725: "N"}
    for deg, point in want.items():
        assert weather.compass(deg) == point, deg


def test_the_symbol_and_the_rest():
    from ike import weather
    assert weather.split_symbol("☁ 12 °C · Cloudy · Rome") == ("☁", "12 °C · Cloudy · Rome")
    assert weather.split_symbol("12 °C · Rome") == ("", "12 °C · Rome")         # no symbol: never "12"
    assert weather.split_symbol("☁") == ("", "☁") and weather.split_symbol("") == ("", "")


def test_the_words_of_the_details_are_in_every_language():
    from ike import weather
    words = ["Feels like", "Wind", "Humidity", "Pressure", "Chance of precipitation"] + list(weather.COMPASS)
    for f in sorted((ROOT / "ike" / "resources" / "lang").glob("*.json")):
        strings = json.loads(f.read_text("utf-8"))["strings"]
        for w in words:
            assert strings.get(w, "").strip(), (f.stem, w)
        assert len({strings[p] for p in weather.COMPASS}) == 8, f.stem         # eight different points


# --- the stand-in service -------------------------------------------------------------------------------
@pytest.fixture
def service():
    """Open-Meteo's stand-in: answers FULL; with mode "refuse" it answers 400 to a request with the
    hourly field (as the real service does to a field it does not know)."""
    state = {"seen": [], "mode": "full"}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            state["seen"].append(self.path)
            code, body = 200, FULL
            if state["mode"] == "refuse" and "precipitation_probability" in self.path:
                code, body = 400, {"error": True, "reason": "Cannot initialize from invalid String value"}
            elif state["mode"] == "refuse":         # only what was asked for
                body = {"current": {k: v for k, v in FULL["current"].items() if k != "precipitation_probability"}}
            elif "temperature_unit=fahrenheit" in self.path:
                body = {"current": dict(FULL["current"], temperature_2m=54.3, apparent_temperature=50.4)}
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):
            pass

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    state["base"] = "http://127.0.0.1:%d" % httpd.server_address[1]
    yield state
    httpd.shutdown()


READ = """(function () {
  var w = document.getElementById('weather'), more = document.getElementById('weather-more');
  if (!w || !more) return null;
  return {text: w.textContent, html: w.innerHTML.replace(/ style="[^"]*"/g, ''), more: more.textContent,
          items: Array.prototype.map.call(more.querySelectorAll('.wx-i'), function (i) {
            var use = i.querySelector('svg.wx-s use');
            return {cls: i.className, text: i.textContent, label: i.querySelector('.wx-l').textContent,
                    value: i.querySelector('.wx-v').textContent, title: i.title, icon: use && use.getAttribute('href'),
                    hidden: i.querySelector('svg').getAttribute('aria-hidden'),
                    labelWidth: i.querySelector('.wx-l').getBoundingClientRect().width,
                    svgs: i.querySelectorAll('svg').length};
          })};
})()"""

STEPS_SERVICE = JS + r'''
def steps(ike, qapp, out):
    win = ike.windows[0]
    for _ in range(40):
        yield 100
        if ike.weather.data.get("temp") is not None:
            break
    yield 800
    out["pushed"] = yield from js(win.current_view(), READ)       # written into the open page by ikeWeather()
    view = win.add_tab()                                           # drawn with the page (shields.newtab_html)
    yield 1500
    out["drawn"] = yield from js(view, READ)
    out["data"] = ike.weather.data
'''


def _run(run_ike, service, unit="celsius"):
    settings = {"weather_city": "Rome", "weather_lat": 41.89, "weather_lon": 12.51, "weather_unit": unit}
    return run_ike(STEPS_SERVICE.replace("READ", repr(READ)), settings=settings,
                   env={"IKE_TEST_WEATHER": service["base"]})


def test_the_details_come_with_the_same_request(run_ike, service):
    out = _run(run_ike, service)
    forecasts = [p for p in service["seen"] if p.startswith("/forecast")]
    assert forecasts == ["/forecast?latitude=41.89&longitude=12.51&current=" + FIELDS
                         + "%2Cprecipitation_probability"]
    for page in (out["pushed"], out["drawn"]):
        assert page["text"] == "⛅ 12 °C · Partly cloudy · Rome"                # the 1.1.24 rule: sym + " " + rest
        items = page["items"]
        assert [(i["label"], i["value"]) for i in items] == [
            ("Feels like", "10 °C"), ("Wind", "14 km/h NW"), ("Humidity", "78%"), ("Pressure", "1016 hPa"),
            ("Chance of precipitation", "20%")]
        for i in items:
            assert i["text"] == i["label"] + " " + i["value"]                   # read aloud: the name and the value
            assert i["title"] == i["label"] + ": " + i["value"]                 # and shown on hover
            assert i["icon"] == "#wx-" + i["cls"].split("wx-")[-1] and i["hidden"] == "true"
            assert i["labelWidth"] <= 1                                         # the name is not drawn
        assert all(i["svgs"] == 1 for i in items)                                # one symbol each, nothing more
    # the page that got the weather later and the page drawn with it: the same block
    assert out["pushed"]["html"] == out["drawn"]["html"]
    assert out["pushed"]["html"] == ('<span class="wsym"><span class="wg">⛅</span></span> '
                                     '<span class="wtxt">12 °C · Partly cloudy · Rome</span>')


def test_fahrenheit_and_miles_per_hour(run_ike, service):
    out = _run(run_ike, service, "fahrenheit")
    forecasts = [p for p in service["seen"] if p.startswith("/forecast")]
    assert forecasts == ["/forecast?latitude=41.89&longitude=12.51&current=" + FIELDS
                         + "%2Cprecipitation_probability&temperature_unit=fahrenheit"]
    page = out["drawn"]
    assert page["text"] == "⛅ 54 °F · Partly cloudy · Rome"
    assert [i["value"] for i in page["items"]] == ["50 °F", "9 mph NW", "78%", "30.01 inHg", "20%"]
    assert out["data"]["wind"] == 14.4                                         # kept in km/h (the greeting's unit)


def test_a_refused_field_does_not_cost_the_weather(run_ike, service):
    service["mode"] = "refuse"
    out = _run(run_ike, service)
    forecasts = [p for p in service["seen"] if p.startswith("/forecast")]
    base = "/forecast?latitude=41.89&longitude=12.51&current=" + FIELDS
    assert forecasts == [base + "%2Cprecipitation_probability", base]     # once more, at once, once
    page = out["drawn"]
    assert page["text"] == "⛅ 12 °C · Partly cloudy · Rome"
    assert [i["label"] for i in page["items"]] == ["Feels like", "Wind", "Humidity", "Pressure"]


# --- the layout, measured --------------------------------------------------------------------------------
MEASURE = """(function () {
  function box(e) { if (!e) return null; var r = e.getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom]; }
  var q = function (s) { return document.querySelector(s); }, all = function (s) {
    return Array.prototype.map.call(document.querySelectorAll(s), box); };
  return {sym: box(q('#weather .wsym')), txt: box(q('#weather .wtxt')), weather: box(q('#weather')),
          clock: box(q('.clock')), date: box(q('.date')), more: box(q('#weather-more')), items: all('.wx-i'),
          corner: box(q('.corner')), stats: box(q('.stats')), shown: getComputedStyle(q('#weather-more')).display,
          off: q('#weather-more').dataset.off || '',
          icons: all('.wx-i > svg.wx-s'), vals: all('.wx-v'),
          vw: innerWidth, vh: innerHeight, shift: q('#weather .wg').style.transform,
          bg: getComputedStyle(document.documentElement).getPropertyValue('--bg').trim()};
})()"""

# window width, height, zoom: an ordinary window, the same at 150 % and 200 %, the narrowest width that
# shows the details (a tall window), the same width lower (the corner would meet the figures: the row
# gives way), a narrow one, a crowded one
NARROWEST = 830
CASES = ((1100, 760, 1.0), (1650, 1140, 1.5), (2200, 1520, 2.0), (NARROWEST, 1000, 1.0), (NARROWEST, 760, 1.0),
         (760, 760, 1.0), (1100, 760, 1.5))
SHOWN = {"1100x760-1.0", "1650x1140-1.5", "2200x1520-2.0", "%dx1000-1.0" % NARROWEST}

# every language: the label of the weather, a long city and the details, through the page's own ikeWeather()
EVERY = """(function () {
  var packs = PACKS, bad = [], n = 0;
  function box(e) { var r = e.getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom]; }
  function mid(b) { return (b[1] + b[3]) / 2; }
  for (var code in packs) {
    var p = packs[code];
    ikeWeather("⛅ 12 °C · " + p.label + " · Llanfairpwllgwyngyll", undefined, p.more);
    var s = box(document.querySelector('#weather .wsym')), t = box(document.querySelector('#weather .wtxt')),
        w = box(document.getElementById('weather')), c = box(document.querySelector('.clock')),
        m = box(document.getElementById('weather-more'));
    n++;
    if (Math.abs(mid(s) - mid(t)) > 1 || s[2] > t[0] || Math.abs(w[2] - c[2]) > 1.5 || Math.abs(m[2] - c[2]) > 1.5 ||
        w[0] < 0 || m[0] < 0 || w[2] > innerWidth || m[2] > innerWidth) bad.push([code, 'block', s, t, w, m, c]);
    var lines = {};
    Array.prototype.forEach.call(document.querySelectorAll('.wx-i'), function (i) {
      var ic = box(i.querySelector('svg.wx-s')), v = box(i.querySelector('.wx-v')), b = box(i);
      if (Math.abs(mid(ic) - mid(v)) > 1 || b[0] < 0 || b[2] > innerWidth || ic[2] > v[0]) bad.push([code, 'item', i.textContent]);
      lines[Math.round(mid(b))] = 1;
    });
    if (Object.keys(lines).length > 1) bad.push([code, 'more than one line', Object.keys(lines)]);     // one discreet row
  }
  return [n, bad];
})()"""

STEPS_LAYOUT = JS + r'''
def steps(ike, qapp, out):
    import os, time
    from PyQt6.QtCore import QUrl
    ike.config["weather_city"], ike.config["weather_lat"], ike.config["weather_lon"] = "Roma", 41.89, 12.51
    ike.weather.data = dict(DATA, key=[41.89, 12.51, "celsius"], time=time.time())
    win = ike.windows[0]
    view = win.current_view()
    res = {}
    for width, height, zoom in CASES:
        win.resize(width, height)
        view.setZoomFactor(zoom)
        view.load(QUrl("ike:newtab"))
        yield 1800
        m = yield from js(view, MEASURE)
        path = os.path.join(SHOTS, "w%dx%d-z%s.png" % (width, height, zoom))
        view.grab().save(path)
        res["%dx%d-%s" % (width, height, zoom)] = [m, path, zoom]
    out["layout"] = res
    win.resize(NARROWEST, 1000)                    # every language at the narrowest width with the details
    view.setZoomFactor(1.0)
    view.load(QUrl("ike:newtab"))
    yield 1800
    out["every"] = yield from js(view, EVERY)
    out["every_width"] = yield from js(view, "innerWidth")
'''


def _ink_rows(image, left, right, top, bottom, bg):
    """The first and last rows, in the box, with pixels clearly not the page's colour."""
    rows = []
    for y in range(max(0, top), min(image.height(), bottom)):
        for x in range(max(0, left), min(image.width(), right)):
            c = image.pixelColor(x, y)
            if abs(c.red() - bg[0]) + abs(c.green() - bg[1]) + abs(c.blue() - bg[2]) > 90:
                rows.append(y)
                break
    return rows[0], rows[-1]


def test_symbol_and_text_are_one_tidy_block(run_ike, tmp_path):
    import os

    from PyQt6.QtGui import QGuiApplication, QImage

    from ike import weather
    packs = {}
    for f in sorted((ROOT / "ike" / "resources" / "lang").glob("*.json")):
        strings = json.loads(f.read_text("utf-8"))["strings"]
        tr = lambda t, s=strings: s.get(t, t)                                          # noqa: E731
        packs[f.stem] = {"label": tr("Partly cloudy"), "more": weather.details(_w(), tr)}
    assert len(packs) >= 59
    data = weather.parse(FULL)
    shots = tmp_path / "shots"
    shots.mkdir()
    script = (STEPS_LAYOUT.replace("MEASURE", repr(MEASURE)).replace("EVERY", repr(EVERY.replace("PACKS", json.dumps(packs))))
              .replace("DATA", repr(data)).replace("SHOTS", repr(str(shots))).replace("CASES", repr(CASES)).replace("NARROWEST", str(NARROWEST)))
    # no tiles: nothing of the page under the corner when the pixels are counted
    out = run_ike(script, settings={"ui_scheme": "theme:ike", "language": "it", "newtab_tiles": "none"},
                  env=NO_NETWORK, timeout=300)
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QGuiApplication.instance() or QGuiApplication([])
    for name, (m, path, zoom) in out["layout"].items():
        sym, txt, w, clock, more = m["sym"], m["txt"], m["weather"], m["clock"], m["more"]
        mid = lambda b: (b[1] + b[3]) / 2                                               # noqa: E731
        # the boxes: the symbol and the text on the same middle line, side by side, the block flush right
        assert abs(mid(sym) - mid(txt)) <= 1, (name, sym, txt)
        assert sym[2] + 6 <= txt[0], (name, sym, txt)
        assert abs(w[2] - clock[2]) <= 1.5 and w[0] >= 0 and w[2] <= m["vw"], (name, w, clock)
        # a small window or a large zoom: the details give way (nothing else of the block changes)
        if m["vh"] <= 540 or m["vw"] <= 820:
            assert m["shown"] == "none" and more[2] - more[0] == 0 and m["off"] == "", name
        elif name not in SHOWN:                                                         # would meet the figures
            assert m["shown"] == "none" and m["off"] == "crowded", name
        else:
            assert m["shown"] == "flex" and abs(more[2] - clock[2]) <= 1.5 and more[0] >= 0 and more[3] <= m["vh"], name
            assert len(m["items"]) == 5
            st, co = m["stats"], m["corner"]
            assert st[2] <= co[0] or co[1] >= st[3], (name, st, co)                     # clear of the figures
        if name == "1100x760-1.5":
            assert sym[3] - sym[1] < 75, sym                                             # the symbol smaller
        # the details: one row, each symbol on its value's middle line, all on one middle line, in order
        shown = m["shown"] != "none"
        for icon, val in zip(m["icons"], m["vals"]) if shown else ():
            assert abs(mid(icon) - mid(val)) <= 1 and icon[2] <= val[0], (name, icon, val)
        items = m["items"] if shown else []
        for a, b in zip(items, items[1:]):
            assert abs(mid(a) - mid(b)) < 0.5 and a[2] + 10 <= b[0], (name, a, b)
        # the pixels: the ink of the symbol and the ink of the text have the same middle (counted where
        # nothing else of the page is under the corner: all but the crowded windows)
        st, co = m["stats"], m["corner"]
        if not (st[2] <= co[0] or co[1] >= st[3]):
            assert name not in SHOWN, name
            continue
        image = QImage(path)
        assert not image.isNull()
        hexbg = m["bg"]
        bg = (int(hexbg[1:3], 16), int(hexbg[3:5], 16), int(hexbg[5:7], 16))
        k = image.width() / m["vw"]                                                        # device pixels per CSS pixel
        pad = int(4 * k)
        s0, s1 = _ink_rows(image, int(sym[0] * k), int(sym[2] * k), int(sym[1] * k) - pad, int(sym[3] * k) + pad, bg)
        t0, t1 = _ink_rows(image, int(txt[0] * k), int(txt[2] * k), int(txt[1] * k), int(txt[3] * k) + 1, bg)
        ink_sym, ink_txt = (s0 + s1 + 1) / 2, (t0 + t1 + 1) / 2
        assert abs(ink_sym - ink_txt) <= 2.5 * k, (name, (s0, s1), (t0, t1), m["shift"])
        assert abs(ink_sym - mid(sym) * k) <= 2 * k, (name, (s0, s1), sym)               # in the middle of its box
        # and each small symbol's ink on its value's ink middle line
        for icon, val in zip(m["icons"], m["vals"]) if shown else ():
            i0, i1 = _ink_rows(image, int(icon[0] * k), int(icon[2] * k), int(icon[1] * k) - pad, int(icon[3] * k) + pad, bg)
            v0, v1 = _ink_rows(image, int(val[0] * k), int(val[2] * k), int(val[1] * k), int(val[3] * k) + 1, bg)
            assert abs((i0 + i1) - (v0 + v1)) / 2 <= 1.5 * k, (name, (i0, i1), (v0, v1))
    assert 820 < out["every_width"] <= NARROWEST
    n, bad = out["every"]
    assert n >= 59 and not bad, bad[:5]
    del app
