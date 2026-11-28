"""Dark Reader for the comparisons of tests/dark_engine/ (mode "dr"), since 1.1.30
when it left I.K.E.: its loader (ike/darkpages.py) and its files are taken from
a checkout of I.K.E. 1.1.28 or older, given in DE_DR_ROOT, e.g.

    git worktree add /tmp/ike-1.1.28 v1.1.28
    DE_DR_ROOT=/tmp/ike-1.1.28 python3 tests/dark_engine/render.py OUT --modes off,dr,proto

Nothing of it is part of I.K.E. or of its automatic tests.
"""

import importlib.util
import os
import sys
from pathlib import Path


def darkpages():
    """The module darkpages of that checkout, its files read from there."""
    try:
        from ike import darkpages as here  # an I.K.E. that still has it
        return here
    except ImportError:
        pass
    root = os.environ.get("DE_DR_ROOT")
    if not root or not (Path(root) / "ike" / "darkpages.py").is_file():
        sys.exit("Dark Reader is no longer part of I.K.E. (1.1.30): set DE_DR_ROOT to a checkout "
                 "of I.K.E. 1.1.28 to compare with it")
    spec = importlib.util.spec_from_file_location("ike.darkpages", Path(root) / "ike" / "darkpages.py",
                                                  submodule_search_locations=None)
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = "ike"
    sys.modules["ike.darkpages"] = mod
    spec.loader.exec_module(mod)
    mod.RES_DIR = Path(root) / "ike" / "resources"      # its darkreader.js, proxy and darkmode.js (DE_DR_ROOT)
    return mod
