# Security of I.K.E.

The state of I.K.E.'s protections against attacks (not its privacy and
anti-fingerprinting work, which is in README.md and CHANGELOG.md), after the
independent security audit of 2026-11-20 and the work of 1.1.18. What is
written here was checked by a test or by a run named below; what could not be
checked says so.

## How I.K.E. is built

- **The web engine** is Qt WebEngine, the system's `qt6-webengine` from Arch
  Linux: Chromium 140 with the security fixes of later Chrome versions
  backported by Qt (Qt 6.12.0: up to Chrome 157). I.K.E. cannot update it;
  `sudo pacman -Syu` does. Help -> About shows both versions and how far
  behind the engine's security fixes are; a notice comes when they are three
  Chrome versions behind (two is normal between two Qt releases).
- **Web pages run in sandboxed processes** (Chromium's renderer sandbox:
  user and PID namespaces and a seccomp filter). **Each site has its own
  process** (Site Isolation, turned on by I.K.E. since 1.1.18; Qt leaves it
  off).
- **The browser itself** (Python, PyQt6) is not sandboxed, as in every
  Chromium browser: it holds the interface, the request check
  (`ike/shields.py`), the password vault, user scripts and the updater. Pages
  reach it only through: a request interceptor (every request), console
  messages carrying a secret (user scripts, reader mode), events with a
  per-profile secret (media controls), the `ike:` scheme (locked to I.K.E.'s
  own pages) and QWebChannel in an isolated world (passwords).
- **Updates** of I.K.E. are signed (Ed25519), checked against a SHA-256,
  never older than the running version, expire after 180 days, arrive in
  stages over 24 hours (with the daily check, everybody within about two
  days), cannot be replayed to undo a stop, and can be stopped by the owner
  (docs/UPDATES.md).

## Status of the audit's findings

| # | Finding | Status in 1.1.18 | Test |
|---|---|---|---|
| F1 | Site Isolation off | **Fixed**: `--site-per-process`; off only with `IKE_ALLOW_UNSAFE_ENGINE=1` | `test_site_isolation.py`, `test_sandbox.py` |
| F2 | Public pages reach the home network with subresources | **Fixed** for literal local addresses (every IPv4/IPv6 form), local names by their form, redirects, and sandboxed or data: frames (I.K.E.'s request check); since 1.1.19 also for public names that resolve to a private address (DNS rebinding), pages and forms a site opens at home, and WebRTC (the engine's own check); **open** for WebSockets by such a name and behind a proxy, see below | `test_home_network.py`, `test_home_network_engine.py` |
| F3 | Media secret and worker seed readable by pages | **Fixed** for the media secret (also through getters on Object.prototype); **mitigated** for the worker seed: no page function receives it, but a site's own worker can still read its own seed from its address (that site's value only, nothing shared across sites) | `test_media_secret.py` |
| F4 | Outdated-engine notice only at five versions | **Fixed**: three versions (two is normal between two Qt releases), counted by the security fixes; reference version shown | `test_engine_age.py` |
| F5 | Releases to everybody at once, manifests never expire | **Fixed**: expiry, staged release, halt that a replay cannot undo, old-style manifests reported; urgent releases on request | `test_update_safety.py` |
| F6 | User-script bridge trusts the token alone | **Fixed** for pages: the sending address must be a frame the page has, matching the script. **Limit**: a page that frames one of the script's sites and has stolen the token can claim that frame's address (the message does not say which frame sent it); with site isolation the token lives only in that site's processes | `test_userscript_bridge.py` |
| F7 | Dangerous inherited engine switches kept silently | **Fixed**: dropped and named, however written (quotes, one dash, any case, a variable set to 0); kept only on request, then shown; `--disable-gpu-sandbox` kept for graphics drivers that need it, and shown | `test_engine_switches.py`, `test_sandbox.py` |
| F8 | Root turns the sandbox off silently | **Fixed**: I.K.E. does not start as root unless asked, and says why, before touching updates or settings | `test_engine_switches.py` |
| F9 | The network service runs in the browser process | **Open** (Qt WebEngine's design; nothing I.K.E. can change) | - |
| - | No vulnerability check of the Rust crates | **Fixed**: RustSec every day and on every pull request | `security.yml` (positive control below) |
| - | Tests never ran with the sandbox | **Fixed**: CI job `sandbox` | `security.yml` |

## Independent review of 1.1.19 (fixed in 1.1.20)

Each fix has a test that failed before it (`tests/test_review_fixes.py`, and
the files named). What is left is said in the last column.

| # | Finding | Fix | Left |
|---|---|---|---|
| H1 | Canvas, audio and text noise could be peeled off (a grey canvas of the same size gave the mask; every 97th audio sample by one factor; `measureText('')` was the offset) | The canvas mask depends on the picture too; audio noise only on buffers the engine rendered, every sample its own factor; text width per text and font, 0 for an empty text | A site's own blob worker can still read its own seed (F3) and with it recompute that site's mask. The noise changes only the lowest bit of red, green and blue (to stay invisible): the other seven bits of each are the real picture |
| H2 | A second start within 20 s rolled a healthy update back for good | The start that tries the update holds a lock for its life; a later start neither counts nor rolls back | Needs the 1.1.20 package (`ike_boot.py` is not self-updated) |
| M1 | A page could make I.K.E. download any `.user.js`, also from the router, with a User-Agent naming I.K.E. | Only the user's own act offers an install; the home network only for a typed address; the browser's User-Agent | - |
| M2 | Enter or Space granted a permission (Allow was the default) | Enter and Esc block; Allow can be clicked only after 0.7 s | - |
| M3 | Encrypted DNS did not cover I.K.E.'s own requests | `ike/doh.py`: the same provider (RFC 8484) for the home-network checks, dark mode's sheets, user scripts, icons, updates, filter lists; Qt requests pinned to its answer with the name in TLS; redirects followed as new requests; the user is told when the engine refuses the setting | Search suggestions, weather and the extension store (fixed hosts) still use the system resolver; an icon's redirect is not followed with encrypted DNS on |
| M4 | Dark mode's sheet fetch skipped the lists and allowed http on https pages | Mixed content refused, the lists asked, the browser's User-Agent | - |
| M5 | Spoofed values detectable | Getters keep the engine's receiver check; Strict: WebGPU present with no adapter, a battery on mains, the header's language = navigator.languages; Maximum: Intl, dates and numbers in en-US, in workers too | The time zone and GPC (not sent by Chrome) are not covered; an independent fingerprinting audit is planned |
| L1 | Manifest not bound to its channel | Each manifest names its channel | Manifests without the field are accepted (older releases) |
| L2 | Halt did not withdraw a staged copy | Withdrawn and listed as bad | - |
| L3 | Own requests named I.K.E.; every engine asked at first start | The pages' User-Agent everywhere; only the engine in use | - |
| L4 | User scripts shared one world; answers delivered after the tab changed site | A world per script; an update into the page's world asks; late answers dropped | - |
| L5 | Embedded-video click relay: the page could put its own element on the point | Hardened (owner's decision): only when the page holds a frame of a video site, the point must still be on that frame when the click is made, at most once every 3 s; the skip on the video site itself unchanged | A page that moves its element in the few milliseconds between the check and the click (not shown possible) |
| L6 | The logins' channel shared with the other helpers of its world | The channel's receiver is locked after the helper makes it, and so are `qt` and `qt.webChannelTransport` (not writable, not configurable), so no transport of another script's can be put in front of it; the others get only `fetchCss`, `cssFetched`, `adClick`, `adClickEmbedded` | Code in that world can still send blind calls on the transport (no answers): it cannot read a login. Separate worlds would move the video-ad helpers (owner's decision) |
| L7 | Favicons decoded by every image plugin outside the sandbox | Only PNG and ICO, by their first bytes | - |
| L8 | Store extensions not signature-checked | CRX3 only, signed by the key of the id asked for (RSA or ECDSA) | The store's own publisher signature is not checked |
| L9 | Generated password left on the clipboard | Marked for clipboard managers and cleared after 45 s | - |
| L10 | `site_of` approximated the Public Suffix List | The system's list (`publicsuffix-list`); a longer fallback | The page script's noise seed still uses the short list |
| L11 | Unknown arguments went to Qt | Dropped, named on stderr | - |

A second pass of the same reviewer over these fixes found more of the same
kind; fixed too:

| # | Finding | Fix | Left |
|---|---|---|---|
| N4 | The fingerprinting protection called built-ins a page can replace while it runs (`WeakSet`/`WeakMap` methods, `Promise.prototype.then`, `.apply`/`.call`, `Math.imul`, `Uint32Array`, the length of typed arrays, `ImageData`'s `data`, a canvas's own size): each replacement gave the real canvas or audio values, the masked font names, or the full browser version | Everything it uses is taken before the page runs; its collections keep their methods as own, frozen properties; the noise uses a multiply of its own; what a `ScriptProcessorNode` hands the page is noised too | The time zone and other values outside the protection's list (see the fingerprinting audit) |
| N5 | Maximum: an empty language list, or a language the engine lacks, fell back to the system's language | Such a list means the language shown (en-US), in pages and workers; the list is read once, as the engine reads it | Texts the engine writes itself (a form's validation message) stay in the system's language: the engine's language is one for every site, and Maximum is chosen per site |

## Known limits (not solved)

- **The home network, since 1.1.19.** Two checks work together. I.K.E.'s
  own request check stops literal local addresses, local names and
  redirects to them, from every kind of request, and cannot resolve names
  (it would stall every page). The engine's own check (Local Network Access,
  Chromium 140 in Qt 6.12, off in Qt and turned on by I.K.E. with
  `LocalNetworkAccessChecks:LocalNetworkAccessChecksWarn/false`,
  `LocalNetworkAccessForNavigations` and `LocalNetworkAccessChecksWebRTC`)
  looks at the real address when it connects, so a public name that points
  home (DNS rebinding) is stopped too. Tested on the real engine
  (`test_home_network_engine.py`), by address and by such a name, from a
  public page: pictures, scripts, styles, frames, fetch, XHR, workers,
  beacons, a redirect, WebRTC (STUN), a link or script that opens a page at
  home, a form sent there: all stopped; the address the user types opens.
  Without the engine's check, the same test fails.
  - **No per-site exceptions.** Qt answers the engine's permission with
    "denied" (no per-site prompt), and the engine's only exception
    (`--ip-address-space-overrides`) is given at start for every site at
    once: tried on 2026-11-20, an exception for one site let another public
    site reach the same device through its own name. So a part of a page
    stopped this way is said in the window with no button, and the switch
    is dropped when inherited. "Allow for this site" remains for a page at
    home that a public page tried to open: the user's click opens it.
  - **Still open:** a WebSocket to a public name that points home (Chromium
    140 only warns; a WebSocket to a literal local address is stopped by
    I.K.E.); WebTransport (not tested); with a proxy the engine sees only
    the proxy's address, so only I.K.E.'s check applies; service workers
    were not tested (they need https). IPv6 is tested where the computer has
    it (`::1`; not in this container). A public site that must talk to a
    device at home (some media servers, printer set-up pages) cannot.
    Protect the router with a password and keep its firmware current.
- **Workers started from a file of the site** see the real values of the
  computer (anti-fingerprinting, not an exploit protection); a partial way
  around it waits for the owner on `experiment/file-workers`.
- **The engine's patch lag** depends on Qt and Arch: Chrome fixes arrive in
  `qt6-webengine` some weeks later.
- **Certificate Transparency, HSTS preload, V8 hardening of Arch's build and
  the GPU process on real hardware** were not verified (no means here).
- `IKE_ALLOW_UNSAFE_ENGINE=1` exists for tests and special cases: with it the
  user takes protections away on purpose, and the window says so.

## The sandbox on Arch Linux and CachyOS

Chromium's sandbox on Linux needs unprivileged user namespaces, which Arch's
and CachyOS's kernels allow by default (`linux`, `linux-zen`,
`linux-cachyos`). With `linux-hardened`, or with
`kernel.unprivileged_userns_clone=0`, the engine cannot use its sandbox, and
Help -> About cannot tell (it reports the switches that turn the sandbox off,
not what the kernel allows). I.K.E. never adds `--no-sandbox` by itself
(since 1.1.18 not even as root). To check: Help -> About must say "Engine
sandbox: on" and "Site isolation: every site in its own process", and on a
normal kernel `grep Seccomp /proc/$(pgrep -f 'QtWebEngineProcess.*renderer' |
head -1)/status` shows `Seccomp: 2`.

## What was run, and where

- **This container (Ubuntu, PyPI Qt 6.12.0 / Chromium 140, as root):** every
  new test, each run on the previous code first to see it fail (F1, F2, F3,
  F5, F6) and then on the fix; `test_sandbox.py` as a normal user through
  `unshare` with the sandbox on (3 runs out of 3).
- **GitHub Actions:** the whole suite (`tests.yml`), the Arch container with
  Arch's own Qt (`arch.yml`), the sandbox job and the RustSec check
  (`security.yml`): results in the pull request.
- **RustSec positive control:** a crate pinned at a vulnerable version
  (smallvec 1.6.0) made the check fail with RUSTSEC-2021-0003; the engine's
  own crates: no advisory (2026-11-20).
- **Not run:** real hardware GPUs, a real Plasma session, real websites
  (project rule), a real DNS-rebinding service.
