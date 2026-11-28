# Maintainer: the I.K.E. project <https://github.com/NullSector-2077/IKE-Browser>
#
# Builds I.K.E. from this repository. Run `makepkg -si` from a clone; the
# sources are taken from the clone itself (no download).
pkgname=ike-browser
pkgver=1.1.32
pkgrel=1
pkgdesc="I.K.E. - Internet Kontrol Experience: private, independent web browser"
arch=('x86_64')
url="https://github.com/NullSector-2077/IKE-Browser"
license=('GPL-3.0-or-later')
depends=('python' 'python-pyqt6' 'python-pyqt6-webengine' 'qt6-webengine' 'qt6-webchannel'
         'qt6-svg' 'python-cryptography' 'python-jeepney' 'hicolor-icon-theme' 'publicsuffix-list')
makedepends=('rust' 'gcc')
optdepends=('noto-fonts-cjk: Chinese, Japanese and Korean interface text'
            'noto-fonts: Arabic, Hebrew, Indic, Thai, Georgian, Armenian and other scripts'
            'plasma-integration: Plasma theme, colours and file dialogs'
            'chromium-widevine: system-wide Widevine instead of the copy I.K.E. downloads'
            'libva-nvidia-driver: video decoding with NVIDIA graphics cards (Settings, experimental)'
            'intel-media-driver: video decoding with Intel graphics cards'
            'hunspell-en_us: spell checking in English (other languages: their hunspell-* package)'
            'hunspell-it: spell checking in Italian')
install=ike-browser.install
options=('!debug')
source=()
sha256sums=()

build() {
  cd "$startdir"
  # Every x86_64 processor, old ones too (an i5-3570K): the package and the
  # AdBlock engine carried by the self-update are built on the owner's
  # computer, whose makepkg.conf may target its own newer processor
  # (-march=native, x86-64-v3...); such code stops with "illegal
  # instruction" on an older one. The last option given wins.
  RUSTFLAGS="${RUSTFLAGS:-} -C target-cpu=x86-64" \
  cargo build --release --locked --manifest-path ike-adblock/Cargo.toml \
      --target-dir "$srcdir/target"
  gcc $CFLAGS -march=x86-64 -mtune=generic $LDFLAGS -o "$srcdir/ike-browser-launcher" launcher/ike-browser.c
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
  for size in 16 22 24 32 48 64 128 256 512 1024; do
    install -Dm644 "data/icons/ike-browser-$size.png" \
        "$pkgdir/usr/share/icons/hicolor/${size}x${size}/apps/ike-browser.png"
  done
  install -Dm644 data/icons/ike-browser.svg \
      "$pkgdir/usr/share/icons/hicolor/scalable/apps/ike-browser.svg"
  install -Dm644 data/icons/ike-browser-256.png "$pkgdir/usr/share/pixmaps/ike-browser.png"

  # licences: I.K.E.'s (the GPL v3 text and its notice), every shipped
  # component's, and the Rust libraries of the AdBlock engine (docs/THIRD-PARTY.md)
  install -Dm644 -t "$pkgdir/usr/share/licenses/$pkgname" LICENSE COPYRIGHT licenses/* docs/THIRD-PARTY.md
  # the Rust standard library inside the engine: the notice of the compiler that built it
  local rustdoc
  for rustdoc in "$(rustc --print sysroot)/share/doc/rust" /usr/share/doc/rust; do
    if [ -f "$rustdoc/COPYRIGHT-library.html" ]; then
      install -Dm644 "$rustdoc/COPYRIGHT-library.html" \
          "$pkgdir/usr/share/licenses/$pkgname/RUST-STD-COPYRIGHT.html"
      break
    fi
  done
  # Arch's own rust package has none (found by the weekly Arch check): the copy
  # kept in the repository (from Rust 1.97, tools/licence-texts/) is used then
  [ -f "$pkgdir/usr/share/licenses/$pkgname/RUST-STD-COPYRIGHT.html" ] ||
      install -Dm644 tools/licence-texts/RUST-STD-COPYRIGHT.html \
          "$pkgdir/usr/share/licenses/$pkgname/RUST-STD-COPYRIGHT.html"

  # documentation
  install -Dm644 -t "$pkgdir/usr/share/doc/$pkgname" README.md CHANGELOG.md docs/*.md
}
