# Security audit (1.0.3)

Date: 2026-11-16. Scope: the whole repository at 1.0.2 — Python modules, the
Rust module and its interface, packaging, workflows, the way Qt WebEngine is
configured.

## Method

- Reading the code along each way data enters the browser process (see the
  trust boundaries in [architecture.md](architecture.md)).
- For every suspicion, an attack written as a test and run in the real
  browser on the local machine (local files and local servers only; nothing
  was tried against third-party sites). A finding is listed as fixed only if
  its test failed before the change and passes after it.
- Advisory databases for the dependencies (`cargo audit`, `pip-audit`).
- Not done: see "Limits of this audit" at the end.

Ratings: **Critical** — a website can run code outside the sandbox or read
the user's data without any action of the user. **High** — the user's data
can be read or changed after an ordinary action (opening a file, clicking a
link). **Medium** — a protection the user relies on does not hold, or the
browser can be stopped from outside. **Low** — hardening, needs another
weakness or local access.

No finding was rated Critical.

## Engine state

I.K.E. uses the Qt WebEngine of the system. On Arch / CachyOS that is the
`qt6-webengine` package, updated by the distribution; I.K.E. cannot update it
and does not ship one. Its age decides which Chromium security fixes are
present. Since 1.0.3 Help → About shows the Chromium version and the security
patch level reported by the engine, and a warning when the sandbox is off.

In the test environment of this audit: Qt 6.12.0, Qt WebEngine 6.140.0,
Chromium 140.0.7339.264 with security patches up to 157.0.8103.50 (the
figures the engine reports about itself).

Settings of the engine set by I.K.E. (`ike/shields.py`, `ike/webview.py`):

| Setting | Value | Note |
|---|---|---|
| Sandbox | on | off only as administrator (Chromium refuses it) and on the CI runner |
| Site isolation, process per site | engine default | not changed by I.K.E. |
| TLS certificate errors | always refused | no "continue anyway"; the only switch that accepts them works inside the test harness only |
| HTTPS-only | on by default | setting `https_only` |
| JavaScript | on; per site off from the shield | |
| Pages opening windows by script | off (`JavascriptCanOpenWindows`) | pop-ups need a click |
| Clipboard access by scripts | off | pages ask through the permission |
| DNS prefetch, hyperlink auditing (`ping`) | off | |
| WebRTC | public interfaces only when "hide local IP" is set | |
| Local content reading files | restricted since 1.0.3 | finding 1 |
| Permissions (camera, microphone, location, notifications, screen) | asked per site; a refusal is remembered by the engine | a page cannot ask again and again (tested) |
| `ike:` scheme | I.K.E.'s own pages only since 1.0.3 | finding 3 |
| Switches that turn web security off | none | checked by a test |

## Findings fixed in 1.0.3

| # | Rating | Finding | Fix | Test |
|---|---|---|---|---|
| 1 | High | **A page opened from a file could read any file the user can read** and send it to a server (Qt WebEngine lets local content read `file:` addresses by default). A downloaded HTML file, once opened, could take SSH keys, documents, the browser's own profile. | The request interceptor decides for every `file:` request of a local page: never for scripts' own requests (`fetch`, XHR), frames and objects only inside the page's folder (or `<name>_files` for a saved page), pictures / media / styles / scripts / fonts allowed as saved pages need them. | `test_reach_of_a_local_page`, `test_a_local_page_cannot_read_other_files` |
| 2 | Medium | **A clicked link with a non-web scheme started the application registered for it without a question** (`QDesktopServices`), with the address exactly as the page wrote it — the way argument-injection bugs of other programs are reached from a web page. | I.K.E. asks first, showing the site and the exact encoded address; "Cancel" is the default; nothing is started from a script without a click or from a background tab. | `test_a_link_never_starts_another_application_without_asking` |
| 3 | Low | **Web pages could load `ike:logo` and frame `ike:newtab`**: a site could recognise I.K.E. (against the purpose of presenting a common browser) and show the user's new tab page inside its own. | The scheme handler serves only requests that I.K.E. itself started. | `test_a_web_page_cannot_use_the_ike_addresses` |
| 4 | Medium | **"Cookies and site data" deleted only cookies.** Local storage, IndexedDB, service workers and the like stayed, also with "clear when closed": a tracker keeps its identifier there just as well. Qt WebEngine has no call to delete them. | `ike/sitedata.py`: the folders are removed before the engine starts next (and at exit with "clear when closed"); the dialog says that this part happens at the next start. Links are removed, never followed. | `test_clearing_site_data_removes_what_sites_stored`, `test_clear_when_closed_leaves_no_site_data`, `test_site_data_is_removed_without_following_links` |
| 5 | Medium | **A fault in the filter engine ended the browser.** The Rust module was built with `panic = "abort"`; filter lists and addresses are remote input. | `panic = "unwind"`, `catch_unwind` at every entry; the Python side counts the error and goes on (that request is not filtered by the engine). | `test_a_failing_filter_engine_never_stops_the_browser`, Rust `a_panic_becomes_an_error` |
| 6 | Medium | **Any Python error in a handler ended the browser** (PyQt6 aborts on an unhandled exception in a slot): every open tab lost, and a way to stop the browser for whatever content reaches a faulty handler. | Errors are logged and counted, the browser goes on; the tests fail on any such error. | `test_an_error_in_a_handler_does_not_end_the_browser` |
| 7 | Low | **The socket of the running instance had a predictable name in the shared temporary folder.** On a computer with several users another user could create it first and receive the addresses handed over by a second start. | Socket in `XDG_RUNTIME_DIR` with owner-only access; the old name is used only if it belongs to the same user; the message is checked (kinds, sizes). | `test_instance_socket_is_private_to_the_user`, `test_hand_over_message_is_checked` |
| 8 | Low | **Notification text could become an option of `notify-send`** (a page title starting with `-`) or markup in the notification. | `--` before the text, markup escaped. | `test_notification_text_cannot_become_an_option` |
| 9 | Low | **Test switches worked in a normal start**: an environment variable accepted invalid certificates, another granted permissions. Whoever controls the environment controls the user's programs anyway, but a protection should not have a hidden off switch. | The switches answer only inside the test harness. | `test_switches_that_turn_protections_off_need_a_test_session` |
| 10 | Low | **State files of the self-update were trusted as written**: the version folder name and the channel were used to build paths and addresses without a check. They are the user's own files, so this needs local write access. | Version names must look like versions, the channel is one of the two known, unknown content is ignored. | `test_boot_does_not_follow_a_tampered_state_file`, `test_update_channel_is_one_of_the_known_two` |
| 11 | Low | **Filter-list conditions (`!#if`) went through Python's `eval`** after a filter of the allowed words. No way around the filter was found; `eval` on remote text is not a thing to keep. | A small parser. | `test_list_conditions_are_read_without_running_code` |
| 12 | Low | **Password files were created with the default permissions and restricted afterwards** (export, vault); a copied password stayed in the clipboard and in the clipboard manager's history. | Files created owner-only from the first byte; the copy carries the hint that keeps it out of Klipper's history and is cleared after 45 s if still there. | `test_password_files_are_private_from_the_start`, `test_a_copied_password_is_marked_secret_and_cleared` |
| 13 | Low | **Settings of the wrong kind stopped the start** (a damaged or hand-edited `settings.json`). | Kinds checked on reading. | `test_settings_of_the_wrong_kind_fall_back` |
| 14 | Low | **Closing during a background download aborted the program** (possible loss of the session being saved). | `ike/background.py`. | `test_closing_while_a_download_waits_does_not_abort` |
| 15 | Low | **pyo3 0.23.5 had two published advisories** (RUSTSEC-2025-0020, RUSTSEC-2026-0177). Neither is in code the module calls. | pyo3 0.30.1; `cargo audit` reports nothing. | `cargo audit` |

Residual of finding 1: a local page can still load a picture, a media file,
a style sheet or a script from anywhere on the disk, because pages saved by
browsers and local documentation need it, and can therefore learn whether
such a file exists and, for a picture, what it shows. Text files, keys,
documents and databases are out of reach. Blocking this too would break saved
pages, against the rule of not breaking content.

## Open issues

Not fixed in 1.0.3, with the reason. None is rated above Medium.

| # | Rating | Issue | Why it is open |
|---|---|---|---|
| A | Medium | **Widevine** (optional, installed only when the user asks): the module is downloaded over HTTPS from Google and checked for being a 64-bit Linux library, but there is no pinned hash or signature to compare with, and an installed module is never updated (`drm.update_available()` exists and is not called). | Google publishes no detached signature for it; pinning a hash means a release of I.K.E. for every Widevine release. Needs a decision of the owner: pin and release, or keep as is and say so in Settings. Belongs to the component manager of the platform study. |
| B | Medium | **Chrome extensions** (experimental, off by default): the signature inside the CRX file is not verified; the download is HTTPS from the Chrome Web Store only. | Verifying CRX3 needs the protobuf header and RSA / ECDSA checks; planned with the extension work, not a quick fix. |
| C | Medium | ~~**Saved passwords are filled when the page loads**~~ — fixed in 1.1.17: filled only on a real click or Tab into the form (see below). | — |
| D | Low | ~~The vault's scrypt parameters are constants~~ — 1.1.17: read from the file, N raised to 2^17 with an automatic upgrade at unlock. **No automatic lock** after a time: left as is by the owner's choice (the fill menu asks before any login reaches a page). | — |
| E | Low | **Downloads made by I.K.E. itself** (filter lists, updates, Chrome version, Widevine) use Python's `urllib`: they follow proxy environment variables but not a proxy set only in Plasma's settings, unlike the pages. | Moving them to Qt's network stack touches four modules and their tests. |
| F | Low | ~~**GitHub Actions are pinned by tag**~~ — 1.1.17: pinned by commit hash, Dependabot updates hash and version comment. | — |
| G | Low | ~~**Permission questions of background tabs** appear over the current tab~~ — 1.1.17: they wait until the tab is shown. | — |
| H | Low | The set of redirect targets remembered by the shield (`shields.redirected`) grows during a long session. | Small (one short string per redirect); to be bounded. |
| I | Low | "Delete data of this site" clears the storage of the page's own origin through the page; data of other subdomains of the same site stays until "Clear browsing data". | Qt WebEngine has no per-site storage deletion. |
| J | Low | Starting I.K.E. **as administrator** switches the sandbox off (Chromium does not run it as root). | Shown in Help → About. Refusing to start as root is the owner's choice. |
| K | Low | Known limits already listed in the ROADMAP: DNS rebinding in user scripts' requests, user scripts of the same world trust each other, the presented graphics card can be told apart by a rendering comparison. | Unchanged. |

For the record, not a vulnerability: `IKE_TEST_HOOK` makes the browser run a
Python file at start (it is how the tests work). It is read from the
environment of the user who starts the browser, who can run any program
anyway.

## Areas reviewed without findings

- **TLS**: a server with an untrusted certificate is refused before the
  request is sent, and the page offers no way to go on
  (`test_a_server_with_an_untrusted_certificate_is_refused`, new); no switch
  weakens it; I.K.E.'s own downloads use Python's default verification with
  the system's certificate store.
- **Self-update**: signature checked before parsing, hashes before
  installing, no downgrade, bad versions remembered, roll-back when a version
  does not start (existing tests in `test_updater.py`).
- **User scripts**: tokens per script, `@grant` and `@connect` enforced,
  local addresses refused (existing attack tests in `test_userscripts.py`).
- **Password bridge**: exact-origin matching, token per profile (existing
  tests in `test_passwords.py`); vault AES-GCM with a fresh nonce per write.
- **Injected scripts and cosmetic filters**: selectors and scriptlet
  arguments from the lists are validated and escaped before injection.
- **Downloads**: a server cannot choose the place: names such as
  `../../.bashrc` or an absolute path end as plain names inside the download
  folder (the engine reduces them; I.K.E. only chooses the folder), and
  nothing is opened automatically
  (`test_a_download_cannot_choose_a_place_outside_the_download_folder`, new).
- **Archive handling** (Widevine, extensions, updates): entries leaving the
  target folder are ignored (existing tests).
- **Python ↔ Rust**: strings in, strings and plain objects out; no `unsafe`
  in the module; the cached engine is read back with adblock-rust's own
  deserialiser from the user's cache folder and rebuilt from the lists when
  it does not load.
- **Ad blocking and fingerprinting**: behaviour unchanged; their tests
  (`test_adblock.py`, `test_fingerprint.py`, `test_part_b.py`) pass as
  before. When the engine fails for a request, that request is let through
  (no general fail-closed, as the working rules ask); the cookie rules,
  HTTPS-only and the injected protections do not depend on the engine.
- **Workflows**: least-privilege `permissions`, no `pull_request_target`,
  credentials not persisted, no secrets used by the test workflow.
- **Repository**: no keys, tokens or personal data found in the tree or in
  the files added by this work.

## Limits of this audit

- Qt WebEngine, Chromium, Qt, adblock-rust, `cryptography` and Widevine were
  used, not reviewed. Their security is that of the versions installed.
- No fuzzing (of the engine module, of the list parsers, of the scheme
  handler).
- No test on a real Plasma / Wayland session: the clipboard hint with a real
  Klipper, the question for external applications with real handlers
  (`xdg-open`, KDE's dialogs), the notification of `notify-send`, and
  portals were exercised with stand-ins only.
- No test against real websites, by rule; fingerprinting protection was
  compared with itself on local pages, not judged by commercial
  fingerprinting scripts.
- No network attacker was simulated beyond an untrusted certificate on a
  local server.
- The review was done by one reviewer in one pass. A second review of
  findings 1, 2 and 4 — the ones with new logic — is worth having.

## Review of 1.1.17

Date: 2026-11-19. Scope: the browser's code at 1.1.16 (`ike/`, its scripts in
`ike/resources/`), with the same method as above: each suspicion written as an
attack in a test, run in the real browser against local servers only; a
finding is fixed only if its test failed before and passes after.

| Rating | Finding | Fix | Test |
|---|---|---|---|
| High | **A page could read a saved password without any action of the user.** With the vault unlocked, `passwords.js` filled the first visible password field of the page's origin as soon as one appeared. A script running on the site (an advert, an injected comment) built a 2×2 transparent login form and read the password the browser filled into it (the test read it 26 times in two seconds). Open issue C of 1.0.3. | The login is filled only on a trusted `pointerdown` or Tab `keyup` on the password field or its user name field; clicks, focus and key events made by the page's scripts are not trusted. A user name already typed picks its own login. The helper no longer watches the page's changes. | `test_passwords.py::test_a_page_cannot_harvest_a_saved_password` |
| Medium | **Dark mode read the home network for a web site.** The style sheets a page cannot read cross-origin were fetched by the browser (`PageBridge.fetchCss`) from any http(s) address, including this computer and private networks, and the restyled sheet ended up in the page. | `outside_home()` (shared with GM_xmlhttpRequest's check) refuses local names, private addresses and names that resolve to them, and every redirect is checked the same way (never https → http); a page of the home network itself still gets its own sheets. | `test_security.py::test_dark_mode_never_reads_the_home_network_for_a_web_site` |
| Medium | **User script updates trusted plain http and could widen a script.** The daily check installed any newer version silently, also from an `http://` update address (anybody on the same network could hand over code that runs in pages) and also when the update added sites, `@grant`s, `@connect` hosts or frames. | Automatic checks only for `https://` update addresses; an update that widens what the script may do, or loads `@require` / `@resource` over http, is shown to the user first. | `test_security.py::test_user_script_updates_that_ask_for_more_need_the_user` |
| Low | **The browser's own requests kept cookies** in one shared in-memory jar: a search engine could tie together the words typed in the address bar for its suggestions; site icon requests carried the cookies of earlier ones. | `app.network` has a jar that keeps none; user scripts have their own manager and keep theirs, as before. | the dark-mode test above (the jar stays empty) |

Areas read again without new findings: the program update (signed manifest,
hash, safe unpacking, rollback), the `ike:` scheme, the hand-over socket,
D-Bus methods (KRunner, MPRIS), the extension and Widevine downloads, filter
lists and scriptlet trust, the new tab page's escaping, downloads into the
download folder, profiles' names, private windows (no history, no icons on
disk), permissions, certificates.

Decided by the owner and done in the same version:

| Rating | Change | Test |
|---|---|---|
| — | Saved logins are offered in a menu of I.K.E. under the field (opened only by a trusted click or Tab); only the chosen login reaches the page; "Not now" is remembered for the page. The page's bridge no longer has a slot that returns logins. | `test_passwords.py::test_a_page_cannot_harvest_a_saved_password` |
| Low | Warning, once per page, when a login form of a plain http site (not this computer or the home network) is clicked. | `test_passwords.py::test_a_login_on_an_unencrypted_page_is_warned_about` |
| Low | Permission questions of background tabs wait until the tab is shown (open issue G); nothing is answered on the user's behalf meanwhile. | `test_security.py::test_a_background_tab_asks_for_a_permission_only_when_shown` |
| Low | A site that starts downloads one after another without the user's input is asked about once ("Allow" for the session, "Block"); downloads within 3 s of a click, key or address of the user, and those I.K.E. starts, never ask. | `test_security.py::test_a_site_asks_before_a_burst_of_downloads` |
| Low | Vault: scrypt N = 2^17, r = 8, p = 1 for new vaults. A vault file is accepted only if it names exactly that profile or the legacy one (N = 2^15, r = 8, p = 1, every vault of 1.0.0 to 1.1.16), as whole numbers; anything else is refused before scrypt runs (a doctored file naming N = 2^20, r = 16, p = 4 would have cost 2 GiB and four rounds per try). A legacy vault is sealed again with the current profile at unlock (open issue D, first half). | `test_passwords.py::test_vault_accepts_exactly_its_two_scrypt_profiles`, `test_vault_refuses_other_scrypt_parameters_before_running_scrypt`, `test_legacy_vault_moves_to_the_current_profile_without_losing_anything` |
| Low | GitHub Actions pinned by commit hash (open issue F). | `test_security.py::test_github_actions_are_pinned_by_commit_hash` |

Left for later, by the owner's choice: the automatic lock of the vault, and
verifying the signature of Chrome extensions (open issue B) until extensions
work and are no longer experimental.

