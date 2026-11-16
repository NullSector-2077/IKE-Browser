# I.K.E. — Internet Control Experience

A light, independent web browser focused on privacy: no telemetry, no accounts,
no sponsored content, with ad blocking and fingerprinting protection built in.

The interface, protections, password manager and updater are I.K.E.'s own code
(Python + Qt). Pages are rendered by Qt WebEngine, the Chromium engine (provided
by the system on Arch Linux, bundled in the AppImage and on Windows). I.K.E. is
developed on and for KDE Plasma (CachyOS / Arch Linux), and runs on other Linux
distributions and on Windows 10 and 11.

**Version 1.6.1** — see [CHANGELOG.md](CHANGELOG.md).

This release is for Arch Linux / CachyOS only. The existing AppImage and Windows
builds remain at 1.6.0 and are available from the previous GitHub release; no new
binaries for those platforms are included while their media runtimes are being reworked.

## Install (Arch Linux, CachyOS)

Build the package from a clone of this repository and install it:

```bash
git clone https://github.com/NullSector-2077/IKE-Browser.git
cd IKE-Browser
makepkg -si
```

Or install a ready-made package:

```bash
sudo pacman -U ike-browser-1.6.1-1-x86_64.pkg.tar.zst
```

Pacman installs the dependencies, Qt WebEngine included, and keeps them updated
with the rest of the system. Start I.K.E. from the application menu or with
`ike-browser`. To remove it: `sudo pacman -R ike-browser`.

Personal data lives in `~/.config/ike-browser`, `~/.local/share/ike-browser`
and `~/.cache/ike-browser`, and is kept when the package is removed. Extra
profiles: `ike-browser --profile NAME`.

## Install (other Linux distributions)

Download `IKE-Browser-<version>-x86_64.AppImage` from the
[releases page](https://github.com/NullSector-2077/IKE-Browser/releases), make it
executable and start it:

```bash
chmod +x IKE-Browser-*-x86_64.AppImage
./IKE-Browser-*-x86_64.AppImage
```

It contains everything, Qt WebEngine included, and needs glibc 2.34 or later
(Debian 12, Ubuntu 22.04, Fedora 35 and newer) and FUSE. It updates itself,
web engine included; keep it in a folder you can write to, such as
`~/Applications`.

## Install (Windows)

Download `IKE-Browser-<version>-x64-setup.exe` from the
[releases page](https://github.com/NullSector-2077/IKE-Browser/releases) and
run it. It installs I.K.E. for your user only (no administrator rights), in
`%LOCALAPPDATA%\Programs\IKE-Browser`, with Qt WebEngine included, and adds it
to the Start menu and to Windows' web browsers (Settings → Apps → Default apps).
It needs Windows 10 (version 1809 or later) or Windows 11, 64-bit (x64).

The installer has no code-signing certificate, so the first time Windows
SmartScreen says "Windows protected your PC": choose **More info** → **Run
anyway**. I.K.E. updates itself, web engine included; every update is signed
with the project's key and checked before use. To remove it: Settings → Apps →
Installed apps → I.K.E. → Uninstall (your bookmarks, passwords and settings in
`%APPDATA%\ike-browser` and `%LOCALAPPDATA%\ike-browser` are kept).

## Features

**Protection**
- A shield next to the address bar with five levels — Off, Compatibility,
  Balanced, Strict, Maximum — set globally or per site, with counters for ads,
  trackers, scripts, third-party cookies, HTTPS upgrades and removed tracking
  parameters.
- Content blocking with the EasyList, EasyPrivacy, uBlock filters, Peter Lowe
  and regional lists, network and cosmetic filters, your own lists and filters.
  Lists update daily. YouTube video ads are removed from the player data, with
  an automatic skip as a fallback.
- Cookie banners refused and hidden automatically.
- Fingerprinting protection: values that identify the computer change from site
  to site and from session to session — canvas, WebGL, audio, plugins, number of
  CPU cores, WebGL extensions, and the graphics card (a common model chosen per
  site, never the real one). The browser presents the current stable Chrome
  version, checked once a day.
- Automatic HTTPS, encrypted DNS (DNS over HTTPS), third-party cookie blocking,
  reduced referrer, Global Privacy Control.
- **Repair this site**: when a page does not work, the shield finds the
  protection that breaks it and turns off only that one, for that site only.

**Browsing**
- Horizontal or vertical tabs, tab groups, workspaces, containers with separate
  cookies, split view, suspension of inactive tabs, private windows, profiles.
- Bookmarks bar; bookmarks that do not fit are listed under a » button.
- Password vault (AES-256-GCM, scrypt key), autofill, generator, CSV import and
  export; passkeys and FIDO2 security keys.
- User scripts (Greasemonkey / Tampermonkey / Violentmonkey style), installed
  from a file, an address or by opening a `.user.js` link, updated daily. Each
  script gets only the functions its `@grant` lines ask for and reaches only
  the sites its `@connect` lines allow; your home network only when named.
- Import from Firefox and Chromium-based browsers, local backup and restore,
  download manager, PDF viewer, reader mode, picture-in-picture, page dark mode
  (Dark Reader), translation through an external service, site permissions.
- Free choice of search engines (DuckDuckGo by default), suggestions, keywords.
- New tab page with a clock and, for a city you choose, the weather.
- **Site resources** (Shift+Esc): memory, CPU and network of each open site,
  with optional limits that suspend or freeze greedy background tabs.
- **Watched pages**: right-click a page, or a part of it such as a price, to be
  notified when it changes.

**Desktop integration** (Linux, through D-Bus; nothing to install)
- Media controls: the tab playing sound appears in Plasma's media widget and on
  the lock screen and answers the media keys (also on GNOME and other desktops).
- Downloads in Plasma's notifications, open tabs and bookmarks in KRunner, and
  "Send to device" to a phone paired with KDE Connect.

**Windows**
- Media controls: the tab playing sound appears in Windows' media controls and
  on the lock screen and answers the media keys.
- I.K.E. presents itself to sites as an ordinary Chrome for Windows, with the
  same fingerprinting protection as on Linux.

**Appearance and languages**
- Follows the system theme by default; icon themes installed on the computer or
  the bundled Lucide and Phosphor sets; light or dark interface.
- Interface themes: five ready-made ones (Ice, Night, Paper, Forest, High
  contrast) and your own, with your choice of background, text, accent, toolbar
  and tab colours and of the font family and size.
- English, Italian, Spanish, French, German, Portuguese, Chinese (Simplified) and
  Japanese included. Chinese and Japanese need a CJK font such as
  `noto-fonts-cjk`.

## External services

I.K.E. has no servers of its own and sends no telemetry. It contacts only:

| Service | When | What is sent |
|---|---|---|
| Filter list sites (easylist.to, ublockorigin.github.io, pgl.yoyo.org, …) | once a day; urgent-fix lists every few hours | a plain download of the list |
| Google's Chrome version list (versionhistory.googleapis.com) | once a day | a plain request, no personal data |
| The search engine you chose | when you search; suggestions while typing, if on | what you type in the address bar |
| Encrypted DNS provider | only if you turn DNS over HTTPS on | the names of the sites you visit |
| Google Translate (or the address you set) | only when you translate a page | the address of the page |
| Google's Widevine download (dl.google.com) | only if you ask I.K.E. to install Widevine | a plain download |
| Open-Meteo (open-meteo.com), free, no account, no key | weather on the new tab page, only after you choose a city | finding the city: its name, once; then only the city's coordinates (rounded), at most every 30 minutes and only when a new tab is open. Your location is never asked. Can be switched off in Settings → General |
| The pages you chose to watch | at the interval you chose, only while I.K.E. is open | a normal page load, like a private window: without your cookies |
| The sites of your user scripts | once a day, if automatic updates are on | a plain download of each script |
| GitHub (github.com and its download servers) | once a day, unless I.K.E. updates are off | a plain download of the latest release's signed manifest, and of the update when you install it |

## Updates

- Filter lists and the presented Chrome version update themselves daily.
- On Arch / CachyOS the web engine updates with the system (`pacman -Syu`);
  the AppImage and the Windows version update their own web engine.
- I.K.E. itself updates from the latest GitHub release, signed with the
  project's key and checked before use (Settings → General: ask, automatic or
  off); see [docs/UPDATES.md](docs/UPDATES.md).
- The components inside I.K.E. — the AdBlock engine, the uBlock Origin
  scriptlets and, in the AppImage and on Windows, Qt WebEngine and Python — are checked for
  new versions every day, and updated with a new release
  ([docs/MAINTENANCE.md](docs/MAINTENANCE.md)).

## Repository layout

| Path | Contents |
|---|---|
| `ike/` | the browser (Python package) and its resources |
| `ike_boot.py` | start-up script |
| `ike-adblock/` | I.K.E. AdBlock Engine: Rust module around adblock-rust |
| `vendor/adblock/` | loader for the engine module |
| `launcher/` | `/usr/bin/ike-browser` launcher and the Windows `ike-browser.exe` (C) |
| `installer/` | Windows installer (Inno Setup) |
| `data/` | desktop entry, icons, update channel configuration |
| `docs/` | building, updates, translating, testing, third-party components |
| `licenses/` | licences of bundled third-party components |
| `tools/` | maintenance scripts |

See [docs/BUILDING.md](docs/BUILDING.md) to build or run from source, and
[ROADMAP.md](ROADMAP.md) for planned work.

## Licence

GPL-3.0-or-later, see [LICENSE](LICENSE). Bundled third-party components keep
their own licences, listed in [docs/THIRD-PARTY.md](docs/THIRD-PARTY.md).
