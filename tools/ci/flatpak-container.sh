#!/bin/bash
# Prepares Flathub's flatpak-github-actions container for a build
# (.github/workflows/flatpak.yml and flatpak-engine.yml).
set -euo pipefail
df -h "$PWD"
echo "processors: $(nproc)"
free -g || true
flatpak --version
flatpak-builder --version
# The run times come preinstalled in the image's own layer, where ostree
# cannot rename across the overlay ("Invalid cross-device link" when
# flatpak-builder updates them): copied into the container's writable layer.
if [ ! -e /var/lib/flatpak/.ike-copied ]; then
    mv /var/lib/flatpak /var/lib/flatpak.image
    cp -a /var/lib/flatpak.image /var/lib/flatpak
    rm -rf /var/lib/flatpak.image
    touch /var/lib/flatpak/.ike-copied
fi
mkdir -p -m 700 "${XDG_RUNTIME_DIR:-/tmp/xdg-runtime}"
mkdir -p out
