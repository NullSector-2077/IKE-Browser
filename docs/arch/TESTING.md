# Arch / CachyOS tests

The test suite starts the real browser without a display (PyQt6 + Qt WebEngine), using temporary profiles and local stand-in data. Run it from the repository root after building the native AdBlock module:

    cargo build --release --locked --manifest-path ike-adblock/Cargo.toml
    install -m755 ike-adblock/target/release/libike_adblock.so vendor/adblock/ike_adblock.abi3.so
    python3 -m pytest

Ruff is configured in pyproject.toml:

    ruff check .

The desktop integration tests use D-Bus stand-ins; tests that require unavailable system services are skipped explicitly. AdBlock engine tests require the Rust extension to be built. GitHub Actions runs the same Linux test suite in a headless environment.

To test an installed Arch package rather than the repository source:

    IKE_TEST_APP=/usr/lib/ike-browser python3 -m pytest

The final acceptance gate remains a real installation on Arch Linux / CachyOS: verify package dependencies, launch, Qt WebEngine, AdBlock, privacy controls, profiles, persistence, upgrade and removal behavior.
