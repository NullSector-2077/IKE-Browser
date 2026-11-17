"""I.K.E. - Internet Kontrol Experience."""

import os

__version__ = "1.1.7"
# Oldest installed system part (ike_boot.py, AdBlock engine module, launcher,
# desktop icons) this ike/ folder goes with. Raise it when a release needs
# a new system part: older installations are then told to update the package
# instead of receiving a self-update (see docs/UPDATES.md).
# 1.0.1: the icons installed under /usr/share/icons changed (new lettering).
__min_system__ = "1.0.1"
APP_NAME = "I.K.E."
APP_LONG_NAME = "I.K.E. - Internet Kontrol Experience"
APP_ID = "ike-browser"


def early_args(argv):
    """Read --profile before any module computes its data folders."""
    for i, a in enumerate(argv):
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
