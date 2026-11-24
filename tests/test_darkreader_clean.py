"""Dark Reader in I.K.E. holds only what it needs to work (the owner's rule, 1.1.25):
no advertising, donations, news or social sites, and no way to the network
other than the known ones.

Checked on ike/resources/darkreader.js (the engine, rebuilt by the automatic
updates from Dark Reader's releases: tools/build-darkreader.py), on its
style-sheet proxy (darkreader-proxy.js) and on I.K.E.'s own darkmode.js:

- every absolute http(s) address in them is one of ALLOWED, each with its
  reason (none of them is ever contacted);
- no donation, payment or social site appears anywhere in them;
- the engine reaches the network only through the fetch() calls listed in
  FETCHES (style sheets and images of the page, as the extension does); a new
  one makes this test fail, so that a person (or Claude) looks at it before it
  ships. ike/resources/darkreader.js itself is never edited by hand.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "ike" / "resources"
FILES = ("darkreader.js", "darkreader-proxy.js", "darkmode.js")

# (file, address): why it is there
ALLOWED = {
    ("darkreader.js", "https://darkreader.org/"): "the attribution in the header the MIT licence asks for (text)",
    ("darkreader.js", "https://darkreader.org"): "the attribution in the banner the MIT licence asks for (text)",
    ("darkreader.js", "https://github.com/darkreader/darkreader/blob/main/LICENSE"):
        "the link to the MIT licence in the banner (text, never contacted)",
    ("darkreader.js", "https://fonts.googleapis.com/"):
        "a startsWith() comparison on a style sheet's own address (no request)",
    ("darkreader.js", "http://www.w3.org/2000/svg"): "the SVG namespace (no request)",
    ("darkreader.js", "http://www.w3.org/1999/xlink"): "the XLink namespace (no request)",
    ("darkreader-proxy.js", "https://darkreader.org"): "the attribution the MIT licence asks for (text)",
    ("darkreader-proxy.js", "http://www.w3.org/2000/svg"): "the SVG namespace (no request)",
    ("darkmode.js", "https://darkreader.org"): "I.K.E.'s note naming Dark Reader (text)",
}

UNWANTED = re.compile(r"donat|patreon|opencollective|open collective|paypal|liberapay|ko-fi|buymeacoffee|"
                      r"twitter|\bx\.com\b|facebook|mastodon|youtube\.com|instagram|reddit|discord|telegram",
                      re.IGNORECASE)

# The engine's ways to the network, as they are today (Dark Reader 4.9.135): the text
# of each line that calls fetch(), stripped. Each is for the page's own style sheets or
# images, as in the extension; a page's own scripts are never fetched.
FETCHES = [
    "const response = await fetch(url, {",                         # loadAsDataURL / loadAsText
    "return window.DarkReader.Plugins.fetch(request);",           # the fetch method I.K.E. sets
    "const response = await fetch(dataURL);",                      # a data: URL read as a blob
    "return await (await fetch(url)).text();",                     # an @import's text
]
NETWORK = re.compile(r"\bfetch\s*\(|XMLHttpRequest|sendBeacon|new\s+WebSocket|EventSource|importScripts|"
                     r"\.open\s*\(\s*['\"](GET|POST)", re.IGNORECASE)


def _text(name):
    return (RES / name).read_text("utf-8")


def test_every_address_is_known_and_has_a_reason():
    found = set()
    for name in FILES:
        for url in re.findall(r"""https?://[^\s"'`)<>\\]+""", _text(name)):
            found.add((name, url))
    unknown = sorted(found - set(ALLOWED))
    assert not unknown, "addresses not in the list (look at them, then add them with a reason): %s" % unknown
    assert all(ALLOWED.values())
    missing = sorted(set(ALLOWED) - found)
    assert not missing, "listed but gone (remove them from ALLOWED): %s" % missing


def test_no_donation_payment_or_social_site():
    for name in FILES:
        for i, line in enumerate(_text(name).splitlines(), 1):
            m = UNWANTED.search(line)
            assert m is None, "%s:%d: %r" % (name, i, line.strip()[:160])


def test_the_engine_reaches_the_network_only_where_it_is_known():
    calls = [line.strip() for line in _text("darkreader.js").splitlines() if NETWORK.search(line)]
    assert calls == FETCHES, "the engine's network calls changed: %s" % calls
    proxy = [line.strip() for line in _text("darkreader-proxy.js").splitlines() if NETWORK.search(line)]
    assert proxy == [], proxy
    # I.K.E.'s own script: the page's style sheets only, through the page, else through the browser
    own = [line.strip() for line in _text("darkmode.js").splitlines() if NETWORK.search(line)]
    assert own == ["return window.fetch(url).then(function (r) {"], own


def test_news_is_only_a_name_never_fetched():
    """"news" appears in the engine only as the names of message types the extension
    uses; nothing reads news from anywhere."""
    engine = _text("darkreader.js")
    lines = [line.strip() for line in engine.splitlines()
             if re.search(r"(?<![a-z])news(?![a-z])", line, re.IGNORECASE)]
    for line in lines:
        assert (re.fullmatch(r'MessageType\w*\["[A-Z_]*NEWS[A-Z_]*"\]\s*=(\s*"[a-z-]*news[a-z-]*";)?', line)
                or re.fullmatch(r'"[a-z-]*news[a-z-]*";', line)), line
