"""The greeting and the friendly messages of the new tab page (1.1.24).

Everything is decided in the page itself (ike/resources/greeting.js) from the computer's clock,
the week of the page's language and the weather the page already has (weather.py): nothing is
asked of the network. This module holds the words (English, the source of every language pack),
what the page is given, and the cleaning of what the page hands back to be kept.

What is kept, in I.K.E.'s own settings (``greeting_state``) and nowhere else: the date of the
first and of the last opening of the new tab page, the days of use, the streak of days in a row,
the usual hour of the first opening (a running average), the version last seen and which
messages were shown lately. Never a site, an address or a history entry. Nothing is kept with
the greeting switched off, and nothing leaves the computer.

Holidays are never guessed: the user chooses the traditions (``greeting_holidays``), all off
at first; a holiday is greeted on its day, in the words of the language.
"""

import json
import re

from .config import RES_DIR

# the greeting by period of the day (local time): 05:00, 12:00, 18:00, 23:00
GREETINGS = (
    ("morning", "Good morning"),
    ("afternoon", "Good afternoon"),
    ("evening", "Good evening"),
    ("night", "Good night"),
)
# the pool of friendly lines: [group, [(key, words)]]; the groups, their weights and when each
# line fits are in greeting.js (tests/test_greeting.py compares the two lists of keys)
POOL = (
    ("updated", (("updated", "I.K.E. has been updated to {version}"),)),
    ("away", (("away", "It's been a while"),)),
    ("welcome", (("welcome", "Welcome back"),)),
    ("streak", (("streak3", "%d days in a row: thank you"),
                ("streak7", "Thanks for using I.K.E. every day"))),
    ("late", (("late", "It's late: remember to rest"),)),
    ("dst", (("dst", "Tonight the clocks change"),)),
    ("season", (("spring", "Spring starts today"), ("summer", "Summer starts today"),
                ("autumn", "Autumn starts today"), ("winter", "Winter starts today"))),
    ("newmonth", (("newmonth", "A new month begins"),)),
    ("weather", (("rain", "Take an umbrella if you go out"), ("snow", "It's snowing outside: stay warm"),
                 ("fog", "Fog outside: careful if you drive"), ("wind", "Strong wind today"),
                 ("hot", "It's very hot: drink water"), ("cold", "It's very cold: dress warmly"),
                 ("sun", "Enjoy the sun"))),
    ("week", (("week", "Have a good start to the week"), ("soon", "The weekend is near"),
              ("weekend", "Have a nice weekend"))),
    ("period", (("morning1", "A fresh start to the day"), ("morning2", "Ready for a good day?"),
                ("afternoon1", "Hope your day is going well"), ("afternoon2", "Time for a short break?"),
                ("evening1", "Hope you had a good day"), ("evening2", "Time to slow down a little"),
                ("night1", "Rest well when you can"), ("night2", "Sleep well when it's time"))),
    ("fact", (("fact1", "Fun fact: the first website went online in 1991"),
              ("fact2", "Fun fact: honey never spoils"),
              ("fact3", "Fun fact: octopuses have three hearts"),
              ("fact4", "Fun fact: a day on Venus is longer than its year"),
              ("fact5", "Fun fact: bananas are berries, strawberries are not"),
              ("fact6", "Fun fact: the first email was sent in 1971"),
              ("fact7", "Fun fact: sunlight takes about 8 minutes to reach us"),
              ("fact8", "Fun fact: lightning is hotter than the Sun's surface"),
              ("fact9", "Fun fact: the first web browser was called WorldWideWeb"),
              ("fact10", "Fun fact: the Eiffel Tower is taller in summer"),
              ("fact11", "Fun fact: some penguins give pebbles as gifts"),
              ("fact12", "Fun fact: in many languages, @ is named after an animal"))),
    ("cheer", (("cheer1", "You've got this"), ("cheer2", "Small steps count too"),
               ("cheer3", "One thing at a time"), ("cheer4", "Remember to drink some water"),
               ("cheer5", "A short stretch does wonders"), ("cheer6", "Breathe in, breathe out: you're doing fine"),
               ("cheer7", "A short break helps the next hour"), ("cheer8", "Be kind to yourself today"),
               ("cheer9", "Good things take a little time"), ("cheer10", "Today is a good day to learn something"))),
)
WORDS = tuple(w for _group, words in POOL for w in words)
# the greetings of the holidays (respectful, nothing more); one word per holiday, shared where the
# customary form is the same (Christmas and Easter of both Christian traditions, the two Eids)
HOLIDAY_WORDS = (
    ("newyear", "Happy New Year"), ("christmas", "Merry Christmas"), ("easter", "Happy Easter"),
    ("ramadan", "Ramadan Mubarak"), ("eid", "Eid Mubarak"), ("shana", "Shana Tova"),
    ("kippur", "Wishing you a meaningful Yom Kippur"), ("hanukkah", "Happy Hanukkah"),
    ("passover", "Happy Passover"), ("diwali", "Happy Diwali"), ("holi", "Happy Holi"),
    ("vesak", "Happy Vesak"), ("lunarny", "Happy Lunar New Year"), ("nowruz", "Happy Nowruz"),
)
# the traditions the user can choose (Settings, New tab page): id, name, the holidays it includes
TRADITIONS = (
    ("christian", "Christian (Catholic, Protestant)", "Christmas (25 December) and Easter."),
    ("orthodox", "Orthodox Christian", "Christmas (7 January) and Orthodox Easter."),
    ("islamic", "Islamic", "The start of Ramadan, Eid al-Fitr and Eid al-Adha."),
    ("jewish", "Jewish", "Rosh Hashanah, Yom Kippur, Hanukkah and Passover."),
    ("hindu", "Hindu", "Diwali and Holi."),
    ("buddhist", "Buddhist", "Vesak."),
    ("lunar", "Lunar New Year", None),
    ("nowruz", "Nowruz", None),
    ("civil", "New Year (1 January)", None),
)
TRADITION_IDS = tuple(t[0] for t in TRADITIONS)
TONES = ("friendly", "greetings")

WARM_C = 20          # "warm" for "Enjoy the sun": 20 °C, 68 °F
HOT_C = 35           # "very hot": 35 °C, 95 °F
COLD_C = -5          # "very cold": -5 °C, 23 °F
WIND_KMH = 50        # "strong wind": 50 km/h, force 7


def _celsius(temp, unit):
    return (temp - 32) * 5 / 9 if unit == "°F" else temp


def weather_kind(code, temp=None, unit="°C", wind=None):
    """What the page needs of the weather: {"k": "rain" | "snow" | "fog" | "clear" | "", "warm", "hot",
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


def holiday_tables(chosen):
    """The dates of the holidays that have no rule, for the traditions chosen (resources/holidays.json)."""
    try:
        data = json.loads((RES_DIR / "holidays.json").read_text("utf-8"))
    except (OSError, ValueError):
        return {}
    keys = []
    if "hindu" in chosen:
        keys += ["diwali", "holi"]
    if "buddhist" in chosen:
        keys.append("vesak")
    if "lunar" in chosen:
        keys.append("lunarny")
    return {k: [d for d in data.get(k, []) if isinstance(d, str) and DAY.fullmatch(d)] for k in keys}


# --- what the page hands back to be kept ---------------------------------------------------------
DAY = re.compile(r"\d{4}-\d\d-\d\d")
VERSION = re.compile(r"[0-9A-Za-z.+-]{1,24}")
GROUP_KEYS = {g: tuple(k for k, _ in words) for g, words in POOL}
ALL_KEYS = frozenset(k for keys in GROUP_KEYS.values() for k in keys)
PERIODS = tuple(k for k, _ in GREETINGS)


def _int(v, high):
    return v if isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= high else 0


def clean_state(obj):
    """The state the page sent, reduced to what the greeting keeps: nothing else gets through."""
    if not isinstance(obj, dict):
        return {}
    out = {}
    for k in ("first", "last", "upd"):
        v = obj.get(k)
        out[k] = v if isinstance(v, str) and DAY.fullmatch(v) else ""
    for k in ("ver", "updDone"):
        v = obj.get(k)
        out[k] = v if isinstance(v, str) and VERSION.fullmatch(v) else ""
    out["days"] = _int(obj.get("days"), 10 ** 6)
    out["streak"] = _int(obj.get("streak"), 10 ** 6)
    out["hn"] = _int(obj.get("hn"), 10 ** 6)
    hour = obj.get("hour")
    out["hour"] = round(float(hour), 2) if isinstance(hour, (int, float)) and not isinstance(hour, bool) \
        and 0 <= hour <= 24 else 0
    bags = obj.get("bags")
    out["bags"] = {g: [k for k in v if k in GROUP_KEYS[g]][:len(GROUP_KEYS[g])]
                   for g, v in (bags.items() if isinstance(bags, dict) else ())
                   if g in GROUP_KEYS and isinstance(v, list) and all(isinstance(k, str) for k in v)}
    cool = obj.get("cool")
    out["cool"] = {k: v for k, v in (cool.items() if isinstance(cool, dict) else ())
                   if k in ALL_KEYS and v == _int(v, 10 ** 6) and isinstance(v, int)}
    cur = obj.get("cur")
    out["cur"] = {}
    if isinstance(cur, dict) and cur.get("p") in PERIODS and cur.get("k") in ALL_KEYS \
            and isinstance(cur.get("d"), str) and DAY.fullmatch(cur["d"]):
        out["cur"] = {"p": cur["p"], "d": cur["d"], "k": cur["k"], "t": _int(cur.get("t"), 10 ** 14)}
    return out


def page_data(T, weather=None, hemisphere=0, version="", tone="friendly", chosen=(), state=None, key=""):
    """The JSON the page reads: the words (translated), the weather, the state kept, the choices.
    It sits in a script block that is not run (type application/json): no "<", ">" or "&" can
    leave it."""
    words = dict(GREETINGS)
    if tone == "friendly":
        words.update(WORDS)
    chosen = [c for c in chosen if c in TRADITION_IDS]
    if chosen:
        words.update(HOLIDAY_WORDS)
    data = {"s": {k: T(v) for k, v in words.items()}, "w": weather or {}, "h": hemisphere, "v": version,
            "tone": tone if tone in TONES else "friendly", "hol": chosen,
            "tab": holiday_tables(chosen), "st": clean_state(state), "k": key}
    text = json.dumps(data, ensure_ascii=True)
    return text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
