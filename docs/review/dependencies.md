# Dependencies

State on 2026-11-16. Licences are reported as the projects declare them; this
is a technical inventory, not legal advice.

## Used from the system (Arch / CachyOS package)

| Component | Package | Updated by | Note |
|---|---|---|---|
| Python 3 | `python` | pacman | |
| Qt 6, Qt SVG, Qt WebChannel | `qt6-base`, `qt6-svg`, `qt6-webchannel` | pacman | LGPL-3.0 / GPL (as packaged by Arch) |
| Qt WebEngine with Chromium | `qt6-webengine` | pacman | Decides which Chromium security fixes are present. I.K.E. shows the version and the security patch level in Help → About |
| PyQt6, PyQt6-WebEngine | `python-pyqt6`, `python-pyqt6-webengine` | pacman | GPL-3.0 (Riverbank), compatible with I.K.E.'s GPL-3.0-or-later |
| cryptography | `python-cryptography` | pacman | Vault (scrypt, AES-GCM), update signatures (Ed25519) |
| jeepney | `python-jeepney` | pacman | D-Bus (desktop integration) |

Nothing of this is shipped inside I.K.E.'s package, so fixes arrive with the
system's updates. The other side of it: I.K.E. cannot make the engine newer
than the distribution's. On a system that is not updated, the engine is old.

## Built into the package

| Component | Version | Licence | Advisories | Note |
|---|---|---|---|---|
| adblock-rust | 0.13.5, pinned exactly | MPL-2.0 | none known | Checked daily by `tools/check-components.py` |
| pyo3 | 0.30.1 (was 0.23.5) | MIT OR Apache-2.0 | 0.23.5: RUSTSEC-2025-0020 and RUSTSEC-2026-0177, in functions the module does not call; none for 0.30.1 | Upgraded in 1.0.3 |
| Other Rust crates (86, through adblock-rust, pyo3 and serde_json) | pinned by `Cargo.lock` | MIT, Apache-2.0, MPL-2.0, Unicode-3.0, Unlicense (one of the choices), LLVM exception | `cargo audit`: 0 vulnerabilities in 89 crates | Listed in `docs/THIRD-PARTY.md` |
| uBlock Origin scriptlets | built from a pinned commit by `tools/build-ubo-scriptlets.mjs` | GPL-3.0 | — | Data file, checked daily |
| Dark Reader | its lists only since 1.1.30 (`darkreader-data.json`), read by the I.K.E. Dark Engine | MIT | — | The engine itself left I.K.E. in 1.1.30 |
| Lucide, Phosphor icons | bundled SVG | ISC, MIT | — | |
| Orbitron | not shipped: only shapes drawn from it | SIL OFL 1.1 | — | Approved brand artwork |

## Downloaded at run time

| What | From | Integrity |
|---|---|---|
| Filter lists (EasyList, EasyPrivacy, uBlock Origin lists, the user's own) | the lists' own servers, HTTPS | TLS only; the content is text parsed by a memory-safe parser, selectors and scriptlet arguments are validated before use |
| Self-update of the Python part | the address in the package (GitHub releases) | Ed25519 signature of the manifest, SHA-256 of the payload, no downgrade |
| Current Chrome version (for the identity presented to sites until 1.1.13; since 1.1.14 only for the engine's age in Help → About) | Google's version service, HTTPS | A version number, checked for its form and bounded |
| Weather on the new tab page (optional) | Open-Meteo, HTTPS | Numbers shown as text |
| Widevine (only when the user asks) | Google, HTTPS | TLS and a check of the file's kind; no pinned hash — open issue A of the audit |
| Chrome extensions (experimental, off by default) | Chrome Web Store, HTTPS | TLS; CRX signature not verified — open issue B |

## Test and build tools

| Tool | Version in the audit | Note |
|---|---|---|
| PyQt6 / PyQt6-WebEngine from PyPI (tests outside Arch, GitHub runner) | 6.12.0 / 6.140.0, pinned in `tools/test-requirements.txt` | `pip-audit -r tools/test-requirements.txt`: no known vulnerabilities |
| cryptography, cffi, certifi, jeepney | pinned in the same file | same result |
| Rust | stable (1.97.0 in the audit) | `--locked` builds |
| ruff, pytest | runner's current | not shipped |
| GitHub Actions: `actions/checkout@v5`, `actions/setup-python@v6`, `dtolnay/rust-toolchain@stable`, `actions/cache@v4`, `actions/upload-artifact@v4` | pinned by tag | open issue F: pin by commit hash |

## Assessment

- **Outdated or unmaintained**: none found. `tools/check-components.py`, run
  against the real sources on the day of the audit, reports adblock-rust
  0.13.5 as the current release and the bundled scriptlets as unchanged in
  the newest uBlock Origin commit. It also reports new bindings for the test
  environment (PyQt6 6.12.1, PyQt6-WebEngine 6.140.1; the Qt libraries
  themselves unchanged): left to the daily maintenance workflow, so that the
  final tests of 1.0.3 ran on the versions the earlier ones ran on.
- **Needless**: none found. Each dependency is used; the three direct Rust
  dependencies are the minimum for the module.
- **Licences**: everything built in is under a licence compatible with
  distribution under GPL-3.0-or-later (MPL-2.0 files stay under MPL-2.0;
  their licence text is in `licenses/`). Widevine is proprietary and is
  neither shipped nor installed without the user's request. The codec
  question (H.264, AAC through the system's FFmpeg on Linux; Windows) is
  treated in `docs/platforms/` (archive branch `docs/multiplatform-plan`).
- **How to repeat the checks**:

  ```bash
  cargo install cargo-audit && cargo audit --file ike-adblock/Cargo.lock
  pip install pip-audit && pip-audit -r tools/test-requirements.txt
  python3 tools/check-components.py
  ```
