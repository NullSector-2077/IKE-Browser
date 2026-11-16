# Updates

| What | How it updates |
|---|---|
| Filter lists | daily, by I.K.E. (Settings → Components) |
| Chrome version presented to sites | daily check of Google's public version list; estimated from the calendar when offline |
| User scripts | daily, from their update address |
| Web engine (Qt WebEngine) | with the system (`sudo pacman -Syu`) |
| I.K.E. itself | signed update channel on GitHub Releases, described below |
| Components inside I.K.E. (AdBlock engine, uBlock Origin scriptlets) | checked daily and prepared as a tested candidate by GitHub Actions on a separate branch; the owner reviews and approves before merge and signing ([MAINTENANCE.md](MAINTENANCE.md)) |

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
- the payload `ike-<version>.tar.gz` — only the `ike/` folder of the new version
- the package `ike-browser-<version>-1-x86_64.pkg.tar.zst`, for installing by hand

I.K.E. checks the signature, then the hash, unpacks the new version in the
user's data folder (`~/.local/share/ike-browser/updates`), runs a self-test, and
uses it from the next start. A version that fails to start is rolled back
automatically and never installed again. Nothing under `/usr` is touched.

`min_system` is `__min_system__` from `ike/__init__.py`: the oldest installed
system part (`ike_boot.py`, the AdBlock engine module, the launcher) the new
`ike/` folder works with. Raise it when a release changes one of those parts.
An installation older than that is not self-updated: it shows once "I.K.E. X is
available, but it needs a newer installation package".

Pre-releases and drafts are not "latest" on GitHub, so they are never offered.
Other users can download updates only while the repository is public.

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

On the owner's computer, from a clone at the commit to release (the version in
`ike/__init__.py` and the PKGBUILD already raised and merged into `main`):

```fish
cd ~/IKE-Browser; git switch main; git pull
makepkg -Csf
python3 tools/make-release.py
```

`makepkg` builds `ike-browser-<version>-1-x86_64.pkg.tar.zst`. The release tool
asks the passphrase, writes `dist/release-<version>/` (payload, manifests,
signatures) and checks each signature with the public key of
`data/update.json`. Then publish everything as a normal release (not a draft,
not a pre-release):

```fish
gh release create v<version> dist/release-<version>/* \
    ike-browser-<version>-1-x86_64.pkg.tar.zst \
    --title "I.K.E. <version>" --notes "See CHANGELOG.md"
```

GitHub only builds and tests; the key never leaves the owner's computer.

Without `gh`: GitHub → Releases → Draft a new release → create the matching
`v<version>` tag → attach the same files → Publish release.
