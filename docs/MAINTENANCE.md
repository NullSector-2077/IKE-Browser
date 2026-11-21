# Automatic maintenance

GitHub Actions keeps I.K.E. up to date and prepares the fixes. A pull request
is merged only once its tests are green: since 1.1.19 a fix of the automatic
fix or of ChatGPT that changes no test and no protected file goes into `main`
by itself (`automerge.yml`, below); everything else is merged by the owner or
by Claude working in a session for the owner (CLAUDE.md). The owner alone
**signs and publishes** (one command on the owner's computer, in the issue
GitHub mails when a release is ready, [UPDATES.md](UPDATES.md)). No workflow releases or
signs anything, and no workflow pushes to `main`.

## What runs by itself

| When | What | Workflow | Result |
|---|---|---|---|
| Every day, 05:17 UTC | Upstream versions of the bundled components | `daily-check.yml` | Issue labelled `components` |
| Every day, 06:17 UTC | The updates applied to a candidate built from current `main` | `daily-maintenance.yml` | Branch `automation/daily-maintenance`, draft PR labelled `maintenance` |
| On every PR, every push to `main`, every candidate or fix | Lint, all the tests, the Arch package and its tests | `tests.yml` | Checks on the PR, package download `ike-browser-package` |
| When one of the three above fails | An automatic fix | `autofix.yml` | Draft PR labelled `autofix`, or an issue "ATTENZIONE E' RICHIESTO IL TUO INTERVENTO PER FARE INTERVENIRE CHAT GPT NELL' AUTOFIX!!! (<workflow>)" assigned to the owner, which GitHub mails |
| Mondays, 03:41 UTC | The whole suite and the package on Arch Linux's own Qt (`archlinux:latest`) | `arch.yml` | A failed run to look at (not a required check, no automatic fix) |
| Every day, 04:23 UTC, and on every PR and push to `main` | The security tests with the engine's sandbox really on (as a normal user), and the RustSec advisories of every crate of the AdBlock engine | `security.yml` | Checks on the PR; on `main` the issue "Rust advisories" when one is found (no automatic fix) |
| Mondays, 07:41 UTC | The automation itself: every scheduled check (also the Arch and security ones, 1.1.19), and one tiny question to each reserve of the automatic fix | `health.yml` | Issue "Automation health" when something stopped, failed, waits too long, or a reserve's key or model no longer works |
| Once a month | New versions of the GitHub actions used | Dependabot | One PR labelled `maintenance` |
| When a check of a pull request ends | A fix of the automatic fix (`automation/autofix-main`) or of ChatGPT (`chatgpt/...`) goes into `main` when every check of its last commit passed, it changes no test, no protected file (the checker's lists), no workflow, the ad blocker or the package, the version files only as the automation raises the version, and none of its commits is an autofix trial (`tools/automerge.py`, read from `main`); then the tests of `main` start | `automerge.yml` | The merge and a comment; anything else waits for a person |
| When the tests of `main` pass, and every day at 08:13 UTC | A version in `main` that is not published yet | `release-ready.yml` | An issue "C'E' UNA NUOVA RELEASE IN MAIN PRONTA DA PUBBLICARE!!!" with the exact command, assigned to the owner and naming the owner (GitHub mails it); a reminder comment each week; closed by itself once the version is published |

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

## The automatic fix

`autofix.yml` starts when `Tests` fails on `main`, on the maintenance candidate
or on the fix branch, or when the daily check or the daily maintenance fail.
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
   its own words and without a message for ChatGPT. Its title is not the one
   the plan reads, so it never holds back the fix of a real failure. The log
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
the first 100 comments of an issue and never closes a report when its failure
is gone (L2); ruff and pytest are not pinned, and the reserves' lint runs in
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
4. Never merged by itself: the draft pull request waits for a person. After a
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
3. Mark the PR ready and merge it (a green fix of the automatic fix or of
   ChatGPT that changes no test and no protected file is merged by itself
   since 1.1.19). **Except:** an automatic-fix or ChatGPT
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
- Autofix trials (deliberate errors on `automation/autofix-main`) must keep
  "Autofix trial" at the start of their commit message: `automerge.py` never
  merges a pull request that has such a commit.

The weekly check (`health.yml`, `tools/automation-health.py`) reports, since
1.1.18, a `main` without branch protection (the `protected` field of the
branch in GitHub's API) and the reserves' secrets missing, besides runs of the
automatic fix that failed in the last 7 days and autofix issues or maintenance
pull requests open for more than 7 days. Since 1.1.19 it also watches
`security.yml` (two failed scheduled runs in a row, or none for 3 days) and
`arch.yml` (its last scheduled run failed, or none for 9 days), and asks each
reserve that has a key one tiny question (`tools/autofix-reserve.py ping`):
a refused key or an unknown model is reported, a quota or a passing error is
not.

If the key leaks (it would show only through the agent), delete it in Google AI
Studio and create a new one: it can spend nothing and opens nothing else.
