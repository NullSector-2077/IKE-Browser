# Porting plan

Per platform: what already works, what must change, which tests decide.
Complexity is technical effort for one maintainer: **low** (days),
**medium** (weeks), **high** (months, or a permanent duty).

A platform is not done because the code looks compatible. It is done when
the test suite passes **on that platform**, the checks listed below were run
by hand on a real installation, and updates have been exercised once from
one version to the next.

## The check every platform starts with

Before any packaging work, on a real installation of the platform, with its
own Qt:

1. `python3 -c "from PyQt6.QtWebEngineCore import qWebEngineVersion, qWebEngineChromiumVersion, qWebEngineChromiumSecurityPatchVersion as p; print(qWebEngineVersion(), qWebEngineChromiumVersion(), p())"`
   — the engine is 6.8 or later, and how far behind its security patches are.
2. I.K.E. from the repository starts, Help → About shows no sandbox warning.
3. The codec page (`canPlayType` for H.264, AAC, VP9, AV1, Opus) — what video
   will play.
4. `python3 -m pytest` — the whole suite, on that system's Qt.

These four answers replace most of the "to verify" marks of this study.

## Arch Linux / CachyOS

| | |
|---|---|
| State | Supported: built, packaged, tested (automatic tests on PyPI's Qt; the owner's daily use on Arch's) |
| Dependencies | `python`, `python-pyqt6`, `python-pyqt6-webengine`, `qt6-webengine`, `qt6-webchannel`, `qt6-svg`, `python-cryptography`, `python-jeepney` |
| Format | PKGBUILD; AUR when the owner decides |
| Qt WebEngine | the system's, with the system's FFmpeg |
| Component manager | Python part (existing updater); later Widevine through signed manifests |
| Codecs and media | as Arch builds them: H.264 / AAC available |
| Updates | pacman for the package; I.K.E.'s signed self-update for the Python part |
| Signing | Ed25519 release key (owner only); for the AUR nothing more |
| Still to do | AUR: `PKGBUILD` with a real `source=` (the release tarball) and checksums instead of building from the working tree; `.SRCINFO`; decide whether `ike-browser-bin` (the built package) is offered too |
| Tests needed | the suite in an Arch container in the workflow (today the workflow builds the package on Ubuntu with dependency checks off) |
| Complexity | **low** |

## Flatpak (Ubuntu 24.04, Linux Mint 22, Debian 12 and 13, and everything else)

| | |
|---|---|
| State | Nothing exists |
| Dependencies | `org.kde.Platform` (current 6.x), the PyQt base application on Flathub, which brings PyQt6, PyQt6-WebEngine and the Qt WebEngine base application; `cryptography` and `jeepney` as Python modules in the manifest; Rust SDK extension at build time for the engine module |
| Format | one manifest, built and hosted by Flathub |
| Qt WebEngine | the base application's, with its Flatpak support for Chromium's sandbox |
| Component manager | Widevine and dictionaries only, in the application's own data folder; **no Python self-update** (the application folder is read-only; Flathub delivers updates) — `ike_boot.py` must detect the Flatpak and switch the updater off |
| Codecs and media | through the Freedesktop codecs extension; to be confirmed with the codec page inside the Flatpak |
| Updates | Flathub |
| Signing | Flathub signs the repository; I.K.E.'s key is not involved |
| Problems to solve | paths (`~/.var/app/…`: already XDG, should just work); the single-instance socket (inside the sandbox: fine); D-Bus names to own or talk to (MPRIS, notifications, KDE Connect, KRunner) must be declared one by one; KRunner's runner file cannot be written to the host; opening downloads and "show in folder" through portals; file dialogs through the portal (Qt does it); pages opened from files see only what the portal grants — the local-file rules of 1.0.3 need a second look there; default-browser registration through the exported desktop file; Widevine's path; which base-application version tracks which Qt WebEngine, and how fast it follows security releases |
| Tests needed | the suite inside `flatpak-builder --run`; by hand: sandbox on, codecs, downloads, default browser, each D-Bus feature |
| Complexity | **medium** |

## Ubuntu 26.04 LTS and Linux Mint 23 (native DEB)

| | |
|---|---|
| State | Should run from the repository (Qt 6.10) — *to verify* with the four checks |
| Dependencies | `python3-pyqt6`, `python3-pyqt6.qtwebengine`, `python3-pyqt6.qtsvg`, `python3-pyqt6.qtwebchannel`, `python3-cryptography`, `python3-jeepney`, `libnotify-bin` (names to confirm) |
| Format | DEB built with a `debian/` folder; hosted in a signed APT repository or a PPA |
| Qt WebEngine | Ubuntu's; sandbox through Ubuntu's AppArmor profile for `QtWebEngineProcess` — to confirm that it also applies when the process is started by I.K.E. |
| Component manager | as Arch |
| Codecs and media | as Ubuntu builds Qt WebEngine — unknown until the codec page is run |
| Updates | APT for the package; I.K.E.'s self-update for the Python part (the `__min_system__` rule already separates the two) |
| Signing | a GPG key for the APT repository (a second key, owner only) or Launchpad's PPA signing |
| Problems to solve | Python version (stable ABI module: fine); Plasma features on GNOME / Cinnamon: every D-Bus feature already does nothing without its service, to be confirmed; the theme follows Qt's platform theme, which on GNOME needs `qt6-gtk-platformtheme` or looks foreign; Mint 23 does not exist yet |
| Tests needed | the suite on Ubuntu 26.04 with **Ubuntu's** Qt packages (the workflow today uses PyPI's Qt on Ubuntu 24.04, which proves nothing about Ubuntu's Qt); by hand on Kubuntu and on stock Ubuntu |
| Complexity | **medium** (packaging and hosting more than code) |

## Debian 13

| | |
|---|---|
| State | At the minimum Qt (6.8.2) — *to verify* |
| Recommendation | **Flatpak**, because Debian's release notes exclude Qt WebEngine from security support in stable. A native DEB (the Ubuntu one, rebuilt) is technically possible and can be offered with that warning |
| Problems to solve | anything in I.K.E. that quietly needs more than 6.8 will show up here first: run the suite on Debian 13's Qt before deciding |
| Complexity | **low** on top of the Ubuntu DEB; the decision is about security, not effort |

## Fedora 43 and later (native RPM)

| | |
|---|---|
| State | Should run from the repository (Qt 6.10 / 6.11) — *to verify* |
| Dependencies | `python3-pyqt6`, `python3-pyqt6-webengine`, `qt6-qtwebengine`, `qt6-qtsvg`, `qt6-qtwebchannel`, `python3-cryptography`, `python3-jeepney` (names to confirm) |
| Format | RPM from a spec file; Copr builds, hosts and signs |
| Qt WebEngine | Fedora's |
| Codecs and media | Fedora builds without patent-encumbered codecs: expect no H.264 / AAC in the stock package; whether RPM Fusion offers a replacement for Qt 6's WebEngine is to be checked. I.K.E. must say what it found (codec check in Help → About) instead of failing silently |
| Updates | dnf; I.K.E.'s self-update for the Python part |
| Signing | Copr's key |
| Problems to solve | SELinux: nothing expected for a user program, to be confirmed; Fedora KDE and GNOME both to be tried |
| Tests needed | the suite in a Fedora container with Fedora's Qt; by hand on Fedora KDE |
| Complexity | **medium** |

## Windows

| | |
|---|---|
| State | When this plan was written: nothing worked, the code had no Windows branch. **Since 1.2.0**: a preview built, installed and tested on a Windows runner, with the official Qt WebEngine (no H.264 / AAC) — see the first part of [windows.md](windows.md); by hand it is still untested ([WINDOWS-CHECKLIST.md](../WINDOWS-CHECKLIST.md)) |
| Dependencies | all bundled: CPython (embeddable), the Qt Company's Qt and Qt WebEngine through the PyQt wheels pinned by hash, `cryptography`, the engine module built with the MSVC Rust tool chain |
| Format | per-user installer; MSIX as the alternative |
| Qt WebEngine | bundled, replaced as a whole with each installer; never a second Qt on the side |
| Component manager | Python part (self-update), Widevine (`widevinecdm.dll`), later the engine module; a full-bundle update channel for the engine itself, signed |
| Codecs and media | to be settled first: the stock build is not expected to play H.264 / AAC; options A, B, C in [windows.md](windows.md) |
| Updates | I.K.E.'s own, since there is no package manager: Python part as today; a signed full installer when Qt WebEngine changes — which for security should be every Qt WebEngine patch release |
| Signing | Ed25519 for I.K.E.'s updates (existing) **and** an Authenticode certificate for the installer and executables (new, bought, owner only) |
| Problems to solve | every row of the "Linux-only today" table; an identity presented to sites that is consistent for Windows (the fingerprinting tests must be re-based); the whole Plasma integration has no counterpart at first; antivirus false positives; installer, uninstaller, default-browser registration; a Windows test runner |
| Tests needed | the suite on `windows-latest`; by hand on Windows 10 and 11: install without administrator, sandbox, codecs, default browser, update, uninstall leaves nothing |
| Complexity | **high**, and a permanent duty: I.K.E. becomes responsible for shipping every engine security update itself |

## Order proposed

1. **AUR** (low) — when the owner decides.
2. **The four checks on Ubuntu 26.04, Debian 13 and Fedora 43** in
   containers, added to the workflow as informative jobs with each
   distribution's own Qt. Cheap, and it turns this study's "to verify" into
   facts before any packaging.
3. **Flatpak** (medium) — the widest reach for one piece of work, and the
   only sound answer for Ubuntu 24.04, Mint 22 and Debian.
4. **DEB for Ubuntu 26.04**, then **RPM for Fedora** (medium each).
5. **Windows** (high) — only after the codec test and the licence answer,
   and only if the owner accepts the duty of shipping engine updates.

Before step 3, one change in I.K.E. itself serves every platform: the
**codec and engine report** in Help → About (what plays, engine age, sandbox,
native or bundled). On Arch it is information; everywhere else it is the
difference between "I.K.E. is broken" and "this system's Qt has no H.264".
