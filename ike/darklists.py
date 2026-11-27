"""Fetch Dark Reader's compatibility lists for the next I.K.E. launch."""

import json
import os
import re
import tempfile
import time
import urllib.request
from datetime import datetime

from PyQt6.QtCore import QThread

from . import doh
from .config import CACHE_DIR

CACHE = CACHE_DIR / "darkreader-lists.json"
HEAD = "https://api.github.com/repos/darkreader/darkreader/commits/main"
RAW = "https://raw.githubusercontent.com/darkreader/darkreader/"
FILES = ("dynamic-theme-fixes.config", "dark-sites.config", "detector-hints.config")
LIMIT = 2 * 1024 * 1024
INTERVAL = 24 * 3600

FIX_FIELDS = {"INVERT": "invert", "CSS": "css", "IGNORE INLINE STYLE": "ignoreInlineStyle",
              "IGNORE IMAGE ANALYSIS": "ignoreImageAnalysis", "IGNORE CSS URL": "ignoreCSSUrl"}
HINT_FIELDS = {"TARGET": "target", "MATCH": "match", "NO DARK THEME": "noDarkTheme",
               "SYSTEM THEME": "systemTheme", "IFRAME": "iframe"}
COMMAND = re.compile(r"^[A-Z]+(?: [A-Z]+){0,2}$")
# Reject constructs that can create external CSS requests, including escaped
# or comment-split spellings. The bundled fixes remain available for these.
EXTERNAL_CSS = re.compile(r"[@\\]|/\*|\b(?:url|src|image|image-set)\s*\(", re.I)
SELECTOR_BREAKOUT = re.compile(r"[{};\\]")


def _lines(text):
    return [line.strip() for line in text.splitlines() if line.strip()]


def _blocks(text, fields):
    for block in re.split(r"^[ \t]*={2,}[ \t]*$", text.replace("\r", ""), flags=re.M):
        lines = block.split("\n")
        marks = [i for i, line in enumerate(lines) if COMMAND.fullmatch(line)]
        if not marks:
            continue
        entry = {"url": _lines("\n".join(lines[:marks[0]]))}
        for start, end in zip(marks, marks[1:] + [len(lines)]):
            name = fields.get(lines[start])
            if not name:
                continue
            value = "\n".join(lines[start + 1:end]).strip()
            if name in ("noDarkTheme", "systemTheme"):
                entry[name] = True
            elif name in ("css", "target"):
                entry[name] = value
            else:
                entry[name] = [item for item in _lines(value)
                               if len(item) <= 2048 and not SELECTOR_BREAKOUT.search(item)]
        yield entry


def _revision(commit, date):
    if not isinstance(commit, str) or not re.fullmatch(r"[a-f0-9]{40}", commit):
        raise ValueError("invalid Dark Reader revision")
    if not isinstance(date, str):
        raise ValueError("invalid Dark Reader revision date")
    datetime.strptime(date, "%Y-%m-%dT%H:%M:%SZ")


def unpack(snapshot, bundled):
    """Validate downloaded text and build the two engines' shared data."""
    commit, date = snapshot["commit"], snapshot["date"]
    _revision(commit, date)
    texts = snapshot["texts"]
    if (not isinstance(texts, list) or len(texts) != len(FILES)
            or not all(isinstance(t, str) and 0 < len(t) <= LIMIT for t in texts)):
        raise ValueError("invalid Dark Reader list size")
    if date[:10] < bundled.get("lists_date", ""):
        raise ValueError("Dark Reader lists are older than the bundle")
    known_regex = {url for key in ("fixes", "detector_hints") for entry in bundled[key]
                   for url in entry["url"] if url.startswith("/")}
    known_regex.update(url for url in bundled["dark_sites"] if url.startswith("/"))

    def patterns(values):
        return [v for v in values if len(v) <= 512 and (not v.startswith("/") or v in known_regex)]

    fixes = list(_blocks(texts[0], FIX_FIELDS))
    dark = patterns(_lines(texts[1]))
    hints = list(_blocks(texts[2], HINT_FIELDS))
    if not fixes or fixes[0]["url"] != ["*"] or not dark or not hints:
        raise ValueError("incomplete Dark Reader lists")
    original_css = {tuple(entry["url"]): entry.get("css", "") for entry in bundled["fixes"]}
    for fix in fixes:
        css = fix.get("css", "")
        if len(css) > 32768 or EXTERNAL_CSS.search(css):
            fix["css"] = original_css.get(tuple(fix["url"]), "")
    for entry in (*fixes, *hints):
        entry["url"] = patterns(entry["url"])
    return dict(bundled, lists_commit=commit, lists_date=date[:10],
                fixes=[f for f in fixes if f["url"]], dark_sites=dark,
                detector_hints=[h for h in hints if h["url"]])


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise OSError("Dark Reader list redirect refused")


def _read(url):
    request = urllib.request.Request(url, headers={"Accept": "*/*", "User-Agent": "I.K.E. list updater"})
    with doh.urlopen(request, timeout=15, handlers=(NoRedirect(),)) as response:
        data = response.read(LIMIT + 1)
    if len(data) > LIMIT:
        raise ValueError("Dark Reader response is too large")
    return data.decode("utf-8")


def _cached(path):
    with path.open("rb") as stream:
        raw = stream.read(8 * LIMIT + 1)
    if len(raw) > 8 * LIMIT:
        raise ValueError("Dark Reader cache is too large")
    return json.loads(raw)


def load(bundled, path=CACHE):
    try:
        return unpack(_cached(path), bundled)
    except (OSError, ValueError, KeyError, TypeError):
        return bundled


def refresh(bundled, path=CACHE, read=_read):
    head = json.loads(read(HEAD))
    commit, date = head["sha"], head["commit"]["committer"]["date"]
    _revision(commit, date)
    if commit == bundled.get("lists_commit") or date[:10] < bundled.get("lists_date", ""):
        return False
    try:
        current = _cached(path)
        unpack(current, bundled)
        if commit == current["commit"] or date < current["date"]:
            return False
    except (OSError, ValueError, KeyError, TypeError):
        pass
    snapshot = {"commit": commit, "date": date,
                "texts": [read(f"{RAW}{commit}/src/config/{name}") for name in FILES]}
    unpack(snapshot, bundled)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, mode="w", encoding="utf-8", delete=False) as out:
        temporary = out.name
        try:
            json.dump(snapshot, out, ensure_ascii=False)
            out.flush()
            os.fsync(out.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    return True


class Checker(QThread):
    def run(self):
        from .darkfixes import bundled_data
        try:
            refresh(bundled_data())
        except (OSError, ValueError, KeyError, TypeError):
            pass


def due():
    stamp = CACHE.with_suffix(".checked")
    try:
        if time.time() - stamp.stat().st_mtime < INTERVAL:
            return False
    except FileNotFoundError:
        pass
    except OSError:
        return False
    try:
        stamp.parent.mkdir(parents=True, exist_ok=True)
        stamp.touch()
    except OSError:
        return False
    return True
