"""Files, folders and links handed to the desktop's own apps (1.1.24).

Until 1.1.23 a downloaded file was opened through Qt's QDesktopServices,
which starts xdg-open, and I.K.E. became the default browser through
xdg-settings: both from xdg-utils, whose Arch advisory (AVG-1420) has no fix.
Now nothing of xdg-utils is used:

- a file, a folder or a link goes to the XDG desktop portal
  (org.freedesktop.portal.OpenURI, the same service sandboxed apps use):
  OpenFile with a file descriptor of the file, so the portal opens exactly
  that file with the app the desktop chose for its type; OpenDirectory shows
  a file in its folder (Dolphin, Files, Thunar...); OpenURI takes a link of
  another kind (mailto:, magnet:...). The D-Bus code is I.K.E.'s own
  (desktopbus.py, jeepney); nothing waits: the answer comes on the event loop;
- when no portal answers, the desktop's own opener does it if it is there
  (kioclient on KDE, gio on GNOME and the desktops built on GLib, exo-open
  on Xfce); with none, a message says where the file is. Never xdg-open;
- the default browser is written in ~/.config/mimeapps.list as the XDG MIME
  Applications specification says (and in KDE's kdeglobals when it names a
  browser of its own), atomically, every other line kept;
- the handoffs of the menus ("Open with Okular", "Open image in Gwenview",
  "Add to calendar"...) are offered only when the desktop has an app for that
  type: read from the same mimeapps.list files and from the apps' .desktop
  files (mimeinfo.cache), never by starting anything.
"""

import os
import re
import shutil
import subprocess
import time
from pathlib import Path

PORTAL = ("org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop", "org.freedesktop.portal.OpenURI")
OWN_IDS = ("ike-browser.desktop",)
BROWSER_TYPES = ("x-scheme-handler/http", "x-scheme-handler/https", "text/html")
DEFAULTS = "Default Applications"
ADDED = "Added Associations"
REMOVED = "Removed Associations"
# the desktop's own openers, used only when no portal answers and only when installed
OPENERS = ("kioclient", "gio", "exo-open")
# temporary copies handed to an app (an image, a PDF, a page's source) are kept a day
KEEP_SECONDS = 24 * 3600


# --- where the XDG files are ----------------------------------------------------------------------

def _absolute(value, default):
    p = Path(value) if value else None
    return p if p is not None and p.is_absolute() else default


def config_home(environ=None):
    env = os.environ if environ is None else environ
    return _absolute(env.get("XDG_CONFIG_HOME"), Path(env.get("HOME") or Path.home()) / ".config")


def data_home(environ=None):
    env = os.environ if environ is None else environ
    return _absolute(env.get("XDG_DATA_HOME"), Path(env.get("HOME") or Path.home()) / ".local" / "share")


def _dir_list(value, default):
    out = [Path(p) for p in (value or "").split(":") if p and Path(p).is_absolute()]
    return out or [Path(p) for p in default]


def config_dirs(environ=None):
    env = os.environ if environ is None else environ
    return _dir_list(env.get("XDG_CONFIG_DIRS"), ("/etc/xdg",))


def data_dirs(environ=None):
    env = os.environ if environ is None else environ
    return _dir_list(env.get("XDG_DATA_DIRS"), ("/usr/local/share", "/usr/share"))


def desktops(environ=None):
    env = os.environ if environ is None else environ
    return [d.lower() for d in (env.get("XDG_CURRENT_DESKTOP") or "").split(":") if d.strip()]


def list_files(environ=None):
    """The mimeapps.list files in the specification's order, the first the strongest."""
    out = []
    folders = [config_home(environ), *config_dirs(environ), data_home(environ) / "applications",
               *(d / "applications" for d in data_dirs(environ))]
    names = ["%s-mimeapps.list" % d for d in desktops(environ)] + ["mimeapps.list"]
    for folder in folders:
        out += [folder / name for name in names]
    return out


# --- reading ----------------------------------------------------------------------------------------

def parse_groups(text):
    """{group: {key: value}} of a desktop-entry style file (the first of a repeated key wins)."""
    groups, cur = {}, None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            cur = groups.setdefault(line[1:-1], {})
            continue
        if cur is not None and "=" in line:
            key, value = line.split("=", 1)
            cur.setdefault(key.strip(), value.strip())
    return groups


def ids(value):
    return [v.strip() for v in (value or "").split(";") if v.strip()]


_cache = {}


def _read(path):
    """parse_groups of a file, kept while the file is unchanged ({} when there is none)."""
    try:
        st = path.stat()
    except OSError:
        return {}
    key = str(path)
    stamp = (st.st_mtime_ns, st.st_size)
    hit = _cache.get(key)
    if hit and hit[0] == stamp:
        return hit[1]
    try:
        groups = parse_groups(path.read_text("utf-8", "replace"))
    except OSError:
        groups = {}
    if len(_cache) > 4000:
        _cache.clear()
    _cache[key] = (stamp, groups)
    return groups


def desktop_file(desktop_id, environ=None):
    """The path of an installed app's .desktop file, or None ("kde-foo.desktop" may be kde/foo.desktop)."""
    if not desktop_id.endswith(".desktop") or "/" in desktop_id or desktop_id.startswith("."):
        return None
    tries = [desktop_id]
    parts = desktop_id.split("-")
    for i in range(1, len(parts)):
        tries.append("/".join(parts[:i]) + "/" + "-".join(parts[i:]))
    for folder in [data_home(environ), *data_dirs(environ)]:
        for name in tries:
            p = folder / "applications" / name
            if p.is_file():
                return p
    return None


def _program(value, environ=None):
    """The program an Exec= or TryExec= line starts, when it exists."""
    env = os.environ if environ is None else environ
    words = (value or "").split()
    while words and (words[0] == "env" or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", words[0])):
        words.pop(0)
    if not words:
        return None
    prog = words[0].strip('"')
    if prog.startswith("/"):
        return prog if os.access(prog, os.X_OK) else None
    return shutil.which(prog, path=env.get("PATH"))


class DesktopApp:
    def __init__(self, desktop_id, name, path):
        self.id, self.name, self.path = desktop_id, name, path

    def __repr__(self):
        return "DesktopApp(%r, %r)" % (self.id, self.name)


def app_info(desktop_id, environ=None, language=None):
    """The app of a .desktop id when it is installed and can start, else None."""
    if desktop_id in OWN_IDS or desktop_id.startswith("ike-browser"):
        return None
    path = desktop_file(desktop_id, environ)
    if path is None:
        return None
    entry = _read(path).get("Desktop Entry", {})
    if entry.get("Hidden", "").lower() == "true" or entry.get("Type", "Application") != "Application":
        return None
    if entry.get("TryExec") and not _program(entry["TryExec"], environ):
        return None
    if not _program(entry.get("Exec"), environ):
        return None
    name = ""
    if language:
        base = language.split("_")[0]
        name = entry.get("Name[%s]" % language) or entry.get("Name[%s]" % base) or ""
    name = name or entry.get("Name") or desktop_id[:-len(".desktop")]
    return DesktopApp(desktop_id, name, path)


def _cached_ids(folder, mime):
    """The apps that declare `mime` in one applications folder (mimeinfo.cache, else the files)."""
    cache = folder / "mimeinfo.cache"
    if cache.is_file():
        return ids(_read(cache).get("MIME Cache", {}).get(mime))
    found = []
    try:
        files = sorted(folder.rglob("*.desktop"))
    except OSError:
        return []
    for f in files[:2000]:
        if mime in ids(_read(f).get("Desktop Entry", {}).get("MimeType")):
            found.append("-".join(f.relative_to(folder).parts))      # kde/kate.desktop is kde-kate.desktop
    return found


def default_app(mime, environ=None, language=None):
    """The app the desktop opens `mime` with, as the XDG MIME Applications
    specification finds it: the defaults of the mimeapps.list files, then
    their added associations, then the apps that declare the type, without
    the removed ones. None when there is none (I.K.E. itself never counts)."""
    files = list_files(environ)
    groups = [_read(f) for f in files]
    for g in groups:
        for i in ids(g.get(DEFAULTS, {}).get(mime)):
            app = app_info(i, environ, language)
            if app:
                return app
    removed = set()
    for g in groups:
        for i in ids(g.get(ADDED, {}).get(mime)):
            if i not in removed:
                app = app_info(i, environ, language)
                if app:
                    return app
        removed.update(ids(g.get(REMOVED, {}).get(mime)))
    for folder in [data_home(environ), *data_dirs(environ)]:
        for i in _cached_ids(folder / "applications", mime):
            if i not in removed:
                app = app_info(i, environ, language)
                if app:
                    return app
    return None


def _ancestors(mime):
    """The type and its parents (text/x-python -> text/plain), from Qt's MIME database."""
    out = [mime]
    try:
        from PyQt6.QtCore import QMimeDatabase
        t = QMimeDatabase().mimeTypeForName(mime)
        if t.isValid():
            out += [m for m in [t.name()] + list(t.allAncestors()) if m not in out]
    except Exception:
        pass
    return out


_found = {}
FOUND_SECONDS = 5           # a menu or the downloads window asks often: the answer is kept a moment


def app_for(mime, environ=None):
    """The desktop's app for a type or one of its parents, or None."""
    from .i18n import current
    lang = current()
    key = (mime, lang)
    hit = _found.get(key) if environ is None else None
    if hit and time.monotonic() - hit[0] < FOUND_SECONDS:
        return hit[1]
    found = None
    for m in _ancestors(mime):
        found = default_app(m, environ, lang)
        if found:
            break
    if environ is None:
        _found[key] = (time.monotonic(), found)
    return found


def file_type(path, how="name"):
    """The MIME type of a file (Qt's MIME database): by its "name", its
    "content" alone, or "both"."""
    from PyQt6.QtCore import QMimeDatabase
    M = QMimeDatabase.MatchMode
    mode = {"name": M.MatchExtension, "content": M.MatchContent}.get(how, M.MatchDefault)
    return QMimeDatabase().mimeTypeForFile(str(path), mode)


def image_type(name):
    """The image type a file name says, else image/png (the viewer of any image)."""
    try:
        t = file_type(name or "x").name()
    except Exception:
        t = ""
    return t if t.startswith("image/") else "image/png"


# --- the kinds of file a handoff is for ------------------------------------------------------------

ARCHIVES = ("application/zip", "application/x-tar", "application/x-compressed-tar", "application/x-bzip-compressed-tar",
            "application/x-bzip2-compressed-tar", "application/x-xz-compressed-tar",
            "application/x-zstd-compressed-tar", "application/x-7z-compressed", "application/x-rar",
            "application/vnd.rar", "application/gzip", "application/x-bzip2", "application/x-xz",
            "application/zstd", "application/x-lzma", "application/x-archive", "application/x-cpio",
            "application/x-lha", "application/x-arj", "application/x-cd-image")
CALENDAR = "text/calendar"


def kind_of(mime_type):
    """"archive", "calendar", "image", "pdf" or "" for a QMimeType."""
    names = [mime_type.name()] + list(mime_type.allAncestors())
    if CALENDAR in names:
        return "calendar"
    if "application/pdf" in names:
        return "pdf"
    if any(n.startswith("image/") for n in names):
        return "image"
    if any(n in ARCHIVES for n in names):
        return "archive"
    return ""


# --- the default browser ------------------------------------------------------------------------------

def _write_atomic(path, text):
    """Write `text` into `path` in one step (a link is followed to its file); the file keeps its mode."""
    import tempfile
    path = Path(path)
    if path.is_symlink():
        path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        mode = path.stat().st_mode & 0o7777
    except OSError:
        mode = 0o644
    fd, tmp = tempfile.mkstemp(prefix="." + path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def set_defaults(text, values, group=DEFAULTS, only_existing=False):
    """The text of a mimeapps.list with `values` ({type: desktop id}) first in
    `group`; the other apps of those types stay after it, every other line as
    it was. only_existing: change only the types the group already has."""
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines(keepends=True)
    if lines and not lines[-1].endswith(("\n", "\r")):
        lines[-1] += newline
    done = set()
    start = end = None                 # the group's header line and the line after its last entry
    cur = None
    for n, line in enumerate(lines):
        s = line.strip()
        if s.startswith("[") and s.endswith("]"):
            cur = s[1:-1]
            if cur == group and start is None:
                start = end = n + 1
            continue
        if cur != group:
            continue
        if s and not s.startswith("#"):
            end = n + 1
        if "=" in s and not s.startswith("#"):
            key, value = s.split("=", 1)
            key = key.strip()
            if key in values and key not in done:
                own = values[key]
                rest = [i for i in ids(value) if i != own]
                lines[n] = "%s=%s" % (key, ";".join([own] + rest) + ";") + newline
                done.add(key)
    missing = [k for k in values if k not in done]
    if only_existing or not missing:
        return "".join(lines)
    add = ["%s=%s;%s" % (k, values[k], newline) for k in missing]
    if start is None:
        if lines and lines[-1].strip():
            lines.append(newline)
        lines += ["[%s]%s" % (group, newline)] + add
    else:
        lines[end:end] = add
    return "".join(lines)


def set_default_browser(desktop_id=OWN_IDS[0], environ=None):
    """Make an app the default web browser for this user: ~/.config/mimeapps.list
    (http, https and text/html), a desktop's own list there that names other
    browsers for them, and KDE's kdeglobals when it names a browser. Returns
    the files written; raises OSError when the main one cannot be written."""
    home = config_home(environ)
    values = dict.fromkeys(BROWSER_TYPES, desktop_id)
    written = []
    main = home / "mimeapps.list"
    try:
        old = main.read_text("utf-8")
    except FileNotFoundError:
        old = ""
    _write_atomic(main, set_defaults(old, values))
    written.append(main)
    for d in desktops(environ):
        extra = home / ("%s-mimeapps.list" % d)
        try:
            text = extra.read_text("utf-8")
        except OSError:
            continue
        new = set_defaults(text, values, only_existing=True)
        if new != text:
            _write_atomic(extra, new)
            written.append(extra)
    kde = home / "kdeglobals"
    try:
        text = kde.read_text("utf-8")
    except OSError:
        text = None
    if text is not None:
        new = kde_browser(text, desktop_id)
        if new != text:
            _write_atomic(kde, new)
            written.append(kde)
    return written


def kde_browser(text, desktop_id):
    """kdeglobals with [General] BrowserApplication set to the app, when the
    file already names a browser there (KIO opens web links with it)."""
    lines = text.splitlines(keepends=True)
    group = None
    for n, line in enumerate(lines):
        s = line.strip()
        if s.startswith("[") and s.endswith("]"):
            group = s[1:-1]
            continue
        if group == "General" and re.match(r"BrowserApplication(\[[^\]]*\])?\s*=", s):
            end = line[len(line.rstrip("\r\n")):]
            lines[n] = "BrowserApplication=%s%s" % (desktop_id, end or "\n")
    return "".join(lines)


# --- handing over ----------------------------------------------------------------------------------------

def temp_dir():
    """A private folder for the copies handed to an app; copies older than a day go."""
    from .config import CACHE_DIR
    folder = Path(CACHE_DIR) / "handoff"
    folder.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(folder, 0o700)
        now = time.time()
        for f in folder.iterdir():
            if f.is_file() and now - f.stat().st_mtime > KEEP_SECONDS:
                f.unlink()
    except OSError:
        pass
    return folder


def safe_name(name, fallback="file"):
    name = re.sub(r"[^\w .,()+-]", "_", (name or "").strip())[:120].strip(" .")
    return name or fallback


def opener_order(environ=None):
    """The desktop's own openers, its own first."""
    desk = desktops(environ)
    first = ("kioclient" if any("kde" in d for d in desk)
             else "exo-open" if any("xfce" in d for d in desk) else "gio")
    return [first] + [o for o in OPENERS if o != first]


def start_opener(target, environ=None):
    """Open a file, folder or link with the desktop's own opener when one is
    installed (never xdg-open). Returns the program started, or ""."""
    target = str(target)
    if not target or target.startswith("-"):
        return ""
    from .fontallow import child_env
    env = child_env(os.environ if environ is None else environ)
    kw = {"env": env, "stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
          "stderr": subprocess.DEVNULL, "start_new_session": True}
    for prog in opener_order(environ):
        if not shutil.which(prog, path=env.get("PATH")):
            continue
        try:
            if prog == "kioclient":
                subprocess.Popen(["kioclient", "exec", target], **kw)
            elif prog == "gio":
                subprocess.Popen(["gio", "open", target], **kw)
            else:
                subprocess.Popen(["exo-open", target], **kw)
        except OSError:
            continue
        return prog
    return ""


class Handoff:
    """Hands files, folders and links to the desktop (the portal, else its own opener)."""

    def __init__(self, app=None, bus_factory=None, opener=start_opener):
        self.app = app
        self._bus = None
        self._bus_factory = bus_factory
        self._opener = opener
        self.tokens = 0

    def _portal(self):
        if self._bus is not None and self._bus.connected:
            return self._bus
        if self._bus_factory is not None:
            bus = self._bus_factory()
        else:
            from .desktopbus import Bus
            bus = Bus(None, fds=True)
            if not bus.connect():
                bus = None
        self._bus = bus
        return bus

    def _options(self):
        self.tokens += 1
        return {"handle_token": ("s", "ike%d_%d" % (os.getpid(), self.tokens))}

    # --- what the menus and windows call
    def open_file(self, path, parent=None):
        """Open a file (or a folder) with the app the desktop chose for it."""
        self._send_file("OpenFile", Path(path), parent, lambda: self._fallback(Path(path), parent))

    def show_in_folder(self, path, parent=None):
        """Show a file in its folder, selected (the file manager); a folder is opened itself."""
        path = Path(path)
        if path.is_dir():
            return self.open_file(path, parent)
        folder = path.parent

        def instead():
            # a portal older than OpenDirectory: the folder itself
            self._send_file("OpenFile", folder, parent, lambda: self._fallback(folder, parent))
        self._send_file("OpenDirectory", path, parent, instead)

    def open_uri(self, url, parent=None):
        """A link of another kind (mailto:, magnet:...) to the app the desktop chose for it."""
        text = url if isinstance(url, str) else bytes(url.toEncoded()).decode("ascii", "replace")
        bus = self._portal()
        if bus is None:
            self._fallback(text, parent)
            return
        bus.call(*PORTAL, "OpenURI", "ssa{sv}", ("", text, self._options()),
                 on_reply=lambda *_a: None, on_error=lambda _e: self._fallback(text, parent))

    # --- the parts
    def _send_file(self, member, path, parent, otherwise):
        try:
            fd = os.open(str(path), os.O_RDONLY | os.O_CLOEXEC)
        except OSError:
            self._fallback(path, parent)
            return
        try:
            bus = self._portal()
            if bus is None:
                otherwise()
                return
            bus.call(*PORTAL, member, "sha{sv}", ("", fd, self._options()),
                     on_reply=lambda *_a: None, on_error=lambda _e: otherwise())
        finally:
            os.close(fd)                       # the bus has sent its own copy

    def _fallback(self, target, parent):
        if self._opener(str(target)):
            return
        self.nothing(target, parent)

    def nothing(self, target, parent=None):
        """No portal and no opener: say so, and where the file is."""
        try:
            from PyQt6.QtWidgets import QMessageBox

            from .i18n import T
            box = QMessageBox(QMessageBox.Icon.Information, "I.K.E.",
                              T("No app of the desktop could open %s.") % target, parent=parent)
            from PyQt6.QtCore import Qt
            box.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
            box.open()
            self.last_message = box
        except Exception:
            pass
