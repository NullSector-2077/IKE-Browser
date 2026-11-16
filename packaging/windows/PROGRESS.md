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

Tests on Windows (213 pass, 11 skipped with reasons). Remaining failures:

- `test_scriptlets_do_not_change_fingerprint`: WebGL on the runner (no GPU,
  "Microsoft Basic Render" through Direct3D) sometimes gives no context on
  the 2nd/3rd page ("Unable to initialize SkSurface"). The temporary job
  "WebGL of the runner" tries sets of test-only engine flags
  (`IKE_TEST_WEBGL_FLAGS`).
- `test_shield_icon_levels`: Windows' bold "M" reached the sampled pixel;
  the sample is now below the letter.
- `test_memory_limit` (once in three runs): now waits for the pages and the
  measured memory instead of fixed pauses.
- `test_instance_pipe_on_windows`: the handed-over page did not appear in
  the first window; the test now waits and prints the windows and the second
  start's output.

## Next

- Choose the WebGL flags from the experiment, remove the temporary job.
- Fix the handover if it really fails; then a green run; then the final
  report.
