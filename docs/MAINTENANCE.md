# Automatic maintenance

GitHub Actions keeps I.K.E. up to date and prepares the fixes. Since
2026-11-22 (the owner's decisions) no AI agent merges into `main` and no agent
merges its own work. The automation's own pull requests (a candidate per
component, an automatic fix, a security fix, a builder's re-anchoring) are
merged by the workflow's own code read from `main` only when they are **fully
verified** ("The verified merge", below). Since AUTOMAT (the owner's name for
this whole system, and the owner's third decision of 2026-11-22: see "AUTOMAT:
the full automation") anything less is tried again by itself, never left for
a person and never closed; the owner's only step is the signature. Claude merges the pull requests the owner asked
for once every check is green; ChatGPT's and people's pull requests wait for
the owner's order (CLAUDE.md; a verified ChatGPT fix is adopted by AUTOMAT
only when the owner turned the switch `AUTOMAT_CHATGPT_AUTOMERGE` on: "AUTOMAT,
part 2"). The owner alone **signs and publishes** (one
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
   installed package, for a new engine the default filter lists in that
   engine against `main`'s, and "Nothing gets worse": blocking,
   fingerprinting surface, network and security settings measured against
   `main`'s, below), `security.yml` (the sandbox, the RustSec
   advisories) and `arch.yml` (Arch Linux's own packages) on its commit.
5. **Fixed by an AI when they fail, on that branch only.** `autofix.yml`
   fixes the candidate's own branch under the guard
   (`tools/check-autofix-patch.py`), a fresh run per attempt starting with the
   next free provider, up to `FIX_ATTEMPTS` (`tools/ai-providers.py`), the
   tests again after each. On a candidate of the engine (adblock, pyo3, a
   major crate) the AI may adapt I.K.E.'s wrapper; on a builder's branch it may
   only re-anchor I.K.E.'s existing patches. An AI never edits a workflow: what
   it wanted there is a written proposal for a person. The cap is per day:
   when today's attempts are used up the branch stays open, the ledger says
   "retrying" and the next day it goes on (AUTOMAT).
6. **Merged by itself** when everything is green and verified
   (`tools/automerge.py`, `automerge.yml`, read from `main`). Several
   candidates go into the same unpublished version; one that is behind
   `main` is refreshed first (`main` merged into its branch, its tests
   again), and after every merge the others are judged again, so they all
   converge into `main` one after another ("The verified merge", below).
7. **The owner signs.** `release-ready.yml` mails the owner the command that
   signs and publishes the new version; every user then gets it by itself.

## AUTOMAT: the full automation

**AUTOMAT** is the owner's name for the whole automatic maintenance described
in this document. The owner's decisions of 2026-11-22, in the owner's words:
"intervento umano limitato solo alla firma. ike deve cercarsi gli
aggiornamenti installarli testarli e correggerli da solo su github. 100%
lavoro in team di ia", and "niente annullamenti automatici, l'automazione deve
essere in grado di riparare tutto, anche se comporta molti tentativi... niente
deve rimanere indietro". So: every update and every AI fix reaches `main` by
itself when it is verified; what is not verified yet stays open and is tried
again; the owner only signs, and the signing notice says what the signature
covers. Where an older paragraph below still says "waits for a person" or
"needs-person", this section is the rule.

**Two tiers** (`tools/fix-guard.py`, `tier()`):

| Tier | Files | An AI |
|---|---|---|
| B | the workflows (`.github/`), the tests, every tool (`tools/`: the guard, the merge, the reviewers, the plan, "Nothing gets worse"), the engine's sandbox and start (`ike/app.py`, `ike_boot.py`, `launcher/`), the signing and update channel (`ike/updater.py`, `ike/__init__.py`, `ike/extensions.py`), the package recipe, what comes from others or is generated (Dark Reader, uBlock Origin's scriptlets, the icon sets, the Cargo files, `vendor/`), YouTube's ad blocking (`videoads.js`, `videorelay.js`, `mediahook.js`, `Scriptlets.host_scripts`), and any file the guard does not know | never changes them. An update that needs one stays open as "retrying" with a note; the deterministic tools (the CI pins, the builders' re-anchoring rule) keep their own paths. Only with the owner's switch `AUTOMAT_TIER_B` a few of these files open in their narrowest form ("Tier B, behind the owner's switch", below) |
| A | I.K.E.'s ad-blocking adapter (`ike/blocker.py`, `ike/scriptlets.py`, `ike-adblock/src/*.rs`, `vendor/adblock/__init__.py`), the modules that decide the user's safety (`PROTECTED_PY`: shields, passwords, webview, config, DoH...), I.K.E.'s own page scripts (`fingerprint.js` and the others), the look-alike table, a new entry of `components.json` | may fix them; the fix merges by itself only with everything below |
| (none) | the other interface modules under `ike/` and `docs/` | as before (the 1.1.19 rules) |

**The static guard** (a program, not an AI; `tools/check-autofix-patch.py
--auto` before a patch is kept, and `tools/automerge.py` before the merge):

1. *Additive only* (Python, on the syntax trees of the file before and
   after): every old statement is still there, unchanged, in the same order
   and nesting. No branch, condition, return or raise removed or changed; a
   `try` keeps its handlers; functions keep their names and arguments.
2. *No entry leaves a table*: an assignment to the same name may only grow (a
   list, tuple, set, dict, a block of rules by its lines).
3. *No new way out of old code*: a new `return`, `raise`, `break`, `continue`
   or exit is allowed only under a new condition that is not a constant, or as
   the last statement of a function; no constant given to (and no `del` of) a
   name the old code sets.
   *No old name is bound again* (part 2, found while building tier B: the
   additive rule alone let it through). A new statement may not define,
   import, assign, loop over or delete a name the old module or class
   already binds: a second `def allowed(...)` at the end of a file would
   silently replace the first, `TABLE = TABLE[:1]` would empty a table after
   it was written. It may not hide an old function, class or import inside a
   function, and may not change an old module-level object through an
   attribute, an index or a method that removes entries (`K.method = ...`,
   `TABLE[k] = ...`, `TABLE.clear()`). In a page script or in Rust: no old
   declaration declared again where the old code stands, nothing the old
   file declares assigned to.
4. *Nothing new that reaches out*: no new import but a few harmless modules,
   no more `eval`, `exec`, `open`, process, file-writing, loading or network
   calls than before, no new address or host name.
5. *Page scripts, Rust, the JSON table*: every old line of code still there,
   in order; a new line may not leave old code, switch a value of the old file
   to a constant, or reach out; the table may only grow. On a candidate of
   the engine the wrapper follows the new engine (no additive rule there).
   In I.K.E.'s own page scripts (since the fourth review of "Nothing gets
   worse", 2026-11-24, whose copies made of added lines only weakened the
   fingerprinting) a new line also may not leave code (`return`, `throw`,
   `break`, `continue`) anywhere but inside a function the change itself
   adds, may not read where or when the page is (the address, its host and
   protocol, the origin, `top`, `parent`, `frameElement`, the referrer, the
   date, `performance`, `Math.random`), and may not change an object the old
   script has by a method (`splice`, `pop`, `shift`, `push`, `add`, `set`,
   `delete`...) or `delete` from it: no early exit for some sites or frames,
   no protection that depends on the site or the time, no name taken out of
   the masked fonts or the hidden extensions, no site put into a list of
   exceptions. Since round 5 (2026-11-25: one-line copies passed both this
   guard and "Nothing gets worse") a new line also may not assign, anywhere
   in it (inside a callback, a loop, after a `;`, `++`), to a name the change
   does not declare itself (the level for some sites, the cores above 8, a
   size under which the noise stops, the key changed later); may not run
   something later (a timer, a frame or idle callback, a microtask, a
   promise's continuation, a listener) outside a function the change adds;
   and may not name sites in a pattern or a text (a regular expression of
   brand names or top-level domains).
   **Since round 6** (2026-11-25: rules on lines kept leaking. A destructuring
   `[k] = [n]`, a loop's target, a second declarator wrote to old names;
   `Object.defineProperty`, `Reflect.set` and `Object.assign` changed old
   objects; `document.URL` or `window['loc' + 'ation']` read the address; and
   two added lines re-wrapped the real processor count for every screen whose
   `devicePixelRatio` is not 1, a condition no session of "Nothing gets worse"
   made true. Placed before `install(window)`, as the review wrote them, they
   leak nothing, because install's own wrap comes after and stays outer; placed
   after it, they leak) a page script is read by its **syntax tree**. The guard has its
   own JavaScript parser (`tools/js-parse.py`: no package, no network, checked
   against acorn on every version of the page scripts in the history). It
   refuses what would read differently in the browser: an escaped name, a line
   separator outside a text, an HTML-like comment, an old octal, a name beyond
   ASCII. A script that does not parse is refused. Every statement of the old
   tree must still be in the new one, in order and in its place; statements
   may only be added to a list of statements. In what is added, nothing may:
   (a) write to what the old script has: a binding by any assignment, pattern,
   `++`, a loop's target or a declaration, a parameter's too, or one that
   changes what an old name refers to; an object's properties, `delete`, a
   method that changes it, `Object.defineProperty`, `assign`,
   `setPrototypeOf`, `freeze` and the like, `Reflect.set`, `__proto__`, a
   page object or a global. New code changes only objects it makes itself;
   (b) read the page's environment (where or when the page is, its screen,
   window and device, chance, timers and events), unless "Nothing gets worse"
   measures it in its matrix of the users' configurations (below), or the
   new code is inside a function the change adds and reads exactly what the
   old script reads too. An interface's prototype, such as `Date.prototype`,
   is no read;
   (c) reach a property by a computed name (only a literal, or a number:
   arithmetic, a length, a counter), or use `eval`, `Function`, `with`,
   `import()` or `.constructor`;
   (d) leave code (`return` or `throw` outside a function the change adds,
   `break` or `continue` out of a loop it did not add);
   (e) branch on what no measurement covers: an `if`, `?:`, `&&`, `||`, `??`,
   `switch`, loop test, `?.`, default value, `for-in/of`, or a `catch` that
   does more than give a value back. Its test may read only literals, the
   change's own names (set in their own function from such values; a
   parameter when every call gives such values), the level (`lv`, `strict`,
   `maximum`: every level is measured), and the configurations the matrix
   measures: devicePixelRatio, the window and screen sizes, the orientation,
   touch points, `matchMedia` with a literal query of the pointer, hover,
   colour scheme, motion, contrast, resolution or size, the languages, the
   time zone (`Intl`), the processors and the memory. These are listed once,
   in `tools/env-axes.py`, for both the probe and the guard: an axis added
   to the probe is allowed in the guard at once, and nothing else is. A
   condition on a counter, the time, the referrer, cookies, the visibility,
   a site, a text or an API the matrix does not cover stays refused;
   (f) define or re-wrap a property through an I.K.E. helper (`wrap`,
   `getter`, `setter`, any old function that defines properties) or
   `Object.defineProperty` and the like. The exception is a property whose
   name is a literal the old script never has, on a prototype: a new
   disguise, never a second wrap of a protected one.
   The rules on lines stay for what they add: the old lines in order, no
   always-true condition, nothing that reaches out, no site named, no new
   address.
   *What it accepts and refuses*, measured on 2026-11-25. Every one of the 38
   weakened copies made in the reviews is refused, the three forms of the
   gated re-wrap among them (by the re-wrap). Of Fable's 15 additive forms of
   an AI's honest fix (a new wrap, a helper, a counter, a listener, a
   timer...), 11 pass (`main`'s guard: 12, round 5's: 11). Of the six reads
   of the environment no matrix covers (`navigator.userAgent`,
   `document.cookie`, `visibilityState`, `document.URL`, `baseURI`,
   `window['loc' + 'ation']`), none passes (`main`'s and round 5's: 4). Of the
   33 commits of `main`'s history that added lines to `fingerprint.js`
   (their added lines alone), it refuses all 33 (`main`'s guard 28, round
   5's 31). Those are a person's feature work: each changes old objects,
   wraps protected properties again, branches on page data or feature
   detection, or reads the environment, and only one of them is refused
   for a branch alone. So the automatic fix can add a new disguise with
   conditions on the users' configurations and the level, a helper, a new
   wrap; changing what the old script protects stays a person's.
6. *Small*: 5 files and 150 lines per attempt, 8 files and 400 lines for all
   the AI commits of a pull request; no file added, removed or renamed.
7. *The component manifest*: only a new entry, a plain download of a file
   that is already there with the sha256 it declares.

What it does not prove: a fix can still weaken a protection by *adding* code
(a new condition true too often, a new entry in a list of exceptions). That
is what "Nothing gets worse", the whole suite and the reviewers are for.

**Two independent AI reviewers** (`tools/ai-review.py`, `ai-review.yml`).
When every other condition holds on a commit, `tools/automerge.py` starts the
review. Two free providers other than the one that wrote the fix (the
`Author:` line the guard job writes into the `autofix:` commit), different
from each other, first those that wrote nothing on the branch, get only the
diff of the files the AI changed and the failure it answers, between marks
made for that request and named as data. Each is asked how the change could
weaken blocking, privacy, fingerprinting, the sandbox or the updates, and
answers one JSON object, `{"verdict": "approve" | "reject", "reasons":
[...]}`; anything else is no answer. Both approve: the commit gets the status
`ai-review` and a comment with the verdicts, and the merge is judged again.
One reject: the fix is refused and the next attempt of the automatic fix
starts with the reasons (`work=refused/<sha>`). Fewer than two answers: nobody
is asked; the review is started again later. The job with the providers' keys
has no GitHub token and runs nothing a model wrote. A change of a tier-B file
the owner opened needs **three** reviewers of three providers (below). A fix
whose author is none of the free providers (ChatGPT's adopted fix, a
deterministic recipe) may be reviewed by any of them.

**What a commit of an AI needs to merge** (`ai_requirements`), on top of the
verified merge: the static guard on the whole AI change; the category
`no-regression` ("Nothing gets worse": ad blocking with YouTube's, the
fingerprinting surface, the network hosts, the security settings, against
`main`) passed on that commit; the step "Fingerprinting unchanged" passed too
(every fingerprinting value the same or stricter: a value that is only
"changed", or passed by evidence or by the allowlist, needs a person on an
AI's change; the two reviewers are shown those rows); no "worse" of "Nothing
gets worse" ever found on the same change of protected code (its patch id,
the label `nothing-gets-worse:<id>` the merge adds when it fails: a later run
that passes does not count; a person removes the label to have it judged
again); for an AI's change of the page scripts or `ike/shields.py`, three
measures with independent keys (`--runs 3`), any one weaker fails; the
workflow's own status `ai-review` and its
comment with two approving reviews of that very commit by two providers,
none the author's; no test file changed beyond the recorded rules the
workflow itself adds.

**Nothing waits for a person, nothing is closed.** Each former "person" path
and what happens now:

| Before | Now |
|---|---|
| An AI fix of protected code (`ike/blocker.py`, `ike/scriptlets.py`, the safety modules, page scripts) | merges by itself under the static guard, `no-regression` and the two reviews |
| A filter lists' fix | the same; the recorded rules the workflow adds are not a test change |
| The cap of attempts (4 on a candidate, 2 on `main`'s branches and the security ones) | per day: when today's are used up the plan says "retry", nothing is closed, no issue; the next day the daily check starts it again, another free provider first, a fresh context with what was tried (`autofix_commits_today`, `tools/ai-work.py`) |
| The AI could not, or a check refused its change ("ATTENZIONE..." issue) | the same daily retry; no issue |
| No free provider five times | still retried every day; one informational note after `RETRY_CAP` |
| A fix refused by the merge's rules or by the reviewers | the automatic fix again with the reasons (`refused/<sha>`) |
| A refresh conflict beyond CHANGELOG and version | a candidate per component is rebuilt from `main` by the daily maintenance; on any other branch `main` is merged in with the files in conflict taken from `main` ("conflicts as main's"), its tests run again and the automatic fix goes on |
| A second version raise, a CHANGELOG heading of another version | `main` merged in with "version as main's": the version files are `main`'s, the candidate's lines move under `main`'s unpublished version |
| Checks passed but a category not verified, or a check that did not pass | the daily check starts its Tests, Security and Arch Linux again |
| A builder that refused, a pin of the workflows that fails its tests, a dependency used but not declared | "retrying": the re-anchoring every day, the next release of the pin, the PKGBUILD's candidate; no AI touches tier B |
| A lists finding no AI may fix (the engine itself) | as today the engine drops the rule; "retrying", it goes with a new engine |
| A security fix that still fails | stays **blocked** and the owner is told (the owner's earlier decision), and the automatic fix tries again every day under the security rules |
| An advisory with no fixed version upstream; YouTube's rules and uBlock Origin's own resources | unchanged: blocked and the owner told; the owner's own rules |
| A failure of GitHub, a setting or a workflow | unchanged: an issue (no AI may fix a workflow) |

The maintenance ledger shows these as **retrying** (with the number of tries
or days); `tools/automerge.py --daily` (job `judge-again` of the daily check)
judges every open pull request of the automation again once a day and starts
what its last verdict left for the next day. The comment on a pull request
that is not merged is informational and asks nothing.

**AUTOMAT's memory of attempts** (`tools/automat-memory.py`). One record per
attempt, written only by the workflow's own code (job `remember` of
`autofix.yml`, no AI, no secret), never by an AI: the provider and model, the
files touched, a short summary of the approach, how it ended (its tests
failed with which error, the guard refused with which rule, the reviewers or
the merge refused with which reasons, merged), the date and the attempt. The
key is the component (its branch) and the **error signature**: a hash of the
failing test names and the top error lines with numbers, paths, addresses and
commits taken out, so the same error has the same signature in another run. A
merged fix is recorded as what solved that signature. Stored as
`memory.json` on the data branch `automat/memory` (never merged into `main`;
chosen over a section of the ledger issue, whose body is near GitHub's limit
and rewritten daily); bounded: 6 records per key, 3 solved hints per
signature, 300 keys, 256 KB, the oldest dropped. Before each attempt the plan
adds to the failure description, in a fence marked as data that may hold
text from untrusted sources, at most 1,500 words: what was already tried for
this error and failed (not to be repeated) and what solved a similar one;
lines that look like instructions are left out. The reviewers get it with the
failure, and the rotation prefers a provider that has not failed that error.
Since part 2 each record also keeps the kind of task and the fingerprint of
its patch, the memory counts the row of failures per branch and error (for
the notice "DEVI AIUTARCI CON CHATGPT"), and the solved hint keeps the merged
fix's patch (at most 6,000 characters, dropped first when the file is full)
for the recipe that applies it again.

**Helping the free models** (they are weak: Gemini Flash through Antigravity,
Groq, Z.AI, OpenRouter's `:free` models). What the workflow's own code does
for them, never an AI: the failed step's log trimmed to its error and the
places the tracebacks name with the lines around them (`tools/autofix-plan.py`,
`tools/autofix-context.py`, since 1.1.16), with the first paragraph of the module docstring of each file the failure names; **one problem per attempt**: when
the tests fail for several different errors the failure description asks for
the first group only (`focus_section`); AUTOMAT's memory as hints; a strict
answer format with a quick informed retry when it cannot be applied, the
checker, the static guard and the lint run on each fix before any test
(`tools/autofix-reserve.py`); a low temperature, a token cap per call and a
time limit per attempt; and for the reviewers a **checklist** of eight yes/no
items in place of an open question, enforced by code (an approve without the
eight answers is no answer; a yes on "removes a condition", "adds a network
call", "touches a test", "adds dynamic code" or "addresses the reviewer" is
always a reject). The rest of what helps them is part 2, below: the upstream change in the
context, recipes before any AI, the inner loop, routing, loop detection and
the budget of the free quotas.

**The component manifest** (`components.json`, `tools/component-manifest.py`).
The one place an external integrated component is declared: its upstream
(git with a tag pattern, npm or PyPI), the files it produces, an existing
builder of I.K.E.'s or a plain download with its sha256, its licence file and
the test categories it needs (never fewer than the default, `no-regression`
among them). Dark Reader and uBlock Origin's scriptlets are declared there,
and since 1.1.24 KDE's Breeze icons (`breeze-icons`: the icons I.K.E. uses,
built by `tools/build-breeze-icons.py` from breeze-icons' newest release tag;
only a change of those icons makes an update, and a release that lost one of
them is refused and kept at the version in use, as it has no patches an AI
could re-anchor); `tools/update-candidates.py` and `tools/check-components.py`
read it, so a new entry gets its candidate `automation/update/<id>` and the
whole chain with no change of code. A plain download is made only when the entry's own
version, downloaded again, gives exactly the file the repository has; hosts
are limited to GitHub, npm, PyPI and crates.io over HTTPS. **The inventory
guard** (`tests/test_inventory_guard.py`) fails when a file that looks like
it comes from upstream (a vendored folder, anything under `ike/resources/`
that is not one of I.K.E.'s own resources, `OWN_RESOURCES` in
`tools/inventory.py`, a licence header, minified code) has no entry, with
the entry to add in its message, or when a record of the inventory has no
update path. The automatic fix may add that missing entry (rule 7 above).

**The owner's token, needed once.** `main`'s protection requires the check
`tests` of the pull request itself. A push or a pull request made with the
workflow's own token starts no workflow: its `pull_request` runs wait for an
approval forever, and the runs the automation dispatches are not taken for
the required check (PRs #107 to #110: "Required status check "tests" is
expected", HTTP 405). So **the repository secret `IKE_WORKFLOW_TOKEN` is
required for AUTOMAT to be 100% unattended**: a fine-grained token of the
owner's, for this repository only, with Contents, Pull requests and Workflows
read and write. When it is set, the candidates' pushes and pull requests
(`daily-maintenance.yml`), the automatic fix's (`autofix.yml`, job publish)
and the refresh (`tools/automerge.py`) use it, so the pull request's own
Tests, Security and Arch Linux start and the dispatched runs are not needed;
a verified pull request that only has dispatched runs is closed and opened
again with it, which starts them. It is only in those steps: no AI ever sees
it, and the automatic fix's push checks once more that nothing under
`.github/` changes. Without it nothing crashes and nothing is weakened: the
verified candidate is "retrying", the owner gets one note that says how to
make the token, and it merges by itself once the token exists. A fine-grained token
expires: the weekly check (`health.yml`, `tools/automation-health.py` `token_problem`)
reads GitHub's header `GitHub-Authentication-Token-Expiration` and opens the issue "Automation
health" 21 days before the date, or at once when GitHub refuses the token (2026-11-25). Branch
protection is never changed, no check is faked, no run is approved by API.

**The informed signature** (`tools/release-notice.py`, `release-ready.yml`).
The notice lists every change merged since the last published version:
before everything else each change an AI wrote on a reserved file (only
possible with the owner's switch `AUTOMAT_TIER_B`: its files, its three
reviewers' verdicts, "Nothing gets worse"); then, marked, the other ones that
touch reserved files (tier B: the deterministic tools), each with its diff
link; then each AI change
of protected code with its files, a one-line summary, the two reviewers'
verdicts and the result of "Nothing gets worse"; the other changes; and what
is still being retried or blocked; and the use and the remaining budget of
each provider's free quota. What could not be read is said as not read.

**Residual risks, said plainly.** The reviewers are free models reading
text an AI wrote: a fix that addresses them is one more reason to reject, the
answer must be strict JSON, and they are never the last check, but they can
be wrong. The static guard is strict about what is removed and cannot judge
what is added. "Nothing gets worse" compares what it measures. Free quotas
run out: then nothing merges, and the retry comes the next day. The owner's
token has more rights than the workflow's own; it is used only by steps with
no AI. Part 2 adds its own: the limits of the free quotas are careful guesses
until a person checks them (the live headers correct them, but a provider
that sends none is only counted); a recipe's rename or re-anchoring is a
program's guess, kept only when every check passes; the job `try` runs code
an AI wrote (with no key, a token that only reads, and a checksum on the fix
that is pushed); with `AUTOMAT_CHATGPT_AUTOMERGE` on, a fix written outside
this repository reaches `main` with no person reading it, under the same
gate as an AI's; with `AUTOMAT_TIER_B` on, an AI's statements can be added to
the sandbox's and the update channel's files outside their frozen functions,
and a workflow's pinned versions can move: three free models and the tests
stand where a person stood.

### AUTOMAT, part 2 (2026-11-23)

What the first part left unbuilt. Three **repository variables** steer it;
only the owner can set them (GitHub's settings: no file of the repository and
no workflow can, and no tool of the automation ever writes one):

| Variable | Default | What it does |
|---|---|---|
| `AUTOMAT_CHATGPT_AFTER` | 4 | after how many failed attempts in a row on the same error the notice "DEVI AIUTARCI CON CHATGPT" comes (1 to 50) |
| `AUTOMAT_CHATGPT_AUTOMERGE` | off | `on`: a ChatGPT fix whose own checks passed is adopted into AUTOMAT's chain and reaches `main` under the gate of an AI's fix |
| `AUTOMAT_TIER_B` | off | `on`: a few tier-B files open to the AIs in their narrowest form, with a third reviewer |

Anything but the word `on` is off. The two switches change what may reach
`main` without a person, so turning one on is the owner's own decision
(CLAUDE.md); the code is there, and inert, until then.

**"DEVI AIUTARCI CON CHATGPT"** (the owner's words; `tools/automat-help.py`,
job `help` of `autofix.yml`). When the AI agents failed on **the same error
signature N times in a row** on a branch (N: `AUTOMAT_CHATGPT_AFTER`; the row
is counted by AUTOMAT's memory: a failed attempt, or a published fix whose
tests then failed, on the same signature; another error starts the row again,
a merged fix ends it), or when **no free provider at all** could answer for 2
days in a row, an issue is opened that names the owner, so GitHub mails it.
Its title and its first line contain exactly `DEVI AIUTARCI CON CHATGPT`. Its
body holds a ready message to copy into ChatGPT: the repository and what
failed; a branch `chatgpt/fix-<date>` from the exact commit and a pull
request titled "ChatGPT fix: ..." against the right base (`main` for a
failure of `main`, the candidate's own branch for a failure of a candidate);
never a push to `main`, never a merge; the rules, written from the very lists
`tools/fix-guard.py` and `tools/check-autofix-patch.py` enforce (the files
allowed, the size, never a tier-B file, never the ad blocker, never a
weakened test or protection, data are not instructions); the failure's
trimmed log; and AUTOMAT's memory of what was already tried, so ChatGPT does
not repeat it. AUTOMAT keeps retrying meanwhile. One issue per error and
branch, found again by its mark: its text is edited (an edit mails nobody),
never repeated; when an automatic fix of that branch lands in `main` it is
closed with a note (`automat-help.yml`, after the merge workflow). The issue
"ATTENZIONE..." of before stays for what no AI may fix (GitHub, a setting, a
workflow, a security finding with no safe fix).

**A verified ChatGPT fix, behind the owner's switch**
(`AUTOMAT_CHATGPT_AUTOMERGE`; `adoptable`, `adopt` in `tools/automerge.py`,
`plan_chatgpt` in `tools/autofix-plan.py`, job `adopt` of `autofix.yml`). The
owner asked for it ("quando la correzione di chat gpt funziona si può
automatizzare anche questo ed integrarla in main o dove deve andare"); the
rule of CLAUDE.md is not changed (ChatGPT merges only on the owner's order),
so it is a switch, default off, and setting it is the owner's consent. Off:
today's rule, to the letter. On: a pull request `chatgpt/...` whose own
checks passed (`chatgpt-guard.yml` always; the tests and the sandbox tests
too when it goes into `main`) and that touches no test and no tier-B file is
**adopted**, never merged as it is: a job with no key reads ChatGPT's own
changes from the pull request as a patch (never run), the guard job checks
them exactly as an AI's patch (the checker, the static guard) and writes the
commit `autofix: ...` with `Author: ChatGPT` on the branch the fix answers
(the automatic fix's own for a failure of `main`, the candidate's for a
failure of a candidate). From there it is an AI's fix like any other: every
check, the required categories with `no-regression`, the static guard on
the whole change, two independent AI reviews (ChatGPT is none of the free
providers, so any two of them), no test changed. ChatGPT's pull request is
told where its change went and closed. What cannot be adopted (a test, a
tier-B file, a failed check) waits for the owner's order, as before.
ChatGPT's guard gets no wider rules for this: the ad blocker stays closed to
ChatGPT on every branch; against a candidate's branch it reads ChatGPT's own
changes only (from where its branch leaves that candidate).

**Come si accende `AUTOMAT_CHATGPT_AUTOMERGE`** (lo può fare solo il
proprietario, dal sito di GitHub):

1. Apri la pagina del repository su GitHub e vai su **Settings**.
2. Nel menu a sinistra: **Secrets and variables** → **Actions**.
3. Scegli la scheda **Variables** (non "Secrets") e premi **New repository
   variable**.
4. In "Name" scrivi `AUTOMAT_CHATGPT_AUTOMERGE`, in "Value" scrivi `on`, poi
   premi "Add variable".

Da quel momento una correzione di ChatGPT che supera tutti i controlli entra
da sola. Per spegnerlo: nella stessa pagina cancella la variabile, oppure
cambia il valore in `off`. Qualsiasi valore diverso da `on` vuol dire spento.

**Tier B, behind the owner's switch, in its narrowest form**
(`AUTOMAT_TIER_B`; `tools/tier-b.py`, called by the static guard). The
concern stands: a workflow step an AI may edit is arbitrary shell in a job
that holds tokens. So only what a program can prove harmless opens:

- **a workflow where nothing changes but a pinned version**, checked line by
  line with the logic of `tools/ci-pins.py`: the file keeps its number of
  lines; every changed line is, before and after, the same pin (an action's
  full commit with its version comment, the same action, a release tag whose
  commit is read with `git ls-remote` from the action's own repository;
  cargo-deny's version; the Python, Node.js or numeric Rust version), the
  line otherwise identical, never an older version. A command, a permission,
  a secret, a trigger, `runs-on`, a new step is no pin and is refused. The
  fix's push checks it once more with the network, and needs the owner's
  `IKE_WORKFLOW_TOKEN` (GitHub refuses a workflow change to the workflow's
  own token);
- **Python in `ike/app.py`, `ike/updater.py` and `ike_boot.py`** under tier
  A's additive rule, plus fixed invariants: every function of the update
  channel (`ike/updater.py`, `ike_boot.py`) and, in `ike/app.py`, every
  function whose code decides the sandbox and isolation switches, the update
  check or the extensions is **frozen** (the very same syntax tree: an added
  `if ...: return True` inside `verify_signature` would be additive, and is
  refused), so the signature check still refuses an unsigned or wrongly
  signed update (the protected tests `tests/test_updater.py::test_signature`
  and `::test_bad_signature_is_refused` prove it on every commit, and no AI
  may change a test); `UNSAFE_SWITCHES`, `UNSAFE_FEATURES`, `UNSAFE_ENV`,
  `LNA_FEATURES` and `ENGINE_SAFETY` only grow, and no new code names them;
  the update check stays once every 24 hours (the comparison with
  `last_app_check` is the same); and new code stays away from what decides:
  it may not name a frozen function or the updater (a new line that calls
  `save_state(...)` would change the update channel without changing one of
  its functions), write to or call the configuration, call a setter
  (`set...(...)`), give a constant to an attribute or an entry of any object
  (`self.blocker.enabled = False`), or hold a text that names an engine switch
  or a sandbox setting. The patch checker's own rule stays above all this: no added or
  removed line that names an engine protection;
- **a third independent free reviewer** for any such change (three reviews
  of three providers, none the author's), and the change is **listed first**
  in the signing notice, with its files and the three verdicts.

Everything else of tier B stays never an AI's, and so do the rule-keepers:
`tools/fix-guard.py`, `tools/automerge.py`, `tools/ai-review.py`,
`tools/no-regression.py`, `tools/check-autofix-patch.py`, `tools/tier-b.py`
and `chatgpt-guard.yml` (a workflow: only a pin of it could ever change).

**Come si accende `AUTOMAT_TIER_B`** (lo può fare solo il proprietario, dal
sito di GitHub):

1. Apri la pagina del repository su GitHub e vai su **Settings**.
2. Nel menu a sinistra: **Secrets and variables** → **Actions**.
3. Scegli la scheda **Variables** (non "Secrets") e premi **New repository
   variable**.
4. In "Name" scrivi `AUTOMAT_TIER_B`, in "Value" scrivi `on`, poi premi "Add
   variable".

Da quel momento le AI possono proporre quelle poche modifiche, sempre con
tre revisori e sempre elencate per prime nell'avviso di firma. Per spegnerlo:
nella stessa pagina cancella la variabile, oppure cambia il valore in `off`.
Non dare mai al token `IKE_WORKFLOW_TOKEN` il permesso "Variables": così
nessun workflow può accendere un interruttore al posto tuo.

**The budget of the free quotas** (`tools/ai-quota.py`, data in
`tools/ai-quota.json`). The limits of each provider (requests and tokens per
day and per minute) are data, each with its source; where the provider's
documentation could not be read on the day the file was written the number
is a conservative one and says `"verified": false` (today: all four; a person
who checks one sets it with the date). The answers correct it: the rate-limit
headers of every call (their names per provider are data too) and a 429 with
its `retry-after`; what a provider says today counts more than the file. The
use of each day is kept in `quota.json` on the data branch `automat/memory`,
per provider and candidate; the steps that hold the keys only write numbers,
and jobs without keys add them to the record (job `remember` of
`autofix.yml`; `automat-quota.yml` for the reviewers, so `ai-review.yml`
never gets the right to write). Before each call: a provider that is spent
today is never asked; a fix is not started unless, after it, two other
providers with a key (three for tier B) keep room for one review each (the
reserve: without it the fix waits and nothing is wasted); while another
real update is pending at the same time, one candidate's fixes take at most
half of a provider's day (alone, all of it); a limit per minute is waited
out when it is short. The signing notice shows the use and what is left per
provider, and whether each limit was verified. Since 2026-11-24 real updates may
use all of the free quota; what they leave each day goes to self-improvement,
the drill and the CI's updates ("Real updates first, and every day's free quota
used", below).

**Recipes before any AI** (`tools/automat-recipes.py`, a step of the job
`fix` with no key, before Antigravity). A fix that already solved this very
error (AUTOMAT's memory keeps the patch of a merged fix by the error's
signature: applied again when the same error comes back, as on a candidate
rebuilt from `main`); a symbol the upstream change renamed (the failure
misses a name, and the upstream change says for sure it was renamed: replaced
as a whole word in the files of I.K.E. involved); a builder's patch
re-anchored (on a builder's branch, the new upstream lines the refusal shows
are searched for the lines closest to the old anchor; one clear place only).
What a recipe makes is treated exactly like an AI's fix: the cheap checks,
the patch checker with the static guard (the builders' rule for an anchor),
the lint, then the tests, "Nothing gets worse" and the reviewers before any
merge (its commit says `Author: Recipe / <name>`). An AI is asked only when
no recipe applies or its result is refused; a recipe that failed for an
error is not tried again for it.

**The upstream change in the context** (`tools/upstream-diff.py`, in the job
`plan`: no key of any AI there). For a candidate of a component the failure
description gets what its authors changed between the version in `main` and
the new one: for the engine's crates the versions that differ in
`Cargo.lock` (the ones the failure names first), each crate's repository from
crates.io, then GitHub's comparison of the two release tags and the release
notes; Dark Reader by its two versions; uBlock Origin's scriptlets by their
two commits; the test packages from PyPI. Only api.github.com, crates.io and
pypi.org are asked, JSON only, the repository's token to GitHub alone. It is
cut to a budget (the lines about the names the failure mentions first) and
quoted as data: lines that look like instructions are left out, links cut,
fences defused. The renames a program is sure of go to the recipes.

**The inner loop** (`tools/autofix-inner.py`, `tools/autofix-reserve.py
--inner`, the jobs `try` and `again`). The answer must be exactly the patch
format (one JSON object, a few small edits). Cheap checks run at once, none
of which runs what the model wrote: Python is compiled, never run;
JavaScript is parsed by `node --check`; JSON is read; the patch checker with
the static guard and the lint read the change; a change of the engine's
wrapper is compiled by `cargo check`, which runs the crates' build scripts
and therefore runs as a user of its own with no key, no sudo and no network
(the crates fetched before). What a check finds goes back to the **same**
model, at most three answers per model; a refusal for safety still stops
everything; Antigravity's own fix gets the same cheap checks, and what they
find goes to the reserves. Then the job `try`, which holds no key and a
token that only reads, runs **the tests that failed** (those of the group
this attempt was asked to fix) on the accepted fix, in the tests' own
environment. That job runs what an AI wrote, and the workflow runs for
`main` (its caches and artifacts are `main`'s), so the tests run as a user of
their own with no sudo and no network but the machine's own, on a copy of the
tree: nothing of the job's own processes can be read from there. When the
tests pass the fix is pushed and GitHub runs the whole suite as before; when
at least one of them still fails **with the same error** it is not pushed,
and the job `again` starts the next round with the fix and the tests' output
for the same AI (at most three rounds). The publish job pushes only the
bundle whose checksum the guard job wrote. A failure with no test to run, an
environment that could not be set up, or tests that fail in another way now,
is "not-run": the fix is published and tested by GitHub as before.

**Routing and going in circles** (`tools/automat-route.py`). The kind of
task is read from the failure (rust, multi-file, builder, lists, manifest,
page-script, python): hard ones go to the strongest free model first, simple
ones to the fast ones; the starting order is data (`tools/ai-quota.json`),
and once a provider has enough recorded attempts at a kind of task its
success rate in AUTOMAT's memory places it. A provider that already failed
this very error goes last. Every call keeps a low temperature and a cap on
the answer, smaller for a simple task. The fingerprint of each patch (its
added and removed lines) is compared with the ones of this attempt and with
those that already failed for this error: the same patch twice stops the
attempt, and that is recorded.

**Stricter gate of the fingerprint protection** (permanent: the owner's
decision of 2026-11-24). Why: an independent review showed weakened copies of
`ike/resources/fingerprint.js` that pass both the static guard
(`tools/fix-guard.py`) and "Nothing gets worse" (only one first-party test
site, APIs and realms it never reads, fonts judged on the settings, noise not
tied to the key). So an AI's change of that file (`STRICT_GATE_FILES` in
`tools/tier-b.py`) merges by itself only when, besides everything an AI's fix always needs,
**three** independent reviewers of providers other than the author's approved
it (the tier-B mechanism, `needed_reviews`) and the report of "Nothing gets
worse" on the commit (the artifact `tests-checks` of `tests.yml`) has only
"stricter" rows of the fingerprinting surface: any "changed", "accepted",
"worse" or other row of it refuses the change (`strict_gate` in
`tools/automerge.py`, checked before the reviewers are asked). No person is
involved: a refused change is "retrying" like any other AI fix, and the
automatic fix tries again with the reason (its attempts of the day, the
providers rotated); a report that cannot be read is "not verified" and its
checks run again. Every other file, an update with no AI, and a person's or
Claude's pull request are judged exactly as before. The gate is permanent:
it stays also after "Nothing gets worse" and the static guard are hardened.

### The AUTOMAT drill (2026-11-23)

The owner asked for a live exercise of AUTOMAT on GitHub: "un test fake fatto bene, molto
complicato, uno scenario reale di un aggiornamento massivo di Qt e di tutte le altre componenti
installabili, per vedere se le IA riescono a risolvere il problema". The drill is that exercise. It
runs AUTOMAT's real chain, end to end, on a realistic emergency, and it can never reach `main` or a
user.

**The one command** (on the owner's computer, or by Claude):

```bash
gh workflow run automat-drill.yml --ref main
```

`-f scenario=qt` is the default; `-f action=stop` ends a drill early with its final report;
`-f action=report` writes the report into the run's summary only; `-f restart=true` starts again
over a drill that runs.

**The scenario** (`tools/automat-drill.json`, scenario `qt`): a major release of Qt and PyQt
("PyQt6 7.0 / Qt 7.0", simulated), with jeepney 1.0 moving at the same time, changes some of the
APIs I.K.E. really uses, as such releases do: enum members renamed, methods renamed, a method that no
longer takes a callback. The breaks touch different files of I.K.E., ordinary interface modules and
one protected (tier A) module; some are easy (a rename the release notes name, which the recipe
`renamed-symbol` may try before any AI), some need the AI to understand the change (a callback
replaced by a signal; a break inside `try` that fails silently; a renamed getter in the first line
of a handler of the protected module, where the static guard's additive rule allows only adding
code). The list, with what each break touches, the tests
it breaks and **the expected solution, for judging the drill**, is in `tools/automat-drill.json`
on `main` (a drill's branch carries only the breaks: the AIs' checkout does not hold the answers).
The scenario's release notes (also there) are what "What changed upstream" gives the AIs, read
from `main`'s copy, as a real release's notes would be. The expected solutions keep working with
today's Qt (the new API with a fallback to the old one, or an API both releases have), because the
drill also runs where today's Qt is: Arch Linux (`arch.yml`) does not get the simulated release, so
a fix that forgot the fallback fails there, and AUTOMAT's Arch path fixes that too.

The six breaks of scenario `qt` (their expected solutions: `tools/automat-drill.json` on `main`):

| Break | What the new release changes | I.K.E.'s files | Difficulty |
|---|---|---|---|
| B1 | `QWebEnginePage.WebAction.ReloadAndBypassCache` renamed `ReloadBypassingCache` | `repair.py`, `shieldpanel.py`, `window.py` | easy |
| B2 | `QWebEnginePage.recentlyAudible()` renamed `isRecentlyAudible()`: the whole browser fails at its first tab | `window.py`, `features.py`, `resources.py`, `plasma.py` | medium |
| B3 | `QWebEnginePage.findText()` takes no result callback: the count comes with `findTextFinished` | `window.py` (the find bar) | hard |
| B4 | `QWebEngineFullScreenRequest.toggleOn()` renamed `isToggleOn()`, in the first line of the full-screen handler | `webview.py` (protected, tier A: only additions) | hard |
| B5 | `QWebEnginePage.LifecycleState.Discarded` renamed `Evicted`, inside `try`: tabs silently stay awake | `features.py`, `resources.py` | hard |
| B6 | jeepney 1.0 (another component at once): `Message.serialise()` renamed `serialize()`, inside `try`: the desktop integration silently turns off | `desktopbus.py` | medium |

Only I.K.E.'s own code (the checkout's `ike/` and `ike_boot.py`) sees the new names: the tests and
their helpers, which no AI may change, and the libraries' own code keep today's, as a real release
changes its own code along with its names. Each break fails at least the test the scenario names
for it, and with every expected solution applied the tests pass under the simulated release and
under today's Qt (checked before the drill was published).

**How it runs** (`tools/automat-drill.py`, `automat-drill.yml`; no AI, no AI key):

1. `start` makes, for each scenario, the branch `automation/update/drill-<name>` from `main`
   with one commit `update: drill-<name> <from> -> <to> (no AI)` that only adds the marker
   `tools/automat-drill.active` and writes the scenario's breaks into `tools/automat-drill.json`
   (a candidate of the full chain: `tools/update-candidates.py` knows the ids `drill-*`, never in a
   daily plan and in no serial group, so it holds back no real candidate). It opens the draft pull
   request "DRILL: ..." with the label `automat-drill`, starts its Tests, Security and Arch Linux,
   and opens one issue "DRILL: esercitazione di AUTOMAT in corso" (nobody named or assigned).
2. In the drill's own test runs (Tests, the Security tests, the automatic fix's job `try`) the
   composite action `ike-test-env` sees the marker and installs `tools/automat-drill-shim.py`
   into that runner's Python: only a process started from the drill's checkout gets the simulated
   release (`main`'s checkout in the same job, the base of "Nothing gets worse", keeps today's Qt).
   On every other branch the step installs nothing.
3. From there everything is AUTOMAT's own: the tests fail and hand over, the plan (one problem per
   attempt, the memory, the upstream notes), the recipes, the free AIs with the inner loop, the
   static guard, the job `try`, publish, Tests again, `tools/automerge.py` with "Nothing gets
   worse" and the two reviewers, the retries with the reasons, the daily retry, and "DEVI AIUTARCI
   CON CHATGPT" after `AUTOMAT_CHATGPT_AFTER` failures in a row on one error.
4. `tick` (every three hours, and as soon as `tools/automerge.py` finds a drill complete) writes
   the report into the drill's issue (an edit: no mail) and the run's summary; when every drill is
   complete, or after its hours (`hours`, 48), the final report is one comment naming the owner,
   the drill's only mail, and its issue, pull request and help notice are closed (the branch stays).

**What makes it a drill and never more** (each tested in `tests/test_automat_drill.py`):

| Where | What a drill gets |
|---|---|
| `tools/automerge.py` | judged like any other pull request, so the guard, "Nothing gets worse" and the reviewers really run; where it would merge, the verdict is "drill": a note on the pull request ("complete"), and the report is asked; `merge_it()` refuses one; no comment names the owner; never rebuilt by the daily maintenance |
| any one mark | the branch `automation/update/drill-*`, the title `DRILL...`, the label `automat-drill`, the file `tools/automat-drill.active` |
| `tools/release-notice.py` | never listed, neither as a change nor as an update still being retried |
| `tools/maintenance-ledger.py` | never an entry (its branch is no update) |
| `tools/automat-help.py` | "DEVI AIUTARCI CON CHATGPT" in drill mode: title `DRILL (esercitazione) DEVI AIUTARCI CON CHATGPT: ...`, the body says it is an exercise, the message for ChatGPT is the real one (its pull request would go against the drill's branch), nobody named or assigned; never the notice "no free provider at all" |
| `tools/autofix-plan.py` | fixed like a candidate, with its scenario's attempts per day (`attempts_per_day`, at most 12; a real candidate keeps `FIX_ATTEMPTS`); its Security run opens no security branch; what would open an issue is retried instead |
| `tools/upstream-diff.py` | "What changed upstream" is the scenario's release notes, from `main`'s copy, with no network |
| AUTOMAT's memory and the quotas | the attempts are recorded under the drill's branch name, and the drill uses the real free quotas (its share is in the report); since 2026-11-24 it is background work: only what real updates leave, never while one is pending ("Real updates first", below) |

**The report** says, for each break: fixed or not (its tests in the junit results of the last
Tests run), by which provider or recipe and at which attempt (the first `autofix:` commit after
which its tests passed, its `Author:` line), after how many hours; the attempts of AUTOMAT's memory
with how each ended (the guard's rule, the reviewers' reasons); the reviewers' verdicts; the checks
of the last commit, and "Nothing gets worse" on it and on every commit an AI or a recipe wrote; the
free quota the drill used per provider; the drill's help notice. At the end it adds the expected solutions, to judge the drill.

**What only the live run shows**: whether the free models find the fixes; how many attempts and
how much quota they use; whether the reviewers approve; the real duration of the runs; what the
Arch Linux job says of fixes that forgot the fallback; whether GitHub starts the pull request's
own checks (with the owner's `IKE_WORKFLOW_TOKEN`) or the dispatched ones.

### Real updates first, and every day's free quota used (2026-11-24)

The owner's decisions of 2026-11-24, in the owner's words: "use the free AIs every day, always when
needed, above all for real updates; what is left goes to self-evolution, drills etc.", and then:
**real updates may use all of the free quota, at any time; what they leave each day goes to
self-improvement** (the drill, the replay bench, self-evolution, and the CI's updates after the real
ones). There is no fixed share. Still free providers only, no cost, nothing weakened; it only decides
**who gets a free quota first**. The rules are in `tools/ai-quota.py` (the Budget every AI call already
goes through), the numbers in `tools/ai-quota.json` (`"priority"`, and each provider's `"reset"`); the
proofs are `tests/test_automat_priority.py`.

**Four classes**, by the branch of the work (`priority_of`; the prefixes are data, each must end in `-`
or `/`, and a real update's branch can never be made background):

| Class | What | Branches |
|---|---|---|
| 1 | security fixes | `automation/update/security-*` |
| 2 | updates of what ships to users: the engine and ad-blocking crates, Dark Reader, uBlock Origin's scriptlets, the filter lists, Python and Qt, the Breeze icons, the daily candidate, a fix of `main`; anything unknown too (never starved; a trial started by hand has no prefix of its own and counts here) | every other `automation/update/*`, `automation/builder/*`, `automation/daily-maintenance`, `automation/autofix-main` |
| 3 | updates of the CI and the tools | `automation/update/ci-*` |
| 4 | background: the AUTOMAT drill, the replay bench, self-evolution | `automation/update/drill-*`, `automation/bench/*`, `automation/evolve/*` |

**Classes 1 and 2 may always use all of every free quota**, at any time: nothing but the provider's own
limits (and the rules that were already there: a fix starts only when two other providers can review it;
while another security fix or real update is pending at the same time, a candidate takes at most half
of a provider's day, `share_per_candidate`, so two real updates share it fairly; a lone one may use all
of it) ever stops them. Security fixes come first in the
order of the work: the daily check starts the work waiting in the ledger by class (`tools/ai-work.py`).

**Classes 3 and 4 get only what real work leaves, and all of it** (`priority_why`):

- **never while work of class 1 or 2 is pending or retrying**, and they pause at once when one appears
  (also their reviews). Pending (`pending_all`): an open pull request of the automation whose last commit
  has a run that is not green (failed, cancelled, running, or not readable; only the newest run of each
  workflow counts, so a cancelled run that was run again does not), read by the plan of `autofix.yml`
  with GET calls (`tools/ai-quota.py pending`) and handed to the agent and the reserves
  (`--quota-pending`, with `--quota-memory`); and a row of failures in AUTOMAT's memory (`streak`) of
  the last `pending_days` (2) days. **Fail closed**: when the plan cannot read GitHub the list is
  `unknown` (also when it is missing; nothing pending is `none`), and the background pauses; real work
  never waits for it (the drill's tick and the reviewers' budget, `ai-review.yml`, do the same). Every merge of the automation ends its branch's row
  (`tools/automat-memory.py merged`, also with no AI fix). A row whose branch has no open pull request
  and whose newest pull request was closed strictly after the row's last failure (full times: the row
  keeps the time of its last failure, `at`) is left out of the priority: `closed` (run by `automerge.yml`
  on each of its runs) only marks the row, never deletes it, so the count of failures in a row
  that `tools/automat-help.py` reads stays; a new failure clears the mark. The long-lived branches
  (`automation/autofix-main`, `automation/daily-maintenance`, `automation/audit`) are never closed: a
  broken `main` whose fix is retrying stays pending. The writers of the data branch (the automatic fix's
  record, the merge's) wait in no concurrency group (GitHub cancels a waiting job when a third arrives):
  each makes its record from the branch's newest commit, writes only what changed, makes it again when
  its push is not a fast-forward or the branch could not be read (six tries), and warns when it could
  not;
- **only in the provider's leftover window** (`leftover_window`): the last `release_hours` (3) hours
  before its own reset, never while its day has more than that left. For a reset a person verified, the
  provider's own reset header, when it gave one, counts more than the data file (a reset it gave that is
  already past is rolled forward by whole days). One not verified is more
  careful: the later of the data file's reset time (its `"reset"`, even unverified) and the header's, and
  never during the real day's `maintenance_window` (04:00-12:00 UTC: the security tests, the daily check
  and candidates and their automatic fixes). Then they may use **everything left**, with no margin: the
  provider's own limit is the only one.

A paused or early fix ends "budget", which is "deferred": it waits like any fix that found no free
provider, and nothing is lost. A background fix is not started either when its reviewers have nothing
left for it. **Each provider's use is counted on its own day** (`provider_day`: the date its day began in
its own zone; Gemini's day ends at midnight in California, the others' at midnight UTC), so what is
"left" is what is left of the provider's own day. **A quota answer (429) to work of class 3 or 4 never
spends the provider for classes 1 and 2** (`spent_low`): real work still asks it; money asked (402) spends
it for everybody.

**Not verified**: none of the four reset times could be checked on 2026-11-24 (the providers' pages could
not be reached); each says so (`"verified": false`) with what it rests on. So today the background takes
Groq's, Z.AI's and OpenRouter's leftovers in 21:00-24:00 UTC, and none of Antigravity's: its last hours
(05:00-08:00 UTC, midnight in California) fall in the maintenance window, so its leftovers wait until a
person checks its reset and sets it with the date.

**OpenRouter: one budget for all its free models.** Every `:free` model counts against one daily cap
of the account, never one per model (`"shared_free_models": true`; the budget's provider is
"OpenRouter", whatever the model). At the start of each run that holds the key (the reserves, the
reviewers) `GET https://openrouter.ai/api/v1/key` (`tools/ai-providers.py` `OPENROUTER_KEY_INFO`) is read
with the key, following no redirect, for `is_free_tier` only (`account_tier`): the documented cap (50
requests a day, as remembered, not verified) always stays; when the account is not on the free tier the
signing notice says "OpenRouter account is not free tier". Money in the answer (usage, limit: credits) is
never read as requests. The count of the day comes from OpenRouter's own headers and its 429
"free-models-per-day". Which models are used is unchanged.

**The drill respects it** (`tools/automat-drill.py`, `automat-drill.yml`, every three hours): its report
says whether the drill may use the free AIs now, gets the providers' leftovers, or is paused for real
updates (naming them, read from the open pull requests too); the tick starts a drill's fix the budget held
back again (`autofix.yml`, work `run/<id>`) only when background work may run, no automatic fix runs or
waits, the failure is at least two hours old, once a day per failed run (the plan's attempts per day still
count). The signing notice shows, per provider, what real work and the background used today.

**Antigravity and the background**: one session of the agent counts ten requests of Gemini's twenty a day,
so a class 3 or 4 session fits only when real work left that much; it then waits like any other.

### No deadlock of the free quotas (2026-11-25)

A real jam, found on 2026-11-25: PR #111 (`automation/update/lists-2026-11-22`) was "retrying", yet for
three days no attempt landed, because every provider was skipped for a reason of its own and so nobody
was ever asked: Antigravity by the rotation (the attempt started with Z.AI), Z.AI as "spent today" (a
429 of **concurrency**, Z.AI's code 1302, was one of its "day words"), OpenRouter by the reviewers'
reserve (no other provider had room for a review that day), Groq because the request (7,678 tokens) was
larger than its limit of 6,000 tokens a minute, which no later day could change. The owner's rule is
that nothing stays behind, so none of these may hold forever. What changed (`tools/ai-quota.py`,
`tools/ai-quota.json`, `tools/autofix-reserve.py`, `tools/autofix-agent.py`; the proofs, with a drill
of that day's four reasons, are `tests/test_automat_deadlock.py`):

- **A request is fitted to the provider's minute** (`fitted`, `compact_message`): when it is larger than
  the provider's limit of tokens per minute, it is made smaller, deterministically: the rules stay
  whole; the end of the failure and the plan's notes (the reasons earlier fixes were refused among them)
  each keep their share; the names of the files to change, and whole files to change while they fit; the
  code around the failure takes what is left; the answer may shrink to `MIN_ANSWER` tokens. Only when
  even that cannot fit is the provider skipped, with that reason ("even the smallest request ...").
  A follow-up of the inner loop is fitted the same way. A provider that answers 413 or 429 with its
  limit per minute ("Limit 6000") teaches it (`learned_minute_tokens`): it is kept in the day's record
  and the request is fitted to it and asked again.
- **A 429 says which limit** (`rate_limit_scope`): the day's quota only when the provider says so in its
  words and not of a minute, when its own headers say nothing is left of its day, or when it asks to
  wait more than an hour; a limit per minute, of concurrency or a busy service (`minute_words`, and for
  Z.AI its codes 1302 and 1305, matched only as its `"code"`) is waited out and asked again in
  the same run (at most `MINUTE_RETRIES` times, each wait at most `MINUTE_WAIT` seconds). When nothing
  says which, it is a minute: one more request tomorrow costs less than a provider lost for a day. A 503
  is asked again after 5, 15 and 45 seconds (`BACKOFF`, or its own short `Retry-After`).
- **The reviewers' reserve has a way forward** (`Budget.way_forward`): when the reserve alone would leave
  every provider unasked, a second pass asks the one whose fix leaves the most reviewers with room today
  (the attempt's order breaks a tie). The fix is written now and **its two independent reviews come on a
  later day**: the reserve only decides when, never whether. The verified merge still requires the
  status `ai-review` of two (three for tier B) independent providers on that very commit, so the fix
  waits on its branch, and the review is asked again every day until it comes. The fix's summary
  and the status of the run say so (`reviews_deferred`). Never for background work (classes 3 and 4
  simply wait), and never when fewer providers than the reviews need could ever review it (a key, not
  marked unavailable). A review now counts within the provider's own minute (`review_size`): Groq, with
  6,000 tokens a minute against the reserve's 9,000, never counted as a reviewer.
- **The rotation never skips the only provider with room**: a later attempt still starts with the next
  provider, unless no reserve can be asked (now, or with its reviews later) and Antigravity can: then
  Antigravity goes on. Not rotated, Antigravity keeps the reviewers' reserve as before while a reserve
  can be asked, and takes the way forward itself only when none can.
- **The watchdog** (`ran --component`, `days_unasked`, `stuck_text`): each run of the automatic fix
  records its branch as asked or unasked for the day in `quota.json`; a branch that asked nobody for two
  days in a row (`UNASKED_DAYS`) is said plainly, in Italian, in the reserves' message (which reaches the
  pull request), as a warning of the run, by `ai-quota.py show`, and in bold in the signing notice
  before the updates still being retried. Nobody is mailed for it. A run whose attempt started with a
  reserve (rotated) and asked nobody now counts as a day with no provider too.

- **The stall of 2026-11-25 afternoon** (run 45625320020, PR #111 again): Z.AI was still "spent today"
  from a mark written before the reading of its codes was fixed, and every OpenRouter model failed: five
  answered 429 (the run waited 61 s on each, model after model, as if the whole account were blocked) and
  the reasoning models gave no text ("no JSON object in the answer"). It was **not** the account's privacy
  setting: that answers 404 "No endpoints found matching your data policy", which the reserve says
  plainly (`DATA_POLICY`). What changed: a mark "spent today" carries the time it was written
  (`spent_at`) and is **checked again with one request after `SPENT_RECHECK` (3 hours)**; a mark with
  no time (written before this rule) holds for its day as before; only "it asked for money" never expires (`mark_expired`). A 429 of one
  free model's pool upstream (`model_words` in `tools/ai-quota.json`: "rate-limited upstream") moves to
  the next model at once and holds back none of OpenRouter's other models (`per_model`). Every error now
  shows the provider's own words in the log (`error_words`, URLs and keys removed), so the next stall
  says which limit it was. OpenRouter is asked for little reasoning, not sent back
  (`"reasoning": {"effort": "low", "exclude": true}`), and an answer cut off before its text says so
  (`cutoff`) instead of "no JSON object".
- **The reasoning that left no answer** (2026-11-27, run 45983654916, PR #111): with the stall gone, nine of
  eleven free models were asked and almost all were cut off, their whole answer spent on reasoning. Each
  provider is now asked for little reasoning with its own parameter, and a model cut off is asked once more
  with its reasoning off (`reasoning_params`: OpenRouter `reasoning.effort` "minimal", then "none"; Z.AI
  `thinking: {"type": "disabled"}`; Groq `reasoning_effort` "low" for gpt-oss, "none" for Qwen 3.8 27B;
  read on each provider's page that day). A model whose reasoning is mandatory refuses "none" (HTTP 400):
  the next model is asked.
- **Gemini's real quota, learned** (2026-11-25): Google publishes no numbers for the free tier ("can be
  viewed in Google AI Studio"), so `requests_per_day` of Antigravity in `tools/ai-quota.json` is an
  estimate. Gemini's 429 names the limit it hit and its value (`google.rpc.QuotaFailure`: `quotaId`
  `GenerateRequestsPerDayPerProjectPerModel-FreeTier`, `quotaValue`): `learned_quotas` reads it,
  `Budget.learn` keeps it for the rest of the provider's day as its day limit of requests (and a
  `PerMinute` token limit as its minute), from the reviewers' calls and from Antigravity's errors alike.

**From the providers' own pages** (read on 2026-11-25 on each provider's own page or code: every
provider in `tools/ai-quota.json` has `source_urls`, `source_verified_on` and a `signals_source` or
`words_source` that says what each value rests on). `source_verified_on` is the day the value was read
on the provider's page. It is not a person's check, so `"verified"` stays `false`: the file's rule is
that a person verifies a number.

- **Gemini** (`ai.google.dev/gemini-api/docs/rate-limits`): limits are per project, not per key; the
  requests of a day reset at midnight Pacific; no free numbers are published for the text models any
  more (careful values stay). Which limit a 429 is comes from Google's own gemini-cli code, not from
  the documentation: a quotaId with `PerDay` or `Daily`, or `limit: 0`, is the day, read before a
  short retryDelay; a retryDelay over 300 seconds is the day too (`day_wait_seconds`). The new
  Interactions API names them (`rate_limit_exceeded`, `too_many_requests`: a minute; `quota_exceeded`:
  the day). `MODEL_CAPACITY_EXHAUSTED` is a busy model (the next model).
- **Groq** (`console.groq.com/docs/rate-limits`): `openai/gpt-oss-120b`, `openai/gpt-oss-20b` and
  `qwen/qwen3.8-27b` take 30 requests and 8,000 tokens a minute, 1,000 requests and 200,000 tokens a
  day on the free plan, per organisation; `x-ratelimit-*-requests` is always the day's,
  `x-ratelimit-*-tokens` always the minute's; `retry-after` only on a 429. The wording of the 429's
  message ("per minute (TPM)", "per day (RPD)") is not shown on the official pages.
- **Z.AI** (`docs.z.ai/api-reference/api-code`): every limit is a 429 and only the string
  `error.code` tells which: 1302 (rate limit) and 1305 (overloaded) wait; 1308, 1309, 1310, 1311,
  1313 and 1314-1321 are not asked again today; 1113 asks for money. 1303 is not on Z.AI's list. The
  free models are `glm-4.7-flash` (200K of context, 128K of output) and `glm-4.5-flash`; no number of
  their limits is published.
- **OpenRouter** (`openrouter.ai/docs/api-reference/limits`): 20 requests a minute and 50 a day for
  all its free models together (1,000 a day only after 10 credits bought: none), failed requests
  count, the day ends at 00:00 UTC. The documented 429 says only `error_type: rate_limit_exceeded`,
  for a minute and a day alike; its `X-RateLimit-*` headers come only with a 429 (also inside
  `error.metadata.headers`) and are read as the minute's. `limit_source`
  (`openrouter_free_tier_per_minute`, `upstream_provider_shared_pool`: a minute;
  `openrouter_free_tier_daily`: the day) is shown only on OpenRouter's blog: not verified. A 404 "No
  endpoints found matching your data policy" is the account's privacy setting, not a quota and not a
  model that is gone: the message says so plainly and the other providers go on.
- **The default models** (`tools/ai-providers.py`): Antigravity and the Gemini API `Gemini 4 Hydrogen`,
  then 3.8 Flash, 3.6 Flash, 3.5 Flash Lite (Antigravity's free plan keeps only Gemini 4 Hydrogen after
  2026-11-30; a model that is no longer offered, `MODEL_GONE`, makes way for the next one instead of
  stopping the agent); Groq `openai/gpt-oss-120b`, `qwen/qwen3.8-27b`, `openai/gpt-oss-20b`; Z.AI
  `glm-4.7-flash`, `glm-4.5-flash`; OpenRouter rebuilt from its own list each run (see "Reserves" below).

## What runs by itself

| When | What | Workflow | Result |
|---|---|---|---|
| By hand (`gh workflow run automat-drill.yml --ref main`), every three hours while it runs | The AUTOMAT drill: a simulated major Qt release on `automation/update/drill-<name>`, fixed by AUTOMAT's real chain, never merged (no key, no AI here) | `automat-drill.yml` | The drill's pull request "DRILL: ..." and issue (label `automat-drill`), the report in the issue and the run's summary; at the end one comment naming the owner |
| Sundays, 03:17 UTC | The cleanup of the branches: those merged into `main` at their tip, fully contained in it, with no open pull request of them or based on them, older than seven days and not protected, each by compare-and-swap (no key, no AI) | `branch-sweep.yml` | The deleted branches listed in the run's summary ("The cleanup of the branches") |
| After every run of the two AI reviewers | Their use of the free quotas, added to the day's record (numbers only; no key, no AI) | `automat-quota.yml` | `quota.json` on the data branch `automat/memory` ("The budget of the free quotas") |
| After every run of the merge workflow | The notices "DEVI AIUTARCI CON CHATGPT" of the branches whose fix landed in `main` are closed with a note (no key, no AI) | `automat-help.yml` | The issue labelled `automat-help` closed |
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
| When the tests of `main` pass (after a merge by itself: when its Tests and Security pass), and every day at 08:13 UTC | A version in `main` that is not published yet, with `tests` and `sandbox` green on its last commit | `release-ready.yml` | An issue "LA RELEASE E' PRONTA DA FIRMARE: I.K.E. <version>" (until 2026-11-22: "C'E' UNA NUOVA RELEASE IN MAIN PRONTA DA PUBBLICARE!!!"), its first line the same words and right under it the one command, in `bash -c '...'` so it is the same in fish, with the exact command, assigned to the owner and naming the owner (GitHub mails it), listing what was merged by itself since the last release (fully verified, so the owner knows what the signature covers); a reminder comment each week; closed by itself once the version is published; never opened again for a version whose notice the owner closed |

### The tests in parallel jobs (2026-11-24)

The owner's priority (AUTOMAT block 1, step 1): one round of `tests.yml` took
about 40 minutes and one of `arch.yml` 70 to 90; nothing of the chain above
can go faster than its tests. Since 2026-11-24 both split the suite across
parallel jobs, with no test lost and no gate weakened:

- `tools/shard-tests.py` splits it by whole test files, balanced by the
  durations in `tools/test-timings.json`, the same way for the same files;
  each file in exactly one shard. The number of shards is `SHARDS` at the top
  of each workflow (4), for the sources and for the installed package each.
- `tests.yml`: `tests shard k/N` (the suite on the sources), `tests installed
  k/N` (the suite against the package of `tests package`, checked by its
  sha256 before any test runs), `tests checks` (lint, the licences, the Rust
  tests, the test that must fail, "No tests lost", the filter lists, "Nothing
  gets worse", once per commit), `tests of the starting commit` (on the
  automation's and ChatGPT's branches) and **`tests`, the gate**: main's
  required check, the job `publish.py`, `release-ready.yml` and the verified
  merge read. It runs whatever happened before it, and passes only when every
  job passed and every test pytest collects (an independent collection in
  `tests checks`, and each shard's own) ran exactly once across the shards
  (`tools/shard-tests.py verify`: a test missing, run twice, run in the wrong
  shard or not collected, a shard missing, failed, cancelled or of another
  commit all fail it; passed, failed and skipped all count as run). The steps
  `tools/test-categories.py` reads keep their names on the job `tests`:
  "Tests" and "Tests of the installed package" are the gate's completeness
  checks, and every other one ("Lint", "Licences", "No tests lost", "Arch
  package", "Nothing gets worse"...) restates the outcome of that very step in
  the job that ran it (skipped there, skipped here: not verified). The gate
  writes the run's `test-results` (the merged `junit.xml`,
  `junit-installed.xml`, `summary.json`, "Nothing gets worse"'s report) as
  before, and only from every shard's results.
- `arch.yml`: in Arch's container, `Arch Linux shard k/N`, `Arch Linux
  installed k/N` (each builds the package with makepkg and installs it with
  pacman) and `Arch Linux styles` (the widget styles, an independent
  collection of the tests, and the record `arch-versions` of the daily check);
  the engine's crates and build are kept in GitHub's cache by `Cargo.lock`, its
  sources and the Rust compiler. Every part installs the same packages: the job
  `Arch Linux plan` picks one day's snapshot of Arch's repositories in the Arch
  Linux Archive (today's when it is there, else yesterday's; with
  `[core-testing]` and `[extra-testing]` for `arch-testing.yml`), every part
  reads the package databases from it alone and takes the packages from Arch's
  mirrors while they still have that version, else from the archive (when the
  archive does not answer, Arch's mirrors as they are, with a warning). The job
  **`Arch Linux`** is the gate, as above, and also fails when the parts did not
  all record the same Arch packages, or a part's record is missing.
  `arch-testing.yml` calls it as before.
- What a shard records and the gate checks (`shard.json`): the commit, the run
  and its attempt, the installed copy tested and the package's sha256; the gate
  refuses results of another commit or run, an installed shard with no
  installed copy or with another package than "tests package"'s, a source shard
  that tested an installed copy. The installed shards are held to the same
  independent collection as the sources. A shard whose files are all skipped
  whole at collection passes (pytest's "no tests"), and their skips still count.
- The automatic fix (`tools/autofix-plan.py`, `GATES`, `without_gate`,
  `gate_alone`): when a part failed, the gate's failure only says so again and
  is set aside; the plan reads the part's failed steps and log, so a test that
  failed once in a shard runs once more before any AI, and a runner's or
  pacman's failure in a part is an issue, as with the one job of before. When
  the gate failed alone (a part cancelled or out of time, results missing, a
  test that did not run exactly once, the Arch parts on different packages) it
  is never an AI's: the whole run once more (`gh run rerun` of every job), then
  an issue. A cancelled run is not handed over (`!cancelled()`) and the plan
  skips it.
- Refreshing the durations (they only balance the shards; the gate checks
  completeness whatever they say): download `test-results` of a green run and
  `python3 tools/shard-tests.py timings --junit junit.xml --junit junit-installed.xml`.

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
Dark Reader (`tools/build-darkreader.py`: the proxy taken out of the engine,
I.K.E.'s speed patches, `PATCHES`, each of which must find its text, its
"anchor", exactly once, and the checks of "Dark Reader's builder: the rules
of every update" below) and uBlock Origin's scriptlets
(`tools/build-ubo-scriptlets.mjs`: `builtinScriptlets` of
`src/js/resources/scriptlets.js`, read with Node.js). Since 1.1.20 (the
owner's decision) `tools/check-components.py` keeps two kinds of trouble
apart:

| What happened | Called | What it does |
|---|---|---|
| An upstream source could not be read: the network, crates.io, PyPI, npm, GitHub, `git clone`, npm's hash that does not match | **source unreachable** | Infrastructure. The report's row says "check failed: source unreachable: ..."; `--apply` applies **nothing** and exits 1 (fail closed); the maintenance's check step fails and the automatic fix opens "GitHub or the runner failed: Daily maintenance candidate", no AI. The next daily run tries again. |
| The new version was downloaded, but I.K.E.'s builder does not accept it: the proxy or `injectProxy` is not where it was, the npm package is laid out differently, the site fixes do not start with the common fix or hold what could be a script, a link a person must judge, a changed network call, the API of I.K.E.'s Dark Reader panel gone, a result that does not parse (Dark Reader's speed patches no longer stop it since 2026-11-24: see below); uBlock Origin's library moved, the builder stopped, found no scriptlets, or a scriptlet needs an entry the library does not have | **builder refused**: a component incompatibility | That component **stays at the version in use, with I.K.E.'s changes** (never replaced by the unpatched upstream). Every other component is still applied and tested (the crates' security updates included); `--apply` exits 0. The report has a section for the owner, and since 2026-11-22 the builders' path starts (below): an AI may re-anchor the existing patches on `automation/builder/<id>` only; the guard refuses `tools/build-*` to every other run. |

**How to read the report** (the `components` issue, the run's summary, and the
maintenance candidate's pull request when other components changed). The
issue is titled "Component incompatibility: a builder refused a new upstream
version" and names the owner in a comment when it first appears. Its table
marks the component "**refused**", and the section "Component incompatibility"
gives:

- the component and its versions, in use -> new (for Dark Reader the engine
  version and the lists' commit; for uBlock Origin the commits);
- the step that refused: for Dark Reader the proxy / `injectProxy` / the site
  fixes, the links check, the network calls check, the panel's API or the
  parse check; for uBlock Origin the builder;
- the reason, as the builder said it;
- "The new upstream version around the anchor": the anchor's lines no longer
  found, and the new engine's lines (numbered) around the first anchor line
  still there, or every place where the anchor is now found twice; for
  uBlock Origin what the new checkout has where the builder looks (the file
  and its exports, or the files next to it);
- the builder's log.

**Dark Reader's builder: the rules of every update** (the owner's decisions
of 2026-11-24; the comment at the top of `tools/build-darkreader.py`). Dark
Reader keeps updating by itself; after every update the builder:

| Step | What it does | When it stops (builder refused) |
|---|---|---|
| The proxy change (`PROXY_BLOCK`, `PROXY_EVENT`): the style-sheet proxy asked for by an event with the session's token, never an inline script | Made | Always when it cannot be made: without it Google's sites break, or a page could start the proxy. Not a speed patch |
| The speed patches (`PATCHES`) | Each family is made when all its texts are found exactly once. A family that no longer fits is **left out**, with the families that need it (`PATCH_NEEDS`), and the update ships without it: the builder prints "speed patch left out: ...", `darkreader-data.json` records it (`"ike_build"`, written only when something was left out or removed), and the daily report's note, so the candidate's CHANGELOG line and the signing notice, name it | Never |
| Links in `darkreader.js` and `darkreader-proxy.js` | Kept: the links of `LINKS_ALLOWED` (each with its reason: Dark Reader's site and MIT licence in its notices, `https://fonts.googleapis.com/` compared with a sheet's address, the SVG / XLink / XHTML namespaces) and a bare scheme the code compares with (`https://`, `moz-extension://`). Removed: any other link in a comment; a link of a denied kind in a string (the string becomes `""`) or in a template literal (only the link goes). Denied kinds (`LINK_DENY`): donation (Patreon, Open Collective, PayPal, Liberapay, Ko-fi, Buy Me a Coffee, GitHub Sponsors, "donate" pages), social (X / Twitter, Facebook, Mastodon, Reddit, YouTube channels, Discord, Telegram ...), news / blog / "what's new", analytics / telemetry, advertising | An unknown link in a string or template literal; a denied link the code compares with or looks up (removing it would change what the code does); a link the reader cannot place |
| Network calls (`NETWORK_CALLS`): fetch, XMLHttpRequest, sendBeacon, WebSocket, EventSource, importScripts, counted in the code (4.9.135: fetch 4 times, nothing else) | Counted | A new kind or another count: a person reads the new call, then updates `NETWORK_CALLS` |
| The API of I.K.E.'s Dark Reader panel (`PANEL_API`): `enable(theme, fixes)`, `disable`, `setFetchMethod` and the theme's fields (brightness, contrast, sepia, grayscale, mode, useFont, fontFamily, textStroke, the dark and light scheme colours, scrollbarColor, selectionColor) | Checked | Any of it gone (the panel and `darkmode.js` would break) |
| The site fixes (`darkreader-data.json`): CSS put in a style element, selectors, flags. Sites' own image and font addresses in the CSS are allowed: they are the sites' assets, and this list is not scrubbed | Checked: no field but Dark Reader's, nothing but text | Anything that looks like a script (`DATA_SCRIPT_MARKS`: `<script`, `</style`, `javascript:`, `expression(`, `-moz-binding`, `behavior:`, an HTML or script `data:` address, `onload=` / `onerror=`): in Chromium none of the list can run as a script, and this keeps it so |
| The result | Read again by the builder's own reader of scripts (`lex`): removing links must leave the same code; and `node --check` (when Node.js is there, as in the daily check) must accept the files whenever it accepts Dark Reader's own engine | When either says no |

A build that stops writes nothing: the Dark Reader in use stays, nothing
breaks, and the refusal waits for Claude or a person (the daily report says
which step; the builders' path below cannot fix these steps, only anchors).
Dark Reader's unused message types `MARK_NEWS_AS_READ` / `MARK_NEWS_AS_DISPLAYED`
are left in: names of an enum, no link, nothing calls them, and removing them
would need one more patch to keep anchored. `tests/test_darkreader.py` proves
the rules: injected links of each kind (removed or stopping), a speed patch
whose anchor is gone (left out, the others made, the script still parses), the
proxy's anchor gone (stop), the panel's API, the site fixes, and the real
engine made again from the shipped one, rebuilt byte for byte; a guard checks
that the shipped `darkreader.js`, `darkreader-proxy.js` and `darkmode.js` have
only allowed links. Pages whose Content-Security-Policy refuses added `<style>`
elements (archlinux.org) are handled in `darkmode.js`, not by a patch: a
`<style>` made in I.K.E.'s isolated world whose sheet the policy refused is
given to the page as a constructed style sheet with the same rules
(`tests/test_dark_csp.py`); it works on the DOM Dark Reader uses (its
`<style>` elements, their `sheet` and `textContent`), so an update of Dark
Reader needs nothing for it.

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
  owner's decision of 2026-11-21): no patch can come in this way. Since
  2026-11-24 a speed patch that no longer fits does not refuse the update
  (it is left out, above), so this path starts only for a refusal; a left-out
  patch is brought back by re-anchoring it under the same rule;
- uBlock Origin (`tools/build-ubo-scriptlets.mjs`): only the path of the
  library it imports (a file under the checkout, ending in `.js`).

The re-anchored builder then runs: `daily-maintenance.yml` (mode `builder`)
applies the update on that branch with it (for uBlock Origin the builder
itself refuses a library that is not there; for Dark Reader an anchor found
not exactly once leaves its family out, said in the note), and its tests prove
the result: `tests/test_darkreader.py` checks that the shipped engine is Dark
Reader's own npm engine with exactly I.K.E.'s changes but the families
recorded as left out (byte identity) and only the measured families, and the
Dark Reader cost test runs with the whole suite. A builder
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
  ships (noto-fonts, noto-fonts-cjk,
  plasma-integration, intel-media-driver, libva-nvidia-driver);
  `tests/test_optional_deps.py` has one case per optdepends entry of the
  PKGBUILD: where the package is installed, pacman finds all its files and
  what I.K.E. uses of it works (a Noto CJK font,
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
  Qt's `QDesktopServices`, which `ike/` no longer calls since 1.1.24), each
  mapped to its Arch package (`TOOL_PACKAGES`; I.K.E. itself starts none for notifications since 1.1.24: they are a D-Bus call); the desktop's own
  openers that `ike/handoff.py` starts only when no desktop portal answers and
  only when installed (`kioclient`, `gio`, `exo-open`: `DESKTOP_TOOLS`) are
  listed as the desktop's, not as dependencies (1.1.24: xdg-utils, whose Arch
  advisory AVG-1420 has no fix, is no longer used or declared);
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
| retrying | AUTOMAT (2026-11-22): it could not be finished today and is tried again every day, with its tries or days: the automatic fix used its attempts of the day or could not, a check or the reviewers refused its change, a builder refused, a dependency is not declared yet, checks passed but a category is not verified. One informational note after `RETRY_NOTE_DAYS` |
| needs-person | only what the owner's own rules keep for the owner (YouTube's rules, uBlock Origin's own resources) and entries written before AUTOMAT. Until then: a builder refused it and its re-anchoring is not there yet, a pin of a workflow until its candidate exists (an AI's change of a workflow is only a proposal), a dependency used but not declared (until the PKGBUILD's candidate), the automatic fix reached its cap (`FIX_ATTEMPTS`: the branch is kept, the owner told once), or checks that passed but left a required category not verified |
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
| `protection-dropped` | possible security regression | yes (not for `ENGINE_LIMITS`) | a blocking rule with an option that protects (`removeparam`, `csp`, `redirect`, `redirect-rule`, `permissions`, `header`, `urlskip`, `uritransform`, `inline-script`, `strict1p`, `strict3p`, `ipaddress`, `denyallow`, `to`, `method`, `popup`, `popunder`) that the engine drops or reads differently |
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

**Engine limits are not given to an AI** (2026-11-27, PR #111). `ENGINE_LIMITS` in `tools/filter-lists.py`
names the engine's reasons that no change of I.K.E.'s adapter can fix; such a finding keeps its class but gets
no AI analysis. The first: "csp with content type" (adblock-rust refuses `csp=` with `$doc`; the adapter may
not drop an option, and I.K.E. applies no `$csp` rule at all, since Qt WebEngine cannot add a response header).
PR #111 was an AI's guess at it: a helper nothing called and a function put inside a class; the static guard
refused it. Such gaps are Claude's work (an engine update, or a browser feature with the owner).

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
`MAX_ATTEMPTS` (2) analyses on one branch, a person. The run never opens the
"ATTENZIONE..." issue: the ledger is where a person reads it.

When the analysis' change makes the branch's **Tests** (or Arch Linux) fail,
the automatic fix takes that failure like a full chain's candidate
(2026-11-22; until then the plan skipped it and PR #111 waited for the
`TESTING_DAYS`): `tools/autofix-plan.py` plans a fix of the same
`automation/update/lists-<date>` (that exact name only) from its tip, in the
same **lists mode** (the guard's `--lists`, the adapter only; the recorded
rules are already on the branch), each attempt with a fresh context, the
earlier change and the new logs, and the next free provider first. The
analysis itself is attempt 1 (its `autofix:` commit); after `FIX_ATTEMPTS`
(4) a person is told by the "ATTENZIONE..." issue and the branch is kept.
Those runs report to the finding's entry by its branch
(`tools/ai-work.py`): a new change keeps it "testing" and the
`TESTING_DAYS` count again from it; the cap makes it "needs-person".

### Free AI providers, checked every week (WP9)

**New models found by AUTOMAT itself** (block 2, 2026-11-27; the owner: AUTOMAT keeps up with the providers and
updates the models' names by itself). The weekly check also reads each provider's own list of models (Gemini
API `GET /models`; Groq and Z.AI `GET .../models`), leaves out what is not text (embeddings, images, speech,
guards) and asks up to `TRY_NEW` new ones per provider a tiny question on the key, newest version first
(`tools/provider-check.py` `discover`). The keys have no billing, so a model that answers is free there;
Gemini's 429 with "limit: 0" says the free plan has none of it (recorded as not free, never used). The models
that answered reach the automatic fix as `AUTOFIX_DISCOVERED` (`provider-check.py discovered`, read by the
plan of `autofix.yml` from the weekly artifact) and are asked **after** the configured ones: the reserves
(`chain`), Antigravity (`models`, in the CLI's form "Gemini 5 Flash (High)") and the Gemini reviewers.
A configured model its provider no longer lists is said in the weekly issue, with the new free model that
replaces it meanwhile; Claude then updates `tools/ai-providers.py`. OpenRouter rebuilds its free list at
every run already. Not found by this: a model only Antigravity's CLI offers (it has no list), and a
provider's change of its free plan that keeps the model listed (the answers' billing errors still mark it).

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
   models in the variable `AUTOFIX_GROQ_MODELS`, default `openai/gpt-oss-120b`,
   then `qwen/qwen3.8-27b` (a preview that may vanish at short notice), then
   `openai/gpt-oss-20b`; its free plan takes 8,000 tokens a minute, so it gets
   only the failure and the code around it, fitted to its minute), then Z.AI
   (`ZAI_API_KEY`, models in `AUTOFIX_ZAI_MODELS`, default `glm-4.7-flash`
   then `glm-4.5-flash`, Z.AI's free GLM Flash models, another family than
   the others, with the whole files too; added in 1.1.19, the owner's
   choice; its free limits are shown only in the account), then OpenRouter
   (`OPENROUTER_API_KEY`, models in `AUTOFIX_OPENROUTER_MODELS`, default
   `particle-ai/particle-1:free`, `nvidia/nemotron-3-ultra-550b-a55b:free`,
   `inclusionai/ling-3.2-flash:free`, `google/gemma-4-31b-it:free`, which also
   get the whole files). Since 2026-11-25 each run rebuilds OpenRouter's list
   from OpenRouter's own `GET /api/v1/models` (`refreshed`): the listed models
   that are still there at zero price, then the two free models with the
   largest context it offers now, then the Free Models Router `openrouter/free`
   as the last resort (it picks a free model at random and falls back only to
   free models). Never a paid model and never a paid fallback. When the list
   cannot be read, the configured models are asked as they are, and a listed
   model that answers 404 still brings in the free models of the moment. Each reserve's fix goes through the same checker
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
   `automation/update/arch-testing-<date>`, and since 2026-11-22 the filter
   lists' `automation/update/lists-<date>`, in lists mode) a failure is fixed up to
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
   `FIX_ATTEMPTS_MAIN` (two), Antigravity first each time. (Until 2026-11-22
   the plan stopped the isolated candidates at that cap of two as well.)

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

### The cleanup of the branches (2026-11-24)

GitHub's setting "Automatically delete head branches" does not fire for a merge made by
`github-actions[bot]`, so the branches the verified merge merged stayed. Two parts, one list of what
is protected (`tools/branch-sweep.py`, `PROTECTED`; proofs in `tests/test_branch_sweep.py`). Every
deletion is a compare-and-swap: `git push --force-with-lease=refs/heads/<ref>:<sha> <repo>
:refs/heads/<ref>` with the job's token (in the environment, never on the command line), so GitHub deletes
the branch only if it still points at the commit that was judged; never an unconditional delete.

- **Right after the verified merge** (`tools/automerge.py`, `delete_head`, the last step of
  `merge_it`): the head branch it merged is deleted, only an isolated candidate of the full chain
  (`automation/update/<id>`, `automation/builder/<id>`; never a drill's) of this repository, and only
  while its tip is still the merged commit (a branch that moved keeps its new commits). The workflow's
  own token, with the `contents: write` the merge already has. `automation/autofix-main` is the
  automatic fix's long-lived branch and stays, as `automation/daily-maintenance`, `automat/memory` and
  everything else. Any error is caught: it never fails or undoes the merge, the steps after it (AUTOMAT's
  memory, the other pull requests judged again) always run, and the weekly sweep takes the branch later.
- **Every week** (`branch-sweep.yml`, Sundays 03:17 UTC, or by hand; `contents: write` and
  `pull-requests: read` only, from `main`): a branch is deleted only when a pull request of it was
  merged into the default branch at exactly its tip (its head, its commit and its base all match), its
  tip is fully contained in `main` (GitHub's compare: `ahead_by` is the integer 0), no pull request of it
  is open (from any repository) and none is based on it (the base of an open pull request stays), its
  tip is older than seven days, and it is not protected: `main`, `automat/memory`,
  `automation/autofix-main`, `automation/daily-maintenance`, `automation/audit`, the multiplatform
  archive (`windows/port`, `windows/engine`, `linux/packages`, `linux/flatpak`,
  `linux/distro-checks`, `docs/multiplatform-plan`), `experiment/file-workers`, any branch GitHub
  itself protects. A `release/*` branch follows the same rule: it stays until its pull request is merged
  into the default branch, then goes like the others. **A branch with commits that are not in `main` is
  never deleted**, whatever its age (an open candidate, a drill's record, the archive). At most 100 go in
  one run, and every deletion is listed in the run's summary (with what was kept and why); what went
  wrong is said on the run's page: a sweep that could not run is an `::error` naming why (and the summary
  says it), branches not deleted, or not judged because of an error or because GitHub could not be read, a
  `::warning` naming them (with the reason). Automatic, the
  owner's decision; a person can see what it would do with `python3 tools/branch-sweep.py sweep --repo
  OWNER/NAME --dry-run`, and `python3 tools/branch-sweep.py protected REF` says whether a name is
  protected.

## Nothing gets worse

The verified merge has no person reading the change, and tests can miss a
subtle weakening. So every commit is also measured against `main` (since
2026-11-22): the step **"Nothing gets worse"** of `tests.yml` (the category
`no-regression` of `tools/test-categories.py`, required for every kind that
changes what reaches users: I.K.E.'s own code, so every AI fix and security
fix, the AdBlock engine and its crates, the Dark Reader and uBlock Origin
scriptlets builders, the filter lists, the PKGBUILD). It checks out `main`'s
current commit (on `main` itself, the commit before) in a second worktree,
gives it its own AdBlock engine, and runs `tools/no-regression.py` **from
`main`'s copy**, with `main`'s copy of the inputs, on both commits in the same
job: a candidate never judges itself, and both are measured the same way.

What is measured, offline (a local server and proxy, nothing leaves the
computer) and without a display, with the real browser of each commit:

- **Ad and tracker blocking.** 100 fixed requests
  (`tests/data/no-regression/corpus.json`: ad networks, trackers, malware,
  cookie notices, YouTube's ads and telemetry, the home network, HTTPS and
  tracking parameters, the hands-off sites) through I.K.E.'s own request check
  at all five levels, with the eleven default filter lists replaced by small
  local fixtures (`tests/data/no-regression/lists/`); 20 elements of three
  pages loaded in the engine (element hiding and the pages' scriptlets); the
  scriptlets of the video sites; the element-hiding rules of seven addresses.
  Worse: a request blocked on `main` and allowed here, an element hidden on
  `main` and shown here, a rule or scriptlet lost. YouTube is only read:
  nothing here changes its blocking. A request newly let through passes only
  when the **filter list data** that decides it changed: an engine built from
  the lists alone (not I.K.E.'s own rules) names the rule that blocked it on
  `main` and the exception that lets it through here, with the list each comes
  from and a digest of each list; the rule must be gone from its list's new
  data, or the exception must come from a list whose data changed, and on
  `main` the lists themselves must have stopped it. The same list data with
  another result (an engine or code change) stays worse. The corpus's lists
  are `main`'s on both sides in `tests.yml`, so there a request newly let
  through is always worse; the rule applies to snapshots measured with
  other list data (`compare`).
- **Fingerprinting surface.** What a probe page's scripts read at every level
  (navigator, screen, fonts, canvas, WebGL and WebGL2, audio by
  `getChannelData`, `copyFromChannel` and an `AnalyserNode`, `toBlob`,
  `convertToBlob`, `VideoFrame.copyTo`, matchMedia, Client Hints, workers
  (dedicated from a blob, shared, and from a file of the site), frames (added,
  made by `innerHTML` and from `srcdoc`, each with its card, extensions,
  sound, languages and cores), permissions, storage, battery, the `ike:`
  pages), in **eight sessions** at every level but Off (two there): each a
  page load with its own noise key, as a new start of the browser has, and
  once more with the first key (what is noised must read as it did then: a
  noise drawn anew at each load fails, `again.<value>`). The probe is served
  **on real-looking sites over https** (since the fourth review: an address
  of this computer told the code measured where it was, and every page was
  one site): random names under common top-level domains, through the local
  proxy, with a certificate of the run's own authority trusted in that
  profile only (`openssl`, `certutil`). A small page of the sites is read on
  six hosts per level: other sites must differ (two of them under `.co.uk`,
  a public suffix of two labels), two hosts of one site agree, every host is
  noised (`sites.differ.`, `sites.agree.`, `sites.noised.`); the frame's
  canvas must stay its page's (`frame.agrees.canvas`); a large space whose
  sessions all differ on main must not repeat (a noise drawn from a few
  keys). The probe's sizes, text and sound are random per check, the same on
  both sides. `check` gives both sides the same keys, sites and shape, all
  random. Each noised value is also read twice in
  the same session and in a frame of another site; the probe's canvas and
  sound are read on two starts with a fresh profile and the browser's own
  random key; and the whole probe once more on **another machine** (another
  time zone, language and screen size, 32 processors and 2 GB: a disguise
  equal to this computer's value, 4 cores or 8 GB, is told from the real one
  there, and one that gives way to more than 8 cores shows; its values are
  observations of their own, `fingerprint2/<level>/<value>`, worse where a
  part is that machine's real value and was not on `main`, or, for a part
  `main` fixes in all its sessions, comes closer to it; a pick, whose pool
  may follow the machine, the cores among 4 and 8 where there are 8 or
  more, gets the real-value test only, and a width or a list drawn per
  session is judged on the first machine's sessions). Since round 6 the
  page scripts are also measured in **a matrix of the users' common
  configurations** (`tools/env-axes.py`, one list for the probe and the
  static guard; the owner's direction of 2026-11-25: cover them up front,
  so the automatic fix needs no person for a condition on them). Its axes
  are:
  - scale 1, 1.25, 1.5, 2;
  - page zoom 90 %, 100 %, 110 %, 125 %, 150 %;
  - screens 1280 x 720, 1366 x 768, 1536 x 864, 1920 x 1080, 2560 x 1440,
    3440 x 1440 and 3840 x 2160, the window filling the screen;
  - no touch or a touch screen (5 points, a coarse pointer, no hover);
  - light or dark colours, reduced motion or not, forced colours (high
    contrast) or not;
  - English, Italian, German, Japanese;
  - the time zones UTC, Europe/Rome, America/New_York, Asia/Tokyo;
  - 2 to 32 processors, 4 to 32 GB;
  - the four protected levels.

  The sources are the public statistics of desktop screens and browsers and
  the Steam hardware survey (2025-2026): 1366 x 768 and 1920 x 1080 lead, and
  1536 x 864 is 1920 x 1080 at 125 %. GNOME and KDE offer these scales;
  dark colours, reduced motion and high contrast are accessibility settings
  of every desktop. The languages and zones are those of I.K.E.'s users.
  Every pair of two axes' values is in at least one session (a greedy
  all-pairs cover, about 50 sessions). Added to them are the corners: each
  level with every axis at its first value and at its last. The seed is the
  run's own, the same on both sides of a check, so different runs meet
  different triples.

  Each session is a page of its own in one browser run, with a noise key of
  its own (the run's keys in turn), so every one of the few values `main`
  draws appears. The engine's own emulation (its DevTools, on this computer
  only) gives:
  - the screen, its scale, the window and the orientation;
  - the colours, the motion and the contrast;
  - the time zone and the locale;
  - the processors.

  The browser gives the zoom. I.K.E.'s setting gives the languages. A small
  preloaded library gives the memory, read by each page's new process. A
  touch screen is a second browser run whose engine has the touch settings,
  because each navigation undoes the engine's touch emulation. The page
  reads its values twice: in the page, protected, and in a world of its own,
  where they are the real ones under that configuration. The languages are
  the configuration's own, since the engine itself disguises them at Strict
  and Maximum. A session's value is worse (`matrix/<session>/<value>`) where
  the page shows that configuration's real value, `main` did not, and `main`
  never shows that value at that level in any session, so neither a draw
  that meets the real one by chance nor a value `main` leaves real counts.

  The matrix adds about 30 s a side (two browser starts and about 20 s of
  sessions). What it cannot give on GitHub's runners: the graphics card's
  names (WebGL runs on the engine's software renderer, whose texts no switch
  changes) and X11 against Wayland (no display server; the engine runs
  offscreen). The static guard keeps refusing a condition on either. The
  other machine (32 processors, 2 GB, another time zone, language and
  screen) stays for the fixed disguises' `env.` marks. Since round 5 the page of the sites is also read on the hosts of
  well-known brands (`www.google.com`, `www.youtube.com`, ...; one mark per
  brand, `sites.brand.<read>.<host>`, for a protection switched off for
  sites named in a pattern), once more in the same page 100 s after its load
  at Balanced (`late.<read>`: a change deferred past the first seconds), and
  the probe reads a picture of 1024 x 1024 and a WebGL texture of 512 x 512
  (`canvas_large`, `webgl_large`: a noise that stops above some size). Every level is measured after the
  check of the fonts a page could find (`fontcheck.py`, which a start runs
  after 15 s and which changes every level's settings) has answered, as on a
  user's computer after the first start; no answer is an error. Since 2026-11-24 the values the
  protection disguises are judged by what protects the user, not by the
  number: the canvas (its picture, `toBlob`, a picture of known bytes at an
  offset, 896 stripes each of its own flat colour, the frame's and the worker's), the
  audio, WebGL (the card's name, its limits, extensions, and `readPixels` of
  a texture of known bytes), the navigator's identity (user agent, platform,
  cores, memory, languages, plugins...), the screen, the fonts, Client Hints,
  the time zone and locale, the media queries (`FP_JUDGED` in the tool). Each
  part of such a value is compared, in every session, with the **Off** level
  (the real value; `main`'s and the candidate's both count). A rule written
  against a weakening never lets it pass; what chance can produce is told
  from it by more readings, not by looser rules (the second independent review
  of 2026-11-24):
  - the real value in a session only as often as chance gives it: where
    chance never gives it (a picture's hash, a card's name not among the
    common ones), in no session where `main` never gave it; where it does,
    by how often it does as measured on `main` (a single text width: its
    noise has 61 steps, one of them none, measured on `main`'s 128 widths of
    every session; the extensions: each name left out about half the time,
    measured on `main`'s 24 draws, also for the worker's list, `LIST_PEERS`)
    and never more often than that leaves under 1 in 10,000 (`CHANCE`);
    where `main` gave it too (the cores, one of two), never far more often
    (an exact permutation test of both sides' sessions); never a hidden
    value readable, never the real text in a text or more of the real one's
    words than any of `main`'s readings had;
  - **drawn from a large space** (the hash of a picture or of a sound, random
    plugin names: `NOISE_PARTS`): still different with the session;
  - **drawn from a few common values** (`PICK_VALUES`, `PICK_PARTS`: the
    card's name and maker, the extensions, the cores, a text width): the
    page's own ones are read 24 times on each side (the 8 sessions and 16
    more keys on a small page, `PICK_DRAWS`); never the same in all of them
    where an exact permutation test of both sides' draws puts that under 1 in
    10,000 (`CHANCE`; the card's name the same 24 times is far beyond chance,
    its maker, one of two, is not);
  - **a list drawn per session** (the extensions, also the worker's; the
    plugins): as many names changed from the real list (the sessions' means,
    beyond chance: Student's t over 8 + 8 sessions at 5, `COUNT_Z`) and at
    least three different lists where `main` has them; a number drawn per
    session (not a pick), as far from the real one, the same way; read in
    fewer than three sessions, it cannot be judged;
  - **a fixed disguise** on `main` (the same in every session, away from the
    real value): no closer to the real value (a list shows no real name `main`
    hid and comes no closer, a number is no nearer); a new fixed value only
    when a person counts it among the common ones
    (`tests/data/no-regression/common-values.json`, `main`'s copy); and on the
    other machine it must not follow the real one (the `env.<value>` marks);
  - **the size of the noise** (`NOISE`), measured by the tool against Off's
    real values (the same on both sides, or it cannot be compared) on what the
    page hands over: pictures of varied known bytes (the page's, its
    `toDataURL`, the blob, the offset picture, the frame's and its
    `toDataURL`, WebGL's `readPixels`, the worker's), the flat stripes (the
    count of stripes changed), the text widths (the page's 128 and the
    frame's 64), the audio samples. For each, the mean change, the share of
    elements changed, and the share that differs **between sessions** (a
    noise drawn the same each time, or at the same places, has less); for the
    audio, the spread of the factors (a constant gain has none); for the text
    widths also the session with the fewest changed (`widths_least`: a session
    with no width noise, which a single width's real value cannot show beyond
    chance, fails here). Each must
    stay at least `main`'s less the tolerance of chance (four times the spread
    of two draws of the same noise: a false "worse" 3 in 100,000 per measure;
    at least 20 %, never more than 35 %, `TOLERANCE_CAP`: where it would be
    more, more is measured, as the 896 stripes) **and at least the floor** a
    person keeps (`tests/data/no-regression/noise-floor.json`), with no
    tolerance on the floor, so merges cannot lower the noise step by step.
    The floors are 0.9 of the lowest `main` measured (0.8 for the flat
    stripes, whose count varies most); a floor written as anything but a
    number above 0 is an error, and the report says when a floor is under 60 %
    of `main`'s noise (a stronger noise merged: a person raises the floor);
  - **marks** that must stay true where they are on `main`: `<value>.noised`
    (it differs from Off), `stable.<value>` (read twice in the same session, the
    same: a noise new at every read could be averaged away), `site.<value>`
    (another site's frame differs; in I.K.E. a frame shares its page's noise,
    so today false on `main`), `natural/<value>.differs` and `.noised` (two
    starts with the browser's own keys differ from each other and from Off),
    `env.<value>` (a fixed disguise the same on the other machine);
  - **the masked font names** (`fingerprint-config/<level>/fonts`, the
    names fingerprint.js masks: they follow the computer's fonts and when
    its check answered, so two runs of the same code could differ, as on
    pull request #155): judged by what protects, not by their digest. The
    tool measures itself, in the same run, which fonts a page can find (a
    page of its own in a profile with none of I.K.E.'s scripts, over
    fingerprint.js's names, `main`'s as well as the candidate's, and the
    families installed); every one must be
    masked (but the six every system has). A font found and left unmasked
    where `main` masked it is worse; another list that masks every font
    found is "changed"; not measured on the candidate, it cannot be judged.
    And at Strict and Maximum each of those fonts is tested **inside the
    protected page and in a frame of it** (`fonts_found`,
    `fonts_found_frame`): none may keep its own width there; one more than
    on `main` is worse (a name taken out of the list, or out of the masks at
    run time, shows here);
  - **values that were null on main and are missing here** are never "the
    same": not measured on the candidate, so worse.

  When that holds, the change passes: "changed" (still protected), or
  "stricter" when the noise grew beyond the tolerance (the case of pull
  request #148: the audio noise ten times larger). Weaker, so worse: back to
  the real value, the same in every session, a smaller noise, more of a real
  list, nearer the real value, a hidden value now readable, a mark turned
  false. What cannot be judged is worse: a level measured without Off, a value
  that changes between sessions at Off too, a part that could not be read,
  fewer sessions on the candidate, a value only one side has, real values the
  noise is measured against that differ between the two sides. Values
  with a **protective direction** (`PROTECTIVE`: the native look of the
  replaced functions, `webdriver`, Global Privacy Control, the APIs offered,
  media devices, battery, WebGPU, local fonts, the keyboard map, voices, the
  third-party image, the `ike:` pages, permissions) are worse when the
  protected value of `main` (hidden, refused, native-looking) is lost, stricter
  when it is gained, and cannot be judged otherwise; so are the storage quota,
  the pages' scriptlets (`page-scriptlets/*`) and the fingerprinting
  configuration. None of these ever passes by evidence.
- **Network.** The hosts the browser contacts by itself with a fresh profile,
  on two starts, at start and while loading the probe page (the engine and Qt
  through a recording proxy, I.K.E.'s own Python through an audit hook that
  also refuses the connection). Worse: a host `main` does not contact, unless
  every new host is declared in `tests/data/no-regression/endpoints.json` for
  that observation (I.K.E.'s known external endpoints: the host, what it is
  for, the observation, where the code names it; a host `main` already
  contacts is not listed, it is not new) **and** this change's own code names
  it (added lines of `ike/**/*.py`, not comments).
- **Security settings.** The engine switches I.K.E. adds and what it drops
  from a hostile environment (no sandbox, no site isolation, remote
  debugging...), its lists of unsafe switches, tracking parameters and
  hands-off sites, the WebEngine settings, permissions, scripts and request
  headers of every level, the protective defaults. Stricter or equal passes;
  worse: anything weaker or missing (an added hands-off site, a switch that
  reads as weaker, a default turned off) and any change the rules cannot
  judge (a header, a setting whose safer value is not known). **No
  exceptions**: no evidence accepts a change of a security setting, only a
  person.

**Needed changes pass by themselves** (the owner's principle of 2026-11-24:
a change needed for I.K.E. to work correctly and for its protections to keep
working is approved by the chain itself), but only where the tool can tell a
need from a weakening (an independent review of the same day: "when in doubt,
worse"). Each difference is judged by its section's rules (stricter or still
protected: it passes; weaker: worse), or it cannot be judged (worse). The one
kind evidence of need can accept is **a fingerprinting value `main` left real
that the change now disguises in every session**, and only when all of this
holds:

- a person bound a test to that value in
  `tests/data/no-regression/necessity.json` (an exact test id, the values'
  keys with at most the level as `*`, the files under `ike/` the change must
  touch, why); `main`'s copy of the file counts;
- the test **fails on `main` and passes here** in the junit results (main's:
  the last run of `tests.yml` pushed to `main` on `main`'s commit that ended in
  success or failure, read by the job **main-results**, the only one with
  `actions: read`, which runs none of the candidate's code), and running it
  again **three times on each side** (`main`'s worktree, the candidate) it
  fails every time on `main` and passes every time here;
- this change touches one of the binding's files but not the test's own file,
  and the test claims at most four values (`NECESSITY_CAP`).

Evidence never accepts a weakening, a value that could not be read or was not
measured, an Off-level row, a value with a protective direction, the
fingerprinting configuration, a request, a host or a security setting: an AI
fix that turns a protection off and also makes a failing test pass is still
worse. A request newly let through and a new host have only their own
evidence (the list data, the registry).

A candidate that blocks more, or is stricter, passes, and the report says
so. A part that could not be measured fails: it is never passed. The step
writes a JSON report and a summary in plain words to the run's summary and to
the `test-results` download (`no-regression/report.md`, `report.json`). The
report says **why** each difference passed (`why` and `passed_by` in the
JSON): the rule that judged it, the evidence (which test, confirmed how,
which files, which list rule, which declared endpoint), or the person who
accepted it; its first line says "Passed, N by evidence" when evidence let
something through; each worse row says whether it is weaker or could not be
judged; and it lists the evidence it read. What passed by evidence is also a
notice of the run, which the signing notice (`tools/release-notice.py`) lists
under "Differenze passate per prova, senza una persona".

**Accepting a change.** A change that keeps or strengthens the protection
(a larger or another noise, another draw of the same common values) and a
needed change with its evidence pass by themselves and need no entry. A new
fixed disguise (a screen size, a user agent...) passes once a person adds it
to `tests/data/no-regression/common-values.json` (the value, the part, the
common values, why). The allowlist is only
for what a person read and wants although the tool calls it worse: a real
weakening, or a change it cannot judge. A person adds an entry to
`tests/data/no-regression/allowlist.json`: the observation's key as the report
prints it (a glob), optionally its value on `main` and on the candidate (so it
accepts that one change only), why, and who accepted it when. For a value whose
readings change with the session's key (a disguised value: its value never
repeats), an entry pins instead the part the row is about (`"part": "[3]"`),
a text of the row's detail (`"detail": "the real value"`) and the version of
I.K.E. it is for (`"version": "1.1.25"`: with another version the entry no
longer counts). The file is
under `tests/data/`: the automatic fix may not touch it, and a pull request
that changes it is a test file changed, so it never merges by itself. Since
2026-11-24 `tests.yml` reads **`main`'s copy** of the allowlist, of the
endpoints, of the tests' bindings, of the common values and of the floors,
never the candidate's (a file of them that cannot be read is an error, never
"none"): an entry counts
once it is on `main` (first a pull request with the entry, then the change).
An entry that no longer matches anything is listed in the report, to be
removed. The noise floors (`noise-floor.json`) are raised when the noise is
made stronger, never lowered without a person reading why.

By hand: `python3 tools/no-regression.py check --base-repo <main checkout>
--candidate-repo . --out-dir /tmp/nr` (each checkout needs its
`vendor/adblock` engine built); `snapshot` and `compare` do the two halves.
The evidence: `--main-junit` and `--candidate-junit` (pytest's junit files),
`--necessity`, `--endpoints`, `--diff` (the change as git's diff; `check` asks
git for it in the candidate's checkout, from its merge base with `main`'s
commit, and runs the bound tests again itself; `compare` takes `--confirmed`).

What it cannot see: a weakening outside the corpus (another site, request or
API than those measured); YouTube's own pages, which need HTTPS (its requests,
element-hiding rules and scriptlets are measured, not a page of it);
timers that start more than 100 s after the page's load (the late read at
Balanced waits 100 s; a later change, or one at another level, is the
static guard's to refuse); brands other than the nine hosts measured; a
configuration outside the matrix (a triple of values no session of the run
meets, an axis it does not have: the graphics card, the display server): the
static guard refuses a condition on what the matrix does not cover, and
different runs meet different triples; the
sandbox really on (GitHub's
runners refuse it: `security.yml` tests it); a real graphics card and the
user's own fonts (software rendering, the runner's fonts, the same on both
sides); whether a new disguised value is rarer than the old one when neither
is nearer the real one (the tool knows the real value, not how common a value
is: for a fixed disguise a person decides, in the common values), a drawn
value that can be alike in every draw by chance (the card's maker, one of two;
the copies of the card's name in the shared and the file worker and in the
frames made by `innerHTML` and `srcdoc`, read in the 8 sessions only), a real
value shown somewhat more often than chance shows it
(the real list of extensions in a tenth of the draws instead of 1 in 128
fails one time in four; in a quarter, nine times in ten), and a noise in
another site's frame (I.K.E.'s frames share
their page's noise: `site.` is false on `main` and only guards a future
per-frame noise). What `main` itself leaves real cannot get worse and is
only judged when it changes: on 2026-11-24 a dedicated worker started from
a file of the site (not from a blob) read the real card, extensions and
languages at Strict on `main` (an I.K.E. gap the probe now shows, reported
for a fix of its own).

**False alarms.** A red from chance would hold back every real update of the
day; a pass from a looser rule would let a weakening through. So no rule is
loosened for chance: what chance can produce is told from a weakening by more
readings (eight sessions, 24 draws of the picks, 896 stripes, 128 widths).
Main against main in the same run (as in `tests.yml`: the same random keys,
sites and shape on both sides) gives the same values, so nothing is judged at
all. A rewrite of the noise of the same strength draws every noised value
anew; measured as main against main with independent random keys and sites
(16 snapshots, every ordered pair: 240 comparisons), none had a "worse" on
2026-11-24 (`main` f51ba83, with the fourth review's measures), nor on
2026-11-25 (`main` 8176b12, with round 5's measures: brands, the late read,
the large pictures, the other machine with 32 processors). The same
experiment, in earlier rounds, found what more readings fixed: in round 5,
texts of the same width (digits for digits) noised alike since 1.1.25 draws
a width's noise from its own value, so the count changed varied with the
key (now 128 texts of different widths), and the cores, a pick drawn only
on the other machine, judged as a fixed disguise there (now its real value
there only); 84 of 240 with
the real value of a text width or of the extensions' list in one session
(chance gives it: now judged against how often, measured on `main`), and 5 of
240 with fewer flat stripes changed (448 stripes repeating every 256 were
noised alike in pairs: now 896, each of its own colour). Computed for such a
run: 141 noise measures, each at most 3 in 100,000 (together 0.03 %); the
counts of 24 lists drawn per session at 1 in 10,000 each (0.24 %); 43
real-value tests at 1 in 10,000 each (0.43 %); the picks, the hashes and the
marks far below: under 0.8 % per run. And 20 real runs of `check`, main
against main as in `tests.yml`, gave 20 passes (an earlier 20, a round
before, had one red: the storage estimate at Off ran out of its 3 s on a busy
computer; it now has 10 s), 6 more with round 5's measures (2026-11-25,
`main` 8176b12) gave 6 passes, and 6 more with round 6's matrix gave 6
passes; the 240 pairs of 16 snapshots with independent keys, each with its
56 sessions of the matrix, gave none worse. A check takes about 350 s on a
4-core computer running two at once (the late read and the brands add about
55 s a side, the matrix about 30 s a side: two browser starts and 20 s of
sessions); `--runs 3` about 18 minutes, within its step's 45.

**Code that recognises the measurement** and behaves differently there
is only partly guarded: the probe's address, title, global, the frame's host,
the hook's files, its variable and the noise keys of `check` are random for
each run, and the static guard (`tools/fix-guard.py`) and the AI reviewers
(`tools/ai-review.py`) refuse an AI change that names what measures it
(`IKE_TEST_*`, `IKE_NR*`, `IKE_NO_SINGLE`, `nrResult`, "no regression", the
offscreen platform, SwiftShader, the sandbox and D-Bus variables of the run,
`GITHUB_ACTIONS`/`CI`/`RUNNER_*`, the local address, `.example` hosts,
`addaudithook`/`sys.modules`, the probe's drawn text and known-bytes generator,
the noise keys' store...); the code measured still runs in the same job, with
its test hook. The gate should move to a job of its own on a fresh runner,
planned with the sharded CI of the branch `automation/fast-tests`. `main`'s
side is measured by `main`'s copy of the tool, so these rules, the extra
readings and the evidence apply to both sides once they are on `main`; a
snapshot of an older copy compares safely: what it lacks on `main`'s side is
judged on the candidate alone, or is worse, and a candidate without a second
session where `main` has one is worse.

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

An issue titled "DEVI AIUTARCI CON CHATGPT" (label `automat-help`) asks nothing
that blocks: AUTOMAT keeps retrying; pasting its message into ChatGPT helps it
("AUTOMAT, part 2").

An issue labelled `autofix` or `automation-health` means the automation needs a
person: open a conversation and paste its link. Since AUTOMAT these are only
a security finding with no safe fix and the failures of GitHub, a setting or
a workflow; everything else is retried by itself.

## Repository settings (once)

- Settings → Actions → General → Workflow permissions: keep **Read repository
  contents** (each job asks for what it needs) and tick **Allow GitHub Actions
  to create and approve pull requests** (otherwise the candidate and the fixes
  cannot open their pull requests).
- **Required for AUTOMAT to run with no one** (see "The owner's token, needed
  once" above), and for the workflows' pins (the full chain, 2026-11-22): the
  repository **secret** `IKE_WORKFLOW_TOKEN`, a fine-grained personal access
  token of the owner's, for this repository only, with the permissions
  Contents, Pull requests and Workflows (read and write). Only the
  workflow's own push and merge steps receive it (a candidate's push and pull
  request in `daily-maintenance.yml`, the automatic fix's in `autofix.yml`
  job publish, the refresh and the merge in `automerge.yml`); no AI step ever
  sees it. Without it
  those candidates wait (a warning says why) and Dependabot's monthly pull
  request remains the way for the actions.
- Settings → Secrets and variables → Actions → **Variables** (optional, the
  owner's alone; "AUTOMAT, part 2" says what each does and how to set it):
  `AUTOMAT_CHATGPT_AFTER` (a number, default 4), `AUTOMAT_CHATGPT_AUTOMERGE`
  and `AUTOMAT_TIER_B` (`on`, default off). The token `IKE_WORKFLOW_TOKEN`
  never gets the permission "Variables": no workflow can then set a switch.
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
