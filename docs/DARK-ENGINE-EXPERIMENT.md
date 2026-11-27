# Dark Engine experiment

This record belongs to `experiment/dark-engine-chatgpt`. The experiment is off by default. Select **I.K.E. Dark Engine (experimental)**
in Settings under Dark mode method, and enable dark mode. Dark Reader and
Chromium remain separately selectable. The legacy hidden flag is still read
for existing profiles.

## 2026-11-26

### Changes

- Continued from `be86af8`, where the experimental renderer already ran
  in ApplicationWorld at every shield level.
- Delay rewriting author declarations until the document's native-dark
  metadata is known. Support modern CSS colors through a cached sRGB
  conversion and keep the priority of mapped CSS custom properties.
- Keep SVG presentation colors below author stylesheet rules and follow
  their attribute changes. Recheck a small image only when its selected
  source changes. A cross-origin image that cannot be sampled no longer
  prevents sampling later images. Use the Dark Reader list's image and
  linked stylesheet exclusions.
- Keep records of constructed style sheets in a weak map so replaced
  adopted sheets can be collected and ordinary document updates no longer
  iterate over obsolete records.
- Fail the comparison renderer on failed or timed-out navigation. Require
  every comparison input, use both engines' dark-site lists and measure
  CPU time and memory over fresh, alternating Qt processes.

### Verified

- Debian with the pinned Qt 6.12.0, Qt WebEngine 6.140.0, Chromium
  140.0.7339.264 and the branch's locked Rust ad blocker. Built the native
  ad blocker and C launcher. Ruff, Python compilation, and JavaScript
  syntax checks passed. Arch packaging, Plasma and hardware GPU behavior
  are pending.
- The final focused run passed 13 browser tests in
  `test_dark_engine_experiment.py` and `test_dark_blank.py`. It covers
  rendering at all five shield levels, ApplicationWorld state isolation,
  native dark, modern CSS, rule priority, image replacement and SVG.
  The preceding broader run passed 28 tests covering the experimental
  renderer, Dark Reader and frames, fingerprinting and Client Hints.
- On offline copies of Arch Linux, Hacker News and Python Docs, the first
  corrected prototype and the original branch head rendered pixel-identical
  screenshots. The prototype passed Arch Linux and Python Docs. Both
  engines failed the same three contrast regions on Hacker News.
- The live comparison's first run correctly failed on the workspace
  certificate error. After making the OS-trusted proxy CA available only to
  the disposable Qt profile, five public pages loaded in all three modes.
  Python Docs passed with the prototype. Measured non-image light area on
  MDN fell from 74.4% with Dark Reader to 1.7% with the prototype, above
  the 1% target. GitHub and Wikipedia triggered image comparisons in both
  modes. Live content varied between some captures. The standalone renderer
  does not include I.K.E.'s complete shield or ad blocker.

| Synthetic scrolling/mutation workload | Dark Reader | Dark Engine |
| --- | ---: | ---: |
| Median duration (15 samples per mode) | 600.4 ms | 414.5 ms |
| Median observed process-tree CPU time (three runs of five) | 5.76 s | 4.18 s |
| Median peak process-tree PSS (three runs of five) | 384.1 MiB | 336.9 MiB |

The environment reports software rendering. These process measurements
describe this workload and sample, with CPU time from observed processes
and shared memory apportioned by PSS. Hardware GPU usage remains unmeasured.
Repeat with `python3 tests/dark_engine/resources.py OUT --runs 3 --bench 5`
and use the same display mode, engine version and background workload.

### Follow-up

- Cross-origin stylesheet overrides now follow their sources' media and
  removal, including links inserted inside an existing page. A response
  for a replaced link can no longer restore the old override. An independent
  Chromium check also exercised restrictive CSP, link disabling and delayed
  responses from a replaced link.
- Initial Dark Reader detector hints preserve native themes where they
  match. An explicit per-site dark choice takes precedence. A site declaring
  both light and dark palettes is checked against the current preference.
- Contrast for translucent text now uses the composited foreground against
  its declared background. The original foreground opacity is retained.
  Re-running both new regressions against `ef8dafb` reproduced the missing
  cross-origin overrides and the 3.50:1 contrast ratio. On the current code
  both tests passed, including at least 4.5:1 contrast with the same opacity.
- The follow-up benchmark used fresh, alternating Qt processes again.
  Dark Reader and the experiment measured 570.2 and 378.0 ms per synthetic
  run, 5.94 and 3.86 s of observed CPU time per five-run trial, and 393.3
  and 373.5 MiB peak PSS, respectively. These are medians from 15 synthetic
  runs and three process-tree trials per mode with software rendering.
- In the full I.K.E. browser at Maximum, Hacker News, Python Docs and MDN
  each loaded in all three modes using disposable profiles and the test
  fixture's minimal filter list. Both dark renderers passed Python Docs
  and failed two contrast regions on Hacker News. MDN stayed light before
  the dual-palette fix. The corrected experiment loaded the same page at
  Maximum with a dark root background and processed 60 stylesheets and
  628 rules.
- The 36-test regression run passed in the offscreen harness. The final
  renderer and backdrop run passed 17 tests, including the stylesheet
  lifecycle and dark theme detector cases. An attempt with Chromium
  sandboxing enabled stopped during startup because the workspace's setuid
  helper could not run. A separate namespace check failed against the
  read-only UID map, and the workspace exposes no hardware render device.

- The first mixed-background fix kept layers in their author form until the image
  checks settle. This lets the engine apply the mapped gradient and any
  transformed icons together. A failed image keeps its original URL and
  still lets the gradient update. The regression failed at `9af3298` and
  passed with the fix at Maximum for both stylesheet and inline rules.
  The offscreen renderer and backdrop suites passed 18 tests, and the
  focused regression passed again after reducing callbacks to one pending
  layer per pass. Slow images could delay conversion of the gradient.
- The follow-up maps gradients while image analysis is pending and keeps
  the authored value until the remaining layers settle. When a delayed
  image is ready, the rule and inline declarations gain the transformed
  image without mapping their gradients twice. A page's replacement of
  the declaration takes precedence. At Maximum, the fixture holds the SVG
  response until the first read of computed styles. The gradient remained
  white at `0825910` and darkened before the response with the follow-up.
  The renderer and backdrop suites passed 19 tests with the follow-up.
- The Qt comparison passed the logo, photo and background-image fixtures
  with the experiment. Dark Reader passed the photo fixture and reported
  an invisible icon in the logo fixture and a low-contrast text region in
  the background-image fixture.
- Background images now retain at most 256 cached results and 4,194,304
  encoded characters after the work settles. Eviction starts with the
  least recently used results. It waits for outstanding image analyses
  and scheduled stylesheet updates, so bursts can temporarily exceed
  either limit. Existing rendered backgrounds keep their converted data.
- At Maximum, the cache tests converted all 270 small icons and all 24
  larger tiles. The two cases exercised the entry and encoded-character
  limits respectively and verified that a reused source still renders
  correctly. The `d72cf50` baseline with a read-only cache counter
  kept all 270 icon entries. These measurements describe cache contents,
  with renderer and GPU memory outside their scope. The renderer and
  backdrop suites passed 21 tests with the cache limit in place.

### Experimental package

- Built `ike-browser-1.1.25-1-x86_64.pkg.tar.zst` from a clean archive of
  `19813b0` using the unchanged `PKGBUILD` and makepkg 7.0.0 on Debian.
  The build used `--nodeps` because the host has no Arch package database.
  Cargo built the locked Rust dependencies and GCC built the launcher.
- `zstd -t` passed and `pacman -Qip` recognized the package and listed
  the Arch runtime dependencies. The archive contains the expected
  metadata, x86-64 launcher, native ad blocker and exact Dark Engine
  source. The package is unsigned and intended for local testing.
- All 21 renderer and backdrop tests passed with `IKE_TEST_APP` pointing
  at the extracted package's application directory and the pinned Qt
  runtime. The test harness started the packaged Python entry point.
- The expanded run using the extracted package for browser integration
  passed 86 tests. It covered Dark Engine, Dark Reader and embedded
  frames, the backdrop, fingerprinting and simulated GPU identities,
  Client Hints, privacy controls and settings.
- The standalone Qt benchmark was repeated with browser code matching
  the package. Three fresh process-tree trials and 15 synthetic samples
  per mode gave the following medians under software rendering.

| Packaged code revision | Dark Reader | Dark Engine |
| --- | ---: | ---: |
| Synthetic duration | 565.7 ms | 396.4 ms |
| Observed CPU time per five-run trial | 5.72 s | 3.99 s |
| Peak process-tree PSS | 381.1 MiB | 356.2 MiB |

- Package SHA-256:
  `a803098ffca55372286ce8d9ca9bc4a6811a32cee626faaa7f6619ec12d9791d`.

### Open work and next check

- Continue visual checks on deterministic content and investigate the
  remaining low-contrast regions. Live image comparisons need stable
  content and identical viewport conditions.
- The prototype rewrites author CSS in place. Some CSSOM property writes
  that keep the same rule identities are missed. Direct late
  `link.sheet.disabled` changes can wait until the next DOM mutation.
  Native theme hints are evaluated at initial page load. Test profile
  changes, frame handling, and the live workload before judging daily
  usability.
- Verify dependency resolution and installation on Arch/CachyOS, then
  repeat the benchmarks with a real GPU and measure scrolling and
  compositing.

## Visual review of harder pages

- A page whose grid and cards are drawn with white at 3.5 %, 5 % and 12 %
  alpha keeps those highlights. Washes made with `color-mix(... currentColor
  ...)` had turned black when evaluated in a detached canvas: contextual
  colours now stay in CSS so Chromium resolves them on their element.
- A global link colour was removed from the engine defaults. Regression
  coverage checks inherited text, a non-link anchor and authored white links.
- A blocking script holding the parser showed a white body: the engine keeps
  the top-level body dark until it has mapped the author styles.
- Dark translucent backgrounds keep their authored RGB and alpha (a neutral
  overlay fixture checks the computed value at Maximum).
- A consent iframe could cover the page with a flat dark rectangle: an
  embedded document's transparent canvas now stays transparent (an iframe
  fixture checks the composited pixels over the parent page at Maximum).
- Open shadow roots are released at the next frame after removal; reattached
  roots are rescanned and observed again.
- The visual harness records the HTTP status and excludes error responses
  from comparison metrics.

Live pages vary between captures (consent, images, page state), so a live
difference is assigned to a CSS transformation only when the content is the
same in all modes.

The expanded Qt suite passed 94 tests at `9c4ac8e`, including frames,
fingerprinting, Client Hints, privacy and settings. The experimental package
workflow built and installed the package for `9c4ac8e` in the Arch container.

| Visual review revision | Dark Reader | Dark Engine |
| --- | ---: | ---: |
| Synthetic duration | 599.7 ms | 395.7 ms |
| Observed CPU time per five-run trial | 6.26 s | 4.03 s |
| Peak process-tree PSS | 348.4 MiB | 326.6 MiB |

Speedometer 3.1 ran offline on that revision with software rendering: one
run per mode reported 7.48 ± 0.61 for Dark Reader and 9.04 ± 0.47 for Dark
Engine.

### Native palette follow-up

- The engine recognizes explicit `dark` and `system` palette markers on
  the top-level document when the authored colors confirm a readable dark
  canvas. It checks the author's colors with its early cover momentarily
  excluded. A dark marker on a light page cannot trigger a pause by itself.
- While an existing dark theme is active, the engine watches its specific
  hint or metadata and system preference. If the site switches to light,
  it starts on the same document. The Qt tests cover a changed hint, a
  declared palette switch, a misleading palette marker and replaced
  dark-only metadata. The two resume cases reproduced white backgrounds
  at `9c4ac8e` and passed with the follow-up.
- The opposite transition still needs reversible author-style changes.
  CSSOM changes with no DOM notification and the same rule identities
  also remain open.
- The comparison tool keeps reports for pages with all three captures and
  reports failed pages separately (exit status 1 for a partial comparison).
  A page can name an element it must contain, so an error page served with a
  successful HTTP status is not compared.

The expanded Qt regression suite passed 98 tests on the follow-up,
including six focused native-theme checks. No checks in that suite
were interrupted.

The follow-up repeated the standalone Qt synthetic benchmark with
software rendering and the same 15 samples and three process-tree
trials per mode.

| Native palette follow-up | Dark Reader | Dark Engine |
| --- | ---: | ---: |
| Synthetic duration | 592.5 ms | 401.0 ms |
| Observed CPU time per five-run trial | 6.65 s | 4.14 s |
| Peak process-tree PSS | 353.6 MiB | 326.2 MiB |

The next renderer check is a late replacement of a constructed
stylesheet inside an already open shadow root.


## Final package and session continuity

Continue committing intermediate work and recording completed tests, remaining defects, blockers and next steps before session limits. On resumption, fetch the experimental branch and continue from the latest checkpoint. Do not request final packaging until all agreed visual, functional, privacy and performance objectives have been verified. Only then include `[experimental-ready]` in the final commit message and push it to this branch. The package workflow skips ordinary pushes; verify the final Arch package job and artifact before reporting readiness. Do not mark unresolved or blocked objectives as complete. Do not modify main or Automat.

## Round 3 (Claude, 2026-11-27): toward replacing Dark Reader

ChatGPT's branch was brought into `wip/ike-dark-engine-r3` as one commit, with
main merged on top (the strict Content-Security-Policy fix of Dark Reader).

### Measuring

- `tests/dark_engine/conformance.py`: Dark Reader's own dynamic-theme test
  scenarios (`tests/dark_engine/scenarios/`, MIT, attributed; 150 cases, 125
  that can be shown as a page) opened with Dark Reader and with the engine;
  element by element: text colour difference (CIEDE2000), the mean colour of
  each element's box on screen, elements hidden that were shown without dark
  mode, text below 3:1 that was readable without dark mode.
- `render.py` can load a variant of the engine per mode (`DE_JS_<mode>=file`)
  for A/B comparisons; Speedometer 3.1 runs alternate the modes, 3 rounds.
- The 22 page copies of rounds 1-2 plus 6 big sites (Wikipedia, MDN, Hacker
  News, YouTube, Python docs, GitHub); GitHub's copy has no style sheets
  (github.githubassets.com is not reachable from the build machine).

### Changes

- The page's changes are handled once a frame, before it is drawn (Speedometer
  -15 % -> -12 % from the page without dark mode; Dark Reader -31 %). One search
  per added subtree instead of two gave no measurable gain and was left out.
- Conformance with Dark Reader's scenarios: 115 -> 123 of 125. Every CSS colour
  name in lists, gradients, shadows and fallbacks; pictures in custom
  properties; url() holding quotes; large light backdrops made dark with their
  details kept (Dark Reader hides them); links without their own colour as
  Dark Reader draws them; SVG colour attributes holding variables; Dark
  Reader's lock (`<meta name="darkreader-lock">`), also when added later,
  through an undo log of every value written into the page. The two cases left
  are deliberate (a system colour keyword resolved as the browser does; an SVG
  stroke from a variable keeps its colour where Dark Reader greys it).
- Bright background colours (orange, green, cyan, red) are made dark enough
  for light text (relative luminance at most 0.10): Hacker News' bar was below
  3:1 with Dark Reader and with the engine.
- Pages dark by their own design without saying so are recognised (25 points
  of the window, the background really drawn there, light text on it), after
  the page's style sheets arrived (at most 1.5 s, the dark cover meanwhile),
  and watched in case they turn light.
- Dark Reader's fix CSS is filtered for the engine (`darkfixes.engine_css`):
  rules that need Dark Reader's own output are left out, generically (3382 of
  3821 rules kept); an invalid invert selector no longer voids the list. The
  lists the engine uses: the fixes (invert, CSS, ignored inline styles,
  ignored images, ignored style sheets), the dark sites and the detector hints.
