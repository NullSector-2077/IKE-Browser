# What the Windows installer of I.K.E. contains

I.K.E. itself is free software under the GNU General Public License,
version 3 or later (`LICENSE.txt`). Its source code, and the scripts that
build this installer from it, are at
https://github.com/NullSector-2077/IKE-Browser (`packaging/windows/`).

On Windows there is no system Qt or Python, so the installer carries them.
Each stays under its own licence:

| Part | Where in the installation | Licence | Source |
|---|---|---|---|
| CPython (embeddable distribution) | `python\` | Python Software Foundation License (`Python-LICENSE.txt`) | https://www.python.org/downloads/source/ |
| Qt (Core, Gui, Widgets, Network, Qml, Quick, WebChannel, …) | `python\Lib\site-packages\PyQt6\Qt6\` | LGPL-3.0 / GPL-3.0 | https://download.qt.io/official_releases/qt/ |
| Qt WebEngine, with Chromium | `python\Lib\site-packages\PyQt6\Qt6\` (`Qt6WebEngineCore.dll`, `QtWebEngineProcess.exe`, `resources\`, `translations\qtwebengine_locales\`) | LGPL-3.0 / GPL-3.0; Chromium and its parts under BSD-style and other free licences, listed by the engine itself at the address `chrome://credits` | https://download.qt.io/official_releases/qt/ |
| PyQt6, PyQt6-WebEngine, PyQt6-sip | `python\Lib\site-packages\PyQt6\` | GPL-3.0 (PyQt6-sip: BSD-2-Clause) | https://pypi.org/project/PyQt6/ (source archives) |
| cryptography (with OpenSSL inside) | `python\Lib\site-packages\cryptography\` | Apache-2.0 or BSD-3-Clause; OpenSSL: Apache-2.0 | https://pypi.org/project/cryptography/ |
| cffi, pycparser | `python\Lib\site-packages\` | MIT; BSD-3-Clause | https://pypi.org/project/cffi/ |
| I.K.E. AdBlock Engine (`ike_adblock.pyd`), built from adblock-rust | `vendor\adblock\` | MPL-2.0 (see `THIRD-PARTY.md`) | `ike-adblock/` in the repository |
| Microsoft Visual C++ run time (`vcruntime140*.dll`, `msvcp140*.dll`, …) | next to Python and to the Qt libraries, as their publishers ship them | Microsoft's redistribution terms | — |

The licence texts that come with the Python packages are kept in their
`*.dist-info` folders under `python\Lib\site-packages\`.

The Qt libraries are separate files (DLLs) that I.K.E. loads at run time. You
may replace them with your own builds of the same Qt version, as the LGPL
provides: put your files in place of those of the same name.

## Codecs

This installer contains **no H.264, AAC or HEVC decoder** and no other
proprietary codec. Qt WebEngine is the Qt Company's official build as
published on PyPI, which is made without proprietary codecs: it plays VP8,
VP9, AV1, Opus, Vorbis, FLAC and MP3. The FFmpeg libraries that the Qt wheel
carries for Qt Multimedia (`avcodec`, `avformat`, …) are **removed** when the
installer is built (`packaging/windows/build.py`, `PRUNE`); the build fails if
one of them is still there.

Widevine is not in the installer either. I.K.E. downloads it from Google only
when you ask for it.
