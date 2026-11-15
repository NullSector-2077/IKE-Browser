# I.K.E. Browser

**Internet Kontrol Experience**

I.K.E. Browser is a desktop web browser project built with Python, PyQt6 and QtWebEngine, with a Rust-based content-blocking component.

## Project status

This repository is the clean starting point for the I.K.E. Browser 1.0.0 line. It is intentionally separate from the former ICE Browser repository and does not carry over its release history.

## Architecture

- **Application interface:** Python and PyQt6.
- **Web platform:** QtWebEngine supplied by the target operating system.
- **Content blocking:** Rust component.
- **Linux packaging:** intended for Arch Linux and compatible distributions, using system-provided Qt/PyQt6/QtWebEngine dependencies rather than bundling those libraries.

## Development

The source tree, build instructions, supported platforms, security behavior and feature documentation will be added and verified as the 1.0.0 baseline is prepared.

## License

The applicable license and third-party notices will be documented with the source distribution.
