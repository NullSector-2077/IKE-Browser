# Changelog

## 1.1.23

- uBlock Origin scriptlets: 2bc679d99a (2026-11-10) -> 5934db2a04 (2026-11-21) (1 changed, 0 new, 0 removed)

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
