# Fingerprinting audit after the 1.1.32 changes (2026-11-28)

The owner's brief for 1.1.32, point 3.3: after the worker, Trusted Types and
passkey changes, check the anti-fingerprinting protection level by level, in
every place a site can read values. Tool: `tests/fp_audit.py` (not part of the
automatic tests; it prints a table per level). Setup: this repository at the
merge of both sessions' branches (18b0084 and later), PyQt6-WebEngine 6.140.1
(Chromium 140.0.7339.264), software WebGL (llvmpipe), 4 cores, 8 GB, UTC,
en-US, offscreen. What the container cannot show: a real graphics card,
WebGPU (no adapter here), other time zones and languages, a real desktop's
fonts; the values that depend on them were only compared between places, not
judged.

## What was measured

In the page, a frame of the same site, a srcdoc frame, an empty frame the page
fills, a blob worker, a data: worker, a worker from the site's file, a worker
started by a worker, a shared worker from a blob and from a file, and a
service worker: cores, memory, languages, time zone and locale, user agent,
brands and high-entropy client hints, an OffscreenCanvas picture and a text
width, WebGL vendor/renderer (WEBGL_debug_renderer_info), extensions, limits
and a read of pixels, WebGPU's adapter, a font found by `local()`; audio in
the page.

## Results (verified)

| Place | Off, Compatibility | Balanced | Kontrol | Maximum |
|---|---|---|---|---|
| frame, srcdoc, empty frame | as the page | as the page | as the page | as the page |
| blob worker, worker's worker | as the page | as the page | as the page | as the page |
| data: worker | as the page | own noise (own seed, by design) | own noise | own noise |
| worker from the site's file | as the page | **engine's values** (real card name, no noise) | as the page (protected copy) | as the page |
| shared worker from a blob | engine's fonts* | page's values, engine's fonts* | page's values, engine's fonts* | page's values, engine's fonts* |
| shared worker from a file | engine's values | **engine's values** | **engine's values: full version 140.0.7339.264, real card name, no noise** | refused |
| service worker | engine's values | **engine's values** | **engine's values (as above)** | refused |

\* Shared and service workers draw text with the engine's default font, not
the page's (a width of 149 against 138 here), at every level including Off:
the engine's own difference, not I.K.E.'s; Chromium gives workers without a
document the default fonts too.

Compatibility equals Off for every value (only the passkey answers and the
privacy signal differ). WebGL's pixels of a plain colour are left exact in
the page and its workers (by design); a data: worker's own seed noises them.

## Findings

1. **Kontrol: a site's own shared and service workers show the engine's
   values** (since the 1.1.32 rule that lets a site's own workers run at
   Kontrol, the owner's decision, the other session's area): the full Chrome
   version, the real graphics card's name and an unnoised canvas, where the
   page says 140.0.0.0, no card name and a noised canvas. Only the site's own
   code runs there (a third-party script cannot start a worker from its own
   file, and a blob worker is protected), so it is the site itself that can
   read them, and compare them with the page. No engine switch hides them:
   tried `--disable-blink-features=WebGLDebugRendererInfo` and the
   `--gpu-testing-gl-*` switches, no effect in workers; Qt WebEngine cannot
   add a script to a worker loaded from a file. To be shown to the user with
   the other reductions (the shield's diagnosis), or kept out (as Maximum).
2. **Balanced: workers, shared workers and service workers from the site's
   files show the engine's values** (since 1.1.18, documented as a known
   limit in tests/test_fingerprint_gpu.py): same reason.
3. **Passkeys: a silent passkey upgrade started a real request for a security
   key.** With `conditionalCreate: true` (Chromium's answer) a site may call
   `navigator.credentials.create({mediation: 'conditional'})` after a password
   sign-in; Qt WebEngine treats it as an ordinary request
   (`webAuthUxRequested`, Discovery): a key plugged in would blink, and the
   request blocks the next one. Fixed: I.K.E. answers `conditionalCreate:
   false` (as Firefox does), its only difference from Chromium's list.
   Conditional sign-in (`conditionalGet`) waits silently, as in Chromium with
   no passkey saved (tests/test_passkeys.py).
4. **Ways a site can make the protection step back on purpose**, all
   documented in docs/SECURITY.md: a server policy that allows only its own
   Trusted Types names and a default policy (workers start as asked: the
   Cloudflare compromise; Qt offers no other way to give the worker its
   protection under that policy); at Kontrol a worker-src without blob: (the
   site's own file runs as asked, the other session's rule); a site's own
   shared and service workers (point 1). None of them can be used by a
   third-party script alone, and none from a `<meta>` a script adds (tests in
   tests/test_trusted_types_workers.py and tests/test_worker_addresses.py).
5. **Known, unchanged**: a ReportingObserver and a listener after
   `document.open()` can see the refusal of I.K.E.'s Trusted Types policy on
   sites that allow only their own names; at Compatibility the three passkey
   functions read `function () { [native code] }`.

Nothing found that leaks the noise's seed, and no place where a page's own
script can take the protection out of its workers (both reviews' cases are
tests now).
