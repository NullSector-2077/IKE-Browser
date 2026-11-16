#!/bin/sh
# Installs a built I.K.E. under DESTDIR with the same layout as the Arch
# package (PKGBUILD, package()): the browser in /usr/lib/ike-browser, the
# launcher in /usr/bin, desktop entry, icons, licences and documentation.
# Used by the DEB (packaging/debian/rules) and RPM (packaging/rpm/*.spec)
# builds; run from the repository root.
#
#   tools/install-linux.sh DESTDIR ENGINE_MODULE LAUNCHER LICENSEDIR DOCDIR
#
# ENGINE_MODULE: the built libike_adblock.so; LAUNCHER: the built launcher;
# LICENSEDIR / DOCDIR: where the distribution keeps licences and documents
# (for example /usr/share/doc/ike-browser on Debian, /usr/share/licenses/
# ike-browser on Fedora).
set -eu
dest="$1"
engine="$2"
launcher="$3"
licdir="$4"
docdir="$5"
lib="$dest/usr/lib/ike-browser"

# the browser
install -d "$lib"
cp -r ike "$lib/"
find "$lib" -name __pycache__ -type d -prune -exec rm -rf {} +
install -Dm644 ike_boot.py "$lib/ike_boot.py"
install -Dm644 data/update.json "$lib/update.json"
install -d "$lib/vendor/adblock"
install -m644 vendor/adblock/__init__.py vendor/adblock/adblock.pyi vendor/adblock/py.typed "$lib/vendor/adblock/"
install -Dm755 "$engine" "$lib/vendor/adblock/ike_adblock.abi3.so"
install -Dm755 "$launcher" "$dest/usr/bin/ike-browser"

# desktop integration
install -Dm644 data/ike-browser.desktop "$dest/usr/share/applications/ike-browser.desktop"
for size in 48 64 128 256 512; do
    install -Dm644 "data/icons/ike-browser-$size.png" \
        "$dest/usr/share/icons/hicolor/${size}x${size}/apps/ike-browser.png"
done
install -Dm644 data/icons/ike-browser.svg "$dest/usr/share/icons/hicolor/scalable/apps/ike-browser.svg"
install -Dm644 data/icons/ike-browser-256.png "$dest/usr/share/pixmaps/ike-browser.png"

# licences and documentation
install -d "$dest$licdir" "$dest$docdir"
install -m644 LICENSE licenses/* docs/THIRD-PARTY.md "$dest$licdir/"
install -m644 README.md CHANGELOG.md docs/*.md "$dest$docdir/"
