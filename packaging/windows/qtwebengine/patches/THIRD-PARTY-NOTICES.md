# Third-party code in I.K.E.'s Qt WebEngine for Windows

This file travels with the built engine (`LICENSES/` in the zip) and with the
patches. It lists the code that I.K.E. adds to Qt WebEngine 6.140.0 so that
H.264 and AAC are decoded by Windows (Media Foundation). Qt WebEngine and
Chromium themselves keep their own licences and notices, which the
`PyQt6-WebEngine-Qt6` wheel carries. Nothing here is legal advice.

## 1. `platform_media` — Opera Software ASA, Vivaldi Technologies AS

- What: the software H.264 decoder over the Windows H.264 transform
  (`WMFVideoDecoder`), the helper that loads the Windows decoder libraries
  before the sandbox closes (`platform_media_init`), and the hooks that put
  them into Chromium.
- From: Vivaldi 7.6.3797 (Chromium 140.0.7339.136), source archive
  `vivaldi-source_7.6.3797.tar.xz`, <https://vivaldi.com/source/>; read from
  the Git mirror <https://github.com/ric2b/Vivaldi-browser>, commit
  `bb6a67c4a38211d36180421ee814367f8d274be4`.
- Copyright: "Copyright (c) 2018 Vivaldi Technologies AS. All rights
  reserved." / "Copyright (C) 2015 Opera Software ASA. All rights reserved." /
  "This file is an original work developed by Opera Software ASA".
- Licence: BSD 3-clause. The two texts are next to this file in a built
  engine (`platform_media-OPERA_LICENSE.txt`, © 2013 Opera Software ASA;
  `platform_media-VIVALDI_LICENSE.txt`, © 2015 Vivaldi Technologies) and in
  patch `chromium/0002` (`chromium/platform_media/`).
- Changes made by I.K.E.: listed in `platform_media-README.ike.md`
  (`chromium/platform_media/README.ike.md`).

Neither the name of Opera Software ASA nor of Vivaldi Technologies nor the
names of their contributors are used to endorse or promote I.K.E.

## 2. "Enable platform aac audio and h264 video" — Cromite

- What: the Windows part for AAC: Chromium's `MediaFoundationAudioDecoder`
  takes every AAC profile, the stream is handed over with ADTS headers,
  `FFmpegAudioDecoder` refuses AAC (GN argument `enable_platform_aac_audio`).
- From: Cromite, `build/patches/Enable-platform-aac-audio-and-h264-video.patch`,
  <https://github.com/uazo/cromite>, commit `3724efc6` (release
  153.0.8010.37). Author: uazo, 6 March 2024. Context:
  <https://github.com/uazo/cromite/pull/856>.
- Licence, as the patch states it: "License: GPL-2.0-or-later -
  https://spdx.org/licenses/GPL-2.0-or-later.html".
- Changes made by I.K.E.: only the Windows AAC hunks are used (patch
  `chromium/0003` says which); they are unchanged.

Because of this part the engine as I.K.E. builds it is distributed under the
GNU General Public License, version 3 or (at your option) any later version —
the licence of I.K.E. itself, which GPL-2.0-or-later code may be combined
into, and one of the licences Qt WebEngine is offered under. The complete
corresponding source is: Qt WebEngine `v6.140.0` and its Chromium at the
commits pinned in `packaging/windows/qtwebengine/versions.json`, plus the
patches and build scripts in `packaging/windows/qtwebengine/` of
<https://github.com/NullSector-2077/IKE-Browser> at the commit named in
`IKE-ENGINE.txt`.

## 3. Written for I.K.E.

Patches `chromium/0001`, `chromium/0004` and `qtwebengine/0001`: small edits
of Chromium's and Qt WebEngine's own files, under the licence of the file
they change (BSD-3-Clause for Chromium; Qt WebEngine's for `CMakeLists.txt`).
