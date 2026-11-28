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
| Windows, other Linux distributions | out of scope of 1.0.x | see `docs/platforms/` on the archive branch `docs/multiplatform-plan` |

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
versions do not differ, not how fast I.K.E. is on a real computer.

## 1.1.25 fingerprinting

The owner asked whether the fingerprinting changes of 1.1.25 cost anything.

**How it was measured.** `tests/measure_fp125.py` (new): the Arch container
(4 shared cores, no GPU, software WebGL as the tests, `offscreen`), the
default lists as far as they could be had offline. Before = `main` at
5c26c2f, after = this branch; the two copies alternate start by start, at
Balanced, Strict and Maximum; each start times every item 5 times inside the
page (performance.now) and keeps the median; 5 starts of each copy at each
level: the median of the 5 medians, and their spread (min-max), in ms.

| ms | Balanced before | Balanced after | Strict before | Strict after | Maximum before | Maximum after |
|---|---|---|---|---|---|---|
| 30 frames put in and loaded | 390.9 (326.2-402.6) | 352.3 (336.4-389.8) | 978.0 (910.5-1089.9) | 1056.2 (941.0-1129.6) | 1005.8 (983.6-1106.7) | 1035.4 (961.4-1054.2) |
| an inline (blob) worker, to its first message | 34.5 (30.1-41.0) | 33.2 (28.9-41.0) | 58.7 (52.0-68.1) | 44.3 (31.3-51.2) | 60.7 (55.4-73.0) | 40.6 (29.0-54.6) |
| a worker from a file (classic) | 7.9 (7.1-10.0) | 7.7 (7.5-16.0) | 9.7 (7.9-12.6) | 19.6 (17.2-26.4) | 11.5 (10.7-13.8) | 17.8 (16.8-23.4) |
| a worker from a file (module) | 7.6 (6.3-9.6) | 7.4 (6.9-8.5) | 8.5 (7.4-13.3) | 20.9 (18.8-22.1) | 9.1 (7.9-22.3) | 18.2 (16.8-21.7) |
| 20 workers from a file at once | 72.7 (60.7-87.7) | 68.4 (62.9-88.5) | 77.8 (70.4-96.2) | 226.8 (195.3-235.4) | 93.0 (81.1-95.8) | 203.7 (195.0-261.6) |
| getImageData, 1000 x 1000 canvas with text | 7.7 (6.9-9.1) | 7.5 (6.8-12.8) | 7.4 (7.3-8.2) | 8.4 (7.1-10.6) | 7.9 (7.5-11.5) | 8.7 (7.2-10.4) |
| toDataURL, the same | 17.0 (14.4-17.4) | 16.7 (15.5-18.6) | 17.8 (15.2-23.4) | 17.0 (15.9-21.2) | 17.6 (16.9-18.7) | 18.9 (16.2-19.2) |
| getImageData, 1000 x 1000 canvas of rectangles | 5.2 (4.8-5.6) | 5.1 (4.8-5.3) | 5.1 (4.8-5.8) | 3.2 (3.0-3.4) | 5.2 (4.7-5.7) | 3.3 (3.0-3.4) |
| toDataURL, the same | 14.4 (12.6-15.3) | 13.7 (12.7-14.6) | 14.1 (11.8-18.1) | 6.3 (5.8-6.4) | 14.4 (13.1-14.6) | 6.3 (6.0-6.5) |
| 10,000 WebGL getParameter | 1.6 (1.1-1.8) | 1.1 (0.9-1.2) | 1.1 (0.9-1.1) | 1.3 (1.1-2.5) | 1.2 (0.9-3.7) | 1.3 (1.3-2.1) |
| 20 readPixels of 256 x 256 | 19.7 (15.5-25.1) | 17.8 (16.7-25.3) | 16.6 (16.2-29.3) | 24.0 (22.7-31.1) | 19.2 (18.5-21.2) | 25.4 (23.2-34.1) |
| 10,000 measureText + width | 8.2 (5.7-11.8) | 6.5 (6.1-8.3) | 19.6 (18.1-28.8) | 8.6 (7.1-10.9) | 22.0 (18.9-32.8) | 8.0 (6.7-10.4) |

**Reading.** Balanced: no difference larger than the spread (nothing of
Balanced changed but the inline workers' languages). Strict and Maximum:

- **Workers from a file** cost about 10 ms more to start (8-12 -> 17-21 ms),
  20 at once about 130 ms more (78-93 -> 204-227 ms): before 1.1.25 such a
  worker started with no protection at all; now it starts as an inline
  worker does (the protection's own code first). Inline workers start
  faster than before (59-61 -> 41-44 ms, see below). 20 at once cost less
  after the review's third round (below).
- **Canvas**: a canvas of solid rectangles is read about twice as fast
  (no noise: toDataURL 14 -> 6 ms); one with text costs the same as before
  within the spread (getImageData 7.4-7.9 -> 8.4-8.7 ms, toDataURL equal).
- **measureText** is 2.5 times faster (20-22 -> 8-9 ms for 10,000): it is no
  longer wrapped, the width's noise is computed from the width alone.
- **WebGL readPixels**: the median is about 0.3 ms more per 256 x 256 read
  (16.6-19.2 -> 24-25 ms for 20; the spreads touch at Strict, not at
  Maximum): each pixel is compared with its neighbours so that a plain
  colour reads back exactly. getParameter: no difference beyond the spread.
- **Frames**: 30 frames 3-8 % slower (978-1006 -> 1035-1056 ms), inside the
  spread of both copies (910-1107 against 941-1130): the protection installed
  in each frame wraps a few more methods.

**What was made cheaper after the first measurement** (the same method,
Strict, first run against the final one):

| ms | before (main) | first version | final |
|---|---|---|---|
| a worker from a file (classic) | 12.6 (8.4-15.2) | 36.3 (32.9-46.3) | 19.6 (17.2-26.4) |
| a worker from a file (module) | 9.3 (7.5-12.2) | 43.8 (35.0-46.9) | 20.9 (18.8-22.1) |
| 20 workers from a file at once | 96.1 (81.3-99.0) | 473.4 (467.2-495.4) | 226.8 (195.3-235.4) |
| an inline (blob) worker, to its first message | 64.0 (54.4-83.1) | 58.7 (49.5-80.4) | 44.3 (31.3-51.2) |
| getImageData, 1000 x 1000 canvas with text | 8.1 (7.9-9.6) | 19.9 (16.2-22.2) | 8.4 (7.1-10.6) |
| toDataURL, the same | 18.3 (16.0-19.1) | 23.0 (21.9-27.1) | 17.0 (15.9-21.2) |

- The font masks of a worker (one empty face for each installed font name a
  site could test, needed at Strict and above) are made when the worker
  first reaches its fonts (its font set, a FontFace, a canvas of its own),
  not when it starts: they were about half of a worker's start, and most
  workers draw no text.
- The edge noise of a 2D read takes the four one-pixel rows and columns
  around the part read instead of reading the whole part a second time with
  a margin, and the whole canvas (toDataURL, toBlob, convertToBlob) needs no
  second read at all; large pictures skip the pixels that are not looked at
  instead of testing each one.

**Workers from a file after the review's third round.** A classic script
is no longer read by the page (the page waited for it, once per worker):
the worker fetches it itself with `importScripts`; a module's first
messages are held until it has run. Measured again the same way (5 starts
of each copy, Strict and Maximum, all items; the others did not move beyond
their spread):

| ms | Strict before (main) | Strict, round 2 | Strict, round 3 | Maximum before (main) | Maximum, round 2 | Maximum, round 3 |
|---|---|---|---|---|---|---|
| a worker from a file (classic) | 8.8 (6.8-11.1) | 19.6 (17.2-26.4) | 18.5 (14.4-24.2) | 8.9 (7.8-10.6) | 17.8 (16.8-23.4) | 19.2 (15.1-23.7) |
| a worker from a file (module) | 8.0 (5.9-8.5) | 20.9 (18.8-22.1) | 17.6 (15.1-22.8) | 8.6 (7.1-8.9) | 18.2 (16.8-21.7) | 17.4 (15.6-22.1) |
| 20 workers from a file at once | 69.5 (53.5-75.0) | 226.8 (195.3-235.4) | 120.8 (115.6-157.1) | 66.6 (62.5-78.5) | 203.7 (195.0-261.6) | 133.5 (125.3-152.4) |
| an inline (blob) worker, to its first message | 51.4 (43.6-58.1) | 44.3 (31.3-51.2) | 32.7 (30.2-46.5) | 57.6 (47.7-67.4) | 40.6 (29.0-54.6) | 39.0 (31.0-42.1) |

("before" and "round 3" from this run; "round 2" from the run above.) One
worker: the same as in round 2 within the spread, about 10 ms more than
with no protection. 20 at once: about 50-65 ms more than with no
protection, where round 2 cost 110-150 ms more: the workers' scripts are
now fetched side by side, not one after the other by the page.

Not tried: a computer with a real GPU, Speedometer (not reachable here). These figures say what differs between the two copies on
this machine, not how fast I.K.E. is.

## 1.1.24, the frame guard

The aim: the frame guard of fingerprint.js cheaper, with no frame of a
page's own site ever handed out unprotected.

**How it was measured.** The Arch container (4 shared cores, no GPU,
`offscreen`; other sessions ran tests at the same time, so single runs vary
by 5-10 %). Before = `main` at d036bb1, after = this branch; the two copies
alternate start by start. A page doing what Speedometer's pages do, each
part timed on its own, 9 rounds a load, 3 loads a start, 16 starts of each
copy (48 medians each, the median of them given):

| ms | Off | before | after |
|---|---|---|---|
| 3,000 list items appended one by one (TodoMVC vanilla) | 9.2 | 13.75 | 13.1 |
| 10 trees of 300 items built outside the page, then put in (React, Lit) | 5.8 | 8.4 | 7.4 |
| HTML written with innerHTML (jQuery, Backbone) | 10.25 | 11.75 | 11.45 |
| 6,000 text nodes put into the page | 2.1 | 2.65 | 2.6 |
| insertBefore / after / replaceWith in the page | 2.55 | 3.9 | 3.7 |
| the page of tests/measure_dom.py | 10.05 | 13.1 | 12.55 |

Speedometer (main branch of WebKit/Speedometer, served locally; 14 DOM
suites: the vanilla, Web Components, React, React-Redux, Backbone, Angular,
Vue, jQuery, Preact, Svelte and Lit TodoMVCs and both news sites; 3
iterations a run, 7 runs of each copy alternated): score 12.9 before, 13.2
after, median; the runs spread over 11.4-14.3 for both. No claim is made
from it: the guard is a small part of the whole benchmark (1.1.23).

**Where the cost is.** Measured in a plain Qt WebEngine page (no I.K.E.):
a MutationObserver that watched the document once and was disconnected
leaves every later insertion 22 % slower (8.8 -> 10.7 ms for the page of
measure_dom.py), because the engine keeps the document marked as watched
for good. In I.K.E. (copies of fingerprint.js with one part taken out, for
reference only): without the watch of the loading page, items appended
12.9 -> 11.7 ms, innerHTML 11.0 -> 9.1; without the hooks of the DOM
methods, items appended 12.9 -> 10.0, trees 7.9 -> 5.9. Inside the hooks,
the function around the engine's method costs about 0.7 ms of the 3,000
items, and each look through one of the engine's getters about 50 ns (as
much as the number of frames of the window): in a loop alone 10-20 ns, in a
real page several times that.

**What changed** (fingerprint.js, `guard()`), in the order the looks are
taken: the nodes put in, as before (text and an element without children
that is not a frame: done; children are now looked at before the name, and
the name is compared as a string); then the target: outside any document,
nothing put there gets a window, and nothing more is looked at (taken
before the call, since replaceWith takes the target itself out; a node in
a shadow root is in the document when its host is; a Range is never
"outside"); a call that swaps nodes no longer reads the count before it,
which it never used (it is looked at after it in any case); with no frame
at the guard's last look, the count before the call is taken as 0 (none
after: nothing came in; any after: every frame is looked at, whatever the
call did). With frames at the last look both counts are read as before, so
the review's "frame removed, another added" attack is met the same way.
The number of frames is read through a bound call.

**What could not be made cheaper, and why.** The watch while the page
loads protects a frame written in the page's HTML before the page's next
script reads it through `window[i]` or by its name, which no getter can
catch. Checked here: the engine runs nothing (not even a script injected
for every frame at document creation) in a frame the parser just wrote
before the parent's next script (a probe script saw "none" in both an
empty frame and one with a src); the frame's load event comes at once only
for an empty frame (no src, or about:blank), not for src, srcdoc, object or
embed; and any MutationObserver, on any node of the document, leaves the
same lasting mark. So the watch stays, and with it most of what the guard
costs on pages that insert a lot (about a fifth of their insertion time).

**Tests.** tests/test_frame_guard_paths.py (new) plays each quick path as
an attack at Balanced and Strict: 22 ways to put a frame in, each read at
once through window[i], frames[i], frames[name], window[name],
getElementById(...).contentWindow and .contentDocument (132 frames), frames
in frames (built outside the frame's page, the parent's own appendChild,
document.write, by name), a frame swapped for another, taken out and put
back, a page lying about isConnected, firstElementChild, localName and
length, frames in shadow roots, an object frame. Its frames load a page:
the existing tests mostly use empty frames, whose load event (heard by the
guard inside the insertion) protects them whatever the hooks do; with the
hooks taken out, every way in of the new test fails when read through
window[i], frames[i] or a name. Three copies of the
new code with a mistake each (isConnected read from the page's own
property, the count after the call skipped, swaps not looked at) each fail
it. It passes on `main` too: the answers did not change. The existing frame
tests (test_frame_guard, test_frame_guard_review, test_runtime_paths,
test_fingerprint) pass unchanged.

Found while writing them, the same on `main`, not claimed: page code that
runs inside the very call that puts a frame in reads it before the guard
looks: a script in a fragment made by createContextualFragment put in with
the frame, or a custom element's connectedCallback put in with it. It is
the class of the known "script inside the same document.write"
(test_frame_guard_review.py); closing it needs the insertion split or the
custom element callbacks wrapped, left for a later version.

## 1.1.23, Dark Reader and Brave

A measurement with Speedometer 3.1 on a real computer: Brave with the
Dark Reader extension scores more than I.K.E. with Dark Reader, and I.K.E.
with the engine's own dark mode scores more than Brave with Dark Reader. The
question: does I.K.E.'s way of giving Dark Reader to a page cost more than
the extension's?

**How it was measured.** Ubuntu container, 4 shared cores, no GPU (another
session was running tests at the same time); PyQt 6.12 / Qt WebEngine 6.12
(Chromium 140) offscreen, and Chrome for Testing 153 headless. Local pages
only. Per frame: a page creates 30-40 same-origin frames one after the
other (each a small light page with 150 colour rules), as Speedometer does,
waits for each to load, changes its list (100 items added, completed,
removed) and removes it. CPU = the main thread of the page's renderer, read
from /proc; variants alternate round by round in one process. In Chrome,
I.K.E.'s own engine (darkmode.js with darkreader.js, the proxy in the page's
world, the site's settings) was loaded as an extension's content scripts,
run_at document_start, all_frames, as the Dark Reader extension declares
them; the extension itself could not be run here (the session's rules
refused loading a downloaded extension), so it was read instead
(darkreader/darkreader at v4.9.135).

**Per frame** (renderer CPU per frame, median of rounds):

| | off | Dark Reader | added |
|---|---|---|---|
| I.K.E. (Qt 6.12, Chromium 140), user script | 24.8 ms | 51.9 ms | +27 ms |
| Chrome 153, the same engine as an extension's content script | 19.5 / 20.3 ms | 45.5 / 50.5 ms | +26 / +30 ms |

So the way the script is given makes no difference. In Chrome: script
time 0.1 -> 19.2 ms per frame, style 4.0 -> 5.5 ms, the page's memory +0.26
MB per frame; of Dark Reader's time, 10 ms is the dark copy of the frame's
style sheet and 3 ms its start (`createThemeAndWatchForUpdates`); compiling
its 387 KB and the isolated world cost about 1 ms (a frame with the engine
installed but not started against one without: first script of the page
10.6 against 9.4 ms). darkreader-data.json never reaches a page: the site's
fix and hints are picked in Python (`ike/darkfixes.py`), as the extension's
background does, and each frame receives only the small result. Starting
Dark Reader after the frame's HTML is read (as the extension does, when the
background's answer arrives) and the plain engine without I.K.E.'s changes
cost the same per frame (within the noise).

**Speedometer** (six suites: TodoMVC JavaScript-ES5, ES5-Complex-DOM, React,
Svelte-Complex-DOM, Lit-Complex-DOM, jQuery; 5 iterations):

| | off | Dark Reader | engine's dark mode |
|---|---|---|---|
| I.K.E. (Qt 6.12), score | 11.96 | 6.81 (-43 %) | 11.76 |
| Chrome 153, score | 18.5 | 10.5 with I.K.E.'s engine as an extension (-43 %) | |

Dark Reader costs both browsers the same share. The owner's two results
follow from that and from the engine under each browser: Brave runs a
newer Chromium than Qt 6.12's 140 (here Chrome 153 scored 55 % more than
I.K.E. with no dark mode at all), so 0.57 of a higher score is still more
than 0.57 of I.K.E.'s, and less than I.K.E. with the engine's dark mode,
which costs almost nothing. The new Chromium cannot be had before Qt ships
it. Speedometer counts only the tests' steps, not the loading of each frame;
what it sees of Dark Reader is its work while the tests change the page
(new styles, new elements, the restyles that follow): in Chrome 1,578
against 832 ms of renderer CPU per iteration of the six suites; in the
profile, Dark Reader's JavaScript about 160 ms, the engine's own work
(style, layout) about 220 ms more, garbage collection 97 against 37 ms.

**What changed in 1.1.23**: a frame with no size (display:none, or one or
two pixels) waits for its first size before it starts Dark Reader
(`ike/resources/darkmode.js`, no change to Dark Reader's own engine). The
browser tells a frame its new size before drawing it, so a frame shown
later is dark from its first picture. Hidden frames, interleaved, 4 rounds
of 30: renderer CPU per frame 43.3 ms -> 13.8 ms (with dark mode off: 11.8);
frames of one pixel 56.0 -> 28.2 ms. `tests/test_darkreader_frames.py` in
I.K.E. itself: load time added by Dark Reader to a hidden frame 17.6 / 21.7
ms before, 0.2 / 1.9 ms after (to a shown frame, 20-26 ms both); a shown
frame dark as before, hidden frames not started, then dark once shown,
with the same colours as the frame shown from the start.

**Not done**: remembering the kinds of a page's CSS variables from one
load to the next (the owner said no); sharing the colour caches between
frames of one site (about 3 ms of a frame's 30, and only in its loading,
which Speedometer does not count); a V8 code cache for user scripts (Qt has
none, and compiling is about 1 ms per frame anyway).

## 1.1.23, the colours of selected text

The owner's decision of 2026-11-22, from the list above: patch
`selection-colours` in `tools/build-darkreader.py`. Dark Reader's user-agent
style had

    ::selection {
        background-color: var(--darkreader-background-0060d4, #004daa) !important;
        color: var(--darkreader-text-ffffff, #e8e6e3) !important;
    }

and now has `#004daa` and `#e8e6e3` there (for any theme: the colour that
was the fallback). The variable is written only when `color-variables` puts
it on `:root` (a site fix names it, or the same variable had another colour);
otherwise var() always gave its fallback, so the colour is the same. Why it
matters: a `::selection` that reads a variable is worked out again for every
element whose variables differ from its parent's, at every restyle (the
1.1.21 study counted 1,695 more style resolutions in one restyle of the Lit
page). That rule is the only text that changes: `tests/test_darkreader.py`
counts the patch among the kept families (now ten) and checks, in the
browser, the rule's text and the computed colours of selected text
(rgb(0, 77, 170) behind rgb(232, 230, 227), as before).

**Pixels.** Text selected on six pages (a plain page, a page whose every row
sets its own colour variables, a page with its own `::selection` colours, a
text area, Speedometer's Lit and JavaScript-ES5 complex pages), one browser
process per engine, screenshots 1000x800 compared pixel by pixel: five
identical, 0 pixels different; on the ES5 complex page 25 pixels differ in
the icons at the top right, where two runs of the same engine differ by
2,521 (Dark Reader's analysis of the icons finishes at a different moment);
the selected text is identical there too. Computed selection colours
identical on all six.

**Speed** (same container; one process per run; old and new engine in
turns):

| | before | after |
|---|---|---|
| one full restyle of the Lit page (fastest of 41), 3 runs | 45.5 / 42.6 / 39.6 ms | 34.7 / 35.0 / 34.2 ms |
| the same, median of 41 | 54.6 / 50.8 / 45.1 ms | 40.1 / 41.3 / 38.1 ms |
| Speedometer, Lit-Complex-DOM, mean of 10 | 128.6 / 139.5 / 141.7 ms | 105.1 / 112.8 / 114.5 ms |
| WebComponents-Complex-DOM | 219.1 / 235.4 / 215.0 ms | 170.6 / 176.0 / 204.7 ms |
| Charts-observable-plot | 200.0 / 203.8 / 188.1 ms | 182.4 / 185.0 / 195.0 ms |
| score of the three suites | 5.71 / 5.46 / 5.65 | 6.82 / 6.64 / 6.17 |

## 1.1.23, speed and fluidity

Two read-only studies of 2026-11-22 measured where the interface thread and
the page loads spend their time (the interface's own work at the start, new
tabs, changes of tab, page loads, rest and painting; then a comparison of
page loads with Falkon's way of injecting scripts). This section gives the
changes made from them and the numbers before and after, measured with the
studies' own probes.

**How it was measured.** A 4-core shared cloud container, no GPU, Python
3.13, PyQt 6.12 / Qt 6.12 from PyPI, Chromium 140; local pages only. Before =
`main` at b0f6eb2 (1.1.22 plus #115), after = this branch; the copies were
run one after the other for each scenario, alternating. "Offscreen" is Qt's
software screen of the tests; "OpenGL" is Xvfb at 1920×1080 with Mesa's
llvmpipe, where the page is an OpenGL surface as on a real graphics card (a
picture of the page is then a read-back). The interface-thread scenario
(`probe/scenario.py`: rest, 12 new tabs, page loads, 60 changes of tab with
10 tabs, repaints, hovering the toolbar) ran five times each, alternating
(the medians below); the others once or twice (both given when twice).
Function times come from timers wrapped around about 150 functions of
I.K.E. (they add 0.5–1 µs a call). The machine is shared: spreads of
10–20 % between runs are usual, and only differences larger than that are
read as changes.

| What | Before | After |
|---|---|---|
| Rest, new tab page in front, OpenGL: CPU of all processes / interface wake-ups a second | 5.6 % / 12.2 | **2.5 % / 3.0** (clock F1) |
| Rest, new tab page in front, offscreen (5 runs): CPU / wake-ups a second | 1.1 % / 4.2 | **0.4 % / 2.2** |
| Rest, one tab (5 runs): CPU / wake-ups a second | 1.5 % / 3.0 | **1.1 % / 0.8** |
| Rest, ten tabs (5 runs): CPU / wake-ups a second | 2.4 % / 2.9 | 2.0 % / 2.9 |
| Change of tab, offscreen (5 runs, 57 changes each) | 3.9 ms (CPU 3.3; the picture 1.6) | **2.1 ms (CPU 1.9; the picture 0)** |
| Change of tab, OpenGL (two runs) | 11.3 / 10.4 ms | **4.3 / 6.1 ms** (preview picture F2) |
| New tab, offscreen (5 runs): `add_tab` / page loaded | 11.1 ms / 96 ms | **7.5 ms** / 101 ms (within the spread: 76–117 ms both) |
| New tab, OpenGL (two runs): `add_tab` | 22.7 / 20.2 ms | **13.4 / 16.1 ms** |
| Heavy page (402 requests, 100 blocked), interface CPU (5 runs) | 447 ms [375–538] | **406 ms [389–427]** |
| of which the loading mark, the loading line, the line over the page, the address field under the "+N", the "+N" | 6.9, 15.2, 6.9, 13.7, 9.4 ms | **2.8, 12.0, 0.7, 7.4, 4.5 ms** |
| Slow page with 10 tabs, interface CPU for 3.3 s, effects on | 2.6 % (140 ms of Python) | **1.4 % (61 ms)** (mark F3/F7) |
| Four slow pages in the background | 2.3 % (122 ms of Python) | **1.7 % (65 ms)** |
| Animated page, 60 frames/s: interface CPU / I.K.E.'s Python each 5 s | 10.1 % / 23 ms | **5.3 % / 0 ms** (line out of the page F4) |
| Same, with the loading line shown | 8.1 % / 51 ms | 7.1 % / **23 ms** |
| Scrolling by script, 60 frames/s: Python each 5 s | 20 ms | **0 ms** |
| Hovering ten toolbar buttons (5 runs): interface CPU / window repaints | 115 ms / 115 | 109 ms (within the spread) / **0** |
| Whole window repainted / the tab bar / the toolbar (5 runs) | 7.1 / 0.97 / 3.9 ms | **4.7** / 1.1 / 4.0 ms (the last two within the spread) |
| Start, warm (9 starts, two series): navigation of the first page | 239 / 266 ms | **227 / 234 ms** |
| Start, warm: the new tab page loaded | 340 / 392 ms | **318 / 328 ms** |
| Start, cold: navigation of the first page | 277 / 263 ms | **234 / 230 ms** |
| New site (a new page process each load, 24 sites' scriptlets installed, real lists): article | 82.6 ms (DOMContentLoaded 72.7) | **60.9 ms (50.7)** (F-b2) |
| Same: page with 20 frames blocked by the lists | 580 ms | **383 ms** (F-b1) |
| Same: page with 10 frames of another site | 233 ms | **210 ms** |
| Same: page with 20 empty frames | 259 ms | 252 ms |

What was changed (the numbers of the studies in brackets):

- **F1, the new tab page's clock** (`newtab.html`): its text is written only
  when it changes, and the page wakes at the next minute (and when it is
  shown again) instead of every second.
- **F2, the preview picture of a tab** (`tabpreview.capture`, `window.py`):
  taken when the mouse comes to the tabs (a click follows 0.1 s later or
  more), and 0.6 s after a page of the tab in view finished loading; at a
  change of tab only for a tab with no picture or whose page changed since.
  Only the top of the page the card shows is scaled, a quick halving first,
  then the smooth step: the card's picture is the same as before within a
  few levels a colour (tests/test_fluidity.py).
- **F3/F7, the loading mark and the tab bar**: the twelve pictures of a tab's
  mark are drawn once; a tab that is not in the part being repainted is not
  drawn again (QTabBar draws every tab for any repaint): the mark repaints
  its own tab only. With few tabs this saves little; with ten tabs the
  slow-load row above.
- **F4, the line between the bars and the page** (`ChromeEdge`): the page
  area keeps its first row for it, so it is no longer under the page's
  frames; **the loading line** is a flat bar drawn from two pictures, shows
  only for loads longer than 0.15 s and never for `ike:` pages.
- **F5/F8/F13**: the "+N" and the ring of the shield at 30 pictures a second;
  the toolbar paints its own (flat) background where the widget style's
  window is one flat colour (Breeze, Fusion, Windows), so Qt stops a repaint
  of a button, the "+N" or the field's cursor at the toolbar: the window is
  no longer repainted behind a hover (row above). Its look is unchanged.
- **F6, the start**: the first view is made and its page asked for right
  after the tab bar and the page area, before the toolbar and the menus;
  the filter engine, the request interceptor and every page script are in
  place before that moment (tests/test_start_speed.py checks it, and that it
  comes before the bars). The theme's icons are kept per name, icon set and
  theme. Filling menus only when they open was not done: tests and other
  code read the menus' entries directly (the ☰ menu, the menu bar's, the
  extensions' switches), and the menus that change were already filled when
  they open.
- **Falkon comparison**: `// ==UserScript== @exclude chrome-error://*` at the
  end of the page scripts (fingerprint protection, media hook, cookie
  banners, list scriptlets, the video sites' scripts): the engine no longer
  runs them in the error page of a frame the shield blocked; `@include`
  limits a site's list scriptlets and (owner's OK of 2026-11-22) the video
  sites' scripts to their hosts and to empty frames, which take their
  parent's host; each script keeps its own check of the host. At the end of
  the script, so the line numbers an error's stack shows are the same. The
  engine's own probes (tests/test_script_limits.py) show where each runs, a
  control script shows the error page does run unlimited scripts, and the
  YouTube tests pass unchanged. History and site icons: WAL with
  synchronous=NORMAL (a backup checkpoints first; clearing checkpoints so
  nothing stays in the -wal file; a restore removes an old -wal file).
- **fingerprint.js, per-site values once per document**: looked at and left
  as it is. The site's key, its two SHA-256 and the Public Suffix lookup are
  already worked out once per document (once per run of the script); a
  frame is its own document, and sharing them with the page around it would
  mean handing them over through something the page can reach. Working out
  SHA-256's constant tables once per document instead of twice gave the
  same values and no measurable gain (0.24–0.41 ms before and after for a
  document's whole site setup, cold, in Node), so it was not kept.

What the faster paths cost: none of the changes touches a protection
decision; the request checks, the filter engine and the fingerprint
protection are as they were. The tab hover and the new tab's fade (Breeze
touches) add about 10 repaints of one tab when a tab is opened, and only
while the mouse moves over the tabs; nothing runs at rest (the rest rows).

## 1.1.23, Speedometer: the engine and the protection

The owner's question: Brave is much faster than I.K.E. on Speedometer 3.1,
both without dark mode (on a real computer, both at their strongest
protection: Brave 47.4, I.K.E. at Maximum 33.3). How much of it is I.K.E.?

**How it was measured.** A container with 4 shared cores and no GPU
(another session ran tests at the same time, so single runs vary by about
5 %); PyQt 6.12.1, Qt WebEngine 6.12.0 = Chromium 140.0.7339.264 (Qt's own
binary build, GCC); Chrome for Testing 153.0.8010.12 and 140.0.7339.207
(Google's builds), headless, software drawing like Qt's `offscreen`;
Speedometer 3.1 (`release/3.1`) served locally, the whole default set, 5
iterations a run, medians of 3 runs unless said; nine of the eleven default
lists. Scores here are about a third of a desktop's: only the comparisons
count.

| | Speedometer 3.1 score |
|---|---|
| A. Chrome 153 | 19.6 |
| A'. Chrome 140, Google's build | 18.7 (Chrome 153 in the same series: 19.2) |
| B. a bare Qt WebEngine window (Chromium 140, Qt's build) | 11.6 (12.3 in the Chrome 140 series) |
| C. B with I.K.E.'s switches, profile and settings, no scripts | 11.9 at Balanced, 11.9 at Maximum |
| D. I.K.E., shield Off | 11.8 |
| E. I.K.E., Balanced | 11.7 (11.5 in a series of 5) |
| F. I.K.E., Strict | 11.8 |
| G. I.K.E., Maximum | 11.2 (11.6 in a series of 5; without fingerprint.js 11.9) |

At Balanced, each piece switched off in turn (fingerprint.js, the video
scripts, the request checks, the cookie banners, the interface's timers and
effects, every script) moved the score by less than the spread of the runs
(10.9-11.4 against 11.7). At Maximum, each of the font allowlist, the font
masks, the text measure noise, the language rewrite and the screen/media
query answers alone did the same (10.9-11.9 against 11.2).

What the steps show:

- **A -> A' (version): 2-5 %.** **A' -> B (the build): 1.5 times.** The
  same Chromium 140 scores 18.7 as Google builds it and 12.3 as Qt ships it.
  Google builds Chrome with clang, ThinLTO and profile-guided optimisation;
  Qt's binary build uses GCC without them, and Arch's `qt6-webengine`, as
  far as its build file shows, is built through Qt's CMake with the
  distribution's GCC flags, also without them. The loss is in the synchronous part of the steps (JavaScript, DOM,
  style and layout inside the step: 908 ms against 1,512 ms for the whole
  set), more than in the part after it (448 against 671 ms): the same
  pattern seen between Brave and I.K.E. (NewsSite-Next 1.87 times
  there, 1.95 times between Chrome and the bare Qt window here). Nothing in
  I.K.E. can change it; it follows Qt's and Arch's builds.
- **B -> C (settings): none** (C scored slightly more than B, within the
  spread).
- **C -> D/E/F/G (I.K.E.'s work): a few percent.** Renderer time per
  iteration at Maximum: 3,780 ms, 3,484 ms without fingerprint.js (8 %,
  about half of it while frames load, which Speedometer does not score).
  Where it shows is the DOM-heavy pages: TodoMVC-jQuery at Maximum 269 ms,
  243 ms without fingerprint.js.

Counted during one iteration at Maximum (an instrumented copy): no wrapper
sits on the measuring APIs (offsetWidth, getBoundingClientRect,
getComputedStyle, getBBox, performance.now, Date are the engine's own);
NewsSite-Next makes 3,600 appendChild calls through the frame guard,
Perf-Dashboard 2,500 and 773 measureText, observable-plot 4,700
insertBefore/appendChild, jQuery 600 innerHTML writes of up to 23 KB each.
The costs found:

1. **The frame guard's watch while a page is built.** It is a
   MutationObserver on the document, disconnected once the page is built;
   the engine, though, keeps the document marked as watched for good, and
   every later insertion into it pays for that mark (measured in two frames
   of one page, one watched once and disconnected: +17-27 % for innerHTML,
   appendChild and text nodes, the same after garbage collection). jQuery
   without the watch: 239 ms against 267. It is what protects a frame
   written in a page's HTML before the page's next script reads it through
   window[i]; nothing else runs at that moment, so it stays.
2. **The guard read every HTML string written through innerHTML** (a
   search for a frame tag: 14 microseconds for 23 KB, 9 ms per jQuery
   iteration). Fixed: with no frame in the window the guard's check has
   nothing to look at, so the string is not searched; a moved node is not
   looked at either when the window had no frame before the call (only the
   count can tell of a new frame then). jQuery at Balanced 284 -> 261 ms,
   renderer time 348 -> 316 ms per iteration (6 runs each); the search is
   gone from the profile.
3. **At Maximum, calls that ask for no language were rewritten to en-US**,
   which sends the engine down its slow way even when it already speaks
   en-US (the global level Maximum starts it with --lang=en-US). Fixed: once
   per kind, the engine's own objects made with no language and with en-US
   are compared (every resolved option the same, the language exactly
   en-US); when they agree, such a call is handed on as it is. Per call:
   localeCompare 600 -> 75 ns (15 without the protection), Number
   toLocaleString 850 -> 330 ns, Date toLocaleDateString 1,300 -> 700 ns,
   toLocaleUpperCase 540 -> 50 ns, new Intl.NumberFormat 17.4 -> 14.6
   microseconds. PluralRules resolves en-US to "en" when it is written and
   keeps the rewrite; so do a site at Maximum while the browser is not.
4. Smaller ones left as they are: an appendChild of an element through the
   guard costs about 0.5 microseconds more; measureText with its width at
   Strict and above about 1.4 microseconds more (the noise needs the text
   and the font of each measure).

tests/test_runtime_paths.py plays the ways a frame can still come in on the
quick paths (written HTML, a subtree with a frame inside, a frame taken
away behind the guard's back and another added, nodes moved with and
without frames, a shadow root) at Balanced and Strict, and asks dates,
numbers, sorting, case and every Intl kind with nothing, undefined, an empty
list and languages the engine does not have, at the global Maximum and with
one site at Maximum: every answer must be the one 'en-US' gives. The same
tests pass on 1.1.22's fingerprint.js: the answers did not change.

## 1.1.22, start and speed

The aim: a faster start, above all, with every feature and every
protection as it was. The shields, the filter rules and the fingerprint
script are in place before the first page, as before; nothing a page can
observe changed (no injected script was touched; the Public Suffix List
codes fingerprint.js receives are the same string).

**How it was measured.** The Arch container (Python 3.14, PyQt 6.12,
qt6-webengine 6.140, 4 shared cores, no GPU, `offscreen`; another session
was running tests in the same container, so the spreads are wide). Before
= branch `fix/1.1.22` (3af6015), after = branch `perf/1.1.22`; the two
copies alternate start by start (ABAB). The nine default lists that could
be had (EasyList, EasyPrivacy, uBlock filters, quick fixes, privacy,
badware, unbreak, cookie notices, EasyList Cookie List; URLhaus and
EasyList Italy were missing), so the filter engine has its real size.
"Cold" = a new profile (the engine and the other caches built at that
start); "warm" = the same profile started again (the usual start). Times
from starting the process to the first paint of the window and to the
new tab page loaded (`loadFinished`); main-thread CPU from
`/proc/self/task/<pid>/schedstat`; PSS from `smaps_rollup` 3 s after the
page. Two series of 11 starts of each kind (the second one an hour later,
with the container quieter); medians, interquartile range in brackets.

| Start | series 1: before → after | series 2: before → after | change |
|---|---|---|---|
| warm, to the first window | 480 [446–505] → 431 [399–453] ms | 466 [431–506] → 417 [390–434] ms | **-49 / -49 ms (-10 %)** |
| warm, to the first page | 592 [563–633] → 546 [507–567] ms | 573 [545–625] → 535 [495–557] ms | **-46 / -38 ms (-7 %)** |
| warm, CPU of the interface thread to the window | 350 [337–376] → 316 [292–349] ms | 341 [332–395] → 310 [296–320] ms | -34 / -31 ms |
| warm, CPU of the interface thread to the page | 403 [390–431] → 368 [341–402] ms | 390 [377–446] → 358 [338–375] ms | -35 / -32 ms |
| cold, to the first window | 640 [601–669] → 586 [553–651] ms | 652 [608–693] → 563 [534–590] ms | **-54 / -89 ms (-8 / -14 %)** |
| cold, to the first page | 757 [707–796] → 707 [663–774] ms | 760 [706–826] → 684 [639–709] ms | **-50 / -76 ms (-7 / -10 %)** |
| cold, CPU of the interface thread to the window | 364 [353–401] → 384 [350–420] ms | 379 [371–416] → 362 [333–392] ms | within the spread |
| memory (PSS) of the main process, warm | 157.6 [157.1–177.5] → 154.2 [153.4–156.7] MB | 169.8 [156.7–208.2] → 155.1 [152.7–201.6] MB | within the spread |
| memory (PSS) of the main process, cold | 177.8 [175.5–179.8] → 174.3 [173.8–177.4] MB | 207.5 [177.3–236.8] → 174.6 [172.4–186.1] MB | within the spread |
| memory (PSS) of the renderers, warm | 86.4 [80.0–114.4] → 81.7 [78.6–88.3] MB | 121.4 [90.3–125.9] → 89.9 [88.2–126.0] MB | within the spread |
| Python modules loaded up to the first page (`-X importtime`, one warm start each) | 248 → 224 | | -24 |

PSS divides a shared page among the processes that use it, and other
browsers of another session were running in the container at times: the
memory figures jump by 30–50 MB from start to start and show no change
beyond that (series 1: about -3 MB for the main process, fewer modules
loaded).

**Where the time went (warm, before).** A timeline of one copy with time
stamps at each step (5 starts): Python and `ike_boot.py` 22 ms; PyQt6 and
Qt WebEngine's libraries 65–75 ms; the command line 22 ms (argparse and,
on Python 3.14, the `_colorize`, `dataclasses`, `inspect` and `ast` it
brings in); the first web profile 105–135 ms (Qt WebEngine starting
Chromium); the profile's scripts 22 ms, 19 of them the Public Suffix
List's codes for fingerprint.js; the window 70–85 ms; the new tab page in
its renderer 100–115 ms after the window. The cold start adds the PSL
parse (about 28 ms, once per list update) and the filter engine built in
its thread while the interface is set up: its Python parts (reading,
`!#if` branches, the generichide fix, the scriptlet index, about 150 ms)
take turns with the interface for Python's lock. What is left is mostly
Qt and Chromium (the profile, the renderer, the widgets): no switch or
flag was used to change it.

**What changed, and what each part gained** (each part in a fresh process
with the caches of an earlier start, before and after alternating; median
of 15 [interquartile range] unless said otherwise):

| Change | before | after | test |
|---|---|---|---|
| The PSL codes for fingerprint.js kept next to the parsed list (`pslcodes-1-<size>-<time>.txt` in the cache, same size and time of the system's file as the parsed list, a format number in the name); a new or damaged copy is worked out again | 20.5 ms [20.3–22.2] (list read + codes) | 2.1 ms [2.0–2.2] | `test_psl_codes_are_kept_and_are_the_same`, `test_psl_codes_follow_a_new_list`, `test_psl_codes_without_the_system_list` |
| The usual start (no option on the command line) reads it without argparse, the same answer; the error handler imports traceback only when there is an error to write | 17.4 ms [16.3–17.9] | 0.0 ms | `test_the_command_line_reads_as_before`, `test_the_usual_start_does_not_load_argparse`, `test_an_error_in_a_handler_does_not_end_the_browser` (test_security) |
| The engine's build thread is I.K.E.'s own (one thread kept for every build, as before) instead of concurrent.futures, which loads logging and with it traceback; a build running at exit still finishes | `prepare()` 4.2 ms [4.1–6.2] (9 runs) | 1.5 ms [1.3–1.6] (9 runs) | `test_the_start_loads_no_module_it_does_not_need`, `test_the_build_thread_runs_every_build_and_hands_back_results`, `test_a_build_running_at_exit_finishes_first` |
| A build from the lists reads each list once and chooses its `!#if` branches once (twice for the scriptlets until 1.1.21); the generichide fix searches from one `@@` to the next; the scriptlet index splits only the lines with `+js(` and most arguments at once | an engine rebuilt in the running browser (as after a list update), 7 starts × 5 rebuilds: 234.5 ms (225–258), longest stall of the interface 17.2 ms (13.5–18.6) | 174.5 ms (171–188), stall 7.7 ms (6.1–14.6) | `test_sanitize_changes_the_same_lines_as_before`, `test_sanitize_takes_less_time_than_before`, `test_scriptlet_arguments_split_as_before`, `test_scriptlet_rules_are_read_as_before`, `test_scriptlet_index_takes_less_time_than_before`, `test_a_build_reads_each_list_once_and_gives_the_same_engine` |

The first engine from its cache (warm) takes the same time: 17.0 ms when
built in the interface's own thread, before and after; the time `load()`
waits for it at start was within the spread (26.0 [25.7–28.4] before,
29.1 [27.9–32.8] after in one series of 15; 26.4 against 19.8 ms in a
series of 11, concurrent.futures against the new thread on their own).

Every change gives the same result as before, checked three ways: the old
code (kept in tests/test_start_speed.py) against the new on thousands of
random texts with every line separator Python knows; on the nine real
lists, the old and the new copy give the same generichide fix, the same
scriptlet index and the same engine file, byte for byte (SHA-1 compared);
and the PSL codes read back are compared with the ones worked out.

**The injected scripts on a page** (unchanged by this work; measured to
know their cost). A small local page (200 paragraphs), 12 loads per start
after 2 warm-up loads, 7 starts of each copy alternating; "first" = when
the page's first script runs (`performance.now()` in `<head>`), CPU = the
renderers' main threads from the navigation to 300 ms after the load;
medians, the range of the 7 starts in brackets:

| Page | first script, before / after | renderer CPU, before / after |
|---|---|---|
| shields off for the site | 13.5 (11.5–15.6) / 13.4 (12.4–16.0) ms | 20.5 (18.3–25.9) / 20.0 (19.2–25.5) ms |
| Balanced (default) | 16.4 (13.9–19.7) / 16.6 (14.3–19.7) ms | 24.8 (22.1–29.2) / 24.3 (22.2–28.7) ms |
| Strict, before the font check has answered (all 714 names masked) | 37.2 (35.3–43.5) / 39.2 (33.9–45.6) ms | 45.5 (45.0–50.3) / 46.6 (42.6–54.2) ms |
| Balanced with the page dark mode (Dark Reader) | 22.7 (22.3–25.5) / 25.5 (23.0–27.3) ms | 48.7 (44.2–49.9) / 47.9 (46.8–55.8) ms |

So, against the shields off for the site, Balanced costs about 3 ms
before a page's own code and about 4 ms of renderer CPU per page. Strict,
until the font check has answered (15 s after the first start, then
remembered), costs about 21 ms more than Balanced on both counts, mostly
the masks of the font list; Dark Reader adds about 6 ms before the page's
code and 24 ms of CPU to Balanced. No change was made there: each would
change what a page can observe or how soon a protection applies.

**Looked at and left as it was.** The start's timers were already late
(update check at 1.5 s and then once every 24 hours, the engines' icons at
4 s, the health confirmation at 20 s, the font check at 15 s and only when
its answer is not known); Dark Reader is read only when dark mode is on;
the session's tabs are restored lazily; the PSL parse was already cached
(1.1.20). The font database (`QFontDatabase.families()`, about 9 ms) is
needed by the interface's own text anyway; the font check's answer must
be there before the first page. PyQt6 creates its enum classes the first
time they are used (about 280 at start): the cost moves, it does not go.

**Tests.** `ruff check .` clean. The whole suite on this branch: locally
(Python 3.13, PyQt 6.12 from PyPI) 932 passed, 19 skipped, 2 failed; in the
Arch container (Python 3.14, Arch's Qt) 929 passed, 21 skipped, 3 failed.
None of the failures comes from this work:
`test_the_default_lists_in_the_bundled_engine` needs the engine's parse
report, which the engine library used here (built on 2026-11-20) does not
have (it fails on `fix/1.1.22` as well); `test_a_check_does_not_wait_for_other_python_threads`
is a timing test of the engine alone that failed while both suites ran at
the same time, on `fix/1.1.22` as well, and passes on a quiet machine
(test_adblock.py: 4 passed with both copies in the container and
locally); `test_withdrawn_list_is_named_only_where_it_is_removed` asks
git for the files, and the container's copy is not a git checkout (it
passes locally). tests/test_start_speed.py: 14 passed locally and in the
container.

## 1.1.21, Dark Reader: only the measured changes

The owner's rule (2026-11-21): a change to Dark Reader stays only if it
gives a measurable gain; otherwise the engine stays closer to Dark Reader's
own, and a new engine has fewer texts to match in the automatic update.

**How it was measured.** Inside the real I.K.E. (empty profile, offscreen,
dark mode on with Dark Reader), on the Arch container (Python 3.14, PyQt
6.12, 4 shared cores, no GPU). Two builds alternate in one browser process
(ABBA order, 1 warm-up and 8 measured rounds); between them only the engine
text changes, and a marker read back after every load proves which one
ran. The time is the CPU time of the page's renderer main thread (where
Dark Reader, style and layout run), from the navigation to 1 s after the
page settled; medians of the 8 rounds. Spread = the larger interquartile
range of the two builds. Measurable = a gain larger than the spread, in
two independent runs. Each page is a synthetic worst case for one change
(built from its own description) plus Speedometer 3's
TodoMVC-Lit-Complex-DOM with its three steps; an ordinary article page is
measured with a tiny page loaded before each load.

**Family by family** (all 53 changes against all but one family; the
family's own target page; CPU ms, run 1 / run 2 [/ run 3]):

| family | changes | page | with | without | spread | verdict |
|---|---|---|---|---|---|---|
| color-variables | 3 | many new colours | 919 / 871 | 2895 / 2888 | 115 / 68 | **kept** (-68 %; ordinary page -15 / -20 %) |
| style-groups | 12 | repeated SVG icons | 352 / 331 | 2393 / 2354 | 210 / 115 | **kept** (-85 %) |
| shadow-texts | 1 | 200 shadow roots | 267 / 235 | 353 / 332 | 80 / 62 | **kept** (-24 / -29 %) |
| shadow-host-walk | 1 | 42,000 elements | 1775 / 1582 / 1471 | 1874 / 1798 / 1660 | 228 / 216 / 91 | **kept** (-12 / -11 % in runs 2 and 3) |
| dark-copy | 5 | 200 shadow roots | 274 / 218 / 254 | 325 / 254 / 272 | 58 / 30 / 49 | **kept**, second step (above the spread in 1 of 3 runs here) |
| declarations-modifiable | 6 | 2,000 CSS rules | 733 / 689 / 710 | 812 / 746 / 756 | 88 / 88 / 54 | **kept**, second step (-6 to -10 %, below the spread here) |
| variables-none | 1 | 2,000 CSS rules | 784 / 707 / 707 | 845 / 773 / 751 | 101 / 69 / 67 | **kept**, second step (below the spread here) |
| style-moves | 2 | moved style elements | 920 / 769 / 795 | 904 / 921 / 829 | 76 / 147 / 86 | **kept**, third step (above the spread in 1 of 3 runs here) |
| svg-sizes | 9 | SVG chart | 648 / 720 / 705 | 679 / 731 / 761 | 71 / 43 / 31 | dropped (above the spread in 1 of 3 runs) |
| shadow-styles-once | 1 | 200 shadow roots | 261 / 284 / 270 | 300 / 291 / 292 | 113 / 51 / 37 | **kept**, second step (with dark-copy) |
| var-rule-same-text | 2 | undefined variables; Lit-Complex | 358 / 329 / 351; 560 / 595 / 595 | 410 / 372 / 388; 592 / 600 / 592 | 87 / 55 / 53; 120 / 80 / 88 | dropped (its code path was never reached) |
| adopted-vars-first | 1 | Lit-like variables; Lit-Complex | 287 / 320; 623 / 646 | 268 / 294; 668 / 581 | 28 / 55; 76 / 92 | dropped |
| adopted-once | 4 | adopted sheets | 204 / 222 | 215 / 224 | 37 / 42 | dropped |
| one-text | 3 | 2,000 CSS rules | 782 / 658 | 718 / 685 | 83 / 42 | dropped |
| image-selectors | 1 | background images | 479 / 440 | 483 / 442 | 31 / 62 | dropped |
| inline-style-key | 1 | inline colours | 1866 / 1903 | 1873 / 1861 | 157 / 60 | dropped |

Runtime dependencies were checked: dark-copy needs style-groups,
var-rule-same-text needs one-text, shadow-styles-once needs shadow-texts;
no kept family needs a dropped one. Every load of every build gave the same computed colours
(colour, background, borders, fill, stroke, background image, shadows,
outline, decoration and stop colours of every element of the document and
of every shadow root).

**First step: the four families alone against the full build** (1.1.20's
53 changes = A, the 17 changes of color-variables, style-groups,
shadow-texts and shadow-host-walk = B; CPU ms; + means B is slower):

| page | run 1 | run 2 | run 3 | run 4 | reading |
|---|---|---|---|---|---|
| ordinary article (separate) | 102 / 98 (-4 %); 109 / 101 (-8 %) | | | | not slower |
| many new colours (color-variables) | 899 / 824 (-9 %) | 937 / 890 (-5 %) | | | not slower |
| 42,000 elements (shadow-host-walk) | 1561 / 1399 (-12 %) | 1475 / 1397 (-6 %) | | | not slower |
| repeated SVG icons (style-groups) | 414 / 397 (-4 %) | 325 / 373 (+13 %, spread 31) | 368 / 376 (+2 %) | 355 / 395 (+10 %, spread 32) | slower in 2 of 4 runs |
| 200 shadow roots (shadow-texts) | 273 / 367 (+25 %, spread 47) | 342 / 343 (0 %) | 252 / 329 (+23 %, spread 30) | 224 / 324 (+31 %, spread 55) | **slower in 3 of 4 runs** |
| 2,000 CSS rules | 710 / 869 (+18 %, spread 79) | | 758 / 881 (+14 %, spread 69) | 702 / 905 (+22 %, spread 42) | **slower in 3 of 3 runs** |
| Speedometer TodoMVC-Lit-Complex-DOM | 619 / 621 (0 %) | 565 / 608 (+7 %, spread 38) | 572 / 585 (+2 %) | 528 / 590 (+11 %, spread 29) | slower in 2 of 4 runs |
| undefined variables (Lit pattern) | 370 / 468 (+21 %, spread 70) | | 360 / 334 (-8 %) | 342 / 375 (+9 %) | slower in 1 of 3 runs |
| other pages (moved styles, SVG chart, adopted sheets, background images, inline colours, Lit-like variables) | -2 to +13 %, all within the spread | | | | not slower |

Colours: identical in every load of these runs and the ones below (no error
in Dark Reader's world, every load settled and ran the build it claimed);
the only difference between loads is how many of Dark Reader's own style elements
exist at the instant of the reading (11 or 12 on the icons page, 30 or 31
on Lit-Complex), in both builds alike.

**Second step: each dropped family added back to the four** (the four +
the family = A, the four = B, two runs each), where the spread is smaller
than against the full build:

| added to the reduced build | page | run 1 | run 2 | reading |
|---|---|---|---|---|
| dark-copy + shadow-styles-once | 200 shadow roots | -24 % (spread 26 ms) | -18 % (spread 34 ms) | measurable together |
| dark-copy | 200 shadow roots | -10 % (below) | -22 % (above) | 1 of 2 |
| shadow-styles-once | 200 shadow roots | -6 % | -1.5 % | no |
| declarations-modifiable + variables-none | 2,000 CSS rules | -12.5 % | -11 % | measurable together |
| declarations-modifiable | 2,000 CSS rules | -6 % (spread 29 ms) | -9 % (spread 27 ms) | measurable alone |
| variables-none | 2,000 CSS rules | -7 % (spread 40 ms) | -7 % (spread 40 ms) | measurable alone |
| one-text | 2,000 CSS rules | -2 % | +8 % | no |
| style-moves | repeated SVG icons | -7 % (below) | -9 % (above) | 1 of 2 (see the third step) |
| adopted-vars-first + adopted-once | Lit-Complex | +3 % | -4 % | no |
| all twelve | shadow roots / CSS rules / icons / Lit-Complex | -29 / -19 / -15 / +2 % | -21 / -18 / -9 / -2 % | shadow roots and CSS rules measurable |

So, by the same rule, `dark-copy` with `shadow-styles-once`,
`declarations-modifiable` and `variables-none` give a measurable gain on
their own worst-case pages once the bigger changes are gone: measured
against the full build their gain was hidden in its larger spread. They
were kept too (decision of 2026-11-21).

**Third step: the eight families against the full build, then what is
left** (1.1.20's 53 changes = A, the 30 changes of the eight families = B;
CPU ms, + means B is slower; two runs, icons and Lit-Complex four):

| page | run 1 | run 2 | run 3 | run 4 |
|---|---|---|---|---|
| ordinary article (separate) | 99 / 100 (+1 %) | 98 / 99 (+1 %) | | |
| 200 shadow roots | 293 / 321 (+9 %) | 236 / 238 (+1 %) | | |
| 2,000 CSS rules | 696 / 754 (+8 %) | 765 / 792 (+4 %) | | |
| many new colours | 840 / 855 (+2 %) | 942 / 909 (-4 %) | | |
| 42,000 elements | 1470 / 1457 (-1 %) | 1505 / 1466 (-3 %) | | |
| repeated SVG icons | 351 / 360 (+2 %) | 377 / 413 (+9 %) | 319 / 369 (+14 %, spread 23) | 355 / 380 (+7 %) |
| Speedometer TodoMVC-Lit-Complex-DOM | 614 / 642 (+4 %) | 548 / 589 (+7 %, spread 36) | 632 / 644 (+2 %) | 620 / 692 (+10 %, spread 72) |

No page was slower beyond the spread in two runs, but the icons page and
Lit-Complex were slower by a few per cent in most rounds. Added back to the
eight families (the eight + X = A, the eight = B, two runs):

| added to the eight | page | run 1 | run 2 | reading |
|---|---|---|---|---|
| style-moves | repeated SVG icons | -12 % (spread 31 ms) | -13 % (spread 33 ms) | measurable: kept |
| style-moves | Lit-Complex | -5 % | -6 % | below the spread |
| adopted-once + adopted-vars-first | Lit-Complex | -1 % | -8 % | below the spread |

**Result.** Kept: 32 changes in 9 families (color-variables, style-groups,
shadow-texts, shadow-host-walk, dark-copy, shadow-styles-once,
declarations-modifiable with its three guards, variables-none,
style-moves), exactly as in 1.1.20. Dropped: 21 changes in 7 families
(svg-sizes, adopted-once, adopted-vars-first, one-text,
var-rule-same-text, image-selectors, inline-style-key).

**The shipped build (nine families) against the full build** (1.1.20's 53
changes = A, the 32 kept = B; CPU ms; + means B is slower; two runs):

| page | run 1 | run 2 | reading |
|---|---|---|---|
| ordinary article (separate) | 95 / 103 (+7 %, spread 14) | 96 / 94 (-2 %) | not slower |
| 200 shadow roots | 298 / 336 (+11 %, spread 101) | 241 / 228 (-6 %) | not slower |
| 2,000 CSS rules | 695 / 709 (+2 %) | 739 / 750 (+1 %) | not slower |
| repeated SVG icons | 328 / 348 (+6 %, spread 47) | 377 / 369 (-2 %) | not slower |
| many new colours | 820 / 817 (0 %) | 936 / 870 (-7 %) | not slower |
| 42,000 elements | 1435 / 1408 (-2 %) | 1331 / 1327 (0 %) | not slower |
| Speedometer TodoMVC-Lit-Complex-DOM | 637 / 645 (+1 %) | 526 / 539 (+2 %) | not slower |

No page is slower beyond the spread in either run. Colours: one colour
fingerprint per page across all 1,746 loads of this work (every build,
every page); no error in Dark Reader's world, every load settled and ran
the build it claimed.

## 1.1.19, page dark mode with Dark Reader

(Some of the changes named in this section and in the 1.1.18 one were
removed in 1.1.21, see above.)

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
measured on a real computer.

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
  browser on a real computer cannot come from them; the engine's Chromium
  version and its graphics path are the other candidates, to be checked on
  that computer (chrome://gpu in I.K.E., `pacman -Q qt6-webengine`).
- On a real computer (2026-11-20; I.K.E. 1.1.17 as installed,
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
  the top page). (Measured again for 1.1.20: about 2.5 ms per new frame, of
  which 1.6 ms is the engine building the WebGL interfaces the first time
  the script touches them; wrapping WebGL later would let a page keep an
  unwrapped function, so it stays as it is.) At Strict and Maximum the font masks cost much more until
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
  versions, they do not say how fast I.K.E. is on a real computer.
