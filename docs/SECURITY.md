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
| M5 | Spoofed values detectable | Getters keep the engine's receiver check; Strict: WebGPU present with no adapter, a battery on mains, the header's language = navigator.languages; Maximum: Intl, dates and numbers in en-US, in workers too | GPC (not sent by Chrome) is not covered; the time zone only with the "Protected time zone" option (1.1.24, opt-in: UTC for the whole engine) |
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
| FP-H-A | (fingerprinting audit) Wrappers still looked up `call`/`apply`, `filter`, `toLowerCase`, `slice`, `RegExp.prototype.exec` when called: the hidden WebGL extension, an inline worker without its prelude | No method of the page's is used; the client hints answer in the engine's key order | - |
| FP-H-B | The site's seed readable from an inline worker's own address (`fetch(self.location.href)`, `ErrorEvent.filename`, a `data:` address) | The prelude revokes its address first; location and errors name the page's address and line; a `data:` worker gets a seed of its own | A worker's `Error().stack` still names the revoked address |
| FP-H-D | Fonts at Strict: `local()`, the masks as an oracle (U+E000, `fonts.load()`), another realm's `clear()`, workers, names outside the list | Masks over U+D800 (no text reaches them), `local()` of a masked name fails, any realm's `clear()` refills, `load()` filtered, masks in inline workers, every installed family masked | CSS `@font-face { src: local() }` and workers loaded from an address still find installed fonts: only a font allowlist for the whole engine closes them (to decide) |
| FP-H-E, M-1, M-8 | Pixels without noise through WebGL2 pack buffers, `readPixels` into other arrays and in workers, `VideoFrame.copyTo`; analyser byte data; float16 reads corrupted | Each route noised (bytes only; float results stay exact); float16 values get their own noise | WebGPU read-back not checked (no adapter in the tests) |
| N3 | Noise removable by a majority vote over reads with one corner changed, and audio factors read from a buffer of known samples | The noise depends on each pixel's colour and its neighbour's, each sample's value and the one before it: neither the place nor the whole picture | Areas of one plain colour are left as they are (they say nothing about the computer); noise of any kind cannot resist a script written against it (audit, I-1) |
| FP-M-5 | Error stacks named the protection (`userscript:ike-fp`) | Neutral script names; the protection's lines taken out of stacks | A page that sets `Error.prepareStackTrace` still sees the frames |
| FP-M-6 | The plugin list recognisable (the prototype's `item()`/`length`/`name` threw; own properties on the invented entries) | The engine's own getters and methods answer for the list and the invented entries | - |
| FP-V (second pass) | 13 more ways around the fixes: a getter on `Promise`/`Array.prototype.constructor` (species), setters on `Array.prototype`'s index names, module workers (imports run before the prelude), workers inside workers from a page-made address, WebGL numbers given as text or objects, float16 reads rounded to 8 bits, `local()` written with escapes, comments or objects, quiet audio sharing one factor, `SharedArrayBuffer`, the plugin list's own keys, `split()` in the stack cleaning, Trusted Types and `Worker()` with no argument | The engine's promises get an own constructor; loops instead of `filter()`; elements written with `defineProperty`; internal tables without a prototype; module workers get a seed of their own; nested blob addresses read and given the prelude; WebGL numbers read once and passed on as read; float16 noise at the 8-bit scale; every `local()` taken out of FontFace sources; audio factors from each sample's own bits; `SharedArrayBuffer` noised; `ownKeys` and descriptors of the plugin list; a TrustedScriptURL kept, or the prelude's address given a policy of its own | See "Known limits of the noise" below |
| FP-M-4 | The storage quota gave the disk size | `StaticStorageQuota`: 10 GiB for everyone | - |
| N5 | Maximum: an empty language list, or a language the engine lacks, fell back to the system's language | Such a list means the language shown (en-US), in pages and workers; the list is read once, as the engine reads it | At the global level Maximum the engine itself speaks en-US too (form messages, Date's zone names, every kind of worker; owner's decision, audit M-7). A site set to Maximum by itself keeps the engine's texts in the system's language: the engine has one language for all sites |

## Known limits of the noise (proven by the independent verification)

A protection written into the page's own world can make the cheap, exact
routes useless; it cannot stop a script written against it:

- **The lowest bit made visible.** The noise changes only the lowest bit of
  a colour, to stay invisible. A page can composite a noisy read with itself
  (`difference`, then `lighter` several times) and see which bits changed:
  the real picture in two reads. Noise that survived this would be visible.
- **Plain colours** are left as they are (they say nothing about the
  computer): a one-colour canvas usually reads the same in every session.
- **Float WebGL reads** (`FLOAT`) and **AudioWorklet** taps are not noised:
  floats are left exact for programs that compute with them, and a worklet
  runs where the page's world cannot reach.
- **Fonts**: at Balanced, and at a site set to Strict or Maximum by itself,
  a style sheet's `@font-face { src: local() }` and workers loaded from an
  address still find installed fonts. At the global levels Strict and
  Maximum the engine itself sees only the common families since 1.1.21 (see
  below).
- **Screen size in style sheets**: at Strict `matchMedia` answers the shown
  screen size since 1.1.21, but a style sheet's own `@media (device-width: ...)`
  is evaluated by the engine with the real size, and a page can read its
  effect (a computed style).
- **A site set to Maximum by itself** (not the global level) keeps the
  engine's own texts and the time zone's name in the system's language.

## Fingerprinting: the audit's remaining points (1.1.21)

Each with a test in `tests/test_review_fixes.py` that failed before the fix.

| Point | Was | Now |
|---|---|---|
| Fonts (audit "known limits") | A style sheet's `src: local()` and workers loaded from an address found any installed font | At the global levels Strict and Maximum fontconfig gets a file of I.K.E.'s (`ike/fontallow.py`): the system's configuration plus a rule that keeps only DejaVu, Liberation, Noto, Cantarell, Source Han and WenQuanYi. Read at start (a change of level applies after a restart); I.K.E.'s own interface uses the same fonts; programs I.K.E. starts get the user's configuration back; nothing changes when none of these families is installed |
| Cores (Cover Your Tracks) | 2, 4, 6, 8 (12, 16 at Balanced) per site; "2" was rare | 4 or 8, never more than the computer has; Strict and above the higher one |
| M-2 | `matchMedia('(min-device-width: Npx)')` gave the real screen size behind Strict's usual one | `device-width`, `device-height`, `device-aspect-ratio` (both syntaxes) answered for the shown size; the query's text kept. Style sheets: see "Known limits of the noise" |
| L-2 | The noise's site came from a short list of hosting domains: unrelated sites under another one shared their noise | The system's Public Suffix List, as for the rest of I.K.E., given to the page as sorted 24-bit hashes (about 35 KB); a chance match makes a site one label longer, never shared |
| L-3 | `window.name` written on one site was still there on the next site of the tab | Emptied in a top-level document reached from another site (or from nowhere) on a new navigation, unless a script opened the tab; kept within a site and on a reload |
| GPU name at Strict | Hidden ("not available" in Cover Your Tracks, about 7.5 bits) | Kept hidden: every Linux renderer name carries the driver's details and is rarer than "not available"; a fixed name of I.K.E.'s would mark its users (still so in 1.1.25: no name, with one shared set of extensions and limits, below) |

## Fingerprinting: the sites' own checks (1.1.25)

A run of the real browser against browserleaks.com and CreepJS (the owner's
decisions of 2026-11-24), then an independent adversarial review of the
result (three rounds). Each point with a test in `tests/test_fingerprint_125.py`
or `tests/test_fingerprint_125_workers.py` (the review's own probes, in
`tests/data/fingerprint-125/`) that failed before the fix.

| Point | Was | Now |
|---|---|---|
| Client hints, every level | Service and shared workers get the engine's own client hints, never the profile's: "Chromium" only, the engine's full version and the real kernel (6.18.44) where the page said "Google Chrome", 140.0.0.0 and 6.0.0 | The profile keeps the engine's own brand list, versions and order (nothing is set over them, at Strict either: Qt sorts a list it is given, and frames, headers and shared workers came in two orders); the engine leaves the kernel out (`ReduceUserAgentDataLinuxPlatformVersion`; the platform version is empty everywhere). At Strict and Maximum the major version (140.0.0.0) is given by the request check and by the scripts of pages and workers |
| Service and shared workers from a file, Strict and Maximum | Started, with the engine's own values and no protection | Not started: their script is refused in the request check, in every frame and worker (`register()` fails as when the script cannot be fetched); one registered before at a lower level is unregistered |
| Dedicated workers from a file, Strict and Maximum (also a site set to Strict by itself) | No protection at all: the real card, limits and extensions, canvas without noise, the installed fonts, the real network, the full version, every language | Started from a blob address holding the protection, which then runs the site's script with its real address: a classic script by the engine's own `importScripts` (its fetch, its type check, its "use strict"; the page does not wait for it), a module by `import()`, the messages the page posts before the module has run held and delivered to it in order. Inside, the location, `importScripts`, `fetch`, `Request`, `XMLHttpRequest`, `WebSocket`, `EventSource` and nested workers read relative addresses against the file's; a syntax error, an exception or a missing script reach the page as before, with the site's address; nested workers and workers in frames of other sites the same; a sandboxed frame (an opaque origin) gets none, as with the engine. Where a content security policy refuses blob workers, the worker the page asked for is refused by the request check, as when its script cannot be fetched, and the page sees no policy report of the protection's: it never runs without the protection. Balanced: unchanged |
| Plugins, Strict | Chrome's five PDF viewers plus two invented ones with no type (CreepJS: "missing mimetype") | Chrome's own five, with their two types, the same for everyone (Balanced keeps the invented ones) |
| WebGL, Strict | `getParameter` of the debug enums gave null with no error (Chrome raises INVALID_ENUM), a random part of the extensions hidden with the real limits (CreepJS: "suspicious capabilities") | No card name (the owner's choice, as before): `WEBGL_debug_renderer_info` is not offered, and the debug enums give the engine's own INVALID_ENUM and null. A fixed list of extensions every common desktop card has, never one the real context lacks, never enabled otherwise (`WEBGL_debug_shaders` no longer offered); a fixed floor of limits (table below), never above the real one; plain colours read back exactly (`readPixels`). The same in pages, frames, workers and WebGL 2; WebGPU gives no adapter |
| Canvas, Strict | The noise changed pixels of plain colours: CreepJS reads back single pixels it drew ("pixel data modified"); the page's own pixels (`putImageData`) came back changed | A canvas whose pixels all came from solid, opaque, whole-pixel rectangles, from `putImageData` or from another such canvas copied unscaled at a whole pixel is read back exactly; a `putImageData` that covers the whole canvas makes it exact again. Elsewhere only opaque pixels at an edge get noise (a pixel with the colour of its four neighbours never), and a pixel's noise depends on the canvas, not on the part read. No size is exempt (review point LOW-11): small canvases with the noise left out could be put together into any picture, a piece at a time |
| Text widths, Strict | The noise depended on the text and the font's name: two fonts that are not installed measured differently (Chrome: the same) | The noise depends on the real width alone, in pages and workers; `measureText` is no longer wrapped |
| Fonts found by measuring text, Strict (review round 3) | A frame of the site's own found every installed font (its first page keeps the window of its empty document, which the page around had protected, and the fonts of the new document were not masked); once the font check had run (some seconds after a start) its list masked "Monospace", the engine's own name for monospace, and a worker's monospace became another font: workers no longer found Times New Roman where the page did | The new document of such a frame is masked by the protection that protected its window; "Monospace" is never masked (like Arial or Times New Roman, every system answers to it); the page, its frames and every kind of worker find the same fonts (`test_every_context_finds_the_same_fonts`) |
| Recognising a protected frame, every level (review round 3; since 1.1.18) | The protection asked a realm whether it was protected by calling its toString with a secret value: a page that had replaced a frame's toString, then loaded the frame, caught the secret ("ike:" and 32 letters), and with it told I.K.E. apart in any new frame (its toString answered where Chrome throws) | No secret at all: a frame's own protection is seen by reading its toString with the protection's own (never calling the frame's), and a frame's page that keeps the window the page around had protected is seen by where its toString comes from. toString answers every value as Chrome does (`test_no_value_handed_to_a_page_toString`). A frame whose toString the page set to another engine function before the frame's own script started is still seen as protected (several replaced functions are looked at), and a replaced function always reads as the engine's, never as the protection's source (`test_a_frame_is_protected_once`) |
| Languages, Strict | `navigator.languages` ["it-IT"], the header "it-IT,it;q=0.9", Intl "it" | ["it-IT", "it"], as the header; at the global level Strict the engine is given the same. Intl keeps the engine's "it": Chrome's default locale for Intl is its own interface language, not the first accepted language (the same engine code here). Balanced: inline workers carry the page's list too |
| Network, Strict | JavaScript rtt 0 and a downlink of about 9.5, the client hints 100 and about 1.7 | 4g, 50 ms, 10 Mbit/s in pages, workers and the hints a site asked for. Balanced leaves the engine's values (an iframe's navigation can carry other ones in its headers) |

**The WebGL floor at Strict** (`fingerprint.js`, `GLX.lim`). Every value is
one that every common desktop card (Intel on Mesa from Ivy Bridge on, AMD on
Mesa, NVIDIA's own driver, the llvmpipe software renderer) meets, so all of
them report the same; where a number comes from: "ES3" is the minimum
OpenGL ES 3.0 asks of every implementation, "llvmpipe" was measured on the
test computer, "Mesa"/"NVIDIA" are from public reports and memory (not
measured here).

| Limit | Floor | Source |
|---|---|---|
| MAX_TEXTURE_SIZE, MAX_CUBE_MAP_TEXTURE_SIZE, MAX_RENDERBUFFER_SIZE, MAX_VIEWPORT_DIMS | 16384 | llvmpipe; Intel Gen7+, AMD, NVIDIA from memory |
| MAX_VERTEX_ATTRIBS, MAX_VERTEX/TEXTURE_IMAGE_UNITS, SUBPIXEL_BITS | 16, 16, 16, 4 | ES3 |
| MAX_COMBINED_TEXTURE_IMAGE_UNITS | 32 | ES3 |
| MAX_VERTEX_UNIFORM_VECTORS, MAX_FRAGMENT_UNIFORM_VECTORS | 1024 | llvmpipe (Mesa's common value, from memory) |
| MAX_VERTEX/FRAGMENT_UNIFORM_COMPONENTS | 4096 | the vectors x 4 |
| MAX_VARYING_VECTORS, MAX_VARYING_COMPONENTS, MAX_VERTEX_OUTPUT_COMPONENTS, MAX_FRAGMENT_INPUT_COMPONENTS | 15, 60, 64, 60 | ES3 |
| ALIASED_LINE_WIDTH_RANGE, ALIASED_POINT_SIZE_RANGE | [1, 1], [1, 255] | ES3; Mesa Intel 255.875, llvmpipe 256 |
| MAX_TEXTURE_MAX_ANISOTROPY_EXT, MAX_DRAW_BUFFERS, MAX_COLOR_ATTACHMENTS | 16, 8, 8 | llvmpipe; desktop cards from memory |
| MAX_3D_TEXTURE_SIZE, MAX_ARRAY_TEXTURE_LAYERS | 2048 | llvmpipe; desktop cards from memory |
| MAX_SAMPLES, MAX_UNIFORM_BUFFER_BINDINGS, MAX_UNIFORM_BLOCK_SIZE, MAX_*_UNIFORM_BLOCKS, MAX_COMBINED_UNIFORM_BLOCKS | 4, 24, 16384, 12, 24 | ES3 |
| MAX_COMBINED_VERTEX/FRAGMENT_UNIFORM_COMPONENTS | 53248 | ES3's formula from the values above |
| Transform feedback (interleaved, separate attribs, separate components) | 64, 4, 4 | ES3 |
| MIN/MAX_PROGRAM_TEXEL_OFFSET, MAX_TEXTURE_LOD_BIAS, MAX_ELEMENT_INDEX | -8, 7, 2, 2^24-1 | ES3 |
| UNIFORM_BUFFER_OFFSET_ALIGNMENT | 256 at least | the largest ES3 allows (a larger alignment is always safe) |
| MAX_ELEMENTS_VERTICES, MAX_ELEMENTS_INDICES | 3000 | llvmpipe (Mesa's default) |

The extensions offered at Strict, those the real context has among:
ANGLE_instanced_arrays, EXT_blend_minmax, EXT_color_buffer_float,
EXT_color_buffer_half_float, EXT_frag_depth, EXT_sRGB,
EXT_texture_compression_rgtc, EXT_texture_filter_anisotropic,
KHR_parallel_shader_compile, OES_element_index_uint, OES_fbo_render_mipmap,
OES_standard_derivatives, OES_texture_float, OES_texture_float_linear,
OES_texture_half_float, OES_texture_half_float_linear,
OES_vertex_array_object, WEBGL_color_buffer_float,
WEBGL_compressed_texture_s3tc, WEBGL_depth_texture, WEBGL_draw_buffers,
WEBGL_lose_context, WEBGL_multi_draw (every one of them on llvmpipe; on the
others from memory; in doubt an extension was left out). What a page sees is
the names that are both in this list and in the real context's: on the
test computer WebGL 1 shows 22 of the 23 (EXT_color_buffer_float is WebGL
2's alone) and WebGL 2 shows 9. A card that lacks one of them shows one
fewer: the list is fixed only as far as the real context allows (an
extension it does not have is never offered).

**Known limits, not solved.**
- The real limits can still be found by trying them: `activeTexture` up to
  the real number of units, a texture or viewport larger than the floor,
  wide lines. A protection written in JavaScript can only lower what is
  reported, not what the card does.
- CreepJS still files the test computer's software WebGL as "suspicious
  capabilities" (also with the shield off: it compares the limits with a
  list of real cards, which a floor cannot match exactly), and the 2 x 2
  picture of curves it knows sometimes as "suspicious pixel data".
- A pixel-aligned `rect()` + `fill()` (a path) gets the noise at its edges,
  where Chrome draws it exactly: paths are not followed one by one.
- A `putImageData` over part of a canvas that has text gets the noise at
  its edges like the rest of the canvas.
- Every wrapped function shows a line of the protection's own
  (`userscript:content`) in a stack read from inside an argument's
  `valueOf` or `toString` (fewer since 1.1.25: transforms and `measureText`
  are no longer wrapped, `fillRect` and `getImageData` no longer convert the
  page's arguments themselves).
- A site that probes behaviour rather than values (it asks for a texture
  larger than the reported limit, times a draw, compares a canvas with one
  drawn again) can still tell the protection is there: the values are
  lowered, not the card.
- Stacks: a stack read inside `fillRect`, `getImageData`, WebGL's
  `getParameter` and `getExtension` and the `Worker` constructor (from an
  argument's `valueOf`, `toString` or a getter) still has one line of the
  protection's.
- Workers from a file at Strict (the review's third round):
  - their script is fetched by the worker (`importScripts` or `import()`),
    not by the page as a worker's script: the server sees a script's request
    (Sec-Fetch-Dest `script` and mode `no-cors` or `cors`, where the engine
    sends `worker` and `same-origin`; no Referer) and the page's
    own timeline does not list it (the engine lists it there);
  - a module worker's imported files are in the worker's own timeline (the
    engine leaves them out); its own script is not;
  - a message the page posts to a module worker before the worker's module
    has run is held and handed to it afterwards, in order, as a new event:
    `isTrusted` false (the engine's is true), and a stack read in its
    handler ends with one line of the blob address. A module that waits at
    its top level (`await`) gets the messages that came meanwhile once it
    has run, where the engine hands them to the handlers already set, or
    drops them when none is set;
  - the bottom line of a stack read in the script's first run is the blob
    address (one line, under the site's own lines), and a relative
    `importScripts` puts one line of the protection's between the imported
    file and the script that imported it;
  - a file served as `text/plain`: the engine runs it as a worker; at Strict
    it is refused (`importScripts` asks for a script's type), as when the
    file is missing;
  - a page whose content security policy refuses blob workers (`worker-src
    'self'`) gets no worker at all: the worker is refused, never started
    without the protection (the owner's choice). The page's own
    `securitypolicyviolation` event naming the protection is stopped, but
    the engine's report is not: a policy's `report-uri` or `report-to` and
    a `ReportingObserver` still receive it, with the blocked address "blob"
    and the source "userscript" (the protection's own line).
- At Balanced, a shared or service worker from a file runs without the
  protection (as before 1.1.25) and shows the engine's own languages (["it"]
  on the test computer) where the page shows its full list ("it-IT", "it",
  "en-US", "en"). At Strict and Maximum they are refused.
- No canvas size is left exact (review point LOW-11, declined): a 2 x 2
  canvas gets the same noise as any other.
- A module worker has a noise seed of its own (verification V-3: a module's
  imports run before the protection and could read the site's seed): its
  text widths and canvas noise differ from the page's by their noise (a
  few parts in a million for a width); the fonts it finds are the same.

## Google's sites and Cover Your Tracks (1.1.27)

The owner's decisions of 2026-11-27, each with its tests
(`tests/test_google_firefox.py`, `tests/test_canvas_exports.py`).

| Point | Was | Now |
|---|---|---|
| Google's sign-in, "this browser may not be secure" | Only accounts.google.com got a Firefox identity, a fixed Firefox 140 (June 2025); the engine's client hints in the same request said `"Chromium";v="140"`; the getters of the JavaScript identity showed their source; Google's sensitive services (AI Studio, the cloud console, the account, payments) got "Compatibility" and then no protection at all (1.1.14) | Every request and frame of Google's sites, a Google sign-in embedded anywhere and what it loads present the Firefox of the calendar (`osinfo.firefox_major`: never ahead of a real release, at most about a version behind), the engine's three client hints sent empty, Firefox's navigator in every frame with getters that read as the engine's, no `userAgentData`, no `window.chrome`; the user's level everywhere on Google's sites |
| Google's own domains on Google's pages | Left alone on the sensitive services; filtered elsewhere | At Balanced, Google's own domains (google.com, gstatic.com, googleapis.com, googleusercontent.com, recaptcha.net) go the "same site" free way on Google's pages, and their third-party cookies are kept there, as Firefox's entity list counts them; its ad and analytics domains are filtered as before; Strict and Maximum filter everything |
| Cover Your Tracks: "unique" fingerprint | The noise of a canvas was the same at every read of a site in a session, so two exports of the same drawing were equal | Each export (`toDataURL`, `toBlob`, `convertToBlob`, WebGL canvases included) gets a varying part on top of the site's noise: the lowest bit of one in 32 opaque pixels at an edge of the drawing, chosen from the site's secret key and the number of exports so far. The majority of many exports is the picture with the site's noise (tested), so averaging gives nothing more than one read did; `getImageData` is unchanged |

**Limits.** The identity is Firefox's texts on Chromium's engine: a site
that tests the engine's features can still tell it is not Firefox (the
Firefox identity of accounts.google.com up to 1.1.26 was accepted most of the
time; the real Google could not be tried from the tests). Workers keep the
engine's own `navigator.userAgent` (not covered). The client hints go
out empty rather than missing (Qt has no way to take a header away). With
the shield off on a Google site, or "Make sign-in work" off, Google sees the
engine as it is. The varying part of an export is in the page's world:
like the rest of the noise it cannot resist a script written against it
(see "Known limits of the noise").

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
  around it waits for the owner on `experiment/file-workers`. The protected
  time zone (1.1.24) is the exception: it is the engine's own, so those
  workers see UTC too.

## The privacy package of 1.1.24

- **Protected time zone** (`ike/timezone.py`, opt-in, the shield): the engine
  starts with `TZ=UTC`, I.K.E. takes its own zone back right after (its
  menus, history and the new tab clock stay local) and keeps `TZ` set, so the
  engine never follows the system's time-zone files for its pages. Pages,
  frames, inline workers and workers from a file agree on UTC
  (`getTimezoneOffset`, `Intl...resolvedOptions().timeZone`, `Date` strings);
  no script rewrites the date functions, so the Intl fast path of Maximum and
  every page's speed are untouched. A change applies after a restart.
- **Bounce tracking** (`ike/bounce.py`, on by default): a main-frame redirect
  (the server's, or the page's own without a click) away from another
  registrable domain marks that site; half a minute later its cookies go
  and its local storage, databases, caches and service workers are cleared
  from a hidden page at its address that loads nothing. Never for sites the
  user used (a click, a key, an address typed) in the last 45 days or that
  were in the history when the protection first ran, open in a tab,
  bookmarked, allowed in the shield (protection off, cookies allowed), or
  sign-in, payment and the other sensitive services. One check per
  main-frame navigation, nothing per request; private windows are not
  touched. The sites used are kept in the settings (`bounce_used`, emptied
  with the history).
- **Quiet permission prompts** (`ike/quietperms.py`, on by default):
  notifications, location, camera and microphone ask through a sign in the
  address bar instead of a window. A request for notifications without a
  click or key on the page in the 5 seconds before is refused at once and
  not stored (the site may ask again after a click). The engine keeps the
  user's answers per site, as before.
- **Password breach check** (`ike/breach.py`, opt-in): k-anonymity with Have
  I Been Pwned's range API (5 hexadecimal characters of the SHA-1 sent,
  `Add-Padding: true`, the comparison made locally, each password once per
  session, nothing written).
- **"Update the system"** (`ike/advisory.py`): an advisory signed into the
  update manifest by the release tool, read only from a verified manifest
  during the daily check (docs/UPDATES.md).
- **Battery saver** (`ike/battery.py`, opt-in): UPower's `OnBattery` over the
  system bus (QtDBus), asked once and then followed through its signal; no
  connection at all while the saver is off.
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
