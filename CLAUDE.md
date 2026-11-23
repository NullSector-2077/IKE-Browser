# Instructions for Claude

Read this first in every session, then README.md, ROADMAP.md (working rules,
decisions, status) and CHANGELOG.md.

- Talk to the owner in Italian: short, plain, no jargon. The owner is not a
  programmer. Repository documentation stays in English.
- Arch Linux / CachyOS only. The multiplatform pull requests (#16, #14, #13,
  #11, #10) were closed on 2026-11-20 by the owner's decision; their branches
  (windows/port, windows/engine, linux/packages, linux/flatpak,
  linux/distro-checks, automation/audit, docs/multiplatform-plan) are the
  archive: never delete them.
- Priorities: simplicity, speed, protection, privacy. I.K.E. must run on old
  PCs (e.g. an Ivy Bridge i5-3570K) and on any graphics card (NVIDIA, AMD,
  Intel, old and new); the web engine chooses the GPU path, no forced flags.
- Do not change YouTube ad blocking and do not reorganize menus or settings
  without asking.
- GitHub: Claude does everything on GitHub by itself (branches, pull requests,
  issues, workflows) without asking each time. Merging into `main` (the
  owner's decision of 2026-11-22): no AI agent merges by itself (AutoFix,
  Antigravity, Groq, Z.AI, OpenRouter...), and no agent ever merges its own
  work. Claude merges the PRs the owner asked for when all checks are green
  (the owner's standing order); ChatGPT merges only on the owner's explicit
  order, after green tests; people's PRs wait for the owner's order. Two
  switches exist, both off until the owner turns them on in GitHub's settings
  (repository variables; docs/MAINTENANCE.md, "AUTOMAT, part 2", says how):
  `AUTOMAT_CHATGPT_AUTOMERGE` (a ChatGPT fix whose checks passed is adopted
  by AUTOMAT and reaches `main` only under the gate of an AI's fix) and
  `AUTOMAT_TIER_B` (a few tier-B files open to the AIs in their narrowest
  form, with a third reviewer); turning either on is the owner's decision,
  and no agent, workflow or file of the repository ever sets them. The one
  exception, the verified merge (the owner's second decision of 2026-11-22):
  the automation's own PRs (the daily candidate
  `automation/daily-maintenance`, an AutoFix fix `automation/autofix-main` or
  `automation/update/*`) are merged by the workflow's own code read from
  `main` (`tools/automerge.py`, `automerge.yml`), only when fully verified:
  every check of the last commit passed (tests, sandbox, Security, Arch
  Linux), every category `tools/test-categories.py` requires for the changed
  components passed with nothing "not verified" and no required test
  skipped, no test file changed or removed, no protected file or workflow
  touched, licences up to date, no open security finding. AUTOMAT, the full
  automation (the owner's third decision of 2026-11-22; AUTOMAT is the
  owner's name for the whole automatic maintenance; in the owner's words:
  "intervento umano limitato solo alla firma. ike deve cercarsi gli
  aggiornamenti installarli testarli e correggerli da solo su github. 100%
  lavoro in team di ia", and: "niente annullamenti automatici, l'automazione
  deve essere in grado di riparare tutto, anche se comporta molti
  tentativi... niente deve rimanere indietro"): an AI fix of tier-A
  protected code (the ad-blocking adapter, the modules that decide the
  user's safety, I.K.E.'s own page scripts) merges by itself when it is fully
  verified as above and also "Nothing gets worse" passed (the category
  `no-regression`), the static guard accepts it (`tools/fix-guard.py`: only
  statements added, nothing removed or weakened, nothing new that reaches
  out) and two independent AI reviewers of other free providers than the
  author's approved that commit (`tools/ai-review.py`). Tier B (workflows,
  tests, tools, the sandbox and start, the signing and update channel, the
  package, what comes from others, YouTube's ad blocking) is never changed
  by an AI. Nothing waits for a person and nothing is closed or given up:
  what is not merged stays open as "retrying" and is tried again every day
  (the attempts capped per day, the free providers rotated, a fresh context
  with AUTOMAT's memory of what was already tried), with informational notes
  only; a security finding with no safe fix stays blocked and the owner is
  told. The signature is the one human step, so `release-ready.yml`'s notice
  lists everything it covers (changes of reserved files first, each AI
  change of protected code with its files, its two reviewers' verdicts and
  the no-regression result, and what is still being retried). Only signing
  and publishing releases belong to the owner (`python3 tools/publish.py` on
  the owner's PC).
- Automatic maintenance (the owner's decisions of 2026-11-22): AI agents work
  only on isolated branches (`automation/update/*`, `automation/builder/*`
  and the existing maintenance branches), never on `main`; for the builders of
  Dark Reader and uBlock Origin they may only re-anchor I.K.E.'s existing
  patches, with tests; workflow files only as proposals a person reads; they
  never change their own protections or permissions. A vulnerability starts
  an analysis and a fix on an isolated branch; with no safe fix the candidate
  is blocked and the owner is told. Only free AI providers (the owner
  confirmed no billing on Gemini, Groq, Z.AI, OpenRouter, Antigravity), with
  periodic checks, `:free` models on OpenRouter, no local inference.
- The private signing key never goes in the repository, in a package or on
  GitHub Actions. The repository is public: no personal data, keys or secrets.
- Open pull requests with the REST API (`gh api
  repos/NullSector-2077/IKE-Browser/pulls`); GraphQL is not available.
- Autofix ("Antigravity": `.github/workflows/autofix.yml`,
  `tools/autofix-agent.py`, `tools/autofix-plan.py`): do not run tests by
  hand, GitHub Actions decides; changes to it never touch the browser's code.
- Every version merged and signed must reach every user by itself (AdBlock
  engine included), with no commands. The update check stays once every 24
  hours.
- Do not stop for small things; keep going. If the owner interrupts, stop and
  wait.
