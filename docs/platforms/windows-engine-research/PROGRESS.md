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

| 44010178959 (2026-11-17 03:26) | probe, commit `34b2cc8` (saved unreviewed when Fable's usage ended; reviewed afterwards: correct, it copies Vivaldi's stride / rows arithmetic from `WMFVideoDecoder::ConfigureDecoder()` and `CreateOutputFrame()`); Server 2022 + 2025 | 12 of 12 passed on both. Vivaldi's fixed picture layout (stride = `MFGetStrideForBitmapInfoHeader(YV12, width)` rounded up to 16, rows = coded height rounded up to 16) equals the decoder's real output in all six H.264 cases (320x240, 854x480, 1920x1080, 1280x720, 854x480 low delay, 322x242). It differs only from the provisional output type offered before the first `MF_E_TRANSFORM_STREAM_CHANGE` (e.g. 854 / 480 before, 864 / 480 with aperture 854x480 after), and Vivaldi's decoder reconfigures on that change before the first picture. Also shows that `MFGetStrideForBitmapInfoHeader` links with `mfplat.lib` (the engine's link needs nothing more for it) |

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
- 2026-11-17 03:22 — run 44007527523, stage 1: "The patched media code first"
  **passed** (03:17–03:22): GN accepted the arguments and MSVC compiled the
  integrated patches (Vivaldi's `platform_media`, Cromite's AAC hunks, the
  I.K.E. glue) with the rest of the media code. Not yet linked. Full build
  running; this stage stops building at minute 285 (about 07:50) and saves
  its build folder.
- 2026-11-17 03:30 — Opus 5.5 took over from Fable. Reviewed the unreviewed
  probe commit `34b2cc8` (see run 44010178959 above) and patch 0004 (the ADTS
  profile mapping writes LC for HE-AAC / HE-AAC v2 with the core sample rate
  from the AudioSpecificConfig, as `FFmpegAACBitstreamConverter` expects; the
  early return in `ffmpeg_common.cc` only skips a debug check). The build
  script already had the edits for the integrated patches (commit `23493a1`:
  `WMFVideoDecoder` among the expected strings, the licence files copied into
  the package); nothing was left half-done there.

## Follow-up by ChatGPT (2026-11-17, owner-authorised Windows codec work)

The first integrated build is now further along than the earlier log implied:

- Run [44007527523](https://github.com/NullSector-2077/IKE-Browser/actions/runs/44007527523):
  both build stages completed; the final Qt WebEngine package was produced.
  The link/evidence/package steps passed. The stock PyPI control also passed.
- On both Windows Server verification runners, the first built-engine pass
  decoded the H.264 Baseline/Main/High clips and AAC-LC MP4 clips with the
  expected `WMFVideoDecoder` and `MediaFoundationAudioDecoder` names. The
  video-only and audio-only Media Source cases passed as well.
- The combined Media Source case failed while adding its second
  `SourceBuffer`, with `QuotaExceededError`. This is Chromium's generic mapping
  for `ChunkDemuxer::kReachedIdLimit`, not a byte-memory quota: `ChunkDemuxer`
  accepts new IDs only while `WAITING_FOR_INIT` or `INITIALIZING`. The old
  test appended the video init segment before registering the audio buffer,
  so the demuxer had already left the allowed state. The MSE harness now
  registers every SourceBuffer before appending any segment. See Chromium's
  `ChunkDemuxer::AddId` state guard in
  [source](https://chromium.googlesource.com/chromium/src.git/+/adac9f8446f93e101ce0f641af773c2024003955/media/filters/chunk_demuxer.cc#650).
- The workflow then installed the optional Server-Media-Foundation feature
  and retried. On the Server 2022 runner the DLLs were already present before
  installation (`mfplat.dll`, `msmpeg2vdec.dll`, `msauddecmft.dll`), and the
  first pass had already used them successfully. After the feature-install
  retry, H.264/AAC were no longer advertised by that process. This retry was
  therefore removed rather than treating a test-harness failure as a missing
  Windows decoder.
- The GPU-disabled command also had a shell/argparse issue:
  `--flags "--disable-gpu"` was parsed as a missing argument. It is now passed
  as `--flags=--disable-gpu`.

Commits made on `windows/engine`:

| Commit | Change |
|---|---|
| `67ca00d` | Create all Media Source buffers before appending the first segment; check HTTP responses before appending |
| `f1ba982` | Remove the disruptive Media Foundation feature retry; correct the `--disable-gpu` argument |

Run [44115530898](https://github.com/NullSector-2077/IKE-Browser/actions/runs/44115530898)
was started from commit `f1ba982` to rebuild and verify these changes. Its
result must be added here after the jobs finish. Do not claim the MSE
two-buffer fix works until that run confirms it on both Windows runners.

The runners have no physical GPU. Even after the software path passes, a
real Windows 10/11 PC with a GPU is still required to prove hardware H.264
selection (`D3D11VideoDecoder`), 1080p60/4K performance, real-site MSE and
long-session seek/audio-sync behaviour.

### HE-AAC status (explicitly not yet verified)

- `MediaFoundationAudioDecoder` is patched to accept AAC profiles beyond the
  original xHE-AAC-only path, and `verify_codecs.py` contains a HE-AAC probe.
- The generated HE-AAC test clip is conditional on FFmpeg exposing
  `libfdk_aac`. The hosted Windows runners used in the previous codec run do
  not have that encoder, so the clip was skipped; AAC-LC playback was tested,
  but HE-AAC v1/v2 playback was not.
- `packaging/windows/qtwebengine/patches/README.md` now labels HE-AAC as
  code-path-present/runtime-test-pending. Do not call it verified until a
  pinned HE-AAC sample is played through the built Qt WebEngine and produces
  decoded audio. The code currently reports MIME support, which is not proof
  of successful decode.

### Verification after the MSE / workflow fixes — run 44115530898

Run [44115530898](https://github.com/NullSector-2077/IKE-Browser/actions/runs/44115530898)
completed successfully on 2026-11-17. The build and both real-playback jobs passed:

- Stage 1: restored the prior 1.16 GB build tree; all patches applied; configure
  passed; media smoke compilation passed; the full Qt WebEngine build completed;
  install/link evidence/package and build-tree upload passed.
- The stock PyPI engine control remained negative for H.264/AAC on both runners.
- Windows Server 2022 and Windows Server 2025 both decoded:
  H.264 Baseline, Main, High (including B-frames, up to 1920x1080),
  AAC-LC stereo 44.1 kHz and mono 48 kHz, the two-buffer combined H.264+Aac
  Media Source case, video-only MSE and audio-only MSE.
- The built engine selected `WMFVideoDecoder` for H.264 and
  `MediaFoundationAudioDecoder` for AAC-LC, confirmed by Chromium's Media log;
  each test observed decoded pictures and audio bytes.
- The full same playback suite passed again on both Windows Server runners
  with `--disable-gpu`. This confirms the Windows software Media Foundation
  H.264 fallback and AAC decode do not require Chromium GPU acceleration.
- HE-AAC was still skipped because FFmpeg on the hosted runners has no
  `libfdk_aac`; it remains code-path-present/runtime-test-pending.

Artifacts from the run:

- `ike-qtwebengine-windows` (engine package), artifact ID `14344077644`.
- `engine-build-tree` (incremental build tree), artifact ID `14344213072`.
- `engine-codec-check-windows-2022`, artifact ID `14344078429`.
- `engine-codec-check-windows-2025`, retained by the successful 2025 job.

**Scope of this evidence:** these are hosted Windows Server VMs using the
Microsoft Basic Render Driver, not physical GPU hardware. The run proves the
software decoder path, H.264/AAC playback and MSE on the two tested Windows
Server code bases. It does not prove D3D11 hardware decoder selection, GPU
acceleration, performance on a consumer Windows 10/11 desktop, HE-AAC,
DRM/protected media, streaming-site compatibility, extended playback/seek
stability or A/V sync over long sessions. Those need separate tests.

Next work: secure the Media Foundation DLL loading path, make the H.264
factory's one-time function lookup thread-safe, add a reproducible HE-AAC
fixture/test, then run another incremental build and codec matrix.


### Follow-up hardening and HE-AAC fixture work — 2026-11-17

- Commit `43211a7` hardens `platform_media_init.cc`: the existing
  `LoadLibraryExW(..., LOAD_LIBRARY_SEARCH_SYSTEM32)` restriction is kept,
  and `std::call_once` now synchronizes the shared `mfplat.dll` handle and
  each decoder DLL handle. This prevents concurrent renderer initialization
  from racing on the global handle cache.
- `WMFVideoDecoder::CreateWMFDecoder()` already uses a function-local static
  for the `DllGetClassObject` lookup; C++ guarantees thread-safe
  initialization of that static. The loader cache was the unsynchronized part.
- Build run [44122657019](https://github.com/NullSector-2077/IKE-Browser/actions/runs/44122657019)
  is active on commit `43211a7`. Its PyPI negative-control job passed; stage 1
  is still in its tools / Qt / source preparation step. The patch-application
  and MSVC smoke steps have not run yet, so the loader change is not yet
  compile-verified.
- The fixture-discovery workflow
  [44123443165](https://github.com/NullSector-2077/IKE-Browser/actions/runs/44123443165)
  passed on Windows Server 2022. FFprobe identified both official Fraunhofer
  files as AAC stereo at 44.1 kHz:
  - AOT 5 / HE-AAC v1: 234,051 bytes,
    SHA-256 `ede70e3b2f7e364aeb0eb3854b7d9a5877be99a499dcebe22ac5a7349d68747c`,
    FFprobe profile `HE-AAC`.
  - AOT 29 / HE-AAC v2: 241,061 bytes,
    SHA-256 `d021b3dfbfb7ad42eacdad9c3391b5268603d6f1c6bcf171e57292ff1ada06fb`,
    FFprobe profile `HE-AACv2`.
- Commit `0897d26` adds both as mandatory fixtures in `verify_codecs.py`.
  The clip builder checks HTTPS content type, exact size and SHA-256, MP4
  signature, FFprobe profile, stereo / 44.1 kHz and AudioSpecificConfig
  presence. Playback cases are added for both profiles and MIME probes now
  cover `mp4a.40.5` and `mp4a.40.29`. The test still only counts as decoded
  when the media element reports actual audio bytes.
- Workflow
  [44124142153](https://github.com/NullSector-2077/IKE-Browser/actions/runs/44124142153)
  is exercising the fixture downloader and full clip builder on Windows.
  Fixture validation is not engine playback: HE-AAC v1/v2 remain unverified
  until the built Qt WebEngine passes those two playback cases.
