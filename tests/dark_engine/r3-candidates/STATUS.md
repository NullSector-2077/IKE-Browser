# Dark Engine round 3: where it stopped (2026-11-27, paused by the owner)

Not measured yet: candidate variants of `ike/darkengine.js` (each a full copy
with one change), to compare with `render.py` (`DE_JS_<mode>=file`, e.g.
`--modes off,proto,protoo1` with `DE_JS_protoo1=.../o1.js`):

- `o1.js`: one search of an added subtree instead of two; custom elements
  (possible shadow-root hosts) found by XPath, without a script object for
  every element.
- `o2.js`: the observer only queues the page's changes; they are handled once
  a frame, before it is drawn (nodes added and removed in between cost nothing).
- `q1.js`: quality, not speed: a bright mapped background (orange, green, cyan)
  is made darker until light text reads on it (Hacker News' orange bar: text at
  2.1:1 with Dark Reader and with the engine).

Measured on the engine of a8f1d30 (rules changed in place), Speedometer 3.1 on
the local copy, in a container with software rendering, 3 runs each:

| run | off | Dark Reader | Dark Engine |
|---|---|---|---|
| 1 | 12.8 | 8.69 | 10.6 |
| 2 | 13.5 | 9.35 | 11.0 |
| 3 | 14.0 | 9.71 | 11.6 |
| mean | 13.43 | 9.25 (-31 %) | 11.07 (-18 %) |

Page by page (22 pages, 6 of them big sites, DE_SAME_ORIGIN_CSS=1): the engine
passes all but hn-front (the orange bar, as Dark Reader; see q1.js) and
github-repo (the copy has no style sheets: github.githubassets.com was not
reachable; the four "changed pictures" are broken-image boxes in every mode).
Dark Reader leaves mdn-page light (85 % light areas); the engine darkens it.
Pixels with a colour difference over 10 from Dark Reader: 0-1.3 % on the pages
both pass.

Next: measure o1 and o2 (3 Speedometer runs each, then together), keep what
gains more than the spread, rerun every page after each kept change; then q1;
the live big sites; the owner's check (owner-check.sh, now one self-updating
command); Fable's review.
