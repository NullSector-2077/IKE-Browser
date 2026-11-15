# I.K.E. Browser

**Internet Kontrol Experience**

I.K.E. Browser is a desktop browser project based on Python, PyQt6 and QtWebEngine, with a Rust-based content-blocking component.

## Project status

This is the independent I.K.E. Browser 1.0.0 repository. It starts a clean project and release history; the previous ICE Browser repository remains separate and unchanged.

The repository is currently in its bootstrap phase. The application source and final Arch packaging recipe have not yet been imported. This branch contains project documentation and a repository-health workflow, not an installable browser or a complete source release.

## Initial platform and architecture

- **Application layer:** Python and PyQt6.
- **Web engine:** QtWebEngine.
- **Content blocking:** Rust component.
- **First packaging target:** Arch Linux / CachyOS x86_64.
- **Qt deployment on Arch:** Qt, PyQt6 and QtWebEngine are to be supplied by system packages, not bundled into the Arch package.

The exact dependency list, supported platform matrix and implemented feature set will be documented only after the corresponding source has been imported and checked.

## Documentation

- [Changelog](CHANGELOG.md) — begins at I.K.E. 1.0.0; no ICE release history is carried over.
- [Build and packaging policy](docs/BUILDING.md)
- [Testing and acceptance gates](docs/TESTING.md)
- [Maintenance and automation policy](docs/MAINTENANCE.md)

## Automation

The repository-health workflow is scheduled for 08:00 Europe/Rome. It uses two UTC cron triggers and a local-time guard to account for CET/CEST. At this bootstrap stage it checks the documentation baseline and reports that application tests are not yet available.

The workflow does not publish releases, sign packages, update dependencies automatically, or push to main.

## Release and signing policy

The first Arch package must be built and installed on the maintainer's CachyOS system before publication. The final package must be signed locally. Private signing keys and passphrases must never be committed or uploaded to GitHub Actions.

## License

The license and third-party notices for the imported source and dependencies will be established and included before a source or binary release is published.
