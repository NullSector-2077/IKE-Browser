# Windows engine: progress note

Kept current while the work goes on, so that another session can take over at
any moment. Times are UTC. Branch `windows/engine`, worktree
`/home/claude/wt-engine`. Rule for this file: only what a workflow run showed
is written as a result; everything else is marked as expected or open.

## Goal

H.264 and AAC on Windows decoded by Windows' own Media Foundation decoders
(driver and software), no H.264 / AAC decoder and no OpenH264 in the engine
(`ffmpeg_branding="Chromium"`). Owner's decision of 2026-11-17: integrate
existing open-source code instead of developing I.K.E.'s own adapter.

## What is integrated (2026-11-17)

| Patch (`packaging/windows/qtwebengine/patches/`) | Origin, licence |
|---|---|
| `chromium/0002-vivaldi-platform-media-h264-windows` | Vivaldi 7.6.3797 `platform_media` (Opera origin), mirror `ric2b/Vivaldi-browser` @ `bb6a67c4a38211d36180421ee814367f8d274be4`; BSD 3-clause. `WMFVideoDecoder`, `platform_media_init`, `VivaldiDecoderConfig`, logging helpers; hooks in `decoder.{h,cc}`, `default_decoder_factory.cc`, `renderer_main_platform_delegate_win.cc`. 7 files byte-identical, 3 with marked changes (`chromium/platform_media/README.ike.md` in the patch) |
| `chromium/0003-cromite-platform-aac-audio-windows` | Cromite `Enable-platform-aac-audio-and-h264-video.patch` @ `3724efc6`, Windows AAC hunks only, unchanged; GPL-2.0-or-later |
| `chromium/0004-qt-and-free-ffmpeg-fixes` | I.K.E. glue: COM on Qt's in-process GPU thread; `FAILED(ConfigureOutput())`; AAC sample format and AAC profile (for the ADTS header) when FFmpeg has no AAC decoder / parser |
| `chromium/0001`, `qtwebengine/0001` | I.K.E.: assert relaxed; GN args (`ffmpeg_branding="Chromium"`, `media_use_openh264=false`, `rtc_use_h264=false`, `enable_platform_aac_audio=true`, …) |
| `superseded/own-adapter/` | the earlier own implementation, kept, not applied |

Not integrated, with the reason: Vivaldi's FFmpeg-level AAC decoder
(`wmfaacdec.c`, needs `ffmpeg_branding="Chrome"`) and its GPU / utility
start-up hooks; Cromite's H.264 and Android parts. See `patches/README.md`.

Why patch 0004 was needed (found by reading, 2026-11-17): Cromite hands AAC to
Windows with ADTS headers. For plain MP4 files the header is written by
`FFmpegAACBitstreamConverter` from FFmpeg's `codecpar->profile`, which only an
AAC decoder or parser fills in — and a Chromium-branded FFmpeg has neither
(`libavformat/isom.c` sets channels and rate, not the profile). Cromite never
meets this because it builds FFmpeg "Chrome"-branded. Same for the sample
format. Media Source is not affected (Chromium's own MP4 parser).

## Runs

| Run | What | Result |
|---|---|---|
| 43968550111 (2026-11-16 22:17) | old own-adapter patches, stage 1 from nothing | GN and the early compile of the media code passed; stage 1 reached step 13501 of 19527 in 4 h 13 min of building and saved its build folder (0.71 GB packed); cancelled at the start of stage 2 by the push below. Never linked, never played |
| 43976704292 | decoders probe (own-adapter call sequence), Server 2022 + 2025 | 10 of 10 probe runs passed: the Windows H.264 and AAC decoders exist and decode on the runners (software), AAC both as bare frames and with ADTS headers |

| 44003268848 (2026-11-17 02:28) | decoders probe with a third AAC mode that repeats the integrated code's calls (COM, `MFTEnumEx` + `ActivateObject`, payload type ADTS + AudioSpecificConfig, frames with ADTS headers); Server 2022 + 2025 | 12 of 12 passed on both. This is the Windows side of the Cromite AAC path and of Vivaldi's H.264 calls (same input type, YV12 output, `DllGetClassObject`), outside Chromium. It says nothing about the engine itself |

Runs with the integrated patches: see "Log" below.

## Not proven yet (as of the last log entry)

- that the integrated patches compile with MSVC inside Qt's Chromium;
- that the engine links, passes the "no FFmpeg H.264 / AAC, no OpenH264"
  checks and packages;
- any playback with the built engine. Until the `verify` jobs have run,
  nothing about playing H.264 / AAC with this engine is known.

## How to continue (for whoever takes over)

- Latest runs: `gh api "repos/NullSector-2077/IKE-Browser/actions/runs?branch=windows/engine&per_page=8"`,
  jobs with `.../runs/<id>/jobs`, logs with `.../jobs/<job id>/logs`
  (artifact downloads are blocked from the agent environment; the logs and
  the job summaries have what is needed).
- A push that changes `patches/**` (not `.md`), `versions.json` or the two
  engine workflows starts a new run and **cancels the running one**. A
  cancelled stage does not save its build folder: push such changes right
  after a stage has finished ("Keep the build folder" done), or use
  `[skip ci]` and let the next stage pick the change up (every stage checks
  out the head of the branch; only the workflow files stay those of the run).
- First thing to look at in a new run: stage 1, step "The patched media code
  first" (about 15–40 minutes after the start). If it fails, the log has
  `FAILED:` with the compiler's message; fix the patch in the local clone
  (`/home/claude/src/qwc`, one commit per patch; `/home/claude/work/gen/gen_patches.py`
  writes the patch files from the commits), push.
- The whole build needs fewer stages than first thought: stage 1 of run
  43968550111 did 13501 of 19527 steps (the remaining ones include the
  heaviest: Blink, V8, the link). Expect two or three stages of up to
  4 h 45 min. The last stage
  uploads `ike-qtwebengine-windows`; then `verify` plays the clips on Server
  2022 and 2025 and writes the decoder names into the job summary.
- Expected decoder names in `verify`: video `WMFVideoDecoder`, audio
  `MediaFoundationAudioDecoder`.
- Local source clones: `/home/claude/src/qwc` (Qt's Chromium, sparse, branch
  with the four commits `p0001`, `vivaldi`, `cromite-aac`, `ike-glue`),
  `/home/claude/src/qtwebengine`, `/home/claude/viv76` (Vivaldi 7.6 files),
  `/home/claude/research/src/uazo_cromite`. They are not in the repository; the
  patches are.

## If it cannot be made to work

Fallbacks in order (see `windows-codec-fallbacks.md`): (1) for AAC, feed bare
AAC frames instead of ADTS as the superseded own patch 0004 did; (2) Vivaldi's
FFmpeg-level `wmfaacdec.c` — only acceptable if the link map proves no FFmpeg
H.264 / AAC decoder object is linked, because it needs `ffmpeg_branding="Chrome"`;
(3) Cobalt 24.lts Starboard decoders as a reference for the MFT handling.

## Log

- 2026-11-17 02:30 — integration written and checked locally: the four
  chromium patches applied in order to pristine `e2b413ea` reproduce the local
  tree; pushed with `[skip ci]` while stage 1 of run 43968550111 was still
  compiling, so as not to cancel it.
- 2026-11-17 02:31 — probe run 44003268848 passed (see "Runs"). Waiting for
  stage 1 of run 43968550111 to save its build folder (build stops at 03:02,
  then packing) before the push that starts the run with the integrated
  patches.
- 2026-11-17 03:04 — run **44007527523** started by push `7df8f58`: the first
  build with the integrated patches, continuing from the build folder of run
  43968550111.
