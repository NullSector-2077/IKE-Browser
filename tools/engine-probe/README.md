# Engine probe (1.1.29)

What websites can observe of the engine, measured the same way on I.K.E. and
on a Chromium of the engine's version. Not part of the browser, not in the
package. Used by the weekly check `.github/workflows/engine-identity.yml`
(docs/MAINTENANCE.md, "The engine's identity, every week"); the study that
made it is docs/review/engine-privacy-study.md.

- `probe.html`, `probe-core.js`, `probe-worker.js`: every global and interface
  member in the page, a same-origin frame and the dedicated, shared and service
  workers; CSS, V8 errors, Intl, navigator and client hints, WebGL, WebGPU,
  codecs, DRM, permissions, the permission policy, `window.chrome`.
- `extra.html`: behaviours (advertising APIs at work, the language in every
  place, URL origins, WebAuthn, PDF, forms).
- `run.py OUT TARGET...`: opens a page in each browser (`ike:LEVEL`, `qt`,
  `chrome:NAME=BINARY`, `+FLAGS`, `@label`), with the request headers, the TLS
  ClientHello (JA4) and the HTTP/2 preface of a local HTTPS server.
- `diff.py A B`, `classify.py`: what differs, and where it comes from.
- `identity_guard.py`: the weekly check's verdict, in Italian, for the
  signing notice; `baseline.json`: the engine's known gaps.

    xvfb-run -a python3 tools/engine-probe/run.py out ike:balanced "chrome:x=/usr/bin/chromium@chromium"
    python3 tools/engine-probe/diff.py out/ike-balanced.json out/chromium.json
