# Changelog

## 1.1.32

- **WhatsApp and Telegram work at Kontrol** (the owner: they worked only at
  Compatibility and Balanced; WhatsApp turned into a white page after a
  change of level). The web compatibility campaign of 2026-11-28
  (docs/review/web-compat-2026-11.md: I.K.E. built with makepkg and
  installed in Arch, 44 sites at the four levels against Chromium 140 and
  Brave) proved the cause by lifting one rule at a time: since 1.1.25
  Kontrol and Maximum refused the sites' own service workers, shared
  workers and workers from their files, and unregistered older service
  workers; and where a site's policy refuses blob: workers (WhatsApp,
  Telegram, Google's apps, GitHub) the protected copy of a dedicated worker
  was refused a moment after the Worker object was made, so the fallback
  never ran and the site had no worker at all. WhatsApp's QR code was never
  drawn, Telegram Web K was an empty page (white without dark mode); the
  Dark Engine was not involved. Now Kontrol lets the site's own workers run
  (only the site's files can be in them) and keeps older service workers; a
  dedicated worker whose protected copy the policy refuses gets the site's
  own file inside the same Worker object (the messages posted meanwhile are
  delivered, the refusal is not shown to the page), and the document's later
  workers start from the file at once. Every worker a page's script makes
  from its own text keeps the protection. What these workers can read is in
  docs/SECURITY.md. The shield counts them ("Site's own workers allowed").
- **Maximum says when it refuses a site's own workers**: a bar above the
  page ("This level blocks the site's own background workers: the site may
  not work.") with "Allow them on this site", the same note and button in
  the shield, and the count of refused workers. Allowing them is remembered
  with the site's repairs ("Undo the repair" takes it back) and changes
  nothing else; the other sites stay as they are. "Repair this site" knows
  the workers as a protection of their own, tried right after the
  fingerprinting protection, so on WhatsApp it now turns off only the
  workers, not the whole fingerprinting protection
  (`ike/shields.py`, `ike/resources/fingerprint.js`, `ike/workersbar.py`,
  `ike/shieldpanel.py`, `ike/repair.py`; tests/test_site_workers.py, five
  new texts in every language pack).
- **A reusable web compatibility suite** (tests/compat/, outside the
  automatic tests, GitHub Actions and AUTOMAT): real sites at every level
  with their own checks, a local page of web technologies (workers,
  WebAssembly, WebGL, codecs, DASH/HLS/Widevine, WebRTC, storage, upload and
  download) and the same checks in Chromium or Brave.
- **Cloudflare's checks pass again at Balanced, Kontrol and Maximum** (the
  owner saw Turnstile fail at every level but Compatibility; Brave at its
  highest protection passed). Found by switching I.K.E.'s protections off one
  at a time in the real engine on Cloudflare's own Turnstile demo: not the
  cookies, the ad blocking, the headers or the noise, but the workers.
  Cloudflare's challenge frame allows only its own Trusted Types policies by
  name; I.K.E. starts a page's worker from an address with its protection in
  it, made trusted by a policy of its own, which that frame refuses. The bare
  address went on, the frame's own default policy turned it into an address
  its worker-src refuses, and Turnstile's workers never started. Now, where
  the site refuses I.K.E.'s policy and has a default policy of its own, the
  worker starts as the page asked (its values are the engine's there; the
  page itself stays protected); everywhere else workers keep the protection
  as before. Verified on turnstile.pages.dev: Off, Compatibility, Balanced,
  Kontrol and Maximum all pass (`ike/resources/fingerprint.js`,
  tests/test_trusted_types_workers.py).
- **A page's script cannot take the protection out of its workers** (found by
  the two independent reviews of the change above): I.K.E.'s policy is made
  as a document from the network starts, before any script of the page, so
  only the policy the site's server sent can refuse it, not a `<meta>` a
  script adds later; empty frames, srcdoc and blob: documents, which take
  such a `<meta>` from the page, never start a worker without the protection
  (it keeps it, or does not start); a page that used up the stack, or gave a
  `data:` worker an address with a character beyond Latin-1, got a worker
  without the protection until now and gets an error or a protected worker;
  and the page no longer sees the protection's own refusals (in an empty
  frame it always saw one, from "userscript"), while its own Trusted Types
  errors and events still reach it. Two older ways to an unprotected inline
  worker found by the review are still open (docs/SECURITY.md, "Known
  limits of the noise").
- **The noise's seed is no longer handed to such a page**: the protection's
  policy was named 'p' + the site's seed, and a site that refuses it reads the
  name in the refusal (`securitypolicyviolation`'s `sample`, and the report its
  server receives); with the seed the noise can be taken off. The name is now
  random, another in every document.
## 1.1.31

- **Pages that steal passwords are stopped** (the owner's choice after the
  comparison with the best-known browsers): the Phishing URL Blocklist
  (curben's malware-filter, from OpenPhish, IPThreat and PhishTank, updated
  twice a day, CC BY-SA 4.0) is on by default next to the malware list, and
  every profile gets it once (whoever turns it off keeps it off). As with
  every list, a page it stops can still be opened with "Open anyway"
  (`ike/config.py`, tests/test_security.py).
- **The password vault locks itself** (`ike/vaultlock.py`): after 15 minutes
  in which I.K.E. was not used (no key, click, wheel turn or touch in its
  windows; the Passwords window offers Never, 5, 15, 30 and 60 minutes), and
  when the desktop locks the screen, the screen saver starts or the computer
  goes to sleep (a switch, on). Its next use asks for the master password; the
  Passwords window closes. Nothing runs while the vault is locked, and a
  message on the bus can only lock it (tests/test_vault_lock.py, on a real
  session bus too).
- **Spell checking while typing** (`ike/spelling.py`, Settings → Language and
  translation → Spelling, on): misspelled words in the page's text fields are
  underlined and the right-click menu offers the corrections, in the
  language of the system and of the interface (English when there is no
  dictionary of it). Hunspell's dictionaries, on this computer: nothing typed
  is sent anywhere. On Arch Linux and CachyOS each `hunspell-*` package
  brings them (`hunspell-it`, `hunspell-en_us`: new optional dependencies);
  Settings say which are in use, or which package to install
  (tests/test_spelling.py; the Arch Linux check installs both).
- **The history kept for a chosen time** (Settings → Privacy → Browsing data,
  "Keep the history"): Always (the default: nothing changes), 1, 3 or 6
  months, 1 or 2 years. Older pages and downloads are deleted by themselves at
  the start, every hour and when the choice is applied; bookmarks, passwords,
  cookies and settings stay (tests/test_history_keep.py).
- **Print preview**: Print… (Ctrl+P, the menus, the page's menu) shows the
  pages as they will be printed first, then the system's print window from
  its Print button (tests/test_print_preview.py).
- **No white frame between two pages** (the owner saw one on a fast site,
  with and without dark mode): the page's backdrop colour is given again when
  the new page starts and when its address changes, so that the renderer of
  another site gets it from its first frame (`ike/webview.py`).
- **Dark Engine: a background of a gradient and a colour is darkened** (a
  panel of a site stayed white in 1.1.30): Chromium reads a layer without a
  picture as `initial` in the list (`background: linear-gradient(#fff, #fff),
  rgba(0,0,0,.03)`); written back so, the whole dark declaration was not valid
  and the page's light one stayed. Such a layer is now written as `none`
  (tests/test_dark_engine_hard.py).
- **The new tab page is customised from the new tab page** (the owner's
  request): a small gear beside the clock and the weather (it shows when the
  mouse is over them) and one beside the counter open a small panel in the
  style of Plasma's widgets, with the switches of the rest of I.K.E.: clock,
  weather, its city, temperature, wind and pressure units; the counter (this
  month or since installation) and the site tiles (bookmarks, most visited
  or none, hidden tiles shown again). A choice changes only that setting and
  the page comes back in place with the panel open; only the page itself can
  do it (the session's key), a web page cannot (`ike/newtab.py`,
  tests/test_newtab_panels.py).
- **The names of the favourite sites are readable** (they were grey): in the
  text colour, a little heavier, in the light and the dark theme.
- **A clearer glass on the new tab page** (the owner's request): over a
  photo, each group of text (greeting, wordmark, clock and weather, counter,
  buttons, the sites' names) sits on a glass that shows the photo, with a
  thin discreet edge, and the letters and the weather's symbols have a soft
  halo in the page's colour. The glass is tinted only as much as the photo
  under that group asks, from 8 % (18 % before): every text still reads at
  4.5:1 on the worst part of the photo, the large figures at 3:1, and the
  sites' small names now at 7:1 (tests/test_newtab_readability.py: white,
  black, busy and I.K.E.'s own photo, light and dark theme).
- **The clock and the weather are smaller** (the owner: the weather was too
  large for a second row of sites): the clock 32 px (42), the weather's
  symbol about 1.15 cm (2 cm); in a narrow window its details now fit too.
- **The logo lights up on the new tab page** (the owner's choice): a light
  starts from the left and the right ends of both lines of the logo's
  circuit at once, faint, and grows as it runs to the middle, where the two
  lights meet in a small flash; each branch lights up as the light passes
  it, at the same speed, and its pad gives a small discreet glow when the
  light reaches it (the lengths and the timings come from the logo's own
  drawing). The light is a little wider than the white traces, full colour
  over them and fading outwards. About 3 seconds of light, then 2 seconds of
  rest. Only with the interface's effects on (so not with reduced motion
  asked, nor with the battery saver at work); nothing moves during the rest,
  and a tab that is not shown runs none. Measured on a computer drawing
  without a graphics card, the new tab page with the light takes about 3 %
  of one processor core more than without (tests/test_newtab_logo.py).
- **Pages change softly** (the owner: "pages come in abruptly"): the old
  page's picture stays over the tab until the new page has drawn its first
  content, then fades away in a fifth of a second; turning dark mode on or
  off for a page fades its colours the same way. Nothing waits for it: the
  new page loads as fast as before under the picture, which lets the mouse
  through; a very quick page that has drawn already is simply shown
  (`ike/pagefade.py`, tests/test_graphics_131.py).
- **The page mode's sun turns into the moon** and back, instead of a plain
  swap of icons, and **the shield's octagon turns half a turn**, as a coin,
  to show the new protection level. With the interface's effects only.
- **I.K.E. Kontrol** (`ike:kontrol`, also from the counter's panel on the new
  tab page): what I.K.E. blocked, counted on this computer only: this month,
  the month before and since installation, and this session's counts by
  kind and the sites that tried most, as traces of the logo's circuit ending
  in a small octagonal pad (the owner's choice). The sites of private
  windows are never listed, they only add to the totals; a web page can
  neither open nor read the page (`ike/resources/kontrol.html`,
  tests/test_kontrol.py).
- **About I.K.E. names Dark Reader's lists**, with the date of the lists in
  use, and no longer a Dark Reader version: since 1.1.30 only its lists are
  part of I.K.E.

## 1.1.30

1.1.29 was never published on its own: everything prepared for it is in
this release.

- **The shield's numbers in the logo's letters** (the owner's choice): the
  number beside the octagon in the address bar, the "+N" that rises beside
  it, and the new tab page's figures and their words are written in Orbitron,
  the typeface of the logo's lettering, in the colour of the logo's K (its
  light blue on a dark background, its darker blue on a light one, always
  readable at 3:1), a little smaller and lighter than before. The font file
  is shipped unchanged (SIL OFL 1.1, `ike/resources/fonts/orbitron.ttf`) and
  never installed in the system's font list, so no page can find it
  (`ike/cyberfont.py`); languages it has no letters for keep their own font.

- **Cover Your Tracks says "randomized fingerprint"** (the owner: "I want to
  be randomized"). Its code counts five values that differ between two sites
  (the audio, the canvas and WebGL pictures, the plugins, the cores) and needs
  four. The canvas and WebGL pictures varied at every export (1.1.27): it read
  "randomized" on both of its sites, took that for the same value and counted
  nothing. Now every export is the site's own picture (another on every site
  and in every session, as Brave does), the plugins differ at every level
  (Kontrol and Maximum: Chrome's five PDF viewers in an order of the site's own)
  and the cores are 4 or 8 per site at every level where the computer has 8:
  four or five of five, at Balanced, Kontrol and Maximum
  (tests/test_cover_your_tracks.py runs Cover Your Tracks' comparison on two
  sites). The common graphics card tried while preparing this release is gone
  again: in a real test Cover Your Tracks counted its Linux name as 1 browser in
  58,876 (15.85 bits), against 1 in 183 for "None".
- **Strict is now called Kontrol** (the owner's choice, the K of I.K.E.): the
  shield's fourth level keeps its protections and its place, and every
  setting already saved keeps its level (inside, the level is still
  "strict"). The shield shows a K drawn like the logo's, in the light blue of
  the logo's K (#65C2EF, 8.4:1 on the shield's centre), instead of the S;
  every language calls the level Kontrol. The menus' inventory recorded for
  1.1.30 reads the old name as the new one (tests/test_menus_reorg.py).

- **Dark Reader leaves I.K.E.** (the owner's decision, after trying the I.K.E.
  Dark Engine in 1.1.28): the I.K.E. Dark Engine is the dark mode for pages,
  Chromium's own the other choice (Settings → Web pages → Dark mode method).
  A profile that had Dark Reader gets the engine by itself; Dark Reader's
  colours and per-site themes leave the profile (`dark_theme`,
  `dark_site_themes`), its engine, panel and theme modules go (`darkpages.py`,
  `darkpanel.py`, `darktheme.py`, `resources/darkreader.js`,
  `resources/darkreader-proxy.js`) with their tests. The toolbar's Dark mode
  button always opens the "I.K.E. Dark Engine" panel; with Chromium's own dark
  mode its look is greyed, with a note. Dark Reader's lists stay (MIT,
  `darkfixes.py`, `darklists.py`), fetched by the browser once a day.
- **No white while a page arrives**: a page that is plainly light is darkened
  as soon as its body and its style sheets are there, and what arrives after
  is handled as it comes (a slowly arriving shop was white for about 2 s, now
  never); a page that may say "dark already" is judged at DOMContentLoaded as
  before (tests/test_dark_engine_detect.py).
- **No white flash in frames**: a page in a frame is covered dark until the
  engine has mapped it, then a frame meant to be transparent is transparent
  again (Speedometer 3.1: frames with more than a quarter of light pixels 211
  → 12, the rest its grey picture placeholders).
- **Colours kept in registered variables are darkened too**: a page that
  gives a colour only as the initial value of a registered custom property
  (`@property --x { initial-value: #fff }`, used as `var(--x)`) kept it light,
  so a band of a shop's home page stayed white under text made light. The
  engine now sets the mapped value with no specificity (at the root, or on
  every element when the property is not inherited), so a value the page sets
  itself still wins (tests/test_dark_engine_hard.py). The live check also
  says where a light area's variables get their value.
- **A variable's fallback colour is darkened too**: a page that defines a
  colour as another variable with a fallback (`--band-bg: var(--theme-bg,
  #fff)`, the theme never defined) kept the fallback white; the engine now
  maps the fallback where the variable is defined, in style sheets and in
  style attributes alike.
- **Rules added later without a change to the page are seen**: rules a page
  inserts into a style sheet by script (`insertRule`, CSS-in-JS) change no
  element, so nothing told the engine; the sheets are now looked at again
  0.3, 1.5, 5 and 15 s after the page last changed. A style element whose
  text is rewritten in place is seen at once (tests/test_dark_engine_hard.py).
- **A page with many pictures can no longer keep the engine busy**: on a page
  with a few large darkened pictures and many small icons, the engine made
  room in its picture memory by letting the icons go, the page's next pass
  asked for them again, and so on without end (the page stopped answering).
  A picture left as it is now keeps that verdict when it leaves the memory,
  only pictures that hold data are let go for their size, and a sheet, rule
  or element is written again for a returning picture at most 40 times in
  10 s.
- The live check can click a site's age or cookie question first
  (`--click "Accept"`) and takes a page that never stops loading (live
  video) as it is after 20 s instead of giving up.
- **A gradient next to a variable is darkened too**: a background written as a
  gradient beside a variable in one value (`linear-gradient(#fff, #fff),
  var(--picture)`) was left as written, so a panel of a site stayed white
  under text made light; its gradients are now mapped, the variable left to
  its own definition (tests/test_dark_engine_hard.py).
- **Text over a photo stays readable**: photos are kept as they are while the
  page's text is made light, so a caption drawn dark over a light photo (a
  shop's banner or card) became light on light; text laid over a large picture
  now gets a dark halo (tests/test_dark_engine_hard.py).
- The live check also runs inside a running I.K.E., on the page as it is
  seen (`tests/dark_engine/live-diag.py`, signed in and scrolled), and
  lists light text on a light layer or picture with the site's own rules.
- **AUTOMAT follows Dark Reader's lists only**: the engine, its builder and its
  re-anchoring are gone (`tools/build-darkreader-lists.py` rebuilds the
  shipped lists byte for byte with `ike/darklists.py`'s own functions); the
  lists are checked every day and fetched by the browser itself (no
  candidate).
- The Dark Engine's live check also writes `diagnose.txt`:
  the large light areas the engine left and where their colour comes from (a
  rule of a sheet, an inline style, a sheet the page cannot read, a frame, a
  picture).
- **Menus and Settings reorganised** (the owner's request; no function added
  or removed, every shortcut unchanged: tests/test_menus_reorg.py compares
  everything reachable with 1.1.30's inventory).
  - The menu bar: File (open, save, print, downloads, backups, quit), Edit,
    **Tabs** (new tabs and windows, containers, profiles, workspaces, close),
    **Page** (zoom, reader, dark mode, translation, sound, source and
    developer tools), View (only the window's bars), History, Bookmarks,
    **Privacy** (levels, repairs, passwords, clearing data), Extensions, Tools
    (command bar, resources, watched pages, search engines, Settings), Help
    (now with About I.K.E.).
  - The ☰ menu: no "More" any longer. New tab, window and private window,
    then the owner's categories (Tabs and windows, Web page, Edit, File and
    downloads, Audio and video, Bookmarks and history, Privacy and security,
    Browser appearance, I.K.E. extensions, Performance and tools, Backup and
    restore), Settings, Help, About, Quit; never more than two levels (a
    submenu's entries are shown in place, under its name).
  - Both are described in one place, `ike/menus.py`, and share the same
    QActions.
  - The extensions under five headings (Privacy and security, Browsing and
    appearance, Audio and video, Productivity, System and resources), the
    same in the menus and in Settings → I.K.E. extensions.
  - Settings: the crowded pages split (**Web pages**: zoom, dark mode, the
    Dark Engine, sound and DRM videos; **Ads and trackers**: the blocker and
    its lists; **Site permissions**; the translation service under **Language
    and translation**), and the 14 pages in four areas named in the list
    (Basics, Appearance and browsing, Privacy and security, System and
    extensions). Their icons 28 px (were 22). Every link and the names of
    earlier versions open the right page; the search also finds an area by
    its name.
- **The Settings' search no longer misses options**: it could take an option
  for one already seen (Python's id() of a short-lived Qt wrapper reused).
- The note on Chrome extensions no longer names uBlock Origin, Dark Reader
  and Consent-O-Matic: I.K.E. has all three built in (the owner).
- **Where a link goes, again** (the owner): the address of the link under the
  mouse in a small box at the page's bottom corner, as other browsers show it
  (the other corner when the mouse is there). 1.0 had put it in the status
  bar, which took room from the page each time: the whole page shook, and
  1.0.1 removed it. The box lies over the page and moves nothing; KDE's
  tooltip look, its corners slightly rounded.
- Icons and texts aligned: the extensions' cards (icon and bold name in the
  middle of the card) and the containers' dots in the menus (the owner).
- **Short messages in Plasma's style** (zoom, notes; the owner): the window's
  colour with a thin line and a soft shadow, the corners slightly rounded
  (4 px), rising a few pixels as they fade in. They were a flat grey box.
- **Sites see a more ordinary Chromium** (the Engine Privacy Layer study,
  measured against Arch's own Chromium of the engine's version, Chrome and
  Brave: docs/review/engine-privacy-study.md). At
  Balanced and above `window.chrome` is the one Chromium 140 has (`loadTimes`,
  `csi`, `app`, measured shape: no difference left), `permissions.query`
  answers as Chromium where Qt WebEngine said "denied" for everything it has
  no prompt for, and the network a page reads (rtt, downlink) and the network
  hints are the common ones Kontrol already showed (Qt said rtt 0). CreepJS
  already saw I.K.E. as "like headless" no more than Chrome and Brave.
- **No advertising measurement**: Attribution Reporting and Topics are off in
  the engine (`ConversionMeasurement`, `BrowsingTopics`; their APIs taken from
  pages). Qt WebEngine kept an advertiser's attribution source in the profile,
  where Chromium keeps none, and sent the Topics header.
- **One language everywhere**: the engine is given the first language sites
  are told at every level (it was at Maximum only), so shared and service
  workers, dates and numbers say what the page says (they said "en" where
  the page said "en-US"). The language header is written as Chrome writes it
  (`de-DE,de;q=0.9,en-US;q=0.8`; Qt sent the list without weights, which no
  Chromium does), and at Kontrol and Maximum it keeps the engine's own place
  among the headers.
- **HTTP/3**, as Chrome, Chromium and Brave use it (Qt WebEngine leaves it
  off): faster on weak or changing networks, never through a proxy; a
  `--disable-quic` of the user's keeps it off. Each site's connections, HTTP/3
  sessions and what the engine remembers of servers are kept apart
  (`PartitionConnectionsByNetworkIsolationKey`), so one site's traffic cannot
  mark another's. Measured on real sites, 6 rounds each: CPU 24.5 s without,
  25.1 s with HTTP/3, 24.7 s with both (within the runs' own spread of 22-28 s);
  load times alike on GitHub's fast network.
- **The Octagon: "Common English language"**: sites are told American English,
  the most common language, at every level; I.K.E.'s own menus keep yours.
- **The new tab page thinks**: 205 new lines (the owner: "it must seem that
  I.K.E. really thinks"): 80 thoughts of I.K.E.'s own, 20 tips with real
  shortcuts, 60 more fun facts, 45 more kind words, in every language.
- **I.K.E.'s thoughts are written letter by letter** on the new tab page, as
  if it were thinking them now (about two and a half seconds; whole letters in every
  script; the other lines appear as before; not with reduced motion).
- **A download flies to the Downloads button**: the file's icon goes in an arc
  from the pointer to the button, smaller and fading as it lands (0.45 s).
- **Touchpad: the swipe shows itself**: a round arrow comes in from the page's
  edge while the fingers swipe back or forward, and fills with the theme's
  blue when letting go will act; nothing where there is no page to go to.
- **The broom has its own panel** (the owner): what the site keeps before
  anything goes (its cookies, the data it stored, its cache, the cookies of
  the other sites its page loaded that you never opened yourself, the
  permissions you gave it), each with a switch and its count; "Clear" deletes
  what is on (everything but the permissions at first), loads the page again
  and says what went. A switch cleans the site by itself when its last tab is
  closed: its cookies at once, what it stored before its next page can read it.
- **The switches' knob keeps its colour** on and off (it turned white when
  on); only the track becomes the theme's blue.
- **A lighter toolbar** (the owner): the octagon in the address bar a little
  smaller and its letter too, so its rim no longer nearly touches the bar's
  border; the navigation and bookmarks bars a little lower (35 and 30 px
  instead of 39 and 34 at the usual scale; buttons, icons and the address
  field keep their size); the bookmarks bar's "more" button shows KDE's own
  double arrow (as Falkon), exactly as tall and as thick as the Forward arrow.
- Measured, not changed (the study's security part): Qt WebEngine has no
  revocation list of Chrome's (a revoked certificate opens), and, as Chrome
  140, it no longer applies its built-in HSTS preload list; I.K.E.'s own
  automatic HTTPS (on by default) still sends every `http://` page to HTTPS.

- **Skip the tracker's stop** (the owner's decision of 2026-11-27, from
  Brave): a link that only passes through a tracker, with the real address
  written inside it (newsletters such as Mailchimp, ActiveCampaign, Amazon
  SES or Postmark; shops' affiliate links; some ad networks), opens that
  address at once: the tracker never sees the click and the page opens
  sooner. Google's AMP copies of articles (`google.com/amp/s/...`,
  `*.cdn.ampproject.org`) open on the publisher's own site. The links are
  those of Brave's public debounce list (MPL-2.0), shipped unchanged as
  `ike/resources/brave-debounce.json` and followed by the daily maintenance
  (`components.json`, entry `brave-debounce`; the manifest now also follows
  an upstream with no releases by the newest commit of a branch). From
  Balanced up, with "Remove tracking parameters from links" on (the default);
  "Repair this site" turns it off for a site. I.K.E.'s own limits on any
  rule (`ike/debounce.py`): only an http or https address, never one of this
  computer or the home network, never one with a user name in it, never the
  same site, never a sign-in or payment service, never the stops that also
  check the destination for the user's safety (Facebook's and Instagram's
  link shim, Steam's link filter, Google's and YouTube's own redirect pages),
  at most three stops in a row. The new address goes through every
  protection again, as the engine itself reads it (a host written in
  escapes or other digits that the engine would read as the home network is
  refused). A rule of the list may only name trackers: a pattern for every
  site or a whole public suffix, a template leading elsewhere than YouTube,
  or a regular expression that could take long is left out, and a new list
  with such a rule fails the tests, so it never reaches main by itself
  (independent review by a second model, tests/test_debounce.py). The
  maintenance compares commit versions as commits (the merge's gate, the
  inventory, the ledger). Google's AMP pages on a
  publisher's own site are left as they are: telling them apart needs a
  script in every page and a second load, for pages a computer rarely gets.
- **Menus as wide as their entries, every time**: now and then, after a
  window had been closed, a menu opened a little narrower than its entries
  (20 to 40 px of the end cut). PyQt can hand I.K.E.'s style a menu entry's
  description wrapped as something else, so the entry was measured by the
  desktop's rules when the menu opened and by I.K.E.'s afterwards. The style
  now reads it as a menu entry every time (`ike/uistyle.py`; found by
  tests/test_text_fit.py, which also measures a menu only once it is open).

## 1.1.28

- **The I.K.E. Dark Engine** (the owner's decision): I.K.E.'s own dark mode
  for pages, a choice beside Dark Reader and Chromium's own (Settings → Web
  pages → Dark mode method → I.K.E. Dark Engine; Dark Reader stays the
  default and stays available while the engine is tried). It gives Dark
  Reader's colours at about half its cost (Speedometer 3.1 here: -15 % from
  the page without dark mode, Dark Reader -32 %), uses only Dark Reader's
  lists (MIT, the rules it can use: `darkfixes.engine_css`), recognises sites
  that are dark already also when they do not declare it, never hides an
  element, keeps what the user writes in editors and mails as written, prints
  the page's own colours, and a page cannot stop it. Measured against Dark
  Reader's own test scenarios (122 of 125 alike, the 3 others deliberate) and
  page by page (docs/DARK-ENGINE.md).
- **Its own panel** under the toolbar's Dark mode button (a moon when the page
  is dark, a sun when it is not), in I.K.E.'s Plasma look: "I.K.E. Dark
  Engine", on everywhere and on this site, four styles drawn in their own
  colours (Graphite, as Dark Reader; Midnight; Warm; Nordic), background
  depth, text brightness, dimmed pictures, sites dark already left as they
  are; a slider shows its effect on the page at once and every open page
  takes the look when it is let go, nothing loaded again. The same options
  in Settings (a box "I.K.E. Dark Engine"). Every language pack has its texts.
- The hidden switch of the experiment (`dark_engine_experiment`) becomes the
  choice in Settings by itself.

- Copies handed to a desktop app (an image to the image viewer, a PDF to the
  PDF reader) are asked of the engine one at a time: asked together on a busy
  computer, one of them could be lost without a word (tests/test_handoff.py,
  which now also says what the engine answered for each download).

### Also in this release: 1.1.27 (never published on its own)

- I.K.E. has a new Breeze octagonal logo, dedicated icons for small sizes and
  the new wordmark on frosted glass over the local 4K WebP Earth background on
  Home and New Tab. About I.K.E. shows the logo alongside the original text.
- The protection control now shows the applied level inside an octagon, with a centred count.
  Reload precedes Home, bookmarks overflow uses two Forward arrows, the page-mode
  button shows a sun or a moon, and About I.K.E. sits above Quit.
- **The level's letter in a colour of its own, cyber cut** (the owner): C
  yellow, B green, S light blue, M pink, each with a contrast of 7:1 or more
  on the octagon's dark centre; the letters are drawn as straight strokes
  with corners cut at 45 degrees and a notch from 26 px up, every point on
  the screen's pixel grid so they are sharp at 16 px too (the same octagon
  in the menus and the panel; the menus' texts unchanged); off keeps its
  white X. The ring that opens when something is
  blocked is centred on the octagon again, and the rising "+N" starts right
  after the number (tests/test_launcher_icons.py).
- **The toolbar's Screenshot button has a menu** (the owner): Visible part
  (Ctrl+Shift+S), Whole page and Selected area, the same entries as Page →
  Screenshot…, in I.K.E.'s Plasma-style menu; a click opens it (it took the
  visible part at once), with no arrow beside the icon, as Print and Zoom
  (tests/test_screenshot_menu.py).
- **The small icons say I K E** (the owner): at 16, 22 and 24 px the
  application icon showed a plain light dot in the octagon; it now shows the
  letters I K E drawn pixel by pixel (the K blue, as in the large logo), the
  octagon unchanged.
- **Plasma's task bar no longer flashes black** (the owner: its buttons
  vanished on hover and the bar turned black for a while): 1.1.27 had given
  the windows' icon its 512 and 1024 px pictures too, and the desktop gets a
  window's icon whole (5.6 MB instead of 0.4); the windows carry the
  pictures up to 256 px again, as in 1.1.26 (the larger ones stay for the
  package and the menu).
- **The new logo reaches the menu by itself** (the owner's rule: every
  release reaches every user with no command): the package installs the
  launcher's icons under /usr/share/icons, which a self-update never
  touches, so 1.1.27's logo would have reached the menu only after the
  package was installed by hand. A few seconds after each start I.K.E. now
  copies the icons of the version in use into the user's own icon folder
  (~/.local/share/icons/hicolor, read before /usr/share/icons): the same
  files the package installs, only those that differ, nothing when I.K.E. is
  not installed as an application (`ike/desktopicons.py`). Plasma may show
  the new icon from the next login.
- **Google's sites see a current Firefox, with the protections on** (the
  owner's decision). Google's sign-in kept refusing I.K.E. now and then ("this
  browser may not be secure"), and AI Studio's API key page did not work: Google
  takes Qt WebEngine's Chromium, some versions behind, for an embedded program
  or a bot. Until 1.1.26 only accounts.google.com was given a Firefox, a fixed
  Firefox 140 more than a year old, while the engine's client hints in the very
  same request still said `"Chromium";v="140"`; and Google's sensitive
  services (AI Studio, the cloud console, the account, payments) were left with
  no protection at all instead. Now every request and every frame of a page of
  Google's sites (google.com and its services, Google's search in every
  country, gstatic.com, googleapis.com...; YouTube is not one of them), a
  Google sign-in embedded in another site ("Sign in with Google") and what it
  loads present the Firefox of the calendar (161 today, estimated from the
  date, nothing fetched; never ahead of a real release): in the header, with
  the engine's client hints sent empty (Qt can only set a header, not take it
  away), and in JavaScript in every frame (Firefox's navigator texts, `oscpu`
  and `buildID`, no `navigator.userAgentData`, no `window.chrome`), with
  getters that read as the engine's own. Google's sites keep the user's
  protection level (fingerprinting noise, filter lists, address clean-up,
  cookies, GPC): no more "Compatibility" or "off" forced there. At Balanced
  Google's own domains count as one site on Google's pages (as Firefox's
  tracking protection counts them), its ad and analytics domains
  (doubleclick.net, google-analytics.com, googletagmanager.com...) do not.
  With the shield off on a site, or with "Make sign-in work" off, nothing
  changes. Microsoft's and Apple's sign-in and PayPal and Stripe keep their
  light protection as before (`ike/config.py` `google_site`,
  `ike/shields.py` `firefox_request`, `ike/resources/fingerprint.js`
  `firefoxIdentity`, `ike/osinfo.py` `firefox_major`;
  tests/test_google_firefox.py, tests/test_page_traces.py).
- **Cover Your Tracks shows a randomized fingerprint again** (the owner
  reported it as a regression). Cover Your Tracks draws its canvas twice and
  calls the fingerprint "randomized" when the two pictures differ, "unique"
  when they are the same; I.K.E.'s noise was the same for every read of a site
  (so that averaging reads cannot remove it), so it showed "unique", though
  the fingerprint was new in every session and on every site. Now a canvas
  exported as a picture (`toDataURL`, `toBlob`, `convertToBlob`; WebGL
  canvases too) gets, on top of the site's noise, a little noise that changes
  at every export: only the lowest bit of a few pixels at the edges of the
  drawing, never in flat areas (1.1.25's exact canvases of solid rectangles
  stay exact). Many exports put together give back the picture with the
  site's noise, never the real one, so averaging gains nothing; `getImageData`
  still gives the same pixels at every read (pages that edit pictures).
  Cover Your Tracks' own script, run on the real engine, now answers
  "randomized" for the canvas and for WebGL at Balanced and Strict
  (tests/test_canvas_exports.py).

- **Dark Reader's lists update by themselves inside I.K.E.** (the owner: no
  new version every day for simple lists). Dark Reader's fixes for single
  sites, its list of sites that are dark already and the hints of a site's own
  dark theme change almost every day, and each change made a new version of
  I.K.E. Now the browser fetches the three lists from Dark Reader's repository
  (raw.githubusercontent.com) once a day in the background, like the filter
  lists (only with automatic updates on), reads and checks them as the
  builder does (`ike/darklists.py` holds the same functions as
  tools/build-darkreader.py, kept identical by a test): only data for Dark Reader, nothing that could be a
  script, the common fix first, not much shorter than the copy I.K.E. came
  with, at most 8 MB, https and that host only. A refused or failed download
  changes nothing and is tried again a few hours later; the dark pages loaded
  next take the new lists. The copy I.K.E. comes with is used until then, and
  again when it is newer. The daily maintenance makes a new version for a new
  Dark Reader engine only (tests/test_darklists.py).
- Dark Reader (engine and lists): 4.9.135, lists 26d0621d65 (2026-11-25) -> 4.9.135, lists 2bd262585f (2026-11-25) (lists changed)
- Rust crates of the AdBlock engine: 88 crates -> 88 crates (psl 2.1.263 -> 2.1.264)

## 1.1.26

- Rust crates of the AdBlock engine: 88 crates -> 88 crates (psl 2.1.261 -> 2.1.263)
- Dark Reader (engine and lists): 4.9.135, lists 586f4b900d (2026-11-24) -> 4.9.135, lists 26d0621d65 (2026-11-25) (lists changed)

## 1.1.25

- **Weather units you can choose** (the owner): in Settings, next to the
  temperature (°C / °F), the wind speed can be shown in km/h, mph, m/s or
  knots and the pressure in hPa, millibar, inHg or mmHg. "Automatic" (the
  default) follows the temperature as before (°C: km/h and hPa; °F: mph and
  inHg), so nothing changes for anyone who does not choose. The conversions
  are done on the computer from the service's km/h and hPa (the request is
  the same); the new tab shows the choice the next time it is drawn. New
  settings `weather_wind_unit` and `weather_pressure_unit`, a value that is
  not one of the choices falling back to the default; tests/test_newtab_weather.py,
  tests/test_settings.py.
- **The History window shows the sites' icons** (the owner): "Show all history"
  lists every page with its site's stored icon (the globe when none is
  stored, nothing fetched for it) and every day with a calendar icon;
  tests/test_extras_124.py.
- **A panel for the toolbar's Dark mode button** (the owner approved its
  look): a click opens it under the button, as the shield's panel opens, in
  place of the menu with two entries ("On everywhere" and "On for this site"
  stay in the View and ☰ menus as they were). In it: dark mode for every site
  (the switch of the title) and for this site; Dark or Light (Dark Reader's
  two modes); Brightness, Contrast, Sepia and Grayscale with their values and
  a "Reset" button; under "More" the text font (only one of the computer's
  fonts), the text stroke, the background and text colours (of the dark or
  of the light colours, as chosen), the scroll bars (Automatic, Hidden or a
  colour), the colour of selected text, and "Only for this site" (the
  choices kept for that site alone); at the end "Dark mode settings…", which
  opens Settings → Appearance at the dark mode of pages. No link outside
  I.K.E. (no Dark Reader news, donations or social sites). A slider moved
  shows on the page of the tab at once (after 0.12 s, Dark Reader takes the
  new colours in the page's isolated world: the page is not loaded again);
  let go, the colours are kept and every open page gets them, and the pages
  loaded afterwards. With Chromium's own dark mode the colours do nothing:
  they are greyed, with the note "The sliders work with Dark Reader". Every
  value is checked before it is kept or reaches a page (ranges, colours as
  `#rrggbb`, a font name that can be written in a style sheet), and nothing a
  page does can change them; the panel is made at its first click and does
  nothing while closed (`ike/darkpanel.py`, `ike/darktheme.py`,
  tests/test_dark_panel.py). The settings keep Dark Reader's whole theme
  (`dark_theme`, with Dark Reader's own defaults; those of 1.1.24 are
  completed, their three values kept) and the sites with colours of their
  own (`dark_site_themes`). One visible change: the scroll bars of dark
  pages follow the page's colours ("Automatic", the default of the Dark
  Reader extension on Linux); they were left as the engine draws them.
- **Panels for the toolbar's Zoom and Downloads buttons** (the owner approved
  their look), made at their first click with the dark mode panel's frame
  (`ike/panelkit.py`, the popup machinery shared in `window._panel_popup`):
  - **Zoom** (`ike/zoompanel.py`): the site's name, − 110 % +, a slider over
    the same steps as Ctrl and +/− (30 % to 400 %) with 30 %, 100 % and 400 %
    under their ticks, "Remembered for this site" (or "Not remembered in a
    private window"), "Actual size" (Ctrl+0), the default zoom (the same
    setting as Settings → Appearance, which keeps it; the pages at the old
    default follow it) and "Also with Ctrl and the mouse wheel". It stays
    open while the zoom changes, without the box over the page. The ☰ menu
    keeps its Zoom submenu.
  - **Downloads** (`ike/downloadpanel.py`, `ike/downloadlist.py`; Ctrl+J
    and the button open it, the downloads window stays under "Show all
    downloads"): one row per download with the icon of its kind, its name
    shortened in the middle and one line of state: while it runs the bytes,
    the speed and the time left (smoothed over time) with a slim bar; paused;
    size, site and time once done; a program from a site visited before with
    a shield; why it failed, in red, with "Retry" always there; a download
    stopped by I.K.E.'s checks with the reason, in red, and "Download
    anyway…", which asks the very same question again with "Cancel" chosen.
    Its actions are small buttons shown under the mouse or the keyboard's
    focus (pause, resume, cancel, open the file, show it in its folder,
    retry, remove it from the list); a right click gives them all with Ark
    or the calendar where the desktop has them and "Copy link address". New:
    pause and resume, the speed and time left, retry (the same address
    again through every check of a new download), the stopped downloads
    listed, one entry removed. At its foot "Show all downloads", "Open the
    downloads folder" and "Clear the list" (what ended leaves the list; what
    runs and the files stay). Opening it clears the green "done" ring, as
    the downloads window did. The list survives a restart (the owner's
    choice): the last 50 entries of normal windows, metadata only (name,
    place, address, size, state, time, site, a short note), in I.K.E.'s
    database next to the history; a private window shows its own downloads
    only and never writes them; clearing the history (or all browsing data)
    clears it.
- **The "more" buttons show KDE's double arrow**: the bookmarks bar's and the
  toolbar's buttons for what does not fit show `arrow-right-double` (I.K.E.'s
  own drawing where the theme has none) in a square 26 × 26 button, the
  arrows exactly in its middle (measured on the painted pixels at scale 1 and
  2); they showed the "»" text, a little off centre.
- **"Bookmark this page" fixed after the address bar** (the owner's design):
  4 pixels after its right edge, centred with it in height; it can no longer
  be moved or hidden (settings that moved or hid it are mended once; it
  left the toolbar's lists and Settings → Appearance), and the address bar
  and the button are centred in the window as one block (the room the
  toolbar really leaves is measured, so the block sits exactly in the
  middle when it fits). A page already bookmarked shows the filled bookmark
  (Breeze's `bookmarks-bookmarked`, I.K.E.'s own drawing where the theme has
  none). The shipped Breeze set was built again from breeze-icons 6.32.0
  for the new names.
- **One look for every menu, and a new History menu** (the owner approved the
  pictures; the menus keep the same entries, in the same order and places).
  On KDE Plasma, Breeze still draws the menus (and Oxygen and Kvantum where
  they are the style). With any other widget style (Fusion, Qt's Windows…)
  I.K.E. draws them itself, as Breeze does: a rounded panel with a light
  shadow, rows of one height, one column for the icons kept also where an
  entry has none (every text starts on one line), a column for a switch
  (an option turned on and off) or a radio (a choice among several) only in
  the menus that have one, the keyboard shortcuts dimmed on one right edge,
  the arrows of submenus in one column, thin separators, the entry under the
  mouse in the accent colour with a thin outline, a submenu 2 to 3 px from
  its menu on either side and from right to left too (`ike/uistyle.py`). On
  every desktop:
  - every entry has an icon where KDE has one: "Save as PDF…"
    (document-export), "Page source" (format-text-code), "I.K.E.
    extensions" (plugins), "About Qt", "Reset to default layout", the two
    entries of "Dark mode for pages", a tab's "Tab group", "Move to
    workspace" and "Reopen in container" and their entries (a group's or a
    container's colour as a dot), a link's "Open link in container" (each
    container's colour), the workspaces, profiles and containers menus, and in
    "Send to device" each device as a phone, a tablet, a computer or a
    television, as KDE Connect says;
  - the titles inside two menus, Protection's "Protection level for every
    site" and the toolbar menu's "Toolbar buttons", are real section names
    (small and dimmed, where the texts start), no longer greyed entries;
  - **History**: Back, Forward, Home, Reopen closed tab and Recently closed
    tabs at the top, with their shortcuts; then the last 15 pages under Today,
    Yesterday, This week (the five days before) and Earlier, each with its
    icon, its title shortened in its middle to 290 px (no longer cut after 60
    characters) and its site on the right, dimmed; the recently closed tabs
    show their site too. At the bottom "Show all history" (Ctrl+H) and the new
    **"Clear recent history…"**, which deletes only the pages visited in the
    last hour, today or all of them (a small window to choose; "all" is the
    history part of "Clear browsing data"): cookies, cache, permissions,
    passwords, bookmarks and the private windows are left as they are.
    "Clear browsing data…" (Ctrl+Shift+Del) stays under Protection. The new
    texts in all 59 language packs; tests/test_menus_125.py.

- **The weather's symbol and its text aligned** (the owner: they were not):
  the symbol (about two centimetres since 1.1.24) has a square box of its own
  and the text a box beside it, both on the same middle line; the text wraps
  in its own column for a long name or language, and the block stays flush
  right with the clock. Fonts draw a symbol higher or lower in its line: the
  page draws it once on a small canvas to see where its ink really is and
  moves it to the middle of its box, whatever the font and the zoom. In a low
  window (or at a large zoom) the symbol is at most 13 % of the window's
  height. Measured on the page drawn for real at 100, 150 and 200 % and in
  every language: the boxes and the ink of the pixels
  (tests/test_newtab_weather.py).
- **A few weather details, as in Plasma's weather widget, kept simple** (the
  owner: minimalist, nothing cluttered; the wind and the pressure): under the
  weather one discreet row of five small symbols drawn in the text's colour
  with their values, all on one middle line, flush right: felt temperature,
  wind (speed and the point of the compass it comes from), humidity, pressure
  at sea level and chance of precipitation. °C goes with km/h and hPa, °F with
  mph and inHg (as mph already goes with °F). Each value is read aloud with its
  name (the name also shows on hover). They come with the same single request
  to Open-Meteo, which now also asks for `wind_direction_10m`,
  `apparent_temperature`, `relative_humidity_2m`, `pressure_msl` and
  `precipitation_probability` (still only the rounded coordinates and the
  temperature unit are sent; the wind always comes in km/h and the pressure
  in hPa, turned into mph and inHg by I.K.E.). Should the service refuse the
  last one, the request is made once more at once without it. Over a photo the
  row sits on the same frosted glass as the clock and reads at 4.5:1
  (tests/test_newtab_readability.py). The row never wraps: in a small window,
  or where the corner would meet the figures under the search field, it gives
  way.
- **23 more greeting lines for the moments of the day and of the week**, short
  and a little witty, in all 59 languages: early morning, mid-morning, the
  lunch break, late afternoon, evening, late night and deep night, the first
  working day of the week, the evening before the weekend and the weekend
  (the week of the page's language: Monday and Friday in most of Europe,
  Sunday and Thursday in the Gulf). Nothing about a religion; a holiday the
  user chose still wins all day, and "Greetings only" still shows no line.
  Chosen at random as before (tests/test_greeting.py).
- **Dark Reader keeps updating by itself, cleaned of useless links** (the
  owner's decisions of 2026-11-24, `tools/build-darkreader.py`). After every
  update the builder removes from Dark Reader's code every link it does not
  need: any link in a comment, and donation, social, news, analytics and
  advertising links in its texts. Only the links Dark Reader needs or its MIT
  licence's notice stay, each listed with its reason; none is ever contacted.
  A link nobody has judged yet, a new network call, a missing part of what
  I.K.E.'s Dark Reader panel uses, or site fixes that look like a script stop
  the update: the Dark Reader in use stays until Claude or a person looks.
- **A speed patch that no longer fits no longer holds Dark Reader back**: the
  update ships without it (and without the patches that depend on it), and
  the update's notes and the signing notice say which. The proxy change that
  keeps Google's sites working is not optional: without it the update waits.
- Dark Reader (engine and lists): 4.9.135, lists 16a1eccbfa (2026-11-21) -> 4.9.135, lists 586f4b900d (2026-11-24) (lists changed)
- **Fingerprinting: what the sites' own checks found** (a run of I.K.E.
  against browserleaks.com and CreepJS, the owner's decisions of 2026-11-24,
  then three rounds of an independent adversarial review; docs/SECURITY.md,
  tests/test_fingerprint_125.py, tests/test_fingerprint_125_workers.py):
  - at every level the page, its frames, every kind of worker and the request
    headers give the same brand list in the same order, the same Chrome
    version and no kernel version. Service and shared workers get the
    engine's own client hints, never the profile's: they said "Chromium"
    only, the engine's full version and the real kernel (6.18.44) where the
    page said "Google Chrome", 140.0.0.0 and 6.0.0. The profile now keeps the
    engine's own list, versions and order ("Google Chrome" is no longer
    added) and the engine leaves the kernel out (the platform version is
    empty everywhere);
  - Strict and Maximum (also a site set to Strict by itself): a worker a site
    starts from a file of its own (classic or module, nested, in a frame of
    another site) gets the same protection as the page: it starts from a
    blob holding the protection, which then runs the site's script with its
    real address (relative addresses, location and errors as before): a
    classic script by the engine's own `importScripts` (the page no longer
    waits for it, "use strict" kept), a module by `import()` with the
    messages posted before it ran held and delivered in order (one posted at
    once was lost). Where a page's security policy forbids that, the worker
    is refused, never started without the protection, and the page sees no
    policy report naming the protection. No service worker and no shared worker
    from a site's own file (one registered before at a lower level is
    unregistered);
  - Strict and Maximum: Chrome's own five PDF plugins with their two types
    (the two invented ones had no type: "missing mimetype"); one WebGL
    identity for everyone (still no card name, a fixed list of extensions
    common cards all have, a fixed floor of limits never above the real
    ones, in pages, frames, workers and WebGL 2; plain colours read back
    exactly); canvas noise only on opaque pixels at an edge, none on a canvas
    of solid rectangles, of the page's own pixels or of such a canvas copied,
    and the same for a pixel read alone as for the whole picture ("pixel data
    modified" no more); text widths whose noise does not depend on a font's
    name (two missing fonts measure the same, as in Chrome), in workers too;
    the same fonts found by measuring text in the page, its frames and every
    kind of worker (a frame of the site's own found every installed font,
    workers lost Times New Roman once the font check had run);
    no secret handed to a function a page could have replaced (a page that
    replaced a frame's toString caught the value that told I.K.E. apart);
    the languages as the header says them ("it-IT", "it"); one common network
    speed in JavaScript and in the client hints (4g, 50 ms, 10 Mbit/s).
    Maximum stays different from Strict by its language only;
  - Balanced: inline workers show the page's languages (a shared worker gave
    the engine's single one).
  - What it costs (docs/review/tests-and-performance.md, tests/measure_fp125.py):
    see "1.1.25 fingerprinting" there.

## 1.1.24

- **Stronger audio fingerprinting protection**: each sample the engine renders
  for a page is now changed by up to 0.1 % (was 0.01 %), still far below
  hearing. With the smaller noise two sessions gave the same audio
  fingerprint about one time in six once the page rounded it to 4 decimals,
  as fingerprinting scripts do; now about one time in fifty. The noise still
  depends on the site's key, the sample and the one before it.
- **Squared switches, closer to Plasma** (the owner's choice): every on / off
  switch is a rectangle with rounded corners and a square knob, no longer a
  pill. Those of the windows and the Settings are a little smaller (a line and
  two pixels tall, they were a line and four), as are those of the lists (one
  line, they were a line and two); those of the menus keep their size.
- **The new tab page's Settings button follows the icon choice**: KDE's own
  Breeze "configure" icon with the default choice and on Plasma, the chosen
  icon theme's or shipped set's icon otherwise, drawn in the page's text
  colour; the shipped icon when none is found. Only a plain
  drawing is put in the page (no script, link or outside reference).
- **KDE's Breeze icons come with I.K.E.** (the owner's request): Settings →
  Appearance → Icons offers "Breeze (KDE) (included with I.K.E.)", drawn in
  the interface's text colour like the other included sets, so the icons are
  KDE's even on a desktop without breeze-icons (still not a dependency of the
  package). Only the icons I.K.E. uses are shipped: 103 from breeze-icons
  6.32.0, 84 KB, read when they are first shown. The new tab page's Settings
  icon uses it where the Breeze theme is not installed (with the default
  choice, before the icon theme in use), and when the set is chosen.
  `tools/build-breeze-icons.py` copies them from KDE's release (the
  colour-scheme style removed, nothing else of the drawing changed; anything
  but a plain drawing stops it); the
  daily maintenance follows breeze-icons' new releases by itself
  (`components.json`, entry `breeze-icons`), and a release that lost one of
  the icons is refused and the set kept as it is. Licence: LGPL-3.0-or-later,
  `licenses/LICENSE.breeze-icons` (tests/test_breeze_icons.py).
- **A greeting and friendly messages on the new tab page** (top left; at narrow
  widths it stops short of the Settings button): "Good morning" (05:00),
  "Good afternoon" (12:00), "Good evening" (18:00), "Good night" (23:00), in the
  language of I.K.E., and under it at most one short line from a pool of 98
  messages in groups (the days away or a streak, an update, the small hours, the
  evening before the clocks change, the first of a season and of a month, the
  weather the page already has, the week of the page's language, the time of day,
  fun facts that are true, encouragement). A line comes again only after the
  others of its group (a shuffled bag per group) and not within three days; it
  stays for two hours or until the period changes, not on every new tab. In
  Settings, New tab page: the greeting (on), the tone ("Greetings only" or "Also
  friendly messages", the default) and "Holidays to remember", one switch per
  tradition, all off: Christian, Orthodox Christian, Islamic, Jewish, Hindu,
  Buddhist, Lunar New Year, Nowruz and the civil New Year; I.K.E. never guesses
  them. The days come from the engine's own calendars (Umm al-Qura, Hebrew,
  Chinese) and the computus for Easter, a small table for Diwali, Holi, Vesak and
  the Lunar New Year of some years (`ike/resources/holidays.json`, to be
  refreshed). Worked out in the page; kept in I.K.E.'s own settings and nowhere
  else: the first and last day, the days of use, the streak, the usual hour of
  the first opening, the version seen and the messages shown; nothing is asked of
  the network (the wind speed joins the temperature and the weather code in the
  weather request). The words go into the page as data, never as script
  (`ike/greeting.py`, `ike/resources/greeting.js`, tests/test_greeting.py). The
  "Add" tile is as visible as the Settings button.
- **The K of I.K.E. is light cyan** (#7df3ff, the light stop of the shield's
  edge) in the logo, in every icon size and in "Kontrol" of the full name; the
  lettering and its font are unchanged and the other letters keep their colour.
  `tools/make-brand.py` and `tools/make-small-icons.py` now draw the K as its
  own path (`lettering-k`; in the wordmark `<path class="k">`, which is the
  text colour until the page's CSS colours it) (tests/test_brand.py).
Privacy package (A2b; every item agreed by the owner):

- **Bounce tracking is cleaned up** (on by default; Settings -> Protection): a
  site you only pass through, because a link sends you there and it
  redirects you on at once (by its server or by its own script, without a
  click), loses its cookies and stored data (local storage, databases,
  caches, service workers) half a minute later, as Brave and Firefox do.
  Never for sites you used in the last 45 days (a click, a key, an address
  typed; the sites already in the history count as used), have open in a
  tab or bookmarked, allowed in the shield, or for sign-in and payment
  services. One check per page change, nothing per request
  (`ike/bounce.py`, tests/test_privacy_124.py).
- **Protected time zone** ("Fuso orario protetto", in the shield, off by
  default): every site sees UTC instead of your time zone, in pages, frames
  and every kind of worker (those a site starts from a file of its own too),
  because the web engine itself runs in UTC; I.K.E.'s own menus, history and
  new tab clock keep your time. Some sites will show wrong times; it applies
  after a restart (`ike/timezone.py`).
- **Quiet permission questions** (on by default; Settings -> Privacy): a site
  asking for notifications, your location, the camera or the microphone
  shows a small sign in the address bar instead of a window; a click on it
  answers (Allow, Block, Not now). Notifications asked for without a click
  on the page are refused at once, and the refusal is not remembered. The
  answers are kept per site as before (`ike/quietperms.py`).
- **Password breach check** (off by default; the Passwords window): when a
  password is saved or filled in, Have I Been Pwned's range service is asked
  with only the first 5 characters of its SHA-1 fingerprint (and the padding
  header); the comparison is made on the computer, and a password found in
  known breaches is said once (`ike/breach.py`).
- **"Update the system"** ("Aggiorna il sistema"): when the signed update
  information read once a day names a security problem of the web engine
  fixed in a newer version than the installed one, I.K.E. says so once per
  session, with the command `sudo pacman -Syu`. The field is written by the
  release tool from `data/engine-advisory.json` (absent until the owner
  writes one: no notice), and read only after the signature is verified
  (`ike/advisory.py`, docs/UPDATES.md).
- **Battery saver** (off by default; Settings -> System): on battery, tabs in
  the background pause after a minute, and the interface's animations and
  the pictures of the tabs for their preview cards stop; plugged in again,
  everything runs as before. Whether the computer is on battery comes from
  UPower's own signal (QtDBus, nothing to install, nothing polled)
  (`ike/battery.py`).

- **xdg-utils is no longer used** (its Arch advisory AVG-1420 has no fix and
  stopped every automatic merge): a downloaded file, a folder or a link
  (mailto:, magnet:...) goes to the XDG desktop portal
  (org.freedesktop.portal.OpenURI) through I.K.E.'s own D-Bus code: OpenFile
  with a descriptor of the very file, OpenDirectory to show a file in its
  folder, OpenURI for links. With no portal, the desktop's own opener when it
  is installed (kioclient on KDE, gio, exo-open on Xfce), else a message that
  says where the file is; never xdg-open. "Make I.K.E. the default browser"
  writes `~/.config/mimeapps.list` itself, as the XDG MIME Applications
  specification says (http, https and text/html), atomically and keeping
  every other entry; a desktop's own list and KDE's kdeglobals are updated
  only where they already name a browser. xdg-utils left the PKGBUILD's
  optional dependencies and the Arch check (`ike/handoff.py`,
  tests/test_handoff.py).
- **Handoffs to the desktop's apps**, shown only when the desktop has the app
  (read from the mimeapps.list files and the apps' .desktop files, nothing
  started to find out): "Open with Okular" for a PDF, "Open image in
  Gwenview" in an image's menu, "Open the page source in Kate" in a page's
  menu, "Add to calendar" for `.ics` links, and in the downloads window "Show
  in folder" (Dolphin or the file manager, the file selected), "Open with
  Ark" for an archive and "Add to calendar" for a calendar file. On other
  desktops the names are those of their own PDF reader, image viewer, editor,
  archive manager and calendar. An image or PDF is fetched by the engine
  itself into a private folder (`~/.cache/ike-browser/handoff`, emptied after a
  day) and handed over only when its content is of that kind.
- **Safer downloads**: a program or a script (AppImage, .run, .sh, .exe, .msi,
  .deb, .rpm, .jar, .py, .bat, .cmd, .ps1, .desktop, by name or MIME type) from
  a site on I.K.E.'s protection lists or from a site never visited before
  asks first; a file over http from an https page (a mixed download) is
  stopped. "Cancel" is the default and the Esc answer, "Download anyway"
  works after a moment and lets that one download through, at the user's
  risk. Nothing is asked of the network (`ike/safedownload.py`,
  tests/test_safe_downloads.py).
- **"Clear this site's data" says what it removed**: cookies, the site's
  storage (local and session storage, databases, service workers) and caches,
  counted by the clean itself in I.K.E.'s own script world (the page sees
  nothing), and the permissions it keeps. Found on the way: when a site set
  the same cookie again in a later answer, the engine reported it removed and
  never added back, so I.K.E.'s list lost it and the clean left that cookie
  behind; every cookie the site may still have is now deleted
  (tests/test_clean_site.py).
- A question with a delayed "yes" button (permissions, a burst of downloads)
  answered "no" before the delay ended no longer raises an error.
- 14 new interface strings, translated into all 59 languages; the downloads
  window's new buttons are measured by the text-fit test in every language.
- **Desktop notifications without libnotify**: I.K.E. now calls the notification
  service of the desktop (org.freedesktop.Notifications, through Qt's own D-Bus)
  instead of starting `notify-send`. Same app name, icon, title, text and timeout;
  a page's text can still never become an option or markup; with no service
  nothing happens, as before. `libnotify` is no longer an optional dependency.
- **The Public Suffix List copy is JSON, not marshal**: the parsed copy of the
  list kept in the cache is plain JSON (about as fast to load: 0.81 ms against
  0.74 ms for a list of 8,700 rules). An old marshal copy is ignored and deleted;
  a damaged copy is rebuilt from the list.
- **"Not secure" in the address bar**: a page over plain http shows a small
  red "Not secure" (translated in every language) after the lock. Not for
  localhost, 127.x.x.x, ::1, file:, about: or ike: pages.
- **One mark on the current tab, Breeze's own, and it glides** (the
  owner's choice, with a mockup): Breeze drew its fixed accent line on the
  current tab and I.K.E. its own gliding line under it, so two blue lines
  showed. Now there is one: Breeze's line along the top edge of the tab,
  following its two rounded top corners and not down the sides, with
  Breeze's thickness (3 px), corner radius (5 px) and colour (the palette's
  highlight, the inactive one in an inactive window). It glides from tab
  to tab (position and width) and jumps with reduced motion; the line
  under the tab is gone and the style's own fixed mark is not drawn in
  I.K.E.'s tab bar. Measured on Breeze's code and render: in Breeze the
  tab bar with I.K.E.'s mark is the same picture, pixel for pixel, as
  Breeze draws it with its own (light and dark, tests/test_touches_124.py).
  Fusion, Oxygen, Kvantum and Windows get the same shape in their
  highlight colour (Kvantum themes that draw a mark in their own pictures
  keep it).
- **The current tab stands a little raised**: its background is a shade
  lighter than the window's (a little white mixed in) in Breeze, Fusion and
  Windows; in styles that paint the tab otherwise (Oxygen, Kvantum's
  pictures) the same shade of white is laid over it.
- **The close button of a tab glows red under the mouse**, like Plasma's
  window close button and drawn by the same code as the vertical tabs' and
  the window's own close buttons (`ike/closebutton.py`: a disc in Breeze's
  negative colour, KDE's own when the colour scheme sets it, or the Aurorae
  theme's button), coming in over 120 ms.
- **Tabs slide aside while one is dragged**, in the horizontal bar (Qt's
  own movement, now following "Interface effects" and the desktop's reduced
  motion) and in the vertical tabs (the rows open a place for the dragged
  one, where Qt only showed a line; it is dropped where the place opened).
- **The vertical tabs' panel widens and narrows smoothly** between only
  the icons and the titles (200 ms).
- **The vertical tabs' panel keeps its width** (the owner's report): the
  width the user drags it to is kept in the settings and comes back after
  a restart, in a new window and when vertical tabs are chosen again (the
  panel shown again took its smallest width); it is saved at once when the
  window closes, and a stored width is held between 120 px and the smaller
  of 720 px and half the screen.
- **A tab pulled out of the window opens in a new window**: pulled more than
  40 px above or below the tab bar, the tab follows the mouse as a small
  picture of its page (the tab preview's picture); dropped outside every
  tab bar it opens in a new window, on another window's tab bar it moves
  there, back on its own bar or with Esc it stays. A row of the vertical
  tabs dropped outside the list does the same.
- **Quick actions say they were done in a small box**, like Plasma's
  on-screen display: a rounded box with the desktop's icon and the text
  ("Link copied", "Bookmark added", "Screenshot saved", the zoom), in the
  desktop's colours, fading in and out in about 1.2 s and never taking the
  keyboard or the mouse.
- **Tooltips fade in and out** briefly (90 and 110 ms; on Wayland the
  desktop's own effects do it, as for menus).
- **The find bar (Ctrl+F) slides in from the bottom**, and its field
  flashes red for a moment when nothing is found, then keeps its soft tint.
- **Touchpad gestures**: a horizontal swipe goes back or forward, the page
  sliding away; a pinch zooms the page, the zoom shown in the small box and
  kept for the site as with Ctrl+wheel. They are Qt's native gestures (on
  Wayland the compositor's: a two-finger pinch; a swipe as the compositor
  sends it, with three or more fingers where two-finger strokes scroll).
- **Ctrl or Alt held for a second shows the keys of the toolbar buttons**:
  small labels under the buttons (Alt+Left, Ctrl+R, Ctrl+D...), gone when
  the key is let go or another key is pressed.
- **Tab groups take Breeze's colours** (the desktop's accent first, then
  the colour scheme's positive, neutral, negative, visited and link colours,
  then KDE's yellow, turquoise and grey) **and fold and unfold smoothly**,
  in the horizontal and the vertical tabs.
- Every one of these costs nothing at rest (no timer, no animation once it
  has played: the tests compare what runs before and after each), and each
  follows "Interface effects" and the desktop's reduced motion, changing
  at once without them (`ike/polish.py`, `ike/tabs.py`, `ike/motion.py`,
  `ike/gestures.py`, tests/test_touches_124.py).
- **The ☰ menu regrouped with one logic** (the owner's go-ahead: "with
  criterion and logic"): new tab, window and private window; then this page
  (Find in page, Zoom, Dark mode for pages, Reader mode, Translate page);
  then keeping it (Print, Save as PDF, Save page as, Screenshot); then the
  library (History, Bookmarks, Downloads); then Protection, I.K.E.
  extensions and More; then Settings and Help; then Quit. Find, Reader
  mode, Translate and Save page as are new in the ☰ menu itself; "Check for
  I.K.E. updates" and "About I.K.E." moved into its new Help submenu (with
  Keyboard shortcuts and About Qt), so nothing is there twice any more.
  Nothing was removed and every keyboard shortcut is the same
  (tests/test_menus_124.py checks every entry of 1.1.23's menus and every
  shortcut).
- **"More" ("Altro") fixed**: in KDE's Breeze its texts touched or crossed
  the arrows of their submenus ("Visualizza", "Strumenti"), and its
  entries, without icons, began left of every other menu's texts. It now
  holds the menu bar's File, Edit, View and Tools, each with its icon (Help
  moved up into the ☰ menu); and in every menu, in every widget style, an
  entry that opens a submenu gets half a line of room before its arrow
  (Breeze left 3 px or less). The text-fit test now measures, in all 59
  languages, that no text comes within 6 px of a submenu's arrow, and
  tests/test_menus_124.py does it in Breeze, Fusion, Windows, Oxygen and
  Kvantum, left to right and right to left.
- **The menu bar's View and Tools in groups**: View goes zoom → full screen,
  reader mode, dark mode → vertical tabs, split view, workspaces → the
  window's bars → page source and developer tools; Tools goes command bar
  and tab search → downloads and passwords → translate, floating video, mute
  → site resources, suspending tabs, watched pages → search engines and the
  Chrome Web Store → Settings. File, Edit, History, Bookmarks, Protection,
  Extensions and Help are as before.
- **A search field in the Settings**: type a word and only the pages that
  have it stay in the list, its options marked with a light frame in the
  desktop's highlight colour; it finds an option by its name, by its ⓘ
  explanation or by a choice of its list, without minding capitals or
  accents (modalita finds modalità), in every language; "No setting found"
  when nothing has it; Esc empties the field, Ctrl+F goes to it. No new
  library, nothing done while nothing is typed.
- **The Settings in a clearer order**: General, Appearance, New tab page,
  Search, Downloads, then Protection and Privacy, then I.K.E. extensions,
  then Language, Updates and System (every page keeps its name, so links to
  a page still open it). Appearance is in groups: the colours and icons,
  Window, Toolbar buttons, Web pages (zoom and dark mode). On every page the
  options of all its groups start on one line, and the names stand in the
  middle of their option's height.
- **Toolbar buttons you can add** (off until you choose them in Settings →
  Appearance → Toolbar buttons or with a right click on the toolbar): Zoom
  (its menu: zoom in, zoom out, actual size), Manage bookmarks, Print or save
  as PDF (its menu), Send to device (the phones and computers paired with KDE
  Connect, with the Plasma integration extension) and Site resources (with
  its extension). A click opens their menu, as with the dark mode button.
- **History by day**: the history window groups the pages under "Today",
  "Yesterday" and then the date, written as the interface's language writes
  it; each page shows the time of its last visit. The search works as
  before and keeps the grouping; a day's heading is never opened nor
  deleted.
- **Reader mode: the column and the type**: on the reader's bar, a narrow,
  medium or wide column and serif or sans-serif type, next to the text size
  and the colours; I.K.E. remembers the choice.
- **Screenshot of the whole page or of an area**: "Screenshot…" (☰ menu,
  File, a page's right-click menu) opens its choices: the visible part, the
  whole page (taken a screen at a time and put together, the bars that stay
  in place shown once, up to 16,000 pixels) or an area dragged with the
  mouse over a still picture of the page (Esc cancels). Ctrl+Shift+S and the
  toolbar button take the visible part as before; the picture is saved as
  before (`ike/screenshot.py`).
- **Dark PDFs** (off by default; Settings → Appearance → Web pages, "Show
  PDFs with dark colours"): PDFs in I.K.E.'s own viewer are shown with their
  colours turned around, light text on a dark page, the open ones at once.
  Nothing runs on other pages, and nothing at all while it is off. "Open
  with Okular" for a PDF is the one of the handoffs above.
- **A welcome at the very first start** (`ike/welcome.py`): four short steps
  in plain words, before the first window: the language (the computer's,
  confirmed or changed: the welcome itself changes language at once), how
  much I.K.E. blocks (Compatibility, Balanced, Strict, one plain line each),
  the search engine, and, only if ticked, I.K.E. as the default browser.
  "Skip" changes nothing; everything stays changeable in the Settings. It
  is never shown again, and never to a profile that already had settings.
- **"Copy clean link" in a link's right-click menu**: the address without
  utm_, fbclid, gclid, mc_eid and the other tracking parameters I.K.E.
  already removes (the same list), as the address bar's own "Copy clean
  link"; the address bar keeps "Paste and go".
- **History → Recently closed tabs**: the last 10 tabs closed, newest
  first, with their title and the site's icon; one chosen opens again (in
  the ☰ menu's History too). Ctrl+Shift+T still reopens the last one;
  private windows keep no list.
- 27 new interface strings, translated into all 59 languages; the welcome's
  four steps are measured by the text-fit test in every language
  (tests/test_extras_124.py).
- **The frame guard looks less, and protects as before**: a node put into a
  tree a page is still building outside the document (no frame there gets a
  window) is no longer looked at further, a call that swaps nodes no longer
  counts the frames before it, and with no frame at the guard's last look
  only the count after the call is read. Measured in a page doing what
  Speedometer's pages do (4 shared cores, Balanced, 48 rounds each,
  medians): elements appended one by one 13.75 -> 13.1 ms, trees built
  outside the page then put in 8.4 -> 7.4 ms, tests/measure_dom.py's page
  13.1 -> 12.55 ms (shield Off: 9.2, 5.8 and 10.05 ms), so 14-38 % of the
  guard's own cost there; Speedometer (14 DOM suites, 7 runs each) 12.9 ->
  13.2, within the spread of the runs (11.4-14.3). The larger part left,
  about a fifth on pages that insert a lot, is the watch of frames written
  in the page's HTML while it loads: the engine keeps a document marked as
  watched for good once it was, and nothing else can protect such a frame
  before the page's next script reads it through window[i] (measured: the
  engine runs nothing in that frame first, and its load event comes only
  for an empty frame), so it stays. A new test plays every quick path as
  an attack (132 frames read at once through window[i], frames[i], by
  name, contentWindow and contentDocument; frames in frames, swapped
  frames, a page lying about isConnected, firstElementChild, localName and
  length, shadow roots); its frames load a page, so none is saved by its
  own load event. Found and noted, the same before: a script or a custom
  element put in together with a frame runs inside that very call, before
  the guard looks (docs/review/tests-and-performance.md, "1.1.24, the frame
  guard"; tests/test_frame_guard_paths.py).

## 1.1.23

- **Widevine installs again** (Settings -> DRM video): Google no longer serves the old zips on
  dl.google.com/widevine-cdm/ ("HTTP Error 404" in 1.1.22). I.K.E. now asks Chrome's component
  updater (update.googleapis.com) for the Widevine component, as a Chromium on x64 Linux would and
  nothing more, downloads the package it names only over https from Google's own servers, and
  installs it only if its SHA-256 matches the answer, it is signed with Widevine's own key and it
  holds a 64-bit x86-64 Linux library. The old folder stays only as a fallback; when Google offers
  nothing, the message says so and names the AUR package chromium-widevine as another way.
  "Check for a newer version" asks the same question and says when the copy is already the newest.
- **The application icon can be read when it is small**: at 16, 22, 24, 32,
  48 and 64 px (the panel, the title bar, the task switcher, the menus) the
  shield is drawn again for each size's own pixels, the same shield, colours
  and plate, with larger, bolder letters on whole pixels (at 16 px "IKE", no
  room for the dots), instead of the large logo shrunk to a grey smudge. They
  are installed in the icon theme (hicolor) and the window icon carries them
  all; 128 px and larger and the scalable logo are unchanged
  (`tools/make-small-icons.py`, tests/test_brand.py).
- **Pages run faster with the fingerprinting protection, which gives them
  exactly the same answers** (Speedometer study of 1.1.23): the guard that
  protects new frames no longer reads through all the HTML a page writes
  (innerHTML, outerHTML) when the page has no frame, nor looks at a moved
  part of the page when there was no frame to move (Speedometer's jQuery
  page at Balanced: 284 -> 261 ms); at Maximum, when the engine already
  speaks English, dates, numbers, sorting and upper or lower case that ask
  for no language go straight to the engine (a sort compares 8 times
  faster; numbers, dates and case as fast as with no protection). Tests
  compare the quick and the usual ways' answers. The rest of the distance
  from Chrome and Brave is the web engine: on the same computer Google's own
  build of Chromium 140 (the version inside Qt 6.12) scores 1.5 times Qt's
  build of it, and Chromium 153 only 2 % more than 140. I.K.E.'s own work
  costs a few percent of the whole benchmark (2-4 % at Maximum) and up to a
  tenth on pages that rewrite much of themselves, most of it the price of
  protecting the frames a page writes in its HTML
  (docs/review/tests-and-performance.md, "1.1.23").
- **Dark Reader skips the frames nobody sees**: a frame that is not shown
  (hidden, or a frame of a pixel or two, as trackers and advertisers use)
  no longer starts Dark Reader until it gets a size; shown later, it is dark
  from its first picture, as before. Each such frame costs about 20 ms less
  to load in dark mode (about 30 ms of the page's processor time): about
  what it costs with dark mode off. Shown frames and pages look exactly as
  before. tests/test_darkreader_frames.py loads frames one after the other,
  as Speedometer does, and checks both.
- **Dark Reader: the colours of selected text written as colours** (the
  owner's decision): Dark Reader wrote them as a CSS variable with the colour
  as fallback, and a selection colour read from a variable makes the browser
  work the selection style out again for every element that sets variables
  of its own, at every restyle. One full restyle of Speedometer's Lit page
  42-46 -> 34-35 ms (fastest of 41, three runs); Speedometer with Dark Reader
  (Lit, Web Components and Charts, 10 iterations, three runs each) 5.46-5.71
  -> 6.17-6.82, Lit 129-142 -> 105-115 ms. Selected text has the same colours,
  pixel for pixel (screenshots of six pages, before and after); only that one
  rule's text differs. The engine's tenth measured change
  (`tools/build-darkreader.py`, "selection-colours").
- **Why Brave with the Dark Reader extension scores more than I.K.E. with
  Dark Reader on Speedometer** (the owner's question): measured, the way
  I.K.E. gives Dark Reader to a page costs the same as the extension's own
  way. I.K.E.'s copy of Dark Reader put into Chrome as an extension costs
  Chrome 43 % of its Speedometer score, exactly what it costs I.K.E. (43 %);
  per frame, 26-30 against 27 ms. The difference is the engine under it: Qt
  6.12 has Chromium 140, Brave a newer one, faster with or without Dark
  Reader. Most of Dark Reader's cost on Speedometer comes from its work
  while the tests change the page, by the way Dark Reader works; the
  engine's own dark mode costs almost nothing. Details in
  docs/review/tests-and-performance.md, "1.1.23, Dark Reader and Brave".
- uBlock Origin scriptlets: 2bc679d99a (2026-11-10) -> 5934db2a04 (2026-11-21) (1 changed, 0 new, 0 removed)
- Rust crates of the AdBlock engine: 88 crates -> 88 crates (psl 2.1.253 -> 2.1.261; regex 1.13.1 -> 1.13.2; regex-automata 0.4.18 -> 0.4.19; regex-syntax 0.8.11 -> 0.8.12; smallvec 1.16.5 -> 1.16.6)
- Dark Reader (engine and lists): 4.9.135, lists 30e8a10e65 (2026-11-16) -> 4.9.135, lists 16a1eccbfa (2026-11-21) (lists changed)
- **No white flash at the start**: the view of a new tab shows the new tab
  page's own colour before the page paints (dark grey on a dark interface),
  at the start and for every new tab; sites in light mode keep white between
  pages.
- **The new tab page no longer jumps when it opens**: the bookmarks bar
  ("only on a new tab") went away for a moment when the page started
  loading and came back when it arrived, so the page grew and shrank again
  and, in that moment, showed what the engine had not painted yet. The bar
  now follows the address the tab was asked to open, so it stays put; a site
  opened in a new tab no longer shows it for a moment either
  (tests/test_start_flash.py).
- **The tab preview keeps no pictures it does not show**: the hidden card
  lets go of the last picture, and a finished blend from one tab to the next
  releases both.

Speed and fluidity (two studies measured where the time went, the numbers
before and after are in docs/review/tests-and-performance.md, "1.1.23"):

- **Pages with blocked ads load sooner**: I.K.E.'s page scripts no longer
  run in the error page of a frame the shield blocked (nothing can reach
  it), and a site's own scriptlets (and, with the owner's OK, the video
  sites' scripts) are compiled only on that site, not in every page: a page
  with 20 blocked ad frames loads in 383 ms instead of 580 ms, an article on
  a new site in 61 ms instead of 83 ms. What the scripts do where they run
  is the same (tests/test_script_limits.py; the YouTube tests unchanged).
- **The new tab page's clock wakes once a minute**: it wrote its text every
  second, and the whole window repainted with it; with the new tab page in
  front the computer now does 4/5 less (2.5 % of a core instead of 5.6 %,
  3 wake-ups a second instead of 12).
- **Changing tab is about twice as quick** (2.1 ms instead of 3.9 ms here,
  4–6 ms instead of 10–11 ms with OpenGL; a new tab 7.5 ms instead of 11): the small
  picture of a tab for its preview card is taken when the mouse comes to
  the tabs or once its page has loaded, not at every change of tab. The card
  shows the same picture.
- **Loading costs less**: the turning mark of a loading tab is drawn once
  and repaints only its own tab; the line between the bars and the page no
  longer lies over the page (it was repainted at every frame of a video or
  of scrolling: 60 times a second); the loading line is drawn from a
  picture, appears only for a load that takes more than 0.15 s and never
  for I.K.E.'s own pages; the "+N" and the ring of the shield move at 30
  pictures a second; the toolbar paints its own background where the
  window's is one flat colour, so a hover or the "+N" no longer repaints the
  whole window behind it.
- **The first page is asked for sooner**: while the window builds its bars
  and menus (about 40 ms earlier), with the filter engine, the request
  interceptor and every page script already in place, as before
  (tests/test_start_speed.py checks it).
- **History and site icons** use SQLite's WAL mode: saving no longer waits
  for the disk; a backup still has the last visits, and clearing them leaves
  nothing behind.
- **Background tabs are suspended after an hour** (was 20 minutes; the
  owner's choice): whoever kept the old 20 gets 60 once, any other value
  stays. When the computer is short of memory, tabs are still suspended
  sooner, as before.

The look, in the colours of the theme in use (Breeze's own ways):

- One corner radius for everything I.K.E. draws; a flat loading bar; the
  line under the current tab with square ends; spacing on Breeze's 4-px
  step; Breeze's hover colour on the toolbar's buttons and the tabs, which
  now come and go softly (only the button or tab under the mouse, nothing
  at rest; no fade with reduced motion or the effects off); a new tab fades
  in and a closed one fades out; a focus ring on the buttons I.K.E. draws
  itself when they are reached with Tab; one colour for every separator line.
- **The ☰ menu button and the dark mode button show their icon only**, with
  no arrow, in every widget style; a click opens their menu as before.
- **A private window is easier to tell apart**: its toolbar is a little
  purple, and its "Private" badge has the private-browsing icon and a border.
- **The address suggestions, and the shield's and the site's panels** have
  the same corner radius and a light shadow (the panels only where the
  widget style gives its menus none of its own: Breeze and Oxygen do).
- **Nothing gets worse** (automatic maintenance, nothing changes in the
  browser): every commit is measured against `main` with the real browser,
  the same way on the same fixed inputs (ad and tracker blocking, YouTube's
  requests included, the fingerprinting surface at every level, the hosts
  contacted by itself, the security settings), and anything weaker fails
  (`tools/no-regression.py`, the step "Nothing gets worse" of tests.yml,
  docs/MAINTENANCE.md). A change a person accepted goes in
  tests/data/no-regression/allowlist.json.

## 1.1.22

Two things the owner saw in 1.1.21 on KDE Plasma:

- **The switches are whole in every desktop style**: with Breeze (Plasma's
  style) only the first part of each switch showed in the Settings and the
  other windows, and in the shield panel its text was drawn over it. Breeze
  (and Oxygen) keep a check box's box at their own size whatever they are
  asked; the switch is now measured and placed by I.K.E. itself, as the one
  of the "I.K.E. extensions" page was in 1.1.20. tests/test_switches.py
  checks every switch of the windows in Breeze, Fusion, Windows, Oxygen and
  Kvantum (in Breeze 162 were cut before, none now).
- **Every text fits in every widget style**: the text-fit test of 1.1.21 now
  also runs in Breeze, Oxygen, Kvantum and Qt's Windows style on Arch Linux
  (the Arch job installs them). Two more things it found are fixed: buttons
  keep at least 2 px above and below their text (Kvantum's default theme left
  one for Persian), and in Qt's Windows style a menu's entries no longer touch
  its left side.
- **Also when I.K.E. follows the system**: with KDE Plasma's own theme (its
  colours, light or dark, and its fonts) and with GNOME's (GTK), every text,
  switch and the tab preview are measured too. It found one more thing: a
  choice list with a long entry (dark mode, in Tamil) made the Appearance
  page wider than the window, as Qt kept a width it had measured before the
  list was narrowed; every long choice list of the Settings is now narrowed
  for good (its open list still shows each entry whole).
- **On KDE, KDE's own icons only**: following the system on Plasma, every
  icon of the interface now comes from Breeze. Three came from another theme
  installed on the computer (the containers' lock, twice, and the Privacy
  page); each icon now asks first for Breeze's name for the same thing, and
  other desktops keep theirs. tests/test_icons.py opens every window and menu
  with KDE's theme and fails on any icon that is not Breeze's own.
- **The other desktops' own look too**: following the system on GNOME,
  Xfce, MATE, Cinnamon or LXQt, the icons now come from that desktop's own
  theme (Adwaita, elementary, MATE's, Papirus, Breeze) instead of I.K.E.'s
  drawings or Qt's (47 icons on GNOME, 42 on Xfce, 46 on MATE were not; with
  no desktop theme at all no icon is left empty any more); GNOME's and MATE's
  one-colour icons are painted in the text colour, so they show on dark
  windows too. Text that the desktop's colours left too pale is made
  readable (the notes of the Settings on KDE light, LXQt and plain Qt, the
  tab preview's CPU and memory on GNOME, the numbers of the new tab page),
  and with GNOME's larger font an option goes under its name instead of
  making a Settings page wider than the window, and the site permissions
  window no longer exceeds the screen. tests/test_icons.py and
  tests/test_desktop_colours.py check each desktop, light and dark, on Arch
  Linux.
- **The tab preview shows the whole memory value**: CPU and memory were side
  by side, half the card each, and "182 MB" could end in "…". They are now
  one under the other, each the card's whole width; a test checks every
  language with a large font.

Speed, with every feature and protection as it was:

- **A faster start, the same protection**: the window comes about 50 ms
  sooner (480 → 431 ms in the test container), 54–89 ms for a new profile,
  and the first page 38–76 ms sooner. The Public Suffix List's codes for the
  fingerprint protection are kept instead of being worked out at every start,
  and the usual start no longer loads Python modules it does not need. A
  filter engine built from the lists (a new profile, a list update) takes
  175 ms instead of 235, and the interface's longest pause meanwhile is
  about 8 ms instead of 17 (medians). Every protection is in place before the first page as
  before, and what a page sees is unchanged (numbers and method:
  docs/review/tests-and-performance.md, "1.1.22, start and speed").

## 1.1.21

Fingerprinting: the points left by the independent audit of 1.1.20, each
with a test that failed before the fix (docs/SECURITY.md has the table).

- **Fonts at Strict and Maximum**: the engine itself now sees only the font
  families most Linux computers have (DejaVu, Liberation, Noto, Cantarell,
  Source Han, WenQuanYi), so a page's style sheet (`src: local()`) or a
  worker can no longer find a font the user installed. Read at start: a
  change of level applies after a restart. I.K.E.'s own interface uses the
  same fonts at these levels.
- **Processors**: the number shown is 4 or 8, the most common values (2 was
  rare enough to single the browser out).
- **Screen size at Strict**: `matchMedia` answers the shown screen size too;
  a search over the device-width queries gave the real one away.
- **The noise's site** follows the Public Suffix List: two unrelated sites
  on one hosting service (a.altervista.org, b.altervista.org) no longer share
  their noise.
- **`window.name`** is emptied when the tab moves to another site.

- **The tab preview** (the mouse over a tab that is not open) is a card of
  I.K.E.'s own: fully opaque (a tooltip window, which some desktop styles draw
  partly transparent), with rounded corners, its picture the card's whole
  width on a scaled screen too (it filled half of it at 2x), and under the
  title the tab's CPU and memory with a coloured bar each, read once a second
  while the card is shown.

The interface, as the owner tried it on KDE Plasma (no menu, setting or
shortcut changed):

- **An ⓘ instead of the grey line under each option**: in a narrow window or
  with a larger font the explanations under the options could be cut. Each
  one is now in a small round ⓘ right after its option (the desktop's own
  icon): the mouse over it shows the explanation, a click, Space or Enter
  shows it in a small window that a click or Esc closes, and screen readers
  read it. The sentence at the top of each Settings page stays, wrapped.
- **Texts never touch or cross a border**: buttons keep room around their
  text, a check box's long text wraps beside its box (right to left too),
  the toolbar buttons and permissions of the Settings wrap instead of
  widening the page. A new test (tests/test_text_fit.py) opens the window,
  the menus, every Settings page and the other windows in every language
  pack and fails on any text that is cut, too close to its frame or needs
  sideways scrolling: 101 problems in 58 languages before (176 on Arch
  Linux with Noto Sans), none now.
- **Everything fits the screen**: About is a window whose text scrolls, at
  most the size of the screen (it could run past the bottom); the Settings,
  the main window and the other windows never open larger than the screen.
- **Menus longer than the screen scroll** (the ☰ menu, the menu bar,
  history, bookmarks, context menus), whatever the desktop's style.
- **Switches instead of check boxes**, as the owner asked: every on / off
  option (the Settings, the shield's panel, the find bar, clear data,
  import, passwords, resources, watched pages, site information, the email
  question) is a switch like those of the "I.K.E. extensions" page, with
  the same text in the same place; the filter lists and the user scripts
  show a switch in each entry (a click on it or Space turns it); menu
  entries turned on and off (menu bar, extensions, toolbar buttons, dark
  mode, workspaces, tab groups, profiles, a video's loop and controls) show
  a small switch instead of the tick, while a choice among several (the
  protection level, the search engine) keeps its dot. Nothing else changes:
  same settings, same signals. tests/test_switches.py fails on any check
  box, ticked list or ticked menu entry that is not a switch.

- **Dark Reader closer to its own version**: of I.K.E.'s 53 changes to Dark
  Reader, only the 32 that measurably make pages faster are kept (new
  colours, repeated icons and style sheets, shadow roots, the search for
  shadow roots, large style sheets); the other 21 saved no time that could
  be told from noise, so they went. Pages turn dark exactly as before, and
  a new Dark Reader has fewer places where its automatic update can stop.

## 1.1.20

An independent review of 1.1.19 (security and privacy) found 18 points; each
one is fixed here with a test that failed before the fix (tests/test_review_fixes.py).

- **A key press never grants a permission**: in the camera, microphone,
  location, "open with another program" and many-downloads questions, Enter
  and Esc now block, and "Allow" can be clicked only a moment later (a page
  could ask exactly when the user was typing).
- **Fingerprinting noise can no longer be peeled off**: the canvas noise now
  depends on the picture too (a plain grey canvas of the same size gave the
  pattern away, and with it the real pixels); the audio noise touches only
  what the engine rendered, every sample by its own tiny factor; text widths
  change per text and font, and an empty text measures 0.
- **The protected values look like Chrome's**: the replaced properties throw
  as Chrome's do on a wrong object; Strict keeps WebGPU with no adapter and a
  battery on mains power instead of removing them, and sends the one language
  it shows in the Accept-Language header too; Maximum's dates and numbers use
  en-US like its navigator.language, also when a page asks for an empty
  list of languages or one the engine does not have.
- **A page can no longer switch the fingerprinting protection off from
  inside**: the protection used some of the page's own built-in functions
  while the page ran; a page that replaced one of them (for example
  `WeakSet.prototype.has` or `Promise.prototype.then`) was handed the real
  canvas or audio values, the hidden font names, or the full browser version.
  Everything it uses is now taken before the page runs (second review pass).
- **An independent audit of the fingerprinting protection** (first groups
  of its fixes; each with a test that failed before):
  - no built-in function of the page's is used any more, `call`, `apply`,
    `filter`, `toLowerCase`, `slice` and regular expressions included (they
    gave the hidden WebGL extension, an inline worker without protection);
    the client hints keep the engine's own order of keys;
  - an inline worker can no longer read its own prelude and with it the
    site's noise key: its address is withdrawn at once, its location and its
    errors name the page's own address and line, and a `data:` worker gets
    a key of its own;
  - fonts at Strict and Maximum: the masks no longer tell which fonts are
    installed, `local()` in a FontFace answers as for an absent font, a
    frame's `clear()` cannot remove the page's masks, workers get the same
    masks, and every font installed on the computer is masked, not only the
    714 known names;
  - the other ways to the pixels get the noise too: WebGL2 pixel buffers,
    `readPixels` into any array of bytes (also in workers), `VideoFrame`;
    the byte data of audio analysers; 16-bit float (HDR) canvas reads get a
    noise of their own;
  - the noise can no longer be removed by reading a picture several times
    with one corner changed (a majority vote), nor the audio noise by
    rendering a buffer of known samples: it now depends on the content
    itself, not on the whole picture or on the place of a sample;
  - sites are told the same storage space (10 GiB) on every computer, not
    60 % of the disk to the byte;
  - an error a page provokes no longer names I.K.E. in its stack, and the
    two invented plugins answer like real ones to the engine's own checks;
  - a second independent pass tried 13 more ways around these fixes
    (constructor and index-setter tricks, module workers, workers inside
    workers, WebGL numbers written as text, other spellings of fonts, quiet
    audio, Trusted Types pages): each is closed, with a test; what a page's
    world cannot close is listed in docs/SECURITY.md.
- **Dark mode with Dark Reader: no full restyle when the page starts.** The
  dark cover that hides the white flash while Dark Reader starts was a
  colour on the page's root, and taking it away made the browser style the
  whole page again (the largest part of Dark Reader's extra cost on
  Speedometer's Lit pages, found by an independent review). It is now an
  image in the page's head: the same dark, no restyle.
- **The default fonts are Chrome's** (Times New Roman, Arial, Monospace):
  a page could read the desktop's own font names from them. Pages that
  choose no font of their own may look slightly different.
- **Maximum protection: the web engine speaks English too** when it is the
  global level (form messages, the PDF viewer, dates, workers); I.K.E.'s own
  menus and windows keep your language. It applies after a restart.
- **Ctrl+Shift+A opens the extensions** ("Search open tabs…" stays in the
  menu without a shortcut): with both, neither worked.
- **Encrypted DNS also for I.K.E.'s own requests**: with encrypted DNS on,
  the home-network checks, dark mode's style sheets, user scripts, the sites'
  icons, updates and filter lists ask the same provider instead of the
  system's resolver; when the engine refuses the setting, I.K.E. says so.
- **I.K.E.'s own requests no longer name I.K.E.**: filter lists, updates, the
  version check, the DRM download and user scripts send the pages' User-Agent;
  at the first start only the search engine in use is asked for its icon.
- **User scripts**: a page can no longer make I.K.E. download a `.user.js`
  by itself (only the user's own click or typed address offers an install,
  and the home network only when typed); each script with GM functions runs
  in a world of its own, so another installed script cannot read its token
  or answers; an update that moves a script into the page's world asks first;
  an answer that arrives after the tab changed site is dropped.
- **Dark mode's style sheets** follow the page's rules: never in clear for an
  encrypted page, never what the filter lists block for it, with the
  browser's User-Agent.
- **The logins' channel is the password helper's alone**: the other helpers
  of its world get only the calls they use; a second channel cannot take the
  answers.
- **Updates**: a second start of I.K.E. within 20 seconds of an update (a link
  from another program) no longer rolls a healthy update back for good (needs
  this package: ike_boot.py); each channel's manifest names its channel; a
  version stopped by the owner is withdrawn even when already staged.
- **Smaller fixes**: extension packages from the store must carry the
  extension's own signature (CRX3); site icons are decoded only as PNG or ICO;
  the password generated from the page menu stays out of clipboard history
  and is taken off after 45 seconds; arguments I.K.E. does not know are not
  passed to Qt; the site of a name follows the Public Suffix List of the
  system (new dependency: publicsuffix-list), so `a.wordpress.com` and
  `b.wordpress.com` are two sites.
- **The automatic click that skips an ad in an embedded video** lands only on
  the video: only when the page really holds a video frame, the point must
  still be on it when the click is made, and at most once every 3 seconds (a
  page could put something of its own there to get a real click). The skip
  on the video site itself is unchanged (the owner's decision).
- **Faster where the reviews found time** (an independent performance review
  of 1.1.20, each fix measured and tested): visits and site icons are written
  to disk together a moment later instead of one wait for the disk per page
  (on a hard disk tens of milliseconds at the end of every page load); an
  icon drawn again with the same picture is not written again; the history
  menu and the new tab page use indexes (at 100,000 visits 10-17 ms -> under
  0.2 ms); the ad-blocking engine of the session is built in its own thread
  while I.K.E. sets up, still in place before any page loads; no download
  code is loaded at start-up; the Public Suffix List is read from a parsed
  copy; the canvas noise is computed four bytes at a time; encrypted DNS
  keeps one connection to its provider and asks a name once.
- **The canvas noise no longer undoes itself**: pixels the page wrote back
  and read again lost the noise and gave the real picture (found while
  measuring the noise; also in 1.1.19).
- **Forty more languages** (the owner's request): Dutch, Swedish, Danish,
  Norwegian, Finnish, Icelandic, Greek, Hungarian, Romanian, Turkish,
  Estonian, Lithuanian, Latvian, Catalan, Galician, Basque, Albanian,
  Afrikaans, Swahili, Filipino, Korean, Indonesian, Malay, Vietnamese, Thai,
  Hindi, Bengali, Marathi, Nepali, Tamil, Telugu, Georgian, Armenian,
  Azerbaijani, Kazakh, Uzbek, and from right to left Arabic, Hebrew, Persian
  and Urdu, for which the whole interface turns (the address bar's shield and
  buttons too). Every text translated, checked automatically; corrections by
  native speakers are welcome.
- **Dark mode with Dark Reader on pages built from components** (Lit, web
  components): their style sheets are matched before their dark copy is
  written, so the page is no longer styled again two more times as soon as
  the components appear; rules whose text did not change are not written
  again. The dark result is the same, byte for byte. (Found by running
  Speedometer 3 inside I.K.E.; pages with very much CSS still cost more with
  Dark Reader than with the engine's own dark mode, by the way Dark Reader
  works: it makes a dark copy of every style.)
- `docs/platforms` left `main`; it is kept, identical, on the archive branch
  `docs/multiplatform-plan`.
- **Menus and Settings, grouped so that everyone finds their way** (the
  owner's plan). The ☰ menu holds the everyday entries, each with an icon and
  a short explanation: new tab and windows, Protection (the level, Repair
  this site, Site permissions, Update filter lists, Clear browsing data),
  I.K.E. extensions, Dark mode for pages, Zoom, History, Bookmarks,
  Downloads, Print / Save as PDF / Screenshot, Settings, Check for I.K.E.
  updates (new: a check at once, answered as the daily one), About I.K.E.
  (now with each component's version) and Quit; every other command is under
  More. The menu bar reads File, Edit, View, History, Bookmarks, Protection,
  Extensions, Tools, Help; Settings moved to Tools. Every shortcut is the
  same. The Settings have eleven pages (General, Language, Appearance, New
  tab page, Search, Protection, Privacy, I.K.E. extensions, Downloads,
  Updates, System), each with one sentence saying what it holds and a short
  explanation under every option. Nothing was removed and every setting keeps
  its name, its default and its meaning; the old page names still open the
  Settings.
- **I.K.E. extensions**: the features that come with I.K.E. (no third-party
  code), each with an on/off switch in the menu and in the Settings: user
  scripts, dark mode for pages, skip ads in videos, cookie banners, password
  manager, page watcher, split view, floating video, translation,
  containers, site resources, weather, command bar and Plasma integration.
  All on as before; off hides the feature's entries and buttons and stops
  its work. Two new ones, off until chosen: **automatic scrolling** (middle
  click on an empty part of a page and move the mouse; any click or Esc
  stops it) and **open the selected text with the middle button** (as an
  address or a search, in the same tab; never run as code). Links, fields
  and buttons keep their own middle click (tests/test_menus_extensions.py).

## 1.1.19

- **The home network, also through public names**: the web engine's own
  protection (Local Network Access) is on for every site. A public page can
  no longer reach this computer, the router or other devices at home, even
  through a public name that points there (DNS rebinding): pictures,
  scripts, frames, fetch, workers, redirects, WebRTC, links and forms that
  open a page at home. There are no exceptions per site: the engine's only
  way to make one opens the device to every site (tried), so it is not used,
  and the window says what was stopped without an "Allow" button (a page at
  home that a public page tried to open can still be opened by the user's
  click). Still open: a WebSocket to a public name that points home (the
  engine only warns), and behind a proxy (docs/SECURITY.md).
- **Page dark mode with Dark Reader is faster, with the same result**: less
  repeated work on pages built from many components (200 shadow roots:
  278 -> 100 ms of Dark Reader's work), with adopted style sheets (-21 %),
  icons (-18 %) and large style sheets (2,000 rules: -33 %, the dark copy
  written in one go). The dark result is byte for byte the same (checked on
  six kinds of page); no light frame appears when pages load, and an empty
  page is now dark too in dark mode.
- **A separator line for the vertical tabs** when their panel slides in over
  the page, in the colour of the desktop's own separators (as in Dolphin).
- **Startpage is the default search engine**. Whoever was on DuckDuckGo,
  the previous default, moves to Startpage once; another engine chosen stays.
- `tests/measure_smooth.py`: how smoothly pages appear and scroll, the same
  local pages measured in I.K.E. and in another browser.
- **Automation** (docs/MAINTENANCE.md): Z.AI's free models are a reserve of
  the automatic fix (after Groq, before OpenRouter), and the weekly check
  asks every reserve one tiny question, so a refused key or a gone model is
  found early; every scheduled check is kept on and watched (the Arch and
  security ones were not); the AdBlock engine's other crates (pyo3, psl,
  regex...) are followed and updated, not only the engine; pytest and ruff
  are pinned like the other test packages; the reserves see the files the
  latest commits changed, and one provider can no longer end the chain
  alone. Two gaps in the security tests were closed (a popup or a form of a
  page with no origin of its own, found by breaking each guard on purpose).

## 1.1.18

Speed, measured before and after on the same computer (the numbers are in
docs/review/tests-and-performance.md, "1.1.18, before and after"); no
protection was removed or weakened.

- **Pages that change a lot run faster with the shield on**: the
  fingerprinting protection watched every change of every page for the whole
  life of the page, to find new frames. It now watches while the page is being
  built (where it is needed) and stops afterwards; the ways a frame can come
  in later are guarded directly, and once the page is built every insertion
  that may bring a frame looks at the frames of the page (an independent
  review found that a frame removed and another added escaped the first
  version; fixed, with its attack pages as tests). A page adding and removing thousands of
  elements: 23.7 -> 17.6 ms at Balanced (11.5 ms with the shield off).
- **Page dark mode with Dark Reader is lighter**: changes to how Dark
  Reader's engine works (built in from its npm package, checked at every
  update) stop it from making the browser restyle the whole page or lay it
  out again for nothing (a style it took for moved, a colour variable set on
  the whole page when a fallback already gives the same colour, SVG shapes
  measured one at a time), let identical style elements (an icon repeated
  with its own style) share one dark copy, and cut its work for every
  shadow root. Pages look exactly the same. Speedometer 3.0 with Dark
  Reader: 5.7 -> 6.9 on the same computer (Svelte-Complex-DOM 250 -> 52 ms,
  Lit-Complex-DOM 273 -> 175 ms, observable-plot charts 359 -> 239 ms); the
  engine's own dark mode stays the lightest.
- **Frames added in more ways are protected**: a frame put into a page through
  a Range (insertNode, surroundContents), a shadow root or execCommand gets the
  same protection as the page at once. In 1.1.17 the Range and execCommand
  ones showed the real canvas to the page's next lines.
- **Less work in the window while a page loads**: the shield, its "+N" and
  its ring are drawn once and reused instead of at every frame of their
  animation; a blocked advert no longer tells every window at once (they hear
  of it once per site every 16 ms, the shield still ends on the exact count).
  A page with 400 requests and 150 adverts: 234 -> 190 ms of the interface's
  processor time, request checks 17.0 -> 13.2 ms. The "+N" now repaints only
  its own strip, not the address field under it.
- **Request checks never wait for other work**: the AdBlock engine let go of
  Python's lock for each check (a few microseconds), so whenever other Python
  work ran in the background (the engine rebuilt after a list update) every
  request of the page in view could wait up to 5 ms. It keeps the lock now:
  while the engine is rebuilt, the slowest check of a heavy page went from
  7-18 ms to about 2 ms and all its checks from 24-35 to 17-24 ms. Settings
  read for every request (per-site levels and options) are looked up without
  work when the user has none.
- **The graphics card named to sites is a common one** (fingerprinting): at
  Balanced each site gets one of eight Intel and NVIDIA models written exactly
  as Chrome reports them on Linux, without driver versions, of the same maker
  as the real card (an NVIDIA computer is told of an NVIDIA model, an Intel
  one of an Intel model: the limits WebGL reports tell the maker anyway, and
  another maker's name was a contradiction a script could see); AMD names, which
  on Linux always carry the LLVM and DRM versions and so were very rare (an
  "RX 580 ... LLVM 17.0.6, DRM 3.57" was one in 368,000 browsers on Cover
  Your Tracks), are no longer used. WebGPU names the same card as WebGL
  (vendor and architecture), in pages, frames and workers. At Strict and
  Maximum no card is named at all: the WEBGL_debug_renderer_info extension is
  hidden in every frame and worker (until now a model was shown there too,
  although the code said it was hidden) and WebGPU stays off. Checked in 23
  places a page can ask (frames of every kind, workers of every kind,
  OffscreenCanvas, WebGL 1 and 2). Not reachable: a worker a site starts from
  a file of its own (`new Worker("/w.js")`) sees the real values, as before;
  Qt WebEngine gives no way to add a script to it.
- **No page can read anything shared across sites** (found by an independent
  review; present since the protection's first versions): a page that
  replaced `Function.prototype.toString` could read the session's secret key,
  the same on every site, so any site could recognise the browser session
  everywhere without cookies; and the per-site noise came from a hash a page
  could undo. The key now stays inside I.K.E.: each site gets its own values,
  derived with SHA-256, and nothing a page can call ever receives a secret.
  A test plays the attack on two sites.
- **One Chrome version at Strict and Maximum** (owner's decision): JavaScript
  gave the reduced version (140.0.0.0) while the client hints a site asked for
  (Sec-CH-UA-Full-Version, Sec-CH-UA-Full-Version-List) carried the full one,
  so a page saw two different versions. The headers now say 140.0.0.0 too;
  only hints the engine already sends are changed, none is added. Balanced
  still gives the engine's real full version everywhere.
- **Workers of every kind get the protection**: a worker from a blob of any
  type or size, a worker started by another worker, and a worker from a blob
  address made inside a worker (they saw the real values).
- **Pictures and scripts of other sites load on pages that send no
  referrer**: on a page whose referrer policy is "no-referrer" or
  "same-origin", the shield added a Referer anyway and the engine cancelled
  every request to another site; now only a Referer the request carries is
  cut to its own origin.
- **Two request rules**: an http address of a sensitive service (Google
  account, PayPal, Stripe's checkout) is still made secure; a service
  worker's own request, which belongs to no page, is checked against the
  filter lists at Balanced too (it went the "same site, free way").
- **Tabs**: a tab counts as idle from the moment the user leaves it (a tab
  looked at for half an hour was suspended at the next check after the user
  left it); a tab of another workspace that plays sound or is loading is not
  suspended.
- **Hostile frames**: 23 ways a page can make or reach a new frame and use it
  at once (srcdoc, outerHTML, replaceWith, `<object>`, document.write,
  DOMParser, declarative shadow roots, cloneNode, moveBefore, a frame opened
  or sent to a new page again...) were played against the protection: every
  one gives the page's own protected values, never the real ones.
- **YouTube: less of I.K.E.'s own on top of the filter lists** (the owner saw
  YouTube's "ad blockers violate YouTube's Terms of Service" wall with
  1.1.17; approved by the owner on 2026-11-20). I.K.E. did three things on
  YouTube that neither uBlock Origin nor the lists do, two of them against
  choices the lists' maintainers made on purpose because YouTube refuses
  playback otherwise: its own rules blocked some of YouTube's own requests
  the lists leave open (api/stats/atr, which uBlock un-blocked for that
  reason, every api/stats/qoe request where the lists block one narrow form,
  delayplay, get_midroll_ and error_204); its video-ad fallback hid
  #player-ads and other boxes the lists keep visible on purpose; and an ad
  that could not be sought was sent to its end over and over (about 1,200
  jumps in three seconds in a local simulation; now one a second). Those
  requests and boxes are now left to the lists; other companies' ad and
  tracking hosts and YouTube's ad reports stay blocked, ads are still muted
  and hidden while they play, and nothing is done to hide the blocker from
  YouTube. Tested on local pages shaped like YouTube's player only:
  youtube.com cannot be reached from the test machine, so whether the wall
  is gone is checked on the owner's computer.
- **Tabs when memory runs short**: with less than a tenth of the computer's
  memory available, the tabs not looked at for five minutes or more are
  suspended a few at a time, oldest first, before their usual time (each gives
  back about 50 MB; 30 tabs: 1912 -> 422 MB when suspended). Nothing changes
  with enough memory or with suspension turned off.

Security audit of 2026-11-20 (an independent, read-only review of the whole
browser; every finding worked on before release, what is left is in
docs/SECURITY.md):

- **Every site in its own process** (owner's decision): Qt WebEngine leaves
  Chromium's Site Isolation off, so a frame of another site shared its page's
  process and one bug in the engine could let a page read the other site.
  I.K.E. now turns it on (`--site-per-process`), as Chrome always
  does; turning it off takes `IKE_ALLOW_UNSAFE_ENGINE=1`. Measured: four tabs
  with four frames of other sites each used 494 MB instead of 436 MB (+13 %),
  13 processes instead of 8.
- **The home network is protected from every kind of request**: until now
  only pages and frames of a public site were stopped from opening the
  router or a service of this computer; a POST from fetch, a picture, a
  script, a beacon or a WebSocket got there (the engine stops none of them).
  Every request is checked now, a stopped part shows the usual notice with
  "Allow for this site", and names local by their form count too
  (`router`, `fritz.box`, `*.lan`, `*.home.arpa`, `*.internal`...).
- **No page can read I.K.E.'s secrets on media sites**: the secret of the
  media-command events was a piece of the fingerprinting key, and a page on
  a media site could read it (and, with its own seed, work out the whole
  key and recognise the browser on other sites). The media secret is now a
  random value of its own, the page cannot see the events any more, and the
  hidden part of workers never reaches a function the page replaced.
- **An independent adversarial review** of this work found seven more ways
  around it, all fixed with a test that failed before: frames with no
  origin of their own (sandboxed, data:) reached the router; switches written
  in quotes or with one dash, and `QTWEBENGINE_DISABLE_SANDBOX=0`, still
  turned the sandbox off; the media secret leaked through a getter on
  Object.prototype; a replayed manifest could undo a halt; refusing to start
  as root counted a pending update as failed; workers at Strict and Maximum
  read the full Chrome version.
- **No browser without its sandbox by accident**: engine switches inherited
  from the environment that take a protection away (the sandbox, site
  isolation, web security, certificate checks, remote debugging, also
  `QTWEBENGINE_DISABLE_SANDBOX` and `QTWEBENGINE_REMOTE_DEBUGGING`) are
  dropped, and the window says which; graphics and video switches are never
  touched. Started as root (where the sandbox cannot work) I.K.E. no longer
  switches its sandbox off silently: it does not start, and says why. Both
  only with `IKE_ALLOW_UNSAFE_ENGINE=1`, and then the window and Help ->
  About say which protections are off. About also shows whether site
  isolation is on.
- **Websites are asked for the system's language**: every new profile asked
  for Italian ("it-IT,it,en-US,en") whatever the system's language, which
  gave non-Italian users Italian pages and a rare, identifying combination.
  Now the system's languages are asked for, as Chrome does (a German system:
  "de-DE,de,en-US,en"); settings that still had the old default follow the
  system, a list the user typed stays (Settings → General shows the system's
  list when the field is empty). Maximum still sends a common "en-US,en".
- **User scripts cannot be impersonated**: a message on the user-script
  bridge is taken only from a page the script really runs on (a frame that
  page has, matching the script's sites), not just from whoever has its
  token.
- **The web engine's age**: the notice that the system's engine is behind
  with its security fixes comes at three Chrome versions (it was five; two is
  normal between two Qt releases); About counts the age by the security fixes
  and shows the current Chrome it compares with, checked or estimated.
- **Signed updates that expire, arrive in stages and can be stopped**: every
  manifest expires after 180 days (an old copy kept back installs nothing),
  a release is offered over 24 hours instead of to everybody at once
  (`publish.py --urgente` for a security fix; with the daily check everybody
  has it within about two days), the owner can stop a release with a signed
  "halt" manifest, and a replayed older manifest cannot undo it. "Check for
  updates" does not wait.
- **Rust advisories checked every day**: the RustSec database against every
  crate of the AdBlock engine, on every pull request and daily
  (`security.yml`), with an issue when something is found.
- **The sandbox proven in CI**: a new job runs the security tests with the
  engine's sandbox really on, as a normal user, and fails if any page
  process runs without it (`test_sandbox.py`).
- **Not solved, said plainly** (docs/SECURITY.md): a public name that
  resolves to an address of the home network (DNS rebinding) is not stopped,
  nor are WebRTC and WebTransport: I.K.E. cannot resolve names in its
  request check without slowing every page, and the engine's own protection
  (Local Network Access, present in Qt 6.12 but off, with no per-site
  permission) is turned on in 1.1.19, for every site. A site's own worker can read its own noise
  seed. A page that frames one of a user script's sites and has stolen the
  script's token can still act as that frame.

Automatic maintenance and fixes (pull request #59; nothing of the browser):

- An old "Automatic fix needs you" issue no longer stops every later fix of
  `main`: only one naming the same failed commit, or reported in the last 24
  hours. A daily maintenance that cannot reach an upstream source, or whose
  new AdBlock engine does not build, becomes an issue instead of a fix of
  `main`. A pending fix is no longer dropped for later runs that only skip.
- The AI agent cannot write the repository's `.git`, and the runner runs git
  on its work without any configuration the agent could have written; it
  runs without the reserves' keys and without name lookups (DNS). Half-done
  work of the agent is always thrown away.
- Reserves: one model saying "not fixable" no longer stops the others (two
  must agree); a malformed answer moves to the next model; nothing a model
  writes can command the workflow.
- Checks: tests can no longer be weakened by removing or renaming a test,
  `assert True`, an early `return` or a changed reference file; YouTube's ad
  blocking, the test packages and the build tools are never changed by an
  automatic fix; Groq and OpenRouter keys are caught; a patch must apply.
- The weekly health check also reports failed automatic fixes, missing reserve
  keys, issues and maintenance pull requests waiting more than a week, and
  `main` without branch protection.

Licences (pull request #67):

- **Every licence shipped with the package**: LICENSE is now the complete GNU
  GPL v3 text (the I.K.E. notice moved to COPYRIGHT); the package and the
  self-update carry the licence and notice files of every Rust library
  compiled into the AdBlock engine (licenses/RUST-CRATES.txt), of the uBlock
  Origin scriptlets with their source (licenses/NOTICE.ubo-scriptlets) and of
  the Rust standard library, with docs/THIRD-PARTY.md. The tests refuse a
  library under a licence not approved in ike-adblock/deny.toml or from
  outside crates.io (cargo-deny).
- **Peter Lowe's list removed**: its author states no licence for it. It is
  gone from the lists, the credits and the documentation; settings of earlier
  versions lose it once, on or off, with its downloaded copy.

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
- **Full audit of the browser** (docs/review/security-audit.md, "Full audit"):
  - user scripts never fetch their libraries and resources (@require,
    @resource) from this computer or the home network, also through a
    redirect or a name that points there, unless the script itself was
    installed from there; an update that loads code from a new place asks
    first, and the install question says where the code comes from;
  - one click of the user is worth one download: a page that answers it with
    many gets the first and asks for the rest (until now every download of
    the next three seconds went through);
  - the new tab page's own links that change something (add a tile, choose
    the search engine) carry a key of the session: a web page's link to them,
    opened from the right-click menu, no longer adds bookmarks or changes the
    engine;
  - **home network protection**: a page of a public site that opens an
    address of this computer or of the home network (a form sent to the
    router, a frame of a local service) is stopped, and a bar offers "Allow
    for this site"; addresses the user opens are not touched;
  - a site name that does not resolve is no longer taken as "not local" by
    the checks of dark mode and of the user scripts' requests;
  - the clicks I.K.E. makes to skip a video ad no longer count as the user's
    (the ad blocking itself is unchanged);
  - an error while checking a request is counted (Help -> About) and a file
    of the computer stays refused;
  - two profiles open together never install an update at the same time,
    and never write the update state over each other;
  - a frame of the home network stopped inside a public page is said in the
    bar (it was silent), and an error inside the request checks keeps a
    public page's way into the home network refused;
  - the files of user scripts are downloaded from the very address that was
    checked (DNS rebinding: a name that answers "public" to the check and
    "home" to the connection no longer gets through).
- **Faster where it was measured, with the same protection** (the full
  measurements are in docs/review/tests-and-performance.md):
  - after a filter list update the AdBlock engine is rebuilt in the
    background while the engine in use keeps blocking; the window no longer
    stops for about 0.2 s (the engine module lets go of Python's lock while
    it builds or loads);
  - the shield's number is redrawn at most ten times a second instead of at
    every blocked element (150 redraws on a page full of ads), and always
    ends on the exact count;
  - the registrable domain of a host, asked several times for every request,
    is remembered;
  - with resource limits set, the check every 5 seconds no longer asks every
    tab for the data it downloaded (only the window shows it), and the
    window stops refreshing while minimized;
  - the settings file is written only when something changed (it was written
    every minute);
  - looking for Widevine at start no longer loads the download code;
  - at Strict and Maximum the font protection masks only the font names the
    engine can find on this computer (it asks the engine once, with the test
    fingerprinting scripts use, and again when the fonts change): a page still
    finds none of them, and a page with 30 frames opens about twice as fast.
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
  and data) is no longer checked against the filter lists, like the standard
  mode of other content blockers. Most of the requests of a page are the site's own, so the
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
  these sites is still respected.
- **Payments with PayPal and Stripe**: their anti-fraud checks can refuse a
  payment or a sign-in when part of them is blocked or changed (PayPal
  sign-ins that work only with the protections off are a known case). PayPal's sign-in
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
- **Faster pages** (measured on YouTube: less blocking
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
[The archived screenshot](https://github.com/NullSector-2077/IKE-Browser/blob/v1.1.26/docs/screenshots/ike-1.1.9.jpg) shows the new tab page with the default toolbar.

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
