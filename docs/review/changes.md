# Changes in 1.0.1, 1.0.2 and 1.0.3

Each version is on its own branch and pull request (`ike-1.0.1`, `ike-1.0.2`,
`ike-1.0.3`), each built on the one before. The user-facing list is in
[CHANGELOG.md](../../CHANGELOG.md); this file says what was found, why it was
changed and where.

## 1.0.1 — clean-up and brand

| Change | Files |
|---|---|
| Removed the one-time import of the earlier installation and the old-vault fallback (every installation has completed it) | `ike/legacy.py` and `tests/test_legacy.py` deleted; `ike/app.py`, `ike/passwords.py`, `PKGBUILD` (`conflicts` / `replaces` gone) |
| Logo, application icons and wordmark drawn as shapes from Orbitron (SIL OFL), shipped from the approved artwork | `ike/resources/ike.svg`, `ike/resources/wordmark.svg`, `data/icons/`, `ike/resources/newtab.html`, `licenses/LICENSE.orbitron`, `docs/THIRD-PARTY.md` |
| Protection hexagon drawn as a regular vector, sized to the address field | `ike/shieldpanel.py` (`paint_shield`, `shield_icon`, `TOOLBAR_SHIELD_GROW`) |
| Link preview bar removed | `ike/window.py` |

### Link preview bar

Hovering a link showed its address in a status bar that appeared at the bottom
of the window and took space from the page, so the page moved under the mouse.
The connection from `linkHovered` to the status bar was removed. The bar
itself stays for zoom and toolbar messages, which do not depend on the mouse
position. `tests/test_linkbar.py` checks on a local page that hovering a link
does not change the size of the page and that the other messages still show.

## 1.0.2 — toolbar, interface effects, new-tab background

### Toolbar: what was wrong

Moving a button by long press worked "sometimes". The cause, reproduced in a
test before any change:

1. The old code rearranged the toolbar **while** the button was being dragged.
2. `QToolBar` creates a new button widget every time an action is inserted.
   The widget that was receiving the mouse events was destroyed at the first
   step of the drag.
3. So the drag stopped, the button stayed wherever that first step had put
   it, nothing was saved, and the new widget had no long-press handler.

Two more problems found on the way: in a narrow window Qt's own overflow hid
the menu and the window buttons instead of the optional buttons; and the
"Back / Forward / Home" entries of "Toolbar buttons" in Settings had no effect.

### Toolbar: what was done

- `ike/toolbar.py` (new) holds **one description** of the arrangement
  (`ToolbarLayout`: left zone, right zone, hidden buttons) used by every
  window and stored in the settings; the old setting is read and kept.
- `ToolbarMover` shows a marker and a ghost of the button during the drag and
  applies the move **once, on release**. QToolBar is kept.
- A "Customise toolbar" mode (context menu of the toolbar, View menu, Esc to
  leave), "Reset to default layout", the long press kept.
- Own overflow: buttons that do not fit go under a » button (`spill()`), so
  the address bar, the menu and the window buttons stay visible at every
  width and scale.
- Files: `ike/toolbar.py`, `ike/features.py`, `ike/window.py`, `ike/app.py`,
  `tests/test_toolbar.py`.

### Visual changes

All in `ike/effects.py` (new), switched by one setting (`ui_effects`) and off
when the desktop asks for no animations: menus and the shield panel fade in,
the red of I.K.E.'s own close buttons glides in, the loading line advances
smoothly, a tab that loads for a while shows a small turning mark; tooltips
show the keyboard shortcut. The system's style, colours and fonts are used as
before; no palette is fixed. Files: `ike/effects.py`, `ike/closebutton.py`,
`ike/tabs.py`, `ike/loadingline.py`, `ike/window.py`, `ike/dialogs.py`,
`ike/themes.py`, `tests/test_effects.py`.

### New-tab background

`ike/newtabbg.py` (new): a photo chosen by the user, copied into I.K.E.'s data
folder (scaled once if larger than a 4K screen), served as `ike:background`
to the new tab page only, with a veil in the page's colour.
`tests/test_newtab_background.py`.

## 1.0.3 — code review and security audit

Security changes are described one by one in
[security-audit.md](security-audit.md). The rest:

### Clean-up results

| Found | Done |
|---|---|
| Unused functions: `storage.set_title`, `tabs._row_at`, `desktopbus.unexport`, `desktopbus.name_has_owner`, `scriptlets.has_rules`, `scriptlets.embed_scripts`; an unused parameter of `shields.dark_for`; a condition that was always true in the status bar code (`or True`) | Removed |
| Five places started a `QThread` each in its own way; none handled the browser closing while the thread ran | One helper, `ike/background.py` |
| Messages of the interface without a translation could go unnoticed (the check only compared the language packs with each other) | `tools/check-lang.py` now reads the `T("…")` strings of the source; four missing strings translated |
| Rust library list in `docs/THIRD-PARTY.md` out of step with `Cargo.lock` | Regenerated (89 crates) |
| Test switches read straight from the environment in several modules | One function, `osinfo.test_switch()`, which only answers inside the test harness |

ruff reports no unused import or variable (it is part of the workflow). No
needless dependency was found: the Python side needs PyQt6, PyQt6-WebEngine
and `cryptography`; the Rust side adblock-rust, pyo3 and serde_json.

Not done, on purpose: splitting `window.py`, `dialogs.py` and `features.py`
(see [architecture.md](architecture.md)).

### Stability

| Found | Done |
|---|---|
| A Python error escaping from a signal handler makes PyQt6 end the program: one broken handler closed every tab | `app._keep_running_after_errors()`: logged to the terminal and to `errors.log`, counted in Help → About, the browser goes on. The tests now fail on any such error |
| Closing while a background download ran: "QThread: Destroyed while thread is still running", abort (exit code -6) | `background.let_go()`: waits briefly, then detaches the thread from the objects being destroyed. Exit code 0 |
| adblock-rust built with `panic = "abort"`: a fault in the engine ended the browser | `panic = "unwind"` and `catch_unwind` at every entry of the module; the Python side treats the error as "engine not available for this call" |
| A value of the wrong kind in `settings.json` could stop the start | Kinds checked when the file is read; the default is used instead |

### Optimisations (each one measured)

| Change | Before | After | How measured |
|---|---|---|---|
| Applying the settings rebuilt the filter engine (read back from its cache) even when no list had changed | 0.29 s | 0.00 s | A second `Blocker.load()` with six real default lists (EasyList, EasyPrivacy, four uBlock Origin lists) saved once to a local folder; package 1.0.2 against package 1.0.3 |
| Not an optimisation, a cost: pyo3 0.23 → 0.30 and the panic guard around every engine call | 1.40–1.51 µs per request | 1.47–1.63 µs per request | Median of 7 rounds of 4,000 `check_network_urls` calls against 53,000 generated rules, three alternating runs of the module of each package. About 0.1 µs more per request: under 0.01 ms for a page of a hundred requests, not visible in the page-load times |

No other optimisation is claimed. The review looked for repeated or blocking
work at start-up, when a tab opens and on every request, and found nothing
whose cost showed up in a measurement: start-up is dominated by Qt WebEngine
itself, and the interceptor spends its time in the engine call above. The
whole-program measurements are in
[tests-and-performance.md](tests-and-performance.md).

### Compatibility

- Settings: no key removed or renamed; new keys have defaults
  (`tests/settings-keys.json` lists every key and is checked by a test).
- Internal interfaces used by the tests and by user data (vault format,
  history database, update manifest) are unchanged.
- `__min_system__` is 1.0.1 since 1.0.1 (the icons under `/usr` changed), so
  1.0.0 installations get 1.0.1 and later as a package, not through the
  self-update. 1.0.2 and 1.0.3 do not raise it. The hardening of the engine
  module and of `ike_boot.py` in 1.0.3 lives in the package and reaches a
  self-updated installation only with the next package.
