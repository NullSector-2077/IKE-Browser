# I.K.E. Browser

**Internet Kontrol Experience**

I.K.E. is a privacy-focused desktop browser built with Python, PyQt6 and Qt WebEngine, with a Rust-based AdBlock engine. Its application baseline comes from the previously working 1.6.1 source, transferred and renamed for the IKE project.

## Supported build target

The repository currently packages **Arch Linux and CachyOS x86_64 only**. Qt, Qt WebEngine, PyQt6 and Python are supplied by the system package manager. Keep the system current with `sudo pacman -Syu`.

Windows and other Linux distribution builds (including AppImage) are not part of this repository's current release target. Their installers, packaging workflows and platform-specific build files have not been transferred.

## Build and install

```bash
sudo pacman -S --needed base-devel rust
makepkg -si
```

To clone the repository first:

```bash
git clone https://github.com/NullSector-2077/IKE-Browser.git
cd IKE-Browser
makepkg -si
```

Start the browser from the desktop menu or run `ike-browser`. Remove it with `sudo pacman -R ike-browser`. Personal settings and browsing data are kept under `~/.config/ike-browser`, `~/.local/share/ike-browser` and `~/.cache/ike-browser`.

## Features

- Content blocking with network and cosmetic filters, filter-list updates and a native Rust engine.
- Anti-fingerprinting protections, HTTPS upgrades, encrypted DNS options and third-party cookie controls.
- Profiles, containers, tab groups, workspaces, split view and private windows.
- Password vault, bookmarks, user scripts, download manager, PDF viewer and reader mode.
- KDE Plasma integration through D-Bus.

See [Arch build instructions](docs/arch/BUILDING.md), [tests](docs/arch/TESTING.md), [update and release process](docs/arch/UPDATES.md), and [third-party notices](docs/arch/THIRD-PARTY.md).

## Project and release policy

The previous source repository, [ICE-Browser](https://github.com/NullSector-2077/ICE-Browser), remains separate and unchanged. This repository uses its own `main` branch and review process. Source changes are proposed through pull requests; release signing stays on the maintainer's computer. Private keys and passphrases must never be committed or uploaded to GitHub Actions.
