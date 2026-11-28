# AUTOMAT: the manual of jams

A jam is anything that stops a pull request, or AUTOMAT's daily work, for a
reason that has nothing to do with the change it carries. Written on
2026-11-25 from the jams of 2026-11-24 and 2026-11-25, at the owner's request
("AUTOMAT must learn from these simple, banal errors too").

For each jam: **the sign** (what is seen on GitHub), **the cause**, **what
was done**, **the guard** that keeps it from coming back, and **the rule** for
the next time. A jam whose guard is a test is in `tests/test_lessons.py` or
next to the code it guards.

## How to read a red pull request (in this order)

1. **Is the same failure on every open pull request at once?** Then it is
   not their fault: it is a shared step (a mirror, a runner, a workflow, a
   provider). Fix the shared step once, on its own branch, then bring the
   others up to date (jam 8).
2. **Was the run made on an old merge?** A pull request's run tests the merge
   of its branch with `main` *as it was when the run started*. "Re-run failed
   jobs" reuses that same old merge, also after `main` was fixed (jam 4).
   Bring the branch up to date instead.
3. **Does it fail only at some hours, or only in one shard?** Then it is the
   test, not the change (jams 6 and 7).
4. **Did "Nothing gets worse" fail on values that move by a few millionths?**
   Compare the branch's `ike/resources/fingerprint.js` with `main`'s: a
   branch behind `main` measures the old protection (jam 10).
5. Only then read the change itself.

## The jams

### 1. The false alarm of the fonts ("Nothing gets worse", 2026-11-24, #157)

- **Sign**: "Nothing gets worse" said the fonts got worse on a change that
  did not touch them.
- **Cause**: the comparison measured before the font check had settled, so
  `main` and the candidate were read in different states.
- **Done**: the measure is taken after the font check (#157).
- **Guard**: the order is in the check itself (the "Nothing gets worse"
  conversation keeps it).
- **Rule**: a "worse" that the change cannot explain is first a question about
  the measure, never a reason to touch the protection.

### 2. A test imported a module the test machine does not have (yaml, #155)

- **Sign**: three new tests stopped with `ModuleNotFoundError: yaml` before
  checking anything.
- **Cause**: `yaml` is not in `tools/test-requirements.txt`.
- **Done**: the tests read the workflows without a YAML library (b2ad3d7).
- **Guard**: `tests/test_lessons.py`, lesson 2: every module a test imports
  is in the standard library, the repository or the requirements.

### 3. Tests imported I.K.E. from the checkout (ROOT) instead of the copy under test (#155, #174, #176)

- **Sign**: "tests installed k/4" failed with "another copy of I.K.E. is
  imported", on tests that passed everywhere else.
- **Cause**: a test put the checkout first on `sys.path`; in the installed
  package's shards the next test of the same process found the wrong copy.
  `tools/check-components.py` then read the wrong copy too.
- **Done**: tests import from `conftest.APP`; `check-components` takes any
  other copy out of `sys.modules`, imports the given one and puts the other
  back (#174, #176).
- **Guard**: `tests/test_lessons.py`, lesson 1, and
  `tests/test_check_components_import.py`.

### 4. "Re-run failed jobs" reused the old merge

- **Sign**: a fix landed on `main`, the failed jobs of a pull request were run
  again, and they failed in exactly the same way.
- **Cause**: a `pull_request` run is tied to the merge commit made when it
  started. A re-run takes that same commit and the workflows and tools in it.
- **Done**: the pull requests were brought up to date with `main` (GitHub's
  "Update branch", `PUT /repos/{owner}/{repo}/pulls/{n}/update-branch`),
  which makes a new merge and new runs.
- **Rule**: after a fix of a shared step, update the branches, never re-run.
  An update by a person or Claude adds "Merge branch 'main' into …", which
  the verified merge accepts since 2026-11-27 exactly like its own refresh
  (`tools/automerge.py` `UPDATE_BRANCH`, `refresh_problem`: two parents, the
  second in `main`, the very tree git computes again), so the candidate still
  merges by itself. A merge GitHub resolved otherwise is refused, as before,
  and Claude merges it when green.

### 5. Arch Linux does not run on most pull requests

- **Sign**: a pull request merged green, then "Arch Linux" failed on `main`.
- **Cause**: `arch.yml` runs on pull requests only when they touch the
  package or `arch.yml` itself (it is long); it does run on every branch of
  the automation before its merge, and on every push to `main`.
- **Rule**: before merging a person's or Claude's pull request that changes
  what ships (`ike/`, `ike_boot.py`, the engine, the package), start Arch on
  its branch by hand (`gh workflow run arch.yml --ref <branch>`) and wait for
  it.

### 6. Tests that depended on the hour of the day (#166)

- **Sign**: a test of the quotas failed on `main` at 00:50 UTC only (Tests
  and Arch, shard 3), and passed again later.
- **Cause**: the test put every provider on the repository's UTC day, while
  each provider has its own day (Gemini resets at midnight Pacific time).
- **Done**: the test uses `quota.provider_day`, as the tool does.
- **Rule**: a test of time never reads the clock: it passes a fixed `now`,
  and walks the hours that matter (just before and after each provider's
  reset).

### 7. The order of the tests in the shards (#173, #174)

- **Sign**: "tests installed 2/4" failed after a pull request only *added* a
  test file.
- **Cause**: the shard plan balances whole files by their durations; a new
  file moved `test_lists_providers` next to a test that left the checkout
  imported (jam 3). The bug was old; the new order showed it.
- **Rule**: a failure that appears when files move between shards is a test
  that leaves something behind (an import, an environment variable, a file).
  Find the test that ran before it in that shard (the shard's junit file
  lists the order) and fix that one.

### 8. An Arch mirror lost a file of the day's snapshot (zxing-cpp .sig 404, #177)

- **Sign**: every Arch run of every open candidate (#154, #169, #170, #171)
  failed the same way: `failed retrieving file
  'zxing-cpp-3.1.1-1-x86_64.pkg.tar.zst.sig' … 404`, then `failed to commit
  transaction`.
- **Cause**: the runs use one day's snapshot; the mirrors listed first had
  already dropped that version's signature, and pacman stopped instead of
  asking the archive.
- **Done**: the package steps retry once with only the snapshot's Arch Linux
  Archive server, which keeps every version, with a warning (#177).
- **Guard**: `tests/test_shards.py`.
- **Rule**: jam 1 of "How to read": the same failure everywhere is the shared
  step's.

### 9. The free AI providers stalled (#173, #179)

- **Sign**: PR #111 was "retrying" for days, and the "Automatic fix" runs
  said "Reserves: none" or asked nobody.
- **Cause, first stall (#173)**: each provider was skipped for a reason of its
  own: a 429 of concurrency read as the day's quota, the reviewers' reserve,
  a request larger than Groq's minute.
- **Cause, second stall (#179, run 45625320020)**: a wrong "spent today" mark
  of Z.AI, written before #173, stayed for the rest of the day; OpenRouter's
  free models answered 429 because their pool at the upstream provider was
  busy, and the run waited 61 s on each as if the whole account were blocked;
  the reasoning models used all their room for reasoning and gave no text.
  It was not OpenRouter's privacy setting (that is a 404 "No endpoints found
  matching your data policy", reported plainly when it happens).
- **Done**: see docs/MAINTENANCE.md, "No deadlock of the free quotas". A
  "spent today" mark is checked again after three hours; a busy free model
  hands over to the next at once; the provider's own words are in the log.
- **Guard**: `tests/test_automat_deadlock.py`,
  `tests/test_automat_stall_1125.py`; the watchdog (`stuck_text`) says a
  branch that asked nobody for two days.

### 10. A candidate behind `main` measured the old protection ("Nothing gets worse", #171)

- **Sign**: "Nothing gets worse" found 6 rows worse (canvas, fonts, frame at
  Strict and Maximum) on a Dark Reader update that does not touch the
  fingerprint protection.
- **Cause**: the branch was made before #175 changed the width noise; `main`
  had it, the branch did not, so the two measured different protections.
- **Rule**: bring the branch up to date (jam 4), never add allowlist entries
  for it.

### 11. The Arch archive was too slow for every part at once (main 65bb121, #186)

- **Sign**: every Arch part failed on `main` after #177: a mirror had dropped a
  file (404), the fallback asked the archive alone, and the archive "sent
  nothing for 10 s" ("Operation too slow"), then pacman skipped it.
- **Cause**: ten parts asked the archive at once, five files each.
- **Done**: the archive first and the mirrors after it, one file at a time, with
  no limit of slowness, three tries after 30, 120 and 300 s; never another
  database, so every part still tests the same packages (#186).
- **Guard**: `tests/test_shards.py`.

### 12. The free models spent their whole answer on reasoning (run 45983654916, #187)

- **Sign**: after #179 the models were asked, but the log said `cutoff` for
  almost every one.
- **Cause**: reasoning models count their reasoning in the answer's room.
- **Done**: each provider is asked for little reasoning with its own parameter,
  and a model cut off is asked again with its reasoning off (#187).
- **Guard**: `tests/test_automat_reasoning_cutoff.py`.

### 13. An impossible task given to the AIs for five days (PR #111, #190)

- **Sign**: a pull request "retrying" for days; the free models' fix was a
  helper nothing called and a function put inside a class; the guard refused it.
- **Cause**: the finding (an AdBlock engine limit: `csp=` with `$doc`) could not
  be fixed in I.K.E.'s adapter, and I.K.E. applies no `$csp` rule at all; the
  AIs had only the engine's error.
- **Done**: engine limits are no longer given to an AI (`ENGINE_LIMITS`); the AIs
  get AUTOMAT's playbook (`tools/automat-playbook.py`); a test guards the class
  the fix broke; #111 closed at the owner's order (#190).
- **Rule**: before giving a task to the AIs, ask "can this be fixed in the files
  they may change?" If not, it is Claude's work, recorded as a gap.

### 14. A test that failed only in CI hid a real defect (test_handoff, #201, #206, 2026-11-27)

- **Sign**: `test_handoffs_are_shown_only_when_the_desktop_has_the_app` failed
  in "tests shard 4/4" on every run of main after 1.1.28's merge, never
  locally; a missing file changed from run to run. It blocked the signature
  (`tools/publish.py` needs main's tests green).
- **Cause**: longer waits did not help. What helped was making the test say
  everything: the engine's own answer for each download (#206). It showed that
  one hand-off download (the image already shown in the page) started and
  never finished: "Open image in…" could do nothing for a user too.
- **Rule**: when a test fails only sometimes, first make its failure message
  complete (what the program and the engine said), then fix the cause. A
  longer wait is never the fix; re-running is only a stop-gap.

### 15. The tests ran again after AUTOMAT's own attempt (the drill, 2026-11-27)

- **Sign**: after "autofix: attempt 1" (a recipe fixed one of six breaks) the
  tests failed on the five left, and the plan chose "rerun" (the rule for a
  test that fails only sometimes): a round of 40 minutes lost per attempt.
- **Done**: a failing commit that the automatic fix itself wrote goes to the
  next attempt at once (`tools/autofix-plan.py`, `own_attempt`).

### 16. A failure of main fixed by a person kept the drill paused (2026-11-27)

- **Sign**: the drill's second attempt asked nobody: "paused for real updates
  first: ... pending (automation/autofix-main)".
- **Cause**: main's tests had failed that evening (a flaky test); the automatic
  fix opened a row for `automation/autofix-main`; a person's pull request then
  fixed main, so no automatic fix ever ended the row.
- **Done**: that row ends when main's newest finished Tests run passed after it
  (`tools/ai-quota.py` `main_green_since`), whoever fixed main.

### 17. A fix in conflict with main got no tests at all (the drill, 2026-11-28, PR #208)

- **Sign**: after "autofix: attempt 1" the drill's pull request showed only "ChatGPT fix guard" (skipped);
  no Tests, Security or Arch run started, and nothing happened for an hour.
- **Cause**: the fix's commit adds a CHANGELOG line (main's version was published); main's CHANGELOG had
  changed at the top (1.1.31's notes), so the pull request conflicted with main. GitHub starts no
  `pull_request` run on a pull request in conflict, and the verified merge refreshed a candidate only once
  it was fully verified: nothing would ever judge it.
- **Done**: the automatic fix asks the verified merge at once after its push (`automerge.yml`, `sha`); a
  pull request of the automation in conflict with main is refreshed first, verified or not
  (`tools/automerge.py` `conflicts_with_main`), and its tests start on the refreshed commit.
- **Guard**: `tests/test_merge_and_mail.py`,
  `test_a_candidate_in_conflict_with_main_is_refreshed_before_any_check`.
- **Rule**: a pull request with no checks on its last commit is first a question about GitHub's
  mergeability, never a reason to re-run.

### 18. The reserves could never fix a large file (the drill, 2026-11-28, #231)

- **Sign**: "answer not usable: ike/window.py is not one of the files shown", attempt after attempt.
- **Cause**: the reserves get whole files up to 60 000 characters; `ike/window.py` (175 KB) never fits, and
  an edit was accepted only in a file shown whole, although the code at the failure was in the excerpt.
- **Done**: a file whose excerpt at the failure is shown may be edited too (`editable_files`); the text to
  replace must still appear exactly once, the checks after it are the same.
- **Guard**: `tests/test_reserve_excerpt_edits.py`.

### 19. A limit of one model's answers stopped a whole provider (Groq, 2026-11-28, #234)

- **Sign**: "Groq: not asked: even the smallest request ... is larger than its limit per minute (1000 tokens)".
- **Cause**: one model's 429 said "output tokens per minute (OTPM): Limit 1000"; it was learned as Groq's
  limit of tokens a minute and kept for the next days, and since no request fitted it, Groq was never asked
  again, so its headers could not correct it.
- **Done**: an output limit is not learned; the headers' readings come before a learned value.
- **Guard**: `tests/test_groq_output_limit.py`.
- **Rule**: a learned limit that makes a provider unaskable must be one that a later answer can correct.

### 20. Gemini's agent never ran in the closed room (2026-11-25 to 2026-11-28)

- **Sign**: "Agent stopped: temporary" for every Gemini model (2026-11-25), "Agent stopped: timeout" after 8
  minutes (2026-11-28), and each time "Ricerche di nomi (DNS) dell'agente bloccate: ~150".
- **Cause**: the Antigravity CLI looks up names besides the Gemini API (pinned in /etc/hosts); the closed room
  refuses every lookup, so the CLI never reached its work. Gemini had made no fix at all.
- **Done**: the CLI is not started (only with `AUTOFIX_AGENT_CLI=on`); Gemini is asked through its own API by
  the reserves' step (the host the reviewers already use), under Antigravity's name and quota, with a budget
  that holds whole large files (`tools/autofix-reserve.py` `chain`, `tools/ai-providers.py` `GEMINI_OPENAI`).
- **Guard**: `tests/test_gemini_api_first.py`.
- **Rule**: a provider that never produced an answer is first a question about whether it can run at all.

## Prepared responses (what Claude does, in order)

| Situation | First step | Never |
|---|---|---|
| All candidates red on the same step | fix the step on its own branch, merge it, update the candidates | re-run, or change the candidates |
| One candidate red after `main` moved | update its branch | re-run its failed jobs |
| A test red at one hour or in one shard | fix the test (fixed clock, nothing left behind) | mark it flaky and move on |
| "Nothing gets worse" red on a change that cannot cause it | compare the protection files with `main`, then the measure | allowlist the values |
| The same kind of failure comes back to the AIs every day with no fix | check that it can be fixed in the files they may change; if not, take it from them (`ENGINE_LIMITS`, the playbook) | let it retry for days |
| AI work asked nobody | read the "fix" job's "Reserve:" lines; the provider's own words are there | turn on a paid plan or change a privacy setting (the owner's decision) |
