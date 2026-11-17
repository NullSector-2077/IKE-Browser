# Changelog

## 1.1.8

- **New tab page**: I.K.E.'s own picture (the Earth with its network of
  lights, by the project's owner) is the background photo unless the user
  chooses another. Whoever had no photo gets it once; whoever removes it keeps
  the page plain. Settings → New tab page has a "Default" button beside
  "Choose…" and "Remove" to go back to it (the user's copy is then deleted).
  The picture is dark: on a light interface the page takes the colours of the
  I.K.E. theme while it is shown, so its text stays readable; a photo of the
  user's keeps the interface colours as before. The picture is kept with the
  program (167 KB, JPEG), nothing is copied or downloaded, and a website
  cannot load it.
- The **veil** over any background photo is now a layer of the page's own
  background instead of an element of its own over the page: the same look,
  one painted surface less (about 15-20 MB less memory with a photo).

Measured against 1.1.7, package against package (1.1.7 without a photo, 1.1.8
with its own): start-up (0.28 – 0.31 s against 0.31 s) and processor time at
rest (0.75 % of one core) unchanged; memory 397 – 399 MiB against 369 MiB
(+28 MiB, the photo decoded and painted; it was +45 – 55 MiB before the veil
change), while using the interface, which opens new tabs, 7.5 – 8.7 % against
6.1 – 6.4 %. Whoever removes the photo is back to 1.1.7's figures.

## 1.1.7

- The **address bar** takes half of the window (it was 60 %; a setting left at
  the old 60 becomes 50 once).
- **Short messages** (the zoom, notes such as "No article text was found") in
  a rounded pill at the bottom of the page that fades in and out, instead of
  the status bar line.
- **Find bar** (Ctrl+F): "3 of 12" in a small pill, the field softly tinted
  red when nothing is found, Shift+Enter for the previous match, the arrows
  with their keys in the tooltip.
- **Shield**: when its number grows, a small "+N" rises from it and fades.
- The **site's icon** beside its name in the shield panel and in the site
  panel.
- **Settings**: the pages change with a short fade (their order is unchanged).
- **New tab page**: a Settings button at the top right and a "Background
  photo" button at the bottom left (it opens Settings → New tab page), both as
  large as the site tiles; the clock and the weather moved to the bottom right;
  the logo and "Internet Kontrol Experience" always stay, with a soft shadow
  that keeps them readable on a photo. A website cannot use those buttons
  (refused, as the tiles' answers).

Measured against 1.1.6, package against package: start-up (0.28 – 0.32 s),
processor time at rest (0.6 – 0.7 % of one core), while using the interface
(5.7 – 6.6 %) and memory (354 – 356 MiB) unchanged within the measuring noise.

## 1.1.6

- The **address field** is the system's own again (the rounded one of 1.1.3
  is switched off; suggestions with icons and the zoom sign stay).
- **Toolbar icons** a little larger (24 pixels instead of 20); the window
  buttons keep their size.
- **Phosphor Bold**, a set of thicker icons, ships with I.K.E. (Settings →
  Appearance → Icons).
- **Translate page** is now a sign in the address bar, shown on web pages, as
  in other browsers. **Bookmark this page** takes its place on the toolbar
  (its star fills when the page is a bookmark); a toolbar arranged by the user
  keeps its order, with the bookmark where the translation was.
- **Maximize button**: the diamond of Plasma's "restore" while the window is
  maximized or full screen, the arrow otherwise; minimize and maximize show a
  soft circle in the theme's colour under the mouse, as the close button does.
- The arrow of the **Downloads** button moves gently while files arrive.
- A **thin line** between the bars and the page.
- **Smooth scrolling** of pages, on by default (Settings → General; it takes
  effect after a restart).
- Already there: the tooltips of the toolbar buttons name their keyboard
  shortcut.

Measured against 1.1.5, package against package: start-up (0.29 – 0.30 s),
processor time at rest (0.6 – 0.7 % of one core), while using the interface
(5.3 – 6.7 %) and memory (353 – 354 MiB) unchanged within the measuring noise.

## 1.1.5

More finish, in the colours of the theme in use; each touch can be switched
off on its own in `ike/polish.py`.

- **The shield pulses**: a ring opens once around it when it blocks something
  on the page in view (at most every 1.5 seconds; with "Interface effects"
  only). The touch of the old Cyber theme, without the rest of it.
- **Shield panel**: what was blocked on the site, as bars by kind (ads and
  trackers, scripts, cross-site cookies, upgrades to HTTPS, tracking
  parameters), shown when something was blocked.
- **Downloads window**: the icon of each file's kind and a slim progress bar
  under its size.
- **Search suggestions** show the search engine's own icon (once its site was
  opened), a magnifier otherwise.
- **Reader mode**: light, sepia or dark and the size of the text, chosen on
  the page and remembered; the site and the reading time under the title.

Measured against 1.1.4, package against package: start-up (0.27 – 0.29 s),
processor time at rest (0.6 – 0.7 % of one core), while using the interface
(5.9 – 7.1 %) and memory (352 – 354 MiB) unchanged within the measuring noise.

## 1.1.4

**Page dark mode with Dark Reader, as its extension does it.** Dark Reader was
in I.K.E. but parts of some sites (Google Translate, for one) came out wrong.
Four causes, all fixed:
- The first site opened in a tab (from the new tab page) was not darkened at
  all: the script was given to the page when it started to navigate, and the
  engine had already started the site in another process. Dark Reader's
  scripts now belong to the profile, as the extension's do.
- Dark Reader's style-sheet proxy, which catches the styles sites make with
  JavaScript, was put into the page as an inline script, which strict
  Content-Security-Policies (Google's sites) block. It now runs in the page's
  own world, where no policy stops it, started with the extension's own event
  (with a token of the session in its name, so a page cannot start it).
- The extension's lists were missing: its fixes for single sites (about
  3,000), its list of sites that are dark already (left alone), and the hints
  of its detector. They are now in I.K.E. (`ike/resources/darkreader-data.json`).
- The detector of a site's own dark theme was missing: a site with its own
  dark theme is now left as it is, as in the extension. A site you turned dark
  yourself is always made dark.
Dark Reader's engine and lists are followed by the daily maintenance like the
other components (`tools/build-darkreader.py`). The engine of Qt stays as the
other choice; no setting changed.

New:
- **Zoom kept for each site**: Ctrl + wheel, the View menu or the keys; the
  site opens at that zoom again; "Actual size" forgets it. Not kept in private
  windows.
- **Videos and sounds that start by themselves** can be blocked (Settings →
  General; off by default), for all sites or, from the site panel, for one.
- **Site panel**: a click on the lock in the address bar shows the connection,
  the permissions, the cookies (with "Clear this site's data"), the protection
  level, the zoom (with "Actual size") and whether videos and sounds may start
  by themselves on the site.
- **Command bar (F2)**: type a few letters to reach a menu command, an open
  tab, a bookmark, a page of the history or a page of the Settings. F2, as in
  Vivaldi, not Ctrl+K: many sites (GitHub, Slack, Discord, Notion) use Ctrl+K
  themselves.
- **Pages for sites that cannot be reached** (site not found, no connection,
  refused, too slow, interrupted) in I.K.E.'s look, with "Try again". The
  address and the history stay those of the site. Certificate warnings stay
  the engine's own.
- **Mouse gestures**, off by default (Settings → General): hold the right
  button and draw ← back, → forward, ↑ reload, ↓→ close the tab. A right
  click alone opens the menu as always.
- The daily maintenance tool accepts a README that names any package release
  (`-2-`), not only `-1-`.

Measured against 1.1.3 on the same machine, package against package, with
dark mode off and on: start-up (0.28 – 0.31 s), processor time at rest
(0.5 – 0.7 % of one core), while using the interface (5.7 – 6.5 %) and memory
(354 – 356 MiB) are unchanged within the measuring noise. The package is
about 0.3 MB larger (Dark Reader's lists).

## 1.1.3

A more modern finish, one small touch at a time, all in the colours of the
theme in use (the system's or an interface theme). Light on purpose: nothing
moves while the browser is still; the moving parts follow "Interface effects"
and the desktop's "no animations", and without them everything changes at
once. Each touch can be switched off on its own in `ike/polish.py`.

Tabs:
- **A line under the current tab** in the accent colour (on the left edge of
  the row with vertical tabs) that glides to the tab you open.
- **Long titles fade out** at the edge of the tab instead of ending in "…".
- A tab's **icon changes with a short fade**: the site's icon arriving, the
  loading mark leaving.
- Vertical tabs: the **hover colour comes and goes softly**, and a **new tab
  fades in** from the left.
- The **speaker of a tab playing sound pulses** gently, only while it plays.

Address bar and toolbar:
- The **address field is rounded**, and its edge lights up softly in the
  accent colour while you type.
- **Suggestions** have taller rows with the **site's icon** (a magnifier for
  searches) and fade in.
- A **zoom sign** appears in the address field when the page is not at its
  usual zoom; a click on it brings the page back.
- **Reload and Stop** change into each other with a short fade.

Bars and the rest:
- The **find bar**, the **repair bar** and the **full-screen notice** fade in.
- The **tab preview** fades in, and its picture blends from one tab to the
  next.
- The **loading line** starts soft and reaches its full colour a little
  further on.
- A **finished download** shows a **tick** in its green ring, with a small pop.

New tab page:
- **More site tiles**: up to 32, **sixteen per row** on a wide window (seven
  before); they wrap on narrower windows.
- The tiles **lift a little** under the mouse. (A fade-in of the whole page
  was tried and left out: it cost the engine work at every new tab.)

Already there, so not added again: the lock in the address field and the
number of blocked items beside the shield.

Measured against 1.1.2 on the same machine, package against package: start-up
(0.29 – 0.30 s) and processor time at rest (0.5 – 0.7 % of one core) are
unchanged; while the interface is used without pause (menus, hover, tabs
opened and closed every two seconds) 5.2 – 5.5 % of one core instead of
4.9 – 5.0 %; memory 354 – 355 MiB instead of 353 MiB.

## 1.1.2

- **The "I.K.E. Cyber" theme is gone.** It had problems and the owner chose
  not to keep it. Whoever used it starts with "Follow the system" (the
  default); its settings (accent colour, tab shape, glow, cut corners, the
  grid of the new tab page and the suggestion) are removed from
  settings.json, every other setting stays as it was. With it went what only
  the Cyber theme drew: its tab shapes, the cut address field, the square
  menus, the shield's pulse, the equaliser on tabs playing sound, the ring of
  blocked items in the shield panel, the accent frame of the tab preview, the
  counter that counted up and the "Try the Cyber theme" suggestion on the new
  tab page and in Settings. Kept: the other interface themes (I.K.E., Night,
  Paper, Forest, High contrast and your own), the interface effects (menus
  fading in, the loading mark, the soft change of theme), the site tiles, the
  monthly counter and the "New tab page" settings.
- **Twelve Slavic languages**: Russian, Ukrainian, Belarusian, Bulgarian,
  Polish, Czech, Slovak, Slovenian, Croatian, Serbian (Cyrillic), Bosnian and
  Macedonian, every text of the interface translated. Chosen in Settings, or
  taken from the system's language. Made with AI and not yet reviewed by
  native speakers: corrections are welcome.
- "Engine" in Help → About is now translated as the browser engine in German
  and Spanish (it read "search engine").
- Updates itself from 1.1.1 and 1.1.0 (only the browser's own files changed).
- Package `ike-browser-1.1.2-2`: a new number, so it cannot be mistaken for an
  earlier test build of 1.1.2 without the Cyber removal.

## 1.1.1

- **Help → About tells which video and audio formats play** (H.264, AAC,
  HEVC, VP9, AV1, Opus, MP3) and which do not. I.K.E. ships no codec of its
  own: what plays depends on the engine installed on the system (on Arch
  Linux, Qt WebEngine built with the system's FFmpeg). When a video does not
  play, About now shows whether the engine of this system can play its
  format at all. The engine is asked once per session, when About is first
  opened, in a blank private page that is thrown away at once; no web page is
  involved and nothing is written to disk.
- **Help → About shows how old the engine is**: how many Chrome versions it is
  behind the current one (the Chrome version I.K.E. already checks once a
  day for the fingerprinting protection).
- Updates itself from 1.1.0 (only the browser's own files changed).

## 1.1.0

A theme of I.K.E.'s own and a richer new tab page. "Follow the system" stays
the default and looks and behaves as before; no setting was reset.

- **The "I.K.E. Cyber" theme** (Settings → Appearance → Interface colours, or
  "Try the Cyber theme" on the new tab page): dark, one accent colour, cut
  corners and thin luminous lines, the same on every system. Drawn with what
  Qt already offers: no new library, no blur behind the window.
  - Three **tab shapes** to choose from, for horizontal and vertical tabs:
    *Cut* (one cut corner, a line above the current tab), *Blade* (slanted
    sides, a line below), *Viewfinder* (no fill, the current tab between two
    brackets). Dragging, closing, groups and the loading mark work as before.
  - Accent colour (five ready ones or any other), glow and cut corners can
    be switched in Settings.
  - The address field has a cut frame that lights up when it is used; the
    toolbar buttons light a corner under the mouse; menus are square with
    luminous separators.
  - Light effects, all under the existing "Interface effects" switch and off
    when the desktop asks for no animations: the mark of the current tab
    glides to the new tab, the shield pulses once when it blocks, the
    counter counts up, the bars of a window fade into a new theme.
  - A tab that plays sound shows a small equaliser; the shield panel shows a
    ring of what was blocked by kind; the tab preview has an accent frame;
    the colour of a tab group is a luminous mark on the tab's edge.
- **Suggested once, never imposed.** The new tab page suggests the Cyber
  theme one time ("Try the Cyber theme" / "Not now"); while it is on trial
  the same place offers "Keep it" / "Back to the system theme". Settings
  mark "Follow the system" as the default and Cyber as recommended.
- **Counter per month.** The new tab page shows the trackers and ads blocked
  this month and last month and starts again on the first of each month. The
  total since installation goes on being counted and can be shown instead
  (Settings → New tab page). The month's count starts from zero with this
  version; the total is untouched.
- **Site tiles on the new tab page**: your bookmarks or the sites you visit
  most (worked out from the history on this computer), or none; a tile to
  add a site; a tile can be hidden without deleting the bookmark.
- **Settings → New tab page**: a page of its own for tiles, counter, clock,
  weather and the background photo (the photo was at the bottom of
  "General", where it was hard to find).
- Security: titles and addresses shown on the new tab page are escaped and
  only web addresses become tiles; the answers the page gives for the user
  (hide a tile, add a site, switch the theme) are refused when they come
  from a website. Both with attack tests.

Not in this version: tabs do not slide when they open and close (Qt's tab bar
adds and removes them at once), and menus have square, not cut, corners.

Measured against 1.0.3 on the same machine, package against package. With
"Follow the system": processor time at rest (0.9 – 1.0 % of one core),
start-up (0.30 – 0.34 s) and memory (354 → 357 MiB) are unchanged; a new tab
costs about 5 ms more of processor time (108 → 113 ms over all processes),
because the page shows more. With the Cyber theme: the same at rest, start-up
0.32 – 0.33 s, 370 MiB, a new tab about 130 ms.

## 1.0.3

A review of the whole code and a security audit; the full report is in
[docs/review/](docs/review/README.md). No feature was removed and no setting
changed its meaning.

Security:

- **A page opened from a file can no longer read other files.** Before, a
  saved web page could read any file the user can read and send it away. Now
  a local page never reads files with scripts; pictures, video, style sheets,
  scripts and fonts next to it still load, and frames only from the page's
  own folder. Saved pages keep working.
- **Web pages cannot load I.K.E.'s own addresses** (`ike:logo`, `ike:newtab`
  in a frame): a site could recognise the browser that way.
- **A link that starts another application asks first** (`mailto:`, `magnet:`
  and the private kinds of installed programs), showing the exact address
  handed over; a tab in the background starts nothing.
- **"Cookies and site data" also removes local storage, databases and service
  workers** (from "Clear browsing data" and with "clear when closed"). Cookies
  go at once; the rest when I.K.E. is started again, as the engine cannot
  delete it while running — the dialog says so.
- A second start of I.K.E. hands its addresses over through a socket in the
  user's own runtime folder; the old name in the shared temporary folder is
  only trusted when it belongs to the same user.
- Desktop notifications: the title of a page can no longer add options or
  markup to the notification.
- Copying a password marks it as secret for the clipboard manager (the hint
  Klipper follows to keep it out of its history) and clears it after 45
  seconds; exported passwords and
  the vault are created readable by the owner only from the first byte.
- The update channel, the state of the self-update and the version folder
  name are checked before use; the test switches of the browser only work
  inside the test harness.
- Filter-list conditions are read by a small parser instead of Python's
  `eval`.
- Help → About shows the Chromium security patch level of the engine and warns
  when the engine's sandbox is off.

Stability:

- An error in one handler of the interface no longer ends the whole browser:
  it is written to `errors.log` in the cache folder, counted in Help → About,
  and the browser goes on.
- Closing I.K.E. while a download in the background (filter lists, Chrome
  version, updates) is still running no longer ends with an abort.
- A fault inside the ad-blocking engine becomes an error the browser handles
  (that request is not filtered by the engine; the other protections still
  apply) instead of ending the program. Needs the package: the engine is not part of the self-update.
- Settings of the wrong kind in `settings.json` (edited by hand or damaged)
  fall back to the default instead of stopping the start.

Other:

- pyo3 (the Python–Rust bridge) 0.23 → 0.30, which closes two published
  advisories; neither affected code I.K.E. uses.
- Applying the settings no longer reloads an unchanged filter engine
  (0.3 s with the default lists).
- Unused code removed; every message of the interface is now checked for a
  translation by `tools/check-lang.py`.
- Measured before and after on the same machine: start-up, opening a tab,
  loading a page, processor time and memory are unchanged.

## 1.0.2

- **Toolbar buttons can be moved reliably.** A long press and drag, or the new
  "Customise toolbar" mode (right-click the toolbar, or the View menu), where
  the buttons show an outline and are dragged at once. A marker shows where
  the button will land, on either side of the address bar; the arrangement is
  saved and shown in every window, and "Reset to default layout" brings back
  the original one. Back, Forward and Home and the separator after them stay
  in place. (Before, the toolbar rebuilt the dragged button at the first
  movement, so the drag stopped and nothing was saved.)
- In a narrow window the buttons that do not fit are listed under a » button
  instead of pushing the menu and the window buttons out of view.
- Back, Forward and Home can now really be hidden from "Toolbar buttons" (the
  choice was offered in Settings but had no effect).
- **New tab page: your own photo as background** (Settings → General): fill
  the page, show the whole photo or centre it, with a veil in the page's own
  colour to keep the text readable. A copy is kept in I.K.E.'s data folder
  (scaled down once if larger than a 4K screen) and is never sent anywhere; web
  pages cannot load it. The interface colours and the theme do not change.
- **Interface effects**, all light: the shield panel and the menus fade in, the
  red of I.K.E.'s own close buttons glides in on hover, the loading line
  advances smoothly, and a tab that takes a while to load shows a small
  turning mark. They are off when the desktop is set to show no animations
  (Plasma's animation speed at "Instant") and can be turned off in Settings →
  Appearance. Processor time, memory and start-up measured before and after:
  no difference (`tests/measure_idle.py`, `tests/measure_startup.py`).
- Tooltips of buttons and menu entries also show the keyboard shortcut.
- Two messages that were shown only in English are translated.

## 1.0.1

- The logo, the application icon at every size and the new tab page show
  "I.K.E"; the lettering of the logo and of the full name, "Internet Kontrol
  Experience", is drawn as shapes from the Orbitron typeface (SIL Open Font
  License), so it looks the same on every system and needs no font installed.
  The interface fonts are unchanged.
- The shield in the toolbar is drawn about 18% larger inside the same button,
  and is now sharp at every screen scale. Ad blocking is unchanged.
- Hovering a link no longer shows its address in a bar at the bottom of the
  window, so the page no longer moves. The bar still appears for zoom and
  toolbar messages.
- Removed the one-time import of the earlier installation, which every
  installation has completed. A password vault that was never opened with
  I.K.E. 1.0.0 must be opened once with 1.0.0 before updating.
- This release changes the icons installed with the package, so it is installed
  as a package (`sudo pacman -U …`); I.K.E. 1.0.0 announces it instead of
  updating itself.

## 1.0.0

First release of I.K.E. — Internet Kontrol Experience, for Arch Linux and
CachyOS.

- Privacy shield with five levels (Off, Compatibility, Balanced, Strict,
  Maximum), per-site levels and "Repair this site".
- I.K.E. AdBlock Engine (adblock-rust) with EasyList, EasyPrivacy, uBlock
  filters and regional lists, cosmetic filtering, uBlock Origin scriptlets and
  YouTube video-ad removal.
- Fingerprinting protection that changes per site and per session, including a
  common graphics-card model instead of the real one; the presented Chrome
  version follows the current stable release automatically.
- Password vault (AES-256-GCM), passkeys and security keys, user scripts with
  per-script permissions, containers, workspaces, tab groups, split view,
  vertical tabs, watched pages, site resources, Widevine installed on request.
- KDE Plasma integration: media controls, downloads, KRunner, KDE Connect.
- Interface themes, icon sets and eight languages.
- Signed self-update from GitHub releases with automatic roll-back.
- Daily automatic check of the bundled components, with a tested candidate
  release prepared on GitHub Actions for the owner to approve.
- At the first start, the settings, bookmarks, history, passwords, cookies and
  user scripts of the earlier installation are imported; the old folders are
  removed once I.K.E. has started correctly.
