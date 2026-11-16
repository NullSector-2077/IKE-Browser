# Updates

| What | How it updates |
|---|---|
| Filter lists | daily, by I.K.E. (Settings → Components) |
| Chrome version presented to sites | daily check of Google's public version list; estimated from the calendar when offline |
| User scripts | daily, from their update address |
| Web engine (Qt WebEngine) | Arch / CachyOS: with the system (`pacman -Syu`); AppImage and Windows: with I.K.E. itself |
| I.K.E. itself | signed update channel on GitHub Releases, described below |
| Components inside I.K.E. (AdBlock engine, uBlock Origin scriptlets, bundled Qt WebEngine and Python) | checked daily and prepared as a tested candidate by GitHub Actions on a separate branch; the owner reviews and approves before merge and signing ([MAINTENANCE.md](MAINTENANCE.md)) |

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
  `{"version": "1.4.1", "payload": "ice-1.4.1.tar.gz", "sha256": "<hex>", "min_system": "1.4.0"}`
- `stable.json.sig` — base64 Ed25519 signature of the exact bytes of `stable.json`
- `beta.json`, `beta.json.sig` — the same for the beta channel (for now a copy
  of stable, so users who chose "beta" are not left without updates)
- the payload `ice-<version>.tar.gz` — only the `ike/` folder of the new version
- the package and the AppImage, for people installing by hand
- `IKE-Browser-<version>-x64-setup.exe`, the Windows installer, and
  `IKE-Browser-<version>-windows-x64.zip`, the Windows program folder used by
  the updater (built by GitHub, see [BUILDING.md](BUILDING.md))

The manifest names the whole-program files with their size and SHA-256:
`"appimage": {"file": ..., "size": ..., "sha256": ...}` and
`"windows": {"file": ..., "size": ..., "sha256": ...}`.

I.K.E. checks the signature, then the hash, unpacks the new version in the
user's data folder (`~/.local/share/ike-browser/updates`), runs a self-test, and
uses it from the next start. A version that fails to start is rolled back
automatically and never installed again. Nothing under `/usr` is touched.

The AppImage and the Windows installation replace the whole program instead,
so Qt WebEngine and Python are updated too. On Windows I.K.E. downloads the
update archive, checks its size and hash against the signed manifest, unpacks
it into `app\<version>` next to the folder in use (refusing any file that
would land outside it, links, device names, duplicates and archives that grow
too large), starts it once to check it (self-test), and only then writes the
new version into the file `current` that the launcher reads. The folder in use
stays as `previous`; older ones are removed. Nothing needs administrator
rights. If the new version is started once and does not close cleanly or
confirm a healthy start, the next start goes back to `previous` by itself and
the version is never installed again. A release without the `windows` entry
is announced, not installed.

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
mkdir -p ~/.ice-signing; chmod 700 ~/.ice-signing
openssl genpkey -algorithm ed25519 -aes-256-cbc -out ~/.ice-signing/ice-update.key
chmod 600 ~/.ice-signing/ice-update.key
openssl pkey -in ~/.ice-signing/ice-update.key -pubout -outform DER | tail -c 32 | base64
```

The last line prints the public key that goes into `data/update.json`. Keep a
copy of the key file and of its passphrase off the computer (a USB stick and a
password manager). Losing it means installed copies can no longer be updated
automatically; if it leaks, anyone can sign updates — in both cases make a new
key, put the new public key in a release, and tell users to install that release
by hand.

**Never put the private key in the repository or in a package.**
`.gitignore` excludes `*.key` and `*.pem`, `tools/make-release.py` refuses a key
stored inside the repository, and a test fails if a private key is committed.

## Publishing a release

### Arch Linux / CachyOS only (1.6.1)

This release intentionally publishes only the Arch package. Do not download,
build or attach AppImage or Windows artifacts. The release still needs the
signed `stable.json` / `beta.json` manifests and `ice-<version>.tar.gz`
payload so the Arch installation can update its application code.

On the owner's CachyOS / Arch computer, from the updated clone:

```fish
cd ~/IKE-Browser
git switch main
git pull
makepkg -Csf
python3 tools/make-release.py --channels stable,beta
```

After checking that the package was created as
`ike-browser-1.6.1-1-x86_64.pkg.tar.zst` and that the release tool verified
both signatures, publish only the signed files and the Arch package:

```fish
gh release create v1.6.1 dist/release-1.6.1/* \
    ike-browser-1.6.1-1-x86_64.pkg.tar.zst \\
    --title "I.K.E. 1.6.1" --notes "Arch Linux / CachyOS release. See CHANGELOG.md."
```

Do not attach an AppImage, Windows installer or Windows update archive. Because
the signed manifest has neither an `appimage` nor a `windows` entry, existing
AppImage and Windows installations will be told that a platform package is
needed; they will not install the Arch-only update. Their current 1.6.0 builds
remain available from the preceding release.

### Full multi-platform release

On the owner's computer, from a clone at the commit to release (the version in
`ike/__init__.py` and the PKGBUILD already raised and merged into `main`):

```fish
cd ~/IKE-Browser; git switch main; git pull
gh run download <run-id> -n ice-windows        # the Windows files built by GitHub for this commit
python3 tools/make-release.py --appimage IKE-Browser-<version>-x86_64.AppImage \
    --windows IKE-Browser-<version>-windows-x64.zip
```

It asks the passphrase, writes `dist/release-<version>/` (payload, manifests,
signatures) and checks each signature with the public key of `data/update.json`;
it also checks that the Windows archive is this version's, complete, with the
project's update channel and key. Then publish everything as a normal release
(not a draft, not a pre-release):

```fish
gh release create v<version> dist/release-<version>/* \
    ike-browser-<version>-1-x86_64.pkg.tar.zst IKE-Browser-<version>-x86_64.AppImage \
    IKE-Browser-<version>-x64-setup.exe IKE-Browser-<version>-windows-x64.zip \
    --title "I.K.E. <version>" --notes "See CHANGELOG.md"
```

`<run-id>` is the run of the Windows workflow for the release commit on `main`
(`gh api "repos/NullSector-2077/IKE-Browser/actions/workflows/windows.yml/runs?branch=main" --jq '.workflow_runs[0].id'`).
GitHub only builds; the key never leaves the owner's computer.

Without `gh`: GitHub → Releases → Draft a new release → create the matching
`v<version>` tag → attach the same files → Publish release.
