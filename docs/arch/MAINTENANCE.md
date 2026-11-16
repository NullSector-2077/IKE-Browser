# Automatic component maintenance

The daily maintenance candidate is prepared by GitHub Actions. Claude is not
part of the scheduled process and has no repository task to run.

## What runs every day

| Step | Who | Where |
|---|---|---|
| Check upstream component versions | GitHub Actions, `.github/workflows/daily-check.yml` | Issue labelled `components` and a 14-day report artifact |
| Apply eligible updates on an isolated branch | GitHub Actions, `.github/workflows/daily-maintenance.yml` | `automation/daily-maintenance` |
| Build and test the candidate | GitHub Actions | Linux source tests, Windows source tests, Arch package, AppImage, Windows installer and installed-copy tests |
| Inspect results and code | Project owner and ChatGPT, when the owner asks | Draft PR labelled `maintenance` |
| Approve and merge to `main` | Project owner, after review with ChatGPT | The maintenance PR |
| Sign and publish the release | Project owner, on the owner's computer | `docs/UPDATES.md` |

The daily workflow never writes to `main`, never merges a PR, never creates a
GitHub release, and never reads or receives the private Ed25519 signing key.
The maintenance PR remains a draft until the owner and ChatGPT have reviewed
the code, all test results and the candidate artifacts.

## Components followed

`tools/check-components.py` checks:

| Component | Version written in | What triggers an update |
|---|---|---|
| adblock-rust, the AdBlock engine library | `ike-adblock/Cargo.toml`, `ike-adblock/src/lib.rs`, `ike-adblock/Cargo.lock` | A newer stable release on crates.io |
| uBlock Origin scriptlets | `ike/resources/ubo-scriptlets.json` | The rebuilt scriptlets differ, not merely a new upstream commit |
| Qt WebEngine / PyQt6 bundled in AppImage and Windows | `tools/appimage-requirements.txt` | A newer compatible Qt/PyQt6 package set |
| Standalone Python bundled in AppImage and Windows | `tools/build-appimage.sh`, `tools/build-windows.ps1` | A newer Python patch release from python-build-standalone |

Other AppImage packages (cryptography, certifi, and their dependencies) and
new builds of the same Python are reported as informational. They are carried
along only when an actionable component update is being prepared.

On Arch / CachyOS, Qt WebEngine is supplied by the system and is updated with
the system (`pacman -Syu`); it is not bundled or independently pinned by ICE.
Filter lists, the presented Chrome version and user scripts update themselves
inside the browser. Dark Reader is not part of this component updater.
Windows-only media-control packages in `tools/windows-requirements.txt`
remain manually maintained and are covered by the Windows tests.

## Daily candidate workflow

1. At 05:17 UTC, `daily-check.yml` checks the upstream sources and updates the
   `components` issue.
2. At 06:17 UTC, `daily-maintenance.yml` checks out the persistent branch
   `automation/daily-maintenance`, or recreates it from `main` if it was
   deleted. It first incorporates the latest `main`.
3. The component checker runs with `--apply`. If any upstream source cannot be
   checked, it exits unsuccessfully and applies no updates. Informational
   rebuilds alone do not create a release candidate.
4. If there are no actionable changes, the workflow stops without a commit or
   a PR. Otherwise it updates the patch version, the Arch package version,
   README and CHANGELOG, and raises `__min_system__` when the AdBlock system
   module changes.
5. It commits only the component/version files to the maintenance branch and
   creates or updates one draft PR against `main`.
6. GitHub Actions first runs the Linux and Windows source suites and builds
   and tests the Windows installer and installed copy. Only after all of those
   checks pass does it build and test the Arch package and AppImage. Candidate
   packages are retained as workflow artifacts for 30 days.
7. Any failed check leaves the PR in draft and blocks promotion. A successful
   run means the candidate passed the automated checks; it does not mean the
   update has been approved or published.

The component checker intentionally fails closed: if even one upstream
source cannot be queried, no component updates are applied. A failed source,
test, build or package check must be investigated before the candidate is
promoted. GitHub Actions cannot adapt ICE's source code to an incompatible
upstream API on its own; the owner asks ChatGPT to inspect the logs and prepare
a separate fix when needed.

## Review rules

- Never push to `main` from the maintenance workflow.
- Never merge without the owner's explicit decision.
- Never publish a release from GitHub Actions.
- Never place the private signing key in the repository, a package, an Actions
  secret or a runner.
- Change only what the component update requires. No unrelated features,
  clean-ups or settings changes.
- Do not skip or weaken tests to make a candidate green.
- Keep one maintenance PR at a time. New eligible updates go into the same
  persistent branch and PR.
- A green CI result is necessary, not sufficient: inspect the diff, changelog,
  dependency compatibility, test coverage and package artifacts before merge.
- If an upstream API change needs code adaptation, stop the automated process.
  ChatGPT investigates and prepares a fix on a separate branch/commit; Claude
  remains in standby unless the owner later asks for it.

## Daily owner review

The owner can ask ChatGPT:

> Controlliamo IKE Browser: verifica il branch di manutenzione, la PR, gli
> aggiornamenti, i log di GitHub Actions e gli artefatti.

ChatGPT reviews the actual commit and run results, explains any failures in
Italian and, when appropriate, prepares a bounded correction on a separate
branch. The owner remains responsible for deciding when to merge and publish.

## Release after approval

Only after the owner and ChatGPT agree that the candidate is correct:

1. Ensure the maintenance branch is current with `main`; rerun tests and
   rebuild artifacts if the base commit changed.
2. The owner approves and merges the PR into `main`.
3. Download the Linux package/AppImage artifacts and the Windows artifacts
   from the successful workflow runs.
4. Follow the signing and publishing instructions in `docs/UPDATES.md`.
   The private key stays at `~/.ice-signing/ice-update.key` on the owner's PC.
5. Verify the published release assets and signed `stable.json`.

The exact commands and paths must be supplied for the actual version and run
IDs; never guess a run ID or artifact filename.
