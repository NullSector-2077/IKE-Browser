# Testing I.K.E. Browser

## Bootstrap status

This repository currently contains the project README and bootstrap documentation only. Application tests cannot run until the application source, Rust component, test suite and build metadata have been imported.

The CI workflow must report this state clearly rather than presenting a no-op run as a successful application test.

## Required checks after source import

### Static checks
- Validate Python syntax and run the project's configured linter.
- Build the Rust content-blocking component in locked/reproducible mode.
- Check that generated native modules are placed only in build output and are not committed.
- Validate documentation links and packaging metadata.

### Automated tests
- Run the complete Python test suite.
- Run Rust tests for the native component.
- Test the browser in a headless Linux environment where supported.
- Keep platform-specific tests separate and report skipped tests explicitly.

### Arch/CachyOS acceptance
The maintainer must build and install the package on a real Arch Linux or CachyOS system. CI packaging alone is not a substitute for this test.

Acceptance includes:
- dependency resolution through pacman;
- successful application launch;
- QtWebEngine operation and media playback checks;
- core privacy/content-blocking behavior;
- profile and user-data persistence;
- upgrade and uninstall behavior;
- package contents and permissions;
- local package signature verification.

## Reporting

A check is successful only when its intended test actually ran and passed. Missing source, skipped tests, unavailable system dependencies and untested platform targets must be reported as such.
