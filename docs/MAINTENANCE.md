# Automatic maintenance

GitHub Actions keeps I.K.E. up to date and prepares the fixes. Since
2026-11-22 (the owner's decisions) no AI agent merges into `main` and no agent
merges its own work. The automation's own pull requests (a candidate per
component, an automatic fix, a security fix, a builder's re-anchoring) are
merged by the workflow's own code read from `main` only when they are **fully
verified** ("The verified merge", below); anything less waits for the owner,
who is named in one comment. Claude merges the pull requests the owner asked
for once every check is green; ChatGPT's and people's pull requests wait for
the owner's order (CLAUDE.md). The owner alone **signs and publishes** (one
command on the owner's computer, in the issue GitHub mails when a release is
ready, [UPDATES.md](UPDATES.md)). No workflow releases or signs anything, and
no workflow pushes to `main` (the verified merge is a merge of a pull request).

## The whole chain

Every external component I.K.E. can update goes through the same chain by
itself; the owner only signs.

1. **Detected.** Every day `tools/check-components.py` (the bundled
   components, the engine's crates, the test packages), `tools/ci-pins.py`
   (the workflows' pins), `tools/pkgbuild-sync.py` (what the code needs from
   the PKGBUILD), `tools/inventory.py` (every external component, a new one
   included) and the Arch check (the whole dependency closure of I.K.E.'s Arch
   packages) find what is new; `tools/maintenance-ledger.py` keeps one entry
   per update in the issue "Maintenance ledger".
2. **An isolated candidate.** `daily-maintenance.yml` makes one candidate per
   component, or small coherent group, on its own branch
   `automation/update/<id>` made from `main` (`tools/update-candidates.py`),
   with no credentials while the code of others runs, and opens its draft pull
   request. Candidates that change the same file go one at a time; an open
   one is rebuilt and pushed only when it differs. A builder that refuses a
   new upstream version goes to the builders' path instead
   (`automation/builder/<id>`). An Arch package changed in the closure starts
   `arch.yml` on `main`; Arch's next packages are tried once a week
   (`arch-testing.yml`).
3. **Integrated.** The candidate's own commit (`update: <id> <from> -> <to>
   (no AI)`, `ci: ...`, `pkgbuild: ...`) changes only that component's files,
   the licences and, when it ships, the version (raised when `main`'s is
   published, with its CHANGELOG line).
4. **Tested, Arch included.** `tests.yml` (lint, the whole suite, the Rust
   tests, the licences, no tests lost, the package, the old processor, the
   installed package, and for a new engine the default filter lists in that
   engine against `main`'s), `security.yml` (the sandbox, the RustSec
   advisories) and `arch.yml` (Arch Linux's own packages) on its commit.
5. **Fixed by an AI when they fail, on that branch only.** `autofix.yml`
   fixes the candidate's own branch under the guard
   (`tools/check-autofix-patch.py`), a fresh run per attempt starting with the
   next free provider, up to `FIX_ATTEMPTS` (`tools/ai-providers.py`), the
   tests again after each. On a candidate of the engine (adblock, pyo3, a
   major crate) the AI may adapt I.K.E.'s wrapper; on a builder's branch it may
   only re-anchor I.K.E.'s existing patches. An AI never edits a workflow: what
   it wanted there is a written proposal for a person. At the cap the branch
   is kept, the ledger says needs-person and the owner is told once.
6. **Merged by itself** when everything is green and verified
   (`tools/automerge.py`, `automerge.yml`, read from `main`). Several
   candidates go into the same unpublished version; one that is behind
   `main` is refreshed first (`main` merged into its branch, its tests
   again), and after every merge the others are judged again, so they all
   converge into `main` one after another ("The verified merge", below).
7. **The owner signs.** `release-ready.yml` mails the owner the command that
   signs and publishes the new version; every user then gets it by itself.

## What runs by itself

| When | What | Workflow | Result |
|---|---|---|---|
| Every day, 05:17 UTC | Upstream versions of the bundled components (and whether I.K.E.'s builders still accept them), Arch Linux's own packages and their whole dependency closure against what the last green `arch.yml` run on `main` tested, and the default filter lists loaded into `main`'s AdBlock engine | `daily-check.yml` | Issue labelled `components` (titled "Component incompatibility: ..." when a builder refused a new version); when anything of Arch's closure changed, `arch.yml` started on `main`; the inventory of every external component and the issue "Maintenance ledger" (label `maintenance-ledger`), see "Inventory, ledger and what is verified" |
| Every day, 06:17 UTC | One candidate per component (the full chain), each made from current `main`; a builder that refused starts its re-anchoring | `daily-maintenance.yml` | Branches `automation/update/<id>`, each with its draft PR labelled `maintenance` and its Tests, Security and Arch Linux; `automation/builder/<id>` for a builder (see "One candidate per component") |
| On every PR, every push to `main`, every candidate or fix | Lint, all the tests, the Arch package and its tests; on a commit of the automation that changes the engine, today's filter lists in its engine against `main`'s | `tests.yml` | Checks on the PR, package download `ike-browser-package` |
| When one of the three above fails, or `arch.yml` fails on `main`, on the fix branch or on a candidate | An automatic fix (for `arch.yml` only when `Tests` passed on the same commit) | `autofix.yml` | A fix on the failed branch (a candidate's own) or a draft PR labelled `autofix`, or an issue "ATTENZIONE E' RICHIESTO IL TUO INTERVENTO PER FARE INTERVENIRE CHAT GPT NELL' AUTOFIX!!! (<workflow>)" assigned to the owner, which GitHub mails |
| Every push to `main`, when the daily check finds Arch's closure changed, after a merge made by itself, on every candidate and fix, and Mondays at 03:41 UTC | The whole suite and the package on Arch Linux's own Python, Qt and Qt WebEngine (`archlinux:latest`), the optional dependencies installed, and a record of the versions it tested (the whole closure) | `arch.yml` | Artifact `arch-versions` and the run's summary; a failure goes to the automatic fix (see "Arch Linux's own packages"); not a required check of the release |
| Wednesdays, 04:23 UTC | `arch.yml` with Arch's `[core-testing]` and `[extra-testing]` on | `arch-testing.yml` | A failure on `main` is fixed on `automation/update/arch-testing-<date>`, merged only when it passes on stable and testing |
| Every day, 04:23 UTC, and on every PR and push to `main` | The security tests with the engine's sandbox really on (as a normal user), and the RustSec advisories of every crate of the AdBlock engine | `security.yml` | Checks on the PR; on `main` the issue "Rust advisories" when one is found; since 2026-11-22 a finding goes to an analysis and a fix on an isolated branch `automation/update/security-<id>`, never on `main`, or is blocked and the owner told (see "Security findings and vulnerability sources") |
| Mondays, 07:41 UTC | The automation itself: every scheduled check (also the Arch and security ones, 1.1.19), one tiny question to each reserve of the automatic fix, and (WP9) whether every AI provider, Gemini included, answers and is free | `health.yml` | Issue "Automation health" when something stopped, failed, waits too long, a reserve's key or model no longer works, or a provider is not free (marked unavailable: the automatic fix skips it); artifact `ai-providers` |
| Once a month | New versions of the GitHub actions used (a double check: `tools/ci-pins.py` moves them every day) | Dependabot | One PR labelled `maintenance`, for a person |
| When a check of a pull request ends, or the automation's own Tests, Security and Arch Linux runs pass on its branch (a dispatch) | The verified merge (2026-11-22): a candidate per component (`automation/update/<id>`, the workflows' pins `automation/update/ci-<name>` and the PKGBUILD's `automation/update/pkgbuild` included), a builder's re-anchoring (`automation/builder/<id>`), the single combined candidate (`automation/daily-maintenance`), a fix of the automatic fix (`automation/autofix-main`) or a security fix (`automation/update/security-<id>`) is merged when it is fully verified: every check of its last commit passed (`tests`, `sandbox`, `rust-advisories`, `Arch Linux`, and "Arch Linux (testing)" for a fix of Arch's next packages), every category its components need passed with nothing "not verified" and no required test skipped, no test file changed or removed, no protected file or workflow (but the CI pins' own edit), the licences up to date, no open security finding, the version raised when main's is published, and never a second raise on top of an unpublished version (several merges by themselves go into the same one); the automatic fix's files also follow the 1.1.19 rules, or on a candidate of the engine the wrapper's rules, or on a builder's branch the re-anchoring rule. Arch Linux is started on the commit when it has not run there. A fix of ChatGPT (`chatgpt/...`) that passes the 1.1.19 rules is only marked ready for the owner's order. A fully verified candidate behind `main` is refreshed instead: `main` merged into its branch (CHANGELOG.md and the version files resolved as decided, any other conflict for a person), pushed to that branch with the workflow's token, its Tests, Security and Arch Linux started again. After every merge the other open pull requests of the automation are judged again. Rules: `tools/automerge.py`, read from `main` | `automerge.yml` | Merged, then `main`'s Tests, Security and Arch Linux start and the release notice follows (one per version); otherwise one comment naming the owner with the reason (edited when the reason changes, never repeated), and the ledger says needs-person (blocked for a security finding); ChatGPT: one comment, ready and waiting for the owner's order |
| When the tests of `main` pass (after a merge by itself: when its Tests and Security pass), and every day at 08:13 UTC | A version in `main` that is not published yet, with `tests` and `sandbox` green on its last commit | `release-ready.yml` | An issue "C'E' UNA NUOVA RELEASE IN MAIN PRONTA DA PUBBLICARE!!!" with the exact command, assigned to the owner and naming the owner (GitHub mails it), listing what was merged by itself since the last release (fully verified, so the owner knows what the signature covers); a reminder comment each week; closed by itself once the version is published; never opened again for a version whose notice the owner closed |

## Components followed

`tools/check-components.py` checks (each line is one candidate, or a small
group of them, `--only <id>`):

| Component | Candidate | Version written in | What triggers an update |
|---|---|---|---|
| adblock-rust, the AdBlock engine library | `adblock` | `ike-adblock/Cargo.toml`, `ike-adblock/src/lib.rs`, `ike-adblock/Cargo.lock` | A newer stable release on crates.io |
| The engine's other crates (serde_json and every crate pyo3 and adblock bring, psl's list of public suffixes included; 1.1.19) | `crates` | `ike-adblock/Cargo.lock` | A newer compatible version of any of them (`cargo update`, the requirements as they are, adblock kept at its exact version) |
| pyo3, the bridge to Python | `pyo3` | `ike-adblock/Cargo.toml`, `ike-adblock/Cargo.lock` | A new release line: the requirement is raised (the automatic fix may adapt I.K.E.'s wrapper) |
| A new major version of another direct crate of the engine (serde_json 2, ...) | `crate-major-<crate>` | `ike-adblock/Cargo.toml`, `ike-adblock/Cargo.lock` | Its requirement in `Cargo.toml` is raised, then `cargo update`; the automatic fix may adapt the wrapper. A major version of a crate only adblock brings (thiserror 2, rand, selectors...) cannot be taken by I.K.E.'s requirements: it comes with a new adblock, which is its own candidate; the ledger keeps it as retry-later, looked at weekly |
| uBlock Origin scriptlets | `ubo-scriptlets` | `ike/resources/ubo-scriptlets.json` | The rebuilt scriptlets differ, not merely a new upstream commit |
| Dark Reader: engine (npm "darkreader") and the lists of its extension (GitHub) | `darkreader` | `ike/resources/darkreader.js`, `darkreader-proxy.js`, `darkreader-data.json` (`tools/build-darkreader.py`) | A newer engine, or lists that changed (site fixes, dark sites, detector hints) |
| The packages of the automatic tests: Qt's wheels; pytest, ruff and theirs; the other libraries | `test-qt`, `test-tools`, `test-libs` | `tools/test-requirements.txt` | A newer package set on PyPI (no new version of I.K.E.: nothing ships) |
| The workflows' pins: every GitHub Action, cargo-deny, setup-python's and setup-node's versions, the Rust toolchain | `ci-<name>` | `.github/workflows/*.yml`, `.github/actions/*` (`tools/ci-pins.py`) | A newer release (see "The workflows' pins") |
| The PKGBUILD's depends, optdepends and minima | `pkgbuild` | `PKGBUILD` (`tools/pkgbuild-sync.py`) | A module, Qt module or program the code uses and no package declares, a package needed at run time that is only optional, or a `# needs: <package> >= <version>` the code declares (see "Arch Linux's own packages") |

The browser itself runs on Arch Linux's `qt6-webengine`, updated with the
system (`sudo pacman -Syu`); the Chrome version presented to sites is the one of
that engine (1.1.14). Filter lists and user
scripts update themselves inside the browser (the daily check loads today's
lists into the bundled engine: see "The default filter lists" below).

### When a builder refuses a new upstream version

Two of the components are not copied but built, with I.K.E.'s own changes:
Dark Reader (`tools/build-darkreader.py`: the proxy taken out of the engine
and I.K.E.'s speed patches, `PATCHES`, each of which must find its text, its
"anchor", exactly once) and uBlock Origin's scriptlets
(`tools/build-ubo-scriptlets.mjs`: `builtinScriptlets` of
`src/js/resources/scriptlets.js`, read with Node.js). Since 1.1.20 (the
owner's decision) `tools/check-components.py` keeps two kinds of trouble
apart:

| What happened | Called | What it does |
|---|---|---|
| An upstream source could not be read: the network, crates.io, PyPI, npm, GitHub, `git clone`, npm's hash that does not match | **source unreachable** | Infrastructure. The report's row says "check failed: source unreachable: ..."; `--apply` applies **nothing** and exits 1 (fail closed); the maintenance's check step fails and the automatic fix opens "GitHub or the runner failed: Daily maintenance candidate", no AI. The next daily run tries again. |
| The new version was downloaded, but I.K.E.'s builder does not accept it: a patch's anchor is gone or found twice, the proxy or `injectProxy` is not where it was, the npm package is laid out differently, the site fixes do not start with the common fix; uBlock Origin's library moved, the builder stopped, found no scriptlets, or a scriptlet needs an entry the library does not have | **builder refused**: a component incompatibility | That component **stays at the version in use, with I.K.E.'s changes** (never replaced by the unpatched upstream). Every other component is still applied and tested (the crates' security updates included); `--apply` exits 0. The report has a section for the owner, and since 2026-11-22 the builders' path starts (below): an AI may re-anchor the existing patches on `automation/builder/<id>` only; the guard refuses `tools/build-*` to every other run. |

**How to read the report** (the `components` issue, the run's summary, and the
maintenance candidate's pull request when other components changed). The
issue is titled "Component incompatibility: a builder refused a new upstream
version" and names the owner in a comment when it first appears. Its table
marks the component "**refused**", and the section "Component incompatibility"
gives:

- the component and its versions, in use -> new (for Dark Reader the engine
  version and the lists' commit; for uBlock Origin the commits);
- the step that refused: for Dark Reader the patch by its name in `PATCHES`
  (for instance "I.K.E.'s patch 'style-moves'"), or the proxy / `injectProxy`
  / the site fixes; for uBlock Origin the builder;
- the reason, as the builder said it;
- "The new upstream version around the anchor": the anchor's lines no longer
  found, and the new engine's lines (numbered) around the first anchor line
  still there, or every place where the anchor is now found twice; for
  uBlock Origin what the new checkout has where the builder looks (the file
  and its exports, or the files next to it);
- the builder's log.

**The builders' path** (WP11, 2026-11-22). The daily maintenance starts it by
itself (`autofix.yml`, work `builder/<id>/<date>`, with the refusal above as
the failure description): on the isolated branch `automation/builder/<id>`
an AI may **only re-anchor I.K.E.'s existing patches**, never add one, never
change what a patch puts in, never change upstream code
(`tools/builder-anchor.py`, enforced by the guard's `--builder <id>` mode and
again by the verified merge):

- Dark Reader (`tools/build-darkreader.py`): the same `PATCHES` by name and
  in the same order, each replacement text byte-identical; only anchor texts
  may change, re-found in the new upstream engine; everything outside
  `PATCHES` byte-identical. Dark Reader keeps only measured patches (the
  owner's decision of 2026-11-21): no patch can come in this way;
- uBlock Origin (`tools/build-ubo-scriptlets.mjs`): only the path of the
  library it imports (a file under the checkout, ending in `.js`).

The re-anchored builder then runs: `daily-maintenance.yml` (mode `builder`)
applies the update on that branch with it (the builder itself refuses an
anchor found not exactly once), and its tests prove the result:
`tests/test_darkreader.py` checks that the shipped engine is Dark Reader's own
npm engine with exactly I.K.E.'s changes (byte identity) and only the measured
families, and the Dark Reader cost test runs with the whole suite. A builder
that still refuses is given to the AI again, up to `FIX_ATTEMPTS`; then the
branch is kept and the owner told. A person may always adapt a patch by hand
in a pull request, as any change of `tools/`. Until the new version is merged,
users keep the working, customised version.

### The default filter lists in the bundled engine

The lists I.K.E. turns on by default (`DEFAULT_LISTS` in `ike/config.py`)
change every day on users' computers, outside I.K.E.'s releases, while the
AdBlock engine and uBlock Origin's scriptlets come with I.K.E. Every day the
job `lists` of `daily-check.yml` (permission `contents: read`, no token, only
`main`'s own code) builds `main`'s engine and runs
`tools/check-components.py --filter-lists lists.json --markdown lists.md`:

- each list is downloaded as I.K.E. downloads it (HTTPS, at most 32 MB, the
  `!#include` sub-lists next to it, one level) and read as I.K.E. reads it
  (`!#if` answered as uBlock Origin on Chromium, `ike/scriptlets.py`);
- the engine reads each list with `parse_report` (a read-only function of
  the engine module, the same parser and options as the browser uses): rules
  taken (network, cosmetic), lines it does not support and rules it cannot
  parse, with examples. Then all the lists are loaded together and the
  engine is built and asked once;
- every `domain##+js(name, ...)` rule is resolved against the bundled
  scriptlet library exactly as `ike/scriptlets.py` does (aliases, the
  scriptlets uBlock Origin keeps to trusted lists only from uBlock Origin's
  own site, none from the cookie lists).

A **finding** (never a failure of the code; since 2026-11-22 each one is
classified, and some are analysed by an AI on an isolated branch: see "Filter
lists in five classes" below): a scriptlet name the library does not know (`ike/scriptlets.py` drops
such a rule without a word: list/scriptlet drift), a list the engine cannot
read for more than a quarter of its rules (`LIST_UNREAD_SHARE`; on
2026-11-21 the uBlock lists were between 0.1% and 15%, mostly rules of other
blockers such as `replace=` and HTML filters), a list that is not a list
(empty, binary, too big), an engine that cannot be built from them. A list
that cannot be downloaded is **unreachable** and nothing more. The findings
open (or keep) the `components` issue, titled "Filter lists: findings about
the bundled components" when nothing else is new, with the section "The
default filter lists in the bundled engine". The job fails only when `main`'s
engine does not build or the check itself stops: an issue for a person.

Known on 2026-11-21: uBlock Origin's own resources used as scriptlets
(`noeval`, `nofab`, `popads-dummy`, `popads.net`, `fingerprint2`; about 70
rules of "uBlock filters" and "Unbreak") are not part of `builtinScriptlets`,
so I.K.E. does not run them. They are listed as a note every day
(`KNOWN_UNRUN_SCRIPTLETS`), not as a finding; whether to bundle them is the
owner's decision. Any other unknown name is a finding.

The maintenance candidate gets the same check against its own engine and
library (when the engine builds): the section is added to its pull request,
and it never stops the candidate. The unit tests use a small recorded
snapshot of real rules (`tests/data/filter-lists-snapshot.txt`), offline;
`IKE_TEST_NETWORK=1` also runs the check on the real lists.

### Dark Reader's cost budget

Dark Reader's patches applying is not enough: they are there to keep it
fast. `tests/test_darkreader_cost.py` starts the browser once, with a local
page that gives Dark Reader a fixed amount of work (600 style rules, 400
styled elements, 60 shadow roots, an SVG, then 30 bursts of new styles and
elements), and times it until the page is idle again with Dark Reader, with
the engine's own dark mode and with no dark mode, in turns (a rotating
order, one round to warm up, 7 rounds measured). It checks that each mode is
what it claims, then compares the **median of each round's ratios** (Dark
Reader / off, Dark Reader / engine dark), never absolute times, with
`tests/data/darkreader-cost.json`: it fails only when a ratio is above the
recorded one times its margin (2), a clear regression. It runs wherever the
whole suite runs (`Tests`, the maintenance candidate, `arch.yml`); on GitHub
the line "Dark Reader cost: ..." goes into the run's summary.

Recorded on 2026-11-21 in a container with software drawing: Dark Reader /
off about 3.1 (2.7 to 3.3 over five runs), Dark Reader / engine dark about
3.3, engine dark / off about 1.0. **To update the baseline** after a
deliberate change (a new Dark Reader engine that is slower for a good
reason, a new patch, a GitHub runner whose ratios differ): run
`IKE_DARK_COST_RECORD=1 python3 -m pytest -q tests/test_darkreader_cost.py`,
compare with the "Dark Reader cost" lines of a few green GitHub runs, keep
the larger values in `tests/data/darkreader-cost.json`, and say why in the
pull request. The automatic fix can never change it (`tests/data/` is
refused by its guard).

### Arch Linux's own packages

`Tests` runs on Ubuntu with Python 3.13 and PyPI's Qt; users run Arch's
Python, Qt, PyQt and Qt WebEngine, which `pacman -Syu` updates at any time,
outside I.K.E.'s releases. These are followed as components too
(`ARCH_PACKAGES` in `tools/check-components.py`): `qt6-webengine`,
`qt6-base`, `qt6-webchannel`, `qt6-svg`, `python-pyqt6`,
`python-pyqt6-webengine`, `python`, `python-cryptography`, `python-jeepney`,
`publicsuffix-list` and `rust` (it brings `cargo`, for the build). Since
1.1.22 also the packages features of 1.1.21 and 1.1.22 depend on:
`fontconfig`, `noto-fonts` and `ttf-dejavu` (the font allowlist,
`ike/fontallow.py`), `breeze`, `oxygen`, `kvantum`, `plasma-integration` and
`breeze-icons` (the widget styles, KDE's theme and the icon test) and
`ffmpeg` (video). `arch.yml` installs them from the branch `fix/1.1.22` on;
until then a run records them as "not installed": the report says **not
verified** for them, and Arch's new versions of a package a run did not
install never start `arch.yml` (a package no run recorded at all still
does, once).

- **What was really tested.** `arch.yml` installs them in `archlinux:latest`
  and records, before the tests, what it tests: `pacman -Q` of each package,
  Python, Qt, PyQt and the engine's Chromium as I.K.E. reports it
  (`chromever.engine_full()`). The record is in the run's summary and in the
  artifact `arch-versions` (`arch-versions.json`, kept 90 days).
- **Every day** (`daily-check.yml`) the check reads, with GET calls of
  GitHub's API only, the record of the last green `arch.yml` run on `main`
  (`--save-arch-tested`; the token is only in that step, not where the
  sources of others are built), and the version of each package in Arch's
  official repositories, core and extra, from Arch's package site
  (`--arch`; the -testing repositories never count). The components report
  (artifact, run summary, and the `components` issue when that is written)
  has a section with both columns and the run that tested them.
- **What happens.** A package in another version (a new `pkgrel` too: a
  rebuild can break as well), or no green run on `main` with a record yet:
  "Arch changed: compatibility to verify". The small job `start-arch`, whose
  only permission is `actions: write`, starts `arch.yml` on `main` (not when
  a run of it is already queued or running). This is never an update to
  apply and never a release by itself; the daily maintenance does not look
  at Arch at all. When Arch's site cannot be read, the package is "source
  unreachable": never a change and nothing is started (the weekly run stays
  as a floor). A mirror that lags behind Arch's site makes `arch.yml` test
  the older set; the next day the check finds the change again and starts it
  once more.
- **The whole dependency closure** (WP10 (a), 2026-11-22). The record of
  `arch.yml` also holds every package pacman installed for I.K.E.
  (`pacman -Qi` of every installed package, followed recursively through
  "Depends On" and "Provides", from `ARCH_PACKAGES` and the PKGBUILD's
  depends, makedepends and the optdepends it installed): Mesa, ffmpeg, NSS,
  ICU, the fonts, Qt's libraries and the rest. The daily check downloads
  Arch's core and extra package databases once (geo.mirror.pkgbuild.com) and
  compares every package of that closure with them: one in another version
  (a new `pkgrel` too) is "Arch changed" and starts `arch.yml` on `main`.
  A database that cannot be read is "source unreachable", never a change.
- **Arch's next packages** (WP10 (b)). Once a week `arch-testing.yml` calls
  `arch.yml` with Arch's `[core-testing]` and `[extra-testing]` repositories
  on (before core and extra, as Arch's own `pacman.conf` says; its record is
  kept apart, never the "last tested on main"). A failure of the build or of
  the tests there, while `Tests` passed on the same commit, is fixed by the
  automatic fix on `automation/update/arch-testing-<date>` made from `main`
  (one at a time); that fix is tested on Arch's stable packages and on the
  testing ones, and merges by itself only when both pass, with the version
  raised. pacman, the mirrors and the container are not the code's: an issue,
  no AI.
- **An Arch update that breaks `main`** (WP10 (c)) is the failure below: the
  automatic fix works on `automation/autofix-main`, tested on Arch too, and
  the verified merge takes it with the version raised.
- **The PKGBUILD kept right** (WP10 (d)). `tools/pkgbuild-sync.py` reads
  what the code needs: the inventory's "used but not declared" (a required
  import or Qt module goes into depends, an optional import or a program
  `ike/` starts into optdepends with what uses it) and "declared too weakly"
  (into depends), and the minima the code declares where it needs them, a
  comment `# needs: <package> >= <version>` in `ike/` or `ike_boot.py` (the
  PKGBUILD then says `'<package>>=<version>'`; a minimum is only raised).
  The daily maintenance makes it a candidate, `automation/update/pkgbuild`;
  the verified merge accepts only that change of the recipe (entries added,
  minima raised, an optional entry moved into depends, and the version), and
  `pacman -U` in `arch.yml` installs a new dependency, so its tests prove it.
  An "unknown provider" stays for a person.
- **The optional dependencies** (WP10 (e)). `arch.yml` installs those Arch
  ships (libnotify, xdg-utils, noto-fonts, noto-fonts-cjk,
  plasma-integration, intel-media-driver, libva-nvidia-driver);
  `tests/test_optional_deps.py` has one case per optdepends entry of the
  PKGBUILD: where the package is installed, pacman finds all its files and
  what I.K.E. uses of it works (notify-send, xdg-settings, a Noto CJK font,
  KDE's platform theme, the VA-API drivers, the Widevine library where
  `ike/drm.py` looks); where it is not installed the case is skipped as
  **not verified**, never "incompatible" (chromium-widevine is in the AUR:
  no check of GitHub installs it, and it says so).
- **A failure of `arch.yml`** goes to the automatic fix (`autofix.yml` listens
  to "Arch Linux"; the runs the automation itself started hand their failure
  over, as `tests.yml` does):
  - pacman, Arch's mirrors or keyring, a package not found, a conflict
    (steps "Git (for the checkout)", "Arch's packages"), the container, or
    the engine's crates that cannot be downloaded ("AdBlock engine's
    crates"): the issue "GitHub or the runner failed: Arch Linux", no AI;
  - a test step that failed runs once more first, as in `Tests`;
  - a failure of the engine's build or of the tests is the code's. It is
    fixed only when `Tests` passed on the same commit (the plan waits for
    its result, at most 50 minutes): then it is an incompatibility with Arch
    alone. When `Tests` failed too, its own fix handles it; when `Tests` has
    no result on that commit, an issue asks a person to look;
  - the failure description given to the fix names the packages that changed
    since the last green run on `main` (old -> new, from the two records, and
    Python, Qt, PyQt and Chromium), the failed tests, the files the logs name
    and the failed step's log. The guard's rules are the same as for every
    fix: `ike/` and I.K.E.'s own page scripts; never the package, the
    engine, the builders (`tools/build-*`), `vendor/`, the Cargo files, the
    workflows or the tests' data;
  - the fix is tested on Arch too (`publish` starts `arch.yml` on
    `automation/autofix-main` with the tests and the security tests, also
    for a later attempt on that branch after another failure), and
    the merge waits for every check of its commit; when `arch.yml` passes
    there, it asks for the merge as the other checks do.

## Inventory, ledger and what is verified

The first work packages of the full automatic maintenance (2026-11-22; the
owner's decisions are in CLAUDE.md: nothing merges into `main` by itself, AI
agents only on isolated branches, workflow files only as proposals, free
providers only). They extend `tools/check-components.py` and the daily
workflows; there is no second system.

**The inventory** (`tools/inventory.py`, read-only). Every external component
is found in the repository itself, so a dependency added later appears with
no change of the tool:

- PKGBUILD `depends`, `makedepends`, `optdepends` and the commands of
  `build()` (`cargo`: `rust`; `gcc`; and `makepkg`);
- the Arch packages the daily check follows (`ARCH_PACKAGES`);
- the Python modules `ike/` and `ike_boot.py` import (AST), each mapped to its
  Arch package by Arch's rule (`foo` is `python-foo`, with the exceptions of
  `MODULE_PACKAGES`), and the PyQt6 modules with the Qt packages they need
  (`QtWebEngineCore`: `python-pyqt6-webengine` and `qt6-webengine`, `QtSvg`:
  `qt6-svg`...);
- the programs `ike/` starts (`subprocess`, `QProcess`; `xdg-open` through
  Qt's `QDesktopServices`), each mapped to its Arch package (`notify-send`:
  `libnotify`, `xdg-settings`: `xdg-utils`);
- every crate of `ike-adblock/Cargo.lock`, direct or transitive;
- the Node.js modules of `tools/*.mjs`;
- the PyPI packages the workflows install (`-r tools/test-requirements.txt`
  and single packages), `cargo install` tools (cargo-deny), the Rust,
  Python and Node.js versions, the runner images and apt packages;
- every `uses:` of a GitHub Action with the commit it is pinned to;
- Dark Reader, uBlock Origin's scriptlets, the default filter lists
  (`ike/config.py` `DEFAULT_LISTS`) and the vendored AdBlock engine.

A module, program or build command that no declared package covers is a
finding **"used but not declared"** (an optional import whose package is only
in `optdepends` is fine; a required one is "declared too weakly"); a program
or Qt module whose package is not known is "unknown provider"; an action not
pinned to a commit is "not pinned". Each record has its name, kind, type,
origin (where in the repository it was found), distribution, the version in
use, the available version (Arch from archlinux.org's JSON API as
`check-components.py` reads it, crates.io's index, PyPI, npm, GitHub's tags
with `git ls-remote`, the builders' own check for Dark Reader and uBlock
Origin, the lists check for the lists), its update mode, the tests an update
needs, its compatibility (a crate's update is "semver-compatible" or "major:
needs a requirement change"), vulnerabilities, the last check and its result.
What is not known or could not be read is "unknown" or "not checked", never
guessed; a host that does not answer three times is not asked again that
day. Vulnerabilities come only from a check that ran: the RustSec advisories
of `security.yml`'s last run on `main` for the crates, and since WP7 the OSV
database and Arch's security tracker for the rest (see "Security findings and
vulnerability sources"); a source that did not answer leaves its components
"not checked". On today's repository the inventory finds about 200
components and no finding. Output: JSON and a Markdown summary (the daily
check's run summary and artifact `maintenance-ledger`).

**The ledger** (`tools/maintenance-ledger.py`, job `ledger` of
`daily-check.yml`: `contents: read`, `actions: read`, `pull-requests: read`,
`issues: write`; the token only in the steps that call GitHub, never in the
inventory's). One issue, "Maintenance ledger", labelled `maintenance-ledger`
and written only by the daily check: a readable table and, between two
markers, a JSON block the next run reads back (only from the bot's own issue;
a block with an unknown state or a key that does not match its entry is not
read, and the ledger starts again). One entry per update of one component,
key `<component>@<new version>`, with from → to, state, reason, attempts,
first and last seen, the last run's link, the next retry and a short
history. The states:

| State | When |
|---|---|
| detected | a newer version (or a new dependency) was found |
| candidate | its own candidate carries it (`automation/update/<id>`, or the combined one); its tests have not run |
| testing | the candidate's checks, or `arch.yml` on `main` for an Arch package, are running |
| fixing | they failed: the automatic fix works on it, on the candidate's own branch |
| passed | every required check passed (the verified merge takes it), or it is in `main` |
| blocked | an advisory with no fixed version upstream, a security fix the automatic fix gave up on, or tried `MAX_ATTEMPTS` times |
| needs-person | a builder refused it and its re-anchoring is not there yet, a pin of a workflow until its candidate exists (an AI's change of a workflow is only a proposal), a dependency used but not declared (until the PKGBUILD's candidate), the automatic fix reached its cap (`FIX_ATTEMPTS`: the branch is kept, the owner told once), or checks that passed but left a required category not verified |
| retry-later | a source unreachable today (tried again the next day), or a new major version `cargo update` cannot take (looked at again weekly) |

Since the full chain each entry follows its own candidate: the ledger reads
every open pull request of `automation/update/<id>` and `automation/builder/<id>`
(`update_branches`: its commit, the runs of Tests, Arch Linux and Security
there, its skipped tests, the automatic fix's commits and the merge's
verdict) and gives the entry of that component the candidate's state.

The same update is never added twice; a failed one keeps its reason and is
tried again when its time comes or when `main` changes; finished entries
leave after 30 days. The issue's body stays under `MAX_BODY` (60,000
characters; GitHub's limit is 65,536): when it would not, the entries' history
goes first, then the oldest finished entries are folded into one count line,
then the open entries lose their spare fields one kind after the other (the
sample rules last) and the filter lists' rows of the table become one line.
A blocked, needs-person, fixing or other open entry is never left out; the
artifact `maintenance-ledger` (`ledger.json`) always has everything. A test
gives 5,000 rules of findings next to 22 component updates: 83 groups, a body
of about 52,000 characters, every open entry present. A component never seen before (a new import, depend,
crate or `uses:`) is an entry "(new) → version": passed once the tests of
`main` are green with it, "needs-person" while the inventory has a finding
about it. The ledger also **closes the automatic fix's reports whose failure
is gone**: an open report of "Tests" (the bot's issue and its own comments
only) is closed with a comment when, on every branch it names, a run of a
later commit passed every step the report named as failed (with none named,
the whole run). Issue #97 ("Licences", fixed by #95) closes when the next
candidate passes "Licences" and "No tests lost".

**What is verified** (`tools/test-categories.py`). A skipped test, or a check
that did not run, is **not verified**, never passed. `tests.yml` writes
pytest's junit for the suite and for the installed package; the step "What
the tests verified" (always, never failing the run) puts the counts and every
skipped test, by area and with its reason, in the run's summary, and keeps
them in the artifact `test-results` for the ledger and the candidate's pull
request. Each kind of component needs its categories (`REQUIRED`): a crate
needs the Rust tests, the licences, the whole suite, the package build, the
old processor, the installed package, the RustSec advisories and "no tests
lost"; the AdBlock engine also the filter lists and Arch; an Arch package
`arch.yml`; a test package the lint and the suite; and so on. A category not
run on the candidate's commit is "not verified" with the reason; "desktop"
(KDE Plasma, notifications, a real graphics card) is never run by GitHub and
always says so.

The inventory, the ledger, the test categories, the candidate's report and
`tools/check-components.py` itself are in the guard's protected files
(`FORBIDDEN_FILES`): no agent changes what judges it.

Since 2026-11-22 every work package of the plan is in: one candidate per
component (WP5, "One candidate per component"), the security findings (WP6,
WP7), the filter lists' classes and the free providers (WP8, WP9, below), Arch
complete (WP10, "Arch Linux's own packages"), the builders' re-anchoring
(WP11), the workflow proposals (WP12, "The automatic fix"), the candidate's
report (WP13) and the end-to-end proofs (WP14, `tests/test_full_chain.py`).

## Filter lists in five classes, and free AI providers (WP8, WP9)

Two more work packages of the full automatic maintenance (2026-11-22, the
owner's decisions in CLAUDE.md: AI agents only on isolated branches, only free
providers, YouTube's ad blocking never changed without the owner).

### The filter lists' findings in five classes (WP8)

Every day the job `lists` of `daily-check.yml` also runs
`tools/filter-lists.py classify` on the report of `tools/check-components.py
--filter-lists` (which now keeps every rule the engine does not read, at most
`LIST_UNREAD_KEEP` per list, with the engine's reason, and whether the list is
trusted). Each rule the engine does not read, each unknown scriptlet and each
list-level problem gets one class, by the first matching rule of this table
(`RULES` in the tool, which a test keeps equal to this table):

| Rule | Class | AI analysis | When |
|---|---|---|---|
| `youtube` | needs a person | no | the rule names YouTube's hosts (youtube.com, youtu.be, ytimg.com, googlevideo.com, youtube-nocookie.com, youtubekids.com, not in a `denyallow=` list) or its player data (`ytInitial...`, `adPlacements`, `playerResponse`...): CLAUDE.md, YouTube's ad blocking is not changed without the owner |
| `known-resource` | needs a person | no | one of uBlock Origin's own resources used as a scriptlet (`KNOWN_UNRUN_SCRIPTLETS`: `noeval`, `nofab`, `popads-dummy`, `popads.net`, `fingerprint2`): bundling them is the owner's decision; still listed as a note by the check |
| `run-by-ike` | supported | no | a `+js()` rule the engine's parser refuses, but I.K.E.'s own `ike/scriptlets.py` runs it |
| `other-platform` | unsupported but harmless | no | HTML filtering (`##^`) or `replace=`: uBlock Origin has them only on Firefox, and the lists carry the Chromium alternative (scriptlets) |
| `untrusted-scriptlet` | unsupported but harmless | no | a trusted-only scriptlet in a list that is not uBlock Origin's own: uBlock Origin would not run it either |
| `exception-without-blocking` | unsupported but harmless | no | an exception (`@@`) only for a blocking the engine never applies (`popup`, `cname`, `urlskip`, `header`, `permissions`, `denyallow`...): nothing to lift |
| `exception-dropped` | breaking | yes | any other exception the engine drops (`@@`, `#@#`): it blocks or hides what the list unblocks, a site may break |
| `trusted-scriptlet` | possible security regression | yes | a `trusted-...` scriptlet that does not run |
| `protection-dropped` | possible security regression | yes | a blocking rule with an option that protects (`removeparam`, `csp`, `redirect`, `redirect-rule`, `permissions`, `header`, `urlskip`, `uritransform`, `inline-script`, `strict1p`, `strict3p`, `ipaddress`, `denyallow`, `to`, `method`, `popup`, `popunder`) that the engine drops or reads differently |
| `protective-list` | possible security regression | yes | any other dropped rule of a privacy or badware list (by its name: Privacy, Badware, Malicious, EasyPrivacy) |
| `page-blocking` | possible security regression | yes | a dropped rule that blocks whole pages (`$doc`, `$document`, `$all`) |
| `unknown-scriptlet` | breaking | yes | a scriptlet the bundled library does not know (list/library drift) |
| `rule-dropped` | breaking | yes | any other rule of an ads list the engine does not read |
| `list-unusable` | needs a person | no | a list that is not a list (empty, binary, too big) |
| `list-refused` | breaking | no | the engine refuses the list or fails while reading it |
| `engine` | breaking | no | the engine does not load or build from the lists (adblock-rust is a crate: a person) |
| `unread-share` | breaking | no | the engine cannot read more than `LIST_UNREAD_SHARE` (a quarter) of the list |
| `share-rise` | breaking | no | the unread share of a list rose by more than `SHARE_RISE` (5 points) since the day before (the ledger keeps yesterday's shares) |

Findings are grouped by class, rule and detail (the option, the engine's
reason, the scriptlet): `lists/<rule>/<detail>@<class>`, so 1,300 rules make
about 60 groups, not 1,300 entries. The classes go into the `components` issue
below the lists' table, and each **group** becomes **one** ledger entry (the
ledger remembers it while it is reported, also after its entry left), with
the number of rules, the lists concerned and at most three sample rules
(80 characters each; a finished entry keeps only its count): supported and
harmless ones "passed", needs-a-person ones and those no AI may touch
"needs-person", the others queued ("detected") for an AI analysis. Every
rule of every finding stays in the daily check's artifact `filter-lists`
(`lists.json`, `classes.json`), never in the issue.

Recorded on 2026-11-22 from the six uBlock Origin lists this sandbox could
read (EasyList, EasyPrivacy, EasyList Italy, URLhaus and Fanboy's cookie list
were unreachable from it; the daily check reads them all): about 44,800 rules
supported; 243 harmless (HTML filtering and `replace=` 184, exceptions for
pop-ups and CNAME 59); 144 breaking (dropped exceptions, mostly generic
unhide `#@#` and empty `$redirect-rule`/`$removeparam` exceptions, and a few
procedural cosmetic rules); 828 possible security regressions (`$denyallow`
249, `$urlskip` 226, pop-ups 152, `$to` 44, `$ipaddress` 31, `$strict1p` and
`$strict3p` 25, `$header` 20, `$uritransform` 20, `$removeparam` as a regular
expression or empty 19, `$permissions` 10, `$csp` with a content type 8,
`$method` 5, and 15 other unread rules of the Privacy and Badware lists); 72
for a person (69 rules of uBlock Origin's own resources, 3 YouTube rules). These are the
engine's gaps of today, not new regressions: they are written in the ledger
once, and analysed one at a time.

**The AI analysis** (one group, that is one option or one scriptlet, per
attempt; one at a time, the most severe first, at most one started a day,
never for a YouTube rule or a finding of a person; a finding that waits for a
free provider holds the queue). The daily check's job `ai-work` (only `actions:
write`) starts `autofix.yml` with `work=lists/<date>/<finding>`. The plan
(`tools/filter-lists.py plan`, GET calls only) reads that day's lists report,
and writes the task and the finding's real rules (at most `RECORDED_MAX`).
The fix job runs as for any failure (Antigravity in its closed room, then the
reserves), told "This run: the filter lists" and with `--lists`:

- it may change **only I.K.E.'s adapter**: `ike/scriptlets.py`,
  `ike/blocker.py`, `ike-adblock/src/*.rs` (`check-autofix-patch.py --lists`,
  and the reserves cannot even write elsewhere);
- never the upstream lists or `ike/config.py`, the bundled uBlock Origin
  resources, the tests or their data, `Cargo.toml`/`Cargo.lock`, nor YouTube's
  ad blocking: a changed line naming YouTube, its hosts or the video scripts,
  or a hunk inside `Scriptlets.host_scripts`, is refused for safety;
- never weaken blocking: a change that removes more lines than it adds, or
  removes a line that keeps a protection (trust, exceptions, `ghide`,
  `BUILTIN_RULES`, the lists' directives...), is refused for safety. These
  are patterns, not proof: the tests decide.

The guard job (no AI) then adds the recorded rules to
`tests/data/lists-recorded/<date>-<finding>.txt` and commits on
**`automation/update/lists-<date>`** (never `main`); publish opens the pull
request "Filter lists: an AI change of I.K.E.'s adapter (...)" and starts the
tests and the security tests. `tests/test_lists_recorded.py` (protected) proves
that I.K.E. reads every recorded rule **with its meaning**: a scriptlet rule
runs on its domain with the same scriptlet and arguments; any other rule,
after I.K.E.'s rewriting (`sanitize`), is read by the engine as one rule with
every option it had (dropping an option to make a rule parse is refused). The
test first proves itself on recorded rules I.K.E. reads and does not read.
The finding is "testing" while its pull request waits (a person after
`TESTING_DAYS`), "passed" once the lists check no longer reports it, and
"needs-person" when the AI could not, or a check refused its change; after
`MAX_ATTEMPTS` (2) attempts on one branch, a person. The run never opens the
"ATTENZIONE..." issue: the ledger is where a person reads it.

### Free AI providers, checked every week (WP9)

**One place** for the providers: `tools/ai-providers.py` (protected, read by
the agent, the reserves, the weekly check and the queue). It holds the order
(Antigravity first, then `RESERVES` in order: Groq, Z.AI, OpenRouter), the
default models, the time limits, the free-model rule and the retry cap. The
models can still be chosen in the repository variables (`AUTOFIX_MODEL`,
`AUTOFIX_GROQ_MODELS`, `AUTOFIX_ZAI_MODELS`, `AUTOFIX_OPENROUTER_MODELS`).
`MAX_ATTEMPTS` of a fix (`tools/autofix-plan.py`) and the guard's size limits
stay where they were.

**Free only, also when it runs.** OpenRouter's models must end in `:free`:
a model without it, also one set in the variable, is refused and never asked
(`chain()`); the free models discovered when a listed one is gone must also be
priced zero in OpenRouter's own price list. Any answer that reports a cost
(`usage.cost`), and any error that asks for money (HTTP 402, "payment
required", "insufficient balance/credits", Z.AI's code 1113, Gemini's
`BILLING_DISABLED`, a model only for paid tiers) makes that provider
**unavailable** for the rest of the run; a rate limit's advice ("upgrade to
Dev Tier", "check your plan and billing details") is still a quota.

**The weekly check** (`health.yml`, step "The AI providers answer and are
free", `tools/provider-check.py`, with the four keys in that step only):

- every provider with a key, **Gemini included** (the Gemini API's list of
  models, then one tiny `generateContent`, the key in a header), answers one
  tiny request ("Answer with the word OK.", 16 tokens);
- OpenRouter: each configured model must be `:free`, priced zero in
  `/api/v1/models`, and the key must be on the free tier with nothing spent
  (`/api/v1/key`); only then is one model asked;
- an answer with a cost, a paid tier or a billing error marks the provider
  **unavailable**: the result is kept as the artifact `ai-providers` (90 days),
  the plan of `autofix.yml` reads it (`provider-check.py unavailable`, GET
  only) and the agent and the reserves skip that provider
  (`AUTOFIX_UNAVAILABLE`); the issue "Automation health" tells the owner;
- a refused key or an unknown model is reported as before; a busy provider
  (429, 5xx) is not a fault.

Whether Groq, Z.AI and Gemini could charge cannot be proven by their APIs: the
table says "not provable by API: rests on the owner's account without
billing" (Gemini's is proven only when its quota error names the free tier).
OpenRouter's is proven by its own price list and key. The file and the summary
hold provider, model, state and a reason chosen by the tool, never a key or
the text of an answer.

**No free provider at all** (every one busy, out of quota or unavailable; a
refused key or no key at all is still the owner's matter): the fix job says
so (`deferred`), the report opens no issue and leaves the outcome as an
artifact (`ai-work-outcome-*`). The next daily check (`tools/ai-work.py
gather`, GET only) writes it in the ledger as **retry-later**, with its
branch and its attempts kept (`automation/autofix-main`,
`automation/daily-maintenance` or `automation/update/lists-<date>`), and
after `RETRY_HOURS` (24) the job `ai-work` starts it again
(`autofix.yml -f run_id=<the failed run> -f work=run/<id>`, or the same lists
work). A started work that never reports back is counted as a try after
`STUCK_HOURS`. After `RETRY_CAP` (5) tries it is "needs-person" and the owner
is told **once** (a comment naming the owner on the ledger issue); before
that, nobody is asked. **To change the cap, the wait or the order of the
providers: `tools/ai-providers.py`.**

## Security findings and vulnerability sources

WP6 and WP7 (2026-11-22). The owner's decisions: a vulnerability starts an
analysis and a fix by the AI on an **isolated** branch, never on `main`; with
no safe fix the candidate or update is **blocked** and the owner is told;
agents never weaken the sandbox, disable a protection, weaken a test, ignore
a vulnerability without a documented reason, or lower a check to accept a
dependency; nothing merges by itself.

**From a finding to a fix.** `security.yml`'s job `hand-over` gives a failure
on `main`, a maintenance branch or an isolated branch (never a person's pull
request) to `autofix.yml`; `tools/autofix-plan.py` decides:

| Finding | On | What happens |
|---|---|---|
| A RustSec advisory with a fixed version | `main` | Job `security-update`, **no AI**: `tools/security-fix.py apply` runs `cargo update -p <crate>@<version> --precise <first fixed version>` on `automation/update/security-<advisory id>` made from `main`. Only `ike-adblock/Cargo.lock` may change (the job stops otherwise), and cargo-deny must no longer report the advisory (`verify`). Then a draft pull request with the report (the candidate report's format: what changes, AutoFix, problems, tests, security, licences, limits) and `Tests` and `Security` on that branch. A failure there goes to the AI **on that branch**, under the security rules below (I.K.E.'s wrapper of the ad blocker only, when the crate is `adblock` or `pyo3`) |
| An advisory with no fixed version upstream ("No safe upgrade is available!"), a fixed version `cargo update` cannot take (a requirement of the crate that uses it must change), or one the update did not clear | `main`, its branch | **Blocked**: the automatic fix's issue (once while it is open) and the ledger tell the owner. Never ignored: an exception goes only in `ike-adblock/deny.toml`, written by a person with its reason |
| An advisory only a candidate brings | a candidate | The candidate is blocked and the owner told |
| A failed sandbox or isolation test (job `sandbox`) | `main` | The AI on `automation/update/security-sandbox`, made from `main`, under the security rules |
| The same | a candidate | The AI on `automation/update/security-sandbox-<candidate>`, from the candidate's commit (`main` plus its update: from `main` alone the failure does not show); the candidate stays blocked |
| A fix that still fails after `MAX_ATTEMPTS` (2) | its branch | Blocked, the owner told |

The isolated branch is tested again by `tests.yml` (whose `hand-over` covers
`automation/update/security-*`, and "No tests lost" runs there) and
`security.yml`. Other `automation/update/*` and `automation/builder/*`
branches are watched by `security.yml`'s hand-over but get no fix of their
own yet (WP5, WP11).

**The 1.1.18 safety property, kept.** Until 2026-11-22 it read "a finding
here never starts an automatic fix". It now starts one, and the property is:
**a security finding can never make an AI change a protection**. How it is
guaranteed:

1. The plan, the instructions and the checker are read from `main`, never
   from the branch being fixed (as for every fix).
2. Every patch of a security fix goes through `tools/check-autofix-patch.py
   --security`, in the fix job (Antigravity's patch and each reserve's, before
   it is kept) and in the guard job. `--security` comes from the plan's output
   `security`, which is true for every finding of `Security` and every failure
   on `automation/update/security-*`. It refuses, with exit status 3 (no other
   assistant is asked, the owner looks):
   - any added or removed line, in any file, that names one of the engine's
     protections: every string of `UNSAFE_SWITCHES`, `UNSAFE_FEATURES`,
     `UNSAFE_ENV`, `NOTICE_SWITCHES`, `LNA_FEATURES` and `PRIVACY_FEATURES`
     (read with Python's parser from `ike/app.py` of the tree being checked,
     so a switch added there later is protected with no change of the
     checker), the names of those lists, `ENGINE_SAFETY` and the functions
     that decide (`_engine_safety`, `unsafe_allowed`, `refuse_root`,
     `sandbox_off`, `site_isolated`, `engine_safety_lines`),
     `IKE_ALLOW_UNSAFE_ENGINE`, `QTWEBENGINE_DISABLE_SANDBOX`,
     `IKE_TEST_SANDBOX`, `--site-per-process`;
   - the security tests (`SECURITY_TESTS`: the nine files `security.yml` runs
     with the sandbox on, plus `test_security.py`,
     `test_home_network_engine.py` and `test_update_safety.py`);
   - `ike-adblock/deny.toml`, and any added line that names a RustSec
     advisory;
   - and everything the checker refuses for every fix (workflows, tools,
     Cargo files, weakened tests, keys...).
3. For **every** fix, ordinary ones and ChatGPT's included, a line of
   I.K.E.'s code (`ike/`, `ike_boot.py`, `launcher/`) that names those
   protections, and `ike-adblock/deny.toml`, are refused the same way.
4. The deterministic update changes only `Cargo.lock`; it never writes
   `deny.toml`.
5. An exception needs a reason: `security.yml` runs `tools/security-fix.py
   check-ignores` before cargo-deny and fails when an `ignore` entry of
   `deny.toml` has none (a bare id, a placeholder, under 20 characters).
6. The security tests still run with the sandbox on against the fix, on its
   branch, and no test may be lost.

What this does not prove: the checker refuses lines by what they name; a
change of behaviour that names no protection is caught only by the tests on
the branch and by the owner, who reads the diff before ordering the merge
(the pull request says so).

**Vulnerability sources (WP7)**: `tools/vulnerabilities.py`, called by the
inventory in the daily check's ledger job (its step has no token), only in
GitHub Actions, never in the browser (README, "External services"):

| Components | Source | How |
|---|---|---|
| Python test and CI packages (pinned in `tools/test-requirements.txt` or a workflow) | The OSV database: `POST https://api.osv.dev/v1/querybatch` (ecosystem PyPI), then `GET /v1/vulns/<id>` once per advisory found | The name and version only, in batches of 500 |
| npm: Dark Reader's engine (the version in `darkreader-data.json`); the modules of `tools/*.mjs` when a version is pinned (today none: "not checked") | OSV, ecosystem npm | The same |
| GitHub Actions pinned to a commit | OSV, ecosystem "GitHub Actions", by the release the pin's comment names (`# v7.0.1`: 7.0.1) | The same; an action with no release named is "not checked" |
| Arch packages (depends, makedepends, optdepends, `ARCH_PACKAGES`) | Arch's security tracker, `GET https://security.archlinux.org/issues/all.json` (every advisory group, AVG, with its packages, status, affected and fixed versions: the JSON `arch-audit` reads) | By the version the last green `arch.yml` run on `main` tested (else the repositories' one), compared as pacman's `vercmp`: "Vulnerable" (no fix yet), "Testing" (a fix in [testing]), "Fixed" with a newer version |
| Rust crates | RustSec through cargo-deny (`security.yml`), as before | The findings of `main`'s last run, read from its job's log |

A source that does not answer, or answers in another layout, leaves its
components **not checked** (the reason in `vulnerability_note`), never "none
known"; the inventory's `vulnerability_sources` and its summary say which.
Each advisory of a component is **one** ledger entry, key `<component
id>@<advisory id>`: no fixed version upstream is "blocked"; a crate with a
fix is "detected" and then follows its isolated branch (testing, fixing,
passed: waits for the owner's merge, or blocked when the automatic fix gave
up); an Arch package is "detected" (users get the fix with `pacman -Syu`,
`arch.yml` verifies it); PyPI and npm are "detected" (the daily candidate
takes the newer version: its own candidate per component); a GitHub Action
"needs-person" (an AI's workflow change is only a proposal; the pin itself
moves by `tools/ci-pins.py`'s candidate). A failed sandbox test on `main` is the entry
`security:sandbox@failing on main`. An advisory a source that answered no longer reports is
"passed". Every entry that becomes blocked or needs a person is said **once**
in a comment on the ledger issue that names the owner (an edited body
notifies nobody).

Checked on 2026-11-22 while this was built: `api.osv.dev` and
`security.archlinux.org` could not be reached from the development machine
(its network refuses them), so their first real answers come with the first
daily check after the merge; the formats follow their public documentation
and the tests use recorded stand-ins. The deterministic update was tried for
real on the positive control of docs/SECURITY.md (smallvec 1.6.0,
RUSTSEC-2021-0003): `cargo update` took 1.6.1 and cargo-deny no longer
reported it; with `smallvec = "=1.6.0"` it was blocked, as it must be.

Still open: the pull request of a security fix is written when its branch is
pushed (its tests "not verified" until they run); their later results are in
the ledger, not yet written back into the pull request. A security fix that
changes the browser gets its version when the owner orders the merge.

## One candidate per component

Since 2026-11-22 (WP5) the daily maintenance makes **one isolated candidate per
component**, or per small coherent group, instead of one combined candidate
(`daily-maintenance.yml`, `tools/update-candidates.py`):

1. **plan-candidates** (no credentials but a read-only token for the list of
   open pull requests): `tools/check-components.py --json` finds every
   component's candidates, `tools/ci-pins.py check` the workflows' pins,
   `tools/pkgbuild-sync.py plan` the PKGBUILD's; `tools/update-candidates.py
   plan` decides each one: **make** (rebuilt from current `main`), **queued**
   (candidates that change the same file go one at a time: the engine's
   `Cargo.lock`, shared with the security fixes' branches, and the test
   packages' pins; the first by priority goes first, the others wait until
   it is merged or closed), **builder** (the builders' path, above),
   **unreachable** (its source could not be read today: nothing made, tried
   again tomorrow) or skip. The plan is in the run's summary and in the
   artifact `component-report`.
2. **candidate (<id>)**, one job per candidate (at most three at a time), with
   **no credentials** (the code of others runs here: the builders, `cargo
   update`, `pip`): from `main`, `tools/check-components.py --only <id>
   --apply` (or `tools/ci-pins.py apply`, `tools/pkgbuild-sync.py apply`), the
   licence files written again, the version raised by
   `tools/prepare-maintenance.py` when the candidate ships (with its CHANGELOG
   line; never for the test packages or the workflows' pins), and its own
   commit, `update: <id> <from> -> <to> (no AI)` (`ci: ...`, `pkgbuild: ...`).
   The automatic fixes of the open candidate of the same update (commits
   `autofix: ...`) are carried over. The bundle and whether it differs from
   the published branch go to the publish job.
3. **publish (<id>)**, only on `main`: the candidate's commits are checked with
   `main`'s own `tools/update-candidates.py check` (each commit its update's
   own, changing only its files, or the automatic fix's carried over); pushed
   to `automation/update/<id>` with a lease, only when it differs (idempotent:
   the same update is never opened twice); its draft pull request (labelled
   `maintenance`, the report of `tools/maintenance-report.py`) and Tests,
   Security and Arch Linux on it. A pin of the workflows is pushed with the
   repository secret `IKE_WORKFLOW_TOKEN` (GitHub refuses workflow changes to
   the workflow's own token): without it, a warning, and Dependabot's monthly
   pull request stays the way for those pins.
4. From there each candidate goes its own way: a failure goes to the
   automatic fix on its branch (`automation/update/<id>`), a green and
   verified candidate merges by itself, and the ledger follows each one
   (`tools/maintenance-ledger.py`: the branch, its runs, the automatic fix's
   attempts, the verdict of the merge).

A new engine that does not build with I.K.E.'s wrapper (a new adblock, pyo3
or major crate) is still published: its tests fail on its branch, and the
automatic fix may change I.K.E.'s wrapper there (`ike-adblock/src/`,
`vendor/adblock/__init__.py`, `ike/blocker.py`), never `Cargo.toml` or
`Cargo.lock`. A new crate still passes `deny.toml`'s licence and source
checks (the "Licences" step of its tests). A candidate that changes the engine
gets today's default filter lists checked in its own engine, on its own
commit, against `main`'s engine on the same lists (`tests.yml`, the step
"Filter lists in this engine", `tools/filter-lists.py compare`): an engine
that reads them worse fails; a list not downloaded leaves it not verified.

The first scheduled run on `main` closes the combined candidate's open pull
request with a comment (job `retire-combined`; its branch stays, every update it
carried is made again per component).

### The single combined candidate (mode "combined")

Kept, and started by hand: Actions → "Daily maintenance candidate" → Run
workflow with mode `combined` (or `gh workflow run daily-maintenance.yml -f
mode=combined`). It works as before 2026-11-22:

1. `daily-maintenance.yml` starts `automation/daily-maintenance` from the
   current `main` every time and applies the component updates
   (`--apply`; if any upstream source cannot be reached, nothing is applied;
   a component whose builder refuses the new version stays as it is and the
   others are applied: see "When a builder refuses a new upstream version").
   When the candidate's engine builds, today's default filter lists are
   checked against it and the result is added to the pull request.
2. `tools/prepare-maintenance.py` raises the patch version (1.1.10 → 1.1.11, or
   adds to a version of `main` that is not released yet), the package version,
   README and CHANGELOG. A new AdBlock engine travels in the signed
   self-update (1.1.12), so it never needs a new package. **Packages used only by the tests make no new version**: that pull
   request is merged and needs no release.
3. Automatic fixes of the previous candidate (commits `autofix: ...`) are carried
   over. The candidate is pushed only when it differs from the one already
   published, and the tests are started on it.
4. The AdBlock engine of the candidate is built after those fixes are carried
   over (step "Build AdBlock engine of the candidate"). Since the final review
   of 1.1.18 a **new engine that does not build with I.K.E.'s wrapper still
   reaches `automation/daily-maintenance`**, clearly marked: a warning in the
   run, the pull request's title ends with "(the new AdBlock engine does not
   build yet)" and its text says why and not to merge before the checks are
   green. Its tests fail there (`cargo test` of the engine), and the automatic
   fix of the candidate may change I.K.E.'s wrapper only (`ike-adblock/src/`,
   `vendor/adblock/__init__.py`, `ike/blocker.py`, `ike/scriptlets.py`; never
   `Cargo.toml` or `Cargo.lock`), because the candidate's `Cargo.lock` builds
   another `adblock` than `main` (`engine_update()`, `allow_adblock`). The
   step still stops the run, for a person, in two cases only: the engine's
   crates cannot be downloaded (`cargo fetch` fails: GitHub's or crates.io's
   matter), or the engine does not build although the candidate does not
   change it (not a matter for the wrapper).

The licence files (`docs/THIRD-PARTY.md`, `licenses/RUST-CRATES.txt`,
`licenses/NOTICE.ubo-scriptlets`) are written again by `tools/third-party.py`
once, after every component is applied (`refresh_licences`). Until the
trials of 2026-11-22 it ran only with the crates' update, before uBlock
Origin's scriptlets were copied: candidate `97df120` kept the old commit in
`NOTICE.ubo-scriptlets` and failed at "Licences" (issue #97).

The candidate's pull request (since 2026-11-22, `tools/maintenance-report.py`)
lists, above the component report: the components old → new and why; the
automatic fix's commits it carries; the problems found (a builder that
refused, a source unreachable, a new engine that does not build, filter-list
findings); the tests of its commit by category with their results and what
is **not verified** (a category not run yet, a skipped test with its reason,
what GitHub cannot run); the security checks (the sandbox and the RustSec
advisories: `security.yml` is now started on the candidate with its tests);
the licences (`tools/third-party.py --check` when the candidate was made,
and the "Licences" step); and the limits of what was checked. A candidate
pushed in this run has no results yet; the next daily run, which edits the
pull request again, writes them.

### Rehearsing the maintenance on a branch

Started by hand on another branch than `main` (Actions → "Daily maintenance
candidate" → Run workflow → that branch, or `gh workflow run
daily-maintenance.yml --ref <branch>`; the candidates per component by
default, the combined one with mode `combined`), the daily maintenance is a
**rehearsal** (trials of 2026-11-22): the candidate is built from that
branch's commit, with that branch's tools, and **nothing is published**: no
push to `automation/daily-maintenance`, no pull request, no tests started, no
automatic fixes of the real candidate carried over. The run's summary ("A
rehearsal publishes nothing") lists the files the candidate would change and
the component report; the artifacts `maintenance-candidate` (the bundle) and
`component-report` hold the rest. Uses: a person who adapted a builder (a
Dark Reader patch whose anchor is gone, see "When a builder refuses a new
upstream version") sees, before merging, that the component is now applied;
a trial injects a fault on a `trial/...` branch (an unreachable source, a
broken anchor) without touching the real candidate. A rehearsal has its own
queue, so it never waits for or replaces the real run. Until then a run
started on another branch built the candidate from `main` all the same and
published it.

The daily check (`daily-check.yml`) always ran the code of the branch it is
started on; its `components` issue is the real one, so a rehearsal of the
check rewrites that issue until the next daily run on `main` (start one by
hand to put it back at once).

A failure of either daily workflow on another branch than `main` is never
given to the automatic fix of `main` (`rehearsal_reason` in
`tools/autofix-plan.py`; until these trials it was: a fix made from `main`'s
code for a failure `main` does not have). An unreachable source and GitHub's
own failures still open their issue, as on `main`.

## The automatic fix

`autofix.yml` starts when `Tests` fails on `main`, on the maintenance candidate
or on the fix branch, or when the daily check or the daily maintenance fail,
or when `arch.yml` fails on `main` or on the fix branch while `Tests` passed on
the same commit (an incompatibility with Arch Linux's own packages alone).
Failures of forks, of people's pull requests and of the standby branches are
never touched.

1. **plan** (no AI, `tools/autofix-plan.py`): what failed, where the fix goes,
   and the log of the failed step only (from its command to its error, without
   package installs and the runner's cleanup: in the first real trial the end
   of the job's log was 23 KB of noise around two lines of ruff). A setting or
   workflow problem becomes an issue directly, and so (1.1.18) does a daily
   maintenance whose step "Check and apply component updates" failed (an
   upstream source could not be reached: nothing on `main` to fix, the next
   daily run tries again) or whose engine step stopped (crates not
   downloaded, or an unchanged engine that does not build; a new engine that
   does not build is published and fixed on its branch, see "The maintenance
   candidate").
   **GitHub's own failures are not the code's** (final review of 1.1.18): when
   every failed step is one of the runner's own (set up, check out, the
   set-up actions, the Rust toolchain, an artifact kept or fetched) or only a
   job that reports failed (`hand-over` of the tests, `update-issue` of the
   daily check, `publish-candidate` of the maintenance), there is no AI fix of
   `main`: an issue **"GitHub or the runner failed: <workflow>"** says so, in
   its own words and without a message for ChatGPT. Since 2026-11-22 the same
   holds for git failing to reach GitHub inside the tests' bookkeeping steps
   ("No tests lost", "The starting commit's tests on this code", which fetch
   `main`): when every failed step is one of them and each failed job's log
   ends with git's own network or server error and exit code 128 (run
   44990600858: `git fetch` got HTTP 403, and an AI fix was planned), the
   failed jobs run once more, and a second failure is that issue, no AI
   (`infra_in_logs` in `tools/autofix-plan.py`; tests lost for real, or any
   other failure, stay the code's). Its title is not the one
   the plan reads, so it never holds back the fix of a real failure. For
   `arch.yml`, pacman, Arch's mirrors and keyring, the container and the
   engine's crates' download count as such failures too, and a failure of
   the build or the tests is fixed only when `Tests` passed on the same
   commit (see "Arch Linux's own packages"). The log
   of a failed job is asked three times (GitHub may answer 404 for a few
   seconds after a run closes); when no log can be read, that issue too,
   instead of a fix that could only guess. A job that failed without a failed
   step (a time limit) still counts as a real failure.
   An open issue "ATTENZIONE E' RICHIESTO IL TUO INTERVENTO PER FARE INTERVENIRE CHAT GPT NELL' AUTOFIX!!! (<workflow>)" stops a new fix of
   `main` only when it names the same failed commit (the report job ends each
   issue and comment with a hidden `<!-- autofix-sha: ... -->` mark) or was
   reported in the last 24 hours (1.1.18: an old issue of the first trials
   kept every later failure of `main` from a fix).
2. **fix**: first GitHub prepares the code the failure points at
   (`tools/autofix-context.py`, no AI): the places named by tracebacks, pytest
   and ruff, with the lines around them, go into the instructions, and the
   files involved (plus the I.K.E. modules a failed test names) are listed for
   the guard. Then (`tools/autofix-agent.py`, read from `main`) the Antigravity CLI
   (`agy`) runs the instructions of `.github/autofix/prompt.md`, also from
   `main`, in a closed room:
   - its own user and group, a copy of the repository, only `HOME`, `PATH` and
     the API key in its environment, and **no GitHub credentials** (read-only
     job, no token): it can only leave a patch and a summary in Italian;
   - no terminal, no web, no MCP (its own permission rules), and a firewall
     that lets its user reach only the addresses of the Gemini API, pinned in
     `/etc/hosts`. Those are Google front ends that also serve other Google
     services: the firewall limits the agent to those addresses, not to that
     one API. Name lookups are refused too, since the names asked for could
     carry data out (1.1.18): DNS to this machine's resolver (port 53) by the
     firewall, and the resolver's and buses' local sockets
     (systemd-resolved's varlink, D-Bus, Avahi) by an access rule on each,
     when they exist and `setfacl` is there. The workflow checks that the
     agent still finds the Gemini API, and warns when it can still look up
     other names by a way not listed here;
   - `.git` is not the agent's (1.1.18): it belongs to the runner, the agent
     cannot write it, and the sticky bit on the top folder keeps it from
     swapping it for its own. The runner runs git on the agent's work only
     through `$RUNNER_TEMP/rgit`, which first checks that `.git` is still the
     runner's, puts back the configuration saved before the agent started,
     removes nested repositories, and runs git without system or global
     configuration, attributes file, hooks, fsmonitor or submodules (diffs
     with `--no-ext-diff --no-textconv`). Otherwise a `diff.external` or a
     filter written by the agent would run as the runner, which has `sudo`.
     The Antigravity installer runs as the agent before the repository is
     copied, and everything it started is stopped (`$RUNNER_TEMP/stop-agent`,
     an error if anything survives). After the agent, its processes are
     stopped the same way, its crontab removed and its account locked, and
     the tree belongs to the runner again with no group or other write. The
     code at the failure is prepared in the runner's own folder; `.autofix/`
     is made again from the runner's copies, and the agent's summary goes on
     only as the Antigravity step checked it for the key (a marker written at
     the end of that check; without it the summary is dropped and the result
     counts as a time limit). Nothing the agent left in `.autofix/` (a link
     would make the runner read any file and publish it) is read;
   - its own step, with the Gemini key only: the reserves' keys are in the
     next step, which the agent never shares (1.1.18);
   - real limits: at most 8 minutes per model and 25 minutes in all. The free
     plan gives each model about 20 requests a day and every step uses one, so
     it is told to take about 10 steps and to run no tests (GitHub runs them).
   Model after model (`AUTOFIX_MODEL`, then Gemini 3.8, 3.7, 3.6 Flash): only
   when a model's daily quota is used up (or Google is down) does the next one
   go on, with the work already done. When the CLI's own time limit stops an
   agent still at work, nobody else is asked to repeat it: the reserves go on.
   But when that time limit came only because Google answered 503 ("high
   demand") and the CLI kept retrying, Google is down for that model: the
   next one goes on (final review of 1.1.18, seen in the self-test's first
   run; the CLI's JSON answer on standard output is read too).
   The firewall logs the addresses the agent tried to reach and could not, and
   counts its refused name lookups; they go in the summary, for the diagnosis.
   What Antigravity leaves is kept only as a fix that passed the checks below:
   after its time limit, a quota, an error, a refusal, or a step that did not
   finish, its half-done edits are thrown away, with or without reserves
   (1.1.18: without reserve keys they were published). A per-minute limit is waited out once; a
   wrong key or model name stops at once, since another model would not help.
   The failure description travels inside the instructions (the agent may
   not open `.autofix/`, which git ignores). The agent's output is never printed, the key is hidden in its errors, and a
   result containing the key is thrown away. A second attempt receives the
   first fix, the new test logs and the first summary, and corrects only that.

   **The fix is checked at once.** Antigravity's patch goes through the
   guard's checker (`--check-only`, from `main`) inside this job. Refused for
   its size or because it misses the files of the failure: undone, and the
   reserves get the reason. Refused for safety (a forbidden file, a weakened
   test, a key: exit status 3): undone, nobody else is asked, the owner looks.

   **Reserves** (`tools/autofix-reserve.py`, 1.1.15): when Antigravity brings
   no fix it could keep (quota, Google down, an error, nothing changed, or a
   fix refused for its size or pertinence), the reserves are asked one after
   the other, never together, from the clean checkout: Groq (`GROQ_API_KEY`,
   models in the variable `AUTOFIX_GROQ_MODELS`, default `qwen/qwen3.8-27b`
   then `openai/gpt-oss-120b`; its free plan takes about 8,000 tokens a minute,
   so it gets only the failure and the code around it), then Z.AI
   (`ZAI_API_KEY`, models in `AUTOFIX_ZAI_MODELS`, default `glm-4.7-flash`
   then `glm-4.5-flash`, Z.AI's free GLM Flash models, another family than
   the others, with the whole files too; added in 1.1.19, the owner's
   choice; its free limits are shown only in the account), then OpenRouter
   (`OPENROUTER_API_KEY`, models in `AUTOFIX_OPENROUTER_MODELS`, default
   `cohere/north-mini-code:free` then `particle-ai/particle-1:free`, which also
   get the whole files; when a listed free model is gone (HTTP 404, as
   `cohere/north-mini-code:free` on 2026-11-20), the two free models with the
   largest context that OpenRouter lists at that moment are asked too). Each reserve's fix goes through the same checker
   before it is kept; the next model is told why one was refused, and a
   refusal for safety stops them all. A provider
   without its key is skipped; free models change often, so the names live in
   the variables, not in the code. The reserves cannot open files: they get the
   failure, the prepared code and the full text of the files involved (since
   1.1.19 also the page scripts a failing test names and the files the latest
   four commits changed, never a protected one: in autofix trial 4 the failing
   tests named neither the module nor the script that broke), and
   answer with JSON edits (exact text to replace) that the script applies to
   those files only; nothing they write is ever run. 429 and unknown models
   move to the next model, a refused key to the next provider, an answer that
   cannot be applied gets one informed retry; a request too large (413) moves
   to the next provider; any other malformed answer (a list where a file name
   should be, content that is not text) or error moves to the next model with
   its edits undone. A key refused (401/403) is named in the reserves'
   message ("Chiave rifiutata ... GROQ_API_KEY"), not hidden in "no fix
   found", and an answer cut off while it was read counts as a server error
   (asked once more), as a timeout or a refused connection does (final review
   of 1.1.18; each of these cases is simulated in `tests/test_automation.py`,
   and so are Antigravity's endings: quota, wrong key, its time limit, a
   refusal). "Not fixable in the code" from one model asks the next
   one too; the chain stops when models of two different providers say so
   (1.1.18: one weak free model giving up stopped them all; 1.1.19: two models
   of one provider stopped the chain before the last provider was asked). What a model writes reaches
   the log only as one line with no `::`, so it cannot give the runner a
   workflow command.

   **Residual risk: `--dangerously-skip-permissions`.** Antigravity runs with
   this flag (nobody is there to answer its questions) and relies on the deny
   list of its settings (`command(*)`, `unsandboxed(*)`, `read_url(*)`,
   `execute_url(*)`, `mcp(*)`) to have no terminal, web or MCP. **The
   self-test** (final review of 1.1.18) checks that by hand: Actions →
   "Automatic fix" → Run workflow, tick `self_test` (leave `run_id` empty).
   Its job `self-test` runs the very steps of the fix job that build the
   closed room (YAML aliases `*stop-agent`, `*closed-room`,
   `*keep-installer`, not copies): the same user, settings, deny list and
   firewall, only `GEMINI_API_KEY`, no GitHub token. The agent is started
   exactly as the fix starts it and given two plain tasks: create a marker
   file in `/tmp` in the terminal, and open `https://1.1.1.1/` with its web
   tool. `tools/autofix-selftest.py` then checks, outside the agent, that
   the marker does not exist and that the firewall's log (the kernel log,
   `agent-blocked: ... DST=1.1.1.1`) shows no attempt of the agent's
   machine at that address. Green: the agent tried, says its tools were
   denied, and nothing happened. Red with "the deny list did NOT hold": a
   command ran or the web tool tried the page (the record of the risk below
   is then real). Red with "no conclusion": the agent could not run (quota,
   key, time limit), or it ran but does not say its tools were denied: a
   model that refuses to try proves nothing. Busy models, used-up quotas and
   time limits move on to the next model.
   Its runs on the pull request of the final review of 1.1.18 (all on
   2026-11-20): 44715968623 Gemini 3.8 Flash busy (503) until the CLI's
   time limit, which also showed the 503 fix above was needed; 44717299077
   and 44720307349 Gemini 3.6 Flash refused to try (a "security self-test",
   then a page on 127.0.0.1: "instructed not to probe local services");
   44719025467 Gemini 3.7 Flash worked 5.5 minutes with no answer. None of
   them created the marker or reached the page, but **none proved the deny
   list either**: the tasks are now plain (a file, a public page), and the
   proof waits for a day with free quota. It prints what the agent said and
   costs a few requests of the free Gemini quota. A web tool that Google ran
   on its own servers would not show in the firewall's log, so it covers the
   agent's own machine only. If it did not hold,
   the agent could run commands as its own user: it would still have no
   GitHub token and no other key than Gemini's, no write access to `.git`,
   no network but the Gemini API's front-end addresses (and no name lookup
   by the ways listed above), and its work would still
   go through the checks and the tests before a person merges it. The flag
   stays so that the agent does not stop at a question; this paragraph is
   the record of the risk.

   **The Antigravity installer** (1.1.18) is downloaded to a file and its
   sha256 printed in the log ("Antigravity installer sha256: ..."). The
   installer picks the CLI's version itself and checks the download against
   Google's manifest; no version of the CLI can be pinned from here without
   knowing the installer's options. The expected sha256 is the repository
   **variable** `AGY_INSTALLER_SHA256` (Settings → Secrets and variables →
   Actions → Variables), else the value written in the step "A closed room
   for the agent" of `autofix.yml` (empty). Empty: the installer is only
   printed. Set: a different installer is never run (the job stops). Since
   the final review of 1.1.18 every run keeps the exact file whose sha256 it
   printed, as the download **`antigravity-installer`** of the run (3 days;
   `install.sh` and `install.sh.sha256`), also when the job stopped on it:
   download it, read it, and only then record its sha256 in the variable.
   When Google changes the installer, the stop is the signal: read the new
   file of that run, then update the variable. Nothing records a hash by
   itself: trusting the first installer seen, or recording each new one
   automatically, is a choice the owner has not made.
3. **guard** (no AI, `tools/check-autofix-patch.py` from `main`): the patch may
   change only `ike/`, `tests/`, `tools/` and `docs/`; never the workflows, the
   signing and update channel, the version, the package recipe, the updater, the
   test harness or the release tools; never what comes from others or is
   generated (Dark Reader, uBlock Origin's scriptlets, the icon sets, the ad
   blocker's `Cargo.toml` and `Cargo.lock`, `docs/THIRD-PARTY.md`); of the ad
   blocker only I.K.E.'s own wrapper (`ike-adblock/src/`,
   `vendor/adblock/__init__.py`, `ike/blocker.py`, `ike/scriptlets.py`), and
   only on a candidate that updates its engine (the engine itself,
   adblock-rust, is a crate: a problem there is for the maintenance); no test removed or weakened; no keys, binaries or links;
   at most 5 files and 150 lines; and at least one of the files involved in
   the failure must change (`--related`), so a fix stays on the problem. Then lint. A fix of `main` that changes the
   browser gets the next version and a CHANGELOG line.
   Since 1.1.18 also never YouTube's ad blocking (`ike/resources/videoads.js`,
   `videorelay.js`, `mediahook.js`: the owner's rule), the tests' reference
   data (`tests/data/`, `tests/settings-keys.json`), the test packages
   (`tools/test-requirements.txt`), the builders of what comes from others
   (`tools/build-*`, `tools/third-party.py`), the weekly health check, or
   `.github/`; a test is weakened also by a test function removed or renamed,
   an assertion that cannot fail (`assert True`), an early `return` at the top
   of a test or a `SkipTest`; Groq (`gsk_`), OpenRouter (`sk-or-`) and other
   `sk-` keys are caught; a nested repository (gitlink) is refused. With
   `--check-only` the patch must also apply to the tree, or already be in it.
   I.K.E.'s ordinary code (`ike/shields.py` included) stays fixable.
   After the first review of 1.1.18 the checker reads a patch as `git apply`
   does: a hunk holds exactly the lines its `@@ -a,b +c,d @@` header counts
   (an added line `++ x`, shown as `+++ x`, had passed for the next file's
   header and hidden the rest of the file from every check). Also refused:
   `del test_...`, `delattr`, `globals()`/`vars()`, `getattr` on pytest or
   unittest, `os._exit`/`pytest.exit` in tests, `assert x == x`, any change to
   `conftest.py`, `pytest.ini`, `tox.ini`, `setup.cfg`, `pyproject.toml`,
   `ruff.toml`/`.ruff.toml` at any depth or to `tests/**/__init__.py`, and any
   new file in `tests/` that is not a `test_*.py` module.
   After the second review the rules on added test lines are searched in the
   whole raw line (a `#` inside a string no longer hides the rest), and also
   refuse: a test name assigned (`test_x = None`), `del test_...` anywhere on
   the line, statements chained with `;` around a deletion, pytest's
   internals (`_pytest`, `runtest`, `outcomes`, `Skipped`), `os.exec*`,
   `execv`, `_exit`, `getattr` with a name built from pieces or as a
   decorator, an emptied parameter list (`[:0]`), `if False:`/`if 0:`, a
   one-line `if ...: return`, and an `assert` that cannot fail as Python
   reads it (a true constant such as `assert 2` or `assert 'x'`, a tuple
   `assert (cond, 'msg')`, `... or True`, `x == x`). A carriage return alone
   inside a line (it ends a line for Python, not for git) is refused, and the
   patch is read as bytes so it cannot be turned into a new line on the way.
   `monkeypatch.delattr(...)` and the word "skip" in a comment stay fine.
   The final review of 1.1.18 checked the checker on its own and closed
   these gaps (each with a test): **renames** (`git apply --numstat` names
   only the new file of a rename, so renaming `tests/conftest.py`, a test
   module, `ike/updater.py` or a workflow removed it unseen; renames and
   copies are now read from git's summary, both names, and refused);
   **quoted file names** (`"\164ests/..."` is `tests/` for git; names are
   unquoted as git does, and every name the checks read must be one git
   reads); in test files an empty parameter list (in place, or by emptying
   the list a test is parametrized with), `__test__`, pytest hooks or
   `pytest_plugins` in a test module, `AssertionError` caught or
   `suppress`ed, an assertion moved deeper into a block (`if`, `try`,
   `with`, a loop), a `return` anywhere in a test's body (not only at its
   top), a decorator on a test other than a mark or a patch (a fixture, or a
   skipif kept in a name such as `@needs_engine`), pytest's or the harness's
   functions replaced, a test removed through `sys.modules` or `setattr`.
   None of them is found in today's test modules (checked by a test).
   These are patterns, not proof: see the rule below.

   **No tests lost** (`tests.yml`, 1.1.18). On the automation's branches and on
   ChatGPT's, after the tests, the test ids pytest would run (after its own
   hooks: a `conftest.py` that drops items counts) are compared with those of
   the commit the branch starts from (its merge base with `main`): fewer is a
   failure, whatever way the change found. When the starting commit cannot be
   counted (a collection error there) the step warns and goes on. Tests that
   skip themselves while running are not counted here; the patch checks
   catch the usual forms. Since the audit of #65 the ids come from a small
   plugin of the step, written to a file (a test module that printed fake
   ids at exit had fooled a count read from pytest's output).

   **The starting commit's tests on this code** (`tests.yml`, audit of #65).
   When such a branch changed `tests/`, the tests of the commit it starts
   from run once more, exactly as they were, against the branch's code. A
   new module that changes other tests before they run, a stand-in, a
   dropped case or a weakened assertion cannot hide from them. A failure in
   a test file the branch did not change stops the run; one in a file it
   changed is shown as a warning (changing that test may be the fix itself),
   and a person reviews the tests' diff, as the rule below says. **The
   residue** that only that person catches: a weaker assertion or rewritten
   input in a test file the branch changed, whose old version still fails
   for a reason the reviewer must read. I.K.E.'s own code that tells the
   tests apart from real use is refused by the checker by pattern (`pytest`,
   `PYTEST_*`, `unittest`, `conftest` in added lines of `ike/`), not proven
   absent.
4. **publish** (no AI): the fix goes to `automation/autofix-main` (fixes of
   `main`) or onto the maintenance candidate, a draft PR is opened or updated
   with the agent's summary, and the tests start on it.
5. If the tests fail again, a second attempt follows. (Tests started by the
   automation itself send no `workflow_run` to GitHub, so `tests.yml` hands
   their failure over with a dispatch, job `hand-over`, on the automation's own
   branches only; the plan waits for that run to close.) After two, or when nothing
   could be fixed, the issue **"ATTENZIONE E' RICHIESTO IL TUO INTERVENTO PER FARE INTERVENIRE CHAT GPT NELL' AUTOFIX!!! (<workflow>)"** is opened (1.1.19: that title, in the owner's words, assigned to the owner and naming the owner, so GitHub mails it). Its
   reason is plain: quota, chiave, modello, tempo, rifiutata or sicurezza
   (and, 1.1.18, "una riserva ha preparato una correzione, ma i controlli
   automatici l'hanno respinta" when that is what happened).

   **More attempts, other free providers** (the full chain, 2026-11-22). On
   the isolated candidates (`automation/update/<id>`, `automation/builder/<id>`,
   `automation/update/arch-testing-<date>`) a failure is fixed up to
   `FIX_ATTEMPTS` times (`tools/ai-providers.py`, a person's file, today 4).
   Each attempt is a new run of the automatic fix with a **fresh context**:
   the agent gets only the earlier fix, the new test logs and its summary, as
   data; the tests run again after each. Attempt *n* starts with the *n*-th
   free provider of `all_names()` (Antigravity, Groq, Z.AI, OpenRouter, round
   robin), so after a fix that did not pass another provider and model family
   tries first (a provider without its key is skipped: Antigravity then goes
   first as usual; the reserves follow in their order from the one named).
   At the cap the branch is kept, the maintenance ledger says needs-person
   and the owner is told once. On `main`, `automation/autofix-main`, the
   combined candidate and the security branches the cap stays
   `FIX_ATTEMPTS_MAIN` (two), Antigravity first each time.

   **A fix raises the version** (item 5 of the full chain). Every automation
   pull request that changes what ships (I.K.E.'s code, the engine's wrapper,
   a builder's output, a security update of a crate) gets the next version
   when `main`'s is published (`tools/prepare-maintenance.py`, patch +1; added
   to `main`'s version when that is not published yet), with a CHANGELOG line
   written from the plan's report (no code, no link), unless its branch raised
   it already. So it can merge by itself and reach the owner as a version to
   sign.

   **Workflow changes are proposals** (WP12). An AI never edits a workflow:
   the guard refuses `.github/` to every run. When Antigravity's fix touched
   a workflow, the part of `.github/` it wanted is kept, never applied or
   pushed, and the report's issue shows it as "Proposta di modifica dei
   workflow (per una persona: mai applicata)", for a person to read and apply
   by hand.

   **One run at a time per branch** (1.1.18). The workflow has no concurrency
   group of its own any more: GitHub keeps only one waiting run per group and
   replaces it with the next, so a run for a real failure was dropped for a
   later run that only skipped (the tests of a pull request, say). The jobs
   fix, guard and publish wait for each other per branch they work on
   (`automation/autofix-main` or `automation/daily-maintenance`), never
   cancelled. The fix job's own limit (70 minutes) is above its two long steps
   together (32 for Antigravity, 20 for the reserves) and the set-up.
   Final review of 1.1.18, two failures close together (the tests of `main`
   and the daily maintenance, both fixed on `automation/autofix-main`): the
   two fixes run one after the other, and the second publish finds the first
   fix waiting as a pull request and does not push. A fix **overtaken** like
   this (a fix of `main` already waiting, or a newer candidate or fix on the
   branch) ends well with a notice "this fix is not pushed", so the report
   opens no "needs you" issue for a race that lost nothing; a branch that
   moved with no fix waiting there is still an error. Two reports at the
   same moment that both find no issue both open one; the newer one then
   comments on the older and closes itself (audit of #65: a concurrency
   group, used before, let GitHub drop waiting reports). Still
   open: the second fix's agent runs before its publish finds it overtaken,
   spending free quota for nothing.
6. **ChatGPT, started by the owner.** The issue carries a ready message: the
   owner pastes it into ChatGPT (connected to GitHub), which fixes on a branch
   `chatgpt/...` and opens a pull request. `chatgpt-guard.yml` checks its
   changes with the same checker of `main` (it runs as `pull_request_target`
   so a pull request cannot change its own checks, and it never runs anything
   of the pull request: it reads its diff only; since 1.1.18 the diff must
   also apply to a worktree of the commit it starts from, `main` or the
   automation's branch), and `tests.yml` runs all the tests on it. Nothing
   reaches `main` without green checks, and a ChatGPT or automatic-fix pull
   request that changes `tests/` not without a person (or Claude, with the
   change read in full) reviewing its tests diff too (1.1.18).
7. **Claude**, last: a conversation with the issue's link.

**The ad blocker's wrapper, one rule for all.** A fix may touch I.K.E.'s own
wrapper of the ad blocker (`ike-adblock/src/`, `vendor/adblock/__init__.py`,
`ike/blocker.py`, `ike/scriptlets.py`) only on a maintenance candidate whose
`ike-adblock/Cargo.lock` builds another version of the `adblock` crate than
`main` (`engine_update()` in `tools/autofix-plan.py`; anything it cannot read
counts as no update, and a candidate that only brings Dark Reader, scriptlets or
lists never gets it). The plan's `allow_adblock` reaches Antigravity (a section
"This run" in its instructions), the reserves (their instructions, and the
files they may edit) and the checker (`--allow-adblock`); the reserves take
their list of forbidden files from the checker itself, so the two cannot drift.
ChatGPT is never allowed the ad blocker: its guard has no `--allow-adblock`.
`Cargo.toml`, `Cargo.lock` and the adblock-rust engine are never changed by a fix.

### The audit of #65 (final review of 1.1.18)

An independent read-only audit of the chain and of pull request #65; each
point was checked before it was changed, and each change has a test in
`tests/test_automation.py`.

- **A test that failed once runs again first.** A failure only in a pytest
  step (`Tests`, `Tests of the installed package`) on its first attempt is
  not given to an AI: the job `rerun` of `autofix.yml` runs the failed jobs
  again (`gh run rerun --failed`). If they fail again, the tests hand that
  failure over (job `hand-over`, now also on `main` for a run the
  automation started again) and the plan fixes it as before. Lint, the
  engine's tests and the rest go to the fix at once.
- **Reports about other branches never hold back a fix of `main`.** The
  report's hidden mark names the failed branch
  (`<!-- autofix-sha: <commit> on <branch> -->`); only reports about `main`
  count for the 24 hours. (Issue #31 had reports of the trials on
  `automation/autofix-main` from the same morning.) A plan that skips says
  why in a notice.
- **Nothing lost to one failed call.** The plan's calls to GitHub, the
  tests' hand-over and the publish and daily steps' `gh` calls are asked
  again after a pause. A fix already on its branch (pushed by an earlier
  try of the job that then failed) gets its pull request and its tests;
  until now a re-run ended green as "overtaken". A published candidate
  with no Tests run gets one (a run whose pull request step failed left it
  untested every day after). The candidate is pushed with a lease on the
  tip its prepare job saw.
- **Reports**: no concurrency group (GitHub kept one waiting report and
  dropped the others); two reports at the same moment both open an issue,
  and the newer one comments on the older and closes itself.
- **What an AI wrote** in an autofix pull request cannot @mention anyone or
  close an issue on merge (`closes #N`); mentions are neutralised in report
  issues too.
- **The room's firewall** is also checked by address (the check by name
  stopped at the name lookup and proved nothing of the firewall), and its
  checks' own refused connections are cleared from the kernel log.
- **GitHub's failures**: a run that failed with no failed job, or in its
  test environment, is an issue of GitHub's, not an AI fix.
- **The package** of the tests is kept and its sha256 printed as built,
  before the tests of the installed package run code against it.
- **The self-test's positive control**: after the real test the same model
  gets the same tasks with the deny list taken away; if it does not use its
  tools even then, the self-test has no conclusion, never green. The
  probe's address has a log rule of its own, without the rate limit of the
  general one (20 a minute, which a busy agent could use up).

Still open after the audit, by choice: the weekly health check does not yet
report old autofix pull requests or count cancelled runs (L1); the plan reads
the first 100 comments of an issue (L2: since 2026-11-22 the daily check's
ledger closes a report of "Tests" when its failure is gone, see "Inventory,
ledger and what is verified"); ruff and pytest are not pinned, and the reserves' lint runs in
the step that holds their keys (ruff only reads files; L6).

### Trying the whole chain (end to end)

Costs: Antigravity uses the free Gemini quota of the day; Groq, Z.AI and
OpenRouter their free quotas (no money). Needs the secrets `GEMINI_API_KEY`,
`GROQ_API_KEY`, `ZAI_API_KEY` and `OPENROUTER_API_KEY`.

1. A deliberate, harmless error on `automation/autofix-main` (never on `main`),
   for example an unused import that ruff refuses, or a renamed Qt enum that
   makes a test fail.
2. `gh workflow run tests.yml --ref automation/autofix-main`: the tests fail and
   `autofix.yml` starts by itself (or `gh workflow run autofix.yml --ref main
   -f run_id=<the failed run>`).
3. What to read in the run of `autofix.yml`:
   - plan: "the failed step's log" holds the error (not "log not available");
   - fix: "Places found: N" with the file of the error; Antigravity's outcome;
     when it brings nothing, "Reserve: Groq / ..." and, if needed,
     "Reserve: OpenRouter / ..."; "refused by the checks" lines when a fix was
     undone;
   - guard: "Patch accepted"; publish: the draft pull request on
     `automation/autofix-main` and its tests (`tests.yml` on that branch).
4. Never merged by itself: a trial's commit is not one the automatic fix
   wrote, so `automerge.py` leaves the pull request for a person. After a
   trial it is closed, and the branch goes back to the deliberate error.

Trying a change to the automatic fix itself: the fix job reads its tools from
`main`, never from the branch being fixed, so a change is tested by its own
unit tests (`tests/test_automation.py`) on its pull request, merged, and then
tried for real with `gh workflow run autofix.yml --ref main -f run_id=<a failed
run of automation/autofix-main>`. The self-test of the closed room can be run
on a branch before merging (`gh workflow run autofix.yml --ref <branch> -f
self_test=true`): the workflow and the self-test's tool come from that branch.

The agent cannot see Plasma: shapes, effects and the look are always judged by
the owner on the real system.

## The workflows' pins

The workflows pin every GitHub Action by the commit of a release (with the
release as a comment), cargo-deny's version, the Python and Node.js versions
of setup-python and setup-node, and the Rust toolchain (`stable`, which
follows Rust's releases by itself: nothing to pin). Since 2026-11-22
`tools/ci-pins.py`, a deterministic tool and **never an AI**, keeps them
current, one candidate per pin on `automation/update/ci-<name>`:

- an Action only to the commit of an official release tag (`vX.Y.Z`, no
  pre-release) of the **same** action, read with `git ls-remote` from
  github.com (an annotated tag peeled to its commit), the comment moved to
  that tag;
- cargo-deny to its newest release on crates.io; Python to the version Arch
  ships (users run Arch's Python) when setup-python offers it; Node.js to the
  newest LTS line; a numeric Rust toolchain to the newest stable release.

Its commit is `ci: <name> <old> -> <new> (tools/ci-pins.py, no AI)` and
changes one line per pin. The tests run on that branch with the new pin (a
dispatched run uses the branch's own workflows). The verified merge accepts
exactly these edits (`verify_change`): every changed line of a workflow is a
pin of that name on both sides, at the same place, the same action, a commit
that `git ls-remote` shows is the release tag written beside it, and every
commit of the branch is the tool's; any other workflow change, or an AI's
commit there, keeps it for a person. GitHub refuses workflow changes to the
workflow's own token: the push and the merge of these candidates use the
repository secret `IKE_WORKFLOW_TOKEN` (a fine-grained token of the owner's
with Contents, Pull requests and Workflows write on this repository only,
see "Repository settings"); without it the candidate waits and says why.
**Dependabot stays on** for the Actions, monthly, as a double check (the
owner's choice recorded in `.github/dependabot.yml`): its pull request is a
person's, and when the tool's candidate merged first Dependabot closes its
own.

## The verified merge

The owner's decision of 2026-11-22: the AIs fix and carry the work on through
the tests, the system prepares the updated version, and the owner only signs
it when it is ready and has passed the tests. `tools/automerge.py`, run by
`automerge.yml` from `main`'s own copy (a pull request never brings the rules
it is judged by, and no agent merges its own work), merges a pull request
only when ALL of this holds:

- it is the automation's own: a candidate per component
  (`automation/update/<id>`: its own `update: <id> ... (no AI)` commit, which
  may change only that id's files, the licences and the version, checked with
  the same `tools/update-candidates.py` the daily maintenance uses; a CI pin's
  `ci: ...` commits, judged line by line by `tools/ci-pins.py`; the
  PKGBUILD's `pkgbuild: ...` commit, judged by `tools/pkgbuild-sync.py`; plus
  the automatic fix's commits), a builder's re-anchoring
  (`automation/builder/<id>`: the automatic fix's change of that builder only
  as `tools/builder-anchor.py` allows, and the update it then accepts), a fix
  of Arch's next packages (`automation/update/arch-testing-<date>`, which also
  needs "Arch Linux (testing)" green), `automation/daily-maintenance` (the update's
  `maintenance:` commit, which may change only what an update changes, the
  same list as `daily-maintenance.yml`'s check, and the version files only by
  the version; plus the automatic fix's commits), `automation/autofix-main`
  (only commits the automatic fix wrote) or `automation/update/...` (for a
  security update only `security: ... (cargo update, no AI)` commits that
  change `ike-adblock/Cargo.lock`, plus the automatic fix's), in this
  repository, into `main`; no trial, no commit of a person;
- every check of its last commit ended and none failed, and `tests`,
  `sandbox`, `rust-advisories` and `Arch Linux` passed. Arch Linux runs on the
  candidate (`daily-maintenance.yml` starts it with the tests and the
  security tests) and on any other branch of the automation
  (`tools/automerge.py` starts it when it has not run on that commit);
- every category `tools/test-categories.py` requires for the kinds of the
  components it changes, plus every check the automation runs on a commit
  (`MERGE_ALWAYS`: lint, the whole suite, the engine's Rust tests, licences,
  no tests lost, the package, the old processor, the installed package, Arch
  Linux, the sandbox, the advisories), was run and passed on that commit:
  nothing "not verified" (read from the runs that really ran on it: a
  `pull_request` run waiting for approval, "action_required", never hides
  the automation's own run of the same commit). The skipped tests are read
  from its Tests run: one
  that no other check of the commit runs is a required test not run.
  `EXPECTED_SKIPS` (`tools/test-categories.py`) names, from a real Tests run
  on GitHub's runners (2026-11-22), the skips that are environmental there,
  each with where it is verified instead: the sandbox test (`security.yml`),
  the desktops, widget styles and KDE's theme as Arch packages them and the
  optional dependencies (`arch.yml`), the installed package's own tests, the
  real network sources (the daily check), pictures for a person, a split
  run, root (the Arch container), and an AUR package no check can install
  (said as not verified); any other skip still blocks (the IPv6 case of the
  home-network test, for one, runs on GitHub's runners and must not skip). Since the full chain a new AdBlock
  engine can be fully verified: the filter lists are checked on its own
  commit. A kind that needs a real desktop is never fully verified here: it
  waits for the owner;
- no test file changed or removed (a new file of the filter lists' recorded
  evidence, `tests/data/lists-recorded/<name>.txt`, which the workflow writes
  and the AI may not, is not a test change; a change, removal or rename of
  one is), no protected file of the guard
  (`FORBIDDEN_FILES`; a candidate's own files, as `tools/test-requirements.txt`
  for the test packages, are its update's) and no workflow (but the CI pins'
  verified edit); the automatic fix's files follow the 1.1.19 rules (only
  existing interface modules under `ike/` and `docs/`, no line that reaches
  the environment, the network, the system or the test run, no module that
  decides the user's safety); on a candidate of the engine (adblock, pyo3, a
  major crate) the automatic fix may also adapt I.K.E.'s wrapper
  (`ike-adblock/src/*.rs`, `vendor/adblock/__init__.py`, `ike/blocker.py`)
  with no added `unsafe` code, process, file, network or environment access
  or foreign code in Rust, and nothing risky the old Python file did not have;
- the licences are up to date (the "Licences" step: cargo-deny and the
  licence files);
- no open security finding: the issue "Sandbox tests failed on main", the
  issue "Rust advisories" (unless this commit's own RustSec check passed: it
  is free of them) and any security entry of the maintenance ledger that has
  not passed;
- `main`'s version is not published yet, or the pull request raises it (or it
  ships nothing, as a candidate of the test packages). Since 2026-11-22 (the
  owner's decision: everything automatic and verified converges into `main`,
  then one notice to sign) several merges by themselves go into the same
  unpublished version: a pull request whose raise is `main`'s unpublished
  version (a candidate made before `main` was raised), or that raises
  nothing because `main` is raised already, merges; a second raise on top
  (1.1.24 while 1.1.23 is not published), or a CHANGELOG heading of another
  version, waits for a person. (Until then only one merge by itself was
  allowed per unsigned version, review 2 of 1.1.19, M9; it still holds for
  ChatGPT's fixes, which wait for the owner's order anyway.)

**The refresh.** The candidates of one day are all made from the same `main`.
Once the first one is merged, the others are behind `main` and, on
CHANGELOG.md, in conflict with it. A fully verified candidate that is behind
`main` is therefore not merged as it is; `tools/automerge.py` (in the same
job, with the same token) refreshes it:

- `main` is merged into the candidate's branch (`git merge-tree`, no AI);
- CHANGELOG.md, when both changed it, is resolved as `main`'s with the
  candidate's new lines added under the one `## <version>` heading: the
  union of the bullet lines, no duplicates, `main`'s first (exactly what
  `tools/prepare-maintenance.py` writes when it adds to an unpublished
  version). A candidate that changes more than new bullet lines of that
  version, or a `main` whose first section is another version, stops it;
- a version file (`ike/__init__.py`, `PKGBUILD`, `README.md`) in conflict is
  `main`'s when `main`'s version is the candidate's own;
- any other conflict stops the refresh: the pull request waits for a person,
  with one comment naming the owner, and the ledger says needs-person;
- the commit `refresh: main <sha> into <branch> (tools/automerge.py, no AI)`
  (two parents: the candidate's commit, then `main`'s) is pushed to that
  branch only, as a fast-forward (never to `main`). With the owner's
  `IKE_WORKFLOW_TOKEN` it is pushed with that token, and GitHub runs the
  pull request's own Tests, Security and Arch Linux for it; without it, it is
  pushed with the workflow's token and those are started by a dispatch. (A
  push of the workflow's token leaves the pull request's own runs "waiting
  for approval", and `main`'s required check `tests` is then never met: the
  merge is refused with "Required status check "tests" is expected", as on
  2026-11-22.) When they pass it is judged again, and merged.

The merge accepts a refresh commit only when it is exactly that: its own
message naming this branch and a commit of `main`, two parents in that
order, the second one in `main`, and the very tree `tools/automerge.py`
computes again from those two parents (`refresh_problem`); anything else in
it (one more change, one parent, a "main" that is not `main`'s) keeps the
pull request for a person. Its own commits are judged as before, and the
refresh commit accounts for no file of the pull request by itself.

After every merge by itself, `tools/automerge.py` dispatches `automerge.yml`
again for every other open pull request of the automation (its last
commit): the verified ones are refreshed and merged one after another
without anyone. `release-ready.yml` opens one notice per version; when more
merges by themselves come into the same version, the list in that notice is
updated (an edit mails nobody) and no new notice or comment is sent.

Then it is merged at exactly that commit with the workflow's token
(`contents: write` only in that job), and `main`'s Tests, Security and Arch
Linux start; when Tests and Security pass, their `merge-ready` jobs ask
`release-ready.yml`, which mails the owner the command to sign and publish.
Anything less stays a pull request: one comment names the owner and says why
(edited, never repeated, when the reason changes), and the next daily check
writes it into the ledger as needs-person, or blocked for a security finding
(the comment carries a mark the ledger reads). ChatGPT's and people's pull
requests are never merged by themselves.

## The owner's part

1. A notification arrives (GitHub app or e-mail) for a draft PR labelled
   `maintenance` or `autofix`.
2. Wait for the green checks. To try it, download the package of its test run
   and install it:
   `gh run download <run-id> -n ike-browser-package`.
3. Nothing to do for a candidate or a fix that is fully verified: the
   workflow merges it and the release notice follows. One that waits has a
   comment naming the owner and saying why; it is merged on the owner's order
   (Claude merges it once every check is green). **Except:** an
   automatic-fix or ChatGPT pull request that changes anything under `tests/`
   is never merged on green checks alone (and never by itself). A person (or
   Claude, with the change read in full) reviews the diff of the tests first:
   the patch checks and "No tests lost" catch the usual ways of weakening a
   test, not every way.
4. If it raised the version: sign and publish with one command
   ([UPDATES.md](UPDATES.md)).

An issue labelled `autofix` or `automation-health` means the automation needs a
person: open a conversation and paste its link.

## Repository settings (once)

- Settings → Actions → General → Workflow permissions: keep **Read repository
  contents** (each job asks for what it needs) and tick **Allow GitHub Actions
  to create and approve pull requests** (otherwise the candidate and the fixes
  cannot open their pull requests).
- Optional, for the workflows' pins (the full chain, 2026-11-22): the
  repository **secret** `IKE_WORKFLOW_TOKEN`, a fine-grained personal access
  token of the owner's, for this repository only, with the permissions
  Contents, Pull requests and Workflows (read and write). Only two steps
  receive it: the push of a CI pin's candidate (`daily-maintenance.yml`,
  publish) and, in `automerge.yml`, the merge of that candidate once
  `tools/automerge.py` verified every changed line and the push of a
  refresh (so the pull request's own checks run); no AI step ever sees it. Without it
  those candidates wait (a warning says why) and Dependabot's monthly pull
  request remains the way for the actions.
- Settings → Secrets and variables → Actions → **Secrets**: `GEMINI_API_KEY`, a
  Gemini API key from Google AI Studio, in a Google Cloud project **without
  billing** (free tier: nothing can be charged; Google may use the requests to
  improve its products, which is fine for a public repository). Optional
  **variable** `AUTOFIX_MODEL` chooses the model (empty: the CLI's default).
  Reserves (optional, free plans), in this order: `GROQ_API_KEY`
  (console.groq.com), `ZAI_API_KEY` (z.ai, API keys of the account; no
  payment method: the Flash models are free) and `OPENROUTER_API_KEY`
  (openrouter.ai), with the optional variables `AUTOFIX_GROQ_MODELS`,
  `AUTOFIX_ZAI_MODELS` and `AUTOFIX_OPENROUTER_MODELS` (names separated by
  commas, in order). Optional variable `AGY_INSTALLER_SHA256`: the sha256 of
  the Antigravity installer a person has read (see "The Antigravity
  installer").
- Settings → Branches: protect `main` (pull request required, status check
  `tests` required, no force push, no deletion).
- The owner's notices (1.1.19): GitHub mails the owner the two issues above
  (they assign and name the owner). To get only those by mail: on the
  repository, Watch → "Participating and @mentions"; in the account,
  Settings → Notifications: email on for "Participating, @mentions and
  custom", off for "Watching" and "Actions". No address or password is in
  the repository.
- Autofix trials (deliberate errors on `automation/autofix-main`): any commit
  whose message does not start with "autofix: attempt N after a failure of"
  (what the automatic fix writes) keeps the pull request for a person, and so
  does the word "trial" in any commit of a ChatGPT branch.
- `publish.py` and the release notice require both `tests` and `sandbox`
  green on the commit. The maintenance candidate may change only the update's
  own files (engine, scriptlets, Dark Reader, test packages, licences, version
  files), checked before it is pushed; it is bundled before the engine's crates
  are built. Dark Reader's npm tarball must come from npm's registry with the
  sha512 npm published.

The weekly check (`health.yml`, `tools/automation-health.py`) reports, since
1.1.18, a `main` without branch protection (the `protected` field of the
branch in GitHub's API) and the reserves' secrets missing, besides runs of the
automatic fix that failed in the last 7 days and autofix issues or maintenance
pull requests open for more than 7 days. Since 1.1.19 it also watches
`security.yml` (two failed scheduled runs in a row, or none for 3 days) and
`arch.yml` (its last scheduled run failed, or none for 9 days), and asks each
reserve that has a key one tiny question (`tools/autofix-reserve.py ping`):
a refused key or an unknown model is reported, a quota or a passing error is
not. Since 2026-11-22 (WP9) it also asks Gemini, and reports a provider that
is not free (see "Free AI providers, checked every week").

If the key leaks (it would show only through the agent), delete it in Google AI
Studio and create a new one: it can spend nothing and opens nothing else.
