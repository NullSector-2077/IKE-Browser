# Maintenance policy

## Automated component checks

The daily component check monitors only the Rust AdBlock engine and uBlock Origin scriptlet payloads used by the Arch / CachyOS package. When an actionable update is found, the daily maintenance workflow prepares a candidate on a dedicated branch and opens or updates a draft pull request. It builds the updated AdBlock engine and runs the Linux tests and Arch package build.

Python, PyQt6, Qt and Qt WebEngine are system-managed by pacman. Windows and AppImage dependencies are outside this repository's scope. See [Arch maintenance details](arch/MAINTENANCE.md).

## Repository and review policy

The repository-health workflow checks repository structure and documentation. Automation must not merge pull requests, change `main`, sign updates or publish releases.

- `main` is the stable line; do not push transfer work directly to it.
- Propose source changes through pull requests.
- Keep automation on dedicated branches.
- Failed, incomplete or skipped checks must not be described as passing.
- The maintainer reviews and approves every merge.

## Signing and publication

Release signing is a local maintainer operation. Private signing keys must never enter Git, workflow artifacts, Actions logs or repository files. Publish only after the exact Arch package has been built, installed and tested on CachyOS / Arch Linux.
