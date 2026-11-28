"""1.1.31 (the owner): the logo's circuit lights up while the new tab page is shown: a light of about
3 s, then 2 s of rest, light on the computer: one pulse moved on by the page 24 times a second, nothing
at all between two pulses, none in a tab that is not shown, none without the interface's effects."""

from test_security import JS

STEPS = JS + r'''
def steps(ike, qapp, out):
    import time
    from PyQt6.QtCore import QUrl
    win = ike.windows[0]
    view = win.current_view()
    yield from load(view, "ike:newtab")
    probe = """(function () {
      var g = document.querySelector('.logo-glow');
      if (!window.__seen) {
        window.__seen = {on: 0, frames: 0, idle: 0, running: 0};
        new MutationObserver(function () { if (g.classList.contains('on')) __seen.on++; })
          .observe(g, {attributes: true, attributeFilter: ['class']});
        (function f() { __seen.frames++; requestAnimationFrame(f); })();
      }
      return {shown: getComputedStyle(g).display, on: __seen.on, hidden: document.hidden,
              running: document.getAnimations().filter(function (a) { return a.playState === 'running'; }).length};
    })()"""
    out["start"] = yield from js(view, probe)
    yield 9000
    out["shown"] = yield from js(view, probe)
    # between two pulses nothing runs
    idle = []
    for _ in range(40):
        r = yield from js(view, "[document.querySelector('.logo-glow').classList.contains('on'), document.getAnimations().filter(function (a) { return a.playState === 'running'; }).length]")
        idle.append(r)
        yield 100
    out["idle"] = idle
    # another tab in front: this one is hidden, and its logo does nothing
    win.add_tab("about:blank")
    yield 1000
    before = (yield from js(view, probe))["on"]
    yield 9000
    after = yield from js(view, probe)
    out["hidden"] = [before, after["on"], after["hidden"]]
'''


def test_the_logo_lights_up_only_while_shown(run_ike):
    out = run_ike(STEPS, settings={"ui_effects": True, "welcome_done": True},
                  env={"IKE_REDUCED_MOTION": "0", "IKE_TEST_WEATHER": "http://127.0.0.1:9"}, timeout=120)
    assert out["start"]["shown"] == "block", out["start"]
    assert out["shown"]["on"] >= 2, out["shown"]                    # a pulse, 2 s of rest, a pulse
    assert all(r[1] == 0 for r in out["idle"]), out["idle"]          # never left running by itself
    assert any(not r[0] for r in out["idle"]), out["idle"]           # and a rest between the pulses
    b, a, hidden = out["hidden"]
    assert hidden is True and a - b <= 1, out["hidden"]


def test_no_light_without_the_effects(run_ike):
    out = run_ike(JS + r'''
def steps(ike, qapp, out):
    view = ike.windows[0].current_view()
    yield from load(view, "ike:newtab")
    yield 5000
    out["r"] = yield from js(view, "[getComputedStyle(document.querySelector('.logo-glow')).display, document.querySelector('.logo-glow').classList.contains('on'), document.body.className]")
''', settings={"ui_effects": False, "welcome_done": True}, env={"IKE_TEST_WEATHER": "http://127.0.0.1:9"}, timeout=90)
    assert out["r"][0] == "none" and out["r"][1] is False, out["r"]
