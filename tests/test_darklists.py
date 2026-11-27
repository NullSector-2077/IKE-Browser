"""Dark Reader's lists kept up to date by the browser itself (1.1.27, the
owner's decision: no new version every day for simple lists).

- The browser and the builder of the bundled copy read and check the lists
  with the very same functions (tools/build-darkreader-lists.py imports
  ike/darklists.py; 1.1.29: Dark Reader's engine left I.K.E., its lists stay).
- What is fetched is refused, and nothing changes, when it is not data for
  Dark Reader (anything that looks like a script), lacks the common fix, is
  much shorter than the copy I.K.E. came with, is too large, or was
  redirected away from raw.githubusercontent.com.
- The fetched lists are used when they are at least as new as that copy;
  older or damaged ones are not.
- In the browser: once a day (with automatic updates on), in the background;
  a failure is tried again a few hours later; the dark pages loaded next take
  the new lists; nothing with automatic updates off.
- The daily maintenance no longer makes a version every day for changed lists
  only: the bundled copy is refreshed by a weekly candidate (1.1.29).

SIMULATION: stand-ins for the network (no request leaves the computer).
"""

import importlib.util
import io
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

FIXES = """*

INVERT
.logo

CSS
.x { color: red; }

================================

example.test

CSS
.page { background: #111; }

IGNORE INLINE STYLE
.keep
"""
DARK = "dark.example.test\n*.night.test\n"
HINTS = """example.test

TARGET
html

MATCH
.dark-theme
"""


def texts(**over):
    t = {"fixes": FIXES, "dark_sites": DARK, "detector_hints": HINTS}
    t.update(over)
    return t


class Response(io.BytesIO):
    def __init__(self, data, url, length=None):
        super().__init__(data)
        self._url = url
        self.headers = {"Content-Length": str(length)} if length else {}

    def geturl(self):
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def opener(files, redirect=None, length=None):
    seen = []

    def open_(req, timeout=None):
        url = req.full_url
        seen.append((url, dict(req.header_items())))
        name = url.rsplit("/", 1)[1]
        part = {v: k for k, v in __import__("ike.darklists", fromlist=["FILES"]).FILES.items()}[name]
        return Response(files[part].encode("utf-8"), redirect or url, length)
    open_.seen = seen
    return open_


def test_the_browser_reads_the_lists_as_the_builder():
    from ike import darklists
    spec = importlib.util.spec_from_file_location("bdl", ROOT / "tools" / "build-darkreader-lists.py")
    bdl = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bdl)
    # the builder has no reader of its own: it loads the browser's (the same file)
    dl = bdl.darklists()
    assert Path(dl.__file__).resolve() == Path(darklists.__file__).resolve()
    for name in ("parse", "parse_blocks", "parse_array", "fix_value", "hint_value", "data_problems", "check"):
        assert not hasattr(bdl, name), name
        assert getattr(dl, name).__code__.co_code == getattr(darklists, name).__code__.co_code, name
    # the copy I.K.E. comes with passes the browser's own check
    bundled = json.loads((ROOT / "ike/resources/darkreader-data.json").read_text("utf-8"))
    assert darklists.check(bundled, bundled) == ""


def test_fetched_and_checked():
    from ike import darklists
    op = opener(texts())
    lists = darklists.fetch(None, opener=op)
    assert lists["fixes"][0]["url"] == ["*"] and lists["fixes"][1]["css"] == ".page { background: #111; }"
    assert lists["dark_sites"] == ["dark.example.test", "*.night.test"]
    assert lists["detector_hints"][0]["match"] == [".dark-theme"]
    assert len(lists["lists_date"]) == 10 and lists["fetched"] > 0
    urls = [u for u, _ in op.seen]
    assert all(u.startswith("https://raw.githubusercontent.com/darkreader/darkreader/main/src/config/") for u in urls)
    assert len(urls) == 3
    for _, headers in op.seen:                     # the browser's own User-Agent, nothing else of the user's
        assert set(k.lower() for k in headers) == {"user-agent"}, headers


@pytest.mark.parametrize("bad, why", [
    (dict(fixes=FIXES.replace(".x { color: red; }", ".x { background: url(javascript:alert(1)) }")), "Dark Reader"),
    (dict(fixes=FIXES.replace(".x { color: red; }", "</style><script>alert(1)</script>")), "Dark Reader"),
    (dict(fixes=FIXES.split("================================")[1]), "common fix"),
    (dict(fixes="nothing here"), "common fix"),
])
def test_refused_when_not_data_for_dark_reader(bad, why):
    from ike import darklists
    with pytest.raises(ValueError) as e:
        darklists.fetch(None, opener=opener(texts(**bad)))
    assert why in str(e.value)


def test_refused_when_cut_too_large_or_redirected():
    from ike import darklists
    bundled = {"fixes": [{"url": ["*"]}] * 10, "dark_sites": ["a"] * 10, "detector_hints": [{"url": ["b"]}]}
    with pytest.raises(ValueError, match="fixes: 2 entries where I.K.E. came with 10"):
        darklists.fetch(bundled, opener=opener(texts()))
    with pytest.raises(ValueError, match="redirected"):
        darklists.fetch(None, opener=opener(texts(), redirect="https://evil.example/x.config"))
    with pytest.raises(ValueError, match="redirected"):
        darklists.fetch(None, opener=opener(texts(), redirect="http://raw.githubusercontent.com/x"))
    with pytest.raises(ValueError, match="too large"):
        darklists.fetch(None, opener=opener(texts(), length=darklists.MAX_BYTES + 1))
    with pytest.raises(ValueError, match="too large or not text"):
        darklists.fetch(None, opener=opener(texts(dark_sites="a\x00b")))


def test_the_newer_lists_are_used(tmp_path, monkeypatch):
    from ike import darkfixes, darklists
    monkeypatch.setattr(darklists, "store_path", lambda: tmp_path / "darkreader-lists.json")
    bundled = darkfixes.bundled()
    darkfixes.reset()
    try:
        assert not darkfixes.data().get("lists_fetched")              # nothing fetched: the copy
        lists = darklists.fetch(None, opener=opener(texts()))
        lists["lists_date"] = "2000-01-01"                            # older than the copy
        darklists.save(lists)
        darkfixes.reset()
        assert not darkfixes.data().get("lists_fetched")
        lists["lists_date"] = "2999-01-01"
        darklists.save(lists)
        darkfixes.reset()
        d = darkfixes.data()
        assert d["lists_fetched"] and d["version"] == bundled["version"] and len(d["fixes"]) == 2
        assert darkfixes.fix_for("https://www.example.test/a")["css"].endswith(".page { background: #111; }")
        assert darkfixes.in_dark_list("https://a.night.test/") and darkfixes.in_dark_list("https://dark.example.test/")
        assert darkfixes.hints_for("https://example.test/")[0]["target"] == "html"
        # a damaged file is not used
        bad = dict(lists, fixes=[{"url": ["*"], "css": "<script>x</script>"}])
        (tmp_path / "darkreader-lists.json").write_text(json.dumps(bad), "utf-8")
        darkfixes.reset()
        assert not darkfixes.data().get("lists_fetched")
        (tmp_path / "darkreader-lists.json").write_text("{not json", "utf-8")
        darkfixes.reset()
        assert not darkfixes.data().get("lists_fetched")
    finally:
        darkfixes.reset()


STEPS = r'''
import json, time
from ike import darkfixes, darklists

def steps(ike, qapp, out):
    calls = []
    lists = {"fixes": [{"url": ["*"], "css": ".common {}"}, {"url": ["fetched.test"], "css": ".fetched { color: red; }"}],
             "dark_sites": ["dark.fetched.test"], "detector_hints": []}

    def fake(bundled=None, opener=None):
        calls.append(len(bundled["fixes"]))
        if MODE == "fail":
            raise ValueError("no network here")
        return dict(lists, lists_date="2999-01-01", fetched=int(time.time()))
    darklists.fetch = fake
    ike.config["auto_update"] = AUTO
    ike.config["last_darklists_update"] = 0
    ike.check_updates()
    for _ in range(100):
        yield 50
        if getattr(ike, "_dark_lists", None) is None and (calls or not AUTO):
            break
    yield 200
    out["calls"] = calls
    out["last"] = ike.config["last_darklists_update"]
    out["now"] = int(time.time())
    out["stored"] = darklists.store_path().exists()
    out["fetched"] = bool(darkfixes.data().get("lists_fetched"))
    out["fix"] = darkfixes.fix_for("https://fetched.test/")["css"]
    # a second check the same day fetches nothing
    ike.check_updates()
    yield 300
    out["calls2"] = len(calls)
'''


@pytest.mark.parametrize("mode", ["ok", "fail", "off"])
def test_the_browser_fetches_them_once_a_day(run_ike, mode):
    from ike import darklists
    script = "MODE = %r\nAUTO = %r\n" % (mode, mode != "off") + STEPS
    out = run_ike(script, timeout=90, internal_errors=False)
    assert "error" not in out, out.get("error")
    if mode == "off":
        assert out["calls"] == [] and out["last"] == 0 and not out["stored"] and not out["fetched"], out
        return
    assert len(out["calls"]) == 1 and out["calls"][0] > 1000, out     # checked against the copy it came with
    assert out["calls2"] == 1, out                                      # once a day
    if mode == "ok":
        assert out["stored"] and out["fetched"], out
        assert out["fix"].endswith(".fetched { color: red; }"), out
        assert abs(out["last"] - out["now"]) < 30, out
    else:
        assert not out["stored"] and not out["fetched"], out
        # tried again in a few hours, not at every check and not a day later
        due = out["last"] + darklists.UPDATE_INTERVAL - out["now"]
        assert darklists.RETRY_FAILED_AFTER - 60 < due <= darklists.RETRY_FAILED_AFTER, out


def test_the_maintenance_makes_no_daily_version_for_lists_only(tmp_path, monkeypatch):
    """1.1.29: the lists are the whole component (its engine left); a change of them is an update the
    daily maintenance makes on Mondays only (tools/update-candidates.py WEEKLY), never every day."""
    import datetime as dt

    def load(name):
        spec = importlib.util.spec_from_file_location(name.replace("-", "_"), ROOT / "tools" / (name + ".py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    cc, uc = load("check-components"), load("update-candidates")
    cur = json.loads((ROOT / "ike/resources/darkreader-data.json").read_text("utf-8"))
    out = tmp_path / "out"
    out.mkdir()

    def built(new):
        (out / "darkreader-data.json").write_text(json.dumps(new), "utf-8")
        monkeypatch.setattr(cc, "build_darkreader", lambda root, work, dr_src=None: out)
        return cc.check_darkreader(ROOT, tmp_path)
    assert built(dict(cur))["update"] is False
    lists_only = built(dict(cur, dark_sites=cur["dark_sites"] + ["new.example"], lists_commit="f" * 40))
    assert lists_only["update"] is True and lists_only["note"] == "lists changed", lists_only
    report = {"candidates": [{"id": "darkreader", "from": lists_only["current"], "to": lists_only["latest"]}]}
    monday, friday = dt.date(2026, 11, 30), dt.date(2026, 12, 4)
    assert uc.plan(report, {}, today=friday)[0]["action"] == "weekly"
    assert uc.plan(report, {}, today=monday)[0]["action"] == "make"
