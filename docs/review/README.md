# Review of I.K.E. 1.0.x (November 2026)

This folder is the report of the work planned in [ROADMAP.md](../../ROADMAP.md)
for versions 1.0.1, 1.0.2 and 1.0.3: a clean-up, the toolbar and interface
work, a review of the whole code and a security audit.

| File | Content |
|---|---|
| [architecture.md](architecture.md) | How the program is built: processes, modules, trust boundaries |
| [changes.md](changes.md) | What changed in 1.0.1, 1.0.2 and 1.0.3 and in which files: toolbar, visual changes, link bar, clean-up, optimisations |
| [security-audit.md](security-audit.md) | The audit: method, findings rated Critical / High / Medium / Low, what was fixed, what is still open, limits of the audit |
| [dependencies.md](dependencies.md) | Python, Rust, Qt / Chromium and bundled components: versions, advisories, licences |
| [tests-and-performance.md](tests-and-performance.md) | Tests run, tests that could not be run, measurements before and after |
| [remaining-work.md](remaining-work.md) | Remaining work and next phases; where the Linux / Windows strategy, the component manager and the codec questions are treated |

## Initial state (1.0.0, before this work)

- A browser for Arch Linux / CachyOS with KDE Plasma: Python 3 and PyQt6 on Qt
  WebEngine (about 14,500 lines in `ike/`), a Rust module around Brave's
  adblock-rust (`ike-adblock/`), a small C launcher, a PKGBUILD and a signed
  self-update of the Python part.
- 126 automatic tests that start the real browser without a display; lint
  with ruff; a GitHub workflow that runs both and builds the package.
- Known problems at the start: toolbar buttons could not be moved reliably;
  the page jumped when a link was hovered; leftovers of the earlier
  installation's one-time import; the logo still showed the old name.
- No security review had been written down. The audit found one issue rated
  High (a page opened from a file could read any other file of the user) and
  several rated Medium or Low; see [security-audit.md](security-audit.md).

## State after 1.0.3

- 169 automatic tests in 26 files, 23 of them attack simulations and
  regression tests of the audit (`tests/test_security.py`), all run on the
  local machine only; one Rust unit test; `cargo audit` and `pip-audit`
  without known vulnerabilities on the day of the audit (2026-11-16).
- Every finding that could be fixed without removing a feature or breaking
  sites is fixed and has a regression test. Open issues are listed with their
  rating and the reason they were left.
- No feature was removed; no existing setting was reset or changed its
  meaning; ad blocking and fingerprinting protection were not weakened (their
  tests are unchanged and pass).
- Start-up, tab opening, page loading, processor time at rest and memory were
  measured before and after on the same machine: unchanged.

## What this report is not

I.K.E. is not "100% secure" and this report does not say so. The audit is a
review by reading the code and by attacks simulated on the local machine. It
did not fuzz the engine, did not review the source of Qt WebEngine or
Chromium, and nothing was tried on a real Plasma session or against real
websites. The limits are listed at the end of
[security-audit.md](security-audit.md) and the tests that could not be run in
[tests-and-performance.md](tests-and-performance.md).
