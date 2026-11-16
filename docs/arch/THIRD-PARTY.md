# Third-party components

| Component | Where | Licence |
|---|---|---|
| adblock-rust (filter engine, by Brave) | compiled into `ike_adblock.abi3.so` | MPL-2.0, see `LICENSE.adblock-rust` |
| uBlock Origin scriptlets | `ike/resources/ubo-scriptlets.json` | GPL-3.0 |
| Dark Reader | `ike/resources/darkreader.js` | MIT, see `LICENSE.darkreader` |
| Lucide icons | `ike/resources/icons/sets/lucide` | ISC, see `LICENSE.lucide` |
| Phosphor Icons | `ike/resources/icons/sets/phosphor` | MIT, see `LICENSE.phosphor` |

The `ike_adblock` module is written for I.K.E. (sources in `ike-adblock/`, MPL-2.0) and statically links the Rust libraries listed below, each under its own licence.

Filter lists are downloaded at run time from their maintainers and are covered by their own licences. Widevine is **not** included: it is proprietary software by Google, which I.K.E. downloads from Google's server only at the user's request.

## System-provided runtime

The Arch package does not bundle these runtimes; pacman supplies them:

| Component | Licence |
|---|---|
| CPython | PSF-2.0 |
| PyQt6 and PyQt6-WebEngine (Riverbank Computing) | GPL-3.0 |
| Qt 6 and Qt WebEngine, including Chromium (The Qt Company) | LGPL-3.0 (Chromium: BSD-3-Clause and others) |
| cryptography | Apache-2.0 OR BSD-3-Clause |
| jeepney (D-Bus messages for desktop integration) | MIT |

## Rust libraries linked into `ike_adblock`

The list below records the licence expressions for the imported 1.6.1 dependency set. `ike-adblock/Cargo.lock` is the authoritative version lock. Review this inventory whenever that lockfile changes, especially when a dependency is added or replaced.

```
adblock — MPL-2.0
addr — MIT/Apache-2.0
aho-corasick — Unlicense OR MIT
arrayvec — MIT OR Apache-2.0
base64 — MIT OR Apache-2.0
bitflags — MIT OR Apache-2.0
cfg-if — MIT OR Apache-2.0
cssparser — MPL-2.0
cssparser-macros — MPL-2.0
derive_more — MIT
derive_more-impl — MIT
displaydoc — MIT OR Apache-2.0
dtoa — MIT OR Apache-2.0
dtoa-short — MPL-2.0
either — MIT OR Apache-2.0
flatbuffers — Apache-2.0
heck — MIT OR Apache-2.0
ike-adblock — MPL-2.0
icu_collections — Unicode-3.0
icu_locale_core — Unicode-3.0
icu_normalizer — Unicode-3.0
icu_normalizer_data — Unicode-3.0
icu_properties — Unicode-3.0
icu_properties_data — Unicode-3.0
icu_provider — Unicode-3.0
idna — MIT OR Apache-2.0
idna_adapter — Apache-2.0 OR MIT
indoc — MIT OR Apache-2.0
itertools — MIT OR Apache-2.0
itoa — MIT OR Apache-2.0
libc — MIT OR Apache-2.0
litemap — Unicode-3.0
log — MIT OR Apache-2.0
memchr — Unlicense OR MIT
memoffset — MIT
new_debug_unreachable — MIT
once_cell — MIT OR Apache-2.0
percent-encoding — MIT OR Apache-2.0
phf — MIT
phf_generator — MIT
phf_macros — MIT
phf_shared — MIT
potential_utf — Unicode-3.0
precomputed-hash — MIT
proc-macro2 — MIT OR Apache-2.0
psl — MIT/Apache-2.0
psl-types — MIT/Apache-2.0
pyo3 — MIT OR Apache-2.0
pyo3-build-config — MIT OR Apache-2.0
pyo3-ffi — MIT OR Apache-2.0
pyo3-macros — MIT OR Apache-2.0
pyo3-macros-backend — MIT OR Apache-2.0
quote — MIT OR Apache-2.0
rand — MIT OR Apache-2.0
rand_core — MIT OR Apache-2.0
regex — MIT OR Apache-2.0
regex-automata — MIT OR Apache-2.0
regex-syntax — MIT OR Apache-2.0
rustc-hash — Apache-2.0 OR MIT
seahash — MIT
selectors — MPL-2.0
serde — MIT OR Apache-2.0
serde_core — MIT OR Apache-2.0
serde_derive — MIT OR Apache-2.0
serde_json — MIT OR Apache-2.0
servo_arc — MIT OR Apache-2.0
siphasher — MIT OR Apache-2.0
smallvec — MIT OR Apache-2.0
stable_deref_trait — MIT OR Apache-2.0
syn — MIT OR Apache-2.0
syn — MIT OR Apache-2.0
synstructure — MIT
target-lexicon — Apache-2.0 WITH LLVM-exception
thiserror — MIT OR Apache-2.0
thiserror-impl — MIT OR Apache-2.0
tinystr — Unicode-3.0
unicode-ident — (MIT OR Apache-2.0) AND Unicode-3.0
unindent — MIT OR Apache-2.0
utf8_iter — Apache-2.0 OR MIT
utf_types — Apache-2.0 OR MIT
writeable — Unicode-3.0
yoke — Unicode-3.0
yoke-derive — Unicode-3.0
zerofrom — Unicode-3.0
zerofrom-derive — Unicode-3.0
zerotrie — Unicode-3.0
zerovec — Unicode-3.0
zerovec-derive — Unicode-3.0
zmij — MIT
```
