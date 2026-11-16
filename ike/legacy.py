"""One-time import from the browser I.K.E. replaces.

Before I.K.E. 1.0.0 the browser was installed as "ice-browser" and kept its
files in ~/.config/ice-browser and ~/.local/share/ice-browser. At the first
start of I.K.E. those folders are copied into I.K.E.'s own ones (the copy is
made beside them and renamed into place, so a half-made copy is never used),
and the few names that changed are adjusted. Nothing is deleted then: the old
folders are removed only after I.K.E. has run correctly once (clean_up(),
called together with the update health check).

This module is the only place that knows the old names; it can be removed in a
later version, once every installation has been imported.
"""

import json
import shutil
import tempfile
import time
from pathlib import Path

from . import osinfo

LEGACY_ID = "ice-browser"
LEGACY_SCHEME = "ice:"
LEGACY_VAULT_AAD = b"ice-vault-1"
# files and folders that are renamed inside the copied data folder
_DATA_RENAMES = (("ice.sqlite", "ike.sqlite"),)
# setting values that named the old browser
_VALUE_RENAMES = {"set:ice": "set:ike", "theme:ice": "theme:ike"}
# not copied: the old program's own self-updates, which I.K.E. cannot run
_SKIP = ("updates",)
MARKER = "legacy-import.json"


def _legacy(kind):
    return osinfo.app_dir(kind).parent / LEGACY_ID


def _fresh(folder):
    """True when I.K.E. has nothing of its own in this folder yet."""
    if not folder.exists():
        return True
    return folder.is_dir() and all(p.name in _SKIP for p in folder.iterdir())


def _copy_into_place(legacy, target):
    stage_root = tempfile.mkdtemp(prefix=".%s-import-" % osinfo.APP_ID, dir=str(target.parent))
    stage = Path(stage_root) / "copy"
    try:
        shutil.copytree(legacy, stage, symlinks=True, ignore=shutil.ignore_patterns(*_SKIP))
        if target.exists():
            for p in target.iterdir():          # only what _fresh() allows: moved over
                p.replace(stage / p.name)
            target.rmdir()
        stage.replace(target)
    finally:
        shutil.rmtree(stage_root, ignore_errors=True)


def _rename_value(value):
    if isinstance(value, str):
        if value.startswith(LEGACY_SCHEME):
            return "ike:" + value[len(LEGACY_SCHEME):]
        return _VALUE_RENAMES.get(value, value)
    if isinstance(value, list):
        return [_rename_value(v) for v in value]
    if isinstance(value, dict):
        return {k: _rename_value(v) for k, v in value.items()}
    return value


def _adjust(config_dir, data_dir):
    for settings in config_dir.rglob("settings.json"):
        try:
            data = json.loads(settings.read_text("utf-8"))
        except (OSError, ValueError):
            continue
        new = _rename_value(data)
        if new != data:
            tmp = settings.with_suffix(".tmp")
            tmp.write_text(json.dumps(new, indent=1, ensure_ascii=False), "utf-8")
            tmp.replace(settings)
    for old, new in _DATA_RENAMES:
        for p in list(data_dir.rglob(old)):
            if not (p.parent / new).exists():
                p.replace(p.parent / new)


def import_once():
    """Copy the old browser's settings and data, if I.K.E. has none yet.
    Returns True when something was imported."""
    config, data = osinfo.app_dir("config"), osinfo.app_dir("data")
    if (config / MARKER).exists():
        return False
    old_config, old_data = _legacy("config"), _legacy("data")
    if not (old_config.is_dir() or old_data.is_dir()):
        return False
    if not (_fresh(config) and _fresh(data)):
        return False                          # I.K.E. is already in use: leave it alone
    try:
        for old, new in ((old_config, config), (old_data, data)):
            if old.is_dir():
                new.parent.mkdir(parents=True, exist_ok=True)
                _copy_into_place(old, new)
        _adjust(config, data)
    except OSError:
        return False                          # start empty; the old folders are untouched
    config.mkdir(parents=True, exist_ok=True)
    (config / MARKER).write_text(json.dumps({"imported": int(time.time()), "cleaned": False}), "utf-8")
    return True


def clean_up():
    """After a correct start following an import: remove the old folders."""
    marker = osinfo.app_dir("config") / MARKER
    try:
        state = json.loads(marker.read_text("utf-8"))
    except (OSError, ValueError):
        return False
    if state.get("cleaned"):
        return False
    for kind in ("config", "data", "cache"):
        old = _legacy(kind)
        if old.name == LEGACY_ID and old.is_dir() and not old.is_symlink():
            shutil.rmtree(old, ignore_errors=True)
    state["cleaned"] = int(time.time())
    marker.write_text(json.dumps(state), "utf-8")
    return True
