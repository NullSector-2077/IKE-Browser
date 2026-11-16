# Architecture

## Processes

```
ike-browser (C launcher, /usr/bin)
  └─ python ike_boot.py            chooses the version to run (package or a verified self-update)
       └─ ike.app.main()           one Qt application: windows, settings, protections
            ├─ QtWebEngineProcess  one renderer per site (Chromium, sandboxed)
            ├─ QtWebEngineProcess  GPU process
            └─ QtWebEngineProcess  network service
```

The browser process is Python. Web content never runs in it: pages run in
Chromium's renderer processes, inside Chromium's sandbox (kernel namespaces
and seccomp-bpf). I.K.E. does not switch the sandbox off; the two exceptions
are a start as administrator, where Chromium cannot use it, and the GitHub
runner. Help → About says when it is off.

## Layers

| Layer | Files | Role |
|---|---|---|
| Start | `launcher/ike-browser.c`, `ike_boot.py` | Start Python; pick the newest version whose signature and hashes were verified, fall back to the packaged one |
| Application | `ike/app.py`, `ike/config.py`, `ike/background.py`, `ike/sitedata.py` | One instance per user and profile, settings (JSON), profiles and containers, background downloads, clearing data |
| Windows | `ike/window.py`, `ike/features.py`, `ike/toolbar.py`, `ike/tabs.py`, `ike/urlbar.py`, `ike/dialogs.py`, `ike/shieldpanel.py`, `ike/contextmenu.py`, `ike/effects.py`, `ike/themes.py`, `ike/icons.py`, `ike/closebutton.py`, `ike/loadingline.py`, `ike/tabpreview.py`, `ike/downloadring.py`, `ike/newtabbg.py` | The interface: Qt Widgets, the system's style and colours |
| Pages | `ike/webview.py` | `QWebEnginePage` / `QWebEngineView`: navigation rules, permissions, certificate errors, new windows |
| Protection | `ike/shields.py`, `ike/blocker.py`, `ike/scriptlets.py`, `ike/repair.py`, `ike/chromever.py`, `ike/osinfo.py` | Request interceptor, cookie filter, injected scripts (fingerprinting, cosmetic filters, scriptlets), the `ike:` scheme, the identity presented to sites |
| Filter engine | `ike-adblock/src/lib.rs` → `vendor/adblock/ike_adblock.abi3.so` | adblock-rust behind a PyO3 module (stable ABI) |
| Data | `ike/storage.py`, `ike/passwords.py`, `ike/favicons.py`, `ike/importer.py` | History and bookmarks (SQLite), the encrypted vault, import / backup |
| Extras | `ike/userscripts.py`, `ike/extensions.py`, `ike/watcher.py`, `ike/resources.py`, `ike/weather.py`, `ike/drm.py` | User scripts, Chrome extensions (experimental), page watcher, per-site resources, weather, Widevine |
| Desktop | `ike/plasma.py`, `ike/desktopbus.py` | Media controls, KRunner, download notifications, KDE Connect over D-Bus |
| Update | `ike/updater.py`, `tools/make-release.py` | Daily check, Ed25519 signature of the manifest and SHA-256 of what it names, staged install, roll-back |

## Trust boundaries

1. **Web content → browser process.** The only ways in are: the request
   interceptor and cookie filter (data: URLs, headers, types), the `ike:`
   scheme handler, console messages used as the channel of user scripts and
   the password bridge (each guarded by a per-profile or per-script secret
   token), titles and addresses shown in the interface and handed to the
   desktop (notifications, media controls), downloads, and permission
   requests. The audit looked at each of them.
2. **Remote lists → browser process.** Filter lists and scriptlet rules are
   remote text. They are parsed by adblock-rust (Rust, memory safe) and by
   `ike/scriptlets.py`; selectors and scriptlet arguments are escaped before
   they are injected. Since 1.0.3 a fault of the engine cannot end the
   browser and list conditions are no longer evaluated with `eval`.
3. **Update server → program.** Only files whose manifest is signed with the
   owner's Ed25519 key (public key in the package) and whose SHA-256 matches
   are run; a version older than the running one or needing a newer package is
   refused. The private key is never in the repository, in a package or on
   GitHub Actions.
4. **Local files and other local users.** The profile is in the user's own
   folders; the vault is encrypted (scrypt + AES-GCM); since 1.0.3 the socket
   of the running instance is in the user's runtime folder and pages opened
   from files cannot read other files.
5. **Python ↔ Rust.** The module exposes five calls taking strings and
   returning strings / small objects. No pointers cross the boundary, the
   Rust side has no `unsafe` of its own, and since 1.0.3 a panic is caught at
   the boundary and becomes a Python exception.

## Notes from the code review

- `ike/window.py` (about 1,900 lines), `ike/dialogs.py` (1,600) and
  `ike/features.py` (1,200) carry too much. They were not split in 1.0.x: the
  split has no user-visible gain, touches almost every test and would have
  hidden the security changes in a large diff. It is listed in
  [remaining-work.md](remaining-work.md).
- `IkeWindow` and `IkeApp` know each other closely (the window calls the
  application for almost everything). New code (`toolbar.py`, `effects.py`,
  `newtabbg.py`, `sitedata.py`, `background.py`) was written as small modules
  with a narrow surface and their own tests, the direction for later work.
- Background work uses `QThread` objects owned by the application; since
  1.0.3 they are started through `ike/background.py`, which also lets them
  finish or detaches them when the browser closes.
