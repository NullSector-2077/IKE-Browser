# Third-party components

| Component | Where | Licence |
|---|---|---|
| adblock-rust 0.13.5 (filter engine, by Brave) | compiled into `ike_adblock.abi3.so` | MPL-2.0, see `LICENSE.adblock-rust` |
| uBlock Origin scriptlets | `ike/resources/ubo-scriptlets.json` | GPL-3.0 |
| Dark Reader | `ike/resources/darkreader.js` | MIT, see `LICENSE.darkreader` |
| Lucide icons | `ike/resources/icons/sets/lucide` | ISC, see `LICENSE.lucide` |
| Phosphor Icons | `ike/resources/icons/sets/phosphor` | MIT, see `LICENSE.phosphor` |
| Orbitron 2.001 (typeface, The Orbitron Project Authors) | the lettering of the logo and of the full name, drawn as paths in `ike/resources/ike.svg`, `ike/resources/wordmark.svg` and the icons of `data/icons` (`tools/make-brand.py`); the font itself is not shipped | SIL Open Font License 1.1, see `LICENSE.orbitron` |

The `ike_adblock` module is written for I.K.E. (sources in `ike-adblock/`,
MPL-2.0) and statically links the Rust libraries listed below, each under its
own licence.

Filter lists are downloaded at run time from their maintainers and are covered
by their own licences. Widevine is **not** included: it is proprietary software
by Google, which I.K.E. downloads from Google's server only at the user's
request.

## Used from the system

The Arch package uses the system's Python, Qt 6, Qt WebEngine (with Chromium),
PyQt6 and Python modules (python-cryptography, python-jeepney), installed and
updated by pacman under their own licences.

## Rust libraries linked into `ike_adblock`

```
adblock v0.13.5 — MPL-2.0
addr v0.15.6 — MIT/Apache-2.0
aho-corasick v1.1.5 — Unlicense OR MIT
arrayvec v0.7.8 — MIT OR Apache-2.0
base64 v0.22.1 — MIT OR Apache-2.0
bitflags v2.13.2 — MIT OR Apache-2.0
cssparser v0.35.0 — MPL-2.0
cssparser-macros v0.6.1 — MPL-2.0
derive_more v2.1.1 — MIT
derive_more-impl v2.1.1 — MIT
displaydoc v0.2.7 — MIT OR Apache-2.0
dtoa v1.0.11 — MIT OR Apache-2.0
dtoa-short v0.3.5 — MPL-2.0
either v1.19.0 — MIT OR Apache-2.0
flatbuffers v25.12.19 — Apache-2.0
heck v0.5.0 — MIT OR Apache-2.0
icu_collections v2.4.0 — Unicode-3.0
icu_locale_core v2.4.0 — Unicode-3.0
icu_normalizer v2.4.0 — Unicode-3.0
icu_normalizer_data v2.4.0 — Unicode-3.0
icu_properties v2.4.0 — Unicode-3.0
icu_properties_data v2.4.0 — Unicode-3.0
icu_provider v2.4.0 — Unicode-3.0
idna v1.1.0 — MIT OR Apache-2.0
idna_adapter v1.2.2 — Apache-2.0 OR MIT
ike-adblock v1.0.0 — MPL-2.0
itertools v0.14.0 — MIT OR Apache-2.0
itoa v1.0.19 — MIT OR Apache-2.0
libc v0.2.191 — MIT OR Apache-2.0
litemap v0.8.3 — Unicode-3.0
log v0.4.35 — MIT OR Apache-2.0
memchr v2.8.3 — Unlicense OR MIT
new_debug_unreachable v1.0.6 — MIT
once_cell v1.21.4 — MIT OR Apache-2.0
percent-encoding v2.3.2 — MIT OR Apache-2.0
phf v0.11.3 — MIT
phf_codegen v0.11.3 — MIT
phf_generator v0.11.3 — MIT
phf_macros v0.11.3 — MIT
phf_shared v0.11.3 — MIT
portable-atomic v1.15.0 — Apache-2.0 OR MIT
potential_utf v0.1.6 — Unicode-3.0
precomputed-hash v0.1.1 — MIT
proc-macro2 v1.0.107 — MIT OR Apache-2.0
psl v2.1.253 — MIT/Apache-2.0
psl-types v2.0.11 — MIT/Apache-2.0
pyo3 v0.30.1 — MIT OR Apache-2.0
pyo3-build-config v0.30.1 — MIT OR Apache-2.0
pyo3-ffi v0.30.1 — MIT OR Apache-2.0
pyo3-macros v0.30.1 — MIT OR Apache-2.0
pyo3-macros-backend v0.30.1 — MIT OR Apache-2.0
quote v1.0.47 — MIT OR Apache-2.0
rand v0.8.8 — MIT OR Apache-2.0
rand_core v0.6.4 — MIT OR Apache-2.0
regex v1.13.1 — MIT OR Apache-2.0
regex-automata v0.4.18 — MIT OR Apache-2.0
regex-syntax v0.8.11 — MIT OR Apache-2.0
rustc-hash v2.1.3 — Apache-2.0 OR MIT
rustc_version v0.4.1 — MIT OR Apache-2.0
seahash v4.1.0 — MIT
selectors v0.32.0 — MPL-2.0
semver v1.0.28 — MIT OR Apache-2.0
serde v1.0.229 — MIT OR Apache-2.0
serde_core v1.0.229 — MIT OR Apache-2.0
serde_derive v1.0.229 — MIT OR Apache-2.0
serde_json v1.0.154 — MIT OR Apache-2.0
servo_arc v0.4.3 — MIT OR Apache-2.0
siphasher v1.0.4 — MIT OR Apache-2.0
smallvec v1.16.5 — MIT OR Apache-2.0
stable_deref_trait v1.2.1 — MIT OR Apache-2.0
syn v2.0.119 — MIT OR Apache-2.0
syn v3.0.10 — MIT OR Apache-2.0
synstructure v0.14.0 — MIT
target-lexicon v0.13.6 — Apache-2.0 WITH LLVM-exception
thiserror v1.0.69 — MIT OR Apache-2.0
thiserror-impl v1.0.69 — MIT OR Apache-2.0
tinystr v0.8.5 — Unicode-3.0
unicode-ident v1.0.27 — (MIT OR Apache-2.0) AND Unicode-3.0
utf8_iter v1.1.0 — Apache-2.0 OR MIT
utf_types v1.0.0 — Apache-2.0 OR MIT
writeable v0.6.4 — Unicode-3.0
yoke v0.8.4 — Unicode-3.0
yoke-derive v0.8.4 — Unicode-3.0
zerofrom v0.1.8 — Unicode-3.0
zerofrom-derive v0.1.8 — Unicode-3.0
zerotrie v0.2.5 — Unicode-3.0
zerovec v0.11.9 — Unicode-3.0
zerovec-derive v0.11.7 — Unicode-3.0
zmij v1.0.23 — MIT
```
