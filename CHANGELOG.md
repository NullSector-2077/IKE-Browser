# Changelog

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
