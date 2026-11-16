# Linux: distributions and package formats

Read [README.md](README.md) first for how sources, measurements and "to
verify" are marked. Versions were read on 2026-11-16.

## What I.K.E. needs from the system

| Need | Minimum | Why |
|---|---|---|
| Qt WebEngine | **6.8** | `QWebEnginePermission` and `permissionRequested` (new in Qt 6.8) are used without a fallback; client hints (6.8) and the extension manager (6.10) are optional in the code |
| PyQt6 and PyQt6-WebEngine | matching the Qt of the system | bindings must be built for the installed Qt |
| Python | 3.10 | the engine module is built for the stable ABI from 3.9; PyQt6's own wheels start at 3.10 (*measured*: tag `cp310-abi3`) |
| `cryptography`, `jeepney` | any current | vault, update signatures, D-Bus |
| glibc (only for a self-contained Qt from PyPI) | 2.34 | *measured*: the wheels are tagged `manylinux_2_34` |
| Kernel | user namespaces (3.8) and seccomp-bpf (3.5) | Chromium's sandbox [Q3] |
| Run-time libraries of Qt WebEngine | NSS, fontconfig, D-Bus, ALSA, libdrm / GBM, EGL / GL, X11 / xkbcommon libraries, Kerberos | [Q3]; *measured* with `ldd` on the PyPI build, which finds all of them on a desktop system |
| Rust (build only) | stable | the engine module; never needed by the user |

Fonts, certificates, sound and graphics need nothing special: Qt WebEngine
uses fontconfig, the NSS / system certificate store, PulseAudio or PipeWire
through its PulseAudio interface, and the system's Mesa. Wayland and X11 are
both served by Qt's platform plug-ins (`qwayland`, `qxcb`; *measured*: both are
in the PyPI build). Hardware video decoding (VA-API) depends on how the
distribution built Qt WebEngine and is *to verify* per distribution.

## The distributions

| Distribution | Qt WebEngine in its packages | PyQt6-WebEngine | Enough for I.K.E. (≥ 6.8)? | Codecs (H.264 / AAC) in Qt WebEngine |
|---|---|---|---|---|
| Arch Linux / CachyOS | 6.11.x (6.12 in testing) [D1] | 6.11.x | **yes** — the platform of today | yes: built against the system `ffmpeg` [D1]; what the tests on the owner's system show |
| Debian 13 "trixie" (stable) | 6.8.2 [D2] | 6.9.0 [D3] | **yes, at the minimum** | *to verify* |
| Debian 12 "bookworm" | 6.4.2 [D2] | 6.4.0 [D3] | no | — |
| Debian testing / unstable | 6.10 – 6.11 [D2][D4] | 6.11 [D4] | yes | *to verify* |
| Ubuntu 26.04 LTS | 6.10 [D5] | 6.10.0 [D5] | **yes** | *to verify* |
| Ubuntu 24.04 LTS "noble" | older than 6.8 (*to verify* the exact version) | 6.6.0 [D5] | no | — |
| Linux Mint 22.x | Ubuntu 24.04's packages [D6] | 6.6.0 | no | — |
| Linux Mint 23 (when released, on Ubuntu 26.04) | 6.10 expected | 6.10 | expected yes, *to verify* | *to verify* |
| Fedora 43 | 6.10.3 [D7] | 6.10.x [D7] | **yes** | not by default: Fedora builds without patent-encumbered codecs [D8]; *to verify* what RPM Fusion adds for Qt 6 |
| Fedora 44 / 45 | 6.11.x [D7] | 6.11.0 [D7] | yes | same |

Three things beyond version numbers:

1. **Debian does not give security support to Qt WebEngine in stable.** The
   release notes say that applications using `qtwebengine` are not covered
   by security support, and that for browsers only current versions are a
   workable answer [D9]. A browser whose engine is frozen for two years is
   not something I.K.E. should call safe. On Debian stable the Flatpak, whose
   run time follows Qt's releases, is the better engine even where the native
   package would run.
2. **Ubuntu 23.10 and later restrict unprivileged user namespaces through
   AppArmor** [D10][D11]. Programs from the archive get a profile — the list
   of profiles shipped by Ubuntu includes one for `QtWebEngineProcess`
   [D12] — so the distribution's Qt WebEngine keeps its sandbox. A Chromium
   that the user unpacks somewhere (an AppImage, a pip-installed Qt) has no
   profile and its sandbox cannot start; the usual advice found on the web,
   `--no-sandbox`, is exactly what I.K.E. must not do. *To verify* on Ubuntu
   24.04 and 26.04.
3. **Codecs are decided when Qt WebEngine is built**, not by what is
   installed later: Chromium fixes its list of codecs at compile time [D8]
   [Q1]. Arch builds with the proprietary codecs and the system FFmpeg; the
   Qt Company's own binaries (and so the PyPI wheels) do not — *measured*:
   `canPlayType` answers "no" for H.264, H.265 and AAC and "probably" for
   VP8, VP9, AV1, Opus, Vorbis, FLAC and MP3. The same small test page is the
   check to run on every distribution before promising video.

## Measured on each distribution (2026-11-16)

The workflow "Linux distributions" runs I.K.E. in a container of each
distribution with that distribution's own Python, Qt, PyQt and Qt WebEngine
packages; "Linux packages" builds, installs, starts and tests the DEB and RPM
packages. `tools/engine-report.py --decode tests/media` gives the engine's
versions, what it declares (`canPlayType`, Media Source) and what it really
decodes (a two-second clip per format: video played, audio decoded through
Web Audio).

| Distribution | Qt WebEngine | Chromium base (security patches up to) | Declares H.264 / AAC | Decodes H.264 / AAC | VP9, AV1, Opus, MP3 |
|---|---|---|---|---|---|
| Arch Linux | 6.140.0 | 140 (157.0.8103.50) | yes / yes | yes / yes | yes |
| Ubuntu 26.04 | 6.10.2 | 134 (144.0.7559.96) | yes / yes | yes / yes | yes |
| Debian 13 | 6.8.2 | 122 (132.0.6834.111) | yes / yes | yes / yes | yes |
| Fedora 43 | 6.10.3 | 134 (146.0.7680.164) | yes / yes | **no** / yes | yes |
| PyPI (Qt's own build, tests only) | 6.140.0 | 140 (157.0.8103.50) | no / no | no / no | yes |

- **Fedora** builds its Qt WebEngine with H.264 enabled on top of its own
  FFmpeg, which has no H.264 decoder: the engine says it plays H.264 and then
  does not. Help → About shows what the engine declares; a site offering
  only H.264 will not play on stock Fedora. Adding a decoder to the system is
  the user's choice and is not done or suggested by I.K.E.
- **Debian 13**: the engine's Chromium base (122) is the oldest of the four
  and, as Debian's release notes say, not covered by security support in
  stable. The native package works; the Flatpak is still the recommendation
  there.
- In containers Chromium's sandbox cannot start; the packages keep it on.
  For the WebGL part of the fingerprinting test the tests choose software
  WebGL switches that work on each engine (`tests/conftest.py`,
  `SOFTWARE_WEBGL`): Debian's engine has no SwiftShader and gives WebGL only
  through Mesa with GPU compositing.

## Package formats compared

| | PKGBUILD / AUR | DEB | RPM | Flatpak | AppImage |
|---|---|---|---|---|---|
| Engine comes from | system Qt | system Qt | system Qt | KDE run time + Qt WebEngine base application [F1] | bundled Qt (PyPI or own build) |
| Size of I.K.E.'s package | about 2 MiB (*measured*) | similar | similar | I.K.E. small; the KDE run time is downloaded once (hundreds of MiB) and shared with other KDE Flatpaks | about 200 MiB download, 490 MiB unpacked (*measured* for the PyPI Qt: wheels of 84 + 111 + 8 MiB) |
| Engine security updates | the distribution (fast on Arch, Fedora; **none promised on Debian stable** [D9]) | same | same | Flathub rebuilds of the base application for each KDE run time | I.K.E. would have to ship every Qt WebEngine patch release itself |
| Chromium sandbox | works | works (Ubuntu: archive profile [D12]) | works | works through the base application's Flatpak support [F2] | **fails on Ubuntu ≥ 23.10** without a root-installed profile [D10][D11] |
| H.264 / AAC | as the distribution builds it | as the distribution builds it | not by default on Fedora [D8] | through the Freedesktop codecs extension (`ffmpeg-full`, now `codecs-extra`) [F3][F4]; *to verify* with the base application of the chosen run time | no with the PyPI build (*measured*); yes only with an own build of Qt WebEngine and the licence question settled |
| Desktop integration (KRunner, KDE Connect, media keys, default browser, `xdg-open`) | full | full | full | through portals and D-Bus permissions; KRunner runner file and native paths need work; *to verify* each | full, but no installation: no desktop file, icon or default-browser entry until the user integrates it |
| I.K.E.'s self-update of the Python part | yes (as today) | yes | yes | **no**: the application folder is read-only; updates come from the repository | possible in principle; replaces a whole 200 MiB file otherwise |
| Widevine | user's folder, as today | same | same | *to verify*: path inside the sandbox | same as native |
| Maintenance for one person | one file, one distribution | a `debian/` folder per release family; a repository or PPA to host and sign | a spec file; Copr can build and host | one manifest; Flathub builds, hosts and signs; review to enter | a build script; hosting and update channel are ours; glibc ≥ 2.34 only |
| Reaches | Arch family | Debian 13, Ubuntu 26.04, Mint 23 | Fedora 43+ | every distribution with Flatpak, including Ubuntu 24.04, Mint 22, Debian 12 | glibc ≥ 2.34, with the sandbox problem above |

## Strategy proposed

Not the easiest format, but the one where the engine is patched by someone
who can keep up, the sandbox stays on and video plays:

1. **Arch / CachyOS: PKGBUILD**, as now; AUR when the owner decides.
2. **Flatpak on Flathub as the second target**, before DEB and RPM. One
   manifest reaches every distribution, including the three that cannot run
   I.K.E. natively (Ubuntu 24.04, Mint 22, Debian 12) and Debian stable,
   where the native engine gets no security support. The engine follows the
   KDE run time; the sandbox works; the codecs extension exists. Its price
   is the integration work (portals, D-Bus names, no self-update, Widevine
   path), which is real and listed in [porting-plan.md](porting-plan.md).
3. **Native DEB for Ubuntu 26.04 (and Mint 23), native RPM for Fedora 43+**,
   after the Flatpak: small packages on the system's Qt, with the
   integration I.K.E. has today. For Debian 13 a native package is possible
   (6.8.2 is the minimum) but the Flatpak is the recommendation, for the
   reason in point 1 of the previous section.
4. **No AppImage** as an offered format: without an own, regularly rebuilt
   Qt WebEngine it has neither H.264 nor a sandbox on Ubuntu, and shipping
   it would put the whole engine's security updates on one maintainer.
5. **No mixing**: a native package uses only the system's Qt and PyQt; the
   Flatpak only the run time's. I.K.E.'s component manager
   ([component-manager.md](component-manager.md)) never downloads Qt
   libraries next to a system Qt.

## Sources

- [Q1] Qt WebEngine Features (audio and video codecs; the option
  `-webengine-proprietary-codecs`; decoding done by Chromium):
  https://doc.qt.io/qt-6.11/qtwebengine-features.html
- [Q2] Deploying Qt WebEngine Applications:
  https://doc.qt.io/qt-6/qtwebengine-deploying.html
- [Q3] Qt WebEngine Platform Notes (build requirements, run-time libraries,
  sandbox requirements): https://doc.qt.io/qt-6.10/qtwebengine-platform-notes.html
- [Q4] Chromium versions in Qt WebEngine: https://wiki.qt.io/QtWebEngine/ChromiumVersions
- [D1] Arch Linux packages `qt6-webengine`, `python-pyqt6-webengine`:
  https://archlinux.org/packages/extra/x86_64/qt6-webengine/
- [D2] Debian package tracker, `qt6-webengine`: https://tracker.debian.org/pkg/qt6-webengine
- [D3] Debian packages, `pyqt6-webengine` (bookworm 6.4.0, trixie 6.9.0):
  https://packages.debian.org/webengine
- [D4] Debian package tracker, `pyqt6-webengine`: https://tracker.debian.org/pkg/pyqt6-webengine
- [D5] Ubuntu packages, `python3-pyqt6.qtwebengine`:
  https://packages.ubuntu.com/search?keywords=python3-pyqt6.qtwebengine
- [D6] Linux Mint 22.1 release notes ("Linux Mint 22 is based on Ubuntu
  24.04"): https://linuxmint.com/rel_xia.php
- [D7] Fedora packages, `qt6-qtwebengine` and `python-pyqt6-webengine`:
  https://packages.fedoraproject.org/pkgs/qt6-qtwebengine/qt6-qtwebengine/
  and https://packages.fedoraproject.org/pkgs/python-pyqt6-webengine/python3-pyqt6-webengine/
- [D8] Red Hat Bugzilla 2053868, "qtwebengine: Use system ffmpeg libraries"
  (the codec list is fixed at compile time; Fedora's build and the
  "freeworld" one): https://bugzilla.redhat.com/show_bug.cgi?id=2053868
- [D9] Debian release notes, "Security status of web browsers and their
  rendering engines":
  https://www.debian.org/releases/trixie/release-notes/issues.en.html#security-status-of-web-browsers-and-their-rendering-engines
- [D10] Ubuntu 24.04 LTS release notes, "Unprivileged user namespace
  restrictions": https://discourse.ubuntu.com/t/ubuntu-24-04-lts-noble-numbat-release-notes/39890
- [D11] Chromium documentation, "AppArmor User Namespace Restrictions vs.
  Chromium Developer Builds":
  https://chromium.googlesource.com/chromium/src/+/main/docs/security/apparmor-userns-restrictions.md
- [D12] Launchpad bug 2046844 and the AppArmor package changes that add the
  profiles (the listing of `/etc/apparmor.d` there includes
  `QtWebEngineProcess`): https://bugs.launchpad.net/bugs/2046844
- [F1] Qt WebEngine base application on Flathub:
  https://github.com/flathub/io.qt.qtwebengine.BaseApp ; PyQt base
  application: https://github.com/flathub/com.riverbankcomputing.PyQt.BaseApp
- [F2] Notes of the base application on Chromium's sandbox inside Flatpak:
  https://github.com/tinywrkb/io.qt.qtwebengine.BaseApp/wiki
- [F3] KDE bug 403713, "QWebEngine in KDE flatpak runtime cannot play h.264
  videos?": https://bugs.kde.org/show_bug.cgi?id=403713
- [F4] LWN, the Freedesktop SDK's `codecs-extra` extension:
  https://lwn.net/Articles/1015408
