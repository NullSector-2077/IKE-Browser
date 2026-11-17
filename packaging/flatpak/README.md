# I.K.E. as a Flatpak

Work in progress on branch `linux/flatpak` (ROADMAP.md, "Next: multiplatform",
step 3). Not yet on Flathub; the bundle is built and tested by
`.github/workflows/flatpak.yml`.

## What is in it

| Part | Comes from |
|---|---|
| Qt 6.11, Python 3.13 | the KDE 6.11 run time (`org.kde.Platform//6.11`) |
| PyQt6, PyQt6-WebEngine | the PyQt base application (`com.riverbankcomputing.PyQt.BaseApp//6.11`) |
| Qt WebEngine 6.11.3 | built by this manifest (`qtwebengine/`): the base application's source, patches and switches, but decoding through the run time's FFmpeg — see "Codecs" below |
| jeepney, cryptography | built from their source archives (`generated/python3-runtime-deps.json`) |
| I.K.E. AdBlock engine | built from `ike-adblock/` with the vendored crates (`generated/cargo-sources.json`) |
| I.K.E. | this repository, laid out under `/app/lib/ike-browser` as the PKGBUILD lays it out under `/usr/lib` |

The application ID is `io.github.nullsector_2077.IKE-Browser` (Flathub's rule
for GitHub projects: `io.github.<user>.<repository>`, the dash of the user name
turned into an underscore).

## Differences from the Arch package

- **Updates come from Flatpak.** The program folder is read-only: I.K.E.'s own
  self-update is off (`ike/updater.py`, `ike_boot.py`); language packs are
  still downloaded into the user's folder.
- **Desktop names** are the application ID (desktop entry, icon, notifications,
  `QGuiApplication.desktopFileName`); media controls and KRunner keep their
  own D-Bus names, granted in the manifest (`--own-name`).
- **Default browser**: the Settings button does not call `xdg-settings`
  (it would change only the sandbox's copy); the desktop's own settings do it.
- **Restart and other profiles** start a new sandbox through `flatpak-spawn`.
- **Files**: the Downloads folder directly; anything else through the file
  chooser portal.
- **Chromium's sandbox stays on**: inside Flatpak it starts its processes
  through the Flatpak portal (patches of the Qt WebEngine base application).

## Codecs

ROADMAP.md, "Codecs": I.K.E. never ships a proprietary codec. The Flatpak
decodes H.264 / AAC only through the run time's FFmpeg, never through
decoders inside the bundle: H.264 through the run time's codec extension
(`org.freedesktop.Platform.codecs-extra//25.08-extra`, which Flathub
distributes separately and installs with the run time), AAC already through
the base run time's FFmpeg. Chosen by the owner on 2026-11-17 after two
studies, together with the hint below; OpenH264 stays off.

Flathub's Qt WebEngine base application cannot give that: it is built with
`-DQT_FEATURE_webengine_proprietary_codecs=ON` and Chromium's own FFmpeg
(`webengine_system_ffmpeg=OFF`), so its `libQt6WebEngineCore` contains
Chromium's H.264 and AAC decoders (measured: with the codec extension
removed it still decoded both, run 43974228106). The manifest therefore
builds Qt WebEngine again (`qtwebengine/qtwebengine.json`) with the base
application's own source, patches (Chromium's sandbox through the Flatpak
portal, paths, Widevine, PipeWire) and switches, except:

- `webengine_system_ffmpeg=ON`: Chromium decodes through the run time's
  FFmpeg (7.1, libavcodec 61). The base run time's FFmpeg (Freedesktop
  25.08) has the AAC decoder but not H.264, HEVC, VC-1 or VVC; the codec
  extension, put first on the library path when it is installed, has them
  all. Chromium uses only its `h264` among them (HEVC stays with hardware
  decoding, as in Chromium). Two small patches make Chromium
  and Qt's configure check accept an FFmpeg without Chromium's
  `av_stream_get_first_dts` addition (`qtwebengine/patches/*system-ffmpeg*`).
- No OpenH264 compiled in (`rtc_use_h264=false`, `media_use_openh264=false`,
  `qtwebengine/patches/qtwebengine-no-openh264.patch`): the base application
  builds Cisco's H.264 encoder into the engine for WebRTC, MediaRecorder and
  WebCodecs; the KDE SDK has no OpenH264 to build against instead. So in the
  Flatpak sites cannot *encode* H.264 (MediaRecorder, WebCodecs, WebRTC),
  and `rtc_use_h264=false` also removes WebRTC's software H.264 *decoder*:
  a video call uses VP8, VP9 or AV1, which WebRTC services support, but no
  H.264 in either direction. Playing H.264 in pages (`<video>`, Media Source,
  WebCodecs decoding) is not affected. The same choice as openSUSE's
  `qt6-webengine` (`rtc-dont-use-h264.patch`). The owner decided on
  2026-11-17 to leave OpenH264 off (Freedesktop 25.08 has none, and Chromium
  uses it only to encode).
- QtPdf is not built again (the base application's stays; I.K.E. does not use
  it).

**Help → About** (only inside the Flatpak): when the codec extension is not
installed, it says that H.264 plays only with it and shows the command that
adds it, `flatpak install flathub org.freedesktop.Platform.codecs-extra//25.08-extra`
(`ike/mediacheck.py`). It detects the extension the way Freedesktop's own
FFmpeg test does: Flatpak writes
`/run/flatpak/ld.so.conf.d/runtime-*-org.freedesktop.Platform.codecs-extra.conf`
for an installed extension that adds a library folder. The engine itself
cannot tell: with a system FFmpeg Chromium declares H.264 whether a decoder
is there or not. The branch `25.08-extra` follows the KDE run time (6.11 is
built on Freedesktop 25.08); a test fails when the manifest's run time
changes without it. Outside a Flatpak nothing changes.

The base application's Qt WebEngine libraries are deleted before the new ones
are installed. The PyQt bindings of the PyQt base application stay and load
the new engine (same Qt 6.11 series).

The workflow checks it on every run (`tools/ci/flatpak-codecs.py`): no
program or library of the installed bundle contains FFmpeg's H.264, AAC or
HEVC decoder, while the same search finds them in the base application (the
control); `libQt6WebEngineCore` takes `libavcodec` from the run time; the
engine report is made with the codec extension (H.264 and AAC must decode)
and, for information, without it; and Help → About's check of the extension
is run in the sandbox with and without it. Only then is the bundle kept as the run's download (`ike-browser-flatpak`).

Building Chromium takes longer than one GitHub job may run: the jobs
`engine-1` … `engine-3` (`.github/workflows/flatpak-engine.yml`) build it in
parts, passing compiled files on through ccache, and keep the finished module
in flatpak-builder's cache. Later runs take it from there until the module,
the base application or the SDK changes.

## Building locally

```bash
flatpak install flathub org.kde.Sdk//6.11 com.riverbankcomputing.PyQt.BaseApp//6.11 \
    org.freedesktop.Sdk.Extension.rust-stable//25.08 org.freedesktop.Sdk.Extension.node20//25.08
flatpak-builder --user --install --force-clean build-flatpak \
    packaging/flatpak/io.github.nullsector_2077.IKE-Browser.yml
flatpak run io.github.nullsector_2077.IKE-Browser
```

A local build compiles Chromium: hours, about 30 GB of disk and 16 GB of
memory. `--ccache` keeps the compiled files for the next build.

### Updating Qt WebEngine

When Flathub's `io.qt.qtwebengine.BaseApp` (branch 6.11) moves to a new Qt
release: in `qtwebengine/qtwebengine.json` the archive's version, address
and `sha512` (Qt publishes them; Gentoo's `dev-qt/qtwebengine/Manifest` lists
the same SHA-512), the base application's patches copied again into
`qtwebengine/patches/` with its list of patches and switches; the three
`*system-ffmpeg*` / `*no-openh264*` patches checked against the new source.
The engine jobs then build it once and cache it.

`tools/flatpak-sources.py` regenerates `generated/` after a change of
`ike-adblock/Cargo.lock` or of the pinned Python packages.

## Progress

- 2026-11-16, run 43974228106 (e6d7600): build, install, `--version`,
  libraries and AdBlock engine, and the engine report with Chromium's sandbox
  ON (as an ordinary user, Flatpak portal) all pass; H.264, AAC, VP9, AV1,
  Opus and MP3 decoded. The suite inside the sandbox: 184 passed, 24 skipped,
  1 failed (a test that gives a socket to another user: one user only in the
  sandbox's user namespace; fixed). **Blocker**: with the codec extension
  removed the bundle still decodes H.264 and AAC — the Qt WebEngine base
  application is built with `-DQT_FEATURE_webengine_proprietary_codecs=ON`
  and Chromium's own FFmpeg (`system_ffmpeg=OFF`), so its decoders are inside
  the bundle and the workflow does not keep it.
- 2026-11-17: run 43977320802 (5e5870d) green, but the bundle was not kept
  (the blocker above). Change: the manifest builds Qt WebEngine with the run
  time's FFmpeg (section "Codecs"); the workflow builds it in up to three
  chained jobs and checks the bundle's files for decoders.
- 2026-11-17, run 44001339255 (589c545): the engine configures with the run
  time's FFmpeg (7.1: libavcodec 61.19, without `av_stream_get_first_dts`,
  hence the two patches); GN stopped at OpenH264 (`use_system_openh264`: the
  SDK has no `openh264.pc`). Now no OpenH264 at all (section "Codecs").
- 2026-11-17: the owner's decision on codecs (above): this route, OpenH264
  off, plus Help → About's hint when the codec extension is missing (with
  translations and tests). README corrected on AAC (base run time) and on
  WebRTC (no software H.264 decoding either).
