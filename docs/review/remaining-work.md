# Remaining work and next phases

> Written for 1.0.3 and kept as a snapshot: several items were done later
> (CHANGELOG.md), and the Linux / Windows plans were archived on 2026-11-20.
> Current open work: [ROADMAP.md](../../ROADMAP.md).

## Decisions for the owner

1. **Widevine** (audit, open issue A): pin a hash per version in I.K.E. (a
   release of I.K.E. for every Widevine release) or keep TLS-only and say so
   in Settings; and whether an installed module should be updated
   automatically (the code to detect a newer one exists and is not called).
2. **Filling saved passwords** (open issue C): keep filling when the page
   loads, or fill the password only after the user focuses the field.
3. **`__min_system__`**: set to 1.0.1 because the icons under `/usr` changed
   in 1.0.1. With it, 1.0.0 installations move to 1.0.1 and later by package
   only. Setting it back to 1.0.0 lets the self-update carry 1.0.0 → 1.0.3,
   with the old icon until the next package.
4. **Start as administrator** (open issue J): refuse, or keep the warning in
   Help → About.

## Work left from the audit

In the order suggested:

1. Extensions: verify the CRX3 signature before unpacking (issue B) — before
   the feature leaves "experimental".
2. Permission questions only for the tab in view (issue G).
3. Vault format 2: parameters in the header, idle lock (issue D), with a
   migration test that cannot lose a password.
4. I.K.E.'s own downloads through Qt's network stack, so they follow the
   desktop's proxy (issue E).
5. Pin GitHub Actions by commit hash with an update rule (issue F).
6. Bound `shields.redirected` (issue H).
7. A second review of the three changes with new logic: local file rules,
   the question for external applications, clearing site data.
8. Fuzzing of the engine module's entry points and of `scriptlets.preprocess`
   (cargo-fuzz / Atheris), on a schedule, not in the pull-request workflow.

## Work left from the code review

- Split `ike/window.py`, `ike/dialogs.py` and `ike/features.py` by area
  (toolbar and menus; settings pages; workspaces and groups), one pull request
  per file, no behaviour change, the existing tests as the safety net.
- Icons: their uniformity across themes can only be judged on a real Plasma
  session (left untouched in 1.0.2 for that reason).
- The known limits in ROADMAP.md (media keys next / previous, user-script menu
  commands, Dark Reader).

## To be checked by the owner on the real system

None of this could be run in the environment of this work (no display, no
Plasma, no pacman):

- Installing the three packages with pacman on CachyOS and a first start of
  each on Plasma 6 / Wayland.
- Moving toolbar buttons with a real mouse and with a touchpad; the
  customise mode; the » button in a narrow window; fractional scaling.
- Fades and the gliding close button with KWin's compositor; Plasma's
  animation speed set to "Instant" switching them off.
- The question before a link opens another application, with real handlers
  (`mailto:`, `magnet:`, `steam:`).
- Copying a password: absent from Klipper's history, gone after 45 seconds.
- "Clear browsing data" → restart → a site that had stored data starts fresh.
- Opening a saved web page (`page.html` + `page_files/`) from Downloads and
  from another folder: it looks as before.
- Help → About: engine version, patch level, no sandbox warning.

## Next phases

1. **Platform study** — documents only, in `docs/platforms/`: Linux
   distributions and package formats, the component manager, Windows (Qt
   run time, deployment, codecs and licences), a porting plan per platform.
   The strategy for Linux and Windows, the component manager and the codec
   and licence questions are treated there, not in this report.
2. **AUR** — when the owner says it is time.
3. Then, by the ROADMAP: the first platform beyond Arch chosen from the
   study, with its own tests on that platform before it is called supported.
