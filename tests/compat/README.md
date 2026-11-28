# Web compatibility campaign (tests/compat)

A reusable, manual suite that opens real websites in the real, installed
I.K.E. at each protection level and records what the pages did. It is not
part of `python3 -m pytest` (no file here starts with `test_`), it is not run
by GitHub Actions and AUTOMAT does not use it: it needs the network, takes
tens of minutes and its results depend on the sites of the day.

First used for the campaign of 2026-11-28 (docs/review/web-compat-2026-11.md).

## Files

| File | What it does |
|---|---|
| `run.py` | Starts I.K.E. (the installed copy, `/usr/lib/ike-browser`, or `--app`) with a fresh profile copied from a "base" profile, at one level (`--level`), with or without dark mode (`--dark on/off`, `--engine ike/engine`), and runs `steps.py`. `--warm DIR` makes the base profile once (I.K.E. downloads its real filter lists). `--x11` runs on Xvfb instead of the offscreen platform (WebGL needs it). `--switch strict,maximum:4000,...` changes the level while each page is open, through the same calls as the shield (`apply_settings`, `refresh_windows`, reload). `--flags=...` adds engine switches. `COMPAT_PATCH` (environment) runs Python inside the browser before the first site: used for experiments that lift one rule only. |
| `steps.py` | Runs inside I.K.E. (through `tests/harness.py`): opens each site in its own tab, waits, runs `probe.js` in I.K.E.'s own world (the page cannot see it), records the engine's console messages, every request I.K.E. blocked (with its type) and a screenshot. |
| `probe.js` | What the page shows and does: text, nodes, frames, canvases, videos (ready state, time, errors), service workers, colours, plus the site's own check from `sites.json`. |
| `sites.json` | The sites and their checks (results found, video advancing, map drawn, QR code shown...). `partial` marks a site whose main function needs an account (only the page before sign-in is tested). |
| `baseline.js` | The same sites and checks in another Chromium browser through Playwright (Chromium of the engine's version, Brave...). |
| `webtech/` | Local pages for the web technologies: `index.html` (WebSocket, workers of every kind, WebAssembly, WebGL, WebGPU, canvas, storage, codecs, playback, EME, WebRTC, permissions, upload, download...), `streaming.html` (DASH, HLS and Widevine with public test streams), `serve.py` (serves them on `http://localhost:8123`, a secure context, with an upload endpoint and a download), `make-media.sh` (the small test videos, made with ffmpeg). |

## Running it (Arch Linux)

```bash
# once: an Arch container (or an Arch machine) with I.K.E. installed from the PKGBUILD,
# xorg-server-xvfb, and the base profile with the real filter lists
python tests/compat/run.py --warm ~/compat/base
# the web technologies page
(cd tests/compat/webtech && ./make-media.sh media && python serve.py 8123 &)
# one level, dark mode on, all the sites
python tests/compat/run.py --x11 --base ~/compat/base --level strict --dark on \
    --sites tests/compat/sites.json --out ~/compat/out/strict --flags=--ignore-gpu-blocklist
# the same sites in Chromium 140 / Brave (Playwright)
node tests/compat/baseline.js /path/to/chrome tests/compat/sites.json ~/compat/out/chrome140
```

`--ignore-gpu-blocklist` is only for machines without a graphics card (a
container): the engine refuses WebGL on a software renderer otherwise. On a
real PC leave it out, so the engine chooses its own GPU path. It has a cost:
with it (or with the offscreen platform) Discord's sign-in page stays empty,
in Qt WebEngine as such; without it, in an X window, Discord works (the
campaign of 2026-11-28, section 4.2). Check a failing site both ways.

Results: `OUT/results.json` (one record per site), `OUT/<site>.png`,
`OUT/stderr.txt` (the engine's own messages).

## What it cannot tell

- A site that needs an account is tested only up to its sign-in page; no
  account is created and no credentials are used.
- Sign-in, payment and purchase flows are never completed.
- From a data centre, some sites answer with a captcha or a geographic block
  whatever the browser; compare with the baseline browsers before calling it
  an I.K.E. problem.
- Real GPU paths, hardware video decoding, cameras, microphones and
  notifications need a desktop session; the container gives only fakes.
