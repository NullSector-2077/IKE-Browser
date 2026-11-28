"""The new tab page beyond its frame: the counter per month and the site tiles.

Everything shown here that comes from outside (titles of pages, addresses) is
untrusted text: it is escaped, and only web addresses become links.
"""

import html
import time
from urllib.parse import quote, urlsplit

from .i18n import T

TILES = 32                    # how many tiles at most: two rows of 16 on a wide window
HIDDEN_MAX = 200              # hidden tiles remembered


# --- the counter per month -------------------------------------------------
def month_key(now=None):
    return time.strftime("%Y-%m", time.localtime(now))


def _before(key):
    """The month before "YYYY-MM"."""
    try:
        y, m = int(key[:4]), int(key[5:7])
    except (ValueError, TypeError):
        return ""
    return "%04d-%02d" % ((y, m - 1) if m > 1 else (y - 1, 12))


def _month(config):
    m = config.data.get("blocked_month")
    if not isinstance(m, dict):
        m = {}
    count, prev = m.get("count", 0), m.get("prev", 0)
    return {"key": m.get("key") if isinstance(m.get("key"), str) else "",
            "count": count if isinstance(count, int) and not isinstance(count, bool) and count >= 0 else 0,
            "prev_key": m.get("prev_key") if isinstance(m.get("prev_key"), str) else "",
            "prev": prev if isinstance(prev, int) and not isinstance(prev, bool) and prev >= 0 else 0}


def roll(config, now=None):
    """Start a new month when the calendar did. Returns the month's record."""
    m = _month(config)
    key = month_key(now)
    if m["key"] != key:
        # the month that just ended is kept for the "last month" figure, but only
        # if it really was the month before (the browser may have been unused for long)
        ended = m["key"] == _before(key)
        m = {"key": key, "count": 0,
             "prev_key": m["key"] if ended else "", "prev": m["count"] if ended else 0}
    config.data["blocked_month"] = m
    return m


_known = [0.0, ""]            # until when (epoch) the current month's key is known, and that key


def count_blocked(config, now=None):
    """One more tracker or ad blocked. Called for every blocked request, so the
    calendar is looked at once a month, not each time."""
    config.data["blocked_total"] += 1
    if now is None:
        m = config.data.get("blocked_month")
        if time.time() < _known[0] and type(m) is dict and m.get("key") == _known[1] and type(m.get("count")) is int:
            m["count"] += 1
            return
    roll(config, now)["count"] += 1
    if now is None:
        t = time.localtime()
        _known[0] = time.mktime((t.tm_year, t.tm_mon + 1, 1, 0, 0, 0, 0, 0, -1))      # the first of next month
        _known[1] = month_key()


def month_name(key):
    """ "November" for "2026-11", in the language of the interface."""
    names = ("January", "February", "March", "April", "May", "June", "July", "August",
             "September", "October", "November", "December")
    try:
        return T(names[int(key[5:7]) - 1])
    except (ValueError, IndexError, TypeError):
        return ""


def _number(n):
    return "{:,}".format(int(n)).replace(",", ".")


def stats_html(config, level_label, level, now=None):
    """The figures under the search field."""
    cells = []
    if config.data.get("blocked_counter") == "total":
        cells.append((_number(config["blocked_total"]), T("trackers and ads blocked"), True))
    else:
        m = roll(config, now)
        cells.append((_number(m["count"]), T("blocked in %s") % month_name(m["key"]), True))
        if m["prev_key"]:
            cells.append((_number(m["prev"]), month_name(m["prev_key"]), False))
    out = []
    for value, label, main in cells:
        out.append('<div%s><b class="num" data-n="%s">%s</b><span>%s</span></div>' % (
            ' class="main"' if main else "", value.replace(".", ""), value, html.escape(label)))
    out.append('<div><b>%s</b><span>%s</span></div>' % (html.escape(level), html.escape(level_label)))
    return "".join(out)


# --- site tiles -------------------------------------------------------------
def web_address(text):
    """A clean http(s) address from what the user typed, or ""."""
    text = (text or "").strip()
    if not text or any(c in text for c in " \t\r\n\"'<>`\\"):
        return ""
    if "://" not in text:
        # "example.org" or "example.org:8080/x"; anything else with a colon before
        # the path is another kind of address ("javascript:…", "data:…")
        head = text.split("/", 1)[0]
        if ":" in head and not head.rsplit(":", 1)[1].isdigit():
            return ""
        text = "https://" + text
    try:
        parts = urlsplit(text)
        host = parts.hostname or ""
        parts.port                                # a port that is not a number raises
    except ValueError:
        return ""
    if parts.scheme not in ("http", "https") or len(text) > 2000:
        return ""
    if not host or not all(c.isalnum() or c in "-." for c in host) or parts.username or parts.password:
        return ""
    return text


def _host(url):
    try:
        return (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


def _name(host):
    return host[4:] if host.startswith("www.") else host


def tiles(config, storage):
    """[(address, title)] for the tiles: bookmarks, most visited sites, or none."""
    mode = config.data.get("newtab_tiles")
    if mode not in ("bookmarks", "visited") or storage is None:
        return []
    hidden = config.data.get("newtab_tiles_hidden")
    hidden = set(h for h in hidden if isinstance(h, str)) if isinstance(hidden, list) else set()
    found, seen = [], set()
    if mode == "bookmarks":
        rows = list(storage.bookmarks())
        first = config.data.get("newtab_tiles_first")
        first = [u for u in first if isinstance(u, str)] if isinstance(first, list) else []
        if first:
            # the sites added from the page itself come first, the newest before the others:
            # with many bookmarks a new tile would otherwise never be among those shown
            rank = {u: i for i, u in enumerate(first)}
            rows.sort(key=lambda row: rank.get(row[0], len(rank)))
        for url, title, _folder in rows:
            url = web_address(url)
            if url and url not in hidden and url not in seen:
                seen.add(url)
                title = (title or "").strip()
                found.append((url, _name(_host(url)) if not title or "://" in title else title))
            if len(found) >= TILES:
                break
    else:
        for url, _title in storage.most_visited(400):
            host = _host(web_address(url))
            if not host:
                continue
            site = "%s://%s/" % (urlsplit(url).scheme, host)
            if _name(host) in seen or site in hidden:
                continue
            seen.add(_name(host))
            found.append((site, _name(host)))
            if len(found) >= TILES:
                break
    return found


def tiles_html(config, storage):
    mode = config.data.get("newtab_tiles")
    if mode not in ("bookmarks", "visited"):
        return ""
    out = ['<div class="tiles">']
    for url, title in tiles(config, storage):
        host = _host(url)
        letter = (_name(host)[:1] or "?").upper()
        out.append(
            '<div class="tile"><a href="%s" title="%s"><span class="ico"><i>%s</i>'
            '<img src="ike:favicon?h=%s" alt="" onerror="this.remove()"></span>'
            '<span class="name">%s</span></a>'
            '<a class="hide" href="ike:tile?hide=%s" title="%s" aria-label="%s">×</a></div>' % (
                html.escape(url, quote=True), html.escape(url, quote=True), html.escape(letter),
                quote(host, safe=""), html.escape(title[:60]), quote(url, safe=""),
                html.escape(T("Hide this tile"), quote=True), html.escape(T("Hide this tile"), quote=True)))
    if mode == "bookmarks":
        out.append(
            # a real button opens the field (see the page's script): a hidden field cannot be
            # reached by clicking its label, which is why the first version did nothing
            '<form class="tile add" action="ike:tile" method="get"><button type="button" class="open" '
            'aria-expanded="false"><span class="ico">+</span><span class="name">%s</span></button>'
            '<input name="add" autocomplete="off" spellcheck="false" placeholder="%s" aria-label="%s"></form>' % (
                html.escape(T("Add")), html.escape(T("address of the site"), quote=True),
                html.escape(T("Address of the site to add"), quote=True)))
    out.append("</div>")
    return "".join(out)


def engines_html(config):
    """The engine picker of the search box (1.1.10): the default engine's own
    icon; a click lists the installed engines with theirs, and the one chosen
    (ike:engine) becomes the default. Until an engine's icon is known a
    magnifier shows."""
    from .config import RES_DIR
    try:
        lens = (RES_DIR / "icons" / "sets" / "lucide" / "edit-find.svg").read_text("utf-8").strip()
    except OSError:
        lens = ""

    def ico(e):
        return ('<span class="eng-ico">%s<img src="ike:favicon?h=%s" alt="" '
                'onerror="ikeIconLater(this)" onload="this.style.visibility=\'visible\'"></span>' % (
                    lens, quote(_host(e.get("url", "")), safe="")))
    engines = [e for e in config["search_engines"] if isinstance(e, dict) and e.get("name")]
    current = config.engine()
    label = html.escape(T("Default search engine"), quote=True)
    rows = []
    for e in engines:
        on = e["name"] == current.get("name")
        rows.append('<a role="menuitemradio" aria-checked="%s" href="ike:engine?name=%s">%s'
                    '<span class="eng-name">%s</span><span class="eng-tick">%s</span></a>' % (
                        "true" if on else "false", quote(e["name"], safe=""), ico(e),
                        html.escape(e["name"]), "\u2713" if on else ""))
    return ('<div class="eng"><button type="button" class="eng-btn" aria-haspopup="menu" aria-expanded="false" '
            'title="%s: %s" aria-label="%s">%s<span class="eng-arrow">\u25be</span></button>'
            '<div class="eng-menu" role="menu" aria-label="%s">%s</div></div>' % (
                label, html.escape(current.get("name", ""), quote=True), label, ico(current), label, "".join(rows)))


def hide_tile(config, url):
    hidden = config.data.get("newtab_tiles_hidden")
    hidden = [h for h in hidden if isinstance(h, str)] if isinstance(hidden, list) else []
    if url and url not in hidden:
        hidden.append(url[:2000])
    config.data["newtab_tiles_hidden"] = hidden[-HIDDEN_MAX:]


def put_first(config, url):
    """A site added with the "Add" tile: its tile is the first one, and is shown again if it was hidden."""
    first = config.data.get("newtab_tiles_first")
    first = [u for u in first if isinstance(u, str) and u != url] if isinstance(first, list) else []
    config.data["newtab_tiles_first"] = ([url] + first)[:TILES * 4]
    hidden = config.data.get("newtab_tiles_hidden")
    if isinstance(hidden, list) and url in hidden:
        config.data["newtab_tiles_hidden"] = [h for h in hidden if h != url]


# --- the page's own small panels (1.1.31) -------------------------------------
# The owner: "a small panel in I.K.E./KDE style, with its own settings, so that the new tab
# page is customised from the new tab page itself". A gear beside the corner (clock and
# weather) and one beside the counter open a small panel; each choice in it is a link of the
# page itself (ike:ntset, with the session's key, see shields.py) that changes one of the
# settings below to one of its values, nothing else, and shows the page again. The texts are
# the Settings window's own, so every language already has them.
def _panel_settings():
    from .config import WEATHER_CHOICES
    out = {"newtab_clock": ("1", "0"), "newtab_weather": ("1", "0"),
           "blocked_counter": ("month", "total"), "newtab_tiles": ("bookmarks", "visited", "none"),
           "newtab_tiles_hidden": ("clear",)}
    out.update(WEATHER_CHOICES)
    return out


PANEL_SETTINGS = _panel_settings()
PANELS = ("corner", "stats")


def set_from_panel(config, name, value):
    """A choice made in one of the page's panels. Only the settings and values of
    PANEL_SETTINGS; returns True when a setting changed."""
    choices = PANEL_SETTINGS.get(name)
    if not choices or value not in choices:
        return False
    if name == "newtab_tiles_hidden":
        new = []
    elif choices == ("1", "0"):
        new = value == "1"
    else:
        new = value
    if config.data.get(name) == new:
        return False
    config.data[name] = new
    return True


def _set_link(name, value, which):
    return "ike:ntset?s=%s&amp;v=%s&amp;p=%s" % (name, value, which)


def _switch(config, name, label, which):
    on = bool(config.data.get(name))
    return ('<a class="np-row np-sw" role="switch" aria-checked="%s" data-s="%s" href="%s">'
            '<span class="np-l">%s</span><span class="np-knob" aria-hidden="true"></span></a>' % (
                "true" if on else "false", name, _set_link(name, "0" if on else "1", which), html.escape(label)))


def _segments(config, name, label, items, which):
    """A row of small buttons, one of them pressed (as Plasma's own)."""
    now = config.data.get(name)
    buttons = "".join('<a class="np-seg" role="radio" aria-checked="%s" data-s="%s" href="%s">%s</a>' % (
        "true" if key == now else "false", name, _set_link(name, key, which), html.escape(text))
        for key, text in items)
    return ('<div class="np-row np-choice"><span class="np-l">%s</span>'
            '<span class="np-segs" role="radiogroup" aria-label="%s">%s</span></div>' % (
                html.escape(label), html.escape(label, quote=True), buttons))


def _radios(config, name, label, items, which):
    """A short list, one line each, the chosen one marked (for the longer choices)."""
    now = config.data.get(name)
    rows = "".join('<a class="np-radio" role="radio" aria-checked="%s" data-s="%s" href="%s">'
                   '<span class="np-dot" aria-hidden="true"></span><span>%s</span></a>' % (
                       "true" if key == now else "false", name, _set_link(name, key, which), html.escape(text))
                   for key, text in items)
    return ('<div class="np-group" role="radiogroup" aria-label="%s"><div class="np-sub">%s</div>%s</div>' % (
        html.escape(label, quote=True), html.escape(label), rows))


def panel_html(config, which, gear):
    """The gear and its panel: "corner" (clock and weather) or "stats" (counter and tiles)."""
    rows = []
    if which == "corner":
        title = T("New tab page")
        rows.append(_switch(config, "newtab_clock", T("Show the clock and the date"), which))
        rows.append(_switch(config, "newtab_weather", T("Show the weather"), which))
        if config.data.get("newtab_weather"):
            city = config.data.get("weather_city") if isinstance(config.data.get("weather_city"), str) else ""
            rows.append('<a class="np-row np-city" href="ike:open?what=newtab"><span class="np-l">%s</span>'
                        '<span class="np-v">%s</span></a>' % (html.escape(T("City for the weather")),
                                                              html.escape(city[:60] or "…")))
            rows.append(_segments(config, "weather_unit", T("Temperature"),
                                  (("celsius", "°C"), ("fahrenheit", "°F")), which))
            rows.append(_segments(config, "weather_wind_unit", T("Wind"),
                                  (("auto", T("Automatic")), ("kmh", "km/h"), ("mph", "mph"), ("ms", "m/s"), ("kn", "kn")), which))
            rows.append(_segments(config, "weather_pressure_unit", T("Pressure"),
                                  (("auto", T("Automatic")), ("hpa", "hPa"), ("mbar", "mbar"), ("inhg", "inHg"),
                                   ("mmhg", "mmHg")), which))
    else:
        title = T("New tab page")
        rows.append(_radios(config, "blocked_counter", T("Blocked counter"),
                            (("month", T("This month (starts again on the first of each month)")),
                             ("total", T("Since I.K.E. was installed"))), which))
        rows.append(_radios(config, "newtab_tiles", T("Site tiles"),
                            (("bookmarks", T("My bookmarks")), ("visited", T("The sites I visit most")),
                             ("none", T("None"))), which))
        hidden = config.data.get("newtab_tiles_hidden")
        if isinstance(hidden, list) and hidden:
            rows.append('<a class="np-row np-act" data-s="newtab_tiles_hidden" href="%s">%s</a>' % (
                _set_link("newtab_tiles_hidden", "clear", which), html.escape(T("Show the hidden tiles again"))))
    label = html.escape(T("Customize…"), quote=True)
    return ('<div class="np-wrap np-%s"><button type="button" class="np-gear" aria-haspopup="dialog" '
            'aria-expanded="false" title="%s" aria-label="%s">%s</button>'
            '<div class="np" role="dialog" aria-label="%s"><div class="np-head">%s</div>%s'
            '<a class="np-foot" href="ike:open?what=newtab">%s</a></div></div>' % (
                which, label, label, gear, html.escape(title, quote=True), html.escape(title), "".join(rows),
                html.escape(T("Settings"))))
