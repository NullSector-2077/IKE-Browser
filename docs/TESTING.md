# Testing I.K.E. Browser

The application test suite is in `tests/`. GitHub Actions runs the Linux headless test job for pull requests, pushes to `main` and `rebrand/**`, and daily Arch maintenance candidates. It builds the Rust AdBlock extension, runs Ruff, then executes pytest.

For local testing on Arch / CachyOS:

```bash
sudo pacman -S --needed base-devel rust python-pytest python-ruff
cargo build --release --locked --manifest-path ike-adblock/Cargo.toml
install -m755 ike-adblock/target/release/libike_adblock.so vendor/adblock/ike_adblock.abi3.so
ruff check .
python -m pytest
```

A CI pass is not a substitute for the maintainer's acceptance test on a real CachyOS / Arch system. Before release, build and install the PKGBUILD, launch the browser, check Qt WebEngine, AdBlock, privacy protections, profiles, persistent user data, upgrade and removal behavior, and inspect the package contents. See [Arch testing details](arch/TESTING.md).
