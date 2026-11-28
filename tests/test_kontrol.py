"""1.1.31: ike:kontrol, what I.K.E. blocked, counted on this computer only: the month, the month before,
the total, and this session's counts by kind and by site. The sites of private windows are never listed;
a web page cannot open it nor read it."""

import sys

from conftest import APP
from test_security import JS

sys.path.insert(0, str(APP))


class Cfg:
    def __init__(self, **data):
        self.data = {"blocked_total": 48207, "blocked_month": {}, "blocked_counter": "month"}
        self.data.update(data)

    def __getitem__(self, key):
        return self.data[key]


def st(ads=0, scripts=0, cookies=0, https=0, params=0):
    return {"ads": ads, "scripts": scripts, "cookies": cookies, "https": https, "params": params}


def test_the_parts_of_the_page():
    import time

    from ike import newtab
    now = time.mktime((2026, 11, 15, 12, 0, 0, 0, 0, -1))
    cfg = Cfg(blocked_month={"key": "2026-11", "count": 3760, "prev_key": "2026-10", "prev": 5912})
    stats = {"www.youtube.com": st(ads=500, scripts=312), "amazon.it": st(ads=600, scripts=4, cookies=3),
             "secret.example": st(ads=9000), "<b>x.example": st(scripts=2), "quiet.example": st(https=4, params=7)}
    for i in range(12):
        stats["site%d.example" % i] = st(ads=1)
    parts = newtab.kontrol_parts(cfg, stats, {"secret.example"}, now)
    assert "3.760" in parts["readouts"] and "5.912" in parts["readouts"] and "48.207" in parts["readouts"]
    sites = parts["sites"]
    assert "secret.example" not in sites                               # a private window's site
    assert sites.index("youtube.com") < sites.index("amazon.it")       # the most first, "www." left out
    assert "<b>x.example" not in sites and "&lt;b&gt;x.example" in sites
    assert "quiet.example" not in sites                                # nothing of its blocked was ads or scripts
    assert sites.count('class="row"') == newtab.KONTROL_SITES
    # the private site still adds to the counts by kind: 500 + 600 + 9000 + 12 ads
    assert "10.112" in parts["kinds"]
    assert 'style="width:100.0%"' in parts["kinds"] and 'style="width:100.0%"' in sites
    empty = newtab.kontrol_parts(cfg, {}, set(), now)
    assert 'class="empty"' in empty["kinds"] and 'class="empty"' in empty["sites"]


STEPS = JS + r'''
def steps(ike, qapp, out):
    from PyQt6.QtCore import QUrl
    ike.shields.stats["www.example.org"] = dict(ads=40, scripts=2, cookies=1, https=0, params=3)
    ike.shields.stats["hidden.example"] = dict(ads=99, scripts=0, cookies=0, https=0, params=0)
    ike.shields.private_hosts.add("hidden.example")
    view = ike.windows[0].current_view()
    yield from load(view, "ike:kontrol")
    yield 600
    out["page"] = yield from js(view, """(function () {
      var r = document.querySelectorAll('.panel')[1].querySelectorAll('.row');
      return {title: document.title, sites: [].map.call(r, function (x) { return x.textContent; }),
              readouts: document.querySelectorAll('.ro').length, font: getComputedStyle(document.querySelector('.ro b')).fontFamily,
              pad: getComputedStyle(document.querySelector('.trace i'), '::after').width};
    })()""")
    # a web page cannot show it nor read it
    view.setHtml("<iframe src='ike:kontrol'></iframe><script>fetch('ike:kontrol').then(function (r) { return r.text(); })"
                 ".then(function (t) { document.title = 'read:' + t.length; }, function () { document.title = 'refused'; });"
                 "</script>", QUrl("http://site.example/"))
    yield 1500
    out["web"] = [view.title(), (yield from js(view, "(function(){try{return document.querySelector('iframe').contentDocument ? 'open' : 'closed'}catch(e){return 'closed'}})()"))]
'''


def test_the_page_in_the_browser(run_ike):
    out = run_ike(STEPS, settings={"welcome_done": True}, timeout=90)
    p = out["page"]
    assert p["title"] == "I.K.E. Kontrol" and p["readouts"] >= 2, p
    assert p["sites"] == ["example.org42"], p["sites"]                # the private site is not there
    assert "IKE Cyber" in p["font"] and p["pad"] == "10px", p
    assert out["web"][0] != "" and not out["web"][0].startswith("read:"), out["web"]
