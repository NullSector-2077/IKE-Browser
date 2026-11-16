# Platform study (November 2026)

Documents only: nothing here is implemented, and no platform is "supported"
because of this study. Today I.K.E. is built, packaged and tested for Arch
Linux / CachyOS.

| File | Content |
|---|---|
| [linux.md](linux.md) | Arch / CachyOS, Debian, Ubuntu, Linux Mint, Fedora: versions and requirements; DEB, RPM, PKGBUILD, AppImage and Flatpak compared; the strategy proposed |
| [component-manager.md](component-manager.md) | What can and cannot be separated from Qt WebEngine, and how optional components would be found, verified, installed, updated and rolled back |
| [windows.md](windows.md) | Qt run time, deployment, helper processes, Visual C++ run time; codecs; a matrix of what may be shipped |
| [porting-plan.md](porting-plan.md) | Per platform: what already works, what must change, tests needed, complexity |

## How to read it

- **Sources.** Statements about Qt, Chromium and the distributions cite the
  official page they come from (list at the end of each file). Package
  versions were read on 2026-11-16 and change every week: check them again
  before acting.
- **Measured.** Some facts were measured in the test environment of this
  work (the PyPI build of Qt WebEngine 6.140 on Linux, and the content of the
  Windows wheels, listed without running them). They are marked *measured*.
- **To verify.** What could only be read, not tried — everything about a real
  Debian, Ubuntu, Mint, Fedora or Windows system — is marked *to verify*, with
  the test that would settle it.
- **Licences and patents.** The matrices describe what the projects and their
  documentation say. They are not legal advice and make no definitive legal
  statement; before shipping codecs or a proprietary module, the owner should
  ask someone qualified.

## Summary of the findings

1. **I.K.E. needs Qt WebEngine 6.8 or later** (it uses the permission
   interface introduced there). That decides the Linux map: Arch / CachyOS,
   Debian 13, Ubuntu 26.04 and Fedora 43+ have it in their own packages;
   Debian 12, Ubuntu 24.04 and Linux Mint 22 do not.
2. **The engine must come from one place.** Either the distribution's Qt
   (native package: small, patched by the distribution, codecs through the
   system's FFmpeg where the distribution builds it so) or a complete,
   self-contained Qt. Never I.K.E.'s Python on the system Qt for some parts
   and a downloaded Qt for others.
3. **Nothing inside Qt WebEngine can be downloaded separately.** *Measured*:
   in the Qt Company's build, Chromium's FFmpeg is linked into
   `libQt6WebEngineCore` (195 MiB); there is no codec library to swap. The
   pieces that really are separate are Widevine, the spell-check
   dictionaries, the filter lists and I.K.E.'s own Python part and engine
   module.
4. **The self-contained build has two costs that a browser cannot ignore.**
   *Measured*: the PyPI build plays no H.264 and no AAC (so most video sites
   fail), and on Ubuntu 23.10 and later a Chromium that is not installed by
   the system cannot start its sandbox without an AppArmor profile. I.K.E.
   never disables the sandbox to make something work, so an AppImage or a
   pip-style bundle is not an acceptable main format there.
5. **Proposed order**: (a) keep the PKGBUILD and add the AUR when the owner
   decides; (b) native DEB for Debian 13 and Ubuntu 26.04, native RPM for
   Fedora, each using the distribution's Qt; (c) Flatpak on Flathub for
   everything else on Linux (Ubuntu 24.04, Mint 22, Debian 12, and as the
   common fallback), built on the KDE run time and the Qt WebEngine base
   application; (d) Windows last, as a self-contained build, after a decision
   on codecs. Details and reasons in [linux.md](linux.md) and
   [porting-plan.md](porting-plan.md).
6. **Windows is the largest step**: the whole desktop integration is
   Plasma / D-Bus, the updater and the paths assume Linux, and a build with
   H.264 / AAC means building Qt WebEngine from source and settling the
   licence question first. See [windows.md](windows.md).
