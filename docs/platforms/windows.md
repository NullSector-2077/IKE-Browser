# Windows

Nothing of this was run on Windows. The contents of the Windows packages of
Qt were listed (not executed) in the environment of this study and are
marked *measured*; everything about behaviour is *to verify* on a real
Windows 10 / 11 system.

## The run time

On Windows there is no system Qt: I.K.E. has to bring Python, Qt, Qt
WebEngine and PyQt with it. Two ways to get them:

| | The Qt Company's binaries (the PyPI wheels of PyQt6 are a repackaging of them [W1]) | Own build of Qt WebEngine |
|---|---|---|
| Effort | none: `pip install` at build time | Visual Studio 2022, a current Windows SDK, no MinGW [W2]; hours of build time and tens of GiB of disk for every Qt WebEngine patch release |
| Engine updates | a new wheel for each Qt WebEngine release; I.K.E. ships a new installer | I.K.E. builds and ships each one |
| H.264 / AAC | not expected: proprietary codecs are off unless Qt WebEngine is configured with `-webengine-proprietary-codecs` [W3]. *Measured* on the Linux wheel of the same release: `canPlayType` says no for H.264, H.265 and AAC. *To verify* on Windows with the same page | possible with that option; the documentation warns that distributing the codecs needs licences [W3] |
| Repeatable and verifiable | yes: wheel versions pinned with their hashes (`pip install --require-hashes`), the same input for every build | only with a fixed tool chain image; much harder to let others verify |

*Measured* content of the Windows wheels (Qt 6.12.0, Qt WebEngine 6.140.0):

| Piece | Where | Size |
|---|---|---|
| `Qt6WebEngineCore.dll` (Chromium, with its media code inside) | `PyQt6/Qt6/bin` | 195 MiB |
| `QtWebEngineProcess.exe` (renderer, GPU and network helper processes) | `PyQt6/Qt6/bin` | small |
| `Qt6WebEngineWidgets.dll`, `Qt6WebEngineQuick*.dll` | `PyQt6/Qt6/bin` | small |
| Resources: `qtwebengine_resources*.pak`, `qtwebengine_devtools_resources.pak`, `icudtl.dat`, `v8_context_snapshot.bin` | `PyQt6/Qt6/resources` | about 25 MiB needed; the rest of the folder's 101 MiB are `.debug` variants used only by debug builds [W4] |
| Locales (`*.pak`) | `PyQt6/Qt6/translations/qtwebengine_locales` | 44 MiB; could be cut to I.K.E.'s seven languages plus English |
| Qt itself (Core, Gui, Widgets, Network, Svg, WebChannel, Qml / Quick as Qt WebEngine needs them, platform plug-in `qwindows`) | `PyQt6-Qt6` wheel | 189 MiB unpacked for all of Qt; I.K.E. needs a part |
| Visual C++ run time (`vcruntime140*.dll`, `msvcp140*.dll`, `concrt140.dll`) | inside the `PyQt6-Qt6` wheel, next to the Qt DLLs | present; Qt WebEngine needs version 14.28 or later [W4] |
| `opengl32sw.dll` (software OpenGL), `d3dcompiler_47.dll` | `PyQt6-Qt6` wheel | 20 MiB, 4 MiB |
| `avcodec-63.dll`, `ffmpegmediaplugin.dll` | `PyQt6-Qt6` wheel | belongs to **Qt Multimedia**, not to Qt WebEngine; I.K.E. does not use Qt Multimedia and should not ship them |
| Downloads | wheels | 76 MiB (Qt) + 127 MiB (Qt WebEngine) |

A first estimate for an installer: 150 – 200 MiB compressed, about 400 MiB
installed, most of it one DLL.

## Deployment

- Qt's documentation describes what a Qt WebEngine application must carry:
  the libraries, `QtWebEngineProcess`, the resources and the locales, found
  through fixed relative paths or the overrides `QTWEBENGINEPROCESS_PATH`,
  `QTWEBENGINE_RESOURCES_PATH`, `QTWEBENGINE_LOCALES_PATH` [W4]. For C++
  programs `windeployqt` collects them [W4]. For a Python program the wheel
  layout already is a working deployment: keep `PyQt6/Qt6` as it is.
- Python: the embeddable distribution of CPython from python.org, with
  I.K.E.'s `ike/` package and the wheels unpacked into its `site-packages`
  — no freezing tool needed, the files stay readable and the Python
  self-update keeps working. (PyInstaller is the alternative; it hides the
  layout and tends to trigger antivirus heuristics. *To verify* both.)
- Launcher: a small `ike-browser.exe` (the C launcher adapted, or a few
  lines of Rust) that starts the embedded Python with `ike_boot.py`, carries
  the icon and the version resource and sets the AppUserModelID.
- Installer: per-user by default (no administrator), into
  `%LOCALAPPDATA%\Programs\ike-browser`; registers the uninstall entry and
  the "default browser" capabilities (`RegisteredApplications`,
  `URLAssociations`). MSIX is the alternative with clean install / uninstall
  and store-style updates, at the price of its container rules. *To verify*.
- Signing: Windows judges downloaded programs by their Authenticode
  signature (SmartScreen). That needs a code-signing certificate from a
  certificate authority — a separate key and a recurring cost, unrelated to
  I.K.E.'s Ed25519 update key. The update key keeps doing what it does:
  I.K.E. verifying I.K.E.'s own updates. Neither key ever goes to the
  repository or to GitHub Actions; signing the installer stays a step on the
  owner's computer (or a hardware token).
- Sandbox: Chromium's sandbox on Windows is part of Qt WebEngine and needs
  no installation step. *To verify* that nothing in I.K.E.'s start-up
  switches it off (today the only such place is the start as root on Linux).

## What in I.K.E. is Linux-only today

The code has no branch for another system. From the code review:

| Area | Today | On Windows |
|---|---|---|
| Folders (`ike/config.py`, `ike/osinfo.py`) | XDG | `%APPDATA%`, `%LOCALAPPDATA%` (Qt's `QStandardPaths` gives them) |
| Single instance (`ike/app.py`) | Unix socket in `XDG_RUNTIME_DIR`, owner check with `getuid` | `QLocalServer` named pipe, restricted to the user (`UserAccessOption` already set) |
| Desktop integration (`ike/plasma.py`, `ike/desktopbus.py`) | D-Bus: MPRIS, KRunner, notifications with progress, KDE Connect | none of it exists; Windows equivalents (media transport controls, toast notifications, jump lists) are new code or left out at first |
| Notifications (`ike/osinfo.py`) | `notify-send` | Qt's `QSystemTrayIcon.showMessage` or toasts |
| Reduced motion, theme (`ike/effects.py`, `ike/themes.py`) | `kdeglobals`, GTK settings | `SPI_GETCLIENTAREAANIMATION`; Qt 6.5+ follows the Windows light / dark setting |
| Identity presented to sites (`ike/osinfo.py`, `ike/chromever.py`) | Chrome on Linux | must present Chrome on Windows, consistently in every surface the fingerprinting tests check |
| File permissions of the vault and exports (`ike/passwords.py`) | mode 0600 | the user's profile folder is already private; optional DPAPI wrapping of the vault key |
| Clipboard secret hint | Klipper's MIME hint | Windows' `ExcludeClipboardContentFromMonitorProcessing` / `CanIncludeInClipboardHistory` formats |
| Widevine (`ike/drm.py`) | ELF check, `libwidevinecdm.so` | PE check, `widevinecdm.dll` |
| Self-update (`ike/updater.py`, `ike_boot.py`) | rename over files in use | Windows locks loaded files: the staged-folder design already avoids replacing files in use, *to verify* |
| Engine module | `ike_adblock.abi3.so` | `ike_adblock.pyd`, built by the Rust MSVC tool chain; the code has nothing Linux-specific |
| Resource limits per site (`ike/resources.py`) | `/proc` | `psutil` or Windows APIs |
| Tests | `offscreen`, D-Bus stand-ins | the suite on a Windows runner; the Plasma tests skipped; a GitHub `windows-latest` job is the natural place |

## Codecs

What the documentation says, and what follows:

1. Qt WebEngine plays H.264, AAC and the MP4 container **only if built with
   proprietary codecs enabled**; decoding is done by Chromium; distributing
   such a build needs licences [W3].
2. **Qt Multimedia using Media Foundation or FFmpeg says nothing about Qt
   WebEngine.** They are separate modules with separate media code; the
   `avcodec` DLL in the Qt wheel belongs to Qt Multimedia (*measured*).
3. Whether a Qt WebEngine built **without** proprietary codecs can still
   play H.264 on Windows by handing the stream to the system's decoders: no
   statement for it was found in Qt's documentation; point 1 says the
   opposite. Treat it as **no** until the test page says otherwise on a real
   Windows system. This is the first thing to verify, because it decides the
   whole Windows plan.
4. What plays without proprietary codecs (*measured* on Linux, expected the
   same): VP8, VP9, AV1, Opus, Vorbis, FLAC, MP3. Large video sites that
   offer VP9 / AV1 work; sites that offer only H.264 / AAC — many news,
   social and conferencing sites — do not.

### Matrix

Not legal advice; no definitive statement. "Check" means: ask someone
qualified before shipping.

| Component | Ship inside I.K.E. | Use what the system has | Needs checks or a licence | Do not ship |
|---|---|---|---|---|
| Qt (LGPL-3.0 / GPL), as the Qt Company's binaries | yes, with the licence texts, the source offer and replaceable DLLs (they are separate files) | — | follow the LGPL / GPL obligations [W5] | — |
| PyQt6, PyQt6-WebEngine (GPL-3.0) | yes: I.K.E. is GPL-3.0-or-later | — | — | — |
| Qt WebEngine with Chromium, **without** proprietary codecs | yes; ship the third-party licence list Qt provides [W5] | — | — | — |
| FFmpeg code inside Qt WebEngine (free codecs only) | yes, as part of the above (LGPL build) | — | — | — |
| H.264 decoding | — | Windows has licensed decoders, but Qt WebEngine is not documented to use them (point 3) | a build with `-webengine-proprietary-codecs`: patent licences (the H.264 pool administered by Via LA; terms, thresholds and expiry differ by country) | an own build with H.264, before that question is answered |
| AAC decoding | — | as H.264 | separate AAC patent licence programme; same caution | as H.264 |
| OpenH264 (Cisco) | — | — | Cisco's royalty cover applies to Cisco's own binary as downloaded from Cisco, under its conditions [W6]; Qt WebEngine can be built to use a system OpenH264 [W2], which still needs the proprietary-codecs build and covers H.264 only, not AAC | bundling a rebuilt OpenH264 as if covered |
| H.265 / HEVC | — | Windows sells its own extension | separate pools | yes: do not ship |
| VP8, VP9, AV1, Opus, Vorbis, FLAC | yes (royalty-free by their licensors' terms) | — | — | — |
| MP3 | yes (in the standard build; patents expired) | — | — | — |
| Widevine CDM | — | — | Google's licence; I.K.E. only downloads it from Google when the user asks | yes: never inside the installer |
| Visual C++ run time | yes, as Microsoft's redistributable files (app-local or the redistributable installer) | often already installed | Microsoft's redistribution terms | — |
| Python (PSF licence) | yes | — | — | — |

### The honest options for Windows video

- **A. Ship without H.264 / AAC**, say so plainly in the README and in
  Help → About (the codec check of the component manager), and let the
  repair assistant explain a video that does not play. Legally the simplest;
  many sites will not play.
- **B. Own build with proprietary codecs** after the licence question is
  answered by someone qualified. Technically heavy and a permanent duty to
  rebuild for every Chromium security release.
- **C. Wait for the test of point 3.** If the stock build can decode through
  Windows after all, A becomes acceptable at once.

Recommendation: verify C first; plan for A; do not start B without the
answer on licences.

## Sources

- [W1] Riverbank Computing, PyQt mailing list, on the Qt wheels being the Qt
  Company's binaries repackaged: https://www.riverbankcomputing.com/pipermail/pyqt/
- [W2] Qt WebEngine Platform Notes (Windows build requirements, optional
  system FFmpeg / OpenH264): https://doc.qt.io/qt-6.10/qtwebengine-platform-notes.html
- [W3] Qt WebEngine Features, "Audio and Video Codecs":
  https://doc.qt.io/qt-6.11/qtwebengine-features.html
- [W4] Deploying Qt WebEngine Applications (files to deploy, search paths
  and overrides, debug resources, Visual C++ Redistributable 14.28):
  https://doc.qt.io/qt-6.11/qtwebengine-deploying.html
- [W5] Qt WebEngine Licensing: https://doc.qt.io/qt-6/qtwebengine-licensing.html
- [W6] OpenH264, binary licence: https://www.openh264.org/BINARY_LICENSE.txt
