# Component manager

A design, not code. It answers: which parts of I.K.E. can arrive separately
from the package, and how they are found, checked, installed, updated,
repaired and rolled back — on Linux and on Windows — without the user
needing administrator rights, compilers or SDKs.

## What can really be separated

| Part | Separate from Qt WebEngine? | Today | Note |
|---|---|---|---|
| Chromium's media code (FFmpeg, codecs) | **No** on the Qt Company's builds: *measured*, `libQt6WebEngineCore` (195 MiB) contains it; there is no codec library beside it, and the codec list is fixed at compile time [C1][C2]. On distributions that build against the system FFmpeg (Arch [C3]) the library is the system's, updated by the system — not by I.K.E. | system | **Nothing to manage.** A manager that "adds H.264" by downloading a library cannot work |
| Qt WebEngine itself (library, `QtWebEngineProcess`, `.pak` resources, locales, ICU data, V8 snapshot [C4]) | Only as a whole, together with the matching Qt and PyQt | system package | Native: belongs to the distribution. Self-contained (Windows, Flatpak run time): belongs to the bundle. Never a mix |
| Widevine CDM | **Yes**: one library loaded from a path given to Chromium (`--widevine-path` [C1]) | `ike/drm.py`, on request, TLS only | The first real client of the manager |
| Spell-check dictionaries (`.bdic`) | Yes: files in a folder Qt WebEngine reads (`QTWEBENGINE_DICTIONARIES_PATH`) [C1] | not offered | Candidate; Debian packages them system-wide since trixie [C5] |
| Filter lists | Yes: text | `ike/blocker.py`, daily, TLS | Stay where they are; could share the download and atomic-write code |
| uBlock Origin scriptlets | Yes: one JSON file | shipped with the Python part | Stay with the Python part (they must match the code that injects them) |
| I.K.E.'s Python part | Yes | `ike/updater.py`: signed manifest, SHA-256, staged, roll-back | **The model** for everything else |
| I.K.E.'s engine module (`ike_adblock`, native) | Yes in principle (stable ABI, one file per platform) | package only | Would let ad-blocking engine fixes arrive without a package; needs per-platform builds and the same signing |
| Chrome extensions | Yes | experimental | Own verification (CRX signature), see the audit |

So the manager is for: **Widevine, dictionaries, the engine module, the
Python part** — and it is the existing updater, generalised. It is not a
way to assemble a browser engine on the user's computer.

## Rules

1. **Only verified files run.** A component is installed only if a manifest
   signed with I.K.E.'s release key (Ed25519, the key already used for
   updates) names it with its size and SHA-256, and the downloaded file
   matches. TLS alone is not integrity.
2. **Third-party binaries are pinned.** For Widevine the manifest carries
   the exact version, the vendor's address and the SHA-256 of the file the
   owner verified when signing. I.K.E. downloads from the vendor (it does
   not redistribute the file), compares, and refuses anything else. A new
   Widevine version becomes available when a new manifest is signed — the
   decision the audit left to the owner (open issue A).
3. **No downgrade.** A manifest older than the one already accepted is
   refused (a monotonic sequence number inside the signed manifest), so an
   attacker who replays an old, validly signed manifest cannot bring back a
   vulnerable version.
4. **Compatibility is declared, not guessed.** Each entry names the
   platform (`linux-x86_64`, `windows-x86_64`), the range of I.K.E. versions
   and, where it matters, of Qt WebEngine / Chromium versions it works with.
   An entry that does not fit is not offered.
5. **The user's folder, no administrator.** Everything lives under the
   data folder (`~/.local/share/ike-browser/components/` on Linux,
   `%LOCALAPPDATA%\ike-browser\components\` on Windows). Nothing is written
   to system folders, nothing is added to the library search path.
6. **Atomic.** Download to a temporary file in the same folder → check size
   and hash → unpack into `components/<name>/<version>.new/` (entries
   leaving the folder refused, as the existing code does) → rename to
   `<version>/` → write `state.json` through a temporary file and rename.
   A crash at any step leaves the old version in use.
7. **Repair and roll-back.** At start, each component in use is checked
   against the hash in its accepted manifest; a damaged one is removed and
   fetched again. The previous version is kept until the new one has run
   once without the browser failing to start (the "confirm healthy" step of
   the updater); otherwise I.K.E. goes back and marks the version bad.
8. **Never mixed with a system Qt.** The manager does not download Qt, Qt
   WebEngine, PyQt or FFmpeg libraries, on any platform. On a native Linux
   package those come from the distribution; on Windows and in a Flatpak
   from the bundle, replaced only as a whole by a new bundle.
9. **Visible and optional.** Settings lists each component with version,
   source and state; optional ones (Widevine, dictionaries) are installed
   only when the user asks; removing one is a button.
10. **Offline is fine.** No component is needed to browse; a failed check
    changes nothing and is tried again the next day.

## Manifest (sketch)

```json
{
  "format": 1,
  "sequence": 42,
  "issued": "2026-11-16",
  "components": [
    {
      "name": "widevine",
      "version": "4.10.2891.0",
      "platform": "linux-x86_64",
      "needs": {"ike": ">=1.1.0", "chromium": ">=130"},
      "source": "vendor",
      "url": "https://…vendor's address…",
      "size": 0,
      "sha256": "…",
      "unpack": "zip",
      "files": {"libwidevinecdm.so": "…sha256 of the file inside…"}
    }
  ]
}
```

`components.json` and `components.json.sig` sit next to the update
manifests of each channel. The private key stays with the owner: never in
the repository, in a package or on GitHub Actions; signing is a step of
`tools/make-release.py` on the owner's computer.

## Detection

| Component | How I.K.E. knows what is there |
|---|---|
| Qt WebEngine and Chromium | `qWebEngineVersion()`, `qWebEngineChromiumVersion()`, `qWebEngineChromiumSecurityPatchVersion()` — already shown in Help → About |
| Codecs | a hidden page asking `canPlayType` / `MediaSource.isTypeSupported` once per engine version; the result shown in Help → About, so "video does not play" has an answer |
| Widevine | the file in the component folder and its hash; also a system-wide one (for example from a distribution package) is detected and preferred, never overwritten |
| Sandbox | already detected (About warns when it is off) |
| Native package or self-contained | where `PyQt6` was loaded from; decides whether the Python self-update is allowed (not in a Flatpak) |

## Linux and Windows

| | Linux native | Flatpak | Windows |
|---|---|---|---|
| Qt / Qt WebEngine | distribution | run time + base application | inside I.K.E.'s installer; replaced as a whole by a new installer or a signed full update |
| Python part | self-update as today | repository only | self-update as today (paths adapted) |
| Engine module | package (later: component) | repository | installer (later: component) |
| Widevine | component | component, *to verify* the path in the sandbox | component (`widevinecdm.dll`) |
| Signature of what the system checks | package signature (pacman, apt, dnf) | Flathub | Authenticode on the installer and executables — a second key, of a different kind, see [windows.md](windows.md) |

## Sources

- [C1] Qt WebEngine Features (codecs option, decoding by Chromium,
  Widevine path): https://doc.qt.io/qt-6.11/qtwebengine-features.html
- [C2] Red Hat Bugzilla 2053868 (codec list fixed at compile time):
  https://bugzilla.redhat.com/show_bug.cgi?id=2053868
- [C3] Arch Linux package `qt6-webengine` (depends on `ffmpeg`):
  https://archlinux.org/packages/extra/x86_64/qt6-webengine/
- [C4] Deploying Qt WebEngine Applications (process, resources, locales,
  dictionaries, environment overrides):
  https://doc.qt.io/qt-6/qtwebengine-deploying.html
- [C5] Debian 13 release notes, "Spell-checking support in Qt WebEngine web
  browsers": https://www.debian.org/releases/trixie/release-notes/
