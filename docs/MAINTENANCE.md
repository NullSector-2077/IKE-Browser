# Automatic component maintenance

The components bundled in I.K.E. are checked every day by GitHub Actions. When
one has a new version, a tested candidate release is prepared on its own branch
for the owner to review. Nothing is merged, released or signed automatically.

## What runs every day

| Step | Who | Where |
|---|---|---|
| Check upstream component versions | GitHub Actions, `.github/workflows/daily-check.yml` (05:17 UTC) | Issue labelled `components` and a 14-day report artifact |
| Apply the updates on an isolated branch | GitHub Actions, `.github/workflows/daily-maintenance.yml` (06:17 UTC) | Branch `automation/daily-maintenance` |
| Lint, tests, Arch package and tests of the installed package | GitHub Actions, `.github/workflows/tests.yml` called on the candidate | The run's checks and the `ike-browser-package` download |
| Review and merge to `main` | The project owner | The draft pull request labelled `maintenance` |
| Sign and publish the release | The project owner, on the owner's computer | [UPDATES.md](UPDATES.md) |

The workflows never write to `main`, never merge a pull request, never create
a GitHub release, and never read or receive the private signing key.

## Components followed

`tools/check-components.py` checks:

| Component | Version written in | What triggers an update |
|---|---|---|
| adblock-rust, the AdBlock engine library | `ike-adblock/Cargo.toml`, `ike-adblock/src/lib.rs`, `ike-adblock/Cargo.lock` | A newer stable release on crates.io |
| uBlock Origin scriptlets | `ike/resources/ubo-scriptlets.json` | The rebuilt scriptlets differ, not merely a new upstream commit |
| Qt WebEngine / PyQt6 of the automatic tests | `tools/test-requirements.txt` | A newer Qt / PyQt6 package set on PyPI |

The browser itself runs on Arch Linux's `qt6-webengine`, updated with the
system (`sudo pacman -Syu`); the report shows its current version next to the
one the tests use. Other test packages (cryptography, certifi and their
dependencies) are reported as informational and carried along only with an
actionable update. Filter lists, the presented Chrome version and user scripts
update themselves inside the browser.

## Known vulnerabilities

The same daily check runs `tools/audit-deps.py`: `cargo audit` (RustSec) on the
engine module's `Cargo.lock`, and `pip-audit` (PyPI / OSV advisories) on the
pinned Python packages of the tests and, once it exists, of the Windows build.
On Linux the browser runs on the distribution's own Qt and Python, which the
distribution's security team follows; those are covered by the weekly
"Linux distributions" workflow, which tests I.K.E. on each distribution's
current packages. A known vulnerability, or an audit that could not run, keeps
the "components" issue open with the details. Nothing is updated
automatically for it: stability and security come before taking every new
version; the owner decides, and the fix goes through a candidate branch like
any other update.

## The candidate

1. `daily-maintenance.yml` checks out `automation/daily-maintenance` (or
   creates it from `main`) and brings in the latest `main`.
2. The component checker runs with `--apply`. If any upstream source cannot be
   checked, nothing is applied.
3. Without actionable changes the workflow stops. Otherwise
   `tools/prepare-maintenance.py` raises the patch version (1.0.0 → 1.0.1),
   the package version, README and CHANGELOG, and raises `__min_system__` when
   the AdBlock engine module changes (an installed system part: such a release
   reaches users as a new package, not as a self-update).
4. The changed files are committed to the branch and one draft pull request
   against `main` is created or updated.
5. `tests.yml` runs on the branch: lint, the full test suite, the Arch package
   built with `makepkg`, and the full suite again against the installed
   package. The package is kept as the run's `ike-browser-package` download.

## The owner's part

1. Open the draft pull request labelled `maintenance` and check that all the
   checks are green.
2. Optionally download the package from the run and try it:
   `gh run download <run-id> -n ike-browser-package`.
3. Mark the pull request ready and merge it.
4. Sign and publish the release from an up-to-date clone, as in
   [UPDATES.md](UPDATES.md).

If a component update needs changes to I.K.E.'s own code, the tests fail and
the pull request stays a draft: the adaptation is done by hand on that branch.

## Repository settings

### Required checks before merging

So that a pull request with a failing test cannot be merged, GitHub must be
told which checks are required. Once the workflows have run on `main` at
least once (after the pull requests that add them are merged):

1. GitHub → the repository → **Settings** → **Rules** → **Rulesets** →
   **New ruleset** → **New branch ruleset**.
2. Name: `main`. Enforcement status: **Active**. Target branches: **Add
   target** → **Include default branch**.
3. Tick **Require a pull request before merging** (no approvals needed: the
   owner is the only reviewer) and **Require status checks to pass**.
4. Under the status checks, **Add checks** and pick each of: `tests`
   (Tests), `Arch Linux`, `Ubuntu 26.04`, `Debian 13`, `Fedora 43` (Linux
   distributions), `DEB - Ubuntu 26.04`, `DEB - Debian 13`, `RPM - Fedora 43`
   (Linux packages), and the Flatpak and Windows checks once those
   workflows are on `main`.
5. **Create**.

From then on the merge button stays grey until every required check is
green; a failed run keeps its logs and downloads (test results, engine
report, packages) on the run's page for 30 days.

The maintenance workflow opens pull requests with the workflow's own token.
In the repository's Settings → Actions → General, "Workflow permissions" must
allow GitHub Actions to create pull requests.
