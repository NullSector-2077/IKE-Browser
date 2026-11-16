# Arch / CachyOS maintenance

## System dependencies

Python, PyQt6, Qt WebEngine and the system Qt libraries are provided by Arch packages. Users update them with sudo pacman -Syu. I.K.E. must not bundle or independently replace the system Qt runtime.

## Browser components

The Rust AdBlock engine is locked by ike-adblock/Cargo.lock. uBlock Origin scriptlets are stored in ike/resources/ubo-scriptlets.json and can be regenerated with tools/build-ubo-scriptlets.mjs from an upstream uBlock checkout. Changes to either component require a dedicated branch, a locked build, tests and human review.

The signed application update channel carries only the ike/ Python application folder. The bootstrap, launcher and compiled AdBlock extension remain package-managed system parts; increase __min_system__ when a new application release requires newer system parts.

## Automation and review

The repository-health workflow runs daily at 08:00 Europe/Rome and checks repository structure. The application test workflow runs on pull requests and pushes to main. There is no automated dependency-apply workflow, auto-merge or automatic release publication.

All source changes go through a pull request. The maintainer reviews and approves merges. Release signing and package signing happen locally on the maintainer's Arch/CachyOS computer. Private keys and passphrases never enter GitHub Actions or the repository.
