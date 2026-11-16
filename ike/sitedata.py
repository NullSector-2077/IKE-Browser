"""What websites stored on this computer besides cookies: local storage,
databases, service workers and the like.

Qt WebEngine can delete cookies and the cache while it runs, but it has no
call for the rest, and the folders cannot be taken away under the running
engine. So "Clear browsing data" notes the wish, and the folders are removed
when I.K.E. starts next, before the engine opens them; when I.K.E. closes
with "clear when closed" they are also removed right then, as far as the
closing engine lets go of them.

On Windows the closing engine lets go of nothing: a file that is open cannot
be deleted there. So I.K.E. leaves a small helper behind when it closes
(finish_later): it waits until the browser has ended and removes what is
left (finish_after) - unless another I.K.E. has started meanwhile, which
clears by itself before its engine opens the data.
"""

import shutil
import time
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


def left(data_dir=None):
    """Is any site data still on the disk?"""
    return any((folder / name).exists() or (folder / name).is_symlink()
               for folder in profile_folders(data_dir) for name in SITE_DATA)


FINISH = "--finish-clearing"         # ike_boot.py passes it here without starting the browser


def finish_later(command):
    """Windows, when I.K.E. closes with "clear when closed": start the helper
    that finishes the removal once this process has ended. `command` is what
    starts I.K.E. (updater.boot_command())."""
    import os
    import subprocess
    env = dict(os.environ)
    env.pop("IKE_TEST_HOOK", None)
    try:
        subprocess.Popen(list(command) + [FINISH, str(os.getpid())], env=env, stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return True
    except (OSError, ValueError):
        return False                 # the data goes at the next start, as noted


def finish_after(pid, data_dir=None, tries=40, pause=0.25, wait_for_exit=None, running=None):
    """The helper's work: wait for the browser that started it to end, then
    remove what it could not. The note for the next start stays, so the next
    start clears once more. (wait_for_exit and running are Windows' own
    answers; the automatic tests pass stand-ins.)"""
    if wait_for_exit is None or running is None:
        from . import winapi
        wait_for_exit = wait_for_exit or winapi.wait_for_exit
        running = running or winapi.is_running
    if not str(pid).isdigit() or not asked(data_dir):
        return 0                     # not started by a closing I.K.E.: nothing to do
    wait_for_exit(int(pid), 30)
    for _ in range(tries):
        if running():
            return 0                 # a new I.K.E. is using the folders: hands off
        remove(data_dir)
        if not left(data_dir):
            break
        time.sleep(pause)            # the engine's own helper processes end a moment later
    return 0


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
