# Patches for Qt WebEngine on Windows

For Qt WebEngine **6.140.0** (tag `v6.140.0`), which contains Chromium
**140.0.7339.264** (`qt/qtwebengine-chromium`, commit `e2b413ea`). The exact
commits are pinned in `../versions.json`; the patches apply to those and to
nothing else without being looked at again.

What they do, in one sentence: the engine knows MP4, H.264 and AAC and hands
the decoding to the decoders that are part of Windows (Media Foundation); it
contains no H.264 / AAC decoder or encoder of its own.

## How they are applied

`../build.py patch` applies `qtwebengine/*.patch` in the root of the
qtwebengine checkout and `chromium/*.patch` in `src/3rdparty`, with
`git apply`, in file-name order.

## GN arguments

Set by `qtwebengine/0001` when Qt WebEngine is configured with
`-DFEATURE_webengine_proprietary_codecs=ON`:

| Argument | Value | Why |
|---|---|---|
| `proprietary_codecs` | `true` | the engine recognises MP4, `avc1`, `mp4a`, and converts H.264 to the form a decoder wants |
| `ffmpeg_branding` | `"Chromium"` | FFmpeg is built with its free codecs only: no H.264 decoder, no AAC decoder, not even their parsers |
| `media_use_openh264` | `false` | no OpenH264 encoder in the media code |
| `rtc_use_h264` | `false` | no OpenH264 encoder and no FFmpeg H.264 decoder in WebRTC |
| `enable_hevc_parser_and_hw_decoder` | `false` | H.265 was not asked for; leaves its parser out |
| `enable_platform_dolby_vision`, `enable_platform_encrypted_dolby_vision` | `false` | required by Chromium when H.265 is off |

Qt's switch as Qt ships it sets `ffmpeg_branding="Chrome"` and
`rtc_use_h264=true`, which builds FFmpeg's H.264 and AAC decoders into the
engine. That is what `qtwebengine/0001` removes.

## The patches

| Patch | What it changes |
|---|---|
| `qtwebengine/0001-gn-args-windows-decoders` | `src/core/CMakeLists.txt`: the GN arguments above |
| `chromium/0001-build-proprietary-formats-with-free-ffmpeg` | `media/BUILD.gn`: Chromium refuses `proprietary_codecs=true` together with `ffmpeg_branding="Chromium"`; allowed on Windows |
| `chromium/0002-media-windows-decoder-libraries` | new `media/base/win/mf_decoder_libraries.{h,cc}`: finds `mfplat.dll`, `msmpeg2vdec.dll` (H.264) and `msauddecmft.dll` (AAC) in the system directory. The renderer loads the first two when it starts (`content/renderer/renderer_main_platform_delegate_win.cc`), because nothing can be loaded once its sandbox is closed |
| `chromium/0003-media-h264-windows-software-decoder` | new `media/filters/win/media_foundation_video_decoder.{h,cc}`: a `media::VideoDecoder` that drives the H.264 Media Foundation transform of Windows in software. Added as the last entry of the default decoder list (`media/renderers/default_decoder_factory.cc`), with its own decoder type and name (`media/base/decoder.{h,cc}`) |
| `chromium/0004-media-aac-windows-decoder` | `media/filters/win/media_foundation_audio_decoder.{h,cc}`: Chromium's existing Media Foundation audio decoder takes every AAC profile (upstream: xHE-AAC only), creates the Windows AAC transform directly, strips the ADTS header that Media Source adds, and gets two fixes from later Chromium versions. `media/ffmpeg/ffmpeg_common.cc`: AAC from a plain MP4 file gets a sample format although FFmpeg has no AAC decoder |
| `chromium/0005-media-supported-types-windows` | `media/base/supported_types.cc`: `canPlayType` / `isTypeSupported` say yes to H.264 and AAC only when Windows has the decoders, and no to the H.264 profiles no Windows decoder takes (High 10 and above) |

## Who decodes what

| Stream | Decoder | Where it runs |
|---|---|---|
| H.264, graphics driver can decode it | Chromium's `D3D11VideoDecoder` (unchanged; Direct3D 11 video decoding by the driver) | GPU service |
| H.264 otherwise (no usable driver decoder, software rendering, virtual machine), and video smaller than 360 lines, for which Chromium prefers software | `MediaFoundationVideoDecoder` → `CLSID_CMSH264DecoderMFT` in `msmpeg2vdec.dll` | renderer, inside its sandbox |
| AAC-LC, HE-AAC | `MediaFoundationAudioDecoder` → `CLSID_CMSAACDecMFT` in `msauddecmft.dll` | GPU service (in Qt WebEngine: the browser process) |
| VP8, VP9, AV1, Opus, Vorbis, FLAC, MP3 | as before: libvpx, dav1d, FFmpeg's free codecs | renderer |

Chromium's own demuxers stay: FFmpeg's MP4 demuxer for files, Chromium's
`MP4StreamParser` for Media Source.

## Known limits

- Web Audio's `decodeAudioData()` cannot decode AAC: it calls FFmpeg directly.
- Bare `.aac` (ADTS) files do not play: FFmpeg's ADTS demuxer is not built.
- H.264 High 10, 4:2:2, 4:4:4: not supported, and reported as such.
- Windows N editions need Microsoft's Media Feature Pack; without it H.264 and
  AAC are reported as not supported.
- WebRTC has H.264 only where the graphics driver provides it.
- The software H.264 decoder works on the media thread and copies each
  picture once. Not measured above 1080p.

## Provenance and licence

- `media_foundation_video_decoder.*` and `mf_decoder_libraries.*` were written
  for I.K.E. They are marked `SPDX-License-Identifier: BSD-3-Clause`, the
  licence of the Chromium code they are compiled into, so the licence of the
  engine as a whole does not change.
- The approach — a `media::VideoDecoder` over the Windows H.264 transform,
  created with `DllGetClassObject` from a system library that is loaded before
  the sandbox closes — is the one of the `platform_media` code of Opera and
  Vivaldi ("an original work developed by Opera Software ASA", BSD 3-clause,
  published in Vivaldi's source archives at <https://vivaldi.com/source/>).
  No source text was copied from it.
- The changes to `media_foundation_audio_decoder.*`, `ffmpeg_common.cc`,
  `supported_types.cc` and the other existing files are edits of Chromium's
  code (BSD-style licence, © The Chromium Authors). Two of them are fixes
  taken from later Chromium versions: `FAILED(ConfigureOutput())` in
  `PumpOutput()`, and not asking for a sample for an empty buffer.
- Every I.K.E. change inside an existing file is marked with a comment that
  starts `I.K.E.:`.

Nothing here is legal advice. Whether a build with these patches needs a
patent licence is the open question written down in `docs/platforms/`.

## Regenerating for a new Qt WebEngine

Check out the new tag and its Chromium commit, apply the patches (`git apply
--3way` helps), build, run the workflow's codec check, then write the patches
again with `git diff` per group of files and update `../versions.json`.
