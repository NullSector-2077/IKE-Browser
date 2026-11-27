#!/bin/sh
# The big-site check of the I.K.E. Dark Engine experiment, one command on the
# owner's Arch Linux PC (read-only: a private profile that keeps nothing, plain
# page loads, no login, nothing typed or sent). The one command (it downloads
# the experiment's branch into ~/.cache/ike-dark-check, or updates it, then runs):
#
#   sh -c 'd=~/.cache/ike-dark-check; git -C "$d" pull -q --ff-only 2>/dev/null || { rm -rf "$d"; git clone -q --depth 1 -b experiment/ike-dark-engine https://github.com/NullSector-2077/IKE-Browser.git "$d"; } && sh "$d/tests/dark_engine/owner-check.sh"'
#
# Result: ~/ike-dark-check-<date>/ (side-by-side pictures in sheets/: without
# dark mode, Dark Reader, I.K.E. Dark Engine; the verdicts in metrics.txt, load
# times in times.txt). Options: see owner_check.py (--sites wikipedia,github,...;
# --url ADDRESS for any other page, repeatable, kept on this computer only;
# another folder as argument).
here=$(cd "$(dirname "$0")" && pwd)
missing=""
command -v git >/dev/null 2>&1 || missing="$missing git"
python3 -c "import PyQt6.QtWebEngineWidgets" 2>/dev/null || missing="$missing python-pyqt6 python-pyqt6-webengine"
python3 -c "import numpy" 2>/dev/null || missing="$missing python-numpy"
python3 -c "import PIL" 2>/dev/null || missing="$missing python-pillow"
if [ -n "$missing" ]; then
    echo "Missing:$missing"
    echo "Install them with:  sudo pacman -S --needed$missing"
    echo "then run the same command again."
    exit 1
fi
exec python3 "$here/owner_check.py" "$@"
