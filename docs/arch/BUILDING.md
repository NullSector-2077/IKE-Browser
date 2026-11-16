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

## AppImage (other Linux distributions)

```bash
tools/build-appimage.sh            # writes dist/IKE-Browser-<version>-x86_64.AppImage
```

Needs `curl`, `cargo` and network access to github.com and pypi.org; any
x86_64 Linux works. The AppImage bundles a standalone CPython
(python-build-standalone), PyQt6 and Qt WebEngine from PyPI, cryptography,
certifi, jeepney, the AdBlock engine and `ike/`. The Python packages are
installed at the exact versions of `tools/appimage-requirements.txt`, and the
Python build is set at the top of the script with its SHA-256 sum; the daily
component check (`tools/check-components.py`) says when newer ones exist, so each release
carries a current web engine. The bundled versions are listed in
`usr/lib/ike-browser/BUNDLED.txt` inside the image. The result needs glibc 2.34
or later (Debian 12, Ubuntu 22.04, Fedora 35 and newer).

An AppImage updates itself by downloading the AppImage of the newest release
(signed manifest, see [UPDATES.md](UPDATES.md)), so the web engine is updated
with it. On systems that restrict unprivileged user namespaces (Ubuntu 23.10
and later) the Chromium sandbox is turned off, as for other AppImages.

To run the test suite against a built AppImage:

```bash
ICE_TEST_APPIMAGE=dist/IKE-Browser-<version>-x86_64.AppImage python3 -m pytest
```

With `ICE_TEST_APPIMAGE_NEW` pointing to a second, newer AppImage, the suite
also checks that the first one updates itself to the second.

## Windows

The Windows files are built by GitHub Actions on a Windows runner
(`.github/workflows/windows.yml`, for every pull request, push to `main` and
tag) and kept as the run's artifact `ice-windows`:

- `IKE-Browser-<version>-x64-setup.exe` — the installer (Inno Setup), for the
  current user only, without administrator rights, in
  `%LOCALAPPDATA%\Programs\IKE-Browser`. It adds I.K.E. to the Start menu, to
  Windows' list of web browsers (Settings → Apps → Default apps) and to the
  installed apps; uninstalling keeps the personal data in
  `%APPDATA%\ike-browser` and `%LOCALAPPDATA%\ike-browser`.
- `IKE-Browser-<version>-windows-x64.zip` — the same program folder, used by
  I.K.E.'s own updater (see [UPDATES.md](UPDATES.md)).

The same can be built on a Windows x64 computer with Visual Studio Build Tools
(C++), Rust and PowerShell 7 (Inno Setup is installed with Chocolatey when it is
missing):

```powershell
pwsh tools/build-windows.ps1 -Out dist
```

It bundles the same pieces as the AppImage — a standalone CPython
(python-build-standalone, the same version), PyQt6 and Qt WebEngine at the
versions of `tools/appimage-requirements.txt`, cryptography, certifi — plus
Windows' media controls (`tools/windows-requirements.txt`), the AdBlock engine
(`ike_adblock.pyd`) and `ike/`. Debugging symbols and Qt modules I.K.E. does
not use (Designer, Qt Quick 3D, Multimedia, Bluetooth, …) are left out. The
bundled versions are listed in `app\<version>\BUNDLED.txt`.

The installation folder holds `ike-browser.exe` (`launcher/ike-browser-windows.c`,
a small C program), the file `current` naming the version folder in use, and
`app\<version>\` with the program. The launcher runs the bundled Python inside
its own process, so Windows shows I.K.E. (not Python) in the taskbar, Task
Manager and firewall, and never uses a Python installed on the computer.

To run the test suite against an installed copy (as the workflow does):

```powershell
$env:ICE_TEST_EXE = "$env:LOCALAPPDATA\Programs\IKE-Browser\ike-browser.exe"
$env:ICE_TEST_APP = "$env:LOCALAPPDATA\Programs\IKE-Browser\app\<version>"
$env:ICE_TEST_QPA = "windows"
python -m pytest
```

The installer is not signed with a code-signing certificate: Windows
SmartScreen warns the first time ("Windows protected your PC" → More info →
Run anyway). Updates are protected by the project's own Ed25519 signature.

## I.K.E. AdBlock Engine

`ike-adblock/` is a native Python module (PyO3, stable `abi3` interface,
Python 3.9 or later) built on Brave's adblock-rust library. Only Rust is needed:

```bash
cargo build --release --locked --manifest-path ike-adblock/Cargo.toml
install -m755 ike-adblock/target/release/libike_adblock.so \
    vendor/adblock/ike_adblock.abi3.so
```

On Windows the library is `target\release\ike_adblock.dll`, copied as
`vendor\adblock\ike_adblock.pyd`.

`Cargo.lock` pins every dependency, so builds are repeatable. To move to a new
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

## uBlock Origin scriptlets

`ike/resources/ubo-scriptlets.json` is generated from uBlock Origin's sources
with `tools/build-ubo-scriptlets.mjs` (Node.js); see the header of that script.
`tools/check-components.py` rebuilds it from the newest sources every day and
`--apply` puts the new file in place.
