# Security of I.K.E.

The state of I.K.E.'s protections against attacks (not its privacy and
anti-fingerprinting work, which is in README.md and CHANGELOG.md), after the
independent security audit of 2026-11-20 and the work of 1.1.18. What is
written here was checked by a test or by a run named below; what could not be
checked says so.

## How I.K.E. is built

- **The web engine** is Qt WebEngine, the system's `qt6-webengine` from Arch
  Linux: Chromium 140 with the security fixes of later Chrome versions
  backported by Qt (Qt 6.12.0: up to Chrome 157). I.K.E. cannot update it;
  `sudo pacman -Syu` does. Help -> About shows both versions and how far
  behind the engine is; a notice comes when its security fixes are two
  Chrome versions behind.
- **Web pages run in sandboxed processes** (Chromium's renderer sandbox:
  user and PID namespaces and a seccomp filter). **Each site has its own
  process** (Site Isolation, turned on by I.K.E. since 1.1.18; Qt leaves it
  off).
- **The browser itself** (Python, PyQt6) is not sandboxed, as in every
  Chromium browser: it holds the interface, the request check
  (`ike/shields.py`), the password vault, user scripts and the updater. Pages
  reach it only through: a request interceptor (every request), console
  messages carrying a secret (user scripts, reader mode), events with a
  per-profile secret (media controls), the `ike:` scheme (locked to I.K.E.'s
  own pages) and QWebChannel in an isolated world (passwords).
- **Updates** of I.K.E. are signed (Ed25519), checked against a SHA-256,
  never older than the running version, expire after 180 days, arrive in
  stages within 24 hours and can be stopped by the owner (docs/UPDATES.md).

## Status of the audit's findings

| # | Finding | Status in 1.1.18 | Test |
|---|---|---|---|
| F1 | Site Isolation off | **Fixed**: `--site-per-process`; off only with `IKE_ALLOW_UNSAFE_ENGINE=1` | `test_site_isolation.py`, `test_sandbox.py` |
| F2 | Public pages reach the home network with subresources | **Fixed** for literal local addresses (every IPv4/IPv6 form), local names by their form and redirects; **open** for public names that resolve to a private address (DNS rebinding), see below | `test_home_network.py` |
| F3 | Media secret and worker seed readable by pages | **Fixed** | `test_media_secret.py` |
| F4 | Outdated-engine notice only at five versions | **Fixed**: two versions, reference version shown | `test_engine_age.py` |
| F5 | Releases to everybody at once, manifests never expire | **Fixed**: expiry, staged release, halt; urgent releases on request | `test_update_safety.py` |
| F6 | User-script bridge trusts the token alone | **Fixed**: the sending page must be a frame of the page that matches the script | `test_userscript_bridge.py` |
| F7 | Dangerous inherited engine switches kept silently | **Fixed**: dropped and named; kept only on request, then shown | `test_engine_switches.py`, `test_sandbox.py` |
| F8 | Root turns the sandbox off silently | **Fixed**: I.K.E. does not start as root unless asked, and says why | `test_engine_switches.py` |
| F9 | The network service runs in the browser process | **Open** (Qt WebEngine's design; nothing I.K.E. can change) | - |
| - | No vulnerability check of the Rust crates | **Fixed**: RustSec every day and on every pull request | `security.yml` (positive control below) |
| - | Tests never ran with the sandbox | **Fixed**: CI job `sandbox` | `security.yml` |

## Known limits (not solved)

- **DNS rebinding and public names of private addresses.** A public page can
  still reach a device of the home network through a public name that
  resolves to its address. The engine's own protection (Private Network
  Access / Local Network Access) does not block anything in Qt 6.12 /
  Chromium 140: tried on 2026-11-20 with every related feature switch, from
  a page served with `treat-as-public-address`. I.K.E. cannot resolve names
  in its request check without stalling every page. Literal addresses, local
  names and redirects to them are stopped. Protect the router with a
  password and keep its firmware current.
- **Workers started from a file of the site** see the real values of the
  computer (anti-fingerprinting, not an exploit protection); a partial way
  around it waits for the owner on `experiment/file-workers`.
- **The engine's patch lag** depends on Qt and Arch: Chrome fixes arrive in
  `qt6-webengine` some weeks later.
- **Certificate Transparency, HSTS preload, V8 hardening of Arch's build and
  the GPU process on real hardware** were not verified (no means here).
- `IKE_ALLOW_UNSAFE_ENGINE=1` exists for tests and special cases: with it the
  user takes protections away on purpose, and the window says so.

## The sandbox on Arch Linux and CachyOS

Chromium's sandbox on Linux needs unprivileged user namespaces, which Arch's
and CachyOS's kernels allow by default (`linux`, `linux-zen`,
`linux-cachyos`). With `linux-hardened`, or with
`kernel.unprivileged_userns_clone=0`, the engine cannot sandbox; Help ->
About then shows "Engine sandbox: OFF". I.K.E. never adds `--no-sandbox` by
itself (since 1.1.18 not even as root). To check: Help -> About must say
"Engine sandbox: on" and "Site isolation: every site in its own process".

## What was run, and where

- **This container (Ubuntu, PyPI Qt 6.12.0 / Chromium 140, as root):** every
  new test, each run on the previous code first to see it fail (F1, F2, F3,
  F5, F6) and then on the fix; `test_sandbox.py` as a normal user through
  `unshare` with the sandbox on (3 runs out of 3).
- **GitHub Actions:** the whole suite (`tests.yml`), the Arch container with
  Arch's own Qt (`arch.yml`), the sandbox job and the RustSec check
  (`security.yml`): results in the pull request.
- **RustSec positive control:** a crate pinned at a vulnerable version
  (smallvec 1.6.0) made the check fail with RUSTSEC-2021-0003; the engine's
  own crates: no advisory (2026-11-20).
- **Not run:** real hardware GPUs, a real Plasma session, real websites
  (project rule), a real DNS-rebinding service.
