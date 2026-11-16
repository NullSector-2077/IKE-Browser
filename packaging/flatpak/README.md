# I.K.E. as a Flatpak

Work in progress on branch `linux/flatpak` (ROADMAP.md, "Next: multiplatform",
step 3). Not yet on Flathub; the bundle is built and tested by
`.github/workflows/flatpak.yml`.

## What is in it

| Part | Comes from |
|---|---|
| Qt 6.11, Python 3.13 | the KDE 6.11 run time (`org.kde.Platform//6.11`) |
| PyQt6, PyQt6-WebEngine | the PyQt base application (`com.riverbankcomputing.PyQt.BaseApp//6.11`) |
| Qt WebEngine | see "Codecs" below |
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

ROADMAP.md, "Codecs": I.K.E. never ships a proprietary codec. The Flatpak may
play H.264 / AAC only through the run time's own codec extension
(`org.freedesktop.Platform.codecs-extra`), which Flathub distributes
separately, never through decoders inside the bundle.

The workflow checks it on every run: the engine report is made again with the
codec extension removed. Whatever is decoded then must come from the run
time's FFmpeg, not from a library inside `/app`. Only then is the bundle kept
as the run's download (`ike-browser-flatpak`).

## Building locally

```bash
flatpak install flathub org.kde.Sdk//6.11 com.riverbankcomputing.PyQt.BaseApp//6.11 \
    org.freedesktop.Sdk.Extension.rust-stable//25.08
flatpak-builder --user --install --force-clean build-flatpak \
    packaging/flatpak/io.github.nullsector_2077.IKE-Browser.yml
flatpak run io.github.nullsector_2077.IKE-Browser
```

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
