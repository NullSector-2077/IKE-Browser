"""I.K.E. - Internet Kontrol Experience."""

import os

__version__ = "1.1.26"
# Oldest installed system part (ike_boot.py, launcher, desktop icons) this ike/
# folder goes with. Raise it only when a release cannot work without a new
# system part: older installations are then told to update the package instead
# of receiving a self-update (see docs/UPDATES.md). Rule of the project: every
# release reaches every user by itself, so this stays as low as possible.
# 1.0.1: the icons installed under /usr/share/icons changed (new lettering).
# 1.1.12: back from 1.1.11 to 1.0.1: the AdBlock engine now travels inside the
# signed self-update (ike/_engine), it is no longer a reason to raise this.
__min_system__ = "1.0.1"
APP_NAME = "I.K.E."
APP_LONG_NAME = "I.K.E. - Internet Kontrol Experience"
APP_ID = "ike-browser"


def early_args(argv):
    """Read --profile before any module computes its data folders."""
    for i, a in enumerate(argv):
        if a == "--":
            return                        # addresses only after it (the menu's entry, review 4, N12)
        name = None
        if a == "--profile" and i + 1 < len(argv):
            name = argv[i + 1]
        elif a.startswith("--profile="):
            name = a.split("=", 1)[1]
        if name is not None:
            name = "".join(ch for ch in name if ch.isalnum() or ch in "-_")
            if name:
                os.environ["IKE_PROFILE"] = name
            return
