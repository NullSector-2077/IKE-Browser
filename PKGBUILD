# Maintainer: the I.K.E. project <https://github.com/NullSector-2077/IKE-Browser>
#
# Builds I.K.E. from this repository. Run `makepkg -si` from a clone; the
# sources are taken from the clone itself, so this also works while the
# repository is private.
pkgname=ike-browser
pkgver=1.1.5
pkgrel=1
pkgdesc="I.K.E. - Internet Kontrol Experience: private, independent web browser"
arch=('x86_64')
url="https://github.com/NullSector-2077/IKE-Browser"
license=('GPL-3.0-or-later')
depends=('python' 'python-pyqt6' 'python-pyqt6-webengine' 'qt6-webengine' 'qt6-webchannel'
         'qt6-svg' 'python-cryptography' 'python-jeepney' 'hicolor-icon-theme')
makedepends=('rust' 'gcc')
optdepends=('libnotify: desktop notifications'
            'noto-fonts-cjk: Chinese and Japanese interface text'
            'xdg-utils: set I.K.E. as the default browser'
            'plasma-integration: Plasma theme, colours and file dialogs'
            'chromium-widevine: system-wide Widevine instead of the copy I.K.E. downloads')
install=ike-browser.install
options=('!debug')
source=()
sha256sums=()

build() {
  cd "$startdir"
  cargo build --release --locked --manifest-path ike-adblock/Cargo.toml \
      --target-dir "$srcdir/target"
  gcc $CFLAGS $LDFLAGS -o "$srcdir/ike-browser-launcher" launcher/ike-browser.c
}

package() {
  cd "$startdir"
  local lib="$pkgdir/usr/lib/ike-browser"

  # the browser
  install -d "$lib"
  cp -r --no-preserve=ownership ike "$lib/"
  find "$lib" -name __pycache__ -type d -prune -exec rm -rf {} +
  install -Dm644 ike_boot.py "$lib/ike_boot.py"
  install -Dm644 data/update.json "$lib/update.json"
  install -Dm644 -t "$lib/vendor/adblock" vendor/adblock/__init__.py \
      vendor/adblock/adblock.pyi vendor/adblock/py.typed
  install -Dm755 "$srcdir/target/release/libike_adblock.so" \
      "$lib/vendor/adblock/ike_adblock.abi3.so"
  install -Dm755 "$srcdir/ike-browser-launcher" "$pkgdir/usr/bin/ike-browser"

  # desktop integration
  install -Dm644 data/ike-browser.desktop "$pkgdir/usr/share/applications/ike-browser.desktop"
  local size
  for size in 48 64 128 256 512; do
    install -Dm644 "data/icons/ike-browser-$size.png" \
        "$pkgdir/usr/share/icons/hicolor/${size}x${size}/apps/ike-browser.png"
  done
  install -Dm644 data/icons/ike-browser.svg \
      "$pkgdir/usr/share/icons/hicolor/scalable/apps/ike-browser.svg"
  install -Dm644 data/icons/ike-browser-256.png "$pkgdir/usr/share/pixmaps/ike-browser.png"

  # licences and documentation
  install -Dm644 LICENSE "$pkgdir/usr/share/licenses/$pkgname/LICENSE"
  install -Dm644 -t "$pkgdir/usr/share/licenses/$pkgname" licenses/* docs/THIRD-PARTY.md
  install -Dm644 -t "$pkgdir/usr/share/doc/$pkgname" README.md CHANGELOG.md docs/*.md
}
