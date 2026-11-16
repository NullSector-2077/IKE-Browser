"""The few things I.K.E. asks Windows directly (through ctypes, no extra
library): who the user is, who owns a named pipe, the memory and CPU time of a
process, whether animations are wanted, the name the task bar groups windows
under.

Imported only on Windows (``sys.platform == "win32"``); every function gives
a harmless answer when a call fails. The parts that do not need Windows (the
name of the single-instance pipe) are plain functions the automatic tests run
on every system.
"""

import ctypes
import re
import sys

APP_USER_MODEL_ID = "IKE.Browser"
RUNNING_MUTEX = "IKE.Browser.Running"   # AppMutex of packaging/windows/ike-browser.iss
SPI_GETCLIENTAREAANIMATION = 0x1042
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
SYNCHRONIZE = 0x00100000
TOKEN_QUERY = 0x0008
TOKEN_USER, TOKEN_OWNER = 1, 4       # TOKEN_INFORMATION_CLASS: TokenUser, TokenOwner
SE_KERNEL_OBJECT = 6
OWNER_SECURITY_INFORMATION = 0x00000001
TICKS_PER_SECOND = 10_000_000        # FILETIME counts 100-nanosecond steps
_PIPE_NAME_MAX = 200                 # a pipe name may be 256 characters with its \\.\pipe\ prefix


def instance_name(app_id, user, profile):
    """Name of the pipe the running browser of a user and profile listens on.

    Pipe names are shared by every user of the computer, so the name carries
    the user's own identifier (the SID, as text): two users never meet on one
    name. Only letters, digits, "-" and "_" are kept, so nothing in a profile
    name can turn the name into a path (a pipe name must not contain "\\")."""
    def plain(text):
        return re.sub(r"[^A-Za-z0-9_-]", "", str(text))
    name = "%s-%s-%s" % (plain(app_id), plain(user) or "user", plain(profile) or "default")
    return name[:_PIPE_NAME_MAX]


if sys.platform == "win32":
    from ctypes import wintypes

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    _user32 = ctypes.WinDLL("user32", use_last_error=True)

    _kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    _kernel32.OpenProcess.restype = wintypes.HANDLE
    _kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    _kernel32.WaitForSingleObject.restype = wintypes.DWORD
    _kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
    _kernel32.LocalFree.restype = wintypes.HLOCAL
    _kernel32.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    _kernel32.GetProcessTimes.restype = wintypes.BOOL
    _advapi32.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
    _advapi32.OpenProcessToken.restype = wintypes.BOOL
    _advapi32.GetTokenInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                              wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    _advapi32.GetTokenInformation.restype = wintypes.BOOL
    _advapi32.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR)]
    _advapi32.ConvertSidToStringSidW.restype = wintypes.BOOL
    _advapi32.GetSecurityInfo.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.DWORD,
                                          ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p,
                                          ctypes.c_void_p, ctypes.c_void_p,
                                          ctypes.POINTER(ctypes.c_void_p)]
    _advapi32.GetSecurityInfo.restype = wintypes.DWORD
    _advapi32.EqualSid.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    _advapi32.EqualSid.restype = wintypes.BOOL
    _user32.SystemParametersInfoW.argtypes = [wintypes.UINT, wintypes.UINT, ctypes.c_void_p, wintypes.UINT]
    _user32.SystemParametersInfoW.restype = wintypes.BOOL

    class _MemoryCounters(ctypes.Structure):          # PROCESS_MEMORY_COUNTERS_EX
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
                    ("PrivateUsage", ctypes.c_size_t)]

    _kernel32.K32GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(_MemoryCounters),
                                                  wintypes.DWORD]
    _kernel32.K32GetProcessMemoryInfo.restype = wintypes.BOOL

    def _token_buffer(kind=TOKEN_USER):
        """A piece of this process's token (a buffer that starts with the
        pointer to a SID: the user's, or the default owner of what the
        process creates), or None."""
        token = wintypes.HANDLE()
        if not _advapi32.OpenProcessToken(_kernel32.GetCurrentProcess(), TOKEN_QUERY, ctypes.byref(token)):
            return None
        try:
            size = wintypes.DWORD(0)
            _advapi32.GetTokenInformation(token, kind, None, 0, ctypes.byref(size))
            if not size.value:
                return None
            buf = ctypes.create_string_buffer(size.value)
            if not _advapi32.GetTokenInformation(token, kind, buf, size, ctypes.byref(size)):
                return None
            return buf
        finally:
            _kernel32.CloseHandle(token)

    def _sid_of(buf):
        return ctypes.cast(buf, ctypes.POINTER(ctypes.c_void_p))[0]

    def _sid_text(sid):
        text = wintypes.LPWSTR()
        if not sid or not _advapi32.ConvertSidToStringSidW(sid, ctypes.byref(text)):
            return ""
        try:
            return text.value or ""
        finally:
            _kernel32.LocalFree(ctypes.cast(text, wintypes.HLOCAL))

    def user_sid():
        """The user's security identifier as text ("S-1-5-21-…"), or ""."""
        buf = _token_buffer()
        return _sid_text(_sid_of(buf)) if buf is not None else ""

    def owner_of(handle):
        """The owner of the object behind a handle, as text, or ""."""
        if not handle or int(handle) in (-1, 0):
            return ""
        owner, descriptor = ctypes.c_void_p(), ctypes.c_void_p()
        if _advapi32.GetSecurityInfo(wintypes.HANDLE(int(handle)), SE_KERNEL_OBJECT,
                                     OWNER_SECURITY_INFORMATION, ctypes.byref(owner), None, None, None,
                                     ctypes.byref(descriptor)) != 0:
            return ""
        try:
            return _sid_text(owner.value)
        finally:
            _kernel32.LocalFree(ctypes.cast(descriptor, wintypes.HLOCAL))

    def own_sids():
        """Who an object created by this process belongs to: the user, or -
        for a process started "as administrator" - what Windows then names as
        the owner (the Administrators group). Nobody without those rights
        can make an object with one of these owners."""
        found = set()
        for kind in (TOKEN_USER, TOKEN_OWNER):
            buf = _token_buffer(kind)
            if buf is not None:
                found.add(_sid_text(_sid_of(buf)))
        found.discard("")
        return found

    def owned_by_user(handle):
        """Does the object behind this handle (the pipe a second start has
        connected to) belong to the user of this process? Anybody may create
        a pipe with a given name first; only the owner tells whose it is."""
        owner = owner_of(handle)
        return bool(owner) and owner in own_sids()

    def _open(pid, access=PROCESS_QUERY_LIMITED_INFORMATION):
        try:
            return _kernel32.OpenProcess(access, False, int(pid)) or None
        except (TypeError, ValueError, OverflowError):
            return None

    def process_memory(pid):
        """Private memory of a process in bytes (what Task Manager calls
        "Memory (private working set)" is close to it), or None."""
        handle = _open(pid)
        if handle is None:
            return None
        try:
            counters = _MemoryCounters()
            counters.cb = ctypes.sizeof(counters)
            if not _kernel32.K32GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
                return None
            return int(counters.PrivateUsage or counters.WorkingSetSize)
        finally:
            _kernel32.CloseHandle(handle)

    def process_cpu_ticks(pid):
        """User + kernel CPU time of a process in 100-nanosecond steps, or None."""
        handle = _open(pid)
        if handle is None:
            return None
        try:
            made, ended, kernel, user = (wintypes.FILETIME() for _ in range(4))
            if not _kernel32.GetProcessTimes(handle, ctypes.byref(made), ctypes.byref(ended),
                                             ctypes.byref(kernel), ctypes.byref(user)):
                return None
            return sum((t.dwHighDateTime << 32) | t.dwLowDateTime for t in (kernel, user))
        finally:
            _kernel32.CloseHandle(handle)

    def wait_for_exit(pid, seconds=10):
        """Wait until a process has ended (at most `seconds`)."""
        handle = _open(pid, SYNCHRONIZE)
        if handle is None:
            return                       # already gone, or not ours to wait for
        try:
            _kernel32.WaitForSingleObject(handle, int(seconds * 1000))
        finally:
            _kernel32.CloseHandle(handle)

    def animations_wanted():
        """Settings → Accessibility → Visual effects → "Animation effects"
        (SPI_GETCLIENTAREAANIMATION): False when the user turned them off."""
        value = wintypes.BOOL(1)
        if not _user32.SystemParametersInfoW(SPI_GETCLIENTAREAANIMATION, 0, ctypes.byref(value), 0):
            return True
        return bool(value.value)

    def set_app_id():
        """Give the process the name the task bar groups its windows under,
        the same one the installer writes into the Start-menu shortcut: a
        pinned I.K.E. and its open windows share one button."""
        try:
            shell32 = ctypes.WinDLL("shell32")
            shell32.SetCurrentProcessExplicitAppUserModelID.argtypes = [wintypes.LPCWSTR]
            shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
        except (OSError, AttributeError):
            pass

    _running = []

    def mark_running():
        """Hold, for as long as I.K.E. runs, the named mark the installer and
        the uninstaller look for: they ask to close I.K.E. first instead of
        failing on files that are in use."""
        if _running:
            return
        try:
            _kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
            _kernel32.CreateMutexW.restype = wintypes.HANDLE
            handle = _kernel32.CreateMutexW(None, False, RUNNING_MUTEX)
            if handle:
                _running.append(handle)
        except (OSError, AttributeError):
            pass

    def is_running():
        """Is an I.K.E. of this user running (one that holds the mark of
        mark_running)?"""
        try:
            _kernel32.OpenMutexW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
            _kernel32.OpenMutexW.restype = wintypes.HANDLE
            handle = _kernel32.OpenMutexW(SYNCHRONIZE, False, RUNNING_MUTEX)
        except (OSError, AttributeError):
            return False
        if not handle:
            return False
        _kernel32.CloseHandle(handle)
        return True
