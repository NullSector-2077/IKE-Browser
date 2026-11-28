# The I.K.E. Dark Engine

I.K.E.'s own dark mode for pages (1.1.28; the only page dark mode besides
Chromium's own since 1.1.30, when Dark Reader's engine left I.K.E.). Settings
→ Web pages → Dark mode method; its own panel under the toolbar's Dark mode
button.

## How it works

- `ike/darkengine.js`, run in the isolated world of I.K.E.'s scripts (a page
  cannot stop it): one pass over the page's style sheets and inline styles,
  one generated override sheet per source sheet, then only the nodes and
  sheets that change are looked at again, once a frame before it is drawn.
- Colours are mapped as Dark Reader does (its lists are used, not its code):
  text and backgrounds, gradients, shadows, SVG colours, colours held in CSS
  variables (Tailwind's channels, shadcn/ui's `H S% L%`); bright backgrounds
  are made dark enough for light text; pictures are kept, never inverted.
- Pages that are dark by their own design are recognised, also when they do
  not declare it, and left as they are; Dark Reader's lock
  (`<meta name="darkreader-lock">`) is honoured.
- What the user writes in editors and mails keeps its colours; printing uses
  the page's own colours.
- Dark Reader's lists (`ike/resources/darkreader-data.json`, MIT): its fixes
  for single sites, the sites dark already and the hints of a site's own dark
  theme. The browser fetches them itself once a day (`ike/darklists.py`);
  `ike/darkfixes.py` keeps only the rules the engine can use
  (`darkfixes.engine_css`). The panel and Settings: `ike/darkenginepanel.py`,
  `ike/darkengine.py`.

## Measured (1.1.28)

- Speedometer 3.1 (local copy, software rendering, 3 alternating runs): about
  -15 % from the page without dark mode, against -32 % with Dark Reader.
- Dark Reader's own dynamic-theme test scenarios (`tests/dark_engine/scenarios/`,
  MIT, attributed): 122 of 125 alike; the 3 left are deliberate (a system
  colour keyword resolved as the browser does, an SVG stroke from a variable
  that keeps its colour, a bright red background made darker for light text).
- 22 page copies and the big sites reachable from the build machine
  (Wikipedia, MDN, Hacker News, Python docs).

## Tests and tools

- Automatic tests: `test_dark_engine_experiment.py`, `test_dark_engine_hard.py`,
  `test_dark_engine_detect.py`, `test_dark_engine_lists.py`,
  `test_dark_engine_panel.py`, `test_dark_csp.py`, `test_dark_blank.py`,
  `test_darklists.py`, `test_darkreader_lists.py` (docs/TESTING.md).
- `tests/dark_engine/` (not part of the automatic tests): `render.py` and
  `metrics.py` (pictures and verdicts of a page in each mode), `conformance.py`
  (Dark Reader's scenarios), `pages.py` and `localsites.py` (the page copies),
  `variants.py` (an engine variant per mode, for A/B comparisons),
  `drcompare.py` (against Dark Reader, from a checkout of 1.1.28 or earlier
  given in `DE_DR_ROOT`).
- **The live check** of real sites, on a computer that can reach them
  (read-only: a private profile that keeps nothing, plain page loads, no
  login): `tests/dark_engine/owner-check.sh` (one command that keeps a copy of
  `main` in `~/.cache/ike-dark-check`), `busy-check.sh` for one page that never
  stops loading, `live-diag.py` for the page shown in a running I.K.E.
  Their results stay on that computer.
