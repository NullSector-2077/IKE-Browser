# I.K.E.'s Qt WebEngine for Windows

I.K.E. never ships a proprietary codec (ROADMAP.md, "Codecs"). On Windows
there is no system Qt, and the Qt WebEngine that PyPI offers plays neither
H.264 nor AAC. This folder builds I.K.E.'s own Qt WebEngine, in which those
two are decoded by the decoders that are part of Windows (Media Foundation) —
by the graphics driver where it can, in software otherwise — as Vivaldi and
Opera do.

| File | Purpose |
|---|---|
| `versions.json` | the pinned Qt WebEngine, Chromium, Qt and PyQt versions |
| `patches/` | the changes to Qt WebEngine and its Chromium, with their own README |
| `build.py` | the build, in stages, for a GitHub Actions Windows runner |
| `verify_codecs.py` | plays real clips with an installed PyQt6 and says which decoders were used |
| `runner-media.ps1`, `runner-pyqt.ps1` | workflow helpers |

Workflow: `.github/workflows/windows-engine.yml` (stages in
`windows-engine-stage.yml`).

## What is built

Only Qt WebEngine `6.140.0`, against the official Qt `6.12.0` binaries for
MSVC 2022 (taken from Qt's online repository and checked against its SHA-1
files) — the same Qt that the `PyQt6-Qt6` wheel repackages. One release
configuration, no debug information, Qt PDF left out.

The result is a zip laid out like the `PyQt6-WebEngine-Qt6` wheel
(`PyQt6/Qt6/bin`, `resources`, `translations/qtwebengine_locales`, `qml`), to
be copied over an installed `PyQt6-WebEngine-Qt6 6.140.0`, with a
`SHA256SUMS.txt`. The PyQt bindings (`PyQt6-WebEngine`) are used as they come
from PyPI.

## How the build fits on free runners

A runner has 4 processors and a job may last 6 hours; Qt WebEngine needs
several times that. So the workflow is a chain of up to seven stages. Each
stage:

1. fetches Qt and the sources again (pinned commits) and applies the patches;
2. unpacks the build folder the stage before saved (an artifact, 7-Zip in
   pieces);
3. gives every source file a fixed date, and the current time only to patched
   files whose content changed — so Ninja rebuilds exactly what changed;
4. compiles the patched media code first (a mistake shows in minutes);
5. builds until minute 285 of the job, then stops Ninja;
6. saves the build folder again.

The stage in which the build finishes installs it, checks what was linked in
and packages it. A new run continues from the build folder the previous run
kept (seven days), so a changed patch costs one short run, not a whole build.

## The checks

- **What is linked in** (`build.py evidence`, fails the run): the GN
  arguments; FFmpeg's codec, parser and demuxer lists; every object file and
  library given to the linker searched for `ff_h264_decoder`,
  `ff_aac_decoder`, `ff_hevc_decoder`, `WelsCreateDecoder`,
  `WelsCreateSVCEncoder`; the linker's map of `Qt6WebEngineCore.dll` searched
  for the same names; free decoders searched for as well, to show the search
  finds FFmpeg's symbols at all.
- **Text in the finished DLL** (`build.py package`, fails the run): messages
  that only FFmpeg's H.264 / AAC decoders and OpenH264 contain must be absent;
  the names of the Windows decoders must be present.
- **Real playback** (`verify_codecs.py`, last job): clips made on the runner
  with FFmpeg (used there only; never shipped) are played in a
  `QWebEngineView`: H.264 Baseline / Main / High with AAC-LC as files and
  through Media Source, 320×240 to 1920×1080, plus VP9, Opus and MP3 as
  controls. A clip counts only if pictures were decoded, the four coloured
  quarters of the picture read back with the right colours, and audio bytes
  were decoded. The decoder names come from the engine's media log. The same
  clips are first played with the engine from PyPI, where H.264 / AAC must
  fail — otherwise the check would prove nothing.

The runners have no graphics card, so they prove the **software** path. That
the graphics driver's decoder is used on a real computer has to be checked
there: see "Still to test on a real Windows PC" below.

## State

See the end of this file, written after the runs.
