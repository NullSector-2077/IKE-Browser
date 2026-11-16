# Third-party components

| Component | Where | Licence |
|---|---|---|
| adblock-rust 0.13.5 (filter engine, by Brave) | compiled into `ike_adblock.abi3.so` | MPL-2.0, see `LICENSE.adblock-rust` |
| uBlock Origin scriptlets | `ike/resources/ubo-scriptlets.json` | GPL-3.0 |
| Dark Reader | `ike/resources/darkreader.js` | MIT, see `LICENSE.darkreader` |
| Lucide icons | `ike/resources/icons/sets/lucide` | ISC, see `LICENSE.lucide` |
| Phosphor Icons | `ike/resources/icons/sets/phosphor` | MIT, see `LICENSE.phosphor` |

The Arch package uses the system's Python, PyQt6, Qt WebEngine, `python-cryptography` and `python-jeepney` packages. Qt and Python runtimes are not bundled. Filter lists are downloaded at run time from their maintainers and remain subject to their own licences. Widevine is not included; it is proprietary software by Google and is downloaded only at the user's request.

## Rust libraries linked into `ike_adblock`

See `ike-adblock/Cargo.lock` for the exact locked dependency graph and each crate's licence metadata. The upstream licences are distributed in `licenses/` where required.
