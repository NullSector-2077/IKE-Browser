# Windows

**State: preview (1.2.0), not released.** I.K.E. is built, installed, started
and tested for Windows 10 / 11 (64-bit) by GitHub Actions on a Windows runner
(`.github/workflows/windows.yml`). Nobody has used it on a real Windows PC
yet: [WINDOWS-CHECKLIST.md](../WINDOWS-CHECKLIST.md) is the list for that
test. The installer is a download of the workflow run, never a release.

The first part of this page is what exists now; the study it grew from
("The run time" onwards, November 2026) follows unchanged, with a note where
the port answered one of its questions.

## What is implemented

Linux is untouched: every Windows part sits behind a `sys.platform ==
"win32"` branch in the module that needs it, and the calls into Windows
itself are in one small file, `ike/winapi.py` (ctypes; no new library).

| Area | On Windows | Checked automatically on the Windows runner |
|---|---|---|
| Folders (`ike/osinfo.py`, `ike_boot.py`) | settings: `%APPDATA%\ike-browser`; data (profile, bookmarks, vault, lists, updates): `%LOCALAPPDATA%\ike-browser\data`; cache: `%LOCALAPPDATA%\ike-browser\cache`. The `XDG_*` variables, when set, are still followed (the tests use them) | yes: paths, a real start without the variables, nothing written elsewhere in the home folder |
| Single instance (`ike/app.py`) | `QLocalServer` on a named pipe `ike-browser-<the user's SID>-<profile>`, open to the user only; a second start connects, asks Windows who owns the pipe, and hands its addresses over only if it is this user's | yes: hand-over, rubbish ignored, and a pipe made under that name by "somebody else" gets nothing |
| Desktop integration (`ike/plasma.py`) | off: there is no D-Bus. No error, no message; the four switches are not shown in Settings and keep their values | yes (`test_without_desktop_bus`, internal-error check of every test) |
| Notifications (`ike/osinfo.py`) | Qt's `QSystemTrayIcon.showMessage`: I.K.E.'s icon appears in the notification area while a message shows. Plain text, cut to Windows' lengths | text handling yes; a visible notification no (the runner has no desktop to show it on) |
| Reduced motion (`ike/effects.py`) | Windows' "Animation effects" switch (`SPI_GETCLIENTAREAANIMATION`) | yes (the call answers; switching it by hand: checklist) |
| Light / dark | Qt follows Windows' setting; "Follow the system" stays the default | the theme tests pass; the look is for the checklist |
| Identity shown to sites (`ike/osinfo.py`, `ike/shields.py`, `fingerprint.js`) | Chrome on Windows in every surface: user agent `Windows NT 10.0; Win64; x64`, `navigator.platform` `Win32`, Client Hints platform `Windows` with platform version `19.0.0` (Windows 11) or `10.0.0` (Windows 10), Chrome's version list for `win64`, the Firefox identity used for Google's sign-in, and Direct3D 11 names for the made-up graphics card | yes (`test_fingerprint.py` on Windows, `test_platform.py`) |
| Clipboard (`ike/passwords.py`) | a copied password carries Windows' three formats that keep it out of the clipboard history and the cloud clipboard | the formats are set: yes; that Win+V really omits it: checklist |
| Widevine (`ike/drm.py`) | **implemented, not verified in use**: Google's archive for Windows (`…-win-x64.zip`) is downloaded on request; `widevinecdm.dll` must be a complete 64-bit x86-64 DLL (PE check: machine, DLL flag, 64-bit header, every section inside the file) before it is kept, with its `.sig` file | the check and the archive handling: yes, with crafted, hostile and cut files. A real download and a playing service: no — see "Known limits" |
| Self-update (`ike/updater.py`, `ike_boot.py`) | unchanged design: signature (Ed25519), hash, unpack into `…\data\updates\versions\<version>.staging`, self-test, rename, used from the next start, roll-back. The installation folder is never written. The rename is tried again for a few seconds if Windows still holds a file. `min_system` is kept as it is (1.0.1) | yes: the whole of `test_updater.py`, also through the installed `ike-browser.exe` |
| Per-site resources (`ike/resources.py`) | **implemented** with Windows' own calls: private memory (`GetProcessMemoryInfo`) and CPU time (`GetProcessTimes`) of each page's process | yes (`test_resources.py`, `test_windows.py`) |
| Import from another browser (`ike/importer.py`) | Firefox, Chrome, Edge, Brave, Vivaldi, Chromium, Opera and others looked for under `AppData` | the locations: yes; a real profile: checklist |
| Default browser | the installer lists I.K.E. for Windows' "Default apps" (entries under `HKEY_CURRENT_USER` only); "Make I.K.E. the default browser" opens that page of Windows' settings, because Windows lets only the user choose | registry entries written and removed: yes; choosing it: checklist |
| Engine module | `ike_adblock.pyd`, built from `ike-adblock/` with Rust for MSVC; loaded by the same `vendor/adblock/__init__.py` | yes (Rust tests, `test_adblock.py`) |
| Sandbox | never switched off by I.K.E. on Windows (the only place that does it is the start as root on Linux). The tests run with it **on** | yes: the page process has a lower integrity level than the browser |

## The installer

Built by `packaging/windows/build.py` (see [BUILDING.md](../BUILDING.md)):

- **Python**: the embeddable CPython 3.13 from python.org, its SHA-256
  pinned in the build script. With its `._pth` file it loads modules only
  from the installation: no `PYTHONPATH`, no user site-packages.
- **Qt, Qt WebEngine, PyQt6, cryptography**: the official wheels from PyPI,
  each pinned to one version and one SHA-256 in
  `packaging/windows/requirements.txt` and installed with
  `pip --require-hashes --only-binary=:all: --no-deps`. The wheel layout is
  kept as it is (`python\Lib\site-packages\PyQt6\Qt6\…`).
- **Taken out**: Qt Multimedia and the FFmpeg libraries that come with it in
  the Qt wheel (`avcodec`, `avformat`, `avutil`, `swresample`, `swscale`,
  the multimedia plug-ins), and the `.debug` resource files. The build and
  the workflow fail if a codec library or a key file is still in the folder.
- **Launcher** `ike-browser.exe` (`packaging/windows/launcher/`, C, about a
  hundred lines): a windowed program — no console window — that loads the
  Python DLL next to it and runs `ike_boot.py` **inside its own process**.
  Chosen over starting `pythonw.exe` so that the task bar, Task Manager and
  a pinned shortcut show "I.K.E." with its icon instead of "Python", and
  over a freezing tool (PyInstaller) so that the files stay ordinary,
  readable Python and the self-update keeps working. It looks for Python
  nowhere else (not on `PATH`, not in the registry) and reads no environment
  variable.
- **Installer**: Inno Setup, `PrivilegesRequired=lowest` — for the current
  user, no administrator question — into `%LOCALAPPDATA%\Programs\I.K.E`
  (Windows does not allow a folder name that ends with a dot), with a
  Start-menu shortcut, an optional desktop shortcut and the optional
  "Default apps" entries.
- **Uninstaller**: removes the program folder, the shortcuts and its
  registry entries. It **leaves the user's data**
  (`%APPDATA%\ike-browser`, `%LOCALAPPDATA%\ike-browser`), as removing the
  package does on Linux. To delete the data too, delete those two folders.
- **Not signed** with a Windows (Authenticode) certificate: SmartScreen
  warns about an unknown publisher. The Ed25519 update key has nothing to do
  with that and never goes to GitHub Actions.

### Putting another engine in

The codec rule (ROADMAP) asks for H.264 / AAC through Windows' own decoders,
which needs I.K.E.'s own build of Qt WebEngine; that is separate work
(branch `windows/engine`). The installer is prepared for it and nothing
more: `build.py --engine DIR` copies files laid out like the wheel
(`PyQt6\Qt6\bin\Qt6WebEngineCore.dll`, `PyQt6\Qt6\resources\…`) over
the files of the same names, refuses anything that is not a replacement, and
records each replaced file with its hash in `build-info.json`. Without
`--engine`, the installer carries the official engine.

## Codecs in this build

Plainly: **this build does not play H.264 or AAC.** It ships the official Qt
WebEngine, built by the Qt Company without proprietary codecs, and I.K.E.
ships no proprietary codec.

| Plays | Does not play |
|---|---|
| VP8, VP9, AV1 (video); Opus, Vorbis, FLAC, MP3 (audio); WebM, Ogg, and MP4 files that hold only those | H.264, AAC, HEVC — most `.mp4` / `.m4a` files and the sites that offer nothing else |

Measured on the Windows runner with the installed copy (workflow step
"Engine check", the same question Help → About asks): H.264 no, AAC no, HEVC
no; VP9, AV1, Opus, MP3 yes. This answers point 3 of the study below: the
stock build does **not** hand H.264 to Windows' decoders.

## Known limits and what is still to verify

- Everything in [WINDOWS-CHECKLIST.md](../WINDOWS-CHECKLIST.md): the look,
  real windows and task bar, visible notifications, sound, real websites,
  hardware video decoding, SmartScreen, "Default apps".
- **Widevine**: not tried with a real download or a real service. Services
  such as Netflix are expected **not** to work in this build: they need
  H.264 / AAC, and on Windows Widevine also verifies the browser's own
  signature, which an unsigned program does not have.
- **Media keys and Windows' media controls** (the counterpart of MPRIS),
  toast notifications with buttons, download progress in the task bar and
  jump lists are not written.
- **Certificates of I.K.E.'s own downloads** (filter lists, the Chrome
  version, updates, user scripts): Python checks them against Windows'
  certificate store. On a freshly installed Windows that store can lack a
  root certificate until some program has needed it; a download then fails
  with a certificate error and is tried again later. Pages in the browser
  are not affected (the engine has its own checks). To verify on a real PC.
- **WebGL on a PC without a graphics driver**: on the runner (no graphics
  card, Direct3D in software) the engine's compositing loses its Direct3D
  context after a page or two and WebGL is then missing on later pages. The
  fingerprinting test therefore composites in software there (a switch of
  that test only; see [TESTING.md](../TESTING.md)). The browser itself is
  not given that switch. Expected not to happen with a real graphics card;
  to verify on a real PC (checklist, section 5). Virtual machines without a
  graphics driver may see it.
- `ike-browser.exe --version` prints nothing in a terminal by itself (a
  windowed program has no console): use `ike-browser.exe --version | more`.
- A running I.K.E. holds its files: the installer and the uninstaller ask to
  close it first.
- The vault and exported password files have no "owner only" mode as on
  Linux; they lie in the user's profile, which other ordinary users cannot
  read. Wrapping the vault key with Windows' data protection (DPAPI) is not
  done.
- Windows on ARM, 32-bit Windows and Windows older than 10 (1809) are not
  built.
- Restarting I.K.E. from itself (after a change that needs it) starts the
  installed launcher again. Seen while reading the code for this, not run:
  on Linux the same restart, from a copy installed by a self-update, looks
  for `ike_boot.py` next to that copy, where there is none (`ike/app.py`,
  end of `main`). Left as it is — Linux was not to change in this step —
  and noted in ROADMAP.md.

---

# The study (November 2026)

Nothing below was run on Windows when it was written. The contents of the
Windows packages of Qt were listed (not executed) in the environment of this
study and are marked *measured*; everything about behaviour was *to verify*
on a real Windows 10 / 11 system. Where the port has since answered a
question, the first part of this page says so.

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
