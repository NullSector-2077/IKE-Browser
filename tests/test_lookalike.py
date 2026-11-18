"""Sosia (1.1.14): sites that imitate the address of a famous one.

The check must never get in the way of real sites: none of the ~10,000 real
sites of tests/data/lookalike-near-real.txt (sites of the top million whose
names are close to a famous one) may be flagged, nor the famous sites
themselves with their country domains, nor the payment pages a bank sends
you to. And it must catch the tricks scams use. The window shows the warning
above the page, without blocking it, and "This site is fine" is remembered.
"""

from pathlib import Path

import pytest

from ike import lookalike

ROOT = Path(__file__).resolve().parent.parent

LOOKALIKES = {
    "paypa1.com": "PayPal",                       # digit for a letter
    "www.paypai.it": "PayPal",                    # i for l
    "www.pаypal.com": "PayPal",                   # Cyrillic а
    "xn--pypal-4ve.com": "PayPal",                # the same, as the browser receives it
    "paypal.com.secure-login.xyz": "PayPal",      # the real address in front of a false one
    "pay-pal.com": "PayPal",
    "arnazon.it": "Amazon",                       # rn for m
    "instgaram.com": "Instagram",                 # two letters swapped
    "g00gle.com": "Google",
    "youtubee.com": "YouTube",                    # a doubled letter
    "www.yout-ube.com": "YouTube",
    "instagran.com": "Instagram",                 # m for n
    "facebok.com": "Facebook",                    # a double letter made single
    "netfiix.com": "Netflix",
    "p0ste.it": "Poste Italiane",
    "posteitaliane.verifica-conto.com.posteitaliane.it.evil.xyz": "Poste Italiane",
    "intesasanpao1o.com": "Intesa Sanpaolo",
    "unicredlt.it": "UniCredit",
    "bancobpn.it": "Banco BPM",
    "steamcomrnuunity.com": "Steam",              # seen in the real top million
}

REAL = [
    "paypal.com", "www.paypal.it", "amazon.it", "www.amazon.co.uk", "google.it", "mail.google.com",
    "www.youtube.com", "accounts.google.com", "www.poste.it", "www.intesasanpaolo.com",
    "www.unicredit.it", "www.bancobpm.it", "www.instagram.com", "www.facebook.com",
    "www.netflix.com", "steamcommunity.com", "store.steampowered.com",
    # payment pages and services a shop or a bank sends you to
    "checkout.stripe.com", "secure.nexi.it", "ecommerce.nexi.it", "www.satispay.com", "3dsecure.cartasi.it",
    "acs.sia.eu", "secure5.arcot.com", "authentication.cardinalcommerce.com", "www.klarna.com",
    "www.scalapay.com", "pay.google.com", "www.postepay.it", "idp.poste.it", "login.agid.gov.it",
    # names one letter away from a famous one, but real
    "finance.yahoo.com", "www.telegraf.rs", "twister.com", "inecobank.am", "booklog.jp",
    "www.bancobpi.pt", "www.applied.com", "l-cloud.jp", "www.bancomediolanum.es",
    "posta.it", "www.libero.it", "www.repubblica.it", "it.wikipedia.org",
    # not a web address
    "", "localhost", "127.0.0.1",
]


@pytest.fixture(scope="module")
def checker():
    return lookalike.Checker()


@pytest.mark.parametrize("host,brand", sorted(LOOKALIKES.items()))
def test_tricks_are_caught(checker, host, brand):
    assert checker.check(host) == brand


@pytest.mark.parametrize("host", REAL)
def test_real_sites_are_left_alone(checker, host):
    assert checker.check(host) is None


def test_ten_thousand_real_sites_near_famous_names(checker):
    lines = (ROOT / "tests/data/lookalike-near-real.txt").read_text("utf-8").splitlines()
    hosts = [h for h in lines if h and not h.startswith("#")]
    assert len(hosts) > 10000
    flagged = [(h, checker.check(h)) for h in hosts if checker.check(h)]
    assert flagged == []


def test_a_site_marked_as_fine_is_not_flagged_again(checker):
    assert checker.check("www.paypa1.com") == "PayPal"
    assert checker.check("www.paypa1.com", allowed={"paypa1.com"}) is None


def test_every_famous_site_is_its_own():
    """The official domains of each name are not flagged as any other name."""
    c = lookalike.Checker()
    for _display, _key, _sk, domains in c.brands:
        for d in domains:
            assert c.check(d) is None, d
            assert c.check("www." + d) is None, d


SHOWN = r"""
from PyQt6.QtCore import QUrl

def steps(ike, qapp, out):
    win = ike.windows[0]
    v = win.current_view()
    done = {}
    v.page().loadFinished.connect(lambda ok: done.setdefault("ok", ok))
    # a page with an address that imitates PayPal (no network: the address is
    # the base address of local content)
    v.setHtml("<!doctype html><title>t</title><input type=password>", QUrl("http://paypa1.com/login"))
    while "ok" not in done:
        yield 20
    yield 300
    bar = win.lookalike_bar
    out["shown"] = bar.isVisible()
    out["text"] = bar.text.text()
    out["page_ok"] = done["ok"]
    bar.ok.click()
    yield 100
    out["hidden_after_fine"] = not bar.isVisible()
    out["remembered"] = list(ike.config["lookalike_ok"])
    # the real one: no bar
    done.clear()
    v.setHtml("<!doctype html><title>t</title>", QUrl("https://www.paypal.com/"))
    while "ok" not in done:
        yield 20
    yield 200
    out["real_shown"] = bar.isVisible()
    # and nothing at all when Sosia is off
    ike.config["lookalike_warn"] = False
    done.clear()
    v.setHtml("<!doctype html><title>t</title>", QUrl("http://arnazon.it/"))
    while "ok" not in done:
        yield 20
    yield 200
    out["off_shown"] = bar.isVisible()
"""


def test_the_warning_above_the_page(run_ike):
    out = run_ike(SHOWN)
    assert out["page_ok"], out                      # nothing is blocked
    assert out["shown"], out
    assert "PayPal" in out["text"] and "paypa1.com" in out["text"], out
    assert out["hidden_after_fine"] and out["remembered"] == ["paypa1.com"], out
    assert not out["real_shown"], out
    assert not out["off_shown"], out
