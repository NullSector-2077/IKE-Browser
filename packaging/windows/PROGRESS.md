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

## In progress

Tests on Windows (215 pass, 11 skipped with reasons, on run 43998802862).
Fixed, waiting for a green run:

- `test_scriptlets_do_not_change_fingerprint`: on the GPU-less runner the
  engine's Direct3D compositing loses its context after a page or two and
  WebGL goes with it. The experiment job (runs 43975618488, 44000289126)
  showed `--disable-gpu-compositing` keeps WebGL alive; the test adds it on
  Windows only (test switch, not the browser's). Experiment job removed.
- `test_instance_pipe_on_windows`: the handover works; the test's last
  "rubbish" (a valid message with an empty address list) legitimately opened
  a new window, which then received the page. Now the same rubbish as on
  Linux, and the window count is checked.
- `test_download_progress_ring`: waits for the download to start (passed on
  run 43998802862).

## Next

- A green run (both jobs), then the final numbers into the documents and the
  final report.
