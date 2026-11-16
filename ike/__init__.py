"""I.K.E. - Internet Control Experience."""

import os

__version__ = "1.6.1"
# Oldest installed system part (ike_boot.py, AdBlock engine module, launcher,
# AppImage runtime) this ike/ folder works with. Raise it when a release needs
# a new system part: older installations are then told to update the package
# instead of receiving a self-update (see docs/UPDATES.md).
__min_system__ = "1.4.0"
APP_NAME = "I.K.E."
APP_LONG_NAME = "I.K.E. - Internet Control Experience"
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
                os.environ["ICE_PROFILE"] = name
            return
