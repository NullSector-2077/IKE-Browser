# AUTOMAT: future scenarios and prepared responses

Analysis of 2026-11-25, written at the owner's request: plan every plausible
future scenario of I.K.E.'s own components (routine to disastrous), from what
actually broke in their past big updates, and prepare the responses before
they are needed. The full catalogue, 30 scenarios with their detection signal,
what AUTOMAT does today, the gap, the prepared response, the tier and the
drill, is in [`scenarios.json`](scenarios.json). `stubdiff-prototype.py` is the
prototype of the PyQt stub diff (section 3, recipe 1); it is not used by any
workflow yet.

Sources were read on 2026-11-25. Pages that could not be reached from the
analysis environment (docs.python.org, www.qt.io, github.com) were used
through search summaries only. Everything not checked against a primary source
is marked "not verified" in the catalogue.

## 1. What dominates

- **Qt WebEngine now jumps Chromium every quarter.** Since Qt 6.12, Qt
  WebEngine is released on its own. Its version carries the Chromium major
  (6.140 = Chromium 140), and a new minor arrives about every three months,
  each on a new Chromium major
  ([qwe-releases](https://doc.qt.io/qtwebengine/qwe-releases.html)). Users get
  it through `pacman -Syu`.
- **PyPI is about 12 days ahead of Arch.** PyQt6-WebEngine 6.140.0 reached PyPI
  on 2026-11-02 and Arch's `qt6-webengine 6.140.0-1` on 2026-11-14. That is a
  free early warning, which the `test-qt` candidate only half uses today.
- **Past breaks show the patterns to plan for:**
  - Qt 6.8 replaced the permission API.
  - Arch's qt6-webengine 6.11.0 left pages blank or garbled on some GPUs
    (not verified in detail).
  - Chromium replaced PNA with LNA.
  - Python 3.12–3.14 removed modules. Python 3.14 also caused a crash that
    showed up on Arch only (I.K.E. `dcfc0c7`).
  - adblock-rust and pyo3 ship a breaking minor every 3–5 months.
  - Gemini cut its free tier, and Groq shut down models.
  - GitHub Actions removed Node 20.
  - Widevine's old download address started answering 404.

## 2. The three structural gaps

1. **A system update that stops I.K.E. at start cannot be repaired by itself
   (S15).** `ike_boot.py` rolls back only a bad self-update. The updater runs
   inside the app and imports PyQt6. If an Arch update of Qt, PyQt, Python or
   cryptography breaks the import, both copies fail and no fix can arrive.
2. **Tier-B breakages have no one assigned (S02, S05, S12, S13).** These are
   the engine flags in `ike/app.py`, the tools, the runner image and the
   provider list. They end in "retrying" with nobody scheduled to repair them.
3. **Detection is late or silent (S02, S03, S04, S24).**
   - Arch `[testing]` is tried weekly.
   - There is no canary for Python-next or for the upstream branches.
   - Chromium ignores unknown feature names silently.
   - New fingerprinting surfaces are not measured.

## 3. Prepared responses

**Early detection.** All of these are tier B, built by Claude.

- Arch `[testing]` checked daily when a package of the closure changes, plus a
  watcher on Arch's rebuild todo list.
- `test-qt` raised to priority class 2, to use the PyPI lead.
- A weekly, non-blocking canary for the next Python.
- Canaries on the main branches of adblock-rust, Dark Reader and uBO. They only
  report and are never merged.
- `tools/engine-features.py`: checks every Chromium feature name I.K.E. turns on
  against the new Chromium's own definitions.
- A census of the fingerprinting surface: every property of window, navigator,
  screen and the worker scopes, plus the headers, compared with a kept baseline.
- Deprecation watchers for the AI providers and for GitHub's runners and
  actions.
- An expiry warning for `IKE_WORKFLOW_TOKEN`.
- A weekly canary of the services I.K.E. calls at run time.
- A watcher on Arch's qt6-webengine GPU problems.

**Deterministic recipes.** These go in `tools/automat-recipes.py` and run before
any AI, gated like an AI's fix.

1. `qt-stub-rename`: the PyQt `.pyi` stub diff.
2. `compat-fallback`: a new `ike/qtcompat.py`, so one fix works on both Qt
   versions.
3. `signature-adapter`.
4. `stdlib-replacement`: a table of removed stdlib names and their
   replacements.
5. `cargo-fix` and `clippy --fix`.
6. `rust-api-rename`, from rustdoc JSON.
7. `scriptlet-alias`, from uBO's own alias list.

**Tool-side changes** (tier B):
- `runs-on` followed as a CI pin;
- PKGBUILD renames taken from Arch's `replaces`;
- a per-icon fallback for Breeze;
- keyring refresh and retries for Arch's snapshot archive.

**Surviving at start.**
- Optional features are imported lazily, behind fences, so a missing Qt name
  turns off one feature instead of stopping the browser.
- A start-up rescue path (owner's decision; see section 5).
- A check of the AdBlock engine `.so` against glibc.

**AI providers.**
- Model discovery for every provider, so a retired model does not stop the
  chain.
- Conservative quotas.
- Recipes first, so a quarter's update needs fewer AI calls.

**New drills**, modelled on the real breaks:
- `drill-webengine`
- `drill-python`
- `drill-flag-gone`
- `drill-adblock`
- `drill-blackout`
- `drill-surface`
- `drill-startup`

## 4. Plan to 2026-12-20

**Block 2, "ready before it lands" (11-26 → 12-08):**
- the Qt API diff and its recipes, with `ike/qtcompat.py`;
- Arch `[testing]` checked daily;
- `engine-features.py`;
- provider discovery and the deprecation watchers;
- `runs-on` as a pin, the scanner of log warnings, the token expiry warning;
- the Python-next canary and `stdlib-replacement`.

**Block 3, "repair and survive" (12-09 → 12-20):**
- the scheduled repair session for tier B (owner);
- the start-up rescue path and the lazy fences (owner);
- the surface census;
- the Rust and scriptlet recipes;
- four drills;
- an engine advisory drafted automatically;
- the small items of section 3.

**After 12-20:**
- the upstream canaries;
- a licence and abandonment check;
- a successor signing key (owner);
- a second source for uBO's resources;
- mutation tests of "Nothing gets worse".

**Tiers.** Every tool, workflow, test and builder item is tier B, built by
Claude or a person. No item gives an AI a new tier-B path, and none needs
`AUTOMAT_TIER_B` or `AUTOMAT_CHATGPT_AUTOMERGE`.

## 5. Decisions for the owner

- A scheduled repair session for tier-B items left "retrying" for more than
  48 hours.
- The start-up rescue path in `ike_boot.py`. It changes the update channel.
- Any new free AI provider.
- A GPU-problem notice inside the browser.
- A successor signing key.
- Changing a default when a component has no safe fix.
