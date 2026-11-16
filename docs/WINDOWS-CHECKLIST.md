# I.K.E. on Windows: the test on a real PC

I.K.E. 1.2.0 for Windows is a **preview**: it is built and tested by GitHub
Actions on a Windows server without a screen, a sound card or a graphics
card. This list is what only a person at a real Windows 10 or 11 PC can
check. Tick each line; write down what does not behave as described (and,
when it helps, Help → About → the lines about the engine).

Where the installer comes from: GitHub → the repository → **Actions** →
**Windows** → the newest run with a green tick → at the bottom,
**Artifacts** → `ike-browser-windows-installer` (a .zip with
`ike-browser-1.2.0-windows-x64-setup.exe` and `build-info.json`). Nothing is
published as a release until this list has been gone through.

## What the automatic checks already cover

Run on every push, on GitHub's `windows-latest` (Windows Server 2025); a
failing step fails the run. Details: [TESTING.md](TESTING.md),
[platforms/windows.md](platforms/windows.md).

| Checked automatically | How |
|---|---|
| The browser starts, opens pages, tabs, private windows, settings, themes, languages | the whole test suite (`tests/`) with the real browser, the engine's sandbox on |
| Ad blocking, cosmetic filters, scriptlets, the shield's counters | `test_adblock.py`, `test_repair.py`, with the engine module built for Windows |
| The identity shown to sites is Chrome on Windows everywhere (request header, `navigator`, Client Hints, workers, frames); the graphics card named is a Windows one, never the real one | `test_fingerprint.py`, `test_platform.py` |
| Folders: settings under `%APPDATA%`, the rest under `%LOCALAPPDATA%` | `test_platform.py`, `test_windows.py` |
| One running browser per user; a second start hands its address over; a pipe made by somebody else is told nothing | `test_windows.py` |
| The self-update: signature, hash, staged folder, next start on the new version, roll-back | `test_updater.py`, also through the installed `ike-browser.exe` |
| Password vault, downloads landing in the download folder, local-file rules, user scripts, the security tests | `test_passwords.py`, `test_security.py`, `test_userscripts.py` |
| The installer installs for the current user without questions, `ike-browser.exe --version` answers, every module loads, the engine answers; no H.264 / AAC / HEVC, VP9 / AV1 / Opus / MP3 present | workflow steps "Install", "Start it", "Engine check" |
| No codec library, no key file in the installer | `packaging/windows/check-install.py` |
| The uninstaller removes the program, the shortcut and its registry entries and leaves the user's data | workflow step "Uninstall" |

What a server **cannot** show: how it looks, real windows and the task bar,
notifications on screen, sound, hardware video decoding, real websites,
Windows' own dialogs (SmartScreen, Default apps), a second user account.
That is the list below.

## Before you start

- [ ] The PC: Windows 10 (22H2) or Windows 11, 64-bit. Note which, and the
      graphics card.
- [ ] If you can, make a restore point or use a spare user account: this is a
      preview.

## 1. Install

- [ ] Double-click the setup file. Windows SmartScreen will warn ("Windows
      protected your PC", unknown publisher): **expected**, the installer is
      not signed with a Windows certificate. "More info" → "Run anyway".
- [ ] **No** administrator question (no blue / yellow "Do you want to allow
      this app to make changes" window) appears at any point.
- [ ] The wizard shows the licence, two tick boxes ("List I.K.E. among the
      browsers…", ticked; "Create a desktop shortcut", not ticked) and
      installs in under a minute or two.
- [ ] Afterwards: `I.K.E.` is in the Start menu with its icon; the folder
      `%LOCALAPPDATA%\Programs\I.K.E` exists (paste that into Explorer's
      address bar); Settings → Apps → Installed apps lists "I.K.E." 1.2.0.

## 2. First start

- [ ] Start I.K.E. from the Start menu. **No black console window** opens, not
      even for a moment.
- [ ] The window appears within a few seconds, maximised, with the new tab
      page (logo, clock, "Try the Cyber theme").
- [ ] The task bar shows I.K.E.'s icon (not a Python icon); Task Manager
      lists "I.K.E. - Internet Kontrol Experience".
- [ ] Right-click the task-bar button → "Pin to taskbar"; close I.K.E.; the
      pinned button keeps the icon and starts I.K.E. again, in the same
      button (not a second one).
- [ ] Windows Firewall does not ask anything at start.
- [ ] The interface is in your Windows display language if it is one of the
      eight (otherwise English).
- [ ] Help → About: version 1.2.0; "I.K.E. AdBlock Engine" active; the
      sandbox line does **not** say it is off; plays VP9, AV1, Opus, MP3;
      does not play H.264, AAC, HEVC.

## 3. Browsing and tabs

- [ ] Open several ordinary sites (a news site, Wikipedia, a shop, a web
      mail). Pages load, scroll smoothly, text is sharp (also on a screen
      scaled to 125 % or 150 %).
- [ ] New tab, close tab, reopen closed tab, drag a tab to another place,
      middle-click a link, Ctrl+Tab, Ctrl+T, Ctrl+W, Ctrl+L, F5, F11.
- [ ] Settings → Appearance: vertical tabs on and off; "I.K.E. Cyber" theme on
      and back to "Follow the system". With "Follow the system" the window
      follows Windows' light / dark setting.
- [ ] Own window buttons (Settings → Appearance, system title bar off):
      minimise, maximise, close; the window can be moved, resized, snapped to
      a screen edge (Win+arrows).
- [ ] A private window; a second profile from the menu (opens a second
      I.K.E. with its own data).
- [ ] With I.K.E. open, start it again from the Start menu: a new window of
      the **same** I.K.E. appears (not a second program in Task Manager's
      "Apps").
- [ ] Type text with your keyboard layout, accents and an input method if
      you use one (Chinese / Japanese).

## 4. Ad blocking

- [ ] Settings → Components → update the filter lists: they download without
      an error. (If "certificate" errors appear here, note them: see
      "Known limits" in platforms/windows.md.)
- [ ] A site full of advertisements: they are gone and the shield counts.
- [ ] YouTube: a few videos without advertisements before or inside them.
- [ ] A site that breaks: shield → "Repair this site".

## 5. Fingerprinting protection

- [ ] https://coveryourtracks.eff.org/ — note the result. "User agent" must
      name Windows and Chrome (no "Linux", no "QtWebEngine"); "Platform":
      Win32; the WebGL renderer names a Direct3D11 card that is **not**
      your real one (at Balanced).
- [ ] https://browserleaks.com/client-hints — platform "Windows",
      architecture x86, 64-bit, and the same Chrome version as the user
      agent.
- [ ] Sign in to a Google account and to one Microsoft account: the sign-in
      pages work.

## 6. Downloads

- [ ] Download a file: the dialog asks where; the progress ring on the
      toolbar turns; the file is in the folder chosen and opens from the
      downloads list.
- [ ] A PDF opens in the built-in viewer.
- [ ] Open a downloaded `.html` file from Explorer with "Open with → I.K.E."

## 7. Notifications

- [ ] Menu → "Suspend inactive tabs now" (or let a watched page change): the
      short notice appears inside the window.
- [ ] A notification of Windows appears (bottom right, with I.K.E.'s icon)
      when: a site you allowed sends one (https://www.bennish.net/web-notifications.html),
      or an I.K.E. update was installed. While it shows, a small I.K.E. icon
      is in the notification area (near the clock) and leaves afterwards.
- [ ] "Do not disturb" in Windows silences them.

## 8. Settings

- [ ] Settings → every page opens; nothing is cut off; no sideways scroll bar.
- [ ] General has **no** "Desktop integration" section (Plasma, KRunner, KDE
      Connect do not exist on Windows).
- [ ] "Make I.K.E. the default browser" opens Windows' "Default apps";
      I.K.E. is in the list there; choose it; a link clicked in another
      program (a mail, a document) opens in I.K.E. Then give the default
      back to your usual browser.
- [ ] Change a few settings, close I.K.E., start again: they were kept.
      The file is `%APPDATA%\ike-browser\settings.json`.
- [ ] Windows Settings → Accessibility → Visual effects → "Animation
      effects" off: I.K.E.'s small fades stop (within a few seconds); on
      again: they are back.

## 9. Profiles and data

- [ ] `%APPDATA%\ike-browser` holds `settings.json`;
      `%LOCALAPPDATA%\ike-browser\data` holds the profile, bookmarks and
      history (`ike.sqlite`) and, once created, the password vault
      (`vault.bin`); `%LOCALAPPDATA%\ike-browser\cache` the cache.
- [ ] Nothing of I.K.E. appears directly in your user folder
      (`C:\Users\<you>`).
- [ ] Passwords: create the vault, save a login, close, start, unlock,
      autofill. Copy a password: it does **not** appear in the clipboard
      history (Win+V, if you have it on).
- [ ] Import bookmarks from another browser (Firefox, Chrome or Edge), if
      you have one: note whether it is found.
- [ ] Backup and restore (menu → Import and backup).

## 10. Video and sound

- [ ] YouTube: video and sound play; 1080p; full screen and back with Esc;
      picture-in-picture. (YouTube offers VP9 / AV1 and Opus.)
- [ ] The media keys of the keyboard: note what happens (Windows' media
      controls are not connected yet).
- [ ] Shift+Esc → Site resources: memory and CPU of the open sites are
      shown and change.
- [ ] A long video for ten minutes: no stutter; note the CPU use in Task
      Manager and whether "GPU" shows video decoding.

## 11. Codecs — what must work and what does not yet

- [ ] **Must play**: https://test-videos.co.uk/bigbuckbunny/webm-vp9 (VP9),
      https://test-videos.co.uk/bigbuckbunny/webm-av1 or an AV1 video on
      YouTube ("Stats for nerds" shows `av01`), any `.webm`, `.ogg`, `.opus`,
      `.flac`, `.mp3` file.
- [ ] **Does not play yet — expected**: H.264 and AAC, that is most `.mp4`
      and `.m4a` files, and the sites that offer only those (many news and
      social sites, some streaming and video-call services). The page shows
      an empty or endless-loading player; Help → About says "Does not play:
      H.264, AAC, HEVC". This build ships the official Qt WebEngine, which
      has no decoder for them, and I.K.E. ships no proprietary codec. Making
      them play through the decoders Windows itself has is separate work
      (branch `windows/engine`), not part of this installer.
- [ ] Netflix / Prime Video / Disney+: **expected not to work** in this
      preview (they need H.264 / AAC, and Widevine's verification of the
      browser). Settings → Components → Widevine → Install: note whether the
      download and installation succeed and what the services then say.

## 12. Update

There is no newer release to update to yet, so the real path cannot be
walked. What can be seen:

- [ ] Help → "Check for updates": answers "up to date" (or names a newer
      version) without an error.
- [ ] Settings → General → "I.K.E. updates": ask / automatic / off are there.
- [ ] After the first real update (the next release): I.K.E. says it was
      installed, the next start shows the new version in Help → About, and
      `%LOCALAPPDATA%\ike-browser\data\updates\versions\` holds it. The
      folder in `Programs` is not changed by a self-update: a new installer
      is needed only when a release says so.
- [ ] Installing the same or a newer setup file over the existing
      installation works, with I.K.E. closed; with I.K.E. open, the setup
      asks to close it.

## 13. Uninstall

- [ ] Settings → Apps → Installed apps → I.K.E. → Uninstall (with I.K.E.
      closed). No administrator question.
- [ ] Gone: the Start-menu entry, `%LOCALAPPDATA%\Programs\I.K.E`, I.K.E. in
      "Default apps".
- [ ] **Kept, on purpose**: `%APPDATA%\ike-browser` and
      `%LOCALAPPDATA%\ike-browser` (your bookmarks, passwords, history,
      settings). Install again: everything is back.
- [ ] To remove the data too, delete those two folders by hand.

## What to send back

The ticked list, the Windows version and graphics card, the text of
Help → About, a screenshot of anything odd, and — if something failed —
`%LOCALAPPDATA%\ike-browser\cache\errors.log` (it holds only I.K.E.'s own
error messages; look through it before sending).
