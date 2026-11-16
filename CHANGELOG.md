# Changelog

## 1.0.2

- **Toolbar buttons can be moved reliably.** A long press and drag, or the new
  "Customise toolbar" mode (right-click the toolbar, or the View menu), where
  the buttons show an outline and are dragged at once. A marker shows where
  the button will land, on either side of the address bar; the arrangement is
  saved and shown in every window, and "Reset to default layout" brings back
  the original one. Back, Forward and Home and the separator after them stay
  in place. (Before, the toolbar rebuilt the dragged button at the first
  movement, so the drag stopped and nothing was saved.)
- In a narrow window the buttons that do not fit are listed under a » button
  instead of pushing the menu and the window buttons out of view.
- Back, Forward and Home can now really be hidden from "Toolbar buttons" (the
  choice was offered in Settings but had no effect).
- **New tab page: your own photo as background** (Settings → General): fill
  the page, show the whole photo or centre it, with a veil in the page's own
  colour to keep the text readable. A copy is kept in I.K.E.'s data folder
  (scaled down once if larger than a 4K screen) and is never sent anywhere; web
  pages cannot load it. The interface colours and the theme do not change.
- **Interface effects**, all light: the shield panel and the menus fade in, the
  red of I.K.E.'s own close buttons glides in on hover, the loading line
  advances smoothly, and a tab that takes a while to load shows a small
  turning mark. They are off when the desktop is set to show no animations
  (Plasma's animation speed at "Instant") and can be turned off in Settings →
  Appearance. Processor time, memory and start-up measured before and after:
  no difference (`tests/measure_idle.py`, `tests/measure_startup.py`).
- Tooltips of buttons and menu entries also show the keyboard shortcut.
- Two messages that were shown only in English are translated.

## 1.0.1

- The logo, the application icon at every size and the new tab page show
  "I.K.E"; the lettering of the logo and of the full name, "Internet Kontrol
  Experience", is drawn as shapes from the Orbitron typeface (SIL Open Font
  License), so it looks the same on every system and needs no font installed.
  The interface fonts are unchanged.
- The shield in the toolbar is drawn about 18% larger inside the same button,
  and is now sharp at every screen scale. Ad blocking is unchanged.
- Hovering a link no longer shows its address in a bar at the bottom of the
  window, so the page no longer moves. The bar still appears for zoom and
  toolbar messages.
- Removed the one-time import of the earlier installation, which every
  installation has completed. A password vault that was never opened with
  I.K.E. 1.0.0 must be opened once with 1.0.0 before updating.
- This release changes the icons installed with the package, so it is installed
  as a package (`sudo pacman -U …`); I.K.E. 1.0.0 announces it instead of
  updating itself.

## 1.0.0

First release of I.K.E. — Internet Kontrol Experience, for Arch Linux and
CachyOS.

- Privacy shield with five levels (Off, Compatibility, Balanced, Strict,
  Maximum), per-site levels and "Repair this site".
- I.K.E. AdBlock Engine (adblock-rust) with EasyList, EasyPrivacy, uBlock
  filters and regional lists, cosmetic filtering, uBlock Origin scriptlets and
  YouTube video-ad removal.
- Fingerprinting protection that changes per site and per session, including a
  common graphics-card model instead of the real one; the presented Chrome
  version follows the current stable release automatically.
- Password vault (AES-256-GCM), passkeys and security keys, user scripts with
  per-script permissions, containers, workspaces, tab groups, split view,
  vertical tabs, watched pages, site resources, Widevine installed on request.
- KDE Plasma integration: media controls, downloads, KRunner, KDE Connect.
- Interface themes, icon sets and eight languages.
- Signed self-update from GitHub releases with automatic roll-back.
- Daily automatic check of the bundled components, with a tested candidate
  release prepared on GitHub Actions for the owner to approve.
- At the first start, the settings, bookmarks, history, passwords, cookies and
  user scripts of the earlier installation are imported; the old folders are
  removed once I.K.E. has started correctly.
