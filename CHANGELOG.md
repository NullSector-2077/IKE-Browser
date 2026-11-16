# Changelog

## 1.6.1

**Interface**
- Optional toolbar buttons and user-created separators can be reordered by holding
  and dragging; they can be placed on either side of the address field. The layout
  can be locked and unlocked, while button visibility remains configurable.
- Back, Forward, Home and Reload stay grouped at the left, with a separator after
  Reload. The three navigation icons are slightly more visible without enlarging
  their buttons; the maximize control uses a Plasma-style diamond.
- The I.K.E. Shield and Translate controls live inside the address field, beside
  the site identity and bookmark controls. Site permissions are indicated only
  when a site has stored permissions.
- Refined hover states, the active-tab accent, rounded menus, shortcut-aware
  tooltips and a lightweight tab-loading ring polish the interface.
- The private-window indicator is now a compact rounded badge.
- The page loading indicator has a more visible track and a subtle progress endpoint.

**Distribution**
- This is an Arch Linux / CachyOS package release. The Qt WebEngine continues to
  come from the system package manager.
- No new AppImage or Windows installer is attached to this release. Those builds
  remain on 1.6.0 while the media codec and runtime strategy is being developed.

## 1.6.0

**Windows**
- I.K.E. for Windows 10 (1809 or later) and 11, 64-bit:
  `IKE-Browser-1.6.0-x64-setup.exe` installs it for the current user, without
  administrator rights, with Qt WebEngine and Python included. It appears in the
  Start menu, in Windows' list of web browsers (Settings → Apps → Default apps)
  and in the installed apps; uninstalling keeps bookmarks, passwords and
  settings. The installer is not signed with a code-signing certificate:
  SmartScreen asks once (More info → Run anyway).
- Updates itself like the AppImage, web engine included: the new version is
  downloaded, checked against the release's signature, unpacked next to the one
  in use, started once to check it, and used from the next start; the previous
  one is kept, and a version that does not start correctly is given up by
  itself at the next start.
- Everything works as on Linux: shield, ad blocking, fingerprinting protection,
  passwords, user scripts, Repair this site, Site resources (memory and CPU from
  Windows), watched pages, Widevine (I.K.E.'s own copy, downloaded with your
  consent). On Windows I.K.E. presents itself to sites as an ordinary Chrome for
  Windows, with a common graphics card chosen per site, as on Linux.
- Media controls: the tab playing sound appears in Windows' media controls and
  answers the media keys (Settings → General).
- Notifications are Windows notifications; "Make I.K.E. the default browser"
  opens Windows' default-apps page; the import finds the other browsers'
  Windows folders.
- Settings in `%APPDATA%\ike-browser`, data and cache in
  `%LOCALAPPDATA%\ike-browser`.
- KRunner, KDE Connect and Plasma's download notifications are Linux only.

**Linux**
- Nothing changes for users: the same behaviour, the same values presented to
  sites, the same speed.

**Building and tests**
- The Windows installer and update archive are built by GitHub
  (`tools/build-windows.ps1`, `.github/workflows/windows.yml`), then the whole
  test suite runs against the installed copy on a Windows runner, including a
  real self-update and roll-back, then it is uninstalled. GitHub only builds:
  releases are still signed on the owner's computer
  (`tools/make-release.py --windows`).
- The automatic tests also run from source on Windows for every pull request.
- The daily component check follows the Windows build's Python too; the Windows
  build uses the same Qt WebEngine and PyQt6 as the AppImage.
- New tests: folders and identity on each system, the Widevine module check,
  Windows updates (and attacks by a release server or a doctored archive),
  Windows media controls driven from outside like a media key.

## 1.5.2

**Security**
- User scripts: a site can no longer use the user scripts to reach your home
  network, write to the clipboard, open tabs or show notifications.
  - Each script gets only the GM functions its `@grant` lines ask for
    (`GM_info` always); a script without `@grant` gets none, as in
    Violentmonkey and Greasemonkey 4. Scripts that use GM functions without
    declaring them need a `@grant` line.
  - Every script has its own secret key for talking to I.K.E., and I.K.E.
    checks the key and the script's grants before doing anything.
  - Scripts that run inside the page start before the page's own code and
    keep what they need to talk to I.K.E., so a page that replaces
    `console.info` or `JSON.stringify` learns nothing; the answers of
    `GM_xmlhttpRequest` cannot be taken over by the page.
  - `GM_xmlhttpRequest` follows `@connect` (the page's site, the listed
    domains and their subdomains, or `*`). This computer and the home network
    (localhost, 127.x, 10.x, 172.16–31.x, 192.168.x, 169.254.x, 100.64.x,
    IPv6 local addresses, `.local`) are reached only when `@connect` names
    them, also after a redirect and when a name leads there.
  - The install dialog also shows the sites a script connects to.
- Password manager: a login saved for `http://site` is no longer offered on
  `http://site:443` (and `https://site:80`): only the protocol's own port is
  left out of the site's address.
- Full screen and mouse lock still work at once (games, videos), and now show
  for a few seconds which site has the screen or the pointer, with "press Esc
  to exit" / "press Esc to show the cursor". Esc always ends both. A tab that
  is not in view cannot ask for them.
- Ad blocker: unchanged. When the engine fails on a request it still lets it
  through (blocking everything would break browsing); these errors are now
  counted and shown in Help → About. Fingerprinting protection: unchanged, and
  checked against the filter lists' scriptlets.

**Interface**
- The address bar is in the middle of the window.
- Minimize, maximize and close are a little larger, with a separator before
  them (window without the system title bar).

**Tests**
- New tests for user scripts (common scripts and attacks by a page),
  passwords, full screen and mouse lock, engine errors, and fingerprinting
  with scriptlets.

## 1.5.1

**Automatic maintenance**
- Every day GitHub checks whether the components inside I.K.E. have new
  versions: the AdBlock engine (adblock-rust), the uBlock Origin scriptlets, and
  in the AppImage Qt WebEngine / PyQt6 and Python. When one has, Claude prepares
  a tested update as a pull request and the owner approves and signs the
  release (docs/MAINTENANCE.md). Filter lists, the Chrome version and user
  scripts keep updating themselves in the browser every day.
- `tools/check-components.py` does the check (`--apply` writes the new
  versions); `tools/appimage-requirements.txt` holds the exact package versions
  of the AppImage, so every AppImage contains what was tested.
- Lint and the automatic tests also run on GitHub for every pull request.

**AppImage**
- The certificates of `certifi` were missing from the 1.5.0 AppImage (they are
  used only on distributions without system certificates in the usual places):
  they are back, newer (2026.10.23). The build now checks that every module is
  inside the image.

## 1.5.0

**Repair this site**
- A button in the shield for pages that do not work: I.K.E. turns off the
  protections active on the site, then turns them back on a group at a time
  and asks after each reload whether the page works. What breaks the page stays
  off for that site only, is remembered, and can be undone from the shield. If
  only switching the whole shield off helps, it offers that. Nothing is saved
  until the end; cancelling puts everything back. Can be hidden (Settings →
  Privacy).
- Two new per-site switches used by it: refusing cookie banners, and cleaning
  tracking parameters and the referrer.

**Site resources**
- Tools → Site resources… (Shift+Esc): memory, CPU, requests and data of each
  open site, refreshed every two seconds while the window is open.
- Optional limits for background tabs: over the memory limit a site's
  background tabs are suspended, over the CPU limit (for 15 seconds) they are
  frozen until opened again. The tab in view and tabs playing sound are never
  touched. Off by default.

**Watched pages**
- Right-click → “Notify me when this page changes…” or “… this part
  changes…” (a price, a headline). Checked every 15 minutes, hour, 6 hours or
  day, only while I.K.E. is open, in the background like a private window
  (without your cookies). A desktop notification says when the text changed.
- Tools → Watched pages…: open, check now, change the interval, remove, switch
  checking off.

**Desktop integration** (Linux, through D-Bus)
- Media controls (MPRIS): the tab playing sound appears in Plasma's media
  widget and on the lock screen and answers the media keys; title, artist and
  cover come from the site. Also used by GNOME and other desktops.
- Downloads in Plasma's notifications, with progress and cancel.
- Open tabs and bookmarks in KRunner.
- “Send to device”: pages, links and tabs to a phone paired with KDE Connect.
- Settings → General → Desktop integration: one switch for each. Keeping the
  screen on during videos was already done by the web engine.
- New dependency: `python-jeepney`.

## 1.4.0

**Updates**
- I.K.E. updates itself from the latest release on GitHub. Each release is
  signed with the project's Ed25519 key; I.K.E. checks the signature and the
  hash, tries the new version before using it, keeps the previous one and goes
  back to it automatically if the new one does not start. Settings → General
  (I.K.E. updates: ask, automatic or off) and Help → Check for updates work as
  before; nothing under `/usr` is touched.
- A release that needs a newer package (a new AdBlock engine or start-up
  script) is not installed by itself: I.K.E. says once that a new package is
  available.
- `tools/make-release.py` prepares and signs the update files of a release on
  the owner's computer; docs/UPDATES.md lists the steps.

**AppImage**
- `IKE-Browser-<version>-x86_64.AppImage` for Linux distributions other than
  Arch / CachyOS (glibc 2.34 or later: Debian 12, Ubuntu 22.04, Fedora 35 and
  newer). It contains Python, Qt WebEngine and everything else, and updates
  itself by downloading the AppImage of the newest release, so the web engine
  is updated too. The previous file is kept as `<name>.previous`.
- `tools/build-appimage.sh` builds it (docs/BUILDING.md).

**Tests**
- Update tests: signatures, damaged or dangerous files, a full update through a
  local server that answers like GitHub, roll-back, AppImage replacement. The
  whole suite can also run against a built AppImage.

## 1.3.2

**Interface**
- New tab page: a clock with the date in the top right corner and, for a city
  you choose in Settings → General, the weather from Open-Meteo (free, no
  account). Your location is never asked; finding the city sends its name
  once, then only the city's rounded coordinates are sent, at most every 30
  minutes and only when a new tab is open. Clock and weather can be switched
  off; °C or °F.
- Downloads button with a progress ring: the ring fills in the accent colour
  while files download and turns green when they are done, until the
  downloads list is opened.
- Address bar: the site's domain in normal text and the rest of the address
  dimmed, so look-alike addresses stand out. While editing, everything is in
  normal text.
- A thin line in the accent colour across the top of the page while it loads.
- Tab previews: resting the mouse on a tab shows a small picture of the page,
  taken when you left the tab and kept in memory only.
- The overflow button of the bookmarks bar shows » again instead of a
  bookmarks icon (bug from 1.2.0).
- The README lists every external service I.K.E. contacts and what it sends.

**Languages**
- Italian is now a language pack (`it.json`) like the others, with the same
  texts. Spanish, French, German and Portuguese are complete (16 strings were
  missing).

**Code**
- Automatic tests that run the real browser without a display
  (`python3 -m pytest`, see docs/TESTING.md) and ruff settings
  (`ruff check .`).
- `ike/window.py` split: address bar, vertical tabs, shield and close buttons
  are in modules of their own. Unused code removed. No change in behaviour.

## 1.3.0

**Interface**
- The shield in the toolbar has the colours of the I.K.E. icon: a light-blue rim
  around a dark-blue centre, so the protection-level letter is readable on any
  theme. "Off" is unchanged.
- With the system title bar turned off, the browser's own close button is drawn
  like the close button of the vertical tabs and lights up with a red circle
  when the mouse is on it (Breeze and Aurorae themes are followed).
- Interface themes (Settings → Appearance → Interface colours): ready-made
  themes Ike, Night, Paper, Forest and High contrast, and "Customize…" to choose
  background, text, accent, toolbar and tab colours and the font family and
  size, shown live, saved as your own theme and deletable. "Follow the system"
  stays the default and changes nothing on Plasma. Web pages are not affected.
- I.K.E.'s own icons follow a change of interface colours at once, without a
  restart.
- Long check box texts in Settings → Appearance wrap instead of making the page
  scroll sideways.

**Languages**
- Chinese (Simplified) and Japanese. Qt's own texts (dialog buttons) are
  translated too. New optional dependency: `noto-fonts-cjk`.
- `tools/check-lang.py` checks every language pack for missing strings and for
  broken placeholders, accelerators and final punctuation.

## 1.2.0

**Fingerprinting**
- Values that identify the computer now change from site to site and from
  session to session at Balanced and above: graphics card (a common model chosen
  per site, never the real one), plugins, number of CPU cores and the list of
  WebGL extensions, in addition to canvas, WebGL and audio. Cover Your Tracks'
  own measuring code reports a randomized fingerprint.
- The browser presents the current stable Chrome version in headers,
  JavaScript, workers and Client Hints. It is checked once a day against
  Google's public version list (no personal data is sent) and estimated from the
  calendar when the check is not possible, never ahead of reality.

**User scripts**
- New user script manager (Settings → User scripts): install from a file, from
  an address or by opening a `.user.js` link; enable, disable, remove; daily
  update check.
- Supported: `GM_getValue`, `GM_setValue`, `GM_deleteValue`, `GM_listValues`,
  `GM_addStyle`, `GM_addElement`, `GM_xmlhttpRequest`, `GM_setClipboard`,
  `GM_openInTab`, `GM_notification`, `GM_download`, `GM_getResourceText`,
  `GM_getResourceURL`, `GM_info`, `@require`, `@resource`, `@run-at`,
  `@noframes`, and the promise-based `GM.*` equivalents. A failing script does
  not affect other scripts or the page.

**Interface**
- Settings reorganised with a vertical, icon-labelled section list.
- Icons: follow the system, any icon theme installed on the computer, or the
  bundled Lucide and Phosphor sets. Interface colours: system, light or dark.
- Bookmarks that do not fit in the bookmarks bar are listed under a » button.
- Spanish, French, German and Portuguese translations included.

**Project**
- Source tree reorganised; the package is built from source by the PKGBUILD.

## 1.1.1

- YouTube ads: scripts are installed per profile and limited to their sites, so
  they reach the page being loaded (before, they reached the page being left
  when the site changed).
- Filter lists: `!#if` directives are honoured for a Chromium engine, and
  `!#include` sub-lists are downloaded.

## 1.1.0

- I.K.E. AdBlock Engine: a native module built on adblock-rust 0.13.5, with the
  previous binding kept as a fallback.
- uBlock Origin scriptlets for list rules that need them.
- Widevine is located or downloaded by I.K.E. itself, with the user's consent.
