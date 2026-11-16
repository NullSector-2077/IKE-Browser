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

`ike-adblock/` is a native Python module built with Rust and PyO3. Build it with `cargo build --release --locked --manifest-path ike-adblock/Cargo.toml`.

## Running from source

```bash
python3 ike_boot.py
```
