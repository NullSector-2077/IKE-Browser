"""One-time import from the browser I.K.E. replaces (ike/legacy.py)."""

import base64
import json
import os
import shutil

import pytest
from conftest import write_profile

from ike import legacy


@pytest.fixture
def home(tmp_path, monkeypatch):
    h = tmp_path / "home"
    for var, sub in (("XDG_CONFIG_HOME", ".config"), ("XDG_DATA_HOME", ".local/share"),
                     ("XDG_CACHE_HOME", ".cache")):
        monkeypatch.setenv(var, str(h / sub))
    return h


def old_profile(h):
    cfg, data, cache = (h / ".config/ice-browser", h / ".local/share/ice-browser",
                        h / ".cache/ice-browser")
    for d in (cfg, data / "profile", data / "updates/versions/1.6.1", cache / "web",
              data / "profiles/work"):
        d.mkdir(parents=True, exist_ok=True)
    (cfg / "settings.json").write_text(json.dumps({
        "homepage": "ice:newtab", "session": [["https://example.org", "ice:newtab"]],
        "icon_theme": "set:ice", "ui_scheme": "theme:ice", "default_engine": "DuckDuckGo",
        "notes": "advice, device and slice stay as they are"}), "utf-8")
    (data / "ice.sqlite").write_bytes(b"bookmarks")
    (data / "profiles/work/ice.sqlite").write_bytes(b"work bookmarks")
    (data / "profile/Cookies").write_bytes(b"cookies")
    (data / "vault.bin").write_text("{}", "utf-8")
    return cfg, data, cache


def test_import_and_clean_up(home):
    old_cfg, old_data, old_cache = old_profile(home)
    new_cfg, new_data = home / ".config/ike-browser", home / ".local/share/ike-browser"
    new_data.mkdir(parents=True)                 # an empty folder made by an earlier start counts as fresh
    assert legacy.import_once()
    settings = json.loads((new_cfg / "settings.json").read_text("utf-8"))
    assert settings["homepage"] == "ike:newtab"
    assert settings["session"] == [["https://example.org", "ike:newtab"]]
    assert (settings["icon_theme"], settings["ui_scheme"]) == ("set:ike", "theme:ike")
    assert settings["notes"] == "advice, device and slice stay as they are"
    assert (new_data / "ike.sqlite").read_bytes() == b"bookmarks"
    assert (new_data / "profiles/work/ike.sqlite").read_bytes() == b"work bookmarks"
    assert not (new_data / "ice.sqlite").exists()
    assert (new_data / "profile/Cookies").read_bytes() == b"cookies"
    assert (new_data / "vault.bin").exists()
    assert not (new_data / "updates").exists()   # the old program's self-updates are not taken
    assert not any(p.name.startswith(".ike-browser-import-") for p in new_data.parent.iterdir())
    # nothing of the old browser is deleted yet, and the import runs only once
    assert old_cfg.is_dir() and old_data.is_dir() and old_cache.is_dir()
    assert not legacy.import_once()
    # after a correct start the old folders go
    assert legacy.clean_up()
    assert not old_cfg.exists() and not old_data.exists() and not old_cache.exists()
    assert (new_cfg / "settings.json").exists() and (new_data / "ike.sqlite").exists()
    assert not legacy.clean_up()


def test_nothing_to_import(home):
    assert not legacy.import_once()
    assert not legacy.clean_up()
    assert not (home / ".config/ike-browser").exists()


def test_existing_profile_is_left_alone(home):
    old_cfg, old_data, _ = old_profile(home)
    write_profile(home / ".config/ike-browser", home / ".local/share/ike-browser", {"homepage": "https://mine"})
    assert not legacy.import_once()
    settings = json.loads((home / ".config/ike-browser/settings.json").read_text("utf-8"))
    assert settings["homepage"] == "https://mine"
    assert not legacy.clean_up()
    assert old_cfg.is_dir() and old_data.is_dir()


def test_failed_copy_keeps_both_sides(home, monkeypatch):
    old_cfg, old_data, _ = old_profile(home)

    def broken(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(shutil, "copytree", broken)
    assert not legacy.import_once()
    assert not (home / ".config/ike-browser/settings.json").exists()
    assert not (home / ".config/ike-browser" / legacy.MARKER).exists()
    assert (old_cfg / "settings.json").exists() and (old_data / "ice.sqlite").exists()


def test_old_password_vault_opens_and_is_sealed_again(tmp_path):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    from ike import passwords
    vault = passwords.Vault(tmp_path / "vault.bin")
    vault.create("master")
    vault.entries = [{"origin": "https://example.org", "user": "me", "password": "secret"}]
    vault.save()
    # the same file as the old browser wrote it
    blob = json.loads(vault.path.read_text("utf-8"))
    key = vault._derive("master", base64.b64decode(blob["salt"]))
    nonce = os.urandom(12)
    data = AESGCM(key).encrypt(nonce, json.dumps(vault.entries).encode(), legacy.LEGACY_VAULT_AAD)
    blob.update(nonce=base64.b64encode(nonce).decode(), data=base64.b64encode(data).decode())
    vault.path.write_text(json.dumps(blob), "utf-8")
    old = passwords.Vault(vault.path)
    assert not old.unlock("wrong")
    assert old.unlock("master") and old.entries[0]["password"] == "secret"
    blob = json.loads(vault.path.read_text("utf-8"))
    key = vault._derive("master", base64.b64decode(blob["salt"]))
    plain = AESGCM(key).decrypt(base64.b64decode(blob["nonce"]), base64.b64decode(blob["data"]), b"ike-vault-1")
    assert json.loads(plain)[0]["user"] == "me"


def test_browser_imports_the_old_profile(run_ike, tmp_path):
    """The first start of I.K.E. finds the old browser's bookmarks and settings;
    the old folders are removed only after the start was confirmed healthy."""
    home = tmp_path / "home"
    run_ike("""
        def steps(ike, qapp, out):
            ike.storage.add_bookmark("https://example.org/", "Example")
            yield 100
    """, settings={"startup": "home"})
    # make that profile look like the old browser's
    old_cfg, old_data = home / ".config/ice-browser", home / ".local/share/ice-browser"
    (home / ".config/ike-browser").rename(old_cfg)
    (home / ".local/share/ike-browser").rename(old_data)
    (old_data / "ike.sqlite").rename(old_data / "ice.sqlite")
    settings = json.loads((old_cfg / "settings.json").read_text("utf-8"))
    settings.update(homepage="ice:newtab", ui_scheme="theme:ice")
    (old_cfg / "settings.json").write_text(json.dumps(settings), "utf-8")
    out = run_ike("""
        from ike import legacy

        def steps(ike, qapp, out):
            out["bookmarks"] = [b[0] for b in ike.storage.bookmarks()]
            out["homepage"] = ike.config["homepage"]
            out["scheme"] = ike.config["ui_scheme"]
            out["tab"] = ike.windows[0].current_view().url().toString()
            out["cleaned"] = legacy.clean_up()
            yield 100
    """, prepare=False)
    assert out["bookmarks"] == ["https://example.org/"]
    assert (out["homepage"], out["scheme"]) == ("ike:newtab", "theme:ike")
    assert out["tab"].startswith("ike:")
    assert out["cleaned"] and not old_cfg.exists() and not old_data.exists()
