#!/bin/sh
# Installs, inside a container of the given distribution, what I.K.E. needs to
# run and to be tested with THAT distribution's own Python, Qt, PyQt and Qt
# WebEngine packages (never PyPI's), plus the build tools of the engine module.
# Used by .github/workflows/linux-distros.yml; runs as root.
#
#   tools/ci/distro-deps.sh arch|ubuntu|debian|fedora
set -eu
distro="$1"

case "$distro" in
arch)
    pacman -Syu --noconfirm --needed \
        python python-pyqt6 python-pyqt6-webengine qt6-webengine qt6-webchannel qt6-svg \
        python-cryptography python-jeepney python-pytest \
        base-devel rust git sudo \
        ffmpeg dbus glib2 noto-fonts ttf-dejavu libnotify xdg-utils
    ;;
ubuntu|debian)
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -q
    apt-get install -yq --no-install-recommends \
        python3 python3-pyqt6 python3-pyqt6.qtwebengine python3-pyqt6.qtsvg \
        python3-pyqt6.qtwebchannel \
        python3-cryptography python3-jeepney python3-pytest \
        qt6-image-formats-plugins qt6-svg-plugins \
        ca-certificates curl git gcc libc6-dev pkg-config \
        ffmpeg dbus libglib2.0-bin fonts-noto-core fonts-dejavu-core fontconfig \
        libnotify-bin xdg-utils xauth
    ;;
fedora)
    dnf -y -q install \
        python3 python3-pyqt6 python3-pyqt6-webengine qt6-qtwebengine qt6-qtsvg qt6-qtwebchannel \
        python3-cryptography python3-jeepney python3-pytest \
        ca-certificates curl git gcc \
        ffmpeg-free dbus-daemon dbus-tools glib2 google-noto-sans-fonts dejavu-sans-fonts fontconfig \
        libnotify xdg-utils
    ;;
*)
    echo "unknown distribution: $distro" >&2
    exit 2
    ;;
esac

# Rust for the engine module (build time only). Arch's own is current; the
# others may be older than the lock file needs, so rustup's stable is used.
if ! command -v cargo >/dev/null 2>&1; then
    curl -sSf https://sh.rustup.rs | sh -s -- -y -q --profile minimal
    echo "$HOME/.cargo/bin" >> "${GITHUB_PATH:-/dev/null}"
fi

# the font of a Plasma desktop: the layout tests measure text widths
mkdir -p "$HOME/.config/fontconfig"
cat > "$HOME/.config/fontconfig/fonts.conf" <<'EOF'
<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd"><fontconfig>
<alias binding="strong"><family>sans-serif</family><prefer><family>Noto Sans</family></prefer></alias>
</fontconfig>
EOF
fc-cache -f >/dev/null
fc-match sans-serif
