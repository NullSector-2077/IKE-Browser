"""Dark Reader's lists, kept up to date by I.K.E. itself (1.1.27, the owner's
decision: "no new version every day for simple lists").

Dark Reader's site fixes, its list of sites that are dark already and the
hints that recognise a site's own dark theme change almost every day. Until
1.1.26 each change made a new version of I.K.E. (the daily maintenance rebuilt
ike/resources/darkreader-data.json). Now the browser fetches the three lists
from Dark Reader's repository once a day, as it fetches the filter lists, and
uses them in place of the copy it came with; a new version is made only for a
new Dark Reader engine.

What is fetched is read the way tools/build-darkreader.py reads it (the same
functions: the builder imports them from here) and checked the same way
before anything uses it: data for Dark Reader only (CSS for a style element,
selectors, flags), nothing that could be a script, the common fix first, and
lists not much shorter than the copy I.K.E. came with (a cut or broken
download is refused). Https only, from raw.githubusercontent.com only, no
cookies, the browser's own User-Agent; nothing about the user is sent. A
download that fails or is refused changes nothing: the lists in use stay.

No Qt here except the background thread (made when a download starts), so
the builder can import this module.
"""

import json
import re
import time
from urllib.parse import urlsplit

SOURCE = "https://raw.githubusercontent.com/darkreader/darkreader/main/src/config/"
FILES = {"fixes": "dynamic-theme-fixes.config", "dark_sites": "dark-sites.config",
         "detector_hints": "detector-hints.config"}
HOST = "raw.githubusercontent.com"
MAX_BYTES = 8 * 1024 * 1024
UPDATE_INTERVAL = 24 * 3600
RETRY_FAILED_AFTER = 3 * 3600
# a list fetched with less than this share of the entries of the copy I.K.E.
# came with is taken for a broken download (Dark Reader's lists only grow)
MIN_SHARE = 0.5
STORE_NAME = "darkreader-lists.json"


# --- reading Dark Reader's lists (shared with tools/build-darkreader.py) ----------

FIX_COMMANDS = {"INVERT": "invert", "CSS": "css", "IGNORE INLINE STYLE": "ignoreInlineStyle",
                "IGNORE IMAGE ANALYSIS": "ignoreImageAnalysis", "IGNORE CSS URL": "ignoreCSSUrl"}
HINT_COMMANDS = {"TARGET": "target", "MATCH": "match", "NO DARK THEME": "noDarkTheme",
                 "SYSTEM THEME": "systemTheme", "IFRAME": "iframe"}
COMMAND_LINE = re.compile(r"^[A-Z]+(\s[A-Z]+){0,2}$")
# what can never be in data for Dark Reader (CSS, selectors, flags)
DATA_SCRIPT_MARKS = ("<script", "</style", "javascript:", "vbscript:", "expression(", "-moz-binding",
                     "behavior:", "data:text/html", "data:text/javascript", "data:application/javascript",
                     "onload=", "onerror=")


def parse_array(text):
    return [s.strip() for s in text.replace("\r", "").split("\n") if s.strip()]


def parse_blocks(text, commands, value):
    """Dark Reader's parseSitesFixesConfig, in Python."""
    out = []
    for block in re.split(r"^\s*={2,}\s*$", text.replace("\r", ""), flags=re.M):
        lines = block.split("\n")
        marks = [i for i, ln in enumerate(lines) if COMMAND_LINE.match(ln)]
        if not marks:
            continue
        entry = {"url": parse_array("\n".join(lines[:marks[0]]))}
        for n, i in enumerate(marks):
            command = lines[i].strip()
            end = marks[n + 1] if n + 1 < len(marks) else len(lines)
            prop = commands.get(command)
            if prop:
                entry[prop] = value(command, "\n".join(lines[i + 1:end]))
        out.append(entry)
    return out


def fix_value(command, text):
    return text.strip() if command == "CSS" else parse_array(text)


def hint_value(command, text):
    if command == "TARGET":
        return text.strip()
    if command in ("NO DARK THEME", "SYSTEM THEME"):
        return True
    return parse_array(text)


def parse(texts):
    """The three lists from the texts of Dark Reader's three files (keyed as FILES)."""
    return {"fixes": parse_blocks(texts["fixes"], FIX_COMMANDS, fix_value),
            "dark_sites": parse_array(texts["dark_sites"]),
            "detector_hints": parse_blocks(texts["detector_hints"], HINT_COMMANDS, hint_value)}


def data_problems(data):
    """What in the lists is not data for Dark Reader: unknown fields, values
    that are not text, anything that looks like a script ([] when none)."""
    allowed = {"fixes": {"url"} | set(FIX_COMMANDS.values()), "detector_hints": {"url"} | set(HINT_COMMANDS.values())}
    out = []
    for part, keys in allowed.items():
        if not isinstance(data.get(part), list):
            out.append("%s: not a list" % part)
            continue
        for n, entry in enumerate(data[part]):
            if not isinstance(entry, dict):
                out.append("%s[%d]: not an entry" % (part, n))
                continue
            if set(entry) - keys:
                out.append("%s[%d]: unknown fields %s" % (part, n, sorted(set(entry) - keys)))
            for key, value in entry.items():
                values = value if isinstance(value, list) else [value]
                for v in values:
                    if v is True:
                        continue
                    if not isinstance(v, str):
                        out.append("%s[%d].%s: not text" % (part, n, key))
                        continue
                    low = re.sub(r"\s+", "", v.lower())
                    hit = next((m for m in DATA_SCRIPT_MARKS if m.replace(" ", "") in low), "")
                    if hit:
                        urls = entry.get("url") if isinstance(entry.get("url"), list) else []
                        out.append("%s[%d].%s (%s): %r" % (part, n, key, ", ".join(map(str, urls[:2]))[:80], hit))
    if not isinstance(data.get("dark_sites"), list) or not all(isinstance(s, str) for s in data["dark_sites"]):
        out.append("dark_sites: not text")
    return out


def check(lists, bundled=None):
    """Why the fetched lists cannot be used, or "" (bundled: the copy I.K.E. came with)."""
    problems = data_problems(lists)
    if problems:
        return "not data for Dark Reader: %s" % "; ".join(problems[:3])
    fixes = lists["fixes"]
    if not fixes or fixes[0].get("url", [])[:1] != ["*"]:
        return "the site fixes do not start with the common fix"
    if bundled:
        for part in FILES:
            have = len(bundled.get(part) or ())
            if have and len(lists[part]) < have * MIN_SHARE:
                return "%s: %d entries where I.K.E. came with %d" % (part, len(lists[part]), have)
    return ""


# --- the copy fetched by the browser ----------------------------------------------

def store_path():
    from .config import DATA_DIR
    return DATA_DIR / STORE_NAME


def load_fetched():
    """The lists the browser fetched ({"lists_date", "fetched", "fixes", ...}), or None."""
    try:
        d = json.loads(store_path().read_text("utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(d, dict) or not isinstance(d.get("lists_date"), str) or check(d):
        return None
    return d


def newer_than(fetched, bundled):
    """Are the fetched lists at least as new as the copy I.K.E. came with?"""
    return bool(fetched) and fetched.get("lists_date", "") >= (bundled or {}).get("lists_date", "")


def fetch(bundled=None, opener=None):
    """Fetch, read and check the three lists (blocking; the background thread
    runs it). Returns the lists to store, or raises ValueError with the reason."""
    if opener is None:
        from . import doh
        opener = doh.urlopen
    import urllib.request

    from . import osinfo
    texts = {}
    for part, name in FILES.items():
        url = SOURCE + name
        req = urllib.request.Request(url, headers={"User-Agent": osinfo.browser_user_agent()})
        with opener(req, timeout=40) as r:
            final = urlsplit(r.geturl())
            if final.scheme != "https" or (final.hostname or "").lower() != HOST:
                raise ValueError("%s: redirected away from %s" % (name, HOST))
            length = r.headers.get("Content-Length")
            if length and int(length) > MAX_BYTES:
                raise ValueError("%s: too large" % name)
            raw = r.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES or b"\x00" in raw:
            raise ValueError("%s: too large or not text" % name)
        texts[part] = raw.decode("utf-8")
    lists = parse(texts)
    why = check(lists, bundled)
    if why:
        raise ValueError(why)
    lists["lists_date"] = time.strftime("%Y-%m-%d", time.gmtime())
    lists["fetched"] = int(time.time())
    return lists


def save(lists):
    path = store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(lists, separators=(",", ":")), "utf-8")
    tmp.replace(path)


def needs_update(config):
    if not config["auto_update"]:
        return False
    return time.time() - (config.get("last_darklists_update") or 0) > UPDATE_INTERVAL


def make_thread(bundled, parent=None):
    """A background thread that fetches, checks and stores the lists; its
    signal done(ok, reason) comes back on the thread that made it."""
    from PyQt6.QtCore import QThread, pyqtSignal

    class Fetch(QThread):
        done = pyqtSignal(bool, str)

        def run(self):
            try:
                save(fetch(bundled))
                self.done.emit(True, "")
            except Exception as e:          # the lists in use stay as they are
                self.done.emit(False, str(e)[:300])

    return Fetch(parent)
