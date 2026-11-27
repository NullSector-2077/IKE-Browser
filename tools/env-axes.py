#!/usr/bin/env python3
"""The configurations of users' computers that "Nothing gets worse" measures, in one place (2026-11-25).

The probe (tools/no-regression.py) measures I.K.E.'s page scripts in a matrix of these configurations, and
the static guard (tools/fix-guard.py) lets new page-script code branch on exactly what the matrix covers: an
axis added here is measured by the probe and allowed in the guard's conditions at once, and nothing else is.

Round 6 of the review of "Nothing gets worse": two added lines re-wrapped the real processor count for every
screen whose devicePixelRatio is not 1, and every session of the measurement had devicePixelRatio 1. A
condition is safe when every value it can see is measured; so the common configurations of Linux desktops
are covered up front, in pairs (every pair of two axes' values appears in at least one session), with a few
corners (every axis at its first value, every axis at its last) at each level, and a seed per run so different
runs meet different triples.

Sources and assumptions (the values are the common ones of desktops and laptops that run Linux, as the
public statistics of desktop screens, browsers and the Steam hardware survey show them in 2025-2026, and as
desktop environments offer them): screens 1366x768 and 1920x1080 lead, 1536x864 is 1920x1080 at 125 %, then
2560x1440, 3840x2160, the ultrawide 3440x1440 and the small 1280x720; scale 1, 1.25, 1.5 and 2 (GNOME and KDE
offer these; fractional scaling is common on laptops); page zoom 90 % to 150 % (the browser's own steps);
touch screens on some laptops; dark colours, reduced motion and forced colours (high contrast) are
accessibility settings of every desktop; languages and time zones of I.K.E.'s users (Italian, German,
Japanese, English); processors 2 to 32 and memory 4 to 32 GB. What the engine cannot be given here is said
in NOT_COVERED (and stays refused in the guard's conditions).

    env-axes.py [SEED]      prints the sessions of a run's matrix
"""

import itertools
import json
import random
import re
import sys

# name, values, how the probe gives it (the engine's DevTools emulation per page, the browser's zoom, I.K.E.'s
# settings, the small library that answers for the machine), and what a page reads of it
AXES = (
    ("scale", (1, 1.25, 1.5, 2)),
    ("zoom", (0.9, 1, 1.1, 1.25, 1.5)),
    ("screen", ((1280, 720), (1366, 768), (1536, 864), (1920, 1080), (2560, 1440), (3440, 1440), (3840, 2160))),
    ("touch", (False, True)),
    ("scheme", ("light", "dark")),
    ("motion", ("no-preference", "reduce")),
    ("contrast", ("none", "forced")),
    ("language", ("en-US", "it-IT", "de-DE", "ja-JP")),
    ("timezone", ("UTC", "Europe/Rome", "America/New_York", "Asia/Tokyo")),
    ("cores", (2, 4, 8, 12, 16, 32)),
    ("memory", (4, 8, 16, 32)),
    ("level", ("compatibility", "balanced", "strict", "maximum")),
)
# the browser's own window around the page (a toolbar, tabs): the page's height is the screen's less this
CHROME_HEIGHT = 110

# What a page reads of these axes (the static guard: a new condition may read them, and nothing else of the
# page's environment). Globals and properties, as tools/fix-guard.py _env_key names them ("name" or
# "name.member"); matchMedia only with a literal query of COVERED_MEDIA's features.
COVERED_READS = frozenset("""
devicePixelRatio innerWidth innerHeight outerWidth outerHeight visualViewport
screen screen.width screen.height screen.availWidth screen.availHeight screen.orientation orientation
matchMedia maxTouchPoints navigator.maxTouchPoints ontouchstart
language languages navigator.language navigator.languages
hardwareConcurrency navigator.hardwareConcurrency deviceMemory navigator.deviceMemory
Intl Intl.DateTimeFormat resolvedOptions timeZone
""".split())
COVERED_MEDIA = frozenset("""
pointer any-pointer hover any-hover prefers-color-scheme prefers-reduced-motion forced-colors prefers-contrast
resolution min-resolution max-resolution -webkit-device-pixel-ratio -webkit-min-device-pixel-ratio
-webkit-max-device-pixel-ratio width min-width max-width height min-height max-height orientation
aspect-ratio min-aspect-ratio max-aspect-ratio device-width min-device-width max-device-width device-height
min-device-height max-device-height
""".split())
# the protection's own state whose every value is measured (the levels are an axis): fingerprint.js's names
PROTECTION_STATE = frozenset(("lv", "strict", "maximum"))
# what the engine cannot be given on GitHub's runners (said in the report and in docs/MAINTENANCE.md)
NOT_COVERED = (
    "the graphics card's names: WebGL runs on the engine's software renderer, whose vendor and renderer "
    "texts no switch changes",
    "X11 against Wayland: the runners have no display server; the engine runs offscreen",
)


def _pairs(axes):
    return {((i, a), (j, b)) for (i, (_, va)), (j, (_, vb)) in itertools.combinations(enumerate(axes), 2)
            for a in range(len(va)) for b in range(len(vb))}


# round 7 (Fable's third review): the values between and beyond the grid. A condition compared with a value no
# session has (a screen 1600 wide, 6 processors, Europe/Berlin) was never true in the measurement. So the
# probe adds sessions at the values a change's own conditions compare with (and beside them: derive), and a
# few sessions of the run at random real-world values off the grid (FUZZ, drawn from the run's seed)
FUZZ_SESSIONS = 8
FUZZ = {"width": (1024, 5120), "scale": (1.0, 3.0, 0.05), "zoom": (0.5, 2.0, 0.05), "cores": (1, 64),
        "memory": (2, 64)}
MAX_DERIVED = 24              # the values a change may compare with: beyond them the run is not verified
# what a page reads -> the axis that gives it (tools/fix-guard.py _env_key names)
READ_AXIS = {
    "hardwareConcurrency": "cores", "navigator.hardwareConcurrency": "cores",
    "deviceMemory": "memory", "navigator.deviceMemory": "memory",
    "screen.width": "screen-width", "screen.availWidth": "screen-width", "outerWidth": "screen-width",
    "screen.height": "screen-height", "screen.availHeight": "screen-height", "outerHeight": "screen-height",
    "innerWidth": "viewport-width", "innerHeight": "viewport-height", "visualViewport": "viewport-width",
    "devicePixelRatio": "dpr", "timeZone": "timezone", "resolvedOptions": "timezone",
    "Intl.DateTimeFormat": "timezone",
    "language": "language", "navigator.language": "language",
}
# round 9 (Fable's review of round 8): the grid's two-valued axes a change reads, met with its other values in
# the joint sessions (a desktop with no touch screen and 1920, 4 cores, 8 GB was in no session)
MEDIA_AXIS = {"pointer": "touch", "any-pointer": "touch", "hover": "touch", "any-hover": "touch",
              "prefers-color-scheme": "scheme", "prefers-reduced-motion": "motion", "forced-colors": "contrast"}
BOOLEAN_KINDS = {"touch": (False, True), "scheme": ("light", "dark"), "motion": ("no-preference", "reduce"),
                 "contrast": ("none", "forced")}
MEDIA_NUMBER = re.compile(r"\(\s*(min-|max-)?(-webkit-(?:min-|max-)?device-pixel-ratio|width|height|device-width|"
                          r"device-height|resolution)\s*:\s*([0-9.]+)\s*(px|dppx|x|dpi|dpcm)?\s*\)")


def derive(literals):
    """The configurations a change's conditions name ([{"read", "op", "value"} | {"media"}] from
    tools/fix-guard.py axis_literals): {kind: sorted values}, each number with the values beside it (a
    threshold is then measured on both sides), each text as it is."""
    out, raw = {}, {}

    def add(kind, values):
        out.setdefault(kind, set()).update(values)
    for item in literals or ():
        if item.get("axis") in BOOLEAN_KINDS:
            add(item["axis"], set(BOOLEAN_KINDS[item["axis"]]))
            continue
        if "media" in item:
            for g in MEDIA_GROUP.findall(str(item["media"])):
                feat = g.partition(":")[0].strip().lower()
                if feat in MEDIA_AXIS:
                    add(MEDIA_AXIS[feat], set(BOOLEAN_KINDS[MEDIA_AXIS[feat]]))
            for m in MEDIA_NUMBER.finditer(str(item["media"])):
                try:
                    feat, v, unit = m.group(2), float(m.group(3)), m.group(4) or ""
                except ValueError:
                    continue
                if "pixel-ratio" in feat or feat == "resolution":
                    v = v / 96 if unit == "dpi" else v * 2.54 / 96 if unit == "dpcm" else v
                    add("dpr", _beside(v, 0.05))
                    raw.setdefault("dpr", []).append(round(v, 3))
                elif feat in ("width", "height"):
                    add("viewport-" + feat, _beside(v, 1))
                    raw.setdefault("viewport-" + feat, []).append(v)
                else:
                    add("screen-" + feat.split("-")[1], _beside(v, 1))
                    raw.setdefault("screen-" + feat.split("-")[1], []).append(v)
            continue
        kind, v = READ_AXIS.get(item.get("read")), item.get("value")
        if kind is None:
            continue
        if kind in ("timezone", "language"):
            if isinstance(v, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_+/-]{1,40}", v):
                add(kind, {v})
            continue
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            continue
        add(kind, _beside(v, 0.05 if kind == "dpr" else 1))
        raw.setdefault(kind, []).append(v)
    # round 9: between two values a change compares one kind with, a value inside (1.01 < dpr < 1.04 was
    # true in no session)
    for kind, nums in raw.items():
        nums = sorted(set(nums))
        for a, b in zip(nums, nums[1:]):
            mid = round((a + b) / 2, 3) if kind == "dpr" else int((a + b) // 2)
            if a < mid < b:
                out[kind].add(mid)
    return {k: sorted(v, key=str) for k, v in out.items()}


# round 8 (Fable's fourth review): what a media query the probe can make true and false. A number of
# MEDIA_NUMBER is derived (its value and beside it); the features below have every value in the grid (the
# touch axis gives pointer and hover, the scheme, motion and contrast axes the rest). Anything else
# (aspect-ratio, orientation, em units, prefers-contrast...) no session sets: the guard refuses it
MEDIA_BOOLEAN = {"pointer": ("fine", "coarse"), "any-pointer": ("fine", "coarse"), "hover": ("hover", "none"),
                 "any-hover": ("hover", "none"), "prefers-color-scheme": ("light", "dark"),
                 "prefers-reduced-motion": ("no-preference", "reduce"), "forced-colors": ("none", "active")}
MEDIA_GROUP = re.compile(r"\(([^()]*)\)")


def media_measured(query):
    """True when every feature of a literal media query is one the matrix sets on both sides (round 8)."""
    q = str(query or "")
    groups = MEDIA_GROUP.findall(q)
    if not groups or MEDIA_GROUP.sub("", q).strip(" ,").lower().replace("and", "").replace("not", "").replace(
            "only", "").replace("screen", "").replace("all", "").strip(" ,"):
        return False
    for g in groups:
        m = MEDIA_NUMBER.fullmatch("(" + g + ")")
        if m:
            # round 10 (Fable's review of round 9): the precision the sessions set (3 decimals of a ratio,
            # whole pixels), as read_measured asks of a read; round 11: a ratio in dpi or dpcm too
            try:
                v = float(m.group(3))
            except ValueError:
                return False
            unit = m.group(4) or ""
            if "pixel-ratio" in m.group(2) or m.group(2) == "resolution":
                r = v / 96 if unit == "dpi" else v * 2.54 / 96 if unit == "dpcm" else v
                if round(r, 3) != r:
                    return False
            elif v != int(v):
                return False
            continue
        feat, _, val = g.partition(":")
        feat, val = feat.strip().lower(), val.strip().lower()
        if feat not in MEDIA_BOOLEAN or (val and val not in MEDIA_BOOLEAN[feat]):
            return False
    return True


OPS = {"===": lambda a, b: a == b, "==": lambda a, b: a == b, "!==": lambda a, b: a != b,
       "!=": lambda a, b: a != b, "<": lambda a, b: a < b, "<=": lambda a, b: a <= b, ">": lambda a, b: a > b,
       ">=": lambda a, b: a >= b}


def read_measured(read, op, value):
    """True when a comparison of a covered read with a literal is one the probe makes true and false (round 8,
    Fable's fourth review: a text derive cannot set, such as 'pt_BR.UTF-8', was accepted and never measured;
    round 9: the values the sessions really get, rounded and floored, and the literal's own type)."""
    kind = READ_AXIS.get(read)
    if kind is None or op not in OPS:
        return False
    if kind in ("timezone", "language"):
        if not isinstance(value, str) or op not in ("===", "==", "!==", "!="):
            return False
    elif isinstance(value, bool) or not isinstance(value, (int, float)) or \
            (kind == "dpr" and round(value, 3) != value) or (kind != "dpr" and value != int(value)):
        return False
    got = [_session_value(kind, v) for v in derive([{"read": read, "op": op, "value": value}]).get(kind, [])]
    try:
        results = {bool(OPS[op](g, value)) for g in got}
    except TypeError:
        return False
    return results == {True, False} or (kind in ("timezone", "language") and True in results)


def _session_value(kind, v):
    """What a session derived at v makes the page read (the floors of _derived_rows)."""
    if kind == "memory":
        return max(1, int(v))
    if kind in ("cores",) or kind.startswith("screen-") or kind.startswith("viewport-"):
        return int(v)
    return v


def _beside(v, step):
    if step == 1:
        return {int(round(x)) for x in (v - 1, v, v + 1) if x >= 1}
    return {round(x, 3) for x in (v - step, v, v + step) if x >= 0.5}


def _derived_rows(derived, axes, levels):
    """The sessions of a change's own values: each at every level, the other axes at their last (largest)
    values, the zoom and scale at 1 where the value is a size (so the page reads exactly that value)."""
    last = {n: v[-1] for n, v in axes}
    rows = []
    for kind, values in sorted(derived.items()):
        for v in values:
            for level in levels:
                s = dict(last, level=level, zoom=1, scale=1)
                if kind == "cores":
                    s["cores"] = int(v)
                elif kind == "memory":
                    s["memory"] = max(1, int(v))
                elif kind == "dpr":
                    s["scale"] = float(v)
                elif kind == "timezone":
                    s["timezone"] = v
                elif kind == "language":
                    s["language"] = v
                elif kind in BOOLEAN_KINDS:
                    s[kind] = v
                elif kind == "screen-width":
                    s["screen"] = (int(v), max(480, int(round(v * 9 / 16))))
                elif kind == "screen-height":
                    s["screen"] = (max(640, int(round(v * 16 / 9))), int(v))
                elif kind == "viewport-width":
                    s["screen"] = (int(v), max(480, int(round(v * 9 / 16))))
                elif kind == "viewport-height":
                    s["screen"] = (max(640, int(round((v + CHROME_HEIGHT) * 16 / 9))), int(v) + CHROME_HEIGHT)
                s["derived"] = "%s %s" % (kind, v)
                rows.append(s)
    return rows


JOINT_SLOTS = ("width", "height", "cores", "memory", "dpr", "timezone", "language", "touch", "scheme", "motion",
               "contrast")
MAX_JOINT = 128               # the joint sessions a run measures: beyond them the run is not verified


def _joint_values(derived):
    """A change's own values by what a session sets (round 8): the screen's width and height (a window's size
    at zoom 1 is the screen's, less the browser's own window in height), cores, memory, scale, zone, language."""
    slots = {}
    for kind, values in derived.items():
        for v in values:
            if kind in ("screen-width", "viewport-width"):
                slots.setdefault("width", set()).add(int(v))
            elif kind == "screen-height":
                slots.setdefault("height", set()).add(int(v))
            elif kind == "viewport-height":
                slots.setdefault("height", set()).add(int(v) + CHROME_HEIGHT)
            else:
                slots.setdefault(kind, set()).add(v)
    return {k: sorted(slots[k], key=str) for k in JOINT_SLOTS if k in slots}


def _joint_count(derived, levels=4):
    slots = _joint_values(derived)
    if len(slots) < 2:
        return 0
    n = 1
    for v in slots.values():
        n *= len(v)
    return n * levels


def _joint_rows(derived, axes, levels):
    """Round 8 (Fable's fourth review): a condition joining three of a change's own values (a width, a number
    of cores and an amount of memory) was true in no session: the pairs meet two values, never three. So
    every combination of the change's own values, one of each kind, at every level (MAX_JOINT at most)."""
    slots = _joint_values(derived)
    if len(slots) < 2:
        return []
    last = {n: v[-1] for n, v in axes}
    names = list(slots)
    rows = []
    for combo in itertools.product(*(slots[n] for n in names)):
        got = dict(zip(names, combo))
        for level in levels:
            s = dict(last, level=level, zoom=1, scale=1)
            w, h = got.get("width"), got.get("height")
            if w is not None or h is not None:
                if w is None:
                    w = max(640, int(round(h * 16 / 9)))
                if h is None:
                    h = max(480, int(round(w * 9 / 16)))
                s["screen"] = (int(w), int(h))
            if "cores" in got:
                s["cores"] = int(got["cores"])
            if "memory" in got:
                s["memory"] = max(1, int(got["memory"]))
            if "dpr" in got:
                s["scale"] = float(got["dpr"])
            for k in ("timezone", "language", "touch", "scheme", "motion", "contrast"):
                if k in got:
                    s[k] = got[k]
            s["derived"] = "joint " + ", ".join("%s %s" % (n, got[n]) for n in names)
            rows.append(s)
    return rows


def _fuzz_rows(rng, axes, n):
    """A few sessions at random real-world values off the grid (FUZZ), the run's own."""
    levels = list(dict(axes)["level"])
    rows = []
    for i in range(n):
        s = {name: rng.choice(list(values)) for name, values in axes}
        w = rng.randint(*FUZZ["width"])
        s["screen"] = (w, max(480, int(w * rng.uniform(0.4, 0.8))))
        lo, hi, step = FUZZ["scale"]
        s["scale"] = round(lo + step * rng.randint(0, int(round((hi - lo) / step))), 2)
        lo, hi, step = FUZZ["zoom"]
        s["zoom"] = round(lo + step * rng.randint(0, int(round((hi - lo) / step))), 2)
        s["cores"] = rng.randint(*FUZZ["cores"])
        s["memory"] = rng.randint(*FUZZ["memory"])
        s["level"] = levels[i % len(levels)]
        s["fuzz"] = True
        rows.append(s)
    return rows


def sessions(seed, axes=AXES, tries=40, literals=None):
    """The run's sessions: dicts {axis: value}. Every pair of two axes' values in at least one session (a greedy
    all-pairs cover, its choices drawn from the seed), then the corners: each level with every other axis at
    its first value and at its last; then a few sessions off the grid (FUZZ); then, for a change whose new
    conditions compare a configuration with values (literals, tools/fix-guard.py axis_literals), sessions at
    those values and beside them, at every level, and the same values in the pairs."""
    derived = derive(literals)
    if derived:
        axes = _with_derived(axes, derived)
    rng = random.Random(seed)
    todo = _pairs(axes)
    rows = []
    while todo:
        best, gain = None, -1
        for _ in range(tries):
            (i, a), (j, b) = rng.choice(sorted(todo))
            row = {i: a, j: b}
            order = [k for k in range(len(axes)) if k not in row]
            rng.shuffle(order)
            for k in order:
                scores = []
                for v in range(len(axes[k][1])):
                    n = sum(1 for m, w in row.items()
                            if (((m, w), (k, v)) if m < k else ((k, v), (m, w))) in todo)
                    scores.append((n, rng.random(), v))
                row[k] = max(scores)[2]
            got = sum(1 for (m, w), (k, v) in itertools.combinations(sorted(row.items()), 2)
                      if ((m, w), (k, v)) in todo)
            if got > gain:
                best, gain = row, got
        rows.append(best)
        todo -= {((m, w), (k, v)) for (m, w), (k, v) in itertools.combinations(sorted(best.items()), 2)}
    out = [{axes[k][0]: axes[k][1][v] for k, v in sorted(r.items())} for r in rows]
    names = [a[0] for a in axes]
    if "level" in names:
        for level in dict(axes)["level"]:
            for end in (0, -1):
                out.append(dict({n: v[end] for n, v in axes if n != "level"}, level=level))
        out += _fuzz_rows(random.Random(seed ^ 0x5eed), AXES, FUZZ_SESSIONS)
        out += _derived_rows(derived, AXES, dict(axes)["level"])
        out += _joint_rows(derived, AXES, dict(axes)["level"])
    return out


def _with_derived(axes, derived):
    """The axes with a change's own values added (the pairs then meet them with every other axis's values)."""
    extra = {"cores": "cores", "memory": "memory", "dpr": "scale", "timezone": "timezone", "language": "language"}
    out = []
    for name, values in axes:
        values = list(values)
        for kind, vals in derived.items():
            if extra.get(kind) == name:
                values += [v for v in vals if v not in values]
            if name == "screen" and kind.endswith("width"):
                values += [(int(v), max(480, int(round(v * 9 / 16)))) for v in vals
                           if (int(v), max(480, int(round(v * 9 / 16)))) not in values]
            if name == "screen" and kind.endswith("height"):
                values += [(max(640, int(round(v * 16 / 9))), int(v)) for v in vals
                           if (max(640, int(round(v * 16 / 9))), int(v)) not in values]
        out.append((name, tuple(values)))
    return tuple(out)


def too_many(literals):
    """True when a change compares with more values than a run measures (MAX_DERIVED), or its values make
    more combinations than a run measures (MAX_JOINT)."""
    d = derive(literals)
    return sum(len(v) for v in d.values()) > MAX_DERIVED * 3 or _joint_count(d) > MAX_JOINT


def viewport(s):
    """The page's size in CSS pixels in a session: the screen's, less the browser's window, at its zoom."""
    w, h = s["screen"]
    return int(w / s["zoom"]), int((h - CHROME_HEIGHT) / s["zoom"])


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    seed = int(argv[0]) if argv else 1
    rows = sessions(seed)
    print(json.dumps({"seed": seed, "sessions": len(rows), "rows": rows}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
