"""Repair this site: find the protection that breaks a page and turn off only that one.

The user starts it from the shield. Every protection that is active on the site
is turned off and the page reloaded; if the page then works, protections are
turned back on a group at a time (halves, then quarters...) and the user says
after each reload whether the page still works. What breaks it stays off for
that site only, and is remembered (``site_opts[host]["repaired"]``) so it can be
undone from the shield. Nothing runs and nothing is stored until it is used.

While the search runs the changes live in memory only; cancelling, closing the
window or quitting puts back exactly what was there before.
"""

import copy

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWebEngineCore import QWebEnginePage
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QStyle, QToolButton, QWidget

from .config import rank
from .i18n import T

# (key, name shown to the user). Each one is a per-site switch.
PROTECTIONS = (
    ("ads", "Ad and tracker blocking"),
    ("cookies", "Cross-site cookie blocking"),
    ("fp", "Fingerprinting protection"),
    # 1.1.32: a site whose own workers the user blocked (the shield) and that
    # needs them (WhatsApp, Telegram) loses only that block, not its
    # fingerprinting protection. Right after "fp": the worker rule acts only
    # while "fp" is on, so the search always tries "fp" first (alone or in an
    # earlier group) and finds the workers, never "fp", guilty. Never on a
    # page of a safety warning: there they stay out whatever the repairs say
    ("workers", "Blocking of the site's own background workers"),
    # 1.1.32: two more a page can depend on, tried by the search like the others
    ("dark", "Dark mode on this site"),
    ("webrtc", "Hide local IP addresses from WebRTC"),
    ("https", "HTTPS upgrade"),
    ("consent", "Cookie banner refusal"),
    ("params", "Tracking parameter and referrer cleaning"),
    ("scripts", "Script blocking"),
)
NAMES = dict(PROTECTIONS)


def active(cfg, host):
    """Keys of the protections that act on this site now."""
    lv = rank(cfg.level_for(host))
    if lv == 0:
        return []
    opt = cfg.site_opt
    out = []
    if (cfg["comp_adblock"] or cfg["comp_consent"]) and opt(host, "ads") is not False:
        out.append("ads")
    mode = opt(host, "cookies")
    if mode in ("3p", "all") or (mode is None and lv >= 2 and cfg["block_third_party_cookies"]):
        out.append("cookies")
    if lv >= 2 and opt(host, "fp") is not False:
        out.append("fp")
    if lv >= 3 and opt(host, "fp") is not False and opt(host, "workers") is True:
        out.append("workers")           # blocked by the user on the site (1.1.32)
    if _dark_on(cfg, host):
        out.append("dark")
    if cfg["webrtc_hide_ip"] and opt(host, "webrtc") is not False:
        out.append("webrtc")
    if cfg["https_only"] and opt(host, "https") is not False:
        out.append("https")
    if cfg["comp_consent"] and opt(host, "consent") is not False:
        out.append("consent")
    if (cfg["strip_tracking_params"] or (lv >= 2 and cfg["trim_referrer"])) \
            and opt(host, "params") is not False:
        out.append("params")
    if host in cfg["site_noscript"]:
        out.append("scripts")
    return out


def _dark_on(cfg, host):
    """Does the page dark mode act on this site (shields.dark_for, read from the settings)?"""
    if not cfg.get("comp_dark", True):
        return False
    on = cfg["dark_mode"] == "on"
    listed = cfg["dark_exclude"] if on else cfg["dark_sites"]
    h = (host or "").lower().strip(".")
    while h:
        if h in listed:
            return not on
        if "." not in h:
            break
        h = h.split(".", 1)[1]
    return on


def set_off(cfg, host, key, off):
    """Turn one protection off (or back to its normal state) for this site."""
    if key == "dark":
        # dark mode on everywhere: the site on its list of exceptions; dark
        # mode off: the site taken off its list of dark sites
        on = cfg["dark_mode"] == "on"
        lst = cfg["dark_exclude"] if on else cfg["dark_sites"]
        want_listed = off if on else not off
        if want_listed and host not in lst:
            lst.append(host)
        elif not want_listed and host in lst:
            lst.remove(host)
        return
    if key == "scripts":
        lst = cfg["site_noscript"]
        if off and host in lst:
            lst.remove(host)
        elif not off and host not in lst:
            lst.append(host)
        return
    if key == "workers":
        # the protection here is the user's own block (True): back on is the
        # block again, off lets the site's own workers run (1.1.32). Back on
        # where the block came from a parent: its inheritance, not a block of
        # the host's own that a later "Allow them again" there would miss
        if off:
            cfg.set_site_opt(host, key, False)
        else:
            cfg.set_site_opt(host, key, None)
            if cfg.site_opt(host, key) is not True:
                cfg.set_site_opt(host, key, True)
        return
    value = "allow" if key == "cookies" else False
    cfg.set_site_opt(host, key, value if off else None)


def repaired(cfg, host):
    """Protections turned off on this site by an earlier repair."""
    o = cfg["site_opts"].get((host or "").lower()) or {}
    return [k for k in o.get("repaired", []) if k in NAMES]


def undo(cfg, host):
    host = (host or "").lower()
    keys = repaired(cfg, host)
    for k in keys:
        set_off(cfg, host, k, False)
    o = cfg["site_opts"].get(host)
    if o is not None:
        o.pop("repaired", None)
        if not o:
            cfg["site_opts"].pop(host, None)
    return keys


class Repair(QObject):
    """The search itself, without any widget: the bar below drives it.

    ``state`` is one of: "ask" (a reload was made, waiting for works/broken),
    "found" (done: ``culprits`` stay off), "none" (protections are not the
    cause), "level" (only switching the whole shield off helped: waiting for
    the user to keep it so or not), "cancelled".
    """

    changed = pyqtSignal()

    def __init__(self, app, view, host, suggested=()):
        super().__init__(app)
        self.app = app
        self.view = view
        self.host = host.lower()
        cfg = app.config
        self._saved = (copy.deepcopy(cfg["site_opts"].get(self.host)),
                       self.host in cfg["site_noscript"],
                       cfg["site_levels"].get(self.host),
                       (self.host in cfg["dark_exclude"], self.host in cfg["dark_sites"]))
        self.candidates = active(cfg, self.host)
        self.innocent = []          # turned back on: the page still worked
        self.culprits = []
        self.queue = []             # groups still to try
        self.testing = None         # the group turned back on in the current reload
        # 1.1.32: the probable cause the diagnosis found (incompat.py): tried
        # alone first; if the page still does not work, the full search
        self.suggested = [k for k in suggested if k in self.candidates]
        self.phase = "suggested" if self.suggested else "all"   # suggested -> all -> groups -> level
        self.state = "ask"
        self.step = 0

    # --- applying ------------------------------------------------------
    def _apply(self, off_keys):
        cfg = self.app.config
        for k in self.candidates:
            set_off(cfg, self.host, k, k in off_keys)
        self._reload()

    def _reload(self):
        app = self.app
        app.shields.apply_settings()
        app.refresh_windows()
        self.step += 1
        page = self.view.page() if self.view else None
        if page is not None:
            page.triggerAction(QWebEnginePage.WebAction.ReloadAndBypassCache)
        self.changed.emit()

    def _restore(self):
        cfg = self.app.config
        opts, noscript, level, dark = self._saved
        for listed, name in zip(dark, ("dark_exclude", "dark_sites")):
            lst = cfg[name]
            if listed and self.host not in lst:
                lst.append(self.host)
            elif not listed and self.host in lst:
                lst.remove(self.host)
        if opts is None:
            cfg["site_opts"].pop(self.host, None)
        else:
            cfg["site_opts"][self.host] = copy.deepcopy(opts)
        lst = cfg["site_noscript"]
        if noscript and self.host not in lst:
            lst.append(self.host)
        elif not noscript and self.host in lst:
            lst.remove(self.host)
        if level is None:
            cfg["site_levels"].pop(self.host, None)
        else:
            cfg["site_levels"][self.host] = level

    # --- the search ----------------------------------------------------
    def start(self):
        if not self.candidates:
            self.state = "none"
            self.changed.emit()
            return
        self._apply(self.suggested or self.candidates)

    def answer(self, works):
        if self.state == "level":
            self._finish_level(works)
            return
        if self.state != "ask":
            return
        if self.phase == "suggested":
            if works:
                self._keep(self.suggested)      # only the probable cause stays off
            else:
                self.phase = "all"              # not that one alone: the full search
                self._apply(self.candidates)
            return
        if self.phase == "all":
            if not works:
                # still broken without any of them: maybe something only the
                # whole shield does (language header, list scriptlets...)
                self.phase = "level"
                self.state = "level"
                self._restore()
                self.app.config["site_levels"][self.host] = "off"
                self._reload()
                return
            self.phase = "groups"
            self.queue = _halves(self.candidates)
            self._next()
            return
        # phase "groups": the group in self.testing was turned back on
        if works:
            self.innocent += self.testing
        elif len(self.testing) == 1:
            self.culprits += self.testing
            # one found: try everything not checked yet in a single step
            rest = [k for g in self.queue for k in g]
            self.queue = [rest] if rest else []
        else:
            self.queue = _halves(self.testing) + self.queue
        self._next()

    def _next(self):
        if self.queue:
            self.testing = self.queue.pop(0)
            on = self.innocent + self.testing
            self._apply([k for k in self.candidates if k not in on])
            return
        self.testing = None
        if not self.culprits:
            # every group worked alone: the page breaks only with several of
            # them together, keep them all off rather than guessing
            self.culprits = [k for k in self.candidates if k not in self.innocent] or list(self.candidates)
        self._keep(self.culprits)

    def _keep(self, keys):
        cfg = self.app.config
        self._restore()
        for k in self.candidates:
            set_off(cfg, self.host, k, k in keys)
        o = cfg["site_opts"].setdefault(self.host, {})
        o["repaired"] = sorted(set(o.get("repaired", [])) | set(keys))
        self.culprits = list(keys)
        cfg.save()
        self.state = "found"
        self._reload()

    def _finish_level(self, works):
        """Asked after the whole shield was turned off for the site."""
        self._restore()
        if works:
            self.app.config["site_levels"][self.host] = "off"
            self.app.config.save()
            self.state = "level-kept"
        else:
            self.state = "none"
        self._reload()

    def cancel(self):
        if self.state in ("ask", "level"):
            self._restore()
            self.state = "cancelled"
            self._reload()
        else:
            self.state = "cancelled"
            self.changed.emit()


def _halves(group):
    if len(group) <= 1:
        return [list(group)] if group else []
    mid = (len(group) + 1) // 2
    return [list(group[:mid]), list(group[mid:])]


class RepairBar(QWidget):
    """The question shown above the page while a repair runs."""

    def __init__(self, window):
        super().__init__(window)
        self.win = window
        self.repair = None
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 4, 6, 4)
        self.text = QLabel(self)
        self.text.setWordWrap(True)
        self.yes = QPushButton(T("Yes, it works"), self)
        self.no = QPushButton(T("No, still broken"), self)
        self.undo_btn = QPushButton(T("Undo"), self)
        close = QToolButton(self)
        close.setAutoRaise(True)
        close.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_TitleBarCloseButton))
        close.setToolTip(T("Cancel"))
        lay.addWidget(self.text, 1)
        for b in (self.yes, self.no, self.undo_btn):
            lay.addWidget(b)
        lay.addWidget(close)
        self.yes.clicked.connect(lambda: self.repair and self.repair.answer(True))
        self.no.clicked.connect(lambda: self.repair and self.repair.answer(False))
        self.undo_btn.clicked.connect(self._undo)
        close.clicked.connect(self.cancel)
        self.setAutoFillBackground(True)
        self.hide()

    def start(self, view, host, suggested=()):
        self.cancel()
        self.repair = Repair(self.win.app, view, host, suggested)
        self.repair.changed.connect(self._show)
        view.destroyed.connect(self._view_gone)
        if not self.isVisible():
            from . import polish
            polish.fade_child(self, self.win.app.config)
        self.show()
        self.repair.start()
        self._show()

    def _view_gone(self, *_):
        if self.repair is not None:
            self.repair.view = None
            self.cancel()

    def cancel(self):
        r, self.repair = self.repair, None
        if r is not None:
            r.cancel()
        self.hide()
        self.win.update_shield()

    def _undo(self):
        r = self.repair
        if r is None:
            return
        cfg = self.win.app.config
        if r.state == "level-kept":
            cfg["site_levels"].pop(r.host, None)
        else:
            undo(cfg, r.host)
        cfg.save()
        self.repair = None
        r.state = "cancelled"
        r._reload()
        self.hide()
        self.win.update_shield()

    def _show(self):
        r = self.repair
        if r is None:
            return
        asking = r.state in ("ask", "level")
        self.yes.setVisible(asking)
        self.no.setVisible(asking)
        self.undo_btn.setVisible(r.state in ("found", "level-kept"))
        if r.state == "ask" and r.phase == "suggested":
            msg = T("Repair: the probable cause is off on this site for a moment, every other "
                    "protection stays on. Does the page work now?")
        elif r.state == "ask" and r.phase == "all":
            msg = T("Repair: every protection is off on this site for a moment. Does the page work now?")
        elif r.state == "ask":
            msg = T("Repair, step %d: some protections are back on. Does the page still work?") % r.step
        elif r.state == "level":
            msg = T("Turning off single protections did not help. The whole shield is off on this "
                    "site now: does the page work?")
        elif r.state == "found":
            msg = T("Repaired. Turned off on this site only: %s.") % ", ".join(
                T(NAMES[k]) for k in r.culprits)
        elif r.state == "level-kept":
            msg = T("Repaired: protection is off for this site.")
        elif r.state == "none":
            msg = T("The protections are not the cause: everything is back as it was.")
        else:
            self.hide()
            return
        if r.state in ("found", "level-kept", "none") and r.view is not None:
            # the user said the page works, or that it does not work even with
            # every protection off (not I.K.E.'s doing): the interference ends
            diagnosis = getattr(self.win.app, "diagnosis", None)
            if diagnosis is not None:
                diagnosis.resolved(r.view)
        self.text.setText(msg)
        self.show()
        self.win.update_shield()
