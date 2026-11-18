"""Lookalike sites ("Sosia", 1.1.14): addresses made to pass for a well-known one.

When a page opens, its address is compared, on this computer only, with a short
list of the sites that scams imitate most (banks, payments, shops, mail, social
networks). Three tricks are recognised:

- letters swapped for look-alikes: "paypa1", "arnazon" (rn for m), "g00gle";
- letters of another alphabet that look the same: a Cyrillic "а" in "pаypal";
- a famous address at the start of a false one: "paypal.com.secure-login.xyz".

A slip of one letter (two letters swapped, a similar letter, a double letter)
counts only for names of seven letters or more; any other one-letter difference
does not, as too many real names are one letter away from a famous one. The real
sites of each name are never flagged, and the user can mark any site as fine.
Nothing is blocked: the window shows a bar above the page. No data leaves the
computer, and the check is a few string comparisons per opened page.

No Qt here: the module is plain Python (tests/test_lookalike.py).
"""

import json
import unicodedata
from pathlib import Path

_DATA = Path(__file__).resolve().parent / "resources" / "lookalike.json"
_SLD = frozenset("co com org net gov edu ac or ne go gob nom mil ltd plc sch nhs me info id gv".split())

# letters of other alphabets that look like Latin ones (Unicode TR39 confusables,
# the ones used in practice), and the Latin tricks with digits and letter pairs
_CONFUSABLE = {
    # Cyrillic
    "а": "a", "в": "b", "е": "e", "ё": "e", "і": "i", "ї": "i", "ј": "j", "к": "k", "м": "m",
    "н": "h", "о": "o", "р": "p", "с": "c", "т": "t", "у": "y", "х": "x", "ѕ": "s", "ԁ": "d",
    "һ": "h", "ӏ": "l", "ԛ": "q", "ԝ": "w", "ь": "b", "п": "n", "г": "r",
    # Greek
    "α": "a", "β": "b", "ε": "e", "η": "n", "ι": "i", "κ": "k", "ν": "v", "ο": "o", "ρ": "p",
    "τ": "t", "υ": "u", "χ": "x", "ω": "w",
    # Latin look-alikes that NFKD keeps apart
    "ı": "i", "ł": "l", "ø": "o", "đ": "d", "ħ": "h", "ŀ": "l", "ƒ": "f", "ɡ": "g",
    # digits
    "0": "o", "1": "l", "3": "e", "5": "s", "7": "t",
}


def skeleton(label):
    """What a name looks like: "pаypa1" and "paypal" give the same skeleton."""
    s = unicodedata.normalize("NFKD", label.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = "".join(_CONFUSABLE.get(c, c) for c in s)
    # a dash between two real pieces is a trick ("pay-pal", "tik-tok"); a lone
    # letter before it is a name of its own ("l-cloud")
    parts = [x for x in s.replace("_", "-").split("-") if x]
    if all(len(x) >= 3 for x in parts):
        s = "".join(parts)
    # i and l are the same stroke in many fonts, rn looks like m, vv like w
    return s.replace("i", "l").replace("rn", "m").replace("vv", "w")


def registrable(host):
    """"www.bbc.co.uk" -> "bbc.co.uk" (as shields.site_of)."""
    parts = host.split(".")
    if len(parts) <= 2:
        return host
    three = len(parts[-1]) == 2 and parts[-2] in _SLD
    return ".".join(parts[-3 if three else -2:])


def _unicode_host(host):
    """xn-- labels shown as the letters they stand for."""
    out = []
    for label in host.split("."):
        if label.startswith("xn--"):
            try:
                label = label.encode("ascii").decode("idna")
            except (UnicodeError, ValueError):
                pass
        out.append(label)
    return ".".join(out)


# letters that are easy to mistake for each other at a glance (besides the
# ones skeleton() already merges)
_SIMILAR = {frozenset(p) for p in ("nm", "uv", "ce", "gq")}


def _one_slip(a, b):
    """True when a reads as b at a glance: two neighbouring letters swapped
    ("amzaon"), one letter changed for a similar one ("instagran"), or a double
    letter made single or the other way ("facebok", "youtubee"). Any other
    one-letter difference is not counted: too many real names are one letter
    away from a famous one ("finance" and "binance", "telegraf" and "telegram")."""
    if a == b:
        return False
    if len(a) == len(b):
        diff = [i for i in range(len(a)) if a[i] != b[i]]
        if len(diff) == 1:
            return frozenset((a[diff[0]], b[diff[0]])) in _SIMILAR
        return (len(diff) == 2 and diff[1] == diff[0] + 1
                and a[diff[0]] == b[diff[1]] and a[diff[1]] == b[diff[0]])
    if abs(len(a) - len(b)) != 1:
        return False
    if len(a) > len(b):
        a, b = b, a
    i = 0
    while i < len(a) and a[i] == b[i]:
        i += 1
    if a[i:] != b[i + 1:]:
        return False
    extra = b[i]                 # the letter b has more: is it a doubled one?
    return (i > 0 and b[i - 1] == extra) or (i + 1 < len(b) and b[i + 1] == extra)


class Checker:
    MIN_EDIT = 7          # one-letter slips count from this length on

    def __init__(self, data=None):
        if data is None:
            data = json.loads(_DATA.read_text("utf-8"))
        self.brands = []                  # (name, key, skeleton, official registrable domains)
        self.official = set()
        for b in data["brands"]:
            domains = [d.lower() for d in b["domains"]]
            self.official.update(domains)
            for key in b["names"]:
                self.brands.append((b["display"], key, skeleton(key), frozenset(domains)))
        self.not_lookalikes = {d.lower() for d in data.get("not_lookalikes", [])}

    def _is_official(self, host):
        return any(host == d or host.endswith("." + d) for d in self.official)

    def check(self, host, allowed=()):
        """The name of the famous site this host imitates, or None."""
        host = _unicode_host((host or "").lower().strip(".").split(":")[0])
        if not host or "." not in host or host.replace(".", "").isdigit():
            return None
        site = registrable(host)
        if self._is_official(host) or site in self.not_lookalikes or site in allowed:
            return None
        # a famous address at the start of a false one: paypal.com.secure-login.xyz
        rest = host[:-len(site)].rstrip(".")
        if rest:
            for off in self.official:
                if rest == off or rest.endswith("." + off):
                    return self._display(off)
        label = site.split(".")[0]
        if len(label) < 5:
            return None                   # too short to tell a trick from a name
        sk = skeleton(label)
        for display, key, brand, _domains in self.brands:
            if label == key:
                continue                  # the same name elsewhere: not a look-alike trick
            if sk == brand:
                return display
            if len(key) >= self.MIN_EDIT and len(label) >= self.MIN_EDIT and _one_slip(sk, brand):
                return display
        return None

    def _display(self, domain):
        for display, _key, _sk, domains in self.brands:
            if domain in domains:
                return display
        return domain


_checker = None


def check(host, allowed=()):
    global _checker
    if _checker is None:
        _checker = Checker()
    return _checker.check(host, allowed)
