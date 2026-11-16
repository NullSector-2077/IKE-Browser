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

## Installer (Windows 10 / 11, 64-bit) — preview

GitHub Actions builds it on every push (`.github/workflows/windows.yml`) and
keeps it as the run's `ike-browser-windows-installer` download; that is the
reference. On a PC, with 64-bit CPython 3.13, Rust (the `x86_64-pc-windows-msvc`
tool chain), Visual Studio's C++ build tools and Inno Setup 6 installed:

```powershell
git clone https://github.com/NullSector-2077/IKE-Browser.git
cd IKE-Browser
python -m pip install --require-hashes --only-binary=:all: --no-deps -r packaging\windows\requirements.txt
python packaging\windows\build.py
```

The result is `build\windows\installer\ike-browser-<version>-windows-x64-setup.exe`,
the folder it installs (`build\windows\app`) and `build\windows\build-info.json`,
which lists what went in with its hashes. The script

- downloads the embeddable CPython from python.org and checks it against the
  SHA-256 written in the script;
- installs the wheels of `packaging/windows/requirements.txt`, each checked
  by pip against its pinned hash, and removes Qt Multimedia with its FFmpeg
  libraries (I.K.E. ships no codec; the build stops if one is left);
- builds the AdBlock engine with Rust for MSVC as `ike_adblock.pyd`;
- compiles the launcher `packaging/windows/launcher/ike-browser.c` with its
  icon, version and manifest;
- runs Inno Setup on `packaging/windows/ike-browser.iss`.

`python packaging\windows\build.py --no-installer` stops before Inno Setup;
`--engine DIR` puts the files of a Qt WebEngine built elsewhere in place of
the wheel's (same layout, replacements only). To move to newer wheels:
`python packaging/windows/update-requirements.py` (it reads the hashes from
PyPI), then let the workflow build and test. To move to a newer Python,
change `PYTHON_VERSION` and `PYTHON_SHA256` in `build.py` (the hash is in the
`.spdx.json` file python.org publishes next to the download).

To run from source on Windows instead: install the wheels as above, build
the engine (`cargo build --release --locked --manifest-path ike-adblock/Cargo.toml`,
then copy `ike-adblock\target\release\ike_adblock.dll` to
`vendor\adblock\ike_adblock.pyd`) and start `python ike_boot.py`.

What the Windows build is and is not: [platforms/windows.md](platforms/windows.md).

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
