# I.K.E. — Internet Kontrol Experience

A light, independent web browser for Arch Linux focused on privacy: no
telemetry, no accounts, no sponsored content, with ad blocking and
fingerprinting protection built in.

The interface, protections, password manager and updater are I.K.E.'s own code
(Python + Qt). Pages are rendered by Qt WebEngine, the Chromium engine,
provided and kept up to date by Arch Linux. I.K.E. is developed on and for
KDE Plasma (CachyOS / Arch Linux) and works on the other Arch-based desktops.

**Version 1.1.14** - see [CHANGELOG.md](CHANGELOG.md).

## Install (Arch Linux, CachyOS)

Install a ready-made package from the
[releases page](https://github.com/NullSector-2077/IKE-Browser/releases):

```bash
sudo pacman -U ike-browser-1.1.14-1-x86_64.pkg.tar.zst
```

or build it from a clone of this repository:

```bash
git clone https://github.com/NullSector-2077/IKE-Browser.git
cd IKE-Browser
makepkg -si
```

Pacman installs the dependencies, Qt WebEngine included, and keeps them updated
with the rest of the system. Start I.K.E. from the application menu or with
`ike-browser`. To remove it: `sudo pacman -R ike-browser`.

Personal data lives in `~/.config/ike-browser`, `~/.local/share/ike-browser`
and `~/.cache/ike-browser`, and is kept when the package is removed. Extra
profiles: `ike-browser --profile NAME`.

## Features

**Protection**
- A shield inside the address bar with five levels — Off, Compatibility,
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
  download manager, PDF viewer, reader mode, picture-in-picture, translation
  through an external service, site permissions.
- Page dark mode with Dark Reader as its extension works (its fixes for single
  sites, sites that are dark already left alone, its detector of a site's own
  dark theme; lists kept up to date with the daily maintenance), or with the
  engine's own dark mode.
- Zoom kept for each site; videos and sounds that may not start by themselves
  (all sites, or one); the lock in the address bar opens the site's panel
  (connection, permissions, cookies, protection, zoom, autoplay).
- Command bar (F2): menu commands, open tabs, bookmarks, history and settings in
  one search. Optional mouse gestures (off by default).
- I.K.E.'s own pages for sites that cannot be reached, with "Try again".
- Reader mode with light, sepia or dark and the text size of your choice.
- Free choice of search engines (DuckDuckGo by default), suggestions, keywords; the
  engine in use right after the lock and in the new tab page, a click to change it.
- New tab page with a clock and, for a city you choose, the weather; tiles of
  your bookmarks or of the sites you visit most (up to 32, sixteen per row on
  a wide window); the trackers and ads blocked
  this month; your own photo as its background if you like (kept on the
  computer, never uploaded).
- Toolbar buttons shown, hidden and moved to either side of the address bar
  ("Customise toolbar"); Back, Forward, Home and Reload keep their place at the
  start, and the shield its place inside the address bar, at its end. In a narrow
  window the buttons that do not fit are listed under a » button.
- **Site resources** (Shift+Esc): memory, CPU and network of each open site,
  with optional limits that suspend or freeze greedy background tabs.
- **Watched pages**: right-click a page, or a part of it such as a price, to be
  notified when it changes.

**Desktop integration** (through D-Bus; nothing to install)
- Media controls: the tab playing sound appears in Plasma's media widget and on
  the lock screen and answers the media keys, next and previous included where
  the site offers them; players embedded in a page (a video inside an article)
  too (also on GNOME and other desktops).
- Downloads in Plasma's notifications ("Open" and "Open Containing Folder"
  when done) and as progress on I.K.E.'s icon in the task manager; open tabs
  and bookmarks in KRunner, with "Mute", "Unmute" and "Close tab"; "Send to
  device" to a phone paired with KDE Connect.

**Appearance and languages**
- Follows the system theme by default; icon themes installed on the computer or
  the bundled Lucide and Phosphor sets; light or dark interface.
- Other interface themes: five ready-made ones (I.K.E., Night, Paper, Forest,
  High contrast) and your own, with your choice of background, text, accent,
  toolbar and tab colours and of the font family and size.
- A modern finish in the theme's own colours: a line under the current tab
  that glides to the next one, long tab titles that fade out instead of
  ending in "…", a rounded address field, suggestions with the sites' icons,
  a zoom sign in the address field.
- Light interface effects (short fades, a loading mark on tabs, icons and bars
  that fade in, a speaker that pulses while a tab plays sound) that follow the
  desktop's reduced-motion setting and can be switched off.
- English, Italian, Spanish, French, German, Portuguese, Chinese (Simplified),
  Japanese, Russian, Ukrainian, Belarusian, Bulgarian, Polish, Czech, Slovak,
  Slovenian, Croatian, Serbian (Cyrillic), Bosnian and Macedonian included.
  Chinese and Japanese need a CJK font such as `noto-fonts-cjk`; the Cyrillic
  and Latin Slavic languages work with the usual Noto Sans. The Slavic
  translations were made with AI and not yet reviewed by native speakers:
  corrections are welcome.

## External services

I.K.E. has no servers of its own and sends no telemetry. It contacts only:

| Service | When | What is sent |
|---|---|---|
| Filter list sites (easylist.to, ublockorigin.github.io, pgl.yoyo.org, …) | once a day; urgent-fix lists every few hours | a plain download of the list |
| Google's Chrome version list (versionhistory.googleapis.com) | once a day | a plain request, no personal data |
| The search engine you chose | when you search; suggestions while typing, if on | what you type in the address bar |
| The sites of the installed search engines | once per engine, until its icon is known | a plain request for the site's icon (favicon.ico), nothing else |
| Encrypted DNS provider | only if you turn DNS over HTTPS on | the names of the sites you visit |
| Google Translate (or the address you set) | only when you translate a page | the address of the page |
| Google's Widevine download (dl.google.com) | only if you ask I.K.E. to install Widevine | a plain download |
| Open-Meteo (open-meteo.com), free, no account, no key | weather on the new tab page, only after you choose a city | finding the city: its name, once; then only the city's coordinates (rounded), at most every 30 minutes and only when a new tab is open. Your location is never asked. Can be switched off in Settings → New tab page |
| The pages you chose to watch | at the interval you chose, only while I.K.E. is open | a normal page load, like a private window: without your cookies |
| The sites of your user scripts | once a day, if automatic updates are on | a plain download of each script |
| GitHub (github.com and its download servers) | once a day, unless I.K.E. updates are off | a plain download of the latest release's signed manifest, and of the update when you install it |

## Updates

- Filter lists and the presented Chrome version update themselves daily.
- The web engine updates with the system (`sudo pacman -Syu`).
- I.K.E. itself updates by itself from the latest GitHub release, signed with
  the project's key and checked before use, the AdBlock engine included
  (Settings → General: automatic by default, or ask, or off at your own risk);
  see [docs/UPDATES.md](docs/UPDATES.md).
- The components inside I.K.E. — the AdBlock engine and the uBlock Origin
  scriptlets — are checked for new versions every day by GitHub Actions, which
  prepares a tested candidate release for the owner to approve
  ([docs/MAINTENANCE.md](docs/MAINTENANCE.md)).

## Repository layout

| Path | Contents |
|---|---|
| `ike/` | the browser (Python package) and its resources |
| `ike_boot.py` | start-up script |
| `ike-adblock/` | I.K.E. AdBlock Engine: Rust module around adblock-rust |
| `vendor/adblock/` | loader for the engine module |
| `launcher/` | the `/usr/bin/ike-browser` launcher (C) |
| `data/` | desktop entry, icons, update channel configuration |
| `docs/` | building, updates, maintenance, translating, testing, third-party components |
| `licenses/` | licences of bundled third-party components |
| `tools/` | release and maintenance scripts |
| `tests/` | automatic tests (pytest) |

See [docs/BUILDING.md](docs/BUILDING.md) to build or run from source, and
[ROADMAP.md](ROADMAP.md) for planned work.

## Licence

GPL-3.0-or-later, see [LICENSE](LICENSE). Bundled third-party components keep
their own licences, listed in [docs/THIRD-PARTY.md](docs/THIRD-PARTY.md).
