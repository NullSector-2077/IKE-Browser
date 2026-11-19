"""Weather for the new tab page, from Open-Meteo (https://open-meteo.com):
free, no account, no key.

Privacy:
- the system location is never asked; the user types a city in Settings;
- finding the city sends the typed name to Open-Meteo's geocoding service,
  once, when the user presses "Find";
- the weather request sends only the city's coordinates, rounded to two
  decimals, and the temperature unit; at most once every 30 minutes and only
  when a new tab page is shown;
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


def describe(code):
    for codes, symbol, label in _CODES:
        if code in codes:
            return symbol, label
    return "", ""


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
        try:
            self.data = json.loads(CACHE.read_text("utf-8"))
        except (OSError, ValueError):
            self.data = {}

    def _key(self):
        p = place(self.config)
        return [p[0], p[1], self.config["weather_unit"]] if p else None

    def current(self):
        """{"temp", "unit", "code", "symbol", "label", "city"} or None. Starts a
        refresh in the background when the data is older than 30 minutes."""
        cfg = self.config
        if not cfg["newtab_weather"] or self._key() is None:
            return None
        fresh = self.data.get("key") == self._key()
        if not fresh or time.time() - self.data.get("time", 0) > REFRESH:
            self.refresh()
        if not fresh:
            return None
        symbol, label = describe(self.data.get("code"))
        return {"temp": self.data.get("temp"), "unit": "°F" if cfg["weather_unit"] == "fahrenheit" else "°C",
                "code": self.data.get("code"), "symbol": symbol, "label": label,
                "city": cfg["weather_city"]}

    def refresh(self):
        key = self._key()
        # never more often than every 30 minutes, also after a failure
        if key is None or self._reply is not None or time.time() - self._last_try < REFRESH:
            return
        self._last_try = time.time()
        query = {"latitude": "%.2f" % key[0], "longitude": "%.2f" % key[1],
                 "current": "temperature_2m,weather_code"}
        if key[2] == "fahrenheit":
            query["temperature_unit"] = "fahrenheit"
        reply = self.network.get(_request(FORECAST + "?" + urlencode(query)))
        self._reply = reply
        reply.finished.connect(lambda r=reply, k=key: self._got(r, k))

    def _got(self, reply, key):
        self._reply = None
        try:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                return
            cur = json.loads(bytes(reply.readAll()).decode("utf-8"))["current"]
            self.data = {"key": key, "time": time.time(),
                         "temp": round(float(cur["temperature_2m"])),
                         "code": int(cur["weather_code"])}
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
