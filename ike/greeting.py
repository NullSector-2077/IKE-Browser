"""The greeting in the top-left corner of the new tab page (1.1.24).

Everything is decided in the page itself from the computer's clock, the week of
the page's language and the weather the page already has (weather.py): nothing
is asked of the network and nothing is recorded. The page's script
(newtab.html, ``greetFor``) and ``choose`` below are the same rules; tests
compare them over many moments.

Only what is the same in every culture is here: the time of day, the late
night, the weather and the days of the week (the weekend and the first day of
the week follow the language's own week). No holiday: dated occasions depend on
the culture and the calendar and wait for their own design. They will be one
more row of RULES (here and in the page) and of WORDS.

The words are given to the page as data (a JSON blob), never as script.
"""

import json

# the greeting by period of the day (local time)
GREETINGS = (
    ("morning", "Good morning"),         # 05:00-11:59
    ("afternoon", "Good afternoon"),     # 12:00-17:59
    ("evening", "Good evening"),         # 18:00-22:59
    ("night", "Good night"),             # 23:00-04:59
)
WORDS = (
    ("updated", "I.K.E. has been updated to {version}"),
    ("away", "It's been a while"),
    ("welcome", "Welcome back"),
    ("late", "It's late: remember to rest"),
    ("rain", "Take an umbrella if you go out"),
    ("snow", "It's snowing outside: stay warm"),
    ("fog", "Fog outside: careful if you drive"),
    ("wind", "Strong wind today"),
    ("hot", "It's very hot: drink water"),
    ("cold", "It's very cold: dress warmly"),
    ("sun", "Enjoy the sun"),
    ("dst", "Tonight the clocks change"),
    ("spring", "Spring starts today"),
    ("summer", "Summer starts today"),
    ("autumn", "Autumn starts today"),
    ("winter", "Winter starts today"),
    ("week", "Have a good start to the week"),
    ("soon", "The weekend is near"),
    ("weekend", "Have a nice weekend"),
)
WARM_C = 20          # "warm" for "Enjoy the sun": 20 °C, 68 °F
HOT_C = 35           # "very hot": 35 °C, 95 °F
COLD_C = -5          # "very cold": -5 °C, 23 °F
WIND_KMH = 50        # "strong wind": 50 km/h, force 7
AWAY_DAYS = 3        # "It's been a while": not opened for 3 days
# the week of a region comes from the page (Intl weekInfo); days: 1 = Monday ... 7 = Sunday
DEFAULT_WEEK = {"first": 1, "weekend": [6, 7]}


def period(hour):
    if 5 <= hour < 12:
        return "morning"
    if 12 <= hour < 18:
        return "afternoon"
    if 18 <= hour < 23:
        return "evening"
    return "night"


def work_week_start(week):
    """The first day of the week that is not a weekend day (Monday for most, Sunday where the
    weekend is Friday and Saturday)."""
    day = week["first"]
    for _ in range(7):
        if day not in week["weekend"]:
            return day
        day = day % 7 + 1
    return week["first"]


def day_before_weekend(week):
    """The day before the weekend begins (Friday for most), or 0 with no weekend."""
    days = week["weekend"]
    for d in days:
        before = (d - 2) % 7 + 1
        if before not in days:
            return before
    return 0


def _celsius(temp, unit):
    return (temp - 32) * 5 / 9 if unit == "°F" else temp


def weather_kind(code, temp=None, unit="°C", wind=None):
    """What the page needs of the weather: {"k": "rain" | "snow" | "fog" | "clear", "warm", "hot",
    "cold", "wind": bool} or {} (no data). wind in km/h."""
    if not isinstance(code, int) or isinstance(code, bool):
        return {}
    kind = ""
    if code in (51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82, 95, 96, 99):
        kind = "rain"
    elif code in (71, 73, 75, 77, 85, 86):
        kind = "snow"
    elif code in (45, 48):
        kind = "fog"
    elif code == 0:
        kind = "clear"
    out = {"k": kind, "warm": False, "hot": False, "cold": False, "wind": False}
    if isinstance(temp, (int, float)) and not isinstance(temp, bool):
        c = _celsius(temp, unit)
        out["warm"], out["hot"], out["cold"] = c >= WARM_C, c >= HOT_C, c <= COLD_C
    if isinstance(wind, (int, float)) and not isinstance(wind, bool):
        out["wind"] = wind >= WIND_KMH
    return out


def season_of(month, day, hemisphere):
    """The season that starts on this day (meteorological: the 1st of March, June, September and
    December; swapped in the south), or None. hemisphere: 1 north, -1 south, 0 not known (None)."""
    if day != 1 or hemisphere not in (1, -1) or month not in (3, 6, 9, 12):
        return None
    north = {3: "spring", 6: "summer", 9: "autumn", 12: "winter"}[month]
    if hemisphere == 1:
        return north
    return {"spring": "autumn", "summer": "winter", "autumn": "spring", "winter": "summer"}[north]


# the second line: the first rule that fits wins, nothing otherwise
RULES = (
    ("updated", lambda c: bool(c["updated"])),                                  # the day of an update
    ("away", lambda c: c["gap"] >= AWAY_DAYS),                                  # first opening, 3+ days
    ("welcome", lambda c: c["gap"] >= 1),                                       # first opening of the day
    ("late", lambda c: 1 <= c["hour"] < 5),                                     # 01:00-04:59
    ("dst", lambda c: c["dst"] and c["hour"] >= 18),                            # the evening before
    ("spring", lambda c: c["season"] == "spring"),
    ("summer", lambda c: c["season"] == "summer"),
    ("autumn", lambda c: c["season"] == "autumn"),
    ("winter", lambda c: c["season"] == "winter"),
    ("rain", lambda c: c["weather"].get("k") == "rain"),                        # rain, drizzle, a storm
    ("snow", lambda c: c["weather"].get("k") == "snow"),
    ("fog", lambda c: c["weather"].get("k") == "fog"),
    ("wind", lambda c: bool(c["weather"].get("wind"))),
    ("hot", lambda c: bool(c["weather"].get("hot"))),
    ("cold", lambda c: bool(c["weather"].get("cold"))),
    ("sun", lambda c: c["weather"].get("k") == "clear" and bool(c["weather"].get("warm"))
     and 7 <= c["hour"] < 19),                                                  # clear and warm, by day
    ("week", lambda c: c["day"] == work_week_start(c["week"]) and 5 <= c["hour"] < 12),
    ("soon", lambda c: c["day"] == day_before_weekend(c["week"])),
    ("weekend", lambda c: c["day"] in c["week"]["weekend"]),
)


def choose(hour, weekday, weather=None, week=None, gap=0, updated="", dst=False, season=None):
    """(period, string key of the second line or None). weekday: 1 = Monday ... 7 = Sunday
    (datetime.isoweekday()); week: {"first", "weekend": [days]}, Monday first and Saturday and
    Sunday off when not known; gap: days since the new tab page was last opened (-1 never);
    updated: the version, on the day of an update; dst: the clocks change tonight; season: what
    season_of says."""
    ctx = {"hour": hour, "day": weekday, "weather": weather or {}, "week": week or DEFAULT_WEEK,
           "gap": gap, "updated": updated, "dst": dst, "season": season}
    for key, test in RULES:
        if test(ctx):
            return period(hour), key
    return period(hour), None


def page_data(T, weather=None, gap=0, version="", hemisphere=0):
    """The JSON the page reads: the words (translated), the weather, the days since the page was
    last opened, the version on the day of an update and the hemisphere (0 = the page works it out
    from the time zone). It sits
    in a script block that is not run (type application/json): no "<", ">" or
    "&" can leave it."""
    words = {k: T(v) for k, v in GREETINGS + WORDS}
    data = json.dumps({"s": words, "w": weather or {}, "g": gap, "v": version, "h": hemisphere}, ensure_ascii=True)
    return data.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
