# Roadmap

I.K.E. starts at 1.0.0 for Arch Linux and CachyOS. Versions go up in order
(1.0.1, 1.0.2, …); maintenance releases prepared by GitHub Actions raise the
last number. Decisions below are agreed with the project owner; do not reopen
them without asking.

## Working rules

- Discuss changes before writing code; the owner gives the go-ahead.
- Small, targeted changes; do not rewrite what already works.
- Security and features have the same priority: no feature removed, ad
  blocking and fingerprinting protection never weakened, no general
  "fail-closed", the browser stays light and fast (measure before and after).
- Never break websites to improve a test score.
- Keep the project independent: no other browser's branding or identity, no
  external services beyond those documented in README.md.
- Each step goes on its own branch with a pull request whose base is `main`
  (no pull requests stacked on other pull requests); never write to `main`
  without the owner's approval. The repository is public: never commit
  personal data, keys or secrets.
- The private signing key stays with the owner: never in the repository, in a
  package or on GitHub Actions.
- Test on the real browser (headless PyQt6 + Qt WebEngine) with the existing
  automatic tests (`ruff check .`, `python3 -m pytest`), add tests for new
  parts, including tests that simulate attacks, and say clearly what could not
  be tested.
- Deliver an installable package (`ike-browser-<version>-1-x86_64.pkg.tar.zst`)
  built from the PKGBUILD, update CHANGELOG.md and docs/TESTING.md, and guide
  the owner step by step to sign and publish the release.
- Documentation in English; the owner talks in Italian and prefers short,
  plain explanations.

## Now: Arch Linux / CachyOS

1.0.0 is the base: the browser, its protections, the signed self-update and
the daily component maintenance on GitHub Actions, for Arch-based systems only.

## Next

1. **Remove the one-time import** (`ike/legacy.py`, its call in `ike/app.py`,
   its tests, the fallback in `ike/passwords.py`, and `conflicts` / `replaces`
   in the PKGBUILD) once the owner confirms the earlier installation was
   imported and its folders are gone.
2. **AUR**: publish I.K.E. on the Arch User Repository — when the owner says
   it is time.
3. **Licence**: GPL-3.0-or-later for now; the owner may decide to change it.

## Later

- Other Linux distributions and Windows: to be planned again from scratch when
  the owner asks.
- Android: a separate project. Qt WebEngine does not exist on Android, so it
  would need Android's WebView and a rework of ad blocking, fingerprinting
  protection and user scripts.

## Starting a new session

The owner opens a new conversation, attaches this repository and pastes this
prompt, replacing `<TASK>` and `<VERSION>`:

```
Ciao! Lavoriamo a I.K.E. Browser, repository GitHub NullSector-2077/IKE-Browser
(pubblico). Collegalo a questa sessione e leggi prima README.md, CHANGELOG.md,
docs/TESTING.md, docs/UPDATES.md, docs/MAINTENANCE.md e soprattutto
ROADMAP.md: lì ci sono la lista dei lavori, le decisioni già prese e le regole
di lavoro.

Oggi facciamo: <TASK> (versione <VERSION>).

Segui le regole di lavoro della ROADMAP. Prima di scrivere codice dimmi cosa
farai e aspetta il mio "vai". Alla fine consegnami
ike-browser-<VERSION>-1-x86_64.pkg.tar.zst costruito dal PKGBUILD e guidami
passo passo a firmare e pubblicare la release.

Il mio sistema: CachyOS, KDE Plasma 6 su Wayland, shell fish, terminale
Konsole. Il comando di installazione deve puntare a
"/mnt/CachyStorage/D O W N L O A D/". Rispondimi in italiano, in modo breve e
chiaro.
```

## Known limits to keep in mind

- With DejaVu Sans as the system font, Settings → Appearance scrolls sideways
  by a few pixels in German and Spanish (fine with Noto Sans, Plasma's font).
- Closing I.K.E. while the filter lists or the Chrome version are still being
  downloaded (a few seconds after start-up, or during the daily update) can end
  with "QThread: Destroyed while thread is still running" and an abort instead
  of a clean exit.
- Media controls: next / previous track are not offered (they would need a
  hook inside the pages' own scripts); media inside frames (embedded players)
  are not seen.
- KRunner may need to restart once (or a new login) before it sees I.K.E.'s
  runner file the first time.
- User scripts: `GM_registerMenuCommand` is accepted but shows no menu;
  `GM_xmlhttpRequest` to other sites works from the page but not from frames.
  A name that resolves to a public address when checked and to a local one
  when the request is made (DNS rebinding) is not caught. Scripts in the same
  world trust each other: a malicious installed script could watch another
  one's messages (scripts are installed by the user).
- The graphics card presented to sites is a plausible common model; a script
  comparing rendering with the model could notice the mismatch.
- The bundled Dark Reader page dark mode is not reliable; Qt's own dark mode
  works and is the one to use.
- The ad-blocking engine is adblock-rust (Brave's open-source library, MPL-2.0)
  with uBlock Origin / EasyList filter lists and uBlock Origin scriptlets; the
  integration around them is I.K.E.'s own.
