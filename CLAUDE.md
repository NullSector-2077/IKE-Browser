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
  merges after green tests, issues, workflows) without asking each time. Only
  signing and publishing releases belong to the owner (`python3
  tools/publish.py` on the owner's PC).
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
