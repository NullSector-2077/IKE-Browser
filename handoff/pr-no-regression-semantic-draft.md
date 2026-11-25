## Nothing gets worse: judged by what protects; needed changes pass only on narrow, confirmed evidence

The owner's request (2026-11-24): "Nothing gets worse" compared raw values between `main` and the candidate. On pull request #148 (audio noise raised from ±0.01 % to ±0.1 % per rendered sample, a **stronger** protection) it reported `fingerprint/<level>/audio` as worse only because the number changed, so a person had to add allowlist entries. The owner's principle: *a change necessary for I.K.E. to work correctly and for its protections to keep working is approved by the chain itself*. An independent adversarial review of the first version (7ac6591) asked for much narrower evidence and stronger checks, with the guiding principle **"when in doubt, worse"**. This PR does both: the #148 case passes with no allowlist, and every weakening tried, including adversarial ones, fails.

**Round 4** (this push): rebased on `main` f51ba83, and every weakening of the fourth review now fails (27 weakened copies, each failing; the stronger audio passes), with 20 of 20 main-vs-main checks clean and 0 of 240 rewrite pairs with a "worse".

### Round 7: new code runs only after the old and cannot stop it; the matrix measures the change's own values

Rebased by the coordinator on current main (0e1e18d). Fable's third review of the guard reproduced forms that round 6 accepted:
- **Implicit exits.** A throw without `throw` stopped the old code after it, so the protection never installed: `({}).a.b`, a call of no function, a new function that throws, a recursion, `new Array(-1)`, `1n + 1`, a `let` read too early. The same throw gated on an axis value the matrix did not sample also escaped measurement.
- **Old try blocks.** A new statement inside an old try block was swallowed by the old catch and skipped the rest of the block.
- **Directive demotion.** `0;` before `'use strict'` turned strict mode off.
- **Built-in tampering.** `wrap(String.prototype, 'charCodeAt', …)` reached the old script's hashing.
- **Old code run again.** `install(window)` was called a second time.
- **Unsampled values.** Equality gates compared an axis with a value no session had (6 cores, Europe/Berlin, a width of 1600).

**Guard** (`tools/fix-guard.py`):
- **Position.** New code comes after the last old statement of its block, never before or between old statements, never ahead of a directive.
- **Form.** There it is a declaration that cannot throw (a new function; a `var` given a literal, a function, a list or object of such, or a covered read compared with a literal) or `try { … } catch (e) {}` with an empty catch.
- **Built-ins.** No wrap or definition on the language's own objects or their prototypes (`BUILTINS`).
- **Old functions.** New code calls or references only the pure helpers and the property helpers of the old script (`PAGE_HELPERS`). `install`, `maskFonts`, `farble` and the rest are a person's to call.
- **Measured reads.** A measured value counts as measured only when compared with a literal, negated, or used as a test. The touch points may be compared only with 0–5.
- **Rename opening (Fable's suggestion).** A protected property may be wrapped again only as an `_equal` copy of an old call with exactly the names in `tools/engine-renames.json` changed. That list is tier B, written by AUTOMAT's recipes, and empty today. The copy's other names must bind as in the original. No body edit is allowed. Old statements cannot be removed anyway, so the old name is kept.
- **Workflow and protections.** `autofix.yml` copies `engine-renames.json` beside the guard, and the file is in `FORBIDDEN_FILES` and `NOT_RECENT`.

**Probe** (`tools/env-axes.py`, `run_matrix`):
- **Fuzz sessions.** Each run adds 8 sessions at random off-grid values, seeded per run and the same on both sides: widths 1024–5120, scale 1–3 in steps of 0.05, zoom 50–200 %, cores 1–64, memory 2–64 GB.
- **Derived sessions.** `check` reads the candidate's new conditions through the guard's parser (`axis_literals`): `screen.width === 1600`, `navigator.hardwareConcurrency > 6`, time zones, languages, and `matchMedia` widths and resolutions. For each value and its neighbours (1599/1600/1601; ±0.05 for dpr) it adds sessions at every level, at zoom 100 %. The same values join the pairs, and both sides measure them. More than 24 such values make the run not verified.

**Measured** (main 8176b12's tree, final tool):
- Weakened copies, 46 in all: 34 fail by measurement with 0 errors. These include the effective gated re-wraps H1–H3 (44, 11, 13 matrix rows), I2 Berlin (14), I3 width 1600 (4), J1 the implicit throw (572 rows), J2 the throw gated on width 1600 (41, in the sessions derived at 1600), J4 charCodeAt (95) and J5 install again (1). Six pass: the stronger audio; the no-op copies G1–G3 and I1; and J3 (`0;` before 'use strict'), which changes nothing a page can see. The guard refuses every one of them (table below; the 22 copies whose verdict involves the matrix were re-run with the final tool, and the other 24 fail by the first machine's probe, unchanged).
- Fable's twelve forms of round 7, as unit tests: all refused by the guard (`test_round_seven_*`).
- Main vs main: **6 of 6 pass** (0 worse, 0 errors, 364–372 s).
- Rewrite pairs: **1 of 240 worse**. It came from round 4's hidden-extensions list on the first machine (fewer names changed in the sessions' mean: 4.62 against 3.12), a chance inside that rule's documented budget, not the matrix. The 480 pairs of rounds 5 and 6 gave 0. All 16 snapshots have the matrix's 64 sessions and 0 errors. Two identical snapshots give the same 1,280 matrix values: the zoom is now emulated, not the browser's own, which had raced the page's first reads.
- Runtime: about 365 s per check, two at once on 4 cores (round 6: 350 s); the matrix has 64 sessions (pairs, corners, 8 off-grid) plus 12 per derived value.
- **Honest forms** (Fable's 15 additive AI-style fixes):
  - written where round 7 puts new code (at the end, what runs in try): **10 pass**. Round 6 passed 11; the wrap of a `Date` method is now refused as a built-in;
  - in the middle of the script, as the review wrote them: 0 pass;
  - the six uncovered environment reads: 0 pass.
- **History:** this guard refuses 33/33 added-only parts of main's fingerprint.js commits (main's 28, round 5's 31).
- **Rename opening:** none of main's fingerprint.js commits was an engine rename, so it would have allowed 0 past fixes. It is for the engine's next renames.
- **No-op copies:**
  - Fable's G1–G3, written before `install(window)`, leak nothing, because install's wrap stays outer.
  - I1 (`navigator.hardwareConcurrency === 6` at the end) reads the already-disguised value, so its condition is never true.

  These pass the measurement, correctly, and the guard refuses them. Their effective forms fail: H1–H3, I3 (`innerWidth === 1600`), I2 (Europe/Berlin) and J2 (the throw gated on width 1600).

**Proposed extension point in fingerprint.js** (tier A; for a separate Claude PR if wanted). One fixed hook placed after `install(window);` in the IIFE:

```js
  // the place of new code (tools/fix-guard.py): after the protection is installed, its errors kept to itself
  function extend() {
  }
  try { extend(); } catch (e) {}
```

The guard already accepts new code only after the last old statement, in try. With this hook it could later be narrowed so that new code may only be added inside `extend()`.

| Copy | Verdict | Rows worse | of them in the matrix |
|---|---|---|---|
| H1dpr | **fail** | 44 | 44 |
| H2wide | **fail** | 11 | 11 |
| H3coarse | **fail** | 13 | 13 |
| I2berlin | **fail** | 14 | 14 |
| I3wide1600 | **fail** | 4 | 4 |
| J1throw | **fail** | 572 | 248 |
| J2gated1600 | **fail** | 41 | 41 |
| J4charcode | **fail** | 95 | 0 |
| J5install2 | **fail** | 1 | 0 |
| F2 | **fail** | 51 | 28 |
| G1dpr | **pass** | 0 | 0 |
| G2wide | **pass** | 0 | 0 |
| G3coarse | **pass** | 0 | 0 |
| I1six | **pass** | 0 | 0 |
| J3directive | **pass** | 0 | 0 |
| audio-stronger | **pass** | 0 | 0 |
| F1 | **fail** | 70 | 0 |
| F3 | **fail** | 12 | 0 |
| F4 | **fail** | 4 | 0 |
| audio-off | **fail** | 114 | 46 |
| audio-tenth | **fail** | 6 | 0 |
| gGL2 | **fail** | 21 | 0 |
| gHidden | **fail** | 7 | 0 |
| gInstall | **fail** | 21 | 0 |
| gNofp | **fail** | 564 | 243 |
| gSiteOf | **fail** | 90 | 0 |
| vA | **fail** | 51 | 0 |
| vA1 | **fail** | 21 | 0 |
| vA2 | **fail** | 9 | 0 |
| vA3 | **fail** | 9 | 0 |
| vA4 | **fail** | 3 | 0 |
| vA5 | **fail** | 9 | 0 |
| vB | **fail** | 20 | 0 |
| vC | **fail** | 63 | 0 |
| vD | **fail** | 58 | 0 |
| vE | **fail** | 90 | 0 |
| vL | **fail** | 13 | 0 |
| vM | **fail** | 55 | 35 |
| vS | **fail** | 18 | 0 |
| wk-env | **fail** | 19 | 13 |

### Round 6: page scripts read by their syntax tree; the users' configurations measured up front

Rebased by the coordinator on `main` 88cf758.

Fable's second review of 7cf5b7a found new-line forms that round 5's guard rules on lines did not see:
- destructuring `[k] = [n]`, a loop's target, a second declarator, a parameter declared again;
- `Object.defineProperty`, `Reflect.set` and `Object.assign` on old objects;
- `document.URL`, `baseURI`, `visibilityState` and `window['loc' + 'ation']`.

It also reported a gated re-wrap that passed both layers: two lines, placed before `install(window);`, re-wrapping the real processor count when `devicePixelRatio !== 1` (and variants on `innerWidth > 3000` and a coarse pointer). The owner then gave the direction: AUTOMAT must not need a person, so cover the common user configurations up front rather than making `fingerprint.js` unfixable by AIs.

**A) The static guard, by syntax trees** (`tools/fix-guard.py page_tree_problems`)
- **Its own parser, `tools/js-parse.py`.** No package, no network at CI time, tier B. It parses exactly like acorn 8.14 on all 55 versions of the six page scripts in the history and on the 13 current JS files (darkreader.js included). It refuses what could read differently in the browser: an escaped name (`seed`), a line separator outside a text, an HTML-like comment, an old octal, a name beyond ASCII. A page script that does not parse is refused, and so is one whose parser is missing beside the guard. `autofix.yml` copies the parser and `env-axes.py` from main beside the guard. Both files are in `FORBIDDEN_FILES` and `NOT_RECENT`.
- **The old tree must be embedded in the new one.** Statements may only be added to statement lists. Every old name must resolve to the same binding (a new `let`/`var` that hides an old name is refused).
- **In what is added:**
  - (a) No write to an old binding or object in any form: an assignment, a pattern, `++`, a for-in/of target, a re-declaration (parameters too), `delete`, the mutating methods, `Object.defineProperty`/`assign`/`setPrototypeOf`/`freeze`..., `Reflect.set`/`defineProperty`/`deleteProperty`, `__proto__`, `.call`/`Reflect.apply` of a mutating method, a page object or a global. New code changes only objects it makes.
  - (b) No read of the environment except the axes the matrix measures, or what the old script reads too inside a new function.
  - (c) No computed name except a literal or a number (arithmetic, length, counter). No `eval`, `Function`, `with`, `import()` or `.constructor`.
  - (d) No exit outside a new function or loop.
  - (e) **A condition is allowed when its test reads only what is measured.** That means literals, the change's own clean names (parameters included when every call passes clean values), the level (`lv`, `strict`, `maximum`), and the configurations listed once in **`tools/env-axes.py`** (`COVERED_READS`, `COVERED_MEDIA`). The probe and the guard share that list, so an axis added to the probe is allowed in the guard at once. A condition on anything else stays refused: counters, timing, referrer, cookies, visibility, a site, a text, an uncovered API. A `catch` may only give a clean value back.
  - (f) No re-wrap or definition through an I.K.E. helper (`wrap`, `getter`, `setter`, any old function that defines properties) or `defineProperty` and the like, unless every name is a literal the old script never has, on a prototype.
- **Fable's forms:** every attack form of `guard-syntax.txt` and `guard-honest.txt` is refused (unit tests in `tests/test_no_regression.py`). The gated re-wrap is refused by (f) in all three variants, before and after `install(window)`.

**B) The probe: a matrix of the users' configurations** (`tools/env-axes.py`, `run_matrix`)
- **Axes:**
  - scale 1, 1.25, 1.5, 2;
  - zoom 90–150 %;
  - screens 1280×720, 1366×768, 1536×864, 1920×1080, 2560×1440, 3440×1440, 3840×2160;
  - touch screen or none;
  - dark or light colours;
  - reduced motion or not;
  - forced colours or not;
  - en-US, it-IT, de-DE, ja-JP;
  - UTC, Europe/Rome, America/New_York, Asia/Tokyo;
  - 2–32 cores;
  - 4–32 GB;
  - the four protected levels.

  The sources and assumptions are in docs/MAINTENANCE.md.
- **Coverage:** all pairs of axis values (greedy, seeded per run, the same seed on both sides), plus the corners at each level. That is about 56 sessions per run.
- **How each session is set up:** each session is a fresh page with its own noise key.
  - The engine's DevTools emulation gives device metrics, scale, orientation, colours, motion, contrast, time zone, locale and cores. `--remote-debugging-port` stays on this computer, and I.K.E. keeps it only with `IKE_ALLOW_UNSAFE_ENGINE=1`.
  - The browser gives the zoom and I.K.E.'s setting gives the languages.
  - A preloaded library gives the memory, per renderer, with `--no-zygote` and without a spare renderer.
  - Touch runs in a second browser run with the engine's touch settings, because each navigation undoes the touch emulation.
- **How a session is judged:** values are read in the page (protected) and in an isolated world (real under that configuration). A session is worse where the page shows that configuration's real value, main did not, and main never shows that value at that level (`matrix/<session>/<value>`).
- **Not reachable on the runners:** the GPU vendor strings (software WebGL) and X11 vs Wayland (offscreen only). The guard keeps refusing conditions on either.
- **What the matrix costs:** about 30 s a side (two browser starts and about 20 s for 56 sessions); a check takes about 350 s on 4 cores running two at once (it was about 290 s), `--runs 3` about 18 minutes, within the step's 45.

**Measured (main 8176b12's tree, the final tool):**
- **Fable's gated re-wrap as written** (G1 dpr, G2 innerWidth, G3 coarse pointer, placed before `install(window)`): it **leaks nothing a page sees**. install() wraps the same getter afterwards and its disguise is outer. In the matrix's wide, HiDPI and touch sessions with 12 or 32 real cores the page still showed the disguise. So these copies pass the measurement correctly, and the guard refuses them (re-wrap).
- **The effective forms, after `install(window)`** (H1 dpr, H2 innerWidth, H3 coarse): **fail** by measurement: H1 27 matrix rows, H2 6, H3 16 (the real 2, 12, 16 or 32 cores in the sessions their gate is true).
- **All weakened copies:** the 35 that weaken something fail (F2 also by the matrix: 19 rows; audio-off, gNofp, vM, wk-env too), 0 errors; the stronger audio and Fable's three no-op copies pass (table below).
- **Main vs main:** **6 of 6 pass** (0 worse, 0 errors, 353–363 s each).
- **Rewrite pairs:** **0 of 240 worse** (16 snapshots with independent keys, each with its 56 matrix sessions and 0 errors).
- **Guard on Fable's 15 additive forms of an AI's honest fix:** 11 pass (main's guard 12, round 5's 11). On the six uncovered environment reads, 0 pass (main's 4, round 5's 4). All 38 weakened copies are refused.
- **Honest history**, the added lines of `main`'s 33 commits that added to `fingerprint.js`:
  - this guard refuses **33/33** (main's 28, round 5's 31); over all six page scripts, 43/44 (32, 38);
  - those commits are a person's feature work; each is refused for several reasons: changed old objects (12), writes to old names (13), re-wraps (7), page-data branches and feature detection (26), uncovered environment reads (12);
  - only 1 is refused for a branch alone.

  The target "fewer than 27/29" is not met without loosening (a)–(f), which would let the known exploits through. With the matrix, the automatic fix can add new disguises with conditions on the users' configurations and the level, helpers and new wraps. Changing what the old script protects stays a person's.

| Copy | Verdict | Rows worse | of them in the matrix |
|---|---|---|---|
| H1dpr | **fail** | 27 | 27 |
| H2wide | **fail** | 6 | 6 |
| H3coarse | **fail** | 16 | 16 |
| G1dpr | **pass** | 0 | 0 |
| G2wide | **pass** | 0 | 0 |
| G3coarse | **pass** | 0 | 0 |
| F1 | **fail** | 70 | 0 |
| F2 | **fail** | 42 | 19 |
| F3 | **fail** | 12 | 0 |
| F4 | **fail** | 4 | 0 |
| audio-off | **fail** | 107 | 39 |
| audio-stronger | **pass** | 0 | 0 |
| audio-tenth | **fail** | 6 | 0 |
| gGL2 | **fail** | 21 | 0 |
| gHidden | **fail** | 7 | 0 |
| gInstall | **fail** | 21 | 0 |
| gNofp | **fail** | 532 | 211 |
| gSiteOf | **fail** | 90 | 0 |
| vA | **fail** | 51 | 0 |
| vA1 | **fail** | 21 | 0 |
| vA2 | **fail** | 9 | 0 |
| vA3 | **fail** | 9 | 0 |
| vA4 | **fail** | 3 | 0 |
| vA5 | **fail** | 9 | 0 |
| vB | **fail** | 20 | 0 |
| vC | **fail** | 63 | 0 |
| vD | **fail** | 58 | 0 |
| vE | **fail** | 90 | 0 |
| vF | **fail** | 8 | 0 |
| vL | **fail** | 13 | 0 |
| vM | **fail** | 42 | 22 |
| vS | **fail** | 20 | 0 |
| wk-env | **fail** | 17 | 11 |
| wk-ext | **fail** | 7 | 0 |
| wk-pick | **fail** | 6 | 0 |
| wk-plugins | **fail** | 3 | 0 |
| wk-stripes | **fail** | 1 | 0 |
| wk-widths | **fail** | 22 | 0 |

### Round 5 (Fable's adversarial review of d0f33b9): one-line weakenings that passed both layers
Rebased on `main` 8176b12 (1.1.25). Fable reproduced four one-line weakenings of `fingerprint.js`, and a guard bug, that passed both the static guard and "Nothing gets worse" (pass, 0 worse, 0 `fingerprint_review`). Each is now refused by the guard **and** fails the measurement:

| Copy | What it does | Guard (main / d0f33b9 / now) | Measurement now |
|---|---|---|---|
| F1 | `lv = Math.min(lv, 1)` for hosts matching `/(google\|youtube\|facebook\|…)\.[a-z.]+$/` | accepted / accepted / **refused** (assigns `lv`; a pattern naming sites) | **fail**, 70 rows: `sites.brand.*.www.google.com` and the other brands, true → false |
| F2 | `if (realCores > 8) cores = realCores;` | accepted / accepted / **refused** (assigns `cores`) | **fail**, 23 rows: `fingerprint2/*`, the other machine's real 32 cores |
| F3 | `if (n > 262144) n = 0;` in `farble` | accepted / accepted / **refused** (assigns `n`) | **fail**, 12 rows: `canvas_large`/`webgl_large` real |
| F4 | `setTimeout(function(){ seed = 1; }, 90000);` | accepted / accepted / **refused** (assigns `seed`; runs later) | **fail**, 4 rows: `late.*` true → false |
| F5 | the guard's `ASSIGNS`/`CONSTANT_ASSIGN` anchored at the line's start | – | the page-script rule now scans every assignment of the line |

**A) The static guard** (`tools/fix-guard.py page_script_problems`, I.K.E.'s page scripts):
- A new line may not assign anywhere in it to a name the change does not declare itself. This covers a callback, a loop body, after a `;`, `+=`, `++`. A declaration list (`var a = 1, b = …`) declares all its names.
- No timer, frame or idle callback, microtask, promise continuation or listener outside a function the change adds.
- No pattern or text naming sites (brand names, top-level-domain alternations).
- A condition on the protection's state (`host`, `lv`, `cores`, `n`, `seed`, `strict`…) that guards an assignment or an exit is refused with its own reason.

Results on the copies and on real history:
- **All 32 weakened copies** (F1–F4, the reviewer's earlier ones, the guard copies, the earlier rounds') are refused by the guard.
- **Honest work, measured on the 37 real commits of `main` to `fingerprint.js`:** 36 change old lines and are refused by the additive rule already. Taking only the lines each commit added (29 commits), main's guard refuses 25 and this one **27**. The two more:
  - 1.1.14's frames of PayPal and Stripe left alone, a site exception;
  - 1.1.25's early `return` inside an old function for `toString`.

  Both are a person's to write. A bug found by this measurement, a declaration list treated as assignments (34e0e4a), was fixed and has a test.

**B) The probe:**
- The page of the sites is read on the hosts of nine well-known brands every run (`www.google.com`, `www.youtube.com`, `www.facebook.com`, `www.instagram.com`, `www.amazon.com`, `www.cloudflare.com`, `www.hcaptcha.com`, `www.microsoft.com`, `www.paypal.com`). They are served over the local https proxy, with one mark per brand (`sites.brand.<read>.<host>`). Main leaves PayPal alone on purpose, so its mark is false there and not judged.
- The other machine reports **32 processors** (`sysconf`, `sched_getaffinity`) and 2 GB through the preloaded library. Its values are observations of their own (`fingerprint2/<level>/<value>`, rule `machine2`): worse where a part is that machine's real value and was not on main, or, for a part main fixes in all its sessions, comes closer to it. A pick (the cores among 4 and 8 where there are 8 or more) gets the real-value test only.
- A picture of 1024×1024 and a WebGL texture of 512×512 are read (`canvas_large`, `webgl_large`, with `.noised`, `stable.`, `again.` marks).
- The page of the sites is read again **100 s after its load** in the same page at Balanced (`late.<read>`). The page clock cannot be advanced from outside, so the wait overlaps the rest of the measuring.
- `openssl` and `certutil` are checked first. A missing one is a hard error that names the tool and the package (`openssl`, `libnss3-tools`); the test environment installs both now.

**Runtime**: a check takes about **290 s** on a 4-core computer running two checks at once (about 145 s per side; it was about 170 s): the late re-read adds about 40 s per side, the brands about 15 s. `--runs 3`, only for an AI's change of the page scripts, takes about 15 minutes, within the step's 45.

**Measured (main 8176b12, the final tool):**
- All 31 weakened copies fail, with 0 errors, and the stronger audio passes (table below).
- **Main vs main: 6 of 6 pass** (`check` as in `tests.yml`, 0 worse, 0 errors, 288–292 s each).
- **Rewrite pairs: 0 of 240 worse** (16 snapshots with independent keys, sites and shape, every ordered pair). What it found on the way, fixed: texts of the same width noised alike since 1.1.25 (now 128 texts of distinct widths); the cores, a pick drawn only on the other machine, judged as a fixed disguise there (now only its real value there is worse); "closer" on drawn values of the other machine (now fixed parts only). The floors were re-measured on the 16 snapshots: only the stripes rose (0.0875 → 0.0938, 0.164 → 0.175), and none was lowered.
- Unit tests: `tests/test_no_regression.py` and the guard's and AUTOMAT's tests pass, the real-engine `test_the_check_catches_a_realistic_weakening` too; one failure, `test_automat_part2.py::test_without_the_reviewers_reserve_the_fix_waits_and_nobody_is_called`, fails on `main` too (not this PR's). ruff clean; actionlint only shows old shellcheck notes in workflows this PR does not touch.

| Copy | Verdict | Rows worse | First row |
|---|---|---|---|
| F1 | **fail** | 70 | `fingerprint/balanced/sites.brand.audio.www.amazon.com`: True on main, False here |
| F2 | **fail** | 23 | `fingerprint2/balanced/frame`: [0] the other machine's real value here (32) |
| F3 | **fail** | 12 | `fingerprint/balanced/canvas_large`: the real value (Off's) here, in a session where main never gave it |
| F4 | **fail** | 4 | `fingerprint/balanced/late.audio`: True on main, False here |
| audio-off | **fail** | 68 | `fingerprint/balanced/audio`: the real value (Off's) here, in a session where main never gave it |
| audio-stronger | **pass** | 0 | – |
| audio-tenth | **fail** | 6 | `fingerprint/balanced/audio`: the noise is smaller: dispersion 0.000501585 on main (floor 0.000442), 5.01583e-05 here |
| gGL2 | **fail** | 21 | `fingerprint/balanced/webgl2.extensions`: the real value (Off's) in 24 of 24 sessions here: more than chance gives (1e-05 a session, measured on main) |
| gHidden | **fail** | 7 | `fingerprint/balanced/frame_html`: [2] the real value (Off's) in 8 of 8 sessions here: more than chance gives (0.0048 a session, measured on main |
| gInstall | **fail** | 21 | `fingerprint/balanced/frame`: [2] the real value (Off's) here, in a session where main never gave it; [4][0] the real value (Off's) here, in |
| gNofp | **fail** | 321 | `fingerprint/balanced/audio`: the real value (Off's) here, in a session where main never gave it |
| gSiteOf | **fail** | 90 | `fingerprint/balanced/sites.brand.audio.www.amazon.com`: True on main, False here |
| vA | **fail** | 51 | `fingerprint/balanced/audio_analyser`: the real value (Off's) here, in a session where main never gave it |
| vA1 | **fail** | 21 | `fingerprint/balanced/webgl2.extensions`: the real value (Off's) in 24 of 24 sessions here: more than chance gives (2.9e-05 a session, measured on main) |
| vA2 | **fail** | 9 | `fingerprint/balanced/audio_copy`: the real value (Off's) here, in a session where main never gave it |
| vA3 | **fail** | 9 | `fingerprint/balanced/audio_analyser`: the real value (Off's) here, in a session where main never gave it |
| vA4 | **fail** | 3 | `fingerprint/balanced/canvas_offscreen`: the real value (Off's) here, in a session where main never gave it |
| vA5 | **fail** | 9 | `fingerprint/balanced/video_frame`: the real value (Off's) here, in a session where main never gave it |
| vB | **fail** | 20 | `fingerprint/balanced/frame_html`: [1] the real value (Off's) here, in a session where main never gave it; [2] the real value (Off's) in 8 of 8 s |
| vC | **fail** | 64 | `fingerprint/balanced/again.audio`: True on main, False here |
| vD | **fail** | 58 | `fingerprint/balanced/audio`: only 5 different in 8 sessions here (on main all 8 differed) |
| vE | **fail** | 90 | `fingerprint/balanced/sites.brand.audio.www.amazon.com`: True on main, False here |
| vF | **fail** | 8 | `fingerprint/maximum/fonts_found`: a font a page can find on this computer is not masked here: arimo, caladea, calibri, cambria, carlito, cousine |
| vL | **fail** | 13 | `fingerprint-config/balanced/fonts`: a font a page can find here is not masked: calibri, cambria, helvetica neue |
| vM | **fail** | 20 | `fingerprint/maximum/env.navigator.deviceMemory`: True on main, False here |
| vS | **fail** | 18 | `fingerprint/balanced/sites.brand.pic.www.amazon.com`: True on main, False here |
| wk-env | **fail** | 6 | `fingerprint/maximum/env.intl.locale`: True on main, False here |
| wk-ext | **fail** | 4 | `fingerprint/balanced/frame_x`: [2] the real value (Off's) in 7 of 24 sessions here: more than chance gives (0.015 a session, measured on main |
| wk-pick | **fail** | 4 | `fingerprint/balanced/frame_x`: [1] the same in every one of the 24 sessions here (on main it changed) |
| wk-plugins | **fail** | 3 | `fingerprint/balanced/frame`: [2] closer to the real value: 2 from it on main, 1 here |
| wk-stripes | **fail** | 1 | `fingerprint/balanced/canvas_flat`: the noise is smaller: stripes 0.12207 on main (floor 0.0938), 0.0647321 here; stripes_between 0.229432 on main |
| wk-widths | **fail** | 22 | `fingerprint/maximum/canvas`: [2] the same in every one of the 8 sessions here (on main it changed) |

### The fourth review (Fable's re-check of 1a20dff): weakenings that still passed, and what now measures them
Rebased on `main` f51ba83 (#152's shards, #157's font-check wait: kept, this branch's own wait dropped, so there is one; `measure()` only reports when the check gave no answer). Each finding has a weakened copy that passed before and fails now (the reviewer's copy names); the table under "Real runs" has them all.

- **N1 (critical), one site, an IP over http.**
  - The probe is now served **on real-looking sites over https**: random names under common top-level domains, through the local proxy. The proxy ends the TLS tunnel with a certificate of the run's own authority (`openssl`), trusted only in that profile's NSS database (`certutil`; `libnss3-tools` added to the test environment).
  - A small page of the sites is read on **six hosts** per level (key 1):
    - `a`;
    - a host of the same site, `a2`;
    - two sites under `.co.uk` (a public suffix of two labels: not one site);
    - a `.com`;
    - another top-level domain.
  - The marks, safer-true (true on main must stay true):
    - `sites.differ.<read>`: different sites differ, so one key for every site (vE) fails, and so does a PSL that took `x.co.uk` and `y.co.uk` as one site;
    - `sites.agree.<read>`: two hosts of one site agree;
    - `sites.noised.<read>`: every host is noised, so vS (the noise left out on `.com|.org|.net|.it`) fails on the `.com` host in any run.
  - The reads are the known-bytes picture, `toDataURL`, the audio, WebGL `readPixels` and text widths.
  - http on a real name is not a secure context: no `MediaDevices`, Client Hints, `deviceMemory`… The first attempt, Chromium's switch to treat it as secure, is ignored by QtWebEngine, hence https.
  - The random names, keys and shape are the same on both sides of a check.
- **N2 (high), noise independent of the key or unstable.**
  - Each level loads the probe **once more with the first key**. Every judged value must read as in the first session (`again.<value>`), so vC (key plus `Math.random` per load) fails.
  - A large space (`NOISE_PARTS`) whose sessions all differ on main must not repeat. vD (3 bits of the key, 8 noises) fails: "only 3 different in 8 sessions here".
  - `frame.agrees.canvas`: the frame's canvas is its page's in every session.
- **N3 (high), unread APIs and realms.** New reads:
  - WebGL2: name, vendor, extensions, `readPixels` of known bytes;
  - audio by `copyFromChannel` of a buffer never read by `getChannelData`;
  - an `AnalyserNode` (float and byte, frequency and time);
  - `convertToBlob` of known bytes;
  - `VideoFrame.copyTo`;
  - frames added, made by `innerHTML` and from `srcdoc`, each with canvas, card, extensions, sound, languages, cores and `readPixels`;
  - a `SharedWorker`;
  - a dedicated worker from a file of the site.

  The picture sizes, text, sound length and frequency, and seeds are random per check (`random_shape`) and the same on both sides. vA (all five left out) and each of vA1–vA5, and vB (sub-frames without the WebGL disguise, audio or font masks), fail.
- **N4 (high), fonts.**
  - The fonts a page can find are now tested over **main's list ∪ the candidate's ∪ the installed families** (`fonts_main` in the plan).
  - At Strict and Maximum each one is tested **inside the protected page and in a frame of it** (`fonts_found`, `fonts_found_frame`): none may keep its own width, and one more than on main is worse.
  - vF (11 installed families spliced out of `MASKED` at run time, added lines) and vL (names fontconfig answers to removed from `MASKED_FONTS`) fail.
- **N5 (medium), the AI-merge path.**
  - `report.json` lists `fingerprint_review`: every fingerprinting row that is not "same" or "stricter".
  - `tests.yml` turns it into the step **"Fingerprinting unchanged"**. Its outcome is the job's output and it is never a red; it is restated in the gate only when it passed.
  - `tools/automerge.py` (`ai_requirements`) refuses an AI's change by itself when that step did not pass: a person decides.
  - The two reviewers are shown those rows (`tools/ai-review.py fingerprint_rows`, appended to what they read).
  - A failed "Nothing gets worse" on an AI's change of protected code adds the label `nothing-gets-worse:<patch id of the tier-A files>`. Any later run on the same change that passes still goes to a person; the patch id ignores line numbers, so a rebase keeps it.
  - An AI's change (an `automation/*` branch) of the page scripts or `ike/shields.py` is measured **three times with independent keys, sites and shape** (`--runs 3`); a row worse in any run is worse.
- **N6 (medium), floors.**
  - All floors are rewritten at **0.9 of the lowest main measured** in 19 snapshots (0.8 for the flat stripes). Audio dispersion 4.39e-4 (it was 2.4e-5, a twentieth of main after #148).
  - A floor that is not a number above 0 (e.g. text) is an error.
  - The report says when a floor is under 60 % of main's noise.
- **N7 (medium), disguises equal to the real value.**
  - The other-machine run now has **3 processors** (`sched_setaffinity`) and **2 GB** (a small `LD_PRELOAD` library built with `cc`: `sysconf(_SC_PHYS_PAGES)`, `sysinfo`). Off there reads 3 cores and 2 GB.
  - A pick that is the same in every session (the cores at Strict) now counts as a fixed disguise for the `env.` marks.
  - vM (Strict's cores and memory made the real ones, 4 and 8 here) fails.
- **N8**: the pick page also reads the worker and a frame (card and extensions), and WebGL2: 24 draws each.
- **N9**: an allowlist entry may pin `part`, `detail` and `version` (no longer counting on another version), for rows that change with the key.
- **N10**: an observation measured on main (even as null) and missing on the candidate is never "same": it is unjudged, so worse.
- **Static guard** (`tools/fix-guard.py page_script_problems`, I.K.E.'s page scripts only). These were accepted by main's guard and are refused now (tested):
  - copies made of added lines: vS, vF;
  - a constant `siteOf`;
  - a WebGL2 skip;
  - an `install()` return for sub-frames;
  - `delete hiddenExt[k]`;
  - `CFG.nofp.push(host)`;
  - a time-based and a `Math.random`-based condition.

  The general rules: no new `return`/`throw`/`break`/`continue` outside a function the change adds; no new line reading where or when the page is (`location`, `hostname`, `protocol`, `origin`, `top`, `parent`, `frameElement`, `referrer`, `Date`, `performance`, `Math.random`); no method that changes an object the old script has (`splice`, `pop`, `shift`, `push`, `add`, `set`, `delete`…), no `delete` from it. A new helper with its own exits, or a new wrap, is still accepted.

### Fingerprinting: judged by protection properties
The principle from the second review: **never a false pass**. False alarms are kept low by **more measurement**, never by looser rules.

**What is measured**
- **8 sessions per level** (2 at Off). Each session is a page load with its own noise key; `check` gives both sides the same random keys.
- The values drawn from a few common ones (card name and maker, WebGL extensions, cores, plugins) are read **16 more times per level** on a small page, so there are **24 draws per side**.
- **Another machine**: one more measure run with another time zone, language, screen size, **3 processors and 2 GB** (`OTHER_MACHINE`).
- Every level is measured **after the font check** (`fontcheck.py`) has answered: #157's wait in the hook's `_start`, the one wait; no answer is an error here.

**How each disguised value is judged** (`FP_JUDGED`), part by part, in every session, against **both** Off levels (main's and the candidate's: the real value):
- **The real value in a session**, only as often as chance gives it:
  - where chance never gives it (a picture's hash, a card's name not among the common ones): worse in any session where main never gave it;
  - where it does, by how often, **measured on main**: a single text width (61 noise steps, one of them none) against main's 128 widths of every session; the extensions (each name left out about half the time) against main's 24 draws, also for the worker's list (`LIST_PEERS`). Worse when a binomial tail puts the candidate's count under 10⁻⁴;
  - where main gave it too (the cores, one of two): worse when far more often, by an exact permutation test of both sides' sessions (before, any count passed).
- **Always worse**:
  - a hidden value now readable;
  - the real text contained in a text, or more of its words than in any of main's draws.
- **Large spaces** (`NOISE_PARTS`: picture and sound hashes, random plugin names) must still change with the session.
- **Picks** (`PICK_*`) must never be the same in every draw where an **exact permutation test** of both sides' draws puts that under 10⁻⁴. With 24 draws a constant card name is caught (about 10⁻¹⁰ by chance); the maker alone, one of two, cannot be told from chance.
- **Lists drawn per session** (extensions, the worker's extensions, plugins) and randomised numbers:
  - no fewer names changed, judged by Student's t over the sessions at 5, about 10⁻⁴, with a variance floor so even a constant drop of one name fails;
  - at least 3 different lists where main has them;
  - with fewer than 3 sessions they cannot be judged, so they are worse.
- **Fixed disguises**:
  - no closer to the real value (numbers, lists, texts);
  - a new value only if a person lists it in `tests/data/no-regression/common-values.json` (starts empty);
  - the `env.<value>` mark: it must not follow the real machine on the other machine.

**Noise size** (`NOISE`), measured against Off's real values. The two sides' Off references must match, or the noise is unjudged.
- What is measured:
  - known-bytes pictures: page, page `toDataURL`, blob, offset, frame and frame `toDataURL`, WebGL `readPixels`, worker;
  - 896 flat stripes, each of its own colour: the count of stripes changed;
  - text widths: the page's 128 and the frame's 64;
  - audio: the spread of the factors (a constant gain fails).
- For each: the size, the share changed, and the share that differs **between sessions** (a noise drawn the same each time, or at the same places, fails).
- For the text widths also **the session with the fewest changed** (`widths_least`): a session with no width noise fails here, since a single width's real value is judged against chance.
- **Floor and tolerance**: `need = max(main·(1 − tol), floor)`, with **no tolerance on the floor**. The floor is a person-edited file.
- `tol = max(20 %, 4·√2·cv/√k)`, **capped at 35 %**. Where the cap would bind, more is measured (the stripes went from 112 to 896, each of its own colour: 448 repeating every 256 were noised alike in pairs and varied beyond their tolerance in the keys experiment).

**Marks** that must stay true where they are true on main: `.noised`, `stable.`, `site.`, `natural/.differs`, `natural/.noised`, `env.`.

**Masked font names** (`fingerprint-config/<level>/fonts`, the false "worse" of #155). This value is the digest of `fontcheck.findable()`: the names fingerprint.js masks. They follow the computer's fonts and when its check answered, so two runs of the same code could differ.
- Judged by what protects, not by the digest: the tool measures, **in the same run**, which fonts a page can find. It uses a page of its own in a profile with none of I.K.E.'s scripts, over fingerprint.js's names and the installed families.
- Every font found must be masked (except the six every system has, as in `fontcheck.py`):
  - a font found and left unmasked where main masked it → worse;
  - two different lists that each mask every font found → "changed";
  - fewer unmasked than main → stricter;
  - not measured on the candidate → unjudged.
- Together with the wait for the font check, #155's case (a list on main, no answer yet here) can no longer occur; if it did, it would pass whenever fingerprint.js's whole list covers every font found.

**Other rules**
- Directional keys (`PROTECTIVE`): protected on main must stay protected; becoming protected is stricter.
- Fewer sessions on the candidate than on main → worse.
- The audit hook not reporting I.K.E.'s own hosts → error. A host list missing on the candidate → worse.
- An unreadable floors or common-values file → error.

### Evidence (narrowed by the review)
- **Necessity** accepts only one kind of row: **a value main left real that is now disguised in both sessions**. It needs a test that a person bound to those exact keys in `tests/data/no-regression/necessity.json`. The binding takes an exact test id, keys with at most the level as `*`, and exact files under `ike/`. The file starts empty.
- The test must fail on main and pass here in junit, and then be **re-run 3× on main's worktree (fail 3/3) and 3× on the candidate (pass 3/3)**. The change must touch the binding's files and **not the test's own file**. At most **4 rows per test**.
- Main's junit only comes from a tests.yml run with **event push, branch main, conclusion success|failure**, and only if it matches the very base commit.
- Evidence never accepts: a weakening, "not measured / could not be read", Off-level rows, directional keys, `fingerprint-config/*`, security settings, requests or hosts.
- **Requests**: an allowed request passes only when the filter list data that decides it changed. An engine built from the lists alone names the deciding rule or exception and the list it comes from, with a digest of each list. In `tests.yml` both sides use main's fixture lists, so a newly allowed request is always worse there.
- **Hosts**: `endpoints.json` (person/Claude-only) is now empty: hosts main already contacts aren't pre-declared. Each entry names its observation key (default `network/fresh-profile`). The host must be named in **added non-comment lines of `ike/**/*.py`**.
- **The candidate never brings its own rules**: tests.yml passes **main's copies** of the allowlist, endpoints and necessity bindings (`$where/...`); the floors and common values come from main's copy of the tool. The diff is taken from the **merge base**.
- **Security**: stricter or equal passes; anything else is worse, with no exceptions.

### Not recognisable (partial)
- These are now random for each run (the same on both sides of a check): the sites the probe is served on (real-looking names, over https), the probe's sizes, text and sound, the probe's path, query parameter, title, result global, the third-party host (a real-looking name too), the frame path, the cosmetic attribute, the hook/wrapper/plan/output file names, the plan's environment variable, the network module name and the working folder names. Recorded values are written back with the fixed names, so snapshots compare. The canvas text is neutral, and the audit hook's error is a plain "Network is unreachable".
- `tools/fix-guard.py` (`MEASUREMENT`, `measurement_problems`) and `tools/ai-review.py` (`measurement_marks`, a reject before any model is asked) refuse AI changes that add `IKE_TEST_*`, `IKE_NR*`, `IKE_NO_SINGLE`, `nrResult`, `nr-third`, "no regression", "nothing gets worse", `offscreen`, `QT_QPA_PLATFORM`, `platformName`, `profile_keys`, `swiftshader`, `QTWEBENGINE_DISABLE_SANDBOX`, `DBUS_SESSION_BUS_ADDRESS`, `GITHUB_ACTIONS`/`CI`/`RUNNER_*`, `127.0.0.1`/`localhost`, `.example`, `addaudithook`/`sys.modules`, or the probe's text and known-bytes generator.
- The docs note that the gate should move to its own job on a fresh runner, planned together with `automation/fast-tests`.

### Report and signing notice
- The headline reads **"Passed, N by evidence"**. Every passing row says why (`why`, `passed_by`), every worse row says "weaker" or "cannot be judged", and the report lists the evidence read, including the confirmation record.
- Rows that passed by evidence also become one `::notice` of the run. `tools/release-notice.py` reads it from the `tests checks` (or, before the shards, `tests`) check-run annotations of each merged PR and lists the rows under "Differenze passate per prova, senza una persona". If it can't read them it says so.

### Workflow (`tests.yml`, sharded since #152)
- New job **tests main results** (`main-results`): the only job with `actions: read`, because a permission can't be scoped to a step. It does no checkout, runs only `gh` and none of the candidate's code, and hands main's junit plus the base sha to **tests checks** as an artifact.
- **tests checks** (`needs: main-results`, `if: ${{ !cancelled() }}`, no `actions` permission) runs "Nothing gets worse" with:
  - **main's copies** of the allowlist, endpoints and bindings;
  - main's junit of the very base;
  - this commit's junit of the tests main's bindings name, run there (the shards run elsewhere).

  It has 45 minutes for three runs.
- An AI's change of the page scripts or `ike/shields.py` on an `automation/*` branch gets `--runs 3`.
- The step **"Fingerprinting unchanged"** has its outcome as the job's output and is never a red. The gate restates it only when it passed; `tools/automerge.py` reads it there.
- Options are passed only to a tool copy that supports them (`grep` on main's copy), so until this is on `main` the check runs as today.
- `libnss3-tools` is added to the test environment (`certutil`, to trust the run's own authority in the profile).
- `tools/release-notice.py` reads the evidence notice of **"tests checks"** (or "tests" before the shards), never of a shard.

### False alarms (measured with the final tool, main f51ba83)
A red from chance would hold back every real update that day; a pass from a looser rule would let a weakening through. No rule is loosened for chance: what chance can produce is told from a weakening by **more readings**.
- **Main vs main as in CI** (the same random keys, sites and shape on both sides): **20 real `check` runs, 20 passes, 0 errors, 0 fingerprinting rows** (about 170 s each). The same keys and sites give the same values: nothing is judged.
- **Main vs main with independent keys and sites** (what a rewrite of the noise of the same strength looks like): 16 snapshots (fingerprint, network, security; each with its own random sites), **240 ordered pairs, 0 with any "worse"** with this round's rules (`sites.*`, `again.*`, the noise-part repeats, the masked fonts, the new reads, the floors at 0.9 of main's lowest).
- **Computed bound** for a rewrite run:

  | Source | Count | Chance each | Total |
  |---|---|---|---|
  | noise measures, z = 4 (new: WebGL2, `copyFromChannel`, `convertToBlob`) | 141 | ≤ 3·10⁻⁵ | 0.03 % |
  | counts of the lists drawn per session (now also WebGL2, the shared and file workers, the three frames) | 24 | 10⁻⁴ | 0.24 % |
  | real-value tests (binomial or permutation): those 24 lists, 10 single widths, 9 picks | 43 | 10⁻⁴ | 0.43 % |
  | picks the same in every draw, hashes, noise-part repeats (8 sessions of a 2³² space) | | far below | |
  | marks (`sites.*`, `again.*`, `frame.agrees`) | | the same key and site give the same value | |

  Total **under 0.8 % per run**; 0 seen in 240 pairs. The new reads add list counts and real-value tests, which raises this bound from 0.4 %. Each of these tests stays at 10⁻⁴: none was loosened.

### Real runs (QT_QPA_PLATFORM=offscreen, the final tool, base = `origin/main` f51ba83, main's allowlist, random keys, sites and shape)
Every copy is main's tree with one change, checked against main. **All 27 weakened copies fail; the stronger one passes.** "Before" is the tool of 1a20dff (a6c501e after the rebase) on the same copies.

| Finding | Copy (main f51ba83 + one change) | Before (1a20dff's tool) | Now |
|---|---|---|---|
| N1 | vE: one noise key for every site | pass | **fail**: 14 rows, `sites.differ.*` true → false |
| N1 | vS: the noise left out on `.com/.org/.net/.it` (4 added lines) | pass | **fail**: 52 rows (canvas real, `.noised` false, `sites.noised.*`) |
| N2 | vC: the key and `Math.random` at every load | pass | **fail**: 78 rows, `again.*` true → false |
| N2 | vD: 3 bits of the key (8 noises) | fail (by chance in this run: the card's name the same in 24 draws) | **fail**: 72 rows, "only 5 different in 8 sessions here (on main all 8 differed)" |
| N3 | vA: WebGL2, `copyFromChannel`, `AnalyserNode`, `convertToBlob`, `VideoFrame.copyTo` left out | pass | **fail**: 36 rows |
| N3 | vA1–vA5: each of those alone | – | **fail** each: `webgl2.*` (12), `audio_copy` (6), `audio_analyser` (6), `canvas_offscreen` (6), `video_frame` (6) |
| N3 | vB: sub-frames without the WebGL disguise, audio noise, font masks | pass | **fail**: 11 rows (`frame_html`, `frame_srcdoc`, `fonts_found_frame`) |
| N4 | vF: 11 installed families spliced out of `MASKED` at run time (added lines) | pass | **fail**: `fonts_found`/`fonts_found_frame` at Strict and Maximum |
| N4 | vL: names fontconfig answers to removed from `MASKED_FONTS` | pass | **fail**: 9 rows (`fingerprint-config/*/fonts`, `fonts_found*`: calibri, cambria, helvetica neue) |
| N7 | vM: Strict's cores and memory made the real ones (4 and 8 here) | pass | **fail**: `env.navigator.hardwareConcurrency`, `env.navigator.deviceMemory`, the workers' and frames' `env.` |
| guard | a constant `siteOf` (added lines) | – | **fail**: 14 rows, `sites.differ.*`; refused by the guard |
| guard | a WebGL2 skip (added lines) | – | **fail**: 12 rows `webgl2.*`; refused by the guard |
| guard | `install()` returns for sub-frames (added lines) | – | **fail**: 14 rows (frames, `fonts_found_frame`); refused by the guard |
| guard | `delete hiddenExt[k]` (added lines) | – | **fail**: 21 rows (extensions real); refused by the guard |
| guard | `CFG.nofp.push(host)` (added lines) | – | **fail**: 182 rows; refused by the guard |
| round 2 | wk-pick, wk-ext, wk-widths, wk-stripes, wk-plugins, wk-env, made again on this main | – | **fail** each (4, 12, 8, 3, 6, 4 rows) |
| audio | the noise off; a tenth of it | – | **fail** (29 rows; dispersion 5.0e-4 → 5.0e-5 under the floor 4.39e-4) |
| audio | **ten times stronger** | – | **pass**: `audio`, `audio_copy` "stricter" ×10 |

The static guard on each copy's change: main's `tools/fix-guard.py` accepts vS, vF and the five added-lines copies above; this branch's refuses all 27 (`page_script_problems`; the others were already refused as changed lines).

**Runtime**: one `check` (both sides; all sections; six site hosts and the first key again per level; the other machine; two network starts) takes **about 165 s** locally, so **about 80 s per side** (it was about 117 s per check). `--runs 3`, only for an AI's change of the page scripts, takes three times that.

### Tests
- `tests/test_no_regression.py`: 42 tests, all passing, including the two real-engine ones.
- The other suites: 779 passed (test_automation, test_full_auto, test_full_chain, test_maintenance, test_merge_and_mail, test_automat_drill, test_automat_part2, test_inventory_guard).
- `ruff check .` and `actionlint` are clean.

New tests this round:
- `test_the_fourth_review_sites_keys_frames_and_fonts`:
  - the sites marks: vE, a PSL that merges `.co.uk`, a host of one site with another noise, the `.com` host left unnoised, a host unread;
  - the random sites' shape;
  - `again.*` (vC);
  - repeats of a large space (vD);
  - `frame.agrees`;
  - the masked-fonts rule;
  - a pick fixed for the other machine (vM).
- `test_the_fourth_review_rules_of_the_report`:
  - floors as text or 0 → error, stale floors said, the audio floor raised;
  - allowlist `part`/`detail`/`version`;
  - null on main and missing here → worse;
  - `fingerprint_review`;
  - `merge_runs`;
  - `random_shape`.
- `test_the_guard_refuses_the_added_lines_that_weakened_the_fingerprinting`: 9 additions that main's guard accepts (vS, vF, constant `siteOf`, WebGL2 skip, sub-frames skipped, `delete hiddenExt[k]`, `CFG.nofp.push`, a time and a chance condition) are refused; a new helper with its own exits, and a new wrap, are accepted.
- `test_the_reviewers_see_the_fingerprinting_rows`.
- `test_full_auto`'s AI path: "Fingerprinting unchanged" missing or skipped → person; the sticky label of the same patch id → person, another id → merge; `stick()` posts the label; the patch id ignores line numbers.
- The fixture `with_no_regression`/`runs()` now carries the restated step too: it is what tests.yml gives for a commit where nothing changed.

Changed assertions, explained in the tests:
- `test_the_step_of_tests_yml`: the step moved to **tests checks**; the job that needs main's results is now that one; the bound tests are run there.
- `test_the_signing_notice_lists_what_passed_by_evidence`: the notice is read from "tests checks", and a shard's notice of the same title does not count.
- `test_every_level_is_measured_after_the_font_check`: the one wait is #157's in `_start`.

### Found in I.K.E. itself (not this PR's to fix)
A dedicated worker started from a **file of the site** (not from a blob) reads the **real card, extensions and languages at Strict and Maximum** on `main` (f51ba83). The new `file_worker` read shows it; since `main` gives the real value it can only be judged when it changes. It needs a fix in `fingerprint.js`, separately.

### Risks
- **https in the measurement**:
  - the run's own authority is trusted only in the profile it makes (NSS);
  - `openssl` and `certutil` must be there, and are on the runner after `libnss3-tools`; without them the snapshot reports an error, never http silently;
  - the network starts (fresh profile) still load their probe at `127.0.0.1`, where a fresh profile's HTTPS upgrade would otherwise have nothing to answer.
- **More measured, more to fail**:
  - about 2,000 observations per snapshot;
  - the six-host site page and the again-load can flake under load. Any unread host is "cannot be judged", so worse. None did in the runs above.
- The memory of the other machine needs `cc` (an `LD_PRELOAD` library, there on GitHub's runners). Without a compiler the snapshot reports an error: a disguise equal to the computer's memory could not be told.
- The AI-merge rule is stricter by design: **any** fingerprinting value that is only "changed" needs a person on an AI's change, even when still protected.
- The sticky label is a label: a person may remove it on purpose; the automation never does.
- This PR changes `tests.yml`, the test environment and `tests/`, so it never merges by itself. The CHANGELOG is untouched (tooling only).

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_01MXEs6VZHarM3wfnsxyHDec
