# Patches for Qt WebEngine on Windows

For Qt WebEngine **6.140.0** (tag `v6.140.0`), which contains Chromium
**140.0.7339.264** (`qt/qtwebengine-chromium`, commit `e2b413ea`). The exact
commits are pinned in `../versions.json`; the patches apply to those and to
nothing else without being looked at again.

What they do, in one sentence: the engine knows MP4, H.264 and AAC and hands
the decoding to the decoders that are part of Windows (Media Foundation); it
contains no H.264 / AAC decoder or encoder of its own.

Since 2026-11-17 the code that does this is **not I.K.E.'s own**: it is
integrated from two open-source browsers (the owner's decision). I.K.E.'s
earlier own implementation is kept in `superseded/own-adapter/`, unused.

## Where the code comes from

| Part | From | Licence |
|---|---|---|
| H.264 in software: `WMFVideoDecoder`, `platform_media_init`, hooks | **Vivaldi 7.6.3797** `platform_media` (Chromium 140.0.7339.136, the same Chromium branch as Qt WebEngine 6.140), "an original work developed by Opera Software ASA"; mirror `ric2b/Vivaldi-browser` commit `bb6a67c4a38211d36180421ee814367f8d274be4` | BSD 3-clause (© Opera Software ASA, © Vivaldi Technologies AS); both licence texts are in patch `chromium/0002` |
| AAC: Chromium's `MediaFoundationAudioDecoder` for every AAC profile | **Cromite** `build/patches/Enable-platform-aac-audio-and-h264-video.patch`, Windows AAC hunks; `uazo/cromite` commit `3724efc6` | GPL-2.0-or-later (stated in the patch header, repeated in `chromium/0003`) |
| H.264 by the graphics driver | nothing added: Chromium's `D3D11VideoDecoder`, switched on by `proprietary_codecs=true` | Chromium's |
| Glue for Qt WebEngine and for FFmpeg without AAC | written for I.K.E. (`chromium/0001`, `chromium/0004`, `qtwebengine/0001`) | that of the file changed |

`THIRD-PARTY-NOTICES.md` has the notices in the form that goes into the built
engine (`LICENSES/` in the zip); `chromium/platform_media/README.ike.md`
(inside patch 0002) lists Vivaldi's files with their checksums and I.K.E.'s
three small changes to them.

Licence consequence (not legal advice): with Cromite's GPL-2.0-or-later part
the built engine is a GPL work; it is distributed under GPL-3.0-or-later, the
licence of I.K.E. Its complete source is the pinned upstream commits plus
this folder.

## How they are applied

`../build.py patch` applies `qtwebengine/*.patch` in the root of the
qtwebengine checkout and `chromium/*.patch` in `src/3rdparty`, with
`git apply`, in file-name order. `superseded/` is not applied.

## GN arguments

Set by `qtwebengine/0001` when Qt WebEngine is configured with
`-DFEATURE_webengine_proprietary_codecs=ON`:

| Argument | Value | Why |
|---|---|---|
| `proprietary_codecs` | `true` | the engine recognises MP4, `avc1`, `mp4a`, and converts H.264 to the form a decoder wants |
| `ffmpeg_branding` | `"Chromium"` | FFmpeg is built with its free codecs only: no H.264 decoder, no AAC decoder, not even their parsers |
| `media_use_openh264` | `false` | no OpenH264 encoder in the media code |
| `rtc_use_h264` | `false` | no OpenH264 encoder and no FFmpeg H.264 decoder in WebRTC |
| `enable_platform_aac_audio` | `true` | Cromite's switch: AAC goes to `MediaFoundationAudioDecoder` |
| `enable_hevc_parser_and_hw_decoder` | `false` | H.265 was not asked for; leaves its parser out |
| `enable_platform_dolby_vision`, `enable_platform_encrypted_dolby_vision` | `false` | required by Chromium when H.265 is off |

Qt's switch as Qt ships it sets `ffmpeg_branding="Chrome"` and
`rtc_use_h264=true`, which builds FFmpeg's H.264 and AAC decoders into the
engine. That is what `qtwebengine/0001` removes. Vivaldi and Cromite both
build with `ffmpeg_branding="Chrome"` themselves; I.K.E. does not, which is
why patch 0004 exists.

## The patches

| Patch | Origin | What it changes |
|---|---|---|
| `qtwebengine/0001-gn-args-windows-decoders` | I.K.E. | `src/core/CMakeLists.txt`: the GN arguments above |
| `chromium/0001-build-proprietary-formats-with-free-ffmpeg` | I.K.E. | `media/BUILD.gn`: Chromium refuses `proprietary_codecs=true` together with `ffmpeg_branding="Chromium"`; allowed on Windows |
| `chromium/0002-vivaldi-platform-media-h264-windows` | Vivaldi / Opera | new `platform_media/` (10 source files, 2 licence texts, a provenance note); `media/base/decoder.{h,cc}`: decoder type `kVivWMFDecoder`, name `WMFVideoDecoder`; `media/renderers/default_decoder_factory.cc`: the decoder is added after Chromium's own; `content/renderer/renderer_main_platform_delegate_win.cc`: the renderer loads `mfplat.dll`, `msmpeg2vdec.dll` and `msauddecmft.dll` before its sandbox closes; `media/renderers/BUILD.gn`, `media/base/BUILD.gn`: the files and libraries Vivaldi's own GN file adds |
| `chromium/0003-cromite-platform-aac-audio-windows` | Cromite | `media/media_options.gni`, `media/BUILD.gn`: argument and build flag `enable_platform_aac_audio`; `media/filters/win/media_foundation_audio_decoder.cc`: every AAC profile, ADTS input; `media/base/win/mf_helpers.cc`: payload type ADTS; `media/filters/ffmpeg_audio_decoder.cc`: refuses AAC; `media/filters/ffmpeg_demuxer.cc`: a comment |
| `chromium/0004-qt-and-free-ffmpeg-fixes` | I.K.E. | `content/gpu/in_process_gpu_thread.cc`: COM on Qt's in-process GPU thread; `media_foundation_audio_decoder.cc`: `FAILED(ConfigureOutput())` (fix from later Chromium); `media/ffmpeg/ffmpeg_common.cc`: a sample format for AAC without an FFmpeg decoder; `media/filters/ffmpeg_demuxer.cc`: the AAC profile for the ADTS header from the AudioSpecificConfig |

Left out of Vivaldi's `platform_media` on purpose: its AAC decoder inside
FFmpeg (`ffmpeg/wmfaacdec.c`), because it needs `ffmpeg_branding="Chrome"`;
the start-up hooks for the GPU and utility processes, which serve that
decoder; everything for macOS and Linux. Left out of Cromite's patch: Android,
and its H.264 part (it only refuses FFmpeg's H.264 decoder, which this build
does not have, and announces H.264 profiles no Windows decoder takes).

## Who decodes what

| Stream | Decoder | Where it runs |
|---|---|---|
| H.264, graphics driver can decode it | Chromium's `D3D11VideoDecoder` (unchanged; Direct3D 11 video decoding by the driver) | GPU service |
| H.264 otherwise (no usable driver decoder, software rendering, virtual machine), and video smaller than 360 lines, for which Chromium prefers software | Vivaldi's `WMFVideoDecoder` → `CLSID_CMSH264DecoderMFT` in `msmpeg2vdec.dll` | renderer, inside its sandbox |
| AAC-LC, HE-AAC | `MediaFoundationAudioDecoder` → the Windows AAC decoder, found through Media Foundation (`MFTEnumEx`) | GPU service (in Qt WebEngine: the browser process) |
| VP8, VP9, AV1, Opus, Vorbis, FLAC, MP3 | as before: libvpx, dav1d, FFmpeg's free codecs | renderer |

Chromium's own demuxers stay: FFmpeg's MP4 demuxer for files, Chromium's
`MP4StreamParser` for Media Source. `FFmpegVideoDecoder` is still in the
decoder list in front of `WMFVideoDecoder` and fails for H.264 because FFmpeg
has no H.264 decoder — the same order as in Vivaldi.

## Known limits

- Web Audio's `decodeAudioData()` cannot decode AAC: it calls FFmpeg directly
  (this is what Vivaldi's FFmpeg-level AAC decoder is for).
- Bare `.aac` (ADTS) files do not play: FFmpeg's ADTS demuxer is not built.
- `canPlayType` says yes to H.264 and AAC without asking Windows (as in
  Vivaldi and Cromite): on a Windows N edition without the Media Feature
  Pack, and for H.264 High 10 / 4:2:2 / 4:4:4, the answer is yes and playback
  then fails. `superseded/own-adapter/chromium/0005` shows how to make the
  answer exact.
- `WMFVideoDecoder` decodes on the media thread and copies each picture once
  (Vivaldi's design). Not measured above 1080p.
- WebRTC has H.264 only where the graphics driver provides it.
- `platform_media_init` loads the three libraries by bare name
  (`LoadLibrary`), as in Vivaldi, in every renderer process.

## `superseded/own-adapter/`

I.K.E.'s first implementation (2026-11-16): its own `MediaFoundationVideoDecoder`,
its own library loader and its own change of `MediaFoundationAudioDecoder`
(bare AAC frames), all written for I.K.E. and marked BSD-3-Clause. Its media
code compiled on the runner (run 43968550111, stage 1); it was never linked
or played. Replaced on the owner's decision to integrate existing code
instead of maintaining an adapter. Kept for reference only; `build.py` does
not read this folder.

## Regenerating for a new Qt WebEngine

Check out the new tag and its Chromium commit, apply the patches (`git apply
--3way` helps), build, run the workflow's codec check, then write the patches
again with `git diff` — one commit per patch — and update `../versions.json`.
For a new Chromium major version take `platform_media/` from the Vivaldi
release built on that Chromium version (<https://vivaldi.com/source/>) and
compare Cromite's patch again; update the checksums in
`chromium/platform_media/README.ike.md`.

Nothing here is legal advice. Whether a build with these patches needs a
patent licence is the open question written down in `docs/platforms/`.
