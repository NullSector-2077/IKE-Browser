# I.K.E. — Internet Kontrol Experience

A light, independent web browser for Arch Linux focused on privacy: no
telemetry, no accounts, no sponsored content, with ad blocking and
fingerprinting protection built in.

The interface, protections, password manager and updater are I.K.E.'s own code
(Python + Qt). Pages are rendered by Qt WebEngine, the Chromium engine,
provided and kept up to date by Arch Linux. I.K.E. is developed on and for
KDE Plasma (CachyOS / Arch Linux) and works on the other Arch-based desktops.

**Version 1.1.24** - see [CHANGELOG.md](CHANGELOG.md).

## Install (Arch Linux, CachyOS)

Install a ready-made package from the
[releases page](https://github.com/NullSector-2077/IKE-Browser/releases):

```bash
sudo pacman -U ike-browser-1.1.24-1-x86_64.pkg.tar.zst
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
- Content blocking with EasyList, EasyPrivacy, uBlock filters, the Malicious
  URL Blocklist and EasyList Italy (any other list by its address), network
  and cosmetic filters, your own filters. Lists update daily. YouTube video ads
  are removed by the lists' scriptlets; an ad that still starts is muted,
  hidden and skipped.
- **Same site, free way**: at Compatibility and Balanced (the default), a
  site's own requests are not checked against the filter lists: fewer broken sites, while other companies' ads and trackers
  stay blocked; ads served from the site's own domain are only hidden. Strict
  and Maximum check every request; YouTube is always checked.
- Cookie banners refused and hidden automatically.
- Fingerprinting protection (from Balanced, the default): canvas, WebGL, audio,
  plugins, number of CPU cores, WebGL extensions and the graphics card change
  from site to site and from session to session (at Balanced a common model
  of the same maker chosen per site instead of the exact one; at Strict and
  Maximum no name at all); Strict and Maximum also give common values for the
  screen, fonts, memory, languages and voices. Not covered: the time zone, and
  workers a site starts from a file of its own.
- Sites see Chrome on Linux with the version of I.K.E.'s own engine: header,
  client hints and JavaScript agree (at Strict and Maximum only its major
  number, today 140.0.0.0, in pages, workers and request headers). One
  exception, on by default: Google's sign-in page sees Firefox, because Google
  refuses sign-in from embedded Chromium (Settings → Protection).
- Automatic HTTPS, optional encrypted DNS (DNS over HTTPS, off by default),
  third-party cookies blocked from Balanced up, reduced referrer, Global
  Privacy Control.
- Every site in its own sandboxed process; public pages kept away from the
  router and the home network (also through public names that point there,
  checked by the engine on the real address; WebSockets excepted); signed updates that expire after 180 days and arrive in
  stages. What is protected and what is not: [docs/SECURITY.md](docs/SECURITY.md).
- **Sosia (lookalike warning)**: when an address imitates a famous site
  ("paypa1.com", a Cyrillic letter in "pаypal", "paypal.com.login.xyz"), a bar
  above the page says so. Checked on this computer only, never blocking; the
  famous sites themselves are never flagged (tested against more than 10,000
  real addresses without a false alarm), and any site can be marked as fine.
- **Repair this site**: when a page does not work, the shield finds the
  protection that breaks it and turns off only that one, for that site only.
- **Safer downloads**: a program or a script (AppImage, `.run`, `.sh`, `.exe`,
  `.msi`, `.deb`, `.rpm`, `.jar`, `.py`, `.bat`, `.cmd`, `.ps1`, `.desktop`)
  from a site on the protection lists or from a site you never visited before
  asks first; a file over plain http from an https page is stopped. "Cancel"
  is the default, "Download anyway" is at your own risk. Nothing is asked of
  the network.
- "Clear this site's data" says what it removed: cookies, the site's storage,
  its caches, and the permissions it kept.

**Browsing**
- Horizontal or vertical tabs (vertical ones also with only their icons), tab groups, workspaces, containers with separate
  cookies, split view, suspension of inactive tabs, private windows, profiles.
- Bookmarks bar; bookmarks that do not fit are listed under a » button.
- Password vault (AES-256-GCM, scrypt key), offered in a menu when you click
  into a form of the page (not inside embedded frames), generator, CSV import
  and export; passkeys on FIDO2 security keys.
- User scripts (Greasemonkey / Tampermonkey / Violentmonkey style), installed
  from a file, an address or by opening a `.user.js` link, updated daily. Each
  script gets only the functions its `@grant` lines ask for and reaches only
  the sites its `@connect` lines allow (any public site when it has none);
  your home network only when named.
- Import of bookmarks and history from Firefox and Chromium-based browsers
  (passwords through CSV), local backup and restore,
  download manager, PDF viewer, reader mode, picture-in-picture, translation
  through an external service, site permissions.
- Email links written with the web mail you choose (Gmail, Outlook.com, Proton
  Mail, Yahoo Mail) or with the computer's mail program; I.K.E. can also take
  the email links of other programs.
- Page dark mode with Dark Reader as its extension works (its fixes for single
  sites, sites that are dark already left alone, its detector of a site's own
  dark theme; its lists come with each I.K.E. release), or with the engine's
  own dark mode, which is much lighter
  ([docs/review/tests-and-performance.md](docs/review/tests-and-performance.md)).
- Zoom kept for each site; videos and sounds that may not start by themselves
  (all sites, or one); the lock in the address bar opens the site's panel
  (connection, permissions, cookies, protection, zoom, autoplay).
- Command bar (F2): menu commands, open tabs, bookmarks, history and settings in
  one search. Optional mouse gestures (off by default).
- **I.K.E. extensions** (☰ → I.K.E. extensions, or Settings → I.K.E.
  extensions): the features that come with I.K.E., each with its own on/off
  switch (user scripts, page dark mode, skipping video ads, cookie banners,
  passwords, page watcher, split view, floating video, translation,
  containers, site resources, weather, command bar, Plasma integration), and
  two that are off until you choose them: automatic scrolling with the middle
  button, and opening the selected text with the middle button.
- I.K.E.'s own pages for sites that cannot be reached, with "Try again".
- Reader mode with light, sepia or dark and the text size of your choice.
- Free choice of search engines (Startpage by default since 1.1.19: the old default, DuckDuckGo, becomes Startpage once; another engine chosen is kept), suggestions, keywords; the
  engine in use right after the lock and in the new tab page, a click to change it.
- New tab page with a clock and, for a city you choose, the weather; tiles of
  your bookmarks or of the sites you visit most (up to 32, sixteen per row on
  a wide window); the trackers and ads blocked
  this month; your own photo as its background if you like (kept on the
  computer, never uploaded).
- A greeting and short friendly messages on the new tab page, worked out in the
  page itself; to avoid repeating itself, I.K.E. keeps in its own settings only
  the dates of the first and last visit of the new tab page, the days of use, the
  streak, the usual hour, the version last seen and the messages shown lately
  (never a site, an address or your history), nothing leaves your computer, and
  all of it is off with the switch in Settings → New tab page. Holidays are
  greeted only for the traditions you choose there (none at first).
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
- Files, folders and links go to the desktop through the XDG desktop portal
  (xdg-utils is not used): a download opens with the app the desktop chose
  for it, "Show in folder" selects it in Dolphin or the file manager. With no
  portal running, the desktop's own opener does it when it is there
  (kioclient, gio, exo-open). Only where the desktop has the app: "Open with
  Okular" for a PDF, "Open image in Gwenview", archives in Ark, "Add to
  calendar" for `.ics` files, the page's code in Kate (on other desktops their
  PDF reader, image viewer, archive manager, calendar and text editor).
- Settings → "Make I.K.E. the default browser" writes `~/.config/mimeapps.list`
  as the XDG specification says, keeping every other entry.

**Appearance and languages**
- Follows the system theme by default; icon themes installed on the computer or
  the bundled Lucide, Phosphor and Breeze (KDE's own icons, there even where
  KDE's icon theme is not installed) sets; light or dark interface.
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
  Slovenian, Croatian, Serbian (Cyrillic), Bosnian and Macedonian included,
  and since 1.1.20 forty more: Dutch, Swedish, Danish, Norwegian (Bokmål),
  Finnish, Icelandic, Greek, Hungarian, Romanian, Turkish, Estonian,
  Lithuanian, Latvian, Catalan, Galician, Basque, Albanian, Afrikaans,
  Swahili, Filipino, Korean, Indonesian, Malay, Vietnamese, Thai, Hindi,
  Bengali, Marathi, Nepali, Tamil, Telugu, Georgian, Armenian, Azerbaijani,
  Kazakh, Uzbek, Arabic, Hebrew, Persian and Urdu (these four from right to
  left: the whole interface turns). Chinese, Japanese and Korean need a CJK
  font such as `noto-fonts-cjk`; the other scripts need `noto-fonts` (on most
  desktops already). The translations after Italian were made with AI and
  checked automatically (every text, placeholders, shortcuts, the right
  script), not yet by native speakers: corrections are welcome.

## External services

I.K.E. has no servers of its own and sends no telemetry. It contacts only:

| Service | When | What is sent |
|---|---|---|
| Filter list sites (easylist.to, ublockorigin.github.io, malware-filter.gitlab.io, …) | once a day; urgent-fix lists every few hours | a plain download of the list |
| Google's Chrome version list (versionhistory.googleapis.com) | about once a day, also when I.K.E. updates are off | a plain request (User-Agent "I.K.E. version check"), no personal data; used only to show in Help → About how far behind the system's engine is and to warn when its security fixes are three Chrome versions behind; never for what sites are told |
| The search engine you chose | when you search; suggestions while typing, if on | what you type in the address bar |
| The sites of the installed search engines | once per engine, until its icon is known | a plain request for the site's icon (favicon.ico), nothing else |
| Encrypted DNS provider | only if you turn DNS over HTTPS on | the names of the sites you visit |
| Google Translate (or the address you set) | only when you translate a page | the address of the page |
| Google's update service for Chrome components (update.googleapis.com), then Google's download servers (dl.google.com, *.gvt1.com) | only if you ask I.K.E. to install Widevine or to check for a newer one | one request that says only "a Chromium on x64 Linux, engine version N, wants the Widevine component" (as if none were installed; no cookies, no user or installation id, no other component), then a plain download of the package it names; the old dl.google.com/widevine-cdm/ folder only if that offers nothing |
| Open-Meteo (open-meteo.com), free, no account, no key | weather on the new tab page, only after you choose a city | finding the city: its name, once; then only the city's coordinates (rounded) asking for the temperature, the weather and the wind, at most every 30 minutes and only when a new tab is open. Your location is never asked. Can be switched off in Settings → New tab page |
| The pages you chose to watch | at the interval you chose, only while I.K.E. is open | a normal page load, like a private window: without your cookies |
| The sites of your user scripts | once a day, if automatic updates are on | a plain download of each script |
| GitHub (github.com and its download servers) | once a day, unless I.K.E. updates are off | a plain download of the latest release's signed manifest, and of the update when you install it |
| Chrome Web Store (chromewebstore.google.com, clients2.google.com) | only if you install an experimental Chrome extension | the extension's id; the package is downloaded |

The project's own checks run in GitHub Actions only, never in the browser
and never with anything about its users ([docs/MAINTENANCE.md](docs/MAINTENANCE.md)):

| Service | When | What is sent |
|---|---|---|
| crates.io, PyPI, registry.npmjs.org, github.com, archlinux.org | the daily component check and candidate | plain requests for the newest versions of the components (no account, no key) |
| The OSV vulnerability database (api.osv.dev), free, no account | the daily component check | the name and version of each Python test package, npm package and GitHub Action the project uses, to read their known vulnerabilities |
| Arch Linux's security tracker (security.archlinux.org) | the daily component check | a plain download of its list of advisories (`/issues/all.json`), compared with the Arch packages I.K.E. depends on |
| RustSec's advisory database (github.com/rustsec) | every day and on every pull request (cargo-deny) | a plain download of the database |
| Arch Linux's package mirror (geo.mirror.pkgbuild.com) | the daily component check | a plain download of the core and extra package databases, to compare every package of I.K.E.'s Arch dependency closure with what arch.yml tested |
| The release lists of the tools the workflows pin (github.com tags, raw.githubusercontent.com/actions/python-versions, nodejs.org/dist, static.rust-lang.org) | the daily maintenance (tools/ci-pins.py) | plain requests for the newest release of each pinned action and tool (no account, no key) |
| The automatic fix's free AI providers (Google Gemini, Groq, Z.AI, OpenRouter) | only when a check fails | the failure and the code around it (the repository is public) |

## Updates

- Filter lists update themselves daily; the presented Chrome version is the
  web engine's own, so it changes when the system's `qt6-webengine` does.
- The web engine updates with the system (`sudo pacman -Syu`).
- I.K.E. itself updates by itself from the latest GitHub release, signed with
  the project's key and checked before use, the AdBlock engine included
  (Settings → Updates: automatic by default, or ask, or off at your own risk);
  see [docs/UPDATES.md](docs/UPDATES.md).
- The components inside I.K.E. — the AdBlock engine, the uBlock Origin
  scriptlets and Dark Reader — are checked for new versions every day by
  GitHub Actions (and the engine's Rust crates against known
  vulnerabilities), which
  prepares a tested candidate release; it is merged once its tests are green,
  then signed and published by the owner
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
| `docs/` | building, updates, maintenance, security, translating, testing, third-party components |
| `licenses/` | licences of bundled third-party components |
| `tools/` | release and maintenance scripts |
| `tests/` | automatic tests (pytest) |

See [docs/BUILDING.md](docs/BUILDING.md) to build or run from source, and
[ROADMAP.md](ROADMAP.md) for planned work.

## Built with

I.K.E. stands on the work of these projects, each under its own licence:

| Project | What it does in I.K.E. | Licence |
|---|---|---|
| [adblock-rust](https://github.com/brave/adblock-rust) by Brave Software | the filter engine of the content blocker | MPL-2.0 |
| Rust libraries of the AdBlock engine (listed in [docs/THIRD-PARTY.md](docs/THIRD-PARTY.md)) | compiled into the engine | MIT / Apache-2.0 / MPL-2.0 / Unicode-3.0 / Unlicense |
| [uBlock Origin](https://github.com/gorhill/uBlock) by Raymond Hill and contributors | scriptlets and filter lists | GPL-3.0 |
| [EasyList, EasyPrivacy, EasyList Italy](https://easylist.to/) by The EasyList authors | filter lists | GPL-3.0 / CC BY-SA 3.0 |
| EasyList Cookie List (Fanboy's Cookiemonster) | filter list | CC BY 3.0 |
| [Malicious URL Blocklist](https://gitlab.com/malware-filter/urlhaus-filter) by curben, from abuse.ch URLhaus | filter list | CC0 1.0 / MIT |
| [Dark Reader](https://github.com/darkreader/darkreader) | dark mode for pages | MIT |
| Qt, Qt WebEngine (Chromium), PyQt6 | the window and the web engine, from the system | LGPL-3.0 / BSD / GPL-3.0 |
| Lucide, Phosphor Icons | icon sets | ISC / MIT |
| [Breeze icons](https://invent.kde.org/frameworks/breeze-icons) by KDE | icon set (the icons I.K.E. uses) | LGPL-3.0 |
| Orbitron | the lettering of the logo | SIL OFL 1.1 |

The filter lists are not shipped: the browser downloads them from their
maintainers. The same list is in Help -> About; the complete one, with every
Rust library of the engine, the new tab picture and the icons, is
[docs/THIRD-PARTY.md](docs/THIRD-PARTY.md), kept up to date by the daily
maintenance.

## Licence

GPL-3.0-or-later: [LICENSE](LICENSE) is the full text of the GNU General Public
License version 3, [COPYRIGHT](COPYRIGHT) the notice. Bundled third-party
components keep their own licences, listed in
[docs/THIRD-PARTY.md](docs/THIRD-PARTY.md); the package installs every licence
text in `/usr/share/licenses/ike-browser/`.
