"""Password breach check (1.1.24, opt-in, off by default; Passwords window).

When the user saves a password in the vault or fills one in from it, I.K.E.
asks the Have I Been Pwned "range" service whether the password appears in
known data breaches, without the password or its fingerprint ever leaving
the computer (k-anonymity):

- the password's SHA-1 fingerprint is computed here (40 hexadecimal digits);
- only its first 5 digits are sent (https://api.pwnedpasswords.com/range/ABCDE);
  more than 800 000 known passwords share each such prefix;
- the service answers with all the endings it knows for that prefix, and the
  comparison is made here. With "Add-Padding: true" every answer has about the
  same size, so even the size does not tell what was asked.

No account, no cookie, the same generic browser name as I.K.E.'s other
requests. Each password is checked at most once per session (only its
fingerprint is kept in memory, never written). A problem with the service
shows nothing.
"""

import hashlib

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from . import background

URL = "https://api.pwnedpasswords.com/range/"
PREFIX = 5
MAX_ANSWER = 2 * 1024 * 1024


def fingerprint(password):
    """The SHA-1 of the password in upper-case hexadecimal."""
    return hashlib.sha1(password.encode("utf-8")).hexdigest().upper()


def split(password):
    """(the 5 digits that are sent, the 35 that never leave the computer)."""
    fp = fingerprint(password)
    return fp[:PREFIX], fp[PREFIX:]


def request(prefix):
    """The request for one prefix: exactly 5 hexadecimal digits, padding asked for."""
    import urllib.request
    if len(prefix) != PREFIX or any(c not in "0123456789ABCDEF" for c in prefix):
        raise ValueError("not a prefix")
    from .osinfo import browser_user_agent
    return urllib.request.Request(URL + prefix, headers={
        "Add-Padding": "true", "User-Agent": browser_user_agent()})


def count_in(answer, suffix):
    """How often `suffix` appears in the service's answer ("SUFFIX:COUNT" lines;
    the padding lines have a count of 0)."""
    suffix = suffix.upper()
    for line in answer.splitlines():
        tail, _, n = line.strip().partition(":")
        if tail.upper() == suffix:
            try:
                return max(0, int(n))
            except ValueError:
                return 0
    return 0


class _Lookup(QThread):
    found = pyqtSignal(str, int)        # the fingerprint's ending, times seen (-1: no answer)

    def __init__(self, prefix, suffix, parent=None):
        super().__init__(parent)
        self.prefix, self.suffix = prefix, suffix

    def run(self):
        n = -1
        try:
            from . import doh
            with doh.urlopen(request(self.prefix), timeout=20) as r:
                if r.geturl().startswith(URL):            # no redirect elsewhere
                    n = count_in(r.read(MAX_ANSWER).decode("ascii", "replace"), self.suffix)
        except Exception:
            n = -1
        self.found.emit(self.suffix, n)


class BreachCheck(QObject):
    """Checks the passwords the vault saves or fills, when the user chose it."""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.seen = {}          # fingerprint -> times found (this session only)
        self._busy = set()

    def on(self):
        return bool(self.app.config.get("pw_breach_check"))

    def check(self, password, site, notify=None):
        """Look the password up (in the background) and tell the user when it
        was found. Nothing at all when the option is off."""
        if not self.on() or not password:
            return False
        prefix, suffix = split(password)
        fp = prefix + suffix
        if fp in self.seen:
            self._tell(self.seen[fp], site, notify)
            return True
        if fp in self._busy:
            return True
        self._busy.add(fp)
        job = _Lookup(prefix, suffix, self)

        def done(_suffix, n):
            self._busy.discard(fp)
            if n >= 0:
                self.seen[fp] = n
                self._tell(n, site, notify)
        job.found.connect(done)
        background.start(job)
        return True

    def _tell(self, n, site, notify):
        if n <= 0:
            return
        from .i18n import T
        text = T("The password used on %s appears %d times in known data breaches: change it.") % (site, n)
        (notify or self.app._notify)(text)
