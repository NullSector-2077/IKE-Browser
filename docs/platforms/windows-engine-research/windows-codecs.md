# Windows: H.264 / AAC through the decoders of Windows, with Qt WebEngine

Study date: 2026-11-16. Nothing here was built or run on Windows.

## Summary

- **Build switches alone do not meet the requirement.** `proprietary_codecs=true` + `ffmpeg_branding="Chromium"` makes the engine *say* H.264 and AAC are supported, but only H.264 **video** then decodes (GPU, D3D11); **AAC-LC has no decoder at all**, so an ordinary MP4 (H.264 + AAC) fails.
- Chromium's Media Foundation audio decoder exists and is on by default, but accepts only **xHE-AAC on Windows 11 22H2+**. A patch of about ten lines would let it take all AAC. Not upstream, not tested.
- H.264 is decoded only by `D3D11VideoDecoder`: needs a GPU with H.264 decode and a driver that is not blocklisted. **No software fallback exists** in Chromium (140 to 160), and Qt compiles `MediaFoundationRenderer` out.
- Firefox-like behaviour (software H.264 through the Windows MFT) needs a larger patch. A working BSD-licensed precedent exists: Vivaldi / Opera `platform_media`.
- So: **achievable only with I.K.E.'s own Chromium patches on top of Qt WebEngine**, rebuilt for every engine release. Partially (GPU-only video) with ~40 lines; fully with several hundred.
- Building Qt WebEngine on free GitHub runners (4 vCPU, 6 h per job) needs a chained, resumable build; only `qtwebengine` has to be built, against the official Qt 6.12 binaries. PyQt bindings need no rebuild (inferred).
- Legal note: the build contains no H.264 / AAC sample decoder, but does contain H.264 parsing and picture-buffer code. Mozilla declined to ship comparable code. Ask someone qualified.

## 0. How to read this

- **[V]** verified by reading the source or the documentation named.
- **[I]** inferred from those; not observed running.
- **[T]** to test on a real Windows system before relying on it.
- `chromium.googlesource.com`, `source.chromium.org` and `code.qt.io` were not reachable from the study environment. Source was read from the official GitHub mirrors: `qt/qtwebengine` (branch `6.140`, commit `8eadc324`; branch `6.11`, commit `d2640b7c`) and `qt/qtwebengine-chromium` (branch `140-based`, commit `871c3567`, which is exactly the submodule commit of `qtwebengine` 6.140) [Q1][C0]. Upstream Chromium was compared on `chromium/chromium` `main` (160.0.8167.0) [U1].
- Line numbers refer to those commits.
- Pages that could not be opened are listed at the end.

## 1. Which Chromium

| Qt WebEngine | Based on Chromium | Security patches up to | Source |
|---|---|---|---|
| 6.10 (branch, 6.10.3) | 134.0.6998.208 | 146.0.7680.177 | [V] `CHROMIUM_VERSION` [Q2] |
| 6.11 (branch, 6.11.3) | 140.0.7339.264 | 155.0.8059.85 | [V] [Q2] |
| 6.12 (branch) | 140.0.7339.264 | 151.0.7922.108 | [V] [Q2] |
| **6.140** (branch, tag `v6.140.0`) | 140.0.7339.264 | 157.0.8103.50 | [V] [Q2] |

- From Qt 6.12, Qt WebEngine is released separately and numbered after its Chromium base: 6.140 = Chromium 140. Qt 6.12.0 ships without Qt WebEngine binaries [V][Q3][Q4].
- A Qt WebEngine release can be built against an older Qt; the Qt used sets the minimum Qt it runs on [V][Q3].
- A move to a newer Chromium is announced, which raises compiler requirements and **requires Rust** [V][Q3]. Branches `146-based` and `152-based` already exist in Qt's Chromium fork [V][C0].
- PyPI on the study date: `PyQt6` 6.12.1, `PyQt6-Qt6` 6.12.0, `PyQt6-WebEngine` 6.140.1 (has an sdist), `PyQt6-WebEngine-Qt6` 6.140.0 (wheels only, 132 MB for `win_amd64`) [V][P1].

Everything below was read for Chromium 140 (Qt WebEngine 6.11, 6.12, 6.140). The three decisive pieces of code are identical in `134-based` (Qt 6.10), `146-based`, `152-based` and upstream `main` [V][C0][U1].

## 2. Question 1 — what Chromium does with `proprietary_codecs=true`, `ffmpeg_branding="Chromium"` on Windows

### What the two switches control [V]

- `ffmpeg_branding` selects one of two generated FFmpeg configurations. For Windows x64 the only differences are [C1]:

  | | `Chromium` | `Chrome` adds |
  |---|---|---|
  | Decoders | FLAC, MP3, Vorbis, PCM variants, libopus | `ff_h264_decoder`, `ff_aac_decoder` |
  | Parsers | FLAC, MPEG audio, Opus, Vorbis, VP9 | `ff_aac_parser`, `ff_h264_parser` |
  | Demuxers | FLAC, Matroska, **MOV / MP4**, MP3, Ogg, WAV | `ff_aac_demuxer` (raw ADTS) |

- `proprietary_codecs` is a separate switch, off unless Chrome-branded [C2]. It sets `USE_PROPRIETARY_CODECS` and by default also turns on [C3]:
  - `media_use_openh264` — **Cisco's OpenH264 encoder source is compiled in** (`media/video/openh264_video_encoder.cc`, `//third_party/openh264:encoder`) [C3][C4];
  - on Windows `enable_hevc_parser_and_hw_decoder`, `enable_platform_hevc`, `enable_platform_dolby_vision` (HEVC through the GPU, with Chromium's H.265 parser) [C3];
  - `enable_hls_demuxer`, `enable_mse_mpeg2ts_stream_parser` (the HLS player itself is off by default on desktop [C5]).
- WebRTC: `rtc_use_h264` builds the OpenH264 encoder and an FFmpeg-based H.264 decoder wrapper [C6]. Qt sets `rtc_use_h264=true` together with `proprietary_codecs` (section 3).

Consequence [V]: Qt's switch as defined ships an H.264 encoder and FFmpeg's H.264 / AAC decoders. To keep codecs out, `ffmpeg_branding="Chromium"`, `media_use_openh264=false` **and** `rtc_use_h264=false` are all needed.

### 1a. `canPlayType` / `MediaSource.isTypeSupported`

**Yes for both, unconditionally — whether or not anything can decode.** [V]

- MIME table: with `USE_PROPRIETARY_CODECS`, `video/mp4`, `audio/mp4`, `audio/aac`, `video/x-m4v`, `audio/x-m4a`, `video/3gpp` get H.264 and AAC [C7] (`mime_util_internal.cc` 332–360, 399–408). The MSE parser table gets `avc1.*`, `avc3.*`, `mp4a.40.*` [C8].
- Decoder check: `IsDefaultDecoderSupportedVideoType` has `case VideoCodec::kH264: return true;` [C9] (`supported_types.cc` 455–456). It does not ask FFmpeg or the GPU.
- AAC: `IsDecoderAACSupported` returns `true` for every profile except xHE-AAC [C9] (302–305).
- Qt WebEngine does not override these: it uses Chromium's `RenderMediaClient`, which falls through to the defaults [C10]; no override was found in `src/core` [Q5].
- `IsDecoderBuiltInVideoCodec(kH264)` also returns `true` from build flags alone (`ENABLE_FFMPEG_VIDEO_DECODERS && USE_PROPRIETARY_CODECS`), although FFmpeg has no H.264 decoder in this build [C9] (587–593).

Risk [I]: sites choose formats from these answers. A build that says "yes" and cannot decode can break pages that play today through VP9 / AV1 / Opus.

### 1b. Who decodes H.264

Decoder order in the renderer [V][C11] (`default_decoder_factory.cc`):

1. `DecryptingVideoDecoder` (encrypted streams only).
2. The GPU decoder through Mojo — **only** if `gpu_factories->IsGpuVideoDecodeAcceleratorEnabled()`.
3. libvpx, dav1d (not H.264).
4. `FFmpegVideoDecoder` — finds no H.264 codec in this build.

The GPU decoder on Windows [V][C12] (`gpu_mojo_media_client_win.cc`):

- `CreatePlatformVideoDecoder` returns `D3D11VideoDecoder::Create(...)` or nothing if the workaround `disable_d3d11_video_decoder` is set. It is the only Windows video decoder there.
- It uses the D3D11 device of ANGLE (`shared_context_state->GetD3D11Device()`), needs feature level 11_0, `ID3D11VideoDevice`, and a decoder profile reported by the driver [C13] (`d3d11_video_decoder.cc` 386–406, 1047–1110).
- Its H.264 work is split: Chromium's `H264Decoder` parses the stream and manages reference pictures, and "offloads the final steps of the decoding process" to the accelerator [C14].

Software fallback through Media Foundation: **none.** [V]

- No Media Foundation video decoder for clear content exists in Chromium 140 or in `main` 160 (searched; `media/gpu/windows/` has only D3D11 / D3D12 decoders and MF *encoders*) [C12][U1].
- The old `DXVAVideoDecodeAccelerator`, which wrapped the Windows H.264 transform, is no longer in the tree (its files are absent in `140-based`) [C12]. Vivaldi's developers say it insisted on hardware too, and that the D3D11 code "assumes video hardware acceleration is always available" [X1].
- `MediaFoundationRenderer` can play **clear** content upstream behind the feature `MediaFoundationClearPlayback`, which is **disabled by default** [C5] (1377–1381) [C15]. It would use Windows' own pipeline, including its software decoders [I].
  - **Not usable in Qt WebEngine:** Qt's fork guards that code with `BUILDFLAG(IS_WIN) && BUILDFLAG(ENABLE_WEB_SPEECH)` [C16] (`media_factory.cc` 131, 650; upstream has only `IS_WIN` [U2]), and Qt WebEngine builds with `enable_web_speech=false` [Q6]. It also relies on DirectComposition surfaces, which Qt's compositor does not use [I].
- Microsoft's own page for Edge lists the same fallback chain ending in FFmpeg, and says H.264 does not play if that fails [M1].

### 1c. AAC

A Media Foundation audio decoder exists [V]: `media/filters/win/media_foundation_audio_decoder.cc` [C17].

- Built on Windows by default: `mojo_media_services` contains `audio_decoder`, hosted in the GPU process [C3] (310–316). `GpuMojoMediaClientWin::CreatePlatformAudioDecoder` returns it [C12].
- The renderer always tries `FFmpegAudioDecoder` first, then the Mojo decoder [C11].
- **Codecs it accepts** (`GetTypeInfo`, lines 90–122):
  - AAC **only if** `profile == kXHE_AAC` **and** Windows ≥ 11 22H2;
  - AC-3 / E-AC-3, AC-4, DTS only with build flags that are off by default.
  - Any other AAC falls through to `std::nullopt` → `CreateDecoder` returns `E_NOTIMPL` → `kUnsupportedCodec`.
- The GPU side advertises only `{kAAC, kXHE_AAC}` [C12] (104–107).
- `FFmpegAudioDecoder` refuses xHE-AAC and otherwise needs FFmpeg's AAC decoder [C18].

Result [V]: with Chromium-branded FFmpeg, **AAC-LC and HE-AAC have no decoder**. Audio initialisation fails with `DECODER_ERROR_NOT_SUPPORTED`, which fails the whole playback, video included [C19].

What a patch would change [I][T]:

- The code to feed AAC to the Windows decoder is already there (`GetAacAudioType`, raw AAC with the AudioSpecificConfig) [C20]. The Windows AAC decoder handles AAC-LC, HE-AAC v1 and v2 [M2].
- In Qt WebEngine the GPU service runs **inside the browser process** (`--in-process-gpu` is always set) and Qt calls `PreSandboxMediaFoundationInitialization()` there [Q6][Q7]. So no sandbox change is needed for an MF decoder on that side [I].
- Vivaldi notes the same possibility: "In theory Chromium code can be patched to support all AAC variations" [X2].
- Limits that remain [V]: Web Audio `decodeAudioData` calls FFmpeg directly (`audio_file_reader.cc`) [C21], so AAC there fails; raw `.aac` files need FFmpeg's ADTS demuxer, which is absent [C1].
- For `<video src="x.mp4">` (FFmpeg demuxer, not MSE) FFmpeg leaves the sample format unset when it has no decoder; Chromium fixes this up for AC-3 but not for AAC, so the audio track would be rejected as invalid [C22] (427–468) [I]. One more small patch.

### 1d. No GPU decoder available

Playback of H.264 **fails**; it is not replaced by anything. [V]

- No decoder initialises → `DECODER_ERROR_NOT_SUPPORTED` → format error on the media element [C19].
- `isTypeSupported` still says yes (1a).
- Cases [I]: `--disable-gpu` or Qt Quick software backend; Qt's fallback to the software D3D11 adapter (`QRhi::PreferSoftwareRenderer`) [Q8]; virtual machines and remote sessions without a GPU; drivers on Chromium's lists (8 entries valid for Windows switch off accelerated video decode, 6 switch off or limit `D3D11VideoDecoder`) [C23]; streams the hardware cannot do (the DXVA path is limited to Baseline / Main / High [M3]).
- **GitHub's Windows runners have no GPU** [I]: I.K.E.'s own CI could not test real H.264 playback on them in the GPU-only variant.
- Windows N / KN editions lack Media Foundation until the Media Feature Pack is installed; Chromium logs exactly that hint [C24]. Firefox has the same limit [F1].

## 3. Question 2 — Qt WebEngine's build system

### Where the switches are set [V]

`src/core/CMakeLists.txt` (6.140: lines 430–436; 6.11: 431–437) [Q6]:

```cmake
extend_gn_list(gnArgArg
    ARGS proprietary_codecs rtc_use_h264
    CONDITION QT_FEATURE_webengine_proprietary_codecs
)
if(QT_FEATURE_webengine_proprietary_codecs)
    list(APPEND gnArgArg ffmpeg_branding="Chrome")
endif()
```

- The feature is declared in `src/core/api/configure.cmake` (110–114, `AUTODETECT OFF`) and the command-line switch in `src/core/api/qt_cmdline.cmake` (line 7) [Q9].
- `extend_gn_list` writes `name=true` or `name=false` [Q10]. The list is written to `args.gn` in the build directory [Q11].
- There is no hook for extra GN arguments (searched `cmake/` and `src/core`) [Q11]. vcpkg appends to the generated `args.gn` after configuring [B1]; a source patch is the more predictable way.

### Smallest patch (not built — [T])

```diff
--- a/src/core/CMakeLists.txt
+++ b/src/core/CMakeLists.txt
         extend_gn_list(gnArgArg
-            ARGS proprietary_codecs rtc_use_h264
+            ARGS proprietary_codecs
             CONDITION QT_FEATURE_webengine_proprietary_codecs
         )
-        if(QT_FEATURE_webengine_proprietary_codecs)
-            list(APPEND gnArgArg ffmpeg_branding="Chrome")
-        endif()
+        list(APPEND gnArgArg
+            ffmpeg_branding="Chromium"
+            rtc_use_h264=false
+            media_use_openh264=false
+        )
```

Then configure with `-webengine-proprietary-codecs`. Optional, to keep HEVC and Dolby Vision code out as well [C3]:

```
enable_hevc_parser_and_hw_decoder=false
enable_platform_dolby_vision=false
enable_platform_encrypted_dolby_vision=false
```

(`enable_platform_hevc` then becomes false by its default; the two Dolby Vision lines are needed because of an assert [C3] 163–165, 209–210.)

Why this should compile [I]: Chromium's Android configuration is the same shape — proprietary codecs on, no OpenH264, FFmpeg without video decoders [C3] (71–73, 250–255); the FFmpeg bridge code already handles "no H.264 parser in FFmpeg" [C22] (638–654); Vivaldi builds with `proprietary_codecs=true` and the two decoders removed from FFmpeg [X3].

### Is hardware video decoding on in Qt WebEngine on Windows?

Yes by default, as far as source and Qt's statements show. [V] for the code path, [T] for behaviour.

- Qt selects ANGLE for Chromium whenever Qt Quick uses a supported RHI backend, passes Qt's adapter LUID on Direct3D 11, and runs the GPU service in-process [Q7] (179–188, 759–764, 833–840).
- Qt touches no Windows video-decode switch; the only one it disables is the Linux feature [Q7] (752–755).
- Nothing in Qt's GN arguments changes `mojo_media_services` [Q6].
- Qt's statements: "QtWebEngine in Qt6 supports hardware acceleration for video playback only on Windows and macOS" (QTBUG-110260) [Q12]; the wiki says for 6.5 that Windows video acceleration "should work automatically" [Q13].
- No Qt documentation was found that names `D3D11VideoDecoder`, and none on H.264 through it with the official binaries — they cannot show it, being built without proprietary codecs [Q14].
- Qt registers H.264 as a Widevine capability when `USE_PROPRIETARY_CODECS` is set [Q5].

Check on a real system [T]: `chrome://gpu` ("Video Decode") and `chrome://media-internals` (decoder name `D3D11VideoDecoder`) inside I.K.E.

## 4. Question 3 — building on GitHub Actions

### Requirements [V]

| Need | Value | Source |
|---|---|---|
| Compiler | MSVC only (no MinGW); VS 2022 with compiler ≥ 14.36, or VS 2019 ≥ 14.29; C++20 | [Q15][Q16] |
| Windows SDK | ≥ 10.0.26100.0 | [Q15][Q16] |
| CMake / Ninja | ≥ 3.19 / ≥ 1.7.2 (the documentation prints "3.8" for Ninja; `configure.cmake` reuses the Python variable in that sentence) | [Q15][Q16] |
| Python | ≥ 3.8 with `html5lib` | [Q15][Q16] |
| Node.js | 64-bit, ≥ 20 | [Q15][Q16] |
| gperf, bison, flex | native Windows builds; Qt advises against MSYS2 / Cygwin tools. vcpkg uses `win_flex` / `win_bison` and links them to the plain names | [Q16][B1] |
| Qt modules | `Gui`, `Qml`, `Quick` are required targets → qtbase, **qtshadertools** (Qt Quick is not built without its `qsb` tool), qtdeclarative. Optional: qtwebchannel, qtpositioning, qttools | [Q15][Q17][Q18] |
| Build path | very short: vcpkg found a build tree path longer than 22 characters fails for Release on Windows | [B1] |
| Static build | not supported | [Q16] |

So the list "qtbase + qtdeclarative + qtwebchannel + qtwebengine + qtsvg" lacks **qtshadertools**. qtsvg is not needed by the engine, only by I.K.E. itself.

Better [I]: do not build Qt at all. Install the official Qt 6.12 MSVC binaries (same Qt as the `PyQt6-Qt6` wheel) and build only `qtwebengine` with `qt-configure-module`, which Qt's wiki describes for 6.12 [Q19].

### The runner [V]

- `windows-latest` / `windows-2025` / `windows-2022`, public repository: 4 cores, 16 GB RAM, 14 GB SSD [G1]. Free for public repositories [G2].
- A job is killed after **6 hours**; a workflow run may last 35 days; cache is 10 GB per repository [G3].
- Larger runners are for Team / Enterprise plans [G1]. A self-hosted runner allows 5 days per job [G3].

### Time and space

- No measured time for Qt WebEngine on such a runner was found. **[I], rough:** 8–15 hours of compilation. Basis: Linux From Scratch gives 44 SBU with 8 parallel jobs and 12 GB of disk for 6.11.3, the slowest package in its book [B2]; the runner has 4 virtual cores and MSVC.
- MSVC memory: forum reports of "compiler out of heap space" and very high use on many-core machines; fewer parallel jobs is the usual remedy [B3]. With 4 jobs on 16 GB: [T].
- It will not fit in one 6-hour job [I].

### What others do [V]

- **ungoogled-chromium-windows** builds full Chromium on `windows-2022` runners with **16 chained jobs**. Each runs Ninja for at most 3.5 hours, then zips the build tree into an artifact; the next job downloads it and continues. It builds under `C:\` and installs the needed Windows SDK itself [B4].
- That shows disk space on the hosted runner is enough for a whole Chromium build tree [I].
- Compiler cache: Qt WebEngine forwards `CMAKE_CXX_COMPILER_LAUNCHER` to GN as `cc_wrapper` [Q20], so `sccache` can be attached. With MSVC inside this build: [T]. It helps only when sources repeat; 10 GB cache limit [G3].
- Jumbo builds (`-webengine-jumbo-build`) are on by default with a merge limit of 8; a higher limit compiles faster and needs more memory per job [Q15][Q20] [I].
- Environment variables `NINJAFLAGS` and `QTWEBENGINE_GN_THREADS` limit parallelism [Q11][B1].

### PyQt6 against the custom engine

- The PyPI Qt wheels are a repackaging of the Qt Company's installer binaries [P2].
- **Option 1 — replace files, no binding build [I][T].** Keep `PyQt6`, `PyQt6-Qt6`, `PyQt6-WebEngine` from PyPI. Build `qtwebengine` at the same version against the same Qt, and replace the engine files of `PyQt6-WebEngine-Qt6`: `Qt6WebEngine*.dll`, `QtWebEngineProcess.exe`, the resource `.pak` files, `icudtl.dat`, `v8_context_snapshot.bin`, locales. Codec switches do not change the C++ interface the bindings link to. Which commit the PyPI wheel was built from must be matched; a Qt forum thread notes that the first 6.140 wheels were a pre-release build [P3].
- **Option 2 — `pyqt-bundle --qt-dir <Qt prefix> <wheel>`** replaces the Qt inside a wheel with a local one. Its documentation assumes installer binaries and says a source-built Qt "may work but is unsupported" [P4].
- **Option 3 — build the bindings.** `PyQt6-WebEngine` has a 38 kB sdist; PyPI says pip can build it with `qmake` on `PATH`, or `sip-install` [P1][P5]. Needs `PyQt-builder`, `sip`, the installed `PyQt6` and MSVC. Small compared with the engine [I].

## 5. Question 4 — legal notes (not advice)

### What a build with `proprietary_codecs=true`, Chromium FFmpeg, OpenH264 off contains [V]

| Piece | In the build? | Source |
|---|---|---|
| FFmpeg H.264 decoder, AAC decoder, their parsers | **no** | [C1] |
| OpenH264 encoder | **no**, if `media_use_openh264=false` and `rtc_use_h264=false`; yes by default | [C3][C4][C6] |
| FFmpeg MOV / MP4 demuxer | yes — and already in every Qt WebEngine | [C1] |
| Chromium's MP4 parser for AVC and AAC boxes, ADTS parser, H.264 Annex B converters, MPEG-2 TS parsers, HLS playlist code | yes, added by the switch | [C25] |
| `H264Parser`, `H264Decoder` + `H264DPB`, `D3D11H264Accelerator` | yes — **not** behind the switch; already in stock builds | [C26] |
| H.265 parser, `H265Decoder`, D3D11 H.265 accelerator | added by the switch on Windows unless turned off | [C3][C26] |
| Glue to Media Foundation decoders and encoders | yes | [C12][C17] |

So: nothing that turns an H.264 or AAC stream into pictures or samples by itself. What it does contain is container and bitstream **parsing**, and for H.264 the reference-picture bookkeeping that precedes the GPU's work [C14].

Whether such code needs a licence is a legal question this study cannot answer. Two public positions differ:

- Vivaldi ships it, stating that the parsing and metadata code "has been patent-free at least since 2017" [X3], and expects the last relevant H.264 patent around 2027 [X1]. These are Vivaldi's statements, not verified here.
- Mozilla was asked to ship FFmpeg's `vaapi_h264.c` (hardware H.264, no software decoder) in Firefox's own FFmpeg. The bug was closed WONTFIX; the discussion names decoded-picture-buffer patents with expiry dates listed up to 2028 and suggests asking Mozilla's lawyers [F2].

### Firefox on Windows, for comparison [V]

- Firefox's bundled FFmpeg ("ffvpx") has VP8, VP9, AV1, MP3, FLAC, Vorbis, Opus, PCM and "does not ship the H.264 decoder" [F3].
- `WMFDecoderModule` creates Windows' own transforms: `CLSID_CMSH264DecoderMFT` for H.264, `CLSID_CMSAACDecMFT` for AAC. Video runs with DXVA in the GPU process or **in software** in the RDD process; audio is software only [F4].
- Mozilla's help says Firefox relies on the operating system's H.264 support; the Cisco OpenH264 plug-in, installed separately, serves WebRTC only [F5][F6].
- The Windows H.264 transform decodes in software when DXVA is not available [M3].

The difference from the GPU-only Qt WebEngine variant: Firefox hands the whole stream to Windows; Chromium's D3D11 path parses it and manages reference pictures itself.

## 6. Question 5 — conclusion

**Is the requirement achievable with Qt WebEngine on Windows?** With switches only: **no.** With I.K.E.'s own patches to Qt's Chromium: **yes**, in two sizes.

### Variant 0 — switches only (section 3 patch)

- Works [I]: H.264 video with Opus / MP3 / FLAC audio or silent, on a GPU with H.264 decode.
- Does not work [V]: anything with AAC — nearly all MP4 on the web. Reports support it does not have.
- Not worth shipping.

### Variant 1 — GPU video + Windows AAC (about 40 changed lines, all [T])

1. Section 3 patch in `src/core/CMakeLists.txt`.
2. `media_foundation_audio_decoder.cc`, `GetTypeInfo`: return `MFAudioFormat_AAC` for every AAC profile (keep the Windows 11 22H2 condition for xHE-AAC only).
3. `gpu_mojo_media_client_win.cc`, `GetPlatformSupportedAudioDecoderConfigs`: also announce plain AAC when Media Foundation initialises.
4. `supported_types.cc`:
   - AAC: answer from the audio list of step 3 (so Windows N says "no").
   - H.264: answer from the GPU's profile list instead of `return true`, the mechanism HEVC already uses; drop H.264 from `IsDecoderBuiltInVideoCodec`. The profile list is filled only under `PLATFORM_HAS_OPTIONAL_HEVC_DECODE_SUPPORT` [C10] (24–36, 155–174): either leave HEVC platform support on or widen those conditions.
5. `ffmpeg_common.cc`: give AAC a sample format when FFmpeg supplies none (for `<video src>` MP4).

Works then [I]: MP4 and MSE with H.264 + AAC on Windows 10 / 11 with a normal GPU.

Does not work:

- H.264 without a usable GPU decoder: fails, but honestly reported after step 4.
- Web Audio decoding of AAC; raw `.aac` files.
- Windows N without the Media Feature Pack.
- Real playback tests on GitHub's runners.
- Unknown until tested: HE-AAC and multichannel details, seeking, AAC with Widevine.

### Variant 2 — Variant 1 + software H.264 through the Windows transform (Firefox-like)

- Add a `media::VideoDecoder` that drives `CLSID_CMSH264DecoderMFT`, tried after the GPU decoder.
- Precedent with a compatible licence: Vivaldi's `platform_media/decoders/win/wmf_video_decoder.cc` (about 19 kB, original work of Opera, BSD 3-clause) plus pre-loading `msmpeg2vdec.dll` before the renderer sandbox closes [X1][X4][X5]. Vivaldi does AAC differently: a C decoder behind FFmpeg's codec interface (`wmfaacdec.c`), which also covers Web Audio, at the price of sandbox changes [X2].
- Cost [I]: several hundred lines in Chromium's media and sandbox start-up, tested only on real Windows, re-fitted at every Chromium change (140 now, a newer base announced [Q3]).

### Recipe (for Variant 1 or 2)

1. Pin one Qt WebEngine tag (today `v6.140.0`) and the matching official Qt 6.12 MSVC binaries.
2. Keep the patches as files in I.K.E.'s repository; apply them to a clean checkout in CI.
3. Chained GitHub jobs on `windows-2022` / `windows-2025`: short path, `qt-configure-module <src> -webengine-proprietary-codecs`, Ninja with a time limit, build tree passed on as an artifact (section 4).
4. Check the result in CI without a GPU: `args.gn` contains the intended values; the linker map / PDB of `Qt6WebEngineCore.dll` has no `ff_h264_decoder`, `ff_aac_decoder` or OpenH264 (`WelsCreateSVCEncoder`) symbols; `canPlayType` answers.
5. Replace the engine files in the PyQt wheel layout (section 4, option 1).
6. Real playback test on a Windows machine with a GPU before every release.
7. Repeat for every Qt WebEngine security release. This is the permanent cost.

### Alternatives that respect the requirement

- **A. Ship the stock engine without H.264 / AAC** and say so (already option A of `docs/platforms/windows.md`). VP8, VP9, AV1, Opus, Vorbis, FLAC, MP3 play [Q14].
- **B. Variant 1 or 2 above.**
- **C. A system engine instead of a bundled one: WebView2** (Microsoft Edge's engine, with Microsoft's codecs, updated by Windows). I.K.E. would ship no engine and no codec. Qt WebView can use WebView2 on Windows [Q21], but its API is far smaller than Qt WebEngine's; I.K.E.'s blocker, profiles, scripts and permissions would need a different design [I]. Not studied further.
- **D. Hand direct media links to Windows** [I]: for a navigation straight to an `.mp4` / `.m4a` file, play it with the system (default player, or Qt Multimedia's Media Foundation backend). Covers downloads and direct links only, not video inside pages.
- Not an alternative: OpenH264 from Cisco. Chromium uses it only for encoding [C3]; it would not decode `<video>` and does not cover AAC.

### Order of work suggested

1. Before any patch: build Variant 0 once (proves the CI chain and the file replacement) and look at `chrome://media-internals` on a real Windows PC with an H.264 + Opus test file. That answers whether `D3D11VideoDecoder` really runs inside Qt WebEngine.
2. Then the AAC patch (steps 2–3, 5), then honest reporting (step 4).
3. Decide on Variant 2 only after seeing how often Variant 1 fails on real machines.
4. Put the legal question (section 5) to someone qualified before publishing a build.

## Pages that could not be opened

- `https://searchfox.org/firefox-main/source/dom/media/platforms/wmf/WMFVideoMFTManager.cpp` — permission request not answered. The software / hardware statement for Firefox therefore rests on `WMFDecoderModule.cpp` [F4] and Microsoft's page [M3].
- `https://doc.qt.io/qt-6.11/qtwebengine-platform-notes.html` — same; `https://doc.qt.io/qt-6/qtwebengine-platform-notes.html` (6.140) was read instead.
- `https://qt-project.atlassian.net/browse/PYSIDE-1808` — returned no content.
- `https://forums.freebsd.org/threads/how-long-is-building-qt6-webengine-supposed-to-take.87845/` — server error.
- `https://sources.debian.org/src/qt6-webengine/6.8.2%2Bdfsg-4/debian/patches/ccache.diff` — needs JavaScript.

## Sources

Qt WebEngine (`https://github.com/qt/qtwebengine`, mirror of code.qt.io):

- [Q1] Branches and tags: https://github.com/qt/qtwebengine/tree/6.140 ; https://github.com/qt/qtwebengine/tree/6.11
- [Q2] `CHROMIUM_VERSION`: https://github.com/qt/qtwebengine/blob/6.140/CHROMIUM_VERSION ; https://github.com/qt/qtwebengine/blob/6.12/CHROMIUM_VERSION ; https://github.com/qt/qtwebengine/blob/6.11/CHROMIUM_VERSION ; https://github.com/qt/qtwebengine/blob/6.10/CHROMIUM_VERSION
- [Q3] Qt blog, "Qt WebEngine will release separate" (2026-09-24): https://www.qt.io/blog/qt-webengine-will-release-separate
- [Q4] Qt wiki, Chromium versions: https://wiki.qt.io/QtWebEngine/ChromiumVersions
- [Q5] `src/core/content_client_qt.cpp` (lines 340–356); renderer client: https://github.com/qt/qtwebengine/blob/6.140/src/core/content_client_qt.cpp ; https://github.com/qt/qtwebengine/blob/6.140/src/core/renderer/content_renderer_client_qt.h
- [Q6] `src/core/CMakeLists.txt` (GN arguments, lines 331–436): https://github.com/qt/qtwebengine/blob/6.140/src/core/CMakeLists.txt ; 6.11: https://github.com/qt/qtwebengine/blob/6.11/src/core/CMakeLists.txt
- [Q7] `src/core/web_engine_context.cpp`; `src/core/content_main_delegate_qt.cpp` (lines 162–168): https://github.com/qt/qtwebengine/blob/6.140/src/core/web_engine_context.cpp ; https://github.com/qt/qtwebengine/blob/6.140/src/core/content_main_delegate_qt.cpp
- [Q8] `src/core/rhi_gpu_info.cpp` (lines 91–103): https://github.com/qt/qtwebengine/blob/6.140/src/core/rhi_gpu_info.cpp
- [Q9] `src/core/api/configure.cmake`, `src/core/api/qt_cmdline.cmake`: https://github.com/qt/qtwebengine/blob/6.140/src/core/api/configure.cmake ; https://github.com/qt/qtwebengine/blob/6.140/src/core/api/qt_cmdline.cmake
- [Q10] `cmake/QtGnTargetHelpers.cmake` (`extend_gn_list`, lines 44–62): https://github.com/qt/qtwebengine/blob/6.140/cmake/QtGnTargetHelpers.cmake
- [Q11] `cmake/Functions.cmake` (`add_gn_command`, `NINJAFLAGS`, `QTWEBENGINE_GN_THREADS`): https://github.com/qt/qtwebengine/blob/6.140/cmake/Functions.cmake
- [Q12] QTBUG-110260: https://bugreports-test.qt.io/browse/QTBUG-110260
- [Q13] Qt wiki, video acceleration: https://wiki.qt.io/QtWebEngine/VideoAcceleration
- [Q14] Qt WebEngine Features (codecs, hardware acceleration): https://doc.qt.io/qt-6.11/qtwebengine-features.html ; source https://github.com/qt/qtwebengine/blob/6.140/src/core/doc/src/qtwebengine-features.qdoc
- [Q15] `configure.cmake` (versions lines 10–34; checks lines 300–535; jumbo lines 633–651): https://github.com/qt/qtwebengine/blob/6.140/configure.cmake
- [Q16] Qt WebEngine Platform Notes (6.140): https://doc.qt.io/qt-6/qtwebengine-platform-notes.html
- [Q17] `dependencies.yaml`: https://github.com/qt/qtwebengine/blob/6.140/dependencies.yaml
- [Q18] qtdeclarative, Qt Quick needs `qsb`: https://github.com/qt/qtdeclarative/blob/6.11/src/CMakeLists.txt ; https://github.com/qt/qtdeclarative/blob/6.11/dependencies.yaml
- [Q19] Qt wiki, building Qt WebEngine for Qt 6: https://wiki.qt.io/QtWebEngine/Qt6Build
- [Q20] `cmake/QtToolchainHelpers.cmake` (jumbo lines 371–376; `cc_wrapper` lines 400–402): https://github.com/qt/qtwebengine/blob/6.140/cmake/QtToolchainHelpers.cmake
- [Q21] Qt WebView: https://doc.qt.io/qt-6.12/qtwebview-index.html

Chromium as used by Qt (`https://github.com/qt/qtwebengine-chromium`, branch `140-based`, paths under `chromium/`):

- [C0] Branch list: https://github.com/qt/qtwebengine-chromium/branches
- [C1] FFmpeg configurations: https://github.com/qt/qtwebengine-chromium/tree/140-based/chromium/third_party/ffmpeg/chromium/config/Chromium/win/x64 ; https://github.com/qt/qtwebengine-chromium/tree/140-based/chromium/third_party/ffmpeg/chromium/config/Chrome/win/x64 (`libavcodec/codec_list.c`, `libavcodec/parser_list.c`, `libavformat/demuxer_list.c`); `ffmpeg_options.gni`: https://github.com/qt/qtwebengine-chromium/blob/140-based/chromium/third_party/ffmpeg/ffmpeg_options.gni
- [C2] `build/config/features.gni`: https://github.com/qt/qtwebengine-chromium/blob/140-based/chromium/build/config/features.gni
- [C3] `media/media_options.gni`: https://github.com/qt/qtwebengine-chromium/blob/140-based/chromium/media/media_options.gni
- [C4] `media/video/BUILD.gn` (lines 76–82): https://github.com/qt/qtwebengine-chromium/blob/140-based/chromium/media/video/BUILD.gn
- [C5] `media/base/media_switches.cc`: https://github.com/qt/qtwebengine-chromium/blob/140-based/chromium/media/base/media_switches.cc
- [C6] `third_party/webrtc/webrtc.gni` (lines 184–193); `modules/video_coding/BUILD.gn` (lines 525–535): https://github.com/qt/qtwebengine-chromium/blob/140-based/chromium/third_party/webrtc/webrtc.gni ; https://github.com/qt/qtwebengine-chromium/blob/140-based/chromium/third_party/webrtc/modules/video_coding/BUILD.gn
- [C7] `media/base/mime_util_internal.cc`: https://github.com/qt/qtwebengine-chromium/blob/140-based/chromium/media/base/mime_util_internal.cc
- [C8] `media/filters/stream_parser_factory.cc`: https://github.com/qt/qtwebengine-chromium/blob/140-based/chromium/media/filters/stream_parser_factory.cc
- [C9] `media/base/supported_types.cc`: https://github.com/qt/qtwebengine-chromium/blob/140-based/chromium/media/base/supported_types.cc
- [C10] `content/renderer/media/render_media_client.cc`: https://github.com/qt/qtwebengine-chromium/blob/140-based/chromium/content/renderer/media/render_media_client.cc
- [C11] `media/renderers/default_decoder_factory.cc`; `media/mojo/clients/mojo_decoder_factory.cc`: https://github.com/qt/qtwebengine-chromium/blob/140-based/chromium/media/renderers/default_decoder_factory.cc ; https://github.com/qt/qtwebengine-chromium/blob/140-based/chromium/media/mojo/clients/mojo_decoder_factory.cc
- [C12] `media/mojo/services/gpu_mojo_media_client_win.cc`; `gpu_mojo_media_client.cc`: https://github.com/qt/qtwebengine-chromium/blob/140-based/chromium/media/mojo/services/gpu_mojo_media_client_win.cc ; https://github.com/qt/qtwebengine-chromium/blob/140-based/chromium/media/mojo/services/gpu_mojo_media_client.cc
- [C13] `media/gpu/windows/d3d11_video_decoder.cc`: https://github.com/qt/qtwebengine-chromium/blob/140-based/chromium/media/gpu/windows/d3d11_video_decoder.cc
- [C14] `media/gpu/h264_decoder.h` (lines 30–32): https://github.com/qt/qtwebengine-chromium/blob/140-based/chromium/media/gpu/h264_decoder.h
- [C15] `media/base/win/mf_feature_checks.cc`: https://github.com/qt/qtwebengine-chromium/blob/140-based/chromium/media/base/win/mf_feature_checks.cc
- [C16] `content/renderer/media/media_factory.cc`: https://github.com/qt/qtwebengine-chromium/blob/140-based/chromium/content/renderer/media/media_factory.cc
- [C17] `media/filters/win/media_foundation_audio_decoder.cc`: https://github.com/qt/qtwebengine-chromium/blob/140-based/chromium/media/filters/win/media_foundation_audio_decoder.cc
- [C18] `media/filters/ffmpeg_audio_decoder.cc` (lines 103–116): https://github.com/qt/qtwebengine-chromium/blob/140-based/chromium/media/filters/ffmpeg_audio_decoder.cc
- [C19] `media/renderers/audio_renderer_impl.cc` (669–678); `video_renderer_impl.cc` (311–320); `third_party/blink/renderer/platform/media/web_media_player_impl.cc` (387–405): https://github.com/qt/qtwebengine-chromium/blob/140-based/chromium/media/renderers/audio_renderer_impl.cc ; https://github.com/qt/qtwebengine-chromium/blob/140-based/chromium/media/renderers/video_renderer_impl.cc ; https://github.com/qt/qtwebengine-chromium/blob/140-based/chromium/third_party/blink/renderer/platform/media/web_media_player_impl.cc
- [C20] `media/base/win/mf_helpers.cc` (`GetAacAudioType`, lines 457–500): https://github.com/qt/qtwebengine-chromium/blob/140-based/chromium/media/base/win/mf_helpers.cc
- [C21] `media/filters/audio_file_reader.cc`: https://github.com/qt/qtwebengine-chromium/blob/140-based/chromium/media/filters/audio_file_reader.cc
- [C22] `media/ffmpeg/ffmpeg_common.cc`; `media/filters/ffmpeg_demuxer.cc` (lines 221–257): https://github.com/qt/qtwebengine-chromium/blob/140-based/chromium/media/ffmpeg/ffmpeg_common.cc ; https://github.com/qt/qtwebengine-chromium/blob/140-based/chromium/media/filters/ffmpeg_demuxer.cc
- [C23] GPU lists: https://github.com/qt/qtwebengine-chromium/blob/140-based/chromium/gpu/config/software_rendering_list.json ; https://github.com/qt/qtwebengine-chromium/blob/140-based/chromium/gpu/config/gpu_driver_bug_list.json
- [C24] `media/base/win/mf_initializer.cc`: https://github.com/qt/qtwebengine-chromium/blob/140-based/chromium/media/base/win/mf_initializer.cc
- [C25] `media/formats/BUILD.gn`; `media/filters/BUILD.gn`: https://github.com/qt/qtwebengine-chromium/blob/140-based/chromium/media/formats/BUILD.gn ; https://github.com/qt/qtwebengine-chromium/blob/140-based/chromium/media/filters/BUILD.gn
- [C26] `media/gpu/BUILD.gn` (lines 232–233, 365–370); `media/parsers/BUILD.gn` (lines 11–18): https://github.com/qt/qtwebengine-chromium/blob/140-based/chromium/media/gpu/BUILD.gn ; https://github.com/qt/qtwebengine-chromium/blob/140-based/chromium/media/parsers/BUILD.gn

Upstream Chromium (`https://github.com/chromium/chromium`, mirror):

- [U1] `main`: https://github.com/chromium/chromium/blob/main/media/filters/win/media_foundation_audio_decoder.cc ; https://github.com/chromium/chromium/blob/main/media/base/supported_types.cc ; https://github.com/chromium/chromium/blob/main/media/mojo/services/gpu_mojo_media_client_win.cc ; https://github.com/chromium/chromium/blob/main/chrome/VERSION
- [U2] 140.0.7339.207 `media_factory.cc`: https://github.com/chromium/chromium/blob/140.0.7339.207/content/renderer/media/media_factory.cc

Vivaldi (official source: https://vivaldi.com/source/ ; read through the unofficial mirror `ric2b/Vivaldi-browser`):

- [X1] `platform_media/docs/video_decoders.md`: https://github.com/ric2b/Vivaldi-browser/blob/master/platform_media/docs/video_decoders.md
- [X2] `platform_media/docs/audio_decoders.md`: https://github.com/ric2b/Vivaldi-browser/blob/master/platform_media/docs/audio_decoders.md
- [X3] `platform_media/README.md`, `docs/ffmpeg.md`: https://github.com/ric2b/Vivaldi-browser/blob/master/platform_media/README.md ; https://github.com/ric2b/Vivaldi-browser/blob/master/platform_media/docs/ffmpeg.md
- [X4] `platform_media/decoders/win/wmf_video_decoder.cc`, `platform_media/sandbox/win/platform_media_init.cc`, `platform_media/source_updates.gni`: https://github.com/ric2b/Vivaldi-browser/tree/master/platform_media
- [X5] Licences: https://github.com/ric2b/Vivaldi-browser/blob/master/platform_media/OPERA_LICENSE.txt ; https://github.com/ric2b/Vivaldi-browser/blob/master/LICENSE

Firefox / Mozilla:

- [F1] Windows N / KN: https://support.mozilla.org/en-US/kb/fix-video-audio-problems-firefox-windows
- [F2] Bug 1737116: https://bugzilla.mozilla.org/show_bug.cgi?id=1737116
- [F3] `media/ffvpx/README_MOZILLA`: https://searchfox.org/firefox-main/source/media/ffvpx/README_MOZILLA
- [F4] `WMFDecoderModule.cpp`: https://searchfox.org/firefox-main/source/dom/media/platforms/wmf/WMFDecoderModule.cpp
- [F5] Audio and video in Firefox: https://support.mozilla.org/en-US/kb/viewing-html5-audio-and-video
- [F6] OpenH264 plug-in: https://support.mozilla.org/en-US/kb/open-h264-plugin-firefox

Microsoft:

- [M1] Edge, video playback issues: https://learn.microsoft.com/en-us/troubleshoot/microsoft-edge/development/video-playback-issues
- [M2] AAC Decoder: https://learn.microsoft.com/en-ca/windows/win32/medfound/aac-decoder
- [M3] H.264 Video Decoder: https://learn.microsoft.com/en-ie/Windows/Win32/medfound/h-264-video-decoder

Building, GitHub, PyQt:

- [B1] vcpkg port `qtwebengine`: https://github.com/microsoft/vcpkg/blob/master/ports/qtwebengine/portfile.cmake
- [B2] Linux From Scratch, QtWebEngine 6.11.3: https://linuxfromscratch.org/blfs/view/svn/x/qtwebengine.html
- [B3] Qt forum, "Can't build QtWebEngine. Compiler out of heap space": https://forum.qt.io/post/809994
- [B4] ungoogled-chromium-windows: https://github.com/ungoogled-software/ungoogled-chromium-windows/blob/master/.github/workflows/reusable-build.yml ; https://github.com/ungoogled-software/ungoogled-chromium-windows/blob/master/.github/actions/stage/index.js ; https://github.com/ungoogled-software/ungoogled-chromium-windows/blob/master/build.py ; https://github.com/ungoogled-software/ungoogled-chromium-windows/blob/master/.github/actions/prepare/action.yml
- [G1] GitHub-hosted runners: https://docs.github.com/en/actions/reference/runners/github-hosted-runners
- [G2] Billing: https://docs.github.com/en/actions/reference/usage-limits-billing-and-administration
- [G3] Limits: https://docs.github.com/en/actions/reference/limits
- [P1] PyPI: https://pypi.org/project/PyQt6-WebEngine ; https://pypi.org/project/PyQt6-WebEngine-Qt6/ ; https://pypi.org/project/PyQt6/ ; https://pypi.org/project/PyQt6-Qt6/
- [P2] PyQt mailing list, Qt wheels are repackaged installer binaries: https://riverbankcomputing.com/pipermail/pyqt/2024-December/046112.html
- [P3] Qt forum, PySide6-WebEngine 6.12.0.140 wheels: https://forum.qt.io/post/840725
- [P4] `pyqt-bundle`: https://pyqt-builder.readthedocs.io/en/stable/pyqtbundle.html
- [P5] PyQt-builder: https://github.com/Python-PyQt/PyQt-builder/blob/main/README.md
