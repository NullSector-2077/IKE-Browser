"""I.K.E. DRM: finds, installs and updates the Widevine module by itself.

Services such as Netflix or Prime Video only play through Google's Widevine
module. Widevine is proprietary: I.K.E. cannot ship it, and it does not borrow
the copy of another browser either. With the user's consent it downloads the
module from Google's own server into I.K.E.'s data folder (no administrator
rights needed), checks it and uses it from there. A copy installed by a
distribution package is used when there is no copy of I.K.E.'s own.
"""

import json
import os
import shutil
import struct
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from .config import DATA_DIR

OWN_DIR = DATA_DIR / "WidevineCdm"
LIB_NAME, PLATFORM_DIR, ZIP_SUFFIX = "libwidevinecdm.so", "linux_x64", "linux-x64"
OWN_LIB = OWN_DIR / "_platform_specific" / PLATFORM_DIR / LIB_NAME
# copies installed by a distribution / AUR package (never another browser's)
SYSTEM_LIBS = (
    "/usr/lib/chromium/WidevineCdm/_platform_specific/linux_x64/" + LIB_NAME,
    "/usr/lib/chromium/" + LIB_NAME,
    "/usr/lib/chromium-widevine/" + LIB_NAME,
    "/opt/WidevineCdm/_platform_specific/linux_x64/" + LIB_NAME,
    "/usr/lib/widevine/" + LIB_NAME,
)
SOURCE = "https://dl.google.com/widevine-cdm/"
VERSIONS_URL = SOURCE + "versions.txt"
# tried, newest first, when the version list cannot be read
KNOWN_VERSIONS = ("4.10.2891.0", "4.10.2830.0", "4.10.2710.0")
MAX_ZIP = 64 * 1024 * 1024
MAX_LIB = 96 * 1024 * 1024


class DrmError(Exception):
    pass


def _version_key(v):
    return tuple(int(p) if p.isdigit() else 0 for p in v.split("."))


def _manifest_version(lib):
    """Version from the manifest.json that belongs to a library, or ''."""
    lib = Path(lib)
    for folder in (lib.parent, lib.parent.parent.parent):
        try:
            data = json.loads((folder / "manifest.json").read_text("utf-8"))
            return str(data.get("version", ""))
        except (OSError, ValueError):
            continue
    return ""


def status():
    """{"path", "version", "source"}; source is "ike", "system" or "" (none)."""
    if OWN_LIB.is_file():
        return {"path": str(OWN_LIB), "version": _manifest_version(OWN_LIB), "source": "ike"}
    for path in SYSTEM_LIBS:
        if os.path.isfile(path):
            return {"path": path, "version": _manifest_version(path), "source": "system"}
    return {"path": "", "version": "", "source": ""}


def library_path():
    return status()["path"] or None


def check_library(data):
    """Raise DrmError unless data is a 64-bit x86-64 Linux shared library."""
    if len(data) < 64 or data[:4] != b"\x7fELF":
        raise DrmError("the module is not a Linux library")
    if data[4] != 2 or data[5] != 1:
        raise DrmError("the module is not a 64-bit library")
    e_type, e_machine = struct.unpack_from("<HH", data, 16)
    if e_type != 3 or e_machine != 62:
        raise DrmError("the module is not built for this kind of computer (x86-64)")
    if len(data) > MAX_LIB:
        raise DrmError("the module is unexpectedly large")


def install_from_zip(data, expect_version=None):
    """Check a Widevine archive and install it into I.K.E.'s folder.

    Only the three known files are taken from the archive. The previous copy is
    replaced only once the new one is complete. Returns the installed version.
    """
    import io
    import zipfile
    if len(data) > MAX_ZIP:
        raise DrmError("the archive is unexpectedly large")
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise DrmError("the download is not a valid archive")
    files = {}
    for info in archive.infolist():
        name = info.filename.rsplit("/", 1)[-1]
        if name in (LIB_NAME, "manifest.json", "LICENSE.txt", "LICENSE") and name not in files:
            if info.file_size > MAX_LIB:
                raise DrmError("the archive holds an unexpectedly large file")
            files[name] = archive.read(info)
    if LIB_NAME not in files or "manifest.json" not in files:
        raise DrmError("the archive does not contain the Widevine module")
    check_library(files[LIB_NAME])
    try:
        manifest = json.loads(files["manifest.json"].decode("utf-8"))
        version = str(manifest["version"])
    except (ValueError, KeyError, UnicodeDecodeError):
        raise DrmError("the archive has no readable version information")
    if expect_version and version != expect_version:
        raise DrmError("the archive holds version %s, not %s" % (version, expect_version))
    arch = str(manifest.get("arch", "x64")).lower()
    if arch not in ("x64", "x86_64", "amd64"):
        raise DrmError("the module is for another architecture (%s)" % arch)

    OWN_DIR.parent.mkdir(parents=True, exist_ok=True)
    new = OWN_DIR.with_name(OWN_DIR.name + ".new")
    old = OWN_DIR.with_name(OWN_DIR.name + ".old")
    shutil.rmtree(new, ignore_errors=True)
    lib_dir = new / "_platform_specific" / PLATFORM_DIR
    lib_dir.mkdir(parents=True)
    (lib_dir / LIB_NAME).write_bytes(files[LIB_NAME])
    os.chmod(lib_dir / LIB_NAME, 0o755)
    (new / "manifest.json").write_bytes(files["manifest.json"])
    licence = files.get("LICENSE.txt") or files.get("LICENSE")
    if licence:
        (new / "LICENSE.txt").write_bytes(licence)
    shutil.rmtree(old, ignore_errors=True)
    if OWN_DIR.exists():
        OWN_DIR.rename(old)
    new.rename(OWN_DIR)
    shutil.rmtree(old, ignore_errors=True)
    return version


def remove():
    """Delete I.K.E.'s own copy (a system package's copy is not touched)."""
    shutil.rmtree(OWN_DIR, ignore_errors=True)


def _get(url, limit):
    # imported only when Widevine is downloaded, not at every start (1.1.17)
    import urllib.request

    req = urllib.request.Request(url, headers={"User-Agent": "I.K.E. DRM manager"})
    with urllib.request.urlopen(req, timeout=60) as r:
        final = r.geturl()
        if not final.startswith("https://"):
            raise DrmError("refusing an insecure redirect")
        data = r.read(limit + 1)
    if len(data) > limit:
        raise DrmError("the download is unexpectedly large")
    return data


def available_versions():
    """Versions offered by the server, newest first (the known ones as a fallback)."""
    versions = []
    try:
        text = _get(VERSIONS_URL, 64 * 1024).decode("ascii", "ignore")
        for line in text.split():
            parts = line.strip().split(".")
            if len(parts) == 4 and all(p.isdigit() for p in parts):
                versions.append(line.strip())
    except Exception:
        pass
    for v in KNOWN_VERSIONS:
        if v not in versions:
            versions.append(v)
    return sorted(set(versions), key=_version_key, reverse=True)


class Installer(QThread):
    """Downloads and installs Widevine in the background."""

    finished_ok = pyqtSignal(str)        # installed version
    failed = pyqtSignal(str)             # reason

    def __init__(self, parent=None, zip_path=None):
        super().__init__(parent)
        self.zip_path = zip_path

    def run(self):
        try:
            if self.zip_path:
                data = Path(self.zip_path).read_bytes()
                self.finished_ok.emit(install_from_zip(data))
                return
            last = "no version could be downloaded"
            for version in available_versions()[:6]:
                try:
                    data = _get("%s%s-%s.zip" % (SOURCE, version, ZIP_SUFFIX), MAX_ZIP)
                    self.finished_ok.emit(install_from_zip(data, version))
                    return
                except DrmError as e:
                    last = str(e)
                except Exception as e:      # this version is not on the server
                    last = "%s: %s" % (version, e)
            self.failed.emit(last)
        except Exception as e:
            self.failed.emit(str(e))


def update_available():
    """Newest version on the server if it is newer than I.K.E.'s copy, else ''."""
    st = status()
    if st["source"] != "ike" or not st["version"]:
        return ""
    try:
        text = _get(VERSIONS_URL, 64 * 1024).decode("ascii", "ignore")
    except Exception:
        return ""
    listed = [v for v in text.split() if len(v.split(".")) == 4 and v.replace(".", "").isdigit()]
    if not listed:
        return ""
    newest = max(listed, key=_version_key)
    return newest if _version_key(newest) > _version_key(st["version"]) else ""
