# Windows H.264 / AAC through Media Foundation: existing open-source implementations

Study date: 2026-11-16/17. Follows `windows-codecs.md` and `platform-media.md`; does not repeat them.
**[V]** verified in source / primary page; **[I]** inferred; **[T]** to test on Windows. Nothing was built or run.

## Summary

1. Only **one** published open-source implementation does software H.264 through Windows' own decoder inside Chromium's media pipeline: **Vivaldi's `platform_media`** (Opera origin, BSD-3-Clause, GPL-3.0 compatible).
2. **Vivaldi 7.6.3797 is built on Chromium 140.0.7339.136** — the same Chromium branch as Qt WebEngine 6.140 (140.0.7339.264). Mirror commit `bb6a67c4a…`; tarball `https://source.vivaldi.com/vivaldi-source_7.6.3797.tar.xz`.
3. Every Chromium hook the Vivaldi **video** decoder needs applies cleanly (`git apply --check`) to Qt's `140-based` files; only the FFmpeg-audio hooks conflict with Qt's own edits. Ready diff: `vivaldi-7.6.3797-media-hooks.diff`.
4. Main porting work: Vivaldi uses its own GN fork (`update_target`) → rewrite as plain BUILD.gn edits; stub two Vivaldi-only headers. ~900 lines of foreign code + ~30 lines of hooks for video.
5. Vivaldi's **AAC** path is an FFmpeg-internal decoder and requires `ffmpeg_branding="Chrome"` (asserted) — conflicts with "no proprietary decoder shipped" unless proven out of the link; avoid it.
6. Best AAC source: **Cromite's patch** (GPL-2.0-or-later): lets Chromium's own `MediaFoundationAudioDecoder` take all AAC (ADTS). Its Windows hunks apply cleanly to Qt 140; in Cromite since 2024-03-06 (patch date) and still in its 153 release [V]; that spans roughly Chromium 122 → 153 [I]. Its H.264 is GPU-only.
7. Upstream Chromium has no clear-content software H.264 path; `MediaFoundationClearPlayback` is "for testing purposes" (still in `main` 160) and is compiled out in Qt.
8. Cobalt (Google, Apache-2.0) has a standalone MF H.264 + AAC decoder outside Chromium's pipeline (24.lts, removed later) — reference code only.
9. Rejected: Thorium, ungoogled-chromium-windows (ship Chrome-branded FFmpeg [V]); Brave, Electron codec forks (FFmpeg-based changes only [V]); Supermium, ungoogled-chromium, Chromium-for-windows-7-REWORK, CEF #3559 (no Media Foundation decoding code [V]); Opera (no public source).
10. **Recommendation**: fallback = Vivaldi 7.6 `WMFVideoDecoder` + `platform_media_init` (video) + Cromite's MF-audio patch (AAC) + the two Qt-specific fixes from `platform-media.md` §3 (HRESULT test, COM on the in-process GPU thread).

## Ranked candidates (where to get each one)

| # | Candidate | What it gives on Windows | Licence | Source location |
|---|---|---|---|---|
| 1 | **Vivaldi `platform_media`** (Opera origin) | software H.264 via `CLSID_CMSH264DecoderMFT` in renderer (`media::VideoDecoder`); AAC via Windows AAC MFT behind FFmpeg's codec API (covers Web Audio too); GPU H.264 stays Chromium's D3D11 | BSD-3-Clause (Opera file headers + `platform_media/OPERA_LICENSE.txt`; Vivaldi root `LICENSE`) — GPL-3.0 compatible | official: `https://vivaldi.com/source/` (tarballs); Git mirror `https://github.com/ric2b/Vivaldi-browser` (folder `platform_media/`, Chromium hooks under `chromium/`) — details in section 1 |
| 2 | **Cromite `Enable-platform-aac-audio-and-h264-video.patch`** | AAC via Chromium's own `MediaFoundationAudioDecoder` (all profiles, ADTS); H.264 **GPU only** (D3D11) — no software video | GPL-2.0-or-later (patch header) — compatible with GPL-3.0-or-later | `https://github.com/uazo/cromite/blob/master/build/patches/Enable-platform-aac-audio-and-h264-video.patch`; GN args in `build/cromite.gn_args` |
| 3 | Upstream Chromium `MediaFoundationRenderer` clear playback | whole pipeline handed to Windows Media Engine | BSD-3 (Chromium) | in tree; feature `kMediaFoundationClearPlayback`, "for testing purposes" — not a practical option in Qt WebEngine |
| 4 | Cobalt Starboard win32 MF decoders (Google) | H.264 (MFT, D3D11-aware) + AAC MFT, outside Chromium's media pipeline | Apache-2.0 — compatible with GPL-3 | `https://github.com/youtube/cobalt` branch `24.lts.1+`, `starboard/shared/win32/` (removed in current `main`) — reference only |

Not usable (FFmpeg-based, or no Windows MF decoding; evidence in "Rejected"): Thorium, Supermium, ungoogled-chromium(-windows), Brave, Chromium-for-windows-7-REWORK, CEF issue 3559 (no Windows code), Opera (no public source).

## Candidate 1 detail: Vivaldi `platform_media` — exact sources for Chromium 140

### Pick Vivaldi 7.6.3797: it is Chromium 140.0.7339.136 [V]

| Vivaldi | Chromium (`chromium/chrome/VERSION`) | Mirror commit (`ric2b/Vivaldi-browser`, branch `master`) | Official tarball |
|---|---|---|---|
| **7.6.3797** | **140.0.7339.136** — same major/branch as Qt's 140.0.7339.264 | `bb6a67c4a38211d36180421ee814367f8d274be4` ("Added version 7.6.3797") | `https://source.vivaldi.com/vivaldi-source_7.6.3797.tar.xz` (2190 MB, 2025-09-12) |
| 7.7.3851 | 142.0.7444.143 | `c063c01f5717cfc7b8a03c6a992dabadc866fdc4` (newest mirror commit, 2025-12-01) | `https://source.vivaldi.com/vivaldi-source_7.7.3851.tar.xz` |
| 8.3.4191 (newest) | not checked | not in mirror (mirror stops at 7.7) | `https://source.vivaldi.com/vivaldi-source_8.3.4191.tar.xz` (2026-10-28) |

- Official list: `https://vivaldi.com/source/` → links of the form `https://source.vivaldi.com/vivaldi-source_<version>.tar.xz`; the "Checksums" links are dead (`#`) [V, page read 2026-11-17]. `source.vivaldi.com` is **not reachable from this study environment** (proxy 403), so the tarballs were not downloaded; the GitHub mirror was used.
- Mirror tags stop at `7.1.3570`; versions 7.2–7.7 exist only as commits on `master` (all added 2025-12-01) [V, `git ls-remote`, `git log`]. Unofficial mirror: compare a file against the official tarball before shipping [I].
- `platform_media/` differs between 7.6 and 7.7 by **one line** (`wmf_video_decoder.cc`: `memcpy(buff_ptr, base::span(input).data(), …)`) [V, `git diff`]. So the 7.7 analysis in `platform-media.md` applies to 7.6 unchanged.
- Fetch for reading only `platform_media/` cheaply:
  `git clone --filter=blob:none --no-checkout https://github.com/ric2b/Vivaldi-browser && cd Vivaldi-browser && git sparse-checkout set --no-cone /platform_media/ /LICENSE /README /gn/config/ && git checkout bb6a67c4a38211d36180421ee814367f8d274be4`
  (a local partial clone already exists at `/home/claude/src/vivaldi`, at 7.7; `git show bb6a67c4a…:<path>` works there).

### Licence files [V]

- `platform_media/OPERA_LICENSE.txt` — BSD 3-clause, © 2013 Opera Software ASA (Windows decoder and sandbox helper headers: "original work developed by Opera Software ASA").
- `LICENSE` (repo root) — BSD 3-clause, © 2015 Vivaldi Technologies; root `README`: Vivaldi's original work "governed by a BSD-style license".
- `platform_media/ffmpeg/wmfaacdec.c` — © 2021 Vivaldi (root licence), but compiled **inside FFmpeg** and includes FFmpeg internal headers → the linked result is also under FFmpeg's LGPL-2.1+ (already the case for Chromium's FFmpeg) [I]. All GPL-3.0-or-later compatible.

### Windows files to take (paths in the Vivaldi tree, 7.6) [V]

| File | Lines | Role | Needed for |
|---|---|---|---|
| `platform_media/decoders/win/wmf_video_decoder.{h,cc}` | 70 + 512 | `media::VideoDecoder`, software H.264 through `CLSID_CMSH264DecoderMFT` from `msmpeg2vdec.dll`, renderer | video |
| `platform_media/decoders/vivaldi_decoder_config.{h,cc}` | ~45 | appends `WMFVideoDecoder` to the decoder list; includes `base/vivaldi_switches.h` (Vivaldi-only file → stub or drop) | video |
| `platform_media/decoders/platform_logging_util.*`, `debug_buffer_logger.*` | ~110 | logging helpers used by the decoder | video |
| `platform_media/sandbox/win/platform_media_init.{h,cc}` | 134 | pre-loads `mfplat.dll`, `msmpeg2vdec.dll`, `msauddecmft.dll` (Win8+; `msmpeg2adec.dll` before) before the sandbox; `InitForRendererProcess/GPUProcess/UtilityProcess` (utility: only sub-types like `audio.mojom.AudioService`) | both |
| `platform_media/ffmpeg/wmfaacdec.c` | 1105 | FFmpeg `AVCodec` `ffwmf_aac_decoder` over `CLSID_CMSAACDecMFT` (raw + ADTS) | audio, incl. Web Audio |
| `platform_media/ffmpeg/ffviv_audio_kit.{c,h}`, `ffviv_log.{cc,h}` | ~330 | helpers for the FFmpeg decoder; log redirection | audio |
| `platform_media/ffmpeg/BUILD.gn` | 100 | generates a patched `libavcodec/codec_list.c` (comments out `ff_h264_decoder`, replaces `ff_aac_decoder` by `ffwmf_aac_decoder`) and a redirected `libavutil/log.h`; **asserts `ffmpeg_branding == "Chrome"`** | audio |
| `platform_media/source_updates.gni` | 120 | injects all the above into `//media/renderers:renderers`, `//base:base`, `//third_party/ffmpeg:ffmpeg_internal` | build |
| `gn/config/features.gni`, `gn/config/BUILD.gn` | — | `system_proprietary_codecs = is_win || is_mac` → define `USE_SYSTEM_PROPRIETARY_CODECS`; include dirs `//vivaldi/`, `//vivaldi/platform_media/` | build |

### Hooks in Chromium 140 [V]

Saved as a ready-to-read diff: **`/home/claude/research/vivaldi-7.6.3797-media-hooks.diff`** (271 lines; Vivaldi 7.6 `chromium/<path>` vs `raw.githubusercontent.com/chromium/chromium/140.0.7339.136/<path>`). Files:
`content/gpu/gpu_main.cc` (InitForGPUProcess), `content/renderer/renderer_main_platform_delegate_win.cc` (InitForRendererProcess), `content/utility/utility_main.cc` (InitForUtilityProcess), `media/BUILD.gn` (assert relaxed with `is_vivaldi`), `media/base/decoder.{h,cc}` (`kVivWMFDecoder` = "WMFVideoDecoder"), `media/ffmpeg/ffmpeg_common.cc` and `media/filters/ffmpeg_glue.cc` (codec allow-list / strict mode off when `vivaldi::IsVivaldiRunning()`; `kStrictFFmpegCodecs`… default disabled), `media/renderers/default_decoder_factory.cc` (`VivaldiDecoderConfig::AddVideoDecoders`), `media/test/pipeline_integration_test_base.cc`.
Not covered: files outside `media/` and `content/{gpu,renderer,utility,app}` were not searched (partial clone) — a full `grep -r USE_SYSTEM_PROPRIETARY_CODECS` on the tarball is still to do [T].

**Dry run against Qt's tree [V]**: the hunks of that diff were checked with `git apply --check` against the same files from `qt/qtwebengine-chromium` branch `140-based` (`chromium/<path>`, fetched 2026-11-17):

- apply cleanly: `content/gpu/gpu_main.cc`, `content/renderer/renderer_main_platform_delegate_win.cc`, `content/utility/utility_main.cc`, `media/BUILD.gn`, `media/base/decoder.{h,cc}`, `media/renderers/default_decoder_factory.cc` — i.e. **every hook the video decoder needs**. `renderer_main_platform_delegate_win.cc`, `default_decoder_factory.cc`, `decoder.h` are byte-identical to upstream 140.0.7339.136, and Qt's `renderer_main.cc` calls `platform.PlatformInitialize()` (line 215).
- do not apply: `media/ffmpeg/ffmpeg_common.cc`, `media/filters/ffmpeg_glue.cc` (Qt adds `IS_QTWEBENGINE && USE_SYSTEM_FFMPEG` blocks there) and `media/test/pipeline_integration_test_base.cc` — only the FFmpeg-audio path and a test are affected; the hunks are small and can be redone by hand.

### Porting to qtwebengine-chromium `140-based` — what changes [I unless marked]

1. **GN extensions**: `update_target(...)` / `update_template_instance(...)` are **Vivaldi's own GN fork** (`https://github.com/vivaldi/Vivaldi-GN`, blog 2018-08-20 [V]); Qt uses stock GN. Rewrite `source_updates.gni` as direct edits of `media/renderers/BUILD.gn`, `base/BUILD.gn` (or better a small new `//media/platform_media` source_set), and `third_party/ffmpeg/BUILD.gn`.
2. **Vivaldi-only symbols**: `app/vivaldi_apptools.h` (`vivaldi::IsVivaldiRunning()`), `base/vivaldi_switches.h`, `is_vivaldi` → replace by a constant / own buildflag.
3. **Paths**: code expects `//vivaldi/platform_media/…` and include root `platform_media/…` → place at `src/3rdparty/chromium/platform_media/` (Qt layout) or rewrite includes.
4. **Video only (recommended minimum)**: `wmf_video_decoder.*`, `vivaldi_decoder_config.*`, logging helpers, `platform_media_init.*`, hooks in `decoder.{h,cc}`, `default_decoder_factory.cc`, `renderer_main_platform_delegate_win.cc`. No FFmpeg change. Keeps `ffmpeg_branding="Chromium"`. ~900 lines of foreign code + ~30 lines of hooks.
5. **Audio the Vivaldi way** needs `ffmpeg_branding="Chrome"` (asserted), i.e. FFmpeg's H.264/AAC decoder *sources* in the build config, removed only from `codec_list.c` → conflicts with the owner's "no proprietary decoder shipped" unless the link map proves `ff_h264_decoder`/`ff_aac_decoder` objects are absent (the H.264 *parser* stays) [I][T]. Cheaper: take AAC from Cromite (candidate 2) or I.K.E.'s own MF-audio patch instead.
6. Qt specifics already known (platform-media.md §3): GPU service in-process (COM not initialised there; GPU pre-load hook irrelevant), `--in-process-gpu`; Qt's `content/app` startup differs, but `RendererMainPlatformDelegate::PlatformInitialize()` is used by Qt's renderer too [I].

## Candidate 2 detail: Cromite [V]

- File: `build/patches/Enable-platform-aac-audio-and-h264-video.patch` in `uazo/cromite`, clone at commit `3724efc6` (2026-09-19); `build/RELEASE` = 153.0.8010.37.
- Patch header: author uazo, dated 2024-03-06, "License: GPL-2.0-or-later", context PR #856 ("Enable platform aac hevc", fixes #710). 11 files, +70 / −1. Still in `build/cromite_patches_list.txt` (line 253) in 2026 → maintained across ~30 Chromium releases [I].
- Licence consequence [I]: the patched Chromium files become GPL-2.0-or-later as distributed; fine for I.K.E. (GPL-3.0-or-later) and for Qt WebEngine's LGPL-3/GPL-2+/GPL-3 terms when combined into a GPL-3 product, but the engine build is then no longer BSD/LGPL-only. The Windows hunks are ~25 lines of obvious changes; re-writing them independently (as I.K.E.'s own audio patch already does) avoids the question.
- Windows part:
  - `media/filters/win/media_foundation_audio_decoder.cc`: `GetTypeInfo` returns `MFAudioFormat_AAC` for every AAC profile; `NeedsBitstreamConversion()` true for AAC (stream converted to ADTS).
  - `media/base/win/mf_helpers.cc`: `wPayloadType = 1` (ADTS) instead of 0 (raw).
  - `media/filters/ffmpeg_audio_decoder.cc`: refuses AAC → the Mojo MF decoder is used.
  - `media/filters/ffmpeg_video_decoder.cc`: refuses H.264 / HEVC.
  - `media/gpu/windows/supported_profile_helpers.cc`: D3D11 H.264 max 4096x2304, High10/422/444 advertised "so that play is still attempted".
  - `media/media_options.gni`, `media/BUILD.gn`: new args `enable_platform_aac_audio`, `enable_platform_h264_video` + buildflags.
- H.264: **GPU only** (D3D11VideoDecoder); no software MFT. Its comment says so: "Enables h264 video decoder using only ... D3D11VideoDecoder in Windows".
- Build: `cromite.gn_args` keeps `ffmpeg_branding="Chrome"` (lines 29–30) → FFmpeg H.264/AAC decoders are still compiled into Cromite and only refused at run time. For I.K.E. use with `ffmpeg_branding="Chromium"`.
- Not covered by the patch for a Chromium-branded FFmpeg: `<video src=x.mp4>` AAC sample-format fix (`ffmpeg_common.cc`, see windows-codecs.md 1c), and the in-process-GPU COM issue (platform-media.md §3) [I].
- PR discussion: tested on Android ("AVD or physical device"); no Windows test listed [V, PR page]. A reviewer objected that `ffmpeg_branding="Chrome"` "will still ship codecs" and that `ffmpeg_branding="Chromium"` was "unsuccessful" for him; the author answered the flags are needed for Chromium code paths [V, PR page]. So Cromite + Chromium-branded FFmpeg is **untested by anyone** [I][T].
- **Dry run on Qt `140-based` [V]**: hunks for `media/base/win/mf_helpers.cc`, `media/filters/ffmpeg_audio_decoder.cc`, `ffmpeg_demuxer.cc`, `ffmpeg_video_decoder.cc`, `media/filters/win/media_foundation_audio_decoder.cc`, `media/gpu/windows/supported_profile_helpers.cc` apply cleanly; `media/BUILD.gn` and `media/media_options.gni` fail on context only (re-add 2 + 8 lines by hand); Android files irrelevant.
- Missing for Qt [I, from platform-media.md §3]: the `if (!ConfigureOutput())` HRESULT bug in 140's `PumpOutput` (HE-AAC output-type change), and COM not initialised on Qt's in-process GPU thread (upstream `MFTEnumEx` path). Also `supported_types.cc` honesty (windows-codecs.md §6 step 4) and the AAC sample-format fix in `ffmpeg_common.cc`.
- Recommended use: take only the Windows hunks, drop the H.264 profile/resolution widening (it makes `canPlayType` claim High10/4:4:4 which nothing decodes).

## Candidate 3: upstream Chromium `MediaFoundationRenderer` for clear content [V]

- Chromium `main` (160.0.8167.0, 2026-11-16) `media/base/media_switches.cc`: "Enables the use of MediaFoundationRenderer for clear content on supported systems. This is for testing purposes, and is not intended to be enabled more broadly." `kMediaFoundationClearPlayback` = `FEATURE_DISABLED_BY_DEFAULT`.
- In Qt 140 the renderer factory code is behind `IS_WIN && ENABLE_WEB_SPEECH` and Qt builds `enable_web_speech=false` (windows-codecs.md §1b); it also renders through DirectComposition, which Qt does not use [I].
- `MediaFoundationAudioDecoder` in `main` still accepts AAC only for xHE-AAC on Windows 11 22H2+ (lines 102–104) — no upstream AAC-LC change exists.
- Verdict: not a fallback.

## Candidate 4: Cobalt Starboard win32 (reference only) [V]

- `https://github.com/youtube/cobalt`, branch `24.lts.1+` (commit `880712a1`, 2026-10-13), `starboard/shared/win32/`: `video_decoder.cc` (830 lines; `CLSID_MSH264DecoderMFT`, D3D11-aware, can switch DXVA off via `CODECAPI_AVDecVideoAcceleration_H264`), `win32_audio_decoder.cc` (254), `media_transform.cc` (392), `media_foundation_utils.cc`, `audio_decoder.cc`, `decrypting_decoder.cc`. Licence: Apache-2.0 per file header (one-way compatible with GPL-3.0).
- Not a `media::VideoDecoder`; written against Starboard's player API. In `main` (2026-11-16) `starboard/shared/win32/` holds only `posix_emu` — removed.
- Use: second opinion on MFT handling (output-type changes, DXVA on/off), not integration.

## Rejected, with the evidence

| Project | Why not | Evidence |
|---|---|---|
| Thorium | `win_args.gn`: `proprietary_codecs=true`, `ffmpeg_branding="Chrome"`, `enable_ffmpeg_video_decoders=true`, `rtc_use_h264=true` → ships FFmpeg H.264/AAC | [V] clone `Alex313031/thorium` 2026-11-13 |
| ungoogled-chromium-windows | `flags.windows.gn`: `ffmpeg_branding="Chrome"`, `proprietary_codecs=true` | [V] clone 2026-11-13 (157.0.8103.78) |
| ungoogled-chromium | no Media Foundation decoder patch (grep) | [V] |
| Brave | patches only FFmpeg (adds HEVC to FFmpeg list), FFmpeg-based | [V] `brave-core/patches/media-*`, `third_party/ffmpeg/*` |
| Supermium (v144 tree, patch repo) | no DXVA / MF software decoder; `media/filters/win` holds only Chromium's audio decoder | [V] tree listing |
| Chromium-for-windows-7-REWORK (`e3kskoy7wqk`) | Win7 reverts only (D3D11 decoder, core audio, capture); no MF software decoding | [V] diffs in `chromium-140.0.7339.264/` |
| CEF issue #3559 "Enable proprietary codecs with hardware OS decoding support only" | open discussion; only a macOS AudioToolbox FFmpeg experiment by the CEF maintainer, which still failed; no Windows code | [V] issue page |
| Electron: `5rahim/electron-media-patch`, `Muril-o/electron-chromium-codecs` | patch Chromium's FFmpeg for HEVC/AC3; no Media Foundation | [V] READMEs |
| Opera | "Opera is not open source"; open parts at `github.com/operasoftware`; no `platform_media` published | [V] Opera forum (moderator, 2018) + searches |
| Old Chromium `media/mf/h264mft.cc` (2010, BSD, `CMSH264DecoderMFT`, NV12, optional DXVA) | historic; 15 years of API drift | [V] googlesource page |
| Qt bug tracker | no report or patch for OS decoders found; QTBUG-86092 is about MSVC + H.264 | [V] |

## How to integrate the recommended fallback (order of work) [I]

1. Copy from Vivaldi 7.6 (`bb6a67c4a…`): `platform_media/decoders/win/wmf_video_decoder.{h,cc}`, `platform_media/decoders/{vivaldi_decoder_config,platform_logging_util,debug_buffer_logger}.{h,cc}`, `platform_media/sandbox/win/platform_media_init.{h,cc}`, `platform_media/OPERA_LICENSE.txt`, Vivaldi root `LICENSE` (as `LICENSE.vivaldi`). Keep all headers.
2. Apply the hunks of `vivaldi-7.6.3797-media-hooks.diff` for `decoder.{h,cc}`, `default_decoder_factory.cc`, `renderer_main_platform_delegate_win.cc` (and `utility_main.cc` only if audio pre-load is wanted); replace `defined(USE_SYSTEM_PROPRIETARY_CODECS)` by an I.K.E. define; remove `#include "base/vivaldi_switches.h"`.
3. Write a plain GN `source_set` for those files (deps `//base`, `//media/base`, `//media/base/win:media_foundation_util`; libs as in Vivaldi's `source_updates.gni`: `d3d9.lib dxva2.lib strmiids.lib mf.lib mfreadwrite.lib mfuuid.lib Propsys.lib`) and depend on it from `//media/renderers`; `platform_media_init` must be linkable from `content/renderer` (Vivaldi puts it in `//base`).
4. AAC: apply the Windows hunks of Cromite's patch, plus the HRESULT and COM fixes, `ffmpeg_branding="Chromium"`.
5. Test on Windows: `chrome://media-internals` must show `WMFVideoDecoder` with `--disable-gpu`/`--disable-accelerated-video-decode`, and `MediaFoundationAudioDecoder` (via Mojo) for AAC.

## Sources

Vivaldi / Opera
- Vivaldi source archives (list): https://vivaldi.com/source/ ; 7.6 tarball https://source.vivaldi.com/vivaldi-source_7.6.3797.tar.xz (not downloadable from the study environment)
- Mirror: https://github.com/ric2b/Vivaldi-browser — commits `bb6a67c4a38211d36180421ee814367f8d274be4` (7.6.3797, `chromium/chrome/VERSION` = 140.0.7339.136) and `c063c01f5717cfc7b8a03c6a992dabadc866fdc4` (7.7.3851, 142.0.7444.143); files read: `platform_media/**`, `gn/config/{features.gni,BUILD.gn}`, `README`, `LICENSE`, `platform_media/OPERA_LICENSE.txt`, hook files listed in section "Hooks"
- Vivaldi GN extensions: https://vivaldi.com/?p=28328 (2018-08-20) → https://github.com/vivaldi/Vivaldi-GN
- Opera: https://forums.opera.com/post/154216 ; https://github.com/operasoftware

Chromium / Qt
- Upstream 140.0.7339.136 files: https://raw.githubusercontent.com/chromium/chromium/140.0.7339.136/<path>
- Upstream main (160.0.8167.0): https://github.com/chromium/chromium/blob/main/media/base/media_switches.cc ; https://github.com/chromium/chromium/blob/main/media/filters/win/media_foundation_audio_decoder.cc ; https://github.com/chromium/chromium/blob/main/content/renderer/media/media_factory.cc
- Qt's Chromium 140: https://github.com/qt/qtwebengine-chromium/tree/140-based/chromium (files used for the `git apply --check` runs)
- Old Chromium H.264 MFT wrapper: https://chromium.googlesource.com/chromium/chromium/+/d3f4c0027364e81fad704fbca8cce4940140a9ac/media/mf/h264mft.cc

Cromite
- Patch: https://github.com/uazo/cromite/blob/master/build/patches/Enable-platform-aac-audio-and-h264-video.patch ; args https://github.com/uazo/cromite/blob/master/build/cromite.gn_args ; licence statement https://github.com/uazo/cromite/blob/master/README.md#license ; PR https://github.com/uazo/cromite/pull/856 (clone commit `3724efc6`, 2026-09-19)

Others
- CEF: https://github.com/chromiumembedded/cef/issues/3559
- Cobalt: https://github.com/youtube/cobalt/tree/24.lts.1%2B/starboard/shared/win32 (commit `880712a1`)
- Thorium https://github.com/Alex313031/thorium/blob/main/win_args.gn ; ungoogled-chromium-windows https://github.com/ungoogled-software/ungoogled-chromium-windows/blob/master/flags.windows.gn ; brave-core https://github.com/brave/brave-core/tree/master/patches ; Supermium https://github.com/win32ss/supermium (branch v144) ; https://github.com/e3kskoy7wqk/Chromium-for-windows-7-REWORK
- Electron: https://github.com/5rahim/electron-media-patch ; https://github.com/Muril-o/electron-chromium-codecs
- Qt: https://bugreports-test.qt.io/browse/QTBUG-86092

Not reachable / not done: `source.vivaldi.com` (proxy 403); GitHub REST API for these repos (session not authorised), so Cromite's full patch history was not listed; a full-tree grep of Vivaldi 7.6 for `USE_SYSTEM_PROPRIETARY_CODECS` outside `media/` and `content/`.

Local copies: Vivaldi partial clone `/home/claude/src/vivaldi` (7.7; 7.6 objects fetched); clones under `/home/claude/research/src/` (`uazo_cromite`, `cobalt_24lts`, `win7rework`, `viv_commits.git` = commit list only, plus earlier ones).
