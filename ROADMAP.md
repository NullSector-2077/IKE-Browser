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
  (no pull requests stacked on other pull requests). Since 2026-11-22 no AI
  agent merges into `main` by itself and no agent merges its own work:
  Claude merges the PRs the owner asked for when all checks are green (the
  owner's standing order), ChatGPT only on the owner's order; the
  automation's own PRs (daily candidate, AutoFix fix, isolated update) are
  merged by the workflow's own code from `main` only when fully verified
  (the verified merge, below; since AUTOMAT also an AI's fix of protected
  code, under the static guard and two AI reviews), ChatGPT's and people's
  pull requests wait for the owner (see CLAUDE.md); signing and publishing
  stay with the owner. The repository is
  public: never commit personal data, keys or secrets.
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
  (1.1.14: Google's own requests there are left alone, and PayPal's and Stripe's parts of any shop too;
  other companies' trackers stay blocked), so
  anti-abuse checks never refuse the user.

## Owner's decisions

- 2026-11-24, **a stricter gate for an AI's change of the fingerprint
  protection, permanent** (the owner's decision; the owner never has to
  intervene). An independent review showed weakened copies of
  `ike/resources/fingerprint.js` that pass both the static guard and "Nothing
  gets worse". So an AI's change of that file merges by itself only with
  three independent AI reviewers and with only "stricter" fingerprinting rows
  in "Nothing gets worse"; short of that it is retried by the automatic fix
  with the reason, like any refused AI fix. The gate stays for good, also
  after "Nothing gets worse" and the static guard are hardened. Nothing else
  changes (`tools/tier-b.py` `STRICT_GATE_FILES`, `tools/automerge.py`
  `strict_gate`; docs/MAINTENANCE.md, "AUTOMAT, part 2").
- 2026-11-24, **AUTOMAT, block 1: real updates first, and the branches
  cleaned** (the owner: "use the free AIs every day, always when needed,
  above all for real updates; what is left goes to self-evolution, drills
  etc.", and: real updates may use all of the free quota at any time; what
  they leave each day goes to self-improvement). AI work has four classes
  (security fixes, updates of what ships, the CI's, background such as the
  drill). The first two may always use all of every free quota; the other
  two run only while none of the first is pending (or while that cannot be
  read), and only in each provider's leftover window (the last hours before
  its reset; with a reset not verified, also never during the day's
  maintenance window), each provider counted on its own day; one
  candidate's share of a provider holds only while another real update is
  pending at the same time;
  OpenRouter's free models are one budget of the account
  (`tools/ai-quota.py`, docs/MAINTENANCE.md "Real updates first"). The
  verified merge deletes the candidate branch it merged, and a weekly sweep
  deletes branches merged into `main` at their tip, never a protected one or
  one with commits not in `main`, always by compare-and-swap
  (`tools/branch-sweep.py`, `branch-sweep.yml`). Still to do by a person:
  check each provider's reset time (all marked unverified).
- 2026-11-23, **the menus and the Settings regrouped again, for 1.1.24**
  (work package B2; the owner: "puoi riorganizzarli tu, ma devono essere
  fatti con criterio e logica, e con le scritte centrate bene, annota anche
  il fatto di risolvere sta parte di altro"). The ☰ menu goes new tabs and
  windows → this page → print and save → history, bookmarks, downloads →
  protection, extensions, More → Settings, Help → Quit; "More" ("Altro")
  holds the menu bar's File, Edit, View and Tools with their icons, and its
  texts no longer touch the submenu arrows (in Breeze they did: fixed for
  every menu, tests/test_menus_124.py and the text-fit test). Settings: the
  pages in the order of everyday use, Appearance in groups, the options of
  each page on one line, a search field. Five toolbar buttons a user can
  add, off by default. Nothing removed, every shortcut kept. Any further
  reorganisation goes back to asking the owner.
- 2026-11-23, **the AUTOMAT drill** (the owner's request: "un test fake
  fatto bene, molto complicato, uno scenario reale di un aggiornamento
  massivo di Qt e di tutte le altre componenti installabili, per vedere se
  le IA riescono a risolvere il problema"). One command,
  `gh workflow run automat-drill.yml --ref main`, starts a simulated major
  release of Qt, PyQt and jeepney on `automation/update/drill-qt` (six
  breaks in I.K.E.'s code, one in a protected module), and AUTOMAT's real
  chain fixes it; it is never merged, never in the signing notice or the
  ledger, and mails the owner once, at its end, with the report
  (`tools/automat-drill.py`, docs/MAINTENANCE.md "The AUTOMAT drill").
- 2026-11-23, **AUTOMAT, part 2** (what the first part left unbuilt; the
  owner wants nothing left behind). Built, all inert towards `main` until a
  check passes: the notice "DEVI AIUTARCI CON CHATGPT" after
  `AUTOMAT_CHATGPT_AFTER` (default 4) failed attempts in a row on one error,
  or two days without any free provider, with a ready message for ChatGPT
  (`tools/automat-help.py`); the budget of each provider's free quota, its
  limits as data (`tools/ai-quota.json`, unverified ones marked) corrected by
  the live headers, a reserve kept for the reviewers (`tools/ai-quota.py`);
  deterministic recipes before any AI (`tools/automat-recipes.py`); the
  upstream change in the context (`tools/upstream-diff.py`); the inner loop
  (strict patch format, cheap checks, the errors back to the same AI, the
  failing tests first: `tools/autofix-inner.py`, the job `try`); routing by
  kind of task and loop detection (`tools/automat-route.py`). The static
  guard also refuses a new statement that binds an old name again. Two
  switches, **off until the owner turns them on** in GitHub's settings:
  `AUTOMAT_CHATGPT_AUTOMERGE` (a verified ChatGPT fix is adopted and merges
  under the gate of an AI's fix) and `AUTOMAT_TIER_B` (tier B in its
  narrowest form: a workflow's pinned versions; statements added to
  `ike/app.py`, `ike/updater.py`, `ike_boot.py` outside their frozen
  functions; three reviewers). Still to do by a person: check each
  provider's limits against its documentation and mark them verified
  (docs/MAINTENANCE.md, "AUTOMAT, part 2").
- 2026-11-22, **AUTOMAT**, the full automation (the owner's name for the
  whole automatic maintenance; in the owner's words: "intervento umano
  limitato solo alla firma... 100% lavoro in team di ia", and "niente
  annullamenti automatici... niente deve rimanere indietro"). The owner's
  only step is the signature. An AI fix of tier-A protected code (the
  ad-blocking adapter, the safety modules, I.K.E.'s page scripts) merges by
  itself when it is fully verified, "Nothing gets worse" (no-regression)
  passed, the static guard accepts it (`tools/fix-guard.py`: only statements
  added) and two independent AI reviewers of other providers approved that
  commit (`tools/ai-review.py`). Tier B (workflows, tests, tools, sandbox and
  start, signing and updates, the package, YouTube's ad blocking) is never an
  AI's. Nothing waits for a person, nothing is closed: the attempts are
  capped per day and go on the next day ("retrying" in the ledger, with
  AUTOMAT's memory of what was tried, `tools/automat-memory.py`); a refresh
  conflict or a second version raise is resolved by a rebuild or by main
  merged in; only a security finding with no safe fix stays blocked and the
  owner is told. Every external component is declared in `components.json`
  and updated by the same chain (a guard fails when one is not). The signing
  notice lists everything the signature covers. For AUTOMAT to run with no
  one, the owner sets the repository secret `IKE_WORKFLOW_TOKEN` once
  (docs/MAINTENANCE.md, "AUTOMAT: the full automation").
- 2026-11-22, everything automatic and verified converges into `main`, then
  one notice to sign: several verified merges go into the same unpublished
  version (a second raise on top waits for a person); a verified candidate
  behind `main` is refreshed by itself (`main` merged into its branch,
  CHANGELOG.md and the version files resolved deterministically, any other
  conflict for a person, its tests again, no AI) and the others are judged
  again after every merge (docs/MAINTENANCE.md, "The verified merge").
- 2026-11-22, the verified merge (later the same day as "nothing merges by
  itself", which stays for everything else): the AIs fix and carry the work
  on through the tests; the system prepares the updated version and the
  owner only signs it when it is ready and has passed the tests. The
  workflow merges the automation's own PR by itself when everything is green
  and verified (like the old "Merge green fixes", but only for complete
  candidates), then the signing notice: the daily candidate, an AutoFix fix
  or an isolated update, merged by `tools/automerge.py` read from `main`,
  never by an agent, only when every check of its last commit passed (tests,
  sandbox, Security, Arch Linux, which now runs on the candidate), every
  category its components need passed (nothing "not verified", no required
  test skipped), no test file changed or removed, no protected file or
  workflow touched, licences up to date and no open security finding.
  Anything less stays a PR, one comment naming the owner, needs-person or
  blocked in the ledger. ChatGPT's and people's PRs keep waiting for the
  owner's order. The owner's standing order to Claude: Claude merges the PRs
  the owner asked for when all checks are green.
- 2026-11-21, for 1.1.21 (obsolete since 1.1.30: Dark Reader's engine left
  I.K.E., only its lists remain, `tools/build-darkreader-lists.py`): I.K.E.'s
  changes to Dark Reader (then `tools/build-darkreader.py`) stay only when their speed gain was
  measured (larger than the spread in two runs). Kept, 9 families:
  color-variables, style-groups, shadow-texts, shadow-host-walk (measured
  against all of 1.1.20's changes); dark-copy with shadow-styles-once,
  declarations-modifiable, variables-none (measured when added back to a
  build with only the first four); style-moves (measured when added back to
  a build with those eight). Removed, 7 families: svg-sizes, adopted-once,
  adopted-vars-first, one-text, var-rule-same-text, image-selectors,
  inline-style-key. The engine stays
  closer to Dark Reader's own and its automatic updates have fewer texts to
  match (numbers: docs/review/tests-and-performance.md, "1.1.21"). A new
  change to Dark Reader comes in only with a measured gain.
- 2026-11-21, for 1.1.20: menus and Settings regrouped with icons and short
  explanations, an "I.K.E. extensions" section with a switch for each;
  Ctrl+Shift+A opens the extensions; Chrome's default font families for
  every page; at the global level Maximum the engine itself runs in en-US;
  the font allowlist waits for 1.1.21.
- **Arch Linux / CachyOS only** (2026-11-17). Other Linux distributions and
  Windows were suspended, and on 2026-11-20 their pull requests (#10, #11,
  #13, #14, #16) were closed; the branches stay as the archive and are never
  deleted: `windows/port`, `windows/engine`, `linux/flatpak`,
  `linux/packages`, `linux/distro-checks`, `automation/audit`,
  `docs/multiplatform-plan`. Their Arch container check now runs weekly on
  `main` (`.github/workflows/arch.yml`).
- One change at a time, each tried by the owner before release. Menus, settings
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
- **Menus, Settings and I.K.E. extensions** (2026-11-21, asked and approved
  by the owner, branch `ui/1.1.20-menus`): the ☰ menu and the menu bar
  grouped by what an ordinary user looks for, eleven Settings pages with an
  explanation under each option, and the built-in features listed as "I.K.E.
  extensions" with an on/off switch each (`ike/ikeextensions.py`). No option
  removed, every setting keeps its name, default and meaning; the two new
  extensions (automatic scrolling, open the selected text with the middle
  button) are off until the user turns them on.

## Status

- **1.1.31** is prepared as one release (the owner: one test round for the
  whole release): the new tab page customised from itself (its own small
  panels), a clearer glass, the logo's light, I.K.E. Kontrol (`ike:kontrol`),
  pages that change softly, the sun and the moon, the shield's turn, the
  Dark Engine's empty layers and the backdrop between pages (#224), and the
  comparison session's package (#226: phishing list, vault lock, spelling,
  history kept for a chosen time, print preview). Published on 2026-11-28
  (#227, two test rounds: the first found `kontrol.html` missing from
  `tools/inventory.py` and a fade test that raced on a fast runner).
- **Next: 1.1.32**, the site-compatibility work of two other conversations.
  Until it is published AUTOMAT merges nothing into `main` (the owner's
  decision of 2026-11-28): "Merge green fixes" (`automerge.yml`) is disabled
  and AUTOMAT re-enables it when 1.1.32 is out. AUTOMAT's own fixes (#229,
  #230, #231, #234) go in together as #235, at the owner's request.
- **Dark Engine, open points** (for the next conversation): the owner saw a
  white flash on a fast dark site (1.1.31 gives the backdrop again at every
  new page and fades pages: to be verified on the owner's PC) and had a
  white box on one site (empty layers, fixed in #224: to be verified). The
  diagnosis on the owner's own I.K.E. is `tests/dark_engine/live-diag.py`
  (its docstring says how), the private-profile one `owner-check.sh`
  (`docs/DARK-ENGINE.md`). The branches `feature/1.1.29-dark-engine` and
  `experiment/ike-dark-engine` are kept by the owner: never delete them.
- **1.1.30** (1.1.29 included, never published on its own) is published.
  Its work: the I.K.E. Dark Engine as the only page dark mode (Dark Reader's
  engine removed, its lists kept), the menus and Settings reorganised, the
  level Strict shown as Kontrol, Brave's debounce list (skip the tracker's
  stop), the shield's figures in the logo's typeface, the privacy package
  (common English, the broom's panel, Cover Your Tracks' "randomized").
- **AUTOMAT** (the maintenance session), 2026-11-28. Open: #205 (learned
  limits kept for the next days), #212, #215. Next: the drill as the AIs'
  field test after 1.1.30 (#208); then one AI caller in place of five
  (simplification D). Waiting for the owner: the weekly Claude session for
  tier B; the start-up rescue path in ike_boot.py.
- AUTOMAT block 1 (2026-11-24, branch `automation/block1-priority`, merged):
  real updates may use all of the free quota, background work (the drill,
  the CI's updates) only the day's leftovers and never while a real update
  is pending, OpenRouter's free models as one budget, the merged candidate
  branches deleted and a weekly branch sweep (two independent reviews'
  findings fixed); the providers' reset times are not verified.
- **Kept for the owner's decision**: `experiment/file-workers` (workers
  started from a file) and `feature/engine-identity-check` (a weekly check of
  the engine's identity in the signing notice), never merged.

## Open work

- **Security** (docs/SECURITY.md): 1.1.19 turns on the engine's Local
  Network Access (it covers DNS rebinding) for every site, with no per-site
  exceptions: the engine has no per-site permission, and its only way to let
  a device through (`--ip-address-space-overrides`, now an unsafe switch)
  opens it to every site (tried: an exception for one site let another
  through). Left open: WebSockets by a public name that points home (the
  engine only warns in Chromium 140), and behind a proxy the engine sees
  only the proxy's address. The owner's decision (2026-11-21): no setting to
  turn the protection off; a per-site permission comes when Qt WebEngine
  passes the engine's permission request to the browser. Certificate Transparency, HSTS preload
  and Arch's V8 hardening to be verified on a real system.
- **Smooth page loading (1.1.19, owner's request)**: measured with
  `tests/measure_smooth.py` (docs/review/tests-and-performance.md):
  pictures, big photos, lazy pictures, growing feeds and slow pages show no
  cost of I.K.E. beyond the page dark mode, whose lighter choice is
  Chromium's own. Scrolling with a real graphics card is still to be
  measured on real hardware.
- **Workers started from a file**: `experiment/file-workers` (see Known
  limits); merged only if the owner wants it, probably as an option.
- **Fingerprinting, done for 1.1.21** (docs/SECURITY.md): the font
  allowlist at the global levels Kontrol (then called Strict) and Maximum
  (owner's decision of 2026-11-21; the interface font follows it on KDE
  Plasma), cores 4 or 8, `matchMedia` and the shown screen size (M-2,
  partial: style sheets remain the engine's), the Public Suffix List for the
  noise's site (L-2), `window.name` across sites (L-3). The GPU name at
  Strict stays hidden (evaluated: rarer than "not available").
- **Fingerprinting, done for 1.1.25** (docs/SECURITY.md, the owner's
  decisions of 2026-11-24, from a run against browserleaks.com and CreepJS
  and two rounds of an independent adversarial review): every kind of worker
  and the headers agree with the page (the engine's own brand list and
  order, no kernel version); at Strict and Maximum workers from a site's own
  file get the protection (service and shared ones are not started), and
  there Chrome's own PDF plugins, one WebGL identity for everyone (no card
  name), canvas noise only on edges, the languages and the network speed as
  the headers say them. Left: CreepJS's list of real cards' limits
  ("suspicious capabilities" as "trash", no lie); behavioural probes of the
  real WebGL limits.
- **Still open from the fingerprinting audit**: Balanced's open values
  (L-4, owner's choice), workers loaded from an address (H-C, Qt limit;
  `experiment/file-workers`). Review 4's N11 (the embedded video click
  checking the frame's content, shadow roots) touches the YouTube helpers:
  with the owner.
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
  mismatch. At Kontrol and Maximum no model is named (1.1.25: with one shared
  set of extensions and a floor of limits for everyone).
- The I.K.E. Dark Engine costs more than Chromium's own dark mode (it
  rewrites the page's style sheets): measured in
  docs/review/tests-and-performance.md; Chromium's is the lighter choice.
- A worker a site starts from a file of its own (`new Worker("/w.js")`) sees
  the real values (graphics card, cores): Qt WebEngine gives no way to add a
  script to it. A partial way around it is on the branch
  `experiment/file-workers`, waiting for the owner's decision. At Strict and
  Maximum (1.1.25) such a worker gets the protection (its script runs after
  it from a blob address; refused where a page's policy forbids that), and
  service and shared workers from a file are not started; what still differs
  from the engine is in docs/SECURITY.md (its script's request, timelines,
  one blob line under a stack, a `text/plain` file refused).
- The ad-blocking engine is adblock-rust (open-source library, MPL-2.0)
  with uBlock Origin / EasyList filter lists and uBlock Origin scriptlets; the
  integration around them is I.K.E.'s own.
