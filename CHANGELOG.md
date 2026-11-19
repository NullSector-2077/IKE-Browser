# Changelog

## 1.1.17

Security review (each point has a test that plays the attack on this computer).

- **Saved passwords are offered, never filled by themselves**: clicking (or
  tabbing) into a login form opens a small menu of I.K.E. under the field,
  "Fill in: name" for each saved login of the site and "Not now"; only the
  login chosen reaches the page, and after "Not now" the page is not asked
  about again. Until now the password was filled as soon as a form appeared,
  and a script of the page (an advert, a comment) could build a tiny invisible
  form and read it. Clicks, focus or key presses made by the page's own
  scripts open nothing; the page never sees the menu. A user name already
  typed shows only its own login.
- **Warning for passwords on unencrypted pages**: clicking into a login form
  of a plain http site (not this computer or the home network) says once that
  others on the network can read what is typed there; the menu says it too.
- **Permission questions of background tabs wait**: a site in a tab the user
  is not looking at (camera, microphone, notifications, location...) is asked
  about only when its tab is shown, so its question never appears over another
  site's page; asked over and over meanwhile, it is one question.
- **A burst of downloads asks first**: a site that starts one download after
  another by itself gets its first file, and the rest wait for one question
  ("Allow" for the rest of the session, or "Block"). Downloads right after the
  user's own click, typing or Save never ask.
- **Stronger password vault**: the key of the vault is derived with four times
  the work (scrypt N = 2^17, about a third of a second once when it is opened)
  so guessing the master password of a stolen file is four times slower. An
  existing vault opens as before and is sealed again with the new strength at
  once; nothing is lost. A vault file naming any other key settings than
  I.K.E.'s two is refused at once, before any work: a doctored file cannot
  make the unlock take gigabytes of memory.
- **Dark mode never reads the home network for a web site**: the style sheets
  that dark mode fetches for a page (those the page cannot read itself) are no
  longer fetched from this computer or the home network (router, printer, a
  program listening here), also after a redirect or through a name that points
  there; a page of the home network itself still gets its own.
- **User scripts update themselves only safely**: the daily check uses only
  https addresses, and an update that asks for more than the installed version
  (more sites, more GM_ functions, more hosts) or loads code over plain http is
  shown to the user first, as a new script is.
- **Code in the address bar is not run**: a "javascript:" address typed or
  pasted in the address bar would run inside the site in view, with the
  user's account (the "paste this to get a gift" scam). It is refused there;
  bookmarks that run code (bookmarklets) still work.
- **No silent fallback to an unprotected connection**: when the secure (https)
  address of a site asked for over http does not answer, the page stops and a
  bar says why, with "Continue without protection" for this session. Until
  now I.K.E. went to http by itself, which someone on the network can force.
- **Sites that spread malware are blocked**: the Malicious URL Blocklist
  (abuse.ch URLhaus, CC0 / MIT; on by default in uBlock Origin) is on for new
  and existing users. A whole page the lists block shows a bar that says so,
  with "Continue anyway" for this session.
- **Warning when the web engine misses security fixes**: when the system's
  qt6-webengine is five or more Chrome versions behind with its security
  fixes, a notice (once per session) and Help -> About say to update the
  system.
- **The Passwords window asks for the master password** before it shows,
  copies or exports a saved password (once every five minutes), so whoever
  sits at a computer left with the vault open cannot read them all. Filling a
  login into a site is unchanged.
- **GitHub actions pinned by their commit**: the tests and the automatic
  fixes run exactly the code of the actions that was checked, not whatever a
  moved tag points to; Dependabot keeps them current.
- **The browser's own requests keep no cookies** (search suggestions, site
  icons, weather, downloads of extensions and languages): a search engine can
  no longer tie together the words typed in the address bar. User scripts keep
  theirs, as before.

## 1.1.16

- **Vertical tabs with only their icons**: a button at the top of the vertical
  tab panel narrows it to the tabs' icons (the title shows when the mouse rests
  on one; the middle button or the tab menu closes it) and back to the titles,
  with the width the user had given the panel. The choice is kept.
- **New hover shape**: the highlight behind a toolbar button under the mouse
  is no longer a circle but a rectangle with rounded corners and a faint
  outline fading downwards, in the theme's colour; the short messages over the
  page (zoom, notes) take the same shape. The window buttons keep their round
  highlight and the red one of Close.
- **Video decoding with the graphics card** (Settings -> General): Automatic
  (the default: the engine decides, as before), On (experimental) or Off.
  Qt WebEngine already decodes videos with the graphics card where it can
  (Intel, AMD, with the VA-API driver); with NVIDIA's own driver it turns it
  off, and On asks for it anyway (with libva-nvidia-driver). If I.K.E. does not
  close normally while it is on, the next start goes back to Automatic and says
  so. Off helps when a driver shows videos wrongly.
- **Menu next to the window buttons**: the menu button is now fixed right
  before Minimize, with the fixed separator on its left, so it sits with the
  window buttons; with the system's title bar it is the last button. It can no
  longer be moved (the other buttons still can).
- **Email links**: a "mailto:" link is now written with the service the user
  chooses, as in other browsers: Gmail, Outlook.com, Proton Mail or Yahoo Mail
  open in a new tab with the address, subject and text already filled in, or
  the computer's mail program takes it. I.K.E. asks at each link until a choice
  is remembered (Settings -> General -> Email links). I.K.E. can also be chosen
  as the system's program for email links (System Settings -> Default
  Applications): links clicked in other programs then open in the chosen web
  mail.
- **Site colour on the address bar's edge**: the colour of the site now draws
  only a thin outline around the address bar, with the same short fade; the
  toolbar keeps the theme's own colour (the tinted toolbar of 1.1.14 was too
  much). The option is still in Settings -> Appearance.
- **Peter Lowe's list off by default**: its author states no licence for it,
  and uBlock Origin's wiki lists it as non-commercial; until the author
  confirms the terms for I.K.E., the list is off for new and existing users
  (once: whoever turns it on again keeps it on). The other lists already cover
  almost all of its servers.
- **Licences and credits checked against their sources**: EasyList Italy is
  under EasyList's licence (GPL-3.0 / CC BY-SA 3.0), the EasyList Cookie List
  under CC BY 3.0, as its own header states; the filter lists are now listed
  one by one with maintainer, licence and default in docs/THIRD-PARTY.md, with
  the origin of the new tab picture and of the fallback icons, Dark Reader's
  version, uBlock Origin's copyright line (also recorded in the scriptlet
  file) and where adblock-rust's source is. None of the Rust libraries has a
  NOTICE file to carry.

## 1.1.15

- **Same site, free way (faster pages, fewer broken sites)**: at Balanced and
  Compatibility, what a site asks of itself (its own pictures, scripts, styles
  and data) is no longer checked against the filter lists, as Brave does in its
  standard mode. Most of the requests of a page are the site's own, so the
  content blocker has much less to do, and the sites that broke because one of
  their own parts was blocked work again. The ads and trackers of other
  companies stay blocked, the hiding of ad boxes stays on, Strict and Maximum
  check every request as before, and the video sites (YouTube, whose ads come
  from YouTube itself) are always checked at every level.
- **Speech voices hidden**: the list of the speech-synthesis voices installed
  on the computer tells systems and their language packs apart. At Balanced a
  site now sees only the voices of the page's languages and English (enough to
  read aloud), at Strict and Maximum only the default voice.

## 1.1.14

- **Google's sensitive services work with the shield on**: on AI Studio, the
  Cloud Console, the Google account and Google's payment pages, creating an API
  key (or a similar protected operation) could still end in "permission denied"
  with the shield on, and worked only after switching the shield off. Since
  1.1.12 these pages got "Compatibility", but the filter lists still blocked
  some of Google's own requests there. Now Google's own requests on these
  pages go through untouched, as with the shield off: no filter list, no
  changed header, no address clean-up, no list scripts, nothing changed in the
  page (an embedded Google sign-in frame keeps its normal identity too). The
  trackers of other companies stay blocked, every other site keeps its
  protections, YouTube is not touched, and a level the user chose for one of
  these sites is still respected. Brave reaches the same result with a list of
  hand-written exceptions.
- **Payments with PayPal and Stripe**: their anti-fraud checks can refuse a
  payment or a sign-in when part of them is blocked or changed (Brave users
  report PayPal sign-ins that work only with the shield off). PayPal's sign-in
  and Stripe's checkout page get the same treatment as Google's sensitive
  services, and in every shop PayPal's and Stripe's own parts (payment buttons
  and fields, their anti-fraud checks, their frames and cookies) are left
  alone. The rest of the shop keeps its protections. Any other site that
  refuses an operation can still be fixed from the shield with "Repair site".
- **Sosia, the lookalike warning**: when the address of a page imitates a
  famous site (banks, Poste, PayPal, Amazon, Google, Apple, Microsoft, social
  networks, couriers, crypto exchanges...), a bar above the page says so:
  "Careful: paypa1.com looks like PayPal, but it is not PayPal". It recognises
  the tricks scams use: digits and look-alike letters ("paypa1", "arnazon"),
  letters of other alphabets that look the same, a real address in front of a
  false one ("paypal.com.secure-login.xyz"), two letters swapped or a double
  letter. Nothing is blocked; "This site is fine" remembers the site. The check
  runs on this computer only, once per opened page, and is tested against more
  than 10,000 real sites with names close to the famous ones: none of them is
  flagged. On by default (Settings -> Privacy).
- **Site tint**: the navigation bar takes a light tint of the site's own colour
  (the colour a site declares for browsers, or the main colour of its icon),
  with a short fade; greys give none and I.K.E.'s own pages keep the normal
  bar. The colour is read in I.K.E.'s isolated world, never seen by the page.
  On by default (Settings -> Appearance).
- **Credits**: Help -> About lists the projects I.K.E. is built on with their
  licences (adblock-rust by Brave, uBlock Origin, EasyList, Dark Reader, Qt and
  Chromium, PyQt6, icons and the logo typeface), the README has the same list,
  and docs/THIRD-PARTY.md now follows the AdBlock engine by itself: the daily
  maintenance rewrites it when the engine moves to a new version.
- **Honest version number**: I.K.E. now tells sites the Chrome version of its
  own engine (for example 140) instead of the newest Chrome (157). A site can
  test which features the engine really has, so the old claim was easy to
  catch, and anti-abuse checks treat a browser that says one version and
  behaves like another as suspicious. The same version is given everywhere
  (address requests, client hints, JavaScript) and follows the engine by itself
  when Arch updates it. The fingerprinting protection is unchanged; Help ->
  About still shows how many versions the engine is behind the newest Chrome.

## 1.1.13

- **Updates install by themselves for everyone**: "Install automatically" is
  now the default of Settings -> I.K.E. updates. Users only browse: every signed
  release is downloaded, checked and installed by itself (once a day at most) and
  used at the next start. Whoever had the old default "Ask before installing"
  moves to automatic once; "Do not check" stays the user's own choice.
- **Faster pages** (from a comparison with Brave on YouTube: less blocking
  time, an earlier main picture, fewer requests):
  - the cookie-banner handler no longer weighs on the page while it loads: one
    query for all the known "reject" buttons instead of about forty, no layout
    work to read the text of every button, and its looks run in the page's
    idle time;
  - I.K.E.'s own rules, next to the lists, block the telemetry of YouTube and
    Google the lists let through (quality and ad reports, event logs,
    performance pings), never the watch history or the video servers;
  - each request is checked by the AdBlock engine without looking up again how
    to ask it;
  - the disk cache grows to 512 MB, so a second visit takes the big scripts
    of a site from the disk;
  - the login helper stops watching a page once its login is filled in.
- **Runs on old processors too** (an i5-3570K, for one): the AdBlock engine
  and the launcher are built for every x86_64 processor, not for the newer
  one of the computer that builds the release, whose code could stop with
  "illegal instruction" elsewhere.

## 1.1.12

- **Every release now reaches every user by itself**, the AdBlock engine
  included: the engine built for a release travels inside the signed
  self-update (`ike/_engine`) and is used first; the installed one stays as the
  fallback. A new engine no longer needs a new package, so the minimum system
  goes back to 1.0.1 and 1.1.10 and 1.1.11 update to this version by
  themselves, without commands.
- **Pages can no longer see I.K.E. where nothing was asked**: the media
  commands of the desktop (next / previous in Plasma) touch only the pages of
  media sites (YouTube, Spotify, SoundCloud, Twitch and others, setting
  `media_sites`). Before, they changed every page, even with the shield off, and
  anti-abuse checks noticed it: Google AI Studio sometimes refused to list or
  create API keys ("permission denied").
- **Google's sensitive services** (AI Studio, Cloud console, account, payments,
  admin) get "Compatibility" by themselves, like the sign-in pages; a level
  chosen by the user for them is kept.
- **Lighter fingerprinting protection**: the guard that protects the frames a
  page adds looks only at insertions that can bring a frame, and remembers
  frames already protected. On a page that changes itself a lot, its cost
  drops from about 60% to about 15% of the page's own work; every frame stays
  protected.

## 1.1.11

- adblock-rust (AdBlock engine): 0.13.5 -> 0.13.6 (system part: raise __min_system__ and adapt ike-adblock/src/lib.rs if the API changed)
- Qt WebEngine / PyQt6 (tests): Qt 6.12.0, WebEngine wheel 6.140.0 -> Qt 6.12.0, WebEngine wheel 6.140.0 (PyQt6 6.12.0 -> 6.12.1, PyQt6-WebEngine 6.140.0 -> 6.140.1; Arch Linux qt6-webengine 6.140.0)
- AdBlock engine system component updated; minimum compatible system package is now 1.1.11.

## 1.1.10

- **The shield is inside the address bar**, at its right end, with its number
  beside it (1.1.9: outside, left of the bar, with a small arrow). A click on it
  opens its panel as before. The field's own buttons (clear, translate, zoom)
  sit left of it and the address stops before them; the "+N" still rises right
  of the number. The address bar gets the room the shield had in the toolbar.
- **The search engine, right after the lock** in the address bar: the icon of
  the engine in use; a click lists the installed engines, each with its own
  icon, and the one chosen becomes the default (as in Settings -> Search). The
  same in the new tab page's search box, with the mouse or the keyboard (arrow
  keys, Esc). The icons are the engines' own, asked once from each engine's
  site (its favicon) and then kept; until one is known a magnifier shows. Only
  I.K.E. and its own pages can choose the engine, never a website.

- **The shield's panel stays on the screen.** With "Advanced controls" open it
  went past the bottom of the screen and did not always take its size again:
  now it is never taller than the room below the shield, a scroll bar appears
  when it does not fit, and it grows and shrinks with its content.

Package 1.1.10-3 (1.1.10-1 and -2, never published, had the first parts). From this release on, every new release raises the last
number of the version (1.1.10, 1.1.11, ...); the package number after the dash
changes only when the same version is built again.

## 1.1.9

**Plasma integration**, made complete (all through D-Bus, nothing to install,
nothing running while unused):

- **Downloads**: when a download is done, Plasma's notification offers "Open"
  (with the file's own program) and "Open Containing Folder" (the file shown in
  the file manager). I.K.E. now tells Plasma that a download is one file and
  gives its folder as the destination, as KDE's own copy jobs do; before, Plasma
  took the job for several files and "Open folder" tried to open the file as a
  folder, which did nothing.
- **Task manager**: I.K.E.'s icon shows the progress of the downloads and how
  many are running (the LauncherEntry signal Plasma follows, as Dolphin and
  Firefox), and clears when they end.
- **Media: next and previous.** The media keys and Plasma's media widget can go
  to the next or previous track or video where the site offers it (YouTube,
  music sites: whatever a site declares with the Media Session API). A small
  script in the page's own world keeps the site's two commands for the desktop;
  the page sees the usual native functions, and only I.K.E. can send the
  commands (their event name holds a secret of the profile). Off with "Media
  controls" (Settings -> General), never in private windows.
- **Media: embedded players** (a video of another site inside an article) are
  found and controlled too: the frames of the page are read from I.K.E.'s own
  world, nothing is added to them.
- **KRunner**: the tabs it finds have "Mute tab" / "Unmute tab" (a tab playing
  sound) and "Close tab", as with Plasma Browser Integration. The first time,
  KRunner is told that its plugins changed (the signal System Settings sends),
  so I.K.E. is found at once instead of after a new login.

**Graphic touches** (with "Interface effects" on; all still without them or
when Plasma's animations are set to "Instant"):

- The **bookmark star** fills with a small pop when a page is saved.
- The **shield** fades from one protection level's icon to the next.
- A **dot** on a tab that finished loading in the background, until it is
  opened.
- **Vertical tabs**: a closed row fades out.
- **Toolbar buttons**: under the mouse a soft round highlight in the theme's
  colour comes in and goes, as on the minimize and maximize buttons (a pill
  for a button with text, such as the shield with its number).
- The **shield panel's bars** grow from zero when it opens.
- **New tab page**: the tiles come in one after the other.
- The **address bar** stays in the middle of the window when the shield's
  number appears (it stayed 8 pixels off until something else moved).

Package 1.1.9-2 (1.1.9-1 had the graphic touches and Plasma parts, without the toolbar below).
`docs/screenshots/ike-1.1.9.jpg` shows the new tab page with the default toolbar.

**Toolbar** (the owner's arrangement as the default):

- The **shield** has a fixed place right before the address bar, and **Reload**
  joins Back, Forward and Home at the start, followed by the fixed separator.
  None of them can be dragged; every other button still can.
- The default arrangement, for a new installation and for "Reset to default
  layout": dark mode, private window, clear this site's data, screenshot and
  split view on the left of the address bar; bookmark, downloads, reader mode
  and the menu on its right; the floating video starts hidden. A toolbar
  already arranged by the user keeps its arrangement (the shield and Reload
  simply leave its zones).
- The **menu bar** is off for a new installation (it takes room for little; the
  menu button has everything). Settings -> Appearance switches it on.
- In a very narrow window (under about 560 px with many buttons) the fixed
  buttons come first and the address bar takes what is left, down to 80 px,
  instead of Qt hiding the window buttons; and the toolbar looks again when
  the address bar gets narrower (it could stay with its last buttons under
  Qt's own overflow arrow). Where the buttons on the left leave too little
  room, the address bar keeps half of the window and stands as near to the
  middle as it can, as before.

Already there and checked again: the site's domain in normal text and the rest
of the address dimmed, the Downloads button's progress ring, the suggestions
fading in (on Plasma's Wayland session KWin itself fades pop-ups), the soft
change of interface theme.

Measured against 1.1.8-2, package against package: start-up (0.25 – 0.27 s
against 0.26 – 0.27 s), processor time at rest (0.80 – 0.85 % of one core
against 0.80 – 0.90 %) and memory (412 MiB against 411 MiB) unchanged; while
using the interface, which moves the mouse over the toolbar buttons, 8.6 – 9.6 %
against 7.8 – 8.5 % (the round hover gliding in and out). The Plasma parts work
only on events (a download, a click in the media widget, a KRunner search): the
media of a page is read once a second only while a tab plays sound, as before.

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
- **Shield**: the "+N" that rises when the number grows is drawn beside the
  number, bold, with a thin edge in the toolbar's colour, and stays a moment
  before it fades (1.1 s). It was drawn over the shield icon, in the colour of
  the icon's edge, and could not be seen.
- Settings → General: the "load restored tabs" line wraps, so the page needs no
  sideways scrolling in long languages (Russian).
- Package 1.1.8-2 (the first build was 1.1.8-1).

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
