# Automatic maintenance

GitHub Actions keeps I.K.E. up to date and prepares the fixes. A pull request
is merged only once its tests are green, and since 2026-11-22 (the owner's
decision) only on the owner's order: nothing merges into `main` by itself.
`automerge.yml` still judges a fix of the automatic fix or of ChatGPT; one
that would have merged in 1.1.19 to 1.1.21 is now marked ready and the owner
is told once (its token cannot merge). Claude merges what the owner asked for;
ChatGPT only on the owner's explicit order (CLAUDE.md). The owner alone
**signs and publishes** (one command on the owner's computer, in the issue
GitHub mails when a release is ready, [UPDATES.md](UPDATES.md)). No workflow releases or
signs anything, and no workflow pushes to `main`.

## What runs by itself

| When | What | Workflow | Result |
|---|---|---|---|
| Every day, 05:17 UTC | Upstream versions of the bundled components (and whether I.K.E.'s builders still accept them), Arch Linux's own packages against the versions the last green `arch.yml` run on `main` tested, and the default filter lists loaded into `main`'s AdBlock engine | `daily-check.yml` | Issue labelled `components` (titled "Component incompatibility: ..." when a builder refused a new version); when Arch's packages changed, `arch.yml` started on `main`; the inventory of every external component and the issue "Maintenance ledger" (label `maintenance-ledger`), see "Inventory, ledger and what is verified" |
| Every day, 06:17 UTC | The updates applied to a candidate built from current `main` | `daily-maintenance.yml` | Branch `automation/daily-maintenance`, draft PR labelled `maintenance` |
| On every PR, every push to `main`, every candidate or fix | Lint, all the tests, the Arch package and its tests | `tests.yml` | Checks on the PR, package download `ike-browser-package` |
| When one of the three above fails, or `arch.yml` fails on `main` or on the fix branch | An automatic fix (for `arch.yml` only when `Tests` passed on the same commit) | `autofix.yml` | Draft PR labelled `autofix`, or an issue "ATTENZIONE E' RICHIESTO IL TUO INTERVENTO PER FARE INTERVENIRE CHAT GPT NELL' AUTOFIX!!! (<workflow>)" assigned to the owner, which GitHub mails |
| Every push to `main`, when the daily check finds Arch's packages changed, after a merge made by itself, on an automatic fix of an Arch failure, and Mondays at 03:41 UTC | The whole suite and the package on Arch Linux's own Python, Qt and Qt WebEngine (`archlinux:latest`), and a record of the versions it tested | `arch.yml` | Artifact `arch-versions` and the run's summary; a failure goes to the automatic fix (see "Arch Linux's own packages"); not a required check of the release |
| Every day, 04:23 UTC, and on every PR and push to `main` | The security tests with the engine's sandbox really on (as a normal user), and the RustSec advisories of every crate of the AdBlock engine | `security.yml` | Checks on the PR; on `main` the issue "Rust advisories" when one is found (no automatic fix) |
| Mondays, 07:41 UTC | The automation itself: every scheduled check (also the Arch and security ones, 1.1.19), one tiny question to each reserve of the automatic fix, and (WP9) whether every AI provider, Gemini included, answers and is free | `health.yml` | Issue "Automation health" when something stopped, failed, waits too long, a reserve's key or model no longer works, or a provider is not free (marked unavailable: the automatic fix skips it); artifact `ai-providers` |
| Once a month | New versions of the GitHub actions used | Dependabot | One PR labelled `maintenance` |
| When a check of a pull request ends, or the automation's own Tests and Security runs of its fix pass (a dispatch) | A fix of the automatic fix (`automation/autofix-main`, only commits it wrote itself) or of ChatGPT (`chatgpt/...`) is marked ready for the owner's order (since 2026-11-22; it merged by itself in 1.1.19 to 1.1.21) when every check of its last commit passed, `tests` and `sandbox` included, and it changes only existing Python modules of the interface under `ike/` (and `docs/`), with no added line that reaches the environment, the network, the system or the test run, plus the version files exactly as the automation raises the version. It waits for a person when it adds or removes a file, touches a module that decides the user's safety (`app`, `config`, `passwords`, `userscripts`, `webview`, `shields`, `updater`, `doh`...), a page script under `ike/resources/`, tests, tools, workflows, the ad blocker or the package; when main's version is already published and the fix does not raise it; and when `main` already holds a fix merged by itself and not yet published (one unread merge per release). Rules: `tools/automerge.py`, read from `main` (review 2 of 1.1.19). The owner's merge is a push to `main`, which starts its tests | `automerge.yml` | One comment: ready, waiting for the owner's order; otherwise one comment naming the owner: "chiedi a Claude di revisionarla" |
| When the tests of `main` pass, and every day at 08:13 UTC | A version in `main` that is not published yet, with `tests` and `sandbox` green on its last commit | `release-ready.yml` | An issue "C'E' UNA NUOVA RELEASE IN MAIN PRONTA DA PUBBLICARE!!!" with the exact command, assigned to the owner and naming the owner (GitHub mails it), listing the fixes merged by themselves since the last release (to have them read before signing); a reminder comment each week; closed by itself once the version is published; never opened again for a version whose notice the owner closed |

## Components followed

`tools/check-components.py` checks:

| Component | Version written in | What triggers an update |
|---|---|---|
| adblock-rust, the AdBlock engine library | `ike-adblock/Cargo.toml`, `ike-adblock/src/lib.rs`, `ike-adblock/Cargo.lock` | A newer stable release on crates.io |
| The engine's other crates (pyo3, serde_json and every crate they and adblock bring, psl's list of public suffixes included; 1.1.19) | `ike-adblock/Cargo.lock`, and `ike-adblock/Cargo.toml` for a new pyo3 release line | A newer compatible version of any of them (`cargo update`, adblock kept at its exact version), or a new pyo3 line (the requirement is raised; the automatic fix may adapt I.K.E.'s wrapper, as for a new engine) |
| uBlock Origin scriptlets | `ike/resources/ubo-scriptlets.json` | The rebuilt scriptlets differ, not merely a new upstream commit |
| Dark Reader: engine (npm "darkreader") and the lists of its extension (GitHub) | `ike/resources/darkreader.js`, `darkreader-proxy.js`, `darkreader-data.json` (`tools/build-darkreader.py`) | A newer engine, or lists that changed (site fixes, dark sites, detector hints) |
| Qt WebEngine / PyQt6 of the automatic tests | `tools/test-requirements.txt` | A newer Qt / PyQt6 package set on PyPI |

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
| The new version was downloaded, but I.K.E.'s builder does not accept it: a patch's anchor is gone or found twice, the proxy or `injectProxy` is not where it was, the npm package is laid out differently, the site fixes do not start with the common fix; uBlock Origin's library moved, the builder stopped, found no scriptlets, or a scriptlet needs an entry the library does not have | **builder refused**: a component incompatibility | That component **stays at the version in use, with I.K.E.'s changes** (never replaced by the unpatched upstream). Every other component is still applied and tested (the crates' security updates included); `--apply` exits 0. The report has a section for a person. No AI: `tools/build-*` and the components' files are a person's (the automatic fix's guard refuses them). |

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

What a person does: adapt the patch (or the builder) to the new text in a
pull request, as any change of `tools/`; the next daily run then takes the
new version. Until then users keep the working, customised version.

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
of `security.yml`'s last run on `main` for the crates; everything else says
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
| candidate | the daily candidate carries it (read from the candidate's files); its tests have not run |
| testing | the candidate's checks, or `arch.yml` on `main` for an Arch package, are running |
| fixing | they failed: the automatic fix works on it |
| passed | every required check passed (it waits for the owner's merge), or it is in `main` |
| blocked | a RustSec advisory, or tried `MAX_ATTEMPTS` times |
| needs-person | a builder refused it, a workflow file (proposals only), a dependency used but not declared, the automatic fix gave up, or checks that passed but left a required category not verified |
| retry-later | a source unreachable today (tried again the next day), or a new major version `cargo update` cannot take (looked at again weekly) |

The same update is never added twice; a failed one keeps its reason and is
tried again when its time comes or when `main` changes; finished entries
leave after 30 days. A component never seen before (a new import, depend,
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

Not yet (later work packages): one candidate per component (WP5); security
findings connected to an analysis and a fix on an isolated branch (WP6);
advisories for Python, npm, Arch and the actions (WP7); the optional Arch
packages tested one by one and `arch.yml` on the candidate (WP10); the
builders' re-anchoring path and workflow proposals (WP11, WP12). The filter
lists' classification (WP8) and the free providers (WP9) are below.

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
reason, the scriptlet): `filter-list/<class>/<rule>/<detail>@finding`. The
classes go into the `components` issue below the lists' table, and each
finding becomes **one** ledger entry (the ledger remembers it while it is
reported, also after its entry left): supported and harmless ones "passed",
needs-a-person ones and those no AI may touch "needs-person", the others
queued ("detected") for an AI analysis.

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

**The AI analysis** (one at a time, the most severe first, never for a
YouTube rule or a finding of a person; a finding that waits for a free
provider holds the queue). The daily check's job `ai-work` (only `actions:
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

## The maintenance candidate

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
daily-maintenance.yml --ref <branch>`), the daily maintenance is a
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

## The owner's part

1. A notification arrives (GitHub app or e-mail) for a draft PR labelled
   `maintenance` or `autofix`.
2. Wait for the green checks. To try it, download the package of its test run
   and install it:
   `gh run download <run-id> -n ike-browser-package`.
3. Mark the PR ready and merge it on the owner's order (since 2026-11-22
   nothing merges by itself; a green fix that changes no test and no protected
   file is only marked ready). **Except:** an automatic-fix or ChatGPT
   pull request that changes anything under `tests/` is never merged on green
   checks alone. A person (or Claude, with the change read in full) reviews
   the diff of the tests first: the patch checks and "No tests lost" catch
   the usual ways of weakening a test, not every way.
4. If it raised the version: sign and publish with one command
   ([UPDATES.md](UPDATES.md)).

An issue labelled `autofix` or `automation-health` means the automation needs a
person: open a conversation and paste its link.

## Repository settings (once)

- Settings → Actions → General → Workflow permissions: keep **Read repository
  contents** (each job asks for what it needs) and tick **Allow GitHub Actions
  to create and approve pull requests** (otherwise the candidate and the fixes
  cannot open their pull requests).
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
