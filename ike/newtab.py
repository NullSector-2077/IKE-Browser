"""The new tab page beyond its frame: the counter per month, the site tiles,
the Cyber look and the one-time suggestion of the Cyber theme.

Everything shown here that comes from outside (titles of pages, addresses) is
untrusted text: it is escaped, and only web addresses become links.
"""

import html
import time
from urllib.parse import quote, urlsplit

from .i18n import T

TILES = 8                     # how many tiles at most
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
            # with many bookmarks a new tile would otherwise never be among the eight shown
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


# --- the Cyber look and its suggestion -------------------------------------
def body_class(config, theme):
    """Classes of <body>: the Cyber look and its options."""
    names = []
    if theme is not None and theme.get("look") == "cyber":
        names.append("cyber")
        if config.data.get("cyber_corners", True):
            names.append("cut")
        if config.data.get("cyber_glow", True):
            names.append("glow")
        if config.data.get("newtab_grid", True):
            names.append("grid")
    return " ".join(names)


def hint_html(config, theme):
    """The suggestion to try the Cyber theme, shown until it is answered; and,
    while the theme is on trial, the way back in one click."""
    state = config.data.get("cyber_hint")
    cyber = theme is not None and theme.get("look") == "cyber"
    if state == "ask" and theme is None and (config.data.get("ui_scheme") or "system") == "system":
        text = (T("I.K.E. has a theme of its own: Cyber."), T("You can try it and go back with one click."))
        links = (("go", "ike:theme?try=cyber", T("Try the Cyber theme")), ("", "ike:theme?later=1", T("Not now")))
    elif state == "trial" and cyber:
        text = (T("This is the Cyber theme."), T("Its colours and tab shapes are in Settings, Appearance."))
        links = (("go", "ike:theme?keep=1", T("Keep it")), ("", "ike:theme?back=1", T("Back to the system theme")))
    else:
        return ""
    return '<div class="hint"><span><b>%s</b> %s</span>%s</div>' % (
        html.escape(text[0]), html.escape(text[1]),
        "".join('<a%s href="%s">%s</a>' % (' class="go"' if cls else "", href, html.escape(label))
                for cls, href, label in links))


def answer_hint(config, query):
    """Apply the answer given on the page. Returns True when the theme changed."""
    state = config.data.get("cyber_hint")
    if query.get("try") == "cyber" and state == "ask":
        config.data["ui_scheme"] = "theme:cyber"
        config.data["cyber_hint"] = "trial"
        return True
    if "back" in query and state == "trial":
        config.data["ui_scheme"] = "system"
        config.data["cyber_hint"] = "done"
        return True
    if "later" in query or "keep" in query:
        config.data["cyber_hint"] = "done"
    return False
