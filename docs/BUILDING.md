# Building I.K.E. Browser

## Current repository state

The I.K.E. repository is being initialized as a clean 1.0.0 project line. The application source tree and packaging recipe have not yet been imported into this repository. Consequently, a complete build cannot be performed from this branch yet.

Do not treat this bootstrap branch as a source release or installable package.

## Initial platform target

The first packaging target is Arch Linux and CachyOS, x86_64.

The intended Arch package must use dependencies supplied by the operating system rather than bundling Qt or QtWebEngine. The package metadata must declare the actual runtime dependencies required by the application, including Python, PyQt6, PyQt6-WebEngine, Qt WebEngine and the required Qt modules.

The final dependency list must be checked against the imported source and a clean Arch/CachyOS installation before release. Do not copy a dependency list blindly from the former ICE package.

## Build validation (after source import)

Once the source tree and PKGBUILD are present:

1. Review the PKGBUILD and all install hooks.
2. Confirm that Qt/PyQt6/QtWebEngine are system dependencies and are not copied into the package.
3. Build with makepkg on Arch/CachyOS.
4. Inspect the package file list and dependency metadata.
5. Install the package on the maintainer's CachyOS machine.
6. Launch the installed application and exercise the critical browser functions.
7. Verify upgrade and removal behavior, including preservation of user data.
8. Sign the final package locally with the maintainer's existing signing key.

The signing key and passphrase must remain local. They must never be committed, uploaded as an artifact, placed in GitHub Secrets for routine builds, or exposed in workflow logs.

## Release gate

No package is considered release-ready until the maintainer has completed the real installation test and verified the signed package on CachyOS.
