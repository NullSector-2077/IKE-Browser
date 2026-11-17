# Windows port (1.2.0): progress

Working notes of the port on the `windows/port` branch, kept current so the
work can be taken up again after an interruption. Removed (or reduced to the
final state) before the branch is merged.

## Done

- Code port behind `sys.platform` checks: folders, single instance (named
  pipe named after the user's SID, owner checked), notifications, identity
  shown to sites, Widevine check, updater, "clear when closed" finished after
  the browser ended.
- Build (`build.py`): embedded Python, pinned wheels with hashes
  (`requirements.txt`), Rust module as `.pyd` (MSVC), C launcher, per-user
  Inno Setup installer; `check-install.py`, `engine-check.py`.
- Workflow `.github/workflows/windows.yml`: build, installer, silent install,
  `--version`, `--selftest`, engine check, tests of the installed copy,
  silent uninstall checked, artifact `ike-browser-windows-installer`.
  All of these steps passed on run 43971104252 except the tests.
- Documents: docs/platforms/windows.md, docs/WINDOWS-CHECKLIST.md,
  docs/BUILDING.md, docs/UPDATES.md, docs/TESTING.md, CHANGELOG 1.2.0,
  README preview note.

## State

**Green** three times: runs 44004432361 (7506d72), 44008291247 (07e3371)
and 44009243310 (ad229f2, the head): both jobs, every step — 218 passed,
11 skipped (each with its reason) in the source tree and through the
installed `ike-browser.exe`; installer built, installed, `--version`,
`--selftest`, engine check, uninstalled and checked; artifact
`ike-browser-windows-installer`. Linux: the whole suite passes locally
(221 passed, 8 skipped: 7 Windows-only, 1 network); tests changed after
that full run were run one by one on Linux.

Fixed in this last session (all test-side, nothing in the browser):

- WebGL on the GPU-less runner: `test_fingerprint.py` adds
  `--disable-gpu-compositing` on Windows (Direct3D compositing loses its
  context after a page or two there). Experiment job removed.
- Pipe test: the same rubbish as on Linux (a valid message with an empty
  address list opens a window, by design).
- Waits instead of fixed pauses: download ring, Add tile, site data, the
  new-tab photo, loading line, codec report with the hostile page loaded,
  external-link click, CPU limit, the new tab page's search.

## Next

- The owner's test on a real PC (docs/WINDOWS-CHECKLIST.md).
- H.264 / AAC through Windows' decoders: branch `windows/engine`.
- Remove this file before merging.
