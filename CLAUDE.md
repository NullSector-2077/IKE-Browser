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
  order, after green tests; people's PRs wait for the owner's order. The one
  exception, the verified merge (the owner's second decision of 2026-11-22):
  the automation's own PRs (the daily candidate
  `automation/daily-maintenance`, an AutoFix fix `automation/autofix-main` or
  `automation/update/*`) are merged by the workflow's own code read from
  `main` (`tools/automerge.py`, `automerge.yml`), only when fully verified:
  every check of the last commit passed (tests, sandbox, Security, Arch
  Linux), every category `tools/test-categories.py` requires for the changed
  components passed with nothing "not verified" and no required test
  skipped, no test file changed or removed, no protected file or workflow
  touched, licences up to date, no open security finding. Anything less
  stays a PR, with one comment naming the owner, and in the ledger as
  needs-person or blocked. After a merge `release-ready.yml` tells the owner
  a version is ready to sign. Only signing and publishing releases belong to
  the owner (`python3 tools/publish.py` on the owner's PC).
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
