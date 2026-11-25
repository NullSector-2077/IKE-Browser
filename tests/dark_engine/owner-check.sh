#!/bin/sh
# The big-site check of the I.K.E. Dark Engine experiment, one command on the
# owner's Arch Linux PC (read-only: a private profile that keeps nothing, plain
# page loads, no login, nothing typed or sent). From a copy of the branch:
#
#   git clone --depth 1 -b experiment/ike-dark-engine https://github.com/NullSector-2077/IKE-Browser.git ~/ike-de-check && sh ~/ike-de-check/tests/dark_engine/owner-check.sh
#
# Result: ~/ike-dark-check-<date>/ (side-by-side pictures in sheets/, the
# verdicts in metrics.txt, load times in times.txt). Options: see
# owner_check.py (--sites wikipedia,github,...; another folder as argument).
here=$(cd "$(dirname "$0")" && pwd)
missing=""
python3 -c "import PyQt6.QtWebEngineWidgets" 2>/dev/null || missing="$missing python-pyqt6 python-pyqt6-webengine"
python3 -c "import numpy" 2>/dev/null || missing="$missing python-numpy"
python3 -c "import PIL" 2>/dev/null || missing="$missing python-pillow"
if [ -n "$missing" ]; then
    echo "Missing:$missing"
    echo "Install them with:  sudo pacman -S --needed$missing"
    exit 1
fi
exec python3 "$here/owner_check.py" "$@"
