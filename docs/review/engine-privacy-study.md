# Engine Privacy Layer: feasibility study (2026-11-27)

Question (owner): can I.K.E.'s engine (Qt WebEngine) look to websites like an
ordinary Chrome/Chromium, natively (engine switches) rather than by injected
JavaScript, without replacing or forking Qt WebEngine, without weakening any
protection, and maintained automatically by AUTOMAT?

Status: study only. Experimental branch `claude/sharp-faraday-bp7cvq`; nothing
merged, nothing changed in I.K.E.'s code. Tools: `tools/engine-probe/`.

## Setup (verified)

| Browser | Version | Where |
|---|---|---|
| Qt WebEngine (Arch `qt6-webengine 6.140.0-2`) | Chromium 140.0.7339.264, security patches of 157.0.8103.50 | local Arch chroot and GitHub Actions (archlinux:latest) |
| I.K.E. (this checkout) at off, compatibility, balanced, strict, maximum | same engine | both |
| Arch Chromium 140.0.7339.207 (Arch Linux Archive) | same generation | GitHub Actions |
| Chrome for Testing 140.0.7339.207 | same generation | both |
| Arch Chromium 158.0.8127.88 (latest) | latest | both |
| Chrome for Testing 158.0.8127.88 | latest | local |
| Google Chrome 158.0.8127.88 stable | latest | GitHub Actions |
| Brave 1.100.59 (Chromium 158) | latest | GitHub Actions |

Same machine and conditions per run (Xvfb 1920x1080, Mesa llvmpipe through
ANGLE for WebGL, root in a container so the sandbox is off for every browser,
LANG en_US, TZ Europe/Rome). Facts that depend on the machine (GPU, screen,
fonts, memory, network hints) are classified "environment" and left out of
the counts. Repeated runs: Qt vs Qt 14 differing facts (all ECH GREASE length
and network hints), Chrome vs Chrome 18, Brave vs Brave 93 (Brave randomises
per session).

The probe (`probe.html`) records ~48,000 facts per browser: every global and
every interface member (page, same-origin frame, dedicated, shared and
service workers), CSS computed properties, 160 `CSS.supports` tests, 23
at-rules, 26 media queries, 47 V8 error messages, stack format, native
function text, Intl/ICU, navigator and all client hints, WebGL 1/2, WebGPU,
canPlayType/MSE/MediaRecorder/WebCodecs/WebRTC codecs, EME key systems, 37
permissions, the permission policy, `window.chrome`, 24 WebAssembly
features, request headers (names, order, values), the TLS ClientHello (JA4,
sorted JA3) and the HTTP/2 preface (Akamai fingerprint).

## 1. How sites recognise I.K.E. today (verified)

Page-level facts that differ (environment excluded), GitHub Actions run
46010536780:

| | Chromium 140 (Arch) | Chrome 140 | Chromium 158 | Chrome 158 | Brave 158 |
|---|---|---|---|---|---|
| Qt WebEngine bare | 474 | 503 | 1857 | 1873 | 1964 |
| I.K.E. off | 451 | 462 | 1820 | 1836 | 1963 |
| I.K.E. compatibility | 472 | 475 | 1842 | 1858 | 1949 |
| I.K.E. balanced | 483 | 486 | 1853 | 1869 | 1954 |
| I.K.E. strict | 464 | 467 | 1834 | 1850 | 1953 |
| I.K.E. maximum | 462 | 465 | 1832 | 1848 | 1951 |
| balanced + candidate switches | 571 | 574 | 1784 | 1800 | 1872 |
| Chromium 140 (Arch) | 0 | 44 | 1429 | 1445 | 1657 |
| Chrome 158 | 1445 | 1452 | 42 | 0 | 345 |

Strict and Maximum also refuse service workers and shared workers from a
file (by design), which removes two whole realms (~11,000 facts); not
counted above.

Three layers:

**A. Engine age (the dominant signal, ~75 % of the facts).** Chromium 140 vs
158: 88 interfaces missing, 74 CSS properties, new CSS functions and
selectors, `Temporal`, `Math.sumPrecise`, permission-policy features, WGSL
language features. Network: the TLS ClientHello of Qt is byte-for-byte
Chrome 140's (JA4 `t13d1516h2_8daaf6152771_d8a2da3f94cd`, also on
tls.browserleaks.com); Chrome/Chromium 158 add the Trust Anchor IDs extension
(0xca34) and ML-DSA signature algorithms (JA4 `t13d1517...`).

**B. Qt WebEngine's own gaps (present in Chrome and Chromium of the same
version, absent in Qt), version-independent:**
- 36 globals: PaymentRequest family (5), WebUSB (16), Background Fetch (3),
  Document Picture-in-Picture (2+1), EyeDropper, WebOTP (OTPCredential),
  Web Speech recognition (`webkitSpeechRecognition` family, 5), built-in AI
  (Summarizer, Translator, LanguageDetector, CreateMonitor),
  CookieDeprecationLabel; plus `navigator.usb`,
  `navigator.getInstalledRelatedApps`, `Request.targetAddressSpace`,
  `ServiceWorkerRegistration.backgroundFetch`; permission-policy `payment`,
  `usb`, `otp-credentials`.
- `window.chrome` exists but is empty; Chrome and Chromium have `app`,
  `csi`, `loadTimes`.
- `navigator.permissions.query`: 17 permissions `denied` where Chromium
  says `prompt` or `granted`.
- Intl: Arch builds Qt WebEngine with the system ICU (12 collations, 162
  currencies, 78 numbering systems) where Chromium 140 bundles its own (10,
  159, 69): reveals "Qt WebEngine on a distribution".
- WGSL language features: 0 (Chromium 140: 4).
- HTTP/3: Qt never uses QUIC (cloudflare-quic.com, third load: `h2`); every
  Chrome, Chromium and Brave uses `h3`.
- Widevine: only when I.K.E. finds a CDM (ike/drm.py); plain Chromium has none
  either.
- Same as Chrome 140, verified: CSS, V8 errors and stack, WebAssembly
  features, WebGL extensions and parameters on the same GPU, codecs, HTTP/2
  preface, header order of plain Qt.

**C. I.K.E.'s own choices:** UA without "QtWebEngine" and brands consistent in
every realm (good); kernel version hidden (good); Balanced adds two random
plugins (as Brave); Sec-GPC header and `navigator.globalPrivacyControl` (as
Brave); Strict and Maximum report `140.0.0.0` as full version (as Brave
reports `158.0.0.0`), refuse service and shared workers, normalise WebGL to
a minimal profile; Balanced sends `Accept-Language: en-US,en` with no
q-values, which no Chromium sends (Chrome `en-US,en;q=0.9`, Brave randomises
q). The header order of Balanced (Sec-GPC after Accept, Accept-Language
last) equals Brave's.

**Public tools (GitHub Actions):** CreepJS: bare Qt 63 % "like headless", I.K.E.
at every level 44 %, the same as Chrome 158 and Brave; no lies reported.
Cover Your Tracks: every browser unique or nearly unique on the CI machine
(an unusual machine: not informative about the engine); I.K.E. "some
protection", Brave "strong", Chrome "not protected". BrowserLeaks TLS:
I.K.E. = Chrome 140.

## 2. What engine switches can and cannot do (verified)

Blink's feature lists of 140 and 158 (`runtime_enabled_features.json5`):
399 features stable in 158 do not exist in 140's code at all; only 57 exist
behind a switch (41 experimental, 13 test).

| Experiment (Qt bare, toward Chrome 158) | fixed | broken | new unique | verdict |
|---|---|---|---|---|
| `--enable-blink-features=` the 57 | 147 | 76 | 14 | no: early implementations differ from the shipped ones (AnimationTrigger, permission element) |
| `--enable-experimental-web-platform-features` | 200 | 633 | 5 | no |
| `--js-flags=--harmony` / `--js-staging` | 0 | 0 | 0 | no effect: Temporal, sumPrecise not built |
| `--enable-features=TLSTrustAnchorIDs` | 0 | 0 | 0 | no effect: needs Chrome's root store data |
| `--enable-blink-features=ScriptedSpeechRecognition` | - | - | - | page process killed ("No binder found for interface media.mojom.SpeechRecognizer") |
| PaymentRequest, EyeDropper, WebOTP, DocumentPictureInPictureAPI, Translation/LanguageDetection/AISummarization APIs | 0 | 0 | 0 | no effect: compiled out or gated elsewhere |
| WebUSB, InstalledApp | appear, `getDevices()` = [] | | | technically possible; adds a hardware-access surface with no chooser in Qt: rejected |
| **remove what Chrome 158 removed**: `--disable-blink-features=Fledge,AdInterestGroupAPI,SharedStorageAPI,AttributionReporting` (+ matching `--disable-features`) | **69** | **0** | **0** | works; see 3 |

## 3. The one native change that works, and its trade-off

Removing the Privacy Sandbox advertising APIs that current Chrome no longer
has (Protected Audience/FLEDGE, Shared Storage, Attribution Reporting,
Private Aggregation): 69 facts closer to Chrome 158, none broken, nothing
new. Privacy benefit: these are cross-site advertising and measurement APIs.
Cost (GitHub Actions, 8 alternated runs): probe page median 2542 ms vs
2525 ms, start-to-result 3.8 s both: within noise. Compatibility: APIs
already gone from Chrome; Brave never had them.

Trade-off: the same 69 facts move I.K.E. away from Chrome 140, the version it
truthfully presents (TLS, CSS, V8 all say 140). "Chromium 140 without the
ad APIs" matches Brave-like and de-Googled builds of that age, not stock
Chrome 140. Since the crowd of real Chrome 140 users in late 2026 is small
(Chrome auto-updates), and the other signals (Sec-GPC, plugins at Balanced)
already point to the privacy-browser crowd, the change is a modest gain,
not a disguise.

## 3b. HTTP/3 (QUIC)

Qt WebEngine leaves QUIC off; every Chrome-family browser uses it. A
server sees "Chromium UA, never QUIC": a network-level difference no page
script can see but any CDN logs. `--enable-quic` turns it on (verified).
Open points for the review: why Qt leaves it off (proxies, its own network
settings), whether I.K.E.'s DNS-over-HTTPS, proxy handling and request
interception (ad blocking) still apply to QUIC requests.

Refinement of 3 (verified on Chrome 158 stable): `AttributionReporting`
must stay on: Chrome 158 still has `attributionSrc` and
`XMLHttpRequest.setAttributionReporting` (6 facts broken with it off).
The candidate set is `--disable-blink-features=Fledge,AdInterestGroupAPI,
SharedStorageAPI` and `--disable-features=Fledge,SharedStorageAPI,
PrivateAggregationApi,InterestGroupStorage`.

## 4. Presenting a newer version: not credible (verified)

The engine would claim 158 while the TLS handshake (no 0xca34, no ML-DSA),
88 missing interfaces, 74 CSS properties and JavaScript built-ins say 140.
Anti-bot services compare exactly these. The decision of 1.1.14
(`ike/chromever.py`: present the engine's real version) is confirmed.

## 5. Ideas outside engine switches (assessed, not built)

- `window.chrome.{app,csi,loadTimes}` by I.K.E.'s page script: cheap, would
  remove one classic "not Chrome" test; but it simulates a deprecated API
  (values must be plausible) and the constraint "no artificial responses"
  argues against it. Owner's decision.
- `Accept-Language` with Chrome's q-values at Balanced (`en-US,en;q=0.9`):
  a fix in I.K.E.'s own Python, no simulation; recommended.
- QUIC: `--enable-quic` (an engine switch, verified on GitHub Actions run
  46016302796): Qt and I.K.E. Balanced then use `h3` on cloudflare-quic.com
  as Chrome does; the probe's facts are unchanged (0 fixed, 0 broken).
  Second native change that works; see 3b.
- Missing Qt APIs, permission states, system ICU: not removable without
  changing Qt WebEngine or Arch's build.

## 6. Maintenance (proposal)

`tools/engine-probe/identity_guard.py` (prototype) checks, after each Qt
WebEngine update: the layer's switches still remove their APIs in every
realm (a renamed feature is ignored silently by the engine: this notices
it); one identity in page, frame and workers; JA4 equals the same-generation
Chromium; no new Qt-only gap beyond a recorded baseline. Proposed home: the
weekly Arch runs (`arch.yml`, `arch-testing.yml`) with Chrome for Testing of
the engine's own version (downloaded by version number, so nothing is fixed
by hand), its failures routed like any Arch failure to AutoFix.

## 7. Independent review (Fable 5.2, high reasoning) and corrected conclusions

The reviewer re-ran experiments in the same Arch chroot (results in the
session's scratch space, not committed). Spot-checked here: findings 1 and 4
reproduced from its result files.

1. **Ad APIs, corrected.** Qt's ContentBrowserClient leaves
   `IsInterestGroupAPIAllowed` and `IsSharedStorageAllowed` at their default
   `false` (Chromium 140 `content_browser_client.cc`): FLEDGE and Shared
   Storage are already inert in Qt (`sharedStorage is disabled`). Attribution
   Reporting is **active** (`IsAttributionReportingOperationAllowed` defaults
   to `true`): a response with `Attribution-Reporting-Register-Source` wrote
   rows in the profile's `Conversions` database on bare Qt and on I.K.E. off
   and Balanced; I.K.E. sends `Attribution-Reporting-Eligible` and
   `Sec-Browsing-Topics`. `--disable-features=ConversionMeasurement` stops it
   (no header, no database). The section 3 candidate removed the inert APIs
   and kept the working one: replaced by section 8.
2. **References.** Chrome for Testing is not a faithful Chrome (147 facts
   from Chromium 158 at the same version; field-trial configuration likely).
   Use Arch Chromium and Google Chrome stable only. `CookieDeprecationLabel`
   and `Request.targetAddressSpace` are not Qt gaps.
3. **More Qt tells, none removable by a switch** (supports conclusion 2):
   `new URL('foo:bar').origin` is `"foo://"` (Chromium `"null"`);
   `navigator.connection.rtt` 0 / downlink ~10 (Chromium 100 / ~1.5);
   `PublicKeyCredential.getClientCapabilities()` never settles; PDF in a frame
   leaves an `<embed>`; `wakeLock`, MIDI, Picture-in-Picture refused;
   `hrefTranslate`, `allowPaymentRequest` missing.
4. **One identity everywhere is false today**: shared and service workers
   report `languages ['en']` and the page's Intl locale is `en`, while the
   page says `en-US`; GPC is absent in workers. `--lang=<user's language>`
   (set by I.K.E. only at Maximum today) fixes Intl and the workers' language
   (verified).
5. **identity_guard.py** as proposed is unfit: JA4 must drop GREASE signature
   algorithms (fixed in `run.py`); its realm check compares too little; it
   ignores refused realms; and its files are tier B, so no AI may repair it:
   failures would wait in "retrying" forever.
6. Numbers carry noise: I.K.E. refused the self-signed test certificate (18
   TLS facts counted; I.K.E.'s HTTP/2 preface not measured), header facts are
   counted once per request (~6 real signals), Balanced's random plugin names
   add 6 per comparison. "Byte for byte" TLS: only JA4 and sorted JA3 were
   shown equal.
7. The "Brave-like crowd" argument is unsound: no switch set makes I.K.E.
   match a real crowd; decide switches on function, not disguise.
8. `--enable-quic`: Chromium uses QUIC only for direct connections (a proxy
   is not bypassed); interception (ad blocking) is above the transport.
   Unmeasured: the QUIC handshake fingerprint, CPU on old PCs, Local Network
   Access over h3; Alt-Svc in `Network Persistent State` becomes cross-site
   state (connections are not partitioned by default in 140).
9. I.K.E.'s own: autoplay allowed without a gesture at off and Balanced;
   Strict fetches worker scripts with `Sec-Fetch-Dest: script`; no WebRTC
   candidates (by design).

## 8. Conclusions after the review

- Verified not feasible: closing the version gap, removing Qt's own gaps,
  presenting a newer version, by switches or otherwise without changing Qt.
- Worth doing (native, small, measured):
  1. `--disable-features=ConversionMeasurement` (and the blink feature
     `AttributionReporting`): stops a working cross-site ad-measurement API;
     `BrowsingTopics` off as well. Cost: 16 page facts away from Chromium 158,
     none toward anything rarer that is not already distinct.
  2. `--lang=<user's language>` at every level: one language in every realm.
  3. `Accept-Language` with Chrome's q-values at Balanced.
- To measure before deciding: `--enable-quic` (fingerprint, CPU, Local
  Network Access, Alt-Svc state).
- Not recommended: exposing APIs Qt cannot serve (renderer kills, hangs),
  `window.chrome` emulation (simulated API).
- Maintenance: an informational line in `release-ready.yml`'s notice from a
  weekly probe against Arch Chromium of the engine's version and Chrome
  stable, with the removed-API list derived at run time; not an AutoFix job.

## 9. Round 2: Chromium of the engine's version as the only target

Owner's request (2026-11-27). GitHub Actions run 46024103140, Arch
container. Reference: Arch's Chromium 140.0.7339.207 (Arch Linux Archive),
the closest Arch build to Qt WebEngine's 140.0.7339.264; picked by the
workflow from the installed engine's version, so it follows Qt WebEngine
updates by itself. Each browser run twice to measure noise.
`tools/engine-probe/classify.py` sorts every page-level difference:

| I.K.E. | engine (from Qt) | I.K.E.'s own | noise | test artefact |
|---|---|---|---|---|
| off | 332 facts / 73 signals | 23 / 7 | 27 / 5 | 15 / 2 |
| balanced | 332 / 73 | 52 / 11 | 27 / 5 | 15 / 2 |
| strict | 323 / 71 | 63 / 15 | 9 / 2 | 15 / 2 |
| balanced + approved changes | 330 / 71 | 59 / 19 | 27 / 5 | 15 / 2 |
| strict + approved changes | 321 / 69 | 80 / 24 | 9 / 2 | 15 / 2 |

Approved changes (`--lang`, `ConversionMeasurement`/`BrowsingTopics` off,
blink `AttributionReporting`/`TopicsAPI` off, Accept-Language in Chrome's
form): the language is the same in every realm (Intl locale fixed), the
Accept-Language difference is gone, and the profile keeps no attribution
source (bare Qt and I.K.E. today: 3 rows in `Conversions`; Chromium 140:
none, so Qt stores more than Chromium does). They add 8 to 9 API signals
(`attributionSrc`, `browsingTopics`, ...) that Chromium 140 still exposes.

The 71 engine signals are 14 things: Payment Request, WebUSB, Background
Fetch, Document Picture-in-Picture, EyeDropper, WebOTP, speech recognition,
built-in AI (4), `hrefTranslate`/`allowPaymentRequest`, empty
`window.chrome`, 17 permission states, system ICU (3 lists), network
quality (rtt 0), `Pragma`/`Cache-Control` on `no-store` fetches. Behaviour
(extra.html): URL origins of unknown schemes (`"foo://"` vs `"null"`),
WebAuthn (`getClientCapabilities` hangs, no public-key credentials),
Wake Lock and MIDI refused. I.K.E.'s own: GPC, plugins, client-hint
platform version, autoplay without a gesture (off/balanced), Picture-in-
Picture off.

None of the 71 engine signals has an engine switch (round 1 and the
review). Closing them needs either Qt WebEngine changes or page-script
simulation: possible for `window.chrome`, permission states, network
quality and URL origins (values only), impossible honestly for the missing
APIs (they would have to work).

## 10. Security part (owner's request, 2026-11-27)

Measured on Arch Linux (GitHub Actions run 46030855554 and the local chroot):

| Check | Qt WebEngine / I.K.E. | Chromium 140 (Arch) | Chromium 158 | Chrome 158 |
|---|---|---|---|---|
| ELF hardening (PIE, full RELRO, NX, stack protector, fortify) | yes | yes | yes | yes |
| V8 heap sandbox compiled in (`--js-flags=--sandbox-testing` recognised) | yes | yes | yes | yes |
| expired, wrong host, self-signed, untrusted root, Superfish, eDellRoot (badssl.com) | blocked | blocked | blocked | blocked |
| TLS 1.0/1.1, RC4, 3DES, NULL, DH1024 | refused | refused | refused | refused |
| revoked certificate (revoked.badssl.com) | **opens** | blocked (CRLSet) | blocked | blocked |
| key pinning (pinning-test.badssl.com) | opens | opens | opens | blocked |
| HSTS preload list (12 long-preloaded names, sub-resources of an http page) | **not applied** | not applied (Chrome 140 too) | applied (10/12) | - |
| Certificate Transparency (no-sct.badssl.com) | not measurable: the test host's certificate has expired | | | |

Revocation: Qt WebEngine has no component updater, so no CRLSet; no engine
switch turns it on. HSTS preload: Chromium 140 itself does not apply the list
any more (the build is too old for it); I.K.E.'s own automatic HTTPS
(`https_only`, on by default) still sends every top-level `http://` page to
HTTPS, so the gap is limited to sub-resources of plain-HTTP pages.
