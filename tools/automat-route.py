#!/usr/bin/env python3
"""Which free model gets which task, and when an attempt is going in circles (AUTOMAT part 2; no AI here).

The free models are not equal: one reads files and holds a large context, others answer fast and
take short messages. Until now every attempt asked them in a fixed order, moved by one each attempt.

- **The kind of task** (task_type), read from the failure by code: ``rust`` (the engine's wrapper: a
  compiler error, a ``.rs`` file), ``multi-file`` (the failure names three or more of I.K.E.'s code
  files, or the tests fail for three or more different errors), ``builder`` (a re-anchoring),
  ``lists`` (the filter lists' analysis), ``manifest`` (a missing entry of components.json),
  ``page-script`` (one of I.K.E.'s page scripts), else ``python``. Hard ones (HARD) go to the
  strongest free model first, simple ones to the fast ones.
- **The order** (order): a starting order from tools/ai-quota.json ("routing": data, not code), then
  what AUTOMAT's memory has measured: once a provider has ``min_samples`` recorded attempts at a kind
  of task, its success rate there ((merged + 1) / (attempts + 2)) places it above or below the ones
  not measured yet. A provider that already failed this very error goes last; with no memory of the
  error, a later attempt starts one further down, so the same one never starts twice in a row.
- **Low temperature and a cap on the answer** (temperature, answer_tokens): data too; a simple task
  gets a smaller cap than the provider's own.
- **Going in circles** (Loop): the fingerprint of each patch (tools/automat-memory.py patch_hash) is
  compared with the ones this attempt already made and with the ones that failed before for this
  error. The same patch twice stops the attempt, and that is recorded: asking again would give it a
  third time.

    automat-route.py plan --failure FILE [--mode lists|builder] [--memory FILE --component ID]
                          [--attempt N] [--names A,B,C] [--limits FILE]
        prints task=..., hard=..., order=A,B,C and first=A
"""

import argparse
import importlib.util
import re
import sys
from pathlib import Path

HARD = ("rust", "multi-file", "builder")
NAMES = ("Antigravity", "Groq", "Z.AI", "OpenRouter")
RUST = re.compile(r"error\[E\d{4}\]|\bcargo (?:build|check|test)\b|-->\s*\S+\.rs:\d+|\S+\.rs:\d+:\d+|panicked at "
                  r"|ike-adblock/src/|\brustc\b", re.I)
CODE_FILE = re.compile(r"((?:ike|ike-adblock/src|vendor/adblock)/[\w./-]+\.(?:py|rs|js|json))")
PAGE_SCRIPT = re.compile(r"ike/resources/[\w.-]+\.js")
MANIFEST = re.compile(r"components\.json|test_inventory_guard", re.I)
MULTI = 3


def _tool(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), Path(__file__).resolve().parent /
                                                  (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def code_files(failure):
    """I.K.E.'s code files a failure names (not the tests), in the order they appear."""
    out = []
    for m in CODE_FILE.finditer(failure or ""):
        if m.group(1) not in out:
            out.append(m.group(1))
    return out


def task_type(failure, related=(), mode="", builder="", groups=None):
    """The kind of task a failure is (one of tools/automat-memory.py TASKS)."""
    if builder or mode == "builder":
        return "builder"
    if mode == "lists":
        return "lists"
    # the error itself, not the notes the plan adds after it
    failure = re.split(r"\n## (?:One problem per attempt|AUTOMAT's memory of this error|What changed upstream"
                       r"|The fix of this attempt's last round"
                       r"|Why earlier fixes were refused|Previous automatic fix)", failure or "")[0]
    files = [f for f in list(related or ()) + code_files(failure) if not f.startswith(("tests/", "tools/", "docs/"))]
    files = list(dict.fromkeys(files))
    if MANIFEST.search(failure) and not any(f.endswith((".py", ".rs")) for f in files if f != "components.json"):
        return "manifest"
    if RUST.search(failure) or any(f.endswith(".rs") for f in files):
        return "rust"
    if groups is None:
        try:
            groups = len(_tool("automat-memory").groups(failure))
        except Exception:
            groups = 0
    if len(files) >= MULTI or groups >= MULTI:
        return "multi-file"
    if files and all(PAGE_SCRIPT.fullmatch(f) for f in files):
        return "page-script"
    return "python"


def hard(task):
    return task in HARD


def routing(limits=None):
    data = (limits or {}).get("routing") if isinstance(limits, dict) else None
    data = data if isinstance(data, dict) else {}

    def names(key, default):
        value = data.get(key)
        return [n for n in value if n in NAMES] if isinstance(value, list) else list(default)
    tokens = data.get("answer_tokens") if isinstance(data.get("answer_tokens"), dict) else {}
    temp = data.get("temperature")
    samples = data.get("min_samples")
    return {"strong": names("strong", ("Antigravity", "OpenRouter", "Z.AI", "Groq")),
            "fast": names("fast", ("Groq", "Z.AI", "OpenRouter", "Antigravity")),
            "min_samples": samples if isinstance(samples, int) and not isinstance(samples, bool) and samples >= 1 else 3,
            "temperature": temp if isinstance(temp, (int, float)) and not isinstance(temp, bool) and 0 <= temp <= 0.3
            else 0.1,
            "simple": tokens.get("simple") if isinstance(tokens.get("simple"), int) and tokens.get("simple") >= 256
            else 2000,
            "hard": tokens.get("hard") if isinstance(tokens.get("hard"), int) and tokens.get("hard") >= 256 else 6000}


def order(task, names=NAMES, rates=None, limits=None, attempt=1, failed=()):
    """The providers of names in the order this task asks them.

    rates: {(provider, task): [merged, failed]} of AUTOMAT's memory; failed: the providers that already
    failed this very error; attempt: 1, 2, ... (with no memory of the error, attempt n starts one
    further down)."""
    conf = routing(limits)
    names = [n for n in names if n]
    prior = [n for n in conf["strong" if hard(task) else "fast"] if n in names]
    prior += [n for n in names if n not in prior]
    rates = rates or {}

    def score(name):
        merged, lost = (rates.get((name, task)) or [0, 0])[:2]
        if merged + lost < conf["min_samples"]:
            return 0.5                                   # not measured yet: between the good and the bad
        return (merged + 1.0) / (merged + lost + 2.0)
    ranked = sorted(prior, key=lambda n: (-score(n), prior.index(n)))
    failed = [n for n in ranked if n in set(failed or ())]
    if failed:
        return [n for n in ranked if n not in failed] + failed
    shift = (max(1, int(attempt or 1)) - 1) % len(ranked) if ranked else 0
    return ranked[shift:] + ranked[:shift]


def answer_tokens(task, cap, limits=None):
    """The cap on a model's answer for this kind of task: never above the provider's own."""
    conf = routing(limits)
    return max(256, min(int(cap), conf["hard" if hard(task) else "simple"]))


def temperature(limits=None):
    return routing(limits)["temperature"]


class Loop:
    """The patches of one attempt, by fingerprint. check(): "" for a new patch, "tried" for one that
    already failed for this error before (the model is told once), "twice" for the same patch a second
    time in this attempt or again after being told: the attempt stops there."""

    def __init__(self, tried=()):
        self.tried = {t for t in tried if t}
        self.seen = {}
        self.stopped = ""

    def check(self, fingerprint):
        if not fingerprint:
            return ""
        self.seen[fingerprint] = self.seen.get(fingerprint, 0) + 1
        if self.seen[fingerprint] >= 2:
            self.stopped = fingerprint
            return "twice"
        if fingerprint in self.tried:
            return "tried"
        return ""


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("cmd", choices=("plan",))
    ap.add_argument("--failure", required=True)
    ap.add_argument("--mode", default="")
    ap.add_argument("--memory")
    ap.add_argument("--component", default="")
    ap.add_argument("--attempt", default="1")
    ap.add_argument("--names", default=",".join(NAMES))
    ap.add_argument("--limits")
    a = ap.parse_args(argv)
    try:
        failure = Path(a.failure).read_text("utf-8", "replace")
    except OSError:
        failure = ""
    task = task_type(failure, mode=a.mode if a.mode in ("lists", "builder") else "")
    rates, failed = {}, set()
    mem = _tool("automat-memory")
    if a.memory:
        memory = mem.load(a.memory)
        rates = mem.rates(memory)
        failed = mem.failed_providers(memory, a.component, mem.signature(failure))
    limits = _tool("ai-quota").load_limits(a.limits)
    names = [n for n in a.names.split(",") if n in NAMES]
    ranked = order(task, names, rates, limits, int(a.attempt) if a.attempt.isdigit() else 1, failed)
    print("task=%s" % task)
    print("hard=%s" % ("true" if hard(task) else "false"))
    print("order=%s" % ",".join(ranked))
    print("first=%s" % (ranked[0] if ranked else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
