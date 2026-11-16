# Tests and performance

## Environment of the tests

A Linux container without a display: Python 3.13.18, PyQt6 6.12.0 and
PyQt6-WebEngine 6.140.0 from PyPI (the versions of
`tools/test-requirements.txt`; Chromium 140.0.7339.264), Rust 1.97.0, two
processor cores, Qt's `offscreen` platform, the Chromium sandbox off (it
cannot start in the container, as on the GitHub runner). **Not** CachyOS, not
Plasma, not Wayland, not Arch's own Qt packages.

## Tests run

| Check | 1.0.1 | 1.0.2 | 1.0.3 |
|---|---|---|---|
| `ruff check .` | clean | clean | clean |
| `python3 -m pytest`, repository | 129 passed, 1 skipped | 146 passed, 1 skipped | 171 passed, 1 skipped |
| Package built from the PKGBUILD with `makepkg` (as an ordinary user, dependency check off: the container is not Arch) | built | built | built |
| `python3 -m pytest` against the files of the built package (`IKE_TEST_APP`) | 129 passed, 1 skipped | 146 passed, 1 skipped | 171 passed, 1 skipped |
| No key or certificate file inside the package | checked | checked | checked |
| GitHub "Tests" workflow on the pull request (Ubuntu runner: lint, tests, package, tests on the installed copy) | passed | passed | see the pull request |
| `cargo test` of the engine module | — | — | 1 passed |
| `cargo audit` | — | — | 0 vulnerabilities (89 crates) |
| `pip-audit -r tools/test-requirements.txt` | — | — | no known vulnerabilities |
| `tools/check-lang.py` (seven languages, every string of the source) | 0 missing | 0 missing | 780 of 780, 0 missing |
| `tools/check-components.py` against the real sources | — | — | run; see [dependencies.md](dependencies.md) |

The one skipped test is the one that asks the real upstream sources for the
component check (it runs only with `IKE_TEST_NETWORK=1`); the same check was
run by hand, last row of the table.

What the tests are: each starts the real browser with an empty profile and
looks at it from inside (see [docs/TESTING.md](../TESTING.md)). Mouse and
keyboard are simulated by sending Qt events to the widgets. New in these
versions: `test_brand.py`, `test_linkbar.py` (1.0.1), `test_toolbar.py`,
`test_effects.py`, `test_newtab_background.py` (1.0.2), `test_security.py`
(1.0.3, 25 tests). Since 1.0.3 a test also fails when the browser logged an
internal error during it.

## Tests that could not be run

Nothing in this list was tried. The owner's checklist is in
[remaining-work.md](remaining-work.md).

| Not run | Why | Risk left |
|---|---|---|
| Installing the package with `pacman -U` on Arch / CachyOS | no pacman database in the container; the package was built and unpacked, its files tested | dependency names or install paths wrong on a real system (unchanged since 1.0.0 except the removed `conflicts` / `replaces`) |
| A start on KDE Plasma 6 / Wayland with Arch's Qt 6 packages | no display, no compositor | anything that depends on the platform plugin, the Breeze style or KWin: exact sizes, fades, the drag ghost, window buttons |
| Dragging toolbar buttons with a real mouse or touchpad | events were simulated | timing of the long press, the feel of the drag |
| Fractional scaling and a change of scale while running | `offscreen` has one fixed scale; scales were simulated by size only | blurry or misplaced marks at 125 % / 150 % |
| Reduced motion read from a running Plasma | read from files written by the test | a different key in a newer Plasma |
| Klipper, `notify-send`, `xdg-open`, KRunner, KDE Connect, media keys | stand-ins on a private D-Bus | behaviour of the real services |
| Pages of real websites | by rule: nothing against third-party sites | breakage of a particular site by the new local-file or external-link rules (they act on `file:` pages and non-web links only) |
| GPU acceleration, video, DRM (Widevine), codecs | no GPU, no proprietary codecs in the PyPI build | none of these was changed |
| The self-update from 1.0.2 to 1.0.3 against the real release server | needs a signed release, which only the owner can make | covered by `test_updater.py` with a local server and a test key |
| Windows, other Linux distributions | out of scope of 1.0.x | see `docs/platforms/` |

## Performance, before and after

Same machine, same commands, the installed files of the 1.0.2 package against
those of the 1.0.3 package, runs alternated. Three rounds; ranges are given
because the differences between rounds are larger than between versions.

| Measure | 1.0.2 | 1.0.3 | Tool |
|---|---|---|---|
| Start-up to first window (median of 9 starts) | 0.27 – 0.30 s | 0.28 – 0.29 s | `tests/measure_startup.py` |
| Processor at rest (share of one core, 20 s) | 0.70 – 0.80 % | 0.70 – 0.75 % | `tests/measure_idle.py` |
| Processor while the toolbar is used | 5.8 – 6.2 % | 5.8 – 6.0 % | same |
| Memory, all processes (PSS) | 359 – 362 MiB | 362 – 366 MiB | same |
| Opening a new tab (median of 30) | 78 – 85 ms | 82 – 85 ms | script of the audit: `add_tab` to `loadFinished` |
| Loading a local test page (300 paragraphs, 20 pictures, 10 scripts, 10 blocked requests; median of 30) | 96 – 103 ms | 93 – 100 ms | same script, local server |
| Applying settings with unchanged lists | 0.29 s | 0.00 s | see [changes.md](changes.md) |
| Filter engine, one request | 1.40 – 1.51 µs | 1.47 – 1.63 µs | see [changes.md](changes.md) |

Reading: no measurable change in start-up, tab opening, page loading,
processor time or memory. One real gain (settings) and one real, very small
cost (the guard around the engine).

1.0.1 against 1.0.2, measured the same way when 1.0.2 was finished: rest
0.7 – 0.8 % both, toolbar use about 5.4 % against 5.0 – 5.5 %, memory 349 MiB
both, start-up 0.28 s against 0.27 s. (Absolute figures differ a little
between the two sessions; only figures of the same session are compared.)

These numbers describe a small container without a GPU. They say that the
versions do not differ, not how fast I.K.E. is on the owner's computer.
