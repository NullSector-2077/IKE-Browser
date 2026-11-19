"""Speed without less protection (1.1.17, docs/review/performance-1117.md).

- A new AdBlock engine is built in a thread while the engine in use keeps
  blocking, and the Rust part lets go of Python's lock while it builds, so
  the interface does not stop.
- The shield's number is redrawn at most ten times a second, and always ends
  on the exact count.
- site_of() is remembered and gives the same answers.
- The limits of the resource monitor do not ask every tab for its downloads.
- An unchanged settings file is not written again.
- Looking for Widevine at start does not load the download modules.
"""

import json
import subprocess
import sys
import threading
import time

from conftest import APP, needs_engine


def _vendor():
    sys.path.insert(0, str(APP / "vendor"))
    try:
        import adblock
        return adblock
    finally:
        sys.path.remove(str(APP / "vendor"))


@needs_engine
def test_the_engine_is_built_without_holding_the_interface():
    """A big list built in another thread: the main thread goes on (before
    1.1.17 it stood still for as long as the build, about 90 ms here)."""
    adblock = _vendor()
    rules = "\n".join("||ads%d.example^\n##.banner-%d" % (i, i) for i in range(120000))

    def build():
        fs = adblock.FilterSet()
        fs.add_filter_list(rules)
        built.append(adblock.Engine(fs))
    built = []
    t = threading.Thread(target=build)
    gaps, last = [], time.perf_counter()
    t.start()
    while t.is_alive():
        time.sleep(0.002)
        now = time.perf_counter()
        gaps.append(now - last)
        last = now
    t.join()
    assert built and built[0].check_network_urls("https://ads5.example/x.js", "https://site.test/",
                                                  "script").matched
    assert len(gaps) > 5, "the build was too quick to tell"
    assert max(gaps) < 0.05, max(gaps)            # the main thread was never held for long


@needs_engine
def test_a_new_engine_takes_over_only_when_it_is_ready(run_ike):
    """After the first engine, a rebuild runs in the background: meanwhile the
    engine in use still blocks what it blocked; then the new rules apply."""
    out = run_ike(r'''
def steps(ike, qapp, out):
    import time
    b = ike.blocker
    yield 500
    page = "https://site.test/"
    out["before"] = b.request_action("https://ads.example.test/a.js", page, "script")[0]
    ike.config["custom_filters"] = "||newly-blocked.example^"
    a = time.perf_counter()
    b.load()
    out["load_returned_ms"] = (time.perf_counter() - a) * 1000
    out["building"] = b.building
    out["meanwhile"] = [b.request_action("https://ads.example.test/a.js", page, "script")[0],
                        b.request_action("https://newly-blocked.example/x.js", page, "script")[0]]
    for _ in range(200):
        if not b.building:
            break
        yield 20
    out["after"] = [b.request_action("https://ads.example.test/a.js", page, "script")[0],
                    b.request_action("https://newly-blocked.example/x.js", page, "script")[0]]
    b.load()                                    # nothing changed: nothing is built
    out["again_building"] = b.building
''', timeout=90)
    assert out["before"] == "block"
    assert out["building"] is True and out["load_returned_ms"] < 50, out
    assert out["meanwhile"] == ["block", "allow"], out
    assert out["after"] == ["block", "block"], out
    assert out["again_building"] is False


def test_the_shield_is_redrawn_at_most_ten_times_a_second(run_ike):
    """150 things blocked in a row on the page in view: a handful of redraws,
    and the number shown at the end is the exact count."""
    out = run_ike(r'''
def steps(ike, qapp, out):
    from PyQt6.QtCore import QUrl
    win = ike.windows[0]
    yield 500
    win.current_view().setHtml("<title>t</title>", QUrl("https://news.example.test/"))
    yield 800
    host = win.current_host()
    calls = []
    real = type(win).update_shield
    def counted(self):
        calls.append(1)
        real(self)
    type(win).update_shield = counted
    sh = ike.shields
    for _ in range(150):
        sh.count(host, "ads")
    out["right_away"] = len(calls)
    yield 400
    out["redraws"] = len(calls)
    out["shown"] = win.shield_btn.text()
    out["total"] = sh.total(host)
''', timeout=60)
    assert out["right_away"] == 0
    assert 1 <= out["redraws"] <= 3, out
    assert out["shown"] == str(out["total"]) == "150", out


def test_site_of_is_remembered_and_unchanged():
    sys.path.insert(0, str(APP))
    try:
        from ike.shields import site_of
    finally:
        sys.path.remove(str(APP))
    cases = {"www.bbc.co.uk": "bbc.co.uk", "a.b.example.com": "example.com", "user.github.io": "user.github.io",
             "x.user.github.io": "user.github.io", "127.0.0.1": "127.0.0.1", "localhost": "localhost", "": ""}
    for _ in range(2):                          # the second time from the cache
        assert {h: site_of(h) for h in cases} == cases
    assert site_of.cache_info().hits >= len(cases)
    assert site_of.cache_info().maxsize == 4096   # bounded


def test_the_monitor_limits_do_not_wake_every_tab(run_ike):
    """With a limit set and the window closed, the check reads memory and CPU
    only; the window, when open, still gets the data column."""
    out = run_ike(r'''
def steps(ike, qapp, out):
    from PyQt6.QtCore import QUrl
    win = ike.windows[0]
    for i in range(3):
        v = win.add_tab(QUrl("about:blank"), background=True)
        v.setHtml("<title>t</title>", QUrl("https://site%d.example.test/" % i))
    yield 1200
    asked = []
    for v in win.all_views():
        page = v.page()
        real = page.runJavaScript
        def spy(*a, real=real):
            asked.append(1)
            return real(*a)
        page.runJavaScript = spy
    mon = ike.resources
    mon.sample(net=False)
    out["limits_check"] = len(asked)
    mon.sample()
    out["window_sample"] = len(asked)
    yield 100
''', timeout=60)
    assert out["limits_check"] == 0
    assert out["window_sample"] > 0


def test_an_unchanged_settings_file_is_not_written_again(tmp_path, monkeypatch):
    import importlib
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    sys.path.insert(0, str(APP))
    try:
        from ike import config as C
        importlib.reload(C)
        cfg = C.Config()
        cfg.save()
        first = cfg.path.stat().st_mtime_ns
        time.sleep(0.02)
        cfg.save()                                   # nothing changed
        assert cfg.path.stat().st_mtime_ns == first
        cfg["homepage"] = "https://changed.example/"
        cfg.save()
        assert json.loads(cfg.path.read_text())["homepage"] == "https://changed.example/"
        cfg.path.unlink()                            # removed from outside: written again
        cfg.save()
        assert cfg.path.exists()
    finally:
        sys.path.remove(str(APP))


def test_looking_for_widevine_loads_no_download_code():
    code = ("import sys; sys.path[:0] = [%r]; import ike.drm as d; d.library_path(); "
            "print('urllib.request' in sys.modules, 'zipfile' in sys.modules)" % str(APP))
    res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         env={"QT_QPA_PLATFORM": "offscreen", "HOME": "/tmp"})
    assert res.stdout.split() == ["False", "False"], res.stdout + res.stderr
