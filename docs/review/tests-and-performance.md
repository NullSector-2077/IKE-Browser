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

## 1.1.19, page dark mode with Dark Reader

Measured with `tests/measure_smooth.py` (six local pages, Dark Reader off,
on, and the engine's dark mode; 3 runs, this container, software drawing):
pictures, big photos, lazy pictures, a growing feed and a slowly arriving
page show no difference between the three. Pages with much CSS, shadow roots
or SVG showed one long task with Dark Reader at load (about 125-140 ms each
for 2,000 rules, 200 shadow roots, 2,000 SVG shapes). Six changes to Dark
Reader (`tools/build-darkreader.py`, 1.1.19 entries) remove repeated work.
The dark result is byte for byte the same with and without them: every
sheet, adopted sheet and computed colour, hashed, on six pages (one with
@media, @layer, @container, @supports and nested rules). Dark
Reader's own CPU time on those pages, median of 9 runs (headless Chromium,
DOM changed after load):

| Page | before | after | change |
|---|---|---|---|
| 200 shadow roots, one identical style each | 277.8 ms | 99.5 ms | -64 % |
| 200 shadow roots, adopted style sheets | 43.7 ms | 34.5 ms | -21 % |
| icons (SVG and inline styles) | 45.6 ms | 37.2 ms | -18 % |
| 2,000 CSS rules | 60.1 ms | 58.2 ms | -3 % |
| 2,000 CSS rules, the dark copy written as one text (second pass) | 77.9 ms | 52.0 ms | -33 % |
| 2,000 SVG shapes | 62.3 ms | 61.7 ms | about the same |

Most of what is left on the last two is real work (each colour converted,
each shape's colour written as an inline style, the page's own first layout
done in Dark Reader's task). No white frame was seen on the way: from a dark
page to any page (plain, slow style sheet, slow body, 4,000 rules, another
site in another process), frames grabbed every 15 ms for 3 s; the one white
case, an empty page in dark mode, is dark since 1.1.19
(`test_dark_blank.py`). Scrolling smoothness cannot be measured here
(software drawing caps every mode at about 37 frames a second): it is
measured on the owner's computer.

## 1.1.18, before and after

Same container as below (4 cores, no GPU; Qt 6.12.0 / PyQt6 6.12 from PyPI,
Ubuntu 24.04), filter lists read from one folder for both versions
(`--lists`; 9 of the 11 default lists: EasyList Italy and the Malicious URL
Blocklist could not be reached from the container), local pages only. "Before"
is `main` at 41aca0c (1.1.17), "after" is the 1.1.18 branch. Runs of the two
versions were alternated; medians of each run, averaged over the runs.

`tests/measure_perf.py` (two runs of each version, 3 start-ups each):

| Measure | 1.1.17 | 1.1.18 | Note |
|---|---|---|---|
| Page with 400 requests (150 to ad servers) | 437 ms | 377 ms | |
| Time spent checking its requests | 17.0 ms | 13.2 ms | |
| Interface thread's processor time for that page | 234 ms | 190 ms | `time.thread_time()` around each load, 3 alternated pairs |
| 30 frames, Off / Balanced / Strict / Maximum | 269 / 388 / 454 / 436 ms | 222 / 380 / 410 / 413 ms | the Off figures moved too: noise of the container |
| Start-up cold / warm | 0.89 / 0.60 s | 0.84 / 0.59 s | unchanged |
| Switching tab, new tab | 3.0, 9.0 ms | 3.1, 10.1 ms | unchanged |
| Memory, all processes, 1 tab / 10 tabs | 592 / 697 MB | 530 / 700 MB | the 1-tab figure moved between runs of the same version too |
| Processor at rest, 1 tab | 3.0 % | 1.1 % | **not claimed**: a direct test (heavy page in view, 15 s at rest, three runs alternated) gives 2.4 against 2.6 % |

DOM work (a page that adds 12,000 elements, removes them, and sets innerHTML
300 times, after it is loaded; median of 7 rounds, two runs each):

| | ms |
|---|---|
| Shield Off | 11.5 |
| 1.1.17, Balanced | 23.7 |
| 1.1.18, Balanced | 17.6 |
| without the frame guard's hooks at all (for reference, not shipped) | 13.7 |

Speedometer (WebKit/Speedometer, release/3.0 and release/3.1 branches, served
locally; 5 iterations a run; scores are low because the container has no GPU
and 4 shared cores — only the comparison counts):

| | 3.0 score | 3.1 score | ES6-Webpack-Complex-DOM (3.1) |
|---|---|---|---|
| Plain Qt WebEngine (no I.K.E.) | 12.0 | | |
| 1.1.17, Off | 12.3 | | |
| 1.1.17, Balanced | 10.57 (3 runs) | 10.75 (2 runs) | 128 ms |
| 1.1.18, Balanced | 10.90 (3 runs) | 10.85 (2 runs) | 110 ms |

In 3.1, the DOM-heavy tests improved (Angular-Complex-DOM -6 %,
React-Complex-DOM -10 %, Svelte-Complex-DOM -11 %, jQuery -9 %,
ES6-Webpack-Complex-DOM -14 %); the others moved by up to 6 % either way,
which is the noise of the container (they do not touch what changed).

What the comparison showed:

- I.K.E.'s own protections cost 2-4 % of the Speedometer score here (plain Qt
  WebEngine 12.0, I.K.E. Off 12.3, Balanced 11.8, Strict 11.8, Maximum 11.7 in
  one series of 5 iterations each). A gap of about 29 % against another
  browser on the owner's computer cannot come from them; the engine's Chromium
  version and its graphics path are the other candidates, to be checked on
  that computer (chrome://gpu in I.K.E., `pacman -Q qt6-webengine`).
- On the owner's computer (CachyOS, 2026-11-20; I.K.E. 1.1.17 as installed,
  Speedometer 3.0, 10 iterations, compared with a reference Chromium browser on the same computer):

  | Speedometer 3.0 | I.K.E., Dark Reader | reference | I.K.E., engine dark mode |
  |---|---|---|---|
  | Score, mean | 20.51 | 29.02 | 33.29 |
  | Score, iterations 2-10 | 20.90 | 29.58 | 33.88 |
  | Best | 21.74 | 30.71 | 34.90 |
  | First (cold) iteration | 16.98 | 23.91 | 28.06 |
  | Geomean of the times | 48.97 ms | 34.63 ms | 30.16 ms |
  | Async total | 647.35 ms | 489.06 ms | 223.99 ms |

  The gap came from Dark Reader; with the engine's dark mode I.K.E. scored
  14.7 % above the reference.
- Page dark mode with Dark Reader costs much more: 1.1.18 Balanced with dark
  mode on scored 6.12 with Dark Reader (Complex-DOM tests 2-7 times slower)
  and 10.5 with the engine's own dark mode. Dark Reader watches every change of
  a page by design; I.K.E.'s own part around it (darkmode.js) is small.
- The main cost of the fingerprinting protection on DOM-heavy pages was its
  MutationObserver on the whole document for the page's whole life (removing
  it alone took the four DOM-heavy tests from 9.7 to 10.45); the hooks on
  appendChild and the like cost little (about 0.3 microseconds a call), and
  the innerHTML hook nothing measurable.
- Per frame, the protection's script takes about 0.3 ms to install (4-5 ms in
  the top page). At Strict and Maximum the font masks cost much more until
  I.K.E. knows which fonts the computer has (the first 15 seconds of a new
  profile, or after fonts change): the 30-frame page took 1.2 s instead of
  0.4 s then; afterwards Strict and Maximum cost about 5 % more than Balanced.
- The request checks run in the interface's thread (verified:
  `QThread.currentThread()` inside `interceptRequest` is the application's
  thread). Of what is left (about 33 microseconds a request), the Rust engine
  is about a quarter; moving more of the checks into Rust would save a few
  milliseconds per heavy page and duplicate security rules in two languages, so
  it was not done.
- Tabs at rest (a busy page with timers and 30 MB of data, all processes):

  | Tabs | Active | Frozen | Suspended |
  |---|---|---|---|
  | 10 | 882 MB, 6.4 % | 851 MB, 1.1 % | 384 MB, 0.9 % |
  | 20 | 1394 MB, 2.3 % | 1339 MB, 0.7 % | 401 MB, 1.0 % |
  | 30 | 1912 MB, 2.2 % | 1828 MB, 1.6 % | 422 MB, 1.1 % |

  The engine already slows hidden tabs down, so freezing saves little;
  suspending gives back about 50 MB a tab. 1.1.18 therefore suspends earlier
  only when the computer runs short of memory.

### 1.1.18, final comparison (second pass)

Same kind of container (4 cores, no GPU), `main` at 9a49196 (1.1.17 with the
automation of #59, #62, #63) against this branch at 19f4684, 8 of the 11
default lists read from one folder for both (EasyList Italy, the Malicious
URL Blocklist and the EasyList Cookie List could not be reached), local pages
only. Runs alternated old / new. Other agents compiled in the same container
during the second round, so its absolute numbers are lower; only the
alternated pairs are compared.

Speedometer 3.1 (WebKit/Speedometer `release/3.1`, served locally, 3
iterations a run, Balanced):

| Page dark mode | 1.1.17 (round 1 / 2) | 1.1.18 (round 1 / 2) |
|---|---|---|
| none | 9.13 / 8.25 | 9.12 / 8.12 (same) |
| the engine's own | 8.80 / 9.08 | 8.83 / 8.56 (within the noise) |
| Dark Reader | 5.24 / 4.94 | 6.56 / 5.85 (+18-25 %) |

`tests/measure_perf.py --runs 2` (round 1 / round 2):

| Measure | 1.1.17 | 1.1.18 |
|---|---|---|
| Page with 400 requests: interface thread's processor time | 317 / 337 ms | 281 / 273 ms |
| Its request checks | 19.0 / 16.1 ms | 12.6 / 14.6 ms |
| Its load | 479 / 517 ms | 492 / 434 ms (noise) |
| Shield redrawn for it | 4 / 4 | 3 / 3 |
| Start-up cold, warm | 0.98-1.00, 0.63-0.65 s | 0.94-1.02, 0.64-0.71 s (same) |
| Engine rebuilt, window frozen meanwhile | 300 ms, 20 ms | 290 ms, 20 ms (same) |
| 30 frames, Off / Balanced / Strict / Maximum | 292-363 / 444 / 531-543 / 524-550 ms | 274-310 / 414-518 / 464-612 / 500-564 ms (noise, both ways) |
| Processor at rest, 1 tab / 10 tabs | 4.5, 3.9 % / 0.75, 0.70 % | 1.5, 1.5 % / 0.75, 0.55 % |
| Memory, all processes, 1 tab / 10 tabs | 550, 546 / 708, 703 MB | 540, 422 / 709, 621 MB (the second round of 1.1.18 is lower, not claimed) |

The request checks while the engine is rebuilt in the background (after a
list update), heavy page, 5 rounds of 6 loads, alternated: all checks of a
load 24-35 ms -> 17-24 ms, the slowest single check 6-18 ms -> 1.8-2.5 ms
(the Rust module no longer lets go of Python's lock for one check). The
longest pause of the interface during such a load moved from 60-82 to
75-108 ms in medians; per load the values overlap widely (42-134 ms either
way), so no change is claimed for it.

Many tabs (a "live" page: a timer changing the page every 100 ms, an
animation, 2,000 objects of data; one window, all processes; same numbers
for 1.1.17 and 1.1.18 within 1 %):

| Tabs | Active | Frozen | Suspended | A suspended tab shown again |
|---|---|---|---|---|
| 10 | 598 MB, 20 % | 604 MB, 14 % | 437 MB, 2.6 % | 0.40 s |
| 20 | 812 MB, 18 % | 808 MB, 11 % | 451 MB, 2.6 % | 0.40 s |
| 30 | 1021 MB, 18.5 % | 1007 MB, 8 % | 461 MB, 2.8 % | 0.35 s |

Processor time in those rows comes almost all from the tab in view. Ten
live tabs in the background with an empty tab in view: 1.7 % in the first
minute, then 0.0-0.1 % per minute for the next seven (the engine already
slows hidden tabs down). Freezing tabs earlier would therefore save nothing;
suspending gives back memory (about 19 MB a tab here), which 1.1.18 does
earlier only when memory runs short.

## 1.1.18, page dark mode with Dark Reader

Where Dark Reader's cost came from (Speedometer 3.0 suites traced through
the DevTools protocol: style recalculations with their element counts and
causes, selector statistics, and the JavaScript profile inside the measured
steps only):

- **Whole-page restyles inside the steps.** Most of the extra time was the
  engine styling every element of a page again, not Dark Reader's script:
  - after a large change of the page, every style element added since Dark
    Reader started counted as "moved" (its new neighbour was Dark Reader's
    own copy of it) and its copy was rebuilt: Svelte-Complex-DOM, 118
    rebuilds and 1,771 elements restyled in one step instead of 600;
  - each colour seen for the first time became a new variable on `:root`,
    which restyles everything (Charts-observable-plot 16 times,
    React-Stockcharts-SVG 13, Editor-CodeMirror 54 in their steps);
  - a page variable whose kind (background, text, border) Dark Reader learns
    only later changes a `:root` rule of its copy: TodoMVC-Lit-Complex-DOM,
    7,521 elements restyled when the first item (a shadow root with adopted
    style sheets) appears, against 817 without Dark Reader.
- **SVG shapes measured one at a time.** For every shape with a fill colour
  Dark Reader reads its size right after changing the previous shape, so the
  page is laid out again for each one: 40 % of Charts-observable-plot's
  steps.
- **The walk looking for shadow roots** asked a script function about every
  element: 6.2 ms on a 9,000-element page; the same walk without it, 0.4 ms.
- **More style sheets for every element.** Dark Reader adds a copy after
  every style element of the page; each element is then matched against
  twice as many sheets (the Complex-DOM pages have 416 identical style
  elements inside SVG icons: their copies alone cost about 20 % of those
  suites). This is how Dark Reader keeps the page's order of rules; the
  first round left it as it is, the second round (`style-groups`, below)
  shares one copy among identical style elements.

Changes (build-time patches in `tools/build-darkreader.py`, each refused if
a new engine no longer has the text it changes): `style-moves`,
`color-variables` and `svg-sizes` remove the restyles and layouts above,
`shadow-host-walk` the slow walk. The computed colours of a test page with
every kind of content (`tests/test_darkreader.py::test_what_dark_reader_darkens`)
are identical before and after.

Speedometer 3.0, Balanced, dark mode on with Dark Reader, 5 iterations a
run, runs alternated (container: 4 shared cores, no GPU):

| | before | after |
|---|---|---|
| Score, pair 1 | 5.90 | 6.87 |
| Score, pair 2 | 6.16 | 7.22 |
| TodoMVC-Svelte-Complex-DOM | 236 / 233 ms | 71 / 60 ms |
| Charts-observable-plot | 299 / 336 ms | 228 / 221 ms |
| React-Stockcharts-SVG | 397 / 378 ms | 326 / 312 ms |
| TodoMVC-Lit-Complex-DOM | 287 / 260 ms | 259 / 244 ms |

On six of the heaviest suites (two more pairs, before / after / after
without `color-variables`): 4.97 and 5.56 / 7.12 and 7.50 / 6.90 and 6.92;
`color-variables` alone took Charts-observable-plot from 252 and 228 ms to
224 and 210 ms. The other suites moved within the noise of the container.
For reference, on the same container: no dark mode 10.9, the engine's own
dark mode 10.5. `tests/measure_dom.py` (dark mode on) did not change (24.5
and 25.4 before, 24.7 and 24.9 ms after): it times only the page's own
script, and Dark Reader's work runs after it.

Second round (same branch):

- `style-groups`: identical style elements (same text, media, type and
  title, in the same document or shadow root) share one Dark Reader copy,
  placed after the last of them. All the originals give the same
  declarations and all the copies the same changed ones, and a copy comes
  right after its original, so the copy after the last original is the one
  that wins in the cascade over the others and over any rule in between.
  When the page adds, removes or moves members, the copy goes after the new
  last one before anything is drawn; an element whose text, attributes or
  rules change leaves its group and gets its own copy, as before. Test:
  `test_identical_style_elements_share_one_copy` (seven phases of moves,
  additions, removals, text and CSSOM changes, a different rule in between,
  a media group, a shadow root); run on the version before, it passes every
  colour check and fails only on the number of copies.
- `shadow-texts`, `adopted-once`: the texts of the three style elements of
  every shadow root are built once per theme and fix; a root's adopted
  sheets are set once per render to the same final list. Dark Reader's
  script in the "add 100 items" steps of WebComponents and Lit: 361 -> 283
  profile samples; the suites' timings moved within the noise.
- `image-selectors`: one search for all background-image selectors that
  wait for a matching element, the per-selector search only when it finds
  something (TodoMVC-jQuery: 55 samples in its steps).

The computed colours, borders, fills, strokes and background images of every
element (document and shadow roots, about 6,300 each) of the Lit, Svelte and
WebComponents Complex-DOM pages, after adding 12 items, are identical with
and without all the changes.

Speedometer 3.0 after both rounds (this session's container was slower than
the first one: the engine's own dark mode scored 8.66 here):

| | before | after |
|---|---|---|
| Score, pair 1 | 5.75 | 7.01 |
| Score, pair 2 | 5.69 | 6.73 |
| TodoMVC-Lit-Complex-DOM | 267 / 280 ms | 164 / 187 ms |
| TodoMVC-Svelte-Complex-DOM | 197 / 305 ms | 46 / 59 ms |
| TodoMVC-JavaScript-ES6-Webpack-Complex-DOM | 287 / 224 ms | 190 / 191 ms |
| TodoMVC-Angular-Complex-DOM | 117 / 117 ms | 93 / 97 ms |
| Charts-observable-plot | 343 / 375 ms | 258 / 220 ms |
| React-Stockcharts-SVG | 393 / 440 ms | 354 / 364 ms |

Seven Complex-DOM suites alone, `style-groups` against the first round (two
alternated pairs): 7.93 / 7.65 -> 9.37 / 9.93.

What is left, and why:

- a page variable whose kind is learned late (Lit) still restyles the whole
  page once: the new value must reach every element (Lit 164-187 ms against
  49 with the engine's dark mode);
- every element with an inline colour or a fill gets Dark Reader's own
  inline values, and SVG shapes must be measured to tell icons from
  backgrounds (charts: about 1.9 times the engine's dark mode for
  observable-plot, 1.35 for Stockcharts);
- every change of a page is examined, and every shadow root gets three style
  elements and its own watchers. They cannot be one constructed sheet
  adopted by all roots: adopted sheets come after a root's own style
  elements in the cascade, while Dark Reader puts its elements first, so a
  page rule of the same specificity would lose where it now wins;
- style sheets that are not identical still each get a copy.

## 1.1.18, the security work (before = `main` at 09569d1, after = PR #69)

Same container (Ubuntu, PyPI Qt 6.12.0 / Chromium 140, 4 shared cores, no
GPU), the two copies run one after the other with the same commands, on
2026-11-20. Small differences are within the noise of this machine.

| Measure | before | after |
|---|---|---|
| Start-up to first window (`measure_startup.py 5`, two runs each) | 0.237 / 0.222 s | 0.199 / 0.237 s |
| CPU at rest, new tab page (`measure_idle.py 20`, two runs each) | 2.4 / 2.0 % of a core | 2.1 / 2.0 % |
| CPU while using the interface | 6.6 / 8.1 % | 7.8 / 6.3 % |
| Memory after the interface run, back to back late in the evening | 417-421 MiB | 410-426 MiB |
| `measure_perf.py --runs 3`: frames, Balanced | 263.7 ms | 265.7 ms |
| `measure_perf.py`: one tab / ten tabs (PSS) | 526 / 700 MB | 531 / 705 MB |
| Speedometer 3.0, Balanced, 5 iterations, one run each | 13.0 | 14.1 |
| Site isolation alone: 4 tabs with 4 frames of other sites each, 3 runs each way | 435-436 MB, 8 processes | 494-495 MB, 13 processes |

The first two `measure_idle` runs gave 303 and 314 MiB for "before" and 410
and 411 MiB for "after"; run again back to back, "before" gave 417 and 421:
the earlier difference was the machine, not the code (with site isolation
switched off the "after" copy gave 416-423). Site isolation costs memory only
when pages have frames of other sites (+13 % in the test above, one more
process per other site); pages without them are unchanged. Not measured:
real hardware GPUs and video decoding, a real Plasma session.

## 1.1.17, before and after

Same container (4 cores, no GPU), same commands: `tests/measure_perf.py`
on a copy of `main` before the work (dc94b62, with its own filter engine
library) and on the finished branch (with the rebuilt library). The same
filter lists were used for both (`--lists`), and local test pages, so the
network does not count. Medians; three runs each unless said otherwise.

| Measure | Before | After | Note |
|---|---|---|---|
| Start-up to first window, cold | 0.79 s | 0.84 s | within the noise: warm start-ups alternated old/new gave 0.570 against 0.573 s |
| Start-up, warm | 0.57 s | 0.62 s | same as above |
| Rebuilding the filter engine | 195 ms | 204 ms | now on its own thread |
| Window frozen while the engine is rebuilt | 191 ms | 13 ms | the real gain of P1 |
| Page with 400 requests (150 to ad servers) | 612 ms | 554 ms | |
| Time spent checking its requests | 61 ms | 19 ms | |
| Shield redrawn for it | 152 times | 4 times | |
| 30 frames, shield Off | 283 ms | 267 ms | |
| 30 frames, Balanced | 349 ms | 348 ms | 5 rounds × 10 loads, old and new alternated; a first, non-alternated run gave 333 against 389 ms |
| 30 frames, Strict | 1108 ms | 430 ms | fonts: only the ones a page can find are masked |
| 30 frames, Maximum | 899 ms | 387 ms | same |
| Switching tab | 3.8 ms | 3.0 ms | |
| Opening a new tab | 11.1 ms | 10.9 ms | |
| Processor at rest, 1 tab | 3.8 % | 3.3 % | share of one core |
| Processor at rest, 10 tabs | 0.55 % | 0.50 % | |
| Memory, all processes, 1 tab (PSS) | 711 MB | 573 MB | |
| Memory, all processes, 10 tabs (PSS) | 875 MB | 730 MB | |
| Memory of the main process, 5 engine rebuilds | 308 → 318 MB | 336 → 349 MB | stops growing after the second rebuild: the memory kept by the one build thread, given back to the system after each swap (`malloc_trim`); no leak |

The protections were measured with the numbers above, not switched off for
them:

- the heavy page has the same requests blocked before and after;
- fingerprinting: of the 714 fonts of the list, 50 can be found on this
  computer; with only those 50 masked a page finds 0 of them, as with all 714;
- the whole test suite (AdBlock, Shields, fingerprinting, passwords, user
  scripts, updates) passes on the branch.

### Final checks of the owner (1.1.17)

| Check | Result | Test |
|---|---|---|
| Home network: a public site's page or frame cannot open a private IPv4 address, localhost, `[::1]`, a `fd00::/8` address, a `.local` or `.localhost` name, nor go there through a redirect | stopped, and the window says so (also for a frame: before this check a stopped frame was silent) | `test_home_network_protection_in_every_case`, `test_a_redirect_from_a_public_address_to_home_is_stopped` |
| Home network: addresses the user types or picks, and home pages that use home addresses, are never stopped | not stopped | same |
| "Allow for this site": that site only, until I.K.E. closes; nothing written to the settings | as described | same |
| User scripts: install, daily check and "Check for updates" gather files with the same checks | one function for all three | `test_script_updates_go_through_the_same_checks` and the earlier user-script tests |
| User scripts: redirects and DNS rebinding | each redirect is checked; a file's name is looked up once and the connection goes to that checked address (new in this check) | `test_script_libraries_go_to_the_address_that_was_checked` |
| User scripts: a new update cannot bring code from new places or widen its permissions in silence | it asks | `test_a_user_script_update_loading_code_from_new_places_asks` and earlier |
| Errors: a name that cannot be looked up, a timeout, a failed redirect | refused for user-script files; a fault inside the request checks keeps files of the computer and a public site's way into the home network refused (new in this check), while ordinary pages go on | `test_errors_while_checking_keep_protected_things_protected`, `test_a_name_that_does_not_resolve_is_not_let_through` |
| Two profiles at once | settings, data and cache are separate per profile; the only shared folder is the program updates: installing is one at a time (lock), and the state file is written through a temporary file of each process | `test_two_profiles_never_write_the_update_state_over_each_other`, `test_one_installation_at_a_time` |

### Limits that remain

- A name of the home network that is not written as an address (for example
  `fritz.box`) is not recognised as local by the request checks, because they
  run without a DNS lookup (a lookup there would slow every page). The web
  engine's own protection (Private Network Access) still stops a public page's
  scripts and images towards it; a public page that sends the tab there is not
  stopped. (Note of 2026-11-20: tried with Qt 6.12, the engine's protection
  is off and stopped nothing; since 1.1.18 `fritz.box`, `*.lan` and similar
  names are recognised by their form. See docs/SECURITY.md.)
- Behind a proxy set in the environment the user-script downloads cannot pin
  the checked address (the proxy looks the name up); the redirect and address
  checks still apply.
- These numbers come from a container without a GPU; they compare the two
  versions, they do not say how fast I.K.E. is on the owner's computer.
