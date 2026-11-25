"""tools/check-components.py reads the copy of I.K.E. it is given, even when
another copy was imported before in the same process (the installed-package
shard: a test before it had imported the checkout), and leaves the process as
it found it."""

import importlib.util
import shutil
import sys

from conftest import ROOT


def load():
    spec = importlib.util.spec_from_file_location("check_components_import", ROOT / "tools/check-components.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_check_reads_the_copy_it_is_given(tmp_path):
    other = tmp_path / "app"
    shutil.copytree(ROOT / "ike", other / "ike", ignore=shutil.ignore_patterns("__pycache__", "resources"))
    (other / "ike/resources").mkdir()
    check = load()
    before = {k: v for k, v in sys.modules.items() if k == "ike" or k.startswith("ike.")}
    first, _ = check.ike_modules(ROOT)                          # one copy imported first
    assert first.__file__.startswith(str(ROOT)), first.__file__
    current = sys.modules.get("ike.config")                      # whatever this process holds now
    config, scriptlets = check.ike_modules(other)                # then another asked for
    assert config.__file__.startswith(str(other.resolve())), config.__file__
    assert scriptlets.__file__.startswith(str(other.resolve())), scriptlets.__file__
    assert sys.modules.get("ike.config") is current              # the process is left as it was
    again, _ = check.ike_modules(ROOT)
    assert again.__file__.startswith(str(ROOT)), again.__file__
    for k in [k for k in sys.modules if (k == "ike" or k.startswith("ike.")) and k not in before]:
        del sys.modules[k]
    sys.modules.update(before)
