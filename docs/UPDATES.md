# Updates

| What | How it updates |
|---|---|
| Filter lists | daily, by I.K.E. (Settings → Components) |
| Chrome version presented to sites | the engine's own version (1.1.14), so it follows the system's `qt6-webengine` (at Strict and Maximum only its major number, 140.0.0.0, since 1.1.18); the current stable Chrome is checked daily (Google's public version list) only to show the engine's age in Help -> About |
| User scripts | daily, from their update address |
| Web engine (Qt WebEngine) | with the system (`sudo pacman -Syu`) |
| I.K.E. itself, AdBlock engine included | signed update channel on GitHub Releases, described below; installed automatically by default (1.1.13), once a day at most, used at the next start |
| Components inside I.K.E. (AdBlock engine, uBlock Origin scriptlets) | checked daily and prepared as a tested candidate by GitHub Actions on a separate branch; merged once its tests are green, then signed and published by the owner ([MAINTENANCE.md](MAINTENANCE.md)) |

## The I.K.E. update channel

`data/update.json` (installed as `/usr/lib/ike-browser/update.json`) holds the
address of the channel and the Ed25519 public key that signs it. With either
field empty, self-updating is off.

```json
{ "url": "https://github.com/NullSector-2077/IKE-Browser/releases/latest/download",
  "pubkey": "<base64 Ed25519 public key>" }
```

The channel is the latest GitHub release of the repository. Each release has
these assets (fixed names, so `releases/latest/download/<name>` always points
to the newest release):

- `stable.json` — the manifest:
  `{"version": "1.0.1", "payload": "ike-1.0.1.tar.gz", "sha256": "<hex>", "min_system": "1.0.0"}`
- `stable.json.sig` — base64 Ed25519 signature of the exact bytes of `stable.json`
- `beta.json`, `beta.json.sig` — the same for the beta channel (for now a copy
  of stable, so users who chose "beta" are not left without updates)
- the payload `ike-<version>.tar.gz` — the `ike/` folder of the new version,
  with the AdBlock engine module built for the release in `ike/_engine/adblock/`
  (1.1.12): I.K.E. uses that engine first and the installed one as the
  fallback, so a new engine reaches every user without a new package
- the package `ike-browser-<version>-1-x86_64.pkg.tar.zst`, for installing by hand

I.K.E. checks the signature, then the hash, unpacks the new version in the
user's data folder (`~/.local/share/ike-browser/updates`), runs a self-test, and
uses it from the next start. A version that fails to start is rolled back
automatically and never installed again. Nothing under `/usr` is touched.

`min_system` is `__min_system__` from `ike/__init__.py`: the oldest installed
system part (`ike_boot.py`, the launcher, the desktop entry and its icons) the
new `ike/` folder goes with. The project's rule is that every release reaches
every user by itself (ROADMAP.md): raise it only when a release cannot work
without a new system part. The AdBlock engine is not such a part since 1.1.12.
An installation older than that is not self-updated: it shows once "I.K.E. X is
available, but it needs a newer installation package".

Pre-releases and drafts are not "latest" on GitHub, so they are never offered.

## Expiry, staged release and stopping a release (1.1.18)

Every manifest signed by `tools/make-release.py` carries `issued`, `expires`
(180 days later) and `rollout` (`start` and `hours`, 24 by default). The
updater (`ike/updater.py`, `manifest_problem`):

- installs nothing from an **expired** manifest and says so ("the update
  information is out of date"): a copy kept back after its time cannot hold
  users on an old release unnoticed. The next release's manifest is valid
  again, so this never blocks updates for good;
- gives each installation a fixed **place** from 0 to 99 (kept in
  `updates/state.json`): place N installs once N % of the rollout window has
  passed, so a release reaches everybody within 24 hours, a few first.
  "Check for updates" asked by the user does not wait. A clock that is days
  behind does not wait either;
- installs nothing from a manifest with **`"halt": true`**.

To publish a security fix to everybody at once:
`python3 tools/publish.py --urgente`. To stop a release that went wrong,
sign a halt manifest of the same version and upload it over the release's
own (the package and the payload stay as they are):

```
python3 tools/make-release.py --halt --out /tmp/halt
gh release upload v<version> /tmp/halt/stable.json /tmp/halt/stable.json.sig /tmp/halt/beta.json /tmp/halt/beta.json.sig --clobber
```

Installations that already took it keep it (the rollback of a copy that does
not start still works); the others wait for the next release. Manifests of
releases before 1.1.18 have none of these fields and are taken as before.
Downgrades were already refused (only a newer version than the running or
staged one is installed), and every payload is checked against the signed
SHA-256 before it is unpacked.

## The signing key

Generated once by the owner, on the owner's computer (fish shell):

```fish
mkdir -p ~/.ike-signing; chmod 700 ~/.ike-signing
openssl genpkey -algorithm ed25519 -aes-256-cbc -out ~/.ike-signing/ike-update.key
chmod 600 ~/.ike-signing/ike-update.key
openssl pkey -in ~/.ike-signing/ike-update.key -pubout -outform DER | tail -c 32 | base64
```

The last line prints the public key that goes into `data/update.json`. Keep a
copy of the key file and of its passphrase off the computer (a USB stick and a
password manager). Losing it means installed copies can no longer be updated
automatically; if it leaks, anyone can sign updates — in both cases make a new
key, put the new public key in a release, and tell users to install that release
by hand.

**Never put the private key in the repository, in a package or on GitHub
Actions.** `.gitignore` excludes `*.key` and `*.pem`, `tools/make-release.py`
refuses a key stored inside the repository, and a test fails if a private key is
committed.

## Publishing a release

On the owner's computer, from a clone of the repository, once the pull request
that raised the version is merged into `main` and its tests have passed:

```fish
cd ~/IKE-Browser; git switch main; git pull
python3 tools/publish.py
```

`tools/publish.py` does everything and stops, changing nothing on GitHub, at
the first problem: it checks that the clone is `main` without local changes and
equal to GitHub's, that the version of `ike/__init__.py` and the PKGBUILD agree
and is not published yet, and that the automatic tests passed on that exact
commit; it builds the package (`makepkg -Csf`), signs the update files with
`tools/make-release.py` (which asks the passphrase), takes the release notes
from the version's section of CHANGELOG.md, creates the GitHub release with its
tag on that commit (the package with its real pkgrel, e.g. `-3`), and finally
reads the published files back from GitHub and checks signature, version and
hash. `python3 tools/publish.py --dry-run` does all of it except the release.

GitHub only builds and tests; the key never leaves the owner's computer.

By hand, step by step (what the command does):

```fish
makepkg -Csf
python3 tools/make-release.py
gh release create v<version> dist/release-<version>/* \
    ike-browser-<version>-<pkgrel>-x86_64.pkg.tar.zst \
    --title "I.K.E. <version>" --notes-file <notes>
```
