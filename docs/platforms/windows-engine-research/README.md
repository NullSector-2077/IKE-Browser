# Windows engine: research notes

Studies made on 2026-11-16/17 for H.264 / AAC on Windows through Windows' own
decoders (Media Foundation), without shipping any proprietary decoder. Kept
here so that a new session can continue from them.

- `windows-codecs.md` — what Chromium 140 / Qt WebEngine 6.140 do on Windows
  with `proprietary_codecs=true` and `ffmpeg_branding="Chromium"`; where Qt
  sets the switches; the build on GitHub's runners.
- `platform-media.md` — Vivaldi's `platform_media` (from Opera, BSD-3): where
  it is, its licence, how it works.
- `windows-codec-fallbacks.md` — ranked open-source implementations; the
  owner's choice (2026-11-17): Vivaldi 7.6 `platform_media` video path
  (Chromium 140, same branch as Qt WebEngine 6.140) + the Windows part of
  Cromite's `Enable-platform-aac-audio-and-h264-video.patch` (GPL-2.0+) for
  AAC, built with `ffmpeg_branding="Chromium"`.
- `vivaldi-7.6.3797-media-hooks.diff` — Vivaldi 7.6.3797's Chromium media
  hooks (BSD-3, © Opera Software ASA / Vivaldi Technologies AS), from the
  mirror ric2b/Vivaldi-browser at commit
  bb6a67c4a38211d36180421ee814367f8d274be4, kept for the port.

None of this is legal advice.
