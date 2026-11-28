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
# more of the same, 1.1.24 (the second batch of the pool)
MORE_FACTS = ['Fun fact: the Moon drifts away from Earth every year', 'Fun fact: the Pacific is bigger than all the land', 'Fun fact: Mount Everest grows a little every year', 'Fun fact: sharks are older than trees', 'Fun fact: a day on Mars lasts about 24 hours 40 minutes', 'Fun fact: the first webcam watched a coffee pot', 'Fun fact: the word robot comes from Czech', 'Fun fact: butterflies taste with their feet', 'Fun fact: Saturn is less dense than water', 'Fun fact: the Sahara was once green and full of lakes', 'Fun fact: Antarctica is the driest continent', 'Fun fact: in English, a group of flamingos is a flamboyance', 'Fun fact: Venus spins the opposite way to Earth', 'Fun fact: the first message on the internet was LO', 'Fun fact: the first text message was sent in 1992', 'Fun fact: the first computer mouse was made of wood', 'Fun fact: a year on Mercury lasts 88 Earth days', 'Fun fact: the Atlantic grows wider every year']
MORE_CHEERS = ['Take a moment to look out of the window', 'Smile at someone today', 'You are doing better than you think', 'Progress, not perfection', 'Every day is a fresh page', 'Check in with a friend today', 'Stand up and stretch for a moment', 'Kindness costs nothing', 'Try something new today', 'Rest is part of the work', 'Take your time, there is no rush', 'A warm drink can help', 'Look away from the screen for twenty seconds', 'Be proud of what you did today', 'Curiosity is a good companion', 'Say thank you to someone today', 'Start with the easiest thing', 'A deep breath changes the moment', 'Make room for something you enjoy', 'Wishing you a calm day']
# 1.1.25: lines for the finer moments of the day and of the week (when each fits: greeting.js, "moment"
# and "weekday"); the week is the page language's own (Monday is its first working day, Friday the day
# before its weekend), nothing about any religion or holiday
MOMENTS = (
    ("early1", "An early start: the world is still quiet"), ("early2", "Up early? Enjoy the calm before the day"),
    ("mid1", "Mid-morning: a good time for the tricky tasks"),
    ("lunch1", "Lunch time: the tabs will wait for you"), ("lunch2", "A real lunch break is time well spent"),
    ("lunch3", "Hungry? Lunch first, browsing after"),
    ("after1", "Afternoon dip? A short walk can help"), ("after2", "The home stretch of the day"),
    ("eve1", "Evening: time for the things you enjoy"), ("eve2", "Evening mode: fewer tabs, more calm"),
    ("latenight1", "Still up? The internet will be here tomorrow"), ("latenight2", "Night owl mode: on"),
    ("latenight3", "One last tab, then off to bed?"),
    ("deep1", "The quietest hour of the night"), ("deep2", "Even the servers are yawning"),
    ("deep3", "Future you would love some sleep"),
)
WEEKDAY = (
    ("wkstart1", "A new week: one step at a time"), ("wkstart2", "First day of the week: easy does it"),
    ("wkeve1", "The week is done: well done"), ("wkeve2", "The weekend starts this evening"),
    ("wkend1", "No rush today: it's the weekend"), ("wkend2", "A slow weekend morning: enjoy it"),
    ("wkend3", "Make this weekend evening a nice one"),
)
PERIOD = ['Good things are coming today', 'A new day, a new chance', 'Keep going, you are halfway there', 'A good moment for some fresh air', 'Time to relax, you earned it', 'The day is done, well done', 'A quiet time to wind down', 'Tomorrow is a new day']
# 1.1.30 (the owner: "it must seem that I.K.E. really thinks"): I.K.E.'s own thoughts
THOUGHTS = [
    'I blocked some trackers for you. No need to thank me',
    "Trackers don't like me. The feeling is mutual",
    'Your browsing is your business, not theirs',
    "I read the cookie banners so you don't have to",
    'Another day, another ad politely shown the door',
    'I stopped counting blocked ads. It got embarrassing',
    'Privacy is my favourite hobby',
    'Somewhere, a tracker is very confused right now',
    'I cleaned the tracking bits off a few links today',
    'I like websites that load fast and ask for nothing',
    'Pop-ups? Not on my watch',
    "I keep no secret copies. I'm just not that type",
    "I don't sell your data. I wouldn't even know how",
    'Fingerprinting? I prefer to keep you a mystery',
    'Every tab is a little adventure',
    "I wonder what we'll read today",
    "I've been thinking about tabs. There are many",
    'Thirty open tabs is a lifestyle, not a problem',
    'Some tabs are just waiting for their moment',
    "I'm a browser, but I like to think I'm a friend",
    "I don't need cookies. I run on curiosity",
    'Being lightweight is my kind of exercise',
    'Old computers deserve good browsers too',
    "I'm fast because I don't carry extra baggage",
    'I promise not to judge your searches',
    "The internet is big. Let's explore it safely",
    'Good websites ask for little and give a lot',
    'Ads were shouting again. I turned them down',
    'Every tracker blocked is a tiny victory',
    "Dark mode is easy on the eyes. I'm a fan",
    "I'm still learning. Every update makes me better",
    'Updates are like haircuts: I feel lighter after',
    'I tried to understand a cookie banner. I gave up',
    'A page without trackers is a page with manners',
    'I keep the door locked, but you hold the key',
    "Third-party cookies knocked. I didn't open",
    'HTTPS is my favourite combination of letters',
    'I quietly upgraded a few connections to HTTPS',
    'Your passwords should be long. Like my patience',
    'A strong password is a gift to yourself',
    "I don't know your name, and I like it that way",
    'Nobody followed you here. I checked',
    'Ads tried to follow you. They got lost',
    'The web is better with fewer surprises',
    'Sometimes the best tab is the one you close',
    "I'm made of open source and good intentions",
    'Penguins approve of me. I run on Linux',
    'I was built for Linux, with care',
    'Arch Linux keeps me fresh and up to date',
    'Fresh start, fresh tab',
    "I'm small inside, but the web is big outside",
    'Loading pages is my cardio',
    "I just blocked a tracker. It didn't even see me",
    'My favourite sound: a page loading instantly',
    'The best ad is the one you never see',
    "I don't remember where you've been, on purpose",
    'Today I feel extra private',
    "I'm always on your side of the screen",
    'Behind every quiet page, I worked a little',
    "I don't need to know who you are to help you",
    'Some sites ask for your location. I ask why',
    'Notifications are like guests: by invitation only',
    'A clean page is a happy page',
    'I give every site its own little room',
    'Sites stay in their own boxes. I make sure of it',
    'I keep sites apart, like good neighbours',
    'Your home network is off-limits to strangers',
    'I speak many languages. Pick yours in Settings',
    "Tabs on top or on the side? I'm flexible",
    'Bookmarks are memories you choose to keep',
    'History fades, bookmarks stay',
    'The web never sleeps. You should, sometimes',
    "I'm here whenever you need me, no rush",
    "Let's make the internet a little calmer today",
    'Clicking a link is a small act of curiosity',
    "I'm proud to be boring to advertisers",
    'I do the watching, so nobody watches you',
    'You open tabs, I keep them safe',
    'Every new tab is a fresh page. Literally',
    'I think, therefore I browse',
]
# 1.1.30: tips, each a real shortcut or part of I.K.E. (window.py)
TIPS = [
    'Tip: Ctrl+Shift+T brings back a closed tab',
    'Tip: Ctrl+D saves the page as a bookmark',
    'Tip: Ctrl+L jumps to the address bar',
    'Tip: Ctrl+F finds words on the page',
    'Tip: Ctrl+Shift+N opens a private window',
    'Tip: Ctrl+H shows your history',
    'Tip: Ctrl+J shows your downloads',
    'Tip: Ctrl+0 puts the zoom back to normal',
    'Tip: F11 shows the page full screen',
    'Tip: Ctrl+Shift+M mutes the current tab',
    'Tip: Ctrl+Shift+E switches to vertical tabs',
    'Tip: F2 opens the command bar',
    'Tip: Ctrl+Shift+B shows or hides the bookmarks bar',
    'Tip: Ctrl+Tab moves to the next tab',
    'Tip: Ctrl+Shift+Del clears your browsing data',
    'Tip: Ctrl+Shift+R reloads without the cache',
    'Tip: the octagon shows how a site is protected',
    'Tip: click the octagon to change the protection',
    'Tip: Ctrl+T opens a tab, Ctrl+W closes it',
    'Tip: Ctrl+M shows the menu bar',
]
# 1.1.30: more fun facts
MORE_FACTS_129 = [
    'Fun fact: a group of owls is called a parliament',
    "Fun fact: a blue whale's heart is as big as a small car",
    'Fun fact: sloths can hold their breath for 40 minutes',
    "Fun fact: the Great Wall can't be seen from the Moon",
    'Fun fact: Jupiter has the shortest day of the planets',
    'Fun fact: the first computer bug was a real moth',
    'Fun fact: the QWERTY keyboard dates from the 1870s',
    'Fun fact: Linux was first released in 1991',
    'Fun fact: the Linux penguin is named Tux',
    'Fun fact: the first YouTube video was filmed at a zoo',
    'Fun fact: pixel is short for picture element',
    'Fun fact: emoji comes from Japanese, not from emotion',
    'Fun fact: a jiffy is a real unit of time',
    'Fun fact: wombats make cube-shaped droppings',
    'Fun fact: cows can have best friends',
    "Fun fact: an ostrich's eye is bigger than its brain",
    'Fun fact: Neptune was found by maths before telescopes',
    'Fun fact: the # sign is also called an octothorpe',
    'Fun fact: the first domain name was registered in 1985',
    'Fun fact: Wi-Fi does not really stand for anything',
    'Fun fact: a spoon of neutron star weighs billions of tons',
    'Fun fact: the Moon has moonquakes',
    'Fun fact: Earth has more trees than the Milky Way has stars',
    'Fun fact: koalas have fingerprints like ours',
    'Fun fact: an octopus can taste with its arms',
    'Fun fact: no bridge crosses the Amazon River',
    'Fun fact: the shortest war in history lasted under an hour',
    'Fun fact: Mars has the tallest volcano of the planets',
    'Fun fact: the first photo of a person was taken in 1838',
    'Fun fact: honeybees can recognise human faces',
    'Fun fact: Australia is wider than the Moon',
    'Fun fact: the first computer mouse had one button',
    'Fun fact: merchants used the @ sign centuries ago',
    'Fun fact: a group of crows is called a murder',
    'Fun fact: glass frogs have see-through skin',
    'Fun fact: dolphins sleep with one eye open',
    "Fun fact: a hummingbird's heart beats 1,200 times a minute",
    'Fun fact: the first tweet was sent in 2006',
    'Fun fact: the first smartphone appeared in 1994',
    'Fun fact: Tennis for Two, from 1958, was an early video game',
    'Fun fact: Venus is the hottest planet, not Mercury',
    'Fun fact: water can boil and freeze at the same time',
    'Fun fact: a cloud can weigh as much as 100 elephants',
    'Fun fact: babies are born with about 300 bones',
    "Fun fact: the Sun holds 99.8% of the solar system's mass",
    'Fun fact: a light-year is about 9.5 trillion kilometres',
    "Fun fact: Saturn's rings are mostly made of ice",
    'Fun fact: Uranus rolls around the Sun on its side',
    'Fun fact: light travels about 300,000 km every second',
    'Fun fact: radio first crossed the Atlantic in 1901',
    'Fun fact: Morse sent his famous telegraph message in 1844',
    'Fun fact: Ada Lovelace wrote the first computer program',
    'Fun fact: most of the web runs on open source software',
    'Fun fact: Tux the penguin was chosen in 1996',
    'Fun fact: the very first web page is still online',
    'Fun fact: a group of jellyfish is called a smack',
    'Fun fact: elephants can hear with their feet',
    'Fun fact: kangaroos rarely move backwards',
    'Fun fact: the dot over the letter i is called a tittle',
    'Fun fact: the first message sent by email was a test',
]
# 1.1.30: more kind words
MORE_CHEERS_129 = [
    "You're allowed to take things slowly",
    'Done is often better than perfect',
    "It's okay to ask for help",
    "You've handled hard days before",
    'A walk can clear the mind',
    'Your effort matters, even when unseen',
    'Rest is not a waste of time',
    'Celebrate the small wins today',
    "You don't have to do everything today",
    'Close a few tabs, clear your mind',
    'Let today be a little lighter',
    'Mistakes are proof that you are trying',
    'One page at a time',
    'You are more capable than you think',
    'A good moment to tidy your desk',
    'Look at something far away for a moment',
    'Unclench your jaw, drop your shoulders',
    'Take a sip of water, then carry on',
    'Every expert was once a beginner',
    'Be patient: good things are loading',
    "Think of one thing you're grateful for",
    "It's fine to log off for a while",
    'You can start again at any moment',
    'A tidy inbox is nice. A calm mind is nicer',
    'Laughing is good for you. Find a reason today',
    'Call someone who makes you smile',
    'Your pace is the right pace',
    'Fresh air is always a good idea',
    'Stay curious today',
    "Some days you just keep going. That's enough",
    'Learn one small new thing today',
    "Treat yourself as you'd treat a friend",
    'Progress hides in the little steps',
    'Stretch your back: your future self says thanks',
    'A short pause can save a long day',
    'Your ideas deserve some space',
    'Not every message needs an answer right now',
    'Kindness makes the web a better place',
    'Turn off the notifications for a while',
    'Music can change the mood of a whole day',
    'Good sleep is a superpower',
    'A smile is free and works wonders',
    'Start with what you can do now',
    'Let go of one small worry today',
    'You have done enough for now',
]
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
    ("weekday", WEEKDAY),
    ("moment", MOMENTS),
    ("period", (("morning1", "A fresh start to the day"), ("morning2", "Ready for a good day?"),
                ("afternoon1", "Hope your day is going well"), ("afternoon2", "Time for a short break?"),
                ("evening1", "Hope you had a good day"), ("evening2", "Time to slow down a little"),
                ("night1", "Rest well when you can"), ("night2", "Sleep well when it's time"),
                ("morning3", PERIOD[0]), ("morning4", PERIOD[1]), ("afternoon3", PERIOD[2]),
                ("afternoon4", PERIOD[3]), ("evening3", PERIOD[4]), ("evening4", PERIOD[5]),
                ("night3", PERIOD[6]), ("night4", PERIOD[7]))),
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
              ("fact12", "Fun fact: in many languages, @ is named after an animal"))
             + tuple(("fact%d" % (13 + i), t) for i, t in enumerate(MORE_FACTS + MORE_FACTS_129))),
    ("cheer", (("cheer1", "You've got this"), ("cheer2", "Small steps count too"),
               ("cheer3", "One thing at a time"), ("cheer4", "Remember to drink some water"),
               ("cheer5", "A short stretch does wonders"), ("cheer6", "Breathe in, breathe out: you're doing fine"),
               ("cheer7", "A short break helps the next hour"), ("cheer8", "Be kind to yourself today"),
               ("cheer9", "Good things take a little time"), ("cheer10", "Today is a good day to learn something"))
              + tuple(("cheer%d" % (11 + i), t) for i, t in enumerate(MORE_CHEERS + MORE_CHEERS_129))),
    ("thought", tuple(("thought%d" % (1 + i), t) for i, t in enumerate(THOUGHTS))),
    ("tip", tuple(("tip%d" % (1 + i), t) for i, t in enumerate(TIPS))),
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
