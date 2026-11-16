# Roadmap

I.K.E. starts at 1.0.0 for Arch Linux and CachyOS. Versions go up in order
(1.0.1, 1.0.2, …); maintenance releases prepared by GitHub Actions raise the
last number. Decisions below are agreed with the project owner; do not reopen
them without asking.

## Working rules

- Discuss changes before writing code; the owner gives the go-ahead.
- Small, targeted changes; do not rewrite what already works.
- Security and features have the same priority: no feature removed, ad
  blocking and fingerprinting protection never weakened, no general
  "fail-closed", the browser stays light and fast (measure before and after).
- Never break websites to improve a test score.
- Keep the project independent: no other browser's branding or identity, no
  external services beyond those documented in README.md.
- Each step goes on its own branch with a pull request whose base is `main`
  (no pull requests stacked on other pull requests); never write to `main`
  without the owner's approval. The repository is public: never commit
  personal data, keys or secrets.
- The private signing key stays with the owner: never in the repository, in a
  package or on GitHub Actions.
- Test on the real browser (headless PyQt6 + Qt WebEngine) with the existing
  automatic tests (`ruff check .`, `python3 -m pytest`), add tests for new
  parts, including tests that simulate attacks, and say clearly what could not
  be tested.
- Deliver an installable package (`ike-browser-<version>-1-x86_64.pkg.tar.zst`)
  built from the PKGBUILD, update CHANGELOG.md and docs/TESTING.md, and guide
  the owner step by step to sign and publish the release.
- Documentation in English; the owner talks in Italian and prefers short,
  plain explanations.
- When the owner has approved a session plan and asks for unattended work,
  carry it through without stopping for approvals on analysis, coding and
  tests. Commit and push to the session's branch often, so nothing is lost if
  the session stops, and write in "Status" below where the work stopped. Even
  then: never merge, sign or publish, and no destructive Git operations.
- Never report a check that was not actually run.

## Now: Arch Linux / CachyOS

1.0.0 is the base: the browser, its protections, the signed self-update and
the daily component maintenance on GitHub Actions, for Arch-based systems only.

## Next

Plan approved by the owner on 2026-11-16. It joins the owner's "master
roadmap" (phases 0–14: brand, interface, toolbar, shield, link preview bar,
new-tab background, code review, security audit, platforms, component manager,
Windows codecs, porting plan, tests, final review) with the earlier list.
Versions go up by one per session: 1.0.1, 1.0.2, 1.0.3. In every session the
tests cover what it changes (phase 13), CHANGELOG.md and docs/TESTING.md are
updated, and the work goes on one branch with one pull request to `main`. When
an earlier version is not merged yet, the next branch starts from it, so its
pull request also contains the earlier one; the owner merges them in order.

Principles for every session (from the owner):
- Do not overturn the existing interface. Every customisation keeps working
  (interface themes, colours, fonts) and I.K.E. keeps following the system
  theme (Plasma / Breeze): no own palette, no fixed colours; new elements use
  the existing theme system; existing settings are never reset.
- No heavy effects, no needless dependencies; the Rust core, ad blocking and
  fingerprinting protection are never weakened; security is never traded for
  compatibility.
- Document every important change.

### 1.0.1 — clean-up and brand (done, waiting for the owner)

Branch `ike-1.0.1`. Done and tested:

1. The one-time import is removed (`ike/legacy.py`, its calls, its test, the
   old-vault fallback, `conflicts` / `replaces`).
2. Brand: the logo, every icon size and the new tab page show "I.K.E" and
   "Internet Kontrol Experience", lettered in Orbitron (OFL, licence in
   `licenses/`) and drawn as paths by `tools/make-brand.py`; the font is not
   shipped and the interface fonts are unchanged.
3. The toolbar's shield is drawn 18% larger inside the same button, as shapes
   (sharp at every scale).
4. No link preview bar; the status bar stays for zoom and toolbar messages.

`__min_system__` is 1.0.1: the icons installed under `/usr/share/icons`
changed, so 1.0.0 announces this release instead of self-updating (the owner
may put it back to 1.0.0 before signing if a stale menu icon is acceptable).

### 1.0.2 — toolbar, interface polish, new-tab background (done, waiting for the owner)

Branch `ike-1.0.2` (contains 1.0.1). Done and tested:

1. Toolbar. Cause of the unreliable moving: the toolbar was rearranged while
   the button was dragged, and QToolBar builds a new button each time an
   action is inserted, so the button receiving the mouse events was destroyed
   at the first step (the drag stopped, the button landed in a wrong place,
   nothing was saved, and the new button could not be dragged). Now
   `ike/toolbar.py` holds one description of the arrangement
   (`ToolbarLayout`) and `ToolbarMover` shows a marker during the drag and
   applies the move once, on release. QToolBar is kept (it can do this).
   "Customise toolbar" mode, reset to default, the long press kept. Buttons
   that do not fit a narrow window go under a » button, so the address bar,
   the menu and the window buttons stay in view at every width and scale.
2. Interface effects in `ike/effects.py`: menus and the shield panel fade in,
   gliding hover of the close buttons, smooth loading line, loading mark on
   tabs; setting `ui_effects`; off with the desktop's reduced motion; no
   measurable cost. Icons were left as they are: their uniformity can only be
   judged on a real Plasma session.
3. New-tab background photo in `ike/newtabbg.py`.

### 1.0.3 — code review and security audit (done, waiting for the owner)

Branch `ike-1.0.3` (contains 1.0.1 and 1.0.2). The report is in
[docs/review/](docs/review/README.md): one finding rated High (a page opened
from a file could read any other file), four Medium, ten Low, all fixed with
regression tests; eleven open issues, none above Medium, three of which need a
decision of the owner (Widevine integrity and updates, when saved passwords
are filled, CRX signatures). The plan that was followed:


1. **Code review of the whole project** (Python modules, Rust core,
   Python ↔ Rust interface, configuration, dependencies, interface, packaging,
   workflows, tests): duplicated or unused code, overloaded classes and
   modules, needless dependencies, unused imports and variables, incomplete
   error handling, possible leaks, costly or repeated operations, blocking
   loads, concurrency, Qt signals and widget lifetimes, tight coupling,
   Python / Rust mismatches. Write the findings first; change only what has a
   technical reason; keep internal APIs and settings compatible. Performance:
   start-up, tab opening, memory, CPU, page loading measured before and after;
   no optimisation claimed without a measurement.
2. **Security audit** (a review, not only automatic scanning):
   - Qt WebEngine / Chromium: real version and security state, sandbox,
     process isolation, TLS certificates, permissions, local files,
     JavaScript settings, local APIs, custom schemes, harmful content, any
     setting that turns a protection off. The sandbox is never disabled to fix
     compatibility (the CI runner is the only exception, as now).
   - Python ↔ Rust: FFI, memory, input validation, deserialisation, error
     handling, crashes, trust boundaries.
   - Ad blocking and fingerprinting: filter robustness, list updates, rule
     integrity, bypasses, exceptions, tracker protection, consistency,
     breakage of sites.
   - Downloads, cookies, cache, profiles, local storage, passwords,
     permissions, sensitive data, clearing browsing data, opening external
     applications, URL handling.
   - Dependencies (Python, Rust, Qt, Chromium, bundled components): known
     vulnerabilities from official advisories, outdated or unmaintained
     packages, licences, needless components.
   - Findings rated Critical / High / Medium / Low; fix what can be fixed
     safely, with regression tests run locally (never against third-party
     sites). Never call the browser 100% secure; open issues and the limits of
     the audit are written down.
3. **Final review** (phase 14) of the whole repository after these changes:
   errors introduced, untidy or duplicated code, security, crashes, packaging;
   check that the visual changes broke nothing; fix what is safe and run the
   affected tests again.
4. **Report** in `docs/review/` (English, new files only): initial state,
   architecture, changes and files, toolbar problems found and fixed, visual
   changes, link preview bar, clean-up results, optimisations, audit results,
   fixed and still open vulnerabilities, compatibility, dependencies, Linux
   and Windows strategy, component manager, codecs and licences, tests run,
   tests that could not be run, performance, remaining work, next phases.

### Platform study (documents only: no version, no code) (done, waiting for the owner)

Branch `docs/platform-study` (contains 1.0.3). Written in
[docs/platforms/](docs/platforms/README.md). Main results: I.K.E. needs Qt
WebEngine 6.8 or later (Arch / CachyOS, Debian 13, Ubuntu 26.04, Fedora 43+
have it; Debian 12, Ubuntu 24.04 and Mint 22 do not); nothing inside Qt
WebEngine can be downloaded separately, codecs are fixed when it is built;
the proposed order is AUR, checks on each distribution's own Qt, Flatpak,
DEB and RPM, Windows last. Nothing was tried on those systems: what is still
to verify is marked. The plan that was followed:


In `docs/platforms/` (English), citing the official sources used:
- **Linux** — Arch / CachyOS, Debian, Ubuntu, Linux Mint, Fedora: Python, Qt
  and Qt WebEngine versions, system and multimedia libraries, fonts,
  certificates, hardware acceleration, Wayland / X11, PipeWire, ABI, native
  dependencies; realistic minimum versions. DEB, RPM, PKGBUILD, AppImage and
  Flatpak compared on size, maintenance, security, updates, dependencies and
  compatibility; a concrete strategy (not the easiest format by default).
- **Component manager** (Linux and Windows): what can really be separated
  from Qt WebEngine and how it is loaded; detection, compatible versions,
  download, integrity (signed manifests, SHA-256, TLS, pinned versions),
  atomic installation, update, repair, roll-back, no unauthorised downgrades,
  no unverified binaries, the user's folder without admin rights, no SDKs for
  the user. Native (distribution packages) versus self-contained; never mix
  system Qt with downloaded Qt.
- **Windows**: Qt runtime, Qt WebEngine, helper processes, Chromium
  resources, Visual C++ runtime, official Qt deployment tools, optional
  components, repeatable and verifiable builds. Codecs: whether Qt WebEngine
  can use Windows' own decoders (Media Foundation, H.264, audio) — Qt
  Multimedia using Media Foundation does not mean Qt WebEngine does; Qt
  WebEngine decodes through its own FFmpeg and needs proprietary codecs
  enabled when it is built — to be verified. A matrix: redistributable /
  usable through the system / needs checks or a licence / must not be shipped,
  for Qt, Chromium, FFmpeg, proprietary codecs and patents (also by
  territory). No definitive legal statements.
- **Porting plan** per platform (Arch / CachyOS, Debian, Ubuntu, Mint,
  Fedora, Windows): dependencies, format, Qt WebEngine strategy, component
  manager, codecs and media, updates, signing and integrity, tests needed,
  problems to solve, technical complexity; what already works versus what
  needs changes. A platform is not "done" because the code looks compatible.

### 1.1.0 — the Cyber theme, new-tab tiles, monthly counter (approved by the owner on 2026-11-16)

Branch `ike-1.1.0` (starts from `docs/platform-study`). The design was agreed
on a shared canvas before any code. Rule of the whole version: **"Follow the
system" stays the default and behaves exactly as before**; everything "Cyber"
is one optional theme of I.K.E.'s own, drawn with what is already there (Qt
Widgets, QPainter, the HTML of the new tab page) — no new library, no blur
behind the window. No existing setting is reset or changes meaning.

1. **Counter per month.** The new tab page shows the trackers and ads blocked
   in the current month and in the month before; it starts again on the first
   of the month. The all-time total goes on being counted (`blocked_total`)
   and can be chosen instead. Setting `blocked_counter` (`month` | `total`).
2. **Site tiles on the new tab page**, between the search field and the
   counter: the user's bookmarks or the most visited sites (local history
   only), or none; site icon or initial; a tile to add one; a tile can be
   hidden without deleting anything. Setting `newtab_tiles`
   (`bookmarks` | `visited` | `none`). Titles and addresses are untrusted
   text: escaped, web addresses only — with an attack test.
3. **The "I.K.E. Cyber" theme**: a ready-made theme (dark, one accent colour)
   with a look of its own — cut corners, thin luminous lines, a grid on the
   new tab page when there is no photo. Options, shown only with this theme:
   accent colour, shape of the tabs, glow, cut corners. The other ready-made
   and custom themes stay.
4. **Tab shapes of the Cyber theme**, horizontal and vertical, chosen by the
   user: *Smusso* (one cut corner, line above the current tab), *Lama*
   (slanted sides, line below), *Mirino* (no fill, the current tab between
   two brackets). Dragging, closing, groups, sound and the loading mark work
   as before. With "Follow the system" the tabs are the desktop's.
5. **Light effects**, all under the existing "Interface effects" switch and
   off when the desktop asks for no animations: the accent line glides to the
   new current tab; the address field lights up on focus; tabs open and
   close with a short slide; the shield pulses once when it blocks; the
   counter counts up when the new tab opens; a lit corner on hover.
6. **Small things**: an equaliser on a tab that plays sound; the tab preview,
   group colour, download ring, menus and shield panel in the Cyber look; the
   site's domain emphasised in the address field; a short fade when the theme
   changes.
7. **Clear options and a clear suggestion.** Settings → Appearance shows the
   theme choice first, "Follow the system" marked as the default and "I.K.E.
   Cyber" as recommended; the new tab page suggests the Cyber theme once,
   with "Try it" and "Not now", and it is one click to go back.
8. Dropped on purpose: a live trace of blocked requests under the toolbar (it
   would distract).
9. Tests for each part (shapes drawn at several sizes and scales, drag and
   close with the Cyber tabs, month roll-over with a fixed clock, tiles with
   hostile titles, nothing changed with "Follow the system"); processor time
   at rest and in use measured against 1.0.3; translations in the seven
   languages; package built and tested.

### Status

- 2026-11-16: plan written.
- 2026-11-16: unattended session started. 1.0.1 finished on branch
  `ike-1.0.1` (pull request #5, 129 tests passed, package built and tested).
- 1.0.2 finished on branch `ike-1.0.2` (146 tests passed, package built and
  tested); next is 1.0.3 on `ike-1.0.3`. Noted for the 1.0.3 audit: web
  pages can load `ike:logo` and frame `ike:newtab` (a way to recognise the
  browser); settings of the wrong type are not checked when read.
- 1.0.3 finished on branch `ike-1.0.3` (172 tests, package built and
  tested; report in `docs/review/`, pull request #7).
- Platform study finished on branch `docs/platform-study` (documents only).
  Everything of this plan is done and waits for the owner: review, merge
  (#4, #5, #6, #7, then the study), sign and publish. Nothing was merged,
  signed or published by the unattended session.
- 1.1.0 started on branch `ike-1.1.0` (plan above approved). Done so far:
  nothing yet.

### Also planned

- **AUR**: publish I.K.E. on the Arch User Repository — when the owner says it
  is time.
- **Licence**: GPL-3.0-or-later for now; the owner may decide to change it.

## Later

- Other Linux distributions and Windows: implementation planned with the owner
  after the platform study.
- Android: a separate project. Qt WebEngine does not exist on Android, so it
  would need Android's WebView and a rework of ad blocking, fingerprinting
  protection and user scripts.

## Starting a new session

The owner opens a new conversation, attaches this repository and pastes this
prompt, replacing `<TASK>` and `<VERSION>` (for unattended work, add: "il piano
è già approvato, lavora da solo senza chiedere il vai, fai commit e push
spesso"):

```
Ciao! Lavoriamo a I.K.E. Browser, repository GitHub NullSector-2077/IKE-Browser
(pubblico). Collegalo a questa sessione e leggi prima README.md, CHANGELOG.md,
docs/TESTING.md, docs/UPDATES.md, docs/MAINTENANCE.md e soprattutto
ROADMAP.md: lì ci sono la lista dei lavori, le decisioni già prese e le regole
di lavoro.

Oggi facciamo: <TASK> (versione <VERSION>).

Segui le regole di lavoro della ROADMAP. Prima di scrivere codice dimmi cosa
farai e aspetta il mio "vai". Alla fine consegnami
ike-browser-<VERSION>-1-x86_64.pkg.tar.zst costruito dal PKGBUILD e guidami
passo passo a firmare e pubblicare la release.

Il mio sistema: CachyOS, KDE Plasma 6 su Wayland, shell fish, terminale
Konsole. Il comando di installazione deve puntare a
"/mnt/CachyStorage/D O W N L O A D/". Rispondimi in italiano, in modo breve e
chiaro.
```

## Known limits to keep in mind

- With DejaVu Sans as the system font, Settings → Appearance scrolls sideways
  by a few pixels in German and Spanish (fine with Noto Sans, Plasma's font).
- "Cookies and site data" deletes cookies at once; local storage, databases
  and service workers go when I.K.E. starts next (Qt WebEngine cannot delete
  them while it runs). The dialog says so.
- A page opened from a file can still load pictures, media, style sheets and
  scripts from anywhere on the disk (saved pages need it), so it can tell
  whether such a file exists; it can no longer read other files.
- Open issues of the 1.0.3 audit: see `docs/review/security-audit.md`.
- Media controls: next / previous track are not offered (they would need a
  hook inside the pages' own scripts); media inside frames (embedded players)
  are not seen.
- KRunner may need to restart once (or a new login) before it sees I.K.E.'s
  runner file the first time.
- User scripts: `GM_registerMenuCommand` is accepted but shows no menu;
  `GM_xmlhttpRequest` to other sites works from the page but not from frames.
  A name that resolves to a public address when checked and to a local one
  when the request is made (DNS rebinding) is not caught. Scripts in the same
  world trust each other: a malicious installed script could watch another
  one's messages (scripts are installed by the user).
- The graphics card presented to sites is a plausible common model; a script
  comparing rendering with the model could notice the mismatch.
- The bundled Dark Reader page dark mode is not reliable; Qt's own dark mode
  works and is the one to use.
- The ad-blocking engine is adblock-rust (Brave's open-source library, MPL-2.0)
  with uBlock Origin / EasyList filter lists and uBlock Origin scriptlets; the
  integration around them is I.K.E.'s own.
