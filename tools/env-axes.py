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


def sessions(seed, axes=AXES, tries=40):
    """The run's sessions: dicts {axis: value}. Every pair of two axes' values in at least one session (a greedy
    all-pairs cover, its choices drawn from the seed), then the corners: each level with every other axis at
    its first value and at its last."""
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
    return out


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
