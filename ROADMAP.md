# Roadmap

I.K.E. is a browser for Arch Linux and CachyOS. Versions go up in order
(1.1.17, 1.1.18, …); maintenance releases prepared by GitHub Actions raise the
last number. The history of every version is in CHANGELOG.md. Decisions below
are agreed with the project owner; do not reopen them without asking.

## Working rules

- Plans are agreed with the owner first; once a plan is approved, the work
  is carried through without asking again (see CLAUDE.md).
- Small, targeted changes; do not rewrite what already works.
- Security and features have the same priority: no feature removed, ad
  blocking and fingerprinting protection never weakened, no general
  "fail-closed", the browser stays light and fast (measure before and after).
- Never break websites to improve a test score.
- Keep the project independent: no other browser's branding or identity, no
  external services beyond those documented in README.md.
- Each step goes on its own branch with a pull request whose base is `main`
  (no pull requests stacked on other pull requests). Since 2026-11-18 Claude
  merges pull requests by itself once GitHub Actions is green; signing and
  publishing stay with the owner (see CLAUDE.md). The repository is public:
  never commit personal data, keys or secrets.
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
  then: never sign or publish, and no destructive Git operations.
- Never report a check that was not actually run.
- **Every release reaches every user by itself** (owner's rule, 2026-11-18,
  for Arch and for every future platform: other Linux, Windows...): each
  version merged into `main` and signed by the owner is installed
  automatically at the next start of I.K.E., the AdBlock engine and the other
  bundled components included. Nobody (the owner included) has to visit
  GitHub, run a command or install a package by hand. The self-update carries
  everything it can (since 1.1.12 also the engine, in `ike/_engine`);
  `__min_system__` is raised only when nothing else is possible, and then the
  release must say how it still reaches users without commands. The web engine
  of the system (Arch's `qt6-webengine`) updates with the system. Automatic
  installation is the default (1.1.13); users may turn updates off, at their
  own risk.
- Pages must not be able to see I.K.E.: outside the protections the user
  chose, nothing in a page is changed (1.1.12), and on sensitive services
  (sign-in, AI Studio, cloud consoles, payments) the protections stay light
  (1.1.14: Google's own requests there are left alone, as Brave does with its
  hand-written exceptions, and PayPal's and Stripe's parts of any shop too;
  other companies' trackers stay blocked), so
  anti-abuse checks never refuse the user.

## Owner's decisions

- **Arch Linux / CachyOS only** (2026-11-17). Other Linux distributions and
  Windows were suspended, and on 2026-11-20 their pull requests (#10, #11,
  #13, #14, #16) were closed; the branches stay as the archive and are never
  deleted: `windows/port`, `windows/engine`, `linux/flatpak`,
  `linux/packages`, `linux/distro-checks`, `automation/audit`,
  `docs/multiplatform-plan`. Their Arch container check now runs weekly on
  `main` (`.github/workflows/arch.yml`).
- One change at a time, each tried by the owner on CachyOS. Menus, settings
  and navigation are not reorganised, and YouTube ad blocking is not changed,
  without asking.
- I.K.E. runs on old computers (e.g. an Ivy Bridge i5-3570K) and any graphics
  card; the web engine chooses the GPU path, no forced flags.
- The update check runs once every 24 hours; every signed release reaches
  every user by itself (rule above).
- At Strict and Maximum Chrome's version is the reduced one (140.0.0.0) in
  JavaScript and in the client hints alike (2026-11-20).
- Filter lists without a licence are not shipped (one was removed in 1.1.18,
  CHANGELOG).
- Android would be a separate project (Qt WebEngine does not exist there).

## Status

- 1.1.18 (speed without less protection, privacy fixes from an independent
  review, YouTube, automation, licences) is merged into `main` and waits for
  the owner's signature (`python3 tools/publish.py`).
- The owner checks the YouTube anti-adblock notice on CachyOS with 1.1.18.

## Open work

- **Workers started from a file**: `experiment/file-workers` (see Known
  limits); merged only if the owner wants it, probably as an option.
- **Dark Reader**: the early plain background could leave from inside
  `<head>` to avoid one whole-page restyle (unfinished, untested work on
  `handover/perf/1.1.18-darkreader-3`).
- **Privacy items of the 1.1.18 review left for later**: canvas and audio
  noise that a page can remove, font masking, pages that can tell I.K.E. from
  stack traces, a home-made public-suffix list, re-encoded tracking-parameter
  clean-up, impossible combinations at Strict and Maximum (screen,
  languages).
- A pinned daily `cargo audit` of the Rust crates of the AdBlock engine.
- **AUR**: publish I.K.E. there when the owner says it is time.

## Starting a new session

The owner opens a new conversation with this repository attached and asks
for the task in Italian. Claude reads CLAUDE.md, README.md, this file and
CHANGELOG.md first, and docs/TESTING.md, docs/UPDATES.md and
docs/MAINTENANCE.md when the task touches them.

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
- Media controls: next / previous are offered only where the site declares them
  (Media Session API); "Raise" (bring the tab to the front) may only make the
  task manager entry blink on Wayland, where a window cannot take the focus
  without a token from the desktop.
- User scripts: `GM_registerMenuCommand` is accepted but shows no menu;
  `GM_xmlhttpRequest` to other sites works from the page but not from frames.
  A name that resolves to a public address when checked and to a local one
  when the request is made (DNS rebinding) is not caught. Scripts in the same
  world trust each other: a malicious installed script could watch another
  one's messages (scripts are installed by the user).
- The graphics card presented to sites at Balanced is a common Intel or NVIDIA
  model; a script comparing rendering with the model could notice the
  mismatch. At Strict and Maximum no model is named.
- Page dark mode with Dark Reader costs more than the engine's own dark mode
  (it rewrites the page's style sheets): measured in
  docs/review/tests-and-performance.md; the engine's dark mode is the lighter
  choice.
- A worker a site starts from a file of its own (`new Worker("/w.js")`) sees
  the real values (graphics card, cores): Qt WebEngine gives no way to add a
  script to it. A partial way around it is on the branch
  `experiment/file-workers`, waiting for the owner's decision.
- The ad-blocking engine is adblock-rust (Brave's open-source library, MPL-2.0)
  with uBlock Origin / EasyList filter lists and uBlock Origin scriptlets; the
  integration around them is I.K.E.'s own.
