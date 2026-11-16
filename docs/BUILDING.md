# Building I.K.E.

## Package (Arch Linux, CachyOS)

```bash
sudo pacman -S --needed base-devel rust
git clone https://github.com/NullSector-2077/IKE-Browser.git
cd IKE-Browser
makepkg -si
```

The PKGBUILD takes the sources from the clone, compiles the AdBlock engine and
the launcher, and installs everything under `/usr`.

## I.K.E. AdBlock Engine

`ike-adblock/` is a native Python module (PyO3, stable `abi3` interface,
Python 3.9 or later) built on Brave's adblock-rust library. Only Rust is needed:

```bash
cargo build --release --locked --manifest-path ike-adblock/Cargo.toml
install -m755 ike-adblock/target/release/libike_adblock.so \
    vendor/adblock/ike_adblock.abi3.so
```

`Cargo.lock` pins every dependency, so builds are repeatable. The module's own
tests (a fault inside the engine must become an error, not the end of the
browser) are an ordinary Rust program, built without the default
`extension-module` feature:

```bash
cargo test --no-default-features --locked --manifest-path ike-adblock/Cargo.toml
```

To move to a new
engine version, change `adblock = "=..."` in `Cargo.toml` and `ENGINE_VERSION`
in `src/lib.rs`, then run `cargo update -p adblock` (or let
`python3 tools/check-components.py --apply` do all three).

Help → About I.K.E. shows which engine is in use. If the module cannot be
loaded, an optional `python-adblock` binding placed in `vendor/adblock/` is used
instead; without either, only basic domain blocking is active.

## Running from source

With the dependencies of the PKGBUILD installed and the engine built as above:

```bash
python3 ike_boot.py
```

## Tests

```bash
sudo pacman -S --needed python-pytest ruff
ruff check .
python3 -m pytest
```

See [TESTING.md](TESTING.md). GitHub Actions runs the same on every pull
request, then builds the package with `makepkg` and runs the tests again on the
installed copy; the package is kept as the run's `ike-browser-package` download.

## uBlock Origin scriptlets

`ike/resources/ubo-scriptlets.json` is generated from uBlock Origin's sources
with `tools/build-ubo-scriptlets.mjs` (Node.js); see the header of that script.
`tools/check-components.py` rebuilds it from the newest sources every day and
`--apply` puts the new file in place.
