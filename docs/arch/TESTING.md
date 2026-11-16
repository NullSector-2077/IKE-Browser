# Automatic tests

`tests/` holds checks that start the real browser without a display (PyQt6 +
Qt WebEngine, `QT_QPA_PLATFORM=offscreen`), each time with an empty profile in
a temporary folder and without downloading anything, and look at it from the
inside. From the repository root:

```bash
python3 -m pytest
```

Needs `python-pytest` besides the dependencies of the PKGBUILD; the desktop
integration tests also need `dbus-daemon` and `gdbus` (skipped without them),
and the screen test `ffmpeg`. Every other test runs without a session bus. The AdBlock
engine tests need the engine built into `vendor/adblock/` (see BUILDING.md);
without it they are skipped. The whole run takes about two minutes.
The same tests run on Windows (`python -m pytest`, with Python 3.13 and the
packages of `tools/appimage-requirements.txt` and
`tools/windows-requirements.txt`); `ICE_TEST_QPA=windows` shows real windows
instead of the offscreen platform, as on GitHub's Windows runner. Against an
installed Windows copy, started through its launcher:
`ICE_TEST_EXE=…\ike-browser.exe ICE_TEST_APP=…\app\<version> python -m pytest`.
`python tests/measure_startup.py` gives the median start-up time (the same
variables choose the copy).
To test an installed copy instead of the repository:
`ICE_TEST_APP=/usr/lib/ike-browser python3 -m pytest`. To test a built
AppImage: `ICE_TEST_APPIMAGE=dist/IKE-Browser-<version>-x86_64.AppImage python3 -m pytest`;
add `ICE_TEST_APPIMAGE_NEW=<a newer AppImage>` to also check that the first one
updates itself to the second (the update tests that drive a copy started from
source are skipped there).

| File | What it checks |
|---|---|
| `test_startup.py` | start-up with the new tab page, an address from the command line, private window |
| `test_interface.py` | shield icon at every level and size (dark-blue centre), own window close button (red circle on hover, closes the window), hidden with the system title bar |
| `test_fullscreen.py` | Full screen and mouse lock with real clicks and keys: mouse lock granted with a notice naming the site's origin, Esc frees the pointer; full screen granted with its notice, Esc leaves it; both at once ended by one Esc; a video in full screen, the notice gone after a few seconds; a tab that is no longer in view refused both, the tab in view still allowed |
| `test_window_parts.py` | address bar (addresses, search, keywords, typing an address), vertical tabs (rows, close button), shield panel, find bar |
| `test_themes.py` | the ready-made themes applied live, back to "Follow the system", the system look untouched by default, a user theme saved, applied at the next start and deleted |
| `test_languages.py` | `tools/check-lang.py` without errors, start-up in Italian, German, Chinese and Japanese, language taken from the system (`zh_TW` falls back to Chinese) |
| `test_settings.py` | Settings in all eight languages: 7 sections with icons, no sideways scrolling on General and Appearance, applying without changes changes nothing, a change is saved; the keys of settings.json match `tests/settings-keys.json` |
| `test_part_b.py` | 1.3.2 additions: » button of the bookmarks bar; progress ring of the Downloads button (local server sending a file slowly); domain in normal text and the rest of the address dimmed; loading line (slow local page, tab switch, theme accent colour); tab previews (picture taken when the tab is left, shown instead of the tooltip on horizontal and vertical tabs, not on the current tab); new tab clock and weather (stand-in Open-Meteo server: city search, only rounded coordinates sent, once in 30 minutes, page updated without reload, switched off) |
| `test_updater.py` | Ed25519 signatures; release file names; archives with `..`, absolute paths, other folders or links refused; hash mismatch; `tools/make-release.py` (reproducible payload, signed stable and beta manifests, wrong key or a key inside the repository refused); no private key in the repository; the shipped channel; in the real browser, through a local server that redirects like GitHub Releases: full update, next start on the new version and confirmed, nothing to do the second time, bad signature (payload never downloaded), failing self-test, `min_system` too high (announced once), roll-back of an update that crashes at start; AppImage replaced (backup kept) or left alone (bad hash, failing self-test, no AppImage in the release); with two real AppImages, a real self-update |
| `test_adblock.py` | the engine matches network and cosmetic filters; in a page served locally an image is blocked, an element is hidden and the shield counts it; when the engine fails, requests are let through (fail-open, as before), the errors are counted and shown in Help → About, and blocking resumes with the engine |
| `test_fingerprint.py` | Fingerprinting protection with list scriptlets, at Balanced and Maximum, with software WebGL: the same page measured twice without scriptlets (stable within a session) and once with eleven uBlock Origin scriptlets wrapping timers, fetch, XHR, JSON, events, eval and animation frames: canvas, WebGL, audio, navigator, screen, Client Hints, media devices, WebGPU, a worker, a frame and fifteen functions that must look native are the same; the graphics card is never the real one. `ICE_TEST_FP_OUT=<file>` writes the values |
| `test_repair.py` | Repair this site: a local page broken by the ad blocker is repaired by answering the questions from what the page shows (only ad blocking turned off, remembered, shown in the shield, undone); the search with one and with two culprits, protections not the cause, only the whole shield helps, cancel restores everything, button hidden by the setting |
| `test_resources.py` | Site resources: two local sites measured (memory, CPU, requests, data) and listed; the memory limit suspends only the background tab, which comes back when opened; the CPU limit freezes a busy background tab after three checks, stops it, and it runs again when opened; off by default |
| `test_watcher.py` | Page watcher (a local shop whose price changes and whose page changes at every load): a part with an id, a part without an id, the whole page; unchanged and changed text, notification, no cookies of the user in the checks, shield untouched; the list window (changed in bold, open, remove); part not found; due check; switched off |
| `test_components.py` | Daily component check (`tools/check-components.py`): the versions written in the repository agree (Cargo.toml, Cargo.lock, `ENGINE_VERSION`, AppImage requirements and Python); with stand-in upstream answers and the real Node.js scriptlet builder on a stand-in uBlock checkout: nothing new, each kind of new version found, minor changes (a new uBlock commit with the same scriptlets, a new certifi, a rebuild of the same Python) reported but not counted, `--apply` rewrites every version file and a second check finds nothing, one failing source reported alone, JSON / Markdown / GitHub output; the GitHub workflows; with `ICE_TEST_NETWORK=1` the real sources; against an AppImage, exactly the pinned packages, certifi included |
| `test_passwords.py` | Password manager origins: scheme, host case, the scheme's own default port only (`http://site:443` and `https://site:80` stay distinct), other ports, IPv6, invalid ports, addresses without a scheme (CSV import), older keys unchanged; in the browser, a saved login offered and filled only on its exact origin (not on another subdomain, port or scheme) and, after a redirect, on the origin of the page at fill time |
| `test_plasma.py` | Desktop integration on a private D-Bus with stand-ins (`tests/dbus_standins.py`) and `gdbus` calls: media controls (properties, metadata from the site, pause, play/pause, set position, introspection, name released when the tab closes; off by the setting and for private windows); KRunner (tabs and bookmarks found, short queries ignored, switching to a tab, opening a bookmark, runner file written and removed); downloads in the notifications (progress, speed, total, destination, finished; cancelled from the notification); Send to device (device list, menus, shareUrl, off by the setting); the engine keeps the screen on during a video; nothing happens without a bus |
| `test_platform.py` | What differs between Linux and Windows: the folders (Linux unchanged, Windows `%APPDATA%` / `%LOCALAPPDATA%`), the updater's folder agreed by `ike_boot.py` and `ike/updater.py`, the identity presented to sites on each system (Linux strings unchanged), the Widevine module check (a 64-bit Linux library or Windows DLL; attacks: another machine, a program instead of a library, a truncated header) and its archive (no file outside its folder); the window and Settings on the running system (screenshots with `ICE_TEST_SHOTS`; on Windows only the media-controls switch) |
| `test_windows_update.py` | Windows self-update with a stand-in installation (on any system): the update archive downloaded through GitHub-like redirects, unpacked next to the folder in use, self-tested, `current` / `previous` written, older folders removed, nothing of the small `ike/` update used; refused, with nothing changed and nothing left behind: wrong hash or size, `..`, absolute, drive and backslash names, device names, links, duplicate names, missing files, another version inside, failing self-test, not an archive; nothing downloaded without the `windows` entry or with a bad signature; the first start counted and confirmed; roll-back after a start that did not end cleanly (Linux, stand-in launcher); `tools/make-release.py --windows`. On a real installation (`ICE_TEST_EXE`): a copy updated to a new version for real and started from it, then a version that crashes at start given up by itself at the next start and not offered again |
| `test_winmedia.py` | Windows media controls: a page playing a tone appears in Windows' controls with its title, artist and album; from outside the browser Windows' media sessions are listed, I.K.E.'s found by its title and paused like a media key; play from the controls; gone when the tab closes; off by the setting and for private windows |
| `test_userscripts.py` | User scripts on pages of a local server (other sites through a stand-in proxy): common patterns (`@grant none` in the page, `document-start` before the page, `GM_getValue` / `GM_setValue` kept between loads, `GM_addStyle`, `GM_xmlhttpRequest` and `GM.xmlHttpRequest` to another site, the page's own address, `unsafeWindow`); each script gets only the GM functions of its `@grant` (none without `@grant`); attacks by the page: messages without a token, with a wrong token or another script's token, an operation not granted, `console.info` and `JSON.stringify` replaced before an idle script, the answer callback taken over; `@connect` (listed domains and subdomains, `self`, `*`, not listed); this computer and private addresses (127/8, other forms of 127.0.0.1, `localhost`, 192.168/16, IPv6-mapped, a name resolving to 10/8) refused unless `@connect` names them, also after a redirect; the install dialog lists `@connect` |

Lint (unused code and import order, settings in `pyproject.toml`):

```bash
ruff check .
```

GitHub runs both on every pull request to `main` and every push to `main`
(`.github/workflows/tests.yml`: Ubuntu 24.04, the Chromium sandbox off as on
the runner it cannot start; and Windows Server 2025 with real windows, the
screenshots printed in the log by `tests/shots_to_log.py`). The Windows build
(`.github/workflows/windows.yml`) installs the new installer on the runner,
runs the whole suite against the installed copy, measures its start-up and
uninstalls it.

With `ICE_TEST_SHOTS=<folder>` some tests also save screenshots there, to be
checked by eye.

How a test works: `tests/conftest.py` starts `ike_boot.py` with
`ICE_TEST_HOOK=tests/harness.py`; the harness runs the test's `steps()`
generator inside the browser (each `yield` waits that many milliseconds with
the event loop running), saves what it recorded and closes the browser.

# Test report — 1.6.0

Linux: the real browser was started without a display (PyQt6 + Qt WebEngine
6.12, `QT_QPA_PLATFORM=offscreen`, software rendering) on Ubuntu 24.04, from the
repository, from the built package and from the built AppImage. Windows: on
GitHub's Windows Server 2025 runner with real windows on its desktop, from the
repository and from the copy installed by the new installer (started through
`ike-browser.exe`). Every pull request of the session (#39–#42) passed the
three jobs: Linux, Windows from source, Windows build with the installed copy.

| Test | Result |
|---|---|
| `python3 -m pytest` on the repository (Linux, 142 tests) | 136 pass, 6 skipped (AppImage, network, two AppImages, installed Windows copy, Windows media) |
| The same against the package built with `makepkg -d` (`ICE_TEST_APP=…/usr/lib/ike-browser`) | 136 pass, 6 skipped |
| The same against `IKE-Browser-1.6.0-x86_64.AppImage` | 109 pass, 33 skipped (update tests for a copy started from source, Windows tests) |
| The published 1.5.2 AppImage with the 1.6.0 one as the newer release | the 1.5.2 AppImage replaced itself with 1.6.0 through the local server |
| Windows from source (`tests.yml`, real windows) | 127 pass, 15 skipped (D-Bus, AppImage, the shell-script launcher, the installed-copy test) |
| Windows installed copy (`windows.yml`): installer, whole suite, uninstall | 105 pass, 37 skipped (from-source and Linux-only tests); uninstall removes program, versions and registration, keeps personal data |
| Windows self-update on a copy of the real installation | updated to a new version through GitHub-like redirects, self-tested with the bundled Python, started from `app\<version>`; a version that crashes at start was given up by itself at the next start and not offered again |
| Windows update attacks (from source, Linux and Windows) | 14 doctored archives refused (hash, size, `..`, absolute, drive, backslash, device name, link, duplicate, incomplete, other version, failing self-test, not an archive), nothing changed or left behind; nothing downloaded without the `windows` entry or with a bad signature |
| Windows media controls | Windows lists I.K.E.'s session with the site's title, artist and album; paused from outside the browser like a media key; play; removed when the tab closes; off by the setting and in private windows |
| Identity on Windows | `Windows NT 10.0` in the header, scripts, workers and frames, Client Hints `Windows` / `19.0.0`, `navigator.platform` `Win32`, a Direct3D 11 graphics card that is not the real one |
| Fingerprinting before / after on Linux: `test_fingerprint.py` on 1.5.2 and 1.6.0 (Balanced, Maximum) | passes on both; user agent, Client Hints, screen, media devices, WebGPU and native-looking functions identical |
| Ad blocker before / after: `test_adblock.py` on 1.5.2 and 1.6.0 | the same results |
| Start-up on Linux (median of 9, to the first window; three rounds) | 1.5.2: 0.25 / 0.28 / 0.26 s — 1.6.0: 0.26 / 0.25 / 0.26 s |
| Start-up of the installed Windows copy (median of 9, GitHub runner) | 0.36–0.60 s depending on the runner machine; no difference between the steps of the session |
| Windows files | installer 137 MB, update archive 154 MB, 513 MB installed |
| Package: `ike_boot.py --version`, `update.json`, dependencies | 1.6.0; GitHub channel and the project's public key; no private key in the package; dependencies unchanged; `__min_system__` stays 1.4.0, so installed 1.4.x / 1.5.x copies update themselves |
| `tools/check-lang.py` | all seven packs 748/748, no errors |
| `ruff check .` | clean |

Not testable in this environment: a real Windows 10 / 11 desktop with a GPU
(look of the Windows 11 style on a real screen, the media overlay, the lock
screen, a keyboard's media keys), SmartScreen with a downloaded installer,
choosing I.K.E. as default browser in Windows Settings (the registration is
written; only a person can choose), Widevine downloaded on Windows, importing
from real Windows browsers, a real self-update from a published release (the
first one will be 1.6.0 → 1.6.1), signing with the owner's key, installation
with `pacman` (built with `makepkg -d`), a review of the new texts by native
speakers.

# Test report — 1.5.2

The real browser was started without a display (PyQt6 + Qt WebEngine 6.12,
`QT_QPA_PLATFORM=offscreen`, software rendering) on Ubuntu 24.04, from the
repository, from the built package and from the built AppImage. Every attack
test was also run against 1.5.1, where it fails (a forged clipboard write is
accepted, the token is read through a replaced `console.info`, local addresses
are reached), and passes on 1.5.2.

| Test | Result |
|---|---|
| `python3 -m pytest` on the repository (112 tests) | 109 pass, 3 skipped (AppImage, network, two AppImages) |
| The same against the package built with `makepkg -d` (`ICE_TEST_APP=…/usr/lib/ike-browser`) | 109 pass, 3 skipped |
| The same against `IKE-Browser-1.5.2-x86_64.AppImage` | 101 pass, 11 skipped (update tests for a copy started from source, two AppImages) |
| The published 1.5.1 AppImage with the 1.5.2 one as the newer release | the 1.5.1 AppImage replaced itself with 1.5.2 through the local server |
| Each pull request on GitHub (`.github/workflows/tests.yml`) | pass |
| Ad blocker before / after: `test_adblock.py` on 1.5.1 and 1.5.2 | the same results; the new error count is the only change |
| Fingerprinting before / after: `test_fingerprint.py` on 1.5.1 and 1.5.2 (Balanced, Maximum) | passes on both; the values that do not change per session (Client Hints, screen, media devices, WebGPU, workers, native-looking functions) are identical between the two versions |
| Start-up (median of 9 starts, to the first window; two rounds) | 1.5.1: 0.36 s / 0.38 s — 1.5.2: 0.36 s / 0.34 s |
| A page with ten user scripts (four `@grant none` at every `@run-at`, three with values and styles, two `GM_xmlhttpRequest` with `@connect`, one `unsafeWindow`), median of 12 loads; two rounds | load: 1.5.1 43 / 45 ms — 1.5.2 49 / 38 ms; all ten scripts done: 1.5.1 62 / 65 ms — 1.5.2 68 / 57 ms (the differences are within the noise of this machine) |
| Address bar centre at 1400, 1920 and 2560 px (window without the system title bar) | 1.5.1: 92 px left of the middle at 1400 and at 2560 — 1.5.2: in the middle |
| Package: `ike_boot.py --version`, `update.json`, dependencies | 1.5.2; GitHub channel and the project's public key; no private key in the package; dependencies unchanged; `__min_system__` stays 1.4.0, so installed 1.4.x / 1.5.x copies update themselves |
| `tools/check-lang.py` | all seven packs 747/747, no errors |
| `ruff check .` | clean |

Not testable in this environment: a real Plasma 6 / Wayland desktop (the look
of the notice and of the larger window buttons with Breeze — screenshots were
taken with the Fusion style; pointer confinement under Wayland); real games and
video sites in full screen; real user scripts from Greasy Fork and their
`@connect` sites (stand-in sites and a stand-in proxy were used); a real home
network (192.168.x was refused before any request); DNS rebinding (documented,
not caught); signing with the owner's key and the real self-update of installed
copies (it needs the published, signed release); installation with `pacman`
(built with `makepkg -d`); a review of the new texts by native speakers.

# Test report — 1.5.1

The real browser was started without a display (PyQt6 + Qt WebEngine 6.12,
`QT_QPA_PLATFORM=offscreen`, software rendering) on Ubuntu 24.04, from the
repository, from the built package and from the built AppImage; the same tests
ran on GitHub's Ubuntu 24.04 runner. No change to what the user sees.

| Test | Result |
|---|---|
| `python3 -m pytest` on the repository (95 tests) | 92 pass, 3 skipped (AppImage, network, two AppImages) |
| The same on GitHub (`.github/workflows/tests.yml`) | 92 pass, 3 skipped; with DejaVu Sans, the runner's own font, Settings → Appearance scrolled sideways in German and Spanish (also reproduced here), so the runner uses Noto Sans |
| The same against the package built with `makepkg -d` from Ubuntu's `pacman-package-manager`, as an ordinary user (`ICE_TEST_APP=…/usr/lib/ike-browser`) | 92 pass, 3 skipped |
| The same against `IKE-Browser-1.5.1-x86_64.AppImage` | 84 pass, 11 skipped (update tests for a copy started from source, two AppImages); exactly the pinned packages inside, certifi included |
| The published 1.5.0 AppImage with the 1.5.1 one as the newer release | the 1.5.0 AppImage replaced itself with 1.5.1 through the local server; the new check finds certifi missing in 1.5.0, as expected |
| `tools/check-components.py` against the real sources, here and on GitHub (run by hand) | no errors; nothing new today; certifi 2026.10.23 "also newer", applied |
| The `components` issue, on GitHub | opened by a run on a temporary branch with an older engine written in it, closed by the next run on `main` |
| Package: `ike_boot.py --version`, `--selftest-import`, `update.json`, dependencies | 1.5.1; GitHub channel and the project's public key; no private key in the package |
| `ruff check .` | clean |

Not testable in this environment: the scheduled daily runs themselves (the
GitHub check at 05:17 UTC and the Claude task at 08:41 — both were started by
hand once); a real update found by them and the pull request the task opens
(the steps were done by hand for this release); the owner's ok and the signing
with the owner's key; the AppImage on other distributions, including one
without system certificates, where certifi is used; installation with
`pacman` (dependencies not checked: built with `makepkg -d`).

# Test report — 1.5.0

The real browser was started without a display (PyQt6 + Qt WebEngine 6.12,
`QT_QPA_PLATFORM=offscreen`, software rendering) on Ubuntu 24.04 with the
automatic tests above, from the repository, from the built package and from
the built AppImage; screenshots of the new windows and bars were checked by
eye (Italian and German).

| Test | Result |
|---|---|
| `python3 -m pytest` on the repository (85 tests) | 84 pass, 1 skipped (needs two AppImages) |
| The same against the package built with `makepkg -d` (`ICE_TEST_APP=…/usr/lib/ike-browser`) | 84 pass, 1 skipped |
| The same against `IKE-Browser-1.5.0-x86_64.AppImage` with a second AppImage marked 1.5.1 | 75 pass, 10 skipped (update tests for a copy started from source); the desktop integration works with the jeepney inside the AppImage; the 1.5.0 AppImage replaced itself with the 1.5.1 one through the local server |
| Package: launcher `--version`, `--selftest`, `update.json`, dependencies | 1.5.0; GitHub channel and the project's public key; no private key in the package; `python-jeepney` among the dependencies |
| Without jeepney (import blocked) and a session bus present | the integration stays off, the browser works |
| `tools/check-lang.py` | all seven packs 743/743, no errors |
| `ruff check .` | clean |

Not testable in this environment: a real Plasma 6 / Wayland desktop — the
media widget and the lock screen showing I.K.E., the media keys, the look of
the download notification, KRunner picking up the runner file (it may need
KRunner to restart once, or a new login), focus when KRunner switches to a tab
under Wayland; a real phone with KDE Connect (a stand-in answered on the bus);
real sites for Repair this site (a local page was used) and for the page
watcher (a local shop); CPU and memory figures on a real GPU; the AppImage on
other distributions; installation with `pacman` (built with `makepkg -d`, so
dependencies were not checked by pacman); signing with the owner's key and the
real self-update of installed 1.4.0 copies to 1.5.0 (it needs the published,
signed release); a review of the new Spanish, French, German, Portuguese,
Chinese and Japanese texts by native speakers.

# Test report — 1.4.0

The real browser was started without a display (PyQt6 + Qt WebEngine 6.12,
`QT_QPA_PLATFORM=offscreen`, software rendering) on Ubuntu 24.04 with the
automatic tests above, from the repository, from the built package and from
the built AppImage; AppImage screenshots were checked by eye.

| Test | Result |
|---|---|
| `python3 -m pytest` on the repository (62 tests) | 61 pass, 1 skipped (needs two AppImages) |
| The same against the package built with `makepkg -d` (`ICE_TEST_APP=…/usr/lib/ike-browser`) | 61 pass, 1 skipped |
| The same against `IKE-Browser-1.4.0-x86_64.AppImage` with a second AppImage marked 1.4.1 | 53 pass, 9 skipped (update tests for a copy started from source); the 1.4.0 AppImage downloaded the 1.4.1 one through the local server, checked it, replaced itself and started as 1.4.1 at the next run |
| Package: launcher `/usr/bin/ike-browser --selftest`, `update.json` | 1.4.0; GitHub channel and the project's public key; no private key in the package |
| Package started against the real channel on GitHub (no release published yet) | update check reports "HTTP Error 404" and nothing is installed |
| AppImage: interface, icons, fonts, new tab page, address bar (screenshots) | drawn as in the package |
| `tools/check-lang.py` | all seven packs 667/667, no errors |
| `ruff check .` | clean |

Not testable in this environment: a real release on GitHub (it needs the
owner's signature, so the first real download will be 1.4.0 → 1.4.1), signing
with the owner's key (a test key was used), the AppImage on other
distributions and on a real desktop (Fedora, Debian, Ubuntu with its AppArmor
restriction, GNOME, Hyprland), with a real GPU, under Wayland, and with an
installed icon theme; AppImage start-up time from a real disk; a desktop menu
entry for the AppImage (not created: use the file itself or a tool such as
Gear Lever); a real Plasma 6 / Wayland desktop; installation with `pacman`
(dependencies not checked: built with `makepkg -d`); a review of the new
Spanish, French, German, Portuguese, Chinese and Japanese message by native
speakers.

# Test report — 1.3.2

The real browser was started without a display (PyQt6 + Qt WebEngine 6.12,
`QT_QPA_PLATFORM=offscreen`, software rendering) on Ubuntu 24.04 and checked
with the automatic tests above; screenshots were checked by eye.

| Test | Result |
|---|---|
| `python3 -m pytest` on the repository (40 tests) | pass, also three runs in a row for part A |
| The same tests against the built package (`ICE_TEST_APP=…/usr/lib/ike-browser`) | 40 pass |
| Part A: tests written first, passing on 1.3.0 code and after every cleanup step; the new window-parts tests pass before and after the split of `window.py` | pass |
| Italian strings in `it.json` compared with the old table in `i18n.py` | 648/648 identical |
| `tools/check-lang.py` | all seven packs 666/666, no errors |
| Settings in all eight languages | no sideways scrolling on General and Appearance |
| `ruff check .` | clean |
| Package built with `makepkg -d` from the PKGBUILD, unpacked, launcher `/usr/bin/ike-browser --version`, start through the launcher, `ike_boot.py --selftest-import` | 1.3.2, native AdBlock engine loads |

Not testable in this environment: a real Plasma 6 / Wayland desktop with
Breeze and KWin (look of the » button, progress ring, dimmed address, loading
line and tab-preview popup there), the time the tab-preview picture adds to a
tab switch on a real GPU, typing with an input method (CJK) in the address
bar, the real Open-Meteo service (a stand-in server was used), installation
with `pacman` (dependencies not checked: built with `makepkg -d`), a review of
the new Spanish, French, German, Portuguese, Chinese and Japanese texts by
native speakers.

Found while testing, not changed (it is the same in 1.3.0): closing I.K.E. in
the first seconds after start-up while the filter lists or the Chrome version
are still downloading ends with "QThread: Destroyed while thread is still
running" and an abort instead of a clean exit. Settings and session are saved
before that point.

# Test report — 1.3.0

The real browser was started without a display (PyQt6 + Qt WebEngine 6.12,
Fusion style) and driven by test scripts; screenshots were checked by eye.

| Test | Result |
|---|---|
| Shield at 16 and 22 px, light and dark background, all five levels | dark-blue centre, white letter readable; "Off" unchanged |
| Own close button (system title bar off): at rest, mouse over, click | disc like the vertical-tab button, red circle on hover, the window closes |
| `tools/check-lang.py` | zh and ja 648/648, no placeholder, `&` or punctuation errors |
| Start-up in Chinese and Japanese (`language` setting and `LANG=zh_CN` / `ja_JP`) | menus, settings and new tab page translated, CJK text drawn (Noto CJK) |
| `zh_TW` system language | falls back to Simplified Chinese |
| The five ready-made themes applied live | window, toolbars, tabs, address bar and I.K.E.'s icons recoloured |
| Back to "Follow the system" | palette and font identical to before, toolbars and tabs without own colours |
| "Follow the system" from a fresh profile | no palette, font or widget colour is touched |
| Theme editor: colours, font family and size, live preview | applied at once; Cancel restores the previous look |
| Save as a user theme, restart, delete | saved in settings.json, applied at start-up, delete returns to the system look |
| Settings → Appearance at the default size in en, it, es, fr, de, pt, zh, ja | no sideways scrolling, "Customize…" visible |
| Package built with `makepkg` from the PKGBUILD, unpacked and started from `usr/lib/ike-browser` | version 1.3.0, native AdBlock engine loads and blocks, theme and close button as above |

Not testable in this environment: a real Plasma 6 / Wayland desktop with the
Breeze style and KWin (Breeze or Aurorae close-button look, Plasma colour
scheme changes while a theme is in use), the system icon theme (only I.K.E.'s
own icons were seen), installation with `pacman` (the package was built on
Ubuntu with `makepkg -d`, so dependencies were not checked by pacman), the
download of filter lists, a review of the Chinese and Japanese texts by a
native speaker.

# Test report — 1.2.0

The real browser was started without a display (PyQt6 + Qt WebEngine 6.12,
software WebGL) and driven by test scripts.

| Test | Result |
|---|---|
| Fingerprint measured with Cover Your Tracks' own code (`fp2` library) on two different sites | 4 values differ between sites (canvas, WebGL, audio, plugins) at Balanced, Strict and Maximum: randomized fingerprint |
| Graphics card presented | a common model, different on each site, never the real one |
| WebGL extension list | differs between sites |
| Chrome version, simulated answer of the version service | headers, JavaScript, workers and Client Hints follow it |
| Chrome version without an answer | calendar estimate |
| User scripts: page world, GM functions, `@require`, request to another site, values kept between loads | pass |
| A failing user script | other scripts keep working |
| Disabled script, user scripts switched off | do not run |
| Bookmarks bar with 40 bookmarks at 1000 px | 5 in the bar, 35 under » ; at full width all in the bar and » hidden |
| Settings: 7 sections with icons, user scripts page, icon and language choices | pass, also checked visually |
| Start-up in German and French with the bundled icon sets | pass |
| YouTube ad removal (1.1.1 tests: stand-in server for `www.youtube.com`) | pass |
| AdBlock engine and launcher built from source; package layout installed from the PKGBUILD steps and started | pass |

Not testable in that environment: the real Cover Your Tracks site, the real
YouTube, Greasy Fork, a real Plasma desktop (installed icon themes, colour
scheme).
