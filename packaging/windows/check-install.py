#!/usr/bin/env python3
"""Checks around the Windows installer (used by .github/workflows/windows.yml).

    python check-install.py --tree DIR      the folder to install holds what it must, and
                                            nothing that must not be shipped
    python check-install.py --installed     after the silent install: files, Start-menu
                                            shortcut, uninstall entry - all in the user's
                                            own profile and registry branch
    python check-install.py --make-user-data   leave marks in the user's data folders
    python check-install.py --uninstalled   after the silent uninstall: program, shortcut
                                            and registry entries gone; the user's data
                                            (the marks) still there

Exit status 0 when everything is as it should be; each problem is printed.
"""

import argparse
import fnmatch
import importlib.util
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
APP_ID = "{6C1D3E0B-7F3A-4D5E-9B1C-1A2E5F7C9D42}_is1"          # AppId of ike-browser.iss
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall" + "\\" + APP_ID
REGISTERED = (r"Software\RegisteredApplications", "IKE Browser")
OWN_KEYS = (r"Software\Classes\IKEBrowserHTML", r"Software\Clients\StartMenuInternet\IKE Browser")
MARK = "kept-after-uninstall.txt"


def build_module():
    spec = importlib.util.spec_from_file_location("ike_windows_build", HERE / "build.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def app_dir():
    return Path(os.environ["LOCALAPPDATA"]) / "Programs" / "I.K.E"


def shortcut():
    return Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "I.K.E..lnk"


def user_data():
    return (Path(os.environ["APPDATA"]) / "ike-browser",
            Path(os.environ["LOCALAPPDATA"]) / "ike-browser" / "data")


def key_exists(root, path):
    import winreg
    try:
        winreg.CloseKey(winreg.OpenKey(root, path))
        return True
    except OSError:
        return False


def value(root, path, name):
    import winreg
    try:
        with winreg.OpenKey(root, path) as key:
            return winreg.QueryValueEx(key, name)[0]
    except OSError:
        return None


def check_tree(folder):
    build = build_module()
    folder = Path(folder)
    problems = ["missing: " + name for name in build.REQUIRED if not (folder / name).is_file()]
    for path in folder.rglob("*"):
        if path.is_file() and any(fnmatch.fnmatch(path.name.lower(), pattern) for pattern in build.FORBIDDEN):
            problems.append("must not be shipped: " + path.relative_to(folder).as_posix())
    files = [p for p in folder.rglob("*") if p.is_file()]
    print("%d files, %.1f MiB in %s" % (len(files), sum(p.stat().st_size for p in files) / 2 ** 20, folder))
    return problems


def check_installed():
    import winreg
    app = app_dir()
    problems = check_tree(app) if app.is_dir() else ["not installed: %s" % app]
    if not (app / "unins000.exe").is_file():
        problems.append("no uninstaller in %s" % app)
    if not shortcut().is_file():
        problems.append("no Start-menu shortcut: %s" % shortcut())
    where = value(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY, "InstallLocation")
    if not where or Path(where.rstrip("\\")) != app:
        problems.append("the uninstall entry of the user names %r, not %s" % (where, app))
    for root, name in ((winreg.HKEY_LOCAL_MACHINE, "HKEY_LOCAL_MACHINE"),):
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                winreg.CloseKey(winreg.OpenKey(root, UNINSTALL_KEY, 0, winreg.KEY_READ | view))
                problems.append("an uninstall entry was written under %s (it must be per user)" % name)
            except OSError:
                pass
    if value(winreg.HKEY_CURRENT_USER, *REGISTERED) is None:
        problems.append("I.K.E. is not listed for Windows' default apps (HKCU RegisteredApplications)")
    command = value(winreg.HKEY_CURRENT_USER, OWN_KEYS[0] + r"\shell\open\command", "")
    if not command or str(app / "ike-browser.exe").lower() not in command.lower() or '"%1"' not in command:
        problems.append("the command for web addresses is %r" % command)
    for folder in (os.environ.get("ProgramFiles", ""), os.environ.get("ProgramFiles(x86)", "")):
        if folder and (Path(folder) / "I.K.E").exists():
            problems.append("something was installed under %s" % folder)
    return problems


def make_user_data():
    for folder in user_data():
        folder.mkdir(parents=True, exist_ok=True)
        (folder / MARK).write_text("the uninstaller must leave this file alone\n", "utf-8")
        print("marked", folder)
    return []


def check_uninstalled():
    import winreg
    app = app_dir()
    for _ in range(120):                       # the uninstaller's last step runs after it returned
        if not app.exists():
            break
        time.sleep(0.5)
    problems = []
    if app.exists():
        left = sorted(p.relative_to(app).as_posix() for p in app.rglob("*"))[:40]
        problems.append("still there: %s (%s)" % (app, ", ".join(left) or "empty folder"))
    if shortcut().exists():
        problems.append("the Start-menu shortcut is still there")
    if key_exists(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY):
        problems.append("the uninstall entry is still there")
    if value(winreg.HKEY_CURRENT_USER, *REGISTERED) is not None:
        problems.append("I.K.E. is still listed in HKCU RegisteredApplications")
    for key in OWN_KEYS:
        if key_exists(winreg.HKEY_CURRENT_USER, key):
            problems.append("registry key left behind: HKCU\\" + key)
    for folder in user_data():
        if not (folder / MARK).is_file():
            problems.append("the user's data was touched: %s is gone" % (folder / MARK))
        else:
            print("kept:", folder / MARK)
    return problems


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--tree")
    ap.add_argument("--installed", action="store_true")
    ap.add_argument("--make-user-data", action="store_true")
    ap.add_argument("--uninstalled", action="store_true")
    args = ap.parse_args()
    problems = []
    if args.tree:
        problems += check_tree(args.tree)
    if args.installed:
        problems += check_installed()
    if args.make_user_data:
        problems += make_user_data()
    if args.uninstalled:
        problems += check_uninstalled()
    for problem in problems:
        print("check-install: " + problem, file=sys.stderr)
    if not problems:
        print("check-install: all as expected")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
