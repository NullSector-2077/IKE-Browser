"""Safer downloads (1.1.24): two questions before a file is saved.

- A program or a script (by its name or its type: AppImage, .run, .sh, .exe,
  .msi, .deb, .rpm, .jar, .py, .bat, .cmd, .ps1, .desktop) from a site on
  I.K.E.'s protection lists (the filter lists, the malware list among them)
  or from a site the user never visited before: I.K.E. warns first.
- A file asked for over plain http from a secure (https) page (a "mixed
  download"): someone on the network could read or replace it, so it is
  stopped first.

Both questions have "Cancel" as the default answer and "Download anyway" at
the user's risk (app.py). Nothing is asked of the network: the lists are the
ones already loaded, the visits are I.K.E.'s own history.
"""

from urllib.parse import urlsplit

EXTENSIONS = (".appimage", ".run", ".sh", ".exe", ".msi", ".deb", ".rpm", ".jar", ".py", ".bat", ".cmd", ".ps1",
              ".desktop")
TYPES = frozenset((
    "application/vnd.appimage", "application/x-iso9660-appimage", "application/x-appimage",
    "application/x-executable", "application/x-pie-executable", "application/x-elf",
    "application/x-sh", "application/x-shellscript", "text/x-sh", "text/x-shellscript",
    "application/x-msdownload", "application/x-msdos-program", "application/x-ms-dos-executable",
    "application/x-dosexec", "application/vnd.microsoft.portable-executable", "application/x-ms-installer",
    "application/x-msi", "application/x-ole-storage-msi", "application/vnd.debian.binary-package",
    "application/x-debian-package", "application/x-deb", "application/x-rpm",
    "application/x-redhat-package-manager", "application/java-archive", "application/x-java-archive",
    "text/x-python", "text/x-python3", "application/x-python", "application/x-python-code",
    "application/x-bat", "application/bat", "text/x-msdos-batch", "application/x-msdos-batch",
    "application/x-powershell", "text/x-powershell", "application/x-desktop", "application/x-makeself",
))


def clean_name(name):
    """The name as the desktop will see it (spaces and dots at its end do not count)."""
    return (name or "").strip().rstrip(". \t").lower()


def is_executable(name, mime=""):
    """True for a program or a script, by its name or its MIME type."""
    if clean_name(name).endswith(EXTENSIONS):
        return True
    return (mime or "").split(";")[0].strip().lower() in TYPES


def is_mixed(page_url, url):
    """True for a download over http started from an https page."""
    return (urlsplit(page_url or "").scheme.lower() == "https"
            and urlsplit(url or "").scheme.lower() == "http")


def listed(blocker, url):
    """True when the protection lists stop `url` as a page (a site that spreads malware...)."""
    if not url or urlsplit(url).scheme.lower() not in ("http", "https") or blocker is None:
        return False
    try:
        return bool(blocker.should_block(url, url, "document"))
    except Exception:
        return False


def risk(url, page_url, name, mime, blocker, visited):
    """What to ask before this download, or None.

    url, page_url: the file's and the page's addresses (text); visited(site,
    page_url) says whether the user visited the site before this page.
    Returns {"kind": "mixed" | "listed" | "new", "site": ..., "name": ...}."""
    from .shields import site_of
    # the site is the page's; a download with no page of a site (typed, from
    # I.K.E.'s own pages) is the file's own site
    from_page = bool(urlsplit(page_url or "").hostname)
    source = page_url if from_page else (url or "")
    parts = urlsplit(source)
    host = (parts.hostname or "").lower()
    site = site_of(host) if host else ""
    out = {"site": site or host, "name": name or urlsplit(url or "").path.rsplit("/", 1)[-1]}
    if is_mixed(page_url, url):
        return dict(out, kind="mixed")
    path_name = urlsplit(url or "").path.rsplit("/", 1)[-1]
    if not (is_executable(name, mime) or is_executable(path_name)):
        return None
    if listed(blocker, page_url) or listed(blocker, url):
        return dict(out, kind="listed")
    if site and parts.scheme.lower() in ("http", "https") and not visited(site, page_url if from_page else ""):
        return dict(out, kind="new")
    return None


def message(found):
    """The question's text for a risk()."""
    from .i18n import T
    if found["kind"] == "mixed":
        return T("I.K.E. stopped the download of %s: the page is secure (https), but the file would come "
                 "without protection (http). Someone on the network could read it or replace it.") % found["name"]
    if found["kind"] == "listed":
        return T("%s is a program or a script, and %s is on I.K.E.'s protection lists (sites that spread "
                 "malware). It could harm this computer.") % (found["name"], found["site"])
    return T("%s is a program or a script, and you have never visited %s before. Download it only if you "
             "trust the site.") % (found["name"], found["site"])
