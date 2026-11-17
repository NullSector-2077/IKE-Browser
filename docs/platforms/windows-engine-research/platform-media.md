# Windows: H.264 / AAC through Media Foundation, the way Vivaldi and Opera do it

Study date: 2026-11-16. Follows `windows-codecs.md`. What was built and what
the GitHub runners proved is in the last section ("Results"), which is filled
in from the workflow runs; everything else here was read, not run.

How to read this: **[V]** read in the source named; **[I]** inferred; **[T]**
has to be tested on a real Windows computer.

## Summary

- Vivaldi publishes its whole modified Chromium tree, `platform_media`
  included, as source archives on `vivaldi.com/source`. An unofficial Git
  mirror exists (`ric2b/Vivaldi-browser`); its newest commit is Vivaldi
  7.7.3851 = Chromium 142.0.7444.143 (1 December 2025) [V].
- Licence: BSD 3-clause. The Windows video decoder and the sandbox helper are
  "an original work developed by Opera Software ASA", under
  `platform_media/OPERA_LICENSE.txt` (BSD 3-clause, © 2013 Opera Software ASA);
  Vivaldi's own work is under the BSD 3-clause `LICENSE` at the root
  (© 2015 Vivaldi Technologies) [V]. Compatible with I.K.E.'s GPL-3.0-or-later
  and with Chromium's own BSD licence.
- No public source release of Opera's own `platform_media` was found; the
  code is known through Vivaldi's tree, whose file headers credit Opera.
- Today's `platform_media` is small on Windows: one `media::VideoDecoder`
  (512 lines) that drives the H.264 transform of Windows in the renderer, a
  134-line helper that loads the Windows decoder libraries before the sandbox
  closes, and an AAC decoder written in C behind FFmpeg's codec interface
  (1105 lines). It hooks into Chromium in about ten places. The old
  whole-pipeline design (its own demuxer over IPC) is gone.
- **A smaller path exists and is what I.K.E. now has**: Chromium already
  contains a Media Foundation *audio* decoder that only needs to be allowed to
  take AAC-LC / HE-AAC, and a software H.264 decoder is one new class of about
  500 lines. Chromium's own demuxers stay. I.K.E.'s implementation is its own
  code; from Vivaldi / Opera it takes the idea and two facts about Windows
  (create the transform straight from its DLL; load the DLL before the
  sandbox), not their source text.
- Hardware decoding is not part of `platform_media` at all, in Vivaldi or
  here: it is Chromium's `D3D11VideoDecoder`, which is in every Chromium build
  and switched on for H.264 by `proprietary_codecs=true`.

## 1. Where the code is, and its licence

| What | Where | Checked |
|---|---|---|
| Official source | `https://vivaldi.com/source/` — one archive per release, the complete tree (`chromium/` plus Vivaldi's folders) | [V] the page is named in the mirror's README; the archives themselves were not downloaded (300 MB – 1 GB each, not reachable from the study environment) |
| Git mirror (unofficial) | `https://github.com/ric2b/Vivaldi-browser`, one commit per published archive; newest: "Added version 7.7.3851", 2025-12-01 | [V] cloned (partial clone, `platform_media/` and the hooked Chromium files) |
| Chromium base of that commit | 142.0.7444.143 (`chromium/chrome/VERSION`) | [V] |
| Vivaldi on its licence | The C++ code is published "alongside Chromium changes" under the "open-source BSD license"; the user interface is not open | [V] Vivaldi's blog [S3] |
| Opera | No public tree with `platform_media` found by search. Opera's Linux builds are known to load a separate `libffmpeg.so`, as Vivaldi's do | not found |

Licence text, from the files themselves [V]:

- `platform_media/decoders/win/wmf_video_decoder.{h,cc}` and
  `platform_media/sandbox/win/platform_media_init.{h,cc}`:
  "Copyright (c) 2018 Vivaldi Technologies AS. All rights reserved. /
  Copyright (C) 2015 Opera Software ASA. All rights reserved. / This file is an
  original work developed by Opera Software ASA".
- `platform_media/OPERA_LICENSE.txt`: "All original work by Opera Softare ASA
  contained in this source code distribution is licensed as follows", then the
  three BSD clauses (retain the notice in source, reproduce it in binary
  distributions, no endorsement), © 2013 Opera Software ASA.
- Root `LICENSE`: the same three clauses, © 2015 Vivaldi Technologies; root
  `README`: "Use of original work by Vivaldi Technologies contained in this
  source code package is governed by a BSD-style license".
- `platform_media/ffmpeg/wmfaacdec.c`: "Copyright (c) 2021 Vivaldi Technologies
  AS. All rights reserved" (covered by the root licence). It includes FFmpeg's
  internal headers and is compiled into FFmpeg; `audiotoolboxdec.c` (macOS) is
  a fork of an FFmpeg file, so FFmpeg's LGPL applies to that one.

Not legal advice. What using BSD code would require: keep the copyright
notices in the source, and reproduce notice + licence in the documentation of
a binary distribution. I.K.E. copied no source text (section 4), so the
credit in `patches/README.md` and in the new file's header is a courtesy, not
an obligation; someone qualified should confirm.

## 2. What `platform_media` is today (Vivaldi 7.7, Chromium 142) [V]

Vivaldi's own description (`platform_media/README.md`): because of patents
Vivaldi "cannot ship with certain codecs turned on in ffmpeg (the AAC audio
codec and the h264 video codec)"; on Mac and Windows it uses "platform
decoders in their SDKs", on Linux a second FFmpeg installed by the user.

| Folder | Content | Windows part |
|---|---|---|
| `decoders/` | `media::VideoDecoder` implementations, logging helpers | `win/wmf_video_decoder.{h,cc}` — 512 + 70 lines |
| `ffmpeg/` | GN script that rewrites FFmpeg's `codec_list.c`; audio decoders behind FFmpeg's `AVCodec` interface | `wmfaacdec.c` (1105 lines), `ffviv_audio_kit.c` (228), `ffviv_log.*` |
| `sandbox/` | start-up helpers | `win/platform_media_init.{h,cc}` — 134 lines |
| `docs/` | five short design notes | — |
| `source_updates.gni` | adds the files to Chromium's `//media/renderers`, `//base` and `//third_party/ffmpeg` targets | — |

### Video (H.264)

- `WMFVideoDecoder` creates `CLSID_CMSH264DecoderMFT` by calling
  `DllGetClassObject` in `msmpeg2vdec.dll` directly — not through
  `CoCreateInstance`, which would read the registry, impossible inside the
  renderer's sandbox.
- It runs **in the renderer process**, synchronously on the media thread,
  without a Direct3D device: software decoding only.
- Output asked for: YV12; every picture is copied out of the transform's
  buffer. Two corrections carry comments saying their authors do not know why
  they are needed (row count and stride rounded up to 16).
- `NeedsBitstreamConversion()` returns true, so the demuxers deliver Annex B
  with the parameter sets in the stream. That call only exists with
  `proprietary_codecs=true`, which is why Vivaldi keeps that switch on.
- Hardware: Vivaldi's note says Chromium's old `DXVAVideoDecodeAccelerator`
  could have been patched, but Chromium "deprecated this decoder in favour of
  Direct 3D implementation in `D3D11VideoDecoderImpl` … that assumes video
  hardware acceleration is always available". So hardware H.264 in Vivaldi is
  plain Chromium, and `WMFVideoDecoder` is the fallback after it.

### Audio (AAC)

- Opera's original was a `media::AudioDecoder`. Vivaldi moved it behind
  FFmpeg's codec interface (`ffwmf_aac_decoder`, in C) because Chromium calls
  FFmpeg directly in a few places (Web Audio's `decodeAudioData`, the media
  parser utility) without going through `media::AudioDecoder`.
- It drives `CLSID_CMSAACDecMFT` from `msauddecmft.dll`, again through
  `DllGetClassObject`, and handles both bare AAC frames with the
  AudioSpecificConfig and ADTS framing.
- Cost: the AAC library has to be loaded before the sandbox in every process
  that can decode audio (renderer, GPU, some utility processes), and FFmpeg is
  built with `ffmpeg_branding="Chrome"` plus a rewritten codec list. Vivaldi's
  build settings say why: "ffmpeg_branding == Chromium disables way too much
  code including various utilities unrelated to codecs that we need".
- Vivaldi's own note points at the other way: Chromium's
  `MediaFoundationAudioDecoder` "can be patched to support all AAC
  variations. Such change will remove the need to maintain sandbox relaxations
  in Vivaldi" — not done there only because of the direct FFmpeg calls.

### Hooks in Chromium (all behind `USE_SYSTEM_PROPRIETARY_CODECS`) [V]

| File | Change |
|---|---|
| `media/base/decoder.h`, `decoder.cc` | new `VideoDecoderType::kVivWMFDecoder`, name "WMFVideoDecoder" |
| `media/renderers/default_decoder_factory.cc` | `VivaldiDecoderConfig::AddVideoDecoders()` at the end of the video decoder list |
| `content/renderer/renderer_main_platform_delegate_win.cc` | `platform_media_init::InitForRendererProcess()` in `PlatformInitialize()` |
| `content/gpu/gpu_main.cc`, `content/utility/utility_main.cc` | the same pre-load for the GPU and utility processes |
| `media/BUILD.gn` | the assert "proprietary codecs and ffmpeg_branding set to Chromium are incompatible" relaxed |
| `media/ffmpeg/ffmpeg_common.cc`, `media/filters/ffmpeg_glue.cc` | FFmpeg's codec / demuxer allow-lists and strict mode switched off for Vivaldi |
| `media/test/pipeline_integration_test*.cc` | the decoder added in tests |
| `vivaldi_init_settings.gni` | `proprietary_codecs = true`, `ffmpeg_branding = "Chrome"` |

No change in `media/base/supported_types.cc`, in the demuxers, in the
renderer factory or in the pipeline: Chromium's own MP4 demuxers (FFmpeg's for
files, `MP4StreamParser` for Media Source) feed the decoders. The
`README.md` still lists an "IPCDemuxer" note, but the file is no longer in
the tree: the earlier design, in which Windows' own source reader demuxed
*and* decoded in the GPU process, has been removed.

## 3. How much is needed for Windows, and the porting effort to Chromium 140

Qt WebEngine 6.140 is Chromium 140.0.7339.264 (`qt/qtwebengine-chromium`,
branch `140-based`, commit `e2b413ea`). Vivaldi's code is for Chromium 142: two
versions apart, and the files it hooks are almost the same in 140.

**Porting Vivaldi's code as it is** — feasible, about two days of work plus
testing [I]:

- Video: `wmf_video_decoder.*`, `platform_media_init.*`, the logging helpers
  and four hooks would carry over nearly unchanged.
- Audio is the expensive half: FFmpeg has to be built with the "Chrome"
  configuration (which compiles FFmpeg's own H.264 / AAC decoder sources and
  relies on the rewritten codec list to keep them out of the link), the
  generated-header trick of `platform_media/ffmpeg/BUILD.gn` has to be redone
  for Qt's GN setup, and the AAC library pre-loaded in every process.
- It would not satisfy the owner's wording as cleanly: the build would
  *contain* FFmpeg's H.264 / AAC decoder source in its FFmpeg configuration
  and depend on a list edit for their absence.

**The smaller Windows-only path** — what was implemented:

| Need | Smallest change in Chromium 140 | Lines |
|---|---|---|
| Formats known (MP4, `avc1`, `mp4a`), Annex B conversion | `proprietary_codecs=true`; FFmpeg stays `ffmpeg_branding="Chromium"`; assert in `media/BUILD.gn` relaxed for Windows | 4 |
| No OpenH264, no H.265 | `media_use_openh264=false`, `rtc_use_h264=false`, `enable_hevc_parser_and_hw_decoder=false`, Dolby Vision off | GN arguments |
| AAC decoded by Windows | `MediaFoundationAudioDecoder` (exists, runs in the process that hosts the media service, reached over Mojo) takes every AAC profile instead of xHE-AAC only; strips the ADTS header Media Source adds; creates the Windows AAC transform directly | ~110 |
| AAC in a plain MP4 file | `ffmpeg_common.cc`: a sample format for AAC although FFmpeg has no AAC decoder | ~15 |
| H.264 without a GPU decoder | new `MediaFoundationVideoDecoder` (software, renderer), last in `DefaultDecoderFactory` | ~560 |
| Renderer sandbox | load `mfplat.dll` and `msmpeg2vdec.dll` in `RendererMainPlatformDelegate::PlatformInitialize()` | ~130 |
| Honest `canPlayType` | `supported_types.cc`: H.264 / AAC only when Windows has the decoders; H.264 High 10 and above refused | ~50 |
| H.264 with a GPU | nothing: `D3D11VideoDecoder` is already there | 0 |

Why this is smaller than Vivaldi's: Qt WebEngine always runs Chromium's GPU
service inside the browser process, which has no sandbox, so the audio decoder
needs no pre-loading at all; and I.K.E. accepts that Web Audio's
`decodeAudioData` cannot decode AAC (it calls FFmpeg directly), which is the
one thing Vivaldi's FFmpeg-level decoder was built for.

Two findings while reading Chromium 140 that the earlier study missed [V]:

- `MediaFoundationAudioDecoder::PumpOutput` tests an `HRESULT` with `!`
  (`if (!ConfigureOutput())`), so a successful change of output format — what
  HE-AAC produces — is treated as a failure. Later Chromium has
  `FAILED(ConfigureOutput())`. Fixed in the patch.
- In Qt WebEngine the media service runs on the in-process GPU thread, where
  COM is not initialised (`content/gpu/in_process_gpu_thread.cc`; Chrome's
  separate GPU process initialises it in `gpu_main.cc`). The upstream way of
  creating the transform (`MFTEnumEx` + `IMFActivate::ActivateObject`) needs
  COM. The patch creates the AAC transform from its DLL instead, as Vivaldi
  does, and keeps the upstream way as the fallback.

Known limits of the smaller path [I]:

- Web Audio `decodeAudioData` with AAC, and bare `.aac` (ADTS) files: no.
- H.264 High 10 / 4:2:2 / 4:4:4: no (neither Windows decoder takes them).
- Software H.264 is decoded on the media thread and every picture is copied
  once; fine for ordinary video, not measured for 4K.
- Windows N without the Media Feature Pack: reported as not supported.
- WebRTC: H.264 only where the graphics driver decodes / encodes it.

## 4. Provenance of I.K.E.'s implementation

- `media/filters/win/media_foundation_video_decoder.{h,cc}` and
  `media/base/win/mf_decoder_libraries.{h,cc}` were written for I.K.E. against
  Chromium 140's interfaces (modelled on `FFmpegVideoDecoder` and
  `MediaFoundationAudioDecoder` for the Chromium side, on Microsoft's
  documentation of the H.264 decoder for the Media Foundation side).
- Taken from reading Vivaldi / Opera (ideas and facts, not text): creating the
  transform with `DllGetClassObject` from a pre-loaded system DLL; pre-loading
  in `PlatformInitialize()`; asking for YV12; that the picture buffer is
  padded to 16 rows. The last point is also how Firefox's
  `WMFVideoMFTManager` treats the same decoder. Where Vivaldi rounds blindly,
  I.K.E.'s decoder derives the layout from the buffer's real length and never
  reads past it.
- The audio change edits Chromium's own file (BSD, © The Chromium Authors)
  and backports two fixes from later Chromium.
- New files carry `SPDX-License-Identifier: BSD-3-Clause` — the licence of the
  code they are compiled into — so that the engine's licence situation does
  not change. The owner can choose otherwise.

## 5. Results

See `packaging/windows/qtwebengine/README.md` on branch `windows/engine` for
the state after the workflow runs; the short version is in the final report of
the session.

## Sources

- [S1] Vivaldi source archives: https://vivaldi.com/source/ (named in the
  mirror's README; not opened from the study environment)
- [S2] Mirror: https://github.com/ric2b/Vivaldi-browser — commit
  `c063c01f5717cfc7b8a03c6a992dabadc866fdc4` ("Added version 7.7.3851").
  Files read: `LICENSE`, `README`, `vivaldi_init_settings.gni`,
  `gn/config/BUILD.gn`, `gn/config/features.gni`, `chromium/chrome/VERSION`,
  everything under `platform_media/`, and in `chromium/`:
  `media/base/decoder.{h,cc}`, `media/renderers/default_decoder_factory.cc`,
  `media/BUILD.gn`, `media/ffmpeg/ffmpeg_common.cc`,
  `media/filters/ffmpeg_glue.cc`,
  `content/renderer/renderer_main_platform_delegate_win.cc`,
  `content/gpu/gpu_main.cc`, `content/utility/utility_main.cc`
- [S3] Vivaldi, "Vivaldi browser and open-source":
  https://vivaldi.com/?p=57361
- [S4] Qt's Chromium: https://github.com/qt/qtwebengine-chromium commit
  `e2b413ea3e2dc3c533335e12297abfda95b26cfa`; Qt WebEngine:
  https://github.com/qt/qtwebengine tag `v6.140.0`
  (`e081473af432e2b09d17caa3ca3bffd45992a0bd`)
- [S5] Upstream Chromium `main`,
  `media/filters/win/media_foundation_audio_decoder.cc`:
  https://raw.githubusercontent.com/chromium/chromium/main/media/filters/win/media_foundation_audio_decoder.cc
- [S6] Microsoft, H.264 Video Decoder and AAC Decoder (see `windows-codecs.md`
  [M2][M3])
- [S7] Qt online repository, layout for 6.12 (one folder per compiler):
  https://master.qt.io/online/qtsdkrepository/windows_x86/desktop/qt6_6120/qt6_6120_mingw/Updates.xml

Pages that could not be opened: `https://download.qt.io/online/qtsdkrepository/windows_x86/desktop/`
and `https://master.qt.io/online/qtsdkrepository/windows_x86/desktop/qt6_6120/`
(permission request not answered).
