# Updates on Arch Linux / CachyOS

I.K.E. has two separate update mechanisms:

- **The browser application:** I.K.E. checks the signed GitHub Releases channel. It downloads only the application Python package (ike/), verifies the Ed25519 signature and SHA-256 digest, runs a self-test, and rolls back automatically if startup fails. It never writes under /usr.
- **The system and Qt WebEngine:** these remain managed by Arch Linux. Update them with sudo pacman -Syu; I.K.E. does not download or replace system Qt libraries.

The release channel is configured in data/update.json. Its URL points to the latest release of this repository and its public key verifies the signed stable.json / beta.json manifests. An empty URL or public key disables self-updating.

## Release assets

An Arch/CachyOS release contains:

- stable.json and stable.json.sig
- beta.json and beta.json.sig
- ike-<version>.tar.gz, containing only the ike/ application code
- ike-browser-<version>-1-x86_64.pkg.tar.zst, built locally with makepkg

No AppImage or Windows installers/update archives are produced by this repository.

The manifest's min_system value comes from __min_system__ in ike/__init__.py. Raise it when the new application code requires a newer installed bootstrap, AdBlock module, or launcher. Older packages must be upgraded with pacman before receiving that application update.

## Signing key

Reuse the existing Ed25519 private key that matches the public key in data/update.json. The original ICE update channel used ~/.ice-signing/ice-update.key; keep using that same key to preserve update continuity. It stays on the owner's computer and outside the repository:

    mkdir -p ~/.ice-signing; chmod 700 ~/.ice-signing
    openssl genpkey -algorithm ed25519 -aes-256-cbc -out ~/.ice-signing/ice-update.key
    chmod 600 ~/.ice-signing/ice-update.key
    openssl pkey -in ~/.ice-signing/ice-update.key -pubout -outform DER | tail -c 32 | base64

The final command prints the public key placed in data/update.json. Never commit or upload the private key. Losing it prevents future automatic updates for existing installations; if it is exposed, generate a replacement key and publish a package update containing the new public key.

## Preparing a release

From the reviewed commit on the owner's Arch/CachyOS computer:

    git switch main
    git pull
    makepkg -Csf
    python3 tools/make-release.py --channels stable,beta

Check that the package and both signed manifests were created successfully. Publish only the signed channel files and the Arch package:

    gh release create v<version> dist/release-<version>/* ike-browser-<version>-1-x86_64.pkg.tar.zst \
      --title "I.K.E. <version>" --notes "Arch Linux / CachyOS release."

Do not create a draft or pre-release: installed copies check the latest published release.
