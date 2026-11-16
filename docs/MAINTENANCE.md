# Maintenance policy

## Repository checks

The repository-health workflow remains scheduled for 08:00 Europe/Rome. It checks repository structure and documentation; it does not update packages, push to `main`, merge pull requests or publish releases.

## Dependency and source updates

The Arch system supplies Python, Qt and Qt WebEngine. Users update those with `sudo pacman -Syu`; I.K.E. must not bundle or replace the system Qt runtime.

The browser application has a separate signed update channel. Changes to the Rust AdBlock engine, filter scriptlets, bootstrap or release tooling must be proposed through a branch and pull request, built with locked dependencies, and tested before review. No automatic merge or release publication is permitted.

## Branch and review policy

- `main` is the stable line; do not push transfer work directly to it.
- Propose source changes through pull requests.
- Keep automation on dedicated branches.
- Failed, incomplete or skipped checks must not be described as passing.
- The maintainer reviews and approves every merge.

## Signing and publication

Release signing is a local maintainer operation. Private signing keys must never enter Git, workflow artifacts, Actions logs or repository files. Publish only after the exact Arch package has been built, installed and tested on CachyOS / Arch Linux.
