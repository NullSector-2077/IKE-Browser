"""Weather for the new tab page, from Open-Meteo (https://open-meteo.com):
free, no account, no key.

Privacy:
- the system location is never asked; the user types a city in Settings;
- finding the city sends the typed name to Open-Meteo's geocoding service,
  once, when the user presses "Find";
- the weather request sends only the city's coordinates, rounded to two
  decimals, and the temperature unit; it asks for the current temperature,
  weather code and wind speed and, since 1.1.25 and in the same request, the
  wind direction, the felt temperature, the humidity, the pressure at sea
  level and the chance of precipitation (FIELDS); at most once
  every 30 minutes and only when a new tab page is shown. The wind always
  comes in km/h and is turned into mph here: no other parameter is sent;
- the answer is kept in the cache folder (weather.json).
"""

import json
import os
import time
from urllib.parse import urlencode

from PyQt6.QtCore import QObject, QUrl, pyqtSignal
from PyQt6.QtNetwork import QNetworkReply, QNetworkRequest

from .config import CACHE_DIR

FORECAST = "https://api.open-meteo.com/v1/forecast"
GEOCODING = "https://geocoding-api.open-meteo.com/v1/search"
if os.environ.get("IKE_TEST_WEATHER"):        # stand-in server for the tests
    FORECAST = os.environ["IKE_TEST_WEATHER"] + "/forecast"
    GEOCODING = os.environ["IKE_TEST_WEATHER"] + "/search"
REFRESH = 30 * 60
CACHE = CACHE_DIR / "weather.json"
# what the request asks for (Open-Meteo's "current" variables): BASIC until 1.1.24, the rest for the
# small row of details under the weather (1.1.25; a few, the owner: simple and minimalist, with the
# wind and the pressure). The last
# comes from Open-Meteo's hourly data: should the service ever refuse it (it answers 400 to the whole
# request), the request is made once more at once without it, and the details show without it.
BASIC = ("temperature_2m", "weather_code", "wind_speed_10m")
MORE = ("wind_direction_10m", "apparent_temperature", "relative_humidity_2m", "pressure_msl")
HOURLY = ("precipitation_probability",)
FIELDS = BASIC + MORE + HOURLY
KMH_PER_MPH = 1.609344
INHG_PER_HPA = 0.0295300                      # the pressure in inches of mercury, with °F (as mph goes with °F)
# 1.1.25: the units of the wind and of the pressure can be chosen in Settings; "auto" (the default)
# follows the temperature (°C: km/h and hPa; °F: mph and inHg). The service always answers in km/h and
# hPa: the conversions are done here, nothing in the request changes.
KMH_PER_MS = 3.6
KMH_PER_KN = 1.852
HPA_PER_INHG = 33.8639
HPA_PER_MMHG = 1.333224
WIND_UNITS = ("kmh", "mph", "ms", "kn")
PRESSURE_UNITS = ("hpa", "mbar", "inhg", "mmhg")
# unit -> (how many of the service's unit make one, symbol, decimals shown)
_WIND = {"kmh": (1.0, "km/h", 0), "mph": (KMH_PER_MPH, "mph", 0), "ms": (KMH_PER_MS, "m/s", 1),
         "kn": (KMH_PER_KN, "kn", 0)}
_PRESSURE = {"hpa": (1.0, "hPa", 0), "mbar": (1.0, "mbar", 0), "inhg": (HPA_PER_INHG, "inHg", 2),
             "mmhg": (HPA_PER_MMHG, "mmHg", 0)}


def _shown(value, per, decimals):
    return "%.*f" % (decimals, round(value / per, decimals))


def wind_unit(config):
    """The wind's unit key (see WIND_UNITS) from the settings: "auto" or a value that is not one follows
    the temperature unit."""
    v = config["weather_wind_unit"]
    return v if v in WIND_UNITS else ("mph" if config["weather_unit"] == "fahrenheit" else "kmh")


def pressure_unit(config):
    """The pressure's unit key (see PRESSURE_UNITS), as wind_unit."""
    v = config["weather_pressure_unit"]
    return v if v in PRESSURE_UNITS else ("inhg" if config["weather_unit"] == "fahrenheit" else "hpa")


def convert_wind(kmh, unit):
    """(text of the number, symbol) of a wind speed given in km/h."""
    per, symbol, decimals = _WIND[unit]
    return _shown(kmh, per, decimals), symbol


def convert_pressure(hpa, unit):
    """(text of the number, symbol) of a pressure given in hPa."""
    per, symbol, decimals = _PRESSURE[unit]
    return _shown(hpa, per, decimals), symbol

# WMO weather codes -> (symbol, label); labels are translated when shown
_CODES = (
    ((0,), "☀", "Clear sky"),
    ((1, 2), "⛅", "Partly cloudy"),
    ((3,), "☁", "Cloudy"),
    ((45, 48), "☁", "Fog"),
    ((51, 53, 55, 56, 57), "☂", "Drizzle"),
    ((61, 63, 65, 66, 67, 80, 81, 82), "☂", "Rain"),
    ((71, 73, 75, 77, 85, 86), "❄", "Snow"),
    ((95, 96, 99), "⚡", "Thunderstorm"),
)
# the eight points of the compass, from north clockwise (translated when shown)
COMPASS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
# what the answer's "current" block gives for the details: kept under these names
_DETAILS = (("wind_dir", "wind_direction_10m"), ("feels", "apparent_temperature"),
            ("humidity", "relative_humidity_2m"), ("pressure", "pressure_msl"),
            ("rain", "precipitation_probability"))


def describe(code):
    for codes, symbol, label in _CODES:
        if code in codes:
            return symbol, label
    return "", ""


def split_symbol(text):
    """ "☁ 12 °C · Cloudy · Rome" -> ("☁", "12 °C · Cloudy · Rome"): the symbol shown large and the
    rest (1.1.24); the page's ikeWeather() splits the same way. No symbol (an unknown weather code):
    ("", text), never a number taken for the symbol."""
    sym, _sp, rest = text.partition(" ")
    if not rest or not sym or any(c.isdigit() for c in sym):
        return "", text
    return sym, rest


def _num(v):
    """A finite number from the answer, or None (missing, null, a bool, text, NaN)."""
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v or v in (float("inf"), float("-inf")):
        return None
    return v


def compass(degrees):
    """ "NW" for 315: the point of the compass the wind comes from."""
    return COMPASS[int((degrees % 360) / 45 + 0.5) % 8]


def parse(answer):
    """What is kept of Open-Meteo's answer: the main values (ValueError, KeyError or TypeError
    when one is missing) and the details it had (a missing or broken one is left out)."""
    cur = answer["current"]
    out = {"temp": round(float(cur["temperature_2m"])), "code": int(cur["weather_code"]),
           "wind": float(cur.get("wind_speed_10m") or 0)}
    for key, field in _DETAILS:
        v = _num(cur.get(field))
        if v is not None:
            out[key] = float(v)
    return out


def details(w, T=lambda t: t):
    """The small row of details under the weather (1.1.25, like Plasma's weather widget):
    [{"k": kind, "l": label, "v": value}], each only
    when the answer had it; kind is one of feels, wind, humidity, pressure, rain (the page's symbols).
    Five at most, in one discreet row. The units are the ones chosen in Settings (w["wind_unit"],
    w["pressure_unit"]); without them they follow the temperature unit: °C with km/h and hPa, °F with
    mph and inHg (the pressure at sea level)."""
    if not w:
        return []
    out = []
    fahrenheit = w.get("unit") == "°F"
    feels = _num(w.get("feels"))
    if feels is not None:
        out.append({"k": "feels", "l": T("Feels like"), "v": "%d %s" % (round(feels), "°F" if fahrenheit else "°C")})
    wind, direction = _num(w.get("wind")), _num(w.get("wind_dir"))
    if wind is not None and direction is not None:      # the 1.1.25 answer (1.1.24's cache had the speed only)
        wu = w.get("wind_unit")
        number, symbol = convert_wind(wind, wu if wu in WIND_UNITS else ("mph" if fahrenheit else "kmh"))
        item = {"k": "wind", "l": T("Wind"), "v": "%s %s" % (number, symbol)}
        if float(number) > 0:                                   # where it comes from; none for still air
            item["v"] += " " + T(compass(direction))
        out.append(item)
    hum = _num(w.get("humidity"))
    if hum is not None:
        out.append({"k": "humidity", "l": T("Humidity"), "v": "%d%%" % round(hum)})
    pressure = _num(w.get("pressure"))
    if pressure is not None:
        pu = w.get("pressure_unit")
        number, symbol = convert_pressure(pressure, pu if pu in PRESSURE_UNITS else ("inhg" if fahrenheit else "hpa"))
        out.append({"k": "pressure", "l": T("Pressure"), "v": "%s %s" % (number, symbol)})
    rain = _num(w.get("rain"))
    if rain is not None:
        out.append({"k": "rain", "l": T("Chance of precipitation"), "v": "%d%%" % round(rain)})
    return out


def place(config):
    """(lat, lon, name) of the chosen city, or None."""
    lat, lon = config["weather_lat"], config["weather_lon"]
    if lat is None or lon is None or not config["weather_city"]:
        return None
    return round(float(lat), 2), round(float(lon), 2), config["weather_city"]


def _request(url):
    req = QNetworkRequest(QUrl(url))
    req.setAttribute(QNetworkRequest.Attribute.CookieSaveControlAttribute, False)
    req.setAttribute(QNetworkRequest.Attribute.CookieLoadControlAttribute, False)
    req.setTransferTimeout(15000)
    return req


class Weather(QObject):
    """Keeps the current weather of the chosen city; fetches it when stale."""

    changed = pyqtSignal()
    found = pyqtSignal(list)            # geocoding results: [{name, label, lat, lon}]

    def __init__(self, config, network, parent=None):
        super().__init__(parent)
        self.config = config
        self.network = network
        self._reply = None
        self._search = None
        self._last_try = 0.0
        self._fields = FIELDS           # without HOURLY once the service refused them (see _got)
        try:
            self.data = json.loads(CACHE.read_text("utf-8"))
        except (OSError, ValueError):
            self.data = {}

    def _key(self):
        p = place(self.config)
        return [p[0], p[1], self.config["weather_unit"]] if p else None

    def current(self):
        """{"temp", "unit", "code", "wind", "symbol", "label", "city"} and, when the answer had
        them, "wind_dir", "feels", "humidity", "pressure", "rain" (see details()); or None.
        Starts a refresh in the background when the data is older than 30 minutes."""
        cfg = self.config
        if not cfg["newtab_weather"] or self._key() is None:
            return None
        fresh = self.data.get("key") == self._key()
        if not fresh or time.time() - self.data.get("time", 0) > REFRESH:
            self.refresh()
        if not fresh:
            return None
        symbol, label = describe(self.data.get("code"))
        out = {"temp": self.data.get("temp"), "unit": "°F" if cfg["weather_unit"] == "fahrenheit" else "°C",
               "code": self.data.get("code"), "wind": self.data.get("wind"), "symbol": symbol, "label": label,
               "city": cfg["weather_city"], "wind_unit": wind_unit(cfg), "pressure_unit": pressure_unit(cfg)}
        for k, _field in _DETAILS:
            if _num(self.data.get(k)) is not None:
                out[k] = self.data[k]
        return out

    def refresh(self, again=False):
        key = self._key()
        # never more often than every 30 minutes, also after a failure (again: the single repeat
        # without the hourly fields, right after the service refused them)
        if key is None or self._reply is not None or (time.time() - self._last_try < REFRESH and not again):
            return
        self._last_try = time.time()
        query = {"latitude": "%.2f" % key[0], "longitude": "%.2f" % key[1],
                 "current": ",".join(self._fields)}
        if key[2] == "fahrenheit":
            query["temperature_unit"] = "fahrenheit"
        reply = self.network.get(_request(FORECAST + "?" + urlencode(query)))
        self._reply = reply
        reply.finished.connect(lambda r=reply, k=key: self._got(r, k))

    def _got(self, reply, key):
        self._reply = None
        try:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                if reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute) == 400 \
                        and self._fields == FIELDS:
                    # the service refused a field (it answers 400 to the whole request): once
                    # more, at once, without the one that comes from its hourly data
                    self._fields = BASIC + MORE
                    self.refresh(again=True)
                return
            self.data = dict(parse(json.loads(bytes(reply.readAll()).decode("utf-8"))), key=key, time=time.time())
        except (ValueError, KeyError, TypeError):
            return
        finally:
            reply.deleteLater()
        try:
            CACHE.parent.mkdir(parents=True, exist_ok=True)
            CACHE.write_text(json.dumps(self.data), "utf-8")
        except OSError:
            pass
        self.changed.emit()

    def forget(self):
        """The city changed: the old data no longer applies."""
        self.data = {}
        self._last_try = 0.0
        try:
            CACHE.unlink()
        except OSError:
            pass

    def find(self, name, language="en"):
        """Look the city name up; results come with the found signal."""
        if self._search is not None:
            self._search.abort()
        query = {"name": name.strip(), "count": "8", "format": "json", "language": language}
        reply = self.network.get(_request(GEOCODING + "?" + urlencode(query)))
        self._search = reply
        reply.finished.connect(lambda r=reply: self._found(r))

    def _found(self, reply):
        if self._search is reply:
            self._search = None
        if reply.error() == QNetworkReply.NetworkError.OperationCanceledError:
            reply.deleteLater()             # replaced by a newer search
            return
        out = []
        try:
            if reply.error() == QNetworkReply.NetworkError.NoError:
                for r in json.loads(bytes(reply.readAll()).decode("utf-8")).get("results") or []:
                    parts = [r.get("name"), r.get("admin1"), r.get("country")]
                    out.append({"name": r["name"], "lat": float(r["latitude"]),
                                "lon": float(r["longitude"]),
                                "label": ", ".join(dict.fromkeys(p for p in parts if p))})
        except (ValueError, KeyError, TypeError):
            out = []
        finally:
            reply.deleteLater()
        self.found.emit(out)
