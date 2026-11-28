# Web compatibility campaign, 2026-11-28 (I.K.E. 1.1.30)

Investigation, diagnosis and plan only: nothing in the browser was changed.
The tools are in [tests/compat/](../../tests/compat/README.md) and can be run
again at any time; they are not part of AUTOMAT nor of the automatic tests.

## 1. How it was tested

- **Arch Linux** container (`archlinux:latest` of 2026-11-28, fully updated):
  `qt6-webengine 6.140.0-2` (Chromium 140.0.7339.264),
  `python-pyqt6-webengine 6.140.1-1`, Python 3.14.
- **I.K.E. 1.1.30 built with `makepkg` from this repository's PKGBUILD and
  installed with pacman** (the AdBlock engine compiled from `ike-adblock/`):
  the program the users have, started through `ike_boot.py`.
- A fresh profile for every run, made from one base profile in which I.K.E.
  downloaded its **real filter lists** (EasyList, EasyPrivacy, uBlock filters,
  ...) and, through its own `drm.py`, the **Widevine** module.
- **Xvfb (X11)**, software OpenGL (Mesa llvmpipe). Without a graphics card the
  engine refuses WebGL on a software renderer ("WebGL1 blocklisted"), so the
  runs add `--ignore-gpu-blocklist` (test only; on a real PC the engine
  chooses its own GPU path). The engine sandbox is off (container).
- Each site opened in its own tab, **Dark Engine on**, at Compatibility,
  Balanced, Kontrol and Maximum; after 10-25 s a probe in I.K.E.'s own world
  (invisible to the page) checked the site's **main function** (results
  listed, video advancing, QR code drawn, map canvas, translation shown...),
  and every request I.K.E. blocked and every console message were recorded.
  Anomalies were repeated with the Dark Engine off and with the engine's own
  dark mode, and with level changes while the page is open (after the full
  load and 2.5 s after the start of the load).
- **Baselines**: Chromium 140.0.7339.207 (Chrome for Testing, the same
  Chromium as the engine) and Brave 1.82.172 (Chromium 140), driven by
  Playwright on the same network.
- **Experiments** (no code changed): Python run inside I.K.E. before the first
  site (`COMPAT_PATCH`) lifted one rule at a time, to prove causes.

Limits of the environment (they apply to every browser tested):

- The traffic leaves from a data centre: Google (Search, YouTube) answered
  with "unusual traffic", Microsoft refused Outlook's page as "an automated
  process", Cloudflare asked Claude and Vimeo for a human check, eBay showed
  an empty page, RaiPlay's live channels are only for Italy. These are marked
  `env` and compared with the baselines, never counted against I.K.E.
- No UDP and no DNS of its own: WebRTC through STUN cannot be tested; local
  WebRTC (two peers in one page) can.
- No accounts were used or created: Gmail, Drive, Docs, Facebook, Instagram,
  X, WhatsApp, Telegram, Discord, Teams, Spotify, PayPal, Canva, Outlook,
  Microsoft 365, ChatGPT, Claude and Gemini are tested up to their sign-in
  page or their public part (marked "partial"). Nothing was bought or sent.
- Cloudflare challenges belong to a separate investigation and were not
  analysed here (one observation was passed to it, see 4.7).

## 2. Matrix (Dark Engine on)

`ok` the main function works; `part` the page works, its main function was
not reached (or needs an account: "partial"); `FAIL` not working; `env` a
captcha or block of the data centre that the baseline browsers get too;
`n/t` the run stopped on that page; `-` not run. A `FAIL` of every browser
alike is the environment's (4.6). Kontrol and Maximum of the video sites come
from a second run with the corrected probe (the first one read the result
before the video check had finished).

| Site | Compat. | Balanced | Kontrol | Maximum | Chromium 140 | Brave 1.82 |
|---|---|---|---|---|---|---|
| Google Search | env | env | env | env | env | env |
| Gmail (partial) | ok | ok | ok | ok | ok | ok |
| Google Maps | ok | ok | ok | ok | ok | ok |
| Google Earth | ok | ok | ok | ok | ok | ok |
| Google Drive (partial) | ok | ok | ok | ok | ok | ok |
| Google Docs (partial) | ok | ok | ok | ok | ok | ok |
| Google Translate | ok | ok | ok | ok | ok | ok |
| Facebook (partial) | ok | ok | ok | ok | ok | ok |
| Instagram (partial) | ok | ok | ok | ok | ok | ok |
| X (home) (partial) | ok | ok | ok | ok | ok | ok |
| X (profile) | ok | ok | ok | ok | ok | ok |
| Reddit | ok | ok | ok | ok | FAIL | ok |
| WhatsApp Web (partial) | ok | ok | part | part | ok | ok |
| Telegram Web K (partial) | ok | ok | FAIL | FAIL | ok | ok |
| Telegram Web A (partial) | ok | ok | part | part | ok | ok |
| Discord (partial) | FAIL | FAIL | FAIL | FAIL | ok | ok |
| Microsoft Teams (partial) | ok | ok | ok | ok | ok | ok |
| YouTube | FAIL | FAIL | FAIL | FAIL | FAIL | FAIL |
| Twitch | ok | ok | ok | ok | ok | ok |
| Dailymotion | part | part | part | part | part | part |
| Dailymotion (player) | FAIL | FAIL | FAIL | FAIL | - | FAIL |
| Vimeo | FAIL | FAIL | FAIL | FAIL | FAIL | FAIL |
| Vimeo (player) | ok | ok | ok | ok | - | n/t |
| Spotify (partial) | ok | ok | ok | ok | ok | ok |
| SoundCloud | part | part | part | part | part | part |
| RaiPlay | ok | ok | ok | ok | ok | ok |
| RaiPlay (live) (partial) | FAIL | FAIL | FAIL | FAIL | FAIL | FAIL |
| Mediaset Infinity | ok | ok | ok | ok | ok | ok |
| Bitmovin | FAIL | FAIL | ok | FAIL | FAIL | FAIL |
| Shaka Player | ok | ok | ok | ok | ok | ok |
| HLS.js | ok | ok | ok | ok | ok | ok |
| Amazon | ok | ok | ok | ok | ok | ok |
| eBay | FAIL | FAIL | FAIL | FAIL | FAIL | FAIL |
| AliExpress | ok | ok | ok | ok | ok | ok |
| Booking | ok | ok | ok | ok | ok | ok |
| PayPal (partial) | FAIL | FAIL | ok | ok | FAIL | FAIL |
| Photopea | part | part | part | part | part | part |
| Canva (partial) | ok | ok | ok | ok | FAIL | ok |
| GitHub | ok | ok | ok | ok | ok | ok |
| Outlook (partial) | FAIL | FAIL | FAIL | FAIL | ok | FAIL |
| Microsoft 365 (partial) | ok | ok | ok | ok | ok | ok |
| ChatGPT (partial) | ok | ok | ok | ok | FAIL | ok |
| Claude (partial) | FAIL | FAIL | FAIL | FAIL | FAIL | FAIL |
| Gemini (partial) | ok | ok | ok | ok | ok | ok |

Summary: at Compatibility and Balanced every page that works in Chromium 140
works in I.K.E., except Discord (engine, 4.2) and Outlook's public page
(Microsoft refuses Brave too, 4.3). At Kontrol and Maximum the
same, plus the three messaging pages of 4.1. Twitch, Vimeo's player, Shaka,
HLS.js and (when Cloudflare let it through) Bitmovin play at Kontrol and
Maximum, as the owner saw.

## 3. Anomalies (one line each; details and evidence in section 4)

| # | Site, function | Levels | Chromium 140 / Brave | Dark Engine on / off / engine's dark | Cause | Severity | Evidence | Structural solution |
|---|---|---|---|---|---|---|---|---|
| A1 | WhatsApp Web: QR code never drawn (login impossible) | Kontrol, Maximum | works / works | same in all three | site's workers refused (R1 service worker, R3 dedicated workers vs the site's CSP) — proved | High | blocked `sw.js`; 6 × "Refused to create a worker from 'blob:'"; works with R1+R2+R3 lifted; works with Repair | S1 (+S2) |
| A2 | Telegram Web K: empty page (the "white page") | Kontrol, Maximum | works / works | white / dark-empty / dark-empty | shared workers (MTProto, crypto) and service worker refused (R1) — proved | High | blocked `index.worker`, `crypto.worker`, `sw`; works with R1 lifted | S1 (+S2) |
| A3 | Telegram Web A: QR shown, shared state and service worker missing | Kontrol, Maximum | works / works | same | R1 + R3 — proved | Medium | blocked `sharedState.worker`, `service.worker`; 6 CSP refusals; clean with R1-R3 lifted | S1 (+S2) |
| A4 | White page after a level change | Balanced → Kontrol/Maximum | n/a | white only with dark mode off | A1/A2 after the reload the level change makes; back to Balanced recovers | High (same as A1/A2) | screenshots: 100 % white pixels; recovery at Balanced; no lasting damage after early changes | S1 |
| A5 | Service workers of many sites (offline, push, faster start): Reddit, Twitch, Spotify, SoundCloud, RaiPlay, Amazon, AliExpress, Teams | Kontrol, Maximum | work / work | same | R1/R2 | Low (no visible break before sign-in) | blocked service worker scripts | S1 |
| A6 | Teams (and Google apps, GitHub, Gemini) after sign-in: dedicated workers refused | Kontrol, Maximum | work / work | same | R1/R3 with `worker-src 'self'` | Unverified (needs account) | 2 blocked `Worker` requests on Teams; site policies measured | S1 |
| A7 | Discord: sign-in page never rendered | every level | works / works | same | Qt WebEngine 6.140 (also bare Qt, without I.K.E.); exact API not found | Medium | bare Qt reproducer | S3 (report to Qt) |
| A8 | Outlook: "request blocked, automated process" page for visitors not signed in | every level | works / **blocked too** | same | Microsoft's page refuses browsers that are not Chrome (Brave too, bare Qt too); not headers, not kernel version, not `window.chrome` | Low (sign-in at login.live.com works) | curl with the same headers passes; Brave gets the same page | none for now; check from home |
| A9 | WebAuthn capability questions never answered | every level | answered / — | same | Qt WebEngine | Low (latent) | bare Qt test | S3 |
| A10 | WebRTC between two peers in one page | every level | works / — | same | "Hide the IP address in WebRTC" (public interfaces only) in a container without a public interface | Low / to verify on a PC | works with the option off | S4 |

Not anomalies of I.K.E. (all browsers alike, section 4.6): Google Search and
YouTube ("unusual traffic"), Vimeo and Claude (Cloudflare check), eBay,
PayPal's bot check, RaiPlay live (Italy only), Bitmovin's demo (no video
element reached), Dailymotion's player page alone.


## 4. Findings, grouped by cause

### 4.1 Kontrol and Maximum refuse the sites' own workers (WhatsApp, Telegram) — HIGH

**Sites:** WhatsApp Web (QR code never drawn: a spinner forever), Telegram
Web K (empty page: white without dark mode, dark and empty with it), Telegram
Web A (QR code shown, but no shared state and no service worker), Microsoft
Teams (two dedicated workers refused; the effect after sign-in could not be
checked). Lost at the same levels on many other sites, without a visible
break before sign-in: the service workers of Reddit, Twitch, Spotify,
SoundCloud, RaiPlay, Amazon, AliExpress, Teams and the Shaka demo (offline
pages, push notifications, faster loading). Google's apps (Gmail, Drive,
Docs, Translate, Earth), GitHub, Reddit and Gemini allow workers only from
their own files (`worker-src 'self'` or a strict `script-src`): at Kontrol
their dedicated workers cannot be started either; what this breaks after
sign-in was not testable without an account.

**Levels:** Kontrol and Maximum only. Compatibility and Balanced work.
Chromium 140 and Brave 1.82 (Chromium 140): work. Same result with the Dark
Engine on, off, and with the engine's own dark mode: **the Dark Engine is not
involved.**

**Cause (proved).** Three rules added in 1.1.25 (the owner's decision of
2026-11-24) so that no worker runs without the fingerprinting protection:

- R1, `ike/shields.py` `Interceptor.interceptRequest`: at level >= 3 the
  scripts of service workers, shared workers and dedicated workers
  (`_WORKER_SCRIPTS`) are blocked in the engine. Seen blocked:
  `web.whatsapp.com/sw.js`, `web.telegram.org/k/index.worker-*.js` and
  `crypto.worker-*.js` (shared workers: Telegram K's MTProto connection and
  its encryption), `web.telegram.org/a/sharedState.worker-*.js`, the service
  workers listed above.
- R2, `ike/resources/fingerprint.js` (end of the file): at Kontrol and above
  every service worker registered earlier is unregistered.
- R3, `fingerprint.js` `fromFile()`: a dedicated worker from the site's own
  file is started from a `blob:` address that holds the protection and then
  the site's script. WhatsApp (`worker-src *.whatsapp.com/static_resources/...`)
  and Telegram (`worker-src 'self'`) do not allow `blob:` workers, so the
  engine refuses it ("Refused to create a worker from 'blob:...'", six times
  on each). The code then means to fall back to the page's own address, but
  that refusal is **asynchronous** (checked in Chromium 140: the constructor
  returns, then a `securitypolicyviolation` and an `error` event), so the
  fallback in the `catch` never runs; and R1 would block it anyway.

Experiments in the real browser at Kontrol, nothing else changed:

| Lifted | WhatsApp | Telegram K | Telegram A |
|---|---|---|---|
| nothing (Kontrol as shipped) | spinner, no QR | empty page | QR, errors |
| R1 | spinner, no QR | **works** | QR, errors |
| R1 + R2 | spinner, no QR | (not run) | QR, errors |
| R1 + R2 + R3 | **works** | works | **works, no errors** |
| "Repair this site" (fingerprinting off for the site) | works | works | (not run) |

Nothing else at Kontrol is involved: filter lists (only WhatsApp's own logging
request `/ajax/bz` is blocked, harmless), cookies, storage, the frame guard,
the scriptlets and the Engine Privacy Layer switches are the same at Balanced,
where everything works.

**The white page after a level change.** Reproduced with Telegram K: open at
Balanced (works), switch to Kontrol or Maximum: the page reloads empty, 100 %
white pixels without dark mode (dark and empty with the Dark Engine or the
engine's dark mode, because I.K.E. paints the page's backdrop dark). WhatsApp
logged out shows its frame with an endless spinner instead. Switching back to
Balanced brings both back; changes 2.5 s after the start of a load leave no
lasting damage either. A logged-in WhatsApp (not testable without an
account) starts its whole interface from its service worker and workers, so
at Kontrol it most likely stays on an empty page: the same cause.

**What the workers would reveal if allowed** (measured at Kontrol with R1-R3
lifted; the page's values in brackets): service and shared workers tell the
engine's own values: the real graphics card through `OffscreenCanvas` WebGL
("ANGLE (Mesa, llvmpipe ...)", 35 extensions) [`WebKit WebGL`, 22], a canvas
without noise [noised], Chrome's full version `140.0.7339.264` in
`getHighEntropyValues` [`140.0.0.0`], `languages` `en-US` [`en-US,en`], the
real number of cores on a computer with more than 8 [4 or 8]. Dedicated
workers started through the blob wrapper keep the page's values exactly.
Only code served from the site's own origin runs in service and shared
workers (the browser allows nothing else); a page's third-party scripts
cannot start them, except through files the site itself serves (a push SDK
imported by the site's service worker, for example).

### 4.2 Discord does not render its sign-in page — MEDIUM (engine)

Every level, also with the shield off and **in a bare Qt WebEngine 6.140
window without I.K.E.**: the page loads its 450 resources and renders
nothing (no error, no rejected promise). Chromium 140 and Brave: works. A Qt
WebEngine problem, not I.K.E.'s; the exact missing piece was not found in
this campaign (the WebAuthn queries of 4.4 were ruled out: Discord does not
call them before it renders).

### 4.3 Microsoft's Outlook page calls I.K.E. (and Brave) "an automated process" — LOW

`outlook.live.com/mail/` sends a visitor who is not signed in to
`www.microsoft.com/.../outlook...`, and that page answers I.K.E. "Your
request has been blocked ... Your current User-Agent string appears to be
from an automated process", at every level, in bare Qt WebEngine **and in
Brave 1.82**; only Chromium 140 gets the normal page. The Microsoft account sign-in
(`login.live.com`) and Teams' sign-in work at every level, so signing in
is possible. Ruled out: the request headers (the same headers sent with curl
get the normal page), the hidden kernel version (sending it changed
nothing), `window.chrome` (I.K.E. already gives Chromium's shape since
1.1.30). The decision is made by the page's own scripts; since Brave is
refused as well, it is Microsoft's choice about browsers that are not Chrome
(seen from a data centre), not a defect of I.K.E. Nothing to change in
I.K.E. for now; to check again from a home connection.

### 4.4 Qt WebEngine never answers three WebAuthn questions — LOW (engine, latent)

`PublicKeyCredential.getClientCapabilities()`,
`isConditionalMediationAvailable()` and
`isUserVerifyingPlatformAuthenticatorAvailable()` never settle, at every level
and in bare Qt WebEngine; Chromium 140 answers at once. A sign-in page that
waits for them before showing its form would stay empty. None of the tested
sign-in pages (Google, Microsoft, PayPal, Facebook, Instagram, Claude)
was affected; it is also a way to tell Qt WebEngine apart from Chrome.

### 4.5 WebRTC without host candidates where there is no public interface — LOW / to verify

With "Hide the IP address in WebRTC" on (the default,
`WebRTCPublicInterfacesOnly`), two peers in the same page could not connect in
the container (no candidate at all); with the option off they connect at once
through an mDNS host candidate, as in Chromium 140. On a normal PC the
default-route interface gives a candidate and STUN adds the public one, so
this should only matter on networks without a default route or behind some
VPNs. STUN itself cannot be tested here (no UDP); calls (Meet, Teams,
Discord) need a test on a real PC.

### 4.6 Environment only (not I.K.E.)

Answers given to every browser from this data centre, Chromium 140 and
Brave included: Google's "unusual traffic" page on Search and YouTube,
Cloudflare's human check on Vimeo's and Claude's pages, eBay's empty page,
PayPal's "Invalid request" (its bot check, also for Chromium 140; at Kontrol
I.K.E. got the sign-in form), Dailymotion's player "Forbidden" outside a
page that embeds it, RaiPlay's live channels only for Italy. They need a run
from a home connection.

### 4.7 Cloudflare (handed to the separate investigation)

At Kontrol and Maximum the Turnstile frame of Vimeo's and Claude's checks
logged "Refused to create a worker from 'https://challenges.cloudflare.com/
...turnstile...'": probably the same R3 mechanism (4.1). Passed to the
Cloudflare session as data; not analysed further here.

## 5. Web technologies (local test page, `tests/compat/webtech/`)

Served on `http://localhost:8123` (a secure context), I.K.E. at the four
levels with the Dark Engine on, against Chromium 140 on the same machine.

| Technology | Compat. | Balanced | Kontrol | Maximum | Chromium 140 | Notes |
|---|---|---|---|---|---|---|
| WebSocket (`wss://`) | ok | ok | ok | ok | ok | echo server |
| Dedicated worker (file, module, blob) | ok | ok | ok | ok | ok | at Kontrol/Maximum through the protected wrapper (the page's values inside) |
| Shared worker (file) | ok | ok | **refused** | **refused** | ok | 4.1 |
| Service worker (register, message, fetch) | ok | ok | **refused** | **refused** | ok | 4.1 |
| WebAssembly (streaming) | ok | ok | ok | ok | ok | `SharedArrayBuffer` only with cross-origin isolation, as in Chromium |
| WebGL 1 and 2 | ok | ok | ok | ok | ok | software GL with `--ignore-gpu-blocklist`; Kontrol/Maximum show the common identity "WebKit WebGL" |
| WebGPU | no adapter | no adapter | no adapter | no adapter | no adapter | no GPU in the container; not testable |
| Canvas 2D | ok | ok | ok | ok | ok | flat colours exact; noise only where expected |
| IndexedDB, localStorage, sessionStorage, Cache API, storage estimate | ok | ok | ok | ok | ok | |
| BroadcastChannel, Web Locks, Compression Streams | ok | ok | ok | ok | ok | |
| Codecs: H.264 (baseline, high), AAC, AV1 (MP4, WebM), VP9, VP8, Opus (WebM, MP4), FLAC, MP3 | ok | ok | ok | ok | ok | `canPlayType` "probably", MSE yes, real playback of H.264+AAC, VP9+Opus, AV1+Opus, AV1, Opus files |
| HEVC | no | no | no | no | no | not in Chromium 140 without hardware support |
| WebCodecs (H.264, VP9, AV1 decoders) | ok | ok | ok | ok | ok | |
| DASH (Shaka Player), HLS (hls.js) | ok | ok | ok | ok | ok | Google's and Mux's public test streams |
| DRM: ClearKey | ok | ok | ok | ok | ok | |
| DRM: Widevine | ok | ok | ok | ok | ok | module downloaded by I.K.E.'s own `drm.py`; Shaka's Widevine test stream played at every level |
| WebRTC, two peers in one page | **no candidate** | **no candidate** | **no candidate** | **no candidate** | ok | 4.4; works with "Hide the IP address in WebRTC" off |
| WebRTC through STUN | n/t | n/t | n/t | n/t | n/t | no UDP in the container |
| Camera and microphone | permission sign | permission sign | permission sign | permission sign | ok (fake devices) | I.K.E. shows its quiet permission sign and waits for the user (by design); devices listed at Compatibility and Balanced, hidden until a permission at Kontrol/Maximum |
| Notifications | refused without a click | same | same | same | same | `requestPermission()` without a user gesture refused at once (by design) |
| Upload (`FormData` with a file) | ok | ok | ok | ok | ok | |
| Download (`<a download>` blob, `Content-Disposition` file) | ok | ok | ok | ok | ok | both files saved |
| PDF | ok | ok | ok | ok | ok | the engine's PDF viewer |
| Hardware acceleration | n/t | n/t | n/t | n/t | n/t | no GPU; `mediaCapabilities` reports smooth but not power-efficient decoding here |
| Missing compared with Chromium 140 | `PaymentRequest`, `EyeDropper` | | | | | Qt WebEngine's own gaps, at every level |

n/t: not testable in this environment.


## 6. Proposed structural solutions (for the owner's decision; nothing done)

The constraints of the campaign hold for all of them: no protection lowered
by itself, no general list of allowed sites, fingerprinting protection and its
randomisation untouched in the page, the sandbox untouched, no site's
security check bypassed, no rule for a single site, no extra cost.

### S1 — Kontrol: the site's own workers run; every worker a third party can start stays protected (recommended)

The one cause of 4.1 is the rule "no worker without the protection", applied
also where the protection cannot be put into the worker. The browser itself
decides who can start which worker:

| Worker | Who can start it | Today at Kontrol | Proposed at Kontrol | Maximum |
|---|---|---|---|---|
| dedicated, from `blob:`/`data:` (also a tracker's) | any script of the page | protected (prelude) | unchanged | unchanged |
| dedicated, from the site's file, `blob:` allowed by the site | page scripts, only same-origin files | protected (blob wrapper) | unchanged | unchanged |
| dedicated, from the site's file, `blob:` **forbidden** by the site | page scripts, only same-origin files; nobody can make a `blob:` worker there | refused (breaks WhatsApp, Telegram A, Google apps) | the site's file, engine values | refused |
| shared worker from the site's file | only same-origin files | refused (breaks Telegram K and A) | the site's file, engine values | refused |
| service worker | only same-origin files | refused and unregistered (breaks WhatsApp, offline/push everywhere) | allowed, not unregistered | refused |

In words: at Kontrol a worker runs without the protection only when nothing
but the site's own files can be in it; anything a third-party script could
start keeps the page's values exactly as today. Maximum keeps the 1.1.25 rule
unchanged (the level that may break sites), and says so (S2).

Work:

1. `shields.py`: the worker rule of the interceptor for level 4 only
   (`lv >= 4`); at 3 the scripts of service and shared workers pass.
2. `fingerprint.js`: the unregistering of service workers only at Maximum.
3. `fingerprint.js` `fromFile()`: when the page's policy refuses the protected
   `blob:` copy, start the site's own file instead, inside the same `Worker`
   object the page already holds: the refusal is asynchronous (4.1), so the
   protection listens for its `securitypolicyviolation`, starts the real
   worker, sends it the messages the page posted meanwhile and passes its
   messages and errors on, and hides the engine's error about the refused
   copy (`sameErrors` already does this for other errors). After the first
   refusal the document starts file workers directly. Only pages that both
   forbid `blob:` workers and start workers pay anything; no page pays at
   start. Tests: WhatsApp-like and Telegram-like local pages with the same
   policies, at every level, plus the existing worker tests.
4. Residual difference to know: in service and shared workers a site's own
   code sees the engine's values (full Chrome version, real graphics card,
   canvas without noise, real number of cores above 8, `languages` `en-US`),
   as it already does at Balanced today. Only the site itself can put code
   there (or a library it imports into its own service worker). I.K.E.'s
   Engine Privacy Layer already gives every realm the same language, time
   zone and user agent; the rest has no engine switch in Qt 6.140.

Expected result (from the experiments of 4.1): WhatsApp, Telegram K and
Telegram A work at Kontrol; service workers (offline, notifications, faster
starts) work again on the sites of 4.1; nothing changes at Maximum; no extra
work at page start; less work for the interceptor (fewer blocks).

### S2 — A narrow switch and a visible reason (with S1, or alone if S1 is refused)

1. A new per-site protection "Workers of this site" (`site_opts[host]["workers"]`)
   that the interceptor rule and `fingerprint.js` read instead of the whole
   fingerprinting switch `fp`. Today "Repair this site" on WhatsApp at Kontrol
   finds `fp` and turns **all** fingerprinting protection off for the site
   (verified: it works, but much more than needed). With the new key first in
   `repair.PROTECTIONS`, Repair finds the workers alone and leaves canvas,
   WebGL, fonts, screen, audio... protected.
2. The shield counts the workers it refused on the page ("2 workers
   blocked by Kontrol") and, when there are any, offers "Repair this site".
   No automatic change: the user decides.
3. At Maximum (and at Kontrol if S1 is refused) this is how WhatsApp and
   Telegram are used without lowering the level of every site.

Cost: one dictionary lookup per worker request; nothing at page start.

### S3 — Engine problems: report them and follow the Qt releases

- Discord (4.2) and the WebAuthn questions (4.4): report to Qt
  (bugreports.qt.io) with the bare Qt WebEngine reproducer of
  `tests/compat` (no I.K.E. involved); run the suite again on each new
  `qt6-webengine` of Arch.
- An I.K.E. answer for the three WebAuthn questions after a short wait
  ("no platform authenticator", as Chromium answers on a PC without one) is
  possible in the page script, but it changes the page at every level (the
  1.1.12 rule "nothing in a page is changed outside the protections chosen"):
  only if a real site is found that needs it. None of the tested sites does.

### S4 — WebRTC: measure on a real PC first

Run `tests/compat/webtech/index.html` on a real PC, with "Hide the IP address
in WebRTC" on and off, plus a real call (Meet or Jitsi). Chromium already hides
local addresses behind mDNS names; if the option only removes the local
candidate, it costs compatibility without hiding more. Decide after the
measurement.

### Order proposed

1. S1 (and S2) on one branch, with tests, measured before and after
   (`tests/measure_perf.py`, the compat suite at all four levels).
2. The Qt reports of S3.
3. S4 on the owner's PC (five minutes, a guided procedure).

## 7. Not verified

- Anything after a sign-in (no account was used or created): the chats of
  WhatsApp and Telegram, Gmail, Drive, Docs, Teams, Spotify playback,
  ChatGPT, Claude and Gemini conversations. A logged-in WhatsApp at Kontrol
  (the owner's "white page" with the Dark Engine on) could not be seen; the
  cause above explains it, the screenshot does not prove it.
- A real graphics card (WebGPU, hardware video decoding, the engine's GPU
  blocklist on old cards), real cameras and microphones, notifications shown
  by the desktop, WebRTC calls across the Internet.
- Brave with maximum protection: Brave 1.82 ran with its default Shields.
  Brave protects inside workers because it changes the Chromium engine
  itself; I.K.E. on Qt WebEngine cannot, which is the origin of the choice
  between refusing the workers and letting them run.
- Falkon and qutebrowser were installed but not needed: for Discord and
  Outlook a bare Qt WebEngine window (the same engine, nothing around it)
  already gave the answer.
- The engine sandbox was off (container); the sandbox does not change what a
  page can do.
- One crash at the end of a run in Xvfb (Maximum, after the last site, while
  closing): "Segmentation fault" with an X connection error; not seen in the
  other 30 runs, not investigated.

## 8. The reusable suite

`tests/compat/` (see its README): `run.py` (I.K.E. at one level, real lists,
fresh profile, level changes, experiments), `steps.py` and `probe.js` (what
each page did), `sites.json` (44 pages and their checks), `baseline.js`
(the same checks in Chromium or Brave), `matrix.py` (the table above),
`webtech/` (technologies, streaming, DRM). One full matrix takes about 45
minutes per level on 4 cores; two levels can run at once. Not part of
AUTOMAT, of `python3 -m pytest` or of GitHub Actions, as asked.
