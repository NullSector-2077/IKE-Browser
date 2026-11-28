"""I.K.E. Interference and the diagnosis behind it (1.1.32, the owner's brief
"Ripara sito" and its colours: incompat.py, interference.py,
securebar.danger_of).

- The detectors: a finding needs a protection that really acted (trusted
  evidence from the request check) and a coherent sign that something
  important does not work; a service worker alone, the page's own report
  alone, an unrelated error, a video site: nothing. Yellow when the site
  stays usable, orange when something essential is missing; a finding only
  grows more serious, keeps a known cause, and stays quiet in that tab for
  that site once settled.
- The page cannot raise anything: its own console messages, with a guessed
  key or none, are ignored; a page that is merely empty with no protection
  acting gives nothing.
- The octagon: red only from I.K.E.'s safety warnings and before any
  incompatibility, never pointing at "Repair this site"; one tab's finding
  is not another tab's; a private window has its own evidence; the level
  "off" shows nothing; opening the panel changes nothing; the octagon goes
  back to normal (with its fade) when the user says the site works.
- The animation: no timer without a state, none while the button is hidden
  (the phase kept), none with the effects off (a still rim instead); its
  cost per picture is measured.

SIMULATION: synthetic evidence and probe results for the detectors, a local
page for the forged reports, the safety warnings' own marks on the view.
"""

import http.server
import threading

import pytest

DETECTORS = r'''
def steps(ike, qapp, out):
    import json
    from ike import incompat as I

    class Ctx:
        def __init__(self, active=("fp", "workers"), video=False, level=3, danger=False):
            self.host, self.active, self.video_site = "app.example", list(active), video
            self.level, self.danger = level, danger

    def ev(trusted=(), weak=()):
        e = I.Evidence()
        for k in trusted:
            e.trusted[k] = e.trusted.get(k, 0) + 1
        for k in weak:
            e.weak[k] = e.weak.get(k, 0) + 1
        return e

    def judge(e, probe, ctx=None):
        ctx = ctx or Ctx()
        for d in I.DETECTORS:
            if d.relevant(e, ctx):
                f = d.judge(e, probe, ctx)
                if f is not None:
                    return [f.detector, list(f.keys), f.severity]
        return None

    full = {"blank": False, "sparse": False, "mediaError": False}
    empty = {"blank": True, "sparse": True, "mediaError": False}
    sparse = {"blank": False, "sparse": True, "mediaError": False}
    out["sw_alone_fine"] = judge(ev(["worker:service"]), full)
    out["sw_alone_empty"] = judge(ev(["worker:service"]), empty)
    out["weak_alone"] = judge(ev([], ["protected_worker_refused"]), empty)
    out["page_worker_content"] = judge(ev(["worker:dedicated"]), full)
    out["page_worker_sparse"] = judge(ev(["worker:shared"]), sparse)
    out["copy_and_sw_sparse"] = judge(ev(["worker:service"], ["protected_worker_refused"]), sparse)
    out["workers_at_kontrol"] = judge(ev(["worker:dedicated"]), empty, Ctx(active=("fp",)))
    # Maximum (2026-11-28): refused whatever was chosen; the one choice put forward is Kontrol
    out["max_empty"] = judge(ev(["worker:shared"]), empty, Ctx(active=("fp",), level=4))
    out["max_content"] = judge(ev(["worker:dedicated"]), full, Ctx(active=("fp",), level=4))
    out["max_sw_fine"] = judge(ev(["worker:service"]), full, Ctx(active=("fp",), level=4))
    out["max_danger"] = judge(ev(["worker:shared"]), empty, Ctx(active=("fp",), level=4, danger=True))
    out["max_fp_off"] = judge(ev(["worker:shared"]), empty, Ctx(active=(), level=4))
    out["own_script_empty"] = judge(ev(["own:script"]), empty)
    out["own_script_fine"] = judge(ev(["own:script"]), full)
    out["own_script_video"] = judge(ev(["own:script"]), empty, Ctx(video=True))
    out["player"] = judge(ev(["own:media"]), dict(full, mediaError=True))
    out["player_video"] = judge(ev(["own:media"]), dict(full, mediaError=True), Ctx(video=True))
    out["nothing"] = judge(ev(), empty)

    # the life of a finding in one tab (a stand-in for the view)
    d = ike.diagnosis
    class V:
        pass
    v = V()
    v._ike_diag = {"host": "app.example", "finding": None, "probes": 0, "timer": None, "pending": False,
                   "ended": None, "quiet": set()}
    seen = []
    d.changed.connect(lambda view: seen.append(view is v))
    F = I.Finding
    d._set(v, F("workers", "app.example", ("workers",), "c", I.ATTENTION))
    out["first"] = v._ike_diag["finding"].severity
    d._set(v, F("empty", "app.example", (), "c", I.SERIOUS))
    out["vaguer_kept"] = [v._ike_diag["finding"].detector, v._ike_diag["finding"].severity]
    d._set(v, F("workers", "app.example", ("workers",), "c", I.SERIOUS))
    out["grows"] = v._ike_diag["finding"].severity
    d._set(v, F("workers", "app.example", ("workers",), "c", I.ATTENTION))
    out["never_less"] = v._ike_diag["finding"].severity
    d.resolved(v)
    out["resolved"] = [v._ike_diag["finding"], d.ended(v)]
    d._set(v, F("workers", "app.example", ("workers",), "c", I.SERIOUS))
    out["quiet_after"] = v._ike_diag["finding"]
    out["signals"] = len(seen)

    # the ledger: per profile scope and site
    L = I.Ledger()
    L.note(1, "a.example", "worker:shared")
    L.weak(2, "a.example", "protected_worker_refused")
    out["scope1"] = L.get(1, "a.example").n("worker:")
    out["scope2_trusted"] = L.get(2, "a.example").n("worker:") if L.get(2, "a.example") else 0
    out["other_site"] = L.get(1, "b.example") is None
    yield 10
'''


def test_detectors_and_the_life_of_a_finding(run_ike):
    out = run_ike(DETECTORS, timeout=60)
    # nothing to say: a service worker alone (the page fine or not), the page's
    # own word alone, the workers where the level lets them run, nothing acted
    assert out["sw_alone_fine"] is None, out
    assert out["weak_alone"] is None and out["nothing"] is None, out
    assert out["workers_at_kontrol"] is None, out
    assert out["max_empty"] == ["workers_max", ["kontrol"], "serious"], out
    assert out["max_content"] == ["workers_max", ["kontrol"], "attention"], out
    assert out["max_sw_fine"] is None and out["max_danger"] is None, out
    # the site's fingerprinting switch off does not let them in at Maximum: the same cause
    assert out["max_fp_off"] == ["workers_max", ["kontrol"], "serious"], out
    assert out["own_script_fine"] is None and out["own_script_video"] is None, out
    assert out["player_video"] is None, out
    # an empty app whose service worker alone was refused: the blank page is the sign
    assert out["sw_alone_empty"] == ["workers", ["workers"], "serious"], out
    # yellow while the site shows its content, orange when it does not start
    assert out["page_worker_content"] == ["workers", ["workers"], "attention"], out
    assert out["page_worker_sparse"] == ["workers", ["workers"], "serious"], out
    assert out["copy_and_sw_sparse"] == ["workers", ["workers"], "serious"], out
    # yellow (the review: a script of the site's own address blocked by the
    # lists is often a tracker; the search with the user finds the cause)
    assert out["own_script_empty"] == ["empty", [], "attention"], out
    assert out["player"] == ["player", [], "attention"], out
    # a finding: a known cause stays, it only grows, and once settled it stays quiet
    assert out["first"] == "attention", out
    assert out["vaguer_kept"] == ["workers", "attention"], out
    assert out["grows"] == "serious" and out["never_less"] == "serious", out
    assert out["resolved"] == [None, "resolved"], out
    assert out["quiet_after"] is None, out
    assert out["signals"] == 3, out                      # attention, serious, resolved
    assert out["scope1"] == 1 and out["scope2_trusted"] == 0 and out["other_site"] is True, out


@pytest.fixture
def site():
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.startswith("/redir"):
                self.send_response(302)
                self.send_header("Location", "/page?after-redirect")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if self.path.startswith("/forge"):
                # a page that tries to raise a finding by itself: the report's
                # words with no key, with a guessed key, and an empty body
                body = (b"<!doctype html><title>f</title><body><script>"
                        b"console.debug('protected_worker_refused');"
                        b"console.debug('ike-rk-0123456789abcdef0123456789abcdef protected_worker_refused');"
                        b"console.log('ike-rk- protected_worker_refused');"
                        b"for (var k in window) { if (/ike|rk/i.test(k)) console.log('found ' + k); }"
                        b"window.result = JSON.stringify({ok: 1});"
                        b"</script></body>")
            else:
                body = b"<!doctype html><title>p</title><body><p>" + b"Some text. " * 60 + b"</p></body>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1]
    srv.shutdown()


WINDOW = r'''
import time
from PyQt6.QtCore import QUrl
from PyQt6.QtWidgets import QApplication

def load(view, url):
    done = {}
    view.page().loadFinished.connect(lambda ok, d=done: d.setdefault("ok", ok))
    view.load(QUrl(url))
    while "ok" not in done:
        yield 20

def steps(ike, qapp, out):
    from ike import incompat as I
    win = ike.windows[0]
    anim = win.shield_btn.interference
    out["idle_timer"] = anim._timer.isActive()
    view = win.current_view()
    # the page tries to raise a finding by itself (Maximum: every protection on)
    yield from load(view, "http://127.0.0.1:%d/forge")
    yield 6000
    scope = ike.diagnosis.scope_of(view)
    ev = ike.diagnosis.ledger.get(scope, "127.0.0.1")
    out["forged_weak"] = dict(ev.weak) if ev else {}
    out["forged_state"] = win.interference_state()[0]
    out["forged_timer"] = anim._timer.isActive()

    # a finding on this tab, by I.K.E.'s own hand (the stand-in for evidence)
    yield from load(view, "http://127.0.0.1:%d/page")
    view._ike_diag["quiet"] = set()
    ike.diagnosis._set(view, I.Finding("workers", "127.0.0.1", ("workers",), I.SiteWorkers.CAUSE, I.SERIOUS))
    yield 100
    out["state"] = win.interference_state()
    out["anim"] = anim.state
    out["timer"] = anim._timer.isActive()
    out["tip"] = win.shield_btn.toolTip()
    out["a11y"] = win.shield_btn.accessibleDescription()
    # opening and closing the panel changes nothing
    win.shield_menu.aboutToShow.emit()
    win.shield_menu.aboutToHide.emit()
    out["after_panel"] = anim.state

    # another tab: its own story; back: the finding is still there
    other = win.add_tab(QUrl("http://127.0.0.1:%d/page"))
    yield 1500
    # (its page loaded well: at most its own short green confirmation)
    out["other_tab"] = [win.interference_state()[0], anim.state, anim._timer.isActive() and not anim.confirming()]
    win.set_current(view) if hasattr(win, "set_current") else win.tabs.setCurrentIndex(win.tabs.indexOf(view))
    yield 200
    out["back"] = anim.state

    # hidden window: no timer, the phase kept; shown again: on again
    win.showMinimized()
    yield 300
    win.hide()
    yield 300
    out["hidden_timer"] = anim._timer.isActive()
    phase = anim.phase
    yield 500
    out["phase_kept"] = anim.phase == phase
    win.showNormal()
    yield 500
    out["shown_timer"] = anim._timer.isActive()

    # the cost of one picture of the button (the animation's frame)
    btn = win.shield_btn
    n0, t0 = anim.frames, time.perf_counter()
    for i in range(60):
        anim.phase = i / 60
        btn.repaint()
    out["frame_ms"] = (time.perf_counter() - t0) * 1000 / max(1, anim.frames - n0)

    # a safety warning: red first, never pointing at "Repair this site"
    view.lookalike, view.lookalike_host = "Example Bank", "127.0.0.1"
    win.sync_interference()
    yield 700
    out["danger"] = win.interference_state()
    out["danger_anim"] = anim.state
    win.shield_menu.aboutToShow.emit()
    p = win.shield_panel
    out["danger_panel"] = {"note": p.diag_note.text(), "ok": p.diag_ok.isVisibleTo(p),
                           "default": p.repair_btn.isDefault()}
    view.lookalike = None
    view.cert_refused = "127.0.0.1"                        # as WebPage.certificateError marks it
    win.danger_changed(view)
    out["cert"] = win.interference_state()
    view.cert_refused = None
    win.sync_interference()
    out["after_danger"] = anim.state

    # the level "off" on the site: nothing to say
    ike.config["site_levels"]["127.0.0.1"] = "off"
    win.update_shield()
    out["off"] = anim.state
    ike.config["site_levels"].pop("127.0.0.1", None)
    win.update_shield()
    out["on_again"] = anim.state

    # the effects off: a still rim, no timer
    ike.config["ui_effects"] = False
    anim.set_state(None)
    win.sync_interference()
    out["still"] = [anim.state, anim.style is not None, anim._timer.isActive()]
    ike.config["ui_effects"] = True
    anim.set_state(None)
    win.sync_interference()

    # the user says the site works: the fade, then nothing at all
    win.shield_menu.aboutToShow.emit()
    p.diag_ok.click()
    out["fading"] = [anim.state, anim._anim is not None]
    yield 700
    out["end"] = [anim.state, anim.style, anim._timer.isActive(), win.shield_btn.accessibleDescription()]
    # reloading the same site in this tab: settled, nothing again
    ike.diagnosis._set(view, I.Finding("workers", "127.0.0.1", ("workers",), I.SiteWorkers.CAUSE, I.SERIOUS))
    out["settled"] = win.interference_state()[0]
'''


def test_the_octagon_in_the_window(run_ike, site):
    out = run_ike(WINDOW % (site, site, site), settings={"shield_level": "maximum", "https_only": False},
                  timeout=150)
    assert out["idle_timer"] is False, out
    # the page's own words: never evidence, whatever key it guesses
    assert out["forged_weak"] == {} and out["forged_state"] is None and out["forged_timer"] is False, out
    assert out["state"][0] == "serious" and "Repair this site" in out["state"][1], out
    assert out["anim"] == "serious" and out["timer"] is True, out
    assert out["tip"].startswith("A protection may stop this site") and out["a11y"], out
    assert out["after_panel"] == "serious", out
    assert out["other_tab"] == [None, None, False], out
    assert out["back"] == "serious", out
    assert out["hidden_timer"] is False and out["phase_kept"] is True, out
    assert out["shown_timer"] is True, out
    assert out["frame_ms"] < 4, out                       # a few tenths of a millisecond on a PC
    assert out["danger"][0] == "danger" and "Repair" not in out["danger"][1], out
    assert out["danger_anim"] == "danger", out
    assert out["danger_panel"]["note"].startswith("⛔") and "Repair" not in out["danger_panel"]["note"], out
    assert out["danger_panel"]["ok"] is False and out["danger_panel"]["default"] is False, out
    assert out["cert"][0] == "danger" and "certificate" in out["cert"][1], out
    assert out["after_danger"] == "serious", out          # the incompatibility is still there
    assert out["off"] is None and out["on_again"] == "serious", out
    assert out["still"] == ["serious", True, False], out
    assert out["fading"] == [None, True], out
    assert out["end"] == [None, None, False, ""], out
    assert out["settled"] is None, out


PRIVATE = r'''
def steps(ike, qapp, out):
    from PyQt6.QtCore import QUrl
    win = ike.windows[0]
    priv = ike.new_window(private=True)
    yield 1500
    a, b = win.current_view(), priv.current_view()
    sa, sb = ike.diagnosis.scope_of(a), ike.diagnosis.scope_of(b)
    out["scopes_differ"] = sa != sb and None not in (sa, sb)
    ike.diagnosis.note(sa, "127.0.0.1", "worker:shared")
    out["normal"] = ike.diagnosis.ledger.get(sa, "127.0.0.1") is not None
    out["private"] = ike.diagnosis.ledger.get(sb, "127.0.0.1") is None
    yield 10
'''


def test_a_private_window_has_its_own_evidence(run_ike):
    out = run_ike(PRIVATE, timeout=60)
    assert (out["scopes_differ"], out["normal"], out["private"]) == (True, True, True), out


GREEN = r"""
import time
from PyQt6.QtCore import QUrl

def load(view, url):
    done = {}
    view.page().loadFinished.connect(lambda ok, d=done: d.setdefault("ok", ok))
    view.load(QUrl(url))
    while "ok" not in done:
        yield 20
    return done["ok"]

def steps(ike, qapp, out):
    from ike import incompat as I
    win = ike.windows[0]
    anim = win.shield_btn.interference
    view = win.current_view()
    base = "http://127.0.0.1:%d"
    yield from load(view, base + "/page")
    yield 800
    out["first"] = [anim.confirms, anim.confirming(), win.shield_btn.toolTip().split("\n")[0]]
    out["first_timer"] = anim._timer.isActive()
    yield 2000
    out["after"] = [anim.confirming(), anim.style is None, anim._timer.isActive()]
    # the same site again at once (a web app reloading itself): not again
    yield from load(view, base + "/page?again")
    yield 900
    out["same_site_again"] = anim.confirms
    # another site at once: the tab rests (two sites sending it to each other)
    yield from load(view, "http://localhost:%d/page?rest")
    yield 900
    out["tab_rest"] = anim.confirms
    # another site later: its own green
    view._ike_confirmed_at = -1e9
    yield from load(view, "http://localhost:%d/page")
    yield 900
    out["other_site"] = anim.confirms
    yield 2000
    # a redirect: one green for the page it ends on
    view._ike_confirmed_site = None
    view._ike_confirmed_at = -1e9
    yield from load(view, base + "/redir")
    yield 900
    out["redirect"] = [anim.confirms, view.url().toString().endswith("after-redirect")]
    yield 2000
    # a load that fails: none
    view._ike_confirmed_site = None
    view._ike_confirmed_at = -1e9
    n = anim.confirms
    ok = yield from load(view, "http://127.0.0.1:9/nothing")
    yield 900
    out["failed"] = [ok, anim.confirms - n]
    # two pages at once (a quick click): at most one green, for the last one
    view._ike_confirmed_site = None
    view._ike_confirmed_at = -1e9
    n = anim.confirms
    view.load(QUrl(base + "/page?one"))
    yield 30
    yield from load(view, "http://localhost:%d/page?two")
    yield 900
    out["rapid"] = anim.confirms - n
    yield 2000
    # a tab in the background: none
    view._ike_confirmed_site = None
    view._ike_confirmed_at = -1e9
    n = anim.confirms
    bg = win.add_tab(QUrl(base + "/page?bg"), background=True)
    yield 2500
    out["background"] = anim.confirms - n
    # an exception on the site, the protection off, the effects off: none
    for key, setup, undo in (
            ("exception", lambda: ike.config["site_opts"].__setitem__("127.0.0.1", {"ads": False}),
             lambda: ike.config["site_opts"].pop("127.0.0.1", None)),
            ("off", lambda: ike.config["site_levels"].__setitem__("127.0.0.1", "off"),
             lambda: ike.config["site_levels"].pop("127.0.0.1", None)),
            ("effects_off", lambda: ike.config.__setitem__("ui_effects", False),
             lambda: ike.config.__setitem__("ui_effects", True))):
        setup()
        view._ike_confirmed_site = None
        view._ike_confirmed_at = -1e9
        n = anim.confirms
        yield from load(view, base + "/page?" + key)
        yield 900
        out[key] = anim.confirms - n
        undo()
    # a danger in effect: none (red instead)
    view._ike_confirmed_site = None
    view._ike_confirmed_at = -1e9
    n = anim.confirms
    yield from load(view, base + "/page?danger")
    view.lookalike, view.lookalike_host = "Example Bank", "127.0.0.1"
    win.sync_interference()
    yield 900
    out["danger"] = [anim.confirms - n, anim.state]
    view.lookalike = None
    win.sync_interference()
    yield 600
    # something the diagnosis still looks at: none
    view._ike_confirmed_site = None
    view._ike_confirmed_at = -1e9
    ike.config["site_levels"]["127.0.0.1"] = "maximum"
    ike.config.set_site_opt("127.0.0.1", "workers", True)     # the user's block: refusals are looked into
    yield from load(view, base + "/page?pending")
    d = ike.diagnosis
    d.ledger.note(d.scope_of(view), "127.0.0.1", "worker:shared")
    out["pending"] = win.confirm_due(view)
    ike.config["site_levels"].pop("127.0.0.1", None)
    ike.config.set_site_opt("127.0.0.1", "workers", None)
    # a finding while the green plays: at once the finding's colour
    view._ike_confirmed_site = None
    view._ike_confirmed_at = -1e9
    yield from load(view, "http://localhost:%d/page?cut")
    yield 700
    out["cut_before"] = anim.confirming()
    view._ike_diag["quiet"] = set()
    d._set(view, I.Finding("workers", "localhost", ("workers",), I.SiteWorkers.CAUSE, I.SERIOUS))
    yield 50
    out["cut_after"] = [anim.confirming(), anim.state]
    d.resolved(view)
    yield 800
    # another tab in front while it plays: it stops
    view._ike_confirmed_site = None
    view._ike_confirmed_at = -1e9
    other = win.add_tab(QUrl("about:blank"), background=True)
    yield from load(view, base + "/page?switch")
    yield 650
    out["switch_before"] = anim.confirming()
    win.set_current(other)
    yield 100
    out["switch_after"] = [anim.confirming(), anim.style is None]
"""


def test_the_green_confirmation(run_ike, site):
    out = run_ike(GREEN % ((site,) * 5), timeout=200)
    assert out["first"][0] == 1 and out["first"][1] is True, out
    assert out["first"][2].startswith("I.K.E. found nothing wrong") and "does not prove" in out["first"][2], out
    assert out["first_timer"] is True, out
    assert out["after"] == [False, True, False], out              # 1.8 s, then nothing at all
    assert out["same_site_again"] == 1, out
    assert out["tab_rest"] == 1 and out["other_site"] == 2, out
    assert out["redirect"] == [3, True], out
    assert out["failed"] == [False, 0], out
    assert out["rapid"] <= 1, out
    assert out["background"] == 0, out
    assert out["exception"] == 0 and out["off"] == 0 and out["effects_off"] == 0, out
    assert out["danger"] == [0, "danger"], out
    assert out["pending"] is False, out
    assert out["cut_before"] is True and out["cut_after"] == [False, "serious"], out
    assert out["switch_before"] is True and out["switch_after"] == [False, True], out
