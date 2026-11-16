"""What websites stored on this computer besides cookies: local storage,
databases, service workers and the like.

Qt WebEngine can delete cookies and the cache while it runs, but it has no
call for the rest, and the folders cannot be taken away under the running
engine. So "Clear browsing data" notes the wish, and the folders are removed
when I.K.E. starts next, before the engine opens them; when I.K.E. closes
with "clear when closed" they are also removed right then, as far as the
closing engine lets go of them.
"""

import shutil
from pathlib import Path

from .config import DATA_DIR

# what the engine keeps for sites inside a profile folder (cookies, cache and
# history have their own calls; passwords and settings are not in there)
SITE_DATA = (
    "Local Storage", "Session Storage", "IndexedDB", "Service Worker", "WebStorage", "File System",
    "databases", "blob_storage", "Storage", "SharedStorage", "SharedStorage-wal", "Shared Dictionary",
    "shared_proto_db", "QuotaManager", "QuotaManager-journal", "Trust Tokens", "Trust Tokens-journal",
    "Network Persistent State", "TransportSecurity", "Reporting and NEL", "Reporting and NEL-journal",
    "DIPS", "DIPS-journal", "DIPS-wal", "PrivateAggregation", "PrivateAggregation-journal",
    "InterestGroups", "InterestGroups-wal", "Conversions", "Conversions-journal", "BudgetDatabase",
    "BudgetDatabase-journal", "BrowsingTopicsSiteData", "BrowsingTopicsSiteData-journal",
    "BrowsingTopicsState", "Cookies", "Cookies-journal",
)
MARK = "clear-site-data"


def profile_folders(data_dir=None):
    """The engine's folders: the main profile and one for each container."""
    data = Path(data_dir or DATA_DIR)
    found = [data / "profile"]
    try:
        found += sorted(p for p in (data / "containers").iterdir() if p.is_dir() and not p.is_symlink())
    except OSError:
        pass
    return found


def ask(data_dir=None):
    """Note that the site data is to be removed at the next start."""
    data = Path(data_dir or DATA_DIR)
    try:
        data.mkdir(parents=True, exist_ok=True)
        (data / MARK).write_text("1", "utf-8")
    except OSError:
        pass


def asked(data_dir=None):
    return (Path(data_dir or DATA_DIR) / MARK).exists()


def remove(data_dir=None):
    """Delete the site data of every profile folder. Returns how many entries went."""
    gone = 0
    for folder in profile_folders(data_dir):
        for name in SITE_DATA:
            target = folder / name
            try:
                if target.is_symlink() or target.is_file():
                    target.unlink()             # a link is removed, never followed
                elif target.is_dir():
                    shutil.rmtree(target)
                else:
                    continue
                gone += 1
            except OSError:
                pass
    return gone


def at_start(data_dir=None):
    """Before the engine starts: do what was asked for in the last session."""
    data = Path(data_dir or DATA_DIR)
    if not (data / MARK).exists():
        return False
    remove(data)
    try:
        (data / MARK).unlink()
    except OSError:
        pass
    return True
