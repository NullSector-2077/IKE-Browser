"""I.K.E. DRM: finds, installs and updates the Widevine module by itself.

Services such as Netflix or Prime Video only play through Google's Widevine
module. Widevine is proprietary: I.K.E. cannot ship it, and it does not borrow
the copy of another browser either. With the user's consent it downloads the
module from Google's own server into I.K.E.'s data folder (no administrator
rights needed), checks it and uses it from there. A copy installed by a
distribution package is used when there is no copy of I.K.E.'s own.

Google hands Widevine out through Chrome's component updater (1.1.23: the old
zips on dl.google.com/widevine-cdm/ answer 404). I.K.E. asks that service
(update.googleapis.com, Omaha protocol 3.1) as a Chromium on x64 Linux would,
and only for Widevine: no cookies, no user or installation id, no other
component, and always as if nothing were installed. The answer names the
package (a CRX3) with its SHA-256; the package must match it, be signed with
Widevine's own key (the one its component id is made of) and hold a 64-bit
x86-64 Linux library. The old dl.google.com folder stays only as a fallback.
"""

import json
import os
import shutil
import struct
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from . import osinfo
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
# Chrome's component updater and the id of the Widevine CDM component
UPDATE_URL = "https://update.googleapis.com/service/update2/json"
APP_ID = "oimompecagnajdejgnnjijobebaeigek"
# the old download folder, only a fallback (its version list, then its zips);
# the fixed list of versions kept until 1.1.22 is gone: all of them answer 404
SOURCE = "https://dl.google.com/widevine-cdm/"
VERSIONS_URL = SOURCE + "versions.txt"
# Google's own hosts and their subdomains: the update service and the servers
# its answer sends the package from (dl.google.com, edgedl.me.gvt1.com,
# redirector.gvt1.com and the r*.gvt1.com servers it redirects to)
GOOGLE_DOMAINS = ("google.com", "googleapis.com", "gvt1.com")
MAX_ZIP = 64 * 1024 * 1024
MAX_CRX = MAX_ZIP + 1024 * 1024
MAX_LIB = 96 * 1024 * 1024
MAX_ANSWER = 256 * 1024


class DrmError(Exception):
    pass


class NotOffered(DrmError):
    """Google's servers did not offer a usable Widevine module."""


def _version_key(v):
    return tuple(int(p) if p.isdigit() else 0 for p in v.split("."))


def _plain_version(v):
    """v if it is a version such as 4.10.2891.0, else ''."""
    v = str(v).strip()
    parts = v.split(".")
    return v if len(parts) == 4 and all(p.isdigit() and len(p) <= 6 for p in parts) else ""


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


# ---- downloading, only from Google's own hosts over https -------------------

def google_https(url):
    """True for an https address on one of Google's own hosts."""
    from urllib.parse import urlsplit
    try:
        parts = urlsplit(str(url))
        host = (parts.hostname or "").lower()
        parts.port                              # a malformed port raises ValueError
    except ValueError:
        return False
    if parts.scheme != "https" or parts.username is not None:
        return False
    return any(host == d or host.endswith("." + d) for d in GOOGLE_DOMAINS)


def _open(req):
    """Open a request. A redirect to anything but https on Google's hosts is
    refused before it is followed."""
    import urllib.request

    from . import doh

    class Redirects(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            if not google_https(newurl):
                raise DrmError("refusing an insecure redirect")
            return super().redirect_request(req, fp, code, msg, headers, newurl)
    return doh.urlopen(req, timeout=60, handlers=(Redirects(),))


def _get(url, limit, body=None, headers=None):
    # imported only when Widevine is downloaded, not at every start (1.1.17)
    import urllib.request

    if not google_https(url):
        raise DrmError("refusing an address that is not Google's own over https")
    sent = {"User-Agent": osinfo.browser_user_agent()}
    sent.update(headers or {})
    req = urllib.request.Request(url, data=body, headers=sent)
    with _open(req) as r:
        if not google_https(r.geturl()):
            raise DrmError("refusing an insecure redirect")
        data = r.read(limit + 1)
    if len(data) > limit:
        raise DrmError("the download is unexpectedly large")
    return data


# ---- Chrome's component updater -----------------------------------------------

def update_request(prodversion):
    """The body of the update check, as Chromium sends it for one component.

    It says only "a Chromium on x64 Linux, engine version N, wants Widevine and
    has none": the version sent is always 0.0.0.0, so an installed copy is not
    revealed either. The two ids are new random ones for every request (the
    protocol uses them to match an answer to its request) and never stored."""
    import uuid
    return json.dumps({"request": {
        "protocol": "3.1",
        "@updater": "chromium",
        "@os": "linux",
        "updaterversion": prodversion,
        "prodversion": prodversion,
        "acceptformat": "crx3",
        "arch": "x64",
        "nacl_arch": "x86-64",
        "os": {"platform": "Linux", "arch": "x86_64"},
        "dedup": "cr",
        "ismachine": False,
        "requestid": "{%s}" % uuid.uuid4(),
        "sessionid": "{%s}" % uuid.uuid4(),
        "app": [{
            "appid": APP_ID,
            "version": "0.0.0.0",
            "enabled": True,
            "installsource": "ondemand",
            "updatecheck": {},
        }],
    }}).encode("utf-8")


def parse_answer(data):
    """The package offered in the update service's answer:
    {"version", "name", "sha256", "size", "urls"}, the urls only https ones on
    Google's hosts, in the answer's order. NotOffered when there is none."""
    import re
    try:
        text = data.decode("utf-8") if isinstance(data, bytes) else str(data)
        text = text.lstrip("﻿")
        if text.startswith(")]}'"):                # the XSSI prefix
            text = text[4:]
        apps = json.loads(text)["response"]["app"]
        app = next(a for a in apps if isinstance(a, dict) and a.get("appid") == APP_ID)
    except (ValueError, KeyError, TypeError, StopIteration, UnicodeDecodeError):
        raise NotOffered("the update service's answer could not be read")
    check = app.get("updatecheck") if isinstance(app.get("updatecheck"), dict) else {}
    status = str(check.get("status") or app.get("status") or "")
    if app.get("status", "ok") != "ok" or status != "ok":
        raise NotOffered('the update service answered "%s"' % (status if status != "ok" else app.get("status")))
    try:
        manifest = check["manifest"]
        version = _plain_version(manifest["version"])
        package = manifest["packages"]["package"][0]
        name = str(package["name"])
        sha256 = str(package["hash_sha256"]).lower()
        size = int(package.get("size") or 0)
        bases = [str(u.get("codebase", "")) for u in check["urls"]["url"] if isinstance(u, dict)]
    except (KeyError, IndexError, TypeError, ValueError, AttributeError):
        raise NotOffered("the update service's answer names no package")
    if not version:
        raise NotOffered("the update service's answer has no readable version")
    if not re.fullmatch(r"[0-9a-f]{64}", sha256):
        raise NotOffered("the update service's answer has no SHA-256 for the package")
    if not re.fullmatch(r"[A-Za-z0-9_-][A-Za-z0-9._-]{0,199}", name):
        raise NotOffered("the update service's answer names an unexpected file")
    if size > MAX_CRX:
        raise NotOffered("the package offered is unexpectedly large")
    urls = []
    for base in bases:
        url = (base if base.endswith("/") else base + "/") + name
        if google_https(base) and url not in urls:
            urls.append(url)
    if not urls:
        raise NotOffered("the update service offered no https address on Google's servers")
    return {"version": version, "name": name, "sha256": sha256, "size": size, "urls": urls}


def query():
    """Ask Google's component updater for the current Widevine package."""
    from . import chromever
    prod = chromever.engine_full()
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Update-Interactivity": "fg",
        "X-Goog-Update-AppId": APP_ID,
        "X-Goog-Update-Updater": "chromium-" + prod,
    }
    return parse_answer(_get(UPDATE_URL, MAX_ANSWER, update_request(prod), headers))


def crx_archive(data):
    """The zip inside a CRX3 package signed with Widevine's own key."""
    if len(data) < 12 or data[:4] != b"Cr24":
        raise DrmError("the download is not a Chrome component package")
    version, size = struct.unpack_from("<II", data, 4)
    if version != 3:
        raise DrmError("the package is not in the CRX3 format")
    if 12 + size > len(data):
        raise DrmError("the package is damaged")
    from . import extensions
    try:
        extensions.verify_crx(APP_ID, data)
    except ValueError:
        raise DrmError("the package is not signed with Widevine's own key")
    archive = data[12 + size:]
    if archive[:2] != b"PK":
        raise DrmError("the package is damaged")
    return archive


def fetch(offer):
    """Download the package an answer offered and return the zip inside, once
    its size, its SHA-256 and its signature are right (each address in turn,
    until one gives a package that passes)."""
    import hashlib
    last = "no address could be used"
    for url in offer["urls"][:4]:
        try:
            data = _get(url, MAX_CRX)
            if offer["size"] and len(data) != offer["size"]:
                raise DrmError("the package does not have the size Google's server gave")
            if hashlib.sha256(data).hexdigest() != offer["sha256"]:
                raise DrmError("the package does not match the checksum Google's server gave")
            return crx_archive(data)
        except DrmError as e:
            last = str(e)
        except Exception as e:                  # this server could not be reached
            last = "%s: %s" % (url.split("/")[2], e)
    raise DrmError(last)


# ---- the old download folder, only as a fallback ----------------------------

def available_versions():
    """Versions listed in the old download folder, newest first."""
    text = _get(VERSIONS_URL, 64 * 1024).decode("ascii", "ignore")
    versions = {_plain_version(line) for line in text.split()} - {""}
    return sorted(versions, key=_version_key, reverse=True)


def _from_old_folder(installed=""):
    """Install the newest version of the old folder that is newer than
    `installed`; DrmError when there is none (the component updater could
    not be asked, so I.K.E.'s copy is not said to be the newest)."""
    last = "no version could be downloaded"
    for version in available_versions()[:3]:
        if installed and _version_key(version) <= _version_key(installed):
            break
        try:
            data = _get("%s%s-%s.zip" % (SOURCE, version, ZIP_SUFFIX), MAX_ZIP)
            return install_from_zip(data, version)
        except DrmError as e:
            last = str(e)
        except Exception as e:                  # this version is not on the server
            last = "%s: %s" % (version, e)
    raise DrmError(last)


def download(installed=""):
    """Download and install the newest Widevine from Google's servers.

    Returns the version installed, or "" when `installed` (I.K.E.'s own copy)
    is already the newest offered. The component updater comes first, the old
    download folder only when that fails; NotOffered, with the component
    updater's reason, when neither gives a usable module."""
    try:
        offer = query()
        if installed and _version_key(offer["version"]) <= _version_key(installed):
            return ""
        return install_from_zip(fetch(offer), offer["version"])
    except Exception as e:
        reason = str(e) or e.__class__.__name__
    try:
        return _from_old_folder(installed)
    except Exception:
        pass
    raise NotOffered(reason)


class Installer(QThread):
    """Downloads and installs Widevine in the background."""

    finished_ok = pyqtSignal(str)        # installed version
    up_to_date = pyqtSignal(str)         # I.K.E.'s copy is already the newest
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
            st = status()
            installed = st["version"] if st["source"] == "ike" else ""
            version = download(installed)
            if version:
                self.finished_ok.emit(version)
            else:
                self.up_to_date.emit(installed)
        except NotOffered as e:
            from .i18n import T
            self.failed.emit(T("Google's server did not offer a usable Widevine module (%s). Instead you can "
                               "install the AUR package chromium-widevine: I.K.E. finds it by itself after a "
                               "restart.") % e)
        except Exception as e:
            self.failed.emit(str(e))


def update_available():
    """Newest version Google offers if it is newer than I.K.E.'s copy, else ''.
    The same question as an installation: nothing about the copy is sent."""
    st = status()
    if st["source"] != "ike" or not st["version"]:
        return ""
    try:
        newest = query()["version"]
    except Exception:
        try:
            newest = (available_versions() or [""])[0]
        except Exception:
            return ""
    return newest if _version_key(newest) > _version_key(st["version"]) else ""
