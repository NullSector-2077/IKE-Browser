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

## Prepared responses (what Claude does, in order)

| Situation | First step | Never |
|---|---|---|
| All candidates red on the same step | fix the step on its own branch, merge it, update the candidates | re-run, or change the candidates |
| One candidate red after `main` moved | update its branch | re-run its failed jobs |
| A test red at one hour or in one shard | fix the test (fixed clock, nothing left behind) | mark it flaky and move on |
| "Nothing gets worse" red on a change that cannot cause it | compare the protection files with `main`, then the measure | allowlist the values |
| The same kind of failure comes back to the AIs every day with no fix | check that it can be fixed in the files they may change; if not, take it from them (`ENGINE_LIMITS`, the playbook) | let it retry for days |
| AI work asked nobody | read the "fix" job's "Reserve:" lines; the provider's own words are there | turn on a paid plan or change a privacy setting (the owner's decision) |
