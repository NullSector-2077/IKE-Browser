"""1.1.29: skip the tracker's stop, and Google's AMP copies (ike/debounce.py).

A link that only passes through a tracker, with the real address written
inside it, opens that address at once; the rules are Brave's public debounce
list, shipped unchanged and followed by the daily maintenance (components.json,
entry brave-debounce, a branch upstream). What must never happen: a script,
a file, the home network, an address with a user name in it, a stop that also
protects the user (Facebook, Steam, Google's and YouTube's redirects), a
sign-in or payment service, a loop.
"""

import hashlib
import importlib.util
import json
import sys

import pytest
from conftest import APP, ROOT

sys.path.insert(0, str(APP))

from ike import debounce  # noqa: E402


def site(host):
    """Registrable domain, enough for these tests (no Qt, no Public Suffix List)."""
    parts = host.split(".")
    return ".".join(parts[-3:]) if parts[-2:-1] == ["co"] else ".".join(parts[-2:])


def skip(url, rule_set=None):
    return debounce.skip(url, site_of=site, rule_set=rule_set)


def rules(*raw):
    return debounce.compile_rules(list(raw))


# --- Brave's list as shipped ---------------------------------------------------

@pytest.mark.parametrize("link, target", [
    # an affiliate network
    ("https://go.redirectingat.com/?id=1&url=https%3A%2F%2Fshop.example.com%2Fitem%3Fa%3D1",
     "https://shop.example.com/item?a=1"),
    # Mailchimp's newsletter links
    ("https://us1.mailchimp.com/mctx/clicks?url=https%3A%2F%2Fnews.example.org%2Fa&xid=1",
     "https://news.example.org/a"),
    # ActiveCampaign: the address in base64
    ("https://abc.lt.acemlna.com/Prod/link-tracker?redirectUrl=aHR0cHM6Ly93d3cuZXhhbXBsZS5jb20vcGFnZQ==&x=1",
     "https://www.example.com/page"),
    # Amazon SES: the address in the path
    ("https://xyz.awstrack.me/L0/https:%2F%2Fwww.example.net%2Fpath%3Fq=1/1/0100-abc/xyz=",
     "https://www.example.net/path?q=1"),
    # Google's AMP copies, to the publisher's own site
    ("https://www.google.com/amp/s/www.repubblica.it/cronaca/2026/articolo.amp",
     "https://www.repubblica.it/cronaca/2026/articolo.amp"),
    ("https://www-repubblica-it.cdn.ampproject.org/c/s/www.repubblica.it/x/y", "https://www.repubblica.it/x/y"),
    # two trackers in a row: both skipped
    ("https://go.redirectingat.com/?url=https%3A%2F%2Fgo.skimresources.com%2F%3Furl%3D"
     "https%253A%252F%252Ffinal.example%252F", "https://final.example/"),
])
def test_the_shipped_list_skips_the_trackers_stop(link, target):
    assert skip(link) == target


@pytest.mark.parametrize("link", [
    "https://example.com/?url=https://x.org",                                   # no rule names it
    "https://go.redirectingat.com/?url=javascript%3Aalert(1)",                  # a script
    "https://go.redirectingat.com/?url=file%3A%2F%2F%2Fetc%2Fpasswd",           # a file of the computer
    "https://go.redirectingat.com/?url=ike%3Anewtab",                           # a page of I.K.E.
    "https://r.bttn.io/?btn_url=http%3A%2F%2F192.168.1.1%2F",                   # the router
    "https://go.redirectingat.com/?url=http%3A%2F%2Flocalhost%3A631%2F",        # this computer
    "https://go.redirectingat.com/?url=http%3A%2F%2Frouter%2F",                 # a name of the home network
    "https://go.redirectingat.com/?url=http%3A%2F%2F2130706433%2F",             # 127.0.0.1 in disguise
    "https://go.redirectingat.com/?url=https%3A%2F%2Fuser%3Apw%40evil.example%2F",  # a user name in it
    "https://go.redirectingat.com/?url=https%3A%2F%2Fpaypal.com%40evil.example%2F",  # paypal.com@evil
    "https://go.redirectingat.com/?url=https%3A%2F%2Fgo.redirectingat.com%2Fx",  # the same site
    "https://go.redirectingat.com/?url=https%3A%2F%2Fa.example%2F%0d%0aX",       # control characters
    "https://go.redirectingat.com/?url=",                                       # nothing in it
    "https://go.redirectingat.com/?url=https%3A%2F%2F",                         # no host
    "https://go.redirectingat.com/?url=https%3A%2F%2Fa.example%3A99999%2F",     # a port that is none
    "ftp://go.redirectingat.com/?url=https%3A%2F%2Fa.example%2F",               # not a web page
])
def test_what_is_never_opened_in_the_trackers_place(link):
    assert skip(link) is None


def test_a_very_long_address_is_left_as_it_is():
    long = "https://a.example/" + "x" * debounce.MAX_LENGTH
    assert skip("https://go.redirectingat.com/?url=" + long) is None


# --- what the engine could read otherwise (the independent review, 2026-11-27) ---

@pytest.mark.parametrize("hidden", [
    "http%3A%2F%2F%2531%2539%2532.168.1.1%2Fapply.cgi",         # "%31%39%32" is 192
    "http://１２７.0.0.1:631/admin",                 # full-width digits: 127.0.0.1
    "http%3A%2F%2Floc%2561lhost%3A8080%2F",                      # an escaped "a": localhost
    "http://192。168。1。1/",                        # ideographic full stops
    "http://10.0.0.1​/",                                    # a zero-width space
    "http://ⓛocalhost/",                                    # a circled letter
    "http%3A%2F%2Ffoo%252elocal%2F",                             # an escaped dot: foo.local
])
def test_a_host_the_engine_could_read_as_a_local_one_is_never_opened(hidden):
    assert skip("https://go.redirectingat.com/?url=" + hidden) is None


def test_base64_keeps_its_plus_signs():
    # "https://a.example/?q=~~~" in base64 ends with "+": not a space
    r = rules({"include": ["*://*.ouo.today/*"], "action": "base64,redirect", "param": "cr"})
    assert skip("https://x.ouo.today/?cr=aHR0cHM6Ly9hLmV4YW1wbGUvP3E9fn5+", r) == "https://a.example/?q=~~~"


# --- I.K.E.'s own limits on any rule -------------------------------------------

STOPS = {"include": ["*://*.facebook.com/*", "*://*.instagram.com/*", "*://*.messenger.com/*",
                     "*://steamcommunity.com/*", "*://*.youtube.com/*", "*://*.google.com/*", "*://*.google.it/*",
                     "*://accounts.google.com/*", "*://*.paypal.com/*", "*://*.tracker.example/*"],
         "action": "redirect", "param": "u"}


@pytest.mark.parametrize("link", [
    "https://l.facebook.com/l.php?u=https%3A%2F%2Fa.example%2F",        # Facebook's link shim
    "https://lm.facebook.com/l.php?u=https%3A%2F%2Fa.example%2F",
    "https://l.instagram.com/?u=https%3A%2F%2Fa.example%2F",
    "https://l.messenger.com/l.php?u=https%3A%2F%2Fa.example%2F",
    "https://steamcommunity.com/linkfilter/?u=https%3A%2F%2Fa.example%2F",  # Steam's warning
    "https://www.youtube.com/redirect?u=https%3A%2F%2Fa.example%2F",     # YouTube's warning
    "https://www.youtube.com//redirect?u=https%3A%2F%2Fa.example%2F",
    "https://www.youtube.com/Redirect?u=https%3A%2F%2Fa.example%2F",
    "https://www.google.com/url?u=https%3A%2F%2Fa.example%2F",           # Google's check
    "https://www.google.it/url?u=https%3A%2F%2Fa.example%2F",
    "https://accounts.google.com/x?u=https%3A%2F%2Fa.example%2F",        # a sign-in service
    "https://accounts.google.com./x?u=https%3A%2F%2Fa.example%2F",
    "https://www.paypal.com/x?u=https%3A%2F%2Fa.example%2F",             # a payment service
])
def test_stops_that_protect_the_user_are_kept_even_if_a_rule_names_them(link):
    r = rules(STOPS)
    assert skip(link, r) is None
    # the same rule elsewhere does work
    assert skip("https://t.tracker.example/?u=https%3A%2F%2Fa.example%2F", r) == "https://a.example/"
    # Google's AMP copies are not its redirect page
    assert skip("https://www.google.com/amp/s/a.example/x", debounce.rules()) == "https://a.example/x"


def test_too_many_stops_in_a_row_leave_the_link_as_it_is():
    from urllib.parse import quote
    n = debounce.MAX_STOPS + 2
    r = rules({"include": ["*://*.a%d.test/*" % i for i in range(n)], "action": "redirect", "param": "u"})
    hops = ["https://t.a%d.test/" % i for i in range(n)]
    link = hops[-1]
    for h in reversed(hops[:-1]):
        link = h + "?u=" + quote(link, safe="")
    assert skip(link, r) is None
    link = hops[debounce.MAX_STOPS]
    for h in reversed(hops[:debounce.MAX_STOPS]):
        link = h + "?u=" + quote(link, safe="")
    assert skip(link, r) == hops[debounce.MAX_STOPS]


@pytest.mark.parametrize("rule", [
    {"include": ["*://*/*"], "action": "redirect", "param": "u"},                       # every site
    {"include": ["*://*.co.uk/*"], "action": "redirect", "param": "u"},                 # a public suffix
    {"include": ["*://*.com/*"], "action": "redirect", "param": "u"},
    {"include": ["*://localhost/*"], "action": "redirect", "param": "u"},               # one label
    {"include": ["*://t.example/" + "*a" * 8], "action": "redirect", "param": "u"},     # too many "*"
    {"include": ["*://t.example/*"], "action": "regex-path-template", "param": "^/(.*)$",
     "redirect_url_template": "https://evil.example/$1"},                               # a template anywhere
    {"include": ["*://t.example/*"], "action": "regex-path-template", "param": "^/(.*)$",
     "redirect_url_template": "https://www.youtube.com.evil.example/$1"},
    {"include": ["*://t.example/*"], "action": "regex-path-template", "param": "^/(.*)$",
     "redirect_url_template": "https://$1/x"},
    {"include": ["*://t.example/*"], "action": "regex-path", "param": "^/(a+)+$"},     # nested repeats
    {"include": ["*://t.example/*"], "action": "regex-path", "param": "^/(.*)(.*)(.*)x$"},  # piled up
    {"include": ["*://t.example/*"], "action": "regex-path", "param": r"^/(a)\1$"},    # a back-reference
    {"include": ["*://t.example/*"], "action": "regex-path", "param": "^/(?=a)(.*)$"},  # a look-ahead
])
def test_a_rule_that_could_take_over_or_slow_every_page_is_left_out(rule):
    refused = []
    assert debounce.compile_rules([rule], site_of=site, refused=refused) == () and refused


def test_patterns_are_matched_in_linear_time():
    import time
    r = debounce.compile_rules([{"include": ["*://t.example/*a*a*a*a*b"], "action": "redirect", "param": "u"}],
                               site_of=site)
    start = time.monotonic()
    assert skip("https://t.example/" + "a" * 5000 + "?u=https%3A%2F%2Fz.example%2F", r) is None
    assert time.monotonic() - start < 0.5


def test_the_rule_kinds_of_brave_s_list():
    r = rules(
        {"include": ["*://t.example/*"], "exclude": ["*://t.example/keep*"], "action": "redirect", "param": "to"},
        {"include": ["https://b.example/*"], "action": "base64,redirect", "param": "d"},
        {"include": ["*://p.example/*"], "action": "regex-path", "param": "^/go/([^/]+)/.*$",
         "prepend_scheme": "https"},
        {"include": ["*://y.example/*"], "action": "regex-path-template", "param": "^/([^/]+)$",
         "redirect_url_template": "https://www.youtube.com/watch?v=$1"},
        {"include": ["*://u.example/*"], "action": "something-new", "param": "x"},           # unknown action
        {"include": ["*://v.example/*"], "action": "redirect", "param": "x", "pref": "brave.other"},
        {"include": ["not a pattern"], "action": "redirect", "param": "x"},
        {"include": ["*://w.example/*"], "action": "regex-path", "param": "(unclosed"},       # a bad regex
        "not a rule",
    )
    assert len(r) == 4
    assert skip("https://t.example/c?to=https%3A%2F%2Fa.example%2F", r) == "https://a.example/"
    assert skip("https://t.example/keep?to=https%3A%2F%2Fa.example%2F", r) is None          # excluded
    assert skip("https://b.example/c?d=aHR0cHM6Ly9hLmV4YW1wbGUvYj9jPTE", r) == "https://a.example/b?c=1"
    assert skip("http://b.example/c?d=aHR0cHM6Ly9hLmV4YW1wbGUv", r) is None                  # https only
    assert skip("https://p.example/go/a.example%2Fpage/123", r) == "https://a.example/page"
    assert skip("https://y.example/abc123", r) == "https://www.youtube.com/watch?v=abc123"
    assert skip("https://u.example/?x=https%3A%2F%2Fa.example%2F", r) is None
    assert skip("https://v.example/?x=https%3A%2F%2Fa.example%2F", r) is None
    assert debounce.compile_rules({"not": "a list"}) == ()


# --- the list shipped and followed upstream -------------------------------------

def load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_") + "_debounce", ROOT / "tools" / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_list_is_brave_s_unchanged_and_every_rule_keeps_to_the_limits():
    """A new version of Brave's list reaches main by itself only when this passes: a rule of it
    that breaks I.K.E.'s limits (every site, a public suffix, a template elsewhere, a slow
    expression) fails here and waits for a person."""
    manifest = load("component-manifest")
    entry = manifest.read(ROOT)["components"]["brave-debounce"]
    path = ROOT / "ike" / "resources" / "brave-debounce.json"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["download"][0]["sha256"]
    assert entry["upstream"] == {"git": "https://github.com/brave/adblock-lists", "branch": "master"}
    raw = json.loads(path.read_text("utf-8"))
    refused = []
    compiled = debounce.compile_rules(raw, site_of=site, refused=refused)
    assert refused == []
    # the rules I.K.E. leaves out are only those of an action or a switch it does not know
    known = [r for r in raw if r.get("action") in debounce.ACTIONS and r.get("pref") in (None,) + debounce.PREFS]
    assert len(compiled) == len(known) >= 40
    assert sum(len(r[0]) for r in compiled) == sum(len(r["include"]) for r in known)
    assert (ROOT / entry["licence"]).read_text("utf-8").startswith("Mozilla Public License Version 2.0")


def test_a_branch_upstream_is_followed_by_its_newest_commit(tmp_path):
    manifest = load("component-manifest")
    old, new = b"[]\n", b'[{"include": ["*://t.example/*"], "action": "redirect", "param": "u"}]\n'
    c1, c2 = "1" * 40, "2" * 40
    url = "https://raw.githubusercontent.com/example/lists/%s/debounce.json"
    root = tmp_path / "repo"
    (root / "ike" / "resources").mkdir(parents=True)
    (root / "licenses").mkdir()
    (root / "ike/resources/list.json").write_bytes(old)
    (root / "licenses/LICENSE.lists").write_text("MPL-2.0\n")
    entry = {"name": "a list", "upstream": {"git": "https://github.com/example/lists", "branch": "master"},
             "files": ["ike/resources/list.json"], "version": c1, "licence": "licenses/LICENSE.lists",
             "download": [{"url": url % "{version}", "file": "ike/resources/list.json",
                           "sha256": hashlib.sha256(old).hexdigest()}],
             "tests": list(manifest.DEFAULT_TESTS)}
    data = {"schema": 1, "about": "", "components": {"lists": entry}}
    (root / "components.json").write_text(json.dumps(data))
    assert manifest.problems(data) == []
    files = {url % c1: old, url % c2: new}

    def get(u, timeout=60):
        return files[u]

    same = manifest.check_entry(root, "lists", get=get, heads=lambda g, b: c1)
    assert same["update"] is False and same["latest"] == c1
    info = manifest.check_entry(root, "lists", get=get, heads=lambda g, b: c2)
    assert info["update"] is True and info["latest"] == c2
    manifest.apply_entry(root, info)
    assert (root / "ike/resources/list.json").read_bytes() == new
    written = json.loads((root / "components.json").read_text())["components"]["lists"]
    assert written["version"] == c2 and written["download"][0]["sha256"] == hashlib.sha256(new).hexdigest()
    # a file the declared commit does not give back: no update from an upstream that cannot be checked
    files[url % c2] = b"changed upstream\n"
    with pytest.raises(manifest.Unverified):
        manifest.check_entry(root, "lists", get=get, heads=lambda g, b: c2)
    # a branch and a tag together, or a branch with no git: not an entry
    for bad in ({"git": "https://github.com/example/lists", "branch": "master", "tag": "v*"},
                {"npm": "lists", "branch": "master"}, {"git": "https://github.com/example/lists", "branch": "a b"}):
        assert manifest.entry_problems("lists", dict(entry, upstream=bad))


def test_commit_versions_are_compared_as_commits():
    """A version that is a commit says nothing by its digits: the merge's gate, the inventory and
    the ledger take any other commit as an update and never order two of them by their digits."""
    manifest, inventory = load("component-manifest"), load("inventory")
    old = json.loads((ROOT / "components.json").read_text("utf-8"))
    entry = old["components"]["brave-debounce"]
    new = json.loads(json.dumps(old))
    sha_of = {entry["download"][0]["file"]: "f" * 64}.get
    new["components"]["brave-debounce"]["download"][0]["sha256"] = "f" * 64
    for version in ("abcdef" + "0" * 34, "0" * 40):           # digits "smaller" than the one in use
        new["components"]["brave-debounce"]["version"] = version
        assert manifest.update_problem("brave-debounce", json.dumps(old), json.dumps(new), sha_of) == ""
    new["components"]["brave-debounce"]["version"] = entry["version"]
    assert "does not go up" in manifest.update_problem("brave-debounce", json.dumps(old), json.dumps(new), sha_of)
    rec = {"installed": "9" * 40, "compatibility": inventory.UNKNOWN}
    inventory._compare(rec, "1" * 40, "github")
    assert rec["result"] == "update available"
    rec = {"installed": "9" * 40, "compatibility": inventory.UNKNOWN}
    inventory._compare(rec, "9" * 40, "github")
    assert rec["result"] == "ok"
    rec = {"installed": "1.2.3", "compatibility": inventory.UNKNOWN}       # dotted versions as before
    inventory._compare(rec, "1.2.10", "pypi")
    assert rec["result"] == "update available"
    ledger = load("maintenance-ledger")
    assert ledger.commit("a" * 40) and not ledger.commit("1.2.3")


# --- inside the browser ---------------------------------------------------------

STEPS = r"""
from PyQt6.QtCore import QUrl
from PyQt6.QtWebEngineCore import QWebEngineUrlRequestInfo as I

RT, NT = I.ResourceType, I.NavigationType

class Info:
    def __init__(self, url, initiator="https://mail.example.org/inbox", rtype=RT.ResourceTypeMainFrame):
        self.u, self.i, self.t = QUrl(url), QUrl(initiator), rtype
        self.blocked, self.to = False, None
    def requestUrl(self): return self.u
    def firstPartyUrl(self): return self.u if self.t == RT.ResourceTypeMainFrame else self.i
    def initiator(self): return self.i
    def resourceType(self): return self.t
    def navigationType(self): return NT.NavigationTypeLink
    def requestMethod(self): return b"GET"
    def block(self, b): self.blocked = bool(b)
    def redirect(self, u): self.to = u.toString()
    def setHttpHeader(self, k, v): pass

LINK = "https://go.redirectingat.com/?id=1&url=https%3A%2F%2Fshop.example.com%2Fitem"

def steps(ike, qapp, out):
    yield 0
    icp = ike.shields.interceptor
    errors = ike.blocker.__dict__.setdefault("_test_errors", [])
    old = ike.blocker._engine_error
    ike.blocker._engine_error = lambda what, url, exc: errors.append("%s: %r" % (what, exc))
    info = Info(LINK)
    icp.interceptRequest(info)
    out["link"] = info.to
    out["counted"] = ike.shields.site_stats("shop.example.com")["params"]
    # the new address comes back through the checks: nothing is skipped again, nothing reset
    info = Info("https://shop.example.com/item")
    icp.interceptRequest(info)
    out["again"] = info.to
    out["kept"] = ike.shields.site_stats("shop.example.com")["params"]
    info = Info("https://go.redirectingat.com/?url=https%3A%2F%2Fbare.example&x=a%20b")
    icp.interceptRequest(info)
    out["bare"] = info.to
    info = Info("https://bare.example/")
    icp.interceptRequest(info)
    out["bare_counted"] = ike.shields.site_stats("bare.example")["params"]
    info = Info("https://go.redirectingat.com/?url=http%3A%2F%2F%2531%2539%2532.168.1.1%2F", initiator="")
    icp.interceptRequest(info)
    out["hidden_router"] = info.to
    info = Info("https://www.google.com/amp/s/www.example.net/article")
    icp.interceptRequest(info)
    out["amp"] = info.to
    info = Info("https://r.bttn.io/?btn_url=http%3A%2F%2F192.168.1.1%2F")
    icp.interceptRequest(info)
    out["router"] = info.to
    info = Info(LINK, rtype=RT.ResourceTypeImage)                 # a picture of a page: not a link followed
    icp.interceptRequest(info)
    out["picture"] = info.to
    ike.config.data["site_opts"]["mail.example.org"] = {"params": False}   # "Repair this site" on the page
    info = Info(LINK)
    icp.interceptRequest(info)
    out["repaired"] = info.to
    out["errors"] = errors
    ike.blocker._engine_error = old
"""


def test_the_shield_opens_the_real_address(run_ike):
    out = run_ike(STEPS, settings={"shield_level": "balanced", "strip_tracking_params": True})
    assert out["link"] == "https://shop.example.com/item", out
    assert out["counted"] == 1 and out["kept"] == 1 and out["again"] is None, out
    assert out["amp"] == "https://www.example.net/article", out
    assert out["router"] is None and out["picture"] is None and out["repaired"] is None, out
    assert out["bare"] == "https://bare.example/" and out["bare_counted"] == 1, out
    assert out["hidden_router"] is None, out


def test_off_below_balanced_and_without_the_setting(run_ike):
    for settings in ({"shield_level": "compatibility", "strip_tracking_params": True},
                     {"shield_level": "strict", "strip_tracking_params": False}):
        out = run_ike(STEPS, settings=settings)
        assert out["link"] is None and out["amp"] is None, (settings, out)
    out = run_ike(STEPS, settings={"shield_level": "maximum", "strip_tracking_params": True})
    assert out["link"] == "https://shop.example.com/item", out
