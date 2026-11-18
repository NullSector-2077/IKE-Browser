# Automatic maintenance

GitHub Actions keeps I.K.E. up to date and prepares the fixes. The owner only
**approves** (merges a pull request) and **signs and publishes** (one command on
the owner's computer, [UPDATES.md](UPDATES.md)). Nothing is merged, released or
signed automatically, and no workflow ever writes to `main`.

## What runs by itself

| When | What | Workflow | Result |
|---|---|---|---|
| Every day, 05:17 UTC | Upstream versions of the bundled components | `daily-check.yml` | Issue labelled `components` |
| Every day, 06:17 UTC | The updates applied to a candidate built from current `main` | `daily-maintenance.yml` | Branch `automation/daily-maintenance`, draft PR labelled `maintenance` |
| On every PR, every push to `main`, every candidate or fix | Lint, all the tests, the Arch package and its tests | `tests.yml` | Checks on the PR, package download `ike-browser-package` |
| When one of the three above fails | An automatic fix | `autofix.yml` | Draft PR labelled `autofix`, or an issue "Automatic fix needs you" |
| Mondays, 07:41 UTC | The automation itself | `health.yml` | Issue "Automation health" when something stopped |
| Once a month | New versions of the GitHub actions used | Dependabot | One PR labelled `maintenance` |

## Components followed

`tools/check-components.py` checks:

| Component | Version written in | What triggers an update |
|---|---|---|
| adblock-rust, the AdBlock engine library | `ike-adblock/Cargo.toml`, `ike-adblock/src/lib.rs`, `ike-adblock/Cargo.lock` | A newer stable release on crates.io |
| uBlock Origin scriptlets | `ike/resources/ubo-scriptlets.json` | The rebuilt scriptlets differ, not merely a new upstream commit |
| Dark Reader: engine (npm "darkreader") and the lists of its extension (GitHub) | `ike/resources/darkreader.js`, `darkreader-proxy.js`, `darkreader-data.json` (`tools/build-darkreader.py`) | A newer engine, or lists that changed (site fixes, dark sites, detector hints) |
| Qt WebEngine / PyQt6 of the automatic tests | `tools/test-requirements.txt` | A newer Qt / PyQt6 package set on PyPI |

The browser itself runs on Arch Linux's `qt6-webengine`, updated with the
system (`sudo pacman -Syu`). Filter lists, the presented Chrome version and user
scripts update themselves inside the browser.

## The maintenance candidate

1. `daily-maintenance.yml` starts `automation/daily-maintenance` from the
   current `main` every time and applies the component updates
   (`--apply`; if any upstream source cannot be checked, nothing is applied).
2. `tools/prepare-maintenance.py` raises the patch version (1.1.10 → 1.1.11, or
   adds to a version of `main` that is not released yet), the package version,
   README and CHANGELOG. A new AdBlock engine travels in the signed
   self-update (1.1.12), so it never needs a new package. **Packages used only by the tests make no new version**: that pull
   request is merged and needs no release.
3. Automatic fixes of the previous candidate (commits `autofix: ...`) are carried
   over. The candidate is pushed only when it differs from the one already
   published, and the tests are started on it.

## The automatic fix

`autofix.yml` starts when `Tests` fails on `main`, on the maintenance candidate
or on the fix branch, or when the daily check or the daily maintenance fail.
Failures of forks, of people's pull requests and of the standby branches are
never touched.

1. **plan** (no AI, `tools/autofix-plan.py`): what failed, where the fix goes,
   the end of the logs. A setting or workflow problem becomes an issue directly.
2. **fix** (`tools/autofix-agent.py`, read from `main`): the Antigravity CLI
   (`agy`) runs the instructions of `.github/autofix/prompt.md`, also from
   `main`, in a closed room:
   - its own user, a copy of the repository, only `HOME`, `PATH` and the API
     key in its environment, and **no GitHub credentials** (read-only job, no
     token): it can only leave a patch and a summary in Italian;
   - no terminal, no web, no MCP (its own permission rules), and a firewall
     that lets its user reach only the Gemini API;
   - real limits: at most 8 minutes per model and 25 minutes in all. The free
     plan gives each model about 20 requests a day and every step uses one, so
     it is told to take about 10 steps and to run no tests (GitHub runs them).
   Model after model (`AUTOFIX_MODEL`, then Gemini 3.8, 3.7, 3.6 Flash): only
   when a model's daily quota is used up (or Google is down) does the next one
   go on, with the work already done. A per-minute limit is waited out once; a
   wrong key or model name stops at once, since another model would not help.
   The agent's output is never printed, the key is hidden in its errors, and a
   result containing the key is thrown away. A second attempt receives the
   first fix, the new test logs and the first summary, and corrects only that.
3. **guard** (no AI, `tools/check-autofix-patch.py` from `main`): the patch may
   change only `ike/`, `tests/`, `tools/` and `docs/`; never the workflows, the
   signing and update channel, the version, the package recipe, the updater, the
   test harness or the release tools; the ad blocker only on a candidate that
   updates its engine; no test removed or weakened; no keys, binaries or links;
   at most 5 files and 150 lines. Then lint. A fix of `main` that changes the
   browser gets the next version and a CHANGELOG line.
4. **publish** (no AI): the fix goes to `automation/autofix-main` (fixes of
   `main`) or onto the maintenance candidate, a draft PR is opened or updated
   with the agent's summary, and the tests start on it.
5. If the tests fail again, a second attempt follows. After two, or when nothing
   could be fixed, the issue **"Automatic fix needs you: <workflow>"** is opened. Its
   reason is plain: quota, chiave, modello, tempo or rifiutata.

The agent cannot see Plasma: shapes, effects and the look are always judged by
the owner on the real system.

## The owner's part

1. A notification arrives (GitHub app or e-mail) for a draft PR labelled
   `maintenance` or `autofix`.
2. Wait for the green checks. To try it, download the package of its test run
   and install it:
   `gh run download <run-id> -n ike-browser-package`.
3. Mark the PR ready and merge it.
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
- Settings → Branches: protect `main` (pull request required, status check
  `tests` required, no force push, no deletion).

If the key leaks (it would show only through the agent), delete it in Google AI
Studio and create a new one: it can spend nothing and opens nothing else.
