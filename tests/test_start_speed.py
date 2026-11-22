"""A faster start without less protection (1.1.22, docs/review/tests-and-performance.md,
"1.1.22, start and speed").

- The Public Suffix List's codes for fingerprint.js are kept next to the
  parsed list: the same codes, not worked out again at every start.
- The usual start (no option on the command line) does not load argparse;
  the error handler loads traceback only for an error; the engine's build
  thread is I.K.E.'s own: on Python 3.14 these three brought in logging,
  dataclasses and inspect before the window.
- A filter engine built from the lists reads and prepares each list once,
  finds the generichide exceptions and the scriptlet rules without trying
  every line, and splits most scriptlet arguments at once: the same engine,
  the same scriptlets, in less time.
"""

import json
import os
import random
import re
import subprocess
import sys
import threading
import time

from conftest import APP, needs_engine

sys.path.insert(0, str(APP))


# --- the Public Suffix List's codes ---------------------------------------

PSL_TEXT = "// test list\n" + "".join("x%d.test\nsite%d.co.test\n*.w%d.test\n!a.w%d.test\n" % (i, i, i, i)
                                      for i in range(700))


def _psl_setup(tmp_path, monkeypatch):
    from ike import config, shields
    psl = tmp_path / "psl.dat"
    psl.write_text(PSL_TEXT)
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(shields, "PSL_PATHS", [str(psl)])
    monkeypatch.setattr(shields, "_PSL", [])
    monkeypatch.setattr(shields, "_PSL_FILE", [])
    monkeypatch.setattr(shields, "_PSL_CODES", [])
    return shields, psl


def _fresh(shields, monkeypatch):
    """As a new start: nothing kept in memory, only the files."""
    monkeypatch.setattr(shields, "_PSL", [])
    monkeypatch.setattr(shields, "_PSL_FILE", [])
    monkeypatch.setattr(shields, "_PSL_CODES", [])


def test_psl_codes_are_kept_and_are_the_same(tmp_path, monkeypatch):
    """The codes fingerprint.js gets are those worked out from the list, at
    the first start and at the next ones; the next ones read them back
    instead of hashing every rule again (about 19 ms before the first page)."""
    shields, psl = _psl_setup(tmp_path, monkeypatch)
    first = shields.psl_codes()
    expected = shields._psl_codes_of(shields._psl())
    assert first == expected and len(first) % 4 == 0 and len(first) > 4000
    kept = list((tmp_path / "cache").glob("pslcodes-*.txt"))
    assert len(kept) == 1 and kept[0].read_text() == expected
    _fresh(shields, monkeypatch)
    calls = []
    real = shields.psl_code
    monkeypatch.setattr(shields, "psl_code", lambda r: calls.append(r) or real(r))
    assert shields.psl_codes() == expected
    assert calls == [], "the codes were worked out again"


def test_psl_codes_follow_a_new_list(tmp_path, monkeypatch):
    """A new list (pacman updates publicsuffix-list): new codes, the old copy
    removed. A damaged copy is worked out again, never handed to the pages."""
    shields, psl = _psl_setup(tmp_path, monkeypatch)
    old = shields.psl_codes()
    psl.write_text(PSL_TEXT + "added.example\n")
    st = os.stat(psl)
    os.utime(psl, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))
    _fresh(shields, monkeypatch)
    new = shields.psl_codes()
    assert new != old and new == shields._psl_codes_of(shields._psl())
    assert shields.psl_code("added.example") in [new[i:i + 4] for i in range(0, len(new), 4)]
    kept = list((tmp_path / "cache").glob("pslcodes-*.txt"))
    assert len(kept) == 1 and kept[0].read_text() == new
    for damaged in (new[:-1], new[:-4] + "!!!!", ""):
        kept[0].write_text(damaged)
        _fresh(shields, monkeypatch)
        assert shields.psl_codes() == new
        assert kept[0].read_text() == new


def test_psl_codes_without_the_system_list(tmp_path, monkeypatch):
    """Without the system's list nothing is kept and the page gets no codes,
    as before."""
    shields, psl = _psl_setup(tmp_path, monkeypatch)
    monkeypatch.setattr(shields, "PSL_PATHS", [str(tmp_path / "missing.dat")])
    assert shields.psl_codes() == ""
    assert not list(tmp_path.glob("**/pslcodes-*.txt"))


# --- the command line ------------------------------------------------------

def _argparse_answer(argv):
    """The command line as I.K.E. 1.1.21 read it."""
    import argparse

    from ike import APP_ID, APP_LONG_NAME
    parser = argparse.ArgumentParser(prog=APP_ID, description=APP_LONG_NAME)
    parser.add_argument("urls", nargs="*")
    parser.add_argument("--private", action="store_true")
    parser.add_argument("--profile", default="")
    args, unknown = parser.parse_known_args(argv)
    return vars(args), unknown


def test_the_command_line_reads_as_before():
    from ike.app import parse_args
    for argv in ([], ["https://example.org/"], ["a b", "", "file.html", "ike:newtab", "mailto:x@y.test"],
                 ["--private"], ["--private", "https://a.test/"], ["--profile", "work", "u"],
                 ["--profile=work"], ["-x", "u"], ["--", "-u"], ["u", "--private"], ["--priv"]):
        args, unknown = parse_args(list(argv))
        assert ({"urls": args.urls, "private": args.private, "profile": args.profile}, unknown) \
            == _argparse_answer(list(argv)), argv


def test_the_usual_start_does_not_load_argparse():
    code = ("import sys; sys.path.insert(0, %r); from ike.app import parse_args; "
            "parse_args(['https://example.org/']); print('argparse' in sys.modules)" % str(APP))
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         env=dict(os.environ, QT_QPA_PLATFORM="offscreen"), timeout=60)
    assert out.stdout.strip() == "False", out.stderr[-2000:]


HOOK_MODULES = r'''
import json, os, sys
from PyQt6.QtCore import QTimer
heavy = ("argparse", "traceback", "logging", "concurrent.futures", "dataclasses", "inspect")
out = {"loaded": [m for m in heavy if m in sys.modules],
       "engine": ike.blocker.engine is not None or ike.blocker.fallback is not None,
       "thread": [t.name for t in __import__("threading").enumerate() if t.name.startswith("ike-adblock")]}
with open(os.environ["IKE_TEST_OUT"], "w") as f:
    json.dump(out, f)
for w in list(ike.windows):
    w.close()
QTimer.singleShot(50, qapp.quit)
'''


def test_the_start_loads_no_module_it_does_not_need(run_ike, tmp_path):
    """Up to the first window: none of the modules that cost about 15 ms on
    Python 3.14 without being needed then; the filter engine is ready and
    was built in its own thread."""
    hook = tmp_path / "hook_modules.py"
    hook.write_text(HOOK_MODULES)
    out = run_ike("", env={"IKE_TEST_HOOK": str(hook)})
    assert out["loaded"] == [], out
    assert out["engine"] is True and out["thread"] == ["ike-adblock"], out


# --- the build thread ------------------------------------------------------

def test_the_build_thread_runs_every_build_and_hands_back_results():
    from ike.blocker import _BuildThread
    pool = _BuildThread()
    names = []
    jobs = [pool.submit(lambda n: names.append(threading.current_thread().ident) or n * 2, n) for n in range(5)]
    assert [j.result() for j in jobs] == [0, 2, 4, 6, 8]
    assert len(set(names)) == 1 and names[0] != threading.get_ident()   # one thread, kept, not this one
    failing = pool.submit(lambda: {}["missing"])
    try:
        failing.result()
        raise AssertionError("the error was lost")
    except KeyError:
        pass
    assert pool.submit(lambda: "still serving").result() == "still serving"
    slow = pool.submit(lambda: time.sleep(0.4) or "done")
    a = time.perf_counter()
    pool.close()                                  # waits for the build that is running
    assert time.perf_counter() - a > 0.2 and slow.result() == "done"


@needs_engine
def test_a_build_running_at_exit_finishes_first(run_ike, tmp_path):
    """As with the thread pool until 1.1.21: closing I.K.E. while a new engine
    is being built (a list update) lets it finish and write its cache."""
    marker = tmp_path / "built.txt"
    run_ike(r'''
def steps(ike, qapp, out):
    import time
    b = ike.blocker
    yield 300
    real = b._build
    def slow(snap, sig):
        time.sleep(1.0)
        r = real(snap, sig)
        open(%r, "w").write("finished")
        return r
    b._build = slow
    ike.config["custom_filters"] = "||exit-build.example^"
    b.load()
    out["building"] = b.building
''' % str(marker), timeout=90)
    assert marker.exists() and marker.read_text() == "finished"


# --- the filter lists ------------------------------------------------------

_OLD_GHIDE = re.compile(r"^@@.*\$.*\b(?:ghide|generichide)\b.*$", re.M)


def _old_sanitize(text):
    def fix(m):
        line = m.group(0)
        if "domain=" not in line or "~" not in line:
            return line
        head, _, tail = line.partition("domain=")
        doms, sep, rest = tail.partition(",")
        kept = [d for d in doms.split("|") if d and not d.startswith("~")]
        if not kept:
            return "! " + line
        return head + "domain=" + "|".join(kept) + sep + rest
    return _OLD_GHIDE.sub(fix, text)


GHIDE_LINES = [
    "@@||a.test^$generichide,domain=a.test|~b.test",
    "@@||a.test^$ghide,domain=~b.test",
    "@@||a.test^$ghide,domain=c.test",
    "@@||a.test^$generichide",
    "x@@||a.test^$ghide,domain=a.test|~b.test",
    "  @@||a.test^$ghide,domain=a.test|~b.test",
    "@@||a.test^$domain=a.test|~b.test,generichide",
    "@@||a.test^$domain=a.test|~b.test,ghide,image",
    "@@ $ghide domain=~x @@||b.test^$ghide,domain=d.test|~e.test",
    "||ads.test^$ghide,domain=a.test|~b.test",
    "@@||a.test^$xghide,domain=a.test|~b.test",
    "@@||a.test^$ghidex,domain=a.test|~b.test",
    "@@||a.test^$generichide,domain=a.test|~b.test\r",
    "@@||a.test^ $ghide,domain=a.test|~b.test",
    "example.com##.ad",
    "",
]


def test_sanitize_changes_the_same_lines_as_before():
    from ike.blocker import sanitize
    rnd = random.Random(1122)
    for _ in range(300):
        lines = [rnd.choice(GHIDE_LINES) for _ in range(rnd.randint(1, 12))]
        text = rnd.choice(["\n", "\r\n"]).join(lines) + rnd.choice(["", "\n"])
        assert sanitize(text) == _old_sanitize(text), text
    assert sanitize("@@||a.test^$ghide,domain=a.test|~b.test") == "@@||a.test^$ghide,domain=a.test"


def test_sanitize_takes_less_time_than_before():
    """A list's worth of rules (40,000 lines; as in EasyList, about one in
    twenty an exception): the search goes from one "@@" to the next."""
    from ike.blocker import sanitize
    rnd = random.Random(7)
    text = "\n".join(rnd.choice(["||ads%d.test^$third-party" % i, "example%d.test##.banner" % i] * 19
                                + ["@@||cdn%d.test^$script,domain=s%d.test" % (i, i),
                                   "@@||x%d.test^$generichide,domain=a.test|~b.test" % i])
                     for i in range(40000))

    def best(fn):
        times = []
        for _ in range(5):
            a = time.perf_counter()
            fn(text)
            times.append(time.perf_counter() - a)
        return min(times)
    assert sanitize(text) == _old_sanitize(text)
    assert best(sanitize) < best(_old_sanitize) * 0.6, (best(sanitize), best(_old_sanitize))


def _old_split_args(raw):
    """scriptlets.split_args of 1.1.21."""
    args, cur, i, n = [], "", 0, len(raw)
    while i < n and raw[i] == " ":
        i += 1
    while i <= n:
        if i == n:
            args.append(cur.strip())
            break
        ch = raw[i]
        if not cur.strip() and ch in "'\"`":
            j = i + 1
            buf = ""
            while j < n and raw[j] != ch:
                if raw[j] == "\\" and j + 1 < n and raw[j + 1] == ch:
                    j += 1
                buf += raw[j]
                j += 1
            k = j + 1
            while k < n and raw[k] == " ":
                k += 1
            if j < n and (k == n or raw[k] == ","):
                args.append(buf)
                cur = ""
                i = k + 1
                if k == n:
                    break
                continue
        if ch == "\\" and i + 1 < n and raw[i + 1] == ",":
            cur += ","
            i += 2
            continue
        if ch == ",":
            args.append(cur.strip())
            cur = ""
            i += 1
            continue
        cur += ch
        i += 1
    return args


def test_scriptlet_arguments_split_as_before():
    from ike.scriptlets import split_args
    rnd = random.Random(22)
    alphabet = ["a", "b", "1", ",", " ", "'", '"', "`", "\\", "\t", " ", "　", ".", "-", "$"]
    for _ in range(20000):
        raw = "".join(rnd.choice(alphabet) for _ in range(rnd.randint(0, 14)))
        assert split_args(raw) == _old_split_args(raw), repr(raw)
    for raw in ("set-constant, ads, false", "trusted-set-cookie, a, '1, 2', , ", "x\\, y, z",
                "'unclosed, b", "  'q', r"):
        assert split_args(raw) == _old_split_args(raw), raw


def _old_add_list(s, text, trusted):
    """Scriptlets.add_list of 1.1.21: every line split and tried."""
    from ike import scriptlets
    lib = scriptlets.LIBRARY
    for line in scriptlets.preprocess(text).splitlines():
        if "+js(" not in line:
            continue
        m = scriptlets._RULE.match(line.strip())
        if not m:
            continue
        domains = m.group(1).strip()
        args = _old_split_args(m.group(3))
        if m.group(2):
            name = (lib.resolve(args[0]) or args[0]) if args and args[0] else ""
            targets = [d.strip().lower() for d in domains.split(",") if d.strip()] or ["*"]
            for d in targets:
                s.exceptions.setdefault(d, set()).add(name)
            continue
        if not domains:
            continue
        name = lib.resolve(args[0]) if args else None
        if name is None:
            continue
        if lib.entry(name).get("trust") and not trusted:
            continue
        rule = [name] + args[1:]
        key = json.dumps(rule)
        for d in m.group(1).split(","):
            d = d.strip().lower()
            if not d:
                continue
            if d.startswith("~"):
                s.negated.setdefault(d[1:], set()).add(key)
            else:
                rules = s.by_domain.setdefault(d, [])
                if rule not in rules:
                    rules.append(rule)


SCRIPTLET_LINES = [
    "example.com##+js(set-constant, ads, false)",
    "a.test,~b.test##+js(abort-on-property-read, ads)",
    "example.com#@#+js(set-constant)",
    "#@#+js()",
    "##+js(nowebrtc)",
    "c.test##+js(trusted-set-cookie, a, '1, 2')",
    "d.test##+js(no-setTimeout-if, '\\'x\\'', 100)",
    "e.test##+js(remove-attr, class, 'a b')  ",
    "example.com##.ad",
    "||ads.test^",
    "!#if env_firefox",
    "f.test##+js(set-constant, firefox, true)",
    "!#else",
    "g.test##+js(set-constant, chromium, true)",
    "!#endif",
    "h.test##+js(set-constant, x, 1) i.test##+js(set-constant, y, 2)",
    "",
]


def test_scriptlet_rules_are_read_as_before():
    """The same index from any text: only the lines with "+js(" are split,
    with every line separator Python knows."""
    from ike import scriptlets
    rnd = random.Random(1)
    for _ in range(300):
        lines = [rnd.choice(SCRIPTLET_LINES) for _ in range(rnd.randint(1, 20))]
        text = ""
        for line in lines:
            text += line + rnd.choice(["\n", "\n", "\r\n", "\r", "\x0c", "\x85", " ", "\x1e"])
        if rnd.random() < 0.5:
            text = text.rstrip("\n")
        for trusted in (False, True):
            new, old = scriptlets.Scriptlets(), scriptlets.Scriptlets()
            new.add_list(text, trusted)
            _old_add_list(old, text, trusted)
            assert new.dump() == old.dump(), repr(text)


@needs_engine
def test_a_build_reads_each_list_once_and_gives_the_same_engine(tmp_path, monkeypatch):
    """The engine and the scriptlets of a build from the lists: each list read
    once and its "!#if" branches chosen once (twice each until 1.1.21), and
    the same engine bytes and scriptlets as the lists prepared one by one."""
    import pathlib

    from test_performance import _vendor

    from ike import blocker, config, scriptlets
    monkeypatch.setattr(blocker, "adblock", _vendor())
    monkeypatch.setattr(blocker, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(blocker, "LISTS_DIR", tmp_path / "lists")
    (tmp_path / "cache").mkdir()
    (tmp_path / "lists").mkdir()
    lists = {
        "https://ublockorigin.github.io/uAssets/filters/filters.txt":
            "||ads.test^\n!#if env_firefox\nf.test##+js(set-constant, ff, 1)\n!#else\n"
            "g.test##+js(set-constant, cr, 1)\n!#endif\n@@||x.test^$ghide,domain=a.test|~b.test\n",
        "https://easylist.to/easylist/easylist.txt": "||tracker.test^\nexample.com##.ad\n",
        "https://secure.fanboy.co.nz/fanboy-cookiemonster.txt": "cookie.test##+js(set-constant, c, 1)\n",
    }
    for url, text in lists.items():
        blocker.list_path(url).write_text(text, "utf-8")
    cfg = config.Config(tmp_path / "settings.json")
    cfg.data["filter_lists"] = [{"name": u, "url": u, "enabled": True,
                                 "group": "consent" if "fanboy" in u else "ads"} for u in lists]
    b = blocker.Blocker(cfg)
    reads, chosen = [], []
    real_read, real_pp = pathlib.Path.read_text, scriptlets.preprocess

    def read(self, *a, **k):
        if self.parent == tmp_path / "lists":
            reads.append(self.name)
        return real_read(self, *a, **k)

    def pp(text):
        if "!#if" in text:
            chosen.append(1)                     # real work: the branches chosen
        return real_pp(text)
    monkeypatch.setattr(pathlib.Path, "read_text", read)
    monkeypatch.setattr(blocker, "preprocess", pp)
    monkeypatch.setattr(scriptlets, "preprocess", pp)
    engine, fallback, sc = b._build(b._snapshot(), b._signature())
    monkeypatch.undo()
    assert sorted(reads) == sorted(blocker.list_path(u).name for u in lists), reads
    assert chosen == [1], chosen                 # one list has "!#if" branches: chosen once
    ref = scriptlets.Scriptlets()
    for url, text in lists.items():
        if "fanboy" not in url:
            ref.add_list(text, blocker._trusted_scriptlet_source(url))
    assert sc.dump() == ref.dump()
    assert sc.for_host("g.test") and not sc.for_host("f.test")
    adblock = _vendor()
    fs = adblock.FilterSet()
    for text in [blocker.sanitize(real_pp(t)) for t in lists.values()] + [blocker.BUILTIN_RULES]:
        fs.add_filter_list(text)
    want = adblock.Engine(fs)
    blocker._install_redirect_resources(want)
    assert engine.check_network_urls("https://ads.test/a.js", "https://site.test/", "script").matched
    assert engine.check_network_urls("https://tracker.test/a.js", "https://site.test/", "script").matched
    a, b2 = tmp_path / "a.dat", tmp_path / "b.dat"
    engine.serialize_to_file(str(a))
    want.serialize_to_file(str(b2))
    assert a.read_bytes() == b2.read_bytes()


def test_scriptlet_index_takes_less_time_than_before():
    """The index of a list's worth of rules (40,000 lines, 2,000 scriptlets)."""
    from ike import scriptlets
    rnd = random.Random(3)
    lines = []
    for i in range(40000):
        if i % 20 == 0:
            lines.append("s%d.test,t%d.test##+js(set-constant, v%d, %s)" % (i, i, i, rnd.choice(["false", "'1'"])))
        else:
            lines.append(rnd.choice(["||ads%d.test^" % i, "example%d.test##.banner" % i]))
    text = "\n".join(lines)

    def best(fn):
        times = []
        for _ in range(3):
            a = time.perf_counter()
            fn(scriptlets.Scriptlets(), text, True)
            times.append(time.perf_counter() - a)
        return min(times)
    new, old = scriptlets.Scriptlets(), scriptlets.Scriptlets()
    new.add_list(text, True)
    _old_add_list(old, text, True)
    assert new.dump() == old.dump()
    assert best(lambda s, t, tr: s.add_list(t, tr)) < best(_old_add_list) * 0.8

