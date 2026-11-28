# Worker guard: feasibility study (2026-11-28) — not adopted

Two read-only research phases on one question (the owner's brief "Studio di
fattibilità per l'evoluzione strutturale dell'antifingerprinting" and its second
phase): can I.K.E. give the sites' own workers (dedicated workers from a file,
service workers, shared workers) the fingerprinting protection from outside the
official Qt WebEngine, without blocking or rewriting them? Each phase ended
with an independent adversarial review (Fable 5.2).

**Owner's decision (2026-11-28): the worker guard is not implemented.** No
privileged DevTools channel or equivalent component; official Qt WebEngine
only; security comes before anti-fingerprinting. What the studies learnt that
does not need such a channel is reused (see "What is reused").

Snapshot studied: 1.1.32 (`8252a5d`, merged into `main` as `b01b0e5`, tag
`v1.1.32`). Environments: PyQt6-WebEngine 6.140.1 from PyPI (Chromium
140.0.7339.264) in a container, then an Arch Linux chroot with the official
`qt6-webengine 6.140.0-2`, `python-pyqt6-webengine 6.140.1-1`, a user without
root and the engine's sandbox on (renderers: Seccomp 2, NoNewPrivs), running
the real I.K.E. through `tests/conftest.py`'s harness. The prototype and the
probes were study material and are not kept in the repository.

## 1. Why the workers are hard

- `QWebEngineScript` runs in frames only, never in workers
  (`user_resource_controller`); Qt has no API to change response bodies
  (QTBUG-61071 open), so a worker's script cannot be prefixed by I.K.E.
- Service and shared workers have no document: they always get the engine's
  own values. Chromium's page-level DevTools auto-attach covers dedicated
  workers, service workers (by scope) and OOPIFs, not shared workers (only the
  browser-level attacher has them, which Qt never grants a page session:
  `Target.attachToBrowserTarget` -> "Not allowed").
- Qt does not implement `--remote-debugging-pipe` (it never reads fd 3); the
  remote debugging port listens on localhost for every local process and Qt
  adds `--remote-allow-origins=*`: rejected outright. Qt's extension support
  (6.10+) has no `chrome.debugger` or `chrome.scripting`.
- A Rust or C++ module would have exactly JavaScript's access (no supported
  native hook into Blink's workers): rejected.

## 2. The channel that works (and why it is not used)

`QWebEnginePage::setDevToolsPage` (public since Qt 5.11) on a hidden page,
plus a main-world script there calling `DevToolsHost.sendMessageToEmbedder`
with `dispatchProtocolMessage`, gives a private, in-process Chrome DevTools
Protocol session (no socket: verified with lsof). One hidden page can attach to
every tab (`Target.attachToTarget` with `QWebEnginePage::devToolsId()`).

Verified (Arch, sandbox on, the real `workerPatch` of fingerprint.js):

- The safe injection point is `Debugger.setInstrumentationBreakpoint
  {beforeScriptExecution}`. Evaluating at pause-on-start crashes the page's
  renderer (`self.location` read before the worker's response) and misses
  about 80 `[SecureContext]` interfaces (WebGPU, Cache...) installed later.
- With it, every context of `tests/fp_audit.py`'s probe read the page's values
  at Balanced, Kontrol and Maximum, service and shared workers from a file
  included (1.1.32: the engine's values). Seeds computed in Python matched
  fingerprint.js's; 160 fast cross-site navigations, 0 wrong seeds.
- Popups 20/20 protected; shared workers only by a race (with cached scripts 1
  of 3 instances in time; the others detected, not patched); AudioWorklet and
  PaintWorklet are pausable targets too.
- Freezing: Qt refuses Frozen/Discarded while any DevTools session is attached
  ("DevTools open"); a CDP freeze, detach, Qt freeze and re-attach before
  thaw keeps tab freezing with no unprotected window.
- Cost: about 24 MB fixed (two hidden renderers), about 0 per attached tab,
  about 1.8 MB per protected worker (the prelude itself), idle CPU unchanged;
  under bursts of 300 workers the start time doubles. Same behaviour on Qt
  WebEngine 6.6, 6.8, 6.10, 6.11 and 6.12/6.140.

Why it was rejected (both reviews, reproduced):

- **No privilege reduction is possible.** The hidden page holds
  `DevToolsHost` directly; an allowlist in its code or in Python binds only
  honest callers. From one guard session: `document.cookie` and httpOnly
  cookies of normal and private tabs, `Security.setIgnoreCertificateErrors`
  (a self-signed page then loads without `QWebEnginePage::certificateError`),
  `Page.navigate file:///etc/passwd` plus `Runtime.evaluate` (file read),
  `Page.setDownloadBehavior` (a file written to a chosen folder, bypassing
  `downloadRequested`). A compromise of that one renderer equals a compromise
  of the user's account, with no sandbox escape needed; separate profiles do
  not isolate.
- Sites control strings that reach it (target URLs and titles): a page
  spawning `data:` workers with 1.9 MB addresses pushed over 1 GB through the
  guard in 9 s and delayed other tabs' workers by seconds; a page that
  exhausts its own heap crashes with the same code as a genuine injection
  crash, so watchdogs and crash breakers become remote switches.
- The core would be tier B (never an AI's): AUTOMAT could detect a breakage
  but not repair it.

## 3. What is reused

Without any privileged channel:

- An absolute coverage test (fp_audit's matrix as an automatic test, with the
  expected result per level and context) and negative tests, because "Nothing
  gets worse" compares main and a candidate on the same engine and cannot see
  a loss the engine causes on both sides.
- The worker rules per level: Kontrol lets the sites' own unprotectable workers
  run, with a clear notice; Maximum refuses them (owner's decision of
  2026-11-28, ROADMAP.md).
- Experiments to run before any claim: AudioWorklet noise from the page's own
  script, canvas read-backs that may bypass the noise (`VideoFrame.copyTo`,
  `createImageBitmap`, WebCodecs; Brave lists the first as a known bypass of
  its own), an inventory of the APIs per context after each engine update.
- Known limits stay written down: service and shared workers from a file
  cannot be protected; a service worker already running cannot be stopped at
  once by Qt (it is unregistered, its script refused, and it ends with its
  site's tabs).

## 4. Brave, for comparison (brave-core master, read 2026-11-28)

Brave farbles in Blink's C++ on `ExecutionContext`, so every worker and worklet
is covered and nothing is detectable through `toString`. Its token is a random
128-bit value per site (scheme + eTLD+1), per profile and per browser session,
made in the browser process; frames use the top-level site, dedicated workers
their parent frame, shared and service workers their own origin. Canvas:
HMAC-SHA256 of the pixels with an LFSR, 512 bits flipped; audio: a factor of
0.999-1.000; hardwareConcurrency in [4, real]; screen and media queries
rounded to a standard size. On Linux its font allowlist exists only for
Ubuntu and Fedora (none on Arch), and Standard keeps the real WebGL renderer
name: there I.K.E.'s Kontrol and Maximum are stricter. Brave hid its Strict
mode (1.62-1.64): it broke sites and fewer than 0.5% of users chose it, which
made them stand out. Brave's iOS version protects with injected JavaScript, as
I.K.E. does. Licence MPL-2.0: ideas may be reimplemented freely; copied code
would stay MPL file by file.
