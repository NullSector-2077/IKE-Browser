# Arch / CachyOS maintenance

## System dependencies

Python, PyQt6, Qt WebEngine and the system Qt libraries are provided by Arch packages. Users update them with \`sudo pacman -Syu\`. I.K.E. must not bundle or independently replace the system Qt runtime.

## Browser components

The Rust AdBlock engine is locked by \`ike-adblock/Cargo.lock\`. uBlock Origin scriptlets are stored in \`ike/resources/ubo-scriptlets.json\` and regenerated with \`tools/build-ubo-scriptlets.mjs\` from an upstream uBlock checkout.

The daily component check monitors only these two components:
- AdBlock Rust releases from crates.io, checking that \`Cargo.toml\`, \`Cargo.lock\` and the engine's embedded version agree
- Actual uBlock scriptlet payload changes, not merely a new upstream commit

Python, PyQt6, Qt and Qt WebEngine are deliberately not checked or bundled here; pacman owns those system dependencies. Windows and AppImage dependencies are outside this repository's scope.

## Automation and review

\`.github/workflows/daily-check.yml\` runs the component check daily and updates a single issue when newer versions or check failures are found.

\`.github/workflows/daily-maintenance.yml\` prepares a candidate on the separate \`automation/daily-maintenance\` branch when an actionable component update is found. It updates the locked Rust dependency or generated scriptlets, increments the patch version, builds the AdBlock engine, and runs the Linux test suite and Arch package build. It creates or updates a draft pull request for human review.

The automation never merges a pull request, changes \`main\`, signs an update, or publishes a release. The maintainer reviews and approves all changes. Release signing and package signing happen locally on the maintainer's Arch/CachyOS computer. Private keys and passphrases never enter GitHub Actions or the repository.
