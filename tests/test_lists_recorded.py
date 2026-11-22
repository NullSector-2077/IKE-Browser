"""The filter lists' rules I.K.E. was taught to read (WP8, 2026-11-22).

An AI analysis of a filter-list finding (tools/filter-lists.py, autofix.yml on
automation/update/lists-<date>) may change only I.K.E.'s adapter
(ike/scriptlets.py, ike/blocker.py, ike-adblock/src/). The workflow, never the
AI, records the real rules of the finding in tests/data/lists-recorded/; this
test proves that I.K.E. now reads every one of them, and with its meaning:

- a scriptlet rule ("domain##+js(name, args)") runs on its domain with the
  same scriptlet (by name or one of its aliases) and the same arguments;
- any other rule, after I.K.E.'s own rewriting of the lists (ike/blocker.py
  sanitize), is read by the engine as one rule, with every option of the
  original still there: support never means dropping an option to make a rule
  parse (that would weaken blocking).

The automatic fix's guard refuses any change to this file and to tests/data/.
The checks themselves are proven first on recorded rules I.K.E. reads and on
rules it does not read (tests/data/filter-lists-classes.txt), so an empty
directory still tests something."""

import importlib.util
import re
import sys

import pytest
from conftest import APP, ROOT, needs_engine

RECORDED = ROOT / "tests" / "data" / "lists-recorded"
CLASSES = ROOT / "tests" / "data" / "filter-lists-classes.txt"


def _tool(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), ROOT / "tools" / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _ike():
    root = str(APP)
    if root not in sys.path:
        sys.path.insert(0, root)
    import ike.scriptlets as scr
    try:
        from ike import blocker
    except Exception:          # without Qt: the rules as they are
        blocker = None
    return scr, blocker


def _parse_report():
    check = _tool("check-components")
    mod, parse_report, why = check.engine_module(APP)
    if parse_report is None:
        pytest.skip("this engine has no parse_report: %s" % (why or "built before 1.1.20"))
    return parse_report


def reads(rule, scr, blocker, parse_report):
    """'' when I.K.E. reads the rule with its meaning, else why not."""
    lists = _tool("filter-lists")
    rule = rule.strip()
    if "+js(" in rule:
        m = scr._RULE.match(rule)
        if not m or m.group(2) or not m.group(1).strip():
            return "not a scriptlet rule of a domain"
        args = scr.split_args(m.group(3))
        lib = scr.Library()
        name = lib.resolve(args[0])
        if name is None:
            return "the scriptlet %s is unknown" % args[0]
        host = m.group(1).split(",")[0].strip().lstrip("~")
        host = host[:-2] + ".com" if host.endswith(".*") else host
        s = scr.Scriptlets()
        s.add_list(rule, True)
        run = [r for r in s.for_host(host) if r[0] == name]
        if run != [[name] + args[1:]]:
            return "not run on %s with its arguments: %r" % (host, run)
        if not any(s.scripts_for(host).values()):
            return "no script made for %s" % host
        return ""
    text = blocker.sanitize(rule) if blocker else rule
    if text.startswith("!"):
        return "I.K.E.'s rewriting drops it"
    for option in lists.options_of(rule):
        if option not in lists.options_of(text):
            return "the option %s is dropped" % option
    rep = parse_report(text, False, 3)
    if rep["network"] + rep["cosmetic"] != 1 or rep["unsupported"] + rep["errors"]:
        return "the engine does not read it: %s" % (rep["examples"][:1] or "?")
    return ""


def _rules(path):
    return [ln.strip() for ln in path.read_text("utf-8").splitlines() if ln.strip() and not ln.startswith("!")]


@needs_engine
def test_the_checks_tell_a_rule_read_from_one_dropped():
    """The proof's own proof, on recorded real rules (2026-11-22)."""
    scr, blocker = _ike()
    parse_report = _parse_report()
    rules = _rules(CLASSES)
    read = ["||example.com^$script,3p", "example.com##.ad-banner",
            next(r for r in rules if r.startswith("bild.de##+js(rpnt"))]
    dropped = [r for r in rules if re.search(r"removeparam=/|csp=|denyallow=|\$popup|urlskip=", r)
               and not r.startswith("@@")]
    dropped.append("example.com##+js(no-such-scriptlet, x)")
    for rule in read:
        assert reads(rule, scr, blocker, parse_report) == "", rule
    assert len(dropped) >= 5
    for rule in dropped:
        assert reads(rule, scr, blocker, parse_report), rule
    # supporting a rule by dropping its option is no support: an adapter that
    # rewrote the rule into a plain page block would be caught

    class Dropping:
        @staticmethod
        def sanitize(text):
            return re.sub(r",removeparam=[^,]*", "", text)
    why = reads("||reddit.com^$doc,removeparam=/web_only=/", scr, Dropping, parse_report)
    assert why == "the option removeparam is dropped", why


@needs_engine
def test_every_recorded_rule_is_read():
    scr, blocker = _ike()
    parse_report = _parse_report()
    files = sorted(RECORDED.glob("*.txt")) if RECORDED.is_dir() else []
    for path in files:
        rules = _rules(path)
        assert rules, "%s records no rule" % path.name
        for rule in rules:
            why = reads(rule, scr, blocker, parse_report)
            assert not why, "%s: %s: %s" % (path.name, rule, why)
