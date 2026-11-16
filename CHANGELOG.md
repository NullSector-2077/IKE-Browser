# Changelog

All notable changes to I.K.E. Browser are documented here.

## [1.6.1] - Arch / CachyOS source baseline

- Import the previously working browser source and rename the application, Python namespace, Rust AdBlock module, launcher, paths and package metadata to I.K.E.
- Limit packaging, release instructions and automated tests to Arch Linux / CachyOS x86_64.
- Preserve the signed application update channel; system Qt WebEngine remains managed by pacman.
- No new browser features or functional changes are intended in this transfer.

## [1.0.0] - Initial project baseline

- Establish the independent I.K.E. Browser repository and version line.
- Preserve the product identity: I.K.E. — Internet Kontrol Experience.
- Define Arch Linux / CachyOS as the first packaging and validation target.
- Keep Qt, PyQt6 and QtWebEngine supplied by the target Arch system packages.
- Establish the rule that signing keys remain on the maintainer's machine and are never stored in the repository or GitHub Actions.

This entry records the new repository baseline. It does not claim that a binary release has been built, signed, tested or published. Those steps remain pending validation of the package on the maintainer's CachyOS system.

The previous ICE Browser release history is intentionally not imported into this changelog.
